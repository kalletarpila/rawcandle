from __future__ import annotations

import sqlite3
from collections import Counter


GROUP_CONTEXT_SOURCE_TABLE = "dc_report_context_group_v2"
WINDOW_CONTEXT_SOURCE_TABLE = "dc_report_context_window_v2"
GROUP_SWING_SOURCE_TABLE = "dc_group_swing_signal_daily"
SOURCE_CLASSIFICATIONS = {
    GROUP_CONTEXT_SOURCE_TABLE: "TRANSITIONAL_V2_SOURCE",
    WINDOW_CONTEXT_SOURCE_TABLE: "TRANSITIONAL_V2_SOURCE",
    GROUP_SWING_SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
GROUP_TYPE_TO_ENTITY_TYPE = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
}
BUILDER_OWNED_METRICS = (
    "group_overheat_risk_level",
    "group_current_status",
    "group_window_status",
    "group_status_change",
    "group_timing_state",
    "group_timing_reason",
    "group_overheat_flag",
    "layer_overheat_risk_level",
    "subindustry_overheat_risk_level",
)
METRIC_SPECS = (
    ("overheat_risk_level", "group_overheat_risk_level", "text"),
    ("group_current_status", "group_current_status", "text"),
    ("group_window_status", "group_window_status", "text"),
    ("group_status_change", "group_status_change", "text"),
    ("timing_state", "group_timing_state", "text"),
    ("timing_reason", "group_timing_reason", "text"),
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_one(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> sqlite3.Row | None:
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


def _select_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in column_names:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


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
            e.entity_type,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
        ORDER BY e.entity_type, e.entity_name, c.window_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
        ),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eligible LAYER/SUBINDUSTRY coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _load_group_context_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, GROUP_CONTEXT_SOURCE_TABLE):
        raise ValueError(f"Missing source table '{GROUP_CONTEXT_SOURCE_TABLE}'")
    columns = _column_names(conn, GROUP_CONTEXT_SOURCE_TABLE)
    required = {"signal_date", "taxonomy_version", "horizon", "group_type", "group_name", "run_id"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            f"Source table '{GROUP_CONTEXT_SOURCE_TABLE}' missing required columns: {', '.join(missing)}"
        )
    query = f"""
        SELECT
            horizon,
            group_type,
            group_name,
            {_select_expr(columns, ('timing_state',), 'timing_state')},
            {_select_expr(columns, ('timing_reason',), 'timing_reason')},
            {_select_expr(columns, ('overheat_risk_level',), 'overheat_risk_level')},
            {_select_expr(columns, ('group_current_status',), 'group_current_status')},
            {_select_expr(columns, ('group_window_status',), 'group_window_status')},
            {_select_expr(columns, ('group_status_change',), 'group_status_change')},
            {_select_expr(columns, ('run_id',), 'source_run_id')}
        FROM {GROUP_CONTEXT_SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND group_type IN ('layer', 'subindustry')
          AND horizon IN ('daily', 'rolling2', 'rolling5', 'rolling30')
        ORDER BY group_type, group_name, horizon
    """
    return conn.execute(query, (signal_date, taxonomy_version_code)).fetchall()


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    metric_name: str,
    metric_kind: str,
    source_value: object,
    source_run_id: object,
) -> dict[str, object] | None:
    if metric_kind == "numeric":
        if source_value is None or source_value == "":
            return None
        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_id": int(run_row["ecosystem_id"]),
            "signal_date": str(run_row["signal_date"]),
            "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
            "window_code": str(coverage_row["window_code"]),
            "entity_id": int(coverage_row["entity_id"]),
            "metric_name": metric_name,
            "metric_value_num": float(source_value),
            "metric_value_text": None,
            "metric_unit": None,
            "value_status": "OK",
            "source_run_id": _normalize_text(source_run_id),
        }
    value_text = _normalize_text(source_value)
    if value_text is None:
        return None
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": str(coverage_row["window_code"]),
        "entity_id": int(coverage_row["entity_id"]),
        "metric_name": metric_name,
        "metric_value_num": None,
        "metric_value_text": value_text,
        "metric_unit": None,
        "value_status": "OK",
        "source_run_id": _normalize_text(source_run_id),
    }


