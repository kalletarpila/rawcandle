from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.operating_income_v2 import full_rebuild


def test_fresh_bootstrap_has_v2_schema_but_no_results(tmp_path: Path) -> None:
    target = tmp_path / "fresh.db"
    with sqlite3.connect(target) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        full_rebuild._schema(conn, target, "2026-09-18T00:00:00Z")
    with sqlite3.connect(target) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        assert {"score_result", "valuation_revised_result", "relative_position_snapshot", "relative_valuation_snapshot"} <= tables
        assert conn.execute("SELECT COUNT(*) FROM score_result").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM relative_position_snapshot").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM relative_valuation_snapshot").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None


def test_rebuild_rejects_existing_target_and_analysis_source(tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    target.touch()
    sources = {key: target for key in full_rebuild.REQUIRED_SOURCES}
    with pytest.raises(FileExistsError, match="TARGET_MUST_BE_NEW"):
        full_rebuild.rebuild_v2_analysis(target, sources, as_of_date="2026-09-18", output=tmp_path / "report")
    target.unlink()
    sources = {key: tmp_path / f"{key}.db" for key in full_rebuild.REQUIRED_SOURCES}
    for source in sources.values():
        source.touch()
    sources["market"] = full_rebuild.PRODUCTION_ANALYSIS
    with pytest.raises(ValueError, match="ANALYSIS_CANNOT_BE_SOURCE"):
        full_rebuild.rebuild_v2_analysis(target, sources, as_of_date="2026-09-18", output=tmp_path / "report")


def test_failed_bootstrap_candidate_is_not_ready(tmp_path: Path) -> None:
    sources = {}
    for role in full_rebuild.REQUIRED_SOURCES:
        source = tmp_path / f"{role}.db"
        source.touch()
        sources[role] = source
    target = tmp_path / "target.db"
    output = tmp_path / "run"
    with pytest.raises(RuntimeError, match="INJECTED_V2_REBUILD_BOOTSTRAP_FAILURE"):
        full_rebuild.rebuild_v2_analysis(
            target, sources, as_of_date="2026-09-18", output=output, inject_failure_at="bootstrap"
        )
    assert '"status": "FAILED"' in (output / "result.json").read_text()
    assert '"stage": "bootstrap", "status": "FAILED"' in (output / "events.jsonl").read_text()
    assert target.exists()


def test_calculation_failure_after_bootstrap_is_disposable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = {}
    for role in full_rebuild.REQUIRED_SOURCES:
        source = tmp_path / f"{role}.db"
        source.touch()
        sources[role] = source
    target = tmp_path / "candidate.db"
    output = tmp_path / "run"

    def failed_calculation(*args: object, **kwargs: object) -> None:
        raise RuntimeError("INJECTED_VALUATION_FAILURE")

    monkeypatch.setattr(full_rebuild.phase10b, "calculate", failed_calculation)
    with pytest.raises(RuntimeError, match="INJECTED_VALUATION_FAILURE"):
        full_rebuild.rebuild_v2_analysis(target, sources, as_of_date="2026-09-18", output=output)
    assert '"failed_stage": "v2_calculation"' in (output / "result.json").read_text()
    assert '"status": "FAILED"' in (output / "result.json").read_text()
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM score_result").fetchone()[0] == 0
    target.unlink()
    assert not target.exists()
