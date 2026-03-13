import sqlite3
from pathlib import Path

import pytest

from analysis import run_analysis as run_analysis_module
from analysis.run_analysis import run_candlestick_analysis
from analysis.database_manager import DatabaseManager


def _create_stock_db(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            market TEXT NOT NULL DEFAULT 'usa'
        )
        """
    )
    rows = [
        ("TEST", "2024-01-04", 100.0, 102.0, 95.0, 98.0, 10000),
        # Hammer 2024-01-05
        ("TEST", "2024-01-05", 99.5, 100.8, 90.0, 100.5, 12000),
        ("TEST", "2024-01-06", 101.0, 103.0, 99.0, 102.5, 11000),
    ]
    cursor.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _create_analysis_db_with_bull_div(db_path: Path) -> str:
    db_manager = DatabaseManager(str(db_path))
    db_manager.save_divergence_batch(
        "TEST",
        [
            (
                "2024-01-05",
                2.0,  # bullish_strength > 0
                0.0,
                40.0,
            )
        ],
    )
    db_manager.close()
    return str(db_path)


def test_bull_div_combo_replaces_base_pattern(tmp_path: Path):
    stock_db = _create_stock_db(tmp_path / "stock.db")
    analysis_db = _create_analysis_db_with_bull_div(tmp_path / "analysis.db")

    results = run_candlestick_analysis(
        db_path=stock_db,
        ticker="TEST",
        patterns=["Hammer"],
        analysis_db_path=analysis_db,
    )

    key = "TEST|2024-01-05"
    assert key in results
    patterns = {item["pattern"] for item in results[key]}
    assert "BullDiv & Hammer" in patterns
    assert "Hammer" not in patterns


def test_combo_prefers_lowest_code_and_keeps_other_patterns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    stock_db = _create_stock_db(tmp_path / "stock2.db")
    analysis_db = _create_analysis_db_with_bull_div(tmp_path / "analysis2.db")

    # Pakota kaksi erillistä kynttilähavaintoa samalle päivälle
    monkeypatch.setattr(run_analysis_module, "is_hammer", lambda _row: True)
    monkeypatch.setattr(run_analysis_module, "is_dragonfly_doji", lambda _row: True)

    results = run_candlestick_analysis(
        db_path=stock_db,
        ticker="TEST",
        patterns=["Hammer", "Dragonfly Doji"],
        analysis_db_path=analysis_db,
    )

    key = "TEST|2024-01-05"
    assert key in results
    patterns = [item["pattern"] for item in results[key]]

    assert "BullDiv & Hammer" in patterns
    assert "Hammer" not in patterns
    # Dragonfly Doji jää peruskuvioksi koska Hammer on prioriteetissa pienempi
    assert "Dragonfly Doji" in patterns
