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

    where_clause = ""
    if where:
        where_clause = "WHERE " + " AND ".join(where)

    order_clause = "ORDER BY date DESC, signal_strength DESC"
    sql = f"SELECT * FROM results_data {where_clause} {order_clause}"
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
