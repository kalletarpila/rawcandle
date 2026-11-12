from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from urllib.error import URLError

import pytest

from rawcandle.fundamentals.admin import refresh_update as core, sec_snapshot
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_snapshot_integration as integration
from tests import test_fundamentals_snapshot_workflow as fixtures


@pytest.mark.parametrize("missing", [False, True])
def test_captured_sec_evidence_binds_actual_new_quarter_authority(
    tmp_path, monkeypatch, missing
):
    original = fixtures.native._migrate_refresh_fixture_to_generation_layout

    def prepare(fixture, patch):
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute(
                """INSERT INTO company_cik(company_id,cik_normalized,cik_display,source,status,created_at_utc,
                         source_type,source_name,source_field,source_value,derivation,confidence)
                         VALUES(1,'0000000001','1','TEST','ACTIVE',?,'TEST','SEC','CIK','1','DIRECT','HIGH')""",
                (fixtures.native.NOW,),
            )
        original(fixture, patch)

    monkeypatch.setattr(
        fixtures.native, "_migrate_refresh_fixture_to_generation_layout", prepare
    )
    workflow, native, histories, calls = integration.setup(tmp_path, monkeypatch)
    for dimension in ("ARQ", "MRQ"):
        histories["AAA"][dimension].append(
            fixtures.native._source_row(
                "AAA", dimension, 2026, 3, lastupdated="2026-11-04"
            )
        )
    sec_calls = []

    def raw(url):
        sec_calls.append(url)
        if "submissions" in url:
            return json.dumps(
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K"],
                            "items": ["2.02"],
                            "accessionNumber": ["0000000001-26-000001"],
                            "acceptanceDateTime": ["2026-11-04T20:00:00Z"],
                            "primaryDocument": ["results.htm"],
                        }
                    }
                }
            ).encode()
        if missing:
            raise URLError("fixture missing required primary document")
        return b"Item 2.02 Results of Operations and Financial Condition. Results for the third quarter ended September 30, 2026."

    workflow.sec_fetch_bytes = raw
    result = workflow.start(stop_after="build")
    assert result["outcome"] == "CANDIDATE_READY", result
    assert len(sec_calls) == 2

    def forbidden(url):
        raise AssertionError("SEC network after FETCH")

    workflow.sec_fetch_bytes = forbidden
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    with core.carry.readonly(workflow.env.paths().canonical_db) as db:
        authority = dict(
            db.execute(
                "SELECT * FROM v4_result_publication_authority WHERE company_id=1 AND fiscal_year=2026 AND fiscal_quarter='Q3'"
            ).fetchone()
        )
        quarter = dict(
            db.execute(
                "SELECT * FROM v4_quarter WHERE company_id=1 AND fiscal_year=2026 AND fiscal_quarter='Q3'"
            ).fetchone()
        )
    assert authority["status"] == ("UNRESOLVED" if missing else "VERIFIED")
    assert quarter["first_public_result_date"] == "2026-11-04"
    if missing:
        assert authority["result_publication_timestamp_utc"] is None
        assert result["sec_publication"]["status"] == "PARTIAL"
    else:
        assert authority["result_publication_timestamp_utc"] == "2026-11-04T20:00:00Z"


def test_sec_interrupted_capture_reuses_original_bytes_and_timestamps(tmp_path):
    plan = [
        {
            "company_id": 1,
            "cik": "1",
            "from_calendar_year": 2026,
            "from_calendar_date": "2026-01-01",
            "to_calendar_date": "2026-12-31",
        }
    ]
    reference = {"operation_id": "fetch_original", "sha256": "source"}
    calls = []

    def interrupted(url):
        calls.append(url)
        if "submissions" in url:
            return json.dumps(
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K"],
                            "items": ["2.02"],
                            "accessionNumber": ["0000000001-26-000001"],
                            "acceptanceDateTime": ["2026-11-04T20:00:00Z"],
                            "primaryDocument": ["result.htm"],
                        }
                    }
                }
            ).encode()
        raise KeyboardInterrupt("interrupted fixture")

    with pytest.raises(KeyboardInterrupt):
        sec_snapshot.capture(
            tmp_path / "sec",
            operation_id="update-original",
            snapshot_reference=reference,
            plan=plan,
            fetch_bytes=interrupted,
            now=lambda: fixtures.NOW,
        )
    pending = json.loads((tmp_path / "sec/pending.json").read_text())
    original = pending["requests"].copy()
    resumed = []

    def remaining(url):
        resumed.append(url)
        return b"Item 2.02 Results of Operations and Financial Condition. Quarter ended September 30, 2026."

    sealed = sec_snapshot.capture(
        tmp_path / "sec",
        operation_id="update-original",
        snapshot_reference=reference,
        plan=plan,
        fetch_bytes=remaining,
        now=lambda: fixtures.NOW,
    )
    assert len(resumed) == 1 and "result.htm" in resumed[0]
    assert all(sealed["requests"][url] == record for url, record in original.items())
    assert not (tmp_path / "sec/pending.json").exists()


