from __future__ import annotations

import math
from dataclasses import replace

import pytest

from rawcandle.fundamentals.diagnostic_flags.engine import (
    FLAG_NAMES,
    MODEL_CONTRACT,
    MODEL_FINGERPRINT,
    DiagnosticEndpoint,
    DiagnosticInput,
    FlagStatus,
    canonical_json,
    evaluate_diagnostic_flags,
    fingerprint,
)


def endpoint(*, current: bool, **overrides) -> DiagnosticEndpoint:
    values = {
        "company_id": 1,
        "quarter_id": 2 if current else 1,
        "fiscal_year": 2025,
        "fiscal_quarter": "Q4" if current else "Q3",
        "fiscal_sequence": 8104 if current else 8103,
        "period_end": "2025-12-31" if current else "2025-09-30",
        "source_available_date": "2026-02-15" if current else "2025-11-15",
        "ttm_available_date": "2026-02-16" if current else "2025-11-16",
        "valuation_available_date": "2026-02-17" if current else "2025-11-17",
        "ttm_status": "TTM_READY",
        "revenue": 100_000_000.0,
        "ebit": 10_000_000.0,
        "common_earnings": 10_000_000.0,
        "operating_cashflow": 10_000_000.0,
        "capex": 0.0,
        "cash": 10_000_000.0,
        "total_debt": 20_000_000.0,
        "accounts_receivable": 10_000_000.0,
        "inventory": 10_000_000.0,
        "accounts_payable": 5_000_000.0,
        "deferred_revenue": 2_000_000.0,
        "total_assets": 100_000_000.0,
        "trajectory": 8.0 if current else None,
        "valuation_status": "VALUATION_FULL",
        "valuation_reason": "READY",
        "applicability_classification": "SUPPORTED",
        "applicability_reason": "SUPPORTED_OPERATING_CLASS",
        "ebit_yield": 0.10,
        "fcf_yield": 0.10,
        "earnings_yield": 0.10,
    }
    values.update(overrides)
    return DiagnosticEndpoint(**values)


def inputs(*, current=None, prior=None, consecutive=True) -> DiagnosticInput:
    return DiagnosticInput(current or endpoint(current=True), endpoint(current=False) if prior is None else prior, consecutive)


def flag(data: DiagnosticInput, name: str):
    return dict(zip(FLAG_NAMES, evaluate_diagnostic_flags(data), strict=True))[name]


