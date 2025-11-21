from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def add_same_day_aggregate_features(
    df_raw: pd.DataFrame,
    df_dedup: pd.DataFrame,
    pattern_column: str,
) -> pd.DataFrame:
    """
    Liittää saman päivän aggregaatit deduplikoituun DataFrameen.
    """
    if df_dedup.empty or df_raw.empty:
        return _ensure_aggregate_columns(df_dedup)

    if "ticker" not in df_raw.columns or "date" not in df_raw.columns:
        return _ensure_aggregate_columns(df_dedup)

    work = df_raw.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["ticker", "date"])
    if work.empty:
        return _ensure_aggregate_columns(df_dedup)

    work["ticker"] = work["ticker"].astype(str)
    patterns = work.get(pattern_column)
    if patterns is None:
        return _ensure_aggregate_columns(df_dedup)
    work["_pattern"] = pd.to_numeric(patterns, errors="coerce").fillna(0).astype(int)
    work["_is_signal"] = work["_pattern"] != 0
    work["_is_candle"] = work["_pattern"].isin({1, 2, 3, 4, 5, 6})
    work["_strength"] = pd.to_numeric(work.get("vahvuus"), errors="coerce")
    if "is_divergence_today" in work.columns:
        bd_mask = pd.to_numeric(
            work["is_divergence_today"], errors="coerce"
        ).fillna(0) == 1
    else:
        bd_mask = pd.Series(False, index=work.index)
    work["_is_bd"] = bd_mask | (work["_pattern"] == 7)

    grouped = work.groupby(["ticker", "date"], sort=False)
    records = []
    for (ticker, date), group in grouped:
        signal_mask = group["_is_signal"]
        signal_patterns = group.loc[signal_mask, "_pattern"]
        signal_strengths = group.loc[signal_mask, "_strength"].dropna().to_numpy()
        num_signals = int(signal_mask.sum())
        unique_patterns = (
            int(signal_patterns[signal_patterns != 0].nunique())
            if num_signals
            else 0
        )
        max_strength = (
            float(signal_strengths.max()) if signal_strengths.size else float(0.0)
        )
        sum_strength = (
            float(signal_strengths.sum()) if signal_strengths.size else float(0.0)
        )
        if signal_strengths.size >= 2:
            sorted_vals = np.sort(signal_strengths)
            second_best = float(sorted_vals[-2])
        else:
            second_best = float(0.0)
        has_cluster = int(num_signals >= 2)
        has_reversal_cluster = int(
            bool(group["_is_bd"].any() and group["_is_candle"].any())
        )
        records.append(
            {
                "ticker": ticker,
                "date": date,
                "num_signals_same_day": num_signals,
                "num_unique_patterns_same_day": unique_patterns,
                "max_signal_strength_same_day": max_strength,
                "second_best_strength_same_day": second_best,
                "sum_signal_strength_same_day": sum_strength,
                "has_same_day_cluster": has_cluster,
                "has_same_day_reversal_cluster": has_reversal_cluster,
            }
        )

    aggregates = pd.DataFrame(records)
    if aggregates.empty:
        return _ensure_aggregate_columns(df_dedup)

    out = df_dedup.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["ticker"] = out["ticker"].astype(str)
    out = out.merge(
        aggregates,
        on=["ticker", "date"],
        how="left",
        sort=False,
    )
    return _ensure_aggregate_columns(out)


AGGREGATE_COLUMNS = [
    "num_signals_same_day",
    "num_unique_patterns_same_day",
    "max_signal_strength_same_day",
    "second_best_strength_same_day",
    "sum_signal_strength_same_day",
    "has_same_day_cluster",
    "has_same_day_reversal_cluster",
]


def _ensure_aggregate_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in AGGREGATE_COLUMNS:
        if col not in out.columns:
            if col.startswith("has_"):
                out[col] = 0
            else:
                out[col] = 0.0
        else:
            if col.startswith("has_"):
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
            else:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out
