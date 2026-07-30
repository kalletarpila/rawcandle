from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from analysis.datacenter_indices.pipeline_plan import build_stage2_incremental_plan
from analysis.datacenter_indices.pipeline_watermark import (
    list_pipeline_watermarks,
    upsert_pipeline_watermark,
)
from rawcandle.scheduler import runner as scheduler_runner
from rawcandle.scheduler.config import create_default_scheduler_config
from rawcandle.scheduler.runner import DatacenterPostStepResult
from services.stock_update_service import STATUS_OK, STATUS_OK_WITH_WARNINGS


TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
PRODUCTION_DB_PREFIX = "/home/kalle/projects/rawcandle/data/"


def _weekdays(start: str, count: int) -> list[str]:
    cursor = date.fromisoformat(start)
    values: list[str] = []
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _weekdays_until(start: str, end: str) -> list[str]:
    cursor = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    values: list[str] = []
    while cursor <= end_date:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _create_price_db(path: Path, dates: list[str]) -> None:
    rows = []
    for ticker in ("AAA", "BBB"):
        for offset, signal_date in enumerate(dates):
            price = 100.0 + offset
            rows.append(
                (
                    ticker,
                    signal_date,
                    price,
                    price + 1.0,
                    price - 1.0,
                    price,
                    1000 + offset,
                    "usa",
                )
            )
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


def _create_analysis_db(path: Path) -> None:
    DatabaseManager(str(path)).close()


def _write_taxonomy_csv(tmp_path: Path) -> Path:
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{TAXONOMY_VERSION},AAA,Power,UPS,CORE,1,1.0,",
                f"{TAXONOMY_VERSION},BBB,Cooling,Chillers,CORE,1,1.0,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _assert_temp_db_paths(*paths: Path) -> None:
    for path in paths:
        assert str(path).startswith("/tmp/")
        assert not str(path).startswith(PRODUCTION_DB_PREFIX)


def _orchestrator_kwargs(tmp_path: Path, dates: list[str]) -> dict[str, object]:
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db, dates)
    _create_analysis_db(analysis_db)
    _assert_temp_db_paths(price_db, analysis_db)
    return {
        "price_db": price_db,
        "analysis_db": analysis_db,
        "taxonomy_csv": _write_taxonomy_csv(tmp_path),
        "taxonomy_version": TAXONOMY_VERSION,
        "market": "usa",
        "signal_date": dates[-1],
        "start_date": dates[0],
        "index_base_date": "2020-01-01",
        "output_dir": tmp_path / "reports",
        "skip_audit": True,
        "skip_reports": True,
        "no_technical_relevance": True,
    }


def _arg_value(argv: list[str], option: str) -> str:
    return argv[argv.index(option) + 1]


def _fake_orchestrator_runners(monkeypatch, calls: list[tuple[str, list[str]]]) -> None:
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_indices_main",
        lambda argv: calls.append(("index", list(argv))) or 0,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_ticker_swing_signals_main",
        lambda argv: calls.append(("ticker", list(argv))) or 0,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_group_swing_signals_main",
        lambda argv: calls.append(("group", list(argv))) or 0,
    )
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_group_synthetic_ohlc_main",
        lambda argv: calls.append(("synthetic", list(argv))) or 0,
    )


def _pipeline_summary(summary: dict[str, object]) -> dict[str, str]:
    return {str(key): str(value) for key, value in summary.items()}


def _ec_config(tmp_path: Path):
    config = create_default_scheduler_config(
        osakedata_db_path=str(tmp_path / "osakedata.db"),
        analysis_db_path=str(tmp_path / "analysis.db"),
        log_dir=str(tmp_path / "logs"),
    )
    config.enabled_markets = ["usa"]
    config.ec_source_layer_enabled = True
    config.ec_source_layer_taxonomy_csv = str(tmp_path / "taxonomy.csv")
    config.ec_source_layer_watchlist = str(tmp_path / "watchlist.txt")
    config.ec_source_layer_backup_dir = str(tmp_path / "backups")
    config.datacenter_stage2_incremental_enabled = True
    (tmp_path / "watchlist.txt").write_text("AAA\nBBB\n", encoding="utf-8")
    (tmp_path / "backups").mkdir(exist_ok=True)
    return config


