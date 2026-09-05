from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_diagnostic_flags_production import build_parser
from rawcandle.fundamentals.diagnostic_flags.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.diagnostic_flags.persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
)
from rawcandle.fundamentals.diagnostic_flags import production
from rawcandle.fundamentals.schema.operating_working_capital import (
    migrate_and_backfill_operating_working_capital,
)
from rawcandle.fundamentals.score import engine as score_engine
from tests.test_fundamentals_v4_diagnostic_flags_source import databases


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "analysis_db": production.PRODUCTION_PATHS["analysis"],
        "canonical_db": production.PRODUCTION_PATHS["canonical"],
        "provider_db": production.PRODUCTION_PATHS["provider"],
        "market_db": production.PRODUCTION_PATHS["market"],
        "taxonomy_db": production.PRODUCTION_PATHS["taxonomy"],
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(overrides)
    return values


def test_production_gate_requires_exact_paths_contract_and_confirmation(tmp_path: Path):
    assert production.validate_production_request(**request())["analysis"].endswith(
        "fundamentals_analysis.db"
    )
    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION"):
        production.validate_production_request(**request(apply=True))
    with pytest.raises(ValueError, match="REQUIRES_APPLY"):
        production.validate_production_request(**request(confirm_production=True))
    with pytest.raises(ValueError, match="FULL_HISTORY"):
        production.validate_production_request(**request(full_universe=False))
    for field in ("model_fingerprint", "persistence_version", "layout_fingerprint"):
        with pytest.raises(ValueError, match="MISMATCH"):
            production.validate_production_request(**request(**{field: "wrong"}))
    for name in ("analysis", "canonical", "provider", "market", "taxonomy"):
        with pytest.raises(PermissionError, match=f"PATH_REQUIRED:{name}"):
            production.validate_production_request(
                **request(**{f"{name}_db": tmp_path / f"{name}.db"})
            )


def test_production_cli_is_dry_run_by_default():
    args = build_parser().parse_args([
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--taxonomy-db", str(production.PRODUCTION_PATHS["taxonomy"]),
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--persistence-version", PERSISTENCE_VERSION,
        "--layout-fingerprint", LAYOUT_FINGERPRINT,
        "--expected-source-fingerprint", "source",
        "--expected-economic-result-fingerprint", "result",
        "--expected-package-fingerprint", "package",
        "--expected-content-fingerprint", "content",
        "--full-universe", "--output-dir", "/tmp/diagnostic-production-test",
    ])
    assert args.apply is args.confirm_production is args.pipeline_smoke is False
    assert args.as_of_date is None


def test_pipeline_smoke_requires_as_of_date(tmp_path: Path):
    from rawcandle.cli import run_fundamentals_v4_diagnostic_flags_production as cli

    args = type("Args", (), {
        "provider_compatibility": False,
        "working_capital": False,
        "diagnostic_schema": False,
        "pipeline_smoke": True,
        "apply": True,
        "as_of_date": None,
    })()
    with pytest.raises(ValueError, match="REQUIRES_AS_OF_DATE"):
        cli.run(args)


def test_refresh_schema_apply_noop_deep_replay_and_readers(tmp_path: Path):
    paths = databases(tmp_path)
    calculation = production.calculate_production_package(
        analysis_db=paths.analysis_db, canonical_db=paths.canonical_db
    )
    migration = production.migrate_diagnostic_schema(analysis_db=paths.analysis_db)
    assert migration["objects_added"] and migration["quick_check"] == "ok"
    assert production.migrate_diagnostic_schema(
        analysis_db=paths.analysis_db
    )["objects_added"] == []
    first = production.refresh_diagnostic_flags(
        analysis_db=paths.analysis_db,
        canonical_db=paths.canonical_db,
        applied_at_utc="now",
        calculation=calculation,
    )
    second = production.refresh_diagnostic_flags(
        analysis_db=paths.analysis_db,
        canonical_db=paths.canonical_db,
        applied_at_utc="later",
        calculation=calculation,
    )
    assert first["apply"]["outcome"] == "APPLIED"
    assert second["apply"]["outcome"] == "NO_CHANGE"
    assert first["physical_content_fingerprint"] == calculation.physical_content_fingerprint
    assert production.deep_authoritative_replay(
        analysis_db=paths.analysis_db, calculation=calculation
    )["mismatch_count"] == 0
    readers = production.reader_verification(
        analysis_db=paths.analysis_db, calculation=calculation
    )
    assert readers["wrong_fingerprint_rejected"]


def test_working_capital_production_override_requires_exact_pair(tmp_path: Path):
    with pytest.raises(PermissionError, match="EXACT_PRODUCTION_PAIR"):
        migrate_and_backfill_operating_working_capital(
            tmp_path / "provider.db",
            tmp_path / "canonical.db",
            "now",
            allow_production=True,
        )


def test_post_valuation_order_and_failure_isolation(tmp_path: Path, monkeypatch):
    paths = score_engine.ScorePaths(
        tmp_path,
        tmp_path / "artifacts",
        tmp_path / "canonical.db",
        tmp_path / "analysis.db",
        tmp_path / "market.db",
    )
    calls = []
    monkeypatch.setattr(
        score_engine,
        "refresh_diagnostic_after_valuation",
        lambda *a, **kw: calls.append("diagnostic") or {"apply": {}},
    )
    monkeypatch.setattr(
        score_engine,
        "refresh_delta_then_relative_position",
        lambda *a, **kw: calls.append("downstream") or {
            "delta_refresh": {}, "relative_position_refresh": {}, "failed_stages": []
        },
    )
    args = {
        "diagnostic_model_fingerprint": "d",
        "diagnostic_persistence_version": "p",
        "diagnostic_layout_fingerprint": "l",
        "delta_model_fingerprint": "d",
        "delta_persistence_version": "p",
        "delta_layout_fingerprint": "l",
        "relative_position_model_fingerprint": "r",
    }
    assert score_engine.refresh_post_valuation_stages(paths, **args)["failed_stages"] == []
    assert calls == ["diagnostic", "downstream"]

    calls.clear()
    monkeypatch.setattr(
        score_engine,
        "refresh_diagnostic_after_valuation",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("forced")),
    )
    with pytest.raises(score_engine.PostValuationRefreshError) as caught:
        score_engine.refresh_post_valuation_stages(paths, **args)
    assert calls == ["downstream"]
    assert caught.value.report["failed_stages"] == ["DIAGNOSTIC_FLAGS"]


def test_production_schema_contains_no_json_score_or_severity(tmp_path: Path):
    paths = databases(tmp_path)
    production.migrate_diagnostic_schema(analysis_db=paths.analysis_db)
    with sqlite3.connect(paths.analysis_db) as connection:
        schema = "\n".join(
            row[0] or ""
            for row in connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name LIKE 'diagnostic_flag_%'"
            )
        ).lower()
    assert "json" not in schema and "severity" not in schema
    assert "diagnostic_score" not in schema
