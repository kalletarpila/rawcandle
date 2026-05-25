from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot


SECTION_ORDER = [
    "source_reports",
    "action_summary",
    "market_map",
    "watchlist",
    "tickers",
    "decision_trace",
]


@dataclass(frozen=True)
class SectionCountRow:
    section_name: str
    left_count: int
    right_count: int
    delta_count: int
    status: str


@dataclass(frozen=True)
class SideSelection:
    dashboard_db: str
    run_id: str
    label: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only parity audit for two persisted ecosystem dashboard snapshots."
    )
    parser.add_argument("--left-dashboard-db", required=True)
    parser.add_argument("--left-run-id", required=True)
    parser.add_argument("--right-dashboard-db", required=True)
    parser.add_argument("--right-run-id", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--left-label", default="reports")
    parser.add_argument("--right-label", default="structured")
    parser.add_argument("--report-date")
    return parser


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _emit_section_marker(name: str) -> None:
    print(f"section;{name}")


def _emit_row(values: list[object]) -> None:
    print(";".join(_normalize_text(value) for value in values))


def _load_side_snapshot(selection: SideSelection, ecosystem_code: str, report_date: str | None):
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


def _section_rows(snapshot, section_name: str) -> list[dict[str, object]]:
    value = getattr(snapshot, section_name)
    return list(value)


def _source_report_key(row: dict[str, object]) -> str:
    path_value = row.get("markdown_path") or row.get("csv_path") or ""
    return "|".join(
        [
            _normalize_text(row.get("report_kind")),
            _normalize_text(row.get("horizon")),
            _normalize_text(path_value),
        ]
    )


def _action_summary_key(row: dict[str, object]) -> str:
    action_value = row.get("action")
    return _normalize_text(action_value)


def _market_map_key(row: dict[str, object]) -> str:
    layer_name = row.get("layer")
    subindustry_name = row.get("subindustry")
    if layer_name or subindustry_name:
        return "|".join([_normalize_text(layer_name), _normalize_text(subindustry_name)])
    return "|".join(
        [
            _normalize_text(row.get("market_level")),
            _normalize_text(row.get("name")),
            _normalize_text(row.get("parent_name")),
            _normalize_text(row.get("taxonomy_path")),
        ]
    )


def _ticker_key(row: dict[str, object]) -> str:
    return _normalize_text(row.get("ticker"))


def _decision_trace_key(row: dict[str, object]) -> str:
    trace_index = row.get("trace_index")
    rule_name = row.get("matched_rule")
    return "|".join(
        [
            _normalize_text(row.get("ticker")),
            _normalize_text(trace_index),
            _normalize_text(rule_name),
        ]
    )


def _key_func(section_name: str):
    if section_name == "source_reports":
        return _source_report_key
    if section_name == "action_summary":
        return _action_summary_key
    if section_name == "market_map":
        return _market_map_key
    if section_name in {"watchlist", "tickers"}:
        return _ticker_key
    if section_name == "decision_trace":
        return _decision_trace_key
    raise ValueError(f"unsupported section: {section_name}")


def _map_by_key(section_name: str, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    key_func = _key_func(section_name)
    return {key_func(row): row for row in rows}


def _value_for_output(value: object) -> str:
    return "" if value is None else str(value)


def _field_pairs(section_name: str) -> list[tuple[str, str]]:
    if section_name == "watchlist":
        return [
            ("action", "action"),
            ("primary_reason", "primary_reason"),
            ("current_status", "current_status"),
        ]
    if section_name == "tickers":
        return [
            ("action", "action"),
            ("current_status", "current_status"),
            ("trend_state", "trend_state"),
            ("latest_structure_label", "latest_structure_label"),
            ("latest_bos_event_type", "latest_bos_event_type"),
            ("latest_reset_reason", "latest_reset_reason"),
        ]
    if section_name == "action_summary":
        return [("count", "count")]
    return []


def _compare_field_differences(
    section_name: str,
    left_rows: dict[str, dict[str, object]],
    right_rows: dict[str, dict[str, object]],
) -> list[list[object]]:
    shared_keys = sorted(set(left_rows) & set(right_rows))
    field_differences: list[list[object]] = []
    for key in shared_keys:
        left_row = left_rows[key]
        right_row = right_rows[key]
        for field_name, output_name in _field_pairs(section_name):
            left_value = left_row.get(field_name)
            right_value = right_row.get(field_name)
            if left_value != right_value:
                field_differences.append(
                    [
                        section_name,
                        key,
                        output_name,
                        _value_for_output(left_value),
                        _value_for_output(right_value),
                    ]
                )
    return field_differences


def _compare_key_differences(
    section_name: str,
    left_rows: dict[str, dict[str, object]],
    right_rows: dict[str, dict[str, object]],
) -> list[list[object]]:
    left_only = sorted(set(left_rows) - set(right_rows))
    right_only = sorted(set(right_rows) - set(left_rows))
    rows: list[list[object]] = []
    for key in left_only:
        rows.append([section_name, "ONLY_LEFT", key])
    for key in right_only:
        rows.append([section_name, "ONLY_RIGHT", key])
    return rows


def _build_section_counts(left_snapshot, right_snapshot) -> list[SectionCountRow]:
    rows: list[SectionCountRow] = []
    for section_name in SECTION_ORDER:
        left_count = len(_section_rows(left_snapshot, section_name))
        right_count = len(_section_rows(right_snapshot, section_name))
        delta_count = right_count - left_count
        rows.append(
            SectionCountRow(
                section_name=section_name,
                left_count=left_count,
                right_count=right_count,
                delta_count=delta_count,
                status="MATCH" if delta_count == 0 else "DIFF",
            )
        )
    return rows


def _run_summary_rows(left_snapshot, right_snapshot, left_selection: SideSelection, right_selection: SideSelection) -> list[list[object]]:
    return [
        [
            "left",
            left_selection.label,
            left_selection.dashboard_db,
            left_snapshot.run.ecosystem_code,
            left_snapshot.run.report_date,
            left_snapshot.run.run_id,
            left_snapshot.run.status or "",
            left_snapshot.run.created_at_utc or "",
        ],
        [
            "right",
            right_selection.label,
            right_selection.dashboard_db,
            right_snapshot.run.ecosystem_code,
            right_snapshot.run.report_date,
            right_snapshot.run.run_id,
            right_snapshot.run.status or "",
            right_snapshot.run.created_at_utc or "",
        ],
    ]


def _summary_lines(
    *,
    ecosystem_code: str,
    report_date: str | None,
    left_selection: SideSelection,
    right_selection: SideSelection,
    section_counts: list[SectionCountRow],
    key_difference_count: int,
    field_difference_count: int,
) -> list[str]:
    sections_with_count_diff = sum(1 for row in section_counts if row.status == "DIFF")
    return [
        f"SUMMARY ecosystem_dashboard_parity_audit.ecosystem_code={ecosystem_code}",
        f"SUMMARY ecosystem_dashboard_parity_audit.report_date={report_date or ''}",
        f"SUMMARY ecosystem_dashboard_parity_audit.left_label={left_selection.label}",
        f"SUMMARY ecosystem_dashboard_parity_audit.right_label={right_selection.label}",
        f"SUMMARY ecosystem_dashboard_parity_audit.left_run_id={left_selection.run_id}",
        f"SUMMARY ecosystem_dashboard_parity_audit.right_run_id={right_selection.run_id}",
        f"SUMMARY ecosystem_dashboard_parity_audit.sections_compared={len(SECTION_ORDER)}",
        f"SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff={sections_with_count_diff}",
        f"SUMMARY ecosystem_dashboard_parity_audit.key_differences={key_difference_count}",
        f"SUMMARY ecosystem_dashboard_parity_audit.field_differences={field_difference_count}",
        "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
    ]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
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

    section_counts = _build_section_counts(left_snapshot, right_snapshot)
    key_difference_rows: list[list[object]] = []
    field_difference_rows: list[list[object]] = []
    for section_name in SECTION_ORDER:
        left_rows = _map_by_key(section_name, _section_rows(left_snapshot, section_name))
        right_rows = _map_by_key(section_name, _section_rows(right_snapshot, section_name))
        key_difference_rows.extend(
            _compare_key_differences(section_name, left_rows, right_rows)
        )
        field_difference_rows.extend(
            _compare_field_differences(section_name, left_rows, right_rows)
        )

    _emit_section_marker("run_summary")
    _emit_row(
        [
            "run_summary",
            "side",
            "label",
            "dashboard_db",
            "ecosystem_code",
            "report_date",
            "run_id",
            "readiness",
            "created_at_utc",
        ]
    )
    for row in _run_summary_rows(left_snapshot, right_snapshot, left_selection, right_selection):
        _emit_row(["run_summary", *row])

    _emit_section_marker("section_counts")
    _emit_row(
        [
            "section_counts",
            "section_name",
            "left_count",
            "right_count",
            "delta_count",
            "status",
        ]
    )
    for row in section_counts:
        _emit_row(
            [
                "section_counts",
                row.section_name,
                row.left_count,
                row.right_count,
                row.delta_count,
                row.status,
            ]
        )

    _emit_section_marker("key_differences")
    _emit_row(["key_differences", "section_name", "diff_type", "key"])
    for row in key_difference_rows:
        _emit_row(["key_differences", *row])

    _emit_section_marker("field_differences")
    _emit_row(
        [
            "field_differences",
            "section_name",
            "key",
            "field_name",
            "left_value",
            "right_value",
        ]
    )
    for row in field_difference_rows:
        _emit_row(["field_differences", *row])

    _emit_section_marker("summary")
    for line in _summary_lines(
        ecosystem_code=args.ecosystem_code,
        report_date=args.report_date,
        left_selection=left_selection,
        right_selection=right_selection,
        section_counts=section_counts,
        key_difference_count=len(key_difference_rows),
        field_difference_count=len(field_difference_rows),
    ):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())