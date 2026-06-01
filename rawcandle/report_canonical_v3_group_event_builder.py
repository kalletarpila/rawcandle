from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict


SOURCE_TABLE = "dc_group_synthetic_ohlc_daily"
GROUP_TYPE_BY_ENTITY_TYPE = {
    "LAYER": "layer",
    "SUBINDUSTRY": "subindustry",
}
ENTITY_TYPE_BY_GROUP_TYPE = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
}


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


def _normalize_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _load_eligible_group_entities(conn: sqlite3.Connection, run_id: str) -> dict[tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT DISTINCT
            e.entity_id,
            e.entity_type,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
        ORDER BY e.entity_type, e.entity_name
        """,
        (run_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eligible LAYER/SUBINDUSTRY coverage rows for run_id '{run_id}'")
    return {
        (GROUP_TYPE_BY_ENTITY_TYPE[str(row["entity_type"])], str(row["entity_name"])): row
        for row in rows
    }


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_code: str,
    signal_date: str,
    lookback_calendar_days: int | None,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    params: list[object] = [
        taxonomy_version_code,
        signal_date,
        "layer",
        "subindustry",
    ]
    query = f"""
        SELECT
            ohlc_date,
            taxonomy_version,
            group_type,
            group_name,
            latest_structure_label,
            trend_classification,
            latest_bos_event_type,
            latest_bos_event_date,
            latest_reset_reason,
            latest_reset_event_date,
            calc_version,
            run_id
        FROM {SOURCE_TABLE}
        WHERE taxonomy_version = ?
          AND ohlc_date <= ?
          AND group_type IN (?, ?)
    """
    if lookback_calendar_days is not None:
        threshold = (_normalize_date(signal_date) - dt.timedelta(days=lookback_calendar_days)).isoformat()
        query += " AND ohlc_date >= ?"
        params.append(threshold)
    query += " ORDER BY group_type, group_name, ohlc_date"
    return conn.execute(query, tuple(params)).fetchall()


def _map_bos_direction(event_type: str | None) -> str:
    normalized = str(event_type).strip().upper().replace(" ", "_") if event_type else ""
    if normalized in {"BOS_UP", "DOUBLE_BOS_UP"}:
        return "UP"
    if normalized in {"BOS_DOWN", "DOUBLE_BOS_DOWN"}:
        return "DOWN"
    return "UNKNOWN"


def _map_reset_direction(reason: str | None) -> str:
    normalized = str(reason).strip().upper().replace(" ", "_") if reason else ""
    if "UP" in normalized:
        return "UP"
    if "DOWN" in normalized:
        return "DOWN"
    return "NONE"


def _map_trend_direction(trend: str | None) -> str:
    normalized = str(trend).strip().upper().replace(" ", "_") if trend else ""
    if normalized in {"UP", "BULLISH"}:
        return "UP"
    if normalized in {"DOWN", "BEARISH"}:
        return "DOWN"
    if normalized in {"NEUTRAL", "MIXED"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _append_event(
    *,
    bucket: dict[str, dict[str, object]],
    run_row: sqlite3.Row,
    entity_row: sqlite3.Row,
    event_date: str,
    event_type: str,
    event_direction: str,
    event_label: str,
    source_run_id: object,
) -> None:
    event_key = (
        f"group_synthetic:{SOURCE_TABLE}:{int(entity_row['entity_id'])}:"
        f"{event_type}:{event_date}:{event_label}"
    )
    bucket[event_key] = {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "entity_id": int(entity_row["entity_id"]),
        "event_date": event_date,
        "event_type": event_type,
        "source_table": SOURCE_TABLE,
        "source_run_id": str(source_run_id) if source_run_id is not None else None,
        "source_event_id": None,
        "event_key": event_key,
        "event_label": event_label,
        "event_direction": event_direction,
        "event_status": "ACTIVE",
        "event_payload_ref": None,
    }


def _build_event_rows(
    *,
    run_row: sqlite3.Row,
    source_rows: list[sqlite3.Row],
    eligible_entities: dict[tuple[str, str], sqlite3.Row],
    lookback_calendar_days: int | None,
) -> tuple[list[dict[str, object]], dict[str, int], dict[str, int], list[str], int, int, list[str]]:
    signal_day = _normalize_date(str(run_row["signal_date"]))
    threshold = signal_day - dt.timedelta(days=lookback_calendar_days) if lookback_calendar_days is not None else None
    warnings: list[str] = []
    limitations = [
        "ECOSYSTEM and TICKER events are excluded from this pilot.",
        "BOS/RESET use explicit persisted event dates only; age fields are not used to infer event dates.",
        "STRUCTURE_CHANGE and TREND_STATE_CHANGE are derived conservatively from persisted daily snapshot diffs.",
    ]
    source_rows_mapped = 0
    source_rows_skipped = 0
    grouped_rows: dict[tuple[int, str], list[sqlite3.Row]] = defaultdict(list)

    for row in source_rows:
        group_type = str(row["group_type"])
        group_name = str(row["group_name"])
        entity_row = eligible_entities.get((group_type, group_name))
        if entity_row is None:
            warnings.append(
                f"Missing V3 group entity for source group_type='{group_type}' group_name='{group_name}'"
            )
            source_rows_skipped += 1
            continue
        grouped_rows[(int(entity_row["entity_id"]), group_type)].append(row)
        source_rows_mapped += 1

    event_bucket: dict[str, dict[str, object]] = {}

    for (entity_id, _group_type), rows in grouped_rows.items():
        entity_row = next(
            row for row in eligible_entities.values() if int(row["entity_id"]) == entity_id
        )
        prior_structure: str | None = None
        prior_trend: str | None = None

        for row in rows:
            current_day = _normalize_date(str(row["ohlc_date"]))

            bos_type = str(row["latest_bos_event_type"]).strip() if row["latest_bos_event_type"] is not None else ""
            bos_date = str(row["latest_bos_event_date"]).strip() if row["latest_bos_event_date"] is not None else ""
            if bos_type and bos_date:
                bos_day = _normalize_date(bos_date)
                if bos_day <= signal_day and (threshold is None or bos_day >= threshold):
                    _append_event(
                        bucket=event_bucket,
                        run_row=run_row,
                        entity_row=entity_row,
                        event_date=bos_date,
                        event_type="BOS",
                        event_direction=_map_bos_direction(bos_type),
                        event_label=bos_type,
                        source_run_id=row["run_id"] or row["calc_version"],
                    )

            reset_reason = str(row["latest_reset_reason"]).strip() if row["latest_reset_reason"] is not None else ""
            reset_date = str(row["latest_reset_event_date"]).strip() if row["latest_reset_event_date"] is not None else ""
            if reset_reason and reset_date:
                reset_day = _normalize_date(reset_date)
                if reset_day <= signal_day and (threshold is None or reset_day >= threshold):
                    _append_event(
                        bucket=event_bucket,
                        run_row=run_row,
                        entity_row=entity_row,
                        event_date=reset_date,
                        event_type="RESET",
                        event_direction=_map_reset_direction(reset_reason),
                        event_label=reset_reason,
                        source_run_id=row["run_id"] or row["calc_version"],
                    )

            structure_label = (
                str(row["latest_structure_label"]).strip() if row["latest_structure_label"] is not None else ""
            )
            if prior_structure and structure_label and structure_label != prior_structure:
                _append_event(
                    bucket=event_bucket,
                    run_row=run_row,
                    entity_row=entity_row,
                    event_date=str(row["ohlc_date"]),
                    event_type="STRUCTURE_CHANGE",
                    event_direction="NONE",
                    event_label=f"{prior_structure} -> {structure_label}",
                    source_run_id=row["run_id"] or row["calc_version"],
                )
            if structure_label:
                prior_structure = structure_label

            trend = str(row["trend_classification"]).strip() if row["trend_classification"] is not None else ""
            if prior_trend and trend and trend != prior_trend:
                _append_event(
                    bucket=event_bucket,
                    run_row=run_row,
                    entity_row=entity_row,
                    event_date=str(row["ohlc_date"]),
                    event_type="TREND_STATE_CHANGE",
                    event_direction=_map_trend_direction(trend),
                    event_label=f"{prior_trend} -> {trend}",
                    source_run_id=row["run_id"] or row["calc_version"],
                )
            if trend:
                prior_trend = trend

    event_rows = sorted(
        event_bucket.values(),
        key=lambda row: (
            str(row["event_type"]),
            str(row["event_date"]),
            int(row["entity_id"]),
            str(row["event_key"]),
        ),
    )
    event_type_counts = Counter(str(row["event_type"]) for row in event_rows)
    event_direction_counts = Counter(str(row["event_direction"]) for row in event_rows)
    return (
        event_rows,
        dict(sorted(event_type_counts.items())),
        dict(sorted(event_direction_counts.items())),
        warnings,
        source_rows_mapped,
        source_rows_skipped,
        limitations,
    )


def _existing_event_count(
    conn: sqlite3.Connection,
    run_id: str,
    entity_ids: list[int],
) -> int:
    if not entity_ids:
        return 0
    placeholders = ", ".join("?" for _ in entity_ids)
    params: list[object] = [run_id, SOURCE_TABLE, *entity_ids]
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE run_id = ?
              AND source_table = ?
              AND entity_id IN ({placeholders})
            """,
            tuple(params),
        ).fetchone()[0]
    )


