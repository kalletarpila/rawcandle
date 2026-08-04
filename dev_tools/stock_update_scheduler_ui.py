from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import threading
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import flet as ft

from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
    validate_run_time,
    validate_scheduler_config,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    SchedulerAlreadyRunningError,
    read_scheduler_status,
    run_scheduler_config,
)
from rawcandle.datacenter_taxonomy_change_orchestrator import (
    DATACENTER_ECOSYSTEM_CODE,
    REBUILD_MODE_AUTO,
    REBUILD_MODE_DELTA,
    REBUILD_MODE_FULL,
    activate_taxonomy_change,
    build_production_taxonomy_change_services,
    execute_taxonomy_rebuild,
    inspect_taxonomy_change,
    plan_taxonomy_activation,
    prepare_taxonomy_change,
    resume_taxonomy_rebuild,
    validate_and_finalize_taxonomy_rebuild,
)
from rawcandle.datacenter_taxonomy_operation_log import (
    complete_taxonomy_change_operation,
    create_taxonomy_change_operation,
    inspect_taxonomy_change_artifacts,
    inspect_taxonomy_operation_lock,
    list_taxonomy_change_operations,
    prepare_taxonomy_change_evidence_package,
    prepare_taxonomy_change_log_download,
    read_taxonomy_change_log,
    taxonomy_operation_lock_context,
    write_taxonomy_operation_artifact,
)


SCHEDULER_UI_PORT = 8555
DEFAULT_DATACENTER_PRICE_DB = "data/osakedata.db"
DEFAULT_DATACENTER_ANALYSIS_DB = "data/analysis.db"
DEFAULT_DATACENTER_TAXONOMY_CSV = "data/datacenter_ecosystem_taxonomy_full_v1.csv"
DEFAULT_DATACENTER_TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
DEFAULT_DATACENTER_MARKET = "usa"
DEFAULT_DATACENTER_INDEX_BASE_DATE = "2020-01-01"
DEFAULT_DATACENTER_OUTPUT_DIR = "/home/kalle/projects/rawcandle/swing_reports"
DEFAULT_DATACENTER_EXPECTED_TICKER_COUNT = "236"
DEFAULT_DATACENTER_EXPECTED_GROUP_COUNT = "54"
DEFAULT_DATACENTER_EXPECTED_SYNTHETIC_OHLC_COUNT = "53"
DEFAULT_DATACENTER_ROLLING_WINDOW_SIZE = "20"
DEFAULT_DATACENTER_WATCHLIST_FILE = "/home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt"
DEFAULT_DATACENTER_SIGNAL_DATE = (date.today() - timedelta(days=1)).isoformat()
DEFAULT_DATACENTER_START_DATE = "2025-08-01"
_SUMMARY_FILENAME_RE = r"stock_update_scheduler_summary_"
_MARKET_LOG_FILENAME_RE = re.compile(
    r"^stock_update_(omxh|omxs|usa)_(\d{8}T\d{4,6}Z)(?:_(\d+))?\.(txt|log)$"
)
_DATACENTER_LOG_FILENAME_RE = re.compile(
    r"^datacenter_pipeline_([a-z0-9_]+)_(\d{8}T\d{4,6}Z)(?:_(\d+))?\.(txt|log)$"
)
_EC_SOURCE_LAYER_LOG_FILENAME_RE = re.compile(
    r"^ec_source_layer_([a-z0-9_]+)_(\d{8}T\d{4,6}Z)(?:_(\d+))?\.(txt|log)$"
)
_TIMER_PATH = Path.home() / ".config/systemd/user/stock-update-scheduler.timer"
_TAXONOMY_EVIDENCE_ROOT = "temp/datacenter_taxonomy_changes"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone stock update scheduler control panel."
    )
    parser.add_argument("--config", default="scheduler_config.json")
    parser.add_argument("--port", type=int, default=SCHEDULER_UI_PORT)
    return parser


def build_config_from_ui_values(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    log_dir: str,
    timezone: str,
    run_time: str,
    selected_markets: List[str],
    technical_relevance_enabled: bool,
    base_config: StockUpdateSchedulerConfig | None = None,
) -> StockUpdateSchedulerConfig:
    config = replace(
        base_config or StockUpdateSchedulerConfig(),
        enabled_markets=selected_markets,
        run_time=run_time,
        osakedata_db_path=osakedata_db_path,
        analysis_db_path=analysis_db_path,
        log_dir=log_dir,
        timezone=timezone,
        technical_relevance_enabled=technical_relevance_enabled,
    )
    return validate_scheduler_config(config)


def load_latest_scheduler_summary(log_dir: str) -> Optional[Dict[str, Any]]:
    directory = Path(log_dir)
    if not directory.exists():
        return None
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.name.startswith(_SUMMARY_FILENAME_RE)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def list_scheduler_log_files(log_dir: str, limit: int = 10) -> list[dict[str, Any]]:
    directory = Path(log_dir)
    if not directory.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        market_match = _MARKET_LOG_FILENAME_RE.match(path.name)
        datacenter_match = _DATACENTER_LOG_FILENAME_RE.match(path.name)
        ec_source_layer_match = _EC_SOURCE_LAYER_LOG_FILENAME_RE.match(path.name)
        if market_match:
            timestamp = market_match.group(2)
            suffix = market_match.group(3) or "0"
            entry_type = "market_log"
        elif datacenter_match:
            timestamp = datacenter_match.group(2)
            suffix = datacenter_match.group(3) or "0"
            entry_type = "datacenter_log"
        elif ec_source_layer_match:
            timestamp = ec_source_layer_match.group(2)
            suffix = ec_source_layer_match.group(3) or "0"
            entry_type = "ec_source_layer_log"
        else:
            continue
        stat_result = path.stat()
        entries.append(
            {
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat_result.st_size,
                "modified_at": str(int(stat_result.st_mtime)),
                "sort_key": f"{timestamp}_{suffix}",
                "type": entry_type,
            }
        )
    entries.sort(key=lambda item: item["sort_key"], reverse=True)
    return entries[:limit]


def build_text_log_browser_url(path: str) -> str:
    return f"/{quote(Path(path).name)}"


