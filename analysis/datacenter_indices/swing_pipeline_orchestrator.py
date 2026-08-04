from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from shutil import copy2
from time import perf_counter
from typing import Callable
import re
import sqlite3

from analysis.datacenter_indices.persistence import resolve_created_at_utc
from analysis.datacenter_indices.swing_daily_report import (
    DEFAULT_OHLC_CALC_VERSION,
    DEFAULT_SIGNAL_VERSION,
    DEFAULT_WATCHLIST_FILE,
    format_daily_swing_report_summary_lines,
    write_daily_swing_signal_report,
)
from analysis.datacenter_indices.swing_pipeline_audit import (
    format_swing_pipeline_audit_summary_lines,
    load_swing_pipeline_audit,
)
from analysis.datacenter_indices.technical_relevance_context import (
    load_datacenter_pipeline_technical_relevance_tickers,
)
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from analysis.datacenter_indices.pipeline_plan import (
    DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    Stage2IncrementalPlan,
    build_stage2_incremental_plan,
)
from analysis.datacenter_indices.swing_weekly_report import (
    format_weekly_swing_report_summary_lines,
    write_weekly_swing_report,
)
from run_datacenter_group_swing_signals import main as run_datacenter_group_swing_signals_main
from run_datacenter_group_synthetic_ohlc import main as run_datacenter_group_synthetic_ohlc_main
from run_datacenter_indices import main as run_datacenter_indices_main
from run_datacenter_ticker_swing_signals import main as run_datacenter_ticker_swing_signals_main
from rawcandle.technical_signal_relevance_service import (
    TechnicalSignalRelevanceProfile,
    format_technical_relevance_profile_summary_lines,
    run_technical_signal_relevance_for_tickers,
)
from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    read_relevance_run,
)
from rawcandle.datacenter_decision_summary import (
    DecisionSummaryError,
    build_decision_summary,
    extract_section,
    parse_metadata,
)


WINDOWS_REPORT_COPY_DIR = Path("/mnt/d/swing_reports")


FINAL_PIPELINE_SUMMARY_ORDER = (
    "pipeline_signal_date",
    "pipeline_start_date",
    "pipeline_index_base_date",
    "pipeline_taxonomy_version",
    "pipeline_signal_version",
    "pipeline_ohlc_calc_version",
    "technical_relevance.enabled",
    "technical_relevance.mode",
    "technical_relevance.run_id",
    "technical_relevance.ticker_count",
    "technical_relevance.ticker_count_status",
    "technical_relevance.start_date",
    "technical_relevance.end_date",
    "technical_relevance.status",
    "technical_relevance_run_id",
    "pipeline_output_dir",
    "windows_report_copy.enabled",
    "windows_report_copy.destination_dir",
    "windows_report_copy.execution_status",
    "windows_report_copy.skip_reason",
    "pipeline_stage_count",
    "pipeline_completed_stage_count",
    "pipeline.total_duration_seconds",
    "audit_validation_status",
    "daily_report_path",
    "daily_report_csv_path",
    "weekly_report_path",
    "weekly_report_csv_path",
    "rolling_30_report_path",
    "rolling_30_report_csv_path",
    "rolling_5_report_path",
    "rolling_5_report_csv_path",
    "rolling_2_report_path",
    "rolling_2_report_csv_path",
    "decision_summary_report_path",
    "decision_summary.status",
    "decision_summary.execution_status",
    "decision_summary.skip_reason",
    "decision_summary.error",
    "pipeline_status",
)

DAILY_REPORT_FILENAME_RE = re.compile(
    r"^datacenter_daily_(?P<signal_date>\d{4}-\d{2}-\d{2})(?:_(?P<hhmm>\d{4}))?_full\.md$"
)

PIPELINE_STAGE_KEYS = (
    "datacenter_base_index",
    "ticker_swing_base_snapshots",
    "group_swing_base_metrics",
    "synthetic_ohlc_base",
    "relative_ohlc20",
    "group_structure_bos_reset",
    "group_timing_states",
    "group_overheat_risk",
    "ticker_scanners",
    "pipeline_audit",
    "automatic_technical_relevance",
    "daily_report",
    "rolling_30_report",
    "rolling_5_report",
    "rolling_2_report",
    "windows_report_copy",
)


@dataclass(frozen=True)
class PipelineStage:
    stage_key: str
    heading: str
    argv: list[str]
    runner: Callable[[], dict[str, object] | None]
    watermark_builder: Callable[[dict[str, object] | None], dict[str, object]] | None = None
    preserve_watermark_coverage_start: bool = False
    skip_status: str | None = None
    skip_reason: str | None = None


