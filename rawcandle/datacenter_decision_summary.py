from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class DecisionSummaryError(ValueError):
    pass


STATUS_PRIORITY = {
    "NOT_PART_OF_DATACENTER_ECOSYSTEM": 0,
    "HIGH_EXIT_RISK": 1,
    "MEDIUM_EXIT_RISK": 2,
    "GROUP_RISK": 3,
    "NEUTRAL_MONITOR": 4,
    "BREAKOUT_CANDIDATE": 5,
}

WATCHLIST_METRICS = [
    "watchlist_tickers_total",
    "watchlist_in_datacenter_taxonomy",
    "watchlist_not_in_datacenter_taxonomy",
    "watchlist_missing_price",
    "watchlist_subindustry_context_risk_count",
    "watchlist_layer_context_risk_count",
    "watchlist_both_context_risk_count",
    "watchlist_breakout_count",
    "watchlist_pullback_count",
    "watchlist_high_exit_risk_count",
    "watchlist_medium_exit_risk_count",
]

ECOSYSTEM_CHANGE_METRICS = [
    "return_5d",
    "return_10d",
    "return_20d",
    "pct_above_ma10",
    "pct_above_ema20",
    "ema20_breadth_delta_5d",
    "trend_breadth",
    "weakness_breadth",
    "timing_state",
    "overheat_risk_level",
    "data_quality_status",
]

GROUP_FIELDS = [
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
]

WATCHLIST_FIELDS = [
    "ticker",
    "watchlist_status",
    "primary_layer",
    "primary_subindustry",
    "close",
    "return_5d",
    "return_10d",
    "return_20d",
    "distance_to_ema20_pct",
    "ticker_trend_state",
    "latest_structure_label",
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
]

DAILY_BREAKOUT_FIELDS = [
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
    "price_data_status",
    "latest_bullish_relevance_class",
    "latest_bullish_relevance_reason",
    "latest_bearish_relevance_class",
    "latest_bearish_relevance_reason",
]

DAILY_PULLBACK_FIELDS = [
    "ticker",
    "primary_layer",
    "primary_subindustry",
    "close",
    "distance_to_ema10_pct",
    "distance_to_ema20_pct",
    "fast_ema10_pullback_signal",
    "conservative_ema20_pullback_signal",
    "return_5d",
    "return_20d",
    "return_60d",
    "latest_structure_label",
    "ticker_trend_state",
    "price_data_status",
    "latest_bullish_relevance_class",
    "latest_bullish_relevance_reason",
]

DAILY_EXIT_FIELDS = [
    "ticker",
    "primary_layer",
    "primary_subindustry",
    "close",
    "return_5d",
    "return_10d",
    "return_20d",
    "distance_to_ema20_pct",
    "latest_structure_label",
    "ticker_trend_state",
    "exit_risk_severity",
    "exit_reason",
    "price_data_status",
    "latest_bearish_relevance_class",
    "latest_bearish_relevance_reason",
]

ROLLING5_PULLBACK_ALERT_FIELDS = [
    "ticker",
    "rolling_5_pullback_state",
    "primary_layer",
    "primary_subindustry",
    "pullback_days",
    "fast_ema10_pullback_days",
    "conservative_ema20_pullback_days",
    "breakout_days",
    "exit_risk_days",
    "latest_ticker_trend_state",
    "latest_bullish_relevance_class",
    "latest_bearish_relevance_class",
    "primary_reason",
    "next_action",
]

ROLLING30_BUY_FIELDS = [
    "ticker",
    "rolling_30_buy_state",
    "primary_layer",
    "primary_subindustry",
    "window_watchlist_status",
    "current_watchlist_status",
    "breakout_days",
    "pullback_days",
    "exit_risk_days",
    "latest_ticker_trend_state",
    "latest_structure_label",
    "primary_reason",
    "blocking_reason",
]

ROLLING30_EXIT_FIELDS = [
    "ticker",
    "rolling_30_exit_state",
    "primary_layer",
    "primary_subindustry",
    "window_watchlist_status",
    "current_watchlist_status",
    "exit_risk_days",
    "latest_exit_risk_severity",
    "latest_exit_reason",
    "latest_ticker_trend_state",
    "primary_reason",
    "risk_reason",
]


