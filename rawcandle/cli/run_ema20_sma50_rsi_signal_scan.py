from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

DEFAULT_OUTPUT_DIR = Path("/home/kalle/projects/rawcandle/EMASMA_GC")


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


@dataclass(frozen=True)
class ForwardReturnMetrics:
    max_forward_return_pct: float | None
    max_forward_return_days: int | None
    min_forward_return_pct: float | None
    min_forward_return_days: int | None


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
    parser.add_argument(
        "--include-forward-returns",
        action="store_true",
        help="Include forward return metrics for returned signal rows.",
    )
    parser.add_argument(
        "--forward-window",
        type=int,
        default=60,
        help="Number of future trading days to inspect for forward returns.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional CSV output path. When omitted, CSV is written under the default output directory.",
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


def _require_positive_forward_window(value: int) -> int:
    if value <= 0:
        raise ValueError(f"forward-window must be > 0, got {value}")
    return value


def _load_price_rows(
    db_path: Path,
    market: str,
    end_date: str | None,
) -> list[PriceRow]:
    sql = """
        SELECT osake, pvm, close
        FROM osakedata
        WHERE market = ?
          AND close IS NOT NULL
    """
    params: list[object] = [market]
    if end_date is not None:
        sql += " AND pvm <= ?"
        params.append(end_date)
    sql += " ORDER BY osake ASC, pvm ASC"
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
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
    end_date: str | None,
    min_rsi: float,
) -> list[SignalRow]:
    closes = [row.close for row in rows]
    ema20_values = _calculate_ema_series(closes, 20)
    sma50_values = _calculate_sma_series(closes, 50)

    signals: list[SignalRow] = []
    for idx in range(1, len(rows)):
        row = rows[idx]
        if row.date < start_date:
            continue
        if end_date is not None and row.date > end_date:
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


def _group_price_rows_by_ticker(rows: list[PriceRow]) -> dict[str, list[PriceRow]]:
    rows_by_ticker: dict[str, list[PriceRow]] = {}
    for row in rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)
    return rows_by_ticker


def _calculate_forward_return_metrics(
    rows: list[PriceRow],
    event_date: str,
    forward_window: int,
) -> ForwardReturnMetrics:
    event_index = next((idx for idx, row in enumerate(rows) if row.date == event_date), None)
    if event_index is None:
        raise ValueError(f"Event date {event_date} not found in ticker price rows")

    event_close = rows[event_index].close
    future_rows = rows[event_index + 1 : event_index + 1 + forward_window]
    if not future_rows:
        return ForwardReturnMetrics(
            max_forward_return_pct=None,
            max_forward_return_days=None,
            min_forward_return_pct=None,
            min_forward_return_days=None,
        )

    max_return: float | None = None
    max_days: int | None = None
    min_return: float | None = None
    min_days: int | None = None
    for offset, row in enumerate(future_rows, start=1):
        future_return_pct = ((row.close - event_close) / event_close) * 100.0
        if max_return is None or future_return_pct > max_return:
            max_return = future_return_pct
            max_days = offset
        if min_return is None or future_return_pct < min_return:
            min_return = future_return_pct
            min_days = offset

    return ForwardReturnMetrics(
        max_forward_return_pct=max_return,
        max_forward_return_days=max_days,
        min_forward_return_pct=min_return,
        min_forward_return_days=min_days,
    )


def scan_signals(
    db_path: Path,
    analysis_db_path: Path,
    market: str,
    start_date: str,
    end_date: str,
    price_end_date: str | None,
    min_rsi: float,
) -> tuple[list[SignalRow], dict[str, list[PriceRow]]]:
    price_rows = _load_price_rows(
        db_path=db_path,
        market=market,
        end_date=price_end_date,
    )
    rows_by_ticker = _group_price_rows_by_ticker(price_rows)

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
    return sorted(signals, key=lambda item: (item.date, item.ticker)), rows_by_ticker


def _format_float(value: float) -> str:
    return f"{value:.4f}"


def _format_csv_float(value: float) -> str:
    return _format_float(value).replace(".", ",")


def _default_output_path(
    market: str,
    start_date: str,
    end_date: str,
    include_forward_returns: bool,
    forward_window: int,
) -> Path:
    suffix = (
        f"_forward_{forward_window}d"
        if include_forward_returns
        else ""
    )
    filename = (
        f"ema20_sma50_rsi_signal_scan_{market}_{start_date}_{end_date}{suffix}.csv"
    )
    return DEFAULT_OUTPUT_DIR / filename


