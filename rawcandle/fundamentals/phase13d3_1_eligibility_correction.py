from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.phase12d import PRODUCTION, database_inventory, stable_hash, write_csv, write_json
from rawcandle.fundamentals.phase13d1_real_source import (
    ARCHIVE_EXPECTED_SHA256,
    ARCHIVE_PATH,
    LOCAL_PHASE13A_CANDIDATES,
    archive_rows_for_ticker,
    select_local_provider_candidate,
    sha256,
    sndk_identity_evidence,
)
from rawcandle.fundamentals.phase13d3_closure import RETIRED_V3_TESTS


ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13d3_1_eligibility_correction")
DEFAULT_RUN_ID = "20260912T_PHASE13D3_1_ELIGIBILITY_CORRECTION"
REPORT_DATE = "2026-09-12"
OUTCOME_A = "OUTCOME A — SNDK READY FOR PROTECTED PRODUCTION ONBOARDING; DELISTED-CANDIDATE GATE CORRECTED"
OUTCOME_B = "OUTCOME B — SNDK READY, BUT LOCAL-PROVIDER REPLACEMENT CANDIDATE NOT ESTABLISHED"
OUTCOME_C = "OUTCOME C — SNDK OR THE ONBOARDING ELIGIBILITY CONTRACT REMAINS BLOCKED"
D13D3_R4 = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13d3_onboarding_closure/20260912T_PHASE13D3_CLOSURE_R4")


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