@dataclass(frozen=True)
class MarkdownReport:
    path: Path
    text: str


def normalize_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def parse_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## ") and metadata:
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        norm = normalize_key(key)
        if norm:
            metadata[norm] = value.strip()
    return metadata


def heading_pattern(title: str) -> re.Pattern[str]:
    escaped = re.escape(title.strip())
    return re.compile(rf"^(?P<marks>#+)\s+{escaped}\s*$", re.IGNORECASE | re.MULTILINE)


def extract_section(text: str, title: str, *, required: bool = True) -> str:
    match = heading_pattern(title).search(text)
    if not match:
        if required:
            raise DecisionSummaryError(f"Required section not found: {title}")
        return ""
    level = len(match.group("marks"))
    start = match.end()
    next_heading = re.compile(rf"^#{{1,{level}}}\s+", re.MULTILINE)
    next_match = next_heading.search(text, start)
    end = next_match.start() if next_match else len(text)
    return text[start:end].strip()


def parse_markdown_tables(section: str) -> list[list[dict[str, str]]]:
    lines = section.splitlines()
    tables: list[list[dict[str, str]]] = []
    index = 0
    while index < len(lines) - 1:
        if _is_table_header(lines[index], lines[index + 1]):
            headers = [_clean_cell(cell) for cell in _split_row(lines[index])]
            normalized_headers = [normalize_key(header) for header in headers]
            index += 2
            rows: list[dict[str, str]] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                cells = [_clean_cell(cell) for cell in _split_row(lines[index])]
                if len(cells) < len(normalized_headers):
                    cells.extend([""] * (len(normalized_headers) - len(cells)))
                row = {
                    header: cells[pos] if pos < len(cells) else ""
                    for pos, header in enumerate(normalized_headers)
                }
                rows.append(row)
                index += 1
            tables.append(rows)
        else:
            index += 1
    return tables


def first_table(section: str, *, required: bool = True) -> list[dict[str, str]]:
    tables = parse_markdown_tables(section)
    if not tables:
        if required and "No rows." not in section:
            raise DecisionSummaryError("Required markdown table not found")
        return []
    return tables[0]


def table_at(section: str, index: int, *, required: bool = True) -> list[dict[str, str]]:
    tables = parse_markdown_tables(section)
    if index < len(tables):
        return tables[index]
    if required:
        raise DecisionSummaryError(f"Required markdown table #{index + 1} not found")
    return []


