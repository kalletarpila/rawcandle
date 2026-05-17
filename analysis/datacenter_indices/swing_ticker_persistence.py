from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from analysis.database_manager import DatabaseManager

from .persistence import resolve_created_at_utc
from .swing_analysis_readers import (
    read_batch_candlestick_enrichment,
    read_batch_divergence_enrichment,
    read_batch_dow_structure_enrichment,
)
from .swing_ticker_metrics import TickerOhlcvRow, calculate_ticker_swing_metrics
from .taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_MAX_VALID_PRICE_ROWS = 220

TICKER_SWING_SUMMARY_ORDER = [
    "signal_date",
    "market",
    "write_mode",
    "signal_version",
    "run_id",
    "taxonomy_rows",
    "taxonomy_versions",
    "primary_tickers",
    "duplicate_primary_rows",
    "rows_prepared",
    "inserted_count",
    "updated_count",
    "upserted_count",
    "skipped_existing_count",
    "deleted_count",
    "missing_as_of_date_count",
    "missing_close_as_of_date_count",
    "insufficient_history_count",
    "ok_price_count",
    "validation_status",
]

TICKER_SWING_PROFILE_SUMMARY_ORDER = [
    "profile_enabled",
    "profile_taxonomy_load_seconds",
    "profile_price_load_seconds",
    "profile_metric_calc_seconds",
    "profile_dow_reader_seconds",
    "profile_divergence_reader_seconds",
    "profile_candle_reader_seconds",
    "profile_db_write_seconds",
    "profile_total_seconds",
    "profile_tickers_processed",
    "profile_price_rows_loaded",
    "profile_rows_prepared",
]

TICKER_SCANNER_SUMMARY_ORDER = [
    "start_date",
    "end_date",
    "requested_start_date",
    "requested_end_date",
    "valid_trading_dates",
    "skipped_non_trading_dates",
    "write_mode",
    "signal_version",
    "run_id",
    "updated_count",
    "missing_base_row_count",
    "cleared_count",
    "breakout_count",
    "fast_ema10_pullback_count",
    "conservative_ema20_pullback_count",
    "pullback_count",
    "exit_risk_count",
    "high_exit_risk_count",
    "medium_exit_risk_count",
    "low_exit_risk_count",
    "validation_status",
]

ENTRY_ELIGIBLE_PRICE_STATUSES = {"OK", "INSUFFICIENT_HISTORY"}


@dataclass(frozen=True)
class DatacenterTickerSwingSnapshotRow:
    signal_date: str
    taxonomy_version: str
    ticker: str
    primary_layer: str | None
    primary_subindustry: str | None
    close: float | None
    volume: float | None
    return_5d: float | None
    return_10d: float | None
    return_20d: float | None
    return_60d: float | None
    ma10: float | None
    ema10: float | None
    ema20: float | None
    distance_to_ma10_pct: float | None
    distance_to_ema10_pct: float | None
    distance_to_ema20_pct: float | None
    above_ma10: int | None
    above_ema10: int | None
    above_ema20: int | None
    ema10_slope_positive: int | None
    ema20_slope_positive: int | None
    ema10_slope_lookback: int | None
    ema20_slope_lookback: int | None
    highest_close_20d: float | None
    volume_avg_20d: float | None
    volume_vs_avg20: float | None
    latest_structure_label: str | None
    latest_structure_confirmed_as_of_date: str | None
    bullish_divergence_signal: int | None
    bearish_divergence_signal: int | None
    hidden_bullish_divergence_signal: int | None
    hidden_bearish_divergence_signal: int | None
    bullish_candle_signal: int | None
    bearish_candle_signal: int | None
    breakout_signal: int | None
    fast_ema10_pullback_signal: int | None
    conservative_ema20_pullback_signal: int | None
    pullback_signal: int | None
    exit_risk_signal: int | None
    exit_reason: str | None
    exit_risk_severity: str | None
    price_data_status: str | None
    signal_version: str
    run_id: str
    created_at_utc: str


