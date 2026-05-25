from __future__ import annotations

import pytest

from rawcandle.cli import run_stock_update_scheduler as cli
from rawcandle.scheduler.runner import (
    ScheduledMarketRunResult,
    ScheduledStockUpdateRunResult,
    SchedulerAlreadyRunningError,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
)


def _result(overall_status):
    return ScheduledStockUpdateRunResult(
        started_at_utc="2026-05-16T00:00:00Z",
        finished_at_utc="2026-05-16T00:10:00Z",
        config_path="/tmp/scheduler.json",
        enabled_markets=["omxh", "omxs"],
        market_results=[
            ScheduledMarketRunResult(
                market="omxh",
                started_at_utc="2026-05-16T00:00:00Z",
                finished_at_utc="2026-05-16T00:01:00Z",
                exit_code=0,
                summary_status=STATUS_OK,
                log_path="/tmp/logs/omxh.log",
                summary_lines=["SUMMARY market=omxh"],
            ),
            ScheduledMarketRunResult(
                market="omxs",
                started_at_utc="2026-05-16T00:01:00Z",
                finished_at_utc="2026-05-16T00:02:00Z",
                exit_code=0 if overall_status == STATUS_OK else 1,
                summary_status=overall_status if overall_status != STATUS_OK else STATUS_OK,
                log_path="/tmp/logs/omxs.log",
                summary_lines=["SUMMARY market=omxs"],
            ),
        ],
        overall_status=overall_status,
        summary_json_path="/tmp/logs/summary.json",
        skipped=False,
        skip_reason=None,
        technical_relevance_attempted=0,
        technical_relevance_enabled=False,
        technical_relevance_status="DISABLED",
        technical_relevance_market="NONE",
        technical_relevance_run_id="NONE",
        technical_relevance_ticker_count=0,
        technical_relevance_start_date="NONE",
        technical_relevance_end_date="NONE",
        technical_relevance_records_written=0,
        technical_relevance_relevant_count=0,
        technical_relevance_weak_context_count=0,
        technical_relevance_noise_count=0,
        technical_relevance_unknown_signal_count=0,
        technical_relevance_missing_dow_context_count=0,
        technical_relevance_missing_bar_index_count=0,
        technical_relevance_duration_seconds="0.000",
        technical_relevance_skip_reason="",
        technical_relevance_error="",
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
        datacenter_pipeline_audit_validation_status="SKIPPED",
        datacenter_pipeline_log_path="",
        datacenter_pipeline_signal_date="NONE",
        datacenter_pipeline_signal_date_source="NONE",
        datacenter_pipeline_signal_date_resolution="NONE",
        datacenter_pipeline_requested_calendar_signal_date="NONE",
        datacenter_pipeline_daily_report_path=None,
        datacenter_pipeline_daily_report_csv_path=None,
        datacenter_pipeline_rolling_30_report_path=None,
        datacenter_pipeline_rolling_30_report_csv_path=None,
        datacenter_pipeline_rolling_5_report_path=None,
        datacenter_pipeline_rolling_5_report_csv_path=None,
        datacenter_pipeline_rolling_2_report_path=None,
        datacenter_pipeline_rolling_2_report_csv_path=None,
        datacenter_pipeline_weekly_report_path=None,
        datacenter_pipeline_weekly_report_csv_path=None,
        datacenter_pipeline_error="",
        datacenter_dashboard_attempted=0,
        datacenter_dashboard_status="SKIPPED",
        datacenter_dashboard_dashboard_db="",
        datacenter_dashboard_report_date="",
        datacenter_dashboard_md_reports_status="SKIPPED",
        datacenter_dashboard_source_reports_available=0,
        datacenter_dashboard_html_output_path="",
        datacenter_dashboard_run_id="",
        datacenter_dashboard_skip_reason="",
        datacenter_dashboard_error="",
    )


def _skipped_result():
    return ScheduledStockUpdateRunResult(
        started_at_utc="2026-05-16T00:00:00Z",
        finished_at_utc="2026-05-16T00:00:01Z",
        config_path="/tmp/scheduler.json",
        enabled_markets=["omxh", "omxs"],
        market_results=[],
        overall_status=STATUS_OK,
        summary_json_path="/tmp/logs/summary.json",
        skipped=True,
        skip_reason="skip_next_run",
        technical_relevance_attempted=0,
        technical_relevance_enabled=False,
        technical_relevance_status="DISABLED",
        technical_relevance_market="NONE",
        technical_relevance_run_id="NONE",
        technical_relevance_ticker_count=0,
        technical_relevance_start_date="NONE",
        technical_relevance_end_date="NONE",
        technical_relevance_records_written=0,
        technical_relevance_relevant_count=0,
        technical_relevance_weak_context_count=0,
        technical_relevance_noise_count=0,
        technical_relevance_unknown_signal_count=0,
        technical_relevance_missing_dow_context_count=0,
        technical_relevance_missing_bar_index_count=0,
        technical_relevance_duration_seconds="0.000",
        technical_relevance_skip_reason="",
        technical_relevance_error="",
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
        datacenter_pipeline_audit_validation_status="SKIPPED",
        datacenter_pipeline_log_path="",
        datacenter_pipeline_signal_date="NONE",
        datacenter_pipeline_signal_date_source="NONE",
        datacenter_pipeline_signal_date_resolution="NONE",
        datacenter_pipeline_requested_calendar_signal_date="NONE",
        datacenter_pipeline_daily_report_path=None,
        datacenter_pipeline_daily_report_csv_path=None,
        datacenter_pipeline_rolling_30_report_path=None,
        datacenter_pipeline_rolling_30_report_csv_path=None,
        datacenter_pipeline_rolling_5_report_path=None,
        datacenter_pipeline_rolling_5_report_csv_path=None,
        datacenter_pipeline_rolling_2_report_path=None,
        datacenter_pipeline_rolling_2_report_csv_path=None,
        datacenter_pipeline_weekly_report_path=None,
        datacenter_pipeline_weekly_report_csv_path=None,
        datacenter_pipeline_error="",
        datacenter_dashboard_attempted=0,
        datacenter_dashboard_status="SKIPPED",
        datacenter_dashboard_dashboard_db="",
        datacenter_dashboard_report_date="",
        datacenter_dashboard_md_reports_status="SKIPPED",
        datacenter_dashboard_source_reports_available=0,
        datacenter_dashboard_html_output_path="",
        datacenter_dashboard_run_id="",
        datacenter_dashboard_skip_reason="SKIP_NEXT_RUN",
        datacenter_dashboard_error="",
    )


