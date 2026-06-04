from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE_TICKER = "dc_ticker_swing_signal_daily"
SOURCE_TABLE_GROUP = "dc_group_swing_signal_daily"
TARGET_ENTITY_TYPE = "TICKER"
TARGET_WINDOWS = ("rolling2", "rolling5", "rolling30")
WINDOW_DATE_COUNTS = {
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
TARGET_METRICS = (
    "breakout_days",
    "pullback_days",
    "exit_risk_days",
    "high_exit_risk_days",
    "medium_exit_risk_days",
    "valid_signal_dates",
    "distance_to_ema20_pct",
)
COUNT_METRICS = (
    "breakout_days",
    "pullback_days",
    "exit_risk_days",
    "high_exit_risk_days",
    "medium_exit_risk_days",
    "valid_signal_dates",
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_one(conn: sqlite3.Connection, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    return conn.execute(query, params).fetchone()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _resolve_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = _fetch_one(
        conn,
        """
        SELECT
            rr.run_id,
            rr.ecosystem_id,
            ee.ecosystem_code,
            rr.taxonomy_version_id,
            tv.version_code,
            rr.signal_date
        FROM eco_report_run rr
        JOIN eco_ecosystem ee ON ee.ecosystem_id = rr.ecosystem_id
        JOIN eco_taxonomy_version tv ON tv.taxonomy_version_id = rr.taxonomy_version_id
        WHERE rr.run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        raise ValueError(f"Missing eco_report_run for run_id '{run_id}'")
    return row


def _load_target_coverage(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    rows = conn.execute(
        f"""
        SELECT
            c.run_id,
            c.ecosystem_id,
            c.signal_date,
            c.taxonomy_version_id,
            c.window_code,
            c.entity_id,
            e.entity_code
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND e.entity_type = ?
        ORDER BY c.window_code, e.entity_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            *TARGET_WINDOWS,
            TARGET_ENTITY_TYPE,
        ),
    ).fetchall()
    if not rows:
        raise ValueError(
            f"Missing eligible {TARGET_ENTITY_TYPE} rolling-window coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _load_metric_unit_conventions(conn: sqlite3.Connection, run_row: sqlite3.Row) -> dict[str, str | None]:
    rows = conn.execute(
        f"""
        SELECT m.metric_name, m.metric_unit, COUNT(*) AS n
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.signal_date = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND e.entity_type = ?
          AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
        GROUP BY m.metric_name, m.metric_unit
        ORDER BY m.metric_name, m.metric_unit
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_WINDOWS,
            TARGET_ENTITY_TYPE,
            *TARGET_METRICS,
        ),
    ).fetchall()
    units_by_metric: dict[str, set[str | None]] = {metric_name: set() for metric_name in TARGET_METRICS}
    for row in rows:
        units_by_metric[str(row["metric_name"])].add(_normalize_text(row["metric_unit"]))
    conventions: dict[str, str | None] = {}
    for metric_name, units in units_by_metric.items():
        if len(units) > 1:
            raise ValueError(f"Multiple metric_unit conventions found for metric '{metric_name}'")
        conventions[metric_name] = next(iter(units)) if units else None
    return conventions


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    limit: int,
) -> list[str]:
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    required = {"signal_date", "taxonomy_version"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required columns: {', '.join(missing)}")
    rows = conn.execute(
        f"""
        SELECT DISTINCT signal_date
        FROM {SOURCE_TABLE_GROUP}
        WHERE signal_date <= ?
          AND taxonomy_version = ?
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (signal_date, taxonomy_version_code, limit),
    ).fetchall()
    selected_dates = sorted(str(row["signal_date"]) for row in rows)
    if len(selected_dates) < limit:
        raise ValueError(
            f"Not enough valid signal_date values in '{SOURCE_TABLE_GROUP}' for limit={limit}; "
            f"found {len(selected_dates)}"
        )
    return selected_dates


def _load_ticker_history_rows(
    conn: sqlite3.Connection,
    *,
    selected_dates: list[str],
    taxonomy_version_code: str,
    eligible_tickers: list[str],
) -> tuple[list[sqlite3.Row], set[str]]:
    if not _table_exists(conn, SOURCE_TABLE_TICKER):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_TICKER}'")
    columns = _column_names(conn, SOURCE_TABLE_TICKER)
    required = {
        "ticker",
        "signal_date",
        "taxonomy_version",
        "breakout_signal",
        "pullback_signal",
        "exit_risk_signal",
        "exit_risk_severity",
        "distance_to_ema20_pct",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing required columns: {', '.join(missing)}")
    if "run_id" not in columns and "signal_version" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing both run_id and signal_version")
    if not selected_dates or not eligible_tickers:
        return [], columns
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_TICKER}
        WHERE signal_date IN ({", ".join("?" for _ in selected_dates)})
          AND taxonomy_version = ?
          AND ticker IN ({", ".join("?" for _ in eligible_tickers)})
        ORDER BY ticker, signal_date
        """,
        (*selected_dates, taxonomy_version_code, *eligible_tickers),
    ).fetchall()
    return rows, columns


def _existing_target_row_count(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            WHERE m.run_id = ?
              AND m.signal_date = ?
              AND m.taxonomy_version_id = ?
              AND m.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
              AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
              AND EXISTS (
                SELECT 1
                FROM eco_entity e
                WHERE e.entity_id = m.entity_id
                  AND e.entity_type = ?
              )
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                *TARGET_WINDOWS,
                *TARGET_METRICS,
                TARGET_ENTITY_TYPE,
            ),
        ).fetchone()[0]
    )


def _delete_existing_rows(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    cursor = conn.execute(
        f"""
        DELETE FROM eco_entity_metric_value
        WHERE run_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
          AND window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
          AND EXISTS (
            SELECT 1
            FROM eco_entity e
            WHERE e.entity_id = eco_entity_metric_value.entity_id
              AND e.entity_type = ?
          )
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_WINDOWS,
            *TARGET_METRICS,
            TARGET_ENTITY_TYPE,
        ),
    )
    return int(cursor.rowcount)


