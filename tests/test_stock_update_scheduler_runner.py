from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.scheduler import runner as scheduler_runner
from rawcandle.scheduler.config import (
    DEFAULT_DATACENTER_ENRICHMENT_TAXONOMY_VERSION,
    DEFAULT_DATACENTER_ENRICHMENT_WATCHLIST_FILE,
    create_default_scheduler_config,
    read_scheduler_config,
    scheduler_config_from_dict,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    DatacenterDashboardPostStepResult,
    DatacenterPostStepConfig,
    DatacenterSignalDateResolution,
    SchedulerDashboardConfigInspection,
    SchedulerEnrichmentPlanInspection,
    SchedulerAlreadyRunningError,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    inspect_scheduler_enrichment_plan,
    _resolve_datacenter_signal_date,
    _resolve_market_technical_relevance_tickers,
    _resolve_latest_valid_ohlcv_date_for_market,
    _resolve_technical_relevance_end_date,
    acquire_scheduler_lock,
    inspect_scheduler_dashboard_config,
    read_scheduler_status,
    release_scheduler_lock,
    run_scheduler_config,
    scheduler_lock_path,
    scheduler_status_path,
)
from services.stock_update_service import StockUpdateResult


def _touch(path):
    path.write_text("", encoding="utf-8")


def _create_osakedata_with_rows(path, rows):
    import sqlite3

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _create_group_index_dates_db(path, rows):
    import sqlite3

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_group_index_daily (
                index_date TEXT,
                taxonomy_version TEXT,
                group_type TEXT,
                group_name TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO dc_group_index_daily (index_date, taxonomy_version, group_type, group_name)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _write_taxonomy_csv(path: Path, rows: list[tuple[str, str, str, str, str, int, int, str]]) -> None:
    lines = [
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes"
    ]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_datacenter_signal_date_resolution(
    *,
    signal_date: str | None,
    requested_calendar_signal_date: str,
    candidate_count: int = 1,
    ticker_valid_date_count: int = 1,
    group_valid_date_count: int = 1,
    min_price_ticker_count: int = 59,
    skip_reason: str = "",
) -> DatacenterSignalDateResolution:
    return DatacenterSignalDateResolution(
        signal_date=signal_date,
        requested_calendar_signal_date=requested_calendar_signal_date,
        signal_date_source="DOWNSTREAM_VALID_DATE",
        signal_date_resolution="TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT",
        min_price_ticker_count=min_price_ticker_count,
        candidate_count=candidate_count,
        ticker_valid_date_count=ticker_valid_date_count,
        group_valid_date_count=group_valid_date_count,
        skip_reason=skip_reason,
    )


def _build_technical_relevance_end_date_resolution(
    *,
    end_date: str | None,
    requested_calendar_signal_date: str,
    candidate_count: int = 1,
    ticker_valid_date_count: int = 1,
    min_price_ticker_count: int = 59,
    skip_reason: str = "",
):
    return scheduler_runner.TechnicalRelevanceEndDateResolution(
        end_date=end_date,
        requested_calendar_signal_date=requested_calendar_signal_date,
        end_date_source="TECHNICAL_RELEVANCE_TAXONOMY_VALID_DATE",
        end_date_resolution="TAXONOMY_VALID_DATE_WITH_MIN_TICKER_COUNT",
        min_price_ticker_count=min_price_ticker_count,
        candidate_count=candidate_count,
        ticker_valid_date_count=ticker_valid_date_count,
        skip_reason=skip_reason,
    )


def _prepare_ready_datacenter_reports_dir(tmp_path, report_date: str = "2026-05-22"):
    reports_dir = tmp_path / "swing_reports"
    reports_dir.mkdir()
    for prefix in ("daily", "rolling_2", "rolling_5", "rolling_30"):
        (reports_dir / f"datacenter_{prefix}_{report_date}_0000_full.md").write_text(
            "report",
            encoding="utf-8",
        )
    return reports_dir


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _stub_datacenter_dashboard_post_step(monkeypatch, request):
    if "real_datacenter_dashboard" in request.fixturenames:
        return

    def fake_dashboard_post_step(**kwargs):
        config = kwargs["config"]
        return DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=config.datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z",
            skip_reason="",
            error=None,
        )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_post_step",
        fake_dashboard_post_step,
    )


@pytest.fixture
def real_datacenter_dashboard():
    return None


def _write_config(
    tmp_path,
    *,
    enabled_markets=None,
    osakedata_db=None,
    analysis_db=None,
    log_dir=None,
    skip_next_run=False,
    technical_relevance_enabled=False,
    datacenter_dashboard_enabled=True,
    datacenter_dashboard_db=None,
    datacenter_dashboard_html_output_dir=None,
    datacenter_dashboard_source_mode=None,
    datacenter_enrichment_enabled=None,
    datacenter_enrichment_apply_migrations=None,
    datacenter_enrichment_taxonomy_version=None,
    datacenter_enrichment_watchlist_file=None,
    datacenter_enrichment_write_mode=None,
    datacenter_dashboard_fallback_to_reports=None,
    datacenter_dashboard_run_acceptance_report=None,
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
    config.technical_relevance_enabled = technical_relevance_enabled
    config.datacenter_dashboard_enabled = datacenter_dashboard_enabled
    if datacenter_dashboard_db is not None:
        config.datacenter_dashboard_db = str(datacenter_dashboard_db)
    if datacenter_dashboard_html_output_dir is not None:
        config.datacenter_dashboard_html_output_dir = str(datacenter_dashboard_html_output_dir)
    if datacenter_dashboard_source_mode is not None:
        config.datacenter_dashboard_source_mode = datacenter_dashboard_source_mode
    if datacenter_enrichment_enabled is not None:
        config.datacenter_enrichment_enabled = datacenter_enrichment_enabled
    if datacenter_enrichment_apply_migrations is not None:
        config.datacenter_enrichment_apply_migrations = datacenter_enrichment_apply_migrations
    if datacenter_enrichment_taxonomy_version is not None:
        config.datacenter_enrichment_taxonomy_version = datacenter_enrichment_taxonomy_version
    if datacenter_enrichment_watchlist_file is not None:
        config.datacenter_enrichment_watchlist_file = str(datacenter_enrichment_watchlist_file)
    if datacenter_enrichment_write_mode is not None:
        config.datacenter_enrichment_write_mode = datacenter_enrichment_write_mode
    if datacenter_dashboard_fallback_to_reports is not None:
        config.datacenter_dashboard_fallback_to_reports = datacenter_dashboard_fallback_to_reports
    if datacenter_dashboard_run_acceptance_report is not None:
        config.datacenter_dashboard_run_acceptance_report = datacenter_dashboard_run_acceptance_report
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter post-step should not run")
        ),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter post-step should not run")
        ),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
    )

    result = run_scheduler_config(config_path=str(config_path))
    log_path = result.market_results[0].log_path
    log_text = (tmp_path / "logs" / Path(log_path).name).read_text(encoding="utf-8")

    assert Path(log_path).exists()
    assert log_path.endswith(".txt")
    assert "run_started_at_local=" in log_text
    assert "run_finished_at_local=" in log_text
    assert "run_started_at_utc=" not in log_text
    assert "SUMMARY market=omxh" in log_text
    assert "market=omxh" in log_text


def test_scheduler_runner_uses_minute_precision_log_filename(tmp_path, monkeypatch):
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
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert Path(result.market_results[0].log_path).name.startswith("stock_update_omxh_")
    assert Path(result.market_results[0].log_path).name.endswith(".txt")
    assert "T" in Path(result.market_results[0].log_path).name
    assert Path(result.market_results[0].log_path).stem.split("_")[-1].endswith("Z")
    assert len(Path(result.market_results[0].log_path).stem.split("_")[-1]) == 14


