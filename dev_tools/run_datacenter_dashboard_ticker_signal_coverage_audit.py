from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path


SOURCE_TABLE = "dc_ticker_swing_signal_daily"
ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$")
DISALLOWED_TICKER_LABELS = {
    "LAYER",
    "SUBINDUSTRY",
    "ECOSYSTEM",
    "HEADER",
    "WATCHLIST",
    "MARKET",
    "ACTION",
    "SUMMARY",
    "DECISION",
    "TRACE",
}
NEUTRAL_LIKE_VALUES = {"", "NEUTRAL", "NEUTRAL_MONITOR", "OK", "INFO", "READY"}
FIELD_SPECS: tuple[tuple[str, str | None], ...] = (
    ("breakout_signal", None),
    ("pullback_signal", None),
    ("exit_risk_signal", None),
    ("exit_risk_severity", None),
    ("exit_reason", None),
    ("price_data_status", "data_quality_status"),
    ("ticker_trend_state", "trend_state"),
    ("latest_structure_label", None),
    ("latest_structure_freshness", None),
    ("latest_bos_event_type", None),
    ("latest_bos_freshness", None),
    ("latest_reset_reason", None),
    ("latest_reset_freshness", None),
    ("bullish_candle_signal", None),
    ("bullish_divergence_signal", None),
    ("hidden_bullish_divergence_signal", None),
    ("ma_break_status", None),
    ("freshness_status", None),
    ("daily_status", None),
    ("rolling_2d_status", None),
    ("rolling_5d_status", None),
    ("rolling_30d_status", None),
    ("current_status", None),
    ("action", None),
)
SOURCE_DISTRIBUTION_FIELDS: tuple[str, ...] = (
    "exit_risk_severity",
    "exit_risk_signal",
    "breakout_signal",
    "pullback_signal",
    "price_data_status",
    "ticker_trend_state",
    "latest_bos_event_type",
    "latest_reset_reason",
)
ENRICHMENT_DISTRIBUTION_FIELDS: tuple[str, ...] = (
    "action",
    "current_status",
    "ma_break_status",
    "freshness_status",
    "trend_state",
    "latest_bos_event_type",
    "latest_reset_reason",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace(";", ",").replace("\n", " ").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"analysis_db not found: {db_path}")
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


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_non_empty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_truthy_signal(value: object) -> bool:
    text = _normalized_text(value)
    if text is None:
        return False
    if text in {"0", "0.0", "FALSE", "false"}:
        return False
    return True


def _is_valid_ticker(value: object) -> bool:
    ticker = _normalized_text(value)
    if ticker is None:
        return False
    normalized = ticker.upper()
    if DATE_RE.match(normalized):
        return False
    if " " in normalized:
        return False
    if not VALID_TICKER_RE.match(normalized):
        return False
    if normalized in DISALLOWED_TICKER_LABELS:
        return False
    return True


