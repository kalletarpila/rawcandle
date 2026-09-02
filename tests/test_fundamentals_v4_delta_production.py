from __future__ import annotations

from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_delta_production import build_parser
from rawcandle.fundamentals.delta import production
from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import LAYOUT_FINGERPRINT, PERSISTENCE_VERSION
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FP
from rawcandle.fundamentals.score import engine as score_engine
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_FP
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_FP
from tests.test_fundamentals_v4_delta_source import build_databases


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "analysis_db": production.PRODUCTION_PATHS["analysis"],
        "canonical_db": production.PRODUCTION_PATHS["canonical"],
        "provider_db": production.PRODUCTION_PATHS["provider"],
        "market_db": production.PRODUCTION_PATHS["market"],
        "taxonomy_db": production.PRODUCTION_PATHS["taxonomy"],
        "score_model_fingerprint": SCORE_FP,
        "lifecycle_model_fingerprint": LIFECYCLE_FP,
        "valuation_model_fingerprint": VALUATION_FP,
        "delta_model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(overrides)
    return values


def test_production_cli_defaults_to_dry_run() -> None:
    args = build_parser().parse_args([
        "--analysis-db", str(production.PRODUCTION_PATHS["analysis"]),
        "--canonical-db", str(production.PRODUCTION_PATHS["canonical"]),
        "--provider-db", str(production.PRODUCTION_PATHS["provider"]),
        "--market-db", str(production.PRODUCTION_PATHS["market"]),
        "--taxonomy-db", str(production.PRODUCTION_PATHS["taxonomy"]),
        "--as-of-date", "2026-09-01",
        "--score-model-fingerprint", SCORE_FP,
        "--lifecycle-model-fingerprint", LIFECYCLE_FP,
        "--valuation-model-fingerprint", VALUATION_FP,
        "--delta-model-fingerprint", MODEL_FINGERPRINT,
        "--persistence-version", PERSISTENCE_VERSION,
        "--layout-fingerprint", LAYOUT_FINGERPRINT,
        "--fundamental-source-fingerprint", "fundamental-source",
        "--lifecycle-source-fingerprint", "lifecycle-source",
        "--valuation-source-fingerprint", "valuation-source",
        "--economic-package-fingerprint", "economic-package",
        "--full-universe", "--output-dir", "/tmp/delta-production-test",
    ])
    assert args.apply is args.confirm_production is args.deep_replay is args.migrate_only is args.pipeline_smoke is False


def test_production_gate_requires_every_authorization() -> None:
    production.validate_production_request(**request())
    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION"):
        production.validate_production_request(**request(apply=True))
    with pytest.raises(ValueError, match="REQUIRES_APPLY"):
        production.validate_production_request(**request(confirm_production=True))
    with pytest.raises(ValueError, match="FULL_HISTORY"):
        production.validate_production_request(**request(full_universe=False))
    for field in (
        "score_model_fingerprint", "lifecycle_model_fingerprint",
        "valuation_model_fingerprint", "delta_model_fingerprint",
    ):
        with pytest.raises(ValueError, match="FINGERPRINT"):
            production.validate_production_request(**request(**{field: "wrong"}))
    with pytest.raises(ValueError, match="PERSISTENCE_VERSION"):
        production.validate_production_request(**request(persistence_version="wrong"))
    with pytest.raises(ValueError, match="LAYOUT_FINGERPRINT"):
        production.validate_production_request(**request(layout_fingerprint="wrong"))


@pytest.mark.parametrize("name", ["analysis", "canonical", "provider", "market", "taxonomy"])
def test_production_gate_rejects_nonexact_paths(name: str, tmp_path: Path) -> None:
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


def paths(tmp_path: Path) -> score_engine.ScorePaths:
    return score_engine.ScorePaths(
        tmp_path, tmp_path / "artifacts", tmp_path / "canonical.db",
        tmp_path / "analysis.db", tmp_path / "market.db",
    )


