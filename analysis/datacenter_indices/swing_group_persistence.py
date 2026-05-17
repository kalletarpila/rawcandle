from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from analysis.database_manager import DatabaseManager

from .persistence import resolve_created_at_utc
from .taxonomy import DatacenterTaxonomyRow, load_datacenter_taxonomy_csv


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_MIN_ELIGIBLE_COUNT = 3
DEFAULT_MIN_COVERAGE_RATIO = 0.60

GROUP_SWING_SUMMARY_ORDER = [
    "signal_date",
    "write_mode",
    "signal_version",
    "run_id",
    "taxonomy_rows",
    "taxonomy_versions",
    "group_rows",
    "inserted_count",
    "updated_count",
    "upserted_count",
    "skipped_existing_count",
    "deleted_count",
    "ok_group_count",
    "partial_data_group_count",
    "too_small_group_count",
    "no_data_group_count",
    "validation_status",
]

GROUP_SWING_TIMING_SUMMARY_ORDER = [
    "start_date",
    "end_date",
    "write_mode",
    "signal_version",
    "run_id",
    "updated_count",
    "missing_base_row_count",
    "cleared_count",
    "buy_zone_count",
    "add_on_pullback_count",
    "trim_watch_count",
    "exit_zone_count",
    "neutral_count",
    "validation_status",
]

GROUP_TYPE_ORDER = {
    "ecosystem": 0,
    "layer": 1,
    "subindustry": 2,
}

ELIGIBLE_PRICE_STATUSES = {"OK", "INSUFFICIENT_HISTORY"}


@dataclass(frozen=True)
class DatacenterGroupSwingSignalRow:
    signal_date: str
    taxonomy_version: str
    group_type: str
    group_name: str
    member_count: int
    eligible_count: int
    return_5d: float | None
    return_10d: float | None
    return_20d: float | None
    return_60d: float | None
    pct_above_ma10: float | None
    pct_above_ema20: float | None
    pct_above_rising_ema20: float | None
    ma10_breadth_delta_5d: float | None
    ema20_breadth_delta_5d: float | None
    trend_breadth: float | None
    weakness_breadth: float | None
    overheat_risk_level: str | None
    timing_state: str | None
    timing_reason: str | None
    data_quality_status: str
    signal_version: str
    run_id: str
    created_at_utc: str


def _normalize_ticker(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def build_group_swing_run_id(
    *,
    as_of_date: str,
    signal_version: str,
    run_id: str | None = None,
) -> str:
    if run_id is not None:
        return run_id
    compact_date = as_of_date.replace("-", "")
    return f"DC_GROUP_SWING_{compact_date}_{signal_version}".replace(" ", "_")


def format_group_swing_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in GROUP_SWING_SUMMARY_ORDER]


def format_group_swing_timing_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in GROUP_SWING_TIMING_SUMMARY_ORDER]


def _match_lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


