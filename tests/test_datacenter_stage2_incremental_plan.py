from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_plan import (
    DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    build_stage2_incremental_plan,
)
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark


TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"


def _create_analysis_db(path: Path) -> None:
    DatabaseManager(str(path)).close()


def _create_price_db(path: Path) -> None:
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
        conn.commit()


def _write_taxonomy_csv(tmp_path: Path) -> Path:
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{TAXONOMY_VERSION},AAA,Power,UPS,CORE,1,1.0,",
                f"{TAXONOMY_VERSION},BBB,Cooling,Chillers,CORE,1,1.0,",
                f"{TAXONOMY_VERSION},SPY,Market,Benchmark,WATCH_ONLY,0,1.0,",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _weekdays(start: str, count: int) -> list[str]:
    cursor = date.fromisoformat(start)
    values: list[str] = []
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _insert_valid_prices(
    price_db: Path,
    dates: list[str],
    *,
    tickers: tuple[str, ...] = ("AAA", "BBB"),
    market: str = "usa",
) -> None:
    rows = []
    for ticker in tickers:
        for offset, signal_date in enumerate(dates):
            price = 100 + offset
            rows.append(
                (
                    ticker,
                    signal_date,
                    price,
                    price + 1,
                    price - 1,
                    price,
                    1000 + offset,
                    market,
                )
            )
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _count_watermarks(analysis_db: Path) -> int:
    with sqlite3.connect(analysis_db) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0])


def _base_plan_kwargs(tmp_path: Path, dates: list[str]) -> dict[str, object]:
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)
    _insert_valid_prices(price_db, dates)
    return {
        "analysis_db_path": analysis_db,
        "price_db_path": price_db,
        "taxonomy_csv_path": _write_taxonomy_csv(tmp_path),
        "taxonomy_version": TAXONOMY_VERSION,
        "market": "usa",
        "requested_start": dates[0],
        "requested_end": dates[-1],
    }


def test_stage2_missing_watermark_plans_full_requested_valid_range(tmp_path):
    dates = _weekdays("2026-07-01", 8)
    kwargs = _base_plan_kwargs(tmp_path, dates)

    plan = build_stage2_incremental_plan(**kwargs)

    assert plan.mode == "FULL"
    assert plan.materialization_start == dates[0]
    assert plan.materialization_end == dates[-1]
    assert plan.output_dates == dates
    assert plan.reason_code == "MISSING_COMPATIBLE_WATERMARK"


def test_stage2_incremental_uses_trading_day_overlap_not_calendar_gap(tmp_path):
    dates = _weekdays("2026-07-01", 10)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[6],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(**kwargs)

    assert plan.mode == "INCREMENTAL"
    assert plan.overlap_trading_days == DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS
    assert plan.reason_code == "NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP"
    assert plan.reason_details["first_new_valid_signal_date"] == dates[7]
    assert plan.materialization_start == dates[2]
    assert plan.materialization_end == dates[-1]
    assert plan.output_dates == dates[2:]


def test_stage2_incremental_zero_overlap_starts_at_first_new_valid_date(tmp_path):
    dates = _weekdays("2026-07-01", 10)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[6],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(**kwargs, overlap_trading_days=0)

    assert plan.mode == "INCREMENTAL"
    assert plan.materialization_start == dates[7]
    assert plan.output_dates == dates[7:]


def test_stage2_incremental_rejects_negative_overlap(tmp_path):
    dates = _weekdays("2026-07-01", 3)
    kwargs = _base_plan_kwargs(tmp_path, dates)

    with pytest.raises(ValueError, match="overlap_trading_days"):
        build_stage2_incremental_plan(**kwargs, overlap_trading_days=-1)


def test_stage2_current_watermark_plans_skip_without_runtime_semantics(tmp_path):
    dates = _weekdays("2026-07-01", 5)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[-1],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(**kwargs)

    assert plan.mode == "SKIP"
    assert plan.materialization_start is None
    assert plan.output_dates == []
    assert plan.downstream_stage_plans[0].reason_code == "STAGE2_SKIP_NO_DIRTY_RANGE"


