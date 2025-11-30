from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import yfinance as yf


logger = logging.getLogger(__name__)


@dataclass
class SplitEvent:
    osake: str
    split_date: str  # ISO YYYY-MM-DD
    split_ratio: float


def fetch_splits_for_ticker(ticker: str, yf_ticker: Optional[yf.Ticker] = None) -> List[SplitEvent]:
    """Hae splitit yhdelle tickerille. Palauttaa listan SplitEventeja, virheissä tyhjä lista."""
    if not ticker:
        return []

    try:
        ticker_obj = yf_ticker or yf.Ticker(ticker)
        splits = ticker_obj.splits
        if splits is None or splits.empty:
            return []
        events: List[SplitEvent] = []
        for idx, ratio in splits.items():
            try:
                date_str = idx.strftime("%Y-%m-%d")
                events.append(
                    SplitEvent(
                        osake=ticker,
                        split_date=date_str,
                        split_ratio=float(ratio),
                    )
                )
            except Exception:
                continue
        return events
    except Exception as exc:
        logger.warning("Splitien haku epäonnistui tickerille %s (%s)", ticker, exc)
        return []


def upsert_splits(conn: sqlite3.Connection, splits: Iterable[SplitEvent]) -> int:
    """Insertoi split-eventit INSERT OR IGNORE -tyyppisesti. Palauttaa insert count."""
    cursor = conn.cursor()
    inserted = 0
    for ev in splits:
        cursor.execute(
            """
            INSERT OR IGNORE INTO splits_data (osake, split_date, split_ratio)
            VALUES (?, ?, ?)
            """,
            (ev.osake, ev.split_date, ev.split_ratio),
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


def sync_splits_for_ticker(db_path: Path | str, ticker: str, yf_ticker: Optional[yf.Ticker] = None) -> int:
    """Hakee tickerin splitit ja upsertoi ne splits_data-tauluun. Palauttaa insert count."""
    events = fetch_splits_for_ticker(ticker, yf_ticker=yf_ticker)
    if not events:
        return 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS splits_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                osake TEXT NOT NULL,
                split_date TEXT NOT NULL,
                split_ratio REAL NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(osake, split_date)
            )
            """
        )
        inserted = upsert_splits(conn, events)
        return inserted
    finally:
        conn.close()


def rate_limited_fetch(fetch_func, max_per_second: float = 3.0):
    """Palauttaa wrapperin, joka varmistaa ettei kutsuta useammin kuin max_per_second."""
    min_interval = 1.0 / max_per_second if max_per_second > 0 else 0.0
    last_called = [0.0]

    def wrapper(*args, **kwargs):
        now = time.time()
        elapsed = now - last_called[0]
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        result = fetch_func(*args, **kwargs)
        last_called[0] = time.time()
        return result

    return wrapper
