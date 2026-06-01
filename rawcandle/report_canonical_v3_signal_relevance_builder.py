from __future__ import annotations

import sqlite3
from collections import Counter


ALLOWED_DIRECTIONS = {
    "BULLISH": "BULLISH",
    "BEARISH": "BEARISH",
    "NEUTRAL": "NEUTRAL",
    "MIXED": "MIXED",
    "UP": "UP",
    "DOWN": "DOWN",
    "NONE": "NONE",
}
RELEVANCE_MAP = {
    "RELEVANT": "RELEVANT",
    "WEAK_CONTEXT": "WEAK_CONTEXT",
    "NOISE": "NOISE",
    "NOT_RELEVANT": "NOT_RELEVANT",
    "CONTEXTUAL": "CONTEXTUAL",
    "CONFIRMING": "CONFIRMING",
    "COUNTER_TREND": "COUNTER_TREND",
    "STALE": "STALE",
}
TIMEFRAME_BY_WINDOW = {
    "daily": "1d",
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def _resolve_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = _fetch_one(
        conn,
        """
        SELECT
            rr.run_id,
            rr.ecosystem_id,
            ee.ecosystem_code,
            rr.taxonomy_version_id,
            tv.version_code,
            rr.signal_date
        FROM eco_report_run rr
        JOIN eco_ecosystem ee ON ee.ecosystem_id = rr.ecosystem_id
        JOIN eco_taxonomy_version tv ON tv.taxonomy_version_id = rr.taxonomy_version_id
        WHERE rr.run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        raise ValueError(f"Missing eco_report_run for run_id '{run_id}'")
    return row


def _resolve_window(conn: sqlite3.Connection, window_code: str) -> str:
    if window_code != "daily":
        raise ValueError("Only window_code='daily' is supported in this pilot")
    row = _fetch_one(
        conn,
        """
        SELECT window_code
        FROM eco_report_window
        WHERE window_code = ?
        """,
        (window_code,),
    )
    if row is None:
        raise ValueError(f"Missing eco_report_window for window_code '{window_code}'")
    return str(row["window_code"])


def _discover_technical_relevance_run_id(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> str:
    pattern = f"DATACENTER_TECH_REL_{taxonomy_version_code}_{signal_date.replace('-', '_')}"
    rows = conn.execute(
        """
        SELECT DISTINCT run_id
        FROM technical_signal_relevance
        WHERE signal_date = ? AND timeframe = '1d' AND run_id LIKE ?
        ORDER BY run_id
        """,
        (signal_date, pattern),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(
            "Could not uniquely discover technical_relevance_run_id for "
            f"signal_date '{signal_date}' and taxonomy '{taxonomy_version_code}'"
        )
    return str(rows[0]["run_id"])


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    technical_relevance_run_id: str,
    signal_date: str,
    window_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, "technical_signal_relevance"):
        raise ValueError("Missing source table 'technical_signal_relevance'")
    timeframe = TIMEFRAME_BY_WINDOW[window_code]
    rows = conn.execute(
        """
        SELECT
            ticker,
            timeframe,
            signal_date,
            signal_confirmed_as_of_date,
            signal_name,
            signal_close_price,
            signal_direction,
            signal_family,
            signal_source_type,
            signal_source_id,
            dow_trend_state,
            dow_context_state,
            latest_bos_direction,
            bars_since_latest_bos,
            latest_reset_reason,
            bars_since_latest_reset,
            near_latest_pivot,
            near_active_bos_level,
            is_trend_aligned,
            is_counter_trend,
            relevance_class,
            relevance_reason,
            relevance_rule_version,
            mapping_version,
            reason_version,
            rule_trace,
            created_at_utc,
            run_id
        FROM technical_signal_relevance
        WHERE run_id = ? AND signal_date = ? AND timeframe = ?
        ORDER BY ticker, signal_name, signal_source_type, signal_source_id
        """,
        (technical_relevance_run_id, signal_date, timeframe),
    ).fetchall()
    if not rows:
        raise ValueError(
            f"No technical_signal_relevance rows found for run_id '{technical_relevance_run_id}' "
            f"and signal_date '{signal_date}'"
        )
    return rows


def _load_ticker_entities(conn: sqlite3.Connection, ecosystem_id: int) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT entity_id, entity_code
        FROM eco_entity
        WHERE ecosystem_id = ? AND entity_type = 'TICKER'
        """,
        (ecosystem_id,),
    ).fetchall()
    return {str(row["entity_code"]): row for row in rows}


def _normalize_signal_direction(value: object, warnings: list[str]) -> str:
    if value is None:
        warnings.append("source_signal_direction:null->UNKNOWN")
        return "UNKNOWN"
    text = str(value).strip().upper()
    mapped = ALLOWED_DIRECTIONS.get(text)
    if mapped is not None:
        return mapped
    warnings.append(f"source_signal_direction:{text}->UNKNOWN")
    return "UNKNOWN"


def _normalize_relevance_label(value: object, warnings: list[str]) -> str:
    if value is None:
        warnings.append("source_relevance_class:null->UNKNOWN")
        return "UNKNOWN"
    text = str(value).strip().upper()
    mapped = RELEVANCE_MAP.get(text)
    if mapped is not None:
        return mapped
    warnings.append(f"source_relevance_class:{text}->UNKNOWN")
    return "UNKNOWN"


def _format_context(prefix: str, value: object, age_value: object | None = None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    if age_value is None:
        return f"{prefix}:{value}"
    return f"{prefix}:{value};bars={age_value}"


def _build_rows(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    technical_relevance_run_id: str,
    source_rows: list[sqlite3.Row],
    ticker_entities: dict[str, sqlite3.Row],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int], dict[str, int], list[str], int]:
    observation_rows: list[dict[str, object]] = []
    relevance_rows: list[dict[str, object]] = []
    signal_family_counts: Counter[str] = Counter()
    relevance_label_counts: Counter[str] = Counter()
    warnings: list[str] = []
    source_rows_skipped = 0
    seen_grains: set[tuple[object, ...]] = set()

    for source_row in source_rows:
        ticker = str(source_row["ticker"])
        entity_row = ticker_entities.get(ticker)
        if entity_row is None:
            warnings.append(f"Missing V3 ticker entity for source ticker '{ticker}'")
            source_rows_skipped += 1
            continue

        signal_name = str(source_row["signal_name"])
        observed_date = str(source_row["signal_confirmed_as_of_date"] or source_row["signal_date"])
        grain = (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            window_code,
            int(entity_row["entity_id"]),
            signal_name,
            observed_date,
        )
        if grain in seen_grains:
            warnings.append(f"Duplicate signal observation grain skipped for ticker '{ticker}' and signal '{signal_name}'")
            source_rows_skipped += 1
            continue
        seen_grains.add(grain)

        direction_warnings: list[str] = []
        normalized_direction = _normalize_signal_direction(source_row["signal_direction"], direction_warnings)
        warnings.extend(direction_warnings)
        relevance_warnings: list[str] = []
        relevance_label = _normalize_relevance_label(source_row["relevance_class"], relevance_warnings)
        warnings.extend(relevance_warnings)
        source_event_id = str(source_row["signal_source_id"] or "").strip()
        if not source_event_id:
            source_event_id = (
                f"{ticker}|{signal_name}|{source_row['signal_source_type']}|"
                f"{source_row['signal_date']}|{source_row['relevance_rule_version']}"
            )

        observation_rows.append(
            {
                "run_id": str(run_row["run_id"]),
                "ecosystem_id": int(run_row["ecosystem_id"]),
                "signal_date": str(run_row["signal_date"]),
                "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
                "window_code": window_code,
                "entity_id": int(entity_row["entity_id"]),
                "signal_name": signal_name,
                "signal_family": source_row["signal_family"],
                "signal_direction": normalized_direction,
                "signal_value": source_row["relevance_class"],
                "observed_date": observed_date,
                "source_table": "technical_signal_relevance",
                "source_run_id": technical_relevance_run_id,
                "source_event_id": source_event_id,
                "signal_status": "ACTIVE",
            }
        )
        relevance_rows.append(
            {
                "relevance_label": relevance_label,
                "relevance_score": None,
                "relevance_reason": source_row["relevance_reason"],
                "trend_alignment": (
                    "ALIGNED"
                    if int(source_row["is_trend_aligned"]) == 1
                    else "NOT_ALIGNED"
                ),
                "dow_context": _format_context(
                    "dow",
                    f"{source_row['dow_trend_state']}|{source_row['dow_context_state']}"
                    if source_row["dow_trend_state"] is not None or source_row["dow_context_state"] is not None
                    else None,
                ),
                "bos_context": _format_context(
                    "bos",
                    source_row["latest_bos_direction"],
                    source_row["bars_since_latest_bos"],
                ),
                "reset_context": _format_context(
                    "reset",
                    source_row["latest_reset_reason"],
                    source_row["bars_since_latest_reset"],
                ),
                "counter_trend_context": (
                    "COUNTER_TREND"
                    if int(source_row["is_counter_trend"]) == 1
                    else "NOT_COUNTER_TREND"
                ),
            }
        )
        signal_family = source_row["signal_family"] if source_row["signal_family"] is not None else "UNKNOWN"
        signal_family_counts[str(signal_family)] += 1
        relevance_label_counts[relevance_label] += 1

    return (
        observation_rows,
        relevance_rows,
        dict(sorted(relevance_label_counts.items())),
        dict(sorted(signal_family_counts.items())),
        warnings,
        source_rows_skipped,
    )


def _existing_source_rows_count(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    window_code: str,
    technical_relevance_run_id: str,
) -> tuple[int, int]:
    observation_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_observation
            WHERE run_id = ? AND window_code = ? AND source_run_id = ?
            """,
            (run_id, window_code, technical_relevance_run_id),
        ).fetchone()[0]
    )
    relevance_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_signal_relevance
            WHERE signal_observation_id IN (
                SELECT signal_observation_id
                FROM eco_signal_observation
                WHERE run_id = ? AND window_code = ? AND source_run_id = ?
            )
            """,
            (run_id, window_code, technical_relevance_run_id),
        ).fetchone()[0]
    )
    return observation_count, relevance_count


