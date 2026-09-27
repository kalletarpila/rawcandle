from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


PROVIDER = "YAHOO_FINANCE"

FAMILY_FISCAL_ESTIMATE = "FISCAL_ESTIMATE"
FAMILY_PRICE_TARGET = "PRICE_TARGET"
FAMILY_EARNINGS_HISTORY_REFERENCE = "EARNINGS_HISTORY_REFERENCE"
FORECAST_FAMILIES = (
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    FAMILY_EARNINGS_HISTORY_REFERENCE,
)

STATUS_SUCCESS_WITH_DATA = "SUCCESS_WITH_DATA"
STATUS_VALID_NO_DATA = "VALID_NO_DATA"
STATUS_PROVIDER_SYMBOL_UNAVAILABLE = "PROVIDER_SYMBOL_UNAVAILABLE"
STATUS_RATE_LIMITED = "RATE_LIMITED"
STATUS_TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
STATUS_MALFORMED = "MALFORMED_OR_SCHEMA_MISMATCH"
STATUS_SUCCESS_CHANGED = "SUCCESS_CHANGED"
STATUS_SUCCESS_UNCHANGED = "SUCCESS_UNCHANGED"

STATE_FIELD_ABSENT = "FIELD_ABSENT"
STATE_EMPTY_OBJECT = "EMPTY_OBJECT"
STATE_EXPLICIT_NULL = "EXPLICIT_NULL"
STATE_NUMERIC_ZERO = "NUMERIC_ZERO"
STATE_NUMERIC_VALUE = "NUMERIC_VALUE"
STATE_TEXT_VALUE = "TEXT_VALUE"

EARNINGS_TREND_CONTRACT_VERSION = "yahoo_earnings_trend_v1"
PRICE_TARGET_CONTRACT_VERSION = "yahoo_price_target_v1"
EARNINGS_HISTORY_CONTRACT_VERSION = "yahoo_earnings_history_reference_v1"

_ABSENT = object()

EARNINGS_TREND_SECTION_FIELDS = {
    "earningsEstimate": (
        "avg", "low", "high", "yearAgoEps", "numberOfAnalysts", "growth",
        "earningsCurrency",
    ),
    "revenueEstimate": (
        "avg", "low", "high", "yearAgoRevenue", "numberOfAnalysts", "growth",
        "revenueCurrency",
    ),
    "epsTrend": (
        "current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo",
        "epsTrendCurrency",
    ),
    "epsRevisions": (
        "upLast7days", "upLast30days", "downLast7Days", "downLast30days",
        "downLast90days", "epsRevisionsCurrency",
    ),
}

PRICE_TARGET_SOURCE_FIELDS = {
    "current": "currentPrice",
    "low": "targetLowPrice",
    "high": "targetHighPrice",
    "mean": "targetMeanPrice",
    "median": "targetMedianPrice",
}

EARNINGS_HISTORY_VALUE_FIELDS = (
    "epsEstimate",
    "epsActual",
    "epsDifference",
    "surprisePercent",
)


class ForecastContractError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalForecast:
    family: str
    contract_version: str
    payload: Mapping[str, Any]
    canonical_json: str
    content_hash: str
    schema_drift: tuple[str, ...]


@dataclass(frozen=True)
class ParsedPayload:
    status: str
    forecast: CanonicalForecast | None = None
    error_code: str | None = None
    error_message: str | None = None


def _field(mapping: Any, name: str) -> Any:
    if not isinstance(mapping, Mapping):
        return _ABSENT
    return mapping.get(name, _ABSENT)


def _decimal_text(value: int | float | Decimal) -> str:
    if isinstance(value, bool):
        raise ForecastContractError("boolean is not a forecast numeric value")
    if isinstance(value, float) and not math.isfinite(value):
        raise ForecastContractError("forecast numeric value must be finite")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ForecastContractError("invalid forecast numeric value") from exc
    if not number.is_finite():
        raise ForecastContractError("forecast numeric value must be finite")
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonical_state(value: Any = _ABSENT) -> dict[str, Any]:
    if value is _ABSENT:
        return {"state": STATE_FIELD_ABSENT}
    if value == {}:
        return {"state": STATE_EMPTY_OBJECT}
    if value is None:
        return {"state": STATE_EXPLICIT_NULL}
    if isinstance(value, Mapping):
        return canonical_state(value.get("raw", _ABSENT))
    if isinstance(value, bool):
        raise ForecastContractError("boolean is not a forecast numeric value")
    if isinstance(value, (int, float, Decimal)):
        state = STATE_NUMERIC_ZERO if value == 0 else STATE_NUMERIC_VALUE
        return {"state": state, "value": _decimal_text(value)}
    if isinstance(value, str):
        return {"state": STATE_TEXT_VALUE, "value": value}
    raise ForecastContractError(
        f"unsupported forecast value type: {type(value).__name__}"
    )


