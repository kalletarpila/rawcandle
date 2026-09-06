from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from rawcandle.fundamentals.score.engine import COMPONENTS, MODEL_CONTRACT
from rawcandle.fundamentals.snapshot.assembler import (
    CURRENT_PRICE_LABEL,
    REPORT_CONTRACT,
    _current_price_valuation,
    _resolve_ticker,
    SnapshotPaths,
    assemble_company_snapshot,
    assert_source_unchanged,
    four_observation_average,
    lifecycle_presentation,
    lifecycle_transition_status,
    strict_fiscal_slots,
    three_point_valuation_multiples,
    valuation_multiples_context,
)
from rawcandle.fundamentals.snapshot.renderer import render_snapshot, verify_rendered_report
from rawcandle.fundamentals.snapshot.writer import publish_report, report_filename


def _score(total: float) -> dict[str, object]:
    points = {name: MODEL_CONTRACT["components"][name]["maximum"] for name in COMPONENTS}
    scale = total / sum(points.values())
    return {
        "total_score": total,
        "readiness_status": "SCORE_FULL",
        "components": {
            name: {"component_score": maximum * scale, "evidence": {"metric_value": 0.1}}
            for name, maximum in points.items()
        },
    }


def _valuation(total: float, price: float) -> dict[str, object]:
    return {
        "valuation_status": "VALUATION_FULL",
        "reason_code": "VALUATION_FULL",
        "price_date": "2026-08-14",
        "price_age_calendar_days": 0,
        "selected_price": price,
        "ebit_yield": 0.08,
        "fcf_yield": 0.07,
        "earnings_yield": 0.06,
        "ebit_points": total * 0.4,
        "fcf_points": total * 0.4,
        "earnings_points": total * 0.2,
        "total_valuation_score": total,
    }


def _diagnostics() -> list[dict[str, object]]:
    names = (
        "ABRUPT_FUNDAMENTAL_SHIFT",
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE",
        "CAPEX_INTENSITY_SHIFT_CANDIDATE",
        "NET_DEBT_SHIFT_CANDIDATE",
        "VALUATION_YIELD_OUTLIER",
        "RECENT_MARGIN_DECELERATION_REVIEW",
        "WORKING_CAPITAL_SHIFT_CANDIDATE",
    )
    return [
        {
            "flag_name": name,
            "status": "EVALUATED_FLAGGED" if index == 0 else "EVALUATED_CLEAR",
            "reason_code": "TEST_REASON",
            "evidence": {
                "metric_value": 0.0197,
                "threshold": 0.1,
                "revenue_shift_ratio": 0.25,
                "ebit_shift_ratio": 0.15,
            },
        }
        for index, name in enumerate(names)
    ]


