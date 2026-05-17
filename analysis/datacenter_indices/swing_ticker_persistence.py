from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from analysis.database_manager import DatabaseManager

from .persistence import resolve_created_at_utc
from .swing_analysis_readers import read_ticker_analysis_enrichment
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
    return [f"SUMMARY {key}={summary[key]}" for key in TICKER_SWING_SUMMARY_ORDER]


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
            ORDER BY pvm DESC
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
) -> tuple[list[DatacenterTickerSwingSnapshotRow], dict[str, int | str]]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    primary_rows, duplicate_primary_rows = _select_primary_taxonomy_rows(taxonomy_rows)

    rows: list[DatacenterTickerSwingSnapshotRow] = []
    with sqlite3.connect(analysis_db_path) as analysis_conn:
        analysis_conn.row_factory = sqlite3.Row
        for taxonomy_row in primary_rows:
            ohlcv_rows = load_bounded_ticker_ohlcv_history(
                price_db_path=price_db_path,
                ticker=taxonomy_row.ticker,
                market=market,
                as_of_date=normalized_as_of_date,
                max_valid_price_rows=max_valid_price_rows,
            )
            metrics = calculate_ticker_swing_metrics(ohlcv_rows, normalized_as_of_date)
            enrichment = read_ticker_analysis_enrichment(
                analysis_conn,
                _normalize_ticker(taxonomy_row.ticker),
                market,
                normalized_as_of_date,
            )
            rows.append(
                DatacenterTickerSwingSnapshotRow(
                    signal_date=normalized_as_of_date,
                    taxonomy_version=str(taxonomy_row.taxonomy_version),
                    ticker=_normalize_ticker(taxonomy_row.ticker),
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
                    latest_structure_label=enrichment.dow.latest_structure_label,
                    latest_structure_confirmed_as_of_date=enrichment.dow.latest_structure_confirmed_as_of_date,
                    bullish_divergence_signal=enrichment.divergence.bullish_divergence_signal,
                    bearish_divergence_signal=enrichment.divergence.bearish_divergence_signal,
                    hidden_bullish_divergence_signal=enrichment.divergence.hidden_bullish_divergence_signal,
                    hidden_bearish_divergence_signal=enrichment.divergence.hidden_bearish_divergence_signal,
                    bullish_candle_signal=enrichment.candlestick.bullish_candle_signal,
                    bearish_candle_signal=enrichment.candlestick.bearish_candle_signal,
                    breakout_signal=None,
                    fast_ema10_pullback_signal=None,
                    conservative_ema20_pullback_signal=None,
                    pullback_signal=None,
                    exit_risk_signal=None,
                    exit_reason=None,
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
                        pullback_signal, exit_risk_signal, exit_reason, price_data_status,
                        signal_version, run_id, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            pullback_signal, exit_risk_signal, exit_reason, price_data_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            pullback_signal, exit_risk_signal, exit_reason, price_data_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    )
    write_summary = write_ticker_swing_snapshot_rows(
        analysis_db_path=analysis_db_path,
        rows=rows,
        signal_date=normalized_as_of_date,
        signal_version=signal_version,
        write_mode=write_mode,
    )
    return {
        "signal_date": normalized_as_of_date,
        "market": market if market is not None else "ALL",
        "write_mode": write_mode,
        "signal_version": signal_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }
