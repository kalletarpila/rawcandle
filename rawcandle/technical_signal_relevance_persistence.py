from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .technical_signal_relevance import (
    TechnicalSignalRelevanceConfig,
    TechnicalSignalRelevanceRecord,
)


CREATED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MIGRATION_SQL_PATH = (
    Path(__file__).resolve().parent
    / "sqlite"
    / "migrations"
    / "001_create_technical_signal_relevance.sql"
)


@dataclass(frozen=True)
class TechnicalSignalRelevanceRunRow:
    run_id: str
    relevance_rule_version: str
    mapping_version: str
    reason_version: str
    config_snapshot_json: str
    created_at_utc: str


@dataclass(frozen=True)
class TechnicalSignalRelevanceStoredRow:
    ticker: str
    timeframe: str
    signal_date: str
    signal_confirmed_as_of_date: str
    signal_name: str
    signal_close_price: float | None
    signal_direction: str | None
    signal_family: str | None
    signal_source_type: str | None
    signal_source_id: str | None
    dow_trend_state: str | None
    dow_context_state: str | None
    latest_bos_direction: str | None
    bars_since_latest_bos: int | None
    latest_reset_reason: str | None
    bars_since_latest_reset: int | None
    near_latest_pivot: int
    near_active_bos_level: int
    is_trend_aligned: int
    is_counter_trend: int
    relevance_class: str
    relevance_reason: str
    relevance_rule_version: str
    mapping_version: str
    reason_version: str
    rule_trace: str | None
    created_at_utc: str
    run_id: str


