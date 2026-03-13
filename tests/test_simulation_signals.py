import datetime as dt

from simu.db import AnalysisEvent
from simu.signals import resolve_signals


class DummyRepo:
    def __init__(self, events=None, divergences=None):
        self._events = events or []
        self._divergences = divergences or []

    def fetch_events(self, ticker, start_date, end_date):
        return list(self._events)

    def fetch_divergences(self, ticker, start_date, end_date):
        return list(self._divergences)


def _event(pattern_key: str, date: dt.date, strength: float = 0.5) -> AnalysisEvent:
    return AnalysisEvent(
        ticker="AAA",
        date=date,
        pattern_key=pattern_key,
        raw_pattern=pattern_key,
        strength=strength,
    )


def test_combo_requirement_filters_when_divergence_missing():
    date = dt.date(2024, 1, 2)
    repo = DummyRepo(events=[_event("hammer", date, 0.9)])

    result = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["hammer"],
        min_strength=0.1,
        require_combo=True,
    )

    assert result == {}


def test_combo_requirement_keeps_best_candlestick_with_divergence():
    date = dt.date(2024, 1, 2)
    repo = DummyRepo(
        events=[_event("hammer", date, 0.9)],
        divergences=[_event("bullish_divergence", date, 1.2)],
    )

    result = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["hammer", "bullish_divergence"],
        min_strength=0.1,
        require_combo=True,
    )

    assert date in result
    assert result[date].pattern_key == "hammer"


def test_downtrend_allowed_with_combo_requirement():
    date = dt.date(2024, 1, 5)
    repo = DummyRepo(
        events=[_event("downtrend", date, 1.0)],
        divergences=[_event("bullish_divergence", date, 1.1)],
    )

    # Ilman combo-vaatimusta valitaan divergenssi (downtrend ohitetaan).
    no_combo = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["downtrend", "bullish_divergence"],
        min_strength=0.1,
        require_combo=False,
    )
    assert no_combo[date].pattern_key == "bullish_divergence"

    with_combo = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["downtrend", "bullish_divergence"],
        min_strength=0.1,
        require_combo=True,
    )
    assert date in with_combo
    assert with_combo[date].pattern_key == "downtrend"


def test_combo_accepts_divergence_from_previous_days():
    date = dt.date(2024, 1, 10)
    repo = DummyRepo(
        events=[_event("hammer", date, 0.8)],
        divergences=[_event("bullish_divergence", date - dt.timedelta(days=2), 1.1)],
    )

    result = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["hammer", "bullish_divergence"],
        min_strength=0.1,
        require_combo=True,
    )

    assert date in result
    assert result[date].pattern_key == "hammer"


def test_combo_rejects_divergence_outside_window():
    date = dt.date(2024, 1, 10)
    repo = DummyRepo(
        events=[_event("hammer", date, 0.8)],
        divergences=[_event("bullish_divergence", date - dt.timedelta(days=5), 1.1)],
    )

    result = resolve_signals(
        repo,
        "AAA",
        dt.date(2024, 1, 1),
        dt.date(2024, 12, 31),
        ["hammer", "bullish_divergence"],
        min_strength=0.1,
        require_combo=True,
    )

    assert result == {}
