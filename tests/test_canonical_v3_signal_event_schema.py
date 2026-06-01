import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


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


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code,
            ecosystem_name,
            description,
            status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
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
        (ecosystem_id, "DC_TAXONOMY_FULL_V1", "V1", None, None, None, None, 1, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_entity(conn: sqlite3.Connection, ecosystem_id: int) -> int:
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
        (ecosystem_id, "TICKER", "NVDA", "NVDA", "NVDA", None, None, None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> str:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            run_type,
            status,
            warning_count,
            error_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("run-1", ecosystem_id, taxonomy_version_id, "2026-06-01", "BUILD", "OK", 0, 0),
    )
    return "run-1"


def _insert_signal_observation(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    signal_name: str = "bullish_divergence",
    observed_date: str = "2026-06-01",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            signal_name,
            signal_family,
            signal_direction,
            signal_value,
            observed_date,
            source_table,
            source_run_id,
            source_event_id,
            signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            ecosystem_id,
            "2026-06-01",
            taxonomy_version_id,
            "daily",
            entity_id,
            signal_name,
            "divergence",
            "BULLISH",
            "YES",
            observed_date,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def test_signal_event_migration_creates_tables_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_signal_event.db"

    apply_report_canonical_v3_migration(str(db_path))
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        expected_tables = {
            "eco_signal_observation",
            "eco_signal_relevance",
            "eco_entity_event",
        }
        for table_name in expected_tables:
            assert _table_exists(conn, table_name)
    finally:
        conn.close()


def test_signal_and_relevance_constraints(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_signal_constraints.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        entity_id = _insert_entity(conn, ecosystem_id)
        run_id = _insert_run(conn, ecosystem_id, taxonomy_version_id)

        signal_observation_id = _insert_signal_observation(
            conn,
            run_id=run_id,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_signal_observation(
                conn,
                run_id=run_id,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_signal_observation (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    signal_name, observed_date, signal_direction, signal_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", entity_id, "x", "2026-06-01", "BAD", "ACTIVE"),
            )
        conn.execute(
            """
            INSERT INTO eco_signal_observation (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                signal_name, observed_date, signal_direction, signal_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", entity_id, "ma_break", "2026-05-31", None, "ACTIVE"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_signal_observation (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    signal_name, observed_date, signal_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", entity_id, "x2", "2026-06-01", "BAD"),
            )

        conn.execute(
            """
            INSERT INTO eco_signal_relevance (
                signal_observation_id,
                relevance_label,
                relevance_score,
                relevance_reason,
                trend_alignment,
                dow_context,
                bos_context,
                reset_context,
                counter_trend_context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (signal_observation_id, "RELEVANT", 1.0, None, None, None, None, None, None),
        )
        conn.execute(
            """
            INSERT INTO eco_signal_relevance (
                signal_observation_id,
                relevance_label,
                relevance_score,
                relevance_reason,
                trend_alignment,
                dow_context,
                bos_context,
                reset_context,
                counter_trend_context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (signal_observation_id, "CONTEXTUAL", 0.5, None, None, None, None, None, None),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_signal_relevance (
                    signal_observation_id,
                    relevance_label
                ) VALUES (?, ?)
                """,
                (signal_observation_id, "RELEVANT"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_signal_relevance (
                    signal_observation_id,
                    relevance_label
                ) VALUES (?, ?)
                """,
                (signal_observation_id, "BAD"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_signal_relevance (
                    signal_observation_id,
                    relevance_label,
                    relevance_score
                ) VALUES (?, ?, ?)
                """,
                (signal_observation_id, "NOISE", -1.0),
            )
    finally:
        conn.close()


def test_entity_event_constraints_and_indexes(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_event_constraints.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        entity_id = _insert_entity(conn, ecosystem_id)
        run_id = _insert_run(conn, ecosystem_id, taxonomy_version_id)

        conn.execute(
            """
            INSERT INTO eco_entity_event (
                run_id,
                ecosystem_id,
                taxonomy_version_id,
                entity_id,
                event_date,
                event_type,
                source_table,
                source_run_id,
                source_event_id,
                event_key,
                event_label,
                event_direction,
                event_status,
                event_payload_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                ecosystem_id,
                taxonomy_version_id,
                entity_id,
                "2026-06-01",
                "BOS",
                None,
                None,
                None,
                "bos:2026-06-01:nvda:1",
                None,
                "UP",
                "ACTIVE",
                None,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_event (
                    run_id,
                    ecosystem_id,
                    taxonomy_version_id,
                    entity_id,
                    event_date,
                    event_type,
                    source_event_id,
                    event_key,
                    event_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    ecosystem_id,
                    taxonomy_version_id,
                    entity_id,
                    "2026-06-01",
                    "BOS",
                    None,
                    "bos:2026-06-01:nvda:1",
                    "ACTIVE",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_event (
                    run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type, event_key, event_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, taxonomy_version_id, entity_id, "2026-06-01", "BAD", "bad-key", "ACTIVE"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_event (
                    run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type, event_key, event_direction, event_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, taxonomy_version_id, entity_id, "2026-06-01", "RESET", "reset-key", "BAD", "ACTIVE"),
            )
        conn.execute(
            """
            INSERT INTO eco_entity_event (
                run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type, event_key, event_direction, event_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, ecosystem_id, taxonomy_version_id, entity_id, "2026-06-02", "RESET", "reset-key", None, "STALE"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_event (
                    run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type, event_key, event_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, taxonomy_version_id, entity_id, "2026-06-03", "RESET", "reset-key-2", "BAD"),
            )

        assert "idx_eco_signal_observation_date_taxonomy_window_entity" in _index_names(conn, "eco_signal_observation")
        assert "idx_eco_signal_observation_ecosystem_family_status" in _index_names(conn, "eco_signal_observation")
        assert "idx_eco_signal_observation_entity_name_observed_date" in _index_names(conn, "eco_signal_observation")
        assert "idx_eco_signal_observation_source_run_id" in _index_names(conn, "eco_signal_observation")
        assert "idx_eco_signal_relevance_signal_observation_id" in _index_names(conn, "eco_signal_relevance")
        assert "idx_eco_signal_relevance_label" in _index_names(conn, "eco_signal_relevance")
        assert "idx_eco_signal_relevance_assigned_at_utc" in _index_names(conn, "eco_signal_relevance")
        assert "idx_eco_entity_event_ecosystem_type_status" in _index_names(conn, "eco_entity_event")
        assert "idx_eco_entity_event_taxonomy_entity_date" in _index_names(conn, "eco_entity_event")
        assert "idx_eco_entity_event_source_run_id" in _index_names(conn, "eco_entity_event")
        assert "idx_eco_entity_event_date_type" in _index_names(conn, "eco_entity_event")
    finally:
        conn.close()