def _normalize_run_id_token(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def build_datacenter_technical_relevance_run_id(
    *,
    taxonomy_version: str,
    signal_date: str,
) -> str:
    return (
        "DATACENTER_TECH_REL_"
        f"{_normalize_run_id_token(taxonomy_version)}_"
        f"{signal_date.replace('-', '_')}"
    )


def compute_datacenter_technical_relevance_date_range(signal_date: str) -> tuple[str, str]:
    normalized_signal_date = datetime.strptime(signal_date, "%Y-%m-%d").date()
    return (
        (normalized_signal_date - timedelta(days=45)).isoformat(),
        normalized_signal_date.isoformat(),
    )


def _resolve_output_timestamp_hhmm(generated_at_utc: str | None) -> str:
    if generated_at_utc:
        return datetime.strptime(generated_at_utc, "%Y-%m-%dT%H:%M:%SZ").strftime("%H%M")
    return datetime.now().strftime("%H%M")


def _timestamp_output_path(path: Path, *, date_value: str, hhmm: str) -> Path:
    stem = path.stem
    for token in (date_value, date_value.replace("-", "_")):
        if token in stem:
            return path.with_name(f"{stem.replace(token, f'{token}_{hhmm}', 1)}{path.suffix}")
    return path.with_name(f"{stem}_{hhmm}{path.suffix}")


def _build_decision_summary_output_path(
    *,
    output_dir: Path,
    signal_date: str,
    output_hhmm: str,
) -> Path:
    return _timestamp_output_path(
        output_dir / f"datacenter_decision_summary_{signal_date}_full.md",
        date_value=signal_date,
        hhmm=output_hhmm,
    )


def _read_report_metadata(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    try:
        return parse_metadata(extract_section(text, "1. Title and run metadata"))
    except DecisionSummaryError:
        return {}


def _find_previous_daily_report(
    *,
    current_daily_report: Path,
    current_signal_date: str,
) -> Path | None:
    current_metadata = _read_report_metadata(current_daily_report)
    candidates: list[tuple[str, str, Path]] = []
    for path in current_daily_report.parent.glob("datacenter_daily_*_full.md"):
        if path.resolve() == current_daily_report.resolve():
            continue
        match = DAILY_REPORT_FILENAME_RE.match(path.name)
        if match is None:
            continue
        candidate_signal_date = match.group("signal_date")
        if candidate_signal_date >= current_signal_date:
            continue
        candidate_metadata = _read_report_metadata(path)
        if not _daily_report_metadata_matches(current_metadata, candidate_metadata):
            continue
        candidates.append((candidate_signal_date, path.name, path))
    if not candidates:
        return None
    return sorted(candidates)[-1][2]


def _daily_report_metadata_matches(current: dict[str, str], candidate: dict[str, str]) -> bool:
    for key in ("signal_version", "ohlc_calc_version", "taxonomy_version"):
        if current.get(key) and candidate.get(key) != current[key]:
            return False
    return True


def _generate_decision_summary_report(
    *,
    current_daily_report: Path,
    current_rolling2_report: Path,
    current_rolling5_report: Path,
    current_rolling30_report: Path,
    output_path: Path,
    signal_date: str,
) -> dict[str, object]:
    required_sources = [
        current_daily_report,
        current_rolling2_report,
        current_rolling5_report,
        current_rolling30_report,
    ]
    missing_sources = [path for path in required_sources if not path.exists()]
    if missing_sources:
        reason = "missing_source_reports:" + ",".join(str(path) for path in missing_sources)
        print(f"WARNING decision_summary skipped: {reason}")
        return {
            "status": "SKIPPED",
            "execution_status": "SKIPPED",
            "skip_reason": reason,
            "error": "",
            "output_markdown": "",
            "previous_daily_report_path": "",
        }
    previous_daily_report = _find_previous_daily_report(
        current_daily_report=current_daily_report,
        current_signal_date=signal_date,
    )
    if previous_daily_report is None:
        reason = "missing_previous_daily"
        print(f"WARNING decision_summary skipped: {reason}")
        return {
            "status": "SKIPPED",
            "execution_status": "SKIPPED",
            "skip_reason": reason,
            "error": "",
            "output_markdown": "",
            "previous_daily_report_path": "",
        }
    try:
        build_decision_summary(
            current_daily=current_daily_report,
            previous_daily=previous_daily_report,
            current_rolling2=current_rolling2_report,
            current_rolling5=current_rolling5_report,
            current_rolling30=current_rolling30_report,
            output=output_path,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        print(f"WARNING decision_summary failed: {error}")
        return {
            "status": "FAILED",
            "execution_status": "FAILED",
            "skip_reason": "",
            "error": error,
            "output_markdown": "",
            "previous_daily_report_path": str(previous_daily_report),
        }
    print(f"SUMMARY decision_summary_report_path={output_path}")
    return {
        "status": "OK",
        "execution_status": "EXECUTED",
        "skip_reason": "",
        "error": "",
        "output_markdown": str(output_path),
        "previous_daily_report_path": str(previous_daily_report),
    }


def format_pipeline_final_summary_lines(summary: dict[str, object]) -> list[str]:
    lines: list[str] = []
    printed_keys: set[str] = set()
    for key in FINAL_PIPELINE_SUMMARY_ORDER:
        if key == "pipeline_status":
            continue
        if key in summary:
            lines.append(f"SUMMARY {key}={summary[key]}")
            printed_keys.add(key)
    for stage_key in PIPELINE_STAGE_KEYS:
        for suffix in (
            "status",
            "duration_seconds",
            "execution_status",
            "skip_reason",
        ):
            key = f"pipeline_stage.{stage_key}.{suffix}"
            if key in summary:
                lines.append(f"SUMMARY {key}={summary[key]}")
                printed_keys.add(key)
    for key, value in summary.items():
        if key not in printed_keys and key != "pipeline_status":
            lines.append(f"SUMMARY {key}={value}")
    if "pipeline_status" in summary:
        lines.append(f"SUMMARY pipeline_status={summary['pipeline_status']}")
    return lines


def _format_duration_seconds(value: float) -> str:
    return f"{value:.3f}"


def _build_stage_duration_summary_defaults() -> dict[str, str]:
    summary: dict[str, str] = {}
    for stage_key in PIPELINE_STAGE_KEYS:
        summary[f"pipeline_stage.{stage_key}.status"] = "SKIPPED"
        summary[f"pipeline_stage.{stage_key}.duration_seconds"] = "0.000"
        summary[f"pipeline_stage.{stage_key}.execution_status"] = "NOT_RUN"
    return summary


def _csv_or_none(values: list[str]) -> str:
    return ",".join(values) if values else "NONE"


def _stage2_plan_summary_defaults(*, enabled: bool) -> dict[str, object]:
    return {
        "stage2_incremental_enabled": "true" if enabled else "false",
        "stage2_plan": "NOT_REQUESTED" if not enabled else "UNKNOWN",
        "stage2_plan_mode": "LEGACY_FULL_RANGE" if not enabled else "UNKNOWN",
        "stage2_planned_materialization_start": "NONE",
        "stage2_planned_materialization_end": "NONE",
        "stage2_execution_status": "LEGACY_EXECUTION" if not enabled else "NOT_RUN",
        "stage2_attempted_dates": "NONE",
        "stage2_completed_dates": "NONE",
        "stage2_actual_materialized_start": "NONE",
        "stage2_actual_materialized_end": "NONE",
        "stage2_retry_required": "false",
        "downstream_dirty_start": "NONE",
        "downstream_dirty_end": "NONE",
        "downstream_incremental_stages": "NONE",
        "planner_skipped_stages": "NONE",
    }


def _stage2_plan_summary(plan: Stage2IncrementalPlan) -> dict[str, object]:
    downstream_stages = [
        str(item.stage_number)
        for item in plan.downstream_stage_plans
        if item.included_in_pilot_dirty_chain
    ]
    planned_start = plan.materialization_start or "NONE"
    planned_end = plan.materialization_end or "NONE"
    return {
        "stage2_incremental_enabled": "true",
        "stage2_plan": plan.reason_code,
        "stage2_plan_mode": plan.mode,
        "stage2_planned_materialization_start": planned_start,
        "stage2_planned_materialization_end": planned_end,
        "stage2_execution_status": "SKIPPED_BY_INCREMENTAL_PLAN" if plan.mode == "SKIP" else "PLANNED",
        "stage2_attempted_dates": "NONE",
        "stage2_completed_dates": "NONE",
        "stage2_actual_materialized_start": "NONE",
        "stage2_actual_materialized_end": "NONE",
        "stage2_retry_required": "false",
        "downstream_dirty_start": planned_start if plan.mode != "SKIP" else "NONE",
        "downstream_dirty_end": planned_end if plan.mode != "SKIP" else "NONE",
        "downstream_incremental_stages": ",".join(downstream_stages) if downstream_stages else "NONE",
        "planner_skipped_stages": (
            "ticker_swing_base_snapshots,group_swing_base_metrics,group_timing_states,"
            "group_overheat_risk,ticker_scanners"
            if plan.mode == "SKIP"
            else "NONE"
        ),
    }


def _stage2_success_summary(plan: Stage2IncrementalPlan) -> dict[str, object]:
    return {
        "stage2_execution_status": "EXECUTED",
        "stage2_attempted_dates": _csv_or_none(plan.output_dates),
        "stage2_completed_dates": _csv_or_none(plan.output_dates),
        "stage2_actual_materialized_start": plan.materialization_start or "NONE",
        "stage2_actual_materialized_end": plan.materialization_end or "NONE",
        "stage2_retry_required": "false",
    }


def _stage2_failed_summary(plan: Stage2IncrementalPlan) -> dict[str, object]:
    return {
        "stage2_execution_status": "FAILED",
        "stage2_attempted_dates": _csv_or_none(plan.output_dates),
        "stage2_completed_dates": "NONE",
        "stage2_actual_materialized_start": "NONE",
        "stage2_actual_materialized_end": "NONE",
        "stage2_retry_required": "true",
    }


def _format_technical_relevance_stage_summary_lines(
    summary: dict[str, object],
    *,
    status: str,
) -> list[str]:
    keys = (
        "run_id",
        "ticker_count",
        "start_date",
        "end_date",
        "observations_seen",
        "records_written",
        "relevant_count",
        "weak_context_count",
        "noise_count",
        "unknown_signal_count",
        "missing_dow_context_count",
        "missing_bar_index_count",
    )
    lines: list[str] = []
    for key in keys:
        if key in summary:
            lines.append(f"SUMMARY technical_relevance.{key}={summary[key]}")
    if "existing_run_reused" in summary:
        lines.append(f"SUMMARY technical_relevance.existing_run_reused={summary['existing_run_reused']}")
    if "skip_reason" in summary:
        lines.append(f"SUMMARY technical_relevance.skip_reason={summary['skip_reason']}")
    lines.append(f"SUMMARY technical_relevance.status={status}")
    return lines


def _run_cli_stage(main_func: Callable[[list[str]], int], argv: list[str]) -> dict[str, object] | None:
    exit_code = main_func(argv)
    if exit_code != 0:
        raise RuntimeError(f"Stage failed with exit code {exit_code}: {' '.join(argv)}")
    return None


def _write_stage_watermark(
    *,
    analysis_db: Path,
    builder: Callable[[dict[str, object] | None], dict[str, object]] | None,
    result: dict[str, object] | None,
    generated_at_utc: str | None,
    preserve_coverage_start: bool = False,
) -> None:
    if builder is None:
        return
    payload = builder(result)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        last_successful_at_utc=generated_at_utc,
        preserve_coverage_start=preserve_coverage_start,
        **payload,
    )


def _run_audit_stage(
    *,
    analysis_db: Path,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
    ohlc_calc_version: str,
    expected_ticker_count: int | None,
    expected_group_count: int | None,
    expected_synthetic_ohlc_count: int | None,
    weekly_window_size: int,
    strict: bool,
) -> dict[str, object]:
    result = load_swing_pipeline_audit(
        analysis_db_path=analysis_db,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        expected_ticker_count=expected_ticker_count,
        expected_group_count=expected_group_count,
        expected_synthetic_ohlc_count=expected_synthetic_ohlc_count,
        weekly_window_size=weekly_window_size,
        strict=strict,
    )
    for line in format_swing_pipeline_audit_summary_lines(result["summary"]):
        print(line)
    return result


def _run_automatic_technical_relevance_stage(
    *,
    analysis_db: Path,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
    generated_at_utc: str | None,
    profile_technical_relevance: bool = False,
) -> dict[str, object]:
    start_date, end_date = compute_datacenter_technical_relevance_date_range(signal_date)
    run_id = build_datacenter_technical_relevance_run_id(
        taxonomy_version=taxonomy_version,
        signal_date=signal_date,
    )
    profile = TechnicalSignalRelevanceProfile() if profile_technical_relevance else None
    with sqlite3.connect(analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        apply_technical_signal_relevance_migration(conn)
        tickers = load_datacenter_pipeline_technical_relevance_tickers(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
        )
        if not tickers:
            raise RuntimeError(
                "Automatic technical relevance ticker universe is empty for "
                f"signal_date={signal_date}, taxonomy_version={taxonomy_version}, signal_version={signal_version}"
            )
        if read_relevance_run(conn, run_id) is not None:
            result = {
                "summary": {
                    "run_id": run_id,
                    "ticker_count": len(tickers),
                    "start_date": start_date,
                    "end_date": end_date,
                    "observations_seen": 0,
                    "records_written": 0,
                    "relevant_count": 0,
                    "weak_context_count": 0,
                    "noise_count": 0,
                    "unknown_signal_count": 0,
                    "missing_dow_context_count": 0,
                    "missing_bar_index_count": 0,
                    "existing_run_reused": 1,
                    "skip_reason": "RUN_ID_ALREADY_EXISTS",
                }
            }
            return result
        try:
            batch_summary = run_technical_signal_relevance_for_tickers(
                conn,
                tickers,
                "1d",
                start_date,
                end_date,
                run_id,
                resolve_created_at_utc(generated_at_utc),
                profile=profile,
            )
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            error_text = str(exc)
            if "technical_signal_relevance_runs.run_id" not in error_text and "UNIQUE constraint failed" not in error_text:
                raise
            return {
                "summary": {
                    "run_id": run_id,
                    "ticker_count": len(tickers),
                    "start_date": start_date,
                    "end_date": end_date,
                    "observations_seen": 0,
                    "records_written": 0,
                    "relevant_count": 0,
                    "weak_context_count": 0,
                    "noise_count": 0,
                    "unknown_signal_count": 0,
                    "missing_dow_context_count": 0,
                    "missing_bar_index_count": 0,
                    "existing_run_reused": 1,
                    "skip_reason": "RUN_ID_ALREADY_EXISTS",
                }
            }
    result = {
        "summary": {
            "run_id": run_id,
            "ticker_count": len(tickers),
            "start_date": start_date,
            "end_date": end_date,
            "observations_seen": batch_summary.observations_seen,
            "records_written": batch_summary.records_written,
            "relevant_count": batch_summary.relevant_count,
            "weak_context_count": batch_summary.weak_context_count,
            "noise_count": batch_summary.noise_count,
            "unknown_signal_count": batch_summary.unknown_signal_count,
            "missing_dow_context_count": batch_summary.missing_dow_context_count,
            "missing_bar_index_count": batch_summary.missing_bar_index_count,
        }
    }
    if profile is not None:
        result["profile_summary"] = profile.to_summary_dict()
    return result


def _load_dry_run_technical_relevance_ticker_snapshot_count(
    *,
    analysis_db: Path,
    signal_date: str,
    taxonomy_version: str,
    signal_version: str,
) -> int:
    with sqlite3.connect(analysis_db) as conn:
        table_exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'dc_ticker_swing_signal_daily'
            """
        ).fetchone()
        if table_exists is None:
            return 0
        conn.row_factory = sqlite3.Row
        tickers = load_datacenter_pipeline_technical_relevance_tickers(
            conn,
            signal_date=signal_date,
            taxonomy_version=taxonomy_version,
            signal_version=signal_version,
        )
    return len(tickers)


def _run_daily_report_stage(
    *,
    analysis_db: Path,
    signal_date: str,
    signal_version: str,
    ohlc_calc_version: str,
    taxonomy_version: str,
    watchlist_file: Path,
    output_md: Path,
    output_csv: Path,
    include_taxonomy_listing: bool,
    technical_relevance_run_id: str | None = None,
) -> dict[str, object]:
    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date=signal_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        taxonomy_version=taxonomy_version,
        watchlist_file=watchlist_file,
        output_md=output_md,
        output_csv=output_csv,
        include_taxonomy_listing=include_taxonomy_listing,
        technical_relevance_run_id=technical_relevance_run_id,
    )
    for line in format_daily_swing_report_summary_lines(result["summary"]):
        print(line)
    return result


def _run_weekly_report_stage(
    *,
    analysis_db: Path,
    end_date: str,
    signal_version: str,
    ohlc_calc_version: str,
    taxonomy_version: str,
    window_size: int,
    watchlist_file: Path,
    output_md: Path,
    output_csv: Path,
    include_taxonomy_listing: bool,
    technical_relevance_run_id: str | None = None,
) -> dict[str, object]:
    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date=end_date,
        signal_version=signal_version,
        ohlc_calc_version=ohlc_calc_version,
        taxonomy_version=taxonomy_version,
        window_size=window_size,
        watchlist_file=watchlist_file,
        output_md=output_md,
        output_csv=output_csv,
        include_taxonomy_listing=include_taxonomy_listing,
        technical_relevance_run_id=technical_relevance_run_id,
    )
    for line in format_weekly_swing_report_summary_lines(result["summary"]):
        print(line)
    return result


def _build_timestamped_report_output_paths(
    *,
    output_dir: Path,
    prefix: str,
    signal_date: str,
    output_hhmm: str,
) -> tuple[Path, Path]:
    output_md = _timestamp_output_path(
        output_dir / f"{prefix}_{signal_date}_full.md",
        date_value=signal_date,
        hhmm=output_hhmm,
    )
    output_csv = _timestamp_output_path(
        output_dir / f"{prefix}_{signal_date}_full.csv",
        date_value=signal_date,
        hhmm=output_hhmm,
    )
    return output_md, output_csv


def _summary_lines_to_dict(lines: Sequence[str]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for line in lines:
        if not line.startswith("SUMMARY ") or "=" not in line:
            continue
        key, value = line[len("SUMMARY ") :].split("=", 1)
        summary[key] = value
    return summary


def _copy_generated_report_files(
    *,
    destination_dir: Path,
    source_paths: list[Path],
) -> dict[str, object]:
    missing_paths = [path for path in source_paths if not path.exists()]
    if missing_paths:
        missing_text = ", ".join(str(path) for path in missing_paths)
        raise RuntimeError(f"windows report copy stage missing source files: {missing_text}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied_paths: list[Path] = []
    for source_path in source_paths:
        destination_path = destination_dir / source_path.name
        copy2(source_path, destination_path)
        copied_paths.append(destination_path)
    return {
        "summary": {
            "destination_dir": str(destination_dir),
            "copied_file_count": len(copied_paths),
            "copied_files": ",".join(str(path) for path in copied_paths),
            "missing_files": "",
        }
    }


def run_datacenter_swing_pipeline(
    *,
    price_db: Path,
    analysis_db: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    market: str,
    signal_date: str,
    start_date: str,
    index_base_date: str,
    output_dir: Path,
    signal_version: str = DEFAULT_SIGNAL_VERSION,
    ohlc_calc_version: str = DEFAULT_OHLC_CALC_VERSION,
    expected_ticker_count: int | None = None,
    expected_group_count: int | None = None,
    expected_synthetic_ohlc_count: int | None = None,
    weekly_window_size: int = 20,
    watchlist_file: Path | None = None,
    no_taxonomy_listing: bool = False,
    technical_relevance_run_id: str | None = None,
    no_technical_relevance: bool = False,
    profile_technical_relevance: bool = False,
    profile_ticker_swing_snapshots: bool = False,
    skip_index: bool = False,
    skip_audit: bool = False,
    skip_reports: bool = False,
    audit_strict: bool = False,
    stage2_incremental: bool = False,
    stage2_overlap_trading_days: int = DEFAULT_STAGE2_INCREMENTAL_OVERLAP_TRADING_DAYS,
    windows_report_copy_enabled: bool = True,
    dry_run: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    total_start = perf_counter()
    if stage2_overlap_trading_days < 0:
        raise ValueError("stage2_overlap_trading_days must be zero or greater")
    if technical_relevance_run_id is not None and not technical_relevance_run_id.strip():
        raise ValueError("technical_relevance_run_id must be non-empty when provided")
    if no_technical_relevance and technical_relevance_run_id is not None:
        raise ValueError("--no-technical-relevance and --technical-relevance-run-id cannot be used together")
    technical_relevance_mode = (
        "disabled"
        if no_technical_relevance
        else ("existing_run" if technical_relevance_run_id is not None else "auto")
    )
    technical_relevance_enabled = technical_relevance_mode != "disabled"
    resolved_technical_relevance_run_id = (
        None if technical_relevance_mode == "disabled" else technical_relevance_run_id
    )
    technical_relevance_ticker_count = 0
    technical_relevance_ticker_count_status = (
        "DISABLED"
        if technical_relevance_mode == "disabled"
        else (
            "NOT_APPLICABLE_EXISTING_RUN"
            if technical_relevance_mode == "existing_run"
            else "NOT_AVAILABLE_DRY_RUN"
        )
    )
    technical_relevance_status = (
        "DISABLED"
        if technical_relevance_mode == "disabled"
        else ("SKIPPED_EXISTING_RUN" if technical_relevance_mode == "existing_run" else "DRY_RUN")
    )
    technical_relevance_existing_run_reused = 0
    technical_relevance_start_date = "NONE"
    technical_relevance_end_date = "NONE"
    if technical_relevance_mode == "auto":
        resolved_technical_relevance_run_id = build_datacenter_technical_relevance_run_id(
            taxonomy_version=taxonomy_version,
            signal_date=signal_date,
        )
        technical_relevance_start_date, technical_relevance_end_date = (
            compute_datacenter_technical_relevance_date_range(signal_date)
        )
        if dry_run:
            technical_relevance_ticker_count = _load_dry_run_technical_relevance_ticker_snapshot_count(
                analysis_db=analysis_db,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                signal_version=signal_version,
            )
            if technical_relevance_ticker_count > 0:
                technical_relevance_ticker_count_status = "EXISTING_DB_SNAPSHOT"
    selected_watchlist_file = Path(DEFAULT_WATCHLIST_FILE) if watchlist_file is None else Path(watchlist_file)
    stage_duration_summary = _build_stage_duration_summary_defaults()
    technical_relevance_profile_summary: dict[str, object] = {}
    ticker_swing_snapshot_profile_summary: dict[str, object] = {}
    if profile_technical_relevance and technical_relevance_mode != "auto":
        technical_relevance_profile_summary["technical_relevance_profile.status"] = technical_relevance_status
    stage2_plan: Stage2IncrementalPlan | None = None
    stage2_summary: dict[str, object] = _stage2_plan_summary_defaults(enabled=stage2_incremental)
    stage2_start_date = start_date
    stage2_end_date = signal_date
    stage2_chain_start_date = start_date
    stage2_chain_end_date = signal_date
    if stage2_incremental:
        stage2_plan = build_stage2_incremental_plan(
            analysis_db_path=analysis_db,
            price_db_path=price_db,
            taxonomy_csv_path=taxonomy_csv,
            taxonomy_version=taxonomy_version,
            market=market,
            requested_start=start_date,
            requested_end=signal_date,
            signal_version=signal_version,
            overlap_trading_days=stage2_overlap_trading_days,
        )
        stage2_summary = _stage2_plan_summary(stage2_plan)
        if stage2_plan.mode != "SKIP":
            if stage2_plan.materialization_start is None or stage2_plan.materialization_end is None:
                raise ValueError("Stage 2 incremental plan is missing materialization range")
            stage2_start_date = stage2_plan.materialization_start
            stage2_end_date = stage2_plan.materialization_end
            stage2_chain_start_date = stage2_plan.materialization_start
            stage2_chain_end_date = stage2_plan.materialization_end
    output_hhmm = _resolve_output_timestamp_hhmm(generated_at_utc)
    daily_output_md, daily_output_csv = _build_timestamped_report_output_paths(
        output_dir=output_dir,
        prefix="datacenter_daily",
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )
    weekly_output_md, weekly_output_csv = _build_timestamped_report_output_paths(
        output_dir=output_dir,
        prefix="datacenter_weekly",
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )
    rolling_30_output_md, rolling_30_output_csv = _build_timestamped_report_output_paths(
        output_dir=output_dir,
        prefix="datacenter_rolling_30",
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )
    rolling_5_output_md, rolling_5_output_csv = _build_timestamped_report_output_paths(
        output_dir=output_dir,
        prefix="datacenter_rolling_5",
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )
    rolling_2_output_md, rolling_2_output_csv = _build_timestamped_report_output_paths(
        output_dir=output_dir,
        prefix="datacenter_rolling_2",
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )
    decision_summary_output_md = _build_decision_summary_output_path(
        output_dir=output_dir,
        signal_date=signal_date,
        output_hhmm=output_hhmm,
    )

    stages: list[PipelineStage] = []
    if not skip_index:
        index_argv = [
            "--ohlcv-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            taxonomy_version,
            "--market",
            market,
            "--index-base-date",
            index_base_date,
            "--start-date",
            index_base_date,
            "--end-date",
            signal_date,
            "--write-mode",
            "replace-range",
        ]
        stages.append(
            PipelineStage(
                stage_key="datacenter_base_index",
                heading="Datacenter base index",
                argv=index_argv,
                runner=lambda argv=index_argv: _run_cli_stage(run_datacenter_indices_main, argv),
                watermark_builder=lambda _result: {
                    "component_name": "GROUP_INDEX",
                    "taxonomy_version": taxonomy_version,
                    "market": market,
                    "signal_version": "",
                    "calc_version": "",
                    "start_date": index_base_date,
                    "end_date": signal_date,
                    "row_count": None,
                    "status": "OK",
                },
            )
        )

    ticker_base_argv = [
        "--price-db",
        str(price_db),
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--start-date",
        stage2_start_date,
        "--end-date",
        stage2_end_date,
        "--market",
        market,
        "--signal-version",
        signal_version,
        "--write-mode",
        "replace-date",
    ]
    if profile_ticker_swing_snapshots:
        ticker_base_argv.append("--profile")
    stages.append(
        PipelineStage(
            stage_key="ticker_swing_base_snapshots",
            heading="Ticker swing base snapshots",
            argv=ticker_base_argv,
            runner=lambda argv=ticker_base_argv: _run_cli_stage(run_datacenter_ticker_swing_signals_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "TICKER_SWING_BASE",
                "taxonomy_version": taxonomy_version,
                "market": market,
                "signal_version": signal_version,
                "calc_version": "",
                "start_date": stage2_start_date,
                "end_date": stage2_end_date,
                "row_count": None,
                "status": "OK",
            },
            preserve_watermark_coverage_start=True,
            skip_status=(
                "SKIPPED_BY_INCREMENTAL_PLAN"
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
            skip_reason=(
                str(stage2_plan.reason_code)
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
        )
    )

    group_base_argv = [
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--start-date",
        stage2_chain_start_date,
        "--end-date",
        stage2_chain_end_date,
        "--signal-version",
        signal_version,
        "--write-mode",
        "replace-date",
    ]
    stages.append(
        PipelineStage(
            stage_key="group_swing_base_metrics",
            heading="Group swing base metrics",
            argv=group_base_argv,
            runner=lambda argv=group_base_argv: _run_cli_stage(run_datacenter_group_swing_signals_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "GROUP_SWING_BASE",
                "taxonomy_version": taxonomy_version,
                "market": "",
                "signal_version": signal_version,
                "calc_version": "",
                "start_date": stage2_chain_start_date,
                "end_date": stage2_chain_end_date,
                "row_count": None,
                "status": "OK",
            },
            preserve_watermark_coverage_start=True,
            skip_status=(
                "SKIPPED_BY_INCREMENTAL_PLAN"
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
            skip_reason=(
                str(stage2_plan.reason_code)
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
        )
    )

    synthetic_base_argv = [
        "--price-db",
        str(price_db),
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
        "--market",
        market,
        "--calc-version",
        ohlc_calc_version,
        "--write-mode",
        "replace-range",
    ]
    stages.append(
        PipelineStage(
            stage_key="synthetic_ohlc_base",
            heading="Synthetic OHLC base",
            argv=synthetic_base_argv,
            runner=lambda argv=synthetic_base_argv: _run_cli_stage(run_datacenter_group_synthetic_ohlc_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "SYNTHETIC_OHLC_BASE",
                "taxonomy_version": taxonomy_version,
                "market": market,
                "signal_version": "",
                "calc_version": ohlc_calc_version,
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    relative_argv = [
        "--price-db",
        str(price_db),
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
        "--market",
        market,
        "--calc-version",
        ohlc_calc_version,
        "--write-mode",
        "replace-relative-range",
        "--relative-only",
    ]
    stages.append(
        PipelineStage(
            stage_key="relative_ohlc20",
            heading="Relative OHLC20",
            argv=relative_argv,
            runner=lambda argv=relative_argv: _run_cli_stage(run_datacenter_group_synthetic_ohlc_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "SYNTHETIC_OHLC_RELATIVE",
                "taxonomy_version": taxonomy_version,
                "market": market,
                "signal_version": "",
                "calc_version": ohlc_calc_version,
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    structure_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
        "--calc-version",
        ohlc_calc_version,
        "--write-mode",
        "replace-structure-range",
        "--structure-only",
    ]
    stages.append(
        PipelineStage(
            stage_key="group_structure_bos_reset",
            heading="Group structure / BOS / RESET",
            argv=structure_argv,
            runner=lambda argv=structure_argv: _run_cli_stage(run_datacenter_group_synthetic_ohlc_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "SYNTHETIC_OHLC_STRUCTURE",
                "taxonomy_version": taxonomy_version,
                "market": market,
                "signal_version": "",
                "calc_version": ohlc_calc_version,
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    timing_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        stage2_chain_start_date,
        "--end-date",
        stage2_chain_end_date,
        "--signal-version",
        signal_version,
        "--write-mode",
        "replace-timing-range",
        "--timing-only",
    ]
    stages.append(
        PipelineStage(
            stage_key="group_timing_states",
            heading="Group timing states",
            argv=timing_argv,
            runner=lambda argv=timing_argv: _run_cli_stage(run_datacenter_group_swing_signals_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "GROUP_TIMING",
                "taxonomy_version": taxonomy_version,
                "market": "",
                "signal_version": signal_version,
                "calc_version": "",
                "start_date": stage2_chain_start_date,
                "end_date": stage2_chain_end_date,
                "row_count": None,
                "status": "OK",
            },
            preserve_watermark_coverage_start=True,
            skip_status=(
                "SKIPPED_BY_INCREMENTAL_PLAN"
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
            skip_reason=(
                str(stage2_plan.reason_code)
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
        )
    )

    overheat_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        stage2_chain_start_date,
        "--end-date",
        stage2_chain_end_date,
        "--signal-version",
        signal_version,
        "--write-mode",
        "replace-overheat-range",
        "--overheat-only",
    ]
    stages.append(
        PipelineStage(
            stage_key="group_overheat_risk",
            heading="Group overheat risk",
            argv=overheat_argv,
            runner=lambda argv=overheat_argv: _run_cli_stage(run_datacenter_group_swing_signals_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "GROUP_OVERHEAT",
                "taxonomy_version": taxonomy_version,
                "market": "",
                "signal_version": signal_version,
                "calc_version": "",
                "start_date": stage2_chain_start_date,
                "end_date": stage2_chain_end_date,
                "row_count": None,
                "status": "OK",
            },
            preserve_watermark_coverage_start=True,
            skip_status=(
                "SKIPPED_BY_INCREMENTAL_PLAN"
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
            skip_reason=(
                str(stage2_plan.reason_code)
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
        )
    )

    scanner_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        stage2_chain_start_date,
        "--end-date",
        stage2_chain_end_date,
        "--signal-version",
        signal_version,
        "--taxonomy-version",
        taxonomy_version,
        "--write-mode",
        "replace-scanner-range",
        "--scanner-only",
    ]
    stages.append(
        PipelineStage(
            stage_key="ticker_scanners",
            heading="Ticker scanners",
            argv=scanner_argv,
            runner=lambda argv=scanner_argv: _run_cli_stage(run_datacenter_ticker_swing_signals_main, argv),
            watermark_builder=lambda _result: {
                "component_name": "TICKER_SCANNER",
                "taxonomy_version": taxonomy_version,
                "market": "",
                "signal_version": signal_version,
                "calc_version": "",
                "start_date": stage2_chain_start_date,
                "end_date": stage2_chain_end_date,
                "row_count": None,
                "status": "OK",
            },
            preserve_watermark_coverage_start=True,
            skip_status=(
                "SKIPPED_BY_INCREMENTAL_PLAN"
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
            skip_reason=(
                str(stage2_plan.reason_code)
                if stage2_plan is not None and stage2_plan.mode == "SKIP"
                else None
            ),
        )
    )

    if not skip_audit:
        audit_argv = [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            signal_date,
            "--taxonomy-version",
            taxonomy_version,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
        ]
        if expected_ticker_count is not None:
            audit_argv.extend(["--expected-ticker-count", str(expected_ticker_count)])
        if expected_group_count is not None:
            audit_argv.extend(["--expected-group-count", str(expected_group_count)])
        if expected_synthetic_ohlc_count is not None:
            audit_argv.extend(["--expected-synthetic-ohlc-count", str(expected_synthetic_ohlc_count)])
        audit_argv.extend(["--weekly-window-size", str(weekly_window_size)])
        if audit_strict:
            audit_argv.append("--strict")
        stages.append(
            PipelineStage(
                stage_key="pipeline_audit",
                heading="Pipeline audit",
                argv=audit_argv,
                runner=lambda: _run_audit_stage(
                    analysis_db=analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    expected_ticker_count=expected_ticker_count,
                    expected_group_count=expected_group_count,
                    expected_synthetic_ohlc_count=expected_synthetic_ohlc_count,
                    weekly_window_size=weekly_window_size,
                    strict=audit_strict,
                ),
                watermark_builder=lambda result: {
                    "component_name": "PIPELINE_AUDIT",
                    "taxonomy_version": taxonomy_version,
                    "market": "",
                    "signal_version": signal_version,
                    "calc_version": ohlc_calc_version,
                    "start_date": signal_date,
                    "end_date": signal_date,
                    "row_count": None,
                    "status": str(result["summary"]["validation_status"]),
                },
            )
        )

    if technical_relevance_mode == "auto":
        technical_relevance_argv = [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            signal_date,
            "--taxonomy-version",
            taxonomy_version,
            "--signal-version",
            signal_version,
        ]
        if profile_technical_relevance:
            technical_relevance_argv.append("--profile-technical-relevance")
        stages.append(
            PipelineStage(
                stage_key="automatic_technical_relevance",
                heading="Automatic technical relevance",
                argv=technical_relevance_argv,
                runner=lambda: _run_automatic_technical_relevance_stage(
                    analysis_db=analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    signal_version=signal_version,
                    generated_at_utc=generated_at_utc,
                    profile_technical_relevance=profile_technical_relevance,
                ),
            )
        )

    if not skip_reports:
        daily_argv = [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            signal_date,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
            "--taxonomy-version",
            taxonomy_version,
            "--watchlist-file",
            str(selected_watchlist_file),
            "--output-md",
            str(output_dir / f"datacenter_daily_{signal_date}_full.md"),
            "--output-csv",
            str(output_dir / f"datacenter_daily_{signal_date}_full.csv"),
        ]
        weekly_argv = [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            signal_date,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
            "--taxonomy-version",
            taxonomy_version,
            "--window-size",
            str(weekly_window_size),
            "--watchlist-file",
            str(selected_watchlist_file),
            "--output-md",
            str(output_dir / f"datacenter_weekly_{signal_date}_full.md"),
            "--output-csv",
            str(output_dir / f"datacenter_weekly_{signal_date}_full.csv"),
        ]
        rolling_30_argv = [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            signal_date,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
            "--taxonomy-version",
            taxonomy_version,
            "--window-size",
            "30",
            "--watchlist-file",
            str(selected_watchlist_file),
            "--output-md",
            str(output_dir / f"datacenter_rolling_30_{signal_date}_full.md"),
            "--output-csv",
            str(output_dir / f"datacenter_rolling_30_{signal_date}_full.csv"),
        ]
        rolling_5_argv = [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            signal_date,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
            "--taxonomy-version",
            taxonomy_version,
            "--window-size",
            "5",
            "--watchlist-file",
            str(selected_watchlist_file),
            "--output-md",
            str(output_dir / f"datacenter_rolling_5_{signal_date}_full.md"),
            "--output-csv",
            str(output_dir / f"datacenter_rolling_5_{signal_date}_full.csv"),
        ]
        rolling_2_argv = [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            signal_date,
            "--signal-version",
            signal_version,
            "--ohlc-calc-version",
            ohlc_calc_version,
            "--taxonomy-version",
            taxonomy_version,
            "--window-size",
            "2",
            "--watchlist-file",
            str(selected_watchlist_file),
            "--output-md",
            str(output_dir / f"datacenter_rolling_2_{signal_date}_full.md"),
            "--output-csv",
            str(output_dir / f"datacenter_rolling_2_{signal_date}_full.csv"),
        ]
        if no_taxonomy_listing:
            daily_argv.append("--no-taxonomy-listing")
            weekly_argv.append("--no-taxonomy-listing")
            rolling_30_argv.append("--no-taxonomy-listing")
            rolling_5_argv.append("--no-taxonomy-listing")
            rolling_2_argv.append("--no-taxonomy-listing")
        if resolved_technical_relevance_run_id is not None:
            daily_argv.extend(["--technical-relevance-run-id", resolved_technical_relevance_run_id])
            weekly_argv.extend(["--technical-relevance-run-id", resolved_technical_relevance_run_id])
            rolling_30_argv.extend(["--technical-relevance-run-id", resolved_technical_relevance_run_id])
            rolling_5_argv.extend(["--technical-relevance-run-id", resolved_technical_relevance_run_id])
            rolling_2_argv.extend(["--technical-relevance-run-id", resolved_technical_relevance_run_id])
        stages.append(
            PipelineStage(
                stage_key="daily_report",
                heading="Daily report",
                argv=daily_argv,
                runner=lambda: _run_daily_report_stage(
                    analysis_db=analysis_db,
                    signal_date=signal_date,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    taxonomy_version=taxonomy_version,
                    watchlist_file=selected_watchlist_file,
                    output_md=daily_output_md,
                    output_csv=daily_output_csv,
                    include_taxonomy_listing=not no_taxonomy_listing,
                    technical_relevance_run_id=resolved_technical_relevance_run_id,
                ),
                watermark_builder=lambda _result: {
                    "component_name": "DAILY_REPORT",
                    "taxonomy_version": taxonomy_version,
                    "market": "",
                    "signal_version": signal_version,
                    "calc_version": ohlc_calc_version,
                    "start_date": signal_date,
                    "end_date": signal_date,
                    "row_count": None,
                    "status": "OK",
                },
            )
        )
        stages.append(
            PipelineStage(
                stage_key="rolling_30_report",
                heading="Rolling 30 report",
                argv=rolling_30_argv,
                runner=lambda: _run_weekly_report_stage(
                    analysis_db=analysis_db,
                    end_date=signal_date,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    taxonomy_version=taxonomy_version,
                    window_size=30,
                    watchlist_file=selected_watchlist_file,
                    output_md=rolling_30_output_md,
                    output_csv=rolling_30_output_csv,
                    include_taxonomy_listing=not no_taxonomy_listing,
                    technical_relevance_run_id=resolved_technical_relevance_run_id,
                ),
                watermark_builder=lambda result: {
                    "component_name": "ROLLING_REPORT_30",
                    "taxonomy_version": taxonomy_version,
                    "market": "",
                    "signal_version": signal_version,
                    "calc_version": ohlc_calc_version,
                    "start_date": str(result["summary"].get("window_start_date", signal_date)),
                    "end_date": signal_date,
                    "row_count": None,
                    "status": "OK",
                },
            )
        )
        stages.append(
            PipelineStage(
                stage_key="rolling_5_report",
                heading="Rolling 5 report",
                argv=rolling_5_argv,
                runner=lambda: _run_weekly_report_stage(
                    analysis_db=analysis_db,
                    end_date=signal_date,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    taxonomy_version=taxonomy_version,
                    window_size=5,
                    watchlist_file=selected_watchlist_file,
                    output_md=rolling_5_output_md,
                    output_csv=rolling_5_output_csv,
                    include_taxonomy_listing=not no_taxonomy_listing,
                    technical_relevance_run_id=resolved_technical_relevance_run_id,
                ),
                watermark_builder=lambda result: {
                    "component_name": "ROLLING_REPORT_5",
                    "taxonomy_version": taxonomy_version,
                    "market": "",
                    "signal_version": signal_version,
                    "calc_version": ohlc_calc_version,
                    "start_date": str(result["summary"].get("window_start_date", signal_date)),
                    "end_date": signal_date,
                    "row_count": None,
                    "status": "OK",
                },
            )
        )
        stages.append(
            PipelineStage(
                stage_key="rolling_2_report",
                heading="Rolling 2 report",
                argv=rolling_2_argv,
                runner=lambda: _run_weekly_report_stage(
                    analysis_db=analysis_db,
                    end_date=signal_date,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    taxonomy_version=taxonomy_version,
                    window_size=2,
                    watchlist_file=selected_watchlist_file,
                    output_md=rolling_2_output_md,
                    output_csv=rolling_2_output_csv,
                    include_taxonomy_listing=not no_taxonomy_listing,
                    technical_relevance_run_id=resolved_technical_relevance_run_id,
                ),
                watermark_builder=lambda result: {
                    "component_name": "ROLLING_REPORT_2",
                    "taxonomy_version": taxonomy_version,
                    "market": "",
                    "signal_version": signal_version,
                    "calc_version": ohlc_calc_version,
                    "start_date": str(result["summary"].get("window_start_date", signal_date)),
                    "end_date": signal_date,
                    "row_count": None,
                    "status": "OK",
                },
            )
        )
        windows_report_copy_argv = [
            "--destination-dir",
            str(WINDOWS_REPORT_COPY_DIR),
            "--source-report",
            str(daily_output_md),
            "--source-report",
            str(daily_output_csv),
            "--source-report",
            str(rolling_30_output_md),
            "--source-report",
            str(rolling_30_output_csv),
            "--source-report",
            str(rolling_5_output_md),
            "--source-report",
            str(rolling_5_output_csv),
            "--source-report",
            str(rolling_2_output_md),
            "--source-report",
            str(rolling_2_output_csv),
        ]
        if windows_report_copy_enabled:
            stages.append(
                PipelineStage(
                    stage_key="windows_report_copy",
                    heading="Windows report copy",
                    argv=windows_report_copy_argv,
                    runner=lambda: _copy_generated_report_files(
                        destination_dir=WINDOWS_REPORT_COPY_DIR,
                        source_paths=[
                            Path(daily_report_path),
                            Path(daily_report_csv_path),
                            Path(rolling_30_report_path),
                            Path(rolling_30_report_csv_path),
                            Path(rolling_5_report_path),
                            Path(rolling_5_report_csv_path),
                            Path(rolling_2_report_path),
                            Path(rolling_2_report_csv_path),
                        ]
                        + ([Path(decision_summary_report_path)] if decision_summary_report_path else []),
                    ),
                )
            )

    if dry_run:
        if profile_technical_relevance:
            technical_relevance_profile_summary["technical_relevance_profile.status"] = (
                "DRY_RUN" if technical_relevance_mode == "auto" else technical_relevance_status
            )
        if profile_ticker_swing_snapshots:
            ticker_swing_snapshot_profile_summary["ticker_swing_snapshot_profile.status"] = "DRY_RUN"
        for index, stage in enumerate(stages, start=1):
            if stage.skip_status is not None:
                stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "SKIPPED"
                stage_duration_summary[f"pipeline_stage.{stage.stage_key}.execution_status"] = stage.skip_status
                if stage.skip_reason is not None:
                    stage_duration_summary[f"pipeline_stage.{stage.stage_key}.skip_reason"] = stage.skip_reason
            else:
                stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "DRY_RUN"
                stage_duration_summary[f"pipeline_stage.{stage.stage_key}.execution_status"] = "DRY_RUN"
            print(f"=== Stage {index}/{len(stages)}: {stage.heading} ===")
            print("PLAN " + " ".join(stage.argv))
        return {
            "summary": {
                "pipeline_signal_date": signal_date,
                "pipeline_start_date": start_date,
                "pipeline_index_base_date": index_base_date,
                "pipeline_taxonomy_version": taxonomy_version,
                "pipeline_signal_version": signal_version,
                "pipeline_ohlc_calc_version": ohlc_calc_version,
                "technical_relevance.enabled": "true" if technical_relevance_enabled else "false",
                "technical_relevance.mode": technical_relevance_mode,
                "technical_relevance.run_id": resolved_technical_relevance_run_id or "NONE",
                "technical_relevance.ticker_count": technical_relevance_ticker_count,
                "technical_relevance.ticker_count_status": technical_relevance_ticker_count_status,
                "technical_relevance.start_date": technical_relevance_start_date,
                "technical_relevance.end_date": technical_relevance_end_date,
                "technical_relevance.status": technical_relevance_status,
                "technical_relevance_run_id": resolved_technical_relevance_run_id or "NONE",
                "pipeline_output_dir": str(output_dir),
                "windows_report_copy.enabled": "true" if windows_report_copy_enabled else "false",
                "windows_report_copy.destination_dir": str(WINDOWS_REPORT_COPY_DIR),
                "windows_report_copy.execution_status": (
                    "DRY_RUN" if windows_report_copy_enabled and not skip_reports else "SKIPPED"
                ),
                "windows_report_copy.skip_reason": (
                    "" if windows_report_copy_enabled and not skip_reports else "disabled"
                ),
                "pipeline_stage_count": len(stages),
                "pipeline_completed_stage_count": 0,
                "pipeline.total_duration_seconds": _format_duration_seconds(perf_counter() - total_start),
                "audit_validation_status": "SKIPPED" if skip_audit else "DRY_RUN",
                "daily_report_path": "",
                "daily_report_csv_path": "",
                "weekly_report_path": "",
                "weekly_report_csv_path": "",
                "rolling_30_report_path": "",
                "rolling_30_report_csv_path": "",
                "rolling_5_report_path": "",
                "rolling_5_report_csv_path": "",
                "rolling_2_report_path": "",
                "rolling_2_report_csv_path": "",
                "decision_summary_report_path": "",
                "decision_summary.status": "SKIPPED",
                "decision_summary.execution_status": "DRY_RUN",
                "decision_summary.skip_reason": "dry_run",
                "decision_summary.error": "",
                "pipeline_status": "DRY_RUN",
                **stage_duration_summary,
                **stage2_summary,
                **ticker_swing_snapshot_profile_summary,
                **technical_relevance_profile_summary,
            }
        }

    completed_stage_count = 0
    audit_validation_status = "SKIPPED" if skip_audit else "UNKNOWN"
    daily_report_path = ""
    daily_report_csv_path = ""
    weekly_report_path = ""
    weekly_report_csv_path = ""
    rolling_30_report_path = ""
    rolling_30_report_csv_path = ""
    rolling_5_report_path = ""
    rolling_5_report_csv_path = ""
    rolling_2_report_path = ""
    rolling_2_report_csv_path = ""
    decision_summary_report_path = ""
    decision_summary_status = "SKIPPED" if skip_reports else "NOT_RUN"
    decision_summary_execution_status = "SKIPPED" if skip_reports else "NOT_RUN"
    decision_summary_skip_reason = "reports_skipped" if skip_reports else ""
    decision_summary_error = ""
    daily_report_result: dict[str, object] | None = None
    rolling_30_report_result: dict[str, object] | None = None
    rolling_5_report_result: dict[str, object] | None = None
    rolling_2_report_result: dict[str, object] | None = None
    if not skip_reports:
        output_dir.mkdir(parents=True, exist_ok=True)

    for index, stage in enumerate(stages, start=1):
        if stage.heading == "Daily report" and audit_validation_status == "FAIL":
            break
        if stage.heading == "Weekly swing report" and audit_validation_status == "FAIL":
            break
        print(f"=== Stage {index}/{len(stages)}: {stage.heading} ===")
        if stage.skip_status is not None:
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "SKIPPED"
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.execution_status"] = stage.skip_status
            if stage.skip_reason is not None:
                stage_duration_summary[f"pipeline_stage.{stage.stage_key}.skip_reason"] = stage.skip_reason
                print(f"SUMMARY pipeline_stage.{stage.stage_key}.skip_reason={stage.skip_reason}")
            print(f"SUMMARY pipeline_stage.{stage.stage_key}.execution_status={stage.skip_status}")
            continue
        stage_start = perf_counter()
        try:
            result = stage.runner()
        except Exception:
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "FAILED"
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.execution_status"] = "FAILED"
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.duration_seconds"] = _format_duration_seconds(
                perf_counter() - stage_start
            )
            if stage2_plan is not None and stage.stage_key == "ticker_swing_base_snapshots":
                stage2_summary.update(_stage2_failed_summary(stage2_plan))
                for key, value in stage2_summary.items():
                    if key.startswith("stage2_"):
                        print(f"SUMMARY {key}={value}")
            raise
        stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "OK"
        stage_duration_summary[f"pipeline_stage.{stage.stage_key}.execution_status"] = "EXECUTED"
        stage_duration_summary[f"pipeline_stage.{stage.stage_key}.duration_seconds"] = _format_duration_seconds(
            perf_counter() - stage_start
        )
        if stage2_plan is not None and stage.stage_key == "ticker_swing_base_snapshots":
            stage2_summary.update(_stage2_success_summary(stage2_plan))
        _write_stage_watermark(
            analysis_db=analysis_db,
            builder=stage.watermark_builder,
            result=result,
            generated_at_utc=generated_at_utc,
            preserve_coverage_start=stage.preserve_watermark_coverage_start,
        )
        completed_stage_count += 1
        if stage.heading == "Pipeline audit":
            audit_validation_status = str(result["summary"]["validation_status"])
            if audit_validation_status == "FAIL":
                return {
                    "summary": {
                        "pipeline_signal_date": signal_date,
                        "pipeline_start_date": start_date,
                        "pipeline_index_base_date": index_base_date,
                        "pipeline_taxonomy_version": taxonomy_version,
                        "pipeline_signal_version": signal_version,
                        "pipeline_ohlc_calc_version": ohlc_calc_version,
                        "technical_relevance.enabled": "true" if technical_relevance_enabled else "false",
                        "technical_relevance.mode": technical_relevance_mode,
                        "technical_relevance.run_id": resolved_technical_relevance_run_id or "NONE",
                        "technical_relevance.ticker_count": technical_relevance_ticker_count,
                        "technical_relevance.ticker_count_status": technical_relevance_ticker_count_status,
                        "technical_relevance.start_date": technical_relevance_start_date,
                        "technical_relevance.end_date": technical_relevance_end_date,
                        "technical_relevance.status": technical_relevance_status,
                        "technical_relevance_run_id": resolved_technical_relevance_run_id or "NONE",
                        "pipeline_output_dir": str(output_dir),
                        "windows_report_copy.enabled": "true" if windows_report_copy_enabled else "false",
                        "windows_report_copy.destination_dir": str(WINDOWS_REPORT_COPY_DIR),
                        "windows_report_copy.execution_status": (
                            "EXECUTED" if windows_report_copy_enabled and not skip_reports else "SKIPPED"
                        ),
                        "windows_report_copy.skip_reason": (
                            "" if windows_report_copy_enabled and not skip_reports else "disabled"
                        ),
                        "pipeline_stage_count": len(stages),
                        "pipeline_completed_stage_count": completed_stage_count,
                        "pipeline.total_duration_seconds": _format_duration_seconds(perf_counter() - total_start),
                        "audit_validation_status": audit_validation_status,
                        "daily_report_path": "",
                        "daily_report_csv_path": "",
                        "weekly_report_path": "",
                        "weekly_report_csv_path": "",
                        "rolling_30_report_path": "",
                        "rolling_30_report_csv_path": "",
                        "rolling_5_report_path": "",
                        "rolling_5_report_csv_path": "",
                        "rolling_2_report_path": "",
                        "rolling_2_report_csv_path": "",
                        "decision_summary_report_path": "",
                        "decision_summary.status": "SKIPPED",
                        "decision_summary.execution_status": "SKIPPED",
                        "decision_summary.skip_reason": "audit_failed_before_reports_completed",
                        "decision_summary.error": "",
                        "pipeline_status": "FAIL",
                        **stage_duration_summary,
                        **stage2_summary,
                        **ticker_swing_snapshot_profile_summary,
                        **technical_relevance_profile_summary,
                    }
                }
        elif stage.heading == "Automatic technical relevance":
            automatic_status = (
                "SKIPPED_EXISTING_RUN"
                if int(result["summary"].get("existing_run_reused", 0)) == 1
                else "OK"
            )
            for line in _format_technical_relevance_stage_summary_lines(result["summary"], status=automatic_status):
                print(line)
            if profile_technical_relevance and "profile_summary" in result:
                for line in format_technical_relevance_profile_summary_lines(result["profile_summary"]):
                    print(line)
            resolved_technical_relevance_run_id = str(result["summary"]["run_id"])
            technical_relevance_ticker_count = int(result["summary"]["ticker_count"])
            technical_relevance_existing_run_reused = int(result["summary"].get("existing_run_reused", 0))
            technical_relevance_ticker_count_status = (
                "EXISTING_RUN_REUSED" if technical_relevance_existing_run_reused == 1 else "ACTUAL_RUN"
            )
            technical_relevance_status = automatic_status
            technical_relevance_start_date = str(result["summary"]["start_date"])
            technical_relevance_end_date = str(result["summary"]["end_date"])
        elif stage.heading == "Daily report":
            daily_report_result = result
            daily_report_path = str(result["summary"]["output_markdown"])
            daily_report_csv_path = str(result["summary"]["output_csv"])
        elif stage.heading == "Weekly swing report":
            weekly_report_path = str(result["summary"]["output_markdown"])
            weekly_report_csv_path = str(result["summary"]["output_csv"])
        elif stage.heading == "Rolling 30 report":
            rolling_30_report_result = result
            rolling_30_report_path = str(result["summary"]["output_markdown"])
            rolling_30_report_csv_path = str(result["summary"]["output_csv"])
        elif stage.heading == "Rolling 5 report":
            rolling_5_report_result = result
            rolling_5_report_path = str(result["summary"]["output_markdown"])
            rolling_5_report_csv_path = str(result["summary"]["output_csv"])
        elif stage.heading == "Rolling 2 report":
            rolling_2_report_result = result
            rolling_2_report_path = str(result["summary"]["output_markdown"])
            rolling_2_report_csv_path = str(result["summary"]["output_csv"])
            decision_summary_result = _generate_decision_summary_report(
                current_daily_report=Path(daily_report_path),
                current_rolling2_report=Path(rolling_2_report_path),
                current_rolling5_report=Path(rolling_5_report_path),
                current_rolling30_report=Path(rolling_30_report_path),
                output_path=decision_summary_output_md,
                signal_date=signal_date,
            )
            decision_summary_report_path = str(decision_summary_result["output_markdown"])
            decision_summary_status = str(decision_summary_result["status"])
            decision_summary_execution_status = str(decision_summary_result["execution_status"])
            decision_summary_skip_reason = str(decision_summary_result["skip_reason"])
            decision_summary_error = str(decision_summary_result["error"])
        elif stage.heading == "Windows report copy":
            copy_summary = result["summary"]
            for key, value in copy_summary.items():
                print(f"SUMMARY windows_report_copy.{key}={value}")

    pipeline_status = "OK"
    if audit_validation_status == "WARN":
        pipeline_status = "WARN"
    if audit_validation_status == "FAIL":
        pipeline_status = "FAIL"
    if pipeline_status == "OK" and decision_summary_status == "FAILED":
        pipeline_status = "WARN"

    return {
        "summary": {
            "pipeline_signal_date": signal_date,
            "pipeline_start_date": start_date,
            "pipeline_index_base_date": index_base_date,
            "pipeline_taxonomy_version": taxonomy_version,
            "pipeline_signal_version": signal_version,
            "pipeline_ohlc_calc_version": ohlc_calc_version,
            "technical_relevance.enabled": "true" if technical_relevance_enabled else "false",
            "technical_relevance.mode": technical_relevance_mode,
            "technical_relevance.run_id": resolved_technical_relevance_run_id or "NONE",
            "technical_relevance.ticker_count": technical_relevance_ticker_count,
            "technical_relevance.ticker_count_status": technical_relevance_ticker_count_status,
            "technical_relevance.start_date": technical_relevance_start_date,
            "technical_relevance.end_date": technical_relevance_end_date,
            "technical_relevance.status": technical_relevance_status,
            "technical_relevance_run_id": resolved_technical_relevance_run_id or "NONE",
            **(
                {"technical_relevance.existing_run_reused": technical_relevance_existing_run_reused}
                if technical_relevance_existing_run_reused == 1
                else {}
            ),
            "pipeline_output_dir": str(output_dir),
            "windows_report_copy.enabled": "true" if windows_report_copy_enabled else "false",
            "windows_report_copy.destination_dir": str(WINDOWS_REPORT_COPY_DIR),
            "windows_report_copy.execution_status": (
                "EXECUTED" if windows_report_copy_enabled and not skip_reports else "SKIPPED"
            ),
            "windows_report_copy.skip_reason": (
                "" if windows_report_copy_enabled and not skip_reports else "disabled"
            ),
            "pipeline_stage_count": len(stages),
            "pipeline_completed_stage_count": completed_stage_count,
            "pipeline.total_duration_seconds": _format_duration_seconds(perf_counter() - total_start),
            "audit_validation_status": audit_validation_status,
            "daily_report_path": daily_report_path,
            "daily_report_csv_path": daily_report_csv_path,
            "weekly_report_path": weekly_report_path,
            "weekly_report_csv_path": weekly_report_csv_path,
            "rolling_30_report_path": rolling_30_report_path,
            "rolling_30_report_csv_path": rolling_30_report_csv_path,
            "rolling_5_report_path": rolling_5_report_path,
            "rolling_5_report_csv_path": rolling_5_report_csv_path,
            "rolling_2_report_path": rolling_2_report_path,
            "rolling_2_report_csv_path": rolling_2_report_csv_path,
            "decision_summary_report_path": decision_summary_report_path,
            "decision_summary.status": decision_summary_status,
            "decision_summary.execution_status": decision_summary_execution_status,
            "decision_summary.skip_reason": decision_summary_skip_reason,
            "decision_summary.error": decision_summary_error,
            "pipeline_status": pipeline_status,
            **stage_duration_summary,
            **stage2_summary,
            **ticker_swing_snapshot_profile_summary,
            **technical_relevance_profile_summary,
        }
    }
