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


def _insert_entity(
    conn: sqlite3.Connection,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
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
            entity_code,
            entity_code if entity_type == "TICKER" else None,
            None,
            None,
            None,
            "ACTIVE",
        ),
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
            completed_at_utc,
            warning_count,
            error_count,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            ecosystem_id,
            taxonomy_version_id,
            "2026-06-01",
            "BUILD",
            "OK",
            None,
            0,
            0,
            None,
        ),
    )
    return "run-1"


def test_core_fact_migration_creates_tables_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_core_facts.db"

    apply_report_canonical_v3_migration(str(db_path))
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        expected_tables = {
            "eco_report_run",
            "eco_entity_window_snapshot",
            "eco_entity_metric_value",
            "eco_entity_coverage",
            "eco_quality_summary",
        }
        for table_name in expected_tables:
            assert _table_exists(conn, table_name)
    finally:
        conn.close()


def test_core_fact_constraints_and_uniqueness(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_core_fact_constraints.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        ecosystem_entity_id = _insert_entity(conn, ecosystem_id, "ECOSYSTEM", "DATACENTER")
        ticker_entity_id = _insert_entity(conn, ecosystem_id, "TICKER", "NVDA")
        run_id = _insert_run(conn, ecosystem_id, taxonomy_version_id)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_run (
                    run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("bad-run-type", ecosystem_id, taxonomy_version_id, "2026-06-01", "BAD", "OK"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_run (
                    run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("bad-status", ecosystem_id, taxonomy_version_id, "2026-06-01", "BUILD", "BAD"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_run (
                    run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("bad-counts", ecosystem_id, taxonomy_version_id, "2026-06-01", "BUILD", "OK", -1, 0),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_report_run (
                    run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("bad-error-counts", ecosystem_id, taxonomy_version_id, "2026-06-01", "BUILD", "OK", 0, -1),
            )

        conn.execute(
            """
            INSERT INTO eco_entity_window_snapshot (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                snapshot_status, timing_state, trend_state, summary_state, classification_state,
                freshness_status, quality_status, asof_observed_at, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                "OK", "BUY_ZONE", "UP", "STRONG", "BUY_TRIGGER",
                "FRESH", "OK", None, None,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_window_snapshot (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id, snapshot_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "OK"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_window_snapshot (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id, snapshot_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("snap-bad-1", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "BAD"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_window_snapshot (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id, snapshot_status, freshness_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("snap-bad-2", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "OK", "BAD"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_window_snapshot (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id, snapshot_status, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("snap-bad-3", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "OK", "BAD"),
            )

        conn.execute(
            """
            INSERT INTO eco_entity_metric_value (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                "return_5d", 12.5, None, "pct", "OK", None,
            ),
        )
        conn.execute(
            """
            INSERT INTO eco_entity_metric_value (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                "timing_label", None, "BUY_ZONE", None, "OK", None,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_metric_value (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    metric_name, value_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "return_5d", "OK"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_metric_value (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    metric_name, value_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("metric-bad", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id, "other", "BAD"),
            )

        conn.execute(
            """
            INSERT INTO eco_entity_coverage (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
                coverage_status, source_row_count, missing_component_count, coverage_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                1, 1, 1, 1, 1, 1,
                "OK", 5, 0, None,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_coverage (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
                    coverage_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "cov-bad-1", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                    2, 1, 1, 1, 1, 1, "OK",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_coverage (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
                    coverage_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "cov-bad-2", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                    1, 1, 1, 1, 1, 1, "BAD",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_coverage (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
                    coverage_status, source_row_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "cov-bad-3", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                    1, 1, 1, 1, 1, 1, "OK", -1,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_entity_coverage (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                    in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal, has_window_context,
                    coverage_status, missing_component_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "cov-bad-4", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", ticker_entity_id,
                    1, 1, 1, 1, 1, 1, "OK", -1,
                ),
            )

        conn.execute(
            """
            INSERT INTO eco_quality_summary (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
                scope_entity_id, quality_status, expected_count, actual_count, missing_count,
                incomplete_count, stale_count, warning_count, error_count, summary_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", "RUN",
                ecosystem_entity_id, "OK", 10, 10, 0, 0, 0, 0, 0, None,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_quality_summary (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
                    scope_entity_id, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", "RUN",
                    ecosystem_entity_id, "OK",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_quality_summary (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
                    scope_entity_id, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "quality-bad-1", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", "BAD",
                    ecosystem_entity_id, "OK",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_quality_summary (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
                    scope_entity_id, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "quality-bad-2", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", "RUN",
                    ecosystem_entity_id, "BAD",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO eco_quality_summary (
                    run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, quality_scope,
                    scope_entity_id, quality_status, expected_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "quality-bad-3", ecosystem_id, "2026-06-01", taxonomy_version_id, "daily", "RUN",
                    ecosystem_entity_id, "OK", -1,
                ),
            )
    finally:
        conn.close()


def test_expected_core_fact_indexes_exist(tmp_path) -> None:
    db_path = tmp_path / "canonical_v3_core_fact_indexes.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(str(db_path))
    try:
        assert "idx_eco_report_run_ecosystem_signal_date" in _index_names(conn, "eco_report_run")
        assert "idx_eco_report_run_taxonomy_signal_date" in _index_names(conn, "eco_report_run")
        assert "idx_eco_report_run_status_signal_date" in _index_names(conn, "eco_report_run")
        assert "idx_eco_entity_window_snapshot_date_taxonomy_window" in _index_names(conn, "eco_entity_window_snapshot")
        assert "idx_eco_entity_window_snapshot_entity_date" in _index_names(conn, "eco_entity_window_snapshot")
        assert "idx_eco_entity_window_snapshot_ecosystem_window_status" in _index_names(conn, "eco_entity_window_snapshot")
        assert "idx_eco_entity_metric_value_date_taxonomy_window_metric" in _index_names(conn, "eco_entity_metric_value")
        assert "idx_eco_entity_metric_value_entity_metric_date" in _index_names(conn, "eco_entity_metric_value")
        assert "idx_eco_entity_metric_value_ecosystem_metric" in _index_names(conn, "eco_entity_metric_value")
        assert "idx_eco_entity_coverage_date_taxonomy_window_status" in _index_names(conn, "eco_entity_coverage")
        assert "idx_eco_entity_coverage_entity_date" in _index_names(conn, "eco_entity_coverage")
        assert "idx_eco_entity_coverage_ecosystem_status" in _index_names(conn, "eco_entity_coverage")
        assert "idx_eco_quality_summary_date_taxonomy_window_status" in _index_names(conn, "eco_quality_summary")
        assert "idx_eco_quality_summary_ecosystem_scope_status" in _index_names(conn, "eco_quality_summary")
        assert "idx_eco_quality_summary_scope_entity_date" in _index_names(conn, "eco_quality_summary")
    finally:
        conn.close()
