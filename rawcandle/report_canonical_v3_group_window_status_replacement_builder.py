from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE = "dc_group_swing_signal_daily"
SOURCE_CLASSIFICATIONS = {
    SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("rolling2", "rolling5", "rolling30")
HORIZON_WINDOW_SIZES = {
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
GROUP_TYPE_TO_ENTITY_TYPE = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
}
REPLACEMENT_METRIC_NAMES = (
    "group_window_status",
    "group_status_change",
)
ROLLING_GROUP_STATUS_PRIORITY = {
    "EXIT_ZONE": 0,
    "TRIM_WATCH": 1,
    "ADD_ON_PULLBACK": 2,
    "BUY_ZONE": 3,
    "NEUTRAL": 4,
    None: 5,
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
          AND c.window_code IN ('rolling2', 'rolling5', 'rolling30')
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
        raise ValueError(f"Missing eligible LAYER/SUBINDUSTRY rolling coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _build_pair_clause(pairs: list[tuple[str, str]]) -> tuple[str, list[object]]:
    clause = " OR ".join("(group_type = ? AND group_name = ?)" for _ in pairs)
    params: list[object] = []
    for group_type, group_name in pairs:
        params.extend((group_type, group_name))
    return clause, params


def _load_window_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_group_names: set[tuple[str, str]],
    horizon: str,
) -> list[str]:
    if not eligible_group_names:
        return []
    limit = HORIZON_WINDOW_SIZES[horizon]
    pairs = sorted(eligible_group_names)
    pair_clause, pair_params = _build_pair_clause(pairs)
    rows = conn.execute(
        f"""
        SELECT DISTINCT signal_date
        FROM {SOURCE_TABLE}
        WHERE signal_date <= ?
          AND taxonomy_version = ?
          AND group_type IN ('layer', 'subindustry')
          AND ({pair_clause})
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (signal_date, taxonomy_version_code, *pair_params, limit),
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _load_source_history_rows(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_code: str,
    eligible_group_names: set[tuple[str, str]],
    selected_dates: set[str],
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    if not eligible_group_names or not selected_dates:
        return []
    columns = _column_names(conn, SOURCE_TABLE)
    required = {
        "signal_date",
        "taxonomy_version",
        "group_type",
        "group_name",
        "timing_state",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing)}")
    if "run_id" not in columns and "signal_version" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing both run_id and signal_version columns")

    date_placeholders = ", ".join("?" for _ in selected_dates)
    pairs = sorted(eligible_group_names)
    pair_clause, pair_params = _build_pair_clause(pairs)
    query = f"""
        SELECT
            signal_date,
            taxonomy_version,
            group_type,
            group_name,
            timing_state,
            {"run_id" if "run_id" in columns else "NULL"} AS run_id,
            {"signal_version" if "signal_version" in columns else "NULL"} AS signal_version
        FROM {SOURCE_TABLE}
        WHERE taxonomy_version = ?
          AND signal_date IN ({date_placeholders})
          AND group_type IN ('layer', 'subindustry')
          AND ({pair_clause})
        ORDER BY signal_date ASC, group_type ASC, group_name ASC
    """
    params: list[object] = [taxonomy_version_code, *sorted(selected_dates), *pair_params]
    return conn.execute(query, tuple(params)).fetchall()


def _most_severe_group_status(source_rows: list[sqlite3.Row]) -> str | None:
    if not source_rows:
        return None
    values = [row["timing_state"] for row in source_rows]
    return min(values, key=lambda value: ROLLING_GROUP_STATUS_PRIORITY.get(value, 6))


def _status_change(source_rows: list[sqlite3.Row]) -> str | None:
    if not source_rows:
        return None
    first_status = _normalize_text(source_rows[0]["timing_state"])
    last_status = _normalize_text(source_rows[-1]["timing_state"])
    if not first_status or not last_status or first_status == last_status:
        return None
    return f"{first_status} -> {last_status}"


def _resolve_source_lineage(source_rows: list[sqlite3.Row]) -> tuple[str | None, str | None]:
    run_ids = {
        value
        for value in (_normalize_text(row["run_id"]) for row in source_rows)
        if value is not None
    }
    if len(run_ids) == 1:
        return next(iter(run_ids)), None
    signal_versions = {
        value
        for value in (_normalize_text(row["signal_version"]) for row in source_rows)
        if value is not None
    }
    if len(signal_versions) == 1:
        return next(iter(signal_versions)), None
    return None, (
        "Mixed source lineage for selected window rows: "
        f"run_ids={sorted(run_ids) or []}, signal_versions={sorted(signal_versions) or []}"
    )


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    metric_name: str,
    metric_value_text: str,
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
        "metric_value_num": None,
        "metric_value_text": metric_value_text,
        "metric_unit": None,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def _existing_replacement_count(conn: sqlite3.Connection, *, run_id: str) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
              AND m.window_code IN ('rolling2', 'rolling5', 'rolling30')
              AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
            """,
            (run_id, *REPLACEMENT_METRIC_NAMES),
        ).fetchone()[0]
    )


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> int:
    existing_count = _existing_replacement_count(conn, run_id=run_id)
    if existing_count and not replace_existing:
        raise ValueError(f"Group window/status-change replacement rows already exist for run_id '{run_id}'")
    if not existing_count or not replace_existing:
        return 0
    conn.execute(
        f"""
        DELETE FROM eco_entity_metric_value
        WHERE rowid IN (
            SELECT m.rowid
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
              AND m.window_code IN ('rolling2', 'rolling5', 'rolling30')
              AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
        )
        """,
        (run_id, *REPLACEMENT_METRIC_NAMES),
    )
    return existing_count


def build_canonical_v3_group_window_status_from_group_swing(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        coverage_by_group: dict[tuple[str, str], list[sqlite3.Row]] = {}
        eligible_group_names: set[tuple[str, str]] = set()
        selected_entity_ids: set[int] = set()
        for row in coverage_rows:
            entity_type = str(row["entity_type"])
            entity_name = str(row["entity_name"])
            coverage_by_group.setdefault((entity_type, entity_name), []).append(row)
            selected_entity_ids.add(int(row["entity_id"]))
            if entity_type == "LAYER":
                eligible_group_names.add(("layer", entity_name))
            elif entity_type == "SUBINDUSTRY":
                eligible_group_names.add(("subindustry", entity_name))

        selected_window_dates = {
            horizon: _load_window_dates(
                conn,
                signal_date=str(run_row["signal_date"]),
                taxonomy_version_code=str(run_row["version_code"]),
                eligible_group_names=eligible_group_names,
                horizon=horizon,
            )
            for horizon in TARGET_WINDOWS
        }
        selected_dates = {date for dates in selected_window_dates.values() for date in dates}
        source_rows = _load_source_history_rows(
            conn,
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_group_names=eligible_group_names,
            selected_dates=selected_dates,
        )

        history_by_group: dict[tuple[str, str], list[sqlite3.Row]] = {}
        source_keys: set[tuple[str, str]] = set()
        for row in source_rows:
            entity_type = GROUP_TYPE_TO_ENTITY_TYPE.get(str(row["group_type"]).lower())
            if entity_type is None:
                continue
            group_name = str(row["group_name"])
            key = (entity_type, group_name)
            source_keys.add(key)
            history_by_group.setdefault(key, []).append(row)

        warnings: list[str] = []
        metric_rows: list[dict[str, object]] = []
        source_rows_mapped = 0
        source_rows_skipped = 0
        mixed_source_run_warning_count = 0
        missing_source_groups = sorted(
            f"{entity_type}:{group_name}"
            for entity_type, group_name in coverage_by_group
            if (entity_type, group_name) not in source_keys
        )

        for (entity_type, group_name), group_coverage_rows in sorted(coverage_by_group.items()):
            group_history_rows = sorted(
                history_by_group.get((entity_type, group_name), []),
                key=lambda row: str(row["signal_date"]),
            )
            if not group_history_rows:
                continue
            history_by_date = {str(row["signal_date"]): row for row in group_history_rows}
            coverage_by_window = {str(row["window_code"]): row for row in group_coverage_rows}

            for window_code in TARGET_WINDOWS:
                coverage_row = coverage_by_window.get(window_code)
                if coverage_row is None:
                    continue
                window_dates = selected_window_dates[window_code]
                if len(window_dates) < HORIZON_WINDOW_SIZES[window_code]:
                    warnings.append(
                        f"Insufficient global source dates for {entity_type}:{group_name}:{window_code}"
                    )
                    source_rows_skipped += 1
                    continue
                selected_rows = [history_by_date[date] for date in window_dates if date in history_by_date]
                if len(selected_rows) < HORIZON_WINDOW_SIZES[window_code]:
                    warnings.append(
                        f"Missing source history for {entity_type}:{group_name}:{window_code}"
                    )
                    source_rows_skipped += 1
                    continue
                source_run_id, lineage_warning = _resolve_source_lineage(selected_rows)
                if lineage_warning is not None or source_run_id is None:
                    mixed_source_run_warning_count += 1
                    warnings.append(f"{entity_type}:{group_name}:{window_code}: {lineage_warning}")
                    source_rows_skipped += 1
                    continue

                source_rows_mapped += 1
                group_window_status = _normalize_text(_most_severe_group_status(selected_rows))
                if group_window_status is not None:
                    metric_rows.append(
                        _build_metric_row(
                            run_row=run_row,
                            coverage_row=coverage_row,
                            metric_name="group_window_status",
                            metric_value_text=group_window_status,
                            source_run_id=source_run_id,
                        )
                    )
                group_status_change = _normalize_text(_status_change(selected_rows))
                if group_status_change is not None:
                    metric_rows.append(
                        _build_metric_row(
                            run_row=run_row,
                            coverage_row=coverage_row,
                            metric_name="group_status_change",
                            metric_value_text=group_status_change,
                            source_run_id=source_run_id,
                        )
                    )

        metric_name_counts = dict(sorted(Counter(row["metric_name"] for row in metric_rows).items()))
        metric_value_counts = dict(
            sorted(Counter(f"{row['metric_name']}|{row['metric_value_text']}" for row in metric_rows).items())
        )

        conn.execute("BEGIN")
        rows_deleted_on_replace = _ensure_replace_allowed(
            conn,
            run_id=str(run_row["run_id"]),
            replace_existing=replace_existing,
        )
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
            "source_classifications": dict(SOURCE_CLASSIFICATIONS),
            "selected_group_entity_count": len(selected_entity_ids),
            "window_count": len(TARGET_WINDOWS),
            "selected_window_dates": dict(sorted(selected_window_dates.items())),
            "source_rows_read": len(source_rows),
            "source_rows_mapped": source_rows_mapped,
            "source_rows_skipped": source_rows_skipped,
            "missing_source_groups": missing_source_groups,
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": metric_name_counts,
            "metric_value_counts": metric_value_counts,
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "mixed_source_run_warning_count": mixed_source_run_warning_count,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": [
                "replaces only group_window_status and group_status_change",
                "source is dc_group_swing_signal_daily, not dc_report_context_group_v2",
                "latest-N valid signal_date semantics are used, not calendar-day semantics",
                "metric source_table lineage is unavailable because eco_entity_metric_value has no source_table column",
                "no daily rows are created",
                "no signal rows are created",
                "no relevance rows are created",
                "no event rows are created",
            ],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
