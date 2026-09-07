from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.operating_income_v2 import phase9e
from rawcandle.fundamentals.operating_income_v2.persistence import PACKAGE_FINGERPRINT


def _database(path: Path, table: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE {table}(id INTEGER)")


def _args(paths: dict[str, Path], **overrides: object) -> argparse.Namespace:
    values = {
        **{f"{name}_db": path for name, path in paths.items()},
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
        "package_fingerprint": PACKAGE_FINGERPRINT,
        "score_fingerprint": phase9e.EXPECTED_MODELS["score"],
        "lifecycle_fingerprint": phase9e.EXPECTED_MODELS["lifecycle"],
        "valuation_fingerprint": phase9e.EXPECTED_MODELS["valuation"],
        "delta_fingerprint": phase9e.EXPECTED_MODELS["delta"],
        "relative_fingerprint": phase9e.EXPECTED_MODELS["relative_position"],
        "diagnostic_fingerprint": phase9e.EXPECTED_MODELS["diagnostic_flags"],
        "snapshot_fingerprint": phase9e.EXPECTED_MODELS["snapshot"],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def production_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {name: tmp_path / f"{name}.db" for name in phase9e.PRODUCTION}
    for name, path in paths.items():
        _database(path, phase9e.DATABASE_TYPES[name])
    monkeypatch.setattr(phase9e, "PRODUCTION", paths)
    return paths


def test_phase9e_request_requires_exact_paths_full_universe_and_fingerprints(production_paths: dict[str, Path]) -> None:
    phase9e.validate_request(_args(production_paths))
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        phase9e.validate_request(_args(production_paths, full_universe=False))
    with pytest.raises(ValueError, match="PACKAGE_FINGERPRINT"):
        phase9e.validate_request(_args(production_paths, package_fingerprint="wrong"))
    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_ANALYSIS"):
        phase9e.validate_request(_args(production_paths, analysis_db=production_paths["canonical"]))
    with pytest.raises(PermissionError, match="CONFIRMATION"):
        phase9e.validate_request(_args(production_paths, apply=True, confirm_production=False))


def test_phase9e_request_rejects_symlink_alias(production_paths: dict[str, Path], tmp_path: Path) -> None:
    alias = tmp_path / "analysis-alias.db"
    alias.symlink_to(production_paths["analysis"])
    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_ANALYSIS"):
        phase9e.validate_request(_args(production_paths, analysis_db=alias))


def test_phase9e_backup_includes_diagnostic_and_activation_counts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "analysis.db"
    tables = (
        "score_result", "lifecycle_revised_result", "valuation_revised_result",
        "diagnostic_flag_package", "diagnostic_flag_endpoint",
        "diagnostic_flag_evaluation", "operating_income_v2_package_manifest",
        "fundamentals_active_model_family",
    )
    with sqlite3.connect(source) as conn:
        for table in tables:
            conn.execute(f"CREATE TABLE {table}(id INTEGER)")
            conn.execute(f"INSERT INTO {table} VALUES(1)")
    result = phase9e._backup(source, tmp_path / "backups", "test")
    assert result["key_row_counts"] == {table: 1 for table in tables}