def _snapshot() -> dict[str, object]:
    history = []
    for index, quarter in enumerate(("Q2", "Q3", "Q4", "Q1", "Q2")):
        year = 2025 if index < 3 else 2026
        score = _score(70.0 + index)
        history.append({
            "label": ("YoY base", "t−3", "t−2", "t−1", "Nykyinen")[index],
            "fiscal_year": year,
            "fiscal_quarter": quarter,
            "availability_date": f"2026-0{index + 1}-15",
            "score": score,
            "valuation": _valuation(50.0 + index, 10.0 + index),
            "ttm": {"blocker_codes_json": "[]"},
            "score_raw": {
                "revenue_growth_yoy_ttm": 0.1,
                "ebit_margin_ttm": 0.2,
                "ebit_margin_direction": 0.01,
                "fcf_margin_ttm": 0.15,
                "balance_sheet_branch": "NET_DEBT_TO_EBIT",
                "balance_sheet_value": 1.25,
                "shares_outstanding_yoy_change": 0.02,
                "fundamental_trajectory": 8.0,
            },
        })
    delta_components = [
        {"component_name": name, "qoq_delta": 1.0, "two_quarter_delta": 2.0, "yoy_delta": 4.0}
        for name in COMPONENTS
    ]
    lifecycle_history = [
        {"fiscal_year": 2024 + ((index + 2) // 4), "fiscal_quarter": f"Q{(index + 2) % 4 + 1}", "row": {
            "raw_state": "GROWTH", "final_state": "GROWTH",
            "lifecycle_status": "LIFECYCLE_READY", "reason_code": "CLASSIFIED_GROWTH",
            "source_available_date": "2026-08-15",
        }, "transition_status": "NO_PENDING_TRANSITION"}
        for index in range(4)
    ]
    current_values = {
        "ttm_revenue": 500_000_000.0, "ttm_ebit": 100_000_000.0,
        "ttm_operating_cashflow": 90_000_000.0, "ttm_capex": -10_000_000.0,
        "ttm_free_cashflow": 80_000_000.0, "ttm_net_income_common": 70_000_000.0,
        "cash": 50_000_000.0, "total_debt": 20_000_000.0, "net_debt": -30_000_000.0,
        "total_assets": 600_000_000.0, "accounts_receivable": 20_000_000.0,
        "inventory": 10_000_000.0, "accounts_payable": 8_000_000.0,
        "deferred_revenue": 2_000_000.0, "operating_net_working_capital": 20_000_000.0,
        "shares_outstanding": 100_000_000.0,
    }
    diagnostics = _diagnostics()
    current_price_valuation = {
        **_valuation(60.0, 12.0),
        "label": CURRENT_PRICE_LABEL,
        "price_date": "2026-09-04",
        "price_age_calendar_days": 2,
        "diagnostic_selected_price": 12.0,
        "diagnostic_price_eligible": True,
    }
    for slot, values in zip(history, (current_values,) * len(history)):
        slot["ttm"] = {
            **values,
            "endpoint_quarter_id": history.index(slot) + 1,
            "blocker_codes_json": "[]",
            "net_income_common_4q_ready": 1,
        }
        slot["valuation"].update(
            shares_outstanding=values["shares_outstanding"],
            total_debt=values["total_debt"],
            cash=values["cash"],
            ttm_ebit=values["ttm_ebit"],
            ttm_free_cashflow=values["ttm_free_cashflow"],
            ttm_net_income_common=values["ttm_net_income_common"],
            market_cap=slot["valuation"]["selected_price"]
            * values["shares_outstanding"],
        )
        slot["valuation"]["enterprise_value"] = (
            slot["valuation"]["market_cap"]
            + values["total_debt"]
            - values["cash"]
        )
    valuation_multiples = three_point_valuation_multiples(
        history=history,
        current_price_valuation=current_price_valuation,
    )
    return {
        "report_contract": REPORT_CONTRACT,
        "report_date": "2026-09-06",
        "history_notice": "Currently revised history — not original point-in-time history",
        "identity": {"ticker": "TEST", "company_name": "TEST INC", "sector": "Technology", "industry": "Software", "taxonomy_memberships": []},
        "anchor": {"company_id": 1, "quarter_id": 5, "fiscal_year": 2026, "fiscal_quarter": "Q2", "period_end": "2026-06-30", "source_availability_date": "2026-08-14", "fundamental_age_days": 23, "ttm_readiness": "TTM_READY"},
        "history": history,
        "delta": {"total": {"qoq_delta": 7.0, "two_quarter_delta": 14.0, "yoy_delta": 28.0, "qoq_status": "DELTA_READY", "two_quarter_status": "DELTA_READY", "yoy_status": "DELTA_READY"}, "components": delta_components},
        "lifecycle": {
            "history": lifecycle_history,
            "current_status": "LIFECYCLE_READY",
            "confirmed_state": "GROWTH",
            "tenure_quarters": 4,
            "active_since_fiscal_year": 2025,
            "active_since_fiscal_quarter": "Q3",
            "active_since_available_date": "2025-11-01",
            "candidate_state": None,
            "candidate_count": 0,
        },
        "valuation_four_observation_average": 52.5,
        "valuation_four_observation_count": 4,
        "current_price_valuation": current_price_valuation,
        "valuation_multiples": valuation_multiples,
        "relative_position": {"available": True, "rows": [
            {"measure": measure, "peer_scope": scope, "percentile": 75.0, "peer_count": 100, "peer_group_id": "ALL" if scope == "UNIVERSE" else "Technology", "snapshot_date": "2026-09-01"}
            for measure in ("FUNDAMENTAL_SCORE", "ABSOLUTE_VALUATION_SCORE")
            for scope in ("UNIVERSE", "SECTOR", "INDUSTRY")
        ], "coverage": [
            {"measure": measure, "peer_scope": "ECOSYSTEM", "coverage_status": "NOT_ECOSYSTEM_MEMBER", "reason_code": "NO_QUALIFYING_CORE_OR_EXTENDED_MEMBERSHIP"}
            for measure in ("FUNDAMENTAL_SCORE", "ABSOLUTE_VALUATION_SCORE")
        ]},
        "diagnostic": {"evaluations": diagnostics},
        "diagnostic_counts": {"EVALUATED_FLAGGED": 1, "EVALUATED_CLEAR": 6, "FLAG_NOT_READY": 0, "FLAG_NOT_APPLICABLE": 0},
        "absolute_values": {"yoy_base": current_values, "previous": current_values, "current": current_values},
        "component_contract": {name: MODEL_CONTRACT["components"][name]["maximum"] for name in COMPONENTS},
        "model_fingerprints": {name: f"{name}-fingerprint" for name in ("score", "lifecycle", "valuation", "delta", "relative_position", "diagnostic_flags")},
        "source_state": {"score": [1, "source"]},
        "source_state_fingerprint": "source-fingerprint",
    }


