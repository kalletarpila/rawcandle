from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
from rawcandle.fundamentals.admin.artifacts import sha256_file
from rawcandle.fundamentals.admin.run_acceptance_cleanup import (
    RunAcceptanceCleanupError,
    accept_run_and_cleanup_backups,
    inspect_cleanup_eligibility,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


RUN_ID = "20260922T150000Z_add_tickers_abc123_production_deadbeef"


class _Page:
    def __init__(self) -> None:
        self.dialog = None
        self.opened_dialogs = []

    def update(self) -> None:
        pass

    def open(self, dialog) -> None:
        self.dialog = dialog
        self.opened_dialogs.append(dialog)
        dialog.open = True

    def launch_url(self, _url: str) -> None:
        pass


def _database(path: Path, value: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence VALUES (?)", (value,))


def _fixture(tmp_path: Path, *, outcome: str = "COMPLETED", rollback: str = "NOT_REQUIRED") -> dict[str, object]:
    run_root = tmp_path / "runs"
    run_dir = run_root / RUN_ID
    backup_root = tmp_path / "backups"
    backup_dir = backup_root / RUN_ID
    live_dir = tmp_path / "live"
    run_dir.mkdir(parents=True)
    live_paths: dict[str, Path] = {}
    backups = {}
    for role in ("provider", "canonical", "analysis"):
        live = live_dir / f"{role}.db"
        backup = backup_dir / f"{role}.db"
        _database(live, f"live-{role}")
        _database(backup, f"backup-{role}")
        live_paths[role] = live
        backups[role] = {
            "source": str(live),
            "backup": str(backup),
            "verification": {
                "sha256": sha256_file(backup),
                "size": backup.stat().st_size,
                "quick_check": "ok",
                "foreign_key_check": [],
            },
        }
    result = {
        "run_id": RUN_ID,
        "operation_type": "ADD_TICKERS",
        "mode": "PRODUCTION_APPLY",
        "outcome": outcome,
        "completed_at_utc": "2026-09-22T15:01:00Z",
        "rollback": {"status": rollback},
        "atomic_replacement": {"status": "REPLACED"},
        "postflight": {"quick_check": "ok"},
        "backups": backups,
    }
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir / "operation_report.md").write_text("report", encoding="utf-8")
    (run_dir / "progress_status.json").write_text(
        json.dumps({
            "current_stage_id": "COMPLETED",
            "current_stage_number": 9,
            "total_declared_stages": 9,
            "stage_state": "COMPLETED",
            "message": "Done",
        }),
        encoding="utf-8",
    )
    return {
        "run_root": run_root,
        "run_dir": run_dir,
        "backup_root": backup_root,
        "backup_dir": backup_dir,
        "live_paths": live_paths,
        "journal_path": tmp_path / "journal.json",
        "result": result,
    }


def _inspect(fixture: dict[str, object]) -> dict[str, object]:
    return inspect_cleanup_eligibility(
        RUN_ID,
        run_root=fixture["run_root"],
        backup_root=fixture["backup_root"],
        journal_path=fixture["journal_path"],
        live_paths=fixture["live_paths"],
    )


def _cleanup(fixture: dict[str, object]) -> dict[str, object]:
    return accept_run_and_cleanup_backups(
        RUN_ID,
        run_root=fixture["run_root"],
        backup_root=fixture["backup_root"],
        journal_path=fixture["journal_path"],
        live_paths=fixture["live_paths"],
        lock_factory=nullcontext,
    )


def test_completed_production_run_is_eligible(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    eligibility = _inspect(fixture)
    assert eligibility["status"] == "ELIGIBLE"
    assert eligibility["backup_count"] == 3
    assert eligibility["bytes_freed"] > 0


@pytest.mark.parametrize(
    ("outcome", "rollback", "reason"),
    [
        ("FAILED", "NOT_REQUIRED", "terminal COMPLETED"),
        ("COMPLETED", "COMPLETED", "Rollback was required"),
        ("ROLLED_BACK", "COMPLETED", "terminal COMPLETED"),
    ],
)
def test_failed_or_rollback_run_is_not_eligible(
    tmp_path: Path, outcome: str, rollback: str, reason: str
) -> None:
    fixture = _fixture(tmp_path, outcome=outcome, rollback=rollback)
    eligibility = _inspect(fixture)
    assert eligibility["eligible"] is False
    assert reason in eligibility["reason"]


def test_nonterminal_journal_blocks_cleanup(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["journal_path"].write_text(
        json.dumps({"journal_format_version": 1, "state": "PUBLISHING"}),
        encoding="utf-8",
    )
    assert _inspect(fixture)["reason"] == "Recovery journal still active"
    with pytest.raises(RunAcceptanceCleanupError, match="Recovery journal still active"):
        _cleanup(fixture)


def test_hash_mismatch_blocks_all_deletion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    target = fixture["backup_dir"] / "provider.db"
    with sqlite3.connect(target) as connection:
        connection.execute("INSERT INTO evidence VALUES ('changed')")
    with pytest.raises(RunAcceptanceCleanupError, match="HASH_MISMATCH"):
        _cleanup(fixture)
    assert all((fixture["backup_dir"] / f"{role}.db").exists() for role in ("provider", "canonical", "analysis"))


def test_live_integrity_failure_blocks_all_deletion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["live_paths"]["analysis"].write_text("not sqlite", encoding="utf-8")
    with pytest.raises(RunAcceptanceCleanupError, match="LIVE_DATABASE"):
        _cleanup(fixture)
    assert all((fixture["backup_dir"] / f"{role}.db").exists() for role in ("provider", "canonical", "analysis"))


def test_cleanup_deletes_only_selected_backups_and_preserves_evidence(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    unrelated = fixture["backup_root"] / "another_run" / "analysis.db"
    _database(unrelated)
    live_before = {
        role: (path.stat().st_size, path.stat().st_mtime_ns)
        for role, path in fixture["live_paths"].items()
    }

    result = _cleanup(fixture)

    assert result["cleanup_outcome"] == "COMPLETED"
    assert result["bytes_freed"] > 0
    assert len(result["files_deleted"]) == 3
    assert not fixture["backup_dir"].exists()
    assert unrelated.exists()
    assert (fixture["run_dir"] / "operation_report.md").exists()
    assert (fixture["run_dir"] / "backup_cleanup.json").exists()
    assert live_before == {
        role: (path.stat().st_size, path.stat().st_mtime_ns)
        for role, path in fixture["live_paths"].items()
    }


def test_repeat_cleanup_is_idempotent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    first = _cleanup(fixture)
    second = _cleanup(fixture)
    assert first["cleanup_outcome"] == "COMPLETED"
    assert second["status"] == "ALREADY_CLEANED"
    assert _inspect(fixture)["status"] == "ALREADY_CLEANED"


def test_canonical_only_cik_backup_shape_is_supported(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    result = fixture["result"]
    canonical = result.pop("backups")["canonical"]
    result.pop("postflight")
    result.pop("atomic_replacement")
    result["operation_type"] = "SYNCHRONIZE_PROVIDER_CIK"
    result["backup"] = {
        "path": canonical["backup"],
        "verification": canonical["verification"],
    }
    result["after_audit"] = {"status": "ok"}
    result["validation"] = {
        "published_binding_matches_candidate": True,
        "non_target_canonical_unchanged": True,
        "provider_unchanged": True,
        "analysis_unchanged": True,
    }
    (fixture["backup_dir"] / "provider.db").unlink()
    (fixture["backup_dir"] / "analysis.db").unlink()
    (fixture["run_dir"] / "result.json").write_text(json.dumps(result), encoding="utf-8")

    assert _inspect(fixture)["status"] == "ELIGIBLE"
    cleaned = _cleanup(fixture)
    assert cleaned["cleanup_outcome"] == "COMPLETED"
    assert len(cleaned["files_deleted"]) == 1
    assert not fixture["backup_dir"].exists()


def test_partially_missing_backup_without_evidence_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    (fixture["backup_dir"] / "canonical.db").unlink()
    assert _inspect(fixture)["status"] == "NOT_ELIGIBLE"
    with pytest.raises(RunAcceptanceCleanupError, match="missing canonical"):
        _cleanup(fixture)
    assert not (fixture["run_dir"] / "backup_cleanup.json").exists()


def test_ui_shows_action_only_for_eligible_run_and_cleaned_state_afterward(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    state = {"cleaned": False}

    def inspect(_run_id: str) -> dict[str, object]:
        if state["cleaned"]:
            return {"eligible": False, "status": "ALREADY_CLEANED", "reason": "Accepted / backups cleaned"}
        return {"eligible": True, "status": "ELIGIBLE", "backup_count": 3, "bytes_freed": 3 * 1024**3}

    def cleanup(_run_id: str) -> dict[str, object]:
        state["cleaned"] = True
        return {"status": "COMPLETED", "cleanup_outcome": "COMPLETED", "bytes_freed": 3 * 1024**3}

    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=inspect,
        cleanup_apply=cleanup,
    )
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)
    info_button = controls.history_column.controls[0].controls[7]
    info_button.on_click(None)
    assert controls.cleanup_button.visible is True
    assert "Production data is not changed" in controls.cleanup_status_field.value

    controls.cleanup_button.on_click(None)
    page.dialog.actions[1].on_click(None)
    assert controls.cleanup_button.visible is False
    assert controls.cleanup_status_field.value == "Accepted / backups cleaned"


def test_history_listing_does_not_inspect_or_hash_backups(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls = []
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda run_id: calls.append(run_id) or {},
    )
    assert service.history_entries(limit=8)
    assert calls == []
