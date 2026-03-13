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


def compute_divergence_for_date(
    dates: List[str],
    closes: List[float],
    rsi_values: List[Optional[float]],
    idx: int,
) -> Dict[str, Any]:
    close_t = closes[idx]
    rsi_t = rsi_values[idx]

    if idx + 1 < MIN_HISTORY_DAYS or rsi_t is None or close_t <= 0.0:
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

    results: List[Dict[str, Any]] = []
    for idx in range(len(work_df)):
        date_value = dates[idx]
        if start_date is not None and date_value < start_date:
            continue
        results.append(compute_divergence_for_date(dates, closes, rsi_values, idx))

    return results
