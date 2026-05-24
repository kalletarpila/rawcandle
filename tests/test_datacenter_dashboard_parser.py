from __future__ import annotations

from pathlib import Path

from dev_tools.datacenter_dashboard_parser import (
    parse_datacenter_dashboard_file,
    parse_datacenter_dashboard_reports,
)
from dev_tools.datacenter_dashboard_support import DatacenterReportStatus


def test_parse_datacenter_dashboard_file_parses_simple_semicolon_table(tmp_path):
    report_path = tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "section;ticker;status;reason;distance_to_ema20;latest_structure_label",
                "rolling_30_buy_filter;NVDA;WATCH_ZONE;OK_SETUP;-1.5;HL",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="rolling 30d",
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.ticker == "NVDA"
    assert row.horizon == "rolling 30d"
    assert row.raw_status == "WATCH_ZONE"
    assert row.reason == "OK_SETUP"
    assert row.distance_to_ema20 == -1.5
    assert row.latest_structure_label == "HL"
    assert result.warnings == []


def test_parse_datacenter_dashboard_file_tolerates_missing_optional_columns(tmp_path):
    report_path = tmp_path / "datacenter_daily_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;status",
                "AVGO;SELL_TRIGGER",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="daily",
    )

    row = result.rows[0]
    assert row.ticker == "AVGO"
    assert row.raw_status == "SELL_TRIGGER"
    assert row.reason is None
    assert row.distance_to_ema20 is None


def test_parse_datacenter_dashboard_file_preserves_unknown_columns_in_raw_fields(tmp_path):
    report_path = tmp_path / "datacenter_rolling_5_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;status;custom_flag",
                "AMD;EARLY_PULLBACK;SPECIAL",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="rolling 5d",
    )

    assert result.rows[0].raw_fields["custom_flag"] == "SPECIAL"


def test_parse_datacenter_dashboard_file_skips_rows_without_ticker(tmp_path):
    report_path = tmp_path / "datacenter_rolling_2_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;status",
                ";WATCH_PRESSURE",
                "SMCI;SHARP_2D_DROP",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="rolling 2d",
    )

    assert [row.ticker for row in result.rows] == ["SMCI"]
    assert any("skipped without ticker" in warning for warning in result.warnings)


def test_parse_datacenter_dashboard_file_handles_malformed_lines_without_crashing(tmp_path):
    report_path = tmp_path / "datacenter_daily_2026-05-22_0000_full.md"
    report_path.write_text(
        "\n".join(
            [
                "Some prose header",
                "| ticker | status | reason |",
                "| --- | --- | --- |",
                "| LRCX | BUY_WATCH | mixed |",
                "|  | malformed | line |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="daily",
    )

    assert [row.ticker for row in result.rows] == ["LRCX"]
    assert len(result.warnings) == 1


def test_parse_datacenter_dashboard_reports_parses_multiple_horizons(tmp_path):
    daily_path = tmp_path / "datacenter_daily_2026-05-22_0000_full.csv"
    daily_path.write_text("ticker;status\nNVDA;BUY_WATCH\n", encoding="utf-8")
    rolling_path = tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.csv"
    rolling_path.write_text("ticker;status\nAVGO;WATCH_ZONE\n", encoding="utf-8")

    result = parse_datacenter_dashboard_reports(
        [
            DatacenterReportStatus(
                horizon="daily",
                status="OK",
                path=str(daily_path),
                modified_at="2026-05-22T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 30d",
                status="OK",
                path=str(rolling_path),
                modified_at="2026-05-22T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 5d",
                status="MISSING",
                path=None,
                modified_at=None,
            ),
        ]
    )

    assert result.total_row_count == 2
    assert result.total_warning_count == 0
    assert {report.horizon: report.row_count for report in result.reports} == {
        "daily": 1,
        "rolling 30d": 1,
        "rolling 5d": 0,
    }
