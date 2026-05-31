from __future__ import annotations

import csv
import io
import sqlite3


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _markdown_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _append_markdown_table(
    lines: list[str],
    *,
    headers: list[str],
    rows: list[list[object]],
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_markdown_value(value) for value in row) + " |")
    lines.append("")


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

    subindustries_by_layer: dict[str, set[str]] = {}
    for subindustry_name, subindustry_row in subindustry_rows.items():
        parent_layer_name = str(subindustry_row.get("parent_group_name") or "")
        if parent_layer_name:
            subindustries_by_layer.setdefault(parent_layer_name, set()).add(subindustry_name)
    for layer_name, subindustry_name in tickers_by_layer_subindustry:
        subindustries_by_layer.setdefault(layer_name, set()).add(subindustry_name)

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
        subindustries_for_layer = sorted(subindustries_by_layer.get(layer_name, set()))
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


def build_markdown_rolling5_canonical_v2_report(formatter_data: dict[str, object]) -> str:
    metadata = dict(formatter_data.get("metadata") or {})
    run = formatter_data.get("run")
    window_rows = list(formatter_data.get("window_rows") or [])
    rolling5_pullback_rows = list(formatter_data.get("rolling5_pullback_rows") or [])
    watchlist_rows = list(formatter_data.get("watchlist_rows") or [])
    repeated_breakout_rows = list(formatter_data.get("repeated_breakout_rows") or [])
    repeated_pullback_rows = list(formatter_data.get("repeated_pullback_rows") or [])
    repeated_exit_risk_rows = list(formatter_data.get("repeated_exit_risk_rows") or [])
    taxonomy_listing_rows = list(formatter_data.get("taxonomy_listing_rows") or [])
    section_counts = dict(formatter_data.get("section_counts") or {})
    deferred_sections = dict(formatter_data.get("deferred_sections") or {})

    window_start_date = ""
    window_end_date = ""
    valid_signal_dates = ""
    if window_rows:
        window_start_date = _markdown_value(window_rows[0].get("window_start_date"))
        window_end_date = _markdown_value(window_rows[0].get("window_end_date"))
        valid_signal_dates = _markdown_value(window_rows[0].get("valid_signal_dates"))

    lines: list[str] = [
        "# Datacenter Rolling5 Canonical V2 Report",
        "",
        "## 1. Title / metadata",
        f"signal_date: {_markdown_value(metadata.get('signal_date'))}",
        f"taxonomy_version: {_markdown_value(metadata.get('taxonomy_version'))}",
        f"selected_run_id: {_markdown_value(metadata.get('selected_run_id'))}",
        f"status: {_markdown_value((run or {}).get('status') if isinstance(run, dict) else None)}",
        f"horizon: {_markdown_value(metadata.get('horizon'))}",
        f"window_start_date: {window_start_date}",
        f"window_end_date: {window_end_date}",
        f"valid_signal_dates: {valid_signal_dates}",
        "",
        "## 2. Summary counts",
        f"- group_count: {_markdown_value(section_counts.get('group_row_count'))}",
        f"- window_row_count: {_markdown_value(section_counts.get('window_row_count'))}",
        f"- rolling5_classification_count: {_markdown_value(section_counts.get('rolling5_classification_row_count'))}",
        f"- watchlist_row_count: {_markdown_value(section_counts.get('watchlist_row_count'))}",
        f"- repeated_breakout_row_count: {_markdown_value(section_counts.get('repeated_breakout_row_count'))}",
        f"- repeated_pullback_row_count: {_markdown_value(section_counts.get('repeated_pullback_row_count'))}",
        f"- repeated_exit_risk_row_count: {_markdown_value(section_counts.get('repeated_exit_risk_row_count'))}",
        "",
        "### Rolling5 classification state counts",
    ]

    classification_state_counts = dict(section_counts.get("rolling5_classification_state_counts") or {})
    if classification_state_counts:
        for state, count in sorted(classification_state_counts.items()):
            lines.append(f"- {state}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "### Current watchlist status counts"])
    current_watchlist_status_counts = dict(section_counts.get("current_watchlist_status_counts") or {})
    if current_watchlist_status_counts:
        for status, count in sorted(current_watchlist_status_counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "### Window watchlist status counts"])
    window_watchlist_status_counts = dict(section_counts.get("window_watchlist_status_counts") or {})
    if window_watchlist_status_counts:
        for status, count in sorted(window_watchlist_status_counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## 3. Rolling5 pullback rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "classification_state",
            "primary_reason",
            "blocking_reason",
            "next_action",
            "current_watchlist_status",
            "window_watchlist_status",
            "pullback_days",
            "fast_ema10_pullback_days",
            "conservative_ema20_pullback_days",
            "exit_risk_days",
            "exit_risk_severity",
            "latest_exit_reason",
            "primary_layer",
            "primary_subindustry",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("classification_state"),
                row.get("primary_reason"),
                row.get("blocking_reason"),
                row.get("next_action"),
                row.get("current_watchlist_status"),
                row.get("window_watchlist_status"),
                row.get("pullback_days"),
                row.get("fast_ema10_pullback_days"),
                row.get("conservative_ema20_pullback_days"),
                row.get("exit_risk_days"),
                row.get("exit_risk_severity"),
                row.get("latest_exit_reason"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
            ]
            for row in rolling5_pullback_rows
        ],
    )

    lines.append("## 4. Watchlist rows")
    if watchlist_rows:
        _append_markdown_table(
            lines,
            headers=[
                "ticker",
                "current_watchlist_status",
                "window_watchlist_status",
                "primary_layer",
                "primary_subindustry",
                "layer_context_risk_status",
                "subindustry_context_risk_status",
                "breakout_days",
                "pullback_days",
                "exit_risk_days",
            ],
            rows=[
                [
                    row.get("ticker"),
                    row.get("current_watchlist_status"),
                    row.get("window_watchlist_status"),
                    row.get("primary_layer"),
                    row.get("primary_subindustry"),
                    row.get("layer_context_risk_status"),
                    row.get("subindustry_context_risk_status"),
                    row.get("breakout_days"),
                    row.get("pullback_days"),
                    row.get("exit_risk_days"),
                ]
                for row in watchlist_rows
            ],
        )
    else:
        lines.extend(["- none", ""])

    lines.append("## 5. Repeated breakout rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "breakout_days",
            "first_signal_date",
            "last_signal_date",
            "current_watchlist_status",
            "window_watchlist_status",
            "trend_state",
            "latest_structure_label",
            "primary_layer",
            "primary_subindustry",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("breakout_days"),
                row.get("first_signal_date"),
                row.get("last_signal_date"),
                row.get("current_watchlist_status"),
                row.get("window_watchlist_status"),
                row.get("trend_state"),
                row.get("latest_structure_label"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
            ]
            for row in repeated_breakout_rows
        ],
    )

    lines.append("## 6. Repeated pullback rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "pullback_days",
            "fast_ema10_pullback_days",
            "conservative_ema20_pullback_days",
            "first_signal_date",
            "last_signal_date",
            "current_watchlist_status",
            "window_watchlist_status",
            "trend_state",
            "latest_structure_label",
            "primary_layer",
            "primary_subindustry",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("pullback_days"),
                row.get("fast_ema10_pullback_days"),
                row.get("conservative_ema20_pullback_days"),
                row.get("first_signal_date"),
                row.get("last_signal_date"),
                row.get("current_watchlist_status"),
                row.get("window_watchlist_status"),
                row.get("trend_state"),
                row.get("latest_structure_label"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
            ]
            for row in repeated_pullback_rows
        ],
    )

    lines.append("## 7. Repeated exit-risk rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "exit_risk_days",
            "high_exit_risk_days",
            "medium_exit_risk_days",
            "exit_risk_severity",
            "latest_exit_reason",
            "current_watchlist_status",
            "window_watchlist_status",
            "trend_state",
            "latest_structure_label",
            "primary_layer",
            "primary_subindustry",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("exit_risk_days"),
                row.get("high_exit_risk_days"),
                row.get("medium_exit_risk_days"),
                row.get("exit_risk_severity"),
                row.get("latest_exit_reason"),
                row.get("current_watchlist_status"),
                row.get("window_watchlist_status"),
                row.get("trend_state"),
                row.get("latest_structure_label"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
            ]
            for row in repeated_exit_risk_rows
        ],
    )

    lines.append("## 8. Taxonomy listing preview")
    _append_markdown_table(
        lines,
        headers=[
            "row_type",
            "layer",
            "subindustry",
            "ticker",
            "timing_state",
            "overheat_risk_level",
            "group_current_status",
            "group_window_status",
            "group_status_change",
            "current_watchlist_status",
            "window_watchlist_status",
        ],
        rows=[
            [
                row.get("row_type"),
                row.get("layer"),
                row.get("subindustry"),
                row.get("ticker"),
                row.get("timing_state"),
                row.get("overheat_risk_level"),
                row.get("group_current_status"),
                row.get("group_window_status"),
                row.get("group_status_change"),
                row.get("current_watchlist_status"),
                row.get("window_watchlist_status"),
            ]
            for row in taxonomy_listing_rows
        ],
    )

    lines.append("## 9. Deferred sections")
    labels = {
        "swing_ma_break_status": "detailed swing MA break status",
        "swing_signal_freshness": "detailed swing signal freshness",
        "technical_relevance_context": "full technical relevance context",
        "synthetic_event_history": "full synthetic event history",
    }
    if deferred_sections:
        for key in sorted(deferred_sections):
            lines.append(f"- {labels.get(key, key)}: {_markdown_value(deferred_sections.get(key))}")
    else:
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def build_csv_rolling5_canonical_v2_report(formatter_data: dict[str, object]) -> str:
    metadata = dict(formatter_data.get("metadata") or {})
    run = formatter_data.get("run")
    window_rows = list(formatter_data.get("window_rows") or [])
    rolling5_pullback_rows = list(formatter_data.get("rolling5_pullback_rows") or [])
    watchlist_rows = list(formatter_data.get("watchlist_rows") or [])
    repeated_breakout_rows = list(formatter_data.get("repeated_breakout_rows") or [])
    repeated_pullback_rows = list(formatter_data.get("repeated_pullback_rows") or [])
    repeated_exit_risk_rows = list(formatter_data.get("repeated_exit_risk_rows") or [])
    taxonomy_listing_rows = list(formatter_data.get("taxonomy_listing_rows") or [])
    section_counts = dict(formatter_data.get("section_counts") or {})
    deferred_sections = dict(formatter_data.get("deferred_sections") or {})

    window_start_date = ""
    window_end_date = ""
    valid_signal_dates = ""
    if window_rows:
        window_start_date = _csv_value(window_rows[0].get("window_start_date"))
        window_end_date = _csv_value(window_rows[0].get("window_end_date"))
        valid_signal_dates = _csv_value(window_rows[0].get("valid_signal_dates"))

    fieldnames = [
        "section",
        "key",
        "value",
        "ticker",
        "classification_state",
        "primary_reason",
        "blocking_reason",
        "next_action",
        "current_watchlist_status",
        "window_watchlist_status",
        "primary_layer",
        "primary_subindustry",
        "layer_context_risk_status",
        "subindustry_context_risk_status",
        "breakout_days",
        "pullback_days",
        "fast_ema10_pullback_days",
        "conservative_ema20_pullback_days",
        "exit_risk_days",
        "high_exit_risk_days",
        "medium_exit_risk_days",
        "exit_risk_severity",
        "latest_exit_reason",
        "first_signal_date",
        "last_signal_date",
        "trend_state",
        "latest_structure_label",
        "row_type",
        "layer",
        "subindustry",
        "timing_state",
        "overheat_risk_level",
        "group_current_status",
        "group_window_status",
        "group_status_change",
        "deferred_section",
        "status",
        "reason",
    ]

    def _empty_row(section: str) -> dict[str, str]:
        row = {fieldname: "" for fieldname in fieldnames}
        row["section"] = section
        return row

    rows: list[dict[str, str]] = []

    metadata_rows = [
        ("signal_date", metadata.get("signal_date")),
        ("taxonomy_version", metadata.get("taxonomy_version")),
        ("selected_run_id", metadata.get("selected_run_id")),
        ("status", (run or {}).get("status") if isinstance(run, dict) else None),
        ("horizon", metadata.get("horizon")),
        ("window_start_date", window_start_date),
        ("window_end_date", window_end_date),
        ("valid_signal_dates", valid_signal_dates),
    ]
    for key, value in metadata_rows:
        row = _empty_row("metadata")
        row["key"] = str(key)
        row["value"] = _csv_value(value)
        rows.append(row)

    summary_rows = [
        ("group_count", section_counts.get("group_row_count")),
        ("window_row_count", section_counts.get("window_row_count")),
        ("rolling5_classification_count", section_counts.get("rolling5_classification_row_count")),
        ("watchlist_row_count", section_counts.get("watchlist_row_count")),
        ("repeated_breakout_row_count", section_counts.get("repeated_breakout_row_count")),
        ("repeated_pullback_row_count", section_counts.get("repeated_pullback_row_count")),
        ("repeated_exit_risk_row_count", section_counts.get("repeated_exit_risk_row_count")),
    ]
    for key, value in summary_rows:
        row = _empty_row("summary_counts")
        row["key"] = str(key)
        row["value"] = _csv_value(value)
        rows.append(row)

    for key, value in sorted(dict(section_counts.get("rolling5_classification_state_counts") or {}).items()):
        row = _empty_row("rolling5_classification_state_counts")
        row["key"] = str(key)
        row["value"] = _csv_value(value)
        rows.append(row)

    for key, value in sorted(dict(section_counts.get("current_watchlist_status_counts") or {}).items()):
        row = _empty_row("current_watchlist_status_counts")
        row["key"] = str(key)
        row["value"] = _csv_value(value)
        rows.append(row)

    for key, value in sorted(dict(section_counts.get("window_watchlist_status_counts") or {}).items()):
        row = _empty_row("window_watchlist_status_counts")
        row["key"] = str(key)
        row["value"] = _csv_value(value)
        rows.append(row)

    for source_row in rolling5_pullback_rows:
        row = _empty_row("rolling5_pullback_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["classification_state"] = _csv_value(source_row.get("classification_state"))
        row["primary_reason"] = _csv_value(source_row.get("primary_reason"))
        row["blocking_reason"] = _csv_value(source_row.get("blocking_reason"))
        row["next_action"] = _csv_value(source_row.get("next_action"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        row["pullback_days"] = _csv_value(source_row.get("pullback_days"))
        row["fast_ema10_pullback_days"] = _csv_value(source_row.get("fast_ema10_pullback_days"))
        row["conservative_ema20_pullback_days"] = _csv_value(source_row.get("conservative_ema20_pullback_days"))
        row["exit_risk_days"] = _csv_value(source_row.get("exit_risk_days"))
        row["exit_risk_severity"] = _csv_value(source_row.get("exit_risk_severity"))
        row["latest_exit_reason"] = _csv_value(source_row.get("latest_exit_reason"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        rows.append(row)

    for source_row in watchlist_rows:
        row = _empty_row("watchlist_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        row["layer_context_risk_status"] = _csv_value(source_row.get("layer_context_risk_status"))
        row["subindustry_context_risk_status"] = _csv_value(source_row.get("subindustry_context_risk_status"))
        row["breakout_days"] = _csv_value(source_row.get("breakout_days"))
        row["pullback_days"] = _csv_value(source_row.get("pullback_days"))
        row["exit_risk_days"] = _csv_value(source_row.get("exit_risk_days"))
        rows.append(row)

    for source_row in repeated_breakout_rows:
        row = _empty_row("repeated_breakout_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["breakout_days"] = _csv_value(source_row.get("breakout_days"))
        row["first_signal_date"] = _csv_value(source_row.get("first_signal_date"))
        row["last_signal_date"] = _csv_value(source_row.get("last_signal_date"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        row["trend_state"] = _csv_value(source_row.get("trend_state"))
        row["latest_structure_label"] = _csv_value(source_row.get("latest_structure_label"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        rows.append(row)

    for source_row in repeated_pullback_rows:
        row = _empty_row("repeated_pullback_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["pullback_days"] = _csv_value(source_row.get("pullback_days"))
        row["fast_ema10_pullback_days"] = _csv_value(source_row.get("fast_ema10_pullback_days"))
        row["conservative_ema20_pullback_days"] = _csv_value(source_row.get("conservative_ema20_pullback_days"))
        row["first_signal_date"] = _csv_value(source_row.get("first_signal_date"))
        row["last_signal_date"] = _csv_value(source_row.get("last_signal_date"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        row["trend_state"] = _csv_value(source_row.get("trend_state"))
        row["latest_structure_label"] = _csv_value(source_row.get("latest_structure_label"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        rows.append(row)

    for source_row in repeated_exit_risk_rows:
        row = _empty_row("repeated_exit_risk_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["exit_risk_days"] = _csv_value(source_row.get("exit_risk_days"))
        row["high_exit_risk_days"] = _csv_value(source_row.get("high_exit_risk_days"))
        row["medium_exit_risk_days"] = _csv_value(source_row.get("medium_exit_risk_days"))
        row["exit_risk_severity"] = _csv_value(source_row.get("exit_risk_severity"))
        row["latest_exit_reason"] = _csv_value(source_row.get("latest_exit_reason"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        row["trend_state"] = _csv_value(source_row.get("trend_state"))
        row["latest_structure_label"] = _csv_value(source_row.get("latest_structure_label"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        rows.append(row)

    for source_row in taxonomy_listing_rows:
        row = _empty_row("taxonomy_listing_preview")
        row["row_type"] = _csv_value(source_row.get("row_type"))
        row["layer"] = _csv_value(source_row.get("layer"))
        row["subindustry"] = _csv_value(source_row.get("subindustry"))
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["timing_state"] = _csv_value(source_row.get("timing_state"))
        row["overheat_risk_level"] = _csv_value(source_row.get("overheat_risk_level"))
        row["group_current_status"] = _csv_value(source_row.get("group_current_status"))
        row["group_window_status"] = _csv_value(source_row.get("group_window_status"))
        row["group_status_change"] = _csv_value(source_row.get("group_status_change"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["window_watchlist_status"] = _csv_value(source_row.get("window_watchlist_status"))
        rows.append(row)

    deferred_reasons = {
        "swing_ma_break_status": "detailed swing MA break status",
        "swing_signal_freshness": "detailed swing signal freshness",
        "technical_relevance_context": "full technical relevance context",
        "synthetic_event_history": "full synthetic event history",
    }
    for deferred_key, deferred_status in deferred_sections.items():
        row = _empty_row("deferred_sections")
        row["deferred_section"] = str(deferred_key)
        row["status"] = _csv_value(deferred_status)
        row["reason"] = deferred_reasons.get(str(deferred_key), "")
        rows.append(row)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
