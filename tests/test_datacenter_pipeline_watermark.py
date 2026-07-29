from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_watermark import (
    get_pipeline_watermark,
    list_pipeline_watermarks,
    upsert_pipeline_watermark,
)


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def test_upsert_inserts_new_watermark(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    assert row["component_name"] == "GROUP_INDEX"
    assert row["market"] == "usa"
    assert row["end_date"] == "2026-05-15"


def test_upsert_updates_existing_watermark_with_same_key(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )
    updated = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-02",
        end_date="2026-05-16",
        status="WARN",
        row_count=123,
        last_successful_at_utc="2026-05-18T11:00:00Z",
    )

    assert updated["start_date"] == "2020-01-02"
    assert updated["end_date"] == "2026-05-16"
    assert updated["status"] == "WARN"
    assert updated["row_count"] == 123


def test_optional_dimensions_normalize_to_empty_string(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    assert row["market"] == ""
    assert row["signal_version"] == ""
    assert row["calc_version"] == ""


def test_get_pipeline_watermark_returns_expected_row(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SCANNER",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2026-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    row = get_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SCANNER",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
    )

    assert row is not None
    assert row["component_name"] == "TICKER_SCANNER"


def test_list_pipeline_watermarks_filters_by_taxonomy_version(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2026-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="OTHER",
        start_date="2026-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    rows = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 1
    assert rows[0]["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"


def test_timestamps_can_be_injected_for_deterministic_tests(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="DAILY_REPORT",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        calc_version="DC_SWING_OHLC_V1",
        start_date="2026-05-15",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T12:34:56Z",
    )

    assert row["last_successful_at_utc"] == "2026-05-18T12:34:56Z"


def test_primary_key_uniqueness_is_enforced_for_watermark_table(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2026-01-01",
        end_date="2026-05-15",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2026-01-02",
        end_date="2026-05-16",
        status="WARN",
        last_successful_at_utc="2026-05-18T11:00:00Z",
    )

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0]

    assert count == 1


def test_preserve_coverage_start_merges_overlapping_ok_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2025-08-01",
        end_date="2026-07-24",
        status="OK",
        last_successful_at_utc="2026-07-27T05:00:00Z",
    )

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2026-07-20",
        end_date="2026-07-27",
        status="OK",
        last_successful_at_utc="2026-07-28T05:00:00Z",
        preserve_coverage_start=True,
    )

    assert row["start_date"] == "2025-08-01"
    assert row["end_date"] == "2026-07-27"


def test_preserve_coverage_start_does_not_merge_disjoint_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2025-08-01",
        end_date="2025-08-15",
        status="OK",
        last_successful_at_utc="2026-07-27T05:00:00Z",
    )

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2026-07-20",
        end_date="2026-07-27",
        status="OK",
        last_successful_at_utc="2026-07-28T05:00:00Z",
        preserve_coverage_start=True,
    )

    assert row["start_date"] == "2026-07-20"
    assert row["end_date"] == "2026-07-27"


def test_preserve_coverage_start_does_not_merge_incompatible_identity(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="OLD_TAXONOMY",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2025-08-01",
        end_date="2026-07-24",
        status="OK",
        last_successful_at_utc="2026-07-27T05:00:00Z",
    )

    row = upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        start_date="2026-07-20",
        end_date="2026-07-27",
        status="OK",
        last_successful_at_utc="2026-07-28T05:00:00Z",
        preserve_coverage_start=True,
    )

    old_row = get_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version="OLD_TAXONOMY",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
    )

    assert old_row is not None
    assert old_row["start_date"] == "2025-08-01"
    assert row["start_date"] == "2026-07-20"
    assert row["end_date"] == "2026-07-27"
