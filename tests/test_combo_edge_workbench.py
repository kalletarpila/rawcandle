from __future__ import annotations

import sqlite3
from datetime import date
from datetime import timedelta
from pathlib import Path

from analysis.combo_edge_workbench import run_pipeline


def _create_stock_db(path: Path, dates: list[str], closes: list[float]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                close REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO osakedata (osake, pvm, close) VALUES (?, ?, ?)",
            [("AAA", date_value, close_value) for date_value, close_value in zip(dates, closes)],
        )
        conn.commit()


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT,
                date TEXT,
                bullish_strength REAL,
                bearish_strength REAL,
                rsi REAL,
                is_bullish_divergence_r3 INTEGER,
                pivot_gap_r3 INTEGER,
                pivot_drop_pct_r3 REAL,
                pivot2_date_r3 TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE analysis_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                pattern TEXT,
                signal_strength REAL,
                rsi14 REAL,
                candle_pattern INTEGER,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength, rsi,
                is_bullish_divergence_r3, pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2024-01-11", 1.2, 0.0, 30.0, 1, 13, 8.5, "2024-01-08"),
        )
        conn.executemany(
            """
            INSERT INTO analysis_findings (
                ticker, date, pattern, signal_strength, rsi14, candle_pattern, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-11", "Bullish Divergence", 1.2, 30.0, 0, "2026-03-20"),
                ("AAA", "2024-01-09", "BullDiv & Hammer", 0.9, 31.0, 1, "2026-03-20"),
            ],
        )
        conn.commit()


def test_run_pipeline_builds_workbench_and_reports(tmp_path: Path) -> None:
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    workbench_db = tmp_path / "combo_edge_workbench.db"
    area_csv = tmp_path / "combo_edge_area_summary.csv"
    tree_report = tmp_path / "combo_edge_tree_rules.txt"

    start = date(2024, 1, 1)
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(70)]
    closes = [100.0 + (offset * 2.0) for offset in range(70)]
    _create_stock_db(stock_db, dates, closes)
    _create_analysis_db(analysis_db)

    stats = run_pipeline(
        analysis_db_path=analysis_db,
        stock_db_path=stock_db,
        workbench_db_path=workbench_db,
        area_summary_csv_path=area_csv,
        tree_report_path=tree_report,
    )

    assert stats["source_findings"] == 2
    assert stats["inserted_rows"] == 2
    assert stats["summary_rows"] >= 1
    assert area_csv.exists()
    assert tree_report.exists()

    with sqlite3.connect(workbench_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT case_kind, source_pattern, finding_date, linked_event_date,
                   combo_offset, pivot_gap_r3, pivot_drop_pct_r3, winsor_ret_30, winsor_ret_40
            FROM edge_cases
            ORDER BY source_pattern, finding_date
            """
        ).fetchall()
        assert len(rows) == 2

        combo_row = next(row for row in rows if row["source_pattern"] == "BullDiv & Hammer")
        assert combo_row["linked_event_date"] == "2024-01-11"
        assert combo_row["combo_offset"] == 1
        assert combo_row["pivot_gap_r3"] == 13
        assert combo_row["pivot_drop_pct_r3"] == 8.5
        assert combo_row["winsor_ret_30"] is not None
        assert combo_row["winsor_ret_40"] is not None

        bull_div_row = next(row for row in rows if row["source_pattern"] == "Bullish Divergence")
        assert bull_div_row["linked_event_date"] == "2024-01-11"
        assert bull_div_row["combo_offset"] is None
        assert bull_div_row["winsor_ret_40"] is not None

        summary = conn.execute(
            """
            SELECT source_pattern, rsi_scope, gap_bin, drop_bin, n
            FROM edge_area_summary
            WHERE source_pattern = 'Bullish Divergence'
            """
        ).fetchall()
        assert summary
        assert summary[0]["gap_bin"] == "11-14"
        assert summary[0]["drop_bin"] == ">7"
