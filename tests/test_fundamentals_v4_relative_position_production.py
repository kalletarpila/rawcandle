from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_relative_position_production import build_parser
from rawcandle.cli import run_fundamentals_v4_relative_position_production as production_cli
from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT,
    EcosystemMembership,
    RelativeMeasure,
    RelativeObservation,
    calculate_snapshot,
)
from rawcandle.fundamentals.relative_position.persistence import (
    RelativePositionRepository,
    apply_snapshot as persist_snapshot,
)
from rawcandle.fundamentals.relative_position import production
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL
from rawcandle.fundamentals.score import engine as score_engine


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "canonical_db": production.PRODUCTION_PATHS["canonical"],
        "provider_db": production.PRODUCTION_PATHS["provider"],
        "analysis_db": production.PRODUCTION_PATHS["analysis"],
        "market_db": production.PRODUCTION_PATHS["market"],
        "taxonomy_db": production.PRODUCTION_PATHS["taxonomy"],
        "model_fingerprint": MODEL_FINGERPRINT,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(overrides)
    return values


def observation(company_id: int, measure: RelativeMeasure, offset: float = 0.0):
    return RelativeObservation(
        source_observation_id=f"{measure.value}:{company_id}:{offset}",
        company_id=company_id,
        security_id=company_id,
        ticker=f"T{company_id}",
        measure=measure,
        score=float(company_id) + offset,
        source_status=(
            "SCORE_FULL" if measure == RelativeMeasure.FUNDAMENTAL_SCORE
            else "VALUATION_FULL"
        ),
        source_eligible=True,
        eligibility_reason="ELIGIBLE",
        source_observation_date="2026-08-01",
        source_model_version="SOURCE",
        source_model_fingerprint="source-model",
        source_result_fingerprint=f"source:{company_id}:{measure.value}:{offset}",
        sector="Technology",
        industry="Software",
        ecosystem_memberships=(EcosystemMembership("DATACENTER", "CORE"),),
    )


def snapshot(offset: float = 0.0, *, measures=tuple(RelativeMeasure)):
    rows = [
        observation(company_id, measure, offset)
        for measure in measures
        for company_id in range(1, 21)
    ]
    return calculate_snapshot(
        rows,
        snapshot_date="2026-09-01",
        freshness_days=180,
        classification_fingerprint="classification",
        taxonomy_fingerprint="taxonomy",
    )


def analysis_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(ANALYSIS_SCHEMA_SQL)
        conn.execute("CREATE TABLE upstream_marker(value TEXT)")
        conn.execute("INSERT INTO upstream_marker VALUES ('committed')")


def test_production_gate_defaults_to_dry_run_and_requires_every_gate() -> None:
    args = build_parser().parse_args([
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--taxonomy-db", str(production.PRODUCTION_PATHS["taxonomy"]),
        "--snapshot-date", "2026-09-01",
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe", "--output-dir", "/tmp/relative-production-test",
    ])
    assert args.apply is args.confirm_production is args.pipeline_smoke is False
    production.validate_production_request(**request())
    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION"):
        production.validate_production_request(**request(apply=True))
    with pytest.raises(ValueError, match="REQUIRES_APPLY"):
        production.validate_production_request(**request(confirm_production=True))
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        production.validate_production_request(**request(full_universe=False))
    with pytest.raises(ValueError, match="FINGERPRINT"):
        production.validate_production_request(**request(model_fingerprint="wrong"))


def test_pipeline_smoke_requires_apply() -> None:
    args = build_parser().parse_args([
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--taxonomy-db", str(production.PRODUCTION_PATHS["taxonomy"]),
        "--snapshot-date", "2026-09-01",
        "--model-fingerprint", MODEL_FINGERPRINT,
        "--full-universe", "--output-dir", "/tmp/relative-production-test",
        "--pipeline-smoke",
    ])
    with pytest.raises(ValueError, match="SMOKE_REQUIRES_APPLY"):
        production_cli.run(args)


@pytest.mark.parametrize("name", ["canonical", "provider", "analysis", "market", "taxonomy"])
def test_production_gate_rejects_every_nonexact_path(name: str, tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match=f"PATH_REQUIRED:{name}"):
        production.validate_production_request(**request(**{f"{name}_db": tmp_path / f"{name}.db"}))


def test_production_gate_rejects_symlink_and_normalized_alias(tmp_path: Path) -> None:
    alias = tmp_path / "analysis.db"
    alias.symlink_to(production.PRODUCTION_PATHS["analysis"])
    with pytest.raises(PermissionError, match="PATH_REQUIRED:analysis"):
        production.validate_production_request(**request(analysis_db=alias))
    normalized = production.PRODUCTION_PATHS["analysis"].parent / ".." / "data" / "fundamentals_analysis.db"
    with pytest.raises(PermissionError, match="PATH_REQUIRED:analysis"):
        production.validate_production_request(**request(analysis_db=normalized))


