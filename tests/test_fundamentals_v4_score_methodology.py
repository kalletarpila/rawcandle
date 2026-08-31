from __future__ import annotations

import inspect

import pytest

from rawcandle.fundamentals.score import methodology as method


def row(idx: int, *, revenue: float = 100.0, ebit: float = 10.0, fcf: float = 8.0, shares: float = 10.0):
    year = 2021 + (idx - 1) // 4
    quarter = (idx - 1) % 4 + 1
    return {
        "ttm_id": idx,
        "company_id": 1,
        "security_id": 1,
        "ticker": "TEST",
        "endpoint_fiscal_year": year,
        "endpoint_fiscal_quarter": f"Q{quarter}",
        "period_end": f"{year}-{quarter * 3:02d}-28",
        "ttm_source_available_date": f"{year}-{quarter * 3:02d}-29",
        "ttm_revenue": revenue,
        "ttm_ebit": ebit,
        "ttm_ebitda": ebit + 2,
        "ttm_free_cashflow": fcf,
        "cash": 20.0,
        "total_debt": 10.0,
        "shares_outstanding": shares,
        "core_ttm_ready": 1,
    }


def test_locked_architecture_and_piecewise_anchors():
    assert method.MODEL_VERSION == "SIMPLE_FUNDAMENTAL_SCORE_V1"
    assert method.piecewise_score(0.0, method.ANCHORS["revenue_growth_yoy_ttm"]) == 7.0
    assert method.piecewise_score(0.15, method.ANCHORS["revenue_growth_yoy_ttm"]) == 14.0
    assert method.piecewise_score(0.10, method.ANCHORS["share_change_yoy"]) == 0.0


def test_feature_history_requires_exact_fiscal_continuity():
    rows = [row(idx, revenue=100 + idx, ebit=10 + idx / 2, fcf=8 + idx / 4) for idx in range(1, 9)]
    features = method.build_features(rows)
    assert features[7]["revenue_growth_yoy_ttm"] is not None
    assert features[7]["consistency_points"] is not None

    with_gap = method.build_features([item for item in rows if item["ttm_id"] != 7])
    endpoint = next(item for item in with_gap if item["ttm_id"] == 8)
    assert endpoint["revenue_growth_yoy_ttm"] is not None
    assert endpoint["consistency_points"] is None


def test_consistency_formula_stable_and_volatile_cases():
    stable = [row(idx, revenue=100.0, ebit=10.0, fcf=8.0) for idx in range(1, 9)]
    stable_score = method.build_features(stable)[-1]["consistency_points"]
    assert stable_score == 10.0

    volatile = []
    for idx in range(1, 9):
        volatile.append(row(idx, revenue=100.0 + (40 if idx % 2 else 0), ebit=30.0 if idx % 2 else -10.0, fcf=25.0 if idx % 2 else -15.0))
    volatile_score = method.build_features(volatile)[-1]["consistency_points"]
    assert volatile_score == pytest.approx(10.0 / 3.0)


def test_asof_selects_one_latest_known_snapshot_per_security():
    features = method.build_features([row(idx) for idx in range(1, 7)])
    selected = method.asof_snapshot(features, "2022-06-30")
    assert len(selected) == 1
    assert selected[0]["ttm_id"] == 6
    assert selected[0]["ttm_source_available_date"] <= "2022-06-30"


def test_balance_special_cases_and_floor_sensitivity():
    profitable = row(1, ebit=10.0, fcf=1.0)
    profitable.update(cash=0.0, total_debt=40.0)
    assert method.balance_points(profitable, 4.0) == 0.0
    assert method.balance_points(profitable, 6.0) == pytest.approx(8.0 / 3.0)

    net_cash_burn = row(1, ebit=-1.0, fcf=-2.0)
    net_cash_burn.update(cash=20.0, total_debt=10.0)
    assert method.balance_points(net_cash_burn) == 5.0

    net_debt_loss = row(1, ebit=-1.0, fcf=2.0)
    net_debt_loss.update(cash=10.0, total_debt=20.0)
    assert method.balance_points(net_debt_loss) == 0.0


def test_dilution_evidence_classification_keeps_split_and_unresolved_distinct():
    assert method._dilution_evidence_classification(1.0, 1.1, 1.2, [], [{"split_ratio": 2.0}]) == "LOCAL_SPLIT_EVIDENCE"
    assert method._dilution_evidence_classification(1.0, 0.1, 0.2, [], []) == "UNRESOLVED"


def test_research_module_has_no_production_writer_or_swingmaster_dependency():
    source = inspect.getsource(method).lower()
    assert "mode=ro" in source
    assert "insert into" not in source
    assert "update score_result" not in source
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source
