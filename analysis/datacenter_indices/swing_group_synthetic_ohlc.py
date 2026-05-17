from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import pstdev
from typing import Sequence

from analysis.database_manager import DatabaseManager

from .persistence import resolve_created_at_utc
from .taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv


DEFAULT_CALC_VERSION = "DC_SWING_OHLC_V1"
DEFAULT_RELATIVE_BASE_WINDOW = 20
DEFAULT_MIN_ELIGIBLE_COUNT = 3
DEFAULT_MIN_COVERAGE_RATIO = 0.60

SYNTHETIC_OHLC_SUMMARY_ORDER = [
    "start_date",
    "end_date",
    "market",
    "write_mode",
    "calc_version",
    "run_id",
    "taxonomy_rows",
    "taxonomy_versions",
    "group_types",
    "group_rows",
    "inserted_count",
    "updated_count",
    "upserted_count",
    "skipped_existing_count",
    "deleted_count",
    "ok_group_date_count",
    "partial_data_group_date_count",
    "too_small_group_date_count",
    "no_data_group_date_count",
    "validation_status",
]

RELATIVE_OHLC_SUMMARY_ORDER = [
    "start_date",
    "end_date",
    "market",
    "write_mode",
    "calc_version",
    "relative_base_window",
    "run_id",
    "taxonomy_rows",
    "taxonomy_versions",
    "group_types",
    "updated_count",
    "missing_base_row_count",
    "cleared_count",
    "relative_rows_with_values",
    "relative_rows_without_eligible_tickers",
    "validation_status",
]

GROUP_TYPE_ORDER = {
    "layer": 0,
    "subindustry": 1,
}


@dataclass(frozen=True)
class DatacenterGroupSyntheticOhlcRow:
    ohlc_date: str
    taxonomy_version: str
    group_type: str
    group_name: str
    member_count: int
    eligible_count: int
    synthetic_open: float | None
    synthetic_high: float | None
    synthetic_low: float | None
    synthetic_close: float | None
    synthetic_volume: float | None
    ma20: float | None
    ema20: float | None
    distance_to_ema20_pct: float | None
    volatility_20d: float | None
    pivot_radius: int | None
    latest_pivot_high_date: str | None
    latest_pivot_high_value: float | None
    latest_pivot_low_date: str | None
    latest_pivot_low_value: float | None
    latest_structure_label: str | None
    trend_classification: str | None
    relative_base_window: int | None
    relative_open_20: float | None
    relative_high_20: float | None
    relative_low_20: float | None
    relative_close_20: float | None
    relative_upper_wick_20: float | None
    relative_lower_wick_20: float | None
    relative_close_extension_20: float | None
    relative_high_extension_20: float | None
    relative_low_extension_20: float | None
    relative_eligible_count: int | None
    data_quality_status: str
    calc_version: str
    run_id: str
    created_at_utc: str


@dataclass(frozen=True)
class _TickerPriceRow:
    ticker: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(frozen=True)
class _TickerDailySyntheticInput:
    open_return: float
    high_return: float
    low_return: float
    close_return: float
    volume: float | None


@dataclass(frozen=True)
class _TickerDailyRelativeInput:
    relative_open: float
    relative_high: float
    relative_low: float
    relative_close: float


def _normalize_ticker(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def build_group_synthetic_ohlc_run_id(
    *,
    start_date: str,
    end_date: str,
    calc_version: str,
    run_id: str | None = None,
) -> str:
    if run_id is not None:
        return run_id
    return (
        f"DC_GROUP_SYNTH_OHLC_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{calc_version}"
        .replace(" ", "_")
    )


def format_group_synthetic_ohlc_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in SYNTHETIC_OHLC_SUMMARY_ORDER]


def format_group_relative_ohlc_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in RELATIVE_OHLC_SUMMARY_ORDER]


def _load_taxonomy_rows(taxonomy_csv_path: str | Path) -> list[DatacenterTaxonomyRow]:
    return load_datacenter_taxonomy_csv(taxonomy_csv_path)


def _build_group_definitions(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
) -> list[tuple[str, str, tuple[str, ...]]]:
    layer_map: dict[str, set[str]] = {}
    subindustry_map: dict[str, set[str]] = {}
    for row in taxonomy_rows:
        ticker = _normalize_ticker(row.ticker)
        layer_map.setdefault(str(row.layer), set()).add(ticker)
        subindustry_map.setdefault(str(row.subindustry), set()).add(ticker)
    groups: list[tuple[str, str, tuple[str, ...]]] = []
    groups.extend(
        ("layer", layer, tuple(sorted(tickers)))
        for layer, tickers in sorted(layer_map.items())
    )
    groups.extend(
        ("subindustry", subindustry, tuple(sorted(tickers)))
        for subindustry, tickers in sorted(subindustry_map.items())
    )
    return groups


