from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from rawcandle.fundamentals.operating_income_v2 import (
    delta, diagnostic_flags, diagnostic_flags_eight, lifecycle, phase10b,
)
from rawcandle.fundamentals.operating_income_v2 import relative_position, score, valuation
from rawcandle.fundamentals.operating_income_v2.persistence import (
    MANIFEST_TABLE, ensure_schema, migrate_copy, physical_fingerprint,
)
from rawcandle.fundamentals.operating_income_v2.readers import ParallelModelRepository
from rawcandle.fundamentals.operating_income_v2.activation import (
    activate_package,
    activate_v2,
    active_family,
    assert_v2_active,
    deactivate_v2,
)
from rawcandle.fundamentals.operating_income_v2.readers import ActiveModelRepository
from rawcandle.fundamentals.operating_income_v2.reporting import render_company_report
from rawcandle.fundamentals.operating_income_v2.rehearsal import _ro, _score_delta_observation
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL
from rawcandle.fundamentals.schema.analysis_compat_schema import DIAGNOSTIC_SCHEMA_SQL, LIFECYCLE_SCHEMA_SQL
from tests.test_fundamentals_v4_operating_income_v2 import (
    diagnostic_endpoint, relative_observation, ttm, valuation_observation,
)


def _calculated() -> dict[str, object]:
    source = ttm(1, operating_margin=0.10)
    scores = score.compute_score_rows([source], {}, generated_at="test", run_id="test")
    observation = lifecycle.LifecycleObservation(
        1, 1, 2023, "Q1", "2023-03-28", "2023-03-29", True,
        100.0, 10.0, 8.0, None, None, False, (25.0, 25.0, 25.0, 25.0), 1,
    )
    state_result = lifecycle.replay_state_machine((lifecycle.classify_raw_state(observation),))[0]
    value = valuation.calculate_valuation(
        replace(valuation_observation(), fiscal_year=2023, fiscal_quarter="Q1", quarter_id=1,
                period_end="2023-03-28", fundamental_available_date="2023-03-29"),
        (valuation.PriceBar("2023-03-29", 10.0, 10.0, 10.0, 10.0),),
    )
    delta_observation = _score_delta_observation(scores[0], source)
    delta_result = delta.calculate_fundamental_delta(
        delta_observation, (delta_observation,), source_fingerprint="fixture",
    )
    diagnostic_rows = []
    current = phase10b._candidate_endpoint(
        source, diagnostic_endpoint(1, 10.0), coherent=True,
    )
    for result in diagnostic_flags_eight.evaluate_diagnostic_flags(
        diagnostic_flags_eight.DiagnosticInput(current, None, False, False)
    ):
        diagnostic_rows.append({
            "company_id": 1, "quarter_id": 1, "ticker": "TEST",
            "flag_name": result.flag_name, "status": result.status.value,
            "reason_code": result.reason_code, "triggered": result.triggered,
            "comparison_quarter_id": result.comparison_quarter_id,
            "effective_available_date": result.effective_available_date,
            "evidence": {item.name: item.value for item in result.evidence},
            "model_version": result.model_version,
            "model_fingerprint": result.model_fingerprint,
        })
    relative_rows = []
    for company_id in range(1, 21):
        relative_rows.append(relative_observation(company_id, float(company_id)))
        relative_rows.append(replace(
            relative_observation(company_id, float(company_id)),
            source_observation_id=f"V:{company_id}",
            measure=relative_position.RelativeMeasure.ABSOLUTE_VALUATION_SCORE,
            source_model_version=valuation.MODEL_VERSION,
            source_model_fingerprint=valuation.MODEL_FINGERPRINT,
        ))
    relative = relative_position.calculate_snapshot(
        relative_rows, snapshot_date="2026-09-01", freshness_days=180,
        classification_fingerprint="classification", taxonomy_fingerprint="taxonomy",
    )
    valuation_source = {
        **value.to_dict(), "security_active": 1, "sector": "Technology",
        "industry": "Software - Application", "source_fingerprint": "current-source",
    }
    return {
        "rows": [source], "score_v2": scores, "lifecycle_v2": {(1, 1): state_result},
        "valuation_source_rows": [valuation_source], "valuation_v2": {(1, 1): value},
        "delta_results": [delta_result], "diagnostics_full": diagnostic_rows,
        "relative": relative,
        "taxonomy_dependency": {
            "domain": "dc_ecosystem", "version": "DC_TEST_V1",
            "semantic_fingerprint": "taxonomy",
        },
    }


