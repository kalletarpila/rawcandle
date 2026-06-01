import sqlite3

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_watchlist_import import (
    _parse_watchlist_tickers,
    import_datacenter_watchlist_to_v3,
)


def _write_watchlist_fixture(path) -> None:
    path.write_text(
        "\n".join(
            [
                "# comment",
                "",
                "nvda",
                "msft",
                "brk.b",
                "NVDA",
                "  amd  ",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ticker_entity(conn: sqlite3.Connection, ticker: str, status: str = "ACTIVE") -> int:
    ecosystem_id = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code, ecosystem_name, description, status
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(ecosystem_code) DO NOTHING
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    _ = ecosystem_id
    ecosystem_row = conn.execute(
        "SELECT ecosystem_id FROM eco_ecosystem WHERE ecosystem_code = ?",
        ("DATACENTER",),
    ).fetchone()
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
        (int(ecosystem_row[0]), "TICKER", ticker, ticker, ticker, None, None, None, status),
    )
    return int(cursor.lastrowid)


def test_import_watchlist_persists_watchlist_and_members_for_existing_tickers(tmp_path) -> None:
    db_path = tmp_path / "watchlist.db"
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist_fixture(watchlist_path)

    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        _insert_ticker_entity(conn, "NVDA")
        _insert_ticker_entity(conn, "MSFT")
        conn.commit()
    finally:
        conn.close()

    summary = import_datacenter_watchlist_to_v3(
        db_path=str(db_path),
        watchlist_source_path=str(watchlist_path),
    )

    conn = _connect(str(db_path))
    try:
        watchlist_row = conn.execute(
            """
            SELECT w.watchlist_code, w.watchlist_name, w.status, w.source_type, w.source_reference
            FROM eco_watchlist w
            """
        ).fetchone()
        assert watchlist_row == (
            "DATACENTER_DEFAULT",
            "Datacenter default watchlist",
            "ACTIVE",
            "TXT",
            str(watchlist_path),
        )

        ecosystem_row = conn.execute(
            "SELECT ecosystem_code, ecosystem_name FROM eco_ecosystem"
        ).fetchone()
        assert ecosystem_row == ("DATACENTER", "Datacenter")

        member_tickers = conn.execute(
            """
            SELECT e.entity_code
            FROM eco_watchlist_member wm
            JOIN eco_entity e ON e.entity_id = wm.entity_id
            ORDER BY e.entity_code
            """
        ).fetchall()
        assert member_tickers == [("MSFT",), ("NVDA",)]

        assert summary == {
            "ecosystems_inserted_or_existing": 1,
            "watchlists_inserted_or_existing": 1,
            "source_tickers_read": 5,
            "unique_source_tickers": 4,
            "ticker_entities_found": 2,
            "ticker_entities_created": 0,
            "members_inserted_or_existing": 2,
            "missing_ticker_entities": 2,
            "warnings": [
                "Ticker entity not found for watchlist import: BRK.B",
                "Ticker entity not found for watchlist import: AMD",
            ],
        }
    finally:
        conn.close()


def test_import_watchlist_is_idempotent_and_membership_is_independent_from_taxonomy_relations(tmp_path) -> None:
    db_path = tmp_path / "watchlist_idempotent.db"
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist_fixture(watchlist_path)

    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    try:
        _insert_ticker_entity(conn, "NVDA")
        _insert_ticker_entity(conn, "MSFT")
        conn.commit()
    finally:
        conn.close()

    first_summary = import_datacenter_watchlist_to_v3(
        db_path=str(db_path),
        watchlist_source_path=str(watchlist_path),
    )
    second_summary = import_datacenter_watchlist_to_v3(
        db_path=str(db_path),
        watchlist_source_path=str(watchlist_path),
    )

    conn = _connect(str(db_path))
    try:
        member_count = conn.execute(
            "SELECT COUNT(*) FROM eco_watchlist_member"
        ).fetchone()[0]
        relation_count = conn.execute(
            "SELECT COUNT(*) FROM eco_taxonomy_entity_relation"
        ).fetchone()[0]
        assert member_count == 2
        assert relation_count == 0
        assert first_summary["members_inserted_or_existing"] == 2
        assert second_summary["members_inserted_or_existing"] == 2
    finally:
        conn.close()


def test_parser_and_missing_ticker_creation_mode(tmp_path) -> None:
    db_path = tmp_path / "watchlist_create_missing.db"
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist_fixture(watchlist_path)

    parsed_tickers, source_tickers_read = _parse_watchlist_tickers(str(watchlist_path))
    assert parsed_tickers == ["NVDA", "MSFT", "BRK.B", "AMD"]
    assert source_tickers_read == 5

    summary = import_datacenter_watchlist_to_v3(
        db_path=str(db_path),
        watchlist_source_path=str(watchlist_path),
        create_missing_ticker_entities=True,
    )

    conn = _connect(str(db_path))
    try:
        created_entities = conn.execute(
            """
            SELECT entity_code, ticker, status
            FROM eco_entity
            ORDER BY entity_code
            """
        ).fetchall()
        assert created_entities == [
            ("AMD", "AMD", "WATCH_ONLY"),
            ("BRK.B", "BRK.B", "WATCH_ONLY"),
            ("MSFT", "MSFT", "WATCH_ONLY"),
            ("NVDA", "NVDA", "WATCH_ONLY"),
        ]
        member_count = conn.execute(
            "SELECT COUNT(*) FROM eco_watchlist_member"
        ).fetchone()[0]
        assert member_count == 4
        assert summary["ticker_entities_found"] == 0
        assert summary["ticker_entities_created"] == 4
        assert summary["missing_ticker_entities"] == 0
        assert summary["warnings"] == []
    finally:
        conn.close()
