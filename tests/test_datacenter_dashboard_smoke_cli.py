from __future__ import annotations

import pytest

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionTrace,
    DatacenterDecisionBatchResult,
    DatacenterTickerDecision,
)
from dev_tools.datacenter_dashboard_inspector import DatacenterTickerInspectorView
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardReportParseSummary,
    DatacenterDashboardRow,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.run_datacenter_dashboard_smoke import main


def _write_report(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_missing_or_empty_report_directory_yields_missing_readiness_and_exit_zero(
    tmp_path, capsys
):
    empty_reports_dir = tmp_path / "reports"
    empty_reports_dir.mkdir()

    exit_code = main(["--reports-dir", str(empty_reports_dir)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert f"SUMMARY reports_dir={empty_reports_dir}" in lines
    assert "SUMMARY readiness=MISSING" in lines
    assert "SUMMARY found_reports=0" in lines
    assert "SUMMARY missing_reports=4" in lines
    assert "SUMMARY decision_total=0" in lines


def test_fixture_reports_produce_parsed_rows_and_decisions(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_rolling_30_2026-05-22_0000_full.csv",
        "ticker;status\nTSM;BUY_ZONE\n",
    )
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY readiness=PARTIAL" in lines
    assert "SUMMARY total_parsed_rows=2" in lines
    assert "SUMMARY decision_total=2" in lines
    assert "SUMMARY action.SELL=1" in lines
    assert "SUMMARY action.WATCH=1" in lines
    assert "SUMMARY pullback.VALID_PULLBACK=0" in lines
    assert "SUMMARY pullback.EARLY_PULLBACK=0" in lines
    assert "SUMMARY pullback.STRUCTURE_BLOCKED_PULLBACK=0" in lines
    assert "SUMMARY pullback.BREAKDOWN_NOT_PULLBACK=0" in lines
    assert "SUMMARY pullback.NO_PULLBACK=2" in lines
    assert "SUMMARY pullback.INSUFFICIENT_DATA=0" in lines
    assert "SUMMARY pullback_action.VALID_PULLBACK.SELL=0" in lines
    assert "SUMMARY pullback_action.VALID_PULLBACK.WATCH=0" in lines
    assert "SUMMARY pullback_action.EARLY_PULLBACK.WATCH=0" in lines
    assert "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.SELL=0" in lines
    assert "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.NEUTRAL=0" in lines


def test_ticker_found_prints_selected_ticker_summary(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--ticker", "nvda"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SUMMARY selected_ticker=NVDA" in output
    assert "SUMMARY selected_ticker_found=1" in output
    assert "SUMMARY selected_action=SELL" in output
    assert "SUMMARY selected_severity=CRITICAL" in output
    assert "SUMMARY selected_conflict_detected=false" in output
    assert "INSPECTOR ticker=NVDA action=SELL severity=CRITICAL" in output


def test_ticker_not_found_prints_selected_ticker_found_zero(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status\nNVDA;SELL\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--ticker", "AMD"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SUMMARY selected_ticker=AMD" in output
    assert "SUMMARY selected_ticker_found=0" in output
    assert "SUMMARY selected_action=" in output


def test_max_rows_limits_decision_output_rows(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;reason",
                "NVDA;SELL;close_below_ema20",
                "AVGO;WATCH;exit_risk",
                "TSM;BULLISH;",
                "INTC;SIDEWAYS;",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--max-rows", "2"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    decision_lines = [line for line in lines if line.startswith("DECISION ")]
    assert len(decision_lines) == 2


def test_action_counts_are_printed_deterministically(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_rolling_30_2026-05-22_0000_full.csv",
        "ticker;status;distance_to_ema20;blocking_reasons\nMETA;BUY_ZONE;16.5;STRUCTURAL_BLOCK\nTSM;BUY_ZONE;;\n",
    )
    _write_report(
        reports_dir / "datacenter_rolling_5_2026-05-22_0000_full.csv",
        "ticker;status\nTSM;PULLBACK\n",
    )
    _write_report(
        reports_dir / "datacenter_rolling_2_2026-05-22_0000_full.csv",
        "ticker;high_exit_risk_days_count\nLRCX;1\n",
    )
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;reason",
                "NVDA;SELL;close_below_ema20",
                "AVGO;WATCH;exit_risk",
                "TSM;BULLISH;",
                "INTC;SIDEWAYS;",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    summary_lines = [line for line in lines if line.startswith("SUMMARY action.")]
    assert summary_lines == [
        "SUMMARY action.SELL=1",
        "SUMMARY action.REDUCE=1",
        "SUMMARY action.TIGHTEN_STOP=1",
        "SUMMARY action.BLOCKED=1",
        "SUMMARY action.WAIT_PULLBACK=0",
        "SUMMARY action.BUY_NOW=1",
        "SUMMARY action.WATCH=0",
        "SUMMARY action.NEUTRAL=1",
    ]


def test_cli_uses_existing_helpers_rather_than_duplicating_logic(monkeypatch, tmp_path, capsys):
    calls = {
        "discover": 0,
        "parse_batch": 0,
        "parse_file": 0,
        "decisions": 0,
        "inspector": 0,
    }

    def fake_discover(reports_dir: str) -> DatacenterDashboardStatus:
        calls["discover"] += 1
        return DatacenterDashboardStatus(
            overall_status="PARTIAL",
            reports=[
                DatacenterReportStatus(
                    horizon="daily",
                    status="OK",
                    path=str(tmp_path / "daily.csv"),
                    modified_at="2026-05-24T00:00:00",
                )
            ],
        )

    def fake_parse_batch(
        reports: list[DatacenterReportStatus],
    ) -> DatacenterDashboardBatchParseResult:
        calls["parse_batch"] += 1
        return DatacenterDashboardBatchParseResult(
            reports=[
                DatacenterDashboardReportParseSummary(
                    horizon="daily",
                    source_file=str(tmp_path / "daily.csv"),
                    row_count=1,
                    warning_count=0,
                )
            ],
            total_row_count=1,
            total_warning_count=0,
        )

    def fake_parse_file(path: str, horizon: str):
        calls["parse_file"] += 1
        return type(
            "ParseResult",
            (),
            {
                "rows": [
                    DatacenterDashboardRow(
                        ticker="NVDA",
                        horizon=horizon,
                        source_file=path,
                        section=None,
                        row_kind=None,
                        raw_action=None,
                        raw_status="SELL",
                        reason="close_below_ema20",
                        trend_state=None,
                        latest_structure_label=None,
                        latest_bos_event_type=None,
                        latest_reset_reason=None,
                        distance_to_ema20=None,
                        high_exit_risk_days_count=None,
                        blocking_reasons=None,
                        ma_break_status=None,
                        ema20_break_confirmed=None,
                        sma50_break_confirmed=None,
                        close_below_ema20=None,
                        close_below_sma50=None,
                        consecutive_closes_below_ema20=None,
                        consecutive_closes_below_sma50=None,
                        ema20_break_pct=None,
                        sma50_break_pct=None,
                        freshness_status=None,
                        structure_warning_overrides_bullish_signal=None,
                        latest_bullish_signal_age_td=None,
                        latest_bearish_signal_age_td=None,
                        latest_bos_up_age_td=None,
                        latest_bos_down_age_td=None,
                        latest_reset_age_td=None,
                        raw_fields={},
                    )
                ]
            },
        )()

    def fake_decisions(rows):
        calls["decisions"] += 1
        return DatacenterDecisionBatchResult(
            decisions=[
                DatacenterTickerDecision(
                    ticker="NVDA",
                    action="SELL",
                    severity="CRITICAL",
                    primary_reason="SELL_SIGNAL_DETECTED",
                    reasons=[],
                    blocking_reasons=[],
                    horizons_present=["daily"],
                    horizon_statuses={"daily": "SELL"},
                    distance_to_ema20=None,
                    high_exit_risk_days_count=None,
                    trend_state=None,
                    latest_structure_label=None,
                    latest_bos_event_type=None,
                    latest_reset_reason=None,
                    pullback_validity="NO_PULLBACK",
                    pullback_reason="NO_PULLBACK_CONTEXT",
                    source_files=[str(tmp_path / "daily.csv")],
                    decision_trace=[
                        DatacenterDecisionTrace(
                            ticker="NVDA",
                            action="SELL",
                            matched_rule="SELL",
                            horizon="daily",
                            field_name="reason",
                            matched_token="close_below_ema20",
                            matched_value="close_below_ema20",
                            source_file=str(tmp_path / "daily.csv"),
                            section=None,
                            row_kind=None,
                        )
                    ],
                )
            ],
            action_counts={
                "SELL": 1,
                "REDUCE": 0,
                "TIGHTEN_STOP": 0,
                "BLOCKED": 0,
                "WAIT_PULLBACK": 0,
                "BUY_NOW": 0,
                "WATCH": 0,
                "NEUTRAL": 0,
            },
            pullback_counts={
                "VALID_PULLBACK": 0,
                "EARLY_PULLBACK": 0,
                "STRUCTURE_BLOCKED_PULLBACK": 0,
                "BREAKDOWN_NOT_PULLBACK": 0,
                "NO_PULLBACK": 1,
                "INSUFFICIENT_DATA": 0,
            },
            pullback_action_counts={
                "VALID_PULLBACK": {
                    "SELL": 0,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
                "EARLY_PULLBACK": {
                    "SELL": 0,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
                "STRUCTURE_BLOCKED_PULLBACK": {
                    "SELL": 0,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
                "BREAKDOWN_NOT_PULLBACK": {
                    "SELL": 0,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
                "NO_PULLBACK": {
                    "SELL": 1,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
                "INSUFFICIENT_DATA": {
                    "SELL": 0,
                    "REDUCE": 0,
                    "TIGHTEN_STOP": 0,
                    "BLOCKED": 0,
                    "WAIT_PULLBACK": 0,
                    "BUY_NOW": 0,
                    "WATCH": 0,
                    "NEUTRAL": 0,
                },
            },
            warning_count=0,
            warnings=[],
        )

    def fake_inspector(decision, rows):
        calls["inspector"] += 1
        return DatacenterTickerInspectorView(
            ticker="NVDA",
            action="SELL",
            severity="CRITICAL",
            primary_reason="SELL_SIGNAL_DETECTED",
            pullback_validity="NO_PULLBACK",
            pullback_reason="NO_PULLBACK_CONTEXT",
            supporting_signals=["close_below_ema20"],
            conflicting_signals=[],
            override_explanation=None,
            conflict_detected=False,
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_smoke.discover_datacenter_dashboard_status",
        fake_discover,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_smoke.parse_datacenter_dashboard_reports",
        fake_parse_batch,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_smoke.parse_datacenter_dashboard_file",
        fake_parse_file,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_smoke.build_datacenter_ticker_decisions",
        fake_decisions,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_smoke.build_datacenter_ticker_inspector_view",
        fake_inspector,
    )

    exit_code = main(["--reports-dir", str(tmp_path), "--ticker", "NVDA"])

    assert exit_code == 0
    assert calls == {
        "discover": 1,
        "parse_batch": 1,
        "parse_file": 1,
        "decisions": 1,
        "inspector": 1,
    }
    assert "SUMMARY selected_ticker_found=1" in capsys.readouterr().out


def test_default_output_does_not_include_trace_summary_lines(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SUMMARY pullback.NO_PULLBACK=1" in output
    assert "SUMMARY pullback_action.VALID_PULLBACK.SELL=0" in output
    assert "SUMMARY pullback_action.EARLY_PULLBACK.WATCH=0" in output
    assert "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.NEUTRAL=0" in output
    assert "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.NEUTRAL=0" in output
    assert "SUMMARY trace.SELL.horizon.daily=" not in output
    assert "TRACE ticker=NVDA" not in output


def test_show_trace_includes_selected_ticker_trace_lines(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--ticker", "NVDA", "--show-trace"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "TRACE ticker=NVDA action=SELL rule=SELL_HARD_TOKEN horizon=daily field=raw_status token=sell value=SELL" in output


def test_show_trace_includes_sell_horizon_and_token_summary_counts(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_rolling_2_2026-05-22_0000_full.csv",
        "ticker;status;latest_bos_event_type;latest_reset_reason\nNVDA;WATCH;BOS_DOWN;RESET\n",
    )
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nAVGO;SELL;close_below_ema20\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--show-trace"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY trace.SELL.horizon.daily=1" in lines
    assert "SUMMARY trace.SELL.horizon.rolling_2d=2" in lines
    assert "SUMMARY trace.SELL.horizon.rolling_5d=0" in lines
    assert "SUMMARY trace.SELL.horizon.rolling_30d=0" in lines
    assert "SUMMARY trace.SELL.token.SELL=1" in lines
    assert "SUMMARY trace.SELL.token.close_below_ema20=0" in lines
    assert "SUMMARY trace.SELL.token.BOS_DOWN=1" in lines
    assert "SUMMARY trace.SELL.token.RESET=1" in lines
    assert "SUMMARY pullback.NO_PULLBACK=2" in lines
    assert "SUMMARY pullback.STRUCTURE_BLOCKED_PULLBACK=0" in lines
    assert "SUMMARY pullback_action.VALID_PULLBACK.SELL=0" in lines
    assert "SUMMARY pullback_action.EARLY_PULLBACK.WATCH=0" in lines
    assert "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.SELL=0" in lines
    assert "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.NEUTRAL=0" in lines


def test_show_trace_output_is_deterministic(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason\nNVDA;SELL;close_below_ema20\n",
    )

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--ticker", "NVDA", "--show-trace"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    trace_lines = [line for line in lines if line.startswith("TRACE ")]
    assert trace_lines == [
        "TRACE ticker=NVDA action=SELL rule=SELL_HARD_TOKEN horizon=daily field=raw_status token=sell value=SELL"
    ]


def test_pullback_summary_counts_are_printed_deterministically(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL",
                "BBB;PULLBACK_CANDIDATE;OK;",
                "CCC;SIDEWAYS;;",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    pullback_lines = [line for line in lines if line.startswith("SUMMARY pullback.")]
    assert pullback_lines == [
        "SUMMARY pullback.VALID_PULLBACK=1",
        "SUMMARY pullback.EARLY_PULLBACK=1",
        "SUMMARY pullback.STRUCTURE_BLOCKED_PULLBACK=0",
        "SUMMARY pullback.BREAKDOWN_NOT_PULLBACK=0",
        "SUMMARY pullback.NO_PULLBACK=1",
        "SUMMARY pullback.INSUFFICIENT_DATA=0",
    ]


def test_pullback_action_summary_counts_are_printed_deterministically(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL",
                "BBB;PULLBACK_CANDIDATE;OK;",
                "CCC;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;",
                "DDD;PULLBACK_CANDIDATE;;STRUCTURE_WARNING_OVERRIDES_BULLISH",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    pullback_action_lines = [
        line for line in lines if line.startswith("SUMMARY pullback_action.")
    ]
    assert pullback_action_lines == [
        "SUMMARY pullback_action.VALID_PULLBACK.SELL=0",
        "SUMMARY pullback_action.VALID_PULLBACK.REDUCE=0",
        "SUMMARY pullback_action.VALID_PULLBACK.TIGHTEN_STOP=0",
        "SUMMARY pullback_action.VALID_PULLBACK.WATCH=0",
        "SUMMARY pullback_action.VALID_PULLBACK.BUY_NOW=0",
        "SUMMARY pullback_action.VALID_PULLBACK.NEUTRAL=1",
        "SUMMARY pullback_action.EARLY_PULLBACK.SELL=0",
        "SUMMARY pullback_action.EARLY_PULLBACK.REDUCE=0",
        "SUMMARY pullback_action.EARLY_PULLBACK.TIGHTEN_STOP=0",
        "SUMMARY pullback_action.EARLY_PULLBACK.WATCH=0",
        "SUMMARY pullback_action.EARLY_PULLBACK.BUY_NOW=0",
        "SUMMARY pullback_action.EARLY_PULLBACK.NEUTRAL=1",
        "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.SELL=0",
        "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.REDUCE=0",
        "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.TIGHTEN_STOP=0",
        "SUMMARY pullback_action.STRUCTURE_BLOCKED_PULLBACK.NEUTRAL=1",
        "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.SELL=1",
        "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.REDUCE=0",
        "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.TIGHTEN_STOP=0",
        "SUMMARY pullback_action.BREAKDOWN_NOT_PULLBACK.NEUTRAL=0",
    ]


def test_show_trace_selected_ticker_inspector_can_include_ma_break_and_freshness_status(
    tmp_path, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;reason;ma_break_status;freshness_status\nNVDA;SELL;close_below_ema20;EMA20_CONFIRMED_BREAK;FRESH_BEARISH_SIGNAL\n",
    )

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--ticker", "NVDA", "--show-trace"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "INSPECTOR horizon=daily" in output
    assert "ma_break_status=EMA20_CONFIRMED_BREAK" in output
    assert "freshness_status=FRESH_BEARISH_SIGNAL" in output


def test_show_trace_selected_ticker_output_includes_pullback_validity_and_reason(
    tmp_path, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_rolling_2_2026-05-22_0000_full.csv",
        "ticker;status;latest_bos_event_type;latest_bos_freshness\nNVDA;PULLBACK_CANDIDATE;BOS_DOWN;FRESH\n",
    )

    exit_code = main(
        ["--reports-dir", str(reports_dir), "--ticker", "NVDA", "--show-trace"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "INSPECTOR pullback_validity=STRUCTURE_BLOCKED_PULLBACK" in output
    assert "INSPECTOR pullback_reason=FRESH_BOS_DOWN_BLOCKS_PULLBACK" in output


def test_default_output_does_not_include_pullback_validity_lines_when_show_trace_not_used(
    tmp_path, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_rolling_2_2026-05-22_0000_full.csv",
        "ticker;status;latest_bos_event_type;latest_bos_freshness\nNVDA;PULLBACK_CANDIDATE;BOS_DOWN;FRESH\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--ticker", "NVDA"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "INSPECTOR pullback_validity=" not in output
    assert "INSPECTOR pullback_reason=" not in output


def test_pullback_debug_prints_rows(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status;reason",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL;",
                "BBB;PULLBACK_CANDIDATE;OK;;",
                "CCC;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;;",
                "DDD;PULLBACK_CANDIDATE;;STRUCTURE_WARNING_OVERRIDES_BULLISH;",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--pullback-debug"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    debug_lines = [line for line in lines if line.startswith("PULLBACK_DEBUG ")]
    assert len(debug_lines) == 4
    assert debug_lines[0].startswith("PULLBACK_DEBUG ticker=AAA validity=VALID_PULLBACK")
    assert debug_lines[1].startswith("PULLBACK_DEBUG ticker=BBB validity=EARLY_PULLBACK")
    assert debug_lines[2].startswith(
        "PULLBACK_DEBUG ticker=DDD validity=STRUCTURE_BLOCKED_PULLBACK"
    )
    assert debug_lines[3].startswith(
        "PULLBACK_DEBUG ticker=CCC validity=BREAKDOWN_NOT_PULLBACK"
    )


def test_default_output_without_pullback_debug_does_not_print_pullback_debug_rows(
    tmp_path, capsys
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "ticker;status;ma_break_status;freshness_status\nAAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir)])

    assert exit_code == 0
    assert "PULLBACK_DEBUG " not in capsys.readouterr().out


def test_pullback_debug_validity_filters_rows(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL",
                "BBB;PULLBACK_CANDIDATE;OK;",
            ]
        )
        + "\n",
    )

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--pullback-debug",
            "--pullback-debug-validity",
            "VALID_PULLBACK",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    debug_lines = [line for line in lines if line.startswith("PULLBACK_DEBUG ")]
    assert len(debug_lines) == 1
    assert "ticker=AAA" in debug_lines[0]
    assert "validity=VALID_PULLBACK" in debug_lines[0]


def test_pullback_debug_action_filters_rows(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL",
                "BBB;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;",
            ]
        )
        + "\n",
    )

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--pullback-debug",
            "--pullback-debug-action",
            "SELL",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    debug_lines = [line for line in lines if line.startswith("PULLBACK_DEBUG ")]
    assert len(debug_lines) == 1
    assert "ticker=BBB" in debug_lines[0]
    assert "action=SELL" in debug_lines[0]


def test_max_pullback_debug_rows_limits_pullback_debug_rows(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL",
                "BBB;PULLBACK_CANDIDATE;OK;",
                "CCC;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;",
                "DDD;PULLBACK_CANDIDATE;;STRUCTURE_WARNING_OVERRIDES_BULLISH",
            ]
        )
        + "\n",
    )

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--pullback-debug",
            "--max-pullback-debug-rows",
            "2",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    debug_lines = [line for line in lines if line.startswith("PULLBACK_DEBUG ")]
    assert len(debug_lines) == 2


def test_invalid_pullback_debug_validity_filter_exits_non_zero(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--reports-dir",
                str(reports_dir),
                "--pullback-debug",
                "--pullback-debug-validity",
                "BAD_VALUE",
            ]
        )

    assert exc_info.value.code != 0


def test_invalid_pullback_debug_action_filter_exits_non_zero(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--reports-dir",
                str(reports_dir),
                "--pullback-debug",
                "--pullback-debug-action",
                "BAD_ACTION",
            ]
        )

    assert exc_info.value.code != 0


def test_pullback_debug_output_order_is_deterministic(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status;reason",
                "CCC;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;;",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL;",
                "DDD;PULLBACK_CANDIDATE;;STRUCTURE_WARNING_OVERRIDES_BULLISH;",
                "BBB;PULLBACK_CANDIDATE;OK;;",
            ]
        )
        + "\n",
    )

    exit_code = main(["--reports-dir", str(reports_dir), "--pullback-debug"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    debug_lines = [line for line in lines if line.startswith("PULLBACK_DEBUG ")]
    assert debug_lines == [
        "PULLBACK_DEBUG ticker=AAA validity=VALID_PULLBACK reason=FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK action=NEUTRAL severity=INFO primary_reason=NO_DECISIVE_SIGNAL first_trace_rule=NEUTRAL_FALLBACK first_trace_token= first_trace_horizon=",
        "PULLBACK_DEBUG ticker=BBB validity=EARLY_PULLBACK reason=WAIT_FOR_BULLISH_CONFIRMATION action=NEUTRAL severity=INFO primary_reason=NO_DECISIVE_SIGNAL first_trace_rule=NEUTRAL_FALLBACK first_trace_token= first_trace_horizon=",
        "PULLBACK_DEBUG ticker=DDD validity=STRUCTURE_BLOCKED_PULLBACK reason=STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL action=NEUTRAL severity=INFO primary_reason=NO_DECISIVE_SIGNAL first_trace_rule=NEUTRAL_FALLBACK first_trace_token= first_trace_horizon=",
        "PULLBACK_DEBUG ticker=CCC validity=BREAKDOWN_NOT_PULLBACK reason=EMA20_CONFIRMED_BREAK action=SELL severity=CRITICAL primary_reason=SELL_SIGNAL_DETECTED first_trace_rule=SELL_EMA20_CONFIRMED_BREAK first_trace_token=EMA20_CONFIRMED_BREAK first_trace_horizon=daily",
    ]


def test_pullback_debug_does_not_change_decision_output_counts(tmp_path, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _write_report(
        reports_dir / "datacenter_daily_2026-05-22_0000_full.csv",
        "\n".join(
            [
                "ticker;status;ma_break_status;freshness_status;reason",
                "AAA;PULLBACK_CANDIDATE;OK;FRESH_BULLISH_SIGNAL;",
                "CCC;PULLBACK_CANDIDATE;EMA20_CONFIRMED_BREAK;;",
            ]
        )
        + "\n",
    )

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--pullback-debug",
            "--max-rows",
            "2",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "SUMMARY action.SELL=1" in output
    assert "SUMMARY action.NEUTRAL=1" in output
    assert "DECISION ticker=CCC action=SELL severity=CRITICAL reason=SELL_SIGNAL_DETECTED" in output
    assert "DECISION ticker=AAA action=NEUTRAL severity=INFO reason=NO_DECISIVE_SIGNAL" in output
