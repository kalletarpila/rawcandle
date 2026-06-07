from __future__ import annotations

import sqlite3
from pathlib import Path


REQUIRED_EC_TABLES = (
    "ec_ecosystem",
    "ec_entity",
    "ec_watchlist",
    "ec_watchlist_member",
)


def _fetch_existing_id(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return int(row[0])


def _require_ec_sidecar_tables(conn: sqlite3.Connection) -> None:
    existing = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name GLOB 'ec_*'
            """
        ).fetchall()
    }
    missing = [table_name for table_name in REQUIRED_EC_TABLES if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required ec_ sidecar tables: {missing}")


def _parse_watchlist_tickers(watchlist_path: str | Path) -> tuple[list[str], int, int]:
    unique_tickers: list[str] = []
    seen: set[str] = set()
    source_ticker_count = 0
    duplicate_ticker_count = 0

    for raw_line in Path(watchlist_path).read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        source_ticker_count += 1
        ticker = value.upper()
        if ticker in seen:
            duplicate_ticker_count += 1
            continue
        seen.add(ticker)
        unique_tickers.append(ticker)

    if not unique_tickers:
        raise ValueError("Watchlist source did not contain any valid tickers")

    return unique_tickers, source_ticker_count, duplicate_ticker_count


def _require_ecosystem(conn: sqlite3.Connection, ecosystem_code: str) -> int:
    ecosystem_id = _fetch_existing_id(
        conn,
        """
        SELECT ecosystem_id
        FROM ec_ecosystem
        WHERE ecosystem_code = ?
        """,
        (ecosystem_code,),
    )
    if ecosystem_id is None:
        raise ValueError(f"Required ec_ecosystem row not found for ecosystem_code {ecosystem_code!r}")
    return ecosystem_id


def _ensure_watchlist_absent(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    watchlist_code: str,
) -> None:
    existing_id = _fetch_existing_id(
        conn,
        """
        SELECT watchlist_id
        FROM ec_watchlist
        WHERE ecosystem_id = ? AND watchlist_code = ?
        """,
        (ecosystem_id, watchlist_code),
    )
    if existing_id is not None:
        raise ValueError(
            "Target watchlist already exists for ecosystem "
            f"{ecosystem_id} and watchlist_code {watchlist_code!r}"
        )


def _insert_watchlist(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    watchlist_code: str,
    watchlist_name: str,
    source_reference: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_watchlist (
            ecosystem_id,
            watchlist_code,
            watchlist_name,
            source_type,
            source_reference,
            status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, watchlist_code, watchlist_name, "TXT", source_reference, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _find_ticker_entity_id(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    ticker: str,
) -> int | None:
    return _fetch_existing_id(
        conn,
        """
        SELECT entity_id
        FROM ec_entity
        WHERE ecosystem_id = ?
          AND entity_type = 'TICKER'
          AND entity_code = ?
        """,
        (ecosystem_id, ticker),
    )


def _insert_watchlist_member(
    conn: sqlite3.Connection,
    *,
    watchlist_id: int,
    entity_id: int,
) -> int:
    conn.execute(
        """
        INSERT INTO ec_watchlist_member (
            watchlist_id,
            entity_id,
            member_role,
            status,
            active_to,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (watchlist_id, entity_id, "WATCH", "ACTIVE", None, None),
    )
    return 1


def load_datacenter_watchlist_to_ec_sidecar(
    db_path: str | Path,
    watchlist_path: str | Path,
    ecosystem_code: str = "DATACENTER",
    watchlist_code: str = "DATACENTER_WATCHLIST",
    watchlist_name: str = "Datacenter Watchlist",
    replace_existing: bool = False,
) -> dict[str, object]:
    if replace_existing:
        raise NotImplementedError(
            "replace_existing=True is not implemented for EC-WATCH-01; "
            "use replace_existing=False"
        )

    unique_tickers, source_ticker_count, duplicate_ticker_count = _parse_watchlist_tickers(watchlist_path)
    warnings: list[str] = []

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _require_ec_sidecar_tables(conn)
        with conn:
            ecosystem_id = _require_ecosystem(conn, ecosystem_code)
            _ensure_watchlist_absent(conn, ecosystem_id=ecosystem_id, watchlist_code=watchlist_code)
            watchlist_id = _insert_watchlist(
                conn,
                ecosystem_id=ecosystem_id,
                watchlist_code=watchlist_code,
                watchlist_name=watchlist_name,
                source_reference=str(watchlist_path),
            )

            loaded_member_count = 0
            missing_tickers: list[str] = []
            for ticker in unique_tickers:
                entity_id = _find_ticker_entity_id(conn, ecosystem_id=ecosystem_id, ticker=ticker)
                if entity_id is None:
                    missing_tickers.append(ticker)
                    warnings.append(f"Ticker entity not found for watchlist ticker {ticker}")
                    continue
                loaded_member_count += _insert_watchlist_member(
                    conn,
                    watchlist_id=watchlist_id,
                    entity_id=entity_id,
                )

        if loaded_member_count == 0:
            status = "NO_VALID_MEMBERS"
        elif missing_tickers:
            status = "OK_WITH_WARNINGS"
        else:
            status = "OK"

        return {
            "status": status,
            "ecosystem_code": ecosystem_code,
            "watchlist_code": watchlist_code,
            "watchlist_name": watchlist_name,
            "source_ticker_count": source_ticker_count,
            "unique_ticker_count": len(unique_tickers),
            "loaded_member_count": loaded_member_count,
            "missing_ticker_count": len(missing_tickers),
            "missing_tickers": missing_tickers,
            "duplicate_ticker_count": duplicate_ticker_count,
            "warnings": warnings,
        }
    finally:
        conn.close()
