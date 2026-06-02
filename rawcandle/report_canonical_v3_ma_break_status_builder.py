from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict

from analysis.datacenter_indices.swing_ma_break_status import (
    build_swing_ma_break_status_rows,
    load_ticker_ma_history_rows,
)


SOURCE_TABLE = "dc_ticker_swing_signal_daily"
SOURCE_CLASSIFICATIONS = {
    SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
TARGET_WINDOW = "daily"
TARGET_ENTITY_TYPE = "TICKER"
SIGNAL_FAMILY = "MA_BREAK_STATUS"
SIGNAL_NAME = "MA_BREAK_STATUS"


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


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _select_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in column_names:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


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


def _load_target_coverage(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT
            c.run_id,
            c.ecosystem_id,
            c.signal_date,
            c.taxonomy_version_id,
            c.window_code,
            c.entity_id,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code = ?
          AND e.entity_type = ?
        ORDER BY e.entity_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            TARGET_WINDOW,
            TARGET_ENTITY_TYPE,
        ),
    ).fetchall()
    if not rows:
        raise ValueError(
            f"Missing eligible {TARGET_ENTITY_TYPE}/{TARGET_WINDOW} coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _load_latest_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_tickers: set[str],
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    columns = _column_names(conn, SOURCE_TABLE)
    required = {"signal_date", "ticker", "close", "ema20", "signal_version"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing)}")

    taxonomy_filter = "AND taxonomy_version = ?" if "taxonomy_version" in columns else ""
    ticker_clause = ", ".join("?" for _ in sorted(eligible_tickers))
    query = f"""
        SELECT
            ticker,
            signal_date,
            close,
            ema20,
            signal_version,
            {_select_expr(columns, ('run_id',), 'source_run_id')}
        FROM {SOURCE_TABLE}
        WHERE signal_date = ?
          {taxonomy_filter}
          AND ticker IN ({ticker_clause})
        ORDER BY ticker
    """
    params: list[object] = [signal_date]
    if "taxonomy_version" in columns:
        params.append(taxonomy_version_code)
    params.extend(sorted(eligible_tickers))
    return conn.execute(query, tuple(params)).fetchall()


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _map_direction_and_status(signal_value: str | None) -> tuple[str, str]:
    normalized = _normalize_text(signal_value)
    if normalized is None:
        return "UNKNOWN", "UNKNOWN"
    if normalized == "OK":
        return "NEUTRAL", "ACTIVE"
    if normalized == "INSUFFICIENT_DATA":
        return "UNKNOWN", "UNKNOWN"
    if "BREAK" in normalized or "WARNING" in normalized:
        return "DOWN", "ACTIVE"
    return "UNKNOWN", "UNKNOWN"


def _build_observation_rows(
    *,
    run_row: sqlite3.Row,
    algorithm_rows: list[dict[str, object]],
    coverage_by_ticker: dict[str, sqlite3.Row],
    source_identity_by_ticker: dict[str, dict[str, str | None]],
    warnings: list[str],
) -> tuple[list[dict[str, object]], int, int]:
    observation_rows: list[dict[str, object]] = []
    mapped_count = 0
    skipped_count = 0

    for algorithm_row in algorithm_rows:
        ticker = str(algorithm_row.get("ticker") or "")
        if not ticker:
            warnings.append("Skipped MA break algorithm row with missing ticker")
            skipped_count += 1
            continue
        coverage_row = coverage_by_ticker.get(ticker)
        if coverage_row is None:
            warnings.append(f"Skipped MA break algorithm row without eligible daily coverage: {ticker}")
            skipped_count += 1
            continue

        signal_value = _normalize_text(algorithm_row.get("ma_break_status"))
        signal_direction, signal_status = _map_direction_and_status(signal_value)
        identity = source_identity_by_ticker.get(ticker, {})
        observed_date = _normalize_text(algorithm_row.get("as_of_date")) or str(run_row["signal_date"])
        source_run_id = _normalize_text(identity.get("source_run_id")) or _normalize_text(identity.get("signal_version"))

        observation_rows.append(
            {
                "run_id": str(run_row["run_id"]),
                "ecosystem_id": int(run_row["ecosystem_id"]),
                "signal_date": str(run_row["signal_date"]),
                "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
                "window_code": TARGET_WINDOW,
                "entity_id": int(coverage_row["entity_id"]),
                "signal_name": SIGNAL_NAME,
                "signal_family": SIGNAL_FAMILY,
                "signal_direction": signal_direction,
                "signal_value": signal_value or "UNKNOWN",
                "observed_date": observed_date,
                "source_table": SOURCE_TABLE,
                "source_run_id": source_run_id,
                "source_event_id": f"ma_break_status:{ticker}:{observed_date}:{SIGNAL_NAME}",
                "signal_status": signal_status,
            }
        )
        mapped_count += 1

    return observation_rows, mapped_count, skipped_count


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> None:
    existing_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_signal_observation
        WHERE run_id = ?
          AND signal_family = ?
        """,
        (run_id, SIGNAL_FAMILY),
    ).fetchone()[0]
    if existing_count and not replace_existing:
        raise ValueError(f"MA_BREAK_STATUS signal rows already exist for run_id '{run_id}'")
    if not existing_count:
        return

    relevance_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_signal_relevance sr
        JOIN eco_signal_observation so
          ON so.signal_observation_id = sr.signal_observation_id
        WHERE so.run_id = ?
          AND so.signal_family = ?
        """,
        (run_id, SIGNAL_FAMILY),
    ).fetchone()[0]
    if relevance_count:
        raise ValueError(
            f"Cannot replace MA_BREAK_STATUS signal rows for run_id '{run_id}' because relevance rows exist"
        )

    conn.execute(
        """
        DELETE FROM eco_signal_observation
        WHERE run_id = ?
          AND signal_family = ?
        """,
        (run_id, SIGNAL_FAMILY),
    )


