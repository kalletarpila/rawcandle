from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .swing_daily_report import WATCHLIST_MISSING_PRICE_STATUSES

EMERGENCY_SELL_PRESSURE = "EMERGENCY_SELL_PRESSURE"
SHARP_2D_DROP = "SHARP_2D_DROP"
WATCH_PRESSURE = "WATCH_PRESSURE"
NO_EMERGENCY = "NO_EMERGENCY"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class Rolling2SellPressureClassification:
    rolling_2_sell_pressure_state: str
    primary_reason: str
    risk_reason: str
    next_action: str


def _is_fresh_or_recent(value: object | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().upper()
    return normalized in {"FRESH", "RECENT", "CURRENT"}


def _has_fresh_bos_down(row: Mapping[str, Any]) -> bool:
    return (
        row.get("last_latest_bos_event_type") == "BOS_DOWN"
        and _is_fresh_or_recent(row.get("last_latest_bos_freshness"))
    )


def _has_fresh_reset(row: Mapping[str, Any]) -> bool:
    return (
        row.get("last_latest_reset_reason") not in {None, "", "NULL"}
        and _is_fresh_or_recent(row.get("last_latest_reset_freshness"))
    )


def _is_high_exit_risk_status(value: object | None) -> bool:
    return value == "HIGH_EXIT_RISK"


def _is_group_or_medium_risk_status(value: object | None) -> bool:
    return value in {"GROUP_RISK", "MEDIUM_EXIT_RISK"}


def _has_explicit_extreme_exit_severity(value: object | None) -> bool:
    return value in {"EXTREME", "CRITICAL"}


def _has_exit_reason_token(value: object | None, *tokens: str) -> bool:
    if value in {None, "", "NULL"}:
        return False
    normalized_tokens = {token.strip().lower() for token in tokens}
    normalized_parts = {
        part.strip().lower()
        for part in str(value).replace("|", ";").split(";")
        if part.strip()
    }
    return any(token in normalized_parts for token in normalized_tokens)


def _float_value(value: object | None) -> float | None:
    if value in {None, "", "NULL"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_negative_ema20_context(value: object | None) -> bool:
    numeric = _float_value(value)
    return numeric is not None and numeric < 0.0


def _has_structural_breakdown_label(value: object | None) -> bool:
    return value in {"LL", "LH"}


def classify_rolling_2_sell_pressure_row(row: Mapping[str, Any]) -> Rolling2SellPressureClassification:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get("all_price_rows_missing") is True:
        return Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state=INSUFFICIENT_DATA,
            primary_reason="MISSING_PRICE_CONTEXT",
            risk_reason="",
            next_action="WAIT_FOR_DATA",
        )

    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state=INSUFFICIENT_DATA,
            primary_reason="MISSING_TICKER_CONTEXT",
            risk_reason="",
            next_action="WAIT_FOR_DATA",
        )

    current_watchlist_status = row.get("current_watchlist_status")
    window_watchlist_status = row.get("window_watchlist_status")
    exit_risk_days = int(row.get("exit_risk_days") or 0)
    high_exit_risk_days = int(row.get("high_exit_risk_days") or 0)
    medium_exit_risk_days = int(row.get("medium_exit_risk_days") or 0)
    latest_exit_severity = row.get("last_exit_risk_severity")
    latest_exit_reason = row.get("last_exit_reason")
    trend_state = row.get("last_ticker_trend_state")
    latest_bearish_relevance_class = row.get("latest_bearish_relevance_class")
    has_fresh_bos_down = _has_fresh_bos_down(row)
    has_fresh_reset = _has_fresh_reset(row)
    current_high_exit_risk = _is_high_exit_risk_status(current_watchlist_status)
    current_medium_or_group_risk = _is_group_or_medium_risk_status(current_watchlist_status)
    window_medium_or_group_risk = _is_group_or_medium_risk_status(window_watchlist_status)
    has_relevant_bearish_context = latest_bearish_relevance_class == "RELEVANT"
    has_weak_bearish_context = latest_bearish_relevance_class == "WEAK_CONTEXT"
    has_extreme_or_critical_severity = _has_explicit_extreme_exit_severity(latest_exit_severity)
    has_structural_breakdown_label = _has_structural_breakdown_label(row.get("last_latest_structure_label"))
    has_structure_label_breakdown_reason = _has_exit_reason_token(latest_exit_reason, "latest_structure_label_ll")
    has_close_below_ema20_reason = _has_exit_reason_token(latest_exit_reason, "close_below_ema20")
    has_return_10d_pressure_reason = _has_exit_reason_token(latest_exit_reason, "return_10d_lt_minus_8pct")
    has_double_breakdown_reason = has_close_below_ema20_reason and has_return_10d_pressure_reason
    has_emergency_structure_confirmation = (
        trend_state == "DOWN"
        or has_structural_breakdown_label
        or has_fresh_bos_down
        or has_fresh_reset
        or has_structure_label_breakdown_reason
        or has_double_breakdown_reason
    )

    if (
        (has_extreme_or_critical_severity and exit_risk_days >= 1)
        or (
            exit_risk_days >= 2
            and (high_exit_risk_days >= 2 or current_high_exit_risk)
            and latest_exit_severity == "HIGH"
            and has_emergency_structure_confirmation
        )
        or (has_fresh_bos_down and has_fresh_reset and exit_risk_days >= 1)
        or (has_relevant_bearish_context and current_high_exit_risk)
    ):
        risk_reason = (
            "CRITICAL_OR_EXTREME_EXIT_SEVERITY"
            if has_extreme_or_critical_severity and exit_risk_days >= 1
            else "HIGH_PRESSURE_WITH_STRUCTURAL_BREAKDOWN"
            if (
                exit_risk_days >= 2
                and (high_exit_risk_days >= 2 or current_high_exit_risk)
                and latest_exit_severity == "HIGH"
                and has_emergency_structure_confirmation
            )
            else "FRESH_BOS_DOWN_AND_RESET"
            if has_fresh_bos_down and has_fresh_reset and exit_risk_days >= 1
            else "RELEVANT_BEARISH_CONTEXT_WITH_CURRENT_HIGH_EXIT_RISK"
        )
        return Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state=EMERGENCY_SELL_PRESSURE,
            primary_reason="CONFIRMED_TWO_DAY_SELL_PRESSURE",
            risk_reason=risk_reason,
            next_action="CHECK_STOP_OR_REDUCE",
        )

    if (
        (exit_risk_days >= 2 and high_exit_risk_days >= 2 and latest_exit_severity == "HIGH")
        or (exit_risk_days >= 2 and latest_exit_severity in {"MEDIUM", "HIGH"})
        or (high_exit_risk_days >= 1 and (has_close_below_ema20_reason or has_return_10d_pressure_reason))
        or (has_relevant_bearish_context and exit_risk_days >= 1)
        or (has_fresh_bos_down and exit_risk_days >= 1)
    ):
        risk_reason = (
            "TWO_DAY_HIGH_PRESSURE_WITHOUT_FULL_BREAKDOWN"
            if exit_risk_days >= 2 and high_exit_risk_days >= 2 and latest_exit_severity == "HIGH"
            else "EXIT_RISK_PERSISTENT_TWO_DAYS"
            if exit_risk_days >= 2 and latest_exit_severity in {"MEDIUM", "HIGH"}
            else "BREAKDOWN_REASON_WITH_HIGH_EXIT_DAY"
            if high_exit_risk_days >= 1 and (has_close_below_ema20_reason or has_return_10d_pressure_reason)
            else "RELEVANT_BEARISH_CONTEXT"
            if has_relevant_bearish_context and exit_risk_days >= 1
            else "FRESH_BOS_DOWN"
        )
        return Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state=SHARP_2D_DROP,
            primary_reason="SHARP_SHORT_TERM_DROP",
            risk_reason=risk_reason,
            next_action="TIGHTEN_STOP_REVIEW_DAILY_TRIGGER",
        )

    if (
        exit_risk_days >= 1
        or medium_exit_risk_days >= 1
        or latest_exit_severity not in {None, "", "NULL"}
        or has_weak_bearish_context
        or current_medium_or_group_risk
        or window_medium_or_group_risk
        or current_high_exit_risk
        or _is_negative_ema20_context(row.get("last_distance_to_ema20_pct"))
    ):
        risk_reason = (
            "EXIT_RISK_PRESENT"
            if exit_risk_days >= 1 and latest_exit_severity in {None, "", "NULL"}
            else "MEDIUM_EXIT_RISK"
            if medium_exit_risk_days >= 1 or latest_exit_severity == "MEDIUM"
            else "GROUP_RISK"
            if current_watchlist_status == "GROUP_RISK" or window_watchlist_status == "GROUP_RISK"
            else "CURRENT_HIGH_EXIT_RISK"
            if current_high_exit_risk
            else "WEAK_BEARISH_CONTEXT"
            if has_weak_bearish_context
            else "NEGATIVE_EMA20_DISTANCE"
            if _is_negative_ema20_context(row.get("last_distance_to_ema20_pct"))
            else "WINDOW_MEDIUM_EXIT_RISK"
            if window_watchlist_status == "MEDIUM_EXIT_RISK"
            else "MILD_EXIT_RISK_SEVERITY"
        )
        return Rolling2SellPressureClassification(
            rolling_2_sell_pressure_state=WATCH_PRESSURE,
            primary_reason="MILD_OR_UNCONFIRMED_SELL_PRESSURE",
            risk_reason=risk_reason,
            next_action="MONITOR_NEXT_SESSION",
        )

    return Rolling2SellPressureClassification(
        rolling_2_sell_pressure_state=NO_EMERGENCY,
        primary_reason="NO_TWO_DAY_SELL_PRESSURE",
        risk_reason="",
        next_action="NONE",
    )
