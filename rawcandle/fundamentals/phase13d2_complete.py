from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2.pipeline import refresh_active_package
from rawcandle.fundamentals.phase12d import PRODUCTION, database_inventory, rebuild_ttm, reconcile_canonical, write_csv, write_json
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13d1_real_source import (
    ARCHIVE_EXPECTED_SHA256,
    ARCHIVE_PATH,
    OUTCOME_BLOCKED as OUTCOME_D1_BLOCKED,
    RehearsalCopies,
    archive_rows_for_ticker,
    connect_sndk_taxonomy_identity,
    create_sndk_canonical_identity,
    production_preflight,
    select_local_provider_candidate,
    sha256,
    sndk_identity_evidence,
    stage_sndk_archive_rows,
)
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.engine import calculate_relative_valuation
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT as RV_LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION as RV_PERSISTENCE_VERSION,
    RelativeValuationRepository,
    apply_snapshot,
    quick_check as rv_quick_check,
    validate_snapshot,
)
from rawcandle.fundamentals.relative_valuation.source import ReadOnlySourcePaths, load_relative_valuation_source
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths


PHASE = "PHASE13D2_COMPLETE_REAL_SOURCE_ONBOARDING_REHEARSAL"
OUTCOME_B = "OUTCOME B — ECONOMIC REBUILD COMPLETE; RELATIVE VALUATION, REPORTING OR ROLLBACK CONTRACT STILL BLOCKED"
OUTCOME_C = "OUTCOME C — REAL-SOURCE ONBOARDING OR COHERENT DOWNSTREAM REBUILD NOT READY"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13d2_complete_onboarding")
REPORT_DATE = "2026-09-12"
APPLIED_AT = "2026-09-12T00:00:00Z"
TICKERS = ("AREB", "SNDK")


def resolve_output(output: Path | None) -> Path:
    return (output or ARTIFACT_ROOT / "20260912T_PHASE13D2_COMPLETE").resolve()


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def create_rehearsal_copies(output: Path, lane: str) -> RehearsalCopies:
    copies = output / lane / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    destinations = {
        "provider": copies / "fundamentals_provider.db",
        "canonical": copies / "fundamentals_v4.db",
        "analysis": copies / "fundamentals_analysis.db",
        "market": copies / "osakedata.db",
        "taxonomy": copies / "analysis.db",
    }
    for name, source in PRODUCTION.items():
        online_backup(source, destinations[name])
    return RehearsalCopies(
        root=copies,
        provider=destinations["provider"],
        canonical=destinations["canonical"],
        analysis=destinations["analysis"],
        market=destinations["market"],
        taxonomy=destinations["taxonomy"],
    )


def _company_security(canonical_db: Path, ticker: str) -> dict[str, Any] | None:
    with readonly(canonical_db) as conn:
        row = conn.execute(
            "SELECT c.company_id,c.company_key,c.company_name,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) WHERE UPPER(s.current_ticker)=UPPER(?)",
            (ticker,),
        ).fetchone()
    return dict(row) if row else None


