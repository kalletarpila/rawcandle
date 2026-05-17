from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Sequence

from .swing_daily_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    OVERHEAT_PRIORITY,
    TREND_PRIORITY,
    _check_required_tables,
    _float_value,
    _format_table,
    _normalize_path,
    _parse_iso_date,
    _row_to_dict,
    _utc_now_iso,
)


WEEKLY_REPORT_SUMMARY_ORDER = [
    "end_date",
    "signal_version",
    "ohlc_calc_version",
    "taxonomy_version",
    "taxonomy_version_inferred",
    "valid_signal_dates_count",
    "window_start_date",
    "window_end_date",
    "incomplete_window",
    "group_rows",
    "ticker_rows",
    "synthetic_ohlc_rows",
    "repeated_breakout_tickers",
    "repeated_pullback_tickers",
    "repeated_exit_risk_tickers",
    "output_markdown",
    "output_csv",
    "validation_status",
]

TIMING_STATE_ORDER = [
    "BUY_ZONE",
    "ADD_ON_PULLBACK",
    "TRIM_WATCH",
    "EXIT_ZONE",
    "NEUTRAL",
    None,
]

OVERHEAT_RANK = {
    None: 0,
    "LOW": 1,
    "ELEVATED": 2,
    "HIGH": 3,
    "EXTREME": 4,
}


def _count_by_date_and_field(
    rows: Sequence[dict[str, object]],
    *,
    date_field: str,
    value_field: str,
    group_type: str | None = None,
) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        if group_type is not None and row.get("group_type") != group_type:
            continue
        date_value = str(row.get(date_field) or "")
        field_value = "NULL" if row.get(value_field) is None else str(row.get(value_field))
        group_value = "" if group_type is None else group_type
        key = (date_value, group_value, field_value)
        counts[key] = counts.get(key, 0) + 1
    ordered_keys = sorted(counts)
    return [
        {
            "signal_date": date_value,
            "group_type": group_value,
            "status": field_value,
            "count": counts[(date_value, group_value, field_value)],
        }
        for date_value, group_value, field_value in ordered_keys
    ]


def _group_rows_by_key(
    rows: Sequence[dict[str, object]],
    *,
    key_fields: Sequence[str],
    date_field: str,
) -> dict[tuple[object, ...], list[dict[str, object]]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        grouped.setdefault(key, []).append(row)
    for group_rows in grouped.values():
        group_rows.sort(key=lambda row: str(row.get(date_field) or ""))
    return grouped


def _numeric_change(first_row: dict[str, object], last_row: dict[str, object], field_name: str) -> float | None:
    first_value = _float_value(first_row.get(field_name))
    last_value = _float_value(last_row.get(field_name))
    if first_value is None or last_value is None:
        return None
    return last_value - first_value


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    end_date: str,
    signal_version: str,
    taxonomy_version: str | None,
    limit: int = 5,
) -> list[str]:
    if taxonomy_version is None:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT signal_date
        FROM dc_group_swing_signal_daily
        WHERE signal_date <= ?
          AND signal_version = ?
          AND taxonomy_version = ?
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        (end_date, signal_version, taxonomy_version, limit),
    ).fetchall()
    return sorted(str(row["signal_date"]) for row in rows)


def _resolve_weekly_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    end_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> tuple[str | None, int]:
    if taxonomy_version is not None:
        return taxonomy_version, 0
    rows = conn.execute(
        """
        SELECT DISTINCT taxonomy_version
        FROM dc_group_swing_signal_daily
        WHERE signal_date <= ?
          AND signal_version = ?
        ORDER BY taxonomy_version ASC
        """,
        (end_date, signal_version),
    ).fetchall()
    versions = [str(row["taxonomy_version"]) for row in rows if row["taxonomy_version"] is not None]
    if len(versions) == 1:
        return versions[0], 1
    if len(versions) > 1:
        raise ValueError(
            "Multiple taxonomy_version values exist for the selected weekly window and signal_version; "
            "pass --taxonomy-version explicitly"
        )
    return None, 0


