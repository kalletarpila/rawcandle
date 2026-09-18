from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals import phase12d
from rawcandle.fundamentals.schema.analysis_compat_schema import DIAGNOSTIC_SCHEMA_SQL, LIFECYCLE_SCHEMA_SQL
from rawcandle.fundamentals.operating_income_v2 import (
    diagnostic_flags_eight,
    phase10b,
    persistence,
)
from rawcandle.fundamentals.operating_income_v2.readers import ParallelModelRepository
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL, bootstrap_all
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation
from rawcandle.research.fundamental_profile_baseline.contract import (
    CONTRACT_FINGERPRINT as PHASE12B_CONTRACT_FINGERPRINT,
)
from tests.test_fundamentals_v4_diagnostic_flags_phase10b import endpoint
from tests.test_fundamentals_v4_operating_income_v2_persistence import _calculated


def _databases(tmp_path: Path) -> tuple[Path, Path, Path]:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, "bootstrap")
    with sqlite3.connect(canonical) as connection:
        connection.execute(
            "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) "
            "VALUES(1,'AAA','AAA','ACTIVE','n','n')"
        )
        connection.execute(
            "INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) "
            "VALUES(1,1,'AAA',1,'n','n')"
        )
    with sqlite3.connect(provider) as connection:
        connection.execute(
            "INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) "
            "VALUES('run','SHARADAR','n','COMPLETE','fixture')"
        )
    return provider, canonical, analysis


def _row(quarter: int, *, revision: int = 1, operating_income: int = 10) -> dict[str, object]:
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    period = f"2023-{month_day}"
    return {
        "ticker": "AAA", "permaticker": "1", "dimension": "ARQ",
        "calendardate": period, "reportperiod": period,
        "fiscalperiod": f"2023-Q{quarter}", "date": f"2023-{quarter * 3 + 1:02d}-30",
        "lastupdated": f"2026-01-{revision:02d}", "revenue": 100,
        "gp": 50, "opinc": operating_income, "ebit": 12, "ebitda": 14,
        "netinc": 8, "netinccmn": 7, "ncfo": 11, "capex": -2, "fcf": 9,
        "cashneq": 20, "debt": 5, "debtc": 1, "debtnc": 4,
        "sharesbas": 10, "shareswa": 10, "shareswadil": 11,
        "receivables": 12, "inventory": 6, "payables": 7,
        "deferredrev": 3, "assets": 200,
    }


def _insert(provider: Path, row: dict[str, object]) -> None:
    with sqlite3.connect(provider) as connection:
        connection.row_factory = sqlite3.Row
        assert insert_production_sharadar_observation(
            connection, row, "run", "accepted", company_id=1, security_id=1
        )


def _logical_guard_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE guarded("
            "id INTEGER PRIMARY KEY, amount REAL, status TEXT, reason TEXT, payload BLOB)"
        )
        connection.executemany(
            "INSERT INTO guarded(id,amount,status,reason,payload) VALUES(?,?,?,?,?)",
            [
                (1, 10.5, "READY", "BASELINE", b"alpha"),
                (2, None, "LIMITED", None, b"beta"),
            ],
        )


def _inventory_wrapper(role: str, path: Path) -> dict[str, object]:
    return {
        "databases": {role: phase12d.database_inventory(path)},
        "reports": {},
        "scheduler": {"exists": False, "sha256": None, "size": None, "mtime_ns": None},
    }


def _logical_guard_inventories(
    tmp_path: Path, role: str, mutation_sql: str
) -> tuple[dict[str, object], dict[str, object]]:
    db = tmp_path / f"{role}.db"
    _logical_guard_db(db)
    before = _inventory_wrapper(role, db)
    with sqlite3.connect(db) as connection:
        connection.execute(mutation_sql)
    after = _inventory_wrapper(role, db)
    return before, after


