from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE = "dc_report_classification_v2"
DEFAULT_CLASSIFICATION_TYPES = (
    "daily_trigger",
    "rolling2_sell_pressure",
    "rolling5_pullback",
)
WINDOW_CODE_BY_CLASSIFICATION_TYPE = {
    "daily_trigger": "daily",
    "rolling2_sell_pressure": "rolling2",
    "rolling5_pullback": "rolling5",
}
SUPPORTED_CLASSIFICATION_TYPES = frozenset(DEFAULT_CLASSIFICATION_TYPES)


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


def _normalize_requested_classification_types(
    classification_types: list[str] | None,
) -> tuple[str, ...]:
    if classification_types is None:
        return DEFAULT_CLASSIFICATION_TYPES

    requested = tuple(classification_types)
    unsupported = sorted(set(requested) - SUPPORTED_CLASSIFICATION_TYPES)
    if unsupported:
        raise ValueError(
            "Unsupported classification_type(s) for this phase: "
            + ", ".join(unsupported)
            + ". rolling30_buy and rolling30_exit are handled later."
        )
    return requested


def _classification_type_from_source(
    horizon: str | None,
    source_classification_type: str | None,
) -> str | None:
    normalized_type = str(source_classification_type).strip().lower() if source_classification_type else ""
    normalized_horizon = str(horizon).strip().lower() if horizon else ""
    if normalized_type == "daily_trigger" or normalized_horizon == "daily":
        return "daily_trigger"
    if normalized_type == "rolling2_sell_pressure" or normalized_horizon == "rolling2":
        return "rolling2_sell_pressure"
    if normalized_type == "rolling5_pullback" or normalized_horizon == "rolling5":
        return "rolling5_pullback"
    return None


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _select_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in column_names:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")

    columns = _column_names(conn, SOURCE_TABLE)
    required = {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "horizon",
        "classification_type",
        "classification_state",
    }
    missing_required = sorted(required - columns)
    if missing_required:
        raise ValueError(
            f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing_required)}"
        )

    query = f"""
        SELECT
            signal_date,
            taxonomy_version,
            ticker,
            horizon,
            classification_type,
            classification_state,
            {_select_expr(columns, ('primary_reason',), 'primary_reason')},
            {_select_expr(columns, ('blocking_reason',), 'blocking_reason')},
            {_select_expr(columns, ('risk_reason',), 'risk_reason')},
            {_select_expr(columns, ('next_action',), 'next_action')},
            {_select_expr(columns, ('candidate_priority', 'priority_score'), 'priority_score')},
            {_select_expr(columns, ('candidate_priority_label', 'priority_label'), 'priority_label')},
            {_select_expr(columns, ('rank', 'sort_rank'), 'sort_rank')},
            {_select_expr(columns, ('source_classifier',), 'source_classifier')},
            {_select_expr(columns, ('classification_version',), 'classification_version')},
            {_select_expr(columns, ('run_id',), 'source_run_id')}
        FROM {SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND horizon IN ('daily', 'rolling2', 'rolling5')
        ORDER BY horizon, ticker
    """
    return conn.execute(query, (signal_date, taxonomy_version_code)).fetchall()


def _load_eligible_ticker_entities(
    conn: sqlite3.Connection,
    *,
    run_row: sqlite3.Row,
    classification_types: tuple[str, ...],
) -> dict[tuple[str, str], sqlite3.Row]:
    windows = tuple(WINDOW_CODE_BY_CLASSIFICATION_TYPE[value] for value in classification_types)
    placeholders = ", ".join("?" for _ in windows)
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            c.window_code,
            e.entity_id,
            e.entity_code
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code IN ({placeholders})
          AND e.ecosystem_id = ?
          AND e.entity_type = 'TICKER'
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            *windows,
            int(run_row["ecosystem_id"]),
        ),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eligible TICKER coverage rows for run_id '{run_row['run_id']}'")
    return {(str(row["window_code"]), str(row["entity_code"])): row for row in rows}


