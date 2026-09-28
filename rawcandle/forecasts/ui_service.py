from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rawcandle.forecasts.hardening import (
    ForecastDailyAlreadyRunningError,
    classify_drift,
    forecast_daily_lock,
    health_report,
)
from rawcandle.forecasts.operator import report_run
from rawcandle.forecasts.scheduler import (
    FORECAST_DAILY_COMMAND,
    FORECAST_SCHEDULER_NAME,
    FORECAST_TIMEOUT_SECONDS,
    install_scheduler,
)
from rawcandle.forecasts.scheduler_config import (
    DEFAULT_FORECAST_SCHEDULER_CONFIG,
    ForecastSchedulerConfig,
    read_forecast_scheduler_config,
    set_forecast_skip_next_run,
    validate_forecast_scheduler_config,
    write_forecast_scheduler_config,
)
from rawcandle.forecasts.schema import connect_forecasts_db


FORECAST_LOG_DOWNLOAD_ROUTE = "/forecast/logs"
FORECAST_LOG_PATTERN = re.compile(r"^forecast_(?:scheduler|run_[0-9TZ]+)\.log$")


def _run_systemctl(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *arguments], check=False,
        capture_output=True, text=True, timeout=5.0,
    )


def _systemctl_value(*arguments: str) -> str:
    process = _run_systemctl(*arguments)
    return (process.stdout or process.stderr).strip()


def _unit_path(name: str) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / name