def _load_rows_for_dates(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_field: str,
    selected_dates: Sequence[str],
    version_field: str,
    version_value: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if not selected_dates or taxonomy_version is None:
        return []
    placeholders = ", ".join("?" for _ in selected_dates)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {table_name}
        WHERE {date_field} IN ({placeholders})
          AND {version_field} = ?
          AND taxonomy_version = ?
        ORDER BY {date_field} ASC
        """,
        tuple(selected_dates) + (version_value, taxonomy_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def load_weekly_swing_report_data(
    *,
    analysis_db_path: str | Path,
    end_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    taxonomy_version: str | None = None,
) -> dict[str, object]:
    normalized_end_date = _parse_iso_date(end_date)
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        _check_required_tables(
            conn,
            [
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            ],
        )
        resolved_taxonomy_version, taxonomy_version_inferred = _resolve_weekly_taxonomy_version(
            conn,
            end_date=normalized_end_date,
            signal_version=signal_version,
            taxonomy_version=taxonomy_version,
        )
        valid_signal_dates = _load_valid_signal_dates(
            conn,
            end_date=normalized_end_date,
            signal_version=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        group_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        ticker_rows = _load_rows_for_dates(
            conn,
            table_name="dc_ticker_swing_signal_daily",
            date_field="signal_date",
            selected_dates=valid_signal_dates,
            version_field="signal_version",
            version_value=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        synthetic_rows = _load_rows_for_dates(
            conn,
            table_name="dc_group_synthetic_ohlc_daily",
            date_field="ohlc_date",
            selected_dates=valid_signal_dates,
            version_field="calc_version",
            version_value=ohlc_calc_version,
            taxonomy_version=resolved_taxonomy_version,
        )
    return {
        "requested_end_date": normalized_end_date,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        "taxonomy_version": resolved_taxonomy_version,
        "taxonomy_version_inferred": taxonomy_version_inferred,
        "valid_signal_dates": valid_signal_dates,
        "group_rows": group_rows,
        "ticker_rows": ticker_rows,
        "synthetic_rows": synthetic_rows,
    }


def _build_repeated_ticker_rows(
    rows: Sequence[dict[str, object]],
    *,
    signal_field: str,
    extra_count_fields: Sequence[str] = (),
) -> list[dict[str, object]]:
    grouped = _group_rows_by_key(rows, key_fields=("taxonomy_version", "ticker"), date_field="signal_date")
    output_rows: list[dict[str, object]] = []
    for (_, ticker), ticker_rows in grouped.items():
        positive_rows = [row for row in ticker_rows if row.get(signal_field) == 1]
        if not positive_rows:
            continue
        last_row = ticker_rows[-1]
        row = {
            "ticker": ticker,
            f"{signal_field.removesuffix('_signal')}_days": len(positive_rows),
            "first_signal_date": str(positive_rows[0].get("signal_date") or ""),
            "last_signal_date": str(positive_rows[-1].get("signal_date") or ""),
            "last_primary_layer": last_row.get("primary_layer"),
            "last_primary_subindustry": last_row.get("primary_subindustry"),
            "last_close": last_row.get("close"),
            "last_return_5d": last_row.get("return_5d"),
            "last_return_10d": last_row.get("return_10d"),
            "last_return_20d": last_row.get("return_20d"),
            "last_return_60d": last_row.get("return_60d"),
            "last_volume_vs_avg20": last_row.get("volume_vs_avg20"),
            "last_latest_structure_label": last_row.get("latest_structure_label"),
            "last_exit_reason": last_row.get("exit_reason"),
            "last_bullish_candle_signal": last_row.get("bullish_candle_signal"),
            "last_bearish_candle_signal": last_row.get("bearish_candle_signal"),
            "last_bullish_divergence_signal": last_row.get("bullish_divergence_signal"),
            "last_bearish_divergence_signal": last_row.get("bearish_divergence_signal"),
            "last_hidden_bullish_divergence_signal": last_row.get("hidden_bullish_divergence_signal"),
            "last_hidden_bearish_divergence_signal": last_row.get("hidden_bearish_divergence_signal"),
            "last_price_data_status": last_row.get("price_data_status"),
            "last_distance_to_ema20_pct": last_row.get("distance_to_ema20_pct"),
        }
        for field_name in extra_count_fields:
            row[f"{field_name.removesuffix('_signal')}_days"] = sum(
                1 for current_row in ticker_rows if current_row.get(field_name) == 1
            )
        output_rows.append(row)
    return output_rows


def build_markdown_weekly_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    if top_n <= 0:
        raise ValueError(f"Invalid top_n: {top_n}")

    requested_end_date = str(report_data["requested_end_date"])
    signal_version = str(report_data["signal_version"])
    ohlc_calc_version = str(report_data["ohlc_calc_version"])
    taxonomy_version = "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"])
    valid_signal_dates = list(report_data["valid_signal_dates"])  # type: ignore[arg-type]
    group_rows = list(report_data["group_rows"])  # type: ignore[arg-type]
    ticker_rows = list(report_data["ticker_rows"])  # type: ignore[arg-type]
    synthetic_rows = list(report_data["synthetic_rows"])  # type: ignore[arg-type]
    generated = generated_at_utc or _utc_now_iso()
    window_start_date = valid_signal_dates[0] if valid_signal_dates else ""
    window_end_date = valid_signal_dates[-1] if valid_signal_dates else ""
    incomplete_window = "YES" if len(valid_signal_dates) < 5 else "NO"
    end_group_rows = [row for row in group_rows if row.get("signal_date") == window_end_date]

    ecosystem_rows = [
        row
        for row in group_rows
        if row.get("group_type") == "ecosystem" and row.get("group_name") == "DC_ECOSYSTEM_TOTAL"
    ]
    ecosystem_first = ecosystem_rows[0] if ecosystem_rows else None
    ecosystem_last = ecosystem_rows[-1] if ecosystem_rows else None

    lines = [
        "# Datacenter Weekly Swing Report",
        "",
        "## 1. Title and run metadata",
        f"end_date: {requested_end_date}",
        f"signal_version: {signal_version}",
        f"ohlc_calc_version: {ohlc_calc_version}",
        f"taxonomy_version: {taxonomy_version}",
        f"generated_at_utc: {generated}",
        "source_tables: dc_group_swing_signal_daily, dc_ticker_swing_signal_daily, dc_group_synthetic_ohlc_daily",
        "Window type: last 5 valid trading days, not calendar week",
        "",
        "## 2. Window summary",
    ]
    if len(valid_signal_dates) < 5:
        lines.append("INCOMPLETE WINDOW – FEWER THAN 5 VALID SIGNAL DATES")
    lines.append(
        _format_table(
            ["metric", "value"],
            [
                {"metric": "requested_end_date", "value": requested_end_date},
                {"metric": "window_start_date", "value": window_start_date},
                {"metric": "window_end_date", "value": window_end_date},
                {"metric": "valid_signal_dates_count", "value": len(valid_signal_dates)},
                {"metric": "valid_signal_dates_included", "value": ", ".join(valid_signal_dates)},
                {"metric": "incomplete_window", "value": incomplete_window},
            ],
        ).rstrip()
    )

    lines.extend(["", "## 3. Ecosystem 5-day change"])
    if ecosystem_first is None or ecosystem_last is None:
        lines.append("Ecosystem row missing.")
    else:
        ecosystem_change_rows = []
        for field_name in (
            "return_5d",
            "return_10d",
            "return_20d",
            "pct_above_ma10",
            "pct_above_ema20",
            "ema20_breadth_delta_5d",
            "trend_breadth",
            "weakness_breadth",
        ):
            ecosystem_change_rows.append(
                {
                    "metric": field_name,
                    "first_value": ecosystem_first.get(field_name),
                    "last_value": ecosystem_last.get(field_name),
                    "change": _numeric_change(ecosystem_first, ecosystem_last, field_name),
                }
            )
        for field_name in ("timing_state", "overheat_risk_level", "data_quality_status"):
            ecosystem_change_rows.append(
                {
                    "metric": field_name,
                    "first_value": ecosystem_first.get(field_name),
                    "last_value": ecosystem_last.get(field_name),
                    "change": f"{ecosystem_first.get(field_name) or ''} -> {ecosystem_last.get(field_name) or ''}",
                }
            )
        lines.append(
            _format_table(
                ["metric", "first_value", "last_value", "change"],
                ecosystem_change_rows,
            ).rstrip()
        )

    lines.extend(["", "## 4. Overheat / rotation risk progression"])
    if any(row.get("overheat_risk_level") == "EXTREME" for row in end_group_rows):
        lines.append("EXTREME RISK – TIGHTEN STOPS / NO NEW LONGS")
    overheat_count_rows = _count_by_date_and_field(
        group_rows,
        date_field="signal_date",
        value_field="overheat_risk_level",
    )
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], overheat_count_rows).rstrip())
    lines.extend(["", "Worsened groups"])
    worsened_rows: list[dict[str, object]] = []
    for (_, group_type, group_name), current_rows in _group_rows_by_key(
        group_rows,
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        first_rank = OVERHEAT_RANK.get(first_row.get("overheat_risk_level"), 0)
        last_rank = OVERHEAT_RANK.get(last_row.get("overheat_risk_level"), 0)
        if last_rank > first_rank:
            worsened_rows.append(
                {
                    "group_type": group_type,
                    "group_name": group_name,
                    "first_overheat_risk_level": first_row.get("overheat_risk_level"),
                    "last_overheat_risk_level": last_row.get("overheat_risk_level"),
                    "risk_rank_change": last_rank - first_rank,
                    "last_return_10d": last_row.get("return_10d"),
                    "last_return_20d": last_row.get("return_20d"),
                    "last_ema20_breadth_delta_5d": last_row.get("ema20_breadth_delta_5d"),
                    "last_weakness_breadth": last_row.get("weakness_breadth"),
                }
            )
    worsened_rows.sort(
        key=lambda row: (
            -(int(row["risk_rank_change"])),
            -OVERHEAT_RANK.get(row.get("last_overheat_risk_level"), 0),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "first_overheat_risk_level",
                "last_overheat_risk_level",
                "risk_rank_change",
                "last_return_10d",
                "last_return_20d",
                "last_ema20_breadth_delta_5d",
                "last_weakness_breadth",
            ],
            worsened_rows,
        ).rstrip()
    )

    lines.extend(["", "## 5. Subindustry timing persistence"])
    timing_rows: list[dict[str, object]] = []
    for (_, _, group_name), current_rows in _group_rows_by_key(
        [row for row in group_rows if row.get("group_type") == "subindustry"],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        last_row = current_rows[-1]
        row = {
            "subindustry": group_name,
            "last_timing_state": last_row.get("timing_state"),
            "last_return_5d": last_row.get("return_5d"),
            "last_return_10d": last_row.get("return_10d"),
            "last_pct_above_ema20": last_row.get("pct_above_ema20"),
            "last_ema20_breadth_delta_5d": last_row.get("ema20_breadth_delta_5d"),
            "last_data_quality_status": last_row.get("data_quality_status"),
        }
        for state in TIMING_STATE_ORDER:
            column_name = "null_days" if state is None else f"{str(state).lower()}_days"
            row[column_name] = sum(1 for current_row in current_rows if current_row.get("timing_state") == state)
        timing_rows.append(row)
    timing_rows.sort(
        key=lambda row: (
            -int(row["exit_zone_days"]),
            -int(row["trim_watch_days"]),
            -int(row["buy_zone_days"]),
            str(row["subindustry"]),
        )
    )
    lines.append(
        _format_table(
            [
                "subindustry",
                "last_timing_state",
                "buy_zone_days",
                "add_on_pullback_days",
                "trim_watch_days",
                "exit_zone_days",
                "neutral_days",
                "null_days",
                "last_return_5d",
                "last_return_10d",
                "last_pct_above_ema20",
                "last_ema20_breadth_delta_5d",
                "last_data_quality_status",
            ],
            timing_rows,
        ).rstrip()
    )

    lines.extend(["", "## 6. Subindustry improvement / deterioration", "", "### A. Most improved subindustries"])
    change_rows: list[dict[str, object]] = []
    for (_, _, group_name), current_rows in _group_rows_by_key(
        [row for row in group_rows if row.get("group_type") == "subindustry"],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="signal_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        change_rows.append(
            {
                "subindustry": group_name,
                "return_5d_change": _numeric_change(first_row, last_row, "return_5d"),
                "return_10d_change": _numeric_change(first_row, last_row, "return_10d"),
                "pct_above_ema20_change": _numeric_change(first_row, last_row, "pct_above_ema20"),
                "ema20_breadth_delta_5d_change": _numeric_change(first_row, last_row, "ema20_breadth_delta_5d"),
                "trend_breadth_change": _numeric_change(first_row, last_row, "trend_breadth"),
                "weakness_breadth_change": _numeric_change(first_row, last_row, "weakness_breadth"),
            }
        )
    improved_rows = sorted(
        change_rows,
        key=lambda row: (
            -(_float_value(row.get("pct_above_ema20_change")) or float("-inf")),
            -(_float_value(row.get("return_10d_change")) or float("-inf")),
            _float_value(row.get("weakness_breadth_change")) if row.get("weakness_breadth_change") is not None else float("inf"),
            str(row.get("subindustry") or ""),
        ),
    )[:top_n]
    deteriorated_rows = sorted(
        change_rows,
        key=lambda row: (
            _float_value(row.get("pct_above_ema20_change")) if row.get("pct_above_ema20_change") is not None else float("inf"),
            _float_value(row.get("return_10d_change")) if row.get("return_10d_change") is not None else float("inf"),
            -(_float_value(row.get("weakness_breadth_change")) or float("-inf")),
            str(row.get("subindustry") or ""),
        ),
    )[:top_n]
    change_headers = [
        "subindustry",
        "return_5d_change",
        "return_10d_change",
        "pct_above_ema20_change",
        "ema20_breadth_delta_5d_change",
        "trend_breadth_change",
        "weakness_breadth_change",
    ]
    lines.append(_format_table(change_headers, improved_rows).rstrip())
    lines.extend(["", "### B. Most deteriorated subindustries"])
    lines.append(_format_table(change_headers, deteriorated_rows).rstrip())

    lines.extend(["", "## 7. Repeated breakout tickers"])
    breakout_rows = _build_repeated_ticker_rows(ticker_rows, signal_field="breakout_signal")
    breakout_rows.sort(
        key=lambda row: (
            -int(row["breakout_days"]),
            -(_float_value(row.get("last_return_10d")) or float("-inf")),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "breakout_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_10d",
                "last_volume_vs_avg20",
                "last_latest_structure_label",
                "last_price_data_status",
            ],
            breakout_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 8. Repeated pullback tickers"])
    pullback_rows = _build_repeated_ticker_rows(
        ticker_rows,
        signal_field="pullback_signal",
        extra_count_fields=("fast_ema10_pullback_signal", "conservative_ema20_pullback_signal"),
    )
    pullback_rows.sort(
        key=lambda row: (
            -int(row["conservative_ema20_pullback_days"]),
            -int(row["fast_ema10_pullback_days"]),
            -int(row["pullback_days"]),
            -(_float_value(row.get("last_return_60d")) or float("-inf")),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "pullback_days",
                "fast_ema10_pullback_days",
                "conservative_ema20_pullback_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_20d",
                "last_return_60d",
                "last_latest_structure_label",
                "last_bullish_candle_signal",
                "last_bullish_divergence_signal",
                "last_hidden_bullish_divergence_signal",
                "last_price_data_status",
            ],
            pullback_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 9. Repeated exit-risk tickers"])
    exit_rows = _build_repeated_ticker_rows(ticker_rows, signal_field="exit_risk_signal")
    exit_rows.sort(
        key=lambda row: (
            -int(row["exit_risk_days"]),
            _float_value(row.get("last_return_10d")) if row.get("last_return_10d") is not None else float("inf"),
            _float_value(row.get("last_distance_to_ema20_pct")) if row.get("last_distance_to_ema20_pct") is not None else float("inf"),
            str(row.get("ticker") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "ticker",
                "exit_risk_days",
                "first_signal_date",
                "last_signal_date",
                "last_primary_layer",
                "last_primary_subindustry",
                "last_close",
                "last_return_5d",
                "last_return_10d",
                "last_return_20d",
                "last_distance_to_ema20_pct",
                "last_latest_structure_label",
                "last_exit_reason",
                "last_bearish_candle_signal",
                "last_bearish_divergence_signal",
                "last_hidden_bearish_divergence_signal",
                "last_price_data_status",
            ],
            exit_rows[:top_n],
        ).rstrip()
    )

    lines.extend(["", "## 10. Synthetic OHLC structure changes"])
    synthetic_change_rows: list[dict[str, object]] = []
    for (_, group_type, group_name), current_rows in _group_rows_by_key(
        [row for row in synthetic_rows if row.get("group_type") in {"subindustry", "layer"}],
        key_fields=("taxonomy_version", "group_type", "group_name"),
        date_field="ohlc_date",
    ).items():
        first_row = current_rows[0]
        last_row = current_rows[-1]
        synthetic_change_rows.append(
            {
                "group_type": group_type,
                "group_name": group_name,
                "first_trend_classification": first_row.get("trend_classification"),
                "last_trend_classification": last_row.get("trend_classification"),
                "first_latest_structure_label": first_row.get("latest_structure_label"),
                "last_latest_structure_label": last_row.get("latest_structure_label"),
                "synthetic_close_change": _numeric_change(first_row, last_row, "synthetic_close"),
                "distance_to_ema20_pct_change": _numeric_change(first_row, last_row, "distance_to_ema20_pct"),
                "relative_close_extension_20_change": _numeric_change(first_row, last_row, "relative_close_extension_20"),
                "volatility_20d_change": _numeric_change(first_row, last_row, "volatility_20d"),
                "last_data_quality_status": last_row.get("data_quality_status"),
            }
        )
    synthetic_change_rows.sort(
        key=lambda row: (
            str(row.get("group_type") or ""),
            TREND_PRIORITY.get(row.get("last_trend_classification"), 3),
            -(_float_value(row.get("relative_close_extension_20_change")) or float("-inf")),
            str(row.get("group_name") or ""),
        )
    )
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "first_trend_classification",
                "last_trend_classification",
                "first_latest_structure_label",
                "last_latest_structure_label",
                "synthetic_close_change",
                "distance_to_ema20_pct_change",
                "relative_close_extension_20_change",
                "volatility_20d_change",
                "last_data_quality_status",
            ],
            synthetic_change_rows,
        ).rstrip()
    )

    lines.extend(["", "## 11. Data quality over the window"])
    group_quality_rows = _count_by_date_and_field(
        group_rows,
        date_field="signal_date",
        value_field="data_quality_status",
    )
    ticker_quality_rows = _count_by_date_and_field(
        ticker_rows,
        date_field="signal_date",
        value_field="price_data_status",
    )
    lines.append("Group data quality counts")
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], group_quality_rows).rstrip())
    lines.extend(["", "Ticker price data quality counts"])
    lines.append(_format_table(["signal_date", "group_type", "status", "count"], ticker_quality_rows).rstrip())
    lines.extend(["", "End-date data quality details"])
    non_ok_end_groups = [
        {
            "group_type": row.get("group_type"),
            "group_name": row.get("group_name"),
            "data_quality_status": row.get("data_quality_status"),
        }
        for row in end_group_rows
        if row.get("data_quality_status") != "OK"
    ]
    lines.append(_format_table(["group_type", "group_name", "data_quality_status"], non_ok_end_groups).rstrip())
    end_ticker_rows = [row for row in ticker_rows if row.get("signal_date") == window_end_date]
    lines.extend(
        [
            "",
            _format_table(
                ["metric", "count"],
                [
                    {
                        "metric": "ticker_count_missing_as_of_date_end_date",
                        "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE"),
                    },
                    {
                        "metric": "ticker_count_missing_close_as_of_date_end_date",
                        "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE"),
                    },
                ],
            ).rstrip(),
        ]
    )

    lines.extend(["", "## 12. Missing / incomplete inputs summary"])
    end_synthetic_rows = [row for row in synthetic_rows if row.get("ohlc_date") == window_end_date]
    lines.append("Window-total counts")
    lines.append(
        _format_table(
            ["metric", "count"],
            [
                {"metric": "group_rows_missing_timing_state", "count": sum(1 for row in group_rows if row.get("timing_state") is None)},
                {"metric": "group_rows_missing_overheat_risk_level", "count": sum(1 for row in group_rows if row.get("overheat_risk_level") is None)},
                {
                    "metric": "ticker_rows_with_scanner_fields_null",
                    "count": sum(
                        1
                        for row in ticker_rows
                        if any(
                            row.get(field_name) is None
                            for field_name in (
                                "breakout_signal",
                                "fast_ema10_pullback_signal",
                                "conservative_ema20_pullback_signal",
                                "pullback_signal",
                                "exit_risk_signal",
                            )
                        )
                    ),
                },
                {"metric": "synthetic_ohlc_rows_missing_latest_structure_label", "count": sum(1 for row in synthetic_rows if row.get("latest_structure_label") is None)},
                {"metric": "synthetic_ohlc_rows_missing_relative_close_20", "count": sum(1 for row in synthetic_rows if row.get("relative_close_20") is None)},
                {"metric": "ticker_rows_with_missing_as_of_date", "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE")},
                {"metric": "ticker_rows_with_missing_close_as_of_date", "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE")},
            ],
        ).rstrip()
    )
    lines.extend(["", "End-date-only counts"])
    lines.append(
        _format_table(
            ["metric", "count"],
            [
                {"metric": "group_rows_missing_timing_state_end_date", "count": sum(1 for row in end_group_rows if row.get("timing_state") is None)},
                {"metric": "group_rows_missing_overheat_risk_level_end_date", "count": sum(1 for row in end_group_rows if row.get("overheat_risk_level") is None)},
                {
                    "metric": "ticker_rows_with_scanner_fields_null_end_date",
                    "count": sum(
                        1
                        for row in end_ticker_rows
                        if any(
                            row.get(field_name) is None
                            for field_name in (
                                "breakout_signal",
                                "fast_ema10_pullback_signal",
                                "conservative_ema20_pullback_signal",
                                "pullback_signal",
                                "exit_risk_signal",
                            )
                        )
                    ),
                },
                {"metric": "synthetic_ohlc_rows_missing_latest_structure_label_end_date", "count": sum(1 for row in end_synthetic_rows if row.get("latest_structure_label") is None)},
                {"metric": "synthetic_ohlc_rows_missing_relative_close_20_end_date", "count": sum(1 for row in end_synthetic_rows if row.get("relative_close_20") is None)},
                {"metric": "ticker_rows_with_missing_as_of_date_end_date", "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE")},
                {"metric": "ticker_rows_with_missing_close_as_of_date_end_date", "count": sum(1 for row in end_ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE")},
            ],
        ).rstrip()
    )
    return "\n".join(lines).strip() + "\n"


def build_csv_weekly_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(["section", "line"])
    current_section = "report"
    for line in markdown.splitlines():
        if line.startswith("## "):
            current_section = line[3:]
            writer.writerow([current_section, ""])
            continue
        if line.startswith("# "):
            current_section = line[2:]
            writer.writerow([current_section, ""])
            continue
        writer.writerow([current_section, line])
    return output.getvalue()


def format_weekly_swing_report_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in WEEKLY_REPORT_SUMMARY_ORDER if key in summary]


def write_weekly_swing_report(
    *,
    analysis_db_path: str | Path,
    end_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    taxonomy_version: str | None = None,
    output_md: str | Path | None = None,
    output_csv: str | Path | None = None,
    top_n: int = 20,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db_path,
        end_date=end_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        taxonomy_version=taxonomy_version,
    )
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    csv_text = build_csv_weekly_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    output_md_value = ""
    output_csv_value = ""
    if output_md is not None:
        output_md_path = _normalize_path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(markdown, encoding="utf-8")
        output_md_value = str(output_md_path)
    if output_csv is not None:
        output_csv_path = _normalize_path(output_csv)
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        output_csv_path.write_text(csv_text, encoding="utf-8")
        output_csv_value = str(output_csv_path)

    breakout_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="breakout_signal"))  # type: ignore[arg-type]
    pullback_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="pullback_signal"))  # type: ignore[arg-type]
    exit_count = len(_build_repeated_ticker_rows(list(report_data["ticker_rows"]), signal_field="exit_risk_signal"))  # type: ignore[arg-type]
    valid_signal_dates = list(report_data["valid_signal_dates"])  # type: ignore[arg-type]
    summary = {
        "end_date": str(report_data["requested_end_date"]),
        "signal_version": str(report_data["signal_version"]),
        "ohlc_calc_version": str(report_data["ohlc_calc_version"]),
        "taxonomy_version": "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"]),
        "taxonomy_version_inferred": int(report_data.get("taxonomy_version_inferred") or 0),
        "valid_signal_dates_count": len(valid_signal_dates),
        "window_start_date": valid_signal_dates[0] if valid_signal_dates else "",
        "window_end_date": valid_signal_dates[-1] if valid_signal_dates else "",
        "incomplete_window": "YES" if len(valid_signal_dates) < 5 else "NO",
        "group_rows": len(report_data["group_rows"]),  # type: ignore[arg-type]
        "ticker_rows": len(report_data["ticker_rows"]),  # type: ignore[arg-type]
        "synthetic_ohlc_rows": len(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        "repeated_breakout_tickers": breakout_count,
        "repeated_pullback_tickers": pullback_count,
        "repeated_exit_risk_tickers": exit_count,
        "output_markdown": output_md_value,
        "output_csv": output_csv_value,
        "validation_status": "OK",
    }
    return {
        "markdown": markdown,
        "csv": csv_text,
        "summary": summary,
    }
