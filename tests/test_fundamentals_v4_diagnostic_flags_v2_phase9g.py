from dataclasses import fields
import inspect

import pytest

from rawcandle.fundamentals.diagnostic_flags import engine as v1
from rawcandle.fundamentals.operating_income_v2 import diagnostic_flags as v2
from rawcandle.fundamentals.operating_income_v2.rehearsal import _diagnostic_endpoint


def endpoint(*, current: bool, **overrides) -> v2.DiagnosticEndpoint:
    values = {
        "company_id": 1,
        "quarter_id": 2 if current else 1,
        "fiscal_year": 2025,
        "fiscal_quarter": "Q2" if current else "Q1",
        "fiscal_sequence": 8102 if current else 8101,
        "period_end": "2025-06-30" if current else "2025-03-31",
        "source_available_date": "2025-08-01" if current else "2025-05-01",
        "ttm_available_date": "2025-08-01" if current else "2025-05-01",
        "valuation_available_date": "2025-08-01" if current else "2025-05-01",
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
    }
    values.update(overrides)
    return v2.DiagnosticEndpoint(**values)


def evaluate(flag: str, current: v2.DiagnosticEndpoint, prior: v2.DiagnosticEndpoint | None):
    results = v2.evaluate_diagnostic_flags(v2.DiagnosticInput(current, prior, prior is not None))
    return dict(zip(v2.FLAG_NAMES, results, strict=True))[flag]


def test_endpoint_builder_wires_canonical_working_capital_fields_and_preserves_zero() -> None:
    source = {
        "company_id": 9, "endpoint_quarter_id": 99, "endpoint_fiscal_year": 2025,
        "endpoint_fiscal_quarter": "Q4", "period_end": "2025-12-31",
        "ttm_source_available_date": "2026-02-01", "core_ttm_ready": 1,
        "quarter_source_available_date": "2026-02-01",
        "ttm_revenue": 1.0, "ttm_operating_income": 2.0,
        "ttm_net_income_common": 3.0, "ttm_operating_cashflow": 4.0,
        "ttm_capex": -5.0, "cash": 6.0, "total_debt": 7.0,
        "accounts_receivable": 0.0, "inventory": 8.0,
        "accounts_payable": 9.0, "deferred_revenue": 10.0,
        "total_assets": 11.0,
    }
    result = _diagnostic_endpoint(
        source, valuation_result=None, trajectory=None,
        applicability_classification="SUPPORTED",
        applicability_reason="SUPPORTED_OPERATING_COMPANY",
    )
    assert (
        result.accounts_receivable, result.inventory, result.accounts_payable,
        result.deferred_revenue, result.total_assets,
    ) == (0.0, 8.0, 9.0, 10.0, 11.0)


@pytest.mark.parametrize(
    ("ratio", "status"),
    (
        (0.10 - 1e-12, v2.FlagStatus.CLEAR),
        (0.10, v2.FlagStatus.FLAGGED),
        (0.10 + 1e-12, v2.FlagStatus.FLAGGED),
    ),
)
def test_working_capital_binary64_threshold(ratio: float, status: v2.FlagStatus) -> None:
    prior = endpoint(current=False, accounts_receivable=0.0, inventory=0.0, accounts_payable=0.0, deferred_revenue=0.0)
    current = endpoint(current=True, accounts_receivable=ratio * 100_000_000.0, inventory=0.0, accounts_payable=0.0, deferred_revenue=0.0)
    result = evaluate(v2.FLAG_NAMES[6], current, prior)
    assert result.status == status
    assert dict((item.name, item.value) for item in result.evidence)["boundary_operator"] == ">="


@pytest.mark.parametrize(
    ("current", "prior", "consecutive", "status", "reason"),
    (
        (endpoint(current=True, inventory=None), endpoint(current=False), True, v2.FlagStatus.NOT_READY, "REQUIRED_INPUT_MISSING"),
        (endpoint(current=True, total_assets=0.0), endpoint(current=False), True, v2.FlagStatus.NOT_READY, "TOTAL_ASSETS_NOT_STRICTLY_POSITIVE"),
        (endpoint(current=True, inventory=float("inf")), endpoint(current=False), True, v2.FlagStatus.NOT_READY, "REQUIRED_INPUT_NON_FINITE"),
        (endpoint(current=True), None, False, v2.FlagStatus.NOT_READY, "PRIOR_FISCAL_ENDPOINT_MISSING"),
        (endpoint(current=True, applicability_classification="NOT_APPLICABLE"), endpoint(current=False), True, v2.FlagStatus.NOT_APPLICABLE, "ACCOUNTING_CLASS_NOT_APPLICABLE"),
    ),
)
def test_working_capital_readiness_boundaries(current, prior, consecutive, status, reason) -> None:
    result = dict(zip(
        v2.FLAG_NAMES,
        v2.evaluate_diagnostic_flags(v2.DiagnosticInput(current, prior, consecutive)),
        strict=True,
    ))[v2.FLAG_NAMES[6]]
    assert (result.status, result.reason_code) == (status, reason)


def _v1_endpoint(value: v2.DiagnosticEndpoint) -> v1.DiagnosticEndpoint:
    common = {
        field.name: getattr(value, field.name)
        for field in fields(v1.DiagnosticEndpoint)
        if hasattr(value, field.name)
    }
    common["ebit"] = value.operating_income
    common["ebit_yield"] = value.operating_income_yield
    return v1.DiagnosticEndpoint(**common)


def _v1_name(name: str) -> str:
    return (
        name.replace("current_operating_margin", "current_ebit_margin")
        .replace("prior_operating_margin", "prior_ebit_margin")
        .replace("operating_income_shift", "ebit_shift")
        .replace("operating_income_yield", "ebit_yield")
        .replace("current_operating_income", "current_ebit")
        .replace("prior_operating_income", "prior_ebit")
        .replace("delta_operating_income", "delta_ebit")
        .replace("operating_income_trigger", "ebit_trigger")
    )


def test_native_v2_matches_v1_for_all_economically_unchanged_flags() -> None:
    current = endpoint(
        current=True, revenue=120_000_000.0, operating_income=4_000_000.0,
        common_earnings=-3_000_000.0, operating_cashflow=20_000_000.0,
        capex=-20_000_000.0, cash=2_000_000.0, total_debt=80_000_000.0,
        operating_income_yield=0.55,
    )
    prior = endpoint(current=False)
    new = v2.evaluate_diagnostic_flags(v2.DiagnosticInput(current, prior, True))
    old = v1.evaluate_diagnostic_flags(v1.DiagnosticInput(_v1_endpoint(current), _v1_endpoint(prior), True))
    for index in range(6):
        assert (new[index].status.value, new[index].reason_code, new[index].triggered) == (
            old[index].status.value, old[index].reason_code, old[index].triggered,
        )
        new_evidence = {_v1_name(item.name): item.value for item in new[index].evidence}
        old_evidence = {item.name: item.value for item in old[index].evidence}
        assert new_evidence == old_evidence


def test_v2_engine_has_no_v1_adapter_or_ebit_semantics() -> None:
    source = inspect.getsource(v2).lower()
    assert "diagnostic_flags import engine as v1" not in source
    assert "_v1_endpoint" not in source
    assert "ebit" not in source
    assert "ebitda" not in source
