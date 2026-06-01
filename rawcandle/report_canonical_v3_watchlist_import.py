from __future__ import annotations

import sqlite3
from pathlib import Path

from .report_canonical_v3_migration import apply_report_canonical_v3_migration


def _fetch_id(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return int(row[0])


def _ensure_ecosystem(conn: sqlite3.Connection) -> tuple[int, int]:
    existing_id = _fetch_id(
        conn,
        "SELECT ecosystem_id FROM eco_ecosystem WHERE ecosystem_code = ?",
        ("DATACENTER",),
    )
    if existing_id is not None:
        return existing_id, 1
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
    return int(cursor.lastrowid), 1


def _parse_watchlist_tickers(watchlist_source_path: str) -> tuple[list[str], int]:
    tickers: list[str] = []
    seen: set[str] = set()
    source_tickers_read = 0
    for raw_line in Path(watchlist_source_path).read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        source_tickers_read += 1
        ticker = value.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers, source_tickers_read


def _ensure_watchlist(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    watchlist_code: str,
    watchlist_name: str,
    source_reference: str,
) -> tuple[int, int]:
    existing_id = _fetch_id(
        conn,
        """
        SELECT watchlist_id
        FROM eco_watchlist
        WHERE ecosystem_id = ? AND watchlist_code = ?
        """,
        (ecosystem_id, watchlist_code),
    )
    if existing_id is not None:
        return existing_id, 1
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
        (
            ecosystem_id,
            watchlist_code,
            watchlist_name,
            None,
            "TXT",
            source_reference,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid), 1


def _find_ticker_entity_id(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    ticker: str,
) -> int | None:
    return _fetch_id(
        conn,
        """
        SELECT entity_id
        FROM eco_entity
        WHERE ecosystem_id = ?
          AND entity_type = ?
          AND entity_code = ?
        """,
        (ecosystem_id, "TICKER", ticker),
    )


def _create_missing_ticker_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    ticker: str,
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
            "TICKER",
            ticker,
            ticker,
            ticker,
            None,
            None,
            None,
            "WATCH_ONLY",
        ),
    )
    return int(cursor.lastrowid)


def _ensure_watchlist_member(
    conn: sqlite3.Connection,
    *,
    watchlist_id: int,
    entity_id: int,
) -> int:
    existing_id = _fetch_id(
        conn,
        """
        SELECT watchlist_member_id
        FROM eco_watchlist_member
        WHERE watchlist_id = ? AND entity_id = ?
        """,
        (watchlist_id, entity_id),
    )
    if existing_id is not None:
        return 0
    conn.execute(
        """
        INSERT INTO eco_watchlist_member (
            watchlist_id,
            entity_id,
            member_role,
            member_status,
            effective_from,
            effective_to,
            sort_order,
            removed_at_utc,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (watchlist_id, entity_id, None, "ACTIVE", None, None, None, None, None),
    )
    return 1


def import_datacenter_watchlist_to_v3(
    db_path: str,
    watchlist_source_path: str,
    watchlist_code: str = "DATACENTER_DEFAULT",
    watchlist_name: str = "Datacenter default watchlist",
    create_missing_ticker_entities: bool = False,
    dry_run: bool = False,
) -> dict:
    unique_tickers, source_tickers_read = _parse_watchlist_tickers(watchlist_source_path)

    if not dry_run:
        apply_report_canonical_v3_migration(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    warnings: list[str] = []
    summary = {
        "ecosystems_inserted_or_existing": 0,
        "watchlists_inserted_or_existing": 0,
        "source_tickers_read": source_tickers_read,
        "unique_source_tickers": len(unique_tickers),
        "ticker_entities_found": 0,
        "ticker_entities_created": 0,
        "members_inserted_or_existing": 0,
        "missing_ticker_entities": 0,
        "warnings": warnings,
    }
    try:
        ecosystem_id, ecosystem_count = _ensure_ecosystem(conn)
        summary["ecosystems_inserted_or_existing"] = ecosystem_count

        watchlist_id, watchlist_count = _ensure_watchlist(
            conn,
            ecosystem_id=ecosystem_id,
            watchlist_code=watchlist_code,
            watchlist_name=watchlist_name,
            source_reference=watchlist_source_path,
        )
        summary["watchlists_inserted_or_existing"] = watchlist_count

        for ticker in unique_tickers:
            entity_id = _find_ticker_entity_id(conn, ecosystem_id=ecosystem_id, ticker=ticker)
            if entity_id is None:
                if not create_missing_ticker_entities:
                    summary["missing_ticker_entities"] += 1
                    warnings.append(
                        f"Ticker entity not found for watchlist import: {ticker}"
                    )
                    continue
                entity_id = _create_missing_ticker_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    ticker=ticker,
                )
                summary["ticker_entities_created"] += 1
            else:
                summary["ticker_entities_found"] += 1

            summary["members_inserted_or_existing"] += _ensure_watchlist_member(
                conn,
                watchlist_id=watchlist_id,
                entity_id=entity_id,
            ) or 1

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return summary
    finally:
        conn.close()