def test_scheduler_cli_missing_config_exits_via_parser():
    with pytest.raises(SystemExit):
        cli.main([])


def test_scheduler_cli_successful_run_prints_top_level_summary_lines(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_status=OK" in captured.out
    assert "SUMMARY markets_enabled=omxh,omxs" in captured.out
    assert "SUMMARY summary_json_path=/tmp/logs/summary.json" in captured.out
    assert "SUMMARY scheduler_skipped=0" in captured.out
    assert "SUMMARY scheduler_skip_reason=" in captured.out
    assert "SUMMARY technical_relevance.attempted=0" in captured.out
    assert "SUMMARY technical_relevance.enabled=false" in captured.out
    assert "SUMMARY technical_relevance.status=DISABLED" in captured.out
    assert "SUMMARY technical_relevance.market=NONE" in captured.out
    assert "SUMMARY technical_relevance.run_id=NONE" in captured.out
    assert "SUMMARY technical_relevance.ticker_count=0" in captured.out
    assert "SUMMARY technical_relevance.start_date=NONE" in captured.out
    assert "SUMMARY technical_relevance.end_date=NONE" in captured.out
    assert "SUMMARY technical_relevance.records_written=0" in captured.out
    assert "SUMMARY technical_relevance.relevant_count=0" in captured.out
    assert "SUMMARY technical_relevance.weak_context_count=0" in captured.out
    assert "SUMMARY technical_relevance.noise_count=0" in captured.out
    assert "SUMMARY technical_relevance.unknown_signal_count=0" in captured.out
    assert "SUMMARY technical_relevance.missing_dow_context_count=0" in captured.out
    assert "SUMMARY technical_relevance.missing_bar_index_count=0" in captured.out
    assert "SUMMARY technical_relevance.duration_seconds=0.000" in captured.out
    assert "SUMMARY technical_relevance.skip_reason=" in captured.out
    assert "SUMMARY datacenter_pipeline.attempted=0" in captured.out
    assert "SUMMARY datacenter_pipeline.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_pipeline.market=usa" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date_source=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date_resolution=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.requested_calendar_signal_date=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.audit_validation_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_pipeline.log_path=" in captured.out
    assert "SUMMARY datacenter_pipeline.daily_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.daily_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_30_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_30_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_5_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_5_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_2_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_2_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.weekly_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.weekly_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.error=" in captured.out
    assert "SUMMARY datacenter_dashboard.attempted=0" in captured.out
    assert "SUMMARY datacenter_dashboard.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.dashboard_db=" in captured.out
    assert "SUMMARY datacenter_dashboard.report_date=" in captured.out
    assert "SUMMARY datacenter_dashboard.md_reports_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.source_reports_available=0" in captured.out
    assert "SUMMARY datacenter_dashboard.html_output_path=" in captured.out
    assert "SUMMARY datacenter_dashboard.run_id=" in captured.out
    assert "SUMMARY datacenter_dashboard.skip_reason=" in captured.out
    assert "SUMMARY datacenter_dashboard.error=" in captured.out


def test_scheduler_cli_ok_overall_status_exits_zero(monkeypatch):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 0


def test_scheduler_cli_ok_with_warnings_exits_one(monkeypatch):
    monkeypatch.setattr(
        cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK_WITH_WARNINGS)
    )
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_failed_exits_one(monkeypatch):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_FAILED))
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_prints_per_market_status_and_log_lines(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))

    cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert "SUMMARY market.omxh.status=OK" in captured.out
    assert "SUMMARY market.omxh.log_path=/tmp/logs/omxh.log" in captured.out
    assert "SUMMARY market.omxs.status=OK" in captured.out
    assert "SUMMARY market.omxs.log_path=/tmp/logs/omxs.log" in captured.out


def test_scheduler_cli_skipped_run_prints_skip_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _skipped_result())

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_status=OK" in captured.out
    assert "SUMMARY scheduler_skipped=1" in captured.out
    assert "SUMMARY scheduler_skip_reason=skip_next_run" in captured.out
    assert "SUMMARY markets_total=0" in captured.out


def test_scheduler_cli_lock_conflict_prints_failed_summary_and_exits_one(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "run_scheduler_config",
        lambda config_path: (_ for _ in ()).throw(
            SchedulerAlreadyRunningError("already running")
        ),
    )

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY scheduler_status=FAILED" in captured.out
    assert "SUMMARY scheduler_skipped=0" in captured.out
    assert "SUMMARY scheduler_skip_reason=" in captured.out
    assert "SUMMARY error=already running" in captured.out
