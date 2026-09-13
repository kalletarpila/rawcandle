from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from rawcandle.fundamentals.diagnostic_flags import persistence as diagnostic_v1
from rawcandle.fundamentals.operating_income_v2 import phase10b
from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13f3_1_package_recovery import (
    StageTelemetry,
    _economic_fingerprint,
    instrumented_package_refresh,
)


def test_stage_telemetry_records_heartbeat(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sample(value INTEGER)")
    conn.commit()
    conn.close()
    telemetry = StageTelemetry(tmp_path, analysis_db=db)

    with telemetry.heartbeat("calculate", interval_seconds=0.01):
        time.sleep(0.035)

    events = json.loads((tmp_path / "package_refresh_telemetry.json").read_text())["events"]
    running = [event for event in events if event["stage"] == "calculate" and event["status"] == "RUNNING"]
    assert len(running) >= 2
    assert all("analysis_db" in event for event in running)


def test_instrumented_package_refresh_refuses_production_analysis(tmp_path: Path) -> None:
    paths = {
        "provider": PRODUCTION["provider"],
        "canonical": PRODUCTION["canonical"],
        "analysis": PRODUCTION["analysis"],
        "market": PRODUCTION["market"],
        "taxonomy": PRODUCTION["taxonomy"],
    }

    with pytest.raises(PermissionError):
        instrumented_package_refresh(paths, tmp_path)


def test_economic_fingerprint_excludes_runtime_metadata() -> None:
    base = {
        "identity": {"fingerprint": "identity"},
        "universe": {"identity": {"economic_result_fingerprint": "universe"}},
        "package": {"first_apply": {"economic_result_fingerprint": "package"}},
        "relative_position": {"result_fingerprint": "rp"},
        "relative_valuation": {"snapshot": {"result_fingerprint": "rv"}},
        "snapshots": {
            "VMRK": {
                "status": "GENERATED",
                "fingerprint": "report",
                "output_path": "/tmp/run-1/VMRK.md",
                "generated_at_utc": "2026-09-13T00:00:00Z",
            }
        },
    }
    changed = json.loads(json.dumps(base))
    changed["snapshots"]["VMRK"]["output_path"] = "/tmp/run-2/VMRK.md"
    changed["snapshots"]["VMRK"]["generated_at_utc"] = "2026-09-13T01:00:00Z"

    assert _economic_fingerprint(base) == _economic_fingerprint(changed)


def test_phase10b_validation_derives_endpoint_count_from_current_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyRepository:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self.conn = conn

        def assert_v2_bundle(self, *args: object, **kwargs: object) -> None:
            return None

    rows = {
        "score": 2,
        "score_component": 14,
        "lifecycle": 2,
        "valuation": 2,
        "delta": 2,
        "delta_component": 14,
        "diagnostic_endpoint": 2,
        "diagnostic_evaluation": 16,
        "relative_result": 2,
        "relative_coverage": 2,
    }
    monkeypatch.setattr(phase10b, "ParallelModelRepository", DummyRepository)
    monkeypatch.setattr(phase10b.persistence, "row_counts", lambda conn, diagnostic_model=None: rows)
    monkeypatch.setattr(phase10b.persistence, "physical_fingerprint", lambda conn, diagnostic_model=None: "physical")
    db = tmp_path / "analysis.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute(f"CREATE TABLE {diagnostic_v1.PACKAGE_TABLE}(package_id INTEGER, model_fingerprint TEXT)")
        conn.execute(f"CREATE TABLE {diagnostic_v1.ENDPOINT_TABLE}(endpoint_id INTEGER, package_id INTEGER, company_id INTEGER, fiscal_sequence INTEGER)")
        conn.execute(f"CREATE TABLE {diagnostic_v1.EVALUATION_TABLE}(endpoint_id INTEGER, flag_id INTEGER)")
        conn.execute(
            f"INSERT INTO {diagnostic_v1.PACKAGE_TABLE} VALUES(?,?)",
            (1, phase10b.diagnostic_flags_eight.MODEL_FINGERPRINT),
        )
        for endpoint_id, company_id in ((1, 101), (2, 102)):
            conn.execute(f"INSERT INTO {diagnostic_v1.ENDPOINT_TABLE} VALUES(?,?,?,?)", (endpoint_id, 1, company_id, endpoint_id))
            conn.executemany(
                f"INSERT INTO {diagnostic_v1.EVALUATION_TABLE} VALUES(?,?)",
                [(endpoint_id, flag_id) for flag_id in range(1, 9)],
            )
        result = phase10b.validate_candidate_package(conn)
    finally:
        conn.close()

    assert result["ok"] is True
    assert result["counts"]["diagnostic_endpoint"] == 2
