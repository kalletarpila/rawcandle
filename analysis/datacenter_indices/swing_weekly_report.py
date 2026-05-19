from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Sequence

from .swing_daily_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_WATCHLIST_FILE,
    EXIT_RISK_SEVERITY_PRIORITY,
    FRESHNESS_PRIORITY,
    GROUP_BOS_PRIORITY,
    GROUP_RESET_PRIORITY,
    OVERHEAT_PRIORITY,
    TREND_PRIORITY,
    WATCHLIST_MISSING_PRICE_STATUSES,
    _daily_context_risk_value,
    _build_group_synthetic_context_by_key,
    _has_layer_context_risk,
    _has_subindustry_context_risk,
    _is_group_risk_state,
    _check_required_tables,
    _float_value,
    _build_csv_rows_from_markdown,
    _format_table,
    _normalize_path,
    _parse_iso_date,
    _resolve_watchlist_context,
    _row_to_dict,
    _utc_now_iso,
)


DEFAULT_WEEKLY_WINDOW_SIZE = 5

WEEKLY_REPORT_SUMMARY_ORDER = [
    "end_date",
    "signal_version",
    "ohlc_calc_version",
    "taxonomy_version",
    "taxonomy_version_inferred",
    "window_size",
    "valid_signal_dates_count",
    "window_start_date",
    "window_end_date",
    "incomplete_window",
    "group_rows",
    "ticker_rows",
    "synthetic_ohlc_rows",
    "repeated_breakout_tickers",
    "repeated_pullback_tickers",
    "repeated_exit_risk_tickers",
    "output_markdown",
    "output_csv",
    "validation_status",
]

TIMING_STATE_ORDER = [
    "BUY_ZONE",
    "ADD_ON_PULLBACK",
    "TRIM_WATCH",
    "EXIT_ZONE",
    "NEUTRAL",
    None,
]

OVERHEAT_RANK = {
    None: 0,
    "LOW": 1,
    "ELEVATED": 2,
    "HIGH": 3,
    "EXTREME": 4,
}

GROUP_TYPE_PRIORITY = {
    "ecosystem": 0,
    "layer": 1,
    "subindustry": 2,
}

OVERHEAT_STATUS_PRIORITY = {
    "EXTREME": 0,
    "HIGH": 1,
    "ELEVATED": 2,
    "LOW": 3,
    "NULL": 4,
}


def _count_by_date_and_field(
    rows: Sequence[dict[str, object]],
    *,
    date_field: str,
    value_field: str,
    group_type: str | None = None,
) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        if group_type is not None and row.get("group_type") != group_type:
            continue
        date_value = str(row.get(date_field) or "")
        field_value = "NULL" if row.get(value_field) is None else str(row.get(value_field))
        group_value = "" if group_type is None else group_type
        key = (date_value, group_value, field_value)
        counts[key] = counts.get(key, 0) + 1
    ordered_keys = sorted(counts)
    return [
        {
            "signal_date": date_value,
            "group_type": group_value,
            "status": field_value,
            "count": counts[(date_value, group_value, field_value)],
        }
        for date_value, group_value, field_value in ordered_keys
    ]


def _count_by_date_group_type_and_field(
    rows: Sequence[dict[str, object]],
    *,
    date_field: str,
    value_field: str,
) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        date_value = str(row.get(date_field) or "")
        group_type_value = row.get("group_type")
        normalized_group_type = "NULL" if group_type_value is None else str(group_type_value)
        field_value = "NULL" if row.get(value_field) is None else str(row.get(value_field))
        key = (date_value, normalized_group_type, field_value)
        counts[key] = counts.get(key, 0) + 1
    ordered_keys = sorted(
        counts,
        key=lambda key: (
            key[0],
            GROUP_TYPE_PRIORITY.get(key[1], 3),
            "" if key[1] == "NULL" else key[1],
            OVERHEAT_STATUS_PRIORITY.get(key[2], 5),
            "" if key[2] == "NULL" else key[2],
        ),
    )
    return [
        {
            "signal_date": date_value,
            "group_type": group_type_value,
            "status": field_value,
            "count": counts[(date_value, group_type_value, field_value)],
        }
        for date_value, group_type_value, field_value in ordered_keys
    ]


def _group_rows_by_key(
    rows: Sequence[dict[str, object]],
    *,
    key_fields: Sequence[str],
    date_field: str,
) -> dict[tuple[object, ...], list[dict[str, object]]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        grouped.setdefault(key, []).append(row)
    for group_rows in grouped.values():
        group_rows.sort(key=lambda row: str(row.get(date_field) or ""))
    return grouped


def _numeric_change(first_row: dict[str, object], last_row: dict[str, object], field_name: str) -> float | None:
    first_value = _float_value(first_row.get(field_name))
    last_value = _float_value(last_row.get(field_name))
    if first_value is None or last_value is None:
        return None
    return last_value - first_value


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    end_date: str,
    signal_version: str,
    taxonomy_version: str | None,
    limit: int = DEFAULT_WEEKLY_WINDOW_SIZE,
) -> list[str]:
    if taxonomy_version is None:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT signal_date
        FROM dc_group_swing_signal_daily
        WHERE signal_date <= ?
          AND signal_version = ?
          AND taxonomy_version = ?
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (end_date, signal_version, taxonomy_version, limit),
    ).fetchall()
    return sorted(str(row["signal_date"]) for row in rows)


def _resolve_weekly_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    end_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> tuple[str | None, int]:
    if taxonomy_version is not None:
        return taxonomy_version, 0
    rows = conn.execute(
        """
        SELECT DISTINCT taxonomy_version
        FROM dc_group_swing_signal_daily
        WHERE signal_date <= ?
          AND signal_version = ?
        ORDER BY taxonomy_version ASC
        """,
        (end_date, signal_version),
    ).fetchall()
    versions = [str(row["taxonomy_version"]) for row in rows if row["taxonomy_version"] is not None]
    if len(versions) == 1:
        return versions[0], 1
    if len(versions) > 1:
        raise ValueError(
            "Multiple taxonomy_version values exist for the selected weekly window and signal_version; "
            "pass --taxonomy-version explicitly"
        )
    return None, 0


