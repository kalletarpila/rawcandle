from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .swing_daily_report import EXIT_RISK_SEVERITY_PRIORITY, WATCHLIST_MISSING_PRICE_STATUSES


@dataclass(frozen=True)
class Rolling30BuyClassification:
    rolling_30_buy_state: str
    primary_reason: str
    blocking_reason: str


@dataclass(frozen=True)
class Rolling30ExitClassification:
    rolling_30_exit_state: str
    primary_reason: str
    risk_reason: str


def _is_high_exit_risk_status(value: object | None) -> bool:
    return value in {"HIGH_EXIT_RISK", "WINDOW_HIGH_EXIT_RISK"}


def _is_group_or_medium_risk_status(value: object | None) -> bool:
    return value in {"GROUP_RISK", "MEDIUM_EXIT_RISK"}


def _is_buy_oriented_status(value: object | None) -> bool:
    return value in {"BREAKOUT_CANDIDATE", "PULLBACK_CANDIDATE"}


def _has_negative_group_context(row: Mapping[str, object]) -> bool:
    return row.get("window_watchlist_status") in {"HIGH_EXIT_RISK", "GROUP_RISK"}


def _has_fresh_bos_down(row: Mapping[str, Any]) -> bool:
    return row.get("last_latest_bos_event_type") == "BOS_DOWN" and row.get(
        "last_latest_bos_freshness"
    ) in {"FRESH", "RECENT", "CURRENT"}


def _has_fresh_reset(row: Mapping[str, Any]) -> bool:
    return row.get("last_latest_reset_reason") not in {
        None,
        "",
        "NULL",
    } and row.get("last_latest_reset_freshness") in {"FRESH", "RECENT", "CURRENT"}


def _has_explicit_high_exit_severity(value: object | None) -> bool:
    return value in {"HIGH", "EXTREME", "CRITICAL"}


def _has_explicit_extreme_exit_severity(value: object | None) -> bool:
    return value in {"EXTREME", "CRITICAL"}


def _rolling_30_high_exit_risk_reason(
    current_watchlist_status: object | None,
    window_watchlist_status: object | None,
) -> str | None:
    if _is_high_exit_risk_status(current_watchlist_status):
        return "CURRENT_HIGH_EXIT_RISK"
    if _is_high_exit_risk_status(window_watchlist_status):
        return "HISTORICAL_WINDOW_HIGH_EXIT_RISK"
    return None


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


def classify_rolling_30_buy_row(row: Mapping[str, object]) -> Rolling30BuyClassification:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get(
        "all_price_rows_missing"
    ) is True:
        return Rolling30BuyClassification(
            "INSUFFICIENT_DATA", "missing_price_context", "price_data_missing"
        )

    trend_state = row.get("last_ticker_trend_state")
    breakout_days = int(row.get("breakout_days") or 0)
    pullback_days = int(row.get("pullback_days") or 0)
    exit_risk_days = int(row.get("exit_risk_days") or 0)
    has_fresh_bos_down = _has_fresh_bos_down(row)
    has_fresh_reset = _has_fresh_reset(row)
    has_buy_oriented_status = _is_buy_oriented_status(
        row.get("current_watchlist_status")
    ) or _is_buy_oriented_status(row.get("window_watchlist_status"))
    has_buy_activity = breakout_days > 0 or pullback_days > 0 or has_buy_oriented_status

    has_clear_bearish_relevance = row.get("latest_bearish_relevance_class") == "RELEVANT"
    current_watchlist_status = row.get("current_watchlist_status")
    window_watchlist_status = row.get("window_watchlist_status")
    has_explicit_current_high_risk = _is_high_exit_risk_status(current_watchlist_status)
    has_explicit_high_severity = _has_explicit_high_exit_severity(
        row.get("last_exit_risk_severity")
    )
    has_window_high_risk = _is_high_exit_risk_status(window_watchlist_status)
    has_mixed_context = (
        current_watchlist_status == "NEUTRAL_MONITOR"
        or _is_group_or_medium_risk_status(current_watchlist_status)
        or _is_group_or_medium_risk_status(window_watchlist_status)
        or has_window_high_risk
        or exit_risk_days > 0
    )

    if (
        trend_state == "DOWN"
        or has_fresh_bos_down
        or has_fresh_reset
        or has_explicit_current_high_risk
        or has_explicit_high_severity
        or has_clear_bearish_relevance
    ):
        blocking_reason = (
            "recent_bos_down"
            if has_fresh_bos_down
            else "recent_reset"
            if has_fresh_reset
            else "CURRENT_HIGH_EXIT_RISK"
            if has_explicit_current_high_risk
            else "high_exit_risk_severity"
            if has_explicit_high_severity
            else "relevant_bearish_context"
            if has_clear_bearish_relevance
            else "down_trend"
        )
        return Rolling30BuyClassification(
            "AVOID", "clear_structural_or_exit_block", blocking_reason
        )

    if (
        has_buy_activity
        and (trend_state == "UP" or has_buy_oriented_status)
        and not _has_negative_group_context(row)
        and exit_risk_days == 0
        and not has_clear_bearish_relevance
        and not has_window_high_risk
    ):
        reason = (
            "UP_STRUCTURE_WITH_REPEATED_BUY_SIGNAL"
            if breakout_days > 0
            else "UP_STRUCTURE_WITH_PULLBACK_CONTEXT"
        )
        return Rolling30BuyClassification("BUY_ZONE", reason, "")

    if has_buy_activity or has_mixed_context:
        blocking_reason = (
            _rolling_30_high_exit_risk_reason(
                current_watchlist_status, window_watchlist_status
            )
            if has_window_high_risk
            else "GROUP_RISK"
            if window_watchlist_status == "GROUP_RISK"
            else "EXIT_RISK_DAYS_WITHOUT_HIGH_SEVERITY"
            if exit_risk_days > 0
            else ""
        )
        return Rolling30BuyClassification(
            "WATCH_ZONE", "MIXED_OR_UNCONFIRMED_STRUCTURE", blocking_reason
        )

    return Rolling30BuyClassification("WATCH_ZONE", "MIXED_OR_UNCONFIRMED_STRUCTURE", "")