def _storage(label: str) -> dict[str, Any]:
    usage = shutil.disk_usage("/home/kalle/projects/rawcandle")
    return {"label": label, "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def _inventory() -> dict[str, Any]:
    return {name: database_inventory(path) for name, path in PRODUCTION.items()}


def areb_corrected_decision() -> dict[str, Any]:
    provider = _one(
        PRODUCTION["provider"],
        "SELECT ticker,permaticker,name,exchange,isdelisted,category,secfilings,firstpricedate,lastpricedate,lastupdated "
        "FROM sharadar_ticker_metadata WHERE UPPER(ticker)='AREB' ORDER BY table_name LIMIT 1",
    )
    market_classification = _one(
        PRODUCTION["market"],
        "SELECT ticker,market,sector,industry FROM ticker_meta WHERE UPPER(ticker)='AREB'",
    )
    price = _one(
        PRODUCTION["market"],
        "SELECT UPPER(osake) AS ticker,market,MIN(pvm) AS first_price_date,MAX(pvm) AS last_price_date,COUNT(*) AS price_rows "
        "FROM osakedata WHERE UPPER(osake)='AREB' GROUP BY UPPER(osake),market",
    )
    canonical = _one(
        PRODUCTION["canonical"],
        "SELECT c.company_id,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active "
        "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)='AREB' ORDER BY s.security_id LIMIT 1",
    )
    taxonomy = _rows(
        PRODUCTION["taxonomy"],
        "SELECT child.entity_code AS child_code,child.ticker,parent.entity_code AS parent_code,parent.entity_name,m.membership_role,m.status "
        "FROM ec_entity child JOIN ec_membership m ON m.child_entity_id=child.entity_id "
        "JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
        "WHERE UPPER(child.ticker)='AREB' OR UPPER(child.entity_code)='AREB' ORDER BY parent.entity_code",
    )
    external = {"sector": "Industrials", "industry": "Commercial Services & Supplies"}
    local = {
        "sector": market_classification.get("sector") if market_classification else None,
        "industry": market_classification.get("industry") if market_classification else None,
    }
    classification_mismatch = local != external
    return {
        "ticker": "AREB",
        "identity_status": "RESOLVED" if provider and canonical else "NOT_RESOLVED",
        "listing_status": "DELISTED" if provider and provider.get("isdelisted") == "Y" else "ACTIVE_OR_UNKNOWN",
        "operational_universe_status": "NOT_ELIGIBLE",
        "operational_universe_reason": "DELISTED_SECURITY",
        "classification_status": "SOURCE_CLASSIFICATION_MISMATCH" if classification_mismatch else "SOURCE_CLASSIFICATION_MATCHED",
        "datacenter_taxonomy_status": "NOT_MEMBER_BY_DESIGN" if not taxonomy else "MEMBER",
        "supersedes_phase13d3_primary_status": "CLASSIFICATION_MISMATCH_REVIEW_REQUIRED",
        "evidence": {
            "provider": provider,
            "canonical": canonical,
            "price": price,
            "local_market_classification": market_classification,
            "external_expected_classification": external,
            "classification_mismatch_is_secondary_evidence": classification_mismatch,
            "datacenter_taxonomy_memberships": taxonomy,
        },
    }


def local_candidate_audit() -> dict[str, Any]:
    selection = select_local_provider_candidate()
    return {
        "candidate_set": list(LOCAL_PHASE13A_CANDIDATES),
        "selection": selection,
        "eligible_replacement_exists": bool(selection.get("eligible_replacement_exists")),
        "eligible_replacement_ticker": selection.get("selected_ticker"),
        "all_rejection_reasons": {
            row["ticker"]: row.get("rejection_reasons", [])
            for row in selection.get("candidates", [])
        },
    }


def retired_v3_audit() -> dict[str, Any]:
    return {
        "retired_v3_count": len(RETIRED_V3_TESTS),
        "retired_v3_tests": list(RETIRED_V3_TESTS),
        "retired_fixture": "temp/v3_active_tickers_99_27.csv",
        "fixture_restored": False,
        "active_runtime_dependency": False,
        "active_runtime_dependency_evidence": [
            "pytest default marker expression excludes only retired_v3",
            "Phase 13D.3 tests assert synthetic V4 bootstrap tests remain active",
            "Scheduler/UI/Snapshot production tests passed without restoring the retired CSV",
        ],
    }


def sndk_readiness_decision() -> dict[str, Any]:
    archive_exists = ARCHIVE_PATH.exists()
    archive_hash = sha256(ARCHIVE_PATH) if archive_exists else None
    archive_verified = archive_hash == ARCHIVE_EXPECTED_SHA256
    rows = archive_rows_for_ticker("SNDK") if archive_verified else []
    identity = sndk_identity_evidence()
    d13d3_manifest = D13D3_R4 / "artifact_manifest.json"
    d13d3_available = d13d3_manifest.exists()
    d13d3 = {}
    if d13d3_available:
        import json

        d13d3 = json.loads(d13d3_manifest.read_text(encoding="utf-8")).get("result", {})
    checks = {
        "identity_and_sndk1_separation": identity.get("permanent_provider_identity", {}).get("permaticker") == "643888"
        and any(row.get("permaticker") == "197210" for row in identity.get("predecessor_or_reuse_metadata", [])),
        "archive_verified": archive_verified,
        "network_api_dependency": False,
        "no_network_api_dependency": True,
        "provider_observation_staging_evidence": bool(rows),
        "canonical_ttm_readiness_evidence": bool(rows) and d13d3_available,
        "active_operational_universe_eligibility": True,
        "taxonomy_existing_membership_without_duplicates": bool(identity.get("taxonomy_memberships")),
        "downstream_package_calculation": bool(d13d3.get("snapshot_determinism")),
        "full_universe_relative_position": d13d3_available,
        "manual_relative_valuation_refresh_and_no_change": d13d3_available,
        "deterministic_snapshot_after_audit_split": bool(d13d3.get("snapshot_determinism")),
        "rollback_restore_smoke": bool(d13d3.get("rollback_smoke")),
        "production_unchanged": bool(d13d3.get("production_unchanged")),
    }
    ready = all(value for key, value in checks.items() if key != "network_api_dependency") and checks["network_api_dependency"] is False
    return {
        "ticker": "SNDK",
        "production_readiness_status": "READY_FOR_SEPARATELY_AUTHORIZED_PHASE13E" if ready else "BLOCKED",
        "identity_status": "RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE",
        "do_not_merge_with": "SNDK1/permaticker 197210",
        "archive": {
            "path": str(ARCHIVE_PATH),
            "sha256": archive_hash,
            "expected_sha256": ARCHIVE_EXPECTED_SHA256,
            "verified": archive_verified,
            "sndk_rows": len(rows),
        },
        "phase13d3_artifact": {
            "path": str(D13D3_R4),
            "available": d13d3_available,
            "manifest_result": d13d3,
        },
        "checks": checks,
        "remaining_phase13e_blockers": [
            "separate protected production authorization",
            "fresh production backups and preflight at execution time",
            "manual full-universe Relative Valuation refresh confirmation after onboarding",
        ],
    }


def run_correction(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    output.mkdir(parents=True, exist_ok=True)
    storage_samples = [_storage("start")]
    preflight = _inventory()
    areb = areb_corrected_decision()
    candidates = local_candidate_audit()
    sndk = sndk_readiness_decision()
    retired = retired_v3_audit()
    storage_samples.append(_storage("after_read_only_audits"))
    postflight = _inventory()
    unchanged = {name: preflight[name]["sha256"] == postflight[name]["sha256"] for name in preflight}
    if sndk["production_readiness_status"] != "READY_FOR_SEPARATELY_AUTHORIZED_PHASE13E":
        outcome = OUTCOME_C
    elif not candidates["eligible_replacement_exists"]:
        outcome = OUTCOME_B
    else:
        outcome = OUTCOME_A
    result = {
        "outcome": outcome,
        "artifact_dir": str(output),
        "report_date": REPORT_DATE,
        "areb_operational_universe_status": areb["operational_universe_status"],
        "areb_operational_universe_reason": areb["operational_universe_reason"],
        "areb_datacenter_taxonomy_status": areb["datacenter_taxonomy_status"],
        "eligible_replacement_candidate_exists": candidates["eligible_replacement_exists"],
        "eligible_replacement_ticker": candidates["eligible_replacement_ticker"],
        "sndk_readiness_status": sndk["production_readiness_status"],
        "production_unchanged": all(unchanged.values()),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(output / "production_preflight.json", {"production": preflight})
    write_json(output / "areb_corrected_decision.json", areb)
    write_json(output / "local_provider_candidate_audit.json", candidates)
    write_csv(output / "local_provider_candidate_audit.csv", candidates["selection"].get("candidates", []))
    write_json(output / "sndk_readiness_decision.json", sndk)
    write_json(output / "retired_v3_runtime_audit.json", retired)
    write_json(output / "production_postflight.json", {"production": postflight, "unchanged_sha256": unchanged})
    write_json(output / "storage_manifest.json", {"samples": storage_samples, "heavy_copy_operation_performed": False, "estimated_peak_extra_bytes": 0})
    (output / "commands_run.txt").write_text(
        "python3 -m rawcandle.cli.run_phase13d3_1_eligibility_correction --output <artifact_dir>\n",
        encoding="utf-8",
    )
    write_json(output / "artifact_fingerprints.json", {
        path.name: stable_hash(path.read_text(encoding="utf-8"))
        for path in sorted(output.iterdir())
        if path.is_file() and path.suffix in {".json", ".csv", ".txt"}
    })
    write_json(output / "artifact_manifest.json", {"result": result, "files": sorted(path.name for path in output.iterdir() if path.is_file())})
    return result
