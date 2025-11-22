from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time
from typing import Callable, Iterable, List, Optional

import pandas as pd
import yfinance as yf

from analysis.database_manager import DatabaseManager


def _clean_tickers(tickers: Iterable[str]) -> List[str]:
    cleaned = []
    for t in tickers:
        if not t:
            continue
        symbol = t.strip().upper()
        if symbol:
            cleaned.append(symbol)
    return cleaned


def fetch_blackouts_for_tickers(
    tickers: Iterable[str],
    *,
    start_date: str = "2018-01-01",
    db_path: str = "data/analysis.db",
    db: Optional[DatabaseManager] = None,
) -> dict:
    tickers = _clean_tickers(tickers)
    if not tickers:
        return {"inserted": 0, "details": [], "errors": ["Ei ticker-valintaa"]}

    cache_dir = Path(db_path).resolve().parent / "yf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:  # pragma: no cover - protective
        yf.set_tz_cache_location(str(cache_dir / "tz.db"))
    except Exception:
        pass

    try:
        start_dt = datetime.fromisoformat(start_date).date()
    except ValueError:
        raise ValueError("Virheellinen päivämäärä. Käytä muotoa YYYY-MM-DD.")

    owned_db = False
    if db is None:
        db = DatabaseManager(db_path)
        owned_db = True
    entries: List[tuple[str, str, str, str]] = []
    details: List[dict] = []
    errors: List[str] = []

    for ticker in tickers:
        div_count = 0
        earn_count = 0
        try:
            yt = yf.Ticker(ticker)
            hist = yt.history(start=start_date, actions=True)
            if not hist.empty and "Dividends" in hist.columns:
                div_series = hist["Dividends"]
                for idx, value in div_series.items():
                    if value and value > 0:
                        event_date = pd.Timestamp(idx).date()
                        if event_date >= start_dt:
                            entries.append(
                                (ticker, event_date.isoformat(), "dividend", "yfinance")
                            )
                            div_count += 1

            earnings_df = None
            try:
                earnings_df = yt.get_earnings_dates(limit=60)
            except Exception:
                earnings_df = getattr(yt, "earnings_dates", None)
            if earnings_df is not None and not earnings_df.empty:
                df = earnings_df.copy().reset_index()
                date_col = "index"
                if "Earnings Date" in df.columns:
                    date_col = "Earnings Date"
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df.dropna(subset=[date_col])
                for event_ts in df[date_col]:
                    event_date = event_ts.date()
                    if event_date >= start_dt:
                        entries.append(
                            (ticker, event_date.isoformat(), "earnings", "yfinance")
                        )
                        earn_count += 1

            details.append(
                {
                    "ticker": ticker,
                    "dividends": div_count,
                    "earnings": earn_count,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            errors.append(f"{ticker}: {exc}")

    inserted = db.insert_blackout_entries(entries)
    if owned_db:
        db.close()
    return {"inserted": inserted, "details": details, "errors": errors}


def fetch_blackouts_for_missing_tickers(
    *,
    start_date: str = "2018-01-01",
    db_path: str = "data/analysis.db",
    delay_seconds: float = 1.5,
    limit: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    Hae blackout-päivät kaikille tickereille, joilta tiedot puuttuvat.

    Args:
        start_date: Aikaisin huomioitava päivä
        db_path: Analysis-kannan polku
        delay_seconds: Viive jokaisen tickerin välillä
        limit: Kuinka monta tickeriä käsitellään (debug-tarkoituksiin)
        progress_callback: Kutsutaan jokaiselle tickerille (ticker, current, total)
    """
    db = DatabaseManager(db_path)
    tickers = db.get_tickers_missing_blackouts(limit=limit)
    total = len(tickers)
    if total == 0:
        db.close()
        return {
            "inserted": 0,
            "processed": 0,
            "details": [],
            "errors": [],
            "tickers": [],
        }

    inserted_total = 0
    processed = 0
    details: List[dict] = []
    errors: List[str] = []
    log_path = Path(db_path).resolve().parent / "blackoutdays.txt"

    for idx, ticker in enumerate(tickers, start=1):
        if cancel_check and cancel_check():
            break
        result = fetch_blackouts_for_tickers(
            [ticker],
            start_date=start_date,
            db_path=db_path,
            db=db,
        )
        inserted_this = result.get("inserted", 0)
        inserted_total += inserted_this
        details.extend(result.get("details", []))
        errors.extend(result.get("errors", []))
        processed += 1
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{ticker};{inserted_this}\n")
        except Exception:
            pass
        if progress_callback:
            try:
                progress_callback(ticker, processed, total, inserted_this)
            except Exception:
                pass
        if idx < total and delay_seconds > 0:
            time.sleep(delay_seconds)

    db.close()
    return {
        "inserted": inserted_total,
        "processed": processed,
        "total": total,
        "cancelled": processed < total,
        "details": details,
        "errors": errors,
        "tickers": tickers,
    }
