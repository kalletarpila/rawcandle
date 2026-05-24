from __future__ import annotations

from dev_tools.datacenter_dashboard_decisions import (
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
                    source_files=[str(tmp_path / "daily.csv")],
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
