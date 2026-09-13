from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import (
    PRODUCTION,
    compare_production_inventory,
    database_inventory,
    production_inventory,
    stable_hash,
    write_json,
)
from rawcandle.fundamentals.phase13b_foundation import (
    CandidatePaths,
    attach_dependencies,
    backfill_universe,
    candidate_relative_valuation_dependency_state,
    ensure_candidate_schema,
    online_backup,
    reject_production_path,
    taxonomy_identity,
)
from rawcandle.fundamentals.phase13f3_1_package_recovery import instrumented_package_refresh, utc_now
from rawcandle.fundamentals.phase13f3_2_successor_recovery import (
    PERMATICKERS,
    archive_reconciliation,
    stage_provider_rows,
    successor_canonical_ttm_report,
)
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    APPLIED_AT,
    REPORT_DATE,
    TRANSITIONS,
    _apply_transition_identities,
    _areb_counts,
    _manual_rv_refresh,
    _snapshot_smoke,
    _storage,
    _valuation_classification_update,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RP_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.production import refresh_relative_position


PHASE = "PHASE13F3_3_VERSIONED_ECONOMIC_STRUCTURAL_BREAK_CONTRACT"
ARTIFACT_ROOT = Path("/home/kalle/projects/rawcandle/temp/fundamentals_v4_phase13f3_3_structural_break_contract")
DEFAULT_RUN_ID = "20260913T_PHASE13F3_3_STRUCTURAL_BREAK_CONTRACT"
OUTCOME_A = "OUTCOME A — VERSIONED STRUCTURAL-BREAK CONTRACT IMPLEMENTED AND COPY-ONLY REHEARSAL VERIFIED"
OUTCOME_B = "OUTCOME B — STRUCTURAL-BREAK CONTRACT OR DOWNSTREAM CHAIN STILL BLOCKED"


def _events() -> tuple[dict[str, Any], ...]:
    enriched = []
    for transition in TRANSITIONS:
        row = dict(transition)
        row["permaticker"] = PERMATICKERS.get(str(row["current_ticker"]), "")
        enriched.append(row)
    return structural_break.default_events(enriched)


def _structural_package_fingerprint(structural: Mapping[str, Any]) -> str:
    return stable_hash({
        "base_package": "OPERATING_INCOME_V2_PARALLEL_PERSISTENCE_V2",
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_regime_fingerprint": structural["regime_fingerprint"],
    })


def _structural_evidence(canonical_db: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            f"""WITH quarter_counts AS (
                    SELECT event_id,
                           COUNT(*) quarter_rows,
                           SUM(CASE WHEN economic_regime='PRE_EVENT' THEN 1 ELSE 0 END) pre_event_quarters,
                           SUM(CASE WHEN economic_regime='UNRESOLVED' THEN 1 ELSE 0 END) unresolved_quarters
                      FROM {structural_break.QUARTER_TABLE}
                     GROUP BY event_id
                 ),
                 ttm_counts AS (
                    SELECT event_id,
                           SUM(CASE WHEN ttm_regime_status='PRE_EVENT_COHERENT' THEN 1 ELSE 0 END) pre_event_ttm,
                           SUM(CASE WHEN ttm_regime_status='POST_EVENT_COHERENT' THEN 1 ELSE 0 END) post_event_clean_ttm,
                           SUM(CASE WHEN ttm_regime_status='STRUCTURAL_NOT_READY' THEN 1 ELSE 0 END) structural_not_ready_ttm
                      FROM {structural_break.TTM_TABLE}
                     GROUP BY event_id
                 )
                SELECT e.successor_ticker,e.predecessor_ticker,e.event_type,e.event_date,
                       e.comparability_status,e.review_status,
                       COALESCE(q.quarter_rows,0) quarter_rows,
                       COALESCE(q.pre_event_quarters,0) pre_event_quarters,
                       COALESCE(q.unresolved_quarters,0) unresolved_quarters,
                       COALESCE(t.pre_event_ttm,0) pre_event_ttm,
                       COALESCE(t.post_event_clean_ttm,0) post_event_clean_ttm,
                       COALESCE(t.structural_not_ready_ttm,0) structural_not_ready_ttm
                  FROM {structural_break.EVENT_TABLE} e
                  LEFT JOIN quarter_counts q USING(event_id)
                  LEFT JOIN ttm_counts t USING(event_id)
                 ORDER BY e.successor_ticker"""
        )]
        eligibility, metadata = structural_break.latest_ttm_eligibility(conn, as_of_date=REPORT_DATE)
    by_company = {
        str(row.company_id): {
            "eligible": row.eligible,
            "reason_code": row.reason_code,
            "ticker_event_type": row.event_type,
            "ttm_regime_status": row.ttm_regime_status,
        }
        for row in eligibility.values()
    }
    return {"rows": rows, "current_eligibility": by_company, "metadata": metadata}


