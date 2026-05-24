from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from dev_tools.datacenter_dashboard_support import DatacenterReportStatus


@dataclass(frozen=True)
class DatacenterDashboardRow:
    ticker: str
    horizon: str
    source_file: str
    section: str | None
    row_kind: str | None
    raw_action: str | None
    raw_status: str | None
    reason: str | None
    trend_state: str | None
    latest_structure_label: str | None
    latest_bos_event_type: str | None
    latest_reset_reason: str | None
    distance_to_ema20: float | None
    high_exit_risk_days_count: int | None
    blocking_reasons: str | None
    ma_break_status: str | None
    ema20_break_confirmed: int | None
    sma50_break_confirmed: int | None
    close_below_ema20: int | None
    close_below_sma50: int | None
    consecutive_closes_below_ema20: int | None
    consecutive_closes_below_sma50: int | None
    ema20_break_pct: float | None
    sma50_break_pct: float | None
    freshness_status: str | None
    structure_warning_overrides_bullish_signal: int | None
    latest_bullish_signal_age_td: int | None
    latest_bearish_signal_age_td: int | None
    latest_bos_up_age_td: int | None
    latest_bos_down_age_td: int | None
    latest_reset_age_td: int | None
    raw_fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatacenterDashboardParseResult:
    rows: list[DatacenterDashboardRow]
    warnings: list[str]


@dataclass(frozen=True)
class DatacenterDashboardReportParseSummary:
    horizon: str
    source_file: str | None
    row_count: int
    warning_count: int


@dataclass(frozen=True)
class DatacenterDashboardBatchParseResult:
    reports: list[DatacenterDashboardReportParseSummary]
    total_row_count: int
    total_warning_count: int


_COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ticker": ("ticker", "symbol", "osake"),
    "raw_action": ("action", "recommendation", "signal", "decision"),
    "raw_status": ("status", "state"),
    "reason": ("reason", "reasons"),
    "blocking_reasons": ("blocking_reasons", "blocking_reason"),
    "trend_state": ("trend_state", "ticker_trend_state", "last_ticker_trend_state"),
    "latest_structure_label": (
        "latest_structure_label",
        "last_latest_structure_label",
    ),
    "latest_bos_event_type": (
        "latest_bos_event_type",
        "last_latest_bos_event_type",
    ),
    "latest_reset_reason": (
        "latest_reset_reason",
        "last_latest_reset_reason",
    ),
    "distance_to_ema20": (
        "distance_to_ema20",
        "ema20_distance",
        "distance_from_ema20",
        "dist_ema20",
        "last_distance_to_ema20",
    ),
    "high_exit_risk_days_count": (
        "high_exit_risk_days_count",
        "exit_risk_days",
        "risk_days_count",
    ),
    "ma_break_status": ("ma_break_status",),
    "ema20_break_confirmed": ("ema20_break_confirmed",),
    "sma50_break_confirmed": ("sma50_break_confirmed",),
    "close_below_ema20": ("close_below_ema20",),
    "close_below_sma50": ("close_below_sma50",),
    "consecutive_closes_below_ema20": ("consecutive_closes_below_ema20",),
    "consecutive_closes_below_sma50": ("consecutive_closes_below_sma50",),
    "ema20_break_pct": ("ema20_break_pct",),
    "sma50_break_pct": ("sma50_break_pct",),
    "freshness_status": ("freshness_status",),
    "structure_warning_overrides_bullish_signal": ("structure_warning_overrides_bullish_signal",),
    "latest_bullish_signal_age_td": ("latest_bullish_signal_age_td",),
    "latest_bearish_signal_age_td": ("latest_bearish_signal_age_td",),
    "latest_bos_up_age_td": ("latest_bos_up_age_td",),
    "latest_bos_down_age_td": ("latest_bos_down_age_td",),
    "latest_reset_age_td": ("latest_reset_age_td",),
}

_HEADER_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_MARKDOWN_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")


def _normalize_header(value: str) -> str:
    normalized = _HEADER_NORMALIZE_RE.sub("_", value.strip().lower()).strip("_")
    return normalized


def _resolve_column(headers: list[str], canonical_name: str) -> Optional[str]:
    header_set = set(headers)
    for synonym in _COLUMN_SYNONYMS.get(canonical_name, ()):
        if synonym in header_set:
            return synonym
    return None


