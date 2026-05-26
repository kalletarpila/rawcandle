from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_file(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_reports_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "report.md").write_text("# report\n", encoding="utf-8")


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sample(value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES ('source-only')")


def _table_exists(path: Path, table_name: str) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
    return row is not None


def _summary_lines(*lines: str) -> tuple[int, dict[str, str], str, str]:
    stdout = "\n".join(lines) + "\n"
    parsed: dict[str, str] = {}
    for line in lines:
        if line.startswith("SUMMARY ") and "=" in line:
            key, value = line[len("SUMMARY ") :].split("=", 1)
            parsed[key] = value
    return 0, parsed, stdout, ""


def test_missing_analysis_db_fails_clearly_and_does_not_create_copy(tmp_path, capsys):
    analysis_db = tmp_path / "missing.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "analysis_db not found:" in captured.err
    assert not work_dir.exists()


def test_missing_reports_dir_fails_clearly(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "missing-reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "reports_dir not found:" in captured.err
    assert not work_dir.exists()


def test_smoke_copies_analysis_db_and_does_not_mutate_source(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    original_bytes = analysis_db.read_bytes()

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        log_path.write_text(f"{step_name}\n", encoding="utf-8")
        if step_name == "enrichment_write":
            return _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            )
        if step_name == "enrichment_audit":
            return _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=PARTIAL",
            )
        if step_name == "enrichment_export":
            Path(argv[argv.index("--output-json") + 1]).write_text("{}", encoding="utf-8")
            return _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=0",
            )
        if step_name == "enrichment_build":
            Path(argv[argv.index("--dashboard-db") + 1]).write_text("", encoding="utf-8")
            return _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_RUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=0",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=0",
            )
        if step_name == "reports_build":
            Path(argv[argv.index("--dashboard-db") + 1]).write_text("", encoding="utf-8")
            return _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=REPORTS_RUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=2",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=2",
                "SUMMARY ecosystem_dashboard_build.trace_rows=3",
            )
        if step_name == "parity_audit":
            return _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=1",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=2",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=3",
            )
        if step_name == "parity_explain":
            return _summary_lines("SUMMARY ecosystem_dashboard_parity_explain.status=OK")
        raise AssertionError(step_name)

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    output = capsys.readouterr().out
    copied_db = work_dir / "analysis_enrichment_smoke_2026-05-22.db"
    assert exit_code == 0
    assert copied_db.exists()
    assert copied_db.read_bytes() == original_bytes
    assert analysis_db.read_bytes() == original_bytes
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.status=OK" in output
    assert (
        "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.apply_migrations_to_copy=0"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.copy_migration_status=SKIPPED"
        in output
    )


def test_smoke_invokes_steps_in_deterministic_order(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    calls: list[str] = []

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        calls.append(step_name)
        log_path.write_text(step_name, encoding="utf-8")
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=1",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ERUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RRUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0",
            ),
            "parity_explain": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_explain.status=OK"
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    assert exit_code == 0
    assert calls == [
        "enrichment_write",
        "enrichment_audit",
        "enrichment_export",
        "enrichment_build",
        "reports_build",
        "parity_audit",
        "parity_explain",
    ]


def test_apply_migrations_to_copy_runs_before_enrichment_write_and_updates_only_copy(
    tmp_path, monkeypatch, capsys
):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    calls: list[str] = []

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        calls.append(step_name)
        log_path.write_text(step_name, encoding="utf-8")
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=PARTIAL",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=0",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ERUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=0",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=0",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=0",
                "SUMMARY ecosystem_dashboard_build.trace_rows=0",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RRUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=0",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=0",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=0",
                "SUMMARY ecosystem_dashboard_build.trace_rows=0",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0",
            ),
            "parity_explain": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_explain.status=OK"
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
            "--apply-migrations-to-copy",
        ]
    )

    output = capsys.readouterr().out
    copied_db = work_dir / "analysis_enrichment_smoke_2026-05-22.db"
    assert exit_code == 0
    assert calls[0] == "enrichment_write"
    assert _table_exists(analysis_db, "dc_dashboard_ticker_enrichment_daily") is False
    assert _table_exists(copied_db, "dc_dashboard_ticker_enrichment_daily") is True
    assert (
        "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.apply_migrations_to_copy=1"
        in output
    )
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.copy_migration_status=OK" in output
    log_path = work_dir / "copy_migrations.log"
    assert log_path.exists()
    assert str(copied_db) in log_path.read_text(encoding="utf-8")


