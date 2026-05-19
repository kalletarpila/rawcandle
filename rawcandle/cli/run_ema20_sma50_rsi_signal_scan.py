from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PriceRow:
    ticker: str
    date: str
    close: float


@dataclass(frozen=True)
class SignalRow:
    ticker: str
    date: str
    ema20: float
    sma50: float
    rsi: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan EMA20/SMA50 upward cross events with RSI confirmation."
    )
    parser.add_argument("--db", required=True, help="Path to OHLCV SQLite DB.")
    parser.add_argument(
        "--analysis-db",
        required=True,
        help="Path to analysis SQLite DB used for RSI lookup.",
    )
    parser.add_argument("--market", required=True, help="Market filter.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date YYYY-MM-DD.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum rows to print.")
    parser.add_argument("--min-rsi", type=float, default=50.0, help="Minimum RSI threshold.")
    parser.add_argument(
        "--output-format",
        choices=("csv", "summary"),
        default="csv",
        help="Output format.",
    )
    return parser


def _normalize_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _require_non_negative_limit(value: int) -> int:
    if value < 0:
        raise ValueError(f"limit must be >= 0, got {value}")
    return value


def _load_price_rows(db_path: Path, market: str, end_date: str) -> list[PriceRow]:
    sql = """
        SELECT osake, pvm, close
        FROM osakedata
        WHERE market = ?
          AND pvm <= ?
          AND close IS NOT NULL
        ORDER BY osake ASC, pvm ASC
    """
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(sql, (market, end_date)).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Failed to read osakedata from {db_path}: {exc}") from exc

    return [
        PriceRow(
            ticker=str(row[0]),
            date=_normalize_iso_date(str(row[1]), "osakedata.pvm"),
            close=float(row[2]),
        )
        for row in rows
    ]


def _load_rsi_map(
    analysis_db_path: Path,
    tickers: Iterable[str],
    end_date: str,
) -> dict[tuple[str, str], float]:
    ticker_list = sorted({str(item) for item in tickers if str(item)})
    if not ticker_list:
        return {}

    placeholders = ", ".join("?" for _ in ticker_list)
    sql = f"""
        SELECT ticker, date, rsi
        FROM divergence_data
        WHERE ticker IN ({placeholders})
          AND date <= ?
          AND rsi IS NOT NULL
    """
    params = [*ticker_list, end_date]
    try:
        with sqlite3.connect(analysis_db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Failed to read divergence_data from {analysis_db_path}: {exc}") from exc

    rsi_map: dict[tuple[str, str], float] = {}
    for ticker, row_date, rsi in rows:
        normalized_date = _normalize_iso_date(str(row_date), "divergence_data.date")
        rsi_map[(str(ticker), normalized_date)] = float(rsi)
    return rsi_map


def _calculate_sma_series(closes: list[float], window: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if window <= 0:
        return values
    running_sum = 0.0
    for idx, close in enumerate(closes):
        running_sum += close
        if idx >= window:
            running_sum -= closes[idx - window]
        if idx >= window - 1:
            values[idx] = running_sum / float(window)
    return values


def _calculate_ema_series(closes: list[float], window: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if window <= 0 or len(closes) < window:
        return values
    alpha = 2.0 / float(window + 1)
    ema = sum(closes[:window]) / float(window)
    values[window - 1] = ema
    for idx in range(window, len(closes)):
        ema = (closes[idx] * alpha) + (ema * (1.0 - alpha))
        values[idx] = ema
    return values


def _scan_ticker_rows(
    rows: list[PriceRow],
    rsi_map: dict[tuple[str, str], float],
    start_date: str,
    end_date: str,
    min_rsi: float,
) -> list[SignalRow]:
    closes = [row.close for row in rows]
    ema20_values = _calculate_ema_series(closes, 20)
    sma50_values = _calculate_sma_series(closes, 50)

    signals: list[SignalRow] = []
    for idx in range(1, len(rows)):
        row = rows[idx]
        if row.date < start_date or row.date > end_date:
            continue
        previous_ema20 = ema20_values[idx - 1]
        previous_sma50 = sma50_values[idx - 1]
        current_ema20 = ema20_values[idx]
        current_sma50 = sma50_values[idx]
        if (
            previous_ema20 is None
            or previous_sma50 is None
            or current_ema20 is None
            or current_sma50 is None
        ):
            continue
        if previous_ema20 > previous_sma50:
            continue
        if current_ema20 <= current_sma50:
            continue
        rsi = rsi_map.get((row.ticker, row.date))
        if rsi is None or rsi <= min_rsi:
            continue
        signals.append(
            SignalRow(
                ticker=row.ticker,
                date=row.date,
                ema20=current_ema20,
                sma50=current_sma50,
                rsi=rsi,
            )
        )
    return signals


def scan_signals(
    db_path: Path,
    analysis_db_path: Path,
    market: str,
    start_date: str,
    end_date: str,
    min_rsi: float,
) -> list[SignalRow]:
    price_rows = _load_price_rows(db_path=db_path, market=market, end_date=end_date)
    rows_by_ticker: dict[str, list[PriceRow]] = {}
    for row in price_rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)

    rsi_map = _load_rsi_map(
        analysis_db_path=analysis_db_path,
        tickers=rows_by_ticker.keys(),
        end_date=end_date,
    )

    signals: list[SignalRow] = []
    for ticker in sorted(rows_by_ticker):
        signals.extend(
            _scan_ticker_rows(
                rows=rows_by_ticker[ticker],
                rsi_map=rsi_map,
                start_date=start_date,
                end_date=end_date,
                min_rsi=min_rsi,
            )
        )
    return sorted(signals, key=lambda item: (item.date, item.ticker))


def _format_float(value: float) -> str:
    return f"{value:.4f}"


def format_summary_lines(
    market: str,
    start_date: str,
    end_date: str,
    min_rsi: float,
    limit: int,
    candidate_count: int,
    returned_count: int,
) -> list[str]:
    return [
        f"SUMMARY market={market}",
        f"SUMMARY start_date={start_date}",
        f"SUMMARY end_date={end_date}",
        f"SUMMARY min_rsi={min_rsi:.4f}",
        f"SUMMARY limit={limit}",
        f"SUMMARY candidates={candidate_count}",
        f"SUMMARY returned={returned_count}",
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        db_path = Path(args.db)
        analysis_db_path = Path(args.analysis_db)
        start_date = _normalize_iso_date(args.start_date, "start-date")
        end_date = _normalize_iso_date(args.end_date, "end-date")
        if start_date > end_date:
            raise ValueError("start-date must be <= end-date")
        limit = _require_non_negative_limit(int(args.limit))
        signals = scan_signals(
            db_path=db_path,
            analysis_db_path=analysis_db_path,
            market=str(args.market),
            start_date=start_date,
            end_date=end_date,
            min_rsi=float(args.min_rsi),
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    limited_signals = signals[:limit]
    if args.output_format == "csv":
        print("ticker;date;ema20;sma50;rsi")
        for row in limited_signals:
            print(
                f"{row.ticker};{row.date};{_format_float(row.ema20)};{_format_float(row.sma50)};{_format_float(row.rsi)}"
            )

    for line in format_summary_lines(
        market=str(args.market),
        start_date=start_date,
        end_date=end_date,
        min_rsi=float(args.min_rsi),
        limit=limit,
        candidate_count=len(signals),
        returned_count=len(limited_signals),
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
