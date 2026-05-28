from __future__ import annotations

import argparse
import sys
from collections import Counter

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.run_datacenter_dashboard_rolling5_pullback_v1_classifier_audit import (
    CLASSIFIER_TO_REPORTS,
    REPORT_PRIORITY,
    Classification,
    _cell,
    _connect_analysis_read_only,
    _load_source_window_rows,
    _ma_break_confirmed,
    _normalized_text,
    _parse_tickers,
    _print_row,
    _print_section,
    _pullback_signal_present,
    _snapshot_ticker_map,
    _structure_blocker,
    _taxonomy_version_for_report_date,
    _has_bullish_signal,
    _classify_ticker as _classify_v1_ticker,
)


def _bool_token(value: object) -> bool:
    normalized = _normalized_text(value).strip().upper()
    return normalized in {"1", "TRUE", "YES", "Y", "T"}


def _strict_breakdown_blocker(window_rows: list[dict[str, object]]) -> bool:
    for row in window_rows:
        if _ma_break_confirmed(row):
            return True
        if _bool_token(row.get("return_10d_lt_minus_8pct")):
            return True
        if _bool_token(row.get("close_below_ema20")):
            return True
    return False


def _classify_v2_ticker(
    ticker: str,
    reports_pullback_validity: str,
    window_rows: list[dict[str, object]],
) -> Classification:
    latest_row = window_rows[-1] if window_rows else {}
    if len(window_rows) == 0:
        classifier_status = "INSUFFICIENT_DATA"
        reason = "source_rows=0"
        return Classification(
            ticker=ticker,
            reports_pullback_validity=reports_pullback_validity,
            classifier_status=classifier_status,
            classifier_mapped_status=CLASSIFIER_TO_REPORTS[classifier_status],
            source_rows=0,
            pullback_days=0,
            latest_bullish_signal_age=None,
            structure_blocker=0,
            breakdown_blocker=0,
            latest_return_10d=latest_row.get("return_10d"),
            latest_distance_to_ema20_pct=latest_row.get("distance_to_ema20_pct"),
            latest_exit_risk_signal=latest_row.get("exit_risk_signal"),
            reason=reason,
        )

    pullback_days = sum(1 for row in window_rows if _pullback_signal_present(row))
    bullish_indices = [index for index, row in enumerate(window_rows) if _has_bullish_signal(row)]
    latest_bullish_signal_age = (
        len(window_rows) - 1 - bullish_indices[-1] if bullish_indices else None
    )
    structure_blocker = int(
        pullback_days > 0 and any(_structure_blocker(row) for row in window_rows)
    )
    breakdown_blocker = int(_strict_breakdown_blocker(window_rows))

    if len(window_rows) < 2:
        classifier_status = "INSUFFICIENT_DATA"
    elif breakdown_blocker == 1:
        classifier_status = "BREAKDOWN_NOT_PULLBACK_CONTEXT"
    elif pullback_days > 0 and structure_blocker == 1:
        classifier_status = "STRUCTURE_BLOCKED_PULLBACK_CONTEXT"
    elif pullback_days > 0 and latest_bullish_signal_age is not None and latest_bullish_signal_age <= 1:
        classifier_status = "VALID_PULLBACK_CONTEXT"
    elif pullback_days > 0:
        classifier_status = "EARLY_PULLBACK_CONTEXT"
    else:
        classifier_status = "NO_PULLBACK_CONTEXT"

    reason = (
        f"source_rows={len(window_rows)}|pullback_days={pullback_days}|"
        f"latest_bullish_signal_age={_cell(latest_bullish_signal_age)}|"
        f"structure_blocker={structure_blocker}|breakdown_blocker={breakdown_blocker}"
    )
    return Classification(
        ticker=ticker,
        reports_pullback_validity=reports_pullback_validity,
        classifier_status=classifier_status,
        classifier_mapped_status=CLASSIFIER_TO_REPORTS[classifier_status],
        source_rows=len(window_rows),
        pullback_days=pullback_days,
        latest_bullish_signal_age=latest_bullish_signal_age,
        structure_blocker=structure_blocker,
        breakdown_blocker=breakdown_blocker,
        latest_return_10d=latest_row.get("return_10d"),
        latest_distance_to_ema20_pct=latest_row.get("distance_to_ema20_pct"),
        latest_exit_risk_signal=latest_row.get("exit_risk_signal"),
        reason=reason,
    )