def test_refresh_first_noop_and_changed_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis = tmp_path / "analysis.db"
    analysis_database(analysis)
    current = snapshot()
    monkeypatch.setattr(production, "calculate_current_snapshot", lambda **_: current)
    args = {
        "canonical_db": tmp_path / "canonical.db",
        "analysis_db": analysis,
        "market_db": tmp_path / "market.db",
        "taxonomy_db": tmp_path / "taxonomy.db",
        "snapshot_date": "2026-09-01",
        "model_fingerprint": MODEL_FINGERPRINT,
        "applied_at_utc": "2026-09-01T23:00:00Z",
    }
    first = production.refresh_relative_position(**args)
    second = production.refresh_relative_position(**args)
    assert first.apply["result_rows_inserted"] == len(current.results)
    assert second.apply["result_rows_inserted"] == second.apply["result_rows_deleted"] == 0
    assert second.apply["coverage_rows_inserted"] == second.apply["coverage_rows_deleted"] == 0
    assert second.apply["activation_changes"] == 0

    changed = snapshot(1.0)
    monkeypatch.setattr(production, "calculate_current_snapshot", lambda **_: changed)
    third = production.refresh_relative_position(**args)
    assert third.apply["activation_changes"] == 1
    with sqlite3.connect(analysis) as conn:
        assert conn.execute("SELECT value FROM upstream_marker").fetchone()[0] == "committed"


def test_relative_failure_preserves_active_and_committed_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis = tmp_path / "analysis.db"
    analysis_database(analysis)
    args = {
        "canonical_db": tmp_path / "canonical.db", "analysis_db": analysis,
        "market_db": tmp_path / "market.db", "taxonomy_db": tmp_path / "taxonomy.db",
        "snapshot_date": "2026-09-01", "model_fingerprint": MODEL_FINGERPRINT,
        "applied_at_utc": "2026-09-01T23:00:00Z",
    }
    monkeypatch.setattr(production, "calculate_current_snapshot", lambda **_: snapshot())
    production.refresh_relative_position(**args)
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        old = RelativePositionRepository(conn).active_metadata(model_fingerprint=MODEL_FINGERPRINT)["snapshot_id"]

    changed = snapshot(1.0)
    monkeypatch.setattr(production, "calculate_current_snapshot", lambda **_: changed)

    def fail(conn, value, **kwargs):
        return persist_snapshot(conn, value, **kwargs, inject_failure_at="before_activation")

    monkeypatch.setattr(production, "apply_snapshot", fail)
    with pytest.raises(RuntimeError, match="PRE_ACTIVATION"):
        production.refresh_relative_position(**args)
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        assert RelativePositionRepository(conn).active_metadata(model_fingerprint=MODEL_FINGERPRINT)["snapshot_id"] == old
        assert conn.execute("SELECT value FROM upstream_marker").fetchone()[0] == "committed"


def test_missing_required_measure_is_rejected() -> None:
    with pytest.raises(ValueError, match="COMPLETE_SNAPSHOT_REQUIRES_BOTH_MEASURES"):
        production.validate_required_upstream(
            snapshot(measures=(RelativeMeasure.FUNDAMENTAL_SCORE,))
        )


def test_pipeline_order_and_explicit_fingerprint_propagation() -> None:
    source = inspect.getsource(score_engine.run_score)
    assert source.index("refresh_lifecycle_after_score") < source.index("refresh_valuation_after_lifecycle")
    assert source.index("refresh_valuation_after_lifecycle") < source.index("refresh_delta_then_relative_position")
    post = inspect.getsource(score_engine.refresh_delta_then_relative_position)
    assert post.index("refresh_delta_after_valuation") < post.index("refresh_relative_position_after_valuation")
    hook = inspect.getsource(score_engine.refresh_relative_position_after_valuation)
    assert "model_fingerprint=model_fingerprint" in hook
    assert "refresh_relative_position" in hook
    assert "provider" not in hook.lower()


def test_relative_failure_is_reported_as_pipeline_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = score_engine.ScorePaths(
        tmp_path, tmp_path / "artifacts", tmp_path / "canonical.db",
        tmp_path / "analysis.db", tmp_path / "market.db",
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("forced relative failure")

    monkeypatch.setattr(score_engine, "refresh_relative_position_after_valuation", fail)
    with pytest.raises(RuntimeError, match="forced relative failure"):
        score_engine.refresh_relative_position_after_valuation(
            paths, model_fingerprint=MODEL_FINGERPRINT
        )