def _sha256_if_file(path: str | None) -> str | None:
    if not path or not Path(path).is_file():
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _connect_taxonomy_db_readonly(db_path: str):
    import sqlite3

    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _taxonomy_table_names(conn: Any) -> set[str]:
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def inspect_scheduler_taxonomy_state(
    *,
    config_path: str,
    deployment_id: int | None = None,
    evidence_root: str = _TAXONOMY_EVIDENCE_ROOT,
) -> dict[str, Any]:
    config = read_scheduler_config(config_path)
    state: dict[str, Any] = {
        "status": "OK",
        "scheduler_datacenter_taxonomy_version": config.datacenter_taxonomy_version,
        "scheduler_ec_taxonomy_version": config.ec_source_layer_taxonomy_version,
        "analysis_db_path": config.analysis_db_path,
        "active_taxonomy": {},
        "fact_heads": {},
        "watermark_heads": {},
        "db_config_consistency_status": "UNKNOWN",
        "deployment": None,
        "inspect": None,
        "operations": [],
        "blocking_errors": [],
    }
    conn = _connect_taxonomy_db_readonly(config.analysis_db_path)
    try:
        tables = _taxonomy_table_names(conn)
        active = None
        if {"ec_taxonomy_version", "ec_ecosystem"}.issubset(tables):
            active_row = conn.execute(
                """
                SELECT tv.*, e.ecosystem_code
                FROM ec_taxonomy_version tv
                JOIN ec_ecosystem e ON e.ecosystem_id = tv.ecosystem_id
                WHERE e.ecosystem_code = ? AND tv.is_active = 1
                ORDER BY tv.taxonomy_version_id DESC
                LIMIT 1
                """,
                (DATACENTER_ECOSYSTEM_CODE,),
            ).fetchone()
            active = dict(active_row) if active_row is not None else None
        if active:
            active_version = str(active.get("taxonomy_version_code") or "")
            source_reference = str(active.get("source_reference") or "")
            state["active_taxonomy"] = {
                "version": active_version,
                "csv_path": source_reference,
                "sha256": active.get("source_hash") or _sha256_if_file(source_reference),
                "deployment_id": active.get("activated_by_taxonomy_change_id"),
                "status": "ACTIVE" if active.get("is_active") else active.get("status"),
                "ticker_count": None,
                "group_count": None,
                "synthetic_group_count": None,
            }
            if "ec_membership" in tables:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT entity_id) FROM ec_membership WHERE taxonomy_version_id = ?",
                    (active.get("taxonomy_version_id"),),
                ).fetchone()
                state["active_taxonomy"]["ticker_count"] = row[0] if row else None
            for table, date_col in [
                ("dc_ticker_swing_signal_daily", "signal_date"),
                ("dc_group_swing_signal_daily", "signal_date"),
                ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
                ("dc_group_index_daily", "index_date"),
            ]:
                if table in tables:
                    row = conn.execute(
                        f"SELECT MAX({date_col}) FROM {table} WHERE taxonomy_version = ?",
                        (active_version,),
                    ).fetchone()
                    state["fact_heads"][table] = row[0] if row else None
            if "ec_pipeline_watermark" in tables:
                rows = conn.execute(
                    """
                    SELECT source_table, MAX(latest_signal_date) AS head
                    FROM ec_pipeline_watermark
                    GROUP BY source_table
                    ORDER BY source_table
                    """
                ).fetchall()
                state["watermark_heads"] = {str(row["source_table"]): row["head"] for row in rows}
            if active_version == config.datacenter_taxonomy_version == config.ec_source_layer_taxonomy_version:
                state["db_config_consistency_status"] = "OK"
            else:
                state["db_config_consistency_status"] = "BLOCKED_MIXED_DB_CONFIG_STATE"
                state["blocking_errors"].append("scheduler taxonomy config does not match active DB taxonomy")
        else:
            state["db_config_consistency_status"] = "BLOCKED_NO_ACTIVE_TAXONOMY"
            state["blocking_errors"].append("active taxonomy not found")
    finally:
        conn.close()
    if deployment_id is not None:
        inspection = inspect_taxonomy_change(
            analysis_db=config.analysis_db_path,
            deployment_id=deployment_id,
            scheduler_config_path=config_path,
        )
        state["inspect"] = inspection
        state["deployment"] = inspection.get("deployment")
        state["operations"] = list_taxonomy_change_operations(
            deployment_id=deployment_id,
            evidence_root=evidence_root,
        )
    return state


def format_taxonomy_state_lines(state: dict[str, Any]) -> str:
    active = state.get("active_taxonomy", {})
    fact_heads = state.get("fact_heads", {})
    watermark_heads = state.get("watermark_heads", {})
    return "\n".join(
        [
            f"active_taxonomy_version={active.get('version', '')}",
            f"active_taxonomy_csv={active.get('csv_path', '')}",
            f"active_taxonomy_sha256={active.get('sha256', '')}",
            f"active_deployment_id={active.get('deployment_id', '')}",
            f"active_deployment_status={active.get('status', '')}",
            f"ticker_count={active.get('ticker_count', '')}",
            f"group_count={active.get('group_count', '')}",
            f"synthetic_group_count={active.get('synthetic_group_count', '')}",
            f"dc_fact_head={max([value for value in fact_heads.values() if value] or [''])}",
            f"ec_fact_head={state.get('ec_fact_head', '')}",
            f"dc_watermark_head={max([value for value in watermark_heads.values() if value] or [''])}",
            f"ec_watermark_head={max([value for value in watermark_heads.values() if value] or [''])}",
            f"scheduler_datacenter_taxonomy_version={state.get('scheduler_datacenter_taxonomy_version', '')}",
            f"scheduler_ec_taxonomy_version={state.get('scheduler_ec_taxonomy_version', '')}",
            f"db_config_consistency_status={state.get('db_config_consistency_status', '')}",
            "blocking_errors=" + "; ".join(state.get("blocking_errors", [])),
        ]
    )


def format_taxonomy_plan_lines(summary: dict[str, Any]) -> str:
    plan = summary.get("plan", {}) if isinstance(summary.get("plan"), dict) else {}
    diff = plan.get("taxonomy_diff", {}) if isinstance(plan.get("taxonomy_diff"), dict) else {}
    scope = plan.get("delta_scope_summary", {}) if isinstance(plan.get("delta_scope_summary"), dict) else {}
    estimate = plan.get("estimated_delta_work", {}) if isinstance(plan.get("estimated_delta_work"), dict) else {}
    return "\n".join(
        [
            f"deployment_id={summary.get('deployment_id', '')}",
            f"current_taxonomy_version={plan.get('current_taxonomy_version', '')}",
            f"current_taxonomy_hash={plan.get('current_source_sha256', '')}",
            f"proposed_taxonomy_version={plan.get('proposed_taxonomy_version', '')}",
            f"proposed_taxonomy_hash={plan.get('proposed_source_sha256', '')}",
            f"date_range={plan.get('date_from', '')}..{plan.get('date_to', '')}",
            f"recommended_rebuild_mode={plan.get('recommended_rebuild_mode', '')}",
            f"selected_rebuild_mode={plan.get('selected_rebuild_mode', plan.get('rebuild_mode', ''))}",
            f"plan_hash={plan.get('plan_hash', '')}",
            f"delta_safe={plan.get('delta_safe', '')}",
            "delta_blocking_reasons=" + "; ".join(plan.get("delta_blocking_reasons", [])),
            f"added_tickers={len(diff.get('added_tickers', []))}",
            f"removed_tickers={len(diff.get('removed_tickers', []))}",
            f"primary_membership_changes={len(diff.get('primary_membership_changes', []))}",
            f"secondary_membership_additions={len(diff.get('secondary_membership_additions', []))}",
            f"secondary_membership_removals={len(diff.get('secondary_membership_removals', []))}",
            f"scope_flag_changes={len(diff.get('scope_flag_changes', []))}",
            f"affected_tickers={len(scope.get('affected_tickers', diff.get('affected_tickers', [])))}",
            f"affected_groups={len(scope.get('affected_groups', diff.get('affected_groups', [])))}",
            f"unaffected_tickers={len(scope.get('unaffected_tickers', []))}",
            f"unaffected_groups={len(scope.get('unaffected_groups', []))}",
            f"total_tickers={estimate.get('total_tickers', '')}",
            f"affected_ticker_count={estimate.get('affected_ticker_count', '')}",
            f"copied_ticker_count={estimate.get('copied_ticker_count', '')}",
            f"rebuilt_ticker_count={estimate.get('rebuilt_ticker_count', '')}",
            f"total_groups={estimate.get('total_groups', '')}",
            f"affected_group_count={estimate.get('affected_group_count', '')}",
            f"copied_group_count={estimate.get('copied_group_count', '')}",
            f"estimated_copy_row_count={estimate.get('estimated_copy_row_count', '')}",
            f"estimated_rebuild_row_count={estimate.get('estimated_rebuild_row_count', '')}",
            f"estimated_full_rebuild_row_count={estimate.get('estimated_full_rebuild_row_count', '')}",
            f"estimated_work_reduction_pct={estimate.get('estimated_work_reduction_pct', '')}",
            "blocking_errors=" + "; ".join(summary.get("blocking_errors", plan.get("blocking_errors", []))),
        ]
    )


def taxonomy_confirmation_key(plan: dict[str, Any]) -> tuple[Any, ...]:
    return (
        plan.get("deployment_id"),
        plan.get("proposed_taxonomy_version"),
        plan.get("proposed_source_sha256"),
        plan.get("date_from"),
        plan.get("date_to"),
        plan.get("selected_rebuild_mode", plan.get("rebuild_mode")),
        plan.get("plan_hash"),
    )