def _match_gt(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def _match_gte(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _timing_state_and_reason(row: sqlite3.Row) -> tuple[str, str]:
    data_quality_status = str(row["data_quality_status"]) if row["data_quality_status"] is not None else ""
    return_5d = None if row["return_5d"] is None else float(row["return_5d"])
    return_10d = None if row["return_10d"] is None else float(row["return_10d"])
    return_20d = None if row["return_20d"] is None else float(row["return_20d"])
    return_60d = None if row["return_60d"] is None else float(row["return_60d"])
    pct_above_ma10 = None if row["pct_above_ma10"] is None else float(row["pct_above_ma10"])
    pct_above_ema20 = None if row["pct_above_ema20"] is None else float(row["pct_above_ema20"])
    ema20_breadth_delta_5d = None if row["ema20_breadth_delta_5d"] is None else float(row["ema20_breadth_delta_5d"])
    weakness_breadth = None if row["weakness_breadth"] is None else float(row["weakness_breadth"])

    exit_reasons: list[str] = []
    if _match_lt(ema20_breadth_delta_5d, -15.0):
        exit_reasons.append("ema20_breadth_delta_5d_lt_minus_15")
    if _match_lt(return_20d, 0.0):
        exit_reasons.append("return_20d_neg")
    if _match_lt(pct_above_ema20, 40.0):
        exit_reasons.append("pct_above_ema20_lt_40")
    if _match_gt(weakness_breadth, 60.0):
        exit_reasons.append("weakness_breadth_gt_60")
    if exit_reasons:
        return "EXIT_ZONE", "EXIT_ZONE:" + ";".join(exit_reasons)

    trim_reasons: list[str] = []
    if _match_lt(ema20_breadth_delta_5d, -10.0):
        trim_reasons.append("ema20_breadth_delta_5d_lt_minus_10")
    if _match_lt(return_10d, 0.0):
        trim_reasons.append("return_10d_neg")
    if _match_lt(pct_above_ma10, 50.0):
        trim_reasons.append("pct_above_ma10_lt_50")
    if trim_reasons:
        return "TRIM_WATCH", "TRIM_WATCH:" + ";".join(trim_reasons)

    add_on_checks = [
        (_match_gt(return_20d, 0.0), "return_20d_pos"),
        (_match_gt(return_60d, 0.0), "return_60d_pos"),
        (_match_lt(return_5d, 0.0) and _match_gte(return_5d, -0.05), "return_5d_pullback_ge_minus_5pct"),
        (_match_gte(pct_above_ema20, 65.0), "pct_above_ema20_ge_65"),
        (data_quality_status == "OK", "data_quality_ok"),
    ]
    if all(matched for matched, _ in add_on_checks):
        return "ADD_ON_PULLBACK", "ADD_ON_PULLBACK:" + ";".join(code for _, code in add_on_checks)

    buy_checks = [
        (_match_gt(return_5d, 0.0), "return_5d_pos"),
        (_match_gt(return_10d, 0.0), "return_10d_pos"),
        (_match_gte(pct_above_ema20, 80.0), "pct_above_ema20_ge_80"),
        (_match_gte(ema20_breadth_delta_5d, -10.0), "ema20_breadth_delta_5d_ge_minus_10"),
        (data_quality_status == "OK", "data_quality_ok"),
    ]
    if all(matched for matched, _ in buy_checks):
        return "BUY_ZONE", "BUY_ZONE:" + ";".join(code for _, code in buy_checks)

    return "NEUTRAL", "NEUTRAL:no_state_rule_matched"


def _load_taxonomy_rows(
    taxonomy_csv_path: str | Path,
) -> list[DatacenterTaxonomyRow]:
    return load_datacenter_taxonomy_csv(taxonomy_csv_path)


def _build_group_definitions(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
) -> list[tuple[str, str, tuple[str, ...]]]:
    ecosystem_tickers = tuple(sorted({_normalize_ticker(row.ticker) for row in taxonomy_rows}))
    layer_map: dict[str, set[str]] = {}
    subindustry_map: dict[str, set[str]] = {}
    for row in taxonomy_rows:
        ticker = _normalize_ticker(row.ticker)
        layer_map.setdefault(str(row.layer), set()).add(ticker)
        subindustry_map.setdefault(str(row.subindustry), set()).add(ticker)

    groups: list[tuple[str, str, tuple[str, ...]]] = [
        ("ecosystem", "DC_ECOSYSTEM_TOTAL", ecosystem_tickers)
    ]
    groups.extend(
        ("layer", layer, tuple(sorted(tickers)))
        for layer, tickers in sorted(layer_map.items())
    )
    groups.extend(
        ("subindustry", subindustry, tuple(sorted(tickers)))
        for subindustry, tickers in sorted(subindustry_map.items())
    )
    return groups


def _load_ticker_snapshots(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND signal_version = ?
        ORDER BY ticker ASC
        """,
        (signal_date, taxonomy_version, signal_version),
    ).fetchall()
    return {str(row["ticker"]): row for row in rows}


def _calculate_group_return_from_index_levels(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    group_type: str,
    group_name: str,
    lookback: int,
) -> float | None:
    rows = conn.execute(
        """
        SELECT index_date, index_level_equal
        FROM dc_group_index_daily
        WHERE taxonomy_version = ?
          AND group_type = ?
          AND group_name = ?
          AND index_date <= ?
          AND index_level_equal IS NOT NULL
        ORDER BY index_date ASC
        """,
        (taxonomy_version, group_type, group_name, signal_date),
    ).fetchall()
    if not rows:
        return None
    if str(rows[-1]["index_date"]) != signal_date:
        return None
    if len(rows) <= lookback:
        return None
    current_level = float(rows[-1]["index_level_equal"])
    previous_level = float(rows[-(lookback + 1)]["index_level_equal"])
    if previous_level == 0:
        return None
    return (current_level / previous_level) - 1.0


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return 100.0 * float(numerator) / float(denominator)


def _count_int_flag(rows: Sequence[sqlite3.Row], field_name: str, expected: int = 1) -> tuple[int, int]:
    eligible = [row for row in rows if row[field_name] is not None]
    matches = sum(1 for row in eligible if int(row[field_name]) == expected)
    return matches, len(eligible)


def _calculate_breadth_metrics(
    member_tickers: Sequence[str],
    snapshots_by_ticker: dict[str, sqlite3.Row],
) -> tuple[int, int, float | None, float | None, float | None, float | None, float | None]:
    member_count = len(set(member_tickers))
    member_snapshot_rows = [
        snapshots_by_ticker[ticker]
        for ticker in sorted(set(member_tickers))
        if ticker in snapshots_by_ticker
    ]
    eligible_rows = [
        row
        for row in member_snapshot_rows
        if str(row["price_data_status"]) in ELIGIBLE_PRICE_STATUSES
    ]
    eligible_count = len(eligible_rows)

    above_ma10_yes, above_ma10_den = _count_int_flag(eligible_rows, "above_ma10")
    above_ema20_yes, above_ema20_den = _count_int_flag(eligible_rows, "above_ema20")

    rising_ema20_eligible = [
        row
        for row in eligible_rows
        if row["above_ema20"] is not None and row["ema20_slope_positive"] is not None
    ]
    pct_above_rising_ema20 = _pct(
        sum(
            1
            for row in rising_ema20_eligible
            if int(row["above_ema20"]) == 1 and int(row["ema20_slope_positive"]) == 1
        ),
        len(rising_ema20_eligible),
    )

    structure_eligible = [
        row for row in member_snapshot_rows if row["latest_structure_label"] is not None
    ]
    trend_breadth = _pct(
        sum(
            1
            for row in structure_eligible
            if str(row["latest_structure_label"]) in {"HH", "HL"}
        ),
        len(structure_eligible),
    )
    weakness_breadth = _pct(
        sum(
            1
            for row in structure_eligible
            if str(row["latest_structure_label"]) in {"LH", "LL"}
        ),
        len(structure_eligible),
    )

    return (
        member_count,
        eligible_count,
        _pct(above_ma10_yes, above_ma10_den),
        _pct(above_ema20_yes, above_ema20_den),
        pct_above_rising_ema20,
        trend_breadth,
        weakness_breadth,
    )


def _load_prior_breadth_value(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    group_type: str,
    group_name: str,
    signal_version: str,
    field_name: str,
    lookback: int = 5,
) -> float | None:
    rows = conn.execute(
        f"""
        SELECT {field_name}
        FROM dc_group_swing_signal_daily
        WHERE taxonomy_version = ?
          AND group_type = ?
          AND group_name = ?
          AND signal_version = ?
          AND signal_date < ?
          AND {field_name} IS NOT NULL
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (taxonomy_version, group_type, group_name, signal_version, signal_date, lookback),
    ).fetchall()
    if len(rows) < lookback:
        return None
    return float(rows[-1][0])


def _calculate_data_quality_status(
    *,
    member_count: int,
    eligible_count: int,
    min_eligible_count: int,
    min_coverage_ratio: float,
) -> str:
    if member_count == 0 or eligible_count == 0:
        return "NO_DATA"
    if eligible_count < min_eligible_count:
        return "TOO_SMALL"
    coverage_ratio = float(eligible_count) / float(member_count)
    if coverage_ratio < min_coverage_ratio:
        return "PARTIAL_DATA"
    return "OK"


def build_group_swing_signal_rows(
    *,
    analysis_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    signal_date: str,
    signal_version: str,
    run_id: str,
    created_at_utc: str,
    min_eligible_count: int = DEFAULT_MIN_ELIGIBLE_COUNT,
    min_coverage_ratio: float = DEFAULT_MIN_COVERAGE_RATIO,
) -> tuple[list[DatacenterGroupSwingSignalRow], dict[str, int | str]]:
    normalized_signal_date = _parse_iso_date(signal_date, "signal_date")
    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv_path)
    rows_out: list[DatacenterGroupSwingSignalRow] = []

    taxonomy_versions = sorted({str(row.taxonomy_version) for row in taxonomy_rows})
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        for taxonomy_version in taxonomy_versions:
            version_rows = [
                row for row in taxonomy_rows if str(row.taxonomy_version) == taxonomy_version
            ]
            groups = _build_group_definitions(version_rows)
            ticker_snapshots = _load_ticker_snapshots(
                conn,
                signal_date=normalized_signal_date,
                taxonomy_version=taxonomy_version,
                signal_version=signal_version,
            )
            for group_type, group_name, group_tickers in groups:
                (
                    member_count,
                    eligible_count,
                    pct_above_ma10,
                    pct_above_ema20,
                    pct_above_rising_ema20,
                    trend_breadth,
                    weakness_breadth,
                ) = _calculate_breadth_metrics(group_tickers, ticker_snapshots)

                return_5d = _calculate_group_return_from_index_levels(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    lookback=5,
                )
                return_10d = _calculate_group_return_from_index_levels(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    lookback=10,
                )
                return_20d = _calculate_group_return_from_index_levels(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    lookback=20,
                )
                return_60d = _calculate_group_return_from_index_levels(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    lookback=60,
                )

                prior_ma10_breadth = _load_prior_breadth_value(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    signal_version=signal_version,
                    field_name="pct_above_ma10",
                )
                prior_ema20_breadth = _load_prior_breadth_value(
                    conn,
                    signal_date=normalized_signal_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    signal_version=signal_version,
                    field_name="pct_above_ema20",
                )

                rows_out.append(
                    DatacenterGroupSwingSignalRow(
                        signal_date=normalized_signal_date,
                        taxonomy_version=taxonomy_version,
                        group_type=group_type,
                        group_name=group_name,
                        member_count=member_count,
                        eligible_count=eligible_count,
                        return_5d=return_5d,
                        return_10d=return_10d,
                        return_20d=return_20d,
                        return_60d=return_60d,
                        pct_above_ma10=pct_above_ma10,
                        pct_above_ema20=pct_above_ema20,
                        pct_above_rising_ema20=pct_above_rising_ema20,
                        ma10_breadth_delta_5d=None
                        if pct_above_ma10 is None or prior_ma10_breadth is None
                        else pct_above_ma10 - prior_ma10_breadth,
                        ema20_breadth_delta_5d=None
                        if pct_above_ema20 is None or prior_ema20_breadth is None
                        else pct_above_ema20 - prior_ema20_breadth,
                        trend_breadth=trend_breadth,
                        weakness_breadth=weakness_breadth,
                        overheat_risk_level=None,
                        timing_state=None,
                        timing_reason=None,
                        data_quality_status=_calculate_data_quality_status(
                            member_count=member_count,
                            eligible_count=eligible_count,
                            min_eligible_count=min_eligible_count,
                            min_coverage_ratio=min_coverage_ratio,
                        ),
                        signal_version=signal_version,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                    )
                )

    summary = {
        "taxonomy_rows": len(taxonomy_rows),
        "taxonomy_versions": len(taxonomy_versions),
        "group_rows": len(rows_out),
        "ok_group_count": sum(1 for row in rows_out if row.data_quality_status == "OK"),
        "partial_data_group_count": sum(1 for row in rows_out if row.data_quality_status == "PARTIAL_DATA"),
        "too_small_group_count": sum(1 for row in rows_out if row.data_quality_status == "TOO_SMALL"),
        "no_data_group_count": sum(1 for row in rows_out if row.data_quality_status == "NO_DATA"),
    }
    return sorted(
        rows_out,
        key=lambda row: (
            row.taxonomy_version,
            GROUP_TYPE_ORDER[row.group_type],
            row.group_name,
        ),
    ), summary


def _serialize_row(row: DatacenterGroupSwingSignalRow) -> tuple[object, ...]:
    return (
        row.signal_date,
        row.taxonomy_version,
        row.group_type,
        row.group_name,
        row.member_count,
        row.eligible_count,
        row.return_5d,
        row.return_10d,
        row.return_20d,
        row.return_60d,
        row.pct_above_ma10,
        row.pct_above_ema20,
        row.pct_above_rising_ema20,
        row.ma10_breadth_delta_5d,
        row.ema20_breadth_delta_5d,
        row.trend_breadth,
        row.weakness_breadth,
        row.overheat_risk_level,
        row.timing_state,
        row.timing_reason,
        row.data_quality_status,
        row.signal_version,
        row.run_id,
        row.created_at_utc,
    )


def _row_key(row: DatacenterGroupSwingSignalRow) -> tuple[str, str, str, str, str]:
    return (
        row.signal_date,
        row.taxonomy_version,
        row.group_type,
        row.group_name,
        row.signal_version,
    )


def write_group_swing_signal_rows(
    *,
    analysis_db_path: str | Path,
    rows: Sequence[DatacenterGroupSwingSignalRow],
    signal_date: str,
    signal_version: str,
    write_mode: str,
) -> dict[str, int]:
    normalized_signal_date = _parse_iso_date(signal_date, "signal_date")
    if write_mode not in {"insert-missing", "upsert", "replace-date"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    taxonomy_versions = sorted({row.taxonomy_version for row in rows})
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    inserted_count = 0
    updated_count = 0
    skipped_existing_count = 0
    deleted_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-date":
            if taxonomy_versions:
                placeholders = ", ".join("?" for _ in taxonomy_versions)
                cursor.execute(
                    f"""
                    DELETE FROM dc_group_swing_signal_daily
                    WHERE signal_date = ?
                      AND signal_version = ?
                      AND taxonomy_version IN ({placeholders})
                    """,
                    [normalized_signal_date, signal_version, *taxonomy_versions],
                )
                deleted_count = cursor.rowcount
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO dc_group_swing_signal_daily (
                        signal_date, taxonomy_version, group_type, group_name,
                        member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                        pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                        ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                        trend_breadth, weakness_breadth, overheat_risk_level,
                        timing_state, timing_reason, data_quality_status,
                        signal_version, run_id, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _serialize_row(row),
                )
                inserted_count += 1
        else:
            existing_keys = {
                (
                    str(existing_row[0]),
                    str(existing_row[1]),
                    str(existing_row[2]),
                    str(existing_row[3]),
                    str(existing_row[4]),
                )
                for existing_row in cursor.execute(
                    """
                    SELECT signal_date, taxonomy_version, group_type, group_name, signal_version
                    FROM dc_group_swing_signal_daily
                    WHERE signal_date = ?
                      AND signal_version = ?
                    """,
                    (normalized_signal_date, signal_version),
                ).fetchall()
            }
            for row in rows:
                key = _row_key(row)
                if write_mode == "insert-missing":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO dc_group_swing_signal_daily (
                            signal_date, taxonomy_version, group_type, group_name,
                            member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                            pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                            ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                            trend_breadth, weakness_breadth, overheat_risk_level,
                            timing_state, timing_reason, data_quality_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _serialize_row(row),
                    )
                    if cursor.rowcount == 1:
                        inserted_count += 1
                    else:
                        skipped_existing_count += 1
                else:
                    cursor.execute(
                        """
                        INSERT INTO dc_group_swing_signal_daily (
                            signal_date, taxonomy_version, group_type, group_name,
                            member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                            pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                            ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                            trend_breadth, weakness_breadth, overheat_risk_level,
                            timing_state, timing_reason, data_quality_status,
                            signal_version, run_id, created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_date, taxonomy_version, group_type, group_name, signal_version)
                        DO UPDATE SET
                            member_count = excluded.member_count,
                            eligible_count = excluded.eligible_count,
                            return_5d = excluded.return_5d,
                            return_10d = excluded.return_10d,
                            return_20d = excluded.return_20d,
                            return_60d = excluded.return_60d,
                            pct_above_ma10 = excluded.pct_above_ma10,
                            pct_above_ema20 = excluded.pct_above_ema20,
                            pct_above_rising_ema20 = excluded.pct_above_rising_ema20,
                            ma10_breadth_delta_5d = excluded.ma10_breadth_delta_5d,
                            ema20_breadth_delta_5d = excluded.ema20_breadth_delta_5d,
                            trend_breadth = excluded.trend_breadth,
                            weakness_breadth = excluded.weakness_breadth,
                            overheat_risk_level = excluded.overheat_risk_level,
                            timing_state = excluded.timing_state,
                            timing_reason = excluded.timing_reason,
                            data_quality_status = excluded.data_quality_status,
                            run_id = excluded.run_id,
                            created_at_utc = excluded.created_at_utc
                        """,
                        _serialize_row(row),
                    )
                    if key in existing_keys:
                        updated_count += 1
                    else:
                        inserted_count += 1
        conn.commit()
        return {
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "upserted_count": inserted_count + updated_count if write_mode == "upsert" else 0,
            "skipped_existing_count": skipped_existing_count,
            "deleted_count": deleted_count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        db_manager.close()


def _load_existing_group_swing_rows(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    signal_version: str,
    group_types: Sequence[str] | None = None,
) -> list[sqlite3.Row]:
    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    conn.row_factory = sqlite3.Row
    try:
        params: list[object] = [start_date, end_date, signal_version]
        group_type_clause = ""
        if group_types:
            placeholders = ", ".join("?" for _ in group_types)
            group_type_clause = f" AND group_type IN ({placeholders})"
            params.extend(group_types)
        return conn.execute(
            f"""
            SELECT *
            FROM dc_group_swing_signal_daily
            WHERE signal_date >= ?
              AND signal_date <= ?
              AND signal_version = ?
              {group_type_clause}
            ORDER BY signal_date ASC, taxonomy_version ASC, group_type ASC, group_name ASC
            """,
            params,
        ).fetchall()
    finally:
        db_manager.close()


def build_group_timing_updates(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str,
    signal_version: str,
    run_id: str,
    created_at_utc: str,
    group_types: Sequence[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, int | str]]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )

    rows = _load_existing_group_swing_rows(
        analysis_db_path=analysis_db_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
        group_types=group_types,
    )
    updates: list[dict[str, object]] = []
    counts = {
        "BUY_ZONE": 0,
        "ADD_ON_PULLBACK": 0,
        "TRIM_WATCH": 0,
        "EXIT_ZONE": 0,
        "NEUTRAL": 0,
    }
    for row in rows:
        timing_state, timing_reason = _timing_state_and_reason(row)
        counts[timing_state] += 1
        updates.append(
            {
                "signal_date": str(row["signal_date"]),
                "taxonomy_version": str(row["taxonomy_version"]),
                "group_type": str(row["group_type"]),
                "group_name": str(row["group_name"]),
                "signal_version": str(row["signal_version"]),
                "timing_state": timing_state,
                "timing_reason": timing_reason,
                "run_id": run_id,
                "created_at_utc": created_at_utc,
                "existing_timing_state": None if row["timing_state"] is None else str(row["timing_state"]),
                "existing_timing_reason": None if row["timing_reason"] is None else str(row["timing_reason"]),
            }
        )
    return updates, {
        "missing_base_row_count": 0,
        "buy_zone_count": counts["BUY_ZONE"],
        "add_on_pullback_count": counts["ADD_ON_PULLBACK"],
        "trim_watch_count": counts["TRIM_WATCH"],
        "exit_zone_count": counts["EXIT_ZONE"],
        "neutral_count": counts["NEUTRAL"],
    }


def write_group_timing_updates(
    *,
    analysis_db_path: str | Path,
    updates: Sequence[dict[str, object]],
    start_date: str,
    end_date: str,
    signal_version: str,
    write_mode: str,
    group_types: Sequence[str] | None = None,
) -> dict[str, int]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if write_mode not in {"update-existing", "replace-timing-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")

    db_manager = DatabaseManager(str(analysis_db_path))
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    updated_count = 0
    cleared_count = 0
    try:
        cursor.execute("BEGIN")
        if write_mode == "replace-timing-range":
            params: list[object] = [normalized_start_date, normalized_end_date, signal_version]
            group_type_clause = ""
            if group_types:
                placeholders = ", ".join("?" for _ in group_types)
                group_type_clause = f" AND group_type IN ({placeholders})"
                params.extend(group_types)
            cursor.execute(
                f"""
                UPDATE dc_group_swing_signal_daily
                SET timing_state = NULL,
                    timing_reason = NULL
                WHERE signal_date >= ?
                  AND signal_date <= ?
                  AND signal_version = ?
                  {group_type_clause}
                """,
                params,
            )
            cleared_count = cursor.rowcount
            filtered_updates = list(updates)
        else:
            filtered_updates = [
                row
                for row in updates
                if row["existing_timing_state"] != row["timing_state"]
                or row["existing_timing_reason"] != row["timing_reason"]
            ]

        for row in filtered_updates:
            cursor.execute(
                """
                UPDATE dc_group_swing_signal_daily
                SET timing_state = ?,
                    timing_reason = ?,
                    run_id = ?,
                    created_at_utc = ?
                WHERE signal_date = ?
                  AND taxonomy_version = ?
                  AND group_type = ?
                  AND group_name = ?
                  AND signal_version = ?
                """,
                (
                    row["timing_state"],
                    row["timing_reason"],
                    row["run_id"],
                    row["created_at_utc"],
                    row["signal_date"],
                    row["taxonomy_version"],
                    row["group_type"],
                    row["group_name"],
                    row["signal_version"],
                ),
            )
            updated_count += cursor.rowcount
        conn.commit()
        return {
            "updated_count": updated_count,
            "cleared_count": cleared_count,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        db_manager.close()


def persist_datacenter_group_swing_signals(
    *,
    analysis_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    signal_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    write_mode: str = "upsert",
    min_eligible_count: int = DEFAULT_MIN_ELIGIBLE_COUNT,
    min_coverage_ratio: float = DEFAULT_MIN_COVERAGE_RATIO,
) -> dict[str, int | str]:
    normalized_signal_date = _parse_iso_date(signal_date, "signal_date")
    if write_mode not in {"insert-missing", "upsert", "replace-date"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    resolved_run_id = build_group_swing_run_id(
        as_of_date=normalized_signal_date,
        signal_version=signal_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    rows, prep_summary = build_group_swing_signal_rows(
        analysis_db_path=analysis_db_path,
        taxonomy_csv_path=taxonomy_csv_path,
        signal_date=normalized_signal_date,
        signal_version=signal_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        min_eligible_count=min_eligible_count,
        min_coverage_ratio=min_coverage_ratio,
    )
    write_summary = write_group_swing_signal_rows(
        analysis_db_path=analysis_db_path,
        rows=rows,
        signal_date=normalized_signal_date,
        signal_version=signal_version,
        write_mode=write_mode,
    )
    return {
        "signal_date": normalized_signal_date,
        "write_mode": write_mode,
        "signal_version": signal_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }


def persist_datacenter_group_timing_states(
    *,
    analysis_db_path: str | Path,
    start_date: str,
    end_date: str | None = None,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    write_mode: str = "update-existing",
    group_types: Sequence[str] | None = None,
) -> dict[str, int | str]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date or start_date, "end_date")
    if write_mode not in {"update-existing", "replace-timing-range"}:
        raise ValueError(f"Unsupported write_mode: {write_mode}")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    resolved_run_id = build_group_swing_run_id(
        as_of_date=normalized_end_date,
        signal_version=signal_version,
        run_id=run_id,
    )
    resolved_created_at_utc = resolve_created_at_utc(created_at_utc)
    updates, prep_summary = build_group_timing_updates(
        analysis_db_path=analysis_db_path,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at_utc,
        group_types=group_types,
    )
    write_summary = write_group_timing_updates(
        analysis_db_path=analysis_db_path,
        updates=updates,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        signal_version=signal_version,
        write_mode=write_mode,
        group_types=group_types,
    )
    return {
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "write_mode": write_mode,
        "signal_version": signal_version,
        "run_id": resolved_run_id,
        **prep_summary,
        **write_summary,
        "validation_status": "OK",
    }