def test_migration_failure_stops_before_enrichment_write(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    calls: list[str] = []

    def fake_apply_migrations_to_copy(copied_db: Path, log_path: Path) -> None:
        raise RuntimeError("migration exploded")

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        calls.append(step_name)
        return _summary_lines(
            "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._apply_migrations_to_copy",
        fake_apply_migrations_to_copy,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
            "--apply-migrations-to-copy",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert calls == []
    assert "migration exploded" in captured.err
    assert "status=OK" not in captured.out


def test_skip_html_omits_render_args_and_summary_paths_are_empty(
    tmp_path, monkeypatch, capsys
):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    build_argvs: dict[str, list[str]] = {}

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        log_path.write_text(step_name, encoding="utf-8")
        if step_name in {"enrichment_build", "reports_build"}:
            build_argvs[step_name] = list(argv)
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=PARTIAL",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=0",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ERUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=0",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=0",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=0",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RRUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=0",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=0",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=0",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0",
            ),
            "parity_explain": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_explain.status=OK"
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
            "--skip-html",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--render-html" not in build_argvs["enrichment_build"]
    assert "--render-html" not in build_argvs["reports_build"]
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_html=" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_html=" in output
    assert str(work_dir / "datacenter_dashboard_enrichment_2026-05-22.html") not in output


def test_skip_parity_explain_omits_that_step(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    calls: list[str] = []

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        calls.append(step_name)
        log_path.write_text(step_name, encoding="utf-8")
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=1",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ERUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RRUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0",
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
            "--skip-parity-explain",
        ]
    )

    assert exit_code == 0
    assert "parity_explain" not in calls


def test_parses_run_ids_counts_and_parity_summaries(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        log_path.write_text(step_name, encoding="utf-8")
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=4",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ENRICH_RUN_ID",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=5",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=6",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=7",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=8",
                "SUMMARY ecosystem_dashboard_build.trace_rows=9",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=REPORTS_RUN_ID",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=10",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=11",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=12",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=13",
                "SUMMARY ecosystem_dashboard_build.trace_rows=14",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=15",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=16",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=17",
            ),
            "parity_explain": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_explain.status=OK"
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_run_id=ENRICH_RUN_ID" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_run_id=REPORTS_RUN_ID" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_source_reports=10" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_market_map=11" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_watchlist=12" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_tickers=13" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.reports_decision_trace=14" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_source_reports=5" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_action_summary=4" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_market_map=6" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_watchlist=7" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_tickers=8" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.enrichment_decision_trace=9" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.parity_sections_with_count_diff=15" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.parity_key_differences=16" in output
    assert "SUMMARY datacenter_dashboard_enrichment_e2e_smoke.parity_field_differences=17" in output


def test_failure_in_middle_step_stops_later_steps_and_has_no_ok_status(
    tmp_path, monkeypatch, capsys
):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)
    calls: list[str] = []

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        calls.append(step_name)
        log_path.write_text(step_name, encoding="utf-8")
        if step_name == "enrichment_export":
            return 2, {}, "", "export failed\n"
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=PARTIAL",
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert calls == ["enrichment_write", "enrichment_audit", "enrichment_export"]
    assert "status=OK" not in captured.out
    assert "enrichment_export failed:" in captured.err


def test_log_files_are_written(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "prices.db"
    reports_dir = tmp_path / "reports"
    work_dir = tmp_path / "work"
    _create_analysis_db(analysis_db)
    _create_file(price_db, "prices")
    _create_reports_dir(reports_dir)

    def fake_run_logged_step(*, step_name, step_main, argv, log_path):
        log_path.write_text(f"log:{step_name}\n", encoding="utf-8")
        outputs = {
            "enrichment_write": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_write.status=OK"
            ),
            "enrichment_audit": _summary_lines(
                "SUMMARY datacenter_dashboard_enrichment_audit.status=OK",
                "SUMMARY datacenter_dashboard_enrichment_audit.readiness=READY",
            ),
            "enrichment_export": _summary_lines(
                "SUMMARY datacenter_dashboard_analysis_db_export.status=OK",
                "SUMMARY datacenter_dashboard_analysis_db_export.action_summary=1",
            ),
            "enrichment_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=ERUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "reports_build": _summary_lines(
                "SUMMARY ecosystem_dashboard_build.status=OK",
                "SUMMARY ecosystem_dashboard_build.run_id=RRUN",
                "SUMMARY ecosystem_dashboard_build.source_reports_count=1",
                "SUMMARY ecosystem_dashboard_build.market_map_rows=1",
                "SUMMARY ecosystem_dashboard_build.watchlist_rows=1",
                "SUMMARY ecosystem_dashboard_build.ticker_rows=1",
                "SUMMARY ecosystem_dashboard_build.trace_rows=1",
            ),
            "parity_audit": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_audit.status=OK",
                "SUMMARY ecosystem_dashboard_parity_audit.sections_with_count_diff=0",
                "SUMMARY ecosystem_dashboard_parity_audit.key_differences=0",
                "SUMMARY ecosystem_dashboard_parity_audit.field_differences=0",
            ),
            "parity_explain": _summary_lines(
                "SUMMARY ecosystem_dashboard_parity_explain.status=OK"
            ),
        }
        return outputs[step_name]

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_e2e_smoke._run_logged_step",
        fake_run_logged_step,
    )

    exit_code = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--reports-dir",
            str(reports_dir),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--work-dir",
            str(work_dir),
        ]
    )

    assert exit_code == 0
    for name in [
        "enrichment_write.log",
        "enrichment_audit.log",
        "enrichment_export.log",
        "enrichment_build.log",
        "reports_build.log",
        "parity_audit.log",
        "parity_explain.log",
    ]:
        assert (work_dir / name).exists()