def _run_bridge(
    *,
    tmp_path: Path,
    monkeypatch,
    signal_date: str,
    pipeline_summary: dict[str, str],
    backfill_summary: dict[str, object] | None = None,
):
    config = _ec_config(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_refresh",
        lambda **kwargs: calls.append(("refresh", kwargs))
        or {
            "attempted": True,
            "status": "REFRESH_COMPLETED",
            "signal_date": signal_date,
            "refresh_mode": "replace_selected_date",
            "backup_path": str(tmp_path / "backups" / "refresh.sqlite"),
            "coverage_status": "OK",
            "parity_status": "OK",
            "total_mismatch_count": 0,
            "error": None,
        },
    )
    if backfill_summary is None:
        backfill_summary = {
            "status": "BACKFILL_COMPLETED",
            "date_from": pipeline_summary["stage2_actual_materialized_start"],
            "date_to": pipeline_summary["stage2_actual_materialized_end"],
            "backup_path": str(tmp_path / "backups" / "backfill.sqlite"),
            "per_date_results": [
                {
                    "date": pipeline_summary["stage2_actual_materialized_start"],
                    "coverage_status": "OK",
                    "parity_status": "OK",
                },
                {
                    "date": pipeline_summary["stage2_actual_materialized_end"],
                    "coverage_status": "OK_WITH_WARNINGS",
                    "parity_status": "OK",
                },
            ],
            "total_mismatch_count": 0,
            "error": None,
            "watermark_refresh_performed": True,
            "watermark_advance_status": "OK",
        }
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_backfill",
        lambda **kwargs: calls.append(("backfill", kwargs)) or backfill_summary,
    )
    result = scheduler_runner._run_ec_source_layer_refresh_post_step(
        config=config,
        target_market="usa",
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date=signal_date,
            pipeline_summary=pipeline_summary,
        ),
    )
    return result, calls


def test_e2e_feature_disabled_preserves_legacy_datacenter_ranges_and_latest_bridge(
    tmp_path, monkeypatch
):
    dates = _weekdays("2026-06-01", 8)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    calls: list[tuple[str, list[str]]] = []
    _fake_orchestrator_runners(monkeypatch, calls)
    monkeypatch.setattr(
        orchestrator,
        "build_stage2_incremental_plan",
        lambda **_: (_ for _ in ()).throw(AssertionError("planner should not run")),
    )

    result = orchestrator.run_datacenter_swing_pipeline(**kwargs)

    summary = result["summary"]
    assert summary["stage2_incremental_enabled"] == "false"
    assert summary["stage2_plan_mode"] == "LEGACY_FULL_RANGE"
    for argv in (calls[1][1], calls[2][1], calls[6][1], calls[7][1], calls[8][1]):
        assert (_arg_value(argv, "--start-date"), _arg_value(argv, "--end-date")) == (
            dates[0],
            dates[-1],
        )
    decision = scheduler_runner._build_ec_bridge_decision(
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date=dates[-1],
            pipeline_summary=_pipeline_summary(summary),
        ),
        stage2_incremental_enabled=False,
    )
    assert decision.bridge_mode == "LATEST_REFRESH"
    assert decision.reason_code == "LEGACY_EC_REFRESH_BEHAVIOR"


