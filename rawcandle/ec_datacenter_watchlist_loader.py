from __future__ import annotations

import hashlib
import json
import sqlite3
import string
from pathlib import Path


REQUIRED_EC_TABLES = (
    "ec_ecosystem",
    "ec_entity",
    "ec_watchlist",
    "ec_watchlist_member",
)
RECONCILIATION_AUDIT_TABLE = "ec_watchlist_reconciliation_audit"


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


def _require_reconciliation_audit_table(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (RECONCILIATION_AUDIT_TABLE,),
    ).fetchone()
    if row is None:
        raise ValueError(
            "Missing required ec_watchlist_reconciliation_audit table; "
            "apply migration 025 before automatic watchlist reconciliation"
        )


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


def _parse_watchlist_tickers_strict(watchlist_path: str | Path) -> tuple[list[str], int, str]:
    path = Path(watchlist_path)
    raw_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    unique_tickers: list[str] = []
    seen: set[str] = set()
    duplicate_tickers: list[str] = []
    invalid_tickers: list[str] = []
    allowed = set(string.ascii_uppercase + string.digits + ".-")

    for raw_line in raw_bytes.decode("utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        ticker = value.upper()
        if not ticker or any(char not in allowed for char in ticker):
            invalid_tickers.append(ticker or "<blank>")
            continue
        if ticker in seen:
            duplicate_tickers.append(ticker)
            continue
        seen.add(ticker)
        unique_tickers.append(ticker)

    if invalid_tickers:
        raise ValueError(f"Invalid watchlist ticker syntax: {sorted(set(invalid_tickers))}")
    if duplicate_tickers:
        raise ValueError(f"Duplicate watchlist tickers are not allowed: {sorted(set(duplicate_tickers))}")
    if not unique_tickers:
        raise ValueError("Watchlist source did not contain any valid tickers")

    return unique_tickers, len(unique_tickers), source_sha256


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


def _create_watchlist_only_ticker_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    ticker: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ec_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            entity_role_code,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, "TICKER", ticker, ticker, ticker, "TICKER", "ACTIVE"),
    )
    return int(cursor.lastrowid)


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


def _fetch_watchlist_id(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    watchlist_code: str,
) -> int | None:
    return _fetch_existing_id(
        conn,
        """
        SELECT watchlist_id
        FROM ec_watchlist
        WHERE ecosystem_id = ?
          AND watchlist_code = ?
          AND status = 'ACTIVE'
        """,
        (ecosystem_id, watchlist_code),
    )


def _ensure_watchlist(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    watchlist_code: str,
    watchlist_name: str,
    source_reference: str,
) -> int:
    watchlist_id = _fetch_watchlist_id(conn, ecosystem_id=ecosystem_id, watchlist_code=watchlist_code)
    if watchlist_id is not None:
        conn.execute(
            """
            UPDATE ec_watchlist
            SET source_type = 'TXT',
                source_reference = ?,
                updated_at_utc = CURRENT_TIMESTAMP
            WHERE watchlist_id = ?
              AND (
                COALESCE(source_type, '') <> 'TXT'
                OR COALESCE(source_reference, '') <> ?
              )
            """,
            (source_reference, watchlist_id, source_reference),
        )
        return watchlist_id
    return _insert_watchlist(
        conn,
        ecosystem_id=ecosystem_id,
        watchlist_code=watchlist_code,
        watchlist_name=watchlist_name,
        source_reference=source_reference,
    )


