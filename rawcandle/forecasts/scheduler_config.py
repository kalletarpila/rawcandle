from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORECAST_SCHEDULER_CONFIG = ROOT / "forecast_scheduler_config.json"
_RUN_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


@dataclass(frozen=True)
class ForecastSchedulerConfig:
    forecasts_db_path: str = str(ROOT / "data" / "forecasts.db")
    fundamentals_db_path: str = str(ROOT / "data" / "fundamentals_v4.db")
    log_dir: str = str(ROOT / "logs" / "forecasts")
    timezone: str = "Europe/Helsinki"
    run_time: str = "14:00"
    skip_next_run: bool = False


def validate_forecast_run_time(value: str) -> str:
    if not _RUN_TIME_PATTERN.fullmatch(str(value)):
        raise ValueError("run_time must use HH:MM")
    hours, minutes = (int(part) for part in str(value).split(":"))
    if hours not in range(24) or minutes not in range(60):
        raise ValueError("run_time must use a valid 24-hour HH:MM value")
    return f"{hours:02d}:{minutes:02d}"


def validate_forecast_timezone(value: str) -> str:
    timezone = str(value).strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {timezone}") from exc
    return timezone


def validate_forecast_scheduler_config(
    config: ForecastSchedulerConfig,
) -> ForecastSchedulerConfig:
    values = asdict(config)
    for key in ("forecasts_db_path", "fundamentals_db_path", "log_dir"):
        values[key] = str(values[key]).strip()
        if not values[key]:
            raise ValueError(f"{key} must be non-empty")
        if any(character in values[key] for character in ("\n", "\r", "\0")):
            raise ValueError(f"{key} contains unsupported control characters")
    values["run_time"] = validate_forecast_run_time(config.run_time)
    values["timezone"] = validate_forecast_timezone(config.timezone)
    if type(config.skip_next_run) is not bool:
        raise ValueError("skip_next_run must be a bool")
    return ForecastSchedulerConfig(**values)


def read_forecast_scheduler_config(
    path: str | Path = DEFAULT_FORECAST_SCHEDULER_CONFIG,
) -> ForecastSchedulerConfig:
    config_path = Path(path)
    if not config_path.exists():
        return validate_forecast_scheduler_config(ForecastSchedulerConfig())
    data = json.loads(config_path.read_text(encoding="utf-8"))
    expected = set(asdict(ForecastSchedulerConfig()))
    extra = set(data) - expected
    if extra:
        raise ValueError(f"unexpected forecast config keys: {sorted(extra)}")
    return validate_forecast_scheduler_config(ForecastSchedulerConfig(**data))


def _write_forecast_scheduler_config_unlocked(
    path: str | Path,
    config: ForecastSchedulerConfig,
) -> None:
    validated = validate_forecast_scheduler_config(config)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temporary:
            json.dump(asdict(validated), temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


@contextmanager
def _forecast_config_lock(path: str | Path):
    config_path = Path(path)
    lock_path = config_path.with_suffix(config_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def write_forecast_scheduler_config(
    path: str | Path,
    config: ForecastSchedulerConfig,
) -> None:
    with _forecast_config_lock(path):
        _write_forecast_scheduler_config_unlocked(path, config)


def set_forecast_skip_next_run(
    path: str | Path,
    *,
    skip: bool,
) -> ForecastSchedulerConfig:
    with _forecast_config_lock(path):
        config = read_forecast_scheduler_config(path)
        updated = ForecastSchedulerConfig(**{**asdict(config), "skip_next_run": skip})
        _write_forecast_scheduler_config_unlocked(path, updated)
        return updated


def consume_forecast_skip_next_run(
    path: str | Path = DEFAULT_FORECAST_SCHEDULER_CONFIG,
) -> bool:
    config_path = Path(path)
    with _forecast_config_lock(config_path):
        config = read_forecast_scheduler_config(config_path)
        if not config.skip_next_run:
            return False
        updated = ForecastSchedulerConfig(
            **{**asdict(config), "skip_next_run": False}
        )
        _write_forecast_scheduler_config_unlocked(config_path, updated)
        return True
