from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from . import config
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
) -> Dict[_dt.date, SelectedSignal]:
    """Fetch and filter t0 signals for the given ticker and pattern selection."""
    selected = canonicalise_selection(selected_patterns)
    if not selected:
        return {}

    downtrend_only = set(selected) == {"downtrend"}
    selected_set = set(selected)

    # Check if divergences are selected
    has_divergences = (
        "bullish_divergence" in selected_set or "bearish_divergence" in selected_set
    )
    has_candlestick_patterns = any(
        p not in {"bullish_divergence", "bearish_divergence"} for p in selected_set
    )

    # Fetch candlestick pattern events
    raw_events: List[AnalysisEvent] = []
    if has_candlestick_patterns:
        raw_events.extend(repo.fetch_events(ticker, start_date, end_date))

    # Fetch divergence events
    if has_divergences:
        raw_events.extend(repo.fetch_divergences(ticker, start_date, end_date))

    grouped: Dict[_dt.date, List[AnalysisEvent]] = {}
    for event in raw_events:
        key = event.pattern_key
        if key not in selected_set:
            continue
        if key == "downtrend" and not downtrend_only:
            # downtrend allowed only when it is the sole selection
            continue
        strength = float(event.strength or 0.0)
        if strength < min_strength:
            continue
        grouped.setdefault(event.date, []).append(
            AnalysisEvent(
                ticker=event.ticker,
                date=event.date,
                pattern_key=event.pattern_key,
                raw_pattern=event.raw_pattern,
                strength=strength,
            )
        )

    selected_signals: Dict[_dt.date, SelectedSignal] = {}
    for date_value, candidates in grouped.items():
        selected_signals[date_value] = _choose_event(candidates)
    return selected_signals