def build_canonical_v3_ma_break_status(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        coverage_by_ticker = {str(row["entity_code"]): row for row in coverage_rows}
        eligible_tickers = set(coverage_by_ticker)
        warnings: list[str] = []
        limitations = [
            "uses existing swing_ma_break_status algorithm",
            "signal_family is MA_BREAK_STATUS, not eco_entity_event MA_BREAK",
            "no event rows are created",
            "no signal relevance rows are created",
            "no metric rows are created",
            "daily/TICKER only",
            "group MA break/status out of scope",
        ]

        latest_rows = _load_latest_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_tickers=eligible_tickers,
        )
        source_identity_by_ticker: dict[str, dict[str, str | None]] = {
            str(row["ticker"]): {
                "source_run_id": _normalize_text(row["source_run_id"]),
                "signal_version": _normalize_text(row["signal_version"]),
            }
            for row in latest_rows
        }
        latest_row_dicts = [{key: row[key] for key in row.keys()} for row in latest_rows]
        source_tickers = {str(row["ticker"]) for row in latest_rows}
        missing_source_tickers = sorted(eligible_tickers - source_tickers)

        history_rows: list[dict[str, object]] = []
        algorithm_rows: list[dict[str, object]] = []
        latest_rows_by_signal_version: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in latest_row_dicts:
            signal_version = _normalize_text(row.get("signal_version"))
            if signal_version is None:
                warnings.append(f"Skipped source row without signal_version for ticker '{row.get('ticker')}'")
                continue
            latest_rows_by_signal_version[signal_version].append(row)

        skipped_count = 0
        for signal_version, grouped_latest_rows in latest_rows_by_signal_version.items():
            tickers = [str(row["ticker"]) for row in grouped_latest_rows]
            grouped_history = load_ticker_ma_history_rows(
                conn,
                tickers=tickers,
                as_of_date=str(run_row["signal_date"]),
                signal_version=signal_version,
                taxonomy_version=str(run_row["version_code"]),
            )
            history_rows.extend(grouped_history)
            grouped_algorithm_rows = build_swing_ma_break_status_rows(
                latest_rows=grouped_latest_rows,
                history_rows=grouped_history,
                as_of_date=str(run_row["signal_date"]),
            )
            algorithm_rows.extend(grouped_algorithm_rows)

        expected_algorithm_tickers = {
            str(row["ticker"])
            for grouped_rows in latest_rows_by_signal_version.values()
            for row in grouped_rows
        }
        skipped_count += len(source_tickers) - len(expected_algorithm_tickers)

        observation_rows, mapped_count, algorithm_skipped_count = _build_observation_rows(
            run_row=run_row,
            algorithm_rows=algorithm_rows,
            coverage_by_ticker=coverage_by_ticker,
            source_identity_by_ticker=source_identity_by_ticker,
            warnings=warnings,
        )
        total_skipped = skipped_count + algorithm_skipped_count
        signal_name_counts = dict(sorted(Counter(row["signal_name"] for row in observation_rows).items()))
        signal_value_counts = dict(
            sorted(Counter(f"{row['signal_name']}|{row['signal_value']}" for row in observation_rows).items())
        )
        signal_direction_counts = dict(sorted(Counter(row["signal_direction"] for row in observation_rows).items()))

        conn.execute("BEGIN")
        _ensure_replace_allowed(conn, run_id=str(run_row["run_id"]), replace_existing=replace_existing)
        conn.executemany(
            """
            INSERT INTO eco_signal_observation (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                signal_name, signal_family, signal_direction, signal_value, observed_date,
                source_table, source_run_id, source_event_id, signal_status
            ) VALUES (
                :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code, :entity_id,
                :signal_name, :signal_family, :signal_direction, :signal_value, :observed_date,
                :source_table, :source_run_id, :source_event_id, :signal_status
            )
            """,
            observation_rows,
        )
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "source_classifications": dict(SOURCE_CLASSIFICATIONS),
            "selected_ticker_entity_count": len(coverage_by_ticker),
            "source_rows_read": len(latest_rows),
            "history_rows_read": len(history_rows),
            "history_policy": "load all dc_ticker_swing_signal_daily rows <= signal_date for eligible tickers grouped by signal_version",
            "algorithm_rows_produced": len(algorithm_rows),
            "source_rows_mapped": mapped_count,
            "source_rows_skipped": total_skipped,
            "missing_source_tickers": missing_source_tickers,
            "signal_observations_inserted": len(observation_rows),
            "signal_name_counts": signal_name_counts,
            "signal_value_counts": signal_value_counts,
            "signal_direction_counts": signal_direction_counts,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": limitations,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