def _normalized_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text


def _safe_float(
    value: str | None,
    *,
    source_file: str,
    field_name: str,
    warnings: list[str],
) -> float | None:
    text = _normalized_optional_string(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        warnings.append(
            f"{source_file}: invalid float for {field_name}: {text}"
        )
        return None


def _safe_int(
    value: str | None,
    *,
    source_file: str,
    field_name: str,
    warnings: list[str],
) -> int | None:
    text = _normalized_optional_string(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        warnings.append(
            f"{source_file}: invalid int for {field_name}: {text}"
        )
        return None


def _build_row(
    *,
    header: list[str],
    values: list[str],
    horizon: str,
    source_file: str,
    section: str | None,
    warnings: list[str],
) -> DatacenterDashboardRow | None:
    padded_values = values[: len(header)] + [""] * max(0, len(header) - len(values))
    raw_fields = {
        column: value.strip()
        for column, value in zip(header, padded_values)
        if column
    }
    ticker_key = _resolve_column(header, "ticker")
    if ticker_key is None:
        return None
    ticker = raw_fields.get(ticker_key, "").strip()
    if not ticker:
        return None

    def _text_field(canonical_name: str) -> str | None:
        return _normalized_optional_string(
            raw_fields.get(_resolve_column(header, canonical_name) or "")
        )

    def _int_field(canonical_name: str) -> int | None:
        resolved_column = _resolve_column(header, canonical_name)
        return _safe_int(
            raw_fields.get(resolved_column or ""),
            source_file=source_file,
            field_name=canonical_name,
            warnings=warnings,
        )

    def _float_field(canonical_name: str) -> float | None:
        resolved_column = _resolve_column(header, canonical_name)
        return _safe_float(
            raw_fields.get(resolved_column or ""),
            source_file=source_file,
            field_name=canonical_name,
            warnings=warnings,
        )

    return DatacenterDashboardRow(
        ticker=ticker,
        horizon=horizon,
        source_file=source_file,
        section=_normalized_optional_string(section or raw_fields.get("section") or None),
        row_kind=_normalized_optional_string(raw_fields.get("row_kind")),
        raw_action=_text_field("raw_action"),
        raw_status=_text_field("raw_status"),
        reason=_text_field("reason"),
        trend_state=_text_field("trend_state"),
        latest_structure_label=_text_field("latest_structure_label"),
        latest_bos_event_type=_text_field("latest_bos_event_type"),
        latest_reset_reason=_text_field("latest_reset_reason"),
        distance_to_ema20=_float_field("distance_to_ema20"),
        high_exit_risk_days_count=_int_field("high_exit_risk_days_count"),
        blocking_reasons=_text_field("blocking_reasons"),
        ma_break_status=_text_field("ma_break_status"),
        ema20_break_confirmed=_int_field("ema20_break_confirmed"),
        sma50_break_confirmed=_int_field("sma50_break_confirmed"),
        close_below_ema20=_int_field("close_below_ema20"),
        close_below_sma50=_int_field("close_below_sma50"),
        consecutive_closes_below_ema20=_int_field("consecutive_closes_below_ema20"),
        consecutive_closes_below_sma50=_int_field("consecutive_closes_below_sma50"),
        ema20_break_pct=_float_field("ema20_break_pct"),
        sma50_break_pct=_float_field("sma50_break_pct"),
        freshness_status=_text_field("freshness_status"),
        structure_warning_overrides_bullish_signal=_int_field("structure_warning_overrides_bullish_signal"),
        latest_bullish_signal_age_td=_int_field("latest_bullish_signal_age_td"),
        latest_bearish_signal_age_td=_int_field("latest_bearish_signal_age_td"),
        latest_bos_up_age_td=_int_field("latest_bos_up_age_td"),
        latest_bos_down_age_td=_int_field("latest_bos_down_age_td"),
        latest_reset_age_td=_int_field("latest_reset_age_td"),
        raw_fields=raw_fields,
    )


def _parse_semicolon_rows(
    *,
    text: str,
    horizon: str,
    source_file: str,
) -> DatacenterDashboardParseResult:
    rows: list[DatacenterDashboardRow] = []
    warnings: list[str] = []
    current_header: list[str] | None = None
    current_section: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or ";" not in stripped or stripped.startswith("SUMMARY "):
            continue
        try:
            parsed_row = next(csv.reader([line], delimiter=";"))
        except csv.Error as exc:
            warnings.append(f"{source_file}: line {line_number} csv parse failed: {exc}")
            continue
        normalized = [_normalize_header(cell) for cell in parsed_row]
        if _resolve_column(normalized, "ticker") is not None:
            current_header = normalized
            if normalized and normalized[0] == "section":
                current_section = parsed_row[0].strip() or current_section
            continue
        if current_header is None:
            continue
        if normalized and normalized[0] == "section":
            current_section = parsed_row[0].strip() or current_section
        row = _build_row(
            header=current_header,
            values=parsed_row,
            horizon=horizon,
            source_file=source_file,
            section=current_section,
            warnings=warnings,
        )
        if row is None:
            warnings.append(f"{source_file}: line {line_number} skipped without ticker")
            continue
        rows.append(row)
    return DatacenterDashboardParseResult(rows=rows, warnings=warnings)


def _parse_markdown_rows(
    *,
    text: str,
    horizon: str,
    source_file: str,
) -> DatacenterDashboardParseResult:
    rows: list[DatacenterDashboardRow] = []
    warnings: list[str] = []
    lines = text.splitlines()
    line_index = 0
    while line_index < len(lines):
        header_line = lines[line_index].strip()
        if "|" not in header_line or line_index + 1 >= len(lines):
            line_index += 1
            continue
        separator_line = lines[line_index + 1].strip()
        if not _MARKDOWN_SEPARATOR_RE.match(separator_line):
            line_index += 1
            continue
        header = [
            _normalize_header(cell)
            for cell in header_line.strip("|").split("|")
        ]
        if _resolve_column(header, "ticker") is None:
            line_index += 2
            continue
        line_index += 2
        while line_index < len(lines):
            row_line = lines[line_index].strip()
            if not row_line or "|" not in row_line:
                break
            values = [cell.strip() for cell in row_line.strip("|").split("|")]
            row = _build_row(
                header=header,
                values=values,
                horizon=horizon,
                source_file=source_file,
                section=None,
                warnings=warnings,
            )
            if row is None:
                warnings.append(f"{source_file}: line {line_index + 1} skipped without ticker")
            else:
                rows.append(row)
            line_index += 1
        continue
    return DatacenterDashboardParseResult(rows=rows, warnings=warnings)


def parse_datacenter_dashboard_file(
    *,
    path: str,
    horizon: str,
) -> DatacenterDashboardParseResult:
    source_file = str(path)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return DatacenterDashboardParseResult(
            rows=[],
            warnings=[f"{source_file}: read failed: {exc}"],
        )

    semicolon_result = _parse_semicolon_rows(
        text=text,
        horizon=horizon,
        source_file=source_file,
    )
    markdown_result = _parse_markdown_rows(
        text=text,
        horizon=horizon,
        source_file=source_file,
    )
    if semicolon_result.rows or semicolon_result.warnings:
        return semicolon_result
    return markdown_result


def parse_datacenter_dashboard_reports(
    report_statuses: Iterable[DatacenterReportStatus],
) -> DatacenterDashboardBatchParseResult:
    summaries: list[DatacenterDashboardReportParseSummary] = []
    total_rows = 0
    total_warnings = 0

    for report_status in report_statuses:
        if report_status.path is None:
            summaries.append(
                DatacenterDashboardReportParseSummary(
                    horizon=report_status.horizon,
                    source_file=None,
                    row_count=0,
                    warning_count=0,
                )
            )
            continue
        parse_result = parse_datacenter_dashboard_file(
            path=report_status.path,
            horizon=report_status.horizon,
        )
        row_count = len(parse_result.rows)
        warning_count = len(parse_result.warnings)
        total_rows += row_count
        total_warnings += warning_count
        summaries.append(
            DatacenterDashboardReportParseSummary(
                horizon=report_status.horizon,
                source_file=report_status.path,
                row_count=row_count,
                warning_count=warning_count,
            )
        )

    return DatacenterDashboardBatchParseResult(
        reports=summaries,
        total_row_count=total_rows,
        total_warning_count=total_warnings,
    )
