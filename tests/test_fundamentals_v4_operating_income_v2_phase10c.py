from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.operating_income_v2 import phase10b, phase10c


def _database(path: Path, table: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE {table}(id INTEGER)")


def _args(paths: dict[str, Path], **overrides: object) -> argparse.Namespace:
    values = {
        **{f"{name}_db": path for name, path in paths.items()},
        "full_universe": True, "apply": False, "confirm_production": False,
        "package_fingerprint": phase10c.LOCKED_PACKAGE,
        "expected_active_package": phase10c.ROLLBACK_PACKAGE,
        "score_fingerprint": phase10c.EXPECTED_MODELS["score"],
        "lifecycle_fingerprint": phase10c.EXPECTED_MODELS["lifecycle"],
        "valuation_fingerprint": phase10c.EXPECTED_MODELS["valuation"],
        "delta_fingerprint": phase10c.EXPECTED_MODELS["delta"],
        "relative_fingerprint": phase10c.EXPECTED_MODELS["relative_position"],
        "diagnostic_fingerprint": phase10c.EXPECTED_MODELS["diagnostic_flags"],
        "snapshot_fingerprint": phase10c.EXPECTED_MODELS["snapshot"],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def production_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {name: tmp_path / f"{name}.db" for name in phase10c.PRODUCTION}
    for name, path in paths.items():
        _database(path, phase10c.DATABASE_TYPES[name])
    monkeypatch.setattr(phase10c, "PRODUCTION", paths)
    return paths


def test_phase10c_request_requires_exact_paths_and_full_identities(production_paths) -> None:
    phase10c.validate_request(_args(production_paths))
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        phase10c.validate_request(_args(production_paths, full_universe=False))
    with pytest.raises(ValueError, match="PACKAGE_FINGERPRINT"):
        phase10c.validate_request(_args(production_paths, package_fingerprint="wrong"))
    with pytest.raises(ValueError, match="MODEL_PACKAGE"):
        phase10c.validate_request(_args(production_paths, diagnostic_fingerprint="wrong"))
    with pytest.raises(ValueError, match="EXPECTED_ACTIVE"):
        phase10c.validate_request(_args(production_paths, expected_active_package="wrong"))


def test_phase10c_request_rejects_alias_collision_and_missing_confirmation(
    production_paths, tmp_path
) -> None:
    alias = tmp_path / "analysis-alias.db"
    alias.symlink_to(production_paths["analysis"])
    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_ANALYSIS"):
        phase10c.validate_request(_args(production_paths, analysis_db=alias))
    with pytest.raises(PermissionError, match="CONFIRMATION"):
        phase10c.validate_request(
            _args(production_paths, apply=True, confirm_production=False)
        )


def test_phase10c_request_restricts_artifact_and_backup_paths(
    production_paths, tmp_path
) -> None:
    with pytest.raises(PermissionError, match="OUTPUT_PATH"):
        phase10c.validate_request(
            _args(production_paths, output=tmp_path / "outside")
        )
    with pytest.raises(PermissionError, match="BACKUP_PATH"):
        phase10c.validate_request(
            _args(production_paths, backup_dir=tmp_path / "backups")
        )


def test_phase10c_locked_source_identities_match_candidate() -> None:
    phase10c._identity_gate()
    assert phase10c.LOCKED_PACKAGE == phase10b.PACKAGE_FINGERPRINT
    assert phase10c.EXPECTED_MODELS == {
        name: identity[1] for name, identity in phase10b.MODEL_MAP.items()
    }


def test_phase10c_ui_smoke_uses_public_recent_reports_api() -> None:
    assert hasattr(phase10c.FundamentalsSnapshotUIService, "recent_reports")
    assert not hasattr(phase10c.FundamentalsSnapshotUIService, "list_recent_reports")
