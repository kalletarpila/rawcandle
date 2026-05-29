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
from analysis.datacenter_indices.swing_weekly_report import (
    format_weekly_swing_report_summary_lines,
    write_weekly_swing_report,
)
from dev_tools.datacenter_dashboard_structured_export import (
    DatacenterStructuredExportReport,
    write_datacenter_dashboard_input_json_from_pipeline_reports,
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
    "pipeline_status",
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


def format_pipeline_final_summary_lines(summary: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key in FINAL_PIPELINE_SUMMARY_ORDER:
        if key == "pipeline_status":
            continue
        if key in summary:
            lines.append(f"SUMMARY {key}={summary[key]}")
    for stage_key in PIPELINE_STAGE_KEYS:
        status_key = f"pipeline_stage.{stage_key}.status"
        duration_key = f"pipeline_stage.{stage_key}.duration_seconds"
        if status_key in summary:
            lines.append(f"SUMMARY {status_key}={summary[status_key]}")
        if duration_key in summary:
            lines.append(f"SUMMARY {duration_key}={summary[duration_key]}")
    for key, value in summary.items():
        if key not in FINAL_PIPELINE_SUMMARY_ORDER and not key.startswith("pipeline_stage."):
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
    return summary


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
) -> None:
    if builder is None:
        return
    payload = builder(result)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        last_successful_at_utc=generated_at_utc,
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


def _pipeline_report_for_structured_export(
    *,
    horizon: str,
    result: dict[str, object] | None,
) -> DatacenterStructuredExportReport:
    if not isinstance(result, dict):
        raise ValueError(
            f"structured export missing internal report result for horizon={horizon}"
        )
    summary = result.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(
            f"structured export missing summary payload for horizon={horizon}"
        )
    markdown_path = str(summary.get("output_markdown") or "").strip()
    if not markdown_path:
        raise ValueError(
            f"structured export missing output_markdown for horizon={horizon}"
        )
    csv_text = result.get("csv")
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError(
            f"structured export missing in-memory csv payload for horizon={horizon}"
        )
    report_data = result.get("report_data")
    if not isinstance(report_data, dict):
        raise ValueError(
            f"structured export missing in-memory report_data for horizon={horizon}"
        )
    return DatacenterStructuredExportReport(
        horizon=horizon,
        markdown_path=markdown_path,
        csv_text=csv_text,
        report_data=report_data,
    )


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
    dry_run: bool = False,
    generated_at_utc: str | None = None,
    export_dashboard_input_json: Path | None = None,
) -> dict[str, object]:
    total_start = perf_counter()
    if technical_relevance_run_id is not None and not technical_relevance_run_id.strip():
        raise ValueError("technical_relevance_run_id must be non-empty when provided")
    if no_technical_relevance and technical_relevance_run_id is not None:
        raise ValueError("--no-technical-relevance and --technical-relevance-run-id cannot be used together")
    if export_dashboard_input_json is not None and dry_run:
        raise ValueError("--export-dashboard-input-json cannot be used with --dry-run")
    if export_dashboard_input_json is not None and skip_reports:
        raise ValueError("--export-dashboard-input-json requires generated reports; cannot be used with --skip-reports")
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
        start_date,
        "--end-date",
        signal_date,
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
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    group_base_argv = [
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
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
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
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
        start_date,
        "--end-date",
        signal_date,
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
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    overheat_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
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
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
        )
    )

    scanner_argv = [
        "--analysis-db",
        str(analysis_db),
        "--start-date",
        start_date,
        "--end-date",
        signal_date,
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
                "start_date": start_date,
                "end_date": signal_date,
                "row_count": None,
                "status": "OK",
            },
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
                    ],
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
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "DRY_RUN"
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
                "pipeline_status": "DRY_RUN",
                **stage_duration_summary,
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
    daily_report_result: dict[str, object] | None = None
    rolling_30_report_result: dict[str, object] | None = None
    rolling_5_report_result: dict[str, object] | None = None
    rolling_2_report_result: dict[str, object] | None = None
    structured_export_summary: dict[str, object] = {}

    if not skip_reports:
        output_dir.mkdir(parents=True, exist_ok=True)

    for index, stage in enumerate(stages, start=1):
        if stage.heading == "Daily report" and audit_validation_status == "FAIL":
            break
        if stage.heading == "Weekly swing report" and audit_validation_status == "FAIL":
            break
        print(f"=== Stage {index}/{len(stages)}: {stage.heading} ===")
        stage_start = perf_counter()
        try:
            result = stage.runner()
        except Exception:
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "FAILED"
            stage_duration_summary[f"pipeline_stage.{stage.stage_key}.duration_seconds"] = _format_duration_seconds(
                perf_counter() - stage_start
            )
            raise
        stage_duration_summary[f"pipeline_stage.{stage.stage_key}.status"] = "OK"
        stage_duration_summary[f"pipeline_stage.{stage.stage_key}.duration_seconds"] = _format_duration_seconds(
            perf_counter() - stage_start
        )
        _write_stage_watermark(
            analysis_db=analysis_db,
            builder=stage.watermark_builder,
            result=result,
            generated_at_utc=generated_at_utc,
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
                        "pipeline_status": "FAIL",
                        **stage_duration_summary,
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
        elif stage.heading == "Windows report copy":
            copy_summary = result["summary"]
            for key, value in copy_summary.items():
                print(f"SUMMARY windows_report_copy.{key}={value}")

    if export_dashboard_input_json is not None:
        _dashboard_input, export_summary_lines = write_datacenter_dashboard_input_json_from_pipeline_reports(
            ecosystem_code="DATACENTER",
            report_date=signal_date,
            reports_dir=str(output_dir),
            output_json=str(export_dashboard_input_json),
            daily_report=_pipeline_report_for_structured_export(
                horizon="daily",
                result=daily_report_result,
            ),
            rolling_30_report=_pipeline_report_for_structured_export(
                horizon="rolling 30d",
                result=rolling_30_report_result,
            ),
            rolling_5_report=_pipeline_report_for_structured_export(
                horizon="rolling 5d",
                result=rolling_5_report_result,
            ),
            rolling_2_report=_pipeline_report_for_structured_export(
                horizon="rolling 2d",
                result=rolling_2_report_result,
            ),
        )
        structured_export_summary = _summary_lines_to_dict(export_summary_lines)

    pipeline_status = "OK"
    if audit_validation_status == "WARN":
        pipeline_status = "WARN"
    if audit_validation_status == "FAIL":
        pipeline_status = "FAIL"

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
            "pipeline_status": pipeline_status,
            **stage_duration_summary,
            **structured_export_summary,
            **ticker_swing_snapshot_profile_summary,
            **technical_relevance_profile_summary,
        }
    }
