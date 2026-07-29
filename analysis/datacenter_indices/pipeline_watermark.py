from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _normalize_dimension(value: str | None) -> str:
    return value or ""


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {str(key): row[key] for key in row.keys()}


def upsert_pipeline_watermark(
    *,
    analysis_db_path: Path,
    component_name: str,
    taxonomy_version: str,
    start_date: str,
    end_date: str,
    market: str | None = None,
    signal_version: str | None = None,
    calc_version: str | None = None,
    row_count: int | None = None,
    status: str = "OK",
    last_successful_run_id: str | None = None,
    last_successful_at_utc: str | None = None,
    notes: str | None = None,
    preserve_coverage_start: bool = False,
) -> dict[str, Any]:
    normalized_market = _normalize_dimension(market)
    normalized_signal_version = _normalize_dimension(signal_version)
    normalized_calc_version = _normalize_dimension(calc_version)
    timestamp = last_successful_at_utc or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO dc_pipeline_watermark (
                component_name,
                taxonomy_version,
                market,
                signal_version,
                calc_version,
                start_date,
                end_date,
                row_count,
                status,
                last_successful_run_id,
                last_successful_at_utc,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(component_name, taxonomy_version, market, signal_version, calc_version)
            DO UPDATE SET
                start_date = CASE
                    WHEN ?
                     AND dc_pipeline_watermark.status = 'OK'
                     AND excluded.status = 'OK'
                     AND excluded.start_date <= dc_pipeline_watermark.end_date
                     AND excluded.end_date >= dc_pipeline_watermark.start_date
                    THEN MIN(dc_pipeline_watermark.start_date, excluded.start_date)
                    ELSE excluded.start_date
                END,
                end_date = CASE
                    WHEN ?
                     AND dc_pipeline_watermark.status = 'OK'
                     AND excluded.status = 'OK'
                     AND excluded.start_date <= dc_pipeline_watermark.end_date
                     AND excluded.end_date >= dc_pipeline_watermark.start_date
                    THEN MAX(dc_pipeline_watermark.end_date, excluded.end_date)
                    ELSE excluded.end_date
                END,
                row_count = excluded.row_count,
                status = excluded.status,
                last_successful_run_id = excluded.last_successful_run_id,
                last_successful_at_utc = excluded.last_successful_at_utc,
                notes = excluded.notes
            """,
            (
                component_name,
                taxonomy_version,
                normalized_market,
                normalized_signal_version,
                normalized_calc_version,
                start_date,
                end_date,
                row_count,
                status,
                last_successful_run_id,
                timestamp,
                notes,
                1 if preserve_coverage_start else 0,
                1 if preserve_coverage_start else 0,
            ),
        )
        row = conn.execute(
            """
            SELECT *
            FROM dc_pipeline_watermark
            WHERE component_name = ?
              AND taxonomy_version = ?
              AND market = ?
              AND signal_version = ?
              AND calc_version = ?
            """,
            (
                component_name,
                taxonomy_version,
                normalized_market,
                normalized_signal_version,
                normalized_calc_version,
            ),
        ).fetchone()
    return _row_to_dict(row) or {}


def get_pipeline_watermark(
    *,
    analysis_db_path: Path,
    component_name: str,
    taxonomy_version: str,
    market: str | None = None,
    signal_version: str | None = None,
    calc_version: str | None = None,
) -> dict[str, Any] | None:
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM dc_pipeline_watermark
            WHERE component_name = ?
              AND taxonomy_version = ?
              AND market = ?
              AND signal_version = ?
              AND calc_version = ?
            """,
            (
                component_name,
                taxonomy_version,
                _normalize_dimension(market),
                _normalize_dimension(signal_version),
                _normalize_dimension(calc_version),
            ),
        ).fetchone()
    return _row_to_dict(row)


def list_pipeline_watermarks(
    *,
    analysis_db_path: Path,
    taxonomy_version: str | None = None,
    component_name: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT *
        FROM dc_pipeline_watermark
        WHERE 1 = 1
    """
    params: list[str] = []
    if taxonomy_version is not None:
        query += " AND taxonomy_version = ?"
        params.append(taxonomy_version)
    if component_name is not None:
        query += " AND component_name = ?"
        params.append(component_name)
    query += """
        ORDER BY component_name ASC, taxonomy_version ASC, market ASC, signal_version ASC, calc_version ASC
    """

    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_row_to_dict(row) or {} for row in rows]
