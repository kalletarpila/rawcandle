from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analysis import backfill_t0_alin_minus_close as backfill


def _build_results_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE results_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                t0_alin REAL,
                t0_alinMiinusClose REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO results_data (t0_alin, t0_alinMiinusClose) VALUES (?, ?)",
            [
                (105.0, None),   # needs update -> 5.0
                (100.0, 0.0),    # already correct -> skip
                (98.0, -1.0),    # incorrect -> update to -2.0
                (None, None),    # missing source -> skip
            ],
        )
    return db_path


def test_compute_t0_alin_minus_close_handles_values():
    assert backfill.compute_t0_alin_minus_close(101.0) == 1.0
    assert backfill.compute_t0_alin_minus_close(99) == -1.0
    assert backfill.compute_t0_alin_minus_close(None) is None
    assert backfill.compute_t0_alin_minus_close("bad") is None


def test_build_updates_only_for_missing_or_different(tmp_path: Path):
    db_path = _build_results_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = backfill.fetch_rows(conn)
        updates = backfill.build_updates(rows)
    assert len(updates) == 2
    values_by_id = {u.row_id: u.value for u in updates}
    assert pytest.approx(values_by_id[1]) == 5.0
    assert pytest.approx(values_by_id[3]) == -2.0


def test_backfill_applies_updates(tmp_path: Path):
    db_path = _build_results_db(tmp_path)
    updated = backfill.backfill(db_path, apply=True)
    assert updated == 2

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT t0_alin, t0_alinMiinusClose FROM results_data ORDER BY id"
        ).fetchall()
    assert rows[0][1] == pytest.approx(5.0)   # None -> computed
    assert rows[1][1] == pytest.approx(0.0)   # unchanged
    assert rows[2][1] == pytest.approx(-2.0)  # corrected
    assert rows[3][1] is None                 # missing source stays None
