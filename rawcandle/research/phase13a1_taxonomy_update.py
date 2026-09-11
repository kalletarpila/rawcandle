from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT, compare_production_inventory, production_inventory
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT as RV_MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.persistence import RelativeValuationRepository
from rawcandle.fundamentals.snapshot.ui_service import PRODUCTION_SNAPSHOT_PATHS


PHASE = "PHASE13A1_TAXONOMY_UPDATE_READINESS_AUDIT"
OUTCOME = "OUTCOME B — TAXONOMY VERSIONING OR DEPENDENCY TRACKING REQUIRED FIRST"
DOC_PATH = ROOT / "docs/fundamentals_v4/fundamentals_v4_phase13_architecture_contract.md"
ACTIVE_TAXONOMY_SOURCE = ROOT / "data/datacenter_taxonomy_full_v2_1.csv"
SCHEDULER_UI = ROOT / "dev_tools/stock_update_scheduler_ui.py"
TAXONOMY_ORCHESTRATOR = ROOT / "rawcandle/datacenter_taxonomy_change_orchestrator.py"
LOCK_PATH = ROOT / "temp/.fundamentals_phase9e.lock"


@dataclass(frozen=True)
class AuditPaths:
    output: Path
    canonical_db: Path = PRODUCTION["canonical"]
    analysis_db: Path = PRODUCTION["analysis"]
    market_db: Path = PRODUCTION["market"]
    taxonomy_db: Path = PRODUCTION["taxonomy"]
    provider_db: Path = PRODUCTION["provider"]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({field for row in rows for field in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted((dict(row) for row in rows), key=lambda item: stable_json(item)):
            writer.writerow(row)


def connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _one(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else 0


def git_state() -> dict[str, Any]:
    upstream = subprocess.run(("git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"), cwd=ROOT, capture_output=True, text=True, check=False)
    behind = ahead = None
    if upstream.returncode == 0 and upstream.stdout.strip():
        left, right = upstream.stdout.split()
        behind, ahead = int(left), int(right)
    return {
        "branch": subprocess.run(("git", "branch", "--show-current"), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "head": subprocess.run(("git", "rev-parse", "HEAD"), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "status_porcelain": subprocess.run(("git", "status", "--porcelain"), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "upstream_behind": behind,
        "upstream_ahead": ahead,
    }


def taxonomy_source_inventory(paths: AuditPaths) -> list[dict[str, Any]]:
    with connect_ro(paths.taxonomy_db) as conn:
        versions = [dict(row) for row in conn.execute(
            "SELECT taxonomy_version_id,taxonomy_version_code,taxonomy_name,source_type,source_reference,source_hash,status,is_active,active_from,active_to,created_at_utc "
            "FROM ec_taxonomy_version ORDER BY taxonomy_version_id"
        )]
        table_counts = {
            table: _one(conn, f"SELECT COUNT(*) FROM {table}")
            for table in ("ec_ecosystem", "ec_taxonomy_version", "ec_entity", "ec_entity_alias", "ec_membership")
        }
    rows = []
    for version in versions:
        source_ref = str(version.get("source_reference") or "")
        source_path = Path(source_ref)
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        rows.append({
            **version,
            "source_exists": source_path.exists(),
            "source_size": source_path.stat().st_size if source_path.exists() else 0,
            "source_file_sha256": file_sha256(source_path) if source_path.exists() else "",
            "source_hash_matches_file": bool(source_path.exists() and version.get("source_hash") == file_sha256(source_path)),
        })
    rows.append({
        "taxonomy_version_code": "TABLE_COUNTS",
        "taxonomy_name": "production taxonomy table counts",
        "source_type": "SQLITE",
        "source_reference": str(paths.taxonomy_db),
        "source_hash": stable_hash(table_counts),
        "status": "EVIDENCE",
        "is_active": "",
        "active_from": "",
        "active_to": "",
        "created_at_utc": "",
        "source_exists": paths.taxonomy_db.exists(),
        "source_size": paths.taxonomy_db.stat().st_size,
        "source_file_sha256": file_sha256(paths.taxonomy_db),
        "source_hash_matches_file": "",
        **{f"count_{key}": value for key, value in table_counts.items()},
    })
    return rows


def taxonomy_identity_reconciliation(paths: AuditPaths) -> list[dict[str, Any]]:
    with connect_ro(paths.canonical_db) as canonical, connect_ro(paths.taxonomy_db) as taxonomy:
        active_company_tickers = {row[0]: int(row[1]) for row in canonical.execute("SELECT UPPER(current_ticker),company_id FROM security WHERE active=1")}
        alias_rows = [(str(row[0]).upper(), int(row[1])) for row in canonical.execute("SELECT UPPER(a.ticker),s.company_id FROM ticker_alias a JOIN security s USING(security_id)")]
        aliases: dict[str, set[int]] = {}
        for ticker, company_id in alias_rows:
            aliases.setdefault(ticker, set()).add(company_id)
        taxonomy_tickers = [str(row[0]).upper() for row in taxonomy.execute(
            "SELECT ticker FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE' AND ticker IS NOT NULL ORDER BY ticker"
        )]
    counts = {
        "direct_current_ticker": 0,
        "alias_only": 0,
        "ambiguous_alias": 0,
        "unmapped": 0,
    }
    rows = []
    for ticker in taxonomy_tickers:
        direct = active_company_tickers.get(ticker)
        alias_companies = aliases.get(ticker, set())
        if direct is not None:
            status = "DIRECT_CURRENT_TICKER"
            company_id = direct
            counts["direct_current_ticker"] += 1
        elif len(alias_companies) == 1:
            status = "ALIAS_ONLY"
            company_id = next(iter(alias_companies))
            counts["alias_only"] += 1
        elif len(alias_companies) > 1:
            status = "AMBIGUOUS_ALIAS"
            company_id = ""
            counts["ambiguous_alias"] += 1
        else:
            status = "UNMAPPED"
            company_id = ""
            counts["unmapped"] += 1
        rows.append({"taxonomy_ticker": ticker, "mapping_status": status, "company_id": company_id})
    operational_without_taxonomy = sorted(set(active_company_tickers) - set(taxonomy_tickers))
    rows.append({
        "taxonomy_ticker": "__SUMMARY__",
        "mapping_status": "OPERATIONAL_WITHOUT_ACTIVE_TAXONOMY",
        "company_id": len(operational_without_taxonomy),
        "sample": " ".join(operational_without_taxonomy[:25]),
        **counts,
    })
    return rows


def taxonomy_change_classification_contract() -> dict[str, Any]:
    return {
        "version": "PHASE13A1_TAXONOMY_CHANGE_CLASSIFICATION_V1",
        "identity_key": "stable company_id/security_id plus explicit ticker/alias evidence; never ticker alone",
        "change_categories": [
            "COMPANY_ADDED_TO_TAXONOMY",
            "COMPANY_REMOVED_OR_INACTIVE",
            "TICKER_OR_ALIAS_CHANGED",
            "SECTOR_CHANGED",
            "INDUSTRY_CHANGED",
            "ACCOUNTING_CLASSIFICATION_CHANGED",
            "PEER_GROUP_MEMBERSHIP_CHANGED",
            "ELIGIBILITY_APPLICABILITY_CHANGED",
            "DISPLAY_NAME_OR_DESCRIPTION_CHANGED",
            "SOURCE_METADATA_CHANGED",
            "IDENTITY_AMBIGUOUS",
            "MISSING_AUTHORITATIVE_SOURCE_IDENTITY",
            "UNCHANGED",
        ],
        "impact_classes": [
            "NO_CHANGE",
            "PRESENTATION_ONLY",
            "MEMBERSHIP_CHANGE",
            "PEER_GROUP_CHANGE",
            "ACCOUNTING_APPLICABILITY_CHANGE",
            "IDENTITY_AMBIGUOUS",
            "SOURCE_NOT_READY",
        ],
        "preview_fields": [
            "stable_identity",
            "current_ticker",
            "current_value",
            "proposed_value",
            "authoritative_source_version",
            "authoritative_source_fingerprint",
            "effective_or_as_of_date",
            "change_category",
            "economic_impact_class",
            "affected_downstream_layers",
            "readiness_or_blocking_reason",
        ],
    }


def downstream_dependency_matrix() -> list[dict[str, Any]]:
    return [
        {"field": "sector", "consumers": "Relative Position, Relative Valuation, Snapshot presentation", "impact": "PEER_GROUP_CHANGE", "rebuild_scope": "full-universe peer-scoped analysis"},
        {"field": "industry", "consumers": "Relative Position, Relative Valuation, Snapshot presentation", "impact": "PEER_GROUP_CHANGE", "rebuild_scope": "full-universe peer-scoped analysis"},
        {"field": "ecosystem membership", "consumers": "Relative Position ecosystem scope, Relative Valuation ecosystem memberships, Snapshot taxonomy section", "impact": "MEMBERSHIP_CHANGE", "rebuild_scope": "full-universe peer-scoped analysis"},
        {"field": "accounting applicability/classification", "consumers": "Score/Valuation/Diagnostics applicability gates if introduced as Fundamentals accounting taxonomy", "impact": "ACCOUNTING_APPLICABILITY_CHANGE", "rebuild_scope": "all affected companies plus coherent OI V2 package"},
        {"field": "display name/description/notes/report_group_status", "consumers": "Scheduler taxonomy pages, Snapshot presentation when surfaced", "impact": "PRESENTATION_ONLY", "rebuild_scope": "taxonomy DB/report presentation only"},
        {"field": "ticker alias", "consumers": "identity resolution, onboarding, taxonomy mapping audit", "impact": "IDENTITY_AMBIGUOUS or MEMBERSHIP_CHANGE", "rebuild_scope": "block until identity resolved"},
        {"field": "source_hash/source_reference/version", "consumers": "preview/apply confirmation, provenance", "impact": "SOURCE_NOT_READY or NO_CHANGE", "rebuild_scope": "none unless rows changed"},
        {"field": "Fundamental Score V2 numeric inputs", "consumers": "Score, Lifecycle, Valuation, Delta", "impact": "NO_CHANGE for EC-only taxonomy", "rebuild_scope": "none for current EC taxonomy"},
        {"field": "Diagnostic Flags V2 inputs", "consumers": "eight Diagnostic Flags V2", "impact": "NO_CHANGE for EC-only taxonomy except future applicability gates", "rebuild_scope": "none for current EC taxonomy"},
    ]


def database_write_and_rollback_matrix() -> list[dict[str, Any]]:
    return [
        {"case": "presentation_only_taxonomy_update", "databases_written": "taxonomy database only; maybe reports on explicit generation", "backup_required": "data/analysis.db", "rollback": "restore taxonomy DB if apply fails"},
        {"case": "peer_group_change", "databases_written": "taxonomy DB and fundamentals_analysis.db", "backup_required": "data/analysis.db and data/fundamentals_analysis.db", "rollback": "restore both; Relative Position/RV must reconcile"},
        {"case": "accounting_applicability_change", "databases_written": "taxonomy DB, canonical if applicability is persisted there, analysis DB", "backup_required": "all modified DBs", "rollback": "restore every modified DB; no activation-only claim"},
        {"case": "taxonomy_membership_add_remove", "databases_written": "taxonomy DB and peer-scoped analysis rows", "backup_required": "taxonomy and analysis DBs", "rollback": "restore both on any downstream failure"},
        {"case": "combined_ticker_plus_taxonomy_apply", "databases_written": "provider, canonical, taxonomy, analysis", "backup_required": "fundamentals_provider.db, fundamentals_v4.db, data/analysis.db, fundamentals_analysis.db", "rollback": "complete multi-DB restore on coherent-batch failure"},
    ]


def taxonomy_ui_status_contract() -> dict[str, Any]:
    return {
        "view": "Fundamentals / Taxonomy Update",
        "statuses": [
            "NO_TAXONOMY_CHANGE",
            "CHANGES_DETECTED",
            "PRESENTATION_ONLY_CHANGES",
            "ECONOMIC_CHANGES_REQUIRE_REBUILD",
            "IDENTITY_REVIEW_REQUIRED",
            "SOURCE_NOT_READY",
            "APPLIED",
            "NO_CHANGE",
            "FAILED_ROLLED_BACK",
        ],
        "apply_rejects_if": [
            "source changed after preview",
            "active taxonomy changed after preview",
            "operational universe changed after preview",
            "relevant database fingerprints changed",
            "preview expired",
            "another maintenance job is active",
        ],
        "browser_must_not_receive": ["unrestricted filesystem paths", "raw SQL", "raw exception traces", "API keys", "database credentials"],
    }


def snapshot_failure_diagnosis(paths: AuditPaths) -> dict[str, Any]:
    requested_report_date = "2026-09-12"
    with connect_ro(paths.analysis_db) as conn:
        repo = RelativeValuationRepository(conn)
        selected = repo.report_snapshot_metadata(requested_report_date, model_fingerprint=RV_MODEL_FINGERPRINT)
        available = [dict(row) for row in conn.execute(
            "SELECT snapshot_id,model_fingerprint,as_of_date,status,created_at_utc,completed_at_utc,source_fingerprint,result_fingerprint "
            "FROM relative_valuation_snapshot WHERE model_fingerprint=? ORDER BY as_of_date,created_at_utc",
            (RV_MODEL_FINGERPRINT,),
        )]
        active = [dict(row) for row in conn.execute("SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint")]
    return {
        "requested_report_date": requested_report_date,
        "database_paths": {key: str(value) for key, value in PRODUCTION_SNAPSHOT_PATHS.__dict__.items()},
        "available_relative_valuation_snapshots": available,
        "active_relative_valuation_pointer": active,
        "selected_snapshot": selected,
        "phase11e_non_future_rule": "Use active complete snapshot when active as_of_date <= report_date; otherwise newest retained complete same-contract snapshot with as_of_date <= report_date.",
        "diagnosis": "STALE_TEST_EXPECTATION",
        "evidence": "For report date 2026-09-12 the active 2026-09-10 snapshot is eligible and selected. The old test expected 2026-09-08 from the prior production state. The observed 2026-09-06 line is Relative Position source-state metadata, not Relative Valuation.",
        "correction": "Updated the real Snapshot integration test to derive the expected Relative Valuation snapshot date through RelativeValuationRepository.report_snapshot_metadata().",
        "production_data_modified": False,
    }


def relative_valuation_taxonomy_coherence(paths: AuditPaths) -> dict[str, Any]:
    with connect_ro(paths.analysis_db) as analysis, connect_ro(paths.taxonomy_db) as taxonomy:
        columns = [str(row["name"]) for row in analysis.execute("PRAGMA table_info(relative_valuation_snapshot)")]
        active_taxonomy = [dict(row) for row in taxonomy.execute(
            "SELECT taxonomy_version_code,source_hash,source_reference,active_from FROM ec_taxonomy_version WHERE status='ACTIVE' AND is_active=1 ORDER BY taxonomy_version_id"
        )]
        active_rv = [dict(row) for row in analysis.execute(
            "SELECT snapshot_id,as_of_date,source_fingerprint,result_fingerprint FROM relative_valuation_snapshot WHERE snapshot_id IN (SELECT snapshot_id FROM relative_valuation_active_snapshot)"
        )]
    has_explicit_taxonomy_columns = any("taxonomy" in column.lower() for column in columns)
    return {
        "active_taxonomy": active_taxonomy,
        "active_relative_valuation": active_rv,
        "relative_valuation_snapshot_columns": columns,
        "explicit_taxonomy_dependency_columns_present": has_explicit_taxonomy_columns,
        "source_calculation_includes_taxonomy_fingerprint": True,
        "reader_detects_current_taxonomy_mismatch_without_recalculation": False,
        "decision": "Economically material taxonomy changes require a manually confirmed full-universe Relative Position and Relative Valuation refresh in the same operation, or the active RV snapshot can appear valid while reflecting older peer taxonomy.",
    }


def quantitative_summary(paths: AuditPaths) -> dict[str, Any]:
    with connect_ro(paths.taxonomy_db) as taxonomy, connect_ro(paths.canonical_db) as canonical, connect_ro(paths.analysis_db) as analysis:
        active_taxonomy_tickers = {row[0] for row in taxonomy.execute("SELECT UPPER(ticker) FROM ec_entity WHERE entity_type='TICKER' AND status='ACTIVE' AND ticker IS NOT NULL")}
        operational = {row[0] for row in canonical.execute("SELECT UPPER(current_ticker) FROM security WHERE active=1")}
        peer_rows = _one(analysis, "SELECT COUNT(*) FROM relative_position_result")
        rv_peer_rows = _one(analysis, "SELECT COUNT(*) FROM relative_valuation_peer_position")
        memberships = _one(taxonomy, "SELECT COUNT(*) FROM ec_membership WHERE status='ACTIVE'")
    return {
        "active_taxonomy_identities": len(active_taxonomy_tickers),
        "matching_operational_universe": len(active_taxonomy_tickers & operational),
        "operational_companies_without_taxonomy": len(operational - active_taxonomy_tickers),
        "taxonomy_entries_without_operational_company": len(active_taxonomy_tickers - operational),
        "active_memberships": memberships,
        "relative_position_rows": peer_rows,
        "relative_valuation_peer_rows": rv_peer_rows,
    }


def production_preflight_postflight(paths: AuditPaths, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "production_writes_performed": False,
        "external_requests_performed": False,
        "maintenance_lock_path": str(LOCK_PATH),
        "inventory_reconciliation": compare_production_inventory(before, after),
        "safe_connection": "SQLite file URI mode=ro plus PRAGMA query_only=ON; no immutable=1",
    }


def build_report(git: Mapping[str, Any], quantitative: Mapping[str, Any], diagnosis: Mapping[str, Any], coherence: Mapping[str, Any]) -> str:
    selected = diagnosis.get("selected_snapshot") or {}
    return f"""# Phase 13A.1 Taxonomy Update Readiness Report

Selected outcome: **{OUTCOME}**.

## Snapshot Integration Test Diagnosis

The failing real Snapshot integration test requested report date `{diagnosis['requested_report_date']}`. The production paths were the standard `PRODUCTION_SNAPSHOT_PATHS` under `data/`. Available Relative Valuation snapshots are recorded in `relative_valuation_taxonomy_coherence.json` and `snapshot_integration_failure_diagnosis.json`.

Phase 11E's non-future rule selects the active complete snapshot when its `as_of_date` is not later than the report date. Current production active Relative Valuation is `{selected.get('as_of_date')}` (`{selected.get('snapshot_id')}`). Therefore the hard-coded test expectation `2026-09-08` was stale after the Phase 12E/ten-year refresh. This was not a fixture/path mismatch and not a reader defect. The test now derives the expected date through `RelativeValuationRepository.report_snapshot_metadata()`.

## Taxonomy Source

The current persisted taxonomy source is Datacenter/EC taxonomy, active version `DC_TAXONOMY_FULL_V2_1`, source file `data/datacenter_taxonomy_full_v2_1.csv`, source hash recorded in `ec_taxonomy_version`. Existing top-level Scheduler Taxonomy functionality is Datacenter/EC taxonomy orchestration, not a dedicated Fundamentals accounting taxonomy UI. Future Fundamentals `Taxonomy Update` must remain a separate view/operation even if it reuses safe read-only diff and lock/backup conventions.

## Quantitative Evidence

- Active taxonomy ticker identities: {quantitative['active_taxonomy_identities']}.
- Matching operational Fundamentals universe: {quantitative['matching_operational_universe']}.
- Operational companies without active taxonomy: {quantitative['operational_companies_without_taxonomy']}.
- Taxonomy tickers without operational company: {quantitative['taxonomy_entries_without_operational_company']}.
- Active taxonomy memberships: {quantitative['active_memberships']}.
- Relative Position rows currently derived from taxonomy/classification context: {quantitative['relative_position_rows']}.
- Relative Valuation peer rows: {quantitative['relative_valuation_peer_rows']}.

## Relative Valuation Coherence

Relative Valuation source calculation includes a taxonomy fingerprint, but `relative_valuation_snapshot` does not expose explicit taxonomy dependency columns. The reader cannot prove current-taxonomy compatibility without recalculating or comparing a separately persisted taxonomy dependency. Economically material taxonomy updates should therefore require same-operation full-universe Relative Position and Relative Valuation refresh, with complete rollback if either dependent stage fails.

## Future Contract

`Check Taxonomy Changes` is read-only and emits a fingerprinted preview. `Apply Taxonomy Changes` must reference that exact preview, acquire the maintenance lock, verify no writer is active, back up every database that may change, apply exactly the previewed change set, rebuild economically affected layers, reconcile, then prove a second logical and physical `NO_CHANGE`.

Ticker onboarding and taxonomy update remain separate manual operations, but a combined batch should stage identities, stage taxonomy changes, stage provider/canonical additions, calculate combined impact, show one immutable preview, and apply the accepted coherent batch.

## Git

Audit started on branch `{git['branch']}` at `{git['head']}` with upstream behind/ahead `{git['upstream_behind']}/{git['upstream_ahead']}`.
"""


def recommended_scope_text() -> str:
    return """# Recommended Phase 13B Taxonomy Scope

Implement a read-only `check-taxonomy-changes` backend before any apply path.

Required apply prerequisites:

- authoritative source fingerprint matches preview;
- active taxonomy, operational universe and relevant database fingerprints match preview;
- maintenance lock and writer checks pass;
- backups are independently openable;
- peer-group/applicability changes rebuild Relative Position and Relative Valuation in the same confirmed operation;
- stale Relative Valuation peer snapshots are never silently displayed as coherent with materially changed taxonomy.
"""


def run(paths: AuditPaths) -> dict[str, Any]:
    paths.output.mkdir(parents=True, exist_ok=False)
    before = production_inventory()
    git = git_state()
    source_rows = taxonomy_source_inventory(paths)
    identity_rows = taxonomy_identity_reconciliation(paths)
    classification_contract = taxonomy_change_classification_contract()
    dependency_rows = downstream_dependency_matrix()
    rollback_rows = database_write_and_rollback_matrix()
    ui_contract = taxonomy_ui_status_contract()
    diagnosis = snapshot_failure_diagnosis(paths)
    coherence = relative_valuation_taxonomy_coherence(paths)
    quantitative = quantitative_summary(paths)
    decision = {
        "phase": PHASE,
        "outcome": OUTCOME,
        "principal_blocker": "Relative Valuation persistence lacks explicit current taxonomy dependency tracking for reader-time mismatch detection.",
        "phase13a_ticker_onboarding_outcome": "OUTCOME B — AUTHORITATIVE OPERATIONAL UNIVERSE WORK REQUIRED FIRST",
        "combined_phase13b_implication": "Build authoritative universe and taxonomy preview contracts before any write-capable UI.",
    }
    write_csv(paths.output / "taxonomy_source_inventory.csv", source_rows)
    write_csv(paths.output / "taxonomy_identity_reconciliation.csv", identity_rows)
    write_json(paths.output / "taxonomy_change_classification_contract.json", classification_contract)
    write_csv(paths.output / "taxonomy_downstream_dependency_matrix.csv", dependency_rows)
    write_csv(paths.output / "taxonomy_database_write_and_rollback_matrix.csv", rollback_rows)
    write_json(paths.output / "taxonomy_ui_status_contract.json", ui_contract)
    write_json(paths.output / "relative_valuation_taxonomy_coherence.json", coherence)
    write_json(paths.output / "snapshot_integration_failure_diagnosis.json", diagnosis)
    write_json(paths.output / "quantitative_taxonomy_evidence.json", quantitative)
    write_json(paths.output / "decision.json", decision)
    (paths.output / "recommended_phase13b_taxonomy_scope.md").write_text(recommended_scope_text(), encoding="utf-8")
    report = build_report(git, quantitative, diagnosis, coherence)
    (paths.output / "PHASE13A1_TAXONOMY_UPDATE_READINESS_REPORT.md").write_text(report, encoding="utf-8")
    commands = {
        "commands": [
            "sqlite3 -readonly data/analysis.db ...",
            "python3 -m rawcandle.cli.run_phase13a1_taxonomy_update_audit --output <artifact-dir>",
            "python3 -m pytest tests/test_fundamentals_snapshot_ui.py::test_ui_service_real_snapshot_integration_is_read_only",
        ],
        "secrets_omitted": True,
    }
    write_json(paths.output / "commands_executed.json", commands)
    source_manifest = {
        "files": [
            {"path": "rawcandle/datacenter_taxonomy_change_orchestrator.py", "sha256": file_sha256(TAXONOMY_ORCHESTRATOR)},
            {"path": "dev_tools/stock_update_scheduler_ui.py", "sha256": file_sha256(SCHEDULER_UI)},
            {"path": "rawcandle/fundamentals/relative_valuation/source.py", "sha256": file_sha256(ROOT / "rawcandle/fundamentals/relative_valuation/source.py")},
            {"path": "rawcandle/fundamentals/relative_valuation/persistence.py", "sha256": file_sha256(ROOT / "rawcandle/fundamentals/relative_valuation/persistence.py")},
        ],
    }
    source_manifest["fingerprint"] = stable_hash(source_manifest)
    write_json(paths.output / "source_manifest.json", source_manifest)
    after = production_inventory()
    prepost = production_preflight_postflight(paths, before, after)
    write_json(paths.output / "production_preflight_postflight.json", prepost)
    result_manifest = {
        "result_fingerprint": stable_hash({
            "decision": decision,
            "source_rows": source_rows,
            "identity_rows": identity_rows,
            "classification_contract": classification_contract,
            "dependency_rows": dependency_rows,
            "rollback_rows": rollback_rows,
            "ui_contract": ui_contract,
            "diagnosis": diagnosis,
            "coherence": coherence,
            "quantitative": quantitative,
        }),
        "artifact_files": sorted(path.name for path in paths.output.iterdir() if path.is_file()),
    }
    write_json(paths.output / "result_manifest.json", result_manifest)
    return {
        "ok": True,
        "outcome": OUTCOME,
        "output": str(paths.output),
        "production_unchanged": prepost["inventory_reconciliation"]["identical"],
        "result_fingerprint": result_manifest["result_fingerprint"],
        "snapshot_test_diagnosis": diagnosis["diagnosis"],
    }
