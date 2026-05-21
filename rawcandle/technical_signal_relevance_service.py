from __future__ import annotations

import sqlite3
from typing import Iterable

from .technical_signal_relevance import TechnicalSignalRelevanceConfig
from .technical_signal_relevance_batch import (
    ObservationContextKey,
    TechnicalSignalRelevanceBatchSummary,
    run_technical_signal_relevance_batch,
)
from .technical_signal_relevance_sources import (
    assign_event_bar_distances,
    assign_pivot_bar_distances,
    build_bar_index,
    read_candlestick_observations,
    read_divergence_observations,
    read_dow_events,
    read_dow_pivots,
    read_dow_snapshot,
)


def _normalize_requested_tickers(tickers: Iterable[str]) -> list[str]:
    unique_tickers = {str(ticker) for ticker in tickers}
    return sorted(unique_tickers)


def run_technical_signal_relevance_for_tickers(
    conn: sqlite3.Connection,
    tickers: Iterable[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    run_id: str,
    created_at_utc: str,
    config: TechnicalSignalRelevanceConfig | None = None,
) -> TechnicalSignalRelevanceBatchSummary:
    resolved_config = config or TechnicalSignalRelevanceConfig()
    normalized_tickers = _normalize_requested_tickers(tickers)
    lookback_bars = max(
        resolved_config.near_pivot_window_bars,
        resolved_config.recent_bos_window_bars,
        resolved_config.recent_reset_window_bars,
    ) + 5

    observations = []
    for ticker in normalized_tickers:
        observations.extend(
            read_candlestick_observations(
                conn,
                ticker,
                timeframe,
                start_date,
                end_date,
            )
        )
        observations.extend(
            read_divergence_observations(
                conn,
                ticker,
                timeframe,
                start_date,
                end_date,
            )
        )

    bar_indexes = {
        ticker: build_bar_index(
            conn,
            ticker,
            timeframe,
            start_date,
            end_date,
            lookback_bars,
        )
        for ticker in normalized_tickers
    }

    dow_snapshots_by_key: dict[ObservationContextKey, object] = {}
    events_by_key: dict[ObservationContextKey, object] = {}
    pivots_by_key: dict[ObservationContextKey, object] = {}
    for observation in observations:
        key: ObservationContextKey = (
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        if key in dow_snapshots_by_key:
            continue
        dow_snapshots_by_key[key] = read_dow_snapshot(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        raw_events = read_dow_events(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        raw_pivots = read_dow_pivots(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        bar_index = bar_indexes.get(observation.ticker)
        events_by_key[key] = assign_event_bar_distances(
            raw_events,
            observation.signal_confirmed_as_of_date,
            bar_index,
        )
        pivots_by_key[key] = assign_pivot_bar_distances(
            raw_pivots,
            observation.signal_confirmed_as_of_date,
            bar_index,
        )

    return run_technical_signal_relevance_batch(
        conn=conn,
        run_id=run_id,
        observations=observations,
        dow_snapshots_by_key=dow_snapshots_by_key,
        events_by_key=events_by_key,
        pivots_by_key=pivots_by_key,
        config=resolved_config,
        created_at_utc=created_at_utc,
    )


__all__ = ["run_technical_signal_relevance_for_tickers"]