def _load_price_rows(
    *,
    price_db_path: str | Path,
    tickers: Sequence[str],
    market: str | None,
    end_date: str,
) -> list[_TickerPriceRow]:
    if not tickers:
        return []
    placeholders = ", ".join("?" for _ in tickers)
    params: list[object] = [end_date, *tickers]
    market_sql = ""
    if market is not None:
        market_sql = " AND market = ?"
        params = [end_date, market, *tickers]
    query = f"""
        SELECT TRIM(osake) AS osake, pvm, open, high, low, close, volume
        FROM osakedata
        WHERE pvm <= ?
          {market_sql}
          AND UPPER(TRIM(osake)) IN ({placeholders})
        ORDER BY UPPER(TRIM(osake)) ASC, pvm ASC
    """
    with sqlite3.connect(price_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [
        _TickerPriceRow(
            ticker=_normalize_ticker(row["osake"]),
            date=str(row["pvm"]),
            open=None if row["open"] is None else float(row["open"]),
            high=None if row["high"] is None else float(row["high"]),
            low=None if row["low"] is None else float(row["low"]),
            close=None if row["close"] is None else float(row["close"]),
            volume=None if row["volume"] is None else float(row["volume"]),
        )
        for row in rows
    ]


def _build_in_range_dates(
    all_dates: Sequence[str],
    *,
    start_date: str,
    end_date: str,
) -> list[str]:
    return [value for value in all_dates if start_date <= value <= end_date]


def _build_ticker_daily_inputs(
    price_rows: Sequence[_TickerPriceRow],
) -> tuple[dict[str, dict[str, _TickerDailySyntheticInput]], list[str]]:
    rows_by_ticker: dict[str, list[_TickerPriceRow]] = {}
    all_dates: set[str] = set()
    for row in price_rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)
        all_dates.add(row.date)

    result: dict[str, dict[str, _TickerDailySyntheticInput]] = {}
    for ticker, ticker_rows in rows_by_ticker.items():
        previous_valid_close: float | None = None
        daily_map: dict[str, _TickerDailySyntheticInput] = {}
        for row in sorted(ticker_rows, key=lambda item: item.date):
            if (
                row.open is not None
                and row.high is not None
                and row.low is not None
                and row.close is not None
                and previous_valid_close is not None
                and previous_valid_close != 0
            ):
                daily_map[row.date] = _TickerDailySyntheticInput(
                    open_return=(row.open / previous_valid_close) - 1.0,
                    high_return=(row.high / previous_valid_close) - 1.0,
                    low_return=(row.low / previous_valid_close) - 1.0,
                    close_return=(row.close / previous_valid_close) - 1.0,
                    volume=row.volume,
                )
            if row.close is not None:
                previous_valid_close = row.close
        result[ticker] = daily_map
    return result, sorted(all_dates)


def _build_ticker_daily_relative_inputs(
    price_rows: Sequence[_TickerPriceRow],
    *,
    relative_base_window: int,
) -> tuple[dict[str, dict[str, _TickerDailyRelativeInput]], list[str]]:
    rows_by_ticker: dict[str, list[_TickerPriceRow]] = {}
    all_dates: set[str] = set()
    for row in price_rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)
        all_dates.add(row.date)

    result: dict[str, dict[str, _TickerDailyRelativeInput]] = {}
    for ticker, ticker_rows in rows_by_ticker.items():
        valid_close_history: list[float] = []
        daily_map: dict[str, _TickerDailyRelativeInput] = {}
        for row in sorted(ticker_rows, key=lambda item: item.date):
            if row.close is not None:
                valid_close_history.append(row.close)
            if (
                row.open is not None
                and row.high is not None
                and row.low is not None
                and row.close is not None
                and len(valid_close_history) >= relative_base_window
            ):
                rolling_base = (
                    sum(valid_close_history[-relative_base_window:]) / float(relative_base_window)
                )
                if rolling_base != 0:
                    daily_map[row.date] = _TickerDailyRelativeInput(
                        relative_open=row.open / rolling_base,
                        relative_high=row.high / rolling_base,
                        relative_low=row.low / rolling_base,
                        relative_close=row.close / rolling_base,
                    )
        result[ticker] = daily_map
    return result, sorted(all_dates)


