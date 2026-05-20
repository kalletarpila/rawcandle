from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"
DEFAULT_WATCHLIST_FILE = "/home/kalle/projects/rawcandle/swing_reports/datacenter_watchlist.txt"

DAILY_REPORT_SUMMARY_ORDER = [
    "signal_date",
    "signal_version",
    "ohlc_calc_version",
    "taxonomy_version",
    "taxonomy_version_inferred",
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

EXIT_RISK_SEVERITY_PRIORITY = {
    "HIGH": 0,
    "MEDIUM": 1,
    "LOW": 2,
    None: 3,
}

FRESHNESS_PRIORITY = {
    "FRESH": 0,
    "AGING": 1,
    "STALE": 2,
    None: 3,
}

GROUP_RESET_PRIORITY = {
    "DOUBLE_BOS_DOWN": 0,
    "DOUBLE_BOS_UP": 1,
    None: 2,
}

GROUP_BOS_PRIORITY = {
    "BOS_DOWN": 0,
    "BOS_UP": 1,
    None: 2,
}

WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}


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


def _localize_csv_text(value: str) -> str:
    return re.sub(r"(?<=\d)\.(?=\d)", ",", value)


def _parse_markdown_table_cells(line: str) -> list[str] | None:
    if not line.startswith("|"):
        return None
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_table_separator(cells: Sequence[str]) -> bool:
    if not cells:
        return False
    return all(cell != "" and set(cell) <= {"-", ":"} for cell in cells)


