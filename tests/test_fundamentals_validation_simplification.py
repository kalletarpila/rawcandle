"""Equivalent detail, scoped inputs, and independent trust boundaries."""
from copy import deepcopy
from datetime import timedelta
import json
import os

import pytest

from rawcandle.fundamentals.admin import acquisition_snapshot as a, refresh_update as core
from rawcandle.fundamentals.admin.artifacts import AdminRunWriter
from rawcandle.fundamentals.admin.contracts import AdminOperationType, fingerprint
from tests import test_fundamentals_snapshot_workflow as f


def decisions():
    safe = {"ticker": "AAA", "classification": "HISTORICAL_REVISION",
            "details": [{"value": x, "created_at_utc": "run-local"} for x in range(100)]}
    held = {"ticker": "BBB", "classification": "REVIEW_REQUIRED",
            "review_reason": "UNRESOLVED", "provenance": {"source": "immutable"}}
    global_hold = {"ticker": "CCC", "classification": "REVIEW_REQUIRED",
                   "review_reason": "WHOLE_TICKER_IDENTITY_UNPROVEN"}
    unchanged = {"ticker": "DDD", "classification": "NO_EFFECTIVE_CHANGE"}
    return dict(changes=[safe, held, global_hold, unchanged], safe=[safe],
                held=[{"ticker": "BBB", "scope": "LOCAL", "change": held}],
                **{"global": [{"ticker": "CCC", "scope": "GLOBAL", "change": global_hold}]},
                plans={"AAA": {"dimensions": {}}},
                old_retention=[{"ticker": "PSQL", "scope": "OLD_RETENTION",
                                "company_id": 42, "history": "PRESERVE_EXACT_OLD"}])


def test_compact_atomic_evidence_exact_semantics_and_fingerprint(tmp_path):
    value = decisions()
    writer = AdminRunWriter("validation", AdminOperationType.REFRESH_FUNDAMENTALS, root=tmp_path)
    core._write_decisions(writer, value)
    path = writer.run_dir / "decisions.json"
    raw = core._read(path)
    assert raw["changes"][0] == {"ticker": "AAA", "partition": "safe", "index": 0}
    assert raw["held"] == value["held"] and raw["safe"] == value["safe"]
    expanded = core._read_decisions(path)
    assert expanded == value
    assert expanded["changes"][0] is expanded["safe"][0]
    assert expanded["changes"][1] is expanded["held"][0]["change"]
    assert core._decision_fingerprint(value) == fingerprint({k: value[k] for k in ("safe", "held", "global")})
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(value))
    assert core._read_decisions(legacy) == value


@pytest.mark.parametrize("reference", [
    {"ticker": "BBB", "partition": "safe", "index": 0},
    {"ticker": "AAA", "partition": "plans", "index": 0},
    {"ticker": "AAA", "partition": "safe", "index": -1},
    {"ticker": "AAA", "partition": "safe", "index": 99},
])
def test_invalid_detail_references_fail(tmp_path, reference):
    compact = core._compact_decisions(decisions())
    compact["changes"][0] = reference
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(compact))
    with pytest.raises(core.Phase2Error, match="REFERENCES_INVALID"):
        core._read_decisions(path)


