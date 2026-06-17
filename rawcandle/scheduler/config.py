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
_OPTIONAL_CONFIG_KEYS.update(
    {
        "datacenter_dashboard_fallback_to_reports",
        "datacenter_dashboard_reports_reference_db",
        "datacenter_dashboard_reports_reference_enabled",
        "datacenter_dashboard_reports_reference_html_output_dir",
        "datacenter_dashboard_run_acceptance_report",
        "datacenter_dashboard_source_mode",
        "datacenter_enrichment_apply_migrations",
        "datacenter_enrichment_enabled",
        "datacenter_v3_reports_ecosystem",
        "datacenter_v3_reports_enabled",
        "datacenter_v3_reports_output_dir",
        "datacenter_v3_reports_taxonomy_version",
        "ec_source_layer_enabled",
        "ec_source_layer_ecosystem",
        "ec_source_layer_taxonomy_version",
        "ec_source_layer_taxonomy_csv",
        "ec_source_layer_watchlist",
        "ec_source_layer_backup_dir",
        "ec_source_layer_mode",
        "ec_source_layer_require_legacy_reports_success",
        "ec_source_layer_only_on_new_signal_date",
    }
)
SUPPORTED_EC_SOURCE_LAYER_MODES = ("refresh_latest",)


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
    datacenter_dashboard_fallback_to_reports: bool = True
    datacenter_dashboard_reports_reference_db: str | None = None
    datacenter_dashboard_reports_reference_enabled: bool = False
    datacenter_dashboard_reports_reference_html_output_dir: str | None = None
    datacenter_dashboard_run_acceptance_report: bool = True
    datacenter_dashboard_source_mode: str = "reports"
    datacenter_enrichment_apply_migrations: bool = False
    datacenter_enrichment_enabled: bool = False
    datacenter_v3_reports_ecosystem: str = "DATACENTER"
    datacenter_v3_reports_enabled: bool = False
    datacenter_v3_reports_output_dir: str | None = None
    datacenter_v3_reports_taxonomy_version: str = "DC_TAXONOMY_FULL_V1"
    ec_source_layer_enabled: bool = False
    ec_source_layer_ecosystem: str = "DATACENTER"
    ec_source_layer_taxonomy_version: str = "DC_TAXONOMY_FULL_V1"
    ec_source_layer_taxonomy_csv: str | None = None
    ec_source_layer_watchlist: str | None = None
    ec_source_layer_backup_dir: str | None = None
    ec_source_layer_mode: str = "refresh_latest"
    ec_source_layer_require_legacy_reports_success: bool = True
    ec_source_layer_only_on_new_signal_date: bool = True


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
    if type(config.datacenter_dashboard_fallback_to_reports) is not bool:
        raise ValueError("datacenter_dashboard_fallback_to_reports must be a bool")
    if type(config.datacenter_dashboard_reports_reference_enabled) is not bool:
        raise ValueError("datacenter_dashboard_reports_reference_enabled must be a bool")
    if type(config.datacenter_dashboard_run_acceptance_report) is not bool:
        raise ValueError("datacenter_dashboard_run_acceptance_report must be a bool")
    if type(config.datacenter_enrichment_apply_migrations) is not bool:
        raise ValueError("datacenter_enrichment_apply_migrations must be a bool")
    if type(config.datacenter_enrichment_enabled) is not bool:
        raise ValueError("datacenter_enrichment_enabled must be a bool")
    if type(config.datacenter_v3_reports_enabled) is not bool:
        raise ValueError("datacenter_v3_reports_enabled must be a bool")
    if type(config.ec_source_layer_enabled) is not bool:
        raise ValueError("ec_source_layer_enabled must be a bool")
    if config.ec_source_layer_mode not in SUPPORTED_EC_SOURCE_LAYER_MODES:
        raise ValueError(
            "ec_source_layer_mode must be one of: "
            + ", ".join(SUPPORTED_EC_SOURCE_LAYER_MODES)
        )
    if type(config.ec_source_layer_require_legacy_reports_success) is not bool:
        raise ValueError("ec_source_layer_require_legacy_reports_success must be a bool")
    if type(config.ec_source_layer_only_on_new_signal_date) is not bool:
        raise ValueError("ec_source_layer_only_on_new_signal_date must be a bool")
    if config.ec_source_layer_enabled:
        if not config.ec_source_layer_ecosystem:
            raise ValueError("ec_source_layer_ecosystem must be non-empty when ec_source_layer_enabled is true")
        if not config.ec_source_layer_taxonomy_version:
            raise ValueError(
                "ec_source_layer_taxonomy_version must be non-empty when ec_source_layer_enabled is true"
            )
        if not config.ec_source_layer_taxonomy_csv:
            raise ValueError("ec_source_layer_taxonomy_csv must be non-empty when ec_source_layer_enabled is true")
        if not config.ec_source_layer_watchlist:
            raise ValueError("ec_source_layer_watchlist must be non-empty when ec_source_layer_enabled is true")
        if not config.ec_source_layer_backup_dir:
            raise ValueError("ec_source_layer_backup_dir must be non-empty when ec_source_layer_enabled is true")
    return StockUpdateSchedulerConfig(
        enabled_markets=enabled_markets,
        run_time=run_time,
        osakedata_db_path=config.osakedata_db_path,
        analysis_db_path=config.analysis_db_path,
        log_dir=config.log_dir,
        timezone=config.timezone,
        skip_next_run=config.skip_next_run,
        technical_relevance_enabled=config.technical_relevance_enabled,
        datacenter_dashboard_fallback_to_reports=(
            config.datacenter_dashboard_fallback_to_reports
        ),
        datacenter_dashboard_reports_reference_db=(
            config.datacenter_dashboard_reports_reference_db
        ),
        datacenter_dashboard_reports_reference_enabled=(
            config.datacenter_dashboard_reports_reference_enabled
        ),
        datacenter_dashboard_reports_reference_html_output_dir=(
            config.datacenter_dashboard_reports_reference_html_output_dir
        ),
        datacenter_dashboard_run_acceptance_report=(
            config.datacenter_dashboard_run_acceptance_report
        ),
        datacenter_dashboard_source_mode=config.datacenter_dashboard_source_mode,
        datacenter_enrichment_apply_migrations=(
            config.datacenter_enrichment_apply_migrations
        ),
        datacenter_enrichment_enabled=config.datacenter_enrichment_enabled,
        datacenter_v3_reports_ecosystem=config.datacenter_v3_reports_ecosystem,
        datacenter_v3_reports_enabled=config.datacenter_v3_reports_enabled,
        datacenter_v3_reports_output_dir=config.datacenter_v3_reports_output_dir,
        datacenter_v3_reports_taxonomy_version=(
            config.datacenter_v3_reports_taxonomy_version
        ),
        ec_source_layer_enabled=config.ec_source_layer_enabled,
        ec_source_layer_ecosystem=config.ec_source_layer_ecosystem,
        ec_source_layer_taxonomy_version=config.ec_source_layer_taxonomy_version,
        ec_source_layer_taxonomy_csv=config.ec_source_layer_taxonomy_csv,
        ec_source_layer_watchlist=config.ec_source_layer_watchlist,
        ec_source_layer_backup_dir=config.ec_source_layer_backup_dir,
        ec_source_layer_mode=config.ec_source_layer_mode,
        ec_source_layer_require_legacy_reports_success=(
            config.ec_source_layer_require_legacy_reports_success
        ),
        ec_source_layer_only_on_new_signal_date=(
            config.ec_source_layer_only_on_new_signal_date
        ),
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
        datacenter_dashboard_fallback_to_reports=data.get(
            "datacenter_dashboard_fallback_to_reports", True
        ),
        datacenter_dashboard_reports_reference_db=data.get(
            "datacenter_dashboard_reports_reference_db"
        ),
        datacenter_dashboard_reports_reference_enabled=data.get(
            "datacenter_dashboard_reports_reference_enabled", False
        ),
        datacenter_dashboard_reports_reference_html_output_dir=data.get(
            "datacenter_dashboard_reports_reference_html_output_dir"
        ),
        datacenter_dashboard_run_acceptance_report=data.get(
            "datacenter_dashboard_run_acceptance_report", True
        ),
        datacenter_dashboard_source_mode=data.get(
            "datacenter_dashboard_source_mode", "reports"
        ),
        datacenter_enrichment_apply_migrations=data.get(
            "datacenter_enrichment_apply_migrations", False
        ),
        datacenter_enrichment_enabled=data.get("datacenter_enrichment_enabled", False),
        datacenter_v3_reports_ecosystem=data.get(
            "datacenter_v3_reports_ecosystem", "DATACENTER"
        ),
        datacenter_v3_reports_enabled=data.get("datacenter_v3_reports_enabled", False),
        datacenter_v3_reports_output_dir=data.get("datacenter_v3_reports_output_dir"),
        datacenter_v3_reports_taxonomy_version=data.get(
            "datacenter_v3_reports_taxonomy_version", "DC_TAXONOMY_FULL_V1"
        ),
        ec_source_layer_enabled=data.get("ec_source_layer_enabled", False),
        ec_source_layer_ecosystem=data.get("ec_source_layer_ecosystem", "DATACENTER"),
        ec_source_layer_taxonomy_version=data.get(
            "ec_source_layer_taxonomy_version", "DC_TAXONOMY_FULL_V1"
        ),
        ec_source_layer_taxonomy_csv=data.get("ec_source_layer_taxonomy_csv"),
        ec_source_layer_watchlist=data.get("ec_source_layer_watchlist"),
        ec_source_layer_backup_dir=data.get("ec_source_layer_backup_dir"),
        ec_source_layer_mode=data.get("ec_source_layer_mode", "refresh_latest"),
        ec_source_layer_require_legacy_reports_success=data.get(
            "ec_source_layer_require_legacy_reports_success", True
        ),
        ec_source_layer_only_on_new_signal_date=data.get(
            "ec_source_layer_only_on_new_signal_date", True
        ),
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
        datacenter_dashboard_fallback_to_reports=True,
        datacenter_dashboard_reports_reference_db=None,
        datacenter_dashboard_reports_reference_enabled=False,
        datacenter_dashboard_reports_reference_html_output_dir=None,
        datacenter_dashboard_run_acceptance_report=True,
        datacenter_dashboard_source_mode="reports",
        datacenter_enrichment_apply_migrations=False,
        datacenter_enrichment_enabled=False,
        datacenter_v3_reports_ecosystem="DATACENTER",
        datacenter_v3_reports_enabled=False,
        datacenter_v3_reports_output_dir=None,
        datacenter_v3_reports_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_enabled=False,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv=None,
        ec_source_layer_watchlist=None,
        ec_source_layer_backup_dir=None,
        ec_source_layer_mode="refresh_latest",
        ec_source_layer_require_legacy_reports_success=True,
        ec_source_layer_only_on_new_signal_date=True,
    )
    return validate_scheduler_config(config)
