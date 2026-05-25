from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_build import main


def _write_report(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_structured_input_json(path: Path, *, report_date: str = "2026-05-22") -> Path:
    payload = {
        "ecosystem_code": "DATACENTER",
        "report_date": report_date,
        "readiness": "READY",
        "total_parsed_rows": 1,
        "total_parse_warnings": 0,
        "source_reports": [
            {
                "source_report_path": "structured://test",
                "source_report_type": "structured",
                "source_report_date": report_date,
                "loaded_row_count": 1,
                "status": "OK",
            }
        ],
        "action_summary": [],
        "market_map": [],
        "watchlist": [],
        "tickers": [],
        "decision_trace": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
    assert captured["input_mode"] == "reports"
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


def test_wrapper_forwards_render_html_and_html_output(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    html_output = tmp_path / "dashboard.html"
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status\nNVDA;SELL\n",
    )
    captured_build: dict[str, object] = {}
    captured_render: dict[str, object] = {}

    def fake_generate(**kwargs):
        captured_build.update(kwargs)
        return (
            "RUN_HTML",
            (
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RUN_HTML",
            ),
        )

    def fake_render(**kwargs):
        captured_render.update(kwargs)
        Path(kwargs["output"]).write_text("RUN_HTML NVDA", encoding="utf-8")
        return object()

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_build.generate_ecosystem_dashboard_build",
        fake_generate,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_build.generate_datacenter_dashboard_html_file",
        fake_render,
    )

    exit_code = main(
        [
            "--dashboard-db",
            str(tmp_path / "ecosystem_dashboard.db"),
            "--reports-dir",
            str(reports_dir),
            "--report-date",
            "2026-05-22",
            "--render-html",
            "--html-output",
            str(html_output),
        ]
    )

    assert exit_code == 0
    assert captured_build["ecosystem_code"] == "DATACENTER"
    assert captured_build["input_mode"] == "reports"
    assert captured_render == {
        "dashboard_db": str(tmp_path / "ecosystem_dashboard.db"),
        "ecosystem_code": "DATACENTER",
        "run_id": "RUN_HTML",
        "output": str(html_output),
        "report_date": None,
        "title": None,
    }
    output = capsys.readouterr().out
    assert "SUMMARY ecosystem_dashboard_build.render_html_requested=1" in output
    assert f"SUMMARY ecosystem_dashboard_build.html_output_path={html_output}" in output
    assert "SUMMARY ecosystem_dashboard_build.html_render_status=OK" in output


def test_wrapper_forwards_explicit_input_mode_reports(tmp_path, monkeypatch, capsys):
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
            "RUN_MODE",
            (
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RUN_MODE",
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
            "--input-mode",
            "reports",
        ]
    )

    assert exit_code == 0
    assert captured["input_mode"] == "reports"


def test_wrapper_forwards_structured_mode_and_structured_input_json(
    tmp_path, monkeypatch
):
    structured_json = _write_structured_input_json(tmp_path / "dashboard_input.json")
    captured: dict[str, object] = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return (
            "RUN_STRUCTURED",
            (
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RUN_STRUCTURED",
            ),
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_build.generate_ecosystem_dashboard_build",
        fake_generate,
    )

    exit_code = main(
        [
            "--dashboard-db",
            str(tmp_path / "ecosystem_dashboard.db"),
            "--report-date",
            "2026-05-22",
            "--input-mode",
            "structured",
            "--structured-input-json",
            str(structured_json),
        ]
    )

    assert exit_code == 0
    assert captured["ecosystem_code"] == "DATACENTER"
    assert captured["input_mode"] == "structured"
    assert captured["structured_input_json"] == str(structured_json)
    assert captured["reports_dir"] is None
