from __future__ import annotations

import pytest

from rawcandle.scheduler.config import (
    DEFAULT_TIMEZONE,
    StockUpdateSchedulerConfig,
    create_default_scheduler_config,
    read_scheduler_config,
    scheduler_config_from_dict,
    scheduler_config_to_dict,
    validate_market_list,
    validate_run_time,
    validate_scheduler_config,
    write_scheduler_config,
)

_LEGACY_DASHBOARD_CONFIG_KEYS = {
    "datacenter_dashboard_fallback_to_reports": True,
    "datacenter_dashboard_reports_reference_db": (
        "/home/kalle/projects/rawcandle/temp/datacenter_dashboard_reports_reference.db"
    ),
    "datacenter_dashboard_reports_reference_enabled": True,
    "datacenter_dashboard_reports_reference_html_output_dir": (
        "/home/kalle/projects/rawcandle/swing_reports"
    ),
    "datacenter_dashboard_run_acceptance_report": True,
    "datacenter_dashboard_source_mode": "enrichment",
    "datacenter_enrichment_apply_migrations": False,
    "datacenter_enrichment_enabled": True,
    "datacenter_v3_reports_ecosystem": "DATACENTER",
    "datacenter_v3_reports_enabled": False,
    "datacenter_v3_reports_output_dir": "/home/kalle/projects/rawcandle/swing_reports/v3",
    "datacenter_v3_reports_taxonomy_version": "DC_TAXONOMY_FULL_V1",
}


def test_default_scheduler_config_uses_omxh_and_omxs_not_usa():
    config = create_default_scheduler_config(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert config.skip_next_run is False
    assert config.technical_relevance_enabled is False
    assert config.ec_source_layer_enabled is False
    assert config.ec_source_layer_ecosystem == "DATACENTER"
    assert config.ec_source_layer_taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert config.ec_source_layer_mode == "refresh_latest"
    assert config.ec_source_layer_require_legacy_reports_success is True
    assert config.ec_source_layer_only_on_new_signal_date is True


def test_market_validation_normalizes_case_whitespace_and_deduplicates():
    assert validate_market_list([" OMXH ", "omxs", "OMXH"]) == ["omxh", "omxs"]


def test_unsupported_market_raises_value_error():
    with pytest.raises(ValueError):
        validate_market_list(["omxh", "lse"])


@pytest.mark.parametrize("run_time", ["05:30", "00:00", "23:59"])
def test_run_time_validation_accepts_valid_values(run_time):
    assert validate_run_time(run_time) == run_time


@pytest.mark.parametrize("run_time", ["24:00", "12:60", "5:30", "bad"])
def test_run_time_validation_rejects_invalid_values(run_time):
    with pytest.raises(ValueError):
        validate_run_time(run_time)


def test_scheduler_config_serialization_roundtrip():
    config = StockUpdateSchedulerConfig(
        enabled_markets=[" OMXH ", "OMXS", "OMXH"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone=DEFAULT_TIMEZONE,
        skip_next_run=False,
        technical_relevance_enabled=True,
        ec_source_layer_enabled=True,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv="/tmp/taxonomy.csv",
        ec_source_layer_watchlist="/tmp/watchlist.txt",
        ec_source_layer_backup_dir="/tmp/backups",
        ec_source_layer_mode="refresh_latest",
        ec_source_layer_require_legacy_reports_success=True,
        ec_source_layer_only_on_new_signal_date=False,
        datacenter_dashboard_reports_reference_html_output_dir=(
            "/home/kalle/projects/rawcandle/swing_reports"
        ),
    )

    serialized = scheduler_config_to_dict(config)
    deserialized = scheduler_config_from_dict(serialized)

    assert deserialized == StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone=DEFAULT_TIMEZONE,
        skip_next_run=False,
        technical_relevance_enabled=True,
        ec_source_layer_enabled=True,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv="/tmp/taxonomy.csv",
        ec_source_layer_watchlist="/tmp/watchlist.txt",
        ec_source_layer_backup_dir="/tmp/backups",
        ec_source_layer_mode="refresh_latest",
        ec_source_layer_require_legacy_reports_success=True,
        ec_source_layer_only_on_new_signal_date=False,
        datacenter_dashboard_reports_reference_html_output_dir=(
            "/home/kalle/projects/rawcandle/swing_reports"
        ),
    )


def test_scheduler_config_json_write_read_roundtrip(tmp_path):
    path = tmp_path / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        skip_next_run=True,
        technical_relevance_enabled=True,
    )

    write_scheduler_config(str(path), config)
    loaded = read_scheduler_config(str(path))

    assert loaded == validate_scheduler_config(config)


