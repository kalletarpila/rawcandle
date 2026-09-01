from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Sequence


MODEL_VERSION = "V4_FUNDAMENTAL_LIFECYCLE_V1"
TTM_MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"


class LifecycleState(str, Enum):
    STARTUP = "STARTUP"
    DISTRESSED = "DISTRESSED"
    SCALING = "SCALING"
    GROWTH = "GROWTH"
    MATURE = "MATURE"
    DECLINING = "DECLINING"
    STRUGGLING = "STRUGGLING"
    TRANSITION = "TRANSITION"
    UNCLASSIFIED = "UNCLASSIFIED"


class LifecycleStatus(str, Enum):
    READY = "LIFECYCLE_READY"
    NOT_READY = "LIFECYCLE_NOT_READY"


class StartupProfile(str, Enum):
    PRE_REVENUE = "PRE_REVENUE"
    REVENUE_GENERATING = "REVENUE_GENERATING"


class LifecycleReason(str, Enum):
    CLASSIFIED_PRE_REVENUE_STARTUP = "CLASSIFIED_PRE_REVENUE_STARTUP"
    CLASSIFIED_DISTRESSED = "CLASSIFIED_DISTRESSED"
    CLASSIFIED_REVENUE_GENERATING_STARTUP = "CLASSIFIED_REVENUE_GENERATING_STARTUP"
    CLASSIFIED_SCALING = "CLASSIFIED_SCALING"
    CLASSIFIED_GROWTH = "CLASSIFIED_GROWTH"
    CLASSIFIED_MATURE = "CLASSIFIED_MATURE"
    CLASSIFIED_DECLINING = "CLASSIFIED_DECLINING"
    CLASSIFIED_STRUGGLING = "CLASSIFIED_STRUGGLING"
    CLASSIFIED_TRANSITION = "CLASSIFIED_TRANSITION"
    TTM_NOT_READY = "TTM_NOT_READY"
    TTM_MODEL_VERSION_UNSUPPORTED = "TTM_MODEL_VERSION_UNSUPPORTED"
    SOURCE_AVAILABILITY_DATE_MISSING = "SOURCE_AVAILABILITY_DATE_MISSING"
    SOURCE_AVAILABILITY_DATE_INVALID = "SOURCE_AVAILABILITY_DATE_INVALID"
    CURRENT_REVENUE_MISSING = "CURRENT_REVENUE_MISSING"
    CURRENT_REVENUE_INVALID = "CURRENT_REVENUE_INVALID"
    CURRENT_REVENUE_NEGATIVE = "CURRENT_REVENUE_NEGATIVE"
    CURRENT_EBIT_MISSING = "CURRENT_EBIT_MISSING"
    CURRENT_EBIT_INVALID = "CURRENT_EBIT_INVALID"
    CURRENT_FCF_MISSING = "CURRENT_FCF_MISSING"
    CURRENT_FCF_INVALID = "CURRENT_FCF_INVALID"
    PRE_REVENUE_QUARTER_COUNT_INVALID = "PRE_REVENUE_QUARTER_COUNT_INVALID"
    PRE_REVENUE_QUARTER_REVENUE_MISSING = "PRE_REVENUE_QUARTER_REVENUE_MISSING"
    PRE_REVENUE_QUARTER_REVENUE_INVALID = "PRE_REVENUE_QUARTER_REVENUE_INVALID"
    ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET = "ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET"
    FISCAL_CHAIN_INVALID = "FISCAL_CHAIN_INVALID"
    LAG4_REVENUE_MISSING = "LAG4_REVENUE_MISSING"
    LAG4_REVENUE_INVALID = "LAG4_REVENUE_INVALID"
    LAG4_REVENUE_NONPOSITIVE = "LAG4_REVENUE_NONPOSITIVE"
    LAG4_EBIT_MISSING = "LAG4_EBIT_MISSING"
    LAG4_EBIT_INVALID = "LAG4_EBIT_INVALID"
    REQUIRED_METRICS_MISSING = "REQUIRED_METRICS_MISSING"


class StateMachineReason(str, Enum):
    LEADING_UNCLASSIFIED = "LEADING_UNCLASSIFIED"
    UNCLASSIFIED_CLEARED_CANDIDATE = "UNCLASSIFIED_CLEARED_CANDIDATE"
    INITIAL_STATE_CONFIRMED = "INITIAL_STATE_CONFIRMED"
    CONFIRMED_STATE_REPEATED = "CONFIRMED_STATE_REPEATED"
    CANDIDATE_STARTED = "CANDIDATE_STARTED"
    CANDIDATE_REPLACED = "CANDIDATE_REPLACED"
    CANDIDATE_CONFIRMED = "CANDIDATE_CONFIRMED"
    DISTRESSED_IMMEDIATE_ENTRY = "DISTRESSED_IMMEDIATE_ENTRY"


MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "ttm_model_version": TTM_MODEL_VERSION,
    "economic_states": [state.value for state in LifecycleState if state is not LifecycleState.UNCLASSIFIED],
    "technical_state": LifecycleState.UNCLASSIFIED.value,
    "startup_profiles": [profile.value for profile in StartupProfile],
    "status": {"ready": LifecycleStatus.READY.value, "not_ready": LifecycleStatus.NOT_READY.value},
    "reason_codes": [reason.value for reason in LifecycleReason],
    "state_machine_reason_codes": [reason.value for reason in StateMachineReason],
    "priority": [
        "PRE_REVENUE_STARTUP",
        "DISTRESSED",
        "REVENUE_GENERATING_STARTUP",
        "SCALING",
        "GROWTH",
        "MATURE",
        "DECLINING",
        "STRUGGLING",
        "TRANSITION",
    ],
    "thresholds": {
        "distressed": {"ebit_margin_lt": -0.20, "fcf_margin_lt": -0.20},
        "startup": {"growth_gt": 0.30, "ebit_margin_lt": -0.05, "fcf_margin_lt": 0.0},
        "scaling": {"growth_gt": 0.10, "ebit_margin_gte": 0.0, "margin_direction_gt": 0.0},
        "growth": {"growth_gt": 0.20, "ebit_margin_lt": 0.10, "margin_direction_gte": -0.05},
        "mature": {"ebit_margin_gte": 0.15, "fcf_margin_gte": 0.05, "growth_gte": -0.05, "margin_direction_gte": -0.05},
        "declining": {"growth_lt": -0.05, "margin_direction_lt": -0.05},
        "struggling": {"ebit_margin_lt_or_fcf_margin_lt": 0.0, "growth_gte": -0.05, "margin_direction_gte": -0.05},
    },
    "pre_revenue": {
        "quarter_count": 4,
        "all_quarter_revenues_exactly_zero": True,
        "ttm_ebit_lt": 0.0,
        "ttm_fcf_lt": 0.0,
    },
    "required_metrics": {
        "PRE_REVENUE_STARTUP": ["four_observed_zero_revenue_quarters", "current_ttm_ebit", "current_ttm_fcf"],
        "DISTRESSED": ["positive_current_ttm_revenue", "current_ttm_ebit", "current_ttm_fcf"],
        "REVENUE_GENERATING_STARTUP": ["G", "M", "F"],
        "SCALING": ["G", "M", "DeltaM"],
        "GROWTH": ["G", "M", "DeltaM"],
        "MATURE": ["G", "M", "DeltaM", "F"],
        "DECLINING": ["G", "M", "DeltaM"],
        "STRUGGLING": ["G", "M", "DeltaM", "F"],
        "TRANSITION": ["G", "M", "DeltaM", "F"],
    },
    "numeric_semantics": {
        "comparison_arithmetic": "DECIMAL_FROM_SOURCE_NUMBER_STRING",
        "classification_rounding": None,
        "public_metric_type": "FLOAT_UNROUNDED",
    },
    "state_machine": {
        "ordinary_confirmation_count": 2,
        "distressed_entry": "IMMEDIATE",
        "distressed_exit": "TWO_IDENTICAL_NON_DISTRESSED",
        "unclassified": "NOT_READY_CLEAR_CANDIDATE_PRESERVE_LAST_CONFIRMED_ONLY_AS_HISTORY",
        "forced_path": False,
    },
    "excluded_inputs": ["score", "price", "returns", "valuation", "leverage", "debt", "dilution", "sector_rank", "percentiles", "future_outcomes"],
}
MODEL_FINGERPRINT = hashlib.sha256(
    json.dumps(MODEL_CONTRACT, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class LifecycleObservation:
    company_id: int
    endpoint_quarter_id: int
    endpoint_fiscal_year: int
    endpoint_fiscal_quarter: str
    period_end: str
    source_available_date: str | None
    core_ttm_ready: bool
    ttm_revenue: float | None
    ttm_ebit: float | None
    ttm_free_cashflow: float | None
    lag4_ttm_revenue: float | None = None
    lag4_ttm_ebit: float | None = None
    lag4_chain_valid: bool = False
    input_quarter_revenues: tuple[float | None, ...] = ()
    security_id: int | None = None
    source_data_version: str | None = None
    ttm_model_version: str = TTM_MODEL_VERSION


@dataclass(frozen=True)
class LifecycleMetrics:
    revenue_growth_yoy_ttm: float | None
    ebit_margin_ttm: float | None
    ebit_margin_direction: float | None
    fcf_margin_ttm: float | None


@dataclass(frozen=True)
class RawLifecycleResult:
    observation: LifecycleObservation
    raw_state: LifecycleState
    lifecycle_status: LifecycleStatus
    reason_code: LifecycleReason
    metrics: LifecycleMetrics
    startup_profile: StartupProfile | None = None
    missing_inputs: tuple[str, ...] = ()
    model_version: str = MODEL_VERSION
    model_fingerprint: str = MODEL_FINGERPRINT


@dataclass(frozen=True)
class LifecycleMachineState:
    last_confirmed_state: LifecycleState | None = None
    last_confirmed_startup_profile: StartupProfile | None = None
    candidate_state: LifecycleState | None = None
    candidate_startup_profile: StartupProfile | None = None
    candidate_count: int = 0


@dataclass(frozen=True)
class StateMachineResult:
    raw_result: RawLifecycleResult
    final_state: LifecycleState | None
    final_startup_profile: StartupProfile | None
    last_confirmed_state: LifecycleState | None
    candidate_state: LifecycleState | None
    candidate_count: int
    lifecycle_status: LifecycleStatus
    transition_reason: StateMachineReason
    model_version: str = MODEL_VERSION
    model_fingerprint: str = MODEL_FINGERPRINT


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _empty_metrics() -> LifecycleMetrics:
    return LifecycleMetrics(None, None, None, None)


def _unclassified(
    observation: LifecycleObservation,
    reason: LifecycleReason,
    metrics: LifecycleMetrics,
    *missing_inputs: str,
) -> RawLifecycleResult:
    return RawLifecycleResult(
        observation=observation,
        raw_state=LifecycleState.UNCLASSIFIED,
        lifecycle_status=LifecycleStatus.NOT_READY,
        reason_code=reason,
        metrics=metrics,
        missing_inputs=tuple(sorted(set(missing_inputs))),
    )


def _classified(
    observation: LifecycleObservation,
    state: LifecycleState,
    reason: LifecycleReason,
    metrics: LifecycleMetrics,
    startup_profile: StartupProfile | None = None,
) -> RawLifecycleResult:
    return RawLifecycleResult(
        observation=observation,
        raw_state=state,
        lifecycle_status=LifecycleStatus.READY,
        reason_code=reason,
        metrics=metrics,
        startup_profile=startup_profile,
    )


def _availability_reason(value: str | None) -> LifecycleReason | None:
    if value is None or not value.strip():
        return LifecycleReason.SOURCE_AVAILABILITY_DATE_MISSING
    try:
        date.fromisoformat(value)
    except ValueError:
        return LifecycleReason.SOURCE_AVAILABILITY_DATE_INVALID
    return None


def _classify_zero_revenue(observation: LifecycleObservation) -> RawLifecycleResult:
    metrics = _empty_metrics()
    revenues = observation.input_quarter_revenues
    if len(revenues) != 4:
        return _unclassified(
            observation,
            LifecycleReason.PRE_REVENUE_QUARTER_COUNT_INVALID,
            metrics,
            "input_quarter_revenues",
        )
    if any(value is None for value in revenues):
        return _unclassified(
            observation,
            LifecycleReason.PRE_REVENUE_QUARTER_REVENUE_MISSING,
            metrics,
            "input_quarter_revenues",
        )
    if any(not _finite(value) for value in revenues):
        return _unclassified(
            observation,
            LifecycleReason.PRE_REVENUE_QUARTER_REVENUE_INVALID,
            metrics,
            "input_quarter_revenues",
        )
    if observation.ttm_ebit is None:
        return _unclassified(observation, LifecycleReason.CURRENT_EBIT_MISSING, metrics, "ttm_ebit")
    if not _finite(observation.ttm_ebit):
        return _unclassified(observation, LifecycleReason.CURRENT_EBIT_INVALID, metrics, "ttm_ebit")
    if observation.ttm_free_cashflow is None:
        return _unclassified(observation, LifecycleReason.CURRENT_FCF_MISSING, metrics, "ttm_free_cashflow")
    if not _finite(observation.ttm_free_cashflow):
        return _unclassified(observation, LifecycleReason.CURRENT_FCF_INVALID, metrics, "ttm_free_cashflow")
    if (
        all(float(value) == 0.0 for value in revenues)
        and float(observation.ttm_ebit) < 0.0
        and float(observation.ttm_free_cashflow) < 0.0
    ):
        return _classified(
            observation,
            LifecycleState.STARTUP,
            LifecycleReason.CLASSIFIED_PRE_REVENUE_STARTUP,
            metrics,
            StartupProfile.PRE_REVENUE,
        )
    return _unclassified(
        observation,
        LifecycleReason.ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET,
        metrics,
        "pre_revenue_conditions",
    )


def classify_raw_state(observation: LifecycleObservation) -> RawLifecycleResult:
    """Classify one source-provenanced TTM observation without mutable state."""
    if observation.ttm_model_version != TTM_MODEL_VERSION:
        return _unclassified(
            observation,
            LifecycleReason.TTM_MODEL_VERSION_UNSUPPORTED,
            _empty_metrics(),
            "ttm_model_version",
        )
    availability_reason = _availability_reason(observation.source_available_date)
    if availability_reason is not None:
        return _unclassified(observation, availability_reason, _empty_metrics(), "source_available_date")
    if not observation.core_ttm_ready:
        return _unclassified(observation, LifecycleReason.TTM_NOT_READY, _empty_metrics(), "core_ttm_ready")
    if observation.ttm_revenue is None:
        return _unclassified(observation, LifecycleReason.CURRENT_REVENUE_MISSING, _empty_metrics(), "ttm_revenue")
    if not _finite(observation.ttm_revenue):
        return _unclassified(observation, LifecycleReason.CURRENT_REVENUE_INVALID, _empty_metrics(), "ttm_revenue")

    revenue = float(observation.ttm_revenue)
    revenue_decimal = _decimal(revenue)
    if revenue_decimal < 0:
        return _unclassified(observation, LifecycleReason.CURRENT_REVENUE_NEGATIVE, _empty_metrics(), "ttm_revenue")
    if revenue_decimal == 0:
        return _classify_zero_revenue(observation)
    if observation.ttm_ebit is None:
        return _unclassified(observation, LifecycleReason.CURRENT_EBIT_MISSING, _empty_metrics(), "ttm_ebit")
    if not _finite(observation.ttm_ebit):
        return _unclassified(observation, LifecycleReason.CURRENT_EBIT_INVALID, _empty_metrics(), "ttm_ebit")

    ebit_decimal = _decimal(float(observation.ttm_ebit))
    ebit_margin_decimal = ebit_decimal / revenue_decimal
    ebit_margin = float(ebit_margin_decimal)
    fcf_margin = None
    fcf_problem: tuple[LifecycleReason, str] | None = None
    if observation.ttm_free_cashflow is None:
        fcf_problem = (LifecycleReason.CURRENT_FCF_MISSING, "ttm_free_cashflow")
    elif not _finite(observation.ttm_free_cashflow):
        fcf_problem = (LifecycleReason.CURRENT_FCF_INVALID, "ttm_free_cashflow")
    else:
        fcf_margin_decimal = _decimal(float(observation.ttm_free_cashflow)) / revenue_decimal
        fcf_margin = float(fcf_margin_decimal)

    level_metrics = LifecycleMetrics(None, ebit_margin, None, fcf_margin)
    if fcf_margin is not None and ebit_margin_decimal < Decimal("-0.20") and fcf_margin_decimal < Decimal("-0.20"):
        return _classified(
            observation,
            LifecycleState.DISTRESSED,
            LifecycleReason.CLASSIFIED_DISTRESSED,
            level_metrics,
        )

    history_problem: tuple[LifecycleReason, str] | None = None
    if not observation.lag4_chain_valid:
        history_problem = (LifecycleReason.FISCAL_CHAIN_INVALID, "lag4_chain")
    elif observation.lag4_ttm_revenue is None:
        history_problem = (LifecycleReason.LAG4_REVENUE_MISSING, "lag4_ttm_revenue")
    elif not _finite(observation.lag4_ttm_revenue):
        history_problem = (LifecycleReason.LAG4_REVENUE_INVALID, "lag4_ttm_revenue")
    elif float(observation.lag4_ttm_revenue) <= 0.0:
        history_problem = (LifecycleReason.LAG4_REVENUE_NONPOSITIVE, "lag4_ttm_revenue")

    if history_problem is not None:
        reason, field = history_problem
        return _unclassified(observation, reason, level_metrics, field)

    previous_revenue = float(observation.lag4_ttm_revenue)
    previous_revenue_decimal = _decimal(previous_revenue)
    growth_decimal = revenue_decimal / previous_revenue_decimal - 1
    growth = float(growth_decimal)
    margin_direction = None
    margin_direction_decimal = None
    margin_problem: tuple[LifecycleReason, str] | None = None
    if observation.lag4_ttm_ebit is None:
        margin_problem = (LifecycleReason.LAG4_EBIT_MISSING, "lag4_ttm_ebit")
    elif not _finite(observation.lag4_ttm_ebit):
        margin_problem = (LifecycleReason.LAG4_EBIT_INVALID, "lag4_ttm_ebit")
    else:
        previous_margin_decimal = _decimal(float(observation.lag4_ttm_ebit)) / previous_revenue_decimal
        margin_direction_decimal = ebit_margin_decimal - previous_margin_decimal
        margin_direction = float(margin_direction_decimal)

    metrics = LifecycleMetrics(growth, ebit_margin, margin_direction, fcf_margin)
    if (
        fcf_margin is not None
        and growth_decimal > Decimal("0.30")
        and ebit_margin_decimal < Decimal("-0.05")
        and fcf_margin_decimal < 0
    ):
        return _classified(
            observation,
            LifecycleState.STARTUP,
            LifecycleReason.CLASSIFIED_REVENUE_GENERATING_STARTUP,
            metrics,
            StartupProfile.REVENUE_GENERATING,
        )
    if (
        margin_direction_decimal is not None
        and growth_decimal > Decimal("0.10")
        and ebit_margin_decimal >= 0
        and margin_direction_decimal > 0
    ):
        return _classified(observation, LifecycleState.SCALING, LifecycleReason.CLASSIFIED_SCALING, metrics)
    if (
        margin_direction_decimal is not None
        and growth_decimal > Decimal("0.20")
        and ebit_margin_decimal < Decimal("0.10")
        and margin_direction_decimal >= Decimal("-0.05")
    ):
        return _classified(observation, LifecycleState.GROWTH, LifecycleReason.CLASSIFIED_GROWTH, metrics)
    if (
        margin_direction_decimal is not None
        and fcf_margin is not None
        and ebit_margin_decimal >= Decimal("0.15")
        and fcf_margin_decimal >= Decimal("0.05")
        and growth_decimal >= Decimal("-0.05")
        and margin_direction_decimal >= Decimal("-0.05")
    ):
        return _classified(observation, LifecycleState.MATURE, LifecycleReason.CLASSIFIED_MATURE, metrics)
    if margin_direction_decimal is not None and (
        growth_decimal < Decimal("-0.05") or margin_direction_decimal < Decimal("-0.05")
    ):
        return _classified(observation, LifecycleState.DECLINING, LifecycleReason.CLASSIFIED_DECLINING, metrics)
    if (
        margin_direction_decimal is not None
        and fcf_margin is not None
        and (ebit_margin_decimal < 0 or fcf_margin_decimal < 0)
        and growth_decimal >= Decimal("-0.05")
        and margin_direction_decimal >= Decimal("-0.05")
    ):
        return _classified(observation, LifecycleState.STRUGGLING, LifecycleReason.CLASSIFIED_STRUGGLING, metrics)
    if margin_direction_decimal is not None and fcf_margin is not None:
        return _classified(observation, LifecycleState.TRANSITION, LifecycleReason.CLASSIFIED_TRANSITION, metrics)

    missing: list[str] = []
    problems: list[tuple[LifecycleReason, str]] = []
    if margin_problem is not None:
        problems.append(margin_problem)
        missing.append(margin_problem[1])
    if fcf_problem is not None:
        problems.append(fcf_problem)
        missing.append(fcf_problem[1])
    if problems:
        return _unclassified(observation, problems[0][0], metrics, *missing)
    return _unclassified(observation, LifecycleReason.REQUIRED_METRICS_MISSING, metrics, "lifecycle_metrics")


def advance_state_machine(
    state: LifecycleMachineState,
    raw_result: RawLifecycleResult,
) -> tuple[LifecycleMachineState, StateMachineResult]:
    """Advance one immutable state-machine step."""
    if raw_result.model_version != MODEL_VERSION or raw_result.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("LIFECYCLE_MODEL_IDENTITY_MISMATCH")
    if (
        raw_result.raw_state is LifecycleState.UNCLASSIFIED
        and raw_result.lifecycle_status is not LifecycleStatus.NOT_READY
    ) or (
        raw_result.raw_state is not LifecycleState.UNCLASSIFIED
        and raw_result.lifecycle_status is not LifecycleStatus.READY
    ):
        raise ValueError("LIFECYCLE_RAW_RESULT_STATUS_MISMATCH")

    if raw_result.raw_state is LifecycleState.UNCLASSIFIED:
        next_state = LifecycleMachineState(
            last_confirmed_state=state.last_confirmed_state,
            last_confirmed_startup_profile=state.last_confirmed_startup_profile,
        )
        reason = (
            StateMachineReason.LEADING_UNCLASSIFIED
            if state.last_confirmed_state is None
            else StateMachineReason.UNCLASSIFIED_CLEARED_CANDIDATE
        )
        return next_state, StateMachineResult(
            raw_result=raw_result,
            final_state=None,
            final_startup_profile=None,
            last_confirmed_state=next_state.last_confirmed_state,
            candidate_state=None,
            candidate_count=0,
            lifecycle_status=LifecycleStatus.NOT_READY,
            transition_reason=reason,
        )

    raw_state = raw_result.raw_state
    raw_profile = raw_result.startup_profile if raw_state is LifecycleState.STARTUP else None
    if state.last_confirmed_state is None:
        next_state = LifecycleMachineState(raw_state, raw_profile)
        reason = StateMachineReason.INITIAL_STATE_CONFIRMED
    elif raw_state is LifecycleState.DISTRESSED:
        next_state = LifecycleMachineState(LifecycleState.DISTRESSED)
        reason = StateMachineReason.DISTRESSED_IMMEDIATE_ENTRY
    elif raw_state is state.last_confirmed_state:
        confirmed_profile = raw_profile if raw_state is LifecycleState.STARTUP else state.last_confirmed_startup_profile
        next_state = LifecycleMachineState(raw_state, confirmed_profile)
        reason = StateMachineReason.CONFIRMED_STATE_REPEATED
    elif raw_state is state.candidate_state:
        count = state.candidate_count + 1
        if count >= 2:
            next_state = LifecycleMachineState(raw_state, raw_profile)
            reason = StateMachineReason.CANDIDATE_CONFIRMED
        else:
            next_state = LifecycleMachineState(
                state.last_confirmed_state,
                state.last_confirmed_startup_profile,
                raw_state,
                raw_profile,
                count,
            )
            reason = StateMachineReason.CANDIDATE_STARTED
    else:
        next_state = LifecycleMachineState(
            state.last_confirmed_state,
            state.last_confirmed_startup_profile,
            raw_state,
            raw_profile,
            1,
        )
        reason = StateMachineReason.CANDIDATE_REPLACED if state.candidate_state is not None else StateMachineReason.CANDIDATE_STARTED

    return next_state, StateMachineResult(
        raw_result=raw_result,
        final_state=next_state.last_confirmed_state,
        final_startup_profile=next_state.last_confirmed_startup_profile,
        last_confirmed_state=next_state.last_confirmed_state,
        candidate_state=next_state.candidate_state,
        candidate_count=next_state.candidate_count,
        lifecycle_status=LifecycleStatus.READY,
        transition_reason=reason,
    )


def replay_state_machine(raw_results: Sequence[RawLifecycleResult]) -> tuple[StateMachineResult, ...]:
    """Replay a caller-provided chronological source sequence deterministically."""
    state = LifecycleMachineState()
    output: list[StateMachineResult] = []
    previous_date: date | None = None
    for raw_result in raw_results:
        available = raw_result.observation.source_available_date
        if available is None:
            raise ValueError("LIFECYCLE_REPLAY_AVAILABILITY_DATE_REQUIRED")
        try:
            current_date = date.fromisoformat(available)
        except ValueError as exc:
            raise ValueError("LIFECYCLE_REPLAY_AVAILABILITY_DATE_INVALID") from exc
        if previous_date is not None and current_date < previous_date:
            raise ValueError("LIFECYCLE_REPLAY_SEQUENCE_NOT_CHRONOLOGICAL")
        state, result = advance_state_machine(state, raw_result)
        output.append(result)
        previous_date = current_date
    return tuple(output)
