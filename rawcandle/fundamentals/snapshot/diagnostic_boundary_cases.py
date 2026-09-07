from __future__ import annotations

from dataclasses import replace
from typing import Any

from rawcandle.fundamentals.operating_income_v2.diagnostic_flags import (
    DiagnosticEndpoint,
    DiagnosticInput,
    evaluate_diagnostic_flags,
)


EPSILON = 1e-12


def _endpoint(*, current: bool) -> DiagnosticEndpoint:
    return DiagnosticEndpoint(
        company_id=1,
        quarter_id=2 if current else 1,
        fiscal_year=2024,
        fiscal_quarter="Q2" if current else "Q1",
        fiscal_sequence=8098 if current else 8097,
        period_end="2024-06-30" if current else "2024-03-31",
        source_available_date="2024-08-01" if current else "2024-05-01",
        ttm_available_date="2024-08-01" if current else "2024-05-01",
        valuation_available_date="2024-08-01" if current else "2024-05-01",
        ttm_status="TTM_READY",
        revenue=100_000_000.0,
        operating_income=10_000_000.0,
        common_earnings=10_000_000.0,
        operating_cashflow=10_000_000.0,
        capex=-5_000_000.0,
        cash=10_000_000.0,
        total_debt=10_000_000.0,
        accounts_receivable=10_000_000.0,
        inventory=10_000_000.0,
        accounts_payable=10_000_000.0,
        deferred_revenue=10_000_000.0,
        total_assets=100_000_000.0,
        trajectory=7.0,
        valuation_status="VALUATION_FULL",
        valuation_reason="VALUATION_FULL",
        applicability_classification="SUPPORTED",
        applicability_reason="SUPPORTED_NON_FINANCIAL",
        operating_income_yield=0.10,
        fcf_yield=0.10,
        earnings_yield=0.10,
    )


def _one(flag: str, current: DiagnosticEndpoint, prior: DiagnosticEndpoint | None) -> dict[str, Any]:
    result = next(
        item for item in evaluate_diagnostic_flags(DiagnosticInput(current, prior, prior is not None))
        if item.flag_name == flag
    )
    payload = result.to_dict()
    return {"status": payload["status"], "reason_code": payload["reason_code"], "evidence": payload["evidence"]}


def _record(rows: list[dict[str, Any]], *, flag: str, case: str, current: DiagnosticEndpoint, prior: DiagnosticEndpoint | None, expected_status: str) -> None:
    result = _one(flag, current, prior)
    rows.append({
        "flag": flag,
        "case": case,
        "expected_status": expected_status,
        "actual_status": result["status"],
        "reason_code": result["reason_code"],
        "metric_value": result["evidence"].get("metric_value"),
        "threshold": result["evidence"].get("threshold"),
        "passed": result["status"] == expected_status,
    })