def test_stage2_forced_range_is_exact_output_range_with_warmup(tmp_path):
    dates = _weekdays("2026-07-01", 12)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[7],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(
        **kwargs,
        force_range_start=dates[6],
        force_range_end=dates[8],
    )

    assert plan.mode == "INCREMENTAL"
    assert plan.reason_code == "FORCED_RANGE"
    assert plan.materialization_start == dates[6]
    assert plan.materialization_end == dates[8]
    assert plan.output_dates == dates[6:9]
    assert plan.calculation_input_start == dates[0]


def test_stage2_forced_range_must_be_inside_requested_range(tmp_path):
    dates = _weekdays("2026-07-01", 5)
    kwargs = _base_plan_kwargs(tmp_path, dates)

    with pytest.raises(ValueError, match="inside the requested range"):
        build_stage2_incremental_plan(
            **kwargs,
            force_range_start="2026-06-30",
            force_range_end=dates[1],
        )


def test_stage2_uses_current_220_valid_price_row_warmup_behavior(tmp_path):
    dates = _weekdays("2025-08-01", 250)
    kwargs = _base_plan_kwargs(tmp_path, dates)

    plan = build_stage2_incremental_plan(
        **kwargs,
        force_range_start=dates[-1],
        force_range_end=dates[-1],
    )

    assert plan.output_dates == [dates[-1]]
    assert plan.max_valid_price_rows == 220
    assert plan.calculation_input_start == dates[-220]
    assert plan.reason_details["input_resolution"]["preload_fetched_row_count"] >= 440


def test_stage2_incompatible_watermark_version_plans_full_with_evidence(tmp_path):
    dates = _weekdays("2026-07-01", 5)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version="OTHER_TAXONOMY",
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[-1],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(**kwargs)

    assert plan.mode == "FULL"
    assert plan.reason_code == "INCOMPATIBLE_OR_MISSING_COMPATIBLE_WATERMARK"
    assert plan.reason_details["existing_component_watermarks"][0]["taxonomy_version"] == "OTHER_TAXONOMY"


def test_stage2_warmup_filters_primary_tickers_to_requested_taxonomy_version(tmp_path):
    dates = _weekdays("2026-07-01", 5)
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "osakedata.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)
    _insert_valid_prices(price_db, dates, tickers=("AAA", "ZZZ"))
    taxonomy_csv.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{TAXONOMY_VERSION},AAA,Power,UPS,CORE,1,1.0,",
                "OTHER_TAXONOMY,ZZZ,Cooling,Chillers,CORE,1,1.0,",
            ]
        ),
        encoding="utf-8",
    )

    plan = build_stage2_incremental_plan(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        requested_start=dates[0],
        requested_end=dates[-1],
    )

    assert plan.reason_details["input_resolution"]["primary_ticker_count"] == 1
    assert plan.calculation_input_start == dates[0]


def test_stage2_downstream_dirty_chain_includes_stages_3_7_8_9_and_excludes_stage6(tmp_path):
    dates = _weekdays("2026-07-01", 8)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    upsert_pipeline_watermark(
        analysis_db_path=kwargs["analysis_db_path"],
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[-1],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )

    plan = build_stage2_incremental_plan(
        **kwargs,
        dirty_from_date=dates[3],
    )

    downstream_by_stage = {item.stage_number: item for item in plan.downstream_stage_plans}
    assert sorted(downstream_by_stage) == [3, 7, 8, 9]
    for downstream in downstream_by_stage.values():
        assert downstream.materialization_start == dates[3]
        assert downstream.materialization_end == dates[-1]
        assert downstream.included_in_pilot_dirty_chain is True
    assert plan.excluded_stage_plans == [
        {
            "stage_number": 6,
            "component": "SYNTHETIC_OHLC_STRUCTURE",
            "stage_name": "Group structure / BOS / RESET",
            "included_in_pilot_dirty_chain": False,
            "reason_code": "STAGE6_OUTSIDE_STAGE2_INCREMENTAL_PILOT",
        }
    ]


def test_stage2_planner_does_not_write_watermarks(tmp_path):
    dates = _weekdays("2026-07-01", 5)
    kwargs = _base_plan_kwargs(tmp_path, dates)
    before_count = _count_watermarks(kwargs["analysis_db_path"])

    build_stage2_incremental_plan(**kwargs)

    assert _count_watermarks(kwargs["analysis_db_path"]) == before_count
