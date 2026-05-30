from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dev_tools.run_report_canonical_v2_parity_audit import main
from tests.test_report_canonical_v2_parity_audit import (
    _connect,
    _run_v2,
    _seed_source_rows,
)


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "analysis.sqlite"


def _classification_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM dc_report_classification_v2").fetchone()
    assert row is not None
    return int(row[0])


def _run_cli(capsys, *args: str) -> tuple[int, str, str]:
    exit_code = main(list(args))
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_text_output_ok_case(tmp_path: Path, capsys) -> None:
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)

    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--format",
        "text",
    )

    assert exit_code == 0
    assert stderr == ""
    assert "SUMMARY status=OK" in stdout
    assert "SUMMARY signal_date=2026-05-30" in stdout
    assert "SUMMARY taxonomy_version=DC_TAXONOMY_FULL_V1" in stdout
    assert "SUMMARY market=usa" in stdout
    assert "SUMMARY horizons=daily,rolling2,rolling5,rolling30" in stdout
    assert "SUMMARY mismatch_count=0" in stdout
    assert "SUMMARY missing_current_count=0" in stdout
    assert "SUMMARY missing_v2_count=0" in stdout
    assert "SUMMARY matched_count=5" in stdout
    assert "SUMMARY horizon.daily.matched_count=1" in stdout
    assert "SUMMARY horizon.rolling30.matched_count=2" in stdout
    assert "MISMATCH " not in stdout


def test_text_output_mismatch_case(tmp_path: Path, capsys) -> None:
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET classification_state = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN", "NVDA", "daily_trigger"),
    )
    conn.commit()

    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--horizons",
        "daily",
        "--format",
        "text",
    )

    assert exit_code == 1
    assert stderr == ""
    assert "SUMMARY status=MISMATCH" in stdout
    assert (
        "MISMATCH horizon=daily classification_type=daily_trigger "
        "ticker=NVDA field=classification_state current=BUY_TRIGGER v2=BROKEN "
        "reason=field_mismatch"
    ) in stdout


def test_json_output(tmp_path: Path, capsys) -> None:
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)

    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--format",
        "json",
    )

    assert exit_code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["status"] == "OK"
    assert payload["mismatch_count"] == 0
    assert payload["missing_current_count"] == 0
    assert payload["missing_v2_count"] == 0
    assert payload["matched_count"] == 5
    assert isinstance(payload["mismatches"], list)


def test_selected_horizons_exclude_other_mismatches(tmp_path: Path, capsys) -> None:
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    conn.execute(
        """
        UPDATE dc_report_classification_v2
        SET classification_state = ?
        WHERE ticker = ? AND classification_type = ?
        """,
        ("BROKEN", "NVDA", "rolling30_buy"),
    )
    conn.commit()

    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--horizons",
        "daily",
        "--format",
        "text",
    )

    assert exit_code == 0
    assert stderr == ""
    assert "SUMMARY horizons=daily" in stdout
    assert "SUMMARY status=OK" in stdout
    assert "rolling30_buy" not in stdout


def test_invalid_horizon_fails(tmp_path: Path, capsys) -> None:
    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--horizons",
        "daily,bad_horizon",
    )

    assert exit_code == 2
    assert stdout == ""
    assert "unsupported horizons: bad_horizon" in stderr


def test_cli_does_not_write_db(tmp_path: Path, capsys) -> None:
    conn = _connect(tmp_path)
    _seed_source_rows(conn)
    _run_v2(conn)
    before_count = _classification_count(conn)

    exit_code, stdout, stderr = _run_cli(
        capsys,
        "--db",
        str(_db_path(tmp_path)),
        "--signal-date",
        "2026-05-30",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--format",
        "text",
    )

    after_count = _classification_count(conn)
    assert exit_code == 0
    assert stderr == ""
    assert before_count == after_count
    assert "SUMMARY status=OK" in stdout
