from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.generations import (
    LEGACY_GENERATION_ID,
    ROLE_FILENAMES,
    FundamentalsGenerationError,
    activate_generation,
    active_manifest_path,
    generation_manifest,
    generations_root,
    migrate_flat_layout,
    resolve_active_generation,
    prepare_generation_from_candidates,
)
from rawcandle.fundamentals.admin.publication_journal import (
    PUBLICATION_ROLES,
    PublicationRecoveredRetryRequired,
    activate_prepared_generation,
    guard_production_writes,
    prepare_journal,
    recover_if_required,
    sqlite_verification,
    update_journal,
)


def _database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO generation VALUES(?)", (value,))


def _flat_fixture(root: Path, value: str = "old") -> None:
    for filename in ROLE_FILENAMES.values():
        _database(root / "data" / filename, value)


def _value(path: Path) -> str:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        return str(connection.execute("SELECT value FROM generation").fetchone()[0])


def test_missing_pointer_resolves_one_pinned_legacy_generation(tmp_path: Path) -> None:
    _flat_fixture(tmp_path)
    binding = resolve_active_generation(tmp_path)
    assert binding.generation_id == LEGACY_GENERATION_ID
    assert binding.layout == "LEGACY_FLAT"
    assert {_value(path) for path in binding.role_paths().values()} == {"old"}
    assert not active_manifest_path(tmp_path).exists()


@pytest.mark.parametrize("generation_id", ("../escape", "..", "bad/name", "bad\\name"))
def test_migration_rejects_unsafe_generation_id(
    tmp_path: Path, generation_id: str,
) -> None:
    _flat_fixture(tmp_path)

    with pytest.raises(FundamentalsGenerationError, match="GENERATION_ID_INVALID"):
        migrate_flat_layout(project_root=tmp_path, generation_id=generation_id)

    assert not generations_root(tmp_path).exists()


def test_explicit_migration_is_hash_preserving_idempotent_and_keeps_flat_layout(
    tmp_path: Path,
) -> None:
    _flat_fixture(tmp_path)
    before = {
        role: (tmp_path / "data" / filename).read_bytes()
        for role, filename in ROLE_FILENAMES.items()
    }

    result = migrate_flat_layout(project_root=tmp_path, generation_id="generation-1")
    repeat = migrate_flat_layout(project_root=tmp_path, generation_id="ignored")

    assert result["status"] == "MIGRATED_AND_ACTIVATED"
    assert repeat["status"] == "ALREADY_MIGRATED"
    active = resolve_active_generation(tmp_path, require_generation=True)
    assert active.generation_id == "generation-1"
    assert {_value(path) for path in active.role_paths().values()} == {"old"}
    assert all(
        (tmp_path / "data" / filename).read_bytes() == before[role]
        for role, filename in ROLE_FILENAMES.items()
    )


def test_reader_binding_remains_old_across_atomic_activation(tmp_path: Path) -> None:
    _flat_fixture(tmp_path)
    migrate_flat_layout(project_root=tmp_path, generation_id="old")
    pinned_old = resolve_active_generation(tmp_path, require_generation=True)
    new_dir = generations_root(tmp_path) / "new"
    verification = {}
    for role, filename in ROLE_FILENAMES.items():
        path = new_dir / filename
        _database(path, "new")
        import hashlib
        verification[role] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = generation_manifest(
        "new", role_verification=verification, source="TEST",
    )

    activate_generation(
        manifest, project_root=tmp_path,
        expected_active_generation_id="old",
    )
    pinned_new = resolve_active_generation(tmp_path, require_generation=True)

    assert {_value(path) for path in pinned_old.role_paths().values()} == {"old"}
    assert {_value(path) for path in pinned_new.role_paths().values()} == {"new"}
    assert pinned_old.generation_id == "old"
    assert pinned_new.generation_id == "new"