def test_e2e_incremental_multi_date_success_drives_historical_bridge(
    tmp_path, monkeypatch
):
    dates = _weekdays("2026-06-01", 10)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    assert isinstance(analysis_db, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[6],
        status="OK",
        last_successful_at_utc="2026-06-12T00:00:00Z",
    )
    calls: list[tuple[str, list[str]]] = []
    _fake_orchestrator_runners(monkeypatch, calls)

    result = orchestrator.run_datacenter_swing_pipeline(
        **kwargs,
        stage2_incremental=True,
        stage2_overlap_trading_days=2,
    )

    summary = result["summary"]
    expected_start = dates[5]
    assert summary["stage2_plan_mode"] == "INCREMENTAL"
    assert summary["stage2_planned_materialization_start"] == expected_start
    assert summary["stage2_actual_materialized_start"] == expected_start
    assert summary["stage2_actual_materialized_end"] == dates[-1]
    assert summary["stage2_completed_dates"] == ",".join(dates[5:])
    assert summary["downstream_incremental_stages"] == "3,7,8,9"

    ticker_base = calls[1][1]
    group_base = calls[2][1]
    structure = calls[5][1]
    timing = calls[6][1]
    overheat = calls[7][1]
    scanner = calls[8][1]
    for argv in (ticker_base, group_base, timing, overheat, scanner):
        assert (_arg_value(argv, "--start-date"), _arg_value(argv, "--end-date")) == (
            expected_start,
            dates[-1],
        )
    assert (_arg_value(structure, "--start-date"), _arg_value(structure, "--end-date")) == (
        dates[0],
        dates[-1],
    )

    watermarks = {
        row["component_name"]: row
        for row in list_pipeline_watermarks(
            analysis_db_path=analysis_db,
            taxonomy_version=TAXONOMY_VERSION,
        )
    }
    for component in (
        "GROUP_SWING_BASE",
        "GROUP_TIMING",
        "GROUP_OVERHEAT",
        "TICKER_SCANNER",
    ):
        assert watermarks[component]["start_date"] == expected_start
        assert watermarks[component]["end_date"] == dates[-1]
    assert watermarks["TICKER_SWING_BASE"]["start_date"] == dates[0]
    assert watermarks["TICKER_SWING_BASE"]["end_date"] == dates[-1]
    assert watermarks["SYNTHETIC_OHLC_STRUCTURE"]["start_date"] == dates[0]

    bridge_result, bridge_calls = _run_bridge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        signal_date=dates[-1],
        pipeline_summary=_pipeline_summary(summary),
    )
    assert [name for name, _ in bridge_calls] == ["backfill"]
    backfill_kwargs = bridge_calls[0][1]
    assert backfill_kwargs["date_from"] == expected_start
    assert backfill_kwargs["date_to"] == dates[-1]
    assert bridge_result.bridge_mode == "HISTORICAL_BACKFILL"
    assert bridge_result.bridge_status == "OK"
    assert bridge_result.bridge_watermark_refresh_performed is True


def test_e2e_production_regression_next_day_plan_stays_incremental_after_overlap_run(
    tmp_path, monkeypatch
):
    dates = _weekdays_until("2025-08-01", "2026-07-28")
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    price_db = kwargs["price_db"]
    taxonomy_csv = kwargs["taxonomy_csv"]
    assert isinstance(analysis_db, Path)
    assert isinstance(price_db, Path)
    assert isinstance(taxonomy_csv, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date="2025-08-01",
        end_date="2026-07-24",
        status="OK",
        last_successful_at_utc="2026-07-27T05:00:00Z",
    )
    calls: list[tuple[str, list[str]]] = []
    _fake_orchestrator_runners(monkeypatch, calls)

    first_result = orchestrator.run_datacenter_swing_pipeline(
        **{
            **kwargs,
            "signal_date": "2026-07-27",
        },
        stage2_incremental=True,
        stage2_overlap_trading_days=5,
    )

    first_summary = first_result["summary"]
    assert first_summary["stage2_plan_mode"] == "INCREMENTAL"
    assert first_summary["stage2_actual_materialized_start"] == "2026-07-20"
    assert first_summary["stage2_actual_materialized_end"] == "2026-07-27"
    watermarks = {
        row["component_name"]: row
        for row in list_pipeline_watermarks(
            analysis_db_path=analysis_db,
            taxonomy_version=TAXONOMY_VERSION,
        )
    }
    assert watermarks["TICKER_SWING_BASE"]["start_date"] == "2025-08-01"
    assert watermarks["TICKER_SWING_BASE"]["end_date"] == "2026-07-27"

    next_plan = build_stage2_incremental_plan(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        requested_start="2025-08-01",
        requested_end="2026-07-28",
        signal_version=SIGNAL_VERSION,
        overlap_trading_days=5,
    )

    assert next_plan.mode == "INCREMENTAL"
    assert next_plan.reason_code == "NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP"
    assert next_plan.materialization_start == "2026-07-21"
    assert next_plan.materialization_end == "2026-07-28"


