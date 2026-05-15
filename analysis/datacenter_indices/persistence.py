from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from analysis.database_manager import DatabaseManager

from .calculator import DatacenterGroupIndexRow, DatacenterPriceRow, calculate_datacenter_group_indices
from .taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv


DATACENTER_INDEX_SUMMARY_ORDER = [
    "taxonomy_version",
    "market",
    "index_base_date",
    "start_date",
    "end_date",
    "write_mode",
    "run_id",
    "taxonomy_rows",
    "taxonomy_unique_tickers",
    "benchmark_tickers",
    "requested_price_tickers",
    "found_price_tickers",
    "missing_price_tickers",
    "price_rows_read",
    "calculated_rows_total",
    "rows_in_write_range",
    "rows_deleted",
    "rows_inserted",
    "group_count_total",
    "ecosystem_group_count",
    "layer_group_count",
    "subindustry_group_count",
    "data_quality_ok_rows",
    "data_quality_partial_rows",
    "data_quality_too_small_rows",
    "data_quality_no_data_rows",
    "relative_strength_spy_non_null_rows",
    "relative_strength_qqq_non_null_rows",
    "write_status",
]

GROUP_TYPE_ORDER = {
    "ecosystem": 0,
    "layer": 1,
    "subindustry": 2,
}

CREATED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class DatacenterOhlcvReadResult:
    price_rows: list[DatacenterPriceRow]
    requested_tickers: tuple[str, ...]
    found_tickers: tuple[str, ...]


