from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.valuation import engine as v1
from rawcandle.fundamentals.valuation.methodology import ANCHORS

from .contract import OPERATING_YIELD_ANCHORS, VALUATION_MODEL_VERSION, fingerprint, model_fingerprint


MODEL_VERSION = VALUATION_MODEL_VERSION
MODEL_CONTRACT = {
    **v1.MODEL_CONTRACT,
    "model_version": MODEL_VERSION,
    "components": {
        "OPERATING_INCOME_VALUATION": {"maximum": 40.0, "measure": "ttm_operating_income/enterprise_value", "anchors": OPERATING_YIELD_ANCHORS},
        "FCF_VALUATION": v1.MODEL_CONTRACT["components"]["FCF_VALUATION"],
        "EARNINGS_VALUATION": v1.MODEL_CONTRACT["components"]["EARNINGS_VALUATION"],
    },
    "operating_income_fallback": None,
}
MODEL_CONTRACT["full_requirements"] = [
    item.replace("ebit", "operating_income") for item in v1.MODEL_CONTRACT["full_requirements"]
]
MODEL_CONTRACT["decision_precedence"] = [
    item.replace("EBIT", "OPERATING_INCOME") for item in v1.MODEL_CONTRACT["decision_precedence"]
]
MODEL_FINGERPRINT = model_fingerprint(MODEL_VERSION, MODEL_CONTRACT)

Applicability = v1.Applicability
PriceBar = v1.PriceBar
PriceSelection = v1.PriceSelection
classify_applicability = v1.classify_applicability
select_price = v1.select_price


@dataclass(frozen=True)
class ValuationObservation:
    company_id: int
    security_id: int | None
    ticker: str | None
    fiscal_year: int
    fiscal_quarter: str
    quarter_id: int
    period_end: str
    fundamental_available_date: str | None
    ttm_readiness_status: str
    ttm_blocker_codes: tuple[str, ...]
    ttm_operating_income: float | None
    ttm_free_cashflow: float | None
    ttm_net_income_common: float | None
    net_income_common_4q_ready: bool
    shares_outstanding: float | None
    cash: float | None
    total_debt: float | None
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class ValuationResult:
    model_version: str
    model_fingerprint: str
    result_fingerprint: str
    valuation_status: str
    reason_code: str
    company_id: int
    security_id: int | None
    ticker: str | None
    fiscal_year: int
    fiscal_quarter: str
    quarter_id: int
    period_end: str
    fundamental_available_date: str | None
    price_date: str | None
    price_age_calendar_days: int | None
    selected_price: float | None
    shares_outstanding: float | None
    market_cap: float | None
    cash: float | None
    total_debt: float | None
    net_debt: float | None
    enterprise_value: float | None
    ttm_operating_income: float | None
    ttm_free_cashflow: float | None
    ttm_net_income_common: float | None
    operating_income_yield: float | None
    operating_income_points: float | None
    fcf_yield: float | None
    fcf_points: float | None
    earnings_yield: float | None
    earnings_points: float | None
    total_valuation_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_valuation(
    observation: ValuationObservation,
    price_bars: Sequence[PriceBar | Mapping[str, Any]],
) -> ValuationResult:
    mapped = v1.ValuationObservation(
        company_id=observation.company_id,
        security_id=observation.security_id,
        ticker=observation.ticker,
        fiscal_year=observation.fiscal_year,
        fiscal_quarter=observation.fiscal_quarter,
        quarter_id=observation.quarter_id,
        period_end=observation.period_end,
        fundamental_available_date=observation.fundamental_available_date,
        ttm_readiness_status=observation.ttm_readiness_status,
        ttm_blocker_codes=tuple(code.replace("OPERATING_INCOME", "EBIT") for code in observation.ttm_blocker_codes),
        ttm_ebit=observation.ttm_operating_income,
        ttm_free_cashflow=observation.ttm_free_cashflow,
        ttm_net_income_common=observation.ttm_net_income_common,
        net_income_common_4q_ready=observation.net_income_common_4q_ready,
        shares_outstanding=observation.shares_outstanding,
        cash=observation.cash,
        total_debt=observation.total_debt,
        sector=observation.sector,
        industry=observation.industry,
    )
    result = v1.calculate_valuation(mapped, price_bars)
    payload = result.to_dict()
    payload["model_version"] = MODEL_VERSION
    payload["model_fingerprint"] = MODEL_FINGERPRINT
    payload["reason_code"] = str(payload["reason_code"]).replace("TTM_EBIT", "TTM_OPERATING_INCOME")
    payload["ttm_operating_income"] = payload.pop("ttm_ebit")
    payload["operating_income_yield"] = payload.pop("ebit_yield")
    payload["operating_income_points"] = payload.pop("ebit_points")
    payload.pop("result_fingerprint")
    payload["result_fingerprint"] = fingerprint(payload)
    return ValuationResult(**payload)
