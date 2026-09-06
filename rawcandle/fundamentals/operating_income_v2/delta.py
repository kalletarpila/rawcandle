from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from rawcandle.fundamentals.delta import engine as v1

from .contract import COMPONENTS, DELTA_MODEL_VERSION, fingerprint, model_fingerprint
from .score import MODEL_FINGERPRINT as SCORE_MODEL_FINGERPRINT
from .score import MODEL_VERSION as SCORE_MODEL_VERSION


MODEL_VERSION = DELTA_MODEL_VERSION
SEMANTIC_MODE = "CURRENTLY_REVISED_OPERATING_INCOME_FUNDAMENTAL_HISTORY_DELTA"
COMPONENT_MAXIMA = dict(zip(COMPONENTS, (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0)))
MODEL_CONTRACT = {
    **v1.MODEL_CONTRACT,
    "model_version": MODEL_VERSION,
    "semantic_mode": SEMANTIC_MODE,
    "source_score_model_version": SCORE_MODEL_VERSION,
    "source_score_model_fingerprint": SCORE_MODEL_FINGERPRINT,
    "components": COMPONENT_MAXIMA,
    "mixed_v1_v2_endpoints": "REJECT",
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

Horizon = v1.Horizon
DeltaStatus = v1.DeltaStatus
FiscalObservation = v1.FiscalObservation


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
    horizons: tuple[dict[str, Any], ...]
    result_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TO_V1 = {
    "OPERATING_PROFITABILITY": "EBIT_PROFITABILITY",
    "OPERATING_MARGIN_DIRECTION": "EBIT_MARGIN_DIRECTION",
}
_FROM_V1 = {value: key for key, value in _TO_V1.items()}


def _validate(row: ScoreObservation) -> None:
    if row.model_version != SCORE_MODEL_VERSION or row.model_fingerprint != SCORE_MODEL_FINGERPRINT:
        raise ValueError("OPERATING_INCOME_V2_SCORE_MODEL_MISMATCH")
    if tuple(component.component_name for component in row.components) != COMPONENTS:
        raise ValueError("OPERATING_INCOME_V2_COMPONENT_CONTRACT_MISMATCH")


def _to_v1(row: ScoreObservation) -> v1.ScoreObservation:
    _validate(row)
    return v1.ScoreObservation(
        fiscal=row.fiscal,
        score_result_id=row.score_result_id,
        model_version=v1.SCORE_MODEL_VERSION,
        model_fingerprint=v1.SCORE_MODEL_FINGERPRINT,
        total_score=row.total_score,
        readiness_status=row.readiness_status,
        ttm_readiness_status=row.ttm_readiness_status,
        components=tuple(v1.ScoreComponentObservation(
            _TO_V1.get(item.component_name, item.component_name), item.points,
            item.maximum_points, item.value_status, item.imputed,
        ) for item in row.components),
        reweighted=row.reweighted,
    )


def calculate_fundamental_delta(
    current: ScoreObservation,
    company_history: Sequence[ScoreObservation],
    *,
    source_fingerprint: str,
) -> FundamentalDeltaResult:
    _validate(current)
    for row in company_history:
        _validate(row)
    result = v1.calculate_fundamental_delta(
        _to_v1(current), [_to_v1(row) for row in company_history],
        source_fingerprint=source_fingerprint,
    )
    payload = result.to_dict()
    payload["model_version"] = MODEL_VERSION
    payload["model_fingerprint"] = MODEL_FINGERPRINT
    payload["semantic_mode"] = SEMANTIC_MODE
    payload["score_model_version"] = SCORE_MODEL_VERSION
    payload["score_model_fingerprint"] = SCORE_MODEL_FINGERPRINT
    for horizon in payload["horizons"]:
        for component in horizon["components"]:
            component["component_name"] = _FROM_V1.get(component["component_name"], component["component_name"])
    payload["horizons"] = tuple(payload["horizons"])
    payload.pop("result_fingerprint")
    payload["result_fingerprint"] = fingerprint(payload)
    return FundamentalDeltaResult(**payload)