def _canonical_result(
    family: str,
    contract_version: str,
    payload: Mapping[str, Any],
    schema_drift: list[str],
) -> CanonicalForecast:
    canonical_json = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return CanonicalForecast(
        family=family,
        contract_version=contract_version,
        payload=payload,
        canonical_json=canonical_json,
        content_hash=hashlib.sha256(canonical_json.encode("ascii")).hexdigest(),
        schema_drift=tuple(sorted(set(schema_drift))),
    )


def _quote_module(payload: Mapping[str, Any], module_name: str) -> Mapping[str, Any]:
    quote_summary = payload.get("quoteSummary")
    if not isinstance(quote_summary, Mapping):
        raise ForecastContractError("quoteSummary must be an object")
    result = quote_summary.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], Mapping):
        raise ForecastContractError("quoteSummary.result must contain one object")
    module = result[0].get(module_name)
    if not isinstance(module, Mapping):
        raise ForecastContractError(f"{module_name} must be an object")
    return module


def _drift(prefix: str, mapping: Mapping[str, Any], expected: set[str]) -> list[str]:
    return [f"{prefix}.{key}" for key in mapping if key not in expected]


def _is_zero_placeholder(value: Any) -> bool:
    raw = value.get("raw") if isinstance(value, Mapping) else None
    return (
        isinstance(value, Mapping)
        and set(value) == {"raw", "fmt", "longFmt"}
        and isinstance(raw, (int, float))
        and not isinstance(raw, bool)
        and raw == 0
        and value.get("fmt") is None
        and value.get("longFmt") == "0"
    )


def _is_empty_earnings_trend_row(row: Any) -> bool:
    if not isinstance(row, Mapping):
        return False
    expected_row = {
        "maxAge", "period", "endDate", "growth", *EARNINGS_TREND_SECTION_FIELDS
    }
    if not set(row) <= expected_row or row.get("growth") != {}:
        return False
    earnings = row.get("earningsEstimate")
    revenue = row.get("revenueEstimate")
    eps_trend = row.get("epsTrend")
    revisions = row.get("epsRevisions")
    if not all(isinstance(value, Mapping) for value in (
        earnings, revenue, eps_trend, revisions
    )):
        return False
    if set(earnings) != set(EARNINGS_TREND_SECTION_FIELDS["earningsEstimate"]):
        return False
    if set(revenue) != set(EARNINGS_TREND_SECTION_FIELDS["revenueEstimate"]):
        return False
    if set(eps_trend) != set(EARNINGS_TREND_SECTION_FIELDS["epsTrend"]):
        return False
    if set(revisions) != set(EARNINGS_TREND_SECTION_FIELDS["epsRevisions"]):
        return False
    if any(
        earnings[field] != {}
        for field in EARNINGS_TREND_SECTION_FIELDS["earningsEstimate"]
        if field != "earningsCurrency"
    ) or earnings["earningsCurrency"] is not None:
        return False
    if not all(
        _is_zero_placeholder(revenue[field])
        for field in ("avg", "low", "high", "numberOfAnalysts")
    ):
        return False
    if revenue["yearAgoRevenue"] != {} or revenue["growth"] != {}:
        return False
    if revenue["revenueCurrency"] is not None:
        return False
    if any(
        eps_trend[field] != {}
        for field in EARNINGS_TREND_SECTION_FIELDS["epsTrend"]
        if field != "epsTrendCurrency"
    ) or eps_trend["epsTrendCurrency"] is not None:
        return False
    if any(
        revisions[field] != {}
        for field in EARNINGS_TREND_SECTION_FIELDS["epsRevisions"]
        if field != "epsRevisionsCurrency"
    ) or revisions["epsRevisionsCurrency"] is not None:
        return False
    return True


