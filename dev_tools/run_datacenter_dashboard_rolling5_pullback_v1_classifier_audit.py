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
REPORT_PRIORITY = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)
CLASSIFIER_TO_REPORTS = {
    "VALID_PULLBACK_CONTEXT": "VALID_PULLBACK",
    "EARLY_PULLBACK_CONTEXT": "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK_CONTEXT": "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK_CONTEXT": "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK_CONTEXT": "NO_PULLBACK",
    "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
}


@dataclass(frozen=True)
class Classification:
    ticker: str
    reports_pullback_validity: str
    classifier_status: str
    classifier_mapped_status: str
    source_rows: int
    pullback_days: int
    latest_bullish_signal_age: int | None
    structure_blocker: int
    breakdown_blocker: int
    latest_return_10d: object
    latest_distance_to_ema20_pct: object
    latest_exit_risk_signal: object
    reason: str


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


def _safe_float(value: object) -> float | None:
    text = _cell(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bool_value(value: object) -> bool:
    return _safe_int(value) == 1


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


def _has_bullish_signal(row: dict[str, object]) -> bool:
    return any(
        _bool_value(row.get(field_name))
        for field_name in (
            "bullish_candle_signal",
            "bullish_divergence_signal",
            "hidden_bullish_divergence_signal",
        )
    )


def _pullback_signal_present(row: dict[str, object]) -> bool:
    return any(
        _bool_value(row.get(field_name))
        for field_name in (
            "pullback_signal",
            "conservative_ema20_pullback_signal",
            "fast_ema10_pullback_signal",
        )
    )


def _structure_blocker(row: dict[str, object]) -> bool:
    if _normalized_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN":
        return True
    return "DOUBLE_BOS_DOWN" in _normalized_text(row.get("latest_reset_reason")).upper()


def _ma_break_confirmed(row: dict[str, object]) -> bool:
    value = _normalized_text(row.get("ma_break_status")).upper()
    return "CONFIRMED_BREAK" in value or value in {
        "EMA20_CONFIRMED_BREAK",
        "SMA50_CONFIRMED_BREAK",
    }


def _return_10d_breakdown(row: dict[str, object]) -> bool:
    numeric = _safe_float(row.get("return_10d"))
    if numeric is None:
        return False
    if abs(numeric) <= 1:
        return numeric <= -0.08
    return numeric <= -8


def _distance_exit_breakdown(row: dict[str, object]) -> bool:
    distance = _safe_float(row.get("distance_to_ema20_pct"))
    if distance is None:
        return False
    return distance < 0 and _bool_value(row.get("exit_risk_signal"))


def _breakdown_blocker(window_rows: list[dict[str, object]]) -> bool:
    for row in window_rows:
        if _ma_break_confirmed(row):
            return True
        if _return_10d_breakdown(row):
            return True
        if _distance_exit_breakdown(row):
            return True
    return False


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
        columns = _table_columns(conn, SOURCE_TABLE)
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
    source_windows: dict[str, list[dict[str, object]]],
    explicit_tickers: list[str],
) -> list[str]:
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in reports_by_ticker]
    selected: list[str] = []
    for pullback_validity in REPORT_PRIORITY:
        for ticker in sorted(reports_by_ticker):
            if ticker == "CRGY" and not source_windows.get(ticker):
                continue
            row = reports_by_ticker[ticker]
            if _normalized_text(row.get("pullback_validity"), "INSUFFICIENT_DATA") != pullback_validity:
                continue
            if not source_windows.get(ticker):
                continue
            selected.append(ticker)
    return selected


