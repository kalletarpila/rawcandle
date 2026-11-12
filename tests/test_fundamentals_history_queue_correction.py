"""Rolling retention and historical queue contracts; only disposable finance."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.admin import acquisition_snapshot as fetch
from rawcandle.fundamentals.admin import refresh_fundamentals as refresh
from rawcandle.fundamentals.admin import refresh_review_queue as queue
from rawcandle.fundamentals.admin.artifacts import sha256_file
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.generations import (
    ROLE_FILENAMES,
    migrate_flat_layout,
    resolve_active_generation,
)
from tests.test_fundamentals_acquisition_snapshot import (
    Response,
    Transport,
    NOW,
    OP,
    SECRET,
)
from tests.test_fundamentals_admin_refresh_copy_test import (
    create_provider,
    create_canonical,
    _insert_legacy_version,
    source_row,
)
from tests.test_fundamentals_admin_refresh_review_queue import _ticker_local_review
from tests.provider_capture_fixtures import full_row


def quarter(ticker, dimension, year, number):
    month = number * 3
    following = date(year + int(month == 12), month % 12 + 1, 1)
    period = following - timedelta(days=1)
    filing = period + timedelta(days=30) if dimension == "ARQ" else period
    return full_row(
        source_row(
            ticker=ticker,
            dimension=dimension,
            date=filing.isoformat(),
            reportperiod=period.isoformat(),
            fiscalperiod=f"{year}-Q{number}",
            revenue=100,
        )
    )


def histories():
    return {
        d: [
            quarter("TEST", d, year, q)
            for year in range(2016, 2027)
            for q in range(1, 5)
            if (2016, 2) <= (year, q) <= (2026, 3)
        ]
        for d in ("ARQ", "MRQ")
    }


def native_old(tmp_path, rows):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    provider = data / ROLE_FILENAMES["provider"]
    create_provider(provider)
    with sqlite3.connect(provider) as db:
        for d in ("ARQ", "MRQ"):
            for n, row in enumerate(rows[d]):
                _insert_legacy_version(db, row, f"old-{d}-{n}")
    canonical = data / ROLE_FILENAMES["canonical"]
    create_canonical(canonical)
    with sqlite3.connect(canonical) as db:
        db.execute(
            "INSERT INTO v4_quarter VALUES(2,1,2016,'Q2','2016-06-30','2016-Q2','2016-06-30','SHARADAR_ARQ','ACCEPTED','2016-07-30',NULL,'old','old')"
        )
        db.execute(
            "INSERT INTO v4_quarter_financials(quarter_id,revenue,canonical_source_policy,created_at_utc,updated_at_utc) VALUES(2,77,'SHARADAR_ARQ_PRIMARY','old','old')"
        )
        db.execute(
            "UPDATE v4_quarter SET first_public_result_date='2016-07-30' WHERE quarter_id=2"
        )
    with sqlite3.connect(data / ROLE_FILENAMES["analysis"]) as db:
        db.execute("CREATE TABLE old_analysis(value)")
    migrate_flat_layout(project_root=project, generation_id="old")
    return project


def acquire(tmp_path, project, rows, monkeypatch=None):
    class NativeTransport(Transport):
        def __call__(self, request, timeout):
            from urllib.parse import parse_qs, urlsplit

            if "/schema/" in request.full_url:
                return super().__call__(request, timeout)
            p = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
            self.calls.append((p["ticker"], p["dimension"]))
            return Response(
                [r for r in rows[p["dimension"]] if p["from"] <= r["date"] <= p["to"]]
            )

    transport = NativeTransport()
    result = fetch.start_fetch(
        ["TEST"],
        project_root=project,
        root=tmp_path / "runs",
        operation_id=OP,
        source_day="2026-11-11",
        client=transport.client(),
        now=lambda: NOW,
    )
    assert result["status"] == "FETCH_SEALED"
    return fetch.open_snapshot(OP, root=tmp_path / "runs"), transport


def role_hashes(project):
    return {
        r: sha256_file(p)
        for r, p in resolve_active_generation(project).role_paths().items()
    }


def test_ordinary_rolling_expiry_and_new_quarter_keep_exact_old_authority(tmp_path):
    rows = histories()
    old = {d: rows[d][:-1] for d in rows}
    project = native_old(tmp_path, old)
    before = role_hashes(project)
    # Request date includes the OLD ARQ filing, but actual returned financial
    # periods now begin later. Filing date is not the rolling report boundary.
    incoming = {d: rows[d][1:] for d in rows}
    snap, transport = acquire(tmp_path, project, incoming)
    slot = snap.read_slot(0)
    assert slot["source_history_comparison_required"]
    assert not slot["incoming_financial_input_eligible"]
    transport.calls.clear()
    comparison = snap.compare_source_history("TEST", project_root=project)
    assert comparison["status"] == "OLD_RETAINED_SOURCE_READY"
    assert not comparison["ticker_local_hold_required"]
    assert comparison["incoming_source_for_phase2_eligible"]
    assert comparison["automatic_deletion_authorized"] is False
    assert comparison["publication_authorized"] is False
    assert all(
        e["event"] == refresh.AGED_OUT_OF_SOURCE_WINDOW for e in comparison["events"]
    )
    assert (
        comparison["observed_provider_coverage"]["ARQ"]["min_reportperiod"]
        == "2016-09-30"
    )
    assert not transport.calls
    assert role_hashes(project) == before
    active = resolve_active_generation(project)
    with sqlite3.connect(
        f"file:{active.role_paths()['canonical']}?mode=ro", uri=True
    ) as db:
        assert db.execute(
            "SELECT q.period_end,q.first_public_result_date,f.revenue FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) WHERE q.quarter_id=2"
        ).fetchone() == ("2016-06-30", "2016-07-30", 77)
    current = refresh.load_current_history(
        active.role_paths()["provider"], "TEST", "ARQ"
    )
    assert len(current["rows"]) == len(old["ARQ"])
    assert all(capture.envelope(row) is None for row in current["rows"])
    assert incoming["ARQ"][-1]["fiscalperiod"] == "2026-Q3"


@pytest.mark.parametrize("missing", [(2022, 2), (2026, 2)])
def test_missing_inside_complete_window_is_local_comparison_not_deletion(
    tmp_path, missing
):
    rows = histories()
    project = native_old(tmp_path, rows)
    before = role_hashes(project)
    incoming = {
        d: [r for r in rows[d] if r["fiscalperiod"] != f"{missing[0]}-Q{missing[1]}"]
        for d in rows
    }
    snap, _ = acquire(tmp_path, project, incoming)
    comparison = snap.compare_source_history("TEST", project_root=project)
    assert comparison["status"] == "SOURCE_HISTORY_REVIEW_REQUIRED"
    assert comparison["ticker_local_hold_required"]
    assert not comparison["incoming_source_for_phase2_eligible"]
    assert all(e["event"] == refresh.TRUE_SOURCE_REMOVAL for e in comparison["events"])
    assert not comparison["automatic_deletion_authorized"]
    assert snap.read_slot(0)["receipt"]["state"] == "COMPLETE_VERIFIED"
    assert role_hashes(project) == before


def test_short_response_does_not_prove_ten_year_retention_boundary(tmp_path):
    rows = histories()
    project = native_old(tmp_path, rows)
    snap, _ = acquire(tmp_path, project, {d: rs[-4:] for d, rs in rows.items()})
    comparison = snap.compare_source_history("TEST", project_root=project)
    assert comparison["ticker_local_hold_required"]
    assert not comparison["incoming_source_for_phase2_eligible"]
    assert any(
        e["classification_reason"] == "EFFECTIVE_PROVIDER_BOUNDARY_UNPROVEN"
        for e in comparison["events"]
    )


def test_fiscal_labels_alone_cannot_prove_effective_reportperiod_window(tmp_path):
    rows = histories()
    project = native_old(tmp_path, rows)
    source = {d: [deepcopy(r) for r in rs[1:]] for d, rs in rows.items()}
    # A misleading old fiscal label must not turn a short actual report span
    # into proof of a decade-wide response.
    for values in source.values():
        for n, r in enumerate(values):
            r["reportperiod"] = f"2025-{(n%12)+1:02d}-01"
    snap, _ = acquire(tmp_path, project, source)
    result = snap.compare_source_history("TEST", project_root=project)
    assert not result["incoming_source_for_phase2_eligible"]


def test_outside_request_old_only_history_does_not_require_remote_reappearance(
    tmp_path,
):
    rows = histories()
    for d in rows:
        rows[d].insert(0, quarter("TEST", d, 2010, 1))
    project = native_old(tmp_path, rows)
    before = role_hashes(project)
    snap, _ = acquire(tmp_path, project, {d: rs[2:] for d, rs in rows.items()})
    result = snap.compare_source_history("TEST", project_root=project)
    assert result["outside_request_old_rows_preserved"] >= 2
    assert not result["ticker_local_hold_required"]
    assert role_hashes(project) == before


def test_old_v1_sealed_checkpoint_remains_readable_without_new_capture(
    tmp_path, monkeypatch
):
    rows = histories()
    project = native_old(tmp_path, rows)
    with monkeypatch.context() as patch:
        patch.setattr(fetch, "POLICY", fetch.LEGACY_POLICY)
        snap, transport = acquire(tmp_path, project, rows)
    original = snap.read_slot(0)["records"][0]
    reread = fetch.open_snapshot(OP, root=tmp_path / "runs")
    assert capture.envelope(reread.read_slot(0)["records"][0]) == capture.envelope(
        original
    )
    assert reread.manifest["policy"] == fetch.LEGACY_POLICY
    assert reread.validate_preflight(
        old_authority=fetch.pin_old_authority(project), now=NOW + timedelta(days=7)
    )["acquisition_eligible"]


def original_writer_binding(item, extended):
    """Independent historical writer contract, no new-reader hash shortcuts."""
    context = item["review_context"]
    order = lambda xs: sorted(
        xs, key=lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"))
    )
    result = {
        "ticker": item["ticker"].upper(),
        "queue_item_id": item["queue_item_id"],
        "review_type": item["review_type"],
        "reason_codes": sorted(item["reason_codes"]),
        "affected_source_keys": order(item["affected_source_keys"]),
        "fiscal_identities": order(item["fiscal_identities"]),
        "source_evidence_fingerprint": item["source_evidence_fingerprint"],
        "published_binding": item["last_published_binding"],
        "identity_binding": context.get("identity_binding", {}),
        "locality_proof": context.get("locality_proof", {}),
    }
    fields = ["capture_integrity", "historical_freeze"] + (
        ["quarantine_locality", "baseline_integrity_hold"] if extended else []
    )
    return result | {k: context[k] for k in fields if context.get(k)}


def old_queue_row(tmp_path, *, extended=True, baseline=True):
    path = tmp_path / "queue.db"
    q = queue.RefreshReviewQueue(path)
    item = q.upsert_local(
        queue.classify_review_scope(_ticker_local_review("TEST", 1)),
        run_id="old-writer",
        published_binding="old",
    )
    context = item["review_context"]
    if extended:
        context["quarantine_locality"] = {
            "contract": "ARCHIVED_QUARANTINE_V1",
            "ticker": "TEST",
            "scope": "TICKER_LOCAL_REVIEW",
            "old_generation": "old",
        }
    if baseline and extended:
        context["baseline_integrity_hold"] = {
            "carry_forward_authority": {"generation_id": "old"},
            "new_incoming_evidence_accepted": False,
        }
    context["queue_evidence_fingerprint"] = fingerprint(
        original_writer_binding(item, extended)
    )
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE refresh_review_queue SET review_context_json=? WHERE ticker=?",
            (json.dumps(context), "TEST"),
        )
    return q, item


@pytest.mark.parametrize(
    "extended,baseline", [(False, False), (True, False), (True, True)]
)
def test_original_writer_rows_read_without_database_migration(
    tmp_path, extended, baseline
):
    q, item = old_queue_row(tmp_path, extended=extended, baseline=baseline)
    before = sha256_file(q.path)
    actual = q.get("TEST")
    assert actual["review_context"] == item["review_context"]
    assert actual["operator_action"] is None and actual["status"] == "OPEN"
    assert sha256_file(q.path) == before
    assert not queue.match_retained_history_approval(
        actual, {}, published_binding="old"
    )["applied"]


@pytest.mark.parametrize(
    "target",
    [
        "quarantine_locality",
        "baseline_integrity_hold",
        "source_evidence_fingerprint",
        "identity",
        "affected_keys",
    ],
)
def test_bound_evidence_tampering_is_not_accepted_as_legacy_local(tmp_path, target):
    q, item = old_queue_row(tmp_path)
    with sqlite3.connect(q.path) as db:
        if target == "source_evidence_fingerprint":
            db.execute(
                "UPDATE refresh_review_queue SET source_evidence_fingerprint='tampered'"
            )
        elif target == "affected_keys":
            db.execute("UPDATE refresh_review_queue SET affected_source_keys_json='[]'")
        else:
            context = item["review_context"]
            if target == "identity":
                context["identity_binding"]["company_id"] = 999
            else:
                context[target]["tampered"] = True
            db.execute(
                "UPDATE refresh_review_queue SET review_context_json=?",
                (json.dumps(context),),
            )
    before = sha256_file(q.path)
    with pytest.raises(ValueError, match="EVIDENCE_TAMPERED"):
        q.get("TEST")
    assert sha256_file(q.path) == before


def test_unknown_version_and_missing_extended_binding_fail_closed(tmp_path):
    q, item = old_queue_row(tmp_path)
    for version in ("UNKNOWN", None):
        context = deepcopy(item["review_context"])
        if version:
            context["queue_evidence_version"] = version
        else:
            context.pop("queue_evidence_fingerprint")
        with sqlite3.connect(q.path) as db:
            db.execute(
                "UPDATE refresh_review_queue SET review_context_json=?",
                (json.dumps(context),),
            )
        with pytest.raises(ValueError, match="VERSION_UNKNOWN|BINDING_MISSING"):
            q.get("TEST")


def test_terminal_resolution_and_operator_authority_are_not_reopened(tmp_path):
    q, item = old_queue_row(tmp_path)
    with sqlite3.connect(q.path) as db:
        db.execute(
            "UPDATE refresh_review_queue SET status='RESOLVED',operator_action='WAIT_FOR_PROVIDER',resolution_at_utc='old',resolution_evidence_json='{}'"
        )
    before = sha256_file(q.path)
    actual = q.get("TEST")
    assert actual["status"] == "RESOLVED" and actual["resolution_at_utc"] == "old"
    assert not queue.retained_history_approval_eligibility(actual)["eligible"]
    assert not queue.fiscal_revision_approval_eligibility(actual)["eligible"]
    assert not queue.true_removal_approval_eligibility(actual)["eligible"]
    assert sha256_file(q.path) == before


def test_one_hundred_independent_native_local_holds_do_not_become_global():
    changes = [_ticker_local_review(f"T{n}", n + 1) for n in range(125)]
    changes.append({"ticker": "SAFE", "classification": "NEW_QUARTER"})
    partition = queue.partition_changes(changes)
    assert len(partition["held"]) == 125 and not partition["global_blockers"]
    assert [s["ticker"] for s in partition["safe_changes"]] == ["SAFE"]


def test_shared_contract_corruption_is_not_silently_relabelled_local(tmp_path):
    q, item = old_queue_row(tmp_path)
    other = queue.classify_review_scope(_ticker_local_review("SAFE", 2))
    q.upsert_local(other, run_id="safe", published_binding="old")
    with sqlite3.connect(q.path) as db:
        db.execute(
            "UPDATE refresh_review_queue SET source_evidence_fingerprint='corrupt' WHERE ticker='TEST'"
        )
    assert q.get("SAFE")["ticker"] == "SAFE"
    with pytest.raises(ValueError, match="EVIDENCE_TAMPERED"):
        q.list_items()


def test_per_ticker_comparison_pins_manifest_without_rehashing_all_roles(
    tmp_path, monkeypatch
):
    rows = histories()
    project = native_old(tmp_path, rows)
    snap, _ = acquire(tmp_path, project, {d: rs[1:] for d, rs in rows.items()})
    monkeypatch.setattr(
        fetch,
        "pin_old_authority",
        lambda *a, **k: pytest.fail("per-ticker role rehash"),
    )
    assert snap.compare_source_history("TEST", project_root=project)[
        "incoming_source_for_phase2_eligible"
    ]
    manifest = project / "data/fundamentals_active_generation.json"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(fetch.SnapshotError, match="OLD_AUTHORITY_DRIFT"):
        snap.compare_source_history("TEST", project_root=project)


def test_recognized_explicit_evidence_version_is_bound_and_readable(tmp_path):
    q, item = old_queue_row(tmp_path)
    item["review_context"]["queue_evidence_version"] = queue.QUEUE_EVIDENCE_VERSION
    item["review_context"]["queue_evidence_fingerprint"] = fingerprint(
        queue._queue_evidence_binding(item)
    )
    with sqlite3.connect(q.path) as db:
        db.execute(
            "UPDATE refresh_review_queue SET review_context_json=?",
            (json.dumps(item["review_context"]),),
        )
    before = sha256_file(q.path)
    assert (
        q.get("TEST")["review_context"]["queue_evidence_version"]
        == queue.QUEUE_EVIDENCE_VERSION
    )
    assert sha256_file(q.path) == before
