from __future__ import annotations

import datetime as dt
import sqlite3


def _parse_signal_date(signal_date: str) -> str:
    try:
        return dt.date.fromisoformat(signal_date).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid signal_date: {signal_date}") from exc


def _fetch_one(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> sqlite3.Row | None:
    return conn.execute(query, params).fetchone()


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


def _resolve_ecosystem(conn: sqlite3.Connection, ecosystem_code: str) -> sqlite3.Row:
    row = _fetch_one(
        conn,
        """
        SELECT ecosystem_id, ecosystem_code
        FROM eco_ecosystem
        WHERE ecosystem_code = ?
        """,
        (ecosystem_code,),
    )
    if row is None:
        raise ValueError(f"Missing ecosystem for ecosystem_code '{ecosystem_code}'")
    return row


def _resolve_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_code: str | None,
) -> sqlite3.Row:
    if taxonomy_version_code is not None:
        row = _fetch_one(
            conn,
            """
            SELECT taxonomy_version_id, version_code
            FROM eco_taxonomy_version
            WHERE ecosystem_id = ? AND version_code = ?
            """,
            (ecosystem_id, taxonomy_version_code),
        )
        if row is None:
            raise ValueError(
                f"Missing taxonomy version '{taxonomy_version_code}' for ecosystem_id {ecosystem_id}"
            )
        return row

    rows = conn.execute(
        """
        SELECT taxonomy_version_id, version_code
        FROM eco_taxonomy_version
        WHERE ecosystem_id = ? AND is_active = 1 AND status = 'ACTIVE'
        ORDER BY version_code
        """,
        (ecosystem_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"No active taxonomy version found for ecosystem_id {ecosystem_id}")
    if len(rows) > 1:
        raise ValueError(
            f"Multiple active taxonomy versions found for ecosystem_id {ecosystem_id}; taxonomy_version_code is required"
        )
    return rows[0]


def _load_active_windows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT window_code, sort_order
        FROM eco_report_window
        WHERE is_active = 1
        ORDER BY sort_order, window_code
        """
    ).fetchall()
    if not rows:
        raise ValueError("No active report windows found")
    return rows


def _generate_run_id(ecosystem_code: str, signal_date: str, taxonomy_version_code: str) -> str:
    return f"V3_BASE_{ecosystem_code}_{signal_date.replace('-', '_')}_{taxonomy_version_code}"


def _validate_replace_allowed(conn: sqlite3.Connection, run_id: str) -> None:
    dependent_tables = (
        "eco_entity_window_snapshot",
        "eco_entity_metric_value",
        "eco_signal_observation",
        "eco_entity_event",
    )
    blocking_tables: list[str] = []
    for table_name in dependent_tables:
        if not _table_exists(conn, table_name):
            continue
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name} WHERE run_id = ?", (run_id,)).fetchone()
        if int(row[0]) > 0:
            blocking_tables.append(table_name)
    if blocking_tables:
        raise ValueError(
            f"Cannot replace run_id '{run_id}' because dependent rows exist in: {', '.join(blocking_tables)}"
        )


def _delete_owned_rows_for_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("DELETE FROM eco_quality_summary WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM eco_entity_coverage WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM eco_report_run WHERE run_id = ?", (run_id,))


def _load_daily_signal_tickers(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> set[str]:
    if not _table_exists(conn, "dc_ticker_swing_signal_daily"):
        return set()
    rows = conn.execute(
        """
        SELECT ticker
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    return {str(row[0]).strip().upper() for row in rows}


def _load_selected_entities(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
) -> tuple[dict[int, sqlite3.Row], set[int], set[int], int]:
    taxonomy_entity_ids = {
        int(row[0])
        for row in conn.execute(
            """
            SELECT parent_entity_id
            FROM eco_taxonomy_entity_relation
            WHERE taxonomy_version_id = ?
            UNION
            SELECT child_entity_id
            FROM eco_taxonomy_entity_relation
            WHERE taxonomy_version_id = ?
            """,
            (taxonomy_version_id, taxonomy_version_id),
        ).fetchall()
    }
    ecosystem_entity_row = _fetch_one(
        conn,
        """
        SELECT entity_id
        FROM eco_entity
        WHERE ecosystem_id = ? AND entity_type = 'ECOSYSTEM' AND status IN ('ACTIVE', 'WATCH_ONLY')
        ORDER BY entity_id
        LIMIT 1
        """,
        (ecosystem_id,),
    )
    if ecosystem_entity_row is None:
        raise ValueError(f"Missing ECOSYSTEM entity for ecosystem_id {ecosystem_id}")
    ecosystem_entity_id = int(ecosystem_entity_row[0])
    taxonomy_entity_ids.add(ecosystem_entity_id)

    watchlist_entity_ids = {
        int(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT m.entity_id
            FROM eco_watchlist_member m
            JOIN eco_watchlist w ON w.watchlist_id = m.watchlist_id
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE w.ecosystem_id = ?
              AND w.status = 'ACTIVE'
              AND m.member_status = 'ACTIVE'
              AND e.status IN ('ACTIVE', 'WATCH_ONLY')
            """,
            (ecosystem_id,),
        ).fetchall()
    }

    selected_entity_ids = sorted(taxonomy_entity_ids | watchlist_entity_ids)
    entities = {
        int(row["entity_id"]): row
        for row in conn.execute(
            f"""
            SELECT entity_id, entity_type, entity_code, entity_name, ticker, status
            FROM eco_entity
            WHERE entity_id IN ({", ".join("?" for _ in selected_entity_ids)})
            ORDER BY entity_type, entity_code, entity_id
            """,
            tuple(selected_entity_ids),
        ).fetchall()
    } if selected_entity_ids else {}
    return entities, taxonomy_entity_ids, watchlist_entity_ids, ecosystem_entity_id


def _build_coverage_row(
    entity: sqlite3.Row,
    *,
    run_id: str,
    ecosystem_id: int,
    signal_date: str,
    taxonomy_version_id: int,
    window_code: str,
    in_taxonomy: int,
    in_watchlist: int,
    has_daily_signal: int,
) -> dict[str, object]:
    entity_type = str(entity["entity_type"])
    entity_status = str(entity["status"])
    ticker = str(entity["ticker"] or entity["entity_code"] or "").strip().upper()

    if entity_type != "TICKER":
        has_instrument = 1
        has_price_data = 1
        has_daily_signal_value = 1
        has_window_context = 1
        coverage_status = "OK" if in_taxonomy == 1 else ("WATCHLIST_ONLY" if in_watchlist == 1 else "UNKNOWN")
        source_row_count: int | None = None
        missing_component_count = 0
    else:
        has_daily_signal_value = has_daily_signal
        if in_taxonomy == 1 and entity_status == "ACTIVE":
            has_instrument = 1
            has_price_data = 1
        else:
            # First base builder keeps ticker availability logic intentionally conservative.
            has_instrument = 0
            has_price_data = 0
        has_window_context = 1 if has_daily_signal_value == 1 else 0
        source_row_count = has_daily_signal_value
        missing_component_count = sum(
            1
            for value in (
                has_instrument,
                has_price_data,
                has_daily_signal_value,
                has_window_context,
            )
            if value == 0
        )
        if in_taxonomy == 0 and in_watchlist == 1:
            coverage_status = "WATCHLIST_ONLY"
        elif has_daily_signal_value == 0:
            coverage_status = "MISSING_DAILY_SIGNAL"
        elif in_taxonomy == 1:
            coverage_status = "OK"
        else:
            coverage_status = "UNKNOWN"

    if coverage_status == "WATCHLIST_ONLY":
        coverage_notes = "watchlist_only_entity"
    elif coverage_status == "MISSING_DAILY_SIGNAL":
        coverage_notes = f"missing_daily_signal:{ticker}"
    elif coverage_status == "UNKNOWN":
        coverage_notes = "unknown_coverage_status"
    else:
        coverage_notes = None

    return {
        "run_id": run_id,
        "ecosystem_id": ecosystem_id,
        "signal_date": signal_date,
        "taxonomy_version_id": taxonomy_version_id,
        "window_code": window_code,
        "entity_id": int(entity["entity_id"]),
        "in_taxonomy": in_taxonomy,
        "in_watchlist": in_watchlist,
        "has_instrument": has_instrument,
        "has_price_data": has_price_data,
        "has_daily_signal": has_daily_signal_value,
        "has_window_context": has_window_context,
        "coverage_status": coverage_status,
        "source_row_count": source_row_count,
        "missing_component_count": missing_component_count,
        "coverage_notes": coverage_notes,
    }


def build_canonical_v3_base_run(
    db_path: str,
    ecosystem_code: str,
    signal_date: str,
    taxonomy_version_code: str | None = None,
    run_id: str | None = None,
    run_type: str = "BUILD",
    replace_run: bool = False,
) -> dict:
    normalized_signal_date = _parse_signal_date(signal_date)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ecosystem_row = _resolve_ecosystem(conn, ecosystem_code)
        ecosystem_id = int(ecosystem_row["ecosystem_id"])
        taxonomy_row = _resolve_taxonomy_version(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_code=taxonomy_version_code,
        )
        taxonomy_version_id = int(taxonomy_row["taxonomy_version_id"])
        resolved_taxonomy_version_code = str(taxonomy_row["version_code"])
        active_windows = _load_active_windows(conn)

        resolved_run_id = (
            run_id
            if run_id is not None
            else _generate_run_id(ecosystem_code, normalized_signal_date, resolved_taxonomy_version_code)
        )

        existing_run = _fetch_one(
            conn,
            "SELECT run_id FROM eco_report_run WHERE run_id = ?",
            (resolved_run_id,),
        )
        if existing_run is not None and not replace_run:
            raise ValueError(f"Run '{resolved_run_id}' already exists and replace_run is False")
        if existing_run is not None and replace_run:
            _validate_replace_allowed(conn, resolved_run_id)

        daily_signal_tickers = _load_daily_signal_tickers(
            conn,
            signal_date=normalized_signal_date,
            taxonomy_version_code=resolved_taxonomy_version_code,
        )
        entities, taxonomy_entity_ids, watchlist_entity_ids, ecosystem_entity_id = _load_selected_entities(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
        )
        if not entities:
            raise ValueError(
                f"No entities selected for ecosystem_code '{ecosystem_code}' and taxonomy_version '{resolved_taxonomy_version_code}'"
            )

        coverage_rows: list[dict[str, object]] = []
        for window_row in active_windows:
            window_code = str(window_row["window_code"])
            for entity_id, entity in entities.items():
                ticker = str(entity["ticker"] or entity["entity_code"] or "").strip().upper()
                coverage_rows.append(
                    _build_coverage_row(
                        entity,
                        run_id=resolved_run_id,
                        ecosystem_id=ecosystem_id,
                        signal_date=normalized_signal_date,
                        taxonomy_version_id=taxonomy_version_id,
                        window_code=window_code,
                        in_taxonomy=1 if entity_id in taxonomy_entity_ids else 0,
                        in_watchlist=1 if entity_id in watchlist_entity_ids else 0,
                        has_daily_signal=1 if ticker and ticker in daily_signal_tickers else 0,
                    )
                )

        warning_count = sum(1 for row in coverage_rows if row["coverage_status"] != "OK")
        run_status = "OK_WITH_WARNINGS" if warning_count > 0 else "OK"
        quality_rows: list[dict[str, object]] = []
        expected_count = len(entities)
        for window_row in active_windows:
            window_code = str(window_row["window_code"])
            window_coverage_rows = [row for row in coverage_rows if row["window_code"] == window_code]
            actual_count = len(window_coverage_rows)
            missing_count = sum(1 for row in window_coverage_rows if row["coverage_status"] != "OK")
            warning_rows = sum(
                1
                for row in window_coverage_rows
                if row["coverage_status"] in {"WATCHLIST_ONLY", "MISSING_DAILY_SIGNAL", "UNKNOWN"}
            )
            quality_status = "WARN" if missing_count > 0 else "OK"
            summary_note = f"selected_entities={expected_count};missing={missing_count}" if missing_count > 0 else None
            for quality_scope in ("RUN", "WINDOW"):
                quality_rows.append(
                    {
                        "run_id": resolved_run_id,
                        "ecosystem_id": ecosystem_id,
                        "signal_date": normalized_signal_date,
                        "taxonomy_version_id": taxonomy_version_id,
                        "window_code": window_code,
                        "quality_scope": quality_scope,
                        "scope_entity_id": ecosystem_entity_id,
                        "quality_status": quality_status,
                        "expected_count": expected_count,
                        "actual_count": actual_count,
                        "missing_count": missing_count,
                        "incomplete_count": 0,
                        "stale_count": 0,
                        "warning_count": warning_rows,
                        "error_count": 0,
                        "summary_note": summary_note,
                    }
                )

        conn.execute("BEGIN")
        if existing_run is not None and replace_run:
            _delete_owned_rows_for_run(conn, resolved_run_id)
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
                resolved_run_id,
                ecosystem_id,
                taxonomy_version_id,
                normalized_signal_date,
                run_type,
                run_status,
                None,
                warning_count,
                0,
                f"coverage_rows={len(coverage_rows)};quality_rows={len(quality_rows)}",
            ),
        )
        conn.executemany(
            """
            INSERT INTO eco_entity_coverage (
                run_id,
                ecosystem_id,
                signal_date,
                taxonomy_version_id,
                window_code,
                entity_id,
                in_taxonomy,
                in_watchlist,
                has_instrument,
                has_price_data,
                has_daily_signal,
                has_window_context,
                coverage_status,
                source_row_count,
                missing_component_count,
                coverage_notes
            ) VALUES (
                :run_id,
                :ecosystem_id,
                :signal_date,
                :taxonomy_version_id,
                :window_code,
                :entity_id,
                :in_taxonomy,
                :in_watchlist,
                :has_instrument,
                :has_price_data,
                :has_daily_signal,
                :has_window_context,
                :coverage_status,
                :source_row_count,
                :missing_component_count,
                :coverage_notes
            )
            """,
            coverage_rows,
        )
        conn.executemany(
            """
            INSERT INTO eco_quality_summary (
                run_id,
                ecosystem_id,
                signal_date,
                taxonomy_version_id,
                window_code,
                quality_scope,
                scope_entity_id,
                quality_status,
                expected_count,
                actual_count,
                missing_count,
                incomplete_count,
                stale_count,
                warning_count,
                error_count,
                summary_note
            ) VALUES (
                :run_id,
                :ecosystem_id,
                :signal_date,
                :taxonomy_version_id,
                :window_code,
                :quality_scope,
                :scope_entity_id,
                :quality_status,
                :expected_count,
                :actual_count,
                :missing_count,
                :incomplete_count,
                :stale_count,
                :warning_count,
                :error_count,
                :summary_note
            )
            """,
            quality_rows,
        )
        conn.commit()
        return {
            "run_id": resolved_run_id,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": resolved_taxonomy_version_code,
            "signal_date": normalized_signal_date,
            "window_count": len(active_windows),
            "selected_entity_count": len(entities),
            "coverage_rows_inserted": len(coverage_rows),
            "quality_rows_inserted": len(quality_rows),
            "warning_count": warning_count,
            "status": run_status,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
