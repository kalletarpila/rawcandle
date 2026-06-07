import csv
import sqlite3
from pathlib import Path

from rawcandle.cli import run_ec_source_layer_build as cli


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


def _ready_plan(signal_date: str = "2026-06-05") -> dict[str, object]:
    return {
        "status": "READY_NO_WRITE_PLAN",
        "selected_date_info": {"selected_signal_date": signal_date},
    }


def test_refuses_when_confirm_db_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-db") + 1] = str(tmp_path / "wrong.sqlite")
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_REFUSED" in output
    assert "--confirm-db must exactly match --db" in output


def test_refuses_when_confirm_ecosystem_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-ecosystem") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_REFUSED" in output
    assert "--confirm-ecosystem must exactly match --ecosystem" in output


def test_refuses_when_confirm_taxonomy_mismatches(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    args[args.index("--confirm-taxonomy-version") + 1] = "WRONG"
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_REFUSED" in output
    assert "--confirm-taxonomy-version must exactly match --taxonomy-version" in output


def test_refuses_when_backup_dir_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    missing_dir = tmp_path / "missing-backups"
    args[args.index("--backup-dir") + 1] = str(missing_dir)
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_REFUSED" in output
    assert "backup_dir does not exist" in output


def test_refuses_when_planner_is_blocked(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(
        cli,
        "plan_ec_source_layer_build",
        lambda **_: {"status": "BLOCKED_EXISTING_EC_SCHEMA", "selected_date_info": {"selected_signal_date": None}},
    )

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_REFUSED" in output
    assert "planner gate did not pass: BLOCKED_EXISTING_EC_SCHEMA" in output


def test_creates_backup_before_first_write(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []

    def fake_plan(**_):
        return _ready_plan()

    def fake_backup(**_):
        call_order.append("backup")
        backup_path = tmp_path / "backups" / "backup.sqlite"
        backup_path.write_text("backup", encoding="utf-8")
        return backup_path

    def fake_migration(_db_path: str) -> None:
        call_order.append("migration")

    monkeypatch.setattr(cli, "plan_ec_source_layer_build", fake_plan)
    monkeypatch.setattr(cli, "_create_backup", fake_backup)
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", fake_migration)
    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_datacenter_watchlist_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_collect_ec_row_counts", lambda _: {"ec_ecosystem": 1})

    summary = cli.run_ec_source_layer_build(
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

    assert summary["status"] == "BUILD_COMPLETED"
    assert call_order == ["backup", "migration"]


def test_runs_steps_in_correct_order_on_fixture_success_path(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    call_order: list[str] = []

    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())
    monkeypatch.setattr(
        cli,
        "_create_backup",
        lambda **_: (call_order.append("backup") or (tmp_path / "backups" / "backup.sqlite")),
    )
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", lambda _db: call_order.append("migration"))
    monkeypatch.setattr(
        cli,
        "load_datacenter_taxonomy_to_ec_sidecar",
        lambda **_: (call_order.append("taxonomy") or {"status": "OK", "taxonomy_rows": 329}),
    )
    monkeypatch.setattr(
        cli,
        "load_datacenter_watchlist_to_ec_sidecar",
        lambda **_: (call_order.append("watchlist") or {"status": "OK_WITH_WARNINGS", "watchlist_only_tickers": ["CRGY"]}),
    )
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: (call_order.append("ticker") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: (call_order.append("group_signal") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: (call_order.append("synthetic") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: (call_order.append("group_index") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: (call_order.append("watermark") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: (call_order.append("coverage") or {"status": "OK_WITH_WARNINGS"}))
    monkeypatch.setattr(
        cli,
        "audit_dc_ec_fact_parity",
        lambda **_: (call_order.append("parity") or {"status": "OK_WITH_WARNINGS", "total_mismatch_count": 0}),
    )
    monkeypatch.setattr(cli, "_collect_ec_row_counts", lambda _: {"ec_ecosystem": 1, "ec_ticker_signal_daily": 236})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert call_order == [
        "backup",
        "migration",
        "taxonomy",
        "watchlist",
        "ticker",
        "group_signal",
        "synthetic",
        "group_index",
        "watermark",
        "coverage",
        "parity",
    ]
    assert "EC Source Layer Build" in output
    assert "Build Status: BUILD_COMPLETED" in output
    assert "Final Row Counts" in output


def test_stops_on_taxonomy_load_failure_and_reports_backup(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    backup_path = tmp_path / "backups" / "backup.sqlite"

    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: backup_path)
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", lambda _db: None)

    def fail_taxonomy(**_):
        raise RuntimeError("taxonomy load exploded")

    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", fail_taxonomy)

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_FAILED" in output
    assert "backup.sqlite" in output
    assert "taxonomy load exploded" in output


def test_stops_on_fact_loader_failure_and_reports_completed_steps(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", lambda _db: None)
    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_datacenter_watchlist_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "FAILED"})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Build Status: BUILD_FAILED" in output
    assert "completed: load_datacenter_taxonomy_to_ec_sidecar" in output
    assert "completed: load_datacenter_watchlist_to_ec_sidecar" in output
    assert "completed: load_ec_ticker_signal_daily_from_dc" in output


def test_success_path_runs_coverage_and_parity_audits(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    called = {"coverage": 0, "parity": 0}

    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", lambda _db: None)
    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_datacenter_watchlist_to_ec_sidecar", lambda **_: {"status": "OK"})
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
    monkeypatch.setattr(cli, "_collect_ec_row_counts", lambda _: {"ec_ecosystem": 1})

    summary = cli.run_ec_source_layer_build(
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

    assert summary["status"] == "BUILD_COMPLETED"
    assert called == {"coverage": 1, "parity": 1}


def test_existing_true_ec_schema_blocks_when_planner_says_so(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(
        cli,
        "plan_ec_source_layer_build",
        lambda **_: {"status": "BLOCKED_EXISTING_EC_SCHEMA", "selected_date_info": {"selected_signal_date": None}},
    )

    summary = cli.run_ec_source_layer_build(
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

    assert summary["status"] == "BUILD_REFUSED"


def test_success_path_prints_final_row_counts(tmp_path: Path, monkeypatch, capsys) -> None:
    args = _base_args(tmp_path)
    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())
    monkeypatch.setattr(cli, "_create_backup", lambda **_: tmp_path / "backups" / "backup.sqlite")
    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", lambda _db: None)
    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_datacenter_watchlist_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})
    monkeypatch.setattr(cli, "_collect_ec_row_counts", lambda _: {"ec_ecosystem": 1, "ec_watchlist": 1})

    exit_code = cli.main(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "- ec_ecosystem=1" in output
    assert "- ec_watchlist=1" in output


def test_integration_like_success_creates_real_backup_and_keeps_legacy_tables(tmp_path: Path, monkeypatch) -> None:
    args = _base_args(tmp_path)
    db_path = Path(args[1])
    backup_dir = Path(args[11])

    monkeypatch.setattr(cli, "plan_ec_source_layer_build", lambda **_: _ready_plan())

    def fake_migration(db: str) -> None:
        conn = sqlite3.connect(db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()

    monkeypatch.setattr(cli, "apply_ec_sidecar_migration", fake_migration)
    monkeypatch.setattr(cli, "load_datacenter_taxonomy_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_datacenter_watchlist_to_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_ticker_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_signal_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_synthetic_ohlc_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_group_index_daily_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "load_ec_pipeline_watermark_from_dc", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_facts_against_ec_sidecar", lambda **_: {"status": "OK"})
    monkeypatch.setattr(cli, "audit_dc_ec_fact_parity", lambda **_: {"status": "OK", "total_mismatch_count": 0})

    summary = cli.run_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=args[7],
        watchlist_path=args[9],
        backup_dir=str(backup_dir),
        confirm_db=str(db_path),
        confirm_ecosystem="DATACENTER",
        confirm_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    backups = list(backup_dir.glob("analysis__ec_source_layer__DATACENTER__DC_TAXONOMY_FULL_V1__*.sqlite"))
    assert summary["status"] == "BUILD_COMPLETED"
    assert backups

    conn = sqlite3.connect(db_path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "dc_ticker_swing_signal_daily" in names
        assert "eco_ecosystem" in names
    finally:
        conn.close()
