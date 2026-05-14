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