def test_revision_aware_canonical_rebuild_preserves_identity_and_is_idempotent(
    tmp_path: Path,
) -> None:
    provider, canonical, _ = _databases(tmp_path)
    _insert(provider, _row(1))
    first = phase12d.reconcile_canonical(provider, canonical, applied_at="fixed")
    with sqlite3.connect(canonical) as connection:
        quarter_id = connection.execute("SELECT quarter_id FROM v4_quarter").fetchone()[0]
    assert first["NEW_HISTORY"] == 1

    _insert(provider, _row(1, revision=2, operating_income=15))
    revised = phase12d.reconcile_canonical(provider, canonical, applied_at="fixed")
    with sqlite3.connect(canonical) as connection:
        actual = connection.execute(
            "SELECT q.quarter_id,f.operating_income FROM v4_quarter q "
            "JOIN v4_quarter_financials f USING(quarter_id)"
        ).fetchone()
    assert actual == (quarter_id, 15)
    assert revised["REVISED_OVERLAP"] == 1
    assert revised["unexplained_or_stale_rows"] == 0

    unchanged = phase12d.reconcile_canonical(provider, canonical, applied_at="fixed")
    assert unchanged["UNCHANGED_OVERLAP"] == 1
    assert unchanged.get("NEW_HISTORY", 0) == unchanged.get("REVISED_OVERLAP", 0) == 0


def test_canonical_and_ttm_failures_roll_back_and_ttm_replay_is_noop(tmp_path: Path) -> None:
    provider, canonical, _ = _databases(tmp_path)
    for quarter in range(1, 5):
        _insert(provider, _row(quarter))
    before = phase12d.canonical_logical_fingerprint(canonical)
    with pytest.raises(RuntimeError, match="CANONICAL_FAILURE"):
        phase12d.reconcile_canonical(
            provider, canonical, applied_at="fixed", inject_failure=True
        )
    assert phase12d.canonical_logical_fingerprint(canonical) == before

    phase12d.reconcile_canonical(provider, canonical, applied_at="fixed")
    before_ttm = phase12d.persisted_ttm_fingerprint(canonical)
    with pytest.raises(RuntimeError, match="TTM_FAILURE"):
        phase12d.rebuild_ttm(canonical, applied_at="fixed", inject_failure=True)
    assert phase12d.persisted_ttm_fingerprint(canonical) == before_ttm
    first = phase12d.rebuild_ttm(canonical, applied_at="fixed")
    second = phase12d.rebuild_ttm(canonical, applied_at="fixed")
    assert first["outcome"] == "APPLIED"
    assert second == {
        "outcome": "NO_CHANGE", "rows": 4,
        "fingerprint": first["fingerprint"], "logical_writes": 0,
    }
    assert phase12d._provenance_reconciliation(canonical)["passed"] is True
    assert phase12d._ttm_chain_reconciliation(canonical)["passed"] is True


def test_eight_flag_candidate_apply_refreshes_complete_package_and_noops() -> None:
    calculated = _calculated()
    evaluations = diagnostic_flags_eight.evaluate_diagnostic_flags(
        diagnostic_flags_eight.DiagnosticInput(endpoint(), None, False, False)
    )
    calculated["diagnostics_full"] = [
        {
            "company_id": 1, "quarter_id": 1, "ticker": "TEST",
            "flag_name": result.flag_name, "status": result.status.value,
            "reason_code": result.reason_code, "triggered": result.triggered,
            "comparison_quarter_id": result.comparison_quarter_id,
            "effective_available_date": result.effective_available_date,
            "evidence": {item.name: item.value for item in result.evidence},
            "model_version": result.model_version,
            "model_fingerprint": result.model_fingerprint,
        }
        for result in evaluations
    ]
    calculated["diagnostic_source_fingerprint"] = "source"
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(ANALYSIS_SCHEMA_SQL)
    connection.executescript(LIFECYCLE_SCHEMA_SQL)
    connection.executescript(DIAGNOSTIC_SCHEMA_SQL)
    persistence.ensure_schema(connection)
    candidate = "phase12d-candidate"
    first = phase10b.apply_candidate_package(
        connection, calculated, applied_at="fixed",
        persistence_fingerprint=candidate,
    )
    second = phase10b.apply_candidate_package(
        connection, calculated, applied_at="fixed",
        persistence_fingerprint=candidate,
    )
    assert first.outcome == "APPLIED"
    assert first.rows["score"] == first.rows["lifecycle"] == first.rows["valuation"] == 1
    assert first.rows["delta"] == first.rows["diagnostic_endpoint"] == 1
    assert first.rows["diagnostic_evaluation"] == 8
    assert second.outcome == "NO_CHANGE" and second.logical_changes == 0
    ParallelModelRepository(connection).assert_v2_bundle(
        phase10b.MODEL_MAP, persistence_fingerprint=candidate
    )
    connection.close()