def _normalize_ticker(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _validate_created_at_utc(value: str) -> str:
    if not CREATED_AT_UTC_RE.match(value):
        raise ValueError(
            f"Invalid created_at_utc: {value}. Expected YYYY-MM-DDTHH:MM:SSZ"
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(
            f"Invalid created_at_utc: {value}. Expected YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return value


def resolve_created_at_utc(created_at_utc: str | None = None) -> str:
    if created_at_utc is not None:
        return _validate_created_at_utc(created_at_utc)
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_datacenter_run_id(
    taxonomy_version: str,
    index_base_date: str,
    start_date: str,
    end_date: str,
    run_id: str | None = None,
) -> str:
    if run_id is not None:
        return run_id
    compact_base = index_base_date.replace("-", "")
    compact_start = start_date.replace("-", "")
    compact_end = end_date.replace("-", "")
    value = f"DC_INDEX_{taxonomy_version}_BASE{compact_base}_{compact_start}_{compact_end}"
    return value.replace(" ", "_").replace("-", "")


def format_datacenter_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in DATACENTER_INDEX_SUMMARY_ORDER]


def load_datacenter_taxonomy_for_version(
    taxonomy_csv: str | Path,
    taxonomy_version: str,
) -> list[DatacenterTaxonomyRow]:
    return load_datacenter_taxonomy_csv(
        taxonomy_csv,
        expected_taxonomy_version=taxonomy_version,
    )


def read_ohlcv_price_rows(
    *,
    ohlcv_db_path: str | Path,
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
    market: str | None,
    end_date: str,
    spy_ticker: str = "SPY",
    qqq_ticker: str = "QQQ",
) -> DatacenterOhlcvReadResult:
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    taxonomy_tickers = {_normalize_ticker(row.ticker) for row in taxonomy_rows}
    normalized_spy_ticker = _normalize_ticker(spy_ticker)
    normalized_qqq_ticker = _normalize_ticker(qqq_ticker)
    requested_tickers = tuple(
        sorted(taxonomy_tickers | {normalized_spy_ticker, normalized_qqq_ticker})
    )
    if not requested_tickers:
        return DatacenterOhlcvReadResult(price_rows=[], requested_tickers=(), found_tickers=())

    placeholders = ", ".join("?" for _ in requested_tickers)
    if market is not None:
        params = [market, normalized_end_date, *requested_tickers]
        query = f"""
            SELECT TRIM(osake) AS osake,
                   pvm,
                   close
            FROM osakedata
            WHERE market = ?
              AND pvm <= ?
              AND UPPER(TRIM(osake)) IN ({placeholders})
            ORDER BY UPPER(TRIM(osake)) ASC, pvm ASC
        """
    else:
        params = [normalized_end_date, *requested_tickers]
        query = f"""
            SELECT TRIM(osake) AS osake,
                   pvm,
                   close
            FROM osakedata
            WHERE pvm <= ?
              AND UPPER(TRIM(osake)) IN ({placeholders})
            ORDER BY UPPER(TRIM(osake)) ASC, pvm ASC
        """

    price_rows: list[DatacenterPriceRow] = []
    found_tickers: set[str] = set()
    with sqlite3.connect(ohlcv_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    for row in rows:
        ticker = _normalize_ticker(row["osake"])
        date_value = str(row["pvm"])
        close_value = row["close"]
        if close_value is None:
            raise ValueError(
                f"NULL close for ticker {ticker} on {date_value}"
            )
        found_tickers.add(ticker)
        price_rows.append(
            DatacenterPriceRow(
                ticker=ticker,
                date=date_value,
                close=float(close_value),
            )
        )
    return DatacenterOhlcvReadResult(
        price_rows=price_rows,
        requested_tickers=requested_tickers,
        found_tickers=tuple(sorted(found_tickers)),
    )


def filter_rows_to_write_range(
    rows: Sequence[DatacenterGroupIndexRow],
    *,
    start_date: str,
    end_date: str,
) -> list[DatacenterGroupIndexRow]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    return [
        row
        for row in rows
        if normalized_start_date <= row.index_date <= normalized_end_date
    ]


def write_datacenter_group_index_rows(
    *,
    analysis_db_path: str | Path,
    rows: Sequence[DatacenterGroupIndexRow],
    taxonomy_version: str,
    start_date: str,
    end_date: str,
    run_id: str,
    created_at_utc: str,
    write_mode: str,
) -> tuple[int, int]:
    if write_mode != "replace-range":
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    validated_created_at_utc = _validate_created_at_utc(created_at_utc)

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.index_date,
            GROUP_TYPE_ORDER[row.group_type],
            row.group_name,
        ),
    )

    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute(
            """
            DELETE FROM dc_group_index_daily
            WHERE taxonomy_version = ?
              AND index_date >= ?
              AND index_date <= ?
            """,
            (taxonomy_version, normalized_start_date, normalized_end_date),
        )
        rows_deleted = cursor.rowcount
        rows_inserted = 0
        for row in sorted_rows:
            cursor.execute(
                """
                INSERT INTO dc_group_index_daily (
                    index_date,
                    taxonomy_version,
                    group_type,
                    group_name,
                    member_count,
                    eligible_count,
                    ma50_eligible_count,
                    ma200_eligible_count,
                    daily_return_equal,
                    median_return,
                    pct_positive,
                    pct_above_ma50,
                    pct_above_ma200,
                    index_level_equal,
                    return_20d,
                    return_60d,
                    return_120d,
                    volatility_20d,
                    volatility_60d,
                    relative_strength_spy_60d,
                    relative_strength_qqq_60d,
                    data_quality_status,
                    calc_version,
                    run_id,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.index_date,
                    row.taxonomy_version,
                    row.group_type,
                    row.group_name,
                    row.member_count,
                    row.eligible_count,
                    row.ma50_eligible_count,
                    row.ma200_eligible_count,
                    row.daily_return_equal,
                    row.median_return,
                    row.pct_positive,
                    row.pct_above_ma50,
                    row.pct_above_ma200,
                    row.index_level_equal,
                    row.return_20d,
                    row.return_60d,
                    row.return_120d,
                    row.volatility_20d,
                    row.volatility_60d,
                    row.relative_strength_spy_60d,
                    row.relative_strength_qqq_60d,
                    row.data_quality_status,
                    row.calc_version,
                    run_id,
                    validated_created_at_utc,
                ),
            )
            rows_inserted += 1
        conn.commit()
        return rows_deleted, rows_inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        db_manager.close()


def run_datacenter_indices(
    *,
    ohlcv_db_path: str | Path,
    analysis_db_path: str | Path,
    taxonomy_csv: str | Path,
    taxonomy_version: str,
    market: str | None = None,
    index_base_date: str = "2020-01-01",
    start_date: str,
    end_date: str,
    write_mode: str,
    spy_ticker: str = "SPY",
    qqq_ticker: str = "QQQ",
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, int | str]:
    normalized_index_base_date = _parse_iso_date(index_base_date, "index_base_date")
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date < normalized_index_base_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is earlier than index_base_date {normalized_index_base_date}"
        )
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    if write_mode != "replace-range":
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    normalized_spy_ticker = _normalize_ticker(spy_ticker)
    normalized_qqq_ticker = _normalize_ticker(qqq_ticker)
    resolved_run_id = build_datacenter_run_id(
        taxonomy_version=taxonomy_version,
        index_base_date=normalized_index_base_date,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)

    taxonomy_rows = load_datacenter_taxonomy_for_version(
        taxonomy_csv=taxonomy_csv,
        taxonomy_version=taxonomy_version,
    )
    ohlcv_result = read_ohlcv_price_rows(
        ohlcv_db_path=ohlcv_db_path,
        taxonomy_rows=taxonomy_rows,
        market=market,
        end_date=normalized_end_date,
        spy_ticker=normalized_spy_ticker,
        qqq_ticker=normalized_qqq_ticker,
    )
    calculated_rows = calculate_datacenter_group_indices(
        taxonomy_rows=taxonomy_rows,
        price_rows=ohlcv_result.price_rows,
        taxonomy_version=taxonomy_version,
        start_date=normalized_index_base_date,
        end_date=normalized_end_date,
        spy_ticker=normalized_spy_ticker,
        qqq_ticker=normalized_qqq_ticker,
    )
    rows_in_write_range = filter_rows_to_write_range(
        calculated_rows,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
    )
    rows_deleted, rows_inserted = write_datacenter_group_index_rows(
        analysis_db_path=analysis_db_path,
        rows=rows_in_write_range,
        taxonomy_version=taxonomy_version,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        write_mode=write_mode,
    )

    distinct_groups = {(row.group_type, row.group_name) for row in rows_in_write_range}
    summary = {
        "taxonomy_version": taxonomy_version,
        "market": market if market is not None else "ALL",
        "index_base_date": normalized_index_base_date,
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "write_mode": write_mode,
        "run_id": resolved_run_id,
        "taxonomy_rows": len(taxonomy_rows),
        "taxonomy_unique_tickers": len({_normalize_ticker(row.ticker) for row in taxonomy_rows}),
        "benchmark_tickers": f"{normalized_spy_ticker},{normalized_qqq_ticker}",
        "requested_price_tickers": len(ohlcv_result.requested_tickers),
        "found_price_tickers": len(ohlcv_result.found_tickers),
        "missing_price_tickers": len(set(ohlcv_result.requested_tickers) - set(ohlcv_result.found_tickers)),
        "price_rows_read": len(ohlcv_result.price_rows),
        "calculated_rows_total": len(calculated_rows),
        "rows_in_write_range": len(rows_in_write_range),
        "rows_deleted": rows_deleted,
        "rows_inserted": rows_inserted,
        "group_count_total": len(distinct_groups),
        "ecosystem_group_count": len({group for group in distinct_groups if group[0] == "ecosystem"}),
        "layer_group_count": len({group for group in distinct_groups if group[0] == "layer"}),
        "subindustry_group_count": len({group for group in distinct_groups if group[0] == "subindustry"}),
        "data_quality_ok_rows": sum(1 for row in rows_in_write_range if row.data_quality_status == "OK"),
        "data_quality_partial_rows": sum(1 for row in rows_in_write_range if row.data_quality_status == "PARTIAL_DATA"),
        "data_quality_too_small_rows": sum(1 for row in rows_in_write_range if row.data_quality_status == "TOO_SMALL"),
        "data_quality_no_data_rows": sum(1 for row in rows_in_write_range if row.data_quality_status == "NO_DATA"),
        "relative_strength_spy_non_null_rows": sum(1 for row in rows_in_write_range if row.relative_strength_spy_60d is not None),
        "relative_strength_qqq_non_null_rows": sum(1 for row in rows_in_write_range if row.relative_strength_qqq_60d is not None),
        "write_status": "OK",
    }
    return summary
