from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


OVERVIEW_SECTION_ORDER = ["market_map", "watchlist", "tickers", "decision_trace"]
TICKER_COMPARE_FIELDS = [
    "action",
    "severity",
    "primary_reason",
    "current_status",
    "trend_state",
    "latest_structure_label",
    "latest_bos_event_type",
    "latest_reset_reason",
    "daily_status",
    "rolling_2d_status",
    "rolling_5d_status",
    "rolling_30d_status",
    "horizons_present",
    "is_watchlist",
]


@dataclass(frozen=True)
class SideSelection:
    dashboard_db: str
    run_id: str
    label: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only explanation audit for parity differences between two persisted ecosystem dashboard snapshots."
    )
    parser.add_argument("--left-dashboard-db", required=True)
    parser.add_argument("--left-run-id", required=True)
    parser.add_argument("--right-dashboard-db", required=True)
    parser.add_argument("--right-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--report-date")
    parser.add_argument("--left-label", default="reports")
    parser.add_argument("--right-label", default="structured")
    parser.add_argument("--max-examples", type=int, default=50)
    return parser


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _emit_section_marker(name: str) -> None:
    print(f"section;{name}")


def _emit_row(values: list[object]) -> None:
    print(";".join(_normalize_text(value) for value in values))


def _load_side_snapshot(
    selection: SideSelection,
    ecosystem_code: str,
    report_date: str | None,
):
    snapshot = load_dashboard_snapshot(
        dashboard_db=selection.dashboard_db,
        ecosystem_code=ecosystem_code,
        run_id=selection.run_id,
    )
    if report_date is not None and snapshot.run.report_date != report_date:
        raise ValueError(
            "report_date mismatch for "
            f"{selection.label}: run_id={selection.run_id} has report_date={snapshot.run.report_date}, expected {report_date}"
        )
    return snapshot


def _ticker_key(row: dict[str, object]) -> str:
    return _normalize_text(row.get("ticker"))


def _market_map_key(row: dict[str, object]) -> str:
    taxonomy_path = row.get("taxonomy_path")
    if taxonomy_path not in (None, ""):
        return _normalize_text(taxonomy_path)
    return "|".join(
        [
            _normalize_text(row.get("market_level")),
            _normalize_text(row.get("name")),
            _normalize_text(row.get("parent_name")),
            _normalize_text(row.get("layer")),
            _normalize_text(row.get("subindustry")),
        ]
    )


def _decision_trace_key(row: dict[str, object]) -> str:
    trace_index = row.get("trace_index")
    parts = [_normalize_text(row.get("ticker"))]
    if trace_index not in (None, ""):
        parts.append(_normalize_text(trace_index))
    parts.extend(
        [
            _normalize_text(row.get("matched_rule")),
            _normalize_text(row.get("matched_token")),
            _normalize_text(row.get("field")),
            _normalize_text(row.get("horizon")),
        ]
    )
    return "|".join(parts)


def _section_rows(snapshot, section_name: str) -> list[dict[str, object]]:
    return list(getattr(snapshot, section_name))


def _map_by_key(rows: list[dict[str, object]], key_func) -> dict[str, dict[str, object]]:
    return {key_func(row): row for row in rows}


def _limited_rows(rows: list[list[object]], max_examples: int) -> list[list[object]]:
    return rows[:max_examples]


def _value_text(row: dict[str, object], field_name: str) -> str:
    return _normalize_text(row.get(field_name))


def _sorted_counter_text(counter: Counter[str]) -> str:
    if not counter:
        return ""
    best_value, best_count = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
    return f"{best_value}:{best_count}"


def _parse_horizons(value: object) -> list[str]:
    if value in (None, ""):
        return []
    parts = [part.strip() for part in str(value).split(",")]
    return sorted(part for part in parts if part)


