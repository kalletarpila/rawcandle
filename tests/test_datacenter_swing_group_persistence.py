from __future__ import annotations

import sqlite3

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_persistence import (
    persist_datacenter_group_overheat_risk,
    persist_datacenter_group_swing_signal_range,
    persist_datacenter_group_timing_states,
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


def _insert_group_swing_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                trend_breadth, weakness_breadth, overheat_risk_level,
                timing_state, timing_reason, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


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


def test_range_base_processes_only_group_index_dates_in_ascending_order(tmp_path):
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
    for signal_date in ("2024-01-02", "2024-01-05"):
        for ticker in ["AAA", "BBB", "CCC"]:
            _insert_ticker_snapshot(
                analysis_db,
                (signal_date, "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
            )
    for index_date in ("2024-01-02", "2024-01-05"):
        _insert_group_index_row(
            analysis_db,
            (index_date, "DC_TAXONOMY_V1", "layer", "Power", 3, 3, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )
        _insert_group_index_row(
            analysis_db,
            (index_date, "DC_TAXONOMY_V1", "subindustry", "UPS", 3, 3, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )
        _insert_group_index_row(
            analysis_db,
            (index_date, "DC_TAXONOMY_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL", 3, 3, 0, 0, 0.0, 0.0, 0.0, None, None, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )

    summary = persist_datacenter_group_swing_signal_range(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-01",
        end_date="2024-01-05",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="range-run",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="replace-date",
    )

    rows = _fetch_group_rows(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        processed_dates = [
            row[0]
            for row in conn.execute(
                """
                SELECT DISTINCT signal_date
                FROM dc_group_swing_signal_daily
                ORDER BY signal_date ASC
                """
            ).fetchall()
        ]
    assert summary["requested_start_date"] == "2024-01-01"
    assert summary["requested_end_date"] == "2024-01-05"
    assert summary["valid_signal_dates"] == 2
    assert summary["skipped_non_signal_dates"] == 3
    assert summary["group_rows"] == 6
    assert processed_dates == ["2024-01-02", "2024-01-05"]
    assert {str(row["signal_date"]) for row in rows} == {"2024-01-02", "2024-01-05"}


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


def test_timing_updates_existing_group_rows_and_preserves_metric_fields(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "layer", "Power",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            82.0, 85.0, 70.0,
            5.0, 2.0,
            60.0, 20.0, "KEEP_RISK",
            None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    summary = persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert summary["updated_count"] == 1
    assert row["timing_state"] == "BUY_ZONE"
    assert row["timing_reason"] == "BUY_ZONE:return_5d_pos;return_10d_pos;pct_above_ema20_ge_80;ema20_breadth_delta_5d_ge_minus_10;data_quality_ok"
    assert row["return_20d"] == pytest.approx(0.10)
    assert row["pct_above_ema20"] == pytest.approx(85.0)
    assert row["trend_breadth"] == pytest.approx(60.0)
    assert row["weakness_breadth"] == pytest.approx(20.0)
    assert row["data_quality_status"] == "OK"
    assert row["overheat_risk_level"] == "KEEP_RISK"


def test_timing_does_not_insert_missing_base_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    summary = persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    assert summary["updated_count"] == 0
    assert _fetch_group_rows(analysis_db) == []


def test_timing_classifies_buy_zone_add_on_pullback_trim_watch_exit_zone_and_neutral(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Buy", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, None, 0.0, None, 20.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Add", 5, 5, -0.03, 0.01, 0.10, 0.20, 70.0, 70.0, None, None, 0.0, None, 20.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Trim", 5, 5, 0.01, 0.01, 0.01, 0.02, 40.0, 70.0, None, None, -11.0, None, 20.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Exit", 5, 5, 0.01, 0.01, -0.01, 0.02, 70.0, 39.0, None, None, -16.0, None, 61.0, None, None, None, "PARTIAL_DATA", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Neutral", 5, 5, None, None, None, None, None, None, None, None, None, None, None, None, None, None, "TOO_SMALL", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)

    summary = persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    fetched = _fetch_group_rows(analysis_db)
    assert _group_row(fetched, "layer", "Buy", "2024-01-10")["timing_state"] == "BUY_ZONE"
    assert _group_row(fetched, "layer", "Add", "2024-01-10")["timing_state"] == "ADD_ON_PULLBACK"
    assert _group_row(fetched, "layer", "Trim", "2024-01-10")["timing_state"] == "TRIM_WATCH"
    assert _group_row(fetched, "layer", "Exit", "2024-01-10")["timing_state"] == "EXIT_ZONE"
    assert _group_row(fetched, "layer", "Neutral", "2024-01-10")["timing_state"] == "NEUTRAL"
    assert summary["buy_zone_count"] == 1
    assert summary["add_on_pullback_count"] == 1
    assert summary["trim_watch_count"] == 1
    assert summary["exit_zone_count"] == 1
    assert summary["neutral_count"] == 1


def test_timing_priority_order_and_null_handling(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "ExitWins", 5, 5, -0.01, -0.01, -0.01, 0.10, 30.0, 35.0, None, None, -16.0, None, 70.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "TrimWins", 5, 5, -0.03, 0.01, 0.10, 0.20, 45.0, 70.0, None, None, -11.0, None, 20.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "AddWins", 5, 5, -0.02, 0.02, 0.10, 0.20, 90.0, 90.0, None, None, 0.0, None, 20.0, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "NullSafe", 5, 5, None, None, None, None, None, None, None, None, None, None, None, None, None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)

    persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    fetched = _fetch_group_rows(analysis_db)
    assert _group_row(fetched, "layer", "ExitWins", "2024-01-10")["timing_state"] == "EXIT_ZONE"
    assert _group_row(fetched, "layer", "TrimWins", "2024-01-10")["timing_state"] == "TRIM_WATCH"
    assert _group_row(fetched, "layer", "AddWins", "2024-01-10")["timing_state"] == "ADD_ON_PULLBACK"
    assert _group_row(fetched, "layer", "NullSafe", "2024-01-10")["timing_state"] == "NEUTRAL"


def test_positive_states_require_ok_and_risk_states_can_trigger_when_not_ok(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "PositiveBlocked", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, None, 0.0, None, 20.0, None, None, None, "PARTIAL_DATA", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "RiskAllowed", 5, 5, None, None, -0.01, None, None, 39.0, None, None, None, None, 61.0, None, None, None, "NO_DATA", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)

    persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    fetched = _fetch_group_rows(analysis_db)
    assert _group_row(fetched, "layer", "PositiveBlocked", "2024-01-10")["timing_state"] == "NEUTRAL"
    assert _group_row(fetched, "layer", "RiskAllowed", "2024-01-10")["timing_state"] == "EXIT_ZONE"


def test_timing_reason_is_deterministic_and_write_modes_are_scoped(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Power", 5, 5, None, None, -0.01, 0.02, 45.0, 39.0, None, None, -16.0, 30.0, 61.0, "KEEP_RISK", "OLD", "OLD", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-11", "DC_TAXONOMY_V1", "layer", "Power", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, None, 0.0, 30.0, 20.0, "KEEP_RISK", "OLD", "OLD", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Power", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, None, 0.0, 30.0, 20.0, "KEEP_RISK", "KEEP", "KEEP", "OK", "OTHER_VERSION", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)

    summary = persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-11",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="timing-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-timing-range",
        group_types=("layer",),
    )

    fetched = _fetch_group_rows(analysis_db)
    day1 = _group_row(fetched, "layer", "Power", "2024-01-10")
    day2 = _group_row(fetched, "layer", "Power", "2024-01-11")
    other_version = [row for row in fetched if row["signal_version"] == "OTHER_VERSION"][0]
    assert summary["cleared_count"] == 2
    assert summary["updated_count"] == 2
    assert day1["timing_reason"] == "EXIT_ZONE:ema20_breadth_delta_5d_lt_minus_15;return_20d_neg;pct_above_ema20_lt_40;weakness_breadth_gt_60"
    assert day2["timing_state"] == "BUY_ZONE"
    assert day1["overheat_risk_level"] == "KEEP_RISK"
    assert other_version["timing_state"] == "KEEP"


def test_overheat_updates_existing_rows_and_preserves_metric_and_timing_fields(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "layer", "Power",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            82.0, 85.0, 70.0,
            -4.0, -4.0,
            60.0, 20.0, None,
            "BUY_ZONE", "BUY_ZONE:existing", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_index_row(
        analysis_db,
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Power", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 65.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
    )

    summary = persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="overheat-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    row = _group_row(_fetch_group_rows(analysis_db), "layer", "Power", "2024-01-10")
    assert summary["updated_count"] == 1
    assert row["overheat_risk_level"] == "LOW"
    assert row["return_20d"] == pytest.approx(0.10)
    assert row["pct_above_ema20"] == pytest.approx(85.0)
    assert row["weakness_breadth"] == pytest.approx(20.0)
    assert row["data_quality_status"] == "OK"
    assert row["timing_state"] == "BUY_ZONE"
    assert row["timing_reason"] == "BUY_ZONE:existing"


def test_overheat_does_not_insert_missing_base_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    summary = persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="overheat-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    assert summary["updated_count"] == 0
    assert _fetch_group_rows(analysis_db) == []


def test_overheat_classifies_low_elevated_high_and_extreme(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "LowPct", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -8.0, -6.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "LowBreadth", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -4.0, -4.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Elevated", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -6.0, -6.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "High", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -11.0, -11.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-09", "DC_TAXONOMY_V1", "layer", "Extreme", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -11.0, -11.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Extreme", 5, 5, -0.01, -0.02, -0.01, 0.20, 82.0, 69.0, None, -11.0, -11.0, None, 55.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)
    index_rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "LowPct", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 65.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "LowBreadth", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 75.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Elevated", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 80.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "High", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 85.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        ("2024-01-09", "DC_TAXONOMY_V1", "layer", "Extreme", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 90.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Extreme", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 90.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
    ]
    for row in index_rows:
        _insert_group_index_row(analysis_db, row)

    summary = persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date="2024-01-09",
        end_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="overheat-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    fetched = _fetch_group_rows(analysis_db)
    assert _group_row(fetched, "layer", "LowPct", "2024-01-10")["overheat_risk_level"] == "LOW"
    assert _group_row(fetched, "layer", "LowBreadth", "2024-01-10")["overheat_risk_level"] == "LOW"
    assert _group_row(fetched, "layer", "Elevated", "2024-01-10")["overheat_risk_level"] == "ELEVATED"
    assert _group_row(fetched, "layer", "High", "2024-01-10")["overheat_risk_level"] == "HIGH"
    assert _group_row(fetched, "layer", "Extreme", "2024-01-10")["overheat_risk_level"] == "EXTREME"
    assert summary["low_count"] == 2
    assert summary["elevated_count"] == 1
    assert summary["high_count"] == 2
    assert summary["extreme_count"] == 1


def test_overheat_extreme_requires_two_consecutive_valid_days_and_confirming_weakness(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-08", "DC_TAXONOMY_V1", "layer", "NoPrev", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -1.0, None, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "NoPrev", 5, 5, -0.01, 0.03, 0.10, 0.20, 82.0, 69.0, None, -11.0, -11.0, None, 55.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-09", "DC_TAXONOMY_V1", "layer", "NoWeakness", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -11.0, -11.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "NoWeakness", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 75.0, None, -11.0, -11.0, None, 20.0, None, "BUY_ZONE", "x", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)
    for name in ["NoPrev", "NoWeakness"]:
        _insert_group_index_row(
            analysis_db,
            ("2024-01-09", "DC_TAXONOMY_V1", "layer", name, 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 90.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )
        _insert_group_index_row(
            analysis_db,
            ("2024-01-10", "DC_TAXONOMY_V1", "layer", name, 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 90.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
        )

    persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date="2024-01-08",
        end_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="overheat-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    fetched = _fetch_group_rows(analysis_db)
    assert _group_row(fetched, "layer", "NoPrev", "2024-01-10")["overheat_risk_level"] == "HIGH"
    assert _group_row(fetched, "layer", "NoWeakness", "2024-01-10")["overheat_risk_level"] == "HIGH"


def test_overheat_null_handling_and_scoped_write_modes(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        ("2024-01-10", "DC_TAXONOMY_V1", "layer", "Nulls", 5, 5, None, None, None, None, None, None, None, None, None, None, None, "KEEP", "BUY_ZONE", "keep", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-11", "DC_TAXONOMY_V1", "layer", "Scoped", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -11.0, -11.0, None, 20.0, "OLD", "BUY_ZONE", "keep", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        ("2024-01-11", "DC_TAXONOMY_V1", "layer", "Scoped", 5, 5, 0.02, 0.03, 0.10, 0.20, 82.0, 85.0, None, -11.0, -11.0, None, 20.0, "KEEP_OTHER", "BUY_ZONE", "keep", "OK", "OTHER_VERSION", "seed", "2026-05-17T10:00:00Z"),
    ]
    for row in rows:
        _insert_group_swing_row(analysis_db, row)
    _insert_group_index_row(
        analysis_db,
        ("2024-01-11", "DC_TAXONOMY_V1", "layer", "Scoped", 5, 5, 0, 0, 0.0, 0.0, 0.0, None, 85.0, 100.0, None, None, None, None, None, None, None, "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z"),
    )

    summary = persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-11",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="overheat-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-overheat-range",
        group_types=("layer",),
    )

    fetched = _fetch_group_rows(analysis_db)
    null_row = _group_row(fetched, "layer", "Nulls", "2024-01-10")
    scoped_row = _group_row(fetched, "layer", "Scoped", "2024-01-11")
    other_version = [row for row in fetched if row["signal_version"] == "OTHER_VERSION"][0]
    assert summary["cleared_count"] == 2
    assert summary["updated_count"] == 2
    assert null_row["overheat_risk_level"] is None
    assert scoped_row["overheat_risk_level"] == "HIGH"
    assert scoped_row["timing_state"] == "BUY_ZONE"
    assert other_version["overheat_risk_level"] == "KEEP_OTHER"
