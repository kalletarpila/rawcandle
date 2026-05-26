from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
)
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
NON_NEUTRAL_ACTIONS = {"SELL", "REDUCE", "TIGHTEN_STOP"}
ROLLING_HORIZONS = {"rolling 2d", "rolling 5d", "rolling 30d"}
NEUTRAL_LIKE_TOKENS = {
    "",
    "NEUTRAL",
    "NEUTRAL_MONITOR",
    "NO_EMERGENCY",
    "READY",
    "OK",
    "INFO",
}
COMPARISON_FIELDS: tuple[str, ...] = (
    "action",
    "severity",
    "primary_reason",
    "current_status",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
    "candidate_priority_label",
    "horizons_present",
    "trend_state",
    "latest_structure_label",
    "latest_bos_event_type",
    "latest_reset_reason",
    "ma_break_status",
    "freshness_status",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
)
RAW_FIELDS_SUMMARY_KEYS: tuple[str, ...] = (
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "current_status",
    "action",
    "severity",
    "primary_reason",
    "ma_break_status",
    "freshness_status",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return "|".join(f"{key}={value[key]}" for key in sorted(value))
    return str(value).replace(";", ",").replace("\n", " ").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"analysis_db_copy not found: {db_path}")
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
    tickers = sorted({part.strip().upper() for part in normalized.split() if part.strip()})
    return tickers


def _load_analysis_rows(
    analysis_db_copy: str,
    report_date: str,
) -> tuple[dict[str, dict[str, object]], str | None]:
    with _connect_read_only(analysis_db_copy) as conn:
        if not _table_exists(conn, ENRICHMENT_TABLE):
            raise ValueError(f"missing required analysis table: {ENRICHMENT_TABLE}")
        rows = list(
            conn.execute(
                f"""
                SELECT *
                FROM {ENRICHMENT_TABLE}
                WHERE signal_date = ?
                ORDER BY taxonomy_version ASC, ticker ASC
                """,
                (report_date,),
            ).fetchall()
        )
    taxonomy_versions = sorted(
        {
            str(row["taxonomy_version"]).strip()
            for row in rows
            if row["taxonomy_version"] not in {None, ""}
        }
    )
    inferred_taxonomy = taxonomy_versions[0] if len(taxonomy_versions) == 1 else None
    ticker_map: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = str(row["ticker"]).strip().upper()
        if ticker and ticker not in ticker_map:
            ticker_map[ticker] = dict(row)
    return ticker_map, inferred_taxonomy


