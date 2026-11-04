"""Tiny real SQLite fixtures; no live source, publication or provider workflow."""
import json
import os
from pathlib import Path
import sqlite3

import pytest

from scripts import pb_rehearsal_closeout as storage


@pytest.fixture
def rehearsal(tmp_path):
    root = tmp_path / "copied_project"
    root.mkdir()
    main = root / "source.db"
    with sqlite3.connect(main) as connection:
        connection.execute("CREATE TABLE source(value)")
        connection.execute("INSERT INTO source VALUES (42)")
    receipt = root / "test_receipt.json"
    receipt.write_text('{"status":"PASSED","historical_path":"source.db"}\n')
    return root, main, receipt, tmp_path / "closeout.json", tmp_path / "ledger.json"


def close(rehearsal, **changes):
    root, _, receipt, record, _ = rehearsal
    arguments = dict(outcome="PASSED", evidence=[receipt],
                     capability_loss="Optional historical executable replay; completed disposable test")
    arguments.update(changes)
    return storage.close(root, "future", record, **arguments)


def retire(row, ledger, *, busy=lambda _: None, live=lambda: None):
    return storage.retire_exact(row, ledger, check_live=live, check_busy=busy)


def test_completed_disposable_rehearsal_preserves_audit_after_retirement(rehearsal):
    root, main, receipt, _, ledger = rehearsal
    original = receipt.read_bytes()
    row = close(rehearsal)["files"][0]
    allocated = main.stat().st_blocks * 512
    assert row["decision"] == "RETIRE_APPROVED"
    assert retire(row, ledger) == "REMOVED"
    assert not main.exists() and receipt.read_bytes() == original
    assert json.loads(ledger.read_text())["files"][str(main)]["allocated_bytes_released"] == allocated


@pytest.mark.parametrize("reason", ["Current live Test input", "Nested Test backup needed to restore open publication"])
def test_current_live_or_backup_recovery_dependency_retained(rehearsal, reason):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal, requirements={str(main): dict(owner="active-owner", reason=reason,
                                                        end_event="Verified terminal recovery")})["files"][0]
    assert row["decision"] == "RETAIN_REQUIRED"
    with pytest.raises(ValueError, match="NOT_APPROVED"):
        retire(row, ledger)
    assert main.exists() and not ledger.exists()


def test_interrupted_rehearsal_open_recovery_is_unresolved(rehearsal):
    value = close(rehearsal, outcome="INTERRUPTED")
    assert value["files"][0]["decision"] == "NEEDS_OWNER_DECISION"
    assert value["state"] == "OWNER_DECISION_REQUIRED"


def test_obsolete_generation_does_not_rewrite_immutable_receipt(rehearsal):
    root, main, receipt, _, ledger = rehearsal
    generation = root / "data/fundamentals_generations/old"
    generation.mkdir(parents=True)
    os.replace(main, generation / "canonical.db")
    original = receipt.read_bytes()
    value = close(rehearsal, outcome="SUPERSEDED")
    assert value["files"][0]["decision"] == "RETIRE_APPROVED"
    retire(value["files"][0], ledger)
    assert receipt.read_bytes() == original and "unavailable" in value["executable_replay"]


def test_changed_inode_fails_before_unlink(rehearsal):
    root, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]
    replacement = root / "replacement"
    replacement.write_bytes(main.read_bytes())
    os.replace(replacement, main)
    with pytest.raises(ValueError, match="STALE_IDENTITY"):
        retire(row, ledger)
    assert main.exists() and not ledger.exists()


def test_symlink_replacement_is_rejected(rehearsal, tmp_path):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]
    external = tmp_path / "protected.db"
    external.write_bytes(main.read_bytes())
    main.unlink()
    main.symlink_to(external)
    with pytest.raises(ValueError, match="PATH_NOT_CANONICALLY_CONFINED"):
        retire(row, ledger)
    assert external.exists()


def test_real_concurrent_sqlite_writer_blocks_retirement(rehearsal):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]
    connection = sqlite3.connect(main)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO source VALUES (99)")

        def busy(path):
            # Real descriptor observation, not a mocked SQLite lock result.
            targets = {os.readlink(p) for p in Path('/proc/self/fd').iterdir() if p.exists()}
            if path in targets:
                raise RuntimeError("ACTIVE_SQLITE_USER")

        with pytest.raises(RuntimeError, match="ACTIVE_SQLITE_USER"):
            retire(row, ledger, busy=busy)
        assert main.exists() and not ledger.exists()
    finally:
        connection.rollback()
        connection.close()