def orchestration_args() -> dict[str, str]:
    return {
        "delta_model_fingerprint": MODEL_FINGERPRINT,
        "delta_persistence_version": PERSISTENCE_VERSION,
        "delta_layout_fingerprint": LAYOUT_FINGERPRINT,
        "relative_position_model_fingerprint": "relative-fingerprint",
    }


def test_pipeline_runs_delta_before_relative_and_propagates_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(score_engine, "refresh_delta_after_valuation", lambda *a, **kw: calls.append(("delta", kw)) or {"apply": {"outcome": "NO_CHANGE"}})
    monkeypatch.setattr(score_engine, "refresh_relative_position_after_valuation", lambda *a, **kw: calls.append(("relative", kw)) or {"apply": {"result_rows_inserted": 0}})
    report = score_engine.refresh_delta_then_relative_position(paths(tmp_path), **orchestration_args())
    assert [name for name, _ in calls] == ["delta", "relative"]
    assert calls[0][1]["model_fingerprint"] == MODEL_FINGERPRINT
    assert calls[0][1]["persistence_version"] == PERSISTENCE_VERSION
    assert calls[0][1]["layout_fingerprint"] == LAYOUT_FINGERPRINT
    assert report["failed_stages"] == []


def test_delta_failure_still_runs_independent_relative_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    def fail_delta(*_args, **_kwargs):
        calls.append("delta")
        raise RuntimeError("delta failed")
    monkeypatch.setattr(score_engine, "refresh_delta_after_valuation", fail_delta)
    monkeypatch.setattr(score_engine, "refresh_relative_position_after_valuation", lambda *a, **kw: calls.append("relative") or {"apply": {"result_rows_inserted": 0}})
    with pytest.raises(score_engine.PostValuationRefreshError) as caught:
        score_engine.refresh_delta_then_relative_position(paths(tmp_path), **orchestration_args())
    assert calls == ["delta", "relative"]
    assert caught.value.report["failed_stages"] == ["DELTA"]
    assert caught.value.report["relative_position_refresh"]["status"] == "COMPLETE"


def test_relative_failure_happens_after_committed_delta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(score_engine, "refresh_delta_after_valuation", lambda *a, **kw: calls.append("delta") or {"apply": {"outcome": "APPLIED"}})
    def fail_relative(*_args, **_kwargs):
        calls.append("relative")
        raise RuntimeError("relative failed")
    monkeypatch.setattr(score_engine, "refresh_relative_position_after_valuation", fail_relative)
    with pytest.raises(score_engine.PostValuationRefreshError) as caught:
        score_engine.refresh_delta_then_relative_position(paths(tmp_path), **orchestration_args())
    assert calls == ["delta", "relative"]
    assert caught.value.report["delta_refresh"]["status"] == "COMPLETE"
    assert caught.value.report["failed_stages"] == ["RELATIVE_POSITION"]


def test_refresh_applies_then_returns_no_change_with_routine_check(tmp_path: Path) -> None:
    source_paths = build_databases(tmp_path / "source")
    calculation = production.calculate_production_package(
        analysis_db=source_paths.analysis_db,
        canonical_db=source_paths.canonical_db,
        score_model_fingerprint=SCORE_FP,
        lifecycle_model_fingerprint=LIFECYCLE_FP,
        valuation_model_fingerprint=VALUATION_FP,
    )
    first = production.refresh_delta(
        analysis_db=source_paths.analysis_db,
        canonical_db=source_paths.canonical_db,
        applied_at_utc="2026-09-01T00:00:00Z", calculation=calculation,
    )
    second = production.refresh_delta(
        analysis_db=source_paths.analysis_db,
        canonical_db=source_paths.canonical_db,
        applied_at_utc="2026-09-01T00:00:00Z", calculation=calculation,
    )
    assert first.apply["outcome"] == "APPLIED"
    assert first.physical_content_fingerprint == calculation.physical_content_fingerprint
    assert second.apply["outcome"] == "NO_CHANGE"
    assert second.quick_check["ok"] and not second.quick_check["authoritative_replay"]
