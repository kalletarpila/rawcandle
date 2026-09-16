from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.admin.contracts import AdminOperationType, utc_now
from rawcandle.fundamentals.admin.redaction import redact
from rawcandle.io_atomic import write_text_atomic


class ProgressStage(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    PREVIEW_VALIDATION = "PREVIEW_VALIDATION"
    LOAD_ACTIVE_TAXONOMY = "LOAD_ACTIVE_TAXONOMY"
    LOAD_CANDIDATE = "LOAD_CANDIDATE"
    SOURCE_RESOLUTION = "SOURCE_RESOLUTION"
    RESOLVE_IDENTITIES = "RESOLVE_IDENTITIES"
    VALIDATE_HIERARCHY = "VALIDATE_HIERARCHY"
    BUILD_DIFF = "BUILD_DIFF"
    CLASSIFICATION_SCAN = "CLASSIFICATION_SCAN"
    CLASSIFICATION_RECONCILIATION = "CLASSIFICATION_RECONCILIATION"
    CLASSIFICATION_APPLY = "CLASSIFICATION_APPLY"
    PROVIDER_STAGING = "PROVIDER_STAGING"
    IDENTITY_AND_UNIVERSE = "IDENTITY_AND_UNIVERSE"
    CANONICAL_REBUILD = "CANONICAL_REBUILD"
    TTM_REBUILD = "TTM_REBUILD"
    STRUCTURAL_DEPENDENCIES = "STRUCTURAL_DEPENDENCIES"
    PACKAGE_CALCULATION = "PACKAGE_CALCULATION"
    PACKAGE_APPLY = "PACKAGE_APPLY"
    RELATIVE_POSITION = "RELATIVE_POSITION"
    RELATIVE_VALUATION = "RELATIVE_VALUATION"
    DEPENDENCY_ATTACHMENT = "DEPENDENCY_ATTACHMENT"
    SNAPSHOT_SMOKE = "SNAPSHOT_SMOKE"
    CREATE_COPIES = "CREATE_COPIES"
    APPLY_TAXONOMY = "APPLY_TAXONOMY"
    VALIDATE_APPLY = "VALIDATE_APPLY"
    REFRESH_DEPENDENCIES = "REFRESH_DEPENDENCIES"
    REPLAY_VERIFY = "REPLAY_VERIFY"
    ROLLBACK_VERIFY = "ROLLBACK_VERIFY"
    NO_CHANGE_VERIFICATION = "NO_CHANGE_VERIFICATION"
    FINAL_VALIDATION = "FINAL_VALIDATION"
    ROLLBACK = "ROLLBACK"
    CLEANUP = "CLEANUP"
    COMPLETED = "COMPLETED"


class ProgressState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


BATCH_ADD_TICKERS_STAGES: tuple[ProgressStage, ...] = (
    ProgressStage.PREFLIGHT,
    ProgressStage.PREVIEW_VALIDATION,
    ProgressStage.SOURCE_RESOLUTION,
    ProgressStage.IDENTITY_AND_UNIVERSE,
    ProgressStage.PROVIDER_STAGING,
    ProgressStage.CANONICAL_REBUILD,
    ProgressStage.TTM_REBUILD,
    ProgressStage.STRUCTURAL_DEPENDENCIES,
    ProgressStage.PACKAGE_CALCULATION,
    ProgressStage.PACKAGE_APPLY,
    ProgressStage.RELATIVE_POSITION,
    ProgressStage.RELATIVE_VALUATION,
    ProgressStage.DEPENDENCY_ATTACHMENT,
    ProgressStage.SNAPSHOT_SMOKE,
    ProgressStage.NO_CHANGE_VERIFICATION,
    ProgressStage.FINAL_VALIDATION,
    ProgressStage.ROLLBACK,
    ProgressStage.CLEANUP,
    ProgressStage.COMPLETED,
)


SECTOR_INDUSTRY_STAGES: tuple[ProgressStage, ...] = (
    ProgressStage.PREFLIGHT,
    ProgressStage.PREVIEW_VALIDATION,
    ProgressStage.CLASSIFICATION_SCAN,
    ProgressStage.CLASSIFICATION_RECONCILIATION,
    ProgressStage.CLASSIFICATION_APPLY,
    ProgressStage.PACKAGE_CALCULATION,
    ProgressStage.PACKAGE_APPLY,
    ProgressStage.RELATIVE_POSITION,
    ProgressStage.RELATIVE_VALUATION,
    ProgressStage.DEPENDENCY_ATTACHMENT,
    ProgressStage.SNAPSHOT_SMOKE,
    ProgressStage.NO_CHANGE_VERIFICATION,
    ProgressStage.FINAL_VALIDATION,
    ProgressStage.ROLLBACK,
    ProgressStage.CLEANUP,
    ProgressStage.COMPLETED,
)


TAXONOMY_STAGES: tuple[ProgressStage, ...] = (
    ProgressStage.PREFLIGHT,
    ProgressStage.LOAD_ACTIVE_TAXONOMY,
    ProgressStage.LOAD_CANDIDATE,
    ProgressStage.RESOLVE_IDENTITIES,
    ProgressStage.VALIDATE_HIERARCHY,
    ProgressStage.BUILD_DIFF,
    ProgressStage.PREVIEW_VALIDATION,
    ProgressStage.CREATE_COPIES,
    ProgressStage.APPLY_TAXONOMY,
    ProgressStage.VALIDATE_APPLY,
    ProgressStage.REFRESH_DEPENDENCIES,
    ProgressStage.SNAPSHOT_SMOKE,
    ProgressStage.REPLAY_VERIFY,
    ProgressStage.ROLLBACK_VERIFY,
    ProgressStage.ROLLBACK,
    ProgressStage.CLEANUP,
    ProgressStage.COMPLETED,
)


@dataclass(frozen=True)
class ProgressEvent:
    run_id: str
    operation_type: str
    current_stage_id: str
    current_stage_number: int
    total_declared_stages: int
    stage_state: str
    message: str
    run_started_at_utc: str
    stage_started_at_utc: str | None
    stage_ended_at_utc: str | None
    elapsed_run_seconds: float
    elapsed_stage_seconds: float | None
    last_heartbeat_at_utc: str
    processed_items: int | None = None
    total_items: int | None = None
    processed_rows: int | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    rollback_state: str | None = None
    percent_complete: float | None = None
    sequence: int = 0
    pid: int = field(default_factory=os.getpid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "operation_type": self.operation_type,
            "current_stage_id": self.current_stage_id,
            "current_stage_number": self.current_stage_number,
            "total_declared_stages": self.total_declared_stages,
            "stage_state": self.stage_state,
            "message": self.message,
            "run_started_at_utc": self.run_started_at_utc,
            "stage_started_at_utc": self.stage_started_at_utc,
            "stage_ended_at_utc": self.stage_ended_at_utc,
            "elapsed_run_seconds": self.elapsed_run_seconds,
            "elapsed_stage_seconds": self.elapsed_stage_seconds,
            "last_heartbeat_at_utc": self.last_heartbeat_at_utc,
            "processed_items": self.processed_items,
            "total_items": self.total_items,
            "processed_rows": self.processed_rows,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "rollback_state": self.rollback_state,
            "percent_complete": self.percent_complete,
            "sequence": self.sequence,
            "pid": self.pid,
        }


ProgressCallback = Callable[[Mapping[str, Any]], None]


class ProgressTracker:
    def __init__(
        self,
        *,
        run_id: str,
        operation_type: AdminOperationType | str,
        run_dir: Path,
        stages: Sequence[ProgressStage] = BATCH_ADD_TICKERS_STAGES,
        configured_secrets: Sequence[str] = (),
        callback: ProgressCallback | None = None,
        clock: Callable[[], str] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if len(tuple(stages)) != len(set(stages)):
            raise ValueError("PROGRESS_STAGES_MUST_BE_UNIQUE")
        self.run_id = run_id
        self.operation_type = operation_type.value if isinstance(operation_type, AdminOperationType) else str(operation_type)
        self.run_dir = run_dir
        self.stages = tuple(stages)
        self.configured_secrets = tuple(configured_secrets)
        self.callback = callback
        self.clock = clock
        self.monotonic = monotonic
        self.started_at = self.clock()
        self.started_monotonic = self.monotonic()
        self._sequence = 0
        self._stage_index = -1
        self._stage_state: dict[ProgressStage, ProgressState] = {stage: ProgressState.PENDING for stage in self.stages}
        self._stage_started_at: dict[ProgressStage, str] = {}
        self._stage_started_monotonic: dict[ProgressStage, float] = {}
        self._last_event: dict[str, Any] | None = None
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._write_declared_stages()

    def _write_declared_stages(self) -> None:
        payload = {
            "run_id": self.run_id,
            "operation_type": self.operation_type,
            "stages": [
                {"stage_id": stage.value, "stage_number": index + 1, "state": ProgressState.PENDING.value}
                for index, stage in enumerate(self.stages)
            ],
        }
        write_text_atomic(self.run_dir / "progress_stages.json", json.dumps(self._safe(payload), indent=2, sort_keys=True) + "\n")

    def _safe(self, value: Any) -> Any:
        return redact(value, configured_secrets=self.configured_secrets)

    def _index(self, stage: ProgressStage) -> int:
        try:
            return self.stages.index(stage)
        except ValueError as exc:
            raise ValueError(f"PROGRESS_STAGE_NOT_DECLARED:{stage.value}") from exc

    def _validate(self, stage: ProgressStage, state: ProgressState) -> int:
        index = self._index(stage)
        current = self._stage_state[stage]
        if state == ProgressState.RUNNING:
            if current not in {ProgressState.PENDING, ProgressState.RUNNING}:
                raise ValueError(f"PROGRESS_STAGE_ALREADY_CLOSED:{stage.value}:{current.value}")
            if index < self._stage_index and stage != ProgressStage.ROLLBACK:
                raise ValueError(f"PROGRESS_STAGE_ORDER_REGRESSION:{stage.value}")
            self._stage_index = max(self._stage_index, index)
        elif state in {ProgressState.COMPLETED, ProgressState.SKIPPED}:
            if current not in {ProgressState.PENDING, ProgressState.RUNNING}:
                raise ValueError(f"PROGRESS_STAGE_CANNOT_CLOSE:{stage.value}:{current.value}")
        elif state == ProgressState.ROLLING_BACK:
            if stage != ProgressStage.ROLLBACK:
                raise ValueError("PROGRESS_ROLLING_BACK_REQUIRES_ROLLBACK_STAGE")
            self._stage_index = max(self._stage_index, index)
        elif state == ProgressState.ROLLED_BACK:
            if stage != ProgressStage.ROLLBACK or current != ProgressState.ROLLING_BACK:
                raise ValueError("PROGRESS_ROLLED_BACK_REQUIRES_ROLLING_BACK")
        elif state == ProgressState.FAILED:
            if current in {ProgressState.COMPLETED, ProgressState.SKIPPED, ProgressState.ROLLED_BACK}:
                raise ValueError(f"PROGRESS_STAGE_CANNOT_FAIL_AFTER_CLOSE:{stage.value}:{current.value}")
        return index

    def emit(
        self,
        stage: ProgressStage,
        state: ProgressState,
        message: str,
        *,
        processed_items: int | None = None,
        total_items: int | None = None,
        processed_rows: int | None = None,
        warnings: Sequence[str] = (),
        errors: Sequence[str] = (),
        rollback_state: str | None = None,
    ) -> dict[str, Any]:
        index = self._validate(stage, state)
        now = self.clock()
        now_mono = self.monotonic()
        if state in {ProgressState.RUNNING, ProgressState.ROLLING_BACK} and stage not in self._stage_started_at:
            self._stage_started_at[stage] = now
            self._stage_started_monotonic[stage] = now_mono
        if state != ProgressState.PENDING:
            self._stage_state[stage] = state
        started_mono = self._stage_started_monotonic.get(stage)
        ended = now if state in {ProgressState.COMPLETED, ProgressState.SKIPPED, ProgressState.FAILED, ProgressState.ROLLED_BACK} else None
        percent = None
        if total_items is not None and total_items > 0 and processed_items is not None:
            percent = round(min(100.0, max(0.0, processed_items * 100.0 / total_items)), 2)
        self._sequence += 1
        event = ProgressEvent(
            run_id=self.run_id,
            operation_type=self.operation_type,
            current_stage_id=stage.value,
            current_stage_number=index + 1,
            total_declared_stages=len(self.stages),
            stage_state=state.value,
            message=message,
            run_started_at_utc=self.started_at,
            stage_started_at_utc=self._stage_started_at.get(stage),
            stage_ended_at_utc=ended,
            elapsed_run_seconds=round(now_mono - self.started_monotonic, 3),
            elapsed_stage_seconds=round(now_mono - started_mono, 3) if started_mono is not None else None,
            last_heartbeat_at_utc=now,
            processed_items=processed_items,
            total_items=total_items,
            processed_rows=processed_rows,
            warnings=tuple(warnings),
            errors=tuple(errors),
            rollback_state=rollback_state,
            percent_complete=percent,
            sequence=self._sequence,
        ).as_dict()
        safe = self._safe(event)
        write_text_atomic(self.run_dir / "progress_status.json", json.dumps(safe, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n")
        with (self.run_dir / "progress_events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, sort_keys=True, allow_nan=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._last_event = safe
        if self.callback is not None:
            self.callback(safe)
        return safe

    def running(self, stage: ProgressStage, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(stage, ProgressState.RUNNING, message, **kwargs)

    def completed(self, stage: ProgressStage, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(stage, ProgressState.COMPLETED, message, **kwargs)

    def skipped(self, stage: ProgressStage, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(stage, ProgressState.SKIPPED, message, **kwargs)

    def failed(self, stage: ProgressStage, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(stage, ProgressState.FAILED, message, **kwargs)

    def rolling_back(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(ProgressStage.ROLLBACK, ProgressState.ROLLING_BACK, message, rollback_state="ROLLING_BACK", **kwargs)

    def rolled_back(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self.emit(ProgressStage.ROLLBACK, ProgressState.ROLLED_BACK, message, rollback_state="ROLLED_BACK", **kwargs)

    def heartbeat(self, message: str | None = None) -> dict[str, Any] | None:
        if self._last_event is None:
            return None
        stage = ProgressStage(self._last_event["current_stage_id"])
        state = ProgressState(self._last_event["stage_state"])
        return self.emit(stage, state, message or str(self._last_event.get("message") or "Heartbeat."))


def progress_line(event: Mapping[str, Any]) -> str:
    elapsed = int(float(event.get("elapsed_run_seconds") or 0))
    minutes, seconds = divmod(elapsed, 60)
    elapsed_text = f"{minutes:02d}:{seconds:02d} elapsed"
    rows = event.get("processed_rows")
    row_text = f" - {int(rows):,} rows" if rows is not None else ""
    items = event.get("processed_items")
    total = event.get("total_items")
    if items is not None and total is not None:
        item_text = f" - {int(items):,}/{int(total):,} items"
    elif items is not None:
        item_text = f" - {int(items):,} items"
    else:
        item_text = ""
    return (
        f"[{event['current_stage_number']}/{event['total_declared_stages']}] "
        f"{event['current_stage_id']} - {event['stage_state']} - {elapsed_text}{item_text}{row_text} - {event.get('message') or ''}"
    )
