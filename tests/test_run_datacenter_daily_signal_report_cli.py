from __future__ import annotations

from run_datacenter_daily_signal_report import main as run_datacenter_daily_signal_report_main

from tests.test_datacenter_daily_swing_report import _seed_report_db


def test_cli_writes_markdown_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "daily_report.md"
    output_csv = tmp_path / "daily_report.csv"
    expected_output_md = tmp_path / "daily_report_1200.md"
    expected_output_csv = tmp_path / "daily_report_1200.csv"
    _seed_report_db(analysis_db)

    exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
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
    assert expected_output_md.exists()
    assert expected_output_csv.exists()
    markdown = expected_output_md.read_text(encoding="utf-8")
    assert "# Datacenter Daily Swing Signal Report" in markdown
    assert "## Watchlist Summary" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    csv_text = expected_output_csv.read_text(encoding="utf-8")
    assert csv_text.startswith("section;value_1;")
    assert "0,0476" in csv_text
    assert "Dashboard;metric;value" in csv_text
    assert "Data Quality;scope;group_type;status;count" in csv_text
    assert "| metric | value |" not in csv_text

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2024-01-10"
    assert lines[1] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[2] == "SUMMARY ohlc_calc_version=DC_SWING_OHLC_V1"
    assert lines[3] == "SUMMARY taxonomy_version=DC_TAXONOMY_V1"
    assert lines[4] == "SUMMARY taxonomy_version_inferred=0"
    assert lines[5] == "SUMMARY group_rows=6"
    assert lines[6] == "SUMMARY ticker_rows=4"
    assert lines[7] == "SUMMARY synthetic_ohlc_rows=2"
    assert lines[8] == "SUMMARY breakout_count=1"
    assert lines[9] == "SUMMARY pullback_count=1"
    assert lines[10] == "SUMMARY exit_risk_count=1"
    assert lines[11] == f"SUMMARY output_markdown={expected_output_md}"
    assert lines[12] == f"SUMMARY output_csv={expected_output_csv}"
    assert lines[-1] == "SUMMARY validation_status=OK"


def test_cli_accepts_watchlist_file_and_renders_watchlist_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "daily_report.md"
    output_csv = tmp_path / "daily_report.csv"
    watchlist_file = tmp_path / "watchlist.txt"
    expected_output_md = tmp_path / "daily_report_1200.md"
    _seed_report_db(analysis_db)
    watchlist_file.write_text("AAA\nOUTSIDE\n", encoding="utf-8")

    exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--watchlist-file",
            str(watchlist_file),
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    markdown = expected_output_md.read_text(encoding="utf-8")
    assert "## Watchlist Summary" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    assert "NOT_PART_OF_DATACENTER_ECOSYSTEM" in markdown
