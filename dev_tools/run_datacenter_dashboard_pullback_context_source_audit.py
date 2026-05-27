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
    "NO_PULLBACK",
)
PULLBACK_DEFAULT = "INSUFFICIENT_DATA"
ENTRY_DEFAULT = "INSUFFICIENT_DATA"
CANDIDATE_DEFAULT = "MISSING"
DETAIL_FIELDS = (
    "pullback_validity",
    "pullback_reason",
    "entry_readiness",
    "entry_readiness_reason",
    "candidate_priority",
    "candidate_priority_label",
    "candidate_priority_reason",
    "action",
    "primary_reason",
)
SOURCE_FIELDS = (
    "pullback_signal",
    "pullback_days",
    "breakout_signal",
    "bullish_candle_signal",
    "bullish_divergence_signal",
    "hidden_bullish_divergence_signal",
    "latest_bullish_signal_age_td",
    "latest_bearish_signal_age_td",
    "freshness_status",
    "latest_structure_freshness",
    "latest_bos_freshness",
    "latest_reset_freshness",
    "structure_warning_overrides_bullish_signal",
    "ma_break_status",
    "rolling_5d_status",
    "rolling_2d_status",
    "daily_status",
    "latest_bos_event_type",
    "latest_reset_reason",
    "distance_to_ema20",
    "distance_to_ema20_pct",
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
        columns = _table_columns(conn, SOURCE_TABLE)
        if "taxonomy_version" in columns:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {SOURCE_TABLE}
                WHERE signal_date = ? AND taxonomy_version = ?
                ORDER BY ticker ASC
                """,
                (report_date, taxonomy_version),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {SOURCE_TABLE}
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


def _normalized_pullback(value: object) -> str:
    return _normalized_text(value, PULLBACK_DEFAULT)


def _normalized_entry(value: object) -> str:
    return _normalized_text(value, ENTRY_DEFAULT)


def _normalized_candidate(value: object) -> str:
    return _normalized_text(value, CANDIDATE_DEFAULT)


def _bool_text(value: bool) -> str:
    return "1" if value else "0"


def _rows_by_ticker(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            grouped[ticker].append(row)
    return grouped


def _adapter_rows_by_ticker(rows: list[dict[str, object]]) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = defaultdict(list)
    for row in build_dashboard_rows_from_ticker_enrichment_rows(rows):
        grouped[row.ticker.upper()].append(row)
    return grouped


def _adapter_decisions_by_ticker(rows: list[dict[str, object]]) -> dict[str, object]:
    result = build_decisions_from_ticker_enrichment_rows(rows)
    return {decision.ticker.upper(): decision for decision in result.decisions}


def _has_pullback_context_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    if _normalized_pullback(row.get("pullback_validity")) in {
        "VALID_PULLBACK",
        "EARLY_PULLBACK",
        "STRUCTURE_BLOCKED_PULLBACK",
        "BREAKDOWN_NOT_PULLBACK",
    }:
        return True
    if _safe_int(row.get("pullback_signal")) == 1:
        return True
    pullback_days = _safe_int(row.get("pullback_days"))
    if pullback_days is not None and pullback_days > 0:
        return True
    combined = " ".join(
        _normalized_text(row.get(field_name))
        for field_name in ("pullback_reason", "rolling_5d_status", "rolling_2d_status", "daily_status")
    ).lower()
    return any(term in combined for term in ("pullback", "failed_pullback", "breakdown"))


def _has_fresh_bullish_signal_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    freshness = _normalized_text(row.get("freshness_status")).upper()
    return freshness == "FRESH_BULLISH_SIGNAL"


def _has_structure_override_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    if _safe_int(row.get("structure_warning_overrides_bullish_signal")) == 1:
        return True
    if _normalized_text(row.get("latest_bos_event_type")).upper() == "BOS_DOWN":
        return True
    latest_reset = _normalized_text(row.get("latest_reset_reason")).upper()
    return "DOUBLE_BOS_DOWN" in latest_reset


def _has_ma_break_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    return bool(_normalized_text(row.get("ma_break_status")))


def _has_pullback_days_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    pullback_days = _safe_int(row.get("pullback_days"))
    return pullback_days is not None and pullback_days > 0


def _has_bullish_signal_age_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    return _safe_int(row.get("latest_bullish_signal_age_td")) is not None


def _has_distance_to_ema20_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    return bool(_normalized_text(row.get("distance_to_ema20")) or _normalized_text(row.get("distance_to_ema20_pct")))


def _has_rolling_5d_context_row(row: dict[str, object] | None) -> bool:
    if not row:
        return False
    return bool(_normalized_text(row.get("rolling_5d_status")))


def _has_pullback_context_adapter(adapter_rows: list[object]) -> bool:
    for row in adapter_rows:
        raw_values = " ".join(row.raw_fields.values()).lower()
        if any(
            term in raw_values for term in ("pullback_candidate", "early_pullback", "failed_pullback")
        ):
            return True
        pullback_days = _safe_int(row.raw_fields.get("pullback_days"))
        if pullback_days is not None and pullback_days > 0:
            return True
        if _normalized_text(row.raw_fields.get("pullback_signal")) == "1":
            return True
    return False


def _has_fresh_bullish_signal_adapter(adapter_rows: list[object]) -> bool:
    return any(_normalized_text(row.freshness_status).upper() == "FRESH_BULLISH_SIGNAL" for row in adapter_rows)


def _has_bullish_signal_age_adapter(adapter_rows: list[object]) -> bool:
    return any(row.latest_bullish_signal_age_td is not None for row in adapter_rows)


def _has_structure_override_adapter(adapter_rows: list[object]) -> bool:
    for row in adapter_rows:
        if _safe_int(row.structure_warning_overrides_bullish_signal) == 1:
            return True
        if _normalized_text(row.latest_bos_event_type).upper() == "BOS_DOWN":
            return True
        latest_reset = _normalized_text(row.latest_reset_reason).upper()
        if "DOUBLE_BOS_DOWN" in latest_reset:
            return True
    return False


def _has_ma_break_adapter(adapter_rows: list[object]) -> bool:
    return any(bool(_normalized_text(row.ma_break_status)) for row in adapter_rows)


def _has_distance_to_ema20_adapter(adapter_rows: list[object]) -> bool:
    for row in adapter_rows:
        if row.distance_to_ema20 is not None:
            return True
        if _normalized_text(row.raw_fields.get("distance_to_ema20_pct")):
            return True
    return False


def _raw_fields_summary(adapter_rows: list[object], limit: int = 12) -> str:
    pairs: list[str] = []
    for row in adapter_rows:
        for key in sorted(row.raw_fields):
            pairs.append(f"{key}={_cell(row.raw_fields[key])}")
            if len(pairs) >= limit:
                return "|".join(pairs)
    return "|".join(pairs)


def _selected_tickers(
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    common = set(reports_by_ticker) & set(enrichment_by_ticker)
    if explicit_tickers:
        return [(ticker, "EXPLICIT") for ticker in explicit_tickers if ticker in common][:max_examples]

    weighted: list[tuple[int, str, str]] = []
    for ticker in sorted(common):
        reports_pullback = _normalized_pullback(reports_by_ticker[ticker].get("pullback_validity"))
        enrichment_pullback = _normalized_pullback(
            enrichment_by_ticker[ticker].get("pullback_validity")
        )
        if reports_pullback == enrichment_pullback:
            continue
        if reports_pullback not in REPORT_PULLBACK_PRIORITY:
            continue
        priority = REPORT_PULLBACK_PRIORITY.index(reports_pullback)
        weighted.append((priority, ticker, "PULLBACK_MISMATCH"))
    weighted.sort(key=lambda item: (item[0], item[1]))
    return [(ticker, reason) for _priority, ticker, reason in weighted[:max_examples]]


def _analysis_value(
    field_name: str,
    enrichment_row: dict[str, object] | None,
    source_row: dict[str, object] | None,
) -> object:
    if enrichment_row is not None and field_name in enrichment_row:
        return enrichment_row.get(field_name)
    if source_row is not None and field_name in source_row:
        return source_row.get(field_name)
    return None


def _pullback_distribution(rows: Iterable[dict[str, object]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[_normalized_pullback(row.get("pullback_validity"))] += 1
    return counts


def _pullback_distribution_from_decisions(decisions_by_ticker: dict[str, object]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for decision in decisions_by_ticker.values():
        counts[_normalized_pullback(getattr(decision, "pullback_validity", None))] += 1
    return counts


def _count_rows(rows: Iterable[dict[str, object]], predicate) -> int:
    return sum(1 for row in rows if predicate(row))


def _count_adapter(adapter_rows_by_ticker: dict[str, list[object]], predicate) -> int:
    return sum(1 for rows in adapter_rows_by_ticker.values() if predicate(rows))


def _hypothesis_status(count: int, threshold: int = 1) -> str:
    return "LIKELY" if count >= threshold else "UNLIKELY"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit for why reports-mode has richer pullback context "
            "than enrichment-mode."
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
        source_by_ticker = _load_source_rows(args.analysis_db, args.report_date, taxonomy_version)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
    analysis_by_ticker = _snapshot_ticker_map(analysis_rows)
    adapter_rows = _adapter_rows_by_ticker(analysis_rows)
    adapter_decisions = _adapter_decisions_by_ticker(analysis_rows)
    selected = _selected_tickers(
        reports_by_ticker,
        enrichment_by_ticker,
        _parse_tickers(args.tickers),
        args.max_examples,
    )
    common_tickers = sorted(set(reports_by_ticker) & set(enrichment_by_ticker))

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

    reports_pullback_counts = _pullback_distribution(reports_snapshot.tickers)
    enrichment_pullback_counts = _pullback_distribution(enrichment_snapshot.tickers)
    analysis_pullback_counts = _pullback_distribution(analysis_rows)
    adapter_pullback_counts = _pullback_distribution_from_decisions(adapter_decisions)

    _print_section("pullback_context_counts")
    _print_row(
        "pullback_context_counts",
        "metric",
        "reports_value",
        "enrichment_value",
        "analysis_value",
        "adapter_value",
    )
    for label in (
        ("valid_pullback", "VALID_PULLBACK"),
        ("early_pullback", "EARLY_PULLBACK"),
        ("structure_blocked_pullback", "STRUCTURE_BLOCKED_PULLBACK"),
        ("breakdown_not_pullback", "BREAKDOWN_NOT_PULLBACK"),
        ("no_pullback", "NO_PULLBACK"),
        ("insufficient_data", PULLBACK_DEFAULT),
    ):
        metric_name, pullback_name = label
        _print_row(
            "pullback_context_counts",
            metric_name,
            reports_pullback_counts.get(pullback_name, 0),
            enrichment_pullback_counts.get(pullback_name, 0),
            analysis_pullback_counts.get(pullback_name, 0),
            adapter_pullback_counts.get(pullback_name, 0),
        )
    _print_row(
        "pullback_context_counts",
        "pullback_context_present",
        _count_rows(reports_snapshot.tickers, _has_pullback_context_row),
        _count_rows(enrichment_snapshot.tickers, _has_pullback_context_row),
        _count_rows(analysis_rows, _has_pullback_context_row),
        _count_adapter(adapter_rows, _has_pullback_context_adapter),
    )
    _print_row(
        "pullback_context_counts",
        "fresh_bullish_signal_present",
        _count_rows(reports_snapshot.tickers, _has_fresh_bullish_signal_row),
        _count_rows(enrichment_snapshot.tickers, _has_fresh_bullish_signal_row),
        _count_rows(analysis_rows, _has_fresh_bullish_signal_row),
        _count_adapter(adapter_rows, _has_fresh_bullish_signal_adapter),
    )
    _print_row(
        "pullback_context_counts",
        "structure_override_present",
        _count_rows(reports_snapshot.tickers, _has_structure_override_row),
        _count_rows(enrichment_snapshot.tickers, _has_structure_override_row),
        _count_rows(analysis_rows, _has_structure_override_row),
        _count_adapter(adapter_rows, _has_structure_override_adapter),
    )
    _print_row(
        "pullback_context_counts",
        "ma_break_present",
        _count_rows(reports_snapshot.tickers, _has_ma_break_row),
        _count_rows(enrichment_snapshot.tickers, _has_ma_break_row),
        _count_rows(analysis_rows, _has_ma_break_row),
        _count_adapter(adapter_rows, _has_ma_break_adapter),
    )
    _print_row(
        "pullback_context_counts",
        "pullback_days_present",
        _count_rows(reports_snapshot.tickers, _has_pullback_days_row),
        _count_rows(enrichment_snapshot.tickers, _has_pullback_days_row),
        _count_rows(analysis_rows, _has_pullback_days_row),
        sum(
            1
            for rows in adapter_rows.values()
            if any((_safe_int(row.raw_fields.get("pullback_days")) or 0) > 0 for row in rows)
        ),
    )

    _print_section("selected_tickers")
    _print_row(
        "selected_tickers",
        "ticker",
        "selection_reason",
        "reports_pullback_validity",
        "enrichment_pullback_validity",
        "reports_entry_readiness",
        "enrichment_entry_readiness",
        "reports_candidate_priority_label",
        "enrichment_candidate_priority_label",
    )
    for ticker, reason in selected:
        reports_row = reports_by_ticker[ticker]
        enrichment_row = enrichment_by_ticker[ticker]
        _print_row(
            "selected_tickers",
            ticker,
            reason,
            reports_row.get("pullback_validity"),
            enrichment_row.get("pullback_validity"),
            reports_row.get("entry_readiness"),
            enrichment_row.get("entry_readiness"),
            reports_row.get("candidate_priority_label"),
            enrichment_row.get("candidate_priority_label"),
        )

    _print_section("reports_vs_enrichment_pullback")
    _print_row(
        "reports_vs_enrichment_pullback",
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
        adapter_decision = adapter_decisions.get(ticker)
        for field_name in DETAIL_FIELDS:
            _print_row(
                "reports_vs_enrichment_pullback",
                ticker,
                field_name,
                None if reports_row is None else reports_row.get(field_name),
                None if enrichment_row is None else enrichment_row.get(field_name),
                _analysis_value(field_name, analysis_row, source_row),
                None if adapter_decision is None else getattr(adapter_decision, field_name, None),
            )

    _print_section("source_field_presence")
    _print_row(
        "source_field_presence",
        "ticker",
        "field_name",
        "source_value",
        "analysis_enrichment_value",
        "reports_value",
        "enrichment_value",
    )
    for ticker, _reason in selected:
        reports_row = reports_by_ticker.get(ticker, {})
        enrichment_row = enrichment_by_ticker.get(ticker, {})
        analysis_row = analysis_by_ticker.get(ticker, {})
        source_row = source_by_ticker.get(ticker, {})
        for field_name in SOURCE_FIELDS:
            _print_row(
                "source_field_presence",
                ticker,
                field_name,
                source_row.get(field_name),
                analysis_row.get(field_name),
                reports_row.get(field_name),
                enrichment_row.get(field_name),
            )

    _print_section("adapter_pullback_inputs")
    _print_row(
        "adapter_pullback_inputs",
        "ticker",
        "adapter_row_count",
        "horizons_present",
        "has_pullback_context",
        "has_pullback_days",
        "has_fresh_bullish_signal",
        "has_bullish_signal_age",
        "has_structure_override",
        "has_ma_break",
        "has_distance_to_ema20",
        "raw_fields_summary",
    )
    for ticker, _reason in selected:
        rows = adapter_rows.get(ticker, [])
        _print_row(
            "adapter_pullback_inputs",
            ticker,
            len(rows),
            "|".join(sorted({row.horizon for row in rows})),
            _bool_text(_has_pullback_context_adapter(rows)),
            _bool_text(any((_safe_int(row.raw_fields.get("pullback_days")) or 0) > 0 for row in rows)),
            _bool_text(_has_fresh_bullish_signal_adapter(rows)),
            _bool_text(_has_bullish_signal_age_adapter(rows)),
            _bool_text(_has_structure_override_adapter(rows)),
            _bool_text(_has_ma_break_adapter(rows)),
            _bool_text(_has_distance_to_ema20_adapter(rows)),
            _raw_fields_summary(rows),
        )

    _print_section("gap_group_distribution")
    _print_row(
        "gap_group_distribution",
        "reports_pullback_validity",
        "enrichment_pullback_validity",
        "count",
    )
    gap_counts: Counter[tuple[str, str]] = Counter()
    for ticker in common_tickers:
        gap_counts[
            (
                _normalized_pullback(reports_by_ticker[ticker].get("pullback_validity")),
                _normalized_pullback(enrichment_by_ticker[ticker].get("pullback_validity")),
            )
        ] += 1
    for (reports_pullback, enrichment_pullback), count in sorted(gap_counts.items()):
        _print_row(
            "gap_group_distribution",
            reports_pullback,
            enrichment_pullback,
            count,
        )

    missing_pullback_days = 0
    missing_bullish_signal_age = 0
    missing_rolling_5d_context = 0
    missing_distance_to_ema20 = 0
    missing_structure_override = 0
    source_has_pullback_not_mapped = 0
    for ticker, _reason in selected:
        reports_row = reports_by_ticker[ticker]
        analysis_row = analysis_by_ticker.get(ticker)
        source_row = source_by_ticker.get(ticker)
        adapter_rows_for_ticker = adapter_rows.get(ticker, [])
        reports_pullback = _normalized_pullback(reports_row.get("pullback_validity"))
        if reports_pullback in {"VALID_PULLBACK", "EARLY_PULLBACK"}:
            source_has_days = _has_pullback_days_row(source_row)
            analysis_has_days = _has_pullback_days_row(analysis_row)
            if not source_has_days and not analysis_has_days:
                missing_pullback_days += 1
            if not (_has_bullish_signal_age_row(source_row) or _has_bullish_signal_age_row(analysis_row)):
                missing_bullish_signal_age += 1
            if not (_has_rolling_5d_context_row(source_row) or _has_rolling_5d_context_row(analysis_row)):
                missing_rolling_5d_context += 1
            if not (_has_distance_to_ema20_row(source_row) or _has_distance_to_ema20_row(analysis_row)):
                missing_distance_to_ema20 += 1
        if reports_pullback == "STRUCTURE_BLOCKED_PULLBACK":
            if not (_has_structure_override_row(source_row) or _has_structure_override_row(analysis_row)):
                missing_structure_override += 1
        source_has_pullback_fields = any(
            (
                _safe_int(None if source_row is None else source_row.get("pullback_signal")) == 1,
                _has_pullback_days_row(source_row),
                _has_bullish_signal_age_row(source_row),
                _has_distance_to_ema20_row(source_row),
            )
        )
        if source_has_pullback_fields and (
            not _has_pullback_context_row(analysis_row)
            or not _has_pullback_context_adapter(adapter_rows_for_ticker)
        ):
            source_has_pullback_not_mapped += 1

    needs_rolling_pullback_status = int(
        len(selected) > 0
        and (missing_rolling_5d_context + missing_pullback_days) >= max(1, len(selected) // 2)
    )

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "REPORTS_PULLBACK_USES_ROLLING_5D_CONTEXT",
        _hypothesis_status(missing_rolling_5d_context),
        f"selected={len(selected)}|missing_rolling_5d_context={missing_rolling_5d_context}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_MISSING_PULLBACK_DAYS",
        _hypothesis_status(missing_pullback_days),
        f"selected={len(selected)}|missing_pullback_days={missing_pullback_days}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_MISSING_BULLISH_SIGNAL_AGE",
        _hypothesis_status(missing_bullish_signal_age),
        f"selected={len(selected)}|missing_bullish_signal_age={missing_bullish_signal_age}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_MISSING_DISTANCE_TO_EMA20",
        _hypothesis_status(missing_distance_to_ema20),
        f"selected={len(selected)}|missing_distance_to_ema20={missing_distance_to_ema20}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_MISSING_STRUCTURE_OVERRIDE",
        _hypothesis_status(missing_structure_override),
        f"selected={len(selected)}|missing_structure_override={missing_structure_override}",
    )
    _print_row(
        "hypothesis_summary",
        "SOURCE_HAS_PULLBACK_FIELDS_NOT_MAPPED",
        _hypothesis_status(source_has_pullback_not_mapped),
        f"selected={len(selected)}|source_has_pullback_fields_not_mapped={source_has_pullback_not_mapped}",
    )
    _print_row(
        "hypothesis_summary",
        "NEEDS_ROLLING_PULLBACK_STATUS_ENRICHMENT",
        "LIKELY" if needs_rolling_pullback_status == 1 else "UNLIKELY",
        f"selected={len(selected)}|needs_rolling_pullback_status={needs_rolling_pullback_status}",
    )

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_pullback_context_source_audit.status=OK")
    print(f"SUMMARY datacenter_dashboard_pullback_context_source_audit.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_pullback_context_source_audit.selected_tickers={len(selected)}")
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.reports_valid_pullback="
        f"{reports_pullback_counts.get('VALID_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.reports_early_pullback="
        f"{reports_pullback_counts.get('EARLY_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.reports_structure_blocked="
        f"{reports_pullback_counts.get('STRUCTURE_BLOCKED_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.reports_breakdown_not_pullback="
        f"{reports_pullback_counts.get('BREAKDOWN_NOT_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.enrichment_valid_pullback="
        f"{enrichment_pullback_counts.get('VALID_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.enrichment_early_pullback="
        f"{enrichment_pullback_counts.get('EARLY_PULLBACK', 0)}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.missing_pullback_days="
        f"{missing_pullback_days}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.missing_bullish_signal_age="
        f"{missing_bullish_signal_age}"
    )
    print(
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.needs_rolling_pullback_status="
        f"{needs_rolling_pullback_status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