def _build_csv_rows_from_markdown(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    current_section = "report"
    for line in markdown.splitlines():
        if line.startswith("## "):
            current_section = line[3:]
            rows.append([current_section])
            continue
        if line.startswith("# "):
            current_section = line[2:]
            rows.append([current_section])
            continue
        table_cells = _parse_markdown_table_cells(line)
        if table_cells is not None:
            if _is_markdown_table_separator(table_cells):
                continue
            rows.append([current_section, *(_localize_csv_text(cell) for cell in table_cells)])
            continue
        if line == "":
            rows.append([current_section])
            continue
        rows.append([current_section, _localize_csv_text(line)])
    return rows


def _count_by_field(rows: Sequence[dict[str, object]], field_name: str) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = "NULL" if row.get(field_name) is None else str(row.get(field_name))
        counts[key] = counts.get(key, 0) + 1
    return [{"value": key, "count": counts[key]} for key in sorted(counts)]


def _load_watchlist_tickers(path: str | Path | None) -> list[str]:
    if path is None:
        return []
    tickers: list[str] = []
    seen: set[str] = set()
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        ticker = value.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def _resolve_watchlist_context(watchlist_file: str | Path | None) -> dict[str, object]:
    selected_path = Path(DEFAULT_WATCHLIST_FILE) if watchlist_file is None else Path(watchlist_file)
    if not selected_path.exists():
        return {
            "watchlist_tickers": [],
            "watchlist_file_path": str(selected_path),
            "watchlist_file_missing": True,
        }
    return {
        "watchlist_tickers": _load_watchlist_tickers(selected_path),
        "watchlist_file_path": str(selected_path),
        "watchlist_file_missing": False,
    }


def _is_group_risk_state(
    *,
    subindustry_timing_state: object | None,
    subindustry_overheat_risk_level: object | None,
    layer_timing_state: object | None,
    layer_overheat_risk_level: object | None,
) -> bool:
    return (
        subindustry_timing_state in {"EXIT_ZONE", "TRIM_WATCH"}
        or layer_timing_state in {"EXIT_ZONE", "TRIM_WATCH"}
        or subindustry_overheat_risk_level in {"HIGH", "EXTREME"}
        or layer_overheat_risk_level in {"HIGH", "EXTREME"}
    )


def _has_subindustry_context_risk(
    *,
    subindustry_timing_state: object | None,
    subindustry_overheat_risk_level: object | None,
) -> bool:
    return (
        subindustry_timing_state in {"EXIT_ZONE", "TRIM_WATCH"}
        or subindustry_overheat_risk_level in {"HIGH", "EXTREME"}
    )


def _has_layer_context_risk(
    *,
    layer_timing_state: object | None,
    layer_overheat_risk_level: object | None,
) -> bool:
    return (
        layer_timing_state in {"EXIT_ZONE", "TRIM_WATCH"}
        or layer_overheat_risk_level in {"HIGH", "EXTREME"}
    )


def _daily_context_risk_value(*, in_datacenter_ecosystem: object | None, has_risk: bool) -> str:
    if in_datacenter_ecosystem == "NO":
        return ""
    return "YES" if has_risk else "NO"


def _classify_daily_watchlist_status(row: dict[str, object]) -> str:
    if row.get("in_datacenter_ecosystem") == "NO":
        return "NOT_PART_OF_DATACENTER_ECOSYSTEM"
    if row.get("price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES:
        return "MISSING_PRICE"
    if row.get("exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if row.get("breakout_signal") == 1:
        return "BREAKOUT_CANDIDATE"
    if row.get("pullback_signal") == 1:
        return "PULLBACK_CANDIDATE"
    if _is_group_risk_state(
        subindustry_timing_state=row.get("subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("subindustry_overheat_risk_level"),
        layer_timing_state=row.get("layer_timing_state"),
        layer_overheat_risk_level=row.get("layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _build_group_synthetic_context_by_key(
    synthetic_rows: Sequence[dict[str, object]],
    *,
    include_date: bool,
) -> dict[tuple[object, ...], dict[str, object]]:
    if include_date:
        return {
            (row.get("ohlc_date"), row.get("group_type"), row.get("group_name")): row
            for row in synthetic_rows
        }
    return {
        (row.get("group_type"), row.get("group_name")): row
        for row in synthetic_rows
    }


def _build_daily_report_ticker_row(
    *,
    ticker_row: dict[str, object],
    group_context_by_key: dict[tuple[object, ...], dict[str, object]],
    synthetic_context_by_key: dict[tuple[object, ...], dict[str, object]],
) -> dict[str, object]:
    subindustry_context = group_context_by_key.get(
        ("subindustry", ticker_row.get("primary_subindustry")),
        {},
    )
    layer_context = group_context_by_key.get(
        ("layer", ticker_row.get("primary_layer")),
        {},
    )
    subindustry_structure_context = synthetic_context_by_key.get(
        ("subindustry", ticker_row.get("primary_subindustry")),
        {},
    )
    layer_structure_context = synthetic_context_by_key.get(
        ("layer", ticker_row.get("primary_layer")),
        {},
    )
    output_row = {
        "ticker": ticker_row.get("ticker"),
        "in_datacenter_ecosystem": "YES",
        "subindustry_trend_classification": subindustry_structure_context.get("trend_classification"),
        "subindustry_latest_structure_label": subindustry_structure_context.get("latest_structure_label"),
        "layer_trend_classification": layer_structure_context.get("trend_classification"),
        "layer_latest_structure_label": layer_structure_context.get("latest_structure_label"),
        "primary_layer": ticker_row.get("primary_layer"),
        "primary_subindustry": ticker_row.get("primary_subindustry"),
        "close": ticker_row.get("close"),
        "return_5d": ticker_row.get("return_5d"),
        "return_10d": ticker_row.get("return_10d"),
        "return_20d": ticker_row.get("return_20d"),
        "distance_to_ema20_pct": ticker_row.get("distance_to_ema20_pct"),
        "ticker_trend_state": ticker_row.get("ticker_trend_state"),
        "latest_structure_label": ticker_row.get("latest_structure_label"),
        "latest_structure_freshness": ticker_row.get("latest_structure_freshness"),
        "latest_bos_event_type": ticker_row.get("latest_bos_event_type"),
        "latest_bos_freshness": ticker_row.get("latest_bos_freshness"),
        "latest_reset_reason": ticker_row.get("latest_reset_reason"),
        "latest_reset_freshness": ticker_row.get("latest_reset_freshness"),
        "breakout_signal": ticker_row.get("breakout_signal"),
        "pullback_signal": ticker_row.get("pullback_signal"),
        "exit_risk_signal": ticker_row.get("exit_risk_signal"),
        "exit_risk_severity": ticker_row.get("exit_risk_severity"),
        "exit_reason": ticker_row.get("exit_reason"),
        "subindustry_timing_state": subindustry_context.get("timing_state"),
        "subindustry_overheat_risk_level": subindustry_context.get("overheat_risk_level"),
        "layer_timing_state": layer_context.get("timing_state"),
        "layer_overheat_risk_level": layer_context.get("overheat_risk_level"),
        "price_data_status": ticker_row.get("price_data_status"),
    }
    output_row["subindustry_context_risk"] = _daily_context_risk_value(
        in_datacenter_ecosystem=output_row["in_datacenter_ecosystem"],
        has_risk=_has_subindustry_context_risk(
            subindustry_timing_state=output_row.get("subindustry_timing_state"),
            subindustry_overheat_risk_level=output_row.get("subindustry_overheat_risk_level"),
        ),
    )
    output_row["layer_context_risk"] = _daily_context_risk_value(
        in_datacenter_ecosystem=output_row["in_datacenter_ecosystem"],
        has_risk=_has_layer_context_risk(
            layer_timing_state=output_row.get("layer_timing_state"),
            layer_overheat_risk_level=output_row.get("layer_overheat_risk_level"),
        ),
    )
    output_row["watchlist_status"] = _classify_daily_watchlist_status(output_row)
    return output_row


def _build_daily_watchlist_rows(
    *,
    watchlist_tickers: Sequence[str],
    ticker_rows: Sequence[dict[str, object]],
    group_rows: Sequence[dict[str, object]],
    synthetic_rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    ticker_by_symbol = {
        str(row.get("ticker") or ""): row
        for row in ticker_rows
        if row.get("ticker") is not None
    }
    group_context_by_key = {
        (row.get("group_type"), row.get("group_name")): row
        for row in group_rows
    }
    synthetic_context_by_key = _build_group_synthetic_context_by_key(
        synthetic_rows,
        include_date=False,
    )
    output_rows: list[dict[str, object]] = []
    for ticker in watchlist_tickers:
        ticker_row = ticker_by_symbol.get(ticker)
        if ticker_row is None:
            output_rows.append(
                {
                    "ticker": ticker,
                    "watchlist_status": "NOT_PART_OF_DATACENTER_ECOSYSTEM",
                    "in_datacenter_ecosystem": "NO",
                }
            )
            continue
        output_rows.append(
            _build_daily_report_ticker_row(
                ticker_row=ticker_row,
                group_context_by_key=group_context_by_key,
                synthetic_context_by_key=synthetic_context_by_key,
            )
        )
    return output_rows


def _build_daily_taxonomy_listing_rows(
    *,
    ticker_rows: Sequence[dict[str, object]],
    group_rows: Sequence[dict[str, object]],
    synthetic_rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    layer_names = sorted(
        {
            str(row.get("primary_layer") or "")
            for row in ticker_rows
            if row.get("primary_layer")
        }
    )
    subindustries_by_layer: dict[str, set[str]] = {}
    for row in ticker_rows:
        layer_name = str(row.get("primary_layer") or "")
        subindustry_name = str(row.get("primary_subindustry") or "")
        if not layer_name or not subindustry_name:
            continue
        subindustries_by_layer.setdefault(layer_name, set()).add(subindustry_name)
    group_context_by_key = {
        (row.get("group_type"), row.get("group_name")): row
        for row in group_rows
    }
    synthetic_context_by_key = _build_group_synthetic_context_by_key(
        synthetic_rows,
        include_date=False,
    )
    ticker_rows_by_group: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in ticker_rows:
        layer_name = str(row.get("primary_layer") or "")
        subindustry_name = str(row.get("primary_subindustry") or "")
        if not layer_name or not subindustry_name or row.get("ticker") is None:
            continue
        ticker_rows_by_group.setdefault((layer_name, subindustry_name), []).append(row)
    output_rows: list[dict[str, object]] = []
    for layer_name in layer_names:
        layer_group_row = group_context_by_key.get(("layer", layer_name), {})
        layer_synthetic_row = synthetic_context_by_key.get(("layer", layer_name), {})
        output_rows.append(
            {
                "row_type": "LAYER",
                "layer": layer_name,
                "subindustry": "",
                "ticker": "",
                "status": layer_group_row.get("timing_state"),
                "subindustry_context_risk": "",
                "layer_context_risk": _daily_context_risk_value(
                    in_datacenter_ecosystem="YES",
                    has_risk=_has_layer_context_risk(
                        layer_timing_state=layer_group_row.get("timing_state"),
                        layer_overheat_risk_level=layer_group_row.get("overheat_risk_level"),
                    ),
                ),
                "close": layer_synthetic_row.get("synthetic_close"),
                "return_5d": layer_group_row.get("return_5d"),
                "return_10d": layer_group_row.get("return_10d"),
                "return_20d": layer_group_row.get("return_20d"),
                "distance_to_ema20_pct": layer_synthetic_row.get("distance_to_ema20_pct"),
                "trend_state": layer_synthetic_row.get("trend_classification"),
                "latest_structure_label": layer_synthetic_row.get("latest_structure_label"),
                "latest_structure_freshness": layer_synthetic_row.get("latest_structure_freshness"),
                "latest_bos_event_type": layer_synthetic_row.get("latest_bos_event_type"),
                "latest_bos_freshness": layer_synthetic_row.get("latest_bos_freshness"),
                "latest_reset_reason": layer_synthetic_row.get("latest_reset_reason"),
                "latest_reset_freshness": layer_synthetic_row.get("latest_reset_freshness"),
                "breakout_signal": None,
                "pullback_signal": None,
                "exit_risk_signal": None,
                "exit_risk_severity": None,
                "exit_reason": None,
                "price_data_status": layer_group_row.get("data_quality_status"),
            }
        )
        for subindustry_name in sorted(subindustries_by_layer.get(layer_name, set())):
            subindustry_group_row = group_context_by_key.get(("subindustry", subindustry_name), {})
            subindustry_synthetic_row = synthetic_context_by_key.get(("subindustry", subindustry_name), {})
            output_rows.append(
                {
                    "row_type": "SUBINDUSTRY",
                    "layer": layer_name,
                    "subindustry": subindustry_name,
                    "ticker": "",
                    "status": subindustry_group_row.get("timing_state"),
                    "subindustry_context_risk": _daily_context_risk_value(
                        in_datacenter_ecosystem="YES",
                        has_risk=_has_subindustry_context_risk(
                            subindustry_timing_state=subindustry_group_row.get("timing_state"),
                            subindustry_overheat_risk_level=subindustry_group_row.get("overheat_risk_level"),
                        ),
                    ),
                    "layer_context_risk": _daily_context_risk_value(
                        in_datacenter_ecosystem="YES",
                        has_risk=_has_layer_context_risk(
                            layer_timing_state=layer_group_row.get("timing_state"),
                            layer_overheat_risk_level=layer_group_row.get("overheat_risk_level"),
                        ),
                    ),
                    "close": subindustry_synthetic_row.get("synthetic_close"),
                    "return_5d": subindustry_group_row.get("return_5d"),
                    "return_10d": subindustry_group_row.get("return_10d"),
                    "return_20d": subindustry_group_row.get("return_20d"),
                    "distance_to_ema20_pct": subindustry_synthetic_row.get("distance_to_ema20_pct"),
                    "trend_state": subindustry_synthetic_row.get("trend_classification"),
                    "latest_structure_label": subindustry_synthetic_row.get("latest_structure_label"),
                    "latest_structure_freshness": subindustry_synthetic_row.get("latest_structure_freshness"),
                    "latest_bos_event_type": subindustry_synthetic_row.get("latest_bos_event_type"),
                    "latest_bos_freshness": subindustry_synthetic_row.get("latest_bos_freshness"),
                    "latest_reset_reason": subindustry_synthetic_row.get("latest_reset_reason"),
                    "latest_reset_freshness": subindustry_synthetic_row.get("latest_reset_freshness"),
                    "breakout_signal": None,
                    "pullback_signal": None,
                    "exit_risk_signal": None,
                    "exit_risk_severity": None,
                    "exit_reason": None,
                    "price_data_status": subindustry_group_row.get("data_quality_status"),
                }
            )
            for ticker_row in sorted(
                ticker_rows_by_group.get((layer_name, subindustry_name), []),
                key=lambda row: str(row.get("ticker") or ""),
            ):
                ticker_output_row = _build_daily_report_ticker_row(
                    ticker_row=ticker_row,
                    group_context_by_key=group_context_by_key,
                    synthetic_context_by_key=synthetic_context_by_key,
                )
                output_rows.append(
                    {
                        "row_type": "TICKER",
                        "layer": layer_name,
                        "subindustry": subindustry_name,
                        "ticker": ticker_output_row.get("ticker"),
                        "status": ticker_output_row.get("watchlist_status"),
                        "subindustry_context_risk": ticker_output_row.get("subindustry_context_risk"),
                        "layer_context_risk": ticker_output_row.get("layer_context_risk"),
                        "close": ticker_output_row.get("close"),
                        "return_5d": ticker_output_row.get("return_5d"),
                        "return_10d": ticker_output_row.get("return_10d"),
                        "return_20d": ticker_output_row.get("return_20d"),
                        "distance_to_ema20_pct": ticker_output_row.get("distance_to_ema20_pct"),
                        "trend_state": ticker_output_row.get("ticker_trend_state"),
                        "latest_structure_label": ticker_output_row.get("latest_structure_label"),
                        "latest_structure_freshness": ticker_output_row.get("latest_structure_freshness"),
                        "latest_bos_event_type": ticker_output_row.get("latest_bos_event_type"),
                        "latest_bos_freshness": ticker_output_row.get("latest_bos_freshness"),
                        "latest_reset_reason": ticker_output_row.get("latest_reset_reason"),
                        "latest_reset_freshness": ticker_output_row.get("latest_reset_freshness"),
                        "breakout_signal": ticker_output_row.get("breakout_signal"),
                        "pullback_signal": ticker_output_row.get("pullback_signal"),
                        "exit_risk_signal": ticker_output_row.get("exit_risk_signal"),
                        "exit_risk_severity": ticker_output_row.get("exit_risk_severity"),
                        "exit_reason": ticker_output_row.get("exit_reason"),
                        "price_data_status": ticker_output_row.get("price_data_status"),
                    }
                )
    return output_rows


def _resolve_daily_taxonomy_version(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> tuple[str | None, int]:
    if taxonomy_version is not None:
        return taxonomy_version, 0
    rows = conn.execute(
        """
        SELECT DISTINCT taxonomy_version
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
        ORDER BY taxonomy_version ASC
        """,
        (signal_date, signal_version),
    ).fetchall()
    versions = [str(row["taxonomy_version"]) for row in rows if row["taxonomy_version"] is not None]
    if len(versions) == 1:
        return versions[0], 1
    if len(versions) > 1:
        raise ValueError(
            "Multiple taxonomy_version values exist for the selected signal_date and signal_version; "
            "pass --taxonomy-version explicitly"
        )
    return None, 0


def _load_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if taxonomy_version is None:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
          AND taxonomy_version = ?
        ORDER BY taxonomy_version ASC, group_type ASC, group_name ASC
        """,
        (signal_date, signal_version, taxonomy_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if taxonomy_version is None:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
          AND taxonomy_version = ?
        ORDER BY taxonomy_version ASC, ticker ASC
        """,
        (signal_date, signal_version, taxonomy_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _load_synthetic_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    calc_version: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if taxonomy_version is None:
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
          AND calc_version = ?
          AND taxonomy_version = ?
        ORDER BY taxonomy_version ASC, group_type ASC, group_name ASC
        """,
        (signal_date, calc_version, taxonomy_version),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def load_daily_swing_report_data(
    *,
    analysis_db_path: str | Path,
    signal_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    taxonomy_version: str | None = None,
    watchlist_file: str | Path | None = None,
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
        resolved_taxonomy_version, taxonomy_version_inferred = _resolve_daily_taxonomy_version(
            conn,
            signal_date=normalized_signal_date,
            signal_version=signal_version,
            taxonomy_version=taxonomy_version,
        )
        group_rows = _load_group_rows(
            conn,
            signal_date=normalized_signal_date,
            signal_version=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        ticker_rows = _load_ticker_rows(
            conn,
            signal_date=normalized_signal_date,
            signal_version=signal_version,
            taxonomy_version=resolved_taxonomy_version,
        )
        synthetic_rows = _load_synthetic_rows(
            conn,
            signal_date=normalized_signal_date,
            calc_version=ohlc_calc_version,
            taxonomy_version=resolved_taxonomy_version,
        )
    result = {
        "signal_date": normalized_signal_date,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        "taxonomy_version": resolved_taxonomy_version,
        "taxonomy_version_inferred": taxonomy_version_inferred,
        "group_rows": group_rows,
        "ticker_rows": ticker_rows,
        "synthetic_rows": synthetic_rows,
    }
    result.update(_resolve_watchlist_context(watchlist_file))
    return result


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
    include_taxonomy_listing: bool = True,
) -> str:
    if top_n <= 0:
        raise ValueError(f"Invalid top_n: {top_n}")

    signal_date = str(report_data["signal_date"])
    signal_version = str(report_data["signal_version"])
    ohlc_calc_version = str(report_data["ohlc_calc_version"])
    taxonomy_version = "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"])
    group_rows = list(report_data["group_rows"])  # type: ignore[arg-type]
    ticker_rows = list(report_data["ticker_rows"])  # type: ignore[arg-type]
    synthetic_rows = list(report_data["synthetic_rows"])  # type: ignore[arg-type]
    watchlist_tickers = list(report_data.get("watchlist_tickers") or [])
    watchlist_file_path = str(report_data.get("watchlist_file_path") or DEFAULT_WATCHLIST_FILE)
    watchlist_file_missing = bool(report_data.get("watchlist_file_missing"))
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
    group_context_by_key = {
        (row.get("group_type"), row.get("group_name")): row
        for row in group_rows
    }
    structure_break_rows: list[dict[str, object]] = []
    for row in synthetic_summary_rows:
        if row.get("latest_bos_event_type") is None and row.get("latest_reset_reason") is None:
            continue
        group_context = group_context_by_key.get((row.get("group_type"), row.get("group_name")), {})
        structure_break_rows.append(
            {
                "group_type": row.get("group_type"),
                "group_name": row.get("group_name"),
                "latest_bos_event_type": row.get("latest_bos_event_type"),
                "latest_bos_event_date": row.get("latest_bos_event_date"),
                "latest_bos_freshness": row.get("latest_bos_freshness"),
                "latest_reset_reason": row.get("latest_reset_reason"),
                "latest_reset_event_date": row.get("latest_reset_event_date"),
                "latest_reset_freshness": row.get("latest_reset_freshness"),
                "latest_structure_label": row.get("latest_structure_label"),
                "latest_structure_freshness": row.get("latest_structure_freshness"),
                "trend_classification": row.get("trend_classification"),
                "timing_state": group_context.get("timing_state"),
                "overheat_risk_level": group_context.get("overheat_risk_level"),
            }
        )
    structure_break_rows.sort(
        key=lambda row: (
            GROUP_RESET_PRIORITY.get(row.get("latest_reset_reason"), 2),
            GROUP_BOS_PRIORITY.get(row.get("latest_bos_event_type"), 2),
            FRESHNESS_PRIORITY.get(row.get("latest_bos_freshness"), 3),
            str(row.get("group_type") or ""),
            str(row.get("group_name") or ""),
        )
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
            EXIT_RISK_SEVERITY_PRIORITY.get(row.get("exit_risk_severity"), 3),
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
        f"taxonomy_version: {taxonomy_version}",
        f"generated_at_utc: {generated}",
        "source_tables: dc_group_swing_signal_daily, dc_ticker_swing_signal_daily, dc_group_synthetic_ohlc_daily",
    ]
    watchlist_rows = _build_daily_watchlist_rows(
        watchlist_tickers=watchlist_tickers,
        ticker_rows=ticker_rows,
        group_rows=group_rows,
        synthetic_rows=synthetic_rows,
    )
    taxonomy_listing_rows = _build_daily_taxonomy_listing_rows(
        ticker_rows=ticker_rows,
        group_rows=group_rows,
        synthetic_rows=synthetic_rows,
    )
    watchlist_summary_rows = [
        {"metric": "watchlist_tickers_total", "value": len(watchlist_rows)},
        {"metric": "watchlist_in_datacenter_taxonomy", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES")},
        {"metric": "watchlist_not_in_datacenter_taxonomy", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "NO")},
        {"metric": "watchlist_missing_price", "value": sum(1 for row in watchlist_rows if row.get("watchlist_status") == "MISSING_PRICE")},
        {"metric": "watchlist_subindustry_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("subindustry_context_risk") == "YES")},
        {"metric": "watchlist_layer_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("layer_context_risk") == "YES")},
        {"metric": "watchlist_both_context_risk_count", "value": sum(1 for row in watchlist_rows if row.get("in_datacenter_ecosystem") == "YES" and row.get("subindustry_context_risk") == "YES" and row.get("layer_context_risk") == "YES")},
        {"metric": "watchlist_breakout_count", "value": sum(1 for row in watchlist_rows if row.get("breakout_signal") == 1)},
        {"metric": "watchlist_pullback_count", "value": sum(1 for row in watchlist_rows if row.get("pullback_signal") == 1)},
        {"metric": "watchlist_high_exit_risk_count", "value": sum(1 for row in watchlist_rows if row.get("exit_risk_severity") == "HIGH")},
        {"metric": "watchlist_medium_exit_risk_count", "value": sum(1 for row in watchlist_rows if row.get("exit_risk_severity") == "MEDIUM")},
    ]
    lines.extend(
        [
            "",
            "## Watchlist Summary",
            _format_table(["metric", "value"], watchlist_summary_rows).rstrip(),
        ]
    )
    if watchlist_file_missing:
        lines.append(f"No watchlist file found: {watchlist_file_path}")
    elif not watchlist_rows:
        lines.append("No watchlist tickers.")
    else:
        lines.extend(
            [
                "",
                _format_table(
                    [
                        "ticker",
                        "watchlist_status",
                        "subindustry_context_risk",
                        "layer_context_risk",
                        "subindustry_trend_classification",
                        "subindustry_latest_structure_label",
                        "layer_trend_classification",
                        "layer_latest_structure_label",
                        "in_datacenter_ecosystem",
                        "primary_layer",
                        "primary_subindustry",
                        "close",
                        "return_5d",
                        "return_10d",
                        "return_20d",
                        "distance_to_ema20_pct",
                        "ticker_trend_state",
                        "latest_structure_label",
                        "latest_structure_freshness",
                        "latest_bos_event_type",
                        "latest_bos_freshness",
                        "latest_reset_reason",
                        "latest_reset_freshness",
                        "breakout_signal",
                        "pullback_signal",
                        "exit_risk_signal",
                        "exit_risk_severity",
                        "exit_reason",
                        "subindustry_timing_state",
                        "subindustry_overheat_risk_level",
                        "layer_timing_state",
                        "layer_overheat_risk_level",
                        "price_data_status",
                    ],
                    watchlist_rows,
                ).rstrip(),
            ]
        )

    lines.extend(["", "## 3. Dashboard"])
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

    lines.extend(["", "## 4. Rotation Risk / Overheat Index"])
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

    lines.extend(["", "## 5. Subindustry Timing States"])
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
        ("## 6. Buy-Zone Subindustries", buy_zone_rows),
        ("## 7. Add-On Pullback Subindustries", add_on_rows),
        ("## 8. Trim/Watch Subindustries", trim_rows),
        ("## 9. Exit-Zone Subindustries", exit_rows),
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

    lines.extend(["", "## 10. Synthetic OHLC Structure Summary"])
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
                "latest_structure_age_trading_days",
                "latest_structure_freshness",
                "latest_bos_event_type",
                "latest_bos_age_trading_days",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_age_trading_days",
                "latest_reset_freshness",
                "trend_classification",
                "relative_close_extension_20",
                "relative_upper_wick_20",
                "relative_lower_wick_20",
                "data_quality_status",
            ],
            synthetic_summary_rows,
        ).rstrip()
    )

    lines.extend(["", "## 11. Group Structure Breaks / Resets"])
    lines.append(
        _format_table(
            [
                "group_type",
                "group_name",
                "latest_bos_event_type",
                "latest_bos_event_date",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_event_date",
                "latest_reset_freshness",
                "latest_structure_label",
                "latest_structure_freshness",
                "trend_classification",
                "timing_state",
                "overheat_risk_level",
            ],
            structure_break_rows,
        ).rstrip()
    )

    ticker_section_specs = [
        (
            "## 12. Breakout Ticker Scanner",
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
                "ticker_trend_state",
                "latest_bos_event_type",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_freshness",
                "bullish_candle_signal",
                "bearish_candle_signal",
                "bullish_divergence_signal",
                "bearish_divergence_signal",
                "price_data_status",
            ],
        ),
        (
            "## 13. Pullback Ticker Scanner",
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
                "ticker_trend_state",
                "latest_bos_event_type",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_freshness",
                "bullish_candle_signal",
                "bullish_divergence_signal",
                "hidden_bullish_divergence_signal",
                "price_data_status",
            ],
        ),
        (
            "## 14. Exit-Risk Ticker Scanner",
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
                "latest_structure_age_trading_days",
                "latest_structure_freshness",
                "ticker_trend_state",
                "latest_bos_event_type",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_freshness",
                "exit_reason",
                "exit_risk_severity",
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

    lines.extend(["", "## 15. Data Quality"])
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

    lines.extend(["", "## 16. Missing / Incomplete Inputs Summary"])
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

    if include_taxonomy_listing:
        lines.extend(["", "## Datacenter Taxonomy Listing"])
        if not taxonomy_listing_rows:
            lines.append("No rows.")
        else:
            taxonomy_headers = [
                "row_type",
                "layer",
                "subindustry",
                "ticker",
                "status",
                "subindustry_context_risk",
                "layer_context_risk",
                "close",
                "return_5d",
                "return_10d",
                "return_20d",
                "distance_to_ema20_pct",
                "trend_state",
                "latest_structure_label",
                "latest_structure_freshness",
                "latest_bos_event_type",
                "latest_bos_freshness",
                "latest_reset_reason",
                "latest_reset_freshness",
                "breakout_signal",
                "pullback_signal",
                "exit_risk_signal",
                "exit_risk_severity",
                "exit_reason",
                "price_data_status",
            ]
            current_layer = None
            current_layer_rows: list[dict[str, object]] = []
            for row in taxonomy_listing_rows:
                layer_name = str(row.get("layer") or "")
                if layer_name != current_layer:
                    if current_layer_rows:
                        lines.append(_format_table(taxonomy_headers, current_layer_rows).rstrip())
                        current_layer_rows = []
                    lines.extend(["", f"### Layer: {layer_name}"])
                    current_layer = layer_name
                current_layer_rows.append(row)
            if current_layer_rows:
                lines.append(_format_table(taxonomy_headers, current_layer_rows).rstrip())

    return "\n".join(lines).strip() + "\n"


def build_csv_daily_swing_report(
    report_data: dict[str, object],
    *,
    generated_at_utc: str | None = None,
    top_n: int = 20,
    include_taxonomy_listing: bool = True,
) -> str:
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
        include_taxonomy_listing=include_taxonomy_listing,
    )
    rows = _build_csv_rows_from_markdown(markdown)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    max_columns = max((len(row) for row in rows), default=1)
    writer.writerow(["section", *(f"value_{index}" for index in range(1, max_columns))])
    for row in rows:
        writer.writerow([*row, *([""] * (max_columns - len(row)))])
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
    taxonomy_version: str | None = None,
    output_md: str | Path | None = None,
    output_csv: str | Path | None = None,
    watchlist_file: str | Path | None = None,
    top_n: int = 20,
    generated_at_utc: str | None = None,
    include_taxonomy_listing: bool = True,
) -> dict[str, object]:
    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db_path,
        signal_date=signal_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        taxonomy_version=taxonomy_version,
        watchlist_file=watchlist_file,
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
        include_taxonomy_listing=include_taxonomy_listing,
    )
    csv_text = build_csv_daily_swing_report(
        report_data,
        generated_at_utc=generated_at_utc,
        top_n=top_n,
        include_taxonomy_listing=include_taxonomy_listing,
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
        "taxonomy_version": "" if report_data.get("taxonomy_version") is None else str(report_data["taxonomy_version"]),
        "taxonomy_version_inferred": int(report_data.get("taxonomy_version_inferred") or 0),
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
