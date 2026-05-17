from __future__ import annotations

import sqlite3

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_persistence import (
    persist_datacenter_group_swing_signals,
)


def _write_taxonomy_csv(tmp_path, content: str):
    path = tmp_path / "taxonomy.csv"
    path.write_text(content, encoding="utf-8")
    return path


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def _insert_ticker_snapshot(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                above_ma10, above_ema20, ema20_slope_positive, latest_structure_label,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_group_index_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_index_daily (
                index_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, ma50_eligible_count, ma200_eligible_count,
                daily_return_equal, median_return, pct_positive, pct_above_ma50, pct_above_ma200,
                index_level_equal, return_20d, return_60d, return_120d,
                volatility_20d, volatility_60d, relative_strength_spy_60d, relative_strength_qqq_60d,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _fetch_group_rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM dc_group_swing_signal_daily
            ORDER BY taxonomy_version, group_type, group_name, signal_version
            """
        ).fetchall()


def _group_row(rows, group_type: str, group_name: str, signal_date: str | None = None):
    for row in rows:
        if (
            row["group_type"] == group_type
            and row["group_name"] == group_name
            and (signal_date is None or row["signal_date"] == signal_date)
        ):
            return row
    raise AssertionError(f"Missing row for {group_type} {group_name} {signal_date}")


def test_inserts_group_rows_for_layer_and_subindustry_groups(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Cooling,Chillers,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker, layer, subindustry in [("AAA", "Power", "UPS"), ("BBB", "Cooling", "Chillers")]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, layer, subindustry, 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )

    summary = persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_group_rows(analysis_db)
    assert summary["group_rows"] == 5
    assert _group_row(rows, "layer", "Power")["member_count"] == 1
    assert _group_row(rows, "subindustry", "UPS")["member_count"] == 1


def test_uses_taxonomy_membership_and_not_snapshot_primary_subindustry_for_group_join(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,AAA,Cooling,Cooling services,CORE,0,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_ticker_snapshot(
        analysis_db,
        ("2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", 1, 1, 1, "HL", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_group_rows(analysis_db)
    cooling_row = _group_row(rows, "subindustry", "Cooling services")
    assert cooling_row["member_count"] == 1
    assert cooling_row["eligible_count"] == 1


def test_computes_breadth_metrics_correctly(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    snapshots = [
        ("AAA", 1, 1, 1, "HH", "OK"),
        ("BBB", 0, 1, 0, "LH", "OK"),
        ("CCC", None, None, None, None, "MISSING_AS_OF_DATE"),
    ]
    for ticker, above_ma10, above_ema20, ema20_slope_positive, label, status in snapshots:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", above_ma10, above_ema20, ema20_slope_positive, label, status, "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert row["eligible_count"] == 2
    assert row["pct_above_ma10"] == 50.0
    assert row["pct_above_ema20"] == 100.0
    assert row["pct_above_rising_ema20"] == 50.0


def test_computes_trend_and_weakness_breadth_from_persisted_structure_labels(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,DDD,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker, label in [("AAA", "HH"), ("BBB", "HL"), ("CCC", "LH"), ("DDD", "LL")]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, label, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert row["trend_breadth"] == 50.0
    assert row["weakness_breadth"] == 50.0


def test_computes_returns_from_dc_group_index_daily_valid_observations_not_calendar_days(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker in ["AAA", "BBB", "CCC"]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
    dates_levels = [
        ("2024-01-01", 100.0),
        ("2024-01-02", 102.0),
        ("2024-01-03", 104.0),
        ("2024-01-05", 106.0),
        ("2024-01-06", 108.0),
        ("2024-01-08", 110.0),
        ("2024-01-10", 120.0),
    ]
    for index_date, level in dates_levels:
        _insert_group_index_row(
            analysis_db,
            (index_date, "DC_TAXONOMY_V1", "layer", "Power", 3, 3, 0, 0, 0.0, 0.0, 0.0, None, None, level, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert row["return_5d"] == (120.0 / 102.0) - 1.0
    assert row["return_10d"] is None


def test_returns_are_null_when_exact_signal_date_group_index_row_is_missing(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker in ["AAA", "BBB", "CCC"]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
    for index_date, level in [("2024-01-01", 100.0), ("2024-01-08", 110.0)]:
        _insert_group_index_row(
            analysis_db,
            (index_date, "DC_TAXONOMY_V1", "layer", "Power", 3, 3, 0, 0, 0.0, 0.0, 0.0, None, None, level, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power")
    assert row["return_5d"] is None
    assert row["return_10d"] is None


def test_breadth_deltas_use_prior_persisted_rows_and_not_today_itself(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        for offset, pct in enumerate([10.0, 20.0, 30.0, 40.0, 50.0], start=1):
            conn.execute(
                """
                INSERT INTO dc_group_swing_signal_daily (
                    signal_date, taxonomy_version, group_type, group_name,
                    member_count, eligible_count, pct_above_ma10, pct_above_ema20,
                    data_quality_status, signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"2024-01-0{offset}", "DC_TAXONOMY_V1", "layer", "Power", 3, 3, pct, pct, "OK", "DC_SWING_SIGNAL_V1", "old", "2026-05-17T08:00:00Z"),
            )
        conn.commit()
    for ticker, above_ma10, above_ema20 in [("AAA", 1, 1), ("BBB", 1, 1), ("CCC", 0, 1)]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", above_ma10, above_ema20, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert row["pct_above_ma10"] == pytest.approx((2 / 3) * 100.0)
    assert row["ma10_breadth_delta_5d"] == pytest.approx(((2 / 3) * 100.0) - 10.0)
    assert row["ema20_breadth_delta_5d"] == pytest.approx(100.0 - 10.0)


def test_assigns_data_quality_statuses_deterministically(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,DDD,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,EEE,Cooling,Chillers,CORE,1,1.0,
DC_TAXONOMY_V1,FFF,Cooling,Chillers,CORE,1,1.0,
DC_TAXONOMY_V1,GGG,Cooling,Chillers,CORE,1,1.0,
DC_TAXONOMY_V1,HHH,Services,Monitoring,CORE,1,1.0,
DC_TAXONOMY_V1,III,Services,Monitoring,CORE,1,1.0,
DC_TAXONOMY_V1,JJJ,Services,Monitoring,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker in ["AAA", "BBB", "CCC"]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
    for ticker in ["EEE", "FFF"]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Cooling", "Chillers", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
    _insert_ticker_snapshot(
        analysis_db,
        ("2024-01-10", "DC_TAXONOMY_V1", "HHH", "Services", "Monitoring", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_group_rows(analysis_db)
    assert _group_row(rows, "layer", "Power")["data_quality_status"] == "OK"
    assert _group_row(rows, "layer", "Cooling")["data_quality_status"] == "TOO_SMALL"
    assert _group_row(rows, "layer", "Services")["data_quality_status"] == "TOO_SMALL"
    assert _group_row(rows, "subindustry", "Monitoring")["data_quality_status"] == "TOO_SMALL"


def test_write_modes_and_null_timing_fields(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
    )
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for ticker in ["AAA", "BBB", "CCC"]:
        _insert_ticker_snapshot(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run1",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )
    insert_missing_summary = persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run2",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="insert-missing",
    )
    upsert_summary = persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run3",
        created_at_utc="2026-05-17T13:00:00Z",
        write_mode="upsert",
    )
    replace_summary = persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        run_id="run4",
        created_at_utc="2026-05-17T14:00:00Z",
        write_mode="replace-date",
    )

    rows = _fetch_group_rows(analysis_db)
    layer_row = _group_row(rows, "layer", "Power")
    assert insert_missing_summary["skipped_existing_count"] > 0
    assert upsert_summary["updated_count"] > 0
    assert replace_summary["deleted_count"] > 0
    assert layer_row["overheat_risk_level"] is None
    assert layer_row["timing_state"] is None
    assert layer_row["timing_reason"] is None
