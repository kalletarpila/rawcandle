from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    build_decisions_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)
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
FIELD_NAMES = (
    "action",
    "primary_reason",
    "pullback_validity",
    "pullback_reason",
    "entry_readiness",
    "entry_readiness_reason",
    "candidate_priority",
    "candidate_priority_label",
    "candidate_priority_reason",
    "latest_bullish_signal_age_td",
    "latest_bearish_signal_age_td",
    "structure_warning_overrides_bullish_signal",
    "freshness_status",
    "ma_break_status",
    "rolling_5d_status",
    "rolling_2d_status",
    "daily_status",
    "pullback_days",
    "breakout_signal",
    "pullback_signal",
    "latest_bos_event_type",
    "latest_reset_reason",
    "distance_to_ema20",
    "distance_to_ema20_pct",
)
PULLBACK_DEFAULT = "INSUFFICIENT_DATA"
ENTRY_DEFAULT = "INSUFFICIENT_DATA"
CANDIDATE_DEFAULT = "MISSING"


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


def _snapshot_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


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


def _normalized_pullback(value: object) -> str:
    text = _cell(value)
    return text or PULLBACK_DEFAULT


def _normalized_entry(value: object) -> str:
    text = _cell(value)
    return text or ENTRY_DEFAULT


def _normalized_candidate_label(value: object) -> str:
    text = _cell(value)
    return text or CANDIDATE_DEFAULT


