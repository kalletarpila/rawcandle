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
    assert row.ma_break_status is None
    assert row.freshness_status is None


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


def test_parse_datacenter_dashboard_file_parses_ma_break_fields(tmp_path):
    report_path = tmp_path / "datacenter_daily_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;ma_break_status;ema20_break_confirmed;sma50_break_confirmed;ema20_break_pct;sma50_break_pct",
                "NVDA;EMA20_CONFIRMED_BREAK;1;0;-0.0215;0.0",
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
    assert row.ma_break_status == "EMA20_CONFIRMED_BREAK"
    assert row.ema20_break_confirmed == 1
    assert row.sma50_break_confirmed == 0
    assert row.ema20_break_pct == -0.0215
    assert row.sma50_break_pct == 0.0


def test_parse_datacenter_dashboard_file_parses_freshness_fields(tmp_path):
    report_path = tmp_path / "datacenter_rolling_2_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;freshness_status;structure_warning_overrides_bullish_signal;latest_bullish_signal_age_td;latest_bearish_signal_age_td;latest_bos_up_age_td;latest_bos_down_age_td;latest_reset_age_td",
                "AVGO;STRUCTURE_WARNING_OVERRIDES_BULLISH;1;4;1;12;1;3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="rolling 2d",
    )

    row = result.rows[0]
    assert row.freshness_status == "STRUCTURE_WARNING_OVERRIDES_BULLISH"
    assert row.structure_warning_overrides_bullish_signal == 1
    assert row.latest_bullish_signal_age_td == 4
    assert row.latest_bearish_signal_age_td == 1
    assert row.latest_bos_up_age_td == 12
    assert row.latest_bos_down_age_td == 1
    assert row.latest_reset_age_td == 3


def test_parse_datacenter_dashboard_file_handles_malformed_ma_and_freshness_values(tmp_path):
    report_path = tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.csv"
    report_path.write_text(
        "\n".join(
            [
                "ticker;ema20_break_confirmed;ema20_break_pct;structure_warning_overrides_bullish_signal",
                "TSM;bad_int;bad_float;oops",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="rolling 30d",
    )

    row = result.rows[0]
    assert row.ema20_break_confirmed is None
    assert row.ema20_break_pct is None
    assert row.structure_warning_overrides_bullish_signal is None
    assert any("invalid int for ema20_break_confirmed" in warning for warning in result.warnings)
    assert any("invalid float for ema20_break_pct" in warning for warning in result.warnings)
    assert any(
        "invalid int for structure_warning_overrides_bullish_signal" in warning
        for warning in result.warnings
    )


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


def test_parse_datacenter_dashboard_file_preserves_markdown_section_heading_for_watchlist_rows(tmp_path):
    report_path = tmp_path / "datacenter_daily_2026-05-22_0000_full.md"
    report_path.write_text(
        "\n".join(
            [
                "## Watchlist Summary",
                "| ticker | watchlist_status | latest_structure_label |",
                "| --- | --- | --- |",
                "| NVDA | BREAKOUT_READY | HL |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = parse_datacenter_dashboard_file(
        path=str(report_path),
        horizon="daily",
    )

    assert len(result.rows) == 1
    assert result.rows[0].section == "Watchlist Summary"
    assert result.rows[0].raw_fields["watchlist_status"] == "BREAKOUT_READY"


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
