import os
import sqlite3
import time
from typing import Callable, Dict, Optional, Tuple

import yfinance as yf

TickerInfo = Tuple[str, str]


def _ensure_sector_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(osakedata)")
    columns = {row[1] for row in cursor.fetchall()}
    if "sector" not in columns:
        conn.execute("ALTER TABLE osakedata ADD COLUMN sector TEXT")
    if "industry" not in columns:
        conn.execute("ALTER TABLE osakedata ADD COLUMN industry TEXT")


def _fetch_sector_data(ticker: str) -> Optional[TickerInfo]:
    try:
        info = yf.Ticker(ticker).info or {}
        sector = (info.get("sector") or "").strip()
        industry = (info.get("industry") or "").strip()
        if not sector and not industry:
            return None
        return sector or "ei löydetty", industry or "ei löydetty"
    except Exception:
        return None


def update_sector_metadata(
    db_path: str,
    market_filter: Optional[str] = None,
    *,
    logger: Callable[[str], None] = print,
    sleep_fn: Callable[[float], None] = time.sleep,
    ticker_pause: float = 1.5,
    batch_pause: float = 30.0,
    batch_size: int = 500,
) -> Dict[str, int]:
    """
    Päivitä sektorit ja toimialat osakedata.db:n osakkeille.

    Returns summary counts for callers/tests.
    """
    if not db_path:
        raise ValueError("db_path is required")
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        _ensure_sector_columns(conn)

        params = []
        query = "SELECT DISTINCT osake FROM osakedata WHERE osake IS NOT NULL"
        if market_filter:
            query += " AND LOWER(market) = LOWER(?)"
            params.append(market_filter)
        query += " ORDER BY osake"
        rows = conn.execute(query, params).fetchall()
        tickers = [r[0] for r in rows if r[0]]

        updated = 0
        missing = 0
        errors = 0

        for idx, ticker in enumerate(tickers, 1):
            sector_info = None
            try:
                sector_info = _fetch_sector_data(ticker)
                if sector_info:
                    sector_val, industry_val = sector_info
                else:
                    sector_val = industry_val = "ei löydetty"
                    missing += 1

                conn.execute(
                    "UPDATE osakedata SET sector = ?, industry = ? WHERE osake = ?",
                    (sector_val, industry_val, ticker),
                )
                updated += 1
                if sector_info:
                    logger(f"{ticker} | {sector_val} | {industry_val}")
                else:
                    logger(f"{ticker} | ei löydetty")
            except Exception:
                errors += 1
                logger(f"{ticker} | ei löydetty")
            finally:
                try:
                    sleep_fn(ticker_pause)
                    if idx % batch_size == 0:
                        sleep_fn(batch_pause)
                except Exception:
                    pass

        conn.commit()

    return {"updated": updated, "missing": missing, "errors": errors, "tickers": len(tickers)}