def taxonomy_rebuild_action_state(
    *,
    status: str,
    safe_to_run: bool,
    confirmation_valid: bool,
    blocking_errors: list[str],
) -> dict[str, bool]:
    enabled = status in {"PLANNED", "REBUILD_FAILED"} and safe_to_run and confirmation_valid and not blocking_errors
    return {"run_disabled": not enabled}


def taxonomy_activation_confirmation_key(plan: dict[str, Any]) -> tuple[Any, ...]:
    changed_keys = plan.get("scheduler_changed_keys", [])
    blocking_errors = plan.get("blocking_errors", [])
    return (
        plan.get("deployment_id"),
        plan.get("current_taxonomy_version"),
        plan.get("proposed_taxonomy_version"),
        plan.get("proposed_source_sha256"),
        plan.get("required_signal_date"),
        plan.get("current_db_taxonomy_status"),
        plan.get("current_scheduler_taxonomy_status"),
        plan.get("proposed_scheduler_taxonomy_status"),
        tuple(changed_keys) if isinstance(changed_keys, list) else changed_keys,
        tuple(blocking_errors) if isinstance(blocking_errors, list) else blocking_errors,
        plan.get("safe_to_activate"),
    )


def taxonomy_activation_action_state(
    *,
    orchestration_status: str,
    activation_plan_status: str,
    safe_to_activate: bool,
    confirmation_valid: bool,
    blocking_errors: list[str],
    operation_active: bool = False,
) -> dict[str, bool]:
    enabled = (
        orchestration_status == "READY_TO_ACTIVATE"
        and activation_plan_status == "READY_TO_ACTIVATE"
        and safe_to_activate
        and confirmation_valid
        and not blocking_errors
        and not operation_active
    )
    return {"activate_disabled": not enabled}


def start_taxonomy_background_operation(page: Any, target: Any, *args: Any, **kwargs: Any) -> threading.Thread:
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    if hasattr(page, "taxonomy_job_thread"):
        page.taxonomy_job_thread = thread
    return thread


def launch_browser_url(page: Any, url: str) -> None:
    result = page.launch_url(url)
    if inspect.isawaitable(result):
        async def _await_launch() -> None:
            await result

        page.run_task(_await_launch)


def format_run_now_error_message(exc: Exception) -> str:
    if isinstance(exc, SchedulerAlreadyRunningError):
        return "Run now blocked: scheduler run is already active."
    return f"Run now failed: {exc}"


def get_systemd_user_timer_path() -> Path:
    return _TIMER_PATH


def format_systemd_on_calendar(*, run_time: str) -> str:
    validate_run_time(run_time)
    return f"*-*-* {run_time}:00"


def read_systemd_timer_on_calendar(timer_path: Path) -> Optional[str]:
    if not timer_path.exists():
        return None
    for line in timer_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OnCalendar="):
            return line.split("=", 1)[1]
    return None


def update_systemd_timer_on_calendar(timer_path: Path, *, run_time: str) -> None:
    if not timer_path.exists():
        raise FileNotFoundError(timer_path)
    lines = timer_path.read_text(encoding="utf-8").splitlines()
    replacement = f"OnCalendar={format_systemd_on_calendar(run_time=run_time)}"
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("OnCalendar="):
            updated.append(replacement)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        raise ValueError("OnCalendar line not found")
    timer_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def read_systemd_user_timer_status() -> dict[str, Any]:
    timer_path = get_systemd_user_timer_path()
    on_calendar = read_systemd_timer_on_calendar(timer_path)
    installed = timer_path.exists()
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "stock-update-scheduler.timer"],
            check=False,
            capture_output=True,
            text=True,
        )
        status_summary = proc.stdout.strip() or proc.stderr.strip() or "unknown"
        error = None
    except Exception as exc:  # pragma: no cover - defensive UI helper
        status_summary = "unknown"
        error = str(exc)
    return {
        "timer_path": str(timer_path),
        "on_calendar": on_calendar,
        "installed": installed,
        "status_summary": status_summary if installed else "missing",
        "error": error,
    }


def save_config_and_sync_systemd_timer(
    *,
    config_path: str,
    config: StockUpdateSchedulerConfig,
) -> dict[str, Any]:
    write_scheduler_config(config_path, config)
    timer_path = get_systemd_user_timer_path()
    if not timer_path.exists():
        return {
            "status": "WARNING",
            "message": "Config saved; systemd timer file missing.",
            "timer_path": str(timer_path),
        }
    update_systemd_timer_on_calendar(timer_path, run_time=config.run_time)
    proc = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "status": "WARNING",
            "message": f"Config saved; systemd daemon-reload failed: {proc.stderr.strip()}",
            "timer_path": str(timer_path),
        }
    return {"status": "OK", "message": "Config saved.", "timer_path": str(timer_path)}


def build_skip_next_run_config(config: StockUpdateSchedulerConfig) -> StockUpdateSchedulerConfig:
    config.skip_next_run = True
    return validate_scheduler_config(config)


def build_cancel_skip_next_run_config(config: StockUpdateSchedulerConfig) -> StockUpdateSchedulerConfig:
    config.skip_next_run = False
    return validate_scheduler_config(config)


def scheduler_running_state(status: Optional[dict[str, Any]]) -> dict[str, Any]:
    is_running = bool(status and status.get("is_running"))
    return {"is_running": is_running}


def scheduler_skip_button_state(
    *, is_running: bool, skip_next_run: bool
) -> dict[str, bool]:
    return {
        "skip_disabled": is_running or skip_next_run,
        "cancel_disabled": is_running or not skip_next_run,
    }


def scheduler_skip_next_run_label(config: StockUpdateSchedulerConfig) -> str:
    return "Next scheduled run: SKIP" if config.skip_next_run else "Next scheduled run: RUN"


def apply_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    config = read_scheduler_config(config_path)
    status = read_scheduler_status(config.log_dir)
    if scheduler_running_state(status)["is_running"]:
        return config
    config = build_skip_next_run_config(config)
    write_scheduler_config(config_path, config)
    return config


def apply_cancel_skip_next_run_to_config(config_path: str) -> StockUpdateSchedulerConfig:
    config = read_scheduler_config(config_path)
    status = read_scheduler_status(config.log_dir)
    if scheduler_running_state(status)["is_running"]:
        return config
    config = build_cancel_skip_next_run_config(config)
    write_scheduler_config(config_path, config)
    return config


def build_datacenter_pipeline_command(
    *,
    price_db: str,
    analysis_db: str,
    taxonomy_csv: str,
    taxonomy_version: str,
    market: str,
    signal_date: str,
    start_date: str,
    index_base_date: str,
    output_dir: str,
    expected_ticker_count: str,
    expected_group_count: str,
    expected_synthetic_ohlc_count: str,
    rolling_window_size: str,
    watchlist_file: str,
    dry_run: bool,
) -> List[str]:
    command = [
        "python3",
        "run_datacenter_swing_pipeline.py",
        "--price-db",
        price_db,
        "--analysis-db",
        analysis_db,
        "--taxonomy-csv",
        taxonomy_csv,
        "--taxonomy-version",
        taxonomy_version,
        "--market",
        market,
        "--signal-date",
        signal_date,
        "--start-date",
        start_date,
        "--index-base-date",
        index_base_date,
        "--output-dir",
        output_dir,
        "--expected-ticker-count",
        expected_ticker_count,
        "--expected-group-count",
        expected_group_count,
        "--expected-synthetic-ohlc-count",
        expected_synthetic_ohlc_count,
        "--weekly-window-size",
        rolling_window_size,
        "--watchlist-file",
        watchlist_file,
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def build_datacenter_pipeline_plan_command(**kwargs: str) -> List[str]:
    return build_datacenter_pipeline_command(dry_run=True, **kwargs)


def build_datacenter_audit_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    expected_ticker_count: str,
    expected_group_count: str,
    expected_synthetic_ohlc_count: str,
    rolling_window_size: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_swing_pipeline_audit.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--expected-ticker-count",
        expected_ticker_count,
        "--expected-group-count",
        expected_group_count,
        "--expected-synthetic-ohlc-count",
        expected_synthetic_ohlc_count,
        "--weekly-window-size",
        rolling_window_size,
    ]


