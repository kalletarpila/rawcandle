from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot

_KNOWN_EXTRA_GROUPS = {
    "CPUs",
    "Racks, cabinets, enclosures",
    "Virtualization / cloud software",
    "Mechanical infrastructure",
}
_ACCEPTANCE_PREFIX = "datacenter_dashboard_enrichment_acceptance_report"
_DEFAULT_TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").replace(";", ",").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _fail(message: str) -> int:
    print(f"ERROR {_ACCEPTANCE_PREFIX}: {message}", file=sys.stderr)
    return 1


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"db not found: {db_path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _require_table(conn: sqlite3.Connection, table_name: str) -> None:
    if not _table_exists(conn, table_name):
        raise ValueError(f"required table missing: {table_name}")


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _normalize(value: object) -> str:
    return "" if value is None else str(value).strip()


def _normalized_action(value: object) -> str:
    return _normalize(value).upper()


def _market_map_key(row: dict[str, object]) -> str:
    return "|".join(
        [
            _normalize(row.get("market_level")),
            _normalize(row.get("name")),
            _normalize(row.get("parent_name")),
            _normalize(row.get("layer")),
            _normalize(row.get("subindustry")),
        ]
    )


def _market_map_semantic_name(row: dict[str, object]) -> str:
    return (
        _normalize(row.get("subindustry"))
        or _normalize(row.get("layer"))
        or _normalize(row.get("name"))
    )


def _count_by_action(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = _normalized_action(row.get("action"))
        if not action:
            continue
        counts[action] = counts.get(action, 0) + 1
    return counts


def _ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        _normalize(row.get("ticker")).upper(): row
        for row in rows
        if _normalize(row.get("ticker"))
    }


def _watchlist_tickers(rows: list[dict[str, object]]) -> set[str]:
    return {
        _normalize(row.get("ticker")).upper()
        for row in rows
        if _normalize(row.get("ticker"))
    }


def _trace_model_name(enrichment_trace_count: int, reports_trace_count: int) -> str:
    if enrichment_trace_count >= reports_trace_count:
        return "enrichment_field_presence_v0"
    return "unknown"


