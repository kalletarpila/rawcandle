from __future__ import annotations

from run_datacenter_weekly_swing_report import main as run_datacenter_weekly_swing_report_main

from tests.test_datacenter_weekly_swing_report import _seed_weekly_report_db


def test_cli_writes_markdown_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "weekly_report.md"
    output_csv = tmp_path / "weekly_report.csv"
    expected_output_md = tmp_path / "weekly_report_1200.md"
    expected_output_csv = tmp_path / "weekly_report_1200.csv"
    _seed_weekly_report_db(analysis_db)

    exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert expected_output_md.exists()
    assert expected_output_csv.exists()
    markdown = expected_output_md.read_text(encoding="utf-8")
    csv_text = expected_output_csv.read_text(encoding="utf-8")
    assert "# Datacenter Rolling Swing Report" in markdown
    assert "# Datacenter Weekly Swing Report" not in markdown
    assert "## Watchlist Summary" in markdown
    assert csv_text.startswith("section;value_1;")
    assert "0,02" in csv_text
    assert "Window summary;metric;value" in csv_text
    assert "Ecosystem window change;metric;first_value;last_value;change" in csv_text
    assert "| metric | value |" not in csv_text

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY end_date=2024-01-10"
    assert lines[1] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[2] == "SUMMARY ohlc_calc_version=DC_SWING_OHLC_V1"
    assert lines[3] == "SUMMARY taxonomy_version=DC_TAXONOMY_V1"
    assert lines[4] == "SUMMARY taxonomy_version_inferred=0"
    assert lines[5] == "SUMMARY window_size=5"
    assert lines[6] == "SUMMARY valid_signal_dates_count=5"
    assert lines[7] == "SUMMARY window_start_date=2024-01-02"
    assert lines[8] == "SUMMARY window_end_date=2024-01-10"
    assert lines[9] == "SUMMARY incomplete_window=NO"
    assert lines[10] == "SUMMARY group_rows=20"
    assert lines[11] == "SUMMARY ticker_rows=20"
    assert lines[12] == "SUMMARY synthetic_ohlc_rows=10"
    assert lines[13] == "SUMMARY repeated_breakout_tickers=1"
    assert lines[14] == "SUMMARY repeated_pullback_tickers=1"
    assert lines[15] == "SUMMARY repeated_exit_risk_tickers=1"
    assert lines[16] == f"SUMMARY output_markdown={expected_output_md}"
    assert lines[-1] == "SUMMARY validation_status=OK"


def test_cli_supports_custom_window_size_and_invalid_zero(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "weekly_report.md"
    output_csv = tmp_path / "weekly_report.csv"
    _seed_weekly_report_db(analysis_db)

    exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--window-size",
            "3",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY window_size=3" in lines
    assert "SUMMARY valid_signal_dates_count=3" in lines
    assert "SUMMARY window_start_date=2024-01-05" in lines

    invalid_exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--window-size",
            "0",
        ]
    )
    assert invalid_exit_code != 0


def test_cli_accepts_watchlist_file_and_renders_watchlist_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "weekly_report.md"
    output_csv = tmp_path / "weekly_report.csv"
    watchlist_file = tmp_path / "watchlist.txt"
    expected_output_md = tmp_path / "weekly_report_1200.md"
    _seed_weekly_report_db(analysis_db)
    watchlist_file.write_text("AAA\nOUTSIDE\n", encoding="utf-8")

    exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
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
    assert "current_watchlist_status" in markdown
    assert "window_watchlist_status" in markdown
    assert "NOT_PART_OF_DATACENTER_ECOSYSTEM" in markdown