def _selected_tickers(
    reports_by_ticker: dict[str, dict[str, object]],
    source_windows: dict[str, list[dict[str, object]]],
    explicit_tickers: list[str],
) -> list[str]:
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in reports_by_ticker]
    return [
        ticker
        for ticker in sorted(reports_by_ticker)
        if not (ticker == "CRGY" and not source_windows.get(ticker))
        and source_windows.get(ticker)
    ]


def _distribution_counts(classifications: list[Classification]) -> Counter[str]:
    return Counter(c.classifier_status for c in classifications)


def _confusion_counts(classifications: list[Classification]) -> Counter[tuple[str, str]]:
    return Counter((c.reports_pullback_validity, c.classifier_mapped_status) for c in classifications)


def _exact_matches(classifications: list[Classification]) -> int:
    return sum(1 for c in classifications if c.reports_pullback_validity == c.classifier_mapped_status)


def _match_count(classifications: list[Classification], status: str) -> int:
    return sum(
        1
        for c in classifications
        if c.reports_pullback_validity == status and c.classifier_mapped_status == status
    )


def _overclassification_count(classifications: list[Classification], mapped_status: str) -> int:
    return sum(
        1
        for c in classifications
        if c.reports_pullback_validity != mapped_status and c.classifier_mapped_status == mapped_status
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit comparing rolling5 pullback V1 and V2 classifiers against reports-mode."
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--lookback-rows", type=int, default=5)
    parser.add_argument("--max-examples", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_rows <= 0:
        print("ERROR: --lookback-rows must be greater than 0", file=sys.stderr)
        return 1
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
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        reports_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
        explicit_tickers = _parse_tickers(args.tickers)
        preload_tickers = explicit_tickers or sorted(reports_by_ticker)
        source_windows = _load_source_window_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
            preload_tickers,
            args.lookback_rows,
        )
        selected_tickers = _selected_tickers(reports_by_ticker, source_windows, explicit_tickers)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    v1_classifications: list[Classification] = []
    v2_classifications: list[Classification] = []
    for ticker in selected_tickers:
        reports_pullback = _normalized_text(
            reports_by_ticker[ticker].get("pullback_validity"),
            "INSUFFICIENT_DATA",
        )
        window_rows = source_windows.get(ticker, [])
        v1_classifications.append(_classify_v1_ticker(ticker, reports_pullback, window_rows))
        v2_classifications.append(_classify_v2_ticker(ticker, reports_pullback, window_rows))

    v1_distribution = _distribution_counts(v1_classifications)
    v2_distribution = _distribution_counts(v2_classifications)
    reports_distribution = Counter(c.reports_pullback_validity for c in v2_classifications)
    v1_confusion = _confusion_counts(v1_classifications)
    v2_confusion = _confusion_counts(v2_classifications)

    v1_exact_matches = _exact_matches(v1_classifications)
    v2_exact_matches = _exact_matches(v2_classifications)
    total = len(v2_classifications)
    v1_exact_match_rate = (v1_exact_matches / total) if total else 0.0
    v2_exact_match_rate = (v2_exact_matches / total) if total else 0.0

    comparison_metrics = [
        ("exact_matches", v1_exact_matches, v2_exact_matches),
        ("exact_match_rate", v1_exact_match_rate, v2_exact_match_rate),
        ("valid_early_matches", _match_count(v1_classifications, "VALID_PULLBACK") + _match_count(v1_classifications, "EARLY_PULLBACK"), _match_count(v2_classifications, "VALID_PULLBACK") + _match_count(v2_classifications, "EARLY_PULLBACK")),
        ("structure_blocked_matches", _match_count(v1_classifications, "STRUCTURE_BLOCKED_PULLBACK"), _match_count(v2_classifications, "STRUCTURE_BLOCKED_PULLBACK")),
        ("breakdown_matches", _match_count(v1_classifications, "BREAKDOWN_NOT_PULLBACK"), _match_count(v2_classifications, "BREAKDOWN_NOT_PULLBACK")),
        ("no_pullback_matches", _match_count(v1_classifications, "NO_PULLBACK"), _match_count(v2_classifications, "NO_PULLBACK")),
        ("breakdown_overclassification_count", _overclassification_count(v1_classifications, "BREAKDOWN_NOT_PULLBACK"), _overclassification_count(v2_classifications, "BREAKDOWN_NOT_PULLBACK")),
        ("no_pullback_overclassification_count", _overclassification_count(v1_classifications, "NO_PULLBACK"), _overclassification_count(v2_classifications, "NO_PULLBACK")),
    ]

    v1_by_ticker = {c.ticker: c for c in v1_classifications}
    v2_by_ticker = {c.ticker: c for c in v2_classifications}
    improvement_examples = [
        (ticker, v1_by_ticker[ticker], v2_by_ticker[ticker])
        for ticker in selected_tickers
        if v1_by_ticker[ticker].classifier_mapped_status != v1_by_ticker[ticker].reports_pullback_validity
        and v2_by_ticker[ticker].classifier_mapped_status == v2_by_ticker[ticker].reports_pullback_validity
    ]
    regression_examples = [
        (ticker, v1_by_ticker[ticker], v2_by_ticker[ticker])
        for ticker in selected_tickers
        if v1_by_ticker[ticker].classifier_mapped_status == v1_by_ticker[ticker].reports_pullback_validity
        and v2_by_ticker[ticker].classifier_mapped_status != v2_by_ticker[ticker].reports_pullback_validity
    ]
    improvement_examples.sort(
        key=lambda item: (REPORT_PRIORITY.index(item[1].reports_pullback_validity), item[0])
    )
    regression_examples.sort(
        key=lambda item: (REPORT_PRIORITY.index(item[1].reports_pullback_validity), item[0])
    )

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row("run_summary", "reports", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_db")
    _print_row("run_summary", "analysis", args.analysis_db, taxonomy_version, args.report_date, "analysis_db")

    _print_section("classifier_comparison_summary")
    _print_row("classifier_comparison_summary", "metric", "v1_value", "v2_value", "delta")
    for metric_name, v1_value, v2_value in comparison_metrics:
        delta = v2_value - v1_value
        _print_row("classifier_comparison_summary", metric_name, v1_value, v2_value, delta)

    _print_section("v1_distribution")
    _print_row("v1_distribution", "classifier_status", "mapped_status", "count")
    for classifier_status, count in sorted(v1_distribution.items()):
        _print_row("v1_distribution", classifier_status, CLASSIFIER_TO_REPORTS[classifier_status], count)

    _print_section("v2_distribution")
    _print_row("v2_distribution", "classifier_status", "mapped_status", "count")
    for classifier_status, count in sorted(v2_distribution.items()):
        _print_row("v2_distribution", classifier_status, CLASSIFIER_TO_REPORTS[classifier_status], count)

    _print_section("reports_distribution")
    _print_row("reports_distribution", "pullback_validity", "count")
    for pullback_validity, count in sorted(reports_distribution.items()):
        _print_row("reports_distribution", pullback_validity, count)

    _print_section("v1_confusion_matrix")
    _print_row("v1_confusion_matrix", "reports_pullback_validity", "v1_mapped_status", "count")
    for (reports_pullback, mapped_status), count in sorted(v1_confusion.items()):
        _print_row("v1_confusion_matrix", reports_pullback, mapped_status, count)

    _print_section("v2_confusion_matrix")
    _print_row("v2_confusion_matrix", "reports_pullback_validity", "v2_mapped_status", "count")
    for (reports_pullback, mapped_status), count in sorted(v2_confusion.items()):
        _print_row("v2_confusion_matrix", reports_pullback, mapped_status, count)

    _print_section("v2_improvement_examples")
    _print_row("v2_improvement_examples", "ticker", "reports_pullback_validity", "v1_mapped_status", "v2_mapped_status", "reason")
    for ticker, v1, v2 in improvement_examples[: args.max_examples]:
        _print_row(
            "v2_improvement_examples",
            ticker,
            v1.reports_pullback_validity,
            v1.classifier_mapped_status,
            v2.classifier_mapped_status,
            v2.reason,
        )

    _print_section("v2_regression_examples")
    _print_row("v2_regression_examples", "ticker", "reports_pullback_validity", "v1_mapped_status", "v2_mapped_status", "reason")
    for ticker, v1, v2 in regression_examples[: args.max_examples]:
        _print_row(
            "v2_regression_examples",
            ticker,
            v1.reports_pullback_validity,
            v1.classifier_mapped_status,
            v2.classifier_mapped_status,
            v2.reason,
        )

    v1_breakdown_over = _overclassification_count(v1_classifications, "BREAKDOWN_NOT_PULLBACK")
    v2_breakdown_over = _overclassification_count(v2_classifications, "BREAKDOWN_NOT_PULLBACK")
    v1_breakdown_matches = _match_count(v1_classifications, "BREAKDOWN_NOT_PULLBACK")
    v2_breakdown_matches = _match_count(v2_classifications, "BREAKDOWN_NOT_PULLBACK")
    severe_regression = v2_breakdown_matches < max(0, v1_breakdown_matches - 3)
    v2_worth = v2_exact_match_rate >= 0.60 and not severe_regression

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "V2_REDUCES_BREAKDOWN_OVERCLASSIFICATION",
        "LIKELY" if v2_breakdown_over < v1_breakdown_over else "UNLIKELY",
        f"v1_breakdown_overclassification={v1_breakdown_over}|v2_breakdown_overclassification={v2_breakdown_over}",
    )
    _print_row(
        "hypothesis_summary",
        "V2_IMPROVES_EXACT_MATCH_RATE",
        "LIKELY" if (v2_exact_match_rate - v1_exact_match_rate) >= 0.05 else "UNLIKELY",
        f"v1_exact_match_rate={v1_exact_match_rate:.4f}|v2_exact_match_rate={v2_exact_match_rate:.4f}",
    )
    _print_row(
        "hypothesis_summary",
        "V2_REGRESSES_TRUE_BREAKDOWN",
        "LIKELY" if severe_regression else "UNLIKELY",
        f"v1_breakdown_matches={v1_breakdown_matches}|v2_breakdown_matches={v2_breakdown_matches}",
    )
    _print_row(
        "hypothesis_summary",
        "V2_WORTH_SCHEMA_IMPLEMENTATION",
        "LIKELY" if v2_worth else "UNLIKELY",
        f"v2_exact_match_rate={v2_exact_match_rate:.4f}|severe_regression={int(severe_regression)}",
    )
    _print_row(
        "hypothesis_summary",
        "NEEDS_REPORTS_SEMANTIC_SOURCE",
        "LIKELY" if v2_exact_match_rate < 0.60 else "UNLIKELY",
        f"v2_exact_match_rate={v2_exact_match_rate:.4f}",
    )

    _print_section("summary")
    _print_row("SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.status=OK")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.report_date={args.report_date}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.lookback_rows={args.lookback_rows}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.tickers_evaluated={total}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v1_exact_matches={v1_exact_matches}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v1_exact_match_rate={v1_exact_match_rate:.4f}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_exact_matches={v2_exact_matches}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_exact_match_rate={v2_exact_match_rate:.4f}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_improvements={len(improvement_examples)}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_regressions={len(regression_examples)}")
    _print_row(f"SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_worth_schema_implementation={int(v2_worth)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
