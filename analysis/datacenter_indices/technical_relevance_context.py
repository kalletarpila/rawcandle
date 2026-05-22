from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_RELEVANCE_CLASSES = ("RELEVANT", "WEAK_CONTEXT", "NOISE")


@dataclass(frozen=True)
class TechnicalRelevanceContextRow:
    ticker: str
    timeframe: str
    signal_date: str
    signal_confirmed_as_of_date: str
    signal_name: str
    signal_source_id: str
    relevance_class: str
    relevance_reason: str
    dow_trend_state: str | None
    dow_context_state: str | None
    latest_bos_direction: str | None
    bars_since_latest_bos: int | None
    bars_since_latest_reset: int | None
    near_latest_pivot: int
    near_active_bos_level: int
    is_trend_aligned: int
    is_counter_trend: int


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _normalize_tickers(tickers: Iterable[str]) -> list[str]:
    return sorted({str(ticker).strip() for ticker in tickers if str(ticker).strip()})


def load_technical_relevance_context(
    conn: sqlite3.Connection,
    technical_relevance_run_id: str,
    tickers: Sequence[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    relevance_classes: Sequence[str] | None = None,
    limit_per_ticker: int | None = None,
) -> list[TechnicalRelevanceContextRow]:
    if not technical_relevance_run_id.strip():
        raise ValueError("technical_relevance_run_id must be non-empty")
    normalized_tickers = _normalize_tickers(tickers)
    if not normalized_tickers:
        return []
    if start_date > end_date:
        raise ValueError(f"Invalid date range: {start_date} is after {end_date}")
    if not _table_exists(conn, "technical_signal_relevance"):
        return []

    selected_classes = tuple(relevance_classes or DEFAULT_RELEVANCE_CLASSES)
    if not selected_classes:
        return []

    ticker_placeholders = ", ".join("?" for _ in normalized_tickers)
    class_placeholders = ", ".join("?" for _ in selected_classes)
    rows = conn.execute(
        f"""
        SELECT
            ticker,
            timeframe,
            signal_date,
            signal_confirmed_as_of_date,
            signal_name,
            signal_source_id,
            relevance_class,
            relevance_reason,
            dow_trend_state,
            dow_context_state,
            latest_bos_direction,
            bars_since_latest_bos,
            bars_since_latest_reset,
            near_latest_pivot,
            near_active_bos_level,
            is_trend_aligned,
            is_counter_trend
        FROM technical_signal_relevance
        WHERE run_id = ?
          AND ticker IN ({ticker_placeholders})
          AND timeframe = ?
          AND signal_date >= ?
          AND signal_date <= ?
          AND relevance_class IN ({class_placeholders})
        ORDER BY
            ticker ASC,
            signal_date ASC,
            signal_name ASC,
            signal_source_id ASC,
            relevance_class ASC,
            relevance_reason ASC
        """,
        (
            technical_relevance_run_id,
            *normalized_tickers,
            timeframe,
            start_date,
            end_date,
            *selected_classes,
        ),
    ).fetchall()
    output_rows = [
        TechnicalRelevanceContextRow(
            ticker=str(row["ticker"]),
            timeframe=str(row["timeframe"]),
            signal_date=str(row["signal_date"]),
            signal_confirmed_as_of_date=str(row["signal_confirmed_as_of_date"]),
            signal_name=str(row["signal_name"]),
            signal_source_id=str(row["signal_source_id"]),
            relevance_class=str(row["relevance_class"]),
            relevance_reason=str(row["relevance_reason"]),
            dow_trend_state=None if row["dow_trend_state"] is None else str(row["dow_trend_state"]),
            dow_context_state=None if row["dow_context_state"] is None else str(row["dow_context_state"]),
            latest_bos_direction=None if row["latest_bos_direction"] is None else str(row["latest_bos_direction"]),
            bars_since_latest_bos=None if row["bars_since_latest_bos"] is None else int(row["bars_since_latest_bos"]),
            bars_since_latest_reset=None if row["bars_since_latest_reset"] is None else int(row["bars_since_latest_reset"]),
            near_latest_pivot=int(row["near_latest_pivot"]),
            near_active_bos_level=int(row["near_active_bos_level"]),
            is_trend_aligned=int(row["is_trend_aligned"]),
            is_counter_trend=int(row["is_counter_trend"]),
        )
        for row in rows
    ]
    if limit_per_ticker is None:
        return output_rows
    if limit_per_ticker <= 0:
        raise ValueError("limit_per_ticker must be greater than 0")
    limited_rows: list[TechnicalRelevanceContextRow] = []
    counts_by_ticker: dict[str, int] = {}
    for row in output_rows:
        seen_count = counts_by_ticker.get(row.ticker, 0)
        if seen_count >= limit_per_ticker:
            continue
        counts_by_ticker[row.ticker] = seen_count + 1
        limited_rows.append(row)
    return limited_rows
