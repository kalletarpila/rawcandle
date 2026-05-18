from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_plan import build_datacenter_pipeline_plan
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def test_missing_watermark_returns_missing_watermark_for_components(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    assert result["rows"][0]["plan_action"] == "MISSING_WATERMARK"
    assert result["rows"][1]["plan_action"] == "MISSING_WATERMARK"


def test_fully_covered_watermark_returns_up_to_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2025-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    ticker_row = next(row for row in result["rows"] if row["component_name"] == "TICKER_SWING_BASE")
    assert ticker_row["plan_action"] == "UP_TO_DATE"


def test_group_index_with_older_end_date_returns_run_full_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-01",
        end_date="2026-05-14",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    group_index_row = result["rows"][0]
    assert group_index_row["component_name"] == "GROUP_INDEX"
    assert group_index_row["plan_action"] == "RUN_FULL_RANGE"


def test_ticker_swing_base_with_older_end_date_returns_incremental_candidate(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2026-01-01",
        end_date="2026-05-14",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    row = next(row for row in result["rows"] if row["component_name"] == "TICKER_SWING_BASE")
    assert row["plan_action"] == "RUN_INCREMENTAL_CANDIDATE"
    assert row["requested_start_date"] == "2026-05-15"


def test_synthetic_ohlc_base_with_older_end_date_returns_run_full_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="SYNTHETIC_OHLC_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        calc_version="DC_SWING_OHLC_V1",
        start_date="2026-01-01",
        end_date="2026-05-14",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    row = next(row for row in result["rows"] if row["component_name"] == "SYNTHETIC_OHLC_BASE")
    assert row["plan_action"] == "RUN_FULL_RANGE"


def test_structure_with_older_end_date_returns_run_full_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="SYNTHETIC_OHLC_STRUCTURE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        calc_version="DC_SWING_OHLC_V1",
        start_date="2026-01-01",
        end_date="2026-05-14",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    row = next(row for row in result["rows"] if row["component_name"] == "SYNTHETIC_OHLC_STRUCTURE")
    assert row["plan_action"] == "RUN_FULL_RANGE"


def test_daily_report_missing_returns_run_required(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    row = next(row for row in result["rows"] if row["component_name"] == "DAILY_REPORT")
    assert row["plan_action"] == "RUN_REQUIRED"


def test_pipeline_audit_fail_returns_run_required(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="PIPELINE_AUDIT",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        calc_version="DC_SWING_OHLC_V1",
        start_date="2026-05-15",
        end_date="2026-05-15",
        status="FAIL",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    row = next(row for row in result["rows"] if row["component_name"] == "PIPELINE_AUDIT")
    assert row["plan_action"] == "RUN_REQUIRED"


def test_components_are_returned_in_pipeline_order(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    assert [row["component_name"] for row in result["rows"]] == [
        "GROUP_INDEX",
        "TICKER_SWING_BASE",
        "GROUP_SWING_BASE",
        "SYNTHETIC_OHLC_BASE",
        "SYNTHETIC_OHLC_RELATIVE",
        "SYNTHETIC_OHLC_STRUCTURE",
        "GROUP_TIMING",
        "GROUP_OVERHEAT",
        "TICKER_SCANNER",
        "PIPELINE_AUDIT",
        "DAILY_REPORT",
        "WEEKLY_REPORT",
    ]


def test_missing_watermark_table_returns_fail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("CREATE TABLE placeholder (id INTEGER)")
        conn.commit()

    result = build_datacenter_pipeline_plan(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_date="2026-05-15",
        start_date="2026-01-01",
        index_base_date="2020-01-01",
    )

    assert result["summary"]["validation_status"] == "FAIL"
