from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace(";", ",").replace("\n", " ").strip()


def _print_row(*values: object) -> None:
    print(";".join(_cell(value) for value in values))


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(f"db not found: {db_path}")
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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _normalize(value: object) -> str:
    return _cell(value).upper()


def _market_map_key(row: dict[str, object]) -> str:
    taxonomy_path = _cell(row.get("taxonomy_path"))
    if taxonomy_path:
        return taxonomy_path
    return "|".join(
        [
            _cell(row.get("market_level")),
            _cell(row.get("name")),
            _cell(row.get("parent_name")),
            _cell(row.get("layer")),
            _cell(row.get("subindustry")),
        ]
    )


def _row_name(row: dict[str, object], field_name: str) -> str:
    return _cell(row.get(field_name))


def _shape_for_key(key: str) -> str:
    normalized = key.strip()
    if normalized.startswith("ECOSYSTEM|"):
        return "ECOSYSTEM_PIPE"
    if normalized.startswith("LAYER|"):
        return "LAYER_PIPE"
    if normalized.startswith("SUBINDUSTRY|"):
        return "SUBINDUSTRY_PIPE"
    if normalized.startswith("DC_ECOSYSTEM_TOTAL > ") and normalized.count(" > ") == 1:
        return "DC_ECOSYSTEM_TOTAL_GT_LAYER"
    if normalized.startswith("DC_ECOSYSTEM_TOTAL > ") and normalized.count(" > ") >= 2:
        return "ECOSYSTEM_GT_LAYER_GT_SUBINDUSTRY"
    return "OTHER"


def _market_level_bucket(row: dict[str, object]) -> str:
    level = _normalize(row.get("market_level"))
    if level in {"ECOSYSTEM", "LAYER", "SUBINDUSTRY"}:
        return level.lower()
    return "other"


