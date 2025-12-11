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
        return apply_same_day_aliases(
            _ensure_aggregate_columns(df_dedup), ensure_defaults=True
        )

    if ticker_col not in df_raw.columns or date_col not in df_raw.columns:
        return apply_same_day_aliases(
            _ensure_aggregate_columns(df_dedup), ensure_defaults=True
        )

    work = df_raw.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col])
    if work.empty:
        return apply_same_day_aliases(
            _ensure_aggregate_columns(df_dedup), ensure_defaults=True
        )

    work[ticker_col] = work[ticker_col].astype(str)
    patterns = work.get(pattern_col)
    if patterns is None:
        return apply_same_day_aliases(
            _ensure_aggregate_columns(df_dedup), ensure_defaults=True
        )
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
        signal_count = int(signal_mask.sum())
        records.append(
            {
                ticker_col: ticker,
                date_col: date,
                "signal_count_same_day": signal_count,
            }
        )

    aggregates = pd.DataFrame(records)
    if aggregates.empty:
        return apply_same_day_aliases(
            _ensure_aggregate_columns(df_dedup), ensure_defaults=True
        )

    out = df_dedup.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out[ticker_col] = out[ticker_col].astype(str)
    out = out.merge(
        aggregates,
        on=[ticker_col, date_col],
        how="left",
        sort=False,
    )
    ensured = _ensure_aggregate_columns(out)
    return apply_same_day_aliases(ensured, ensure_defaults=True)


AGGREGATE_COLUMNS = [
    # Säilytetään vain yksinkertainen signaalilaskuri yhteensopivuuteen.
    "signal_count_same_day",
]
INT_AGGREGATE_COLUMNS = {
    "signal_count_same_day",
}

SAME_DAY_ALIAS_MAP = {
    "same_day_signal_count": "signal_count_same_day",
}
SAME_DAY_ALIAS_INT_COLUMNS = {
    "same_day_signal_count",
}


def _ensure_aggregate_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in AGGREGATE_COLUMNS:
        if col not in out.columns:
            if col.startswith("has_") or col in INT_AGGREGATE_COLUMNS:
                out[col] = 0
            else:
                out[col] = 0.0
        else:
            if col.startswith("has_") or col in INT_AGGREGATE_COLUMNS:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
            else:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def apply_same_day_aliases(
    df: pd.DataFrame, ensure_defaults: bool = False
) -> pd.DataFrame:
    """
    Lisää legacy-sarakkeiden aliakset parityä varten.
    """
    out = df.copy()
    for legacy_col, new_col in SAME_DAY_ALIAS_MAP.items():
        if legacy_col in out.columns:
            continue
        if new_col in out.columns:
            out[legacy_col] = out[new_col]
        elif ensure_defaults:
            default_value = (
                0 if legacy_col in SAME_DAY_ALIAS_INT_COLUMNS else 0.0
            )
            out[legacy_col] = default_value
    return out


__all__ = [
    "add_same_day_aggregate_features",
    "apply_same_day_aliases",
]