def test_write_scheduler_config_does_not_create_parent_directories(tmp_path):
    missing_parent = tmp_path / "missing" / "scheduler.json"
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        skip_next_run=False,
    )

    with pytest.raises(Exception):
        write_scheduler_config(str(missing_parent), config)


def test_scheduler_config_from_dict_requires_expected_keys():
    with pytest.raises(ValueError):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh", "omxs"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
            }
        )


def test_scheduler_config_from_dict_rejects_unexpected_keys():
    with pytest.raises(ValueError):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh", "omxs"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                "unexpected": "value",
            }
        )


def test_scheduler_config_from_dict_accepts_known_retired_dashboard_keys():
    config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh", "usa"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
            "technical_relevance_enabled": True,
            "timezone": "Europe/Helsinki",
            **_LEGACY_DASHBOARD_CONFIG_KEYS,
        }
    )

    assert config.datacenter_dashboard_source_mode == "enrichment"
    assert config.datacenter_enrichment_enabled is True
    assert config.datacenter_dashboard_reports_reference_enabled is True
    assert config.datacenter_v3_reports_output_dir == (
        "/home/kalle/projects/rawcandle/swing_reports/v3"
    )


def test_scheduler_config_roundtrip_preserves_known_retired_dashboard_keys(tmp_path):
    path = tmp_path / "scheduler.json"
    source = {
        "enabled_markets": ["omxh", "usa"],
        "run_time": "05:30",
        "osakedata_db_path": "/tmp/osakedata.db",
        "analysis_db_path": "/tmp/analysis.db",
        "log_dir": "/tmp/logs",
        "technical_relevance_enabled": True,
        "timezone": "Europe/Helsinki",
        **_LEGACY_DASHBOARD_CONFIG_KEYS,
    }

    config = scheduler_config_from_dict(source)
    write_scheduler_config(str(path), config)
    roundtripped = read_scheduler_config(str(path))
    serialized = scheduler_config_to_dict(roundtripped)

    for key, value in _LEGACY_DASHBOARD_CONFIG_KEYS.items():
        assert serialized[key] == value


def test_scheduler_config_rejects_truly_unknown_key_even_with_known_legacy_keys():
    with pytest.raises(ValueError, match="Unexpected config keys: totally_unknown"):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh", "usa"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                **_LEGACY_DASHBOARD_CONFIG_KEYS,
                "totally_unknown": "value",
            }
        )


def test_validate_scheduler_config_returns_new_instance():
    config = StockUpdateSchedulerConfig(
        enabled_markets=[" OMXH ", "OMXS", "OMXH"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        skip_next_run=True,
        technical_relevance_enabled=True,
    )

    validated = validate_scheduler_config(config)

    assert validated is not config
    assert config.enabled_markets == [" OMXH ", "OMXS", "OMXH"]
    assert validated.enabled_markets == ["omxh", "omxs"]
    assert config.skip_next_run is True
    assert validated.skip_next_run is True


def test_scheduler_config_to_dict_includes_skip_next_run():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        skip_next_run=True,
        technical_relevance_enabled=True,
    )

    data = scheduler_config_to_dict(config)

    assert data["skip_next_run"] is True


def test_scheduler_config_to_dict_includes_technical_relevance_enabled():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        technical_relevance_enabled=True,
    )

    data = scheduler_config_to_dict(config)

    assert data["technical_relevance_enabled"] is True


def test_scheduler_config_from_dict_defaults_missing_skip_next_run_to_false():
    config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh", "omxs"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
        }
    )

    assert config.skip_next_run is False
    assert config.technical_relevance_enabled is False
    assert config.ec_source_layer_enabled is False
    assert config.ec_source_layer_taxonomy_csv is None
    assert config.ec_source_layer_watchlist is None
    assert config.ec_source_layer_backup_dir is None
    assert config.ec_source_layer_mode == "refresh_latest"


