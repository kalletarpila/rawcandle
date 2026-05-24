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
from run_datacenter_rolling_swing_report import main as run_datacenter_rolling_swing_report_main
from run_datacenter_weekly_swing_report import main as run_datacenter_weekly_swing_report_main

from tests.test_datacenter_weekly_swing_report import _seed_weekly_report_db


def _parse_summary(output: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for line in output.splitlines():
        if not line.startswith("SUMMARY "):
            continue
        key, value = line[len("SUMMARY ") :].split("=", 1)
        summary[key] = value
    return summary


def test_rolling_cli_uses_default_rolling_output_names(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    monkeypatch.chdir(tmp_path)

    exit_code = run_datacenter_rolling_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--window-size",
            "30",
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    summary = _parse_summary(capsys.readouterr().out)
    expected_md = tmp_path / "datacenter_rolling_30_2024-01-10_1200_full.md"
    expected_csv = tmp_path / "datacenter_rolling_30_2024-01-10_1200_full.csv"
    assert exit_code == 0
    assert expected_md.exists()
    assert expected_csv.exists()
    assert summary["report_type"] == "rolling"
    assert summary["window_size"] == "30"
    assert summary["output_markdown"] == str(expected_md)
    assert summary["output_csv"] == str(expected_csv)
    assert summary["validation_status"] == "OK"
    assert "weekly" not in expected_md.name


def test_rolling_cli_respects_explicit_output_paths_using_weekly_timestamp_behavior(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "custom_2024-01-10.md"
    output_csv = tmp_path / "custom_2024-01-10.csv"
    expected_md = tmp_path / "custom_2024-01-10_1200.md"
    expected_csv = tmp_path / "custom_2024-01-10_1200.csv"
    _seed_weekly_report_db(analysis_db)

    exit_code = run_datacenter_rolling_swing_report_main(
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

    summary = _parse_summary(capsys.readouterr().out)
    assert exit_code == 0
    assert expected_md.exists()
    assert expected_csv.exists()
    assert summary["output_markdown"] == str(expected_md)
    assert summary["output_csv"] == str(expected_csv)


def test_rolling_cli_matches_weekly_report_content_for_same_window(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    rolling_md = tmp_path / "rolling_2024-01-10.md"
    rolling_csv = tmp_path / "rolling_2024-01-10.csv"
    weekly_md = tmp_path / "weekly_2024-01-10.md"
    weekly_csv = tmp_path / "weekly_2024-01-10.csv"
    expected_rolling_md = tmp_path / "rolling_2024-01-10_1200.md"
    expected_rolling_csv = tmp_path / "rolling_2024-01-10_1200.csv"
    expected_weekly_md = tmp_path / "weekly_2024-01-10_1200.md"
    expected_weekly_csv = tmp_path / "weekly_2024-01-10_1200.csv"
    _seed_weekly_report_db(analysis_db)

    rolling_exit = run_datacenter_rolling_swing_report_main(
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
            str(rolling_md),
            "--output-csv",
            str(rolling_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )
    weekly_exit = run_datacenter_weekly_swing_report_main(
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
            str(weekly_md),
            "--output-csv",
            str(weekly_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert rolling_exit == 0
    assert weekly_exit == 0
    assert expected_rolling_md.read_text(encoding="utf-8") == expected_weekly_md.read_text(encoding="utf-8")
    assert expected_rolling_csv.read_text(encoding="utf-8") == expected_weekly_csv.read_text(encoding="utf-8")


def test_rolling_cli_supports_technical_relevance_run_id(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    output_md = tmp_path / "rolling_rel_2024-01-10.md"
    output_csv = tmp_path / "rolling_rel_2024-01-10.csv"
    expected_csv = tmp_path / "rolling_rel_2024-01-10_1200.csv"
    _seed_weekly_report_db(analysis_db)

    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id="REL_ROLLING_CLI",
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
                run_id="REL_ROLLING_CLI",
            )
        ],
    )
    conn.commit()
    conn.close()

    exit_code = run_datacenter_rolling_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            "2024-01-10",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--technical-relevance-run-id",
            "REL_ROLLING_CLI",
            "--output-md",
            str(output_md),
            "--output-csv",
            str(output_csv),
            "--generated-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    csv_text = expected_csv.read_text(encoding="utf-8")
    assert "section;technical_relevance_context" in csv_text
    assert ";AAA;1d;2024-01-05;2024-01-05;Hammer;CANDLE;RELEVANT;" in csv_text
