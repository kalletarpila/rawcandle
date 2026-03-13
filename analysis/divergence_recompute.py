from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Tuple

import pandas as pd

from analysis.database_manager import DatabaseManager
from .divergence_engine import compute_divergence_series
from .divergence_v1 import CANDIDATE_WINDOW, LOOKBACK_DAYS, MIN_HISTORY_DAYS, RSI_PERIOD


RECALC_CONTEXT_ROWS = MIN_HISTORY_DAYS + LOOKBACK_DAYS + CANDIDATE_WINDOW + RSI_PERIOD


def _load_existing_divergence_dates(
    analysis_path: Path | str, ticker: str
) -> set[str]:
    try:
        with sqlite3.connect(analysis_path) as conn_an:
            cur = conn_an.cursor()
            cur.execute(
                "SELECT date FROM divergence_data WHERE ticker = ?",
                (ticker,),
            )
            return {str(row[0]) for row in cur.fetchall() if row and row[0]}
    except Exception:
        return set()


def ticker_has_missing_divergence_dates(
    ticker: str,
    osakedata_path: Path | str,
    analysis_path: Path | str,
) -> bool:
    if not ticker:
        return False

    try:
        with sqlite3.connect(osakedata_path) as conn_osake:
            price_dates = {
                str(row[0])
                for row in conn_osake.execute(
                    "SELECT pvm FROM osakedata WHERE osake = ? ORDER BY pvm",
                    (ticker,),
                ).fetchall()
                if row and row[0]
            }
        if not price_dates:
            return False

        divergence_dates = _load_existing_divergence_dates(analysis_path, ticker)
        if not divergence_dates:
            return True

        return any(date_value not in divergence_dates for date_value in price_dates)
    except Exception:
        return False


def _resolve_recompute_window(
    df: pd.DataFrame, existing_dates: set[str], only_missing: bool
) -> tuple[pd.DataFrame, str] | tuple[None, None]:
    if not only_missing:
        if df.empty:
            return None, None
        return df.copy(), str(df.iloc[0]["pvm"])

    missing_indices = [
        idx
        for idx, date_value in enumerate(df["pvm"].astype(str).tolist())
        if date_value not in existing_dates
    ]
    if not missing_indices:
        return None, None

    first_missing_idx = min(missing_indices)
    recalc_start_idx = max(0, first_missing_idx - RECALC_CONTEXT_ROWS)
    write_start_date = str(df.iloc[first_missing_idx]["pvm"])
    return df.iloc[recalc_start_idx:].copy(), write_start_date


def recompute_divergence_for_ticker(
    ticker: str,
    osakedata_path: Path | str,
    analysis_path: Path | str,
    only_missing: bool = False,
) -> Tuple[bool, int, str]:
    """
    Laske divergence_data annetulle tickerille ja kirjoita analysis.db:hen.

    Returns (success, rows_written, error_message)
    """
    try:
        with sqlite3.connect(osakedata_path) as conn_osake:
            df = pd.read_sql_query(
                "SELECT pvm, close FROM osakedata WHERE osake = ? ORDER BY pvm",
                conn_osake,
                params=[ticker],
            )

        if df.empty:
            return False, 0, f"Ei dataa tickerille {ticker}"

        existing_dates = (
            _load_existing_divergence_dates(analysis_path, ticker) if only_missing else set()
        )
        work_df, write_start_date = _resolve_recompute_window(df, existing_dates, only_missing)
        if work_df is None or write_start_date is None:
            return True, 0, ""

        computed_rows = compute_divergence_series(work_df, start_date=write_start_date)
        if not computed_rows:
            return True, 0, ""

        records = [
            (
                str(row["date"]),
                float(row["bullish_strength"] or 0.0),
                float(row["bearish_strength"] or 0.0),
                None if row["rsi"] is None else float(row["rsi"]),
            )
            for row in computed_rows
        ]

        with sqlite3.connect(analysis_path) as conn_an:
            conn_an.execute(
                "DELETE FROM divergence_data WHERE ticker = ? AND date >= ?",
                (ticker, write_start_date),
            )
            conn_an.commit()

        db_manager = DatabaseManager(db_path=str(analysis_path))
        success = db_manager.save_divergence_batch(ticker, records)
        db_manager.close()
        if success:
            return True, len(records), ""
        return False, 0, "Tallennus epäonnistui"
    except Exception as exc:
        return False, 0, str(exc)