def test_contract_and_safety_boundaries_are_explicit(tmp_path: Path) -> None:
    assert phase12d.REBUILD_CONTRACT["phase12b_contract"] == PHASE12B_CONTRACT_FINGERPRINT
    assert phase12d.REBUILD_CONTRACT["history_semantics"] == "currently revised non-PIT"
    assert phase12d.REBUILD_CONTRACT["package"] == phase10b.MODEL_MAP
    with pytest.raises(ValueError, match="OUTPUT_PATH_REJECTED"):
        phase12d.run(tmp_path / "outside")


def test_production_comparison_allows_only_content_identical_sidecar_mtime() -> None:
    before = {
        "databases": {
            "analysis": {
                "sha256": "database",
                "wal": {"exists": False, "size": None, "mtime_ns": None, "sha256": None},
                "shm": {"exists": True, "size": 32768, "mtime_ns": 1, "sha256": "sidecar"},
            }
        },
        "reports": {},
    }
    after = json.loads(json.dumps(before))
    after["databases"]["analysis"]["shm"]["mtime_ns"] = 2
    comparison = phase12d.compare_production_inventory(before, after)
    assert comparison["identical"] is True
    assert comparison["exact_metadata_identical"] is False
    assert comparison["ignored_content_identical_sidecar_mtime_changes"] == [{
        "database": "analysis", "sidecar": "shm",
        "before_mtime_ns": 1, "after_mtime_ns": 2, "sha256": "sidecar",
    }]

    after["databases"]["analysis"]["shm"]["sha256"] = "changed"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False


def test_production_comparison_allows_only_logically_identical_database_physical_drift() -> None:
    before = {
        "databases": {
            "taxonomy": {
                "sha256": "database",
                "size": 100,
                "mtime_ns": 1,
                "schema_fingerprint": "schema",
                "page_count": 10,
                "freelist_count": 0,
                "row_counts": {"taxonomy_table": 5},
                "quick_check": "ok",
                "foreign_key_errors": 0,
                "wal": {"exists": True, "size": 0, "mtime_ns": 1, "sha256": "empty"},
                "shm": {"exists": True, "size": 32768, "mtime_ns": 1, "sha256": "sidecar"},
            }
        },
        "reports": {},
    }
    after = json.loads(json.dumps(before))
    after["databases"]["taxonomy"]["mtime_ns"] = 2
    after["databases"]["taxonomy"]["sha256"] = "layout-changed"
    after["databases"]["taxonomy"]["size"] = 120
    after["databases"]["taxonomy"]["page_count"] = 12
    after["databases"]["taxonomy"]["freelist_count"] = 2
    comparison = phase12d.compare_production_inventory(before, after)

    assert comparison["identical"] is True
    assert comparison["exact_metadata_identical"] is False
    assert comparison["ignored_content_identical_database_mtime_changes"] == [{
        "database": "taxonomy",
        "before_mtime_ns": 1,
        "after_mtime_ns": 2,
        "sha256": "database",
    }]

    after["databases"]["taxonomy"]["schema_fingerprint"] = "changed"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False

    after = json.loads(json.dumps(before))
    after["databases"]["taxonomy"]["row_counts"]["taxonomy_table"] = 6
    assert phase12d.compare_production_inventory(before, after)["identical"] is False

    after = json.loads(json.dumps(before))
    after["databases"]["taxonomy"]["quick_check"] = "database disk image is malformed"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False


@pytest.mark.parametrize("role", ["provider", "canonical", "analysis"])
def test_production_comparison_rejects_same_row_count_numeric_value_mutation(
    tmp_path: Path, role: str
) -> None:
    before, after = _logical_guard_inventories(
        tmp_path, role, "UPDATE guarded SET amount=11.5 WHERE id=1"
    )
    comparison = phase12d.compare_production_inventory(before, after)

    assert comparison["identical"] is False
    assert comparison["blocking_database_content_differences"] == [{
        "database": role,
        "layer": "logical_fingerprints",
        "added": [],
        "removed": [],
        "changed": ["guarded"],
    }]


