from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from typing import Any


SOURCE_TABLE_GROUP = "dc_group_swing_signal_daily"
SOURCE_TABLE_SYNTHETIC = "dc_group_synthetic_ohlc_daily"
TARGET_TABLE = "eco_entity_metric_value"
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("rolling2", "rolling5", "rolling30")
WINDOW_DATE_COUNTS = {
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
GROUP_TYPE_BY_ENTITY_TYPE = {
    "LAYER": "layer",
    "SUBINDUSTRY": "subindustry",
}
ENTITY_TYPE_BY_GROUP_TYPE = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
}
GROUP_SWING_METRICS = (
    ("group_timing_state", "group_timing_state", "text"),
    ("group_overheat_risk_level", "overheat_risk_level", "text"),
    ("pct_above_ema20", "pct_above_ema20", "numeric"),
    ("trend_breadth", "trend_breadth", "numeric"),
    ("weakness_breadth", "weakness_breadth", "numeric"),
    ("return_5d", "return_5d", "numeric"),
    ("return_10d", "return_10d", "numeric"),
    ("return_20d", "return_20d", "numeric"),
)
GROUP_SYNTHETIC_METRICS = (
    ("synthetic_close", "synthetic_close", "numeric"),
)
TARGET_METRIC_NAMES = tuple(
    metric_name for metric_name, _, _ in (*GROUP_SWING_METRICS, *GROUP_SYNTHETIC_METRICS)
)
SOURCE_TABLES_USED = (SOURCE_TABLE_GROUP, SOURCE_TABLE_SYNTHETIC)
VALUE_STATUS_OK = "OK"


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


