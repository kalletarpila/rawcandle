from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    DEFAULT_CALC_VERSION,
    _build_group_definitions,
    _build_in_range_dates,
    _build_ticker_daily_inputs,
    _load_price_rows,
    _load_taxonomy_rows,
    build_group_synthetic_ohlc_rows,
)


DEFAULT_OUTPUT_DIR = Path("temp/datacenter_effective_weight_calculation_only")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare persisted equal-weight DC synthetic OHLC with membership-weighted shadow rows."
    )
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--price-db", type=Path, required=True)
    parser.add_argument("--taxonomy-csv", type=Path, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument(
        "--chain-start-date",
        help="Weighted chain start; defaults to --start-date.",
    )
    parser.add_argument("--market", default=None)
    parser.add_argument("--calc-version", default=DEFAULT_CALC_VERSION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def _validated_output_dir(path: Path) -> Path:
    allowed_root = DEFAULT_OUTPUT_DIR.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(
            f"output-dir must be under {allowed_root}, got {resolved}"
        ) from exc
    return resolved


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def _load_equal_rows(
    analysis_db: Path,
    *,
    taxonomy_versions: list[str],
    start_date: str,
    end_date: str,
    calc_version: str,
) -> dict[tuple[str, str, str, str], sqlite3.Row]:
    placeholders = ", ".join("?" for _ in taxonomy_versions)
    with _readonly_connection(analysis_db) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM dc_group_synthetic_ohlc_daily
            WHERE taxonomy_version IN ({placeholders})
              AND ohlc_date >= ?
              AND ohlc_date <= ?
              AND calc_version = ?
            ORDER BY taxonomy_version, group_type, group_name, ohlc_date
            """,
            (*taxonomy_versions, start_date, end_date, calc_version),
        ).fetchall()
    return {
        (
            str(row["taxonomy_version"]),
            str(row["group_type"]),
            str(row["group_name"]),
            str(row["ohlc_date"]),
        ): row
        for row in rows
    }


def _daily_returns(
    rows: list[object],
    *,
    key_getter,
    date_getter,
    close_getter,
) -> dict[tuple[str, str, str, str], float | None]:
    grouped: dict[tuple[str, str, str], list[object]] = defaultdict(list)
    for row in rows:
        grouped[key_getter(row)].append(row)
    result: dict[tuple[str, str, str, str], float | None] = {}
    for group_key, group_rows in grouped.items():
        previous_close: float | None = None
        for row in sorted(group_rows, key=date_getter):
            close = close_getter(row)
            current_return = None
            if close is not None and previous_close not in (None, 0):
                current_return = (float(close) / float(previous_close)) - 1.0
            result[(*group_key, date_getter(row))] = current_return
            if close is not None:
                previous_close = float(close)
    return result


def run_shadow_comparison(
    *,
    analysis_db: Path,
    price_db: Path,
    taxonomy_csv: Path,
    start_date: str,
    end_date: str,
    chain_start_date: str,
    market: str | None,
    calc_version: str,
    output_dir: Path,
) -> dict[str, object]:
    if chain_start_date > start_date:
        raise ValueError("chain-start-date must not be after start-date")
    output_dir = _validated_output_dir(output_dir)
    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv)
    taxonomy_versions = sorted({str(row.taxonomy_version) for row in taxonomy_rows})
    equal_rows = _load_equal_rows(
        analysis_db,
        taxonomy_versions=taxonomy_versions,
        start_date=start_date,
        end_date=end_date,
        calc_version=calc_version,
    )
    weighted_rows, _summary = build_group_synthetic_ohlc_rows(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=chain_start_date,
        end_date=end_date,
        market=market,
        calc_version=calc_version,
        run_id="MEMBERSHIP_WEIGHTED_SHADOW",
        created_at_utc="1970-01-01T00:00:00Z",
    )
    weighted_rows = [
        row for row in weighted_rows if start_date <= row.ohlc_date <= end_date
    ]

    equal_return_rows = list(equal_rows.values())
    equal_returns = _daily_returns(
        equal_return_rows,
        key_getter=lambda row: (
            str(row["taxonomy_version"]),
            str(row["group_type"]),
            str(row["group_name"]),
        ),
        date_getter=lambda row: str(row["ohlc_date"]),
        close_getter=lambda row: row["synthetic_close"],
    )
    weighted_returns = _daily_returns(
        weighted_rows,
        key_getter=lambda row: (
            row.taxonomy_version,
            row.group_type,
            row.group_name,
        ),
        date_getter=lambda row: row.ohlc_date,
        close_getter=lambda row: row.synthetic_close,
    )

    diagnostics: list[dict[str, object]] = []
    for taxonomy_version in taxonomy_versions:
        version_rows = [
            row for row in taxonomy_rows if str(row.taxonomy_version) == taxonomy_version
        ]
        groups = _build_group_definitions(version_rows)
        tickers = sorted({membership.ticker for group in groups for membership in group.memberships})
        prices = _load_price_rows(
            price_db_path=price_db,
            tickers=tickers,
            market=market,
            end_date=end_date,
        )
        ticker_inputs, all_dates = _build_ticker_daily_inputs(prices)
        comparison_dates = _build_in_range_dates(
            all_dates,
            start_date=start_date,
            end_date=end_date,
        )
        weighted_by_key = {
            (row.group_type, row.group_name, row.ohlc_date): row
            for row in weighted_rows
            if row.taxonomy_version == taxonomy_version
        }

        for group in groups:
            memberships = group.memberships
            for current_date in comparison_dates:
                eligible = [
                    membership
                    for membership in memberships
                    if membership.ticker in ticker_inputs
                    and current_date in ticker_inputs[membership.ticker]
                ]
                eligible_positive = [
                    membership
                    for membership in eligible
                    if membership.effective_weight > 0
                ]
                total_weight = sum(
                    membership.effective_weight for membership in memberships
                )
                eligible_weight = sum(
                    membership.effective_weight for membership in eligible_positive
                )
                primary_weight = sum(
                    membership.effective_weight
                    for membership in eligible_positive
                    if membership.is_primary == 1
                )
                secondary_weight = eligible_weight - primary_weight
                normalized = sorted(
                    (
                        membership.effective_weight / eligible_weight
                        for membership in eligible_positive
                    ),
                    reverse=True,
                ) if eligible_weight > 0 else []
                effective_member_count = (
                    1.0 / sum(weight * weight for weight in normalized)
                    if normalized
                    else 0.0
                )
                key = (
                    taxonomy_version,
                    group.group_type,
                    group.group_name,
                    current_date,
                )
                equal = equal_rows.get(key)
                weighted = weighted_by_key.get(
                    (group.group_type, group.group_name, current_date)
                )
                equal_close = None if equal is None else equal["synthetic_close"]
                weighted_close = (
                    None if weighted is None else weighted.synthetic_close
                )
                close_delta = (
                    None
                    if equal_close is None or weighted_close is None
                    else float(weighted_close) - float(equal_close)
                )
                close_pct_delta = (
                    None
                    if close_delta is None or float(equal_close) == 0
                    else close_delta / float(equal_close)
                )
                diagnostics.append(
                    {
                        "taxonomy_version": taxonomy_version,
                        "group_type": group.group_type,
                        "group_name": group.group_name,
                        "date": current_date,
                        "raw_member_count": len(memberships),
                        "primary_member_count": sum(m.is_primary == 1 for m in memberships),
                        "secondary_member_count": sum(m.is_primary == 0 for m in memberships),
                        "watch_only_member_count": sum(m.report_group_status == "WATCH_ONLY" for m in memberships),
                        "too_small_member_count": sum(m.report_group_status == "TOO_SMALL" for m in memberships),
                        "positive_weight_member_count": sum(m.effective_weight > 0 for m in memberships),
                        "eligible_positive_weight_member_count": len(eligible_positive),
                        "total_effective_weight": total_weight,
                        "eligible_effective_weight": eligible_weight,
                        "primary_effective_weight": primary_weight,
                        "secondary_effective_weight": secondary_weight,
                        "primary_effective_weight_share": primary_weight / eligible_weight if eligible_weight else 0.0,
                        "secondary_effective_weight_share": secondary_weight / eligible_weight if eligible_weight else 0.0,
                        "largest_normalized_weight": normalized[0] if normalized else 0.0,
                        "top3_normalized_weight_share": sum(normalized[:3]),
                        "effective_member_count": effective_member_count,
                        "equal_synthetic_close": equal_close,
                        "weighted_synthetic_close": weighted_close,
                        "close_delta": close_delta,
                        "close_pct_delta": close_pct_delta,
                        "equal_daily_return": equal_returns.get(key),
                        "weighted_daily_return": weighted_returns.get(key),
                    }
                )

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "group_date_comparison.csv"
    fieldnames = list(diagnostics[0]) if diagnostics else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(diagnostics)

    comparable = [
        row for row in diagnostics if row["close_pct_delta"] is not None
    ]
    summary = {
        "status": "OK",
        "mode": "CALCULATION_ONLY_NO_DB_WRITES",
        "start_date": start_date,
        "end_date": end_date,
        "chain_start_date": chain_start_date,
        "calc_version": calc_version,
        "taxonomy_versions": taxonomy_versions,
        "diagnostic_row_count": len(diagnostics),
        "equal_source_row_count": len(equal_rows),
        "comparable_close_row_count": len(comparable),
        "max_absolute_close_pct_delta": max(
            (abs(float(row["close_pct_delta"])) for row in comparable),
            default=None,
        ),
        "comparison_csv": str(csv_path),
        "structure_shadow_included": False,
        "structure_shadow_next_step": "Run chain-safe weighted structure validation before production rebuild planning.",
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**summary, "summary_json": str(summary_path)}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = run_shadow_comparison(
            analysis_db=args.analysis_db,
            price_db=args.price_db,
            taxonomy_csv=args.taxonomy_csv,
            start_date=args.start_date,
            end_date=args.end_date,
            chain_start_date=args.chain_start_date or args.start_date,
            market=args.market,
            calc_version=args.calc_version,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"ERROR {exc}")
        return 1
    for key in sorted(summary):
        print(f"SUMMARY {key}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
