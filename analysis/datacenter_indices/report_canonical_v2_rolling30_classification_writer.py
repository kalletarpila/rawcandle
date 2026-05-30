from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .rolling30_watchlist_classifier import (
    classify_rolling_30_buy_row,
    classify_rolling_30_exit_row,
)


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
    params: list[object] = [signal_date, taxonomy_version, "rolling30"]
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
        "last_price_data_status": row.get("price_data_status"),
        "all_price_rows_missing": bool(row.get("all_price_rows_missing")),
        "last_ticker_trend_state": row.get("trend_state"),
        "current_watchlist_status": row.get("current_watchlist_status"),
        "window_watchlist_status": row.get("window_watchlist_status"),
        "breakout_days": row.get("breakout_days"),
        "pullback_days": row.get("pullback_days"),
        "exit_risk_days": row.get("exit_risk_days"),
        "high_exit_risk_days": row.get("high_exit_risk_days"),
        "medium_exit_risk_days": row.get("medium_exit_risk_days"),
        "last_exit_risk_severity": row.get("exit_risk_severity"),
        "last_latest_bos_event_type": row.get("latest_bos_event_type"),
        "last_latest_bos_freshness": row.get("latest_bos_freshness"),
        "last_latest_reset_reason": row.get("latest_reset_reason"),
        "last_latest_reset_freshness": row.get("latest_reset_freshness"),
        "latest_bearish_relevance_class": row.get("latest_bearish_relevance_class"),
        "last_subindustry_overheat_risk_level": row.get("subindustry_overheat_risk_level"),
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
              AND horizon = 'rolling30'
              AND classification_type IN ('rolling30_buy', 'rolling30_exit')
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
          AND horizon = 'rolling30'
          AND classification_type IN ('rolling30_buy', 'rolling30_exit')
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


def write_report_rolling30_buy_exit_classification_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    classification_version: str = "REPORT_ROLLING30_BUY_EXIT_CLASSIFIER_V2_1",
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
    buy_count = 0
    exit_count = 0
    for row in window_rows:
        classifier_row = _classifier_row(row)
        buy_result = classify_rolling_30_buy_row(classifier_row)
        output_rows.append(
            {
                "signal_date": signal_date,
                "taxonomy_version": taxonomy_version,
                "market": row.get("market") if row.get("market") is not None else market,
                "ticker": row.get("ticker"),
                "horizon": "rolling30",
                "classification_type": "rolling30_buy",
                "classification_state": buy_result.rolling_30_buy_state,
                "primary_reason": buy_result.primary_reason,
                "blocking_reason": buy_result.blocking_reason or None,
                "risk_reason": None,
                "next_action": None,
                "classification_status": "OK",
                "classification_version": classification_version,
                "run_id": run_id,
                "created_at_utc": created_at_value,
            }
        )
        buy_count += 1

        exit_result = classify_rolling_30_exit_row(classifier_row)
        output_rows.append(
            {
                "signal_date": signal_date,
                "taxonomy_version": taxonomy_version,
                "market": row.get("market") if row.get("market") is not None else market,
                "ticker": row.get("ticker"),
                "horizon": "rolling30",
                "classification_type": "rolling30_exit",
                "classification_state": exit_result.rolling_30_exit_state,
                "primary_reason": exit_result.primary_reason,
                "blocking_reason": None,
                "risk_reason": exit_result.risk_reason or None,
                "next_action": None,
                "classification_status": "OK",
                "classification_version": classification_version,
                "run_id": run_id,
                "created_at_utc": created_at_value,
            }
        )
        exit_count += 1

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
        "buy_classification_rows_written": buy_count,
        "exit_classification_rows_written": exit_count,
        "classification_rows_skipped": 0,
        "total_rows_written": len(output_rows),
    }
