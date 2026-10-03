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
from rawcandle.fundamentals.admin.ui_service import (
    AdminOperationCapability,
    AdminUIHistoryEntry,
    FundamentalsAdminUIService,
)


RUN_ID = "20250922T150000Z_add_tickers_abc123_production_deadbeef"


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


def _make_generation_publication(fixture: dict[str, object]) -> dict[str, Path]:
    generation_root = fixture["run_root"].parent / "generations"
    migration_dir = generation_root / "migration_20261003T103216Z"
    active_dir = generation_root / f"refresh_{RUN_ID}"
    migration_paths: dict[str, Path] = {}
    active_paths: dict[str, Path] = {}
    for role in ("provider", "canonical", "analysis"):
        migration_path = migration_dir / f"{role}.db"
        active_path = active_dir / f"{role}.db"
        _database(migration_path, f"migration-{role}")
        _database(active_path, f"active-{role}")
        migration_paths[role] = migration_path
        active_paths[role] = active_path
        fixture["result"]["backups"][role]["source"] = str(migration_path)
    fixture["live_paths"] = active_paths
    manifest = fixture["run_root"].parent / "fundamentals_active_generation.json"
    manifest.write_text(json.dumps({"generation_id": f"refresh_{RUN_ID}"}), encoding="utf-8")
    fixture["result"]["journal"] = {
        "state": "COMPLETED",
        "current_publication_step": "COMPLETED",
        "postflight_state": "PASSED",
        "rollback_recovery_state": "NOT_REQUIRED",
        "generation_activation_state": "ACTIVATED_AND_VERIFIED",
        "production_run_id": RUN_ID,
        "publication_mode": "GENERATION_POINTER",
        "new_generation_id": f"refresh_{RUN_ID}",
        "active_generation_manifest_path": str(manifest),
        "old_generation": {
            "generation_id": "migration_20261003T103216Z",
            "generation_dir": str(migration_dir),
            "layout": "GENERATION_DIRECTORY",
            "roles": {role: str(path) for role, path in migration_paths.items()},
        },
    }
    rollback_backups = [
        {
            "role": role,
            "path": record["backup"],
            "size_bytes": Path(record["backup"]).stat().st_size,
        }
        for role, record in fixture["result"]["backups"].items()
    ]
    fixture["result"]["terminal_cleanup"] = {
        "status": "COMPLETED",
        "cleanup_verification": {"status": "PASSED"},
        "operator_acceptance_required_for_rollback_backup_deletion": "YES",
        "intentionally_retained": {
            "rollback_backup_count": 3,
            "rollback_backup_bytes": sum(item["size_bytes"] for item in rollback_backups),
            "rollback_backups": rollback_backups,
        },
    }
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )
    return {
        "manifest": manifest,
        "migration_dir": migration_dir,
        "active_dir": active_dir,
    }


def test_historical_completed_production_run_is_eligible(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    eligibility = _inspect(fixture)
    assert eligibility["status"] == "ELIGIBLE"
    assert eligibility["backup_count"] == 3
    assert eligibility["bytes_freed"] > 0


def test_generation_production_run_is_eligible_and_ui_shows_cleanup_action(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _make_generation_publication(fixture)
    eligibility = _inspect(fixture)
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda _run_id: _inspect(fixture),
    )
    page = _Page()

    controls = build_fundamentals_admin_page(page=page, service=service)

    assert eligibility["status"] == "ELIGIBLE"
    assert eligibility["backup_count"] == 3
    assert eligibility["bytes_freed"] == sum(
        path.stat().st_size for path in fixture["backup_dir"].iterdir()
    )
    assert controls.history_column.controls[0].controls[-1].tooltip == (
        "Accept run and cleanup backups"
    )
    controls.history_column.controls[0].controls[-1].on_click(None)
    assert "3 verified rollback backup file(s)" in page.dialog.content.value
    assert f"{eligibility['bytes_freed'] / (1024 ** 3):.3f} GiB" in page.dialog.content.value


def test_generation_cleanup_deletes_only_run_backups_and_preserves_generations(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    protected = _make_generation_publication(fixture)

    result = _cleanup(fixture)

    assert result["cleanup_outcome"] == "COMPLETED"
    assert not fixture["backup_dir"].exists()
    assert protected["manifest"].is_file()
    assert protected["active_dir"].is_dir()
    assert protected["migration_dir"].is_dir()
    assert all(path.is_file() for path in fixture["live_paths"].values())
    assert all(
        (protected["migration_dir"] / f"{role}.db").is_file()
        for role in ("provider", "canonical", "analysis")
    )


def test_generation_cleanup_fails_closed_on_source_or_terminal_evidence_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    protected = _make_generation_publication(fixture)
    fixture["result"]["backups"]["provider"]["source"] = str(
        protected["active_dir"] / "provider.db"
    )
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )

    eligibility = _inspect(fixture)

    assert eligibility["eligible"] is False
    assert "source" in eligibility["reason"].lower()
    assert all(path.is_file() for path in fixture["backup_dir"].iterdir())
    assert protected["manifest"].is_file()


def test_generation_cleanup_requires_terminal_generation_journal(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _make_generation_publication(fixture)
    fixture["result"]["journal"]["state"] = "PUBLISHING"
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )

    eligibility = _inspect(fixture)

    assert eligibility["eligible"] is False
    assert eligibility["reason"] == "Generation publication evidence is incomplete"
    assert all(path.is_file() for path in fixture["backup_dir"].iterdir())


def test_historical_generation_run_without_terminal_cleanup_uses_existing_fallback(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _make_generation_publication(fixture)
    fixture["result"].pop("terminal_cleanup")
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )

    eligibility = _inspect(fixture)

    assert eligibility["status"] == "ELIGIBLE"
    assert eligibility["backup_count"] == 3


@pytest.mark.parametrize("protected_name", ("active_generation", "active_manifest", "migration_generation"))
def test_generation_artifacts_cannot_be_declared_as_run_owned_backups(
    tmp_path: Path,
    protected_name: str,
) -> None:
    fixture = _fixture(tmp_path)
    protected = _make_generation_publication(fixture)
    targets = {
        "active_generation": protected["active_dir"] / "provider.db",
        "active_manifest": protected["manifest"],
        "migration_generation": protected["migration_dir"] / "provider.db",
    }
    target = targets[protected_name]
    fixture["result"]["backups"]["provider"]["backup"] = str(target)
    retained = fixture["result"]["terminal_cleanup"]["intentionally_retained"]
    next(
        item for item in retained["rollback_backups"] if item["role"] == "provider"
    )["path"] = str(target)
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )

    eligibility = _inspect(fixture)

    assert eligibility["eligible"] is False
    assert "ownership" in eligibility["reason"].lower()
    assert target.exists()
    assert protected["manifest"].is_file()
    assert protected["active_dir"].is_dir()
    assert protected["migration_dir"].is_dir()


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


