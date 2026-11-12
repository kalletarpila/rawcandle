"""Existing disabled flag survives reload; other native dispatch stays intact."""

from dataclasses import replace
import json
from pathlib import Path

from rawcandle.scheduler import runner
from rawcandle.scheduler.config import read_scheduler_config, write_scheduler_config
from rawcandle.scheduler.runtime_state import read_scheduler_status


def test_full_workflow_hold_skips_finance_and_preserves_other_dispatch_after_reload(
    tmp_path, monkeypatch
):
    # Native config contract, isolated paths; never run a real price/DC/finance job.
    production = read_scheduler_config("scheduler_config.json")
    for name in ("osakedata.db", "analysis.db"):
        (tmp_path / name).touch()
    config = replace(
        production,
        osakedata_db_path=str(tmp_path / "osakedata.db"),
        analysis_db_path=str(tmp_path / "analysis.db"),
        log_dir=str(tmp_path / "logs"),
        enabled_markets=["omxh", "usa"],
        fundamentals_refresh_preview_enabled=False,
        fundamentals_refresh_mode="FULL_WORKFLOW",
        technical_relevance_enabled=True,
    )
    path = tmp_path / "scheduler.json"
    write_scheduler_config(str(path), config)
    original = path.read_bytes()
    calls = []

    def market(**kwargs):
        calls.append(("PRICE_STOCKCORE", kwargs["market"]))
        return runner.ScheduledMarketRunResult(
            market=kwargs["market"],
            started_at_utc="start",
            finished_at_utc="finish",
            exit_code=0,
            summary_status=runner.STATUS_OK,
            log_path="fixture",
            summary_lines=[],
        )

    def technical(**kwargs):
        calls.append(("TECHNICAL", kwargs["target_market"]))
        return runner.TechnicalRelevancePostStepResult(
            attempted=1, enabled=True, status=runner.STATUS_OK, market="usa"
        )

    def dc(**kwargs):
        calls.append(("DATACENTER", kwargs["target_market"]))
        return runner.DatacenterPostStepResult(
            attempted=1, status=runner.STATUS_OK, market="usa"
        )

    def ec(**kwargs):
        calls.append(("EC_SOURCE", kwargs["target_market"]))
        return runner.EcSourceLayerRefreshPostStepResult(
            attempted=1, status=runner.STATUS_OK
        )

    monkeypatch.setattr(runner, "_run_one_market", market)
    monkeypatch.setattr(runner, "_run_technical_relevance_post_step", technical)
    monkeypatch.setattr(runner, "_run_datacenter_post_step", dc)
    monkeypatch.setattr(runner, "_run_ec_source_layer_refresh_post_step", ec)

    def forbidden(*args, **kwargs):
        raise AssertionError("Fundamentals HOLD bypassed")

    monkeypatch.setattr(
        runner, "_run_fundamentals_refresh_preview_post_step", forbidden
    )
    for n in range(2):
        loaded = read_scheduler_config(str(path))
        assert loaded.fundamentals_refresh_preview_enabled is False
        result = runner.run_scheduler_config(config_path=str(path))
        assert result.fundamentals_refresh_preview_attempted == 0
        assert result.fundamentals_refresh_final_outcome == "DISABLED"
        assert result.overall_status == runner.STATUS_OK
        assert path.read_bytes() == original
    assert (
        calls
        == [
            ("PRICE_STOCKCORE", "omxh"),
            ("PRICE_STOCKCORE", "usa"),
            ("TECHNICAL", "usa"),
            ("DATACENTER", "usa"),
            ("EC_SOURCE", "usa"),
        ]
        * 2
    )
    # Native status query has no dispatch/write behavior.
    before = {
        str(p): p.read_bytes() for p in (tmp_path / "logs").iterdir() if p.is_file()
    }
    assert read_scheduler_status(config.log_dir)["is_running"] is False
    assert before == {
        str(p): p.read_bytes() for p in (tmp_path / "logs").iterdir() if p.is_file()
    }
