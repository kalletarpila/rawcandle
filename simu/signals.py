from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from . import config

DIV_KEYS = set(config.DIVERGENCE_KEYS)
MAX_DIVERGENCE_LOOKBACK_DAYS = 3

from .db import AnalysisEvent, AnalysisRepository


@dataclass(frozen=True)
class SelectedSignal:
    date: _dt.date
    pattern_key: str
    raw_pattern: str
    strength: float


def canonicalise_selection(selected: Iterable[str]) -> List[str]:
    """Return a list of known canonical pattern keys from UI selections."""
    result: List[str] = []
    for key in selected:
        key_norm = (key or "").strip().lower()
        if key_norm in config.PATTERN_MAP:
            result.append(key_norm)
    return result


def pattern_label(pattern_key: str) -> str:
    definition = config.PATTERN_MAP.get(pattern_key)
    return definition.label if definition else pattern_key


def _choose_event(events: List[AnalysisEvent]) -> SelectedSignal:
    best_index = -1
    best_strength = float("-inf")
    best_event: AnalysisEvent | None = None
    for idx, event in enumerate(events):
        strength = float(event.strength or 0.0)
        if strength > best_strength or (strength == best_strength and best_index == -1):
            best_strength = strength
            best_index = idx
            best_event = event
    assert best_event is not None
    return SelectedSignal(
        date=best_event.date,
        pattern_key=best_event.pattern_key,
        raw_pattern=best_event.raw_pattern,
        strength=float(best_strength),
    )


def resolve_signals(
    repo: AnalysisRepository,
    ticker: str,
    start_date: _dt.date,
    end_date: _dt.date,
    selected_patterns: Sequence[str],
    min_strength: float,
    require_combo: bool = False,
) -> Dict[_dt.date, SelectedSignal]:
    """Fetch and filter t0 signals for the given ticker and pattern selection."""
    selected = canonicalise_selection(selected_patterns)
    if not selected:
        return {}

    selected_set = set(selected)
    candle_keys = {p for p in selected_set if p not in DIV_KEYS}
    has_divergences = bool(selected_set & DIV_KEYS)
    has_candlestick_patterns = bool(candle_keys)

    if require_combo and (not candle_keys or not has_divergences):
        return {}

    downtrend_only = set(selected) == {"downtrend"}

    raw_events: List[AnalysisEvent] = []
    if has_candlestick_patterns:
        raw_events.extend(repo.fetch_events(ticker, start_date, end_date))
    if has_divergences:
        raw_events.extend(repo.fetch_divergences(ticker, start_date, end_date))

    grouped: Dict[_dt.date, List[AnalysisEvent]] = {}
    candle_events: Dict[_dt.date, List[AnalysisEvent]] = {}
    divergence_dates: set[_dt.date] = set()

    for event in raw_events:
        key = event.pattern_key
        strength = float(event.strength or 0.0)
        if strength < min_strength:
            continue

        if key in DIV_KEYS:
            divergence_dates.add(event.date)
            if not require_combo and key in selected_set:
                grouped.setdefault(event.date, []).append(event)
            continue

        if key not in selected_set:
            continue

        if key == "downtrend" and not (
            downtrend_only or (require_combo and has_divergences)
        ):
            continue

        candle_events.setdefault(event.date, []).append(event)
        if not require_combo:
            grouped.setdefault(event.date, []).append(event)

    selected_signals: Dict[_dt.date, SelectedSignal] = {}

    if require_combo:
        divergence_lookup = set(divergence_dates)

        def has_divergence_for(date_value: _dt.date) -> bool:
            for offset in range(0, MAX_DIVERGENCE_LOOKBACK_DAYS + 1):
                check_date = date_value - _dt.timedelta(days=offset)
                if check_date in divergence_lookup:
                    return True
            return False

        for date_value, candidates in candle_events.items():
            if not has_divergence_for(date_value):
                continue
            selected_signals[date_value] = _choose_event(candidates)
    else:
        for date_value, candidates in grouped.items():
            selected_signals[date_value] = _choose_event(candidates)

    return selected_signals