def build_datacenter_daily_report_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    watchlist_file: str,
    output_dir: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_daily_report.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--watchlist-file",
        watchlist_file,
        "--output-dir",
        output_dir,
    ]


def build_datacenter_rolling_report_command(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    rolling_window_size: str,
    watchlist_file: str,
    output_dir: str,
) -> List[str]:
    return [
        "python3",
        "run_datacenter_rolling_swing_report.py",
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--rolling-window-size",
        rolling_window_size,
        "--watchlist-file",
        watchlist_file,
        "--output-dir",
        output_dir,
    ]


def build_datacenter_watermark_command(*, analysis_db: str) -> List[str]:
    return ["python3", "run_datacenter_pipeline_watermark.py", "--analysis-db", analysis_db]


def find_datacenter_generated_reports(output_dir: str) -> list[Path]:
    directory = Path(output_dir)
    if not directory.exists():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".csv"}
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def populate_datacenter_report_downloads(
    *, reports_column: Any, output_dir: str, assets_root: Path | None = None
) -> None:
    reports_column.controls = [
        ft.Text(str(path)) for path in find_datacenter_generated_reports(output_dir)
    ]


def run_datacenter_ui_command(
    *,
    page: Any,
    title: str,
    command: List[str],
    log_field: Any,
    status_field: Any,
    output_dir: str | None = None,
    reports_column: Any | None = None,
    assets_root: Path | None = None,
    **_kwargs: Any,
) -> None:
    log_field.value = " ".join(command)
    status_field.value = f"{title} planned."
    if output_dir and reports_column is not None:
        populate_datacenter_report_downloads(
            reports_column=reports_column,
            output_dir=output_dir,
            assets_root=assets_root,
        )
    if hasattr(page, "update"):
        page.update()


def _load_config_or_raise(config_path: str) -> StockUpdateSchedulerConfig:
    return read_scheduler_config(config_path)


