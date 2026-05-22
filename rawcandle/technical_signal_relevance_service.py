from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from time import perf_counter
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


@dataclass
class TechnicalSignalRelevanceTickerProfile:
    ticker: str
    seconds: float
    observations: int
    records: int


@dataclass
class TechnicalSignalRelevanceProfile:
    ticker_count: int = 0
    observations_seen: int = 0
    records_written: int = 0
    candlestick_observation_count: int = 0
    divergence_observation_count: int = 0
    read_candlestick_observations_calls: int = 0
    read_divergence_observations_calls: int = 0
    read_dow_snapshot_calls: int = 0
    read_dow_events_calls: int = 0
    read_dow_pivots_calls: int = 0
    read_bar_dates_calls: int = 0
    build_bar_index_calls: int = 0
    total_seconds: float = 0.0
    read_observations_seconds: float = 0.0
    read_dow_context_seconds: float = 0.0
    bar_index_seconds: float = 0.0
    classification_seconds: float = 0.0
    persistence_seconds: float = 0.0
    tickers_with_observations: int = 0
    max_observations_per_ticker: int = 0
    avg_observations_per_ticker: float = 0.0
    slowest_tickers: tuple[TechnicalSignalRelevanceTickerProfile, ...] = ()
    _ticker_seconds: dict[str, float] = field(default_factory=dict)
    _ticker_observations: dict[str, int] = field(default_factory=dict)

    def finalize(
        self,
        *,
        normalized_tickers: list[str],
        batch_summary: TechnicalSignalRelevanceBatchSummary,
    ) -> None:
        self.ticker_count = len(normalized_tickers)
        self.observations_seen = batch_summary.observations_seen
        self.records_written = batch_summary.records_written
        observed_tickers = sorted(
            ticker for ticker, count in self._ticker_observations.items() if count > 0
        )
        self.tickers_with_observations = len(observed_tickers)
        if observed_tickers:
            observation_counts = [self._ticker_observations[ticker] for ticker in observed_tickers]
            self.max_observations_per_ticker = max(observation_counts)
            self.avg_observations_per_ticker = sum(observation_counts) / len(observation_counts)
        slowest = [
            TechnicalSignalRelevanceTickerProfile(
                ticker=ticker,
                seconds=self._ticker_seconds.get(ticker, 0.0),
                observations=self._ticker_observations.get(ticker, 0),
                records=self._ticker_observations.get(ticker, 0),
            )
            for ticker in normalized_tickers
            if self._ticker_seconds.get(ticker, 0.0) > 0 or self._ticker_observations.get(ticker, 0) > 0
        ]
        self.slowest_tickers = tuple(
            sorted(
                slowest,
                key=lambda item: (-item.seconds, item.ticker),
            )[:10]
        )

    def to_summary_dict(self) -> dict[str, object]:
        summary: dict[str, object] = {
            "technical_relevance_profile.ticker_count": self.ticker_count,
            "technical_relevance_profile.observations_seen": self.observations_seen,
            "technical_relevance_profile.records_written": self.records_written,
            "technical_relevance_profile.candlestick_observation_count": self.candlestick_observation_count,
            "technical_relevance_profile.divergence_observation_count": self.divergence_observation_count,
            "technical_relevance_profile.read_candlestick_observations_calls": self.read_candlestick_observations_calls,
            "technical_relevance_profile.read_divergence_observations_calls": self.read_divergence_observations_calls,
            "technical_relevance_profile.read_dow_snapshot_calls": self.read_dow_snapshot_calls,
            "technical_relevance_profile.read_dow_events_calls": self.read_dow_events_calls,
            "technical_relevance_profile.read_dow_pivots_calls": self.read_dow_pivots_calls,
            "technical_relevance_profile.read_bar_dates_calls": self.read_bar_dates_calls,
            "technical_relevance_profile.build_bar_index_calls": self.build_bar_index_calls,
            "technical_relevance_profile.total_seconds": f"{self.total_seconds:.3f}",
            "technical_relevance_profile.read_observations_seconds": f"{self.read_observations_seconds:.3f}",
            "technical_relevance_profile.read_dow_context_seconds": f"{self.read_dow_context_seconds:.3f}",
            "technical_relevance_profile.bar_index_seconds": f"{self.bar_index_seconds:.3f}",
            "technical_relevance_profile.classification_seconds": f"{self.classification_seconds:.3f}",
            "technical_relevance_profile.persistence_seconds": f"{self.persistence_seconds:.3f}",
            "technical_relevance_profile.tickers_with_observations": self.tickers_with_observations,
            "technical_relevance_profile.max_observations_per_ticker": self.max_observations_per_ticker,
            "technical_relevance_profile.avg_observations_per_ticker": f"{self.avg_observations_per_ticker:.3f}",
        }
        for index, item in enumerate(self.slowest_tickers, start=1):
            summary[f"technical_relevance_profile.slowest_ticker.{index}"] = (
                f"{item.ticker}|seconds={item.seconds:.3f}|observations={item.observations}|records={item.records}"
            )
        return summary


