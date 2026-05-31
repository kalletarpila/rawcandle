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
                "pct_above_ema20": layer_row.get("pct_above_ema20"),
                "pct_above_ma10": layer_row.get("pct_above_ma10"),
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
                    "pct_above_ema20": subindustry_row.get("pct_above_ema20"),
                    "pct_above_ma10": subindustry_row.get("pct_above_ma10"),
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


def build_markdown_daily_canonical_v2_report(formatter_data: dict[str, object]) -> str:
    metadata = dict(formatter_data.get("metadata") or {})
    run = formatter_data.get("run")
    group_rows = list(formatter_data.get("group_rows") or [])
    daily_trigger_rows = list(formatter_data.get("daily_trigger_rows") or [])
    watchlist_rows = list(formatter_data.get("watchlist_rows") or [])
    taxonomy_listing_rows = list(formatter_data.get("taxonomy_listing_rows") or [])
    section_counts = dict(formatter_data.get("section_counts") or {})
    deferred_sections = dict(formatter_data.get("deferred_sections") or {})

    group_lookup = {
        (str(row.get("group_type") or ""), str(row.get("group_name") or "")): row
        for row in group_rows
    }

    lines: list[str] = [
        "# Datacenter Daily Canonical V2 Report",
        "",
        "## 1. Title / metadata",
        f"signal_date: {_markdown_value(metadata.get('signal_date'))}",
        f"taxonomy_version: {_markdown_value(metadata.get('taxonomy_version'))}",
        f"selected_run_id: {_markdown_value(metadata.get('selected_run_id'))}",
        f"status: {_markdown_value((run or {}).get('status') if isinstance(run, dict) else None)}",
        "",
        "## 2. Summary counts",
        f"- ticker_count: {_markdown_value(section_counts.get('ticker_row_count'))}",
        f"- group_count: {_markdown_value(section_counts.get('group_row_count'))}",
        f"- daily_trigger_count: {_markdown_value(section_counts.get('daily_trigger_row_count'))}",
        f"- watchlist_count: {_markdown_value(section_counts.get('watchlist_row_count'))}",
        "",
        "### Trigger state counts",
    ]
    trigger_state_counts = dict(section_counts.get("daily_trigger_state_counts") or {})
    if trigger_state_counts:
        for state, count in sorted(trigger_state_counts.items()):
            lines.append(f"- {state}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "### Watchlist status counts"])
    watchlist_status_counts = dict(section_counts.get("watchlist_status_counts") or {})
    if watchlist_status_counts:
        for status, count in sorted(watchlist_status_counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## 3. Daily trigger rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "classification_state",
            "primary_reason",
            "blocking_reason",
            "next_action",
            "current_watchlist_status",
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
                row.get("primary_layer"),
                row.get("primary_subindustry"),
            ]
            for row in daily_trigger_rows
        ],
    )

    lines.append("## 4. Watchlist rows")
    _append_markdown_table(
        lines,
        headers=[
            "ticker",
            "current_watchlist_status",
            "primary_layer",
            "primary_subindustry",
            "layer_context_risk_status",
            "subindustry_context_risk_status",
            "breakout_signal",
            "pullback_signal",
            "exit_risk_signal",
        ],
        rows=[
            [
                row.get("ticker"),
                row.get("current_watchlist_status"),
                row.get("primary_layer"),
                row.get("primary_subindustry"),
                row.get("layer_context_risk_status"),
                row.get("subindustry_context_risk_status"),
                row.get("breakout_signal"),
                row.get("pullback_signal"),
                row.get("exit_risk_signal"),
            ]
            for row in watchlist_rows
        ],
    )

    lines.append("## 5. Taxonomy listing preview")
    taxonomy_rows: list[list[object]] = []
    for row in taxonomy_listing_rows:
        row_type = str(row.get("row_type") or "")
        layer_name = str(row.get("layer") or "")
        subindustry_name = str(row.get("subindustry") or "")
        overheat_risk_level = ""
        if row_type == "LAYER":
            overheat_risk_level = _markdown_value(
                group_lookup.get(("layer", layer_name), {}).get("overheat_risk_level")
            )
        elif row_type == "SUBINDUSTRY":
            overheat_risk_level = _markdown_value(
                group_lookup.get(("subindustry", subindustry_name), {}).get("overheat_risk_level")
            )
        taxonomy_rows.append(
            [
                row.get("row_type"),
                row.get("layer"),
                row.get("subindustry"),
                row.get("ticker"),
                row.get("status") if row_type in {"LAYER", "SUBINDUSTRY"} else "",
                overheat_risk_level,
                row.get("pct_above_ema20"),
                row.get("pct_above_ma10"),
                row.get("distance_to_ema20_pct"),
                row.get("status") if row_type == "TICKER" else "",
            ]
        )
    _append_markdown_table(
        lines,
        headers=[
            "row_type",
            "layer",
            "subindustry",
            "ticker",
            "timing_state",
            "overheat_risk_level",
            "pct_above_ema20",
            "pct_above_ma10",
            "distance_to_ema20_pct",
            "current_watchlist_status",
        ],
        rows=taxonomy_rows,
    )

    lines.append("## 6. Deferred sections")
    labels = {
        "swing_ma_break_status": "detailed swing MA break status",
        "swing_signal_freshness": "detailed swing signal freshness",
        "technical_relevance_context": "full technical relevance context",
    }
    if deferred_sections:
        for key in sorted(deferred_sections):
            lines.append(f"- {labels.get(key, key)}: {_markdown_value(deferred_sections.get(key))}")
    else:
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def build_csv_daily_canonical_v2_report(formatter_data: dict[str, object]) -> str:
    metadata = dict(formatter_data.get("metadata") or {})
    run = formatter_data.get("run")
    daily_trigger_rows = list(formatter_data.get("daily_trigger_rows") or [])
    watchlist_rows = list(formatter_data.get("watchlist_rows") or [])
    taxonomy_listing_rows = list(formatter_data.get("taxonomy_listing_rows") or [])
    section_counts = dict(formatter_data.get("section_counts") or {})
    deferred_sections = dict(formatter_data.get("deferred_sections") or {})

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
        "primary_layer",
        "primary_subindustry",
        "layer_context_risk_status",
        "subindustry_context_risk_status",
        "breakout_signal",
        "pullback_signal",
        "exit_risk_signal",
        "row_type",
        "layer",
        "subindustry",
        "timing_state",
        "overheat_risk_level",
        "pct_above_ema20",
        "pct_above_ma10",
        "distance_to_ema20_pct",
        "deferred_section",
        "status",
        "reason",
    ]

    def _csv_value(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    def _empty_row(section: str) -> dict[str, str]:
        row = {field: "" for field in fieldnames}
        row["section"] = section
        return row

    rows: list[dict[str, str]] = []

    for key in ("signal_date", "taxonomy_version", "selected_run_id"):
        row = _empty_row("metadata")
        row["key"] = key
        row["value"] = _csv_value(metadata.get(key))
        rows.append(row)
    row = _empty_row("metadata")
    row["key"] = "status"
    row["value"] = _csv_value((run or {}).get("status") if isinstance(run, dict) else None)
    rows.append(row)

    for key, value in (
        ("ticker_count", section_counts.get("ticker_row_count")),
        ("group_count", section_counts.get("group_row_count")),
        ("daily_trigger_count", section_counts.get("daily_trigger_row_count")),
        ("watchlist_count", section_counts.get("watchlist_row_count")),
    ):
        row = _empty_row("summary_counts")
        row["key"] = key
        row["value"] = _csv_value(value)
        rows.append(row)

    trigger_state_counts = dict(section_counts.get("daily_trigger_state_counts") or {})
    for key, value in sorted(trigger_state_counts.items()):
        row = _empty_row("trigger_state_counts")
        row["key"] = key
        row["value"] = _csv_value(value)
        rows.append(row)

    watchlist_status_counts = dict(section_counts.get("watchlist_status_counts") or {})
    if watchlist_status_counts:
        for key, value in sorted(watchlist_status_counts.items()):
            row = _empty_row("watchlist_status_counts")
            row["key"] = key
            row["value"] = _csv_value(value)
            rows.append(row)
    else:
        row = _empty_row("watchlist_status_counts")
        row["key"] = "none"
        row["value"] = ""
        rows.append(row)

    for source_row in daily_trigger_rows:
        row = _empty_row("daily_trigger_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["classification_state"] = _csv_value(source_row.get("classification_state"))
        row["primary_reason"] = _csv_value(source_row.get("primary_reason"))
        row["blocking_reason"] = _csv_value(source_row.get("blocking_reason"))
        row["next_action"] = _csv_value(source_row.get("next_action"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        rows.append(row)

    for source_row in watchlist_rows:
        row = _empty_row("watchlist_rows")
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        row["primary_layer"] = _csv_value(source_row.get("primary_layer"))
        row["primary_subindustry"] = _csv_value(source_row.get("primary_subindustry"))
        row["layer_context_risk_status"] = _csv_value(source_row.get("layer_context_risk_status"))
        row["subindustry_context_risk_status"] = _csv_value(source_row.get("subindustry_context_risk_status"))
        row["breakout_signal"] = _csv_value(source_row.get("breakout_signal"))
        row["pullback_signal"] = _csv_value(source_row.get("pullback_signal"))
        row["exit_risk_signal"] = _csv_value(source_row.get("exit_risk_signal"))
        rows.append(row)

    for source_row in taxonomy_listing_rows:
        row = _empty_row("taxonomy_listing_preview")
        row["row_type"] = _csv_value(source_row.get("row_type"))
        row["layer"] = _csv_value(source_row.get("layer"))
        row["subindustry"] = _csv_value(source_row.get("subindustry"))
        row["ticker"] = _csv_value(source_row.get("ticker"))
        row["timing_state"] = _csv_value(source_row.get("status"))
        row["overheat_risk_level"] = _csv_value(source_row.get("overheat_risk_level"))
        row["pct_above_ema20"] = _csv_value(source_row.get("pct_above_ema20"))
        row["pct_above_ma10"] = _csv_value(source_row.get("pct_above_ma10"))
        row["distance_to_ema20_pct"] = _csv_value(source_row.get("distance_to_ema20_pct"))
        row["current_watchlist_status"] = _csv_value(source_row.get("current_watchlist_status"))
        rows.append(row)

    deferred_reasons = {
        "swing_ma_break_status": "detailed swing MA break status",
        "swing_signal_freshness": "detailed swing signal freshness",
        "technical_relevance_context": "full technical relevance context",
    }
    for deferred_key, deferred_status in deferred_sections.items():
        row = _empty_row("deferred_sections")
        row["deferred_section"] = deferred_key
        row["status"] = _csv_value(deferred_status)
        row["reason"] = deferred_reasons.get(deferred_key, "")
        rows.append(row)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