@pytest.mark.parametrize("authorized", [False, True])
def test_no_change_ownership_requires_separate_intent_and_complete_validation(
    tmp_path, monkeypatch, authorized
):
    workflow, native, histories, calls = integration.setup(
        tmp_path, monkeypatch, ownership=True
    )
    for ticker in histories:
        histories[ticker] = {
            d: [
                dict(r["_acquisition_payload"])
                for r in core.rules.load_current_history(
                    native.paths.provider_db, ticker, d
                )["rows"]
            ]
            for d in ("ARQ", "MRQ")
        }
    observed = []

    def ownership(**kwargs):
        assert resolve_active_generation(workflow.env.project).generation_id == "old"
        observed.append(kwargs)
        return {"status": "NO_AUTO_CANDIDATES", "published": 0}

    workflow.ownership_runner = ownership
    result = workflow.start(ownership_intent=authorized)
    assert result["outcome"] == "NO_CHANGE", result
    assert len(observed) == int(authorized)
    assert not list(workflow.env.runs.glob("local_*/build.json"))
    assert not workflow.env.journal.exists()


def test_empty_update_scope_is_a_verified_source_noop(tmp_path, monkeypatch):
    workflow, native, histories, calls = integration.setup(tmp_path, monkeypatch)
    histories.clear()
    result = workflow.start()
    assert result["outcome"] == "NO_CHANGE", result
    assert calls == [("discovery", "ARQ"), ("discovery", "MRQ"), ("schema",)]
    assert not result["production_completed"]


def test_real_financial_commit_then_native_ownership_publication(tmp_path, monkeypatch):
    """Full V2 financial activation, then actual V1 ownership test/publication."""
    from rawcandle.fundamentals import ownership_basis as own
    from rawcandle.fundamentals.admin import pb_ownership_review as review
    from rawcandle.fundamentals.pb_reporting_contract import (
        activate_quarterly_ownership,
    )
    from tests.provider_capture_fixtures import trusted_history
    from copy import deepcopy
    import hashlib, shutil

    original = fixtures.native._migrate_refresh_fixture_to_generation_layout
    artifact = {}

    def economics(row):
        return {
            **row,
            "sharefactor": 1,
            "sharesbas": 100,
            "equity": 1000,
            "equityusd": 1000,
            "price": 10,
            "marketcap": 1000,
            "pb": 1,
        }

    def prepare(fixture, patch):
        histories = {
            d: trusted_history(
                [
                    economics(dict(r["_acquisition_payload"]))
                    for r in core.rules.load_current_history(
                        fixture.paths.provider_db, "AAA", d
                    )["rows"]
                ],
                ticker="AAA",
                dimension=d,
            )
            for d in ("ARQ", "MRQ")
        }
        fixtures.native.replace_provider_histories(
            fixture.paths.provider_db,
            {"AAA": histories},
            {
                "AAA": {
                    "company_id": 1,
                    "security_id": 10,
                    "provider_security_id": "100",
                }
            },
            applied_at=fixtures.native.NOW,
        )
        with sqlite3.connect(fixture.paths.provider_db) as db:
            db.execute(
                "UPDATE sharadar_ticker_metadata SET category='Domestic Common Stock Primary Class' WHERE ticker='AAA'"
            )
        fixtures.native.fresh_rebuild_canonical(
            fixture.paths.provider_db,
            fixture.paths.canonical_db,
            applied_at=fixtures.native.NOW,
        )
        with core.carry.readonly(fixture.paths.canonical_db) as db:
            basis = review.latest_basis(db, 1, as_of=fixtures.NOW.date().isoformat())
        record = deepcopy(
            next(
                r
                for r in own.ownership_reviews_v2()
                if r["release_type"] == "ORDINARY_COMMON"
            )
        )
        record.update(
            {
                k: basis[k]
                for k in (*own.BINDING, "fiscal_year", "fiscal_quarter", "reportperiod")
            }
        )
        record.update(
            accepted_sharesbas=100,
            provider_declared_factor=1,
            accepted_category="Domestic Common Stock Primary Class",
            accepted_provider_date=basis["provider_date"],
            accepted_source_availability_date=basis["source_availability_date"],
            share_source_date=basis["provider_date"],
            unit_effective_from=basis["provider_date"],
            identity_override=False,
        )
        artifact.update(contract=own.QUARTERLY_OWNERSHIP_CONTRACT, records=[record])
        monkeypatch.setattr(
            own,
            "_quarterly_artifact",
            lambda: (
                deepcopy(artifact),
                hashlib.sha256(review.serialize(artifact).encode()).hexdigest(),
            ),
        )
        activate_quarterly_ownership(
            fixture.paths.canonical_db, effective_from="2026-10-08"
        )
        with sqlite3.connect(fixture.paths.market_db) as db:
            for day in ["2026-11-04", "2026-11-11"]:
                db.execute(
                    "INSERT INTO osakedata(osake,market,pvm,open,high,low,close) VALUES('AAA','usa',?,10,11,9,10)",
                    (day,),
                )
        for dimension in ("ARQ", "MRQ"):
            fixture.client.histories["AAA"][dimension] = [
                economics(r) for r in fixture.client.histories["AAA"][dimension]
            ] + [
                economics(
                    fixtures.native._source_row(
                        "AAA", dimension, 2026, q, lastupdated="2026-11-04"
                    )
                )
                for q in (1, 2, 3)
            ]
        original(fixture, patch)

    monkeypatch.setattr(
        fixtures.native, "_migrate_refresh_fixture_to_generation_layout", prepare
    )
    monkeypatch.setattr(review, "utc_now", lambda: fixtures.NOW.isoformat())
    workflow, native, histories, calls = integration.setup(
        tmp_path, monkeypatch, ownership=True
    )
    result = workflow.start(publication_intent=True)
    assert result["outcome"] == "COMPLETED" and result["production_completed"], result
    assert result["ownership_auto"]["status"] == "COMPLETED", result["ownership_auto"]
    assert result["ownership_auto"]["published"] == 1, result["ownership_auto"]
    financial = result["publication_outcome"]["generation_id"]
    active = resolve_active_generation(workflow.env.project)
    assert active.generation_id != financial
    assert result["ownership_auto"]["financial_generation_id"] == financial
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )
    assert workflow.advance(result["run_id"], confirm_publish=True) == result


