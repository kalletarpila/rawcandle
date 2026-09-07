from dataclasses import asdict

import pytest

from rawcandle.fundamentals.operating_income_v2 import (
    activation,
    diagnostic_flags as seven,
    diagnostic_flags_eight as eight,
    phase10b,
    persistence,
    snapshot_eight,
    valuation,
)
from rawcandle.fundamentals.snapshot import renderer


def endpoint(**overrides) -> eight.DiagnosticEndpoint:
    values = {
        "company_id": 1,
        "quarter_id": 2,
        "fiscal_year": 2025,
        "fiscal_quarter": "Q2",
        "fiscal_sequence": 8102,
        "period_end": "2025-06-30",
        "source_available_date": "2025-08-01",
        "ttm_available_date": "2025-08-01",
        "valuation_available_date": "2025-08-01",
        "ttm_status": "TTM_READY",
        "revenue": 100_000_000.0,
        "operating_income": 10_000_000.0,
        "common_earnings": 8_000_000.0,
        "operating_cashflow": 9_000_000.0,
        "capex": -5_000_000.0,
        "cash": 20_000_000.0,
        "total_debt": 30_000_000.0,
        "accounts_receivable": 12_000_000.0,
        "inventory": 8_000_000.0,
        "accounts_payable": 7_000_000.0,
        "deferred_revenue": 3_000_000.0,
        "total_assets": 100_000_000.0,
        "trajectory": 8.0,
        "valuation_status": "VALUATION_FULL",
        "valuation_reason": "VALUATION_FULL",
        "applicability_classification": "SUPPORTED",
        "applicability_reason": "SUPPORTED_OPERATING_COMPANY",
        "operating_income_yield": 0.10,
        "fcf_yield": 0.08,
        "earnings_yield": 0.07,
        "ebit": 20_000_000.0,
        "ttm_endpoint_coherent": True,
    }
    values.update(overrides)
    return eight.DiagnosticEndpoint(**values)


def gap_result(**overrides):
    current = endpoint(**overrides)
    results = eight.evaluate_diagnostic_flags(
        eight.DiagnosticInput(current, None, False, False)
    )
    assert len(results) == 8
    return results[-1]


@pytest.mark.parametrize(
    ("gap", "status"),
    (
        (10_000_000.0 - 1e-6, eight.FlagStatus.CLEAR),
        (10_000_000.0, eight.FlagStatus.FLAGGED),
        (10_000_000.0 + 1e-6, eight.FlagStatus.FLAGGED),
        (-10_000_000.0, eight.FlagStatus.FLAGGED),
    ),
)
def test_non_operating_gap_binary64_boundary(gap, status) -> None:
    result = gap_result(ebit=10_000_000.0 + gap)
    evidence = {item.name: item.value for item in result.evidence}
    calculated_gap = (10_000_000.0 + gap) - 10_000_000.0
    assert result.status == status
    assert evidence["gap_amount"] == calculated_gap
    assert evidence["gap_abs_amount"] == abs(calculated_gap)
    assert evidence["gap_signed_to_revenue"] == calculated_gap / 100_000_000.0
    assert evidence["gap_abs_to_revenue"] == abs(calculated_gap) / 100_000_000.0
    assert evidence["boundary_operator"] == ">="


@pytest.mark.parametrize(
    ("revenue", "gap", "denominator", "status"),
    (
        (5_000_000.0, 999_999.0, 10_000_000.0, eight.FlagStatus.CLEAR),
        (5_000_000.0, 1_000_000.0, 10_000_000.0, eight.FlagStatus.FLAGGED),
        (10_000_000.0, 1_000_000.0, 10_000_000.0, eight.FlagStatus.FLAGGED),
        (20_000_000.0, 2_000_000.0, 20_000_000.0, eight.FlagStatus.FLAGGED),
    ),
)
def test_non_operating_gap_revenue_floor(revenue, gap, denominator, status) -> None:
    result = gap_result(revenue=revenue, operating_income=0.0, ebit=gap)
    evidence = {item.name: item.value for item in result.evidence}
    assert (result.status, evidence["revenue_denominator"]) == (status, denominator)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"ebit": None}, "TTM_EBIT_MISSING"),
        ({"ebit": float("inf")}, "TTM_EBIT_NON_FINITE"),
        ({"operating_income": None}, "TTM_OPERATING_INCOME_MISSING"),
        ({"operating_income": float("nan")}, "TTM_OPERATING_INCOME_NON_FINITE"),
        ({"revenue": None}, "TTM_REVENUE_MISSING"),
        ({"revenue": float("inf")}, "TTM_REVENUE_NON_FINITE"),
        ({"revenue": 0.0}, "TTM_REVENUE_NONPOSITIVE"),
        ({"revenue": -1.0}, "TTM_REVENUE_NONPOSITIVE"),
        ({"ttm_endpoint_coherent": False}, "TTM_ENDPOINT_INCOHERENT"),
        ({"ttm_endpoint_coherent": None}, "TTM_ENDPOINT_INCOHERENT"),
    ),
)
def test_non_operating_gap_not_ready_paths(overrides, reason) -> None:
    result = gap_result(**overrides)
    assert (result.status, result.reason_code, result.triggered) == (
        eight.FlagStatus.NOT_READY, reason, None,
    )


