from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence

DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"
DEFAULT_WEEKLY_WINDOW_SIZE = 5

PIPELINE_AUDIT_SUMMARY_ORDER = [
    "signal_date",
    "taxonomy_version",
    "signal_version",
    "ohlc_calc_version",
    "missing_tables",
    "ticker_rows",
    "distinct_tickers",
    "ok_price_count",
    "missing_as_of_date_count",
    "missing_close_as_of_date_count",
    "insufficient_history_count",
    "scanner_null_count",
    "exit_risk_severity_missing_for_exit_risk_count",
    "ticker_structure_label_invalid_count",
    "ticker_structure_freshness_missing_when_label_present_count",
    "ticker_trend_state_null_count",
    "latest_bos_context_count",
    "latest_reset_context_count",
    "group_rows",
    "ecosystem_group_rows",
    "layer_group_rows",
    "subindustry_group_rows",
    "non_ok_group_count",
    "timing_state_null_count",
    "overheat_risk_level_null_count",
    "group_rows_missing_return_5d",
    "group_rows_missing_return_10d",
    "group_rows_missing_return_20d",
    "group_rows_missing_return_60d",
    "group_rows_missing_pct_above_ema20",
    "group_rows_missing_ema20_breadth_delta_5d",
    "synthetic_ohlc_rows",
    "synthetic_layer_rows",
    "synthetic_subindustry_rows",
    "synthetic_non_ok_count",
    "synthetic_missing_close_count",
    "synthetic_missing_ema20_count",
    "synthetic_missing_relative_close_20_count",
    "synthetic_missing_latest_structure_label_count",
    "synthetic_structure_freshness_missing_when_label_present_count",
    "synthetic_trend_classification_null_count",
    "weekly_valid_signal_dates_count",
    "weekly_window_start_date",
    "weekly_window_end_date",
    "weekly_incomplete_window",
    "daily_ready",
    "weekly_ready",
    "validation_status",
]

REQUIRED_TABLES = [
    "dc_ticker_swing_signal_daily",
    "dc_group_swing_signal_daily",
    "dc_group_synthetic_ohlc_daily",
    "dc_group_index_daily",
]

VALID_TICKER_STRUCTURE_LABELS = {"HH", "HL", "LH", "LL"}


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _count_rows(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    where_sql: str,
    params: Sequence[object],
) -> int:
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}",
            params,
        ).fetchone()[0]
    )


