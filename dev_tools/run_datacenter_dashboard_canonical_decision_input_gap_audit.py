from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
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
SOURCE_TABLE = "dc_ticker_swing_signal_daily"
PULLBACK_DEFAULT = "INSUFFICIENT_DATA"
ENTRY_DEFAULT = "INSUFFICIENT_DATA"
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
FIELD_ITEMS = (
    "pullback_days",
    "rolling_5_pullback_state",
    "rolling_5d_status",
    "fast_ema10_pullback_days",
    "conservative_ema20_pullback_days",
    "freshness_status",
    "structure_warning_overrides_bullish_signal",
    "latest_bos_event_type",
    "latest_bos_freshness",
    "latest_reset_reason",
    "latest_reset_freshness",
    "ma_break_status",
    "high_exit_risk_days_count",
    "latest_bullish_relevance_class",
    "latest_bearish_relevance_class",
    "primary_reason",
    "blocking_reason",
    "blocking_reasons",
    "next_action",
    "return_10d_lt_minus_8pct",
    "close_below_ema20",
)
TOKEN_ITEMS = (
    "pullback_candidate",
    "early_pullback",
    "failed_pullback",
    "short_term_breakdown",
    "no_pullback",
    "fresh_bullish_signal",
    "structure_warning_overrides_bullish",
    "bos_down",
    "double_bos_down",
    "reset",
    "sma50_confirmed_break",
    "ema20_confirmed_break",
    "return_10d_lt_minus_8pct",
    "close_below_ema20",
    "high_exit_risk",
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
SHARED_HELPER_FIELDS = {
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
}
DIFFERENT_NAME_EQUIVALENTS = {
    "blocking_reason": ("blocking_reasons",),
    "blocking_reasons": ("blocking_reason",),
    "rolling_5_pullback_state": ("rolling_5d_status",),
    "rolling_5d_status": ("rolling_5_pullback_state",),
}
FIX_TYPE_BY_ATTRIBUTION = {
    "PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER": "ADAPTER_EXPOSURE_FIX",
    "PRESENT_WITH_DIFFERENT_NAME": "ADAPTER_EXPOSURE_FIX",
    "PRESENT_WITH_DIFFERENT_HORIZON": "ADAPTER_EXPOSURE_FIX",
    "PRESENT_IN_SOURCE_NOT_ENRICHMENT": "ENRICHMENT_WRITER_MAPPING_FIX",
    "DERIVABLE_FROM_SHARED_HELPER": "SHARED_HELPER_PAYLOAD_FIX",
    "PRESENT_IN_REPORTS_ONLY": "REPORTS_ONLY_SEMANTIC",
    "NOT_FOUND": "SOURCE_SCHEMA_GAP",
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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


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
) -> tuple[list[DatacenterDashboardRow], list[str]]:
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
    return rows, warnings


def _load_source_rows(
    analysis_db: str,
    report_date: str,
    taxonomy_version: str,
) -> dict[str, dict[str, object]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, SOURCE_TABLE)
        source_columns = _table_columns(conn, SOURCE_TABLE)
        has_taxonomy = "taxonomy_version" in source_columns
        order_parts = ["ticker ASC"]
        if "signal_version" in source_columns:
            order_parts.append("signal_version ASC")
        order_sql = ", ".join(order_parts)
        if has_taxonomy:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {SOURCE_TABLE}
                WHERE signal_date = ? AND taxonomy_version = ?
                ORDER BY {order_sql}
                """,
                (report_date, taxonomy_version),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {SOURCE_TABLE}
                WHERE signal_date = ?
                ORDER BY {order_sql}
                """,
                (report_date,),
            ).fetchall()
    by_ticker: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row["ticker"]).upper()
        if ticker and ticker not in by_ticker:
            by_ticker[ticker] = {key: row[key] for key in row.keys()}
    return by_ticker


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


def _field_observation(rows: list[DatacenterDashboardRow], name: str) -> dict[str, object]:
    for row in rows:
        value = _field_or_attr_value(row, name)
        text = _cell(value)
        if text:
            source_name = name
            if name == "blocking_reason" and row.blocking_reasons and "blocking_reason" not in row.raw_fields:
                source_name = "blocking_reasons"
            return {
                "present": True,
                "value": text,
                "horizon": row.horizon,
                "source_name": source_name,
            }
    return {"present": False, "value": "", "horizon": "", "source_name": ""}


