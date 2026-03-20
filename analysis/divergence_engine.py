from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .divergence_v1 import (
    LOOKBACK_DAYS,
    MIN_HISTORY_DAYS,
    RSI_PERIOD,
    compute_bearish_candidate_strength,
    compute_bullish_candidate_strength,
    compute_rsi_wilder,
    is_rolling_high_candidate,
    is_rolling_low_candidate,
)

PIVOT_RADIUS_R2 = 2
PIVOT_RADIUS_R3 = 3
MIN_V2_PIVOT_GAP = 5
MAX_V2_PIVOT_GAP = 30


def compute_divergence_for_date(
    dates: List[str],
    closes: List[float],
    rsi_values: List[Optional[float]],
    idx: int,
) -> Dict[str, Any]:
    close_t = closes[idx]
    rsi_t = rsi_values[idx]

    if idx + 1 < MIN_HISTORY_DAYS:
        return {
            "date": dates[idx],
            "bullish_strength": 0.0,
            "bearish_strength": 0.0,
            "rsi": None,
        }

    if rsi_t is None or close_t <= 0.0:
        return {
            "date": dates[idx],
            "bullish_strength": 0.0,
            "bearish_strength": 0.0,
            "rsi": rsi_t,
        }

    bullish_best = 0.0
    bearish_best = 0.0

    lookback_start = max(0, idx - LOOKBACK_DAYS)
    for prev_idx in range(lookback_start, idx):
        close_p = closes[prev_idx]
        rsi_p = rsi_values[prev_idx]

        if rsi_p is None or close_p <= 0.0:
            continue

        if is_rolling_low_candidate(closes, prev_idx):
            if close_t < close_p and rsi_t > rsi_p:
                bullish_best = max(
                    bullish_best,
                    compute_bullish_candidate_strength(close_p, close_t, rsi_p, rsi_t),
                )

        if is_rolling_high_candidate(closes, prev_idx):
            if close_t > close_p and rsi_t < rsi_p:
                bearish_best = max(
                    bearish_best,
                    compute_bearish_candidate_strength(close_p, close_t, rsi_p, rsi_t),
                )

    return {
        "date": dates[idx],
        "bullish_strength": bullish_best,
        "bearish_strength": bearish_best,
        "rsi": rsi_t,
    }


def _is_valid_pivot_index(size: int, idx: int, radius: int) -> bool:
    return idx - radius >= 0 and idx + radius < size


def _window_has_null(values: List[Optional[float]], start: int, end: int) -> bool:
    for idx in range(start, end + 1):
        value = values[idx]
        if value is None or pd.isna(value):
            return True
    return False


def _compute_raw_pivot_candidates(
    values: List[Optional[float]],
    *,
    radius: int,
    is_low: bool,
) -> List[bool]:
    size = len(values)
    raw = [False] * size
    for idx in range(size):
        if not _is_valid_pivot_index(size, idx, radius):
            continue
        if _window_has_null(values, idx - radius, idx + radius):
            continue
        window = values[idx - radius : idx + radius + 1]
        if is_low:
            raw[idx] = values[idx] == min(window)
        else:
            raw[idx] = values[idx] == max(window)
    return raw


def _collapse_tied_clusters(raw_candidates: List[bool], values: List[Optional[float]]) -> List[bool]:
    final = [False] * len(raw_candidates)
    idx = 0
    while idx < len(raw_candidates):
        if not raw_candidates[idx]:
            idx += 1
            continue
        cluster_end = idx
        while (
            cluster_end + 1 < len(raw_candidates)
            and raw_candidates[cluster_end + 1]
            and values[cluster_end + 1] == values[idx]
        ):
            cluster_end += 1
        final[cluster_end] = True
        idx = cluster_end + 1
    return final


