from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

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
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from analysis.datacenter_indices.swing_weekly_report import (
    format_weekly_swing_report_summary_lines,
    write_weekly_swing_report,
)
from run_datacenter_group_swing_signals import main as run_datacenter_group_swing_signals_main
from run_datacenter_group_synthetic_ohlc import main as run_datacenter_group_synthetic_ohlc_main
from run_datacenter_indices import main as run_datacenter_indices_main
from run_datacenter_ticker_swing_signals import main as run_datacenter_ticker_swing_signals_main


FINAL_PIPELINE_SUMMARY_ORDER = (
    "pipeline_signal_date",
    "pipeline_start_date",
    "pipeline_index_base_date",
    "pipeline_taxonomy_version",
    "pipeline_signal_version",
    "pipeline_ohlc_calc_version",
    "pipeline_output_dir",
    "pipeline_stage_count",
    "pipeline_completed_stage_count",
    "audit_validation_status",
    "daily_report_path",
    "weekly_report_path",
    "pipeline_status",
)


@dataclass(frozen=True)
class PipelineStage:
    heading: str
    argv: list[str]
    runner: Callable[[], dict[str, object] | None]
    watermark_builder: Callable[[dict[str, object] | None], dict[str, object]] | None = None


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
        if key in summary:
            lines.append(f"SUMMARY {key}={summary[key]}")
    for key, value in summary.items():
        if key not in FINAL_PIPELINE_SUMMARY_ORDER:
            lines.append(f"SUMMARY {key}={value}")
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
    )
    for line in format_weekly_swing_report_summary_lines(result["summary"]):
        print(line)
    return result


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
    skip_index: bool = False,
    skip_audit: bool = False,
    skip_reports: bool = False,
    audit_strict: bool = False,
    dry_run: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, object]:
    selected_watchlist_file = Path(DEFAULT_WATCHLIST_FILE) if watchlist_file is None else Path(watchlist_file)
    output_hhmm = _resolve_output_timestamp_hhmm(generated_at_utc)
    daily_output_md = _timestamp_output_path(
        output_dir / f"datacenter_daily_{signal_date}_full.md",
        date_value=signal_date,
        hhmm=output_hhmm,
    )
    daily_output_csv = _timestamp_output_path(
        output_dir / f"datacenter_daily_{signal_date}_full.csv",
        date_value=signal_date,
        hhmm=output_hhmm,
    )
    weekly_output_md = _timestamp_output_path(
        output_dir / f"datacenter_weekly_{signal_date}_full.md",
        date_value=signal_date,
        hhmm=output_hhmm,
    )
    weekly_output_csv = _timestamp_output_path(
        output_dir / f"datacenter_weekly_{signal_date}_full.csv",
        date_value=signal_date,
        hhmm=output_hhmm,
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
    stages.append(
        PipelineStage(
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
        if no_taxonomy_listing:
            daily_argv.append("--no-taxonomy-listing")
            weekly_argv.append("--no-taxonomy-listing")
        stages.append(
            PipelineStage(
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
                heading="Weekly swing report",
                argv=weekly_argv,
                runner=lambda: _run_weekly_report_stage(
                    analysis_db=analysis_db,
                    end_date=signal_date,
                    signal_version=signal_version,
                    ohlc_calc_version=ohlc_calc_version,
                    taxonomy_version=taxonomy_version,
                    window_size=weekly_window_size,
                    watchlist_file=selected_watchlist_file,
                    output_md=weekly_output_md,
                    output_csv=weekly_output_csv,
                    include_taxonomy_listing=not no_taxonomy_listing,
                ),
                watermark_builder=lambda result: {
                    "component_name": "WEEKLY_REPORT",
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

    if dry_run:
        for index, stage in enumerate(stages, start=1):
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
                "pipeline_output_dir": str(output_dir),
                "pipeline_stage_count": len(stages),
                "pipeline_completed_stage_count": 0,
                "audit_validation_status": "SKIPPED" if skip_audit else "DRY_RUN",
                "daily_report_path": "",
                "weekly_report_path": "",
                "pipeline_status": "DRY_RUN",
            }
        }

    completed_stage_count = 0
    audit_validation_status = "SKIPPED" if skip_audit else "UNKNOWN"
    daily_report_path = ""
    weekly_report_path = ""

    if not skip_reports:
        output_dir.mkdir(parents=True, exist_ok=True)

    for index, stage in enumerate(stages, start=1):
        if stage.heading == "Daily report" and audit_validation_status == "FAIL":
            break
        if stage.heading == "Weekly swing report" and audit_validation_status == "FAIL":
            break
        print(f"=== Stage {index}/{len(stages)}: {stage.heading} ===")
        result = stage.runner()
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
                        "pipeline_output_dir": str(output_dir),
                        "pipeline_stage_count": len(stages),
                        "pipeline_completed_stage_count": completed_stage_count,
                        "audit_validation_status": audit_validation_status,
                        "daily_report_path": "",
                        "weekly_report_path": "",
                        "pipeline_status": "FAIL",
                    }
                }
        elif stage.heading == "Daily report":
            daily_report_path = str(result["summary"]["output_markdown"])
        elif stage.heading == "Weekly swing report":
            weekly_report_path = str(result["summary"]["output_markdown"])

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
            "pipeline_output_dir": str(output_dir),
            "pipeline_stage_count": len(stages),
            "pipeline_completed_stage_count": completed_stage_count,
            "audit_validation_status": audit_validation_status,
            "daily_report_path": daily_report_path,
            "weekly_report_path": weekly_report_path,
            "pipeline_status": pipeline_status,
        }
    }
