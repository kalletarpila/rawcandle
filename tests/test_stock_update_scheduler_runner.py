from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.scheduler.config import (
    create_default_scheduler_config,
    read_scheduler_config,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    SchedulerAlreadyRunningError,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    acquire_scheduler_lock,
    read_scheduler_status,
    release_scheduler_lock,
    run_scheduler_config,
    scheduler_lock_path,
    scheduler_status_path,
)
from services.stock_update_service import StockUpdateResult


def _touch(path):
    path.write_text("", encoding="utf-8")


def _write_config(
    tmp_path,
    *,
    enabled_markets=None,
    osakedata_db=None,
    analysis_db=None,
    log_dir=None,
    skip_next_run=False,
):
    osakedata_db = osakedata_db or (tmp_path / "osakedata.db")
    analysis_db = analysis_db or (tmp_path / "analysis.db")
    log_dir = log_dir or (tmp_path / "logs")
    config = create_default_scheduler_config(
        osakedata_db_path=str(osakedata_db),
        analysis_db_path=str(analysis_db),
        log_dir=str(log_dir),
    )
    if enabled_markets is not None:
        config.enabled_markets = enabled_markets
    config.skip_next_run = skip_next_run
    path = tmp_path / "scheduler_config.json"
    write_scheduler_config(str(path), config)
    return path


def test_scheduler_runner_preflight_fails_when_osakedata_missing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        osakedata_db=tmp_path / "missing_osakedata.db",
        analysis_db=analysis_db,
    )

    with pytest.raises(ValueError, match="Missing osakedata db"):
        run_scheduler_config(config_path=str(config_path))


def test_scheduler_runner_preflight_fails_when_analysis_missing(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    _touch(osakedata_db)
    config_path = _write_config(
        tmp_path,
        osakedata_db=osakedata_db,
        analysis_db=tmp_path / "missing_analysis.db",
    )

    with pytest.raises(ValueError, match="Missing analysis db"):
        run_scheduler_config(config_path=str(config_path))


def test_scheduler_runner_preflight_fails_when_db_dirs_differ(tmp_path):
    osakedata_dir = tmp_path / "osakedata"
    analysis_dir = tmp_path / "analysis"
    osakedata_dir.mkdir()
    analysis_dir.mkdir()
    osakedata_db = osakedata_dir / "osakedata.db"
    analysis_db = analysis_dir / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        osakedata_db=osakedata_db,
        analysis_db=analysis_db,
    )

    with pytest.raises(ValueError, match="same directory"):
        run_scheduler_config(config_path=str(config_path))


def test_scheduler_runner_runs_markets_in_config_order(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])

    calls = []

    def fake_run(self, **kwargs):
        calls.append(kwargs["market"])
        return StockUpdateResult(market=kwargs["market"], status=STATUS_OK)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        fake_run,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert calls == ["omxh", "omxs"]
    assert [item.market for item in result.market_results] == ["omxh", "omxs"]


def test_scheduler_runner_default_config_does_not_run_usa(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path)

    calls = []

    def fake_run(self, **kwargs):
        calls.append(kwargs["market"])
        return StockUpdateResult(market=kwargs["market"], status=STATUS_OK)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        fake_run,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    run_scheduler_config(config_path=str(config_path))

    assert calls == ["omxh", "omxs"]
    assert "usa" not in calls


def test_scheduler_runner_one_market_failure_does_not_stop_later_market(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])

    calls = []

    def fake_run(self, **kwargs):
        calls.append(kwargs["market"])
        if kwargs["market"] == "omxh":
            raise RuntimeError("boom")
        return StockUpdateResult(market=kwargs["market"], status=STATUS_OK)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        fake_run,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert calls == ["omxh", "omxs"]
    assert len(result.market_results) == 2
    assert result.market_results[0].summary_status == STATUS_FAILED
    assert result.market_results[1].summary_status == STATUS_OK
    assert result.overall_status == STATUS_FAILED


def test_scheduler_runner_writes_log_file_per_market(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(
            market=kwargs["market"], tickers_checked=2, status=STATUS_OK
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))
    log_path = result.market_results[0].log_path
    log_text = (tmp_path / "logs" / Path(log_path).name).read_text(encoding="utf-8")

    assert Path(log_path).exists()
    assert log_path.endswith(".txt")
    assert "SUMMARY market=omxh" in log_text
    assert "market=omxh" in log_text


