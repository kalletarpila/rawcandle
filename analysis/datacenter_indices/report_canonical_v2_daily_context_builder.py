from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable


DEFAULT_DAILY_CONTEXT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}
GROUP_RISK_TIMING_STATES = {"EXIT_ZONE", "TRIM_WATCH"}
GROUP_RISK_OVERHEAT_LEVELS = {"HIGH", "EXTREME"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_run_exists(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM dc_report_run_v2 WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"dc_report_run_v2 row not found for run_id={run_id}")


def _ticker_source_value(
    row: dict[str, object],
    available_columns: set[str],
    *candidate_names: str,
) -> object | None:
    for candidate in candidate_names:
        if candidate in available_columns:
            return row.get(candidate)
    return None


def _group_join_key(*, market: str | None, group_type: str, group_name: object | None) -> tuple[object, ...]:
    return (market, group_type, group_name)


def _is_group_risk_state(
    *,
    subindustry_timing_state: object | None,
    subindustry_overheat_risk_level: object | None,
    layer_timing_state: object | None,
    layer_overheat_risk_level: object | None,
) -> bool:
    return (
        subindustry_timing_state in GROUP_RISK_TIMING_STATES
        or layer_timing_state in GROUP_RISK_TIMING_STATES
        or subindustry_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
        or layer_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
    )


def _classify_daily_watchlist_status(row: dict[str, object]) -> str:
    if int(row.get("in_datacenter_ecosystem") or 0) != 1:
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or row.get("close") is None:
        return "MISSING_PRICE"
    if row.get("exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if row.get("breakout_signal") == 1:
        return "BREAKOUT_CANDIDATE"
    if row.get("pullback_signal") == 1:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("subindustry_overheat_risk_level"),
        layer_timing_state=row.get("layer_timing_state"),
        layer_overheat_risk_level=row.get("layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _context_readiness_status(
    *,
    layer_context: dict[str, object] | None,
    subindustry_context: dict[str, object] | None,
) -> str:
    has_layer = bool(layer_context)
    has_subindustry = bool(subindustry_context)
    if has_layer and has_subindustry:
        return "OK"
    if not has_layer and not has_subindustry:
        return "MISSING_GROUP_CONTEXT"
    if not has_layer:
        return "MISSING_LAYER_CONTEXT"
    return "MISSING_SUBINDUSTRY_CONTEXT"


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    signal_version: str | None,
) -> tuple[list[dict[str, object]], set[str]]:
    source_columns = _get_table_columns(conn, "dc_ticker_swing_signal_daily")
    where_clauses = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None and "market" in source_columns:
        where_clauses.append("market = ?")
        params.append(market)
    if signal_version is not None and "signal_version" in source_columns:
        where_clauses.append("signal_version = ?")
        params.append(signal_version)
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker ASC
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_dict(row) for row in rows], source_columns


def _load_group_context_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = 'daily'"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None:
        where_clauses.append("market = ?")
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_report_context_group_v2
        WHERE {' AND '.join(where_clauses)}
        ORDER BY group_type ASC, group_name ASC
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
            DELETE FROM dc_report_context_daily_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
            """,
            (signal_date, taxonomy_version),
        )
    else:
        conn.execute(
            """
            DELETE FROM dc_report_context_daily_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND market = ?
            """,
            (signal_date, taxonomy_version, market),
        )


def _write_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO dc_report_context_daily_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            primary_layer,
            primary_subindustry,
            in_datacenter_ecosystem,
            is_watchlist,
            current_watchlist_status,
            price_data_status,
            close,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            latest_exit_reason,
            latest_bullish_relevance_class,
            latest_bearish_relevance_class,
            bullish_candle_signal,
            bullish_divergence_signal,
            hidden_bullish_divergence_signal,
            bearish_candle_signal,
            bearish_divergence_signal,
            hidden_bearish_divergence_signal,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            distance_to_ema20_pct,
            distance_to_ema50_pct,
            ma_break_status,
            freshness_status,
            technical_relevance_status,
            technical_relevance_reason,
            trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            layer_timing_state,
            layer_overheat_risk_level,
            layer_context_risk_status,
            subindustry_timing_state,
            subindustry_overheat_risk_level,
            subindustry_context_risk_status,
            context_readiness_status,
            run_id,
            created_at_utc
        ) VALUES (
            :signal_date,
            :taxonomy_version,
            :market,
            :ticker,
            :primary_layer,
            :primary_subindustry,
            :in_datacenter_ecosystem,
            :is_watchlist,
            :current_watchlist_status,
            :price_data_status,
            :close,
            :breakout_signal,
            :pullback_signal,
            :fast_ema10_pullback_signal,
            :conservative_ema20_pullback_signal,
            :exit_risk_signal,
            :exit_risk_severity,
            :latest_exit_reason,
            :latest_bullish_relevance_class,
            :latest_bearish_relevance_class,
            :bullish_candle_signal,
            :bullish_divergence_signal,
            :hidden_bullish_divergence_signal,
            :bearish_candle_signal,
            :bearish_divergence_signal,
            :hidden_bearish_divergence_signal,
            :return_5d,
            :return_10d,
            :return_20d,
            :return_60d,
            :distance_to_ema20_pct,
            :distance_to_ema50_pct,
            :ma_break_status,
            :freshness_status,
            :technical_relevance_status,
            :technical_relevance_reason,
            :trend_state,
            :latest_structure_label,
            :latest_structure_freshness,
            :latest_bos_event_type,
            :latest_bos_freshness,
            :latest_reset_reason,
            :latest_reset_freshness,
            :layer_timing_state,
            :layer_overheat_risk_level,
            :layer_context_risk_status,
            :subindustry_timing_state,
            :subindustry_overheat_risk_level,
            :subindustry_context_risk_status,
            :context_readiness_status,
            :run_id,
            :created_at_utc
        )
        """,
        rows,
    )


