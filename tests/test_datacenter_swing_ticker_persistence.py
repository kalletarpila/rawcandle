from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_ticker_persistence import (
    classify_ticker_structure_freshness,
    classify_exit_risk_severity,
    cleanup_non_trading_ticker_swing_rows,
    load_existing_ticker_signal_dates,
    load_bounded_ticker_ohlcv_history,
    load_bounded_ticker_ohlcv_histories,
    load_valid_price_dates_for_market,
    persist_datacenter_ticker_scanner_signals,
    persist_datacenter_ticker_swing_snapshots,
)
from market_repository import ensure_market_schema


def _write_taxonomy_csv(tmp_path, content: str):
    path = tmp_path / "taxonomy.csv"
    path.write_text(content, encoding="utf-8")
    return path


def _create_price_db(path):
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


def _insert_price_rows(path, rows):
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_dow_structure_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NULL,
                event_date TEXT NOT NULL,
                confirmed_as_of_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                dow_label_high TEXT NULL,
                dow_label_low TEXT NULL,
                trend_state TEXT NULL
            )
            """
        )
        conn.commit()


def _insert_dow_event(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, event_type,
                dow_label_high, dow_label_low, trend_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_divergence_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength,
                hidden_bullish_strength, hidden_bearish_strength, rsi,
                is_bullish_divergence_r3, is_bearish_divergence_r3,
                is_hidden_bullish_divergence_r3, is_hidden_bearish_divergence_r3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_finding(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _fetch_ticker_rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM dc_ticker_swing_signal_daily
            ORDER BY taxonomy_version, ticker, signal_version
            """
        ).fetchall()


def _insert_ticker_swing_row(path, row):
    values = list(row)
    if len(values) == 45:
        values[29:29] = [None, None]
        values.insert(43, None)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, volume, return_5d, return_10d, return_20d, return_60d,
                ma10, ema10, ema20, distance_to_ma10_pct, distance_to_ema10_pct,
                distance_to_ema20_pct, above_ma10, above_ema10, above_ema20,
                ema10_slope_positive, ema20_slope_positive, ema10_slope_lookback,
                ema20_slope_lookback, highest_close_20d, volume_avg_20d, volume_vs_avg20,
                latest_structure_label, latest_structure_confirmed_as_of_date,
                latest_structure_age_trading_days, latest_structure_freshness,
                bullish_divergence_signal, bearish_divergence_signal,
                hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                bullish_candle_signal, bearish_candle_signal, breakout_signal,
                fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values),
        )
        conn.commit()


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


def _insert_group_synthetic_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, synthetic_open, synthetic_high, synthetic_low,
                synthetic_close, synthetic_volume, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def test_persistence_inserts_one_primary_taxonomy_ticker_row(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_ticker_rows(analysis_db)
    assert summary["inserted_count"] == 1
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["latest_structure_age_trading_days"] is None
    assert rows[0]["latest_structure_freshness"] is None


def test_persistence_profile_does_not_change_inserted_or_deleted_counts(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db_plain = tmp_path / "analysis_plain.db"
    analysis_db_profiled = tmp_path / "analysis_profiled.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db_plain)
    _create_analysis_db(analysis_db_profiled)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    plain_summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db_plain,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run_plain",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="replace-date",
        profile=False,
    )
    profiled_summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db_profiled,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run_profiled",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="replace-date",
        profile=True,
    )

    assert plain_summary["inserted_count"] == profiled_summary["inserted_count"] == 1
    assert plain_summary["deleted_count"] == profiled_summary["deleted_count"] == 0
    assert profiled_summary["ticker_swing_snapshot_profile.rows_built"] == 1
    assert profiled_summary["ticker_swing_snapshot_profile.rows_inserted"] == 1
    assert profiled_summary["ticker_swing_snapshot_profile.rows_deleted"] == 0


def test_load_valid_price_dates_for_market_uses_primary_taxonomy_tickers_and_skips_weekend_dates(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    _create_price_db(price_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-15", 101, 102, 100, 101, 1001, "usa"),
            ("SPY", "2024-01-13", 400, 401, 399, 400, 5000, "usa"),
        ],
    )

    valid_dates = load_valid_price_dates_for_market(
        price_db_path=price_db,
        start_date="2024-01-12",
        end_date="2024-01-15",
        market="usa",
        taxonomy_csv_path=taxonomy_csv,
    )

    assert valid_dates == ["2024-01-12", "2024-01-15"]