def _derive_source_run_id(rows: list[sqlite3.Row], columns: set[str]) -> str | None:
    run_ids = set()
    signal_versions = set()
    if "run_id" in columns:
        run_ids = {_normalize_text(row["run_id"]) for row in rows if _normalize_text(row["run_id"]) is not None}
    if "signal_version" in columns:
        signal_versions = {
            _normalize_text(row["signal_version"]) for row in rows if _normalize_text(row["signal_version"]) is not None
        }
    if len(run_ids) == 1:
        return next(iter(run_ids))
    if len(signal_versions) == 1:
        return next(iter(signal_versions))
    return None


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    entity_id: int,
    metric_name: str,
    metric_value_num: float | int,
    metric_unit: str | None,
    source_run_id: str,
) -> dict[str, object]:
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": metric_value_num,
        "metric_value_text": None,
        "metric_unit": metric_unit,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def build_canonical_v3_ticker_window_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        unit_conventions = _load_metric_unit_conventions(conn, run_row)
        existing_rows = _existing_target_row_count(conn, run_row)
        if existing_rows and not replace_existing:
            raise ValueError(
                f"Found {existing_rows} existing target metric rows for run_id '{run_id}' and replace_existing=False"
            )

        coverage_by_window: dict[str, list[sqlite3.Row]] = {window_code: [] for window_code in TARGET_WINDOWS}
        for row in coverage_rows:
            coverage_by_window[str(row["window_code"])].append(row)

        metric_rows: list[dict[str, object]] = []
        warnings: list[str] = []
        metric_name_counts: Counter[str] = Counter()
        metric_name_counts_by_window: dict[str, Counter[str]] = {
            window_code: Counter() for window_code in TARGET_WINDOWS
        }
        metric_unit_counts: Counter[str | None] = Counter()
        metric_value_status_counts: Counter[str] = Counter()
        source_run_id_counts: Counter[str] = Counter()
        selected_ticker_entity_count_by_window: dict[str, int] = {}
        selected_window_dates: dict[str, list[str]] = {}
        source_rows_read_by_window: dict[str, int] = {}
        source_rows_mapped_by_window: dict[str, int] = {}
        source_rows_skipped_by_window: dict[str, int] = {}
        missing_source_tickers_by_window: dict[str, list[str]] = {}
        mixed_source_run_warning_count = 0

        for window_code in TARGET_WINDOWS:
            current_coverage = coverage_by_window[window_code]
            selected_ticker_entity_count_by_window[window_code] = len(current_coverage)
            selected_dates = _load_valid_signal_dates(
                conn,
                signal_date=str(run_row["signal_date"]),
                taxonomy_version_code=str(run_row["version_code"]),
                limit=WINDOW_DATE_COUNTS[window_code],
            )
            selected_window_dates[window_code] = selected_dates
            eligible_tickers = [str(row["entity_code"]) for row in current_coverage]
            source_rows, source_columns = _load_ticker_history_rows(
                conn,
                selected_dates=selected_dates,
                taxonomy_version_code=str(run_row["version_code"]),
                eligible_tickers=eligible_tickers,
            )
            source_rows_read_by_window[window_code] = len(source_rows)
            source_rows_mapped_by_window[window_code] = 0
            source_rows_skipped_by_window[window_code] = 0
            missing_source_tickers_by_window[window_code] = []

            rows_by_ticker: dict[str, list[sqlite3.Row]] = {}
            for row in source_rows:
                rows_by_ticker.setdefault(str(row["ticker"]), []).append(row)

            for coverage_row in current_coverage:
                ticker = str(coverage_row["entity_code"])
                current_rows = rows_by_ticker.get(ticker)
                if not current_rows or len(current_rows) < len(selected_dates):
                    warnings.append(f"Missing lower-level ticker history for {window_code} ticker '{ticker}'")
                    missing_source_tickers_by_window[window_code].append(ticker)
                    continue
                current_rows = sorted(current_rows, key=lambda row: str(row["signal_date"]))
                source_run_id = _derive_source_run_id(current_rows, source_columns)
                if source_run_id is None:
                    mixed_source_run_warning_count += 1
                    source_rows_skipped_by_window[window_code] += 1
                    warnings.append(
                        f"Mixed lower-level lineage for {window_code} ticker '{ticker}', skipping derived metric rows"
                    )
                    continue

                rows_before = len(metric_rows)
                breakout_days = sum(1 for row in current_rows if int(row["breakout_signal"] or 0) == 1)
                pullback_days = sum(1 for row in current_rows if int(row["pullback_signal"] or 0) == 1)
                exit_risk_days = sum(1 for row in current_rows if int(row["exit_risk_signal"] or 0) == 1)
                high_exit_risk_days = sum(
                    1 for row in current_rows if _normalize_text(row["exit_risk_severity"]) == "HIGH"
                )
                medium_exit_risk_days = sum(
                    1 for row in current_rows if _normalize_text(row["exit_risk_severity"]) == "MEDIUM"
                )
                metric_values: dict[str, float | int | None] = {
                    "breakout_days": breakout_days,
                    "pullback_days": pullback_days,
                    "exit_risk_days": exit_risk_days,
                    "high_exit_risk_days": high_exit_risk_days,
                    "medium_exit_risk_days": medium_exit_risk_days,
                    "valid_signal_dates": len(selected_dates),
                    "distance_to_ema20_pct": _normalize_float(current_rows[-1]["distance_to_ema20_pct"]),
                }
                for metric_name in TARGET_METRICS:
                    metric_value_num = metric_values[metric_name]
                    if metric_value_num is None:
                        continue
                    metric_rows.append(
                        _build_metric_row(
                            run_row=run_row,
                            window_code=window_code,
                            entity_id=int(coverage_row["entity_id"]),
                            metric_name=metric_name,
                            metric_value_num=metric_value_num,
                            metric_unit=unit_conventions[metric_name],
                            source_run_id=source_run_id,
                        )
                    )
                    metric_name_counts[metric_name] += 1
                    metric_name_counts_by_window[window_code][metric_name] += 1
                    metric_unit_counts[unit_conventions[metric_name]] += 1
                    metric_value_status_counts["OK"] += 1
                    source_run_id_counts[source_run_id] += 1
                if len(metric_rows) == rows_before:
                    source_rows_skipped_by_window[window_code] += 1
                else:
                    source_rows_mapped_by_window[window_code] += 1

        conn.execute("BEGIN")
        rows_deleted_on_replace = 0
        if replace_existing:
            rows_deleted_on_replace = _delete_existing_rows(conn, run_row)
        if metric_rows:
            conn.executemany(
                """
                INSERT INTO eco_entity_metric_value (
                    run_id,
                    ecosystem_id,
                    signal_date,
                    taxonomy_version_id,
                    window_code,
                    entity_id,
                    metric_name,
                    metric_value_num,
                    metric_value_text,
                    metric_unit,
                    value_status,
                    source_run_id
                ) VALUES (
                    :run_id,
                    :ecosystem_id,
                    :signal_date,
                    :taxonomy_version_id,
                    :window_code,
                    :entity_id,
                    :metric_name,
                    :metric_value_num,
                    :metric_value_text,
                    :metric_unit,
                    :value_status,
                    :source_run_id
                )
                """,
                metric_rows,
            )
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "entity_type": TARGET_ENTITY_TYPE,
            "window_codes": list(TARGET_WINDOWS),
            "selected_ticker_entity_count_by_window": selected_ticker_entity_count_by_window,
            "selected_window_dates": selected_window_dates,
            "source_rows_read_by_window": source_rows_read_by_window,
            "source_rows_mapped_by_window": source_rows_mapped_by_window,
            "source_rows_skipped_by_window": source_rows_skipped_by_window,
            "missing_source_tickers_by_window": missing_source_tickers_by_window,
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": dict(metric_name_counts),
            "metric_name_counts_by_window": {
                window_code: dict(window_counts)
                for window_code, window_counts in metric_name_counts_by_window.items()
            },
            "metric_unit_counts": dict(metric_unit_counts),
            "metric_value_status_counts": dict(metric_value_status_counts),
            "source_run_id_counts": dict(source_run_id_counts),
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "mixed_source_run_warning_count": mixed_source_run_warning_count,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": [
                "replaces only ticker rolling-window metrics",
                "source is dc_ticker_swing_signal_daily history plus dc_group_swing_signal_daily valid-date selection",
                "no source_table column exists on eco_entity_metric_value",
                "latest-N valid signal_date semantics are used, not calendar-day semantics",
                "distance_to_ema20_pct is latest-row direct value, not a window average",
                "does not create MISSING metric rows",
                "daily metrics are not modified",
                "freshness metrics are not modified",
                "group metrics are not modified",
                "no signal/relevance/event/classification rows are created",
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
