from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE = "dc_group_swing_signal_daily"
SOURCE_CLASSIFICATIONS = {
    SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
GROUP_TYPE_TO_ENTITY_TYPE = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
}
REPLACEMENT_METRIC_SPECS = (
    ("overheat_risk_level", "group_overheat_risk_level"),
    ("timing_state", "group_timing_state"),
    ("timing_reason", "group_timing_reason"),
    ("timing_state", "group_current_status"),
)
REPLACEMENT_METRIC_NAMES = tuple(metric_name for _, metric_name in REPLACEMENT_METRIC_SPECS)


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


def _select_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in column_names:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


def _coalesce_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    available = [name for name in preferred_names if name in column_names]
    if not available:
        return f"NULL AS {alias}"
    return f"COALESCE({', '.join(available)}) AS {alias}"


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
          AND c.window_code IN ('daily', 'rolling2', 'rolling5', 'rolling30')
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


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_group_names: set[tuple[str, str]],
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    columns = _column_names(conn, SOURCE_TABLE)
    required = {
        "signal_date",
        "taxonomy_version",
        "group_type",
        "group_name",
        "timing_state",
        "timing_reason",
        "overheat_risk_level",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing)}")
    pairs = sorted(eligible_group_names)
    pair_clause = " OR ".join("(group_type = ? AND group_name = ?)" for _ in pairs)
    query = f"""
        SELECT
            signal_date,
            taxonomy_version,
            group_type,
            group_name,
            timing_state,
            timing_reason,
            overheat_risk_level,
            {_coalesce_expr(columns, ('run_id', 'signal_version', 'calc_version'), 'source_run_id')}
        FROM {SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND group_type IN ('layer', 'subindustry')
          AND ({pair_clause})
        ORDER BY group_type, group_name
    """
    params: list[object] = [signal_date, taxonomy_version_code]
    for group_type, group_name in pairs:
        params.extend((group_type, group_name))
    return conn.execute(query, tuple(params)).fetchall()


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    metric_name: str,
    source_value: object,
    source_run_id: str | None,
) -> dict[str, object] | None:
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
        "source_run_id": source_run_id,
    }


def _build_rows(
    *,
    run_row: sqlite3.Row,
    coverage_by_group: dict[tuple[str, str], list[sqlite3.Row]],
    source_rows: list[sqlite3.Row],
    warnings: list[str],
) -> tuple[list[dict[str, object]], int, int, list[str]]:
    metric_rows: list[dict[str, object]] = []
    mapped_count = 0
    skipped_count = 0
    source_keys = {
        (_normalize_text(row["group_type"]) or "", _normalize_text(row["group_name"]) or "")
        for row in source_rows
    }
    missing_source_groups = sorted(
        f"{entity_type}:{group_name}" for entity_type, group_name in coverage_by_group if (entity_type.lower(), group_name) not in source_keys
    )

    for source_row in source_rows:
        group_type = _normalize_text(source_row["group_type"])
        group_name = _normalize_text(source_row["group_name"])
        if group_type is None or group_name is None:
            warnings.append("Skipped dc_group_swing_signal_daily row with missing group_type/group_name")
            skipped_count += 1
            continue
        entity_type = GROUP_TYPE_TO_ENTITY_TYPE.get(group_type.lower())
        if entity_type is None:
            warnings.append(f"Skipped dc_group_swing_signal_daily row with unsupported group_type '{group_type}'")
            skipped_count += 1
            continue
        coverage_rows = coverage_by_group.get((entity_type, group_name))
        if not coverage_rows:
            warnings.append(
                "Skipped dc_group_swing_signal_daily row without eligible coverage: "
                f"{group_type}/{group_name}"
            )
            skipped_count += 1
            continue

        mapped_count += 1
        source_run_id = _normalize_text(source_row["source_run_id"])
        for coverage_row in coverage_rows:
            for source_column, metric_name in REPLACEMENT_METRIC_SPECS:
                metric_row = _build_metric_row(
                    run_row=run_row,
                    coverage_row=coverage_row,
                    metric_name=metric_name,
                    source_value=source_row[source_column],
                    source_run_id=source_run_id,
                )
                if metric_row is not None:
                    metric_rows.append(metric_row)

    return metric_rows, mapped_count, skipped_count, missing_source_groups


def _existing_replacement_count(conn: sqlite3.Connection, *, run_id: str) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
              AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
            """,
            (run_id, *REPLACEMENT_METRIC_NAMES),
        ).fetchone()[0]
    )


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> int:
    existing_count = _existing_replacement_count(conn, run_id=run_id)
    if existing_count and not replace_existing:
        raise ValueError(f"Group status replacement rows already exist for run_id '{run_id}'")
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
              AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
        )
        """,
        (run_id, *REPLACEMENT_METRIC_NAMES),
    )
    return existing_count


def build_canonical_v3_group_status_from_group_swing(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        coverage_by_group: dict[tuple[str, str], list[sqlite3.Row]] = {}
        selected_entity_ids: set[int] = set()
        selected_windows: set[str] = set()
        eligible_group_names: set[tuple[str, str]] = set()
        for row in coverage_rows:
            entity_type = str(row["entity_type"])
            entity_name = str(row["entity_name"])
            coverage_by_group.setdefault((entity_type, entity_name), []).append(row)
            selected_entity_ids.add(int(row["entity_id"]))
            selected_windows.add(str(row["window_code"]))
            if entity_type == "LAYER":
                eligible_group_names.add(("layer", entity_name))
            elif entity_type == "SUBINDUSTRY":
                eligible_group_names.add(("subindustry", entity_name))

        warnings: list[str] = []
        limitations = [
            "partial replacement only",
            "replaces only group_overheat_risk_level, group_current_status, group_timing_state, group_timing_reason",
            "group_window_status and group_status_change remain transitional",
            "source is dc_group_swing_signal_daily, not dc_report_context_group_v2",
            "fan-out to all windows is allowed only because DB-V3-39 proved exact equivalence for these four metrics",
            "metric source_table lineage is unavailable because eco_entity_metric_value has no source_table column",
            "no signal rows are created",
            "no relevance rows are created",
            "no event rows are created",
        ]

        source_rows = _load_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_group_names=eligible_group_names,
        )
        metric_rows, mapped_count, skipped_count, missing_source_groups = _build_rows(
            run_row=run_row,
            coverage_by_group=coverage_by_group,
            source_rows=source_rows,
            warnings=warnings,
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
            "source_rows_read": len(source_rows),
            "source_rows_mapped": mapped_count,
            "source_rows_skipped": skipped_count,
            "missing_source_groups": missing_source_groups,
            "metric_rows_inserted": len(metric_rows),
            "metric_name_counts": metric_name_counts,
            "metric_value_counts": metric_value_counts,
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": limitations,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