@pytest.mark.parametrize("state", ("RECOVERED", "ROLLED_BACK", "RECOVERY_FAILED"))
def test_recovery_or_rollback_journal_blocks_cleanup(
    tmp_path: Path,
    state: str,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["journal_path"].write_text(
        json.dumps({"journal_format_version": 1, "state": state}),
        encoding="utf-8",
    )

    eligibility = _inspect(fixture)

    assert eligibility["eligible"] is False
    assert "journal" in eligibility["reason"].lower()
    assert all(path.is_file() for path in fixture["backup_dir"].iterdir())


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


def test_historical_run_with_incomplete_hash_evidence_is_not_eligible(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["result"]["backups"]["provider"].pop("verification")
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )

    eligibility = _inspect(fixture)

    assert eligibility["status"] == "NOT_ELIGIBLE"
    assert eligibility["reason"] == "Backup hashes or fingerprints are missing"
    assert all(
        (fixture["backup_dir"] / f"{role}.db").exists()
        for role in ("provider", "canonical", "analysis")
    )


def test_ui_shows_action_only_for_eligible_run_and_cleaned_state_afterward(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    state = {"cleaned": False}
    cleanup_calls: list[str] = []

    def inspect(_run_id: str) -> dict[str, object]:
        if state["cleaned"]:
            return {"eligible": False, "status": "ALREADY_CLEANED", "reason": "Accepted / backups cleaned"}
        return {"eligible": True, "status": "ELIGIBLE", "backup_count": 3, "bytes_freed": 3 * 1024**3}

    def cleanup(_run_id: str) -> dict[str, object]:
        cleanup_calls.append(_run_id)
        state["cleaned"] = True
        return {
            "status": "COMPLETED",
            "cleanup_outcome": "COMPLETED",
            "bytes_freed": 3 * 1024**3,
            "files_deleted": ["provider.db", "canonical.db", "analysis.db"],
        }

    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=inspect,
        cleanup_apply=cleanup,
    )
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)
    row = controls.history_column.controls[0]
    row_cleanup = row.controls[-1]
    assert row_cleanup.tooltip == "Accept run and cleanup backups"

    row_cleanup.on_click(None)
    assert RUN_ID in page.dialog.content.value
    assert "3 verified rollback backup file(s)" in page.dialog.content.value
    assert "3.000 GiB" in page.dialog.content.value
    assert "Live Production databases will not be modified" in page.dialog.content.value
    page.dialog.actions[1].on_click(None)
    assert cleanup_calls == [RUN_ID]
    assert controls.cleanup_status_field.value == "Accepted / backups cleaned (3.000 GiB freed)"
    cleaned_action = controls.history_column.controls[0].controls[-1]
    assert cleaned_action.tooltip == "Backups cleaned"
    assert cleaned_action.disabled is True


def test_ui_historical_already_cleaned_row_shows_terminal_indicator(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda _run_id: {
            "eligible": False,
            "status": "ALREADY_CLEANED",
            "reason": "Accepted / backups cleaned",
        },
    )

    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    action = controls.history_column.controls[0].controls[-1]

    assert action.tooltip == "Backups cleaned"
    assert action.disabled is True


