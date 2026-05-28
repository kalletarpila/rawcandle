from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .swing_daily_report import WATCHLIST_MISSING_PRICE_STATUSES


@dataclass(frozen=True)
class Rolling5PullbackClassification:
    rolling_5_pullback_state: str
    primary_reason: str
    blocking_reason: str
    next_action: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (
            self.rolling_5_pullback_state,
            self.primary_reason,
            self.blocking_reason,
            self.next_action,
        )


def has_fresh_bos_down(row: Mapping[str, Any]) -> bool:
    return (
        row.get("last_latest_bos_event_type") == "BOS_DOWN"
        and _is_fresh_or_recent(row.get("last_latest_bos_freshness"))
    )


def has_fresh_reset(row: Mapping[str, Any]) -> bool:
    return (
        row.get("last_latest_reset_reason") not in {None, "", "NULL"}
        and _is_fresh_or_recent(row.get("last_latest_reset_freshness"))
    )


def is_pullback_oriented_status(value: object | None) -> bool:
    return value in {"PULLBACK_CANDIDATE", "ADD_ON_PULLBACK"}


def classify_rolling_5_pullback_row(row: Mapping[str, Any]) -> Rolling5PullbackClassification:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get("all_price_rows_missing") is True:
        return Rolling5PullbackClassification(
            "INSUFFICIENT_DATA",
            "MISSING_PRICE_CONTEXT",
            "price_data_missing",
            "WAIT_FOR_DATA",
        )

    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return Rolling5PullbackClassification(
            "INSUFFICIENT_DATA",
            "MISSING_TICKER_CONTEXT",
            "missing_ticker",
            "WAIT_FOR_DATA",
        )

    trend_state = row.get("last_ticker_trend_state")
    current_watchlist_status = row.get("current_watchlist_status")
    window_watchlist_status = row.get("window_watchlist_status")
    pullback_days = int(row.get("pullback_days") or 0)
    fast_ema10_pullback_days = int(row.get("fast_ema10_pullback_days") or 0)
    conservative_ema20_pullback_days = int(row.get("conservative_ema20_pullback_days") or 0)
    exit_risk_days = int(row.get("exit_risk_days") or 0)
    latest_exit_severity = row.get("last_exit_risk_severity")
    fresh_bos_down = has_fresh_bos_down(row)
    fresh_reset = has_fresh_reset(row)
    has_relevant_bearish_context = row.get("latest_bearish_relevance_class") == "RELEVANT"
    current_high_exit_risk = current_watchlist_status == "HIGH_EXIT_RISK"
    window_high_exit_risk = window_watchlist_status == "HIGH_EXIT_RISK"
    has_explicit_high_severity = latest_exit_severity in {"HIGH", "EXTREME", "CRITICAL"}
    has_explicit_extreme_severity = latest_exit_severity in {"EXTREME", "CRITICAL"}
    has_pullback_evidence = (
        pullback_days > 0
        or fast_ema10_pullback_days > 0
        or conservative_ema20_pullback_days > 0
        or is_pullback_oriented_status(current_watchlist_status)
        or is_pullback_oriented_status(window_watchlist_status)
    )
    has_pullback_blocker = (
        trend_state == "DOWN"
        or fresh_bos_down
        or fresh_reset
        or has_relevant_bearish_context
        or current_high_exit_risk
        or has_explicit_high_severity
    )
    has_severe_short_term_breakdown = (
        fresh_bos_down
        or (fresh_reset and (trend_state == "DOWN" or current_high_exit_risk or has_explicit_high_severity))
        or (trend_state == "DOWN" and current_high_exit_risk)
        or has_explicit_extreme_severity
        or (has_relevant_bearish_context and current_high_exit_risk)
    )

    if not has_pullback_evidence:
        if has_severe_short_term_breakdown:
            blocking_reason = (
                "recent_bos_down"
                if fresh_bos_down
                else "recent_reset"
                if fresh_reset and (trend_state == "DOWN" or current_high_exit_risk or has_explicit_high_severity)
                else "extreme_exit_risk_severity"
                if has_explicit_extreme_severity
                else "down_trend_with_current_high_exit_risk"
                if trend_state == "DOWN" and current_high_exit_risk
                else "relevant_bearish_context_with_current_high_exit_risk"
            )
            return Rolling5PullbackClassification(
                "SHORT_TERM_BREAKDOWN",
                "SHORT_TERM_BREAKDOWN_WITHOUT_PULLBACK_SETUP",
                blocking_reason,
                "MONITOR_EXIT_RISK",
            )
        return Rolling5PullbackClassification(
            "NO_PULLBACK",
            "NO_MEANINGFUL_PULLBACK_EVIDENCE",
            "",
            "NONE",
        )

    if has_pullback_blocker:
        blocking_reason = (
            "recent_bos_down"
            if fresh_bos_down
            else "recent_reset"
            if fresh_reset
            else "high_exit_risk_status"
            if current_high_exit_risk
            else "high_exit_risk_severity"
            if has_explicit_high_severity
            else "relevant_bearish_context"
            if has_relevant_bearish_context
            else "down_trend"
        )
        return Rolling5PullbackClassification(
            "FAILED_PULLBACK",
            "PULLBACK_SETUP_BLOCKED",
            blocking_reason,
            "REMOVE_FROM_PULLBACK_LIST",
        )

    if (
        has_pullback_evidence
        and (trend_state == "UP" or is_pullback_oriented_status(current_watchlist_status) or is_pullback_oriented_status(window_watchlist_status))
        and exit_risk_days == 0
        and not has_relevant_bearish_context
        and not current_high_exit_risk
        and not window_high_exit_risk
    ):
        primary_reason = (
            "CONFIRMED_EMA20_PULLBACK_CONTEXT"
            if conservative_ema20_pullback_days > 0
            else "CONFIRMED_EMA10_PULLBACK_CONTEXT"
            if fast_ema10_pullback_days > 0
            else "PULLBACK_EVIDENCE_WITH_ACCEPTABLE_STRUCTURE"
        )
        return Rolling5PullbackClassification(
            "PULLBACK_CANDIDATE",
            primary_reason,
            "",
            "REVIEW_FOR_DAILY_TRIGGER",
        )

    return Rolling5PullbackClassification(
        "EARLY_PULLBACK",
        "EARLY_OR_UNCONFIRMED_PULLBACK",
        "EXIT_RISK_DAYS_WITHOUT_HIGH_SEVERITY" if exit_risk_days > 0 else "MIXED_TREND_OR_STATUS",
        "MONITOR_FOR_CONFIRMATION",
    )


def _is_fresh_or_recent(value: object | None) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().upper()
    return normalized in {"FRESH", "RECENT", "CURRENT"}