def _token_observation(rows: list[DatacenterDashboardRow], token: str) -> dict[str, object]:
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


def _observation(rows: list[DatacenterDashboardRow], item: str, *, is_token: bool) -> dict[str, object]:
    if is_token:
        return _token_observation(rows, item)
    return _field_observation(rows, item)


def _value_from_mapping(row: dict[str, object] | None, name: str) -> str:
    if row is None:
        return ""
    text = _cell(row.get(name))
    if text:
        return text
    for alias in DIFFERENT_NAME_EQUIVALENTS.get(name, ()):
        alias_text = _cell(row.get(alias))
        if alias_text:
            return alias_text
    return ""


def _mapping_has_token(row: dict[str, object] | None, token: str) -> tuple[bool, str]:
    if row is None:
        return False, ""
    lowered = token.lower()
    for key, value in row.items():
        text = _cell(value)
        if text and lowered in text.lower():
            return True, key
    return False, ""


def _infer_attribution(
    *,
    item: str,
    is_token: bool,
    reports_obs: dict[str, object],
    enrichment_obs: dict[str, object],
    enrichment_table_row: dict[str, object] | None,
    source_row: dict[str, object] | None,
) -> tuple[str, str]:
    if not reports_obs["present"] and not enrichment_obs["present"]:
        return "NOT_FOUND", "not present in reports or enrichment adapter"
    if reports_obs["present"] and enrichment_obs["present"]:
        if _cell(reports_obs["source_name"]) != _cell(enrichment_obs["source_name"]):
            return (
                "PRESENT_WITH_DIFFERENT_NAME",
                f"reports_source={reports_obs['source_name']}, enrichment_source={enrichment_obs['source_name']}",
            )
        if _cell(reports_obs["horizon"]) != _cell(enrichment_obs["horizon"]):
            return (
                "PRESENT_WITH_DIFFERENT_HORIZON",
                f"reports_horizon={reports_obs['horizon']}, enrichment_horizon={enrichment_obs['horizon']}",
            )
        return "NOT_FOUND", "present on both sides but different value"

    if reports_obs["present"] and not enrichment_obs["present"]:
        if is_token:
            token_present, source_name = _mapping_has_token(enrichment_table_row, item)
            if token_present:
                return (
                    "PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER",
                    f"enrichment_table_field={source_name}",
                )
            token_present, source_name = _mapping_has_token(source_row, item)
            if token_present:
                return (
                    "PRESENT_IN_SOURCE_NOT_ENRICHMENT",
                    f"source_table_field={source_name}",
                )
            if item in SHARED_HELPER_FIELDS or item in {
                "pullback_candidate",
                "early_pullback",
                "failed_pullback",
                "short_term_breakdown",
                "no_pullback",
                "bos_down",
                "double_bos_down",
                "reset",
            }:
                return "DERIVABLE_FROM_SHARED_HELPER", "shared rolling5 helper/upstream fields cover this token"
            return "PRESENT_IN_REPORTS_ONLY", "seen only in reports decision rows"

        direct_text = _cell(None if enrichment_table_row is None else enrichment_table_row.get(item))
        if direct_text:
            return (
                "PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER",
                f"enrichment_table_field={item}",
            )
        for alias in DIFFERENT_NAME_EQUIVALENTS.get(item, ()):
            alias_text = _cell(None if enrichment_table_row is None else enrichment_table_row.get(alias))
            if alias_text:
                return (
                    "PRESENT_WITH_DIFFERENT_NAME",
                    f"enrichment_table_field={alias}",
                )
        source_text = _cell(None if source_row is None else source_row.get(item))
        if source_text:
            return (
                "PRESENT_IN_SOURCE_NOT_ENRICHMENT",
                f"source_table_field={item}",
            )
        for alias in DIFFERENT_NAME_EQUIVALENTS.get(item, ()):
            alias_text = _cell(None if source_row is None else source_row.get(alias))
            if alias_text:
                return (
                    "PRESENT_WITH_DIFFERENT_NAME",
                    f"source_table_field={alias}",
                )
        if item in SHARED_HELPER_FIELDS:
            return "DERIVABLE_FROM_SHARED_HELPER", "field belongs to shared rolling5 helper/upstream payload"
        return "PRESENT_IN_REPORTS_ONLY", "seen only in reports decision rows"

    if not reports_obs["present"] and enrichment_obs["present"]:
        if _cell(reports_obs["source_name"]) != _cell(enrichment_obs["source_name"]):
            return (
                "PRESENT_WITH_DIFFERENT_NAME",
                f"enrichment_source={enrichment_obs['source_name']}",
            )
        if _cell(reports_obs["horizon"]) != _cell(enrichment_obs["horizon"]):
            return (
                "PRESENT_WITH_DIFFERENT_HORIZON",
                f"enrichment_horizon={enrichment_obs['horizon']}",
            )
    return "NOT_FOUND", "no attribution found"