def _market() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE osakedata(osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL)")
    return connection


def _anchor(**changes: object) -> dict[str, object]:
    value = {
        "company_id": 1, "security_id": 2, "endpoint_fiscal_year": 2026,
        "endpoint_fiscal_quarter": "Q2", "endpoint_quarter_id": 5,
        "period_end": "2026-06-30", "readiness_status": "TTM_READY",
        "blocker_codes_json": "[]", "ttm_ebit": 100.0, "ttm_free_cashflow": 80.0,
        "ttm_net_income_common": 60.0, "net_income_common_4q_ready": 1,
        "shares_outstanding": 100.0, "cash": 10.0, "total_debt": 20.0,
        "ttm_source_available_date": "2026-08-14",
    }
    value.update(changes)
    return value


def test_strict_fiscal_selection_preserves_missing_slots_and_supports_eight() -> None:
    rows = [{"fiscal_year": 2025, "fiscal_quarter": "Q4", "value": 1}, {"fiscal_year": 2026, "fiscal_quarter": "Q2", "value": 2}]
    five = strict_fiscal_slots(rows, anchor_year=2026, anchor_quarter="Q2", count=5)
    assert [(row["fiscal_year"], row["fiscal_quarter"]) for row in five] == [(2025, "Q2"), (2025, "Q3"), (2025, "Q4"), (2026, "Q1"), (2026, "Q2")]
    assert five[3]["row"] is None and five[2]["row"]["value"] == 1
    assert len(strict_fiscal_slots(rows, anchor_year=2026, anchor_quarter="Q2", count=8)) == 8


