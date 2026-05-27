from __future__ import annotations

import argparse
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

ACTION_PRIORITY = [
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
]

GAP_TYPES = [
    "REPORTS_SELL_ENRICHMENT_NEUTRAL",
    "REPORTS_SELL_ENRICHMENT_REDUCE",
    "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL_OR_REDUCE",
    "REPORTS_REDUCE_ENRICHMENT_NEUTRAL",
]

MISSING_SIGNAL_FIELDS = [
    "ma_break_status",
    "freshness_status",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "latest_bos_event_type",
    "latest_reset_reason",
    "exit_risk_severity",
    "high_exit_risk_days_count",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
]

SOURCE_DISTRIBUTION_FIELDS = [
    "daily_status",
    "current_status",
    "ma_break_status",
    "freshness_status",
    "latest_bos_event_type",
    "latest_reset_reason",
    "exit_risk_severity",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
]

EXAMPLE_GAP_ORDER = [
    ("SELL", "NEUTRAL"),
    ("SELL", "REDUCE"),
    ("TIGHTEN_STOP", "NEUTRAL"),
    ("TIGHTEN_STOP", "REDUCE"),
    ("REDUCE", "NEUTRAL"),
    ("NEUTRAL", "SELL"),
    ("NEUTRAL", "REDUCE"),
]


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace(";", ",").strip()


def _print_section(name: str) -> None:
    print(f"section;{name}")


def _print_row(prefix: str, *columns: object) -> None:
    print(";".join([prefix, *(_cell(column) for column in columns)]))


