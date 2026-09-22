from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT


_RESULT_NOT_PROVIDED = object()
_HIDDEN_RUNS_FILE = ".hidden_runs.json"


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


@dataclass(frozen=True)
class RunProgressSummary:
    run_id: str
    operation_type: str
    status: str
    current_stage: str
    current_stage_number: int | None
    total_declared_stages: int | None
    completed_stages: int
    heartbeat_age_seconds: float | None
    terminal_outcome: str | None
    artifacts: tuple[str, ...]


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
        if path.is_symlink():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, Mapping) else None
        except Exception:
            return None

    def hidden_run_ids(self) -> frozenset[str]:
        path = self.root / _HIDDEN_RUNS_FILE
        if not path.exists() or path.is_symlink():
            return frozenset()
        payload = self._load_json(path)
        values = payload.get("hidden_run_ids") if payload else None
        if not isinstance(values, list):
            return frozenset()
        return frozenset(
            value for value in values
            if isinstance(value, str) and value and "/" not in value and "\\" not in value
        )

    def hide_run(self, run_id: str) -> Path:
        """Persistently remove a run from history without deleting audit evidence."""
        run_dir = self._resolve_run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError("admin run not found")
        hidden = set(self.hidden_run_ids())
        hidden.add(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / _HIDDEN_RUNS_FILE
        if destination.is_symlink():
            raise ValueError("hidden-run registry symlink is not allowed")
        temporary = self.root / f"{_HIDDEN_RUNS_FILE}.{os.getpid()}.tmp"
        if temporary.exists() or temporary.is_symlink():
            raise FileExistsError("hidden-run registry temporary path already exists")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(
                    {"schema_version": 1, "hidden_run_ids": sorted(hidden)},
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return run_dir

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
                completed_at_utc=result.get("completed_at_utc") or ((status or {}).get("timestamp_utc") if state != "running" else None),
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
        hidden = self.hidden_run_ids()
        entries: list[RunHistoryEntry] = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.name, reverse=True):
            if not path.is_dir() or path.is_symlink() or path.name in hidden:
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

    def progress(
        self,
        run_id: str,
        *,
        result_override: Mapping[str, Any] | None | object = _RESULT_NOT_PROVIDED,
    ) -> RunProgressSummary:
        run_dir = self._resolve_run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError("admin run not found")
        status = self._load_json(run_dir / "progress_status.json") or self._load_json(run_dir / "status.json") or {}
        stages = self._load_json(run_dir / "progress_stages.json") or {}
        result = (
            self._load_json(run_dir / "result.json")
            if result_override is _RESULT_NOT_PROVIDED
            else result_override
        )
        heartbeat_path = run_dir / "progress_events.jsonl"
        if not heartbeat_path.exists():
            heartbeat_path = run_dir / "heartbeat.jsonl"
        heartbeat_age = None
        if heartbeat_path.exists():
            heartbeat_age = max(0.0, __import__("time").time() - heartbeat_path.stat().st_mtime)
        terminal = str(result.get("outcome")) if result else None
        if result:
            state = "completed" if terminal == "COMPLETED" else str(terminal).lower()
        elif heartbeat_age is not None and heartbeat_age <= self.stale_seconds:
            state = "running"
        elif status:
            state = "interrupted"
        else:
            state = "corrupt_or_incomplete"
        event_states: dict[str, str] = {}
        events_path = run_dir / "progress_events.jsonl"
        if events_path.exists() and not events_path.is_symlink():
            try:
                for line in events_path.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    event_states[str(event.get("current_stage_id"))] = str(event.get("stage_state"))
            except Exception:
                event_states = {}
        completed = sum(1 for value in event_states.values() if value in {"COMPLETED", "SKIPPED", "ROLLED_BACK"})
        artifacts = tuple(
            path.name for path in sorted(run_dir.iterdir())
            if path.is_file() and not path.is_symlink()
        )
        return RunProgressSummary(
            run_id=run_id,
            operation_type=str(status.get("operation_type", result.get("operation_type") if result else "UNKNOWN")),
            status=state,
            current_stage=str(status.get("current_stage_id", status.get("stage", "UNKNOWN"))),
            current_stage_number=status.get("current_stage_number"),
            total_declared_stages=status.get("total_declared_stages"),
            completed_stages=completed,
            heartbeat_age_seconds=heartbeat_age,
            terminal_outcome=terminal,
            artifacts=artifacts,
        )
