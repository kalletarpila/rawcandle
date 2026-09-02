from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from rawcandle.fundamentals.delta.engine import (
    DeltaStatus,
    FiscalObservation,
    HORIZON_LAGS,
    Horizon,
    RECONCILIATION_TOLERANCE,
    build_fiscal_index,
    fingerprint,
    resolve_horizon,
)


LIFECYCLE_CONTEXT_VERSION = "CURRENTLY_REVISED_LIFECYCLE_CHANGE_CONTEXT_V1"
VALUATION_DIAGNOSTIC_VERSION = "CURRENTLY_REVISED_FILING_DATE_VALUATION_CHANGE_V1"
LIFECYCLE_CONTEXT_FINGERPRINT = fingerprint({
    "version": LIFECYCLE_CONTEXT_VERSION,
    "horizons": {h.value: HORIZON_LAGS[h] for h in Horizon},
    "ordinal_arithmetic": False,
    "history": "REVISED_HISTORY",
})
VALUATION_DIAGNOSTIC_FINGERPRINT = fingerprint({
    "version": VALUATION_DIAGNOSTIC_VERSION,
    "horizons": {h.value: HORIZON_LAGS[h] for h in Horizon},
    "required_status": "VALUATION_FULL",
    "components": ("EBIT", "FCF", "COMMON_EARNINGS"),
    "reconciliation_tolerance": RECONCILIATION_TOLERANCE,
    "current_day_valuation": False,
    "history": "REVISED_HISTORY",
})