@pytest.mark.parametrize(
    ("name", "metric", "expected"),
    [
        ("ABRUPT_FUNDAMENTAL_SHIFT", 0.199, FlagStatus.CLEAR),
        ("ABRUPT_FUNDAMENTAL_SHIFT", 0.200, FlagStatus.FLAGGED),
        ("ABRUPT_FUNDAMENTAL_SHIFT", 0.201, FlagStatus.FLAGGED),
        ("EARNINGS_CASH_DIVERGENCE_CANDIDATE", 0.199, FlagStatus.CLEAR),
        ("EARNINGS_CASH_DIVERGENCE_CANDIDATE", 0.200, FlagStatus.FLAGGED),
        ("EARNINGS_CASH_DIVERGENCE_CANDIDATE", 0.201, FlagStatus.FLAGGED),
        ("CAPEX_INTENSITY_SHIFT_CANDIDATE", 0.099, FlagStatus.CLEAR),
        ("CAPEX_INTENSITY_SHIFT_CANDIDATE", 0.100, FlagStatus.FLAGGED),
        ("CAPEX_INTENSITY_SHIFT_CANDIDATE", 0.101, FlagStatus.FLAGGED),
        ("NET_DEBT_SHIFT_CANDIDATE", 0.499, FlagStatus.CLEAR),
        ("NET_DEBT_SHIFT_CANDIDATE", 0.500, FlagStatus.FLAGGED),
        ("NET_DEBT_SHIFT_CANDIDATE", 0.501, FlagStatus.FLAGGED),
        ("VALUATION_YIELD_OUTLIER", 0.249, FlagStatus.CLEAR),
        ("VALUATION_YIELD_OUTLIER", 0.250, FlagStatus.FLAGGED),
        ("VALUATION_YIELD_OUTLIER", 0.251, FlagStatus.FLAGGED),
        ("RECENT_MARGIN_DECELERATION_REVIEW", -0.019, FlagStatus.CLEAR),
        ("RECENT_MARGIN_DECELERATION_REVIEW", -0.020, FlagStatus.FLAGGED),
        ("RECENT_MARGIN_DECELERATION_REVIEW", -0.021, FlagStatus.FLAGGED),
        ("WORKING_CAPITAL_SHIFT_CANDIDATE", 0.099, FlagStatus.CLEAR),
        ("WORKING_CAPITAL_SHIFT_CANDIDATE", 0.100, FlagStatus.FLAGGED),
        ("WORKING_CAPITAL_SHIFT_CANDIDATE", 0.101, FlagStatus.FLAGGED),
    ],
)
def test_every_flag_below_exactly_at_and_above_boundary(name, metric, expected):
    current = endpoint(current=True)
    if name == "ABRUPT_FUNDAMENTAL_SHIFT":
        current = replace(current, ebit=10_000_000.0 + metric * 100_000_000.0)
    elif name == "EARNINGS_CASH_DIVERGENCE_CANDIDATE":
        current = replace(current, common_earnings=10_000_000.0 + metric * 100_000_000.0)
    elif name == "CAPEX_INTENSITY_SHIFT_CANDIDATE":
        current = replace(current, capex=-metric * 100_000_000.0)
    elif name == "NET_DEBT_SHIFT_CANDIDATE":
        current = replace(current, total_debt=20_000_000.0 + metric * 100_000_000.0)
    elif name == "VALUATION_YIELD_OUTLIER":
        current = replace(current, ebit_yield=metric, fcf_yield=metric, earnings_yield=metric)
    elif name == "RECENT_MARGIN_DECELERATION_REVIEW":
        current = replace(current, ebit=(0.10 + metric) * 100_000_000.0)
    elif name == "WORKING_CAPITAL_SHIFT_CANDIDATE":
        current = replace(current, accounts_receivable=10_000_000.0 + metric * 100_000_000.0)
    assert flag(inputs(current=current), name).status == expected


def test_or_conditions_are_independent_for_abrupt_and_valuation():
    abrupt = flag(inputs(current=endpoint(current=True, revenue=125_000_000.0, ebit=10_000_000.0)), FLAG_NAMES[0])
    assert abrupt.status == FlagStatus.FLAGGED
    assert abrupt.to_dict()["evidence"]["revenue_trigger"] is True
    valuation = flag(
        inputs(current=endpoint(current=True, ebit_yield=0.50, fcf_yield=0.01, earnings_yield=0.01)),
        "VALUATION_YIELD_OUTLIER",
    )
    assert valuation.status == FlagStatus.FLAGGED
    assert valuation.to_dict()["evidence"] == {
        **valuation.to_dict()["evidence"],
        "maximum_trigger": True,
        "median_trigger": False,
    }


def test_capex_uses_absolute_sign_and_separate_ten_million_revenue_floors():
    data = inputs(
        current=endpoint(current=True, revenue=5_000_000.0, capex=-2_000_000.0),
        prior=endpoint(current=False, revenue=2_000_000.0, capex=500_000.0),
    )
    result = flag(data, "CAPEX_INTENSITY_SHIFT_CANDIDATE")
    evidence = result.to_dict()["evidence"]
    assert result.status == FlagStatus.FLAGGED
    assert evidence["current_denominator"] == evidence["prior_denominator"] == 10_000_000.0
    assert evidence["current_capex_intensity"] == 0.2
    assert evidence["prior_capex_intensity"] == 0.05


def test_margin_allows_negative_ebit_and_flags_crossing_below_zero():
    result = flag(
        inputs(
            current=endpoint(current=True, ebit=-3_000_000.0),
            prior=endpoint(current=False, ebit=1_000_000.0),
        ),
        "RECENT_MARGIN_DECELERATION_REVIEW",
    )
    assert result.status == FlagStatus.FLAGGED
    assert result.to_dict()["evidence"]["signed_margin_change"] == pytest.approx(-0.04)