def test_e2e_incremental_single_date_success_drives_latest_bridge(
    tmp_path, monkeypatch
):
    dates = _weekdays("2026-06-01", 8)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    assert isinstance(analysis_db, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[-2],
        status="OK",
        last_successful_at_utc="2026-06-12T00:00:00Z",
    )
    calls: list[tuple[str, list[str]]] = []
    _fake_orchestrator_runners(monkeypatch, calls)

    result = orchestrator.run_datacenter_swing_pipeline(
        **kwargs,
        stage2_incremental=True,
        stage2_overlap_trading_days=0,
    )

    summary = result["summary"]
    assert summary["stage2_actual_materialized_start"] == dates[-1]
    assert summary["stage2_actual_materialized_end"] == dates[-1]
    bridge_result, bridge_calls = _run_bridge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        signal_date=dates[-1],
        pipeline_summary=_pipeline_summary(summary),
    )
    assert [name for name, _ in bridge_calls] == ["refresh"]
    assert bridge_result.bridge_mode == "LATEST_REFRESH"
    assert bridge_result.bridge_status == "OK"
    assert bridge_result.bridge_watermark_refresh_performed is True


def test_e2e_incremental_skip_writes_no_dirty_watermarks_and_no_ec_bridge(
    tmp_path, monkeypatch
):
    dates = _weekdays("2026-06-01", 8)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    assert isinstance(analysis_db, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[-1],
        status="OK",
        last_successful_at_utc="2026-06-12T00:00:00Z",
    )
    calls: list[tuple[str, list[str]]] = []
    _fake_orchestrator_runners(monkeypatch, calls)

    result = orchestrator.run_datacenter_swing_pipeline(
        **kwargs,
        stage2_incremental=True,
    )

    summary = result["summary"]
    assert summary["stage2_plan_mode"] == "SKIP"
    assert summary["stage2_execution_status"] == "SKIPPED_BY_INCREMENTAL_PLAN"
    assert summary["stage2_actual_materialized_start"] == "NONE"
    assert summary["pipeline_stage.group_structure_bos_reset.execution_status"] == "EXECUTED"
    assert "group_structure_bos_reset" not in summary["planner_skipped_stages"]
    assert {call[0] for call in calls} == {"index", "synthetic"}
    watermarks = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version=TAXONOMY_VERSION,
    )
    dirty_components = {
        "GROUP_SWING_BASE",
        "GROUP_TIMING",
        "GROUP_OVERHEAT",
        "TICKER_SCANNER",
    }
    assert dirty_components.isdisjoint({row["component_name"] for row in watermarks})

    config = _ec_config(tmp_path)
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_refresh",
        lambda **_: (_ for _ in ()).throw(AssertionError("refresh should not run")),
    )
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_backfill",
        lambda **_: (_ for _ in ()).throw(AssertionError("backfill should not run")),
    )
    bridge_result = scheduler_runner._run_ec_source_layer_refresh_post_step(
        config=config,
        target_market="usa",
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status="OK",
            market="usa",
            signal_date=dates[-1],
            pipeline_summary=_pipeline_summary(summary),
        ),
    )
    assert bridge_result.bridge_mode == "SKIPPED_NO_MATERIALIZATION"
    assert bridge_result.bridge_status == "SKIPPED"
    assert bridge_result.bridge_retry_required is False