@pytest.fixture
def database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(ANALYSIS_SCHEMA_SQL)
    conn.executescript(LIFECYCLE_SCHEMA_SQL)
    conn.executescript(DIAGNOSTIC_SCHEMA_SQL)
    ensure_schema(conn)
    conn.commit()
    yield conn
    conn.close()


def test_fresh_analysis_schema_omits_retired_v1_structures(database: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in database.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    assert "lifecycle_result" not in tables
    assert "valuation_result" not in tables
    assert "operating_income_v2_package_manifest_history" not in tables
    assert {"lifecycle_revised_result", "valuation_revised_result"} <= tables


def test_complete_parallel_apply_noop_and_v2_readers(database: sqlite3.Connection, tmp_path: Path) -> None:
    calculated = _calculated()
    first = phase10b.apply_candidate_package(database, calculated, applied_at="2026-09-01T00:00:00Z")
    second = phase10b.apply_candidate_package(database, calculated, applied_at="2026-09-01T00:00:00Z")
    assert first.outcome == "APPLIED"
    assert first.rows["score"] == first.rows["lifecycle"] == first.rows["valuation"] == 1
    assert first.rows["score_component"] == first.rows["delta_component"] == 7
    assert first.rows["diagnostic_evaluation"] == 8
    assert second.outcome == "NO_CHANGE" and second.logical_changes == 0
    assert tuple(database.execute(
        "SELECT taxonomy_domain,taxonomy_version,taxonomy_semantic_fingerprint,calculation_as_of_date "
        "FROM relative_position_v2_taxonomy_dependency"
    ).fetchone()) == ("dc_ecosystem", "DC_TEST_V1", "taxonomy", "2026-09-01")
    assert first.physical_content_fingerprint == second.physical_content_fingerprint
    current_manifest = database.execute(f"SELECT persistence_fingerprint FROM {MANIFEST_TABLE}").fetchone()[0]
    assert database.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' "
        "AND name='operating_income_v2_package_manifest_history'"
    ).fetchone() is None
    assert ParallelModelRepository(database).package_manifest(current_manifest)[
        "persistence_fingerprint"
    ] == current_manifest
    repository = ParallelModelRepository(database)
    repository.assert_v2_bundle()
    assert repository.score_current(1, model_fingerprint=score.MODEL_FINGERPRINT)["model_fingerprint"] == score.MODEL_FINGERPRINT
    with pytest.raises(ValueError, match="UNKNOWN_SCORE_MODEL_FINGERPRINT"):
        repository.score_current(1, model_fingerprint="retired-v1")
    assert repository.score_quarter(1, 1, model_fingerprint=score.MODEL_FINGERPRINT)["quarter_id"] == 1
    assert repository.lifecycle_quarter(1, 2023, "Q1", model_fingerprint=lifecycle.MODEL_FINGERPRINT)["raw_state"]
    assert repository.valuation_quarter(1, 2023, "Q1", model_fingerprint=valuation.MODEL_FINGERPRINT)["valuation_status"]
    assert repository.delta_quarter(1, 2023, 1, model_fingerprint=delta.MODEL_FINGERPRINT)["fiscal_quarter"] == 1
    assert repository.diagnostic_quarter(1, 2023, 1, model_fingerprint=diagnostic_flags_eight.MODEL_FINGERPRINT)["evaluations"]
    assert len(repository.diagnostic_current(1, model_fingerprint=diagnostic_flags_eight.MODEL_FINGERPRINT)["evaluations"]) == 8
    with pytest.raises(ValueError, match="UNKNOWN_SCORE"):
        repository.score_current(1, model_fingerprint="unknown")

    market = tmp_path / "market.db"
    with sqlite3.connect(market) as conn:
        conn.execute("CREATE TABLE osakedata(osake TEXT,pvm TEXT,close REAL)")
        conn.execute("INSERT INTO osakedata VALUES('TEST','2026-09-01',12)")
    report = render_company_report(database, company_id=1, market_db=market, output=tmp_path / "report.md")
    text = report.read_text()
    assert "Operating Profitability" in text and "Operating Income Yield" in text


