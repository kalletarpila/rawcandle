import json
import sqlite3

import pytest

from rawcandle.technical_signal_relevance import (
    BOS_DOWN,
    RELEVANT,
    TechnicalSignalDowSnapshot,
    TechnicalSignalEvent,
    TechnicalSignalObservation,
    TechnicalSignalPivot,
    TechnicalSignalRelevanceConfig,
)
from rawcandle.technical_signal_relevance_batch import (
    run_technical_signal_relevance_batch,
)
from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    read_relevance_records_for_run,
    read_relevance_run,
)


def _connect():
    conn = sqlite3.connect(":memory:")
    apply_technical_signal_relevance_migration(conn)
    return conn


def _obs(
    ticker: str,
    signal_name: str,
    *,
    timeframe: str = "1D",
    signal_date: str = "2024-01-10",
    confirmed_as_of: str = "2024-01-10",
    close: float | None = 100.0,
    source_id: str | None = None,
):
    return TechnicalSignalObservation(
        ticker=ticker,
        timeframe=timeframe,
        signal_date=signal_date,
        signal_confirmed_as_of_date=confirmed_as_of,
        signal_name=signal_name,
        signal_close_price=close,
        signal_source_id=source_id,
    )


def _pivot_low(event_id: str, *, bars_since_confirmation: int | None):
    return TechnicalSignalPivot(
        event_type="PIVOT_LOW",
        event_date="2024-01-09",
        confirmed_as_of_date="2024-01-10",
        event_id=event_id,
        bars_since_confirmation=bars_since_confirmation,
    )


def _event(event_type: str, event_id: str, *, bars_since_confirmation: int | None):
    return TechnicalSignalEvent(
        event_type=event_type,
        event_date="2024-01-09",
        confirmed_as_of_date="2024-01-10",
        event_id=event_id,
        bars_since_confirmation=bars_since_confirmation,
    )


def test_batch_inserts_one_run_and_one_relevance_record():
    conn = _connect()
    summary = run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_001",
        [_obs("AAA", "Bullish Flag")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:00Z",
    )

    run_row = read_relevance_run(conn, "RUN_BATCH_001")
    records = read_relevance_records_for_run(conn, "RUN_BATCH_001")

    assert summary.run_id == "RUN_BATCH_001"
    assert summary.observations_seen == 1
    assert summary.records_written == 1
    assert run_row is not None
    assert len(records) == 1


