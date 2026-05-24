from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from dev_tools.datacenter_dashboard_parser import DatacenterDashboardRow


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
    "BUY_NOW": 3,
    "WAIT_PULLBACK": 4,
    "BLOCKED": 5,
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

_SELL_TERMS = (
    "sell",
    "close_below_ema20",
    "return_10d_lt_minus_8pct",
    "bos_down",
    "reset",
)
_REDUCE_TERMS = (
    "reduce",
    "risk",
    "high_exit_risk",
    "exit_risk",
    "subindustry_context_risk",
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
        action = "NEUTRAL"
        primary_reason: Optional[str] = None

        daily_or_rolling_2 = [
            (row, horizon, text_values)
            for row, horizon, text_values in normalized_rows
            if horizon in {"daily", "rolling 2d"}
        ]
        all_text_values = [
            value
            for _row, _horizon, text_values in normalized_rows
            for value in text_values
        ]

        sell_match = any(
            _contains_any(text_values, _SELL_TERMS)
            for _row, _horizon, text_values in daily_or_rolling_2
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

        if sell_match:
            action = "SELL"
            primary_reason = "SELL_SIGNAL_DETECTED"
            reasons.append("Matched sell-language in daily or rolling 2d context")
        elif direct_reduce_match:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons.append("Matched risk-language in daily or rolling 2d context")
        elif has_tighten_stop:
            action = "TIGHTEN_STOP"
            primary_reason = "HIGH_EXIT_RISK_DAYS_PRESENT"
            reasons.append(
                f"high_exit_risk_days_count={high_exit_risk_days_count}"
            )
        elif (
            rolling_30_positive
            and distance_to_ema20 is not None
            and distance_to_ema20 > 15.0
        ):
            action = "WAIT_PULLBACK"
            primary_reason = "STRETCHED_ABOVE_EMA20"
            reasons.append(f"distance_to_ema20={distance_to_ema20}")
        elif has_blocking:
            action = "BLOCKED"
            primary_reason = "BLOCKING_REASONS_PRESENT"
            reasons.extend(blocking_reasons)
        elif rolling_30_positive and rolling_5_constructive and daily_positive:
            action = "BUY_NOW"
            primary_reason = "MULTI_HORIZON_ALIGNMENT"
            reasons.append("rolling 30d + rolling 5d + daily constructive alignment")
        elif rolling_30_positive:
            action = "WATCH"
            primary_reason = "ROLLING_30_POSITIVE_ONLY"
            reasons.append("Positive rolling 30d context without full alignment")
        else:
            action = "NEUTRAL"
            primary_reason = "NO_DECISIVE_SIGNAL"

        if action == "BLOCKED" and direct_reduce_match:
            action = "REDUCE"
            primary_reason = "RISK_SIGNAL_DETECTED"
            reasons = ["Matched risk-language in daily or rolling 2d context"]

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
