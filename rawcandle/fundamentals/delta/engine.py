from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score.engine import (
    COMPONENTS,
    MODEL_CONTRACT as SCORE_MODEL_CONTRACT,
    MODEL_FINGERPRINT as SCORE_MODEL_FINGERPRINT,
    MODEL_VERSION as SCORE_MODEL_VERSION,
)


MODEL_VERSION = "CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V1"
SEMANTIC_MODE = "CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA"
RECONCILIATION_TOLERANCE = 1e-9
COMPONENT_MAXIMA = {
    name: float(contract["maximum"])
    for name, contract in SCORE_MODEL_CONTRACT["components"].items()
}


class Horizon(str, Enum):
    QOQ = "QOQ"
    TWO_QUARTER = "TWO_QUARTER"
    YOY = "YOY"


HORIZON_LAGS = {Horizon.QOQ: 1, Horizon.TWO_QUARTER: 2, Horizon.YOY: 4}


class DeltaStatus(str, Enum):
    READY = "DELTA_READY"
    SOURCE_NOT_READY = "DELTA_SOURCE_NOT_READY"
    LAG_ENDPOINT_MISSING = "DELTA_LAG_ENDPOINT_MISSING"
    INVALID_FISCAL_CHAIN = "DELTA_INVALID_FISCAL_CHAIN"
    MODEL_MISMATCH = "DELTA_MODEL_MISMATCH"
    ENDPOINT_NOT_COMPARABLE = "DELTA_ENDPOINT_NOT_COMPARABLE"
    COMPONENT_NOT_COMPARABLE = "DELTA_COMPONENT_NOT_COMPARABLE"
    INVALID_VALUE = "DELTA_INVALID_VALUE"
    AVAILABILITY_CHRONOLOGY_INVALID = "DELTA_AVAILABILITY_CHRONOLOGY_INVALID"


class ChainReason(str, Enum):
    READY = "FISCAL_CHAIN_READY"
    PREVIOUS_QUARTER_MISSING = "PREVIOUS_QUARTER_MISSING"
    LAG2_MISSING = "LAG2_MISSING"
    LAG4_MISSING = "LAG4_MISSING"
    INTERMEDIATE_FISCAL_OBSERVATION_MISSING = "INTERMEDIATE_FISCAL_OBSERVATION_MISSING"
    INVALID_FISCAL_TRANSITION = "INVALID_FISCAL_TRANSITION"
    DUPLICATE_FISCAL_IDENTITY = "DUPLICATE_FISCAL_IDENTITY"
    SOURCE_CHRONOLOGY_INVALID = "SOURCE_CHRONOLOGY_INVALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "semantic_mode": SEMANTIC_MODE,
    "source_score_model_version": SCORE_MODEL_VERSION,
    "source_score_model_fingerprint": SCORE_MODEL_FINGERPRINT,
    "horizons": {horizon.value: HORIZON_LAGS[horizon] for horizon in Horizon},
    "complete_chain": {horizon.value: HORIZON_LAGS[horizon] + 1 for horizon in Horizon},
    "total_eligibility": "CANDIDATE_A_STRICT_FULL_SCORE",
    "required_score_status": "SCORE_FULL",
    "required_ttm_status": "TTM_READY",
    "components": COMPONENT_MAXIMA,
    "component_independent_readiness": True,
    "imputation": None,
    "reweighting": None,
    "numeric": {
        "boolean_is_number": False,
        "finite_required": True,
        "reconciliation_absolute_tolerance": RECONCILIATION_TOLERANCE,
        "rounding": None,
    },
    "statuses": [status.value for status in DeltaStatus],
    "revised_history": True,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


MODEL_FINGERPRINT = fingerprint(MODEL_CONTRACT)


def fiscal_sequence(fiscal_year: int, fiscal_quarter: str) -> int:
    if fiscal_quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError(f"INVALID_FISCAL_QUARTER:{fiscal_quarter}")
    return fiscal_year * 4 + int(fiscal_quarter[1])


