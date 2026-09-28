from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from rawcandle.forecasts.scheduler_config import (
    DEFAULT_FORECAST_SCHEDULER_CONFIG,
    ForecastSchedulerConfig,
    read_forecast_scheduler_config,
)


FORECAST_SCHEDULER_NAME = "rawcandle-forecast-daily"
FORECAST_SCHEDULE_LOCAL = "14:00"
FORECAST_TIMEZONE = "Europe/Helsinki"
FORECAST_TIMEOUT_SECONDS = 9000
FORECAST_DAILY_COMMAND = (
    "/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe"
)


def _systemd_argument(value: str | Path) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def service_unit_text(
    repo_root: str | Path,
    *,
    config: ForecastSchedulerConfig | None = None,
    config_path: str | Path = DEFAULT_FORECAST_SCHEDULER_CONFIG,
) -> str:
    root = Path(repo_root).resolve()
    current = config or read_forecast_scheduler_config(config_path)
    log_path = Path(current.log_dir).resolve() / "forecast_scheduler.log"
    return (
        "[Unit]\n"
        "Description=RawCandle bounded Yahoo forecast daily collection\n"
        "Wants=network-online.target\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={root}\n"
        f"Environment=PYTHONPATH={root}\n"
        "Environment="
        f"{_systemd_argument(f'RAWCANDLE_FORECAST_DB={Path(current.forecasts_db_path).resolve()}')}\n"
        "Environment="
        f"{_systemd_argument(f'RAWCANDLE_FUNDAMENTALS_DB={Path(current.fundamentals_db_path).resolve()}')}\n"
        "ExecCondition=/usr/bin/python3 -m rawcandle.cli.forecasts "
        "scheduler-allow-run --config "
        f"{_systemd_argument(Path(config_path).resolve())}\n"
        f"ExecStart={FORECAST_DAILY_COMMAND}\n"
        f"TimeoutStartSec={FORECAST_TIMEOUT_SECONDS}\n"
        f"StandardOutput=append:{log_path}\n"
        f"StandardError=append:{log_path}\n"
        "SyslogIdentifier=rawcandle-forecast-daily\n"
    )


def timer_unit_text(config: ForecastSchedulerConfig | None = None) -> str:
    current = config or read_forecast_scheduler_config()
    return (
        "[Unit]\n"
        "Description=Run bounded RawCandle forecast collection daily\n\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {current.run_time}:00 {current.timezone}\n"
        "Persistent=true\n"
        "AccuracySec=1min\n"
        f"Unit={FORECAST_SCHEDULER_NAME}.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def install_scheduler(
    *, repo_root: str | Path, user_unit_dir: str | Path | None = None,
    apply: bool = False, activate: bool = True,
    config: ForecastSchedulerConfig | None = None,
    config_path: str | Path = DEFAULT_FORECAST_SCHEDULER_CONFIG,
) -> dict[str, Any]:
    current = config or read_forecast_scheduler_config(config_path)
    directory = Path(user_unit_dir or Path.home() / ".config" / "systemd" / "user")
    service_path = directory / f"{FORECAST_SCHEDULER_NAME}.service"
    timer_path = directory / f"{FORECAST_SCHEDULER_NAME}.timer"
    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "service_path": str(service_path),
        "timer_path": str(timer_path),
        "schedule_local": current.run_time,
        "timezone": current.timezone,
        "command": FORECAST_DAILY_COMMAND,
        "timeout_seconds": FORECAST_TIMEOUT_SECONDS,
        "full_bounded_universe": True,
        "independent_from_stock_scheduler": True,
        "automatic_retry": False,
    }
    if not apply:
        return report
    directory.mkdir(parents=True, exist_ok=True)
    log_dir = Path(current.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "forecast_scheduler.log").touch(exist_ok=True)
    service_path.write_text(
        service_unit_text(repo_root, config=current, config_path=config_path),
        encoding="utf-8",
    )
    timer_path.write_text(timer_unit_text(current), encoding="utf-8")
    if user_unit_dir is None:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    if activate:
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", timer_path.name],
            check=True,
        )
    return report | {"activated": activate}
