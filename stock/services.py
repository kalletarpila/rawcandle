from __future__ import annotations

import datetime as dt
import sqlite3
from collections import deque
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from simu import config as simu_config
from simu.db import PriceRow
from simu.indicators import compute_rsi

DATA_DIR = Path("data")
PRICE_DB_PATH = DATA_DIR / "osakedata.db"
ANALYSIS_DB_PATH = DATA_DIR / "analysis.db"


class StockDataError(RuntimeError):
    """Raised when ticker data cannot be fetched."""


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise StockDataError(f"⚠️ Tietokantaa ei löydy: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_price_rows(
    ticker: str,
    *,
    limit: int | None = 200,
    rsi_period: int | None = None,
    price_db: Path | None = None,
) -> List[Dict]:
    """Return latest OHLCV rows (ascending by date) enriched with RSI and SMAs."""
    if not ticker:
        return []

    db_path = Path(price_db or PRICE_DB_PATH)
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT pvm, open, high, low, close, volume
            FROM osakedata
            WHERE osake = ?
            ORDER BY pvm ASC
            """,
            (ticker.strip().upper(),),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    if limit and len(rows) > limit:
        rows = rows[-limit:]

    price_records: List[Dict] = []
    price_rows_for_rsi: List[PriceRow] = []

    for row in rows:
        date_value = dt.date.fromisoformat(row["pvm"])
        open_val = row["open"]
        high_val = row["high"]
        low_val = row["low"]
        close_val = row["close"]
        volume_val = row["volume"]

        price_records.append(
            {
                "date": date_value,
                "open": float(open_val) if open_val is not None else None,
                "high": float(high_val) if high_val is not None else None,
                "low": float(low_val) if low_val is not None else None,
                "close": float(close_val) if close_val is not None else None,
                "volume": float(volume_val) if volume_val is not None else None,
            }
        )

        if close_val is not None:
            price_rows_for_rsi.append(
                PriceRow(
                    date=date_value,
                    open=float(open_val) if open_val is not None else 0.0,
                    high=float(high_val) if high_val is not None else 0.0,
                    low=float(low_val) if low_val is not None else 0.0,
                    close=float(close_val),
                    volume=float(volume_val or 0.0),
                )
            )

    if price_rows_for_rsi:
        period = rsi_period or simu_config.RSI_PERIOD
        rsi_map = compute_rsi(price_rows_for_rsi, period=period)
    else:
        rsi_map = {}

    _apply_sma(price_records, window=20, key="sma20")
    _apply_sma(price_records, window=50, key="sma50")
    _apply_sma(price_records, window=200, key="sma200")

    for record in price_records:
        record["rsi"] = rsi_map.get(record["date"])

    return price_records


def fetch_analysis_records(
    ticker: str,
    *,
    page: int = 0,
    page_size: int = 25,
    analysis_db: Path | None = None,
) -> Tuple[List[Dict], int]:
    """Return paginated analysis_findings rows for the given ticker."""
    if page < 0:
        page = 0
    if page_size <= 0:
        page_size = 25

    db_path = Path(analysis_db or ANALYSIS_DB_PATH)
    conn = _connect(db_path)
    try:
        columns_cursor = conn.execute("PRAGMA table_info(analysis_findings)")
        column_names = [row["name"] for row in columns_cursor.fetchall()]
        if "pattern" in column_names:
            pattern_col = "pattern"
        elif "candle" in column_names:
            pattern_col = "candle"
        else:
            raise StockDataError("analysis_findings-taulusta puuttuu pattern/candle sarake.")

        strength_col = "signal_strength" if "signal_strength" in column_names else None
        has_rsi = "rsi14" in column_names

        total_cursor = conn.execute(
            "SELECT COUNT(*) FROM analysis_findings WHERE ticker = ?",
            (ticker.strip().upper(),),
        )
        total_rows = total_cursor.fetchone()[0]
        if total_rows == 0:
            return [], 0

        offset = page * page_size
        strength_expr = strength_col if strength_col else "NULL"
        rsi_expr = "rsi14" if has_rsi else "NULL"

        query = f"""
            SELECT date,
                   {pattern_col} AS pattern_name,
                   {strength_expr} AS signal_strength,
                   {rsi_expr} AS rsi14
            FROM analysis_findings
            WHERE ticker = ?
            ORDER BY date DESC, rowid DESC
            LIMIT ? OFFSET ?
        """
        result_cursor = conn.execute(
            query,
            (ticker.strip().upper(), page_size, offset),
        )
        records = []
        for row in result_cursor.fetchall():
            date_value = row["date"]
            parsed_date = (
                dt.date.fromisoformat(date_value)
                if date_value
                else None
            )
            records.append(
                {
                    "date": parsed_date,
                    "pattern": row["pattern_name"],
                    "signal_strength": row["signal_strength"],
                    "rsi14": row["rsi14"],
                }
            )
    finally:
        conn.close()

    return records, total_rows


def fetch_analysis_events(
    ticker: str,
    *,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    patterns: Sequence[str] | None = None,
    analysis_db: Path | None = None,
) -> List[Dict]:
    """Return all analysis_findings rows for overlays."""
    if not ticker:
        return []

    db_path = Path(analysis_db or ANALYSIS_DB_PATH)
    conn = _connect(db_path)
    try:
        columns_cursor = conn.execute("PRAGMA table_info(analysis_findings)")
        column_names = [row["name"] for row in columns_cursor.fetchall()]
        if "pattern" in column_names:
            pattern_col = "pattern"
        elif "candle" in column_names:
            pattern_col = "candle"
        else:
            raise StockDataError("analysis_findings-taulusta puuttuu pattern/candle sarake.")

        strength_col = "signal_strength" if "signal_strength" in column_names else None

        query = f"""
            SELECT date,
                   {pattern_col} AS pattern_name,
                   {strength_col if strength_col else 'NULL'} AS signal_strength
            FROM analysis_findings
            WHERE ticker = ?
        """
        params: List = [ticker.strip().upper()]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        if patterns:
            placeholders = ",".join("?" for _ in patterns)
            query += f" AND {pattern_col} IN ({placeholders})"
            params.extend(patterns)

        query += " ORDER BY date ASC"

        cursor = conn.execute(query, params)
        events = []
        for row in cursor.fetchall():
            date_value = row["date"]
            parsed_date = dt.date.fromisoformat(date_value) if date_value else None
            if not parsed_date:
                continue
            events.append(
                {
                    "date": parsed_date,
                    "pattern": row["pattern_name"],
                    "signal_strength": row["signal_strength"],
                }
            )
    finally:
        conn.close()

    return events


def _apply_sma(records: Sequence[Dict], *, window: int, key: str) -> None:
    """Attach simple moving average values to price records in-place."""
    if window <= 1:
        for record in records:
            record[key] = record.get("close")
        return

    history = deque()  # type: ignore[var-annotated]
    running_sum = 0.0

    for record in records:
        close_value = record.get("close")
        if close_value is None:
            record[key] = None
            continue

        history.append(close_value)
        running_sum += close_value
        if len(history) > window:
            removed = history.popleft()
            running_sum -= removed

        if len(history) == window:
            record[key] = running_sum / window
        else:
            record[key] = None