def _readiness(copies: RehearsalCopies, ticker: str) -> dict[str, Any]:
    identity = _company_security(copies.canonical, ticker)
    if identity is None:
        return {
            "ticker": ticker,
            "identity_status": "NOT_RESOLVED",
            "fundamentals_status": "NOT_READY",
            "operational_universe_status": "NOT_PRESENT",
            "taxonomy_status": "TAXONOMY_REVIEW_REQUIRED",
            "downstream_status": "NOT_READY",
            "relative_valuation_status": "NOT_EVALUATED",
        }
    company_id = int(identity["company_id"])
    with readonly(copies.provider) as provider, readonly(copies.canonical) as canonical, readonly(copies.analysis) as analysis, readonly(copies.taxonomy) as taxonomy:
        provider_arq = int(provider.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?) AND dimension='ARQ'",
            (ticker,),
        ).fetchone()[0])
        provider_mrq = int(provider.execute(
            "SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE UPPER(ticker)=UPPER(?) AND dimension='MRQ'",
            (ticker,),
        ).fetchone()[0])
        quarters = int(canonical.execute("SELECT COUNT(*) FROM v4_quarter WHERE company_id=?", (company_id,)).fetchone()[0])
        ttm = int(canonical.execute("SELECT COUNT(*) FROM v4_ttm_values WHERE company_id=?", (company_id,)).fetchone()[0])
        ttm_ready = int(canonical.execute(
            "SELECT COUNT(*) FROM v4_ttm_values WHERE company_id=? AND readiness_status='READY'",
            (company_id,),
        ).fetchone()[0])
        universe = canonical.execute(
            "SELECT membership_status,identity_resolution_status FROM fundamentals_operational_universe_member m "
            "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) WHERE m.company_id=?",
            (company_id,),
        ).fetchone()
        taxonomy_rows = [dict(row) for row in taxonomy.execute(
            "SELECT parent.entity_code,parent.entity_name,m.membership_role,m.is_primary,m.status "
            "FROM ec_entity child JOIN ec_membership m ON m.child_entity_id=child.entity_id "
            "JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id "
            "WHERE UPPER(child.ticker)=UPPER(?) OR UPPER(child.entity_code)=UPPER(?) ORDER BY parent.entity_code,m.membership_id",
            (ticker, ticker),
        )]
        score = analysis.execute(
            "SELECT readiness_status FROM score_result WHERE company_id=? ORDER BY quarter_id DESC, score_result_id DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        lifecycle = analysis.execute(
            "SELECT lifecycle_status FROM lifecycle_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        valuation = analysis.execute(
            "SELECT valuation_status FROM valuation_revised_result WHERE company_id=? ORDER BY fiscal_sequence DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        delta = analysis.execute(
            "SELECT sq.status_text,s2.status_text,sy.status_text FROM fundamental_delta_result r "
            "JOIN fundamental_delta_status sq ON sq.status_id=r.qoq_status_id "
            "JOIN fundamental_delta_status s2 ON s2.status_id=r.two_quarter_status_id "
            "JOIN fundamental_delta_status sy ON sy.status_id=r.yoy_status_id "
            "WHERE r.company_id=? ORDER BY r.fiscal_sequence DESC LIMIT 1",
            (company_id,),
        ).fetchone()
        diagnostics = [str(row[0]) for row in analysis.execute(
            "SELECT source.source_status_text FROM diagnostic_flag_endpoint e "
            "LEFT JOIN diagnostic_flag_source_status source ON source.source_status_id=e.source_status_id "
            "WHERE e.company_id=? ORDER BY e.fiscal_sequence DESC LIMIT 8",
            (company_id,),
        )]
        rp = analysis.execute(
            "SELECT COUNT(*) FROM relative_position_result r JOIN relative_position_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
            (company_id,),
        ).fetchone()[0]
        rv = analysis.execute(
            "SELECT COUNT(*) FROM relative_valuation_company_result r JOIN relative_valuation_active_snapshot a USING(snapshot_id) WHERE r.company_id=?",
            (company_id,),
        ).fetchone()[0]
    taxonomy_status = "CONNECTED_EXISTING_MEMBERSHIP" if taxonomy_rows else "TAXONOMY_REVIEW_REQUIRED"
    downstream_ready = all((score, lifecycle, valuation, delta)) and rp > 0
    return {
        "ticker": ticker,
        "company_id": company_id,
        "security_id": identity["security_id"],
        "identity_status": "RESOLVED_WITH_PREDECESSOR_RISK" if ticker == "SNDK" else "CANONICAL_HISTORICAL_SECURITY",
        "fundamentals_status": "READY" if quarters and ttm else "NOT_READY",
        "provider_arq_observations": provider_arq,
        "provider_mrq_observations": provider_mrq,
        "canonical_quarters": quarters,
        "ttm_endpoints": ttm,
        "ttm_core_ready_rows": ttm_ready,
        "operational_universe_status": str(universe["membership_status"]) if universe else "NOT_PRESENT",
        "operational_identity_status": str(universe["identity_resolution_status"]) if universe else "NOT_PRESENT",
        "taxonomy_status": taxonomy_status,
        "taxonomy_groups": "; ".join(f"{row['entity_code']}:{row['membership_role']}" for row in taxonomy_rows),
        "score_status": str(score[0]) if score else "NOT_READY",
        "lifecycle_status": str(lifecycle[0]) if lifecycle else "NOT_READY",
        "valuation_status": str(valuation[0]) if valuation else "NOT_READY",
        "delta_status": "/".join(str(value) for value in delta) if delta else "NOT_READY",
        "diagnostic_statuses": ";".join(diagnostics) if diagnostics else "NOT_READY",
        "relative_position_status": "READY" if rp else "NOT_READY",
        "relative_valuation_status": "READY" if rv else "NOT_READY",
        "downstream_status": "READY" if downstream_ready else "ADDED_WITH_LIMITATIONS",
    }


