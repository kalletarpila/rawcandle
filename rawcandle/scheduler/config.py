from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


SUPPORTED_MARKETS = ("omxh", "omxs", "usa")
DEFAULT_ENABLED_MARKETS = ["omxh", "omxs"]
DEFAULT_RUN_TIME = "05:30"
DEFAULT_TIMEZONE = "Europe/Helsinki"
_RUN_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")
_REQUIRED_CONFIG_KEYS = {
    "enabled_markets",
    "run_time",
    "osakedata_db_path",
    "analysis_db_path",
    "log_dir",
}
_OPTIONAL_CONFIG_KEYS = {"timezone", "skip_next_run", "technical_relevance_enabled"}


@dataclass(eq=True)
class StockUpdateSchedulerConfig:
    enabled_markets: List[str] = field(default_factory=lambda: list(DEFAULT_ENABLED_MARKETS))
    run_time: str = DEFAULT_RUN_TIME
    osakedata_db_path: str = ""
    analysis_db_path: str = ""
    log_dir: str = ""
    timezone: str = DEFAULT_TIMEZONE
    skip_next_run: bool = False
    technical_relevance_enabled: bool = False


def validate_market_list(markets: List[str]) -> List[str]:
    normalized_markets: List[str] = []
    seen = set()

    for market in markets:
        normalized_market = market.strip().lower()
        if normalized_market not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market: {market}")
        if normalized_market in seen:
            continue
        seen.add(normalized_market)
        normalized_markets.append(normalized_market)

    return normalized_markets


def validate_run_time(run_time: str) -> str:
    if not _RUN_TIME_PATTERN.match(run_time):
        raise ValueError(f"Invalid run_time format: {run_time}")

    hours_str, minutes_str = run_time.split(":")
    hours = int(hours_str)
    minutes = int(minutes_str)
    if not 0 <= hours <= 23:
        raise ValueError(f"Invalid run_time hour: {run_time}")
    if not 0 <= minutes <= 59:
        raise ValueError(f"Invalid run_time minute: {run_time}")

    return f"{hours:02d}:{minutes:02d}"


def validate_scheduler_config(
    config: StockUpdateSchedulerConfig,
) -> StockUpdateSchedulerConfig:
    enabled_markets = validate_market_list(config.enabled_markets)
    run_time = validate_run_time(config.run_time)
    if not config.osakedata_db_path:
        raise ValueError("osakedata_db_path must be non-empty")
    if not config.analysis_db_path:
        raise ValueError("analysis_db_path must be non-empty")
    if not config.log_dir:
        raise ValueError("log_dir must be non-empty")
    if type(config.skip_next_run) is not bool:
        raise ValueError("skip_next_run must be a bool")
    if type(config.technical_relevance_enabled) is not bool:
        raise ValueError("technical_relevance_enabled must be a bool")

    return StockUpdateSchedulerConfig(
        enabled_markets=enabled_markets,
        run_time=run_time,
        osakedata_db_path=config.osakedata_db_path,
        analysis_db_path=config.analysis_db_path,
        log_dir=config.log_dir,
        timezone=config.timezone,
        skip_next_run=config.skip_next_run,
        technical_relevance_enabled=config.technical_relevance_enabled,
    )


def scheduler_config_to_dict(config: StockUpdateSchedulerConfig) -> Dict[str, Any]:
    validated_config = validate_scheduler_config(config)
    return asdict(validated_config)


def scheduler_config_from_dict(data: Dict[str, Any]) -> StockUpdateSchedulerConfig:
    keys = set(data.keys())
    missing_keys = _REQUIRED_CONFIG_KEYS - keys
    extra_keys = keys - (_REQUIRED_CONFIG_KEYS | _OPTIONAL_CONFIG_KEYS)
    if missing_keys:
        missing_keys_str = ", ".join(sorted(missing_keys))
        raise ValueError(f"Missing required config keys: {missing_keys_str}")
    if extra_keys:
        extra_keys_str = ", ".join(sorted(extra_keys))
        raise ValueError(f"Unexpected config keys: {extra_keys_str}")

    config = StockUpdateSchedulerConfig(
        enabled_markets=data["enabled_markets"],
        run_time=data["run_time"],
        osakedata_db_path=data["osakedata_db_path"],
        analysis_db_path=data["analysis_db_path"],
        log_dir=data["log_dir"],
        timezone=data.get("timezone", DEFAULT_TIMEZONE),
        skip_next_run=data.get("skip_next_run", False),
        technical_relevance_enabled=data.get("technical_relevance_enabled", False),
    )
    return validate_scheduler_config(config)


def write_scheduler_config(path: str, config: StockUpdateSchedulerConfig) -> None:
    data = scheduler_config_to_dict(config)
    with open(path, "w", encoding="utf-8") as config_file:
        json.dump(data, config_file, indent=2, sort_keys=True)


def read_scheduler_config(path: str) -> StockUpdateSchedulerConfig:
    with open(path, "r", encoding="utf-8") as config_file:
        data = json.load(config_file)
    return scheduler_config_from_dict(data)


def create_default_scheduler_config(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    log_dir: str,
) -> StockUpdateSchedulerConfig:
    config = StockUpdateSchedulerConfig(
        enabled_markets=list(DEFAULT_ENABLED_MARKETS),
        run_time=DEFAULT_RUN_TIME,
        osakedata_db_path=osakedata_db_path,
        analysis_db_path=analysis_db_path,
        log_dir=log_dir,
        timezone=DEFAULT_TIMEZONE,
        skip_next_run=False,
        technical_relevance_enabled=False,
    )
    return validate_scheduler_config(config)
