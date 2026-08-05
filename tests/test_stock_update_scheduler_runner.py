from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.scheduler import runner as scheduler_runner
from rawcandle.scheduler.config import (
    create_default_scheduler_config,
    read_scheduler_config,
    scheduler_config_from_dict,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    DatacenterPostStepConfig,
    DatacenterPostStepResult,
    DatacenterSignalDateResolution,
    ScheduledMarketRunResult,
    SchedulerAlreadyRunningError,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    _resolve_datacenter_signal_date,
    _resolve_market_technical_relevance_tickers,
    _resolve_latest_valid_ohlcv_date_for_market,
    _resolve_technical_relevance_end_date,
    acquire_scheduler_lock,
    read_scheduler_status,
    release_scheduler_lock,
    run_scheduler_config,
    scheduler_lock_path,
    scheduler_status_path,
)
from services.stock_update_service import StockUpdateResult


def _retired_v3_result_prefix() -> str:
    return "v3" + "_reports_"


def _retired_v3_generation_helper_name() -> str:
    return "_run_" + "v3" + "_datacenter_report_generation"


def _retired_v3_default_helper_name() -> str:
    return "_default_" + "v3" + "_reports_post_step_result"


def _retired_v3_config_enabled_key() -> str:
    return "datacenter_" + "v3" + "_reports_enabled"


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