def _finite(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class LifecycleObservation:
    fiscal: FiscalObservation
    lifecycle_result_id: int
    model_fingerprint: str
    lifecycle_status: str
    raw_state: str
    final_state: str | None
    last_confirmed_state: str | None
    candidate_state: str | None
    candidate_count: int


@dataclass(frozen=True)
class LifecycleHorizonContext:
    horizon: Horizon
    status: DeltaStatus
    reason_code: str
    prior_observation_id: str | None
    prior_final_state: str | None
    state_changed: bool | None


@dataclass(frozen=True)
class LifecycleChangeContext:
    context_version: str
    context_fingerprint: str
    source_fingerprint: str
    company_id: int
    current_observation_id: str
    current_final_state: str | None
    current_raw_state: str
    lifecycle_status: str
    last_confirmed_state: str | None
    candidate_state: str | None
    candidate_count: int
    latest_confirmed_transition_observation_id: str | None
    latest_confirmed_transition_fiscal_sequence: int | None
    consecutive_classified_observations: int
    horizons: tuple[LifecycleHorizonContext, ...]
    result_fingerprint: str


def calculate_lifecycle_context(
    current: LifecycleObservation,
    company_history: Sequence[LifecycleObservation],
    *,
    source_fingerprint: str,
) -> LifecycleChangeContext:
    ordered = sorted(company_history, key=lambda row: row.fiscal.fiscal_sequence)
    fiscal_index = build_fiscal_index([row.fiscal for row in ordered])
    by_sequence = {row.fiscal.fiscal_sequence: row for row in ordered}
    horizons = []
    for horizon in Horizon:
        resolution = resolve_horizon(current.fiscal, fiscal_index[current.fiscal.company_id], horizon)
        prior = by_sequence.get(current.fiscal.fiscal_sequence - HORIZON_LAGS[horizon])
        status, reason = resolution.status, resolution.reason_code
        changed = None
        if status == DeltaStatus.READY:
            if current.lifecycle_status != "LIFECYCLE_READY":
                status, reason = DeltaStatus.SOURCE_NOT_READY, "CURRENT_LIFECYCLE_NOT_READY"
            elif prior is None or prior.lifecycle_status != "LIFECYCLE_READY" or prior.final_state is None:
                status, reason = DeltaStatus.ENDPOINT_NOT_COMPARABLE, "PRIOR_LIFECYCLE_NOT_READY"
            elif current.final_state is None:
                status, reason = DeltaStatus.SOURCE_NOT_READY, "CURRENT_FINAL_STATE_UNAVAILABLE"
            else:
                changed = current.final_state != prior.final_state
        horizons.append(LifecycleHorizonContext(
            horizon, status, reason, prior.fiscal.observation_id if prior else None,
            prior.final_state if prior else None, changed,
        ))
    up_to_current = [row for row in ordered if row.fiscal.fiscal_sequence <= current.fiscal.fiscal_sequence]
    transitions = [
        later for earlier, later in zip(up_to_current, up_to_current[1:])
        if earlier.lifecycle_status == later.lifecycle_status == "LIFECYCLE_READY"
        and earlier.final_state is not None and later.final_state is not None
        and earlier.final_state != later.final_state
    ]
    streak = 0
    if current.lifecycle_status == "LIFECYCLE_READY" and current.final_state is not None:
        for row in reversed(up_to_current):
            if row.lifecycle_status == "LIFECYCLE_READY" and row.final_state == current.final_state:
                streak += 1
            else:
                break
    payload = {
        "context_version": LIFECYCLE_CONTEXT_VERSION,
        "context_fingerprint": LIFECYCLE_CONTEXT_FINGERPRINT,
        "source_fingerprint": source_fingerprint,
        "company_id": current.fiscal.company_id,
        "current_observation_id": current.fiscal.observation_id,
        "current_final_state": current.final_state,
        "current_raw_state": current.raw_state,
        "lifecycle_status": current.lifecycle_status,
        "last_confirmed_state": current.last_confirmed_state,
        "candidate_state": current.candidate_state,
        "candidate_count": current.candidate_count,
        "latest_confirmed_transition_observation_id": transitions[-1].fiscal.observation_id if transitions else None,
        "latest_confirmed_transition_fiscal_sequence": transitions[-1].fiscal.fiscal_sequence if transitions else None,
        "consecutive_classified_observations": streak,
        "horizons": tuple(horizons),
    }
    return LifecycleChangeContext(**payload, result_fingerprint=fingerprint({**payload, "horizons": [asdict(row) for row in horizons]}))


@dataclass(frozen=True)
class ValuationObservation:
    fiscal: FiscalObservation
    valuation_result_id: int
    model_fingerprint: str
    valuation_status: str
    total_score: Any
    ebit_points: Any
    fcf_points: Any
    earnings_points: Any
    price_date: str | None
    selected_price: Any
    ebit_yield: Any
    fcf_yield: Any
    earnings_yield: Any
    market_cap: Any
    enterprise_value: Any
    result_fingerprint: str


@dataclass(frozen=True)
class ValuationHorizonDiagnostic:
    horizon: Horizon
    status: DeltaStatus
    reason_code: str
    prior_observation_id: str | None
    prior_result_id: int | None
    current_score: float | None
    prior_score: float | None
    score_change: float | None
    ebit_points_change: float | None
    fcf_points_change: float | None
    earnings_points_change: float | None
    reconciliation_error: float | None
    current_price_date: str | None
    prior_price_date: str | None
    current_price: float | None
    prior_price: float | None
    current_ebit_yield: float | None
    prior_ebit_yield: float | None
    current_fcf_yield: float | None
    prior_fcf_yield: float | None
    current_earnings_yield: float | None
    prior_earnings_yield: float | None
    current_market_cap: float | None
    prior_market_cap: float | None
    current_enterprise_value: float | None
    prior_enterprise_value: float | None


@dataclass(frozen=True)
class ValuationChangeDiagnostic:
    diagnostic_version: str
    diagnostic_fingerprint: str
    source_fingerprint: str
    company_id: int
    current_observation_id: str
    current_result_id: int
    valuation_model_fingerprint: str
    horizons: tuple[ValuationHorizonDiagnostic, ...]
    result_fingerprint: str


def calculate_valuation_diagnostic(
    current: ValuationObservation,
    company_history: Sequence[ValuationObservation],
    *,
    source_fingerprint: str,
) -> ValuationChangeDiagnostic:
    ordered = sorted(company_history, key=lambda row: row.fiscal.fiscal_sequence)
    fiscal_index = build_fiscal_index([row.fiscal for row in ordered])
    by_sequence = {row.fiscal.fiscal_sequence: row for row in ordered}
    horizons = []
    for horizon in Horizon:
        resolution = resolve_horizon(current.fiscal, fiscal_index[current.fiscal.company_id], horizon)
        prior = by_sequence.get(current.fiscal.fiscal_sequence - HORIZON_LAGS[horizon])
        status, reason = resolution.status, resolution.reason_code
        values = {field: None for field in (
            "score_change", "ebit_points_change", "fcf_points_change",
            "earnings_points_change", "reconciliation_error",
        )}
        if status == DeltaStatus.READY and prior is not None:
            if current.model_fingerprint != prior.model_fingerprint:
                status, reason = DeltaStatus.MODEL_MISMATCH, "VALUATION_MODEL_MISMATCH"
            elif current.valuation_status != "VALUATION_FULL" or prior.valuation_status != "VALUATION_FULL":
                status, reason = DeltaStatus.ENDPOINT_NOT_COMPARABLE, "VALUATION_FULL_REQUIRED"
            elif not current.price_date or not prior.price_date or current.price_date > current.fiscal.available_date or prior.price_date > prior.fiscal.available_date:
                status, reason = DeltaStatus.AVAILABILITY_CHRONOLOGY_INVALID, "PRICE_SOURCE_CHRONOLOGY_INVALID"
            elif not all(_finite(getattr(row, field)) for row in (current, prior) for field in (
                "total_score", "ebit_points", "fcf_points", "earnings_points",
                "selected_price", "ebit_yield", "fcf_yield", "earnings_yield",
                "market_cap", "enterprise_value",
            )):
                status, reason = DeltaStatus.INVALID_VALUE, "VALUATION_VALUE_INVALID"
            else:
                values["score_change"] = float(current.total_score) - float(prior.total_score)
                values["ebit_points_change"] = float(current.ebit_points) - float(prior.ebit_points)
                values["fcf_points_change"] = float(current.fcf_points) - float(prior.fcf_points)
                values["earnings_points_change"] = float(current.earnings_points) - float(prior.earnings_points)
                component_sum = values["ebit_points_change"] + values["fcf_points_change"] + values["earnings_points_change"]
                values["reconciliation_error"] = component_sum - values["score_change"]
                if not math.isclose(component_sum, values["score_change"], abs_tol=RECONCILIATION_TOLERANCE, rel_tol=0.0):
                    status, reason = DeltaStatus.ENDPOINT_NOT_COMPARABLE, "VALUATION_RECONCILIATION_FAILED"
                    values = {key: None for key in values}
        def number(row: ValuationObservation | None, field: str) -> float | None:
            return float(getattr(row, field)) if row is not None and _finite(getattr(row, field)) else None
        horizons.append(ValuationHorizonDiagnostic(
            horizon=horizon, status=status, reason_code=reason,
            prior_observation_id=prior.fiscal.observation_id if prior else None,
            prior_result_id=prior.valuation_result_id if prior else None,
            current_score=number(current, "total_score"), prior_score=number(prior, "total_score"),
            **values,
            current_price_date=current.price_date, prior_price_date=prior.price_date if prior else None,
            current_price=number(current, "selected_price"), prior_price=number(prior, "selected_price"),
            current_ebit_yield=number(current, "ebit_yield"), prior_ebit_yield=number(prior, "ebit_yield"),
            current_fcf_yield=number(current, "fcf_yield"), prior_fcf_yield=number(prior, "fcf_yield"),
            current_earnings_yield=number(current, "earnings_yield"), prior_earnings_yield=number(prior, "earnings_yield"),
            current_market_cap=number(current, "market_cap"), prior_market_cap=number(prior, "market_cap"),
            current_enterprise_value=number(current, "enterprise_value"), prior_enterprise_value=number(prior, "enterprise_value"),
        ))
    payload = {
        "diagnostic_version": VALUATION_DIAGNOSTIC_VERSION,
        "diagnostic_fingerprint": VALUATION_DIAGNOSTIC_FINGERPRINT,
        "source_fingerprint": source_fingerprint,
        "company_id": current.fiscal.company_id,
        "current_observation_id": current.fiscal.observation_id,
        "current_result_id": current.valuation_result_id,
        "valuation_model_fingerprint": current.model_fingerprint,
        "horizons": tuple(horizons),
    }
    return ValuationChangeDiagnostic(**payload, result_fingerprint=fingerprint({**payload, "horizons": [asdict(row) for row in horizons]}))