def test_scheduler_config_to_dict_includes_ec_source_layer_fields():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        ec_source_layer_enabled=True,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv="/tmp/taxonomy.csv",
        ec_source_layer_watchlist="/tmp/watchlist.txt",
        ec_source_layer_backup_dir="/tmp/backups",
        ec_source_layer_mode="refresh_latest",
        ec_source_layer_require_legacy_reports_success=False,
        ec_source_layer_only_on_new_signal_date=False,
    )

    data = scheduler_config_to_dict(config)

    assert data["ec_source_layer_enabled"] is True
    assert data["ec_source_layer_ecosystem"] == "DATACENTER"
    assert data["ec_source_layer_taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert data["ec_source_layer_taxonomy_csv"] == "/tmp/taxonomy.csv"
    assert data["ec_source_layer_watchlist"] == "/tmp/watchlist.txt"
    assert data["ec_source_layer_backup_dir"] == "/tmp/backups"
    assert data["ec_source_layer_mode"] == "refresh_latest"
    assert data["ec_source_layer_require_legacy_reports_success"] is False
    assert data["ec_source_layer_only_on_new_signal_date"] is False


def test_enabled_ec_source_layer_without_required_paths_fails_validation():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        ec_source_layer_enabled=True,
    )

    with pytest.raises(ValueError, match="ec_source_layer_taxonomy_csv"):
        validate_scheduler_config(config)


def test_enabled_ec_source_layer_with_required_fields_passes_validation():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        ec_source_layer_enabled=True,
        ec_source_layer_ecosystem="DATACENTER",
        ec_source_layer_taxonomy_version="DC_TAXONOMY_FULL_V1",
        ec_source_layer_taxonomy_csv="/tmp/taxonomy.csv",
        ec_source_layer_watchlist="/tmp/watchlist.txt",
        ec_source_layer_backup_dir="/tmp/backups",
        ec_source_layer_mode="refresh_latest",
        ec_source_layer_require_legacy_reports_success=True,
        ec_source_layer_only_on_new_signal_date=True,
    )

    validated = validate_scheduler_config(config)

    assert validated.ec_source_layer_enabled is True
    assert validated.ec_source_layer_taxonomy_csv == "/tmp/taxonomy.csv"
    assert validated.ec_source_layer_watchlist == "/tmp/watchlist.txt"
    assert validated.ec_source_layer_backup_dir == "/tmp/backups"


def test_disabled_ec_source_layer_with_missing_paths_passes_validation():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        ec_source_layer_enabled=False,
        ec_source_layer_taxonomy_csv=None,
        ec_source_layer_watchlist=None,
        ec_source_layer_backup_dir=None,
    )

    validated = validate_scheduler_config(config)

    assert validated.ec_source_layer_enabled is False


def test_invalid_ec_source_layer_mode_fails_validation():
    config = StockUpdateSchedulerConfig(
        enabled_markets=["omxh", "omxs"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        ec_source_layer_mode="replace_all",
    )

    with pytest.raises(ValueError, match="ec_source_layer_mode"):
        validate_scheduler_config(config)


def test_scheduler_config_from_dict_accepts_skip_next_run_true():
    config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh", "omxs"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
            "skip_next_run": True,
        }
    )

    assert config.skip_next_run is True
    assert config.technical_relevance_enabled is False


def test_scheduler_config_from_dict_accepts_technical_relevance_enabled_true():
    config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh", "omxs"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
            "technical_relevance_enabled": True,
        }
    )

    assert config.technical_relevance_enabled is True


def test_scheduler_config_from_dict_defaults_missing_technical_relevance_enabled_to_false():
    config = scheduler_config_from_dict(
        {
            "enabled_markets": ["omxh", "omxs"],
            "run_time": "05:30",
            "osakedata_db_path": "/tmp/osakedata.db",
            "analysis_db_path": "/tmp/analysis.db",
            "log_dir": "/tmp/logs",
        }
    )

    assert config.technical_relevance_enabled is False


@pytest.mark.parametrize("skip_next_run", ["true", 1, None])
def test_scheduler_config_from_dict_rejects_non_bool_skip_next_run(skip_next_run):
    with pytest.raises(ValueError):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh", "omxs"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                "skip_next_run": skip_next_run,
            }
        )


@pytest.mark.parametrize("technical_relevance_enabled", ["true", 1, None])
def test_scheduler_config_from_dict_rejects_non_bool_technical_relevance_enabled(
    technical_relevance_enabled,
):
    with pytest.raises(ValueError):
        scheduler_config_from_dict(
            {
                "enabled_markets": ["omxh", "omxs"],
                "run_time": "05:30",
                "osakedata_db_path": "/tmp/osakedata.db",
                "analysis_db_path": "/tmp/analysis.db",
                "log_dir": "/tmp/logs",
                "technical_relevance_enabled": technical_relevance_enabled,
            }
        )
