from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.cli import write_latest_v3_markdown_reports as cli


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _build_fixture_db(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE eco_ecosystem (
                ecosystem_id INTEGER PRIMARY KEY,
                ecosystem_code TEXT NOT NULL,
                ecosystem_name TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE eco_taxonomy_version (
                taxonomy_version_id INTEGER PRIMARY KEY,
                ecosystem_id INTEGER NOT NULL,
                version_code TEXT NOT NULL,
                version_label TEXT NOT NULL,
                is_active INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE eco_report_run (
                run_id TEXT PRIMARY KEY,
                ecosystem_id INTEGER NOT NULL,
                taxonomy_version_id INTEGER NOT NULL,
                signal_date TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                warning_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                created_at_utc TEXT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO eco_ecosystem (ecosystem_id, ecosystem_code, ecosystem_name, status) VALUES (1, 'DATACENTER', 'Datacenter', 'ACTIVE')"
        )
        conn.execute(
            "INSERT INTO eco_ecosystem (ecosystem_id, ecosystem_code, ecosystem_name, status) VALUES (2, 'ENERGY', 'Energy', 'ACTIVE')"
        )
        conn.execute(
            """
            INSERT INTO eco_taxonomy_version (
                taxonomy_version_id, ecosystem_id, version_code, version_label, is_active, status
            ) VALUES
                (1, 1, 'DC_TAXONOMY_FULL_V1', 'Datacenter Full', 1, 'ACTIVE'),
                (2, 1, 'DC_TAXONOMY_ALT_V1', 'Datacenter Alt', 1, 'ACTIVE'),
                (3, 2, 'ENERGY_TAXONOMY_V1', 'Energy V1', 1, 'ACTIVE')
            """
        )
        conn.executemany(
            """
            INSERT INTO eco_report_run (
                run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count, created_at_utc
            ) VALUES (?, ?, ?, ?, 'BUILD', ?, 0, 0, ?)
            """,
            [
                ("RUN_DC_2026_06_03_OK", 1, 1, "2026-06-03", "OK", "2026-06-03 08:00:00"),
                ("RUN_DC_2026_06_04_WARN_A", 1, 1, "2026-06-04", "OK_WITH_WARNINGS", "2026-06-04 08:00:00"),
                ("RUN_DC_2026_06_04_WARN_B", 1, 1, "2026-06-04", "OK_WITH_WARNINGS", "2026-06-04 09:00:00"),
                ("RUN_DC_2026_06_05_FAIL", 1, 1, "2026-06-05", "FAILED", "2026-06-05 08:00:00"),
                ("RUN_DC_ALT_2026_06_04_OK", 1, 2, "2026-06-04", "OK", "2026-06-04 10:00:00"),
                ("RUN_ENERGY_2026_06_04_OK", 2, 3, "2026-06-04", "OK", "2026-06-04 11:00:00"),
                ("RUN_DC_2026_06_04_TIE_A", 1, 1, "2026-06-04", "OK", "2026-06-04 12:00:00"),
                ("RUN_DC_2026_06_04_TIE_B", 1, 1, "2026-06-04", "OK", "2026-06-04 12:00:00")
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_cli_resolves_latest_run_and_calls_writer(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "analysis.db"
    _build_fixture_db(db_path)
    calls: list[dict[str, object]] = []

    def _fake_write_reports(*, db_path: str, run_id: str, out_dir: str, overwrite: bool, only: str | None):
        calls.append(
            {
                "db_path": db_path,
                "run_id": run_id,
                "out_dir": out_dir,
                "overwrite": overwrite,
                "only": only,
            }
        )
        out = Path(out_dir).resolve()
        return (
            out,
            [
                ("rolling30", out / "datacenter_v3_rolling30_2026-06-04.md", 100, 10),
                ("daily", out / "datacenter_v3_daily_2026-06-04.md", 200, 20),
            ],
        )

    monkeypatch.setattr(cli, "write_reports", _fake_write_reports)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "text",
            "--only",
            "rolling30,daily",
            "--overwrite",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert calls == [
        {
            "db_path": str(db_path),
            "run_id": "RUN_DC_2026_06_04_TIE_B",
            "out_dir": str(tmp_path / "out"),
            "overwrite": True,
            "only": "rolling30,daily",
        }
    ]
    assert "V3 Latest Markdown Reports" in captured.out
    assert "run_id: RUN_DC_2026_06_04_TIE_B" in captured.out
    assert "run_status: OK" in captured.out
    assert "final_status: REPORTS_GENERATED" in captured.out
    assert str((tmp_path / "out" / "datacenter_v3_daily_2026-06-04.md").resolve()) in captured.out


def test_cli_filters_by_signal_date_and_allows_ok_with_warnings(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "analysis.db"
    _build_fixture_db(db_path)
    selected: list[str] = []

    def _fake_write_reports(*, db_path: str, run_id: str, out_dir: str, overwrite: bool, only: str | None):
        selected.append(run_id)
        out = Path(out_dir).resolve()
        return (out, [("daily", out / "datacenter_v3_daily_2026-06-04.md", 1, 1)])

    monkeypatch.setattr(cli, "write_reports", _fake_write_reports)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_ALT_V1",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "text",
            "--signal-date",
            "2026-06-04",
            "--status",
            "OK_WITH_WARNINGS,OK",
        ]
    )

    assert result == 0
    assert selected == ["RUN_DC_ALT_2026_06_04_OK"]


def test_cli_returns_no_matching_run_when_default_status_excludes_failed(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "analysis.db"
    _build_fixture_db(db_path)
    called = False

    def _fake_write_reports(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(cli, "write_reports", _fake_write_reports)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "text",
            "--signal-date",
            "2026-06-05",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert called is False
    assert "final_status: NO_MATCHING_ECO_RUN" in captured.out


def test_cli_filters_by_ecosystem_and_taxonomy_version(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "analysis.db"
    _build_fixture_db(db_path)
    selected: list[str] = []

    def _fake_write_reports(*, db_path: str, run_id: str, out_dir: str, overwrite: bool, only: str | None):
        selected.append(run_id)
        out = Path(out_dir).resolve()
        return (out, [("daily", out / "energy_v3_daily_2026-06-04.md", 1, 1)])

    monkeypatch.setattr(cli, "write_reports", _fake_write_reports)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "ENERGY",
            "--taxonomy-version",
            "ENERGY_TAXONOMY_V1",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "text",
        ]
    )

    assert result == 0
    assert selected == ["RUN_ENERGY_2026_06_04_OK"]


def test_cli_returns_failed_when_writer_errors(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "analysis.db"
    _build_fixture_db(db_path)

    def _fake_write_reports(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "write_reports", _fake_write_reports)

    result = cli.main(
        [
            "--db",
            str(db_path),
            "--ecosystem",
            "DATACENTER",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--out-dir",
            str(tmp_path / "out"),
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "error: boom" in captured.err
    assert "final_status: REPORT_GENERATION_FAILED" in captured.out