def _presence_counts(
    *,
    selected: list[tuple[str, str]],
    reports_rows_by_ticker: dict[str, list[DatacenterDashboardRow]],
    enrichment_rows_by_ticker: dict[str, list[DatacenterDashboardRow]],
    enrichment_table_by_ticker: dict[str, dict[str, object]],
    source_by_ticker: dict[str, dict[str, object]],
    item: str,
    is_token: bool,
) -> tuple[int, int, int, int, int]:
    reports_present = 0
    enrichment_present = 0
    reports_only = 0
    enrichment_only = 0
    different_value = 0
    for ticker, _reason in selected:
        reports_obs = _observation(reports_rows_by_ticker.get(ticker, []), item, is_token=is_token)
        enrichment_obs = _observation(enrichment_rows_by_ticker.get(ticker, []), item, is_token=is_token)
        if reports_obs["present"]:
            reports_present += 1
        if enrichment_obs["present"]:
            enrichment_present += 1
        if reports_obs["present"] and not enrichment_obs["present"]:
            reports_only += 1
        if enrichment_obs["present"] and not reports_obs["present"]:
            enrichment_only += 1
        if reports_obs["present"] and enrichment_obs["present"] and _cell(reports_obs["value"]) != _cell(enrichment_obs["value"]):
            different_value += 1
    return reports_present, enrichment_present, reports_only, enrichment_only, different_value


