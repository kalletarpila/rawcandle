"""Installed identity authority, scoped acquisition and real copy publication."""

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.admin import acquisition_snapshot as acquisition
from rawcandle.fundamentals.admin import (
    refresh_update as core,
    refresh_universe as scope,
)
from rawcandle.fundamentals.admin import review_locality as locality
from rawcandle.fundamentals.admin.candidate_publication import select_candidate_scope
from rawcandle.fundamentals.phase13b_foundation import universe_identity
from tests import test_fundamentals_snapshot_integration as fixtures


def subset_authority(fixture, exclude):
    """Construct a native, consistent installed fixture version; retain OLD."""
    with sqlite3.connect(fixture.paths.canonical_db) as db:
        db.row_factory = sqlite3.Row
        vid = db.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version"
        ).fetchone()[0]
        members = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? ORDER BY company_id",
                (vid,),
            )
            if r["company_id"] not in exclude
        ]
        aliases = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM fundamentals_operational_universe_member_alias WHERE universe_version_id=? ORDER BY company_id,security_id,alias_ticker",
                (vid,),
            )
            if r["company_id"] not in exclude
        ]
        identity = universe_identity(members, aliases, as_of_date="2026-11-11")
        new_id = identity["universe_version_id"]
        db.execute(
            "INSERT INTO fundamentals_operational_universe_version VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id,
                "PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1",
                "CURRENT_OPERATIONAL_UNIVERSE",
                "2026-11-11",
                identity["source_fingerprint"],
                identity["economic_result_fingerprint"],
                identity["physical_content_fingerprint"],
                "COMPLETE",
                identity["member_count"],
                identity["company_count"],
                identity["active_security_count"],
                identity["zero_active_company_count"],
                identity["multi_active_company_count"],
                fixtures.fixtures.native.NOW,
                fixtures.fixtures.native.NOW,
            ),
        )
        for table, rows in [
            ("fundamentals_operational_universe_member", members),
            ("fundamentals_operational_universe_member_alias", aliases),
        ]:
            for row in rows:
                row["universe_version_id"] = new_id
                columns = ",".join(row)
                db.execute(
                    f'INSERT INTO {table}({columns}) VALUES({",".join("?" for _ in row)})',
                    tuple(row.values()),
                )
        db.execute(
            "UPDATE fundamentals_operational_universe_active_version SET universe_version_id=?",
            (new_id,),
        )


def configure(kind):
    def apply(fixture):
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            if kind == "alias":
                db.execute(
                    "INSERT INTO ticker_alias VALUES(900,10,'OLD','SHARADAR','2010-01-01','2020-01-01','fixture proven alias')"
                )
            elif kind == "collision":
                db.execute(
                    "INSERT INTO ticker_alias VALUES(900,20,'AAA','SHARADAR',NULL,NULL,'fixture collision')"
                )
            elif kind == "multi":
                db.execute(
                    "INSERT INTO security VALUES(11,1,'AAAB','NASDAQ',1,NULL,NULL,'fixture','fixture')"
                )
            elif kind == "historical":
                db.execute("UPDATE security SET active=0 WHERE company_id=2")
        if kind == "outside":
            subset_authority(fixture, {2})

    return apply


def environment(tmp_path, monkeypatch, kind=None, **kwargs):
    return fixtures.setup(
        tmp_path,
        monkeypatch,
        configure_universe=configure(kind) if kind == "outside" else None,
        prepare_identity=configure(kind) if kind and kind != "outside" else None,
        **kwargs,
    )


@pytest.mark.parametrize(
    "origin",
    ["discovered", "financial_reviews", "accounting_queue", "accounting_installed"],
)
def test_selected_union_requires_admitted_identity_for_each_origin(
    tmp_path, monkeypatch, origin
):
    workflow, _, _, _ = environment(tmp_path, monkeypatch, "outside")
    installed = scope.InstalledUniverse(workflow.env.paths())
    result = installed.plan(**{origin: ["AAA", "BBB", "NEW"]})
    assert result["evaluation_tickers"] == ["AAA"]
    assert {r["ticker"] for r in result["scope_exclusions"]} == {"BBB", "NEW"}
    assert not result["scope_ambiguities"]
    assert all(r["origin"] == origin for r in result["scope_resolutions"])


