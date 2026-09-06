from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score import engine as v1
from rawcandle.fundamentals.score.methodology import ANCHORS

from .contract import (
    COMPONENTS,
    LEVERAGE_ANCHORS,
    OPERATING_DIRECTION_ANCHORS,
    OPERATING_MARGIN_ANCHORS,
    SCORE_MODEL_VERSION,
    TRAJECTORY_TOLERANCE,
    TTM_MODEL_VERSION,
    model_fingerprint,
)


MODEL_VERSION = SCORE_MODEL_VERSION
MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "ttm_model_version": TTM_MODEL_VERSION,
    "components": {
        "REVENUE_GROWTH": {"maximum": 20.0, "anchors": ANCHORS["revenue_growth_yoy_ttm"]},
        "OPERATING_PROFITABILITY": {"maximum": 15.0, "measure": "ttm_operating_income/ttm_revenue", "anchors": OPERATING_MARGIN_ANCHORS},
        "OPERATING_MARGIN_DIRECTION": {"maximum": 15.0, "measure": "operating_margin_t-operating_margin_t_minus_4", "anchors": OPERATING_DIRECTION_ANCHORS},
        "FCF_MARGIN": {"maximum": 15.0, "anchors": ANCHORS["fcf_margin_ttm"]},
        "BALANCE_SHEET_RESILIENCE": {
            "maximum": 15.0,
            "positive_profit_denominator": "ttm_operating_income",
            "positive_profit_anchors": LEVERAGE_ANCHORS,
            "nonpositive_profit_branches": {
                "net_debt_nonpositive_and_fcf_nonnegative": 10.0,
                "net_debt_nonpositive_and_fcf_negative": 5.0,
                "net_debt_positive": 0.0,
            },
        },
        "DILUTION": {"maximum": 10.0, "anchors": ANCHORS["share_change_yoy"]},
        "FUNDAMENTAL_TRAJECTORY": {
            "maximum": 10.0,
            "window_ttm_snapshots": 5,
            "qoq_transitions": 4,
            "legs": ("revenue", "operating_margin", "fcf"),
            "operating_margin_tolerance": TRAJECTORY_TOLERANCE,
            "neutral_points": 5.0,
        },
    },
    "weights": (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0),
    "interpolation": "continuous_piecewise_linear_clamped",
    "positive_revenue_required_for_margins": True,
    "operating_income_fallback": None,
    "imputation": None,
    "statuses": v1.MODEL_CONTRACT["statuses"],
    "dilution_policy": v1.MODEL_CONTRACT["dilution_policy"],
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

_NAME_MAP = {
    "EBIT_PROFITABILITY": "OPERATING_PROFITABILITY",
    "EBIT_MARGIN_DIRECTION": "OPERATING_MARGIN_DIRECTION",
}


def _replace_semantics(value: Any) -> Any:
    if isinstance(value, dict):
        return {_replace_semantics(key): _replace_semantics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_semantics(item) for item in value]
    if isinstance(value, str):
        return (value.replace("ttm_ebit", "ttm_operating_income")
                .replace("ebit_margin", "operating_margin")
                .replace("EBIT", "OPERATING_INCOME")
                .replace("ebit", "operating_income"))
    return value


def _v1_input(row: Mapping[str, Any]) -> dict[str, Any]:
    operating_income = row.get("ttm_operating_income")
    mapped = dict(row)
    mapped["ttm_ebit"] = operating_income
    return mapped


def trajectory_points(
    endpoint_ordinal: int,
    rows_by_ordinal: Mapping[int, Mapping[str, Any]],
) -> tuple[float | None, dict[str, Any]]:
    mapped = {ordinal: _v1_input(row) for ordinal, row in rows_by_ordinal.items()}
    points, evidence = v1.trajectory_points(endpoint_ordinal, mapped)
    return points, _replace_semantics(evidence)


def compute_score_rows(
    ttm_rows: Sequence[Mapping[str, Any]],
    split_events: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    generated_at: str,
    run_id: str,
) -> list[dict[str, Any]]:
    mapped = [_v1_input(row) for row in ttm_rows]
    output = v1.compute_score_rows(
        mapped, split_events, generated_at=generated_at, run_id=run_id
    )
    for row in output:
        row["model_version"] = MODEL_VERSION
        row["model_fingerprint"] = MODEL_FINGERPRINT
        details = json.loads(row["missing_input_reason"])
        details["missing_components"] = [_NAME_MAP.get(name, name) for name in details["missing_components"]]
        details["observed_components"] = [_NAME_MAP.get(name, name) for name in details["observed_components"]]
        details["imputed_components"] = [_NAME_MAP.get(name, name) for name in details["imputed_components"]]
        row["missing_input_reason"] = json.dumps(details, sort_keys=True, separators=(",", ":"))
        for component in row["components"]:
            component["component_name"] = _NAME_MAP.get(component["component_name"], component["component_name"])
            evidence = json.loads(component["evidence_json"])
            component["evidence_json"] = json.dumps(_replace_semantics(evidence), sort_keys=True, separators=(",", ":"))
        assert tuple(item["component_name"] for item in row["components"]) == COMPONENTS
        observed = [item["component_score"] for item in row["components"] if item["component_score"] is not None]
        if row["total_score"] is not None:
            assert abs(float(row["total_score"]) - sum(float(value) for value in observed)) <= 1e-9
    return output


def assert_v2_score(row: Mapping[str, Any]) -> None:
    if row.get("model_version") != MODEL_VERSION or row.get("model_fingerprint") != MODEL_FINGERPRINT:
        raise ValueError("OPERATING_INCOME_V2_SCORE_MODEL_MISMATCH")
    names = tuple(item["component_name"] for item in row.get("components", ()))
    if names != COMPONENTS:
        raise ValueError("OPERATING_INCOME_V2_COMPONENT_CONTRACT_MISMATCH")