def _market_row_dict(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {_market_map_key(row): row for row in rows}


def _semantic_match_type(
    reports_row: dict[str, object],
    enrichment_row: dict[str, object],
) -> str:
    reports_subindustry = _normalize(reports_row.get("subindustry") or reports_row.get("name"))
    enrichment_subindustry = _normalize(
        enrichment_row.get("subindustry") or enrichment_row.get("name")
    )
    if (
        reports_subindustry
        and enrichment_subindustry
        and reports_subindustry == enrichment_subindustry
        and (
            _normalize(reports_row.get("market_level")) == "SUBINDUSTRY"
            or _normalize(enrichment_row.get("market_level")) == "SUBINDUSTRY"
        )
    ):
        return "SAME_SUBINDUSTRY_NAME_DIFFERENT_KEY"

    reports_layer = _normalize(reports_row.get("layer") or reports_row.get("name"))
    enrichment_layer = _normalize(enrichment_row.get("layer") or enrichment_row.get("name"))
    if (
        reports_layer
        and enrichment_layer
        and reports_layer == enrichment_layer
        and (
            _normalize(reports_row.get("market_level")) == "LAYER"
            or _normalize(enrichment_row.get("market_level")) == "LAYER"
        )
    ):
        return "SAME_LAYER_NAME_DIFFERENT_KEY"

    reports_level = _normalize(reports_row.get("market_level"))
    enrichment_level = _normalize(enrichment_row.get("market_level"))
    if reports_level == "ECOSYSTEM" and enrichment_level == "ECOSYSTEM":
        return "SAME_ECOSYSTEM_DIFFERENT_KEY"

    return "NO_MATCH"


def _find_semantic_match(
    source_row: dict[str, object],
    candidate_rows: list[dict[str, object]],
) -> tuple[dict[str, object] | None, str]:
    for match_type in (
        "SAME_SUBINDUSTRY_NAME_DIFFERENT_KEY",
        "SAME_LAYER_NAME_DIFFERENT_KEY",
        "SAME_ECOSYSTEM_DIFFERENT_KEY",
    ):
        for candidate in candidate_rows:
            current = _semantic_match_type(source_row, candidate)
            if current == match_type:
                return candidate, current
    return None, "NO_MATCH"


def _load_analysis_group_rows(
    analysis_db: str,
    signal_date: str,
) -> list[dict[str, object]]:
    with _connect_read_only(analysis_db) as conn:
        table_name = "dc_dashboard_group_enrichment_daily"
        if not _table_exists(conn, table_name):
            raise ValueError(f"required table missing: {table_name}")
        columns = _table_columns(conn, table_name)
        selected_columns = [
            column
            for column in (
                "signal_date",
                "taxonomy_version",
                "market_level",
                "taxonomy_key",
                "name",
                "parent_name",
                "layer",
                "subindustry",
                "taxonomy_path",
                "current_status",
                "source_horizons",
            )
            if column in columns
        ]
        query = (
            f"SELECT {', '.join(selected_columns)} FROM {table_name} "
            "WHERE signal_date = ? "
            "ORDER BY "
            "CASE UPPER(COALESCE(market_level, '')) "
            "WHEN 'ECOSYSTEM' THEN 0 "
            "WHEN 'LAYER' THEN 1 "
            "WHEN 'SUBINDUSTRY' THEN 2 "
            "ELSE 3 END, "
            "COALESCE(layer, ''), COALESCE(subindustry, ''), COALESCE(name, '')"
        )
        rows = []
        for row in conn.execute(query, (signal_date,)).fetchall():
            data = {key: row[key] for key in row.keys()}
            for field_name in (
                "market_level",
                "taxonomy_key",
                "name",
                "parent_name",
                "layer",
                "subindustry",
                "taxonomy_path",
                "current_status",
                "source_horizons",
            ):
                data.setdefault(field_name, None)
            rows.append(data)
        return rows


def _market_map_counts(rows: list[dict[str, object]]) -> tuple[int, int, int, int, int]:
    ecosystem = 0
    layer = 0
    subindustry = 0
    other = 0
    for row in rows:
        bucket = _market_level_bucket(row)
        if bucket == "ecosystem":
            ecosystem += 1
        elif bucket == "layer":
            layer += 1
        elif bucket == "subindustry":
            subindustry += 1
        else:
            other += 1
    return len(rows), ecosystem, layer, subindustry, other


def _trace_status(row: dict[str, object]) -> str:
    return _cell(row.get("current_status"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose reports vs enrichment market_map parity differences.",
    )
    parser.add_argument("--reports-dashboard-db", required=True)
    parser.add_argument("--reports-run-id", required=True)
    parser.add_argument("--enrichment-dashboard-db", required=True)
    parser.add_argument("--enrichment-run-id", required=True)
    parser.add_argument("--analysis-db-copy", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--max-examples", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

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
        analysis_group_rows = _load_analysis_group_rows(
            analysis_db=args.analysis_db_copy,
            signal_date=args.report_date,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reports_market = _market_row_dict(reports.market_map)
    enrichment_market = _market_row_dict(enrichment.market_map)
    only_reports_keys = sorted(set(reports_market) - set(enrichment_market))
    only_enrichment_keys = sorted(set(enrichment_market) - set(reports_market))
    only_reports_rows = [reports_market[key] for key in only_reports_keys]
    only_enrichment_rows = [enrichment_market[key] for key in only_enrichment_keys]

    reports_only_candidates = only_reports_rows[: args.max_examples]
    enrichment_only_candidates = only_enrichment_rows[: args.max_examples]

    possible_matches: list[tuple[str, str, str, str, str]] = []
    matched_reports_keys: set[str] = set()
    matched_enrichment_keys: set[str] = set()
    missing_parent_layer_count = 0
    source_horizons_missing_count = 0
    ecosystem_key_mismatch_count = 0

    for reports_key in only_reports_keys:
        reports_row = reports_market[reports_key]
        match_row, match_type = _find_semantic_match(reports_row, only_enrichment_rows)
        if match_row is None:
            possible_matches.append(
                (
                    reports_key,
                    "",
                    "NO_MATCH",
                    _trace_status(reports_row),
                    "",
                )
            )
            continue
        enrichment_key = _market_map_key(match_row)
        possible_matches.append(
            (
                reports_key,
                enrichment_key,
                match_type,
                _trace_status(reports_row),
                _trace_status(match_row),
            )
        )
        matched_reports_keys.add(reports_key)
        matched_enrichment_keys.add(enrichment_key)
        if (
            match_type == "SAME_SUBINDUSTRY_NAME_DIFFERENT_KEY"
            and _cell(match_row.get("layer")) == ""
            and _cell(match_row.get("parent_name")) == ""
            and _cell(reports_row.get("layer")) != ""
        ):
            missing_parent_layer_count += 1
        if _cell(reports_row.get("source_horizons")) != "" and _cell(
            match_row.get("source_horizons")
        ) == "":
            source_horizons_missing_count += 1
        if match_type == "SAME_ECOSYSTEM_DIFFERENT_KEY":
            reports_key_upper = reports_key.upper()
            enrichment_key_upper = enrichment_key.upper()
            if "DC_ECOSYSTEM_TOTAL" in reports_key_upper and "ECOSYSTEM|" in enrichment_key_upper:
                ecosystem_key_mismatch_count += 1

    unmatched_enrichment = [
        key for key in only_enrichment_keys if key not in matched_enrichment_keys
    ]

    reports_total, reports_ecosystem, reports_layer, reports_subindustry, reports_other = (
        _market_map_counts(reports.market_map)
    )
    enrichment_total, enrichment_ecosystem, enrichment_layer, enrichment_subindustry, enrichment_other = (
        _market_map_counts(enrichment.market_map)
    )

    reports_shape_counts: dict[str, int] = {}
    for key in sorted(reports_market):
        shape = _shape_for_key(key)
        reports_shape_counts[shape] = reports_shape_counts.get(shape, 0) + 1
    enrichment_shape_counts: dict[str, int] = {}
    for key in sorted(enrichment_market):
        shape = _shape_for_key(key)
        enrichment_shape_counts[shape] = enrichment_shape_counts.get(shape, 0) + 1

    same_name_possible_matches = len(matched_reports_keys)
    min_mismatch_side = min(len(only_reports_keys), len(only_enrichment_keys))
    key_shape_not_content = (
        min_mismatch_side > 0
        and same_name_possible_matches * 5 >= min_mismatch_side * 4
    )
    extra_taxonomy_groups = len(unmatched_enrichment) > 0
    ecosystem_mismatch = ecosystem_key_mismatch_count > 0
    horizons_missing = source_horizons_missing_count > 0

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
        "",
        args.report_date,
        "dc_dashboard_group_enrichment_daily",
    )

    _print_row("section", "market_map_counts")
    _print_row(
        "market_map_counts",
        "source",
        "count",
        "ecosystem_count",
        "layer_count",
        "subindustry_count",
        "other_count",
    )
    _print_row(
        "market_map_counts",
        "reports",
        reports_total,
        reports_ecosystem,
        reports_layer,
        reports_subindustry,
        reports_other,
    )
    _print_row(
        "market_map_counts",
        "enrichment",
        enrichment_total,
        enrichment_ecosystem,
        enrichment_layer,
        enrichment_subindustry,
        enrichment_other,
    )

    _print_row("section", "key_shape_distribution")
    _print_row("key_shape_distribution", "source", "shape", "count")
    for source_name, counts in (
        ("reports", reports_shape_counts),
        ("enrichment", enrichment_shape_counts),
    ):
        for shape in (
            "ECOSYSTEM_PIPE",
            "LAYER_PIPE",
            "SUBINDUSTRY_PIPE",
            "ECOSYSTEM_GT_LAYER_GT_SUBINDUSTRY",
            "DC_ECOSYSTEM_TOTAL_GT_LAYER",
            "OTHER",
        ):
            _print_row("key_shape_distribution", source_name, shape, counts.get(shape, 0))

    _print_row("section", "only_reports_market_map")
    _print_row(
        "only_reports_market_map",
        "key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "current_status",
        "source_horizons",
    )
    for row in reports_only_candidates:
        _print_row(
            "only_reports_market_map",
            _market_map_key(row),
            row.get("market_level"),
            row.get("name"),
            row.get("parent_name"),
            row.get("layer"),
            row.get("subindustry"),
            row.get("current_status"),
            row.get("source_horizons"),
        )

    _print_row("section", "only_enrichment_market_map")
    _print_row(
        "only_enrichment_market_map",
        "key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "current_status",
        "source_horizons",
    )
    for row in enrichment_only_candidates:
        _print_row(
            "only_enrichment_market_map",
            _market_map_key(row),
            row.get("market_level"),
            row.get("name"),
            row.get("parent_name"),
            row.get("layer"),
            row.get("subindustry"),
            row.get("current_status"),
            row.get("source_horizons"),
        )

    _print_row("section", "possible_key_matches")
    _print_row(
        "possible_key_matches",
        "reports_key",
        "enrichment_key",
        "match_type",
        "reports_status",
        "enrichment_status",
    )
    for reports_key, enrichment_key, match_type, reports_status, enrichment_status in possible_matches[
        : args.max_examples
    ]:
        _print_row(
            "possible_key_matches",
            reports_key,
            enrichment_key,
            match_type,
            reports_status,
            enrichment_status,
        )

    _print_row("section", "analysis_group_rows")
    _print_row(
        "analysis_group_rows",
        "taxonomy_key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "taxonomy_path",
        "current_status",
        "source_horizons",
    )
    for row in analysis_group_rows[: args.max_examples]:
        _print_row(
            "analysis_group_rows",
            row.get("taxonomy_key"),
            row.get("market_level"),
            row.get("name"),
            row.get("parent_name"),
            row.get("layer"),
            row.get("subindustry"),
            row.get("taxonomy_path"),
            row.get("current_status"),
            row.get("source_horizons"),
        )

    _print_row("section", "hypothesis_summary")
    _print_row("hypothesis_summary", "hypothesis", "status", "evidence")
    _print_row(
        "hypothesis_summary",
        "MARKET_MAP_DIFF_IS_KEY_SHAPE_NOT_CONTENT",
        "LIKELY" if key_shape_not_content else "UNLIKELY",
        f"only_reports={len(only_reports_keys)};only_enrichment={len(only_enrichment_keys)};"
        f"same_name_possible_matches={same_name_possible_matches}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_MISSING_PARENT_LAYER_FOR_SUBINDUSTRIES",
        "LIKELY" if missing_parent_layer_count > 0 else "UNLIKELY",
        f"missing_parent_layer_matches={missing_parent_layer_count}",
    )
    _print_row(
        "hypothesis_summary",
        "ENRICHMENT_HAS_EXTRA_TAXONOMY_GROUPS",
        "LIKELY" if extra_taxonomy_groups else "UNLIKELY",
        f"unmatched_enrichment={len(unmatched_enrichment)}",
    )
    _print_row(
        "hypothesis_summary",
        "ECOSYSTEM_KEY_MISMATCH",
        "LIKELY" if ecosystem_mismatch else "UNLIKELY",
        f"ecosystem_key_mismatch_count={ecosystem_key_mismatch_count}",
    )
    _print_row(
        "hypothesis_summary",
        "SOURCE_HORIZONS_MISSING_IN_ENRICHMENT",
        "LIKELY" if horizons_missing else "UNLIKELY",
        f"source_horizons_missing_matches={source_horizons_missing_count}",
    )

    _print_row("section", "summary")
    print("SUMMARY datacenter_dashboard_market_map_parity_diagnosis.status=OK")
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.report_date="
        f"{args.report_date}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.reports_market_map="
        f"{len(reports.market_map)}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.enrichment_market_map="
        f"{len(enrichment.market_map)}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.only_reports="
        f"{len(only_reports_keys)}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.only_enrichment="
        f"{len(only_enrichment_keys)}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.same_name_possible_matches="
        f"{same_name_possible_matches}"
    )
    print(
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.unmatched_enrichment="
        f"{len(unmatched_enrichment)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
