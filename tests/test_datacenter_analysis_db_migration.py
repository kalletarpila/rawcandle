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
    assert {"signal_date", "taxonomy_version", "ticker", "breakout_signal", "signal_version"}.issubset(columns)

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
    assert {"ohlc_date", "taxonomy_version", "group_type", "latest_structure_label", "calc_version"}.issubset(columns)

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