def test_load_valid_price_dates_for_market_can_scope_to_selected_taxonomy_version(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
OTHER_TAXONOMY,BBB,Cooling,Chillers,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    _create_price_db(price_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
            ("BBB", "2024-01-15", 101, 102, 100, 101, 1000, "usa"),
        ],
    )

    valid_dates = load_valid_price_dates_for_market(
        price_db_path=price_db,
        start_date="2024-01-12",
        end_date="2024-01-15",
        market="usa",
        taxonomy_csv_path=taxonomy_csv,
        taxonomy_version="DC_TAXONOMY_V1",
    )

    assert valid_dates == ["2024-01-12"]


def test_load_existing_ticker_signal_dates_returns_only_existing_base_dates_in_ascending_order(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.commit()

    dates = load_existing_ticker_signal_dates(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-12",
        signal_version="DC_SWING_SIGNAL_V1",
    )

    assert dates == ["2024-01-10", "2024-01-12"]


def test_load_existing_ticker_signal_dates_can_scope_to_taxonomy_version(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-11", "OTHER_TAXONOMY", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.commit()

    dates = load_existing_ticker_signal_dates(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-12",
        signal_version="DC_SWING_SIGNAL_V1",
        taxonomy_version="DC_TAXONOMY_V1",
    )

    assert dates == ["2024-01-10"]


def test_cleanup_non_trading_ticker_rows_dry_run_identifies_candidates_without_deleting(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa")],
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-13", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.commit()

    summary = cleanup_non_trading_ticker_swing_rows(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-12",
        end_date="2024-01-13",
        taxonomy_version="DC_TAXONOMY_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        market="usa",
        apply=False,
    )

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
    assert summary["existing_signal_dates"] == 2
    assert summary["valid_trading_dates"] == 1
    assert summary["non_trading_signal_dates"] == 1
    assert summary["candidate_rows"] == 1
    assert summary["deleted_rows"] == 0
    assert summary["dry_run"] == 1
    assert summary["non_trading_dates"] == "2024-01-13"
    assert count == 2


def test_cleanup_non_trading_ticker_rows_apply_deletes_only_scoped_rows(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
OTHER_TAXONOMY,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-15", 101, 102, 100, 101, 1000, "usa"),
            ("SPY", "2024-01-13", 400, 401, 399, 400, 5000, "usa"),
        ],
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-13", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-15", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-13", "OTHER_TAXONOMY", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-13", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "OTHER_SIGNAL", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-20", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
            ],
        )
        conn.commit()
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-13", "DC_TAXONOMY_V1", "subindustry", "UPS",
            1, 1, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_synthetic_row(
        analysis_db,
        (
            "2024-01-13", "DC_TAXONOMY_V1", "subindustry", "UPS",
            1, 1, 1.0, 1.0, 1.0, 1.0, 100.0, "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    summary = cleanup_non_trading_ticker_swing_rows(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-12",
        end_date="2024-01-15",
        taxonomy_version="DC_TAXONOMY_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        market="usa",
        apply=True,
    )

    with sqlite3.connect(analysis_db) as conn:
        ticker_rows = conn.execute(
            """
            SELECT signal_date, taxonomy_version, signal_version
            FROM dc_ticker_swing_signal_daily
            ORDER BY signal_date, taxonomy_version, signal_version
            """
        ).fetchall()
        group_count = conn.execute("SELECT COUNT(*) FROM dc_group_swing_signal_daily").fetchone()[0]
        synthetic_count = conn.execute("SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily").fetchone()[0]
    assert summary["candidate_rows"] == 1
    assert summary["deleted_rows"] == 1
    assert summary["dry_run"] == 0
    assert ticker_rows == [
        ("2024-01-12", "DC_TAXONOMY_V1", "DC_SWING_SIGNAL_V1"),
        ("2024-01-13", "DC_TAXONOMY_V1", "OTHER_SIGNAL"),
        ("2024-01-13", "OTHER_TAXONOMY", "DC_SWING_SIGNAL_V1"),
        ("2024-01-15", "DC_TAXONOMY_V1", "DC_SWING_SIGNAL_V1"),
        ("2024-01-20", "DC_TAXONOMY_V1", "DC_SWING_SIGNAL_V1"),
    ]
    assert group_count == 1
    assert synthetic_count == 1


def test_cleanup_non_trading_ticker_rows_returns_ok_when_no_candidates_exist(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa")],
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
        )
        conn.commit()

    summary = cleanup_non_trading_ticker_swing_rows(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date="2024-01-12",
        end_date="2024-01-12",
        taxonomy_version="DC_TAXONOMY_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        market="usa",
        apply=False,
    )

    assert summary["candidate_rows"] == 0
    assert summary["deleted_rows"] == 0
    assert summary["non_trading_signal_dates"] == 0
    assert summary["validation_status"] == "OK"


def test_persistence_ignores_non_primary_taxonomy_rows(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,0,1.0,
DC_TAXONOMY_V1,BBB,Cooling,Chillers,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("BBB", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    rows = _fetch_ticker_rows(analysis_db)
    assert [row["ticker"] for row in rows] == ["BBB"]


def test_missing_exact_as_of_date_still_writes_row_with_missing_status_and_null_price_metrics(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-09", 100, 101, 99, 100, 1000, "usa")],
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert row["price_data_status"] == "MISSING_AS_OF_DATE"
    assert row["close"] is None
    assert row["ma10"] is None


def test_persistence_stores_price_metrics_and_analysis_enrichment_fields(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    start = date(2024, 1, 1)
    _insert_price_rows(
        price_db,
        [
            ("AAA", (start + timedelta(days=offset)).isoformat(), 100 + offset, 100 + offset, 100 + offset, 100 + offset, 1000 + offset, "usa")
            for offset in range(20)
        ],
    )
    _insert_dow_event(
        analysis_db,
        ("AAA", "usa", "2024-01-20", "2024-01-20", "PIVOT_HIGH", "HH", None, "UP"),
    )
    _insert_divergence_row(
        analysis_db,
        ("AAA", "2024-01-20", 1.5, 0.0, 0.0, 0.0, 61.0, 1, 0, 0, 0),
    )
    _insert_finding(
        analysis_db,
        ("AAA", "2024-01-20", "Hammer", 0.9, 30.0),
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-20",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert row["close"] == 119.0
    assert row["ma10"] is not None
    assert row["ema20"] == pytest.approx(109.5)
    assert row["latest_structure_label"] == "HH"
    assert row["latest_structure_confirmed_as_of_date"] == "2024-01-20"
    assert row["ticker_trend_state"] == "UP"
    assert row["latest_bos_event_type"] is None
    assert row["latest_reset_event_date"] is None
    assert row["bullish_divergence_signal"] == 1
    assert row["bearish_divergence_signal"] == 0


def test_persistence_stores_latest_bos_and_reset_context(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-11", 101, 102, 100, 101, 1000, "usa"),
            ("AAA", "2024-01-12", 102, 103, 101, 102, 1000, "usa"),
            ("AAA", "2024-01-15", 103, 104, 102, 103, 1000, "usa"),
            ("AAA", "2024-01-16", 104, 105, 103, 104, 1000, "usa"),
        ],
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("ALTER TABLE stock_dow_structure_events ADD COLUMN reset_reason TEXT")
        conn.execute("ALTER TABLE stock_dow_structure_events ADD COLUMN structure_epoch_id INTEGER")
        conn.execute(
            """
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, event_type,
                dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "usa", "2024-01-10", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP", None, 1),
        )
        conn.execute(
            """
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, event_type,
                dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "usa", "2024-01-11", "2024-01-12", "BOS_DOWN", None, None, "UP", None, 1),
        )
        conn.execute(
            """
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, event_type,
                dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "usa", "2024-01-12", "2024-01-15", "RESET", None, None, "NEUTRAL", "DOUBLE_BOS_DOWN", 2),
        )
        conn.commit()

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-16",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert row["ticker_trend_state"] == "NEUTRAL"
    assert row["structure_epoch_id"] == 2
    assert row["latest_bos_event_type"] == "BOS_DOWN"
    assert row["latest_bos_event_date"] == "2024-01-11"
    assert row["latest_bos_confirmed_as_of_date"] == "2024-01-12"
    assert row["latest_bos_age_trading_days"] == 2
    assert row["latest_bos_freshness"] == "FRESH"
    assert row["latest_reset_event_date"] == "2024-01-12"
    assert row["latest_reset_confirmed_as_of_date"] == "2024-01-15"
    assert row["latest_reset_reason"] == "DOUBLE_BOS_DOWN"
    assert row["latest_reset_age_trading_days"] == 1
    assert row["latest_reset_freshness"] == "FRESH"


def test_batched_price_history_loader_matches_single_ticker_loader(tmp_path):
    price_db = tmp_path / "osakedata.db"
    _create_price_db(price_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-08", 10, 11, 9, 10, 100, "usa"),
            ("AAA", "2024-01-09", 11, 12, 10, 11, 101, "usa"),
            ("AAA", "2024-01-10", 12, 13, 11, 12, 102, "usa"),
            ("BBB", "2024-01-09", 20, 21, 19, 20, 200, "usa"),
            ("BBB", "2024-01-10", 21, 22, 20, 21, 201, "usa"),
        ],
    )

    batch_histories, fetched_count = load_bounded_ticker_ohlcv_histories(
        price_db_path=price_db,
        tickers=["AAA", "BBB"],
        market="usa",
        as_of_date="2024-01-10",
        max_valid_price_rows=2,
    )

    assert [row.date for row in batch_histories["AAA"]] == [
        row.date
        for row in load_bounded_ticker_ohlcv_history(
            price_db_path=price_db,
            ticker="AAA",
            market="usa",
            as_of_date="2024-01-10",
            max_valid_price_rows=2,
        )
    ]
    assert [row.date for row in batch_histories["BBB"]] == [
        row.date
        for row in load_bounded_ticker_ohlcv_history(
            price_db_path=price_db,
            ticker="BBB",
            market="usa",
            as_of_date="2024-01-10",
            max_valid_price_rows=2,
        )
    ]
    assert fetched_count >= 4


def test_schema_initializers_create_reader_and_price_indexes(tmp_path):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    ensure_market_schema(str(price_db))
    DatabaseManager(str(analysis_db)).close()

    with sqlite3.connect(price_db) as conn:
        price_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list('osakedata')").fetchall()
        }
    with sqlite3.connect(analysis_db) as conn:
        divergence_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list('divergence_data')").fetchall()
        }
        findings_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list('analysis_findings')").fetchall()
        }

    assert "idx_osakedata_market_ticker_date" in price_indexes
    assert "idx_div_ticker_date" in divergence_indexes
    assert "idx_analysis_findings_ticker_date" in findings_indexes


def test_scanner_fields_remain_null_in_this_step(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert row["breakout_signal"] is None
    assert row["fast_ema10_pullback_signal"] is None
    assert row["conservative_ema20_pullback_signal"] is None
    assert row["pullback_signal"] is None
    assert row["exit_risk_signal"] is None
    assert row["exit_reason"] is None
    assert row["exit_risk_severity"] is None


def test_classify_ticker_structure_freshness_thresholds():
    assert classify_ticker_structure_freshness(None) is None
    assert classify_ticker_structure_freshness(0) == "FRESH"
    assert classify_ticker_structure_freshness(20) == "FRESH"
    assert classify_ticker_structure_freshness(21) == "AGING"
    assert classify_ticker_structure_freshness(40) == "AGING"
    assert classify_ticker_structure_freshness(41) == "STALE"


def test_structure_age_uses_valid_ticker_price_observations(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [
            ("AAA", "2024-01-02", 100, 101, 99, 100, 1000, "usa"),
            ("AAA", "2024-01-03", 101, 102, 100, 101, 1000, "usa"),
            ("AAA", "2024-01-05", 102, 103, 101, 102, 1000, "usa"),
            ("AAA", "2024-01-08", 103, 104, 102, 103, 1000, "usa"),
        ],
    )
    _insert_dow_event(
        analysis_db,
        ("AAA", "usa", "2024-01-02", "2024-01-03", "PIVOT_HIGH", "HH", None, "UP"),
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-08",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert row["latest_structure_label"] == "HH"
    assert row["latest_structure_confirmed_as_of_date"] == "2024-01-03"
    assert row["latest_structure_age_trading_days"] == 2
    assert row["latest_structure_freshness"] == "FRESH"


def test_classify_exit_risk_severity_is_deterministic():
    assert classify_exit_risk_severity(None) is None
    assert classify_exit_risk_severity("") is None
    assert classify_exit_risk_severity("subindustry_exit_zone") == "MEDIUM"
    assert classify_exit_risk_severity("close_below_ema20") == "MEDIUM"
    assert classify_exit_risk_severity("trim_watch_close_below_ma10") == "MEDIUM"
    assert classify_exit_risk_severity("latest_structure_label_ll") == "HIGH"
    assert classify_exit_risk_severity("return_10d_lt_minus_8pct") == "HIGH"
    assert classify_exit_risk_severity("close_below_ema20;subindustry_exit_zone") == "HIGH"
    assert classify_exit_risk_severity("subindustry_exit_zone;custom_reason") == "MEDIUM"
    assert classify_exit_risk_severity("custom_reason") == "LOW"


def test_insert_missing_skips_existing_primary_key_rows(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )
    summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run2",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="insert-missing",
    )

    rows = _fetch_ticker_rows(analysis_db)
    assert summary["inserted_count"] == 0
    assert summary["skipped_existing_count"] == 1
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run1"


def test_upsert_updates_existing_primary_key_row(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run1",
        created_at_utc="2026-05-17T10:00:00Z",
        write_mode="upsert",
    )
    summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run2",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert summary["updated_count"] == 1
    assert row["run_id"] == "run2"
    assert row["created_at_utc"] == "2026-05-17T11:00:00Z"


def test_replace_date_deletes_only_matching_date_taxonomy_version_and_signal_version(tmp_path):
    taxonomy_csv = _write_taxonomy_csv(
        tmp_path,
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
    )
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _insert_price_rows(
        price_db,
        [("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa")],
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-10", "DC_TAXONOMY_V1", "AAA", "Old", "Old", "OK", "DC_SWING_SIGNAL_V1", "old", "2026-05-17T09:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-10", "DC_TAXONOMY_V1", "AAA", "Keep", "Keep", "OK", "OTHER_SIGNAL", "old", "2026-05-17T09:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2024-01-09", "DC_TAXONOMY_V1", "AAA", "KeepDate", "KeepDate", "OK", "DC_SWING_SIGNAL_V1", "old", "2026-05-17T09:00:00Z"),
        )
        conn.commit()

    summary = persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        run_id="run2",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="replace-date",
    )

    rows = _fetch_ticker_rows(analysis_db)
    assert summary["deleted_count"] == 1
    assert len(rows) == 3
    kept_versions = sorted((row["signal_date"], row["signal_version"], row["primary_layer"]) for row in rows)
    assert ("2024-01-09", "DC_SWING_SIGNAL_V1", "KeepDate") in kept_versions
    assert ("2024-01-10", "OTHER_SIGNAL", "Keep") in kept_versions
    assert ("2024-01-10", "DC_SWING_SIGNAL_V1", "Power") in kept_versions


def test_bounded_price_history_loader_limits_valid_rows(tmp_path):
    price_db = tmp_path / "osakedata.db"
    _create_price_db(price_db)
    start = date(2023, 1, 1)
    _insert_price_rows(
        price_db,
        [
            ("AAA", (start + timedelta(days=offset)).isoformat(), 100 + offset, 101 + offset, 99 + offset, 100 + offset, 1000, "usa")
            for offset in range(300)
        ],
    )

    rows = load_bounded_ticker_ohlcv_history(
        price_db_path=price_db,
        ticker="AAA",
        market="usa",
        as_of_date=(start + timedelta(days=299)).isoformat(),
        max_valid_price_rows=220,
    )

    assert len(rows) == 220
    assert rows[0].date == (start + timedelta(days=80)).isoformat()
    assert rows[-1].date == (start + timedelta(days=299)).isoformat()


def test_scanner_updates_existing_rows_and_preserves_metric_and_enrichment_fields(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_ticker_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, 0.01, 0.01, 0.04,
            1, 1, 1, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", "2024-01-10", 0, "FRESH", 0, 0, 0, 0, 0, 0,
            None, None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "BUY_ZONE:existing", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    row = _fetch_ticker_rows(analysis_db)[0]
    assert summary["updated_count"] == 1
    assert row["breakout_signal"] == 1
    assert row["close"] == pytest.approx(120.0)
    assert row["ema20"] == pytest.approx(115.0)
    assert row["latest_structure_label"] == "HH"
    assert row["latest_structure_age_trading_days"] == 0
    assert row["latest_structure_freshness"] == "FRESH"
    assert row["price_data_status"] == "OK"


def test_scanner_range_without_taxonomy_version_preserves_all_taxonomy_behavior(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for taxonomy_version in ("DC_TAXONOMY_V1", "OTHER_TAXONOMY"):
        _insert_ticker_swing_row(
            analysis_db,
            (
                "2024-01-10", taxonomy_version, "AAA", "Power", "UPS",
                120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
                118.0, 119.0, 115.0, 0.01, 0.01, 0.04,
                1, 1, 1, 1, 1, 3, 5, 120.0, 900.0, 1.6,
                "HH", "2024-01-10", 0, "FRESH", 0, 0, 0, 0, 0, 0,
                9, 9, 9, 9, 9, "old", "HIGH", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        _insert_group_swing_row(
            analysis_db,
            (
                "2024-01-10", taxonomy_version, "subindustry", "UPS",
                5, 5, 0.02, 0.03, 0.10, 0.20,
                80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                "BUY_ZONE", "x", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )

    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        taxonomy_version=None,
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-scanner-range",
    )

    assert summary["taxonomy_version"] == "ALL"
    assert summary["updated_count"] == 2
    assert summary["cleared_count"] == 2


def test_scanner_range_with_taxonomy_version_updates_only_selected_taxonomy(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_ticker_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, 0.01, 0.01, 0.04,
            1, 1, 1, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", "2024-01-10", 0, "FRESH", 0, 0, 0, 0, 0, 0,
            9, 9, 9, 9, 9, "old", "HIGH", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_ticker_swing_row(
        analysis_db,
        (
            "2024-01-10", "OTHER_TAXONOMY", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, 0.01, 0.01, 0.04,
            1, 1, 1, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", "2024-01-10", 0, "FRESH", 0, 0, 0, 0, 0, 0,
            7, 7, 7, 7, 7, "keep", "MEDIUM", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "OTHER_TAXONOMY", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        taxonomy_version="DC_TAXONOMY_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-scanner-range",
    )

    rows_after = _fetch_ticker_rows(analysis_db)
    selected_row = [row for row in rows_after if row["taxonomy_version"] == "DC_TAXONOMY_V1"][0]
    other_row = [row for row in rows_after if row["taxonomy_version"] == "OTHER_TAXONOMY"][0]
    assert summary["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert summary["updated_count"] == 1
    assert summary["cleared_count"] == 1
    assert selected_row["breakout_signal"] == 1
    assert other_row["breakout_signal"] == 7
    assert other_row["exit_risk_severity"] == "MEDIUM"


def test_scanner_does_not_insert_missing_base_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )
    assert summary["updated_count"] == 0
    assert _fetch_ticker_rows(analysis_db) == []


def test_breakout_and_pullback_rules_and_missing_subindustry_state(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "BBB", "Power", "UPS",
            100.0, 1000.0, -0.02, 0.04, 0.10, 0.20,
            99.0, 100.0, 98.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 110.0, 900.0, 1.0,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "CCC", "Power", "UPS",
            100.0, 1000.0, -0.03, 0.02, 0.15, 0.30,
            100.0, 105.0, 99.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 110.0, 900.0, None,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "DDD", "Power", "UPS",
            102.0, 1000.0, -0.04, 0.02, 0.10, 0.30,
            99.5, 100.0, 95.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 110.0, 900.0, 1.4,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "EEE", "Power", "UPS",
            101.0, 1000.0, -0.05, 0.01, 0.12, 0.25,
            110.0, 120.0, 100.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 111.0, 900.0, 1.4,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "MISSING_AS_OF_DATE",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "FFF", "Power", "Missing",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in rows:
        _insert_ticker_swing_row(analysis_db, row)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "BUY_ZONE:existing", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    rows_after = {row["ticker"]: row for row in _fetch_ticker_rows(analysis_db)}
    assert rows_after["AAA"]["breakout_signal"] == 1
    assert rows_after["BBB"]["fast_ema10_pullback_signal"] == 1
    assert rows_after["CCC"]["breakout_signal"] == 0
    assert rows_after["CCC"]["conservative_ema20_pullback_signal"] == 1
    assert rows_after["BBB"]["pullback_signal"] == 1
    assert rows_after["CCC"]["pullback_signal"] == 1
    assert rows_after["DDD"]["breakout_signal"] == 0
    assert rows_after["EEE"]["pullback_signal"] == 0
    assert rows_after["FFF"]["breakout_signal"] == 0
    assert rows_after["FFF"]["fast_ema10_pullback_signal"] == 0


def test_breakout_volume_threshold_is_strictly_greater_than_125pct(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.20,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "BBB", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.25,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "CCC", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.26,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "DDD", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.50,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "EEE", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, None,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in rows:
        _insert_ticker_swing_row(analysis_db, row)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "BUY_ZONE:existing", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    rows_after = {row["ticker"]: row for row in _fetch_ticker_rows(analysis_db)}
    assert rows_after["AAA"]["breakout_signal"] == 0
    assert rows_after["BBB"]["breakout_signal"] == 0
    assert rows_after["CCC"]["breakout_signal"] == 1
    assert rows_after["DDD"]["breakout_signal"] == 1
    assert rows_after["EEE"]["breakout_signal"] == 0


def test_exit_risk_rules_and_reason_order(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            90.0, 1000.0, 0.01, -0.09, 0.10, 0.20,
            95.0, 96.0, 100.0, None, None, None,
            None, None, None, 0, 0, 3, 5, 100.0, 900.0, 1.0,
            "LL", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "BAD_STATUS",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "BBB", "Power", "TRIM",
            90.0, 1000.0, 0.01, 0.01, 0.10, 0.20,
            100.0, 101.0, 95.0, None, None, None,
            None, None, None, 0, 0, 3, 5, 100.0, 900.0, 1.0,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "CCC", "Power", "NONE",
            None, 1000.0, None, None, None, None,
            None, None, None, None, None, None,
            None, None, None, None, None, 3, 5, None, None, None,
            None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, "BAD_STATUS",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in rows:
        _insert_ticker_swing_row(analysis_db, row)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "EXIT_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "TRIM",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "TRIM_WATCH", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    rows_after = {row["ticker"]: row for row in _fetch_ticker_rows(analysis_db)}
    assert rows_after["AAA"]["exit_risk_signal"] == 1
    assert rows_after["AAA"]["exit_reason"] == "close_below_ema20;return_10d_lt_minus_8pct;latest_structure_label_ll;subindustry_exit_zone"
    assert rows_after["AAA"]["exit_risk_severity"] == "HIGH"
    assert rows_after["BBB"]["exit_risk_signal"] == 1
    assert rows_after["BBB"]["exit_reason"] == "close_below_ema20;trim_watch_close_below_ma10"
    assert rows_after["BBB"]["exit_risk_severity"] == "MEDIUM"
    assert rows_after["CCC"]["exit_risk_signal"] == 0
    assert rows_after["CCC"]["exit_reason"] is None
    assert rows_after["CCC"]["exit_risk_severity"] is None


def test_scanner_null_inputs_do_not_crash_and_only_independent_exit_conditions_trigger(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            100.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            98.0, 99.0, None, None, None, None,
            None, None, None, 1, 1, 3, 5, None, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "BBB", "Power", "UPS",
            100.0, 1000.0, -0.02, 0.04, 0.10, 0.20,
            98.0, None, 98.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 110.0, 900.0, 1.0,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "CCC", "Power", "UPS",
            100.0, 1000.0, -0.03, 0.02, 0.15, None,
            100.0, 105.0, 99.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 110.0, 900.0, None,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "DDD", "Power", "TRIM",
            None, 1000.0, None, None, None, None,
            None, None, None, None, None, None,
            None, None, None, None, None, 3, 5, None, None, None,
            None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "EEE", "Power", "EXIT",
            None, 1000.0, None, None, None, None,
            None, None, None, None, None, None,
            None, None, None, None, None, 3, 5, None, None, None,
            "HH", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "FFF", "Power", "NONE",
            None, 1000.0, None, None, None, None,
            None, None, None, None, None, None,
            None, None, None, None, None, 3, 5, None, None, None,
            "LL", None, None, None, None, None, None, None,
            None, None, None, None, None, None, "BAD_STATUS",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in rows:
        _insert_ticker_swing_row(analysis_db, row)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "TRIM",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "TRIM_WATCH", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "EXIT",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "EXIT_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="update-existing",
    )

    rows_after = {row["ticker"]: row for row in _fetch_ticker_rows(analysis_db)}
    assert rows_after["AAA"]["breakout_signal"] == 0
    assert rows_after["AAA"]["fast_ema10_pullback_signal"] == 0
    assert rows_after["BBB"]["fast_ema10_pullback_signal"] == 0
    assert rows_after["CCC"]["conservative_ema20_pullback_signal"] == 0
    assert rows_after["DDD"]["exit_risk_signal"] == 0
    assert rows_after["DDD"]["exit_reason"] is None
    assert rows_after["DDD"]["exit_risk_severity"] is None
    assert rows_after["EEE"]["exit_risk_signal"] == 1
    assert rows_after["EEE"]["exit_reason"] == "subindustry_exit_zone"
    assert rows_after["EEE"]["exit_risk_severity"] == "MEDIUM"
    assert rows_after["FFF"]["exit_risk_signal"] == 1
    assert rows_after["FFF"]["exit_reason"] == "latest_structure_label_ll"
    assert rows_after["FFF"]["exit_risk_severity"] == "HIGH"


def test_scanner_write_modes_are_scoped(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            9, 9, 9, 9, 9, "old", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-11", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            9, 9, 9, 9, 9, "old", "OK",
            "DC_SWING_SIGNAL_V1",
            "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Power", "UPS",
            120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
            118.0, 119.0, 115.0, None, None, None,
            None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
            "HH", None, None, None, None, None, None, None,
            7, 7, 7, 7, 7, "keep", "OK",
            "OTHER_SIGNAL", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in rows:
        _insert_ticker_swing_row(analysis_db, row)
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_group_swing_row(
        analysis_db,
        (
            "2024-01-11", "DC_TAXONOMY_V1", "subindustry", "UPS",
            5, 5, 0.02, 0.03, 0.10, 0.20,
            80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
            "BUY_ZONE", "x", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    )

    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-11",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-scanner-range",
    )

    rows_after = _fetch_ticker_rows(analysis_db)
    current_rows = [row for row in rows_after if row["signal_version"] == "DC_SWING_SIGNAL_V1"]
    other_row = [row for row in rows_after if row["signal_version"] == "OTHER_SIGNAL"][0]
    assert summary["cleared_count"] == 2
    assert summary["updated_count"] == 2
    assert all(row["breakout_signal"] in (0, 1) for row in current_rows)
    assert all(row["exit_risk_severity"] in ("HIGH", "MEDIUM", "LOW", None) for row in current_rows)
    assert other_row["breakout_signal"] == 7


def test_scanner_write_modes_are_taxonomy_scoped_when_requested(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    for taxonomy_version, breakout_signal in (("DC_TAXONOMY_V1", 9), ("OTHER_TAXONOMY", 7)):
        _insert_ticker_swing_row(
            analysis_db,
            (
                "2024-01-10", taxonomy_version, "AAA", "Power", "UPS",
                120.0, 1000.0, 0.02, 0.03, 0.10, 0.20,
                118.0, 119.0, 115.0, None, None, None,
                None, None, None, 1, 1, 3, 5, 120.0, 900.0, 1.6,
                "HH", None, None, None, None, None, None, None,
                breakout_signal, breakout_signal, breakout_signal, breakout_signal, breakout_signal, "old", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        _insert_group_swing_row(
            analysis_db,
            (
                "2024-01-10", taxonomy_version, "subindustry", "UPS",
                5, 5, 0.02, 0.03, 0.10, 0.20,
                80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                "BUY_ZONE", "x", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )

    summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date="2024-01-10",
        end_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        taxonomy_version="DC_TAXONOMY_V1",
        run_id="scanner-run",
        created_at_utc="2026-05-17T12:00:00Z",
        write_mode="replace-scanner-range",
    )

    rows_after = _fetch_ticker_rows(analysis_db)
    selected_row = [row for row in rows_after if row["taxonomy_version"] == "DC_TAXONOMY_V1"][0]
    other_row = [row for row in rows_after if row["taxonomy_version"] == "OTHER_TAXONOMY"][0]
    assert summary["cleared_count"] == 1
    assert summary["updated_count"] == 1
    assert selected_row["breakout_signal"] == 1
    assert other_row["breakout_signal"] == 7
    assert other_row["exit_risk_severity"] is None
