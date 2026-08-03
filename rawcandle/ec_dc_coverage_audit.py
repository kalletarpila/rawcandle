from __future__ import annotations

import sqlite3
from pathlib import Path


REQUIRED_ANALYSIS_TABLES = (
    "dc_ticker_swing_signal_daily",
    "dc_group_swing_signal_daily",
    "dc_group_synthetic_ohlc_daily",
)

REQUIRED_EC_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_membership",
    "ec_watchlist",
    "ec_watchlist_member",
)


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection, pattern: str | None = None) -> set[str]:
    if pattern is None:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    else:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name GLOB ?
            """,
            (pattern,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _require_tables(conn: sqlite3.Connection, required_tables: tuple[str, ...], label: str) -> None:
    existing = _table_names(conn)
    missing = [table_name for table_name in required_tables if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required {label} tables: {missing}")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _require_columns(conn: sqlite3.Connection, table_name: str, columns: tuple[str, ...], label: str) -> None:
    existing = _table_columns(conn, table_name)
    missing = [column for column in columns if column not in existing]
    if missing:
        raise ValueError(f"Missing required columns for {label} table {table_name}: {missing}")


def _resolve_signal_date(conn: sqlite3.Connection, signal_date: str | None, taxonomy_version_code: str) -> str:
    if signal_date:
        return signal_date
    row = conn.execute(
        """
        SELECT MAX(signal_date)
        FROM dc_ticker_swing_signal_daily
        WHERE taxonomy_version = ?
        """,
        (taxonomy_version_code,),
    ).fetchone()
    if row is None or row[0] is None:
        raise ValueError(
            "Could not resolve latest signal_date from dc_ticker_swing_signal_daily "
            f"for taxonomy_version={taxonomy_version_code!r}"
        )
    return str(row[0])


def _resolve_matching_date(
    conn: sqlite3.Connection,
    table_name: str,
    date_column: str,
    selected_date: str,
    taxonomy_version_code: str,
) -> str | None:
    row = conn.execute(
        f"""
        SELECT MAX({date_column})
        FROM {table_name}
        WHERE {date_column} = ?
          AND taxonomy_version = ?
        """,
        (selected_date, taxonomy_version_code),
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _fetch_ec_context(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT e.ecosystem_id, tv.taxonomy_version_id
        FROM ec_ecosystem e
        JOIN ec_taxonomy_version tv ON tv.ecosystem_id = e.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    if row is None:
        raise ValueError(
            "Required ec sidecar context not found for "
            f"ecosystem_code={ecosystem_code!r}, taxonomy_version_code={taxonomy_version_code!r}"
        )
    return int(row[0]), int(row[1])


def _fetch_ec_ticker_codes(conn: sqlite3.Connection, ecosystem_id: int) -> set[str]:
    rows = conn.execute(
        """
        SELECT entity_code
        FROM ec_entity
        WHERE ecosystem_id = ?
          AND entity_type = 'TICKER'
        """,
        (ecosystem_id,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _fetch_ec_watchlist_members(conn: sqlite3.Connection, ecosystem_id: int) -> tuple[list[str], list[str]]:
    rows = conn.execute(
        """
        SELECT w.source_reference, e.entity_code
        FROM ec_watchlist w
        LEFT JOIN ec_watchlist_member wm ON wm.watchlist_id = w.watchlist_id
        LEFT JOIN ec_entity e ON e.entity_id = wm.entity_id
        WHERE w.ecosystem_id = ?
        ORDER BY w.watchlist_code, e.entity_code
        """,
        (ecosystem_id,),
    ).fetchall()
    member_tickers = sorted({str(row[1]) for row in rows if row[1] is not None})
    source_references = sorted({str(row[0]) for row in rows if row[0]})
    return member_tickers, source_references


def _parse_watchlist_source(path: str | Path) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        ticker = value.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def _fetch_dc_tickers(conn: sqlite3.Connection, selected_date: str, taxonomy_version_code: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT ticker
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
        ORDER BY ticker
        """,
        (selected_date, taxonomy_version_code),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _fetch_taxonomy_tickers(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT child.entity_code
        FROM ec_membership m
        JOIN ec_entity child ON child.entity_id = m.child_entity_id
        WHERE m.taxonomy_version_id = ?
          AND child.entity_type = 'TICKER'
        ORDER BY child.entity_code
        """,
        (taxonomy_version_id,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _entity_match_exists(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    group_name: str,
    alias_type: str | None = None,
) -> bool:
    if entity_type == "ECOSYSTEM" and alias_type is not None:
        row = conn.execute(
            """
            SELECT 1
            FROM ec_entity_alias a
            JOIN ec_entity e ON e.entity_id = a.entity_id
            WHERE a.ecosystem_id = ?
              AND a.alias_type = ?
              AND a.alias_value = ?
              AND e.entity_type = 'ECOSYSTEM'
            LIMIT 1
            """,
            (ecosystem_id, alias_type, group_name),
        ).fetchone()
        return row is not None

    row = conn.execute(
        """
        SELECT 1
        FROM ec_entity
        WHERE ecosystem_id = ?
          AND entity_type = ?
          AND (entity_name = ? OR entity_code = ?)
        LIMIT 1
        """,
        (ecosystem_id, entity_type, group_name, group_name),
    ).fetchone()
    return row is not None


def _audit_group_table(
    analysis_conn: sqlite3.Connection,
    ec_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    table_name: str,
    date_column: str,
    selected_date: str,
    taxonomy_version_code: str,
) -> dict[str, object]:
    rows = analysis_conn.execute(
        f"""
        SELECT DISTINCT group_type, group_name
        FROM {table_name}
        WHERE {date_column} = ?
          AND taxonomy_version = ?
        ORDER BY group_type, group_name
        """,
        (selected_date, taxonomy_version_code),
    ).fetchall()

    missing_rows: list[dict[str, str]] = []
    counts_by_group_type: dict[str, int] = {}
    matched_count = 0

    for row in rows:
        group_type = str(row[0])
        group_name = str(row[1])
        counts_by_group_type[group_type] = counts_by_group_type.get(group_type, 0) + 1

        if group_type == "layer":
            matched = _entity_match_exists(
                ec_conn,
                ecosystem_id=ecosystem_id,
                entity_type="GROUP_L1",
                group_name=group_name,
            )
        elif group_type == "subindustry":
            matched = _entity_match_exists(
                ec_conn,
                ecosystem_id=ecosystem_id,
                entity_type="GROUP_L2",
                group_name=group_name,
            )
        elif group_type == "ecosystem":
            matched = _entity_match_exists(
                ec_conn,
                ecosystem_id=ecosystem_id,
                entity_type="ECOSYSTEM",
                group_name=group_name,
                alias_type="DC_GROUP_NAME",
            )
        else:
            matched = False

        if matched:
            matched_count += 1
        else:
            missing_rows.append({"group_type": group_type, "group_name": group_name})

    return {
        "count": len(rows),
        "matched_count": matched_count,
        "missing_rows": missing_rows,
        "count_by_group_type": counts_by_group_type,
    }


def _audit_group_index_table(
    analysis_conn: sqlite3.Connection,
    ec_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    selected_date: str,
    taxonomy_version_code: str,
) -> dict[str, object]:
    existing_tables = _table_names(analysis_conn)
    if "dc_group_index_daily" not in existing_tables:
        return {
            "status": "NOT_CHECKED",
            "count": 0,
            "matched_count": 0,
            "missing_rows": [],
        }

    rows = analysis_conn.execute(
        """
        SELECT DISTINCT group_type, group_name
        FROM dc_group_index_daily
        WHERE index_date = ?
          AND taxonomy_version = ?
        ORDER BY group_type, group_name
        """,
        (selected_date, taxonomy_version_code),
    ).fetchall()
    if not rows:
        return {
            "status": "NO_ROWS",
            "count": 0,
            "matched_count": 0,
            "missing_rows": [],
        }

    result = _audit_group_table(
        analysis_conn,
        ec_conn,
        ecosystem_id=ecosystem_id,
        table_name="dc_group_index_daily",
        date_column="index_date",
        selected_date=selected_date,
        taxonomy_version_code=taxonomy_version_code,
    )
    result["status"] = "CHECKED"
    return result


def _primary_membership_checks(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_id: int,
    required_ticker_codes: set[str],
) -> dict[str, object]:
    if required_ticker_codes:
        ticker_placeholders = ", ".join("?" for _ in required_ticker_codes)
        ticker_params: tuple[object, ...] = (taxonomy_version_id, *sorted(required_ticker_codes))
        tickers_without_primary = sorted(
            str(row[0])
            for row in conn.execute(
                f"""
                SELECT child.entity_code
                FROM ec_entity child
                LEFT JOIN ec_membership m
                  ON m.child_entity_id = child.entity_id
                 AND m.taxonomy_version_id = ?
                 AND m.is_primary = 1
                LEFT JOIN ec_entity parent
                  ON parent.entity_id = m.parent_entity_id
                 AND parent.entity_type = 'GROUP_L2'
                WHERE child.entity_type = 'TICKER'
                  AND child.entity_code IN ({ticker_placeholders})
                GROUP BY child.entity_code
                HAVING SUM(CASE WHEN parent.entity_id IS NOT NULL THEN 1 ELSE 0 END) = 0
                """,
                ticker_params,
            ).fetchall()
        )
        tickers_with_multiple_primary = sorted(
            str(row[0])
            for row in conn.execute(
                f"""
                SELECT child.entity_code
                FROM ec_membership m
                JOIN ec_entity child ON child.entity_id = m.child_entity_id
                JOIN ec_entity parent ON parent.entity_id = m.parent_entity_id
                WHERE m.taxonomy_version_id = ?
                  AND child.entity_type = 'TICKER'
                  AND child.entity_code IN ({ticker_placeholders})
                  AND parent.entity_type = 'GROUP_L2'
                  AND m.is_primary = 1
                GROUP BY child.entity_code
                HAVING COUNT(*) > 1
                """,
                ticker_params,
            ).fetchall()
        )
    else:
        tickers_without_primary = []
        tickers_with_multiple_primary = []
    group_l2_without_parent_group_l1 = sorted(
        str(row[0])
        for row in conn.execute(
            """
            SELECT child.entity_name
            FROM ec_entity child
            LEFT JOIN ec_membership m
              ON m.child_entity_id = child.entity_id
             AND m.taxonomy_version_id = ?
            LEFT JOIN ec_entity parent
              ON parent.entity_id = m.parent_entity_id
             AND parent.entity_type = 'GROUP_L1'
            WHERE child.entity_type = 'GROUP_L2'
            GROUP BY child.entity_name
            HAVING SUM(CASE WHEN parent.entity_id IS NOT NULL THEN 1 ELSE 0 END) = 0
            """,
            (taxonomy_version_id,),
        ).fetchall()
    )
    group_l1_without_parent_ecosystem = sorted(
        str(row[0])
        for row in conn.execute(
            """
            SELECT child.entity_name
            FROM ec_entity child
            LEFT JOIN ec_membership m
              ON m.child_entity_id = child.entity_id
             AND m.taxonomy_version_id = ?
            LEFT JOIN ec_entity parent
              ON parent.entity_id = m.parent_entity_id
             AND parent.entity_type = 'ECOSYSTEM'
            WHERE child.entity_type = 'GROUP_L1'
            GROUP BY child.entity_name
            HAVING SUM(CASE WHEN parent.entity_id IS NOT NULL THEN 1 ELSE 0 END) = 0
            """,
            (taxonomy_version_id,),
        ).fetchall()
    )
    multi_membership_ticker_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT child.entity_code
                FROM ec_membership m
                JOIN ec_entity child ON child.entity_id = m.child_entity_id
                JOIN ec_entity parent ON parent.entity_id = m.parent_entity_id
                WHERE m.taxonomy_version_id = ?
                  AND child.entity_type = 'TICKER'
                  AND parent.entity_type = 'GROUP_L2'
                GROUP BY child.entity_code
                HAVING COUNT(*) > 1
            )
            """,
            (taxonomy_version_id,),
        ).fetchone()[0]
    )

    return {
        "ticker_primary_membership_ok": not tickers_without_primary and not tickers_with_multiple_primary,
        "required_ticker_count": len(required_ticker_codes),
        "tickers_without_primary_group_l2": tickers_without_primary,
        "tickers_with_multiple_primary_group_l2": tickers_with_multiple_primary,
        "group_l2_without_parent_group_l1": group_l2_without_parent_group_l1,
        "group_l1_without_parent_ecosystem": group_l1_without_parent_ecosystem,
        "multi_membership_ticker_count": multi_membership_ticker_count,
    }


