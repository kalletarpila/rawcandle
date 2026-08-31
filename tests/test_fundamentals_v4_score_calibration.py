from __future__ import annotations

import inspect
import json
from pathlib import Path

from rawcandle.fundamentals.score import calibration as score


def ttm_row(company_id: int, idx: int, fy: int, fq: str, *, revenue: float = 100.0, ebit: float = 10.0, fcf: float = 8.0, ocf: float = 12.0, cash: float = 50.0, debt: float = 20.0, shares: float = 10.0, available: str = "2024-05-01", ready: int = 1):
    return {
        "company_id": company_id,
        "company_key": f"C{company_id}",
        "company_name": f"Company {company_id}",
        "company_status": "ACTIVE",
        "security_id": company_id,
        "ticker": f"T{company_id}",
        "exchange": "NASDAQ",
        "security_active": 1,
        "ttm_id": idx,
        "endpoint_quarter_id": idx,
        "endpoint_fiscal_year": fy,
        "endpoint_fiscal_quarter": fq,
        "period_end": f"{fy}-{idx % 12 + 1:02d}-28",
        "readiness_status": "TTM_READY" if ready else "TTM_MISSING_REVENUE",
        "blocker_codes_json": "[]" if ready else json.dumps(["TTM_MISSING_REVENUE"]),
        "ttm_revenue": revenue,
        "ttm_ebit": ebit,
        "ttm_ebitda": ebit + 2,
        "ttm_operating_cashflow": ocf,
        "ttm_free_cashflow": fcf,
        "cash": cash,
        "total_debt": debt,
        "shares_outstanding": shares,
        "core_ttm_ready": ready,
        "ttm_source_available_date": available,
        "first_public_result_date": None,
        "input_quarter_ids_json": json.dumps([idx - 3, idx - 2, idx - 1, idx]),
        "input_values_hash": f"h{idx}",
        "canonical_financial_fingerprint": "fp",
        "output_fingerprint": f"ofp{idx}",
    }


def eight_quarters() -> list[dict]:
    quarters = []
    labels = [(2022, "Q1"), (2022, "Q2"), (2022, "Q3"), (2022, "Q4"), (2023, "Q1"), (2023, "Q2"), (2023, "Q3"), (2023, "Q4")]
    for idx, (fy, fq) in enumerate(labels, start=1):
        quarters.append(ttm_row(1, idx, fy, fq, revenue=100 + idx * 5, ebit=10 + idx, fcf=7 + idx, shares=10 + idx * 0.1, available=f"{fy}-05-01"))
    return quarters


def test_score_architecture_weights_locked_and_total_100():
    weights = {c["component_id"]: c["max_points"] for c in score.COMPONENTS}
    assert weights == {
        "growth_earnings_development": 25,
        "profitability_level": 15,
        "margin_direction": 15,
        "cash_flow_quality": 15,
        "development_consistency": 10,
        "balance_sheet_resilience": 15,
        "dilution": 5,
    }
    assert sum(weights.values()) == 100


def test_time_split_uses_availability_date_contract_not_period_end():
    row = ttm_row(1, 1, 2023, "Q4", available="2024-02-15")
    matrix = score.build_feature_matrix([row])
    assert matrix[0]["period_end"].startswith("2023")
    assert matrix[0]["sample_split"] == score.VALIDATION_SPLIT
    assert matrix[0]["availability_fallback_used"] == 0


def test_future_targets_are_later_and_not_score_inputs():
    rows = eight_quarters()
    matrix = score.build_feature_matrix(rows)
    fifth = matrix[4]
    assert fifth["future_1q_observable"] == 1
    assert fifth["future_2q_observable"] == 1
    assert fifth["future_4q_observable"] == 0
    assert all(not name.startswith("future_") for name in score.FEATURE_COLUMNS)


def test_no_stock_ohlcv_lifecycle_or_valuation_inputs_in_features_or_spec():
    spec = score.calibrate_curves(score.build_feature_matrix(eight_quarters()))
    payload = json.dumps(spec, sort_keys=True).lower()
    forbidden = ("stock_return", "price_return", "close_price", "open_price", "high_price", "low_price", "volume", "ohlcv", "lifecycle", "valuation", "yahoo", "sec")
    for word in forbidden:
        assert word not in payload


def test_feature_formulas_are_deterministic_and_missing_is_preserved():
    first = score.build_feature_matrix(eight_quarters())
    second = score.build_feature_matrix(eight_quarters())
    assert first == second
    row = first[4]
    assert row["revenue_growth_yoy_ttm"] == score.safe_growth(125, 105)
    assert row["ebit_growth_yoy_ttm"] == score.safe_growth(15, 11)
    assert row["ebit_margin_ttm"] == score.safe_div(15, 125)
    assert row["fcf_to_ebit"] == score.safe_positive_ratio(12, 15)
    assert row["share_change_yoy"] == score.safe_growth(10.5, 10.1)
    missing = score.feature_row(ttm_row(1, 1, 2024, "Q1", revenue=None), None, None, [], None, None, None)
    assert missing["ebit_margin_ttm"] is None
    assert "YOY_TTM_HISTORY_NOT_READY" in missing["feature_blockers"]


