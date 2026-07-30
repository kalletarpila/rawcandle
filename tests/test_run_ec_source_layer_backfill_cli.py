import csv
import sqlite3
from pathlib import Path

from rawcandle.cli import run_ec_source_layer_backfill as cli


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE dc_ticker_swing_signal_daily (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE eco_ecosystem (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def _write_taxonomy_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerow(["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])


def _write_watchlist(path: Path) -> None:
    path.write_text("NVDA\nCRGY\n", encoding="utf-8")


def _base_args(tmp_path: Path) -> list[str]:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    _create_db(db_path)
    _write_taxonomy_csv(taxonomy_path)
    _write_watchlist(watchlist_path)
    return [
        "--db",
        str(db_path),
        "--ecosystem",
        "DATACENTER",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--date-from",
        "2026-05-29",
        "--date-to",
        "2026-06-04",
        "--taxonomy-csv",
        str(taxonomy_path),
        "--watchlist",
        str(watchlist_path),
        "--backup-dir",
        str(backup_dir),
        "--confirm-db",
        str(db_path),
        "--confirm-ecosystem",
        "DATACENTER",
        "--confirm-taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--format",
        "text",
    ]


def _ready_backfill_plan(status: str = "READY_BACKFILL_PLAN", candidate_dates: list[dict[str, str]] | None = None) -> dict[str, object]:
    if candidate_dates is None:
        candidate_dates = [
            {"date": "2026-05-29", "action": "BACKFILL_MISSING"},
            {"date": "2026-06-01", "action": "BACKFILL_MISSING"},
        ]
    return {
        "status": status,
        "source_date_availability": {
            "missing_source_dates": ["2026-05-30", "2026-05-31"],
        },
        "loaded_state": {
            "candidate_dates": candidate_dates,
            "already_loaded_dates": ["2026-06-04"],
            "partial_dates": [],
        },
    }


def _successful_watermark_summary(latest_signal_date: str = "2026-06-01") -> dict[str, object]:
    return {
        "status": "OK",
        "watermark_policy": "ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL",
        "watermark_refresh_performed": True,
        "watermark_advanced": True,
        "watermark_candidate_latest_signal_date": latest_signal_date,
        "watermark_rows_inserted": 4,
        "watermark_rows_updated": 0,
        "watermark_rows_unchanged": 0,
        "watermark_rows_total": 4,
        "watermark_advance_status": "OK",
    }


def _patch_successful_watermark_finalizer(monkeypatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_finalizer(**kwargs):
        calls.append(kwargs)
        return _successful_watermark_summary(str(kwargs["latest_signal_date"]))

    monkeypatch.setattr(cli, "advance_ec_pipeline_watermarks_after_historical_backfill", fake_finalizer)
    return calls


def test_refuses_when_confirm_db_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-db") + 1] = str(tmp_path / "wrong.sqlite")
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_REFUSED" in output
    assert "--confirm-db must exactly match --db" in output


def test_refuses_when_confirm_ecosystem_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-ecosystem") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_REFUSED" in output
    assert "--confirm-ecosystem must exactly match --ecosystem" in output


def test_refuses_when_confirm_taxonomy_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-taxonomy-version") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_REFUSED" in output
    assert "--confirm-taxonomy-version must exactly match --taxonomy-version" in output


def test_refuses_when_backup_dir_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    missing_dir = tmp_path / "missing-backups"
    args[args.index("--backup-dir") + 1] = str(missing_dir)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_REFUSED" in output
    assert "backup_dir does not exist" in output


def test_skips_when_planner_returns_skip_all_dates_already_loaded(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(
        cli,
        "plan_ec_source_layer_backfill",
        lambda **_: _ready_backfill_plan(status="SKIP_ALL_DATES_ALREADY_LOADED", candidate_dates=[]),
    )

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_SKIPPED" in output
    assert "planner reported SKIP_ALL_DATES_ALREADY_LOADED" in output


def test_refuses_when_planner_is_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: {"status": "BLOCKED_TAXONOMY_SOURCE"})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_REFUSED" in output
    assert "planner gate did not pass: BLOCKED_TAXONOMY_SOURCE" in output


def test_creates_backup_before_first_write(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []
    _patch_successful_watermark_finalizer(monkeypatch)

    def fake_backup(**_):
        call_order.append("backup")
        backup_path = tmp_path / "backups" / "backup.sqlite"
        backup_path.write_text("backup", encoding="utf-8")
        return backup_path

    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", fake_backup)
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: (call_order.append("ticker") or {"status": "OK"}))
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    assert call_order == ["backup", "ticker"]


def test_uses_planner_selected_dates_not_independently_inferred_dates(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    seen_dates: list[str] = []
    planner_dates = [{"date": "2026-06-03", "action": "BACKFILL_MISSING"}]
    watermark_calls = _patch_successful_watermark_finalizer(monkeypatch)

    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=planner_dates))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")

    def capture_loader(**kwargs):
        seen_dates.append(str(kwargs["signal_date"]))
        return {"status": "OK"}

    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    assert seen_dates == ["2026-06-03"]
    assert watermark_calls[0]["latest_signal_date"] == "2026-06-03"


def test_runs_four_fact_loaders_per_date_in_correct_order(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []
    loader_kwargs: dict[str, object] = {}
    planner_dates = [
        {"date": "2026-05-29", "action": "BACKFILL_MISSING"},
        {"date": "2026-06-01", "action": "REPLACE_PARTIAL"},
    ]
    _patch_successful_watermark_finalizer(monkeypatch)

    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=planner_dates))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: (call_order.append("backup") or (tmp_path / "backups" / "backup.sqlite")))

    def ticker_loader(**kwargs):
        call_order.append(f"ticker:{kwargs['signal_date']}")
        loader_kwargs[f"ticker:{kwargs['signal_date']}"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def group_signal_loader(**kwargs):
        call_order.append(f"group_signal:{kwargs['signal_date']}")
        loader_kwargs[f"group_signal:{kwargs['signal_date']}"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def synthetic_loader(**kwargs):
        call_order.append(f"synthetic:{kwargs['signal_date']}")
        loader_kwargs[f"synthetic:{kwargs['signal_date']}"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def group_index_loader(**kwargs):
        call_order.append(f"group_index:{kwargs['signal_date']}")
        loader_kwargs[f"group_index:{kwargs['signal_date']}"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", ticker_loader)
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", group_signal_loader)
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", synthetic_loader)
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", group_index_loader)
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **kwargs: (call_order.append(f"coverage:{kwargs['signal_date']}") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **kwargs: (call_order.append(f"parity:{kwargs['signal_date']}") or {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 0}))
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    exit_code = cli.main(args + ["--allow-replace-existing"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert call_order == [
        "backup",
        "ticker:2026-05-29",
        "group_signal:2026-05-29",
        "synthetic:2026-05-29",
        "group_index:2026-05-29",
        "coverage:2026-05-29",
        "parity:2026-05-29",
        "ticker:2026-06-01",
        "group_signal:2026-06-01",
        "synthetic:2026-06-01",
        "group_index:2026-06-01",
        "coverage:2026-06-01",
        "parity:2026-06-01",
    ]
    assert loader_kwargs["ticker:2026-05-29"]["replace_existing"] is False
    assert loader_kwargs["ticker:2026-06-01"]["replace_existing"] is True
    assert "Backfill Status: BACKFILL_COMPLETED" in output


def test_does_not_run_pipeline_watermark_per_historical_date(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    watermark_calls = _patch_successful_watermark_finalizer(monkeypatch)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    for date_result in summary["per_date_results"]:
        assert "pipeline_watermark_summary" not in date_result
    assert len(watermark_calls) == 1
    assert watermark_calls[0]["latest_signal_date"] == "2026-05-29"
    assert summary["watermark_refresh_performed"] is True


def test_runs_coverage_and_parity_audits_per_date(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    called = {"coverage": 0, "parity": 0}
    parity_include_pipeline_watermark_values = []
    planner_dates = [
        {"date": "2026-05-29", "action": "BACKFILL_MISSING"},
        {"date": "2026-06-01", "action": "BACKFILL_MISSING"},
    ]
    _patch_successful_watermark_finalizer(monkeypatch)

    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=planner_dates))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})

    def coverage(**_):
        called["coverage"] += 1
        return {"status": "OK_WITH_WARNINGS"}

    def parity(**kwargs):
        called["parity"] += 1
        parity_include_pipeline_watermark_values.append(kwargs["include_pipeline_watermark"])
        return {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 0}

    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", coverage)
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", parity)
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    assert called == {"coverage": 2, "parity": 2}
    assert parity_include_pipeline_watermark_values == [False, False]


def test_stops_on_ticker_loader_failure_and_reports_backup_path(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    backup_path = tmp_path / "backups" / "backup.sqlite"
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: backup_path)
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "FAILED"})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_FAILED" in output
    assert "backup.sqlite" in output
    assert "Ticker fact loader returned FAILED" in output


def test_stops_on_parity_mismatch_and_reports_failed_date(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 2})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Backfill Status: BACKFILL_FAILED" in output
    assert "failed_date=2026-05-29" in output
    assert "Fact parity audit did not meet acceptance criteria" in output


def test_success_path_returns_completed_dates_and_row_counts(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    planner_dates = [
        {"date": "2026-05-29", "action": "BACKFILL_MISSING"},
        {"date": "2026-06-01", "action": "BACKFILL_MISSING"},
    ]
    _patch_successful_watermark_finalizer(monkeypatch)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=planner_dates))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})

    def row_counts(_, signal_date: str):
        return {
            "ticker_rows": 236,
            "group_signal_rows": 54,
            "synthetic_ohlc_rows": 53,
            "group_index_rows": 54,
        } if signal_date == "2026-05-29" else {
            "ticker_rows": 240,
            "group_signal_rows": 55,
            "synthetic_ohlc_rows": 53,
            "group_index_rows": 55,
        }

    monkeypatch.setattr(cli, "_selected_date_row_counts", row_counts)

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    assert summary["completed_dates"] == ["2026-05-29", "2026-06-01"]
    assert summary["per_date_results"][0]["row_counts"]["ticker_rows"] == 236
    assert summary["per_date_results"][1]["row_counts"]["ticker_rows"] == 240
    assert summary["watermark_candidate_latest_signal_date"] == "2026-06-01"
    assert summary["watermark_rows_total"] == 4