def format_technical_relevance_profile_summary_lines(summary: dict[str, object]) -> list[str]:
    lines: list[str] = []
    ordered_keys = (
        "technical_relevance_profile.ticker_count",
        "technical_relevance_profile.observations_seen",
        "technical_relevance_profile.records_written",
        "technical_relevance_profile.candlestick_observation_count",
        "technical_relevance_profile.divergence_observation_count",
        "technical_relevance_profile.read_candlestick_observations_calls",
        "technical_relevance_profile.read_divergence_observations_calls",
        "technical_relevance_profile.read_dow_snapshot_calls",
        "technical_relevance_profile.read_dow_events_calls",
        "technical_relevance_profile.read_dow_pivots_calls",
        "technical_relevance_profile.read_bar_dates_calls",
        "technical_relevance_profile.build_bar_index_calls",
        "technical_relevance_profile.total_seconds",
        "technical_relevance_profile.read_observations_seconds",
        "technical_relevance_profile.read_dow_context_seconds",
        "technical_relevance_profile.bar_index_seconds",
        "technical_relevance_profile.classification_seconds",
        "technical_relevance_profile.persistence_seconds",
        "technical_relevance_profile.tickers_with_observations",
        "technical_relevance_profile.max_observations_per_ticker",
        "technical_relevance_profile.avg_observations_per_ticker",
    )
    for key in ordered_keys:
        if key in summary:
            lines.append(f"SUMMARY {key}={summary[key]}")
    slow_keys = sorted(
        (key for key in summary if key.startswith("technical_relevance_profile.slowest_ticker.")),
        key=lambda key: int(key.rsplit(".", 1)[1]),
    )
    for key in slow_keys:
        lines.append(f"SUMMARY {key}={summary[key]}")
    return lines


def run_technical_signal_relevance_for_tickers(
    conn: sqlite3.Connection,
    tickers: Iterable[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    run_id: str,
    created_at_utc: str,
    config: TechnicalSignalRelevanceConfig | None = None,
    profile: TechnicalSignalRelevanceProfile | None = None,
) -> TechnicalSignalRelevanceBatchSummary:
    total_start = perf_counter()
    resolved_config = config or TechnicalSignalRelevanceConfig()
    normalized_tickers = _normalize_requested_tickers(tickers)
    if profile is not None:
        profile.ticker_count = len(normalized_tickers)

    observations = []
    for ticker in normalized_tickers:
        ticker_start = perf_counter()
        if profile is not None:
            profile.read_candlestick_observations_calls += 1
        read_candlestick_start = perf_counter()
        candlestick_observations = read_candlestick_observations(
            conn,
            ticker,
            timeframe,
            start_date,
            end_date,
        )
        if profile is not None:
            profile.read_observations_seconds += perf_counter() - read_candlestick_start
            profile.candlestick_observation_count += len(candlestick_observations)
        observations.extend(candlestick_observations)
        if profile is not None:
            profile.read_divergence_observations_calls += 1
        read_divergence_start = perf_counter()
        divergence_observations = read_divergence_observations(
            conn,
            ticker,
            timeframe,
            start_date,
            end_date,
        )
        if profile is not None:
            profile.read_observations_seconds += perf_counter() - read_divergence_start
            profile.divergence_observation_count += len(divergence_observations)
            profile._ticker_observations[ticker] = len(candlestick_observations) + len(divergence_observations)
            profile._ticker_seconds[ticker] = perf_counter() - ticker_start
        observations.extend(divergence_observations)

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
        context_start = perf_counter()
        if profile is not None:
            profile.read_dow_snapshot_calls += 1
        dow_snapshots_by_key[key] = read_dow_snapshot(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        if profile is not None:
            profile.read_dow_events_calls += 1
        raw_events = read_dow_events(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        if profile is not None:
            profile.read_dow_pivots_calls += 1
        raw_pivots = read_dow_pivots(
            conn,
            observation.ticker,
            observation.timeframe,
            observation.signal_confirmed_as_of_date,
        )
        if profile is not None:
            context_elapsed = perf_counter() - context_start
            profile.read_dow_context_seconds += context_elapsed
            profile._ticker_seconds[observation.ticker] = (
                profile._ticker_seconds.get(observation.ticker, 0.0) + context_elapsed
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

    bar_indexes = {}
    for ticker in sorted(observation_dates_by_ticker):
        bar_index_start = perf_counter()
        if profile is not None:
            profile.read_bar_dates_calls += 1
            profile.build_bar_index_calls += 1
        bar_indexes[ticker] = build_context_aware_bar_index(
            conn,
            ticker,
            timeframe,
            sorted(observation_dates_by_ticker.get(ticker, set())),
            sorted(candidate_context_dates_by_ticker.get(ticker, set())),
            max_lookback_bars=MAX_BAR_INDEX_LOOKBACK_BARS,
        )
        if profile is not None:
            bar_index_elapsed = perf_counter() - bar_index_start
            profile.bar_index_seconds += bar_index_elapsed
            profile._ticker_seconds[ticker] = profile._ticker_seconds.get(ticker, 0.0) + bar_index_elapsed

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

    summary = run_technical_signal_relevance_batch(
        conn=conn,
        run_id=run_id,
        observations=observations,
        dow_snapshots_by_key=dow_snapshots_by_key,
        events_by_key=events_by_key,
        pivots_by_key=pivots_by_key,
        config=resolved_config,
        created_at_utc=created_at_utc,
        profile=profile,
    )
    if profile is not None:
        profile.total_seconds = perf_counter() - total_start
        profile.finalize(
            normalized_tickers=normalized_tickers,
            batch_summary=summary,
        )
    return summary


__all__ = [
    "TechnicalSignalRelevanceProfile",
    "TechnicalSignalRelevanceTickerProfile",
    "format_technical_relevance_profile_summary_lines",
    "run_technical_signal_relevance_for_tickers",
]
