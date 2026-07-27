from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from analysis.datacenter_indices.pipeline_watermark import get_pipeline_watermark
from analysis.datacenter_indices.swing_ticker_persistence import (
    DEFAULT_MAX_VALID_PRICE_ROWS,
    load_bounded_ticker_ohlcv_history_window,
    load_valid_price_dates_for_market,
)
from analysis.datacenter_indices.taxonomy import load_datacenter_taxonomy_csv


DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"
DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS = 5
STAGE2_COMPONENT_NAME = "TICKER_SWING_BASE"
STAGE2_WRITE_MODE = "replace-date"
STAGE2_DOWNSTREAM_STAGE_PLANS = (
    (3, "GROUP_SWING_BASE", "Group swing base metrics"),
    (7, "GROUP_TIMING", "Group timing states"),
    (8, "GROUP_OVERHEAT", "Group overheat risk"),
    (9, "TICKER_SCANNER", "Ticker scanners"),
)

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


@dataclass(frozen=True)
class Stage2DownstreamPlan:
    stage_number: int
    component: str
    stage_name: str
    included_in_pilot_dirty_chain: bool
    materialization_start: str
    materialization_end: str
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Stage2IncrementalPlan:
    component: str
    mode: str
    requested_start: str
    requested_end: str
    effective_requested_end: str
    watermark_start: str | None
    watermark_end: str | None
    materialization_start: str | None
    materialization_end: str | None
    calculation_input_start: str | None
    calculation_input_end: str | None
    overlap_trading_days: int
    max_valid_price_rows: int
    write_mode: str
    reason_code: str
    reason_details: dict[str, Any]
    valid_signal_dates: list[str]
    output_dates: list[str]
    downstream_stage_plans: list[Stage2DownstreamPlan]
    excluded_stage_plans: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["downstream_stage_plans"] = [
            item.to_dict() for item in self.downstream_stage_plans
        ]
        return payload


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


