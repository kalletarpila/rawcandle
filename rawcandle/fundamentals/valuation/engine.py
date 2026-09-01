from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.valuation.methodology import ANCHORS, piecewise_points


MODEL_VERSION = "ABSOLUTE_VALUATION_SCORE_V1"
MAX_PRICE_FALLBACK_CALENDAR_DAYS = 3

REIT_INDUSTRIES = frozenset(
    {
        "REIT - Diversified",
        "REIT - Healthcare Facilities",
        "REIT - Hotel & Motel",
        "REIT - Industrial",
        "REIT - Mortgage",
        "REIT - Office",
        "REIT - Residential",
        "REIT - Retail",
        "REIT - Specialty",
    }
)
BANK_INDUSTRIES = frozenset({"Banks - Diversified", "Banks - Regional"})
INSURANCE_INDUSTRIES = frozenset(
    {
        "Insurance - Diversified",
        "Insurance - Life",
        "Insurance - Property & Casualty",
        "Insurance - Reinsurance",
        "Insurance - Specialty",
        "Insurance Brokers",
    }
)
OTHER_UNSUPPORTED_FINANCIAL_INDUSTRIES = frozenset(
    {
        "Asset Management",
        "Capital Markets",
        "Credit Services",
        "Financial Conglomerates",
        "Mortgage Finance",
        "Shell Companies",
    }
)
SUPPORTED_FINANCIAL_INDUSTRIES = frozenset({"Financial Data & Stock Exchanges"})
SUPPORTED_REAL_ESTATE_INDUSTRIES = frozenset(
    {"Real Estate - Development", "Real Estate - Diversified", "Real Estate Services"}
)
SUPPORTED_NON_FINANCIAL_SECTORS = frozenset(
    {
        "Basic Materials",
        "Communication Services",
        "Consumer Cyclical",
        "Consumer Defensive",
        "Energy",
        "Healthcare",
        "Industrials",
        "Technology",
        "Utilities",
    }
)

MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "components": {
        "EBIT_VALUATION": {"maximum": 40.0, "measure": "ttm_ebit/enterprise_value", "anchors": ANCHORS["ebit_yield"]},
        "FCF_VALUATION": {"maximum": 40.0, "measure": "ttm_free_cashflow/market_cap", "anchors": ANCHORS["fcf_yield"]},
        "EARNINGS_VALUATION": {"maximum": 20.0, "measure": "ttm_net_income_common/market_cap", "anchors": ANCHORS["earnings_yield"]},
    },
    "interpolation": "continuous_piecewise_linear_clamped_at_documented_floor_and_ceiling",
    "nonpositive_numerator_points": 0.0,
    "ev_rule": "enterprise_value_must_be_positive_otherwise_valuation_not_ready",
    "price_rule": {
        "date": "canonical_ttm_source_available_date",
        "selection": "latest_complete_valid_ohlc_on_or_before_date",
        "maximum_fallback_calendar_days": MAX_PRICE_FALLBACK_CALENDAR_DAYS,
        "forward_lookup": False,
        "dividend_transformation": None,
        "split_convention": "price_and_shares_retrospectively_split_compatible_as_stored",
    },
    "applicability": {
        "reit_industries": sorted(REIT_INDUSTRIES),
        "bank_industries": sorted(BANK_INDUSTRIES),
        "insurance_industries": sorted(INSURANCE_INDUSTRIES),
        "other_unsupported_financial_industries": sorted(OTHER_UNSUPPORTED_FINANCIAL_INDUSTRIES),
        "supported_financial_industries": sorted(SUPPORTED_FINANCIAL_INDUSTRIES),
        "supported_real_estate_industries": sorted(SUPPORTED_REAL_ESTATE_INDUSTRIES),
        "supported_non_financial_sectors": sorted(SUPPORTED_NON_FINANCIAL_SECTORS),
        "taxonomy_semantics": "current_revised_not_historical_pit",
    },
    "statuses": ["VALUATION_FULL", "VALUATION_NOT_READY", "VALUATION_NOT_APPLICABLE"],
    "full_requirements": [
        "supported_classification",
        "valid_contiguous_core_ttm",
        "resolved_security_ticker",
        "valid_source_availability_date",
        "valid_price_within_three_calendar_days",
        "positive_shares_and_market_cap",
        "observed_cash_and_total_debt",
        "positive_enterprise_value",
        "four_quarters_common_earnings",
        "observed_ebit_fcf_and_common_earnings",
    ],
    "decision_precedence": [
        "VALUATION_NOT_APPLICABLE_CLASSIFICATION",
        "CLASSIFICATION_NOT_READY",
        "INVALID_FISCAL_CHAIN",
        "TTM_NOT_READY",
        "SECURITY_MAPPING_UNRESOLVED",
        "SOURCE_AVAILABILITY_DATE_MISSING_OR_INVALID",
        "PRICE_MISSING_OR_FALLBACK_TOO_OLD",
        "SHARES_MISSING_OR_NONPOSITIVE",
        "MARKET_CAP_INVALID",
        "CASH_MISSING",
        "DEBT_MISSING",
        "ENTERPRISE_VALUE_NONPOSITIVE",
        "COMMON_EARNINGS_HISTORY_INCOMPLETE",
        "TTM_EBIT_MISSING",
        "TTM_FCF_MISSING",
        "VALUATION_FULL",
    ],
    "imputation": None,
    "weight_transfer": False,
}
MODEL_FINGERPRINT = hashlib.sha256(
    json.dumps(MODEL_CONTRACT, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class Applicability:
    supported: bool | None
    reason_code: str


@dataclass(frozen=True)
class PriceBar:
    price_date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None


@dataclass(frozen=True)
class PriceSelection:
    price_date: str | None
    price_age_calendar_days: int | None
    selected_price: float | None
    reason_code: str | None


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
    ttm_ebit: float | None
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
    ttm_ebit: float | None
    ttm_free_cashflow: float | None
    ttm_net_income_common: float | None
    ebit_yield: float | None
    ebit_points: float | None
    fcf_yield: float | None
    fcf_points: float | None
    earnings_yield: float | None
    earnings_points: float | None
    total_valuation_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def classify_applicability(sector: str | None, industry: str | None) -> Applicability:
    sector = _text(sector)
    industry = _text(industry)
    if sector is None:
        return Applicability(None, "CLASSIFICATION_MISSING")
    if sector in SUPPORTED_NON_FINANCIAL_SECTORS:
        return Applicability(True, "SUPPORTED_OPERATING_COMPANY")
    if sector == "Real Estate":
        if industry is None:
            return Applicability(None, "CLASSIFICATION_MISSING")
        if industry in REIT_INDUSTRIES:
            return Applicability(False, "UNSUPPORTED_REIT_MODEL")
        if industry in SUPPORTED_REAL_ESTATE_INDUSTRIES:
            return Applicability(True, "SUPPORTED_REAL_ESTATE_OPERATING_COMPANY")
        return Applicability(None, "CLASSIFICATION_UNRECOGNIZED")
    if sector == "Financial Services":
        if industry is None:
            return Applicability(None, "CLASSIFICATION_MISSING")
        if industry in BANK_INDUSTRIES:
            return Applicability(False, "UNSUPPORTED_BANK_MODEL")
        if industry in INSURANCE_INDUSTRIES:
            return Applicability(False, "UNSUPPORTED_INSURANCE_MODEL")
        if industry in OTHER_UNSUPPORTED_FINANCIAL_INDUSTRIES:
            return Applicability(False, "UNSUPPORTED_FINANCIAL_MODEL")
        if industry in SUPPORTED_FINANCIAL_INDUSTRIES:
            return Applicability(True, "SUPPORTED_FINANCIAL_DATA_OPERATING_COMPANY")
        return Applicability(None, "CLASSIFICATION_UNRECOGNIZED")
    return Applicability(None, "CLASSIFICATION_UNRECOGNIZED")


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value)) and float(value) > 0.0


def _valid_bar(bar: PriceBar) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close)
    if not all(_finite_positive(value) for value in values):
        return False
    assert bar.open is not None and bar.high is not None and bar.low is not None and bar.close is not None
    return bar.high >= max(bar.open, bar.close, bar.low) and bar.low <= min(bar.open, bar.close, bar.high)


def select_price(
    bars: Sequence[PriceBar | Mapping[str, Any]],
    fundamental_available_date: str | None,
) -> PriceSelection:
    if not fundamental_available_date:
        return PriceSelection(None, None, None, "SOURCE_AVAILABILITY_DATE_MISSING")
    try:
        available = date.fromisoformat(fundamental_available_date)
    except ValueError:
        return PriceSelection(None, None, None, "SOURCE_AVAILABILITY_DATE_INVALID")
    candidates: list[tuple[date, PriceBar]] = []
    for raw in bars:
        bar = raw if isinstance(raw, PriceBar) else PriceBar(
            price_date=str(raw.get("price_date") or raw.get("pvm") or ""),
            open=raw.get("open"),
            high=raw.get("high"),
            low=raw.get("low"),
            close=raw.get("close"),
        )
        try:
            bar_date = date.fromisoformat(bar.price_date)
        except ValueError:
            continue
        if bar_date <= available and _valid_bar(bar):
            candidates.append((bar_date, bar))
    if not candidates:
        return PriceSelection(None, None, None, "PRICE_MISSING")
    price_day, selected = max(candidates, key=lambda item: item[0])
    age = (available - price_day).days
    if age > MAX_PRICE_FALLBACK_CALENDAR_DAYS:
        return PriceSelection(price_day.isoformat(), age, float(selected.close), "PRICE_FALLBACK_TOO_OLD")
    return PriceSelection(price_day.isoformat(), age, float(selected.close), None)