def _build_rows_from_group_context(
    *,
    run_row: sqlite3.Row,
    source_rows: list[sqlite3.Row],
    coverage_map: dict[tuple[str, str, str], sqlite3.Row],
    warnings: list[str],
) -> tuple[list[dict[str, object]], int, int]:
    metric_rows: list[dict[str, object]] = []
    mapped_count = 0
    skipped_count = 0

    for source_row in source_rows:
        group_type = _normalize_text(source_row["group_type"])
        group_name = _normalize_text(source_row["group_name"])
        horizon = _normalize_text(source_row["horizon"])
        if group_type is None or group_name is None or horizon is None:
            warnings.append(
                "Skipped dc_report_context_group_v2 row with missing group_type/group_name/horizon"
            )
            skipped_count += 1
            continue
        entity_type = GROUP_TYPE_TO_ENTITY_TYPE.get(group_type.lower())
        if entity_type is None:
            warnings.append(
                f"Skipped dc_report_context_group_v2 row with unsupported group_type '{group_type}'"
            )
            skipped_count += 1
            continue
        coverage_row = coverage_map.get((horizon, entity_type, group_name))
        if coverage_row is None:
            warnings.append(
                "Skipped dc_report_context_group_v2 row without eligible coverage: "
                f"{group_type}/{group_name}/{horizon}"
            )
            skipped_count += 1
            continue

        mapped_count += 1
        for source_column, metric_name, metric_kind in METRIC_SPECS:
            metric_row = _build_metric_row(
                run_row=run_row,
                coverage_row=coverage_row,
                metric_name=metric_name,
                metric_kind=metric_kind,
                source_value=source_row[source_column],
                source_run_id=source_row["source_run_id"],
            )
            if metric_row is not None:
                metric_rows.append(metric_row)

    return metric_rows, mapped_count, skipped_count


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> None:
    placeholders = ", ".join("?" for _ in BUILDER_OWNED_METRICS)
    existing_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND metric_name IN ({placeholders})
        """,
        (run_id, *BUILDER_OWNED_METRICS),
    ).fetchone()[0]
    if existing_count and not replace_existing:
        raise ValueError(f"Group status builder-owned rows already exist for run_id '{run_id}'")
    if existing_count and replace_existing:
        conn.execute(
            f"""
            DELETE FROM eco_entity_metric_value
            WHERE run_id = ?
              AND metric_name IN ({placeholders})
            """,
            (run_id, *BUILDER_OWNED_METRICS),
        )


def build_canonical_v3_group_status_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        coverage_map: dict[tuple[str, str, str], sqlite3.Row] = {}
        selected_entity_ids: set[int] = set()
        selected_windows: set[str] = set()
        for row in coverage_rows:
            coverage_map[(str(row["window_code"]), str(row["entity_type"]), str(row["entity_name"]))] = row
            selected_entity_ids.add(int(row["entity_id"]))
            selected_windows.add(str(row["window_code"]))

        warnings: list[str] = []
        limitations = [
            "dc_report_context_group_v2 and dc_report_context_window_v2 are TRANSITIONAL_V2_SOURCE",
            "no overheat transition events are created",
            "no group rotation events are created",
            "empty progression/relative-change support tables were not used",
            "metric source_table lineage is not available if eco_entity_metric_value lacks source_table column",
            "dc_report_context_window_v2 and dc_group_swing_signal_daily were not used because dc_report_context_group_v2 provided sufficient group/window snapshot semantics",
        ]

        group_context_rows = _load_group_context_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )

        metric_rows, mapped_count, skipped_count = _build_rows_from_group_context(
            run_row=run_row,
            source_rows=group_context_rows,
            coverage_map=coverage_map,
            warnings=warnings,
        )
        metric_name_counts = dict(sorted(Counter(row["metric_name"] for row in metric_rows).items()))

        conn.execute("BEGIN")
        _ensure_replace_allowed(conn, run_id=str(run_row["run_id"]), replace_existing=replace_existing)
        conn.executemany(
            """
            INSERT INTO eco_entity_metric_value (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
            ) VALUES (
                :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code, :entity_id,
                :metric_name, :metric_value_num, :metric_value_text, :metric_unit, :value_status, :source_run_id
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
            "source_classifications": dict(SOURCE_CLASSIFICATIONS),
            "selected_group_entity_count": len(selected_entity_ids),
            "window_count": len(selected_windows),
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": metric_name_counts,
            "source_rows_read_by_table": {
                GROUP_CONTEXT_SOURCE_TABLE: len(group_context_rows),
                WINDOW_CONTEXT_SOURCE_TABLE: 0,
                GROUP_SWING_SOURCE_TABLE: 0,
            },
            "source_rows_mapped_by_table": {
                GROUP_CONTEXT_SOURCE_TABLE: mapped_count,
                WINDOW_CONTEXT_SOURCE_TABLE: 0,
                GROUP_SWING_SOURCE_TABLE: 0,
            },
            "source_rows_skipped": skipped_count,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": limitations,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
