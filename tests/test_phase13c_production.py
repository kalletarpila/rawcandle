from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase13b_foundation import CandidatePaths, run_candidate_apply
from rawcandle.fundamentals.phase13c_production import exact_production_paths
from tests.test_phase13b_foundation import _analysis, _canonical, _taxonomy


def _paths(tmp_path: Path) -> CandidatePaths:
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    taxonomy = tmp_path / "taxonomy.db"
    _canonical(canonical)
    _analysis(analysis)
    _taxonomy(taxonomy)
    return CandidatePaths(canonical, analysis, taxonomy)


def _state(paths: CandidatePaths) -> tuple[int, int, int, int]:
    with sqlite3.connect(paths.canonical_db) as canonical, sqlite3.connect(paths.analysis_db) as analysis:
        return (
            canonical.execute("SELECT COUNT(*) FROM fundamentals_operational_universe_version").fetchone()[0],
            canonical.execute("SELECT COUNT(*) FROM fundamentals_operational_universe_member").fetchone()[0],
            analysis.execute("SELECT COUNT(*) FROM fundamentals_result_dependency").fetchone()[0],
            analysis.execute("SELECT COUNT(*) FROM relative_valuation_snapshot_dependency").fetchone()[0],
        )


def test_phase13c_uses_phase13b_tooling_with_explicit_production_authorization(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = run_candidate_apply(paths, apply=True, applied_at_utc="PHASE13C_TEST", allow_production=True)
    before_second = _state(paths)
    second = run_candidate_apply(paths, apply=True, applied_at_utc="PHASE13C_TEST", allow_production=True)
    after_second = _state(paths)
    assert first["schema"]["outcome"] == "APPLIED"
    assert first["universe"]["outcome"] == "APPLIED"
    assert first["dependencies"]["outcome"] == "APPLIED"
    assert second["schema"]["outcome"] == "NO_CHANGE"
    assert second["universe"]["outcome"] == "NO_CHANGE"
    assert second["dependencies"]["outcome"] == "NO_CHANGE"
    assert before_second == after_second


def test_phase13c_exact_production_paths_reject_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "db.sqlite"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "link.sqlite"
    link.symlink_to(target)
    monkeypatch.setattr("rawcandle.fundamentals.phase13c_production.PRODUCTION", {"canonical": link, "analysis": target})
    with pytest.raises(PermissionError):
        exact_production_paths()