def _compute_v2_event_flags_for_radius(
    dates: List[str],
    lows: List[Optional[float]],
    highs: List[Optional[float]],
    rsi_values: List[Optional[float]],
    *,
    radius: int,
) -> tuple[
    List[int],
    List[int],
    List[Optional[int]],
    List[Optional[float]],
    List[Optional[str]],
]:
    size = len(rsi_values)
    bullish_flags = [0] * size
    bearish_flags = [0] * size
    pivot_gaps: List[Optional[int]] = [None] * size
    pivot_drop_pcts: List[Optional[float]] = [None] * size
    pivot2_dates: List[Optional[str]] = [None] * size

    if not lows or not highs or len(lows) != size or len(highs) != size:
        return bullish_flags, bearish_flags, pivot_gaps, pivot_drop_pcts, pivot2_dates

    raw_price_pivot_lows = _compute_raw_pivot_candidates(lows, radius=radius, is_low=True)
    raw_price_pivot_highs = _compute_raw_pivot_candidates(highs, radius=radius, is_low=False)
    raw_rsi_pivot_lows = _compute_raw_pivot_candidates(
        rsi_values, radius=radius, is_low=True
    )
    raw_rsi_pivot_highs = _compute_raw_pivot_candidates(
        rsi_values, radius=radius, is_low=False
    )

    final_price_pivot_lows = _collapse_tied_clusters(raw_price_pivot_lows, lows)
    final_price_pivot_highs = _collapse_tied_clusters(raw_price_pivot_highs, highs)
    final_rsi_pivot_lows = _collapse_tied_clusters(raw_rsi_pivot_lows, rsi_values)
    final_rsi_pivot_highs = _collapse_tied_clusters(raw_rsi_pivot_highs, rsi_values)

    price_pivot_lows = [idx for idx, is_pivot in enumerate(final_price_pivot_lows) if is_pivot]
    price_pivot_highs = [idx for idx, is_pivot in enumerate(final_price_pivot_highs) if is_pivot]

    for pivot_idx in range(1, len(price_pivot_lows)):
        p1 = price_pivot_lows[pivot_idx - 1]
        p2 = price_pivot_lows[pivot_idx]
        pivot_gap = p2 - p1
        if pivot_gap < MIN_V2_PIVOT_GAP or pivot_gap > MAX_V2_PIVOT_GAP:
            continue

        if lows[p2] >= lows[p1]:
            continue
        if rsi_values[p1] is None:
            continue

        anchor_rsi = rsi_values[p1]
        pivot_drop_pct = ((lows[p1] - lows[p2]) / lows[p1]) * 100.0
        for r2 in [p2 - 1, p2, p2 + 1]:
            if r2 < 0 or r2 >= size:
                continue
            if not final_rsi_pivot_lows[r2]:
                continue
            if rsi_values[r2] is None:
                continue
            if rsi_values[r2] <= anchor_rsi:
                continue
            event_idx = r2 + radius
            if event_idx >= size:
                continue
            bullish_flags[event_idx] = 1
            pivot_gaps[event_idx] = pivot_gap
            pivot_drop_pcts[event_idx] = pivot_drop_pct
            pivot2_dates[event_idx] = dates[p2]
            break

    for pivot_idx in range(1, len(price_pivot_highs)):
        p1 = price_pivot_highs[pivot_idx - 1]
        p2 = price_pivot_highs[pivot_idx]
        pivot_gap = p2 - p1
        if pivot_gap < MIN_V2_PIVOT_GAP or pivot_gap > MAX_V2_PIVOT_GAP:
            continue

        if highs[p2] <= highs[p1]:
            continue
        if rsi_values[p1] is None:
            continue

        anchor_rsi = rsi_values[p1]
        pivot_drop_pct = ((highs[p2] - highs[p1]) / highs[p1]) * 100.0
        for r2 in [p2 - 1, p2, p2 + 1]:
            if r2 < 0 or r2 >= size:
                continue
            if not final_rsi_pivot_highs[r2]:
                continue
            if rsi_values[r2] is None:
                continue
            if rsi_values[r2] >= anchor_rsi:
                continue
            event_idx = r2 + radius
            if event_idx >= size:
                continue
            bearish_flags[event_idx] = 1
            pivot_gaps[event_idx] = pivot_gap
            pivot_drop_pcts[event_idx] = pivot_drop_pct
            pivot2_dates[event_idx] = dates[p2]
            break

    return bullish_flags, bearish_flags, pivot_gaps, pivot_drop_pcts, pivot2_dates


def compute_divergence_series(
    df: pd.DataFrame,
    *,
    start_date: str | None = None,
) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    work_df = df.copy()
    work_df["pvm"] = work_df["pvm"].astype(str)
    work_df["close"] = pd.to_numeric(work_df["close"], errors="coerce")
    work_df = work_df.dropna(subset=["pvm", "close"]).sort_values("pvm").reset_index(drop=True)

    dates = work_df["pvm"].tolist()
    closes = [float(value) for value in work_df["close"].tolist()]
    rsi_values = compute_rsi_wilder(closes, period=RSI_PERIOD)
    lows = (
        pd.to_numeric(work_df["low"], errors="coerce").tolist()
        if "low" in work_df.columns
        else []
    )
    highs = (
        pd.to_numeric(work_df["high"], errors="coerce").tolist()
        if "high" in work_df.columns
        else []
    )
    (
        bullish_event_flags_r2,
        bearish_event_flags_r2,
        pivot_gaps_r2,
        pivot_drop_pcts_r2,
        pivot2_dates_r2,
    ) = _compute_v2_event_flags_for_radius(
        dates, lows, highs, rsi_values, radius=PIVOT_RADIUS_R2
    )
    (
        bullish_event_flags_r3,
        bearish_event_flags_r3,
        pivot_gaps_r3,
        pivot_drop_pcts_r3,
        pivot2_dates_r3,
    ) = _compute_v2_event_flags_for_radius(
        dates, lows, highs, rsi_values, radius=PIVOT_RADIUS_R3
    )

    results: List[Dict[str, Any]] = []
    for idx in range(len(work_df)):
        date_value = dates[idx]
        if start_date is not None and date_value < start_date:
            continue
        row = compute_divergence_for_date(dates, closes, rsi_values, idx)
        row["is_bullish_divergence_r2"] = bullish_event_flags_r2[idx]
        row["is_bearish_divergence_r2"] = bearish_event_flags_r2[idx]
        row["is_bullish_divergence_r3"] = bullish_event_flags_r3[idx]
        row["is_bearish_divergence_r3"] = bearish_event_flags_r3[idx]
        row["pivot_gap_r2"] = pivot_gaps_r2[idx]
        row["pivot_drop_pct_r2"] = pivot_drop_pcts_r2[idx]
        row["pivot2_date_r2"] = pivot2_dates_r2[idx]
        row["pivot_gap_r3"] = pivot_gaps_r3[idx]
        row["pivot_drop_pct_r3"] = pivot_drop_pcts_r3[idx]
        row["pivot2_date_r3"] = pivot2_dates_r3[idx]
        row["pivot_gap"] = pivot_gaps_r2[idx]
        row["pivot_drop_pct"] = pivot_drop_pcts_r2[idx]
        # Legacy compatibility: generic fields mirror radius-2 semantics.
        row["is_bullish_divergence"] = bullish_event_flags_r2[idx]
        row["is_bearish_divergence"] = bearish_event_flags_r2[idx]
        results.append(row)

    return results
