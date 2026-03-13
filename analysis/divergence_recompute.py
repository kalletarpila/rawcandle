from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Tuple

import pandas as pd

from analysis.candlestick_patterns import (
    calculate_rsi,
    is_bullish_divergence,
    is_bearish_divergence,
)
from analysis.database_manager import DatabaseManager

RSI_PERIOD = 14
DIVERGENCE_LOOKBACK_DAYS = 30
TREND_LOOKBACK_DAYS = 10
MIN_DAYS_BETWEEN = 3
RECALC_CONTEXT_DAYS = RSI_PERIOD + DIVERGENCE_LOOKBACK_DAYS + TREND_LOOKBACK_DAYS + 10


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
            return {row[0] for row in cur.fetchall() if row and row[0]}
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
    recalc_start_idx = max(0, first_missing_idx - RECALC_CONTEXT_DAYS)
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
        work_df, write_start_date = _resolve_recompute_window(
            df, existing_dates, only_missing
        )
        if work_df is None or write_start_date is None:
            return True, 0, ""

        work_df = calculate_rsi(work_df, period=RSI_PERIOD, close_col="close")
        if "RSI" not in work_df.columns:
            return False, 0, "RSI-laskenta epäonnistui"

        records = []
        for idx in range(len(work_df)):
            date = str(work_df.iloc[idx]["pvm"])
            if date < write_start_date:
                continue

            rsi = work_df.iloc[idx]["RSI"]
            bullish_strength = 0.0
            bearish_strength = 0.0

            if idx >= DIVERGENCE_LOOKBACK_DAYS and not pd.isna(rsi):
                bull = is_bullish_divergence(
                    work_df,
                    idx=idx,
                    lookback_days=DIVERGENCE_LOOKBACK_DAYS,
                    min_rsi_gain=3.0,
                    min_days_between=MIN_DAYS_BETWEEN,
                    close_col="close",
                )
                if bull and bull.get("found"):
                    bullish_strength = bull.get("strength", 1.0)
                elif not bullish_strength:
                    bear = is_bearish_divergence(
                        work_df,
                        idx=idx,
                        lookback_days=DIVERGENCE_LOOKBACK_DAYS,
                        min_rsi_drop=3.0,
                        min_days_between=MIN_DAYS_BETWEEN,
                        close_col="close",
                    )
                    if bear and bear.get("found"):
                        bearish_strength = bear.get("strength", 1.0)

            records.append(
                (
                    date,
                    bullish_strength,
                    bearish_strength,
                    rsi if not pd.isna(rsi) else None,
                )
            )

        if not records:
            return True, 0, ""

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