def _action_distribution(rows: list[dict[str, object]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        action = str(row.get("action") or "").strip().upper()
        if action:
            counts[action] += 1
    return counts


def _selection_reason_order(reason: str) -> tuple[int, str]:
    priority = {
        "REPORTS_SELL_ENRICHMENT_NEUTRAL": 0,
        "REPORTS_REDUCE_ENRICHMENT_NEUTRAL": 1,
        "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL": 2,
        "EXPLICIT_REQUEST": 3,
    }
    return (priority.get(reason, len(priority)), reason)


def _select_tickers(
    *,
    explicit_tickers: list[str],
    reports_tickers: dict[str, dict[str, object]],
    enrichment_tickers: dict[str, dict[str, object]],
    max_examples: int,
) -> list[tuple[str, str, str, str]]:
    if explicit_tickers:
        selected: list[tuple[str, str, str, str]] = []
        for ticker in explicit_tickers:
            reports_action = str(reports_tickers.get(ticker, {}).get("action") or "").strip()
            enrichment_action = str(
                enrichment_tickers.get(ticker, {}).get("action") or ""
            ).strip()
            selected.append((ticker, "EXPLICIT_REQUEST", reports_action, enrichment_action))
        return selected

    selected: list[tuple[str, str, str, str]] = []
    for reports_action in ("SELL", "REDUCE", "TIGHTEN_STOP"):
        reason = f"REPORTS_{reports_action}_ENRICHMENT_NEUTRAL"
        matching = []
        for ticker in sorted(set(reports_tickers) & set(enrichment_tickers)):
            if ticker == "CRGY":
                continue
            reports_value = str(reports_tickers[ticker].get("action") or "").strip().upper()
            enrichment_value = str(
                enrichment_tickers[ticker].get("action") or ""
            ).strip().upper()
            if reports_value == reports_action and enrichment_value == "NEUTRAL":
                matching.append((ticker, reason, reports_value, enrichment_value))
        selected.extend(matching[:max_examples])
    selected.sort(key=lambda item: (_selection_reason_order(item[1]), item[0]))
    return selected


def _compact_raw_fields_summary(row) -> str:
    pairs = []
    for key in RAW_FIELDS_SUMMARY_KEYS:
        value = row.raw_fields.get(key)
        if value not in {None, ""}:
            pairs.append(f"{key}={value}")
    return "|".join(pairs)


def _horizons_present_text(decision) -> str:
    return ",".join(decision.horizons_present)


def _bool_status(value: bool) -> str:
    return "LIKELY" if value else "UNLIKELY"


def _is_neutral_like(value: object) -> bool:
    normalized = str(value or "").strip().upper()
    return normalized in NEUTRAL_LIKE_TOKENS


def _has_missing_risk_fields(
    reports_action: str,
    analysis_row: dict[str, object] | None,
) -> bool:
    if reports_action not in NON_NEUTRAL_ACTIONS:
        return False
    if analysis_row is None:
        return True
    risk_keys = (
        "ma_break_status",
        "freshness_status",
        "high_exit_risk_days_count",
        "blocking_reasons",
        "ema20_break_confirmed",
        "sma50_break_confirmed",
        "close_below_ema20",
        "close_below_sma50",
        "consecutive_closes_below_ema20",
        "consecutive_closes_below_sma50",
        "ema20_break_pct",
        "sma50_break_pct",
    )
    for key in risk_keys:
        value = analysis_row.get(key)
        if value not in {None, "", 0, "0"}:
            return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose why enrichment ticker decisions collapse to NEUTRAL.",
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db-copy", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=25)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
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
        analysis_rows, inferred_taxonomy = _load_analysis_rows(
            args.analysis_db_copy,
            args.report_date,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_tickers = {str(row["ticker"]).strip().upper(): row for row in reports.tickers}
    enrichment_tickers = {
        str(row["ticker"]).strip().upper(): row for row in enrichment.tickers
    }
    explicit_tickers = _parse_tickers(args.tickers)
    selected_tickers = _select_tickers(
        explicit_tickers=explicit_tickers,
        reports_tickers=reports_tickers,
        enrichment_tickers=enrichment_tickers,
        max_examples=args.max_examples,
    )

    reports_action_counts = _action_distribution(reports.tickers)
    enrichment_action_counts = _action_distribution(enrichment.tickers)
    common_ticker_symbols = sorted(set(reports_tickers) & set(enrichment_tickers))
    reports_non_neutral_enrichment_neutral = [
        ticker
        for ticker in common_ticker_symbols
        if str(reports_tickers[ticker].get("action") or "").strip().upper()
        in NON_NEUTRAL_ACTIONS
        and str(enrichment_tickers[ticker].get("action") or "").strip().upper() == "NEUTRAL"
    ]

    adapter_rows_by_ticker: dict[str, list[object]] = {}
    adapter_decisions_by_ticker: dict[str, object] = {}
    missing_diagnosis_rows: list[tuple[str, str, str, str]] = []
    no_rolling_count = 0
    weak_raw_count = 0
    missing_risk_count = 0
    adapter_neutral_count = 0

    for ticker, _reason, _reports_action, _enrichment_action in selected_tickers:
        analysis_row = analysis_rows.get(ticker)
        if analysis_row is None:
            adapter_rows = []
            decisions = []
        else:
            adapter_rows = build_dashboard_rows_from_ticker_enrichment_rows([analysis_row])
            decisions = build_decisions_from_ticker_enrichment_rows([analysis_row]).decisions
        adapter_rows_by_ticker[ticker] = adapter_rows
        if decisions:
            adapter_decisions_by_ticker[ticker] = decisions[0]

        has_rolling = any(row.horizon in ROLLING_HORIZONS for row in adapter_rows)
        no_rolling = not has_rolling
        if no_rolling:
            no_rolling_count += 1
        missing_diagnosis_rows.append(
            (
                ticker,
                "NO_ROLLING_HORIZON_INPUTS",
                _bool_status(no_rolling),
                f"adapter_rows={len(adapter_rows)};rolling_rows={sum(1 for row in adapter_rows if row.horizon in ROLLING_HORIZONS)}",
            )
        )

        raw_tokens = []
        for row in adapter_rows:
            raw_tokens.extend([str(row.raw_action or "").strip().upper(), str(row.raw_status or "").strip().upper()])
        meaningful_tokens = [token for token in raw_tokens if token and token not in NEUTRAL_LIKE_TOKENS]
        weak_raw = len(meaningful_tokens) == 0
        if weak_raw:
            weak_raw_count += 1
        missing_diagnosis_rows.append(
            (
                ticker,
                "NO_RAW_ACTION_OR_STATUS_TOKENS",
                _bool_status(weak_raw),
                f"raw_tokens={'|'.join(token for token in raw_tokens if token)}",
            )
        )

        reports_action = str(reports_tickers.get(ticker, {}).get("action") or "").strip().upper()
        missing_risk = _has_missing_risk_fields(reports_action, analysis_row)
        if missing_risk:
            missing_risk_count += 1
        missing_diagnosis_rows.append(
            (
                ticker,
                "MISSING_MA_BREAK_OR_RISK_FIELDS",
                _bool_status(missing_risk),
                f"reports_action={reports_action};ma_break_status={_cell((analysis_row or {}).get('ma_break_status'))};freshness_status={_cell((analysis_row or {}).get('freshness_status'))}",
            )
        )

        adapter_action = str(
            getattr(adapter_decisions_by_ticker.get(ticker), "action", "") or ""
        ).strip().upper()
        adapter_neutral = adapter_action == "NEUTRAL"
        if adapter_neutral:
            adapter_neutral_count += 1
        missing_diagnosis_rows.append(
            (
                ticker,
                "DECISION_LOGIC_RETURNS_NEUTRAL_FROM_ADAPTER_INPUT",
                _bool_status(adapter_neutral),
                f"adapter_action={adapter_action}",
            )
        )

    selected_count = len(selected_tickers)
    threshold = selected_count / 2 if selected_count else 0
    hypothesis_missing_horizon = selected_count > 0 and no_rolling_count > threshold
    hypothesis_weak_raw = selected_count > 0 and weak_raw_count > threshold
    hypothesis_adapter_neutral = selected_count > 0 and adapter_neutral_count > threshold
    hypothesis_reports_signal_missing = selected_count > 0 and missing_risk_count > threshold

    _print_row("section", "run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
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
        args.analysis_db_copy,
        inferred_taxonomy or "",
        args.report_date,
        "analysis_enrichment_rows",
    )

    _print_row("section", "action_collapse_overview")
    _print_row("action_collapse_overview", "metric", "reports_value", "enrichment_value", "details")
    _print_row(
        "action_collapse_overview",
        "reports_distinct_actions",
        len(reports_action_counts),
        "",
        "|".join(f"{action}={reports_action_counts[action]}" for action in sorted(reports_action_counts)),
    )
    _print_row(
        "action_collapse_overview",
        "enrichment_distinct_actions",
        "",
        len(enrichment_action_counts),
        "|".join(
            f"{action}={enrichment_action_counts[action]}"
            for action in sorted(enrichment_action_counts)
        ),
    )
    _print_row(
        "action_collapse_overview",
        "reports_non_neutral_count",
        sum(count for action, count in reports_action_counts.items() if action in NON_NEUTRAL_ACTIONS),
        sum(count for action, count in enrichment_action_counts.items() if action in NON_NEUTRAL_ACTIONS),
        "",
    )
    _print_row(
        "action_collapse_overview",
        "enrichment_non_neutral_count",
        "",
        sum(count for action, count in enrichment_action_counts.items() if action in NON_NEUTRAL_ACTIONS),
        "",
    )
    _print_row(
        "action_collapse_overview",
        "common_tickers",
        len(common_ticker_symbols),
        len(common_ticker_symbols),
        "",
    )
    _print_row(
        "action_collapse_overview",
        "common_tickers_reports_non_neutral_enrichment_neutral",
        len(reports_non_neutral_enrichment_neutral),
        len(reports_non_neutral_enrichment_neutral),
        "",
    )

    _print_row("section", "selected_tickers")
    _print_row("selected_tickers", "ticker", "selection_reason", "reports_action", "enrichment_action")
    for ticker, reason, reports_action, enrichment_action in selected_tickers:
        _print_row("selected_tickers", ticker, reason, reports_action, enrichment_action)

    _print_row("section", "ticker_decision_comparison")
    _print_row("ticker_decision_comparison", "ticker", "field", "reports_value", "enrichment_value", "analysis_value")
    for ticker, _reason, _reports_action, _enrichment_action in selected_tickers:
        reports_row = reports_tickers.get(ticker, {})
        enrichment_row = enrichment_tickers.get(ticker, {})
        analysis_row = analysis_rows.get(ticker, {})
        for field_name in COMPARISON_FIELDS:
            _print_row(
                "ticker_decision_comparison",
                ticker,
                field_name,
                reports_row.get(field_name),
                enrichment_row.get(field_name),
                analysis_row.get(field_name),
            )

    _print_row("section", "adapter_input_rows")
    _print_row(
        "adapter_input_rows",
        "ticker",
        "adapter_row_index",
        "horizon",
        "raw_action",
        "raw_status",
        "reason",
        "trend_state",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_reset_reason",
        "ma_break_status",
        "freshness_status",
        "raw_fields_summary",
    )
    for ticker, _reason, _reports_action, _enrichment_action in selected_tickers:
        for index, row in enumerate(adapter_rows_by_ticker.get(ticker, []), start=1):
            _print_row(
                "adapter_input_rows",
                ticker,
                index,
                row.horizon,
                row.raw_action,
                row.raw_status,
                row.reason,
                row.trend_state,
                row.latest_structure_label,
                row.latest_bos_event_type,
                row.latest_reset_reason,
                row.ma_break_status,
                row.freshness_status,
                _compact_raw_fields_summary(row),
            )

    _print_row("section", "adapter_decision_output")
    _print_row(
        "adapter_decision_output",
        "ticker",
        "action",
        "severity",
        "primary_reason",
        "pullback_validity",
        "entry_readiness",
        "candidate_priority",
        "candidate_priority_label",
        "horizons_present",
        "decision_trace_count",
        "reasons",
        "blocking_reasons",
    )
    for ticker, _reason, _reports_action, _enrichment_action in selected_tickers:
        decision = adapter_decisions_by_ticker.get(ticker)
        _print_row(
            "adapter_decision_output",
            ticker,
            getattr(decision, "action", None),
            getattr(decision, "severity", None),
            getattr(decision, "primary_reason", None),
            getattr(decision, "pullback_validity", None),
            getattr(decision, "entry_readiness", None),
            getattr(decision, "candidate_priority", None),
            getattr(decision, "candidate_priority_label", None),
            _horizons_present_text(decision) if decision is not None else "",
            len(getattr(decision, "decision_trace", [])) if decision is not None else 0,
            "|".join(getattr(decision, "reasons", [])) if decision is not None else "",
            "|".join(getattr(decision, "blocking_reasons", [])) if decision is not None else "",
        )

    _print_row("section", "missing_signal_diagnosis")
    _print_row("missing_signal_diagnosis", "ticker", "diagnosis", "status", "evidence")
    for ticker, diagnosis, status, evidence in missing_diagnosis_rows:
        _print_row("missing_signal_diagnosis", ticker, diagnosis, status, evidence)

    _print_row("section", "hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "ACTION_COLLAPSE_CAUSED_BY_MISSING_HORIZON_STATUS",
        _bool_status(hypothesis_missing_horizon),
        f"selected={selected_count};no_rolling={no_rolling_count}",
    )
    _print_row(
        "hypothesis_summary",
        "ACTION_COLLAPSE_CAUSED_BY_WEAK_RAW_STATUS_MAPPING",
        _bool_status(hypothesis_weak_raw),
        f"selected={selected_count};weak_raw={weak_raw_count}",
    )
    _print_row(
        "hypothesis_summary",
        "ADAPTER_DECISION_MATCHES_ENRICHMENT_NEUTRAL",
        _bool_status(hypothesis_adapter_neutral),
        f"selected={selected_count};adapter_neutral={adapter_neutral_count}",
    )
    _print_row(
        "hypothesis_summary",
        "REPORTS_DECISION_SIGNAL_NOT_AVAILABLE_IN_ENRICHMENT_ROWS",
        _bool_status(hypothesis_reports_signal_missing),
        f"selected={selected_count};missing_risk_fields={missing_risk_count}",
    )

    _print_row("section", "summary")
    _print_row("SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.status=OK")
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.report_date={args.report_date}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.selected_tickers={selected_count}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.reports_non_neutral_enrichment_neutral="
        f"{len(reports_non_neutral_enrichment_neutral)}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.adapter_neutral_count={adapter_neutral_count}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.no_rolling_horizon_inputs={no_rolling_count}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.weak_raw_status_mapping={weak_raw_count}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_ticker_decision_collapse_diagnosis.missing_risk_fields={missing_risk_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