def _number(value: float | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _result(observation: ValuationObservation, **values: Any) -> ValuationResult:
    payload = {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "result_fingerprint": "",
        "company_id": observation.company_id,
        "security_id": observation.security_id,
        "ticker": observation.ticker,
        "fiscal_year": observation.fiscal_year,
        "fiscal_quarter": observation.fiscal_quarter,
        "quarter_id": observation.quarter_id,
        "period_end": observation.period_end,
        "fundamental_available_date": observation.fundamental_available_date,
        "shares_outstanding": _number(observation.shares_outstanding),
        "cash": _number(observation.cash),
        "total_debt": _number(observation.total_debt),
        "ttm_ebit": _number(observation.ttm_ebit),
        "ttm_free_cashflow": _number(observation.ttm_free_cashflow),
        "ttm_net_income_common": _number(observation.ttm_net_income_common),
        "price_date": None,
        "price_age_calendar_days": None,
        "selected_price": None,
        "market_cap": None,
        "net_debt": None,
        "enterprise_value": None,
        "ebit_yield": None,
        "ebit_points": None,
        "fcf_yield": None,
        "fcf_points": None,
        "earnings_yield": None,
        "earnings_points": None,
        "total_valuation_score": None,
        **values,
    }
    payload = {
        key: None if isinstance(value, float) and not math.isfinite(value) else value
        for key, value in payload.items()
    }
    payload["result_fingerprint"] = _fingerprint({key: value for key, value in payload.items() if key != "result_fingerprint"})
    return ValuationResult(**payload)


def calculate_valuation(
    observation: ValuationObservation,
    price_bars: Sequence[PriceBar | Mapping[str, Any]],
) -> ValuationResult:
    applicability = classify_applicability(observation.sector, observation.industry)
    if applicability.supported is False:
        return _result(observation, valuation_status="VALUATION_NOT_APPLICABLE", reason_code=applicability.reason_code)
    if applicability.supported is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code=applicability.reason_code)

    blocker_set = set(observation.ttm_blocker_codes)
    if {"TTM_NON_CONTIGUOUS_WINDOW", "TTM_FISCAL_SEQUENCE_BLOCKED"} & blocker_set:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="INVALID_FISCAL_CHAIN")
    if observation.ttm_readiness_status != "TTM_READY":
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="TTM_NOT_READY")
    if not observation.ticker:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="SECURITY_MAPPING_UNRESOLVED")

    price = select_price(price_bars, observation.fundamental_available_date)
    price_values = {
        "price_date": price.price_date,
        "price_age_calendar_days": price.price_age_calendar_days,
        "selected_price": price.selected_price,
    }
    if price.reason_code:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code=price.reason_code, **price_values)

    shares = _number(observation.shares_outstanding)
    if shares is None or shares <= 0.0:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="SHARES_MISSING_OR_NONPOSITIVE", **price_values)
    assert price.selected_price is not None
    market_cap = price.selected_price * shares
    if not math.isfinite(market_cap) or market_cap <= 0.0:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="MARKET_CAP_INVALID", market_cap=market_cap, **price_values)

    cash = _number(observation.cash)
    debt = _number(observation.total_debt)
    if cash is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="CASH_MISSING", market_cap=market_cap, **price_values)
    if debt is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="DEBT_MISSING", market_cap=market_cap, **price_values)
    net_debt = debt - cash
    enterprise_value = market_cap + net_debt
    balance_values = {"market_cap": market_cap, "net_debt": net_debt, "enterprise_value": enterprise_value, **price_values}
    if not math.isfinite(enterprise_value) or enterprise_value <= 0.0:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="ENTERPRISE_VALUE_NONPOSITIVE", **balance_values)

    if not observation.net_income_common_4q_ready or _number(observation.ttm_net_income_common) is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="COMMON_EARNINGS_HISTORY_INCOMPLETE", **balance_values)
    ebit = _number(observation.ttm_ebit)
    fcf = _number(observation.ttm_free_cashflow)
    common = _number(observation.ttm_net_income_common)
    if ebit is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="TTM_EBIT_MISSING", **balance_values)
    if fcf is None:
        return _result(observation, valuation_status="VALUATION_NOT_READY", reason_code="TTM_FCF_MISSING", **balance_values)
    assert common is not None

    ebit_yield = ebit / enterprise_value
    fcf_yield = fcf / market_cap
    earnings_yield = common / market_cap
    ebit_points = piecewise_points(ebit_yield, ANCHORS["ebit_yield"])
    fcf_points = piecewise_points(fcf_yield, ANCHORS["fcf_yield"])
    earnings_points = piecewise_points(earnings_yield, ANCHORS["earnings_yield"])
    return _result(
        observation,
        valuation_status="VALUATION_FULL",
        reason_code="VALUATION_FULL",
        ebit_yield=ebit_yield,
        ebit_points=ebit_points,
        fcf_yield=fcf_yield,
        fcf_points=fcf_points,
        earnings_yield=earnings_yield,
        earnings_points=earnings_points,
        total_valuation_score=ebit_points + fcf_points + earnings_points,
        **balance_values,
    )