def _finite(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class FiscalObservation:
    observation_id: str
    company_id: int
    fiscal_year: int
    fiscal_quarter: str
    fiscal_sequence: int
    period_end: str
    available_date: str


@dataclass(frozen=True)
class ResolvedHorizon:
    horizon: Horizon
    lag: int
    status: DeltaStatus
    reason_code: str
    current_observation_id: str
    prior_observation_id: str | None
    chain_observation_ids: tuple[str, ...]


def build_fiscal_index(observations: Sequence[FiscalObservation]) -> dict[int, dict[int, FiscalObservation]]:
    index: dict[int, dict[int, FiscalObservation]] = {}
    for observation in sorted(
        observations,
        key=lambda row: (row.company_id, row.fiscal_sequence, row.observation_id),
    ):
        expected = fiscal_sequence(observation.fiscal_year, observation.fiscal_quarter)
        if expected != observation.fiscal_sequence:
            raise ValueError(f"INVALID_FISCAL_TRANSITION:{observation.observation_id}")
        company = index.setdefault(observation.company_id, {})
        if observation.fiscal_sequence in company:
            raise ValueError(
                f"DUPLICATE_FISCAL_IDENTITY:{observation.company_id}:{observation.fiscal_sequence}"
            )
        company[observation.fiscal_sequence] = observation
    return index


def resolve_horizon(
    current: FiscalObservation,
    company_observations: Mapping[int, FiscalObservation],
    horizon: Horizon,
) -> ResolvedHorizon:
    lag = HORIZON_LAGS[horizon]
    prior_sequence = current.fiscal_sequence - lag
    missing_reason = {
        Horizon.QOQ: ChainReason.PREVIOUS_QUARTER_MISSING,
        Horizon.TWO_QUARTER: ChainReason.LAG2_MISSING,
        Horizon.YOY: ChainReason.LAG4_MISSING,
    }[horizon]
    prior = company_observations.get(prior_sequence)
    if prior is None:
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.LAG_ENDPOINT_MISSING, missing_reason.value,
            current.observation_id, None, (),
        )
    required = list(range(prior_sequence, current.fiscal_sequence + 1))
    if any(sequence not in company_observations for sequence in required):
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.INVALID_FISCAL_CHAIN,
            ChainReason.INTERMEDIATE_FISCAL_OBSERVATION_MISSING.value,
            current.observation_id, prior.observation_id, (),
        )
    chain = tuple(company_observations[sequence] for sequence in required)
    if any(item.company_id != current.company_id for item in chain):
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.INVALID_FISCAL_CHAIN,
            ChainReason.INVALID_FISCAL_TRANSITION.value,
            current.observation_id, prior.observation_id, (),
        )
    try:
        period_dates = tuple(date.fromisoformat(item.period_end) for item in chain)
        available_dates = tuple(date.fromisoformat(item.available_date) for item in chain)
    except (TypeError, ValueError):
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.AVAILABILITY_CHRONOLOGY_INVALID,
            ChainReason.SOURCE_CHRONOLOGY_INVALID.value,
            current.observation_id, prior.observation_id,
            tuple(item.observation_id for item in chain),
        )
    if any(later <= earlier for earlier, later in zip(period_dates, period_dates[1:])):
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.INVALID_FISCAL_CHAIN,
            ChainReason.INVALID_FISCAL_TRANSITION.value,
            current.observation_id, prior.observation_id,
            tuple(item.observation_id for item in chain),
        )
    if any(later < earlier for earlier, later in zip(available_dates, available_dates[1:])):
        return ResolvedHorizon(
            horizon, lag, DeltaStatus.AVAILABILITY_CHRONOLOGY_INVALID,
            ChainReason.SOURCE_CHRONOLOGY_INVALID.value,
            current.observation_id, prior.observation_id,
            tuple(item.observation_id for item in chain),
        )
    return ResolvedHorizon(
        horizon, lag, DeltaStatus.READY, ChainReason.READY.value,
        current.observation_id, prior.observation_id,
        tuple(item.observation_id for item in chain),
    )


@dataclass(frozen=True)
class ScoreComponentObservation:
    component_name: str
    points: Any
    maximum_points: float
    value_status: str
    imputed: bool = False


@dataclass(frozen=True)
class ScoreObservation:
    fiscal: FiscalObservation
    score_result_id: int
    model_version: str
    model_fingerprint: str
    total_score: Any
    readiness_status: str
    ttm_readiness_status: str
    components: tuple[ScoreComponentObservation, ...]
    reweighted: bool = False


@dataclass(frozen=True)
class ComponentDelta:
    component_name: str
    status: DeltaStatus
    reason_code: str
    current_points: float | None
    prior_points: float | None
    delta_points: float | None
    maximum_points: float


@dataclass(frozen=True)
class HorizonDelta:
    horizon: Horizon
    status: DeltaStatus
    reason_code: str
    current_score: float | None
    prior_score: float | None
    delta_points: float | None
    prior_observation_id: str | None
    prior_score_result_id: int | None
    prior_fiscal_sequence: int | None
    prior_available_date: str | None
    components: tuple[ComponentDelta, ...]
    component_delta_sum: float | None
    reconciliation_error: float | None