def _read_on_calendar(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OnCalendar="):
            return line.partition("=")[2]
    return None


def read_forecast_timer_status() -> dict[str, Any]:
    timer_name = f"{FORECAST_SCHEDULER_NAME}.timer"
    service_name = f"{FORECAST_SCHEDULER_NAME}.service"
    timer_path = _unit_path(timer_name)
    service_path = _unit_path(service_name)
    error = None
    try:
        enabled = _systemctl_value("is-enabled", timer_name)
        timer_active = _systemctl_value("is-active", timer_name)
        service_active = _systemctl_value("is-active", service_name)
        service_exit_value = _systemctl_value(
            "show", service_name, "-p", "ExecMainStatus", "--value"
        )
        next_run = _systemctl_value(
            "show", timer_name, "-p", "NextElapseUSecRealtime", "--value"
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        enabled = timer_active = service_active = "unknown"
        service_exit_value = ""
        next_run = ""
        error = str(exc)
    try:
        service_exit_status = int(service_exit_value)
    except (TypeError, ValueError):
        service_exit_status = None
    return {
        "installed": timer_path.is_file() and service_path.is_file(),
        "enabled": enabled,
        "active": timer_active,
        "status_summary": f"timer={timer_active}; service={service_active}",
        "service_status": service_active,
        "service_exit_status": service_exit_status,
        "on_calendar": _read_on_calendar(timer_path),
        "timezone": (
            (_read_on_calendar(timer_path) or "").rsplit(" ", 1)[-1] or None
        ),
        "timer_path": str(timer_path),
        "service_path": str(service_path),
        "next_run_local": next_run or None,
        "timeout_seconds": FORECAST_TIMEOUT_SECONDS,
        "command": FORECAST_DAILY_COMMAND,
        "error": error,
    }


def save_forecast_config_and_sync_timer(
    *,
    config_path: str | Path,
    config: ForecastSchedulerConfig,
) -> dict[str, Any]:
    validated = validate_forecast_scheduler_config(config)
    timer_name = f"{FORECAST_SCHEDULER_NAME}.timer"
    enabled_before = _systemctl_value("is-enabled", timer_name) == "enabled"
    write_forecast_scheduler_config(config_path, validated)
    install_scheduler(
        repo_root=Path(__file__).resolve().parents[2],
        apply=True,
        activate=False,
        config=validated,
        config_path=config_path,
    )
    return {
        "status": "OK",
        "message": "Forecast config saved; timer updated without starting service.",
        "enabled_preserved": enabled_before,
        "timer": read_forecast_timer_status(),
    }


def set_forecast_skip(config_path: str | Path, *, skip: bool) -> ForecastSchedulerConfig:
    return set_forecast_skip_next_run(config_path, skip=skip)


def forecast_skip_label(config: ForecastSchedulerConfig) -> str:
    return "Next scheduled run: SKIP" if config.skip_next_run else "Next scheduled run: RUN"


def start_forecast_run_now(config: ForecastSchedulerConfig) -> dict[str, Any]:
    validated = validate_forecast_scheduler_config(config)
    try:
        with forecast_daily_lock(validated.forecasts_db_path):
            pass
    except ForecastDailyAlreadyRunningError:
        return {"status": "OVERLAP_ACTIVE", "message": "Forecast run is already active."}

    log_dir = Path(validated.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"forecast_run_{stamp}.log"
    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "RAWCANDLE_FORECAST_DB": str(Path(validated.forecasts_db_path).resolve()),
        "RAWCANDLE_FUNDAMENTALS_DB": str(
            Path(validated.fundamentals_db_path).resolve()
        ),
    })
    command = FORECAST_DAILY_COMMAND.split(" ")
    with log_path.open("ab") as output:
        process = subprocess.Popen(
            command, cwd=Path(__file__).resolve().parents[2], env=environment,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
        )
    return {
        "status": "STARTED", "pid": process.pid,
        "command": FORECAST_DAILY_COMMAND, "log_path": str(log_path),
    }


def _elapsed_seconds(started: str | None, completed: str | None) -> float | None:
    if not started or not completed:
        return None
    start = datetime.fromisoformat(started.replace("Z", "+00:00"))
    finish = datetime.fromisoformat(completed.replace("Z", "+00:00"))
    return round((finish - start).total_seconds(), 3)


def read_forecast_latest_summary(config: ForecastSchedulerConfig) -> dict[str, Any]:
    database = Path(config.forecasts_db_path)
    with connect_forecasts_db(database) as connection:
        run = connection.execute(
            "SELECT * FROM forecast_run ORDER BY started_at_utc DESC LIMIT 1"
        ).fetchone()
        if run is None:
            return {"overall_status": "NO_RUN"}
        run_id = str(run["run_id"])
        scope = json.loads(run["scope_json"])
        persisted_fetches = int(connection.execute(
            "SELECT COUNT(*) FROM forecast_fetch WHERE run_id=?", (run_id,)
        ).fetchone()[0])
    report = report_run(run_id, forecast_db=database)
    health = health_report(forecast_db=database)
    symbols = scope.get("symbols", [])
    expected_fetches = len(symbols) * 3
    identity = report.get("identity", {})
    fiscal = report.get("fiscal_link", {})
    quality = report.get("provider_quality", {})
    drift_path_counts = quality.get("schema_drift_path_counts") or {
        path: 1 for path in quality.get("schema_drift_paths", [])
    }
    drift_paths = [
        path
        for path, count in drift_path_counts.items()
        for _ in range(int(count))
    ]
    drift = classify_drift(drift_paths)
    database_health = health.get("database", {})
    return {
        "overall_status": str(run["status"]),
        "run_id": run_id,
        "started_at": run["started_at_utc"],
        "completed_at": run["completed_at_utc"],
        "elapsed_seconds": _elapsed_seconds(
            run["started_at_utc"], run["completed_at_utc"]
        ),
        "universe_version": (scope.get("universe") or {}).get("version_id"),
        "symbols_selected": len(symbols),
        "requests_attempted": report.get("family_fetches_attempted", 0),
        "persisted_fetches": persisted_fetches,
        "expected_fetches": expected_fetches,
        "acquisition": report.get("acquisition", {}),
        "identity_resolved": sum(
            int(value) for key, value in identity.items()
            if key not in {"AMBIGUOUS", "UNRESOLVED"}
        ),
        "identity_ambiguous": int(identity.get("AMBIGUOUS", 0)),
        "identity_unresolved": int(identity.get("UNRESOLVED", 0)),
        "fiscal_linked": int(fiscal.get("LINKED", 0)),
        "fiscal_ambiguous": int(fiscal.get("AMBIGUOUS", 0)),
        "fiscal_unresolved": int(fiscal.get("UNRESOLVED", 0)),
        "retries": int(quality.get("retry_count", 0)),
        "drift_policy_version": drift["policy_version"],
        "known_ignored_schema_drift_occurrences": drift["known_ignored_count"],
        "known_ignored_schema_drift_paths": drift[
            "known_ignored_distinct_count"
        ],
        "unknown_schema_drift_occurrences": drift["unknown_drift_count"],
        "unknown_schema_drift_paths": drift["unknown_drift_distinct_count"],
        "quick_check": database_health.get("quick_check"),
        "schema_version": database_health.get("schema_version"),
        "db_size_bytes": database_health.get("size_bytes"),
        "snapshot_count": sum(
            int(value) for value in (health.get("history", {}).get(
                "snapshot_count_by_family", {}
            )).values()
        ),
        "raw_evidence_bytes": health.get("provider_quality", {}).get(
            "raw_evidence_bytes"
        ),
        "rate_limits": int(quality.get("rate_limit_count", 0)),
    }


def list_forecast_logs(log_dir: str, *, limit: int = 20) -> list[dict[str, Any]]:
    directory = Path(log_dir).resolve()
    if not directory.is_dir():
        return []
    entries = []
    for path in directory.iterdir():
        if not path.is_file() or not FORECAST_LOG_PATTERN.fullmatch(path.name):
            continue
        stat = path.stat()
        entries.append({
            "filename": path.name,
            "type": "scheduler" if path.name == "forecast_scheduler.log" else "manual_run",
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, timezone.utc
            ).isoformat(),
        })
    entries.sort(key=lambda item: item["modified_at"], reverse=True)
    return entries[:limit]


def resolve_forecast_log(log_dir: str, filename: str) -> Path:
    if Path(filename).name != filename or not FORECAST_LOG_PATTERN.fullmatch(filename):
        raise ValueError("unsupported forecast log path")
    directory = Path(log_dir).resolve()
    candidate = (directory / filename).resolve()
    if candidate.parent != directory or not candidate.is_file():
        raise FileNotFoundError(filename)
    return candidate


def forecast_config_dict(config: ForecastSchedulerConfig) -> dict[str, Any]:
    return asdict(config)
