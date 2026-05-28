from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
SOURCE_TABLE = "dc_ticker_swing_signal_daily"
REPORT_PULLBACK_PRIORITY = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
)
REQUIRED_SOURCE_COLUMNS = (
    "pullback_signal",
    "breakout_signal",
    "bullish_candle_signal",
    "bullish_divergence_signal",
    "hidden_bullish_divergence_signal",
    "latest_bos_event_type",
    "latest_reset_reason",
    "exit_risk_signal",
    "exit_risk_severity",
    "price_data_status",
    "distance_to_ema20_pct",
    "return_5d",
    "return_10d",
    "rolling_5d_status",
    "pullback_days",
    "latest_bullish_signal_age_td",
    "structure_warning_overrides_bullish_signal",
)
WINDOW_EXAMPLE_FIELDS = (
    "pullback_signal",
    "bullish_candle_signal",
    "bullish_divergence_signal",
    "hidden_bullish_divergence_signal",
    "latest_bos_event_type",
    "latest_reset_reason",
    "exit_risk_signal",
    "exit_risk_severity",
    "distance_to_ema20_pct",
    "return_5d",
    "return_10d",
)


@dataclass(frozen=True)
class CandidateEvaluation:
    ticker: str
    reports_pullback_validity: str
    candidate_rolling5_status: str
    candidate_pullback_days: int
    candidate_latest_bullish_signal_age_td: int | None
    candidate_structure_override: int
    candidate_reason: str


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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row["name"]) for row in rows]


def _normalized_text(value: object, default: str = "") -> str:
    text = _cell(value)
    return text or default


