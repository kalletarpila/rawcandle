from __future__ import annotations

import json
from dataclasses import replace

import pytest

from rawcandle.fundamentals.delta import engine as delta_v1
from rawcandle.fundamentals.diagnostic_flags import engine as diagnostic_v1
from rawcandle.fundamentals.lifecycle import engine as lifecycle_v1
from rawcandle.fundamentals.operating_income_v2 import contract
from rawcandle.fundamentals.operating_income_v2 import delta, diagnostic_flags, lifecycle
from rawcandle.fundamentals.operating_income_v2 import relative_position, score, snapshot, valuation
from rawcandle.fundamentals.relative_position import engine as relative_v1
from rawcandle.fundamentals.score import engine as score_v1
from rawcandle.fundamentals.valuation import engine as valuation_v1


V1_FINGERPRINTS = {
    "score": "6d12268b9b3c1b7da3d3b04b5b097afa1e6781a5c7cbc6dece3344a04e54be80",
    "lifecycle": "db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f",
    "valuation": "17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f",
    "delta": "7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d",
    "relative": "983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2",
    "diagnostic": "1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad",
}


def ttm(index: int, *, operating_margin: float = 0.10, ebit_margin: float = 0.30) -> dict[str, object]:
    year = 2023 + (index - 1) // 4
    quarter = (index - 1) % 4 + 1
    revenue = 100.0
    return {
        "ttm_id": index, "company_id": 1, "security_id": 1, "ticker": "TEST",
        "endpoint_quarter_id": index, "endpoint_fiscal_year": year,
        "endpoint_fiscal_quarter": f"Q{quarter}", "period_end": f"{year}-{quarter*3:02d}-28",
        "ttm_source_available_date": f"{year}-{quarter*3:02d}-29",
        "ttm_revenue": revenue, "ttm_operating_income": revenue * operating_margin,
        "ttm_ebit": revenue * ebit_margin, "ttm_free_cashflow": 8.0,
        "cash": 20.0, "total_debt": 10.0, "shares_outstanding": 10.0,
        "core_ttm_ready": 1,
    }


def component(row: dict[str, object], name: str) -> dict[str, object]:
    return next(item for item in row["components"] if item["component_name"] == name)  # type: ignore[index,union-attr]


def test_v1_fingerprints_are_unchanged_and_v2_are_distinct() -> None:
    assert score_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["score"]
    assert lifecycle_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["lifecycle"]
    assert valuation_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["valuation"]
    assert delta_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["delta"]
    assert relative_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["relative"]
    assert diagnostic_v1.MODEL_FINGERPRINT == V1_FINGERPRINTS["diagnostic"]
    assert len({score.MODEL_FINGERPRINT, lifecycle.MODEL_FINGERPRINT, valuation.MODEL_FINGERPRINT,
                delta.MODEL_FINGERPRINT, relative_position.MODEL_FINGERPRINT,
                diagnostic_flags.MODEL_FINGERPRINT, snapshot.MODEL_FINGERPRINT}) == 7
    assert contract.FAMILY_FINGERPRINT


def test_score_v2_uses_operating_income_and_preserves_unaffected_components() -> None:
    rows = [ttm(index) for index in range(1, 9)]
    v2 = score.compute_score_rows(rows, {}, generated_at="x", run_id="x")[-1]
    v1 = score_v1.compute_score_rows(rows, {}, generated_at="x", run_id="x")[-1]
    assert v2["model_version"] == score.MODEL_VERSION
    assert component(v2, "OPERATING_PROFITABILITY")["component_score"] == 7.5
    assert component(v1, "EBIT_PROFITABILITY")["component_score"] == 15.0
    for name in ("REVENUE_GROWTH", "FCF_MARGIN", "DILUTION"):
        assert component(v2, name)["component_score"] == component(v1, name)["component_score"]
    assert v2["total_score"] == pytest.approx(sum(float(item["component_score"]) for item in v2["components"]))  # type: ignore[arg-type,union-attr]
    assert "ttm_operating_income" in component(v2, "OPERATING_PROFITABILITY")["evidence_json"]