def _calculate_data_quality_status(
    *,
    member_count: int,
    eligible_count: int,
    min_eligible_count: int,
    min_coverage_ratio: float,
) -> str:
    if member_count == 0 or eligible_count == 0:
        return "NO_DATA"
    if eligible_count < min_eligible_count:
        return "TOO_SMALL"
    coverage_ratio = float(eligible_count) / float(member_count)
    if coverage_ratio < min_coverage_ratio:
        return "PARTIAL_DATA"
    return "OK"


def _distance_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) - 1.0


def _calculate_ema_series(values: Sequence[float], window: int) -> list[float]:
    if len(values) < window:
        return []
    alpha = 2.0 / float(window + 1)
    ema = sum(values[:window]) / float(window)
    series = [ema]
    for value in values[window:]:
        ema = (value * alpha) + (ema * (1.0 - alpha))
        series.append(ema)
    return series


def build_group_synthetic_ohlc_rows(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    start_date: str,
    end_date: str,
    market: str | None,
    calc_version: str,
    run_id: str,
    created_at_utc: str,
    min_eligible_count: int = DEFAULT_MIN_ELIGIBLE_COUNT,
    min_coverage_ratio: float = DEFAULT_MIN_COVERAGE_RATIO,
) -> tuple[list[DatacenterGroupSyntheticOhlcRow], dict[str, int | str]]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )

    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    taxonomy_versions = sorted({str(row.taxonomy_version) for row in taxonomy_rows})
    output_rows: list[DatacenterGroupSyntheticOhlcRow] = []

    for taxonomy_version in taxonomy_versions:
        version_rows = [
            row for row in taxonomy_rows if str(row.taxonomy_version) == taxonomy_version
        ]
        group_definitions = _build_group_definitions(version_rows)
        relevant_tickers = sorted({_normalize_ticker(row.ticker) for row in version_rows})
        price_rows = _load_price_rows(
            price_db_path=price_db_path,
            tickers=relevant_tickers,
            market=market,
            end_date=normalized_end_date,
        )
        ticker_inputs, all_dates = _build_ticker_daily_inputs(price_rows)
        in_range_dates = _build_in_range_dates(
            all_dates,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        for group_type, group_name, member_tickers in group_definitions:
            previous_valid_close: float | None = None
            valid_close_history: list[float] = []
            valid_return_history: list[float] = []
            group_rows: list[DatacenterGroupSyntheticOhlcRow] = []

            for current_date in in_range_dates:
                member_count = len(set(member_tickers))
                eligible_inputs = [
                    ticker_inputs[ticker][current_date]
                    for ticker in member_tickers
                    if ticker in ticker_inputs and current_date in ticker_inputs[ticker]
                ]
                eligible_count = len(eligible_inputs)
                status = _calculate_data_quality_status(
                    member_count=member_count,
                    eligible_count=eligible_count,
                    min_eligible_count=min_eligible_count,
                    min_coverage_ratio=min_coverage_ratio,
                )

                synthetic_open: float | None = None
                synthetic_high: float | None = None
                synthetic_low: float | None = None
                synthetic_close: float | None = None
                synthetic_volume: float | None = None

                if eligible_count > 0:
                    if previous_valid_close is None:
                        synthetic_open = 100.0
                        synthetic_high = 100.0
                        synthetic_low = 100.0
                        synthetic_close = 100.0
                    else:
                        group_open_return = sum(item.open_return for item in eligible_inputs) / float(eligible_count)
                        group_high_return = sum(item.high_return for item in eligible_inputs) / float(eligible_count)
                        group_low_return = sum(item.low_return for item in eligible_inputs) / float(eligible_count)
                        group_close_return = sum(item.close_return for item in eligible_inputs) / float(eligible_count)
                        synthetic_open = previous_valid_close * (1.0 + group_open_return)
                        synthetic_high = previous_valid_close * (1.0 + group_high_return)
                        synthetic_low = previous_valid_close * (1.0 + group_low_return)
                        synthetic_close = previous_valid_close * (1.0 + group_close_return)
                    synthetic_high = max(synthetic_high, synthetic_open, synthetic_close)
                    synthetic_low = min(synthetic_low, synthetic_open, synthetic_close)
                    volume_values = [item.volume for item in eligible_inputs if item.volume is not None]
                    synthetic_volume = sum(volume_values) if volume_values else None
                    previous_valid_close = synthetic_close
                    if valid_close_history:
                        valid_return_history.append((synthetic_close / valid_close_history[-1]) - 1.0)
                    valid_close_history.append(synthetic_close)

                ma20 = (
                    sum(valid_close_history[-20:]) / 20.0
                    if synthetic_close is not None and len(valid_close_history) >= 20
                    else None
                )
                ema20_series = _calculate_ema_series(valid_close_history, 20)
                ema20 = ema20_series[-1] if synthetic_close is not None and ema20_series else None
                volatility_20d = (
                    pstdev(valid_return_history[-20:])
                    if synthetic_close is not None and len(valid_return_history) >= 20
                    else None
                )

                group_rows.append(
                    DatacenterGroupSyntheticOhlcRow(
                        ohlc_date=current_date,
                        taxonomy_version=taxonomy_version,
                        group_type=group_type,
                        group_name=group_name,
                        member_count=member_count,
                        eligible_count=eligible_count,
                        synthetic_open=synthetic_open,
                        synthetic_high=synthetic_high,
                        synthetic_low=synthetic_low,
                        synthetic_close=synthetic_close,
                        synthetic_volume=synthetic_volume,
                        ma20=ma20,
                        ema20=ema20,
                        distance_to_ema20_pct=_distance_pct(synthetic_close, ema20),
                        volatility_20d=volatility_20d,
                        pivot_radius=None,
                        latest_pivot_high_date=None,
                        latest_pivot_high_value=None,
                        latest_pivot_low_date=None,
                        latest_pivot_low_value=None,
                        latest_structure_label=None,
                        trend_classification=None,
                        relative_base_window=None,
                        relative_open_20=None,
                        relative_high_20=None,
                        relative_low_20=None,
                        relative_close_20=None,
                        relative_upper_wick_20=None,
                        relative_lower_wick_20=None,
                        relative_close_extension_20=None,
                        relative_high_extension_20=None,
                        relative_low_extension_20=None,
                        relative_eligible_count=None,
                        data_quality_status=status,
                        calc_version=calc_version,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                    )
                )
            output_rows.extend(group_rows)

    summary = {
        "taxonomy_rows": len(taxonomy_rows),
        "taxonomy_versions": len(taxonomy_versions),
        "group_types": "layer,subindustry",
        "group_rows": len(output_rows),
        "ok_group_date_count": sum(1 for row in output_rows if row.data_quality_status == "OK"),
        "partial_data_group_date_count": sum(1 for row in output_rows if row.data_quality_status == "PARTIAL_DATA"),
        "too_small_group_date_count": sum(1 for row in output_rows if row.data_quality_status == "TOO_SMALL"),
        "no_data_group_date_count": sum(1 for row in output_rows if row.data_quality_status == "NO_DATA"),
    }
    return sorted(
        output_rows,
        key=lambda row: (
            row.taxonomy_version,
            GROUP_TYPE_ORDER[row.group_type],
            row.group_name,
            row.ohlc_date,
        ),
    ), summary


def _load_existing_group_synthetic_base_rows(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    calc_version: str,
    taxonomy_versions: Sequence[str],
    group_types: Sequence[str],
) -> dict[tuple[str, str, str, str, str], sqlite3.Row]:
    if not taxonomy_versions or not group_types:
        return {}
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    conn.row_factory = sqlite3.Row
    try:
        version_placeholders = ", ".join("?" for _ in taxonomy_versions)
        type_placeholders = ", ".join("?" for _ in group_types)
        rows = conn.execute(
            f"""
            SELECT *
            FROM dc_group_synthetic_ohlc_daily
            WHERE ohlc_date >= ?
              AND ohlc_date <= ?
              AND calc_version = ?
              AND taxonomy_version IN ({version_placeholders})
              AND group_type IN ({type_placeholders})
            """,
            [start_date, end_date, calc_version, *taxonomy_versions, *group_types],
        ).fetchall()
        return {
            (
                str(row["ohlc_date"]),
                str(row["taxonomy_version"]),
                str(row["group_type"]),
                str(row["group_name"]),
                str(row["calc_version"]),
            ): row
            for row in rows
        }
    finally:
        db_manager.close()


def build_group_relative_ohlc_updates(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    start_date: str,
    end_date: str,
    market: str | None,
    calc_version: str,
    run_id: str,
    created_at_utc: str,
    relative_base_window: int,
) -> tuple[list[dict[str, object]], dict[str, int | str]]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    if relative_base_window <= 0:
        raise ValueError(f"relative_base_window must be positive: {relative_base_window}")

    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    taxonomy_versions = sorted({str(row.taxonomy_version) for row in taxonomy_rows})
    group_types = ["layer", "subindustry"]
    existing_rows = _load_existing_group_synthetic_base_rows(
        analysis_db_path=analysis_db_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        calc_version=calc_version,
        taxonomy_versions=taxonomy_versions,
        group_types=group_types,
    )

    updates: list[dict[str, object]] = []
    missing_base_row_count = 0
    relative_rows_with_values = 0
    relative_rows_without_eligible_tickers = 0

    for taxonomy_version in taxonomy_versions:
        version_rows = [
            row for row in taxonomy_rows if str(row.taxonomy_version) == taxonomy_version
        ]
        group_definitions = _build_group_definitions(version_rows)
        relevant_tickers = sorted({_normalize_ticker(row.ticker) for row in version_rows})
        price_rows = _load_price_rows(
            price_db_path=price_db_path,
            tickers=relevant_tickers,
            market=market,
            end_date=normalized_end_date,
        )
        ticker_inputs, all_dates = _build_ticker_daily_relative_inputs(
            price_rows,
            relative_base_window=relative_base_window,
        )
        in_range_dates = _build_in_range_dates(
            all_dates,
            start_date=normalized_start_date,
            end_date=normalized_end_date,
        )

        for group_type, group_name, member_tickers in group_definitions:
            for current_date in in_range_dates:
                base_key = (
                    current_date,
                    taxonomy_version,
                    group_type,
                    group_name,
                    calc_version,
                )
                if base_key not in existing_rows:
                    missing_base_row_count += 1
                    continue

                eligible_inputs = [
                    ticker_inputs[ticker][current_date]
                    for ticker in member_tickers
                    if ticker in ticker_inputs and current_date in ticker_inputs[ticker]
                ]
                relative_eligible_count = len(eligible_inputs)
                if relative_eligible_count == 0:
                    relative_rows_without_eligible_tickers += 1
                    updates.append(
                        {
                            "ohlc_date": current_date,
                            "taxonomy_version": taxonomy_version,
                            "group_type": group_type,
                            "group_name": group_name,
                            "calc_version": calc_version,
                            "relative_base_window": relative_base_window,
                            "relative_open_20": None,
                            "relative_high_20": None,
                            "relative_low_20": None,
                            "relative_close_20": None,
                            "relative_upper_wick_20": None,
                            "relative_lower_wick_20": None,
                            "relative_close_extension_20": None,
                            "relative_high_extension_20": None,
                            "relative_low_extension_20": None,
                            "relative_eligible_count": 0,
                            "run_id": run_id,
                            "created_at_utc": created_at_utc,
                        }
                    )
                    continue

                group_relative_open = (
                    sum(item.relative_open for item in eligible_inputs)
                    / float(relative_eligible_count)
                )
                group_relative_high = (
                    sum(item.relative_high for item in eligible_inputs)
                    / float(relative_eligible_count)
                )
                group_relative_low = (
                    sum(item.relative_low for item in eligible_inputs)
                    / float(relative_eligible_count)
                )
                group_relative_close = (
                    sum(item.relative_close for item in eligible_inputs)
                    / float(relative_eligible_count)
                )
                group_relative_high = max(
                    group_relative_high,
                    group_relative_open,
                    group_relative_close,
                )
                group_relative_low = min(
                    group_relative_low,
                    group_relative_open,
                    group_relative_close,
                )
                relative_rows_with_values += 1
                updates.append(
                    {
                        "ohlc_date": current_date,
                        "taxonomy_version": taxonomy_version,
                        "group_type": group_type,
                        "group_name": group_name,
                        "calc_version": calc_version,
                        "relative_base_window": relative_base_window,
                        "relative_open_20": group_relative_open,
                        "relative_high_20": group_relative_high,
                        "relative_low_20": group_relative_low,
                        "relative_close_20": group_relative_close,
                        "relative_upper_wick_20": group_relative_high
                        - max(group_relative_open, group_relative_close),
                        "relative_lower_wick_20": min(group_relative_open, group_relative_close)
                        - group_relative_low,
                        "relative_close_extension_20": group_relative_close - 1.0,
                        "relative_high_extension_20": group_relative_high - 1.0,
                        "relative_low_extension_20": group_relative_low - 1.0,
                        "relative_eligible_count": relative_eligible_count,
                        "run_id": run_id,
                        "created_at_utc": created_at_utc,
                    }
                )

    summary = {
        "taxonomy_rows": len(taxonomy_rows),
        "taxonomy_versions": len(taxonomy_versions),
        "group_types": "layer,subindustry",
        "missing_base_row_count": missing_base_row_count,
        "relative_rows_with_values": relative_rows_with_values,
        "relative_rows_without_eligible_tickers": relative_rows_without_eligible_tickers,
    }
    return sorted(
        updates,
        key=lambda row: (
            str(row["taxonomy_version"]),
            GROUP_TYPE_ORDER[str(row["group_type"])],
            str(row["group_name"]),
            str(row["ohlc_date"]),
        ),
    ), summary


def _serialize_row(row: DatacenterGroupSyntheticOhlcRow) -> tuple[object, ...]:
    return (
        row.ohlc_date,
        row.taxonomy_version,
        row.group_type,
        row.group_name,
        row.member_count,
        row.eligible_count,
        row.synthetic_open,
        row.synthetic_high,
        row.synthetic_low,
        row.synthetic_close,
        row.synthetic_volume,
        row.ma20,
        row.ema20,
        row.distance_to_ema20_pct,
        row.volatility_20d,
        row.pivot_radius,
        row.latest_pivot_high_date,
        row.latest_pivot_high_value,
        row.latest_pivot_low_date,
        row.latest_pivot_low_value,
        row.latest_structure_label,
        row.trend_classification,
        row.relative_base_window,
        row.relative_open_20,
        row.relative_high_20,
        row.relative_low_20,
        row.relative_close_20,
        row.relative_upper_wick_20,
        row.relative_lower_wick_20,
        row.relative_close_extension_20,
        row.relative_high_extension_20,
        row.relative_low_extension_20,
        row.relative_eligible_count,
        row.data_quality_status,
        row.calc_version,
        row.run_id,
        row.created_at_utc,
    )


def _row_key(row: DatacenterGroupSyntheticOhlcRow) -> tuple[str, str, str, str, str]:
    return (
        row.ohlc_date,
        row.taxonomy_version,
        row.group_type,
        row.group_name,
        row.calc_version,
    )


def write_group_synthetic_ohlc_rows(
    *,
    analysis_db_path: str | Path,
    rows: Sequence[DatacenterGroupSyntheticOhlcRow],
    start_date: str,
    end_date: str,
    calc_version: str,
    write_mode: str,
) -> dict[str, int]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"insert-missing", "upsert", "replace-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    taxonomy_versions = sorted({row.taxonomy_version for row in rows})
    group_types = sorted({row.group_type for row in rows})
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    inserted_count = 0
    updated_count = 0
    skipped_existing_count = 0
    deleted_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-range":
            if taxonomy_versions and group_types:
                version_placeholders = ", ".join("?" for _ in taxonomy_versions)
                type_placeholders = ", ".join("?" for _ in group_types)
                cursor.execute(
                    f"""
                    DELETE FROM dc_group_synthetic_ohlc_daily
                    WHERE ohlc_date >= ?
                      AND ohlc_date <= ?
                      AND calc_version = ?
                      AND taxonomy_version IN ({version_placeholders})
                      AND group_type IN ({type_placeholders})
                    """,
                    [
                        normalized_start_date,
                        normalized_end_date,
                        calc_version,
                        *taxonomy_versions,
                        *group_types,
                    ],
                )
                deleted_count = cursor.rowcount
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO dc_group_synthetic_ohlc_daily (
                        ohlc_date, taxonomy_version, group_type, group_name, member_count, eligible_count,
                        synthetic_open, synthetic_high, synthetic_low, synthetic_close, synthetic_volume,
                        ma20, ema20, distance_to_ema20_pct, volatility_20d,
                        pivot_radius, latest_pivot_high_date, latest_pivot_high_value,
                        latest_pivot_low_date, latest_pivot_low_value, latest_structure_label,
                        trend_classification, relative_base_window, relative_open_20, relative_high_20,
                        relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                        relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                        relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    str(existing_row[4]),
                )
                for existing_row in cursor.execute(
                    """
                    SELECT ohlc_date, taxonomy_version, group_type, group_name, calc_version
                    FROM dc_group_synthetic_ohlc_daily
                    WHERE ohlc_date >= ?
                      AND ohlc_date <= ?
                      AND calc_version = ?
                    """,
                    (normalized_start_date, normalized_end_date, calc_version),
                ).fetchall()
            }
            for row in rows:
                key = _row_key(row)
                if write_mode == "insert-missing":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO dc_group_synthetic_ohlc_daily (
                            ohlc_date, taxonomy_version, group_type, group_name, member_count, eligible_count,
                            synthetic_open, synthetic_high, synthetic_low, synthetic_close, synthetic_volume,
                            ma20, ema20, distance_to_ema20_pct, volatility_20d,
                            pivot_radius, latest_pivot_high_date, latest_pivot_high_value,
                            latest_pivot_low_date, latest_pivot_low_value, latest_structure_label,
                            trend_classification, relative_base_window, relative_open_20, relative_high_20,
                            relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                            relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                            relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        INSERT INTO dc_group_synthetic_ohlc_daily (
                            ohlc_date, taxonomy_version, group_type, group_name, member_count, eligible_count,
                            synthetic_open, synthetic_high, synthetic_low, synthetic_close, synthetic_volume,
                            ma20, ema20, distance_to_ema20_pct, volatility_20d,
                            pivot_radius, latest_pivot_high_date, latest_pivot_high_value,
                            latest_pivot_low_date, latest_pivot_low_value, latest_structure_label,
                            trend_classification, relative_base_window, relative_open_20, relative_high_20,
                            relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                            relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                            relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ohlc_date, taxonomy_version, group_type, group_name, calc_version)
                        DO UPDATE SET
                            member_count = excluded.member_count,
                            eligible_count = excluded.eligible_count,
                            synthetic_open = excluded.synthetic_open,
                            synthetic_high = excluded.synthetic_high,
                            synthetic_low = excluded.synthetic_low,
                            synthetic_close = excluded.synthetic_close,
                            synthetic_volume = excluded.synthetic_volume,
                            ma20 = excluded.ma20,
                            ema20 = excluded.ema20,
                            distance_to_ema20_pct = excluded.distance_to_ema20_pct,
                            volatility_20d = excluded.volatility_20d,
                            pivot_radius = excluded.pivot_radius,
                            latest_pivot_high_date = excluded.latest_pivot_high_date,
                            latest_pivot_high_value = excluded.latest_pivot_high_value,
                            latest_pivot_low_date = excluded.latest_pivot_low_date,
                            latest_pivot_low_value = excluded.latest_pivot_low_value,
                            latest_structure_label = excluded.latest_structure_label,
                            trend_classification = excluded.trend_classification,
                            relative_base_window = excluded.relative_base_window,
                            relative_open_20 = excluded.relative_open_20,
                            relative_high_20 = excluded.relative_high_20,
                            relative_low_20 = excluded.relative_low_20,
                            relative_close_20 = excluded.relative_close_20,
                            relative_upper_wick_20 = excluded.relative_upper_wick_20,
                            relative_lower_wick_20 = excluded.relative_lower_wick_20,
                            relative_close_extension_20 = excluded.relative_close_extension_20,
                            relative_high_extension_20 = excluded.relative_high_extension_20,
                            relative_low_extension_20 = excluded.relative_low_extension_20,
                            relative_eligible_count = excluded.relative_eligible_count,
                            data_quality_status = excluded.data_quality_status,
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


def write_group_relative_ohlc_updates(
    *,
    analysis_db_path: str | Path,
    updates: Sequence[dict[str, object]],
    start_date: str,
    end_date: str,
    calc_version: str,
    write_mode: str,
) -> dict[str, int]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"update-existing", "replace-relative-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    taxonomy_versions = sorted({str(row["taxonomy_version"]) for row in updates})
    group_types = sorted({str(row["group_type"]) for row in updates})
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    updated_count = 0
    cleared_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-relative-range" and taxonomy_versions and group_types:
            version_placeholders = ", ".join("?" for _ in taxonomy_versions)
            type_placeholders = ", ".join("?" for _ in group_types)
            cursor.execute(
                f"""
                UPDATE dc_group_synthetic_ohlc_daily
                SET relative_base_window = NULL,
                    relative_open_20 = NULL,
                    relative_high_20 = NULL,
                    relative_low_20 = NULL,
                    relative_close_20 = NULL,
                    relative_upper_wick_20 = NULL,
                    relative_lower_wick_20 = NULL,
                    relative_close_extension_20 = NULL,
                    relative_high_extension_20 = NULL,
                    relative_low_extension_20 = NULL,
                    relative_eligible_count = NULL
                WHERE ohlc_date >= ?
                  AND ohlc_date <= ?
                  AND calc_version = ?
                  AND taxonomy_version IN ({version_placeholders})
                  AND group_type IN ({type_placeholders})
                """,
                [normalized_start_date, normalized_end_date, calc_version, *taxonomy_versions, *group_types],
            )
            cleared_count = cursor.rowcount

        for row in updates:
            cursor.execute(
                """
                UPDATE dc_group_synthetic_ohlc_daily
                SET relative_base_window = ?,
                    relative_open_20 = ?,
                    relative_high_20 = ?,
                    relative_low_20 = ?,
                    relative_close_20 = ?,
                    relative_upper_wick_20 = ?,
                    relative_lower_wick_20 = ?,
                    relative_close_extension_20 = ?,
                    relative_high_extension_20 = ?,
                    relative_low_extension_20 = ?,
                    relative_eligible_count = ?,
                    run_id = ?,
                    created_at_utc = ?
                WHERE ohlc_date = ?
                  AND taxonomy_version = ?
                  AND group_type = ?
                  AND group_name = ?
                  AND calc_version = ?
                """,
                (
                    row["relative_base_window"],
                    row["relative_open_20"],
                    row["relative_high_20"],
                    row["relative_low_20"],
                    row["relative_close_20"],
                    row["relative_upper_wick_20"],
                    row["relative_lower_wick_20"],
                    row["relative_close_extension_20"],
                    row["relative_high_extension_20"],
                    row["relative_low_extension_20"],
                    row["relative_eligible_count"],
                    row["run_id"],
                    row["created_at_utc"],
                    row["ohlc_date"],
                    row["taxonomy_version"],
                    row["group_type"],
                    row["group_name"],
                    row["calc_version"],
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


def persist_datacenter_group_synthetic_ohlc(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    start_date: str,
    end_date: str,
    market: str | None,
    calc_version: str = DEFAULT_CALC_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    write_mode: str = "upsert",
    min_eligible_count: int = DEFAULT_MIN_ELIGIBLE_COUNT,
    min_coverage_ratio: float = DEFAULT_MIN_COVERAGE_RATIO,
) -> dict[str, int | str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"insert-missing", "upsert", "replace-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    resolved_run_id = build_group_synthetic_ohlc_run_id(
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        calc_version=calc_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    rows, prep_summary = build_group_synthetic_ohlc_rows(
        analysis_db_path=analysis_db_path,
        price_db_path=price_db_path,
        taxonomy_csv_path=taxonomy_csv_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        market=market,
        calc_version=calc_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        min_eligible_count=min_eligible_count,
        min_coverage_ratio=min_coverage_ratio,
    )
    write_summary = write_group_synthetic_ohlc_rows(
        analysis_db_path=analysis_db_path,
        rows=rows,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        calc_version=calc_version,
        write_mode=write_mode,
    )
    return {
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "market": market if market is not None else "ALL",
        "write_mode": write_mode,
        "calc_version": calc_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }


def persist_datacenter_group_relative_ohlc(
    *,
    analysis_db_path: str | Path,
    price_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    start_date: str,
    end_date: str,
    market: str | None,
    calc_version: str = DEFAULT_CALC_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    relative_base_window: int = DEFAULT_RELATIVE_BASE_WINDOW,
    write_mode: str = "update-existing",
) -> dict[str, int | str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"update-existing", "replace-relative-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    resolved_run_id = build_group_synthetic_ohlc_run_id(
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        calc_version=calc_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    updates, prep_summary = build_group_relative_ohlc_updates(
        analysis_db_path=analysis_db_path,
        price_db_path=price_db_path,
        taxonomy_csv_path=taxonomy_csv_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        market=market,
        calc_version=calc_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        relative_base_window=relative_base_window,
    )
    write_summary = write_group_relative_ohlc_updates(
        analysis_db_path=analysis_db_path,
        updates=updates,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        calc_version=calc_version,
        write_mode=write_mode,
    )
    return {
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "market": market if market is not None else "ALL",
        "write_mode": write_mode,
        "calc_version": calc_version,
        "relative_base_window": relative_base_window,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }
