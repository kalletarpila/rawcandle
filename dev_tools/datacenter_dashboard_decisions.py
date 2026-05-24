from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from dev_tools.datacenter_dashboard_parser import DatacenterDashboardRow


@dataclass(frozen=True)
class DatacenterDecisionTrace:
    ticker: str
    action: str
    matched_rule: str
    horizon: str | None
    field_name: str | None
    matched_token: str | None
    matched_value: str | None
    source_file: str | None
    section: str | None
    row_kind: str | None


@dataclass(frozen=True)
class DatacenterTickerDecision:
    ticker: str
    action: str
    severity: str
    primary_reason: str | None
    reasons: list[str]
    blocking_reasons: list[str]
    horizons_present: list[str]
    horizon_statuses: dict[str, str]
    distance_to_ema20: float | None
    high_exit_risk_days_count: int | None
    trend_state: str | None
    latest_structure_label: str | None
    latest_bos_event_type: str | None
    latest_reset_reason: str | None
    pullback_validity: str | None
    pullback_reason: str | None
    source_files: list[str]
    decision_trace: list[DatacenterDecisionTrace] = field(default_factory=list)


@dataclass(frozen=True)
class DatacenterDecisionBatchResult:
    decisions: list[DatacenterTickerDecision]
    action_counts: dict[str, int]
    pullback_counts: dict[str, int]
    pullback_action_counts: dict[str, dict[str, int]]
    warning_count: int
    warnings: list[str] = field(default_factory=list)


_ACTION_PRIORITY = {
    "SELL": 0,
    "REDUCE": 1,
    "TIGHTEN_STOP": 2,
    "BLOCKED": 3,
    "WAIT_PULLBACK": 4,
    "BUY_NOW": 5,
    "WATCH": 6,
    "NEUTRAL": 7,
}

_SEVERITY_BY_ACTION = {
    "SELL": "CRITICAL",
    "REDUCE": "HIGH",
    "TIGHTEN_STOP": "MEDIUM",
    "BUY_NOW": "HIGH",
    "WAIT_PULLBACK": "MEDIUM",
    "BLOCKED": "HIGH",
    "WATCH": "LOW",
    "NEUTRAL": "INFO",
}

_PULLBACK_VALIDITY_ORDER = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)

_HARD_SELL_TERMS = (
    "return_10d_lt_minus_8pct",
    "sell",
)
_ROLLING_2D_BOS_DOWN_TERMS = (
    "bos_down",
)
_ROLLING_2D_RESET_TERMS = (
    "reset",
)
_ROLLING_2D_CONFIRMATION_TERMS = (
    "reset",
    "double_bos_down",
    "high_exit_risk",
    "failed_pullback",
    "close_below_ema20",
    "return_10d_lt_minus_8pct",
    "sell",
)
_REDUCE_TERMS = (
    "reduce",
    "risk",
    "high_exit_risk",
    "exit_risk",
    "subindustry_context_risk",
)
_DAILY_BOS_DOWN_CONFIRMATION_TERMS = (
    "bos_down",
    "reset",
    "close_below_ema20",
    "sell",
)
_LONG_CONTEXT_CONFIRMATION_TERMS = (
    "reset",
    "double_bos_down",
    "high_exit_risk",
    "failed_pullback",
    "close_below_ema20",
    "return_10d_lt_minus_8pct",
    "sell",
    "bos_down",
)
_ROLLING_30_POSITIVE_TERMS = (
    "buy_zone",
    "leader",
    "positive_trend",
    "up",
    "hh",
    "hl",
    "bos_up",
)
_ROLLING_5_POSITIVE_TERMS = (
    "pullback",
    "breakout",
    "base_ready",
    "support",
    "reversal",
)
_DAILY_POSITIVE_TERMS = (
    "buy_now",
    "bullish",
    "dip",
    "reversal",
    "bos_up",
    "support",
)
_TRACE_TEXT_FIELDS = (
    "raw_action",
    "raw_status",
    "reason",
    "trend_state",
    "latest_structure_label",
    "latest_bos_event_type",
    "latest_reset_reason",
    "blocking_reasons",
)

_PULLBACK_CONTEXT_TERMS = (
    "pullback_candidate",
    "early_pullback",
    "failed_pullback",
)
_PULLBACK_HORIZON_PRIORITY = {
    "daily": 0,
    "rolling 2d": 1,
    "rolling 5d": 2,
    "rolling 30d": 3,
}


def _normalize_horizon(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"rolling 30d", "rolling30d", "rolling_30d"}:
        return "rolling 30d"
    if lowered in {"rolling 5d", "rolling5d", "rolling_5d"}:
        return "rolling 5d"
    if lowered in {"rolling 2d", "rolling2d", "rolling_2d"}:
        return "rolling 2d"
    if lowered == "daily":
        return "daily"
    return value.strip()


def _collect_text_values(row: DatacenterDashboardRow) -> list[str]:
    values = [
        row.raw_action,
        row.raw_status,
        row.reason,
        row.trend_state,
        row.latest_structure_label,
        row.latest_bos_event_type,
        row.latest_reset_reason,
        row.blocking_reasons,
    ]
    values.extend(row.raw_fields.values())
    return [value.lower() for value in values if value]


def _contains_any(text_values: list[str], terms: Iterable[str]) -> bool:
    return any(term.lower() in value for value in text_values for term in terms)


def _build_trace(
    *,
    ticker: str,
    action: str,
    matched_rule: str,
    row: DatacenterDashboardRow | None,
    horizon: str | None,
    field_name: str | None,
    matched_token: str | None,
    matched_value: str | None,
) -> DatacenterDecisionTrace:
    return DatacenterDecisionTrace(
        ticker=ticker,
        action=action,
        matched_rule=matched_rule,
        horizon=horizon,
        field_name=field_name,
        matched_token=matched_token,
        matched_value=matched_value,
        source_file=row.source_file if row is not None else None,
        section=row.section if row is not None else None,
        row_kind=row.row_kind if row is not None else None,
    )


def _match_row_text_trace(
    *,
    ticker: str,
    action: str,
    matched_rule: str,
    rows_with_horizons: list[tuple[DatacenterDashboardRow, str, list[str]]],
    terms: Iterable[str],
) -> DatacenterDecisionTrace | None:
    for term in terms:
        for row, horizon, _text_values in rows_with_horizons:
            for field_name in _TRACE_TEXT_FIELDS:
                value = getattr(row, field_name)
                if not value:
                    continue
                lowered_value = value.lower()
                if term.lower() in lowered_value:
                    return _build_trace(
                        ticker=ticker,
                        action=action,
                        matched_rule=matched_rule,
                        row=row,
                        horizon=horizon,
                        field_name=field_name,
                        matched_token=term,
                        matched_value=value,
                    )
            for raw_field_name in sorted(row.raw_fields):
                raw_value = row.raw_fields[raw_field_name]
                if not raw_value:
                    continue
                lowered_value = raw_value.lower()
                if term.lower() in lowered_value:
                    return _build_trace(
                        ticker=ticker,
                        action=action,
                        matched_rule=matched_rule,
                        row=row,
                        horizon=horizon,
                        field_name=f"raw_fields.{raw_field_name}",
                        matched_token=term,
                        matched_value=raw_value,
                    )
    return None


def _match_first_row_with_value(
    *,
    ticker: str,
    action: str,
    matched_rule: str,
    rows_with_horizons: list[tuple[DatacenterDashboardRow, str, list[str]]],
    predicate,
    field_name: str,
    token: str,
) -> DatacenterDecisionTrace | None:
    for row, horizon, _text_values in rows_with_horizons:
        value = getattr(row, field_name)
        if predicate(value):
            return _build_trace(
                ticker=ticker,
                action=action,
                matched_rule=matched_rule,
                row=row,
                horizon=horizon,
                field_name=field_name,
                matched_token=token,
                matched_value=str(value),
            )
    return None


def _match_row_field_equals(
    *,
    ticker: str,
    action: str,
    matched_rule: str,
    rows_with_horizons: list[tuple[DatacenterDashboardRow, str, list[str]]],
    field_name: str,
    expected_value: str,
    matched_token: str | None = None,
) -> DatacenterDecisionTrace | None:
    for row, horizon, _text_values in rows_with_horizons:
        value = getattr(row, field_name)
        if value == expected_value:
            return _build_trace(
                ticker=ticker,
                action=action,
                matched_rule=matched_rule,
                row=row,
                horizon=horizon,
                field_name=field_name,
                matched_token=matched_token or expected_value,
                matched_value=str(value),
            )
    return None


