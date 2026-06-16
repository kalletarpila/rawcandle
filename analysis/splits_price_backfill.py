from __future__ import annotations

"""
Backfill osakedata hinnat split-tiedon perusteella.

- Etsii splits_data-taulusta rivit, joissa is_price_data_corrected = 0.
- Poistaa hinnat 2018-01-01 alkaen ja hakee uudelleen Yahoo Financesta
  (sama yfinance-hakutapa kuin pääohjelmassa).
- Merkitsee splitit korjatuiksi onnistuneen haun jälkeen.
- Rate limit: max ~3 tickeriä sekunnissa.
"""

import argparse
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
import yfinance as yf

# Lisää projektijuuri sys.path:iin, kun ajetaan skriptinä
import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from market_repository import ensure_market_schema
from analysis.splits_analysis_helpers import delete_analysis_rows_for_ticker
from analysis.divergence_recompute import recompute_divergence_for_ticker

logger = logging.getLogger(__name__)

DEFAULT_START = "2018-01-01"


def default_inclusive_end_date() -> str:
    """Return today's date as the inclusive end date for local callers."""
    return datetime.now().strftime("%Y-%m-%d")


def _exclusive_end_date(date_str: str) -> str:
    """Convert an inclusive YYYY-MM-DD date to the exclusive end date yfinance expects."""
    return (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime("%Y-%m-%d")


def get_tickers_with_uncorrected_splits(conn: sqlite3.Connection) -> List[str]:
    cursor = conn.execute(
        """
        SELECT DISTINCT osake
        FROM splits_data
        WHERE is_price_data_corrected = 0
        ORDER BY osake
        """
    )
    return [row[0] for row in cursor.fetchall() if row[0]]


def has_uncorrected_splits(conn: sqlite3.Connection, ticker: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM splits_data WHERE osake = ? AND is_price_data_corrected = 0 LIMIT 1",
        (ticker,),
    ).fetchone()
    return row is not None


def delete_prices_from_2018(
    conn: sqlite3.Connection, ticker: str, start_date: str = DEFAULT_START
) -> int:
    cursor = conn.execute(
        "DELETE FROM osakedata WHERE osake = ? AND pvm >= ?",
        (ticker, start_date),
    )
    conn.commit()
    return cursor.rowcount


def _infer_market(conn: sqlite3.Connection, ticker: str) -> str:
    try:
        row = conn.execute(
            "SELECT market FROM osakedata WHERE osake = ? ORDER BY pvm DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if row and row[0]:
            return str(row[0]).strip().lower()
    except Exception:
        pass
    return "usa"


def _has_complete_ohlc_values(row: pd.Series) -> bool:
    return not any(pd.isna(row.get(column)) for column in ("Open", "High", "Low", "Close"))


def refetch_prices_from_yahoo(
    conn: sqlite3.Connection,
    ticker: str,
    start_date: str = DEFAULT_START,
    end_date: Optional[str] = None,
) -> int:
    """
    Hakee hinnat ja tallettaa osakedata-tauluun. Palauttaa lisättyjen rivien määrän.
    """
    inclusive_end_date = end_date or default_inclusive_end_date()
    yahoo_end_date = _exclusive_end_date(inclusive_end_date)
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=yahoo_end_date)
    except Exception as exc:
        logger.warning("Yahoo-haku epäonnistui (%s): %s", ticker, exc)
        return 0

    if hist is None or hist.empty:
        logger.info(
            "Ei dataa tickerille %s (ajanjakso %s-%s)",
            ticker,
            start_date,
            inclusive_end_date,
        )
        return 0

    market = _infer_market(conn, ticker)
    rows_added = 0
    cursor = conn.cursor()
    for date, row in hist.iterrows():
        try:
            date_str = date.strftime("%Y-%m-%d")
        except Exception:
            continue
        if not _has_complete_ohlc_values(row):
            continue
        cursor.execute(
            """
            INSERT OR REPLACE INTO osakedata
            (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                date_str,
                float(row["Open"]) if pd.notna(row.get("Open")) else None,
                float(row["High"]) if pd.notna(row.get("High")) else None,
                float(row["Low"]) if pd.notna(row.get("Low")) else None,
                float(row["Close"]) if pd.notna(row.get("Close")) else None,
                int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                market,
            ),
        )
        rows_added += 1
    conn.commit()
    return rows_added


def mark_splits_corrected(conn: sqlite3.Connection, ticker: str) -> int:
    cursor = conn.execute(
        """
        UPDATE splits_data
        SET is_price_data_corrected = 1
        WHERE osake = ? AND is_price_data_corrected = 0
        """,
        (ticker,),
    )
    conn.commit()
    return cursor.rowcount


def _rate_limit_sleep(start_time: float, max_per_second: float = 3.0) -> None:
    min_interval = 1.0 / max_per_second
    elapsed = time.time() - start_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)


def backfill_uncorrected(
    db_path: Path,
    *,
    dry_run: bool = False,
    limit: Optional[int] = None,
    tickers_override: Optional[List[str]] = None,
    start_date: str = DEFAULT_START,
    end_date: Optional[str] = None,
) -> List[str]:
    ensure_market_schema(str(db_path))
    conn = sqlite3.connect(db_path)
    analysis_path = Path("data") / "analysis.db"
    conn_analysis = sqlite3.connect(analysis_path)
    processed: List[str] = []
    try:
        tickers = (
            [t.strip().upper() for t in tickers_override if t.strip()]
            if tickers_override
            else get_tickers_with_uncorrected_splits(conn)
        )
        if limit:
            tickers = tickers[:limit]
        if not tickers:
            logger.info("Ei korjaamattomia splittejä.")
            return []

        logger.info("Aloitetaan backfill %d tickerille (dry_run=%s).", len(tickers), dry_run)
        for idx, ticker in enumerate(tickers, 1):
            started = time.time()
            try:
                logger.info("Korjataan %s (%d/%d)", ticker, idx, len(tickers))
                print(f"[SPLIT] Havaittu korjaamaton split: {ticker} ({idx}/{len(tickers)})")
                if not dry_run:
                    delete_prices_from_2018(conn, ticker, start_date=start_date)
                    added = refetch_prices_from_yahoo(
                        conn, ticker, start_date=start_date, end_date=end_date
                    )
                    if added > 0:
                        # analysis.db puhdistus ja divergence
                        from analysis.splits_analysis_helpers import delete_analysis_rows_for_ticker
                        # tämä import täällä välttää kiertävät riippuvuudet
                        findings, div_rows, res_rows = delete_analysis_rows_for_ticker(
                            conn_analysis, ticker
                        )
                        logger.info(
                            "Poistettu analysis rivit %s: findings=%d, divergence=%d, results=%d",
                            ticker,
                            findings,
                            div_rows,
                            res_rows,
                        )
                        # divergenssin uudelleenlaskenta
                        success, days, err = recompute_divergence_for_ticker(
                            ticker,
                            osakedata_path=db_path,
                            analysis_path=analysis_path,
                            only_missing=False,
                        )
                        if success:
                            mark_splits_corrected(conn, ticker)
                            processed.append(ticker)
                            logger.info(
                                "✅ %s korjattu, rivejä lisätty %d, divergence päivitetty (%d päivää)",
                                ticker,
                                added,
                                days,
                            )
                            print(f"[SPLIT] {ticker}: uudet hinnat haettu ({added} riviä), analysis puhdistettu, divergence laskettu ({days} päivää).")
                        else:
                            logger.warning(
                                "⚠️ Divergenssin laskenta epäonnistui (%s): %s",
                                ticker,
                                err,
                            )
                    else:
                        logger.warning("⚠️ %s: ei lisätty uusia rivejä, jätetään flagit muuttamatta", ticker)
                else:
                    processed.append(ticker)
            except Exception as exc:
                logger.warning("⚠️ %s: korjaus epäonnistui (%s)", ticker, exc)
            finally:
                _rate_limit_sleep(started, max_per_second=3.0)
        logger.info("Backfill valmis. Onnistuneita tickereitä: %d", len(processed))
        return processed
    finally:
        conn_analysis.close()
        conn.close()


def _write_report(processed: Iterable[str]) -> Optional[Path]:
    processed_list = list(processed)
    date_str = datetime.now().strftime("%Y%m%d")
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path = data_dir / f"Splits_{date_str}.txt"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            if processed_list:
                f.write(",".join(processed_list))
            else:
                f.write("")
        return report_path
    except Exception as exc:
        logger.warning("Raportin kirjoitus epäonnistui: %s", exc)
        return None


def run_backfill() -> None:
    parser = argparse.ArgumentParser(
        description="Refetch osakedata hinnat split-tiedon perusteella."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/osakedata.db"),
        help="Polku osakedata.db:hen",
    )
    parser.add_argument("--dry-run", action="store_true", help="Älä kirjoita kantaan.")
    parser.add_argument("--limit", type=int, default=None, help="Käsittele enintään N tickeriä.")
    parser.add_argument(
        "--tickers",
        type=Path,
        default=None,
        help="Polku tiedostoon, jossa tickerit rivittäin (ohittaa splits_data-haun).",
    )
    args = parser.parse_args()

    tickers_override = None
    if args.tickers:
        try:
            with open(args.tickers, "r", encoding="utf-8") as f:
                tickers_override = [line.split("#", 1)[0].strip() for line in f if line.strip()]
        except Exception as exc:
            logger.warning("Tickereiden luku epäonnistui (%s): %s", args.tickers, exc)

    processed = backfill_uncorrected(
        args.db,
        dry_run=args.dry_run,
        limit=args.limit,
        tickers_override=tickers_override,
    )
    report = _write_report(processed)
    if report:
        logger.info("Raportti kirjoitettu: %s", report)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_backfill()
