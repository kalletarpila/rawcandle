import sqlite3

import pytest

from analysis.database_manager import DatabaseManager


def _table_exists(db_path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
    return row is not None


def _table_columns(db_path, table_name: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _primary_key_columns(db_path, table_name: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in sorted(rows, key=lambda row: int(row[5])) if int(row[5]) > 0]


def _index_names(db_path, table_name: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def test_database_manager_initializes_dc_ecosystem_membership_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    assert _table_exists(db_path, "dc_ecosystem_membership")


def test_database_manager_initializes_dc_group_index_daily_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    assert _table_exists(db_path, "dc_group_index_daily")


def test_database_manager_initializes_dc_ticker_swing_signal_daily_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    table_name = "dc_ticker_swing_signal_daily"
    assert _table_exists(db_path, table_name)

    columns = _table_columns(db_path, table_name)
    assert {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "breakout_signal",
        "exit_risk_severity",
        "latest_structure_age_trading_days",
        "latest_structure_freshness",
        "ticker_trend_state",
        "structure_epoch_id",
        "latest_bos_event_type",
        "latest_bos_event_date",
        "latest_bos_confirmed_as_of_date",
        "latest_bos_age_trading_days",
        "latest_bos_freshness",
        "latest_reset_event_date",
        "latest_reset_confirmed_as_of_date",
        "latest_reset_reason",
        "latest_reset_age_trading_days",
        "latest_reset_freshness",
        "signal_version",
    }.issubset(columns)

    assert _primary_key_columns(db_path, table_name) == [
        "signal_date",
        "taxonomy_version",
        "ticker",
        "signal_version",
    ]

    indexes = _index_names(db_path, table_name)
    assert {
        "idx_dc_ticker_swing_signal_daily_date_version",
        "idx_dc_ticker_swing_signal_daily_ticker_date",
        "idx_dc_ticker_swing_signal_daily_subindustry_date",
        "idx_dc_ticker_swing_signal_daily_breakout",
        "idx_dc_ticker_swing_signal_daily_pullback",
        "idx_dc_ticker_swing_signal_daily_exit_risk",
    }.issubset(indexes)


def test_database_manager_adds_exit_risk_severity_to_existing_ticker_swing_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT,
                primary_subindustry TEXT,
                close REAL,
                volume REAL,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                ma10 REAL,
                ema10 REAL,
                ema20 REAL,
                distance_to_ma10_pct REAL,
                distance_to_ema10_pct REAL,
                distance_to_ema20_pct REAL,
                above_ma10 INTEGER,
                above_ema10 INTEGER,
                above_ema20 INTEGER,
                ema10_slope_positive INTEGER,
                ema20_slope_positive INTEGER,
                ema10_slope_lookback INTEGER,
                ema20_slope_lookback INTEGER,
                highest_close_20d REAL,
                volume_avg_20d REAL,
                volume_vs_avg20 REAL,
                latest_structure_label TEXT,
                latest_structure_confirmed_as_of_date TEXT,
                bullish_divergence_signal INTEGER,
                bearish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                hidden_bearish_divergence_signal INTEGER,
                bullish_candle_signal INTEGER,
                bearish_candle_signal INTEGER,
                breakout_signal INTEGER,
                fast_ema10_pullback_signal INTEGER,
                conservative_ema20_pullback_signal INTEGER,
                pullback_signal INTEGER,
                exit_risk_signal INTEGER,
                exit_reason TEXT,
                price_data_status TEXT,
                signal_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, ticker, signal_version)
            )
            """
        )
        conn.commit()

    DatabaseManager(str(db_path)).close()

    columns = _table_columns(db_path, "dc_ticker_swing_signal_daily")
    assert "exit_risk_severity" in columns
    assert "latest_structure_age_trading_days" in columns
    assert "latest_structure_freshness" in columns
    assert "ticker_trend_state" in columns
    assert "structure_epoch_id" in columns
    assert "latest_bos_event_type" in columns
    assert "latest_bos_event_date" in columns
    assert "latest_bos_confirmed_as_of_date" in columns
    assert "latest_bos_age_trading_days" in columns
    assert "latest_bos_freshness" in columns
    assert "latest_reset_event_date" in columns
    assert "latest_reset_confirmed_as_of_date" in columns
    assert "latest_reset_reason" in columns
    assert "latest_reset_age_trading_days" in columns
    assert "latest_reset_freshness" in columns


def test_database_manager_initializes_dc_group_swing_signal_daily_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    table_name = "dc_group_swing_signal_daily"
    assert _table_exists(db_path, table_name)

    columns = _table_columns(db_path, table_name)
    assert {"signal_date", "taxonomy_version", "group_type", "timing_state", "signal_version"}.issubset(columns)

    assert _primary_key_columns(db_path, table_name) == [
        "signal_date",
        "taxonomy_version",
        "group_type",
        "group_name",
        "signal_version",
    ]

    indexes = _index_names(db_path, table_name)
    assert {
        "idx_dc_group_swing_signal_daily_date_version",
        "idx_dc_group_swing_signal_daily_group_date",
        "idx_dc_group_swing_signal_daily_timing_state",
        "idx_dc_group_swing_signal_daily_risk",
    }.issubset(indexes)


def test_database_manager_initializes_dc_group_synthetic_ohlc_daily_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    table_name = "dc_group_synthetic_ohlc_daily"
    assert _table_exists(db_path, table_name)

    columns = _table_columns(db_path, table_name)
    assert {
        "ohlc_date",
        "taxonomy_version",
        "group_type",
        "latest_structure_label",
        "latest_structure_age_trading_days",
        "latest_structure_freshness",
        "latest_bos_event_type",
        "latest_bos_event_date",
        "latest_bos_confirmed_as_of_date",
        "latest_bos_age_trading_days",
        "latest_bos_freshness",
        "latest_reset_event_date",
        "latest_reset_confirmed_as_of_date",
        "latest_reset_reason",
        "latest_reset_age_trading_days",
        "latest_reset_freshness",
        "calc_version",
    }.issubset(columns)

    assert _primary_key_columns(db_path, table_name) == [
        "ohlc_date",
        "taxonomy_version",
        "group_type",
        "group_name",
        "calc_version",
    ]

    indexes = _index_names(db_path, table_name)
    assert {
        "idx_dc_group_synthetic_ohlc_daily_date_version",
        "idx_dc_group_synthetic_ohlc_daily_group_date",
        "idx_dc_group_synthetic_ohlc_daily_structure",
        "idx_dc_group_synthetic_ohlc_daily_trend",
    }.issubset(indexes)


def test_database_manager_adds_group_bos_reset_columns_to_existing_group_synth_table(tmp_path):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                member_count INTEGER,
                eligible_count INTEGER,
                synthetic_open REAL,
                synthetic_high REAL,
                synthetic_low REAL,
                synthetic_close REAL,
                synthetic_volume REAL,
                ma20 REAL,
                ema20 REAL,
                distance_to_ema20_pct REAL,
                volatility_20d REAL,
                pivot_radius INTEGER,
                latest_pivot_high_date TEXT,
                latest_pivot_high_value REAL,
                latest_pivot_low_date TEXT,
                latest_pivot_low_value REAL,
                latest_structure_label TEXT,
                trend_classification TEXT,
                relative_base_window INTEGER,
                relative_open_20 REAL,
                relative_high_20 REAL,
                relative_low_20 REAL,
                relative_close_20 REAL,
                relative_upper_wick_20 REAL,
                relative_lower_wick_20 REAL,
                relative_close_extension_20 REAL,
                relative_high_extension_20 REAL,
                relative_low_extension_20 REAL,
                relative_eligible_count INTEGER,
                data_quality_status TEXT,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (ohlc_date, taxonomy_version, group_type, group_name, calc_version)
            )
            """
        )
        conn.commit()

    DatabaseManager(str(db_path)).close()

    columns = _table_columns(db_path, "dc_group_synthetic_ohlc_daily")
    assert "latest_structure_age_trading_days" in columns
    assert "latest_structure_freshness" in columns
    assert "latest_bos_event_type" in columns
    assert "latest_bos_event_date" in columns
    assert "latest_bos_confirmed_as_of_date" in columns
    assert "latest_bos_age_trading_days" in columns
    assert "latest_bos_freshness" in columns
    assert "latest_reset_event_date" in columns
    assert "latest_reset_confirmed_as_of_date" in columns
    assert "latest_reset_reason" in columns
    assert "latest_reset_age_trading_days" in columns
    assert "latest_reset_freshness" in columns


def test_dc_ecosystem_membership_primary_key_rejects_duplicates(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    manager.close()

    with sqlite3.connect(db_path) as conn:
        row = (
            "DC_TAXONOMY_V1",
            "VRT",
            "Electrical & power systems",
            "UPS, switchgear, PDU",
            "CORE",
            1,
            1.0,
            None,
            "2026-05-14T00:00:00Z",
        )
        conn.execute(
            """
            INSERT INTO dc_ecosystem_membership (
                taxonomy_version,
                ticker,
                layer,
                subindustry,
                report_group_status,
                is_primary,
                role_weight,
                notes,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO dc_ecosystem_membership (
                    taxonomy_version,
                    ticker,
                    layer,
                    subindustry,
                    report_group_status,
                    is_primary,
                    role_weight,
                    notes,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
