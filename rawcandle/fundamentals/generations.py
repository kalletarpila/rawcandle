"""Atomic Fundamentals generation resolution, activation, and flat-layout migration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORMAT_VERSION = 1
LEGACY_GENERATION_ID = "LEGACY_FLAT"
ROLE_FILENAMES = {
    "provider": "fundamentals_provider.db",
    "canonical": "fundamentals_v4.db",
    "analysis": "fundamentals_analysis.db",
}
GENERATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class FundamentalsGenerationError(RuntimeError):
    pass


def _validate_generation_id(generation_id: str) -> str:
    if (
        generation_id == LEGACY_GENERATION_ID
        or not GENERATION_ID_RE.fullmatch(generation_id)
    ):
        raise FundamentalsGenerationError("FUNDAMENTALS_GENERATION_ID_INVALID")
    return generation_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sqlite_check(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FundamentalsGenerationError(f"FUNDAMENTALS_GENERATION_ROLE_INVALID:{path}")
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    if quick_check != "ok":
        raise FundamentalsGenerationError(
            f"FUNDAMENTALS_GENERATION_QUICK_CHECK_FAILED:{path}"
        )
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "quick_check": quick_check,
    }


def generations_root(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root.resolve() / "data" / "fundamentals_generations"


def active_manifest_path(project_root: Path = PROJECT_ROOT) -> Path:
    return project_root.resolve() / "data" / "fundamentals_active_generation.json"


def legacy_role_paths(project_root: Path = PROJECT_ROOT) -> dict[str, Path]:
    data = project_root.resolve() / "data"
    return {role: data / filename for role, filename in ROLE_FILENAMES.items()}


def resolved_production_paths(project_root: Path = PROJECT_ROOT) -> dict[str, Path]:
    root = project_root.resolve()
    roles = resolve_active_generation(root).role_paths()
    return {
        **roles,
        "market": root / "data" / "osakedata.db",
        "taxonomy": root / "data" / "analysis.db",
    }


def resolve_requested_role_path(
    role: str, requested: str | Path | None = None,
    *, project_root: Path = PROJECT_ROOT,
) -> Path:
    if role not in ROLE_FILENAMES:
        raise ValueError(f"FUNDAMENTALS_GENERATION_ROLE_INVALID:{role}")
    active = resolve_active_generation(project_root).role_paths()[role]
    if requested is None:
        return active
    requested_path = Path(requested)
    legacy = legacy_role_paths(project_root)[role]
    if requested_path.resolve() == legacy.resolve():
        return active
    return requested_path


@dataclass(frozen=True)
class GenerationBinding:
    generation_id: str
    layout: str
    roles: Mapping[str, Path]
    manifest_path: Path
    generation_dir: Path
    manifest: Mapping[str, Any]

    def role_paths(self) -> dict[str, Path]:
        return {role: Path(self.roles[role]) for role in ROLE_FILENAMES}

    def evidence(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "layout": self.layout,
            "manifest_path": str(self.manifest_path.resolve()),
            "generation_dir": str(self.generation_dir.resolve()),
            "roles": {
                role: str(path.resolve()) for role, path in self.role_paths().items()
            },
        }


def _legacy_binding(project_root: Path) -> GenerationBinding:
    root = project_root.resolve()
    roles = legacy_role_paths(root)
    return GenerationBinding(
        generation_id=LEGACY_GENERATION_ID,
        layout="LEGACY_FLAT",
        roles=roles,
        manifest_path=active_manifest_path(root),
        generation_dir=root / "data",
        manifest={
            "format_version": FORMAT_VERSION,
            "generation_id": LEGACY_GENERATION_ID,
            "layout": "LEGACY_FLAT",
            "roles": {role: path.name for role, path in roles.items()},
        },
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FundamentalsGenerationError("FUNDAMENTALS_ACTIVE_MANIFEST_PATH_INVALID")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FundamentalsGenerationError(
            "FUNDAMENTALS_ACTIVE_MANIFEST_UNREADABLE"
        ) from exc
    if not isinstance(value, dict) or value.get("format_version") != FORMAT_VERSION:
        raise FundamentalsGenerationError("FUNDAMENTALS_ACTIVE_MANIFEST_FORMAT_INVALID")
    return value


def resolve_active_generation(
    project_root: Path = PROJECT_ROOT, *, require_generation: bool = False,
) -> GenerationBinding:
    root = project_root.resolve()
    pointer = active_manifest_path(root)
    if not pointer.exists():
        if require_generation:
            raise FundamentalsGenerationError("FUNDAMENTALS_GENERATION_MIGRATION_REQUIRED")
        return _legacy_binding(root)
    manifest = _read_manifest(pointer)
    try:
        generation_id = _validate_generation_id(
            str(manifest.get("generation_id") or "")
        )
    except FundamentalsGenerationError as exc:
        raise FundamentalsGenerationError(
            "FUNDAMENTALS_ACTIVE_GENERATION_ID_INVALID"
        ) from exc
    generation_dir = generations_root(root) / generation_id
    if (
        generation_dir.is_symlink()
        or not generation_dir.is_dir()
        or generation_dir.parent.resolve() != generations_root(root).resolve()
    ):
        raise FundamentalsGenerationError("FUNDAMENTALS_ACTIVE_GENERATION_PATH_INVALID")
    role_names = manifest.get("roles")
    if not isinstance(role_names, Mapping) or set(role_names) != set(ROLE_FILENAMES):
        raise FundamentalsGenerationError("FUNDAMENTALS_ACTIVE_GENERATION_ROLES_INVALID")
    roles: dict[str, Path] = {}
    for role, expected_name in ROLE_FILENAMES.items():
        if role_names.get(role) != expected_name:
            raise FundamentalsGenerationError(
                f"FUNDAMENTALS_ACTIVE_GENERATION_ROLE_NAME_INVALID:{role}"
            )
        role_path = generation_dir / expected_name
        if role_path.is_symlink() or not role_path.is_file():
            raise FundamentalsGenerationError(
                f"FUNDAMENTALS_ACTIVE_GENERATION_ROLE_MISSING:{role}"
            )
        roles[role] = role_path
    return GenerationBinding(
        generation_id=generation_id,
        layout="GENERATION_DIRECTORY",
        roles=roles,
        manifest_path=pointer,
        generation_dir=generation_dir,
        manifest=manifest,
    )


def _atomic_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def generation_manifest(
    generation_id: str, *, role_verification: Mapping[str, Mapping[str, Any]],
    created_at_utc: str | None = None, source: str,
) -> dict[str, Any]:
    _validate_generation_id(generation_id)
    if set(role_verification) != set(ROLE_FILENAMES):
        raise ValueError("FUNDAMENTALS_GENERATION_ROLE_SET_INVALID")
    return {
        "format_version": FORMAT_VERSION,
        "generation_id": generation_id,
        "layout": "GENERATION_DIRECTORY",
        "created_at_utc": created_at_utc or _utc_now(),
        "source": source,
        "roles": dict(ROLE_FILENAMES),
        "role_verification": {
            role: dict(role_verification[role]) for role in ROLE_FILENAMES
        },
    }


def prepare_generation_from_candidates(
    candidates: Mapping[str, Path], *, generation_id: str,
    project_root: Path = PROJECT_ROOT, source: str,
) -> dict[str, Any]:
    if set(candidates) != set(ROLE_FILENAMES):
        raise ValueError("FUNDAMENTALS_GENERATION_CANDIDATE_ROLE_SET_INVALID")
    _validate_generation_id(generation_id)
    root = project_root.resolve()
    parent = generations_root(root)
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f".{generation_id}.preparing"
    final = parent / generation_id
    if temporary.exists() or final.exists():
        raise FundamentalsGenerationError("FUNDAMENTALS_GENERATION_TARGET_EXISTS")
    temporary.mkdir()
    try:
        verification: dict[str, dict[str, Any]] = {}
        for role, filename in ROLE_FILENAMES.items():
            candidate = Path(candidates[role])
            if candidate.is_symlink() or not candidate.is_file():
                raise FundamentalsGenerationError(
                    f"FUNDAMENTALS_GENERATION_CANDIDATE_INVALID:{role}"
                )
            destination = temporary / filename
            if candidate.stat().st_dev != temporary.stat().st_dev:
                raise FundamentalsGenerationError(
                    f"FUNDAMENTALS_GENERATION_CROSS_FILESYSTEM:{role}"
                )
            os.replace(candidate, destination)
            _fsync_file(destination)
            verification[role] = _sqlite_check(destination)
        manifest = generation_manifest(
            generation_id,
            role_verification=verification,
            source=source,
        )
        with (temporary / "generation_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(temporary)
        os.replace(temporary, final)
        _fsync_directory(parent)
        return {
            "manifest": manifest,
            "generation_dir": str(final.resolve()),
            "roles": {
                role: str((final / filename).resolve())
                for role, filename in ROLE_FILENAMES.items()
            },
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def activate_generation(
    manifest: Mapping[str, Any], *, project_root: Path = PROJECT_ROOT,
    expected_active_generation_id: str | None = None,
) -> GenerationBinding:
    root = project_root.resolve()
    current = resolve_active_generation(root)
    if (
        expected_active_generation_id is not None
        and current.generation_id != expected_active_generation_id
    ):
        raise FundamentalsGenerationError("FUNDAMENTALS_ACTIVE_GENERATION_DRIFT")
    generation_id = _validate_generation_id(
        str(manifest.get("generation_id") or "")
    )
    generation_dir = generations_root(root) / generation_id
    expected_roles = manifest.get("roles")
    if expected_roles != ROLE_FILENAMES or not generation_dir.is_dir():
        raise FundamentalsGenerationError("FUNDAMENTALS_GENERATION_ACTIVATION_INVALID")
    for role, filename in ROLE_FILENAMES.items():
        verification = _sqlite_check(generation_dir / filename)
        expected_sha = str(
            ((manifest.get("role_verification") or {}).get(role) or {}).get("sha256")
            or ""
        )
        if expected_sha and verification["sha256"] != expected_sha:
            raise FundamentalsGenerationError(
                f"FUNDAMENTALS_GENERATION_ACTIVATION_FINGERPRINT_MISMATCH:{role}"
            )
    _atomic_manifest(active_manifest_path(root), manifest)
    active = resolve_active_generation(root, require_generation=True)
    if active.generation_id != generation_id:
        raise FundamentalsGenerationError("FUNDAMENTALS_GENERATION_ACTIVATION_FAILED")
    return active


def migrate_flat_layout(
    *, project_root: Path = PROJECT_ROOT, generation_id: str,
) -> dict[str, Any]:
    _validate_generation_id(generation_id)
    root = project_root.resolve()
    active = resolve_active_generation(root)
    if active.layout == "GENERATION_DIRECTORY":
        return {
            "status": "ALREADY_MIGRATED",
            "active_generation": active.evidence(),
        }
    sources = legacy_role_paths(root)
    before = {role: _sqlite_check(path) for role, path in sources.items()}
    parent = generations_root(root)
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / generation_id
    temporary = parent / f".{generation_id}.migrating"
    if final.exists():
        manifest_path = final / "generation_manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise FundamentalsGenerationError("FUNDAMENTALS_MIGRATION_GENERATION_EXISTS")
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FundamentalsGenerationError(
                "FUNDAMENTALS_MIGRATION_GENERATION_MANIFEST_INVALID"
            ) from exc
        verification = {
            role: _sqlite_check(final / filename)
            for role, filename in ROLE_FILENAMES.items()
        }
        expected = existing_manifest.get("role_verification") or {}
        if any(
            verification[role]["sha256"]
            != str((expected.get(role) or {}).get("sha256") or "")
            or verification[role]["sha256"] != before[role]["sha256"]
            for role in ROLE_FILENAMES
        ):
            raise FundamentalsGenerationError(
                "FUNDAMENTALS_MIGRATION_GENERATION_RESUME_MISMATCH"
            )
        activated = activate_generation(
            existing_manifest,
            project_root=root,
            expected_active_generation_id=LEGACY_GENERATION_ID,
        )
        return {
            "status": "RESUMED_AND_ACTIVATED",
            "active_generation": activated.evidence(),
            "legacy_flat_files_retained": {
                role: str(path.resolve()) for role, path in sources.items()
            },
            "role_verification": verification,
        }
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        copied: dict[str, dict[str, Any]] = {}
        for role, filename in ROLE_FILENAMES.items():
            destination = temporary / filename
            shutil.copy2(sources[role], destination)
            _fsync_file(destination)
            copied[role] = _sqlite_check(destination)
            if copied[role]["sha256"] != before[role]["sha256"]:
                raise FundamentalsGenerationError(
                    f"FUNDAMENTALS_MIGRATION_COPY_MISMATCH:{role}"
                )
        after = {role: _sqlite_check(path) for role, path in sources.items()}
        if any(before[role]["sha256"] != after[role]["sha256"] for role in ROLE_FILENAMES):
            raise FundamentalsGenerationError("FUNDAMENTALS_MIGRATION_SOURCE_DRIFT")
        manifest = generation_manifest(
            generation_id,
            role_verification=copied,
            source="EXPLICIT_FLAT_LAYOUT_MIGRATION",
        )
        with (temporary / "generation_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(temporary)
        os.replace(temporary, final)
        _fsync_directory(parent)
        activated = activate_generation(
            manifest,
            project_root=root,
            expected_active_generation_id=LEGACY_GENERATION_ID,
        )
        return {
            "status": "MIGRATED_AND_ACTIVATED",
            "active_generation": activated.evidence(),
            "legacy_flat_files_retained": {
                role: str(path.resolve()) for role, path in sources.items()
            },
            "role_verification": copied,
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
