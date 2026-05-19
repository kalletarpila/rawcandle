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
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
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
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
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
    assert "SUMMARY datacenter_pipeline.attempted=0" in captured.out
    assert "SUMMARY datacenter_pipeline.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_pipeline.market=usa" in captured.out


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
