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
        events_by_key[key] = read_dow_events(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        pivots_by_key[key] = read_dow_pivots(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
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