def _first_positive_trace(
    *,
    ticker: str,
    action: str,
    matched_rule: str,
    rows_with_horizons: list[tuple[DatacenterDashboardRow, str, list[str]]],
    horizon_name: str,
    terms: Iterable[str],
    label: str,
) -> DatacenterDecisionTrace | None:
    for row, horizon, text_values in rows_with_horizons:
        if horizon != horizon_name:
            continue
        for term in terms:
            if _contains_any(text_values, (term,)):
                for field_name in _TRACE_TEXT_FIELDS:
                    value = getattr(row, field_name)
                    if value and term.lower() in value.lower():
                        return _build_trace(
                            ticker=ticker,
                            action=action,
                            matched_rule=matched_rule,
                            row=row,
                            horizon=horizon,
                            field_name=field_name,
                            matched_token=term,
                            matched_value=value,
                        )
                for raw_field_name in sorted(row.raw_fields):
                    raw_value = row.raw_fields[raw_field_name]
                    if raw_value and term.lower() in raw_value.lower():
                        return _build_trace(
                            ticker=ticker,
                            action=action,
                            matched_rule=matched_rule,
                            row=row,
                            horizon=horizon,
                            field_name=f"raw_fields.{raw_field_name}",
                            matched_token=term,
                            matched_value=raw_value,
                        )
    for row, horizon, _text_values in rows_with_horizons:
        if horizon == horizon_name:
            return _build_trace(
                ticker=ticker,
                action=action,
                matched_rule=matched_rule,
                row=row,
                horizon=horizon,
                field_name=None,
                matched_token=label,
                matched_value=label,
            )
    return None


def _raw_field_int(raw_fields: dict[str, str], key: str) -> int | None:
    value = raw_fields.get(key)
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _raw_field_text(raw_fields: dict[str, str], key: str) -> str | None:
    value = raw_fields.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _is_fresh_marker(value: str | None) -> bool:
    return value is not None and value.strip().upper() == "FRESH"


def _row_has_pullback_context(row: DatacenterDashboardRow, text_values: list[str]) -> bool:
    if _contains_any(text_values, _PULLBACK_CONTEXT_TERMS):
        return True
    pullback_days = _raw_field_int(row.raw_fields, "pullback_days")
    return pullback_days is not None and pullback_days > 0


def _classify_pullback_validity(
    rows_with_horizons: list[tuple[DatacenterDashboardRow, str, list[str]]],
) -> tuple[str, str]:
    sorted_rows = sorted(
        rows_with_horizons,
        key=lambda item: (
            _PULLBACK_HORIZON_PRIORITY.get(item[1], 99),
            item[0].source_file,
            item[0].section or "",
            item[0].row_kind or "",
        ),
    )
    has_pullback_context = any(
        _row_has_pullback_context(row, text_values)
        for row, _horizon, text_values in sorted_rows
    )
    if not has_pullback_context:
        return ("NO_PULLBACK", "NO_PULLBACK_CONTEXT")

    has_structure_or_freshness_context = any(
        (
            bool(row.latest_bos_event_type)
            or bool(row.latest_reset_reason)
            or bool(row.freshness_status)
            or row.structure_warning_overrides_bullish_signal is not None
            or bool(row.ma_break_status)
            or _raw_field_text(row.raw_fields, "latest_bos_freshness") is not None
            or _raw_field_text(row.raw_fields, "latest_reset_freshness") is not None
        )
        for row, _horizon, _text_values in sorted_rows
    )
    if not has_structure_or_freshness_context:
        return ("INSUFFICIENT_DATA", "MISSING_STRUCTURE_OR_FRESHNESS_CONTEXT")

    acute_rows = [
        (row, horizon, text_values)
        for row, horizon, text_values in sorted_rows
        if horizon in {"daily", "rolling 2d"}
    ]

    for row, _horizon, _text_values in acute_rows:
        if row.freshness_status == "STRUCTURE_WARNING_OVERRIDES_BULLISH":
            return (
                "STRUCTURE_BLOCKED_PULLBACK",
                "STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL",
            )
        if row.structure_warning_overrides_bullish_signal == 1:
            return (
                "STRUCTURE_BLOCKED_PULLBACK",
                "STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL",
            )
        if row.latest_bos_event_type == "BOS_DOWN" and _is_fresh_marker(
            _raw_field_text(row.raw_fields, "latest_bos_freshness")
        ):
            return (
                "STRUCTURE_BLOCKED_PULLBACK",
                "FRESH_BOS_DOWN_BLOCKS_PULLBACK",
            )
        if (
            row.latest_reset_reason
            and "DOUBLE_BOS_DOWN" in row.latest_reset_reason
            and _is_fresh_marker(_raw_field_text(row.raw_fields, "latest_reset_freshness"))
        ):
            return (
                "STRUCTURE_BLOCKED_PULLBACK",
                "FRESH_DOUBLE_BOS_DOWN_BLOCKS_PULLBACK",
            )
        if (
            row.latest_reset_reason
            and "RESET" in row.latest_reset_reason
            and _is_fresh_marker(_raw_field_text(row.raw_fields, "latest_reset_freshness"))
        ):
            return (
                "STRUCTURE_BLOCKED_PULLBACK",
                "FRESH_RESET_BLOCKS_PULLBACK",
            )

    if _has_acute_confirmed_rolling_2d_bos_down(sorted_rows):
        return (
            "STRUCTURE_BLOCKED_PULLBACK",
            "ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK",
        )

    for row, _horizon, _text_values in acute_rows:
        if row.ma_break_status == "SMA50_CONFIRMED_BREAK":
            return ("BREAKDOWN_NOT_PULLBACK", "SMA50_CONFIRMED_BREAK")
        if row.ma_break_status == "EMA20_CONFIRMED_BREAK":
            return ("BREAKDOWN_NOT_PULLBACK", "EMA20_CONFIRMED_BREAK")

    has_fresh_bullish_signal = any(
        row.freshness_status == "FRESH_BULLISH_SIGNAL"
        for row, _horizon, _text_values in sorted_rows
    )
    has_structure_override = any(
        row.freshness_status == "STRUCTURE_WARNING_OVERRIDES_BULLISH"
        or row.structure_warning_overrides_bullish_signal == 1
        for row, _horizon, _text_values in sorted_rows
    )
    has_confirmed_ma_break = any(
        row.ma_break_status in {"SMA50_CONFIRMED_BREAK", "EMA20_CONFIRMED_BREAK"}
        for row, _horizon, _text_values in acute_rows
    )
    has_acceptable_ma_status = any(
        row.ma_break_status in {"OK", "EMA20_WARNING"}
        for row, _horizon, _text_values in acute_rows
    ) or not any(row.ma_break_status for row, _horizon, _text_values in acute_rows)

    if (
        has_acceptable_ma_status
        and not has_structure_override
        and has_fresh_bullish_signal
    ):
        return (
            "VALID_PULLBACK",
            "FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
        )

    if not has_confirmed_ma_break:
        return ("EARLY_PULLBACK", "WAIT_FOR_BULLISH_CONFIRMATION")

    return ("INSUFFICIENT_DATA", "MISSING_STRUCTURE_OR_FRESHNESS_CONTEXT")


