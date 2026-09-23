from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class AdminOperationType(str, Enum):
    ADD_TICKERS = "ADD_TICKERS"
    REMOVE_TICKERS = "REMOVE_TICKERS"
    REMOVE_FUNDAMENTALS_TICKERS = "REMOVE_FUNDAMENTALS_TICKERS"
    REFRESH_FUNDAMENTALS = "REFRESH_FUNDAMENTALS"
    CHECK_UPDATE_SECTOR_INDUSTRY = "CHECK_UPDATE_SECTOR_INDUSTRY"
    CHECK_UPDATE_TAXONOMY = "CHECK_UPDATE_TAXONOMY"
    UPDATE_SECTOR_INDUSTRY = "UPDATE_SECTOR_INDUSTRY"
    UPDATE_TAXONOMY = "UPDATE_TAXONOMY"
    SYNCHRONIZE_PROVIDER_CIK = "SYNCHRONIZE_PROVIDER_CIK"
    RESOLVE_TICKER_IDENTITY = "RESOLVE_TICKER_IDENTITY"


class AdminStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    NO_CHANGE = "NO_CHANGE"
    APPLIED = "APPLIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    ROLLED_BACK = "ROLLED_BACK"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"


class RunStage(str, Enum):
    REQUEST_CREATED = "REQUEST_CREATED"
    PREVIEW_STARTED = "PREVIEW_STARTED"
    PREVIEW_READY = "PREVIEW_READY"
    APPLY_CONFIRMATION_PENDING = "APPLY_CONFIRMATION_PENDING"
    APPLY_STARTED = "APPLY_STARTED"
    WRITE_BOUNDARY_NOT_CROSSED = "WRITE_BOUNDARY_NOT_CROSSED"
    WRITE_BOUNDARY_CROSSED = "WRITE_BOUNDARY_CROSSED"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_COMPLETE = "ROLLBACK_COMPLETE"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED_BEFORE_WRITE = "FAILED_BEFORE_WRITE"
    FAILED_AFTER_WRITE = "FAILED_AFTER_WRITE"
    INTERRUPTED = "INTERRUPTED"


STATUS_MESSAGES: dict[AdminStatus, str] = {
    AdminStatus.ELIGIBLE: "Ready to be included in an apply run.",
    AdminStatus.ALREADY_PRESENT: "Already present; no new action is needed.",
    AdminStatus.NO_CHANGE: "No data would change.",
    AdminStatus.APPLIED: "The accepted action was applied.",
    AdminStatus.REVIEW_REQUIRED: "Needs operator review before it can be applied.",
    AdminStatus.REJECTED: "Rejected by validation and will not be applied.",
    AdminStatus.FAILED: "The item failed during processing.",
    AdminStatus.INTERRUPTED: "The run stopped before a final result was recorded.",
    AdminStatus.ROLLED_BACK: "A post-write failure was rolled back.",
    AdminStatus.COMPLETED: "The run completed successfully.",
    AdminStatus.PARTIALLY_COMPLETED: "The run completed with some unresolved items.",
}

TERMINAL_STAGES = {
    RunStage.COMPLETED,
    RunStage.PARTIALLY_COMPLETED,
    RunStage.FAILED_BEFORE_WRITE,
    RunStage.FAILED_AFTER_WRITE,
    RunStage.INTERRUPTED,
}

VALID_TRANSITIONS: dict[RunStage, set[RunStage]] = {
    RunStage.REQUEST_CREATED: {RunStage.PREVIEW_STARTED, RunStage.APPLY_STARTED, RunStage.INTERRUPTED},
    RunStage.PREVIEW_STARTED: {RunStage.PREVIEW_READY, RunStage.FAILED_BEFORE_WRITE, RunStage.INTERRUPTED},
    RunStage.PREVIEW_READY: {RunStage.APPLY_CONFIRMATION_PENDING, RunStage.COMPLETED, RunStage.INTERRUPTED},
    RunStage.APPLY_CONFIRMATION_PENDING: {RunStage.APPLY_STARTED, RunStage.INTERRUPTED},
    RunStage.APPLY_STARTED: {RunStage.WRITE_BOUNDARY_NOT_CROSSED, RunStage.WRITE_BOUNDARY_CROSSED, RunStage.FAILED_BEFORE_WRITE, RunStage.INTERRUPTED},
    RunStage.WRITE_BOUNDARY_NOT_CROSSED: {RunStage.WRITE_BOUNDARY_CROSSED, RunStage.COMPLETED, RunStage.FAILED_BEFORE_WRITE, RunStage.INTERRUPTED},
    RunStage.WRITE_BOUNDARY_CROSSED: {RunStage.ROLLBACK_STARTED, RunStage.COMPLETED, RunStage.PARTIALLY_COMPLETED, RunStage.FAILED_AFTER_WRITE, RunStage.INTERRUPTED},
    RunStage.ROLLBACK_STARTED: {RunStage.ROLLBACK_COMPLETE, RunStage.FAILED_AFTER_WRITE, RunStage.INTERRUPTED},
    RunStage.ROLLBACK_COMPLETE: {RunStage.FAILED_AFTER_WRITE, RunStage.PARTIALLY_COMPLETED},
}

FINGERPRINT_EXCLUDED_KEYS = {
    "run_id",
    "created_at_utc",
    "started_at_utc",
    "updated_at_utc",
    "completed_at_utc",
    "timestamp_utc",
    "pid",
    "process_id",
    "sequence",
    "output_path",
    "artifact_dir",
    "temp_path",
    "temporary_database_path",
    "heartbeat_counter",
}


