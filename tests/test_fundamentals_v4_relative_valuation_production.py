from __future__ import annotations

import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_relative_valuation_production import build_parser
from rawcandle.fundamentals.relative_valuation import production
from rawcandle.fundamentals.relative_valuation.candidate_snapshot import (
    PRODUCTION_REPORT_PRESENTATION_FINGERPRINT,
    PRODUCTION_SNAPSHOT_FINGERPRINT,
    attach_relative_valuation_unavailable,
)
from rawcandle.fundamentals.relative_valuation.contract import PRODUCTION_REPORT_CONTRACT
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
    deactivate_snapshot,
    ensure_schema,
    set_active_snapshot,
)
def _role_database(path: Path, table: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(f'CREATE TABLE "{table}" (value INTEGER)')


def _args(paths: dict[str, Path], output: Path, **changes: object) -> Namespace:
    values: dict[str, object] = {
        **{f"{name}_db": path for name, path in paths.items()},
        "output": output,
        "backup_dir": output.parent / "backups",
        "as_of_date": "2026-09-08",
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "expected_active_package": production.LOCKED_PACKAGE,
        "expected_source_fingerprint": "s" * 64,
        "expected_result_fingerprint": "r" * 64,
        "expected_physical_fingerprint": "p" * 64,
        "expected_snapshot_id": "i" * 64,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(changes)
    return Namespace(**values)


def test_production_parser_defaults_to_dry_run() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "--confirm-production" in help_text
    assert "--full-universe" in help_text
    assert "--expected-physical-fingerprint" in help_text
    assert len(PRODUCTION_SNAPSHOT_FINGERPRINT) == 64
    assert len(PRODUCTION_REPORT_PRESENTATION_FINGERPRINT) == 64
    assert "CANDIDATE" not in PRODUCTION_REPORT_CONTRACT
    required = {
        action.dest for action in parser._actions if action.required
    }
    assert {
        "canonical_db", "provider_db", "analysis_db", "market_db", "taxonomy_db"
    } <= required


def test_production_gate_requires_exact_roles_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = {name: tmp_path / f"{name}.db" for name in production.PRODUCTION_PATHS}
    for name, path in paths.items():
        _role_database(path, production.DATABASE_TYPES[name])
    output_root = tmp_path / "artifacts"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(production, "PRODUCTION_PATHS", paths)
    monkeypatch.setattr(production, "ARTIFACT_ROOT", output_root)
    monkeypatch.setattr(production, "BACKUP_DIR", backup_root)
    args = _args(paths, output_root / "run")
    args.backup_dir = backup_root
    assert production.validate_production_request(args)["analysis"] == str(paths["analysis"])
    with pytest.raises(PermissionError, match="CONFIRMATION"):
        production.validate_production_request(
            _args(paths, output_root / "apply", backup_dir=backup_root, apply=True)
        )
    wrong = _args(paths, output_root / "wrong", backup_dir=backup_root)
    wrong.layout_fingerprint = "wrong"
    with pytest.raises(ValueError, match="LAYOUT"):
        production.validate_production_request(wrong)
    alias = tmp_path / "analysis-alias.db"
    alias.symlink_to(paths["analysis"])
    symlinked = _args(paths, output_root / "alias", backup_dir=backup_root)
    symlinked.analysis_db = alias
    with pytest.raises(PermissionError, match="ANALYSIS"):
        production.validate_production_request(symlinked)


def test_activation_and_deactivation_are_explicit_and_transactional() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection, applied_at_utc="2026-09-08T00:00:00Z")
    connection.execute(
        "INSERT INTO relative_valuation_snapshot VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "snapshot", "version", MODEL_FINGERPRINT, PERSISTENCE_VERSION,
            LAYOUT_FINGERPRINT, "CURRENTLY_REVISED_NOT_PIT", "2026-09-08",
            "2026-09-08T00:00:00Z", "source", "result", "physical", None,
            None, "COMPLETE", 0, 0, 0, 0, 0, "2026-09-08T00:00:00Z",
            "2026-09-08T00:00:00Z",
        ),
    )
    set_active_snapshot(
        connection, model_fingerprint=MODEL_FINGERPRINT,
        snapshot_id="snapshot", activated_at_utc="2026-09-08T00:01:00Z",
    )
    assert connection.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot").fetchone()[0] == "snapshot"
    assert deactivate_snapshot(connection, model_fingerprint=MODEL_FINGERPRINT) == 1
    assert connection.execute("SELECT COUNT(*) FROM relative_valuation_active_snapshot").fetchone()[0] == 0


def test_unavailable_report_is_explicit_and_uses_production_identities() -> None:
    base = {
        "identity": {"ticker": "TEST"},
        "report_date": "2026-09-07",
        "model_fingerprints": {"snapshot": "base"},
        "report_contract": "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V7",
        "report_presentation_fingerprint": "base",
    }
    snapshot = attach_relative_valuation_unavailable(
        base,
        reason_code="RELATIVE_VALUATION_AS_OF_MISMATCH",
        metadata={"as_of_date": "2026-09-08"},
    )
    assert snapshot["report_contract"] == PRODUCTION_REPORT_CONTRACT
    assert snapshot["report_presentation_fingerprint"] == PRODUCTION_REPORT_PRESENTATION_FINGERPRINT
    assert snapshot["model_fingerprints"]["snapshot"] == PRODUCTION_SNAPSHOT_FINGERPRINT
    markdown = "\n".join(__import__(
        "rawcandle.fundamentals.snapshot.renderer", fromlist=["_relative_valuation_sections"]
    )._relative_valuation_sections(snapshot))
    assert "RELATIVE_VALUATION_AS_OF_MISMATCH" in markdown
    assert "2026-09-08" in markdown and "uudelleenlaskentaa" in markdown