def test_score_v2_has_no_ebit_fallback_and_neutral_trajectory_is_five() -> None:
    rows = [ttm(index) for index in range(1, 6)]
    ordinals = {score_v1.fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]): row for row in rows}
    points, evidence = score.trajectory_points(max(ordinals), ordinals)
    assert points == 5.0
    assert "operating_margin" in json.dumps(evidence)
    rows[-1]["ttm_operating_income"] = None
    rows[-1]["ttm_ebit"] = 999.0
    result = score.compute_score_rows(rows, {}, generated_at="x", run_id="x")[-1]
    assert component(result, "OPERATING_PROFITABILITY")["component_score"] is None
    assert component(result, "FUNDAMENTAL_TRAJECTORY")["component_score"] is None


def life(*, g: float = 0.1, m: float = 0.1, dm: float = 0.0, f: float = 0.05, op: float | None = 10.0, lag_op: float | None = None) -> lifecycle.LifecycleObservation:
    current_revenue = 100.0
    lag_revenue = current_revenue / (1.0 + g)
    if lag_op is None and op is not None:
        lag_op = lag_revenue * (m - dm)
        op = current_revenue * m
    return lifecycle.LifecycleObservation(
        1, 9, 2025, "Q1", "2025-03-31", "2025-05-01", True,
        current_revenue, op, current_revenue * f, lag_revenue, lag_op, True,
        (25.0, 25.0, 25.0, 25.0), 1,
    )


@pytest.mark.parametrize(("observation", "expected"), [
    (life(m=-0.21, f=-0.21), lifecycle.LifecycleState.DISTRESSED),
    (life(g=0.31, m=-0.06, f=-0.01), lifecycle.LifecycleState.STARTUP),
    (life(g=0.11, m=0.0, dm=0.01), lifecycle.LifecycleState.SCALING),
    (life(g=0.21, m=0.09, dm=-0.049), lifecycle.LifecycleState.GROWTH),
    (life(g=-0.049, m=0.15, dm=-0.049, f=0.05), lifecycle.LifecycleState.MATURE),
    (life(g=-0.051, m=0.10), lifecycle.LifecycleState.DECLINING),
    (life(g=0.0, m=-0.01, dm=0.0, f=0.01), lifecycle.LifecycleState.STRUGGLING),
    (life(g=0.0, m=0.10, dm=0.0, f=0.01), lifecycle.LifecycleState.TRANSITION),
])
def test_lifecycle_v2_boundaries(observation: lifecycle.LifecycleObservation, expected: lifecycle.LifecycleState) -> None:
    assert lifecycle.classify_raw_state(observation).raw_state == expected


def test_lifecycle_v2_missing_sign_flip_and_state_machine() -> None:
    missing = life(op=None, lag_op=None)
    assert lifecycle.classify_raw_state(missing).raw_state == lifecycle.LifecycleState.UNCLASSIFIED
    assert "operating_income" in lifecycle.classify_raw_state(missing).missing_inputs[0]
    raw_mature = lifecycle.classify_raw_state(life(g=0.0, m=0.20, f=0.10))
    raw_growth = lifecycle.classify_raw_state(life(g=0.25, m=0.05, dm=0.0, f=0.05))
    raw_distressed = lifecycle.classify_raw_state(life(m=-0.21, f=-0.21))
    state = lifecycle.LifecycleMachineState()
    state, first = lifecycle.advance_state_machine(state, raw_mature)
    state, candidate = lifecycle.advance_state_machine(state, raw_growth)
    state, confirmed = lifecycle.advance_state_machine(state, raw_growth)
    state, crisis = lifecycle.advance_state_machine(state, raw_distressed)
    assert first.final_state == lifecycle.LifecycleState.MATURE
    assert candidate.final_state == lifecycle.LifecycleState.MATURE and candidate.candidate_count == 1
    assert confirmed.final_state == lifecycle.LifecycleState.GROWTH
    assert crisis.final_state == lifecycle.LifecycleState.DISTRESSED
    assert lifecycle.replay_state_machine((raw_mature, raw_growth, raw_growth, raw_distressed))[-1] == crisis


