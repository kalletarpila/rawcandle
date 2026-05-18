from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from analysis.datacenter_indices.pipeline_watermark import get_pipeline_watermark


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"

PIPELINE_COMPONENT_ORDER = (
    "GROUP_INDEX",
    "TICKER_SWING_BASE",
    "GROUP_SWING_BASE",
    "SYNTHETIC_OHLC_BASE",
    "SYNTHETIC_OHLC_RELATIVE",
    "SYNTHETIC_OHLC_STRUCTURE",
    "GROUP_TIMING",
    "GROUP_OVERHEAT",
    "TICKER_SCANNER",
    "PIPELINE_AUDIT",
    "DAILY_REPORT",
    "WEEKLY_REPORT",
)

PLAN_SUMMARY_ORDER = (
    "signal_date",
    "start_date",
    "index_base_date",
    "taxonomy_version",
    "signal_version",
    "ohlc_calc_version",
    "planned_components",
    "up_to_date_count",
    "run_full_range_count",
    "run_incremental_candidate_count",
    "missing_watermark_count",
    "run_required_count",
    "validation_status",
)


def _table_exists(analysis_db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(analysis_db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
    return row is not None


def _next_date(value: str) -> str:
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def _watermark_row(
    *,
    analysis_db_path: Path,
    component_name: str,
    taxonomy_version: str,
    market: str = "",
    signal_version: str = "",
    calc_version: str = "",
) -> dict[str, Any] | None:
    return get_pipeline_watermark(
        analysis_db_path=analysis_db_path,
        component_name=component_name,
        taxonomy_version=taxonomy_version,
        market=market,
        signal_version=signal_version,
        calc_version=calc_version,
    )


def _build_plan_row(
    *,
    component_name: str,
    watermark: dict[str, Any] | None,
    requested_start_date: str,
    requested_end_date: str,
    plan_action: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "component_name": component_name,
        "plan_action": plan_action,
        "existing_start_date": "" if watermark is None else str(watermark["start_date"]),
        "existing_end_date": "" if watermark is None else str(watermark["end_date"]),
        "requested_start_date": requested_start_date,
        "requested_end_date": requested_end_date,
        "status": "" if watermark is None else str(watermark["status"]),
        "reason": reason,
    }


def build_datacenter_pipeline_plan(
    *,
    analysis_db_path: Path,
    taxonomy_version: str,
    market: str,
    signal_date: str,
    start_date: str,
    index_base_date: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
) -> dict[str, Any]:
    if not _table_exists(analysis_db_path, "dc_pipeline_watermark"):
        summary = {
            "signal_date": signal_date,
            "start_date": start_date,
            "index_base_date": index_base_date,
            "taxonomy_version": taxonomy_version,
            "signal_version": signal_version,
            "ohlc_calc_version": ohlc_calc_version,
            "planned_components": 0,
            "up_to_date_count": 0,
            "run_full_range_count": 0,
            "run_incremental_candidate_count": 0,
            "missing_watermark_count": 0,
            "run_required_count": 0,
            "validation_status": "FAIL",
        }
        return {"summary": summary, "rows": []}

    rows: list[dict[str, Any]] = []

    group_index = _watermark_row(
        analysis_db_path=analysis_db_path,
        component_name="GROUP_INDEX",
        taxonomy_version=taxonomy_version,
        market=market,
    )
    if group_index is None:
        rows.append(
            _build_plan_row(
                component_name="GROUP_INDEX",
                watermark=None,
                requested_start_date=index_base_date,
                requested_end_date=signal_date,
                plan_action="MISSING_WATERMARK",
                reason="missing_watermark",
            )
        )
    elif group_index["start_date"] != index_base_date:
        rows.append(
            _build_plan_row(
                component_name="GROUP_INDEX",
                watermark=group_index,
                requested_start_date=index_base_date,
                requested_end_date=signal_date,
                plan_action="RUN_FULL_RANGE",
                reason="index_base_date_mismatch",
            )
        )
    elif group_index["end_date"] < signal_date:
        rows.append(
            _build_plan_row(
                component_name="GROUP_INDEX",
                watermark=group_index,
                requested_start_date=index_base_date,
                requested_end_date=signal_date,
                plan_action="RUN_FULL_RANGE",
                reason="index_out_of_date_full_rebuild_required_currently",
            )
        )
    else:
        rows.append(
            _build_plan_row(
                component_name="GROUP_INDEX",
                watermark=group_index,
                requested_start_date=index_base_date,
                requested_end_date=signal_date,
                plan_action="UP_TO_DATE",
                reason="watermark_covers_requested_range",
            )
        )

    for component_name in ("TICKER_SWING_BASE", "GROUP_SWING_BASE"):
        watermark = _watermark_row(
            analysis_db_path=analysis_db_path,
            component_name=component_name,
            taxonomy_version=taxonomy_version,
            market=market if component_name == "TICKER_SWING_BASE" else "",
            signal_version=signal_version,
        )
        if watermark is None:
            action = "MISSING_WATERMARK"
            reason = "missing_watermark"
        elif watermark["start_date"] > start_date:
            action = "RUN_FULL_RANGE"
            reason = "requested_start_before_watermark"
        elif watermark["end_date"] < signal_date:
            action = "RUN_INCREMENTAL_CANDIDATE"
            reason = "ticker_base_can_extend_from_watermark" if component_name == "TICKER_SWING_BASE" else "group_base_can_extend_from_watermark"
        else:
            action = "UP_TO_DATE"
            reason = "watermark_covers_requested_range"
        rows.append(
            _build_plan_row(
                component_name=component_name,
                watermark=watermark,
                requested_start_date=start_date if watermark is None or watermark.get("end_date", "") >= signal_date else _next_date(str(watermark["end_date"])),
                requested_end_date=signal_date,
                plan_action=action,
                reason=reason,
            )
        )

    synthetic_base = _watermark_row(
        analysis_db_path=analysis_db_path,
        component_name="SYNTHETIC_OHLC_BASE",
        taxonomy_version=taxonomy_version,
        market=market,
        calc_version=ohlc_calc_version,
    )
    if synthetic_base is None:
        action = "MISSING_WATERMARK"
        reason = "missing_watermark"
    elif synthetic_base["start_date"] > start_date:
        action = "RUN_FULL_RANGE"
        reason = "synthetic_chain_start_after_requested_start"
    elif synthetic_base["end_date"] < signal_date:
        action = "RUN_FULL_RANGE"
        reason = "synthetic_chain_incremental_not_enabled"
    else:
        action = "UP_TO_DATE"
        reason = "watermark_covers_requested_range"
    rows.append(
        _build_plan_row(
            component_name="SYNTHETIC_OHLC_BASE",
            watermark=synthetic_base,
            requested_start_date=start_date,
            requested_end_date=signal_date,
            plan_action=action,
            reason=reason,
        )
    )

    relative = _watermark_row(
        analysis_db_path=analysis_db_path,
        component_name="SYNTHETIC_OHLC_RELATIVE",
        taxonomy_version=taxonomy_version,
        market=market,
        calc_version=ohlc_calc_version,
    )
    if relative is None:
        action = "MISSING_WATERMARK"
        reason = "missing_watermark"
    elif relative["start_date"] > start_date:
        action = "RUN_FULL_RANGE"
        reason = "requested_start_before_watermark"
    elif relative["end_date"] < signal_date:
        action = "RUN_INCREMENTAL_CANDIDATE"
        reason = "relative_ohlc_can_extend_after_base_available"
    else:
        action = "UP_TO_DATE"
        reason = "watermark_covers_requested_range"
    rows.append(
        _build_plan_row(
            component_name="SYNTHETIC_OHLC_RELATIVE",
            watermark=relative,
            requested_start_date=start_date if relative is None or relative.get("end_date", "") >= signal_date else _next_date(str(relative["end_date"])),
            requested_end_date=signal_date,
            plan_action=action,
            reason=reason,
        )
    )

    structure = _watermark_row(
        analysis_db_path=analysis_db_path,
        component_name="SYNTHETIC_OHLC_STRUCTURE",
        taxonomy_version=taxonomy_version,
        market=market,
        calc_version=ohlc_calc_version,
    )
    if structure is None:
        action = "MISSING_WATERMARK"
        reason = "missing_watermark"
    elif structure["start_date"] > start_date:
        action = "RUN_FULL_RANGE"
        reason = "requested_start_before_watermark"
    elif structure["end_date"] < signal_date:
        action = "RUN_FULL_RANGE"
        reason = "structure_incremental_not_enabled"
    else:
        action = "UP_TO_DATE"
        reason = "watermark_covers_requested_range"
    rows.append(
        _build_plan_row(
            component_name="SYNTHETIC_OHLC_STRUCTURE",
            watermark=structure,
            requested_start_date=start_date,
            requested_end_date=signal_date,
            plan_action=action,
            reason=reason,
        )
    )

    for component_name in ("GROUP_TIMING", "GROUP_OVERHEAT", "TICKER_SCANNER"):
        watermark = _watermark_row(
            analysis_db_path=analysis_db_path,
            component_name=component_name,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
        )
        if watermark is None:
            action = "MISSING_WATERMARK"
            reason = "missing_watermark"
            requested_component_start_date = start_date
        elif watermark["start_date"] > start_date:
            action = "RUN_FULL_RANGE"
            reason = "requested_start_before_watermark"
            requested_component_start_date = start_date
        elif watermark["end_date"] < signal_date:
            action = "RUN_INCREMENTAL_CANDIDATE"
            reason = {
                "GROUP_TIMING": "group_timing_can_extend_from_watermark",
                "GROUP_OVERHEAT": "group_overheat_can_extend_from_watermark",
                "TICKER_SCANNER": "ticker_scanner_can_extend_from_watermark",
            }[component_name]
            requested_component_start_date = _next_date(str(watermark["end_date"]))
        else:
            action = "UP_TO_DATE"
            reason = "watermark_covers_requested_range"
            requested_component_start_date = start_date
        rows.append(
            _build_plan_row(
                component_name=component_name,
                watermark=watermark,
                requested_start_date=requested_component_start_date,
                requested_end_date=signal_date,
                plan_action=action,
                reason=reason,
            )
        )

    pipeline_audit = _watermark_row(
        analysis_db_path=analysis_db_path,
        component_name="PIPELINE_AUDIT",
        taxonomy_version=taxonomy_version,
        signal_version=signal_version,
        calc_version=ohlc_calc_version,
    )
    if pipeline_audit is None:
        action = "RUN_REQUIRED"
        reason = "missing_watermark"
    elif pipeline_audit["status"] == "FAIL":
        action = "RUN_REQUIRED"
        reason = "previous_audit_failed"
    elif pipeline_audit["end_date"] < signal_date:
        action = "RUN_REQUIRED"
        reason = "audit_out_of_date"
    else:
        action = "UP_TO_DATE"
        reason = "audit_present_for_signal_date"
    rows.append(
        _build_plan_row(
            component_name="PIPELINE_AUDIT",
            watermark=pipeline_audit,
            requested_start_date=signal_date,
            requested_end_date=signal_date,
            plan_action=action,
            reason=reason,
        )
    )

    for component_name in ("DAILY_REPORT", "WEEKLY_REPORT"):
        watermark = _watermark_row(
            analysis_db_path=analysis_db_path,
            component_name=component_name,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
            calc_version=ohlc_calc_version,
        )
        if watermark is None:
            action = "RUN_REQUIRED"
            reason = "missing_watermark"
        elif watermark["end_date"] < signal_date:
            action = "RUN_REQUIRED"
            reason = "report_out_of_date"
        else:
            action = "UP_TO_DATE"
            reason = "report_present_for_signal_date"
        rows.append(
            _build_plan_row(
                component_name=component_name,
                watermark=watermark,
                requested_start_date=signal_date,
                requested_end_date=signal_date,
                plan_action=action,
                reason=reason,
            )
        )

    ordered_rows = [row for component in PIPELINE_COMPONENT_ORDER for row in rows if row["component_name"] == component]
    summary = {
        "signal_date": signal_date,
        "start_date": start_date,
        "index_base_date": index_base_date,
        "taxonomy_version": taxonomy_version,
        "signal_version": signal_version,
        "ohlc_calc_version": ohlc_calc_version,
        "planned_components": len(ordered_rows),
        "up_to_date_count": sum(1 for row in ordered_rows if row["plan_action"] == "UP_TO_DATE"),
        "run_full_range_count": sum(1 for row in ordered_rows if row["plan_action"] == "RUN_FULL_RANGE"),
        "run_incremental_candidate_count": sum(1 for row in ordered_rows if row["plan_action"] == "RUN_INCREMENTAL_CANDIDATE"),
        "missing_watermark_count": sum(1 for row in ordered_rows if row["plan_action"] == "MISSING_WATERMARK"),
        "run_required_count": sum(1 for row in ordered_rows if row["plan_action"] == "RUN_REQUIRED"),
        "validation_status": "OK",
    }
    return {"summary": summary, "rows": ordered_rows}


def format_pipeline_plan_summary_lines(summary: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in PLAN_SUMMARY_ORDER:
        if key in summary:
            lines.append(f"SUMMARY {key}={summary[key]}")
    for key, value in summary.items():
        if key not in PLAN_SUMMARY_ORDER:
            lines.append(f"SUMMARY {key}={value}")
    return lines