def build_report_daily_context_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    signal_version: str | None = DEFAULT_DAILY_CONTEXT_SIGNAL_VERSION,
    calculation_version: str = "REPORT_CANONICAL_DAILY_CONTEXT_V2_1",
    created_at_utc: str | None = None,
    ecosystem_tickers: set[str] | None = None,
    watchlist_tickers: set[str] | None = None,
) -> dict[str, int]:
    del calculation_version
    conn.row_factory = sqlite3.Row
    _ensure_run_exists(conn, run_id)
    created_at_value = created_at_utc or _utc_now_iso()

    ticker_rows, ticker_source_columns = _load_ticker_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        signal_version=signal_version,
    )
    group_rows = _load_group_context_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
    )
    group_context_by_key = {
        _group_join_key(
            market=str(row.get("market")) if row.get("market") is not None else None,
            group_type=str(row.get("group_type") or ""),
            group_name=row.get("group_name"),
        ): row
        for row in group_rows
    }

    # At this builder stage, source ticker rows are already report-scope rows, so absent an
    # explicit ecosystem set they are treated as ecosystem members.
    normalized_ecosystem = None if ecosystem_tickers is None else {ticker.upper() for ticker in ecosystem_tickers}
    normalized_watchlist = {ticker.upper() for ticker in (watchlist_tickers or set())}
    rows_to_write: list[dict[str, object]] = []
    rows_missing_group_context = 0

    for ticker_row in ticker_rows:
        row_market = (
            _ticker_source_value(ticker_row, ticker_source_columns, "market")
            if _ticker_source_value(ticker_row, ticker_source_columns, "market") is not None
            else market
        )
        primary_layer = _ticker_source_value(ticker_row, ticker_source_columns, "primary_layer")
        primary_subindustry = _ticker_source_value(ticker_row, ticker_source_columns, "primary_subindustry")
        layer_context = group_context_by_key.get(
            _group_join_key(market=row_market, group_type="layer", group_name=primary_layer)
        ) or group_context_by_key.get(
            _group_join_key(market=None, group_type="layer", group_name=primary_layer)
        )
        subindustry_context = group_context_by_key.get(
            _group_join_key(market=row_market, group_type="subindustry", group_name=primary_subindustry)
        ) or group_context_by_key.get(
            _group_join_key(market=None, group_type="subindustry", group_name=primary_subindustry)
        )
        readiness_status = _context_readiness_status(
            layer_context=layer_context,
            subindustry_context=subindustry_context,
        )
        if readiness_status != "OK":
            rows_missing_group_context += 1

        ticker_value = str(_ticker_source_value(ticker_row, ticker_source_columns, "ticker") or "")
        in_datacenter_ecosystem = 1
        if normalized_ecosystem is not None:
            in_datacenter_ecosystem = 1 if ticker_value.upper() in normalized_ecosystem else 0
        output_row = {
            "signal_date": signal_date,
            "taxonomy_version": taxonomy_version,
            "market": row_market,
            "ticker": ticker_value,
            "primary_layer": primary_layer,
            "primary_subindustry": primary_subindustry,
            "in_datacenter_ecosystem": in_datacenter_ecosystem,
            "is_watchlist": 1 if ticker_value.upper() in normalized_watchlist else 0,
            "current_watchlist_status": None,
            "price_data_status": _ticker_source_value(ticker_row, ticker_source_columns, "price_data_status"),
            "close": _ticker_source_value(ticker_row, ticker_source_columns, "close"),
            "breakout_signal": int(_ticker_source_value(ticker_row, ticker_source_columns, "breakout_signal") or 0),
            "pullback_signal": int(_ticker_source_value(ticker_row, ticker_source_columns, "pullback_signal") or 0),
            "fast_ema10_pullback_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "fast_ema10_pullback_signal") or 0
            ),
            "conservative_ema20_pullback_signal": int(
                _ticker_source_value(
                    ticker_row,
                    ticker_source_columns,
                    "conservative_ema20_pullback_signal",
                )
                or 0
            ),
            "exit_risk_signal": int(_ticker_source_value(ticker_row, ticker_source_columns, "exit_risk_signal") or 0),
            "exit_risk_severity": _ticker_source_value(ticker_row, ticker_source_columns, "exit_risk_severity"),
            "latest_exit_reason": _ticker_source_value(ticker_row, ticker_source_columns, "exit_reason"),
            "latest_bullish_relevance_class": _ticker_source_value(
                ticker_row,
                ticker_source_columns,
                "latest_bullish_relevance_class",
            ),
            "latest_bearish_relevance_class": _ticker_source_value(
                ticker_row,
                ticker_source_columns,
                "latest_bearish_relevance_class",
            ),
            "bullish_candle_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "bullish_candle_signal") or 0
            ),
            "bullish_divergence_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "bullish_divergence_signal") or 0
            ),
            "hidden_bullish_divergence_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "hidden_bullish_divergence_signal") or 0
            ),
            "bearish_candle_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "bearish_candle_signal") or 0
            ),
            "bearish_divergence_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "bearish_divergence_signal") or 0
            ),
            "hidden_bearish_divergence_signal": int(
                _ticker_source_value(ticker_row, ticker_source_columns, "hidden_bearish_divergence_signal") or 0
            ),
            "return_5d": _ticker_source_value(ticker_row, ticker_source_columns, "return_5d"),
            "return_10d": _ticker_source_value(ticker_row, ticker_source_columns, "return_10d"),
            "return_20d": _ticker_source_value(ticker_row, ticker_source_columns, "return_20d"),
            "return_60d": _ticker_source_value(ticker_row, ticker_source_columns, "return_60d"),
            "distance_to_ema20_pct": _ticker_source_value(ticker_row, ticker_source_columns, "distance_to_ema20_pct"),
            "distance_to_ema50_pct": _ticker_source_value(ticker_row, ticker_source_columns, "distance_to_ema50_pct"),
            # MA/freshness helpers are intentionally left for a later focused task.
            "ma_break_status": None,
            "freshness_status": None,
            "technical_relevance_status": None,
            "technical_relevance_reason": None,
            "trend_state": _ticker_source_value(
                ticker_row,
                ticker_source_columns,
                "trend_state",
                "ticker_trend_state",
            ),
            "latest_structure_label": _ticker_source_value(ticker_row, ticker_source_columns, "latest_structure_label"),
            "latest_structure_freshness": _ticker_source_value(
                ticker_row,
                ticker_source_columns,
                "latest_structure_freshness",
            ),
            "latest_bos_event_type": _ticker_source_value(ticker_row, ticker_source_columns, "latest_bos_event_type"),
            "latest_bos_freshness": _ticker_source_value(ticker_row, ticker_source_columns, "latest_bos_freshness"),
            "latest_reset_reason": _ticker_source_value(ticker_row, ticker_source_columns, "latest_reset_reason"),
            "latest_reset_freshness": _ticker_source_value(ticker_row, ticker_source_columns, "latest_reset_freshness"),
            "layer_timing_state": None if layer_context is None else layer_context.get("timing_state"),
            "layer_overheat_risk_level": None if layer_context is None else layer_context.get("overheat_risk_level"),
            "layer_context_risk_status": None if layer_context is None else layer_context.get("group_context_risk_status"),
            "subindustry_timing_state": None if subindustry_context is None else subindustry_context.get("timing_state"),
            "subindustry_overheat_risk_level": None if subindustry_context is None else subindustry_context.get("overheat_risk_level"),
            "subindustry_context_risk_status": None
            if subindustry_context is None
            else subindustry_context.get("group_context_risk_status"),
            "context_readiness_status": readiness_status,
            "run_id": run_id,
            "created_at_utc": created_at_value,
        }
        output_row["current_watchlist_status"] = _classify_daily_watchlist_status(output_row)
        rows_to_write.append(output_row)

    _delete_existing_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
    )
    _write_rows(conn, rows_to_write)
    conn.commit()

    return {
        "source_ticker_rows_read": len(ticker_rows),
        "daily_rows_written": len(rows_to_write),
        "group_context_rows_read": len(group_rows),
        "rows_missing_group_context": rows_missing_group_context,
        "total_rows_written": len(rows_to_write),
    }
