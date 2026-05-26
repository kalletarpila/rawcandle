from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value).replace(";", ",").replace("\n", " ").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _connect_read_only(db_path: str, *, label: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {db_path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_tickers(value: str | None) -> list[str]:
    if value is None:
        return []
    normalized = value.replace(",", " ")
    return sorted({part.strip().upper() for part in normalized.split() if part.strip()})


def _normalized_action(value: object) -> str:
    return str(value or "").strip()


def _non_empty_action_count(rows: list[dict[str, object]], key: str) -> int:
    return sum(1 for row in rows if _normalized_action(row.get(key)))


def _action_distribution(rows: list[dict[str, object]], key: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        action = _normalized_action(row.get(key))
        if action:
            counts[action] += 1
    return counts


def _load_analysis_rows(
    analysis_db_copy: str,
    report_date: str,
) -> list[dict[str, object]]:
    with _connect_read_only(analysis_db_copy, label="analysis_db_copy") as conn:
        if not _table_exists(conn, ENRICHMENT_TABLE):
            raise ValueError(f"missing required analysis table: {ENRICHMENT_TABLE}")
        rows = conn.execute(
            f"""
            SELECT
                signal_date,
                taxonomy_version,
                ticker,
                action,
                severity,
                primary_reason,
                pullback_validity,
                entry_readiness,
                candidate_priority,
                is_watchlist
            FROM {ENRICHMENT_TABLE}
            WHERE signal_date = ?
            ORDER BY ticker ASC
            """,
            (report_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def _load_optional_json(
    enrichment_json: str | None,
) -> tuple[list[dict[str, object]] | None, list[dict[str, object]] | None]:
    if enrichment_json is None:
        return None, None
    path = Path(enrichment_json)
    if not path.exists():
        raise FileNotFoundError(f"enrichment_json not found: {enrichment_json}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tickers = payload.get("tickers")
    action_summary = payload.get("action_summary")
    if tickers is not None and not isinstance(tickers, list):
        raise ValueError("enrichment_json tickers must be a list")
    if action_summary is not None and not isinstance(action_summary, list):
        raise ValueError("enrichment_json action_summary must be a list")
    return tickers, action_summary


def _dashboard_ticker_map(snapshot) -> dict[str, dict[str, object]]:
    return {
        str(row["ticker"]).strip().upper(): row
        for row in snapshot.tickers
        if str(row["ticker"]).strip()
    }


def _analysis_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        str(row["ticker"]).strip().upper(): row
        for row in rows
        if str(row.get("ticker") or "").strip()
    }


def _json_ticker_map(rows: list[dict[str, object]] | None) -> dict[str, dict[str, object]]:
    if not rows:
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            result[ticker] = row
    return result


def _dashboard_action_summary_distribution(snapshot) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in snapshot.action_summary:
        action = _normalized_action(row.get("action"))
        if action:
            counts[action] += int(row.get("count") or 0)
    return counts


def _json_action_summary_distribution(rows: list[dict[str, object]] | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not rows:
        return counts
    for row in rows:
        action = _normalized_action(row.get("action_label") or row.get("action_bucket"))
        if action:
            counts[action] += int(row.get("ticker_count") or 0)
    return counts


def _select_example_tickers(
    *,
    explicit_tickers: list[str],
    analysis_map: dict[str, dict[str, object]],
    dashboard_map: dict[str, dict[str, object]],
    max_examples: int,
) -> list[str]:
    if explicit_tickers:
        return explicit_tickers
    selected: list[str] = []
    for ticker in sorted(set(analysis_map) | set(dashboard_map)):
        analysis_row = analysis_map.get(ticker, {})
        dashboard_row = dashboard_map.get(ticker, {})
        analysis_action = _normalized_action(analysis_row.get("action"))
        dashboard_action = _normalized_action(dashboard_row.get("action"))
        analysis_is_watchlist = int(analysis_row.get("is_watchlist") or 0)
        if (
            (analysis_action and not dashboard_action)
            or (dashboard_action and not analysis_action)
            or analysis_is_watchlist == 1
        ):
            selected.append(ticker)
        if len(selected) >= max_examples:
            break
    return selected


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose action-field flow across enrichment analysis/dashboard/json layers.",
    )
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db-copy", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--enrichment-json")
    parser.add_argument("--max-examples", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        dashboard_snapshot = load_dashboard_snapshot(
            dashboard_db=args.enrichment_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.enrichment_run_id,
        )
        analysis_rows = _load_analysis_rows(args.analysis_db_copy, args.report_date)
        json_tickers, json_action_summary = _load_optional_json(args.enrichment_json)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    analysis_map = _analysis_ticker_map(analysis_rows)
    dashboard_map = _dashboard_ticker_map(dashboard_snapshot)
    json_map = _json_ticker_map(json_tickers)
    explicit_tickers = _parse_tickers(args.tickers)
    selected_tickers = _select_example_tickers(
        explicit_tickers=explicit_tickers,
        analysis_map=analysis_map,
        dashboard_map=dashboard_map,
        max_examples=args.max_examples,
    )

    analysis_action_counts = _action_distribution(analysis_rows, "action")
    dashboard_action_counts = _action_distribution(dashboard_snapshot.tickers, "action")
    dashboard_action_summary_counts = _dashboard_action_summary_distribution(
        dashboard_snapshot
    )
    json_action_counts = _action_distribution(json_tickers or [], "action_label")
    json_action_summary_counts = _json_action_summary_distribution(json_action_summary)

    analysis_non_empty_action_rows = _non_empty_action_count(analysis_rows, "action")
    dashboard_non_empty_action_rows = _non_empty_action_count(
        dashboard_snapshot.tickers, "action"
    )
    json_non_empty_action_rows = (
        _non_empty_action_count(json_tickers or [], "action_label")
        if json_tickers is not None
        else None
    )
    dashboard_action_summary_non_empty_actions = sum(
        1 for row in dashboard_snapshot.action_summary if _normalized_action(row.get("action"))
    )
    analysis_watchlist_true = sum(
        1 for row in analysis_rows if int(row.get("is_watchlist") or 0) == 1
    )

    actions_present_in_analysis_but_missing_in_dashboard = (
        analysis_non_empty_action_rows > 0 and dashboard_non_empty_action_rows == 0
    )
    actions_missing_already_in_analysis = analysis_non_empty_action_rows == 0
    action_summary_empty_action_row = (
        len(dashboard_snapshot.action_summary) > 0
        and dashboard_action_summary_non_empty_actions == 0
    )
    watchlist_present_in_analysis = analysis_watchlist_true > 0
    if args.enrichment_json is None:
        export_mapping_gap = None
    else:
        export_mapping_gap = (
            actions_present_in_analysis_but_missing_in_dashboard
            and (json_non_empty_action_rows or 0) == 0
        )

    _print_row("section", "aggregate_action_flow")
    _print_row("aggregate_action_flow", "source", "metric", "value")
    _print_row(
        "aggregate_action_flow",
        "analysis_ticker_enrichment",
        "rows",
        len(analysis_rows),
    )
    _print_row(
        "aggregate_action_flow",
        "analysis_ticker_enrichment",
        "non_empty_action_rows",
        analysis_non_empty_action_rows,
    )
    _print_row(
        "aggregate_action_flow",
        "analysis_ticker_enrichment",
        "distinct_actions",
        len(analysis_action_counts),
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_dashboard_snapshot",
        "tickers",
        len(dashboard_snapshot.tickers),
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_dashboard_snapshot",
        "non_empty_action_rows",
        dashboard_non_empty_action_rows,
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_dashboard_snapshot",
        "distinct_actions",
        len(dashboard_action_counts),
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_dashboard_snapshot",
        "action_summary_rows",
        len(dashboard_snapshot.action_summary),
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_dashboard_snapshot",
        "action_summary_non_empty_actions",
        dashboard_action_summary_non_empty_actions,
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_json",
        "tickers",
        len(json_tickers) if json_tickers is not None else "",
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_json",
        "non_empty_action_rows",
        json_non_empty_action_rows if json_non_empty_action_rows is not None else "",
    )
    _print_row(
        "aggregate_action_flow",
        "enrichment_json",
        "distinct_actions",
        len(json_action_counts) if json_tickers is not None else "",
    )

    _print_row("section", "action_summary_rows")
    _print_row("action_summary_rows", "source", "action", "count")
    for action in sorted(analysis_action_counts):
        _print_row(
            "action_summary_rows",
            "analysis_ticker_enrichment",
            action,
            analysis_action_counts[action],
        )
    for action in sorted(dashboard_action_summary_counts):
        _print_row(
            "action_summary_rows",
            "dashboard_snapshot",
            action,
            dashboard_action_summary_counts[action],
        )
    for action in sorted(json_action_summary_counts):
        _print_row(
            "action_summary_rows",
            "enrichment_json",
            action,
            json_action_summary_counts[action],
        )

    _print_row("section", "ticker_action_flow_examples")
    _print_row(
        "ticker_action_flow_examples",
        "ticker",
        "analysis_action",
        "analysis_severity",
        "analysis_primary_reason",
        "analysis_pullback_validity",
        "analysis_entry_readiness",
        "analysis_candidate_priority",
        "analysis_is_watchlist",
        "dashboard_action",
        "dashboard_current_status",
        "dashboard_is_watchlist",
        "json_action",
    )
    for ticker in selected_tickers:
        analysis_row = analysis_map.get(ticker, {})
        dashboard_row = dashboard_map.get(ticker, {})
        json_row = json_map.get(ticker, {})
        _print_row(
            "ticker_action_flow_examples",
            ticker,
            analysis_row.get("action"),
            analysis_row.get("severity"),
            analysis_row.get("primary_reason"),
            analysis_row.get("pullback_validity"),
            analysis_row.get("entry_readiness"),
            analysis_row.get("candidate_priority"),
            analysis_row.get("is_watchlist"),
            dashboard_row.get("action"),
            dashboard_row.get("current_status"),
            dashboard_row.get("is_watchlist"),
            json_row.get("action_label") or json_row.get("action_bucket"),
        )

    _print_row("section", "mapping_gap_hypothesis")
    _print_row("mapping_gap_hypothesis", "hypothesis", "status", "evidence")
    _print_row(
        "mapping_gap_hypothesis",
        "ACTIONS_PRESENT_IN_ANALYSIS_BUT_MISSING_IN_DASHBOARD",
        "LIKELY" if actions_present_in_analysis_but_missing_in_dashboard else "UNLIKELY",
        f"analysis_non_empty_action_rows={analysis_non_empty_action_rows};dashboard_non_empty_action_rows={dashboard_non_empty_action_rows}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "ACTIONS_MISSING_ALREADY_IN_ANALYSIS",
        "LIKELY" if actions_missing_already_in_analysis else "UNLIKELY",
        f"analysis_non_empty_action_rows={analysis_non_empty_action_rows}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "ACTION_SUMMARY_EMPTY_ACTION_ROW",
        "LIKELY" if action_summary_empty_action_row else "UNLIKELY",
        f"dashboard_action_summary_rows={len(dashboard_snapshot.action_summary)};dashboard_action_summary_non_empty_actions={dashboard_action_summary_non_empty_actions}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "WATCHLIST_PRESENT_IN_ANALYSIS",
        "LIKELY" if watchlist_present_in_analysis else "UNLIKELY",
        f"analysis_watchlist_true={analysis_watchlist_true}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "EXPORT_MAPPING_GAP_LIKELY",
        (
            "UNKNOWN"
            if export_mapping_gap is None
            else ("LIKELY" if export_mapping_gap else "UNLIKELY")
        ),
        f"analysis_non_empty_action_rows={analysis_non_empty_action_rows};dashboard_non_empty_action_rows={dashboard_non_empty_action_rows};json_non_empty_action_rows={_cell(json_non_empty_action_rows)}",
    )

    _print_row("section", "summary")
    _print_row("SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.status=OK")
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.report_date={args.report_date}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.analysis_rows={len(analysis_rows)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.analysis_non_empty_action_rows="
        f"{analysis_non_empty_action_rows}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.dashboard_tickers={len(dashboard_snapshot.tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.dashboard_non_empty_action_rows="
        f"{dashboard_non_empty_action_rows}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.dashboard_action_summary_rows="
        f"{len(dashboard_snapshot.action_summary)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.dashboard_action_summary_non_empty_actions="
        f"{dashboard_action_summary_non_empty_actions}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.analysis_watchlist_true={analysis_watchlist_true}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_action_flow_diagnosis.examples={len(selected_tickers)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
