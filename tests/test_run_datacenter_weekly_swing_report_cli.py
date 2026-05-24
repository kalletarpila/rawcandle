from __future__ import annotations

import sqlite3

from rawcandle.technical_signal_relevance import TechnicalSignalRelevanceConfig
from rawcandle.technical_signal_relevance_persistence import (
    TechnicalSignalRelevanceStoredRow,
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    insert_relevance_records,
    insert_relevance_run,
)
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
    assert "## Datacenter Taxonomy Listing" in markdown
    assert "row_type" in markdown
    assert "| LAYER |" in markdown
    assert "| SUBINDUSTRY |" in markdown
    assert "| TICKER |" in markdown
    assert "watchlist_subindustry_context_risk_count" in markdown
    assert "watchlist_layer_context_risk_count" in markdown
    assert "watchlist_both_context_risk_count" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    assert "last_subindustry_trend_classification" in markdown
    assert "last_subindustry_latest_structure_label" in markdown
    assert "last_layer_trend_classification" in markdown
    assert "last_layer_latest_structure_label" in markdown
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


def test_cli_can_omit_taxonomy_listing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "weekly_report.md"
    output_csv = tmp_path / "weekly_report.csv"
    expected_output_md = tmp_path / "weekly_report_1200.md"
    _seed_weekly_report_db(analysis_db)

    exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--no-taxonomy-listing",
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
    assert "## Datacenter Taxonomy Listing" not in markdown


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


def test_weekly_cli_window_20_remains_without_rolling_30_sections(tmp_path):
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
            "--window-size",
            "20",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert "Rolling 30 Buy Filter" not in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_30_buy_filter" not in expected_output_csv.read_text(encoding="utf-8")
    assert "Rolling 5 Pullback Alerts" not in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_5_pullback_alerts" not in expected_output_csv.read_text(encoding="utf-8")
    assert "Rolling 2 Sell Pressure" not in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_2_sell_pressure" not in expected_output_csv.read_text(encoding="utf-8")


def test_weekly_cli_window_30_can_render_rolling_30_sections(tmp_path):
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
            "--window-size",
            "30",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert "Rolling 30 Buy Filter" in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_30_buy_filter" in expected_output_csv.read_text(encoding="utf-8")
    assert "Rolling 5 Pullback Alerts" not in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_5_pullback_alerts" not in expected_output_csv.read_text(encoding="utf-8")


def test_weekly_cli_window_5_can_render_rolling_5_sections(tmp_path):
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
            "--window-size",
            "5",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert "Rolling 5 Pullback Alerts" in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_5_pullback_alerts" in expected_output_csv.read_text(encoding="utf-8")


def test_weekly_cli_window_2_can_render_rolling_2_sections(tmp_path):
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
            "--window-size",
            "2",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert "Rolling 2 Sell Pressure" in expected_output_md.read_text(encoding="utf-8")
    assert "section;rolling_2_sell_pressure" in expected_output_csv.read_text(encoding="utf-8")


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
    assert "last_subindustry_trend_classification" in markdown
    assert "last_subindustry_latest_structure_label" in markdown
    assert "last_layer_trend_classification" in markdown
    assert "last_layer_latest_structure_label" in markdown
    assert "NOT_PART_OF_DATACENTER_ECOSYSTEM" in markdown


def test_cli_can_include_technical_relevance_context_section(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "weekly_report.md"
    output_csv = tmp_path / "weekly_report.csv"
    expected_output_csv = tmp_path / "weekly_report_1200.csv"
    _seed_weekly_report_db(analysis_db)

    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id="REL_WEEKLY_CLI",
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-17T12:00:00Z",
        ),
    )
    insert_relevance_records(
        conn,
        [
            TechnicalSignalRelevanceStoredRow(
                ticker="AAA",
                timeframe="1d",
                signal_date="2024-01-05",
                signal_confirmed_as_of_date="2024-01-05",
                signal_name="Hammer",
                signal_close_price=100.0,
                signal_direction="BULLISH",
                signal_family="REVERSAL_MEDIUM",
                signal_source_type="CANDLE",
                signal_source_id="CANDLE",
                dow_trend_state="UP",
                dow_context_state="NORMAL",
                latest_bos_direction="BOS_UP",
                bars_since_latest_bos=2,
                latest_reset_reason="RESET",
                bars_since_latest_reset=5,
                near_latest_pivot=1,
                near_active_bos_level=0,
                is_trend_aligned=1,
                is_counter_trend=0,
                relevance_class="RELEVANT",
                relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
                relevance_rule_version="TECH_SIGNAL_RELEVANCE_V1",
                mapping_version="TECH_SIGNAL_MAPPING_V1",
                reason_version="TECH_SIGNAL_RELEVANCE_REASON_V1",
                rule_trace='["missing_bar_index=false"]',
                created_at_utc="2026-05-17T12:00:00Z",
                run_id="REL_WEEKLY_CLI",
            )
        ],
    )
    conn.commit()
    conn.close()

    exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--technical-relevance-run-id",
            "REL_WEEKLY_CLI",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    csv_text = expected_output_csv.read_text(encoding="utf-8")
    assert "section;technical_relevance_context" in csv_text
    assert ";AAA;1d;2024-01-05;2024-01-05;Hammer;CANDLE;RELEVANT;" in csv_text
