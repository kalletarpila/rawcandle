from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar


TECH_SIGNAL_RELEVANCE_RULE_VERSION = "TECH_SIGNAL_RELEVANCE_V1"
TECH_SIGNAL_MAPPING_VERSION = "TECH_SIGNAL_MAPPING_V1"
TECH_SIGNAL_RELEVANCE_REASON_VERSION = "TECH_SIGNAL_RELEVANCE_REASON_V1"

RELEVANT = "RELEVANT"
WEAK_CONTEXT = "WEAK_CONTEXT"
NOISE = "NOISE"

BULLISH = "BULLISH"
BEARISH = "BEARISH"

REVERSAL_STRONG = "REVERSAL_STRONG"
REVERSAL_MEDIUM = "REVERSAL_MEDIUM"
CONTINUATION = "CONTINUATION"
STRUCTURAL_PATTERN = "STRUCTURAL_PATTERN"
DIVERGENCE = "DIVERGENCE"
HIDDEN_DIVERGENCE = "HIDDEN_DIVERGENCE"

CANDLE = "CANDLE"
RSI = "RSI"

UP = "UP"
DOWN = "DOWN"
NEUTRAL = "NEUTRAL"

PIVOT_HIGH = "PIVOT_HIGH"
PIVOT_LOW = "PIVOT_LOW"
BOS_UP = "BOS_UP"
BOS_DOWN = "BOS_DOWN"
RESET = "RESET"


@dataclass(frozen=True)
class TechnicalSignalMappingEntry:
    signal_name: str
    signal_direction: str
    signal_family: str
    signal_source_type: str
    default_signal_source_id: str