def _build_csv_lines(
    rows: list[SignalRow],
    include_forward_returns: bool,
    forward_metrics_by_key: dict[tuple[str, str], ForwardReturnMetrics],
) -> list[str]:
    if include_forward_returns:
        lines = [
            "ticker;date;ema20;sma50;rsi;max_forward_return_pct;max_forward_return_days;min_forward_return_pct;min_forward_return_days"
        ]
    else:
        lines = ["ticker;date;ema20;sma50;rsi"]

    for row in rows:
        line = (
            f"{row.ticker};{row.date};{_format_csv_float(row.ema20)};{_format_csv_float(row.sma50)};{_format_csv_float(row.rsi)}"
        )
        if include_forward_returns:
            metrics = forward_metrics_by_key[(row.ticker, row.date)]
            line = (
                f"{line};"
                f"{'' if metrics.max_forward_return_pct is None else _format_csv_float(metrics.max_forward_return_pct)};"
                f"{'' if metrics.max_forward_return_days is None else metrics.max_forward_return_days};"
                f"{'' if metrics.min_forward_return_pct is None else _format_csv_float(metrics.min_forward_return_pct)};"
                f"{'' if metrics.min_forward_return_days is None else metrics.min_forward_return_days}"
            )
        lines.append(line)
    return lines


