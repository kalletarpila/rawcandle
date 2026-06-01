from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter


SOURCE_TABLE = "stock_dow_structure_events"


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


def _load_ticker_entities(conn: sqlite3.Connection, ecosystem_id: int) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT entity_id, entity_code
        FROM eco_entity
        WHERE ecosystem_id = ? AND entity_type = 'TICKER'
        """,
        (ecosystem_id,),
    ).fetchall()
    return {str(row["entity_code"]): row for row in rows}


def _normalize_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    lookback_calendar_days: int | None,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    rows = conn.execute(
        f"""
        SELECT
            id,
            ticker,
            event_date,
            confirmed_as_of_date,
            event_type,
            trend_state,
            break_signal,
            reset_reason,
            structure_epoch_id,
            run_id
        FROM {SOURCE_TABLE}
        WHERE confirmed_as_of_date <= ?
        ORDER BY event_date, ticker, id
        """,
        (signal_date,),
    ).fetchall()
    signal_day = _normalize_date(signal_date)
    if lookback_calendar_days is None:
        return rows
    threshold = signal_day - dt.timedelta(days=lookback_calendar_days)
    filtered: list[sqlite3.Row] = []
    for row in rows:
        event_day = _normalize_date(str(row["event_date"]))
        if event_day >= threshold and event_day <= signal_day:
            filtered.append(row)
    return filtered


def _map_event_type(source_row: sqlite3.Row, warnings: list[str]) -> str:
    reset_reason = str(source_row["reset_reason"]).strip() if source_row["reset_reason"] is not None else ""
    event_type = str(source_row["event_type"]).strip().upper()
    break_signal = str(source_row["break_signal"]).strip().upper() if source_row["break_signal"] is not None else ""

    # RESET wins when the row explicitly represents a reset semantics.
    if reset_reason:
        return "RESET"
    if event_type in {"BOS_UP", "BOS_DOWN", "DOUBLE_BOS_UP", "DOUBLE_BOS_DOWN"}:
        return "BOS"
    if break_signal in {"BOS_UP", "BOS_DOWN", "DOUBLE_BOS_UP", "DOUBLE_BOS_DOWN", "UP", "DOWN"}:
        return "BOS"
    if event_type in {"TREND_CHANGE", "TREND_STATE_CHANGE"}:
        return "TREND_STATE_CHANGE"
    if event_type in {"STRUCTURE_CHANGE", "STRUCTURE_SHIFT"}:
        return "STRUCTURE_CHANGE"
    warnings.append(f"Unknown source event_type '{event_type}' mapped to UNKNOWN")
    return "UNKNOWN"


def _map_event_direction(source_row: sqlite3.Row) -> str:
    event_type = str(source_row["event_type"]).strip().upper()
    break_signal = str(source_row["break_signal"]).strip().upper() if source_row["break_signal"] is not None else ""
    trend_state = str(source_row["trend_state"]).strip().upper() if source_row["trend_state"] is not None else ""

    if source_row["reset_reason"] is not None and str(source_row["reset_reason"]).strip():
        return "NONE"
    if event_type in {"BOS_UP", "DOUBLE_BOS_UP"} or break_signal in {"BOS_UP", "DOUBLE_BOS_UP", "UP"}:
        return "UP"
    if event_type in {"BOS_DOWN", "DOUBLE_BOS_DOWN"} or break_signal in {"BOS_DOWN", "DOUBLE_BOS_DOWN", "DOWN"}:
        return "DOWN"
    if "BULLISH" in event_type or "BULLISH" in break_signal:
        return "BULLISH"
    if "BEARISH" in event_type or "BEARISH" in break_signal:
        return "BEARISH"
    if trend_state in {"UP", "DOWN", "NEUTRAL", "MIXED"}:
        return trend_state
    return "UNKNOWN"


def _build_event_label(source_row: sqlite3.Row) -> str:
    parts: list[str] = []
    if source_row["event_type"] is not None and str(source_row["event_type"]).strip():
        parts.append(str(source_row["event_type"]).strip())
    if source_row["break_signal"] is not None and str(source_row["break_signal"]).strip():
        parts.append(str(source_row["break_signal"]).strip())
    if source_row["reset_reason"] is not None and str(source_row["reset_reason"]).strip():
        parts.append(str(source_row["reset_reason"]).strip())
    return " | ".join(parts) if parts else "UNKNOWN"


def _build_event_key(source_row: sqlite3.Row, mapped_event_type: str) -> str:
    if source_row["id"] is not None:
        return f"{SOURCE_TABLE}:{source_row['id']}"
    reset_reason = str(source_row["reset_reason"]).strip() if source_row["reset_reason"] is not None else ""
    break_signal = str(source_row["break_signal"]).strip() if source_row["break_signal"] is not None else ""
    return (
        f"{SOURCE_TABLE}|{source_row['ticker']}|{source_row['event_date']}|{mapped_event_type}|"
        f"{break_signal}|{reset_reason}|{source_row['structure_epoch_id']}"
    )


def _build_rows(
    *,
    run_row: sqlite3.Row,
    source_rows: list[sqlite3.Row],
    ticker_entities: dict[str, sqlite3.Row],
) -> tuple[list[dict[str, object]], dict[str, int], dict[str, int], list[str], int]:
    event_rows: list[dict[str, object]] = []
    event_type_counts: Counter[str] = Counter()
    event_direction_counts: Counter[str] = Counter()
    warnings: list[str] = []
    source_rows_skipped = 0
    seen_grains: set[tuple[object, ...]] = set()

    for source_row in source_rows:
        ticker = str(source_row["ticker"])
        entity_row = ticker_entities.get(ticker)
        if entity_row is None:
            warnings.append(f"Missing V3 ticker entity for source ticker '{ticker}'")
            source_rows_skipped += 1
            continue

        type_warnings: list[str] = []
        mapped_event_type = _map_event_type(source_row, type_warnings)
        warnings.extend(type_warnings)
        event_direction = _map_event_direction(source_row)
        event_key = _build_event_key(source_row, mapped_event_type)
        event_date = str(source_row["event_date"])
        grain = (
            str(run_row["run_id"]),
            int(run_row["taxonomy_version_id"]),
            int(entity_row["entity_id"]),
            event_date,
            mapped_event_type,
            event_key,
        )
        if grain in seen_grains:
            warnings.append(f"Duplicate event grain skipped for ticker '{ticker}' and event_key '{event_key}'")
            source_rows_skipped += 1
            continue
        seen_grains.add(grain)

        event_rows.append(
            {
                "run_id": str(run_row["run_id"]),
                "ecosystem_id": int(run_row["ecosystem_id"]),
                "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
                "entity_id": int(entity_row["entity_id"]),
                "event_date": event_date,
                "event_type": mapped_event_type,
                "source_table": SOURCE_TABLE,
                "source_run_id": source_row["run_id"],
                "source_event_id": str(source_row["id"]) if source_row["id"] is not None else None,
                "event_key": event_key,
                "event_label": _build_event_label(source_row),
                "event_direction": event_direction,
                "event_status": "ACTIVE",
                "event_payload_ref": None,
            }
        )
        event_type_counts[mapped_event_type] += 1
        event_direction_counts[event_direction] += 1

    return (
        event_rows,
        dict(sorted(event_type_counts.items())),
        dict(sorted(event_direction_counts.items())),
        warnings,
        source_rows_skipped,
    )


def _existing_event_count(conn: sqlite3.Connection, run_id: str) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_entity_event
            WHERE run_id = ? AND source_table = ?
            """,
            (run_id, SOURCE_TABLE),
        ).fetchone()[0]
    )


