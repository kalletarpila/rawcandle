from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .technical_signal_relevance import TechnicalSignalRelevanceConfig
from .technical_signal_relevance_persistence import read_relevance_records_for_run
from .technical_signal_relevance_sources import (
    _resolve_ohlcv_connection,
    _table_exists,
    build_bar_index,
)


NO_RELEVANCE_ROWS_FOR_RUN = "NO_RELEVANCE_ROWS_FOR_RUN"
ROW_NOT_MISSING_BAR_INDEX = "ROW_NOT_MISSING_BAR_INDEX"
MISSING_OHLCV_SOURCE = "MISSING_OHLCV_SOURCE"
NO_OHLCV_ROWS_FOR_TICKER = "NO_OHLCV_ROWS_FOR_TICKER"
OBSERVATION_DATE_NOT_IN_BAR_INDEX = "OBSERVATION_DATE_NOT_IN_BAR_INDEX"
LATEST_BOS_CONFIRMED_DATE_NOT_IN_BAR_INDEX = "LATEST_BOS_CONFIRMED_DATE_NOT_IN_BAR_INDEX"
LATEST_RESET_CONFIRMED_DATE_NOT_IN_BAR_INDEX = "LATEST_RESET_CONFIRMED_DATE_NOT_IN_BAR_INDEX"
LATEST_PIVOT_CONFIRMED_DATE_NOT_IN_BAR_INDEX = "LATEST_PIVOT_CONFIRMED_DATE_NOT_IN_BAR_INDEX"
NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT = "NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT"
EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT = "EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT"
UNKNOWN_BAR_INDEX_MISSING_REASON = "UNKNOWN_BAR_INDEX_MISSING_REASON"

ALL_AUDIT_CATEGORIES = (
    NO_RELEVANCE_ROWS_FOR_RUN,
    ROW_NOT_MISSING_BAR_INDEX,
    MISSING_OHLCV_SOURCE,
    NO_OHLCV_ROWS_FOR_TICKER,
    OBSERVATION_DATE_NOT_IN_BAR_INDEX,
    LATEST_BOS_CONFIRMED_DATE_NOT_IN_BAR_INDEX,
    LATEST_RESET_CONFIRMED_DATE_NOT_IN_BAR_INDEX,
    LATEST_PIVOT_CONFIRMED_DATE_NOT_IN_BAR_INDEX,
    NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT,
    EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT,
    UNKNOWN_BAR_INDEX_MISSING_REASON,
)


@dataclass(frozen=True)
class TechnicalSignalBarIndexAuditRow:
    ticker: str
    timeframe: str
    signal_date: str
    signal_name: str
    relevance_class: str
    relevance_reason: str
    latest_bos_direction: str | None
    bars_since_latest_bos: int | None
    bars_since_latest_reset: int | None
    near_latest_pivot: int
    rule_trace: str | None
    diagnostic_category: str


@dataclass(frozen=True)
class TechnicalSignalBarIndexAuditSummary:
    run_id: str
    rows_total: int
    rows_missing_bar_index: int
    rows_with_bar_index_available: int
    category_counts: dict[str, int]
    sample_rows_by_category: dict[str, list[TechnicalSignalBarIndexAuditRow]]