def classify_rolling_30_exit_row(row: Mapping[str, object]) -> Rolling30ExitClassification:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get(
        "all_price_rows_missing"
    ) is True:
        return Rolling30ExitClassification(
            "INSUFFICIENT_DATA", "missing_price_context", "price_data_missing"
        )

    exit_risk_days = int(row.get("exit_risk_days") or 0)
    high_exit_risk_days = int(row.get("high_exit_risk_days") or 0)
    medium_exit_risk_days = int(row.get("medium_exit_risk_days") or 0)
    latest_bearish_relevance_class = row.get("latest_bearish_relevance_class")
    has_fresh_bos_down = _has_fresh_bos_down(row)
    has_fresh_reset = _has_fresh_reset(row)
    has_extreme_group_context = row.get("last_subindustry_overheat_risk_level") == "EXTREME"
    current_watchlist_status = row.get("current_watchlist_status")
    window_watchlist_status = row.get("window_watchlist_status")
    latest_exit_severity = row.get("last_exit_risk_severity")
    trend_state = row.get("last_ticker_trend_state")

    if _has_explicit_extreme_exit_severity(latest_exit_severity):
        return Rolling30ExitClassification(
            "EXTREME", "EXTREME_EXIT_RISK", "CRITICAL_EXIT_RISK_SEVERITY"
        )

    if (
        latest_exit_severity == "HIGH"
        and exit_risk_days >= 15
        and trend_state == "DOWN"
        and (has_fresh_bos_down or has_fresh_reset)
    ):
        return Rolling30ExitClassification(
            "EXTREME", "EXTREME_EXIT_RISK", "HIGH_SEVERITY_WITH_FRESH_BREAKDOWN"
        )

    if (
        latest_exit_severity == "HIGH"
        or _is_high_exit_risk_status(current_watchlist_status)
        or has_fresh_bos_down
        or has_fresh_reset
        or latest_bearish_relevance_class == "RELEVANT"
        or (exit_risk_days >= 5 and latest_exit_severity not in {None, "", "NULL"})
    ):
        risk_reason = (
            "CURRENT_HIGH_EXIT_RISK"
            if _is_high_exit_risk_status(current_watchlist_status)
            else "HIGH_EXIT_RISK_SEVERITY"
            if latest_exit_severity == "HIGH"
            else "RECENT_BOS_DOWN"
            if has_fresh_bos_down
            else "RECENT_RESET"
            if has_fresh_reset
            else "RELEVANT_BEARISH_CONTEXT"
            if latest_bearish_relevance_class == "RELEVANT"
            else "REPEATED_EXIT_RISK_WITH_SEVERITY"
        )
        return Rolling30ExitClassification("EXIT_ZONE", "ELEVATED_EXIT_RISK", risk_reason)

    if (
        exit_risk_days > 0
        or medium_exit_risk_days > 0
        or _is_high_exit_risk_status(window_watchlist_status)
        or _is_group_or_medium_risk_status(window_watchlist_status)
        or row.get("last_subindustry_overheat_risk_level") in {"HIGH", "ELEVATED", "EXTREME"}
        or latest_bearish_relevance_class == "WEAK_CONTEXT"
        or has_extreme_group_context
    ):
        risk_reason = (
            "EXIT_RISK_DAYS_WITHOUT_HIGH_SEVERITY"
            if exit_risk_days > 0 and latest_exit_severity in {None, "", "NULL"}
            else "GROUP_RISK"
            if window_watchlist_status == "GROUP_RISK"
            else "HISTORICAL_WINDOW_HIGH_EXIT_RISK"
            if _is_high_exit_risk_status(window_watchlist_status)
            else "WINDOW_MEDIUM_EXIT_RISK"
            if window_watchlist_status == "MEDIUM_EXIT_RISK"
            else "WEAK_BEARISH_RELEVANCE"
            if latest_bearish_relevance_class == "WEAK_CONTEXT"
            else "MILD_OR_GROUP_EXIT_RISK"
        )
        return Rolling30ExitClassification(
            "WATCH", "MILD_OR_UNCONFIRMED_EXIT_RISK", risk_reason
        )

    return Rolling30ExitClassification("NORMAL", "NO_MEANINGFUL_EXIT_RISK", "")