@dataclass(frozen=True)
class FundamentalDeltaResult:
    model_version: str
    model_fingerprint: str
    semantic_mode: str
    source_fingerprint: str
    company_id: int
    current_observation_id: str
    current_score_result_id: int
    current_fiscal_sequence: int
    current_fiscal_year: int
    current_fiscal_quarter: str
    current_period_end: str
    current_available_date: str
    current_score: float | None
    current_score_status: str
    score_model_version: str
    score_model_fingerprint: str
    horizons: tuple[HorizonDelta, ...]
    result_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def _component_map(observation: ScoreObservation) -> dict[str, ScoreComponentObservation]:
    output: dict[str, ScoreComponentObservation] = {}
    for component in observation.components:
        if component.component_name in output:
            raise ValueError(f"DUPLICATE_COMPONENT:{observation.score_result_id}:{component.component_name}")
        output[component.component_name] = component
    return output


def _total_reason(observation: ScoreObservation) -> tuple[DeltaStatus, str] | None:
    if observation.model_version != SCORE_MODEL_VERSION or observation.model_fingerprint != SCORE_MODEL_FINGERPRINT:
        return DeltaStatus.MODEL_MISMATCH, "SCORE_MODEL_MISMATCH"
    if observation.readiness_status != "SCORE_FULL" or observation.ttm_readiness_status != "TTM_READY":
        return DeltaStatus.SOURCE_NOT_READY, observation.readiness_status
    if observation.reweighted:
        return DeltaStatus.ENDPOINT_NOT_COMPARABLE, "REWEIGHTED_SCORE"
    if not _finite(observation.total_score):
        return DeltaStatus.INVALID_VALUE, "TOTAL_SCORE_INVALID"
    components = _component_map(observation)
    if set(components) != set(COMPONENTS):
        return DeltaStatus.ENDPOINT_NOT_COMPARABLE, "SEVEN_COMPONENT_CONTRACT_NOT_MET"
    values: list[float] = []
    for name in COMPONENTS:
        component = components[name]
        if component.value_status != "OBSERVED" or component.imputed:
            return DeltaStatus.ENDPOINT_NOT_COMPARABLE, f"COMPONENT_NOT_OBSERVED:{name}"
        if component.maximum_points != COMPONENT_MAXIMA[name]:
            return DeltaStatus.ENDPOINT_NOT_COMPARABLE, f"COMPONENT_MAXIMUM_MISMATCH:{name}"
        if not _finite(component.points):
            return DeltaStatus.INVALID_VALUE, f"COMPONENT_VALUE_INVALID:{name}"
        values.append(float(component.points))
    if not math.isclose(sum(values), float(observation.total_score), abs_tol=RECONCILIATION_TOLERANCE, rel_tol=0.0):
        return DeltaStatus.ENDPOINT_NOT_COMPARABLE, "COMPONENT_SUM_MISMATCH"
    return None


def _component_delta(
    current: ScoreObservation,
    prior: ScoreObservation,
    component_name: str,
) -> ComponentDelta:
    current_component = _component_map(current).get(component_name)
    prior_component = _component_map(prior).get(component_name)
    maximum = COMPONENT_MAXIMA[component_name]
    if (
        current.model_version != SCORE_MODEL_VERSION
        or prior.model_version != SCORE_MODEL_VERSION
        or current.model_fingerprint != SCORE_MODEL_FINGERPRINT
        or prior.model_fingerprint != SCORE_MODEL_FINGERPRINT
    ):
        return ComponentDelta(component_name, DeltaStatus.MODEL_MISMATCH, "SCORE_MODEL_MISMATCH", None, None, None, maximum)
    if current_component is None or prior_component is None:
        return ComponentDelta(component_name, DeltaStatus.COMPONENT_NOT_COMPARABLE, "COMPONENT_MISSING", None, None, None, maximum)
    if current_component.component_name != prior_component.component_name:
        return ComponentDelta(component_name, DeltaStatus.COMPONENT_NOT_COMPARABLE, "COMPONENT_IDENTITY_MISMATCH", None, None, None, maximum)
    if current_component.maximum_points != prior_component.maximum_points or current_component.maximum_points != maximum:
        return ComponentDelta(component_name, DeltaStatus.COMPONENT_NOT_COMPARABLE, "COMPONENT_MAXIMUM_MISMATCH", None, None, None, maximum)
    if current_component.value_status != "OBSERVED" or prior_component.value_status != "OBSERVED" or current_component.imputed or prior_component.imputed:
        return ComponentDelta(component_name, DeltaStatus.COMPONENT_NOT_COMPARABLE, "COMPONENT_NOT_OBSERVED", None, None, None, maximum)
    if not _finite(current_component.points) or not _finite(prior_component.points):
        return ComponentDelta(component_name, DeltaStatus.INVALID_VALUE, "COMPONENT_VALUE_INVALID", None, None, None, maximum)
    current_points = float(current_component.points)
    prior_points = float(prior_component.points)
    return ComponentDelta(
        component_name, DeltaStatus.READY, "COMPONENT_DELTA_READY",
        current_points, prior_points, current_points - prior_points, maximum,
    )


