from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from time import perf_counter
from typing import Iterable, Mapping, TypeVar

from .technical_signal_relevance import (
    NOISE,
    RELEVANT,
    WEAK_CONTEXT,
    TechnicalSignalDowSnapshot,
    TechnicalSignalEvent,
    TechnicalSignalObservation,
    TechnicalSignalPivot,
    TechnicalSignalRelevanceConfig,
    classify_relevance,
)
from .technical_signal_relevance_persistence import (
    build_relevance_run_row,
    build_relevance_stored_row,
    insert_relevance_records,
    insert_relevance_run,
)


ObservationContextKey = tuple[str, str] | tuple[str, str, str]
T = TypeVar("T")


@dataclass(frozen=True)
class TechnicalSignalRelevanceBatchSummary:
    run_id: str
    observations_seen: int
    records_written: int
    relevant_count: int
    weak_context_count: int
    noise_count: int
    unknown_signal_count: int
    missing_dow_context_count: int
    missing_bar_index_count: int


def _observation_sort_key(
    observation: TechnicalSignalObservation,
) -> tuple[str, str, str, str, str, str]:
    return (
        observation.ticker,
        observation.timeframe,
        observation.signal_confirmed_as_of_date,
        observation.signal_date,
        observation.signal_name,
        "" if observation.signal_source_id is None else observation.signal_source_id,
    )


def _context_key(observation: TechnicalSignalObservation) -> ObservationContextKey:
    return (observation.ticker, observation.timeframe)


def _observation_as_of_context_key(
    observation: TechnicalSignalObservation,
) -> tuple[str, str, str]:
    return (
        observation.ticker,
        observation.timeframe,
        observation.signal_confirmed_as_of_date,
    )


def _resolve_context_value(
    mapping: Mapping[ObservationContextKey, T],
    observation: TechnicalSignalObservation,
    default: T,
) -> T:
    observation_specific_key = _observation_as_of_context_key(observation)
    if observation_specific_key in mapping:
        return mapping[observation_specific_key]
    coarse_key = _context_key(observation)
    return mapping.get(coarse_key, default)


def run_technical_signal_relevance_batch(
    conn: sqlite3.Connection,
    run_id: str,
    observations: Iterable[TechnicalSignalObservation],
    dow_snapshots_by_key: Mapping[ObservationContextKey, TechnicalSignalDowSnapshot | None],
    events_by_key: Mapping[ObservationContextKey, list[TechnicalSignalEvent]],
    pivots_by_key: Mapping[ObservationContextKey, list[TechnicalSignalPivot]],
    config: TechnicalSignalRelevanceConfig,
    created_at_utc: str,
    profile: object | None = None,
) -> TechnicalSignalRelevanceBatchSummary:
    sorted_observations = sorted(list(observations), key=_observation_sort_key)
    run_row = build_relevance_run_row(
        run_id=run_id,
        config=config,
        created_at_utc=created_at_utc,
    )
    insert_run_start = perf_counter()
    insert_relevance_run(conn, run_row)
    if profile is not None:
        profile.persistence_seconds += perf_counter() - insert_run_start

    stored_rows = []
    relevant_count = 0
    weak_context_count = 0
    noise_count = 0
    unknown_signal_count = 0
    missing_dow_context_count = 0
    missing_bar_index_count = 0

    for observation in sorted_observations:
        classification_start = perf_counter()
        record = classify_relevance(
            observation,
            _resolve_context_value(dow_snapshots_by_key, observation, None),
            _resolve_context_value(events_by_key, observation, []),
            _resolve_context_value(pivots_by_key, observation, []),
            config=config,
        )
        if profile is not None:
            profile.classification_seconds += perf_counter() - classification_start
        stored_rows.append(
            build_relevance_stored_row(
                record,
                run_id=run_id,
                created_at_utc=created_at_utc,
            )
        )
        if record.relevance_class == RELEVANT:
            relevant_count += 1
        elif record.relevance_class == WEAK_CONTEXT:
            weak_context_count += 1
        elif record.relevance_class == NOISE:
            noise_count += 1
        if record.relevance_reason == "UNKNOWN_SIGNAL_NAME":
            unknown_signal_count += 1
        if "missing_dow_context=true" in record.rule_trace:
            missing_dow_context_count += 1
        if "missing_bar_index=true" in record.rule_trace:
            missing_bar_index_count += 1

    insert_records_start = perf_counter()
    insert_relevance_records(conn, stored_rows)
    if profile is not None:
        profile.persistence_seconds += perf_counter() - insert_records_start
    return TechnicalSignalRelevanceBatchSummary(
        run_id=run_id,
        observations_seen=len(sorted_observations),
        records_written=len(stored_rows),
        relevant_count=relevant_count,
        weak_context_count=weak_context_count,
        noise_count=noise_count,
        unknown_signal_count=unknown_signal_count,
        missing_dow_context_count=missing_dow_context_count,
        missing_bar_index_count=missing_bar_index_count,
    )


__all__ = [
    "ObservationContextKey",
    "TechnicalSignalRelevanceBatchSummary",
    "run_technical_signal_relevance_batch",
]
