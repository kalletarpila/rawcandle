from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
)
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

GAP_GROUPS = (
    "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL",
    "REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE",
    "REPORTS_REDUCE_ENRICHMENT_NEUTRAL",
    "REPORTS_SELL_ENRICHMENT_REDUCE",
    "REPORTS_SELL_ENRICHMENT_NEUTRAL",
)

FIELD_NAMES = (
    "action",
    "severity",
    "primary_reason",
    "current_status",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "high_exit_risk_days_count",
    "ma_break_status",
    "freshness_status",
    "latest_bos_event_type",
    "latest_reset_reason",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
    "candidate_priority_label",
    "horizons_present",
)

RAW_FIELDS_SUMMARY_KEYS = (
    "current_status",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "high_exit_risk_days_count",
    "ma_break_status",
    "freshness_status",
    "latest_bos_event_type",
    "latest_reset_reason",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(_cell(item) for item in value)
    if isinstance(value, tuple):
        return "|".join(_cell(item) for item in value)
    if isinstance(value, dict):
        return "|".join(f"{key}={_cell(value[key])}" for key in sorted(value))
    return str(value).replace("\n", " ").replace(";", ",").strip()


def _print_section(name: str) -> None:
    print(f"section;{name}")


def _print_row(prefix: str, *columns: object) -> None:
    print(";".join([prefix, *(_cell(column) for column in columns)]))


def _normalized_action(value: object) -> str:
    return _cell(value).upper()


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(",", " ")
    selected: list[str] = []
    seen: set[str] = set()
    for token in normalized.split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            selected.append(ticker)
    return selected


def _connect_analysis_read_only(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise ValueError(f"analysis_db_copy not found: {path}")
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


def _load_analysis_rows(analysis_db_copy: str, report_date: str) -> dict[str, dict[str, object]]:
    with _connect_analysis_read_only(analysis_db_copy) as conn:
        _require_table(conn, "dc_dashboard_ticker_enrichment_daily")
        rows = conn.execute(
            """
            SELECT *
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ?
            ORDER BY ticker ASC, taxonomy_version ASC
            """,
            (report_date,),
        ).fetchall()
        by_ticker: dict[str, dict[str, object]] = {}
        for row in rows:
            ticker = _cell(row["ticker"]).upper()
            if ticker and ticker not in by_ticker:
                by_ticker[ticker] = {key: row[key] for key in row.keys()}
        return by_ticker


def _ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            result[ticker] = row
    return result


def _gap_group(reports_action: object, enrichment_action: object) -> str | None:
    reports = _normalized_action(reports_action)
    enrichment = _normalized_action(enrichment_action)
    if reports == "TIGHTEN_STOP" and enrichment == "NEUTRAL":
        return "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL"
    if reports == "TIGHTEN_STOP" and enrichment == "REDUCE":
        return "REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE"
    if reports == "REDUCE" and enrichment == "NEUTRAL":
        return "REPORTS_REDUCE_ENRICHMENT_NEUTRAL"
    if reports == "SELL" and enrichment == "REDUCE":
        return "REPORTS_SELL_ENRICHMENT_REDUCE"
    if reports == "SELL" and enrichment == "NEUTRAL":
        return "REPORTS_SELL_ENRICHMENT_NEUTRAL"
    return None


def _select_tickers(
    *,
    common_tickers: list[str],
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    if explicit_tickers:
        return [
            (
                ticker,
                _gap_group(
                    reports_by_ticker.get(ticker, {}).get("action"),
                    enrichment_by_ticker.get(ticker, {}).get("action"),
                )
                or "EXPLICIT_REQUEST",
            )
            for ticker in explicit_tickers
            if ticker in common_tickers and ticker != "CRGY"
        ]
    selected: list[tuple[str, str]] = []
    for gap_group in GAP_GROUPS:
        matches = []
        for ticker in common_tickers:
            if ticker == "CRGY":
                continue
            group = _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            if group == gap_group:
                matches.append((ticker, gap_group))
        selected.extend(matches[:max_examples])
    return selected[:max_examples]


def _raw_fields_summary(adapter_row) -> str:
    parts = []
    for key in RAW_FIELDS_SUMMARY_KEYS:
        value = adapter_row.raw_fields.get(key)
        if value not in {None, ""}:
            parts.append(f"{key}={value}")
    return "|".join(parts)


def _decision_by_ticker(adapter_result) -> dict[str, object]:
    return {decision.ticker: decision for decision in adapter_result.decisions}


def _trace_summary(trace_rows: list[dict[str, object]] | list[object]) -> tuple[str, str, str, str, str]:
    count = len(trace_rows)
    rules: list[str] = []
    tokens: list[str] = []
    fields: list[str] = []
    horizons: list[str] = []
    for trace in trace_rows[:5]:
        if isinstance(trace, dict):
            rules.append(_cell(trace.get("matched_rule") or trace.get("rule_name")))
            tokens.append(_cell(trace.get("matched_token") or trace.get("input_value")))
            fields.append(_cell(trace.get("field") or trace.get("field_name")))
            horizons.append(_cell(trace.get("horizon") or trace.get("rule_group")))
        else:
            rules.append(_cell(getattr(trace, "rule_name", None)))
            tokens.append(
                _cell(
                    getattr(trace, "matched_token", None)
                    or getattr(trace, "input_value", None)
                    or getattr(trace, "matched_value", None)
                )
            )
            fields.append(_cell(getattr(trace, "field_name", None)))
            horizons.append(_cell(getattr(trace, "horizon", None)))
    return str(count), "|".join(rules), "|".join(tokens), "|".join(fields), "|".join(horizons)


def _adapter_field_value(field_name: str, analysis_row: dict[str, object], adapter_rows: list[object], adapter_decision) -> object:
    if field_name in {
        "action",
        "severity",
        "primary_reason",
        "pullback_validity",
        "entry_readiness",
        "candidate_priority",
        "candidate_priority_label",
        "horizons_present",
    }:
        value = getattr(adapter_decision, field_name, None)
        if field_name == "horizons_present" and value is not None:
            return ",".join(value)
        return value
    if field_name in analysis_row:
        return analysis_row.get(field_name)
    for row in adapter_rows:
        value = row.raw_fields.get(field_name)
        if value not in {None, ""}:
            return value
    return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose TIGHTEN_STOP and REDUCE action parity gaps."
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db-copy", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument("--tickers")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        analysis_by_ticker = _load_analysis_rows(args.analysis_db_copy, args.report_date)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _ticker_map(reports.tickers)
    enrichment_by_ticker = _ticker_map(enrichment.tickers)
    common_tickers = sorted(
        ticker
        for ticker in (set(reports_by_ticker) & set(enrichment_by_ticker) & set(analysis_by_ticker))
        if ticker != "CRGY"
    )
    reports_trace_by_ticker: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in reports.decision_trace:
        reports_trace_by_ticker[_cell(row.get("ticker")).upper()].append(row)
    enrichment_trace_by_ticker: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in enrichment.decision_trace:
        enrichment_trace_by_ticker[_cell(row.get("ticker")).upper()].append(row)

    gap_counts = Counter(
        _gap_group(reports_by_ticker[ticker].get("action"), enrichment_by_ticker[ticker].get("action"))
        for ticker in common_tickers
    )
    gap_counts.pop(None, None)

    selected = _select_tickers(
        common_tickers=common_tickers,
        reports_by_ticker=reports_by_ticker,
        enrichment_by_ticker=enrichment_by_ticker,
        explicit_tickers=_parse_tickers(args.tickers),
        max_examples=args.max_examples,
    )

    adapter_rows_map: dict[str, list[object]] = {}
    adapter_decision_map: dict[str, object] = {}
    for ticker, _group in selected:
        analysis_row = analysis_by_ticker.get(ticker)
        if not analysis_row:
            continue
        adapter_rows = build_dashboard_rows_from_ticker_enrichment_rows([analysis_row])
        adapter_result = build_decisions_from_ticker_enrichment_rows([analysis_row])
        adapter_rows_map[ticker] = adapter_rows
        adapter_decision_map.update(_decision_by_ticker(adapter_result))

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row("run_summary", "reports", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "enrichment", args.enrichment_dashboard_db, args.enrichment_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "analysis_copy", args.analysis_db_copy, "", args.report_date, "analysis_enrichment_tables")

    _print_section("gap_group_counts")
    _print_row("gap_group_counts", "gap_group", "count")
    for gap_group in GAP_GROUPS:
        _print_row("gap_group_counts", gap_group, gap_counts.get(gap_group, 0))

    _print_section("selected_gap_tickers")
    _print_row(
        "selected_gap_tickers",
        "ticker",
        "gap_group",
        "reports_action",
        "enrichment_action",
        "reports_primary_reason",
        "enrichment_primary_reason",
    )
    for ticker, gap_group in selected:
        _print_row(
            "selected_gap_tickers",
            ticker,
            gap_group,
            reports_by_ticker.get(ticker, {}).get("action"),
            enrichment_by_ticker.get(ticker, {}).get("action"),
            reports_by_ticker.get(ticker, {}).get("primary_reason"),
            enrichment_by_ticker.get(ticker, {}).get("primary_reason"),
        )

    _print_section("field_comparison")
    _print_row(
        "field_comparison",
        "ticker",
        "field",
        "reports_value",
        "enrichment_snapshot_value",
        "analysis_value",
        "adapter_value",
    )
    for ticker, _selected_group in selected:
        analysis_row = analysis_by_ticker.get(ticker, {})
        adapter_rows = adapter_rows_map.get(ticker, [])
        adapter_decision = adapter_decision_map.get(ticker)
        for field_name in FIELD_NAMES:
            _print_row(
                "field_comparison",
                ticker,
                field_name,
                reports_by_ticker.get(ticker, {}).get(field_name),
                enrichment_by_ticker.get(ticker, {}).get(field_name),
                analysis_row.get(field_name),
                _adapter_field_value(field_name, analysis_row, adapter_rows, adapter_decision),
            )

    _print_section("adapter_row_inputs")
    _print_row(
        "adapter_row_inputs",
        "ticker",
        "row_index",
        "horizon",
        "raw_action",
        "raw_status",
        "ma_break_status",
        "freshness_status",
        "high_exit_risk_days_count",
        "latest_bos_event_type",
        "latest_reset_reason",
        "raw_fields_summary",
    )
    for ticker, _selected_group in selected:
        for index, row in enumerate(adapter_rows_map.get(ticker, []), start=1):
            _print_row(
                "adapter_row_inputs",
                ticker,
                index,
                row.horizon,
                row.raw_action,
                row.raw_status,
                row.ma_break_status,
                row.freshness_status,
                row.high_exit_risk_days_count,
                row.latest_bos_event_type,
                row.latest_reset_reason,
                _raw_fields_summary(row),
            )

    _print_section("decision_output_comparison")
    _print_row(
        "decision_output_comparison",
        "ticker",
        "reports_action",
        "enrichment_snapshot_action",
        "adapter_action",
        "reports_primary_reason",
        "enrichment_primary_reason",
        "adapter_primary_reason",
        "adapter_pullback_validity",
        "adapter_entry_readiness",
        "adapter_candidate_priority",
        "adapter_horizons_present",
    )
    for ticker, _selected_group in selected:
        adapter_decision = adapter_decision_map.get(ticker)
        _print_row(
            "decision_output_comparison",
            ticker,
            reports_by_ticker.get(ticker, {}).get("action"),
            enrichment_by_ticker.get(ticker, {}).get("action"),
            getattr(adapter_decision, "action", None),
            reports_by_ticker.get(ticker, {}).get("primary_reason"),
            enrichment_by_ticker.get(ticker, {}).get("primary_reason"),
            getattr(adapter_decision, "primary_reason", None),
            getattr(adapter_decision, "pullback_validity", None),
            getattr(adapter_decision, "entry_readiness", None),
            getattr(adapter_decision, "candidate_priority", None),
            ",".join(getattr(adapter_decision, "horizons_present", [])),
        )

    _print_section("decision_trace_comparison")
    _print_row(
        "decision_trace_comparison",
        "ticker",
        "source",
        "trace_count",
        "first_rules",
        "first_tokens",
        "first_fields",
        "first_horizons",
    )
    for ticker, _selected_group in selected:
        for source_name, trace_rows in (
            ("reports_snapshot", reports_trace_by_ticker.get(ticker, [])),
            ("enrichment_snapshot", enrichment_trace_by_ticker.get(ticker, [])),
            ("adapter_decision", list(getattr(adapter_decision_map.get(ticker), "decision_trace", []))),
        ):
            count, rules, tokens, fields, horizons = _trace_summary(trace_rows)
            _print_row(
                "decision_trace_comparison",
                ticker,
                source_name,
                count,
                rules,
                tokens,
                fields,
                horizons,
            )

    tighten_gap_tickers = [
        ticker for ticker, group in selected if group in {
            "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL",
            "REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE",
        }
    ]
    sell_reduce_gap_tickers = [ticker for ticker, group in selected if group == "REPORTS_SELL_ENRICHMENT_REDUCE"]
    tighten_with_visible_count = sum(
        1
        for ticker in tighten_gap_tickers
        if any(
            getattr(row, "high_exit_risk_days_count", None) not in {None, 0}
            for row in adapter_rows_map.get(ticker, [])
        )
    )
    tighten_adapter_tighten = sum(
        1
        for ticker in tighten_gap_tickers
        if _normalized_action(getattr(adapter_decision_map.get(ticker), "action", None)) == "TIGHTEN_STOP"
    )
    persisted_vs_adapter_diff = sum(
        1
        for ticker, _group in selected
        if _normalized_action(enrichment_by_ticker.get(ticker, {}).get("action"))
        != _normalized_action(getattr(adapter_decision_map.get(ticker), "action", None))
    )
    reports_high_exit_without_adapter = sum(
        1
        for ticker in tighten_gap_tickers
        if "HIGH_EXIT" in _normalized_action(reports_by_ticker.get(ticker, {}).get("primary_reason"))
        and not any(
            getattr(row, "high_exit_risk_days_count", None) not in {None, 0}
            for row in adapter_rows_map.get(ticker, [])
        )
    )
    sell_reduce_missing_ma_break = sum(
        1
        for ticker in sell_reduce_gap_tickers
        if not _cell(analysis_by_ticker.get(ticker, {}).get("ma_break_status"))
    )

    hypotheses = [
        (
            "HIGH_EXIT_COUNT_VISIBLE_TO_ADAPTER",
            "LIKELY" if tighten_gap_tickers and tighten_with_visible_count * 2 >= len(tighten_gap_tickers) else "UNLIKELY",
            f"tighten_gap_tickers={len(tighten_gap_tickers)};visible_high_exit_count={tighten_with_visible_count}",
        ),
        (
            "ADAPTER_RETURNS_TIGHTEN_STOP_WHEN_HIGH_EXIT_PRESENT",
            "LIKELY" if tighten_gap_tickers and tighten_adapter_tighten * 2 >= len(tighten_gap_tickers) else "UNLIKELY",
            f"tighten_gap_tickers={len(tighten_gap_tickers)};adapter_tighten_stop={tighten_adapter_tighten}",
        ),
        (
            "PERSISTED_ENRICHMENT_ACTION_DIFFERS_FROM_ADAPTER",
            "LIKELY" if persisted_vs_adapter_diff > 0 else "UNLIKELY",
            f"selected_tickers={len(selected)};persisted_adapter_action_diff={persisted_vs_adapter_diff}",
        ),
        (
            "REPORTS_TIGHTEN_STOP_USES_DIFFERENT_SIGNAL",
            "LIKELY" if reports_high_exit_without_adapter > 0 else "UNLIKELY",
            f"tighten_gap_tickers={len(tighten_gap_tickers)};reports_high_exit_without_adapter={reports_high_exit_without_adapter}",
        ),
        (
            "MA_BREAK_MISSING_EXPLAINS_SELL_REDUCE_GAPS",
            "LIKELY" if sell_reduce_gap_tickers and sell_reduce_missing_ma_break * 2 >= len(sell_reduce_gap_tickers) else "UNLIKELY",
            f"sell_reduce_gap_tickers={len(sell_reduce_gap_tickers)};missing_ma_break_status={sell_reduce_missing_ma_break}",
        ),
    ]

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    for hypothesis, status, evidence in hypotheses:
        _print_row("hypothesis_summary", hypothesis, status, evidence)

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.status=OK")
    print(f"SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.selected_tickers={len(selected)}")
    print(
        "SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.tighten_stop_to_neutral="
        f"{gap_counts.get('REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.tighten_stop_to_reduce="
        f"{gap_counts.get('REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.reduce_to_neutral="
        f"{gap_counts.get('REPORTS_REDUCE_ENRICHMENT_NEUTRAL', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.sell_to_reduce="
        f"{gap_counts.get('REPORTS_SELL_ENRICHMENT_REDUCE', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_tighten_reduce_gap_diagnosis.sell_to_neutral="
        f"{gap_counts.get('REPORTS_SELL_ENRICHMENT_NEUTRAL', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