def build_rolling_30_role_rows_from_base_rows(
    base_rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    buy_rows: list[dict[str, object]] = []
    exit_rows: list[dict[str, object]] = []
    for row in base_rows:
        buy_classification = classify_rolling_30_buy_row(row)
        buy_rows.append(
            {
                "ticker": row.get("ticker"),
                "rolling_30_buy_state": buy_classification.rolling_30_buy_state,
                "primary_layer": row.get("primary_layer"),
                "primary_subindustry": row.get("primary_subindustry"),
                "window_watchlist_status": row.get("window_watchlist_status"),
                "current_watchlist_status": row.get("current_watchlist_status"),
                "breakout_days": row.get("breakout_days"),
                "pullback_days": row.get("pullback_days"),
                "exit_risk_days": row.get("exit_risk_days"),
                "latest_ticker_trend_state": row.get("last_ticker_trend_state"),
                "latest_structure_label": row.get("last_latest_structure_label"),
                "latest_bos_event_type": row.get("last_latest_bos_event_type"),
                "latest_bos_freshness": row.get("last_latest_bos_freshness"),
                "latest_reset_reason": row.get("last_latest_reset_reason"),
                "latest_reset_freshness": row.get("last_latest_reset_freshness"),
                "latest_bullish_relevance_class": row.get("latest_bullish_relevance_class"),
                "latest_bullish_relevance_reason": row.get("latest_bullish_relevance_reason"),
                "latest_bearish_relevance_class": row.get("latest_bearish_relevance_class"),
                "latest_bearish_relevance_reason": row.get("latest_bearish_relevance_reason"),
                "primary_reason": buy_classification.primary_reason,
                "blocking_reason": buy_classification.blocking_reason,
            }
        )
        exit_classification = classify_rolling_30_exit_row(row)
        exit_rows.append(
            {
                "ticker": row.get("ticker"),
                "rolling_30_exit_state": exit_classification.rolling_30_exit_state,
                "primary_layer": row.get("primary_layer"),
                "primary_subindustry": row.get("primary_subindustry"),
                "window_watchlist_status": row.get("window_watchlist_status"),
                "current_watchlist_status": row.get("current_watchlist_status"),
                "exit_risk_days": row.get("exit_risk_days"),
                "latest_exit_risk_severity": row.get("last_exit_risk_severity"),
                "latest_exit_reason": row.get("last_exit_reason"),
                "latest_ticker_trend_state": row.get("last_ticker_trend_state"),
                "latest_bos_event_type": row.get("last_latest_bos_event_type"),
                "latest_bos_freshness": row.get("last_latest_bos_freshness"),
                "latest_reset_reason": row.get("last_latest_reset_reason"),
                "latest_reset_freshness": row.get("last_latest_reset_freshness"),
                "latest_bearish_relevance_class": row.get("latest_bearish_relevance_class"),
                "latest_bearish_relevance_reason": row.get("latest_bearish_relevance_reason"),
                "primary_reason": exit_classification.primary_reason,
                "risk_reason": exit_classification.risk_reason,
            }
        )

    buy_rows.sort(
        key=lambda row: (
            {
                "BUY_ZONE": 0,
                "WATCH_ZONE": 1,
                "AVOID": 2,
                "INSUFFICIENT_DATA": 3,
            }.get(str(row.get("rolling_30_buy_state")), 99),
            -int(row.get("breakout_days") or 0),
            -int(row.get("pullback_days") or 0),
            int(row.get("exit_risk_days") or 0),
            str(row.get("ticker") or ""),
        )
    )
    exit_rows.sort(
        key=lambda row: (
            {
                "EXTREME": 0,
                "EXIT_ZONE": 1,
                "WATCH": 2,
                "NORMAL": 3,
                "INSUFFICIENT_DATA": 4,
            }.get(str(row.get("rolling_30_exit_state")), 99),
            -int(row.get("exit_risk_days") or 0),
            EXIT_RISK_SEVERITY_PRIORITY.get(row.get("latest_exit_risk_severity"), 3),
            str(row.get("ticker") or ""),
        )
    )
    return buy_rows, exit_rows