def _validate_created_at_utc(value: str) -> str:
    if not CREATED_AT_UTC_RE.match(value):
        raise ValueError(
            f"Invalid created_at_utc: {value}. Expected YYYY-MM-DDTHH:MM:SSZ"
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(
            f"Invalid created_at_utc: {value}. Expected YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return value


def resolve_created_at_utc(created_at_utc: str | None = None) -> str:
    if created_at_utc is not None:
        return _validate_created_at_utc(created_at_utc)
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def serialize_rule_trace(rule_trace: tuple[str, ...] | list[str] | None) -> str | None:
    if rule_trace is None:
        return None
    return json.dumps(list(rule_trace), ensure_ascii=True, separators=(",", ":"))


def apply_technical_signal_relevance_migration(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(MIGRATION_SQL_PATH.read_text(encoding="utf-8"))


def build_relevance_run_row(
    *,
    run_id: str,
    config: TechnicalSignalRelevanceConfig,
    created_at_utc: str | None = None,
) -> TechnicalSignalRelevanceRunRow:
    return TechnicalSignalRelevanceRunRow(
        run_id=run_id,
        relevance_rule_version=config.rule_version,
        mapping_version=config.mapping_version,
        reason_version=config.reason_version,
        config_snapshot_json=config.to_snapshot_json(),
        created_at_utc=resolve_created_at_utc(created_at_utc),
    )


def build_relevance_stored_row(
    record: TechnicalSignalRelevanceRecord,
    *,
    run_id: str,
    created_at_utc: str | None = None,
) -> TechnicalSignalRelevanceStoredRow:
    return TechnicalSignalRelevanceStoredRow(
        ticker=record.ticker,
        timeframe=record.timeframe,
        signal_date=record.signal_date,
        signal_confirmed_as_of_date=record.signal_confirmed_as_of_date,
        signal_name=record.signal_name,
        signal_close_price=record.signal_close_price,
        signal_direction=record.signal_direction,
        signal_family=record.signal_family,
        signal_source_type=record.signal_source_type,
        signal_source_id=record.signal_source_id,
        dow_trend_state=record.dow_trend_state,
        dow_context_state=record.dow_context_state,
        latest_bos_direction=record.latest_bos_direction,
        bars_since_latest_bos=record.bars_since_latest_bos,
        latest_reset_reason=record.latest_reset_reason,
        bars_since_latest_reset=record.bars_since_latest_reset,
        near_latest_pivot=int(record.near_latest_pivot),
        near_active_bos_level=int(record.near_active_bos_level),
        is_trend_aligned=int(record.is_trend_aligned),
        is_counter_trend=int(record.is_counter_trend),
        relevance_class=record.relevance_class,
        relevance_reason=record.relevance_reason,
        relevance_rule_version=record.relevance_rule_version,
        mapping_version=record.mapping_version,
        reason_version=record.reason_version,
        rule_trace=serialize_rule_trace(record.rule_trace),
        created_at_utc=resolve_created_at_utc(created_at_utc),
        run_id=run_id,
    )


def insert_relevance_run(
    conn: sqlite3.Connection,
    run_record: TechnicalSignalRelevanceRunRow,
) -> None:
    conn.execute(
        """
        INSERT INTO technical_signal_relevance_runs (
            run_id,
            relevance_rule_version,
            mapping_version,
            reason_version,
            config_snapshot_json,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_record.run_id,
            run_record.relevance_rule_version,
            run_record.mapping_version,
            run_record.reason_version,
            run_record.config_snapshot_json,
            run_record.created_at_utc,
        ),
    )


def insert_relevance_records(
    conn: sqlite3.Connection,
    records: Sequence[TechnicalSignalRelevanceStoredRow],
) -> None:
    conn.executemany(
        """
        INSERT INTO technical_signal_relevance (
            ticker,
            timeframe,
            signal_date,
            signal_confirmed_as_of_date,
            signal_name,
            signal_close_price,
            signal_direction,
            signal_family,
            signal_source_type,
            signal_source_id,
            dow_trend_state,
            dow_context_state,
            latest_bos_direction,
            bars_since_latest_bos,
            latest_reset_reason,
            bars_since_latest_reset,
            near_latest_pivot,
            near_active_bos_level,
            is_trend_aligned,
            is_counter_trend,
            relevance_class,
            relevance_reason,
            relevance_rule_version,
            mapping_version,
            reason_version,
            rule_trace,
            created_at_utc,
            run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.ticker,
                record.timeframe,
                record.signal_date,
                record.signal_confirmed_as_of_date,
                record.signal_name,
                record.signal_close_price,
                record.signal_direction,
                record.signal_family,
                record.signal_source_type,
                record.signal_source_id,
                record.dow_trend_state,
                record.dow_context_state,
                record.latest_bos_direction,
                record.bars_since_latest_bos,
                record.latest_reset_reason,
                record.bars_since_latest_reset,
                int(record.near_latest_pivot),
                int(record.near_active_bos_level),
                int(record.is_trend_aligned),
                int(record.is_counter_trend),
                record.relevance_class,
                record.relevance_reason,
                record.relevance_rule_version,
                record.mapping_version,
                record.reason_version,
                record.rule_trace,
                record.created_at_utc,
                record.run_id,
            )
            for record in records
        ],
    )


def _rows_to_dicts(cursor: sqlite3.Cursor, rows: Sequence[sqlite3.Row | tuple[object, ...]]) -> list[dict[str, object]]:
    columns = [str(column[0]) for column in cursor.description]
    return [
        {column: row[index] for index, column in enumerate(columns)}
        for row in rows
    ]


def read_relevance_run(
    conn: sqlite3.Connection,
    run_id: str,
) -> dict[str, object] | None:
    cursor = conn.execute(
        """
        SELECT
            run_id,
            relevance_rule_version,
            mapping_version,
            reason_version,
            config_snapshot_json,
            created_at_utc
        FROM technical_signal_relevance_runs
        WHERE run_id = ?
        """,
        (run_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    return _rows_to_dicts(cursor, rows)[0]


def read_relevance_records_for_run(
    conn: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, object]]:
    cursor = conn.execute(
        """
        SELECT
            ticker,
            timeframe,
            signal_date,
            signal_confirmed_as_of_date,
            signal_name,
            signal_close_price,
            signal_direction,
            signal_family,
            signal_source_type,
            signal_source_id,
            dow_trend_state,
            dow_context_state,
            latest_bos_direction,
            bars_since_latest_bos,
            latest_reset_reason,
            bars_since_latest_reset,
            near_latest_pivot,
            near_active_bos_level,
            is_trend_aligned,
            is_counter_trend,
            relevance_class,
            relevance_reason,
            relevance_rule_version,
            mapping_version,
            reason_version,
            rule_trace,
            created_at_utc,
            run_id
        FROM technical_signal_relevance
        WHERE run_id = ?
        ORDER BY ticker ASC, timeframe ASC, signal_date ASC, signal_name ASC
        """,
        (run_id,),
    )
    return _rows_to_dicts(cursor, cursor.fetchall())


__all__ = [
    "MIGRATION_SQL_PATH",
    "TechnicalSignalRelevanceRunRow",
    "TechnicalSignalRelevanceStoredRow",
    "apply_technical_signal_relevance_migration",
    "build_relevance_run_row",
    "build_relevance_stored_row",
    "insert_relevance_records",
    "insert_relevance_run",
    "read_relevance_records_for_run",
    "read_relevance_run",
    "resolve_created_at_utc",
    "serialize_rule_trace",
]