def test_working_capital_retains_signed_change_but_threshold_uses_absolute_change():
    result = flag(
        inputs(current=endpoint(current=True, accounts_receivable=0.0)),
        "WORKING_CAPITAL_SHIFT_CANDIDATE",
    )
    evidence = result.to_dict()["evidence"]
    assert result.status == FlagStatus.FLAGGED
    assert evidence["signed_delta_onwc"] == -10_000_000.0
    assert evidence["metric_value"] == 0.10


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_nonpositive_revenue_is_not_applicable(value):
    result = flag(inputs(current=endpoint(current=True, revenue=value)), FLAG_NAMES[0])
    assert (result.status, result.reason_code) == (FlagStatus.NOT_APPLICABLE, "NONPOSITIVE_REVENUE")


def test_missing_current_comparison_and_nonfinite_are_not_ready_not_clear():
    missing_current = flag(inputs(current=endpoint(current=True, ebit=None)), FLAG_NAMES[0])
    missing_prior = flag(inputs(prior=endpoint(current=False, ebit=None)), FLAG_NAMES[0])
    invalid = flag(inputs(current=endpoint(current=True, ebit=math.inf)), FLAG_NAMES[0])
    assert (missing_current.status, missing_current.reason_code) == (FlagStatus.NOT_READY, "REQUIRED_INPUT_MISSING")
    assert (missing_prior.status, missing_prior.reason_code) == (FlagStatus.NOT_READY, "REQUIRED_INPUT_MISSING")
    assert (invalid.status, invalid.reason_code) == (FlagStatus.NOT_READY, "REQUIRED_INPUT_NON_FINITE")


def test_missing_prior_and_nonconsecutive_chain_are_explicit():
    no_prior = DiagnosticInput(endpoint(current=True), None, False)
    assert flag(no_prior, FLAG_NAMES[0]).reason_code == "PRIOR_FISCAL_ENDPOINT_MISSING"
    broken = inputs(consecutive=False)
    assert flag(broken, FLAG_NAMES[0]).reason_code == "NON_CONSECUTIVE_FISCAL_CHAIN"
    assert flag(broken, "WORKING_CAPITAL_SHIFT_CANDIDATE").status == FlagStatus.NOT_READY


@pytest.mark.parametrize("assets", [0.0, -1.0])
def test_zero_and_negative_total_assets_are_not_ready(assets):
    result = flag(inputs(current=endpoint(current=True, total_assets=assets)), "WORKING_CAPITAL_SHIFT_CANDIDATE")
    assert (result.status, result.reason_code) == (FlagStatus.NOT_READY, "TOTAL_ASSETS_NOT_STRICTLY_POSITIVE")


def test_incomplete_onwc_is_not_imputed_and_observed_zero_is_valid():
    missing = flag(inputs(current=endpoint(current=True, inventory=None)), "WORKING_CAPITAL_SHIFT_CANDIDATE")
    zero = flag(inputs(current=endpoint(current=True, inventory=0.0)), "WORKING_CAPITAL_SHIFT_CANDIDATE")
    assert missing.status == FlagStatus.NOT_READY
    assert zero.status in (FlagStatus.CLEAR, FlagStatus.FLAGGED)


def test_unsupported_accounting_class_is_not_applicable_to_operating_flags():
    current = endpoint(
        current=True,
        applicability_classification="NOT_APPLICABLE",
        applicability_reason="UNSUPPORTED_REIT",
        valuation_status="VALUATION_NOT_APPLICABLE",
    )
    results = evaluate_diagnostic_flags(inputs(current=current))
    assert all(item.status == FlagStatus.NOT_APPLICABLE for item in results)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("VALUATION_NOT_READY", FlagStatus.NOT_READY), ("VALUATION_NOT_APPLICABLE", FlagStatus.NOT_APPLICABLE)],
)
def test_valuation_readiness_is_propagated(status, expected):
    result = flag(inputs(current=endpoint(current=True, valuation_status=status)), "VALUATION_YIELD_OUTLIER")
    assert result.status == expected


