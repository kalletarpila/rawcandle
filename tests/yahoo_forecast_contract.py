from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any


CONTRACT_VERSION = "yahoo_earnings_trend_v1"
_ABSENT = object()

SECTION_FIELDS = {
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


def _decimal_text(value: int | float | Decimal) -> str:
    number = Decimal(str(value))
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonical_state(value: Any = _ABSENT) -> dict[str, Any]:
    if value is _ABSENT:
        return {"state": "FIELD_ABSENT"}
    if value == {}:
        return {"state": "EMPTY_OBJECT"}
    if value is None:
        return {"state": "EXPLICIT_NULL"}
    if isinstance(value, dict):
        return canonical_state(value.get("raw", _ABSENT))
    if isinstance(value, bool):
        raise ValueError("boolean is not a forecast numeric value")
    if isinstance(value, (int, float, Decimal)):
        state = "NUMERIC_ZERO" if value == 0 else "NUMERIC_VALUE"
        return {"state": state, "value": _decimal_text(value)}
    if isinstance(value, str):
        return {"state": "TEXT_VALUE", "value": value}
    raise ValueError(f"unsupported forecast value type: {type(value).__name__}")


def _field(mapping: Any, name: str) -> Any:
    if not isinstance(mapping, dict):
        return _ABSENT
    return mapping.get(name, _ABSENT)


def classify_result(case: dict[str, Any]) -> str:
    transport = case.get("transport") or {}
    status = transport.get("http_status")
    if status == 429 or transport.get("exception_type") == "YFRateLimitError":
        return "RATE_LIMITED"
    if isinstance(status, int) and 500 <= status <= 599:
        return "TRANSIENT_5XX"
    payload = case.get("payload")
    if not isinstance(payload, dict):
        return "MALFORMED_OR_SCHEMA_MISMATCH"
    quote_summary = payload.get("quoteSummary")
    if not isinstance(quote_summary, dict):
        return "MALFORMED_OR_SCHEMA_MISMATCH"
    error = quote_summary.get("error")
    if isinstance(error, dict) and error.get("code") == "Not Found":
        return "PROVIDER_SYMBOL_UNAVAILABLE"
    result = quote_summary.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return "MALFORMED_OR_SCHEMA_MISMATCH"
    module = result[0].get("earningsTrend")
    if not isinstance(module, dict) or not isinstance(module.get("trend"), list):
        return "MALFORMED_OR_SCHEMA_MISMATCH"
    return "VALID_NO_DATA" if not module["trend"] else "SUCCESS_WITH_DATA"


def canonicalize(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("quoteSummary", {}).get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise ValueError("quoteSummary.result must contain one result object")
    module = result[0].get("earningsTrend")
    if not isinstance(module, dict) or not isinstance(module.get("trend"), list):
        raise ValueError("earningsTrend.trend must be a list")

    rows = []
    for occurrence_index, source_row in enumerate(module["trend"]):
        if not isinstance(source_row, dict):
            raise ValueError("each earningsTrend row must be an object")
        period = source_row.get("period")
        end_date = source_row.get("endDate")
        if not isinstance(period, str) or not isinstance(end_date, str):
            raise ValueError("trend row period and endDate are required strings")
        normalized_date = date.fromisoformat(end_date).isoformat()
        row = {
            "occurrenceIndex": occurrence_index,
            "providerHorizon": period,
            "providerEndDate": normalized_date,
            "topLevelGrowth": canonical_state(_field(source_row, "growth")),
        }
        for section_name, field_names in SECTION_FIELDS.items():
            section = _field(source_row, section_name)
            row[section_name] = {
                field_name: canonical_state(_field(section, field_name))
                for field_name in field_names
            }
        rows.append(row)

    return {
        "contractVersion": CONTRACT_VERSION,
        "defaultMethodology": canonical_state(
            _field(module, "defaultMethodology")
        ),
        "rows": rows,
    }


def semantic_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        canonicalize(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def semantic_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(semantic_json(payload).encode("ascii")).hexdigest()
