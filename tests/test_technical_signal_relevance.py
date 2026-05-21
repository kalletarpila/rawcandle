from rawcandle.technical_signal_relevance import (
    BEARISH,
    BOS_DOWN,
    BOS_UP,
    BULLISH,
    CANDLE,
    DIVERGENCE,
    RSI,
    TECH_SIGNAL_MAPPING_V1,
    TECH_SIGNAL_MAPPING_VERSION,
    TECH_SIGNAL_RELEVANCE_REASON_V1,
    WEAK_CONTEXT,
    classify_relevance,
    TechnicalSignalDowSnapshot,
    TechnicalSignalEvent,
    TechnicalSignalObservation,
    TechnicalSignalPivot,
    TechnicalSignalRelevanceConfig,
)


REQUIRED_SIGNAL_NAMES = {
    "Hammer",
    "Bullish Engulfing",
    "Piercing Pattern",
    "Three White Soldiers",
    "Morning Star",
    "Dragonfly Doji",
    "Bullish Abandoned Baby",
    "Bullish Flag",
    "Bull Rectangle",
    "Ascending Triangle",
    "Bullish Pennant",
    "Cup and Handle",
    "Bullish Divergence",
    "Hidden Bullish Divergence",
    "Bearish Engulfing",
    "Shooting Star",
    "Dark Cloud Cover",
    "Evening Star",
    "Hanging Man",
    "Falling Three Methods",
    "Bearish Flag",
    "Bear Rectangle",
    "Descending Triangle",
    "Bearish Pennant",
    "Bearish Divergence",
    "Hidden Bearish Divergence",
}

REQUIRED_REASON_NAMES = {
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
}


def _observation(
    *,
    signal_name: str = "Hammer",
    signal_close_price: float | None = 100.0,
    signal_date: str = "2024-01-10",
    signal_confirmed_as_of_date: str = "2024-01-10",
):
    return TechnicalSignalObservation(
        ticker="AAA",
        timeframe="1D",
        signal_date=signal_date,
        signal_confirmed_as_of_date=signal_confirmed_as_of_date,
        signal_name=signal_name,
        signal_close_price=signal_close_price,
    )


def test_mapping_contains_all_required_signal_names():
    assert REQUIRED_SIGNAL_NAMES.issubset(TECH_SIGNAL_MAPPING_V1.keys())


def test_all_mapping_rows_have_required_fields():
    for entry in TECH_SIGNAL_MAPPING_V1.values():
        assert entry.signal_direction
        assert entry.signal_family
        assert entry.signal_source_type
        assert entry.default_signal_source_id


def test_candle_signals_have_candle_source_defaults():
    for signal_name, entry in TECH_SIGNAL_MAPPING_V1.items():
        if entry.signal_source_type == CANDLE:
            assert entry.default_signal_source_id == CANDLE, signal_name


def test_divergence_signals_have_rsi_source_defaults():
    for signal_name, entry in TECH_SIGNAL_MAPPING_V1.items():
        if entry.signal_family in {DIVERGENCE, "HIDDEN_DIVERGENCE"}:
            assert entry.signal_source_type == DIVERGENCE, signal_name
            assert entry.default_signal_source_id == RSI, signal_name


def test_reason_enum_contains_all_required_values():
    assert REQUIRED_REASON_NAMES.issubset(set(TECH_SIGNAL_RELEVANCE_REASON_V1))


def test_unknown_signal_returns_weak_context_fallback():
    record = classify_relevance(
        _observation(signal_name="Not A Real Signal"),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )

    assert record.relevance_class == WEAK_CONTEXT
    assert record.relevance_reason == "UNKNOWN_SIGNAL_NAME"
    assert record.signal_direction is None
    assert record.signal_family is None
    assert record.signal_source_type is None
    assert record.signal_source_id is None
    assert "unknown_signal_name=true" in record.rule_trace
    assert f"mapping_version={TECH_SIGNAL_MAPPING_VERSION}" in record.rule_trace


def test_missing_dow_context_returns_weak_context_fallback():
    record = classify_relevance(
        _observation(),
        None,
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )

    assert record.relevance_class == WEAK_CONTEXT
    assert record.relevance_reason == "NO_DOW_CONTEXT_AVAILABLE"
    assert record.signal_direction == BULLISH
    assert "missing_dow_context=true" in record.rule_trace


