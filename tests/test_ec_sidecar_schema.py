import sqlite3

import pytest

from rawcandle.ec_sidecar_migration import (
    _apply_ec_sidecar_migration_to_connection,
    apply_ec_sidecar_migration,
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _foreign_key_tables(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return {str(row[2]) for row in rows}


def _insert_ecosystem(
    conn: sqlite3.Connection,
    ecosystem_code: str = "DATACENTER",
    ecosystem_name: str = "Datacenter",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_ecosystem (
            ecosystem_code,
            ecosystem_name,
            status
        ) VALUES (?, ?, ?)
        """,
        (ecosystem_code, ecosystem_name, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_taxonomy_version (
            ecosystem_id,
            taxonomy_version_code,
            taxonomy_name,
            source_type,
            source_reference,
            source_hash,
            status,
            is_active,
            active_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            taxonomy_version_code,
            "Datacenter Full V1",
            "CSV",
            "data/datacenter_ecosystem_taxonomy_full_v1.csv",
            "hash-1",
            "ACTIVE",
            1,
            "2026-06-01",
        ),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    entity_name: str | None,
    ticker: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            status,
            active_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            "ACTIVE",
            "2026-06-01",
        ),
    )
    return int(cursor.lastrowid)


def _insert_alias(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    entity_id: int,
    *,
    alias_type: str,
    alias_value: str,
    source_system: str | None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_entity_alias (
            ecosystem_id,
            entity_id,
            alias_type,
            alias_value,
            source_system,
            status,
            active_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            entity_id,
            alias_type,
            alias_value,
            source_system,
            "ACTIVE",
            "2026-06-01",
        ),
    )
    return int(cursor.lastrowid)


def _insert_membership(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    taxonomy_version_id: int,
    *,
    parent_entity_id: int,
    child_entity_id: int,
    membership_type: str = "CONTAINS",
    membership_role: str | None = None,
    is_primary: int = 0,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_membership (
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id,
            child_entity_id,
            membership_type,
            membership_role,
            is_primary,
            role_weight,
            status,
            active_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id,
            child_entity_id,
            membership_type,
            membership_role,
            is_primary,
            1.0,
            "ACTIVE",
            "2026-06-01",
        ),
    )
    return int(cursor.lastrowid)


def _insert_watchlist(conn: sqlite3.Connection, ecosystem_id: int, watchlist_code: str = "PRIMARY") -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_watchlist (
            ecosystem_id,
            watchlist_code,
            watchlist_name,
            source_type,
            source_reference,
            status,
            active_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            watchlist_code,
            "Primary Watchlist",
            "FILE",
            "watchlists/datacenter_watchlist.txt",
            "ACTIVE",
            "2026-06-01",
        ),
    )
    return int(cursor.lastrowid)


def _insert_watchlist_member(
    conn: sqlite3.Connection,
    watchlist_id: int,
    entity_id: int,
    *,
    active_from: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_watchlist_member (
            watchlist_id,
            entity_id,
            member_role,
            status,
            active_from,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (watchlist_id, entity_id, "CORE", "ACTIVE", active_from, None),
    )
    return int(cursor.lastrowid)


def test_ec_sidecar_migration_creates_tables_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "ec_sidecar.db"

    apply_ec_sidecar_migration(str(db_path))
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        expected_tables = {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
            "ec_entity_alias",
            "ec_membership",
            "ec_watchlist",
            "ec_watchlist_member",
        }
        for table_name in expected_tables:
            assert _table_exists(conn, table_name)
    finally:
        conn.close()


def test_ec_sidecar_schema_columns_indexes_and_foreign_keys(tmp_path) -> None:
    db_path = tmp_path / "ec_sidecar_shape.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        assert {
            "ecosystem_id",
            "ecosystem_code",
            "ecosystem_name",
            "status",
            "created_at_utc",
            "updated_at_utc",
        }.issubset(_table_columns(conn, "ec_ecosystem"))
        assert {
            "taxonomy_version_id",
            "ecosystem_id",
            "taxonomy_version_code",
            "source_hash",
            "is_active",
            "active_from",
            "active_to",
            "created_at_utc",
        }.issubset(_table_columns(conn, "ec_taxonomy_version"))
        assert {
            "entity_id",
            "ecosystem_id",
            "entity_type",
            "entity_code",
            "entity_name",
            "ticker",
            "status",
            "active_from",
            "active_to",
            "created_at_utc",
            "updated_at_utc",
        }.issubset(_table_columns(conn, "ec_entity"))
        assert {
            "entity_alias_id",
            "ecosystem_id",
            "entity_id",
            "alias_type",
            "alias_value",
            "source_system",
            "status",
            "active_from",
            "active_to",
            "created_at_utc",
        }.issubset(_table_columns(conn, "ec_entity_alias"))
        assert {
            "membership_id",
            "ecosystem_id",
            "taxonomy_version_id",
            "parent_entity_id",
            "child_entity_id",
            "membership_type",
            "membership_role",
            "is_primary",
            "role_weight",
            "status",
            "active_from",
            "active_to",
            "source_note",
            "created_at_utc",
        }.issubset(_table_columns(conn, "ec_membership"))
        assert {
            "watchlist_id",
            "ecosystem_id",
            "watchlist_code",
            "watchlist_name",
            "source_type",
            "source_reference",
            "status",
            "active_from",
            "active_to",
            "created_at_utc",
            "updated_at_utc",
        }.issubset(_table_columns(conn, "ec_watchlist"))
        assert {
            "watchlist_member_id",
            "watchlist_id",
            "entity_id",
            "member_role",
            "status",
            "active_from",
            "active_to",
            "notes",
            "created_at_utc",
        }.issubset(_table_columns(conn, "ec_watchlist_member"))

        assert {
            "idx_ec_entity_ecosystem_type_code",
            "idx_ec_entity_ticker",
        }.issubset(_index_names(conn, "ec_entity"))
        assert "idx_ec_entity_alias_lookup" in _index_names(conn, "ec_entity_alias")
        assert {
            "idx_ec_membership_taxonomy_parent",
            "idx_ec_membership_taxonomy_child",
        }.issubset(_index_names(conn, "ec_membership"))
        assert "idx_ec_watchlist_member_watchlist" in _index_names(conn, "ec_watchlist_member")
        assert "idx_ec_taxonomy_version_ecosystem_active" in _index_names(conn, "ec_taxonomy_version")

        assert _foreign_key_tables(conn, "ec_taxonomy_version") == {"ec_ecosystem"}
        assert _foreign_key_tables(conn, "ec_entity") == {"ec_ecosystem"}
        assert _foreign_key_tables(conn, "ec_entity_alias") == {"ec_ecosystem", "ec_entity"}
        assert _foreign_key_tables(conn, "ec_membership") == {
            "ec_ecosystem",
            "ec_taxonomy_version",
            "ec_entity",
        }
        assert _foreign_key_tables(conn, "ec_watchlist") == {"ec_ecosystem"}
        assert _foreign_key_tables(conn, "ec_watchlist_member") == {"ec_watchlist", "ec_entity"}
    finally:
        conn.close()


def test_ec_sidecar_basic_insert_path_and_constraints(tmp_path) -> None:
    db_path = tmp_path / "ec_sidecar_constraints.db"
    apply_ec_sidecar_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ec_ecosystem (ecosystem_code, ecosystem_name, status)
                VALUES (?, ?, ?)
                """,
                ("BAD", "Bad", "BROKEN"),
            )

        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        ecosystem_entity_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="ECOSYSTEM",
            entity_code="DATACENTER",
            entity_name="Datacenter",
        )
        group_l1_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="GROUP_L1",
            entity_code="COMPUTE_SILICON",
            entity_name="Compute silicon",
        )
        group_l2_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="GROUP_L2",
            entity_code="GPUS",
            entity_name="GPUs",
        )
        ticker_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVIDIA",
            ticker="NVDA",
        )

        _insert_alias(
            conn,
            ecosystem_id,
            ecosystem_entity_id,
            alias_type="DC_GROUP_NAME",
            alias_value="DC_ECOSYSTEM_TOTAL",
            source_system="dc_group_swing_signal_daily",
        )
        _insert_membership(
            conn,
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id=ecosystem_entity_id,
            child_entity_id=group_l1_id,
            membership_role="PRIMARY",
            is_primary=1,
        )
        _insert_membership(
            conn,
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id=group_l1_id,
            child_entity_id=group_l2_id,
            membership_role="PRIMARY",
            is_primary=1,
        )
        _insert_membership(
            conn,
            ecosystem_id,
            taxonomy_version_id,
            parent_entity_id=group_l2_id,
            child_entity_id=ticker_id,
            membership_role="PRIMARY",
            is_primary=1,
        )
        watchlist_id = _insert_watchlist(conn, ecosystem_id, "DATACENTER_DEFAULT")
        _insert_watchlist_member(conn, watchlist_id, ticker_id, active_from="2026-06-01")

        other_ecosystem_id = _insert_ecosystem(conn, ecosystem_code="ALTDC", ecosystem_name="Alt DC")
        _insert_entity(
            conn,
            other_ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVIDIA duplicate across ecosystems",
            ticker="NVDA",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_entity(
                conn,
                ecosystem_id,
                entity_type="TICKER",
                entity_code="NVDA",
                entity_name="Duplicate same ecosystem/type",
                ticker="NVDA_2",
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_alias(
                conn,
                ecosystem_id,
                ecosystem_entity_id,
                alias_type="DC_GROUP_NAME",
                alias_value="DC_ECOSYSTEM_TOTAL",
                source_system="dc_group_swing_signal_daily",
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_membership(
                conn,
                ecosystem_id,
                taxonomy_version_id,
                parent_entity_id=group_l2_id,
                child_entity_id=ticker_id,
                membership_role="PRIMARY",
                is_primary=1,
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_watchlist(conn, ecosystem_id, "DATACENTER_DEFAULT")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_watchlist_member(conn, watchlist_id, ticker_id, active_from="2026-06-01")
    finally:
        conn.close()


def test_ec_sidecar_connection_helper_applies_schema_in_memory() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _apply_ec_sidecar_migration_to_connection(conn)
        assert _table_exists(conn, "ec_entity_alias")
        assert _table_exists(conn, "ec_membership")
    finally:
        conn.close()