def run_app(page: Any, config_path: str = "scheduler_config.json") -> None:
    config = _load_config_or_raise(config_path)
    page.title = "RawCandle stock update scheduler"
    page.scroll = ft.ScrollMode.AUTO

    osakedata_db_field = ft.TextField(label="osakedata_db_path", value=config.osakedata_db_path)
    analysis_db_field = ft.TextField(label="analysis_db_path", value=config.analysis_db_path)
    log_dir_field = ft.TextField(label="log_dir", value=config.log_dir)
    timezone_field = ft.TextField(label="timezone", value=config.timezone)
    run_time_field = ft.TextField(label="run_time", value=config.run_time)
    omxh_checkbox = ft.Checkbox(label="OMXH", value="omxh" in config.enabled_markets)
    omxs_checkbox = ft.Checkbox(label="OMXS", value="omxs" in config.enabled_markets)
    usa_checkbox = ft.Checkbox(label="USA", value="usa" in config.enabled_markets)
    technical_relevance_checkbox = ft.Checkbox(
        label="Run technical relevance after stock updates",
        value=config.technical_relevance_enabled,
    )
    status_field = ft.TextField(label="Status", read_only=True, multiline=True)
    summary_field = ft.TextField(label="Latest summary", read_only=True, multiline=True)
    timer_status_field = ft.TextField(label="Timer status", read_only=True, multiline=True)
    skip_next_run_text = ft.Text(scheduler_skip_next_run_label(config))
    running_status_text = ft.Text("Scheduler running: UNKNOWN")
    logs_column = ft.Column(spacing=8)

    def selected_markets_from_ui() -> list[str]:
        markets: list[str] = []
        if omxh_checkbox.value:
            markets.append("omxh")
        if omxs_checkbox.value:
            markets.append("omxs")
        if usa_checkbox.value:
            markets.append("usa")
        return markets

    def _market_row_text(market_result: dict[str, Any]) -> str:
        return (
            f"market={market_result.get('market', '')} "
            f"status={market_result.get('summary_status', '')} "
            f"log={market_result.get('log_path', '')}"
        )

    def refresh_timer_status() -> None:
        timer_status = read_systemd_user_timer_status()
        timer_status_field.value = "\n".join(
            [
                f"installed={timer_status.get('installed', False)}",
                f"status_summary={timer_status.get('status_summary', '')}",
                f"on_calendar={timer_status.get('on_calendar', '')}",
                f"timer_path={timer_status.get('timer_path', '')}",
                f"error={timer_status.get('error', '')}",
            ]
        )

    def refresh_running_state(log_dir: str) -> None:
        status = read_scheduler_status(log_dir)
        state = scheduler_running_state(status)
        running_status_text.value = (
            "Scheduler status: running"
            if state["is_running"]
            else "Scheduler status: not running"
        )
        current_config = _load_config_or_raise(config_path)
        button_state = scheduler_skip_button_state(
            is_running=state["is_running"],
            skip_next_run=current_config.skip_next_run,
        )
        skip_next_run_button.disabled = button_state["skip_disabled"]
        cancel_skip_next_run_button.disabled = button_state["cancel_disabled"]
        refresh_timer_status()

    def open_log_in_browser(path: Path) -> None:
        launch_browser_url(page, build_text_log_browser_url(str(path)))
        status_field.value = f"Opened log: {path.name}"

    def refresh_logs_view(log_dir: str) -> None:
        log_entries = list_scheduler_log_files(log_dir)
        latest = load_latest_scheduler_summary(log_dir)
        if latest is None:
            summary_field.value = "No scheduler summary JSON found."
        else:
            lines = [
                f"overall_status={latest.get('overall_status', '')}",
                "enabled_markets=" + ",".join(latest.get("enabled_markets", [])),
                f"summary_json_path={latest.get('summary_json_path', '')}",
                "technical_relevance_status="
                f"{latest.get('technical_relevance_status', '')}",
                "ec_source_layer_status="
                f"{latest.get('ec_source_layer_status', '')}",
            ]
            for market_result in latest.get("market_results", []):
                lines.append(_market_row_text(market_result))
            summary_field.value = "\n".join(lines)

        logs_column.controls = []
        if not log_entries:
            logs_column.controls.append(ft.Text("No text log files found."))
        else:
            for log_entry in log_entries:
                path = Path(log_entry["path"])
                logs_column.controls.append(
                    ft.Row(
                        [
                            ft.Text(
                                f"{log_entry['filename']} "
                                f"[{log_entry['type']}] "
                                f"(size={log_entry['size_bytes']}, modified_at={log_entry['modified_at']})",
                                expand=True,
                            ),
                            ft.TextButton(
                                "Open",
                                on_click=lambda _e, path=path: open_log_in_browser(path),
                            ),
                        ]
                    )
                )
        refresh_running_state(log_dir)

    def update_ui_from_config(next_config: StockUpdateSchedulerConfig) -> None:
        osakedata_db_field.value = next_config.osakedata_db_path
        analysis_db_field.value = next_config.analysis_db_path
        log_dir_field.value = next_config.log_dir
        timezone_field.value = next_config.timezone
        run_time_field.value = next_config.run_time
        enabled = set(next_config.enabled_markets)
        omxh_checkbox.value = "omxh" in enabled
        omxs_checkbox.value = "omxs" in enabled
        usa_checkbox.value = "usa" in enabled
        technical_relevance_checkbox.value = next_config.technical_relevance_enabled
        skip_next_run_text.value = scheduler_skip_next_run_label(next_config)

    def on_save_config(_e: Any) -> None:
        try:
            current_config = _load_config_or_raise(config_path)
            next_config = build_config_from_ui_values(
                osakedata_db_path=osakedata_db_field.value,
                analysis_db_path=analysis_db_field.value,
                log_dir=log_dir_field.value,
                timezone=timezone_field.value,
                run_time=run_time_field.value,
                selected_markets=selected_markets_from_ui(),
                technical_relevance_enabled=bool(technical_relevance_checkbox.value),
                base_config=current_config,
            )
            result = save_config_and_sync_systemd_timer(
                config_path=config_path,
                config=next_config,
            )
            update_ui_from_config(next_config)
            refresh_logs_view(next_config.log_dir)
            status_field.value = result["message"]
        except Exception as exc:
            status_field.value = f"Save config failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_reload_config(_e: Any) -> None:
        try:
            next_config = _load_config_or_raise(config_path)
            update_ui_from_config(next_config)
            refresh_logs_view(next_config.log_dir)
            status_field.value = "Config reloaded."
        except Exception as exc:
            status_field.value = f"Reload config failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_run_now(_e: Any) -> None:
        try:
            run_scheduler_config(config_path=config_path)
            status_field.value = "Run now completed."
        except Exception as exc:
            status_field.value = format_run_now_error_message(exc)
        if hasattr(page, "update"):
            page.update()

    def on_skip_next_run(_e: Any) -> None:
        next_config = apply_skip_next_run_to_config(config_path)
        update_ui_from_config(next_config)
        refresh_running_state(next_config.log_dir)
        if hasattr(page, "update"):
            page.update()

    def on_cancel_skip_next_run(_e: Any) -> None:
        next_config = apply_cancel_skip_next_run_to_config(config_path)
        update_ui_from_config(next_config)
        refresh_running_state(next_config.log_dir)
        if hasattr(page, "update"):
            page.update()

    def on_refresh_logs(_e: Any) -> None:
        refresh_logs_view(log_dir_field.value)
        if hasattr(page, "update"):
            page.update()

    save_config_button = ft.ElevatedButton("Save config", on_click=on_save_config)
    reload_config_button = ft.ElevatedButton("Reload config", on_click=on_reload_config)
    run_now_button = ft.ElevatedButton("Run now", on_click=on_run_now)
    skip_next_run_button = ft.ElevatedButton("Skip next run", on_click=on_skip_next_run)
    cancel_skip_next_run_button = ft.ElevatedButton(
        "Cancel skip", on_click=on_cancel_skip_next_run
    )
    refresh_logs_button = ft.ElevatedButton("Refresh logs", on_click=on_refresh_logs)

    taxonomy_proposed_csv_field = ft.TextField(label="Ehdotettu taxonomy CSV")
    taxonomy_rebuild_mode_dropdown = ft.Dropdown(
        label="Rebuild mode",
        value=REBUILD_MODE_AUTO,
        options=[
            ft.dropdown.Option(REBUILD_MODE_AUTO),
            ft.dropdown.Option(REBUILD_MODE_DELTA),
            ft.dropdown.Option(REBUILD_MODE_FULL),
        ],
    )
    taxonomy_date_from_field = ft.TextField(label="date_from", value=DEFAULT_DATACENTER_START_DATE)
    taxonomy_date_to_field = ft.TextField(label="date_to", value=DEFAULT_DATACENTER_SIGNAL_DATE)
    taxonomy_deployment_id_field = ft.TextField(label="deployment_id")
    taxonomy_active_field = ft.TextField(label="Aktiivinen taxonomy", read_only=True, multiline=True, min_lines=8)
    taxonomy_plan_field = ft.TextField(label="Muutokset ja suunnitelma", read_only=True, multiline=True, min_lines=14)
    taxonomy_status_field = ft.TextField(label="Toteutuksen tila", read_only=True, multiline=True, min_lines=8)
    taxonomy_log_field = ft.TextField(label="Taxonomy loki", read_only=True, multiline=True, min_lines=10)
    taxonomy_operations_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)
    taxonomy_confirmation_state: dict[str, Any] = {
        "summary": None,
        "prepared_plan_key": None,
        "plan_key": None,
        "activation_plan": None,
        "prepared_activation_key": None,
        "activation_key": None,
        "orchestration_status": "",
    }

    def _selected_deployment_id() -> int | None:
        value = str(taxonomy_deployment_id_field.value or "").strip()
        return int(value) if value else None

    def _taxonomy_operation_active() -> bool:
        thread = getattr(page, "taxonomy_job_thread", None)
        if thread is not None and thread.is_alive():
            return True
        lock = inspect_taxonomy_operation_lock(evidence_root=_TAXONOMY_EVIDENCE_ROOT)
        return bool(lock.get("lock_active") and not lock.get("stale"))

    def _taxonomy_services(*, resume: bool = False) -> Any:
        injected = getattr(page, "taxonomy_rebuild_services", None)
        if injected is not None:
            return injected
        return build_production_taxonomy_change_services(
            scheduler_config_path=config_path,
            evidence_root=_TAXONOMY_EVIDENCE_ROOT,
            resume=resume,
        )

    def _activation_plan_with_current_file_hash(plan: dict[str, Any]) -> dict[str, Any]:
        return {
            **plan,
            "proposed_source_sha256": _sha256_if_file(taxonomy_proposed_csv_field.value),
        }

    def refresh_taxonomy_state(deployment_id: int | None = None) -> dict[str, Any]:
        state = inspect_scheduler_taxonomy_state(
            config_path=config_path,
            deployment_id=deployment_id,
            evidence_root=_TAXONOMY_EVIDENCE_ROOT,
        )
        taxonomy_active_field.value = format_taxonomy_state_lines(state)
        inspection = state.get("inspect") or {}
        if inspection:
            normalized_status = str(inspection.get("normalized_orchestration_status", ""))
            taxonomy_status_field.value = "\n".join(
                [
                    f"normalized_orchestration_status={normalized_status}",
                    f"safe_next_action={inspection.get('safe_next_action', '')}",
                    f"per_phase_status={json.dumps(inspection.get('per_phase_status', {}), sort_keys=True)}",
                    f"activation_readiness={json.dumps(inspection.get('activation_readiness', {}), sort_keys=True)}",
                ]
            )
            taxonomy_confirmation_state["orchestration_status"] = normalized_status
            safe_next_action = str(inspection.get("safe_next_action", ""))
            taxonomy_plan_activation_button.disabled = normalized_status != "READY_TO_ACTIVATE"
            taxonomy_resume_button.disabled = safe_next_action != "resume_from_failed_phase"
            taxonomy_validate_button.disabled = safe_next_action != "validation_only_recovery"
            taxonomy_activate_button.disabled = True
            if normalized_status != "READY_TO_ACTIVATE":
                taxonomy_confirmation_state["prepared_activation_key"] = None
                taxonomy_confirmation_state["activation_key"] = None
        else:
            taxonomy_resume_button.disabled = True
            taxonomy_validate_button.disabled = True
        taxonomy_operations_column.controls = [
            ft.Text(
                f"{operation.get('operation_type')} {operation.get('started_at_utc')} "
                f"status={operation.get('status')} operation_id={operation.get('operation_id')}"
            )
            for operation in state.get("operations", [])
        ]
        return state

    def on_taxonomy_prepare(_e: Any) -> None:
        try:
            summary = prepare_taxonomy_change(
                analysis_db=analysis_db_field.value,
                proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                date_from=taxonomy_date_from_field.value or DEFAULT_DATACENTER_START_DATE,
                date_to=taxonomy_date_to_field.value,
                scheduler_config_path=config_path,
                watchlist_path=config.ec_source_layer_watchlist,
                evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                rebuild_mode=taxonomy_rebuild_mode_dropdown.value or REBUILD_MODE_AUTO,
            )
            deployment_id = summary.get("deployment_id") or "prepare_blocked"
            operation = create_taxonomy_change_operation(
                deployment_id=deployment_id,
                operation_type="PREPARE",
                evidence_root=_TAXONOMY_EVIDENCE_ROOT,
            )
            write_taxonomy_operation_artifact(operation, relative_name="prepare.json", payload=summary)
            if isinstance(summary.get("plan"), dict):
                write_taxonomy_operation_artifact(operation, relative_name="plan.json", payload=summary["plan"])
            complete_taxonomy_change_operation(
                operation,
                status="OK" if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else "FAILED",
                failed_phase=None if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else "PREPARE",
            )
            taxonomy_confirmation_state["summary"] = summary
            taxonomy_confirmation_state["prepared_plan_key"] = taxonomy_confirmation_key(summary.get("plan", {}))
            taxonomy_confirmation_state["plan_key"] = None
            taxonomy_confirmation_state["activation_plan"] = None
            taxonomy_confirmation_state["prepared_activation_key"] = None
            taxonomy_confirmation_state["activation_key"] = None
            taxonomy_run_rebuild_button.disabled = True
            taxonomy_activate_button.disabled = True
            taxonomy_plan_field.value = format_taxonomy_plan_lines(summary)
            if summary.get("deployment_id"):
                taxonomy_deployment_id_field.value = str(summary["deployment_id"])
                refresh_taxonomy_state(int(summary["deployment_id"]))
        except Exception as exc:
            taxonomy_status_field.value = f"Prepare failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_refresh(_e: Any) -> None:
        try:
            refresh_taxonomy_state(_selected_deployment_id())
        except Exception as exc:
            taxonomy_status_field.value = f"Refresh failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def _latest_taxonomy_operation() -> tuple[int | None, dict[str, Any] | None]:
        deployment_id = _selected_deployment_id()
        if deployment_id is None:
            return None, None
        operations = list_taxonomy_change_operations(
            deployment_id=deployment_id,
            evidence_root=_TAXONOMY_EVIDENCE_ROOT,
        )
        return deployment_id, operations[0] if operations else None

    def on_taxonomy_show_log(_e: Any) -> None:
        try:
            deployment_id, operation = _latest_taxonomy_operation()
            if deployment_id is None or operation is None:
                taxonomy_log_field.value = "No taxonomy operation logs found."
            else:
                log = read_taxonomy_change_log(
                    deployment_id=deployment_id,
                    operation_id=operation["operation_id"],
                    limit=65536,
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                taxonomy_log_field.value = (
                    f"path={log.get('path')}\nmodified_at={log.get('modified_at')}\n\n"
                    f"{log.get('text', '')}"
                )
        except Exception as exc:
            taxonomy_log_field.value = f"Log read failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_download_log(_e: Any) -> None:
        try:
            deployment_id, operation = _latest_taxonomy_operation()
            if deployment_id is None or operation is None:
                taxonomy_status_field.value = "No downloadable taxonomy log."
            else:
                download = prepare_taxonomy_change_log_download(
                    deployment_id=deployment_id,
                    operation_id=operation["operation_id"],
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                taxonomy_status_field.value = json.dumps(download, sort_keys=True)
                if download.get("status") == "OK":
                    launch_browser_url(page, build_text_log_browser_url(download["path"]))
        except Exception as exc:
            taxonomy_status_field.value = f"Log download failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_download_evidence(_e: Any) -> None:
        try:
            deployment_id, operation = _latest_taxonomy_operation()
            if deployment_id is None or operation is None:
                taxonomy_status_field.value = "No evidence package available."
            else:
                package = prepare_taxonomy_change_evidence_package(
                    deployment_id=deployment_id,
                    operation_id=operation["operation_id"],
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                taxonomy_status_field.value = json.dumps(package, sort_keys=True, default=str)
                launch_browser_url(page, build_text_log_browser_url(package["path"]))
        except Exception as exc:
            taxonomy_status_field.value = f"Evidence package failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_confirm_plan(_e: Any) -> None:
        summary = taxonomy_confirmation_state.get("summary") or {}
        plan = summary.get("plan") or {}
        current_key = taxonomy_confirmation_key(plan)
        taxonomy_confirmation_state["plan_key"] = current_key
        action = taxonomy_rebuild_action_state(
            status="PLANNED",
            safe_to_run=summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"},
            confirmation_valid=current_key == taxonomy_confirmation_state.get("prepared_plan_key"),
            blocking_errors=list(summary.get("blocking_errors", plan.get("blocking_errors", []))),
        )
        taxonomy_run_rebuild_button.disabled = action["run_disabled"]
        taxonomy_status_field.value = "Plan confirmation recorded for current plan hash."
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_run_rebuild(_e: Any) -> None:
        try:
            summary = taxonomy_confirmation_state.get("summary") or {}
            plan = summary.get("plan") or {}
            if taxonomy_confirmation_state.get("plan_key") != taxonomy_confirmation_key(plan):
                taxonomy_status_field.value = "Rebuild blocked: plan confirmation is stale."
            else:
                operation = create_taxonomy_change_operation(
                    deployment_id=summary["deployment_id"],
                    operation_type="REBUILD",
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                with taxonomy_operation_lock_context(
                    deployment_id=summary["deployment_id"],
                    operation_type="REBUILD",
                    operation_id=operation.operation_id,
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                ):
                    run_summary = execute_taxonomy_rebuild(
                        analysis_db=analysis_db_field.value,
                        deployment_id=int(summary["deployment_id"]),
                        proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        date_to=str(plan["date_to"]),
                        scheduler_config_path=config_path,
                        watchlist_path=config.ec_source_layer_watchlist,
                        evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                        confirm_deployment_id=int(summary["deployment_id"]),
                        confirm_proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        confirm_proposed_source_hash=str(plan["proposed_source_sha256"]),
                        confirm_date_from=str(plan["date_from"]),
                        confirm_date_to=str(plan["date_to"]),
                        confirm_rebuild_mode=str(plan["selected_rebuild_mode"]),
                        confirm_plan_hash=str(plan["plan_hash"]),
                        services=_taxonomy_services(),
                    )
                write_taxonomy_operation_artifact(operation, relative_name="run_summary.json", payload=run_summary)
                complete_taxonomy_change_operation(
                    operation,
                    status="OK" if run_summary.get("run_status") in {"READY_TO_ACTIVATE", "NO_CHANGE_READY_TO_ACTIVATE", "ALREADY_ACTIVE"} else "FAILED",
                    failed_phase=run_summary.get("failed_phase"),
                    resume_from_phase=run_summary.get("resume_from_phase"),
                )
                taxonomy_status_field.value = json.dumps(run_summary, indent=2, sort_keys=True, default=str)
                refresh_taxonomy_state(int(summary["deployment_id"]))
        except Exception as exc:
            taxonomy_status_field.value = f"Rebuild failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_resume(_e: Any) -> None:
        try:
            summary = taxonomy_confirmation_state.get("summary") or {}
            plan = summary.get("plan") or {}
            deployment_id = int(summary.get("deployment_id") or _selected_deployment_id() or 0)
            if not deployment_id or not plan:
                taxonomy_status_field.value = "Resume blocked: current UI session has no prepared plan."
            else:
                operation = create_taxonomy_change_operation(
                    deployment_id=deployment_id,
                    operation_type="RESUME",
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                with taxonomy_operation_lock_context(
                    deployment_id=deployment_id,
                    operation_type="RESUME",
                    operation_id=operation.operation_id,
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                ):
                    run_summary = resume_taxonomy_rebuild(
                        analysis_db=analysis_db_field.value,
                        deployment_id=deployment_id,
                        proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        date_to=str(plan["date_to"]),
                        scheduler_config_path=config_path,
                        watchlist_path=config.ec_source_layer_watchlist,
                        evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                        confirm_deployment_id=deployment_id,
                        confirm_proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        confirm_proposed_source_hash=str(plan["proposed_source_sha256"]),
                        confirm_date_from=str(plan["date_from"]),
                        confirm_date_to=str(plan["date_to"]),
                        confirm_rebuild_mode=str(plan["selected_rebuild_mode"]),
                        confirm_plan_hash=str(plan["plan_hash"]),
                        services=_taxonomy_services(resume=True),
                    )
                write_taxonomy_operation_artifact(operation, relative_name="resume_summary.json", payload=run_summary)
                complete_taxonomy_change_operation(
                    operation,
                    status="OK" if run_summary.get("run_status") in {"READY_TO_ACTIVATE", "NO_CHANGE_READY_TO_ACTIVATE", "ALREADY_ACTIVE"} else "FAILED",
                    failed_phase=run_summary.get("failed_phase"),
                    resume_from_phase=run_summary.get("resume_from_phase"),
                )
                taxonomy_status_field.value = json.dumps(run_summary, indent=2, sort_keys=True, default=str)
                refresh_taxonomy_state(deployment_id)
        except Exception as exc:
            taxonomy_status_field.value = f"Resume failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_validate_finalize(_e: Any) -> None:
        try:
            summary = taxonomy_confirmation_state.get("summary") or {}
            plan = summary.get("plan") or {}
            deployment_id = int(summary.get("deployment_id") or _selected_deployment_id() or 0)
            if not deployment_id or not plan:
                taxonomy_status_field.value = "Validation blocked: current UI session has no prepared plan."
            else:
                operation = create_taxonomy_change_operation(
                    deployment_id=deployment_id,
                    operation_type="VALIDATE_FINALIZE",
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                )
                with taxonomy_operation_lock_context(
                    deployment_id=deployment_id,
                    operation_type="VALIDATE_FINALIZE",
                    operation_id=operation.operation_id,
                    evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                ):
                    finalize_summary = validate_and_finalize_taxonomy_rebuild(
                        analysis_db=analysis_db_field.value,
                        deployment_id=deployment_id,
                        proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        date_to=str(plan["date_to"]),
                        scheduler_config_path=config_path,
                    )
                write_taxonomy_operation_artifact(operation, relative_name="finalize_summary.json", payload=finalize_summary)
                complete_taxonomy_change_operation(
                    operation,
                    status="OK" if finalize_summary.get("finalize_status") == "READY_TO_ACTIVATE" else "FAILED",
                    failed_phase=None if finalize_summary.get("finalize_status") == "READY_TO_ACTIVATE" else "VALIDATING",
                )
                taxonomy_status_field.value = json.dumps(finalize_summary, indent=2, sort_keys=True, default=str)
                refresh_taxonomy_state(deployment_id)
        except Exception as exc:
            taxonomy_status_field.value = f"Validation failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_plan_activation(_e: Any) -> None:
        try:
            summary = taxonomy_confirmation_state.get("summary") or {}
            plan = summary.get("plan") or {}
            if not plan:
                taxonomy_status_field.value = "Activation planning requires a prepared plan in the current UI session."
            else:
                activation_plan = plan_taxonomy_activation(
                    analysis_db=analysis_db_field.value,
                    ecosystem_code=DATACENTER_ECOSYSTEM_CODE,
                    deployment_id=int(summary["deployment_id"]),
                    current_taxonomy_version=str(plan["current_taxonomy_version"]),
                    current_taxonomy_csv=str(plan["current_source_reference"]),
                    proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                    proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                    required_signal_date=str(plan["date_to"]),
                    scheduler_config_path=config_path,
                    expected_scheduler_taxonomy_version=str(plan["current_taxonomy_version"]),
                    expected_scheduler_taxonomy_csv=str(plan["current_source_reference"]),
                )
                activation_plan = _activation_plan_with_current_file_hash(activation_plan)
                taxonomy_confirmation_state["activation_plan"] = activation_plan
                taxonomy_confirmation_state["prepared_activation_key"] = (
                    taxonomy_activation_confirmation_key(activation_plan)
                )
                taxonomy_confirmation_state["activation_key"] = None
                taxonomy_status_field.value = json.dumps(activation_plan, indent=2, sort_keys=True, default=str)
                taxonomy_activate_button.disabled = True
        except Exception as exc:
            taxonomy_status_field.value = f"Activation planning failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_confirm_activation(_e: Any) -> None:
        activation_plan = _activation_plan_with_current_file_hash(
            taxonomy_confirmation_state.get("activation_plan") or {}
        )
        current_key = taxonomy_activation_confirmation_key(activation_plan)
        action = taxonomy_activation_action_state(
            orchestration_status=str(taxonomy_confirmation_state.get("orchestration_status") or ""),
            activation_plan_status=str(activation_plan.get("activation_plan_status") or ""),
            safe_to_activate=bool(activation_plan.get("safe_to_activate")),
            confirmation_valid=current_key == taxonomy_confirmation_state.get("prepared_activation_key"),
            blocking_errors=list(activation_plan.get("blocking_errors", [])),
            operation_active=_taxonomy_operation_active(),
        )
        taxonomy_confirmation_state["activation_key"] = (
            current_key if not action["activate_disabled"] else None
        )
        taxonomy_activate_button.disabled = action["activate_disabled"]
        taxonomy_status_field.value = (
            "Activation confirmation recorded for current activation plan."
            if not action["activate_disabled"]
            else "Activation confirmation blocked by current activation plan."
        )
        if hasattr(page, "update"):
            page.update()

    def on_taxonomy_activate(_e: Any) -> None:
        try:
            summary = taxonomy_confirmation_state.get("summary") or {}
            plan = summary.get("plan") or {}
            activation_plan = _activation_plan_with_current_file_hash(
                taxonomy_confirmation_state.get("activation_plan") or {}
            )
            if taxonomy_confirmation_state.get("activation_key") != taxonomy_activation_confirmation_key(activation_plan):
                taxonomy_status_field.value = "Activation blocked: activation confirmation is stale."
            else:
                action = taxonomy_activation_action_state(
                    orchestration_status=str(taxonomy_confirmation_state.get("orchestration_status") or ""),
                    activation_plan_status=str(activation_plan.get("activation_plan_status") or ""),
                    safe_to_activate=bool(activation_plan.get("safe_to_activate")),
                    confirmation_valid=True,
                    blocking_errors=list(activation_plan.get("blocking_errors", [])),
                    operation_active=_taxonomy_operation_active(),
                )
                if action["activate_disabled"]:
                    taxonomy_status_field.value = "Activation blocked: guarded activation plan is not safe."
                else:
                    activation_summary = activate_taxonomy_change(
                        analysis_db=analysis_db_field.value,
                        ecosystem_code=DATACENTER_ECOSYSTEM_CODE,
                        deployment_id=int(summary["deployment_id"]),
                        current_taxonomy_version=str(plan["current_taxonomy_version"]),
                        current_taxonomy_csv=str(plan["current_source_reference"]),
                        proposed_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        proposed_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        required_signal_date=str(plan["date_to"]),
                        confirm_activate_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        expected_scheduler_taxonomy_version=str(plan["proposed_taxonomy_version"]),
                        expected_scheduler_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        scheduler_config_path=config_path,
                        expected_current_scheduler_taxonomy_version=str(plan["current_taxonomy_version"]),
                        expected_current_scheduler_taxonomy_csv=str(plan["current_source_reference"]),
                        target_scheduler_taxonomy_csv=taxonomy_proposed_csv_field.value,
                        config_backup_dir=Path(_TAXONOMY_EVIDENCE_ROOT) / "activation_config_backups",
                    )
                    operation = create_taxonomy_change_operation(
                        deployment_id=summary["deployment_id"],
                        operation_type="ACTIVATE",
                        evidence_root=_TAXONOMY_EVIDENCE_ROOT,
                    )
                    write_taxonomy_operation_artifact(
                        operation,
                        relative_name="activation_result.json",
                        payload=activation_summary,
                    )
                    complete_taxonomy_change_operation(
                        operation,
                        status=(
                            "OK"
                            if activation_summary.get("activation_apply_status") in {"ACTIVE", "NO_CHANGE"}
                            else "FAILED"
                        ),
                        failed_phase=(
                            None
                            if activation_summary.get("activation_apply_status") in {"ACTIVE", "NO_CHANGE"}
                            else "ACTIVATION"
                        ),
                    )
                    activation_status_text = json.dumps(
                        activation_summary,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    )
                    taxonomy_confirmation_state["activation_plan"] = None
                    taxonomy_confirmation_state["prepared_activation_key"] = None
                    taxonomy_confirmation_state["activation_key"] = None
                    taxonomy_activate_button.disabled = True
                    refresh_taxonomy_state(int(summary["deployment_id"]))
                    taxonomy_status_field.value = activation_status_text
        except Exception as exc:
            taxonomy_status_field.value = f"Activation failed: {exc}"
        if hasattr(page, "update"):
            page.update()

    taxonomy_prepare_button = ft.ElevatedButton("Valmistele", on_click=on_taxonomy_prepare)
    taxonomy_refresh_button = ft.ElevatedButton("Päivitä tila", on_click=on_taxonomy_refresh)
    taxonomy_confirm_plan_button = ft.ElevatedButton("Vahvista suunnitelma", on_click=on_taxonomy_confirm_plan)
    taxonomy_run_rebuild_button = ft.ElevatedButton("Käynnistä rebuild", on_click=on_taxonomy_run_rebuild, disabled=True)
    taxonomy_resume_button = ft.ElevatedButton("Jatka epäonnistuneesta vaiheesta", on_click=on_taxonomy_resume, disabled=True)
    taxonomy_validate_button = ft.ElevatedButton("Validoi ja viimeistele", on_click=on_taxonomy_validate_finalize, disabled=True)
    taxonomy_plan_activation_button = ft.ElevatedButton("Suunnittele aktivointi", on_click=on_taxonomy_plan_activation, disabled=True)
    taxonomy_confirm_activation_button = ft.ElevatedButton("Vahvista aktivointi", on_click=on_taxonomy_confirm_activation)
    taxonomy_activate_button = ft.ElevatedButton("Aktivoi", on_click=on_taxonomy_activate, disabled=True)
    taxonomy_show_log_button = ft.ElevatedButton("Näytä loki", on_click=on_taxonomy_show_log)
    taxonomy_download_log_button = ft.ElevatedButton("Lataa loki", on_click=on_taxonomy_download_log)
    taxonomy_download_evidence_button = ft.ElevatedButton("Lataa evidence-paketti", on_click=on_taxonomy_download_evidence)

    scheduler_content = ft.Column(
        [
            osakedata_db_field,
            analysis_db_field,
            log_dir_field,
            timezone_field,
            run_time_field,
            ft.Row([omxh_checkbox, omxs_checkbox, usa_checkbox]),
            technical_relevance_checkbox,
            skip_next_run_text,
            running_status_text,
            ft.Row(
                [
                    save_config_button,
                    reload_config_button,
                    run_now_button,
                    skip_next_run_button,
                    cancel_skip_next_run_button,
                    refresh_logs_button,
                ]
            ),
            status_field,
            summary_field,
            timer_status_field,
            logs_column,
        ],
        spacing=12,
        expand=True,
    )
    taxonomy_content = ft.Column(
        [
            taxonomy_active_field,
            taxonomy_proposed_csv_field,
            ft.Row([taxonomy_rebuild_mode_dropdown, taxonomy_date_from_field, taxonomy_date_to_field]),
            taxonomy_deployment_id_field,
            ft.Row(
                [
                    taxonomy_prepare_button,
                    taxonomy_refresh_button,
                    taxonomy_confirm_plan_button,
                ]
            ),
            ft.Row(
                [
                    taxonomy_run_rebuild_button,
                    taxonomy_resume_button,
                    taxonomy_validate_button,
                    taxonomy_plan_activation_button,
                    taxonomy_confirm_activation_button,
                    taxonomy_activate_button,
                ]
            ),
            taxonomy_plan_field,
            taxonomy_status_field,
            ft.Text("Operaatiot"),
            taxonomy_operations_column,
            ft.Row([taxonomy_show_log_button, taxonomy_download_log_button, taxonomy_download_evidence_button]),
            taxonomy_log_field,
        ],
        spacing=12,
        expand=True,
    )

    refresh_logs_view(config.log_dir)
    try:
        refresh_taxonomy_state(None)
    except Exception as exc:
        taxonomy_active_field.value = f"Taxonomy inspect failed: {exc}"

    page.osakedata_db_field = osakedata_db_field
    page.analysis_db_field = analysis_db_field
    page.log_dir_field = log_dir_field
    page.timezone_field = timezone_field
    page.run_time_field = run_time_field
    page.omxh_checkbox = omxh_checkbox
    page.omxs_checkbox = omxs_checkbox
    page.usa_checkbox = usa_checkbox
    page.technical_relevance_checkbox = technical_relevance_checkbox
    page.save_config_button = save_config_button
    page.reload_config_button = reload_config_button
    page.run_now_button = run_now_button
    page.skip_next_run_button = skip_next_run_button
    page.cancel_skip_next_run_button = cancel_skip_next_run_button
    page.refresh_logs_button = refresh_logs_button
    page.status_field = status_field
    page.summary_field = summary_field
    page.timer_status_field = timer_status_field
    page.running_status_text = running_status_text
    page.logs_column = logs_column
    page.scheduler_content = scheduler_content
    page.taxonomy_content = taxonomy_content
    page.taxonomy_proposed_csv_field = taxonomy_proposed_csv_field
    page.taxonomy_rebuild_mode_dropdown = taxonomy_rebuild_mode_dropdown
    page.taxonomy_date_from_field = taxonomy_date_from_field
    page.taxonomy_date_to_field = taxonomy_date_to_field
    page.taxonomy_deployment_id_field = taxonomy_deployment_id_field
    page.taxonomy_active_field = taxonomy_active_field
    page.taxonomy_plan_field = taxonomy_plan_field
    page.taxonomy_status_field = taxonomy_status_field
    page.taxonomy_log_field = taxonomy_log_field
    page.taxonomy_operations_column = taxonomy_operations_column
    page.taxonomy_prepare_button = taxonomy_prepare_button
    page.taxonomy_refresh_button = taxonomy_refresh_button
    page.taxonomy_confirm_plan_button = taxonomy_confirm_plan_button
    page.taxonomy_run_rebuild_button = taxonomy_run_rebuild_button
    page.taxonomy_resume_button = taxonomy_resume_button
    page.taxonomy_validate_button = taxonomy_validate_button
    page.taxonomy_plan_activation_button = taxonomy_plan_activation_button
    page.taxonomy_confirm_activation_button = taxonomy_confirm_activation_button
    page.taxonomy_activate_button = taxonomy_activate_button
    page.taxonomy_show_log_button = taxonomy_show_log_button
    page.taxonomy_download_log_button = taxonomy_download_log_button
    page.taxonomy_download_evidence_button = taxonomy_download_evidence_button
    page.taxonomy_confirmation_state = taxonomy_confirmation_state

    page.add(
        ft.Tabs(
            tabs=[
                ft.Tab(text="Scheduler", content=scheduler_content),
                ft.Tab(text="Taxonomy", content=taxonomy_content),
            ],
            expand=True,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    initial_config = read_scheduler_config(args.config)

    def _app(page: Any) -> None:
        run_app(page, args.config)

    ft.app(
        target=_app,
        port=args.port,
        view=ft.AppView.WEB_BROWSER,
        assets_dir=initial_config.log_dir,
    )


if __name__ == "__main__":
    main()
