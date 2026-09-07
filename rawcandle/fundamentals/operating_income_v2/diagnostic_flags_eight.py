from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from . import diagnostic_flags as seven
from .contract import model_fingerprint


MODEL_VERSION = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V2_EIGHT_FLAG_V1"
SEMANTIC_MODE = seven.SEMANTIC_MODE
EVIDENCE_SCHEMA_VERSION = "DIAGNOSTIC_SCALAR_EVIDENCE_V3"
REVENUE_SCALE_FLOOR = 10_000_000.0
ACTIVATION_THRESHOLD = 0.10
FLAG_NAME = "NON_OPERATING_EARNINGS_GAP_CANDIDATE"
FLAG_NAMES = (*seven.FLAG_NAMES, FLAG_NAME)
REASON_CODES = (
    *seven.REASON_CODES,
    "NON_OPERATING_EARNINGS_GAP_THRESHOLD_MET",
    "NON_OPERATING_EARNINGS_GAP_BELOW_THRESHOLD",
    "TTM_EBIT_MISSING",
    "TTM_EBIT_NON_FINITE",
    "TTM_OPERATING_INCOME_MISSING",
    "TTM_OPERATING_INCOME_NON_FINITE",
    "TTM_REVENUE_MISSING",
    "TTM_REVENUE_NON_FINITE",
    "TTM_REVENUE_NONPOSITIVE",
    "TTM_ENDPOINT_INCOHERENT",
)

MODEL_CONTRACT = {
    **seven.MODEL_CONTRACT,
    "model_version": MODEL_VERSION,
    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "flags": FLAG_NAMES,
    "reason_codebook": REASON_CODES,
    "definitions": {
        **seven.MODEL_CONTRACT["definitions"],
        FLAG_NAME: {
            "meaning": "Material net pre-tax gap between provider EBIT and Operating Income; review possible non-operating earnings items",
            "formula": "abs(ttm_ebit-ttm_operating_income)/revenue_denominator",
            "gap_amount": "ttm_ebit-ttm_operating_income",
            "revenue_denominator": "max(ttm_revenue,10000000)",
            "threshold": ACTIVATION_THRESHOLD,
            "operator": ">=",
            "positive_revenue": True,
            "comparison": "CURRENT_EXACT_TTM_ENDPOINT_ONLY",
            "directions": ("UPLIFT", "DRAG", "ZERO"),
            "direction_codes": {"UPLIFT": 1, "DRAG": -1, "ZERO": 0},
            "applicability": "SAME_SUPPORTED_OPERATING_CLASSIFICATION_AS_EXISTING_OPERATING_RESULT_DIAGNOSTICS",
            "score_effect": None,
        },
    },
}
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

EVIDENCE_FIELDS = {
    **seven.EVIDENCE_FIELDS,
    FLAG_NAME: (
        "ttm_ebit",
        "ttm_operating_income",
        "ttm_revenue",
        "gap_amount",
        "gap_abs_amount",
        "revenue_denominator",
        "gap_signed_to_revenue",
        "gap_abs_to_revenue",
        "gap_direction_code",
        "activation_threshold",
    ),
}
BOOLEAN_FIELDS = dict(seven.BOOLEAN_FIELDS)
FlagStatus = seven.FlagStatus
EvidenceScalar = seven.EvidenceScalar
FlagEvaluation = seven.FlagEvaluation


@dataclass(frozen=True)
class DiagnosticEndpoint(seven.DiagnosticEndpoint):
    ebit: float | None = None
    ttm_endpoint_coherent: bool | None = None


DiagnosticInput = seven.DiagnosticInput


