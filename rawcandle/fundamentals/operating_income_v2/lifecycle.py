from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from rawcandle.fundamentals.lifecycle import engine as v1

from .contract import LIFECYCLE_MODEL_VERSION, TTM_MODEL_VERSION, model_fingerprint


LifecycleState = v1.LifecycleState
LifecycleStatus = v1.LifecycleStatus
StartupProfile = v1.StartupProfile
LifecycleReason = Enum(
    "LifecycleReason",
    {item.name: item.value.replace("EBIT", "OPERATING_INCOME") for item in v1.LifecycleReason},
    type=str,
)
StateMachineReason = v1.StateMachineReason
LifecycleMachineState = v1.LifecycleMachineState

MODEL_VERSION = LIFECYCLE_MODEL_VERSION
def _operating_semantics(value):
    if isinstance(value, dict):
        return {_operating_semantics(key): _operating_semantics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_operating_semantics(item) for item in value]
    if isinstance(value, str):
        return value.replace("ttm_ebit", "ttm_operating_income").replace("ebit_margin", "operating_margin").replace("EBIT", "OPERATING_INCOME")
    return value


MODEL_CONTRACT = {
    **_operating_semantics(v1.MODEL_CONTRACT),
    "model_version": MODEL_VERSION,
    "ttm_model_version": TTM_MODEL_VERSION,
    "operating_metric": "ttm_operating_income/ttm_revenue",
    "operating_direction": "operating_margin_t-operating_margin_t_minus_4",
    "ebit_fallback": None,
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)


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
    ttm_operating_income: float | None
    ttm_free_cashflow: float | None
    lag4_ttm_revenue: float | None = None
    lag4_ttm_operating_income: float | None = None
    lag4_chain_valid: bool = False
    input_quarter_revenues: tuple[float | None, ...] = ()
    security_id: int | None = None
    source_data_version: str | None = None
    ttm_model_version: str = TTM_MODEL_VERSION


@dataclass(frozen=True)
class LifecycleMetrics:
    revenue_growth_yoy_ttm: float | None
    operating_margin_ttm: float | None
    operating_margin_direction: float | None
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


def _v1_observation(value: LifecycleObservation) -> v1.LifecycleObservation:
    if value.ttm_model_version != TTM_MODEL_VERSION:
        raise ValueError("OPERATING_INCOME_V2_TTM_MODEL_MISMATCH")
    return v1.LifecycleObservation(
        company_id=value.company_id,
        security_id=value.security_id,
        endpoint_quarter_id=value.endpoint_quarter_id,
        endpoint_fiscal_year=value.endpoint_fiscal_year,
        endpoint_fiscal_quarter=value.endpoint_fiscal_quarter,
        period_end=value.period_end,
        source_available_date=value.source_available_date,
        core_ttm_ready=value.core_ttm_ready,
        ttm_revenue=value.ttm_revenue,
        ttm_ebit=value.ttm_operating_income,
        ttm_free_cashflow=value.ttm_free_cashflow,
        lag4_ttm_revenue=value.lag4_ttm_revenue,
        lag4_ttm_ebit=value.lag4_ttm_operating_income,
        lag4_chain_valid=value.lag4_chain_valid,
        input_quarter_revenues=value.input_quarter_revenues,
        source_data_version=value.source_data_version,
        ttm_model_version=v1.TTM_MODEL_VERSION,
    )


def _from_v1(raw: v1.RawLifecycleResult, observation: LifecycleObservation) -> RawLifecycleResult:
    metrics = LifecycleMetrics(
        raw.metrics.revenue_growth_yoy_ttm,
        raw.metrics.ebit_margin_ttm,
        raw.metrics.ebit_margin_direction,
        raw.metrics.fcf_margin_ttm,
    )
    missing = tuple(name.replace("lag4_ttm_ebit", "lag4_ttm_operating_income").replace("ttm_ebit", "ttm_operating_income") for name in raw.missing_inputs)
    return RawLifecycleResult(
        observation, raw.raw_state, raw.lifecycle_status, LifecycleReason[raw.reason_code.name],
        metrics, raw.startup_profile, missing,
    )


def _to_v1(raw: RawLifecycleResult) -> v1.RawLifecycleResult:
    if raw.model_version != MODEL_VERSION or raw.model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("OPERATING_INCOME_V2_LIFECYCLE_MODEL_MISMATCH")
    return v1.RawLifecycleResult(
        _v1_observation(raw.observation), raw.raw_state, raw.lifecycle_status,
        v1.LifecycleReason[raw.reason_code.name],
        v1.LifecycleMetrics(
            raw.metrics.revenue_growth_yoy_ttm,
            raw.metrics.operating_margin_ttm,
            raw.metrics.operating_margin_direction,
            raw.metrics.fcf_margin_ttm,
        ),
        raw.startup_profile,
        tuple(name.replace("lag4_ttm_operating_income", "lag4_ttm_ebit").replace("ttm_operating_income", "ttm_ebit") for name in raw.missing_inputs),
    )


def classify_raw_state(observation: LifecycleObservation) -> RawLifecycleResult:
    return _from_v1(v1.classify_raw_state(_v1_observation(observation)), observation)


def advance_state_machine(
    state: LifecycleMachineState,
    raw_result: RawLifecycleResult,
) -> tuple[LifecycleMachineState, StateMachineResult]:
    next_state, result = v1.advance_state_machine(state, _to_v1(raw_result))
    return next_state, StateMachineResult(
        raw_result, result.final_state, result.final_startup_profile,
        result.last_confirmed_state, result.candidate_state,
        result.candidate_count, result.lifecycle_status,
        result.transition_reason,
    )


def replay_state_machine(raw_results: Sequence[RawLifecycleResult]) -> tuple[StateMachineResult, ...]:
    state = LifecycleMachineState()
    output = []
    for raw in raw_results:
        state, result = advance_state_machine(state, raw)
        output.append(result)
    return tuple(output)