def _has_acute_confirmed_rolling_2d_bos_down(
    normalized_rows: list[tuple[DatacenterDashboardRow, str, list[str]]],
) -> bool:
    daily_or_rolling_2 = [
        (row, horizon, text_values)
        for row, horizon, text_values in normalized_rows
        if horizon in {"daily", "rolling 2d"}
    ]
    rolling_2d_rows = [
        (row, horizon, text_values)
        for row, horizon, text_values in normalized_rows
        if horizon == "rolling 2d"
    ]
    daily_rows = [
        (row, horizon, text_values)
        for row, horizon, text_values in normalized_rows
        if horizon == "daily"
    ]
    rolling_2d_bos_down = any(
        _contains_any(text_values, _ROLLING_2D_BOS_DOWN_TERMS)
        for _row, _horizon, text_values in rolling_2d_rows
    )
    if not rolling_2d_bos_down:
        return False
    rolling_2d_reset = any(
        _contains_any(text_values, _ROLLING_2D_RESET_TERMS)
        for _row, _horizon, text_values in rolling_2d_rows
    )
    acute_high_exit_risk_days_present = any(
        row.high_exit_risk_days_count is not None
        and row.high_exit_risk_days_count >= 1
        for row, _horizon, _text_values in daily_or_rolling_2
    )
    acute_ma_status_available = any(
        row.ma_break_status is not None and row.ma_break_status.strip() != ""
        for row, _horizon, _text_values in daily_or_rolling_2
    )
    explicit_sell_match = any(
        _contains_any(text_values, ("sell",))
        for _row, _horizon, text_values in daily_or_rolling_2
    )
    return_10d_hard_sell_match = any(
        _contains_any(text_values, ("return_10d_lt_minus_8pct",))
        for _row, _horizon, text_values in daily_or_rolling_2
    )
    close_below_ema20_fallback_match = (
        not acute_ma_status_available
        and any(
            _contains_any(text_values, ("close_below_ema20",))
            for _row, _horizon, text_values in daily_or_rolling_2
        )
    )
    hard_sell_match = (
        explicit_sell_match
        or return_10d_hard_sell_match
        or close_below_ema20_fallback_match
    )
    daily_bearish_confirmation = any(
        _contains_any(text_values, _DAILY_BOS_DOWN_CONFIRMATION_TERMS)
        for _row, _horizon, text_values in daily_rows
    )
    acute_rolling_2d_confirmation = any(
        _contains_any(text_values, _ROLLING_2D_CONFIRMATION_TERMS)
        for _row, _horizon, text_values in rolling_2d_rows
    )
    return (
        acute_rolling_2d_confirmation
        or rolling_2d_reset
        or daily_bearish_confirmation
        or hard_sell_match
        or acute_high_exit_risk_days_present
    )


