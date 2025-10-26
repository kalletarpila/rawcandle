from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Sequence, TypeVar

T = TypeVar("T")


def parse_ui_date(value: str) -> _dt.date:
    """Parse Finnish-style date inputs (dd.mm.yyyy)."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Päivämäärä puuttuu")
    try:
        return _dt.datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError as exc:
        raise ValueError(f"Virheellinen päivämäärä '{value}', käytä muotoa pp.kk.vvvv") from exc


def parse_iso_date(value: str) -> _dt.date:
    """Parse YYYY-MM-DD strings coming from the database."""
    return _dt.date.fromisoformat(value)


def ensure_upper_ticker(value: str) -> str:
    """Normalise tickers to uppercase without surrounding whitespace."""
    return (value or "").strip().upper()


def daterange(start: _dt.date, end: _dt.date) -> Iterator[_dt.date]:
    """Yield every date from start to end (inclusive)."""
    if end < start:
        return
    delta = (end - start).days
    for offset in range(delta + 1):
        yield start + _dt.timedelta(days=offset)


def previous_or_none(items: Sequence[_dt.date], date_value: _dt.date) -> Optional[_dt.date]:
    """Return the greatest entry <= date_value."""
    for idx in range(len(items) - 1, -1, -1):
        candidate = items[idx]
        if candidate <= date_value:
            return candidate
    return None


def next_after(items: Sequence[_dt.date], date_value: _dt.date) -> Optional[_dt.date]:
    """Return the smallest entry strictly greater than date_value."""
    for candidate in items:
        if candidate > date_value:
            return candidate
    return None


def take_while_date(items: Sequence[_dt.date], start: _dt.date, end: _dt.date) -> list[_dt.date]:
    """Return dates between start and end inclusive from a sorted list."""
    return [d for d in items if start <= d <= end]


def mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)

