from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace(";", ",").replace("\n", " ").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"db not found: {db_path}")
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


def _market_map_key(row: dict[str, object]) -> str:
    taxonomy_path = _cell(row.get("taxonomy_path"))
    if taxonomy_path:
        return taxonomy_path
    return "|".join(
        [
            _cell(row.get("market_level")),
            _cell(row.get("name")),
            _cell(row.get("parent_name")),
            _cell(row.get("layer")),
            _cell(row.get("subindustry")),
        ]
    )


def _ticker_key_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["ticker"]): row for row in rows}


def _market_map_dict(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {_market_map_key(row): row for row in rows}


def _avg_trace_rows_per_ticker(rows: list[dict[str, object]]) -> float:
    if not rows:
        return 0.0
    tickers = {str(row["ticker"]) for row in rows}
    if not tickers:
        return 0.0
    return len(rows) / len(tickers)


def _load_analysis_metrics(
    analysis_db: str | None,
    signal_date: str,
) -> dict[str, object] | None:
    if analysis_db is None:
        return None

    with _connect_read_only(analysis_db) as conn:
        ticker_table = "dc_dashboard_ticker_enrichment_daily"
        action_table = "dc_dashboard_action_summary_daily"
        trace_table = "dc_dashboard_decision_trace_daily"
        group_table = "dc_dashboard_group_enrichment_daily"

        has_ticker = _table_exists(conn, ticker_table)
        has_action = _table_exists(conn, action_table)
        has_trace = _table_exists(conn, trace_table)
        has_group = _table_exists(conn, group_table)

        metrics: dict[str, object] = {
            "ticker_rows": 0,
            "group_rows": 0,
            "action_summary_rows": 0,
            "decision_trace_rows": 0,
            "is_watchlist_true_count": 0,
            "is_watchlist_false_count": 0,
            "ticker_action_distribution": [],
            "decision_trace_distinct_tickers": 0,
            "decision_trace_top_tickers": [],
            "tables_present": {
                ticker_table: has_ticker,
                action_table: has_action,
                trace_table: has_trace,
                group_table: has_group,
            },
        }

        if has_ticker:
            metrics["ticker_rows"] = conn.execute(
                f"SELECT COUNT(*) FROM {ticker_table} WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]
            metrics["is_watchlist_true_count"] = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {ticker_table}
                WHERE signal_date = ? AND COALESCE(is_watchlist, 0) = 1
                """,
                (signal_date,),
            ).fetchone()[0]
            metrics["is_watchlist_false_count"] = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {ticker_table}
                WHERE signal_date = ? AND COALESCE(is_watchlist, 0) = 0
                """,
                (signal_date,),
            ).fetchone()[0]
            metrics["ticker_action_distribution"] = [
                (str(row["action"]), int(row["count"]))
                for row in conn.execute(
                    f"""
                    SELECT TRIM(action) AS action, COUNT(*) AS count
                    FROM {ticker_table}
                    WHERE signal_date = ? AND TRIM(COALESCE(action, '')) <> ''
                    GROUP BY TRIM(action)
                    ORDER BY TRIM(action) ASC
                    """,
                    (signal_date,),
                ).fetchall()
            ]

        if has_group:
            metrics["group_rows"] = conn.execute(
                f"SELECT COUNT(*) FROM {group_table} WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]

        if has_action:
            metrics["action_summary_rows"] = conn.execute(
                f"SELECT COUNT(*) FROM {action_table} WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]

        if has_trace:
            metrics["decision_trace_rows"] = conn.execute(
                f"SELECT COUNT(*) FROM {trace_table} WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]
            metrics["decision_trace_distinct_tickers"] = conn.execute(
                f"""
                SELECT COUNT(DISTINCT ticker)
                FROM {trace_table}
                WHERE signal_date = ?
                """,
                (signal_date,),
            ).fetchone()[0]
            metrics["decision_trace_top_tickers"] = [
                (str(row["ticker"]), int(row["count"]))
                for row in conn.execute(
                    f"""
                    SELECT ticker, COUNT(*) AS count
                    FROM {trace_table}
                    WHERE signal_date = ?
                    GROUP BY ticker
                    ORDER BY count DESC, ticker ASC
                    """,
                    (signal_date,),
                ).fetchall()
            ]

        return metrics


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose enrichment vs reports dashboard parity differences.",
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--analysis-db-copy")
    parser.add_argument("--max-examples", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        reports = load_dashboard_snapshot(
            dashboard_db=args.reports_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.reports_run_id,
        )
        enrichment = load_dashboard_snapshot(
            dashboard_db=args.enrichment_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.enrichment_run_id,
        )
        analysis_metrics = _load_analysis_metrics(
            analysis_db=args.analysis_db_copy,
            signal_date=args.report_date,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_counts = {
        "source_reports": len(reports.source_reports),
        "action_summary": len(reports.action_summary),
        "market_map": len(reports.market_map),
        "watchlist": len(reports.watchlist),
        "tickers": len(reports.tickers),
        "decision_trace": len(reports.decision_trace),
    }
    enrichment_counts = {
        "source_reports": len(enrichment.source_reports),
        "action_summary": len(enrichment.action_summary),
        "market_map": len(enrichment.market_map),
        "watchlist": len(enrichment.watchlist),
        "tickers": len(enrichment.tickers),
        "decision_trace": len(enrichment.decision_trace),
    }

    reports_action_distribution = [
        (str(row["action"]), int(row["count"])) for row in reports.action_summary
    ]
    enrichment_action_distribution = [
        (str(row["action"]), int(row["count"])) for row in enrichment.action_summary
    ]
    analysis_action_distribution = (
        analysis_metrics["ticker_action_distribution"] if analysis_metrics else []
    )

    reports_market = _market_map_dict(reports.market_map)
    enrichment_market = _market_map_dict(enrichment.market_map)
    only_reports_market_keys = sorted(set(reports_market) - set(enrichment_market))
    only_enrichment_market_keys = sorted(set(enrichment_market) - set(reports_market))

    reports_tickers = _ticker_key_map(reports.tickers)
    enrichment_tickers = _ticker_key_map(enrichment.tickers)
    only_reports_tickers = sorted(set(reports_tickers) - set(enrichment_tickers))
    only_enrichment_tickers = sorted(set(enrichment_tickers) - set(reports_tickers))

    reports_trace_avg = _avg_trace_rows_per_ticker(reports.decision_trace)
    enrichment_trace_avg = _avg_trace_rows_per_ticker(enrichment.decision_trace)
    enrichment_trace_counter = Counter(
        str(row["ticker"]) for row in enrichment.decision_trace if row.get("ticker")
    )
    top_enrichment_trace = sorted(
        enrichment_trace_counter.items(),
        key=lambda item: (-item[1], item[0]),
    )[: args.max_examples]

    analysis_true = (
        int(analysis_metrics["is_watchlist_true_count"]) if analysis_metrics else None
    )
    analysis_false = (
        int(analysis_metrics["is_watchlist_false_count"]) if analysis_metrics else None
    )
    analysis_ticker_rows = (
        int(analysis_metrics["ticker_rows"]) if analysis_metrics else None
    )
    analysis_trace_rows = (
        int(analysis_metrics["decision_trace_rows"]) if analysis_metrics else None
    )
    analysis_trace_distinct = (
        int(analysis_metrics["decision_trace_distinct_tickers"])
        if analysis_metrics
        else None
    )
    analysis_trace_avg = (
        (
            analysis_trace_rows / analysis_trace_distinct
            if analysis_trace_rows and analysis_trace_distinct
            else 0.0
        )
        if analysis_metrics
        else None
    )

    if analysis_metrics is None:
        watchlist_gap_details = "analysis_copy_not_provided"
    elif analysis_true > 0 and enrichment_counts["watchlist"] == 0:
        watchlist_gap_details = "export_mapping_issue_likely"
    elif analysis_true == 0:
        watchlist_gap_details = "watchlist_source_missing_likely"
    else:
        watchlist_gap_details = "no_gap_detected"

    reports_distinct_actions = len(reports_action_distribution)
    enrichment_distinct_actions = len(enrichment_action_distribution)

    if analysis_metrics is None:
        watchlist_source_missing = "UNKNOWN"
        watchlist_export_mapping_issue = "UNKNOWN"
    else:
        watchlist_source_missing = (
            "LIKELY"
            if analysis_true == 0 and enrichment_counts["watchlist"] == 0
            else "UNLIKELY"
        )
        watchlist_export_mapping_issue = (
            "LIKELY"
            if analysis_true > 0 and enrichment_counts["watchlist"] == 0
            else "UNLIKELY"
        )

    action_collapse = (
        "LIKELY"
        if enrichment_distinct_actions <= 1 and reports_distinct_actions > 1
        else "UNLIKELY"
    )
    trace_too_verbose = (
        "LIKELY"
        if (
            enrichment_counts["decision_trace"] > 0
            and (
                reports_counts["decision_trace"] == 0
                or enrichment_counts["decision_trace"]
                > reports_counts["decision_trace"] * 2
            )
        )
        else "UNLIKELY"
    )
    market_map_scope_diff = (
        "LIKELY"
        if only_reports_market_keys or only_enrichment_market_keys
        else "UNLIKELY"
    )
    ticker_count_near_parity = (
        "LIKELY"
        if abs(reports_counts["tickers"] - enrichment_counts["tickers"]) <= 2
        else "UNLIKELY"
    )

    _print_row("section", "run_summary")
    _print_row("run_summary", "side", "dashboard_db", "run_id", "report_date", "source")
    _print_row(
        "run_summary",
        "reports",
        args.reports_dashboard_db,
        args.reports_run_id,
        args.report_date,
        "dashboard_snapshot",
    )
    _print_row(
        "run_summary",
        "enrichment",
        args.enrichment_dashboard_db,
        args.enrichment_run_id,
        args.report_date,
        "dashboard_snapshot",
    )
    _print_row(
        "run_summary",
        "analysis_copy",
        args.analysis_db_copy or "",
        "",
        args.report_date,
        "analysis_enrichment_tables",
    )

    _print_row("section", "section_counts")
    _print_row("section_counts", "section_name", "reports_count", "enrichment_count", "delta")
    for section_name in (
        "source_reports",
        "action_summary",
        "market_map",
        "watchlist",
        "tickers",
        "decision_trace",
    ):
        _print_row(
            "section_counts",
            section_name,
            reports_counts[section_name],
            enrichment_counts[section_name],
            enrichment_counts[section_name] - reports_counts[section_name],
        )

    _print_row("section", "action_distribution")
    _print_row("action_distribution", "source", "action", "count")
    for source_name, distribution in (
        ("reports", reports_action_distribution),
        ("enrichment", enrichment_action_distribution),
        ("analysis_ticker_enrichment", analysis_action_distribution),
    ):
        for action, count in distribution:
            _print_row("action_distribution", source_name, action, count)

    _print_row("section", "watchlist_diagnosis")
    _print_row(
        "watchlist_diagnosis",
        "metric",
        "reports_value",
        "enrichment_value",
        "analysis_value",
        "details",
    )
    _print_row(
        "watchlist_diagnosis",
        "watchlist_rows",
        reports_counts["watchlist"],
        enrichment_counts["watchlist"],
        "",
        "",
    )
    _print_row(
        "watchlist_diagnosis",
        "ticker_rows",
        reports_counts["tickers"],
        enrichment_counts["tickers"],
        analysis_ticker_rows,
        "",
    )
    _print_row(
        "watchlist_diagnosis",
        "is_watchlist_true_count",
        "",
        "",
        analysis_true,
        "",
    )
    _print_row(
        "watchlist_diagnosis",
        "is_watchlist_false_count",
        "",
        "",
        analysis_false,
        "",
    )
    _print_row(
        "watchlist_diagnosis",
        "enrichment_watchlist_export_gap",
        "",
        enrichment_counts["watchlist"],
        analysis_true,
        watchlist_gap_details,
    )

    _print_row("section", "decision_trace_distribution")
    _print_row("decision_trace_distribution", "source", "metric", "value", "details")
    _print_row(
        "decision_trace_distribution",
        "reports",
        "total_trace_rows",
        reports_counts["decision_trace"],
        "",
    )
    _print_row(
        "decision_trace_distribution",
        "enrichment",
        "total_trace_rows",
        enrichment_counts["decision_trace"],
        "",
    )
    _print_row(
        "decision_trace_distribution",
        "reports",
        "distinct_trace_tickers",
        len({str(row["ticker"]) for row in reports.decision_trace}),
        "",
    )
    _print_row(
        "decision_trace_distribution",
        "enrichment",
        "distinct_trace_tickers",
        len({str(row["ticker"]) for row in enrichment.decision_trace}),
        "",
    )
    _print_row(
        "decision_trace_distribution",
        "reports",
        "avg_trace_rows_per_ticker",
        f"{reports_trace_avg:.4f}",
        "",
    )
    _print_row(
        "decision_trace_distribution",
        "enrichment",
        "avg_trace_rows_per_ticker",
        f"{enrichment_trace_avg:.4f}",
        "",
    )
    for ticker, count in top_enrichment_trace:
        _print_row(
            "decision_trace_distribution",
            "enrichment",
            "top_trace_ticker_count",
            count,
            f"ticker:{ticker}",
        )
    if analysis_metrics is not None:
        _print_row(
            "decision_trace_distribution",
            "analysis",
            "total_trace_rows",
            analysis_trace_rows,
            "",
        )
        _print_row(
            "decision_trace_distribution",
            "analysis",
            "distinct_trace_tickers",
            analysis_trace_distinct,
            "",
        )
        _print_row(
            "decision_trace_distribution",
            "analysis",
            "avg_trace_rows_per_ticker",
            f"{analysis_trace_avg:.4f}",
            "",
        )

    _print_row("section", "market_map_key_differences")
    _print_row(
        "market_map_key_differences",
        "diff_type",
        "key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "current_status",
        "source_horizons",
    )
    for key in only_reports_market_keys[: args.max_examples]:
        row = reports_market[key]
        _print_row(
            "market_map_key_differences",
            "ONLY_REPORTS",
            key,
            row.get("market_level"),
            row.get("name"),
            row.get("parent_name"),
            row.get("layer"),
            row.get("subindustry"),
            row.get("current_status"),
            row.get("source_horizons"),
        )
    for key in only_enrichment_market_keys[: args.max_examples]:
        row = enrichment_market[key]
        _print_row(
            "market_map_key_differences",
            "ONLY_ENRICHMENT",
            key,
            row.get("market_level"),
            row.get("name"),
            row.get("parent_name"),
            row.get("layer"),
            row.get("subindustry"),
            row.get("current_status"),
            row.get("source_horizons"),
        )

    _print_row("section", "ticker_key_differences")
    _print_row(
        "ticker_key_differences",
        "diff_type",
        "ticker",
        "action",
        "current_status",
        "is_watchlist",
        "horizons_present",
    )
    for ticker in only_reports_tickers[: args.max_examples]:
        row = reports_tickers[ticker]
        _print_row(
            "ticker_key_differences",
            "ONLY_REPORTS",
            ticker,
            row.get("action"),
            row.get("current_status"),
            row.get("is_watchlist"),
            row.get("horizons_present"),
        )
    for ticker in only_enrichment_tickers[: args.max_examples]:
        row = enrichment_tickers[ticker]
        _print_row(
            "ticker_key_differences",
            "ONLY_ENRICHMENT",
            ticker,
            row.get("action"),
            row.get("current_status"),
            row.get("is_watchlist"),
            row.get("horizons_present"),
        )

    _print_row("section", "hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "WATCHLIST_SOURCE_MISSING",
        watchlist_source_missing,
        f"analysis_is_watchlist_true={_cell(analysis_true)};enrichment_watchlist={enrichment_counts['watchlist']}",
    )
    _print_row(
        "hypothesis_summary",
        "WATCHLIST_EXPORT_MAPPING_ISSUE",
        watchlist_export_mapping_issue,
        f"analysis_is_watchlist_true={_cell(analysis_true)};enrichment_watchlist={enrichment_counts['watchlist']}",
    )
    _print_row(
        "hypothesis_summary",
        "ACTION_COLLAPSE",
        action_collapse,
        f"reports_distinct_actions={reports_distinct_actions};enrichment_distinct_actions={enrichment_distinct_actions}",
    )
    _print_row(
        "hypothesis_summary",
        "TRACE_TOO_VERBOSE",
        trace_too_verbose,
        f"reports_trace={reports_counts['decision_trace']};enrichment_trace={enrichment_counts['decision_trace']}",
    )
    _print_row(
        "hypothesis_summary",
        "MARKET_MAP_SCOPE_DIFF",
        market_map_scope_diff,
        f"only_reports={len(only_reports_market_keys)};only_enrichment={len(only_enrichment_market_keys)}",
    )
    _print_row(
        "hypothesis_summary",
        "TICKER_COUNT_NEAR_PARITY",
        ticker_count_near_parity,
        f"reports_tickers={reports_counts['tickers']};enrichment_tickers={enrichment_counts['tickers']}",
    )

    _print_row("section", "summary")
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.status=OK"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.report_date={args.report_date}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.reports_run_id={args.reports_run_id}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.enrichment_run_id={args.enrichment_run_id}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.reports_tickers={reports_counts['tickers']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.enrichment_tickers={enrichment_counts['tickers']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.reports_watchlist={reports_counts['watchlist']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.enrichment_watchlist={enrichment_counts['watchlist']}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.analysis_is_watchlist_true="
        f"{_cell(analysis_true)}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.reports_action_summary={reports_counts['action_summary']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.enrichment_action_summary={enrichment_counts['action_summary']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.reports_decision_trace={reports_counts['decision_trace']}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.enrichment_decision_trace={enrichment_counts['decision_trace']}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.market_map_only_reports="
        f"{len(only_reports_market_keys)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.market_map_only_enrichment="
        f"{len(only_enrichment_market_keys)}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.ticker_only_reports={len(only_reports_tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.ticker_only_enrichment="
        f"{len(only_enrichment_tickers)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
