from __future__ import annotations

from typing import Any, Iterable, Sequence, Tuple
import sqlite3

import pandas as pd


def build_universe_query(params: dict[str, Any]) -> tuple[str, list[Any]]:
    """
    Build a parametrized SQL query for results_data universe selection.
    """
    where: list[str] = []
    sql_params: list[Any] = []
    market = (params.get("market") or "").strip().lower()
    if market and market != "__all__":
        where.append("LOWER(COALESCE(market, '')) = ?")
        sql_params.append(market)

    if params.get("bullish_only"):
        # Focus on bullish divergence + downtrend control (patterns 0 ja 7)
        where.append("candle_pattern IN (0, 7)")

    if params.get("exclude_blackout"):
        where.append("(COALESCE(is_blackout_window, 0) = 0)")

    if params.get("exclude_crisis"):
        where.append("(COALESCE(is_crisis, 0) = 0)")

    if params.get("only_candle_days"):
        where.append("(COALESCE(is_candle_day, 0) = 1)")

    if params.get("exclude_from_regression_only"):
        where.append("(COALESCE(exclude_from_regression, 0) = 0)")

    sector = (params.get("sector") or "").strip()
    if sector and sector != "__all__":
        where.append("sector = ?")
        sql_params.append(sector)

    rsi_min = params.get("rsi_min")
    if rsi_min is not None:
        try:
            rsi_min_val = float(rsi_min)
            where.append("RSI14_t0 >= ?")
            sql_params.append(rsi_min_val)
        except Exception:
            pass

    rsi_max = params.get("rsi_max")
    if rsi_max is not None:
        try:
            rsi_max_val = float(rsi_max)
            where.append("RSI14_t0 <= ?")
            sql_params.append(rsi_max_val)
        except Exception:
            pass

    vola_min = params.get("vola_min")
    if vola_min is not None:
        try:
            vola_min_val = float(vola_min)
            where.append("ATR_ratio_14 >= ?")
            sql_params.append(vola_min_val)
        except Exception:
            pass

    vola_max = params.get("vola_max")
    if vola_max is not None:
        try:
            vola_max_val = float(vola_max)
            where.append("ATR_ratio_14 <= ?")
            sql_params.append(vola_max_val)
        except Exception:
            pass

    where_clause = ""
    if where:
        where_clause = "WHERE " + " AND ".join(where)

    order_clause = "ORDER BY date DESC, signal_strength DESC"
    limit_clause = ""
    try:
        max_rows = int(params.get("max_rows", 0) or 0)
        if max_rows > 0:
            limit_clause = " LIMIT ?"
            sql_params.append(max_rows)
    except Exception:
        max_rows = 0
    sql = f"SELECT * FROM results_data {where_clause} {order_clause}{limit_clause}"
    return sql, sql_params


def safe_read_results_data(
    conn: sqlite3.Connection, sql: str, params: Sequence[Any]
) -> pd.DataFrame:
    """
    Execute a SQL query safely and return a DataFrame.
    """
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()
    return df


def list_available_markets(conn: sqlite3.Connection) -> list[str]:
    """
    Read unique markets from results_data for dropdown suggestions.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT LOWER(market) FROM results_data WHERE market IS NOT NULL AND TRIM(market) != '' ORDER BY 1"
        )
        rows = [row[0] for row in cursor.fetchall() if row[0]]
        return rows
    except Exception:
        return []
