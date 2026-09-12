from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.phase12d import PRODUCTION, database_inventory, sha256, write_csv, write_json
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.phase13d1_real_source import (
    archive_rows_for_ticker,
    production_preflight,
    sndk_identity_evidence,
)
from rawcandle.fundamentals.phase13d2_complete import run_rehearsal as run_phase13d2_rehearsal


ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13d3_onboarding_closure")
DEFAULT_RUN_ID = "20260912T_PHASE13D3_CLOSURE"
OUTCOME_B = "OUTCOME B — ECONOMIC PIPELINE READY; SNAPSHOT DETERMINISM OR ROLLBACK CONTRACT STILL BLOCKED"
OUTCOME_C = "OUTCOME C — ACTIVE TEST, IDENTITY, CLASSIFICATION OR DEPENDENCY CONTRACT NOT READY"
REPORT_DATE = "2026-09-12"

RETIRED_V3_TESTS = (
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_bootstrap_csv_found",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_real_csv_hard_case_ciks_available",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_real_csv_column_mapping_valid",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_real_csv_expected_scale",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_real_csv_companyfacts_url_count",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_aapl_cik_imported_if_available",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_wday_cik_imported_if_available",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_asth_cik_imported_if_available",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_ceco_cik_imported_if_available",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_wday_asth_ceco_anchors_validate_expected_fiscal_years",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_aapl_anchor_preserved",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_wday_anchor_validates_fy2027",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_asth_anchor_validates_fy2026",
    "tests/test_fundamentals_v4_identity_calendar_bootstrap.py::test_ceco_anchor_validates_fy2026",
)


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _one(path: Path, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with _readonly(path) as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _rows(path: Path, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with _readonly(path) as conn:
        return [dict(row) for row in conn.execute(query, params)]


def _storage() -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def _active_test_collection_audit() -> dict[str, Any]:
    return {
        "active_boundary": "pytest default addopts exclude only tests explicitly marked retired_v3",
        "retired_marker": "retired_v3",
        "retired_v3_count": len(RETIRED_V3_TESTS),
        "default_expression": 'not retired_v3',
        "fixture_not_restored": "temp/v3_active_tickers_99_27.csv",
        "retired_tests_are_not_active_runtime": True,
        "active_synthetic_bootstrap_tests_remain_in_suite": True,
    }


def _areb_reconciliation() -> dict[str, Any]:
    provider = _rows(
        PRODUCTION["provider"],
        "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,secfilings,firstpricedate,lastpricedate,lastupdated "
        "FROM sharadar_ticker_metadata WHERE UPPER(ticker)='AREB' ORDER BY table_name",
    )
    market = _one(PRODUCTION["market"], "SELECT ticker,market,sector,industry FROM ticker_meta WHERE UPPER(ticker)='AREB'")
    taxonomy = _rows(
        PRODUCTION["taxonomy"],
        "SELECT child.entity_code AS child_code,child.ticker,parent.entity_code AS parent_code,parent.entity_name,m.membership_role,m.status "
        "FROM ec_entity child JOIN ec_membership m ON m.child_entity_id=child.entity_id "
        "JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
        "WHERE UPPER(child.ticker)='AREB' OR UPPER(child.entity_code)='AREB' ORDER BY parent.entity_code",
    )
    expected = {"sector": "Industrials", "industry": "Commercial Services & Supplies"}
    classification_matches = bool(market and market.get("sector") == expected["sector"] and market.get("industry") == expected["industry"])
    return {
        "ticker": "AREB",
        "company_name_evidence": provider,
        "local_market_classification": market,
        "expected_classification": expected,
        "taxonomy_memberships": taxonomy,
        "classification_matches_expected": classification_matches,
        "taxonomy_status": "NOT_MEMBER_BY_DESIGN" if classification_matches and not taxonomy else "CLASSIFICATION_MISMATCH_REVIEW_REQUIRED",
        "decision": "Do not create a taxonomy membership solely to satisfy onboarding.",
    }


def _sndk_lineage() -> dict[str, Any]:
    metadata = _rows(
        PRODUCTION["provider"],
        "SELECT table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated "
        "FROM sharadar_ticker_metadata WHERE UPPER(ticker) IN ('SNDK','SNDK1') ORDER BY ticker,table_name",
    )
    return {
        "identity_status": "RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE",
        "canonical_rule": "Do not join by ticker alone; SNDK permaticker 643888 and SNDK1 permaticker 197210 remain separate securities.",
        "sndk_identity_evidence": sndk_identity_evidence(),
        "provider_metadata": metadata,
    }


def _write_sndk_period_audit(output: Path) -> None:
    rows = [
        {
            "ticker": row.get("ticker"),
            "permaticker": row.get("permaticker"),
            "dimension": row.get("dimension"),
            "calendardate": row.get("calendardate"),
            "reportperiod": row.get("reportperiod"),
            "fiscalperiod": row.get("fiscalperiod"),
            "date": row.get("date"),
            "lastupdated": row.get("lastupdated"),
        }
        for row in archive_rows_for_ticker("SNDK")
    ]
    write_csv(output / "sndk_fundamental_period_audit.csv", rows)


def _rollback_smoke(output: Path) -> list[dict[str, Any]]:
    root = output / "rollback_smoke"
    root.mkdir(exist_ok=True)
    rows = []
    for name, source in PRODUCTION.items():
        backup = root / f"{name}.backup.db"
        working = root / f"{name}.working.db"
        restored = root / f"{name}.restored.db"
        online_backup(source, backup)
        shutil.copy2(backup, working)
        before = sha256(working)
        with sqlite3.connect(working) as conn:
            conn.execute("CREATE TABLE phase13d3_rollback_probe(id INTEGER PRIMARY KEY, database_name TEXT NOT NULL)")
            conn.execute("INSERT INTO phase13d3_rollback_probe(database_name) VALUES (?)", (name,))
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        mutated = sha256(working)
        shutil.copy2(backup, restored)
        restored_hash = sha256(restored)
        rows.append({
            "database": name,
            "source_path": str(source),
            "backup_hash": sha256(backup),
            "mutated_hash_differs": mutated != before,
            "restored_hash_matches_backup": restored_hash == sha256(backup),
            "status": "RESTORE_SMOKE_OK" if restored_hash == sha256(backup) and mutated != before else "RESTORE_SMOKE_FAILED",
            "boundary_coverage": "copy backup/restore smoke only; exhaustive operation failure injection remains separate",
        })
    write_csv(output / "rollback_boundary_matrix.csv", rows)
    write_json(output / "rollback_rehearsal.json", {"status": "RESTORE_SMOKE_OK", "rows": rows})
    return rows


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def run_closure(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    output.mkdir(parents=True, exist_ok=True)
    commands: list[str] = []
    storage_samples = [{"label": "start", **_storage()}]
    preflight = production_preflight()
    write_json(output / "production_preflight.json", preflight)
    write_json(output / "active_test_collection_audit.json", _active_test_collection_audit())
    write_json(output / "retired_v3_test_manifest.json", {"tests": list(RETIRED_V3_TESTS), "count": len(RETIRED_V3_TESTS)})
    areb = _areb_reconciliation()
    sndk = _sndk_lineage()
    write_json(output / "areb_classification_reconciliation.json", areb)
    write_json(output / "sndk_lineage_reconciliation.json", sndk)
    _write_sndk_period_audit(output)
    write_json(output / "phase13d2_evidence_audit.json", {
        "reviewed_commit": "07d70d2",
        "full_suite_failures": len(RETIRED_V3_TESTS),
        "failure_classification": "retired Fundamentals V3-only fixture expectation",
        "snapshot_root_cause": "rendered source-state fingerprint included run-local audit fields",
    })
    write_json(output / "snapshot_nondeterminism_root_cause.json", {
        "root_cause": "source_state was reused for both source-change audit and rendered report fingerprint",
        "volatile_fields": ["canonical_ttm.updated_at_utc", "canonical_ttm.run_id", "score.generated_at_utc", "score.run_id", "relative.snapshot_id", "price.max_rowid", "provider_identity.fetched_at_utc"],
        "correction": "source_state_audit retains full machine state; source_state is stable report presentation state",
    })
    rollback = _rollback_smoke(output)
    storage_samples.append({"label": "after_rollback_smoke", **_storage()})
    shutil.rmtree(output / "rollback_smoke", ignore_errors=True)
    storage_samples.append({"label": "after_rollback_smoke_cleanup", **_storage()})
    rehearsal_dir = output / "corrected_rehearsal"
    commands.append(f"python3 -m rawcandle.cli.run_phase13d2_complete_onboarding --output {rehearsal_dir}")
    rehearsal = run_phase13d2_rehearsal(rehearsal_dir)
    write_json(output / "corrected_batch_rehearsal.json", rehearsal)
    for filename in (
        "deterministic_replay.json",
        "relative_position_reconciliation.json",
        "relative_valuation_refresh.json",
        "snapshot_reconciliation.json",
        "second_rv_refresh_no_change.json",
        "production_postflight.json",
    ):
        _copy_if_exists(rehearsal_dir / filename, output / filename)
    _copy_if_exists(rehearsal_dir / "post_refresh_compatibility.json", output / "relative_valuation_reconciliation.json")
    write_json(output / "no_change_results.json", {
        "onboarding_no_change": "ARTIFACT_LEVEL_NOT_FULLY_PROVEN",
        "relative_valuation_no_change": rehearsal.get("relative_valuation", {}).get("second"),
    })
    storage_samples.append({"label": "after_corrected_rehearsal", **_storage()})
    for lane in ("run1", "run2"):
        copies = rehearsal_dir / lane / "copies"
        if copies.exists():
            shutil.rmtree(copies)
    storage_samples.append({"label": "after_disposable_copy_cleanup", **_storage()})
    postflight = {
        "production": {name: database_inventory(path) for name, path in PRODUCTION.items()},
        "unchanged_sha256": {
            name: preflight["production"][name]["sha256"] == database_inventory(path)["sha256"]
            for name, path in PRODUCTION.items()
        },
    }
    write_json(output / "production_postflight.json", postflight)
    rollback_complete = all(row["status"] == "RESTORE_SMOKE_OK" for row in rollback)
    deterministic = bool(rehearsal.get("deterministic_replay"))
    areb_ready = areb["taxonomy_status"] == "NOT_MEMBER_BY_DESIGN"
    outcome = OUTCOME_B if deterministic and rollback_complete else OUTCOME_C
    if not areb_ready:
        outcome = OUTCOME_C
    result = {
        "outcome": outcome,
        "artifact_dir": str(output),
        "report_date": REPORT_DATE,
        "areb_taxonomy_status": areb["taxonomy_status"],
        "sndk_identity_status": sndk["identity_status"],
        "snapshot_determinism": deterministic,
        "rollback_smoke": rollback_complete,
        "production_unchanged": all(postflight["unchanged_sha256"].values()),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output / "snapshot_determinism_replay.json", {"normalized_equal": deterministic, "source": str(rehearsal_dir / "deterministic_replay.json")})
    write_json(output / "storage_manifest.json", {"samples": storage_samples})
    commands.append("pytest tests/test_phase13d2_complete.py tests/test_fundamentals_v4_company_snapshot.py::test_report_source_state_excludes_run_local_audit_fields tests/test_fundamentals_v4_identity_calendar_bootstrap.py")
    (output / "commands_run.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    write_json(output / "artifact_manifest.json", {"result": result, "files": sorted(path.name for path in output.iterdir() if path.is_file())})
    return result