def test_four_observation_average_requires_exactly_four_complete_values() -> None:
    assert four_observation_average([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert four_observation_average([1.0, None, 3.0, 4.0]) is None
    assert four_observation_average([1.0, 2.0, 3.0]) is None


def test_renderer_contains_all_contract_sections_components_raw_values_and_statuses() -> None:
    rendered = render_snapshot(_snapshot())
    assert verify_rendered_report(rendered)
    for heading in (
        "Fundamental Score -historia", "Fundamental-komponenttien pistehistoria",
        "Fundamental raw -mittarihistoria", "Fundamental Delta ja komponenttien kontribuutiot",
        "Absoluuttiset fundamenttiarvot", "Lifecycle-historia",
        "Filing-date Valuation Score -historia", "Valuation-komponenttien pistehistoria",
        "Valuation raw-yield -historia", "Filing-date Valuation comparisons",
        "Indicative current-price valuation", "Three-point valuation multiples",
        "Relative Position", "Diagnostic Flags",
        "Data readiness ja rajoitteet", "Tekninen liite",
    ):
        assert f"## {heading}" in rendered.markdown
    assert "NET_DEBT_TO_EBIT: 1.25x" in rendered.markdown
    assert "EBIT Margin Direction (YoY)" in rendered.markdown
    assert "t−4 (YoY comparison)" in rendered.markdown
    assert "Capex spend" in rendered.markdown
    assert "FCF / Market Cap" in rendered.markdown
    assert "Positive components" in rendered.markdown
    for metric in (
        "Market Capitalization", "Enterprise Value", "P/E", "Earnings Yield",
        "P/FCF", "FCF Yield", "EV/EBIT", "EBIT Yield", "EV/Sales", "P/S",
    ):
        assert f"| {metric} |" in rendered.markdown
    assert "1.20 B" in rendered.markdown
    assert "3/3" in rendered.markdown
    assert "Ei aktiivista ekosysteemijäsenyyttä" in rendered.markdown
    assert "Currently revised history — not original point-in-time history" in rendered.markdown
    assert "TEST_REASON" in rendered.markdown
    assert "None" not in rendered.markdown and "NaN" not in rendered.markdown
    assert "GAAP disruption" not in rendered.markdown


def test_renderer_is_byte_deterministic_and_missing_four_average_is_visible() -> None:
    snapshot = _snapshot()
    snapshot["valuation_four_observation_average"] = None
    snapshot["valuation_four_observation_count"] = 3
    first = render_snapshot(snapshot)
    second = render_snapshot(deepcopy(snapshot))
    assert first == second
    assert "— (3/4)" in first.markdown


def test_renderer_handles_required_presentation_edge_cases() -> None:
    snapshot = _snapshot()
    snapshot["history"][-1]["score"]["components"]["REVENUE_GROWTH"]["component_score"] = 20.0
    snapshot["history"][-1]["ttm"]["ttm_revenue"] = 500_000_000.0
    snapshot["history"][-1]["score_raw"]["revenue_growth_yoy_ttm"] = 1.5
    snapshot["history"][-1]["score_raw"]["revenue_growth_comparison_base"] = 1_000_000.0
    snapshot["history"][-1]["score_raw"]["shares_outstanding_yoy_change"] = -0.000001
    snapshot["history"][-1]["valuation"].update({
        "total_valuation_score": 100.0,
        "ebit_points": 40.0,
        "fcf_points": 40.0,
        "earnings_points": 20.0,
    })
    snapshot["identity"]["taxonomy_memberships"] = [
        {"ecosystem_name": "AI", "peer_group_name": "Accelerators", "membership_role": "CORE"},
        {"ecosystem_name": "Data Center", "peer_group_name": "Power", "membership_role": "EXTENDED"},
    ]

    markdown = render_snapshot(snapshot).markdown

    assert "Pistekatossa nykyisessä endpointissa: Revenue Growth" in markdown
    assert "Kokonaispiste on 100" in markdown
    assert "Base effect -huomio:" in markdown and "vertailupohja 1.00 M" in markdown
    assert "| Net cash | 30.00 M |" in markdown
    assert "| AI | Accelerators | CORE |" in markdown
    assert "| Data Center | Power | EXTENDED |" in markdown
    assert "-0.00" not in markdown and "+0.00" not in markdown


def test_three_point_renderer_distinguishes_na_nm_and_preserves_small_yield() -> None:
    snapshot = _snapshot()
    current, latest, previous = snapshot["valuation_multiples"]["contexts"]
    current["metrics"]["earnings_yield"] = {
        "status": "VALUE",
        "value": 0.00000123,
    }
    latest["metrics"]["p_fcf"] = {"status": "N_M", "value": None}
    previous["metrics"]["p_fcf"] = {"status": "N_A", "value": None}

    markdown = render_snapshot(snapshot).markdown

    assert "0.0001 %" in markdown
    assert "| P/FCF |" in markdown and "N/M" in markdown and "N/A" in markdown
    assert "-0.00x" not in markdown and "-0.00 %" not in markdown


def test_three_point_section_is_part_of_report_content_fingerprint() -> None:
    snapshot = _snapshot()
    before = render_snapshot(snapshot)
    snapshot["valuation_multiples"]["contexts"][0]["metrics"]["pe"]["value"] += 1.0
    after = render_snapshot(snapshot)

    assert before.content_fingerprint != after.content_fingerprint
    assert before.markdown != after.markdown


def test_renderer_marks_missing_filing_price_comparison_endpoint() -> None:
    snapshot = _snapshot()
    snapshot["history"][0]["valuation"] = None

    markdown = render_snapshot(snapshot).markdown

    assert "| Absoluuttinen | +1.00 | +2.00 | — |" in markdown
    assert "| Prosentuaalinen | 7.69 % | 16.67 % | — |" in markdown


def test_current_price_valuation_uses_weekend_close_and_anchor_values() -> None:
    market = _market()
    market.execute("INSERT INTO osakedata VALUES('TEST','2026-09-04',9,11,8,10)")
    result = _current_price_valuation(market, ticker="TEST", report_date="2026-09-06", anchor=_anchor(), classification={"sector": "Technology", "industry": "Software"})
    assert result["valuation_status"] == "VALUATION_FULL"
    assert result["price_date"] == "2026-09-04" and result["price_age_calendar_days"] == 2
    assert result["market_cap"] == 1_000.0
    assert result["enterprise_value"] == 1_010.0
    assert result["fcf_yield"] == pytest.approx(0.08)


def test_current_price_accepts_seven_days_rejects_eight_and_never_looks_forward() -> None:
    market = _market()
    market.executemany("INSERT INTO osakedata VALUES('TEST',?,?,?,?,?)", [
        ("2026-08-30", 9, 11, 8, 10),
        ("2026-09-07", 9, 11, 8, 10),
    ])
    accepted = _current_price_valuation(market, ticker="TEST", report_date="2026-09-06", anchor=_anchor(), classification={"sector": "Technology", "industry": "Software"})
    assert accepted["valuation_status"] == "VALUATION_FULL" and accepted["price_date"] == "2026-08-30"
    stale = _current_price_valuation(market, ticker="TEST", report_date="2026-09-07", anchor=_anchor(), classification={"sector": "Technology", "industry": "Software"})
    assert stale["price_date"] == "2026-09-07"
    only_future = _market()
    only_future.execute("INSERT INTO osakedata VALUES('TEST','2026-09-07',9,11,8,10)")
    unavailable = _current_price_valuation(only_future, ticker="TEST", report_date="2026-09-06", anchor=_anchor(), classification={"sector": "Technology", "industry": "Software"})
    assert unavailable["valuation_status"] == "VALUATION_NOT_READY" and unavailable["reason_code"] == "PRICE_MISSING"
    old = _market()
    old.execute("INSERT INTO osakedata VALUES('TEST','2026-08-29',9,11,8,10)")
    unavailable = _current_price_valuation(old, ticker="TEST", report_date="2026-09-06", anchor=_anchor(), classification={"sector": "Technology", "industry": "Software"})
    assert unavailable["reason_code"] == "CURRENT_PRICE_FALLBACK_TOO_OLD"


def test_current_price_preserves_not_applicable_and_nonpositive_ev() -> None:
    market = _market()
    market.execute("INSERT INTO osakedata VALUES('TEST','2026-09-04',9,11,8,10)")
    reit = _current_price_valuation(market, ticker="TEST", report_date="2026-09-06", anchor=_anchor(), classification={"sector": "Real Estate", "industry": "REIT - Industrial"})
    assert reit["valuation_status"] == "VALUATION_NOT_APPLICABLE"
    negative_ev = _current_price_valuation(market, ticker="TEST", report_date="2026-09-06", anchor=_anchor(cash=2_000.0, total_debt=0.0), classification={"sector": "Technology", "industry": "Software"})
    assert negative_ev["reason_code"] == "ENTERPRISE_VALUE_NONPOSITIVE"


def _multiples_context(**changes: object) -> dict[str, object]:
    ttm = {
        "endpoint_quarter_id": 5,
        "shares_outstanding": 100.0,
        "total_debt": 20.0,
        "cash": 10.0,
        "ttm_revenue": 500.0,
        "ttm_ebit": 100.0,
        "ttm_free_cashflow": 80.0,
        "ttm_net_income_common": 50.0,
        "net_income_common_4q_ready": 1,
    }
    ttm.update(changes)
    return valuation_multiples_context(
        evaluation_point="TEST",
        ttm=ttm,
        valuation=None,
        fiscal_year=2026,
        fiscal_quarter="Q2",
        availability_date="2026-08-14",
        price_date="2026-08-14",
        price=10.0,
        price_eligible=True,
    )


def test_three_point_metric_formulas_and_reciprocals_use_unrounded_inputs() -> None:
    context = _multiples_context()
    metrics = context["metrics"]

    assert metrics["market_cap"] == {"status": "VALUE", "value": 1_000.0}
    assert metrics["enterprise_value"] == {"status": "VALUE", "value": 1_010.0}
    assert metrics["pe"]["value"] == pytest.approx(20.0)
    assert metrics["earnings_yield"]["value"] == pytest.approx(0.05)
    assert metrics["p_fcf"]["value"] == pytest.approx(12.5)
    assert metrics["fcf_yield"]["value"] == pytest.approx(0.08)
    assert metrics["ev_ebit"]["value"] == pytest.approx(10.1)
    assert metrics["ebit_yield"]["value"] == pytest.approx(100 / 1_010)
    assert metrics["ev_sales"]["value"] == pytest.approx(1_010 / 500)
    assert metrics["p_sales"]["value"] == pytest.approx(2.0)
    for multiple, yield_name in (
        ("pe", "earnings_yield"),
        ("p_fcf", "fcf_yield"),
        ("ev_ebit", "ebit_yield"),
    ):
        assert metrics[multiple]["value"] * metrics[yield_name]["value"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("field", "metric_names"),
    (
        ("ttm_net_income_common", ("pe", "earnings_yield")),
        ("ttm_free_cashflow", ("p_fcf", "fcf_yield")),
        ("ttm_ebit", ("ev_ebit", "ebit_yield")),
        ("ttm_revenue", ("ev_sales", "p_sales")),
    ),
)
@pytest.mark.parametrize("value", (0.0, -1.0))
def test_nonpositive_fundamental_is_not_meaningful(
    field: str, metric_names: tuple[str, str], value: float
) -> None:
    metrics = _multiples_context(**{field: value})["metrics"]
    assert [metrics[name]["status"] for name in metric_names] == ["N_M", "N_M"]


def test_missing_inputs_are_na_and_nonpositive_ev_blocks_ev_ratios_only() -> None:
    missing_debt = _multiples_context(total_debt=None)["metrics"]
    assert missing_debt["market_cap"]["status"] == "VALUE"
    assert missing_debt["enterprise_value"]["status"] == "N_A"
    assert missing_debt["ev_ebit"]["status"] == "N_A"
    assert missing_debt["pe"]["status"] == "VALUE"

    nonpositive_ev = _multiples_context(cash=2_000.0, total_debt=0.0)["metrics"]
    assert nonpositive_ev["enterprise_value"]["value"] == -1_000.0
    assert nonpositive_ev["ev_ebit"]["status"] == "N_M"
    assert nonpositive_ev["ev_sales"]["status"] == "N_M"

    net_cash = _multiples_context(cash=200.0, total_debt=0.0)["metrics"]
    assert net_cash["enterprise_value"] == {"status": "VALUE", "value": 800.0}
    assert net_cash["ev_ebit"]["status"] == "VALUE"


def test_three_points_use_latest_base_and_exact_q_minus_one_base() -> None:
    snapshot = _snapshot()
    history = snapshot["history"]
    history[-2]["ttm"]["ttm_revenue"] = 321.0
    history[-2]["valuation"]["ttm_ebit"] = 42.0
    history[-1]["ttm"]["ttm_revenue"] = 654.0
    history[-1]["ttm"]["ttm_ebit"] = 84.0
    history[-1]["valuation"]["ttm_ebit"] = 84.0
    current = snapshot["current_price_valuation"]
    current["diagnostic_selected_price"] = 20.0

    contexts = three_point_valuation_multiples(
        history=history, current_price_valuation=current
    )["contexts"]

    assert contexts[0]["source_inputs"] == contexts[1]["source_inputs"]
    assert contexts[0]["price"] == 20.0
    assert contexts[1]["price"] == history[-1]["valuation"]["selected_price"]
    assert contexts[2]["source_inputs"]["ttm_revenue"] == 321.0
    assert contexts[2]["source_inputs"]["ttm_ebit"] == 42.0
    assert contexts[2]["fiscal_quarter"] == history[-2]["fiscal_quarter"]


def test_missing_exact_q_minus_one_is_not_substituted() -> None:
    snapshot = _snapshot()
    snapshot["history"][-2]["ttm"] = None
    snapshot["history"][-2]["valuation"] = None

    previous = three_point_valuation_multiples(
        history=snapshot["history"],
        current_price_valuation=snapshot["current_price_valuation"],
    )["contexts"][2]

    assert previous["fiscal_year"] is None
    assert all(metric["status"] == "N_A" for metric in previous["metrics"].values())


def test_not_ready_filing_and_stale_current_price_do_not_produce_price_metrics() -> None:
    snapshot = _snapshot()
    snapshot["history"][-2]["valuation"]["price_age_calendar_days"] = 4
    snapshot["current_price_valuation"].update(
        valuation_status="VALUATION_NOT_READY",
        diagnostic_price_eligible=False,
    )

    current, _latest, previous = three_point_valuation_multiples(
        history=snapshot["history"],
        current_price_valuation=snapshot["current_price_valuation"],
    )["contexts"]

    assert all(metric["status"] == "N_A" for metric in current["metrics"].values())
    assert all(metric["status"] == "N_A" for metric in previous["metrics"].values())


def test_not_applicable_status_is_preserved_for_valid_diagnostic_multiples() -> None:
    snapshot = _snapshot()
    latest = snapshot["history"][-1]
    latest["valuation"]["valuation_status"] = "VALUATION_NOT_APPLICABLE"

    context = three_point_valuation_multiples(
        history=snapshot["history"],
        current_price_valuation=snapshot["current_price_valuation"],
    )["contexts"][1]

    assert context["valuation_status"] == "VALUATION_NOT_APPLICABLE"
    assert context["metrics"]["market_cap"]["status"] == "VALUE"
    assert context["metrics"]["pe"]["status"] == "VALUE"


def test_exact_predecessor_uses_fiscal_identity_across_fiscal_year_boundary() -> None:
    snapshot = _snapshot()
    history = snapshot["history"]
    history[-2].update(fiscal_year=2026, fiscal_quarter="Q4")
    history[-1].update(fiscal_year=2027, fiscal_quarter="Q1")

    contexts = three_point_valuation_multiples(
        history=history,
        current_price_valuation=snapshot["current_price_valuation"],
    )["contexts"]

    assert (contexts[1]["fiscal_year"], contexts[1]["fiscal_quarter"]) == (2027, "Q1")
    assert (contexts[2]["fiscal_year"], contexts[2]["fiscal_quarter"]) == (2026, "Q4")


def test_ticker_resolution_is_case_insensitive_alias_aware_and_ambiguous_safe() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,active INTEGER); CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT);")
    connection.execute("INSERT INTO security VALUES(1,10,'BRK.B',1)")
    connection.execute("INSERT INTO ticker_alias VALUES(1,'OLD')")
    assert _resolve_ticker(connection, "brk.b")["ticker"] == "BRK.B"
    assert _resolve_ticker(connection, "old")["resolution"] == "TICKER_ALIAS"
    with pytest.raises(LookupError, match="UNKNOWN_TICKER"):
        _resolve_ticker(connection, "missing")
    connection.executemany("INSERT INTO security VALUES(?,?,?,1)", [(2, 20, "AAA",), (3, 30, "BBB",)])
    connection.executemany("INSERT INTO ticker_alias VALUES(?,?)", [(2, "DUP"), (3, "DUP")])
    with pytest.raises(LookupError, match="AMBIGUOUS_TICKER"):
        _resolve_ticker(connection, "dup")


