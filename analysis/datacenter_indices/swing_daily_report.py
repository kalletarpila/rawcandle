from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"

DAILY_REPORT_SUMMARY_ORDER = [
    "signal_date",
    "signal_version",
    "ohlc_calc_version",
    "group_rows",
    "ticker_rows",
    "synthetic_ohlc_rows",
    "breakout_count",
    "pullback_count",
    "exit_risk_count",
    "output_markdown",
    "output_csv",
    "validation_status",
]

TIMING_PRIORITY = {
    "EXIT_ZONE": 0,
    "TRIM_WATCH": 1,
    "ADD_ON_PULLBACK": 2,
    "BUY_ZONE": 3,
    "NEUTRAL": 4,
    None: 5,
}

OVERHEAT_PRIORITY = {
    "EXTREME": 0,
    "HIGH": 1,
    "ELEVATED": 2,
    "LOW": 3,
    None: 4,
}

TREND_PRIORITY = {
    "UP": 0,
    "NEUTRAL": 1,
    "DOWN": 2,
    None: 3,
}


def _parse_iso_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid signal_date: {value}") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_path(value: str | Path) -> Path:
    return Path(value)


def _check_required_tables(conn: sqlite3.Connection, required_tables: Sequence[str]) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }
    missing = [table for table in required_tables if table not in existing]
    if missing:
        raise ValueError(f"Missing required tables: {', '.join(missing)}")


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _float_value(value: object | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_value(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _format_table(headers: Sequence[str], rows: Sequence[dict[str, object]]) -> str:
    if not rows:
        return "No rows.\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(_format_value(row.get(header)) for header in headers) + " |"
        )
    return "\n".join(lines) + "\n"


def _count_by_field(rows: Sequence[dict[str, object]], field_name: str) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = "NULL" if row.get(field_name) is None else str(row.get(field_name))
        counts[key] = counts.get(key, 0) + 1
    return [{"value": key, "count": counts[key]} for key in sorted(counts)]


def _load_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
        ORDER BY taxonomy_version ASC, group_type ASC, group_name ASC
        """,
        (signal_date, signal_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
        ORDER BY taxonomy_version ASC, ticker ASC
        """,
        (signal_date, signal_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _load_synthetic_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    calc_version: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
          AND calc_version = ?
        ORDER BY taxonomy_version ASC, group_type ASC, group_name ASC
        """,
        (signal_date, calc_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def load_daily_swing_report_data(
    *,
    analysis_db_path: str | Path,
    signal_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
) -> dict[str, object]:
    normalized_signal_date = _parse_iso_date(signal_date)
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
        group_rows = _load_group_rows(
            conn,
            signal_date=normalized_signal_date,
            signal_version=signal_version,
        )
        ticker_rows = _load_ticker_rows(
            conn,
            signal_date=normalized_signal_date,
            signal_version=signal_version,
        )
        synthetic_rows = _load_synthetic_rows(
            conn,
            signal_date=normalized_signal_date,
            calc_version=ohlc_calc_version,
        )
    return {
        "signal_date": normalized_signal_date,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        "group_rows": group_rows,
        "ticker_rows": ticker_rows,
        "synthetic_rows": synthetic_rows,
    }


def _sort_subindustry_timing(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            TIMING_PRIORITY.get(row.get("timing_state"), 5),
            str(row.get("group_name") or ""),
        ),
    )


def _sort_overheat_rows(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            OVERHEAT_PRIORITY.get(row.get("overheat_risk_level"), 4),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        ),
    )


def _section_rows(
    rows: Sequence[dict[str, object]],
    *,
    predicate,
    sort_key,
    top_n: int | None = None,
) -> list[dict[str, object]]:
    filtered = [row for row in rows if predicate(row)]
    ordered = sorted(filtered, key=sort_key)
    return ordered if top_n is None else ordered[:top_n]


def build_markdown_daily_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    if top_n <= 0:
        raise ValueError(f"Invalid top_n: {top_n}")

    signal_date = str(report_data["signal_date"])
    signal_version = str(report_data["signal_version"])
    ohlc_calc_version = str(report_data["ohlc_calc_version"])
    group_rows = list(report_data["group_rows"])  # type: ignore[arg-type]
    ticker_rows = list(report_data["ticker_rows"])  # type: ignore[arg-type]
    synthetic_rows = list(report_data["synthetic_rows"])  # type: ignore[arg-type]
    generated = generated_at_utc or _utc_now_iso()

    ecosystem_row = next(
        (
            row
            for row in group_rows
            if row.get("group_type") == "ecosystem"
            and row.get("group_name") == "DC_ECOSYSTEM_TOTAL"
        ),
        None,
    )
    non_ok_group_count = sum(1 for row in group_rows if row.get("data_quality_status") != "OK")
    overheat_rows = _sort_overheat_rows(
        [row for row in group_rows if row.get("overheat_risk_level") is not None]
    )
    subindustry_rows = _sort_subindustry_timing(
        [row for row in group_rows if row.get("group_type") == "subindustry"]
    )
    buy_zone_rows = _section_rows(
        subindustry_rows,
        predicate=lambda row: row.get("timing_state") == "BUY_ZONE",
        sort_key=lambda row: (
            -(_float_value(row.get("return_10d")) or float("-inf")),
            -(_float_value(row.get("pct_above_ema20")) or float("-inf")),
            str(row.get("group_name") or ""),
        ),
        top_n=top_n,
    )
    add_on_rows = _section_rows(
        subindustry_rows,
        predicate=lambda row: row.get("timing_state") == "ADD_ON_PULLBACK",
        sort_key=lambda row: (
            -(_float_value(row.get("pct_above_ema20")) or float("-inf")),
            -(_float_value(row.get("return_5d")) or float("-inf")),
            str(row.get("group_name") or ""),
        ),
        top_n=top_n,
    )
    trim_rows = _section_rows(
        subindustry_rows,
        predicate=lambda row: row.get("timing_state") == "TRIM_WATCH",
        sort_key=lambda row: (
            _float_value(row.get("ema20_breadth_delta_5d")) if row.get("ema20_breadth_delta_5d") is not None else float("inf"),
            _float_value(row.get("return_10d")) if row.get("return_10d") is not None else float("inf"),
            str(row.get("group_name") or ""),
        ),
        top_n=top_n,
    )
    exit_rows = _section_rows(
        subindustry_rows,
        predicate=lambda row: row.get("timing_state") == "EXIT_ZONE",
        sort_key=lambda row: (
            -(_float_value(row.get("weakness_breadth")) or float("-inf")),
            _float_value(row.get("return_20d")) if row.get("return_20d") is not None else float("inf"),
            str(row.get("group_name") or ""),
        ),
        top_n=top_n,
    )
    synthetic_summary_rows = sorted(
        [
            row
            for row in synthetic_rows
            if row.get("group_type") in {"subindustry", "layer"}
        ],
        key=lambda row: (
            str(row.get("group_type") or ""),
            TREND_PRIORITY.get(row.get("trend_classification"), 3),
            -(_float_value(row.get("relative_close_extension_20")) or float("-inf")),
            str(row.get("group_name") or ""),
        ),
    )
    breakout_rows = _section_rows(
        ticker_rows,
        predicate=lambda row: row.get("breakout_signal") == 1,
        sort_key=lambda row: (
            -(_float_value(row.get("return_10d")) or float("-inf")),
            -(_float_value(row.get("volume_vs_avg20")) or float("-inf")),
            str(row.get("ticker") or ""),
        ),
        top_n=top_n,
    )
    pullback_rows = _section_rows(
        ticker_rows,
        predicate=lambda row: row.get("pullback_signal") == 1,
        sort_key=lambda row: (
            -(int(row.get("conservative_ema20_pullback_signal") or 0)),
            -(int(row.get("fast_ema10_pullback_signal") or 0)),
            -(_float_value(row.get("return_60d")) or float("-inf")),
            str(row.get("ticker") or ""),
        ),
        top_n=top_n,
    )
    exit_risk_rows = _section_rows(
        ticker_rows,
        predicate=lambda row: row.get("exit_risk_signal") == 1,
        sort_key=lambda row: (
            _float_value(row.get("return_10d")) if row.get("return_10d") is not None else float("inf"),
            _float_value(row.get("distance_to_ema20_pct")) if row.get("distance_to_ema20_pct") is not None else float("inf"),
            str(row.get("ticker") or ""),
        ),
        top_n=top_n,
    )

    lines: list[str] = [
        "# Datacenter Daily Swing Signal Report",
        "",
        "## 1. Title and run metadata",
        f"signal_date: {signal_date}",
        f"signal_version: {signal_version}",
        f"ohlc_calc_version: {ohlc_calc_version}",
        f"generated_at_utc: {generated}",
        "source_tables: dc_group_swing_signal_daily, dc_ticker_swing_signal_daily, dc_group_synthetic_ohlc_daily",
        "",
        "## 2. Dashboard",
    ]
    if ecosystem_row is None:
        lines.append("Ecosystem row missing.")
    else:
        dashboard_rows = [
            {"metric": "signal_date", "value": signal_date},
            {"metric": "ecosystem_return_5d", "value": ecosystem_row.get("return_5d")},
            {"metric": "ecosystem_return_10d", "value": ecosystem_row.get("return_10d")},
            {"metric": "ecosystem_return_20d", "value": ecosystem_row.get("return_20d")},
            {"metric": "ecosystem_return_60d", "value": ecosystem_row.get("return_60d")},
            {"metric": "ecosystem_pct_above_ema20", "value": ecosystem_row.get("pct_above_ema20")},
            {"metric": "ecosystem_pct_above_ma10", "value": ecosystem_row.get("pct_above_ma10")},
            {"metric": "ecosystem_ema20_breadth_delta_5d", "value": ecosystem_row.get("ema20_breadth_delta_5d")},
            {"metric": "ecosystem_overheat_risk_level", "value": ecosystem_row.get("overheat_risk_level")},
            {"metric": "non_ok_group_count", "value": non_ok_group_count},
        ]
        lines.append(_format_table(["metric", "value"], dashboard_rows).rstrip())

    lines.extend(["", "## 3. Rotation Risk / Overheat Index"])
    if any(row.get("overheat_risk_level") == "EXTREME" for row in overheat_rows):
        lines.append("EXTREME RISK – TIGHTEN STOPS / NO NEW LONGS")
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "overheat_risk_level",
                "return_10d",
                "return_20d",
                "pct_above_ema20",
                "ema20_breadth_delta_5d",
                "ma10_breadth_delta_5d",
                "weakness_breadth",
                "data_quality_status",
            ],
            overheat_rows,
        ).rstrip()
    )

    lines.extend(["", "## 4. Subindustry Timing States"])
    lines.append(
        _format_table(
            [
                "group_name",
                "timing_state",
                "timing_reason",
                "return_5d",
                "return_10d",
                "return_20d",
                "return_60d",
                "pct_above_ema20",
                "ema20_breadth_delta_5d",
                "trend_breadth",
                "weakness_breadth",
                "data_quality_status",
            ],
            subindustry_rows,
        ).rstrip()
    )

    section_specs = [
        ("## 5. Buy-Zone Subindustries", buy_zone_rows),
        ("## 6. Add-On Pullback Subindustries", add_on_rows),
        ("## 7. Trim/Watch Subindustries", trim_rows),
        ("## 8. Exit-Zone Subindustries", exit_rows),
    ]
    for heading, section_rows in section_specs:
        lines.extend(["", heading])
        lines.append(
            _format_table(
                [
                    "group_name",
                    "timing_state",
                    "return_5d",
                    "return_10d",
                    "return_20d",
                    "return_60d",
                    "pct_above_ema20",
                    "ema20_breadth_delta_5d",
                    "trend_breadth",
                    "weakness_breadth",
                    "data_quality_status",
                ],
                section_rows,
            ).rstrip()
        )

    lines.extend(["", "## 9. Synthetic OHLC Structure Summary"])
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "synthetic_close",
                "ema20",
                "distance_to_ema20_pct",
                "volatility_20d",
                "latest_structure_label",
                "trend_classification",
                "relative_close_extension_20",
                "relative_upper_wick_20",
                "relative_lower_wick_20",
                "data_quality_status",
            ],
            synthetic_summary_rows,
        ).rstrip()
    )

    ticker_section_specs = [
        (
            "## 10. Breakout Ticker Scanner",
            breakout_rows,
            [
                "ticker",
                "primary_layer",
                "primary_subindustry",
                "close",
                "return_5d",
                "return_10d",
                "return_20d",
                "distance_to_ema20_pct",
                "volume_vs_avg20",
                "latest_structure_label",
                "bullish_candle_signal",
                "bearish_candle_signal",
                "bullish_divergence_signal",
                "bearish_divergence_signal",
                "price_data_status",
            ],
        ),
        (
            "## 11. Pullback Ticker Scanner",
            pullback_rows,
            [
                "ticker",
                "primary_layer",
                "primary_subindustry",
                "close",
                "ema10",
                "ema20",
                "distance_to_ema10_pct",
                "distance_to_ema20_pct",
                "fast_ema10_pullback_signal",
                "conservative_ema20_pullback_signal",
                "return_5d",
                "return_20d",
                "return_60d",
                "latest_structure_label",
                "bullish_candle_signal",
                "bullish_divergence_signal",
                "hidden_bullish_divergence_signal",
                "price_data_status",
            ],
        ),
        (
            "## 12. Exit-Risk Ticker Scanner",
            exit_risk_rows,
            [
                "ticker",
                "primary_layer",
                "primary_subindustry",
                "close",
                "return_5d",
                "return_10d",
                "return_20d",
                "distance_to_ema20_pct",
                "latest_structure_label",
                "exit_reason",
                "bearish_candle_signal",
                "bearish_divergence_signal",
                "hidden_bearish_divergence_signal",
                "price_data_status",
            ],
        ),
    ]
    for heading, section_rows, headers in ticker_section_specs:
        lines.extend(["", heading])
        lines.append(_format_table(headers, section_rows).rstrip())

    lines.extend(["", "## 13. Data Quality"])
    group_quality_rows: list[dict[str, object]] = []
    for group_type in sorted({str(row.get("group_type") or "") for row in group_rows}):
        subset = [row for row in group_rows if row.get("group_type") == group_type]
        for item in _count_by_field(subset, "data_quality_status"):
            group_quality_rows.append(
                {
                    "scope": "group",
                    "group_type": group_type,
                    "status": item["value"],
                    "count": item["count"],
                }
            )
    ticker_quality_rows = [
        {
            "scope": "ticker",
            "group_type": "",
            "status": item["value"],
            "count": item["count"],
        }
        for item in _count_by_field(ticker_rows, "price_data_status")
    ]
    lines.append(
        _format_table(
            ["scope", "group_type", "status", "count"],
            group_quality_rows + ticker_quality_rows,
        ).rstrip()
    )

    lines.extend(["", "## 14. Missing / Incomplete Inputs Summary"])
    missing_rows = [
        {
            "metric": "group_rows_missing_timing_state",
            "count": sum(1 for row in group_rows if row.get("timing_state") is None),
        },
        {
            "metric": "group_rows_missing_overheat_risk_level",
            "count": sum(1 for row in group_rows if row.get("overheat_risk_level") is None),
        },
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
        {
            "metric": "synthetic_ohlc_rows_missing_latest_structure_label",
            "count": sum(1 for row in synthetic_rows if row.get("latest_structure_label") is None),
        },
        {
            "metric": "synthetic_ohlc_rows_missing_relative_close_20",
            "count": sum(1 for row in synthetic_rows if row.get("relative_close_20") is None),
        },
        {
            "metric": "ticker_rows_with_missing_as_of_date",
            "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_AS_OF_DATE"),
        },
        {
            "metric": "ticker_rows_with_missing_close_as_of_date",
            "count": sum(1 for row in ticker_rows if row.get("price_data_status") == "MISSING_CLOSE_AS_OF_DATE"),
        },
    ]
    lines.append(_format_table(["metric", "count"], missing_rows).rstrip())

    return "\n".join(lines).strip() + "\n"


def build_csv_daily_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
) -> str:
    markdown = build_markdown_daily_swing_report(
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


def format_daily_swing_report_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [
        f"SUMMARY {key}={summary[key]}"
        for key in DAILY_REPORT_SUMMARY_ORDER
        if key in summary
    ]


def write_daily_swing_signal_report(
    *,
    analysis_db_path: str | Path,
    signal_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    output_md: str | Path | None = None,
    output_csv: str | Path | None = None,
    top_n: int = 20,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db_path,
        signal_date=signal_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
    )
    csv_text = build_csv_daily_swing_report(
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
    summary = {
        "signal_date": str(report_data["signal_date"]),
        "signal_version": str(report_data["signal_version"]),
        "ohlc_calc_version": str(report_data["ohlc_calc_version"]),
        "group_rows": len(report_data["group_rows"]),  # type: ignore[arg-type]
        "ticker_rows": len(report_data["ticker_rows"]),  # type: ignore[arg-type]
        "synthetic_ohlc_rows": len(report_data["synthetic_rows"]),  # type: ignore[arg-type]
        "breakout_count": sum(1 for row in report_data["ticker_rows"] if row.get("breakout_signal") == 1),  # type: ignore[index]
        "pullback_count": sum(1 for row in report_data["ticker_rows"] if row.get("pullback_signal") == 1),  # type: ignore[index]
        "exit_risk_count": sum(1 for row in report_data["ticker_rows"] if row.get("exit_risk_signal") == 1),  # type: ignore[index]
        "output_markdown": output_md_value,
        "output_csv": output_csv_value,
        "validation_status": "OK",
    }
    return {
        "markdown": markdown,
        "csv": csv_text,
        "summary": summary,
    }
