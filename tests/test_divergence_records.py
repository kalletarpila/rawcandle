from __future__ import annotations

import sqlite3
from pathlib import Path

from analysis.database_manager import DatabaseManager


def test_get_divergence_records_from_analysis_findings(tmp_path: Path):
    db_path = tmp_path / "analysis.db"
    dbm = DatabaseManager(db_path=db_path)
    dbm.save_finding(
        ticker="AAA",
        date="2025-01-01",
        pattern="Bullish Divergence",
        signal_strength=2.5,
        rsi14=55.0,
    )
    dbm.save_finding(
        ticker="AAA",
        date="2025-01-02",
        pattern="Bearish Divergence",
        signal_strength=1.5,
        rsi14=45.0,
    )

    records = dbm.get_divergence_records("AAA", ["2025-01-01", "2025-01-02"])
    assert records["2025-01-01"]["bullish_strength"] == 2.5
    assert records["2025-01-02"]["bearish_strength"] == 1.5
    assert records["2025-01-01"]["rsi"] == 55.0

    # Ensure fallback to zeros for missing
    records_missing = dbm.get_divergence_records("AAA", ["2025-01-03"])
    assert records_missing == {}