def _normalized_action(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _action_sort_key(action: str) -> tuple[int, str]:
    normalized = _normalized_action(action)
    if normalized in ACTION_PRIORITY:
        return (ACTION_PRIORITY.index(normalized), normalized)
    return (len(ACTION_PRIORITY), normalized)


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(",", " ")
    tickers = []
    seen: set[str] = set()
    for token in normalized.split():
        ticker = token.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


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
            if not ticker or ticker in by_ticker:
                continue
            by_ticker[ticker] = {key: row[key] for key in row.keys()}
        return by_ticker


def _ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            result[ticker] = row
    return result


def _distribution(rows: list[dict[str, object]], field_name: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        value = _cell(row.get(field_name))
        if value:
            counts[value] += 1
    return counts


def _gap_type(reports_action: str, enrichment_action: str) -> str | None:
    reports_action = _normalized_action(reports_action)
    enrichment_action = _normalized_action(enrichment_action)
    if reports_action == "SELL" and enrichment_action == "NEUTRAL":
        return "REPORTS_SELL_ENRICHMENT_NEUTRAL"
    if reports_action == "SELL" and enrichment_action == "REDUCE":
        return "REPORTS_SELL_ENRICHMENT_REDUCE"
    if reports_action == "TIGHTEN_STOP" and enrichment_action in {"NEUTRAL", "REDUCE"}:
        return "REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL_OR_REDUCE"
    if reports_action == "REDUCE" and enrichment_action == "NEUTRAL":
        return "REPORTS_REDUCE_ENRICHMENT_NEUTRAL"
    return None


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _missing_pct(missing_count: int, total_count: int) -> str:
    if total_count <= 0:
        return "0.0000"
    return f"{(missing_count / total_count) * 100.0:.4f}"


def _selected_tickers(
    common_tickers: list[str],
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[str]:
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in common_tickers and ticker != "CRGY"]
    selected: list[str] = []
    seen: set[str] = set()
    for reports_action, enrichment_action in EXAMPLE_GAP_ORDER:
        matches = [
            ticker
            for ticker in common_tickers
            if ticker != "CRGY"
            and _normalized_action(reports_by_ticker[ticker].get("action")) == reports_action
            and _normalized_action(enrichment_by_ticker[ticker].get("action")) == enrichment_action
        ]
        for ticker in matches[:max_examples]:
            if ticker not in seen:
                seen.add(ticker)
                selected.append(ticker)
    return selected[:max_examples]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose action parity gaps between reports and enrichment dashboard snapshots."
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
        analysis_by_ticker = _load_analysis_rows(args.analysis_db_copy, args.report_date)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1

    reports_by_ticker = _ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _ticker_map(enrichment_snapshot.tickers)
    common_tickers = sorted(
        ticker
        for ticker in set(reports_by_ticker) & set(enrichment_by_ticker) & set(analysis_by_ticker)
        if ticker != "CRGY"
    )
    explicit_tickers = _parse_tickers(args.tickers)
    selected = _selected_tickers(
        common_tickers,
        reports_by_ticker,
        enrichment_by_ticker,
        explicit_tickers,
        args.max_examples,
    )

    confusion = Counter(
        (
            _normalized_action(reports_by_ticker[ticker].get("action")),
            _normalized_action(enrichment_by_ticker[ticker].get("action")),
        )
        for ticker in common_tickers
    )
    gap_rows: dict[str, list[str]] = defaultdict(list)
    for ticker in common_tickers:
        gap = _gap_type(
            _cell(reports_by_ticker[ticker].get("action")),
            _cell(enrichment_by_ticker[ticker].get("action")),
        )
        if gap is not None:
            gap_rows[gap].append(ticker)

    reports_neutral_count = sum(
        1
        for ticker in common_tickers
        if _normalized_action(reports_by_ticker[ticker].get("action")) == "NEUTRAL"
    )
    enrichment_neutral_count = sum(
        1
        for ticker in common_tickers
        if _normalized_action(enrichment_by_ticker[ticker].get("action")) == "NEUTRAL"
    )

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
        "analysis_copy",
        args.analysis_db_copy,
        "",
        args.report_date,
        "analysis_enrichment_tables",
    )

    _print_section("action_confusion_matrix")
    _print_row("action_confusion_matrix", "reports_action", "enrichment_action", "count")
    for reports_action, enrichment_action in sorted(
        confusion,
        key=lambda item: (_action_sort_key(item[0]), _action_sort_key(item[1])),
    ):
        _print_row(
            "action_confusion_matrix",
            reports_action,
            enrichment_action,
            confusion[(reports_action, enrichment_action)],
        )

    _print_section("major_gap_examples")
    _print_row(
        "major_gap_examples",
        "ticker",
        "reports_action",
        "enrichment_action",
        "reports_primary_reason",
        "enrichment_primary_reason",
        "reports_current_status",
        "enrichment_current_status",
        "analysis_daily_status",
        "analysis_current_status",
        "analysis_ma_break_status",
        "analysis_freshness_status",
        "analysis_latest_bos_event_type",
        "analysis_latest_reset_reason",
        "analysis_exit_risk_severity",
        "analysis_high_exit_risk_days_count",
        "analysis_rolling_2d_status",
        "analysis_rolling_5d_status",
        "analysis_rolling_30d_status",
    )
    example_count = 0
    for reports_action, enrichment_action in EXAMPLE_GAP_ORDER:
        matches = [
            ticker
            for ticker in selected
            if _normalized_action(reports_by_ticker[ticker].get("action")) == reports_action
            and _normalized_action(enrichment_by_ticker[ticker].get("action")) == enrichment_action
        ]
        for ticker in matches[: args.max_examples]:
            analysis_row = analysis_by_ticker[ticker]
            reports_row = reports_by_ticker[ticker]
            enrichment_row = enrichment_by_ticker[ticker]
            _print_row(
                "major_gap_examples",
                ticker,
                reports_row.get("action"),
                enrichment_row.get("action"),
                reports_row.get("primary_reason"),
                enrichment_row.get("primary_reason"),
                reports_row.get("current_status"),
                enrichment_row.get("current_status"),
                analysis_row.get("daily_status"),
                analysis_row.get("current_status"),
                analysis_row.get("ma_break_status"),
                analysis_row.get("freshness_status"),
                analysis_row.get("latest_bos_event_type"),
                analysis_row.get("latest_reset_reason"),
                analysis_row.get("exit_risk_severity"),
                analysis_row.get("high_exit_risk_days_count"),
                analysis_row.get("rolling_2d_status"),
                analysis_row.get("rolling_5d_status"),
                analysis_row.get("rolling_30d_status"),
            )
            example_count += 1

    _print_section("missing_signal_summary")
    _print_row(
        "missing_signal_summary",
        "gap_type",
        "field_name",
        "missing_or_empty_count",
        "total_gap_count",
        "missing_pct",
    )
    for gap_type in GAP_TYPES:
        tickers = gap_rows.get(gap_type, [])
        total_gap_count = len(tickers)
        for field_name in MISSING_SIGNAL_FIELDS:
            missing_count = sum(
                1 for ticker in tickers if _is_missing(analysis_by_ticker[ticker].get(field_name))
            )
            _print_row(
                "missing_signal_summary",
                gap_type,
                field_name,
                missing_count,
                total_gap_count,
                _missing_pct(missing_count, total_gap_count),
            )

    _print_section("source_signal_distribution_by_gap")
    _print_row("source_signal_distribution_by_gap", "gap_type", "field_name", "value", "count")
    for gap_type in GAP_TYPES:
        tickers = gap_rows.get(gap_type, [])
        for field_name in SOURCE_DISTRIBUTION_FIELDS:
            counts: Counter[str] = Counter()
            for ticker in tickers:
                value = _cell(analysis_by_ticker[ticker].get(field_name))
                counts[value] += 1
            for value, count in sorted(counts.items(), key=lambda item: (item[0], item[1])):
                _print_row("source_signal_distribution_by_gap", gap_type, field_name, value, count)

    sell_gap_tickers = gap_rows["REPORTS_SELL_ENRICHMENT_NEUTRAL"] + gap_rows["REPORTS_SELL_ENRICHMENT_REDUCE"]
    tighten_gap_tickers = gap_rows["REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL_OR_REDUCE"]
    reports_risk_actions = [
        ticker
        for ticker in common_tickers
        if _normalized_action(reports_by_ticker[ticker].get("action")) in {"SELL", "REDUCE"}
    ]
    partial_mapping_count = sum(
        1
        for ticker in reports_risk_actions
        if _normalized_action(enrichment_by_ticker[ticker].get("action")) in {"SELL", "REDUCE"}
    )
    neutral_mapping_count = sum(
        1
        for ticker in reports_risk_actions
        if _normalized_action(enrichment_by_ticker[ticker].get("action")) == "NEUTRAL"
    )

    hypotheses = [
        (
            "MISSING_ROLLING_2D_SIGNALS_CAUSES_SELL_GAP",
            "LIKELY"
            if sell_gap_tickers
            and sum(
                1 for ticker in sell_gap_tickers if _is_missing(analysis_by_ticker[ticker].get("rolling_2d_status"))
            ) * 2
            > len(sell_gap_tickers)
            else "UNLIKELY",
            f"sell_gap_count={len(sell_gap_tickers)};"
            f"missing_rolling_2d_status={sum(1 for ticker in sell_gap_tickers if _is_missing(analysis_by_ticker[ticker].get('rolling_2d_status')))}",
        ),
        (
            "MISSING_MA_BREAK_STATUS_CAUSES_SELL_GAP",
            "LIKELY"
            if sell_gap_tickers
            and sum(
                1 for ticker in sell_gap_tickers if _is_missing(analysis_by_ticker[ticker].get("ma_break_status"))
            ) * 2
            > len(sell_gap_tickers)
            else "UNLIKELY",
            f"sell_gap_count={len(sell_gap_tickers)};"
            f"missing_ma_break_status={sum(1 for ticker in sell_gap_tickers if _is_missing(analysis_by_ticker[ticker].get('ma_break_status')))}",
        ),
        (
            "MISSING_HIGH_EXIT_RISK_DAYS_CAUSES_TIGHTEN_STOP_GAP",
            "LIKELY"
            if tighten_gap_tickers
            and sum(
                1
                for ticker in tighten_gap_tickers
                if _is_missing(analysis_by_ticker[ticker].get("high_exit_risk_days_count"))
            )
            * 2
            > len(tighten_gap_tickers)
            else "UNLIKELY",
            f"tighten_stop_gap_count={len(tighten_gap_tickers)};"
            f"missing_high_exit_risk_days_count={sum(1 for ticker in tighten_gap_tickers if _is_missing(analysis_by_ticker[ticker].get('high_exit_risk_days_count')))}",
        ),
        (
            "DAILY_EXIT_RISK_MAPPING_WORKS_PARTIALLY",
            "LIKELY" if partial_mapping_count > neutral_mapping_count else "UNLIKELY",
            f"reports_sell_or_reduce={len(reports_risk_actions)};"
            f"enrichment_sell_or_reduce={partial_mapping_count};"
            f"enrichment_neutral={neutral_mapping_count}",
        ),
        (
            "ENRICHMENT_NEUTRAL_STILL_TOO_HIGH",
            "LIKELY" if enrichment_neutral_count > reports_neutral_count * 10 else "UNLIKELY",
            f"enrichment_neutral={enrichment_neutral_count};reports_neutral={reports_neutral_count}",
        ),
    ]

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    for hypothesis, status, evidence in hypotheses:
        _print_row("hypothesis_summary", hypothesis, status, evidence)

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.status=OK")
    print(f"SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.common_tickers={len(common_tickers)}")
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.reports_sell_enrichment_neutral="
        f"{len(gap_rows['REPORTS_SELL_ENRICHMENT_NEUTRAL'])}"
    )
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.reports_sell_enrichment_reduce="
        f"{len(gap_rows['REPORTS_SELL_ENRICHMENT_REDUCE'])}"
    )
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.reports_tighten_stop_enrichment_neutral_or_reduce="
        f"{len(gap_rows['REPORTS_TIGHTEN_STOP_ENRICHMENT_NEUTRAL_OR_REDUCE'])}"
    )
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.reports_reduce_enrichment_neutral="
        f"{len(gap_rows['REPORTS_REDUCE_ENRICHMENT_NEUTRAL'])}"
    )
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.enrichment_neutral_count="
        f"{enrichment_neutral_count}"
    )
    print(
        "SUMMARY datacenter_dashboard_action_parity_gap_diagnosis.reports_neutral_count="
        f"{reports_neutral_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
