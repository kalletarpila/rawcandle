import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import (
    _apply_report_canonical_v3_migration_to_connection,
    apply_report_canonical_v3_migration,
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


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _insert_ecosystem(conn: sqlite3.Connection, ecosystem_code: str = "DATACENTER") -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code,
            ecosystem_name,
            description,
            status
        ) VALUES (?, ?, ?, ?)
        """,
        (ecosystem_code, ecosystem_code.title(), None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    version_code: str = "V1",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id,
            version_code,
            version_label,
            source_type,
            source_reference,
            effective_from,
            effective_to,
            is_active,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            version_code,
            "Version 1",
            None,
            None,
            None,
            None,
            1,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            exchange,
            market,
            currency,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def _insert_watchlist(conn: sqlite3.Connection, ecosystem_id: int, watchlist_code: str = "PRIMARY") -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_watchlist (
            ecosystem_id,
            watchlist_code,
            watchlist_name,
            description,
            source_type,
            source_reference,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, watchlist_code, "Primary", None, None, None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def test_applying_v3_migration_creates_all_base_tables_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_base.db"

    apply_report_canonical_v3_migration(str(db_path))
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        expected_tables = {
            "eco_ecosystem",
            "eco_taxonomy_version",
            "eco_entity",
            "eco_taxonomy_entity_relation",
            "eco_watchlist",
            "eco_watchlist_member",
            "eco_report_window",
        }
        for table_name in expected_tables:
            assert _table_exists(conn, table_name)

        seed_rows = conn.execute(
            """
            SELECT window_code, window_label, window_days, is_active, sort_order
            FROM eco_report_window
            ORDER BY sort_order
            """
        ).fetchall()
        assert seed_rows == [
            ("daily", "Daily", 1, 1, 1),
            ("rolling2", "Rolling 2", 2, 1, 2),
            ("rolling5", "Rolling 5", 5, 1, 3),
            ("rolling30", "Rolling 30", 30, 1, 4),
        ]
    finally:
        conn.close()


def test_base_dimension_constraints_and_uniqueness(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_constraints.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_ecosystem (ecosystem_code, ecosystem_name, status)
                VALUES (?, ?, ?)
                """,
                ("BAD1", "Bad 1", "BROKEN"),
            )

        ecosystem_id = _insert_ecosystem(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_ecosystem (ecosystem_code, ecosystem_name, status)
                VALUES (?, ?, ?)
                """,
                ("DATACENTER", "Duplicate", "ACTIVE"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_version (ecosystem_id, version_code, is_active, status)
                VALUES (?, ?, ?, ?)
                """,
                (ecosystem_id, "BAD-STATUS", 0, "BROKEN"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_version (ecosystem_id, version_code, is_active, status)
                VALUES (?, ?, ?, ?)
                """,
                (ecosystem_id, "BAD-ACTIVE", 2, "ACTIVE"),
            )

        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_taxonomy_version(conn, ecosystem_id)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity (
                    ecosystem_id, entity_type, entity_code, entity_name, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (ecosystem_id, "BAD_TYPE", "X1", "Bad Entity", "ACTIVE"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity (
                    ecosystem_id, entity_type, entity_code, entity_name, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (ecosystem_id, "LAYER", "X2", "Bad Status", "BROKEN"),
            )

        layer_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="LAYER",
            entity_code="LAYER_AI",
            entity_name="AI",
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_entity(
                conn,
                ecosystem_id,
                entity_type="LAYER",
                entity_code="LAYER_AI",
                entity_name="AI Duplicate",
            )

        subindustry_1_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="SUBINDUSTRY",
            entity_code="SUB_GPU",
            entity_name="GPU",
        )
        subindustry_2_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="SUBINDUSTRY",
            entity_code="SUB_MEMORY",
            entity_name="Memory",
        )
        ticker_id = _insert_entity(
            conn,
            ecosystem_id,
            entity_type="TICKER",
            entity_code="NVDA",
            entity_name="NVIDIA",
            ticker="NVDA",
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_entity_relation (
                    taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                    relation_type, membership_role, is_primary, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    taxonomy_version_id,
                    ecosystem_id,
                    layer_id,
                    subindustry_1_id,
                    "BAD_RELATION",
                    None,
                    0,
                    "ACTIVE",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_entity_relation (
                    taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                    relation_type, membership_role, is_primary, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    taxonomy_version_id,
                    ecosystem_id,
                    layer_id,
                    subindustry_1_id,
                    "CONTAINS",
                    "BAD_ROLE",
                    0,
                    "ACTIVE",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_entity_relation (
                    taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                    relation_type, membership_role, is_primary, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    taxonomy_version_id,
                    ecosystem_id,
                    layer_id,
                    subindustry_1_id,
                    "CONTAINS",
                    "CORE",
                    2,
                    "ACTIVE",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_taxonomy_entity_relation (
                    taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                    relation_type, membership_role, weight, is_primary, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    taxonomy_version_id,
                    ecosystem_id,
                    layer_id,
                    subindustry_1_id,
                    "CONTAINS",
                    "CORE",
                    -0.1,
                    0,
                    "ACTIVE",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_watchlist (
                    ecosystem_id, watchlist_code, watchlist_name, status
                ) VALUES (?, ?, ?, ?)
                """,
                (ecosystem_id, "W1", "W1", "BROKEN"),
            )

        watchlist_id = _insert_watchlist(conn, ecosystem_id)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_watchlist(conn, ecosystem_id)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_watchlist_member (
                    watchlist_id, entity_id, member_role, member_status
                ) VALUES (?, ?, ?, ?)
                """,
                (watchlist_id, ticker_id, "BAD_ROLE", "ACTIVE"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_watchlist_member (
                    watchlist_id, entity_id, member_role, member_status
                ) VALUES (?, ?, ?, ?)
                """,
                (watchlist_id, ticker_id, "CORE", "BROKEN"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_window (
                    window_code, window_label, window_days, is_active, sort_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("bad", "Bad", 1, 1, 9),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_window (
                    window_code, window_label, window_days, is_active, sort_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("daily", "Bad Days", 0, 1, 9),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_window (
                    window_code, window_label, window_days, is_active, sort_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("daily", "Bad Active", 1, 2, 9),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_window (
                    window_code, window_label, window_days, is_active, sort_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("daily", "Bad Sort", 1, 1, -1),
            )

        conn.execute(
            """
            INSERT INTO eco_taxonomy_entity_relation (
                taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                relation_type, membership_role, weight, is_primary, sort_order,
                effective_from, effective_to, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                taxonomy_version_id,
                ecosystem_id,
                subindustry_1_id,
                ticker_id,
                "CONTAINS",
                "CORE",
                0.7,
                1,
                1,
                None,
                None,
                "ACTIVE",
            ),
        )
        conn.execute(
            """
            INSERT INTO eco_taxonomy_entity_relation (
                taxonomy_version_id, ecosystem_id, parent_entity_id, child_entity_id,
                relation_type, membership_role, weight, is_primary, sort_order,
                effective_from, effective_to, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                taxonomy_version_id,
                ecosystem_id,
                subindustry_2_id,
                ticker_id,
                "CONTAINS",
                "ADJACENT",
                0.3,
                0,
                2,
                None,
                None,
                "ACTIVE",
            ),
        )
        relation_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_taxonomy_entity_relation
            WHERE taxonomy_version_id = ?
              AND child_entity_id = ?
              AND relation_type = 'CONTAINS'
            """,
            (taxonomy_version_id, ticker_id),
        ).fetchone()[0]
        assert relation_count == 2

        conn.execute(
            """
            INSERT INTO eco_watchlist_member (
                watchlist_id, entity_id, member_role, member_status
            ) VALUES (?, ?, ?, ?)
            """,
            (watchlist_id, ticker_id, "CORE", "ACTIVE"),
        )
        conn.execute(
            """
            INSERT INTO eco_watchlist_member (
                watchlist_id, entity_id, member_role, member_status
            ) VALUES (?, ?, ?, ?)
            """,
            (watchlist_id, subindustry_1_id, "OPTIONAL", "ACTIVE"),
        )
        member_types = conn.execute(
            """
            SELECT e.entity_type
            FROM eco_watchlist_member wm
            JOIN eco_entity e ON e.entity_id = wm.entity_id
            WHERE wm.watchlist_id = ?
            ORDER BY e.entity_type
            """,
            (watchlist_id,),
        ).fetchall()
        assert member_types == [("SUBINDUSTRY",), ("TICKER",)]
    finally:
        conn.close()


def test_expected_indexes_exist() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _apply_report_canonical_v3_migration_to_connection(conn)
        assert "idx_eco_taxonomy_version_ecosystem_status" in _index_names(conn, "eco_taxonomy_version")
        assert "idx_eco_entity_ecosystem_type_status" in _index_names(conn, "eco_entity")
        assert "idx_eco_entity_ticker" in _index_names(conn, "eco_entity")
        assert "idx_eco_taxonomy_relation_parent" in _index_names(conn, "eco_taxonomy_entity_relation")
        assert "idx_eco_taxonomy_relation_child" in _index_names(conn, "eco_taxonomy_entity_relation")
        assert "idx_eco_watchlist_ecosystem_status" in _index_names(conn, "eco_watchlist")
        assert "idx_eco_watchlist_member_watchlist_status" in _index_names(conn, "eco_watchlist_member")
        assert "idx_eco_watchlist_member_entity" in _index_names(conn, "eco_watchlist_member")
    finally:
        conn.close()
