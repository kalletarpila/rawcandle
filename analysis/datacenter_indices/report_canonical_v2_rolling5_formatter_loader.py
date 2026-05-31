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
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = 'rolling5'"]
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


def _load_window_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    selected_run_id: str | None,
) -> list[dict[str, object]]:
    where_clauses = ["signal_date = ?", "taxonomy_version = ?", "horizon = 'rolling5'"]
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
        FROM dc_report_context_window_v2
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
        "horizon = 'rolling5'",
        "classification_type = 'rolling5_pullback'",
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


def _build_rolling5_pullback_rows(
    *,
    window_rows: list[dict[str, object]],
    classification_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    window_by_ticker = {
        str(row.get("ticker") or ""): row
        for row in window_rows
        if str(row.get("ticker") or "")
    }
    output_rows: list[dict[str, object]] = []
    for classification_row in classification_rows:
        ticker = str(classification_row.get("ticker") or "")
        window_row = window_by_ticker.get(ticker, {})
        output_rows.append(
            {
                **classification_row,
                "current_watchlist_status": window_row.get("current_watchlist_status"),
                "window_watchlist_status": window_row.get("window_watchlist_status"),
                "pullback_days": window_row.get("pullback_days"),
                "fast_ema10_pullback_days": window_row.get("fast_ema10_pullback_days"),
                "conservative_ema20_pullback_days": window_row.get("conservative_ema20_pullback_days"),
                "exit_risk_days": window_row.get("exit_risk_days"),
                "exit_risk_severity": window_row.get("exit_risk_severity"),
                "latest_exit_reason": window_row.get("latest_exit_reason"),
                "trend_state": window_row.get("trend_state"),
                "latest_structure_label": window_row.get("latest_structure_label"),
                "latest_bos_event_type": window_row.get("latest_bos_event_type"),
                "latest_bos_freshness": window_row.get("latest_bos_freshness"),
                "latest_reset_reason": window_row.get("latest_reset_reason"),
                "latest_reset_freshness": window_row.get("latest_reset_freshness"),
                "primary_layer": window_row.get("primary_layer"),
                "primary_subindustry": window_row.get("primary_subindustry"),
            }
        )
    output_rows.sort(key=lambda row: str(row.get("ticker") or ""))
    return output_rows


def _build_watchlist_rows(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [dict(row) for row in window_rows if int(row.get("is_watchlist") or 0) == 1]
    rows.sort(key=lambda row: str(row.get("ticker") or ""))
    return rows


def _build_repeated_breakout_rows(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [dict(row) for row in window_rows if int(row.get("breakout_days") or 0) > 0]
    rows.sort(
        key=lambda row: (
            -int(row.get("breakout_days") or 0),
            str(row.get("ticker") or ""),
        )
    )
    return rows


def _build_repeated_pullback_rows(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [
        dict(row)
        for row in window_rows
        if (
            int(row.get("pullback_days") or 0) > 0
            or int(row.get("fast_ema10_pullback_days") or 0) > 0
            or int(row.get("conservative_ema20_pullback_days") or 0) > 0
        )
    ]
    rows.sort(
        key=lambda row: (
            -int(row.get("conservative_ema20_pullback_days") or 0),
            -int(row.get("fast_ema10_pullback_days") or 0),
            -int(row.get("pullback_days") or 0),
            str(row.get("ticker") or ""),
        )
    )
    return rows


def _build_repeated_exit_risk_rows(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [dict(row) for row in window_rows if int(row.get("exit_risk_days") or 0) > 0]
    rows.sort(
        key=lambda row: (
            -int(row.get("exit_risk_days") or 0),
            -int(row.get("high_exit_risk_days") or 0),
            -int(row.get("medium_exit_risk_days") or 0),
            str(row.get("ticker") or ""),
        )
    )
    return rows


def _build_taxonomy_listing_rows(
    *,
    group_rows: list[dict[str, object]],
    window_rows: list[dict[str, object]],
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
    for window_row in window_rows:
        layer_name = str(window_row.get("primary_layer") or "")
        subindustry_name = str(window_row.get("primary_subindustry") or "")
        if not layer_name or not subindustry_name:
            continue
        tickers_by_layer_subindustry.setdefault((layer_name, subindustry_name), []).append(window_row)

    output_rows: list[dict[str, object]] = []
    for layer_name in sorted(layer_rows):
        layer_row = layer_rows[layer_name]
        output_rows.append(
            {
                "row_type": "LAYER",
                "layer": layer_name,
                "subindustry": "",
                "ticker": "",
                "timing_state": layer_row.get("timing_state"),
                "overheat_risk_level": layer_row.get("overheat_risk_level"),
                "group_context_risk_status": layer_row.get("group_context_risk_status"),
                "group_current_status": layer_row.get("group_current_status"),
                "group_window_status": layer_row.get("group_window_status"),
                "group_status_change": layer_row.get("group_status_change"),
                "synthetic_trend_classification": layer_row.get("synthetic_trend_classification"),
                "synthetic_latest_structure_label": layer_row.get("synthetic_latest_structure_label"),
                "synthetic_latest_bos_event_type": layer_row.get("synthetic_latest_bos_event_type"),
                "synthetic_latest_bos_freshness": layer_row.get("synthetic_latest_bos_freshness"),
                "synthetic_latest_reset_reason": layer_row.get("synthetic_latest_reset_reason"),
                "synthetic_latest_reset_freshness": layer_row.get("synthetic_latest_reset_freshness"),
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
                    "timing_state": subindustry_row.get("timing_state"),
                    "overheat_risk_level": subindustry_row.get("overheat_risk_level"),
                    "group_context_risk_status": subindustry_row.get("group_context_risk_status"),
                    "group_current_status": subindustry_row.get("group_current_status"),
                    "group_window_status": subindustry_row.get("group_window_status"),
                    "group_status_change": subindustry_row.get("group_status_change"),
                    "synthetic_trend_classification": subindustry_row.get("synthetic_trend_classification"),
                    "synthetic_latest_structure_label": subindustry_row.get("synthetic_latest_structure_label"),
                    "synthetic_latest_bos_event_type": subindustry_row.get("synthetic_latest_bos_event_type"),
                    "synthetic_latest_bos_freshness": subindustry_row.get("synthetic_latest_bos_freshness"),
                    "synthetic_latest_reset_reason": subindustry_row.get("synthetic_latest_reset_reason"),
                    "synthetic_latest_reset_freshness": subindustry_row.get("synthetic_latest_reset_freshness"),
                }
            )
            for window_row in sorted(
                tickers_by_layer_subindustry.get((layer_name, subindustry_name), []),
                key=lambda row: str(row.get("ticker") or ""),
            ):
                output_rows.append(
                    {
                        "row_type": "TICKER",
                        "layer": layer_name,
                        "subindustry": subindustry_name,
                        "ticker": window_row.get("ticker"),
                        "current_watchlist_status": window_row.get("current_watchlist_status"),
                        "window_watchlist_status": window_row.get("window_watchlist_status"),
                        "layer_context_risk_status": window_row.get("layer_context_risk_status"),
                        "subindustry_context_risk_status": window_row.get("subindustry_context_risk_status"),
                        "breakout_days": window_row.get("breakout_days"),
                        "pullback_days": window_row.get("pullback_days"),
                        "fast_ema10_pullback_days": window_row.get("fast_ema10_pullback_days"),
                        "conservative_ema20_pullback_days": window_row.get("conservative_ema20_pullback_days"),
                        "exit_risk_days": window_row.get("exit_risk_days"),
                        "trend_state": window_row.get("trend_state"),
                        "latest_structure_label": window_row.get("latest_structure_label"),
                        "latest_bos_event_type": window_row.get("latest_bos_event_type"),
                        "latest_bos_freshness": window_row.get("latest_bos_freshness"),
                        "latest_reset_reason": window_row.get("latest_reset_reason"),
                        "latest_reset_freshness": window_row.get("latest_reset_freshness"),
                    }
                )
    return output_rows


def _build_section_counts(
    *,
    group_rows: list[dict[str, object]],
    window_rows: list[dict[str, object]],
    rolling5_pullback_rows: list[dict[str, object]],
    watchlist_rows: list[dict[str, object]],
    repeated_breakout_rows: list[dict[str, object]],
    repeated_pullback_rows: list[dict[str, object]],
    repeated_exit_risk_rows: list[dict[str, object]],
    taxonomy_listing_rows: list[dict[str, object]],
) -> dict[str, object]:
    classification_state_counts: dict[str, int] = {}
    for row in rolling5_pullback_rows:
        state = str(row.get("classification_state") or "")
        classification_state_counts[state] = classification_state_counts.get(state, 0) + 1

    current_watchlist_status_counts: dict[str, int] = {}
    window_watchlist_status_counts: dict[str, int] = {}
    for row in window_rows:
        current_status = str(row.get("current_watchlist_status") or "")
        if current_status:
            current_watchlist_status_counts[current_status] = current_watchlist_status_counts.get(current_status, 0) + 1

        window_status = str(row.get("window_watchlist_status") or "")
        if window_status:
            window_watchlist_status_counts[window_status] = window_watchlist_status_counts.get(window_status, 0) + 1

    return {
        "group_row_count": len(group_rows),
        "window_row_count": len(window_rows),
        "rolling5_classification_row_count": len(rolling5_pullback_rows),
        "watchlist_row_count": len(watchlist_rows),
        "repeated_breakout_row_count": len(repeated_breakout_rows),
        "repeated_pullback_row_count": len(repeated_pullback_rows),
        "repeated_exit_risk_row_count": len(repeated_exit_risk_rows),
        "taxonomy_listing_row_count": len(taxonomy_listing_rows),
        "rolling5_classification_state_counts": dict(sorted(classification_state_counts.items())),
        "current_watchlist_status_counts": dict(sorted(current_watchlist_status_counts.items())),
        "window_watchlist_status_counts": dict(sorted(window_watchlist_status_counts.items())),
    }


def load_rolling5_canonical_formatter_data_v2(
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
    window_rows = _load_window_rows(
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
    rolling5_pullback_rows = _build_rolling5_pullback_rows(
        window_rows=window_rows,
        classification_rows=classification_rows,
    )
    watchlist_rows = _build_watchlist_rows(window_rows)
    repeated_breakout_rows = _build_repeated_breakout_rows(window_rows)
    repeated_pullback_rows = _build_repeated_pullback_rows(window_rows)
    repeated_exit_risk_rows = _build_repeated_exit_risk_rows(window_rows)
    taxonomy_listing_rows = _build_taxonomy_listing_rows(
        group_rows=group_rows,
        window_rows=window_rows,
    )
    section_counts = _build_section_counts(
        group_rows=group_rows,
        window_rows=window_rows,
        rolling5_pullback_rows=rolling5_pullback_rows,
        watchlist_rows=watchlist_rows,
        repeated_breakout_rows=repeated_breakout_rows,
        repeated_pullback_rows=repeated_pullback_rows,
        repeated_exit_risk_rows=repeated_exit_risk_rows,
        taxonomy_listing_rows=taxonomy_listing_rows,
    )
    return {
        "metadata": {
            "signal_date": signal_date,
            "taxonomy_version": taxonomy_version,
            "market": market,
            "requested_run_id": run_id,
            "selected_run_id": selected_run_id,
            "horizon": "rolling5",
        },
        "run": run_row,
        "group_rows": group_rows,
        "window_rows": window_rows,
        "rolling5_pullback_rows": rolling5_pullback_rows,
        "watchlist_rows": watchlist_rows,
        "repeated_breakout_rows": repeated_breakout_rows,
        "repeated_pullback_rows": repeated_pullback_rows,
        "repeated_exit_risk_rows": repeated_exit_risk_rows,
        "taxonomy_listing_rows": taxonomy_listing_rows,
        "section_counts": section_counts,
        "deferred_sections": {
            "swing_ma_break_status": "DEFERRED",
            "swing_signal_freshness": "DEFERRED",
            "technical_relevance_context": "DEFERRED",
            "synthetic_event_history": "DEFERRED",
        },
    }