def metric_map(rows: Sequence[dict[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        key = value_for(row, "metric")
        if not key:
            continue
        result[normalize_key(key)] = value_for(row, "value")
    return result


def build_decision_summary(
    *,
    current_daily: Path,
    previous_daily: Path,
    current_rolling2: Path,
    current_rolling5: Path,
    current_rolling30: Path,
    output: Path,
) -> Path:
    reports = {
        "current_daily": _read_report(current_daily),
        "previous_daily": _read_report(previous_daily),
        "current_rolling2": _read_report(current_rolling2),
        "current_rolling5": _read_report(current_rolling5),
        "current_rolling30": _read_report(current_rolling30),
    }

    rendered = render_decision_summary(reports)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return output


def render_decision_summary(reports: dict[str, MarkdownReport]) -> str:
    current_daily = reports["current_daily"]
    previous_daily = reports["previous_daily"]
    rolling2 = reports["current_rolling2"]
    rolling5 = reports["current_rolling5"]
    rolling30 = reports["current_rolling30"]

    current_meta = parse_metadata(extract_section(current_daily.text, "1. Title and run metadata"))
    previous_meta = parse_metadata(extract_section(previous_daily.text, "1. Title and run metadata"))

    current_watch_section = extract_section(current_daily.text, "Watchlist Summary")
    previous_watch_section = extract_section(previous_daily.text, "Watchlist Summary")
    current_watch_metrics = metric_map(table_at(current_watch_section, 0))
    previous_watch_metrics = metric_map(table_at(previous_watch_section, 0))
    current_watchlist = table_at(current_watch_section, 1)
    previous_watchlist = table_at(previous_watch_section, 1)

    rolling2_change = first_table(extract_section(rolling2.text, "4. Ecosystem window change"))

    buy_zone = first_table(extract_section(current_daily.text, "6. Buy-Zone Subindustries"), required=False)
    add_on = first_table(extract_section(current_daily.text, "7. Add-On Pullback Subindustries"), required=False)
    trim_watch = first_table(extract_section(current_daily.text, "8. Trim/Watch Subindustries"), required=False)
    exit_zone = first_table(extract_section(current_daily.text, "9. Exit-Zone Subindustries"), required=False)

    daily_breakouts = first_table(extract_section(current_daily.text, "12. Breakout Ticker Scanner"), required=False)
    daily_pullbacks = first_table(extract_section(current_daily.text, "13. Pullback Ticker Scanner"), required=False)
    daily_exits = first_table(extract_section(current_daily.text, "14. Exit-Risk Ticker Scanner"), required=False)
    rolling5_breakouts = first_table(extract_section(rolling5.text, "8. Repeated breakout tickers"), required=False)
    rolling5_pullbacks = first_table(extract_section(rolling5.text, "9. Repeated pullback tickers"), required=False)
    rolling5_alerts = first_table(extract_section(rolling5.text, "Rolling 5 Pullback Alerts"), required=False)
    rolling30_buy = first_table(extract_section(rolling30.text, "Rolling 30 Buy Filter"), required=False)
    rolling30_exit = first_table(extract_section(rolling30.text, "Rolling 30 Exit Prefilter"), required=False)

    status_changes = compare_watchlist_status(current_watchlist, previous_watchlist)
    signal_changes = compare_watchlist_signals(current_watchlist, previous_watchlist)
    in_taxonomy, not_in_taxonomy = split_watchlist_by_taxonomy(current_watchlist)

    lines: list[str] = []
    current_date = current_meta.get("signal_date", "")
    title_date = current_date or "unknown"
    lines.append(f"# Datacenter Daily Decision Summary - {title_date}")
    lines.append("")
    lines.extend(_metadata_section(current_meta, previous_meta, reports))
    lines.extend(_executive_signal_section(current_watch_metrics, previous_watch_metrics, rolling2_change, buy_zone, status_changes))
    lines.extend(_ecosystem_change_section(rolling2_change))
    lines.extend(_watchlist_summary_section(current_watch_metrics, previous_watch_metrics))
    lines.extend(_watchlist_status_change_section(status_changes, signal_changes))
    lines.extend(_rotation_map_section(buy_zone, add_on, trim_watch, exit_zone))
    lines.extend(_watchlist_decision_section(in_taxonomy, not_in_taxonomy))
    lines.extend(_scanner_section(daily_breakouts, daily_pullbacks, rolling5_breakouts, rolling5_pullbacks, rolling5_alerts, rolling30_buy))
    lines.extend(_exit_risk_section(daily_exits, rolling30_exit))
    lines.extend(_action_summary_section(current_watch_metrics, buy_zone, daily_breakouts, daily_pullbacks, daily_exits, rolling30_buy, rolling30_exit))
    return "\n".join(lines).rstrip() + "\n"


def compare_watchlist_status(
    current_rows: Sequence[dict[str, str]],
    previous_rows: Sequence[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    previous_by_ticker = {value_for(row, "ticker"): row for row in previous_rows if value_for(row, "ticker")}
    improved: list[dict[str, str]] = []
    deteriorated: list[dict[str, str]] = []
    for current in current_rows:
        ticker = value_for(current, "ticker")
        if not ticker or ticker not in previous_by_ticker:
            continue
        previous = previous_by_ticker[ticker]
        prev_status = value_for(previous, "watchlist_status")
        curr_status = value_for(current, "watchlist_status")
        prev_rank = STATUS_PRIORITY.get(prev_status, -1)
        curr_rank = STATUS_PRIORITY.get(curr_status, -1)
        if prev_rank == curr_rank:
            continue
        target = improved if curr_rank > prev_rank else deteriorated
        target.append(
            {
                "ticker": ticker,
                "previous_status": prev_status,
                "current_status": curr_status,
                "previous_rank": str(prev_rank),
                "current_rank": str(curr_rank),
            }
        )
    return {
        "improved": sorted(improved, key=lambda row: (row["ticker"])),
        "deteriorated": sorted(deteriorated, key=lambda row: (row["ticker"])),
    }


def compare_watchlist_signals(
    current_rows: Sequence[dict[str, str]],
    previous_rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    fields = ["breakout_signal", "pullback_signal", "exit_risk_signal", "exit_risk_severity"]
    previous_by_ticker = {value_for(row, "ticker"): row for row in previous_rows if value_for(row, "ticker")}
    changes: list[dict[str, str]] = []
    for current in current_rows:
        ticker = value_for(current, "ticker")
        previous = previous_by_ticker.get(ticker)
        if not ticker or not previous:
            continue
        for field in fields:
            prev_value = value_for(previous, field)
            curr_value = value_for(current, field)
            if prev_value != curr_value:
                changes.append(
                    {
                        "ticker": ticker,
                        "field": field,
                        "previous_value": prev_value,
                        "current_value": curr_value,
                    }
                )
    return sorted(changes, key=lambda row: (row["ticker"], row["field"]))


def split_watchlist_by_taxonomy(rows: Sequence[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    in_taxonomy: list[dict[str, str]] = []
    not_in_taxonomy: list[dict[str, str]] = []
    for row in rows:
        value = value_for(row, "in_datacenter_ecosystem").upper()
        if value in {"NO", "FALSE", "0"}:
            not_in_taxonomy.append(row)
        else:
            in_taxonomy.append(row)
    in_taxonomy.sort(key=_watchlist_sort_key)
    not_in_taxonomy.sort(key=lambda row: value_for(row, "ticker"))
    return in_taxonomy, not_in_taxonomy


def value_for(row: dict[str, str], field: str, default: str = "") -> str:
    aliases = _aliases(field)
    for alias in aliases:
        if alias in row and row[alias] != "":
            return row[alias]
    return default


def render_table(rows: Sequence[dict[str, str]], fields: Sequence[str], *, limit: int | None = None) -> list[str]:
    selected = list(rows[:limit] if limit is not None else rows)
    if not selected:
        return ["No rows.", ""]
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in selected:
        lines.append("| " + " | ".join(_format_cell(value_for(row, field)) for field in fields) + " |")
    lines.append("")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Datacenter daily decision summary from markdown reports.")
    parser.add_argument("--current-daily", required=True, type=Path)
    parser.add_argument("--previous-daily", required=True, type=Path)
    parser.add_argument("--current-rolling2", required=True, type=Path)
    parser.add_argument("--current-rolling5", required=True, type=Path)
    parser.add_argument("--current-rolling30", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        path = build_decision_summary(
            current_daily=args.current_daily,
            previous_daily=args.previous_daily,
            current_rolling2=args.current_rolling2,
            current_rolling5=args.current_rolling5,
            current_rolling30=args.current_rolling30,
            output=args.output,
        )
    except DecisionSummaryError as exc:
        parser.error(str(exc))
    print(f"wrote {path}")
    return 0


def _metadata_section(
    current_meta: dict[str, str],
    previous_meta: dict[str, str],
    reports: dict[str, MarkdownReport],
) -> list[str]:
    rows = [
        {"field": "report_name", "value": "Datacenter Daily Decision Summary"},
        {"field": "current_signal_date", "value": current_meta.get("signal_date", "")},
        {"field": "previous_signal_date", "value": previous_meta.get("signal_date", "")},
        {"field": "generated_at_utc", "value": current_meta.get("generated_at_utc", "")},
        {"field": "signal_version", "value": current_meta.get("signal_version", "")},
        {"field": "ohlc_calc_version", "value": current_meta.get("ohlc_calc_version", "")},
        {"field": "taxonomy_version", "value": current_meta.get("taxonomy_version", "")},
    ]
    for name, report in reports.items():
        rows.append({"field": f"source_{name}", "value": str(report.path)})
    lines = ["## 1. Title and run metadata"]
    lines.extend(render_table(rows, ["field", "value"]))
    lines.append("Note: This summary is built deterministically from existing markdown reports only. It is not investment advice.")
    lines.append("")
    return lines


def _executive_signal_section(
    current_metrics: dict[str, str],
    previous_metrics: dict[str, str],
    ecosystem_rows: Sequence[dict[str, str]],
    buy_zone: Sequence[dict[str, str]],
    status_changes: dict[str, list[dict[str, str]]],
) -> list[str]:
    timing_row = _metric_row(ecosystem_rows, "timing_state")
    breadth_row = _metric_row(ecosystem_rows, "pct_above_ema20")
    timing = value_for(timing_row, "last_value") or value_for(timing_row, "current_value")
    breadth_change = value_for(breadth_row, "change")
    window_change = _classify_numeric_change(breadth_change)
    rows = [
        {"signal": "ecosystem_timing", "value": timing},
        {"signal": "rolling2_window_change", "value": window_change},
        {"signal": "watchlist_breakout_count", "value": current_metrics.get("watchlist_breakout_count", "")},
        {"signal": "watchlist_pullback_count", "value": current_metrics.get("watchlist_pullback_count", "")},
        {"signal": "watchlist_high_exit_risk_count", "value": current_metrics.get("watchlist_high_exit_risk_count", "")},
        {"signal": "status_improvements", "value": str(len(status_changes["improved"]))},
        {"signal": "status_deteriorations", "value": str(len(status_changes["deteriorated"]))},
        {"signal": "current_buy_zone_subindustries", "value": ", ".join(value_for(row, "group_name") for row in buy_zone) or "None"},
    ]
    previous_total = previous_metrics.get("watchlist_tickers_total", "")
    current_total = current_metrics.get("watchlist_tickers_total", "")
    rows.append({"signal": "watchlist_total_change", "value": f"{previous_total} -> {current_total}"})
    lines = ["## 2. Executive signal"]
    lines.extend(render_table(rows, ["signal", "value"]))
    return lines


def _ecosystem_change_section(rows: Sequence[dict[str, str]]) -> list[str]:
    by_metric = {normalize_key(value_for(row, "metric")): row for row in rows}
    rendered = []
    for metric in ECOSYSTEM_CHANGE_METRICS:
        row = by_metric.get(metric, {})
        rendered.append(
            {
                "metric": metric,
                "previous_value": value_for(row, "first_value") or value_for(row, "previous_value"),
                "current_value": value_for(row, "last_value") or value_for(row, "current_value"),
                "change": value_for(row, "change"),
            }
        )
    lines = ["## 3. Ecosystem dashboard change"]
    lines.extend(render_table(rendered, ["metric", "previous_value", "current_value", "change"]))
    return lines


def _watchlist_summary_section(current: dict[str, str], previous: dict[str, str]) -> list[str]:
    rows = []
    for metric in WATCHLIST_METRICS:
        prev = previous.get(metric, "")
        curr = current.get(metric, "")
        rows.append({"metric": metric, "previous_value": prev, "current_value": curr, "change": _delta(prev, curr)})
    lines = ["## 4. Watchlist summary and change"]
    lines.extend(render_table(rows, ["metric", "previous_value", "current_value", "change"]))
    return lines


def _watchlist_status_change_section(
    status_changes: dict[str, list[dict[str, str]]],
    signal_changes: Sequence[dict[str, str]],
) -> list[str]:
    lines = ["## 5. Ticker-level watchlist status changes", "### Improved statuses"]
    lines.extend(render_table(status_changes["improved"], ["ticker", "previous_status", "current_status", "previous_rank", "current_rank"]))
    lines.append("### Deteriorated statuses")
    lines.extend(render_table(status_changes["deteriorated"], ["ticker", "previous_status", "current_status", "previous_rank", "current_rank"]))
    lines.append("### Changed watchlist signals")
    lines.extend(render_table(signal_changes, ["ticker", "field", "previous_value", "current_value"]))
    return lines


def _rotation_map_section(
    buy_zone: Sequence[dict[str, str]],
    add_on: Sequence[dict[str, str]],
    trim_watch: Sequence[dict[str, str]],
    exit_zone: Sequence[dict[str, str]],
) -> list[str]:
    lines = ["## 6. Rotation map", "### Buy-Zone Subindustries"]
    lines.extend(render_table(buy_zone, GROUP_FIELDS))
    lines.append("### Add-On Pullback Subindustries")
    lines.extend(render_table(add_on, GROUP_FIELDS))
    lines.append("### Trim/Watch Subindustries")
    lines.extend(render_table(trim_watch, GROUP_FIELDS))
    lines.append("### Exit-Zone Subindustries")
    lines.extend(render_table(exit_zone, GROUP_FIELDS))
    return lines


def _watchlist_decision_section(
    in_taxonomy: Sequence[dict[str, str]],
    not_in_taxonomy: Sequence[dict[str, str]],
) -> list[str]:
    lines = ["## 7. Watchlist ticker decision table", "### In Datacenter taxonomy"]
    lines.extend(render_table(in_taxonomy, WATCHLIST_FIELDS))
    lines.append("### Not in Datacenter taxonomy")
    lines.extend(render_table(not_in_taxonomy, ["ticker", "watchlist_status", "in_datacenter_ecosystem", "price_data_status"]))
    return lines


def _scanner_section(
    daily_breakouts: Sequence[dict[str, str]],
    daily_pullbacks: Sequence[dict[str, str]],
    rolling5_breakouts: Sequence[dict[str, str]],
    rolling5_pullbacks: Sequence[dict[str, str]],
    rolling5_alerts: Sequence[dict[str, str]],
    rolling30_buy: Sequence[dict[str, str]],
) -> list[str]:
    lines = ["## 8. Scanner output", "### A. Daily Breakout Ticker Scanner"]
    lines.extend(render_table(daily_breakouts, DAILY_BREAKOUT_FIELDS))
    lines.append("### B. Daily Pullback Ticker Scanner")
    lines.extend(render_table(daily_pullbacks, DAILY_PULLBACK_FIELDS))
    lines.append("### C. Rolling 5 repeated breakout tickers")
    lines.extend(render_table(rolling5_breakouts, _prefixed_fields(rolling5_breakouts, DAILY_BREAKOUT_FIELDS, prefix="last_")))
    lines.append("### D. Rolling 5 pullback alerts")
    alert_rows = rolling5_alerts if rolling5_alerts else rolling5_pullbacks
    alert_fields = ROLLING5_PULLBACK_ALERT_FIELDS if rolling5_alerts else _prefixed_fields(rolling5_pullbacks, DAILY_PULLBACK_FIELDS, prefix="last_")
    lines.extend(render_table(alert_rows, alert_fields))
    lines.append("### E. Rolling 30 buy filter and watch-zone")
    lines.extend(render_table(rolling30_buy, ROLLING30_BUY_FIELDS))
    return lines


def _exit_risk_section(
    daily_exits: Sequence[dict[str, str]],
    rolling30_exit: Sequence[dict[str, str]],
) -> list[str]:
    lines = ["## 9. Exit risk focus", "### A. Daily high exit-risk scanner top 20"]
    high_daily = [row for row in daily_exits if value_for(row, "exit_risk_severity").upper() == "HIGH"]
    lines.extend(render_table(high_daily or daily_exits, DAILY_EXIT_FIELDS, limit=20))
    lines.append("### B. Rolling 30 Exit Prefilter top 20")
    lines.extend(render_table(rolling30_exit, ROLLING30_EXIT_FIELDS, limit=20))
    return lines


def _action_summary_section(
    metrics: dict[str, str],
    buy_zone: Sequence[dict[str, str]],
    daily_breakouts: Sequence[dict[str, str]],
    daily_pullbacks: Sequence[dict[str, str]],
    daily_exits: Sequence[dict[str, str]],
    rolling30_buy: Sequence[dict[str, str]],
    rolling30_exit: Sequence[dict[str, str]],
) -> list[str]:
    high_exit_count = _to_number(metrics.get("watchlist_high_exit_risk_count", "")) or 0
    rows = [
        {
            "area": "watchlist_exit_risk",
            "label": "CHECK_STOP_OR_REDUCE" if high_exit_count > 0 else "MONITOR",
            "basis": f"watchlist_high_exit_risk_count={metrics.get('watchlist_high_exit_risk_count', '')}",
        },
        {
            "area": "daily_breakouts",
            "label": "MONITOR_BREAKOUT_CONFIRMATION",
            "basis": _ticker_list(daily_breakouts),
        },
        {
            "area": "daily_pullbacks",
            "label": "MONITOR_PULLBACK_CONFIRMATION",
            "basis": _ticker_list(daily_pullbacks),
        },
        {
            "area": "buy_zone_subindustries",
            "label": "MONITOR_BREAKOUT_CONFIRMATION",
            "basis": ", ".join(value_for(row, "group_name") for row in buy_zone) or "No rows.",
        },
        {
            "area": "rolling30_watch_zone",
            "label": "MONITOR_BREAKOUT_CONFIRMATION",
            "basis": _ticker_list(rolling30_buy),
        },
        {
            "area": "exit_risk_focus",
            "label": "CHECK_STOP_OR_REDUCE" if daily_exits or rolling30_exit else "MONITOR",
            "basis": f"daily_exit_rows={len(daily_exits)}; rolling30_exit_rows={len(rolling30_exit)}",
        },
    ]
    lines = ["## 10. Action summary"]
    lines.extend(render_table(rows, ["area", "label", "basis"]))
    lines.append("Labels are deterministic report-derived states, not buy/sell recommendations.")
    lines.append("")
    return lines


def _read_report(path: Path) -> MarkdownReport:
    if not path.exists():
        raise DecisionSummaryError(f"Input file not found: {path}")
    if not path.is_file():
        raise DecisionSummaryError(f"Input path is not a file: {path}")
    return MarkdownReport(path=path, text=path.read_text(encoding="utf-8"))


def _is_table_header(header: str, separator: str) -> bool:
    return header.lstrip().startswith("|") and bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", separator))


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def _clean_cell(value: str) -> str:
    return value.strip().replace("\\|", "|")


def _format_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _aliases(field: str) -> list[str]:
    norm = normalize_key(field)
    aliases = [norm]
    if norm.endswith("_end_date"):
        aliases.append(norm[: -len("_end_date")])
    aliases.append(f"last_{norm}")
    aliases.append(f"current_{norm}")
    aliases.append(f"latest_{norm}")
    return list(dict.fromkeys(aliases))


def _watchlist_sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    status = value_for(row, "watchlist_status")
    priority = STATUS_PRIORITY.get(status, -1)
    breakout = 1 if _truthy(value_for(row, "breakout_signal")) else 0
    return (-priority, -breakout, value_for(row, "ticker"))


def _truthy(value: str) -> bool:
    return value.strip().upper() in {"1", "TRUE", "YES", "Y"}


def _to_number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(previous: str, current: str) -> str:
    prev_num = _to_number(previous)
    curr_num = _to_number(current)
    if prev_num is not None and curr_num is not None:
        delta = curr_num - prev_num
        if delta.is_integer():
            return str(int(delta))
        return f"{delta:.6g}"
    if previous == current:
        return "0"
    return f"{previous} -> {current}"


def _metric_row(rows: Sequence[dict[str, str]], metric: str) -> dict[str, str]:
    target = normalize_key(metric)
    for row in rows:
        if normalize_key(value_for(row, "metric")) == target:
            return row
    return {}


def _classify_numeric_change(value: str) -> str:
    num = _to_number(value)
    if num is None:
        return value or "UNKNOWN"
    if num > 0:
        return "IMPROVED"
    if num < 0:
        return "WEAKENED"
    return "UNCHANGED"


def _prefixed_fields(rows: Sequence[dict[str, str]], fields: Sequence[str], *, prefix: str) -> list[str]:
    if not rows:
        return [prefix + field for field in fields]
    sample_keys = set().union(*(row.keys() for row in rows))
    result = []
    for field in fields:
        prefixed = prefix + field
        result.append(prefixed if prefixed in sample_keys else field)
    return result


def _ticker_list(rows: Sequence[dict[str, str]], limit: int = 12) -> str:
    tickers = [value_for(row, "ticker") for row in rows if value_for(row, "ticker")]
    if not tickers:
        return "No rows."
    visible = tickers[:limit]
    suffix = f" (+{len(tickers) - limit} more)" if len(tickers) > limit else ""
    return ", ".join(visible) + suffix


if __name__ == "__main__":
    raise SystemExit(main())