def _safe_int(value: object) -> int | None:
    text = _cell(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _bool_value(value: object) -> bool:
    return _safe_int(value) == 1


def _has_bullish_signal(row: dict[str, object]) -> bool:
    return any(
        _bool_value(row.get(field_name))
        for field_name in (
            "bullish_candle_signal",
            "bullish_divergence_signal",
            "hidden_bullish_divergence_signal",
        )
    )


def _has_structure_override(row: dict[str, object]) -> bool:
    if _bool_value(row.get("structure_warning_overrides_bullish_signal")):
        return True
    if _normalized_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN":
        return True
    latest_reset_reason = _normalized_text(row.get("latest_reset_reason")).upper()
    return "DOUBLE_BOS_DOWN" in latest_reset_reason


def _snapshot_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _normalized_text(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


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
    return _normalized_text(rows[0]["taxonomy_version"])


def _load_source_metadata(
    analysis_db: str,
) -> tuple[list[str], list[str]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, SOURCE_TABLE)
        columns = _table_columns(conn, SOURCE_TABLE)
    obvious_extra = sorted(
        column_name
        for column_name in columns
        if column_name not in REQUIRED_SOURCE_COLUMNS
        and ("rolling" in column_name or "pullback" in column_name)
    )
    return columns, obvious_extra


def _load_source_window_rows(
    analysis_db: str,
    report_date: str,
    taxonomy_version: str,
    tickers: list[str],
    lookback_rows: int,
) -> dict[str, list[dict[str, object]]]:
    if not tickers:
        return {}
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, SOURCE_TABLE)
        columns = set(_table_columns(conn, SOURCE_TABLE))
        has_taxonomy = "taxonomy_version" in columns
        result: dict[str, list[dict[str, object]]] = {}
        for ticker in tickers:
            params: list[object] = [ticker, report_date]
            sql = f"""
                SELECT *
                FROM {SOURCE_TABLE}
                WHERE ticker = ? AND signal_date <= ?
            """
            if has_taxonomy:
                sql += " AND taxonomy_version = ?"
                params.append(taxonomy_version)
            sql += """
                ORDER BY signal_date DESC
                LIMIT ?
            """
            params.append(lookback_rows)
            rows = conn.execute(sql, params).fetchall()
            result[ticker] = [
                {key: row[key] for key in row.keys()}
                for row in reversed(rows)
            ]
    return result


def _selected_tickers(
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[str]:
    common = set(reports_by_ticker) & set(enrichment_by_ticker)
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in common][:max_examples]

    weighted: list[tuple[int, str]] = []
    for ticker in sorted(common):
        reports_pullback = _normalized_text(
            reports_by_ticker[ticker].get("pullback_validity"),
            "INSUFFICIENT_DATA",
        )
        if reports_pullback not in REPORT_PULLBACK_PRIORITY:
            continue
        weighted.append((REPORT_PULLBACK_PRIORITY.index(reports_pullback), ticker))
    weighted.sort(key=lambda item: (item[0], item[1]))
    return [ticker for _priority, ticker in weighted[:max_examples]]


def _evaluate_candidate(
    ticker: str,
    reports_pullback_validity: str,
    window_rows: list[dict[str, object]],
) -> CandidateEvaluation:
    pullback_days = sum(1 for row in window_rows if _bool_value(row.get("pullback_signal")))
    bullish_indices = [index for index, row in enumerate(window_rows) if _has_bullish_signal(row)]
    latest_bullish_signal_age_td = (
        len(window_rows) - 1 - bullish_indices[-1] if bullish_indices else None
    )
    structure_override = int(any(_has_structure_override(row) for row in window_rows))
    if pullback_days > 0 and structure_override == 1:
        candidate_rolling5_status = "FAILED_PULLBACK"
    elif pullback_days > 0:
        candidate_rolling5_status = "PULLBACK_CANDIDATE"
    else:
        candidate_rolling5_status = "NO_PULLBACK"
    reason = (
        f"pullback_days={pullback_days}|"
        f"latest_bullish_signal_age_td={_cell(latest_bullish_signal_age_td)}|"
        f"structure_override={structure_override}"
    )
    return CandidateEvaluation(
        ticker=ticker,
        reports_pullback_validity=reports_pullback_validity,
        candidate_rolling5_status=candidate_rolling5_status,
        candidate_pullback_days=pullback_days,
        candidate_latest_bullish_signal_age_td=latest_bullish_signal_age_td,
        candidate_structure_override=structure_override,
        candidate_reason=reason,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit for whether reports-mode rolling 5d pullback context "
            "can be approximated from structured analysis source tables."
        )
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument("--lookback-rows", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        source_columns, obvious_extra_columns = _load_source_metadata(args.analysis_db)
        reports_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
        enrichment_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
        selected = _selected_tickers(
            reports_by_ticker,
            enrichment_by_ticker,
            _parse_tickers(args.tickers),
            args.max_examples,
        )
        source_windows = _load_source_window_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
            selected,
            args.lookback_rows,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_section("run_summary")
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
        "analysis",
        args.analysis_db,
        taxonomy_version,
        args.report_date,
        "analysis_db",
    )

    _print_section("source_table_columns")
    _print_row("source_table_columns", "table_name", "column_name", "exists", "notes")
    source_column_set = set(source_columns)
    for column_name in REQUIRED_SOURCE_COLUMNS:
        note = "required_candidate_column" if column_name in source_column_set else "missing"
        _print_row(
            "source_table_columns",
            SOURCE_TABLE,
            column_name,
            1 if column_name in source_column_set else 0,
            note,
        )
    for column_name in obvious_extra_columns:
        _print_row(
            "source_table_columns",
            SOURCE_TABLE,
            column_name,
            1,
            "additional_rolling_or_pullback_column",
        )

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
    )
    for ticker in selected:
        reports_row = reports_by_ticker[ticker]
        enrichment_row = enrichment_by_ticker[ticker]
        _print_row(
            "selected_tickers",
            ticker,
            reports_row.get("pullback_validity"),
            enrichment_row.get("pullback_validity"),
            reports_row.get("entry_readiness"),
            enrichment_row.get("entry_readiness"),
            reports_row.get("candidate_priority_label"),
            enrichment_row.get("candidate_priority_label"),
        )

    _print_section("reports_pullback_distribution")
    _print_row("reports_pullback_distribution", "pullback_validity", "count")
    reports_distribution = Counter(
        _normalized_text(row.get("pullback_validity"), "INSUFFICIENT_DATA")
        for row in reports_snapshot.tickers
    )
    for pullback_validity, count in sorted(reports_distribution.items()):
        _print_row("reports_pullback_distribution", pullback_validity, count)

    metric_counts: dict[str, Counter[object]] = {
        "window_has_pullback_signal": Counter(),
        "window_pullback_signal_count": Counter(),
        "window_has_bullish_signal": Counter(),
        "window_bullish_signal_count": Counter(),
        "window_has_bos_down": Counter(),
        "window_has_reset_down": Counter(),
        "latest_row_pullback_signal": Counter(),
        "latest_row_bullish_signal": Counter(),
        "latest_row_bos_down": Counter(),
        "latest_row_reset_down": Counter(),
    }
    candidate_evaluations: list[CandidateEvaluation] = []
    for ticker in selected:
        rows = source_windows.get(ticker, [])
        latest_row = rows[-1] if rows else {}
        pullback_count = sum(1 for row in rows if _bool_value(row.get("pullback_signal")))
        bullish_count = sum(1 for row in rows if _has_bullish_signal(row))
        has_bos_down = int(any(_normalized_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN" for row in rows))
        has_reset_down = int(any("DOUBLE_BOS_DOWN" in _normalized_text(row.get("latest_reset_reason")).upper() for row in rows))
        metric_counts["window_has_pullback_signal"][int(pullback_count > 0)] += 1
        metric_counts["window_pullback_signal_count"][pullback_count] += 1
        metric_counts["window_has_bullish_signal"][int(bullish_count > 0)] += 1
        metric_counts["window_bullish_signal_count"][bullish_count] += 1
        metric_counts["window_has_bos_down"][has_bos_down] += 1
        metric_counts["window_has_reset_down"][has_reset_down] += 1
        metric_counts["latest_row_pullback_signal"][int(_bool_value(latest_row.get("pullback_signal")))] += 1
        metric_counts["latest_row_bullish_signal"][int(_has_bullish_signal(latest_row))] += 1
        metric_counts["latest_row_bos_down"][
            int(_normalized_text(latest_row.get("latest_bos_event_type")).upper() == "BOS_DOWN")
        ] += 1
        metric_counts["latest_row_reset_down"][
            int("DOUBLE_BOS_DOWN" in _normalized_text(latest_row.get("latest_reset_reason")).upper())
        ] += 1
        candidate_evaluations.append(
            _evaluate_candidate(
                ticker,
                _normalized_text(reports_by_ticker[ticker].get("pullback_validity"), "INSUFFICIENT_DATA"),
                rows,
            )
        )

    _print_section("source_window_signal_distribution")
    _print_row("source_window_signal_distribution", "metric", "value", "count")
    for metric_name in (
        "window_has_pullback_signal",
        "window_pullback_signal_count",
        "window_has_bullish_signal",
        "window_bullish_signal_count",
        "window_has_bos_down",
        "window_has_reset_down",
        "latest_row_pullback_signal",
        "latest_row_bullish_signal",
        "latest_row_bos_down",
        "latest_row_reset_down",
    ):
        for value, count in sorted(metric_counts[metric_name].items(), key=lambda item: str(item[0])):
            _print_row("source_window_signal_distribution", metric_name, value, count)

    _print_section("ticker_window_examples")
    _print_row(
        "ticker_window_examples",
        "ticker",
        "source_date",
        "pullback_signal",
        "bullish_candle_signal",
        "bullish_divergence_signal",
        "hidden_bullish_divergence_signal",
        "latest_bos_event_type",
        "latest_reset_reason",
        "exit_risk_signal",
        "exit_risk_severity",
        "distance_to_ema20_pct",
        "return_5d",
        "return_10d",
    )
    examples_printed = 0
    for ticker in selected:
        for row in source_windows.get(ticker, []):
            if examples_printed >= args.max_examples:
                break
            _print_row(
                "ticker_window_examples",
                ticker,
                row.get("signal_date"),
                *(row.get(field_name) for field_name in WINDOW_EXAMPLE_FIELDS),
            )
            examples_printed += 1
        if examples_printed >= args.max_examples:
            break

    _print_section("candidate_mapping_evaluation")
    _print_row(
        "candidate_mapping_evaluation",
        "ticker",
        "reports_pullback_validity",
        "candidate_rolling5_status",
        "candidate_pullback_days",
        "candidate_latest_bullish_signal_age_td",
        "candidate_structure_override",
        "candidate_reason",
    )
    for evaluation in candidate_evaluations:
        _print_row(
            "candidate_mapping_evaluation",
            evaluation.ticker,
            evaluation.reports_pullback_validity,
            evaluation.candidate_rolling5_status,
            evaluation.candidate_pullback_days,
            evaluation.candidate_latest_bullish_signal_age_td,
            evaluation.candidate_structure_override,
            evaluation.candidate_reason,
        )

    valid_early_total = sum(
        1
        for evaluation in candidate_evaluations
        if evaluation.reports_pullback_validity in {"VALID_PULLBACK", "EARLY_PULLBACK"}
    )
    valid_early_with_candidate_context = sum(
        1
        for evaluation in candidate_evaluations
        if evaluation.reports_pullback_validity in {"VALID_PULLBACK", "EARLY_PULLBACK"}
        and (
            evaluation.candidate_pullback_days > 0
            or evaluation.candidate_latest_bullish_signal_age_td is not None
        )
    )
    structure_blocked_total = sum(
        1
        for evaluation in candidate_evaluations
        if evaluation.reports_pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
    )
    structure_blocked_with_candidate_override = sum(
        1
        for evaluation in candidate_evaluations
        if evaluation.reports_pullback_validity == "STRUCTURE_BLOCKED_PULLBACK"
        and evaluation.candidate_structure_override == 1
    )

    structured_source_has_inputs = (
        "LIKELY"
        if {"pullback_signal", "bullish_candle_signal", "bullish_divergence_signal", "hidden_bullish_divergence_signal"}.issubset(source_column_set)
        else "UNLIKELY"
    )
    valid_early_can_be_approximated = (
        "LIKELY"
        if valid_early_total > 0 and valid_early_with_candidate_context * 2 >= valid_early_total
        else "UNLIKELY"
    )
    structure_blocked_can_be_approximated = (
        "LIKELY"
        if structure_blocked_total > 0
        and structure_blocked_with_candidate_override * 2 >= structure_blocked_total
        else "UNLIKELY"
    )
    needs_true_rolling5 = (
        "LIKELY"
        if valid_early_can_be_approximated == "UNLIKELY"
        or structure_blocked_can_be_approximated == "UNLIKELY"
        else "UNLIKELY"
    )
    safe_v0_mapping_recommended = (
        "LIKELY"
        if structured_source_has_inputs == "LIKELY"
        and valid_early_can_be_approximated == "LIKELY"
        and structure_blocked_can_be_approximated == "LIKELY"
        else "UNLIKELY"
    )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "STRUCTURED_SOURCE_HAS_ROLLING5_PULLBACK_INPUTS",
        structured_source_has_inputs,
        f"pullback_signal={'1' if 'pullback_signal' in source_column_set else '0'}|bullish_columns={'1' if {'bullish_candle_signal', 'bullish_divergence_signal', 'hidden_bullish_divergence_signal'}.issubset(source_column_set) else '0'}",
    )
    _print_row(
        "hypothesis_summary",
        "REPORTS_VALID_EARLY_PULLBACK_CAN_BE_APPROXIMATED_FROM_SOURCE_WINDOW",
        valid_early_can_be_approximated,
        f"valid_early_total={valid_early_total}|valid_early_with_candidate_context={valid_early_with_candidate_context}",
    )
    _print_row(
        "hypothesis_summary",
        "STRUCTURE_BLOCKED_CAN_BE_APPROXIMATED_FROM_SOURCE_WINDOW",
        structure_blocked_can_be_approximated,
        f"structure_blocked_total={structure_blocked_total}|structure_blocked_with_candidate_override={structure_blocked_with_candidate_override}",
    )
    _print_row(
        "hypothesis_summary",
        "NEEDS_TRUE_ROLLING5_STATUS_TABLE",
        needs_true_rolling5,
        f"valid_early={valid_early_can_be_approximated}|structure_blocked={structure_blocked_can_be_approximated}",
    )
    _print_row(
        "hypothesis_summary",
        "SAFE_V0_MAPPING_RECOMMENDED",
        safe_v0_mapping_recommended,
        f"structured_source_has_inputs={structured_source_has_inputs}|valid_early={valid_early_can_be_approximated}|structure_blocked={structure_blocked_can_be_approximated}",
    )

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.status=OK")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.selected_tickers={len(selected)}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.lookback_rows={args.lookback_rows}")
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.source_has_pullback_signal="
        f"{1 if 'pullback_signal' in source_column_set else 0}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.source_has_bullish_signals="
        f"{1 if {'bullish_candle_signal', 'bullish_divergence_signal', 'hidden_bullish_divergence_signal'}.issubset(source_column_set) else 0}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.valid_early_with_candidate_context="
        f"{valid_early_with_candidate_context}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.structure_blocked_with_candidate_override="
        f"{structure_blocked_with_candidate_override}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.safe_v0_mapping_recommended="
        f"{1 if safe_v0_mapping_recommended == 'LIKELY' else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