def _is_empty_earnings_trend_payload(payload: Mapping[str, Any]) -> bool:
    try:
        module = _quote_module(payload, "earningsTrend")
    except ForecastContractError:
        return False
    if not set(module) <= {"maxAge", "defaultMethodology", "trend"}:
        return False
    trend = module.get("trend")
    return (
        isinstance(trend, list)
        and bool(trend)
        and all(_is_empty_earnings_trend_row(row) for row in trend)
    )


def canonicalize_earnings_trend(payload: Mapping[str, Any]) -> CanonicalForecast:
    module = _quote_module(payload, "earningsTrend")
    trend = module.get("trend")
    if not isinstance(trend, list):
        raise ForecastContractError("earningsTrend.trend must be a list")
    drift = _drift(
        "earningsTrend", module, {"maxAge", "defaultMethodology", "trend"}
    )
    rows: list[dict[str, Any]] = []
    expected_row = {
        "maxAge", "period", "endDate", "growth", *EARNINGS_TREND_SECTION_FIELDS
    }
    for occurrence_index, source_row in enumerate(trend):
        if not isinstance(source_row, Mapping):
            raise ForecastContractError("each earningsTrend row must be an object")
        period = source_row.get("period")
        end_date = source_row.get("endDate")
        if not isinstance(period, str) or not isinstance(end_date, str):
            raise ForecastContractError("trend row period and endDate are required strings")
        try:
            normalized_date = date.fromisoformat(end_date).isoformat()
        except ValueError as exc:
            raise ForecastContractError("provider endDate must be ISO YYYY-MM-DD") from exc
        drift.extend(_drift(f"trend[{occurrence_index}]", source_row, expected_row))
        row: dict[str, Any] = {
            "occurrenceIndex": occurrence_index,
            "providerHorizon": period,
            "providerEndDate": normalized_date,
            "topLevelGrowth": canonical_state(_field(source_row, "growth")),
        }
        for section_name, field_names in EARNINGS_TREND_SECTION_FIELDS.items():
            section = _field(source_row, section_name)
            if section is not _ABSENT and not isinstance(section, Mapping):
                raise ForecastContractError(f"{section_name} must be an object")
            if isinstance(section, Mapping):
                drift.extend(
                    _drift(
                        f"trend[{occurrence_index}].{section_name}",
                        section,
                        set(field_names),
                    )
                )
            row[section_name] = {
                field_name: canonical_state(_field(section, field_name))
                for field_name in field_names
            }
        rows.append(row)
    canonical = {
        "contractVersion": EARNINGS_TREND_CONTRACT_VERSION,
        "defaultMethodology": canonical_state(_field(module, "defaultMethodology")),
        "rows": rows,
    }
    return _canonical_result(
        FAMILY_FISCAL_ESTIMATE,
        EARNINGS_TREND_CONTRACT_VERSION,
        canonical,
        drift,
    )


def canonicalize_price_targets(payload: Mapping[str, Any]) -> CanonicalForecast:
    module = _quote_module(payload, "financialData")
    expected = {"maxAge", "financialCurrency", *PRICE_TARGET_SOURCE_FIELDS.values()}
    canonical = {
        "contractVersion": PRICE_TARGET_CONTRACT_VERSION,
        "currency": canonical_state(_field(module, "financialCurrency")),
        "values": {
            name: canonical_state(_field(module, source_name))
            for name, source_name in PRICE_TARGET_SOURCE_FIELDS.items()
        },
    }
    return _canonical_result(
        FAMILY_PRICE_TARGET,
        PRICE_TARGET_CONTRACT_VERSION,
        canonical,
        _drift("financialData", module, expected),
    )


def _quarter_date(value: Any) -> str:
    if not isinstance(value, Mapping):
        raise ForecastContractError("earningsHistory quarter must be an object")
    raw = value.get("raw", _ABSENT)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return datetime.fromtimestamp(raw, tz=timezone.utc).date().isoformat()
    formatted = value.get("fmt")
    if not isinstance(formatted, str):
        raise ForecastContractError("earningsHistory quarter needs raw epoch or fmt date")
    try:
        return date.fromisoformat(formatted).isoformat()
    except ValueError as exc:
        raise ForecastContractError("earningsHistory quarter must be ISO date") from exc