def _ratio_text(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0000"
    return f"{numerator / denominator:.4f}"


def _run_summary_rows(
    left_snapshot,
    right_snapshot,
    left_selection: SideSelection,
    right_selection: SideSelection,
) -> list[list[object]]:
    return [
        [
            "left",
            left_selection.label,
            left_selection.dashboard_db,
            left_snapshot.run.ecosystem_code,
            left_snapshot.run.report_date,
            left_snapshot.run.run_id,
        ],
        [
            "right",
            right_selection.label,
            right_selection.dashboard_db,
            right_snapshot.run.ecosystem_code,
            right_snapshot.run.report_date,
            right_snapshot.run.run_id,
        ],
    ]


def _difference_overview_rows(left_snapshot, right_snapshot) -> tuple[list[list[object]], dict[str, dict[str, int]], dict[str, set[str]]]:
    rows: list[list[object]] = []
    counts: dict[str, dict[str, int]] = {}
    common_keys: dict[str, set[str]] = {}
    section_key_funcs = {
        "market_map": _market_map_key,
        "watchlist": _ticker_key,
        "tickers": _ticker_key,
        "decision_trace": _decision_trace_key,
    }
    for section_name in OVERVIEW_SECTION_ORDER:
        key_func = section_key_funcs[section_name]
        left_keys = set(_map_by_key(_section_rows(left_snapshot, section_name), key_func))
        right_keys = set(_map_by_key(_section_rows(right_snapshot, section_name), key_func))
        only_left = left_keys - right_keys
        only_right = right_keys - left_keys
        common = left_keys & right_keys
        counts[section_name] = {
            "left_count": len(left_keys),
            "right_count": len(right_keys),
            "delta_count": len(right_keys) - len(left_keys),
            "only_left_count": len(only_left),
            "only_right_count": len(only_right),
            "common_count": len(common),
        }
        common_keys[section_name] = common
        rows.append(
            [
                section_name,
                len(left_keys),
                len(right_keys),
                len(right_keys) - len(left_keys),
                len(only_left),
                len(only_right),
                len(common),
            ]
        )
    return rows, counts, common_keys


def _ticker_detail_rows(rows_by_ticker: dict[str, dict[str, object]], keys: list[str], prefix: str) -> list[list[object]]:
    rows: list[list[object]] = []
    for ticker in sorted(keys):
        row = rows_by_ticker[ticker]
        rows.append(
            [
                prefix,
                ticker,
                row.get("action"),
                row.get("current_status"),
                row.get("trend_state"),
                row.get("latest_structure_label"),
                row.get("latest_bos_event_type"),
                row.get("latest_reset_reason"),
                row.get("horizons_present"),
                row.get("is_watchlist"),
            ]
        )
    return rows


def _ticker_field_diff_summary_rows(
    left_rows: dict[str, dict[str, object]],
    right_rows: dict[str, dict[str, object]],
    common_tickers: set[str],
) -> tuple[list[list[object]], int]:
    rows: list[list[object]] = []
    total_differences = 0
    for field_name in sorted(TICKER_COMPARE_FIELDS):
        differing_tickers = []
        for ticker in sorted(common_tickers):
            left_value = left_rows[ticker].get(field_name)
            right_value = right_rows[ticker].get(field_name)
            if left_value != right_value:
                differing_tickers.append(
                    (
                        ticker,
                        _normalize_text(left_value),
                        _normalize_text(right_value),
                    )
                )
        total_differences += len(differing_tickers)
        if differing_tickers:
            example_ticker, left_value, right_value = differing_tickers[0]
        else:
            example_ticker = ""
            left_value = ""
            right_value = ""
        rows.append(
            [
                field_name,
                len(differing_tickers),
                example_ticker,
                left_value,
                right_value,
            ]
        )
    return rows, total_differences


def _market_map_detail_rows(rows_by_key: dict[str, dict[str, object]], keys: list[str], prefix: str) -> list[list[object]]:
    rows: list[list[object]] = []
    for key in sorted(keys):
        row = rows_by_key[key]
        rows.append(
            [
                prefix,
                key,
                row.get("market_level"),
                row.get("name"),
                row.get("parent_name"),
                row.get("layer"),
                row.get("subindustry"),
                row.get("current_status"),
                row.get("source_horizons"),
            ]
        )
    return rows


def _decision_trace_summary_rows(rows_by_key: dict[str, dict[str, object]], keys: list[str], prefix: str) -> list[list[object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for key in keys:
        row = rows_by_key[key]
        grouped[_ticker_key(row)].append(row)
    ranked = sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    rows: list[list[object]] = []
    for ticker, ticker_rows in ranked:
        first_row = sorted(
            ticker_rows,
            key=lambda row: (
                _normalize_text(row.get("matched_rule")),
                _normalize_text(row.get("matched_token")),
                _normalize_text(row.get("field")),
                _normalize_text(row.get("horizon")),
                _normalize_text(row.get("trace_index")),
            ),
        )[0]
        rows.append(
            [
                prefix,
                ticker,
                len(ticker_rows),
                first_row.get("matched_rule"),
                first_row.get("matched_token"),
                first_row.get("field"),
                first_row.get("horizon"),
            ]
        )
    return rows


def _right_only_ticker_counters(rows_by_ticker: dict[str, dict[str, object]], keys: list[str]) -> tuple[int, Counter[str], Counter[str], Counter[str]]:
    non_watchlist_count = 0
    action_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    horizon_counter: Counter[str] = Counter()
    for ticker in keys:
        row = rows_by_ticker[ticker]
        if row.get("is_watchlist") not in (1, "1", True):
            non_watchlist_count += 1
        action_counter[_normalize_text(row.get("action"))] += 1
        status_counter[_normalize_text(row.get("current_status"))] += 1
        for horizon in _parse_horizons(row.get("horizons_present")):
            horizon_counter[horizon] += 1
    return non_watchlist_count, action_counter, status_counter, horizon_counter


def _hypothesis_rows(
    *,
    overview_counts: dict[str, dict[str, int]],
    ticker_only_left_keys: list[str],
    ticker_only_right_keys: list[str],
    watchlist_only_left_keys: list[str],
    watchlist_only_right_keys: list[str],
    decision_trace_only_right_keys: list[str],
    decision_trace_only_right_rows: dict[str, dict[str, object]],
    market_map_only_left_keys: list[str],
    market_map_only_right_keys: list[str],
    common_ticker_field_differences: int,
    right_ticker_rows: dict[str, dict[str, object]],
) -> list[list[object]]:
    right_only_trace_tickers = {
        _ticker_key(decision_trace_only_right_rows[key]) for key in decision_trace_only_right_keys
    }
    right_only_ticker_set = set(ticker_only_right_keys)
    overlap_count = len(right_only_trace_tickers & right_only_ticker_set)
    overlap_ratio = (
        overlap_count / len(right_only_trace_tickers)
        if right_only_trace_tickers
        else 0.0
    )
    non_watchlist_count, action_counter, status_counter, horizon_counter = _right_only_ticker_counters(
        right_ticker_rows,
        ticker_only_right_keys,
    )
    return [
        [
            "BROADER_TICKER_UNIVERSE_IN_RIGHT",
            "LIKELY"
            if ticker_only_right_keys
            and overview_counts["tickers"]["right_count"] > overview_counts["tickers"]["left_count"]
            else "UNLIKELY",
            ";".join(
                [
                    f"right_only_tickers={len(ticker_only_right_keys)}",
                    f"left_tickers={overview_counts['tickers']['left_count']}",
                    f"right_tickers={overview_counts['tickers']['right_count']}",
                    f"right_only_non_watchlist={non_watchlist_count}",
                    f"dominant_action={_sorted_counter_text(action_counter)}",
                    f"dominant_status={_sorted_counter_text(status_counter)}",
                    f"dominant_horizon={_sorted_counter_text(horizon_counter)}",
                ]
            ),
        ],
        [
            "WATCHLIST_PARITY_OK",
            "LIKELY"
            if overview_counts["watchlist"]["left_count"] == overview_counts["watchlist"]["right_count"]
            and len(watchlist_only_left_keys) + len(watchlist_only_right_keys) == 0
            else "UNLIKELY",
            ";".join(
                [
                    f"left_watchlist={overview_counts['watchlist']['left_count']}",
                    f"right_watchlist={overview_counts['watchlist']['right_count']}",
                    f"watchlist_key_diff={len(watchlist_only_left_keys) + len(watchlist_only_right_keys)}",
                ]
            ),
        ],
        [
            "EXTRA_RIGHT_DECISION_TRACE_FROM_EXTRA_TICKERS",
            "LIKELY" if overlap_ratio >= 0.75 else "UNLIKELY",
            ";".join(
                [
                    f"right_only_trace_tickers={len(right_only_trace_tickers)}",
                    f"overlap_with_right_only_tickers={overlap_count}",
                    f"overlap_ratio={overlap_ratio:.4f}",
                ]
            ),
        ],
        [
            "MARKET_MAP_SCOPE_DIFF",
            "LIKELY" if market_map_only_left_keys or market_map_only_right_keys else "UNLIKELY",
            ";".join(
                [
                    f"market_map_only_left={len(market_map_only_left_keys)}",
                    f"market_map_only_right={len(market_map_only_right_keys)}",
                ]
            ),
        ],
        [
            "COMMON_TICKER_FIELD_DRIFT",
            "LIKELY" if common_ticker_field_differences > 0 else "UNLIKELY",
            f"common_ticker_field_differences={common_ticker_field_differences}",
        ],
    ]


def _summary_lines(
    *,
    ecosystem_code: str,
    report_date: str | None,
    left_selection: SideSelection,
    right_selection: SideSelection,
    ticker_only_left_count: int,
    ticker_only_right_count: int,
    market_map_only_left_count: int,
    market_map_only_right_count: int,
    decision_trace_only_left_count: int,
    decision_trace_only_right_count: int,
    common_ticker_field_differences: int,
) -> list[str]:
    return [
        f"SUMMARY ecosystem_dashboard_parity_explain.ecosystem_code={ecosystem_code}",
        f"SUMMARY ecosystem_dashboard_parity_explain.report_date={report_date or ''}",
        f"SUMMARY ecosystem_dashboard_parity_explain.left_label={left_selection.label}",
        f"SUMMARY ecosystem_dashboard_parity_explain.right_label={right_selection.label}",
        f"SUMMARY ecosystem_dashboard_parity_explain.left_run_id={left_selection.run_id}",
        f"SUMMARY ecosystem_dashboard_parity_explain.right_run_id={right_selection.run_id}",
        f"SUMMARY ecosystem_dashboard_parity_explain.ticker_only_left={ticker_only_left_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.ticker_only_right={ticker_only_right_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.market_map_only_left={market_map_only_left_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.market_map_only_right={market_map_only_right_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.decision_trace_only_left={decision_trace_only_left_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.decision_trace_only_right={decision_trace_only_right_count}",
        f"SUMMARY ecosystem_dashboard_parity_explain.common_ticker_field_differences={common_ticker_field_differences}",
        "SUMMARY ecosystem_dashboard_parity_explain.status=OK",
    ]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.max_examples <= 0:
        print("ERROR: --max-examples must be greater than 0", file=sys.stderr)
        return 1
    left_selection = SideSelection(
        dashboard_db=str(Path(args.left_dashboard_db)),
        run_id=args.left_run_id,
        label=args.left_label,
    )
    right_selection = SideSelection(
        dashboard_db=str(Path(args.right_dashboard_db)),
        run_id=args.right_run_id,
        label=args.right_label,
    )
    try:
        left_snapshot = _load_side_snapshot(
            left_selection,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
        )
        right_snapshot = _load_side_snapshot(
            right_selection,
            ecosystem_code=args.ecosystem_code,
            report_date=args.report_date,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    left_watchlist_rows = _map_by_key(_section_rows(left_snapshot, "watchlist"), _ticker_key)
    right_watchlist_rows = _map_by_key(_section_rows(right_snapshot, "watchlist"), _ticker_key)
    left_ticker_rows = _map_by_key(_section_rows(left_snapshot, "tickers"), _ticker_key)
    right_ticker_rows = _map_by_key(_section_rows(right_snapshot, "tickers"), _ticker_key)
    left_market_map_rows = _map_by_key(_section_rows(left_snapshot, "market_map"), _market_map_key)
    right_market_map_rows = _map_by_key(_section_rows(right_snapshot, "market_map"), _market_map_key)
    left_trace_rows = _map_by_key(_section_rows(left_snapshot, "decision_trace"), _decision_trace_key)
    right_trace_rows = _map_by_key(_section_rows(right_snapshot, "decision_trace"), _decision_trace_key)

    overview_rows, overview_counts, common_keys = _difference_overview_rows(left_snapshot, right_snapshot)

    watchlist_only_left_keys = sorted(set(left_watchlist_rows) - set(right_watchlist_rows))
    watchlist_only_right_keys = sorted(set(right_watchlist_rows) - set(left_watchlist_rows))
    ticker_only_left_keys = sorted(set(left_ticker_rows) - set(right_ticker_rows))
    ticker_only_right_keys = sorted(set(right_ticker_rows) - set(left_ticker_rows))
    market_map_only_left_keys = sorted(set(left_market_map_rows) - set(right_market_map_rows))
    market_map_only_right_keys = sorted(set(right_market_map_rows) - set(left_market_map_rows))
    decision_trace_only_left_keys = sorted(set(left_trace_rows) - set(right_trace_rows))
    decision_trace_only_right_keys = sorted(set(right_trace_rows) - set(left_trace_rows))

    ticker_field_diff_rows, common_ticker_field_differences = _ticker_field_diff_summary_rows(
        left_ticker_rows,
        right_ticker_rows,
        common_keys["tickers"],
    )
    hypothesis_rows = _hypothesis_rows(
        overview_counts=overview_counts,
        ticker_only_left_keys=ticker_only_left_keys,
        ticker_only_right_keys=ticker_only_right_keys,
        watchlist_only_left_keys=watchlist_only_left_keys,
        watchlist_only_right_keys=watchlist_only_right_keys,
        decision_trace_only_right_keys=decision_trace_only_right_keys,
        decision_trace_only_right_rows=right_trace_rows,
        market_map_only_left_keys=market_map_only_left_keys,
        market_map_only_right_keys=market_map_only_right_keys,
        common_ticker_field_differences=common_ticker_field_differences,
        right_ticker_rows=right_ticker_rows,
    )

    _emit_section_marker("run_summary")
    _emit_row(["run_summary", "side", "label", "dashboard_db", "ecosystem_code", "report_date", "run_id"])
    for row in _run_summary_rows(left_snapshot, right_snapshot, left_selection, right_selection):
        _emit_row(["run_summary", *row])

    _emit_section_marker("difference_overview")
    _emit_row([
        "difference_overview",
        "section_name",
        "left_count",
        "right_count",
        "delta_count",
        "only_left_count",
        "only_right_count",
        "common_count",
    ])
    for row in overview_rows:
        _emit_row(["difference_overview", *row])

    _emit_section_marker("ticker_only_left")
    _emit_row([
        "ticker_only_left",
        "ticker",
        "action",
        "current_status",
        "trend_state",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_reset_reason",
        "horizons_present",
        "is_watchlist",
    ])
    for row in _limited_rows(_ticker_detail_rows(left_ticker_rows, ticker_only_left_keys, "ticker_only_left"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("ticker_only_right")
    _emit_row([
        "ticker_only_right",
        "ticker",
        "action",
        "current_status",
        "trend_state",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_reset_reason",
        "horizons_present",
        "is_watchlist",
    ])
    for row in _limited_rows(_ticker_detail_rows(right_ticker_rows, ticker_only_right_keys, "ticker_only_right"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("ticker_common_field_diff_summary")
    _emit_row([
        "ticker_common_field_diff_summary",
        "field_name",
        "diff_count",
        "example_ticker",
        "left_value",
        "right_value",
    ])
    for row in ticker_field_diff_rows:
        _emit_row(["ticker_common_field_diff_summary", *row])

    _emit_section_marker("market_map_only_left")
    _emit_row([
        "market_map_only_left",
        "key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "current_status",
        "source_horizons",
    ])
    for row in _limited_rows(_market_map_detail_rows(left_market_map_rows, market_map_only_left_keys, "market_map_only_left"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("market_map_only_right")
    _emit_row([
        "market_map_only_right",
        "key",
        "market_level",
        "name",
        "parent_name",
        "layer",
        "subindustry",
        "current_status",
        "source_horizons",
    ])
    for row in _limited_rows(_market_map_detail_rows(right_market_map_rows, market_map_only_right_keys, "market_map_only_right"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("decision_trace_only_left_summary")
    _emit_row([
        "decision_trace_only_left_summary",
        "ticker",
        "count",
        "first_rule",
        "first_token",
        "first_field",
        "first_horizon",
    ])
    for row in _limited_rows(_decision_trace_summary_rows(left_trace_rows, decision_trace_only_left_keys, "decision_trace_only_left_summary"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("decision_trace_only_right_summary")
    _emit_row([
        "decision_trace_only_right_summary",
        "ticker",
        "count",
        "first_rule",
        "first_token",
        "first_field",
        "first_horizon",
    ])
    for row in _limited_rows(_decision_trace_summary_rows(right_trace_rows, decision_trace_only_right_keys, "decision_trace_only_right_summary"), args.max_examples):
        _emit_row(row)

    _emit_section_marker("hypothesis_summary")
    _emit_row(["hypothesis_summary", "hypothesis", "status", "evidence"])
    for row in hypothesis_rows:
        _emit_row(["hypothesis_summary", *row])

    _emit_section_marker("summary")
    for line in _summary_lines(
        ecosystem_code=args.ecosystem_code,
        report_date=args.report_date,
        left_selection=left_selection,
        right_selection=right_selection,
        ticker_only_left_count=len(ticker_only_left_keys),
        ticker_only_right_count=len(ticker_only_right_keys),
        market_map_only_left_count=len(market_map_only_left_keys),
        market_map_only_right_count=len(market_map_only_right_keys),
        decision_trace_only_left_count=len(decision_trace_only_left_keys),
        decision_trace_only_right_count=len(decision_trace_only_right_keys),
        common_ticker_field_differences=common_ticker_field_differences,
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())