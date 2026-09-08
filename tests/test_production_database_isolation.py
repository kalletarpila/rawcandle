from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from rawcandle.testing.database_isolation import (
    PROTECTED_DATABASE_ROLES,
    ProtectedDatabaseWriteError,
    inventory_differences,
    require_test_database_path,
)
from rawcandle.testing.production_database_audit import connection_audit


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DB = PROTECTED_DATABASE_ROLES["analysis_classification"]


def test_plain_production_database_write_open_is_rejected() -> None:
    with pytest.raises(ProtectedDatabaseWriteError, match="TEST_PRODUCTION_DATABASE_WRITE_REJECTED"):
        sqlite3.connect(ANALYSIS_DB)


def test_relative_alias_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    with pytest.raises(ProtectedDatabaseWriteError):
        sqlite3.connect("data/../data/analysis.db")


def test_symlink_alias_is_rejected(tmp_path: Path) -> None:
    alias = tmp_path / "alias.db"
    alias.symlink_to(ANALYSIS_DB)
    with pytest.raises(ProtectedDatabaseWriteError):
        sqlite3.connect(alias)


def test_writable_sqlite_uri_is_rejected() -> None:
    with pytest.raises(ProtectedDatabaseWriteError):
        sqlite3.connect(f"{ANALYSIS_DB.as_uri()}?mode=rw", uri=True)


def test_writable_attach_of_production_database_is_rejected(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "host.db") as connection:
        with pytest.raises(ProtectedDatabaseWriteError):
            connection.execute("ATTACH DATABASE ? AS production", (str(ANALYSIS_DB),))


def test_temporary_database_remains_writable(tmp_path: Path) -> None:
    target = require_test_database_path(tmp_path / "test.db", setting="analysis_db")
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES(1)")
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == 1


def test_approved_readonly_uri_remains_functional() -> None:
    with sqlite3.connect(f"{ANALYSIS_DB.as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()[0] > 0


def test_approved_readonly_attach_remains_functional(tmp_path: Path) -> None:
    readonly_uri = f"{ANALYSIS_DB.as_uri()}?mode=ro"
    with sqlite3.connect(tmp_path / "host.db") as connection:
        connection.execute("ATTACH DATABASE ? AS production", (readonly_uri,))
        assert connection.execute(
            "SELECT COUNT(*) FROM production.sqlite_schema"
        ).fetchone()[0] > 0


def test_python_subprocess_inherits_production_write_guard() -> None:
    command = [
        sys.executable,
        "-c",
        "import sqlite3; sqlite3.connect('data/analysis.db')",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert "TEST_PRODUCTION_DATABASE_WRITE_REJECTED" in result.stderr


def test_missing_test_path_never_falls_back_to_production() -> None:
    with pytest.raises(ValueError, match="MISSING_TEST_DATABASE_PATH"):
        require_test_database_path(None, setting="analysis_db")


def test_inventory_detects_simulated_fixture_mutation(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.db"
    fixture.write_bytes(b"before")
    before = {
        "fixture": {
            "main": {
                "path": str(fixture),
                "exists": True,
                "size": 6,
                "mtime_ns": fixture.stat().st_mtime_ns,
                "sha256": "placeholder-before",
            },
            "wal": {"path": f"{fixture}-wal", "exists": False, "size": None, "mtime_ns": None, "sha256": None},
            "shm": {"path": f"{fixture}-shm", "exists": False, "size": None, "mtime_ns": None, "sha256": None},
        }
    }
    fixture.write_bytes(b"after")
    after = {
        "fixture": {
            "main": {
                "path": str(fixture),
                "exists": True,
                "size": 5,
                "mtime_ns": fixture.stat().st_mtime_ns,
                "sha256": "placeholder-after",
            },
            "wal": before["fixture"]["wal"],
            "shm": before["fixture"]["shm"],
        }
    }
    assert inventory_differences(before, after)


def test_repository_connection_audit_has_no_unresolved_test_paths() -> None:
    findings = connection_audit(ROOT)
    assert findings
    assert not {
        row["classification"]
        for row in findings
    } & {"UNSAFE_REAL_PATH", "AMBIGUOUS"}