def test_safe_atomic_publish_no_change_conflict_and_overwrite(tmp_path: Path) -> None:
    assert report_filename("BRK.B", "2026-09-06") == "BRK.B_2026-09-06.md"
    with pytest.raises(ValueError):
        report_filename("../BAD", "2026-09-06")
    with pytest.raises(ValueError):
        report_filename("TEST", "2026-99-99")
    first = publish_report(output_dir=tmp_path, ticker="TEST", report_date="2026-09-06", markdown="first\n")
    assert first.status == "CREATED" and first.path.read_text() == "first\n"
    assert publish_report(output_dir=tmp_path, ticker="TEST", report_date="2026-09-06", markdown="first\n").status == "NO_CHANGE"
    with pytest.raises(FileExistsError, match="USE_OVERWRITE"):
        publish_report(output_dir=tmp_path, ticker="TEST", report_date="2026-09-06", markdown="second\n")
    assert publish_report(output_dir=tmp_path, ticker="TEST", report_date="2026-09-06", markdown="second\n", overwrite=True).status == "OVERWRITTEN"
    assert not list(tmp_path.glob("*.tmp"))


def test_source_change_fails_closed() -> None:
    assert_source_unchanged({"score": [1]}, {"score": [1]})
    with pytest.raises(RuntimeError, match="SNAPSHOT_SOURCE_CHANGED_DURING_GENERATION"):
        assert_source_unchanged({"score": [1]}, {"score": [2]})


