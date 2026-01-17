import os
import sqlite3
import time
from typing import Callable, Dict, Optional, Tuple

import yfinance as yf

TickerInfo = Tuple[str, str]


def _ensure_metadata_tables(conn: sqlite3.Connection) -> None:
    """Varmista ticker_meta-taulu (ticker, market, sector, industry) ja indeksit."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_meta (
            ticker TEXT PRIMARY KEY,
            market TEXT,
            sector TEXT,
            industry TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_meta_market ON ticker_meta(market)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticker_meta_market_sector ON ticker_meta(market, sector)"
    )


def _fetch_sector_data(ticker: str) -> Optional[TickerInfo]:
    try:
        info = yf.Ticker(ticker).info or {}
        sector = (info.get("sector") or "").strip()
        industry = (info.get("industry") or "").strip()
        if not sector and not industry:
            return None
        return sector or "NULL", industry or "NULL"
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
        _ensure_metadata_tables(conn)

        params = []
        query = """
            SELECT DISTINCT osake AS ticker, LOWER(market) AS market
            FROM osakedata
            WHERE osake IS NOT NULL
        """
        if market_filter:
            query += " AND LOWER(market) = LOWER(?)"
            params.append(market_filter)
        query += " ORDER BY osake"
        rows = conn.execute(query, params).fetchall()
        tickers = [(r[0], r[1]) for r in rows if r[0]]

        updated = 0
        missing = 0
        errors = 0

        for idx, (ticker, mkt) in enumerate(tickers, 1):
            sector_info = None
            try:
                sector_info = _fetch_sector_data(ticker)
                if sector_info:
                    sector_val, industry_val = sector_info
                else:
                    sector_val = industry_val = "NULL"
                    missing += 1

                conn.execute(
                    """
                    INSERT INTO ticker_meta (ticker, market, sector, industry)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET
                        market=excluded.market,
                        sector=excluded.sector,
                        industry=excluded.industry
                    """,
                    (ticker, mkt, sector_val, industry_val),
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
