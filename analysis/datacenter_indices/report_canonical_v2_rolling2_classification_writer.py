from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .rolling2_sell_pressure_classifier import classify_rolling_2_sell_pressure_row


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _ensure_run_exists(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM dc_report_run_v2 WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"dc_report_run_v2 row not found for run_id={run_id}")


def _load_window_context_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = ?"]
    params: list[object] = [signal_date, taxonomy_version, "rolling2"]
    if market is not None:
        where_clauses.append("market = ?")
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_report_context_window_v2
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker ASC
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _classifier_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "ticker": row.get("ticker"),
        "current_watchlist_status": row.get("current_watchlist_status"),
        "window_watchlist_status": row.get("window_watchlist_status"),
        "exit_risk_days": row.get("exit_risk_days"),
        "high_exit_risk_days": row.get("high_exit_risk_days"),
        "medium_exit_risk_days": row.get("medium_exit_risk_days"),
        "last_exit_risk_severity": row.get("exit_risk_severity"),
        "last_exit_reason": row.get("latest_exit_reason"),
        "last_ticker_trend_state": row.get("trend_state"),
        "latest_bearish_relevance_class": row.get("latest_bearish_relevance_class"),
        "last_latest_bos_event_type": row.get("latest_bos_event_type"),
        "last_latest_bos_freshness": row.get("latest_bos_freshness"),
        "last_latest_reset_reason": row.get("latest_reset_reason"),
        "last_latest_reset_freshness": row.get("latest_reset_freshness"),
        "last_latest_structure_label": row.get("latest_structure_label"),
        "last_distance_to_ema20_pct": row.get("distance_to_ema20_pct"),
        "last_price_data_status": row.get("price_data_status"),
        "all_price_rows_missing": bool(row.get("all_price_rows_missing")),
    }


def _delete_existing_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
) -> None:
    if market is None:
        conn.execute(
            """
            DELETE FROM dc_report_classification_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND horizon = 'rolling2'
              AND classification_type = 'rolling2_sell_pressure'
            """,
            (signal_date, taxonomy_version),
        )
        return
    conn.execute(
        """
        DELETE FROM dc_report_classification_v2
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND market = ?
          AND horizon = 'rolling2'
          AND classification_type = 'rolling2_sell_pressure'
        """,
        (signal_date, taxonomy_version, market),
    )


def _write_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            classification_status,
            classification_version,
            run_id,
            created_at_utc
        ) VALUES (
            :signal_date,
            :taxonomy_version,
            :market,
            :ticker,
            :horizon,
            :classification_type,
            :classification_state,
            :primary_reason,
            :blocking_reason,
            :risk_reason,
            :next_action,
            :classification_status,
            :classification_version,
            :run_id,
            :created_at_utc
        )
        """,
        rows,
    )


def write_report_rolling2_sell_pressure_classification_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    classification_version: str = "REPORT_ROLLING2_SELL_PRESSURE_CLASSIFIER_V2_1",
    created_at_utc: str | None = None,
) -> dict[str, int]:
    conn.row_factory = sqlite3.Row
    _ensure_run_exists(conn, run_id)
    created_at_value = created_at_utc or _utc_now_iso()
    window_rows = _load_window_context_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
    )

    output_rows: list[dict[str, object]] = []
    for row in window_rows:
        result = classify_rolling_2_sell_pressure_row(_classifier_row(row))
        output_rows.append(
            {
                "signal_date": signal_date,
                "taxonomy_version": taxonomy_version,
                "market": row.get("market") if row.get("market") is not None else market,
                "ticker": row.get("ticker"),
                "horizon": "rolling2",
                "classification_type": "rolling2_sell_pressure",
                "classification_state": result.rolling_2_sell_pressure_state,
                "primary_reason": result.primary_reason,
                "blocking_reason": None,
                "risk_reason": result.risk_reason or None,
                "next_action": result.next_action,
                "classification_status": "OK",
                "classification_version": classification_version,
                "run_id": run_id,
                "created_at_utc": created_at_value,
            }
        )

    _delete_existing_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
    )
    _write_rows(conn, output_rows)
    conn.commit()

    return {
        "window_context_rows_read": len(window_rows),
        "classification_rows_written": len(output_rows),
        "classification_rows_skipped": 0,
        "total_rows_written": len(output_rows),
    }