def _normalize_ticker(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _chunked_values(values: Sequence[str], chunk_size: int = 900) -> list[list[str]]:
    normalized_values = list(values)
    return [
        normalized_values[index:index + chunk_size]
        for index in range(0, len(normalized_values), chunk_size)
    ]


def _load_primary_tickers_for_taxonomy(
    taxonomy_csv_path: str | Path,
) -> list[str]:
    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    primary_rows, _ = _select_primary_taxonomy_rows(taxonomy_rows)
    return sorted({_normalize_ticker(row.ticker) for row in primary_rows if _normalize_ticker(row.ticker)})


def load_valid_price_dates_for_market(
    *,
    price_db_path: str | Path,
    start_date: str,
    end_date: str,
    market: str | None,
    taxonomy_csv_path: str | Path | None = None,
) -> list[str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )

    primary_tickers: list[str] = []
    if taxonomy_csv_path is not None:
        primary_tickers = _load_primary_tickers_for_taxonomy(taxonomy_csv_path)
        if not primary_tickers:
            return []

    with sqlite3.connect(price_db_path) as conn:
        conn.row_factory = sqlite3.Row
        params: list[object] = [normalized_start_date, normalized_end_date]
        market_sql = ""
        if market is not None:
            market_sql = " AND market = ?"
            params.append(market)
        ticker_sql = ""
        if primary_tickers:
            placeholders = ", ".join("?" for _ in primary_tickers)
            ticker_sql = f" AND UPPER(TRIM(osake)) IN ({placeholders})"
            params.extend(primary_tickers)
        rows = conn.execute(
            f"""
            SELECT DISTINCT pvm
            FROM osakedata
            WHERE pvm >= ?
              AND pvm <= ?
              {market_sql}
              {ticker_sql}
            ORDER BY pvm ASC
            """,
            params,
        ).fetchall()
    return [str(row["pvm"]) for row in rows]


def load_existing_ticker_signal_dates(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    signal_version: str,
) -> list[str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT signal_date
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date >= ?
              AND signal_date <= ?
              AND signal_version = ?
            ORDER BY signal_date ASC
            """,
            (normalized_start_date, normalized_end_date, signal_version),
        ).fetchall()
        return [str(row["signal_date"]) for row in rows]
    finally:
        db_manager.close()


def build_ticker_swing_run_id(
    *,
    as_of_date: str,
    signal_version: str,
    run_id: str | None = None,
) -> str:
    if run_id is not None:
        return run_id
    compact_date = as_of_date.replace("-", "")
    return f"DC_TICKER_SWING_{compact_date}_{signal_version}".replace(" ", "_")


def format_ticker_swing_summary_lines(summary: dict[str, int | str]) -> list[str]:
    lines = [f"SUMMARY {key}={summary[key]}" for key in TICKER_SWING_SUMMARY_ORDER]
    if str(summary.get("profile_enabled", "0")) == "1":
        lines.extend(
            f"SUMMARY {key}={summary[key]}"
            for key in TICKER_SWING_PROFILE_SUMMARY_ORDER
            if key in summary
        )
    return lines


def format_ticker_scanner_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in TICKER_SCANNER_SUMMARY_ORDER if key in summary]


def _match_lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


def _match_lte(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold


def _match_gt(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def _match_gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _load_taxonomy_rows(
    taxonomy_csv_path: str | Path,
) -> list[DatacenterTaxonomyRow]:
    return load_datacenter_taxonomy_csv(taxonomy_csv_path)


def _select_primary_taxonomy_rows(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
) -> tuple[list[DatacenterTaxonomyRow], int]:
    primary_rows = [
        row
        for row in taxonomy_rows
        if int(row.is_primary) == 1
    ]
    sorted_rows = sorted(
        primary_rows,
        key=lambda row: (
            str(row.taxonomy_version),
            _normalize_ticker(row.ticker),
            str(row.layer),
            str(row.subindustry),
        ),
    )
    selected: list[DatacenterTaxonomyRow] = []
    seen_keys: set[tuple[str, str]] = set()
    duplicate_primary_rows = 0
    for row in sorted_rows:
        key = (str(row.taxonomy_version), _normalize_ticker(row.ticker))
        if key in seen_keys:
            duplicate_primary_rows += 1
            continue
        seen_keys.add(key)
        selected.append(row)
    return selected, duplicate_primary_rows


def _load_exact_as_of_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    market: str | None,
    as_of_date: str,
) -> list[TickerOhlcvRow]:
    params: list[object] = [ticker, as_of_date]
    market_sql = ""
    if market is not None:
        market_sql = " AND market = ?"
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT pvm, open, high, low, close, volume
        FROM osakedata
        WHERE UPPER(TRIM(osake)) = ?
          AND pvm = ?
          {market_sql}
        ORDER BY rowid DESC
        LIMIT 1
        """,
        params,
    ).fetchall()
    return [
        TickerOhlcvRow(
            date=str(row["pvm"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]


def load_bounded_ticker_ohlcv_history(
    *,
    price_db_path: str | Path,
    ticker: str,
    market: str | None,
    as_of_date: str,
    max_valid_price_rows: int = DEFAULT_MAX_VALID_PRICE_ROWS,
) -> list[TickerOhlcvRow]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    normalized_ticker = _normalize_ticker(ticker)
    if max_valid_price_rows <= 0:
        raise ValueError("max_valid_price_rows must be greater than 0")

    with sqlite3.connect(price_db_path) as conn:
        conn.row_factory = sqlite3.Row
        params: list[object] = [normalized_ticker, normalized_as_of_date]
        market_sql = ""
        if market is not None:
            market_sql = " AND market = ?"
            params.append(market)
        valid_rows = conn.execute(
            f"""
            SELECT pvm, open, high, low, close, volume
            FROM osakedata
            WHERE UPPER(TRIM(osake)) = ?
              AND pvm <= ?
              AND close IS NOT NULL
              {market_sql}
            ORDER BY pvm DESC, rowid DESC
            LIMIT ?
            """,
            [*params, max_valid_price_rows],
        ).fetchall()
        exact_rows = _load_exact_as_of_row(
            conn,
            ticker=normalized_ticker,
            market=market,
            as_of_date=normalized_as_of_date,
        )

    combined_by_date: dict[str, TickerOhlcvRow] = {
        row.date: row for row in exact_rows
    }
    for row in valid_rows:
        date_value = str(row["pvm"])
        if date_value not in combined_by_date:
            combined_by_date[date_value] = TickerOhlcvRow(
                date=date_value,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
    return sorted(combined_by_date.values(), key=lambda row: row.date)


def load_bounded_ticker_ohlcv_histories(
    *,
    price_db_path: str | Path,
    tickers: Sequence[str],
    market: str | None,
    as_of_date: str,
    max_valid_price_rows: int = DEFAULT_MAX_VALID_PRICE_ROWS,
) -> tuple[dict[str, list[TickerOhlcvRow]], int]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    normalized_tickers = sorted({_normalize_ticker(ticker) for ticker in tickers if _normalize_ticker(ticker)})
    if max_valid_price_rows <= 0:
        raise ValueError("max_valid_price_rows must be greater than 0")
    if not normalized_tickers:
        return {}, 0

    histories: dict[str, dict[str, TickerOhlcvRow]] = {ticker: {} for ticker in normalized_tickers}
    fetched_row_count = 0
    with sqlite3.connect(price_db_path) as conn:
        conn.row_factory = sqlite3.Row
        valid_market_sql = ""
        exact_market_sql = ""
        if market is not None:
            valid_market_sql = " AND market = ?"
            exact_market_sql = " AND market = ?"
        for ticker_chunk in _chunked_values(normalized_tickers):
            placeholders = ", ".join("?" for _ in ticker_chunk)
            valid_params: list[object] = [*ticker_chunk, normalized_as_of_date]
            exact_params: list[object] = [*ticker_chunk, normalized_as_of_date]
            if market is not None:
                valid_params.append(market)
                exact_params.append(market)
            valid_params.append(max_valid_price_rows)
            valid_rows = conn.execute(
                f"""
                WITH ranked_valid AS (
                    SELECT
                        UPPER(TRIM(osake)) AS ticker,
                        pvm,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(TRIM(osake))
                            ORDER BY pvm DESC, rowid DESC
                        ) AS valid_rank
                    FROM osakedata
                    WHERE UPPER(TRIM(osake)) IN ({placeholders})
                      AND pvm <= ?
                      AND close IS NOT NULL
                      {valid_market_sql}
                )
                SELECT ticker, pvm, open, high, low, close, volume
                FROM ranked_valid
                WHERE valid_rank <= ?
                """,
                valid_params,
            ).fetchall()
            exact_rows = conn.execute(
                f"""
                WITH ranked_exact AS (
                    SELECT
                        UPPER(TRIM(osake)) AS ticker,
                        pvm,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        ROW_NUMBER() OVER (
                            PARTITION BY UPPER(TRIM(osake))
                            ORDER BY rowid DESC
                        ) AS exact_rank
                    FROM osakedata
                    WHERE UPPER(TRIM(osake)) IN ({placeholders})
                      AND pvm = ?
                      {exact_market_sql}
                )
                SELECT ticker, pvm, open, high, low, close, volume
                FROM ranked_exact
                WHERE exact_rank = 1
                """,
                exact_params,
            ).fetchall()
            fetched_row_count += len(valid_rows) + len(exact_rows)
            for row in exact_rows:
                ticker = str(row["ticker"])
                combined_by_date = histories[ticker]
                combined_by_date[str(row["pvm"])] = TickerOhlcvRow(
                    date=str(row["pvm"]),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            for row in valid_rows:
                ticker = str(row["ticker"])
                combined_by_date = histories[ticker]
                date_value = str(row["pvm"])
                if date_value not in combined_by_date:
                    combined_by_date[date_value] = TickerOhlcvRow(
                        date=date_value,
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                    )
    return {
        ticker: sorted(rows_by_date.values(), key=lambda row: row.date)
        for ticker, rows_by_date in histories.items()
    }, fetched_row_count


def _row_key(
    row: DatacenterTickerSwingSnapshotRow,
) -> tuple[str, str, str, str]:
    return (
        row.signal_date,
        row.taxonomy_version,
        row.ticker,
        row.signal_version,
    )


def _serialize_row(row: DatacenterTickerSwingSnapshotRow) -> tuple[object, ...]:
    return (
        row.signal_date,
        row.taxonomy_version,
        row.ticker,
        row.primary_layer,
        row.primary_subindustry,
        row.close,
        row.volume,
        row.return_5d,
        row.return_10d,
        row.return_20d,
        row.return_60d,
        row.ma10,
        row.ema10,
        row.ema20,
        row.distance_to_ma10_pct,
        row.distance_to_ema10_pct,
        row.distance_to_ema20_pct,
        row.above_ma10,
        row.above_ema10,
        row.above_ema20,
        row.ema10_slope_positive,
        row.ema20_slope_positive,
        row.ema10_slope_lookback,
        row.ema20_slope_lookback,
        row.highest_close_20d,
        row.volume_avg_20d,
        row.volume_vs_avg20,
        row.latest_structure_label,
        row.latest_structure_confirmed_as_of_date,
        row.bullish_divergence_signal,
        row.bearish_divergence_signal,
        row.hidden_bullish_divergence_signal,
        row.hidden_bearish_divergence_signal,
        row.bullish_candle_signal,
        row.bearish_candle_signal,
        row.breakout_signal,
        row.fast_ema10_pullback_signal,
        row.conservative_ema20_pullback_signal,
        row.pullback_signal,
        row.exit_risk_signal,
        row.exit_reason,
        row.exit_risk_severity,
        row.price_data_status,
        row.signal_version,
        row.run_id,
        row.created_at_utc,
    )


def build_ticker_swing_snapshot_rows(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    as_of_date: str,
    market: str | None,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    run_id: str,
    created_at_utc: str,
    max_valid_price_rows: int = DEFAULT_MAX_VALID_PRICE_ROWS,
    profile: bool = False,
) -> tuple[list[DatacenterTickerSwingSnapshotRow], dict[str, int | str]]:
    total_started_at = time.perf_counter()
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    taxonomy_started_at = time.perf_counter()
    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    primary_rows, duplicate_primary_rows = _select_primary_taxonomy_rows(taxonomy_rows)
    taxonomy_elapsed = time.perf_counter() - taxonomy_started_at
    normalized_tickers = [_normalize_ticker(row.ticker) for row in primary_rows]

    price_started_at = time.perf_counter()
    ohlcv_histories, fetched_price_row_count = load_bounded_ticker_ohlcv_histories(
        price_db_path=price_db_path,
        tickers=normalized_tickers,
        market=market,
        as_of_date=normalized_as_of_date,
        max_valid_price_rows=max_valid_price_rows,
    )
    price_elapsed = time.perf_counter() - price_started_at

    metric_started_at = time.perf_counter()
    metrics_by_ticker = {
        ticker: calculate_ticker_swing_metrics(
            ohlcv_histories.get(ticker, []),
            normalized_as_of_date,
        )
        for ticker in normalized_tickers
    }
    metric_elapsed = time.perf_counter() - metric_started_at

    rows: list[DatacenterTickerSwingSnapshotRow] = []
    dow_elapsed = 0.0
    divergence_elapsed = 0.0
    candle_elapsed = 0.0
    with sqlite3.connect(analysis_db_path) as analysis_conn:
        analysis_conn.row_factory = sqlite3.Row
        dow_started_at = time.perf_counter()
        dow_by_ticker = read_batch_dow_structure_enrichment(
            analysis_conn,
            normalized_tickers,
            market,
            normalized_as_of_date,
        )
        dow_elapsed = time.perf_counter() - dow_started_at

        divergence_started_at = time.perf_counter()
        divergence_by_ticker = read_batch_divergence_enrichment(
            analysis_conn,
            normalized_tickers,
            normalized_as_of_date,
        )
        divergence_elapsed = time.perf_counter() - divergence_started_at

        candle_started_at = time.perf_counter()
        candle_by_ticker = read_batch_candlestick_enrichment(
            analysis_conn,
            normalized_tickers,
            normalized_as_of_date,
        )
        candle_elapsed = time.perf_counter() - candle_started_at

        for taxonomy_row in primary_rows:
            ticker = _normalize_ticker(taxonomy_row.ticker)
            metrics = metrics_by_ticker[ticker]
            dow_snapshot = dow_by_ticker[ticker]
            divergence_snapshot = divergence_by_ticker[ticker]
            candle_snapshot = candle_by_ticker[ticker]
            rows.append(
                DatacenterTickerSwingSnapshotRow(
                    signal_date=normalized_as_of_date,
                    taxonomy_version=str(taxonomy_row.taxonomy_version),
                    ticker=ticker,
                    primary_layer=str(taxonomy_row.layer),
                    primary_subindustry=str(taxonomy_row.subindustry),
                    close=metrics.close,
                    volume=metrics.volume,
                    return_5d=metrics.return_5d,
                    return_10d=metrics.return_10d,
                    return_20d=metrics.return_20d,
                    return_60d=metrics.return_60d,
                    ma10=metrics.ma10,
                    ema10=metrics.ema10,
                    ema20=metrics.ema20,
                    distance_to_ma10_pct=metrics.distance_to_ma10_pct,
                    distance_to_ema10_pct=metrics.distance_to_ema10_pct,
                    distance_to_ema20_pct=metrics.distance_to_ema20_pct,
                    above_ma10=metrics.above_ma10,
                    above_ema10=metrics.above_ema10,
                    above_ema20=metrics.above_ema20,
                    ema10_slope_positive=metrics.ema10_slope_positive,
                    ema20_slope_positive=metrics.ema20_slope_positive,
                    ema10_slope_lookback=metrics.ema10_slope_lookback,
                    ema20_slope_lookback=metrics.ema20_slope_lookback,
                    highest_close_20d=metrics.highest_close_20d,
                    volume_avg_20d=metrics.volume_avg_20d,
                    volume_vs_avg20=metrics.volume_vs_avg20,
                    latest_structure_label=dow_snapshot.latest_structure_label,
                    latest_structure_confirmed_as_of_date=dow_snapshot.latest_structure_confirmed_as_of_date,
                    bullish_divergence_signal=divergence_snapshot.bullish_divergence_signal,
                    bearish_divergence_signal=divergence_snapshot.bearish_divergence_signal,
                    hidden_bullish_divergence_signal=divergence_snapshot.hidden_bullish_divergence_signal,
                    hidden_bearish_divergence_signal=divergence_snapshot.hidden_bearish_divergence_signal,
                    bullish_candle_signal=candle_snapshot.bullish_candle_signal,
                    bearish_candle_signal=candle_snapshot.bearish_candle_signal,
                    breakout_signal=None,
                    fast_ema10_pullback_signal=None,
                    conservative_ema20_pullback_signal=None,
                    pullback_signal=None,
                    exit_risk_signal=None,
                    exit_reason=None,
                    exit_risk_severity=None,
                    price_data_status=metrics.price_data_status,
                    signal_version=signal_version,
                    run_id=run_id,
                    created_at_utc=created_at_utc,
                )
            )

    summary = {
        "taxonomy_rows": len(taxonomy_rows),
        "taxonomy_versions": len({str(row.taxonomy_version) for row in taxonomy_rows}),
        "primary_tickers": len(primary_rows),
        "duplicate_primary_rows": duplicate_primary_rows,
        "rows_prepared": len(rows),
        "missing_as_of_date_count": sum(1 for row in rows if row.price_data_status == "MISSING_AS_OF_DATE"),
        "missing_close_as_of_date_count": sum(1 for row in rows if row.price_data_status == "MISSING_CLOSE_AS_OF_DATE"),
        "insufficient_history_count": sum(1 for row in rows if row.price_data_status == "INSUFFICIENT_HISTORY"),
        "ok_price_count": sum(1 for row in rows if row.price_data_status == "OK"),
    }
    if profile:
        summary.update(
            {
                "profile_enabled": "1",
                "profile_taxonomy_load_seconds": f"{taxonomy_elapsed:.3f}",
                "profile_price_load_seconds": f"{price_elapsed:.3f}",
                "profile_metric_calc_seconds": f"{metric_elapsed:.3f}",
                "profile_dow_reader_seconds": f"{dow_elapsed:.3f}",
                "profile_divergence_reader_seconds": f"{divergence_elapsed:.3f}",
                "profile_candle_reader_seconds": f"{candle_elapsed:.3f}",
                "profile_total_seconds": f"{(time.perf_counter() - total_started_at):.3f}",
                "profile_tickers_processed": len(primary_rows),
                "profile_price_rows_loaded": fetched_price_row_count,
                "profile_rows_prepared": len(rows),
            }
        )
    return rows, summary


def write_ticker_swing_snapshot_rows(
    *,
    analysis_db_path: str | Path,
    rows: Sequence[DatacenterTickerSwingSnapshotRow],
    signal_date: str,
    signal_version: str,
    write_mode: str,
) -> dict[str, int]:
    normalized_signal_date = _parse_iso_date(signal_date, "signal_date")
    if write_mode not in {"insert-missing", "upsert", "replace-date"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    taxonomy_versions = sorted({row.taxonomy_version for row in rows})
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    inserted_count = 0
    updated_count = 0
    skipped_existing_count = 0
    deleted_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-date":
            if taxonomy_versions:
                placeholders = ", ".join("?" for _ in taxonomy_versions)
                cursor.execute(
                    f"""
                    DELETE FROM dc_ticker_swing_signal_daily
                    WHERE signal_date = ?
                      AND signal_version = ?
                      AND taxonomy_version IN ({placeholders})
                    """,
                    [normalized_signal_date, signal_version, *taxonomy_versions],
                )
                deleted_count = cursor.rowcount
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO dc_ticker_swing_signal_daily (
                        signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                        close, volume, return_5d, return_10d, return_20d, return_60d,
                        ma10, ema10, ema20, distance_to_ma10_pct, distance_to_ema10_pct,
                        distance_to_ema20_pct, above_ma10, above_ema10, above_ema20,
                        ema10_slope_positive, ema20_slope_positive, ema10_slope_lookback,
                        ema20_slope_lookback, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                        latest_structure_label, latest_structure_confirmed_as_of_date,
                        bullish_divergence_signal, bearish_divergence_signal,
                        hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                        bullish_candle_signal, bearish_candle_signal, breakout_signal,
                        fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                        pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                        signal_version, run_id, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _serialize_row(row),
                )
                inserted_count += 1
        else:
            existing_keys = {
                (
                    str(existing_row[0]),
                    str(existing_row[1]),
                    str(existing_row[2]),
                    str(existing_row[3]),
                )
                for existing_row in cursor.execute(
                    """
                    SELECT signal_date, taxonomy_version, ticker, signal_version
                    FROM dc_ticker_swing_signal_daily
                    WHERE signal_date = ?
                      AND signal_version = ?
                    """,
                    (normalized_signal_date, signal_version),
                ).fetchall()
            }
            for row in rows:
                key = _row_key(row)
                if write_mode == "insert-missing":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO dc_ticker_swing_signal_daily (
                            signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                            close, volume, return_5d, return_10d, return_20d, return_60d,
                            ma10, ema10, ema20, distance_to_ma10_pct, distance_to_ema10_pct,
                            distance_to_ema20_pct, above_ma10, above_ema10, above_ema20,
                            ema10_slope_positive, ema20_slope_positive, ema10_slope_lookback,
                            ema20_slope_lookback, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                            latest_structure_label, latest_structure_confirmed_as_of_date,
                            bullish_divergence_signal, bearish_divergence_signal,
                            hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                            bullish_candle_signal, bearish_candle_signal, breakout_signal,
                            fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                            pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _serialize_row(row),
                    )
                    if cursor.rowcount == 1:
                        inserted_count += 1
                    else:
                        skipped_existing_count += 1
                else:
                    cursor.execute(
                        """
                        INSERT INTO dc_ticker_swing_signal_daily (
                            signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                            close, volume, return_5d, return_10d, return_20d, return_60d,
                            ma10, ema10, ema20, distance_to_ma10_pct, distance_to_ema10_pct,
                            distance_to_ema20_pct, above_ma10, above_ema10, above_ema20,
                            ema10_slope_positive, ema20_slope_positive, ema10_slope_lookback,
                            ema20_slope_lookback, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                            latest_structure_label, latest_structure_confirmed_as_of_date,
                            bullish_divergence_signal, bearish_divergence_signal,
                            hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                            bullish_candle_signal, bearish_candle_signal, breakout_signal,
                            fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                            pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_date, taxonomy_version, ticker, signal_version)
                        DO UPDATE SET
                            primary_layer = excluded.primary_layer,
                            primary_subindustry = excluded.primary_subindustry,
                            close = excluded.close,
                            volume = excluded.volume,
                            return_5d = excluded.return_5d,
                            return_10d = excluded.return_10d,
                            return_20d = excluded.return_20d,
                            return_60d = excluded.return_60d,
                            ma10 = excluded.ma10,
                            ema10 = excluded.ema10,
                            ema20 = excluded.ema20,
                            distance_to_ma10_pct = excluded.distance_to_ma10_pct,
                            distance_to_ema10_pct = excluded.distance_to_ema10_pct,
                            distance_to_ema20_pct = excluded.distance_to_ema20_pct,
                            above_ma10 = excluded.above_ma10,
                            above_ema10 = excluded.above_ema10,
                            above_ema20 = excluded.above_ema20,
                            ema10_slope_positive = excluded.ema10_slope_positive,
                            ema20_slope_positive = excluded.ema20_slope_positive,
                            ema10_slope_lookback = excluded.ema10_slope_lookback,
                            ema20_slope_lookback = excluded.ema20_slope_lookback,
                            highest_close_20d = excluded.highest_close_20d,
                            volume_avg_20d = excluded.volume_avg_20d,
                            volume_vs_avg20 = excluded.volume_vs_avg20,
                            latest_structure_label = excluded.latest_structure_label,
                            latest_structure_confirmed_as_of_date = excluded.latest_structure_confirmed_as_of_date,
                            bullish_divergence_signal = excluded.bullish_divergence_signal,
                            bearish_divergence_signal = excluded.bearish_divergence_signal,
                            hidden_bullish_divergence_signal = excluded.hidden_bullish_divergence_signal,
                            hidden_bearish_divergence_signal = excluded.hidden_bearish_divergence_signal,
                            bullish_candle_signal = excluded.bullish_candle_signal,
                            bearish_candle_signal = excluded.bearish_candle_signal,
                            breakout_signal = excluded.breakout_signal,
                            fast_ema10_pullback_signal = excluded.fast_ema10_pullback_signal,
                            conservative_ema20_pullback_signal = excluded.conservative_ema20_pullback_signal,
                            pullback_signal = excluded.pullback_signal,
                            exit_risk_signal = excluded.exit_risk_signal,
                            exit_reason = excluded.exit_reason,
                            exit_risk_severity = excluded.exit_risk_severity,
                            price_data_status = excluded.price_data_status,
                            run_id = excluded.run_id,
                            created_at_utc = excluded.created_at_utc
                        """,
                        _serialize_row(row),
                    )
                    if key in existing_keys:
                        updated_count += 1
                    else:
                        inserted_count += 1
        conn.commit()
        return {
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "upserted_count": inserted_count + updated_count if write_mode == "upsert" else 0,
            "skipped_existing_count": skipped_existing_count,
            "deleted_count": deleted_count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        db_manager.close()


def _load_existing_ticker_rows(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    signal_version: str,
) -> list[sqlite3.Row]:
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT *
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date >= ?
              AND signal_date <= ?
              AND signal_version = ?
            ORDER BY signal_date ASC, taxonomy_version ASC, ticker ASC
            """,
            (start_date, end_date, signal_version),
        ).fetchall()
    finally:
        db_manager.close()


def _load_subindustry_state(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    primary_subindustry: str | None,
    signal_version: str,
) -> str | None:
    if primary_subindustry is None:
        return None
    row = conn.execute(
        """
        SELECT timing_state
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND group_type = 'subindustry'
          AND group_name = ?
          AND signal_version = ?
        """,
        (signal_date, taxonomy_version, primary_subindustry, signal_version),
    ).fetchone()
    if row is None or row["timing_state"] is None:
        return None
    return str(row["timing_state"])


def _classify_scanner_fields(
    row: sqlite3.Row,
    *,
    subindustry_state: str | None,
) -> dict[str, object]:
    close = None if row["close"] is None else float(row["close"])
    highest_close_20d = None if row["highest_close_20d"] is None else float(row["highest_close_20d"])
    volume_vs_avg20 = None if row["volume_vs_avg20"] is None else float(row["volume_vs_avg20"])
    return_5d = None if row["return_5d"] is None else float(row["return_5d"])
    return_10d = None if row["return_10d"] is None else float(row["return_10d"])
    return_20d = None if row["return_20d"] is None else float(row["return_20d"])
    return_60d = None if row["return_60d"] is None else float(row["return_60d"])
    ema10 = None if row["ema10"] is None else float(row["ema10"])
    ema20 = None if row["ema20"] is None else float(row["ema20"])
    ma10 = None if row["ma10"] is None else float(row["ma10"])
    latest_structure_label = None if row["latest_structure_label"] is None else str(row["latest_structure_label"])
    price_data_status = None if row["price_data_status"] is None else str(row["price_data_status"])
    entry_eligible = price_data_status in ENTRY_ELIGIBLE_PRICE_STATUSES
    bullish_subindustry = subindustry_state in {"BUY_ZONE", "ADD_ON_PULLBACK"}

    breakout_signal = int(
        entry_eligible
        and bullish_subindustry
        and _match_gte(close, highest_close_20d)  # type: ignore[arg-type]
        and _match_gt(volume_vs_avg20, 1.5)
        and _match_gt(return_5d, 0.0)
        and _match_gt(return_10d, 0.0)
        and close is not None
        and ema20 is not None
        and close > ema20
    )

    ema10_slope_positive = row["ema10_slope_positive"] is not None and int(row["ema10_slope_positive"]) == 1
    ema20_slope_positive = row["ema20_slope_positive"] is not None and int(row["ema20_slope_positive"]) == 1

    fast_ema10_pullback_signal = int(
        entry_eligible
        and bullish_subindustry
        and _match_gt(return_10d, 0.0)
        and close is not None
        and ema10 is not None
        and ema20 is not None
        and close >= (ema10 * 0.97)
        and close <= (ema10 * 1.03)
        and ema10_slope_positive
        and _match_lte(return_5d, 0.0)
        and _match_gte(return_5d, -0.06)
        and close >= (ema20 * 0.98)
    )

    conservative_ema20_pullback_signal = int(
        entry_eligible
        and bullish_subindustry
        and _match_gt(return_20d, 0.0)
        and _match_gt(return_60d, 0.0)
        and close is not None
        and ema20 is not None
        and close >= (ema20 * 0.98)
        and close <= (ema20 * 1.03)
        and ema20_slope_positive
        and _match_lte(return_5d, 0.0)
        and _match_gte(return_5d, -0.08)
    )

    pullback_signal = int(
        fast_ema10_pullback_signal == 1 or conservative_ema20_pullback_signal == 1
    )

    exit_reasons: list[str] = []
    if close is not None and ema20 is not None and close < ema20:
        exit_reasons.append("close_below_ema20")
    if _match_lt(return_10d, -0.08):
        exit_reasons.append("return_10d_lt_minus_8pct")
    if latest_structure_label == "LL":
        exit_reasons.append("latest_structure_label_ll")
    if subindustry_state == "EXIT_ZONE":
        exit_reasons.append("subindustry_exit_zone")
    if subindustry_state == "TRIM_WATCH" and close is not None and ma10 is not None and close < ma10:
        exit_reasons.append("trim_watch_close_below_ma10")
    exit_risk_signal = int(bool(exit_reasons))
    exit_reason = ";".join(exit_reasons) if exit_reasons else None

    return {
        "breakout_signal": breakout_signal,
        "fast_ema10_pullback_signal": fast_ema10_pullback_signal,
        "conservative_ema20_pullback_signal": conservative_ema20_pullback_signal,
        "pullback_signal": pullback_signal,
        "exit_risk_signal": exit_risk_signal,
        "exit_reason": exit_reason,
        "exit_risk_severity": classify_exit_risk_severity(exit_reason) if exit_risk_signal == 1 else None,
    }


def classify_exit_risk_severity(exit_reason: str | None) -> str | None:
    if exit_reason is None:
        return None
    reason_codes = [code.strip() for code in exit_reason.split(";") if code.strip()]
    if not reason_codes:
        return None
    reason_set = set(reason_codes)
    if (
        "latest_structure_label_ll" in reason_set
        or "return_10d_lt_minus_8pct" in reason_set
        or ("subindustry_exit_zone" in reason_set and "close_below_ema20" in reason_set)
        or len(reason_codes) >= 3
    ):
        return "HIGH"
    if (
        "subindustry_exit_zone" in reason_set
        or "trim_watch_close_below_ma10" in reason_set
        or "close_below_ema20" in reason_set
    ):
        return "MEDIUM"
    return "LOW"


def build_ticker_scanner_updates(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    signal_version: str,
    run_id: str,
    created_at_utc: str,
) -> tuple[list[dict[str, object]], dict[str, int | str]]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    rows = _load_existing_ticker_rows(
        analysis_db_path=analysis_db_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
    )
    breakout_count = 0
    fast_count = 0
    conservative_count = 0
    pullback_count = 0
    exit_count = 0
    updates: list[dict[str, object]] = []
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in rows:
            subindustry_state = _load_subindustry_state(
                conn,
                signal_date=str(row["signal_date"]),
                taxonomy_version=str(row["taxonomy_version"]),
                primary_subindustry=None if row["primary_subindustry"] is None else str(row["primary_subindustry"]),
                signal_version=str(row["signal_version"]),
            )
            scanner_fields = _classify_scanner_fields(row, subindustry_state=subindustry_state)
            breakout_count += int(scanner_fields["breakout_signal"])
            fast_count += int(scanner_fields["fast_ema10_pullback_signal"])
            conservative_count += int(scanner_fields["conservative_ema20_pullback_signal"])
            pullback_count += int(scanner_fields["pullback_signal"])
            exit_count += int(scanner_fields["exit_risk_signal"])
            updates.append(
                {
                    "signal_date": str(row["signal_date"]),
                    "taxonomy_version": str(row["taxonomy_version"]),
                    "ticker": str(row["ticker"]),
                    "signal_version": str(row["signal_version"]),
                    **scanner_fields,
                    "run_id": run_id,
                    "created_at_utc": created_at_utc,
                    "existing_breakout_signal": row["breakout_signal"],
                    "existing_fast_ema10_pullback_signal": row["fast_ema10_pullback_signal"],
                    "existing_conservative_ema20_pullback_signal": row["conservative_ema20_pullback_signal"],
                    "existing_pullback_signal": row["pullback_signal"],
                    "existing_exit_risk_signal": row["exit_risk_signal"],
                    "existing_exit_reason": row["exit_reason"],
                    "existing_exit_risk_severity": row["exit_risk_severity"],
                }
            )
    high_exit_count = sum(1 for row in updates if row["exit_risk_severity"] == "HIGH")
    medium_exit_count = sum(1 for row in updates if row["exit_risk_severity"] == "MEDIUM")
    low_exit_count = sum(1 for row in updates if row["exit_risk_severity"] == "LOW")
    return updates, {
        "missing_base_row_count": 0,
        "breakout_count": breakout_count,
        "fast_ema10_pullback_count": fast_count,
        "conservative_ema20_pullback_count": conservative_count,
        "pullback_count": pullback_count,
        "exit_risk_count": exit_count,
        "high_exit_risk_count": high_exit_count,
        "medium_exit_risk_count": medium_exit_count,
        "low_exit_risk_count": low_exit_count,
    }


def write_ticker_scanner_updates(
    *,
    analysis_db_path: str | Path,
    updates: Sequence[dict[str, object]],
    start_date: str,
    end_date: str,
    signal_version: str,
    write_mode: str,
) -> dict[str, int]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"update-existing", "replace-scanner-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    updated_count = 0
    cleared_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-scanner-range":
            cursor.execute(
                """
                UPDATE dc_ticker_swing_signal_daily
                SET breakout_signal = NULL,
                    fast_ema10_pullback_signal = NULL,
                    conservative_ema20_pullback_signal = NULL,
                    pullback_signal = NULL,
                    exit_risk_signal = NULL,
                    exit_reason = NULL,
                    exit_risk_severity = NULL
                WHERE signal_date >= ?
                  AND signal_date <= ?
                  AND signal_version = ?
                """,
                (normalized_start_date, normalized_end_date, signal_version),
            )
            cleared_count = cursor.rowcount
            filtered_updates = list(updates)
        else:
            filtered_updates = [
                row
                for row in updates
                if row["existing_breakout_signal"] != row["breakout_signal"]
                or row["existing_fast_ema10_pullback_signal"] != row["fast_ema10_pullback_signal"]
                or row["existing_conservative_ema20_pullback_signal"] != row["conservative_ema20_pullback_signal"]
                or row["existing_pullback_signal"] != row["pullback_signal"]
                or row["existing_exit_risk_signal"] != row["exit_risk_signal"]
                or row["existing_exit_reason"] != row["exit_reason"]
                or row["existing_exit_risk_severity"] != row["exit_risk_severity"]
            ]
        for row in filtered_updates:
            cursor.execute(
                """
                UPDATE dc_ticker_swing_signal_daily
                SET breakout_signal = ?,
                    fast_ema10_pullback_signal = ?,
                    conservative_ema20_pullback_signal = ?,
                    pullback_signal = ?,
                    exit_risk_signal = ?,
                    exit_reason = ?,
                    exit_risk_severity = ?,
                    run_id = ?,
                    created_at_utc = ?
                WHERE signal_date = ?
                  AND taxonomy_version = ?
                  AND ticker = ?
                  AND signal_version = ?
                """,
                (
                    row["breakout_signal"],
                    row["fast_ema10_pullback_signal"],
                    row["conservative_ema20_pullback_signal"],
                    row["pullback_signal"],
                    row["exit_risk_signal"],
                    row["exit_reason"],
                    row["exit_risk_severity"],
                    row["run_id"],
                    row["created_at_utc"],
                    row["signal_date"],
                    row["taxonomy_version"],
                    row["ticker"],
                    row["signal_version"],
                ),
            )
            updated_count += cursor.rowcount
        conn.commit()
        return {
            "updated_count": updated_count,
            "cleared_count": cleared_count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        db_manager.close()


def persist_datacenter_ticker_swing_snapshots(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    as_of_date: str,
    market: str | None,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    write_mode: str = "upsert",
    max_valid_price_rows: int = DEFAULT_MAX_VALID_PRICE_ROWS,
    profile: bool = False,
) -> dict[str, int | str]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if write_mode not in {"insert-missing", "upsert", "replace-date"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    resolved_run_id = build_ticker_swing_run_id(
        as_of_date=normalized_as_of_date,
        signal_version=signal_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    total_started_at = time.perf_counter()

    rows, prep_summary = build_ticker_swing_snapshot_rows(
        analysis_db_path=analysis_db_path,
        price_db_path=price_db_path,
        taxonomy_csv_path=taxonomy_csv_path,
        as_of_date=normalized_as_of_date,
        market=market,
        signal_version=signal_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        max_valid_price_rows=max_valid_price_rows,
        profile=profile,
    )
    write_started_at = time.perf_counter()
    write_summary = write_ticker_swing_snapshot_rows(
        analysis_db_path=analysis_db_path,
        rows=rows,
        signal_date=normalized_as_of_date,
        signal_version=signal_version,
        write_mode=write_mode,
    )
    summary = {
        "signal_date": normalized_as_of_date,
        "market": market if market is not None else "ALL",
        "write_mode": write_mode,
        "signal_version": signal_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }
    if profile:
        summary["profile_db_write_seconds"] = f"{(time.perf_counter() - write_started_at):.3f}"
        summary["profile_total_seconds"] = f"{(time.perf_counter() - total_started_at):.3f}"
    return summary


def persist_datacenter_ticker_scanner_signals(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str | None = None,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    write_mode: str = "update-existing",
) -> dict[str, int | str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date or start_date, "end_date")
    if write_mode not in {"update-existing", "replace-scanner-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    resolved_run_id = build_ticker_swing_run_id(
        as_of_date=normalized_end_date,
        signal_version=signal_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    updates, prep_summary = build_ticker_scanner_updates(
        analysis_db_path=analysis_db_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
    )
    write_summary = write_ticker_scanner_updates(
        analysis_db_path=analysis_db_path,
        updates=updates,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
        write_mode=write_mode,
    )
    return {
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "write_mode": write_mode,
        "signal_version": signal_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }
