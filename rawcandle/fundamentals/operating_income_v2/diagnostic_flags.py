from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from rawcandle.fundamentals.diagnostic_flags import engine as v1

from .contract import DIAGNOSTIC_MODEL_VERSION, fingerprint, model_fingerprint


MODEL_VERSION = DIAGNOSTIC_MODEL_VERSION
EVIDENCE_SCHEMA_VERSION = "DIAGNOSTIC_SCALAR_EVIDENCE_V2"
AFFECTED_FLAGS = (
    "ABRUPT_FUNDAMENTAL_SHIFT",
    "VALUATION_YIELD_OUTLIER",
    "RECENT_MARGIN_DECELERATION_REVIEW",
)
MODEL_CONTRACT = {
    **v1.MODEL_CONTRACT,
    "model_version": MODEL_VERSION,
    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "affected_flags": AFFECTED_FLAGS,
    "operating_income_fallback": None,
}
definitions = dict(v1.MODEL_CONTRACT["definitions"])
definitions["ABRUPT_FUNDAMENTAL_SHIFT"] = {**definitions["ABRUPT_FUNDAMENTAL_SHIFT"], "formula": "max(abs(delta_revenue)/R,abs(delta_operating_income)/R)"}
definitions["VALUATION_YIELD_OUTLIER"] = {**definitions["VALUATION_YIELD_OUTLIER"], "yields": ("operating_income_over_ev", "fcf_over_market_cap", "common_earnings_over_market_cap")}
definitions["RECENT_MARGIN_DECELERATION_REVIEW"] = {**definitions["RECENT_MARGIN_DECELERATION_REVIEW"], "formula": "trajectory>=7 AND operating_margin_t-operating_margin_t_minus_1<=-0.02"}
MODEL_CONTRACT["definitions"] = definitions
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

FlagStatus = v1.FlagStatus
EvidenceScalar = v1.EvidenceScalar


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
    operating_income: float | None = None
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
    operating_income_yield: float | None = None
    fcf_yield: float | None = None
    earnings_yield: float | None = None


@dataclass(frozen=True)
class DiagnosticInput:
    current: DiagnosticEndpoint
    prior: DiagnosticEndpoint | None
    fiscal_chain_consecutive: bool


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
        return True if self.status == FlagStatus.FLAGGED else False if self.status == FlagStatus.CLEAR else None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["triggered"] = self.triggered
        payload["evidence"] = {item.name: item.value for item in self.evidence}
        return payload


def _v1_endpoint(value: DiagnosticEndpoint | None) -> v1.DiagnosticEndpoint | None:
    if value is None:
        return None
    common = {field.name: getattr(value, field.name) for field in fields(v1.DiagnosticEndpoint) if hasattr(value, field.name)}
    common["ebit"] = value.operating_income
    common["ebit_yield"] = value.operating_income_yield
    return v1.DiagnosticEndpoint(**common)


def _evidence_name(name: str) -> str:
    return (name.replace("current_ebit_margin", "current_operating_margin")
            .replace("prior_ebit_margin", "prior_operating_margin")
            .replace("ebit_shift", "operating_income_shift")
            .replace("ebit_yield", "operating_income_yield")
            .replace("current_ebit", "current_operating_income")
            .replace("prior_ebit", "prior_operating_income")
            .replace("delta_ebit", "delta_operating_income"))


def evaluate_diagnostic_flags(data: DiagnosticInput) -> tuple[FlagEvaluation, ...]:
    mapped = v1.DiagnosticInput(
        current=_v1_endpoint(data.current),
        prior=_v1_endpoint(data.prior),
        fiscal_chain_consecutive=data.fiscal_chain_consecutive,
    )
    output = []
    for result in v1.evaluate_diagnostic_flags(mapped):
        evidence = tuple(sorted(
            (EvidenceScalar(_evidence_name(item.name), item.value) for item in result.evidence),
            key=lambda item: item.name,
        ))
        output.append(FlagEvaluation(
            result.flag_name, result.status, result.reason_code,
            result.company_id, result.quarter_id, result.comparison_quarter_id,
            result.effective_available_date, evidence,
        ))
    return tuple(output)