def _delete_existing_events(
    conn: sqlite3.Connection,
    run_id: str,
    entity_ids: list[int],
) -> None:
    if not entity_ids:
        return
    placeholders = ", ".join("?" for _ in entity_ids)
    params: list[object] = [run_id, SOURCE_TABLE, *entity_ids]
    conn.execute(
        f"""
        DELETE FROM eco_entity_event
        WHERE run_id = ?
          AND source_table = ?
          AND entity_id IN ({placeholders})
        """,
        tuple(params),
    )


def _insert_event_rows(conn: sqlite3.Connection, event_rows: list[dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date,
            event_type, source_table, source_run_id, source_event_id, event_key,
            event_label, event_direction, event_status, event_payload_ref
        ) VALUES (
            :run_id, :ecosystem_id, :taxonomy_version_id, :entity_id, :event_date,
            :event_type, :source_table, :source_run_id, :source_event_id, :event_key,
            :event_label, :event_direction, :event_status, :event_payload_ref
        )
        """,
        event_rows,
    )


def build_canonical_v3_group_structure_events(
    db_path: str,
    run_id: str,
    lookback_calendar_days: int | None = 120,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        eligible_entities = _load_eligible_group_entities(conn, str(run_row["run_id"]))
        entity_ids = sorted(int(row["entity_id"]) for row in eligible_entities.values())
        source_rows = _load_source_rows(
            conn,
            taxonomy_version_code=str(run_row["version_code"]),
            signal_date=str(run_row["signal_date"]),
            lookback_calendar_days=lookback_calendar_days,
        )
        existing_count = _existing_event_count(conn, str(run_row["run_id"]), entity_ids)
        if not replace_existing and existing_count > 0:
            raise ValueError(
                f"Group event rows already exist for run_id '{run_id}' and source_table '{SOURCE_TABLE}'"
            )

        (
            event_rows,
            event_type_counts,
            event_direction_counts,
            warnings,
            source_rows_mapped,
            source_rows_skipped,
            limitations,
        ) = _build_event_rows(
            run_row=run_row,
            source_rows=source_rows,
            eligible_entities=eligible_entities,
            lookback_calendar_days=lookback_calendar_days,
        )

        conn.execute("BEGIN")
        if replace_existing:
            _delete_existing_events(conn, str(run_row["run_id"]), entity_ids)
        _insert_event_rows(conn, event_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_code": str(run_row["ecosystem_code"]),
        "taxonomy_version_code": str(run_row["version_code"]),
        "signal_date": str(run_row["signal_date"]),
        "source_table": SOURCE_TABLE,
        "lookback_calendar_days": lookback_calendar_days,
        "eligible_group_entity_count": len(entity_ids),
        "source_rows_read": len(source_rows),
        "source_rows_mapped": source_rows_mapped,
        "source_rows_skipped": source_rows_skipped,
        "entity_events_inserted": len(event_rows),
        "event_type_counts": event_type_counts,
        "event_direction_counts": event_direction_counts,
        "warning_count": len(warnings),
        "warnings": warnings,
        "limitations": limitations,
    }
