from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List

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
    start_date: str = "2022-01-01",
    db_path: str = "data/analysis.db",
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

    db = DatabaseManager(db_path)
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
    return {"inserted": inserted, "details": details, "errors": errors}
