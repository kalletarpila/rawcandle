from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE_GROUP = "dc_group_swing_signal_daily"
SOURCE_TABLE_SYNTHETIC = "dc_group_synthetic_ohlc_daily"
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
WINDOW_DATE_COUNTS = {
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
TARGET_METRICS = (
    "pct_above_ema20",
    "return_5d",
    "synthetic_close",
    "trend_breadth",
    "weakness_breadth",
    "valid_signal_dates",
)
CURRENT_DAY_GROUP_METRICS = (
    "pct_above_ema20",
    "return_5d",
    "trend_breadth",
    "weakness_breadth",
)
GROUP_TYPE_BY_ENTITY_TYPE = {
    "LAYER": "layer",
    "SUBINDUSTRY": "subindustry",
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
        raise ValueError(
            f"Missing eligible LAYER/SUBINDUSTRY group window coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _load_metric_unit_conventions(conn: sqlite3.Connection, run_row: sqlite3.Row) -> dict[str, str | None]:
    rows = conn.execute(
        f"""
        SELECT m.metric_name, m.metric_unit
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.signal_date = ?
          AND m.taxonomy_version_id = ?
          AND m.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
          AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
          AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
        GROUP BY m.metric_name, m.metric_unit
        ORDER BY m.metric_name, m.metric_unit
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_WINDOWS,
            *TARGET_ENTITY_TYPES,
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
            f"Not enough valid signal_date values in '{SOURCE_TABLE_GROUP}' for limit={limit}; found {len(selected_dates)}"
        )
    return selected_dates


def _load_current_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    group_names_by_type: dict[str, list[str]],
) -> tuple[list[sqlite3.Row], set[str]]:
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    required = {
        "signal_date",
        "taxonomy_version",
        "group_type",
        "group_name",
        "pct_above_ema20",
        "return_5d",
        "trend_breadth",
        "weakness_breadth",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required columns: {', '.join(missing)}")
    if "run_id" not in columns and "signal_version" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing both run_id and signal_version")
    predicates: list[str] = []
    params: list[object] = [signal_date, taxonomy_version_code]
    for group_type, group_names in group_names_by_type.items():
        if not group_names:
            continue
        predicates.append(
            f"(group_type = ? AND group_name IN ({', '.join('?' for _ in group_names)}))"
        )
        params.append(group_type)
        params.extend(group_names)
    if not predicates:
        return [], columns
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_GROUP}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND ({' OR '.join(predicates)})
        ORDER BY group_type, group_name
        """,
        tuple(params),
    ).fetchall()
    return rows, columns


def _load_history_group_rows(
    conn: sqlite3.Connection,
    *,
    selected_dates: list[str],
    taxonomy_version_code: str,
    group_names_by_type: dict[str, list[str]],
) -> tuple[list[sqlite3.Row], set[str]]:
    if not selected_dates:
        return [], set()
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    predicates: list[str] = []
    params: list[object] = [*selected_dates, taxonomy_version_code]
    for group_type, group_names in group_names_by_type.items():
        if not group_names:
            continue
        predicates.append(
            f"(group_type = ? AND group_name IN ({', '.join('?' for _ in group_names)}))"
        )
        params.append(group_type)
        params.extend(group_names)
    if not predicates:
        return [], columns
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_GROUP}
        WHERE signal_date IN ({", ".join("?" for _ in selected_dates)})
          AND taxonomy_version = ?
          AND ({' OR '.join(predicates)})
        ORDER BY group_type, group_name, signal_date
        """,
        tuple(params),
    ).fetchall()
    return rows, columns


def _load_current_synthetic_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    group_names_by_type: dict[str, list[str]],
) -> tuple[list[sqlite3.Row], set[str]]:
    if not _table_exists(conn, SOURCE_TABLE_SYNTHETIC):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_SYNTHETIC}'")
    columns = _column_names(conn, SOURCE_TABLE_SYNTHETIC)
    required = {"ohlc_date", "taxonomy_version", "group_type", "group_name", "synthetic_close"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_SYNTHETIC}' missing required columns: {', '.join(missing)}")
    if "run_id" not in columns and "signal_version" not in columns and "calc_version" not in columns:
        raise ValueError(
            f"Source table '{SOURCE_TABLE_SYNTHETIC}' missing run_id, signal_version, and calc_version"
        )
    predicates: list[str] = []
    params: list[object] = [signal_date, taxonomy_version_code]
    for group_type, group_names in group_names_by_type.items():
        if not group_names:
            continue
        predicates.append(
            f"(group_type = ? AND group_name IN ({', '.join('?' for _ in group_names)}))"
        )
        params.append(group_type)
        params.extend(group_names)
    if not predicates:
        return [], columns
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_SYNTHETIC}
        WHERE ohlc_date = ?
          AND taxonomy_version = ?
          AND ({' OR '.join(predicates)})
        ORDER BY group_type, group_name
        """,
        tuple(params),
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
                  AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
              )
            """,
            (
                str(run_row["run_id"]),
                str(run_row["signal_date"]),
                int(run_row["taxonomy_version_id"]),
                *TARGET_WINDOWS,
                *TARGET_METRICS,
                *TARGET_ENTITY_TYPES,
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
              AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
          )
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_WINDOWS,
            *TARGET_METRICS,
            *TARGET_ENTITY_TYPES,
        ),
    )
    return int(cursor.rowcount)


def _derive_source_run_id(rows: list[sqlite3.Row], columns: set[str], fallback_columns: tuple[str, ...]) -> str | None:
    run_ids: set[str] = set()
    if "run_id" in columns:
        run_ids = {_normalize_text(row["run_id"]) for row in rows if _normalize_text(row["run_id"]) is not None}
    if len(run_ids) == 1:
        return next(iter(run_ids))
    for fallback_column in fallback_columns:
        if fallback_column not in columns:
            continue
        fallback_values = {
            _normalize_text(row[fallback_column]) for row in rows if _normalize_text(row[fallback_column]) is not None
        }
        if len(fallback_values) == 1:
            return next(iter(fallback_values))
    return None


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
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
        "window_code": str(coverage_row["window_code"]),
        "entity_id": int(coverage_row["entity_id"]),
        "metric_name": metric_name,
        "metric_value_num": metric_value_num,
        "metric_value_text": None,
        "metric_unit": metric_unit,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def build_canonical_v3_group_window_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
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

        group_names_by_type: dict[str, list[str]] = {"layer": [], "subindustry": []}
        selected_group_entity_count_by_type: Counter[str] = Counter()
        selected_group_entity_count_by_window: Counter[str] = Counter()
        seen_by_type: dict[str, set[int]] = {entity_type: set() for entity_type in TARGET_ENTITY_TYPES}
        coverage_by_key: dict[tuple[str, str, str], sqlite3.Row] = {}
        coverage_rows_by_window: dict[str, list[sqlite3.Row]] = {window_code: [] for window_code in TARGET_WINDOWS}
        for row in coverage_rows:
            entity_type = str(row["entity_type"])
            window_code = str(row["window_code"])
            group_type = GROUP_TYPE_BY_ENTITY_TYPE[entity_type]
            group_name = str(row["entity_name"])
            coverage_by_key[(window_code, entity_type, group_name)] = row
            coverage_rows_by_window[window_code].append(row)
            if int(row["entity_id"]) not in seen_by_type[entity_type]:
                seen_by_type[entity_type].add(int(row["entity_id"]))
                selected_group_entity_count_by_type[entity_type] += 1
            if group_name not in group_names_by_type[group_type]:
                group_names_by_type[group_type].append(group_name)
            selected_group_entity_count_by_window[window_code] += 1

        current_group_rows, group_columns = _load_current_group_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            group_names_by_type=group_names_by_type,
        )
        current_synthetic_rows, synthetic_columns = _load_current_synthetic_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            group_names_by_type=group_names_by_type,
        )

        group_row_by_key = {
            (str(row["group_type"]).lower(), str(row["group_name"])): row for row in current_group_rows
        }
        synthetic_row_by_key = {
            (str(row["group_type"]).lower(), str(row["group_name"])): row for row in current_synthetic_rows
        }

        selected_window_dates: dict[str, list[str]] = {"daily": [str(run_row["signal_date"])]}
        history_rows_by_window: dict[str, dict[tuple[str, str], list[sqlite3.Row]]] = {}
        source_rows_read_by_table = {
            SOURCE_TABLE_GROUP: len(current_group_rows),
            SOURCE_TABLE_SYNTHETIC: len(current_synthetic_rows),
        }
        for window_code in ("rolling2", "rolling5", "rolling30"):
            selected_dates = _load_valid_signal_dates(
                conn,
                signal_date=str(run_row["signal_date"]),
                taxonomy_version_code=str(run_row["version_code"]),
                limit=WINDOW_DATE_COUNTS[window_code],
            )
            selected_window_dates[window_code] = selected_dates
            history_rows, history_columns = _load_history_group_rows(
                conn,
                selected_dates=selected_dates,
                taxonomy_version_code=str(run_row["version_code"]),
                group_names_by_type=group_names_by_type,
            )
            group_columns |= history_columns
            source_rows_read_by_table[SOURCE_TABLE_GROUP] += len(history_rows)
            grouped_history: dict[tuple[str, str], list[sqlite3.Row]] = {}
            for row in history_rows:
                grouped_history.setdefault((str(row["group_type"]).lower(), str(row["group_name"])), []).append(row)
            history_rows_by_window[window_code] = grouped_history

        metric_rows: list[dict[str, object]] = []
        warnings: list[str] = []
        missing_source_groups: list[str] = []
        metric_name_counts: Counter[str] = Counter()
        metric_name_counts_by_window: dict[str, Counter[str]] = {
            window_code: Counter() for window_code in TARGET_WINDOWS
        }
        metric_name_counts_by_entity_type: dict[str, Counter[str]] = {
            entity_type: Counter() for entity_type in TARGET_ENTITY_TYPES
        }
        metric_unit_counts: Counter[str | None] = Counter()
        metric_value_status_counts: Counter[str] = Counter()
        source_run_id_counts: Counter[str] = Counter()
        source_rows_mapped_by_table = {
            SOURCE_TABLE_GROUP: 0,
            SOURCE_TABLE_SYNTHETIC: 0,
        }
        source_rows_skipped_by_table = {
            SOURCE_TABLE_GROUP: 0,
            SOURCE_TABLE_SYNTHETIC: 0,
        }
        mixed_source_run_warning_count = 0

        def record_metric(row: sqlite3.Row, metric_name: str, metric_value_num: float | int, source_run_id: str) -> None:
            metric_rows.append(
                _build_metric_row(
                    run_row=run_row,
                    coverage_row=row,
                    metric_name=metric_name,
                    metric_value_num=metric_value_num,
                    metric_unit=unit_conventions[metric_name],
                    source_run_id=source_run_id,
                )
            )
            window_code = str(row["window_code"])
            entity_type = str(row["entity_type"])
            metric_name_counts[metric_name] += 1
            metric_name_counts_by_window[window_code][metric_name] += 1
            metric_name_counts_by_entity_type[entity_type][metric_name] += 1
            metric_unit_counts[unit_conventions[metric_name]] += 1
            metric_value_status_counts["OK"] += 1
            source_run_id_counts[source_run_id] += 1

        for coverage_row in coverage_rows:
            entity_type = str(coverage_row["entity_type"])
            window_code = str(coverage_row["window_code"])
            group_type = GROUP_TYPE_BY_ENTITY_TYPE[entity_type]
            group_name = str(coverage_row["entity_name"])
            source_key = (group_type, group_name)

            current_group_row = group_row_by_key.get(source_key)
            if current_group_row is None:
                warnings.append(
                    f"Missing lower-level group row in {SOURCE_TABLE_GROUP} for {entity_type} '{group_name}' / {window_code}"
                )
                missing_source_groups.append(f"{SOURCE_TABLE_GROUP}:{entity_type}:{group_name}:{window_code}")
                source_rows_skipped_by_table[SOURCE_TABLE_GROUP] += 1
            else:
                group_source_run_id = _derive_source_run_id([current_group_row], group_columns, ("signal_version",))
                if group_source_run_id is None:
                    warnings.append(
                        f"Missing lower-level lineage in {SOURCE_TABLE_GROUP} for {entity_type} '{group_name}' / {window_code}"
                    )
                    missing_source_groups.append(f"{SOURCE_TABLE_GROUP}:{entity_type}:{group_name}:{window_code}:lineage")
                    source_rows_skipped_by_table[SOURCE_TABLE_GROUP] += 1
                else:
                    inserted_from_group = False
                    for metric_name in CURRENT_DAY_GROUP_METRICS:
                        metric_value_num = _normalize_float(current_group_row[metric_name])
                        if metric_value_num is None:
                            continue
                        record_metric(coverage_row, metric_name, metric_value_num, group_source_run_id)
                        inserted_from_group = True
                    if window_code != "daily":
                        history_rows = history_rows_by_window[window_code].get(source_key, [])
                        expected_count = WINDOW_DATE_COUNTS[window_code]
                        if len(history_rows) < expected_count:
                            warnings.append(
                                f"Missing lower-level group history for valid_signal_dates in {entity_type} '{group_name}' / {window_code}"
                            )
                            missing_source_groups.append(
                                f"{SOURCE_TABLE_GROUP}:{entity_type}:{group_name}:{window_code}:valid_signal_dates"
                            )
                            source_rows_skipped_by_table[SOURCE_TABLE_GROUP] += 1
                        else:
                            history_source_run_id = _derive_source_run_id(history_rows, group_columns, ("signal_version",))
                            if history_source_run_id is None:
                                mixed_source_run_warning_count += 1
                                warnings.append(
                                    f"Mixed lower-level lineage for valid_signal_dates in {entity_type} '{group_name}' / {window_code}"
                                )
                                source_rows_skipped_by_table[SOURCE_TABLE_GROUP] += 1
                            else:
                                record_metric(
                                    coverage_row,
                                    "valid_signal_dates",
                                    expected_count,
                                    history_source_run_id,
                                )
                                inserted_from_group = True
                    if inserted_from_group:
                        source_rows_mapped_by_table[SOURCE_TABLE_GROUP] += 1

            current_synthetic_row = synthetic_row_by_key.get(source_key)
            if current_synthetic_row is None:
                warnings.append(
                    f"Missing lower-level group row in {SOURCE_TABLE_SYNTHETIC} for {entity_type} '{group_name}' / {window_code}"
                )
                missing_source_groups.append(f"{SOURCE_TABLE_SYNTHETIC}:{entity_type}:{group_name}:{window_code}")
                source_rows_skipped_by_table[SOURCE_TABLE_SYNTHETIC] += 1
            else:
                synthetic_source_run_id = _derive_source_run_id(
                    [current_synthetic_row],
                    synthetic_columns,
                    ("signal_version", "calc_version"),
                )
                synthetic_close = _normalize_float(current_synthetic_row["synthetic_close"])
                if synthetic_source_run_id is None:
                    warnings.append(
                        f"Missing lower-level lineage in {SOURCE_TABLE_SYNTHETIC} for {entity_type} '{group_name}' / {window_code}"
                    )
                    missing_source_groups.append(
                        f"{SOURCE_TABLE_SYNTHETIC}:{entity_type}:{group_name}:{window_code}:lineage"
                    )
                    source_rows_skipped_by_table[SOURCE_TABLE_SYNTHETIC] += 1
                elif synthetic_close is None:
                    source_rows_skipped_by_table[SOURCE_TABLE_SYNTHETIC] += 1
                else:
                    record_metric(coverage_row, "synthetic_close", synthetic_close, synthetic_source_run_id)
                    source_rows_mapped_by_table[SOURCE_TABLE_SYNTHETIC] += 1

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
            "entity_types": list(TARGET_ENTITY_TYPES),
            "window_codes": list(TARGET_WINDOWS),
            "selected_group_entity_count_by_type": dict(selected_group_entity_count_by_type),
            "selected_group_entity_count_by_window": dict(selected_group_entity_count_by_window),
            "selected_window_dates": selected_window_dates,
            "source_rows_read_by_table": source_rows_read_by_table,
            "source_rows_mapped_by_table": source_rows_mapped_by_table,
            "source_rows_skipped_by_table": source_rows_skipped_by_table,
            "missing_source_groups": missing_source_groups,
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": dict(metric_name_counts),
            "metric_name_counts_by_window": {
                window_code: dict(window_counts)
                for window_code, window_counts in metric_name_counts_by_window.items()
            },
            "metric_name_counts_by_entity_type": {
                entity_type: dict(entity_counts)
                for entity_type, entity_counts in metric_name_counts_by_entity_type.items()
            },
            "metric_unit_counts": dict(metric_unit_counts),
            "metric_value_status_counts": dict(metric_value_status_counts),
            "source_run_id_counts": dict(source_run_id_counts),
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "mixed_source_run_warning_count": mixed_source_run_warning_count,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": [
                "replaces only LAYER/SUBINDUSTRY group window metrics",
                "source is dc_group_swing_signal_daily and dc_group_synthetic_ohlc_daily",
                "no source_table column exists on eco_entity_metric_value",
                "latest-N valid signal_date semantics are used for rolling valid_signal_dates",
                "synthetic_close comes from group synthetic OHLC source",
                "does not create MISSING metric rows",
                "ticker metrics are not modified",
                "freshness metrics are not modified",
                "group status metrics are not modified",
                "no signal/relevance/event/classification rows are created",
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
