from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


MODEL_VERSION = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1"
SEMANTIC_MODE = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS"
EVIDENCE_SCHEMA_VERSION = "DIAGNOSTIC_SCALAR_EVIDENCE_V1"
REVENUE_SCALE_FLOOR = 10_000_000.0

FLAG_NAMES = (
    "ABRUPT_FUNDAMENTAL_SHIFT",
    "EARNINGS_CASH_DIVERGENCE_CANDIDATE",
    "CAPEX_INTENSITY_SHIFT_CANDIDATE",
    "NET_DEBT_SHIFT_CANDIDATE",
    "VALUATION_YIELD_OUTLIER",
    "RECENT_MARGIN_DECELERATION_REVIEW",
    "WORKING_CAPITAL_SHIFT_CANDIDATE",
)

REASON_CODES = (
    "ABRUPT_SHIFT_THRESHOLD_MET",
    "ABRUPT_SHIFT_BELOW_THRESHOLD",
    "EARNINGS_CASH_DIVERGENCE_THRESHOLD_MET",
    "EARNINGS_CASH_DIVERGENCE_BELOW_THRESHOLD",
    "CAPEX_INTENSITY_SHIFT_THRESHOLD_MET",
    "CAPEX_INTENSITY_SHIFT_BELOW_THRESHOLD",
    "NET_DEBT_SHIFT_THRESHOLD_MET",
    "NET_DEBT_SHIFT_BELOW_THRESHOLD",
    "VALUATION_YIELD_OUTLIER_THRESHOLD_MET",
    "VALUATION_YIELDS_BELOW_THRESHOLDS",
    "VALUATION_YIELD_NON_FINITE",
    "VALUATION_YIELDS_MISSING",
    "VALUATION_SOURCE_NOT_READY",
    "VALUATION_NOT_APPLICABLE",
    "RECENT_MARGIN_DECELERATION_THRESHOLD_MET",
    "RECENT_MARGIN_DECELERATION_CONDITION_CLEAR",
    "WORKING_CAPITAL_SHIFT_THRESHOLD_MET",
    "WORKING_CAPITAL_SHIFT_BELOW_THRESHOLD",
    "PRIOR_FISCAL_ENDPOINT_MISSING",
    "NON_CONSECUTIVE_FISCAL_CHAIN",
    "REQUIRED_INPUT_MISSING",
    "REQUIRED_INPUT_NON_FINITE",
    "NONPOSITIVE_REVENUE",
    "TOTAL_ASSETS_NOT_STRICTLY_POSITIVE",
    "ACCOUNTING_CLASS_NOT_APPLICABLE",
    "APPLICABILITY_NOT_READY",
)


class FlagStatus(str, Enum):
    FLAGGED = "EVALUATED_FLAGGED"
    CLEAR = "EVALUATED_CLEAR"
    NOT_READY = "FLAG_NOT_READY"
    NOT_APPLICABLE = "FLAG_NOT_APPLICABLE"


MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "semantic_mode": SEMANTIC_MODE,
    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "flags": FLAG_NAMES,
    "statuses": tuple(status.value for status in FlagStatus),
    "reason_codebook": REASON_CODES,
    "history": "CURRENTLY_REVISED_NOT_PIT",
    "fiscal_chain": "EXACT_PRIOR_FISCAL_SEQUENCE_REQUIRED",
    "availability": "MAX_REQUIRED_AUTHORITATIVE_INPUT_AVAILABILITY_DATE",
    "applicability": "FLAG_SPECIFIC_EXISTING_VALUATION_CLASSIFICATION",
    "missing": "NEVER_IMPUTED_NEVER_CLEAR",
    "source_readiness": "REQUIRED_FIELD_OBSERVED_AND_FINITE; TTM_STATUS_RETAINED_AS_EVIDENCE",
    "numeric": {"finite_required": True, "rounding": None, "boolean_is_number": False},
    "definitions": {
        "ABRUPT_FUNDAMENTAL_SHIFT": {
            "formula": "max(abs(delta_revenue)/R,abs(delta_ebit)/R)",
            "scale": "R=max((abs(revenue_t)+abs(revenue_t_minus_1))/2,10000000)",
            "threshold": 0.20,
            "operator": ">=",
            "positive_revenue": True,
        },
        "EARNINGS_CASH_DIVERGENCE_CANDIDATE": {
            "formula": "abs(delta_common_earnings-delta_operating_cashflow)/R",
            "scale": "same_R_as_abrupt_shift",
            "threshold": 0.20,
            "operator": ">=",
        },
        "CAPEX_INTENSITY_SHIFT_CANDIDATE": {
            "formula": "abs(abs(capex_t)/max(revenue_t,10000000)-abs(capex_t_minus_1)/max(revenue_t_minus_1,10000000))",
            "threshold": 0.10,
            "operator": ">=",
            "positive_revenue": True,
        },
        "NET_DEBT_SHIFT_CANDIDATE": {
            "formula": "abs((debt_t-cash_t)-(debt_t_minus_1-cash_t_minus_1))/R",
            "threshold": 0.50,
            "operator": ">=",
        },
        "VALUATION_YIELD_OUTLIER": {
            "formula": "median(available_yields)>=0.25 OR max(available_yields)>=0.50",
            "yields": ("ebit_over_ev", "fcf_over_market_cap", "common_earnings_over_market_cap"),
            "operators": (">=", ">="),
            "thresholds": (0.25, 0.50),
            "required_status": "VALUATION_FULL",
        },
        "RECENT_MARGIN_DECELERATION_REVIEW": {
            "formula": "trajectory>=7 AND ebit_margin_t-ebit_margin_t_minus_1<=-0.02",
            "operators": (">=", "<="),
            "thresholds": (7.0, -0.02),
            "positive_revenue": True,
            "positive_ebit_required": False,
        },
        "WORKING_CAPITAL_SHIFT_CANDIDATE": {
            "onwc": "accounts_receivable+inventory-accounts_payable-deferred_revenue",
            "formula": "abs(onwc_t-onwc_t_minus_1)/asset_scale",
            "asset_scale": "max((total_assets_t+total_assets_t_minus_1)/2,10000000)",
            "threshold": 0.10,
            "operator": ">=",
            "strictly_positive_assets": True,
        },
    },
    "excluded": ("VALUATION_YIELD_DIVERGENCE_REVIEW", "combined_score", "severity"),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


MODEL_FINGERPRINT = fingerprint(MODEL_CONTRACT)


@dataclass(frozen=True)
class DiagnosticEndpoint:
    company_id: int
    quarter_id: int
    fiscal_year: int
    fiscal_quarter: str
    fiscal_sequence: int
    period_end: str
    source_available_date: str | None
    ttm_available_date: str | None = None
    valuation_available_date: str | None = None
    ttm_status: str | None = None
    revenue: float | None = None
    ebit: float | None = None
    common_earnings: float | None = None
    operating_cashflow: float | None = None
    capex: float | None = None
    cash: float | None = None
    total_debt: float | None = None
    accounts_receivable: float | None = None
    inventory: float | None = None
    accounts_payable: float | None = None
    deferred_revenue: float | None = None
    total_assets: float | None = None
    trajectory: float | None = None
    valuation_status: str | None = None
    valuation_reason: str | None = None
    applicability_classification: str | None = None
    applicability_reason: str | None = None
    ebit_yield: float | None = None
    fcf_yield: float | None = None
    earnings_yield: float | None = None


@dataclass(frozen=True)
class DiagnosticInput:
    current: DiagnosticEndpoint
    prior: DiagnosticEndpoint | None
    fiscal_chain_consecutive: bool


@dataclass(frozen=True)
class EvidenceScalar:
    name: str
    value: bool | float | int | str | None


