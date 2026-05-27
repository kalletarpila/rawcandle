import sqlite3

from analysis.database_manager import DatabaseManager
from rawcandle.datacenter_dashboard_enrichment_migration import (
    HIGH_EXIT_RISK_MIGRATION_SQL_PATH,
    MIGRATION_SQL_PATH,
    apply_datacenter_dashboard_enrichment_migration,
)


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


def _primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in sorted(rows, key=lambda row: int(row[5])) if int(row[5]) > 0]


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_datacenter_dashboard_enrichment_migration(conn)
    return conn


def test_migration_file_exists():
    assert MIGRATION_SQL_PATH.is_file()
    assert HIGH_EXIT_RISK_MIGRATION_SQL_PATH.is_file()


def test_database_manager_initializes_dashboard_enrichment_tables(tmp_path):
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    conn = manager.get_connection()

    assert _table_exists(conn, "dc_dashboard_ticker_enrichment_daily")
    assert _table_exists(conn, "dc_dashboard_group_enrichment_daily")
    assert _table_exists(conn, "dc_dashboard_action_summary_daily")
    assert _table_exists(conn, "dc_dashboard_decision_trace_daily")
    assert _table_exists(conn, "dc_dashboard_enrichment_run_daily")

    manager.close()


def test_migration_creates_expected_primary_keys_and_columns():
    conn = _connect()

    assert _primary_key_columns(conn, "dc_dashboard_ticker_enrichment_daily") == [
        "signal_date",
        "taxonomy_version",
        "ticker",
    ]
    assert _primary_key_columns(conn, "dc_dashboard_group_enrichment_daily") == [
        "signal_date",
        "taxonomy_version",
        "market_level",
        "taxonomy_key",
    ]
    assert _primary_key_columns(conn, "dc_dashboard_action_summary_daily") == [
        "signal_date",
        "taxonomy_version",
        "action",
    ]
    assert _primary_key_columns(conn, "dc_dashboard_decision_trace_daily") == [
        "signal_date",
        "taxonomy_version",
        "ticker",
        "trace_index",
    ]
    assert _primary_key_columns(conn, "dc_dashboard_enrichment_run_daily") == ["run_id"]

    assert {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "action",
        "high_exit_risk_days_count",
        "pullback_validity",
        "entry_readiness",
        "candidate_priority",
        "is_watchlist",
        "data_quality_status",
        "calc_version",
        "run_id",
        "created_at_utc",
    }.issubset(_table_columns(conn, "dc_dashboard_ticker_enrichment_daily"))

    assert {
        "signal_date",
        "taxonomy_version",
        "market_level",
        "taxonomy_key",
        "current_status",
        "window_status_30d",
        "overheat_risk",
        "source_horizons",
        "data_quality_status",
    }.issubset(_table_columns(conn, "dc_dashboard_group_enrichment_daily"))

    assert {"action", "count"}.issubset(_table_columns(conn, "dc_dashboard_action_summary_daily"))
    assert {
        "ticker",
        "trace_index",
        "matched_rule",
        "matched_token",
        "matched_value",
        "horizon",
        "field",
    }.issubset(_table_columns(conn, "dc_dashboard_decision_trace_daily"))
    assert {"status", "readiness", "warnings"}.issubset(
        _table_columns(conn, "dc_dashboard_enrichment_run_daily")
    )


def test_migration_creates_representative_indexes():
    conn = _connect()

    assert {
        "idx_dc_dashboard_ticker_enrichment_ticker_date",
        "idx_dc_dashboard_ticker_enrichment_date_action",
        "idx_dc_dashboard_ticker_enrichment_date_watchlist",
        "idx_dc_dashboard_ticker_enrichment_date_taxonomy",
    }.issubset(_index_names(conn, "dc_dashboard_ticker_enrichment_daily"))

    assert {
        "idx_dc_dashboard_group_enrichment_date_level",
        "idx_dc_dashboard_group_enrichment_date_layer",
        "idx_dc_dashboard_group_enrichment_date_taxonomy_path",
    }.issubset(_index_names(conn, "dc_dashboard_group_enrichment_daily"))

    assert {"idx_dc_dashboard_action_summary_date"}.issubset(
        _index_names(conn, "dc_dashboard_action_summary_daily")
    )

    assert {
        "idx_dc_dashboard_decision_trace_date_ticker",
        "idx_dc_dashboard_decision_trace_date_action",
    }.issubset(_index_names(conn, "dc_dashboard_decision_trace_daily"))

    assert {
        "idx_dc_dashboard_enrichment_run_date",
        "idx_dc_dashboard_enrichment_run_status",
    }.issubset(_index_names(conn, "dc_dashboard_enrichment_run_daily"))


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    apply_datacenter_dashboard_enrichment_migration(conn)
    apply_datacenter_dashboard_enrichment_migration(conn)

    assert _table_exists(conn, "dc_dashboard_ticker_enrichment_daily")
    assert _table_exists(conn, "dc_dashboard_group_enrichment_daily")
    assert _table_exists(conn, "dc_dashboard_action_summary_daily")
    assert _table_exists(conn, "dc_dashboard_decision_trace_daily")
    assert _table_exists(conn, "dc_dashboard_enrichment_run_daily")
    assert "high_exit_risk_days_count" in _table_columns(
        conn, "dc_dashboard_ticker_enrichment_daily"
    )


def test_old_snapshot_table_names_are_not_created():
    conn = _connect()

    assert not _table_exists(conn, "dc_dashboard_runs")
    assert not _table_exists(conn, "dc_dashboard_source_reports")
    assert not _table_exists(conn, "dc_dashboard_market_map")
    assert not _table_exists(conn, "dc_dashboard_watchlist_status")
    assert not _table_exists(conn, "dc_dashboard_ticker_status")
    assert not _table_exists(conn, "dc_dashboard_decision_trace")
