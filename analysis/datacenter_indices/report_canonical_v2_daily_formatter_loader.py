from __future__ import annotations

import sqlite3


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _load_run(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    run_id: str | None,
) -> dict[str, object] | None:
    if run_id is not None:
        row = conn.execute(
            """
            SELECT *
            FROM dc_report_run_v2
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return None if row is None else _row_to_dict(row)

    where_clauses = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is None:
        where_clauses.append("market IS NULL")
    else:
        where_clauses.append("market = ?")
        params.append(market)
    row = conn.execute(
        f"""
        SELECT *
        FROM dc_report_run_v2
        WHERE {' AND '.join(where_clauses)}
        ORDER BY created_at_utc DESC, run_id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return None if row is None else _row_to_dict(row)


def _load_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    selected_run_id: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = 'daily'"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is None:
        where_clauses.append("market IS NULL")
    else:
        where_clauses.append("market = ?")
        params.append(market)
    if selected_run_id is not None:
        where_clauses.append("run_id = ?")
        params.append(selected_run_id)
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


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    selected_run_id: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is None:
        where_clauses.append("market IS NULL")
    else:
        where_clauses.append("market = ?")
        params.append(market)
    if selected_run_id is not None:
        where_clauses.append("run_id = ?")
        params.append(selected_run_id)
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


def _load_classification_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    selected_run_id: str | None,
) -> list[dict[str, object]]:
    where_clauses = [
        "signal_date = ?",
        "taxonomy_version = ?",
        "horizon = 'daily'",
        "classification_type = 'daily_trigger'",
    ]
    params: list[object] = [signal_date, taxonomy_version]
    if market is None:
        where_clauses.append("market IS NULL")
    else:
        where_clauses.append("market = ?")
        params.append(market)
    if selected_run_id is not None:
        where_clauses.append("run_id = ?")
        params.append(selected_run_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_report_classification_v2
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker ASC
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _build_daily_trigger_rows(
    *,
    ticker_rows: list[dict[str, object]],
    classification_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    ticker_by_symbol = {
        str(row.get("ticker") or ""): row
        for row in ticker_rows
        if str(row.get("ticker") or "")
    }
    output_rows: list[dict[str, object]] = []
    for classification_row in classification_rows:
        ticker = str(classification_row.get("ticker") or "")
        ticker_row = ticker_by_symbol.get(ticker, {})
        output_rows.append(
            {
                **classification_row,
                "primary_layer": ticker_row.get("primary_layer"),
                "primary_subindustry": ticker_row.get("primary_subindustry"),
                "close": ticker_row.get("close"),
                "current_watchlist_status": ticker_row.get("current_watchlist_status"),
                "exit_risk_severity": ticker_row.get("exit_risk_severity"),
                "trend_state": ticker_row.get("trend_state"),
                "latest_bos_event_type": ticker_row.get("latest_bos_event_type"),
                "latest_reset_reason": ticker_row.get("latest_reset_reason"),
                "latest_bullish_relevance_class": ticker_row.get("latest_bullish_relevance_class"),
                "latest_bearish_relevance_class": ticker_row.get("latest_bearish_relevance_class"),
            }
        )
    output_rows.sort(key=lambda row: str(row.get("ticker") or ""))
    return output_rows


def _build_watchlist_rows(ticker_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [dict(row) for row in ticker_rows if int(row.get("is_watchlist") or 0) == 1]
    rows.sort(key=lambda row: str(row.get("ticker") or ""))
    return rows


def _build_taxonomy_listing_rows(
    *,
    group_rows: list[dict[str, object]],
    ticker_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    layer_rows = {
        str(row.get("group_name") or ""): row
        for row in group_rows
        if row.get("group_type") == "layer" and str(row.get("group_name") or "")
    }
    subindustry_rows = {
        str(row.get("group_name") or ""): row
        for row in group_rows
        if row.get("group_type") == "subindustry" and str(row.get("group_name") or "")
    }

    tickers_by_layer_subindustry: dict[tuple[str, str], list[dict[str, object]]] = {}
    for ticker_row in ticker_rows:
        layer_name = str(ticker_row.get("primary_layer") or "")
        subindustry_name = str(ticker_row.get("primary_subindustry") or "")
        if not layer_name or not subindustry_name:
            continue
        tickers_by_layer_subindustry.setdefault((layer_name, subindustry_name), []).append(ticker_row)

    output_rows: list[dict[str, object]] = []
    for layer_name in sorted(layer_rows):
        layer_row = layer_rows[layer_name]
        output_rows.append(
            {
                "row_type": "LAYER",
                "layer": layer_name,
                "subindustry": "",
                "ticker": "",
                "status": layer_row.get("timing_state"),
                "subindustry_context_risk_status": "",
                "layer_context_risk_status": layer_row.get("group_context_risk_status"),
                "close": layer_row.get("synthetic_close"),
                "return_5d": layer_row.get("return_5d"),
                "return_10d": layer_row.get("return_10d"),
                "return_20d": layer_row.get("return_20d"),
                "distance_to_ema20_pct": layer_row.get("pct_above_ema20"),
                "trend_state": layer_row.get("synthetic_trend_classification"),
                "latest_structure_label": layer_row.get("synthetic_latest_structure_label"),
                "latest_structure_age_trading_days": layer_row.get("synthetic_latest_structure_age_trading_days"),
                "latest_structure_freshness": None,
                "latest_bos_event_type": layer_row.get("synthetic_latest_bos_event_type"),
                "latest_bos_age_trading_days": layer_row.get("synthetic_latest_bos_age_trading_days"),
                "latest_bos_freshness": layer_row.get("synthetic_latest_bos_freshness"),
                "latest_reset_reason": layer_row.get("synthetic_latest_reset_reason"),
                "latest_reset_age_trading_days": layer_row.get("synthetic_latest_reset_age_trading_days"),
                "latest_reset_freshness": layer_row.get("synthetic_latest_reset_freshness"),
                "breakout_signal": None,
                "pullback_signal": None,
                "exit_risk_signal": None,
                "exit_risk_severity": None,
                "price_data_status": layer_row.get("data_quality_status"),
            }
        )
        subindustries_for_layer = sorted(
            {
                subindustry_name
                for candidate_layer, subindustry_name in tickers_by_layer_subindustry
                if candidate_layer == layer_name
            }
        )
        for subindustry_name in subindustries_for_layer:
            subindustry_row = subindustry_rows.get(subindustry_name, {})
            output_rows.append(
                {
                    "row_type": "SUBINDUSTRY",
                    "layer": layer_name,
                    "subindustry": subindustry_name,
                    "ticker": "",
                    "status": subindustry_row.get("timing_state"),
                    "subindustry_context_risk_status": subindustry_row.get("group_context_risk_status"),
                    "layer_context_risk_status": layer_row.get("group_context_risk_status"),
                    "close": subindustry_row.get("synthetic_close"),
                    "return_5d": subindustry_row.get("return_5d"),
                    "return_10d": subindustry_row.get("return_10d"),
                    "return_20d": subindustry_row.get("return_20d"),
                    "distance_to_ema20_pct": subindustry_row.get("pct_above_ema20"),
                    "trend_state": subindustry_row.get("synthetic_trend_classification"),
                    "latest_structure_label": subindustry_row.get("synthetic_latest_structure_label"),
                    "latest_structure_age_trading_days": subindustry_row.get("synthetic_latest_structure_age_trading_days"),
                    "latest_structure_freshness": None,
                    "latest_bos_event_type": subindustry_row.get("synthetic_latest_bos_event_type"),
                    "latest_bos_age_trading_days": subindustry_row.get("synthetic_latest_bos_age_trading_days"),
                    "latest_bos_freshness": subindustry_row.get("synthetic_latest_bos_freshness"),
                    "latest_reset_reason": subindustry_row.get("synthetic_latest_reset_reason"),
                    "latest_reset_age_trading_days": subindustry_row.get("synthetic_latest_reset_age_trading_days"),
                    "latest_reset_freshness": subindustry_row.get("synthetic_latest_reset_freshness"),
                    "breakout_signal": None,
                    "pullback_signal": None,
                    "exit_risk_signal": None,
                    "exit_risk_severity": None,
                    "price_data_status": subindustry_row.get("data_quality_status"),
                }
            )
            for ticker_row in sorted(
                tickers_by_layer_subindustry.get((layer_name, subindustry_name), []),
                key=lambda row: str(row.get("ticker") or ""),
            ):
                output_rows.append(
                    {
                        "row_type": "TICKER",
                        "layer": layer_name,
                        "subindustry": subindustry_name,
                        "ticker": ticker_row.get("ticker"),
                        "status": ticker_row.get("current_watchlist_status"),
                        "subindustry_context_risk_status": ticker_row.get("subindustry_context_risk_status"),
                        "layer_context_risk_status": ticker_row.get("layer_context_risk_status"),
                        "close": ticker_row.get("close"),
                        "return_5d": ticker_row.get("return_5d"),
                        "return_10d": ticker_row.get("return_10d"),
                        "return_20d": ticker_row.get("return_20d"),
                        "distance_to_ema20_pct": ticker_row.get("distance_to_ema20_pct"),
                        "trend_state": ticker_row.get("trend_state"),
                        "latest_structure_label": ticker_row.get("latest_structure_label"),
                        "latest_structure_age_trading_days": ticker_row.get("latest_structure_age_trading_days"),
                        "latest_structure_freshness": ticker_row.get("latest_structure_freshness"),
                        "latest_bos_event_type": ticker_row.get("latest_bos_event_type"),
                        "latest_bos_age_trading_days": ticker_row.get("latest_bos_age_trading_days"),
                        "latest_bos_freshness": ticker_row.get("latest_bos_freshness"),
                        "latest_reset_reason": ticker_row.get("latest_reset_reason"),
                        "latest_reset_age_trading_days": ticker_row.get("latest_reset_age_trading_days"),
                        "latest_reset_freshness": ticker_row.get("latest_reset_freshness"),
                        "breakout_signal": ticker_row.get("breakout_signal"),
                        "pullback_signal": ticker_row.get("pullback_signal"),
                        "exit_risk_signal": ticker_row.get("exit_risk_signal"),
                        "exit_risk_severity": ticker_row.get("exit_risk_severity"),
                        "price_data_status": ticker_row.get("price_data_status"),
                    }
                )
    return output_rows


def _build_section_counts(
    *,
    group_rows: list[dict[str, object]],
    ticker_rows: list[dict[str, object]],
    daily_trigger_rows: list[dict[str, object]],
    watchlist_rows: list[dict[str, object]],
    taxonomy_listing_rows: list[dict[str, object]],
) -> dict[str, object]:
    trigger_state_counts: dict[str, int] = {}
    for row in daily_trigger_rows:
        state = str(row.get("classification_state") or "")
        trigger_state_counts[state] = trigger_state_counts.get(state, 0) + 1

    watchlist_status_counts: dict[str, int] = {}
    for row in watchlist_rows:
        status = str(row.get("current_watchlist_status") or "")
        watchlist_status_counts[status] = watchlist_status_counts.get(status, 0) + 1

    return {
        "group_row_count": len(group_rows),
        "ticker_row_count": len(ticker_rows),
        "daily_trigger_row_count": len(daily_trigger_rows),
        "watchlist_row_count": len(watchlist_rows),
        "taxonomy_listing_row_count": len(taxonomy_listing_rows),
        "daily_trigger_state_counts": dict(sorted(trigger_state_counts.items())),
        "watchlist_status_counts": dict(sorted(watchlist_status_counts.items())),
    }


def load_daily_canonical_formatter_data_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    conn.row_factory = sqlite3.Row
    run_row = _load_run(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        run_id=run_id,
    )
    selected_run_id = None if run_row is None else str(run_row["run_id"])
    group_rows = _load_group_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        selected_run_id=selected_run_id,
    )
    ticker_rows = _load_ticker_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        selected_run_id=selected_run_id,
    )
    classification_rows = _load_classification_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        selected_run_id=selected_run_id,
    )
    daily_trigger_rows = _build_daily_trigger_rows(
        ticker_rows=ticker_rows,
        classification_rows=classification_rows,
    )
    watchlist_rows = _build_watchlist_rows(ticker_rows)
    taxonomy_listing_rows = _build_taxonomy_listing_rows(
        group_rows=group_rows,
        ticker_rows=ticker_rows,
    )
    section_counts = _build_section_counts(
        group_rows=group_rows,
        ticker_rows=ticker_rows,
        daily_trigger_rows=daily_trigger_rows,
        watchlist_rows=watchlist_rows,
        taxonomy_listing_rows=taxonomy_listing_rows,
    )
    return {
        "metadata": {
            "signal_date": signal_date,
            "taxonomy_version": taxonomy_version,
            "market": market,
            "requested_run_id": run_id,
            "selected_run_id": selected_run_id,
        },
        "run": run_row,
        "group_rows": group_rows,
        "ticker_rows": ticker_rows,
        "daily_trigger_rows": daily_trigger_rows,
        "watchlist_rows": watchlist_rows,
        "taxonomy_listing_rows": taxonomy_listing_rows,
        "section_counts": section_counts,
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
        },
    }