def _finite(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


def _evidence(**values: bool | float | int | str | None) -> tuple[EvidenceScalar, ...]:
    return tuple(EvidenceScalar(name, values[name]) for name in sorted(values))


def _result(
    data: DiagnosticInput,
    status: FlagStatus,
    reason_code: str,
    **evidence: bool | float | int | str | None,
) -> FlagEvaluation:
    current = data.current
    common = {
        "current_fiscal_year": current.fiscal_year,
        "current_fiscal_quarter": current.fiscal_quarter,
        "current_period_end": current.period_end,
        "current_source_available_date": current.ttm_available_date,
        "current_ttm_status": current.ttm_status,
        "fiscal_chain_consecutive": data.fiscal_chain_consecutive,
        "applicability_classification": current.applicability_classification,
        "applicability_reason": current.applicability_reason,
        **evidence,
    }
    return FlagEvaluation(
        flag_name=FLAG_NAME,
        status=status,
        reason_code=reason_code,
        company_id=current.company_id,
        quarter_id=current.quarter_id,
        comparison_quarter_id=None,
        effective_available_date=current.ttm_available_date,
        evidence=_evidence(**common),
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
    )


def _non_operating_gap(data: DiagnosticInput) -> FlagEvaluation:
    current = data.current
    classification = current.applicability_classification
    if classification == "NOT_APPLICABLE":
        return _result(data, FlagStatus.NOT_APPLICABLE, "ACCOUNTING_CLASS_NOT_APPLICABLE")
    if classification != "SUPPORTED":
        return _result(data, FlagStatus.NOT_READY, "APPLICABILITY_NOT_READY")
    if current.ttm_endpoint_coherent is not True:
        return _result(data, FlagStatus.NOT_READY, "TTM_ENDPOINT_INCOHERENT", ttm_endpoint_coherent=current.ttm_endpoint_coherent)
    checks = (
        ("ebit", current.ebit, "TTM_EBIT_MISSING", "TTM_EBIT_NON_FINITE"),
        ("operating_income", current.operating_income, "TTM_OPERATING_INCOME_MISSING", "TTM_OPERATING_INCOME_NON_FINITE"),
        ("revenue", current.revenue, "TTM_REVENUE_MISSING", "TTM_REVENUE_NON_FINITE"),
    )
    for name, value, missing_reason, invalid_reason in checks:
        if value is None:
            return _result(data, FlagStatus.NOT_READY, missing_reason, missing_input=name)
        if not _finite(value):
            return _result(data, FlagStatus.NOT_READY, invalid_reason, invalid_input=name)
    if float(current.revenue) <= 0:
        return _result(data, FlagStatus.NOT_READY, "TTM_REVENUE_NONPOSITIVE", ttm_revenue=current.revenue)

    gap = float(current.ebit) - float(current.operating_income)
    denominator = max(float(current.revenue), REVENUE_SCALE_FLOOR)
    signed = gap / denominator
    absolute = abs(gap) / denominator
    direction = "UPLIFT" if gap > 0 else "DRAG" if gap < 0 else "ZERO"
    triggered = absolute >= ACTIVATION_THRESHOLD
    return _result(
        data,
        FlagStatus.FLAGGED if triggered else FlagStatus.CLEAR,
        "NON_OPERATING_EARNINGS_GAP_THRESHOLD_MET" if triggered else "NON_OPERATING_EARNINGS_GAP_BELOW_THRESHOLD",
        ttm_ebit=current.ebit,
        ttm_operating_income=current.operating_income,
        ttm_revenue=current.revenue,
        gap_amount=gap,
        gap_abs_amount=abs(gap),
        revenue_denominator=denominator,
        gap_signed_to_revenue=signed,
        gap_abs_to_revenue=absolute,
        gap_direction=direction,
        gap_direction_code={"UPLIFT": 1, "DRAG": -1, "ZERO": 0}[direction],
        activation_threshold=ACTIVATION_THRESHOLD,
        boundary_operator=">=",
    )


def evaluate_diagnostic_flags(data: DiagnosticInput) -> tuple[FlagEvaluation, ...]:
    existing = tuple(
        replace(
            result,
            model_version=MODEL_VERSION,
            model_fingerprint=MODEL_FINGERPRINT,
            evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        )
        for result in seven.evaluate_diagnostic_flags(data)
    )
    return (*existing, _non_operating_gap(data))
