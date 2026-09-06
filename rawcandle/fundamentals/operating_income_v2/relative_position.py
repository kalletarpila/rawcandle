from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

from rawcandle.fundamentals.relative_position import engine as v1

from .contract import RELATIVE_MODEL_VERSION, fingerprint, model_fingerprint
from .score import MODEL_FINGERPRINT as SCORE_FINGERPRINT
from .score import MODEL_VERSION as SCORE_VERSION
from .valuation import MODEL_FINGERPRINT as VALUATION_FINGERPRINT
from .valuation import MODEL_VERSION as VALUATION_VERSION


MODEL_VERSION = RELATIVE_MODEL_VERSION
MODEL_CONTRACT = {
    **v1.MODEL_CONTRACT,
    "model_version": MODEL_VERSION,
    "source_models": {
        "FUNDAMENTAL_SCORE": (SCORE_VERSION, SCORE_FINGERPRINT),
        "ABSOLUTE_VALUATION_SCORE": (VALUATION_VERSION, VALUATION_FINGERPRINT),
    },
    "mixed_source_models": "REJECT_PER_MEASURE_UNIVERSE",
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

RelativeMeasure = v1.RelativeMeasure
PeerScope = v1.PeerScope
RelativeStatus = v1.RelativeStatus
EcosystemMembership = v1.EcosystemMembership
RelativeObservation = v1.RelativeObservation


@dataclass(frozen=True)
class RelativeSnapshot:
    model_version: str
    model_fingerprint: str
    semantic_mode: str
    snapshot_date: str
    source_fingerprint: str
    result_fingerprint: str
    results: tuple[dict[str, Any], ...]
    coverage: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_sources(observations: Sequence[RelativeObservation]) -> None:
    expected = {
        RelativeMeasure.FUNDAMENTAL_SCORE: (SCORE_VERSION, SCORE_FINGERPRINT),
        RelativeMeasure.ABSOLUTE_VALUATION_SCORE: (VALUATION_VERSION, VALUATION_FINGERPRINT),
    }
    for observation in observations:
        if (observation.source_model_version, observation.source_model_fingerprint) != expected[observation.measure]:
            raise ValueError(f"OPERATING_INCOME_V2_RELATIVE_SOURCE_MODEL_MISMATCH:{observation.measure.value}")


def calculate_snapshot(
    observations: Sequence[RelativeObservation],
    *,
    snapshot_date: str,
    freshness_days: int,
    classification_fingerprint: str,
    taxonomy_fingerprint: str,
) -> RelativeSnapshot:
    _validate_sources(observations)
    mapped = [replace(
        item,
        source_model_version="V2_VALIDATED_SOURCE",
        source_model_fingerprint=fingerprint((item.measure.value, "V2_VALIDATED_SOURCE")),
    ) for item in observations]
    result = v1.calculate_snapshot(
        mapped, snapshot_date=snapshot_date, freshness_days=freshness_days,
        classification_fingerprint=classification_fingerprint,
        taxonomy_fingerprint=taxonomy_fingerprint,
    )
    results = tuple({**item.to_dict(), "model_version": MODEL_VERSION, "model_fingerprint": MODEL_FINGERPRINT} for item in result.results)
    coverage = tuple(item.to_dict() for item in result.coverage)
    source_fp = fingerprint({"observations": [asdict(item) for item in observations], "classification": classification_fingerprint, "taxonomy": taxonomy_fingerprint})
    payload = {"model_version": MODEL_VERSION, "model_fingerprint": MODEL_FINGERPRINT, "semantic_mode": "CURRENT_REVISED_SNAPSHOT", "snapshot_date": snapshot_date, "source_fingerprint": source_fp, "results": results, "coverage": coverage}
    return RelativeSnapshot(**payload, result_fingerprint=fingerprint(payload))