def calculate_fundamental_delta(
    current: ScoreObservation,
    company_history: Sequence[ScoreObservation],
    *,
    source_fingerprint: str,
) -> FundamentalDeltaResult:
    ordered = sorted(company_history, key=lambda row: (row.fiscal.fiscal_sequence, row.score_result_id))
    fiscal_index = build_fiscal_index([row.fiscal for row in ordered])
    score_index = {row.fiscal.fiscal_sequence: row for row in ordered}
    if len(score_index) != len(ordered):
        raise ValueError(f"DUPLICATE_SCORE_FISCAL_IDENTITY:{current.fiscal.company_id}")
    horizons: list[HorizonDelta] = []
    for horizon in Horizon:
        resolution = resolve_horizon(current.fiscal, fiscal_index[current.fiscal.company_id], horizon)
        prior = score_index.get(current.fiscal.fiscal_sequence - HORIZON_LAGS[horizon])
        if resolution.status == DeltaStatus.READY and prior is not None:
            component_deltas = tuple(_component_delta(current, prior, name) for name in COMPONENTS)
        else:
            component_deltas = tuple(
                ComponentDelta(
                    name, resolution.status, resolution.reason_code,
                    None, None, None, COMPONENT_MAXIMA[name],
                )
                for name in COMPONENTS
            )
        current_reason = _total_reason(current)
        prior_reason = _total_reason(prior) if prior is not None else None
        status, reason = resolution.status, resolution.reason_code
        if status == DeltaStatus.READY and current_reason is not None:
            status, reason = current_reason
        elif status == DeltaStatus.READY and prior_reason is not None:
            status = prior_reason[0] if prior_reason[0] == DeltaStatus.MODEL_MISMATCH else DeltaStatus.ENDPOINT_NOT_COMPARABLE
            reason = f"PRIOR_{prior_reason[1]}"
        total_delta = None
        component_sum = None
        reconciliation = None
        if status == DeltaStatus.READY and prior is not None:
            total_delta = float(current.total_score) - float(prior.total_score)
            if any(item.status != DeltaStatus.READY for item in component_deltas):
                status, reason = DeltaStatus.ENDPOINT_NOT_COMPARABLE, "COMPONENT_CONTRIBUTIONS_NOT_COMPLETE"
                total_delta = None
            else:
                component_sum = sum(float(item.delta_points) for item in component_deltas if item.delta_points is not None)
                reconciliation = component_sum - total_delta
                if not math.isclose(component_sum, total_delta, abs_tol=RECONCILIATION_TOLERANCE, rel_tol=0.0):
                    status, reason = DeltaStatus.ENDPOINT_NOT_COMPARABLE, "DELTA_RECONCILIATION_FAILED"
                    total_delta = None
        horizons.append(HorizonDelta(
            horizon=horizon,
            status=status,
            reason_code=reason,
            current_score=float(current.total_score) if _finite(current.total_score) else None,
            prior_score=float(prior.total_score) if prior is not None and _finite(prior.total_score) else None,
            delta_points=total_delta,
            prior_observation_id=prior.fiscal.observation_id if prior else None,
            prior_score_result_id=prior.score_result_id if prior else None,
            prior_fiscal_sequence=prior.fiscal.fiscal_sequence if prior else None,
            prior_available_date=prior.fiscal.available_date if prior else None,
            components=component_deltas,
            component_delta_sum=component_sum,
            reconciliation_error=reconciliation,
        ))
    payload = {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "semantic_mode": SEMANTIC_MODE,
        "source_fingerprint": source_fingerprint,
        "company_id": current.fiscal.company_id,
        "current_observation_id": current.fiscal.observation_id,
        "current_score_result_id": current.score_result_id,
        "current_fiscal_sequence": current.fiscal.fiscal_sequence,
        "current_fiscal_year": current.fiscal.fiscal_year,
        "current_fiscal_quarter": current.fiscal.fiscal_quarter,
        "current_period_end": current.fiscal.period_end,
        "current_available_date": current.fiscal.available_date,
        "current_score": float(current.total_score) if _finite(current.total_score) else None,
        "current_score_status": current.readiness_status,
        "score_model_version": current.model_version,
        "score_model_fingerprint": current.model_fingerprint,
        "horizons": tuple(horizons),
    }
    return FundamentalDeltaResult(
        **payload,
        result_fingerprint=fingerprint({**payload, "horizons": [asdict(item) for item in horizons]}),
    )