def _ensure_replace_allowed(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    classification_types: tuple[str, ...],
    replace_existing: bool,
) -> None:
    placeholders = ", ".join("?" for _ in classification_types)
    existing_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM eco_classification_decision
        WHERE run_id = ?
          AND classification_type IN ({placeholders})
        """,
        (run_id, *classification_types),
    ).fetchone()[0]
    if existing_count and not replace_existing:
        raise ValueError(
            "eco_classification_decision rows already exist for "
            f"run_id '{run_id}' and classification types {', '.join(classification_types)}"
        )
    if existing_count and replace_existing:
        conn.execute(
            f"""
            DELETE FROM eco_classification_decision
            WHERE run_id = ?
              AND classification_type IN ({placeholders})
            """,
            (run_id, *classification_types),
        )


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _normalize_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _decision_status_for_row(row: sqlite3.Row) -> str:
    classification_state = _normalize_text(row["classification_state"])
    if classification_state:
        return "OK"
    return "MISSING"


def _source_classifier_for_type(classification_type: str, source_value: object) -> str:
    normalized = _normalize_text(source_value)
    if normalized:
        return normalized
    if classification_type == "daily_trigger":
        return "daily_trigger"
    if classification_type == "rolling2_sell_pressure":
        return "rolling2_sell_pressure_classifier"
    return "rolling5_pullback_classifier"


def build_canonical_v3_classification_decisions(
    db_path: str,
    run_id: str,
    classification_types: list[str] | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    requested_types = _normalize_requested_classification_types(classification_types)
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        source_rows = _load_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )
        eligible_entities = _load_eligible_ticker_entities(
            conn,
            run_row=run_row,
            classification_types=requested_types,
        )

        warnings: list[str] = []
        decision_rows: list[tuple[object, ...]] = []
        classification_type_counts: Counter[str] = Counter()
        classification_state_counts: Counter[str] = Counter()
        source_rows_mapped = 0
        source_rows_skipped = 0

        for row in source_rows:
            classification_type = _classification_type_from_source(
                row["horizon"],
                row["classification_type"],
            )
            if classification_type not in requested_types:
                continue

            window_code = WINDOW_CODE_BY_CLASSIFICATION_TYPE[classification_type]
            ticker = str(row["ticker"])
            entity_row = eligible_entities.get((window_code, ticker))
            if entity_row is None:
                warnings.append(
                    f"Missing V3 ticker entity/coverage for source ticker='{ticker}' window_code='{window_code}'"
                )
                source_rows_skipped += 1
                continue

            source_rows_mapped += 1
            classification_state = _normalize_text(row["classification_state"]) or ""
            decision_status = _decision_status_for_row(row)
            decision_rows.append(
                (
                    str(run_row["run_id"]),
                    int(run_row["ecosystem_id"]),
                    str(run_row["signal_date"]),
                    int(run_row["taxonomy_version_id"]),
                    window_code,
                    int(entity_row["entity_id"]),
                    classification_type,
                    classification_state,
                    _normalize_text(row["primary_reason"]),
                    _normalize_text(row["blocking_reason"]),
                    _normalize_text(row["risk_reason"]),
                    _normalize_text(row["next_action"]),
                    _normalize_float(row["priority_score"]),
                    _normalize_text(row["priority_label"]),
                    _normalize_int(row["sort_rank"]),
                    _source_classifier_for_type(classification_type, row["source_classifier"]),
                    _normalize_text(row["classification_version"]),
                    _normalize_text(row["source_run_id"]),
                    decision_status,
                )
            )
            classification_type_counts[classification_type] += 1
            classification_state_counts[classification_state] += 1

        conn.execute("BEGIN")
        try:
            _ensure_replace_allowed(
                conn,
                run_id=run_id,
                classification_types=requested_types,
                replace_existing=replace_existing,
            )
            conn.executemany(
                """
                INSERT INTO eco_classification_decision (
                    run_id,
                    ecosystem_id,
                    signal_date,
                    taxonomy_version_id,
                    window_code,
                    entity_id,
                    classification_type,
                    classification_state,
                    primary_reason,
                    blocking_reason,
                    risk_reason,
                    next_action,
                    priority_score,
                    priority_label,
                    sort_rank,
                    source_classifier,
                    classification_version,
                    source_run_id,
                    decision_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                decision_rows,
            )
        except Exception:
            conn.rollback()
            raise
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "classification_types": list(requested_types),
            "source_rows_read": len(source_rows),
            "source_rows_mapped": source_rows_mapped,
            "source_rows_skipped": source_rows_skipped,
            "decision_rows_inserted": len(decision_rows),
            "classification_type_counts": dict(classification_type_counts),
            "classification_state_counts": dict(classification_state_counts),
            "warning_count": len(warnings),
            "warnings": warnings,
        }
    finally:
        conn.close()
