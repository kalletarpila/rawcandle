from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    build_dashboard_rows_from_ticker_enrichment_rows,
    load_ticker_enrichment_rows,
)
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardParseResult,
    DatacenterDashboardRow,
    parse_datacenter_dashboard_file,
)
from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.inspect_ecosystem_dashboard import _connect_read_only

ENRICHMENT_TABLE = "dc_dashboard_ticker_enrichment_daily"
SOURCE_TABLE = "dc_ticker_swing_signal_daily"
PULLBACK_DEFAULT = "INSUFFICIENT_DATA"
PULLBACK_PRIORITY = (
    "VALID_PULLBACK",
    "EARLY_PULLBACK",
    "STRUCTURE_BLOCKED_PULLBACK",
    "BREAKDOWN_NOT_PULLBACK",
    "NO_PULLBACK",
    "INSUFFICIENT_DATA",
)
ROW_SCAN_FIELDS = (
    "raw_action",
    "raw_status",
    "reason",
    "blocking_reasons",
    "ma_break_status",
    "freshness_status",
    "latest_bos_event_type",
    "latest_reset_reason",
)
CANDIDATE_FIELDS = (
    "close_below_ema20",
    "distance_to_ema20_pct",
    "ma_break_status",
    "return_10d",
    "return_10d_lt_minus_8pct",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "price_data_status",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("\n", " ").replace(";", ",").strip()


def _safe_float(value: object) -> float | None:
    text = _cell(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def _connect_analysis_read_only(path: str):
    db_path = Path(path)
    if not db_path.exists():
        raise ValueError(f"analysis_db not found: {path}")
    conn = _connect_read_only(str(db_path))
    conn.row_factory = __import__("sqlite3").Row
    return conn


def _require_table(conn, table_name: str) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"required table missing: {table_name}")


def _table_columns(conn, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


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


def _load_reports_rows(*, reports_dir: str, report_date: str) -> tuple[list[DatacenterDashboardRow], list[str]]:
    dashboard_status = discover_datacenter_dashboard_status(reports_dir, report_date=report_date)
    if not dashboard_status.reports:
        raise ValueError(f"no reports discovered in reports_dir={reports_dir}")
    rows: list[DatacenterDashboardRow] = []
    warnings: list[str] = []
    for report in dashboard_status.reports:
        if report.path is None:
            continue
        parse_result: DatacenterDashboardParseResult = parse_datacenter_dashboard_file(
            path=report.path,
            horizon=report.horizon,
        )
        rows.extend(parse_result.rows)
        warnings.extend(parse_result.warnings)
    return rows, warnings


def _load_source_rows(
    analysis_db: str,
    report_date: str,
    taxonomy_version: str,
) -> dict[str, dict[str, object]]:
    with _connect_analysis_read_only(analysis_db) as conn:
        _require_table(conn, SOURCE_TABLE)
        source_columns = _table_columns(conn, SOURCE_TABLE)
        has_taxonomy = "taxonomy_version" in source_columns
        if has_taxonomy:
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


def _snapshot_ticker_map(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapped: dict[str, dict[str, object]] = {}
    for row in rows:
        ticker = _cell(row.get("ticker")).upper()
        if ticker:
            mapped[ticker] = row
    return mapped


def _group_rows_by_ticker(rows: list[DatacenterDashboardRow]) -> dict[str, list[DatacenterDashboardRow]]:
    grouped: dict[str, list[DatacenterDashboardRow]] = {}
    for row in rows:
        grouped.setdefault(row.ticker.upper(), []).append(row)
    return grouped


def _normalized_field(value: object, default: str) -> str:
    text = _cell(value)
    return text or default


def _selection_reason(
    *,
    reports_row: dict[str, object] | None,
    enrichment_row: dict[str, object] | None,
    reports_rows: list[DatacenterDashboardRow],
) -> tuple[int, str]:
    reports_pullback = _normalized_field(
        None if reports_row is None else reports_row.get("pullback_validity"),
        PULLBACK_DEFAULT,
    )
    enrichment_pullback = _normalized_field(
        None if enrichment_row is None else enrichment_row.get("pullback_validity"),
        PULLBACK_DEFAULT,
    )
    reasons: list[str] = []
    if reports_pullback != enrichment_pullback:
        reasons.append("PULLBACK_VALIDITY_DIFFERENT")
    if _has_close_below_ema20_token(reports_rows):
        reasons.append("REPORTS_HAS_CLOSE_BELOW_EMA20")
    priority = PULLBACK_PRIORITY.index(reports_pullback) if reports_pullback in PULLBACK_PRIORITY else len(PULLBACK_PRIORITY)
    return priority, ",".join(reasons) or "MATCH"


def _selected_tickers(
    *,
    reports_by_ticker: dict[str, dict[str, object]],
    enrichment_by_ticker: dict[str, dict[str, object]],
    reports_grouped: dict[str, list[DatacenterDashboardRow]],
    explicit_tickers: list[str],
    max_examples: int,
) -> list[tuple[str, str]]:
    if explicit_tickers:
        selected: list[tuple[str, str]] = []
        for ticker in explicit_tickers:
            if ticker in reports_by_ticker and ticker in enrichment_by_ticker:
                selected.append((ticker, "EXPLICIT"))
        return selected[:max_examples]

    candidates: list[tuple[int, int, str, str]] = []
    for ticker in sorted(set(reports_by_ticker) & set(enrichment_by_ticker)):
        priority, reason = _selection_reason(
            reports_row=reports_by_ticker.get(ticker),
            enrichment_row=enrichment_by_ticker.get(ticker),
            reports_rows=reports_grouped.get(ticker, []),
        )
        if reason != "MATCH":
            close_priority = 0 if "REPORTS_HAS_CLOSE_BELOW_EMA20" in reason else 1
            candidates.append((close_priority, priority, ticker, reason))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(ticker, reason) for _close_priority, _priority, ticker, reason in candidates[:max_examples]]


def _field_or_attr_value(row: DatacenterDashboardRow, name: str) -> object:
    if name in row.raw_fields and _cell(row.raw_fields.get(name)):
        return row.raw_fields.get(name)
    if hasattr(row, name):
        return getattr(row, name)
    return None


def _scan_token_source(row: DatacenterDashboardRow, token: str) -> tuple[str, str]:
    lowered = token.lower()
    for field_name in ROW_SCAN_FIELDS:
        value = getattr(row, field_name)
        if value and lowered in str(value).lower():
            return field_name, _cell(value)
    for key, value in row.raw_fields.items():
        if value and lowered in str(value).lower():
            return key, _cell(value)
    attr_value = _field_or_attr_value(row, token)
    if _cell(attr_value):
        return token, _cell(attr_value)
    return "", ""


def _has_close_below_ema20_token(rows: list[DatacenterDashboardRow]) -> bool:
    for row in rows:
        if _scan_token_source(row, "close_below_ema20")[0]:
            return True
    return False


def _token_source_details(rows: list[DatacenterDashboardRow]) -> tuple[str, str]:
    for row in rows:
        source_name, value = _scan_token_source(row, "close_below_ema20")
        if source_name:
            return source_name, value or "close_below_ema20"
    return "", ""


def _source_distance_value(row: dict[str, object] | None) -> object:
    if row is None:
        return None
    for key in ("distance_to_ema20_pct", "distance_to_ema20"):
        value = row.get(key)
        if _cell(value):
            return value
    return None


def _mapping_value(row: dict[str, object] | None, field_name: str) -> object:
    if row is None:
        return None
    value = row.get(field_name)
    if _cell(value):
        return value
    if field_name == "distance_to_ema20_pct":
        return _source_distance_value(row)
    return None


def _row_field_value(rows: list[DatacenterDashboardRow], field_name: str) -> object:
    for row in rows:
        value = _field_or_attr_value(row, field_name)
        if _cell(value):
            return value
    return None


def _candidate_mapping_result(
    *,
    reports_has_token: bool,
    source_distance: float | None,
    enrichment_distance: float | None,
    source_row: dict[str, object] | None,
    enrichment_row: dict[str, object] | None,
) -> str:
    if _cell(None if source_row is None else source_row.get("close_below_ema20")) or _cell(
        None if enrichment_row is None else enrichment_row.get("close_below_ema20")
    ):
        return "DIRECT_FIELD_EXISTS"
    if source_distance is None and enrichment_distance is None:
        return "DISTANCE_MISSING" if reports_has_token else "NO_STRUCTURED_EQUIVALENT_FOUND"
    distance = source_distance if source_distance is not None else enrichment_distance
    if reports_has_token:
        if distance is not None and distance < 0:
            return "DISTANCE_NEGATIVE_MATCHES_REPORTS_TOKEN"
        if distance is not None:
            return "DISTANCE_NON_NEGATIVE_CONFLICTS_WITH_REPORTS_TOKEN"
    return "NO_STRUCTURED_EQUIVALENT_FOUND"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the reports-mode source and structured availability of the "
            "close_below_ema20 semantic token."
        )
    )
    parser.add_argument("--reports-dir", required=True)
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
        reports_rows, parse_warnings = _load_reports_rows(
            reports_dir=args.reports_dir,
            report_date=args.report_date,
        )
        taxonomy_version = _taxonomy_version_for_report_date(args.analysis_db, args.report_date)
        enrichment_table_rows = load_ticker_enrichment_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
        )
        enrichment_adapter_rows = build_dashboard_rows_from_ticker_enrichment_rows(
            enrichment_table_rows
        )
        source_rows_by_ticker = _load_source_rows(
            args.analysis_db,
            args.report_date,
            taxonomy_version,
        )
    except Exception as exc:  # pragma: no cover
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    reports_by_ticker = _snapshot_ticker_map(reports_snapshot.tickers)
    enrichment_by_ticker = _snapshot_ticker_map(enrichment_snapshot.tickers)
    reports_grouped = _group_rows_by_ticker(reports_rows)
    enrichment_grouped = _group_rows_by_ticker(enrichment_adapter_rows)
    enrichment_table_by_ticker = {
        _cell(row.get("ticker")).upper(): row for row in enrichment_table_rows if _cell(row.get("ticker"))
    }

    selected_tickers = _selected_tickers(
        reports_by_ticker=reports_by_ticker,
        enrichment_by_ticker=enrichment_by_ticker,
        reports_grouped=reports_grouped,
        explicit_tickers=_parse_tickers(args.tickers),
        max_examples=args.max_examples,
    )

    _print_section("run_summary")
    _print_row("run_summary", "side", "path_or_db", "run_id", "report_date", "source")
    _print_row("run_summary", "reports_dir", args.reports_dir, args.reports_run_id, args.report_date, "reports_parse")
    _print_row("run_summary", "reports_dashboard", args.reports_dashboard_db, args.reports_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "enrichment_dashboard", args.enrichment_dashboard_db, args.enrichment_run_id, args.report_date, "dashboard_snapshot")
    _print_row("run_summary", "analysis", args.analysis_db, taxonomy_version, args.report_date, "analysis_enrichment")

    reports_rows_with_token = 0
    enrichment_adapter_rows_with_token = 0
    enrichment_table_rows_with_token = 0
    source_rows_with_token = 0
    reports_tickers_with_token: set[str] = set()
    enrichment_adapter_tickers_with_token: set[str] = set()
    enrichment_table_tickers_with_token: set[str] = set()
    source_tickers_with_token: set[str] = set()

    for row in reports_rows:
        if _has_close_below_ema20_token([row]):
            reports_rows_with_token += 1
            reports_tickers_with_token.add(row.ticker.upper())
    for row in enrichment_adapter_rows:
        if _has_close_below_ema20_token([row]):
            enrichment_adapter_rows_with_token += 1
            enrichment_adapter_tickers_with_token.add(row.ticker.upper())
    for row in enrichment_table_rows:
        if _cell(row.get("close_below_ema20")):
            enrichment_table_rows_with_token += 1
            enrichment_table_tickers_with_token.add(_cell(row.get("ticker")).upper())
    for ticker, row in source_rows_by_ticker.items():
        if _cell(row.get("close_below_ema20")):
            source_rows_with_token += 1
            source_tickers_with_token.add(ticker)

    _print_section("close_below_ema20_presence")
    _print_row("close_below_ema20_presence", "source", "rows_with_token", "tickers_with_token", "notes")
    _print_row("close_below_ema20_presence", "reports_parser_rows", reports_rows_with_token, len(reports_tickers_with_token), f"parse_warnings={len(parse_warnings)}")
    _print_row("close_below_ema20_presence", "enrichment_adapter_rows", enrichment_adapter_rows_with_token, len(enrichment_adapter_tickers_with_token), "")
    _print_row("close_below_ema20_presence", "enrichment_table", enrichment_table_rows_with_token, len(enrichment_table_tickers_with_token), "")
    _print_row("close_below_ema20_presence", "source_table", source_rows_with_token, len(source_tickers_with_token), "")

    _print_section("candidate_source_fields")
    _print_row(
        "candidate_source_fields",
        "field_name",
        "source_table_exists",
        "enrichment_table_exists",
        "adapter_exposes",
        "non_empty_count",
        "negative_or_true_count",
        "notes",
    )
    all_selected = [ticker for ticker, _reason in selected_tickers]
    for field_name in CANDIDATE_FIELDS:
        source_exists = 0
        enrichment_exists = 0
        adapter_exposes = 0
        non_empty_count = 0
        negative_or_true_count = 0
        for ticker in all_selected:
            source_row = source_rows_by_ticker.get(ticker)
            enrichment_row = enrichment_table_by_ticker.get(ticker)
            adapter_rows = enrichment_grouped.get(ticker, [])
            source_value = _mapping_value(source_row, field_name)
            enrichment_value = _mapping_value(enrichment_row, field_name)
            adapter_value = _row_field_value(adapter_rows, field_name)
            if _cell(source_value):
                source_exists = 1
                non_empty_count += 1
            elif _cell(enrichment_value) or _cell(adapter_value):
                non_empty_count += 1
            if _cell(enrichment_value):
                enrichment_exists = 1
            if _cell(adapter_value):
                adapter_exposes = 1
            comparable = source_value if _cell(source_value) else enrichment_value if _cell(enrichment_value) else adapter_value
            text = _cell(comparable).lower()
            numeric = _safe_float(comparable)
            if field_name == "distance_to_ema20_pct":
                if numeric is not None and numeric < 0:
                    negative_or_true_count += 1
            elif text in {"1", "true", "yes"}:
                negative_or_true_count += 1
        notes = "uses distance_to_ema20 alias" if field_name == "distance_to_ema20_pct" else ""
        _print_row(
            "candidate_source_fields",
            field_name,
            source_exists,
            enrichment_exists,
            adapter_exposes,
            non_empty_count,
            negative_or_true_count,
            notes,
        )

    _print_section("selected_tickers")
    _print_row(
        "selected_tickers",
        "ticker",
        "reports_pullback_validity",
        "enrichment_pullback_validity",
        "reports_has_close_below_ema20",
        "enrichment_has_close_below_ema20",
        "source_distance_to_ema20_pct",
        "enrichment_distance_to_ema20_pct",
        "selection_reason",
    )

    reports_close_below_ema20_tickers = 0
    enrichment_close_below_ema20_tickers = 0
    negative_distance_matches = 0
    mismatch_tickers_with_reports_close_below_ema20 = 0
    mismatch_tickers_with_negative_source_distance = 0
    mismatch_tickers_where_distance_mapping_would_add_token = 0
    mismatch_tickers_unexplained_by_distance = 0
    ma_break_already_covers = 0

    _print_section("per_ticker_close_below_context")
    _print_row(
        "per_ticker_close_below_context",
        "ticker",
        "reports_token_source",
        "reports_token_value",
        "enrichment_token_value",
        "source_distance_to_ema20_pct",
        "enrichment_distance_to_ema20_pct",
        "source_ma_break_status",
        "enrichment_ma_break_status",
        "source_return_10d",
        "enrichment_return_10d",
        "candidate_mapping_result",
        "evidence",
    )

    for ticker, selection_reason in selected_tickers:
        reports_row = reports_by_ticker.get(ticker)
        enrichment_row = enrichment_by_ticker.get(ticker)
        reports_rows_for_ticker = reports_grouped.get(ticker, [])
        enrichment_rows_for_ticker = enrichment_grouped.get(ticker, [])
        source_row = source_rows_by_ticker.get(ticker)
        enrichment_table_row = enrichment_table_by_ticker.get(ticker)

        reports_has_token = _has_close_below_ema20_token(reports_rows_for_ticker)
        enrichment_has_token = _has_close_below_ema20_token(enrichment_rows_for_ticker)
        reports_source_name, reports_token_value = _token_source_details(reports_rows_for_ticker)
        _enrichment_source_name, enrichment_token_value = _token_source_details(enrichment_rows_for_ticker)
        source_distance = _safe_float(_source_distance_value(source_row))
        enrichment_distance = _safe_float(_source_distance_value(enrichment_table_row))
        mapping_result = _candidate_mapping_result(
            reports_has_token=reports_has_token,
            source_distance=source_distance,
            enrichment_distance=enrichment_distance,
            source_row=source_row,
            enrichment_row=enrichment_table_row,
        )
        evidence = []
        if reports_has_token:
            reports_close_below_ema20_tickers += 1
            mismatch_tickers_with_reports_close_below_ema20 += 1
        if enrichment_has_token:
            enrichment_close_below_ema20_tickers += 1
        if source_distance is not None and source_distance < 0:
            mismatch_tickers_with_negative_source_distance += 1
        if mapping_result == "DISTANCE_NEGATIVE_MATCHES_REPORTS_TOKEN":
            negative_distance_matches += 1
            mismatch_tickers_where_distance_mapping_would_add_token += 1
        elif reports_has_token:
            mismatch_tickers_unexplained_by_distance += 1
        source_ma_break_status = _cell(None if source_row is None else source_row.get("ma_break_status"))
        enrichment_ma_break_status = _cell(_row_field_value(enrichment_rows_for_ticker, "ma_break_status"))
        if source_ma_break_status or enrichment_ma_break_status:
            ma_break_already_covers += 1
        evidence.append(f"selection_reason={selection_reason}")
        if source_distance is not None:
            evidence.append(f"source_distance={source_distance:.4f}")
        if enrichment_distance is not None:
            evidence.append(f"enrichment_distance={enrichment_distance:.4f}")

        _print_row(
            "selected_tickers",
            ticker,
            _normalized_field(None if reports_row is None else reports_row.get("pullback_validity"), PULLBACK_DEFAULT),
            _normalized_field(None if enrichment_row is None else enrichment_row.get("pullback_validity"), PULLBACK_DEFAULT),
            int(reports_has_token),
            int(enrichment_has_token),
            _source_distance_value(source_row),
            _source_distance_value(enrichment_table_row),
            selection_reason,
        )
        _print_row(
            "per_ticker_close_below_context",
            ticker,
            reports_source_name,
            reports_token_value,
            enrichment_token_value,
            _source_distance_value(source_row),
            _source_distance_value(enrichment_table_row),
            None if source_row is None else source_row.get("ma_break_status"),
            _row_field_value(enrichment_rows_for_ticker, "ma_break_status"),
            None if source_row is None else source_row.get("return_10d"),
            _row_field_value(enrichment_rows_for_ticker, "return_10d"),
            mapping_result,
            "|".join(evidence),
        )

    _print_section("impact_estimate")
    _print_row("impact_estimate", "metric", "count", "details")
    _print_row("impact_estimate", "reports_close_below_ema20_tickers", reports_close_below_ema20_tickers, "")
    _print_row("impact_estimate", "enrichment_missing_close_below_ema20_tickers", max(reports_close_below_ema20_tickers - enrichment_close_below_ema20_tickers, 0), "")
    _print_row("impact_estimate", "mismatch_tickers_with_reports_close_below_ema20", mismatch_tickers_with_reports_close_below_ema20, "")
    _print_row("impact_estimate", "mismatch_tickers_with_negative_source_distance", mismatch_tickers_with_negative_source_distance, "")
    _print_row("impact_estimate", "mismatch_tickers_where_distance_mapping_would_add_token", mismatch_tickers_where_distance_mapping_would_add_token, "")
    _print_row("impact_estimate", "mismatch_tickers_unexplained_by_distance", mismatch_tickers_unexplained_by_distance, "")

    reports_uses_token = reports_close_below_ema20_tickers > 0
    enrichment_lacks_token = reports_close_below_ema20_tickers > enrichment_close_below_ema20_tickers
    distance_can_derive = negative_distance_matches > 0
    ma_break_covers_this = ma_break_already_covers >= max(reports_close_below_ema20_tickers, 1)
    mapping_likely_fixes = (
        mismatch_tickers_where_distance_mapping_would_add_token > 0
        and mismatch_tickers_where_distance_mapping_would_add_token >= max(1, reports_close_below_ema20_tickers // 2)
    )
    needs_reports_only = reports_close_below_ema20_tickers > 0 and negative_distance_matches == 0

    _print_section("hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "REPORTS_USES_CLOSE_BELOW_EMA20_TOKEN",
        "LIKELY" if reports_uses_token else "UNLIKELY",
        f"reports_close_below_ema20_tickers={reports_close_below_ema20_tickers}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_LACKS_CLOSE_BELOW_EMA20_TOKEN",
        "LIKELY" if enrichment_lacks_token else "UNLIKELY",
        f"enrichment_close_below_ema20_tickers={enrichment_close_below_ema20_tickers}",
    )
    _print_row(
        "hypothesis_summary",
        "DISTANCE_TO_EMA20_CAN_DERIVE_TOKEN",
        "LIKELY" if distance_can_derive else "UNLIKELY",
        f"negative_distance_matches={negative_distance_matches}",
    )
    _print_row(
        "hypothesis_summary",
        "MA_BREAK_ALREADY_COVERS_THIS",
        "LIKELY" if ma_break_covers_this else "UNLIKELY",
        f"ma_break_coverage_count={ma_break_already_covers}",
    )
    _print_row(
        "hypothesis_summary",
        "CLOSE_BELOW_EMA20_MAPPING_LIKELY_FIXES_TOP_GAP",
        "LIKELY" if mapping_likely_fixes else "UNLIKELY",
        f"distance_mapping_adds={mismatch_tickers_where_distance_mapping_would_add_token}",
    )
    _print_row(
        "hypothesis_summary",
        "NEEDS_REPORTS_ONLY_SEMANTIC_EXTRACTION",
        "LIKELY" if needs_reports_only else "UNLIKELY",
        f"unexplained_by_distance={mismatch_tickers_unexplained_by_distance}",
    )

    _print_section("summary")
    print("SUMMARY datacenter_dashboard_close_below_ema20_source_audit.status=OK")
    print(f"SUMMARY datacenter_dashboard_close_below_ema20_source_audit.report_date={args.report_date}")
    print(f"SUMMARY datacenter_dashboard_close_below_ema20_source_audit.selected_tickers={len(selected_tickers)}")
    print(f"SUMMARY datacenter_dashboard_close_below_ema20_source_audit.reports_close_below_ema20_tickers={reports_close_below_ema20_tickers}")
    print(f"SUMMARY datacenter_dashboard_close_below_ema20_source_audit.enrichment_close_below_ema20_tickers={enrichment_close_below_ema20_tickers}")
    print(
        "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.source_distance_to_ema20_available="
        f"{int(any(_source_distance_value(source_rows_by_ticker.get(ticker)) is not None for ticker, _ in selected_tickers))}"
    )
    print(f"SUMMARY datacenter_dashboard_close_below_ema20_source_audit.negative_distance_matches={negative_distance_matches}")
    print(
        "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.mapping_likely_fixes_top_gap="
        f"{int(mapping_likely_fixes)}"
    )
    print(
        "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.needs_reports_only_semantic_extraction="
        f"{int(needs_reports_only)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
