import contextlib
import io
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import inspect_canonical_v3 as cli
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


def _create_empty_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.close()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_cli_fails_clearly_if_db_is_missing() -> None:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr), pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2
    assert "--db" in stderr.getvalue()


def test_cli_inspects_empty_db_without_creating_tables(tmp_path) -> None:
    db_path = tmp_path / "empty.db"
    _create_empty_db(db_path)

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = cli.main(["--db", str(db_path), "--format", "text"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "CANONICAL V3 INSPECT" in output
    assert "TABLES" in output
    assert "eco_ecosystem | NO" in output
    assert "REPORT WINDOWS" in output
    assert "eco_report_window missing" in output
    assert "TAXONOMIES" in output
    assert "eco_ecosystem or eco_taxonomy_version missing" in output
    assert "WATCHLISTS" in output
    assert "eco_ecosystem or eco_watchlist missing" in output

    conn = _connect(db_path)
    try:
        tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()
        assert tables == []
    finally:
        conn.close()


def test_cli_inspects_migrated_db_and_shows_windows_ecosystem_taxonomy_watchlist_counts(tmp_path) -> None:
    db_path = tmp_path / "v3.db"
    apply_report_canonical_v3_migration(str(db_path))

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO eco_ecosystem (
                ecosystem_code, ecosystem_name, description, status
            ) VALUES (?, ?, ?, ?)
            """,
            ("DATACENTER", "Datacenter", None, "ACTIVE"),
        )
        ecosystem_id = int(
            conn.execute(
                "SELECT ecosystem_id FROM eco_ecosystem WHERE ecosystem_code = ?",
                ("DATACENTER",),
            ).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO eco_taxonomy_version (
                ecosystem_id, version_code, version_label, source_type, source_reference,
                effective_from, effective_to, is_active, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ecosystem_id,
                "DC_TAXONOMY_FULL_V1",
                "Datacenter taxonomy",
                "CSV",
                "/tmp/taxonomy.csv",
                None,
                None,
                1,
                "ACTIVE",
            ),
        )
        conn.execute(
            """
            INSERT INTO eco_watchlist (
                ecosystem_id, watchlist_code, watchlist_name, description, source_type, source_reference, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ecosystem_id,
                "DATACENTER_DEFAULT",
                "Datacenter default watchlist",
                None,
                "TXT",
                "/tmp/watchlist.txt",
                "ACTIVE",
            ),
        )
        watchlist_id = int(
            conn.execute(
                "SELECT watchlist_id FROM eco_watchlist WHERE watchlist_code = ?",
                ("DATACENTER_DEFAULT",),
            ).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, exchange, market, currency, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ecosystem_id, "TICKER", "NVDA", "NVDA", "NVDA", None, None, None, "ACTIVE"),
        )
        entity_id = int(
            conn.execute(
                "SELECT entity_id FROM eco_entity WHERE entity_code = ?",
                ("NVDA",),
            ).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO eco_watchlist_member (
                watchlist_id, entity_id, member_role, member_status, effective_from, effective_to, sort_order, removed_at_utc, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (watchlist_id, entity_id, None, "ACTIVE", None, None, None, None, None),
        )
        conn.commit()
    finally:
        conn.close()

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = cli.main(["--db", str(db_path), "--format", "text", "--show-all"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "eco_entity_event | YES | 0" in output
    assert "REPORT WINDOWS" in output
    assert "daily | Daily | 1 | 1 | 1" in output
    assert "rolling30 | Rolling 30 | 30 | 1 | 4" in output
    assert "ECOSYSTEMS" in output
    assert "DATACENTER | Datacenter | ACTIVE" in output
    assert "TAXONOMIES" in output
    assert "DATACENTER | DC_TAXONOMY_FULL_V1 | Datacenter taxonomy | ACTIVE | 1 | CSV | /tmp/taxonomy.csv" in output
    assert "WATCHLISTS" in output
    assert "DATACENTER | DATACENTER_DEFAULT | Datacenter default watchlist | ACTIVE | TXT | /tmp/watchlist.txt | 1" in output
    assert "ROW COUNTS" in output
    assert "eco_watchlist_member | 1" in output