def test_no_scheduler_or_osakedata_paths_are_touched(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    seen_kwargs: list[dict[str, object]] = []
    _patch_successful_watermark_finalizer(monkeypatch)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")

    def capture_loader(**kwargs):
        seen_kwargs.append(kwargs)
        return {"status": "OK"}

    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_COMPLETED"
    assert seen_kwargs
    for kwargs in seen_kwargs:
        assert "osakedata.db" not in str(kwargs)


def test_final_watermark_failure_makes_backfill_fail_after_fact_writes(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_backfill", lambda **_: _ready_backfill_plan(candidate_dates=[{"date": "2026-05-29", "action": "BACKFILL_MISSING"}]))
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
    })
    monkeypatch.setattr(
        cli,
        "advance_ec_pipeline_watermarks_after_historical_backfill",
        lambda **_: (_ for _ in ()).throw(RuntimeError("watermark write failed")),
    )

    summary = cli.run_ec_source_layer_backfill(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        date_from="2026-05-29",
        date_to="2026-06-04",
        taxonomy_csv_path=args[11],
        watchlist_path=args[13],
        backup_dir=args[15],
        confirm_db=args[17],
        confirm_ecosystem=args[19],
        confirm_taxonomy_version=args[21],
    )

    assert summary["status"] == "BACKFILL_FAILED"
    assert summary["completed_dates"] == ["2026-05-29"]
    assert summary["failed_step"] == "advance_ec_pipeline_watermarks_after_historical_backfill"
    assert summary["watermark_advance_status"] == "FAILED"
    assert "watermark write failed" in str(summary["error"])
