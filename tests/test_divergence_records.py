from __future__ import annotations

import sqlite3
from pathlib import Path

from analysis.database_manager import DatabaseManager


def test_get_divergence_records_from_divergence_data_only(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    dbm = DatabaseManager(db_path=db_path)
    dbm.save_divergence_batch(
        "AAA",
        [
            ("2025-01-01", 2.5, 0.0, 55.0, 1, 0),
            ("2025-01-02", 0.0, 1.5, 45.0, 0, 1),
        ],
    )

    records = dbm.get_divergence_records("AAA", ["2025-01-01", "2025-01-02"])
    assert records["2025-01-01"]["bullish_strength"] == 2.5
    assert records["2025-01-02"]["bearish_strength"] == 1.5
    assert records["2025-01-01"]["rsi"] == 55.0

    # Ensure fallback to zeros for missing
    records_missing = dbm.get_divergence_records("AAA", ["2025-01-03"])
    assert records_missing == {}
