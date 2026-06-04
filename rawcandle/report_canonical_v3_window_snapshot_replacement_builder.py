from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict


TARGET_TABLE = "eco_entity_window_snapshot"
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
TARGET_ENTITY_TYPES = ("ECOSYSTEM", "LAYER", "SUBINDUSTRY", "TICKER")
REPLACEMENT_SOURCE_PREFIX = "V3_WINDOW_SNAPSHOT_FROM_ECO_COVERAGE"
V2_SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"

GROUP_TIMING_METRIC = "group_timing_state"
GROUP_WINDOW_METRIC = "group_window_status"
GROUP_PCT_ABOVE_EMA20_METRIC = "pct_above_ema20"
GROUP_FRESHNESS_METRIC = "freshness_latest_structure_class"
TICKER_DISTANCE_EMA20_METRIC = "distance_to_ema20_pct"

CLASSIFICATION_TYPE_BY_WINDOW = {
    "daily": "daily_trigger",
    "rolling2": "rolling2_sell_pressure",
    "rolling5": "rolling5_pullback",
}


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


def _column_names(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


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
            c.coverage_status,
            e.entity_type,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
        ORDER BY e.entity_type, e.entity_name, c.window_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            *TARGET_WINDOWS,
            *TARGET_ENTITY_TYPES,
        ),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eligible coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _load_quality_rows(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT window_code, quality_scope, quality_status
        FROM eco_quality_summary
        WHERE run_id = ?
          AND ecosystem_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
        """,
        (
            str(run_row["run_id"]),
            int(run_row["ecosystem_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
        ),
    ).fetchall()


def _load_classifications(conn: sqlite3.Connection, run_row: sqlite3.Row) -> dict[tuple[int, str, str], str]:
    rows = conn.execute(
        """
        SELECT entity_id, window_code, classification_type, classification_state
        FROM eco_classification_decision
        WHERE run_id = ?
          AND ecosystem_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
        """,
        (
            str(run_row["run_id"]),
            int(run_row["ecosystem_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
        ),
    ).fetchall()
    return {
        (int(row["entity_id"]), str(row["window_code"]), str(row["classification_type"])): str(row["classification_state"])
        for row in rows
    }


def _load_metrics(conn: sqlite3.Connection, run_row: sqlite3.Row) -> dict[tuple[int, str, str], sqlite3.Row]:
    metric_names = (
        GROUP_TIMING_METRIC,
        GROUP_WINDOW_METRIC,
        GROUP_PCT_ABOVE_EMA20_METRIC,
        GROUP_FRESHNESS_METRIC,
        TICKER_DISTANCE_EMA20_METRIC,
    )
    rows = conn.execute(
        f"""
        SELECT entity_id, window_code, metric_name, metric_value_num, metric_value_text
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND ecosystem_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
          AND window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND metric_name IN ({", ".join("?" for _ in metric_names)})
        """,
        (
            str(run_row["run_id"]),
            int(run_row["ecosystem_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_WINDOWS,
            *metric_names,
        ),
    ).fetchall()
    return {(int(row["entity_id"]), str(row["window_code"]), str(row["metric_name"])): row for row in rows}


def _existing_target_row_count(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_window_snapshot
            WHERE run_id = ?
              AND ecosystem_id = ?
              AND signal_date = ?
              AND taxonomy_version_id = ?
            """,
            (
                str(run_row["run_id"]),
                int(run_row["ecosystem_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
            ),
        ).fetchone()[0]
    )


def _delete_existing_rows(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    cursor = conn.execute(
        """
        DELETE FROM eco_entity_window_snapshot
        WHERE run_id = ?
          AND ecosystem_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
        """,
        (
            str(run_row["run_id"]),
            int(run_row["ecosystem_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
        ),
    )
    return int(cursor.rowcount)


def _count_existing_lineage(conn: sqlite3.Connection, run_row: sqlite3.Row) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN source_run_id = ? THEN 1 ELSE 0 END) AS v2_rows,
            SUM(CASE WHEN source_run_id IS NULL THEN 1 ELSE 0 END) AS null_rows
        FROM eco_entity_window_snapshot
        WHERE run_id = ?
          AND ecosystem_id = ?
          AND signal_date = ?
          AND taxonomy_version_id = ?
        """,
        (
            V2_SOURCE_RUN_ID,
            str(run_row["run_id"]),
            int(run_row["ecosystem_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
        ),
    ).fetchone()
    return int(row["v2_rows"] or 0), int(row["null_rows"] or 0)


def _derive_group_trend_state(pct_above_ema20: float | None) -> str | None:
    if pct_above_ema20 is None:
        return None
    if pct_above_ema20 >= 80.0:
        return "UP"
    if pct_above_ema20 <= 20.0:
        return "DOWN"
    return "NEUTRAL"


def _derive_ticker_trend_state(
    rolling30_buy_state: str | None,
    distance_to_ema20_pct: float | None,
) -> str | None:
    if rolling30_buy_state in {"BUY_ZONE", "WATCH_ZONE"}:
        return "UP"
    if rolling30_buy_state == "AVOID":
        if distance_to_ema20_pct is not None and distance_to_ema20_pct <= -0.05:
            return "DOWN"
        return "NEUTRAL"
    if rolling30_buy_state == "INSUFFICIENT_DATA":
        return None
    return None


def _derive_statuses(
    *,
    entity_type: str,
    coverage_status: str,
    window_code: str,
    quality_statuses_by_window: dict[str, set[str]],
) -> tuple[str, str]:
    if entity_type == "ECOSYSTEM":
        statuses = quality_statuses_by_window.get(window_code, set())
        if any(status != "OK" for status in statuses):
            return "WARN", "WARN"
        return "OK", "OK"
    if coverage_status == "OK":
        return "OK", "OK"
    return "WARN", "WARN"


def _build_snapshot_row(
    *,
    snapshot_columns: list[str],
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    replacement_source_run_id: str,
    quality_statuses_by_window: dict[str, set[str]],
    classifications: dict[tuple[int, str, str], str],
    metrics: dict[tuple[int, str, str], sqlite3.Row],
) -> dict[str, object]:
    entity_type = str(coverage_row["entity_type"])
    window_code = str(coverage_row["window_code"])
    entity_id = int(coverage_row["entity_id"])
    coverage_status = str(coverage_row["coverage_status"])

    snapshot_status, quality_status = _derive_statuses(
        entity_type=entity_type,
        coverage_status=coverage_status,
        window_code=window_code,
        quality_statuses_by_window=quality_statuses_by_window,
    )

    timing_state: str | None = None
    trend_state: str | None = None
    summary_state: str | None = None
    classification_state: str | None = None
    freshness_status: str | None = None

    if snapshot_status == "OK":
        if entity_type in {"LAYER", "SUBINDUSTRY"}:
            timing_metric_row = metrics.get((entity_id, window_code, GROUP_TIMING_METRIC))
            timing_state = _normalize_text(timing_metric_row["metric_value_text"]) if timing_metric_row else None
            if window_code == "daily":
                summary_state = timing_state
            else:
                summary_metric_row = metrics.get((entity_id, window_code, GROUP_WINDOW_METRIC))
                summary_state = _normalize_text(summary_metric_row["metric_value_text"]) if summary_metric_row else timing_state
            pct_metric_row = metrics.get((entity_id, window_code, GROUP_PCT_ABOVE_EMA20_METRIC))
            pct_above_ema20 = _normalize_float(pct_metric_row["metric_value_num"]) if pct_metric_row else None
            trend_state = _derive_group_trend_state(pct_above_ema20)
            freshness_metric_row = metrics.get((entity_id, window_code, GROUP_FRESHNESS_METRIC))
            freshness_status = _normalize_text(freshness_metric_row["metric_value_text"]) if freshness_metric_row else None
        elif entity_type == "TICKER":
            classification_type = CLASSIFICATION_TYPE_BY_WINDOW.get(window_code)
            if classification_type is not None:
                classification_state = classifications.get((entity_id, window_code, classification_type))
            summary_state = "OK"
            rolling30_buy_state = classifications.get((entity_id, "rolling30", "rolling30_buy"))
            distance_metric_row = metrics.get((entity_id, window_code, TICKER_DISTANCE_EMA20_METRIC))
            distance_to_ema20_pct = _normalize_float(distance_metric_row["metric_value_num"]) if distance_metric_row else None
            trend_state = _derive_ticker_trend_state(rolling30_buy_state, distance_to_ema20_pct)

    row: dict[str, object] = {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "snapshot_status": snapshot_status,
        "timing_state": timing_state,
        "trend_state": trend_state,
        "summary_state": summary_state,
        "classification_state": classification_state,
        "freshness_status": freshness_status,
        "quality_status": quality_status,
        "asof_observed_at": str(run_row["signal_date"]),
        "source_run_id": replacement_source_run_id,
    }
    return {column: row.get(column) for column in snapshot_columns if column in row}


def build_canonical_v3_window_snapshots(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, TARGET_TABLE):
            raise ValueError(f"Missing target table '{TARGET_TABLE}'")

        run_row = _resolve_run(conn, run_id)
        snapshot_columns = _column_names(conn, TARGET_TABLE)
        required_columns = {
            "run_id",
            "ecosystem_id",
            "signal_date",
            "taxonomy_version_id",
            "window_code",
            "entity_id",
            "snapshot_status",
            "quality_status",
            "asof_observed_at",
            "source_run_id",
        }
        missing_columns = sorted(required_columns - set(snapshot_columns))
        if missing_columns:
            raise ValueError(
                f"Target table '{TARGET_TABLE}' missing required columns: {', '.join(missing_columns)}"
            )

        coverage_rows = _load_target_coverage(conn, run_row)
        quality_rows = _load_quality_rows(conn, run_row)
        classifications = _load_classifications(conn, run_row)
        metrics = _load_metrics(conn, run_row)
        existing_rows = _existing_target_row_count(conn, run_row)
        if existing_rows and not replace_existing:
            raise ValueError(
                f"Found {existing_rows} existing target snapshot rows for run_id '{run_id}' and replace_existing=False"
            )

        old_v2_lineage_rows_removed, old_null_lineage_rows_replaced = _count_existing_lineage(conn, run_row)
        replacement_source_run_id = (
            f"{REPLACEMENT_SOURCE_PREFIX}_{str(run_row['signal_date']).replace('-', '_')}"
        )

        quality_statuses_by_window: dict[str, set[str]] = defaultdict(set)
        for row in quality_rows:
            quality_statuses_by_window[str(row["window_code"])].add(str(row["quality_status"]))

        snapshot_rows: list[dict[str, object]] = []
        rows_by_entity_type: Counter[str] = Counter()
        rows_by_window_code: Counter[str] = Counter()
        snapshot_status_counts: Counter[str] = Counter()
        quality_status_counts: Counter[str] = Counter()
        source_run_id_counts: Counter[str] = Counter()
        warnings: list[str] = []

        for coverage_row in coverage_rows:
            snapshot_row = _build_snapshot_row(
                snapshot_columns=snapshot_columns,
                run_row=run_row,
                coverage_row=coverage_row,
                replacement_source_run_id=replacement_source_run_id,
                quality_statuses_by_window=quality_statuses_by_window,
                classifications=classifications,
                metrics=metrics,
            )
            snapshot_rows.append(snapshot_row)
            entity_type = str(coverage_row["entity_type"])
            window_code = str(coverage_row["window_code"])
            rows_by_entity_type[entity_type] += 1
            rows_by_window_code[window_code] += 1
            snapshot_status_counts[str(snapshot_row["snapshot_status"])] += 1
            quality_status_counts[str(snapshot_row["quality_status"])] += 1
            source_run_id_counts[str(snapshot_row["source_run_id"])] += 1

        conn.execute("BEGIN")
        rows_deleted_on_replace = 0
        if replace_existing:
            rows_deleted_on_replace = _delete_existing_rows(conn, run_row)
        if snapshot_rows:
            insert_columns = [column for column in snapshot_columns if column in snapshot_rows[0]]
            conn.executemany(
                f"""
                INSERT INTO {TARGET_TABLE} (
                    {", ".join(insert_columns)}
                ) VALUES (
                    {", ".join(f':{column}' for column in insert_columns)}
                )
                """,
                snapshot_rows,
            )
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "source_dependency_summary": {
                "eco_entity_coverage": "V3_BASE_CONTROL_FACT",
                "eco_quality_summary": "V3_BASE_CONTROL_FACT",
                "eco_entity_metric_value": "V3_NATIVE_OPTIONAL_DERIVED_FACT",
                "eco_classification_decision": "V3_NATIVE_OPTIONAL_DERIVED_FACT",
                "runtime_excludes": [
                    "dc_report_context_daily_v2",
                    "dc_report_context_window_v2",
                    "dc_report_context_group_v2",
                    "dc_report_classification_v2",
                ],
            },
            "replacement_source_run_id": replacement_source_run_id,
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "snapshot_rows_inserted": len(snapshot_rows),
            "rows_by_entity_type": dict(rows_by_entity_type),
            "rows_by_window_code": dict(rows_by_window_code),
            "snapshot_status_counts": dict(snapshot_status_counts),
            "quality_status_counts": dict(quality_status_counts),
            "old_v2_lineage_rows_removed": old_v2_lineage_rows_removed,
            "old_null_lineage_rows_replaced": old_null_lineage_rows_replaced,
            "source_run_id_counts": dict(source_run_id_counts),
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": [
                "replaces only eco_entity_window_snapshot for one V3 run",
                "source is eco_entity_coverage / V3 base control facts",
                "does not use dc_report_context_*_v2 or dc_report_classification_v2",
                "does not modify metrics/signals/events/classifications/coverage/quality/run rows",
                "snapshot semantics are coverage-derived unless schema inspection proves otherwise",
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