def _collect_loaded_watchlist_members(
    conn: sqlite3.Connection,
    *,
    watchlist_id: int,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT UPPER(e.entity_code) AS ticker, wm.entity_id
        FROM ec_watchlist_member wm
        JOIN ec_entity e ON e.entity_id = wm.entity_id
        WHERE wm.watchlist_id = ?
          AND wm.status = 'ACTIVE'
          AND e.entity_type = 'TICKER'
          AND e.status = 'ACTIVE'
        ORDER BY ticker
        """,
        (watchlist_id,),
    ).fetchall()
    members: dict[str, int] = {}
    duplicates: list[str] = []
    for row in rows:
        ticker = str(row[0])
        if ticker in members:
            duplicates.append(ticker)
        members[ticker] = int(row[1])
    if duplicates:
        raise ValueError(f"Duplicate active watchlist membership rows: {sorted(set(duplicates))}")
    return members


def _resolve_or_create_ticker_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    ticker: str,
    create_missing: bool,
    created_tickers: list[str],
) -> int:
    rows = conn.execute(
        """
        SELECT entity_id
        FROM ec_entity
        WHERE ecosystem_id = ?
          AND entity_type = 'TICKER'
          AND entity_code = ?
          AND status = 'ACTIVE'
        ORDER BY entity_id
        """,
        (ecosystem_id, ticker),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError(f"Ambiguous active EC ticker entity for watchlist ticker {ticker}")
    if len(rows) == 1:
        return int(rows[0][0])
    if not create_missing:
        raise ValueError(f"Watchlist ticker {ticker} is missing from ec_entity")
    entity_id = _create_watchlist_only_ticker_entity(conn, ecosystem_id=ecosystem_id, ticker=ticker)
    created_tickers.append(ticker)
    return entity_id


def _base_reconciliation_summary(
    *,
    status: str,
    ecosystem_code: str,
    taxonomy_version_code: str | None,
    watchlist_code: str,
    source_reference: str,
    source_sha256: str | None = None,
    source_tickers: list[str] | None = None,
    loaded_tickers: list[str] | None = None,
    added_tickers: list[str] | None = None,
    removed_tickers: list[str] | None = None,
    created_watchlist_only_tickers: list[str] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    source_tickers = source_tickers or []
    loaded_tickers = loaded_tickers or []
    added_tickers = sorted(added_tickers or [])
    removed_tickers = sorted(removed_tickers or [])
    created_watchlist_only_tickers = sorted(created_watchlist_only_tickers or [])
    return {
        "watchlist_reconciliation_attempted": True,
        "watchlist_reconciliation_status": status,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "watchlist_code": watchlist_code,
        "watchlist_source_reference": source_reference,
        "watchlist_source_sha256": source_sha256,
        "watchlist_source_member_count": len(source_tickers),
        "watchlist_previous_member_count": len(loaded_tickers),
        "watchlist_current_member_count": len(source_tickers) if status in {"APPLIED", "NO_CHANGE"} else len(loaded_tickers),
        "watchlist_added_count": len(added_tickers),
        "watchlist_removed_count": len(removed_tickers),
        "watchlist_added_tickers": added_tickers,
        "watchlist_removed_tickers": removed_tickers,
        "watchlist_created_watchlist_only_ticker_count": len(created_watchlist_only_tickers),
        "watchlist_created_watchlist_only_tickers": created_watchlist_only_tickers,
        "watchlist_reconciliation_error": error,
    }


def plan_datacenter_watchlist_reconciliation(
    *,
    db_path: str | Path,
    watchlist_path: str | Path,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str | None = "DC_TAXONOMY_FULL_V1",
    watchlist_code: str = "DATACENTER_WATCHLIST",
    watchlist_name: str = "Datacenter Watchlist",
) -> dict[str, object]:
    source_reference = str(watchlist_path)
    try:
        source_tickers, _, source_sha256 = _parse_watchlist_tickers_strict(watchlist_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            _require_ec_sidecar_tables(conn)
            ecosystem_id = _require_ecosystem(conn, ecosystem_code)
            watchlist_id = _fetch_watchlist_id(conn, ecosystem_id=ecosystem_id, watchlist_code=watchlist_code)
            loaded_members = _collect_loaded_watchlist_members(conn, watchlist_id=watchlist_id) if watchlist_id is not None else {}
            loaded_tickers = sorted(loaded_members)
        finally:
            conn.close()
        added = sorted(set(source_tickers) - set(loaded_tickers))
        removed = sorted(set(loaded_tickers) - set(source_tickers))
        return _base_reconciliation_summary(
            status="NO_CHANGE" if not added and not removed else "PLAN_READY",
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            watchlist_code=watchlist_code,
            source_reference=source_reference,
            source_sha256=source_sha256,
            source_tickers=source_tickers,
            loaded_tickers=loaded_tickers,
            added_tickers=added,
            removed_tickers=removed,
        ) | {
            "watchlist_plan_apply_safe": True,
            "watchlist_source_tickers": source_tickers,
            "watchlist_loaded_tickers": loaded_tickers,
        }
    except Exception as exc:
        return _base_reconciliation_summary(
            status="FAILED",
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            watchlist_code=watchlist_code,
            source_reference=source_reference,
            error=str(exc),
        ) | {"watchlist_plan_apply_safe": False}


def apply_datacenter_watchlist_reconciliation(
    *,
    db_path: str | Path,
    watchlist_path: str | Path,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str | None = "DC_TAXONOMY_FULL_V1",
    watchlist_code: str = "DATACENTER_WATCHLIST",
    watchlist_name: str = "Datacenter Watchlist",
    invocation_source: str = "UNKNOWN",
    create_missing_entities: bool = True,
) -> dict[str, object]:
    source_reference = str(watchlist_path)
    try:
        source_tickers, _, source_sha256 = _parse_watchlist_tickers_strict(watchlist_path)
    except Exception as exc:
        return _base_reconciliation_summary(
            status="FAILED",
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            watchlist_code=watchlist_code,
            source_reference=source_reference,
            error=str(exc),
        )

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _require_ec_sidecar_tables(conn)
        _require_reconciliation_audit_table(conn)
        with conn:
            ecosystem_id = _require_ecosystem(conn, ecosystem_code)
            watchlist_id = _ensure_watchlist(
                conn,
                ecosystem_id=ecosystem_id,
                watchlist_code=watchlist_code,
                watchlist_name=watchlist_name,
                source_reference=source_reference,
            )
            loaded_members = _collect_loaded_watchlist_members(conn, watchlist_id=watchlist_id)
            loaded_tickers = sorted(loaded_members)
            added = sorted(set(source_tickers) - set(loaded_tickers))
            removed = sorted(set(loaded_tickers) - set(source_tickers))
            if not added and not removed:
                return _base_reconciliation_summary(
                    status="NO_CHANGE",
                    ecosystem_code=ecosystem_code,
                    taxonomy_version_code=taxonomy_version_code,
                    watchlist_code=watchlist_code,
                    source_reference=source_reference,
                    source_sha256=source_sha256,
                    source_tickers=source_tickers,
                    loaded_tickers=loaded_tickers,
                )

            created_watchlist_only_tickers: list[str] = []
            added_entity_ids = {
                ticker: _resolve_or_create_ticker_entity(
                    conn,
                    ecosystem_id=ecosystem_id,
                    ticker=ticker,
                    create_missing=create_missing_entities,
                    created_tickers=created_watchlist_only_tickers,
                )
                for ticker in added
            }

            for ticker in removed:
                conn.execute(
                    """
                    DELETE FROM ec_watchlist_member
                    WHERE watchlist_id = ?
                      AND entity_id = ?
                      AND status = 'ACTIVE'
                    """,
                    (watchlist_id, loaded_members[ticker]),
                )
            for ticker in added:
                _insert_watchlist_member(conn, watchlist_id=watchlist_id, entity_id=added_entity_ids[ticker])

            post_members = _collect_loaded_watchlist_members(conn, watchlist_id=watchlist_id)
            post_tickers = sorted(post_members)
            if post_tickers != sorted(source_tickers):
                raise RuntimeError(
                    "post-write watchlist verification failed: "
                    f"expected={sorted(source_tickers)} actual={post_tickers}"
                )

            conn.execute(
                """
                INSERT INTO ec_watchlist_reconciliation_audit (
                    ecosystem_id,
                    taxonomy_version_code,
                    watchlist_id,
                    watchlist_code,
                    source_type,
                    source_reference,
                    source_sha256,
                    source_member_count,
                    previous_member_count,
                    new_member_count,
                    added_count,
                    removed_count,
                    added_tickers_json,
                    removed_tickers_json,
                    invocation_source,
                    status,
                    error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ecosystem_id,
                    taxonomy_version_code,
                    watchlist_id,
                    watchlist_code,
                    "TXT",
                    source_reference,
                    source_sha256,
                    len(source_tickers),
                    len(loaded_tickers),
                    len(post_tickers),
                    len(added),
                    len(removed),
                    json.dumps(added, sort_keys=True),
                    json.dumps(removed, sort_keys=True),
                    invocation_source,
                    "APPLIED",
                    None,
                ),
            )

            return _base_reconciliation_summary(
                status="APPLIED",
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                watchlist_code=watchlist_code,
                source_reference=source_reference,
                source_sha256=source_sha256,
                source_tickers=source_tickers,
                loaded_tickers=loaded_tickers,
                added_tickers=added,
                removed_tickers=removed,
                created_watchlist_only_tickers=created_watchlist_only_tickers,
            )
    except Exception as exc:
        return _base_reconciliation_summary(
            status="FAILED",
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            watchlist_code=watchlist_code,
            source_reference=source_reference,
            source_sha256=source_sha256,
            source_tickers=source_tickers,
            error=str(exc),
        )
    finally:
        conn.close()


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
            existing_entity_member_count = 0
            created_watchlist_only_entity_count = 0
            watchlist_only_tickers: list[str] = []
            missing_tickers: list[str] = []
            for ticker in unique_tickers:
                entity_id = _find_ticker_entity_id(conn, ecosystem_id=ecosystem_id, ticker=ticker)
                if entity_id is None:
                    entity_id = _create_watchlist_only_ticker_entity(
                        conn,
                        ecosystem_id=ecosystem_id,
                        ticker=ticker,
                    )
                    created_watchlist_only_entity_count += 1
                    watchlist_only_tickers.append(ticker)
                    warnings.append(
                        "Created watchlist-only ticker entity without taxonomy membership "
                        f"for watchlist ticker {ticker}"
                    )
                else:
                    existing_entity_member_count += 1
                loaded_member_count += _insert_watchlist_member(
                    conn,
                    watchlist_id=watchlist_id,
                    entity_id=entity_id,
                )

        if loaded_member_count == 0:
            status = "NO_VALID_MEMBERS"
        elif watchlist_only_tickers:
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
            "existing_entity_member_count": existing_entity_member_count,
            "created_watchlist_only_entity_count": created_watchlist_only_entity_count,
            "watchlist_only_tickers": watchlist_only_tickers,
            "missing_ticker_count": len(missing_tickers),
            "missing_tickers": missing_tickers,
            "duplicate_ticker_count": duplicate_ticker_count,
            "warnings": warnings,
        }
    finally:
        conn.close()