def test_datacenter_post_step_config_derives_expected_counts_from_taxonomy_csv(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy_v2.csv"
    _write_taxonomy_csv(
        taxonomy_path,
        [
            ("DC_TAXONOMY_FULL_V2", "AAA", "LayerA", "SubA", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V2", "BBB", "LayerA", "SubB", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V2", "CCC", "LayerB", "SubC", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V2", "AAA", "LayerB", "SubC", "EXTENDED", 0, 0.5, ""),
        ],
    )
    config = create_default_scheduler_config(
        osakedata_db_path=str(tmp_path / "osakedata.sqlite"),
        analysis_db_path=str(tmp_path / "analysis.sqlite"),
        log_dir=str(tmp_path / "logs"),
    )
    config.datacenter_taxonomy_csv = str(taxonomy_path)
    config.datacenter_taxonomy_version = "DC_TAXONOMY_FULL_V2"

    resolved = scheduler_runner._resolve_datacenter_post_step_config("usa", config)

    assert resolved is not None
    assert resolved.expected_ticker_count == 3
    assert resolved.expected_group_count == 6
    assert resolved.expected_synthetic_ohlc_count == 5


def test_datacenter_post_step_config_accepts_future_taxonomy_counts(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy_v3.csv"
    _write_taxonomy_csv(
        taxonomy_path,
        [
            ("DC_TAXONOMY_FULL_V3", "AAA", "LayerA", "SubA", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V3", "BBB", "LayerB", "SubB", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V3", "CCC", "LayerC", "SubC", "CORE", 1, 1.0, ""),
            ("DC_TAXONOMY_FULL_V3", "DDD", "LayerC", "SubD", "CORE", 1, 1.0, ""),
        ],
    )
    config = create_default_scheduler_config(
        osakedata_db_path=str(tmp_path / "osakedata.sqlite"),
        analysis_db_path=str(tmp_path / "analysis.sqlite"),
        log_dir=str(tmp_path / "logs"),
    )
    config.datacenter_taxonomy_csv = str(taxonomy_path)
    config.datacenter_taxonomy_version = "DC_TAXONOMY_FULL_V3"

    resolved = scheduler_runner._resolve_datacenter_post_step_config("usa", config)

    assert resolved is not None
    assert resolved.expected_ticker_count == 4
    assert resolved.expected_group_count == 8
    assert resolved.expected_synthetic_ohlc_count == 7


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


def _write_config(
    tmp_path,
    *,
    enabled_markets=None,
    osakedata_db=None,
    analysis_db=None,
    log_dir=None,
    skip_next_run=False,
    technical_relevance_enabled=False,
    ec_source_layer_enabled=None,
    ec_source_layer_ecosystem=None,
    ec_source_layer_taxonomy_version=None,
    ec_source_layer_taxonomy_csv=None,
    ec_source_layer_watchlist=None,
    ec_source_layer_backup_dir=None,
    ec_source_layer_mode=None,
    ec_source_layer_require_legacy_reports_success=None,
    ec_source_layer_only_on_new_signal_date=None,
    datacenter_stage2_incremental_enabled=None,
    datacenter_stage2_overlap_trading_days=None,
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
    if ec_source_layer_enabled is not None:
        config.ec_source_layer_enabled = ec_source_layer_enabled
    if ec_source_layer_ecosystem is not None:
        config.ec_source_layer_ecosystem = ec_source_layer_ecosystem
    if ec_source_layer_taxonomy_version is not None:
        config.ec_source_layer_taxonomy_version = ec_source_layer_taxonomy_version
    if ec_source_layer_taxonomy_csv is not None:
        config.ec_source_layer_taxonomy_csv = str(ec_source_layer_taxonomy_csv)
    if ec_source_layer_watchlist is not None:
        config.ec_source_layer_watchlist = str(ec_source_layer_watchlist)
    if ec_source_layer_backup_dir is not None:
        config.ec_source_layer_backup_dir = str(ec_source_layer_backup_dir)
    if ec_source_layer_mode is not None:
        config.ec_source_layer_mode = ec_source_layer_mode
    if ec_source_layer_require_legacy_reports_success is not None:
        config.ec_source_layer_require_legacy_reports_success = (
            ec_source_layer_require_legacy_reports_success
        )
    if ec_source_layer_only_on_new_signal_date is not None:
        config.ec_source_layer_only_on_new_signal_date = (
            ec_source_layer_only_on_new_signal_date
        )
    if datacenter_stage2_incremental_enabled is not None:
        config.datacenter_stage2_incremental_enabled = datacenter_stage2_incremental_enabled
    if datacenter_stage2_overlap_trading_days is not None:
        config.datacenter_stage2_overlap_trading_days = datacenter_stage2_overlap_trading_days
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


def test_scheduler_runner_config_defaults_include_reports_reference_fields():
    config = create_default_scheduler_config(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
    )



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
            watchlist_file=str(tmp_path / "watchlist.txt"),
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
            watchlist_file=str(tmp_path / "watchlist.txt"),
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
                    "SUMMARY watchlist_reconciliation_attempted=true",
                    "SUMMARY watchlist_reconciliation_status=NO_CHANGE",
                    "SUMMARY watchlist_source_reference=/tmp/watchlist.txt",
                    "SUMMARY watchlist_source_sha256=abc123",
                    "SUMMARY watchlist_source_member_count=37",
                    "SUMMARY watchlist_previous_member_count=37",
                    "SUMMARY watchlist_current_member_count=37",
                    "SUMMARY watchlist_added_count=0",
                    "SUMMARY watchlist_removed_count=0",
                    "SUMMARY watchlist_added_tickers=[]",
                    "SUMMARY watchlist_removed_tickers=[]",
                    "SUMMARY watchlist_reconciliation_error=NONE",
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
    assert "--watchlist-file" in command
    assert (
        command[command.index("--watchlist-file") + 1]
        == "watchlists/datacenter_watchlist.txt"
    )
    assert "--stage2-incremental" not in command
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
    assert result.watchlist_reconciliation_attempted is True
    assert result.watchlist_reconciliation_status == "NO_CHANGE"
    assert result.watchlist_source_reference == "/tmp/watchlist.txt"
    assert result.watchlist_source_sha256 == "abc123"
    assert result.watchlist_source_member_count == 37
    assert result.watchlist_previous_member_count == 37
    assert result.watchlist_current_member_count == 37
    assert result.watchlist_added_count == 0
    assert result.watchlist_removed_count == 0
    assert result.watchlist_added_tickers == "[]"
    assert result.watchlist_removed_tickers == "[]"
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
    assert not any(key.startswith(_retired_v3_result_prefix()) for key in payload)


def test_scheduler_runner_datacenter_incremental_config_passes_stage2_flags(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        datacenter_stage2_incremental_enabled=True,
        datacenter_stage2_overlap_trading_days=0,
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market=kwargs["market"], status=STATUS_OK),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.RawCandleApp._format_stock_update_service_result_for_ui",
        lambda self, result: f"UI {result.market}",
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )

    def fake_subprocess_run(command, **_):
        calls.append(command)
        return _FakeCompletedProcess(
            0,
            "\n".join(
                [
                    "SUMMARY audit_validation_status=OK",
                    "SUMMARY stage2_incremental_enabled=true",
                    "SUMMARY stage2_execution_status=EXECUTED",
                    "SUMMARY stage2_actual_materialized_start=2026-05-16",
                    "SUMMARY stage2_actual_materialized_end=2026-05-16",
                    "",
                ]
            ),
        )

    monkeypatch.setattr("rawcandle.scheduler.runner.subprocess.run", fake_subprocess_run)

    result = run_scheduler_config(config_path=str(config_path))

    command = calls[0]
    assert "--stage2-incremental" in command
    assert command[command.index("--stage2-overlap-trading-days") + 1] == "0"
    assert result.overall_status == STATUS_OK


def test_scheduler_runner_datacenter_success_has_no_v3_result_fields(tmp_path, monkeypatch):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_osakedata_with_rows(
        osakedata_db,
        [("USA_A", "2026-05-16", 1.0, 1.0, 1.0, 2.0, 100, "usa")],
    )
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
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
        "rawcandle.scheduler.runner._resolve_datacenter_signal_date",
        lambda **kwargs: _build_datacenter_signal_date_resolution(
            signal_date="2026-05-16",
            requested_calendar_signal_date="2026-05-27",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.subprocess.run",
        lambda *args, **kwargs: _FakeCompletedProcess(
            0,
            "\n".join(
                [
                    "SUMMARY audit_validation_status=OK",
                    "SUMMARY daily_report_path=/tmp/daily.md",
                    "SUMMARY rolling_30_report_path=/tmp/rolling30.md",
                    "SUMMARY rolling_5_report_path=/tmp/rolling5.md",
                    "SUMMARY rolling_2_report_path=/tmp/rolling2.md",
                    "",
                ]
            ),
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert not hasattr(scheduler_runner, "resolve_latest_run")
    assert not hasattr(scheduler_runner, "write_reports")
    assert not hasattr(scheduler_runner, _retired_v3_generation_helper_name())
    assert not hasattr(scheduler_runner, _retired_v3_default_helper_name())
    assert result.datacenter_pipeline_daily_report_path == "/tmp/daily.md"
    assert not any(key.startswith(_retired_v3_result_prefix()) for key in result.__dict__)
    assert result.overall_status == STATUS_OK


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


def test_scheduler_runner_ec_source_layer_disabled_skips_without_call(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(tmp_path, enabled_markets=["usa"])

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("ec refresh should not be called when disabled")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.ec_source_layer_attempted == 0
    assert result.ec_source_layer_status == "SKIPPED"
    assert result.ec_source_layer_skipped_reason == "DISABLED"
    assert result.ec_source_layer_log_path.endswith(".txt")
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=SKIPPED" in log_text
    assert "skipped_reason=DISABLED" in log_text
    assert "ec_bridge_mode=DISABLED" in log_text


@pytest.mark.parametrize(
    ("incremental_enabled", "pipeline_summary", "dc_status", "expected_mode", "expected_reason"),
    [
        (
            False,
            {},
            "OK",
            "LATEST_REFRESH",
            "LEGACY_EC_REFRESH_BEHAVIOR",
        ),
        (
            True,
            {
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-05",
                "stage2_actual_materialized_end": "2026-06-05",
            },
            "OK",
            "LATEST_REFRESH",
            "SINGLE_DATE_MATERIALIZATION",
        ),
        (
            True,
            {
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
            "OK",
            "HISTORICAL_BACKFILL",
            "MULTI_DATE_MATERIALIZATION",
        ),
        (
            True,
            {
                "stage2_execution_status": "SKIPPED_BY_INCREMENTAL_PLAN",
                "stage2_actual_materialized_start": "NONE",
                "stage2_actual_materialized_end": "NONE",
            },
            "OK",
            "SKIPPED_NO_MATERIALIZATION",
            "NO_SUCCESSFUL_MATERIALIZATION",
        ),
        (
            True,
            {
                "stage2_execution_status": "FAILED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
            "OK",
            "SKIPPED_NO_MATERIALIZATION",
            "NO_SUCCESSFUL_MATERIALIZATION",
        ),
        (
            True,
            {
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "bad-date",
                "stage2_actual_materialized_end": "2026-06-05",
            },
            "OK",
            "SKIPPED_NO_MATERIALIZATION",
            "NO_SUCCESSFUL_MATERIALIZATION",
        ),
        (
            True,
            {
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-05",
                "stage2_actual_materialized_end": "2026-06-05",
            },
            "FAILED",
            "SKIPPED_NO_MATERIALIZATION",
            "DATACENTER_PIPELINE_NOT_SUCCESSFUL",
        ),
    ],
)
def test_ec_bridge_decision_model(
    incremental_enabled,
    pipeline_summary,
    dc_status,
    expected_mode,
    expected_reason,
):
    decision = scheduler_runner._build_ec_bridge_decision(
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status=dc_status,
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary=pipeline_summary,
        ),
        stage2_incremental_enabled=incremental_enabled,
    )

    assert decision.bridge_mode == expected_mode
    assert decision.reason_code == expected_reason


def test_ec_bridge_decision_multi_date_range_ends_at_selected_date():
    decision = scheduler_runner._build_ec_bridge_decision(
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
        stage2_incremental_enabled=True,
    )

    assert decision.bridge_mode == "HISTORICAL_BACKFILL"
    assert decision.required_refresh_start == "2026-06-01"
    assert decision.required_refresh_end == "2026-06-05"


def test_scheduler_runner_ec_source_layer_enabled_runs_after_legacy_success(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
    )

    called_kwargs: dict[str, object] = {}

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
        ),
    )

    def fake_refresh(**kwargs):
        called_kwargs.update(kwargs)
        return {
            "attempted": True,
            "status": "REFRESH_COMPLETED",
            "signal_date": "2026-06-05",
            "refresh_mode": "new_selected_date",
            "skipped_reason": None,
            "backup_path": "/tmp/backups/refresh.sqlite",
            "coverage_status": "OK_WITH_WARNINGS",
            "parity_status": "OK_WITH_WARNINGS",
            "total_mismatch_count": 0,
            "ticker_rows": 236,
            "group_signal_rows": 54,
            "synthetic_ohlc_rows": 53,
            "group_index_rows": 54,
            "watermark_rows": 15,
            "error": None,
            "watchlist_membership_status": "DRIFT_DETECTED",
            "watchlist_sync_required": True,
            "watchlist_missing_in_loaded_count": 28,
            "watchlist_loaded_only_count": 7,
        }

    monkeypatch.setattr("rawcandle.scheduler.runner.run_ec_source_layer_refresh", fake_refresh)

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK
    assert result.datacenter_pipeline_daily_report_path == "/tmp/daily.md"
    assert result.ec_source_layer_attempted == 1
    assert result.ec_source_layer_status == "REFRESH_COMPLETED"
    assert result.ec_bridge_mode == "LATEST_REFRESH"
    assert result.ec_bridge_reason == "LEGACY_EC_REFRESH_BEHAVIOR"
    assert result.ec_bridge_status == "OK"
    assert result.ec_bridge_required_start == "2026-06-05"
    assert result.ec_bridge_required_end == "2026-06-05"
    assert result.ec_bridge_watermark_refresh_performed is True
    assert result.ec_bridge_watchlist_membership_status == "DRIFT_DETECTED"
    assert result.ec_bridge_watchlist_sync_required is True
    assert result.ec_bridge_watchlist_missing_in_loaded_count == 28
    assert result.ec_bridge_watchlist_loaded_only_count == 7
    assert result.ec_source_layer_log_path.endswith(".txt")
    assert result.ec_source_layer_backup_path == "/tmp/backups/refresh.sqlite"
    assert result.ec_source_layer_ticker_rows == 236
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=REFRESH_COMPLETED" in log_text
    assert "coverage_status=OK_WITH_WARNINGS" in log_text
    assert "parity_status=OK_WITH_WARNINGS" in log_text
    assert "ec_bridge_mode=LATEST_REFRESH" in log_text
    assert "ec_bridge_status=OK" in log_text
    assert "ec_bridge_watchlist_membership_status=DRIFT_DETECTED" in log_text
    assert "ec_bridge_watchlist_sync_required=true" in log_text
    assert called_kwargs["db_path"] == str(analysis_db)
    assert called_kwargs["confirm_db"] == str(analysis_db)
    assert called_kwargs["allow_replace_date"] is False
    assert called_kwargs["reconcile_watchlist"] is False


def test_scheduler_runner_ec_bridge_single_date_incremental_uses_latest_refresh(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        datacenter_stage2_incremental_enabled=True,
    )
    refresh_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_incremental_enabled": "true",
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-05",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
    )

    def fake_refresh(**kwargs):
        refresh_calls.append(kwargs)
        return {
            "attempted": True,
            "status": "REFRESH_COMPLETED",
            "signal_date": "2026-06-05",
            "refresh_mode": "replace_selected_date",
            "backup_path": "/tmp/backups/refresh.sqlite",
            "coverage_status": "OK",
            "parity_status": "OK",
            "total_mismatch_count": 0,
            "error": None,
        }

    monkeypatch.setattr("rawcandle.scheduler.runner.run_ec_source_layer_refresh", fake_refresh)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_backfill",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("backfill should not run")),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert len(refresh_calls) == 1
    assert refresh_calls[0]["reconcile_watchlist"] is False
    assert result.ec_bridge_mode == "LATEST_REFRESH"
    assert result.ec_bridge_reason == "SINGLE_DATE_MATERIALIZATION"
    assert result.ec_bridge_status == "OK"
    assert result.ec_bridge_watermark_refresh_performed is True


def test_scheduler_runner_ec_bridge_multi_date_uses_backfill_only(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        ec_source_layer_only_on_new_signal_date=True,
        datacenter_stage2_incremental_enabled=True,
    )
    backfill_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_incremental_enabled": "true",
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("latest refresh should not run")),
    )

    def fake_backfill(**kwargs):
        backfill_calls.append(kwargs)
        return {
            "status": "BACKFILL_COMPLETED",
            "date_from": "2026-06-01",
            "date_to": "2026-06-05",
            "backup_path": "/tmp/backups/backfill.sqlite",
            "per_date_results": [
                {"date": "2026-06-01", "coverage_status": "OK", "parity_status": "OK"},
                {"date": "2026-06-05", "coverage_status": "OK_WITH_WARNINGS", "parity_status": "OK"},
            ],
            "total_mismatch_count": 0,
            "error": None,
            "watermark_refresh_performed": True,
            "watermark_advance_status": "OK",
            "watchlist_membership_status": "DRIFT_DETECTED",
            "watchlist_sync_required": True,
            "watchlist_missing_in_loaded_count": 28,
            "watchlist_loaded_only_count": 7,
        }

    monkeypatch.setattr("rawcandle.scheduler.runner.run_ec_source_layer_backfill", fake_backfill)

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK
    assert len(backfill_calls) == 1
    assert backfill_calls[0]["date_from"] == "2026-06-01"
    assert backfill_calls[0]["date_to"] == "2026-06-05"
    assert backfill_calls[0]["ecosystem_code"] == "DATACENTER"
    assert backfill_calls[0]["taxonomy_version_code"] == "DC_TAXONOMY_FULL_V1"
    assert backfill_calls[0]["allow_replace_existing"] is True
    assert backfill_calls[0]["reconcile_watchlist"] is False
    assert result.ec_source_layer_status == "BACKFILL_COMPLETED"
    assert result.ec_source_layer_refresh_mode == "historical_backfill"
    assert result.ec_bridge_mode == "HISTORICAL_BACKFILL"
    assert result.ec_bridge_status == "OK"
    assert result.ec_bridge_required_start == "2026-06-01"
    assert result.ec_bridge_required_end == "2026-06-05"
    assert result.ec_bridge_coverage_status == "OK_WITH_WARNINGS"
    assert result.ec_bridge_parity_status == "OK"
    assert result.ec_bridge_watermark_refresh_performed is True
    assert result.ec_bridge_watchlist_membership_status == "DRIFT_DETECTED"
    assert result.ec_bridge_watchlist_sync_required is True
    assert result.ec_bridge_watchlist_missing_in_loaded_count == 28
    assert result.ec_bridge_watchlist_loaded_only_count == 7
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "ec_bridge_mode=HISTORICAL_BACKFILL" in log_text
    assert "ec_bridge_watermark_refresh_performed=true" in log_text
    assert "ec_bridge_watchlist_membership_status=DRIFT_DETECTED" in log_text


def test_scheduler_runner_ec_bridge_multi_date_failure_warns_and_records_retry_range(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        datacenter_stage2_incremental_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_backfill",
        lambda **kwargs: {
            "status": "BACKFILL_FAILED",
            "date_from": "2026-06-01",
            "date_to": "2026-06-05",
            "backup_path": "/tmp/backups/backfill.sqlite",
            "per_date_results": [
                {"date": "2026-06-01", "coverage_status": "OK", "parity_status": "OK"},
            ],
            "total_mismatch_count": 0,
            "error": "parity failed",
        },
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK_WITH_WARNINGS
    assert result.ec_bridge_mode == "HISTORICAL_BACKFILL"
    assert result.ec_bridge_status == "FAILED"
    assert result.ec_bridge_retry_required is True
    assert result.ec_bridge_required_start == "2026-06-01"
    assert result.ec_bridge_required_end == "2026-06-05"
    assert result.ec_bridge_error == "parity failed"


def test_scheduler_runner_ec_bridge_multi_date_exception_writes_summary(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        datacenter_stage2_incremental_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_backfill",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("backfill exploded")),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK_WITH_WARNINGS
    assert result.ec_source_layer_status == "BACKFILL_FAILED"
    assert result.ec_bridge_status == "FAILED"
    assert result.ec_bridge_retry_required is True
    assert result.ec_bridge_error == "backfill exploded"
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["ec_bridge_required_start"] == "2026-06-01"
    assert payload["ec_bridge_retry_required"] is True


def test_scheduler_runner_ec_bridge_malformed_backfill_output_is_not_success(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        datacenter_stage2_incremental_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_execution_status": "EXECUTED",
                "stage2_actual_materialized_start": "2026-06-01",
                "stage2_actual_materialized_end": "2026-06-05",
            },
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_backfill",
        lambda **kwargs: {
            "status": "BACKFILL_COMPLETED",
            "per_date_results": [],
            "total_mismatch_count": 0,
            "error": None,
        },
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK_WITH_WARNINGS
    assert result.ec_bridge_status == "FAILED"
    assert result.ec_bridge_coverage_status == "NONE"
    assert result.ec_bridge_retry_required is True


def test_scheduler_runner_ec_bridge_skip_no_materialization_invokes_no_ec(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        datacenter_stage2_incremental_enabled=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            pipeline_summary={
                "stage2_execution_status": "SKIPPED_BY_INCREMENTAL_PLAN",
                "stage2_actual_materialized_start": "NONE",
                "stage2_actual_materialized_end": "NONE",
            },
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("refresh should not run")),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_backfill",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("backfill should not run")),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK
    assert result.ec_source_layer_status == "SKIPPED"
    assert result.ec_bridge_mode == "SKIPPED_NO_MATERIALIZATION"
    assert result.ec_bridge_status == "SKIPPED"
    assert result.ec_bridge_reason == "NO_SUCCESSFUL_MATERIALIZATION"


def test_scheduler_runner_finished_at_utc_reflects_post_step_completion(
    tmp_path, monkeypatch
):
    import datetime as real_datetime

    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
    )

    utc_now_values = iter(
        [
            real_datetime.datetime(2026, 6, 7, 0, 0, 0, tzinfo=real_datetime.timezone.utc),
            real_datetime.datetime(2026, 6, 7, 0, 10, 0, tzinfo=real_datetime.timezone.utc),
        ]
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._utc_now",
        lambda: next(utc_now_values),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_technical_relevance_post_step",
        lambda **kwargs: scheduler_runner.TechnicalRelevancePostStepResult(
            attempted=1,
            enabled=True,
            status="OK",
            market="usa",
            run_id="TECH_RUN_20260607",
            start_date="2026-05-01",
            end_date="2026-06-06",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-06",
            daily_report_path="/tmp/daily.md",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_ec_source_layer_refresh_post_step",
        lambda **kwargs: scheduler_runner.EcSourceLayerRefreshPostStepResult(
            attempted=1,
            status="REFRESH_COMPLETED",
            log_path="/tmp/ec_source_layer_usa_20260607T0010Z.txt",
            signal_date="2026-06-06",
            refresh_mode="new_selected_date",
            skipped_reason="NONE",
            backup_path="/tmp/backups/refresh.sqlite",
            coverage_status="OK_WITH_WARNINGS",
            parity_status="OK_WITH_WARNINGS",
            total_mismatch_count=0,
            ticker_rows=236,
            group_signal_rows=54,
            synthetic_ohlc_rows=53,
            group_index_rows=54,
            watermark_rows=15,
            error="NONE",
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.finished_at_utc == "2026-06-07T00:10:00Z"
    assert result.ec_source_layer_status == "REFRESH_COMPLETED"
    assert result.ec_source_layer_backup_path == "/tmp/backups/refresh.sqlite"
    payload = json.loads(Path(result.summary_json_path).read_text(encoding="utf-8"))
    assert payload["finished_at_utc"] == "2026-06-07T00:10:00Z"
    assert payload["ec_source_layer_status"] == "REFRESH_COMPLETED"
    assert payload["ec_source_layer_backup_path"] == "/tmp/backups/refresh.sqlite"


def test_scheduler_runner_ec_source_layer_skipped_keeps_ok_status(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: {
            "attempted": False,
            "status": "REFRESH_SKIPPED",
            "signal_date": "2026-06-05",
            "refresh_mode": "skip_up_to_date",
            "skipped_reason": "planner reported SKIP_UP_TO_DATE",
            "backup_path": None,
            "coverage_status": None,
            "parity_status": None,
            "total_mismatch_count": None,
            "ticker_rows": None,
            "group_signal_rows": None,
            "synthetic_ohlc_rows": None,
            "group_index_rows": None,
            "watermark_rows": None,
            "error": None,
        },
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK
    assert result.ec_source_layer_status == "REFRESH_SKIPPED"
    assert result.ec_bridge_mode == "LATEST_REFRESH"
    assert result.ec_bridge_status == "NOT_REQUIRED"
    assert result.ec_source_layer_log_path.endswith(".txt")
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=REFRESH_SKIPPED" in log_text
    assert "skipped_reason=planner reported SKIP_UP_TO_DATE" in log_text


def test_scheduler_runner_ec_source_layer_failure_degrades_to_warning(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: {
            "attempted": True,
            "status": "REFRESH_FAILED",
            "signal_date": "2026-06-05",
            "refresh_mode": "new_selected_date",
            "skipped_reason": None,
            "backup_path": "/tmp/backups/refresh.sqlite",
            "coverage_status": None,
            "parity_status": None,
            "total_mismatch_count": None,
            "ticker_rows": None,
            "group_signal_rows": None,
            "synthetic_ohlc_rows": None,
            "group_index_rows": None,
            "watermark_rows": None,
            "error": "refresh failed",
        },
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK_WITH_WARNINGS
    assert result.datacenter_pipeline_daily_report_path == "/tmp/daily.md"
    assert result.ec_source_layer_status == "REFRESH_FAILED"
    assert result.ec_bridge_status == "FAILED"
    assert result.ec_bridge_retry_required is True
    assert result.ec_source_layer_error == "refresh failed"
    assert result.ec_source_layer_log_path.endswith(".txt")
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=REFRESH_FAILED" in log_text
    assert "error=refresh failed" in log_text


def test_scheduler_runner_ec_source_layer_exception_writes_log_and_warns(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("refresh exploded")),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.overall_status == STATUS_OK_WITH_WARNINGS
    assert result.ec_source_layer_status == "REFRESH_FAILED"
    assert result.ec_bridge_status == "FAILED"
    assert result.ec_bridge_retry_required is True
    assert result.ec_source_layer_error == "refresh exploded"
    assert result.ec_source_layer_log_path.endswith(".txt")
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=REFRESH_FAILED" in log_text
    assert "error=refresh exploded" in log_text


def test_scheduler_runner_ec_source_layer_skips_when_legacy_failed_and_required(
    tmp_path, monkeypatch
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)
    config_path = _write_config(
        tmp_path,
        enabled_markets=["usa"],
        ec_source_layer_enabled=True,
        ec_source_layer_taxonomy_csv=tmp_path / "taxonomy.csv",
        ec_source_layer_watchlist=tmp_path / "watchlist.txt",
        ec_source_layer_backup_dir=tmp_path / "backups",
        ec_source_layer_require_legacy_reports_success=True,
    )

    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **kwargs: ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="2026-06-07T00:00:00Z",
            finished_at_utc="2026-06-07T00:01:00Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path="/tmp/usa.log",
            summary_lines=["SUMMARY market=usa"],
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_datacenter_post_step",
        lambda **kwargs: DatacenterPostStepResult(
            attempted=1,
            status="FAILED",
            market="usa",
            signal_date="2026-06-05",
            daily_report_path="/tmp/daily.md",
            error="legacy failed",
        ),
    )
    monkeypatch.setattr(
        "rawcandle.scheduler.runner.run_ec_source_layer_refresh",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("ec refresh should not be called when legacy failed")
        ),
    )

    result = run_scheduler_config(config_path=str(config_path))

    assert result.ec_source_layer_attempted == 0
    assert result.ec_source_layer_status == "SKIPPED"
    assert result.ec_source_layer_skipped_reason == "LEGACY_DATACENTER_NOT_READY"
    assert result.ec_source_layer_log_path.endswith(".txt")
    log_text = Path(result.ec_source_layer_log_path).read_text(encoding="utf-8")
    assert "status=SKIPPED" in log_text
    assert "skipped_reason=LEGACY_DATACENTER_NOT_READY" in log_text


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