@dataclass(frozen=True)
class TechnicalSignalRelevanceConfig:
    near_pivot_window_bars: int = 5
    recent_bos_window_bars: int = 10
    recent_reset_window_bars: int = 20
    near_bos_level_pct: float = 3.0
    rule_version: str = TECH_SIGNAL_RELEVANCE_RULE_VERSION
    mapping_version: str = TECH_SIGNAL_MAPPING_VERSION
    reason_version: str = TECH_SIGNAL_RELEVANCE_REASON_VERSION

    def to_snapshot_dict(self) -> dict[str, object]:
        return {
            "mapping_version": self.mapping_version,
            "near_bos_level_pct": self.near_bos_level_pct,
            "near_pivot_window_bars": self.near_pivot_window_bars,
            "reason_version": self.reason_version,
            "recent_bos_window_bars": self.recent_bos_window_bars,
            "recent_reset_window_bars": self.recent_reset_window_bars,
            "rule_version": self.rule_version,
        }

    def to_snapshot_json(self) -> str:
        return json.dumps(self.to_snapshot_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class TechnicalSignalObservation:
    ticker: str
    timeframe: str
    signal_date: str
    signal_confirmed_as_of_date: str
    signal_name: str
    signal_close_price: float | None
    signal_source_id: str | None = None


@dataclass(frozen=True)
class TechnicalSignalDowSnapshot:
    trend_state: str | None
    dow_context_state: str | None = None
    active_bos_high_price: float | None = None
    active_bos_low_price: float | None = None
    structure_epoch_id: int | None = None
    as_of_date: str | None = None


@dataclass(frozen=True)
class TechnicalSignalEvent:
    event_type: str
    event_date: str
    confirmed_as_of_date: str
    event_id: str | int | None = None
    structure_epoch_id: int | None = None


@dataclass(frozen=True)
class TechnicalSignalPivot:
    event_type: str
    event_date: str
    confirmed_as_of_date: str
    event_id: str | int | None = None
    structure_epoch_id: int | None = None


@dataclass(frozen=True)
class TechnicalSignalRelevanceRecord:
    ticker: str
    timeframe: str
    signal_date: str
    signal_confirmed_as_of_date: str
    signal_name: str
    signal_close_price: float | None
    signal_direction: str | None
    signal_family: str | None
    signal_source_type: str | None
    signal_source_id: str | None
    dow_trend_state: str | None
    dow_context_state: str | None
    latest_bos_direction: str | None
    bars_since_latest_bos: int | None
    latest_reset_reason: str | None
    bars_since_latest_reset: int | None
    near_latest_pivot: int
    near_active_bos_level: int
    is_trend_aligned: int
    is_counter_trend: int
    relevance_class: str
    relevance_reason: str
    relevance_rule_version: str
    mapping_version: str
    reason_version: str
    config_snapshot_json: str
    rule_trace: tuple[str, ...]


T = TypeVar("T")


TECH_SIGNAL_MAPPING_V1 = {
    entry.signal_name: entry
    for entry in (
        TechnicalSignalMappingEntry("Hammer", BULLISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bullish Engulfing", BULLISH, REVERSAL_STRONG, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Piercing Pattern", BULLISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Three White Soldiers", BULLISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Morning Star", BULLISH, REVERSAL_STRONG, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Dragonfly Doji", BULLISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bullish Abandoned Baby", BULLISH, REVERSAL_STRONG, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bullish Flag", BULLISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bull Rectangle", BULLISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Ascending Triangle", BULLISH, STRUCTURAL_PATTERN, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bullish Pennant", BULLISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Cup and Handle", BULLISH, STRUCTURAL_PATTERN, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bullish Divergence", BULLISH, DIVERGENCE, DIVERGENCE, RSI),
        TechnicalSignalMappingEntry("Hidden Bullish Divergence", BULLISH, HIDDEN_DIVERGENCE, DIVERGENCE, RSI),
        TechnicalSignalMappingEntry("Bearish Engulfing", BEARISH, REVERSAL_STRONG, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Shooting Star", BEARISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Dark Cloud Cover", BEARISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Evening Star", BEARISH, REVERSAL_STRONG, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Hanging Man", BEARISH, REVERSAL_MEDIUM, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Falling Three Methods", BEARISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bearish Flag", BEARISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bear Rectangle", BEARISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Descending Triangle", BEARISH, STRUCTURAL_PATTERN, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bearish Pennant", BEARISH, CONTINUATION, CANDLE, CANDLE),
        TechnicalSignalMappingEntry("Bearish Divergence", BEARISH, DIVERGENCE, DIVERGENCE, RSI),
        TechnicalSignalMappingEntry("Hidden Bearish Divergence", BEARISH, HIDDEN_DIVERGENCE, DIVERGENCE, RSI),
    )
}

TECH_SIGNAL_RELEVANCE_REASON_V1 = (
    "NO_DOW_CONTEXT_AVAILABLE",
    "UNKNOWN_SIGNAL_NAME",
    "MAPPING_VERSION_MISSING",
    "INSUFFICIENT_CONTEXT",
    "UP_TREND_BULLISH_CONTINUATION",
    "UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    "UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT",
    "UP_TREND_HIDDEN_BULLISH_DIVERGENCE",
    "UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK",
    "UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS",
    "UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS",
    "UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN",
    "UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN",
    "UP_TREND_BEARISH_CONTINUATION_WITHOUT_BEARISH_STRUCTURE",
    "DOWN_TREND_BEARISH_CONTINUATION",
    "DOWN_TREND_BEARISH_PULLBACK_REVERSAL_NEAR_PIVOT_HIGH",
    "DOWN_TREND_BEARISH_REVERSAL_WITHOUT_PIVOT_CONTEXT",
    "DOWN_TREND_HIDDEN_BEARISH_DIVERGENCE",
    "DOWN_TREND_REGULAR_BEARISH_DIVERGENCE_WEAK",
    "DOWN_TREND_COUNTER_BULLISH_REVERSAL_STRONG_WITHOUT_BOS",
    "DOWN_TREND_COUNTER_BULLISH_REVERSAL_MEDIUM_WITHOUT_BOS",
    "DOWN_TREND_BULLISH_REVERSAL_AFTER_BOS_UP",
    "DOWN_TREND_BULLISH_DIVERGENCE_AFTER_BOS_UP",
    "DOWN_TREND_BULLISH_CONTINUATION_WITHOUT_BULLISH_STRUCTURE",
    "NEUTRAL_CONTINUATION_NO_TREND",
    "NEUTRAL_REVERSAL_STRONG_WEAK_CONTEXT",
    "NEUTRAL_REVERSAL_MEDIUM_NOISE",
    "NEUTRAL_DIVERGENCE_WEAK_CONTEXT",
    "NEUTRAL_STRUCTURAL_PATTERN_WEAK_CONTEXT",
    "NEUTRAL_AFTER_RESET_STRONG_REVERSAL",
    "NEUTRAL_AFTER_RESET_DIVERGENCE",
    "NEUTRAL_AFTER_RESET_HIDDEN_DIVERGENCE_WEAK",
    "NEUTRAL_AFTER_RESET_CONTINUATION_WITHOUT_TREND",
    "NEUTRAL_AFTER_RESET_MEDIUM_REVERSAL_WEAK",
)


def _event_sort_key(item: TechnicalSignalEvent | TechnicalSignalPivot) -> tuple[str, str, str, str, str]:
    return (
        item.confirmed_as_of_date,
        item.event_date,
        item.event_type,
        "" if item.event_id is None else str(item.event_id),
        "" if item.structure_epoch_id is None else str(item.structure_epoch_id),
    )


def _filter_sort_eligible(items: list[T], confirmed_as_of_date: str) -> list[T]:
    eligible = [
        item
        for item in items
        if item.confirmed_as_of_date <= confirmed_as_of_date
    ]
    return sorted(eligible, key=_event_sort_key)


def _extract_latest_bos_direction(events: list[TechnicalSignalEvent]) -> str | None:
    for event in reversed(events):
        if event.event_type == BOS_UP:
            return UP
        if event.event_type == BOS_DOWN:
            return DOWN
    return None


def _extract_latest_reset_reason(events: list[TechnicalSignalEvent]) -> str | None:
    for event in reversed(events):
        if event.event_type == RESET:
            return str(event.event_id) if event.event_id is not None else RESET
    return None


def _is_trend_aligned(trend_state: str | None, signal_direction: str | None) -> int:
    if trend_state == UP and signal_direction == BULLISH:
        return 1
    if trend_state == DOWN and signal_direction == BEARISH:
        return 1
    return 0


def _is_counter_trend(trend_state: str | None, signal_direction: str | None) -> int:
    if trend_state == UP and signal_direction == BEARISH:
        return 1
    if trend_state == DOWN and signal_direction == BULLISH:
        return 1
    return 0


def _near_active_bos_level(
    observation: TechnicalSignalObservation,
    signal_direction: str | None,
    dow_snapshot: TechnicalSignalDowSnapshot | None,
    config: TechnicalSignalRelevanceConfig,
    trace: list[str],
) -> int:
    if observation.signal_close_price is None:
        trace.append("missing_signal_close_price=true")
        return 0

    if signal_direction == BULLISH:
        active_level = None if dow_snapshot is None else dow_snapshot.active_bos_low_price
    elif signal_direction == BEARISH:
        active_level = None if dow_snapshot is None else dow_snapshot.active_bos_high_price
    else:
        active_level = None

    if active_level in (None, 0):
        return 0

    distance_pct = abs(observation.signal_close_price - active_level) / active_level * 100
    trace.append(f"active_bos_distance_pct={distance_pct:.6f}")
    return 1 if distance_pct <= config.near_bos_level_pct else 0


def _near_latest_pivot(
    observation: TechnicalSignalObservation,
    signal_direction: str | None,
    pivots: list[TechnicalSignalPivot],
) -> int:
    if signal_direction == BULLISH:
        expected_event_type = PIVOT_LOW
    elif signal_direction == BEARISH:
        expected_event_type = PIVOT_HIGH
    else:
        return 0

    for pivot in reversed(pivots):
        if pivot.event_type == expected_event_type and pivot.event_date == observation.signal_date:
            return 1
    return 0


def _classify_with_context(
    *,
    signal_direction: str,
    signal_family: str,
    trend_state: str,
    latest_bos_direction: str | None,
    latest_reset_reason: str | None,
    near_latest_pivot: int,
) -> tuple[str, str]:
    if trend_state == UP:
        if signal_direction == BULLISH:
            if signal_family == HIDDEN_DIVERGENCE:
                return RELEVANT, "UP_TREND_HIDDEN_BULLISH_DIVERGENCE"
            if signal_family == DIVERGENCE:
                return WEAK_CONTEXT, "UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK"
            if signal_family in {CONTINUATION, STRUCTURAL_PATTERN}:
                return RELEVANT, "UP_TREND_BULLISH_CONTINUATION"
            if near_latest_pivot:
                return RELEVANT, "UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW"
            return WEAK_CONTEXT, "UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT"
        if signal_family == DIVERGENCE and latest_bos_direction == DOWN:
            return RELEVANT, "UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN"
        if signal_family in {REVERSAL_STRONG, REVERSAL_MEDIUM} and latest_bos_direction == DOWN:
            return RELEVANT, "UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN"
        if signal_family == REVERSAL_STRONG:
            return WEAK_CONTEXT, "UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS"
        if signal_family == REVERSAL_MEDIUM:
            return NOISE, "UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS"
        return NOISE, "UP_TREND_BEARISH_CONTINUATION_WITHOUT_BEARISH_STRUCTURE"

    if trend_state == DOWN:
        if signal_direction == BEARISH:
            if signal_family == HIDDEN_DIVERGENCE:
                return RELEVANT, "DOWN_TREND_HIDDEN_BEARISH_DIVERGENCE"
            if signal_family == DIVERGENCE:
                return WEAK_CONTEXT, "DOWN_TREND_REGULAR_BEARISH_DIVERGENCE_WEAK"
            if signal_family in {CONTINUATION, STRUCTURAL_PATTERN}:
                return RELEVANT, "DOWN_TREND_BEARISH_CONTINUATION"
            if near_latest_pivot:
                return RELEVANT, "DOWN_TREND_BEARISH_PULLBACK_REVERSAL_NEAR_PIVOT_HIGH"
            return WEAK_CONTEXT, "DOWN_TREND_BEARISH_REVERSAL_WITHOUT_PIVOT_CONTEXT"
        if signal_family == DIVERGENCE and latest_bos_direction == UP:
            return RELEVANT, "DOWN_TREND_BULLISH_DIVERGENCE_AFTER_BOS_UP"
        if signal_family in {REVERSAL_STRONG, REVERSAL_MEDIUM} and latest_bos_direction == UP:
            return RELEVANT, "DOWN_TREND_BULLISH_REVERSAL_AFTER_BOS_UP"
        if signal_family == REVERSAL_STRONG:
            return WEAK_CONTEXT, "DOWN_TREND_COUNTER_BULLISH_REVERSAL_STRONG_WITHOUT_BOS"
        if signal_family == REVERSAL_MEDIUM:
            return NOISE, "DOWN_TREND_COUNTER_BULLISH_REVERSAL_MEDIUM_WITHOUT_BOS"
        return NOISE, "DOWN_TREND_BULLISH_CONTINUATION_WITHOUT_BULLISH_STRUCTURE"

    if latest_reset_reason is not None:
        if signal_family == REVERSAL_STRONG:
            return WEAK_CONTEXT, "NEUTRAL_AFTER_RESET_STRONG_REVERSAL"
        if signal_family == REVERSAL_MEDIUM:
            return WEAK_CONTEXT, "NEUTRAL_AFTER_RESET_MEDIUM_REVERSAL_WEAK"
        if signal_family == DIVERGENCE:
            return WEAK_CONTEXT, "NEUTRAL_AFTER_RESET_DIVERGENCE"
        if signal_family == HIDDEN_DIVERGENCE:
            return WEAK_CONTEXT, "NEUTRAL_AFTER_RESET_HIDDEN_DIVERGENCE_WEAK"
        return NOISE, "NEUTRAL_AFTER_RESET_CONTINUATION_WITHOUT_TREND"

    if signal_family in {CONTINUATION}:
        return WEAK_CONTEXT, "NEUTRAL_CONTINUATION_NO_TREND"
    if signal_family == REVERSAL_STRONG:
        return WEAK_CONTEXT, "NEUTRAL_REVERSAL_STRONG_WEAK_CONTEXT"
    if signal_family == REVERSAL_MEDIUM:
        return NOISE, "NEUTRAL_REVERSAL_MEDIUM_NOISE"
    if signal_family in {DIVERGENCE, HIDDEN_DIVERGENCE}:
        return WEAK_CONTEXT, "NEUTRAL_DIVERGENCE_WEAK_CONTEXT"
    return WEAK_CONTEXT, "NEUTRAL_STRUCTURAL_PATTERN_WEAK_CONTEXT"


def classify_relevance(
    observation: TechnicalSignalObservation,
    dow_snapshot: TechnicalSignalDowSnapshot | None,
    events: list[TechnicalSignalEvent] | None,
    pivots: list[TechnicalSignalPivot] | None,
    config: TechnicalSignalRelevanceConfig | None = None,
) -> TechnicalSignalRelevanceRecord:
    resolved_config = config or TechnicalSignalRelevanceConfig()
    resolved_events = _filter_sort_eligible(
        list(events or []),
        observation.signal_confirmed_as_of_date,
    )
    resolved_pivots = _filter_sort_eligible(
        list(pivots or []),
        observation.signal_confirmed_as_of_date,
    )
    latest_bos_direction = _extract_latest_bos_direction(resolved_events)
    latest_reset_reason = _extract_latest_reset_reason(resolved_events)
    trace = [
        f"rule_version={resolved_config.rule_version}",
        f"mapping_version={resolved_config.mapping_version}",
        f"reason_version={resolved_config.reason_version}",
        f"eligible_event_ids={','.join('' if event.event_id is None else str(event.event_id) for event in resolved_events)}",
        f"eligible_pivot_ids={','.join('' if pivot.event_id is None else str(pivot.event_id) for pivot in resolved_pivots)}",
        "missing_bar_index=true",
    ]

    base_record = {
        "ticker": observation.ticker,
        "timeframe": observation.timeframe,
        "signal_date": observation.signal_date,
        "signal_confirmed_as_of_date": observation.signal_confirmed_as_of_date,
        "signal_name": observation.signal_name,
        "signal_close_price": observation.signal_close_price,
        "dow_trend_state": None if dow_snapshot is None else dow_snapshot.trend_state,
        "dow_context_state": None if dow_snapshot is None else dow_snapshot.dow_context_state,
        "latest_bos_direction": latest_bos_direction,
        "bars_since_latest_bos": None,
        "latest_reset_reason": latest_reset_reason,
        "bars_since_latest_reset": None,
        "relevance_rule_version": resolved_config.rule_version,
        "mapping_version": resolved_config.mapping_version,
        "reason_version": resolved_config.reason_version,
        "config_snapshot_json": resolved_config.to_snapshot_json(),
    }

    if not resolved_config.mapping_version:
        trace.append("mapping_version_missing=true")
        return TechnicalSignalRelevanceRecord(
            **base_record,
            signal_direction=None,
            signal_family=None,
            signal_source_type=None,
            signal_source_id=None,
            near_latest_pivot=0,
            near_active_bos_level=0,
            is_trend_aligned=0,
            is_counter_trend=0,
            relevance_class=WEAK_CONTEXT,
            relevance_reason="MAPPING_VERSION_MISSING",
            rule_trace=tuple(trace),
        )

    mapping_entry = TECH_SIGNAL_MAPPING_V1.get(observation.signal_name)
    if mapping_entry is None:
        trace.append("unknown_signal_name=true")
        return TechnicalSignalRelevanceRecord(
            **base_record,
            signal_direction=None,
            signal_family=None,
            signal_source_type=None,
            signal_source_id=None,
            near_latest_pivot=0,
            near_active_bos_level=0,
            is_trend_aligned=0,
            is_counter_trend=0,
            relevance_class=WEAK_CONTEXT,
            relevance_reason="UNKNOWN_SIGNAL_NAME",
            rule_trace=tuple(trace),
        )

    near_active_level = _near_active_bos_level(
        observation,
        mapping_entry.signal_direction,
        dow_snapshot,
        resolved_config,
        trace,
    )
    near_pivot = _near_latest_pivot(
        observation,
        mapping_entry.signal_direction,
        resolved_pivots,
    )
    trace.append(f"near_latest_pivot={near_pivot}")
    trace.append(f"near_active_bos_level={near_active_level}")

    if dow_snapshot is None or not dow_snapshot.trend_state:
        trace.append("missing_dow_context=true")
        return TechnicalSignalRelevanceRecord(
            **base_record,
            signal_direction=mapping_entry.signal_direction,
            signal_family=mapping_entry.signal_family,
            signal_source_type=mapping_entry.signal_source_type,
            signal_source_id=observation.signal_source_id or mapping_entry.default_signal_source_id,
            near_latest_pivot=near_pivot,
            near_active_bos_level=near_active_level,
            is_trend_aligned=0,
            is_counter_trend=0,
            relevance_class=WEAK_CONTEXT,
            relevance_reason="NO_DOW_CONTEXT_AVAILABLE",
            rule_trace=tuple(trace),
        )

    relevance_class, relevance_reason = _classify_with_context(
        signal_direction=mapping_entry.signal_direction,
        signal_family=mapping_entry.signal_family,
        trend_state=dow_snapshot.trend_state,
        latest_bos_direction=latest_bos_direction,
        latest_reset_reason=latest_reset_reason,
        near_latest_pivot=near_pivot,
    )
    trace.append(f"classification={relevance_class}")
    trace.append(f"reason={relevance_reason}")
    return TechnicalSignalRelevanceRecord(
        **base_record,
        signal_direction=mapping_entry.signal_direction,
        signal_family=mapping_entry.signal_family,
        signal_source_type=mapping_entry.signal_source_type,
        signal_source_id=observation.signal_source_id or mapping_entry.default_signal_source_id,
        near_latest_pivot=near_pivot,
        near_active_bos_level=near_active_level,
        is_trend_aligned=_is_trend_aligned(dow_snapshot.trend_state, mapping_entry.signal_direction),
        is_counter_trend=_is_counter_trend(dow_snapshot.trend_state, mapping_entry.signal_direction),
        relevance_class=relevance_class,
        relevance_reason=relevance_reason,
        rule_trace=tuple(trace),
    )


__all__ = [
    "BEARISH",
    "BOS_DOWN",
    "BOS_UP",
    "BULLISH",
    "CANDLE",
    "CONTINUATION",
    "DIVERGENCE",
    "DOWN",
    "HIDDEN_DIVERGENCE",
    "NEUTRAL",
    "NOISE",
    "PIVOT_HIGH",
    "PIVOT_LOW",
    "RELEVANT",
    "RESET",
    "REVERSAL_MEDIUM",
    "REVERSAL_STRONG",
    "RSI",
    "STRUCTURAL_PATTERN",
    "TECH_SIGNAL_MAPPING_V1",
    "TECH_SIGNAL_MAPPING_VERSION",
    "TECH_SIGNAL_RELEVANCE_REASON_V1",
    "TECH_SIGNAL_RELEVANCE_REASON_VERSION",
    "TECH_SIGNAL_RELEVANCE_RULE_VERSION",
    "TechnicalSignalDowSnapshot",
    "TechnicalSignalEvent",
    "TechnicalSignalMappingEntry",
    "TechnicalSignalObservation",
    "TechnicalSignalPivot",
    "TechnicalSignalRelevanceConfig",
    "TechnicalSignalRelevanceRecord",
    "UP",
    "WEAK_CONTEXT",
    "classify_relevance",
]