def _delete_existing_events(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute(
        """
        DELETE FROM eco_entity_event
        WHERE run_id = ? AND source_table = ?
        """,
        (run_id, SOURCE_TABLE),
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


def build_canonical_v3_ticker_structure_events(
    db_path: str,
    run_id: str,
    lookback_trading_days: int | None = None,
    lookback_calendar_days: int | None = 120,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        source_rows = _load_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            lookback_calendar_days=lookback_calendar_days,
        )
        ticker_entities = _load_ticker_entities(conn, int(run_row["ecosystem_id"]))
        existing_count = _existing_event_count(conn, str(run_row["run_id"]))
        if not replace_existing and existing_count > 0:
            raise ValueError(
                f"Entity event rows already exist for run_id '{run_id}' and source_table '{SOURCE_TABLE}'"
            )

        (
            event_rows,
            event_type_counts,
            event_direction_counts,
            warnings,
            source_rows_skipped,
        ) = _build_rows(
            run_row=run_row,
            source_rows=source_rows,
            ticker_entities=ticker_entities,
        )

        conn.execute("BEGIN")
        if replace_existing:
            _delete_existing_events(conn, str(run_row["run_id"]))
        _insert_event_rows(conn, event_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if lookback_trading_days is not None:
        warnings.append("lookback_trading_days ignored in this pilot; calendar lookback was used")

    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_code": str(run_row["ecosystem_code"]),
        "taxonomy_version_code": str(run_row["version_code"]),
        "signal_date": str(run_row["signal_date"]),
        "source_table": SOURCE_TABLE,
        "lookback_calendar_days": lookback_calendar_days,
        "lookback_trading_days": lookback_trading_days,
        "source_rows_read": len(source_rows),
        "source_rows_mapped": len(event_rows),
        "source_rows_skipped": source_rows_skipped,
        "entity_events_inserted": len(event_rows),
        "event_type_counts": event_type_counts,
        "event_direction_counts": event_direction_counts,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
