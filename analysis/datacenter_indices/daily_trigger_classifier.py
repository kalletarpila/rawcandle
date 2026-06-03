from __future__ import annotations


WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}
CLASSIFIER_MISSING_PRICE_STATUSES = {"MISSING_PRICE", "MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}
FRESH_SIGNAL_STATES = {"FRESH", "RECENT", "CURRENT"}
SEVERE_EXIT_SEVERITIES = {"CRITICAL", "EXTREME"}
HIGH_EXIT_SEVERITIES = {"HIGH", "CRITICAL", "EXTREME"}
GROUP_RISK_TIMING_STATES = {"EXIT_ZONE", "TRIM_WATCH"}
GROUP_RISK_OVERHEAT_LEVELS = {"HIGH", "EXTREME"}


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float_value(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_fresh_or_recent(value: object | None) -> bool:
    return _normalize_text(value).upper() in FRESH_SIGNAL_STATES


def _has_reason_token(value: object | None, token: str) -> bool:
    return token.lower() in _normalize_text(value).lower()


def _is_severe_exit_severity(value: object | None) -> bool:
    return _normalize_text(value).upper() in SEVERE_EXIT_SEVERITIES


def _is_high_or_worse_exit_severity(value: object | None) -> bool:
    return _normalize_text(value).upper() in HIGH_EXIT_SEVERITIES


def _has_negative_ema20_context(value: object | None) -> bool:
    distance = _float_value(value)
    return distance is not None and distance < 0


def _has_slightly_negative_ema20_context(value: object | None) -> bool:
    distance = _float_value(value)
    return distance is not None and -0.03 <= distance < 0


def _is_near_pullback_zone(row: dict[str, object]) -> bool:
    for field_name in ("distance_to_ema10_pct", "distance_to_ema20_pct"):
        distance = _float_value(row.get(field_name))
        if distance is not None and abs(distance) <= 0.03:
            return True
    return False


def _is_group_risk_state(
    *,
    subindustry_timing_state: object | None,
    subindustry_overheat_risk_level: object | None,
    layer_timing_state: object | None,
    layer_overheat_risk_level: object | None,
) -> bool:
    return (
        subindustry_timing_state in GROUP_RISK_TIMING_STATES
        or layer_timing_state in GROUP_RISK_TIMING_STATES
        or subindustry_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
        or layer_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
    )


def classify_daily_watchlist_status(row: dict[str, object]) -> str:
    if int(row.get("in_datacenter_ecosystem") or 0) != 1:
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get("close") is None:
        return "MISSING_PRICE"
    if row.get("exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if int(row.get("breakout_signal") or 0) == 1:
        return "BREAKOUT_CANDIDATE"
    if int(row.get("pullback_signal") or 0) == 1:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("subindustry_overheat_risk_level"),
        layer_timing_state=row.get("layer_timing_state"),
        layer_overheat_risk_level=row.get("layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def classify_daily_trigger_row(row: dict[str, object]) -> tuple[str, str, str | None, str | None]:
    ticker = _normalize_text(row.get("ticker"))
    if not ticker:
        return ("INSUFFICIENT_DATA", "MISSING_TICKER_CONTEXT", None, "WAIT_FOR_DATA")

    current_watchlist_status = _normalize_text(row.get("current_watchlist_status")).upper()
    if _normalize_text(row.get("price_data_status")).upper() in CLASSIFIER_MISSING_PRICE_STATUSES or row.get(
        "close"
    ) is None:
        return ("INSUFFICIENT_DATA", "MISSING_PRICE_CONTEXT", None, "WAIT_FOR_DATA")

    trend_state = _normalize_text(row.get("trend_state")).upper()
    exit_risk_severity = _normalize_text(row.get("exit_risk_severity")).upper()
    latest_structure_label = _normalize_text(row.get("latest_structure_label")).upper()
    latest_exit_reason = row.get("latest_exit_reason")

    fresh_bos_down = (
        _normalize_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN"
        and _is_fresh_or_recent(row.get("latest_bos_freshness"))
    )
    stale_bos_down = (
        _normalize_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN"
        and not _is_fresh_or_recent(row.get("latest_bos_freshness"))
    )
    fresh_reset = bool(_normalize_text(row.get("latest_reset_reason"))) and _is_fresh_or_recent(
        row.get("latest_reset_freshness")
    )

    has_pullback_signal = int(row.get("pullback_signal") or 0) == 1
    has_breakout_signal = int(row.get("breakout_signal") or 0) == 1
    has_exit_risk_signal = int(row.get("exit_risk_signal") or 0) == 1
    latest_bullish_relevance_class = _normalize_text(row.get("latest_bullish_relevance_class")).upper()
    latest_bearish_relevance_class = _normalize_text(row.get("latest_bearish_relevance_class")).upper()
    has_bullish_signal = any(
        int(row.get(field_name) or 0) == 1
        for field_name in (
            "bullish_candle_signal",
            "bullish_divergence_signal",
            "hidden_bullish_divergence_signal",
        )
    )
    has_bearish_signal = any(
        int(row.get(field_name) or 0) == 1
        for field_name in (
            "bearish_candle_signal",
            "bearish_divergence_signal",
            "hidden_bearish_divergence_signal",
        )
    )
    relevant_bullish = latest_bullish_relevance_class == "RELEVANT"
    weak_bullish = latest_bullish_relevance_class == "WEAK_CONTEXT"
    relevant_bearish = latest_bearish_relevance_class == "RELEVANT"
    weak_bearish = latest_bearish_relevance_class == "WEAK_CONTEXT"

    high_exit_risk = current_watchlist_status == "HIGH_EXIT_RISK" or _is_high_or_worse_exit_severity(
        exit_risk_severity
    )
    bullish_evidence = has_pullback_signal or has_bullish_signal or _is_near_pullback_zone(row)
    has_ll_structure = latest_structure_label == "LL"
    has_close_below_ema20 = _has_reason_token(latest_exit_reason, "close_below_ema20")
    has_return_10d_lt_minus_8pct = _has_reason_token(latest_exit_reason, "return_10d_lt_minus_8pct")
    has_trim_watch_close_below_ma10 = _has_reason_token(latest_exit_reason, "trim_watch_close_below_ma10")
    has_structure_label_ll_reason = _has_reason_token(latest_exit_reason, "latest_structure_label_ll")
    has_price_break_evidence = (
        has_close_below_ema20
        or has_return_10d_lt_minus_8pct
        or has_trim_watch_close_below_ma10
        or _has_negative_ema20_context(row.get("distance_to_ema20_pct"))
    )
    has_structural_break_evidence = (
        has_ll_structure
        or trend_state == "DOWN"
        or fresh_bos_down
        or fresh_reset
        or has_structure_label_ll_reason
    )
    buy_hard_blocker = (
        trend_state == "DOWN"
        or fresh_bos_down
        or fresh_reset
        or high_exit_risk
        or relevant_bearish
    )

    stop_reason = None
    if _is_severe_exit_severity(exit_risk_severity) and has_exit_risk_signal:
        stop_reason = "CRITICAL_OR_EXTREME_EXIT_SEVERITY"
    elif exit_risk_severity == "HIGH" and has_price_break_evidence and has_structural_break_evidence:
        stop_reason = "PRICE_BREAK_WITH_STRUCTURAL_BREAKDOWN"
    elif fresh_bos_down and fresh_reset and has_price_break_evidence:
        stop_reason = "FRESH_BOS_DOWN_AND_RESET_WITH_PRICE_BREAK"
    elif relevant_bearish and high_exit_risk and has_price_break_evidence:
        stop_reason = "RELEVANT_BEARISH_CONTEXT_WITH_HIGH_EXIT_RISK_AND_PRICE_BREAK"
    if stop_reason:
        return ("STOP_TRIGGER", "CONFIRMED_DAILY_STOP_TRIGGER", stop_reason, "CHECK_STOP_OR_EXIT")

    sell_reason = None
    if has_exit_risk_signal and exit_risk_severity in {"MEDIUM", "HIGH"}:
        sell_reason = (
            "HIGH_EXIT_RISK_WITHOUT_FULL_STOP_CONFIRMATION"
            if exit_risk_severity == "HIGH"
            else "EXIT_RISK_SIGNAL_MEDIUM_OR_HIGH"
        )
    elif has_close_below_ema20:
        sell_reason = "CLOSE_BELOW_EMA20"
    elif has_return_10d_lt_minus_8pct:
        sell_reason = "RETURN_10D_LT_MINUS_8PCT"
    elif has_trim_watch_close_below_ma10:
        sell_reason = "TRIM_WATCH_CLOSE_BELOW_MA10"
    elif _has_reason_token(latest_exit_reason, "subindustry_exit_zone"):
        sell_reason = "SUBINDUSTRY_EXIT_ZONE"
    elif has_structure_label_ll_reason or has_ll_structure or fresh_reset:
        sell_reason = "STRUCTURAL_WARNING_WITHOUT_PRICE_BREAK"
    elif fresh_bos_down:
        sell_reason = "FRESH_BOS_DOWN"
    elif relevant_bearish:
        sell_reason = "RELEVANT_BEARISH_CONTEXT"
    elif has_bearish_signal and trend_state != "UP":
        sell_reason = "BEARISH_DAILY_SIGNAL"
    elif trend_state == "DOWN" and _has_negative_ema20_context(row.get("distance_to_ema20_pct")):
        sell_reason = "DOWN_TREND_BELOW_EMA20"
    if sell_reason:
        return ("SELL_TRIGGER", "DAILY_SELL_TRIGGER", sell_reason, "REVIEW_SELL_OR_TIGHTEN_STOP")

    exit_watch_reason = None
    if has_exit_risk_signal:
        exit_watch_reason = "MILD_EXIT_RISK_SIGNAL"
    elif weak_bearish:
        exit_watch_reason = "WEAK_BEARISH_CONTEXT"
    elif stale_bos_down and not (relevant_bullish and bullish_evidence and trend_state != "DOWN"):
        exit_watch_reason = "STALE_BOS_DOWN"
    elif _has_slightly_negative_ema20_context(row.get("distance_to_ema20_pct")):
        exit_watch_reason = "SLIGHTLY_BELOW_EMA20"
    elif current_watchlist_status in {"MEDIUM_EXIT_RISK", "GROUP_RISK"}:
        exit_watch_reason = current_watchlist_status
    if exit_watch_reason:
        return ("EXIT_WATCH", "DAILY_EXIT_WATCH", "MILD_OR_UNCONFIRMED_EXIT_PRESSURE", "MONITOR_NEXT_SESSION")

    if relevant_bullish and bullish_evidence and not buy_hard_blocker and trend_state != "DOWN":
        primary_reason = (
            "PULLBACK_TRIGGER_WITH_RELEVANT_BULLISH_CONTEXT"
            if has_pullback_signal or _is_near_pullback_zone(row)
            else "BULLISH_DAILY_TRIGGER_WITH_CONTEXT"
        )
        return ("BUY_TRIGGER", primary_reason, None, "REVIEW_WITH_ROLLING_CONTEXT")

    if (
        has_pullback_signal
        or has_breakout_signal
        or has_bullish_signal
        or weak_bullish
        or _is_near_pullback_zone(row)
    ) and not buy_hard_blocker:
        return ("BUY_WATCH", "BULLISH_SETUP_NEEDS_CONFIRMATION", None, "MONITOR_FOR_DAILY_CONFIRMATION")

    return ("NO_TRIGGER", "NO_MEANINGFUL_DAILY_TRIGGER", None, "NONE")