def _lifecycle_row(
    raw: str,
    final: str | None,
    *,
    status: str = "LIFECYCLE_READY",
    candidate: str | None = None,
    candidate_count: int = 0,
    last_confirmed: str | None = None,
) -> dict[str, object]:
    return {
        "raw_state": raw,
        "final_state": final,
        "lifecycle_status": status,
        "candidate_state": candidate,
        "candidate_count": candidate_count,
        "last_confirmed_state": last_confirmed,
    }


@pytest.mark.parametrize(
    ("row", "previous", "expected"),
    (
        (_lifecycle_row("MATURE", "MATURE"), _lifecycle_row("MATURE", "MATURE"), "NO_PENDING_TRANSITION"),
        (_lifecycle_row("SCALING", "MATURE", candidate="SCALING", candidate_count=1), _lifecycle_row("MATURE", "MATURE"), "PENDING_SCALING_1_OF_2"),
        (_lifecycle_row("SCALING", "SCALING"), _lifecycle_row("SCALING", "MATURE", candidate="SCALING", candidate_count=1), "CONFIRMED_SCALING_2_OF_2"),
        (_lifecycle_row("GROWTH", "MATURE", candidate="GROWTH", candidate_count=1), _lifecycle_row("SCALING", "MATURE", candidate="SCALING", candidate_count=1), "PENDING_GROWTH_1_OF_2; REPLACED_SCALING"),
        (_lifecycle_row("UNCLASSIFIED", None, status="LIFECYCLE_NOT_READY", last_confirmed="MATURE"), _lifecycle_row("SCALING", "MATURE", candidate="SCALING", candidate_count=1), "CANDIDATE_CLEARED_BY_UNCLASSIFIED"),
        (_lifecycle_row("DISTRESSED", "DISTRESSED"), _lifecycle_row("MATURE", "MATURE"), "IMMEDIATE_DISTRESSED_ENTRY"),
        (_lifecycle_row("MATURE", "DISTRESSED", candidate="MATURE", candidate_count=1), _lifecycle_row("DISTRESSED", "DISTRESSED"), "PENDING_MATURE_1_OF_2"),
    ),
)
def test_lifecycle_transition_status_uses_persisted_state_machine_fields(
    row: dict[str, object], previous: dict[str, object], expected: str
) -> None:
    assert lifecycle_transition_status(row, previous) == expected