def _delete_existing_rows(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    window_code: str,
    technical_relevance_run_id: str,
) -> None:
    conn.execute(
        """
        DELETE FROM eco_signal_relevance
        WHERE signal_observation_id IN (
            SELECT signal_observation_id
            FROM eco_signal_observation
            WHERE run_id = ? AND window_code = ? AND source_run_id = ?
        )
        """,
        (run_id, window_code, technical_relevance_run_id),
    )
    conn.execute(
        """
        DELETE FROM eco_signal_observation
        WHERE run_id = ? AND window_code = ? AND source_run_id = ?
        """,
        (run_id, window_code, technical_relevance_run_id),
    )


def _insert_observation_rows(conn: sqlite3.Connection, observation_rows: list[dict[str, object]]) -> list[int]:
    observation_ids: list[int] = []
    for row in observation_rows:
        cursor = conn.execute(
            """
            INSERT INTO eco_signal_observation (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
                entity_id, signal_name, signal_family, signal_direction, signal_value,
                observed_date, source_table, source_run_id, source_event_id, signal_status
            ) VALUES (
                :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code,
                :entity_id, :signal_name, :signal_family, :signal_direction, :signal_value,
                :observed_date, :source_table, :source_run_id, :source_event_id, :signal_status
            )
            """,
            row,
        )
        observation_ids.append(int(cursor.lastrowid))
    return observation_ids


