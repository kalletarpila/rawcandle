import sqlite3

import pytest

from rawcandle.report_canonical_v3_base_builder import build_canonical_v3_base_run
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code, ecosystem_name, description, status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int, version_code: str, is_active: int = 1) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id, version_code, version_label, source_type, source_reference,
            effective_from, effective_to, is_active, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, version_code, version_code, None, None, None, None, is_active, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    *,
    entity_type: str,
    entity_code: str,
    status: str = "ACTIVE",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker,
            exchange, market, currency, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_code,
            entity_code if entity_type == "TICKER" else None,
            None,
            None,
            None,
            status,
        ),
    )
    return int(cursor.lastrowid)


def _insert_relation(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    ecosystem_id: int,
    parent_entity_id: int,
    child_entity_id: int,
    membership_role: str = "CORE",
) -> None:
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
            parent_entity_id,
            child_entity_id,
            "CONTAINS",
            membership_role,
            None,
            0,
            None,
            None,
            None,
            "ACTIVE",
        ),
    )


def _insert_watchlist(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_watchlist (
            ecosystem_id, watchlist_code, watchlist_name, description, source_type, source_reference, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, "DATACENTER_DEFAULT", "Datacenter default watchlist", None, "TXT", "/tmp/watchlist.txt", "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_watchlist_member(conn: sqlite3.Connection, watchlist_id: int, entity_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_watchlist_member (
            watchlist_id, entity_id, member_role, member_status,
            effective_from, effective_to, sort_order, removed_at_utc, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (watchlist_id, entity_id, None, "ACTIVE", None, None, None, None, None),
    )


def _create_daily_signal_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL
        )
        """
    )


def _insert_daily_signal(conn: sqlite3.Connection, ticker: str, signal_date: str = "2026-06-01") -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker
        ) VALUES (?, ?, ?)
        """,
        (signal_date, "DC_TAXONOMY_FULL_V1", ticker),
    )


def _seed_base_state(conn: sqlite3.Connection) -> dict[str, int]:
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id, "DC_TAXONOMY_FULL_V1")
    ecosystem_entity_id = _insert_entity(conn, ecosystem_id, entity_type="ECOSYSTEM", entity_code="DATACENTER")
    layer_id = _insert_entity(conn, ecosystem_id, entity_type="LAYER", entity_code="AI_INFRA")
    subindustry_id = _insert_entity(conn, ecosystem_id, entity_type="SUBINDUSTRY", entity_code="GPU")
    active_ticker_id = _insert_entity(conn, ecosystem_id, entity_type="TICKER", entity_code="NVDA")
    watch_only_ticker_id = _insert_entity(
        conn,
        ecosystem_id,
        entity_type="TICKER",
        entity_code="CRGY",
        status="WATCH_ONLY",
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=ecosystem_entity_id,
        child_entity_id=layer_id,
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=layer_id,
        child_entity_id=subindustry_id,
    )
    _insert_relation(
        conn,
        taxonomy_version_id=taxonomy_version_id,
        ecosystem_id=ecosystem_id,
        parent_entity_id=subindustry_id,
        child_entity_id=active_ticker_id,
    )
    watchlist_id = _insert_watchlist(conn, ecosystem_id)
    _insert_watchlist_member(conn, watchlist_id, active_ticker_id)
    _insert_watchlist_member(conn, watchlist_id, watch_only_ticker_id)
    _create_daily_signal_table(conn)
    _insert_daily_signal(conn, "NVDA")
    conn.commit()
    return {
        "ecosystem_id": ecosystem_id,
        "taxonomy_version_id": taxonomy_version_id,
        "ecosystem_entity_id": ecosystem_entity_id,
        "active_ticker_id": active_ticker_id,
        "watch_only_ticker_id": watch_only_ticker_id,
    }


