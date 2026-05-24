from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from dev_tools.datacenter_dashboard_decisions import DatacenterTickerDecision
from dev_tools.datacenter_dashboard_parser import DatacenterDashboardRow


@dataclass(frozen=True)
class DatacenterTickerInspectorView:
    ticker: str
    action: str
    severity: str
    primary_reason: str | None
    pullback_validity: str | None = None
    pullback_reason: str | None = None
    supporting_signals: list[str] = field(default_factory=list)
    conflicting_signals: list[str] = field(default_factory=list)
    override_explanation: str | None = None
    conflict_detected: bool = False


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
_SELL_SUPPORT_SIGNALS = (
    ("SELL", "sell"),
    ("close_below_ema20", "close_below_ema20"),
    ("return_10d_lt_minus_8pct", "return_10d_lt_minus_8pct"),
    ("BOS_DOWN", "bos_down"),
    ("RESET", "reset"),
    ("DOUBLE_BOS_DOWN", "double_bos_down"),
    ("high_exit_risk", "high_exit_risk"),
    ("FAILED_PULLBACK", "failed_pullback"),
)
_REDUCE_SUPPORT_SIGNALS = (
    ("REDUCE", "reduce"),
    ("RISK", "risk"),
    ("high_exit_risk", "high_exit_risk"),
    ("exit_risk", "exit_risk"),
    ("subindustry_context_risk", "subindustry_context_risk"),
)
_CONSTRUCTIVE_CONFLICT_SIGNALS = (
    ("PULLBACK_CANDIDATE", "pullback_candidate"),
    ("BUY_ZONE", "buy_zone"),
    ("BUY_NOW", "buy_now"),
    ("BULLISH", "bullish"),
    ("REVERSAL", "reversal"),
    ("BOS_UP", "bos_up"),
    ("SUPPORT", "support"),
    ("BREAKOUT_CANDIDATE", "breakout_candidate"),
)
_BEARISH_CONFLICT_SIGNALS = (
    ("SELL", "sell"),
    ("REDUCE", "reduce"),
    ("RISK", "risk"),
    ("BOS_DOWN", "bos_down"),
    ("RESET", "reset"),
    ("FAILED_PULLBACK", "failed_pullback"),
    ("close_below_ema20", "close_below_ema20"),
    ("return_10d_lt_minus_8pct", "return_10d_lt_minus_8pct"),
    ("high_exit_risk", "high_exit_risk"),
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


def _collect_text_values(rows: Iterable[DatacenterDashboardRow]) -> list[str]:
    values: list[str] = []
    for row in rows:
        values.extend(
            [
                row.raw_action or "",
                row.raw_status or "",
                row.reason or "",
                row.trend_state or "",
                row.latest_structure_label or "",
                row.latest_bos_event_type or "",
                row.latest_reset_reason or "",
                row.blocking_reasons or "",
                *row.raw_fields.values(),
            ]
        )
    return [value.lower() for value in values if value]


def _contains_any(text_values: list[str], terms: Iterable[str]) -> bool:
    return any(term.lower() in value for value in text_values for term in terms)


def _matched_labels(
    text_values: list[str],
    signal_terms: Iterable[tuple[str, str]],
) -> list[str]:
    labels: list[str] = []
    has_double_bos_down = any("double_bos_down" in value for value in text_values)
    for label, term in signal_terms:
        if label == "BOS_DOWN" and has_double_bos_down:
            continue
        if any(term in value for value in text_values):
            labels.append(label)
    return labels


def build_datacenter_ticker_inspector_view(
    *,
    decision: DatacenterTickerDecision,
    rows: Iterable[DatacenterDashboardRow],
) -> DatacenterTickerInspectorView:
    ticker_rows = [row for row in rows if row.ticker == decision.ticker]
    text_values = _collect_text_values(ticker_rows)
    normalized_rows = [
        (row, _normalize_horizon(row.horizon), _collect_text_values([row]))
        for row in ticker_rows
    ]

    rolling_30_positive = any(
        horizon == "rolling 30d"
        and _contains_any(texts, _ROLLING_30_POSITIVE_TERMS)
        for _row, horizon, texts in normalized_rows
    )
    rolling_5_constructive = any(
        horizon == "rolling 5d"
        and _contains_any(texts, _ROLLING_5_POSITIVE_TERMS)
        for _row, horizon, texts in normalized_rows
    )
    daily_positive = any(
        horizon == "daily"
        and _contains_any(texts, _DAILY_POSITIVE_TERMS)
        for _row, horizon, texts in normalized_rows
    )

    supporting_signals: list[str] = []
    conflicting_signals: list[str] = []
    override_explanation: str | None = None

    if decision.action == "SELL":
        supporting_signals = _matched_labels(text_values, _SELL_SUPPORT_SIGNALS)
        conflicting_signals = _matched_labels(
            text_values, _CONSTRUCTIVE_CONFLICT_SIGNALS
        )
        if conflicting_signals:
            override_explanation = (
                "Bearish structural/risk signals override constructive pullback labels."
            )
    elif decision.action == "REDUCE":
        supporting_signals = _matched_labels(text_values, _REDUCE_SUPPORT_SIGNALS)
        conflicting_signals = _matched_labels(
            text_values, _CONSTRUCTIVE_CONFLICT_SIGNALS
        )
    elif decision.action == "TIGHTEN_STOP":
        if (
            decision.high_exit_risk_days_count is not None
            and decision.high_exit_risk_days_count >= 1
        ):
            supporting_signals = [
                f"high_exit_risk_days_count>={decision.high_exit_risk_days_count}"
            ]
        conflicting_signals = _matched_labels(
            text_values, _CONSTRUCTIVE_CONFLICT_SIGNALS
        )
    elif decision.action == "BLOCKED":
        supporting_signals = sorted(decision.blocking_reasons)
        conflicting_signals = _matched_labels(
            text_values, _CONSTRUCTIVE_CONFLICT_SIGNALS
        )
        if conflicting_signals:
            override_explanation = (
                "Blocking reasons override constructive setup labels."
            )
    elif decision.action == "WAIT_PULLBACK":
        if rolling_30_positive:
            supporting_signals.append("rolling 30d positive context")
        if decision.distance_to_ema20 is not None and decision.distance_to_ema20 > 15.0:
            supporting_signals.append("distance_to_ema20>15.0")
            override_explanation = (
                "Constructive setup is present, but EMA20 distance is stretched."
            )
        conflicting_signals = _matched_labels(text_values, _BEARISH_CONFLICT_SIGNALS)
    elif decision.action == "BUY_NOW":
        if rolling_30_positive:
            supporting_signals.append("rolling 30d positive context")
        if rolling_5_constructive:
            supporting_signals.append("rolling 5d constructive context")
        if daily_positive:
            supporting_signals.append("daily positive trigger")
        conflicting_signals = _matched_labels(text_values, _BEARISH_CONFLICT_SIGNALS)
    elif decision.action == "WATCH":
        if rolling_30_positive:
            supporting_signals.append("rolling 30d positive context")
        conflicting_signals = _matched_labels(text_values, _BEARISH_CONFLICT_SIGNALS)
    else:
        conflicting_signals = []

    return DatacenterTickerInspectorView(
        ticker=decision.ticker,
        action=decision.action,
        severity=decision.severity,
        primary_reason=decision.primary_reason,
        pullback_validity=decision.pullback_validity,
        pullback_reason=decision.pullback_reason,
        supporting_signals=supporting_signals,
        conflicting_signals=conflicting_signals,
        override_explanation=override_explanation,
        conflict_detected=bool(conflicting_signals),
    )
