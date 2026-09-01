from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import run_fundamentals_v4_relative_position_phase4c as cli
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.phase4c import validate_request
from rawcandle.fundamentals.relative_position.source import ReadOnlySourcePaths


def paths(tmp_path: Path) -> ReadOnlySourcePaths:
    values = []
    for name in ("analysis.db", "canonical.db", "market.db", "taxonomy.db"):
        path = tmp_path / name
        sqlite3.connect(path).close()
        values.append(path)
    return ReadOnlySourcePaths(*values)


def validate(source: ReadOnlySourcePaths, destination: Path, **changes) -> None:
    arguments = {
        "destination": destination,
        "model_fingerprint": MODEL_FINGERPRINT,
        "full_universe": True,
        "apply": True,
    }
    arguments.update(changes)
    validate_request(source, **arguments)


def test_valid_nonproduction_absolute_destination_is_accepted(tmp_path: Path) -> None:
    validate(paths(tmp_path), tmp_path / "rehearsal.db")


def test_relative_destination_wrong_fingerprint_and_missing_scope_are_rejected(
    tmp_path: Path,
) -> None:
    source = paths(tmp_path)
    with pytest.raises(ValueError, match="ABSOLUTE"):
        validate(source, Path("relative.db"))
    with pytest.raises(ValueError, match="FINGERPRINT"):
        validate(source, tmp_path / "out.db", model_fingerprint="wrong")
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        validate(source, tmp_path / "out.db", full_universe=False)


def test_source_exact_alias_and_symlink_destinations_are_rejected(tmp_path: Path) -> None:
    source = paths(tmp_path)
    with pytest.raises(PermissionError, match="SOURCE_DATABASE"):
        validate(source, source.analysis_db)
    normalized = tmp_path / "subdir" / ".." / "analysis.db"
    with pytest.raises(PermissionError, match="SOURCE_DATABASE"):
        validate(source, normalized)
    alias = tmp_path / "alias.db"
    alias.symlink_to(source.analysis_db)
    with pytest.raises(PermissionError, match="SYMLINK"):
        validate(source, alias)


def test_exact_and_symlink_production_destinations_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = paths(tmp_path)
    protected = tmp_path / "production.db"
    sqlite3.connect(protected).close()
    monkeypatch.setattr(
        "rawcandle.fundamentals.relative_position.phase4c.PRODUCTION_PATHS",
        {protected},
    )
    with pytest.raises(PermissionError, match="PRODUCTION"):
        validate(source, protected)
    alias = tmp_path / "production-alias.db"
    alias.symlink_to(protected)
    with pytest.raises(PermissionError, match="SYMLINK"):
        validate(source, alias)


def test_cli_defaults_to_dry_run_and_has_no_production_confirmation() -> None:
    parser = cli.build_parser()
    args = parser.parse_args([
        "--analysis-source", "/tmp/a.db",
        "--canonical-source", "/tmp/c.db",
        "--market-source", "/tmp/m.db",
        "--taxonomy-source", "/tmp/t.db",
        "--analysis-destination", "/tmp/d.db",
        "--as-of-date", "2026-09-01",
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe",
    ])
    assert args.apply is False
    assert args.create_online_backup is False
    assert not hasattr(args, "confirm_production")


def test_cli_failure_is_nonzero_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main([
        "--analysis-source", "/tmp/a.db",
        "--canonical-source", "/tmp/c.db",
        "--market-source", "/tmp/m.db",
        "--taxonomy-source", "/tmp/t.db",
        "--analysis-destination", "relative.db",
        "--as-of-date", "2026-09-01",
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe",
    ])
    assert code == 2
    assert capsys.readouterr().err == (
        '{"error": "PHASE4C_ALL_DATABASE_PATHS_MUST_BE_ABSOLUTE", "ok": false}\n'
    )
