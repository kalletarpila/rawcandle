from __future__ import annotations

from typing import Sequence

from pages.index_page.trend_models import TrendChain, TrendSnapshot
from pages.index_page.trend_utils import SeriesPoint
from pages.index_page.trend_snapshot import compute_snapshot as _compute_snapshot
from pages.index_page.trend_chains import compute_chains as _compute_chains


def compute_snapshot(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    k: int,
) -> TrendSnapshot:
    return _compute_snapshot(series, object_type, object_name, lookback, k)


def compute_chains(
    series: Sequence[SeriesPoint],
    object_type: str,
    object_name: str,
    lookback: int,
    k: int,
) -> list[TrendChain]:
    return _compute_chains(series, object_type, object_name, lookback, k)