def test_review_and_accounting_members_selected_without_source_change(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = environment(tmp_path, monkeypatch)
    installed = scope.InstalledUniverse(workflow.env.paths())
    result = installed.plan(
        discovered=[], financial_reviews=["AAA"], accounting_installed=["BBB"]
    )
    assert result["evaluation_tickers"] == ["AAA", "BBB"]
    assert not result["scope_exclusions"]


def test_proven_historical_alias_normalizes_to_current_identity(tmp_path, monkeypatch):
    workflow, _, _, _ = environment(tmp_path, monkeypatch, "alias")
    installed = scope.InstalledUniverse(workflow.env.paths())
    result = installed.plan(discovered=["OLD", "AAA"])
    assert result["evaluation_tickers"] == ["AAA"]
    assert {r["identity"]["security_id"] for r in result["scope_resolutions"]} == {10}
    with pytest.raises(
        scope.RefreshUniverseError, match="INCOMING_SCOPE_NOT_AUTHORIZED"
    ):
        installed.require_tickers(["OLD"])


@pytest.mark.parametrize("kind", ["multi", "collision"])
def test_admitted_identity_ambiguity_stops_before_fetch(tmp_path, monkeypatch, kind):
    workflow, _, _, calls = environment(tmp_path, monkeypatch, kind)
    result = workflow.start(stop_after="fetch", ownership_intent=False)
    assert result["outcome"] == "FAILED"
    assert result["message"] == "REFRESH_ADMITTED_IDENTITY_AMBIGUOUS"
    assert not (workflow.env.runs / result["fetch_operation_id"]).exists()
    assert not any(len(c) == 2 and c[0] in ("AAA", "BBB", "AAAB") for c in calls)
    discovery = core._read(workflow.env.directory() / "discovery.json")
    assert any(r["ticker"] == "AAA" for r in discovery["scope_ambiguities"])


def test_old_only_multi_security_remains_a_financial_global_blocker(
    tmp_path, monkeypatch
):
    workflow, _, histories, _ = environment(tmp_path, monkeypatch, "multi")
    del histories["AAA"]  # Existing ambiguous OLD company has no raw discovery.
    result = workflow.start(stop_after="validate", ownership_intent=False)
    assert result["outcome"] == "BLOCKED", result
    receipt = core._read(
        workflow.env.runs / result["validation_id"] / "validation_receipt.json"
    )
    decisions = core._read(
        workflow.env.runs / result["validation_id"] / "decisions.json"
    )
    assert receipt["counts"]["global"] == 2
    assert {r["ticker"] for r in decisions["global"]} == {"AAA", "AAAB"}
    assert not (workflow.env.runs / result["validation_id"] / "candidate").exists()


def old_identity(paths, ticker):
    with sqlite3.connect(paths.canonical_db) as db:
        company, sid = db.execute(
            "SELECT company_id,security_id FROM security WHERE current_ticker=?",
            (ticker,),
        ).fetchone()
        pid = db.execute(
            "SELECT provider_security_id FROM provider_security_identity WHERE security_id=? AND provider='SHARADAR'",
            (sid,),
        ).fetchone()[0]
    return dict(company_id=company, security_id=sid, provider_security_id=str(pid))


def historical_scores(paths, company):
    # Compare regenerated financial history by economic quarter, not new row IDs.
    with sqlite3.connect(paths.analysis_db) as db:
        db.execute("ATTACH DATABASE ? AS canonical", (str(paths.canonical_db),))
        cols = [r[1] for r in db.execute("PRAGMA table_info(score_result)")]
        values = [
            col
            for col in cols
            if col
            not in {
                "score_result_id",
                "quarter_id",
                "run_id",
                "calculated_at_utc",
                "created_at_utc",
                "updated_at_utc",
                "generated_at_utc",
            }
        ]
        selected = ",".join("s." + col for col in values)
        return sorted(
            db.execute(
                f"SELECT q.fiscal_year,q.fiscal_quarter,{selected} FROM score_result s JOIN canonical.v4_quarter q USING(quarter_id) WHERE s.company_id=?",
                (company,),
            ).fetchall()
        )


def test_scoped_native_workflow_preserves_old_and_publishes_one_candidate(
    tmp_path, monkeypatch
):
    workflow, _, histories, calls = environment(
        tmp_path, monkeypatch, "outside", established=True
    )
    paths = workflow.env.paths()
    identity = old_identity(paths, "BBB")
    old = locality.authority(paths.provider_db, paths.canonical_db, "BBB", identity)
    scores = historical_scores(paths, identity["company_id"])
    history = scope.analysis_history(
        paths.analysis_db, paths.canonical_db, {identity["company_id"]}
    )
    assert all(history.values())
    assert scores
    with sqlite3.connect(paths.canonical_db) as db:
        old_securities = db.execute(
            "SELECT * FROM security ORDER BY security_id"
        ).fetchall()
    histories["NEW"] = deepcopy(
        histories["BBB"]
    )  # Raw discovery only; cannot be fetched.
    result = workflow.start(stop_after="build", ownership_intent=False)
    assert result["outcome"] == "CANDIDATE_READY", result
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert [c for c in calls if c[0] in ("AAA", "BBB", "NEW")] == [
        ("AAA", "ARQ"),
        ("AAA", "MRQ"),
    ]
    discovery = core._read(workflow.env.directory() / "discovery.json")
    assert discovery["evaluation_tickers"] == ["AAA"]
    assert discovery["changed_tickers"] == ["AAA"]
    assert set(discovery["raw_changed_tickers"]) == {"AAA", "BBB", "NEW"}
    assert result["refresh_scope"]["excluded_tickers"] == 2
    assert {r["ticker"] for r in discovery["scope_exclusions"]} == {"BBB", "NEW"}
    receipt = core._read(
        workflow.env.runs / result["validation_id"] / "validation_receipt.json"
    )
    assert (
        receipt["inputs"]["update"]["refresh_universe"]
        == workflow.env.request()["refresh_universe"]
    )
    build = core._read(workflow.env.runs / result["validation_id"] / "build.json")
    assert build["analysis_result"]["invocation_counts"]["full_v2_rebuild"] == 1
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    current = workflow.env.paths()
    assert (
        locality.authority(current.provider_db, current.canonical_db, "BBB", identity)
        == old
    )
    assert historical_scores(current, identity["company_id"]) == scores
    assert (
        scope.analysis_history(
            current.analysis_db, current.canonical_db, {identity["company_id"]}
        )
        == history
    )
    with sqlite3.connect(current.canonical_db) as db:
        assert (
            db.execute("SELECT * FROM security ORDER BY security_id").fetchall()
            == old_securities
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM security WHERE current_ticker='NEW'"
            ).fetchone()[0]
            == 0
        )
    assert (
        core.journals.load_journal(workflow.env.journal)["postflight_state"] == "PASSED"
    )


