from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .same_day_aggregates import apply_same_day_aliases


PATTERN_COLUMN_DEFAULT = "kynttila_koodi"


def load_blackout_dates(db_path: Path | str) -> pd.DataFrame:
    """
    Lataa blackout_dates-taulun (earnings/dividend-päivät) analysis.db-kannasta.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Analysis-kantaa ei löytynyt: {db_path}")

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT ticker, date, event FROM blackout_dates",
            conn,
        )

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["ticker"] = df["ticker"].astype(str)
    df["event"] = df["event"].astype(str).str.lower()
    return df


def apply_blackout_flags(
    df: pd.DataFrame,
    blackout_df: pd.DataFrame,
    date_col: str = "date",
    ticker_col: str = "ticker",
) -> pd.DataFrame:
    """
    Lisää blackout-flagit DataFrameen.
    """
    if blackout_df is None or blackout_df.empty:
        for col in [
            "is_earnings_t0",
            "is_dividend_t0",
            "is_earnings_window",
            "is_dividend_window",
            "is_blackout_t0",
            "is_blackout_window",
            "exclude_from_regression",
            "has_blackout_data",
        ]:
            df[col] = 0
        return df

    df = df.copy()
    if date_col not in df.columns or ticker_col not in df.columns:
        raise ValueError(
            f"apply_blackout_flags: df:stä puuttuu {date_col} tai {ticker_col}"
        )

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df["ticker"] = df[ticker_col].astype(str)

    bo = blackout_df.copy()
    bo = bo[["ticker", "date", "event"]].dropna()
    bo["event"] = bo["event"].str.lower()
    tickers_with_blackout = set(bo["ticker"].astype(str).unique())
    grouped = bo.groupby("ticker")

    df["is_earnings_t0"] = 0
    df["is_dividend_t0"] = 0
    df["is_earnings_window"] = 0
    df["is_dividend_window"] = 0
    df["has_blackout_data"] = (
        df["ticker"].astype(str).isin(tickers_with_blackout).astype(int)
    )

    for idx, row in df.iterrows():
        t0_date = row[date_col]
        tkr = row["ticker"]
        if pd.isna(t0_date) or tkr not in grouped.indices:
            continue

        events_for_ticker = grouped.get_group(tkr)
        deltas = (events_for_ticker["date"] - t0_date).dt.days
        earnings_mask = events_for_ticker["event"] == "earnings"
        earnings_deltas = deltas[earnings_mask]
        dividend_mask = events_for_ticker["event"] == "dividend"
        dividend_deltas = deltas[dividend_mask]

        if (earnings_deltas == 0).any():
            df.at[idx, "is_earnings_t0"] = 1
        if (dividend_deltas == 0).any():
            df.at[idx, "is_dividend_t0"] = 1
        if ((earnings_deltas >= 0) & (earnings_deltas <= 2)).any():
            df.at[idx, "is_earnings_window"] = 1
        if ((dividend_deltas >= 0) & (dividend_deltas <= 1)).any():
            df.at[idx, "is_dividend_window"] = 1

    df["is_blackout_t0"] = (
        (df["is_earnings_t0"] == 1) | (df["is_dividend_t0"] == 1)
    ).astype(int)
    df["is_blackout_window"] = (
        (df["is_earnings_window"] == 1) | (df["is_dividend_window"] == 1)
    ).astype(int)
    df["exclude_from_regression"] = df["is_blackout_window"]

    return df


def preprocess_signals(
    df: pd.DataFrame, pattern_column: str = PATTERN_COLUMN_DEFAULT
) -> pd.DataFrame:
    """
    Puhdistaa signaalit regressiota varten:

    - Yksi rivi per (ticker, date)
    - Valitsee "vahvimman" kynttilän (strongest candle wins)
    - Rakentaa multi-signal -koodin (signal_combo_code) sekä flagit
    """
    required_cols = {"ticker", "date", pattern_column}
    if df.empty:
        return df
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return df

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"])
    work[pattern_column] = work[pattern_column].fillna(0).astype(int)

    rows = []

    for (ticker, date), g in work.groupby(["ticker", "date"], sort=False):
        pat = g[pattern_column].astype(int)

        candles = sorted({p for p in pat.tolist() if p in {1, 2, 3, 4, 5, 6}})

        has_bulldiv = False
        if "is_divergence_today" in g.columns:
            has_bulldiv = bool(g["is_divergence_today"].fillna(0).astype(int).max() == 1)
        if not has_bulldiv and (pat == 7).any():
            has_bulldiv = True

        if not candles and not has_bulldiv:
            combo_code = 0
        elif len(candles) == 1 and not has_bulldiv:
            combo_code = 1
        elif len(candles) >= 2 and not has_bulldiv:
            combo_code = 2
        elif not candles and has_bulldiv:
            combo_code = 4
        else:
            combo_code = 3

        rep = g
        nonzero_mask = rep[pattern_column].astype(int) != 0
        if nonzero_mask.any():
            rep = rep.loc[nonzero_mask]

        if "vahvuus" in rep.columns:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                vahv = pd.to_numeric(rep["vahvuus"], errors="coerce")
            idx = vahv.fillna(vahv.min() - 1).idxmax()
            row = rep.loc[idx].copy()
        else:
            row = rep.iloc[0].copy()

        row["signal_combo_code"] = combo_code
        row["num_candles_same_day"] = len(candles)
        row["has_multi_candle_combo"] = int(len(candles) >= 2)
        row["has_bullish_divergence_same_day"] = int(has_bulldiv)

        rows.append(row)

    result = pd.DataFrame(rows).reset_index(drop=True)
    result = apply_same_day_aliases(result)
    return result


__all__ = [
    "apply_blackout_flags",
    "load_blackout_dates",
    "preprocess_signals",
]