def test_migration_resumes_after_generation_rename_before_pointer_activation(
    tmp_path: Path,
) -> None:
    _flat_fixture(tmp_path)
    final = generations_root(tmp_path) / "resumable"
    final.mkdir(parents=True)
    verification = {}
    import hashlib
    for role, filename in ROLE_FILENAMES.items():
        source = tmp_path / "data" / filename
        destination = final / filename
        shutil.copy2(source, destination)
        verification[role] = {
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()
        }
    manifest = generation_manifest(
        "resumable", role_verification=verification,
        source="EXPLICIT_FLAT_LAYOUT_MIGRATION",
    )
    (final / "generation_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    result = migrate_flat_layout(project_root=tmp_path, generation_id="resumable")

    assert result["status"] == "RESUMED_AND_ACTIVATED"
    assert resolve_active_generation(tmp_path).generation_id == "resumable"


def test_activation_compare_and_swap_rejects_pointer_drift(tmp_path: Path) -> None:
    _flat_fixture(tmp_path)
    migrate_flat_layout(project_root=tmp_path, generation_id="old")
    with pytest.raises(FundamentalsGenerationError, match="ACTIVE_GENERATION_DRIFT"):
        activate_generation(
            json.loads(active_manifest_path(tmp_path).read_text(encoding="utf-8")),
            project_root=tmp_path,
            expected_active_generation_id="different",
        )


def _publication_fixture(tmp_path: Path) -> tuple[Path, dict, dict]:
    _flat_fixture(tmp_path)
    migrate_flat_layout(project_root=tmp_path, generation_id="old")
    old = resolve_active_generation(tmp_path, require_generation=True)
    lane = tmp_path / "temp" / "publication-run"
    backups = tmp_path / "backups" / "publication-run"
    lane.mkdir(parents=True)
    backups.mkdir(parents=True)
    roles = {}
    candidates = {}
    for role, filename in ROLE_FILENAMES.items():
        candidate = lane / f"{role}_candidate.db"
        backup = backups / f"{role}.db"
        _database(candidate, "new")
        shutil.copy2(old.role_paths()[role], backup)
        roles[role] = {
            "production_path": str(old.role_paths()[role]),
            "old_production_fingerprint": sqlite_verification(backup)["sha256"],
            "backup_path": str(backup),
            "verified_backup_fingerprint": sqlite_verification(backup)["sha256"],
            "candidate_path": str(candidate),
            "candidate_fingerprint": sqlite_verification(candidate)["sha256"],
            "replacement_state": "NOT_STARTED",
        }
        candidates[role] = candidate
    journal_path = tmp_path / "data" / "publication_journal.json"
    journal = prepare_journal(
        path=journal_path,
        operation_type="REFRESH_FUNDAMENTALS",
        run_id="publication-run",
        preview_run_id="preview",
        test_run_id="test",
        refresh_set_fingerprint="f" * 64,
        old_source_watermark="old",
        new_source_watermark="new",
        source_schema_fingerprint="schema",
        roles=roles,
        publication_mode="GENERATION_POINTER",
        old_generation=old.evidence() | {"manifest": dict(old.manifest)},
        new_generation_id="new",
        active_generation_manifest_path=active_manifest_path(tmp_path),
    )
    prepared = prepare_generation_from_candidates(
        candidates, generation_id="new", project_root=tmp_path, source="TEST",
    )
    journal = update_journal(
        journal_path, journal,
        generation_activation_state="READY",
        new_generation_manifest=prepared["manifest"],
        new_generation_dir=prepared["generation_dir"],
    )
    return journal_path, journal, prepared


def test_pre_activation_recovery_leaves_old_active_and_requires_retry(
    tmp_path: Path,
) -> None:
    journal_path, _journal, _prepared = _publication_fixture(tmp_path)

    with pytest.raises(PublicationRecoveredRetryRequired):
        guard_production_writes(journal_path)

    assert resolve_active_generation(tmp_path).generation_id == "old"
    assert not (generations_root(tmp_path) / "new").exists()


@pytest.mark.parametrize("pointer_switched_without_journal_update", [False, True])
def test_post_activation_or_activation_boundary_recovery_reactivates_old(
    tmp_path: Path, pointer_switched_without_journal_update: bool,
) -> None:
    journal_path, journal, prepared = _publication_fixture(tmp_path)
    if pointer_switched_without_journal_update:
        activate_generation(
            prepared["manifest"], project_root=tmp_path,
            expected_active_generation_id="old",
        )
    else:
        activate_prepared_generation(
            journal, new_manifest=prepared["manifest"], journal_path=journal_path,
        )
    assert resolve_active_generation(tmp_path).generation_id == "new"

    recovery = recover_if_required(journal_path)

    assert recovery["status"] == "RECOVERED"
    assert resolve_active_generation(tmp_path).generation_id == "old"
    assert not (generations_root(tmp_path) / "new").exists()


def test_completed_generation_remains_active(tmp_path: Path) -> None:
    journal_path, journal, prepared = _publication_fixture(tmp_path)
    journal = activate_prepared_generation(
        journal, new_manifest=prepared["manifest"], journal_path=journal_path,
    )
    update_journal(
        journal_path, journal, state="COMPLETED",
        postflight_state="PASSED", current_publication_step="COMPLETED",
    )

    recovery = recover_if_required(journal_path)

    assert recovery == {"status": "COMPLETED", "recovered": False}
    assert resolve_active_generation(tmp_path).generation_id == "new"
    assert {_value(path) for path in resolve_active_generation(tmp_path).role_paths().values()} == {"new"}