def test_inactive_old_analysis_incompatibility_stops_before_candidate(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = environment(
        tmp_path, monkeypatch, "historical", established=True
    )
    old_paths = workflow.env.paths()
    before = {
        r: core.sha256_file(p)
        for r, p in old_paths.as_dict().items()
        if r in ("provider", "canonical", "analysis")
    }
    result = workflow.start(stop_after="validate", ownership_intent=False)
    assert result["outcome"] == "VALIDATED", result
    result = workflow.advance(result["run_id"], stop_after="build")
    assert result["outcome"] == "FAILED", result
    assert (
        "REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED:2:score_result" in result["message"]
    )
    assert not (workflow.env.runs / result["validation_id"] / "candidate").exists()
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert {
        r: core.sha256_file(p)
        for r, p in workflow.env.paths().as_dict().items()
        if r in before
    } == before


def test_incoming_fetch_scope_and_original_request_reuse_rejected(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = environment(tmp_path, monkeypatch, "outside")
    result = workflow.start(stop_after="fetch", ownership_intent=False)
    assert result["outcome"] == "FETCH_SEALED", result
    request = workflow.env.request()
    with pytest.raises(
        scope.RefreshUniverseError, match="INCOMING_SCOPE_NOT_AUTHORIZED"
    ):
        acquisition.start_fetch(
            ["BBB"],
            project_root=workflow.env.project,
            root=workflow.env.runs,
            source_day=request["source_day"],
            update_binding=request,
            now=workflow.now,
        )
    old = dict(request)
    del old["refresh_universe"]
    with pytest.raises(scope.RefreshUniverseError, match="REQUIRED_NEW_UPDATE"):
        scope.require_binding(workflow.env.paths(), old)


@pytest.mark.parametrize("phase", ["validate", "build"])
def test_pinned_universe_drift_stops_financial_phase(tmp_path, monkeypatch, phase):
    workflow, _, _, _ = environment(tmp_path, monkeypatch)
    result = workflow.start(
        stop_after="fetch" if phase == "validate" else "validate",
        ownership_intent=False,
    )
    assert result["outcome"] in {"FETCH_SEALED", "VALIDATED"}, result
    request = workflow.env.request()
    with sqlite3.connect(workflow.env.paths().canonical_db) as db:
        db.execute(
            "UPDATE fundamentals_operational_universe_member_alias SET source='unauthorized drift'"
        )
    with pytest.raises(scope.RefreshUniverseError, match="UNIVERSE_DRIFT"):
        workflow.env.request()
    with pytest.raises(ValueError, match="UNIVERSE_DRIFT|OLD_ROLE_INTEGRITY_MISMATCH"):
        if phase == "validate":
            core.validate_snapshot(
                workflow.env,
                result["fetch_operation_id"],
                as_of_date=request["as_of_date"],
                now=workflow.now,
            )
        else:
            core.build_candidate(
                workflow.env,
                result["validation_id"],
                expected_validation_fingerprint=result["validation_fingerprint"],
                now=workflow.now,
            )


def test_uninstalled_universe_never_falls_back_to_physical_identity(
    tmp_path, monkeypatch
):
    owner, _, _, _, _ = fixtures.fixtures.setup(tmp_path, monkeypatch)
    with pytest.raises(scope.RefreshUniverseError, match="INSTALLED_UNIVERSE_REQUIRED"):
        scope.InstalledUniverse(owner.paths())


def test_publication_retry_cap_applies_after_membership_filter(tmp_path, monkeypatch):
    workflow, _, _, _ = environment(tmp_path, monkeypatch, "outside")
    paths = workflow.env.paths()
    selected = select_candidate_scope(
        paths.canonical_db,
        [],
        as_of_date="2026-11-11",
        retry_days=1000,
        retry_max_quarters=1,
        eligible_company_ids={1},
    )
    assert selected["quarter_keys"] and {k[0] for k in selected["quarter_keys"]} == {1}
    with pytest.raises(ValueError, match="NEW_QUARTER_OUTSIDE_REFRESH_UNIVERSE"):
        select_candidate_scope(
            paths.canonical_db,
            [[2, 2025, "Q4"]],
            as_of_date="2026-11-11",
            eligible_company_ids={1},
        )


def test_native_pending_reviews_respect_membership_and_remain_stored(
    tmp_path, monkeypatch
):
    workflow, _, _, calls = environment(tmp_path, monkeypatch, "outside")
    queue = core.reviews.RefreshReviewQueue(workflow.env.queue)
    for ticker in ("AAA", "BBB", "REVIEWNEW"):
        queue.upsert_local(
            dict(
                ticker=ticker,
                review_type="SOURCE_HISTORY_REVIEW_REQUIRED",
                reason_codes=["fixture pending review"],
                source_evidence_fingerprint="fixture",
                affected_source_keys=[],
                fiscal_identities=[],
            ),
            run_id="fixture",
            published_binding=None,
        )
    before = {t: queue.get(t) for t in ("AAA", "BBB", "REVIEWNEW")}
    original = workflow.client._opener

    def transport(request, timeout):
        response = original(request, timeout)
        if "/schema/" not in request.full_url and "ticker=" not in request.full_url:
            data = [r for r in json.loads(response.read()) if r["ticker"] != "AAA"]
            return fixtures.fixtures.Response(json.dumps(data).encode())
        return response

    monkeypatch.setattr(workflow.client, "_opener", transport)
    result = workflow.start(stop_after="fetch", ownership_intent=False)
    assert result["outcome"] == "FETCH_SEALED", result
    discovery = core._read(workflow.env.directory() / "discovery.json")
    assert "AAA" not in discovery["changed_tickers"]
    assert discovery["evaluation_tickers"] == ["AAA"]
    assert {r["ticker"] for r in discovery["scope_exclusions"]} == {"BBB", "REVIEWNEW"}
    assert {t: queue.get(t) for t in before} == before
    assert ("AAA", "ARQ") in calls and ("BBB", "ARQ") not in calls


def test_unversioned_alias_and_identity_handoff_never_confer_admission(
    tmp_path, monkeypatch
):
    workflow, _, _, _ = environment(tmp_path, monkeypatch)
    paths = workflow.env.paths()
    with sqlite3.connect(paths.canonical_db) as db:
        db.execute(
            "INSERT INTO ticker_alias VALUES(900,10,'UNVERSIONED','SHARADAR',NULL,NULL,'fixture')"
        )
    assert (
        scope.InstalledUniverse(paths).resolve("UNVERSIONED")["status"] == "AMBIGUOUS"
    )
    with sqlite3.connect(paths.canonical_db) as db:
        db.execute("UPDATE security SET company_id=2 WHERE security_id=10")
    with pytest.raises(scope.RefreshUniverseError, match="SECURITY_CONTRADICTION"):
        scope.InstalledUniverse(paths)


def test_installed_single_security_with_two_physical_actives_stops_before_request(
    tmp_path, monkeypatch
):
    def stale_authority(fixture):
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute(
                "INSERT INTO security VALUES(11,1,'HANDOFF','NASDAQ',1,NULL,NULL,'fixture','fixture')"
            )

    workflow, _, _, calls = fixtures.setup(
        tmp_path, monkeypatch, configure_universe=stale_authority
    )
    with pytest.raises(scope.RefreshUniverseError, match="SECURITY_CONTRADICTION"):
        workflow.start(stop_after="fetch", ownership_intent=False)
    assert not calls
    assert not (workflow.env.directory() / "update_request.json").exists()


def test_missing_old_provider_mapping_stops_without_repair_or_admission(
    tmp_path, monkeypatch
):
    def legacy_old(fixture):
        subset_authority(fixture, {2})
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute("DELETE FROM provider_security_identity WHERE security_id=20")
        with sqlite3.connect(fixture.paths.provider_db) as db:
            db.execute(
                "UPDATE provider_observation SET provider_security_id=NULL WHERE company_id=2"
            )

    workflow, _, _, calls = fixtures.setup(
        tmp_path, monkeypatch, configure_universe=legacy_old
    )
    paths = workflow.env.paths()
    before = {
        r: core.sha256_file(p)
        for r, p in paths.as_dict().items()
        if r in ("provider", "canonical", "analysis")
    }
    result = workflow.start(stop_after="validate", ownership_intent=False)
    assert result["outcome"] == "FAILED", result
    assert result["message"] == "REFRESH_OLD_RETENTION_IDENTITY_UNPROVEN:BBB"
    assert ("BBB", "ARQ") not in calls
    current = workflow.env.paths()
    assert core.resolve_active_generation(workflow.env.project).generation_id == "old"
    assert {
        r: core.sha256_file(p) for r, p in current.as_dict().items() if r in before
    } == before
    with sqlite3.connect(current.canonical_db) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM provider_security_identity WHERE security_id=20"
            ).fetchone()[0]
            == 0
        )