def _load_run_config(conn: sqlite3.Connection, run_id: str) -> TechnicalSignalRelevanceConfig:
    row = conn.execute(
        """
        SELECT config_snapshot_json
        FROM technical_signal_relevance_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return TechnicalSignalRelevanceConfig()
    config_snapshot = json.loads(str(row[0]))
    return TechnicalSignalRelevanceConfig(
        near_pivot_window_bars=int(
            config_snapshot.get("near_pivot_window_bars", TechnicalSignalRelevanceConfig().near_pivot_window_bars)
        ),
        recent_bos_window_bars=int(
            config_snapshot.get("recent_bos_window_bars", TechnicalSignalRelevanceConfig().recent_bos_window_bars)
        ),
        recent_reset_window_bars=int(
            config_snapshot.get(
                "recent_reset_window_bars",
                TechnicalSignalRelevanceConfig().recent_reset_window_bars,
            )
        ),
        near_bos_level_pct=float(
            config_snapshot.get("near_bos_level_pct", TechnicalSignalRelevanceConfig().near_bos_level_pct)
        ),
        rule_version=str(config_snapshot.get("rule_version", TechnicalSignalRelevanceConfig().rule_version)),
        mapping_version=str(
            config_snapshot.get("mapping_version", TechnicalSignalRelevanceConfig().mapping_version)
        ),
        reason_version=str(
            config_snapshot.get("reason_version", TechnicalSignalRelevanceConfig().reason_version)
        ),
    )


def _parse_rule_trace(rule_trace: str | None) -> tuple[list[str], dict[str, str]]:
    if not rule_trace:
        return [], {}
    try:
        entries = [str(item) for item in json.loads(rule_trace)]
    except json.JSONDecodeError:
        entries = [str(rule_trace)]
    parsed = {}
    for entry in entries:
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        parsed[key] = value
    return entries, parsed


def _resolve_audit_ohlcv_connection(
    conn: sqlite3.Connection,
    osakedata_conn: sqlite3.Connection | None,
) -> tuple[sqlite3.Connection | None, bool]:
    if osakedata_conn is not None:
        return osakedata_conn, False
    return _resolve_ohlcv_connection(conn)


def _fetch_confirmed_date_for_event_id(
    conn: sqlite3.Connection,
    event_id: str,
    ticker: str,
    expected_event_type: str | None,
) -> str | None:
    if not _table_exists(conn, "stock_dow_structure_events"):
        return None
    where_clause = "id = ? AND ticker = ?"
    params: list[object] = [event_id, ticker]
    if expected_event_type is not None:
        where_clause += " AND event_type = ?"
        params.append(expected_event_type)
    row = conn.execute(
        f"""
        SELECT confirmed_as_of_date
        FROM stock_dow_structure_events
        WHERE {where_clause}
        """,
        tuple(params),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _make_sample_row(row: dict[str, object], diagnostic_category: str) -> TechnicalSignalBarIndexAuditRow:
    return TechnicalSignalBarIndexAuditRow(
        ticker=str(row["ticker"]),
        timeframe=str(row["timeframe"]),
        signal_date=str(row["signal_date"]),
        signal_name=str(row["signal_name"]),
        relevance_class=str(row["relevance_class"]),
        relevance_reason=str(row["relevance_reason"]),
        latest_bos_direction=None if row["latest_bos_direction"] is None else str(row["latest_bos_direction"]),
        bars_since_latest_bos=None if row["bars_since_latest_bos"] is None else int(row["bars_since_latest_bos"]),
        bars_since_latest_reset=(
            None if row["bars_since_latest_reset"] is None else int(row["bars_since_latest_reset"])
        ),
        near_latest_pivot=int(row["near_latest_pivot"]),
        rule_trace=None if row["rule_trace"] is None else str(row["rule_trace"]),
        diagnostic_category=diagnostic_category,
    )


def _classify_missing_bar_index_reason(
    conn: sqlite3.Connection,
    row: dict[str, object],
    parsed_trace: dict[str, str],
    bar_dates: tuple[str, ...],
) -> str:
    observation_confirmed_as_of_date = str(row["signal_confirmed_as_of_date"])
    if observation_confirmed_as_of_date not in bar_dates:
        return OBSERVATION_DATE_NOT_IN_BAR_INDEX

    latest_bos_event_id = parsed_trace.get("latest_bos_event_id")
    latest_reset_event_id = parsed_trace.get("latest_reset_event_id")
    latest_pivot_event_id = parsed_trace.get("latest_pivot_event_id")

    trace_has_all_id_keys = {
        "latest_bos_event_id",
        "latest_reset_event_id",
        "latest_pivot_event_id",
    }.issubset(parsed_trace.keys())
    if not trace_has_all_id_keys:
        return EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT

    if latest_bos_event_id not in {None, "null"}:
        confirmed_date = _fetch_confirmed_date_for_event_id(
            conn,
            latest_bos_event_id,
            str(row["ticker"]),
            None,
        )
        if confirmed_date is None:
            return EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT
        if confirmed_date not in bar_dates:
            return LATEST_BOS_CONFIRMED_DATE_NOT_IN_BAR_INDEX

    if latest_reset_event_id not in {None, "null"}:
        confirmed_date = _fetch_confirmed_date_for_event_id(
            conn,
            latest_reset_event_id,
            str(row["ticker"]),
            "RESET",
        )
        if confirmed_date is None:
            return EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT
        if confirmed_date not in bar_dates:
            return LATEST_RESET_CONFIRMED_DATE_NOT_IN_BAR_INDEX

    if latest_pivot_event_id not in {None, "null"}:
        confirmed_date = _fetch_confirmed_date_for_event_id(
            conn,
            latest_pivot_event_id,
            str(row["ticker"]),
            None,
        )
        if confirmed_date is None:
            return EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT
        if confirmed_date not in bar_dates:
            return LATEST_PIVOT_CONFIRMED_DATE_NOT_IN_BAR_INDEX

    if latest_bos_event_id == "null" and latest_reset_event_id == "null" and latest_pivot_event_id == "null":
        return NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT

    return UNKNOWN_BAR_INDEX_MISSING_REASON


def audit_missing_bar_index_for_run(
    conn: sqlite3.Connection,
    run_id: str,
    osakedata_conn: sqlite3.Connection | None = None,
    limit_samples: int = 10,
) -> TechnicalSignalBarIndexAuditSummary:
    rows = read_relevance_records_for_run(conn, run_id)
    category_counts = {category: 0 for category in ALL_AUDIT_CATEGORIES}
    sample_rows_by_category = {category: [] for category in ALL_AUDIT_CATEGORIES}

    if not rows:
        category_counts[NO_RELEVANCE_ROWS_FOR_RUN] = 1
        return TechnicalSignalBarIndexAuditSummary(
            run_id=run_id,
            rows_total=0,
            rows_missing_bar_index=0,
            rows_with_bar_index_available=0,
            category_counts=category_counts,
            sample_rows_by_category=sample_rows_by_category,
        )

    config = _load_run_config(conn, run_id)
    lookback_bars = max(
        config.near_pivot_window_bars,
        config.recent_bos_window_bars,
        config.recent_reset_window_bars,
    ) + 5
    resolved_ohlcv_conn, should_close_ohlcv_conn = _resolve_audit_ohlcv_connection(conn, osakedata_conn)
    has_ohlcv_source = (
        resolved_ohlcv_conn is not None and _table_exists(resolved_ohlcv_conn, "osakedata")
    )
    bar_dates_by_ticker: dict[str, tuple[str, ...]] = {}
    date_span_by_ticker: dict[str, tuple[str, str]] = {}
    for row in rows:
        ticker = str(row["ticker"])
        signal_date = str(row["signal_date"])
        confirmed_as_of_date = str(row["signal_confirmed_as_of_date"])
        if ticker not in date_span_by_ticker:
            date_span_by_ticker[ticker] = (signal_date, confirmed_as_of_date)
            continue
        current_start_date, current_end_date = date_span_by_ticker[ticker]
        date_span_by_ticker[ticker] = (
            min(current_start_date, signal_date, confirmed_as_of_date),
            max(current_end_date, signal_date, confirmed_as_of_date),
        )

    rows_missing_bar_index = 0
    for row in rows:
        _, parsed_trace = _parse_rule_trace(None if row["rule_trace"] is None else str(row["rule_trace"]))
        is_missing_bar_index = parsed_trace.get("missing_bar_index") == "true"
        if not is_missing_bar_index:
            category_counts[ROW_NOT_MISSING_BAR_INDEX] += 1
            continue

        rows_missing_bar_index += 1
        ticker = str(row["ticker"])
        if not has_ohlcv_source:
            category = MISSING_OHLCV_SOURCE
        else:
            if ticker not in bar_dates_by_ticker:
                span_start_date, span_end_date = date_span_by_ticker[ticker]
                bar_index = build_bar_index(
                    conn,
                    ticker,
                    str(row["timeframe"]),
                    span_start_date,
                    span_end_date,
                    lookback_bars,
                    ohlcv_conn=resolved_ohlcv_conn,
                )
                bar_dates_by_ticker[ticker] = tuple() if bar_index is None else bar_index.bar_dates
            bar_dates = bar_dates_by_ticker[ticker]
            if not bar_dates:
                category = NO_OHLCV_ROWS_FOR_TICKER
            else:
                category = _classify_missing_bar_index_reason(conn, row, parsed_trace, bar_dates)

        category_counts[category] += 1
        if len(sample_rows_by_category[category]) < limit_samples:
            sample_rows_by_category[category].append(_make_sample_row(row, category))

    if should_close_ohlcv_conn and resolved_ohlcv_conn is not None:
        resolved_ohlcv_conn.close()

    return TechnicalSignalBarIndexAuditSummary(
        run_id=run_id,
        rows_total=len(rows),
        rows_missing_bar_index=rows_missing_bar_index,
        rows_with_bar_index_available=len(rows) - rows_missing_bar_index,
        category_counts=category_counts,
        sample_rows_by_category=sample_rows_by_category,
    )


__all__ = [
    "ALL_AUDIT_CATEGORIES",
    "EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT",
    "LATEST_BOS_CONFIRMED_DATE_NOT_IN_BAR_INDEX",
    "LATEST_PIVOT_CONFIRMED_DATE_NOT_IN_BAR_INDEX",
    "LATEST_RESET_CONFIRMED_DATE_NOT_IN_BAR_INDEX",
    "MISSING_OHLCV_SOURCE",
    "NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT",
    "NO_OHLCV_ROWS_FOR_TICKER",
    "NO_RELEVANCE_ROWS_FOR_RUN",
    "OBSERVATION_DATE_NOT_IN_BAR_INDEX",
    "ROW_NOT_MISSING_BAR_INDEX",
    "TechnicalSignalBarIndexAuditRow",
    "TechnicalSignalBarIndexAuditSummary",
    "UNKNOWN_BAR_INDEX_MISSING_REASON",
    "audit_missing_bar_index_for_run",
]
