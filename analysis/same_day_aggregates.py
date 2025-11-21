from __future__ import annotations

import numpy as np
import pandas as pd


def add_same_day_aggregate_features(
    df_raw: pd.DataFrame,
    df_dedup: pd.DataFrame,
    pattern_col: str = "kynttila_koodi",
    strength_col: str = "vahvuus",
    ticker_col: str = "ticker",
    date_col: str = "date",
) -> pd.DataFrame:
    """
    Lisää saman päivän aggregaatit preprocess_signalsin deduplikoimaan DataFrameen.
    """
    if df_dedup.empty or df_raw.empty:
        return _ensure_aggregate_columns(df_dedup)

    if ticker_col not in df_raw.columns or date_col not in df_raw.columns:
        return _ensure_aggregate_columns(df_dedup)

    work = df_raw.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if work.empty:
        return _ensure_aggregate_columns(df_dedup)

    work[ticker_col] = work[ticker_col].astype(str)
    patterns = work.get(pattern_col)
    if patterns is None:
        return _ensure_aggregate_columns(df_dedup)
    work["_pattern"] = pd.to_numeric(patterns, errors="coerce").fillna(0).astype(int)
    if "is_divergence_today" in work.columns:
        bd_mask = (
            pd.to_numeric(work["is_divergence_today"], errors="coerce").fillna(0) == 1
        )
    else:
        bd_mask = pd.Series(False, index=work.index)
    work["_is_bd"] = bd_mask | (work["_pattern"] == 7)
    work["_is_signal"] = (work["_pattern"] != 0) | work["_is_bd"]
    work["_is_reversal"] = work["_pattern"].isin({1, 2, 3, 4, 5, 6, 7}) | work["_is_bd"]
    work["_strength"] = pd.to_numeric(work.get(strength_col), errors="coerce")

    grouped = work.groupby([ticker_col, date_col], sort=False)
    records = []
    for (ticker, date), group in grouped:
        signal_mask = group["_is_signal"]
        signal_strengths = group.loc[signal_mask, "_strength"].dropna().to_numpy()
        signal_count = int(signal_mask.sum())
        unique_patterns = int(group["_pattern"].nunique())
        max_strength = float(signal_strengths.max()) if signal_strengths.size else 0.0
        if signal_strengths.size >= 2:
            sorted_vals = np.sort(signal_strengths)
            second_best = float(sorted_vals[-2])
        else:
            second_best = 0.0
        has_reversal_cluster = int(group["_is_reversal"].sum() >= 2)
        records.append(
            {
                ticker_col: ticker,
                date_col: date,
                "same_day_signal_count": signal_count,
                "same_day_unique_patterns": unique_patterns,
                "same_day_max_strength": max_strength,
                "same_day_second_best_strength": second_best,
                "has_same_day_reversal_cluster": has_reversal_cluster,
            }
        )

    aggregates = pd.DataFrame(records)
    if aggregates.empty:
        return _ensure_aggregate_columns(df_dedup)

    out = df_dedup.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out[ticker_col] = out[ticker_col].astype(str)
    out = out.merge(
        aggregates,
        on=[ticker_col, date_col],
        how="left",
        sort=False,
    )
    return _ensure_aggregate_columns(out)


AGGREGATE_COLUMNS = [
    "same_day_signal_count",
    "same_day_unique_patterns",
    "same_day_max_strength",
    "same_day_second_best_strength",
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
