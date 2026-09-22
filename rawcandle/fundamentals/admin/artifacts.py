from __future__ import annotations

import csv
import hashlib
import json
import os
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.admin.contracts import (
    AdminCheckpoint,
    AdminFinalResult,
    AdminOperationType,
    RunStage,
    utc_now,
    validate_transition,
)
from rawcandle.fundamentals.admin.redaction import redact, redact_text
from rawcandle.io_atomic import write_text_atomic


ROOT = Path(__file__).resolve().parents[3]
REPORT_ROOT = ROOT / "fundamental_reports"
ADMIN_RUN_ROOT = REPORT_ROOT / "admin_runs"
ADMIN_TEMP_ROOT = ROOT / "temp" / "fundamentals_admin_phase13g1"


def stable_run_id(operation_type: AdminOperationType, request_fingerprint: str, *, suffix: str | None = None) -> str:
    prefix = utc_now().replace("-", "").replace(":", "").replace("+00:00", "Z")
    short = hashlib.sha256(f"{operation_type.value}:{request_fingerprint}".encode("utf-8")).hexdigest()[:12]
    extra = f"_{suffix}" if suffix else ""
    return f"{prefix}_{operation_type.value.lower()}_{short}{extra}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AdminRunWriter:
    def __init__(
        self,
        run_id: str,
        operation_type: AdminOperationType,
        *,
        root: Path = ADMIN_RUN_ROOT,
        configured_secrets: Sequence[str] = (),
    ) -> None:
        self.run_id = run_id
        self.operation_type = operation_type
        self.root = root.resolve()
        self.run_dir = (self.root / run_id).resolve()
        if self.root != self.run_dir and self.root not in self.run_dir.parents:
            raise ValueError("admin run directory escapes configured root")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.configured_secrets = tuple(configured_secrets)
        self._sequence = 0
        self._stage: RunStage | None = None
        self._write_boundary_crossed = False

    def _safe(self, value: Any) -> Any:
        return redact(value, configured_secrets=self.configured_secrets)

    def write_json(self, name: str, value: Any) -> Path:
        path = self.run_dir / name
        write_text_atomic(path, json.dumps(self._safe(value), indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.run_dir / name
        write_text_atomic(path, redact_text(text, configured_secrets=self.configured_secrets))
        return path

    def append_heartbeat(self, payload: Mapping[str, Any]) -> Path:
        return self.append_jsonl("heartbeat.jsonl", payload)

    def append_jsonl(self, name: str, payload: Mapping[str, Any]) -> Path:
        if "/" in name or "\\" in name or not name.endswith(".jsonl"):
            raise ValueError("invalid JSONL artifact name")
        path = self.run_dir / name
        safe = self._safe(dict(payload))
        safe.setdefault("run_id", self.run_id)
        safe.setdefault("operation_type", self.operation_type.value)
        safe.setdefault("timestamp_utc", utc_now())
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, sort_keys=True, allow_nan=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path

    def checkpoint(
        self,
        stage: RunStage,
        *,
        message: str,
        preview_fingerprint: str | None = None,
        counters: Mapping[str, Any] | None = None,
        write_boundary_crossed: bool | None = None,
    ) -> AdminCheckpoint:
        boundary = self._write_boundary_crossed if write_boundary_crossed is None else write_boundary_crossed
        validate_transition(self._stage, stage, write_boundary_crossed=boundary)
        self._sequence += 1
        if stage == RunStage.WRITE_BOUNDARY_CROSSED or boundary:
            self._write_boundary_crossed = True
            boundary = True
        checkpoint = AdminCheckpoint(
            run_id=self.run_id,
            operation_type=self.operation_type,
            stage=stage,
            timestamp_utc=utc_now(),
            sequence=self._sequence,
            preview_fingerprint=preview_fingerprint,
            write_boundary_crossed=boundary,
            message=message,
            counters=dict(counters or {}),
        )
        self._stage = stage
        self.write_json("status.json", checkpoint.as_dict())
        self.append_heartbeat(checkpoint.as_dict())
        return checkpoint

    def write_items_csv(self, items: Sequence[Mapping[str, Any]], name: str = "items.csv") -> Path:
        fields = [
            "requested_value",
            "normalized_value",
            "item_key",
            "market",
            "company_name",
            "status",
            "reason",
            "old_value",
            "new_value",
            "source_category",
            "warning",
            "applied_action",
        ]
        path = self.run_dir / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for item in self._safe(list(items)):
                row = dict(item)
                warnings = row.get("warnings") or []
                row["warning"] = "; ".join(str(value) for value in warnings)
                writer.writerow(row)
        return path

    def write_error(self, exc: BaseException) -> Path:
        payload = {
            "error_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
        }
        return self.write_json("error.json", payload)

    def write_final_result(self, result: AdminFinalResult) -> Path:
        return self.write_json("result.json", result.as_dict())

    def write_exit_code(self, code: int) -> Path:
        return self.write_text("exit_code", f"{int(code)}\n")

    def write_manifest(self) -> Path:
        report_path = self.run_dir / "operation_report.md"
        if (self.run_dir / "result.json").is_file() and not report_path.exists():
            from rawcandle.fundamentals.admin.operation_report import write_operation_report

            write_operation_report(self.run_id, root=self.root)
        artifacts = []
        for path in sorted(self.run_dir.iterdir()):
            if not path.is_file() or path.name == "artifact_manifest.json":
                continue
            artifacts.append({
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
        return self.write_json("artifact_manifest.json", {"run_id": self.run_id, "artifacts": artifacts})