def test_production_comparison_rejects_same_row_count_status_and_reason_mutation(
    tmp_path: Path,
) -> None:
    before, after = _logical_guard_inventories(
        tmp_path,
        "analysis",
        "UPDATE guarded SET status='REVIEW', reason='STRUCTURAL_REVIEW' WHERE id=2",
    )
    comparison = phase12d.compare_production_inventory(before, after)

    assert comparison["identical"] is False
    assert {
        "database": "analysis",
        "layer": "logical_fingerprints",
        "added": [],
        "removed": [],
        "changed": ["guarded"],
    } in comparison["blocking_database_content_differences"]


def test_production_comparison_rejects_structural_value_mutation(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE structural_regime("
            "security_id INTEGER PRIMARY KEY, structural_regime TEXT, reason TEXT)"
        )
        connection.execute(
            "INSERT INTO structural_regime VALUES(1,'POST_EVENT_CLEAN','ACCEPTED')"
        )
    before = _inventory_wrapper("analysis", db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE structural_regime SET structural_regime='COMPARABILITY_REVIEW' "
            "WHERE security_id=1"
        )
    after = _inventory_wrapper("analysis", db)
    comparison = phase12d.compare_production_inventory(before, after)

    assert comparison["identical"] is False
    assert {
        "database": "analysis",
        "layer": "logical_fingerprints",
        "added": [],
        "removed": [],
        "changed": ["structural_regime"],
    } in comparison["blocking_database_content_differences"]


def test_production_comparison_rejects_row_addition_and_removal(tmp_path: Path) -> None:
    db = tmp_path / "provider.db"
    _logical_guard_db(db)
    before = _inventory_wrapper("provider", db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO guarded(id,amount,status,reason,payload) "
            "VALUES(3,1.0,'READY','NEW',X'03')"
        )
    after_add = _inventory_wrapper("provider", db)
    add_comparison = phase12d.compare_production_inventory(before, after_add)

    assert add_comparison["identical"] is False
    assert {
        "database": "provider",
        "layer": "row_counts",
        "added": [],
        "removed": [],
        "changed": ["guarded"],
    } in add_comparison["blocking_database_content_differences"]

    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM guarded WHERE id=2")
    after_remove = _inventory_wrapper("provider", db)
    remove_comparison = phase12d.compare_production_inventory(after_add, after_remove)

    assert remove_comparison["identical"] is False
    assert {
        "database": "provider",
        "layer": "row_counts",
        "added": [],
        "removed": [],
        "changed": ["guarded"],
    } in remove_comparison["blocking_database_content_differences"]


def test_production_comparison_rejects_active_identity_changes() -> None:
    before = {
        "databases": {},
        "reports": {},
        "active_package": {"persistence_fingerprint": "package-a"},
        "active_relative_valuation": [{"snapshot_id": "rv-a"}],
    }
    after = json.loads(json.dumps(before))
    after["active_package"]["persistence_fingerprint"] = "package-b"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False

    after = json.loads(json.dumps(before))
    after["active_relative_valuation"][0]["snapshot_id"] = "rv-b"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False


def test_production_comparison_rejects_dependency_fingerprint_changes() -> None:
    before = {
        "databases": {
            "analysis": {
                "sha256": "database",
                "size": 100,
                "mtime_ns": 1,
                "schema_fingerprint": "schema",
                "page_count": 10,
                "freelist_count": 0,
                "row_counts": {"relative_valuation_snapshot_dependency": 1},
                "quick_check": "ok",
                "foreign_key_errors": 0,
                "wal": {"exists": False, "size": None, "mtime_ns": None, "sha256": None},
                "shm": {"exists": False, "size": None, "mtime_ns": None, "sha256": None},
            }
        },
        "reports": {},
        "active_relative_valuation": [{
            "snapshot_id": "rv",
            "taxonomy_economic_fingerprint": "taxonomy-a",
        }],
    }
    after = json.loads(json.dumps(before))
    after["active_relative_valuation"][0]["taxonomy_economic_fingerprint"] = "taxonomy-b"

    assert phase12d.compare_production_inventory(before, after)["identical"] is False


def test_production_comparison_allows_scheduler_mtime_only() -> None:
    before = {
        "databases": {},
        "reports": {},
        "scheduler": {"exists": True, "sha256": "scheduler", "size": 10, "mtime_ns": 1},
    }
    after = json.loads(json.dumps(before))
    after["scheduler"]["mtime_ns"] = 2
    assert phase12d.compare_production_inventory(before, after)["identical"] is True

    after["scheduler"]["sha256"] = "changed"
    assert phase12d.compare_production_inventory(before, after)["identical"] is False
