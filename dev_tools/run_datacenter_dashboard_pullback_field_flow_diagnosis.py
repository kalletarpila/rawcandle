from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_decisions_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
FIELD_SPECS = (
    ("pullback_validity", "INSUFFICIENT_DATA"),
    ("entry_readiness", "INSUFFICIENT_DATA"),
    ("candidate_priority_label", "MISSING"),
)
DETAIL_FIELDS = (
    "pullback_validity",
    "pullback_reason",
    "entry_readiness",
    "entry_readiness_reason",
    "candidate_priority",
    "candidate_priority_label",
    "candidate_priority_reason",
)
MISSING_BY_FIELD = {
    "pullback_validity": "INSUFFICIENT_DATA",
    "entry_readiness": "INSUFFICIENT_DATA",
    "candidate_priority_label": "MISSING",
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


def _snapshot_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _load_optional_json(enrichment_json: str | None) -> list[dict[str, object]] | None:
    if enrichment_json is None:
        return None
    path = Path(enrichment_json)
    if not path.exists():
        raise FileNotFoundError(f"enrichment_json not found: {enrichment_json}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tickers = payload.get("tickers")
    if tickers is None:
        return []
    if not isinstance(tickers, list):
        raise ValueError("enrichment_json tickers must be a list")
    return tickers


def _json_ticker_map(rows: list[dict[str, object]] | None) -> dict[str, dict[str, object]]:
    if not rows:
        return {}
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _normalized_field(value: object, default: str) -> str:
    text = _cell(value)
    return text or default


def _is_semantic(value: object, default: str) -> bool:
    normalized = _normalized_field(value, default)
    return normalized != default


def _field_distribution(
    rows: list[dict[str, object]],
    field_name: str,
    default: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[_normalized_field(row.get(field_name), default)] += 1
    return counts


def _decision_distribution(
    decisions_by_ticker: dict[str, object],
    field_name: str,
    default: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in decisions_by_ticker.values():
        counts[_normalized_field(getattr(decision, field_name, None), default)] += 1
    return counts


def _select_tickers(
    *,
    explicit_tickers: list[str],
    analysis_by_ticker: dict[str, dict[str, object]],
    dashboard_by_ticker: dict[str, dict[str, object]],
    adapter_by_ticker: dict[str, object],
    max_examples: int,
) -> list[str]:
    if explicit_tickers:
        return [ticker for ticker in explicit_tickers if ticker in dashboard_by_ticker or ticker in analysis_by_ticker]

    selected: list[str] = []
    for ticker in sorted(set(analysis_by_ticker) | set(dashboard_by_ticker) | set(adapter_by_ticker)):
        analysis_row = analysis_by_ticker.get(ticker, {})
        dashboard_row = dashboard_by_ticker.get(ticker, {})
        adapter = adapter_by_ticker.get(ticker)
        include = False
        for field_name, default in FIELD_SPECS:
            analysis_value = _normalized_field(analysis_row.get(field_name), default)
            dashboard_value = _normalized_field(dashboard_row.get(field_name), default)
            adapter_value = _normalized_field(
                None if adapter is None else getattr(adapter, field_name, None),
                default,
            )
            if analysis_value != dashboard_value:
                include = True
                break
            if adapter_value != dashboard_value:
                include = True
                break
            if dashboard_value == default and adapter_value != default:
                include = True
                break
        if include:
            selected.append(ticker)
        if len(selected) >= max_examples:
            break
    return selected


def _diagnosis_for_field(
    *,
    analysis_value: str,
    json_value: str,
    dashboard_value: str,
    adapter_value: str,
    default: str,
) -> str:
    if analysis_value != default and json_value == default:
        return "ANALYSIS_TO_JSON_GAP"
    if json_value != default and dashboard_value == default:
        return "JSON_TO_DASHBOARD_GAP"
    if adapter_value != default and analysis_value == default:
        return "ADAPTER_TO_ANALYSIS_GAP"
    if (
        analysis_value != default
        and analysis_value == json_value
        and analysis_value == adapter_value
        and dashboard_value != analysis_value
    ):
        return "DASHBOARD_STALE_OR_PREVIOUS_RUN"
    return "NO_GAP"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose pullback/readiness/candidate-priority field flow across "
            "analysis enrichment, optional export JSON, persisted dashboard snapshot, "
            "and adapter-rebuilt decisions."
        )
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--enrichment-json")
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dashboard_snapshot = load_dashboard_snapshot(
            dashboard_db=args.enrichment_dashboard_db,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
            run_id=args.enrichment_run_id,
        )
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        analysis_rows = load_ticker_enrichment_rows(
            analysis_db=args.analysis_db,
            signal_date=args.report_date,
            taxonomy_version=taxonomy_version,
        )
        json_rows = _load_optional_json(args.enrichment_json)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    dashboard_by_ticker = _snapshot_ticker_map(dashboard_snapshot.tickers)
    analysis_by_ticker = _snapshot_ticker_map(analysis_rows)
    json_by_ticker = _json_ticker_map(json_rows)
    adapter_result = build_decisions_from_ticker_enrichment_rows(analysis_rows)
    adapter_by_ticker = {
        decision.ticker.upper(): decision for decision in adapter_result.decisions
    }
    explicit_tickers = _parse_tickers(args.tickers)
    selected_tickers = _select_tickers(
        explicit_tickers=explicit_tickers,
        analysis_by_ticker=analysis_by_ticker,
        dashboard_by_ticker=dashboard_by_ticker,
        adapter_by_ticker=adapter_by_ticker,
        max_examples=args.max_examples,
    )

    _print_section("run_summary")
    _print_row("run_summary", "side", "db_path", "run_id", "report_date", "source")
    _print_row(
        "run_summary",
        "analysis",
        args.analysis_db,
        taxonomy_version,
        args.report_date,
        "analysis_db",
    )
    _print_row(
        "run_summary",
        "enrichment_dashboard",
        args.enrichment_dashboard_db,
        args.enrichment_run_id,
        args.report_date,
        "dashboard_db",
    )
    if args.enrichment_json is not None:
        _print_row(
            "run_summary",
            "enrichment_json",
            args.enrichment_json,
            "",
            args.report_date,
            "json",
        )

    _print_section("aggregate_field_flow")
    _print_row(
        "aggregate_field_flow",
        "field_name",
        "analysis_non_empty",
        "json_non_empty",
        "dashboard_non_empty",
        "adapter_non_empty",
        "analysis_insufficient",
        "json_insufficient",
        "dashboard_insufficient",
        "adapter_insufficient",
    )
    for field_name, default in FIELD_SPECS:
        analysis_non_empty = sum(1 for row in analysis_rows if _is_semantic(row.get(field_name), default))
        json_non_empty = (
            ""
            if json_rows is None
            else sum(1 for row in json_rows if _is_semantic(row.get(field_name), default))
        )
        dashboard_non_empty = sum(
            1 for row in dashboard_snapshot.tickers if _is_semantic(row.get(field_name), default)
        )
        adapter_non_empty = sum(
            1
            for decision in adapter_by_ticker.values()
            if _is_semantic(getattr(decision, field_name, None), default)
        )
        analysis_insufficient = sum(
            1 for row in analysis_rows if _normalized_field(row.get(field_name), default) == default
        )
        json_insufficient = (
            ""
            if json_rows is None
            else sum(
                1
                for row in json_rows
                if _normalized_field(row.get(field_name), default) == default
            )
        )
        dashboard_insufficient = sum(
            1
            for row in dashboard_snapshot.tickers
            if _normalized_field(row.get(field_name), default) == default
        )
        adapter_insufficient = sum(
            1
            for decision in adapter_by_ticker.values()
            if _normalized_field(getattr(decision, field_name, None), default) == default
        )
        _print_row(
            "aggregate_field_flow",
            field_name,
            analysis_non_empty,
            json_non_empty,
            dashboard_non_empty,
            adapter_non_empty,
            analysis_insufficient,
            json_insufficient,
            dashboard_insufficient,
            adapter_insufficient,
        )

    _print_section("field_distribution")
    _print_row("field_distribution", "source", "field_name", "value", "count")
    for field_name, default in FIELD_SPECS:
        distributions = [
            ("analysis", _field_distribution(analysis_rows, field_name, default)),
            ("dashboard", _field_distribution(dashboard_snapshot.tickers, field_name, default)),
            ("adapter", _decision_distribution(adapter_by_ticker, field_name, default)),
        ]
        if json_rows is not None:
            distributions.insert(1, ("json", _field_distribution(json_rows, field_name, default)))
        for source_name, counts in distributions:
            for value, count in sorted(counts.items()):
                _print_row("field_distribution", source_name, field_name, value, count)

    _print_section("ticker_field_flow_examples")
    _print_row(
        "ticker_field_flow_examples",
        "ticker",
        "field_name",
        "analysis_value",
        "json_value",
        "dashboard_value",
        "adapter_value",
        "diagnosis",
    )
    for ticker in selected_tickers:
        analysis_row = analysis_by_ticker.get(ticker, {})
        json_row = json_by_ticker.get(ticker, {})
        dashboard_row = dashboard_by_ticker.get(ticker, {})
        adapter = adapter_by_ticker.get(ticker)
        for field_name, default in FIELD_SPECS:
            analysis_value = _normalized_field(analysis_row.get(field_name), default)
            json_value = _normalized_field(json_row.get(field_name), default)
            dashboard_value = _normalized_field(dashboard_row.get(field_name), default)
            adapter_value = _normalized_field(
                None if adapter is None else getattr(adapter, field_name, None),
                default,
            )
            diagnosis = _diagnosis_for_field(
                analysis_value=analysis_value,
                json_value=json_value,
                dashboard_value=dashboard_value,
                adapter_value=adapter_value,
                default=default,
            )
            _print_row(
                "ticker_field_flow_examples",
                ticker,
                field_name,
                analysis_value,
                json_value if json_rows is not None else "",
                dashboard_value,
                adapter_value,
                diagnosis,
            )

    _print_section("mapping_gap_hypothesis")
    _print_row("mapping_gap_hypothesis", "hypothesis", "status", "evidence")

    analysis_values_present_but_dashboard_missing = any(
        _is_semantic(analysis_by_ticker.get(ticker, {}).get("pullback_validity"), "INSUFFICIENT_DATA")
        and not _is_semantic(dashboard_by_ticker.get(ticker, {}).get("pullback_validity"), "INSUFFICIENT_DATA")
        for ticker in set(analysis_by_ticker) | set(dashboard_by_ticker)
    )
    analysis_values_present_but_dashboard_missing = any(
        any(
            _is_semantic(analysis_by_ticker.get(ticker, {}).get(field_name), default)
            and not _is_semantic(dashboard_by_ticker.get(ticker, {}).get(field_name), default)
            for field_name, default in FIELD_SPECS
        )
        for ticker in set(analysis_by_ticker) | set(dashboard_by_ticker)
    )
    if json_rows is None:
        json_values_present_but_dashboard_missing_status = "UNKNOWN"
        json_values_evidence = "json_not_provided"
    else:
        json_gap = any(
            any(
                _is_semantic(json_by_ticker.get(ticker, {}).get(field_name), default)
                and not _is_semantic(dashboard_by_ticker.get(ticker, {}).get(field_name), default)
                for field_name, default in FIELD_SPECS
            )
            for ticker in set(json_by_ticker) | set(dashboard_by_ticker)
        )
        json_values_present_but_dashboard_missing_status = "LIKELY" if json_gap else "UNLIKELY"
        json_values_evidence = (
            f"json_rows={len(json_rows)}|dashboard_rows={len(dashboard_snapshot.tickers)}"
        )

    adapter_values_present_but_not_persisted = any(
        any(
            _is_semantic(getattr(adapter_by_ticker.get(ticker), field_name, None), default)
            and not _is_semantic(dashboard_by_ticker.get(ticker, {}).get(field_name), default)
            for field_name, default in FIELD_SPECS
        )
        for ticker in set(adapter_by_ticker) | set(dashboard_by_ticker)
    )
    analysis_values_not_updated_after_adapter_fix = any(
        any(
            _is_semantic(getattr(adapter_by_ticker.get(ticker), field_name, None), default)
            and not _is_semantic(analysis_by_ticker.get(ticker, {}).get(field_name), default)
            for field_name, default in FIELD_SPECS
        )
        for ticker in set(adapter_by_ticker) | set(analysis_by_ticker)
    )
    persistence_gap_likely = analysis_values_present_but_dashboard_missing or (
        json_values_present_but_dashboard_missing_status == "LIKELY"
    )
    hypotheses = (
        (
            "ANALYSIS_VALUES_PRESENT_BUT_DASHBOARD_MISSING",
            "LIKELY" if analysis_values_present_but_dashboard_missing else "UNLIKELY",
            f"analysis_rows={len(analysis_rows)}|dashboard_rows={len(dashboard_snapshot.tickers)}",
        ),
        (
            "JSON_VALUES_PRESENT_BUT_DASHBOARD_MISSING",
            json_values_present_but_dashboard_missing_status,
            json_values_evidence,
        ),
        (
            "ADAPTER_VALUES_PRESENT_BUT_NOT_PERSISTED",
            "LIKELY" if adapter_values_present_but_not_persisted else "UNLIKELY",
            f"adapter_decisions={len(adapter_by_ticker)}|dashboard_rows={len(dashboard_snapshot.tickers)}",
        ),
        (
            "ANALYSIS_VALUES_NOT_UPDATED_AFTER_ADAPTER_FIX",
            "LIKELY" if analysis_values_not_updated_after_adapter_fix else "UNLIKELY",
            f"analysis_rows={len(analysis_rows)}|adapter_decisions={len(adapter_by_ticker)}",
        ),
        (
            "PERSISTENCE_MAPPING_GAP_LIKELY",
            "LIKELY" if persistence_gap_likely else "UNLIKELY",
            f"analysis_dashboard_gap={int(analysis_values_present_but_dashboard_missing)}|json_dashboard_gap={1 if json_values_present_but_dashboard_missing_status == 'LIKELY' else 0}",
        ),
    )
    for hypothesis_name, status, evidence in hypotheses:
        _print_row("mapping_gap_hypothesis", hypothesis_name, status, evidence)

    analysis_semantic_pullback = sum(
        1 for row in analysis_rows if _is_semantic(row.get("pullback_validity"), "INSUFFICIENT_DATA")
    )
    dashboard_insufficient_pullback = sum(
        1
        for row in dashboard_snapshot.tickers
        if _normalized_field(row.get("pullback_validity"), "INSUFFICIENT_DATA")
        == "INSUFFICIENT_DATA"
    )
    adapter_semantic_pullback = sum(
        1
        for decision in adapter_by_ticker.values()
        if _is_semantic(getattr(decision, "pullback_validity", None), "INSUFFICIENT_DATA")
    )

    _print_section("summary")
    _print_row("SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.status=OK")
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.report_date={args.report_date}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.analysis_rows={len(analysis_rows)}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.dashboard_tickers={len(dashboard_snapshot.tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.json_tickers="
        f"{'' if json_rows is None else len(json_rows)}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.examples={len(selected_tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.analysis_semantic_pullback="
        f"{analysis_semantic_pullback}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.dashboard_insufficient_pullback="
        f"{dashboard_insufficient_pullback}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.adapter_semantic_pullback="
        f"{adapter_semantic_pullback}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.persistence_gap_likely="
        f"{1 if persistence_gap_likely else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
