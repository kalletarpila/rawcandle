from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_build import main


def _write_report(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _table_exists(db_path: Path, table: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table,),
        ).fetchone()
    return row is not None


def test_wrapper_maps_to_datacenter_and_default_dashboard_db(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status\nNVDA;SELL\n",
    )
    captured: dict[str, object] = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return (
            "RUN_X",
            (
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RUN_X",
            ),
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_build.generate_ecosystem_dashboard_build",
        fake_generate,
    )

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 0
    assert captured["ecosystem_code"] == "DATACENTER"
    assert captured["dashboard_db"] == "/home/kalle/projects/rawcandle/data/ecosystem_dashboard.db"
    assert capsys.readouterr().out.strip().splitlines() == [
        "SUMMARY ecosystem_dashboard_build.status=OK",
        "SUMMARY ecosystem_dashboard_build.run_id=RUN_X",
    ]


def test_wrapper_accepts_deprecated_analysis_db_and_does_not_create_dc_tables(
    tmp_path, capsys
):
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(
        [
            "--dashboard-db",
            str(dashboard_db),
            "--analysis-db",
            str(tmp_path / "analysis.db"),
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert (
        "WARNING --analysis-db is deprecated for dashboard build; use --dashboard-db"
        in output
    )
    assert _table_exists(dashboard_db, "ecosystem_dashboard_runs")
    assert not _table_exists(dashboard_db, "dc_dashboard_runs")