@pytest.mark.parametrize(
    ("mode", "outcome"),
    [
        ("PREVIEW", "COMPLETED"),
        ("COPY_ONLY_APPLY", "COMPLETED"),
        ("PRODUCTION_APPLY", "FAILED"),
    ],
)
def test_ui_noneligible_stage_does_not_inspect_or_show_cleanup_action(
    tmp_path: Path, mode: str, outcome: str
) -> None:
    fixture = _fixture(tmp_path)
    fixture["result"]["mode"] = mode
    fixture["result"]["outcome"] = outcome
    (fixture["run_dir"] / "result.json").write_text(
        json.dumps(fixture["result"]), encoding="utf-8"
    )
    calls: list[str] = []
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda run_id: calls.append(run_id) or {"eligible": True},
    )

    controls = build_fundamentals_admin_page(page=_Page(), service=service)
    tooltips = [getattr(control, "tooltip", None) for control in controls.history_column.controls[0].controls]

    assert calls == []
    assert "Accept run and cleanup backups" not in tooltips
    assert "Backups cleaned" not in tooltips


def test_ui_already_cleaned_apply_result_is_success(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda _run_id: {
            "eligible": True, "status": "ELIGIBLE", "backup_count": 3, "bytes_freed": 30,
        },
        cleanup_apply=lambda _run_id: {
            "status": "ALREADY_CLEANED", "cleanup_outcome": "COMPLETED", "bytes_freed": 30,
        },
    )
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)

    controls.history_column.controls[0].controls[-1].on_click(None)
    page.dialog.actions[1].on_click(None)

    assert controls.cleanup_status_field.value == "Accepted / backups cleaned"
    assert controls.history_column.controls[0].controls[-1].tooltip == "Backups cleaned"


def test_ui_revalidation_failure_shows_reason_without_cleanup(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inspections = iter([
        {"eligible": True, "status": "ELIGIBLE", "backup_count": 3, "bytes_freed": 30},
        {
            "eligible": False,
            "status": "NOT_ELIGIBLE",
            "reason": "Backup ownership cannot be proven",
        },
    ])
    cleanup_calls: list[str] = []
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda _run_id: next(inspections),
        cleanup_apply=lambda run_id: cleanup_calls.append(run_id) or {},
    )
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)

    controls.history_column.controls[0].controls[-1].on_click(None)

    assert cleanup_calls == []
    assert page.dialog is None
    assert controls.cleanup_status_field.value == "Backup ownership cannot be proven"


def test_successful_cleanup_updates_only_selected_history_row() -> None:
    run_ids = ("historical-production-a", "historical-production-b")

    class Service:
        def __init__(self) -> None:
            self.cleaned: set[str] = set()

        def capabilities(self):
            return (AdminOperationCapability("ADD_TICKERS", True, True, True),)

        def history_entries(self, *, limit, include_technical=False):
            return [
                AdminUIHistoryEntry(
                    run_id=run_id,
                    operation_type="ADD_TICKERS",
                    outcome="COMPLETED",
                    status="completed",
                    mode="PRODUCTION_APPLY",
                    completed_at_utc="2025-09-22T15:01:00Z",
                    report_available=True,
                )
                for run_id in run_ids[:limit]
            ]

        def cleanup_eligibility(self, run_id):
            if run_id in self.cleaned:
                return {"eligible": False, "status": "ALREADY_CLEANED"}
            return {
                "eligible": True,
                "status": "ELIGIBLE",
                "backup_count": 3,
                "bytes_freed": 30,
            }

        def accept_run_and_cleanup_backups(self, run_id):
            self.cleaned.add(run_id)
            return {
                "status": "COMPLETED",
                "cleanup_outcome": "COMPLETED",
                "bytes_freed": 30,
                "files_deleted": ["provider.db", "canonical.db", "analysis.db"],
            }

    service = Service()
    page = _Page()
    controls = build_fundamentals_admin_page(page=page, service=service)

    controls.history_column.controls[0].controls[-1].on_click(None)
    page.dialog.actions[1].on_click(None)

    first_action = controls.history_column.controls[0].controls[-1]
    second_action = controls.history_column.controls[1].controls[-1]
    assert first_action.tooltip == "Backups cleaned"
    assert first_action.disabled is True
    assert second_action.tooltip == "Accept run and cleanup backups"
    assert second_action.disabled is False
    assert service.cleaned == {run_ids[0]}


def test_history_listing_does_not_inspect_or_hash_backups(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    calls = []
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda run_id: calls.append(run_id) or {},
    )
    assert service.history_entries(limit=8)
    assert calls == []


def test_history_row_eligibility_inspection_does_not_hash_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.run_acceptance_cleanup.sha256_file",
        lambda _path: (_ for _ in ()).throw(AssertionError("eligibility must not hash backups")),
    )
    service = FundamentalsAdminUIService(
        run_root=fixture["run_root"],
        cleanup_inspect=lambda run_id: inspect_cleanup_eligibility(
            run_id,
            run_root=fixture["run_root"],
            backup_root=fixture["backup_root"],
            journal_path=fixture["journal_path"],
            live_paths=fixture["live_paths"],
        ),
    )

    controls = build_fundamentals_admin_page(page=_Page(), service=service)

    assert controls.history_column.controls[0].controls[-1].tooltip == (
        "Accept run and cleanup backups"
    )
