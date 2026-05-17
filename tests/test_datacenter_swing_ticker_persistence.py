from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_ticker_persistence import (
    load_bounded_ticker_ohlcv_history,
    persist_datacenter_ticker_swing_snapshots,
)


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
    assert row["bullish_divergence_signal"] == 1
    assert row["bearish_divergence_signal"] == 0
    assert row["bullish_candle_signal"] == 1
    assert row["bearish_candle_signal"] == 0


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