def run_boundary_cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_current, base_prior = _endpoint(current=True), _endpoint(current=False)
    upper_flags = {
        "ABRUPT_FUNDAMENTAL_SHIFT": 0.20,
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE": 0.20,
        "CAPEX_INTENSITY_SHIFT_CANDIDATE": 0.10,
        "NET_DEBT_SHIFT_CANDIDATE": 0.50,
        "WORKING_CAPITAL_SHIFT_CANDIDATE": 0.10,
    }
    for flag, threshold in upper_flags.items():
        for label, metric, expected in (
            ("immediately_below_threshold", threshold - EPSILON, "EVALUATED_CLEAR"),
            ("exactly_at_threshold", threshold, "EVALUATED_FLAGGED"),
            ("immediately_above_threshold", threshold + EPSILON, "EVALUATED_FLAGGED"),
        ):
            current, prior = base_current, base_prior
            if flag == "ABRUPT_FUNDAMENTAL_SHIFT":
                current = replace(current, operating_income=10_000_000.0 + metric * 100_000_000.0)
            elif flag == "EARNINGS_CASH_DIVERGENCE_CANDIDATE":
                current = replace(current, common_earnings=10_000_000.0 + metric * 100_000_000.0)
            elif flag == "CAPEX_INTENSITY_SHIFT_CANDIDATE":
                prior = replace(prior, capex=0.0)
                current = replace(current, capex=-metric * 100_000_000.0)
            elif flag == "NET_DEBT_SHIFT_CANDIDATE":
                current = replace(current, total_debt=10_000_000.0 + metric * 100_000_000.0)
            else:
                current = replace(current, accounts_receivable=10_000_000.0 + metric * 100_000_000.0)
            _record(rows, flag=flag, case=label, current=current, prior=prior, expected_status=expected)

    for label, value, expected in (
        ("immediately_below_median_threshold", 0.25 - EPSILON, "EVALUATED_CLEAR"),
        ("exactly_at_median_threshold", 0.25, "EVALUATED_FLAGGED"),
        ("immediately_above_median_threshold", 0.25 + EPSILON, "EVALUATED_FLAGGED"),
    ):
        current = replace(base_current, operating_income_yield=value, fcf_yield=value, earnings_yield=value)
        _record(rows, flag="VALUATION_YIELD_OUTLIER", case=label, current=current, prior=base_prior, expected_status=expected)
    for label, value, expected in (
        ("immediately_below_maximum_threshold", 0.50 - EPSILON, "EVALUATED_CLEAR"),
        ("exactly_at_maximum_threshold", 0.50, "EVALUATED_FLAGGED"),
        ("immediately_above_maximum_threshold", 0.50 + EPSILON, "EVALUATED_FLAGGED"),
    ):
        current = replace(base_current, operating_income_yield=value, fcf_yield=0.0, earnings_yield=0.0)
        _record(rows, flag="VALUATION_YIELD_OUTLIER", case=label, current=current, prior=base_prior, expected_status=expected)

    margin_flag = "RECENT_MARGIN_DECELERATION_REVIEW"
    for label, change, expected in (
        ("immediately_below_margin_threshold", -0.02 - EPSILON, "EVALUATED_FLAGGED"),
        ("exactly_at_margin_threshold", -0.02, "EVALUATED_FLAGGED"),
        ("immediately_above_margin_threshold", -0.02 + EPSILON, "EVALUATED_CLEAR"),
    ):
        current = replace(base_current, operating_income=(0.10 + change) * 100_000_000.0)
        _record(rows, flag=margin_flag, case=label, current=current, prior=base_prior, expected_status=expected)
    for label, trajectory, expected in (
        ("immediately_below_trajectory_threshold", 7.0 - EPSILON, "EVALUATED_CLEAR"),
        ("exactly_at_trajectory_threshold", 7.0, "EVALUATED_FLAGGED"),
        ("immediately_above_trajectory_threshold", 7.0 + EPSILON, "EVALUATED_FLAGGED"),
    ):
        current = replace(base_current, trajectory=trajectory, operating_income=8_000_000.0)
        _record(rows, flag=margin_flag, case=label, current=current, prior=base_prior, expected_status=expected)

    missing_fields = {
        "ABRUPT_FUNDAMENTAL_SHIFT": "operating_income",
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE": "common_earnings",
        "CAPEX_INTENSITY_SHIFT_CANDIDATE": "capex",
        "NET_DEBT_SHIFT_CANDIDATE": "cash",
        "VALUATION_YIELD_OUTLIER": "operating_income_yield",
        "RECENT_MARGIN_DECELERATION_REVIEW": "trajectory",
        "WORKING_CAPITAL_SHIFT_CANDIDATE": "accounts_receivable",
    }
    for flag, field in missing_fields.items():
        current = replace(base_current, **{field: None})
        if flag == "VALUATION_YIELD_OUTLIER":
            current = replace(current, fcf_yield=None, earnings_yield=None)
        _record(rows, flag=flag, case="missing_current_input", current=current, prior=base_prior, expected_status="FLAG_NOT_READY")
        _record(rows, flag=flag, case="missing_comparison_input", current=base_current, prior=None, expected_status="EVALUATED_CLEAR" if flag == "VALUATION_YIELD_OUTLIER" else "FLAG_NOT_READY")
        current = replace(base_current, applicability_classification="NOT_APPLICABLE")
        _record(rows, flag=flag, case="unsupported_accounting_classification", current=current, prior=base_prior, expected_status="FLAG_NOT_APPLICABLE")

        if flag == "VALUATION_YIELD_OUTLIER":
            current = replace(base_current, operating_income_yield=float("inf"))
        else:
            current = replace(base_current, **{field: float("inf")})
        _record(rows, flag=flag, case="non_finite_input", current=current, prior=base_prior, expected_status="FLAG_NOT_READY")

        if flag == "WORKING_CAPITAL_SHIFT_CANDIDATE":
            current = replace(base_current, total_assets=0.0)
            expected = "FLAG_NOT_READY"
        elif flag == "VALUATION_YIELD_OUTLIER":
            current = replace(base_current, operating_income_yield=0.0, fcf_yield=0.0, earnings_yield=0.0)
            expected = "EVALUATED_CLEAR"
        else:
            current = replace(base_current, revenue=0.0)
            expected = "FLAG_NOT_APPLICABLE"
        _record(rows, flag=flag, case="zero_denominator", current=current, prior=base_prior, expected_status=expected)

        if flag in {"ABRUPT_FUNDAMENTAL_SHIFT", "EARNINGS_CASH_DIVERGENCE_CANDIDATE", "CAPEX_INTENSITY_SHIFT_CANDIDATE", "NET_DEBT_SHIFT_CANDIDATE"}:
            current = replace(base_current, revenue=1_000_000.0)
            prior = replace(base_prior, revenue=1_000_000.0)
        elif flag == "WORKING_CAPITAL_SHIFT_CANDIDATE":
            current = replace(base_current, total_assets=1_000_000.0)
            prior = replace(base_prior, total_assets=1_000_000.0)
        else:
            current, prior = base_current, base_prior
        _record(rows, flag=flag, case="denominator_below_configured_floor", current=current, prior=prior, expected_status="EVALUATED_CLEAR")

        if flag == "VALUATION_YIELD_OUTLIER":
            current = replace(base_current, operating_income_yield=-0.10, fcf_yield=-0.20, earnings_yield=-0.30)
        elif flag == "WORKING_CAPITAL_SHIFT_CANDIDATE":
            current = replace(base_current, accounts_receivable=-1_000_000.0)
        elif flag == "CAPEX_INTENSITY_SHIFT_CANDIDATE":
            current = replace(base_current, capex=-6_000_000.0)
        else:
            current = replace(base_current, operating_income=-1_000_000.0)
        negative_expected = (
            "EVALUATED_FLAGGED"
            if flag in {"RECENT_MARGIN_DECELERATION_REVIEW", "WORKING_CAPITAL_SHIFT_CANDIDATE"}
            else "EVALUATED_CLEAR"
        )
        _record(rows, flag=flag, case="negative_values_economically_permitted", current=current, prior=base_prior, expected_status=negative_expected)
    return rows
