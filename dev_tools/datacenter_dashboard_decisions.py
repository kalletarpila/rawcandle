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
    source_files: list[str]
    decision_trace: list[DatacenterDecisionTrace] = field(default_factory=list)


@dataclass(frozen=True)
class DatacenterDecisionBatchResult:
    decisions: list[DatacenterTickerDecision]
    action_counts: dict[str, int]
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

_HARD_SELL_TERMS = (
    "close_below_ema20",
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

        hard_sell_match = any(
            _contains_any(text_values, _HARD_SELL_TERMS)
            for _row, _horizon, text_values in daily_or_rolling_2
        )
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
        confirmed_rolling_2d_bos_down = rolling_2d_bos_down and (
            any(
                _contains_any(text_values, ("double_bos_down", "high_exit_risk", "failed_pullback"))
                for _row, _horizon, text_values in rolling_2d_rows
            )
            or rolling_2d_reset
            or daily_bearish_confirmation
            or hard_sell_match
            or has_tighten_stop
        )

        if hard_sell_match:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Matched hard sell-language in daily or rolling 2d context")
            trace = _match_row_text_trace(
                ticker=ticker,
                action=action,
                matched_rule="SELL_HARD_TOKEN",
                rows_with_horizons=daily_or_rolling_2,
                terms=_HARD_SELL_TERMS,
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
                matched_rule="SELL_BOS_DOWN_CONFIRMED",
                rows_with_horizons=rolling_2d_rows,
                terms=("bos_down",),
            )
            if trace is not None:
                decision_trace.append(trace)
            if has_tighten_stop:
                confirm_trace = _match_first_row_with_value(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_BOS_DOWN_CONFIRMED",
                    rows_with_horizons=normalized_rows,
                    predicate=lambda value: value is not None and value >= 1,
                    field_name="high_exit_risk_days_count",
                    token="high_exit_risk_days_count>=1",
                )
            else:
                confirm_trace = _match_row_text_trace(
                    ticker=ticker,
                    action=action,
                    matched_rule="SELL_BOS_DOWN_CONFIRMED",
                    rows_with_horizons=normalized_rows,
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
        elif rolling_30_positive and rolling_5_constructive and daily_positive:
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
        elif rolling_30_positive:
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
                source_files=source_files,
                decision_trace=decision_trace,
            )
        )

    decisions.sort(key=lambda item: (_ACTION_PRIORITY[item.action], item.ticker))
    action_counts = Counter(decision.action for decision in decisions)
    for action_name in _ACTION_PRIORITY:
        action_counts.setdefault(action_name, 0)

    return DatacenterDecisionBatchResult(
        decisions=decisions,
        action_counts=dict(action_counts),
        warning_count=len(warnings),
        warnings=warnings,
    )
