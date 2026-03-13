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


def _normalize_metadata_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.upper() == "NULL":
        return None
    return normalized


def refresh_single_ticker_metadata(
    db_path: str,
    ticker: str,
    market: Optional[str] = None,
    *,
    logger: Callable[[str], None] = print,
) -> bool:
    """
    Refresh ticker_meta for one ticker only if Yahoo returns useful changed/missing data.

    Returns True when a write was performed, otherwise False.
    """
    if not db_path:
        raise ValueError("db_path is required")
    if not ticker:
        raise ValueError("ticker is required")

    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    ticker = ticker.strip().upper()

    with sqlite3.connect(db_path) as conn:
        _ensure_metadata_tables(conn)
        current_row = conn.execute(
            "SELECT market, sector, industry FROM ticker_meta WHERE ticker = ?",
            (ticker,),
        ).fetchone()

    fetched = _fetch_sector_data(ticker)
    if not fetched:
        return False

    fetched_sector = _normalize_metadata_value(fetched[0])
    fetched_industry = _normalize_metadata_value(fetched[1])
    if fetched_sector is None and fetched_industry is None:
        return False

    with sqlite3.connect(db_path) as conn:
        _ensure_metadata_tables(conn)
        current_market = current_row[0] if current_row else None
        current_sector = _normalize_metadata_value(current_row[1]) if current_row else None
        current_industry = _normalize_metadata_value(current_row[2]) if current_row else None

        needs_write = False
        if current_row is None:
            needs_write = fetched_sector is not None or fetched_industry is not None
        else:
            if fetched_sector is not None and current_sector != fetched_sector:
                needs_write = True
            if fetched_industry is not None and current_industry != fetched_industry:
                needs_write = True

        if not needs_write:
            return False

        market_value = (market or current_market or "").strip().lower() or None
        conn.execute(
            """
            INSERT INTO ticker_meta (ticker, market, sector, industry)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                sector=COALESCE(excluded.sector, ticker_meta.sector),
                industry=COALESCE(
                    NULLIF(excluded.industry, 'NULL'),
                    NULLIF(ticker_meta.industry, 'NULL'),
                    ticker_meta.industry,
                    excluded.industry
                )
            """,
            (ticker, market_value, fetched_sector, fetched_industry),
        )
        conn.commit()

    logger(
        f"{ticker} | metadata refreshed"
        f" | sector={fetched_sector or '-'}"
        f" | industry={fetched_industry or '-'}"
    )
    return True


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

        total_params = []
        total_query = """
            SELECT COUNT(DISTINCT osake)
            FROM osakedata
            WHERE osake IS NOT NULL
        """
        if market_filter:
            total_query += " AND LOWER(market) = LOWER(?)"
            total_params.append(market_filter)
        total_tickers = conn.execute(total_query, total_params).fetchone()[0] or 0

        params = []
        query = """
            SELECT DISTINCT o.osake AS ticker, LOWER(o.market) AS market
            FROM osakedata o
            LEFT JOIN ticker_meta tm ON tm.ticker = o.osake
            WHERE o.osake IS NOT NULL
              AND (
                    tm.ticker IS NULL
                 OR tm.sector IS NULL
                 OR TRIM(tm.sector) = ''
                 OR UPPER(TRIM(tm.sector)) = 'NULL'
                 OR tm.industry IS NULL
                 OR TRIM(tm.industry) = ''
                 OR UPPER(TRIM(tm.industry)) = 'NULL'
              )
        """
        if market_filter:
            query += " AND LOWER(o.market) = LOWER(?)"
            params.append(market_filter)
        query += " ORDER BY o.osake"
        rows = conn.execute(query, params).fetchall()
        tickers = [(r[0], r[1]) for r in rows if r[0]]
        skipped = max(0, total_tickers - len(tickers))

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
                        sector=COALESCE(excluded.sector, ticker_meta.sector),
                        industry=COALESCE(
                            NULLIF(excluded.industry, 'NULL'),
                            NULLIF(ticker_meta.industry, 'NULL'),
                            ticker_meta.industry,
                            excluded.industry
                        )
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

    return {
        "updated": updated,
        "missing": missing,
        "errors": errors,
        "tickers": total_tickers,
        "skipped": skipped,
    }