def _max_optional_float(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _max_optional_int(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def build_datacenter_ticker_decisions(
    rows: Iterable[DatacenterDashboardRow],
) -> DatacenterDecisionBatchResult:
    grouped_rows: dict[str, list[DatacenterDashboardRow]] = defaultdict(list)
    for row in rows:
        grouped_rows[row.ticker].append(row)

    decisions: list[DatacenterTickerDecision] = []
    warnings: list[str] = []

    for ticker, ticker_rows in grouped_rows.items():
        normalized_rows = [
            (row, _normalize_horizon(row.horizon), _collect_text_values(row))
            for row in ticker_rows
        ]
        horizon_statuses = {
            horizon: (row.raw_status or row.raw_action or "")
            for row, horizon, _text_values in normalized_rows
        }
        horizons_present = sorted(horizon_statuses)
        source_files = sorted({row.source_file for row in ticker_rows})
        blocking_reasons = sorted(
            {
                row.blocking_reasons.strip()
                for row in ticker_rows
                if row.blocking_reasons and row.blocking_reasons.strip()
            }
        )
        distance_to_ema20 = _max_optional_float(
            row.distance_to_ema20 for row in ticker_rows
        )
        high_exit_risk_days_count = _max_optional_int(
            row.high_exit_risk_days_count for row in ticker_rows
        )
        trend_state = next(
            (row.trend_state for row in ticker_rows if row.trend_state),
            None,
        )
        latest_structure_label = next(
            (row.latest_structure_label for row in ticker_rows if row.latest_structure_label),
            None,
        )
        latest_bos_event_type = next(
            (row.latest_bos_event_type for row in ticker_rows if row.latest_bos_event_type),
            None,
        )
        latest_reset_reason = next(
            (row.latest_reset_reason for row in ticker_rows if row.latest_reset_reason),
            None,
        )

        reasons: list[str] = []
        decision_trace: list[DatacenterDecisionTrace] = []
        action = "NEUTRAL"
        primary_reason: Optional[str] = None

        daily_or_rolling_2 = [
            (row, horizon, text_values)
            for row, horizon, text_values in normalized_rows
            if horizon in {"daily", "rolling 2d"}
        ]
        rolling_2d_rows = [
            (row, horizon, text_values)
            for row, horizon, text_values in normalized_rows
            if horizon == "rolling 2d"
        ]
        daily_rows = [
            (row, horizon, text_values)
            for row, horizon, text_values in normalized_rows
            if horizon == "daily"
        ]
        long_context_rows = [
            (row, horizon, text_values)
            for row, horizon, text_values in normalized_rows
            if horizon in {"rolling 30d", "rolling 5d"}
        ]

        rolling_2d_bos_down = any(
            _contains_any(text_values, _ROLLING_2D_BOS_DOWN_TERMS)
            for _row, _horizon, text_values in rolling_2d_rows
        )
        rolling_2d_reset = any(
            _contains_any(text_values, _ROLLING_2D_RESET_TERMS)
            for _row, _horizon, text_values in rolling_2d_rows
        )
        direct_reduce_match = any(
            _contains_any(text_values, _REDUCE_TERMS)
            for _row, _horizon, text_values in daily_or_rolling_2
        )
        has_blocking = bool(blocking_reasons)
        has_tighten_stop = (
            high_exit_risk_days_count is not None and high_exit_risk_days_count >= 1
        )
        acute_high_exit_risk_days_present = any(
            row.high_exit_risk_days_count is not None
            and row.high_exit_risk_days_count >= 1
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        acute_ma_status_available = any(
            row.ma_break_status is not None and row.ma_break_status.strip() != ""
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        acute_sma50_confirmed_break = any(
            row.ma_break_status == "SMA50_CONFIRMED_BREAK"
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        acute_ema20_confirmed_break = any(
            row.ma_break_status == "EMA20_CONFIRMED_BREAK"
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        acute_sma50_warning = any(
            row.ma_break_status == "SMA50_WARNING"
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        acute_ema20_warning = any(
            row.ma_break_status == "EMA20_WARNING"
            for row, _horizon, _text_values in daily_or_rolling_2
        )
        explicit_sell_match = any(
            _contains_any(text_values, ("sell",))
            for _row, _horizon, text_values in daily_or_rolling_2
        )
        return_10d_hard_sell_match = any(
            _contains_any(text_values, ("return_10d_lt_minus_8pct",))
            for _row, _horizon, text_values in daily_or_rolling_2
        )
        close_below_ema20_fallback_match = (
            not acute_ma_status_available
            and any(
                _contains_any(text_values, ("close_below_ema20",))
                for _row, _horizon, text_values in daily_or_rolling_2
            )
        )
        hard_sell_match = (
            explicit_sell_match
            or return_10d_hard_sell_match
            or close_below_ema20_fallback_match
        )
        freshness_structure_override = any(
            row.freshness_status == "STRUCTURE_WARNING_OVERRIDES_BULLISH"
            or row.structure_warning_overrides_bullish_signal == 1
            for row in ticker_rows
        )

        rolling_30_positive = any(
            horizon == "rolling 30d"
            and _contains_any(text_values, _ROLLING_30_POSITIVE_TERMS)
            for _row, horizon, text_values in normalized_rows
        )
        rolling_5_constructive = any(
            horizon == "rolling 5d"
            and _contains_any(text_values, _ROLLING_5_POSITIVE_TERMS)
            for _row, horizon, text_values in normalized_rows
        )
        daily_positive = any(
            horizon == "daily"
            and _contains_any(text_values, _DAILY_POSITIVE_TERMS)
            for _row, horizon, text_values in normalized_rows
        )
        daily_bearish_confirmation = any(
            _contains_any(text_values, _DAILY_BOS_DOWN_CONFIRMATION_TERMS)
            for _row, _horizon, text_values in daily_rows
        )
        acute_rolling_2d_confirmation = any(
            _contains_any(text_values, _ROLLING_2D_CONFIRMATION_TERMS)
            for _row, _horizon, text_values in rolling_2d_rows
        )
        long_context_confirmation = any(
            _contains_any(text_values, _LONG_CONTEXT_CONFIRMATION_TERMS)
            for _row, _horizon, text_values in long_context_rows
        ) or any(
            row.high_exit_risk_days_count is not None
            and row.high_exit_risk_days_count >= 1
            for row, _horizon, _text_values in long_context_rows
        )
        confirmed_rolling_2d_bos_down = _has_acute_confirmed_rolling_2d_bos_down(
            normalized_rows
        )
        pullback_validity, pullback_reason = _classify_pullback_validity(normalized_rows)

        if acute_sma50_confirmed_break:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Confirmed SMA50 break in daily or rolling 2d context")
            trace = _match_row_field_equals(
                ticker=ticker,
                action=action,
                matched_rule="SELL_SMA50_CONFIRMED_BREAK",
                rows_with_horizons=daily_or_rolling_2,
                field_name="ma_break_status",
                expected_value="SMA50_CONFIRMED_BREAK",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif acute_ema20_confirmed_break:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Confirmed EMA20 break in daily or rolling 2d context")
            trace = _match_row_field_equals(
                ticker=ticker,
                action=action,
                matched_rule="SELL_EMA20_CONFIRMED_BREAK",
                rows_with_horizons=daily_or_rolling_2,
                field_name="ma_break_status",
                expected_value="EMA20_CONFIRMED_BREAK",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif hard_sell_match:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Matched hard sell-language in daily or rolling 2d context")
            trace = None
            if explicit_sell_match:
                trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_HARD_TOKEN",
                    rows_with_horizons=daily_or_rolling_2,
                    terms=("sell",),
                )
            if trace is None and return_10d_hard_sell_match:
                trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_HARD_TOKEN",
                    rows_with_horizons=daily_or_rolling_2,
                    terms=("return_10d_lt_minus_8pct",),
                )
            if trace is None and close_below_ema20_fallback_match:
                trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_HARD_TOKEN",
                    rows_with_horizons=daily_or_rolling_2,
                    terms=("close_below_ema20",),
                )
            if trace is not None:
                decision_trace.append(trace)
        elif confirmed_rolling_2d_bos_down:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Confirmed rolling 2d BOS_DOWN with additional hard confirmation")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="SELL_BOS_DOWN_CONFIRMED_ACUTE",
                rows_with_horizons=rolling_2d_rows,
                terms=("bos_down",),
            )
            if trace is not None:
                decision_trace.append(trace)
            if acute_high_exit_risk_days_present:
                confirm_trace = _match_first_row_with_value(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_BOS_DOWN_CONFIRMED_ACUTE",
                    rows_with_horizons=daily_or_rolling_2,
                    predicate=lambda value: value is not None and value >= 1,
                    field_name="high_exit_risk_days_count",
                    token="high_exit_risk_days_count>=1",
                )
            else:
                confirm_trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_BOS_DOWN_CONFIRMED_ACUTE",
                    rows_with_horizons=daily_or_rolling_2,
                    terms=(
                        "double_bos_down",
                        "high_exit_risk",
                        "failed_pullback",
                        "reset",
                        "close_below_ema20",
                        "return_10d_lt_minus_8pct",
                        "sell",
                    ),
                )
            if confirm_trace is not None:
                decision_trace.append(confirm_trace)
        elif rolling_2d_bos_down and long_context_confirmation:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("Rolling 2d BOS_DOWN has only longer-horizon context and is downgraded to REDUCE")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_BOS_DOWN_LONG_CONTEXT_ONLY",
                rows_with_horizons=rolling_2d_rows,
                terms=("bos_down",),
            )
            if trace is not None:
                decision_trace.append(trace)
            context_trace = _match_first_row_with_value(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_BOS_DOWN_LONG_CONTEXT_ONLY",
                rows_with_horizons=long_context_rows,
                predicate=lambda value: value is not None and value >= 1,
                field_name="high_exit_risk_days_count",
                token="high_exit_risk_days_count>=1",
            )
            if context_trace is None:
                context_trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="REDUCE_BOS_DOWN_LONG_CONTEXT_ONLY",
                    rows_with_horizons=long_context_rows,
                    terms=_LONG_CONTEXT_CONFIRMATION_TERMS,
                )
            if context_trace is not None:
                decision_trace.append(context_trace)
        elif acute_sma50_warning:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("SMA50 warning in daily or rolling 2d context")
            trace = _match_row_field_equals(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_SMA50_WARNING",
                rows_with_horizons=daily_or_rolling_2,
                field_name="ma_break_status",
                expected_value="SMA50_WARNING",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif acute_ema20_warning:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("EMA20 warning in daily or rolling 2d context")
            trace = _match_row_field_equals(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_EMA20_WARNING",
                rows_with_horizons=daily_or_rolling_2,
                field_name="ma_break_status",
                expected_value="EMA20_WARNING",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif direct_reduce_match:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("Matched risk-language in daily or rolling 2d context")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_RISK_TOKEN",
                rows_with_horizons=daily_or_rolling_2,
                terms=_REDUCE_TERMS,
            )
            if trace is not None:
                decision_trace.append(trace)
        elif rolling_2d_bos_down:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("Unconfirmed rolling 2d BOS_DOWN downgraded to REDUCE")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_BOS_DOWN_UNCONFIRMED",
                rows_with_horizons=rolling_2d_rows,
                terms=("bos_down",),
            )
            if trace is not None:
                decision_trace.append(trace)
        elif rolling_2d_reset:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("Unconfirmed rolling 2d RESET downgraded to REDUCE")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_RESET_UNCONFIRMED",
                rows_with_horizons=rolling_2d_rows,
                terms=("reset",),
            )
            if trace is not None:
                decision_trace.append(trace)
        elif has_tighten_stop:
            action = "TIGHTEN_STOP"
            primary_reason = "HIGH_EXIT_RISK_DAYS_PRESENT"
            reasons.append(
                f"high_exit_risk_days_count={high_exit_risk_days_count}"
            )
            trace = _match_first_row_with_value(
                ticker=ticker,
                action=action,
                matched_rule="TIGHTEN_STOP",
                rows_with_horizons=normalized_rows,
                predicate=lambda value: value is not None and value >= 1,
                field_name="high_exit_risk_days_count",
                token="high_exit_risk_days_count>=1",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif has_blocking:
            action = "BLOCKED"
            primary_reason = "BLOCKING_REASONS_PRESENT"
            reasons.extend(blocking_reasons)
            trace = _match_first_row_with_value(
                ticker=ticker,
                action=action,
                matched_rule="BLOCKED",
                rows_with_horizons=normalized_rows,
                predicate=lambda value: bool(value and str(value).strip()),
                field_name="blocking_reasons",
                token="blocking_reasons",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif (
            rolling_30_positive
            and distance_to_ema20 is not None
            and distance_to_ema20 > 15.0
        ):
            action = "WAIT_PULLBACK"
            primary_reason = "STRETCHED_ABOVE_EMA20"
            reasons.append(f"distance_to_ema20={distance_to_ema20}")
            trace = _match_first_row_with_value(
                ticker=ticker,
                action=action,
                matched_rule="WAIT_PULLBACK",
                rows_with_horizons=normalized_rows,
                predicate=lambda value: value is not None and value > 15.0,
                field_name="distance_to_ema20",
                token="distance_to_ema20>15.0",
            )
            if trace is not None:
                decision_trace.append(trace)
        elif (
            not freshness_structure_override
            and rolling_30_positive
            and rolling_5_constructive
            and daily_positive
        ):
            action = "BUY_NOW"
            primary_reason = "MULTI_HORIZON_ALIGNMENT"
            reasons.append("rolling 30d + rolling 5d + daily constructive alignment")
            for horizon_name, terms, label in (
                ("rolling 30d", _ROLLING_30_POSITIVE_TERMS, "rolling 30d positive context"),
                ("rolling 5d", _ROLLING_5_POSITIVE_TERMS, "rolling 5d constructive context"),
                ("daily", _DAILY_POSITIVE_TERMS, "daily positive trigger"),
            ):
                trace = _first_positive_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="BUY_NOW",
                    rows_with_horizons=normalized_rows,
                    horizon_name=horizon_name,
                    terms=terms,
                    label=label,
                )
                if trace is not None:
                    decision_trace.append(trace)
        elif not freshness_structure_override and rolling_30_positive:
            action = "WATCH"
            primary_reason = "ROLLING_30_POSITIVE_ONLY"
            reasons.append("Positive rolling 30d context without full alignment")
            trace = _first_positive_trace(
                ticker=ticker,
                action=action,
                matched_rule="WATCH",
                rows_with_horizons=normalized_rows,
                horizon_name="rolling 30d",
                terms=_ROLLING_30_POSITIVE_TERMS,
                label="rolling 30d positive context",
            )
            if trace is not None:
                decision_trace.append(trace)
        else:
            action = "NEUTRAL"
            primary_reason = "NO_DECISIVE_SIGNAL"
            decision_trace.append(
                _build_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="NEUTRAL_FALLBACK",
                    row=None,
                    horizon=None,
                    field_name=None,
                    matched_token=None,
                    matched_value=None,
                )
            )

        if action == "BLOCKED" and direct_reduce_match:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons = ["Matched risk-language in daily or rolling 2d context"]
            decision_trace = []
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="REDUCE_RISK_TOKEN",
                rows_with_horizons=daily_or_rolling_2,
                terms=_REDUCE_TERMS,
            )
            if trace is not None:
                decision_trace.append(trace)

        if not horizons_present:
            warnings.append(f"{ticker}: no normalized horizons present")

        decisions.append(
            DatacenterTickerDecision(
                ticker=ticker,
                action=action,
                severity=_SEVERITY_BY_ACTION[action],
                primary_reason=primary_reason,
                reasons=reasons,
                blocking_reasons=blocking_reasons,
                horizons_present=horizons_present,
                horizon_statuses=horizon_statuses,
                distance_to_ema20=distance_to_ema20,
                high_exit_risk_days_count=high_exit_risk_days_count,
                trend_state=trend_state,
                latest_structure_label=latest_structure_label,
                latest_bos_event_type=latest_bos_event_type,
                latest_reset_reason=latest_reset_reason,
                pullback_validity=pullback_validity,
                pullback_reason=pullback_reason,
                source_files=source_files,
                decision_trace=decision_trace,
            )
        )

    decisions.sort(key=lambda item: (_ACTION_PRIORITY[item.action], item.ticker))
    action_counts = Counter(decision.action for decision in decisions)
    for action_name in _ACTION_PRIORITY:
        action_counts.setdefault(action_name, 0)
    pullback_counts = Counter(
        decision.pullback_validity or "INSUFFICIENT_DATA" for decision in decisions
    )
    for pullback_name in _PULLBACK_VALIDITY_ORDER:
        pullback_counts.setdefault(pullback_name, 0)
    pullback_action_counts: dict[str, dict[str, int]] = {}
    for pullback_name in _PULLBACK_VALIDITY_ORDER:
        pullback_action_counts[pullback_name] = {
            action_name: 0 for action_name in _ACTION_PRIORITY
        }
    for decision in decisions:
        pullback_name = decision.pullback_validity or "INSUFFICIENT_DATA"
        pullback_action_counts[pullback_name][decision.action] += 1

    return DatacenterDecisionBatchResult(
        decisions=decisions,
        action_counts=dict(action_counts),
        pullback_counts=dict(pullback_counts),
        pullback_action_counts=pullback_action_counts,
        warning_count=len(warnings),
        warnings=warnings,
    )