def test_scheduler_runner_avoids_overwriting_same_minute_log_filename(tmp_path, monkeypatch):
    import datetime as real_datetime
    original_datetime_class = real_datetime.datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "stock_update_omxh_20260516T1900Z.txt").write_text("old", encoding="utf-8")
    config_path = _write_config(tmp_path, enabled_markets=["omxh"], log_dir=log_dir)

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return original_datetime_class(2026, 5, 16, 19, 0, 30, tzinfo=tz)

    monkeypatch.setattr("rawcandle.scheduler.runner.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert Path(result.market_results[0].log_path).name == "stock_update_omxh_20260516T1900Z_2.txt"
    assert (log_dir / "stock_update_omxh_20260516T1900Z.txt").read_text(encoding="utf-8") == "old"


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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
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
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0),
    )

    run_scheduler_config(config_path=str(config_path))


def test_resolve_latest_valid_ohlcv_date_for_market_returns_latest_non_null_close(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_with_rows(
        db_path,
        [
            ("AAA", "2026-05-14", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("AAA", "2026-05-15", 1.0, 1.0, 1.0, 2.0, 100, "usa"),
        ],
    )

    assert _resolve_latest_valid_ohlcv_date_for_market(str(db_path), "usa") == "2026-05-15"


def test_resolve_latest_valid_ohlcv_date_for_market_ignores_null_close_rows(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_with_rows(
        db_path,
        [
            ("AAA", "2026-05-14", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("AAA", "2026-05-15", 1.0, 1.0, 1.0, None, 100, "usa"),
        ],
    )

    assert _resolve_latest_valid_ohlcv_date_for_market(str(db_path), "usa") == "2026-05-14"


def test_resolve_latest_valid_ohlcv_date_for_market_respects_market_filter(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_with_rows(
        db_path,
        [
            ("AAA", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("BBB", "2026-05-22", 1.0, 1.0, 1.0, 1.0, 100, "omxh"),
        ],
    )

    assert _resolve_latest_valid_ohlcv_date_for_market(str(db_path), "usa") == "2026-05-15"


def test_resolve_market_technical_relevance_tickers_returns_sorted_market_tickers(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_with_rows(
        db_path,
        [
            ("BBB", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("AAA", "2026-05-14", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("", "2026-05-16", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("CCC", "2026-05-16", 1.0, 1.0, 1.0, None, 100, "usa"),
            ("OMX", "2026-05-16", 1.0, 1.0, 1.0, 1.0, 100, "omxh"),
        ],
    )

    assert _resolve_market_technical_relevance_tickers(str(db_path), "usa") == ["AAA", "BBB"]


def test_resolve_technical_relevance_end_date_returns_latest_taxonomy_valid_day(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            *[
                (ticker, "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", ticker, "LayerA", "SubA", "CORE", 1, 1, "")
            for ticker in primary_tickers
        ],
    )

    resolution = _resolve_technical_relevance_end_date(
        price_db_path=str(osakedata_db),
        market="usa",
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        requested_calendar_signal_date="2026-05-28",
        expected_ticker_count=25,
    )

    assert resolution.end_date == "2026-05-28"
    assert resolution.end_date_source == "TECHNICAL_RELEVANCE_TAXONOMY_VALID_DATE"
    assert resolution.end_date_resolution == "TAXONOMY_VALID_DATE_WITH_MIN_TICKER_COUNT"
    assert resolution.candidate_count == 2
    assert resolution.ticker_valid_date_count == 2
    assert resolution.skip_reason == ""


def test_resolve_technical_relevance_end_date_rejects_outlier_latest_day(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            (primary_tickers[0], "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("BTC-USD", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", ticker, "LayerA", "SubA", "CORE", 1, 1, "")
            for ticker in primary_tickers
        ],
    )

    resolution = _resolve_technical_relevance_end_date(
        price_db_path=str(osakedata_db),
        market="usa",
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        requested_calendar_signal_date="2026-05-28",
        expected_ticker_count=25,
    )

    assert resolution.end_date == "2026-05-27"
    assert resolution.ticker_valid_date_count == 2
    assert resolution.candidate_count == 2


def test_resolve_datacenter_signal_date_uses_latest_valid_price_date_when_group_index_lags(
    tmp_path,
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            *[
                (ticker, "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
        ],
    )
    _create_group_index_dates_db(
        analysis_db,
        [
            ("2026-05-27", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", ticker, "LayerA", "SubA", "CORE", 1, 1, "")
            for ticker in primary_tickers
        ],
    )

    resolution = _resolve_datacenter_signal_date(
        price_db_path=str(osakedata_db),
        analysis_db_path=str(analysis_db),
        market="usa",
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-05-01",
        requested_calendar_signal_date="2026-05-28",
        expected_ticker_count=8,
    )

    assert resolution.signal_date == "2026-05-28"
    assert resolution.signal_date_source == "DOWNSTREAM_VALID_DATE"
    assert (
        resolution.signal_date_resolution
        == "TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT"
    )
    assert resolution.candidate_count == 2
    assert resolution.ticker_valid_date_count == 2
    assert resolution.group_valid_date_count == 1
    assert resolution.skip_reason == ""


def test_resolve_datacenter_signal_date_rejects_outlier_latest_day_below_min_ticker_count(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            (primary_tickers[0], "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("BTC-USD", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _create_group_index_dates_db(
        analysis_db,
        [
            ("2026-05-27", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
            ("2026-05-28", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", ticker, "LayerA", "SubA", "CORE", 1, 1, "")
            for ticker in primary_tickers
        ],
    )

    resolution = _resolve_datacenter_signal_date(
        price_db_path=str(osakedata_db),
        analysis_db_path=str(analysis_db),
        market="usa",
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-05-01",
        requested_calendar_signal_date="2026-05-28",
        expected_ticker_count=12,
    )

    assert resolution.min_price_ticker_count == 25
    assert resolution.signal_date == "2026-05-27"
    assert resolution.candidate_count == 2


def test_resolve_datacenter_signal_date_never_returns_date_after_requested_calendar_signal_date(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            *[
                (ticker, "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
        ],
    )
    _create_group_index_dates_db(
        analysis_db,
        [
            ("2026-05-27", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
            ("2026-05-28", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", ticker, "LayerA", "SubA", "CORE", 1, 1, "")
            for ticker in primary_tickers
        ],
    )

    resolution = _resolve_datacenter_signal_date(
        price_db_path=str(osakedata_db),
        analysis_db_path=str(analysis_db),
        market="usa",
        taxonomy_csv_path=str(taxonomy_csv),
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-05-01",
        requested_calendar_signal_date="2026-05-27",
        expected_ticker_count=8,
    )

    assert resolution.signal_date == "2026-05-27"
    assert resolution.signal_date <= resolution.requested_calendar_signal_date


def test_run_datacenter_post_step_skips_with_exact_reason_when_no_candidate_passes(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    log_dir = tmp_path / "logs"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("AAA", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _create_group_index_dates_db(analysis_db, [])
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            ("DC_TAXONOMY_FULL_V1", "AAA", "LayerA", "SubA", "CORE", 1, 1, ""),
        ],
    )
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        osakedata_db=osakedata_db,
        analysis_db=analysis_db,
        log_dir=log_dir,
    )
    config = read_scheduler_config(str(config_path))

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv=str(taxonomy_csv),
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2026-05-01",
            index_base_date="2020-01-01",
            output_dir=str(tmp_path / "reports"),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )

    result = scheduler_runner._run_datacenter_post_step(
        config=config,
        target_market="usa",
        effective_today="2026-05-29",
    )

    assert result.status == "SKIPPED"
    assert result.signal_date is None
    assert result.signal_date_source == "DOWNSTREAM_VALID_DATE"
    assert (
        result.signal_date_resolution
        == "TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT"
    )
    assert result.error == "NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE"
    log_text = Path(result.log_path).read_text(encoding="utf-8")
    assert "skip_reason=NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE" in log_text
    assert "signal_date_candidate_count=1" in log_text
    assert "ticker_valid_date_count=1" in log_text
    assert "group_valid_date_count=0" in log_text


def test_run_datacenter_post_step_uses_latest_valid_price_date_in_pipeline_command(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    log_dir = tmp_path / "logs"
    reports_dir = tmp_path / "reports"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (f"TICK{i:02d}", "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for i in range(1, 26)
            ],
            *[
                (f"TICK{i:02d}", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for i in range(1, 26)
            ],
        ],
    )
    _create_group_index_dates_db(
        analysis_db,
        [
            ("2026-05-27", "DC_TAXONOMY_FULL_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ],
    )
    _write_taxonomy_csv(
        taxonomy_csv,
        [
            (
                "DC_TAXONOMY_FULL_V1",
                f"TICK{i:02d}",
                "LayerA",
                "SubA",
                "CORE",
                1,
                1,
                "",
            )
            for i in range(1, 26)
        ],
    )
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        osakedata_db=osakedata_db,
        analysis_db=analysis_db,
        log_dir=log_dir,
    )
    config = read_scheduler_config(str(config_path))
    calls = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv=str(taxonomy_csv),
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2026-05-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=8,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda command, **kwargs: calls.append(command)
        or _FakeCompletedProcess(
            0,
            "\n".join(
                [
                    "SUMMARY audit_validation_status=OK",
                    "SUMMARY daily_report_path=/tmp/daily.md",
                    "SUMMARY daily_report_csv_path=/tmp/daily.csv",
                    "SUMMARY rolling_30_report_path=/tmp/rolling30.md",
                    "SUMMARY rolling_30_report_csv_path=/tmp/rolling30.csv",
                    "SUMMARY rolling_5_report_path=/tmp/rolling5.md",
                    "SUMMARY rolling_5_report_csv_path=/tmp/rolling5.csv",
                    "SUMMARY rolling_2_report_path=/tmp/rolling2.md",
                    "SUMMARY rolling_2_report_csv_path=/tmp/rolling2.csv",
                    "",
                ]
            ),
        ),
    )

    result = scheduler_runner._run_datacenter_post_step(
        config=config,
        target_market="usa",
        effective_today="2026-05-29",
    )

    assert result.status == "OK"
    assert result.signal_date == "2026-05-28"
    command = calls[0]
    assert command[command.index("--signal-date") + 1] == "2026-05-28"
    assert result.requested_calendar_signal_date == "2026-05-28"


def test_scheduler_runner_runs_datacenter_post_step_once_for_usa_success(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("USA_A", "2026-05-16", 1.0, 1.0, 1.0, 2.0, 100, "usa"),
            ("OMX_A", "2026-05-20", 1.0, 1.0, 1.0, 3.0, 100, "omxh"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    calls = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    def fake_subprocess_run(command, cwd, check, capture_output, text):
        calls.append({"command": command, "cwd": cwd, "check": check})
        return _FakeCompletedProcess(
            0,
            "\n".join(
                [
                    "SUMMARY audit_validation_status=OK",
                    "SUMMARY daily_report_path=/tmp/daily.md",
                    "SUMMARY daily_report_csv_path=/tmp/daily.csv",
                    "SUMMARY rolling_30_report_path=/tmp/rolling30.md",
                    "SUMMARY rolling_30_report_csv_path=/tmp/rolling30.csv",
                    "SUMMARY rolling_5_report_path=/tmp/rolling5.md",
                    "SUMMARY rolling_5_report_csv_path=/tmp/rolling5.csv",
                    "SUMMARY rolling_2_report_path=/tmp/rolling2.md",
                    "SUMMARY rolling_2_report_csv_path=/tmp/rolling2.csv",
                    "",
                ]
            ),
        )

    monkeypatch.setattr("rawcandle.scheduler.runner.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert len(calls) == 1
    command = calls[0]["command"]
    assert calls[0]["check"] is False
    assert calls[0]["cwd"] == str(Path(__file__).resolve().parents[1])
    assert command[:2] == ["python3", "run_datacenter_swing_pipeline.py"]
    assert "--market" in command and command[command.index("--market") + 1] == "usa"
    assert "--price-db" in command and command[command.index("--price-db") + 1] == str(osakedata_db)
    assert "--analysis-db" in command and command[command.index("--analysis-db") + 1] == str(analysis_db)
    assert "--taxonomy-csv" in command and command[command.index("--taxonomy-csv") + 1] == "data/datacenter_ecosystem_taxonomy_full_v1.csv"
    assert "--taxonomy-version" in command and command[command.index("--taxonomy-version") + 1] == "DC_TAXONOMY_FULL_V1"
    assert "--start-date" in command and command[command.index("--start-date") + 1] == "2025-08-01"
    assert "--index-base-date" in command and command[command.index("--index-base-date") + 1] == "2020-01-01"
    assert "--output-dir" in command and command[command.index("--output-dir") + 1] == "/home/kalle/projects/rawcandle/swing_reports"
    assert "--expected-ticker-count" in command and command[command.index("--expected-ticker-count") + 1] == "236"
    assert "--expected-group-count" in command and command[command.index("--expected-group-count") + 1] == "54"
    assert "--expected-synthetic-ohlc-count" in command and command[command.index("--expected-synthetic-ohlc-count") + 1] == "53"
    assert "--signal-date" in command and command[command.index("--signal-date") + 1] == "2026-05-16"
    assert result.datacenter_pipeline_attempted == 1
    assert result.datacenter_pipeline_status == "OK"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_signal_date == "2026-05-16"
    assert result.datacenter_pipeline_signal_date_source == "DOWNSTREAM_VALID_DATE"
    assert (
        result.datacenter_pipeline_signal_date_resolution
        == "TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT"
    )
    assert result.datacenter_pipeline_audit_validation_status == "OK"
    assert result.datacenter_pipeline_daily_report_path == "/tmp/daily.md"
    assert result.datacenter_pipeline_daily_report_csv_path == "/tmp/daily.csv"
    assert result.datacenter_pipeline_rolling_30_report_path == "/tmp/rolling30.md"
    assert result.datacenter_pipeline_rolling_30_report_csv_path == "/tmp/rolling30.csv"
    assert result.datacenter_pipeline_rolling_5_report_path == "/tmp/rolling5.md"
    assert result.datacenter_pipeline_rolling_5_report_csv_path == "/tmp/rolling5.csv"
    assert result.datacenter_pipeline_rolling_2_report_path == "/tmp/rolling2.md"
    assert result.datacenter_pipeline_rolling_2_report_csv_path == "/tmp/rolling2.csv"
    assert result.datacenter_pipeline_weekly_report_path is None
    assert result.datacenter_pipeline_weekly_report_csv_path is None
    assert result.datacenter_pipeline_log_path.endswith(".txt")
    log_path = Path(result.datacenter_pipeline_log_path)
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "signal_date_source=DOWNSTREAM_VALID_DATE" in log_text
    assert "SUMMARY audit_validation_status=OK" in log_text
    assert "=== STDOUT ===" in log_text
    assert "=== STDERR ===" in log_text
    assert result.overall_status == STATUS_OK
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["datacenter_pipeline_signal_date"] == "2026-05-16"
    assert payload["datacenter_pipeline_signal_date_source"] == "DOWNSTREAM_VALID_DATE"
    assert payload["datacenter_pipeline_daily_report_path"] == "/tmp/daily.md"
    assert payload["datacenter_pipeline_rolling_30_report_path"] == "/tmp/rolling30.md"
    assert payload["datacenter_pipeline_rolling_5_report_path"] == "/tmp/rolling5.md"
    assert payload["datacenter_pipeline_rolling_2_report_path"] == "/tmp/rolling2.md"
    assert payload["datacenter_pipeline_weekly_report_path"] is None


def test_scheduler_runner_technical_relevance_disabled_by_default(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("technical relevance should be disabled")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_enabled is False
    assert result.technical_relevance_status == "DISABLED"
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["technical_relevance_status"] == "DISABLED"


def test_scheduler_runner_runs_technical_relevance_before_datacenter(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("BBB", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("AAA", "2026-05-16", 1.0, 1.0, 1.0, 2.0, 100, "usa"),
            ("TAXONOMY_ONLY", "2026-05-16", 1.0, 1.0, 1.0, 3.0, 100, "usa"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    calls = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: calls.append(("market_update", kwargs["market"]))
        or StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    def fake_technical_relevance(**kwargs):
        calls.append(("technical_relevance", kwargs["tickers"], kwargs["start_date"], kwargs["end_date"], kwargs["run_id"]))
        class _Summary:
            records_written = 7
            relevant_count = 4
            weak_context_count = 2
            noise_count = 1
            unknown_signal_count = 0
            missing_dow_context_count = 0
            missing_bar_index_count = 0
        return _Summary()

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        fake_technical_relevance,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: calls.append(("datacenter",))
        or _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert calls[0] == ("market_update", "usa")
    assert calls[1][0] == "technical_relevance"
    assert calls[2] == ("datacenter",)
    assert calls[1][1] == ["AAA", "BBB", "TAXONOMY_ONLY"]
    assert calls[1][2] == "2026-04-01"
    assert calls[1][3] == "2026-05-16"
    assert calls[1][4] == "TECH_SIGNAL_REL_DAILY_USA_2026_05_16"
    assert result.technical_relevance_status == "OK"
    assert result.technical_relevance_records_written == 7
    assert result.technical_relevance_relevant_count == 4
    assert result.datacenter_pipeline_status == "OK"
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["technical_relevance_status"] == "OK"
    assert payload["technical_relevance_run_id"] == "TECH_SIGNAL_REL_DAILY_USA_2026_05_16"
    assert payload["technical_relevance_start_date"] == "2026-04-01"
    assert payload["technical_relevance_end_date"] == "2026-05-16"


def test_scheduler_runner_technical_relevance_run_id_uses_resolver_approved_date(
    tmp_path, monkeypatch
):
    import datetime as real_datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            (primary_tickers[0], "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("BTC-USD", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    class FixedDateTime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 29, 8, 30, 0, tzinfo=tz)

    calls = []

    monkeypatch.setattr("rawcandle.scheduler.runner.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    def fake_technical_relevance(**kwargs):
        calls.append(kwargs)

        class _Summary:
            records_written = 1
            relevant_count = 1
            weak_context_count = 0
            noise_count = 0
            unknown_signal_count = 0
            missing_dow_context_count = 0
            missing_bar_index_count = 0

        return _Summary()

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        fake_technical_relevance,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-27",
            requested_calendar_signal_date="2026-05-28",
            candidate_count=2,
            ticker_valid_date_count=2,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-27",
            requested_calendar_signal_date="2026-05-28",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert calls[0]["end_date"] == "2026-05-27"
    assert calls[0]["run_id"] == "TECH_SIGNAL_REL_DAILY_USA_2026_05_27"
    assert result.technical_relevance_end_date == "2026-05-27"
    assert result.technical_relevance_run_id == "TECH_SIGNAL_REL_DAILY_USA_2026_05_27"
    assert result.technical_relevance_requested_calendar_signal_date == "2026-05-28"
    assert result.technical_relevance_end_date_source == "TECHNICAL_RELEVANCE_TAXONOMY_VALID_DATE"
    assert (
        result.technical_relevance_end_date_resolution
        == "TAXONOMY_VALID_DATE_WITH_MIN_TICKER_COUNT"
    )


def test_scheduler_runner_technical_relevance_skips_existing_run_id(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [("AAA", "2026-05-16", 1.0, 1.0, 1.0, 2.0, 100, "usa")],
    )
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
        analysis_db=analysis_db,
    )
    _touch(analysis_db)

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("technical relevance service should not run for duplicate run_id")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.read_relevance_run",
        lambda conn, run_id: {"run_id": run_id},
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_attempted == 1
    assert result.technical_relevance_status == "SKIPPED_EXISTING_RUN"
    assert result.technical_relevance_skip_reason == "RUN_ID_ALREADY_EXISTS"
    assert result.technical_relevance_records_written == 0


def test_scheduler_runner_technical_relevance_existing_run_id_uses_resolver_approved_date(
    tmp_path, monkeypatch
):
    import datetime as real_datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    primary_tickers = [f"TICK{i:02d}" for i in range(1, 26)]
    _create_osakedata_with_rows(
        osakedata_db,
        [
            *[
                (ticker, "2026-05-27", 1.0, 1.0, 1.0, 1.0, 100, "usa")
                for ticker in primary_tickers
            ],
            (primary_tickers[0], "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("BTC-USD", "2026-05-28", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    class FixedDateTime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 29, 8, 30, 0, tzinfo=tz)

    monkeypatch.setattr("rawcandle.scheduler.runner.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("technical relevance service should not run for duplicate run_id")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.read_relevance_run",
        lambda conn, run_id: {"run_id": run_id},
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-27",
            requested_calendar_signal_date="2026-05-28",
            candidate_count=2,
            ticker_valid_date_count=2,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-27",
            requested_calendar_signal_date="2026-05-28",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_status == "SKIPPED_EXISTING_RUN"
    assert result.technical_relevance_run_id == "TECH_SIGNAL_REL_DAILY_USA_2026_05_27"
    assert result.technical_relevance_end_date == "2026-05-27"
    assert result.technical_relevance_skip_reason == "RUN_ID_ALREADY_EXISTS"


def test_scheduler_runner_technical_relevance_skips_when_market_phase_failed(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_FAILED),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_status == "SKIPPED"
    assert result.technical_relevance_skip_reason == "MARKET_UPDATE_FAILED"
    assert result.datacenter_pipeline_status == "SKIPPED"


def test_scheduler_runner_technical_relevance_skips_when_usa_not_enabled(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["omxh"],
        technical_relevance_enabled=True,
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

    assert result.technical_relevance_status == "SKIPPED"
    assert result.technical_relevance_skip_reason == "USA_NOT_ENABLED"


def test_scheduler_runner_technical_relevance_skips_when_no_valid_ohlcv_date(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [("AAA", "2026-05-16", 1.0, 1.0, 1.0, None, 100, "usa")],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
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

    assert result.technical_relevance_status == "SKIPPED"
    assert result.technical_relevance_skip_reason == "NO_VALID_TECHNICAL_RELEVANCE_END_DATE"


def test_scheduler_runner_technical_relevance_skips_when_no_tickers_for_market(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [("", "2026-05-16", 1.0, 1.0, 1.0, 1.0, 100, "usa")],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_status == "SKIPPED"
    assert result.technical_relevance_skip_reason == "NO_TICKERS_FOR_MARKET"


def test_scheduler_runner_technical_relevance_failure_fails_scheduler(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [("AAA", "2026-05-16", 1.0, 1.0, 1.0, 2.0, 100, "usa")],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        technical_relevance_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_technical_signal_relevance_for_tickers",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tech rel boom")),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_technical_relevance_end_date",
        lambda **kwargs: _build_technical_relevance_end_date_resolution(
            end_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.technical_relevance_status == "FAILED"
    assert result.technical_relevance_error == "tech rel boom"
    assert result.datacenter_pipeline_status == "OK"
    assert result.overall_status == STATUS_FAILED


def test_scheduler_runner_runs_datacenter_post_step_for_ok_with_warnings(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(
            market=kwargs["market"], status=STATUS_OK_WITH_WARNINGS
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            0, "SUMMARY audit_validation_status=WARN\n"
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-15",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_pipeline_attempted == 1
    assert result.datacenter_pipeline_status == "OK"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_signal_date == "2026-05-15"
    assert result.datacenter_pipeline_audit_validation_status == "WARN"
    assert result.datacenter_pipeline_log_path.endswith(".txt")
    assert result.overall_status == STATUS_OK_WITH_WARNINGS


def test_scheduler_runner_skips_datacenter_post_step_when_market_phase_failed(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_FAILED),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter post-step should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_pipeline_attempted == 0
    assert result.datacenter_pipeline_status == "SKIPPED"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_audit_validation_status == "SKIPPED"
    assert result.datacenter_pipeline_log_path == ""
    assert result.datacenter_pipeline_daily_report_path is None
    assert result.datacenter_pipeline_rolling_30_report_path is None
    assert result.datacenter_pipeline_rolling_5_report_path is None
    assert result.datacenter_pipeline_rolling_2_report_path is None
    assert result.datacenter_pipeline_weekly_report_path is None
    assert result.overall_status == STATUS_FAILED


def test_scheduler_runner_skips_datacenter_post_step_when_usa_not_enabled(
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
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter post-step should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_pipeline_attempted == 0
    assert result.datacenter_pipeline_status == "SKIPPED"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_audit_validation_status == "SKIPPED"
    assert result.datacenter_pipeline_log_path == ""
    assert result.overall_status == STATUS_OK


def test_scheduler_runner_derives_previous_signal_date_for_datacenter_post_step(
    tmp_path, monkeypatch
):
    import datetime as real_datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("OMX_A", "2026-05-17", 1.0, 1.0, 1.0, 1.0, 100, "omxh"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    class FixedDateTime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 16, 8, 30, 0, tzinfo=tz)

    calls = []

    monkeypatch.setattr("rawcandle.scheduler.runner.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda command, **kwargs: calls.append(command)
        or _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-15",
            requested_calendar_signal_date="2026-05-15",
        ),
    )

    run_scheduler_config(config_path=str(config_path))

    command = calls[0]
    assert command[command.index("--signal-date") + 1] == "2026-05-15"


def test_scheduler_runner_uses_latest_valid_ohlcv_date_not_today_minus_one_for_weekend_like_case(
    tmp_path, monkeypatch
):
    import datetime as real_datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
            ("USA_A", "2026-05-17", 1.0, 1.0, 1.0, None, 100, "usa"),
            ("OMXS_A", "2026-05-18", 1.0, 1.0, 1.0, 1.0, 100, "omxs"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    class FixedDateTime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 18, 8, 30, 0, tzinfo=tz)

    calls = []

    monkeypatch.setattr("rawcandle.scheduler.runner.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda command, **kwargs: calls.append(command)
        or _FakeCompletedProcess(0, "SUMMARY audit_validation_status=OK\n"),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-15",
            requested_calendar_signal_date="2026-05-17",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    command = calls[0]
    assert command[command.index("--signal-date") + 1] == "2026-05-15"
    assert result.datacenter_pipeline_requested_calendar_signal_date == "2026-05-17"


def test_scheduler_runner_skips_datacenter_post_step_when_no_valid_ohlcv_date_for_usa(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, None, 100, "usa"),
            ("OMX_A", "2026-05-20", 1.0, 1.0, 1.0, 1.0, 100, "omxh"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter subprocess should not run without a valid USA signal date")
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date=None,
            requested_calendar_signal_date="2026-05-27",
            candidate_count=0,
            ticker_valid_date_count=0,
            group_valid_date_count=0,
            skip_reason="NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_pipeline_attempted == 0
    assert result.datacenter_pipeline_status == "SKIPPED"
    assert result.datacenter_pipeline_signal_date == "NONE"
    assert result.datacenter_pipeline_signal_date_source == "DOWNSTREAM_VALID_DATE"
    assert result.datacenter_pipeline_error == "NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE"
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["datacenter_pipeline_signal_date"] == "NONE"
    assert payload["datacenter_pipeline_error"] == "NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE"


def test_scheduler_runner_datacenter_post_step_failure_fails_scheduler(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [
            ("USA_A", "2026-05-15", 1.0, 1.0, 1.0, 1.0, 100, "usa"),
        ],
    )
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            7,
            "\n".join(
                [
                    "SUMMARY audit_validation_status=FAIL",
                    "SUMMARY daily_report_path=/tmp/daily_failed.md",
                    "SUMMARY rolling_30_report_path=/tmp/rolling30_failed.md",
                    "",
                ]
            ),
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-15",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_pipeline_attempted == 1
    assert result.datacenter_pipeline_status == "FAILED"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_audit_validation_status == "FAIL"
    assert result.datacenter_pipeline_daily_report_path == "/tmp/daily_failed.md"
    assert result.datacenter_pipeline_daily_report_csv_path is None
    assert result.datacenter_pipeline_rolling_30_report_path == "/tmp/rolling30_failed.md"
    assert result.datacenter_pipeline_rolling_5_report_path is None
    assert result.datacenter_pipeline_log_path.endswith(".txt")
    assert result.overall_status == STATUS_FAILED


def test_scheduler_runner_skip_next_run_marks_datacenter_post_step_skipped(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    log_dir = tmp_path / "logs"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        skip_next_run=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("datacenter post-step should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.skipped is True
    assert result.datacenter_pipeline_attempted == 0
    assert result.datacenter_pipeline_status == "SKIPPED"
    assert result.datacenter_pipeline_market == "usa"
    assert result.datacenter_pipeline_audit_validation_status == "SKIPPED"
    assert result.datacenter_pipeline_log_path == ""
    assert result.datacenter_pipeline_daily_report_path is None
    assert result.datacenter_pipeline_rolling_30_report_path is None
    assert result.datacenter_pipeline_rolling_5_report_path is None
    assert result.datacenter_pipeline_rolling_2_report_path is None
    assert result.datacenter_pipeline_weekly_report_path is None

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


def test_scheduler_runner_dashboard_skipped_when_usa_not_enabled(tmp_path, monkeypatch):
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

    assert result.datacenter_dashboard_attempted == 0
    assert result.datacenter_dashboard_status == "SKIPPED"
    assert result.datacenter_dashboard_md_reports_status == "SKIPPED"
    assert result.datacenter_dashboard_skip_reason == "USA_NOT_ENABLED"


def test_scheduler_runner_dashboard_skipped_when_market_phase_failed(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_FAILED),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_dashboard_attempted == 0
    assert result.datacenter_dashboard_status == "SKIPPED"
    assert result.datacenter_dashboard_md_reports_status == "SKIPPED"
    assert result.datacenter_dashboard_skip_reason == "MARKET_PHASE_FAILED"


def test_scheduler_runner_dashboard_runs_after_datacenter_reports(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "reports"
    html_dir.mkdir()
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
    )

    calls = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )

    def fake_dashboard_post_step(**kwargs):
        calls.append(kwargs)
        return DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z",
            skip_reason="",
            error=None,
        )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_post_step",
        fake_dashboard_post_step,
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert len(calls) == 1
    assert calls[0]["render_html"] is True
    assert calls[0]["report_date"] == "2026-05-22"
    assert calls[0]["reports_dir"] == "/home/kalle/projects/rawcandle/swing_reports"
    assert calls[0]["config"].datacenter_dashboard_db == str(dashboard_db)
    assert calls[0]["html_output"] == str(html_dir / "datacenter_dashboard_2026-05-22.html")
    assert result.datacenter_dashboard_attempted == 1
    assert result.datacenter_dashboard_status == "OK"
    assert result.datacenter_dashboard_md_reports_status == "OK"
    assert result.datacenter_dashboard_source_reports_available == 4
    assert result.datacenter_dashboard_dashboard_db == str(dashboard_db)
    assert result.datacenter_dashboard_html_output_path == str(
        html_dir / "datacenter_dashboard_2026-05-22.html"
    )
    assert result.datacenter_dashboard_run_id == "ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z"
    assert result.datacenter_dashboard_source_mode == "reports"
    assert result.datacenter_enrichment_attempted == 0
    assert result.datacenter_enrichment_status == "SKIPPED"
    assert result.datacenter_dashboard_final_source_mode == "reports"


def test_scheduler_runner_dashboard_not_attempted_when_datacenter_pipeline_failed(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="FAILED",
            market="usa",
            signal_date="2026-05-22",
            error="pipeline failed",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_post_step",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("dashboard build/render should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_dashboard_attempted == 0
    assert result.datacenter_dashboard_status == "SKIPPED"
    assert result.datacenter_dashboard_md_reports_status == "FAILED"
    assert result.datacenter_dashboard_skip_reason == "DATACENTER_PIPELINE_FAILED"
    assert result.datacenter_dashboard_error == "pipeline failed"


def test_scheduler_runner_dashboard_fails_when_md_reports_missing(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "reports"
    html_dir.mkdir()
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(tmp_path / "empty_reports"),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    (tmp_path / "empty_reports").mkdir()

    result = run_scheduler_config(config_path=str(config_path))

    assert result.datacenter_dashboard_attempted == 0
    assert result.datacenter_dashboard_status == "FAILED"
    assert result.datacenter_dashboard_md_reports_status == "MISSING"
    assert result.datacenter_dashboard_source_reports_available == 0
    assert result.datacenter_dashboard_skip_reason == "DATACENTER_MD_REPORTS_MISSING"


def test_scheduler_runner_dashboard_failure_after_md_reports_is_visible(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="FAILED",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z",
            skip_reason="DASHBOARD_BUILD_FAILED",
            error="build failed",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_FAILED
    assert result.datacenter_dashboard_attempted == 1
    assert result.datacenter_dashboard_status == "FAILED"
    assert result.datacenter_dashboard_md_reports_status == "OK"
    assert result.datacenter_dashboard_skip_reason == "DASHBOARD_BUILD_FAILED"
    assert result.datacenter_dashboard_error == "build failed"


def test_scheduler_runner_enrichment_source_mode_disabled_keeps_reports_behavior(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=False,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )

    calls = []

    def fake_reports_post_step(**kwargs):
        calls.append(kwargs)
        return DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            skip_reason="",
            source_mode="reports",
            final_source_mode="reports",
            error=None,
        )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        fake_reports_post_step,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_enrichment_post_step",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("enrichment path should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert len(calls) == 1
    assert result.datacenter_dashboard_source_mode == "enrichment"
    assert result.datacenter_enrichment_attempted == 0
    assert result.datacenter_enrichment_status == "SKIPPED"
    assert result.datacenter_dashboard_final_source_mode == "reports"


def test_scheduler_runner_enrichment_enabled_executes_steps_in_order(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_enrichment_taxonomy_version="DC_TAXONOMY_FULL_V1",
        datacenter_enrichment_write_mode="replace-date",
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_latest_dashboard_run_id",
        lambda dashboard_db, ecosystem_code, report_date: "REPORTS_RUN",
    )

    calls = []

    def fake_run_python_cli_main(cli_main, args):
        calls.append(list(args))
        joined = " ".join(args)
        if "--watchlist-file" in joined and "--mode" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if "--format text" in joined and "--output-json" not in joined and "--reports-dashboard-db" not in joined:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if "--source-mode enrichment" in joined:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        if "--input-mode structured" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY ecosystem_dashboard_build.status=OK",
                    "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_DASH_RUN",
                ]
            )
        if "--reports-dashboard-db" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_acceptance_report.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_acceptance_report.blockers=0",
                    "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation=READY_FOR_SCHEDULER_SWITCH_PLANNING",
                ]
            )
        return 1, ""

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_python_cli_main",
        fake_run_python_cli_main,
    )

    result = run_scheduler_config(config_path=str(config_path))

    joined_calls = [" ".join(args) for args in calls]
    assert any("--watchlist-file" in call for call in joined_calls)
    assert any("--output-json" in call for call in joined_calls)
    assert any("--input-mode structured" in call for call in joined_calls)
    assert result.datacenter_enrichment_attempted == 1
    assert result.datacenter_enrichment_status == "OK"
    assert result.datacenter_dashboard_enrichment_export_status == "OK"
    assert result.datacenter_dashboard_structured_build_status == "OK"
    assert result.datacenter_dashboard_acceptance_report_status == "OK"
    assert result.datacenter_dashboard_acceptance_report_blockers == "0"
    assert (
        result.datacenter_dashboard_acceptance_report_recommendation
        == "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    )
    assert result.datacenter_dashboard_fallback_used == 0
    assert result.datacenter_dashboard_final_source_mode == "enrichment"


def test_scheduler_runner_enrichment_write_failure_falls_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_dashboard_fallback_to_reports=True,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    cli_calls = []

    def fake_cli(cli_main, args):
        cli_calls.append(list(args))
        return 1, ""

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)

    fallback_calls = []
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: fallback_calls.append(kwargs)
        or DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert len(fallback_calls) == 1
    assert len(cli_calls) == 1
    assert result.datacenter_enrichment_attempted == 1
    assert result.datacenter_enrichment_status == "FAILED"
    assert result.datacenter_dashboard_enrichment_export_status == "SKIPPED"
    assert result.datacenter_dashboard_structured_build_status == "SKIPPED"
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_final_source_mode == "reports"
    assert result.datacenter_dashboard_status == "OK"


def test_scheduler_runner_enrichment_audit_failure_falls_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_dashboard_fallback_to_reports=True,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    call_index = {"value": 0}

    def fake_cli(cli_main, args):
        idx = call_index["value"]
        call_index["value"] += 1
        if idx == 0:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        return 1, ""

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.datacenter_enrichment_attempted == 1
    assert result.datacenter_enrichment_status == "FAILED"
    assert result.datacenter_dashboard_enrichment_export_status == "SKIPPED"
    assert result.datacenter_dashboard_structured_build_status == "SKIPPED"
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_final_source_mode == "reports"
    assert result.datacenter_dashboard_status == "OK"


def test_scheduler_runner_enrichment_export_failure_falls_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_dashboard_fallback_to_reports=True,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )

    call_index = {"value": 0}

    def fake_cli(cli_main, args):
        idx = call_index["value"]
        call_index["value"] += 1
        if idx == 0:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if idx == 1:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        return 1, ""

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_status == "OK"
    assert result.datacenter_dashboard_enrichment_export_status == "FAILED"
    assert result.datacenter_dashboard_structured_build_status == "SKIPPED"
    assert result.datacenter_dashboard_final_source_mode == "reports"


def test_scheduler_runner_structured_build_failure_falls_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_dashboard_fallback_to_reports=True,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    call_index = {"value": 0}

    def fake_cli(cli_main, args):
        idx = call_index["value"]
        call_index["value"] += 1
        if idx == 0:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if idx == 1:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if idx == 2:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        return 1, ""

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.datacenter_dashboard_structured_build_status == "FAILED"
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_status == "OK"
    assert result.datacenter_dashboard_final_source_mode == "reports"


def test_scheduler_runner_enrichment_failure_without_fallback_marks_failed(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_dashboard_fallback_to_reports=False,
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_python_cli_main",
        lambda cli_main, args: (1, ""),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("fallback should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.overall_status == STATUS_FAILED
    assert result.datacenter_dashboard_status == "FAILED"
    assert result.datacenter_dashboard_fallback_used == 0
    assert result.datacenter_dashboard_final_source_mode == "enrichment"


def test_scheduler_runner_acceptance_report_failure_falls_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_latest_dashboard_run_id",
        lambda dashboard_db, ecosystem_code, report_date: "REPORTS_RUN",
    )
    call_index = {"value": 0}

    def fake_cli(cli_main, args):
        idx = call_index["value"]
        call_index["value"] += 1
        if idx == 0:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if idx == 1:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if idx == 2:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        if idx == 3:
            return 0, "\n".join(
                [
                    "SUMMARY ecosystem_dashboard_build.status=OK",
                    "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_DASH_RUN",
                ]
            )
        return 1, ""

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.datacenter_dashboard_acceptance_report_status == "FAILED"
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_final_source_mode == "reports"
    assert result.datacenter_dashboard_status == "OK"


def test_scheduler_runner_acceptance_blockers_fall_back_when_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_latest_dashboard_run_id",
        lambda dashboard_db, ecosystem_code, report_date: "REPORTS_RUN",
    )
    call_index = {"value": 0}

    def fake_cli(cli_main, args):
        idx = call_index["value"]
        call_index["value"] += 1
        if idx == 0:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if idx == 1:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if idx == 2:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        if idx == 3:
            return 0, "\n".join(
                [
                    "SUMMARY ecosystem_dashboard_build.status=OK",
                    "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_DASH_RUN",
                ]
            )
        return 0, "\n".join(
            [
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.blockers=1",
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation=NOT_READY_NEEDS_MORE_FIXES",
            ]
        )

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: DatacenterDashboardPostStepResult(
            attempted=1,
            status="OK",
            dashboard_db=kwargs["config"].datacenter_dashboard_db,
            report_date=kwargs["report_date"],
            md_reports_status="OK",
            source_reports_available=4,
            html_output_path=kwargs["html_output"],
            run_id="REPORTS_RUN",
            source_mode="reports",
            final_source_mode="reports",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.datacenter_dashboard_acceptance_report_status == "FAILED"
    assert result.datacenter_dashboard_acceptance_report_blockers == "1"
    assert (
        result.datacenter_dashboard_acceptance_report_recommendation
        == "NOT_READY_NEEDS_MORE_FIXES"
    )
    assert result.datacenter_dashboard_fallback_used == 1
    assert result.datacenter_dashboard_final_source_mode == "reports"
    assert result.datacenter_dashboard_error == "ACCEPTANCE_BLOCKERS"


def test_scheduler_runner_acceptance_blockers_fail_without_fallback(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_dashboard_fallback_to_reports=False,
        datacenter_dashboard_run_acceptance_report=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_latest_dashboard_run_id",
        lambda dashboard_db, ecosystem_code, report_date: "REPORTS_RUN",
    )

    def fake_cli(cli_main, args):
        joined = " ".join(args)
        if "--watchlist-file" in joined and "--mode" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if "--format text" in joined and "--output-json" not in joined and "--reports-dashboard-db" not in joined:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if "--source-mode enrichment" in joined:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        if "--input-mode structured" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY ecosystem_dashboard_build.status=OK",
                    "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_DASH_RUN",
                ]
            )
        return 0, "\n".join(
            [
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.blockers=1",
                "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation=NOT_READY_NEEDS_MORE_FIXES",
            ]
        )

    monkeypatch.setattr("rawcandle.scheduler.runner._run_python_cli_main", fake_cli)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_dashboard_reports_post_step",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("fallback should not run")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))
    assert result.overall_status == STATUS_FAILED
    assert result.datacenter_dashboard_status == "FAILED"
    assert result.datacenter_dashboard_acceptance_report_status == "FAILED"
    assert result.datacenter_dashboard_acceptance_report_blockers == "1"
    assert result.datacenter_dashboard_fallback_used == 0
    assert result.datacenter_dashboard_final_source_mode == "enrichment"
    assert result.datacenter_dashboard_error == "ACCEPTANCE_BLOCKERS"


def test_scheduler_runner_never_runs_migrations_even_when_flag_enabled(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    reports_dir = _prepare_ready_datacenter_reports_dir(tmp_path)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_apply_migrations=True,
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=False,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: scheduler_runner.DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-05-22",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_post_step_config",
        lambda market: scheduler_runner.DatacenterPostStepConfig(
            market="usa",
            taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            start_date="2025-08-01",
            index_base_date="2020-01-01",
            output_dir=str(reports_dir),
            expected_ticker_count=236,
            expected_group_count=54,
            expected_synthetic_ohlc_count=53,
        ),
    )

    calls = []

    def fake_run_python_cli_main(cli_main, args):
        calls.append(list(args))
        joined = " ".join(args)
        if "--watchlist-file" in joined and "--mode" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY datacenter_dashboard_enrichment_write.status=OK",
                    "SUMMARY datacenter_dashboard_enrichment_write.run_id=ENRICH_RUN",
                    "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY",
                ]
            )
        if "--format text" in joined and "--output-json" not in joined and "--reports-dashboard-db" not in joined:
            return 0, "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY"
        if "--source-mode enrichment" in joined:
            return 0, "SUMMARY datacenter_dashboard_analysis_db_export.status=OK"
        if "--input-mode structured" in joined:
            return 0, "\n".join(
                [
                    "SUMMARY ecosystem_dashboard_build.status=OK",
                    "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_DASH_RUN",
                ]
            )
        return 1, ""

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_python_cli_main",
        fake_run_python_cli_main,
    )

    result = run_scheduler_config(config_path=str(config_path))

    joined_calls = [" ".join(args) for args in calls]
    assert all("migration" not in call.lower() for call in joined_calls)
    assert result.datacenter_enrichment_attempted == 1
    assert result.datacenter_dashboard_status == "OK"
    assert result.datacenter_dashboard_final_source_mode == "enrichment"


def test_scheduler_runner_dashboard_helper_uses_dashboard_db_build_and_html_args(
    tmp_path, monkeypatch, real_datacenter_dashboard
):
    reports_dir = tmp_path / "swing_reports"
    reports_dir.mkdir()
    report_date = "2026-05-22"
    for prefix in ("daily", "rolling_2", "rolling_5", "rolling_30"):
        (reports_dir / f"datacenter_{prefix}_{report_date}_0000_full.md").write_text(
            "report",
            encoding="utf-8",
        )

    build_calls = []
    html_calls = []

    monkeypatch.setattr(
        "dev_tools.run_ecosystem_dashboard_build.generate_ecosystem_dashboard_build",
        lambda **kwargs: build_calls.append(kwargs)
        or ("ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z", []),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.generate_datacenter_dashboard_html_file",
        lambda **kwargs: html_calls.append(kwargs),
    )

    config = create_default_scheduler_config(
        osakedata_db_path=str(tmp_path / "osakedata.db"),
        analysis_db_path=str(tmp_path / "analysis.db"),
        log_dir=str(tmp_path / "logs"),
    )
    config.datacenter_dashboard_db = str(tmp_path / "ecosystem_dashboard.db")
    config.datacenter_dashboard_html_output_dir = str(tmp_path / "html")
    (tmp_path / "html").mkdir()

    result = scheduler_runner._run_datacenter_dashboard_post_step(
        config=config,
        reports_dir=str(reports_dir),
        report_date=report_date,
        render_html=True,
        html_output=str(tmp_path / "html" / f"datacenter_dashboard_{report_date}.html"),
    )

    assert result.status == "OK"
    assert build_calls == [
        {
            "dashboard_db": str(tmp_path / "ecosystem_dashboard.db"),
            "ecosystem_code": "DATACENTER",
            "reports_dir": str(reports_dir),
            "report_date": report_date,
            "mode": "replace-date",
            "run_id": None,
        }
    ]
    assert html_calls == [
        {
            "dashboard_db": str(tmp_path / "ecosystem_dashboard.db"),
            "ecosystem_code": "DATACENTER",
            "run_id": "ECO_DASHBOARD_DATACENTER_2026-05-22_20260525T000000Z",
            "output": str(tmp_path / "html" / f"datacenter_dashboard_{report_date}.html"),
            "report_date": None,
            "title": None,
        }
    ]


def test_inspect_scheduler_dashboard_config_returns_deterministic_plan(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert isinstance(inspection, SchedulerDashboardConfigInspection)
    assert inspection.enabled == 1
    assert inspection.ecosystem_code == "DATACENTER"
    assert inspection.dashboard_db == str(dashboard_db)
    assert inspection.reports_dir == "/home/kalle/projects/rawcandle/swing_reports"
    assert inspection.html_output_dir == str(html_dir)
    assert inspection.expected_report_date == "2026-05-22"
    assert inspection.expected_html_output_path == str(
        html_dir / "datacenter_dashboard_2026-05-22.html"
    )
    assert inspection.mode == "replace-date"
    assert inspection.render_html == 1
    assert inspection.usa_enabled == 1
    assert inspection.datacenter_pipeline_enabled == 1
    assert inspection.skip_next_run == 0
    assert inspection.dashboard_source_mode == "reports"
    assert inspection.enrichment_enabled == 0
    assert inspection.enrichment_apply_migrations == 0
    assert (
        inspection.enrichment_taxonomy_version
        == DEFAULT_DATACENTER_ENRICHMENT_TAXONOMY_VERSION
    )
    assert (
        inspection.enrichment_watchlist_file
        == DEFAULT_DATACENTER_ENRICHMENT_WATCHLIST_FILE
    )
    assert inspection.enrichment_watchlist_file_status in {"OK", "MISSING"}
    assert inspection.enrichment_write_mode == "replace-date"
    assert inspection.dashboard_fallback_to_reports == 1
    assert inspection.dashboard_run_acceptance_report == 0
    assert inspection.enrichment_effective_status == "PLANNING_ONLY"
    assert inspection.warnings == ()
    assert inspection.date_status == "OK"
    assert inspection.status == "OK"


def test_inspect_scheduler_dashboard_config_does_not_create_db_or_html_output(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "missing_dashboard.db"
    html_dir = tmp_path / "html"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
    )

    inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert not dashboard_db.exists()
    assert not (html_dir / "datacenter_dashboard_2026-05-22.html").exists()


def test_inspect_scheduler_dashboard_config_supports_disabled_dashboard(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["omxh"],
        datacenter_dashboard_enabled=False,
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        skip_next_run=True,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert inspection.enabled == 0
    assert inspection.dashboard_db == str(dashboard_db)
    assert inspection.html_output_dir == str(html_dir)
    assert inspection.expected_report_date == "2026-05-22"
    assert inspection.expected_html_output_path == str(
        html_dir / "datacenter_dashboard_2026-05-22.html"
    )
    assert inspection.usa_enabled == 0
    assert inspection.skip_next_run == 1
    assert inspection.status == "OK"


def test_inspect_scheduler_dashboard_config_returns_configured_enrichment_visibility(
    tmp_path,
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_apply_migrations=False,
        datacenter_enrichment_taxonomy_version="DC_TAXONOMY_FULL_V1",
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_enrichment_write_mode="replace-date",
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=True,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert inspection.dashboard_source_mode == "enrichment"
    assert inspection.enrichment_enabled == 1
    assert inspection.enrichment_apply_migrations == 0
    assert inspection.enrichment_taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert inspection.enrichment_watchlist_file == str(watchlist_file)
    assert inspection.enrichment_watchlist_file_status == "OK"
    assert inspection.enrichment_write_mode == "replace-date"
    assert inspection.dashboard_fallback_to_reports == 1
    assert inspection.dashboard_run_acceptance_report == 1
    assert inspection.enrichment_effective_status == "READY"
    assert inspection.warnings == ()


def test_inspect_scheduler_dashboard_config_missing_watchlist_file_is_visible(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    missing_watchlist = tmp_path / "missing_watchlist.txt"
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=missing_watchlist,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert inspection.enrichment_watchlist_file == str(missing_watchlist)
    assert inspection.enrichment_watchlist_file_status == "MISSING"
    assert inspection.enrichment_effective_status == "NOT_READY"
    assert "WATCHLIST_FILE_MISSING" in inspection.warnings
    assert inspection.status == "OK"


def test_invalid_dashboard_source_mode_fails_clearly():
    with pytest.raises(
        ValueError,
        match="datacenter_dashboard_source_mode must be one of",
    ):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                "datacenter_dashboard_source_mode": "bad-mode",
            }
        )


def test_invalid_enrichment_write_mode_fails_clearly():
    with pytest.raises(
        ValueError,
        match="datacenter_enrichment_write_mode must be one of",
    ):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                "datacenter_enrichment_write_mode": "bad-write-mode",
            }
        )


def test_inspect_scheduler_dashboard_config_warns_when_enrichment_source_mode_disabled(
    tmp_path,
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=False,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert inspection.enrichment_effective_status == "DISABLED"
    assert inspection.warnings == ("ENRICHMENT_SOURCE_MODE_CONFIGURED_BUT_DISABLED",)


def test_inspect_scheduler_dashboard_config_warns_when_apply_migrations_enabled(
    tmp_path,
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_enrichment_apply_migrations=True,
    )

    inspection = inspect_scheduler_dashboard_config(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert inspection.enrichment_apply_migrations == 1
    assert "ENRICHMENT_APPLY_MIGRATIONS_NOT_WIRED" in inspection.warnings


def test_inspect_scheduler_enrichment_plan_returns_default_plan_visibility(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert isinstance(plan, SchedulerEnrichmentPlanInspection)
    assert plan.status == "OK"
    assert plan.source_mode == "reports"
    assert plan.enrichment_enabled == 0
    assert plan.effective_status == "PLANNING_ONLY"
    assert plan.expected_signal_date == "2026-05-22"
    assert plan.analysis_db == str(analysis_db)
    assert plan.analysis_db_status == "OK"
    assert plan.dashboard_db == str(dashboard_db)
    assert plan.stage_md_reports_generation == "1:DATACENTER_PIPELINE_ENABLED"
    assert plan.stage_enrichment_write == "0:ENRICHMENT_NOT_ENABLED"
    assert plan.stage_structured_dashboard_build == "0:REPORTS_MODE_REMAINS_ACTIVE"
    assert plan.stage_fallback_reports_build == "1:FALLBACK_ENABLED"
    assert plan.warnings == ()


def test_inspect_scheduler_enrichment_plan_for_configured_enrichment_mode(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    html_dir = tmp_path / "html"
    watchlist_file = tmp_path / "watchlist.txt"
    _touch(osakedata_db)
    _touch(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_db=dashboard_db,
        datacenter_dashboard_html_output_dir=html_dir,
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_apply_migrations=False,
        datacenter_enrichment_taxonomy_version="DC_TAXONOMY_FULL_V1",
        datacenter_enrichment_watchlist_file=watchlist_file,
        datacenter_enrichment_write_mode="replace-date",
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_run_acceptance_report=True,
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert plan.enrichment_enabled == 1
    assert plan.effective_status == "READY"
    assert plan.watchlist_file_status == "OK"
    assert plan.stage_enrichment_write == "1:READY_TO_EXECUTE"
    assert plan.stage_enrichment_export_json == "1:FOLLOWS_ENRICHMENT_WRITE"
    assert plan.stage_structured_dashboard_build == "1:ENRICHMENT_SOURCE_READY"
    assert plan.stage_acceptance_report == "1:CONFIG_ENABLED"
    assert plan.stage_fallback_reports_build == "1:FALLBACK_ENABLED"
    assert "ENRICHMENT_EXECUTION_NOT_WIRED" not in plan.warnings


def test_inspect_scheduler_enrichment_plan_warns_when_source_mode_enrichment_but_disabled(
    tmp_path,
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_dashboard_source_mode="enrichment",
        datacenter_enrichment_enabled=False,
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert plan.effective_status == "DISABLED"
    assert "ENRICHMENT_SOURCE_MODE_CONFIGURED_BUT_DISABLED" in plan.warnings
    assert "ENRICHMENT_EXECUTION_NOT_WIRED" not in plan.warnings


def test_inspect_scheduler_enrichment_plan_warns_when_apply_migrations_true(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_apply_migrations=True,
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert plan.apply_migrations == 1
    assert "APPLY_MIGRATIONS_NOT_WIRED" in plan.warnings


def test_inspect_scheduler_enrichment_plan_warns_when_analysis_db_missing(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    _touch(osakedata_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        analysis_db=tmp_path / "missing_analysis.db",
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert plan.analysis_db_status == "MISSING"
    assert "ANALYSIS_DB_NOT_READY" in plan.warnings


def test_inspect_scheduler_enrichment_plan_warns_when_watchlist_missing(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_enrichment_enabled=True,
        datacenter_enrichment_watchlist_file=tmp_path / "missing_watchlist.txt",
    )

    plan = inspect_scheduler_enrichment_plan(
        config_path=str(config_path),
        effective_today="2026-05-23",
    )

    assert plan.watchlist_file_status == "MISSING"
    assert "WATCHLIST_FILE_MISSING" in plan.warnings
