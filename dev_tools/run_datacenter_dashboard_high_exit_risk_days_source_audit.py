from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

GAP_GROUPS = (
    "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL",
    "REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE",
    "REPORTS_REDUCE_ENRICHMENT_NEUTRAL",
    "REPORTS_SELL_ENRICHMENT_REDUCE",
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


def _normalized_action(value: object) -> str:
    return _cell(value).upper()


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
    return None


def _load_enrichment_rows(
    analysis_db: str,
    report_date: str,
) -> dict[str, dict[str, object]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, "dc_dashboard_ticker_enrichment_daily")
        rows = conn.execute(
            """
            SELECT *
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ?
            ORDER BY ticker ASC
            """,
            (report_date,),
        ).fetchall()
        by_ticker: dict[str, dict[str, object]] = {}
        for row in rows:
            ticker = _cell(row["ticker"]).upper()
            if ticker and ticker not in by_ticker:
                by_ticker[ticker] = {key: row[key] for key in row.keys()}
        return by_ticker


def _load_source_history(
    analysis_db: str,
    report_date: str,
    tickers: list[str],
    window_days: int,
) -> dict[str, list[dict[str, object]]]:
    if not tickers:
        return {}
    placeholders = ", ".join("?" for _ in tickers)
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, "dc_ticker_swing_signal_daily")
        rows = conn.execute(
            f"""
            SELECT *
            FROM dc_ticker_swing_signal_daily
            WHERE ticker IN ({placeholders})
              AND signal_date <= ?
            ORDER BY ticker ASC, signal_date DESC
            """,
            (*tickers, report_date),
        ).fetchall()
        grouped_desc: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            ticker = _cell(row["ticker"]).upper()
            if len(grouped_desc[ticker]) >= window_days:
                continue
            grouped_desc[ticker].append({key: row[key] for key in row.keys()})
        return {
            ticker: list(reversed(ticker_rows))
            for ticker, ticker_rows in grouped_desc.items()
        }


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
    for gap_group_name in GAP_GROUPS:
        matches = []
        for ticker in common_tickers:
            if ticker == "CRGY":
                continue
            current_gap = _gap_group(
                reports_by_ticker[ticker].get("action"),
                enrichment_by_ticker[ticker].get("action"),
            )
            if current_gap == gap_group_name:
                matches.append((ticker, gap_group_name))
        selected.extend(matches[:max_examples])
    return selected[:max_examples]


def _safe_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = _cell(value)
        if text:
            return text
    return ""


def _find_reports_high_exit_trace(trace_rows: list[dict[str, object]]) -> dict[str, object] | None:
    for row in trace_rows:
        token = _first_non_empty(
            row.get("matched_token"),
            row.get("matched_value"),
            row.get("input_value"),
        )
        field_name = _first_non_empty(
            row.get("matched_field"),
            row.get("field_name"),
            row.get("field"),
        )
        rule_name = _first_non_empty(row.get("matched_rule"), row.get("rule_name"))
        if (
            token == "high_exit_risk_days_count>=1"
            or field_name == "high_exit_risk_days_count"
            or (rule_name == "TIGHTEN_STOP" and "high_exit_risk" in token)
        ):
            return row
    return None


def _reports_trace_high_exit_count(trace_row: dict[str, object] | None) -> int:
    if trace_row is None:
        return 0
    matched_value = _safe_int(trace_row.get("matched_value"))
    if matched_value is not None:
        return matched_value
    return 1


