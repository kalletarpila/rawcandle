from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


GROUP_TYPE_ORDER = {
    "ecosystem": 0,
    "layer": 1,
    "subindustry": 2,
}

REPORT_SUMMARY_ORDER = [
    "taxonomy_version",
    "as_of_date",
    "rows_read",
    "ecosystem_group_count",
    "layer_group_count",
    "subindustry_group_count",
    "non_ok_group_count",
    "top_n",
    "output_md",
    "output_csv",
    "report_status",
]


@dataclass(frozen=True)
class DatacenterReportRow:
    index_date: str
    taxonomy_version: str
    group_type: str
    group_name: str
    member_count: int
    eligible_count: int
    ma50_eligible_count: int
    ma200_eligible_count: int
    daily_return_equal: float | None
    median_return: float | None
    pct_positive: float | None
    pct_above_ma50: float | None
    pct_above_ma200: float | None
    index_level_equal: float | None
    return_20d: float | None
    return_60d: float | None
    return_120d: float | None
    volatility_20d: float | None
    volatility_60d: float | None
    relative_strength_spy_60d: float | None
    relative_strength_qqq_60d: float | None
    data_quality_status: str
    calc_version: str
    run_id: str
    created_at_utc: str


def _parse_iso_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid as_of_date: {value}") from exc


def _normalize_path(value: str | Path) -> Path:
    return Path(value)


def _sort_rows(rows: Sequence[DatacenterReportRow]) -> list[DatacenterReportRow]:
    return sorted(
        rows,
        key=lambda row: (GROUP_TYPE_ORDER[row.group_type], row.group_name),
    )


def load_datacenter_report_rows(
    analysis_db_path: str | Path,
    taxonomy_version: str,
    as_of_date: str,
) -> list[DatacenterReportRow]:
    normalized_as_of_date = _parse_iso_date(as_of_date)
    query = """
        SELECT
            index_date,
            taxonomy_version,
            group_type,
            group_name,
            member_count,
            eligible_count,
            ma50_eligible_count,
            ma200_eligible_count,
            daily_return_equal,
            median_return,
            pct_positive,
            pct_above_ma50,
            pct_above_ma200,
            index_level_equal,
            return_20d,
            return_60d,
            return_120d,
            volatility_20d,
            volatility_60d,
            relative_strength_spy_60d,
            relative_strength_qqq_60d,
            data_quality_status,
            calc_version,
            run_id,
            created_at_utc
        FROM dc_group_index_daily
        WHERE taxonomy_version = ?
          AND index_date = ?
        ORDER BY group_type, group_name
    """
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        db_rows = conn.execute(query, (taxonomy_version, normalized_as_of_date)).fetchall()

    if not db_rows:
        raise ValueError(
            f"No dc_group_index_daily rows found for taxonomy_version '{taxonomy_version}' "
            f"on as_of_date '{normalized_as_of_date}'"
        )

    rows = [
        DatacenterReportRow(
            index_date=str(row["index_date"]),
            taxonomy_version=str(row["taxonomy_version"]),
            group_type=str(row["group_type"]),
            group_name=str(row["group_name"]),
            member_count=int(row["member_count"]),
            eligible_count=int(row["eligible_count"]),
            ma50_eligible_count=int(row["ma50_eligible_count"]),
            ma200_eligible_count=int(row["ma200_eligible_count"]),
            daily_return_equal=row["daily_return_equal"],
            median_return=row["median_return"],
            pct_positive=row["pct_positive"],
            pct_above_ma50=row["pct_above_ma50"],
            pct_above_ma200=row["pct_above_ma200"],
            index_level_equal=row["index_level_equal"],
            return_20d=row["return_20d"],
            return_60d=row["return_60d"],
            return_120d=row["return_120d"],
            volatility_20d=row["volatility_20d"],
            volatility_60d=row["volatility_60d"],
            relative_strength_spy_60d=row["relative_strength_spy_60d"],
            relative_strength_qqq_60d=row["relative_strength_qqq_60d"],
            data_quality_status=str(row["data_quality_status"]),
            calc_version=str(row["calc_version"]),
            run_id=str(row["run_id"]),
            created_at_utc=str(row["created_at_utc"]),
        )
        for row in db_rows
    ]
    return _sort_rows(rows)


