from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterTickerDecision,
    build_datacenter_ticker_decisions,
)
from dev_tools.datacenter_dashboard_inspector import (
    DatacenterTickerInspectorView,
    build_datacenter_ticker_inspector_view,
)
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardRow,
    parse_datacenter_dashboard_file,
    parse_datacenter_dashboard_reports,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    discover_datacenter_dashboard_status,
)

_ACTION_ORDER = (
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only smoke/debug CLI for the Datacenter Dashboard pipeline."
    )
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--ticker")
    parser.add_argument("--max-rows", type=int)
    return parser


def _print_summary(key: str, value: object) -> None:
    print(f"SUMMARY {key}={value}")


def _collect_rows(dashboard_status: DatacenterDashboardStatus) -> list[DatacenterDashboardRow]:
    parsed_rows: list[DatacenterDashboardRow] = []
    for report in dashboard_status.reports:
        if not report.path:
            continue
        parsed_rows.extend(
            parse_datacenter_dashboard_file(
                path=report.path,
                horizon=report.horizon,
            ).rows
        )
    return parsed_rows


def _selected_decision(
    decision_result: DatacenterDecisionBatchResult,
    ticker: str,
) -> DatacenterTickerDecision | None:
    normalized = ticker.strip().upper()
    for decision in decision_result.decisions:
        if decision.ticker.upper() == normalized:
            return decision
    return None


def _print_decision_rows(
    decision_result: DatacenterDecisionBatchResult,
    max_rows: int,
) -> None:
    for decision in decision_result.decisions[:max_rows]:
        print(
            "DECISION "
            f"ticker={decision.ticker} "
            f"action={decision.action} "
            f"severity={decision.severity} "
            f"reason={decision.primary_reason or ''}"
        )


def _print_inspector_rows(
    *,
    ticker: str,
    inspector_view: DatacenterTickerInspectorView,
    rows: list[DatacenterDashboardRow],
) -> None:
    print(
        "INSPECTOR "
        f"ticker={inspector_view.ticker} "
        f"action={inspector_view.action} "
        f"severity={inspector_view.severity}"
    )
    print(
        "INSPECTOR "
        "supporting_signals="
        + ";".join(inspector_view.supporting_signals)
    )
    print(
        "INSPECTOR "
        "conflicting_signals="
        + ";".join(inspector_view.conflicting_signals)
    )
    print(
        "INSPECTOR "
        f"override_explanation={inspector_view.override_explanation or ''}"
    )

    matching_rows = [row for row in rows if row.ticker.upper() == ticker.strip().upper()]
    matching_rows.sort(
        key=lambda row: (
            row.horizon,
            row.source_file,
            row.section or "",
            row.raw_status or "",
            row.raw_action or "",
        )
    )
    for row in matching_rows:
        print(
            "INSPECTOR "
            f"horizon={row.horizon} "
            f"raw_action={row.raw_action or ''} "
            f"raw_status={row.raw_status or ''} "
            f"reason={row.reason or ''}"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reports_dir = Path(args.reports_dir)
    if reports_dir.exists() and not reports_dir.is_dir():
        print(
            f"reports-dir is not a directory: {reports_dir}",
            file=sys.stderr,
        )
        return 1

    dashboard_status = discover_datacenter_dashboard_status(str(reports_dir))
    parse_batch_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)

    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(
        1 for report in dashboard_status.reports if report.status != "OK"
    )

    _print_summary("reports_dir", reports_dir)
    _print_summary("readiness", dashboard_status.overall_status)
    _print_summary("found_reports", found_reports)
    _print_summary("missing_reports", missing_reports)
    _print_summary("total_parsed_rows", parse_batch_result.total_row_count)
    _print_summary("total_parse_warnings", parse_batch_result.total_warning_count)
    _print_summary("decision_total", len(decision_result.decisions))
    for action_name in _ACTION_ORDER:
        _print_summary(
            f"action.{action_name}",
            decision_result.action_counts.get(action_name, 0),
        )

    if args.ticker:
        selected_ticker = args.ticker.strip().upper()
        decision = _selected_decision(decision_result, selected_ticker)
        _print_summary("selected_ticker", selected_ticker)
        _print_summary("selected_ticker_found", 1 if decision is not None else 0)
        if decision is None:
            _print_summary("selected_action", "")
            _print_summary("selected_severity", "")
            _print_summary("selected_conflict_detected", "")
        else:
            inspector_view = build_datacenter_ticker_inspector_view(
                decision=decision,
                rows=parsed_rows,
            )
            _print_summary("selected_action", inspector_view.action)
            _print_summary("selected_severity", inspector_view.severity)
            _print_summary(
                "selected_conflict_detected",
                str(inspector_view.conflict_detected).lower(),
            )
            _print_inspector_rows(
                ticker=selected_ticker,
                inspector_view=inspector_view,
                rows=parsed_rows,
            )

    if args.max_rows is not None and args.max_rows > 0:
        _print_decision_rows(decision_result, args.max_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
