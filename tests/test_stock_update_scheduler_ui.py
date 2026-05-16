from __future__ import annotations

import json

import pytest

from dev_tools.stock_update_scheduler_ui import (
    build_config_from_ui_values,
    list_scheduler_log_files,
    load_latest_scheduler_summary,
)
from rawcandle.scheduler.config import read_scheduler_config, write_scheduler_config


def test_load_latest_scheduler_summary_picks_newest_by_filename_timestamp(tmp_path):
    older = tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json"
    newer = tmp_path / "stock_update_scheduler_summary_20260516T020000Z.json"
    unrelated = tmp_path / "not_a_summary.json"

    older.write_text(json.dumps({"overall_status": "OK", "marker": "older"}), encoding="utf-8")
    newer.write_text(json.dumps({"overall_status": "OK", "marker": "newer"}), encoding="utf-8")
    unrelated.write_text(json.dumps({"marker": "ignore"}), encoding="utf-8")

    summary = load_latest_scheduler_summary(str(tmp_path))

    assert summary == {"overall_status": "OK", "marker": "newer"}


def test_load_latest_scheduler_summary_returns_none_when_no_summary_exists(tmp_path):
    assert load_latest_scheduler_summary(str(tmp_path)) is None


def test_list_scheduler_log_files_returns_recent_logs_newest_first(tmp_path):
    files = [
        tmp_path / "stock_update_scheduler_summary_20260516T010000Z.json",
        tmp_path / "stock_update_omxh_20260516T020000Z.log",
        tmp_path / "stock_update_omxs_20260516T030000Z.log",
        tmp_path / "ignore_me.txt",
    ]
    for path in files:
        path.write_text("x", encoding="utf-8")

    entries = list_scheduler_log_files(str(tmp_path))

    assert [entry["filename"] for entry in entries] == [
        "stock_update_omxs_20260516T030000Z.log",
        "stock_update_omxh_20260516T020000Z.log",
        "stock_update_scheduler_summary_20260516T010000Z.json",
    ]
    assert entries[0]["path"].endswith("stock_update_omxs_20260516T030000Z.log")


def test_build_config_from_ui_values_normalizes_markets():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
    )

    assert config.enabled_markets == ["omxh", "omxs"]


def test_build_config_from_ui_values_does_not_include_usa_unless_selected():
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", " omxs "],
    )

    assert config.enabled_markets == ["omxh", "omxs"]
    assert "usa" not in config.enabled_markets


def test_build_config_from_ui_values_invalid_run_time_raises_value_error():
    with pytest.raises(ValueError):
        build_config_from_ui_values(
            osakedata_db_path="/tmp/osakedata.db",
            analysis_db_path="/tmp/analysis.db",
            log_dir="/tmp/logs",
            timezone="Europe/Helsinki",
            run_time="5:30",
            selected_markets=["OMXH"],
        )


def test_config_write_read_roundtrip_through_existing_config_module(tmp_path):
    config = build_config_from_ui_values(
        osakedata_db_path="/tmp/osakedata.db",
        analysis_db_path="/tmp/analysis.db",
        log_dir="/tmp/logs",
        timezone="Europe/Helsinki",
        run_time="05:30",
        selected_markets=["OMXH", "OMXS"],
    )
    path = tmp_path / "scheduler.json"

    write_scheduler_config(str(path), config)
    loaded = read_scheduler_config(str(path))

    assert loaded == config