def canonicalize_earnings_history(payload: Mapping[str, Any]) -> CanonicalForecast:
    module = _quote_module(payload, "earningsHistory")
    history = module.get("history")
    if not isinstance(history, list):
        raise ForecastContractError("earningsHistory.history must be a list")
    drift = _drift(
        "earningsHistory", module, {"maxAge", "defaultMethodology", "history"}
    )
    rows = []
    expected_row = {
        "maxAge", "period", "quarter", "currency", *EARNINGS_HISTORY_VALUE_FIELDS
    }
    for occurrence_index, source_row in enumerate(history):
        if not isinstance(source_row, Mapping):
            raise ForecastContractError("each earningsHistory row must be an object")
        period = source_row.get("period")
        if not isinstance(period, str):
            raise ForecastContractError("earningsHistory period must be a string")
        drift.extend(_drift(f"history[{occurrence_index}]", source_row, expected_row))
        rows.append(
            {
                "occurrenceIndex": occurrence_index,
                "providerPeriod": period,
                "providerQuarterDate": _quarter_date(source_row.get("quarter")),
                "currency": canonical_state(_field(source_row, "currency")),
                **{
                    field_name: canonical_state(_field(source_row, field_name))
                    for field_name in EARNINGS_HISTORY_VALUE_FIELDS
                },
            }
        )
    canonical = {
        "contractVersion": EARNINGS_HISTORY_CONTRACT_VERSION,
        "defaultMethodology": canonical_state(_field(module, "defaultMethodology")),
        "rows": rows,
    }
    return _canonical_result(
        FAMILY_EARNINGS_HISTORY_REFERENCE,
        EARNINGS_HISTORY_CONTRACT_VERSION,
        canonical,
        drift,
    )


def canonicalize_family(family: str, payload: Mapping[str, Any]) -> CanonicalForecast:
    if family == FAMILY_FISCAL_ESTIMATE:
        return canonicalize_earnings_trend(payload)
    if family == FAMILY_PRICE_TARGET:
        return canonicalize_price_targets(payload)
    if family == FAMILY_EARNINGS_HISTORY_REFERENCE:
        return canonicalize_earnings_history(payload)
    raise ForecastContractError(f"unsupported forecast family: {family}")


def _has_semantic_data(forecast: CanonicalForecast) -> bool:
    if forecast.family in {FAMILY_FISCAL_ESTIMATE, FAMILY_EARNINGS_HISTORY_REFERENCE}:
        return bool(forecast.payload["rows"])
    values = forecast.payload["values"]
    return any(
        value["state"] in {STATE_NUMERIC_ZERO, STATE_NUMERIC_VALUE, STATE_TEXT_VALUE}
        for value in values.values()
    )


def parse_payload(family: str, payload: Any) -> ParsedPayload:
    if not isinstance(payload, Mapping):
        return ParsedPayload(STATUS_MALFORMED, error_code="PAYLOAD_NOT_OBJECT")
    quote_summary = payload.get("quoteSummary")
    if not isinstance(quote_summary, Mapping):
        return ParsedPayload(STATUS_MALFORMED, error_code="QUOTE_SUMMARY_NOT_OBJECT")
    error = quote_summary.get("error")
    if isinstance(error, Mapping):
        code = str(error.get("code") or "PROVIDER_ERROR")
        message = str(error.get("description") or "")
        status = (
            STATUS_PROVIDER_SYMBOL_UNAVAILABLE
            if code.lower() == "not found"
            else STATUS_MALFORMED
        )
        return ParsedPayload(status, error_code=code, error_message=message)
    if family == FAMILY_FISCAL_ESTIMATE and _is_empty_earnings_trend_payload(payload):
        return ParsedPayload(STATUS_VALID_NO_DATA)
    try:
        forecast = canonicalize_family(family, payload)
    except (ForecastContractError, OverflowError, OSError) as exc:
        return ParsedPayload(
            STATUS_MALFORMED,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
    return ParsedPayload(
        STATUS_SUCCESS_WITH_DATA if _has_semantic_data(forecast) else STATUS_VALID_NO_DATA,
        forecast=forecast,
    )
