from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict

from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    _classify_group_structure_freshness,
)


SOURCE_TABLES_USED = ("eco_entity_event", "eco_entity_metric_value")
TARGET_TABLE = "eco_entity_metric_value"
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
TARGET_METRICS = (
    "freshness_latest_structure_class",
    "freshness_latest_bos_class",
    "freshness_latest_reset_class",
)
EVENT_TYPES_BY_METRIC = {
    "freshness_latest_structure_class": ("STRUCTURE_CHANGE", "TREND_STATE_CHANGE"),
    "freshness_latest_bos_class": ("BOS",),
    "freshness_latest_reset_class": ("RESET",),
}
GROUP_TYPE_BY_ENTITY_TYPE = {
    "LAYER": "layer",
    "SUBINDUSTRY": "subindustry",
}
STRUCTURE_EVENT_PRIORITY = {
    "STRUCTURE_CHANGE": 0,
    "TREND_STATE_CHANGE": 1,
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_one(conn: sqlite3.Connection, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    return conn.execute(query, params).fetchone()


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


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _load_target_coverage(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    rows = conn.execute(
        f"""
        SELECT
            c.window_code,
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
        ORDER BY e.entity_type, e.entity_code, c.window_code
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
            f"Missing eligible LAYER/SUBINDUSTRY coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _load_valid_signal_dates(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT DISTINCT m.signal_date
        FROM {TARGET_TABLE} m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.taxonomy_version_id = ?
          AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
          AND m.signal_date <= ?
        ORDER BY m.signal_date
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            *TARGET_ENTITY_TYPES,
            str(run_row["signal_date"]),
        ),
    ).fetchall()
    dates = [str(row["signal_date"]) for row in rows]
    if not dates:
        raise ValueError(
            "Missing same-run group metric signal_date history in eco_entity_metric_value for "
            f"run_id '{run_row['run_id']}'"
        )
    return dates


def _load_latest_event_rows(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    entity_ids: list[int],
) -> dict[tuple[int, str], sqlite3.Row]:
    if not entity_ids:
        return {}
    rows = conn.execute(
        f"""
        SELECT
            entity_event_id,
            entity_id,
            event_date,
            event_type,
            source_run_id
        FROM eco_entity_event
        WHERE run_id = ?
          AND taxonomy_version_id = ?
          AND event_status = 'ACTIVE'
          AND entity_id IN ({", ".join("?" for _ in entity_ids)})
          AND event_type IN ('STRUCTURE_CHANGE', 'TREND_STATE_CHANGE', 'BOS', 'RESET')
          AND event_date <= ?
        ORDER BY entity_id, event_date DESC, entity_event_id DESC
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            *entity_ids,
            str(run_row["signal_date"]),
        ),
    ).fetchall()
    latest_by_key: dict[tuple[int, str], sqlite3.Row] = {}
    for row in rows:
        entity_id = int(row["entity_id"])
        event_type = str(row["event_type"])
        if event_type in {"STRUCTURE_CHANGE", "TREND_STATE_CHANGE"}:
            key = (entity_id, "freshness_latest_structure_class")
            current = latest_by_key.get(key)
            if current is None:
                latest_by_key[key] = row
                continue
            current_date = str(current["event_date"])
            row_date = str(row["event_date"])
            if row_date > current_date:
                latest_by_key[key] = row
                continue
            if row_date == current_date:
                current_priority = STRUCTURE_EVENT_PRIORITY.get(str(current["event_type"]), 99)
                row_priority = STRUCTURE_EVENT_PRIORITY.get(event_type, 99)
                if row_priority < current_priority:
                    latest_by_key[key] = row
            continue
        metric_name = (
            "freshness_latest_bos_class"
            if event_type == "BOS"
            else "freshness_latest_reset_class"
        )
        key = (entity_id, metric_name)
        if key not in latest_by_key:
            latest_by_key[key] = row
    return latest_by_key


def _count_age_trading_days(valid_signal_dates: list[str], event_date: str, target_signal_date: str) -> int:
    return sum(1 for signal_date in valid_signal_dates if event_date < signal_date <= target_signal_date)


def _existing_row_count(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {TARGET_TABLE} m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND m.taxonomy_version_id = ?
              AND m.signal_date = ?
              AND m.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
              AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
              AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
            """,
            (
                str(run_row["run_id"]),
                int(run_row["taxonomy_version_id"]),
                str(run_row["signal_date"]),
                *TARGET_WINDOWS,
                *TARGET_ENTITY_TYPES,
                *TARGET_METRICS,
            ),
        ).fetchone()[0]
    )


def _delete_existing_rows(conn: sqlite3.Connection, run_row: sqlite3.Row) -> int:
    cursor = conn.execute(
        f"""
        DELETE FROM {TARGET_TABLE}
        WHERE rowid IN (
            SELECT m.rowid
            FROM {TARGET_TABLE} m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND m.taxonomy_version_id = ?
              AND m.signal_date = ?
              AND m.window_code IN ({", ".join("?" for _ in TARGET_WINDOWS)})
              AND e.entity_type IN ({", ".join("?" for _ in TARGET_ENTITY_TYPES)})
              AND m.metric_name IN ({", ".join("?" for _ in TARGET_METRICS)})
        )
        """,
        (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            str(run_row["signal_date"]),
            *TARGET_WINDOWS,
            *TARGET_ENTITY_TYPES,
            *TARGET_METRICS,
        ),
    )
    return int(cursor.rowcount)


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    entity_id: int,
    metric_name: str,
    metric_value_text: str,
    source_run_id: str | None,
) -> dict[str, object]:
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": None,
        "metric_value_text": metric_value_text,
        "metric_unit": None,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def build_canonical_v3_group_freshness_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        valid_signal_dates = _load_valid_signal_dates(conn, run_row)
        entity_ids = sorted({int(row["entity_id"]) for row in coverage_rows})
        latest_event_rows = _load_latest_event_rows(conn, run_row, entity_ids)
        windows_by_entity_id: dict[int, list[str]] = defaultdict(list)
        entity_type_by_id: dict[int, str] = {}
        for row in coverage_rows:
            entity_id = int(row["entity_id"])
            windows_by_entity_id[entity_id].append(str(row["window_code"]))
            entity_type_by_id[entity_id] = str(row["entity_type"])

        existing_rows = _existing_row_count(conn, run_row)
        if existing_rows and not replace_existing:
            raise ValueError(
                f"Group freshness builder-owned rows already exist for run_id '{run_id}'"
            )

        metric_rows: list[dict[str, object]] = []
        missing_event_counts: Counter[str] = Counter()
        freshness_class_counts: Counter[str] = Counter()

        for entity_id in entity_ids:
            entity_type = entity_type_by_id[entity_id]
            group_type = GROUP_TYPE_BY_ENTITY_TYPE[entity_type]
            entity_windows = sorted(set(windows_by_entity_id[entity_id]))
            for metric_name in TARGET_METRICS:
                event_row = latest_event_rows.get((entity_id, metric_name))
                if event_row is None:
                    missing_event_counts[metric_name] += 1
                    continue
                age_trading_days = _count_age_trading_days(
                    valid_signal_dates,
                    str(event_row["event_date"]),
                    str(run_row["signal_date"]),
                )
                freshness_class = _classify_group_structure_freshness(
                    group_type=group_type,
                    age_trading_days=age_trading_days,
                )
                if freshness_class is None:
                    missing_event_counts[metric_name] += 1
                    continue
                source_run_id = _normalize_text(event_row["source_run_id"])
                freshness_class_counts[freshness_class] += len(entity_windows)
                for window_code in entity_windows:
                    metric_rows.append(
                        _build_metric_row(
                            run_row=run_row,
                            window_code=window_code,
                            entity_id=entity_id,
                            metric_name=metric_name,
                            metric_value_text=freshness_class,
                            source_run_id=source_run_id,
                        )
                    )

        conn.execute("BEGIN")
        deleted_rows = 0
        if replace_existing:
            deleted_rows = _delete_existing_rows(conn, run_row)
        if deleted_rows and not replace_existing:
            raise AssertionError("unexpected delete without replace_existing")
        if metric_rows:
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
        conn.commit()

        status = "OK"
        if not latest_event_rows:
            status = "NO_SOURCE_EVENTS"
        elif missing_event_counts:
            status = "OK_WITH_WARNINGS"
        return {
            "run_id": str(run_row["run_id"]),
            "target_signal_date": str(run_row["signal_date"]),
            "windows": list(TARGET_WINDOWS),
            "inserted_rows": len(metric_rows),
            "deleted_rows": deleted_rows,
            "skipped_no_event_count": int(sum(missing_event_counts.values())),
            "missing_event_counts": dict(sorted(missing_event_counts.items())),
            "entity_count": len(entity_ids),
            "source_tables_used": list(SOURCE_TABLES_USED),
            "valid_signal_dates_count": len(valid_signal_dates),
            "freshness_class_counts": dict(sorted(freshness_class_counts.items())),
            "limitations": [
                "uses same-run group metric signal_date coverage from eco_entity_metric_value as trading-day calendar",
                "derives group freshness from eco_entity_event only; no dc_* sources are used",
                "materializes class metrics only; no age metrics or signal observations are created",
            ],
            "status": status,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