def _ttm_chain_rows(copies: RehearsalCopies, ticker: str) -> list[dict[str, Any]]:
    identity = _company_security(copies.canonical, ticker)
    if not identity:
        return []
    with readonly(copies.canonical) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT ? AS ticker,endpoint_fiscal_year,endpoint_fiscal_quarter,period_end,ttm_source_available_date,"
            "readiness_status,blocker_codes_json,operating_income_4q_ready,free_cashflow_4q_ready,net_income_common_4q_ready "
            "FROM v4_ttm_values WHERE company_id=? ORDER BY endpoint_fiscal_year,endpoint_fiscal_quarter",
            (ticker, int(identity["company_id"])),
        )]


def _manual_rv_refresh(copies: RehearsalCopies, *, output: Path, as_of_date: str = REPORT_DATE) -> dict[str, Any]:
    source = load_relative_valuation_source(
        ReadOnlySourcePaths(copies.analysis, copies.canonical, copies.market, copies.taxonomy),
        as_of_date=as_of_date,
    )
    snapshot = calculate_relative_valuation(
        source.inputs,
        as_of_date=as_of_date,
        classification_fingerprint=source.classification_fingerprint,
        taxonomy_fingerprint=source.taxonomy_fingerprint,
    )
    content, physical = validate_snapshot(snapshot, source.inputs)
    with sqlite3.connect(copies.analysis) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        first = apply_snapshot(conn, snapshot, source.inputs, applied_at_utc=APPLIED_AT)
        check = rv_quick_check(conn)
        second_before = database_inventory(copies.analysis)
        second = apply_snapshot(conn, snapshot, source.inputs, applied_at_utc=APPLIED_AT)
        second_after = database_inventory(copies.analysis)
        repo = RelativeValuationRepository(conn)
        active = repo.active_metadata(model_fingerprint=RV_MODEL_FINGERPRINT)
    result = {
        "source_metadata": source.metadata,
        "snapshot": {
            "snapshot_id": first.snapshot_id,
            "as_of_date": as_of_date,
            "source_fingerprint": snapshot.source_fingerprint,
            "result_fingerprint": snapshot.result_fingerprint,
            "physical_content_fingerprint": physical,
            "company_count": len(content["companies"]),
            "peer_rows": len(content["peers"]),
            "own_history_rows": len(content["own_history"]),
            "component_rows": len(content["components"]),
        },
        "first_apply": asdict(first),
        "quick_check": check,
        "active_metadata": active,
        "second_apply": asdict(second),
        "second_physical_no_change": second_before == second_after,
    }
    write_json(output / "relative_valuation_refresh.json", result)
    write_json(output / "second_rv_refresh_no_change.json", {"second_apply": asdict(second), "physical_no_change": result["second_physical_no_change"]})
    return result


def _snapshot_reports(copies: RehearsalCopies, *, output: Path, phase: str) -> dict[str, Any]:
    reports = output / "reports" / phase
    reports.mkdir(parents=True, exist_ok=True)
    paths = SnapshotPaths(copies.canonical, copies.analysis, copies.market, copies.taxonomy, copies.provider)
    results: dict[str, Any] = {}
    for ticker in ("SNDK", "AREB", "NVDA"):
        try:
            generated = generate_active_company_snapshot(
                paths,
                ticker=ticker,
                report_date=REPORT_DATE,
                output_dir=reports,
                overwrite=True,
            )
            text = Path(generated["output_path"]).read_text(encoding="utf-8")
            results[ticker] = {
                "status": generated["status"],
                "output_path": generated["output_path"],
                "fingerprint": generated["report_content_fingerprint"],
                "contains_sndk1": "SNDK1" in text,
                "relative_valuation_unavailable": "Relative Valuation" in text and "unavailable" in text.lower(),
            }
        except Exception as exc:
            results[ticker] = {"status": "FAILED", "error": type(exc).__name__, "reason": str(exc)}
    return results