def _mismatch_counts(
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


def _availability_class(
    *,
    reports_any: bool,
    adapter_any: bool,
    enrichment_table_any: bool,
    source_table_any: bool,
    helper_any: bool,
) -> str:
    if reports_any and adapter_any and enrichment_table_any and source_table_any:
        return "AVAILABLE_ALL"
    if reports_any and not adapter_any and enrichment_table_any:
        return "ADAPTER_MISSING"
    if reports_any and not adapter_any and not enrichment_table_any and source_table_any:
        return "SOURCE_ONLY"
    if reports_any and not adapter_any and not enrichment_table_any and not source_table_any and helper_any:
        return "DERIVABLE"
    if reports_any and not adapter_any and not enrichment_table_any and not source_table_any:
        return "REPORTS_ONLY"
    if not reports_any and adapter_any and enrichment_table_any and not source_table_any:
        return "ENRICHMENT_TABLE_ONLY"
    return "NOT_FOUND"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit canonical decision-input gaps between reports-mode and enrichment-mode "
            "for pullback/readiness/candidate-priority mismatches."
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
        reports_rows, _warnings = _load_reports_rows(
            reports_dir=args.reports_dir,
            report_date=args.report_date,
        )
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        enrichment_table_rows = load_ticker_enrichment_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
        )
        source_by_ticker = _load_source_rows(args.analysis_db, args.report_date, taxonomy_version)
    except Exception as exc:  # pragma: no cover
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    enrichment_adapter_rows = build_dashboard_rows_from_ticker_enrichment_rows(enrichment_table_rows)
    reports_rows_by_ticker = _group_rows_by_ticker(reports_rows)
    enrichment_rows_by_ticker = _group_rows_by_ticker(enrichment_adapter_rows)
    reports_snapshot_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
    enrichment_snapshot_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
    enrichment_table_by_ticker = {str(row.get("ticker", "")).upper(): row for row in enrichment_table_rows if _cell(row.get("ticker"))}

    explicit_tickers = _parse_tickers(args.tickers)
    selected = _selected_tickers(
        reports_by_ticker=reports_snapshot_by_ticker,
        enrichment_by_ticker=enrichment_snapshot_by_ticker,
        explicit_tickers=explicit_tickers,
        max_examples=args.max_examples,
    )

    mismatch_specs = (
        ("pullback_validity", PULLBACK_DEFAULT),
        ("entry_readiness", ENTRY_DEFAULT),
        ("candidate_priority_label", CANDIDATE_LABEL_DEFAULT),
    )
    mismatch_counts: dict[str, tuple[int, int, int, int]] = {}

    _print_section("run_summary")
    _print_row("run_summary", "side", "path_or_db", "run_id", "report_date", "source")
    _print_row("run_summary", "reports_dir", args.reports_dir, args.reports_run_id, args.report_date, "reports_parse")
    _print_row("run_summary", "reports_dashboard", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "enrichment_dashboard", args.enrichment_dashboard_db, args.enrichment_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "analysis", args.analysis_db, taxonomy_version, args.report_date, "analysis_enrichment")

    _print_section("mismatch_summary")
    _print_row("mismatch_summary", "field_name", "matched", "different", "missing_reports", "missing_enrichment")
    for field_name, default in mismatch_specs:
        counts = _mismatch_counts(
            reports_snapshot_by_ticker,
            enrichment_snapshot_by_ticker,
            field_name,
            default,
        )
        mismatch_counts[field_name] = counts
        _print_row("mismatch_summary", field_name, *counts)

    _print_section("canonical_field_gap_counts")
    _print_row(
        "canonical_field_gap_counts",
        "field_name",
        "reports_present_count",
        "enrichment_present_count",
        "reports_only_count",
        "enrichment_only_count",
        "different_value_count",
    )
    field_gap_counts: dict[str, tuple[int, int, int, int, int]] = {}
    for field_name in FIELD_ITEMS:
        counts = _presence_counts(
            selected=selected,
            reports_rows_by_ticker=reports_rows_by_ticker,
            enrichment_rows_by_ticker=enrichment_rows_by_ticker,
            enrichment_table_by_ticker=enrichment_table_by_ticker,
            source_by_ticker=source_by_ticker,
            item=field_name,
            is_token=False,
        )
        field_gap_counts[field_name] = counts
        _print_row("canonical_field_gap_counts", field_name, *counts)

    _print_section("token_gap_counts")
    _print_row(
        "token_gap_counts",
        "token",
        "reports_present_count",
        "enrichment_present_count",
        "reports_only_count",
        "enrichment_only_count",
    )
    token_gap_counts: dict[str, tuple[int, int, int, int, int]] = {}
    for token in TOKEN_ITEMS:
        counts = _presence_counts(
            selected=selected,
            reports_rows_by_ticker=reports_rows_by_ticker,
            enrichment_rows_by_ticker=enrichment_rows_by_ticker,
            enrichment_table_by_ticker=enrichment_table_by_ticker,
            source_by_ticker=source_by_ticker,
            item=token,
            is_token=True,
        )
        token_gap_counts[token] = counts
        _print_row("token_gap_counts", token, counts[0], counts[1], counts[2], counts[3])

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

    gap_counter: Counter[tuple[str, str, str]] = Counter()
    gap_examples: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)

    _print_section("per_ticker_gap_attribution")
    _print_row(
        "per_ticker_gap_attribution",
        "ticker",
        "gap_type",
        "field_or_token",
        "reports_value",
        "enrichment_value",
        "attribution",
        "evidence",
    )
    for ticker, _selection_reason in selected:
        reports_input_rows = reports_rows_by_ticker.get(ticker, [])
        enrichment_input_rows = enrichment_rows_by_ticker.get(ticker, [])
        enrichment_table_row = enrichment_table_by_ticker.get(ticker)
        source_row = source_by_ticker.get(ticker)
        for field_name in FIELD_ITEMS:
            reports_obs = _observation(reports_input_rows, field_name, is_token=False)
            enrichment_obs = _observation(enrichment_input_rows, field_name, is_token=False)
            if not reports_obs["present"] and not enrichment_obs["present"]:
                continue
            gap_type = ""
            if reports_obs["present"] and not enrichment_obs["present"]:
                gap_type = "MISSING_FIELD"
            elif enrichment_obs["present"] and not reports_obs["present"]:
                gap_type = "MISSING_FIELD"
            elif _cell(reports_obs["source_name"]) != _cell(enrichment_obs["source_name"]):
                gap_type = "DIFFERENT_FIELD_NAME"
            elif _cell(reports_obs["horizon"]) != _cell(enrichment_obs["horizon"]):
                gap_type = "DIFFERENT_HORIZON"
            elif _cell(reports_obs["value"]) != _cell(enrichment_obs["value"]):
                gap_type = "DIFFERENT_VALUE"
            if not gap_type:
                continue
            attribution, evidence = _infer_attribution(
                item=field_name,
                is_token=False,
                reports_obs=reports_obs,
                enrichment_obs=enrichment_obs,
                enrichment_table_row=enrichment_table_row,
                source_row=source_row,
            )
            _print_row(
                "per_ticker_gap_attribution",
                ticker,
                gap_type,
                field_name,
                reports_obs["value"],
                enrichment_obs["value"],
                attribution,
                evidence,
            )
            key = (field_name, attribution, FIX_TYPE_BY_ATTRIBUTION.get(attribution, "UNKNOWN"))
            gap_counter[key] += 1
            if ticker not in gap_examples[key]:
                gap_examples[key].append(ticker)
        for token in TOKEN_ITEMS:
            reports_obs = _observation(reports_input_rows, token, is_token=True)
            enrichment_obs = _observation(enrichment_input_rows, token, is_token=True)
            if not reports_obs["present"] and not enrichment_obs["present"]:
                continue
            gap_type = ""
            if reports_obs["present"] and not enrichment_obs["present"]:
                gap_type = "MISSING_TOKEN"
            elif enrichment_obs["present"] and not reports_obs["present"]:
                gap_type = "MISSING_TOKEN"
            elif _cell(reports_obs["source_name"]) != _cell(enrichment_obs["source_name"]):
                gap_type = "DIFFERENT_FIELD_NAME"
            elif _cell(reports_obs["horizon"]) != _cell(enrichment_obs["horizon"]):
                gap_type = "DIFFERENT_HORIZON"
            elif _cell(reports_obs["value"]) != _cell(enrichment_obs["value"]):
                gap_type = "DIFFERENT_VALUE"
            if not gap_type:
                continue
            attribution, evidence = _infer_attribution(
                item=token,
                is_token=True,
                reports_obs=reports_obs,
                enrichment_obs=enrichment_obs,
                enrichment_table_row=enrichment_table_row,
                source_row=source_row,
            )
            _print_row(
                "per_ticker_gap_attribution",
                ticker,
                gap_type,
                token,
                reports_obs["value"],
                enrichment_obs["value"],
                attribution,
                evidence,
            )
            key = (token, attribution, FIX_TYPE_BY_ATTRIBUTION.get(attribution, "UNKNOWN"))
            gap_counter[key] += 1
            if ticker not in gap_examples[key]:
                gap_examples[key].append(ticker)

    _print_section("source_availability_matrix")
    _print_row(
        "source_availability_matrix",
        "field_or_token",
        "reports_rows",
        "enrichment_adapter_rows",
        "enrichment_table",
        "source_table",
        "shared_helper_or_upstream",
        "availability_class",
    )
    for item, is_token in [*( (name, False) for name in FIELD_ITEMS), *((name, True) for name in TOKEN_ITEMS)]:
        reports_any = False
        adapter_any = False
        enrichment_table_any = False
        source_any = False
        helper_any = item in SHARED_HELPER_FIELDS or item in {
            "pullback_candidate",
            "early_pullback",
            "failed_pullback",
            "short_term_breakdown",
            "no_pullback",
            "bos_down",
            "double_bos_down",
            "reset",
        }
        for ticker, _reason in selected:
            if _observation(reports_rows_by_ticker.get(ticker, []), item, is_token=is_token)["present"]:
                reports_any = True
            if _observation(enrichment_rows_by_ticker.get(ticker, []), item, is_token=is_token)["present"]:
                adapter_any = True
            if is_token:
                present, _source_name = _mapping_has_token(enrichment_table_by_ticker.get(ticker), item)
                enrichment_table_any = enrichment_table_any or present
                present, _source_name = _mapping_has_token(source_by_ticker.get(ticker), item)
                source_any = source_any or present
            else:
                enrichment_table_any = enrichment_table_any or bool(_value_from_mapping(enrichment_table_by_ticker.get(ticker), item))
                source_any = source_any or bool(_value_from_mapping(source_by_ticker.get(ticker), item))
        availability = _availability_class(
            reports_any=reports_any,
            adapter_any=adapter_any,
            enrichment_table_any=enrichment_table_any,
            source_table_any=source_any,
            helper_any=helper_any,
        )
        _print_row(
            "source_availability_matrix",
            item,
            int(reports_any),
            int(adapter_any),
            int(enrichment_table_any),
            int(source_any),
            int(helper_any),
            availability,
        )

    ranked_gaps = sorted(
        gap_counter.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1], item[0][2]),
    )
    top_gap = ""
    top_gap_attribution = ""
    recommended_fix_type = "UNKNOWN"
    if ranked_gaps:
        top_gap, top_gap_attribution, recommended_fix_type = ranked_gaps[0][0]

    _print_section("top_explanatory_gaps")
    _print_row(
        "top_explanatory_gaps",
        "rank",
        "field_or_token",
        "mismatch_count",
        "primary_attribution",
        "example_tickers",
        "recommended_fix_type",
    )
    for rank, (gap_key, mismatch_count) in enumerate(ranked_gaps[:10], start=1):
        field_or_token, attribution, fix_type = gap_key
        examples = ",".join(gap_examples[gap_key][:5])
        _print_row(
            "top_explanatory_gaps",
            rank,
            field_or_token,
            mismatch_count,
            attribution,
            examples,
            fix_type,
        )

    fix_type_counts: Counter[str] = Counter()
    for (field_or_token, attribution, fix_type), mismatch_count in ranked_gaps[:10]:
        fix_type_counts[fix_type] += mismatch_count
    majority_fix_type = ""
    majority_fix_count = 0
    if fix_type_counts:
        majority_fix_type, majority_fix_count = max(
            fix_type_counts.items(),
            key=lambda item: (item[1], item[0]),
        )
    total_top_counts = sum(fix_type_counts.values())
    safe_next_fix_identified = int(total_top_counts > 0 and majority_fix_count * 2 > total_top_counts)
    factual_parity_blocker_confirmed = int(mismatch_counts["pullback_validity"][1] > 0)

    hypotheses = [
        (
            "ADAPTER_EXPOSURE_FIX_SUFFICIENT",
            "LIKELY" if top_gap_attribution in {
                "PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER",
                "PRESENT_WITH_DIFFERENT_NAME",
                "PRESENT_WITH_DIFFERENT_HORIZON",
            } else "UNLIKELY",
            f"top_gap_attribution={top_gap_attribution}",
        ),
        (
            "ENRICHMENT_WRITER_MAPPING_REQUIRED",
            "LIKELY" if top_gap_attribution == "PRESENT_IN_SOURCE_NOT_ENRICHMENT" else "UNLIKELY",
            f"top_gap_attribution={top_gap_attribution}",
        ),
        (
            "SHARED_HELPER_PAYLOAD_INCOMPLETE",
            "LIKELY" if top_gap_attribution == "DERIVABLE_FROM_SHARED_HELPER" else "UNLIKELY",
            f"top_gap_attribution={top_gap_attribution}",
        ),
        (
            "REPORTS_ONLY_SEMANTIC_REMAINS",
            "LIKELY" if top_gap_attribution == "PRESENT_IN_REPORTS_ONLY" else "UNLIKELY",
            f"top_gap_attribution={top_gap_attribution}",
        ),
        (
            "FACTUAL_PARITY_BLOCKER_CONFIRMED",
            "LIKELY" if factual_parity_blocker_confirmed else "UNLIKELY",
            f"pullback_validity_differences={mismatch_counts['pullback_validity'][1]}",
        ),
        (
            "SAFE_NEXT_FIX_IDENTIFIED",
            "LIKELY" if safe_next_fix_identified else "UNLIKELY",
            f"majority_fix_type={majority_fix_type}, majority_fix_count={majority_fix_count}, total_top_counts={total_top_counts}",
        ),
    ]
    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    for hypothesis, status, evidence in hypotheses:
        _print_row("hypothesis_summary", hypothesis, status, evidence)

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.status=OK")
    print(f"SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.selected_tickers={len(selected)}")
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.pullback_validity_differences="
        f"{mismatch_counts['pullback_validity'][1]}"
    )
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.entry_readiness_differences="
        f"{mismatch_counts['entry_readiness'][1]}"
    )
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.candidate_priority_label_differences="
        f"{mismatch_counts['candidate_priority_label'][1]}"
    )
    print(f"SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.top_gap={top_gap}")
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.top_gap_attribution="
        f"{top_gap_attribution}"
    )
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.recommended_fix_type="
        f"{recommended_fix_type}"
    )
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.factual_parity_blocker_confirmed="
        f"{factual_parity_blocker_confirmed}"
    )
    print(
        "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.safe_next_fix_identified="
        f"{safe_next_fix_identified}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