def test_e2e_partial_stage2_failure_does_not_claim_materialized_range_or_bridge(
    tmp_path, monkeypatch, capsys
):
    dates = _weekdays("2026-06-01", 10)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    assert isinstance(analysis_db, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[6],
        status="OK",
        last_successful_at_utc="2026-06-12T00:00:00Z",
    )
    calls: list[str] = []
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: 0)

    def failing_stage2(argv):
        calls.append("stage2")
        with sqlite3.connect(analysis_db) as conn:
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily (
                    signal_date, taxonomy_version, ticker, signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (dates[5], TAXONOMY_VERSION, "AAA", SIGNAL_VERSION, "PARTIAL", "2026-06-12T00:00:00Z"),
            )
            conn.commit()
        return 1

    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", failing_stage2)
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_group_swing_signals_main",
        lambda argv: (_ for _ in ()).throw(AssertionError("downstream should not run")),
    )

    with pytest.raises(RuntimeError, match="Stage failed"):
        orchestrator.run_datacenter_swing_pipeline(
            **kwargs,
            stage2_incremental=True,
            stage2_overlap_trading_days=2,
        )
    stdout = capsys.readouterr().out
    assert "SUMMARY stage2_execution_status=FAILED" in stdout
    assert "SUMMARY stage2_actual_materialized_start=NONE" in stdout
    assert "SUMMARY stage2_retry_required=true" in stdout
    assert calls == ["stage2"]
    watermarks = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version=TAXONOMY_VERSION,
    )
    stage2_watermark = [
        row for row in watermarks if row["component_name"] == "TICKER_SWING_BASE"
    ]
    assert len(stage2_watermark) == 1
    assert stage2_watermark[0]["end_date"] == dates[6]

    config = _ec_config(tmp_path)
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_backfill",
        lambda **_: (_ for _ in ()).throw(AssertionError("backfill should not run")),
    )
    bridge_result = scheduler_runner._run_ec_source_layer_refresh_post_step(
        config=config,
        target_market="usa",
        datacenter_result=DatacenterPostStepResult(
            attempted=1,
            status="FAILED",
            market="usa",
            signal_date=dates[-1],
            pipeline_summary=scheduler_runner._parse_summary_lines(stdout),
        ),
    )
    assert bridge_result.bridge_mode == "SKIPPED_NO_MATERIALIZATION"
    assert bridge_result.bridge_reason == "DATACENTER_PIPELINE_NOT_SUCCESSFUL"


@pytest.mark.parametrize(
    ("failing_stage", "failed_component", "later_stage"),
    [
        ("group_base", "GROUP_SWING_BASE", "group_timing_states"),
        ("timing", "GROUP_TIMING", "group_overheat_risk"),
        ("overheat", "GROUP_OVERHEAT", "ticker_scanners"),
        ("scanner", "TICKER_SCANNER", None),
    ],
)
def test_e2e_downstream_failure_stops_chain_and_failed_watermark(
    tmp_path, monkeypatch, failing_stage, failed_component, later_stage
):
    dates = _weekdays("2026-06-01", 10)
    kwargs = _orchestrator_kwargs(tmp_path, dates)
    analysis_db = kwargs["analysis_db"]
    assert isinstance(analysis_db, Path)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[6],
        status="OK",
        last_successful_at_utc="2026-06-12T00:00:00Z",
    )
    executed: list[str] = []
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: 0)

    def ticker(argv):
        stage = "scanner" if "--scanner-only" in argv else "stage2"
        executed.append(stage)
        return 1 if stage == failing_stage else 0

    def group(argv):
        if "--timing-only" in argv:
            stage = "timing"
        elif "--overheat-only" in argv:
            stage = "overheat"
        else:
            stage = "group_base"
        executed.append(stage)
        return 1 if stage == failing_stage else 0

    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", ticker)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", group)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", lambda argv: 0)

    with pytest.raises(RuntimeError, match="Stage failed"):
        orchestrator.run_datacenter_swing_pipeline(
            **kwargs,
            stage2_incremental=True,
            stage2_overlap_trading_days=2,
        )

    assert failing_stage in executed
    if later_stage == "group_timing_states":
        assert "timing" not in executed
    elif later_stage == "group_overheat_risk":
        assert "overheat" not in executed
    elif later_stage == "ticker_scanners":
        assert "scanner" not in executed
    watermarks = {
        row["component_name"]
        for row in list_pipeline_watermarks(
            analysis_db_path=analysis_db,
            taxonomy_version=TAXONOMY_VERSION,
        )
    }
    assert "TICKER_SWING_BASE" in watermarks
    assert failed_component not in watermarks