def _run_lane(output: Path, lane: str) -> dict[str, Any]:
    started = time.perf_counter()
    lane_dir = output / lane
    lane_dir.mkdir(parents=True, exist_ok=True)
    copies = create_rehearsal_copies(output, lane)
    rows = archive_rows_for_ticker("SNDK")
    sndk_identity = create_sndk_canonical_identity(copies.canonical, now=APPLIED_AT)
    stage = stage_sndk_archive_rows(
        copies.provider,
        rows,
        company_id=int(sndk_identity["company_id"]),
        security_id=int(sndk_identity["security_id"]),
        now=APPLIED_AT,
    )
    taxonomy_sndk = connect_sndk_taxonomy_identity(
        copies.taxonomy,
        company_id=int(sndk_identity["company_id"]),
        security_id=int(sndk_identity["security_id"]),
        now=APPLIED_AT,
    )
    canonical = reconcile_canonical(copies.provider, copies.canonical, applied_at=APPLIED_AT)
    ttm = rebuild_ttm(copies.canonical, applied_at=APPLIED_AT)
    package = refresh_active_package({
        "provider": copies.provider,
        "canonical": copies.canonical,
        "analysis": copies.analysis,
        "market": copies.market,
        "taxonomy": copies.taxonomy,
    })
    paths = copies.candidate_paths()
    ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
    universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
    taxonomy = taxonomy_identity(copies.taxonomy)
    pre_refresh = candidate_relative_valuation_dependency_state(
        copies.analysis,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    pre_reports = _snapshot_reports(copies, output=lane_dir, phase="pre_refresh")
    rv = _manual_rv_refresh(copies, output=lane_dir)
    dependencies = attach_dependencies(paths, universe=universe["identity"], applied_at_utc=APPLIED_AT, apply=True)
    post_refresh = candidate_relative_valuation_dependency_state(
        copies.analysis,
        report_date=REPORT_DATE,
        expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
        expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
    )
    post_reports = _snapshot_reports(copies, output=lane_dir, phase="post_refresh")
    readiness = [_readiness(copies, ticker) for ticker in TICKERS]
    ttm_rows = [row for ticker in TICKERS for row in _ttm_chain_rows(copies, ticker)]
    write_csv(lane_dir / "readiness_matrix.csv", readiness)
    write_csv(lane_dir / "ttm_chain_audit.csv", ttm_rows)
    result = {
        "lane": lane,
        "copies": {name: str(path) for name, path in copies.__dict__.items() if isinstance(path, Path)},
        "sndk_identity": sndk_identity,
        "sndk_stage": stage,
        "taxonomy_sndk": taxonomy_sndk,
        "canonical": canonical,
        "ttm": ttm,
        "package": package,
        "universe": universe,
        "pre_refresh_compatibility": pre_refresh,
        "relative_valuation_refresh": rv,
        "dependencies": dependencies,
        "post_refresh_compatibility": post_refresh,
        "pre_reports": pre_reports,
        "post_reports": post_reports,
        "readiness": readiness,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(lane_dir / "first_apply.json", result)
    write_json(lane_dir / "pre_refresh_compatibility.json", pre_refresh)
    write_json(lane_dir / "post_refresh_compatibility.json", post_refresh)
    write_json(lane_dir / "snapshot_reconciliation.json", {"pre_refresh": pre_reports, "post_refresh": post_reports})
    write_json(lane_dir / "downstream_reconciliation.json", {"package": package, "canonical": canonical, "ttm": ttm})
    write_json(lane_dir / "relative_position_reconciliation.json", {"package_relative_position_rows": package["rows"].get("relative_result") if isinstance(package.get("rows"), Mapping) else None})
    return result


def _normalized(result: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("sndk_stage", "canonical", "ttm", "package", "pre_refresh_compatibility", "post_refresh_compatibility", "readiness")
    return {key: result.get(key) for key in keys}


def _without_keys(value: Any, keys_to_remove: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_keys(item, keys_to_remove) for key, item in value.items() if key not in keys_to_remove}
    if isinstance(value, list):
        return [_without_keys(item, keys_to_remove) for item in value]
    return value


def _deterministic_economic(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "onboarding": _without_keys(_normalized(result), {"snapshot_id"}),
        "relative_valuation": {
            "source_fingerprint": result["relative_valuation_refresh"]["snapshot"]["source_fingerprint"],
            "result_fingerprint": result["relative_valuation_refresh"]["snapshot"]["result_fingerprint"],
            "physical_content_fingerprint": result["relative_valuation_refresh"]["snapshot"]["physical_content_fingerprint"],
            "company_count": result["relative_valuation_refresh"]["snapshot"]["company_count"],
            "peer_rows": result["relative_valuation_refresh"]["snapshot"]["peer_rows"],
            "own_history_rows": result["relative_valuation_refresh"]["snapshot"]["own_history_rows"],
            "component_rows": result["relative_valuation_refresh"]["snapshot"]["component_rows"],
            "first_apply": _without_keys(result["relative_valuation_refresh"]["first_apply"], {"snapshot_id"}),
            "second_apply": _without_keys(result["relative_valuation_refresh"]["second_apply"], {"snapshot_id"}),
        },
        "snapshot_reports": {
            phase: {
                ticker: {
                    key: report.get(key)
                    for key in ("status", "fingerprint", "contains_sndk1", "relative_valuation_unavailable", "error", "reason")
                    if key in report
                }
                for ticker, report in reports.items()
            }
            for phase, reports in (("pre_refresh", result["pre_reports"]), ("post_refresh", result["post_reports"]))
        },
    }


def _diff_values(left: Any, right: Any, path: str = "$", *, limit: int = 200) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if type(left) is not type(right):
        return [{"path": path, "left": type(left).__name__, "right": type(right).__name__, "kind": "type_mismatch"}]
    if isinstance(left, Mapping):
        diffs: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right), key=str):
            if len(diffs) >= limit:
                break
            child = f"{path}.{key}"
            if key not in left:
                diffs.append({"path": child, "left": None, "right": right[key], "kind": "missing_left"})
            elif key not in right:
                diffs.append({"path": child, "left": left[key], "right": None, "kind": "missing_right"})
            else:
                diffs.extend(_diff_values(left[key], right[key], child, limit=limit - len(diffs)))
        return diffs[:limit]
    if isinstance(left, list):
        diffs = []
        if len(left) != len(right):
            diffs.append({"path": f"{path}.length", "left": len(left), "right": len(right), "kind": "length_mismatch"})
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            if len(diffs) >= limit:
                break
            diffs.extend(_diff_values(left_item, right_item, f"{path}[{index}]", limit=limit - len(diffs)))
        return diffs[:limit]
    if left != right:
        return [{"path": path, "left": left, "right": right, "kind": "value_mismatch"}]
    return []


def run_rehearsal(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    output = resolve_output(output)
    output.mkdir(parents=True, exist_ok=True)
    preflight = production_preflight()
    source_reconciliation = {
        "archive_path": str(ARCHIVE_PATH),
        "archive_sha256": sha256(ARCHIVE_PATH) if ARCHIVE_PATH.exists() else None,
        "expected_sha256": ARCHIVE_EXPECTED_SHA256,
        "archive_verified": ARCHIVE_PATH.exists() and sha256(ARCHIVE_PATH) == ARCHIVE_EXPECTED_SHA256,
        "network_requests_performed": 0,
        "sndk_archive_rows": len(archive_rows_for_ticker("SNDK")),
    }
    identity = {
        "selection": select_local_provider_candidate(),
        "sndk": sndk_identity_evidence(),
        "sndk1_policy": "SNDK1/permaticker 197210 is predecessor/reuse evidence and is not merged into SNDK/permaticker 643888",
    }
    write_json(output / "production_preflight.json", preflight)
    write_json(output / "source_reconciliation.json", source_reconciliation)
    write_json(output / "identity_reconciliation.json", identity)
    batch_preview = {
        "tickers": list(dict.fromkeys(TICKERS)),
        "duplicates_removed": 0,
        "fingerprint": __import__("rawcandle.fundamentals.phase12d", fromlist=["stable_hash"]).stable_hash({"tickers": TICKERS, "identity": identity, "source": source_reconciliation}),
        "status": "READY_WITH_LIMITATIONS",
    }
    write_json(output / "batch_preview.json", batch_preview)
    first = _run_lane(output, "run1")
    second = _run_lane(output, "run2")
    raw_run1 = _normalized(first)
    raw_run2 = _normalized(second)
    economic_run1 = _deterministic_economic(first)
    economic_run2 = _deterministic_economic(second)
    deterministic = {
        "raw_equal": raw_run1 == raw_run2,
        "raw_differences": _diff_values(raw_run1, raw_run2),
        "normalized_equal": economic_run1 == economic_run2,
        "normalized_differences": _diff_values(economic_run1, economic_run2),
        "normalization_policy": {
            "snapshot_id": "Excluded from economic replay equality only when source/result/physical fingerprints, counts, statuses and report content fingerprints match.",
        },
        "run1": economic_run1,
        "run2": economic_run2,
        "raw_run1": raw_run1,
        "raw_run2": raw_run2,
        "timestamp_and_sqlite_layout_excluded": True,
    }
    write_json(output / "deterministic_replay.json", deterministic)
    write_json(output / "taxonomy_reconciliation.json", {"sndk": first["taxonomy_sndk"], "areb": "TAXONOMY_REVIEW_REQUIRED"})
    write_json(output / "stale_preview_test.json", {"status": "NOT_FULLY_PROVEN", "reason": "Phase13D backend stale preview exists; Phase13D2 batch preview is artifact-level"})
    write_json(output / "first_apply.json", first)
    write_json(output / "readiness_matrix.json", first["readiness"])
    write_csv(output / "readiness_matrix.csv", first["readiness"])
    write_csv(output / "ttm_chain_audit.csv", [row for ticker in TICKERS for row in _ttm_chain_rows(RehearsalCopies(Path(first["copies"]["root"]), Path(first["copies"]["provider"]), Path(first["copies"]["canonical"]), Path(first["copies"]["analysis"]), Path(first["copies"]["market"]), Path(first["copies"]["taxonomy"])), ticker)])
    for filename in ("downstream_reconciliation.json", "relative_position_reconciliation.json", "pre_refresh_compatibility.json", "relative_valuation_refresh.json", "post_refresh_compatibility.json", "snapshot_reconciliation.json", "second_rv_refresh_no_change.json"):
        source = output / "run1" / filename
        if source.exists():
            (output / filename).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(output / "taxonomy_dependency_tests.json", {
        "presentation_only": "NOT_RUN_FULLY",
        "economic_change": "NOT_RUN_FULLY",
        "reason": "AREB taxonomy missing and full dependency mutation tests remain production-operation blockers",
    })
    write_json(output / "failure_injection_results.json", [{"status": "NOT_FULL_MATRIX", "reason": "copy refresh path implemented; exhaustive injection boundaries not completed"}])
    write_json(output / "rollback_rehearsal.json", {"status": "NOT_FULLY_PROVEN", "required_recovery": "full online backup restoration, not activation-only rollback"})
    write_json(output / "second_apply_no_change.json", {"status": "NOT_FULLY_PROVEN", "reason": "fresh batch no-change not applied physically"})
    postflight = {
        "production": {name: database_inventory(path) for name, path in PRODUCTION.items()},
        "unchanged_sha256": {
            name: preflight["production"][name]["sha256"] == database_inventory(path)["sha256"]
            for name, path in PRODUCTION.items()
        },
    }
    write_json(output / "production_postflight.json", postflight)
    outcome = OUTCOME_C
    if first["post_refresh_compatibility"]["state"] == "COMPATIBLE" and first["pre_refresh_compatibility"]["state"] == "OPERATIONAL_UNIVERSE_MISMATCH":
        outcome = OUTCOME_B
    result = {
        "outcome": outcome,
        "artifact_dir": str(output),
        "run1_elapsed_seconds": first["elapsed_seconds"],
        "run2_elapsed_seconds": second["elapsed_seconds"],
        "total_elapsed_seconds": round(time.perf_counter() - started, 3),
        "areb_status": next(row for row in first["readiness"] if row["ticker"] == "AREB"),
        "sndk_status": next(row for row in first["readiness"] if row["ticker"] == "SNDK"),
        "relative_valuation": {
            "pre": first["pre_refresh_compatibility"],
            "post": first["post_refresh_compatibility"],
            "refresh": first["relative_valuation_refresh"]["first_apply"],
            "second": first["relative_valuation_refresh"]["second_apply"],
        },
        "deterministic_replay": deterministic["normalized_equal"],
    }
    write_json(output / "artifact_manifest.json", {"result": result, "files": sorted(path.name for path in output.iterdir() if path.is_file())})
    (output / "commands_run.txt").write_text("python3 -m rawcandle.cli.run_phase13d2_complete_onboarding --output <artifact_dir>\n", encoding="utf-8")
    write_json(output / "artifact_manifest.json", {"result": result, "files": sorted(path.name for path in output.iterdir() if path.is_file())})
    return result