def test_near_active_bos_level_uses_direction_specific_bos_prices():
    bullish_record = classify_relevance(
        _observation(signal_name="Hammer", signal_close_price=97.5),
        TechnicalSignalDowSnapshot(
            trend_state="UP",
            active_bos_low_price=95.0,
            active_bos_high_price=120.0,
        ),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(near_bos_level_pct=3.0),
    )
    bearish_record = classify_relevance(
        _observation(signal_name="Bearish Engulfing", signal_close_price=102.0),
        TechnicalSignalDowSnapshot(
            trend_state="DOWN",
            active_bos_low_price=80.0,
            active_bos_high_price=100.0,
        ),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(near_bos_level_pct=3.0),
    )
    missing_level_record = classify_relevance(
        _observation(signal_name="Hammer", signal_close_price=100.0),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )
    missing_close_record = classify_relevance(
        _observation(signal_name="Hammer", signal_close_price=None),
        TechnicalSignalDowSnapshot(trend_state="UP", active_bos_low_price=99.0),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )

    assert bullish_record.near_active_bos_level == 1
    assert bearish_record.near_active_bos_level == 1
    assert missing_level_record.near_active_bos_level == 0
    assert missing_close_record.near_active_bos_level == 0
    assert "missing_signal_close_price=true" in missing_close_record.rule_trace


def test_events_and_pivots_enforce_no_lookahead_by_confirmed_as_of_date():
    record = classify_relevance(
        _observation(signal_confirmed_as_of_date="2024-01-10"),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=[
            TechnicalSignalEvent(
                event_type=BOS_DOWN,
                event_date="2024-01-09",
                confirmed_as_of_date="2024-01-11",
                event_id="future",
            ),
            TechnicalSignalEvent(
                event_type=BOS_UP,
                event_date="2024-01-08",
                confirmed_as_of_date="2024-01-10",
                event_id="usable",
            ),
        ],
        pivots=[
            TechnicalSignalPivot(
                event_type="PIVOT_LOW",
                event_date="2024-01-10",
                confirmed_as_of_date="2024-01-12",
                event_id="future-pivot",
            ),
            TechnicalSignalPivot(
                event_type="PIVOT_LOW",
                event_date="2024-01-10",
                confirmed_as_of_date="2024-01-10",
                event_id="usable-pivot",
            ),
        ],
        config=TechnicalSignalRelevanceConfig(),
    )

    assert record.latest_bos_direction == "UP"
    assert "eligible_event_ids=usable" in record.rule_trace
    assert "eligible_pivot_ids=usable-pivot" in record.rule_trace
    assert record.near_latest_pivot == 1


def test_events_and_pivots_are_sorted_deterministically_independent_of_input_order():
    events_a = [
        TechnicalSignalEvent(BOS_UP, "2024-01-08", "2024-01-10", event_id="b"),
        TechnicalSignalEvent(BOS_DOWN, "2024-01-09", "2024-01-10", event_id="a"),
    ]
    events_b = list(reversed(events_a))
    pivots_a = [
        TechnicalSignalPivot("PIVOT_LOW", "2024-01-10", "2024-01-10", event_id="2"),
        TechnicalSignalPivot("PIVOT_LOW", "2024-01-10", "2024-01-10", event_id="1"),
    ]
    pivots_b = list(reversed(pivots_a))

    record_a = classify_relevance(
        _observation(),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=events_a,
        pivots=pivots_a,
        config=TechnicalSignalRelevanceConfig(),
    )
    record_b = classify_relevance(
        _observation(),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=events_b,
        pivots=pivots_b,
        config=TechnicalSignalRelevanceConfig(),
    )

    assert record_a.rule_trace == record_b.rule_trace
    assert "eligible_event_ids=b,a" in record_a.rule_trace
    assert "eligible_pivot_ids=1,2" in record_a.rule_trace


def test_bars_since_fields_do_not_use_calendar_fallback():
    record = classify_relevance(
        _observation(),
        TechnicalSignalDowSnapshot(trend_state="UP"),
        events=[],
        pivots=[],
        config=TechnicalSignalRelevanceConfig(),
    )

    assert record.bars_since_latest_bos is None
    assert record.bars_since_latest_reset is None
    assert "missing_bar_index=true" in record.rule_trace


def test_basic_classification_is_deterministic_for_same_input():
    observation = _observation(signal_name="Bearish Divergence", signal_close_price=100.0)
    dow_snapshot = TechnicalSignalDowSnapshot(
        trend_state="UP",
        active_bos_high_price=101.0,
        active_bos_low_price=90.0,
    )
    events = [
        TechnicalSignalEvent(BOS_DOWN, "2024-01-09", "2024-01-10", event_id="1"),
    ]
    pivots = [
        TechnicalSignalPivot("PIVOT_HIGH", "2024-01-10", "2024-01-10", event_id="2"),
    ]
    config = TechnicalSignalRelevanceConfig()

    record_a = classify_relevance(observation, dow_snapshot, events, pivots, config)
    record_b = classify_relevance(observation, dow_snapshot, list(events), list(pivots), config)

    assert record_a.relevance_class == record_b.relevance_class
    assert record_a.relevance_reason == record_b.relevance_reason
    assert record_a.config_snapshot_json == record_b.config_snapshot_json
    assert record_a.rule_trace == record_b.rule_trace