@pytest.mark.parametrize("local_stage", ["validate", "build"])
def test_local_only_noop_never_runs_ownership_publication(
    tmp_path, monkeypatch, local_stage
):
    workflow, native, histories, calls = integration.setup(
        tmp_path, monkeypatch, ownership=True
    )
    for ticker in histories:
        histories[ticker] = {
            d: [
                dict(r["_acquisition_payload"])
                for r in core.rules.load_current_history(
                    native.paths.provider_db, ticker, d
                )["rows"]
            ]
            for d in ("ARQ", "MRQ")
        }
    owned = []
    workflow.ownership_runner = lambda **kwargs: (
        owned.append(kwargs) or {"status": "NO_AUTO_CANDIDATES", "published": 0}
    )
    result = workflow.start(stop_after=local_stage)
    assert result["outcome"] == "NO_CHANGE" and not owned, result
    complete = workflow.advance(result["run_id"], stop_after="publish")
    assert complete["outcome"] == "NO_CHANGE" and len(owned) == 1, complete
    workflow.advance(result["run_id"], stop_after="publish")
    assert len(owned) == 1


def test_sec_capture_resume_cannot_reset_native_http_budget(tmp_path):
    plan = [
        {
            "company_id": 1,
            "cik": "1",
            "from_calendar_year": 2026,
            "from_calendar_date": "2026-01-01",
            "to_calendar_date": "2026-12-31",
        }
    ]

    def interrupted(url):
        raise KeyboardInterrupt("interrupted before first response")

    with pytest.raises(KeyboardInterrupt):
        sec_snapshot.capture(
            tmp_path / "sec",
            operation_id="budget-operation",
            snapshot_reference={"sha256": "source"},
            plan=plan,
            fetch_bytes=interrupted,
            now=lambda: fixtures.NOW,
        )
    attempts = []
    result = sec_snapshot.capture(
        tmp_path / "sec",
        operation_id="budget-operation",
        snapshot_reference={"sha256": "source"},
        plan=plan,
        fetch_bytes=lambda url: attempts.append(url),
        now=lambda: fixtures.NOW + timedelta(seconds=301),
    )
    assert not attempts
    assert result["network_budget_seconds"] == 300
    assert result["network"]["budget_exhausted"] == 1
    assert result["outcomes"][0]["error"] == "TimeoutError"
