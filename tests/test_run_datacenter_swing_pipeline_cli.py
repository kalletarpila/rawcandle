from __future__ import annotations

from pathlib import Path

import pytest

from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from run_datacenter_swing_pipeline import main as run_datacenter_swing_pipeline_main


def _base_args(tmp_path: Path) -> list[str]:
    return [
        "--price-db",
        str(tmp_path / "osakedata.db"),
        "--analysis-db",
        str(tmp_path / "analysis.db"),
        "--taxonomy-csv",
        str(tmp_path / "taxonomy.csv"),
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--signal-date",
        "2026-05-15",
        "--start-date",
        "2026-01-01",
        "--index-base-date",
        "2020-01-01",
        "--output-dir",
        str(tmp_path / "reports"),
    ]


def test_dry_run_prints_planned_stages_and_does_not_call_stage_runners(tmp_path, monkeypatch, capsys):
    def _fail(*args, **kwargs):
        raise AssertionError("stage runner should not be called in dry-run")

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _fail)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _fail)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _fail)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _fail)

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path) + ["--dry-run"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "=== Stage 1/12: Datacenter base index ==="
    assert lines[1].startswith("PLAN --ohlcv-db ")
    assert lines[-1] == "SUMMARY pipeline_status=DRY_RUN"
    assert not (tmp_path / "reports").exists()


def test_pipeline_calls_stages_in_correct_order_and_uses_index_base_date(tmp_path, monkeypatch, capsys):
    calls: list[tuple[str, list[str] | dict[str, object]]] = []

    def _make_cli(name: str):
        def _runner(argv: list[str]) -> int:
            calls.append((name, list(argv)))
            return 0

        return _runner

    def _audit(**kwargs):
        calls.append(("audit", dict(kwargs)))
        return {"summary": {"validation_status": "OK"}}

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(("weekly", dict(kwargs)))
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _make_cli("index"))
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _make_cli("ticker"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _make_cli("group"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _make_cli("synthetic"))
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path)
        + [
            "--expected-ticker-count",
            "236",
            "--expected-group-count",
            "54",
            "--expected-synthetic-ohlc-count",
            "53",
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls] == [
        "index",
        "ticker",
        "group",
        "synthetic",
        "synthetic",
        "synthetic",
        "group",
        "group",
        "ticker",
        "audit",
        "daily",
        "weekly",
    ]
    index_argv = calls[0][1]
    assert index_argv[index_argv.index("--start-date") + 1] == "2020-01-01"
    scanner_argv = calls[8][1]
    assert scanner_argv[scanner_argv.index("--taxonomy-version") + 1] == "DC_TAXONOMY_FULL_V1"
    audit_kwargs = calls[9][1]
    assert audit_kwargs["expected_ticker_count"] == 236
    assert audit_kwargs["expected_group_count"] == 54
    assert audit_kwargs["expected_synthetic_ohlc_count"] == 53
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-4] == "SUMMARY audit_validation_status=OK"
    assert lines[-1] == "SUMMARY pipeline_status=OK"


def test_pipeline_generates_reports_on_audit_warn(tmp_path, monkeypatch, capsys):
    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "WARN"}}

    def _daily(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY audit_validation_status=WARN" in lines
    assert lines[-1] == "SUMMARY pipeline_status=WARN"


def test_pipeline_stops_before_reports_on_audit_fail(tmp_path, monkeypatch, capsys):
    calls: list[str] = []

    def _runner(argv: list[str]) -> int:
        calls.append("stage")
        return 0

    def _audit(**kwargs):
        calls.append("audit")
        return {"summary": {"validation_status": "FAIL"}}

    def _fail_report(**kwargs):
        raise AssertionError("reports must not run after audit FAIL")

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _fail_report)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _fail_report)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code != 0
    assert calls[-1] == "audit"
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY audit_validation_status=FAIL" in lines
    assert lines[-1] == "SUMMARY pipeline_status=FAIL"


def test_skip_audit_and_skip_reports_reduce_stage_count(tmp_path, monkeypatch, capsys):
    def _runner(argv: list[str]) -> int:
        return 0

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--skip-audit", "--skip-reports"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY pipeline_stage_count=9" in lines
    assert "SUMMARY audit_validation_status=SKIPPED" in lines
