from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE = "dc_ticker_swing_signal_daily"
TARGET_ENTITY_TYPE = "TICKER"
WINDOW_CODE = "daily"
TARGET_METRICS = (
    ("distance_to_ema10_pct", "distance_to_ema10_pct"),
    ("distance_to_ema20_pct", "distance_to_ema20_pct"),
    ("return_5d", "return_5d"),
    ("return_10d", "return_10d"),
    ("return_20d", "return_20d"),
    ("return_60d", "return_60d"),
    ("latest_bos_age_trading_days", "latest_bos_age_trading_days"),
    ("latest_reset_age_trading_days", "latest_reset_age_trading_days"),
    ("latest_structure_age_trading_days", "latest_structure_age_trading_days"),
)
TARGET_METRIC_NAMES = tuple(metric_name for metric_name, _ in TARGET_METRICS)


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
        """
        SELECT
            c.run_id,
            c.ecosystem_id,
            c.signal_date,
            c.taxonomy_version_id,
            c.window_code,
            c.entity_id,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code = ?
          AND e.entity_type = ?
        ORDER BY e.entity_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            WINDOW_CODE,
            TARGET_ENTITY_TYPE,
        ),
    ).fetchall()
    if not rows:
        raise ValueError(
            f"Missing eligible {TARGET_ENTITY_TYPE} {WINDOW_CODE} coverage rows for run_id '{run_row['run_id']}'"
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
          AND m.window_code = ?
          AND e.entity_type = ?
          AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
        GROUP BY m.metric_name, m.metric_unit
        ORDER BY m.metric_name, m.metric_unit
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            WINDOW_CODE,
            TARGET_ENTITY_TYPE,
            *TARGET_METRIC_NAMES,
        ),
    ).fetchall()
    units_by_metric: dict[str, set[str | None]] = {metric_name: set() for metric_name in TARGET_METRIC_NAMES}
    for row in rows:
        units_by_metric[str(row["metric_name"])].add(_normalize_text(row["metric_unit"]))
    conventions: dict[str, str | None] = {}
    for metric_name, units in units_by_metric.items():
        if len(units) > 1:
            raise ValueError(f"Multiple metric_unit conventions found for metric '{metric_name}'")
        conventions[metric_name] = next(iter(units)) if units else None
    return conventions


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_tickers: list[str],
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    columns = _column_names(conn, SOURCE_TABLE)
    required = {
        "ticker",
        "signal_date",
        "taxonomy_version",
        "distance_to_ema10_pct",
        "distance_to_ema20_pct",
        "return_5d",
        "return_10d",
        "return_20d",
        "return_60d",
        "latest_bos_age_trading_days",
        "latest_reset_age_trading_days",
        "latest_structure_age_trading_days",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing)}")
    source_run_expr = "run_id AS source_run_id" if "run_id" in columns else "signal_version AS source_run_id"
    if "run_id" not in columns and "signal_version" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing both run_id and signal_version")
    ticker_clause = ", ".join("?" for _ in eligible_tickers)
    rows = conn.execute(
        f"""
        SELECT
            ticker,
            signal_date,
            taxonomy_version,
            distance_to_ema10_pct,
            distance_to_ema20_pct,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            latest_bos_age_trading_days,
            latest_reset_age_trading_days,
            latest_structure_age_trading_days,
            {source_run_expr}
        FROM {SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND ticker IN ({ticker_clause})
        ORDER BY ticker
        """,
        (signal_date, taxonomy_version_code, *eligible_tickers),
    ).fetchall()
    return rows


def _existing_target_row_count(conn: sqlite3.Connection, run_row: sqlite3.Row, entity_ids: list[int]) -> int:
    if not entity_ids:
        return 0
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND signal_date = ?
              AND taxonomy_version_id = ?
              AND window_code = ?
              AND entity_id IN ({", ".join("?" for _ in entity_ids)})
              AND metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                WINDOW_CODE,
                *entity_ids,
                *TARGET_METRIC_NAMES,
            ),
        ).fetchone()[0]
    )


def _delete_existing_rows(conn: sqlite3.Connection, run_row: sqlite3.Row, entity_ids: list[int]) -> int:
    if not entity_ids:
        return 0
    cursor = conn.execute(
        f"""
        DELETE FROM eco_entity_metric_value
        WHERE run_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
          AND window_code = ?
          AND entity_id IN ({", ".join("?" for _ in entity_ids)})
          AND metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            WINDOW_CODE,
            *entity_ids,
            *TARGET_METRIC_NAMES,
        ),
    )
    return int(cursor.rowcount)


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    entity_id: int,
    metric_name: str,
    metric_value_num: float,
    metric_unit: str | None,
    source_run_id: str | None,
) -> dict[str, object]:
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": WINDOW_CODE,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": metric_value_num,
        "metric_value_text": None,
        "metric_unit": metric_unit,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def build_canonical_v3_ticker_daily_direct_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        unit_conventions = _load_metric_unit_conventions(conn, run_row)
        ticker_to_coverage = {str(row["entity_code"]): row for row in coverage_rows}
        eligible_tickers = sorted(ticker_to_coverage)
        entity_ids = [int(row["entity_id"]) for row in coverage_rows]

        source_rows = _load_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_tickers=eligible_tickers,
        )
        source_by_ticker = {str(row["ticker"]): row for row in source_rows}

        existing_rows = _existing_target_row_count(conn, run_row, entity_ids)
        if existing_rows and not replace_existing:
            raise ValueError(
                f"Found {existing_rows} existing target metric rows for run_id '{run_id}' and replace_existing=False"
            )

        metric_rows: list[dict[str, object]] = []
        metric_name_counts: Counter[str] = Counter()
        metric_unit_counts: Counter[str | None] = Counter()
        metric_value_status_counts: Counter[str] = Counter()
        source_run_id_counts: Counter[str | None] = Counter()
        missing_source_tickers: list[str] = []
        warnings: list[str] = []
        source_rows_mapped = 0
        source_rows_skipped = 0

        for ticker in eligible_tickers:
            coverage_row = ticker_to_coverage[ticker]
            source_row = source_by_ticker.get(ticker)
            if source_row is None:
                missing_source_tickers.append(ticker)
                warnings.append(f"Missing lower-level ticker row for daily ticker '{ticker}'")
                continue
            source_run_id = _normalize_text(source_row["source_run_id"])
            rows_before = len(metric_rows)
            for metric_name, source_column in TARGET_METRICS:
                metric_value_num = _normalize_float(source_row[source_column])
                if metric_value_num is None:
                    continue
                metric_unit = unit_conventions[metric_name]
                metric_rows.append(
                    _build_metric_row(
                        run_row=run_row,
                        entity_id=int(coverage_row["entity_id"]),
                        metric_name=metric_name,
                        metric_value_num=metric_value_num,
                        metric_unit=metric_unit,
                        source_run_id=source_run_id,
                    )
                )
                metric_name_counts[metric_name] += 1
                metric_unit_counts[metric_unit] += 1
                metric_value_status_counts["OK"] += 1
                source_run_id_counts[source_run_id] += 1
            if len(metric_rows) == rows_before:
                source_rows_skipped += 1
            else:
                source_rows_mapped += 1

        conn.execute("BEGIN")
        rows_deleted_on_replace = 0
        if replace_existing:
            rows_deleted_on_replace = _delete_existing_rows(conn, run_row, entity_ids)
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
            "window_code": WINDOW_CODE,
            "selected_ticker_entity_count": len(coverage_rows),
            "source_rows_read": len(source_rows),
            "source_rows_mapped": source_rows_mapped,
            "source_rows_skipped": source_rows_skipped,
            "missing_source_tickers": missing_source_tickers,
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": dict(metric_name_counts),
            "metric_unit_counts": dict(metric_unit_counts),
            "metric_value_status_counts": dict(metric_value_status_counts),
            "source_run_id_counts": dict(source_run_id_counts),
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": [
                "replaces only ticker daily direct metrics",
                "source is dc_ticker_swing_signal_daily",
                "no source_table column exists on eco_entity_metric_value",
                "does not create MISSING metric rows",
                "freshness metrics are not modified",
                "rolling/window metrics are not modified",
                "group metrics are not modified",
                "no signal/relevance/event/classification rows are created",
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
