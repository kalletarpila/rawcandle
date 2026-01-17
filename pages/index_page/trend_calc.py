from __future__ import annotations

from typing import Sequence

import datetime as dt

from pages.index_page.trend_models import TrendChain, TrendSnapshot
from pages.index_page.trend_utils import SeriesPoint
from pages.index_page.trend_snapshot import compute_snapshot as _compute_snapshot


def compute_snapshot(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    k: int,
) -> TrendSnapshot:
    return _compute_snapshot(series, object_type, object_name, lookback, k)


def compute_structural_relevance(end_date: dt.date, today: dt.date | None = None) -> str:
    if today is None:
        today = dt.date.today()
    days = (today - end_date).days
    if days <= 20:
        return "ACTIVE"
    elif days <= 60:
        return "FADING"
    else:
        return "HISTORICAL"


def compute_chains(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    pivot_window: int,
) -> list[TrendChain]:
    # local import to avoid circular dependency
    from pages.index_page.trend_chains import compute_chains as _compute_chains

    return _compute_chains(series, object_type, object_name, lookback, pivot_window)