def test_partial_serialization_does_not_replace_previous_evidence(tmp_path, monkeypatch):
    writer = AdminRunWriter("validation", AdminOperationType.REFRESH_FUNDAMENTALS, root=tmp_path)
    path = writer.run_dir / "decisions.json"
    path.write_text("previous")
    def fail(_):
        raise RuntimeError("interrupted")
    monkeypatch.setattr(writer, "_safe", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        core._write_decisions(writer, decisions())
    assert path.read_text() == "previous"
    assert not list(writer.run_dir.glob(".decisions.*.tmp"))


def test_verified_open_once_and_independent_preflight_rechecks(tmp_path, monkeypatch):
    env, _, _, _, acquire = f.setup(tmp_path, monkeypatch)
    op = acquire()
    calls = []
    original = a._verify_snapshot
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(a, "_verify_snapshot", counted)
    old = a.pin_old_authority(env.project)
    snapshot = a.open_snapshot(op, root=env.runs, old_authority=old, now=f.NOW)
    assert len(calls) == 1
    with pytest.raises(a.SnapshotError):
        a.open_snapshot(op, root=env.runs, old_authority=old, now=f.NOW + timedelta(hours=169))
    with pytest.raises(a.SnapshotError, match="OLD_AUTHORITY_DRIFT"):
        a.open_snapshot(op, root=env.runs, old_authority={}, now=f.NOW)
    slot = next(snapshot.iter_slots())
    receipt = a._read(snapshot._run.path(f"fetch/checkpoints/{slot['slot']:06d}.json"))
    body = snapshot._run.verify(receipt["body"], "BODY")
    original_bytes, original_stat = body.read_bytes(), body.stat()
    assert b"AAA" in original_bytes
    body.write_bytes(original_bytes.replace(b"AAA", b"ZZZ", 1))
    os.utime(body, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert body.stat().st_size == original_stat.st_size
    with pytest.raises(a.SnapshotError):
        snapshot.validate_preflight(old_authority=old, now=f.NOW)
    with pytest.raises(a.SnapshotError):
        snapshot.read_slot(slot["slot"])


def test_scoped_window_comparison_matches_independent_load(tmp_path, monkeypatch):
    env, _, _, _, acquire = f.setup(tmp_path, monkeypatch, rolling=True)
    snapshot = a.open_snapshot(acquire(), root=env.runs)
    current = {d: core.rules.load_current_history(env.paths().provider_db, "AAA", d) for d in ("ARQ", "MRQ")}
    source = {s["dimension"]: core.rules.validate_complete_history(snapshot.read_slot(s["slot"])["records"], ticker="AAA", dimension=s["dimension"])
              for s in snapshot.iter_slots() if s["ticker"] == "AAA"}
    before = deepcopy(current)
    scoped = snapshot._compare_loaded_source_history("AAA", current, source, diagnostic=False)
    assert scoped == snapshot.compare_source_history("AAA", project_root=env.project)
    assert current == before


def test_validate_loads_safe_histories_once_and_build_rechecks_source(tmp_path, monkeypatch):
    env, _, _, _, acquire = f.setup(tmp_path, monkeypatch)
    op = acquire()
    calls = []
    original = core.rules.load_current_history
    def counted(path, ticker, dimension):
        calls.append((ticker, dimension))
        return original(path, ticker, dimension)
    monkeypatch.setattr(core.rules, "load_current_history", counted)
    receipt = core.validate_snapshot(env, op, as_of_date=f.native.AS_OF, now=lambda: f.NOW)
    assert calls.count(("AAA", "ARQ")) == calls.count(("AAA", "MRQ")) == 1
    directory, _, expanded = core._load(env, receipt["validation_id"], receipt["fingerprint"])
    assert core._decision_fingerprint(expanded) == receipt["decision_fingerprint"]
    snapshot = a.open_snapshot(op, root=env.runs)
    slot = next(snapshot.iter_slots())
    checkpoint = a._read(snapshot._run.path(f"fetch/checkpoints/{slot['slot']:06d}.json"))
    body = snapshot._run.verify(checkpoint["body"], "BODY")
    body.write_bytes(body.read_bytes() + b" ")
    with pytest.raises(a.SnapshotError):
        core.build_candidate(env, receipt["validation_id"], expected_validation_fingerprint=receipt["fingerprint"], now=lambda: f.NOW)
    assert not (directory / "candidate").exists()


def test_workflow_delegates_new_validation_but_reverifies_reused_receipt(tmp_path, monkeypatch):
    from tests.test_fundamentals_snapshot_integration import setup
    workflow, _, _, _ = setup(tmp_path, monkeypatch)
    fetched = workflow.start(publication_intent=False, ownership_intent=False, stop_after="fetch")
    assert fetched["outcome"] == "FETCH_SEALED"
    original = a._verify_snapshot
    calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(a, "_verify_snapshot", counted)
    result = workflow.advance(fetched["run_id"], stop_after="validate")
    assert result["outcome"] == "VALIDATED", result
    assert len(calls) == 1
    repeated = workflow.advance(fetched["run_id"], stop_after="validate")
    assert repeated["validation_id"] == result["validation_id"]
    assert len(calls) == 2  # A later handoff never trusts a persisted verified flag.
