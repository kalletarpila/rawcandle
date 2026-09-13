from __future__ import annotations

import json

import pytest

from rawcandle.fundamentals.operating_income_v2 import score, valuation
from rawcandle.fundamentals.operating_income_v2 import delta
from tests.test_fundamentals_v4_operating_income_v2 import ttm, valuation_observation


def _with_regime(row: dict[str, object], regime: str, *, ready: bool = True, reason: str = "STRUCTURAL_READY") -> dict[str, object]:
    return {
        **row,
        "structural_contract_version": "ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1",
        "structural_contract_fingerprint": "contract",
        "structural_readiness_status": "STRUCTURAL_READY" if ready else "STRUCTURAL_NOT_READY",
        "structural_reason_code": reason,
        "structural_regime_id": regime,
        "structural_regime_status": regime,
        "readiness_status": "TTM_READY" if ready else "STRUCTURAL_NOT_READY",
        "blocker_codes_json": "[]" if ready else json.dumps(["STRUCTURAL_REGIME_NOT_READY", reason]),
        "core_ttm_ready": 1 if ready else 0,
    }


def _component(row: dict[str, object], name: str) -> dict[str, object]:
    return next(item for item in row["components"] if item["component_name"] == name)  # type: ignore[index,union-attr]


def test_structural_not_ready_endpoint_blocks_score_components() -> None:
    rows = [_with_regime(ttm(index), "event:unresolved", ready=index < 5, reason="UNRESOLVED_FISCAL_BOUNDARY") for index in range(1, 6)]

    result = score.compute_score_rows(rows, {}, generated_at="test", run_id="test")[-1]
    details = json.loads(result["missing_input_reason"])

    assert result["readiness_status"] == "SCORE_NOT_READY"
    assert result["total_score"] is None
    assert details["structural_readiness_status"] == "STRUCTURAL_NOT_READY"
    assert details["structural_reason_code"] == "UNRESOLVED_FISCAL_BOUNDARY"
    assert all(component["component_score"] is None for component in result["components"])


def test_score_history_components_do_not_cross_structural_regime() -> None:
    rows = [_with_regime(ttm(index), "pre") for index in range(1, 5)]
    rows.append(_with_regime(ttm(5), "post"))

    result = score.compute_score_rows(rows, {}, generated_at="test", run_id="test")[-1]
    details = json.loads(result["missing_input_reason"])

    assert result["readiness_status"] == "SCORE_LIMITED"
    assert _component(result, "OPERATING_PROFITABILITY")["component_score"] is not None
    assert _component(result, "REVENUE_GROWTH")["component_score"] is None
    assert _component(result, "OPERATING_MARGIN_DIRECTION")["component_score"] is None
    assert _component(result, "DILUTION")["component_score"] is None
    trajectory_evidence = json.loads(_component(result, "FUNDAMENTAL_TRAJECTORY")["evidence_json"])
    assert trajectory_evidence["blocker"] == "STRUCTURAL_REGIME_INCOMPATIBLE"
    assert "REVENUE_GROWTH" in details["missing_components"]


def test_valuation_preserves_structural_unavailable_reason() -> None:
    result = valuation.calculate_valuation(
        valuation_observation(
            ttm_readiness_status="STRUCTURAL_NOT_READY",
            ttm_blocker_codes=("STRUCTURAL_REGIME_NOT_READY", "CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM"),
        ),
        (valuation.PriceBar("2026-02-01", 10.0, 10.0, 10.0, 10.0),),
    )

    assert result.valuation_status == "VALUATION_NOT_READY"
    assert result.reason_code == "STRUCTURAL_REGIME_NOT_READY"
    assert result.total_valuation_score is None


def test_delta_current_structural_not_ready_endpoint_returns_source_not_ready() -> None:
    row = score.compute_score_rows(
        [_with_regime(ttm(1), "event:unresolved", ready=False, reason="UNRESOLVED_FISCAL_BOUNDARY")],
        {},
        generated_at="test",
        run_id="test",
    )[0]
    fiscal = delta.FiscalObservation("1", 1, 2023, "Q1", 2023 * 4 + 1, "2023-03-28", "2023-03-29")
    maxima = dict(zip(score.COMPONENTS, (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0)))
    observation = delta.ScoreObservation(
        fiscal,
        1,
        score.MODEL_VERSION,
        score.MODEL_FINGERPRINT,
        row["total_score"],
        row["readiness_status"],
        "STRUCTURAL_NOT_READY",
        tuple(
            delta.ScoreComponentObservation(
                item["component_name"],
                item["component_score"],
                maxima[item["component_name"]],
                "OBSERVED" if item["component_score"] is not None else "MISSING",
            )
            for item in row["components"]
        ),
    )

    result = delta.calculate_fundamental_delta(observation, (observation,), source_fingerprint="structural")

    assert {item["status"] for item in result.horizons} == {delta.DeltaStatus.LAG_ENDPOINT_MISSING}


def test_score_without_structural_metadata_retains_existing_behavior() -> None:
    rows = [ttm(index) for index in range(1, 9)]

    result = score.compute_score_rows(rows, {}, generated_at="test", run_id="test")[-1]

    assert result["readiness_status"] == "SCORE_FULL"
    assert result["total_score"] == pytest.approx(sum(float(item["component_score"]) for item in result["components"]))
