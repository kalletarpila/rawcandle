from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT


@dataclass(frozen=True)
class RunHistoryEntry:
    run_id: str
    operation_type: str
    stage: str
    outcome: str
    status: str
    started_at_utc: str | None
    completed_at_utc: str | None
    run_dir: str


class AdminRunHistory:
    def __init__(self, root: Path = ADMIN_RUN_ROOT, *, stale_seconds: int = 3600) -> None:
        self.root = root.resolve()
        self.stale_seconds = stale_seconds

    def _resolve_run_dir(self, run_id: str) -> Path:
        if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
            raise ValueError("invalid run_id")
        raw_path = self.root / run_id
        if raw_path.is_symlink():
            raise ValueError("run path symlink is not allowed")
        path = raw_path.resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("run path escapes admin root")
        return path

    def _load_json(self, path: Path) -> Mapping[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _heartbeat_recent(self, run_dir: Path) -> bool:
        heartbeat = run_dir / "heartbeat.jsonl"
        if not heartbeat.exists():
            return False
        age = max(0.0, __import__("time").time() - heartbeat.stat().st_mtime)
        return age <= self.stale_seconds

    def _active_pid(self, status: Mapping[str, Any] | None) -> bool:
        pid = int((status or {}).get("pid") or 0)
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def summarize(self, run_id: str) -> RunHistoryEntry:
        run_dir = self._resolve_run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError("admin run not found")
        result = self._load_json(run_dir / "result.json")
        status = self._load_json(run_dir / "status.json")
        if result:
            outcome = str(result.get("outcome", "UNKNOWN"))
            state = "completed" if outcome == "COMPLETED" else outcome.lower()
            return RunHistoryEntry(
                run_id=run_id,
                operation_type=str(result.get("operation_type", status.get("operation_type") if status else "UNKNOWN")),
                stage=str(status.get("stage", "COMPLETED") if status else "COMPLETED"),
                outcome=outcome,
                status=state,
                started_at_utc=result.get("started_at_utc"),
                completed_at_utc=result.get("completed_at_utc"),
                run_dir=str(run_dir),
            )
        stage = str((status or {}).get("stage", "UNKNOWN"))
        if self._heartbeat_recent(run_dir) or self._active_pid(status):
            state = "running"
            outcome = "RUNNING"
        elif status is None:
            state = "corrupt_or_incomplete"
            outcome = "CORRUPT_OR_INCOMPLETE"
        else:
            state = "interrupted"
            outcome = "INTERRUPTED"
        return RunHistoryEntry(
            run_id=run_id,
            operation_type=str((status or {}).get("operation_type", "UNKNOWN")),
            stage=stage,
            outcome=outcome,
            status=state,
            started_at_utc=(status or {}).get("timestamp_utc"),
            completed_at_utc=None,
            run_dir=str(run_dir),
        )

    def list_runs(self, *, operation_type: str | None = None, outcome: str | None = None) -> list[RunHistoryEntry]:
        if not self.root.exists():
            return []
        entries: list[RunHistoryEntry] = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.name, reverse=True):
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                entry = self.summarize(path.name)
            except Exception:
                continue
            if operation_type and entry.operation_type != operation_type:
                continue
            if outcome and entry.outcome != outcome:
                continue
            entries.append(entry)
        return entries

    def artifact_path(self, run_id: str, artifact_name: str) -> Path:
        if "/" in artifact_name or "\\" in artifact_name or artifact_name in {"", ".", ".."}:
            raise ValueError("invalid artifact name")
        run_dir = self._resolve_run_dir(run_id)
        path = (run_dir / artifact_name).resolve()
        if run_dir != path.parent or path.is_symlink():
            raise ValueError("artifact path escapes run directory")
        if not path.is_file():
            raise FileNotFoundError("admin artifact not found")
        return path