@pytest.mark.parametrize(
    ("gap", "direction", "code"),
    ((1.0, "UPLIFT", 1), (-1.0, "DRAG", -1), (0.0, "ZERO", 0)),
)
def test_non_operating_gap_direction_is_unambiguous(gap, direction, code) -> None:
    result = gap_result(operating_income=0.0, ebit=gap)
    evidence = {item.name: item.value for item in result.evidence}
    assert (evidence["gap_direction"], evidence["gap_direction_code"]) == (direction, code)


@pytest.mark.parametrize(
    ("sector", "industry", "classification", "status"),
    (
        ("Technology", "Software - Infrastructure", "SUPPORTED", eight.FlagStatus.FLAGGED),
        ("Financial Services", "Banks - Regional", "NOT_APPLICABLE", eight.FlagStatus.NOT_APPLICABLE),
        ("Financial Services", "Insurance - Life", "NOT_APPLICABLE", eight.FlagStatus.NOT_APPLICABLE),
        ("Real Estate", "REIT - Industrial", "NOT_APPLICABLE", eight.FlagStatus.NOT_APPLICABLE),
        ("Financial Services", "Shell Companies", "NOT_APPLICABLE", eight.FlagStatus.NOT_APPLICABLE),
        (None, None, "NOT_READY", eight.FlagStatus.NOT_READY),
    ),
)
def test_non_operating_gap_inherits_operating_model_applicability(
    sector, industry, classification, status
) -> None:
    applicability = valuation.classify_applicability(sector, industry)
    mapped = (
        "SUPPORTED" if applicability.supported is True
        else "NOT_APPLICABLE" if applicability.supported is False
        else "NOT_READY"
    )
    assert mapped == classification
    result = gap_result(
        applicability_classification=mapped,
        applicability_reason=applicability.reason_code,
    )
    assert result.status == status


def test_existing_seven_evaluations_are_economically_identical() -> None:
    current = endpoint()
    prior_values = asdict(current)
    prior_values.update(quarter_id=1, fiscal_quarter="Q1", fiscal_sequence=8101)
    prior = eight.DiagnosticEndpoint(**prior_values)
    inputs = eight.DiagnosticInput(current, prior, True, True)
    candidate = eight.evaluate_diagnostic_flags(inputs)[:7]
    active = seven.evaluate_diagnostic_flags(inputs)
    for before, after in zip(active, candidate, strict=True):
        assert (before.flag_name, before.status, before.reason_code, before.triggered) == (
            after.flag_name, after.status, after.reason_code, after.triggered,
        )
        assert before.evidence == after.evidence
    assert seven.MODEL_FINGERPRINT == "7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031"


def test_candidate_snapshot_definitions_are_contract_driven() -> None:
    definitions = renderer._build_diagnostic_definitions(
        eight.MODEL_CONTRACT, eight.FLAG_NAMES
    )
    assert len(definitions) == 8
    assert definitions[-1].flag_name == eight.FLAG_NAME
    assert "TTM EBIT" in definitions[-1].measurement
    assert "10 %" in definitions[-1].trigger


def test_candidate_has_new_identities_and_is_activation_eligible() -> None:
    assert eight.MODEL_FINGERPRINT != seven.MODEL_FINGERPRINT
    assert snapshot_eight.MODEL_FINGERPRINT != persistence.MODEL_MAP["snapshot"][1]
    assert phase10b.PACKAGE_FINGERPRINT != persistence.PACKAGE_FINGERPRINT
    assert phase10b.PACKAGE_FINGERPRINT in activation.known_packages()
    assert persistence.PACKAGE_FINGERPRINT == phase10b.ACTIVE_PACKAGE_FINGERPRINT
