from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable


DEFAULT_WINDOW_CONTEXT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
ALLOWED_HORIZONS = ("rolling2", "rolling5", "rolling30")
HORIZON_WINDOW_SIZES = {
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}
GROUP_RISK_TIMING_STATES = {"EXIT_ZONE", "TRIM_WATCH"}
GROUP_RISK_OVERHEAT_LEVELS = {"HIGH", "EXTREME"}
FRESH_SIGNAL_STATES = {"FRESH", "RECENT", "CURRENT"}
STALE_SIGNAL_STATES = {"STALE", "AGING"}
SEVERE_EXIT_RISK_SEVERITIES = {"HIGH", "EXTREME", "CRITICAL"}


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


def _normalize_horizons(horizons: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(horizon) for horizon in horizons))
    invalid = [horizon for horizon in normalized if horizon not in ALLOWED_HORIZONS]
    if invalid:
        raise ValueError(f"Unsupported horizons: {', '.join(invalid)}")
    return normalized


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


def _classify_rolling_current_watchlist_status(row: dict[str, object]) -> str:
    if int(row.get("in_datacenter_ecosystem") or 0) != 1:
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES:
        return "MISSING_PRICE"
    if row.get("last_exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("last_exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if row.get("last_breakout_signal") == 1:
        return "BREAKOUT_CANDIDATE"
    if row.get("last_pullback_signal") == 1:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _classify_rolling_window_watchlist_status(row: dict[str, object]) -> str:
    if int(row.get("in_datacenter_ecosystem") or 0) != 1:
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or bool(row.get("all_price_rows_missing")):
        return "MISSING_PRICE"
    if int(row.get("high_exit_risk_days") or 0) > 0:
        return "HIGH_EXIT_RISK"
    if int(row.get("medium_exit_risk_days") or 0) > 0:
        return "MEDIUM_EXIT_RISK"
    if int(row.get("breakout_days") or 0) > 0:
        return "BREAKOUT_CANDIDATE"
    if int(row.get("pullback_days") or 0) > 0:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _is_fresh_or_recent(value: object | None) -> bool:
    return str(value).strip().upper() in FRESH_SIGNAL_STATES if value is not None else False


def _is_stale_or_aging(value: object | None) -> bool:
    return str(value).strip().upper() in STALE_SIGNAL_STATES if value is not None else False


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    signal_version: str | None,
    limit: int,
) -> list[str]:
    table_columns = _get_table_columns(conn, "dc_group_swing_signal_daily")
    where_clauses = ["signal_date <= ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None and "market" in table_columns:
        where_clauses.append("market = ?")
        params.append(market)
    if signal_version is not None and "signal_version" in table_columns:
        where_clauses.append("signal_version = ?")
        params.append(signal_version)
    rows = conn.execute(
        f"""
        SELECT DISTINCT signal_date
        FROM dc_group_swing_signal_daily
        WHERE {' AND '.join(where_clauses)}
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        tuple(params) + (limit,),
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _load_ticker_rows_for_dates(
    conn: sqlite3.Connection,
    *,
    selected_dates: tuple[str, ...],
    taxonomy_version: str,
    market: str | None,
    signal_version: str | None,
) -> tuple[list[dict[str, object]], set[str]]:
    if not selected_dates:
        return [], _get_table_columns(conn, "dc_ticker_swing_signal_daily")
    source_columns = _get_table_columns(conn, "dc_ticker_swing_signal_daily")
    placeholders = ", ".join("?" for _ in selected_dates)
    where_clauses = [f"signal_date IN ({placeholders})", "taxonomy_version = ?"]
    params: list[object] = [*selected_dates, taxonomy_version]
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
        ORDER BY ticker ASC, signal_date ASC
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
    horizon: str,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = ?"]
    params: list[object] = [signal_date, taxonomy_version, horizon]
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


def _context_readiness_status(
    *,
    has_complete_window: bool,
    layer_context: dict[str, object] | None,
    subindustry_context: dict[str, object] | None,
) -> str:
    has_layer = bool(layer_context)
    has_subindustry = bool(subindustry_context)
    if not has_layer and not has_subindustry:
        return "MISSING_GROUP_CONTEXT"
    if not has_layer:
        return "MISSING_LAYER_CONTEXT"
    if not has_subindustry:
        return "MISSING_SUBINDUSTRY_CONTEXT"
    if not has_complete_window:
        return "PARTIAL_WINDOW"
    return "OK"


def _delete_existing_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    horizons: tuple[str, ...],
) -> None:
    placeholders = ", ".join("?" for _ in horizons)
    if market is None:
        conn.execute(
            f"""
            DELETE FROM dc_report_context_window_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND horizon IN ({placeholders})
            """,
            (signal_date, taxonomy_version, *horizons),
        )
    else:
        conn.execute(
            f"""
            DELETE FROM dc_report_context_window_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND horizon IN ({placeholders})
              AND market = ?
            """,
            (signal_date, taxonomy_version, *horizons, market),
        )


def _write_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO dc_report_context_window_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            window_start_date,
            window_end_date,
            valid_signal_dates,
            incomplete_window,
            primary_layer,
            primary_subindustry,
            in_datacenter_ecosystem,
            is_watchlist,
            current_watchlist_status,
            window_watchlist_status,
            breakout_days,
            pullback_days,
            fast_ema10_pullback_days,
            conservative_ema20_pullback_days,
            exit_risk_days,
            high_exit_risk_days,
            medium_exit_risk_days,
            first_signal_date,
            last_signal_date,
            latest_exit_reason,
            layer_timing_state,
            layer_overheat_risk_level,
            layer_context_risk_status,
            subindustry_timing_state,
            subindustry_overheat_risk_level,
            subindustry_context_risk_status,
            trend_state,
            latest_structure_label,
            latest_structure_freshness,
            latest_bos_event_type,
            latest_bos_freshness,
            latest_reset_reason,
            latest_reset_freshness,
            price_data_status,
            exit_risk_severity,
            latest_bearish_relevance_class,
            distance_to_ema20_pct,
            all_price_rows_missing,
            ma_break_status,
            freshness_status,
            technical_relevance_status,
            technical_relevance_reason,
            close_below_ema20_flag,
            close_below_ema50_flag,
            return_10d_lt_minus_8pct_flag,
            double_bos_down_flag,
            double_bos_up_flag,
            fresh_bos_flag,
            fresh_reset_flag,
            stale_structure_flag,
            layer_overheat_risk_flag,
            subindustry_overheat_risk_flag,
            severe_exit_risk_flag,
            context_readiness_status,
            run_id,
            created_at_utc
        ) VALUES (
            :signal_date,
            :taxonomy_version,
            :market,
            :ticker,
            :horizon,
            :window_start_date,
            :window_end_date,
            :valid_signal_dates,
            :incomplete_window,
            :primary_layer,
            :primary_subindustry,
            :in_datacenter_ecosystem,
            :is_watchlist,
            :current_watchlist_status,
            :window_watchlist_status,
            :breakout_days,
            :pullback_days,
            :fast_ema10_pullback_days,
            :conservative_ema20_pullback_days,
            :exit_risk_days,
            :high_exit_risk_days,
            :medium_exit_risk_days,
            :first_signal_date,
            :last_signal_date,
            :latest_exit_reason,
            :layer_timing_state,
            :layer_overheat_risk_level,
            :layer_context_risk_status,
            :subindustry_timing_state,
            :subindustry_overheat_risk_level,
            :subindustry_context_risk_status,
            :trend_state,
            :latest_structure_label,
            :latest_structure_freshness,
            :latest_bos_event_type,
            :latest_bos_freshness,
            :latest_reset_reason,
            :latest_reset_freshness,
            :price_data_status,
            :exit_risk_severity,
            :latest_bearish_relevance_class,
            :distance_to_ema20_pct,
            :all_price_rows_missing,
            :ma_break_status,
            :freshness_status,
            :technical_relevance_status,
            :technical_relevance_reason,
            :close_below_ema20_flag,
            :close_below_ema50_flag,
            :return_10d_lt_minus_8pct_flag,
            :double_bos_down_flag,
            :double_bos_up_flag,
            :fresh_bos_flag,
            :fresh_reset_flag,
            :stale_structure_flag,
            :layer_overheat_risk_flag,
            :subindustry_overheat_risk_flag,
            :severe_exit_risk_flag,
            :context_readiness_status,
            :run_id,
            :created_at_utc
        )
        """,
        rows,
    )


def build_report_window_context_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    horizons: tuple[str, ...] = ("rolling2", "rolling5", "rolling30"),
    signal_version: str | None = DEFAULT_WINDOW_CONTEXT_SIGNAL_VERSION,
    ecosystem_tickers: set[str] | None = None,
    watchlist_tickers: set[str] | None = None,
    calculation_version: str = "REPORT_CANONICAL_WINDOW_CONTEXT_V2_1",
    created_at_utc: str | None = None,
) -> dict[str, int]:
    del calculation_version
    conn.row_factory = sqlite3.Row
    _ensure_run_exists(conn, run_id)
    normalized_horizons = _normalize_horizons(horizons)
    created_at_value = created_at_utc or _utc_now_iso()
    # At this builder stage, source ticker rows are already report-scope rows, so absent an
    # explicit ecosystem set they are treated as ecosystem members.
    normalized_ecosystem = None if ecosystem_tickers is None else {ticker.upper() for ticker in ecosystem_tickers}
    normalized_watchlist = {ticker.upper() for ticker in (watchlist_tickers or set())}

    rows_to_write: list[dict[str, object]] = []
    source_ticker_rows_read = 0
    group_context_rows_read = 0
    rows_missing_group_context = 0
    written_counts = {
        "rolling2_rows_written": 0,
        "rolling5_rows_written": 0,
        "rolling30_rows_written": 0,
    }

    for horizon in normalized_horizons:
        expected_window_size = HORIZON_WINDOW_SIZES[horizon]
        valid_signal_dates = _load_valid_signal_dates(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            market=market,
            signal_version=signal_version,
            limit=expected_window_size,
        )
        selected_dates = tuple(valid_signal_dates)
        ticker_rows, ticker_source_columns = _load_ticker_rows_for_dates(
            conn,
            selected_dates=selected_dates,
            taxonomy_version=taxonomy_version,
            market=market,
            signal_version=signal_version,
        )
        source_ticker_rows_read += len(ticker_rows)
        group_rows = _load_group_context_rows(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            market=market,
            horizon=horizon,
        )
        group_context_rows_read += len(group_rows)
        group_context_by_key = {
            _group_join_key(
                market=str(row.get("market")) if row.get("market") is not None else None,
                group_type=str(row.get("group_type") or ""),
                group_name=row.get("group_name"),
            ): row
            for row in group_rows
        }

        ticker_rows_by_ticker: dict[str, list[dict[str, object]]] = {}
        for row in ticker_rows:
            ticker = str(_ticker_source_value(row, ticker_source_columns, "ticker") or "")
            if not ticker:
                continue
            ticker_rows_by_ticker.setdefault(ticker, []).append(row)
        for current_rows in ticker_rows_by_ticker.values():
            current_rows.sort(key=lambda row: str(_ticker_source_value(row, ticker_source_columns, "signal_date") or ""))

        window_start_date = selected_dates[0] if selected_dates else signal_date
        window_end_date = selected_dates[-1] if selected_dates else signal_date
        valid_signal_date_count = len(selected_dates)
        incomplete_window = 1 if valid_signal_date_count < expected_window_size else 0

        for ticker in sorted(ticker_rows_by_ticker):
            current_rows = ticker_rows_by_ticker[ticker]
            last_row = current_rows[-1]
            row_market = (
                _ticker_source_value(last_row, ticker_source_columns, "market")
                if _ticker_source_value(last_row, ticker_source_columns, "market") is not None
                else market
            )
            primary_layer = _ticker_source_value(last_row, ticker_source_columns, "primary_layer")
            primary_subindustry = _ticker_source_value(last_row, ticker_source_columns, "primary_subindustry")
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
                has_complete_window=(incomplete_window == 0),
                layer_context=layer_context,
                subindustry_context=subindustry_context,
            )
            if readiness_status != "OK":
                rows_missing_group_context += 1

            in_datacenter_ecosystem = 1
            if normalized_ecosystem is not None:
                in_datacenter_ecosystem = 1 if ticker.upper() in normalized_ecosystem else 0
            output_row = {
                "signal_date": signal_date,
                "taxonomy_version": taxonomy_version,
                "market": row_market,
                "ticker": ticker,
                "horizon": horizon,
                "window_start_date": window_start_date,
                "window_end_date": window_end_date,
                "valid_signal_dates": valid_signal_date_count,
                "incomplete_window": incomplete_window,
                "primary_layer": primary_layer,
                "primary_subindustry": primary_subindustry,
                "in_datacenter_ecosystem": in_datacenter_ecosystem,
                "is_watchlist": 1 if ticker.upper() in normalized_watchlist else 0,
                "current_watchlist_status": None,
                "window_watchlist_status": None,
                "breakout_days": sum(1 for row in current_rows if int(_ticker_source_value(row, ticker_source_columns, "breakout_signal") or 0) == 1),
                "pullback_days": sum(1 for row in current_rows if int(_ticker_source_value(row, ticker_source_columns, "pullback_signal") or 0) == 1),
                "fast_ema10_pullback_days": sum(1 for row in current_rows if int(_ticker_source_value(row, ticker_source_columns, "fast_ema10_pullback_signal") or 0) == 1),
                "conservative_ema20_pullback_days": sum(1 for row in current_rows if int(_ticker_source_value(row, ticker_source_columns, "conservative_ema20_pullback_signal") or 0) == 1),
                "exit_risk_days": sum(1 for row in current_rows if int(_ticker_source_value(row, ticker_source_columns, "exit_risk_signal") or 0) == 1),
                "high_exit_risk_days": sum(1 for row in current_rows if _ticker_source_value(row, ticker_source_columns, "exit_risk_severity") == "HIGH"),
                "medium_exit_risk_days": sum(1 for row in current_rows if _ticker_source_value(row, ticker_source_columns, "exit_risk_severity") == "MEDIUM"),
                "first_signal_date": _ticker_source_value(current_rows[0], ticker_source_columns, "signal_date"),
                "last_signal_date": _ticker_source_value(last_row, ticker_source_columns, "signal_date"),
                "latest_exit_reason": _ticker_source_value(last_row, ticker_source_columns, "exit_reason"),
                "layer_timing_state": None if layer_context is None else layer_context.get("timing_state"),
                "layer_overheat_risk_level": None if layer_context is None else layer_context.get("overheat_risk_level"),
                "layer_context_risk_status": None if layer_context is None else layer_context.get("group_context_risk_status"),
                "subindustry_timing_state": None if subindustry_context is None else subindustry_context.get("timing_state"),
                "subindustry_overheat_risk_level": None if subindustry_context is None else subindustry_context.get("overheat_risk_level"),
                "subindustry_context_risk_status": None if subindustry_context is None else subindustry_context.get("group_context_risk_status"),
                "trend_state": _ticker_source_value(last_row, ticker_source_columns, "trend_state", "ticker_trend_state"),
                "latest_structure_label": _ticker_source_value(last_row, ticker_source_columns, "latest_structure_label"),
                "latest_structure_freshness": _ticker_source_value(last_row, ticker_source_columns, "latest_structure_freshness"),
                "latest_bos_event_type": _ticker_source_value(last_row, ticker_source_columns, "latest_bos_event_type"),
                "latest_bos_freshness": _ticker_source_value(last_row, ticker_source_columns, "latest_bos_freshness"),
                "latest_reset_reason": _ticker_source_value(last_row, ticker_source_columns, "latest_reset_reason"),
                "latest_reset_freshness": _ticker_source_value(last_row, ticker_source_columns, "latest_reset_freshness"),
                "price_data_status": _ticker_source_value(last_row, ticker_source_columns, "price_data_status"),
                "exit_risk_severity": _ticker_source_value(last_row, ticker_source_columns, "exit_risk_severity"),
                "latest_bearish_relevance_class": _ticker_source_value(last_row, ticker_source_columns, "latest_bearish_relevance_class"),
                "distance_to_ema20_pct": _ticker_source_value(last_row, ticker_source_columns, "distance_to_ema20_pct"),
                "ma_break_status": None,
                "freshness_status": None,
                "technical_relevance_status": None,
                "technical_relevance_reason": None,
                "close_below_ema20_flag": 1 if (_ticker_source_value(last_row, ticker_source_columns, "distance_to_ema20_pct") or 0) < 0 else 0,
                "close_below_ema50_flag": 1 if (_ticker_source_value(last_row, ticker_source_columns, "distance_to_ema50_pct") or 0) < 0 else 0,
                "return_10d_lt_minus_8pct_flag": 1 if (_ticker_source_value(last_row, ticker_source_columns, "return_10d") or 0) < -8 else 0,
                "double_bos_down_flag": 1 if _ticker_source_value(last_row, ticker_source_columns, "latest_reset_reason") == "DOUBLE_BOS_DOWN" else 0,
                "double_bos_up_flag": 1 if _ticker_source_value(last_row, ticker_source_columns, "latest_reset_reason") == "DOUBLE_BOS_UP" else 0,
                "fresh_bos_flag": 1
                if _ticker_source_value(last_row, ticker_source_columns, "latest_bos_event_type") not in {None, "", "NULL"}
                and _is_fresh_or_recent(_ticker_source_value(last_row, ticker_source_columns, "latest_bos_freshness"))
                else 0,
                "fresh_reset_flag": 1
                if _ticker_source_value(last_row, ticker_source_columns, "latest_reset_reason") not in {None, "", "NULL"}
                and _is_fresh_or_recent(_ticker_source_value(last_row, ticker_source_columns, "latest_reset_freshness"))
                else 0,
                "stale_structure_flag": 1 if _is_stale_or_aging(_ticker_source_value(last_row, ticker_source_columns, "latest_structure_freshness")) else 0,
                "layer_overheat_risk_flag": 1 if (None if layer_context is None else layer_context.get("overheat_risk_level")) in GROUP_RISK_OVERHEAT_LEVELS else 0,
                "subindustry_overheat_risk_flag": 1 if (None if subindustry_context is None else subindustry_context.get("overheat_risk_level")) in GROUP_RISK_OVERHEAT_LEVELS else 0,
                # Safe derivation from current source/context only: use high-or-worse last exit severity.
                "severe_exit_risk_flag": 1 if _ticker_source_value(last_row, ticker_source_columns, "exit_risk_severity") in SEVERE_EXIT_RISK_SEVERITIES else 0,
                "context_readiness_status": readiness_status,
                "run_id": run_id,
                "created_at_utc": created_at_value,
                "last_price_data_status": _ticker_source_value(last_row, ticker_source_columns, "price_data_status"),
                "last_exit_risk_severity": _ticker_source_value(last_row, ticker_source_columns, "exit_risk_severity"),
                "last_breakout_signal": _ticker_source_value(last_row, ticker_source_columns, "breakout_signal"),
                "last_pullback_signal": _ticker_source_value(last_row, ticker_source_columns, "pullback_signal"),
                "last_subindustry_timing_state": None if subindustry_context is None else subindustry_context.get("timing_state"),
                "last_subindustry_overheat_risk_level": None if subindustry_context is None else subindustry_context.get("overheat_risk_level"),
                "last_layer_timing_state": None if layer_context is None else layer_context.get("timing_state"),
                "last_layer_overheat_risk_level": None if layer_context is None else layer_context.get("overheat_risk_level"),
                "all_price_rows_missing": 1 if all(
                    _ticker_source_value(row, ticker_source_columns, "price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES
                    for row in current_rows
                ) else 0,
            }
            output_row["current_watchlist_status"] = _classify_rolling_current_watchlist_status(output_row)
            output_row["window_watchlist_status"] = _classify_rolling_window_watchlist_status(output_row)
            del output_row["last_price_data_status"]
            del output_row["last_exit_risk_severity"]
            del output_row["last_breakout_signal"]
            del output_row["last_pullback_signal"]
            del output_row["last_subindustry_timing_state"]
            del output_row["last_subindustry_overheat_risk_level"]
            del output_row["last_layer_timing_state"]
            del output_row["last_layer_overheat_risk_level"]
            rows_to_write.append(output_row)
            written_counts[f"{horizon}_rows_written"] += 1

    _delete_existing_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        horizons=normalized_horizons,
    )
    _write_rows(conn, rows_to_write)
    conn.commit()

    return {
        **written_counts,
        "total_rows_written": sum(written_counts.values()),
        "source_ticker_rows_read": source_ticker_rows_read,
        "group_context_rows_read": group_context_rows_read,
        "rows_missing_group_context": rows_missing_group_context,
    }
