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


def test_default_scheduler_config_uses_omxh_and_omxs_not_usa():
    config = create_default_scheduler_config(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert config.skip_next_run is False


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


def test_validate_scheduler_config_returns_new_instance():
    config = StockUpdateSchedulerConfig(
        enabled_markets=[" OMXH ", "OMXS", "OMXH"],
        run_time="05:30",
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        skip_next_run=True,
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
    )

    data = scheduler_config_to_dict(config)

    assert data["skip_next_run"] is True


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