@dataclass(frozen=True)
class FlagEvaluation:
    flag_name: str
    status: FlagStatus
    reason_code: str
    company_id: int
    quarter_id: int
    comparison_quarter_id: int | None
    effective_available_date: str | None
    evidence: tuple[EvidenceScalar, ...]
    model_version: str = MODEL_VERSION
    model_fingerprint: str = MODEL_FINGERPRINT
    evidence_schema_version: str = EVIDENCE_SCHEMA_VERSION

    @property
    def triggered(self) -> bool | None:
        if self.status == FlagStatus.FLAGGED:
            return True
        if self.status == FlagStatus.CLEAR:
            return False
        return None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["triggered"] = self.triggered
        payload["evidence"] = {item.name: item.value for item in self.evidence}
        return payload

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def _finite(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


def _evidence(**values: bool | float | int | str | None) -> tuple[EvidenceScalar, ...]:
    return tuple(EvidenceScalar(name, values[name]) for name in sorted(values))


def _effective_date(*dates: str | None) -> str | None:
    observed = [value for value in dates if value]
    return max(observed) if len(observed) == len(dates) else None


def _result(
    data: DiagnosticInput,
    flag_name: str,
    status: FlagStatus,
    reason: str,
    evidence: tuple[EvidenceScalar, ...],
    *,
    comparison: bool = True,
    availability_source: str = "ttm",
) -> FlagEvaluation:
    prior = data.prior if comparison else None
    if availability_source == "canonical":
        current_available = data.current.source_available_date
        prior_available = prior.source_available_date if prior else current_available
    elif availability_source == "valuation":
        current_available = data.current.valuation_available_date
        prior_available = current_available
    else:
        current_available = data.current.ttm_available_date
        prior_available = prior.ttm_available_date if prior else current_available
    common_evidence: dict[str, bool | float | int | str | None] = {
        "current_fiscal_year": data.current.fiscal_year,
        "current_fiscal_quarter": data.current.fiscal_quarter,
        "current_period_end": data.current.period_end,
        "current_source_available_date": current_available,
        "current_ttm_status": data.current.ttm_status,
        "prior_fiscal_year": prior.fiscal_year if prior else None,
        "prior_fiscal_quarter": prior.fiscal_quarter if prior else None,
        "prior_period_end": prior.period_end if prior else None,
        "prior_source_available_date": prior_available if prior else None,
        "prior_ttm_status": prior.ttm_status if prior else None,
        "fiscal_chain_consecutive": data.fiscal_chain_consecutive,
        "applicability_classification": data.current.applicability_classification,
    }
    common_evidence.update({item.name: item.value for item in evidence})
    return FlagEvaluation(
        flag_name=flag_name,
        status=status,
        reason_code=reason,
        company_id=data.current.company_id,
        quarter_id=data.current.quarter_id,
        comparison_quarter_id=prior.quarter_id if prior else None,
        effective_available_date=_effective_date(current_available, prior_available),
        evidence=_evidence(**common_evidence),
    )


def _operating_gate(data: DiagnosticInput, flag_name: str, *, availability_source: str = "ttm") -> FlagEvaluation | None:
    classification = data.current.applicability_classification
    evidence = _evidence(
        applicability_classification=classification,
        applicability_reason=data.current.applicability_reason,
    )
    if classification == "NOT_APPLICABLE":
        return _result(data, flag_name, FlagStatus.NOT_APPLICABLE, "ACCOUNTING_CLASS_NOT_APPLICABLE", evidence, availability_source=availability_source)
    if classification != "SUPPORTED":
        return _result(data, flag_name, FlagStatus.NOT_READY, "APPLICABILITY_NOT_READY", evidence, availability_source=availability_source)
    if data.prior is None:
        return _result(data, flag_name, FlagStatus.NOT_READY, "PRIOR_FISCAL_ENDPOINT_MISSING", evidence, availability_source=availability_source)
    if not data.fiscal_chain_consecutive:
        return _result(data, flag_name, FlagStatus.NOT_READY, "NON_CONSECUTIVE_FISCAL_CHAIN", evidence, availability_source=availability_source)
    return None


def _required_values(
    data: DiagnosticInput,
    flag_name: str,
    values: dict[str, Any],
    *,
    availability_source: str = "ttm",
) -> FlagEvaluation | None:
    missing = tuple(sorted(name for name, value in values.items() if value is None))
    invalid = tuple(sorted(name for name, value in values.items() if value is not None and not _finite(value)))
    if missing:
        return _result(data, flag_name, FlagStatus.NOT_READY, "REQUIRED_INPUT_MISSING", _evidence(missing_inputs="|".join(missing)), availability_source=availability_source)
    if invalid:
        return _result(data, flag_name, FlagStatus.NOT_READY, "REQUIRED_INPUT_NON_FINITE", _evidence(invalid_inputs="|".join(invalid)), availability_source=availability_source)
    return None


def _positive_revenue_gate(data: DiagnosticInput, flag_name: str) -> FlagEvaluation | None:
    assert data.prior is not None
    if float(data.current.revenue) <= 0 or float(data.prior.revenue) <= 0:
        return _result(
            data,
            flag_name,
            FlagStatus.NOT_APPLICABLE,
            "NONPOSITIVE_REVENUE",
            _evidence(current_revenue=data.current.revenue, prior_revenue=data.prior.revenue),
        )
    return None


def _comparison_values(data: DiagnosticInput, names: tuple[str, ...]) -> dict[str, Any]:
    assert data.prior is not None
    return {
        **{f"current_{name}": getattr(data.current, name) for name in names},
        **{f"prior_{name}": getattr(data.prior, name) for name in names},
    }


def _revenue_scale(data: DiagnosticInput) -> float:
    assert data.prior is not None and data.current.revenue is not None and data.prior.revenue is not None
    return max((abs(float(data.current.revenue)) + abs(float(data.prior.revenue))) / 2.0, REVENUE_SCALE_FLOOR)


def _evaluated(
    data: DiagnosticInput,
    flag: str,
    triggered: bool,
    reason: str,
    evidence: tuple[EvidenceScalar, ...],
    *,
    comparison: bool = True,
    availability_source: str = "ttm",
) -> FlagEvaluation:
    return _result(
        data,
        flag,
        FlagStatus.FLAGGED if triggered else FlagStatus.CLEAR,
        reason,
        evidence,
        comparison=comparison,
        availability_source=availability_source,
    )


def _abrupt(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[0]
    gate = _operating_gate(data, flag)
    if gate:
        return gate
    values = _comparison_values(data, ("revenue", "ebit"))
    gate = _required_values(data, flag, values)
    if gate:
        return gate
    gate = _positive_revenue_gate(data, flag)
    if gate:
        return gate
    assert data.prior is not None
    scale = _revenue_scale(data)
    delta_revenue = float(data.current.revenue) - float(data.prior.revenue)
    delta_ebit = float(data.current.ebit) - float(data.prior.ebit)
    revenue_ratio, ebit_ratio = abs(delta_revenue) / scale, abs(delta_ebit) / scale
    revenue_trigger, ebit_trigger = revenue_ratio >= 0.20, ebit_ratio >= 0.20
    return _evaluated(data, flag, revenue_trigger or ebit_trigger, "ABRUPT_SHIFT_THRESHOLD_MET" if revenue_trigger or ebit_trigger else "ABRUPT_SHIFT_BELOW_THRESHOLD", _evidence(
        current_revenue=data.current.revenue, prior_revenue=data.prior.revenue,
        current_ebit=data.current.ebit, prior_ebit=data.prior.ebit,
        delta_revenue=delta_revenue, delta_ebit=delta_ebit, revenue_scale=scale,
        revenue_shift_ratio=revenue_ratio, ebit_shift_ratio=ebit_ratio,
        revenue_trigger=revenue_trigger, ebit_trigger=ebit_trigger,
        metric_value=max(revenue_ratio, ebit_ratio), threshold=0.20, boundary_operator=">=",
    ))


def _earnings_cash(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[1]
    gate = _operating_gate(data, flag)
    if gate:
        return gate
    values = _comparison_values(data, ("revenue", "common_earnings", "operating_cashflow"))
    gate = _required_values(data, flag, values)
    if gate:
        return gate
    gate = _positive_revenue_gate(data, flag)
    if gate:
        return gate
    assert data.prior is not None
    scale = _revenue_scale(data)
    delta_earnings = float(data.current.common_earnings) - float(data.prior.common_earnings)
    delta_cfo = float(data.current.operating_cashflow) - float(data.prior.operating_cashflow)
    ratio = abs(delta_earnings - delta_cfo) / scale
    triggered = ratio >= 0.20
    return _evaluated(data, flag, triggered, "EARNINGS_CASH_DIVERGENCE_THRESHOLD_MET" if triggered else "EARNINGS_CASH_DIVERGENCE_BELOW_THRESHOLD", _evidence(
        current_common_earnings=data.current.common_earnings, prior_common_earnings=data.prior.common_earnings,
        current_operating_cashflow=data.current.operating_cashflow, prior_operating_cashflow=data.prior.operating_cashflow,
        delta_common_earnings=delta_earnings, delta_operating_cashflow=delta_cfo,
        signed_change_difference=delta_earnings-delta_cfo, revenue_scale=scale,
        metric_value=ratio, threshold=0.20, boundary_operator=">=",
    ))


def _capex(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[2]
    gate = _operating_gate(data, flag)
    if gate:
        return gate
    values = _comparison_values(data, ("revenue", "capex"))
    gate = _required_values(data, flag, values)
    if gate:
        return gate
    gate = _positive_revenue_gate(data, flag)
    if gate:
        return gate
    assert data.prior is not None
    current_denominator = max(float(data.current.revenue), REVENUE_SCALE_FLOOR)
    prior_denominator = max(float(data.prior.revenue), REVENUE_SCALE_FLOOR)
    current_intensity = abs(float(data.current.capex)) / current_denominator
    prior_intensity = abs(float(data.prior.capex)) / prior_denominator
    signed_change = current_intensity - prior_intensity
    metric = abs(signed_change)
    triggered = metric >= 0.10
    return _evaluated(data, flag, triggered, "CAPEX_INTENSITY_SHIFT_THRESHOLD_MET" if triggered else "CAPEX_INTENSITY_SHIFT_BELOW_THRESHOLD", _evidence(
        current_capex=data.current.capex, prior_capex=data.prior.capex,
        current_revenue=data.current.revenue, prior_revenue=data.prior.revenue,
        current_denominator=current_denominator, prior_denominator=prior_denominator,
        current_capex_intensity=current_intensity, prior_capex_intensity=prior_intensity,
        signed_intensity_change=signed_change, metric_value=metric, threshold=0.10, boundary_operator=">=",
    ))


def _net_debt(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[3]
    gate = _operating_gate(data, flag)
    if gate:
        return gate
    values = _comparison_values(data, ("revenue", "cash", "total_debt"))
    gate = _required_values(data, flag, values)
    if gate:
        return gate
    gate = _positive_revenue_gate(data, flag)
    if gate:
        return gate
    assert data.prior is not None
    scale = _revenue_scale(data)
    current_net_debt = float(data.current.total_debt) - float(data.current.cash)
    prior_net_debt = float(data.prior.total_debt) - float(data.prior.cash)
    delta = current_net_debt - prior_net_debt
    metric = abs(delta) / scale
    triggered = metric >= 0.50
    return _evaluated(data, flag, triggered, "NET_DEBT_SHIFT_THRESHOLD_MET" if triggered else "NET_DEBT_SHIFT_BELOW_THRESHOLD", _evidence(
        current_cash=data.current.cash, prior_cash=data.prior.cash,
        current_total_debt=data.current.total_debt, prior_total_debt=data.prior.total_debt,
        current_net_debt=current_net_debt, prior_net_debt=prior_net_debt,
        signed_net_debt_change=delta, revenue_scale=scale,
        metric_value=metric, threshold=0.50, boundary_operator=">=",
    ))


def _valuation(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[4]
    current = data.current
    base = _evidence(
        applicability_classification=current.applicability_classification,
        applicability_reason=current.applicability_reason,
        valuation_status=current.valuation_status,
        valuation_reason=current.valuation_reason,
    )
    if current.valuation_status == "VALUATION_NOT_APPLICABLE" or current.applicability_classification == "NOT_APPLICABLE":
        return _result(data, flag, FlagStatus.NOT_APPLICABLE, "VALUATION_NOT_APPLICABLE", base, comparison=False, availability_source="valuation")
    if current.valuation_status != "VALUATION_FULL":
        return _result(data, flag, FlagStatus.NOT_READY, "VALUATION_SOURCE_NOT_READY", base, comparison=False, availability_source="valuation")
    yields = {"ebit_yield": current.ebit_yield, "fcf_yield": current.fcf_yield, "earnings_yield": current.earnings_yield}
    invalid = [name for name, value in yields.items() if value is not None and not _finite(value)]
    if invalid:
        return _result(data, flag, FlagStatus.NOT_READY, "VALUATION_YIELD_NON_FINITE", _evidence(invalid_inputs="|".join(sorted(invalid))), comparison=False, availability_source="valuation")
    available = [float(value) for value in yields.values() if value is not None]
    if not available:
        return _result(data, flag, FlagStatus.NOT_READY, "VALUATION_YIELDS_MISSING", base, comparison=False, availability_source="valuation")
    median_yield, maximum_yield = statistics.median(available), max(available)
    median_trigger, maximum_trigger = median_yield >= 0.25, maximum_yield >= 0.50
    triggered = median_trigger or maximum_trigger
    return _evaluated(data, flag, triggered, "VALUATION_YIELD_OUTLIER_THRESHOLD_MET" if triggered else "VALUATION_YIELDS_BELOW_THRESHOLDS", _evidence(
        ebit_yield=current.ebit_yield, fcf_yield=current.fcf_yield, earnings_yield=current.earnings_yield,
        available_yield_count=len(available), median_yield=median_yield, maximum_yield=maximum_yield,
        median_threshold=0.25, maximum_threshold=0.50, median_trigger=median_trigger,
        maximum_trigger=maximum_trigger, boundary_operator=">=",
    ), comparison=False, availability_source="valuation")


def _margin(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[5]
    gate = _operating_gate(data, flag)
    if gate:
        return gate
    values = _comparison_values(data, ("revenue", "ebit"))
    values["current_trajectory"] = data.current.trajectory
    gate = _required_values(data, flag, values)
    if gate:
        return gate
    gate = _positive_revenue_gate(data, flag)
    if gate:
        return gate
    assert data.prior is not None
    current_margin = float(data.current.ebit) / float(data.current.revenue)
    prior_margin = float(data.prior.ebit) / float(data.prior.revenue)
    change = current_margin - prior_margin
    trajectory_trigger = float(data.current.trajectory) >= 7.0
    margin_trigger = change <= -0.02
    triggered = trajectory_trigger and margin_trigger
    return _evaluated(data, flag, triggered, "RECENT_MARGIN_DECELERATION_THRESHOLD_MET" if triggered else "RECENT_MARGIN_DECELERATION_CONDITION_CLEAR", _evidence(
        current_revenue=data.current.revenue, prior_revenue=data.prior.revenue,
        current_ebit=data.current.ebit, prior_ebit=data.prior.ebit,
        current_ebit_margin=current_margin, prior_ebit_margin=prior_margin,
        signed_margin_change=change, current_trajectory=data.current.trajectory,
        metric_value=change, threshold=-0.02, boundary_operator="<=",
        trajectory_threshold=7.0, margin_change_threshold=-0.02,
        trajectory_operator=">=", margin_operator="<=",
        trajectory_trigger=trajectory_trigger, margin_trigger=margin_trigger,
    ))


def _working_capital(data: DiagnosticInput) -> FlagEvaluation:
    flag = FLAG_NAMES[6]
    gate = _operating_gate(data, flag, availability_source="canonical")
    if gate:
        return gate
    names = ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue", "total_assets")
    values = _comparison_values(data, names)
    gate = _required_values(data, flag, values, availability_source="canonical")
    if gate:
        return gate
    assert data.prior is not None
    if float(data.current.total_assets) <= 0 or float(data.prior.total_assets) <= 0:
        return _result(data, flag, FlagStatus.NOT_READY, "TOTAL_ASSETS_NOT_STRICTLY_POSITIVE", _evidence(
            current_total_assets=data.current.total_assets, prior_total_assets=data.prior.total_assets,
        ), availability_source="canonical")
    current_onwc = float(data.current.accounts_receivable) + float(data.current.inventory) - float(data.current.accounts_payable) - float(data.current.deferred_revenue)
    prior_onwc = float(data.prior.accounts_receivable) + float(data.prior.inventory) - float(data.prior.accounts_payable) - float(data.prior.deferred_revenue)
    delta = current_onwc - prior_onwc
    scale = max((float(data.current.total_assets) + float(data.prior.total_assets)) / 2.0, REVENUE_SCALE_FLOOR)
    metric = abs(delta) / scale
    triggered = metric >= 0.10
    return _result(data, flag, FlagStatus.FLAGGED if triggered else FlagStatus.CLEAR, "WORKING_CAPITAL_SHIFT_THRESHOLD_MET" if triggered else "WORKING_CAPITAL_SHIFT_BELOW_THRESHOLD", _evidence(
        current_accounts_receivable=data.current.accounts_receivable, prior_accounts_receivable=data.prior.accounts_receivable,
        current_inventory=data.current.inventory, prior_inventory=data.prior.inventory,
        current_accounts_payable=data.current.accounts_payable, prior_accounts_payable=data.prior.accounts_payable,
        current_deferred_revenue=data.current.deferred_revenue, prior_deferred_revenue=data.prior.deferred_revenue,
        current_total_assets=data.current.total_assets, prior_total_assets=data.prior.total_assets,
        current_onwc=current_onwc, prior_onwc=prior_onwc, signed_delta_onwc=delta,
        asset_scale=scale, metric_value=metric, threshold=0.10, boundary_operator=">=",
    ), availability_source="canonical")


def evaluate_diagnostic_flags(data: DiagnosticInput) -> tuple[FlagEvaluation, ...]:
    """Evaluate the seven independent V1 diagnostics in canonical order."""
    quarter_numbers = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
    current_quarter = quarter_numbers.get(data.current.fiscal_quarter)
    if current_quarter is None or data.current.fiscal_sequence != data.current.fiscal_year * 4 + current_quarter:
        raise ValueError("CURRENT_FISCAL_IDENTITY_INVALID")
    if data.prior is not None and data.prior.company_id != data.current.company_id:
        raise ValueError("CROSS_COMPANY_COMPARISON")
    if data.prior is not None:
        prior_quarter = quarter_numbers.get(data.prior.fiscal_quarter)
        if prior_quarter is None or data.prior.fiscal_sequence != data.prior.fiscal_year * 4 + prior_quarter:
            raise ValueError("PRIOR_FISCAL_IDENTITY_INVALID")
        if data.fiscal_chain_consecutive and data.prior.fiscal_sequence != data.current.fiscal_sequence - 1:
            raise ValueError("FISCAL_CHAIN_CONSISTENCY_INVALID")
    return (
        _abrupt(data),
        _earnings_cash(data),
        _capex(data),
        _net_debt(data),
        _valuation(data),
        _margin(data),
        _working_capital(data),
    )