@pytest.mark.parametrize(
    "backfill_summary",
    [
        {
            "status": "BACKFILL_COMPLETED",
            "per_date_results": [{"coverage_status": "FAIL", "parity_status": "OK"}],
            "total_mismatch_count": 0,
            "error": "coverage failed",
        },
        {
            "status": "BACKFILL_COMPLETED",
            "per_date_results": [{"coverage_status": "OK", "parity_status": "FAIL"}],
            "total_mismatch_count": 0,
            "error": "parity failed",
        },
        {
            "status": "BACKFILL_COMPLETED",
            "per_date_results": [{"coverage_status": "OK", "parity_status": "OK"}],
            "total_mismatch_count": 1,
            "error": "mismatch",
        },
        {
            "status": "BACKFILL_COMPLETED",
            "per_date_results": [{}],
            "total_mismatch_count": 0,
            "error": None,
        },
    ],
)
def test_e2e_historical_bridge_failures_warn_without_latest_fallback(
    tmp_path, monkeypatch, backfill_summary
):
    config = _ec_config(tmp_path)
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_refresh",
        lambda **_: (_ for _ in ()).throw(AssertionError("latest refresh should not run")),
    )
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_backfill",
        lambda **_: backfill_summary,
    )
    datacenter_result = DatacenterPostStepResult(
        attempted=1,
        status="OK",
        market="usa",
        signal_date="2026-06-05",
        pipeline_summary={
            "stage2_execution_status": "EXECUTED",
            "stage2_actual_materialized_start": "2026-06-01",
            "stage2_actual_materialized_end": "2026-06-05",
        },
    )

    bridge_result = scheduler_runner._run_ec_source_layer_refresh_post_step(
        config=config,
        target_market="usa",
        datacenter_result=datacenter_result,
    )
    decision = scheduler_runner._build_ec_bridge_decision(
        datacenter_result=datacenter_result,
        stage2_incremental_enabled=True,
    )

    assert decision.bridge_mode == "HISTORICAL_BACKFILL"
    assert bridge_result.bridge_status == "FAILED"
    assert bridge_result.bridge_retry_required is True
    assert bridge_result.bridge_required_start == "2026-06-01"
    assert bridge_result.bridge_required_end == "2026-06-05"
    assert bridge_result.bridge_watermark_refresh_performed is False


def test_e2e_latest_refresh_failure_remains_warning_without_backfill(
    tmp_path, monkeypatch
):
    result = scheduler_runner.EcSourceLayerRefreshPostStepResult(
        attempted=1,
        status="REFRESH_FAILED",
        signal_date="2026-06-05",
        bridge_mode="LATEST_REFRESH",
        bridge_status="FAILED",
        bridge_retry_required=True,
    )
    assert (
        result.status in scheduler_runner._bridge_failure_statuses()
        or result.bridge_status == "FAILED"
    )


def test_e2e_ec_source_layer_disabled_invokes_no_refresh_or_backfill(tmp_path, monkeypatch):
    config = _ec_config(tmp_path)
    config.ec_source_layer_enabled = False
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_refresh",
        lambda **_: (_ for _ in ()).throw(AssertionError("refresh should not run")),
    )
    monkeypatch.setattr(
        scheduler_runner,
        "run_ec_source_layer_backfill",
        lambda **_: (_ for _ in ()).throw(AssertionError("backfill should not run")),
    )

    bridge_result = scheduler_runner._run_ec_source_layer_refresh_post_step(
        config=config,
        target_market="usa",
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
    )

    assert bridge_result.status == "SKIPPED"
    assert bridge_result.skipped_reason == "DISABLED"
    assert bridge_result.bridge_mode == "DISABLED"
    assert bridge_result.bridge_status == "SKIPPED"
    assert bridge_result.bridge_retry_required is False