def test_batch_writes_multiple_observations_in_deterministic_order_when_input_is_shuffled():
    conn = _connect()
    observations = [
        _obs("ZZZ", "Bullish Flag", signal_date="2024-01-12", confirmed_as_of="2024-01-12"),
        _obs("AAA", "Bullish Flag", signal_date="2024-01-10", confirmed_as_of="2024-01-10"),
        _obs("AAA", "Bearish Flag", signal_date="2024-01-11", confirmed_as_of="2024-01-11"),
    ]

    run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_002",
        observations,
        {
            ("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
            ("ZZZ", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
        },
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:01Z",
    )
    records = read_relevance_records_for_run(conn, "RUN_BATCH_002")

    assert [(row["ticker"], row["signal_date"], row["signal_name"]) for row in records] == [
        ("AAA", "2024-01-10", "Bullish Flag"),
        ("AAA", "2024-01-11", "Bearish Flag"),
        ("ZZZ", "2024-01-12", "Bullish Flag"),
    ]


def test_batch_summary_counts_relevant_weak_context_and_noise_correctly():
    conn = _connect()
    summary = run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_003",
        [
            _obs("AAA", "Bullish Flag"),
            _obs("BBB", "Hammer"),
            _obs("CCC", "Bearish Flag"),
        ],
        {
            ("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
            ("BBB", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
            ("CCC", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
        },
        {},
        {("BBB", "1D"): [_pivot_low("pivot1", bars_since_confirmation=None)]},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:02Z",
    )

    assert summary.relevant_count == 1
    assert summary.weak_context_count == 1
    assert summary.noise_count == 1


def test_batch_summary_counts_unknown_signal_correctly():
    conn = _connect()
    summary = run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_004",
        [_obs("AAA", "Unknown Signal")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:03Z",
    )

    assert summary.unknown_signal_count == 1
    records = read_relevance_records_for_run(conn, "RUN_BATCH_004")
    assert records[0]["signal_direction"] is None


def test_batch_summary_counts_missing_dow_context_correctly():
    conn = _connect()
    summary = run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_005",
        [_obs("AAA", "Bullish Flag")],
        {},
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:04Z",
    )

    assert summary.missing_dow_context_count == 1


def test_batch_summary_counts_missing_bar_index_correctly():
    conn = _connect()
    summary = run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_006",
        [
            _obs("AAA", "Bullish Flag"),
            _obs("BBB", "Bullish Flag"),
        ],
        {
            ("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
            ("BBB", "1D"): TechnicalSignalDowSnapshot(trend_state="UP"),
        },
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:05Z",
    )

    assert summary.missing_bar_index_count == 0


def test_duplicate_run_id_fails():
    conn = _connect()
    args = (
        conn,
        "RUN_BATCH_007",
        [_obs("AAA", "Bullish Flag")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:06Z",
    )
    run_technical_signal_relevance_batch(*args)
    with pytest.raises(sqlite3.IntegrityError):
        run_technical_signal_relevance_batch(*args)


def test_duplicate_relevance_primary_key_fails():
    conn = _connect()
    with pytest.raises(sqlite3.IntegrityError):
        run_technical_signal_relevance_batch(
            conn,
            "RUN_BATCH_008",
            [
                _obs("AAA", "Bullish Flag"),
                _obs("AAA", "Bullish Flag"),
            ],
            {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
            {},
            {},
            TechnicalSignalRelevanceConfig(),
            "2026-05-21T12:00:07Z",
        )


def test_batch_does_not_use_calendar_day_fallback_for_bars_since_fields():
    conn = _connect()
    run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_009",
        [_obs("AAA", "Bearish Divergence")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {("AAA", "1D"): [_event(BOS_DOWN, "bos1", bars_since_confirmation=3)]},
        {},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:08Z",
    )
    records = read_relevance_records_for_run(conn, "RUN_BATCH_009")

    assert records[0]["bars_since_latest_bos"] == 3
    assert records[0]["bars_since_latest_reset"] is None
    assert json.loads(records[0]["rule_trace"]).count("missing_bar_index=true") == 0


def test_batch_preserves_config_snapshot_json_in_run_table_only():
    conn = _connect()
    config = TechnicalSignalRelevanceConfig()
    run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_010",
        [_obs("AAA", "Bullish Flag")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {},
        {},
        config,
        "2026-05-21T12:00:09Z",
    )
    run_row = read_relevance_run(conn, "RUN_BATCH_010")
    records = read_relevance_records_for_run(conn, "RUN_BATCH_010")

    assert run_row is not None
    assert run_row["config_snapshot_json"] == config.to_snapshot_json()
    assert "config_snapshot_json" not in records[0]


def test_batch_stores_deterministic_rule_trace_serialization():
    conn = _connect()
    run_technical_signal_relevance_batch(
        conn,
        "RUN_BATCH_011",
        [_obs("AAA", "Bearish Divergence")],
        {("AAA", "1D"): TechnicalSignalDowSnapshot(trend_state="UP")},
        {("AAA", "1D"): [_event(BOS_DOWN, "bos_123", bars_since_confirmation=2)]},
        {("AAA", "1D"): [TechnicalSignalPivot(
            event_type="PIVOT_HIGH",
            event_date="2024-01-09",
            confirmed_as_of_date="2024-01-10",
            event_id="pivot_456",
            bars_since_confirmation=2,
        )]},
        TechnicalSignalRelevanceConfig(),
        "2026-05-21T12:00:10Z",
    )
    records = read_relevance_records_for_run(conn, "RUN_BATCH_011")
    rule_trace = json.loads(records[0]["rule_trace"])

    assert isinstance(rule_trace, list)
    assert "selected_relevance_reason=UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN" in rule_trace
    assert "latest_bos_event_id=bos_123" in rule_trace