def _insert_relevance_rows(
    conn: sqlite3.Connection,
    observation_ids: list[int],
    relevance_rows: list[dict[str, object]],
) -> None:
    for signal_observation_id, row in zip(observation_ids, relevance_rows, strict=True):
        conn.execute(
            """
            INSERT INTO eco_signal_relevance (
                signal_observation_id, relevance_label, relevance_score, relevance_reason,
                trend_alignment, dow_context, bos_context, reset_context, counter_trend_context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_observation_id,
                row["relevance_label"],
                row["relevance_score"],
                row["relevance_reason"],
                row["trend_alignment"],
                row["dow_context"],
                row["bos_context"],
                row["reset_context"],
                row["counter_trend_context"],
            ),
        )


def build_canonical_v3_signal_relevance(
    db_path: str,
    run_id: str,
    technical_relevance_run_id: str | None = None,
    window_code: str = "daily",
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        resolved_window_code = _resolve_window(conn, window_code)
        if technical_relevance_run_id is None:
            technical_relevance_run_id = _discover_technical_relevance_run_id(
                conn,
                signal_date=str(run_row["signal_date"]),
                taxonomy_version_code=str(run_row["version_code"]),
            )
        source_rows = _load_source_rows(
            conn,
            technical_relevance_run_id=technical_relevance_run_id,
            signal_date=str(run_row["signal_date"]),
            window_code=resolved_window_code,
        )
        ticker_entities = _load_ticker_entities(conn, int(run_row["ecosystem_id"]))
        existing_observation_count, existing_relevance_count = _existing_source_rows_count(
            conn,
            run_id=str(run_row["run_id"]),
            window_code=resolved_window_code,
            technical_relevance_run_id=technical_relevance_run_id,
        )
        if not replace_existing and (existing_observation_count > 0 or existing_relevance_count > 0):
            raise ValueError(
                "Signal observations or relevance rows already exist for "
                f"run_id '{run_id}', window_code '{resolved_window_code}', "
                f"source_run_id '{technical_relevance_run_id}'"
            )

        (
            observation_rows,
            relevance_rows,
            relevance_label_counts,
            signal_family_counts,
            warnings,
            source_rows_skipped,
        ) = _build_rows(
            run_row=run_row,
            window_code=resolved_window_code,
            technical_relevance_run_id=technical_relevance_run_id,
            source_rows=source_rows,
            ticker_entities=ticker_entities,
        )

        conn.execute("BEGIN")
        if replace_existing:
            _delete_existing_rows(
                conn,
                run_id=str(run_row["run_id"]),
                window_code=resolved_window_code,
                technical_relevance_run_id=technical_relevance_run_id,
            )
        observation_ids = _insert_observation_rows(conn, observation_rows)
        _insert_relevance_rows(conn, observation_ids, relevance_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_code": str(run_row["ecosystem_code"]),
        "taxonomy_version_code": str(run_row["version_code"]),
        "signal_date": str(run_row["signal_date"]),
        "window_code": resolved_window_code,
        "technical_relevance_run_id": technical_relevance_run_id,
        "source_rows_read": len(source_rows),
        "source_rows_mapped": len(observation_rows),
        "source_rows_skipped": source_rows_skipped,
        "signal_observations_inserted": len(observation_rows),
        "signal_relevance_rows_inserted": len(relevance_rows),
        "relevance_label_counts": relevance_label_counts,
        "signal_family_counts": signal_family_counts,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
