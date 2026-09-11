from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.fundamentals import phase12e
from rawcandle.fundamentals.operating_income_v2.activation import (
    TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
    known_packages,
)


def test_ten_year_package_identity_is_exact_and_known():
    assert TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT == "f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40"
    assert TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT in known_packages()


def test_relative_valuation_as_of_skips_incomplete_latest_date(tmp_path: Path):
    market = tmp_path / "market.db"
    with sqlite3.connect(market) as connection:
        connection.execute("CREATE TABLE osakedata(osake TEXT,market TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL)")
        connection.executemany(
            "INSERT INTO osakedata VALUES(?,?,?,?,?,?,?)",
            [(f"T{index}", "usa", "2026-09-10", 1, 1, 1, 1) for index in range(100)]
            + [("ONE", "usa", "2026-09-11", 1, 1, 1, 1)],
        )
    result = phase12e.derive_relative_valuation_as_of(market)
    assert result["as_of_date"] == "2026-09-10"
    assert result["latest_observed_date"] == "2026-09-11"
    assert result["selected_company_count"] == 100


def test_sidecar_monitor_records_observed_peak(tmp_path: Path, monkeypatch):
    paths = {"canonical": tmp_path / "canonical.db", "analysis": tmp_path / "analysis.db"}
    monkeypatch.setattr(phase12e, "PRODUCTION", paths)
    with phase12e.SidecarMonitor() as monitor:
        Path(str(paths["canonical"]) + "-journal").write_bytes(b"x" * 4096)
        monitor._stop.wait(0.03)
    assert monitor.maximum["canonical-journal"] == 4096


def test_pair_restore_replaces_both_databases_and_removes_sidecars(tmp_path: Path, monkeypatch):
    production = {"canonical": tmp_path / "canonical.db", "analysis": tmp_path / "analysis.db"}
    backups = {}
    for index, name in enumerate(("canonical", "analysis"), start=1):
        backup = tmp_path / f"{name}.backup.db"
        with sqlite3.connect(backup) as connection:
            connection.execute("CREATE TABLE sample(value INTEGER)")
            connection.execute("INSERT INTO sample VALUES(?)", (index,))
        with sqlite3.connect(production[name]) as connection:
            connection.execute("CREATE TABLE sample(value INTEGER)")
            connection.execute("INSERT INTO sample VALUES(?)", (index + 10,))
        Path(str(production[name]) + "-journal").write_bytes(b"stale")
        backups[name] = {"destination": str(backup)}
    monkeypatch.setattr(phase12e, "PRODUCTION", production)

    restored = phase12e._restore_pair(backups, tmp_path / "restore")
    assert set(restored) == {"canonical", "analysis"}
    for index, name in enumerate(("canonical", "analysis"), start=1):
        with sqlite3.connect(production[name]) as connection:
            assert connection.execute("SELECT value FROM sample").fetchone()[0] == index
        assert not Path(str(production[name]) + "-journal").exists()


def test_phase12e_expected_reconciliation_counts_are_locked():
    assert phase12e.EXPECTED["endpoints"] == 87_319
    assert phase12e.EXPECTED["diagnostic_evaluations"] == 698_552
    assert phase12e.EXPECTED["new_history"] == 36_734
    assert phase12e.EXPECTED["readiness_changes"] == 6_383
