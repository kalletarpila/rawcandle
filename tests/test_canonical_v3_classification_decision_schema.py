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
        ("run-1", ecosystem_id, taxonomy_version_id, "2026-06-02", "BUILD", "OK", 0, 0),
    )
    return "run-1"


def _insert_decision(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    classification_type: str,
    window_code: str,
    classification_state: str,
    decision_status: str = "OK",
    primary_reason: str | None = None,
    blocking_reason: str | None = None,
    risk_reason: str | None = None,
    next_action: str | None = None,
    priority_score: float | None = None,
    priority_label: str | None = None,
    sort_rank: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            priority_score,
            priority_label,
            sort_rank,
            source_classifier,
            classification_version,
            source_run_id,
            decision_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            ecosystem_id,
            "2026-06-02",
            taxonomy_version_id,
            window_code,
            entity_id,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            priority_score,
            priority_label,
            sort_rank,
            "v2_classifier",
            "V1",
            "source-run-1",
            decision_status,
        ),
    )


def test_classification_decision_migration_creates_table_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_classification_schema.db"

    apply_report_canonical_v3_migration(str(db_path))
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        assert _table_exists(conn, "eco_classification_decision")
    finally:
        conn.close()


def test_classification_decision_constraints_and_allowed_values(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_classification_constraints.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        entity_id = _insert_entity(conn, ecosystem_id)
        _insert_run(conn, ecosystem_id, taxonomy_version_id)

        _insert_decision(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            classification_type="daily_trigger",
            window_code="daily",
            classification_state="SELL_TRIGGER",
            primary_reason="HAS_EXIT_RISK",
            blocking_reason="BELOW_EMA20",
            next_action="REVIEW_WITH_ROLLING_CONTEXT",
            priority_score=10.0,
            priority_label="HIGH",
            sort_rank=1,
        )
        _insert_decision(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            classification_type="rolling2_sell_pressure",
            window_code="rolling2",
            classification_state="WATCH_PRESSURE",
            primary_reason="MILD_OR_UNCONFIRMED_SELL_PRESSURE",
            risk_reason="GROUP_RISK",
            next_action="MONITOR_NEXT_SESSION",
        )
        _insert_decision(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            classification_type="rolling5_pullback",
            window_code="rolling5",
            classification_state="PULLBACK_CANDIDATE",
            primary_reason="CONFIRMED_EMA20_PULLBACK_CONTEXT",
            blocking_reason="",
            next_action="REVIEW_FOR_DAILY_TRIGGER",
        )
        _insert_decision(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            classification_type="rolling30_buy",
            window_code="rolling30",
            classification_state="BUY_ZONE",
            primary_reason="UP_STRUCTURE_WITH_REPEATED_BUY_SIGNAL",
            blocking_reason="",
            next_action="TEXT_ALLOWED",
        )
        _insert_decision(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
            classification_type="rolling30_exit",
            window_code="rolling30",
            classification_state="EXIT_ZONE",
            primary_reason="ELEVATED_EXIT_RISK",
            risk_reason="CURRENT_HIGH_EXIT_RISK",
            next_action="FREE_TEXT_OK",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                classification_type="daily_trigger",
                window_code="daily",
                classification_state="BUY_TRIGGER",
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                classification_type="bad_type",
                window_code="daily",
                classification_state="WHATEVER_STATE",
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                classification_type="daily_trigger",
                window_code="rolling2",
                classification_state="CUSTOM_STATE_TEXT_ALLOWED",
                decision_status="BAD",
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                classification_type="rolling2_sell_pressure",
                window_code="daily",
                classification_state="CUSTOM_STATE_TEXT_ALLOWED",
                priority_score=-1.0,
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_id,
                classification_type="rolling5_pullback",
                window_code="daily",
                classification_state="CUSTOM_STATE_TEXT_ALLOWED",
                sort_rank=-1,
            )

        rows = conn.execute(
            """
            SELECT classification_type, classification_state, next_action
            FROM eco_classification_decision
            ORDER BY classification_type
            """
        ).fetchall()
        assert len(rows) == 5
        assert any(str(row[1]) == "SELL_TRIGGER" for row in rows)
        assert any(str(row[1]) == "WATCH_PRESSURE" for row in rows)
        assert any(str(row[1]) == "PULLBACK_CANDIDATE" for row in rows)
        assert any(str(row[1]) == "BUY_ZONE" for row in rows)
        assert any(str(row[1]) == "EXIT_ZONE" for row in rows)
        assert any(str(row[2]) == "FREE_TEXT_OK" for row in rows)
    finally:
        conn.close()


def test_classification_decision_indexes_exist(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_classification_indexes.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        assert _index_names(conn, "eco_classification_decision") >= {
            "idx_eco_classification_decision_run_window_type",
            "idx_eco_classification_decision_entity_window",
            "idx_eco_classification_decision_state",
            "idx_eco_classification_decision_status",
            "idx_eco_classification_decision_priority",
            "sqlite_autoindex_eco_classification_decision_1",
        }
    finally:
        conn.close()
