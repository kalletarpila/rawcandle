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
    MAX_BAR_INDEX_LOOKBACK_BARS,
    assign_event_bar_distances,
    assign_pivot_bar_distances,
    build_context_aware_bar_index,
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

    dow_snapshots_by_key: dict[ObservationContextKey, object] = {}
    raw_events_by_key: dict[ObservationContextKey, object] = {}
    raw_pivots_by_key: dict[ObservationContextKey, object] = {}
    observation_dates_by_ticker: dict[str, set[str]] = {}
    candidate_context_dates_by_ticker: dict[str, set[str]] = {}
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
        raw_events_by_key[key] = raw_events
        raw_pivots_by_key[key] = raw_pivots
        observation_dates_by_ticker.setdefault(observation.ticker, set()).add(
            observation.signal_confirmed_as_of_date
        )
        candidate_dates = candidate_context_dates_by_ticker.setdefault(observation.ticker, set())
        candidate_dates.add(observation.signal_confirmed_as_of_date)
        candidate_dates.update(event.confirmed_as_of_date for event in raw_events)
        candidate_dates.update(pivot.confirmed_as_of_date for pivot in raw_pivots)

    bar_indexes = {
        ticker: build_context_aware_bar_index(
            conn,
            ticker,
            timeframe,
            sorted(observation_dates_by_ticker.get(ticker, set())),
            sorted(candidate_context_dates_by_ticker.get(ticker, set())),
            max_lookback_bars=MAX_BAR_INDEX_LOOKBACK_BARS,
        )
        for ticker in sorted(observation_dates_by_ticker)
    }

    events_by_key: dict[ObservationContextKey, object] = {}
    pivots_by_key: dict[ObservationContextKey, object] = {}
    for key, raw_events in raw_events_by_key.items():
        ticker, _, observation_confirmed_as_of_date = key
        bar_index = bar_indexes.get(ticker)
        events_by_key[key] = assign_event_bar_distances(
            raw_events,
            observation_confirmed_as_of_date,
            bar_index,
        )
    for key, raw_pivots in raw_pivots_by_key.items():
        ticker, _, observation_confirmed_as_of_date = key
        bar_index = bar_indexes.get(ticker)
        pivots_by_key[key] = assign_pivot_bar_distances(
            raw_pivots,
            observation_confirmed_as_of_date,
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