def test_lifecycle_presentation_is_four_quarters_with_tenure_and_no_not_ready_fallback() -> None:
    rows = [
        {**_lifecycle_row("MATURE", "MATURE"), "fiscal_year": 2025, "fiscal_quarter": "Q4", "source_available_date": "2026-02-01"},
        {**_lifecycle_row("MATURE", "MATURE"), "fiscal_year": 2026, "fiscal_quarter": "Q1", "source_available_date": "2026-05-01"},
        {**_lifecycle_row("MATURE", "MATURE"), "fiscal_year": 2026, "fiscal_quarter": "Q2", "source_available_date": "2026-08-01"},
    ]
    ready = lifecycle_presentation(rows, anchor_year=2026, anchor_quarter="Q2")
    assert len(ready["history"]) == 4
    assert ready["tenure_quarters"] == 3
    assert (ready["active_since_fiscal_year"], ready["active_since_fiscal_quarter"]) == (2025, "Q4")

    rows[-1] = {
        **_lifecycle_row("UNCLASSIFIED", None, status="LIFECYCLE_NOT_READY", last_confirmed="MATURE"),
        "fiscal_year": 2026, "fiscal_quarter": "Q2", "source_available_date": "2026-08-01",
    }
    not_ready = lifecycle_presentation(rows, anchor_year=2026, anchor_quarter="Q2")
    assert not_ready["current_status"] == "LIFECYCLE_NOT_READY"
    assert not_ready["confirmed_state"] is None
    assert not_ready["tenure_quarters"] is None

    rows[-1]["final_state"] = "MATURE"
    not_ready_with_stale_final = lifecycle_presentation(
        rows, anchor_year=2026, anchor_quarter="Q2"
    )
    assert not_ready_with_stale_final["confirmed_state"] is None
    assert not_ready_with_stale_final["tenure_quarters"] is None