def test_lifecycle_v2_pre_revenue_missing_lag_and_distressed_slow_exit() -> None:
    pre_revenue = replace(
        life(),
        ttm_revenue=0.0,
        ttm_operating_income=-10.0,
        ttm_free_cashflow=-5.0,
        input_quarter_revenues=(0.0, 0.0, 0.0, 0.0),
    )
    raw_pre = lifecycle.classify_raw_state(pre_revenue)
    assert raw_pre.raw_state == lifecycle.LifecycleState.STARTUP
    assert raw_pre.startup_profile == lifecycle.StartupProfile.PRE_REVENUE
    missing_lag = replace(life(), lag4_ttm_operating_income=None)
    raw_missing = lifecycle.classify_raw_state(missing_lag)
    assert raw_missing.raw_state == lifecycle.LifecycleState.UNCLASSIFIED
    assert raw_missing.reason_code.value == "LAG4_OPERATING_INCOME_MISSING"

    distressed = lifecycle.classify_raw_state(life(m=-0.21, f=-0.21))
    mature = lifecycle.classify_raw_state(life(g=0.0, m=0.20, f=0.10))
    state = lifecycle.LifecycleMachineState()
    state, _ = lifecycle.advance_state_machine(state, distressed)
    state, first_exit = lifecycle.advance_state_machine(state, mature)
    state, second_exit = lifecycle.advance_state_machine(state, mature)
    assert first_exit.final_state == lifecycle.LifecycleState.DISTRESSED
    assert second_exit.final_state == lifecycle.LifecycleState.MATURE


def test_lifecycle_v2_unclassified_clears_candidate_and_equality_is_not_distressed() -> None:
    equality = lifecycle.classify_raw_state(life(m=-0.20, f=-0.20))
    assert equality.raw_state != lifecycle.LifecycleState.DISTRESSED
    mature = lifecycle.classify_raw_state(life(g=0.0, m=0.20, f=0.10))
    growth = lifecycle.classify_raw_state(life(g=0.25, m=0.05, dm=0.0, f=0.05))
    unclassified = lifecycle.classify_raw_state(life(op=None, lag_op=None))
    state = lifecycle.LifecycleMachineState()
    state, _ = lifecycle.advance_state_machine(state, mature)
    state, pending = lifecycle.advance_state_machine(state, growth)
    assert pending.candidate_state == lifecycle.LifecycleState.GROWTH
    state, interrupted = lifecycle.advance_state_machine(state, unclassified)
    assert interrupted.final_state is None and state.candidate_state is None


def valuation_observation(**updates: object) -> valuation.ValuationObservation:
    values = dict(company_id=1, security_id=1, ticker="TEST", fiscal_year=2025,
                  fiscal_quarter="Q4", quarter_id=4, period_end="2025-12-31",
                  fundamental_available_date="2026-02-01", ttm_readiness_status="TTM_READY",
                  ttm_blocker_codes=(), ttm_operating_income=6.0, ttm_free_cashflow=6.0,
                  ttm_net_income_common=6.0, net_income_common_4q_ready=True,
                  shares_outstanding=10.0, cash=0.0, total_debt=0.0,
                  sector="Technology", industry="Software - Application")
    values.update(updates)
    return valuation.ValuationObservation(**values)


def test_valuation_v2_operating_yield_missing_negative_and_not_applicable() -> None:
    bar = valuation.PriceBar("2026-02-01", 10.0, 10.0, 10.0, 10.0)
    result = valuation.calculate_valuation(valuation_observation(), (bar,))
    assert result.operating_income_yield == pytest.approx(0.06)
    assert result.operating_income_points == 22.0
    assert result.total_valuation_score == 53.0
    negative = valuation.calculate_valuation(valuation_observation(ttm_operating_income=-1.0), (bar,))
    assert negative.operating_income_points == 0.0
    missing = valuation.calculate_valuation(valuation_observation(ttm_operating_income=None), (bar,))
    assert missing.reason_code == "TTM_OPERATING_INCOME_MISSING"
    reit = valuation.calculate_valuation(valuation_observation(sector="Real Estate", industry="REIT - Industrial"), (bar,))
    assert reit.valuation_status == "VALUATION_NOT_APPLICABLE"


def score_observation(sequence: int, total: float) -> delta.ScoreObservation:
    fiscal = delta.FiscalObservation(str(sequence), 1, 2025, f"Q{sequence}", 2025 * 4 + sequence, f"2025-{sequence*3:02d}-28", f"2025-{sequence*3:02d}-29")
    maxima = (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0)
    points = [total / 7] * 7
    return delta.ScoreObservation(fiscal, sequence, score.MODEL_VERSION, score.MODEL_FINGERPRINT, total, "SCORE_FULL", "TTM_READY", tuple(delta.ScoreComponentObservation(name, value, maximum, "OBSERVED") for name, value, maximum in zip(contract.COMPONENTS, points, maxima)))


