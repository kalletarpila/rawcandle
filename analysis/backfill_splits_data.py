#!/usr/bin/env python3
"""
Backfill splits_data-taulu osakedata.db:hen.

- Lukee distinct osake:t osakedata-taulusta.
- Hakee splittitiedot Yahoo Financesta (yfinance).
- Insertoi/ohittaa (INSERT OR IGNORE) tauluun splits_data.
- Rate-limit: max 3 kutsua sekunnissa.
- Tulostaa välitiedot joka 200 tickerin välein.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable

import sys

# Varmista että juuripolku on sys.path:issa (kun ajetaan skriptinä analysis-kansiosta)
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock.splits import rate_limited_fetch, fetch_splits_for_ticker, upsert_splits


def ensure_splits_schema(conn: sqlite3.Connection) -> None:
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
    conn.commit()


def fetch_distinct_tickers(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT DISTINCT osake FROM osakedata ORDER BY osake")
    return [row[0] for row in cur.fetchall() if row[0]]


def backfill(
    db_path: Path,
    *,
    dry_run: bool = False,
    ticker_limit: int | None = None,
    ticker_list: list[str] | None = None,
) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    ensure_splits_schema(conn)
    if ticker_list is not None:
        tickers = [t.strip().upper() for t in ticker_list if t]
    else:
        tickers = fetch_distinct_tickers(conn)
    if ticker_limit:
        tickers = tickers[:ticker_limit]
    if not tickers:
        print("Ei tickereitä osakedatassa.")
        return 0, 0

    limited_fetch = rate_limited_fetch(fetch_splits_for_ticker, max_per_second=3.0)
    total_inserted = 0
    processed = 0

    for ticker in tickers:
        processed += 1
        events = limited_fetch(ticker)
        if events:
            if dry_run:
                inserted = 0
            else:
                inserted = upsert_splits(conn, events)
            total_inserted += inserted
        if processed % 200 == 0:
            print(f"Käsitelty {processed}/{len(tickers)} tickereitä, lisätty {total_inserted} splitiä.")

    print(
        f"Valmis. Tickereitä {len(tickers)}, "
        f"{'kuivaharjoitus, ei kirjoitettu' if dry_run else 'lisätty'} {total_inserted} splitiä."
    )
    return processed, total_inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill splits_data-taulu osakedata.db:stä löytyville tickereille."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/osakedata.db"),
        help="Polku osakedata.db tiedostoon",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Älä kirjoita kantaan, hae ja raportoi vain.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Käsittele enintään N tickeriä (valintajoukosta).",
    )
    parser.add_argument(
        "--tickers",
        type=Path,
        default=None,
        help="Polku tiedostoon, jossa tickerit rivittäin (ohittaa kannasta luetun listan).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers_list = None
    if args.tickers:
        try:
            with open(args.tickers, "r", encoding="utf-8") as f:
                tickers_list = [line.strip().split("#", 1)[0].strip() for line in f if line.strip()]
        except Exception as exc:
            print(f"⚠️ Tickereitä ei voitu lukea tiedostosta: {exc}")
            tickers_list = None

    backfill(
        args.db,
        dry_run=args.dry_run,
        ticker_limit=args.limit,
        ticker_list=tickers_list,
    )


if __name__ == "__main__":
    main()
