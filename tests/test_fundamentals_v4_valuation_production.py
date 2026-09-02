from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import run_fundamentals_v4_valuation_production as production_cli
from rawcandle.cli.run_fundamentals_v4_score import build_parser as score_parser
from rawcandle.cli.run_fundamentals_v4_valuation_production import build_parser
from rawcandle.fundamentals.score import engine as score_engine
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL, bootstrap_database, connect
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT as RELATIVE_POSITION_MODEL_FINGERPRINT,
)
from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import LAYOUT_FINGERPRINT, PERSISTENCE_VERSION
from rawcandle.fundamentals.valuation import production


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "canonical_db": production.PRODUCTION_PATHS["canonical"],
        "provider_db": production.PRODUCTION_PATHS["provider"],
        "analysis_db": production.PRODUCTION_PATHS["analysis"],
        "market_db": production.PRODUCTION_PATHS["market"],
        "model_fingerprint": MODEL_FINGERPRINT,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(overrides)
    return values


def test_production_request_defaults_to_dry_run_and_requires_all_gates() -> None:
    args = build_parser().parse_args([
        "--stage", "valuation",
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe", "--output-dir", "/tmp/valuation-production-test",
    ])
    assert args.apply is False
    assert args.confirm_production is False
    resolved = production.validate_production_request(**request())
    assert resolved["market"] == str(production.PRODUCTION_PATHS["market"])
    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION"):
        production.validate_production_request(**request(apply=True))
    with pytest.raises(ValueError, match="REQUIRES_APPLY"):
        production.validate_production_request(**request(confirm_production=True))
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        production.validate_production_request(**request(full_universe=False))
    with pytest.raises(ValueError, match="FINGERPRINT"):
        production.validate_production_request(**request(model_fingerprint="wrong"))


def test_score_pipeline_cli_is_also_dry_run_and_explicitly_gated() -> None:
    args = score_parser().parse_args([
        "--repo-root", "/home/kalle/projects/rawcandle",
        "--valuation-model-fingerprint", MODEL_FINGERPRINT,
        "--delta-model-fingerprint", DELTA_MODEL_FINGERPRINT,
        "--delta-persistence-version", PERSISTENCE_VERSION,
        "--delta-layout-fingerprint", LAYOUT_FINGERPRINT,
        "--relative-position-model-fingerprint", RELATIVE_POSITION_MODEL_FINGERPRINT,
        "--full-universe",
    ])
    assert args.apply is False
    assert args.confirm_production is False
    assert args.valuation_model_fingerprint == MODEL_FINGERPRINT
    assert args.relative_position_model_fingerprint == RELATIVE_POSITION_MODEL_FINGERPRINT


def test_production_cli_persists_resolved_paths_before_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "evidence"

    def apply(*_args: object, **_kwargs: object) -> dict[str, object]:
        preflight = output / "canonical_production_preflight.json"
        assert preflight.exists()
        assert str(production.PRODUCTION_PATHS["canonical"]) in preflight.read_text(encoding="utf-8")
        return {"writes": 0}

    monkeypatch.setattr(production_cli, "database_evidence", lambda _path: {})
    monkeypatch.setattr(production_cli, "apply_canonical_production", apply)
    args = build_parser().parse_args([
        "--stage", "canonical",
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe", "--output-dir", str(output),
        "--apply", "--confirm-production",
    ])
    report = production_cli.run(args)
    assert report["canonical_migration"] == {"writes": 0}


@pytest.mark.parametrize("name", ["canonical", "provider", "analysis", "market"])
def test_production_request_rejects_every_nonexact_path(name: str, tmp_path: Path) -> None:
    production.validate_production_request(**request(apply=True, confirm_production=True))
    with pytest.raises(PermissionError, match=f"EXACT_PRODUCTION_PATH_REQUIRED:{name}"):
        production.validate_production_request(**request(**{f"{name}_db": tmp_path / f"{name}.db"}))


def test_production_request_rejects_symlink_alias(tmp_path: Path) -> None:
    alias = tmp_path / "canonical.db"
    alias.symlink_to(production.PRODUCTION_PATHS["canonical"])
    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_PATH_REQUIRED:canonical"):
        production.validate_production_request(**request(canonical_db=alias))


def test_refresh_is_idempotent_and_database_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = tmp_path / "analysis.db"
    bootstrap_database(analysis, "fundamentals_analysis", ANALYSIS_SCHEMA_SQL, "old")
    monkeypatch.setattr(production, "calculate_valuation_rows", lambda *_args, **_kwargs: ("source", []))
    first = production.refresh_valuation(tmp_path / "canonical.db", analysis, tmp_path / "market.db", calculated_at="new")
    second = production.refresh_valuation(tmp_path / "canonical.db", analysis, tmp_path / "market.db", calculated_at="newer")
    assert first.rows_inserted == second.rows_inserted == 0
    assert first.rows_deleted == second.rows_deleted == 0
    assert first.rows_unchanged == second.rows_unchanged == 0
    with connect(analysis) as conn:
        assert tuple(conn.execute("SELECT version,applied_at_utc FROM schema_version").fetchone()) == (
            "V4_VALUATION_REVISED_HISTORY_V1", "new"
        )


def test_refresh_failure_rolls_back_schema_and_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = tmp_path / "analysis.db"
    with sqlite3.connect(analysis) as conn:
        conn.execute("CREATE TABLE schema_version(db_name TEXT PRIMARY KEY,version TEXT,applied_at_utc TEXT)")
        conn.execute("INSERT INTO schema_version VALUES ('fundamentals_analysis','old','old')")
        conn.execute("CREATE TABLE marker(value TEXT)")
    monkeypatch.setattr(production, "calculate_valuation_rows", lambda *_args, **_kwargs: ("source", []))

    def fail(conn: sqlite3.Connection, _rows: object) -> object:
        conn.execute("INSERT INTO marker VALUES ('partial')")
        raise RuntimeError("forced valuation failure")

    monkeypatch.setattr(production, "replace_results", fail)
    with pytest.raises(RuntimeError, match="forced valuation failure"):
        production.refresh_valuation(tmp_path / "canonical.db", analysis, tmp_path / "market.db", calculated_at="new")
    with sqlite3.connect(analysis) as conn:
        assert conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0] == 0
        assert conn.execute("SELECT version,applied_at_utc FROM schema_version").fetchone() == ("old", "old")
        assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='valuation_revised_result'").fetchone() is None


def test_score_pipeline_orders_valuation_after_committed_lifecycle() -> None:
    source = inspect.getsource(score_engine.run_score)
    assert source.index('production_preflight.json') < source.index("canonical_before")
    assert source.index("conn.commit()") < source.index("refresh_lifecycle_after_score(paths)")
    assert source.index("refresh_lifecycle_after_score(paths)") < source.index("refresh_valuation_after_lifecycle(paths)")
    assert "FULL_UNIVERSE_FALLBACK" in source


def test_fresh_analysis_schema_contains_active_valuation_contract(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis.db"
    bootstrap_database(analysis, "fundamentals_analysis", ANALYSIS_SCHEMA_SQL, "now")
    with connect(analysis) as conn:
        names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type IN ('table','index')")}
    assert {
        "valuation_revised_result",
        "idx_valuation_revised_current",
        "idx_valuation_revised_status",
    } <= names