@dataclass(frozen=True)
class AdminItemDecision:
    item_key: str
    requested_value: str
    normalized_value: str
    status: AdminStatus
    reason: str
    market: str | None = None
    company_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    source_category: str | None = None
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    applied_action: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["status_message"] = STATUS_MESSAGES[self.status]
        return data


@dataclass(frozen=True)
class AdminBatchRequest:
    operation_type: AdminOperationType
    requested_inputs: tuple[str, ...]
    normalized_inputs: tuple[str, ...]
    rejected_inputs: tuple[Mapping[str, str], ...] = ()
    market: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operation_type"] = self.operation_type.value
        return data


@dataclass(frozen=True)
class AdminPreview:
    operation_type: AdminOperationType
    request: AdminBatchRequest
    decisions: tuple[AdminItemDecision, ...]
    source_state: Mapping[str, Any] = field(default_factory=dict)
    proposed_changes: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = {
            "operation_type": self.operation_type.value,
            "request": self.request.as_dict(),
            "decisions": [item.as_dict() for item in self.decisions],
            "source_state": dict(self.source_state),
            "proposed_changes": [dict(item) for item in self.proposed_changes],
            "warnings": list(self.warnings),
        }
        data["request_fingerprint"] = fingerprint(self.request)
        data["change_set_fingerprint"] = fingerprint(self.proposed_changes)
        data["preview_fingerprint"] = fingerprint(data)
        return data


@dataclass(frozen=True)
class AdminCheckpoint:
    run_id: str
    operation_type: AdminOperationType
    stage: RunStage
    timestamp_utc: str
    sequence: int
    preview_fingerprint: str | None = None
    write_boundary_crossed: bool = False
    message: str = ""
    counters: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "operation_type": self.operation_type.value,
            "stage": self.stage.value,
            "timestamp_utc": self.timestamp_utc,
            "sequence": self.sequence,
            "preview_fingerprint": self.preview_fingerprint,
            "write_boundary_crossed": self.write_boundary_crossed,
            "message": self.message,
            "counters": dict(self.counters),
        }


@dataclass(frozen=True)
class AdminFinalResult:
    run_id: str
    operation_type: AdminOperationType
    outcome: AdminStatus
    mode: str
    started_at_utc: str
    completed_at_utc: str
    preview_fingerprint: str | None
    request: Mapping[str, Any]
    item_results: tuple[AdminItemDecision, ...] = ()
    summary_counts: Mapping[str, int] = field(default_factory=dict)
    rollback: Mapping[str, Any] = field(default_factory=dict)
    downstream: Mapping[str, Any] = field(default_factory=dict)
    artifacts: Mapping[str, str] = field(default_factory=dict)
    recommended_next_action: str = ""
    errors: tuple[Mapping[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operation_type"] = self.operation_type.value
        data["outcome"] = self.outcome.value
        data["outcome_message"] = STATUS_MESSAGES[self.outcome]
        data["item_results"] = [item.as_dict() for item in self.item_results]
        data["result_fingerprint"] = fingerprint({
            "operation_type": data["operation_type"],
            "outcome": data["outcome"],
            "request": data["request"],
            "item_results": data["item_results"],
            "summary_counts": data["summary_counts"],
            "rollback": data["rollback"],
            "downstream": data["downstream"],
        })
        return data


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonicalize(value: Any, *, exclude_run_local: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return canonicalize(asdict(value), exclude_run_local=exclude_run_local)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            text_key = str(key)
            if exclude_run_local and text_key in FINGERPRINT_EXCLUDED_KEYS:
                continue
            output[text_key] = canonicalize(item, exclude_run_local=exclude_run_local)
        return output
    if isinstance(value, (list, tuple)):
        return [canonicalize(item, exclude_run_local=exclude_run_local) for item in value]
    if isinstance(value, set):
        return sorted(canonicalize(item, exclude_run_local=exclude_run_local) for item in value)
    return value


def canonical_json(value: Any, *, exclude_run_local: bool = True) -> str:
    return json.dumps(
        canonicalize(value, exclude_run_local=exclude_run_local),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_item_tokens(raw: str | Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[dict[str, str], ...]]:
    text = raw if isinstance(raw, str) else " ".join(raw)
    requested = tuple(token.strip() for token in re.split(r"[\s,]+", text or "") if token.strip())
    normalized: list[str] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for token in requested:
        value = token.upper()
        if not re.match(r"^[A-Z0-9][A-Z0-9._-]{0,63}$", value):
            rejected.append({"requested_value": token, "reason": "Malformed item key"})
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return requested, tuple(normalized), tuple(rejected)


def build_batch_request(
    operation_type: AdminOperationType,
    raw_inputs: str | Sequence[str],
    *,
    market: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> AdminBatchRequest:
    requested, normalized, rejected = normalize_item_tokens(raw_inputs)
    return AdminBatchRequest(
        operation_type=operation_type,
        requested_inputs=requested,
        normalized_inputs=normalized,
        rejected_inputs=rejected,
        market=market.lower() if market else None,
        options=dict(options or {}),
    )


def validate_transition(previous: RunStage | None, next_stage: RunStage, *, write_boundary_crossed: bool = False) -> None:
    if previous is None:
        if next_stage != RunStage.REQUEST_CREATED:
            raise ValueError(f"first admin stage must be {RunStage.REQUEST_CREATED.value}")
        return
    if previous in TERMINAL_STAGES:
        raise ValueError(f"invalid admin lifecycle transition from terminal stage {previous.value} to {next_stage.value}")
    allowed = VALID_TRANSITIONS.get(previous, set())
    if next_stage not in allowed:
        raise ValueError(f"invalid admin lifecycle transition from {previous.value} to {next_stage.value}")
    if next_stage == RunStage.ROLLBACK_COMPLETE and not write_boundary_crossed:
        raise ValueError("rollback complete requires a crossed write boundary")