def test_manifest_mixing_tamper_and_failure_are_rejected(database: sqlite3.Connection) -> None:
    calculated = _calculated()
    phase10b.apply_candidate_package(database, calculated, applied_at="2026-09-01T00:00:00Z")
    original = physical_fingerprint(database)
    component = database.execute("SELECT score_component_id,component_score FROM score_component ORDER BY score_component_id DESC LIMIT 1").fetchone()
    database.execute("UPDATE score_component SET component_score=999 WHERE score_component_id=?", (component[0],))
    database.commit()
    with pytest.raises(RuntimeError, match="PHYSICAL_CONTENT_CHANGED"):
        phase10b.apply_candidate_package(database, calculated, applied_at="2026-09-01T00:00:00Z")
    database.execute("UPDATE score_component SET component_score=? WHERE score_component_id=?", (component[1], component[0]))
    assert physical_fingerprint(database) == original
    database.execute(f"UPDATE {MANIFEST_TABLE} SET model_manifest_json='{{}}'")
    database.commit()
    with pytest.raises(ValueError, match="MODEL_MANIFEST_MISMATCH"):
        ParallelModelRepository(database).assert_v2_bundle()

    database.execute(f"DELETE FROM {MANIFEST_TABLE}")
    database.commit()
    before = physical_fingerprint(database)
    with pytest.raises(RuntimeError, match="INJECTED_PHASE10B_LIFECYCLE_FAILURE"):
        phase10b.apply_candidate_package(database, calculated, applied_at="later", inject_failure_at="lifecycle")
    assert physical_fingerprint(database) == before


def test_migration_guards_and_wal_aware_reader(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        migrate_copy(Path("relative.db"))
    production_alias = tmp_path / "alias.db"
    production_alias.symlink_to(Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"))
    with pytest.raises(PermissionError):
        migrate_copy(production_alias)

    wal = tmp_path / "wal.db"
    writer = sqlite3.connect(wal)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE observed(value TEXT)")
    writer.execute("INSERT INTO observed VALUES('committed-in-wal')")
    writer.commit()
    assert Path(str(wal) + "-wal").stat().st_size > 0
    with _ro(wal) as reader:
        assert reader.execute("SELECT value FROM observed").fetchone()[0] == "committed-in-wal"
    writer.close()


def test_activation_is_atomic_coherent_and_reversible(database: sqlite3.Connection) -> None:
    with pytest.raises(LookupError, match="NOT_ACTIVE"):
        assert_v2_active(database)
    phase10b.apply_candidate_package(database, _calculated(), applied_at="2026-09-01T00:00:00Z")
    database.execute("BEGIN")
    activated = activate_v2(database, activated_at="2026-09-06T00:00:00Z")
    database.commit()
    assert activated.family_version == "OPERATING_INCOME_MODEL_FAMILY_V2"
    assert active_family(database) == activated
    assert activate_v2(database, activated_at="later") == activated
    active = ActiveModelRepository(database)
    assert active.score_current(1)["model_fingerprint"] == score.MODEL_FINGERPRINT
    assert active.lifecycle_current(1)["model_fingerprint"] == lifecycle.MODEL_FINGERPRINT
    assert active.valuation_current(1)["model_fingerprint"] == valuation.MODEL_FINGERPRINT
    assert active.delta_current(1)["company_id"] == 1
    assert database.execute(
        "SELECT model_fingerprint FROM fundamental_delta_package WHERE model_fingerprint=?",
        (delta.MODEL_FINGERPRINT,),
    ).fetchone()[0] == delta.MODEL_FINGERPRINT
    assert active.diagnostic_current(1)["evaluations"]
    assert isinstance(active.relative_current(1), list)
    with pytest.raises(ValueError, match="UNKNOWN_SCORE_MODEL_FINGERPRINT"):
        ParallelModelRepository(database).score_current(1, model_fingerprint="retired-v1")

    archived = "archived-package"
    with pytest.raises(ValueError, match="UNKNOWN_PACKAGE"):
        activate_package(database, archived, activated_at="later")
    database.execute(
        "UPDATE fundamentals_active_model_family SET persistence_fingerprint=?",
        (archived,),
    )
    with pytest.raises(ValueError, match="ACTIVE_PACKAGE_MISMATCH"):
        assert_v2_active(database)
    database.rollback()

    database.execute("BEGIN")
    deactivate_v2(database)
    database.commit()
    assert active_family(database) is None
