from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardParseResult,
    DatacenterDashboardRow,
    parse_datacenter_dashboard_file,
)
from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
PULLBACK_DEFAULT = "INSUFFICIENT_DATA"
ENTRY_DEFAULT = "INSUFFICIENT_DATA"
CANDIDATE_PRIORITY_DEFAULT = ""
CANDIDATE_LABEL_DEFAULT = "MISSING"
PULLBACK_PRIORITY = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)
HORIZON_PRIORITY = {
    "daily": 0,
    "rolling 2d": 1,
    "rolling 5d": 2,
    "rolling 30d": 3,
}
SUMMARY_FIELDS = (
    "pullback_days",
    "rolling_5_pullback_state",
    "rolling_5d_status",
    "fast_ema10_pullback_days",
    "conservative_ema20_pullback_days",
    "latest_bos_freshness",
    "latest_reset_freshness",
    "latest_bullish_relevance_class",
    "latest_bearish_relevance_class",
    "primary_reason",
    "blocking_reason",
    "next_action",
    "high_exit_risk_days_count",
    "return_10d_lt_minus_8pct",
    "close_below_ema20",
)
TOKEN_FIELD_ITEMS = (
    "pullback_candidate",
    "early_pullback",
    "failed_pullback",
    "short_term_breakdown",
    "pullback_days",
    "rolling_5_pullback_state",
    "rolling_5d_status",
    "latest_bos_freshness",
    "latest_reset_freshness",
    "freshness_status",
    "FRESH_BULLISH_SIGNAL",
    "STRUCTURE_WARNING_OVERRIDES_BULLISH",
    "latest_bos_event_type",
    "latest_reset_reason",
    "ma_break_status",
    "high_exit_risk_days_count",
    "return_10d_lt_minus_8pct",
    "close_below_ema20",
    "blocking_reason",
    "blocking_reasons",
    "next_action",
)
ROW_SCAN_FIELDS = (
    "raw_action",
    "raw_status",
    "reason",
    "blocking_reasons",
    "ma_break_status",
    "freshness_status",
    "latest_bos_event_type",
    "latest_reset_reason",
)


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
    selected: list[str] = []
    seen: set[str] = set()
    for token in raw.replace(",", " ").split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            selected.append(ticker)
    return selected


def _connect_analysis_read_only(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise ValueError(f"analysis_db not found: {path}")
    conn = _connect_read_only(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _require_table(conn: sqlite3.Connection, table_name: str) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"required table missing: {table_name}")


def _taxonomy_version_for_report_date(analysis_db: str, report_date: str) -> str:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, ENRICHMENT_TABLE)
        rows = conn.execute(
            f"""
            SELECT taxonomy_version, COUNT(*) AS row_count
            FROM {ENRICHMENT_TABLE}
            WHERE signal_date = ?
            GROUP BY taxonomy_version
            ORDER BY row_count DESC, taxonomy_version ASC
            """,
            (report_date,),
        ).fetchall()
    if not rows:
        raise ValueError(
            f"no enrichment rows found for report_date={report_date} in {ENRICHMENT_TABLE}"
        )
    if len(rows) > 1:
        raise ValueError(
            f"multiple taxonomy_version values found for report_date={report_date}"
        )
    return _cell(rows[0]["taxonomy_version"])


def _load_reports_rows(
    *,
    reports_dir: str,
    report_date: str,
) -> tuple[list[DatacenterDashboardRow], list[str], list[object]]:
    dashboard_status = discover_datacenter_dashboard_status(reports_dir, report_date=report_date)
    if not dashboard_status.reports:
        raise ValueError(f"no reports discovered in reports_dir={reports_dir}")
    rows: list[DatacenterDashboardRow] = []
    warnings: list[str] = []
    for report in dashboard_status.reports:
        if report.path is None:
            continue
        parse_result: DatacenterDashboardParseResult = parse_datacenter_dashboard_file(
            path=report.path,
            horizon=report.horizon,
        )
        rows.extend(parse_result.rows)
        warnings.extend(parse_result.warnings)
    return rows, warnings, dashboard_status.reports