def test_scheduler_runner_writes_summary_json(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    summary_json_path = Path(result.summary_json_path)
    assert str(summary_json_path).endswith(".json")
    assert summary_json_path.exists()
    payload = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == STATUS_OK
    assert payload["market_results"][0]["market"] == "omxh"
    assert payload["summary_json_path"] == str(summary_json_path)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([STATUS_OK, STATUS_OK], STATUS_OK),
        ([STATUS_OK, STATUS_OK_WITH_WARNINGS], STATUS_OK_WITH_WARNINGS),
        ([STATUS_OK, STATUS_FAILED], STATUS_FAILED),
    ],
)
def test_scheduler_runner_overall_status_rules(tmp_path, monkeypatch, statuses, expected):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])

    status_map = {"omxh": statuses[0], "omxs": statuses[1]}

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(
            market=kwargs["market"], status=status_map[kwargs["market"]]
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == expected


def test_scheduler_runner_does_not_call_update_stock_data(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp.update_stock_data",
        lambda self, e=None: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.overall_status == STATUS_OK


def test_scheduler_runner_does_not_call_rawcandleapp_init(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp.__init__",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("__init__ should not be called")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.overall_status == STATUS_OK


def test_scheduler_runner_skip_next_run_skips_all_markets(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path, enabled_markets=["omxh", "omxs"], skip_next_run=True
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: (_ for _ in ()).throw(
            AssertionError("market run should not be called")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.market_results == []
    assert result.overall_status == STATUS_OK
    assert result.skipped is True
    assert result.skip_reason == "skip_next_run"
    assert result.enabled_markets == ["omxh", "omxs"]
    summary_json_path = Path(result.summary_json_path)
    assert summary_json_path.exists()
    payload = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert payload["skipped"] is True
    assert payload["skip_reason"] == "skip_next_run"
    assert payload["enabled_markets"] == ["omxh", "omxs"]
    assert payload["market_results"] == []


def test_scheduler_runner_skip_next_run_resets_config_to_false(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path, enabled_markets=["omxh", "omxs"], skip_next_run=True
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.skipped is True
    reloaded = read_scheduler_config(str(config_path))
    assert reloaded.skip_next_run is False
    assert reloaded.enabled_markets == ["omxh", "omxs"]
    assert reloaded.osakedata_db_path == str(osakedata_db)
    assert reloaded.analysis_db_path == str(analysis_db)
    assert reloaded.run_time == "05:30"
    assert reloaded.timezone == "Europe/Helsinki"


def test_scheduler_runner_skip_next_run_does_not_create_per_market_logs(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    log_dir = tmp_path / "logs"
    config_path = _write_config(
        tmp_path,
        enabled_markets=["omxh", "omxs"],
        log_dir=log_dir,
        skip_next_run=True,
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.skipped is True
    assert list(log_dir.glob("stock_update_omxh_*.log")) == []
    assert list(log_dir.glob("stock_update_omxs_*.log")) == []


def test_scheduler_runner_skip_next_run_reset_write_failure_propagates(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path, enabled_markets=["omxh", "omxs"], skip_next_run=True
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.write_scheduler_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed")),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        run_scheduler_config(config_path=str(config_path))


def test_scheduler_status_path_returns_log_dir_status_json_path():
    assert (
        scheduler_status_path("/tmp/logs")
        == "/tmp/logs/stock_update_scheduler_status.json"
    )


def test_scheduler_lock_path_returns_log_dir_lock_path():
    assert scheduler_lock_path("/tmp/logs") == "/tmp/logs/stock_update_scheduler.lock"


def test_read_scheduler_status_returns_none_when_file_missing(tmp_path):
    assert read_scheduler_status(str(tmp_path / "missing_logs")) is None


def test_scheduler_status_write_creates_log_dir_if_missing(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    log_dir = tmp_path / "missing_logs"
    config_path = _write_config(
        tmp_path,
        enabled_markets=["omxh"],
        log_dir=log_dir,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    run_scheduler_config(config_path=str(config_path))

    assert log_dir.exists()
    assert Path(scheduler_status_path(str(log_dir))).exists()


def test_scheduler_runner_status_file_written_for_normal_run(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))
    status = read_scheduler_status(str(tmp_path / "logs"))

    assert status is not None
    assert status["is_running"] is False
    assert status["last_status"] == STATUS_OK
    assert status["summary_json_path"] == result.summary_json_path
    assert status["current_market"] is None


def test_scheduler_runner_lock_conflict_raises_and_runs_no_markets(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.acquire_scheduler_lock",
        lambda log_dir: (_ for _ in ()).throw(
            SchedulerAlreadyRunningError("already running")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: (_ for _ in ()).throw(
            AssertionError("market run should not be called")
        ),
    )

    with pytest.raises(SchedulerAlreadyRunningError, match="already running"):
        run_scheduler_config(config_path=str(config_path))


def test_scheduler_runner_lock_conflict_does_not_consume_skip_next_run(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"], skip_next_run=True)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.acquire_scheduler_lock",
        lambda log_dir: (_ for _ in ()).throw(
            SchedulerAlreadyRunningError("already running")
        ),
    )

    with pytest.raises(SchedulerAlreadyRunningError, match="already running"):
        run_scheduler_config(config_path=str(config_path))

    reloaded = read_scheduler_config(str(config_path))
    assert reloaded.skip_next_run is True


def test_scheduler_runner_lock_conflict_does_not_write_summary_json(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path, enabled_markets=["omxh"], log_dir=log_dir)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.acquire_scheduler_lock",
        lambda log_dir: (_ for _ in ()).throw(
            SchedulerAlreadyRunningError("already running")
        ),
    )

    with pytest.raises(SchedulerAlreadyRunningError, match="already running"):
        run_scheduler_config(config_path=str(config_path))

    assert list(log_dir.glob("stock_update_scheduler_summary_*.json")) == []


def test_scheduler_lock_is_released_after_normal_release(tmp_path):
    log_dir = tmp_path / "logs"

    first_lock = acquire_scheduler_lock(str(log_dir))
    release_scheduler_lock(first_lock)
    second_lock = acquire_scheduler_lock(str(log_dir))

    assert Path(scheduler_lock_path(str(log_dir))).exists()
    release_scheduler_lock(second_lock)


def test_scheduler_runner_status_current_market_updates_during_execution(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])
    seen_statuses = []

    def fake_run(self, **kwargs):
        status = read_scheduler_status(str(tmp_path / "logs"))
        seen_statuses.append((kwargs["market"], status["current_market"]))
        return StockUpdateResult(market=kwargs["market"], status=STATUS_OK)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        fake_run,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    run_scheduler_config(config_path=str(config_path))

    assert seen_statuses == [("omxh", "omxh"), ("omxs", "omxs")]


def test_scheduler_runner_skip_next_run_writes_final_ok_status(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path, enabled_markets=["omxh", "omxs"], skip_next_run=True
    )

    result = run_scheduler_config(config_path=str(config_path))
    status = read_scheduler_status(str(tmp_path / "logs"))

    assert result.skipped is True
    assert status["is_running"] is False
    assert status["last_status"] == STATUS_OK
    assert status["summary_json_path"] == result.summary_json_path
    assert status["error"] is None


def test_scheduler_runner_failed_market_final_status_is_failed(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh", "omxs"])

    def fake_run(self, **kwargs):
        if kwargs["market"] == "omxh":
            raise RuntimeError("boom")
        return StockUpdateResult(market=kwargs["market"], status=STATUS_OK)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        fake_run,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))
    status = read_scheduler_status(str(tmp_path / "logs"))

    assert result.overall_status == STATUS_FAILED
    assert status["is_running"] is False
    assert status["last_status"] == STATUS_FAILED
    assert status["current_market"] is None
    assert status["summary_json_path"] == result.summary_json_path


def test_scheduler_runner_unexpected_scheduler_exception_writes_failed_status(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["omxh"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._write_summary_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("summary write failed")),
    )

    with pytest.raises(RuntimeError, match="summary write failed"):
        run_scheduler_config(config_path=str(config_path))

    status = read_scheduler_status(str(tmp_path / "logs"))
    assert status["is_running"] is False
    assert status["last_status"] == STATUS_FAILED
    assert "summary write failed" in status["error"]
