from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from analysis.datacenter_indices.swing_weekly_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_WEEKLY_WINDOW_SIZE,
    _build_rolling_5_pullback_rows,
    _load_rows_for_dates,
    _load_valid_signal_dates,
    _parse_iso_date,
    _resolve_weekly_taxonomy_version,
)
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.run_datacenter_dashboard_rolling5_pullback_v2_classifier_audit import (
    _classify_v2_ticker,
)

REPORT_PRIORITY = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)
UPSTREAM_FIELDS = (
    "rolling_5_pullback_state",
    "pullback_days",
    "fast_ema10_pullback_days",
    "conservative_ema20_pullback_days",
    "latest_bos_event_type",
    "latest_bos_freshness",
    "latest_reset_reason",
    "latest_reset_freshness",
    "latest_bullish_relevance_class",
    "latest_bearish_relevance_class",
    "primary_reason",
    "blocking_reason",
    "next_action",
)
UPSTREAM_TO_REPORTS = {
    "PULLBACK_CANDIDATE": "VALID_PULLBACK",
    "EARLY_PULLBACK": "EARLY_PULLBACK",
    "FAILED_PULLBACK": "STRUCTURE_BLOCKED_PULLBACK",
    "SHORT_TERM_BREAKDOWN": "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK": "NO_PULLBACK",
    "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
}


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("\n", " ").replace(";", ",").strip()


def _print_section(name: str) -> None:
    print(f"section;{name}")


def _print_row(prefix: str, *columns: object) -> None:
    print(";".join([prefix, *(_cell(column) for column in columns)]))


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    output: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            output.append(ticker)
    return output


def _normalize_report_value(value: object, default: str = "") -> str:
    normalized = _cell(value)
    return normalized or default