def _copy_rehearsal(output: Path, lane: str, source: Mapping[str, Any]) -> dict[str, Any]:
    lane_dir = output / lane
    copies = lane_dir / "copies"
    copies.mkdir(parents=True, exist_ok=True)
    provider = copies / "fundamentals_provider.db"
    canonical = copies / "fundamentals_v4.db"
    analysis = copies / "fundamentals_analysis.db"
    result: dict[str, Any] = {"lane": lane, "started_at_utc": utc_now()}
    try:
        result["backups"] = {
            "provider": online_backup(PRODUCTION["provider"], provider),
            "canonical": online_backup(PRODUCTION["canonical"], canonical),
            "analysis": online_backup(PRODUCTION["analysis"], analysis),
        }
        paths = CandidatePaths(canonical, analysis, PRODUCTION["taxonomy"], provider_db=provider, market_db=PRODUCTION["market"])
        result["before"] = {
            "provider": database_inventory(provider),
            "canonical": database_inventory(canonical),
            "analysis": database_inventory(analysis),
        }
        result["identity"] = _apply_transition_identities(canonical)
        result["provider_staging"] = stage_provider_rows(provider, canonical, source["rows_by_ticker"])
        result["provider_staging_replay"] = stage_provider_rows(provider, canonical, source["rows_by_ticker"])
        from rawcandle.fundamentals.phase12d import reconcile_canonical, rebuild_ttm

        result["canonical"] = reconcile_canonical(provider, canonical, applied_at=APPLIED_AT)
        result["ttm"] = rebuild_ttm(canonical, applied_at=APPLIED_AT)
        result["successor_canonical_ttm"] = successor_canonical_ttm_report(canonical)
        result["structural_contract"] = structural_break.apply_contract(
            canonical,
            events=_events(),
            applied_at_utc=APPLIED_AT,
        )
        result["structural_evidence"] = _structural_evidence(canonical)
        structural_package_fp = _structural_package_fingerprint(result["structural_contract"])
        result["structural_package_fingerprint"] = structural_package_fp
        result["valuation_classification"] = _valuation_classification_update(analysis, PRODUCTION["market"], canonical)
        ensure_candidate_schema(paths, applied_at_utc=APPLIED_AT, apply=True)
        universe = backfill_universe(paths, applied_at_utc=APPLIED_AT, apply=True)
        result["universe"] = universe
        result["package"] = instrumented_package_refresh(
            {
                "provider": provider,
                "canonical": canonical,
                "analysis": analysis,
                "market": PRODUCTION["market"],
                "taxonomy": PRODUCTION["taxonomy"],
            },
            lane_dir,
        )
        result["relative_position"] = asdict(refresh_relative_position(
            canonical_db=canonical,
            analysis_db=analysis,
            market_db=PRODUCTION["market"],
            taxonomy_db=PRODUCTION["taxonomy"],
            snapshot_date=REPORT_DATE,
            model_fingerprint=RP_MODEL_FINGERPRINT,
            applied_at_utc=APPLIED_AT,
        ))
        taxonomy = taxonomy_identity(PRODUCTION["taxonomy"])
        result["pre_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["relative_valuation"] = _manual_rv_refresh(paths, output=lane_dir)
        result["dependencies"] = attach_dependencies(paths, universe=universe["identity"], applied_at_utc=APPLIED_AT, apply=True)
        result["post_refresh_compatibility"] = candidate_relative_valuation_dependency_state(
            analysis,
            report_date=REPORT_DATE,
            expected_universe_fingerprint=universe["identity"]["economic_result_fingerprint"],
            expected_taxonomy_economic_fingerprint=taxonomy["taxonomy_economic_fingerprint"],
        )
        result["snapshots"] = _snapshot_smoke(paths, lane_dir)
        result["areb_after"] = _areb_counts(analysis)
        result["final_inventory"] = {
            "provider": database_inventory(provider),
            "canonical": database_inventory(canonical),
            "analysis": database_inventory(analysis),
        }
        write_json(lane_dir / "rehearsal_result.json", result)
        return result
    except BaseException as exc:
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(lane_dir / "rehearsal_failure.json", result)
        raise
    finally:
        if copies.exists():
            shutil.rmtree(copies)
        write_json(lane_dir / "cleanup.json", {
            "transient_copies_removed": not copies.exists(),
            "storage": _storage("cleanup"),
            "remaining_database_artifacts": [
                str(path) for path in lane_dir.rglob("*")
                if path.suffix in {".db", ".sqlite"} or path.name.endswith(("-wal", "-shm", "-journal"))
            ],
        })


def _economic_fingerprint(result: Mapping[str, Any]) -> str:
    return stable_hash({
        "source_recovery": result["provider_staging"]["matched_by_dimension"],
        "structural": result["structural_contract"]["regime_fingerprint"],
        "structural_package_fingerprint": result["structural_package_fingerprint"],
        "package": result["package"]["first_apply"]["economic_result_fingerprint"],
        "relative_position": result["relative_position"]["result_fingerprint"],
        "relative_valuation": result["relative_valuation"]["snapshot"]["result_fingerprint"],
        "rv_exclusions": result["relative_valuation"]["source_metadata"].get("excluded_input_counts", {}),
        "snapshots": {
            ticker: {key: row.get(key) for key in ("status", "fingerprint", "reason", "error")}
            for ticker, row in result["snapshots"].items()
        },
    })


def _blockers(run: Mapping[str, Any] | None, deterministic: Mapping[str, Any]) -> list[str]:
    if run is None:
        return ["FIRST_REHEARSAL_DID_NOT_COMPLETE"]
    blockers: list[str] = []
    if run["provider_staging_replay"]["logical_changes"] != 0:
        blockers.append("PROVIDER_STAGING_REPLAY_NOT_NO_CHANGE")
    if run["pre_refresh_compatibility"]["state"] == "COMPATIBLE":
        blockers.append("PRE_REFRESH_RV_DID_NOT_SHOW_INCOMPATIBILITY")
    if run["post_refresh_compatibility"]["state"] != "COMPATIBLE":
        blockers.append(f"POST_REFRESH_RV_COMPATIBILITY:{run['post_refresh_compatibility']['state']}")
    rv_excluded = run["relative_valuation"]["source_metadata"].get("excluded_input_counts", {})
    if int(rv_excluded.get("CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM", 0)) < 2:
        blockers.append("STRUCTURAL_BREAK_CURRENT_RV_EXCLUSION_NOT_PROVEN")
    evidence = {row["successor_ticker"]: row for row in run["structural_evidence"]["rows"]}
    for ticker in ("VMRK", "NMAD", "VAI"):
        if ticker not in evidence:
            blockers.append(f"STRUCTURAL_EVENT_MISSING:{ticker}")
    if (run["snapshots"].get("VMRK") or {}).get("status") == "FAILED":
        blockers.append("VMRK_SNAPSHOT_FAILED")
    if (run["snapshots"].get("NMAD") or {}).get("status") == "FAILED":
        blockers.append("NMAD_SNAPSHOT_FAILED")
    if int(run["areb_after"]["post_delisting_relative_valuation_rows"]) != 0:
        blockers.append("AREB_POST_DELISTING_RV_ROWS_PRESENT")
    if not deterministic.get("match"):
        blockers.append("DETERMINISTIC_REPLAY_MISMATCH")
    return blockers


def render_report(output: Path, result: Mapping[str, Any]) -> dict[str, Any]:
    run = result.get("run_1") or {}
    rv_meta = ((run.get("relative_valuation") or {}).get("source_metadata") or {})
    lines = [
        "# Phase 13F.3.3 Versioned Economic Structural-Break Contract",
        "",
        f"Outcome: **{result['outcome']}**",
        "",
        "Production writes: none. All writes were restricted to fresh rehearsal copies that were removed after evidence serialization.",
        "",
        f"Structural contract version: `{structural_break.CONTRACT_VERSION}`",
        f"Structural package fingerprint: `{run.get('structural_package_fingerprint')}`",
        f"Pre-refresh RV compatibility: `{((run.get('pre_refresh_compatibility') or {}).get('state'))}`",
        f"Post-refresh RV compatibility: `{((run.get('post_refresh_compatibility') or {}).get('state'))}`",
        f"RV excluded input counts: `{json.dumps(rv_meta.get('excluded_input_counts', {}), sort_keys=True)}`",
        f"Deterministic replay: `{(result.get('determinism') or {}).get('match')}`",
        f"Production immutable: `{result['production_immutability']['identical']}`",
        "",
        "## Event Decisions",
        "",
        "| ticker | event | review | pre-event TTM | post-clean TTM | unresolved quarters |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in ((run.get("structural_evidence") or {}).get("rows") or []):
        lines.append(
            f"| {row['successor_ticker']} | {row['comparability_status']} | {row['review_status']} | "
            f"{row['pre_event_ttm'] or 0} | {row['post_event_clean_ttm'] or 0} | {row['unresolved_quarters'] or 0} |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in result["blockers"])
    if not result["blockers"]:
        lines.append("- none")
    text = "\n".join(lines) + "\n"
    path = output / "phase13f3_3_report.md"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "bytes": len(text.encode("utf-8")), "sha256": stable_hash(text)}


def run_phase13f3_3(output: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    output = (output or ARTIFACT_ROOT / DEFAULT_RUN_ID).resolve()
    reject_production_path(output, "output")
    output.mkdir(parents=True, exist_ok=True)
    pre_inventory = production_inventory()
    source = archive_reconciliation()
    write_json(output / "source_reconciliation.json", {key: value for key, value in source.items() if key != "rows_by_ticker"})
    run_1: dict[str, Any] | None = None
    run_2: dict[str, Any] | None = None
    deterministic: dict[str, Any] = {"match": False}
    try:
        run_1 = _copy_rehearsal(output, "run_1", source)
        run_2 = _copy_rehearsal(output, "run_2", source)
        deterministic = {
            "run_1_economic_fingerprint": _economic_fingerprint(run_1),
            "run_2_economic_fingerprint": _economic_fingerprint(run_2),
        }
        deterministic["match"] = deterministic["run_1_economic_fingerprint"] == deterministic["run_2_economic_fingerprint"]
    except BaseException as exc:
        deterministic = {"match": False, "reason": type(exc).__name__, "message": str(exc)}
    post_inventory = production_inventory()
    blockers = _blockers(run_1, deterministic)
    result = {
        "phase": PHASE,
        "outcome": OUTCOME_A if not blockers else OUTCOME_B,
        "blockers": blockers,
        "source_reconciliation": {key: value for key, value in source.items() if key != "rows_by_ticker"},
        "run_1": run_1,
        "run_2": run_2,
        "determinism": deterministic,
        "production_immutability": compare_production_inventory(pre_inventory, post_inventory),
        "storage": {"final": _storage("final")},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    result["report"] = render_report(output, result)
    write_json(output / "phase13f3_3_result.json", result)
    return result