PRODUCTION_DATA = Path(__file__).resolve().parents[1] / "data"
PRODUCTION_PATHS = SnapshotPaths(
    canonical_db=PRODUCTION_DATA / "fundamentals_v4.db",
    analysis_db=PRODUCTION_DATA / "fundamentals_analysis.db",
    market_db=PRODUCTION_DATA / "osakedata.db",
    taxonomy_db=PRODUCTION_DATA / "analysis.db",
    provider_db=PRODUCTION_DATA / "fundamentals_provider.db",
)


@pytest.mark.parametrize("ticker", ("CRMD", "APD", "NVDA", "AAT", "BNC", "LEG"))
def test_production_sample_reconciles_read_only_when_sources_are_available(ticker: str) -> None:
    if not all(path.is_file() for path in PRODUCTION_PATHS.__dict__.values()):
        pytest.skip("Fundamentals V4 production databases are not present")
    snapshot = assemble_company_snapshot(PRODUCTION_PATHS, ticker=ticker, report_date="2026-09-06")
    assert snapshot["identity"]["ticker"] == ticker
    assert all(row["ok"] for row in snapshot["reconciliation"])
    if ticker in {"CRMD", "APD"}:
        working_capital = next(
            row for row in snapshot["diagnostic"]["evaluations"]
            if row["flag_name"] == "WORKING_CAPITAL_SHIFT_CANDIDATE"
        )
        expected = 0.0197 if ticker == "CRMD" else 0.0181
        assert working_capital["evidence"]["metric_value"] == pytest.approx(expected, abs=0.0001)
    if ticker == "NVDA":
        assert snapshot["identity"]["taxonomy_memberships"]
    if ticker == "AAT":
        assert snapshot["history"][-1]["valuation"]["valuation_status"] == "VALUATION_NOT_APPLICABLE"
    if ticker == "BNC":
        assert snapshot["history"][-1]["score"]["readiness_status"] == "SCORE_NOT_READY"
    if ticker == "LEG":
        assert snapshot["current_price_valuation"]["reason_code"] == "CURRENT_PRICE_FALLBACK_TOO_OLD"
