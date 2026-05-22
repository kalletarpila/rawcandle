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
    assert "subindustry_trend_classification" in markdown
    assert "subindustry_latest_structure_label" in markdown
    assert "layer_trend_classification" in markdown
    assert "layer_latest_structure_label" in markdown
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


def test_cli_can_omit_taxonomy_listing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "daily_report.md"
    output_csv = tmp_path / "daily_report.csv"
    expected_output_md = tmp_path / "daily_report_1200.md"
    _seed_report_db(analysis_db)

    exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
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
    assert "watchlist_subindustry_context_risk_count" in markdown
    assert "watchlist_layer_context_risk_count" in markdown
    assert "watchlist_both_context_risk_count" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    assert "subindustry_trend_classification" in markdown
    assert "subindustry_latest_structure_label" in markdown
    assert "layer_trend_classification" in markdown
    assert "layer_latest_structure_label" in markdown
    assert "NOT_PART_OF_DATACENTER_ECOSYSTEM" in markdown


def test_cli_can_include_technical_relevance_context_section(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "daily_report.md"
    output_csv = tmp_path / "daily_report.csv"
    expected_output_csv = tmp_path / "daily_report_1200.csv"
    _seed_report_db(analysis_db)

    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id="REL_DAILY_CLI",
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
                signal_date="2024-01-10",
                signal_confirmed_as_of_date="2024-01-10",
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
                run_id="REL_DAILY_CLI",
            )
        ],
    )
    conn.commit()
    conn.close()

    exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--technical-relevance-run-id",
            "REL_DAILY_CLI",
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
    assert ";AAA;1d;2024-01-10;2024-01-10;Hammer;CANDLE;RELEVANT;" in csv_text