def _snapshot_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _group_rows_by_ticker(rows: list[DatacenterDashboardRow]) -> dict[str, list[DatacenterDashboardRow]]:
    grouped: dict[str, list[DatacenterDashboardRow]] = {}
    for row in rows:
        grouped.setdefault(row.ticker.upper(), []).append(row)
    for ticker_rows in grouped.values():
        ticker_rows.sort(key=lambda row: (HORIZON_PRIORITY.get(row.horizon, 99), row.row_kind or ""))
    return grouped


def _normalized_field(value: object, default: str) -> str:
    text = _cell(value)
    return text or default


def _snapshot_or_decision_value(
    snapshot_row: dict[str, object] | None,
    decision: object | None,
    field_name: str,
    default: str = "",
) -> str:
    if snapshot_row is not None:
        text = _cell(snapshot_row.get(field_name))
        if text:
            return text
    if decision is not None:
        text = _cell(getattr(decision, field_name, None))
        if text:
            return text
    return default


def _candidate_priority_int(value: object) -> int | None:
    text = _cell(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _selection_reason(
    reports_row: dict[str, object] | None,
    enrichment_row: dict[str, object] | None,
) -> tuple[int, str]:
    reports_pullback = _normalized_field(
        None if reports_row is None else reports_row.get("pullback_validity"),
        PULLBACK_DEFAULT,
    )
    enrichment_pullback = _normalized_field(
        None if enrichment_row is None else enrichment_row.get("pullback_validity"),
        PULLBACK_DEFAULT,
    )
    reports_entry = _normalized_field(
        None if reports_row is None else reports_row.get("entry_readiness"),
        ENTRY_DEFAULT,
    )
    enrichment_entry = _normalized_field(
        None if enrichment_row is None else enrichment_row.get("entry_readiness"),
        ENTRY_DEFAULT,
    )
    reports_priority = _normalized_field(
        None if reports_row is None else reports_row.get("candidate_priority_label"),
        CANDIDATE_LABEL_DEFAULT,
    )
    enrichment_priority = _normalized_field(
        None if enrichment_row is None else enrichment_row.get("candidate_priority_label"),
        CANDIDATE_LABEL_DEFAULT,
    )
    reasons: list[str] = []
    if reports_pullback != enrichment_pullback:
        reasons.append("PULLBACK_VALIDITY_DIFFERENT")
    if reports_entry != enrichment_entry:
        reasons.append("ENTRY_READINESS_DIFFERENT")
    if reports_priority != enrichment_priority:
        reasons.append("CANDIDATE_PRIORITY_LABEL_DIFFERENT")
    priority = PULLBACK_PRIORITY.index(reports_pullback) if reports_pullback in PULLBACK_PRIORITY else len(PULLBACK_PRIORITY)
    return priority, ",".join(reasons) or "MATCH"


def _selected_tickers(
    *,
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    if explicit_tickers:
        selected: list[tuple[str, str]] = []
        for ticker in explicit_tickers:
            if ticker in reports_by_ticker and ticker in enrichment_by_ticker:
                selected.append((ticker, "EXPLICIT"))
        return selected[:max_examples]

    candidates: list[tuple[int, str, str]] = []
    for ticker in sorted(set(reports_by_ticker) & set(enrichment_by_ticker)):
        priority, reason = _selection_reason(reports_by_ticker.get(ticker), enrichment_by_ticker.get(ticker))
        if reason != "MATCH":
            candidates.append((priority, ticker, reason))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [(ticker, reason) for _priority, ticker, reason in candidates[:max_examples]]


def _raw_fields_summary(row: DatacenterDashboardRow) -> str:
    summary = {
        key: row.raw_fields[key]
        for key in SUMMARY_FIELDS
        if _cell(row.raw_fields.get(key))
    }
    return json.dumps(summary, sort_keys=True, separators=(",", ":"))


def _field_or_attr_value(row: DatacenterDashboardRow, name: str) -> object:
    if name in row.raw_fields and _cell(row.raw_fields.get(name)):
        return row.raw_fields.get(name)
    if hasattr(row, name):
        return getattr(row, name)
    if name == "blocking_reason":
        return row.raw_fields.get("blocking_reason") or row.blocking_reasons
    if name == "blocking_reasons":
        return row.blocking_reasons or row.raw_fields.get("blocking_reasons")
    return None


def _token_match_observation(rows: list[DatacenterDashboardRow], token: str) -> dict[str, object]:
    lowered = token.lower()
    for row in rows:
        for field_name in ROW_SCAN_FIELDS:
            value = getattr(row, field_name)
            if value and lowered in str(value).lower():
                return {
                    "present": True,
                    "value": token,
                    "horizon": row.horizon,
                    "source_name": field_name,
                }
        for key, value in row.raw_fields.items():
            if value and lowered in str(value).lower():
                return {
                    "present": True,
                    "value": token,
                    "horizon": row.horizon,
                    "source_name": key,
                }
    return {"present": False, "value": "", "horizon": "", "source_name": ""}


def _field_observation(rows: list[DatacenterDashboardRow], name: str) -> dict[str, object]:
    for row in rows:
        value = _field_or_attr_value(row, name)
        text = _cell(value)
        if text:
            source_name = name
            if name not in row.raw_fields and hasattr(row, name):
                source_name = name
            elif name in row.raw_fields:
                source_name = name
            elif name == "blocking_reason" and row.blocking_reasons:
                source_name = "blocking_reasons"
            return {
                "present": True,
                "value": text,
                "horizon": row.horizon,
                "source_name": source_name,
            }
    return {"present": False, "value": "", "horizon": "", "source_name": ""}


def _observation(rows: list[DatacenterDashboardRow], item: str) -> dict[str, object]:
    if item in {
        "pullback_candidate",
        "early_pullback",
        "failed_pullback",
        "short_term_breakdown",
        "FRESH_BULLISH_SIGNAL",
        "STRUCTURE_WARNING_OVERRIDES_BULLISH",
    }:
        return _token_match_observation(rows, item)
    return _field_observation(rows, item)


def _delta_type(
    reports_obs: dict[str, object],
    enrichment_obs: dict[str, object],
) -> str:
    reports_present = bool(reports_obs["present"])
    enrichment_present = bool(enrichment_obs["present"])
    if reports_present and not enrichment_present:
        return "MISSING_IN_ENRICHMENT"
    if enrichment_present and not reports_present:
        return "MISSING_IN_REPORTS"
    if not reports_present and not enrichment_present:
        return "MATCH"
    if _cell(reports_obs["value"]) != _cell(enrichment_obs["value"]):
        return "DIFFERENT_VALUE"
    if _cell(reports_obs["source_name"]) != _cell(enrichment_obs["source_name"]):
        return "DIFFERENT_FIELD_NAME"
    if _cell(reports_obs["horizon"]) != _cell(enrichment_obs["horizon"]):
        return "DIFFERENT_HORIZON"
    return "MATCH"


def _parity_counts(
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    field_name: str,
    default: str,
) -> tuple[int, int, int, int]:
    matched = 0
    different = 0
    missing_reports = 0
    missing_enrichment = 0
    for ticker in sorted(set(reports_by_ticker) | set(enrichment_by_ticker)):
        reports_row = reports_by_ticker.get(ticker)
        enrichment_row = enrichment_by_ticker.get(ticker)
        reports_value = _normalized_field(None if reports_row is None else reports_row.get(field_name), default)
        enrichment_value = _normalized_field(
            None if enrichment_row is None else enrichment_row.get(field_name),
            default,
        )
        reports_missing = reports_row is None or not _cell(reports_row.get(field_name))
        enrichment_missing = enrichment_row is None or not _cell(enrichment_row.get(field_name))
        if reports_missing:
            missing_reports += 1
        if enrichment_missing:
            missing_enrichment += 1
        if reports_missing or enrichment_missing:
            continue
        if reports_value == enrichment_value:
            matched += 1
        else:
            different += 1
    return matched, different, missing_reports, missing_enrichment


def _decision_input_rows(
    grouped_rows: dict[str, list[DatacenterDashboardRow]],
    ticker: str,
) -> list[DatacenterDashboardRow]:
    return grouped_rows.get(ticker, [])


def _has_pullback_context(rows: list[DatacenterDashboardRow]) -> bool:
    for item in ("pullback_candidate", "early_pullback", "failed_pullback", "pullback_days"):
        if _observation(rows, item)["present"]:
            return True
    return False


def _has_freshness_context(rows: list[DatacenterDashboardRow]) -> bool:
    for item in ("latest_bos_freshness", "latest_reset_freshness", "freshness_status", "FRESH_BULLISH_SIGNAL"):
        if _observation(rows, item)["present"]:
            return True
    return False


def _acute_context_differs(
    reports_rows: list[DatacenterDashboardRow],
    enrichment_rows: list[DatacenterDashboardRow],
) -> bool:
    for item in (
        "freshness_status",
        "ma_break_status",
        "high_exit_risk_days_count",
        "latest_bos_event_type",
        "latest_reset_reason",
    ):
        if _delta_type(_observation(reports_rows, item), _observation(enrichment_rows, item)) != "MATCH":
            return True
    return False


def _likely_divergence_point(
    *,
    reports_rows: list[DatacenterDashboardRow],
    enrichment_rows: list[DatacenterDashboardRow],
    reports_decision: object | None,
    enrichment_decision: object | None,
) -> str:
    if _has_pullback_context(reports_rows) and not _has_pullback_context(enrichment_rows):
        return "NO_PULLBACK_CONTEXT"
    if _has_freshness_context(reports_rows) and not _has_freshness_context(enrichment_rows):
        if _observation(reports_rows, "FRESH_BULLISH_SIGNAL")["present"]:
            return "FRESH_BULLISH_SIGNAL"
        return "MISSING_STRUCTURE_OR_FRESHNESS_CONTEXT"
    if _acute_context_differs(reports_rows, enrichment_rows):
        if (
            _observation(reports_rows, "ma_break_status")["present"]
            or _observation(enrichment_rows, "ma_break_status")["present"]
        ):
            return "MA_BREAK"
        return "ACUTE_BOS_DOWN_CONFIRMATION"
    reports_pullback = _cell(getattr(reports_decision, "pullback_validity", None))
    enrichment_pullback = _cell(getattr(enrichment_decision, "pullback_validity", None))
    reports_entry = _cell(getattr(reports_decision, "entry_readiness", None))
    enrichment_entry = _cell(getattr(enrichment_decision, "entry_readiness", None))
    reports_label = _cell(getattr(reports_decision, "candidate_priority_label", None))
    enrichment_label = _cell(getattr(enrichment_decision, "candidate_priority_label", None))
    if reports_pullback != enrichment_pullback:
        if reports_pullback == "STRUCTURE_BLOCKED_PULLBACK" or enrichment_pullback == "STRUCTURE_BLOCKED_PULLBACK":
            return "STRUCTURE_BLOCKER"
        return "UNKNOWN"
    if reports_entry != enrichment_entry:
        return "ENTRY_READINESS_ACTION_COMBINATION"
    if reports_label != enrichment_label:
        return "CANDIDATE_PRIORITY_MAPPING"
    return "UNKNOWN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare reports-mode and enrichment-mode factual decision parity for "
            "pullback_validity, entry_readiness, and candidate priority."
        )
    )
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
        reports_rows, parse_warnings, report_statuses = _load_reports_rows(
            reports_dir=args.reports_dir,
            report_date=args.report_date,
        )
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        enrichment_source_rows = load_ticker_enrichment_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
        )
    except Exception as exc:  # pragma: no cover - exercised by CLI behavior
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    reports_decision_result = build_datacenter_ticker_decisions(reports_rows)
    enrichment_decision_result = build_decisions_from_ticker_enrichment_rows(enrichment_source_rows)
    enrichment_rows = build_dashboard_rows_from_ticker_enrichment_rows(enrichment_source_rows)

    reports_rows_by_ticker = _group_rows_by_ticker(reports_rows)
    enrichment_rows_by_ticker = _group_rows_by_ticker(enrichment_rows)
    reports_snapshot_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
    enrichment_snapshot_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
    reports_decision_by_ticker = {decision.ticker.upper(): decision for decision in reports_decision_result.decisions}
    enrichment_decision_by_ticker = {
        decision.ticker.upper(): decision for decision in enrichment_decision_result.decisions
    }

    explicit_tickers = _parse_tickers(args.tickers)
    selected = _selected_tickers(
        reports_by_ticker=reports_snapshot_by_ticker,
        enrichment_by_ticker=enrichment_snapshot_by_ticker,
        explicit_tickers=explicit_tickers,
        max_examples=args.max_examples,
    )

    _print_section("run_summary")
    _print_row("run_summary", "side", "path_or_db", "run_id", "report_date", "source")
    _print_row("run_summary", "reports_dir", args.reports_dir, args.reports_run_id, args.report_date, "reports_parse")
    _print_row("run_summary", "reports_dashboard", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "enrichment_dashboard", args.enrichment_dashboard_db, args.enrichment_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "analysis", args.analysis_db, taxonomy_version, args.report_date, "analysis_enrichment")

    parity_specs = (
        ("pullback_validity", PULLBACK_DEFAULT),
        ("entry_readiness", ENTRY_DEFAULT),
        ("candidate_priority", CANDIDATE_PRIORITY_DEFAULT),
        ("candidate_priority_label", CANDIDATE_LABEL_DEFAULT),
    )
    parity_counts: dict[str, tuple[int, int, int, int]] = {}
    _print_section("factual_parity_counts")
    _print_row("factual_parity_counts", "field_name", "matched", "different", "missing_reports", "missing_enrichment")
    for field_name, default in parity_specs:
        counts = _parity_counts(
            reports_snapshot_by_ticker,
            enrichment_snapshot_by_ticker,
            field_name,
            default,
        )
        parity_counts[field_name] = counts
        _print_row("factual_parity_counts", field_name, *counts)

    _print_section("selected_tickers")
    _print_row(
        "selected_tickers",
        "ticker",
        "reports_pullback_validity",
        "enrichment_pullback_validity",
        "reports_entry_readiness",
        "enrichment_entry_readiness",
        "reports_candidate_priority_label",
        "enrichment_candidate_priority_label",
        "selection_reason",
    )
    for ticker, selection_reason in selected:
        reports_row = reports_snapshot_by_ticker.get(ticker, {})
        enrichment_row = enrichment_snapshot_by_ticker.get(ticker, {})
        _print_row(
            "selected_tickers",
            ticker,
            _normalized_field(reports_row.get("pullback_validity"), PULLBACK_DEFAULT),
            _normalized_field(enrichment_row.get("pullback_validity"), PULLBACK_DEFAULT),
            _normalized_field(reports_row.get("entry_readiness"), ENTRY_DEFAULT),
            _normalized_field(enrichment_row.get("entry_readiness"), ENTRY_DEFAULT),
            _normalized_field(reports_row.get("candidate_priority_label"), CANDIDATE_LABEL_DEFAULT),
            _normalized_field(enrichment_row.get("candidate_priority_label"), CANDIDATE_LABEL_DEFAULT),
            selection_reason,
        )

    _print_section("final_field_comparison")
    _print_row("final_field_comparison", "ticker", "field_name", "reports_value", "enrichment_value", "match")
    for ticker, _reason in selected:
        reports_row = reports_snapshot_by_ticker.get(ticker)
        enrichment_row = enrichment_snapshot_by_ticker.get(ticker)
        reports_decision = reports_decision_by_ticker.get(ticker)
        enrichment_decision = enrichment_decision_by_ticker.get(ticker)
        for field_name, default in (
            ("action", ""),
            ("pullback_validity", PULLBACK_DEFAULT),
            ("entry_readiness", ENTRY_DEFAULT),
            ("candidate_priority", CANDIDATE_PRIORITY_DEFAULT),
            ("candidate_priority_label", CANDIDATE_LABEL_DEFAULT),
            ("primary_reason", ""),
        ):
            reports_value = _snapshot_or_decision_value(reports_row, reports_decision, field_name, default)
            enrichment_value = _snapshot_or_decision_value(enrichment_row, enrichment_decision, field_name, default)
            _print_row(
                "final_field_comparison",
                ticker,
                field_name,
                reports_value,
                enrichment_value,
                int(reports_value == enrichment_value),
            )

    _print_section("decision_branch_comparison")
    _print_row(
        "decision_branch_comparison",
        "ticker",
        "side",
        "pullback_validity",
        "pullback_reason",
        "entry_readiness",
        "entry_reason",
        "candidate_priority",
        "candidate_priority_label",
        "candidate_priority_reason",
    )
    for ticker, _reason in selected:
        for side, decisions in (
            ("reports", reports_decision_by_ticker),
            ("enrichment", enrichment_decision_by_ticker),
        ):
            decision = decisions.get(ticker)
            _print_row(
                "decision_branch_comparison",
                ticker,
                side,
                _snapshot_or_decision_value(None, decision, "pullback_validity", PULLBACK_DEFAULT),
                _snapshot_or_decision_value(None, decision, "pullback_reason"),
                _snapshot_or_decision_value(None, decision, "entry_readiness", ENTRY_DEFAULT),
                _snapshot_or_decision_value(None, decision, "entry_readiness_reason"),
                _snapshot_or_decision_value(None, decision, "candidate_priority"),
                _snapshot_or_decision_value(None, decision, "candidate_priority_label", CANDIDATE_LABEL_DEFAULT),
                _snapshot_or_decision_value(None, decision, "candidate_priority_reason"),
            )

    _print_section("reports_decision_inputs")
    _print_row(
        "reports_decision_inputs",
        "ticker",
        "row_index",
        "horizon",
        "section",
        "row_kind",
        "raw_action",
        "raw_status",
        "reason",
        "blocking_reasons",
        "ma_break_status",
        "freshness_status",
        "structure_warning_overrides_bullish_signal",
        "latest_bos_event_type",
        "latest_reset_reason",
        "raw_fields_summary",
    )
    for ticker, _reason in selected:
        for index, row in enumerate(_decision_input_rows(reports_rows_by_ticker, ticker), start=1):
            _print_row(
                "reports_decision_inputs",
                ticker,
                index,
                row.horizon,
                row.section,
                row.row_kind,
                row.raw_action,
                row.raw_status,
                row.reason,
                row.blocking_reasons,
                row.ma_break_status,
                row.freshness_status,
                row.structure_warning_overrides_bullish_signal,
                row.latest_bos_event_type,
                row.latest_reset_reason,
                _raw_fields_summary(row),
            )

    _print_section("enrichment_decision_inputs")
    _print_row(
        "enrichment_decision_inputs",
        "ticker",
        "row_index",
        "horizon",
        "section",
        "row_kind",
        "raw_action",
        "raw_status",
        "reason",
        "blocking_reasons",
        "ma_break_status",
        "freshness_status",
        "structure_warning_overrides_bullish_signal",
        "latest_bos_event_type",
        "latest_reset_reason",
        "raw_fields_summary",
    )
    for ticker, _reason in selected:
        for index, row in enumerate(_decision_input_rows(enrichment_rows_by_ticker, ticker), start=1):
            _print_row(
                "enrichment_decision_inputs",
                ticker,
                index,
                row.horizon,
                row.section,
                row.row_kind,
                row.raw_action,
                row.raw_status,
                row.reason,
                row.blocking_reasons,
                row.ma_break_status,
                row.freshness_status,
                row.structure_warning_overrides_bullish_signal,
                row.latest_bos_event_type,
                row.latest_reset_reason,
                _raw_fields_summary(row),
            )

    pullback_context_gap_count = 0
    different_name_count = 0
    freshness_gap_count = 0
    acute_context_diff_count = 0
    canonical_missing_count = 0

    _print_section("token_field_presence_delta")
    _print_row(
        "token_field_presence_delta",
        "ticker",
        "token_or_field",
        "reports_present",
        "enrichment_present",
        "reports_value",
        "enrichment_value",
        "delta_type",
    )
    for ticker, _reason in selected:
        reports_input_rows = _decision_input_rows(reports_rows_by_ticker, ticker)
        enrichment_input_rows = _decision_input_rows(enrichment_rows_by_ticker, ticker)
        for item in TOKEN_FIELD_ITEMS:
            reports_obs = _observation(reports_input_rows, item)
            enrichment_obs = _observation(enrichment_input_rows, item)
            delta = _delta_type(reports_obs, enrichment_obs)
            _print_row(
                "token_field_presence_delta",
                ticker,
                item,
                int(bool(reports_obs["present"])),
                int(bool(enrichment_obs["present"])),
                reports_obs["value"],
                enrichment_obs["value"],
                delta,
            )
            if item in {
                "pullback_candidate",
                "early_pullback",
                "failed_pullback",
                "short_term_breakdown",
                "pullback_days",
                "rolling_5_pullback_state",
                "rolling_5d_status",
            } and reports_obs["present"] and not enrichment_obs["present"]:
                pullback_context_gap_count += 1
            if item in {
                "pullback_candidate",
                "rolling_5_pullback_state",
                "rolling_5d_status",
            } and delta == "DIFFERENT_FIELD_NAME":
                different_name_count += 1
            if item in {
                "latest_bos_freshness",
                "latest_reset_freshness",
                "freshness_status",
                "FRESH_BULLISH_SIGNAL",
            } and reports_obs["present"] and not enrichment_obs["present"]:
                freshness_gap_count += 1
            if item in {
                "ma_break_status",
                "freshness_status",
                "high_exit_risk_days_count",
                "latest_bos_event_type",
                "latest_reset_reason",
            } and delta != "MATCH":
                acute_context_diff_count += 1
            if item in {
                "pullback_days",
                "latest_bos_freshness",
                "latest_reset_freshness",
                "blocking_reason",
                "next_action",
            } and reports_obs["present"] and not enrichment_obs["present"]:
                canonical_missing_count += 1

    _print_section("trace_delta_summary")
    _print_row(
        "trace_delta_summary",
        "ticker",
        "reports_first_reason",
        "enrichment_first_reason",
        "reports_first_blocker",
        "enrichment_first_blocker",
        "likely_divergence_point",
    )
    for ticker, _reason in selected:
        reports_decision = reports_decision_by_ticker.get(ticker)
        enrichment_decision = enrichment_decision_by_ticker.get(ticker)
        reports_reasons = [] if reports_decision is None else list(getattr(reports_decision, "reasons", []))
        enrichment_reasons = [] if enrichment_decision is None else list(getattr(enrichment_decision, "reasons", []))
        reports_blockers = [] if reports_decision is None else list(getattr(reports_decision, "blocking_reasons", []))
        enrichment_blockers = [] if enrichment_decision is None else list(getattr(enrichment_decision, "blocking_reasons", []))
        _print_row(
            "trace_delta_summary",
            ticker,
            reports_reasons[0] if reports_reasons else "",
            enrichment_reasons[0] if enrichment_reasons else "",
            reports_blockers[0] if reports_blockers else "",
            enrichment_blockers[0] if enrichment_blockers else "",
            _likely_divergence_point(
                reports_rows=_decision_input_rows(reports_rows_by_ticker, ticker),
                enrichment_rows=_decision_input_rows(enrichment_rows_by_ticker, ticker),
                reports_decision=reports_decision,
                enrichment_decision=enrichment_decision,
            ),
        )

    final_field_not_safe = int(
        parity_counts["pullback_validity"][1] > 0
        or parity_counts["entry_readiness"][1] > 0
        or parity_counts["candidate_priority_label"][1] > 0
    )
    adapter_shape_fix_recommended = int(different_name_count > 0)
    canonical_decision_input_missing = int(canonical_missing_count > 0)

    hypotheses = [
        (
            "REPORTS_HAS_PULLBACK_CONTEXT_ENRICHMENT_LACKS",
            "LIKELY" if pullback_context_gap_count > 0 else "UNLIKELY",
            f"pullback_context_gap_count={pullback_context_gap_count}",
        ),
        (
            "ENRICHMENT_HAS_PULLBACK_CONTEXT_UNDER_DIFFERENT_NAME",
            "LIKELY" if different_name_count > 0 else "UNLIKELY",
            f"different_name_count={different_name_count}",
        ),
        (
            "REPORTS_HAS_FRESHNESS_CONTEXT_ENRICHMENT_LACKS",
            "LIKELY" if freshness_gap_count > 0 else "UNLIKELY",
            f"freshness_gap_count={freshness_gap_count}",
        ),
        (
            "ACUTE_ROW_CONTEXT_DIFFERS",
            "LIKELY" if acute_context_diff_count > 0 else "UNLIKELY",
            f"acute_context_diff_count={acute_context_diff_count}",
        ),
        (
            "FINAL_FIELD_PARITY_NOT_SAFE_FOR_SWITCH",
            "LIKELY" if final_field_not_safe else "UNLIKELY",
            (
                f"pullback_differences={parity_counts['pullback_validity'][1]},"
                f"entry_differences={parity_counts['entry_readiness'][1]},"
                f"candidate_label_differences={parity_counts['candidate_priority_label'][1]}"
            ),
        ),
        (
            "ADAPTER_SHAPE_FIX_RECOMMENDED",
            "LIKELY" if adapter_shape_fix_recommended else "UNLIKELY",
            f"different_name_count={different_name_count}",
        ),
        (
            "CANONICAL_DECISION_INPUT_MISSING",
            "LIKELY" if canonical_decision_input_missing else "UNLIKELY",
            f"canonical_missing_count={canonical_missing_count}",
        ),
    ]
    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    for hypothesis, status, evidence in hypotheses:
        _print_row("hypothesis_summary", hypothesis, status, evidence)

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_pullback_decision_trace_parity.status=OK")
    print(f"SUMMARY datacenter_dashboard_pullback_decision_trace_parity.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_pullback_decision_trace_parity.selected_tickers={len(selected)}")
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.pullback_validity_matches="
        f"{parity_counts['pullback_validity'][0]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.pullback_validity_differences="
        f"{parity_counts['pullback_validity'][1]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.entry_readiness_matches="
        f"{parity_counts['entry_readiness'][0]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.entry_readiness_differences="
        f"{parity_counts['entry_readiness'][1]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.candidate_priority_label_matches="
        f"{parity_counts['candidate_priority_label'][0]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.candidate_priority_label_differences="
        f"{parity_counts['candidate_priority_label'][1]}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.final_field_parity_not_safe_for_switch="
        f"{final_field_not_safe}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.adapter_shape_fix_recommended="
        f"{adapter_shape_fix_recommended}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.canonical_decision_input_missing="
        f"{canonical_decision_input_missing}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
