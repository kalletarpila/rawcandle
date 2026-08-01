import csv
import sqlite3
from pathlib import Path

from rawcandle.cli import run_ec_source_layer_refresh as cli


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


def _ready_refresh_plan(
    signal_date: str = "2026-06-06",
    status: str = "READY_REFRESH_NEW_DATE",
    compatibility_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "selected_date_info": {"selected_signal_date": signal_date},
    } | ({"compatibility_summary": compatibility_summary} if compatibility_summary else {})


def _drift_compatibility_summary() -> dict[str, object]:
    return {
        "status": "OK",
        "watchlist_membership_status": "DRIFT_DETECTED",
        "watchlist_sync_required": True,
        "watchlist_source_member_count": 37,
        "watchlist_loaded_member_count": 16,
        "watchlist_missing_in_loaded_count": 28,
        "watchlist_loaded_only_count": 7,
        "watchlist_missing_in_loaded": ["AAPL", "AMD"],
        "watchlist_loaded_only": ["AEHR"],
    }


def test_refuses_when_confirm_db_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-db") + 1] = str(tmp_path / "wrong.sqlite")
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_REFUSED" in output
    assert "--confirm-db must exactly match --db" in output


def test_refuses_when_confirm_ecosystem_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-ecosystem") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_REFUSED" in output
    assert "--confirm-ecosystem must exactly match --ecosystem" in output


def test_refuses_when_confirm_taxonomy_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-taxonomy-version") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_REFUSED" in output
    assert "--confirm-taxonomy-version must exactly match --taxonomy-version" in output


def test_refuses_when_backup_dir_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    missing_dir = tmp_path / "missing-backups"
    args[args.index("--backup-dir") + 1] = str(missing_dir)
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_REFUSED" in output
    assert "backup_dir does not exist" in output


def test_skips_when_planner_returns_skip_up_to_date(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan(status="SKIP_UP_TO_DATE"))

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_SKIPPED" in output
    assert "planner returned SKIP_UP_TO_DATE" in output


def test_refuses_when_planner_is_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(
        cli,
        "plan_ec_source_layer_refresh",
        lambda **_: {"status": "BLOCKED_TAXONOMY_SOURCE", "selected_date_info": {"selected_signal_date": "2026-06-06"}},
    )

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_REFUSED" in output
    assert "planner gate did not pass: BLOCKED_TAXONOMY_SOURCE" in output


def test_creates_backup_before_first_write(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []

    def fake_backup(**_):
        call_order.append("backup")
        backup_path = tmp_path / "backups" / "backup.sqlite"
        backup_path.write_text("backup", encoding="utf-8")
        return backup_path

    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", fake_backup)
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: (call_order.append("ticker") or {"status": "OK"}))
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["status"] == "REFRESH_COMPLETED"
    assert call_order == ["backup", "ticker"]


def test_ready_refresh_with_watchlist_drift_executes_without_membership_write(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []

    monkeypatch.setattr(
        cli,
        "plan_ec_source_layer_refresh",
        lambda **_: _ready_refresh_plan(compatibility_summary=_drift_compatibility_summary()),
    )
    monkeypatch.setattr(
        cli,
        "_create_backup",
        lambda **_: (call_order.append("backup") or (tmp_path / "backups" / "backup.sqlite")),
    )
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: (call_order.append("ticker") or {"status": "OK"}))
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["status"] == "REFRESH_COMPLETED"
    assert summary["watchlist_membership_status"] == "DRIFT_DETECTED"
    assert summary["watchlist_sync_required"] is True
    assert summary["watchlist_missing_in_loaded_count"] == 28
    assert summary["watchlist_loaded_only_count"] == 7
    assert call_order == ["backup", "ticker"]
    assert not hasattr(cli, "load_datacenter_watchlist_to_ec_sidecar")


