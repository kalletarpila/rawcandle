from rawcandle.fundamentals.snapshot.diagnostic_boundary_cases import run_boundary_cases


def test_every_v2_diagnostic_boundary_and_input_gate_is_explicit() -> None:
    rows = run_boundary_cases()
    assert {row["flag"] for row in rows} == {
        "ABRUPT_FUNDAMENTAL_SHIFT",
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE",
        "CAPEX_INTENSITY_SHIFT_CANDIDATE",
        "NET_DEBT_SHIFT_CANDIDATE",
        "VALUATION_YIELD_OUTLIER",
        "RECENT_MARGIN_DECELERATION_REVIEW",
        "WORKING_CAPITAL_SHIFT_CANDIDATE",
    }
    assert all(row["passed"] for row in rows), [row for row in rows if not row["passed"]]
    for flag in {row["flag"] for row in rows}:
        cases = {row["case"] for row in rows if row["flag"] == flag}
        assert {
            "missing_current_input",
            "missing_comparison_input",
            "zero_denominator",
            "denominator_below_configured_floor",
            "negative_values_economically_permitted",
            "non_finite_input",
            "unsupported_accounting_classification",
        } <= cases