def _validate_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _load_component_watermark_rows(
    *,
    analysis_db_path: Path,
    component_name: str,
) -> list[dict[str, Any]]:
    if not _table_exists(analysis_db_path, "dc_pipeline_watermark"):
        return []
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT component_name, taxonomy_version, market, signal_version, calc_version,
                   start_date, end_date, status
            FROM dc_pipeline_watermark
            WHERE component_name = ?
            ORDER BY taxonomy_version, market, signal_version, calc_version
            """,
            (component_name,),
        ).fetchall()
    return [{str(key): row[key] for key in row.keys()} for row in rows]


def _load_primary_tickers_for_taxonomy(
    *,
    taxonomy_csv_path: Path,
    taxonomy_version: str,
) -> list[str]:
    rows = load_datacenter_taxonomy_csv(taxonomy_csv_path)
    return sorted(
        {
            row.ticker.strip().upper()
            for row in rows
            if row.taxonomy_version == taxonomy_version and int(row.is_primary) == 1
        }
    )


def _dates_after(valid_dates: list[str], watermark_end: str) -> list[str]:
    return [value for value in valid_dates if value > watermark_end]


def _resolve_output_dates(
    *,
    valid_dates: list[str],
    materialization_start: str | None,
    materialization_end: str | None,
) -> list[str]:
    if materialization_start is None or materialization_end is None:
        return []
    return [
        value
        for value in valid_dates
        if materialization_start <= value <= materialization_end
    ]


def _resolve_stage2_calculation_input_start(
    *,
    price_db_path: Path,
    taxonomy_csv_path: Path,
    taxonomy_version: str,
    market: str,
    output_dates: list[str],
    max_valid_price_rows: int,
) -> tuple[str | None, dict[str, Any]]:
    if not output_dates:
        return None, {
            "resolved": False,
            "reason": "no_output_dates",
        }
    primary_tickers = _load_primary_tickers_for_taxonomy(
        taxonomy_csv_path=taxonomy_csv_path,
        taxonomy_version=taxonomy_version,
    )
    if not primary_tickers:
        return output_dates[0], {
            "resolved": True,
            "reason": "no_primary_tickers",
            "primary_ticker_count": 0,
        }

    # Reuse the Stage 2 bounded-history preload so planner-visible input start
    # follows the same 220-valid-row behavior as execution.
    history_window = load_bounded_ticker_ohlcv_history_window(
        price_db_path=price_db_path,
        tickers=primary_tickers,
        market=market,
        signal_dates=output_dates,
        max_valid_price_rows=max_valid_price_rows,
    )
    row_dates = [
        row.date
        for rows in history_window.valid_rows_by_ticker.values()
        for row in rows
    ]
    calculation_input_start = min(row_dates, default=output_dates[0])
    return calculation_input_start, {
        "resolved": True,
        "primary_ticker_count": len(primary_tickers),
        "preload_query_count": history_window.query_count,
        "preload_batch_count": history_window.batch_count,
        "preload_fetched_row_count": history_window.fetched_row_count,
        "preload_earliest_signal_date": history_window.earliest_signal_date,
        "preload_latest_signal_date": history_window.latest_signal_date,
    }


def _stage2_downstream_plans(
    *,
    materialization_start: str | None,
    materialization_end: str | None,
    mode: str,
) -> list[Stage2DownstreamPlan]:
    if mode == "SKIP" or materialization_start is None or materialization_end is None:
        return [
            Stage2DownstreamPlan(
                stage_number=stage_number,
                component=component,
                stage_name=stage_name,
                included_in_pilot_dirty_chain=True,
                materialization_start="",
                materialization_end="",
                reason_code="STAGE2_SKIP_NO_DIRTY_RANGE",
            )
            for stage_number, component, stage_name in STAGE2_DOWNSTREAM_STAGE_PLANS
        ]
    return [
        Stage2DownstreamPlan(
            stage_number=stage_number,
            component=component,
            stage_name=stage_name,
            included_in_pilot_dirty_chain=True,
            materialization_start=materialization_start,
            materialization_end=materialization_end,
            reason_code="STAGE2_MATERIALIZED_RANGE_PROPAGATED_CONSERVATIVELY",
        )
        for stage_number, component, stage_name in STAGE2_DOWNSTREAM_STAGE_PLANS
    ]


def build_stage2_incremental_plan(
    *,
    analysis_db_path: Path,
    price_db_path: Path,
    taxonomy_csv_path: Path,
    taxonomy_version: str,
    market: str,
    requested_start: str,
    requested_end: str,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    overlap_trading_days: int = DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    max_valid_price_rows: int = DEFAULT_MAX_VALID_PRICE_ROWS,
    force_full: bool = False,
    force_range_start: str | None = None,
    force_range_end: str | None = None,
    dirty_from_date: str | None = None,
    dependency_dirty_from_date: str | None = None,
) -> Stage2IncrementalPlan:
    requested_start_iso = _validate_iso_date(requested_start, "requested_start")
    requested_end_iso = _validate_iso_date(requested_end, "requested_end")
    if requested_start_iso > requested_end_iso:
        raise ValueError(
            f"Invalid requested range: {requested_start_iso} is after {requested_end_iso}"
        )
    if overlap_trading_days < 0:
        raise ValueError("overlap_trading_days must be zero or greater")
    if max_valid_price_rows <= 0:
        raise ValueError("max_valid_price_rows must be greater than 0")
    if force_full and (force_range_start is not None or force_range_end is not None):
        raise ValueError("force_full cannot be combined with force range")
    if (force_range_start is None) != (force_range_end is None):
        raise ValueError("force_range_start and force_range_end must be provided together")

    force_range_start_iso = (
        _validate_iso_date(force_range_start, "force_range_start")
        if force_range_start is not None
        else None
    )
    force_range_end_iso = (
        _validate_iso_date(force_range_end, "force_range_end")
        if force_range_end is not None
        else None
    )
    if (
        force_range_start_iso is not None
        and force_range_end_iso is not None
        and force_range_start_iso > force_range_end_iso
    ):
        raise ValueError(
            "Invalid forced range: "
            f"{force_range_start_iso} is after {force_range_end_iso}"
        )
    if (
        force_range_start_iso is not None
        and force_range_end_iso is not None
        and (
            force_range_start_iso < requested_start_iso
            or force_range_end_iso > requested_end_iso
        )
    ):
        raise ValueError("force range must be inside the requested range")

    dirty_from_date_iso = (
        _validate_iso_date(dirty_from_date, "dirty_from_date")
        if dirty_from_date is not None
        else None
    )
    dependency_dirty_from_date_iso = (
        _validate_iso_date(dependency_dirty_from_date, "dependency_dirty_from_date")
        if dependency_dirty_from_date is not None
        else None
    )

    valid_signal_dates = load_valid_price_dates_for_market(
        price_db_path=price_db_path,
        start_date=requested_start_iso,
        end_date=requested_end_iso,
        market=market,
        taxonomy_csv_path=taxonomy_csv_path,
        taxonomy_version=taxonomy_version,
    )
    effective_requested_end = valid_signal_dates[-1] if valid_signal_dates else requested_end_iso

    watermark = (
        _watermark_row(
            analysis_db_path=analysis_db_path,
            component_name=STAGE2_COMPONENT_NAME,
            taxonomy_version=taxonomy_version,
            market=market,
            signal_version=signal_version,
        )
        if _table_exists(analysis_db_path, "dc_pipeline_watermark")
        else None
    )
    watermark_start = None if watermark is None else str(watermark["start_date"])
    watermark_end = None if watermark is None else str(watermark["end_date"])
    watermark_status = None if watermark is None else str(watermark["status"])

    reason_details: dict[str, Any] = {
        "policy": "STAGE2_INCREMENTAL_PILOT",
        "overlap_is_materialization_policy": True,
        "warmup_source": "CURRENT_220_VALID_PRICE_ROW_STAGE2_HISTORY_BEHAVIOR",
        "dirty_from_date": dirty_from_date_iso,
        "dependency_dirty_from_date": dependency_dirty_from_date_iso,
    }

    if force_full:
        mode = "FULL"
        materialization_start = requested_start_iso
        materialization_end = effective_requested_end
        reason_code = "FORCED_FULL"
    elif force_range_start_iso is not None and force_range_end_iso is not None:
        mode = "INCREMENTAL"
        materialization_start = force_range_start_iso
        materialization_end = force_range_end_iso
        reason_code = "FORCED_RANGE"
    elif not valid_signal_dates:
        mode = "SKIP"
        materialization_start = None
        materialization_end = None
        reason_code = "NO_VALID_SIGNAL_DATES"
    elif watermark is None:
        mode = "FULL"
        materialization_start = requested_start_iso
        materialization_end = effective_requested_end
        existing_rows = _load_component_watermark_rows(
            analysis_db_path=analysis_db_path,
            component_name=STAGE2_COMPONENT_NAME,
        )
        reason_code = (
            "INCOMPATIBLE_OR_MISSING_COMPATIBLE_WATERMARK"
            if existing_rows
            else "MISSING_COMPATIBLE_WATERMARK"
        )
        reason_details["existing_component_watermarks"] = existing_rows
    elif watermark_status != "OK":
        mode = "FULL"
        materialization_start = requested_start_iso
        materialization_end = effective_requested_end
        reason_code = "UNUSABLE_WATERMARK_STATUS"
        reason_details["watermark_status"] = watermark_status
    elif watermark_start is not None and watermark_start > requested_start_iso:
        mode = "FULL"
        materialization_start = requested_start_iso
        materialization_end = effective_requested_end
        reason_code = "REQUESTED_START_BEFORE_WATERMARK"
    else:
        invalidation_candidates = [
            value
            for value in (dirty_from_date_iso, dependency_dirty_from_date_iso)
            if value is not None
        ]
        if invalidation_candidates:
            mode = "INCREMENTAL"
            materialization_start = max(requested_start_iso, min(invalidation_candidates))
            materialization_end = effective_requested_end
            reason_code = "EXPLICIT_DIRTY_RANGE"
        elif watermark_end is not None and watermark_end >= effective_requested_end:
            mode = "SKIP"
            materialization_start = None
            materialization_end = None
            reason_code = "WATERMARK_COVERS_REQUESTED_TARGET"
        else:
            new_valid_dates = _dates_after(valid_signal_dates, watermark_end or "")
            if not new_valid_dates:
                mode = "SKIP"
                materialization_start = None
                materialization_end = None
                reason_code = "NO_NEW_VALID_SIGNAL_DATES"
            else:
                first_new_date = new_valid_dates[0]
                first_new_index = valid_signal_dates.index(first_new_date)
                start_index = max(0, first_new_index - overlap_trading_days)
                mode = "INCREMENTAL"
                materialization_start = valid_signal_dates[start_index]
                materialization_end = effective_requested_end
                reason_code = "NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP"
                reason_details["first_new_valid_signal_date"] = first_new_date
                reason_details["first_new_valid_signal_date_index"] = first_new_index

    output_dates = _resolve_output_dates(
        valid_dates=valid_signal_dates,
        materialization_start=materialization_start,
        materialization_end=materialization_end,
    )
    calculation_input_start, input_resolution_details = _resolve_stage2_calculation_input_start(
        price_db_path=price_db_path,
        taxonomy_csv_path=taxonomy_csv_path,
        taxonomy_version=taxonomy_version,
        market=market,
        output_dates=output_dates,
        max_valid_price_rows=max_valid_price_rows,
    )
    reason_details.update(
        {
            "valid_signal_date_count": len(valid_signal_dates),
            "output_date_count": len(output_dates),
            "requested_signal_date_was_valid": requested_end_iso in valid_signal_dates,
            "effective_requested_end_source": (
                "latest_valid_signal_date_at_or_before_requested_end"
                if valid_signal_dates and effective_requested_end != requested_end_iso
                else "requested_end"
            ),
            "input_resolution": input_resolution_details,
        }
    )

    return Stage2IncrementalPlan(
        component=STAGE2_COMPONENT_NAME,
        mode=mode,
        requested_start=requested_start_iso,
        requested_end=requested_end_iso,
        effective_requested_end=effective_requested_end,
        watermark_start=watermark_start,
        watermark_end=watermark_end,
        materialization_start=materialization_start,
        materialization_end=materialization_end,
        calculation_input_start=calculation_input_start,
        calculation_input_end=materialization_end,
        overlap_trading_days=overlap_trading_days,
        max_valid_price_rows=max_valid_price_rows,
        write_mode=STAGE2_WRITE_MODE,
        reason_code=reason_code,
        reason_details=reason_details,
        valid_signal_dates=valid_signal_dates,
        output_dates=output_dates,
        downstream_stage_plans=_stage2_downstream_plans(
            materialization_start=materialization_start,
            materialization_end=materialization_end,
            mode=mode,
        ),
        excluded_stage_plans=[
            {
                "stage_number": 6,
                "component": "SYNTHETIC_OHLC_STRUCTURE",
                "stage_name": "Group structure / BOS / RESET",
                "included_in_pilot_dirty_chain": False,
                "reason_code": "STAGE6_OUTSIDE_STAGE2_INCREMENTAL_PILOT",
            }
        ],
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