def audit_dc_facts_against_ec_sidecar(
    analysis_db_path: str,
    ec_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
) -> dict[str, object]:
    analysis_conn = _connect_readonly(analysis_db_path)
    ec_conn = _connect_readonly(ec_db_path)
    try:
        _require_tables(analysis_conn, REQUIRED_ANALYSIS_TABLES, "analysis")
        _require_tables(ec_conn, REQUIRED_EC_TABLES, "ec")
        _require_columns(
            analysis_conn,
            "dc_ticker_swing_signal_daily",
            ("signal_date", "ticker"),
            "analysis",
        )
        _require_columns(
            analysis_conn,
            "dc_group_swing_signal_daily",
            ("signal_date", "group_type", "group_name"),
            "analysis",
        )
        _require_columns(
            analysis_conn,
            "dc_group_synthetic_ohlc_daily",
            ("ohlc_date", "group_type", "group_name"),
            "analysis",
        )

        selected_signal_date = _resolve_signal_date(analysis_conn, signal_date, taxonomy_version_code)
        selected_synthetic_date = _resolve_matching_date(
            analysis_conn,
            "dc_group_synthetic_ohlc_daily",
            "ohlc_date",
            selected_signal_date,
            taxonomy_version_code,
        )
        selected_group_index_date = _resolve_matching_date(
            analysis_conn,
            "dc_group_index_daily",
            "index_date",
            selected_signal_date,
            taxonomy_version_code,
        ) if "dc_group_index_daily" in _table_names(analysis_conn) else None

        ecosystem_id, taxonomy_version_id = _fetch_ec_context(
            ec_conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )

        dc_tickers = _fetch_dc_tickers(analysis_conn, selected_signal_date, taxonomy_version_code)
        ec_tickers = _fetch_ec_ticker_codes(ec_conn, ecosystem_id)
        taxonomy_tickers = _fetch_taxonomy_tickers(
            ec_conn,
            taxonomy_version_id=taxonomy_version_id,
        )
        matched_tickers = sorted(dc_tickers & ec_tickers)
        missing_in_ec_tickers = sorted(dc_tickers - ec_tickers)
        ec_only_tickers = sorted(ec_tickers - dc_tickers)
        unexpected_dc_tickers = sorted(dc_tickers - taxonomy_tickers)

        watchlist_member_tickers, watchlist_sources = _fetch_ec_watchlist_members(ec_conn, ecosystem_id)
        watchlist_missing_tickers: list[str] = []
        for source_reference in watchlist_sources:
            for ticker in _parse_watchlist_source(source_reference):
                if ticker not in watchlist_member_tickers and ticker not in watchlist_missing_tickers:
                    watchlist_missing_tickers.append(ticker)
        watchlist_tickers = set(watchlist_member_tickers)
        dc_fact_tickers = set(dc_tickers)
        watchlist_only_tickers = sorted(watchlist_tickers - taxonomy_tickers)
        watchlist_without_taxonomy_membership_tickers = list(watchlist_only_tickers)
        watchlist_without_dc_fact_tickers = sorted(watchlist_tickers - dc_fact_tickers)
        required_primary_membership_tickers = taxonomy_tickers | dc_fact_tickers

        group_result = _audit_group_table(
            analysis_conn,
            ec_conn,
            ecosystem_id=ecosystem_id,
            table_name="dc_group_swing_signal_daily",
            date_column="signal_date",
            selected_date=selected_signal_date,
            taxonomy_version_code=taxonomy_version_code,
        )
        synthetic_result = _audit_group_table(
            analysis_conn,
            ec_conn,
            ecosystem_id=ecosystem_id,
            table_name="dc_group_synthetic_ohlc_daily",
            date_column="ohlc_date",
            selected_date=selected_synthetic_date or selected_signal_date,
            taxonomy_version_code=taxonomy_version_code,
        )
        group_index_result = _audit_group_index_table(
            analysis_conn,
            ec_conn,
            ecosystem_id=ecosystem_id,
            selected_date=selected_group_index_date or selected_signal_date,
            taxonomy_version_code=taxonomy_version_code,
        )
        membership_result = _primary_membership_checks(
            ec_conn,
            taxonomy_version_id=taxonomy_version_id,
            required_ticker_codes=required_primary_membership_tickers,
        )

        failures = (
            bool(missing_in_ec_tickers)
            or bool(unexpected_dc_tickers)
            or bool(group_result["missing_rows"])
            or bool(synthetic_result["missing_rows"])
            or (
                group_index_result["status"] == "CHECKED"
                and bool(group_index_result["missing_rows"])
            )
            or not membership_result["ticker_primary_membership_ok"]
            or bool(membership_result["group_l2_without_parent_group_l1"])
            or bool(membership_result["group_l1_without_parent_ecosystem"])
        )
        warnings = bool(
            watchlist_missing_tickers
            or watchlist_only_tickers
            or watchlist_without_dc_fact_tickers
        )

        if failures:
            status = "FAILED"
        elif warnings:
            status = "OK_WITH_WARNINGS"
        else:
            status = "OK"

        return {
            "status": status,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "requested_taxonomy_version": taxonomy_version_code,
            "dc_source_taxonomy_version": taxonomy_version_code,
            "dc_source_taxonomy_match": not unexpected_dc_tickers,
            "selected_signal_date": selected_signal_date,
            "selected_synthetic_date": selected_synthetic_date,
            "selected_group_index_date": selected_group_index_date,
            "dc_ticker_count": len(dc_tickers),
            "ec_ticker_count": len(ec_tickers),
            "taxonomy_ticker_count": len(taxonomy_tickers),
            "watchlist_ticker_count": len(watchlist_tickers),
            "dc_fact_ticker_count": len(dc_fact_tickers),
            "matched_ticker_count": len(matched_tickers),
            "missing_in_ec_tickers": missing_in_ec_tickers,
            "ec_only_tickers": ec_only_tickers,
            "unexpected_dc_tickers": unexpected_dc_tickers,
            "watchlist_member_count": len(watchlist_member_tickers),
            "watchlist_only_tickers": watchlist_only_tickers,
            "watchlist_without_taxonomy_membership_tickers": watchlist_without_taxonomy_membership_tickers,
            "watchlist_without_dc_fact_tickers": watchlist_without_dc_fact_tickers,
            "watchlist_missing_tickers": watchlist_missing_tickers,
            "dc_group_count": int(group_result["count"]),
            "matched_group_count": int(group_result["matched_count"]),
            "missing_group_rows": group_result["missing_rows"],
            "dc_group_count_by_type": group_result["count_by_group_type"],
            "dc_synthetic_group_count": int(synthetic_result["count"]),
            "matched_synthetic_group_count": int(synthetic_result["matched_count"]),
            "missing_synthetic_group_rows": synthetic_result["missing_rows"],
            "dc_group_index_status": group_index_result["status"],
            "dc_group_index_count": int(group_index_result["count"]),
            "matched_group_index_count": int(group_index_result["matched_count"]),
            "missing_group_index_rows": group_index_result["missing_rows"],
            "ticker_primary_membership_ok": membership_result["ticker_primary_membership_ok"],
            "required_primary_membership_ticker_count": membership_result["required_ticker_count"],
            "missing_primary_membership_tickers": membership_result["tickers_without_primary_group_l2"],
            "tickers_without_primary_group_l2": membership_result["tickers_without_primary_group_l2"],
            "tickers_with_multiple_primary_group_l2": membership_result["tickers_with_multiple_primary_group_l2"],
            "group_l2_without_parent_group_l1": membership_result["group_l2_without_parent_group_l1"],
            "group_l1_without_parent_ecosystem": membership_result["group_l1_without_parent_ecosystem"],
            "multi_membership_ticker_count": membership_result["multi_membership_ticker_count"],
        }
    finally:
        analysis_conn.close()
        ec_conn.close()