def _load_target_entities(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            e.entity_id,
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
        ORDER BY e.entity_type, e.entity_code, e.entity_name
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
        raise ValueError(
            f"Missing eligible rolling LAYER/SUBINDUSTRY coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _build_target_entity_lookup(
    entity_rows: list[sqlite3.Row],
) -> dict[tuple[str, str], sqlite3.Row]:
    lookup: dict[tuple[str, str], sqlite3.Row] = {}
    duplicates: list[str] = []
    for row in entity_rows:
        entity_type = str(row["entity_type"])
        candidates = {str(row["entity_code"]), str(row["entity_name"])}
        for candidate in candidates:
            key = (entity_type, candidate)
            if key in lookup and int(lookup[key]["entity_id"]) != int(row["entity_id"]):
                duplicates.append(f"{entity_type}:{candidate}")
                continue
            lookup[key] = row
    if duplicates:
        raise ValueError(
            "Ambiguous LAYER/SUBINDUSTRY entity matching candidates: "
            + ", ".join(sorted(set(duplicates)))
        )
    return lookup


def _source_group_pairs(entity_rows: list[sqlite3.Row]) -> dict[str, list[str]]:
    names_by_type: dict[str, set[str]] = defaultdict(set)
    for row in entity_rows:
        group_type = GROUP_TYPE_BY_ENTITY_TYPE[str(row["entity_type"])]
        names_by_type[group_type].add(str(row["entity_code"]))
        names_by_type[group_type].add(str(row["entity_name"]))
    return {group_type: sorted(names) for group_type, names in names_by_type.items()}


def _build_group_filter(
    names_by_group_type: dict[str, list[str]],
) -> tuple[str, list[object]]:
    predicates: list[str] = []
    params: list[object] = []
    for group_type, names in sorted(names_by_group_type.items()):
        if not names:
            continue
        predicates.append(
            f"(group_type = ? AND group_name IN ({', '.join('?' for _ in names)}))"
        )
        params.append(group_type)
        params.extend(names)
    return " OR ".join(predicates), params


def _load_selected_dates_by_window(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> dict[str, list[str]]:
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    required = {"signal_date", "taxonomy_version", "group_type", "group_name"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required columns: {', '.join(missing)}")

    selected_dates_by_window: dict[str, list[str]] = {}
    for window_code, limit in WINDOW_DATE_COUNTS.items():
        rows = conn.execute(
            f"""
            SELECT DISTINCT signal_date
            FROM {SOURCE_TABLE_GROUP}
            WHERE signal_date <= ?
              AND taxonomy_version = ?
              AND group_type IN ('layer', 'subindustry')
            ORDER BY signal_date DESC
            LIMIT ?
            """,
            (signal_date, taxonomy_version_code, limit),
        ).fetchall()
        selected_dates_by_window[window_code] = sorted(str(row["signal_date"]) for row in rows)
    return selected_dates_by_window


def _select_expr(columns: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in columns:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


def _load_group_swing_history_rows(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_code: str,
    selected_dates: list[str],
) -> tuple[list[sqlite3.Row], list[str]]:
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    required = {"signal_date", "taxonomy_version", "group_type", "group_name"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required columns: {', '.join(missing)}")

    skipped_missing_columns: list[str] = []
    available_metric_specs: list[tuple[str, str, str]] = []
    for metric_name, source_column, value_kind in GROUP_SWING_METRICS:
        if source_column in columns:
            available_metric_specs.append((metric_name, source_column, value_kind))
        else:
            skipped_missing_columns.append(metric_name)
    if not selected_dates or not available_metric_specs:
        return [], skipped_missing_columns

    date_placeholders = ", ".join("?" for _ in selected_dates)
    rows = conn.execute(
        f"""
        SELECT
            signal_date,
            group_type,
            group_name,
            {_select_expr(columns, ('run_id', 'signal_version'), 'source_run_id')},
            {', '.join(f'{source_column} AS {metric_name}' for metric_name, source_column, _ in available_metric_specs)}
        FROM {SOURCE_TABLE_GROUP}
        WHERE taxonomy_version = ?
          AND signal_date IN ({date_placeholders})
          AND group_type IN ('layer', 'subindustry')
        ORDER BY signal_date, group_type, group_name
        """,
        (taxonomy_version_code, *selected_dates),
    ).fetchall()
    return rows, skipped_missing_columns


def _load_group_synthetic_history_rows(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_code: str,
    selected_dates: list[str],
) -> tuple[list[sqlite3.Row], list[str]]:
    if not _table_exists(conn, SOURCE_TABLE_SYNTHETIC):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_SYNTHETIC}'")
    columns = _column_names(conn, SOURCE_TABLE_SYNTHETIC)
    required = {"ohlc_date", "taxonomy_version", "group_type", "group_name"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_SYNTHETIC}' missing required columns: {', '.join(missing)}")

    skipped_missing_columns: list[str] = []
    available_metric_specs: list[tuple[str, str, str]] = []
    for metric_name, source_column, value_kind in GROUP_SYNTHETIC_METRICS:
        if source_column in columns:
            available_metric_specs.append((metric_name, source_column, value_kind))
        else:
            skipped_missing_columns.append(metric_name)
    if not selected_dates or not available_metric_specs:
        return [], skipped_missing_columns

    date_placeholders = ", ".join("?" for _ in selected_dates)
    rows = conn.execute(
        f"""
        SELECT
            ohlc_date AS signal_date,
            group_type,
            group_name,
            {_select_expr(columns, ('run_id', 'calc_version', 'signal_version'), 'source_run_id')},
            {', '.join(f'{source_column} AS {metric_name}' for metric_name, source_column, _ in available_metric_specs)}
        FROM {SOURCE_TABLE_SYNTHETIC}
        WHERE taxonomy_version = ?
          AND ohlc_date IN ({date_placeholders})
          AND group_type IN ('layer', 'subindustry')
        ORDER BY ohlc_date, group_type, group_name
        """,
        (taxonomy_version_code, *selected_dates),
    ).fetchall()
    return rows, skipped_missing_columns


def _load_metric_unit_conventions(conn: sqlite3.Connection) -> dict[str, str | None]:
    columns = _column_names(conn, TARGET_TABLE)
    if "metric_unit" not in columns:
        return {metric_name: None for metric_name in TARGET_METRIC_NAMES}
    rows = conn.execute(
        f"""
        SELECT metric_name, metric_unit
        FROM {TARGET_TABLE}
        WHERE metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
        GROUP BY metric_name, metric_unit
        ORDER BY metric_name, metric_unit
        """,
        TARGET_METRIC_NAMES,
    ).fetchall()
    units_by_metric: dict[str, set[str | None]] = {metric_name: set() for metric_name in TARGET_METRIC_NAMES}
    for row in rows:
        units_by_metric[str(row["metric_name"])].add(_normalize_text(row["metric_unit"]))
    return {
        metric_name: next(iter(units)) if len(units) == 1 else None
        for metric_name, units in units_by_metric.items()
    }


def _existing_target_row_count(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    selected_dates_by_window: dict[str, list[str]],
) -> int:
    conditions: list[str] = []
    scope_params: list[object] = [
        str(run_row["run_id"]),
        int(run_row["taxonomy_version_id"]),
    ]
    condition_params: list[object] = []
    for window_code in TARGET_WINDOWS:
        selected_dates = list(selected_dates_by_window.get(window_code) or [])
        if not selected_dates:
            continue
        conditions.append(
            f"(window_code = ? AND signal_date IN ({', '.join('?' for _ in selected_dates)}))"
        )
        condition_params.append(window_code)
        condition_params.extend(selected_dates)
    if not conditions:
        return 0
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {TARGET_TABLE} m
            WHERE m.run_id = ?
              AND m.taxonomy_version_id = ?
              AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
              AND EXISTS (
                SELECT 1
                FROM eco_entity e
                WHERE e.entity_id = m.entity_id
                  AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
              )
              AND ({' OR '.join(conditions)})
            """,
            (
                *scope_params,
                *TARGET_METRIC_NAMES,
                *TARGET_ENTITY_TYPES,
                *condition_params,
            ),
        ).fetchone()[0]
    )


def _delete_existing_rows(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    selected_dates_by_window: dict[str, list[str]],
) -> int:
    conditions: list[str] = []
    scope_params: list[object] = [
        str(run_row["run_id"]),
        int(run_row["taxonomy_version_id"]),
    ]
    condition_params: list[object] = []
    for window_code in TARGET_WINDOWS:
        selected_dates = list(selected_dates_by_window.get(window_code) or [])
        if not selected_dates:
            continue
        conditions.append(
            f"(window_code = ? AND signal_date IN ({', '.join('?' for _ in selected_dates)}))"
        )
        condition_params.append(window_code)
        condition_params.extend(selected_dates)
    if not conditions:
        return 0
    cursor = conn.execute(
        f"""
        DELETE FROM {TARGET_TABLE}
        WHERE run_id = ?
          AND taxonomy_version_id = ?
          AND metric_name IN ({", ".join("?" for _ in TARGET_METRIC_NAMES)})
          AND EXISTS (
            SELECT 1
            FROM eco_entity e
            WHERE e.entity_id = {TARGET_TABLE}.entity_id
              AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
          )
          AND ({' OR '.join(conditions)})
        """,
        (
            *scope_params,
            *TARGET_METRIC_NAMES,
            *TARGET_ENTITY_TYPES,
            *condition_params,
        ),
    )
    return int(cursor.rowcount)


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    signal_date: str,
    entity_id: int,
    metric_name: str,
    value_kind: str,
    source_value: object,
    source_run_id: str | None,
    metric_unit_by_name: dict[str, str | None],
) -> dict[str, object] | None:
    if value_kind == "numeric":
        metric_value_num = _normalize_float(source_value)
        if metric_value_num is None:
            return None
        metric_value_text = None
    else:
        metric_value_text = _normalize_text(source_value)
        if metric_value_text is None:
            return None
        metric_value_num = None
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": signal_date,
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": metric_value_num,
        "metric_value_text": metric_value_text,
        "metric_unit": metric_unit_by_name.get(metric_name),
        "value_status": VALUE_STATUS_OK,
        "source_run_id": source_run_id,
    }


def _insert_metric_rows(conn: sqlite3.Connection, metric_rows: list[dict[str, object]]) -> int:
    if not metric_rows:
        return 0
    conn.executemany(
        f"""
        INSERT INTO {TARGET_TABLE} (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (
            :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code, :entity_id,
            :metric_name, :metric_value_num, :metric_value_text, :metric_unit, :value_status, :source_run_id
        )
        """,
        metric_rows,
    )
    return len(metric_rows)


def build_canonical_v3_group_historical_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        entity_rows = _load_target_entities(conn, run_row)
        entity_lookup = _build_target_entity_lookup(entity_rows)
        selected_dates_by_window = _load_selected_dates_by_window(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )
        existing_rows = _existing_target_row_count(conn, run_row, selected_dates_by_window)
        if existing_rows and not replace_existing:
            raise ValueError(
                f"Found {existing_rows} existing target metric rows for run_id '{run_id}' and replace_existing=False"
            )

        all_selected_dates = sorted(
            {signal_date for dates in selected_dates_by_window.values() for signal_date in dates}
        )
        swing_rows, skipped_group_metrics = _load_group_swing_history_rows(
            conn,
            taxonomy_version_code=str(run_row["version_code"]),
            selected_dates=all_selected_dates,
        )
        synthetic_rows, skipped_synthetic_metrics = _load_group_synthetic_history_rows(
            conn,
            taxonomy_version_code=str(run_row["version_code"]),
            selected_dates=all_selected_dates,
        )
        if not swing_rows and not synthetic_rows:
            return {
                "run_id": str(run_row["run_id"]),
                "target_signal_date": str(run_row["signal_date"]),
                "windows": list(TARGET_WINDOWS),
                "selected_dates_by_window": selected_dates_by_window,
                "inserted_rows": 0,
                "deleted_rows": 0,
                "skipped_missing_source_columns": sorted(set(skipped_group_metrics + skipped_synthetic_metrics)),
                "unresolved_group_rows": 0,
                "source_tables_used": list(SOURCE_TABLES_USED),
                "status": "NO_SOURCE_ROWS",
            }

        metric_unit_by_name = _load_metric_unit_conventions(conn)
        if replace_existing:
            deleted_rows = _delete_existing_rows(conn, run_row, selected_dates_by_window)
        else:
            deleted_rows = 0

        metric_rows: list[dict[str, object]] = []
        unresolved_group_rows = 0
        source_rows_by_table = {
            SOURCE_TABLE_GROUP: swing_rows,
            SOURCE_TABLE_SYNTHETIC: synthetic_rows,
        }
        metric_specs_by_table = {
            SOURCE_TABLE_GROUP: GROUP_SWING_METRICS,
            SOURCE_TABLE_SYNTHETIC: GROUP_SYNTHETIC_METRICS,
        }

        for window_code in TARGET_WINDOWS:
            selected_dates = set(selected_dates_by_window.get(window_code) or [])
            for source_table, source_rows in source_rows_by_table.items():
                metric_specs = metric_specs_by_table[source_table]
                for row in source_rows:
                    signal_date = str(row["signal_date"])
                    if signal_date not in selected_dates:
                        continue
                    group_type = _normalize_text(row["group_type"])
                    group_name = _normalize_text(row["group_name"])
                    entity_type = ENTITY_TYPE_BY_GROUP_TYPE.get(group_type or "")
                    if entity_type is None or group_name is None:
                        unresolved_group_rows += 1
                        continue
                    entity_row = entity_lookup.get((entity_type, group_name))
                    if entity_row is None:
                        unresolved_group_rows += 1
                        continue
                    for metric_name, source_column, value_kind in metric_specs:
                        if source_column not in row.keys():
                            continue
                        metric_row = _build_metric_row(
                            run_row=run_row,
                            window_code=window_code,
                            signal_date=signal_date,
                            entity_id=int(entity_row["entity_id"]),
                            metric_name=metric_name,
                            value_kind=value_kind,
                            source_value=row[source_column],
                            source_run_id=_normalize_text(row["source_run_id"]),
                            metric_unit_by_name=metric_unit_by_name,
                        )
                        if metric_row is not None:
                            metric_rows.append(metric_row)

        inserted_rows = _insert_metric_rows(conn, metric_rows)
        conn.commit()

        skipped_metrics = sorted(set(skipped_group_metrics + skipped_synthetic_metrics))
        status = "OK"
        if skipped_metrics or unresolved_group_rows:
            status = "OK_WITH_WARNINGS"
        return {
            "run_id": str(run_row["run_id"]),
            "target_signal_date": str(run_row["signal_date"]),
            "windows": list(TARGET_WINDOWS),
            "selected_dates_by_window": selected_dates_by_window,
            "inserted_rows": inserted_rows,
            "deleted_rows": deleted_rows,
            "skipped_missing_source_columns": skipped_metrics,
            "unresolved_group_rows": unresolved_group_rows,
            "source_tables_used": list(SOURCE_TABLES_USED),
            "status": status,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