def test_negative_and_near_zero_denominator_guards():
    assert score.safe_growth(10, 0) is None
    assert score.safe_growth(10, -1) is None
    assert score.safe_positive_ratio(5, 0) is None
    assert score.safe_positive_ratio(5, -1) is None
    row = score.feature_row(ttm_row(1, 1, 2024, "Q1", revenue=0, ebit=-1, fcf=-2), None, None, [], None, None, None)
    assert row["ebit_margin_ttm"] is None
    assert row["fcf_to_ebit"] is None


def test_score_bounds_component_bounds_and_monotonic_curves():
    matrix = score.build_feature_matrix(eight_quarters())
    spec = score.calibrate_curves(matrix)
    scored = score.apply_score(matrix, spec)
    for row in scored:
        if row["total_score"] is not None:
            assert 0 <= row["total_score"] <= 100
        for component in score.COMPONENTS:
            value = row[f"{component['component_id']}_score"]
            if value is not None:
                assert 0 <= value <= component["max_points"]
    low = score.linear_score(-0.1, 10, -0.1, 0.3)
    high = score.linear_score(0.3, 10, -0.1, 0.3)
    assert low <= high
    assert score.linear_score(-0.03, 5, -0.03, 0.1, higher_is_better=False) >= score.linear_score(0.1, 5, -0.03, 0.1, higher_is_better=False)


def test_candidate_spec_fingerprint_deterministic_and_2025_2026_do_not_tune():
    matrix = score.build_feature_matrix(eight_quarters())
    spec1 = score.calibrate_curves(matrix)
    spec2 = score.calibrate_curves(matrix)
    assert score.model_fingerprint(spec1) == score.model_fingerprint(spec2)
    assert spec1["calibrated_from"] == score.DEV_SPLIT
    assert "2025" not in json.dumps(spec1["curves"], sort_keys=True)
    assert "2026" not in json.dumps(spec1["curves"], sort_keys=True)


def test_readiness_policy_known_gap_semantics():
    current = ttm_row(1, 5, 2023, "Q1", ready=1)
    old_gap = ttm_row(1, 1, 2022, "Q1", ready=0)
    ready_row = score.feature_row(current, None, ttm_row(1, 1, 2022, "Q1", ready=1), [ttm_row(1, 2, 2022, "Q2"), ttm_row(1, 3, 2022, "Q3"), current], None, None, None)
    blocked_row = score.feature_row(current, None, old_gap, [current], None, None, None)
    assert "CURRENT_TTM_NOT_READY" not in ready_row["feature_blockers"]
    assert "CURRENT_TTM_NOT_READY" not in blocked_row["feature_blockers"]
    assert "YOY_TTM_HISTORY_NOT_READY" in blocked_row["feature_blockers"]
    assert "CIK" not in blocked_row["feature_blockers"]
    assert "PERMATICKER" not in blocked_row["feature_blockers"]


def test_no_swingmaster_runtime_dependency_and_no_production_writer_surface():
    source = inspect.getsource(score)
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source
    assert "requests." not in source
    assert "score_result" in source
    assert "INSERT INTO score_result" not in source
    assert "UPDATE score_result" not in source
    assert "lifecycle_result" in source
    assert "valuation_result" in source
    assert "INSERT INTO lifecycle_result" not in source
    assert "INSERT INTO valuation_result" not in source


def test_review_classification_when_development_monotonicity_fails(tmp_path: Path):
    paths = score.ScorePaths(
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        canonical_db=tmp_path / "missing.db",
        analysis_db=tmp_path / "missing_analysis.db",
        provider_db=tmp_path / "missing_provider.db",
        known_gaps_doc=tmp_path / "known.md",
    )
    matrix = []
    scored = []
    for idx, (band_score, state) in enumerate([(20, "IMPROVING"), (40, "DETERIORATING"), (60, "IMPROVING"), (80, "DETERIORATING")], start=1):
        row = {"company_id": idx, "sample_split": score.DEV_SPLIT, "feature_ready": 1, "total_score": band_score, "score_readiness": "SCORE_READY", "future_4q_fundamental_state": state, "availability_date": "2022-01-01"}
        for component in score.COMPONENTS:
            row[f"{component['component_id']}_score"] = min(component["max_points"], 1)
        matrix.append(row)
        scored.append(dict(row))
    spec = score.calibrate_curves([])
    fp = score.model_fingerprint(spec)
    before = {"score_rows": 0, "lifecycle_rows": 0, "valuation_rows": 0}
    summary = score.final_summary(paths, matrix, scored, spec, fp, before, before, "a", "a", {"values_hash": "t"}, {"values_hash": "t"})
    assert summary["classification"] == score.CLASSIFICATION_REVIEW
    assert summary["production_safety"]["production_score_rows_created"] == 0