def _derive_counts(source_rows: list[dict[str, object]]) -> dict[str, int]:
    return {
        "derived_high_exit_days": sum(
            1 for row in source_rows if _cell(row.get("exit_risk_severity")).upper() == "HIGH"
        ),
        "derived_medium_or_high_exit_days": sum(
            1
            for row in source_rows
            if _cell(row.get("exit_risk_severity")).upper() in {"HIGH", "MEDIUM"}
        ),
        "derived_exit_signal_days": sum(
            1 for row in source_rows if _safe_int(row.get("exit_risk_signal")) == 1
        ),
        "latest_day_high_exit": (
            1
            if source_rows
            and _cell(source_rows[-1].get("exit_risk_severity")).upper() == "HIGH"
            else 0
        ),
        "latest_day_exit_signal": (
            1
            if source_rows and _safe_int(source_rows[-1].get("exit_risk_signal")) == 1
            else 0
        ),
        "source_rows_in_window": len(source_rows),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit where reports-mode high_exit_risk_days_count likely comes from."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--window-days", type=int, default=30)
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
        enrichment_by_ticker_analysis = _load_enrichment_rows(args.analysis_db, args.report_date)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _ticker_map(enrichment_snapshot.tickers)
    common_tickers = sorted(
        ticker
        for ticker in set(reports_by_ticker) & set(enrichment_by_ticker)
        if ticker != "CRGY"
    )
    selected = _select_tickers(
        common_tickers=common_tickers,
        reports_by_ticker=reports_by_ticker,
        enrichment_by_ticker=enrichment_by_ticker,
        explicit_tickers=_parse_tickers(args.tickers),
        max_examples=args.max_examples,
    )
    selected_tickers = [ticker for ticker, _gap_group_name in selected]

    try:
        source_history_by_ticker = _load_source_history(
            args.analysis_db,
            args.report_date,
            selected_tickers,
            args.window_days,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_trace_by_ticker: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trace in reports_snapshot.decision_trace:
        ticker = _cell(trace.get("ticker")).upper()
        if ticker:
            reports_trace_by_ticker[ticker].append(trace)

    tighten_gap_tickers = 0
    reports_high_exit_trace_found = 0
    derived_high_exit_present = 0
    latest_day_high_exit_present = 0
    no_analysis_source_match = 0
    trace_found_and_high_present = 0
    current_day_too_weak_count = 0
    exit_signal_better_match = 0
    medium_or_high_better_match = 0

    _print_section("run_summary")
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
        "analysis",
        args.analysis_db,
        "",
        args.report_date,
        "analysis_db",
    )

    _print_section("selected_tickers")
    _print_row("selected_tickers", "ticker", "reports_action", "enrichment_action", "gap_group")
    for ticker, gap_group_name in selected:
        _print_row(
            "selected_tickers",
            ticker,
            reports_by_ticker.get(ticker, {}).get("action"),
            enrichment_by_ticker.get(ticker, {}).get("action"),
            gap_group_name,
        )

    _print_section("derived_exit_counts")
    _print_row(
        "derived_exit_counts",
        "ticker",
        "reports_action",
        "enrichment_action",
        "reports_trace_high_exit_count",
        "enrichment_high_exit_count",
        "derived_high_exit_days",
        "derived_medium_or_high_exit_days",
        "derived_exit_signal_days",
        "latest_day_high_exit",
        "latest_day_exit_signal",
        "source_rows_in_window",
    )

    _print_section("reports_trace_high_exit")
    _print_row(
        "reports_trace_high_exit",
        "ticker",
        "trace_match_found",
        "matched_value",
        "matched_rule",
        "matched_token",
        "matched_field",
        "matched_horizon",
    )

    _print_section("source_history_examples")
    _print_row(
        "source_history_examples",
        "ticker",
        "signal_date",
        "exit_risk_signal",
        "exit_risk_severity",
        "exit_reason",
        "latest_bos_event_type",
        "latest_reset_reason",
    )

    source_history_example_rows = 0
    per_ticker_metrics: list[dict[str, object]] = []

    for ticker, gap_group_name in selected:
        reports_row = reports_by_ticker.get(ticker, {})
        enrichment_row = enrichment_by_ticker.get(ticker, {})
        analysis_row = enrichment_by_ticker_analysis.get(ticker, {})
        source_rows = source_history_by_ticker.get(ticker, [])
        derived = _derive_counts(source_rows)
        trace_row = _find_reports_high_exit_trace(reports_trace_by_ticker.get(ticker, []))
        reports_trace_count = _reports_trace_high_exit_count(trace_row)
        enrichment_high_exit_count = _safe_int(analysis_row.get("high_exit_risk_days_count")) or 0

        if gap_group_name in {
            "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL",
            "REPORTS_TIGHTEN_STOP_ENRICHMENT_REDUCE",
        }:
            tighten_gap_tickers += 1
            if reports_trace_count >= 1:
                reports_high_exit_trace_found += 1
            if derived["derived_high_exit_days"] >= 1:
                derived_high_exit_present += 1
            if derived["latest_day_high_exit"] >= 1:
                latest_day_high_exit_present += 1
            if (
                reports_trace_count >= 1
                and derived["derived_high_exit_days"] >= 1
            ):
                trace_found_and_high_present += 1
            if (
                reports_trace_count >= 1
                and derived["latest_day_high_exit"] == 0
                and derived["derived_high_exit_days"] >= 1
            ):
                current_day_too_weak_count += 1
            if reports_trace_count >= 1 and derived["derived_exit_signal_days"] >= 1:
                exit_signal_better_match += 1
            if reports_trace_count >= 1 and derived["derived_medium_or_high_exit_days"] >= 1:
                medium_or_high_better_match += 1
            if (
                reports_trace_count >= 1
                and derived["derived_high_exit_days"] == 0
                and derived["derived_medium_or_high_exit_days"] == 0
                and derived["derived_exit_signal_days"] == 0
            ):
                no_analysis_source_match += 1

        _print_row(
            "derived_exit_counts",
            ticker,
            reports_row.get("action"),
            enrichment_row.get("action"),
            reports_trace_count,
            enrichment_high_exit_count,
            derived["derived_high_exit_days"],
            derived["derived_medium_or_high_exit_days"],
            derived["derived_exit_signal_days"],
            derived["latest_day_high_exit"],
            derived["latest_day_exit_signal"],
            derived["source_rows_in_window"],
        )
        _print_row(
            "reports_trace_high_exit",
            ticker,
            1 if trace_row is not None else 0,
            reports_trace_count,
            _first_non_empty(trace_row.get("matched_rule") if trace_row else None, trace_row.get("rule_name") if trace_row else None),
            _first_non_empty(
                trace_row.get("matched_token") if trace_row else None,
                trace_row.get("matched_value") if trace_row else None,
                trace_row.get("input_value") if trace_row else None,
            ),
            _first_non_empty(trace_row.get("matched_field") if trace_row else None, trace_row.get("field_name") if trace_row else None, trace_row.get("field") if trace_row else None),
            _first_non_empty(trace_row.get("matched_horizon") if trace_row else None, trace_row.get("rule_group") if trace_row else None, trace_row.get("horizon") if trace_row else None),
        )
        for source_row in source_rows:
            if source_history_example_rows >= args.max_examples:
                break
            if (
                _safe_int(source_row.get("exit_risk_signal")) == 1
                or _cell(source_row.get("exit_risk_severity")) != ""
            ):
                source_history_example_rows += 1
                _print_row(
                    "source_history_examples",
                    ticker,
                    source_row.get("signal_date"),
                    source_row.get("exit_risk_signal"),
                    source_row.get("exit_risk_severity"),
                    source_row.get("exit_reason"),
                    source_row.get("latest_bos_event_type"),
                    source_row.get("latest_reset_reason"),
                )
        per_ticker_metrics.append(
            {
                "ticker": ticker,
                "gap_group": gap_group_name,
                "reports_trace_count": reports_trace_count,
                "derived": derived,
            }
        )

    reports_high_exit_window_likely = (
        tighten_gap_tickers > 0
        and reports_high_exit_trace_found > 0
        and trace_found_and_high_present * 2 >= reports_high_exit_trace_found
    )
    current_day_derivation_too_weak = (
        reports_high_exit_trace_found > 0
        and current_day_too_weak_count * 2 >= reports_high_exit_trace_found
    )
    exit_signal_count_better_match = (
        reports_high_exit_trace_found > 0
        and exit_signal_better_match > trace_found_and_high_present
    )
    medium_or_high_count_better = (
        reports_high_exit_trace_found > 0
        and medium_or_high_better_match > trace_found_and_high_present
    )
    no_analysis_source = (
        reports_high_exit_trace_found > 0
        and no_analysis_source_match * 2 >= reports_high_exit_trace_found
    )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "REPORTS_HIGH_EXIT_IS_WINDOW_COUNT",
        "LIKELY" if reports_high_exit_window_likely else "UNLIKELY",
        f"tighten_gap_tickers={tighten_gap_tickers},reports_trace_found={reports_high_exit_trace_found},derived_high_exit_present={trace_found_and_high_present}",
    )
    _print_row(
        "hypothesis_summary",
        "CURRENT_DAY_DERIVATION_TOO_WEAK",
        "LIKELY" if current_day_derivation_too_weak else "UNLIKELY",
        f"reports_trace_found={reports_high_exit_trace_found},latest_day_zero_but_window_high={current_day_too_weak_count}",
    )
    _print_row(
        "hypothesis_summary",
        "EXIT_RISK_SIGNAL_COUNT_BETTER_MATCH",
        "LIKELY" if exit_signal_count_better_match else "UNLIKELY",
        f"exit_signal_match={exit_signal_better_match},high_only_match={trace_found_and_high_present}",
    )
    _print_row(
        "hypothesis_summary",
        "MEDIUM_OR_HIGH_COUNT_BETTER_MATCH",
        "LIKELY" if medium_or_high_count_better else "UNLIKELY",
        f"medium_or_high_match={medium_or_high_better_match},high_only_match={trace_found_and_high_present}",
    )
    _print_row(
        "hypothesis_summary",
        "NO_ANALYSIS_SOURCE_FOR_REPORTS_HIGH_EXIT",
        "LIKELY" if no_analysis_source else "UNLIKELY",
        f"reports_trace_found={reports_high_exit_trace_found},all_derived_zero={no_analysis_source_match}",
    )

    _print_section("summary")
    _print_row("SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.status=OK")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.report_date={args.report_date}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.window_days={args.window_days}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.selected_tickers={len(selected)}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.tighten_stop_gap_tickers={tighten_gap_tickers}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.reports_high_exit_trace_found={reports_high_exit_trace_found}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.derived_high_exit_present={derived_high_exit_present}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.latest_day_high_exit_present={latest_day_high_exit_present}")
    _print_row(f"SUMMARY datacenter_dashboard_high_exit_risk_days_source_audit.no_analysis_source_match={no_analysis_source_match}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
