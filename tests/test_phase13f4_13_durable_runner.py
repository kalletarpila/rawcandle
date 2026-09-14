from __future__ import annotations

import json

from rawcandle.fundamentals import phase13f4_2_production as prod


def _patch_common(monkeypatch, *, restore_error: Exception | None = None, apply_error: Exception | None = None) -> dict[str, int]:
    calls = {"restore_backups": 0}
    monkeypatch.setattr(prod, "_preflight", lambda *args, **kwargs: {
        "production_inventory": {"active_package": {"persistence_fingerprint": "base"}, "active_relative_valuation": []},
    })
    monkeypatch.setattr(prod, "archive_reconciliation", lambda: {"rows_by_ticker": {}, "ok": True})
    monkeypatch.setattr(prod, "_copy_acceptance_candidate", lambda *args, **kwargs: {"acceptance_blockers": []})
    monkeypatch.setattr(prod, "_backup_write_set", lambda backup_dir: {
        role: {"sha256": f"{role}-sha", "destination": str(backup_dir / f"{role}.db"), "inventory": {}}
        for role in prod.WRITE_ROLES
    })
    if restore_error is None:
        monkeypatch.setattr(prod, "_restore_rehearsal", lambda *args, **kwargs: {
            "roles": {role: {"ok": True} for role in prod.WRITE_ROLES},
            "ok": True,
        })
    else:
        def fail_restore(*args, **kwargs):
            raise restore_error
        monkeypatch.setattr(prod, "_restore_rehearsal", fail_restore)
    monkeypatch.setattr(prod, "_targeted_production_inventory", lambda: {
        "active_package": {"persistence_fingerprint": "active"},
        "active_relative_valuation": [{"snapshot_id": "rv"}],
    })
    if apply_error is None:
        monkeypatch.setattr(prod, "_apply_pipeline", lambda *args, **kwargs: {"ok": True})
    else:
        def fail_apply(*args, **kwargs):
            raise apply_error
        monkeypatch.setattr(prod, "_apply_pipeline", fail_apply)
    monkeypatch.setattr(prod, "_acceptance_blockers", lambda result: [])
    monkeypatch.setattr(prod, "_second_no_change", lambda *args, **kwargs: {
        "provider_replay_changes": 0,
        "package_outcome": "NO_CHANGE",
        "package_second_apply_outcome": "NO_CHANGE",
        "relative_position_outcome": "NO_CHANGE",
        "relative_valuation_outcome": "NO_CHANGE",
        "relative_valuation_second_outcome": "NO_CHANGE",
        "inventory_exact_no_change": True,
        "inventory_normalized_no_change": True,
        "inventory_compare": {"identical": True},
    })
    monkeypatch.setattr(prod, "database_inventory", lambda path: {"quick_check": "ok", "foreign_key_errors": 0})
    monkeypatch.setattr(prod, "_light_database_inventory", lambda path: {"quick_check": "ok", "foreign_key_errors": 0})
    monkeypatch.setattr(prod, "compare_production_inventory", lambda before, after: {"identical": True})
    def restore_backups(manifest):
        calls["restore_backups"] += 1
        return {role: {"sha256": f"restored-{role}"} for role in prod.WRITE_ROLES}
    monkeypatch.setattr(prod, "_restore_backups", restore_backups)
    return calls


def _stages(output) -> list[str]:
    return [
        json.loads(line)["stage"]
        for line in (output / "stage_journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_durable_runner_records_success_path(monkeypatch, tmp_path) -> None:
    _patch_common(monkeypatch)
    output = tmp_path / "success"

    result = prod.run_phase13f4_2(output, apply=True, outcome_a="A")

    assert result["outcome"] == "A"
    assert (output / "exit_code").read_text(encoding="utf-8").strip() == "0"
    stages = _stages(output)
    assert "RESTORE_REHEARSAL_COMPLETE" in stages
    assert "FIRST_APPLY_STARTED" in stages
    assert stages[-1] == "SUCCESS"


def test_durable_runner_distinguishes_prewrite_failure_after_backup(monkeypatch, tmp_path) -> None:
    calls = _patch_common(monkeypatch, restore_error=RuntimeError("restore rehearsal failed"))
    output = tmp_path / "prewrite_failure"

    result = prod.run_phase13f4_2(output, apply=True, outcome_b="B")

    assert result["outcome"] == "B"
    assert calls["restore_backups"] == 0
    assert "FAILED_PREWRITE" in _stages(output)
    assert (output / "exit_code").read_text(encoding="utf-8").strip() == "2"


def test_durable_runner_rolls_back_postwrite_exception(monkeypatch, tmp_path) -> None:
    calls = _patch_common(monkeypatch, apply_error=RuntimeError("postwrite failed"))
    output = tmp_path / "postwrite_failure"

    result = prod.run_phase13f4_2(output, apply=True, outcome_c="C")

    assert result["outcome"] == "C"
    assert calls["restore_backups"] == 1
    stages = _stages(output)
    assert "FIRST_APPLY_STARTED" in stages
    assert "ROLLBACK_COMPLETE" in stages
    assert "FAILED_POSTWRITE" in stages
