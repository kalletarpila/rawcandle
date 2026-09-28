from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


FORECAST_SCHEDULER_NAME = "rawcandle-forecast-daily"
FORECAST_SCHEDULE_LOCAL = "14:00"
FORECAST_TIMEZONE = "Europe/Helsinki"
FORECAST_TIMEOUT_SECONDS = 9000
FORECAST_DAILY_COMMAND = (
    "/usr/bin/python3 -m rawcandle.cli.forecasts daily --full-bounded-universe"
)


def service_unit_text(repo_root: str | Path) -> str:
    root = Path(repo_root).resolve()
    return (
        "[Unit]\n"
        "Description=RawCandle bounded Yahoo forecast daily collection\n"
        "Wants=network-online.target\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={root}\n"
        f"Environment=PYTHONPATH={root}\n"
        f"ExecStart={FORECAST_DAILY_COMMAND}\n"
        f"TimeoutStartSec={FORECAST_TIMEOUT_SECONDS}\n"
        "SyslogIdentifier=rawcandle-forecast-daily\n"
    )


def timer_unit_text() -> str:
    return (
        "[Unit]\n"
        "Description=Run bounded RawCandle forecast collection daily\n\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {FORECAST_SCHEDULE_LOCAL}:00 {FORECAST_TIMEZONE}\n"
        "Persistent=true\n"
        "AccuracySec=1min\n"
        f"Unit={FORECAST_SCHEDULER_NAME}.service\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def install_scheduler(
    *, repo_root: str | Path, user_unit_dir: str | Path | None = None,
    apply: bool = False, activate: bool = True,
) -> dict[str, Any]:
    directory = Path(user_unit_dir or Path.home() / ".config" / "systemd" / "user")
    service_path = directory / f"{FORECAST_SCHEDULER_NAME}.service"
    timer_path = directory / f"{FORECAST_SCHEDULER_NAME}.timer"
    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "service_path": str(service_path),
        "timer_path": str(timer_path),
        "schedule_local": FORECAST_SCHEDULE_LOCAL,
        "timezone": FORECAST_TIMEZONE,
        "command": FORECAST_DAILY_COMMAND,
        "timeout_seconds": FORECAST_TIMEOUT_SECONDS,
        "full_bounded_universe": True,
        "independent_from_stock_scheduler": True,
        "automatic_retry": False,
    }
    if not apply:
        return report
    directory.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service_unit_text(repo_root), encoding="utf-8")
    timer_path.write_text(timer_unit_text(), encoding="utf-8")
    if activate:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", timer_path.name],
            check=True,
        )
    return report | {"activated": activate}
