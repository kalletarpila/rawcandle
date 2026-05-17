from __future__ import annotations

from run_datacenter_daily_signal_report import main as run_datacenter_daily_signal_report_main

from tests.test_datacenter_daily_swing_report import _seed_report_db


def test_cli_writes_markdown_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "daily_report.md"
    output_csv = tmp_path / "daily_report.csv"
    _seed_report_db(analysis_db)

    exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--top-n",
            "20",
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert output_md.exists()
    assert output_csv.exists()
    assert "# Datacenter Daily Swing Signal Report" in output_md.read_text(encoding="utf-8")

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2024-01-10"
    assert lines[1] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[2] == "SUMMARY ohlc_calc_version=DC_SWING_OHLC_V1"
    assert lines[3] == "SUMMARY group_rows=6"
    assert lines[4] == "SUMMARY ticker_rows=4"
    assert lines[5] == "SUMMARY synthetic_ohlc_rows=2"
    assert lines[6] == "SUMMARY breakout_count=1"
    assert lines[7] == "SUMMARY pullback_count=1"
    assert lines[8] == "SUMMARY exit_risk_count=1"
    assert lines[9] == f"SUMMARY output_markdown={output_md}"
    assert lines[10] == f"SUMMARY output_csv={output_csv}"
    assert lines[-1] == "SUMMARY validation_status=OK"
