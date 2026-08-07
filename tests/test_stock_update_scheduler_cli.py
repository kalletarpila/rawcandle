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
        ec_source_layer_attempted=1,
        ec_source_layer_status="OK",
        ec_source_layer_log_path="/tmp/logs/ec.log",
        ec_source_layer_signal_date="2026-05-22",
        ec_source_layer_refresh_mode="scheduler_post_step",
        ec_source_layer_skipped_reason="NONE",
        ec_source_layer_backup_path="/tmp/backups/analysis.db",
        ec_source_layer_coverage_status="OK",
        ec_source_layer_parity_status="OK",
        ec_source_layer_total_mismatch_count=0,
        ec_source_layer_ticker_rows=10,
        ec_source_layer_group_signal_rows=2,
        ec_source_layer_synthetic_ohlc_rows=2,
        ec_source_layer_group_index_rows=2,
        ec_source_layer_watermark_rows=5,
        ec_source_layer_error="NONE",
        swingmaster_fundamentals_attempted=1,
        swingmaster_result_check_status="SUCCESS",
        swingmaster_result_check_exit_code=0,
        swingmaster_result_check_log_path="/tmp/logs/swingmaster_check.txt",
        swingmaster_result_check_plan_json="/tmp/plan.json",
        swingmaster_result_check_candidate_count=2,
        swingmaster_active_tickers=2936,
        swingmaster_7_day_watch_window_count=17,
        swingmaster_due_for_result_check=3,
        swingmaster_future_confirmation_provider_calls_now=5,
        swingmaster_failure_retries=2,
        swingmaster_maintenance_selected=100,
        swingmaster_total_unique_provider_check_tickers=110,
        swingmaster_maintenance_backlog_remaining=24,
        swingmaster_weekly_update_attempted=0,
        swingmaster_weekly_update_status="SKIPPED",
        swingmaster_weekly_update_log_path="",
    )


def _skipped_result():
    result = _result(STATUS_OK)
    result.market_results = []
    result.skipped = True
    result.skip_reason = "skip_next_run"
    result.ec_source_layer_attempted = 0
    result.ec_source_layer_status = "SKIPPED"
    return result


def test_scheduler_cli_missing_config_exits_via_parser():
    with pytest.raises(SystemExit):
        cli.main([])


def test_scheduler_cli_successful_run_prints_preserved_summary_lines(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_status=OK" in captured.out
    assert "SUMMARY markets_enabled=omxh,omxs" in captured.out
    assert "SUMMARY technical_relevance.attempted=0" in captured.out
    assert "SUMMARY datacenter_pipeline.status=SKIPPED" in captured.out
    assert "SUMMARY ec_source_layer.status=OK" in captured.out
    assert "SUMMARY swingmaster_fundamentals.result_check_status=SUCCESS" in captured.out
    assert "SUMMARY swingmaster_fundamentals.active_tickers=2936" in captured.out
    assert "SUMMARY swingmaster_fundamentals.maintenance_selected=100" in captured.out
    assert "SUMMARY swingmaster_fundamentals.weekly_update_status=SKIPPED" in captured.out


def test_scheduler_cli_ok_with_warnings_exits_one(monkeypatch):
    monkeypatch.setattr(
        cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK_WITH_WARNINGS)
    )

    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_failed_exits_one(monkeypatch):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_FAILED))

    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_skipped_run_prints_skip_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _skipped_result())

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_skipped=1" in captured.out
    assert "SUMMARY scheduler_skip_reason=skip_next_run" in captured.out


def test_scheduler_cli_already_running_exits_one(monkeypatch, capsys):
    def raise_running(config_path):
        raise SchedulerAlreadyRunningError("already running")

    monkeypatch.setattr(cli, "run_scheduler_config", raise_running)

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY scheduler_status=FAILED" in captured.out
    assert "SUMMARY error=already running" in captured.out