def test_base_builder_creates_run_coverage_quality_and_includes_watchlist_only_crgy(tmp_path) -> None:
    db_path = tmp_path / "base_builder.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        ids = _seed_base_state(conn)
    finally:
        conn.close()

    summary = build_canonical_v3_base_run(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        signal_date="2026-06-01",
        taxonomy_version_code=None,
        run_id=None,
        run_type="BUILD",
        replace_run=False,
    )

    conn = _connect(str(db_path))
    try:
        assert summary["run_id"] == "V3_BASE_DATACENTER_2026_06_01_DC_TAXONOMY_FULL_V1"
        assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_ecosystem").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_watchlist").fetchone()[0] == 1

        coverage_rows = conn.execute(
            """
            SELECT entity_id, window_code, in_taxonomy, in_watchlist, has_daily_signal, coverage_status
            FROM eco_entity_coverage
            ORDER BY entity_id, window_code
            """
        ).fetchall()
        assert len(coverage_rows) == 5 * 4

        crgy_rows = conn.execute(
            """
            SELECT in_taxonomy, in_watchlist, coverage_status
            FROM eco_entity_coverage
            WHERE entity_id = ?
            ORDER BY window_code
            """,
            (ids["watch_only_ticker_id"],),
        ).fetchall()
        assert [tuple(row) for row in crgy_rows] == [
            (0, 1, "WATCHLIST_ONLY"),
            (0, 1, "WATCHLIST_ONLY"),
            (0, 1, "WATCHLIST_ONLY"),
            (0, 1, "WATCHLIST_ONLY"),
        ]

        nvda_rows = conn.execute(
            """
            SELECT has_daily_signal, coverage_status
            FROM eco_entity_coverage
            WHERE entity_id = ?
            ORDER BY window_code
            """,
            (ids["active_ticker_id"],),
        ).fetchall()
        assert [tuple(row) for row in nvda_rows] == [
            (1, "OK"),
            (1, "OK"),
            (1, "OK"),
            (1, "OK"),
        ]

        quality_rows = conn.execute(
            """
            SELECT quality_scope, scope_entity_id
            FROM eco_quality_summary
            ORDER BY window_code, quality_scope
            """
        ).fetchall()
        assert len(quality_rows) == 8
        assert all(int(row["scope_entity_id"]) == ids["ecosystem_entity_id"] for row in quality_rows)
    finally:
        conn.close()


def test_base_builder_missing_daily_signal_and_replace_run_behavior(tmp_path) -> None:
    db_path = tmp_path / "base_builder_replace.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        ids = _seed_base_state(conn)
        conn.execute("DELETE FROM dc_ticker_swing_signal_daily WHERE ticker = ?", ("NVDA",))
        conn.commit()
    finally:
        conn.close()

    build_canonical_v3_base_run(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        signal_date="2026-06-01",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        run_id="run-fixed",
        replace_run=False,
    )

    conn = _connect(str(db_path))
    try:
        nvda_rows = conn.execute(
            """
            SELECT has_daily_signal, coverage_status
            FROM eco_entity_coverage
            WHERE run_id = ? AND entity_id = ?
            ORDER BY window_code
            """,
            ("run-fixed", ids["active_ticker_id"]),
        ).fetchall()
        assert [tuple(row) for row in nvda_rows] == [
            (0, "MISSING_DAILY_SIGNAL"),
            (0, "MISSING_DAILY_SIGNAL"),
            (0, "MISSING_DAILY_SIGNAL"),
            (0, "MISSING_DAILY_SIGNAL"),
        ]
    finally:
        conn.close()

    with pytest.raises(ValueError, match="already exists"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            run_id="run-fixed",
            replace_run=False,
        )

    summary = build_canonical_v3_base_run(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        signal_date="2026-06-01",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        run_id="run-fixed",
        replace_run=True,
    )
    conn = _connect(str(db_path))
    try:
        assert summary["coverage_rows_inserted"] == 20
        assert conn.execute("SELECT COUNT(*) FROM eco_report_run WHERE run_id = ?", ("run-fixed",)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage WHERE run_id = ?", ("run-fixed",)).fetchone()[0] == 20
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary WHERE run_id = ?", ("run-fixed",)).fetchone()[0] == 8
    finally:
        conn.close()


def test_base_builder_raises_clear_errors_for_missing_prerequisites(tmp_path) -> None:
    db_path = tmp_path / "base_builder_errors.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing ecosystem"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
        )

    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="No active taxonomy version found"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
        )

    conn = _connect(str(db_path))
    try:
        _insert_taxonomy_version(conn, ecosystem_id, "V1", is_active=1)
        _insert_taxonomy_version(conn, ecosystem_id, "V2", is_active=1)
        _insert_entity(conn, ecosystem_id, entity_type="ECOSYSTEM", entity_code="DATACENTER")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="Multiple active taxonomy versions"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
        )

    conn = _connect(str(db_path))
    try:
        conn.execute("UPDATE eco_taxonomy_version SET is_active = 0")
        conn.execute("UPDATE eco_report_window SET is_active = 0")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="Missing taxonomy version 'V1'|No active report windows found"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
            taxonomy_version_code="V1",
        )


def test_base_builder_raises_error_if_no_active_windows(tmp_path) -> None:
    db_path = tmp_path / "base_builder_no_windows.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        _insert_taxonomy_version(conn, ecosystem_id, "DC_TAXONOMY_FULL_V1")
        _insert_entity(conn, ecosystem_id, entity_type="ECOSYSTEM", entity_code="DATACENTER")
        conn.execute("UPDATE eco_report_window SET is_active = 0")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="No active report windows found"):
        build_canonical_v3_base_run(
            db_path=str(db_path),
            ecosystem_code="DATACENTER",
            signal_date="2026-06-01",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        )
