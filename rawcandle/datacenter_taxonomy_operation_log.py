from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY_OPERATION_ROOT = REPO_ROOT / "temp" / "datacenter_taxonomy_changes"
PRIMARY_LOG_NAME = "taxonomy_change.log"
OPERATION_MANIFEST_NAME = "operation.json"
ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
PACKAGE_MANIFEST_NAME = "package_manifest.json"
MAX_EVIDENCE_PACKAGE_BYTES = 50 * 1024 * 1024
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".wal", ".shm"}
EXCLUDED_NAME_PARTS = {"backup", "scheduler_config"}


@dataclass(frozen=True)
class TaxonomyOperation:
    operation_id: str
    deployment_id: str
    operation_type: str
    started_at_utc: str
    completed_at_utc: str | None
    status: str
    failed_phase: str | None
    resume_from_phase: str | None
    evidence_root: str
    primary_log_path: str
    artifact_manifest_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "deployment_id": self.deployment_id,
            "operation_type": self.operation_type,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "status": self.status,
            "failed_phase": self.failed_phase,
            "resume_from_phase": self.resume_from_phase,
            "evidence_root": self.evidence_root,
            "primary_log_path": self.primary_log_path,
            "artifact_manifest_path": self.artifact_manifest_path,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _approved_root(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else DEFAULT_TAXONOMY_OPERATION_ROOT
    resolved = base.resolve()
    temp_root = (REPO_ROOT / "temp").resolve()
    is_repo_temp = resolved == temp_root or temp_root in resolved.parents
    is_test_managed_temp = "temp" in resolved.parts and str(resolved).startswith("/tmp/")
    if not is_repo_temp and not is_test_managed_temp:
        raise ValueError("taxonomy operation evidence root must be under repository temp/")
    return resolved


def _deployment_dir(deployment_id: str | int, *, root: str | Path | None = None) -> Path:
    safe_id = str(deployment_id)
    if not safe_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("invalid deployment_id")
    return _approved_root(root) / f"deployment_{safe_id}"


def _resolve_under_root(path: str | Path, root: Path) -> Path:
    resolved = Path(path).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("path escapes approved taxonomy evidence root")
    if resolved.is_symlink():
        raise ValueError("symlink evidence path is not allowed")
    for parent in resolved.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlink evidence parent is not allowed")
    return resolved


def _operation_from_manifest(path: Path) -> TaxonomyOperation:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TaxonomyOperation(**payload)


def create_taxonomy_change_operation(
    *,
    deployment_id: str | int,
    operation_type: str,
    evidence_root: str | Path | None = None,
    initial_status: str = "RUNNING",
) -> TaxonomyOperation:
    timestamp = utc_now()
    operation_id = f"{operation_type.lower()}_{timestamp}_{uuid.uuid4().hex[:8]}"
    root = _deployment_dir(deployment_id, root=evidence_root)
    operation_dir = root / f"operation_{operation_id}"
    operation_dir.mkdir(parents=True, exist_ok=False)
    log_path = operation_dir / PRIMARY_LOG_NAME
    artifact_manifest_path = operation_dir / ARTIFACT_MANIFEST_NAME
    artifact_manifest_path.write_text(
        json.dumps({"operation_id": operation_id, "artifacts": []}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    operation = TaxonomyOperation(
        operation_id=operation_id,
        deployment_id=str(deployment_id),
        operation_type=operation_type,
        started_at_utc=timestamp,
        completed_at_utc=None,
        status=initial_status,
        failed_phase=None,
        resume_from_phase=None,
        evidence_root=str(operation_dir),
        primary_log_path=str(log_path),
        artifact_manifest_path=str(artifact_manifest_path),
    )
    log_path.write_text("", encoding="utf-8")
    _write_operation(operation)
    append_taxonomy_operation_log(operation, phase="START", status=initial_status, message="operation started")
    return operation


def _write_operation(operation: TaxonomyOperation) -> None:
    Path(operation.evidence_root, OPERATION_MANIFEST_NAME).write_text(
        json.dumps(operation.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def append_taxonomy_operation_log(
    operation: TaxonomyOperation,
    *,
    phase: str,
    status: str,
    message: str,
    artifact_path: str | None = None,
) -> None:
    event = {
        "utc_timestamp": utc_now(),
        "deployment_id": operation.deployment_id,
        "operation_id": operation.operation_id,
        "operation_type": operation.operation_type,
        "phase": phase,
        "status": status,
        "message": message,
        "artifact_path": artifact_path,
    }
    with Path(operation.primary_log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()


def write_taxonomy_operation_artifact(
    operation: TaxonomyOperation,
    *,
    relative_name: str,
    payload: Any,
) -> Path:
    if "/" in relative_name or "\\" in relative_name or relative_name.startswith("."):
        raise ValueError("artifact name must be a plain relative filename")
    root = Path(operation.evidence_root).resolve()
    path = _resolve_under_root(root / relative_name, root)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    manifest_path = Path(operation.artifact_manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = [item for item in manifest.get("artifacts", []) if item.get("path") != relative_name]
    artifacts.append(
        {
            "path": relative_name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    )
    manifest["artifacts"] = sorted(artifacts, key=lambda item: item["path"])
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    append_taxonomy_operation_log(operation, phase="ARTIFACT", status="OK", message=relative_name, artifact_path=relative_name)
    return path


def complete_taxonomy_change_operation(
    operation: TaxonomyOperation,
    *,
    status: str,
    failed_phase: str | None = None,
    resume_from_phase: str | None = None,
) -> TaxonomyOperation:
    completed = TaxonomyOperation(
        operation_id=operation.operation_id,
        deployment_id=operation.deployment_id,
        operation_type=operation.operation_type,
        started_at_utc=operation.started_at_utc,
        completed_at_utc=utc_now(),
        status=status,
        failed_phase=failed_phase,
        resume_from_phase=resume_from_phase,
        evidence_root=operation.evidence_root,
        primary_log_path=operation.primary_log_path,
        artifact_manifest_path=operation.artifact_manifest_path,
    )
    append_taxonomy_operation_log(completed, phase="COMPLETE", status=status, message="operation completed")
    _write_operation(completed)
    return completed


def list_taxonomy_change_operations(
    *,
    deployment_id: str | int,
    evidence_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = _deployment_dir(deployment_id, root=evidence_root)
    if not root.exists():
        return []
    operations = []
    for manifest in sorted(root.glob("operation_*/operation.json")):
        operation = _operation_from_manifest(manifest)
        operations.append(operation.as_dict())
    operations.sort(key=lambda item: (str(item.get("started_at_utc")), str(item.get("operation_id"))), reverse=True)
    return operations


def _load_operation(
    *,
    deployment_id: str | int,
    operation_id: str,
    evidence_root: str | Path | None = None,
) -> TaxonomyOperation:
    for item in list_taxonomy_change_operations(deployment_id=deployment_id, evidence_root=evidence_root):
        if item["operation_id"] == operation_id:
            if str(item["deployment_id"]) != str(deployment_id):
                raise ValueError("operation belongs to another deployment")
            return TaxonomyOperation(**item)
    raise FileNotFoundError("taxonomy operation not found")


def inspect_taxonomy_change_artifacts(
    *,
    deployment_id: str | int,
    operation_id: str,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    operation = _load_operation(deployment_id=deployment_id, operation_id=operation_id, evidence_root=evidence_root)
    root = Path(operation.evidence_root).resolve()
    log_path = _resolve_under_root(operation.primary_log_path, root)
    artifact_manifest = _resolve_under_root(operation.artifact_manifest_path, root)
    return {
        "operation": operation.as_dict(),
        "primary_log": {
            "path": str(log_path),
            "exists": log_path.is_file(),
            "size_bytes": log_path.stat().st_size if log_path.exists() else 0,
            "modified_at": int(log_path.stat().st_mtime) if log_path.exists() else None,
        },
        "artifact_manifest": json.loads(artifact_manifest.read_text(encoding="utf-8")),
        "automatic_deletion": False,
    }


def read_taxonomy_change_log(
    *,
    deployment_id: str | int,
    operation_id: str,
    offset: int = 0,
    limit: int = 65536,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    if offset < 0 or limit <= 0:
        raise ValueError("offset must be non-negative and limit must be positive")
    operation = _load_operation(deployment_id=deployment_id, operation_id=operation_id, evidence_root=evidence_root)
    root = Path(operation.evidence_root).resolve()
    log_path = _resolve_under_root(operation.primary_log_path, root)
    if not log_path.is_file():
        return {"status": "MISSING", "path": str(log_path), "text": "", "next_offset": offset, "size_bytes": 0}
    size = log_path.stat().st_size
    with log_path.open("r", encoding="utf-8") as handle:
        handle.seek(offset)
        text = handle.read(limit)
        next_offset = handle.tell()
    return {
        "status": "OK",
        "path": str(log_path),
        "text": text,
        "offset": offset,
        "next_offset": next_offset,
        "size_bytes": size,
        "truncated": next_offset < size,
        "modified_at": int(log_path.stat().st_mtime),
    }


def prepare_taxonomy_change_log_download(
    *,
    deployment_id: str | int,
    operation_id: str,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    operation = _load_operation(deployment_id=deployment_id, operation_id=operation_id, evidence_root=evidence_root)
    root = Path(operation.evidence_root).resolve()
    path = _resolve_under_root(operation.primary_log_path, root)
    if not path.is_file():
        return {"status": "MISSING", "error": "primary log is missing"}
    return {
        "status": "OK",
        "path": str(path),
        "filename": f"datacenter_taxonomy_change_deployment_{deployment_id}_{operation.started_at_utc}.log",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _package_exclusion_reason(path: Path) -> str | None:
    lower_name = path.name.lower()
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return "excluded database or SQLite sidecar file"
    if any(part in lower_name for part in EXCLUDED_NAME_PARTS):
        return "excluded backup or scheduler config artifact"
    return None


def prepare_taxonomy_change_evidence_package(
    *,
    deployment_id: str | int,
    operation_id: str,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    operation = _load_operation(deployment_id=deployment_id, operation_id=operation_id, evidence_root=evidence_root)
    root = Path(operation.evidence_root).resolve()
    package_dir = root / "packages"
    package_dir.mkdir(exist_ok=True)
    package_path = package_dir / f"datacenter_taxonomy_change_deployment_{deployment_id}_{operation_id}.zip"
    temp_path = package_path.with_suffix(".zip.tmp")
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total_size = 0
    candidates = sorted(path for path in root.iterdir() if path.is_file())
    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in candidates:
                resolved = _resolve_under_root(path, root)
                reason = _package_exclusion_reason(resolved)
                if reason:
                    excluded.append({"path": resolved.name, "reason": reason})
                    continue
                total_size += resolved.stat().st_size
                if total_size > MAX_EVIDENCE_PACKAGE_BYTES:
                    excluded.append({"path": resolved.name, "reason": "package size limit exceeded"})
                    continue
                file_hash = sha256_file(resolved)
                archive.write(resolved, arcname=resolved.name)
                included.append({"path": resolved.name, "size_bytes": resolved.stat().st_size, "sha256": file_hash})
            manifest = {
                "deployment_id": str(deployment_id),
                "operation_id": operation_id,
                "operation_type": operation.operation_type,
                "operation_status": operation.status,
                "created_at_utc": utc_now(),
                "included_files": included,
                "excluded_files": excluded,
            }
            archive.writestr(PACKAGE_MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
        shutil.move(str(temp_path), str(package_path))
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {
        "status": "OK",
        "path": str(package_path),
        "filename": package_path.name,
        "size_bytes": package_path.stat().st_size,
        "sha256": sha256_file(package_path),
        "manifest": manifest,
    }