def _distribution(rows: Iterable[dict[str, object]], field_name: str, default: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        text = _cell(row.get(field_name))
        counts[text or default] += 1
    return counts


def _distribution_from_decisions(
    decisions_by_ticker: dict[str, object],
    field_name: str,
    default: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in decisions_by_ticker.values():
        text = _cell(getattr(decision, field_name, None))
        counts[text or default] += 1
    return counts


def _selected_tickers(
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    if explicit_tickers:
        selected: list[tuple[str, str]] = []
        for ticker in explicit_tickers:
            reports_row = reports_by_ticker.get(ticker)
            enrichment_row = enrichment_by_ticker.get(ticker)
            if reports_row is None or enrichment_row is None:
                continue
            selected.append((ticker, "EXPLICIT"))
        return selected[:max_examples]

    reasons: list[tuple[str, str, int]] = []
    common_tickers = sorted(set(reports_by_ticker) & set(enrichment_by_ticker))
    for ticker in common_tickers:
        reports_row = reports_by_ticker[ticker]
        enrichment_row = enrichment_by_ticker[ticker]
        reports_pullback = _normalized_pullback(reports_row.get("pullback_validity"))
        enrichment_pullback = _normalized_pullback(enrichment_row.get("pullback_validity"))
        reports_entry = _normalized_entry(reports_row.get("entry_readiness"))
        enrichment_entry = _normalized_entry(enrichment_row.get("entry_readiness"))
        reports_priority = _normalized_candidate_label(
            reports_row.get("candidate_priority_label")
        )
        enrichment_priority = _normalized_candidate_label(
            enrichment_row.get("candidate_priority_label")
        )
        if reports_pullback != enrichment_pullback:
            priority = (
                REPORT_PULLBACK_PRIORITY.index(reports_pullback)
                if reports_pullback in REPORT_PULLBACK_PRIORITY
                else len(REPORT_PULLBACK_PRIORITY)
            )
            reasons.append((ticker, "PULLBACK_MISMATCH", priority))
            continue
        if reports_entry != enrichment_entry:
            reasons.append((ticker, "ENTRY_READINESS_MISMATCH", 50))
            continue
        if reports_priority != enrichment_priority:
            reasons.append((ticker, "CANDIDATE_PRIORITY_MISMATCH", 60))
    reasons.sort(key=lambda item: (item[2], item[0]))
    return [(ticker, reason) for ticker, reason, _priority in reasons[:max_examples]]


def _analysis_value(
    field_name: str,
    enrichment_row: dict[str, object] | None,
    source_row: dict[str, object] | None,
) -> object:
    if source_row is not None and field_name in source_row:
        return source_row.get(field_name)
    if enrichment_row is not None and field_name in enrichment_row:
        return enrichment_row.get(field_name)
    if field_name == "distance_to_ema20" and source_row is not None:
        return source_row.get("distance_to_ema20")
    return None


def _adapter_rows_by_ticker(rows: list[dict[str, object]]) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = defaultdict(list)
    for row in build_dashboard_rows_from_ticker_enrichment_rows(rows):
        grouped[row.ticker.upper()].append(row)
    return grouped


def _adapter_decisions_by_ticker(rows: list[dict[str, object]]) -> dict[str, object]:
    result = build_decisions_from_ticker_enrichment_rows(rows)
    return {decision.ticker.upper(): decision for decision in result.decisions}


def _has_pullback_context(adapter_rows: list[object]) -> bool:
    for row in adapter_rows:
        raw_fields = row.raw_fields
        raw_values = " ".join(raw_fields.values()).lower()
        if any(term in raw_values for term in ("pullback_candidate", "early_pullback", "failed_pullback")):
            return True
        pullback_days = _safe_int(raw_fields.get("pullback_days"))
        if pullback_days is not None and pullback_days > 0:
            return True
    return False


def _has_fresh_bullish_signal(adapter_rows: list[object]) -> bool:
    return any(_cell(row.freshness_status).upper() == "FRESH_BULLISH_SIGNAL" for row in adapter_rows)


def _has_structure_override(adapter_rows: list[object]) -> bool:
    for row in adapter_rows:
        freshness = _cell(row.freshness_status).upper()
        latest_bos = _cell(row.latest_bos_event_type).upper()
        latest_reset = _cell(row.latest_reset_reason).upper()
        if freshness == "STRUCTURE_WARNING_OVERRIDES_BULLISH":
            return True
        if _safe_int(row.structure_warning_overrides_bullish_signal) == 1:
            return True
        if latest_bos == "BOS_DOWN":
            return True
        if "DOUBLE_BOS_DOWN" in latest_reset or ("RESET" in latest_reset and latest_reset):
            return True
    return False


def _has_ma_break(adapter_rows: list[object]) -> bool:
    return any(_cell(row.ma_break_status) for row in adapter_rows)


def _has_distance_to_ema20(adapter_rows: list[object]) -> bool:
    return any(row.distance_to_ema20 is not None for row in adapter_rows)


def _raw_fields_summary(adapter_rows: list[object], limit: int = 10) -> str:
    pairs: list[str] = []
    for row in adapter_rows:
        for key in sorted(row.raw_fields):
            value = _cell(row.raw_fields[key])
            pairs.append(f"{key}={value}")
            if len(pairs) >= limit:
                return "|".join(pairs)
    return "|".join(pairs)


def _decision_trace_reasons(decision: object | None) -> tuple[str, str]:
    if decision is None:
        return "", ""
    reasons = "|".join(decision.reasons[:5])
    blocking = "|".join(decision.blocking_reasons[:5])
    return reasons, blocking


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose reports vs enrichment parity gaps for pullback validity, "
            "entry readiness, and candidate priority."
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
        analysis_rows = load_ticker_enrichment_rows(
            analysis_db=args.analysis_db,
            signal_date=args.report_date,
            taxonomy_version=taxonomy_version,
        )
        source_by_ticker = _load_source_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
    analysis_by_ticker = _snapshot_ticker_map(analysis_rows)
    adapter_rows_by_ticker = _adapter_rows_by_ticker(analysis_rows)
    adapter_decisions = _adapter_decisions_by_ticker(analysis_rows)
    explicit_tickers = _parse_tickers(args.tickers)
    selected = _selected_tickers(
        reports_by_ticker,
        enrichment_by_ticker,
        explicit_tickers,
        args.max_examples,
    )

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

    _print_section("pullback_distribution")
    _print_row("pullback_distribution", "source", "pullback_validity", "count")
    for source_name, counts in (
        ("reports", _distribution(reports_snapshot.tickers, "pullback_validity", PULLBACK_DEFAULT)),
        ("enrichment", _distribution(enrichment_snapshot.tickers, "pullback_validity", PULLBACK_DEFAULT)),
        ("analysis_ticker_enrichment", _distribution(analysis_rows, "pullback_validity", PULLBACK_DEFAULT)),
        (
            "adapter_decision",
            _distribution_from_decisions(adapter_decisions, "pullback_validity", PULLBACK_DEFAULT),
        ),
    ):
        for value, count in sorted(counts.items()):
            _print_row("pullback_distribution", source_name, value, count)

    _print_section("entry_readiness_distribution")
    _print_row("entry_readiness_distribution", "source", "entry_readiness", "count")
    for source_name, counts in (
        ("reports", _distribution(reports_snapshot.tickers, "entry_readiness", ENTRY_DEFAULT)),
        ("enrichment", _distribution(enrichment_snapshot.tickers, "entry_readiness", ENTRY_DEFAULT)),
        ("analysis_ticker_enrichment", _distribution(analysis_rows, "entry_readiness", ENTRY_DEFAULT)),
        (
            "adapter_decision",
            _distribution_from_decisions(adapter_decisions, "entry_readiness", ENTRY_DEFAULT),
        ),
    ):
        for value, count in sorted(counts.items()):
            _print_row("entry_readiness_distribution", source_name, value, count)

    _print_section("candidate_priority_distribution")
    _print_row(
        "candidate_priority_distribution",
        "source",
        "candidate_priority_label",
        "count",
    )
    for source_name, counts in (
        (
            "reports",
            _distribution(reports_snapshot.tickers, "candidate_priority_label", CANDIDATE_DEFAULT),
        ),
        (
            "enrichment",
            _distribution(
                enrichment_snapshot.tickers,
                "candidate_priority_label",
                CANDIDATE_DEFAULT,
            ),
        ),
        (
            "analysis_ticker_enrichment",
            _distribution(analysis_rows, "candidate_priority_label", CANDIDATE_DEFAULT),
        ),
        (
            "adapter_decision",
            _distribution_from_decisions(
                adapter_decisions, "candidate_priority_label", CANDIDATE_DEFAULT
            ),
        ),
    ):
        for value, count in sorted(counts.items()):
            _print_row("candidate_priority_distribution", source_name, value, count)

    _print_section("selected_tickers")
    _print_row(
        "selected_tickers",
        "ticker",
        "selection_reason",
        "reports_action",
        "enrichment_action",
        "reports_pullback_validity",
        "enrichment_pullback_validity",
        "reports_entry_readiness",
        "enrichment_entry_readiness",
        "reports_candidate_priority_label",
        "enrichment_candidate_priority_label",
    )
    for ticker, reason in selected:
        reports_row = reports_by_ticker.get(ticker, {})
        enrichment_row = enrichment_by_ticker.get(ticker, {})
        _print_row(
            "selected_tickers",
            ticker,
            reason,
            reports_row.get("action"),
            enrichment_row.get("action"),
            _normalized_pullback(reports_row.get("pullback_validity")),
            _normalized_pullback(enrichment_row.get("pullback_validity")),
            _normalized_entry(reports_row.get("entry_readiness")),
            _normalized_entry(enrichment_row.get("entry_readiness")),
            _normalized_candidate_label(reports_row.get("candidate_priority_label")),
            _normalized_candidate_label(enrichment_row.get("candidate_priority_label")),
        )

    _print_section("field_comparison")
    _print_row(
        "field_comparison",
        "ticker",
        "field",
        "reports_value",
        "enrichment_value",
        "analysis_value",
        "adapter_value",
    )
    for ticker, _reason in selected:
        reports_row = reports_by_ticker.get(ticker)
        enrichment_row = enrichment_by_ticker.get(ticker)
        analysis_row = analysis_by_ticker.get(ticker)
        source_row = source_by_ticker.get(ticker)
        decision = adapter_decisions.get(ticker)
        for field_name in FIELD_NAMES:
            adapter_value = getattr(decision, field_name, None) if decision is not None else None
            _print_row(
                "field_comparison",
                ticker,
                field_name,
                None if reports_row is None else reports_row.get(field_name),
                None if enrichment_row is None else enrichment_row.get(field_name),
                _analysis_value(field_name, analysis_row, source_row),
                adapter_value,
            )

    _print_section("adapter_input_summary")
    _print_row(
        "adapter_input_summary",
        "ticker",
        "adapter_row_count",
        "horizons_present",
        "has_pullback_context",
        "has_fresh_bullish_signal",
        "has_structure_override",
        "has_ma_break",
        "has_distance_to_ema20",
        "raw_fields_summary",
    )
    ticker_diagnoses: dict[str, dict[str, str]] = {}
    for ticker, _reason in selected:
        adapter_rows = adapter_rows_by_ticker.get(ticker, [])
        has_pullback_context = _has_pullback_context(adapter_rows)
        has_fresh_signal = _has_fresh_bullish_signal(adapter_rows)
        has_structure_override = _has_structure_override(adapter_rows)
        has_ma_break = _has_ma_break(adapter_rows)
        has_distance = _has_distance_to_ema20(adapter_rows)
        horizons_present = "|".join(sorted({_cell(row.horizon) for row in adapter_rows if _cell(row.horizon)}))
        _print_row(
            "adapter_input_summary",
            ticker,
            len(adapter_rows),
            horizons_present,
            int(has_pullback_context),
            int(has_fresh_signal),
            int(has_structure_override),
            int(has_ma_break),
            int(has_distance),
            _raw_fields_summary(adapter_rows),
        )

        reports_row = reports_by_ticker.get(ticker, {})
        reports_pullback = _normalized_pullback(reports_row.get("pullback_validity"))
        decision = adapter_decisions.get(ticker)
        adapter_pullback = _normalized_pullback(
            None if decision is None else decision.pullback_validity
        )
        source_row = source_by_ticker.get(ticker, {})
        source_has_pullback_field = (
            _safe_int(source_row.get("pullback_signal")) == 1
            or (_safe_int(source_row.get("pullback_days")) or 0) > 0
            or _safe_int(source_row.get("breakout_signal")) == 1
        )
        ticker_diagnoses[ticker] = {
            "MISSING_PULLBACK_CONTEXT": (
                "LIKELY"
                if reports_pullback not in {"NO_PULLBACK", "INSUFFICIENT_DATA"} and not has_pullback_context
                else "UNLIKELY"
            ),
            "MISSING_FRESH_BULLISH_SIGNAL": (
                "LIKELY"
                if reports_pullback in {"VALID_PULLBACK", "EARLY_PULLBACK"} and not has_fresh_signal
                else "UNLIKELY"
            ),
            "MISSING_STRUCTURE_OVERRIDE": (
                "LIKELY"
                if reports_pullback == "STRUCTURE_BLOCKED_PULLBACK" and not has_structure_override
                else "UNLIKELY"
            ),
            "MISSING_MA_BREAK_INPUT": (
                "LIKELY"
                if reports_pullback == "BREAKDOWN_NOT_PULLBACK" and not has_ma_break
                else "UNLIKELY"
            ),
            "ADAPTER_RETURNS_INSUFFICIENT_DATA": (
                "LIKELY"
                if adapter_pullback == "INSUFFICIENT_DATA"
                or _normalized_entry(None if decision is None else decision.entry_readiness)
                == "INSUFFICIENT_DATA"
                else "UNLIKELY"
            ),
            "SOURCE_FIELDS_EXIST_BUT_NOT_MAPPED": (
                "LIKELY" if source_has_pullback_field and not has_pullback_context else "UNLIKELY"
            ),
        }

    _print_section("adapter_decision_summary")
    _print_row(
        "adapter_decision_summary",
        "ticker",
        "action",
        "pullback_validity",
        "entry_readiness",
        "candidate_priority",
        "candidate_priority_label",
        "decision_trace_count",
        "reasons",
        "blocking_reasons",
    )
    for ticker, _reason in selected:
        decision = adapter_decisions.get(ticker)
        reasons, blocking = _decision_trace_reasons(decision)
        _print_row(
            "adapter_decision_summary",
            ticker,
            None if decision is None else decision.action,
            None if decision is None else decision.pullback_validity,
            None if decision is None else decision.entry_readiness,
            None if decision is None else decision.candidate_priority,
            None if decision is None else decision.candidate_priority_label,
            0 if decision is None else len(decision.decision_trace),
            reasons,
            blocking,
        )

    _print_section("missing_input_diagnosis")
    _print_row("missing_input_diagnosis", "ticker", "diagnosis", "status", "evidence")
    for ticker, _reason in selected:
        reports_row = reports_by_ticker.get(ticker, {})
        source_row = source_by_ticker.get(ticker, {})
        evidence_map = {
            "MISSING_PULLBACK_CONTEXT": (
                f"reports_pullback={_normalized_pullback(reports_row.get('pullback_validity'))}"
                f"|pullback_signal={_cell(source_row.get('pullback_signal'))}"
                f"|pullback_days={_cell(source_row.get('pullback_days'))}"
            ),
            "MISSING_FRESH_BULLISH_SIGNAL": (
                f"reports_pullback={_normalized_pullback(reports_row.get('pullback_validity'))}"
                f"|freshness_status={_cell(source_row.get('freshness_status'))}"
                f"|latest_bullish_signal_age_td={_cell(source_row.get('latest_bullish_signal_age_td'))}"
            ),
            "MISSING_STRUCTURE_OVERRIDE": (
                f"reports_pullback={_normalized_pullback(reports_row.get('pullback_validity'))}"
                f"|latest_bos_event_type={_cell(source_row.get('latest_bos_event_type'))}"
                f"|latest_reset_reason={_cell(source_row.get('latest_reset_reason'))}"
            ),
            "MISSING_MA_BREAK_INPUT": (
                f"reports_pullback={_normalized_pullback(reports_row.get('pullback_validity'))}"
                f"|ma_break_status={_cell(source_row.get('ma_break_status'))}"
                f"|distance_to_ema20_pct={_cell(source_row.get('distance_to_ema20_pct'))}"
            ),
            "ADAPTER_RETURNS_INSUFFICIENT_DATA": (
                f"adapter_pullback={_cell(getattr(adapter_decisions.get(ticker), 'pullback_validity', None))}"
                f"|adapter_entry={_cell(getattr(adapter_decisions.get(ticker), 'entry_readiness', None))}"
            ),
        }
        for diagnosis_name in (
            "MISSING_PULLBACK_CONTEXT",
            "MISSING_FRESH_BULLISH_SIGNAL",
            "MISSING_STRUCTURE_OVERRIDE",
            "MISSING_MA_BREAK_INPUT",
            "ADAPTER_RETURNS_INSUFFICIENT_DATA",
        ):
            _print_row(
                "missing_input_diagnosis",
                ticker,
                diagnosis_name,
                ticker_diagnoses[ticker][diagnosis_name],
                evidence_map[diagnosis_name],
            )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    selected_count = max(len(selected), 1)
    missing_pullback_context_count = sum(
        1
        for ticker, _reason in selected
        if ticker_diagnoses[ticker]["MISSING_PULLBACK_CONTEXT"] == "LIKELY"
    )
    missing_fresh_bullish_count = sum(
        1
        for ticker, _reason in selected
        if ticker_diagnoses[ticker]["MISSING_FRESH_BULLISH_SIGNAL"] == "LIKELY"
    )
    missing_blocker_count = sum(
        1
        for ticker, _reason in selected
        if ticker_diagnoses[ticker]["MISSING_STRUCTURE_OVERRIDE"] == "LIKELY"
        or ticker_diagnoses[ticker]["MISSING_MA_BREAK_INPUT"] == "LIKELY"
    )
    adapter_insufficient_count = sum(
        1
        for ticker, _reason in selected
        if ticker_diagnoses[ticker]["ADAPTER_RETURNS_INSUFFICIENT_DATA"] == "LIKELY"
    )
    source_not_mapped_count = sum(
        1
        for ticker, _reason in selected
        if ticker_diagnoses[ticker]["SOURCE_FIELDS_EXIST_BUT_NOT_MAPPED"] == "LIKELY"
    )
    hypotheses = {
        "ENRICHMENT_LACKS_PULLBACK_CONTEXT": (
            "LIKELY" if missing_pullback_context_count * 2 >= selected_count else "UNLIKELY",
            f"selected={len(selected)}|missing_pullback_context={missing_pullback_context_count}",
        ),
        "ENRICHMENT_LACKS_BULLISH_SIGNAL_FRESHNESS": (
            "LIKELY" if missing_fresh_bullish_count * 2 >= selected_count else "UNLIKELY",
            f"selected={len(selected)}|missing_fresh_bullish_signal={missing_fresh_bullish_count}",
        ),
        "ENRICHMENT_LACKS_PULLBACK_BLOCKER_CONTEXT": (
            "LIKELY" if missing_blocker_count * 2 >= selected_count else "UNLIKELY",
            f"selected={len(selected)}|missing_blocker_context={missing_blocker_count}",
        ),
        "ADAPTER_OUTPUT_MATCHES_ENRICHMENT_INSUFFICIENT": (
            "LIKELY" if adapter_insufficient_count * 2 >= selected_count else "UNLIKELY",
            f"selected={len(selected)}|adapter_insufficient={adapter_insufficient_count}",
        ),
        "SOURCE_FIELDS_EXIST_BUT_NOT_MAPPED": (
            "LIKELY" if source_not_mapped_count * 2 >= selected_count else "UNLIKELY",
            f"selected={len(selected)}|source_fields_exist_but_not_mapped={source_not_mapped_count}",
        ),
    }
    for hypothesis_name, (status, evidence) in hypotheses.items():
        _print_row("hypothesis_summary", hypothesis_name, status, evidence)

    reports_non_insufficient_pullback = sum(
        1
        for row in reports_snapshot.tickers
        if _normalized_pullback(row.get("pullback_validity")) != "INSUFFICIENT_DATA"
    )
    enrichment_insufficient_pullback = sum(
        1
        for row in enrichment_snapshot.tickers
        if _normalized_pullback(row.get("pullback_validity")) == "INSUFFICIENT_DATA"
    )
    reports_non_insufficient_entry = sum(
        1
        for row in reports_snapshot.tickers
        if _normalized_entry(row.get("entry_readiness")) != "INSUFFICIENT_DATA"
    )
    enrichment_insufficient_entry = sum(
        1
        for row in enrichment_snapshot.tickers
        if _normalized_entry(row.get("entry_readiness")) == "INSUFFICIENT_DATA"
    )

    _print_section("summary")
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.status=OK"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.report_date={args.report_date}"
    )
    _print_row(
        f"SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.selected_tickers={len(selected)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.reports_non_insufficient_pullback="
        f"{reports_non_insufficient_pullback}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.enrichment_insufficient_pullback="
        f"{enrichment_insufficient_pullback}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.reports_non_insufficient_entry="
        f"{reports_non_insufficient_entry}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.enrichment_insufficient_entry="
        f"{enrichment_insufficient_entry}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.missing_pullback_context="
        f"{missing_pullback_context_count}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.missing_fresh_bullish_signal="
        f"{missing_fresh_bullish_count}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.source_fields_exist_but_not_mapped="
        f"{source_not_mapped_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