def format_summary_lines(
    market: str,
    start_date: str,
    end_date: str,
    min_rsi: float,
    limit: int,
    candidate_count: int,
    returned_count: int,
    include_forward_returns: bool = False,
    forward_window: int = 60,
    forward_returns_rows_with_data: int = 0,
    forward_returns_rows_without_data: int = 0,
    forward_returns_positive_count: int = 0,
    forward_returns_bucket_lt_minus10_count: int = 0,
    forward_returns_bucket_minus10_to_0_count: int = 0,
    forward_returns_bucket_0_to_10_count: int = 0,
    forward_returns_bucket_10_to_20_count: int = 0,
    forward_returns_bucket_20_to_50_count: int = 0,
    forward_returns_bucket_gt_50_count: int = 0,
) -> list[str]:
    lines = [
        f"SUMMARY market={market}",
        f"SUMMARY start_date={start_date}",
        f"SUMMARY end_date={end_date}",
        f"SUMMARY min_rsi={min_rsi:.4f}",
        f"SUMMARY limit={limit}",
        f"SUMMARY candidates={candidate_count}",
        f"SUMMARY returned={returned_count}",
    ]
    if include_forward_returns:
        forward_returns_positive_pct = (
            100.0 * forward_returns_positive_count / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_lt_minus10_pct = (
            100.0
            * forward_returns_bucket_lt_minus10_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_minus10_to_0_pct = (
            100.0
            * forward_returns_bucket_minus10_to_0_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_0_to_10_pct = (
            100.0
            * forward_returns_bucket_0_to_10_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_10_to_20_pct = (
            100.0
            * forward_returns_bucket_10_to_20_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_20_to_50_pct = (
            100.0
            * forward_returns_bucket_20_to_50_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        forward_returns_bucket_gt_50_pct = (
            100.0
            * forward_returns_bucket_gt_50_count
            / float(forward_returns_rows_with_data)
            if forward_returns_rows_with_data > 0
            else 0.0
        )
        lines.extend(
            [
                "SUMMARY forward_returns_included=1",
                f"SUMMARY forward_window={forward_window}",
                f"SUMMARY forward_returns_rows_with_data={forward_returns_rows_with_data}",
                f"SUMMARY forward_returns_rows_without_data={forward_returns_rows_without_data}",
                f"SUMMARY forward_returns_positive_count={forward_returns_positive_count}",
                f"SUMMARY forward_returns_positive_pct={forward_returns_positive_pct:.4f}",
                f"SUMMARY forward_returns_bucket_lt_minus10_count={forward_returns_bucket_lt_minus10_count}",
                f"SUMMARY forward_returns_bucket_minus10_to_0_count={forward_returns_bucket_minus10_to_0_count}",
                f"SUMMARY forward_returns_bucket_0_to_10_count={forward_returns_bucket_0_to_10_count}",
                f"SUMMARY forward_returns_bucket_10_to_20_count={forward_returns_bucket_10_to_20_count}",
                f"SUMMARY forward_returns_bucket_20_to_50_count={forward_returns_bucket_20_to_50_count}",
                f"SUMMARY forward_returns_bucket_gt_50_count={forward_returns_bucket_gt_50_count}",
                f"SUMMARY forward_returns_bucket_lt_minus10_pct={forward_returns_bucket_lt_minus10_pct:.4f}",
                f"SUMMARY forward_returns_bucket_minus10_to_0_pct={forward_returns_bucket_minus10_to_0_pct:.4f}",
                f"SUMMARY forward_returns_bucket_0_to_10_pct={forward_returns_bucket_0_to_10_pct:.4f}",
                f"SUMMARY forward_returns_bucket_10_to_20_pct={forward_returns_bucket_10_to_20_pct:.4f}",
                f"SUMMARY forward_returns_bucket_20_to_50_pct={forward_returns_bucket_20_to_50_pct:.4f}",
                f"SUMMARY forward_returns_bucket_gt_50_pct={forward_returns_bucket_gt_50_pct:.4f}",
            ]
        )
    return lines


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
        forward_window = _require_positive_forward_window(int(args.forward_window))
        signal_end_date = None if args.include_forward_returns else end_date
        signals, rows_by_ticker = scan_signals(
            db_path=db_path,
            analysis_db_path=analysis_db_path,
            market=str(args.market),
            start_date=start_date,
            end_date=end_date,
            price_end_date=signal_end_date,
            min_rsi=float(args.min_rsi),
        )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    limited_signals = signals[:limit]
    forward_rows_with_data = 0
    forward_rows_without_data = 0
    forward_positive_count = 0
    forward_bucket_lt_minus10_count = 0
    forward_bucket_minus10_to_0_count = 0
    forward_bucket_0_to_10_count = 0
    forward_bucket_10_to_20_count = 0
    forward_bucket_20_to_50_count = 0
    forward_bucket_gt_50_count = 0
    forward_metrics_by_key: dict[tuple[str, str], ForwardReturnMetrics] = {}
    if args.include_forward_returns:
        for row in limited_signals:
            metrics = _calculate_forward_return_metrics(
                rows=rows_by_ticker[row.ticker],
                event_date=row.date,
                forward_window=forward_window,
            )
            forward_metrics_by_key[(row.ticker, row.date)] = metrics
            if metrics.max_forward_return_days is None:
                forward_rows_without_data += 1
            else:
                forward_rows_with_data += 1
                if (
                    metrics.max_forward_return_pct is not None
                    and metrics.max_forward_return_pct > 0.0
                ):
                    forward_positive_count += 1
                if metrics.max_forward_return_pct is not None:
                    if metrics.max_forward_return_pct < -10.0:
                        forward_bucket_lt_minus10_count += 1
                    elif metrics.max_forward_return_pct <= 0.0:
                        forward_bucket_minus10_to_0_count += 1
                    elif metrics.max_forward_return_pct <= 10.0:
                        forward_bucket_0_to_10_count += 1
                    elif metrics.max_forward_return_pct <= 20.0:
                        forward_bucket_10_to_20_count += 1
                    elif metrics.max_forward_return_pct <= 50.0:
                        forward_bucket_20_to_50_count += 1
                    else:
                        forward_bucket_gt_50_count += 1
    if args.output_format == "csv":
        output_path = (
            Path(args.output)
            if args.output is not None
            else _default_output_path(
                market=str(args.market),
                start_date=start_date,
                end_date=end_date,
                include_forward_returns=bool(args.include_forward_returns),
                forward_window=forward_window,
            )
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        csv_lines = _build_csv_lines(
            rows=limited_signals,
            include_forward_returns=bool(args.include_forward_returns),
            forward_metrics_by_key=forward_metrics_by_key,
        )
        output_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    summary_lines = format_summary_lines(
        market=str(args.market),
        start_date=start_date,
        end_date=end_date,
        min_rsi=float(args.min_rsi),
        limit=limit,
        candidate_count=len(signals),
        returned_count=len(limited_signals),
        include_forward_returns=bool(args.include_forward_returns),
        forward_window=forward_window,
        forward_returns_rows_with_data=forward_rows_with_data,
        forward_returns_rows_without_data=forward_rows_without_data,
        forward_returns_positive_count=forward_positive_count,
        forward_returns_bucket_lt_minus10_count=forward_bucket_lt_minus10_count,
        forward_returns_bucket_minus10_to_0_count=forward_bucket_minus10_to_0_count,
        forward_returns_bucket_0_to_10_count=forward_bucket_0_to_10_count,
        forward_returns_bucket_10_to_20_count=forward_bucket_10_to_20_count,
        forward_returns_bucket_20_to_50_count=forward_bucket_20_to_50_count,
        forward_returns_bucket_gt_50_count=forward_bucket_gt_50_count,
    )
    if args.output_format == "csv":
        csv_lines.extend(summary_lines)
        output_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    for line in summary_lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