def test_repeated_closeout_and_retirement_do_not_duplicate(rehearsal):
    root, main, _, record, ledger = rehearsal
    value = close(rehearsal)
    retire(value["files"][0], ledger)
    assert close(rehearsal) == value
    assert retire(value["files"][0], ledger) == "ALREADY_REMOVED"
    assert len(json.loads(ledger.read_text())["files"]) == 1


def test_ambiguous_attempt_is_never_retried(rehearsal):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]
    storage.durable_json(ledger, {"files": {str(main): {"outcome": "PREPARED"}}})
    with pytest.raises(ValueError, match="REQUIRES_RECONCILIATION"):
        retire(row, ledger)
    assert main.exists()


@pytest.mark.parametrize("owner", ["future", "no-safe-changes"])
def test_both_owner_harnesses_record_need_and_closeout(rehearsal, owner):
    root, main, receipt, record, _ = rehearsal

    def harness():
        assert record.with_name("closeout_creation.json").exists()
        return dict(outcome="PASSED", evidence=[receipt], capability_loss="Optional replay is no longer required")

    value = storage.run_harness(root, owner, record, harness, purpose="Native publication on copies",
                                end_event="Owner comparisons and terminal postflight pass",
                                expected_allocated_bytes=main.stat().st_blocks * 512)
    assert value["owner"] == storage.OWNERS[owner]
    assert value["approved_allocated_bytes"] > 0 and value["retained_allocated_bytes"] == 0
    assert value["retained_gb"] == 0 and value["approved_gb"] > 0


def test_harness_failure_always_reports_remaining_need(rehearsal):
    root, _, _, record, _ = rehearsal

    def harness():
        raise RuntimeError("injected interruption")

    with pytest.raises(RuntimeError, match="injected"):
        storage.run_harness(root, "future", record, harness, purpose="Copy test",
                            end_event="Successful owner closeout", expected_allocated_bytes=8192)
    value = json.loads(record.read_text())
    assert value["files"][0]["decision"] == "NEEDS_OWNER_DECISION"
    assert value["retained_allocated_bytes"] > 0
    assert value["retained_gb"] > 0


def test_non_specific_retention_reason_is_rejected(rehearsal):
    _, main, _, _, _ = rehearsal
    with pytest.raises(ValueError, match="MUST_BE_CONCRETE"):
        close(rehearsal, requirements={str(main): {"reason": "Might be useful"}})


def test_new_live_requirement_cannot_reuse_old_closeout(rehearsal):
    _, main, _, _, _ = rehearsal
    close(rehearsal)
    with pytest.raises(ValueError, match="REQUIREMENTS_CHANGED"):
        close(rehearsal, requirements={str(main): dict(owner="live", reason="Active Test", end_event="Test ends")})


def test_live_drift_after_durable_decision_stops_before_unlink(rehearsal):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]
    calls = []

    def live():
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("LIVE_REFERENCE_CHANGED")

    with pytest.raises(RuntimeError, match="LIVE_REFERENCE_CHANGED"):
        retire(row, ledger, live=live)
    assert main.exists()
    assert json.loads(ledger.read_text())["files"][str(main)]["outcome"] == "PREPARED"


def test_wal_and_shm_inherit_concrete_recovery_hold(rehearsal, monkeypatch):
    root, main, receipt, record, _ = rehearsal
    connection = sqlite3.connect(main)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO source VALUES (99)")
        monkeypatch.chdir(root.parent)
        value = storage.close(Path(root.name), "future", record, outcome="PASSED", evidence=[receipt],
                              capability_loss="Not allowed while recovery is open",
                              requirements={str(main): dict(owner="recovery", reason="Open SQLite transaction", end_event="Rollback verified")})
        assert any(r["path"].endswith('-wal') for r in value['files'])
        assert all(r['decision'] == 'RETAIN_REQUIRED' for r in value['files'])
    finally:
        connection.rollback()
        connection.close()


def test_unlink_failure_stops_with_ambiguous_ledger(rehearsal, monkeypatch):
    _, main, _, _, ledger = rehearsal
    row = close(rehearsal)["files"][0]

    def fail(*args, **kwargs):
        raise OSError("injected unlink failure")

    monkeypatch.setattr(storage.os, 'unlink', fail)
    with pytest.raises(RuntimeError, match="DO_NOT_RETRY_UNLINK"):
        retire(row, ledger)
    assert main.exists()
    assert json.loads(ledger.read_text())["files"][str(main)]["outcome"] == "AMBIGUOUS_STOP"