def _parse_tickers(value: str | None) -> set[str]:
    if value is None:
        return set()
    normalized = value.replace(",", " ")
    return {part.strip().upper() for part in normalized.split() if part.strip()}


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _load_rows(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {table_name}
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY ticker ASC
        """,
        (signal_date, taxonomy_version),
    ).fetchall()
    return [dict(row) for row in rows if _is_valid_ticker(row["ticker"])]


def _ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = str(row["ticker"]).strip().upper()
        result[ticker] = row
    return result


def _distribution(rows: list[dict[str, object]], field_name: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        text = _normalized_text(row.get(field_name))
        if text is None:
            continue
        counts[text] += 1
    return counts


def _coverage_status(
    *,
    source_column_exists: bool,
    enrichment_column_exists: bool,
    source_non_empty_count: int,
    enrichment_non_empty_count: int,
) -> str:
    if not source_column_exists and not enrichment_column_exists:
        return "BOTH_COLUMNS_MISSING"
    if not source_column_exists:
        return "SOURCE_COLUMN_MISSING"
    if not enrichment_column_exists:
        return "ENRICHMENT_COLUMN_MISSING"
    if source_non_empty_count > 0 and enrichment_non_empty_count > 0:
        return "BOTH_POPULATED"
    if source_non_empty_count > 0 and enrichment_non_empty_count == 0:
        return "SOURCE_ONLY"
    if source_non_empty_count == 0 and enrichment_non_empty_count > 0:
        return "ENRICHMENT_ONLY"
    return "BOTH_EMPTY"


def _neutral_like(value: object) -> bool:
    text = (_normalized_text(value) or "").upper()
    return text in NEUTRAL_LIKE_VALUES


def _example_rows(
    *,
    selected_tickers: list[str],
    source_map: dict[str, dict[str, object]],
    enrichment_map: dict[str, dict[str, object]],
    max_examples: int,
) -> list[tuple[str, str, str, str, str, str]]:
    examples: list[tuple[str, str, str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        ticker: str,
        example_type: str,
        source_field: str,
        source_value: object,
        enrichment_field: str,
        enrichment_value: object,
    ) -> None:
        key = (ticker, example_type)
        if key in seen or len(examples) >= max_examples:
            return
        seen.add(key)
        examples.append(
            (
                ticker,
                example_type,
                source_field,
                _normalized_text(source_value) or "",
                enrichment_field,
                _normalized_text(enrichment_value) or "",
            )
        )

    all_tickers = selected_tickers or sorted(set(source_map) | set(enrichment_map))
    for ticker in all_tickers:
        source_row = source_map.get(ticker)
        enrichment_row = enrichment_map.get(ticker)
        if source_row and not enrichment_row:
            add(ticker, "SOURCE_EXISTS_ENRICHMENT_MISSING", "ticker", ticker, "ticker", "")
            continue
        if enrichment_row and not source_row:
            add(ticker, "ENRICHMENT_EXISTS_SOURCE_MISSING", "ticker", "", "ticker", ticker)
            continue
        if not source_row or not enrichment_row:
            continue
        if _normalized_text(source_row.get("exit_risk_severity")) and _neutral_like(
            enrichment_row.get("current_status")
        ):
            add(
                ticker,
                "SOURCE_RISK_ENRICHMENT_NEUTRAL",
                "exit_risk_severity",
                source_row.get("exit_risk_severity"),
                "current_status",
                enrichment_row.get("current_status"),
            )
        if _is_truthy_signal(source_row.get("breakout_signal")) and not _normalized_text(
            enrichment_row.get("daily_status")
        ):
            add(
                ticker,
                "SOURCE_BREAKOUT_NO_ENRICHMENT_STATUS",
                "breakout_signal",
                source_row.get("breakout_signal"),
                "daily_status",
                enrichment_row.get("daily_status"),
            )
        if _is_truthy_signal(source_row.get("pullback_signal")) and not _normalized_text(
            enrichment_row.get("pullback_validity")
        ):
            add(
                ticker,
                "SOURCE_PULLBACK_NO_ENRICHMENT_PULLBACK",
                "pullback_signal",
                source_row.get("pullback_signal"),
                "pullback_validity",
                enrichment_row.get("pullback_validity"),
            )
        if (
            _normalized_text(source_row.get("latest_bos_event_type")) == "BOS_DOWN"
            or _normalized_text(source_row.get("latest_reset_reason"))
        ) and _neutral_like(enrichment_row.get("daily_status")):
            add(
                ticker,
                "SOURCE_BOS_RESET_NO_RISK_STATUS",
                "latest_bos_event_type",
                source_row.get("latest_bos_event_type"),
                "daily_status",
                enrichment_row.get("daily_status"),
            )
        if _normalized_text(source_row.get("price_data_status")) not in {None, "OK"}:
            add(
                ticker,
                "SOURCE_NON_OK_PRICE_STATUS",
                "price_data_status",
                source_row.get("price_data_status"),
                "data_quality_status",
                enrichment_row.get("data_quality_status"),
            )
        if len(examples) >= max_examples:
            break
    return examples


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit source-signal coverage between ticker source rows and ticker enrichment rows.",
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--tickers")
    parser.add_argument("--max-examples", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with _connect_read_only(args.analysis_db) as conn:
            if not _table_exists(conn, SOURCE_TABLE):
                raise ValueError(f"missing required source table: {SOURCE_TABLE}")
            if not _table_exists(conn, ENRICHMENT_TABLE):
                raise ValueError(f"missing required enrichment table: {ENRICHMENT_TABLE}")
            source_columns = _table_columns(conn, SOURCE_TABLE)
            enrichment_columns = _table_columns(conn, ENRICHMENT_TABLE)
            source_rows = _load_rows(
                conn,
                table_name=SOURCE_TABLE,
                signal_date=args.signal_date,
                taxonomy_version=args.taxonomy_version,
            )
            enrichment_rows = _load_rows(
                conn,
                table_name=ENRICHMENT_TABLE,
                signal_date=args.signal_date,
                taxonomy_version=args.taxonomy_version,
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    source_map = _ticker_map(source_rows)
    enrichment_map = _ticker_map(enrichment_rows)
    common_tickers = sorted(set(source_map) & set(enrichment_map))
    source_only_tickers = sorted(set(source_map) - set(enrichment_map))
    enrichment_only_tickers = sorted(set(enrichment_map) - set(source_map))
    selected_tickers = sorted(_parse_tickers(args.tickers))

    _print_row("section", "database")
    _print_row("database", "path", "status", "reason")
    _print_row("database", args.analysis_db, "OK", "read_only")

    _print_row("section", "field_coverage")
    _print_row(
        "field_coverage",
        "field_name",
        "source_column_exists",
        "enrichment_column_exists",
        "source_non_empty_count",
        "enrichment_non_empty_count",
        "gap_count",
        "status",
    )

    fields_source_only = 0
    fields_enrichment_missing = 0
    source_risk_not_mapped_count = 0
    for source_field, enrichment_field_override in FIELD_SPECS:
        enrichment_field = enrichment_field_override or source_field
        source_column_exists = source_field in source_columns
        enrichment_column_exists = enrichment_field in enrichment_columns
        source_non_empty_count = (
            sum(1 for row in source_rows if _is_non_empty(row.get(source_field)))
            if source_column_exists
            else 0
        )
        enrichment_non_empty_count = (
            sum(1 for row in enrichment_rows if _is_non_empty(row.get(enrichment_field)))
            if enrichment_column_exists
            else 0
        )
        gap_count = 0
        if source_column_exists and enrichment_column_exists:
            gap_count = sum(
                1
                for ticker in common_tickers
                if _is_non_empty(source_map[ticker].get(source_field))
                and not _is_non_empty(enrichment_map[ticker].get(enrichment_field))
            )
        status = _coverage_status(
            source_column_exists=source_column_exists,
            enrichment_column_exists=enrichment_column_exists,
            source_non_empty_count=source_non_empty_count,
            enrichment_non_empty_count=enrichment_non_empty_count,
        )
        if status == "SOURCE_ONLY":
            fields_source_only += 1
        if source_non_empty_count > 0 and (
            not enrichment_column_exists or enrichment_non_empty_count == 0
        ):
            fields_enrichment_missing += 1
        if source_field in {
            "exit_risk_signal",
            "exit_risk_severity",
            "latest_bos_event_type",
            "latest_reset_reason",
        }:
            source_risk_not_mapped_count += gap_count
        _print_row(
            "field_coverage",
            source_field,
            1 if source_column_exists else 0,
            1 if enrichment_column_exists else 0,
            source_non_empty_count,
            enrichment_non_empty_count,
            gap_count,
            status,
        )

    _print_row("section", "source_signal_distribution")
    _print_row("source_signal_distribution", "field_name", "value", "count")
    for field_name in SOURCE_DISTRIBUTION_FIELDS:
        if field_name not in source_columns:
            continue
        for value, count in sorted(_distribution(source_rows, field_name).items()):
            _print_row("source_signal_distribution", field_name, value, count)

    _print_row("section", "enrichment_signal_distribution")
    _print_row("enrichment_signal_distribution", "field_name", "value", "count")
    for field_name in ENRICHMENT_DISTRIBUTION_FIELDS:
        if field_name not in enrichment_columns:
            continue
        for value, count in sorted(_distribution(enrichment_rows, field_name).items()):
            _print_row("enrichment_signal_distribution", field_name, value, count)

    examples = _example_rows(
        selected_tickers=selected_tickers,
        source_map=source_map,
        enrichment_map=enrichment_map,
        max_examples=args.max_examples,
    )
    _print_row("section", "ticker_examples")
    _print_row(
        "ticker_examples",
        "ticker",
        "example_type",
        "source_field",
        "source_value",
        "enrichment_field",
        "enrichment_value",
    )
    for row in examples:
        _print_row("ticker_examples", *row)

    source_signal_rows = 0
    for row in source_rows:
        if (
            _is_truthy_signal(row.get("exit_risk_signal"))
            or _is_non_empty(row.get("exit_risk_severity"))
            or _is_truthy_signal(row.get("breakout_signal"))
            or _is_truthy_signal(row.get("pullback_signal"))
            or _normalized_text(row.get("latest_bos_event_type")) == "BOS_DOWN"
            or _is_non_empty(row.get("latest_reset_reason"))
        ):
            source_signal_rows += 1

    enrichment_status_populated_rows = 0
    for row in enrichment_rows:
        if any(
            _is_non_empty(row.get(field_name))
            for field_name in (
                "daily_status",
                "rolling_2d_status",
                "rolling_5d_status",
                "rolling_30d_status",
                "current_status",
                "ma_break_status",
                "freshness_status",
            )
        ):
            enrichment_status_populated_rows += 1

    neutral_or_empty_enrichment_rows = sum(
        1
        for ticker in common_tickers
        if _neutral_like(enrichment_map[ticker].get("action"))
        and _neutral_like(enrichment_map[ticker].get("current_status"))
        and _neutral_like(enrichment_map[ticker].get("daily_status"))
    )

    source_has_risk_signals_not_mapped = (
        source_risk_not_mapped_count > 0 or (
            source_signal_rows > 0 and neutral_or_empty_enrichment_rows == len(common_tickers)
        )
    )
    source_lacks_decision_signals = source_signal_rows == 0
    enrichment_status_fields_missing = enrichment_status_populated_rows == 0
    mapping_layer_needed = source_signal_rows > 0 and (
        enrichment_status_fields_missing
        or neutral_or_empty_enrichment_rows == len(common_tickers)
        or source_risk_not_mapped_count > 0
    )

    _print_row("section", "mapping_gap_hypothesis")
    _print_row("mapping_gap_hypothesis", "hypothesis", "status", "evidence")
    _print_row(
        "mapping_gap_hypothesis",
        "SOURCE_HAS_RISK_SIGNALS_NOT_MAPPED",
        "LIKELY" if source_has_risk_signals_not_mapped else "UNLIKELY",
        f"source_signal_rows={source_signal_rows};source_risk_gaps={source_risk_not_mapped_count};neutral_like_common={neutral_or_empty_enrichment_rows}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "SOURCE_LACKS_DECISION_SIGNALS",
        "LIKELY" if source_lacks_decision_signals else "UNLIKELY",
        f"source_signal_rows={source_signal_rows}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "ENRICHMENT_STATUS_FIELDS_MISSING",
        "LIKELY" if enrichment_status_fields_missing else "UNLIKELY",
        f"enrichment_status_populated_rows={enrichment_status_populated_rows};enrichment_rows={len(enrichment_rows)}",
    )
    _print_row(
        "mapping_gap_hypothesis",
        "MAPPING_LAYER_NEEDED",
        "LIKELY" if mapping_layer_needed else "UNLIKELY",
        f"source_signal_rows={source_signal_rows};neutral_like_common={neutral_or_empty_enrichment_rows};enrichment_status_populated_rows={enrichment_status_populated_rows}",
    )

    _print_row("section", "summary")
    _print_row("SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.status=OK")
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.signal_date="
        f"{args.signal_date}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.taxonomy_version="
        f"{args.taxonomy_version}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.source_rows="
        f"{len(source_rows)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.enrichment_rows="
        f"{len(enrichment_rows)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.common_tickers="
        f"{len(common_tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.source_only_tickers="
        f"{len(source_only_tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.enrichment_only_tickers="
        f"{len(enrichment_only_tickers)}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.fields_source_only="
        f"{fields_source_only}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.fields_enrichment_missing="
        f"{fields_enrichment_missing}"
    )
    _print_row(
        "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.examples="
        f"{len(examples)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