def _load_selected_taxonomy_versions(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_field: str,
    date_value: str,
    version_field: str,
    version_value: str,
) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT taxonomy_version
        FROM {table_name}
        WHERE {date_field} = ?
          AND {version_field} = ?
        ORDER BY taxonomy_version ASC
        """,
        (date_value, version_value),
    ).fetchall()
    return [str(row["taxonomy_version"]) for row in rows if row["taxonomy_version"] is not None]


def _load_weekly_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
    window_size: int,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT signal_date
        FROM dc_group_swing_signal_daily
        WHERE signal_date <= ?
          AND taxonomy_version = ?
          AND signal_version = ?
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (signal_date, taxonomy_version, signal_version, window_size),
    ).fetchall()
    return sorted(str(row["signal_date"]) for row in rows)


def _find_missing_required_tables(conn: sqlite3.Connection, required_tables: Sequence[str]) -> list[str]:
    existing = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }
    return [table for table in required_tables if table not in existing]


def _ticker_summary(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS ticker_rows,
            COUNT(DISTINCT ticker) AS distinct_tickers,
            SUM(CASE WHEN price_data_status = 'OK' THEN 1 ELSE 0 END) AS ok_price_count,
            SUM(CASE WHEN price_data_status = 'MISSING_AS_OF_DATE' THEN 1 ELSE 0 END) AS missing_as_of_date_count,
            SUM(CASE WHEN price_data_status = 'MISSING_CLOSE_AS_OF_DATE' THEN 1 ELSE 0 END) AS missing_close_as_of_date_count,
            SUM(CASE WHEN price_data_status = 'INSUFFICIENT_HISTORY' THEN 1 ELSE 0 END) AS insufficient_history_count,
            SUM(
                CASE
                    WHEN breakout_signal IS NULL
                      OR fast_ema10_pullback_signal IS NULL
                      OR conservative_ema20_pullback_signal IS NULL
                      OR pullback_signal IS NULL
                      OR exit_risk_signal IS NULL
                    THEN 1 ELSE 0
                END
            ) AS scanner_null_count,
            SUM(
                CASE
                    WHEN exit_risk_signal = 1 AND exit_risk_severity IS NULL
                    THEN 1 ELSE 0
                END
            ) AS exit_risk_severity_missing_for_exit_risk_count,
            SUM(
                CASE
                    WHEN latest_structure_label IS NOT NULL
                     AND latest_structure_label NOT IN ('HH', 'HL', 'LH', 'LL')
                    THEN 1 ELSE 0
                END
            ) AS ticker_structure_label_invalid_count,
            SUM(
                CASE
                    WHEN latest_structure_label IS NOT NULL
                     AND latest_structure_freshness IS NULL
                    THEN 1 ELSE 0
                END
            ) AS ticker_structure_freshness_missing_when_label_present_count,
            SUM(CASE WHEN ticker_trend_state IS NULL THEN 1 ELSE 0 END) AS ticker_trend_state_null_count,
            SUM(CASE WHEN latest_bos_event_type IS NOT NULL THEN 1 ELSE 0 END) AS latest_bos_context_count,
            SUM(
                CASE
                    WHEN latest_reset_reason IS NOT NULL OR latest_reset_event_date IS NOT NULL
                    THEN 1 ELSE 0
                END
            ) AS latest_reset_context_count
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND signal_version = ?
        """,
        (signal_date, taxonomy_version, signal_version),
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _group_summary(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS group_rows,
            SUM(CASE WHEN group_type = 'ecosystem' THEN 1 ELSE 0 END) AS ecosystem_group_rows,
            SUM(CASE WHEN group_type = 'layer' THEN 1 ELSE 0 END) AS layer_group_rows,
            SUM(CASE WHEN group_type = 'subindustry' THEN 1 ELSE 0 END) AS subindustry_group_rows,
            SUM(CASE WHEN data_quality_status IS NOT NULL AND data_quality_status <> 'OK' THEN 1 ELSE 0 END) AS non_ok_group_count,
            SUM(CASE WHEN timing_state IS NULL THEN 1 ELSE 0 END) AS timing_state_null_count,
            SUM(CASE WHEN overheat_risk_level IS NULL THEN 1 ELSE 0 END) AS overheat_risk_level_null_count,
            SUM(CASE WHEN return_5d IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_return_5d,
            SUM(CASE WHEN return_10d IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_return_10d,
            SUM(CASE WHEN return_20d IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_return_20d,
            SUM(CASE WHEN return_60d IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_return_60d,
            SUM(CASE WHEN pct_above_ema20 IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_pct_above_ema20,
            SUM(CASE WHEN ema20_breadth_delta_5d IS NULL THEN 1 ELSE 0 END) AS group_rows_missing_ema20_breadth_delta_5d
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND signal_version = ?
        """,
        (signal_date, taxonomy_version, signal_version),
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _synthetic_summary(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    ohlc_calc_version: str,
) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS synthetic_ohlc_rows,
            SUM(CASE WHEN group_type = 'layer' THEN 1 ELSE 0 END) AS synthetic_layer_rows,
            SUM(CASE WHEN group_type = 'subindustry' THEN 1 ELSE 0 END) AS synthetic_subindustry_rows,
            SUM(CASE WHEN data_quality_status IS NOT NULL AND data_quality_status <> 'OK' THEN 1 ELSE 0 END) AS synthetic_non_ok_count,
            SUM(CASE WHEN synthetic_close IS NULL THEN 1 ELSE 0 END) AS synthetic_missing_close_count,
            SUM(CASE WHEN ema20 IS NULL THEN 1 ELSE 0 END) AS synthetic_missing_ema20_count,
            SUM(CASE WHEN relative_close_20 IS NULL THEN 1 ELSE 0 END) AS synthetic_missing_relative_close_20_count,
            -- Reset intentionally clears latest_structure_label until a new pivot structure is confirmed,
            -- so valid reset-state NULL labels are excluded from the missing-structure warning count.
            SUM(
                CASE
                    WHEN latest_structure_label IS NULL
                     AND NOT (
                        data_quality_status = 'OK'
                        AND trend_classification = 'NEUTRAL'
                        AND latest_reset_event_date IS NOT NULL
                        AND synthetic_close IS NOT NULL
                        AND ema20 IS NOT NULL
                        AND relative_close_20 IS NOT NULL
                     )
                    THEN 1 ELSE 0
                END
            ) AS synthetic_missing_latest_structure_label_count,
            SUM(
                CASE
                    WHEN latest_structure_label IS NOT NULL
                     AND latest_structure_freshness IS NULL
                    THEN 1 ELSE 0
                END
            ) AS synthetic_structure_freshness_missing_when_label_present_count,
            SUM(CASE WHEN trend_classification IS NULL THEN 1 ELSE 0 END) AS synthetic_trend_classification_null_count
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
          AND taxonomy_version = ?
          AND calc_version = ?
        """,
        (signal_date, taxonomy_version, ohlc_calc_version),
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}


def _date_level_scanner_null_count(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
) -> int:
    return int(
        conn.execute(
            """
            SELECT
                SUM(
                    CASE
                        WHEN breakout_signal IS NULL
                          OR fast_ema10_pullback_signal IS NULL
                          OR conservative_ema20_pullback_signal IS NULL
                          OR pullback_signal IS NULL
                          OR exit_risk_signal IS NULL
                        THEN 1 ELSE 0
                    END
                )
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND signal_version = ?
            """,
            (signal_date, taxonomy_version, signal_version),
        ).fetchone()[0]
        or 0
    )


def load_swing_pipeline_audit(
    *,
    analysis_db_path: str | Path,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    expected_ticker_count: int | None = None,
    expected_group_count: int | None = None,
    expected_synthetic_ohlc_count: int | None = None,
    weekly_window_size: int = DEFAULT_WEEKLY_WINDOW_SIZE,
    strict: bool = False,
) -> dict[str, object]:
    normalized_signal_date = _parse_iso_date(signal_date, "signal_date")
    if weekly_window_size <= 0:
        raise ValueError("weekly_window_size must be greater than 0")

    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        missing_tables = _find_missing_required_tables(conn, REQUIRED_TABLES)
        if missing_tables:
            summary = {
                "signal_date": normalized_signal_date,
                "taxonomy_version": taxonomy_version,
                "signal_version": signal_version,
                "ohlc_calc_version": ohlc_calc_version,
                "missing_tables": ",".join(missing_tables),
                "ticker_rows": 0,
                "distinct_tickers": 0,
                "ok_price_count": 0,
                "missing_as_of_date_count": 0,
                "missing_close_as_of_date_count": 0,
                "insufficient_history_count": 0,
                "scanner_null_count": 0,
                "exit_risk_severity_missing_for_exit_risk_count": 0,
                "ticker_structure_label_invalid_count": 0,
                "ticker_structure_freshness_missing_when_label_present_count": 0,
                "ticker_trend_state_null_count": 0,
                "latest_bos_context_count": 0,
                "latest_reset_context_count": 0,
                "group_rows": 0,
                "ecosystem_group_rows": 0,
                "layer_group_rows": 0,
                "subindustry_group_rows": 0,
                "non_ok_group_count": 0,
                "timing_state_null_count": 0,
                "overheat_risk_level_null_count": 0,
                "group_rows_missing_return_5d": 0,
                "group_rows_missing_return_10d": 0,
                "group_rows_missing_return_20d": 0,
                "group_rows_missing_return_60d": 0,
                "group_rows_missing_pct_above_ema20": 0,
                "group_rows_missing_ema20_breadth_delta_5d": 0,
                "synthetic_ohlc_rows": 0,
                "synthetic_layer_rows": 0,
                "synthetic_subindustry_rows": 0,
                "synthetic_non_ok_count": 0,
                "synthetic_missing_close_count": 0,
                "synthetic_missing_ema20_count": 0,
                "synthetic_missing_relative_close_20_count": 0,
                "synthetic_missing_latest_structure_label_count": 0,
                "synthetic_structure_freshness_missing_when_label_present_count": 0,
                "synthetic_trend_classification_null_count": 0,
                "weekly_valid_signal_dates_count": 0,
                "weekly_window_start_date": "",
                "weekly_window_end_date": "",
                "weekly_incomplete_window": "YES",
                "daily_ready": "NO",
                "weekly_ready": "NO",
                "validation_status": "FAIL",
            }
            return {
                "summary": summary,
                "weekly_dates": [],
                "weekly_checks": [],
                "fail_reasons": ["missing_tables"],
                "warn_reasons": [],
                "taxonomy_versions": {"ticker": [], "group": [], "synthetic": []},
            }

        ticker = _ticker_summary(
            conn,
            signal_date=normalized_signal_date,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
        )
        group = _group_summary(
            conn,
            signal_date=normalized_signal_date,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
        )
        synthetic = _synthetic_summary(
            conn,
            signal_date=normalized_signal_date,
            taxonomy_version=taxonomy_version,
            ohlc_calc_version=ohlc_calc_version,
        )
        weekly_dates = _load_weekly_valid_signal_dates(
            conn,
            signal_date=normalized_signal_date,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
            window_size=weekly_window_size,
        )
        ticker_taxonomy_versions = _load_selected_taxonomy_versions(
            conn,
            table_name="dc_ticker_swing_signal_daily",
            date_field="signal_date",
            date_value=normalized_signal_date,
            version_field="signal_version",
            version_value=signal_version,
        )
        group_taxonomy_versions = _load_selected_taxonomy_versions(
            conn,
            table_name="dc_group_swing_signal_daily",
            date_field="signal_date",
            date_value=normalized_signal_date,
            version_field="signal_version",
            version_value=signal_version,
        )
        synthetic_taxonomy_versions = _load_selected_taxonomy_versions(
            conn,
            table_name="dc_group_synthetic_ohlc_daily",
            date_field="ohlc_date",
            date_value=normalized_signal_date,
            version_field="calc_version",
            version_value=ohlc_calc_version,
        )

        weekly_checks: list[dict[str, object]] = []
        for weekly_date in weekly_dates:
            weekly_ticker_rows = _count_rows(
                conn,
                table_name="dc_ticker_swing_signal_daily",
                where_sql="signal_date = ? AND taxonomy_version = ? AND signal_version = ?",
                params=(weekly_date, taxonomy_version, signal_version),
            )
            weekly_group_rows = _count_rows(
                conn,
                table_name="dc_group_swing_signal_daily",
                where_sql="signal_date = ? AND taxonomy_version = ? AND signal_version = ?",
                params=(weekly_date, taxonomy_version, signal_version),
            )
            weekly_synthetic_rows = _count_rows(
                conn,
                table_name="dc_group_synthetic_ohlc_daily",
                where_sql="ohlc_date = ? AND taxonomy_version = ? AND calc_version = ?",
                params=(weekly_date, taxonomy_version, ohlc_calc_version),
            )
            weekly_checks.append(
                {
                    "signal_date": weekly_date,
                    "ticker_rows": weekly_ticker_rows,
                    "group_rows": weekly_group_rows,
                    "synthetic_ohlc_rows": weekly_synthetic_rows,
                    "scanner_null_count": _date_level_scanner_null_count(
                        conn,
                        signal_date=weekly_date,
                        taxonomy_version=taxonomy_version,
                        signal_version=signal_version,
                    ),
                }
            )

    daily_ready = (
        ticker["ticker_rows"] > 0
        and group["group_rows"] > 0
        and synthetic["synthetic_ohlc_rows"] > 0
        and ticker["scanner_null_count"] == 0
        and group["timing_state_null_count"] == 0
        and group["non_ok_group_count"] == 0
    )
    weekly_incomplete_window = len(weekly_dates) < weekly_window_size
    weekly_ready = (
        len(weekly_dates) == weekly_window_size
        and bool(weekly_dates)
        and weekly_dates[-1] == normalized_signal_date
        and all(
            check["ticker_rows"] > 0
            and check["group_rows"] > 0
            and check["synthetic_ohlc_rows"] > 0
            and check["scanner_null_count"] == 0
            for check in weekly_checks
        )
    )

    expected_count_issues: list[str] = []
    if expected_ticker_count is not None and ticker["ticker_rows"] != expected_ticker_count:
        expected_count_issues.append("ticker_rows")
    if expected_group_count is not None and group["group_rows"] != expected_group_count:
        expected_count_issues.append("group_rows")
    if expected_synthetic_ohlc_count is not None and synthetic["synthetic_ohlc_rows"] != expected_synthetic_ohlc_count:
        expected_count_issues.append("synthetic_ohlc_rows")

    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    if ticker["ticker_rows"] == 0:
        fail_reasons.append("no_ticker_rows")
    if group["group_rows"] == 0:
        fail_reasons.append("no_group_rows")
    if ticker["scanner_null_count"] > 0:
        fail_reasons.append("scanner_null_count")
    if group["timing_state_null_count"] > 0:
        fail_reasons.append("timing_state_null_count")
    if ticker["ticker_structure_label_invalid_count"] > 0:
        fail_reasons.append("ticker_structure_label_invalid_count")
    if ticker["exit_risk_severity_missing_for_exit_risk_count"] > 0:
        fail_reasons.append("exit_risk_severity_missing_for_exit_risk_count")
    if strict and not weekly_ready:
        fail_reasons.append("weekly_ready")
    if strict and expected_count_issues:
        fail_reasons.extend(expected_count_issues)

    if not fail_reasons:
        if expected_count_issues:
            warn_reasons.extend(expected_count_issues)
        if ticker["missing_as_of_date_count"] > 0:
            warn_reasons.append("missing_as_of_date_count")
        if group["overheat_risk_level_null_count"] > 0:
            warn_reasons.append("overheat_risk_level_null_count")
        if synthetic["synthetic_missing_latest_structure_label_count"] > 0:
            warn_reasons.append("synthetic_missing_latest_structure_label_count")
        if not weekly_ready:
            warn_reasons.append("weekly_ready")

    validation_status = "FAIL" if fail_reasons else ("WARN" if warn_reasons else "OK")

    summary: dict[str, object] = {
        "signal_date": normalized_signal_date,
        "taxonomy_version": taxonomy_version,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        **ticker,
        **group,
        **synthetic,
        "weekly_valid_signal_dates_count": len(weekly_dates),
        "weekly_window_start_date": weekly_dates[0] if weekly_dates else "",
        "weekly_window_end_date": weekly_dates[-1] if weekly_dates else "",
        "weekly_incomplete_window": _yes_no(weekly_incomplete_window),
        "daily_ready": _yes_no(daily_ready),
        "weekly_ready": _yes_no(weekly_ready),
        "validation_status": validation_status,
    }
    if expected_ticker_count is not None:
        summary["expected_ticker_count"] = expected_ticker_count
    if expected_group_count is not None:
        summary["expected_group_count"] = expected_group_count
    if expected_synthetic_ohlc_count is not None:
        summary["expected_synthetic_ohlc_count"] = expected_synthetic_ohlc_count

    return {
        "summary": summary,
        "weekly_dates": weekly_dates,
        "weekly_checks": weekly_checks,
        "fail_reasons": fail_reasons,
        "warn_reasons": warn_reasons,
        "taxonomy_versions": {
            "ticker": ticker_taxonomy_versions,
            "group": group_taxonomy_versions,
            "synthetic": synthetic_taxonomy_versions,
        },
    }


def format_swing_pipeline_audit_summary_lines(summary: dict[str, object]) -> list[str]:
    keys = list(PIPELINE_AUDIT_SUMMARY_ORDER)
    for optional_key in (
        "expected_ticker_count",
        "expected_group_count",
        "expected_synthetic_ohlc_count",
    ):
        if optional_key in summary:
            keys.append(optional_key)
    return [f"SUMMARY {key}={summary[key]}" for key in keys if key in summary]
