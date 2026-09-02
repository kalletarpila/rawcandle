from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT, canonical_json, fingerprint
from rawcandle.fundamentals.delta.persistence import (
    COMPONENT_TABLE, LIFECYCLE_TABLE, META_TABLE, TABLES, TOTAL_TABLE, VALUATION_TABLE,
    DeltaPersistencePackage, apply_package, build_persistence_package, ensure_schema,
    quick_check, recalculate_row_fingerprint, rebuild_package,
)
from rawcandle.fundamentals.delta.readers import (
    FundamentalDeltaRepository, LifecycleChangeRepository, ValuationChangeRepository,
)
from rawcandle.fundamentals.delta.source import DeltaSource, ReadOnlyDeltaPaths, latest_fresh_observations, load_delta_source


PRODUCTION_PATHS = {
    Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
    Path("/home/kalle/projects/rawcandle/data/analysis.db"),
}
BACKUP_ROOT = Path("/home/kalle/projects/rawcandle/backups")
EVIDENCE_TABLES = (
    "score_result", "score_component", "lifecycle_revised_result", "valuation_revised_result",
    "relative_position_snapshot", "relative_position_result", "relative_position_coverage",
    "v4_quarter", "v4_ttm_values", "provider_observation", "sharadar_fundamental_observation",
    "osakedata", "splits_data", "ticker_meta", "ec_entity", "ec_group_signal_daily",
)


def sqlite_online_backup(source: Path, destination: Path) -> None:
    if destination.exists(): raise FileExistsError("PHASE5C_DESTINATION_ALREADY_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn=sqlite3.connect(f"file:{source.resolve()}?mode=ro",uri=True)
    destination_conn=sqlite3.connect(destination)
    try: source_conn.backup(destination_conn); destination_conn.commit()
    finally: destination_conn.close(); source_conn.close()


def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(8*1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def database_evidence(path: Path) -> dict[str,Any]:
    stat=path.stat()
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as conn:
        objects=[tuple(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name")]
        tables={row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        counts={table:int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in (*TABLES,META_TABLE,*EVIDENCE_TABLES) if table in tables}
        page_size=int(conn.execute("PRAGMA page_size").fetchone()[0]); page_count=int(conn.execute("PRAGMA page_count").fetchone()[0]); freelist=int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        sqlite_check=conn.execute("PRAGMA quick_check").fetchone()[0]
    return {"path":str(path.resolve()),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns,"sha256":_sha256(path),"schema_hash":hashlib.sha256(repr(objects).encode()).hexdigest(),"page_size":page_size,"page_count":page_count,"freelist_count":freelist,"used_pages":page_count-freelist,"row_counts":counts,"quick_check":sqlite_check}


def storage_evidence(path: Path) -> dict[str,Any]:
    evidence=database_evidence(path)
    wal=Path(f"{path}-wal"); shm=Path(f"{path}-shm")
    evidence["wal_bytes"]=wal.stat().st_size if wal.exists() else 0; evidence["shm_bytes"]=shm.stat().st_size if shm.exists() else 0
    with sqlite3.connect(path) as conn:
        try:
            rows=conn.execute("SELECT name,SUM(pgsize) bytes,COUNT(*) pages FROM dbstat GROUP BY name ORDER BY name").fetchall()
            evidence["dbstat"]={row[0]:{"bytes":int(row[1]),"pages":int(row[2])} for row in rows}
        except sqlite3.DatabaseError: evidence["dbstat"]={"available":False}
    return evidence


def validate_request(*, analysis_db:Path,canonical_db:Path,provider_db:Path,market_db:Path,taxonomy_db:Path,destination:Path,score_model_fingerprint:str,lifecycle_model_fingerprint:str,valuation_model_fingerprint:str,delta_model_fingerprint:str,full_universe:bool,company_ids:Sequence[int],apply:bool) -> None:
    paths=(analysis_db,canonical_db,provider_db,market_db,taxonomy_db,destination)
    if any(not path.is_absolute() for path in paths): raise ValueError("PHASE5C_ALL_PATHS_MUST_BE_ABSOLUTE")
    if delta_model_fingerprint!=MODEL_FINGERPRINT: raise ValueError("DELTA_MODEL_FINGERPRINT_MISMATCH")
    if full_universe==bool(company_ids): raise ValueError("PHASE5C_EXACTLY_ONE_SCOPE_REQUIRED")
    if destination.is_symlink(): raise PermissionError("PHASE5C_SYMLINK_DESTINATION_BLOCKED")
    source_resolved={path.resolve() for path in paths[:-1]}
    if len(source_resolved)!=5: raise ValueError("PHASE5C_SOURCE_PATHS_MUST_BE_DISTINCT")
    resolved=destination.resolve()
    if resolved in source_resolved: raise PermissionError("PHASE5C_SOURCE_DATABASE_CANNOT_BE_DESTINATION")
    if resolved in {path.resolve() for path in PRODUCTION_PATHS}: raise PermissionError("PHASE5C_PRODUCTION_DESTINATION_BLOCKED")
    try: resolved.relative_to(BACKUP_ROOT.resolve())
    except ValueError: pass
    else: raise PermissionError("PHASE5C_PERSISTENT_BACKUP_DESTINATION_BLOCKED")
    if apply and destination.exists() and not destination.is_file(): raise ValueError("PHASE5C_DESTINATION_MUST_BE_FILE")
    if not all((score_model_fingerprint,lifecycle_model_fingerprint,valuation_model_fingerprint)): raise ValueError("PHASE5C_SOURCE_FINGERPRINTS_REQUIRED")


def _changed_source_package(package:DeltaPersistencePackage, *, marker:str) -> DeltaPersistencePackage:
    source=fingerprint({"source":package.fundamental_source_fingerprint,"simulation":marker})
    totals=[recalculate_row_fingerprint({**row,"source_fingerprint":source}) for row in package.total_rows]
    components=[recalculate_row_fingerprint({**row,"source_fingerprint":source}) for row in package.component_rows]
    return rebuild_package(totals,components,package.lifecycle_rows,package.valuation_rows,fundamental_source_fingerprint=source,lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,valuation_source_fingerprint=package.valuation_source_fingerprint)


def _without_company(package:DeltaPersistencePackage, company_id:int) -> DeltaPersistencePackage:
    return rebuild_package(
        [row for row in package.total_rows if row["company_id"]!=company_id],
        [row for row in package.component_rows if row["company_id"]!=company_id],
        [row for row in package.lifecycle_rows if row["company_id"]!=company_id],
        [row for row in package.valuation_rows if row["company_id"]!=company_id],
        fundamental_source_fingerprint=package.fundamental_source_fingerprint,
        lifecycle_source_fingerprint=package.lifecycle_source_fingerprint,
        valuation_source_fingerprint=package.valuation_source_fingerprint,
    )


def _spot_checks(conn:sqlite3.Connection, source:Any) -> dict[str,Any]:
    fundamental=FundamentalDeltaRepository(conn); lifecycle=LifecycleChangeRepository(conn); valuation=ValuationChangeRepository(conn)
    output={}
    for ticker in ("CRMD","APD"):
        company_id=next((cid for cid,name in source.company_tickers.items() if name==ticker),None)
        if company_id is None: output[ticker]=None; continue
        total=fundamental.current_company(company_id,model_fingerprint=MODEL_FINGERPRINT)
        output[ticker]={"company_id":company_id,"qoq":total["qoq_delta"],"two_quarter":total["two_quarter_delta"],"yoy":total["yoy_delta"],"components":len(fundamental.with_components(company_id,total["fiscal_year"],total["fiscal_quarter"],model_fingerprint=MODEL_FINGERPRINT)["components"]),"lifecycle":lifecycle.current_company(company_id,model_fingerprint=MODEL_FINGERPRINT)["current_final_state"],"valuation_two_quarter":valuation.current_company(company_id,model_fingerprint=MODEL_FINGERPRINT)["two_quarter_delta"]}
    return output


def _readiness_reconciliation(package: DeltaPersistencePackage, *, as_of_date: str, freshness_days: int = 180, source: DeltaSource | None = None) -> dict[str, Any]:
    snapshot=date.fromisoformat(as_of_date)
    historical={prefix:sum(row[f"{prefix}_status"]=="DELTA_READY" for row in package.total_rows) for prefix in ("qoq","two_quarter","yoy")}
    latest={}
    for row in package.total_rows:
        available=date.fromisoformat(row["current_available_date"]); age=(snapshot-available).days
        if 0<=age<=freshness_days:
            current=latest.get(row["company_id"])
            if current is None or row["fiscal_sequence"]>current["fiscal_sequence"]: latest[row["company_id"]]=row
    current_ids={row["fundamental_delta_result_id"] for row in latest.values()}
    if source is None:
        lifecycle=[row for row in package.lifecycle_rows if row["fundamental_delta_result_id"] in current_ids]
        valuation=[row for row in package.valuation_rows if row["fundamental_delta_result_id"] in current_ids]
    else:
        lifecycle_keys={(row.fiscal.company_id,row.fiscal.fiscal_sequence) for row in latest_fresh_observations(source.lifecycle_histories,as_of_date=as_of_date,freshness_days=freshness_days)}
        valuation_keys={(row.fiscal.company_id,row.fiscal.fiscal_sequence) for row in latest_fresh_observations(source.valuation_histories,as_of_date=as_of_date,freshness_days=freshness_days)}
        lifecycle=[row for row in package.lifecycle_rows if (row["company_id"],row["fiscal_sequence"]) in lifecycle_keys]
        valuation=[row for row in package.valuation_rows if (row["company_id"],row["fiscal_sequence"]) in valuation_keys]
    return {
        "historical_endpoints":len(package.total_rows),
        "historical_total_ready":historical,
        "current_fresh_endpoints":len(latest),
        "current_fresh_total_ready":{prefix:sum(row[f"{prefix}_status"]=="DELTA_READY" for row in latest.values()) for prefix in ("qoq","two_quarter","yoy")},
        "current_fresh_lifecycle_two_quarter_ready":sum(row["two_quarter_status"]=="DELTA_READY" for row in lifecycle),
        "current_fresh_valuation_two_quarter_ready":sum(row["two_quarter_status"]=="DELTA_READY" for row in valuation),
        "maximum_total_reconciliation_error":max((float(row["maximum_reconciliation_error"]) for row in package.total_rows if row["maximum_reconciliation_error"] is not None),default=None),
    }


def run_phase5c(*,analysis_db:Path,canonical_db:Path,provider_db:Path,market_db:Path,taxonomy_db:Path,destination:Path,as_of_date:str,score_model_fingerprint:str,lifecycle_model_fingerprint:str,valuation_model_fingerprint:str,delta_model_fingerprint:str,full_universe:bool=False,company_ids:Sequence[int]=(),apply:bool=False,create_online_copy:bool=False,verify_idempotency:bool=False,exercise_company_rebuilds:bool=False,exercise_failures:bool=False,output_dir:Path|None=None) -> dict[str,Any]:
    validate_request(analysis_db=analysis_db,canonical_db=canonical_db,provider_db=provider_db,market_db=market_db,taxonomy_db=taxonomy_db,destination=destination,score_model_fingerprint=score_model_fingerprint,lifecycle_model_fingerprint=lifecycle_model_fingerprint,valuation_model_fingerprint=valuation_model_fingerprint,delta_model_fingerprint=delta_model_fingerprint,full_universe=full_universe,company_ids=company_ids,apply=apply)
    source_paths={"analysis":analysis_db,"canonical":canonical_db,"provider":provider_db,"market":market_db,"taxonomy":taxonomy_db}
    before={name:database_evidence(path) for name,path in source_paths.items()}
    source=load_delta_source(ReadOnlyDeltaPaths(analysis_db,canonical_db),score_model_fingerprint=score_model_fingerprint,lifecycle_model_fingerprint=lifecycle_model_fingerprint,valuation_model_fingerprint=valuation_model_fingerprint)
    started=time.monotonic(); package=build_persistence_package(source); build_seconds=time.monotonic()-started
    report={"ok":True,"mode":"APPLY" if apply else "DRY_RUN","scope":"FULL" if full_universe else "COMPANY","company_ids":sorted(set(company_ids)),"destination":str(destination.resolve()),"package_fingerprint":package.package_fingerprint,"source_fingerprints":{"fundamental":package.fundamental_source_fingerprint,"lifecycle":package.lifecycle_source_fingerprint,"valuation":package.valuation_source_fingerprint},"result_fingerprints":{"fundamental":package.fundamental_result_fingerprint,"lifecycle":package.lifecycle_result_fingerprint,"valuation":package.valuation_result_fingerprint},"package_rows":{"total":len(package.total_rows),"component":len(package.component_rows),"lifecycle":len(package.lifecycle_rows),"valuation":len(package.valuation_rows)},"readiness_reconciliation":_readiness_reconciliation(package,as_of_date=as_of_date,source=source),"package_build_seconds":build_seconds,"production_sources_before":before}
    if not apply:
        after={name:database_evidence(path) for name,path in source_paths.items()}; report["production_sources_after"]=after
        report["destination_exists"]=destination.exists(); report["sources_unchanged"]={name:before[name]==after[name] for name in source_paths}
        if output_dir:
            if not output_dir.is_absolute(): raise ValueError("PHASE5C_OUTPUT_DIR_MUST_BE_ABSOLUTE")
            output_dir.mkdir(parents=True,exist_ok=True); (output_dir/"phase5c_dry_run_report.json").write_text(canonical_json(report)+"\n",encoding="ascii")
        return report
    if create_online_copy: sqlite_online_backup(analysis_db,destination)
    if not destination.is_file(): raise FileNotFoundError("PHASE5C_APPLY_DESTINATION_REQUIRED")
    report["destination_before"]=storage_evidence(destination)
    conn=sqlite3.connect(destination); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE"); ensure_schema(conn,applied_at_utc=f"{as_of_date}T23:59:59Z"); conn.commit()
        report["after_migration"]=storage_evidence(destination)
        started=time.monotonic(); first=apply_package(conn,package,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=company_ids); report["first_apply"]={**asdict(first),"duration_seconds":time.monotonic()-started}
        report["after_first_apply"]=storage_evidence(destination)
        report["reader_spot_checks"]=_spot_checks(conn,source)
        if verify_idempotency:
            before_noop=storage_evidence(destination); second=apply_package(conn,package,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=company_ids); after_noop=storage_evidence(destination)
            report["second_apply"]={**asdict(second),"database_size_unchanged":before_noop["size"]==after_noop["size"],"page_count_unchanged":before_noop["page_count"]==after_noop["page_count"]}
        target_company=next(iter(sorted(source.score_histories)))
        if exercise_company_rebuilds:
            report["company_storage_before"]=storage_evidence(destination)
            report["company_unchanged_rebuild"]=asdict(apply_package(conn,package,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,)))
            changed=_changed_source_package(package,marker="PHASE5C_CHANGED_COMPANY")
            report["company_changed_rebuild"]=asdict(apply_package(conn,changed,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,)))
            report["company_storage_after_change"]=storage_evidence(destination)
            report["company_changed_idempotent"]=asdict(apply_package(conn,changed,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,)))
            removed=_without_company(changed,target_company)
            report["company_removal"]=asdict(apply_package(conn,removed,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,)))
            report["company_storage_after_removal"]=storage_evidence(destination)
            report["company_restore"]=asdict(apply_package(conn,package,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,)))
            report["company_storage_after_restore"]=storage_evidence(destination)
        if exercise_failures:
            failures={}
            candidate=_changed_source_package(package,marker="PHASE5C_FAILURE")
            for stage in ("after_delete","after_total","after_component","after_lifecycle","after_valuation","metadata"):
                before_content=quick_check(conn,model_fingerprint=MODEL_FINGERPRINT)["content_fingerprint"]
                try: apply_package(conn,candidate,applied_at_utc=f"{as_of_date}T23:59:59Z",company_ids=(target_company,),inject_failure_at=stage)
                except RuntimeError as exc: failures[stage]={"error":str(exc),"previous_state_preserved":quick_check(conn,model_fingerprint=MODEL_FINGERPRINT)["content_fingerprint"]==before_content}
                else: raise RuntimeError(f"PHASE5C_FAILURE_INJECTION_DID_NOT_FAIL:{stage}")
            report["failure_injections"]=failures
        report["quick_check"]=quick_check(conn,model_fingerprint=MODEL_FINGERPRINT)
        if not report["quick_check"]["ok"]: raise RuntimeError(f"PHASE5C_QUICK_CHECK_FAILED:{report['quick_check']['details']}")
    finally: conn.close()
    report["destination_after"]=storage_evidence(destination)
    after={name:database_evidence(path) for name,path in source_paths.items()}; report["production_sources_after"]=after; report["sources_unchanged"]={name:before[name]==after[name] for name in source_paths}
    if output_dir:
        if not output_dir.is_absolute(): raise ValueError("PHASE5C_OUTPUT_DIR_MUST_BE_ABSOLUTE")
        output_dir.mkdir(parents=True,exist_ok=True); (output_dir/"phase5c_report.json").write_text(canonical_json(report)+"\n",encoding="ascii")
    return report
