from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_PRICE"}
FRESH_SIGNAL_STATES = {"FRESH", "RECENT", "CURRENT"}
SEVERE_EXIT_SEVERITIES = {"CRITICAL", "EXTREME"}
HIGH_EXIT_SEVERITIES = {"HIGH", "CRITICAL", "EXTREME"}


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


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _float_value(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_fresh_or_recent(value: object | None) -> bool:
    return _normalize_text(value).upper() in FRESH_SIGNAL_STATES


def _has_reason_token(value: object | None, token: str) -> bool:
    reason_text = _normalize_text(value).lower()
    return token.lower() in reason_text


def _is_severe_exit_severity(value: object | None) -> bool:
    return _normalize_text(value).upper() in SEVERE_EXIT_SEVERITIES


def _is_high_or_worse_exit_severity(value: object | None) -> bool:
    return _normalize_text(value).upper() in HIGH_EXIT_SEVERITIES


def _has_negative_ema20_context(value: object | None) -> bool:
    distance = _float_value(value)
    return distance is not None and distance < 0


def _has_slightly_negative_ema20_context(value: object | None) -> bool:
    distance = _float_value(value)
    return distance is not None and distance < 0 and distance >= -0.03


def _is_near_pullback_zone(row: dict[str, object]) -> bool:
    distance = _float_value(row.get("distance_to_ema20_pct"))
    return distance is not None and abs(distance) <= 0.03


def _classify_daily_trigger_row(row: dict[str, object]) -> tuple[str, str, str | None, str | None]:
    ticker = _normalize_text(row.get("ticker"))
    if not ticker:
        return ("INSUFFICIENT_DATA", "MISSING_TICKER_CONTEXT", None, "WAIT_FOR_DATA")

    current_watchlist_status = _normalize_text(row.get("current_watchlist_status")).upper()
    if current_watchlist_status in WATCHLIST_MISSING_PRICE_STATUSES:
        return ("INSUFFICIENT_DATA", "MISSING_PRICE_CONTEXT", None, "WAIT_FOR_DATA")

    trend_state = _normalize_text(row.get("trend_state")).upper()
    exit_risk_severity = _normalize_text(row.get("exit_risk_severity")).upper()
    latest_structure_label = _normalize_text(row.get("latest_structure_label")).upper()
    latest_exit_reason = row.get("latest_exit_reason")

    fresh_bos_down = (
        _normalize_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN"
        and _is_fresh_or_recent(row.get("latest_bos_freshness"))
    )
    stale_bos_down = (
        _normalize_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN"
        and not _is_fresh_or_recent(row.get("latest_bos_freshness"))
    )
    fresh_reset = bool(_normalize_text(row.get("latest_reset_reason"))) and _is_fresh_or_recent(
        row.get("latest_reset_freshness")
    )

    has_pullback_signal = int(row.get("pullback_signal") or 0) == 1
    has_breakout_signal = int(row.get("breakout_signal") or 0) == 1
    has_exit_risk_signal = int(row.get("exit_risk_signal") or 0) == 1
    has_bullish_signal = False
    has_bearish_signal = False
    relevant_bullish = False
    weak_bullish = False
    relevant_bearish = False
    weak_bearish = False

    high_exit_risk = current_watchlist_status == "HIGH_EXIT_RISK" or _is_high_or_worse_exit_severity(
        exit_risk_severity
    )
    bullish_evidence = has_pullback_signal or has_bullish_signal or _is_near_pullback_zone(row)
    has_ll_structure = latest_structure_label == "LL"
    has_close_below_ema20 = _has_reason_token(latest_exit_reason, "close_below_ema20")
    has_return_10d_lt_minus_8pct = _has_reason_token(latest_exit_reason, "return_10d_lt_minus_8pct")
    has_trim_watch_close_below_ma10 = _has_reason_token(latest_exit_reason, "trim_watch_close_below_ma10")
    has_structure_label_ll_reason = _has_reason_token(latest_exit_reason, "latest_structure_label_ll")
    has_price_break_evidence = (
        has_close_below_ema20
        or has_return_10d_lt_minus_8pct
        or has_trim_watch_close_below_ma10
        or _has_negative_ema20_context(row.get("distance_to_ema20_pct"))
    )
    has_structural_break_evidence = (
        has_ll_structure
        or trend_state == "DOWN"
        or fresh_bos_down
        or fresh_reset
        or has_structure_label_ll_reason
    )
    buy_hard_blocker = (
        trend_state == "DOWN"
        or fresh_bos_down
        or fresh_reset
        or high_exit_risk
        or relevant_bearish
    )

    stop_reason = None
    if _is_severe_exit_severity(exit_risk_severity) and has_exit_risk_signal:
        stop_reason = "CRITICAL_OR_EXTREME_EXIT_SEVERITY"
    elif exit_risk_severity == "HIGH" and has_price_break_evidence and has_structural_break_evidence:
        stop_reason = "PRICE_BREAK_WITH_STRUCTURAL_BREAKDOWN"
    elif fresh_bos_down and fresh_reset and has_price_break_evidence:
        stop_reason = "FRESH_BOS_DOWN_AND_RESET_WITH_PRICE_BREAK"
    elif relevant_bearish and high_exit_risk and has_price_break_evidence:
        stop_reason = "RELEVANT_BEARISH_CONTEXT_WITH_HIGH_EXIT_RISK_AND_PRICE_BREAK"
    if stop_reason:
        return ("STOP_TRIGGER", "CONFIRMED_DAILY_STOP_TRIGGER", stop_reason, "CHECK_STOP_OR_EXIT")

    sell_reason = None
    if has_exit_risk_signal and exit_risk_severity in {"MEDIUM", "HIGH"}:
        sell_reason = (
            "HIGH_EXIT_RISK_WITHOUT_FULL_STOP_CONFIRMATION"
            if exit_risk_severity == "HIGH"
            else "EXIT_RISK_SIGNAL_MEDIUM_OR_HIGH"
        )
    elif has_close_below_ema20:
        sell_reason = "CLOSE_BELOW_EMA20"
    elif has_return_10d_lt_minus_8pct:
        sell_reason = "RETURN_10D_LT_MINUS_8PCT"
    elif has_trim_watch_close_below_ma10:
        sell_reason = "TRIM_WATCH_CLOSE_BELOW_MA10"
    elif _has_reason_token(latest_exit_reason, "subindustry_exit_zone"):
        sell_reason = "SUBINDUSTRY_EXIT_ZONE"
    elif has_structure_label_ll_reason or has_ll_structure or fresh_reset:
        sell_reason = "STRUCTURAL_WARNING_WITHOUT_PRICE_BREAK"
    elif fresh_bos_down:
        sell_reason = "FRESH_BOS_DOWN"
    elif relevant_bearish:
        sell_reason = "RELEVANT_BEARISH_CONTEXT"
    elif has_bearish_signal and trend_state != "UP":
        sell_reason = "BEARISH_DAILY_SIGNAL"
    elif trend_state == "DOWN" and _has_negative_ema20_context(row.get("distance_to_ema20_pct")):
        sell_reason = "DOWN_TREND_BELOW_EMA20"
    if sell_reason:
        return ("SELL_TRIGGER", "DAILY_SELL_TRIGGER", sell_reason, "REVIEW_SELL_OR_TIGHTEN_STOP")

    exit_watch_reason = None
    if has_exit_risk_signal:
        exit_watch_reason = "MILD_EXIT_RISK_SIGNAL"
    elif weak_bearish:
        exit_watch_reason = "WEAK_BEARISH_CONTEXT"
    elif stale_bos_down and not (relevant_bullish and bullish_evidence and trend_state != "DOWN"):
        exit_watch_reason = "STALE_BOS_DOWN"
    elif _has_slightly_negative_ema20_context(row.get("distance_to_ema20_pct")):
        exit_watch_reason = "SLIGHTLY_BELOW_EMA20"
    elif current_watchlist_status in {"MEDIUM_EXIT_RISK", "GROUP_RISK"}:
        exit_watch_reason = current_watchlist_status
    if exit_watch_reason:
        return ("EXIT_WATCH", "DAILY_EXIT_WATCH", "MILD_OR_UNCONFIRMED_EXIT_PRESSURE", "MONITOR_NEXT_SESSION")

    if relevant_bullish and bullish_evidence and not buy_hard_blocker and trend_state != "DOWN":
        primary_reason = (
            "PULLBACK_TRIGGER_WITH_RELEVANT_BULLISH_CONTEXT"
            if has_pullback_signal or _is_near_pullback_zone(row)
            else "BULLISH_DAILY_TRIGGER_WITH_CONTEXT"
        )
        return ("BUY_TRIGGER", primary_reason, None, "REVIEW_WITH_ROLLING_CONTEXT")

    if (has_pullback_signal or has_breakout_signal or has_bullish_signal or weak_bullish or _is_near_pullback_zone(row)) and not buy_hard_blocker:
        return ("BUY_WATCH", "BULLISH_SETUP_NEEDS_CONFIRMATION", None, "MONITOR_FOR_DAILY_CONFIRMATION")

    return ("NO_TRIGGER", "NO_MEANINGFUL_DAILY_TRIGGER", None, "NONE")


def _load_daily_context_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None:
        where_clauses.append("market = ?")
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_report_context_daily_v2
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker ASC
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


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
              AND horizon = 'daily'
              AND classification_type = 'daily_trigger'
            """,
            (signal_date, taxonomy_version),
        )
    else:
        conn.execute(
            """
            DELETE FROM dc_report_classification_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND market = ?
              AND horizon = 'daily'
              AND classification_type = 'daily_trigger'
            """,
            (signal_date, taxonomy_version, market),
        )


def _write_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
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


def write_report_daily_trigger_classification_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    classification_version: str = "REPORT_DAILY_TRIGGER_CLASSIFIER_V2_1",
    created_at_utc: str | None = None,
) -> dict[str, int]:
    conn.row_factory = sqlite3.Row
    _ensure_run_exists(conn, run_id)
    created_at_value = created_at_utc or _utc_now_iso()
    daily_rows = _load_daily_context_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
    )

    output_rows: list[dict[str, object]] = []
    for row in daily_rows:
        classification_state, primary_reason, blocking_reason, next_action = _classify_daily_trigger_row(row)
        output_rows.append(
            {
                "signal_date": signal_date,
                "taxonomy_version": taxonomy_version,
                "market": row.get("market") if row.get("market") is not None else market,
                "ticker": row.get("ticker"),
                "horizon": "daily",
                "classification_type": "daily_trigger",
                "classification_state": classification_state,
                "primary_reason": primary_reason,
                "blocking_reason": blocking_reason,
                "risk_reason": None,
                "next_action": next_action,
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
        "daily_context_rows_read": len(daily_rows),
        "classification_rows_written": len(output_rows),
        "classification_rows_skipped": 0,
        "total_rows_written": len(output_rows),
    }