def test_runs_loaders_with_replace_existing_true_in_correct_order(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []
    loader_kwargs: dict[str, object] = {}

    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan(status="READY_REFRESH_REPLACE_DATE"))
    monkeypatch.setattr(
        cli,
        "_create_backup",
        lambda **_: (call_order.append("backup") or (tmp_path / "backups" / "backup.sqlite")),
    )

    def ticker_loader(**kwargs):
        call_order.append("ticker")
        loader_kwargs["ticker"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def group_signal_loader(**kwargs):
        call_order.append("group_signal")
        loader_kwargs["group_signal"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def synthetic_loader(**kwargs):
        call_order.append("synthetic")
        loader_kwargs["synthetic"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def group_index_loader(**kwargs):
        call_order.append("group_index")
        loader_kwargs["group_index"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    def watermark_loader(**kwargs):
        call_order.append("watermark")
        loader_kwargs["watermark"] = kwargs
        return {"status": "OK_WITH_WARNINGS"}

    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", ticker_loader)
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", group_signal_loader)
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", synthetic_loader)
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", group_index_loader)
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", watermark_loader)
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: (call_order.append("coverage") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: (call_order.append("parity") or {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 0}))
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    exit_code = cli.main(args + ["--allow-replace-date"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert call_order == ["backup", "ticker", "group_signal", "synthetic", "group_index", "watermark", "coverage", "parity"]
    assert loader_kwargs["ticker"]["replace_existing"] is True
    assert loader_kwargs["group_signal"]["replace_existing"] is True
    assert loader_kwargs["synthetic"]["replace_existing"] is True
    assert loader_kwargs["group_index"]["replace_existing"] is True
    assert loader_kwargs["watermark"]["replace_existing"] is True
    assert "Refresh Status: REFRESH_COMPLETED" in output


def test_does_not_call_taxonomy_watchlist_loaders_or_migrations(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    import_names = set(cli.__dict__.keys())
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["status"] == "REFRESH_COMPLETED"
    assert "apply_ec_sidecar_migration" not in import_names
    assert "load_datacenter_taxonomy_to_ec_sidecar" not in import_names
    assert "load_datacenter_watchlist_to_ec_sidecar" not in import_names


def test_stops_on_ticker_loader_failure_and_reports_backup(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    backup_path = tmp_path / "backups" / "backup.sqlite"
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: backup_path)
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "FAILED"})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_FAILED" in output
    assert "backup.sqlite" in output
    assert "Ticker fact loader returned FAILED" in output


def test_success_path_runs_coverage_and_parity_audits(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    called = {"coverage": 0, "parity": 0}

    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})

    def coverage(**_):
        called["coverage"] += 1
        return {"status": "OK_WITH_WARNINGS"}

    def parity(**_):
        called["parity"] += 1
        return {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 0}

    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", coverage)
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", parity)
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["status"] == "REFRESH_COMPLETED"
    assert called == {"coverage": 1, "parity": 1}


def test_parity_mismatch_fails_refresh(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 2})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Refresh Status: REFRESH_FAILED" in output
    assert "Fact parity audit did not meet acceptance criteria" in output


def test_success_path_returns_selected_date_row_counts(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["ticker_rows"] == 236
    assert summary["group_signal_rows"] == 54
    assert summary["synthetic_ohlc_rows"] == 53
    assert summary["group_index_rows"] == 54
    assert summary["watermark_rows"] == 15


def test_no_scheduler_or_osakedata_paths_are_touched(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    seen_kwargs: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "plan_ec_source_layer_refresh", lambda **_: _ready_refresh_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")

    def capture_loader(**kwargs):
        seen_kwargs.append(kwargs)
        return {"status": "OK"}

    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", capture_loader)
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", capture_loader)
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **kwargs: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_selected_date_row_counts", lambda *_: {
        "ticker_rows": 236,
        "group_signal_rows": 54,
        "synthetic_ohlc_rows": 53,
        "group_index_rows": 54,
        "watermark_rows": 15,
    })

    summary = cli.run_ec_source_layer_refresh(
        db_path=args[1],
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=args[11],
        confirm_db=args[13],
        confirm_ecosystem=args[15],
        confirm_taxonomy_version=args[17],
    )

    assert summary["status"] == "REFRESH_COMPLETED"
    assert seen_kwargs
    for kwargs in seen_kwargs:
        assert "osakedata.db" not in str(kwargs)