def _filter_group_type(rows: Sequence[DatacenterReportRow], group_type: str) -> list[DatacenterReportRow]:
    return [row for row in rows if row.group_type == group_type]


def _distinct_sorted(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def _metric_value_rows(rows: Sequence[tuple[str, str]]) -> str:
    lines = ["| Metric | Value |", "| --- | --- |"]
    for metric, value in rows:
        lines.append(f"| {metric} | {value} |")
    return "\n".join(lines)


def _format_markdown_percent(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value * 100.0:.2f}%"


def _format_markdown_percent_points(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}%"


def _format_markdown_index(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}"


def _format_markdown_volatility(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.4f}"


def _table_markdown(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _sort_by_metric_desc(rows: Sequence[DatacenterReportRow], metric_name: str) -> list[DatacenterReportRow]:
    with_value = [row for row in rows if getattr(row, metric_name) is not None]
    without_value = [row for row in rows if getattr(row, metric_name) is None]
    return sorted(with_value, key=lambda row: (-getattr(row, metric_name), row.group_name)) + sorted(
        without_value,
        key=lambda row: row.group_name,
    )


def _sort_by_metric_asc(rows: Sequence[DatacenterReportRow], metric_name: str) -> list[DatacenterReportRow]:
    with_value = [row for row in rows if getattr(row, metric_name) is not None]
    without_value = [row for row in rows if getattr(row, metric_name) is None]
    return sorted(with_value, key=lambda row: (getattr(row, metric_name), row.group_name)) + sorted(
        without_value,
        key=lambda row: row.group_name,
    )


def _top_n(rows: Sequence[DatacenterReportRow], metric_name: str, top_n: int, *, reverse: bool) -> list[DatacenterReportRow]:
    eligible = [row for row in rows if getattr(row, metric_name) is not None]
    if reverse:
        sorted_rows = sorted(eligible, key=lambda row: (-getattr(row, metric_name), row.group_name))
    else:
        sorted_rows = sorted(eligible, key=lambda row: (getattr(row, metric_name), row.group_name))
    return sorted_rows[:top_n]


def _average(values: Iterable[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _render_performance_rows_markdown(rows: Sequence[DatacenterReportRow]) -> str:
    headers = [
        "Group",
        "Members",
        "Eligible",
        "Index level",
        "Return 20d",
        "Return 60d",
        "Return 120d",
        "Pct above MA50",
        "Pct above MA200",
        "RS vs SPY 60d",
        "RS vs QQQ 60d",
        "Data quality",
    ]
    table_rows = [
        [
            row.group_name,
            str(row.member_count),
            str(row.eligible_count),
            _format_markdown_index(row.index_level_equal),
            _format_markdown_percent(row.return_20d),
            _format_markdown_percent(row.return_60d),
            _format_markdown_percent(row.return_120d),
            _format_markdown_percent_points(row.pct_above_ma50),
            _format_markdown_percent_points(row.pct_above_ma200),
            _format_markdown_percent(row.relative_strength_spy_60d),
            _format_markdown_percent(row.relative_strength_qqq_60d),
            row.data_quality_status,
        ]
        for row in rows
    ]
    return _table_markdown(headers, table_rows)


def _render_breadth_rows_markdown(rows: Sequence[DatacenterReportRow]) -> str:
    headers = [
        "Group",
        "Pct positive",
        "Pct above MA50",
        "Pct above MA200",
        "Data quality",
    ]
    table_rows = [
        [
            row.group_name,
            _format_markdown_percent_points(row.pct_positive),
            _format_markdown_percent_points(row.pct_above_ma50),
            _format_markdown_percent_points(row.pct_above_ma200),
            row.data_quality_status,
        ]
        for row in rows
    ]
    return _table_markdown(headers, table_rows)


def build_markdown_report(
    rows: Sequence[DatacenterReportRow],
    *,
    taxonomy_version: str,
    as_of_date: str,
    top_n: int,
) -> str:
    sorted_rows = _sort_rows(rows)
    ecosystem_rows = _filter_group_type(sorted_rows, "ecosystem")
    layer_rows = _filter_group_type(sorted_rows, "layer")
    subindustry_rows = _filter_group_type(sorted_rows, "subindustry")
    non_ok_rows = [row for row in sorted_rows if row.data_quality_status != "OK"]

    best_layer = _top_n(layer_rows, "return_60d", 1, reverse=True)
    worst_layer = _top_n(layer_rows, "return_60d", 1, reverse=False)
    best_subindustry = _top_n(subindustry_rows, "return_60d", 1, reverse=True)
    worst_subindustry = _top_n(subindustry_rows, "return_60d", 1, reverse=False)

    layer_rows_by_60d = _sort_by_metric_desc(layer_rows, "return_60d")
    subindustry_rows_by_60d = _sort_by_metric_desc(subindustry_rows, "return_60d")
    breadth_rows = _sort_by_metric_desc(layer_rows, "pct_above_ma50")

    sections = [
        "# Datacenter Ecosystem Index Report",
        "",
        "## 1. Metadata",
        _metric_value_rows(
            [
                ("taxonomy_version", taxonomy_version),
                ("as_of_date", as_of_date),
                ("row_count", str(len(sorted_rows))),
                ("ecosystem_group_count", str(len(ecosystem_rows))),
                ("layer_group_count", str(len(layer_rows))),
                ("subindustry_group_count", str(len(subindustry_rows))),
                ("calc_version_values", ", ".join(_distinct_sorted(row.calc_version for row in sorted_rows))),
                ("run_id_values", ", ".join(_distinct_sorted(row.run_id for row in sorted_rows))),
                ("created_at_utc_values", ", ".join(_distinct_sorted(row.created_at_utc for row in sorted_rows))),
            ]
        ),
        "",
        "## 2. Executive summary",
        _metric_value_rows(
            [
                (
                    "best_layer_by_return_60d",
                    best_layer[0].group_name if best_layer else "NA",
                ),
                (
                    "worst_layer_by_return_60d",
                    worst_layer[0].group_name if worst_layer else "NA",
                ),
                (
                    "best_subindustry_by_return_60d",
                    best_subindustry[0].group_name if best_subindustry else "NA",
                ),
                (
                    "worst_subindustry_by_return_60d",
                    worst_subindustry[0].group_name if worst_subindustry else "NA",
                ),
                ("non_ok_group_count", str(len(non_ok_rows))),
                (
                    "average_layer_pct_above_ma50",
                    _format_markdown_percent_points(_average(row.pct_above_ma50 for row in layer_rows)),
                ),
                (
                    "average_layer_pct_above_ma200",
                    _format_markdown_percent_points(_average(row.pct_above_ma200 for row in layer_rows)),
                ),
            ]
        ),
        "",
        "## 3. Ecosystem total",
        _table_markdown(
            [
                "Group",
                "Index level",
                "Daily return",
                "Return 20d",
                "Return 60d",
                "Return 120d",
                "Pct positive",
                "Pct above MA50",
                "Pct above MA200",
                "RS vs SPY 60d",
                "RS vs QQQ 60d",
                "Data quality",
            ],
            [
                [
                    row.group_name,
                    _format_markdown_index(row.index_level_equal),
                    _format_markdown_percent(row.daily_return_equal),
                    _format_markdown_percent(row.return_20d),
                    _format_markdown_percent(row.return_60d),
                    _format_markdown_percent(row.return_120d),
                    _format_markdown_percent_points(row.pct_positive),
                    _format_markdown_percent_points(row.pct_above_ma50),
                    _format_markdown_percent_points(row.pct_above_ma200),
                    _format_markdown_percent(row.relative_strength_spy_60d),
                    _format_markdown_percent(row.relative_strength_qqq_60d),
                    row.data_quality_status,
                ]
                for row in ecosystem_rows
            ],
        ),
        "",
        "## 4. Layer performance",
        _render_performance_rows_markdown(layer_rows_by_60d),
        "",
        "## 5. Subindustry performance",
        _render_performance_rows_markdown(subindustry_rows_by_60d),
        "",
        "## 6. Top subindustries by 60d return",
        _render_performance_rows_markdown(_top_n(subindustry_rows, "return_60d", top_n, reverse=True)),
        "",
        "## 7. Bottom subindustries by 60d return",
        _render_performance_rows_markdown(_top_n(subindustry_rows, "return_60d", top_n, reverse=False)),
        "",
        "## 8. Top subindustries by 60d relative strength vs SPY",
        _render_performance_rows_markdown(_top_n(subindustry_rows, "relative_strength_spy_60d", top_n, reverse=True)),
        "",
        "## 9. Bottom subindustries by 60d relative strength vs SPY",
        _render_performance_rows_markdown(_top_n(subindustry_rows, "relative_strength_spy_60d", top_n, reverse=False)),
        "",
        "## 10. Breadth summary",
        _render_breadth_rows_markdown(breadth_rows),
        "",
        "## 11. Data quality summary",
        _metric_value_rows(
            [
                ("OK", str(sum(1 for row in sorted_rows if row.data_quality_status == "OK"))),
                ("PARTIAL_DATA", str(sum(1 for row in sorted_rows if row.data_quality_status == "PARTIAL_DATA"))),
                ("TOO_SMALL", str(sum(1 for row in sorted_rows if row.data_quality_status == "TOO_SMALL"))),
                ("NO_DATA", str(sum(1 for row in sorted_rows if row.data_quality_status == "NO_DATA"))),
            ]
        ),
        "",
    ]

    if non_ok_rows:
        sections.extend(
            [
                _table_markdown(
                    ["Group type", "Group name", "Members", "Eligible", "Data quality"],
                    [
                        [
                            row.group_type,
                            row.group_name,
                            str(row.member_count),
                            str(row.eligible_count),
                            row.data_quality_status,
                        ]
                        for row in non_ok_rows
                    ],
                ),
                "",
            ]
        )
    else:
        sections.extend(["All groups have data_quality_status=OK.", ""])

    return "\n".join(sections).strip() + "\n"


def _csv_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def _write_csv_section_header(writer: csv.writer, header: Sequence[str]) -> None:
    writer.writerow(header)


def build_csv_report(
    rows: Sequence[DatacenterReportRow],
    *,
    taxonomy_version: str,
    as_of_date: str,
    top_n: int,
) -> str:
    sorted_rows = _sort_rows(rows)
    ecosystem_rows = _filter_group_type(sorted_rows, "ecosystem")
    layer_rows = _filter_group_type(sorted_rows, "layer")
    subindustry_rows = _filter_group_type(sorted_rows, "subindustry")
    non_ok_rows = [row for row in sorted_rows if row.data_quality_status != "OK"]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    _write_csv_section_header(writer, ["section", "metric", "value"])
    for metric, value in [
        ("taxonomy_version", taxonomy_version),
        ("as_of_date", as_of_date),
        ("row_count", len(sorted_rows)),
        ("ecosystem_group_count", len(ecosystem_rows)),
        ("layer_group_count", len(layer_rows)),
        ("subindustry_group_count", len(subindustry_rows)),
        ("calc_version_values", ",".join(_distinct_sorted(row.calc_version for row in sorted_rows))),
        ("run_id_values", ",".join(_distinct_sorted(row.run_id for row in sorted_rows))),
        ("created_at_utc_values", ",".join(_distinct_sorted(row.created_at_utc for row in sorted_rows))),
    ]:
        writer.writerow(["metadata", metric, value])

    _write_csv_section_header(writer, ["section", "metric", "value"])
    best_layer = _top_n(layer_rows, "return_60d", 1, reverse=True)
    worst_layer = _top_n(layer_rows, "return_60d", 1, reverse=False)
    best_subindustry = _top_n(subindustry_rows, "return_60d", 1, reverse=True)
    worst_subindustry = _top_n(subindustry_rows, "return_60d", 1, reverse=False)
    for metric, value in [
        ("best_layer_by_return_60d", best_layer[0].group_name if best_layer else ""),
        ("worst_layer_by_return_60d", worst_layer[0].group_name if worst_layer else ""),
        ("best_subindustry_by_return_60d", best_subindustry[0].group_name if best_subindustry else ""),
        ("worst_subindustry_by_return_60d", worst_subindustry[0].group_name if worst_subindustry else ""),
        ("non_ok_group_count", len(non_ok_rows)),
        ("average_layer_pct_above_ma50", _csv_value(_average(row.pct_above_ma50 for row in layer_rows))),
        ("average_layer_pct_above_ma200", _csv_value(_average(row.pct_above_ma200 for row in layer_rows))),
    ]:
        writer.writerow(["executive_summary", metric, value])

    def write_performance_section(section_name: str, section_rows: Sequence[DatacenterReportRow]) -> None:
        _write_csv_section_header(
            writer,
            [
                "section",
                "group_name",
                "member_count",
                "eligible_count",
                "index_level_equal",
                "return_20d",
                "return_60d",
                "return_120d",
                "pct_above_ma50",
                "pct_above_ma200",
                "relative_strength_spy_60d",
                "relative_strength_qqq_60d",
                "data_quality_status",
            ],
        )
        for row in section_rows:
            writer.writerow(
                [
                    section_name,
                    row.group_name,
                    row.member_count,
                    row.eligible_count,
                    _csv_value(row.index_level_equal),
                    _csv_value(row.return_20d),
                    _csv_value(row.return_60d),
                    _csv_value(row.return_120d),
                    _csv_value(row.pct_above_ma50),
                    _csv_value(row.pct_above_ma200),
                    _csv_value(row.relative_strength_spy_60d),
                    _csv_value(row.relative_strength_qqq_60d),
                    row.data_quality_status,
                ]
            )

    _write_csv_section_header(
        writer,
        [
            "section",
            "group_name",
            "index_level_equal",
            "daily_return_equal",
            "return_20d",
            "return_60d",
            "return_120d",
            "pct_positive",
            "pct_above_ma50",
            "pct_above_ma200",
            "relative_strength_spy_60d",
            "relative_strength_qqq_60d",
            "data_quality_status",
        ],
    )
    for row in ecosystem_rows:
        writer.writerow(
            [
                "ecosystem_total",
                row.group_name,
                _csv_value(row.index_level_equal),
                _csv_value(row.daily_return_equal),
                _csv_value(row.return_20d),
                _csv_value(row.return_60d),
                _csv_value(row.return_120d),
                _csv_value(row.pct_positive),
                _csv_value(row.pct_above_ma50),
                _csv_value(row.pct_above_ma200),
                _csv_value(row.relative_strength_spy_60d),
                _csv_value(row.relative_strength_qqq_60d),
                row.data_quality_status,
            ]
        )

    write_performance_section("layer_performance", _sort_by_metric_desc(layer_rows, "return_60d"))
    write_performance_section("subindustry_performance", _sort_by_metric_desc(subindustry_rows, "return_60d"))
    write_performance_section("top_subindustry_return_60d", _top_n(subindustry_rows, "return_60d", top_n, reverse=True))
    write_performance_section("bottom_subindustry_return_60d", _top_n(subindustry_rows, "return_60d", top_n, reverse=False))
    write_performance_section("top_subindustry_rs_spy_60d", _top_n(subindustry_rows, "relative_strength_spy_60d", top_n, reverse=True))
    write_performance_section("bottom_subindustry_rs_spy_60d", _top_n(subindustry_rows, "relative_strength_spy_60d", top_n, reverse=False))

    _write_csv_section_header(
        writer,
        [
            "section",
            "group_name",
            "pct_positive",
            "pct_above_ma50",
            "pct_above_ma200",
            "data_quality_status",
        ],
    )
    for row in _sort_by_metric_desc(layer_rows, "pct_above_ma50"):
        writer.writerow(
            [
                "breadth_summary",
                row.group_name,
                _csv_value(row.pct_positive),
                _csv_value(row.pct_above_ma50),
                _csv_value(row.pct_above_ma200),
                row.data_quality_status,
            ]
        )

    _write_csv_section_header(writer, ["section", "metric", "value"])
    for metric, value in [
        ("OK", sum(1 for row in sorted_rows if row.data_quality_status == "OK")),
        ("PARTIAL_DATA", sum(1 for row in sorted_rows if row.data_quality_status == "PARTIAL_DATA")),
        ("TOO_SMALL", sum(1 for row in sorted_rows if row.data_quality_status == "TOO_SMALL")),
        ("NO_DATA", sum(1 for row in sorted_rows if row.data_quality_status == "NO_DATA")),
    ]:
        writer.writerow(["data_quality_summary", metric, value])

    _write_csv_section_header(
        writer,
        ["section", "group_type", "group_name", "member_count", "eligible_count", "data_quality_status"],
    )
    for row in non_ok_rows:
        writer.writerow(
            [
                "non_ok_groups",
                row.group_type,
                row.group_name,
                row.member_count,
                row.eligible_count,
                row.data_quality_status,
            ]
        )

    return output.getvalue()


def format_report_summary_lines(summary: dict[str, int | str]) -> list[str]:
    return [f"SUMMARY {key}={summary[key]}" for key in REPORT_SUMMARY_ORDER]


def write_datacenter_index_report(
    *,
    analysis_db_path: str | Path,
    taxonomy_version: str,
    as_of_date: str,
    output_md: str | Path,
    output_csv: str | Path,
    top_n: int = 10,
) -> dict[str, int | str]:
    if top_n <= 0:
        raise ValueError(f"Invalid top_n: {top_n}")

    normalized_as_of_date = _parse_iso_date(as_of_date)
    rows = load_datacenter_report_rows(
        analysis_db_path=analysis_db_path,
        taxonomy_version=taxonomy_version,
        as_of_date=normalized_as_of_date,
    )
    markdown_report = build_markdown_report(
        rows,
        taxonomy_version=taxonomy_version,
        as_of_date=normalized_as_of_date,
        top_n=top_n,
    )
    csv_report = build_csv_report(
        rows,
        taxonomy_version=taxonomy_version,
        as_of_date=normalized_as_of_date,
        top_n=top_n,
    )

    output_md_path = _normalize_path(output_md)
    output_csv_path = _normalize_path(output_csv)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(markdown_report, encoding="utf-8")
    output_csv_path.write_text(csv_report, encoding="utf-8")

    ecosystem_rows = _filter_group_type(rows, "ecosystem")
    layer_rows = _filter_group_type(rows, "layer")
    subindustry_rows = _filter_group_type(rows, "subindustry")
    non_ok_rows = [row for row in rows if row.data_quality_status != "OK"]
    return {
        "taxonomy_version": taxonomy_version,
        "as_of_date": normalized_as_of_date,
        "rows_read": len(rows),
        "ecosystem_group_count": len(ecosystem_rows),
        "layer_group_count": len(layer_rows),
        "subindustry_group_count": len(subindustry_rows),
        "non_ok_group_count": len(non_ok_rows),
        "top_n": top_n,
        "output_md": str(output_md_path),
        "output_csv": str(output_csv_path),
        "report_status": "OK",
    }
