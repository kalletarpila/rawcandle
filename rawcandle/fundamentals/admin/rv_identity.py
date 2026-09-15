from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def active_relative_valuation_identity(analysis_db: Path) -> dict[str, Any]:
    resolved = analysis_db.resolve()
    empty = {
        "database_path": str(resolved),
        "active_model_fingerprint": None,
        "active_snapshot_id": None,
        "active_snapshot_activated_at_utc": None,
        "active_snapshot_as_of_date": None,
        "active_snapshot_created_at_utc": None,
        "active_snapshot_completed_at_utc": None,
        "active_result_fingerprint": None,
        "active_source_fingerprint": None,
        "active_physical_content_fingerprint": None,
        "active_snapshot_status": None,
        "reader": "relative_valuation_active_snapshot JOIN relative_valuation_snapshot BY snapshot_id",
    }
    with sqlite3.connect(f"file:{resolved}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name IN ('relative_valuation_active_snapshot','relative_valuation_snapshot')"
            )
        }
        if tables != {"relative_valuation_active_snapshot", "relative_valuation_snapshot"}:
            return empty
        row = conn.execute(
            """
            SELECT
                a.model_fingerprint AS active_model_fingerprint,
                a.snapshot_id AS active_snapshot_id,
                a.activated_at_utc AS active_snapshot_activated_at_utc,
                s.as_of_date AS active_snapshot_as_of_date,
                s.created_at_utc AS active_snapshot_created_at_utc,
                s.completed_at_utc AS active_snapshot_completed_at_utc,
                s.result_fingerprint AS active_result_fingerprint,
                s.source_fingerprint AS active_source_fingerprint,
                s.physical_content_fingerprint AS active_physical_content_fingerprint,
                s.status AS active_snapshot_status
            FROM relative_valuation_active_snapshot a
            LEFT JOIN relative_valuation_snapshot s USING(snapshot_id)
            ORDER BY a.model_fingerprint
            LIMIT 1
            """
        ).fetchone()
    return empty | {
        "active_model_fingerprint": row["active_model_fingerprint"] if row else None,
        "active_snapshot_id": row["active_snapshot_id"] if row else None,
        "active_snapshot_activated_at_utc": row["active_snapshot_activated_at_utc"] if row else None,
        "active_snapshot_as_of_date": row["active_snapshot_as_of_date"] if row else None,
        "active_snapshot_created_at_utc": row["active_snapshot_created_at_utc"] if row else None,
        "active_snapshot_completed_at_utc": row["active_snapshot_completed_at_utc"] if row else None,
        "active_result_fingerprint": row["active_result_fingerprint"] if row else None,
        "active_source_fingerprint": row["active_source_fingerprint"] if row else None,
        "active_physical_content_fingerprint": row["active_physical_content_fingerprint"] if row else None,
        "active_snapshot_status": row["active_snapshot_status"] if row else None,
    }