def _load_analysis_counts(
    analysis_db_copy: str,
    report_date: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    with _connect_read_only(analysis_db_copy) as conn:
        for table_name in (
            "dc_dashboard_ticker_enrichment_daily",
            "dc_dashboard_group_enrichment_daily",
            "dc_dashboard_action_summary_daily",
            "dc_dashboard_decision_trace_daily",
            "dc_dashboard_enrichment_run_daily",
        ):
            _require_table(conn, table_name)
            counts[table_name] = _table_count(conn, table_name)
        counts["dc_dashboard_ticker_enrichment_daily_for_date"] = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM dc_dashboard_ticker_enrichment_daily
                WHERE signal_date = ?
                """,
                (report_date,),
            ).fetchone()[0]
        )
    return counts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only acceptance report for datacenter dashboard enrichment path."
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db-copy", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--max-examples", type=int, default=50)
    parser.add_argument("--format", default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.format != "text":
        return _fail(f"unsupported format: {args.format}")

    try:
        reports_snapshot = load_dashboard_snapshot(
            dashboard_db=args.reports_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.reports_run_id,
        )
        enrichment_snapshot = load_dashboard_snapshot(
            dashboard_db=args.enrichment_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.enrichment_run_id,
        )
        analysis_counts = _load_analysis_counts(
            analysis_db_copy=args.analysis_db_copy,
            report_date=args.report_date,
        )
    except Exception as exc:  # pragma: no cover - exercised in CLI tests
        return _fail(str(exc))

    reports_tickers = _ticker_map(reports_snapshot.tickers)
    enrichment_tickers = _ticker_map(enrichment_snapshot.tickers)
    common_tickers = sorted(set(reports_tickers) & set(enrichment_tickers))

    reports_actions = _count_by_action(reports_snapshot.tickers)
    enrichment_actions = _count_by_action(enrichment_snapshot.tickers)
    sell_to_reduce = 0
    reduce_to_tighten = 0
    major_action_mismatches = 0
    for ticker in common_tickers:
        reports_action = _normalized_action(reports_tickers[ticker].get("action"))
        enrichment_action = _normalized_action(enrichment_tickers[ticker].get("action"))
        if reports_action != enrichment_action:
            major_action_mismatches += 1
        if reports_action == "SELL" and enrichment_action == "REDUCE":
            sell_to_reduce += 1
        if reports_action == "REDUCE" and enrichment_action == "TIGHTEN_STOP":
            reduce_to_tighten += 1

    reports_watchlist = _watchlist_tickers(reports_snapshot.watchlist)
    enrichment_watchlist = _watchlist_tickers(enrichment_snapshot.watchlist)
    missing_watchlist = sorted(reports_watchlist - enrichment_watchlist)
    accepted_outside = [ticker for ticker in missing_watchlist if ticker == "CRGY"]
    watchlist_status = "OK"
    watchlist_details = ""
    if missing_watchlist:
        if missing_watchlist == ["CRGY"]:
            watchlist_status = "ACCEPTED_DIFF"
            watchlist_details = "CRGY_NOT_PART_OF_DATACENTER_ECOSYSTEM"
        else:
            watchlist_status = "REVIEW"
            watchlist_details = ",".join(missing_watchlist)

    reports_market_map = {_market_map_key(row): row for row in reports_snapshot.market_map}
    enrichment_market_map = {_market_map_key(row): row for row in enrichment_snapshot.market_map}
    only_reports_keys = sorted(set(reports_market_map) - set(enrichment_market_map))
    only_enrichment_keys = sorted(set(enrichment_market_map) - set(reports_market_map))

    reports_name_index: dict[tuple[str, str], dict[str, object]] = {}
    for row in reports_snapshot.market_map:
        reports_name_index[(
            _normalize(row.get("market_level")).upper(),
            _market_map_semantic_name(row).upper(),
        )] = row
    same_name_possible_matches = 0
    unmatched_enrichment_rows: list[dict[str, object]] = []
    for key in only_enrichment_keys:
        row = enrichment_market_map[key]
        semantic_key = (
            _normalize(row.get("market_level")).upper(),
            _market_map_semantic_name(row).upper(),
        )
        if semantic_key in reports_name_index:
            same_name_possible_matches += 1
        else:
            unmatched_enrichment_rows.append(row)
    unmatched_enrichment = len(unmatched_enrichment_rows)
    extra_groups = sorted(
        {
            _market_map_semantic_name(row)
            for row in unmatched_enrichment_rows
            if _market_map_semantic_name(row) in _KNOWN_EXTRA_GROUPS
        }
    )
    ecosystem_identity_likely = any(
        _normalize(row.get("market_level")).upper() == "ECOSYSTEM"
        and _normalize(row.get("name")) != "DC_ECOSYSTEM_TOTAL"
        for row in enrichment_snapshot.market_map
    )
    ecosystem_identity_status = "LIKELY" if ecosystem_identity_likely else "FIXED"

    reports_trace_count = len(reports_snapshot.decision_trace)
    enrichment_trace_count = len(enrichment_snapshot.decision_trace)
    trace_model = _trace_model_name(enrichment_trace_count, reports_trace_count)

    accepted_differences = 0
    blockers_count = 0
    review_later_count = 0

    print("section;run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row(
        "run_summary",
        "reports",
        args.reports_dashboard_db,
        args.reports_run_id,
        args.report_date,
        "dashboard_db",
    )
    _print_row(
        "run_summary",
        "enrichment",
        args.enrichment_dashboard_db,
        args.enrichment_run_id,
        args.report_date,
        "dashboard_db",
    )
    _print_row(
        "run_summary",
        "analysis_copy",
        args.analysis_db_copy,
        "",
        args.report_date,
        "analysis_db_copy",
    )

    print("section;section_counts")
    _print_row("section_counts", "section_name", "reports_count", "enrichment_count", "delta", "status")
    section_rows = [
        ("source_reports", len(reports_snapshot.source_reports), len(enrichment_snapshot.source_reports)),
        ("action_summary", len(reports_snapshot.action_summary), len(enrichment_snapshot.action_summary)),
        ("market_map", len(reports_snapshot.market_map), len(enrichment_snapshot.market_map)),
        ("watchlist", len(reports_snapshot.watchlist), len(enrichment_snapshot.watchlist)),
        ("tickers", len(reports_snapshot.tickers), len(enrichment_snapshot.tickers)),
        ("decision_trace", reports_trace_count, enrichment_trace_count),
    ]
    for section_name, reports_count, enrichment_count in section_rows:
        delta = enrichment_count - reports_count
        status = "OK" if delta == 0 else "REVIEW"
        if section_name == "source_reports" and reports_count >= 1 and enrichment_count == 1:
            status = "ACCEPTED_DIFF"
        if section_name == "watchlist" and missing_watchlist == ["CRGY"]:
            status = "ACCEPTED_DIFF"
        if section_name == "decision_trace" and enrichment_count >= reports_count:
            status = "ACCEPTED_DIFF"
        if status == "ACCEPTED_DIFF":
            accepted_differences += 1
        _print_row("section_counts", section_name, reports_count, enrichment_count, delta, status)

    print("section;action_acceptance")
    _print_row("action_acceptance", "metric", "reports_value", "enrichment_value", "status", "details")
    sell_diff = abs(reports_actions.get("SELL", 0) - enrichment_actions.get("SELL", 0))
    tighten_diff = abs(
        reports_actions.get("TIGHTEN_STOP", 0) - enrichment_actions.get("TIGHTEN_STOP", 0)
    )
    neutral_value = enrichment_actions.get("NEUTRAL", 0)
    major_action_status = "OK" if major_action_mismatches == 0 else "REVIEW"
    if sell_diff <= 5 and tighten_diff <= 15 and neutral_value <= 1:
        major_action_status = "ACCEPTED_DIFF"
        accepted_differences += 1
    action_rows = [
        ("reports_sell", reports_actions.get("SELL", 0), "", "OK", ""),
        ("enrichment_sell", "", enrichment_actions.get("SELL", 0), "OK", ""),
        ("reports_reduce", reports_actions.get("REDUCE", 0), "", "OK", ""),
        ("enrichment_reduce", "", enrichment_actions.get("REDUCE", 0), "OK", ""),
        ("reports_tighten_stop", reports_actions.get("TIGHTEN_STOP", 0), "", "OK", ""),
        ("enrichment_tighten_stop", "", enrichment_actions.get("TIGHTEN_STOP", 0), "OK", ""),
        ("reports_neutral", reports_actions.get("NEUTRAL", 0), "", "OK", ""),
        (
            "enrichment_neutral",
            "",
            enrichment_actions.get("NEUTRAL", 0),
            "ACCEPTED_DIFF" if neutral_value <= 1 else "REVIEW",
            "NEAR_ZERO_ACCEPTED" if neutral_value <= 1 else "UNEXPECTED_NEUTRAL_COUNT",
        ),
        ("total_common_tickers", len(common_tickers), len(common_tickers), "OK", ""),
        (
            "major_action_mismatches",
            major_action_mismatches,
            major_action_mismatches,
            major_action_status,
            f"SELL_TO_REDUCE={sell_to_reduce},REDUCE_TO_TIGHTEN_STOP={reduce_to_tighten}",
        ),
    ]
    for metric, reports_value, enrichment_value, status, details in action_rows:
        if status == "ACCEPTED_DIFF" and metric != "major_action_mismatches":
            accepted_differences += 1
        _print_row(
            "action_acceptance",
            metric,
            reports_value,
            enrichment_value,
            status,
            details,
        )

    print("section;watchlist_acceptance")
    _print_row("watchlist_acceptance", "metric", "reports_value", "enrichment_value", "status", "details")
    if watchlist_status == "ACCEPTED_DIFF":
        accepted_differences += 1
    _print_row(
        "watchlist_acceptance",
        "reports_watchlist",
        len(reports_watchlist),
        "",
        "OK",
        "",
    )
    _print_row(
        "watchlist_acceptance",
        "enrichment_watchlist",
        "",
        len(enrichment_watchlist),
        "OK",
        "",
    )
    _print_row(
        "watchlist_acceptance",
        "missing_watchlist_tickers",
        len(missing_watchlist),
        len(missing_watchlist),
        watchlist_status,
        watchlist_details,
    )
    _print_row(
        "watchlist_acceptance",
        "accepted_outside_ecosystem_tickers",
        ",".join(accepted_outside),
        ",".join(accepted_outside),
        "ACCEPTED_DIFF" if accepted_outside else "OK",
        "CRGY_NOT_PART_OF_DATACENTER_ECOSYSTEM" if accepted_outside else "",
    )

    print("section;market_map_acceptance")
    _print_row("market_map_acceptance", "metric", "reports_value", "enrichment_value", "status", "details")
    market_map_status = "OK"
    if len(only_reports_keys) > 1 or unmatched_enrichment > 4 or ecosystem_identity_likely:
        market_map_status = "REVIEW"
    elif only_enrichment_keys or only_reports_keys:
        market_map_status = "ACCEPTED_DIFF"
        accepted_differences += 1
    _print_row(
        "market_map_acceptance",
        "reports_market_map",
        len(reports_snapshot.market_map),
        "",
        "OK",
        "",
    )
    _print_row(
        "market_map_acceptance",
        "enrichment_market_map",
        "",
        len(enrichment_snapshot.market_map),
        "OK",
        "",
    )
    _print_row(
        "market_map_acceptance",
        "only_reports",
        len(only_reports_keys),
        len(only_reports_keys),
        market_map_status,
        ",".join(only_reports_keys[: args.max_examples]),
    )
    _print_row(
        "market_map_acceptance",
        "only_enrichment",
        len(only_enrichment_keys),
        len(only_enrichment_keys),
        market_map_status,
        ",".join(only_enrichment_keys[: args.max_examples]),
    )
    _print_row(
        "market_map_acceptance",
        "unmatched_enrichment",
        unmatched_enrichment,
        unmatched_enrichment,
        "ACCEPTED_DIFF" if unmatched_enrichment <= 4 else "REVIEW",
        ",".join(_market_map_semantic_name(row) for row in unmatched_enrichment_rows[: args.max_examples]),
    )
    _print_row(
        "market_map_acceptance",
        "ecosystem_identity_status",
        "FIXED" if not ecosystem_identity_likely else "LIKELY_MISMATCH",
        "FIXED" if not ecosystem_identity_likely else "LIKELY_MISMATCH",
        "OK" if not ecosystem_identity_likely else "REVIEW",
        "ECOSYSTEM_KEY_MISMATCH_UNLIKELY" if not ecosystem_identity_likely else "ECOSYSTEM_KEY_MISMATCH_LIKELY",
    )
    _print_row(
        "market_map_acceptance",
        "extra_groups",
        ",".join(extra_groups),
        ",".join(extra_groups),
        "ACCEPTED_DIFF" if extra_groups else "OK",
        "KNOWN_EXTRA_GROUPS_NOT_FILTERED" if extra_groups else "",
    )

    print("section;decision_trace_acceptance")
    _print_row(
        "decision_trace_acceptance",
        "metric",
        "reports_value",
        "enrichment_value",
        "status",
        "details",
    )
    accepted_differences += 1
    _print_row(
        "decision_trace_acceptance",
        "reports_decision_trace",
        reports_trace_count,
        "",
        "OK",
        "",
    )
    _print_row(
        "decision_trace_acceptance",
        "enrichment_decision_trace",
        "",
        enrichment_trace_count,
        "ACCEPTED_DIFF",
        "VERBOSE_V0_TRACE_ACCEPTED",
    )
    _print_row(
        "decision_trace_acceptance",
        "trace_model",
        "",
        trace_model,
        "ACCEPTED_DIFF",
        "CURRENT_STAGE_DECLARATION",
    )
    _print_row(
        "decision_trace_acceptance",
        "trace_parity_required",
        "",
        "NO_FOR_CURRENT_STAGE",
        "ACCEPTED_DIFF",
        "TRACE_PARITY_NOT_REQUIRED_YET",
    )

    print("section;known_differences")
    _print_row("known_differences", "difference", "status", "details")
    _print_row(
        "known_differences",
        "CRGY outside ecosystem watchlist difference",
        "ACCEPTED_DIFF" if accepted_outside else "OK",
        "CRGY_NOT_PART_OF_DATACENTER_ECOSYSTEM" if accepted_outside else "",
    )
    _print_row(
        "known_differences",
        "enrichment extra market_map groups",
        "ACCEPTED_DIFF" if extra_groups else "OK",
        ",".join(extra_groups),
    )
    _print_row(
        "known_differences",
        "enrichment decision_trace verbose V0",
        "ACCEPTED_DIFF",
        trace_model,
    )
    _print_row(
        "known_differences",
        "action residual SELL/REDUCE/TIGHTEN",
        "ACCEPTED_DIFF" if major_action_status == "ACCEPTED_DIFF" else "REVIEW",
        f"SELL_TO_REDUCE={sell_to_reduce},REDUCE_TO_TIGHTEN_STOP={reduce_to_tighten}",
    )
    _print_row(
        "known_differences",
        "source_reports count difference",
        "ACCEPTED_DIFF" if len(enrichment_snapshot.source_reports) == 1 else "REVIEW",
        f"reports={len(reports_snapshot.source_reports)},enrichment={len(enrichment_snapshot.source_reports)}",
    )

    print("section;blockers")
    _print_row("blockers", "blocker", "status", "details")
    blocker_rows: list[tuple[str, str, str]] = []
    if major_action_status == "REVIEW":
        blocker_rows.append(("action_parity", "BLOCKING", "UNEXPLAINED_ACTION_GAP"))
        blockers_count += 1
    else:
        blocker_rows.append(
            ("action_parity", "NON_BLOCKING", f"SELL_TO_REDUCE={sell_to_reduce},REDUCE_TO_TIGHTEN_STOP={reduce_to_tighten}")
        )
    if watchlist_status == "REVIEW":
        blocker_rows.append(("watchlist_parity", "BLOCKING", watchlist_details or "UNEXPLAINED_WATCHLIST_GAP"))
        blockers_count += 1
    else:
        blocker_rows.append(("watchlist_parity", "NON_BLOCKING", watchlist_details))
    if ecosystem_identity_likely:
        blocker_rows.append(("market_map_identity", "BLOCKING", "ECOSYSTEM_KEY_MISMATCH_LIKELY"))
        blockers_count += 1
    else:
        blocker_rows.append(("market_map_identity", "NON_BLOCKING", "ECOSYSTEM_KEY_MISMATCH_UNLIKELY"))
    blocker_rows.append(("decision_trace_parity", "NON_BLOCKING", "V0_VERBOSE_TRACE_ACCEPTED"))
    blocker_rows.append(("production_db_migration", "REVIEW_LATER", "NOT_IN_SCOPE_FOR_ACCEPTANCE_REPORT"))
    review_later_count += 1
    blocker_rows.append(("scheduler_switch_not_done", "NON_BLOCKING", "ACCEPTANCE_PRECEDES_SWITCH"))
    for blocker, status, details in blocker_rows:
        _print_row("blockers", blocker, status, details)

    recommendation = "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    recommendation_status = "OK"
    recommendation_details = "NO_BLOCKING_PARITY_ISSUES_FOR_NEXT_PLANNING_STAGE"
    if blockers_count > 0:
        recommendation = "NOT_READY_NEEDS_MORE_FIXES"
        recommendation_status = "REVIEW"
        recommendation_details = "BLOCKING_PARITY_ISSUES_PRESENT"
    elif market_map_status == "REVIEW":
        recommendation = "READY_FOR_TEMP_ONLY_PARITY_REVIEW"
        recommendation_status = "REVIEW"
        recommendation_details = "MARKET_MAP_NEEDS_MORE_LOCAL_REVIEW"
    print("section;recommendation")
    _print_row("recommendation", "decision", "status", "details")
    _print_row("recommendation", recommendation, recommendation_status, recommendation_details)

    print("section;summary")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.status=OK")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.report_date={_cell(args.report_date)}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.reports_run_id={_cell(args.reports_run_id)}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.enrichment_run_id={_cell(args.enrichment_run_id)}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.blockers={blockers_count}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.accepted_differences={accepted_differences}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.review_later={review_later_count}")
    print(f"SUMMARY {_ACCEPTANCE_PREFIX}.recommendation={recommendation}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