def _load_rows_for_dates(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_field: str,
    selected_dates: Sequence[str],
    version_field: str,
    version_value: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if not selected_dates or taxonomy_version is None:
        return []
    placeholders = ", ".join("?" for _ in selected_dates)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {table_name}
        WHERE {date_field} IN ({placeholders})
          AND {version_field} = ?
          AND taxonomy_version = ?
        ORDER BY {date_field} ASC
        """,
        tuple(selected_dates) + (version_value, taxonomy_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def load_weekly_swing_report_data(
    *,
    analysis_db_path: str | Path,
    end_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    taxonomy_version: str | None = None,
    window_size: int = DEFAULT_WEEKLY_WINDOW_SIZE,
    watchlist_file: str | Path | None = None,
) -> dict[str, object]:
    if window_size <= 0:
        raise ValueError("window_size must be greater than 0")
    normalized_end_date = _parse_iso_date(end_date)
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        _check_required_tables(
            conn,
            [
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            ],
        )
        resolved_taxonomy_version, taxonomy_version_inferred = _resolve_weekly_taxonomy_version(
            conn,
            end_date=normalized_end_date,
            signal_version=signal_version,
            taxonomy_version=taxonomy_version,
        )
        valid_signal_dates = _load_valid_signal_dates(
            conn,
            end_date=normalized_end_date,
            signal_version=signal_version,
            taxonomy_version=resolved_taxonomy_version,
            limit=window_size,
        )
        group_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        ticker_rows = _load_rows_for_dates(
            conn,
            table_name="dc_ticker_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        synthetic_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_synthetic_ohlc_daily",
            date_field="ohlc_date",
            selected_dates=valid_signal_dates,
            version_field="calc_version",
            version_value=ohlc_calc_version,
            taxonomy_version=resolved_taxonomy_version,
        )
    result = {
        "requested_end_date": normalized_end_date,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        "taxonomy_version": resolved_taxonomy_version,
        "taxonomy_version_inferred": taxonomy_version_inferred,
        "window_size": window_size,
        "valid_signal_dates": valid_signal_dates,
        "group_rows": group_rows,
        "ticker_rows": ticker_rows,
        "synthetic_rows": synthetic_rows,
    }
    result.update(_resolve_watchlist_context(watchlist_file))
    return result


def _build_repeated_ticker_rows(
    rows: Sequence[dict[str, object]],
    *,
    signal_field: str,
    extra_count_fields: Sequence[str] = (),
) -> list[dict[str, object]]:
    grouped = _group_rows_by_key(rows, key_fields=("taxonomy_version", "ticker"), date_field="signal_date")
    output_rows: list[dict[str, object]] = []
    for (_, ticker), ticker_rows in grouped.items():
        positive_rows = [row for row in ticker_rows if row.get(signal_field) == 1]
        if not positive_rows:
            continue
        last_row = ticker_rows[-1]
        row = {
            "ticker": ticker,
            f"{signal_field.removesuffix('_signal')}_days": len(positive_rows),
            "first_signal_date": str(positive_rows[0].get("signal_date") or ""),
            "last_signal_date": str(positive_rows[-1].get("signal_date") or ""),
            "last_primary_layer": last_row.get("primary_layer"),
            "last_primary_subindustry": last_row.get("primary_subindustry"),
            "last_close": last_row.get("close"),
            "last_return_5d": last_row.get("return_5d"),
            "last_return_10d": last_row.get("return_10d"),
            "last_return_20d": last_row.get("return_20d"),
            "last_return_60d": last_row.get("return_60d"),
            "last_volume_vs_avg20": last_row.get("volume_vs_avg20"),
            "last_latest_structure_label": last_row.get("latest_structure_label"),
            "last_latest_structure_age_trading_days": last_row.get("latest_structure_age_trading_days"),
            "last_latest_structure_freshness": last_row.get("latest_structure_freshness"),
            "last_ticker_trend_state": last_row.get("ticker_trend_state"),
            "last_latest_bos_event_type": last_row.get("latest_bos_event_type"),
            "last_latest_bos_freshness": last_row.get("latest_bos_freshness"),
            "last_latest_reset_reason": last_row.get("latest_reset_reason"),
            "last_latest_reset_freshness": last_row.get("latest_reset_freshness"),
            "last_exit_reason": last_row.get("exit_reason"),
            "last_exit_risk_severity": last_row.get("exit_risk_severity"),
            "last_bullish_candle_signal": last_row.get("bullish_candle_signal"),
            "last_bearish_candle_signal": last_row.get("bearish_candle_signal"),
            "last_bullish_divergence_signal": last_row.get("bullish_divergence_signal"),
            "last_bearish_divergence_signal": last_row.get("bearish_divergence_signal"),
            "last_hidden_bullish_divergence_signal": last_row.get("hidden_bullish_divergence_signal"),
            "last_hidden_bearish_divergence_signal": last_row.get("hidden_bearish_divergence_signal"),
            "last_price_data_status": last_row.get("price_data_status"),
            "last_distance_to_ema20_pct": last_row.get("distance_to_ema20_pct"),
        }
        for field_name in extra_count_fields:
            row[f"{field_name.removesuffix('_signal')}_days"] = sum(
                1 for current_row in ticker_rows if current_row.get(field_name) == 1
            )
        output_rows.append(row)
    return output_rows


def _classify_rolling_current_watchlist_status(row: dict[str, object]) -> str:
    if row.get("in_datacenter_ecosystem") == "NO":
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES:
        return "MISSING_PRICE"
    if row.get("last_exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("last_exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if row.get("last_breakout_signal") == 1:
        return "BREAKOUT_CANDIDATE"
    if row.get("last_pullback_signal") == 1:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _classify_rolling_window_watchlist_status(row: dict[str, object]) -> str:
    if row.get("in_datacenter_ecosystem") == "NO":
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get("all_price_rows_missing") is True:
        return "MISSING_PRICE"
    if (row.get("high_exit_risk_days") or 0) > 0:
        return "HIGH_EXIT_RISK"
    if (row.get("medium_exit_risk_days") or 0) > 0:
        return "MEDIUM_EXIT_RISK"
    if (row.get("breakout_days") or 0) > 0:
        return "BREAKOUT_CANDIDATE"
    if (row.get("pullback_days") or 0) > 0:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _build_rolling_watchlist_rows(
    *,
    watchlist_tickers: Sequence[str],
    ticker_rows: Sequence[dict[str, object]],
    group_rows: Sequence[dict[str, object]],
    synthetic_rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    ticker_rows_by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in ticker_rows:
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        ticker_rows_by_ticker.setdefault(ticker, []).append(row)
    for rows in ticker_rows_by_ticker.values():
        rows.sort(key=lambda row: str(row.get("signal_date") or ""))
    group_context_by_key = {
        (row.get("signal_date"), row.get("group_type"), row.get("group_name")): row
        for row in group_rows
    }
    synthetic_context_by_key = _build_group_synthetic_context_by_key(
        synthetic_rows,
        include_date=True,
    )
    output_rows: list[dict[str, object]] = []
    for ticker in watchlist_tickers:
        current_rows = ticker_rows_by_ticker.get(ticker)
        if not current_rows:
            output_rows.append(
                {
                    "ticker": ticker,
                    "current_watchlist_status": "NOT_PART_OF_DATACENTER_ECOSYSTEM",
                    "window_watchlist_status": "NOT_PART_OF_DATACENTER_ECOSYSTEM",
                    "subindustry_context_risk": "",
                    "layer_context_risk": "",
                    "in_datacenter_ecosystem": "NO",
                }
            )
            continue
        last_row = current_rows[-1]
        subindustry_context = group_context_by_key.get(
            (last_row.get("signal_date"), "subindustry", last_row.get("primary_subindustry")),
            {},
        )
        layer_context = group_context_by_key.get(
            (last_row.get("signal_date"), "layer", last_row.get("primary_layer")),
            {},
        )
        subindustry_structure_context = synthetic_context_by_key.get(
            (last_row.get("signal_date"), "subindustry", last_row.get("primary_subindustry")),
            {},
        )
        layer_structure_context = synthetic_context_by_key.get(
            (last_row.get("signal_date"), "layer", last_row.get("primary_layer")),
            {},
        )
        output_row = {
            "ticker": ticker,
            "in_datacenter_ecosystem": "YES",
            "last_subindustry_trend_classification": subindustry_structure_context.get("trend_classification"),
            "last_subindustry_latest_structure_label": subindustry_structure_context.get("latest_structure_label"),
            "last_layer_trend_classification": layer_structure_context.get("trend_classification"),
            "last_layer_latest_structure_label": layer_structure_context.get("latest_structure_label"),
            "primary_layer": last_row.get("primary_layer"),
            "primary_subindustry": last_row.get("primary_subindustry"),
            "first_signal_date": current_rows[0].get("signal_date"),
            "last_signal_date": last_row.get("signal_date"),
            "last_close": last_row.get("close"),
            "last_breakout_signal": last_row.get("breakout_signal"),
            "last_pullback_signal": last_row.get("pullback_signal"),
            "breakout_days": sum(1 for row in current_rows if row.get("breakout_signal") == 1),
            "pullback_days": sum(1 for row in current_rows if row.get("pullback_signal") == 1),
            "exit_risk_days": sum(1 for row in current_rows if row.get("exit_risk_signal") == 1),
            "high_exit_risk_days": sum(1 for row in current_rows if row.get("exit_risk_severity") == "HIGH"),
            "medium_exit_risk_days": sum(1 for row in current_rows if row.get("exit_risk_severity") == "MEDIUM"),
            "last_exit_risk_severity": last_row.get("exit_risk_severity"),
            "last_exit_reason": last_row.get("exit_reason"),
            "last_ticker_trend_state": last_row.get("ticker_trend_state"),
            "last_latest_structure_label": last_row.get("latest_structure_label"),
            "last_latest_structure_freshness": last_row.get("latest_structure_freshness"),
            "last_latest_bos_event_type": last_row.get("latest_bos_event_type"),
            "last_latest_bos_freshness": last_row.get("latest_bos_freshness"),
            "last_latest_reset_reason": last_row.get("latest_reset_reason"),
            "last_latest_reset_freshness": last_row.get("latest_reset_freshness"),
            "last_subindustry_timing_state": subindustry_context.get("timing_state"),
            "last_subindustry_overheat_risk_level": subindustry_context.get("overheat_risk_level"),
            "last_layer_timing_state": layer_context.get("timing_state"),
            "last_layer_overheat_risk_level": layer_context.get("overheat_risk_level"),
            "last_price_data_status": last_row.get("price_data_status"),
            "all_price_rows_missing": all(row.get("price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES for row in current_rows),
        }
        output_row["subindustry_context_risk"] = _daily_context_risk_value(
            in_datacenter_ecosystem=output_row["in_datacenter_ecosystem"],
            has_risk=_has_subindustry_context_risk(
                subindustry_timing_state=output_row.get("last_subindustry_timing_state"),
                subindustry_overheat_risk_level=output_row.get("last_subindustry_overheat_risk_level"),
            ),
        )
        output_row["layer_context_risk"] = _daily_context_risk_value(
            in_datacenter_ecosystem=output_row["in_datacenter_ecosystem"],
            has_risk=_has_layer_context_risk(
                layer_timing_state=output_row.get("last_layer_timing_state"),
                layer_overheat_risk_level=output_row.get("last_layer_overheat_risk_level"),
            ),
        )
        output_row["current_watchlist_status"] = _classify_rolling_current_watchlist_status(output_row)
        output_row["window_watchlist_status"] = _classify_rolling_window_watchlist_status(output_row)
        output_rows.append(output_row)
    return output_rows


def build_markdown_weekly_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    if top_n <= 0:
        raise ValueError(f"Invalid top_n: {top_n}")

    requested_end_date = str(report_data["requested_end_date"])
    signal_version = str(report_data["signal_version"])
    ohlc_calc_version = str(report_data["ohlc_calc_version"])
    taxonomy_version = "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"])
    window_size = int(report_data.get("window_size") or DEFAULT_WEEKLY_WINDOW_SIZE)
    valid_signal_dates = list(report_data["valid_signal_dates"])  # type: ignore[arg-type]
    group_rows = list(report_data["group_rows"])  # type: ignore[arg-type]
    ticker_rows = list(report_data["ticker_rows"])  # type: ignore[arg-type]
    synthetic_rows = list(report_data["synthetic_rows"])  # type: ignore[arg-type]
    watchlist_tickers = list(report_data.get("watchlist_tickers") or [])
    watchlist_file_path = str(report_data.get("watchlist_file_path") or DEFAULT_WATCHLIST_FILE)
    watchlist_file_missing = bool(report_data.get("watchlist_file_missing"))
    generated = generated_at_utc or _utc_now_iso()
    window_start_date = valid_signal_dates[0] if valid_signal_dates else ""
    window_end_date = valid_signal_dates[-1] if valid_signal_dates else ""
    incomplete_window = "YES" if len(valid_signal_dates) < window_size else "NO"
    end_group_rows = [row for row in group_rows if row.get("signal_date") == window_end_date]

    ecosystem_rows = [
        row
        for row in group_rows
        if row.get("group_type") == "ecosystem" and row.get("group_name") == "DC_ECOSYSTEM_TOTAL"
    ]
    ecosystem_first = ecosystem_rows[0] if ecosystem_rows else None
    ecosystem_last = ecosystem_rows[-1] if ecosystem_rows else None

    lines = [
        "# Datacenter Rolling Swing Report",
        "",
        "## 1. Title and run metadata",
        f"end_date: {requested_end_date}",
        f"signal_version: {signal_version}",
        f"ohlc_calc_version: {ohlc_calc_version}",
        f"taxonomy_version: {taxonomy_version}",
        f"window_size: {window_size}",
        f"generated_at_utc: {generated}",
        "source_tables: dc_group_swing_signal_daily, dc_ticker_swing_signal_daily, dc_group_synthetic_ohlc_daily",
        f"Window type: last {window_size} valid trading days, not calendar week",
        "",
        "## 2. Window summary",
    ]
    if len(valid_signal_dates) < window_size:
        lines.append(f"INCOMPLETE WINDOW – FEWER THAN {window_size} VALID SIGNAL DATES")
    lines.append(
        _format_table(
            ["metric", "value"],
            [
                {"metric": "requested_end_date", "value": requested_end_date},
                {"metric": "window_start_date", "value": window_start_date},
                {"metric": "window_end_date", "value": window_end_date},
                {"metric": "valid_signal_dates_count", "value": len(valid_signal_dates)},
                {"metric": "valid_signal_dates_included", "value": ", ".join(valid_signal_dates)},
                {"metric": "incomplete_window", "value": incomplete_window},
            ],
        ).rstrip()
    )

    watchlist_rows = _build_rolling_watchlist_rows(
        watchlist_tickers=watchlist_tickers,
        ticker_rows=ticker_rows,
        group_rows=group_rows,
        synthetic_rows=synthetic_rows,
    )
    watchlist_summary_rows = [
        {"metric": "watchlist_tickers_total", "value": len(watchlist_rows)},
        {"metric": "watchlist_in_datacenter_taxonomy", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES")},
        {"metric": "watchlist_not_in_datacenter_taxonomy", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "NO")},
        {"metric": "watchlist_missing_price_end_date", "value": sum(1 for row in watchlist_rows if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES)},
        {"metric": "watchlist_subindustry_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("subindustry_context_risk") == "YES")},
        {"metric": "watchlist_layer_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("layer_context_risk") == "YES")},
        {"metric": "watchlist_both_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("subindustry_context_risk") == "YES" and row.get("layer_context_risk") == "YES")},
        {"metric": "watchlist_with_breakout_days", "value": sum(1 for row in watchlist_rows if (row.get("breakout_days") or 0) > 0)},
        {"metric": "watchlist_with_pullback_days", "value": sum(1 for row in watchlist_rows if (row.get("pullback_days") or 0) > 0)},
        {"metric": "watchlist_with_exit_risk_days", "value": sum(1 for row in watchlist_rows if (row.get("exit_risk_days") or 0) > 0)},
        {"metric": "watchlist_with_high_exit_risk_days", "value": sum(1 for row in watchlist_rows if (row.get("high_exit_risk_days") or 0) > 0)},
    ]
    lines.extend(
        [
            "",
            "## Watchlist Summary",
            _format_table(["metric", "value"], watchlist_summary_rows).rstrip(),
        ]
    )
    if watchlist_file_missing:
        lines.append(f"No watchlist file found: {watchlist_file_path}")
    elif not watchlist_rows:
        lines.append("No watchlist tickers.")
    else:
        lines.extend(
            [
                "",
                _format_table(
                    [
                        "ticker",
                        "current_watchlist_status",
                        "window_watchlist_status",
                        "subindustry_context_risk",
                        "layer_context_risk",
                        "last_subindustry_trend_classification",
                        "last_subindustry_latest_structure_label",
                        "last_layer_trend_classification",
                        "last_layer_latest_structure_label",
                        "in_datacenter_ecosystem",
                        "primary_layer",
                        "primary_subindustry",
                        "first_signal_date",
                        "last_signal_date",
                        "last_close",
                        "breakout_days",
                        "pullback_days",
                        "exit_risk_days",
                        "high_exit_risk_days",
                        "medium_exit_risk_days",
                        "last_exit_risk_severity",
                        "last_exit_reason",
                        "last_ticker_trend_state",
                        "last_latest_structure_label",
                        "last_latest_structure_freshness",
                        "last_latest_bos_event_type",
                        "last_latest_bos_freshness",
                        "last_latest_reset_reason",
                        "last_latest_reset_freshness",
                        "last_subindustry_timing_state",
                        "last_subindustry_overheat_risk_level",
                        "last_layer_timing_state",
                        "last_layer_overheat_risk_level",
                        "last_price_data_status",
                    ],
                    watchlist_rows,
                ).rstrip(),
            ]
        )

    lines.extend(["", "## 4. Ecosystem window change"])
    if ecosystem_first is None or ecosystem_last is None:
        lines.append("Ecosystem row missing.")
    else:
        ecosystem_change_rows = []
        for field_name in (
            "return_5d",
            "return_10d",
            "return_20d",
            "pct_above_ma10",
            "pct_above_ema20",
            "ema20_breadth_delta_5d",
            "trend_breadth",
            "weakness_breadth",
        ):
            ecosystem_change_rows.append(
                {
                    "metric": field_name,
                    "first_value": ecosystem_first.get(field_name),
                    "last_value": ecosystem_last.get(field_name),
                    "change": _numeric_change(ecosystem_first, ecosystem_last, field_name),
                }
            )
        for field_name in ("timing_state", "overheat_risk_level", "data_quality_status"):
            ecosystem_change_rows.append(
                {
                    "metric": field_name,
                    "first_value": ecosystem_first.get(field_name),
                    "last_value": ecosystem_last.get(field_name),
                    "change": f"{ecosystem_first.get(field_name) or ''} -> {ecosystem_last.get(field_name) or ''}",
                }
            )
        lines.append(
            _format_table(
                ["metric", "first_value", "last_value", "change"],
                ecosystem_change_rows,
            ).rstrip()
        )

    lines.extend(["", "## 5. Overheat / rotation risk progression"])
    if any(row.get("overheat_risk_level") == "EXTREME" for row in end_group_rows):
        lines.append("EXTREME RISK – TIGHTEN STOPS / NO NEW LONGS")
    overheat_count_rows = _count_by_date_group_type_and_field(
        group_rows,
        date_field="signal_date",
        value_field="overheat_risk_level",
    )
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], overheat_count_rows).rstrip())
    lines.extend(["", "Worsened groups"])
    worsened_rows: list[dict[str, object]] = []
    for (_, group_type, group_name), current_rows in _group_rows_by_key(
        group_rows,
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        first_rank = OVERHEAT_RANK.get(first_row.get("overheat_risk_level"), 0)
        last_rank = OVERHEAT_RANK.get(last_row.get("overheat_risk_level"), 0)
        if last_rank > first_rank:
            worsened_rows.append(
                {
                    "group_type": group_type,
                    "group_name": group_name,
                    "first_overheat_risk_level": first_row.get("overheat_risk_level"),
                    "last_overheat_risk_level": last_row.get("overheat_risk_level"),
                    "risk_rank_change": last_rank - first_rank,
                    "last_return_10d": last_row.get("return_10d"),
                    "last_return_20d": last_row.get("return_20d"),
                    "last_ema20_breadth_delta_5d": last_row.get("ema20_breadth_delta_5d"),
                    "last_weakness_breadth": last_row.get("weakness_breadth"),
                }
            )
    worsened_rows.sort(
        key=lambda row: (
            -(int(row["risk_rank_change"])),
            -OVERHEAT_RANK.get(row.get("last_overheat_risk_level"), 0),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "first_overheat_risk_level",
                "last_overheat_risk_level",
                "risk_rank_change",
                "last_return_10d",
                "last_return_20d",
                "last_ema20_breadth_delta_5d",
                "last_weakness_breadth",
            ],
            worsened_rows,
        ).rstrip()
    )

    lines.extend(["", "## 6. Subindustry timing persistence"])
    timing_rows: list[dict[str, object]] = []
    for (_, _, group_name), current_rows in _group_rows_by_key(
        [row for row in group_rows if row.get("group_type") == "subindustry"],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        last_row = current_rows[-1]
        row = {
            "subindustry": group_name,
            "last_timing_state": last_row.get("timing_state"),
            "last_return_5d": last_row.get("return_5d"),
            "last_return_10d": last_row.get("return_10d"),
            "last_pct_above_ema20": last_row.get("pct_above_ema20"),
            "last_ema20_breadth_delta_5d": last_row.get("ema20_breadth_delta_5d"),
            "last_data_quality_status": last_row.get("data_quality_status"),
        }
        for state in TIMING_STATE_ORDER:
            column_name = "null_days" if state is None else f"{str(state).lower()}_days"
            row[column_name] = sum(1 for current_row in current_rows if current_row.get("timing_state") == state)
        timing_rows.append(row)
    timing_rows.sort(
        key=lambda row: (
            -int(row["exit_zone_days"]),
            -int(row["trim_watch_days"]),
            -int(row["buy_zone_days"]),
            str(row["subindustry"]),
        )
    )
    lines.append(
        _format_table(
            [
                "subindustry",
                "last_timing_state",
                "buy_zone_days",
                "add_on_pullback_days",
                "trim_watch_days",
                "exit_zone_days",
                "neutral_days",
                "null_days",
                "last_return_5d",
                "last_return_10d",
                "last_pct_above_ema20",
                "last_ema20_breadth_delta_5d",
                "last_data_quality_status",
            ],
            timing_rows,
        ).rstrip()
    )

    lines.extend(["", "## 7. Subindustry improvement / deterioration", "", "### A. Best relative subindustry changes"])
    change_rows: list[dict[str, object]] = []
    for (_, _, group_name), current_rows in _group_rows_by_key(
        [row for row in group_rows if row.get("group_type") == "subindustry"],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        change_rows.append(
            {
                "subindustry": group_name,
                "return_5d_change": _numeric_change(first_row, last_row, "return_5d"),
                "return_10d_change": _numeric_change(first_row, last_row, "return_10d"),
                "pct_above_ema20_change": _numeric_change(first_row, last_row, "pct_above_ema20"),
                "ema20_breadth_delta_5d_change": _numeric_change(first_row, last_row, "ema20_breadth_delta_5d"),
                "trend_breadth_change": _numeric_change(first_row, last_row, "trend_breadth"),
                "weakness_breadth_change": _numeric_change(first_row, last_row, "weakness_breadth"),
            }
        )
    improved_rows = sorted(
        change_rows,
        key=lambda row: (
            -(_float_value(row.get("pct_above_ema20_change")) or float("-inf")),
            -(_float_value(row.get("return_10d_change")) or float("-inf")),
            _float_value(row.get("weakness_breadth_change")) if row.get("weakness_breadth_change") is not None else float("inf"),
            str(row.get("subindustry") or ""),
        ),
    )[:top_n]
    deteriorated_rows = sorted(
        change_rows,
        key=lambda row: (
            _float_value(row.get("pct_above_ema20_change")) if row.get("pct_above_ema20_change") is not None else float("inf"),
            _float_value(row.get("return_10d_change")) if row.get("return_10d_change") is not None else float("inf"),
            -(_float_value(row.get("weakness_breadth_change")) or float("-inf")),
            str(row.get("subindustry") or ""),
        ),
    )[:top_n]
    change_headers = [
        "subindustry",
        "return_5d_change",
        "return_10d_change",
        "pct_above_ema20_change",
        "ema20_breadth_delta_5d_change",
        "trend_breadth_change",
        "weakness_breadth_change",
    ]
    lines.append(_format_table(change_headers, improved_rows).rstrip())
    lines.extend(["", "### B. Weakest relative subindustry changes"])
    lines.append(_format_table(change_headers, deteriorated_rows).rstrip())

    lines.extend(["", "## 8. Repeated breakout tickers"])
    breakout_rows = _build_repeated_ticker_rows(ticker_rows, signal_field="breakout_signal")
    breakout_rows.sort(
        key=lambda row: (
            -int(row["breakout_days"]),
            -(_float_value(row.get("last_return_10d")) or float("-inf")),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "breakout_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_10d",
                "last_volume_vs_avg20",
                "last_latest_structure_label",
                "last_ticker_trend_state",
                "last_latest_bos_event_type",
                "last_latest_bos_freshness",
                "last_latest_reset_reason",
                "last_latest_reset_freshness",
                "last_price_data_status",
            ],
            breakout_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 9. Repeated pullback tickers"])
    pullback_rows = _build_repeated_ticker_rows(
        ticker_rows,
        signal_field="pullback_signal",
        extra_count_fields=("fast_ema10_pullback_signal", "conservative_ema20_pullback_signal"),
    )
    pullback_rows.sort(
        key=lambda row: (
            -int(row["conservative_ema20_pullback_days"]),
            -int(row["fast_ema10_pullback_days"]),
            -int(row["pullback_days"]),
            -(_float_value(row.get("last_return_60d")) or float("-inf")),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "pullback_days",
                "fast_ema10_pullback_days",
                "conservative_ema20_pullback_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_20d",
                "last_return_60d",
                "last_latest_structure_label",
                "last_ticker_trend_state",
                "last_latest_bos_event_type",
                "last_latest_bos_freshness",
                "last_latest_reset_reason",
                "last_latest_reset_freshness",
                "last_bullish_candle_signal",
                "last_bullish_divergence_signal",
                "last_hidden_bullish_divergence_signal",
                "last_price_data_status",
            ],
            pullback_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 10. Repeated exit-risk tickers"])
    exit_rows = _build_repeated_ticker_rows(ticker_rows, signal_field="exit_risk_signal")
    exit_rows.sort(
        key=lambda row: (
            -int(row["exit_risk_days"]),
            EXIT_RISK_SEVERITY_PRIORITY.get(row.get("last_exit_risk_severity"), 3),
            _float_value(row.get("last_return_10d")) if row.get("last_return_10d") is not None else float("inf"),
            _float_value(row.get("last_distance_to_ema20_pct")) if row.get("last_distance_to_ema20_pct") is not None else float("inf"),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "exit_risk_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_10d",
                "last_return_20d",
                "last_distance_to_ema20_pct",
                "last_latest_structure_label",
                "last_latest_structure_age_trading_days",
                "last_latest_structure_freshness",
                "last_ticker_trend_state",
                "last_latest_bos_event_type",
                "last_latest_bos_freshness",
                "last_latest_reset_reason",
                "last_latest_reset_freshness",
                "last_exit_reason",
                "last_exit_risk_severity",
                "last_bearish_candle_signal",
                "last_bearish_divergence_signal",
                "last_hidden_bearish_divergence_signal",
                "last_price_data_status",
            ],
            exit_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 11. Synthetic OHLC structure changes"])
    synthetic_change_rows: list[dict[str, object]] = []
    for (_, group_type, group_name), current_rows in _group_rows_by_key(
        [row for row in synthetic_rows if row.get("group_type") in {"subindustry", "layer"}],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="ohlc_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        synthetic_change_rows.append(
            {
                "group_type": group_type,
                "group_name": group_name,
                "first_trend_classification": first_row.get("trend_classification"),
                "last_trend_classification": last_row.get("trend_classification"),
                "first_latest_structure_label": first_row.get("latest_structure_label"),
                "last_latest_structure_label": last_row.get("latest_structure_label"),
                "first_latest_structure_age_trading_days": first_row.get("latest_structure_age_trading_days"),
                "last_latest_structure_age_trading_days": last_row.get("latest_structure_age_trading_days"),
                "first_latest_structure_freshness": first_row.get("latest_structure_freshness"),
                "last_latest_structure_freshness": last_row.get("latest_structure_freshness"),
                "first_latest_bos_event_type": first_row.get("latest_bos_event_type"),
                "last_latest_bos_event_type": last_row.get("latest_bos_event_type"),
                "first_latest_bos_freshness": first_row.get("latest_bos_freshness"),
                "last_latest_bos_freshness": last_row.get("latest_bos_freshness"),
                "first_latest_reset_reason": first_row.get("latest_reset_reason"),
                "last_latest_reset_reason": last_row.get("latest_reset_reason"),
                "first_latest_reset_freshness": first_row.get("latest_reset_freshness"),
                "last_latest_reset_freshness": last_row.get("latest_reset_freshness"),
                "synthetic_close_change": _numeric_change(first_row, last_row, "synthetic_close"),
                "distance_to_ema20_pct_change": _numeric_change(first_row, last_row, "distance_to_ema20_pct"),
                "relative_close_extension_20_change": _numeric_change(first_row, last_row, "relative_close_extension_20"),
                "volatility_20d_change": _numeric_change(first_row, last_row, "volatility_20d"),
                "last_data_quality_status": last_row.get("data_quality_status"),
            }
        )
    synthetic_change_rows.sort(
        key=lambda row: (
            str(row.get("group_type") or ""),
            TREND_PRIORITY.get(row.get("last_trend_classification"), 3),
            -(_float_value(row.get("relative_close_extension_20_change")) or float("-inf")),
            str(row.get("group_name") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "first_trend_classification",
                "last_trend_classification",
                "first_latest_structure_label",
                "last_latest_structure_label",
                "first_latest_structure_age_trading_days",
                "last_latest_structure_age_trading_days",
                "first_latest_structure_freshness",
                "last_latest_structure_freshness",
                "first_latest_bos_event_type",
                "last_latest_bos_event_type",
                "first_latest_bos_freshness",
                "last_latest_bos_freshness",
                "first_latest_reset_reason",
                "last_latest_reset_reason",
                "first_latest_reset_freshness",
                "last_latest_reset_freshness",
                "synthetic_close_change",
                "distance_to_ema20_pct_change",
                "relative_close_extension_20_change",
                "volatility_20d_change",
                "last_data_quality_status",
            ],
            synthetic_change_rows,
        ).rstrip()
    )

    end_synthetic_rows = [row for row in synthetic_rows if row.get("ohlc_date") == window_end_date]
    group_context_by_date_key = {
        (row.get("signal_date"), row.get("group_type"), row.get("group_name")): row
        for row in group_rows
    }
    structure_event_rows: list[dict[str, object]] = []
    for row in synthetic_rows:
        if row.get("group_type") not in {"subindustry", "layer"}:
            continue
        if (
            row.get("latest_bos_confirmed_as_of_date") != row.get("ohlc_date")
            and row.get("latest_reset_confirmed_as_of_date") != row.get("ohlc_date")
        ):
            continue
        if row.get("latest_bos_event_type") is None and row.get("latest_reset_reason") is None:
            continue
        group_context = group_context_by_date_key.get(
            (row.get("ohlc_date"), row.get("group_type"), row.get("group_name")),
            {},
        )
        structure_event_rows.append(
            {
                "ohlc_date": row.get("ohlc_date"),
                "group_type": row.get("group_type"),
                "group_name": row.get("group_name"),
                "latest_bos_event_type": row.get("latest_bos_event_type"),
                "latest_bos_event_date": row.get("latest_bos_event_date"),
                "latest_bos_freshness": row.get("latest_bos_freshness"),
                "latest_reset_reason": row.get("latest_reset_reason"),
                "latest_reset_event_date": row.get("latest_reset_event_date"),
                "latest_reset_freshness": row.get("latest_reset_freshness"),
                "latest_structure_label": row.get("latest_structure_label"),
                "latest_structure_freshness": row.get("latest_structure_freshness"),
                "trend_classification": row.get("trend_classification"),
                "timing_state": group_context.get("timing_state"),
                "overheat_risk_level": group_context.get("overheat_risk_level"),
            }
        )
    structure_event_rows.sort(
        key=lambda row: (
            str(row.get("ohlc_date") or ""),
            GROUP_RESET_PRIORITY.get(row.get("latest_reset_reason"), 2),
            GROUP_BOS_PRIORITY.get(row.get("latest_bos_event_type"), 2),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        )
    )
    end_structure_rows: list[dict[str, object]] = []
    for row in end_synthetic_rows:
        if row.get("group_type") not in {"subindustry", "layer"}:
            continue
        if row.get("latest_bos_event_type") is None and row.get("latest_reset_reason") is None:
            continue
        group_context = group_context_by_date_key.get(
            (window_end_date, row.get("group_type"), row.get("group_name")),
            {},
        )
        end_structure_rows.append(
            {
                "group_type": row.get("group_type"),
                "group_name": row.get("group_name"),
                "latest_bos_event_type": row.get("latest_bos_event_type"),
                "latest_bos_event_date": row.get("latest_bos_event_date"),
                "latest_bos_freshness": row.get("latest_bos_freshness"),
                "latest_reset_reason": row.get("latest_reset_reason"),
                "latest_reset_event_date": row.get("latest_reset_event_date"),
                "latest_reset_freshness": row.get("latest_reset_freshness"),
                "latest_structure_label": row.get("latest_structure_label"),
                "latest_structure_freshness": row.get("latest_structure_freshness"),
                "trend_classification": row.get("trend_classification"),
                "timing_state": group_context.get("timing_state"),
                "overheat_risk_level": group_context.get("overheat_risk_level"),
            }
        )
    end_structure_rows.sort(
        key=lambda row: (
            GROUP_RESET_PRIORITY.get(row.get("latest_reset_reason"), 2),
            GROUP_BOS_PRIORITY.get(row.get("latest_bos_event_type"), 2),
            FRESHNESS_PRIORITY.get(row.get("latest_bos_freshness"), 3),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        )
    )

    lines.extend(["", "## 12. Group Structure Break / Reset History"])
    lines.extend(["", "### A. BOS / RESET events during window"])
    lines.append(
        _format_table(
            [
                "ohlc_date",
                "group_type",
                "group_name",
                "latest_bos_event_type",
                "latest_bos_event_date",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_event_date",
                "latest_reset_freshness",
                "latest_structure_label",
                "latest_structure_freshness",
                "trend_classification",
                "timing_state",
                "overheat_risk_level",
            ],
            structure_event_rows,
        ).rstrip()
    )
    lines.extend(["", "### B. Latest BOS / RESET state at window end"])
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "latest_bos_event_type",
                "latest_bos_event_date",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_event_date",
                "latest_reset_freshness",
                "latest_structure_label",
                "latest_structure_freshness",
                "trend_classification",
                "timing_state",
                "overheat_risk_level",
            ],
            end_structure_rows,
        ).rstrip()
    )

    lines.extend(["", "## 13. Data quality over the window"])
    group_quality_rows = _count_by_date_and_field(
        group_rows,
        date_field="signal_date",
        value_field="data_quality_status",
    )
    ticker_quality_rows = _count_by_date_and_field(
        ticker_rows,
        date_field="signal_date",
        value_field="price_data_status",
    )
    lines.append("Group data quality counts")
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], group_quality_rows).rstrip())
    lines.extend(["", "Ticker price data quality counts"])
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], ticker_quality_rows).rstrip())
    lines.extend(["", "End-date data quality details"])
    non_ok_end_groups = [
        {
            "group_type": row.get("group_type"),
            "group_name": row.get("group_name"),
            "data_quality_status": row.get("data_quality_status"),
        }
        for row in end_group_rows
        if row.get("data_quality_status") != "OK"
    ]
    lines.append(_format_table(["group_type", "group_name", "data_quality_status"], non_ok_end_groups).rstrip())
    end_ticker_rows = [row for row in ticker_rows if row.get("signal_date") == window_end_date]
    lines.extend(
        [
            "",
            _format_table(
                ["metric", "count"],
                [
                    {
                        "metric": "ticker_count_missing_as_of_date_end_date",
                        "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE"),
                    },
                    {
                        "metric": "ticker_count_missing_close_as_of_date_end_date",
                        "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE"),
                    },
                ],
            ).rstrip(),
        ]
    )

    lines.extend(["", "## 14. Missing / incomplete inputs summary"])
    lines.append("Window-total counts")
    lines.append(
        _format_table(
            ["metric", "count"],
            [
                {"metric": "group_rows_missing_timing_state", "count": sum(1 for row in group_rows if row.get("timing_state") is None)},
                {"metric": "group_rows_missing_overheat_risk_level", "count": sum(1 for row in group_rows if row.get("overheat_risk_level") is None)},
                {
                    "metric": "ticker_rows_with_scanner_fields_null",
                    "count": sum(
                        1
                        for row in ticker_rows
                        if any(
                            row.get(field_name) is None
                            for field_name in (
                                "breakout_signal",
                                "fast_ema10_pullback_signal",
                                "conservative_ema20_pullback_signal",
                                "pullback_signal",
                                "exit_risk_signal",
                            )
                        )
                    ),
                },
                {"metric": "synthetic_ohlc_rows_missing_latest_structure_label", "count": sum(1 for row in synthetic_rows if row.get("latest_structure_label") is None)},
                {"metric": "synthetic_ohlc_rows_missing_relative_close_20", "count": sum(1 for row in synthetic_rows if row.get("relative_close_20") is None)},
                {"metric": "ticker_rows_with_missing_as_of_date", "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE")},
                {"metric": "ticker_rows_with_missing_close_as_of_date", "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE")},
            ],
        ).rstrip()
    )
    lines.extend(["", "End-date-only counts"])
    lines.append(
        _format_table(
            ["metric", "count"],
            [
                {"metric": "group_rows_missing_timing_state_end_date", "count": sum(1 for row in end_group_rows if row.get("timing_state") is None)},
                {"metric": "group_rows_missing_overheat_risk_level_end_date", "count": sum(1 for row in end_group_rows if row.get("overheat_risk_level") is None)},
                {
                    "metric": "ticker_rows_with_scanner_fields_null_end_date",
                    "count": sum(
                        1
                        for row in end_ticker_rows
                        if any(
                            row.get(field_name) is None
                            for field_name in (
                                "breakout_signal",
                                "fast_ema10_pullback_signal",
                                "conservative_ema20_pullback_signal",
                                "pullback_signal",
                                "exit_risk_signal",
                            )
                        )
                    ),
                },
                {"metric": "synthetic_ohlc_rows_missing_latest_structure_label_end_date", "count": sum(1 for row in end_synthetic_rows if row.get("latest_structure_label") is None)},
                {"metric": "synthetic_ohlc_rows_missing_relative_close_20_end_date", "count": sum(1 for row in end_synthetic_rows if row.get("relative_close_20") is None)},
                {"metric": "ticker_rows_with_missing_as_of_date_end_date", "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE")},
                {"metric": "ticker_rows_with_missing_close_as_of_date_end_date", "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE")},
            ],
        ).rstrip()
    )
    return "\n".join(lines).strip() + "\n"


def build_csv_weekly_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    rows = _build_csv_rows_from_markdown(markdown)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    max_columns = max((len(row) for row in rows), default=1)
    writer.writerow(["section", *(f"value_{index}" for index in range(1, max_columns))])
    for row in rows:
        writer.writerow([*row, *([""] * (max_columns - len(row)))])
    return output.getvalue()


def format_weekly_swing_report_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in WEEKLY_REPORT_SUMMARY_ORDER if key in summary]


def write_weekly_swing_report(
    *,
    analysis_db_path: str | Path,
    end_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    taxonomy_version: str | None = None,
    window_size: int = DEFAULT_WEEKLY_WINDOW_SIZE,
    output_md: str | Path | None = None,
    output_csv: str | Path | None = None,
    watchlist_file: str | Path | None = None,
    top_n: int = 20,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db_path,
        end_date=end_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        taxonomy_version=taxonomy_version,
        window_size=window_size,
        watchlist_file=watchlist_file,
    )
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    csv_text = build_csv_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    output_md_value = ""
    output_csv_value = ""
    if output_md is not None:
        output_md_path = _normalize_path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(markdown, encoding="utf-8")
        output_md_value = str(output_md_path)
    if output_csv is not None:
        output_csv_path = _normalize_path(output_csv)
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        output_csv_path.write_text(csv_text, encoding="utf-8")
        output_csv_value = str(output_csv_path)

    breakout_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="breakout_signal"))  # type: ignore[arg-type]
    pullback_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="pullback_signal"))  # type: ignore[arg-type]
    exit_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="exit_risk_signal"))  # type: ignore[arg-type]
    valid_signal_dates = list(report_data["valid_signal_dates"])  # type: ignore[arg-type]
    summary = {
        "end_date": str(report_data["requested_end_date"]),
        "signal_version": str(report_data["signal_version"]),
        "ohlc_calc_version": str(report_data["ohlc_calc_version"]),
        "taxonomy_version": "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"]),
        "taxonomy_version_inferred": int(report_data.get("taxonomy_version_inferred") or 0),
        "window_size": int(report_data.get("window_size") or DEFAULT_WEEKLY_WINDOW_SIZE),
        "valid_signal_dates_count": len(valid_signal_dates),
        "window_start_date": valid_signal_dates[0] if valid_signal_dates else "",
        "window_end_date": valid_signal_dates[-1] if valid_signal_dates else "",
        "incomplete_window": "YES" if len(valid_signal_dates) < int(report_data.get("window_size") or DEFAULT_WEEKLY_WINDOW_SIZE) else "NO",
        "group_rows": len(report_data["group_rows"]),  # type: ignore[arg-type]
        "ticker_rows": len(report_data["ticker_rows"]),  # type: ignore[arg-type]
        "synthetic_ohlc_rows": len(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        "repeated_breakout_tickers": breakout_count,
        "repeated_pullback_tickers": pullback_count,
        "repeated_exit_risk_tickers": exit_count,
        "output_markdown": output_md_value,
        "output_csv": output_csv_value,
        "validation_status": "OK",
    }
    return {
        "markdown": markdown,
        "csv": csv_text,
        "summary": summary,
    }