def _classify_ticker(
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
            latest_return_10d=None,
            latest_distance_to_ema20_pct=None,
            latest_exit_risk_signal=None,
            reason=reason,
        )
    pullback_days = sum(1 for row in window_rows if _pullback_signal_present(row))
    bullish_indices = [index for index, row in enumerate(window_rows) if _has_bullish_signal(row)]
    latest_bullish_signal_age = (
        len(window_rows) - 1 - bullish_indices[-1] if bullish_indices else None
    )
    structure_blocker = int(any(_structure_blocker(row) for row in window_rows))
    breakdown_blocker = int(_breakdown_blocker(window_rows))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit for proposed V1 rolling5 pullback classifier against reports-mode."
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

    classifications: list[Classification] = []
    for ticker in selected_tickers:
        reports_pullback = _normalized_text(
            reports_by_ticker[ticker].get("pullback_validity"),
            "INSUFFICIENT_DATA",
        )
        classifications.append(
            _classify_ticker(
                ticker,
                reports_pullback,
                source_windows.get(ticker, []),
            )
        )

    classifier_distribution = Counter(c.classifier_status for c in classifications)
    reports_distribution = Counter(c.reports_pullback_validity for c in classifications)
    confusion = Counter((c.reports_pullback_validity, c.classifier_mapped_status) for c in classifications)
    exact_matches = sum(1 for c in classifications if c.reports_pullback_validity == c.classifier_mapped_status)
    exact_match_rate = (exact_matches / len(classifications)) if classifications else 0.0

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
        "analysis",
        args.analysis_db,
        taxonomy_version,
        args.report_date,
        "analysis_db",
    )

    _print_section("classifier_distribution")
    _print_row("classifier_distribution", "classifier_status", "reports_mapped_status", "count")
    for classifier_status, count in sorted(classifier_distribution.items()):
        _print_row(
            "classifier_distribution",
            classifier_status,
            CLASSIFIER_TO_REPORTS[classifier_status],
            count,
        )

    _print_section("reports_distribution")
    _print_row("reports_distribution", "pullback_validity", "count")
    for pullback_validity, count in sorted(reports_distribution.items()):
        _print_row("reports_distribution", pullback_validity, count)

    _print_section("confusion_matrix")
    _print_row("confusion_matrix", "reports_pullback_validity", "classifier_mapped_status", "count")
    for (reports_pullback, classifier_mapped), count in sorted(confusion.items()):
        _print_row("confusion_matrix", reports_pullback, classifier_mapped, count)

    mismatches = [c for c in classifications if c.reports_pullback_validity != c.classifier_mapped_status]
    mismatches.sort(key=lambda c: (REPORT_PRIORITY.index(c.reports_pullback_validity), c.ticker))
    exacts = [c for c in classifications if c.reports_pullback_validity == c.classifier_mapped_status]
    exacts.sort(key=lambda c: (REPORT_PRIORITY.index(c.reports_pullback_validity), c.ticker))
    selected_examples = mismatches[: args.max_examples]
    if len(selected_examples) < args.max_examples:
        selected_examples.extend(exacts[: args.max_examples - len(selected_examples)])

    _print_section("selected_mismatches")
    _print_row(
        "selected_mismatches",
        "ticker",
        "reports_pullback_validity",
        "classifier_status",
        "classifier_mapped_status",
        "reason",
    )
    for classification in selected_examples:
        if classification.reports_pullback_validity == classification.classifier_mapped_status:
            continue
        _print_row(
            "selected_mismatches",
            classification.ticker,
            classification.reports_pullback_validity,
            classification.classifier_status,
            classification.classifier_mapped_status,
            classification.reason,
        )

    _print_section("classifier_inputs")
    _print_row(
        "classifier_inputs",
        "ticker",
        "source_rows",
        "pullback_days",
        "latest_bullish_signal_age",
        "structure_blocker",
        "breakdown_blocker",
        "latest_return_10d",
        "latest_distance_to_ema20_pct",
        "latest_exit_risk_signal",
        "reason",
    )
    for classification in selected_examples:
        _print_row(
            "classifier_inputs",
            classification.ticker,
            classification.source_rows,
            classification.pullback_days,
            classification.latest_bullish_signal_age,
            classification.structure_blocker,
            classification.breakdown_blocker,
            classification.latest_return_10d,
            classification.latest_distance_to_ema20_pct,
            classification.latest_exit_risk_signal,
            classification.reason,
        )

    reports_valid_early = sum(
        count for status, count in reports_distribution.items() if status in {"VALID_PULLBACK", "EARLY_PULLBACK"}
    )
    classifier_valid_early = sum(
        count
        for status, count in classifier_distribution.items()
        if status in {"VALID_PULLBACK_CONTEXT", "EARLY_PULLBACK_CONTEXT"}
    )
    reports_structure_blocked = reports_distribution.get("STRUCTURE_BLOCKED_PULLBACK", 0)
    classifier_structure_blocked = classifier_distribution.get(
        "STRUCTURE_BLOCKED_PULLBACK_CONTEXT", 0
    )
    valid_early_misclassified = sum(
        count
        for (reports_status, classifier_status), count in confusion.items()
        if reports_status in {"VALID_PULLBACK", "EARLY_PULLBACK"}
        and classifier_status in {"NO_PULLBACK", "STRUCTURE_BLOCKED_PULLBACK"}
    )
    structure_blocked_too_broad = sum(
        count
        for (reports_status, classifier_status), count in confusion.items()
        if reports_status in {"VALID_PULLBACK", "EARLY_PULLBACK"}
        and classifier_status == "STRUCTURE_BLOCKED_PULLBACK"
    )
    breakdown_too_broad = sum(
        count
        for (reports_status, classifier_status), count in confusion.items()
        if reports_status != "BREAKDOWN_NOT_PULLBACK"
        and classifier_status == "BREAKDOWN_NOT_PULLBACK"
    )
    insufficient_for_parity = sum(
        count
        for (reports_status, classifier_status), count in confusion.items()
        if reports_status != "INSUFFICIENT_DATA"
        and classifier_status == "INSUFFICIENT_DATA"
    )
    severe_bias = (
        valid_early_misclassified >= max(5, reports_valid_early // 2)
        or structure_blocked_too_broad >= max(5, reports_valid_early // 2)
        or breakdown_too_broad >= 5
        or insufficient_for_parity >= 5
    )
    v1_worth_schema_implementation = int(exact_match_rate >= 0.60 and not severe_bias)

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "V1_CLASSIFIER_CLOSE_TO_REPORTS",
        "LIKELY" if exact_match_rate >= 0.70 else "UNLIKELY",
        f"exact_matches={exact_matches}|tickers_evaluated={len(classifications)}|exact_match_rate={exact_match_rate:.4f}",
    )
    _print_row(
        "hypothesis_summary",
        "V1_VALID_EARLY_TOO_STRICT",
        "LIKELY" if valid_early_misclassified > 0 else "UNLIKELY",
        f"reports_valid_early={reports_valid_early}|valid_early_to_no_or_blocked={valid_early_misclassified}",
    )
    _print_row(
        "hypothesis_summary",
        "V1_STRUCTURE_BLOCKER_TOO_BROAD",
        "LIKELY" if structure_blocked_too_broad > 0 else "UNLIKELY",
        f"valid_early_to_structure_blocked={structure_blocked_too_broad}",
    )
    _print_row(
        "hypothesis_summary",
        "V1_BREAKDOWN_TOO_BROAD",
        "LIKELY" if breakdown_too_broad > 0 else "UNLIKELY",
        f"non_breakdown_to_breakdown={breakdown_too_broad}",
    )
    _print_row(
        "hypothesis_summary",
        "SOURCE_INSUFFICIENT_FOR_PARITY",
        "LIKELY" if insufficient_for_parity > 0 else "UNLIKELY",
        f"non_insufficient_to_insufficient={insufficient_for_parity}",
    )
    _print_row(
        "hypothesis_summary",
        "V1_WORTH_SCHEMA_IMPLEMENTATION",
        "LIKELY" if v1_worth_schema_implementation == 1 else "UNLIKELY",
        f"exact_match_rate={exact_match_rate:.4f}|severe_bias={1 if severe_bias else 0}",
    )

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.status=OK")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.lookback_rows={args.lookback_rows}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.tickers_evaluated={len(classifications)}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.exact_matches={exact_matches}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.exact_match_rate={exact_match_rate:.4f}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.reports_valid_early={reports_valid_early}")
    print(f"SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.classifier_valid_early={classifier_valid_early}")
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.reports_structure_blocked="
        f"{reports_structure_blocked}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.classifier_structure_blocked="
        f"{classifier_structure_blocked}"
    )
    print(
        "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.v1_worth_schema_implementation="
        f"{v1_worth_schema_implementation}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
