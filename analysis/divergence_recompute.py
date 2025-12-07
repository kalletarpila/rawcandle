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

        df = calculate_rsi(df, period=14, close_col="close")
        if "RSI" not in df.columns:
            return False, 0, "RSI-laskenta epäonnistui"

        existing_dates = set()
        if only_missing:
            try:
                with sqlite3.connect(analysis_path) as conn_an:
                    cur = conn_an.cursor()
                    cur.execute(
                        "SELECT date FROM divergence_data WHERE ticker = ?",
                        (ticker,),
                    )
                    existing_dates = {row[0] for row in cur.fetchall()}
            except Exception:
                existing_dates = set()

        records = []
        for idx in range(len(df)):
            date = str(df.iloc[idx]["pvm"])
            if only_missing and date in existing_dates:
                continue

            rsi = df.iloc[idx]["RSI"]
            bullish_strength = 0.0
            bearish_strength = 0.0

            if idx >= 30 and not pd.isna(rsi):
                bull = is_bullish_divergence(
                    df,
                    idx=idx,
                    lookback_days=30,
                    min_rsi_gain=3.0,
                    min_days_between=3,
                    close_col="close",
                )
                if bull and bull.get("found"):
                    bullish_strength = bull.get("strength", 1.0)
                elif not bullish_strength:
                    bear = is_bearish_divergence(
                        df,
                        idx=idx,
                        lookback_days=30,
                        min_rsi_drop=3.0,
                        min_days_between=3,
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

        db_manager = DatabaseManager(db_path=str(analysis_path))
        success = db_manager.save_divergence_batch(ticker, records)
        db_manager.close()
        if success:
            return True, len(records), ""
        return False, 0, "Tallennus epäonnistui"
    except Exception as exc:
        return False, 0, str(exc)