def _connect_analysis_read_only(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise ValueError(f"analysis_db not found: {path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _require_tables(conn: sqlite3.Connection, table_names: tuple[str, ...]) -> None:
    existing = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing = [name for name in table_names if name not in existing]
    if missing:
        raise ValueError(f"required table missing: {', '.join(missing)}")


def _reports_by_ticker(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _normalize_report_value(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _group_ticker_rows(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        ticker = _normalize_report_value(row.get("ticker")).upper()
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    for ticker_rows in grouped.values():
        ticker_rows.sort(key=lambda row: _normalize_report_value(row.get("signal_date")))
    return grouped


def _extract_upstream_source_rows(
    *,
    analysis_db: str,
    report_date: str,
    taxonomy_version: str | None,
) -> tuple[int, str, str, list[dict[str, object]], list[dict[str, object]]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_tables(
            conn,
            (
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            ),
        )
        normalized_date = _parse_iso_date(report_date)
        taxonomy_version, _inferred = _resolve_weekly_taxonomy_version(
            conn,
            end_date=normalized_date,
            signal_version=DEFAULT_SIGNAL_VERSION,
            taxonomy_version=taxonomy_version,
        )
        valid_signal_dates = _load_valid_signal_dates(
            conn,
            end_date=normalized_date,
            signal_version=DEFAULT_SIGNAL_VERSION,
            taxonomy_version=taxonomy_version,
            limit=DEFAULT_WEEKLY_WINDOW_SIZE,
        )
        group_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=DEFAULT_SIGNAL_VERSION,
            taxonomy_version=taxonomy_version,
        )
        ticker_rows = _load_rows_for_dates(
            conn,
            table_name="dc_ticker_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=DEFAULT_SIGNAL_VERSION,
            taxonomy_version=taxonomy_version,
        )
        synthetic_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_synthetic_ohlc_daily",
            date_field="ohlc_date",
            selected_dates=valid_signal_dates,
            version_field="calc_version",
            version_value=DEFAULT_OHLC_CALC_VERSION,
            taxonomy_version=taxonomy_version,
        )
    upstream_rows = _build_rolling_5_pullback_rows(
        ticker_rows=ticker_rows,
        group_rows=group_rows,
        synthetic_rows=synthetic_rows,
        technical_relevance_context_rows=[],
    )
    return (
        1,
        "_build_rolling_5_pullback_rows",
        "",
        upstream_rows,
        ticker_rows,
    )


def _build_v2_baseline_map(
    *,
    reports_by_ticker: dict[str, dict[str, object]],
    ticker_source_rows: list[dict[str, object]],
    selected_tickers: list[str],
) -> dict[str, str]:
    grouped = _group_ticker_rows(ticker_source_rows)
    baseline: dict[str, str] = {}
    for ticker in selected_tickers:
        reports_value = _normalize_report_value(
            reports_by_ticker[ticker].get("pullback_validity"),
            "INSUFFICIENT_DATA",
        )
        classification = _classify_v2_ticker(ticker, reports_value, grouped.get(ticker, []))
        baseline[ticker] = classification.classifier_mapped_status
    return baseline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit for upstream rolling5 structured source rows versus reports-mode pullback_validity."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--taxonomy-version")
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_examples <= 0:
        print("ERROR: --max-examples must be greater than 0", file=sys.stderr)
        return 1
    try:
        reports_snapshot = load_dashboard_snapshot(
            dashboard_db=args.reports_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.reports_run_id,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _reports_by_ticker(reports_snapshot.tickers)
    explicit_tickers = _parse_tickers(args.tickers)

    builder_callable = 0
    builder_function = "_build_rolling_5_pullback_rows"
    builder_reason = ""
    upstream_rows: list[dict[str, object]] = []
    ticker_source_rows: list[dict[str, object]] = []
    try:
        (
            builder_callable,
            builder_function,
            builder_reason,
            upstream_rows,
            ticker_source_rows,
        ) = _extract_upstream_source_rows(
            analysis_db=args.analysis_db,
            report_date=args.report_date,
            taxonomy_version=args.taxonomy_version,
        )
    except Exception as exc:  # diagnostic path must stay non-fatal
        builder_callable = 0
        builder_reason = str(exc)
        upstream_rows = []
        ticker_source_rows = []

    upstream_by_ticker = {
        _normalize_report_value(row.get("ticker")).upper(): row
        for row in upstream_rows
        if _normalize_report_value(row.get("ticker"))
    }
    if explicit_tickers:
        selected_tickers = [ticker for ticker in explicit_tickers if ticker in reports_by_ticker]
    else:
        selected_tickers = [
            ticker
            for ticker in sorted(reports_by_ticker)
            if not (ticker == "CRGY" and ticker not in upstream_by_ticker)
        ]
    common_tickers = [ticker for ticker in selected_tickers if ticker in upstream_by_ticker]

    v2_baseline_by_ticker = (
        _build_v2_baseline_map(
            reports_by_ticker=reports_by_ticker,
            ticker_source_rows=ticker_source_rows,
            selected_tickers=common_tickers,
        )
        if builder_callable == 1
        else {}
    )

    field_coverage_counts: dict[str, tuple[int, int]] = {}
    for field_name in UPSTREAM_FIELDS:
        exists = int(any(field_name in row for row in upstream_rows))
        non_empty_count = sum(1 for row in upstream_rows if _normalize_report_value(row.get(field_name)) != "")
        field_coverage_counts[field_name] = (exists, non_empty_count)

    upstream_distribution = Counter(
        _normalize_report_value(row.get("rolling_5_pullback_state"), "INSUFFICIENT_DATA")
        for row in upstream_rows
    )
    reports_distribution = Counter(
        _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA")
        for ticker in common_tickers
    )
    matrix = Counter(
        (
            _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA"),
            _normalize_report_value(upstream_by_ticker[ticker].get("rolling_5_pullback_state"), "INSUFFICIENT_DATA"),
        )
        for ticker in common_tickers
    )

    upstream_mapped_by_ticker = {
        ticker: UPSTREAM_TO_REPORTS.get(
            _normalize_report_value(upstream_by_ticker[ticker].get("rolling_5_pullback_state"), "INSUFFICIENT_DATA"),
            "INSUFFICIENT_DATA",
        )
        for ticker in common_tickers
    }
    mismatch_tickers = [
        ticker
        for ticker in common_tickers
        if upstream_mapped_by_ticker[ticker]
        != _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA")
    ]
    mismatch_tickers.sort(
        key=lambda ticker: (
            REPORT_PRIORITY.index(
                _normalize_report_value(
                    reports_by_ticker[ticker].get("pullback_validity"),
                    "INSUFFICIENT_DATA",
                )
            ),
            ticker,
        )
    )

    upstream_exact_matches = sum(
        1
        for ticker in common_tickers
        if upstream_mapped_by_ticker[ticker]
        == _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA")
    )
    v2_exact_matches = sum(
        1
        for ticker in common_tickers
        if v2_baseline_by_ticker.get(ticker)
        == _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA")
    )
    upstream_exact_rate = (upstream_exact_matches / len(common_tickers)) if common_tickers else 0.0
    v2_exact_rate = (v2_exact_matches / len(common_tickers)) if common_tickers else 0.0

    core_fields_present = all(field_coverage_counts[field][1] > 0 for field in (
        "rolling_5_pullback_state",
        "pullback_days",
        "primary_reason",
        "blocking_reason",
        "next_action",
    ))
    upstream_builder_reusable = int(builder_callable == 1 and len(upstream_rows) > 0)
    should_expose_upstream_fields = int(upstream_builder_reusable == 1 and core_fields_present)
    needs_helper_extraction = int(builder_callable == 0)

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row("run_summary", "analysis", args.analysis_db, "ROLLING5_UPSTREAM", args.report_date, "analysis_db")
    _print_row("run_summary", "reports", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_db")

    _print_section("upstream_builder_status")
    _print_row("upstream_builder_status", "metric", "value", "details")
    _print_row("upstream_builder_status", "builder_callable", builder_callable, builder_reason)
    _print_row("upstream_builder_status", "builder_function", builder_function, "")
    _print_row(
        "upstream_builder_status",
        "taxonomy_version",
        args.taxonomy_version or "",
        "",
    )
    _print_row("upstream_builder_status", "rows_extracted", len(upstream_rows), "")
    _print_row("upstream_builder_status", "tickers_extracted", len(upstream_by_ticker), "")
    _print_row("upstream_builder_status", "error_or_reason", builder_reason, builder_reason)

    _print_section("upstream_field_coverage")
    _print_row("upstream_field_coverage", "field_name", "exists", "non_empty_count")
    for field_name in UPSTREAM_FIELDS:
        exists, non_empty_count = field_coverage_counts[field_name]
        _print_row("upstream_field_coverage", field_name, exists, non_empty_count)

    _print_section("upstream_distribution")
    _print_row("upstream_distribution", "rolling_5_pullback_state", "count")
    for state, count in sorted(upstream_distribution.items()):
        _print_row("upstream_distribution", state, count)

    _print_section("reports_distribution")
    _print_row("reports_distribution", "pullback_validity", "count")
    for state, count in sorted(reports_distribution.items()):
        _print_row("reports_distribution", state, count)

    _print_section("upstream_vs_reports_matrix")
    _print_row("upstream_vs_reports_matrix", "reports_pullback_validity", "rolling_5_pullback_state", "count")
    for (reports_value, upstream_value), count in sorted(matrix.items()):
        _print_row("upstream_vs_reports_matrix", reports_value, upstream_value, count)

    _print_section("selected_mismatches")
    _print_row(
        "selected_mismatches",
        "ticker",
        "reports_pullback_validity",
        "rolling_5_pullback_state",
        "pullback_days",
        "latest_bos_event_type",
        "latest_bos_freshness",
        "latest_reset_reason",
        "latest_reset_freshness",
        "latest_bullish_relevance_class",
        "primary_reason",
        "blocking_reason",
        "next_action",
    )
    for ticker in mismatch_tickers[: args.max_examples]:
        row = upstream_by_ticker[ticker]
        _print_row(
            "selected_mismatches",
            ticker,
            _normalize_report_value(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA"),
            _normalize_report_value(row.get("rolling_5_pullback_state"), "INSUFFICIENT_DATA"),
            row.get("pullback_days"),
            row.get("latest_bos_event_type"),
            row.get("latest_bos_freshness"),
            row.get("latest_reset_reason"),
            row.get("latest_reset_freshness"),
            row.get("latest_bullish_relevance_class"),
            row.get("primary_reason"),
            row.get("blocking_reason"),
            row.get("next_action"),
        )

    _print_section("mapping_recommendation")
    _print_row("mapping_recommendation", "recommendation", "status", "evidence")
    _print_row(
        "mapping_recommendation",
        "UPSTREAM_BUILDER_REUSABLE",
        "LIKELY" if upstream_builder_reusable == 1 else "UNLIKELY",
        f"builder_callable={builder_callable}|rows_extracted={len(upstream_rows)}",
    )
    _print_row(
        "mapping_recommendation",
        "UPSTREAM_ROWS_MATCH_REPORTS_BETTER_THAN_V2",
        (
            "UNKNOWN"
            if builder_callable == 0
            else "LIKELY" if upstream_exact_rate > v2_exact_rate else "UNLIKELY"
        ),
        f"upstream_exact_rate={upstream_exact_rate:.4f}|v2_exact_rate={v2_exact_rate:.4f}",
    )
    _print_row(
        "mapping_recommendation",
        "SHOULD_EXPOSE_UPSTREAM_ROLLING5_FIELDS",
        "LIKELY" if should_expose_upstream_fields == 1 else "UNLIKELY",
        (
            f"builder_callable={builder_callable}|core_field_coverage={int(core_fields_present)}|"
            f"rows_extracted={len(upstream_rows)}"
        ),
    )
    _print_row(
        "mapping_recommendation",
        "NEEDS_HELPER_EXTRACTION",
        "LIKELY" if needs_helper_extraction == 1 else "UNLIKELY",
        f"builder_callable={builder_callable}|reason={builder_reason}",
    )

    _print_section("summary")
    _print_row("SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.status=OK")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.report_date={args.report_date}")
    _print_row(
        f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.taxonomy_version={args.taxonomy_version or ''}"
    )
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.builder_callable={builder_callable}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.rows_extracted={len(upstream_rows)}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.tickers_extracted={len(upstream_by_ticker)}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.common_tickers={len(common_tickers)}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.upstream_builder_reusable={upstream_builder_reusable}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.should_expose_upstream_fields={should_expose_upstream_fields}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.needs_helper_extraction={needs_helper_extraction}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