def test_effective_dates_use_required_authoritative_sources():
    data = inputs()
    abrupt = flag(data, FLAG_NAMES[0])
    valuation = flag(data, "VALUATION_YIELD_OUTLIER")
    working_capital = flag(data, "WORKING_CAPITAL_SHIFT_CANDIDATE")
    assert abrupt.effective_available_date == "2026-02-16"
    assert valuation.effective_available_date == "2026-02-17"
    assert working_capital.effective_available_date == "2026-02-15"


def test_invalid_fiscal_identities_and_cross_company_comparison_are_rejected():
    with pytest.raises(ValueError, match="CURRENT_FISCAL_IDENTITY_INVALID"):
        evaluate_diagnostic_flags(inputs(current=endpoint(current=True, fiscal_quarter="BAD")))
    with pytest.raises(ValueError, match="PRIOR_FISCAL_IDENTITY_INVALID"):
        evaluate_diagnostic_flags(inputs(prior=endpoint(current=False, fiscal_sequence=999)))
    with pytest.raises(ValueError, match="CROSS_COMPANY_COMPARISON"):
        evaluate_diagnostic_flags(inputs(prior=endpoint(current=False, company_id=2)))
    with pytest.raises(ValueError, match="FISCAL_CHAIN_CONSISTENCY_INVALID"):
        evaluate_diagnostic_flags(inputs(prior=endpoint(current=False, fiscal_year=2025, fiscal_quarter="Q2", fiscal_sequence=8102)))


def test_reason_evidence_and_fingerprints_are_deterministic_and_compact():
    first = evaluate_diagnostic_flags(inputs())
    second = evaluate_diagnostic_flags(inputs())
    assert tuple(item.to_json() for item in first) == tuple(item.to_json() for item in second)
    assert all(tuple(item.name for item in row.evidence) == tuple(sorted(item.name for item in row.evidence)) for row in first)
    assert MODEL_FINGERPRINT == fingerprint(MODEL_CONTRACT)
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert "VALUATION_YIELD_DIVERGENCE_REVIEW" not in FLAG_NAMES
    assert len(FLAG_NAMES) == 7
    serialized = canonical_json([item.to_dict() for item in first])
    assert "combined_score" not in serialized
    assert "severity" not in serialized


def test_crmd_and_apd_numeric_regression_profiles():
    crmd = inputs(
        current=endpoint(
            current=True,
            ebit=8_000_000.0,
            ebit_yield=0.55,
            fcf_yield=0.30,
            earnings_yield=0.25,
            accounts_receivable=13_930_000.0,
        ),
        prior=endpoint(current=False, ebit=11_000_000.0),
    )
    crmd_results = dict(zip(FLAG_NAMES, evaluate_diagnostic_flags(crmd), strict=True))
    assert crmd_results["VALUATION_YIELD_OUTLIER"].status == FlagStatus.FLAGGED
    assert crmd_results["RECENT_MARGIN_DECELERATION_REVIEW"].status == FlagStatus.FLAGGED
    assert crmd_results["WORKING_CAPITAL_SHIFT_CANDIDATE"].status == FlagStatus.CLEAR
    assert crmd_results["WORKING_CAPITAL_SHIFT_CANDIDATE"].to_dict()["evidence"]["metric_value"] == pytest.approx(0.0393)

    apd = inputs(
        current=endpoint(current=True, ebit=35_000_000.0, common_earnings=-15_000_000.0, accounts_receivable=15_930_000.0),
    )
    apd_results = dict(zip(FLAG_NAMES, evaluate_diagnostic_flags(apd), strict=True))
    assert apd_results["ABRUPT_FUNDAMENTAL_SHIFT"].status == FlagStatus.FLAGGED
    assert apd_results["EARNINGS_CASH_DIVERGENCE_CANDIDATE"].status == FlagStatus.FLAGGED
    assert apd_results["WORKING_CAPITAL_SHIFT_CANDIDATE"].status == FlagStatus.CLEAR
    assert apd_results["WORKING_CAPITAL_SHIFT_CANDIDATE"].to_dict()["evidence"]["metric_value"] == pytest.approx(0.0593)