def test_delta_v2_reconciles_and_rejects_v1_mixing() -> None:
    history = [score_observation(i, 7.0 * i) for i in range(1, 5)]
    result = delta.calculate_fundamental_delta(history[-1], history, source_fingerprint="source")
    qoq = next(item for item in result.horizons if item["horizon"] == delta.Horizon.QOQ)
    assert qoq["delta_points"] == 7.0
    assert qoq["component_delta_sum"] == pytest.approx(7.0)
    mixed = replace(history[-1], model_version=score_v1.MODEL_VERSION, model_fingerprint=score_v1.MODEL_FINGERPRINT)
    with pytest.raises(ValueError, match="SCORE_MODEL_MISMATCH"):
        delta.calculate_fundamental_delta(mixed, history, source_fingerprint="source")


def relative_observation(company: int, score_value: float) -> relative_position.RelativeObservation:
    return relative_position.RelativeObservation(
        str(company), company, company, f"T{company}", relative_position.RelativeMeasure.FUNDAMENTAL_SCORE,
        score_value, "SCORE_FULL", True, "READY", "2026-01-01",
        score.MODEL_VERSION, score.MODEL_FINGERPRINT, str(company), "Technology", "Software - Application",
        (relative_position.EcosystemMembership("E", "CORE"),),
    )


def test_relative_v2_ties_and_source_identity() -> None:
    observations = [relative_observation(i, 50.0 if i < 3 else float(i)) for i in range(1, 21)]
    result = relative_position.calculate_snapshot(observations, snapshot_date="2026-01-02", freshness_days=180, classification_fingerprint="c", taxonomy_fingerprint="t")
    tied = [item for item in result.results if item["peer_scope"] == relative_position.PeerScope.UNIVERSE and item["company_id"] in {1, 2}]
    assert len(tied) == 2 and tied[0]["average_rank"] == tied[1]["average_rank"]
    mixed = replace(observations[0], source_model_version=score_v1.MODEL_VERSION, source_model_fingerprint=score_v1.MODEL_FINGERPRINT)
    with pytest.raises(ValueError, match="SOURCE_MODEL_MISMATCH"):
        relative_position.calculate_snapshot([mixed, *observations[1:]], snapshot_date="2026-01-02", freshness_days=180, classification_fingerprint="c", taxonomy_fingerprint="t")


def diagnostic_endpoint(sequence: int, operating_income: float) -> diagnostic_flags.DiagnosticEndpoint:
    return diagnostic_flags.DiagnosticEndpoint(1, sequence, 2025, f"Q{sequence}", 2025*4+sequence, f"2025-{sequence*3:02d}-28", f"2025-{sequence*3:02d}-29", f"2025-{sequence*3:02d}-29", f"2025-{sequence*3:02d}-29", "TTM_READY", 100.0, operating_income, 5.0, 5.0, -2.0, 10.0, 5.0, 1.0, 1.0, 1.0, 1.0, 100.0, 8.0, "VALUATION_FULL", "VALUATION_FULL", "SUPPORTED", "SUPPORTED_OPERATING_COMPANY", operating_income/100.0, 0.05, 0.05)


def test_diagnostic_v2_uses_operating_income_and_is_deterministic() -> None:
    data = diagnostic_flags.DiagnosticInput(diagnostic_endpoint(2, 5.0), diagnostic_endpoint(1, 10.0), True)
    first = diagnostic_flags.evaluate_diagnostic_flags(data)
    second = diagnostic_flags.evaluate_diagnostic_flags(data)
    assert first == second
    assert all(item.model_fingerprint == diagnostic_flags.MODEL_FINGERPRINT for item in first)
    margin = next(item for item in first if item.flag_name == "RECENT_MARGIN_DECELERATION_REVIEW")
    assert "current_operating_margin" in margin.to_dict()["evidence"]
    assert "current_ebit" not in json.dumps([item.to_dict() for item in first])


def test_snapshot_v2_terminology_and_bundle_rejection() -> None:
    bundle = {
        layer: snapshot.ModelIdentity(*identity)
        for layer, identity in snapshot.MODEL_CONTRACT["required_models"].items()
    }
    snapshot.validate_model_bundle(bundle)
    with pytest.raises(ValueError, match="MODEL_MISMATCH"):
        snapshot.validate_model_bundle({**bundle, "score": snapshot.ModelIdentity(score_v1.MODEL_VERSION, score_v1.MODEL_FINGERPRINT)})
    assert "Operating Income" in snapshot.TERMINOLOGY.values()
    assert "EBIT" not in json.dumps(snapshot.TERMINOLOGY)
