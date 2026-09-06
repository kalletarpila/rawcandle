from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RELATIVE_V1

from . import contract, delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation
from .persistence import MODEL_MAP, PACKAGE_FINGERPRINT, apply_package, migrate_copy, physical_fingerprint, row_counts, validate_package
from .readers import ParallelModelRepository
from .rehearsal import calculate
from .reporting import render_company_report


ROOT=Path(__file__).resolve().parents[3]
PRODUCTION={"canonical":ROOT/"data/fundamentals_v4.db","analysis":ROOT/"data/fundamentals_analysis.db","market":ROOT/"data/osakedata.db","provider":ROOT/"data/fundamentals_provider.db","taxonomy":ROOT/"data/analysis.db"}
MARKER="phase9d_rehearsal_copy_marker"


def _hash_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(8*1024*1024),b""): digest.update(block)
    return digest.hexdigest()


def _sidecar(path: Path) -> dict[str,Any] | None:
    if not path.exists(): return None
    stat=path.stat(); return {"path":str(path.resolve()),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns,"sha256":_hash_file(path)}


def production_integrity() -> dict[str,Any]:
    output={}
    for name,path in sorted(PRODUCTION.items()):
        stat=path.stat(); conn=sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True); conn.row_factory=sqlite3.Row
        schema=[tuple(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name")]
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}; keys={"canonical":("v4_ttm_values","v4_quarter_financials"),"analysis":("score_result","lifecycle_revised_result","valuation_revised_result","fundamental_delta_result","diagnostic_flag_evaluation","relative_position_result"),"market":("ticker_meta","splits_data"),"provider":("provider_observation",),"taxonomy":("ec_entity","ec_membership","ec_ecosystem")}[name]
        output[name]={"path":str(path.resolve()),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns,"sha256":_hash_file(path),"schema_hash":contract.fingerprint(schema),"page_count":conn.execute("PRAGMA page_count").fetchone()[0],"freelist_count":conn.execute("PRAGMA freelist_count").fetchone()[0],"key_row_counts":{table:conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in keys if table in tables},"quick_check":conn.execute("PRAGMA quick_check").fetchone()[0],"foreign_key_check":[tuple(r) for r in conn.execute("PRAGMA foreign_key_check")],"wal":_sidecar(Path(str(path)+"-wal")),"shm":_sidecar(Path(str(path)+"-shm"))}; conn.close()
    return output


def compare_production_integrity(before: Mapping[str,Any], after: Mapping[str,Any]) -> dict[str,Any]:
    differences=[]
    allowed=[]
    for database in sorted(before):
        for field in sorted(before[database]):
            if before[database][field] == after[database][field]:
                continue
            if field == "shm":
                left=before[database][field]; right=after[database][field]
                stable_keys=("path","size","sha256")
                if left and right and all(left[key] == right[key] for key in stable_keys):
                    allowed.append({"database":database,"field":"shm.mtime_ns","before":left["mtime_ns"],"after":right["mtime_ns"],"reason":"SQLITE_READ_LOCK_METADATA_ONLY"})
                    continue
            differences.append({"database":database,"field":field,"before":before[database][field],"after":after[database][field]})
    return {"content_identical":not differences,"differences":differences,"allowed_read_lock_metadata_changes":allowed}


def create_copy(source: Path, destination: Path, created_at: str) -> None:
    if destination.exists() or destination.is_symlink(): raise FileExistsError(f"REHEARSAL_DESTINATION_MUST_NOT_EXIST:{destination}")
    destination.parent.mkdir(parents=True,exist_ok=True)
    source_conn=sqlite3.connect(f"file:{source.resolve()}?mode=ro",uri=True); target=sqlite3.connect(destination)
    source_conn.backup(target); target.execute(f"CREATE TABLE {MARKER}(singleton INTEGER PRIMARY KEY CHECK(singleton=1),source_path TEXT NOT NULL,created_at_utc TEXT NOT NULL)"); target.execute(f"INSERT INTO {MARKER} VALUES(1,?,?)",(str(source.resolve()),created_at)); target.commit(); target.close(); source_conn.close()


def validate_destination(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or path.resolve() in {p.resolve() for p in PRODUCTION.values()}: raise PermissionError("PHASE9D_PRODUCTION_OR_ALIAS_DESTINATION_BLOCKED")
    conn=sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True)
    marker=conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",(MARKER,)).fetchone(); expected=conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='score_result'").fetchone(); conn.close()
    if not marker or not expected: raise ValueError("PHASE9D_DESTINATION_NOT_VERIFIED_REHEARSAL_COPY")


def _write_json(path: Path,value: Any) -> None: path.write_text(json.dumps(value,sort_keys=True,indent=2,default=str,allow_nan=False)+"\n",encoding="utf-8")


def _write_csv(path: Path,rows: Sequence[Mapping[str,Any]]) -> None:
    fields=sorted({key for row in rows for key in row});
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def schema_inventory(conn: sqlite3.Connection) -> list[dict[str,Any]]:
    conn.row_factory=sqlite3.Row; return [dict(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name")]


def db_size(path: Path,conn: sqlite3.Connection) -> dict[str,int]:
    return {"main_bytes":path.stat().st_size,"wal_bytes":Path(str(path)+"-wal").stat().st_size if Path(str(path)+"-wal").exists() else 0,"page_count":conn.execute("PRAGMA page_count").fetchone()[0],"freelist_count":conn.execute("PRAGMA freelist_count").fetchone()[0]}


def deep_reconcile(conn: sqlite3.Connection, calculated: Mapping[str,Any]) -> dict[str,Any]:
    errors=[]
    persisted={(r[0],r[1]):(r[2],r[3]) for r in conn.execute("SELECT company_id,quarter_id,total_score,readiness_status FROM score_result WHERE model_fingerprint=?",(score.MODEL_FINGERPRINT,))}
    expected={(r["company_id"],r["quarter_id"]):(r["total_score"],r["readiness_status"]) for r in calculated["score_v2"]}
    if persisted!=expected: errors.append("score_totals")
    components={(r[0],r[1],r[2]):(r[3],r[4]) for r in conn.execute("SELECT r.company_id,r.quarter_id,c.component_name,c.component_score,c.evidence_json FROM score_component c JOIN score_result r USING(score_result_id) WHERE r.model_fingerprint=?",(score.MODEL_FINGERPRINT,))}
    expected_components={(r["company_id"],r["quarter_id"],c["component_name"]):(c["component_score"],c["evidence_json"]) for r in calculated["score_v2"] for c in r["components"]}
    if components!=expected_components: errors.append("score_components")
    life={(r[0],r[1]):tuple(r[2:]) for r in conn.execute("SELECT company_id,quarter_id,raw_state,final_state,lifecycle_status,startup_profile,final_startup_profile,reason_code,transition_reason,last_confirmed_state,candidate_state,candidate_count,revenue_growth_yoy_ttm,operating_margin_ttm,operating_margin_direction,fcf_margin_ttm FROM lifecycle_revised_result WHERE model_fingerprint=?",(lifecycle.MODEL_FINGERPRINT,))}
    expected_life={(k[0],k[1]):(v.raw_result.raw_state.value,v.final_state.value if v.final_state else None,v.lifecycle_status.value,v.raw_result.startup_profile.value if v.raw_result.startup_profile else None,v.final_startup_profile.value if v.final_startup_profile else None,v.raw_result.reason_code.value,v.transition_reason.value,v.last_confirmed_state.value if v.last_confirmed_state else None,v.candidate_state.value if v.candidate_state else None,v.candidate_count,v.raw_result.metrics.revenue_growth_yoy_ttm,v.raw_result.metrics.operating_margin_ttm,v.raw_result.metrics.operating_margin_direction,v.raw_result.metrics.fcf_margin_ttm) for k,v in calculated["lifecycle_v2"].items()}
    if life!=expected_life: errors.append("lifecycle")
    values={(r[0],r[1]):tuple(r[2:]) for r in conn.execute("SELECT company_id,quarter_id,total_valuation_score,valuation_status,reason_code,ttm_operating_income,operating_income_yield,operating_income_points,fcf_yield,fcf_points,earnings_yield,earnings_points FROM valuation_revised_result WHERE model_fingerprint=?",(valuation.MODEL_FINGERPRINT,))}
    expected_values={(k[0],k[1]):(v.total_valuation_score,v.valuation_status,v.reason_code,v.ttm_operating_income,v.operating_income_yield,v.operating_income_points,v.fcf_yield,v.fcf_points,v.earnings_yield,v.earnings_points) for k,v in calculated["valuation_v2"].items()}
    if values!=expected_values: errors.append("valuation")
    delta_fps={r[0] for r in conn.execute("SELECT r.engine_result_fingerprint FROM fundamental_delta_result r JOIN fundamental_delta_package p USING(package_id) WHERE p.model_fingerprint=?",(delta.MODEL_FINGERPRINT,))}
    if delta_fps!={r.result_fingerprint for r in calculated["delta_results"]}: errors.append("delta")
    relative_rows={(r[0],r[1],r[2],r[3]):tuple(r[4:]) for r in conn.execute("SELECT company_id,measure,peer_scope,peer_group_id,source_score,percentile,rank_low,rank_high,average_rank,peer_count,tie_count,result_status,reason_code FROM relative_position_result WHERE model_fingerprint=?",(relative_position.MODEL_FINGERPRINT,))}
    expected_relative={(r["company_id"],r["measure"].value,r["peer_scope"].value,r["peer_group_id"]):(r["score"],r["percentile"],r["rank_low"],r["rank_high"],r["average_rank"],r["peer_count"],r["tie_count"],r["status"].value,r["reason_code"]) for r in calculated["relative"].results}
    if relative_rows!=expected_relative: errors.append("relative")
    counts=row_counts(conn)
    if counts["diagnostic_evaluation"]!=len(calculated["diagnostics_full"]): errors.append("diagnostic_count")
    check=validate_package(conn)
    return {"ok":not errors,"differences":errors,"row_counts":counts,"package_check":check,"tolerance":1e-12}


def _relative_reconciliation(calculated: Mapping[str,Any], analysis: Path) -> list[dict[str,Any]]:
    def ev(v): return v.value if hasattr(v,"value") else v
    v2={(r["company_id"],ev(r["measure"]),ev(r["peer_scope"]),r["peer_group_id"]):r for r in calculated["relative"].results}
    conn=sqlite3.connect(f"file:{analysis.resolve()}?mode=ro",uri=True); conn.row_factory=sqlite3.Row; sid=conn.execute("SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?",(RELATIVE_V1,)).fetchone()[0]
    v1={(r["company_id"],r["measure"],r["peer_scope"],r["peer_group_id"]):dict(r) for r in conn.execute("SELECT * FROM relative_position_result WHERE snapshot_id=?",(sid,))}; conn.close()
    keys=sorted(v1.keys()^v2.keys())
    if not keys: return [{"difference":"NONE","v1_rows":len(v1),"v2_rows":len(v2),"explanation":"Phase 9C LFCR source-date omission corrected; eligibility keys now reconcile."}]
    return [{"difference":"V2_ONLY" if key in v2 else "V1_ONLY","company_id":key[0],"metric":key[1],"scope":key[2],"peer_group":key[3],"reason":(v2.get(key) or v1.get(key)).get("reason_code")} for key in keys]


def run(output: Path,destination: Path) -> dict[str,Any]:
    stamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"); output.mkdir(parents=True,exist_ok=True)
    before=production_integrity(); _write_json(output/"production_integrity_before.json",before)
    create_copy(PRODUCTION["analysis"],destination,stamp); validate_destination(destination)
    conn=sqlite3.connect(destination); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON"); before_schema=schema_inventory(conn); start=db_size(destination,conn); conn.close(); _write_json(output/"schema_object_inventory_before.json",before_schema)
    migration=migrate_copy(destination)
    paths={**PRODUCTION,"analysis":destination}; t=time.perf_counter(); calculated=calculate(paths); calculation_seconds=time.perf_counter()-t
    storage=[{"stage":"start",**start},{"stage":"schema",**db_size(destination,sqlite3.connect(destination))}]; stage_times={}; last=time.perf_counter()
    def stage(name: str,c: sqlite3.Connection) -> None:
        nonlocal last
        now=time.perf_counter(); stage_times[name]=now-last; last=now; storage.append({"stage":name,**db_size(destination,c)})
    conn=sqlite3.connect(destination); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON")
    first=apply_package(conn,calculated,applied_at=stamp,stage_callback=stage); first_size=db_size(destination,conn); second=apply_package(conn,calculated,applied_at=stamp); second_size=db_size(destination,conn); deep=deep_reconcile(conn,calculated)
    expected_counts={"score":50585,"score_component":354095,"lifecycle":50585,"valuation":50585,"delta":50585,"delta_component":354095,"diagnostic_endpoint":50585,"diagnostic_evaluation":354095,"relative_result":13737}
    if any(deep["row_counts"][name]!=count for name,count in expected_counts.items()): raise RuntimeError("PHASE9D_PRODUCTION_SHAPED_ROW_COUNT_MISMATCH")
    repo=ParallelModelRepository(conn); repo.assert_v2_bundle()
    reader_latency=[]
    for ticker in ("AMZN","GOOG","NVDA","CRMD","APD"):
        row=conn.execute("SELECT company_id FROM lifecycle_revised_result WHERE model_fingerprint=? AND ticker=? LIMIT 1",(lifecycle.MODEL_FINGERPRINT,ticker)).fetchone(); begin=time.perf_counter(); repo.score_history(int(row[0]),model_fingerprint=score.MODEL_FINGERPRINT); reader_latency.append({"ticker":ticker,"operation":"score_history","milliseconds":(time.perf_counter()-begin)*1000})
    reports=output/"company_snapshots_v2"; target_tickers=["AMZN","GOOG","NVDA","CRMD","APD","AAT","BNC"]
    candidate=conn.execute("SELECT ticker FROM lifecycle_revised_result WHERE model_fingerprint=? AND candidate_state IS NOT NULL ORDER BY company_id LIMIT 1",(lifecycle.MODEL_FINGERPRINT,)).fetchone();
    if candidate and candidate[0] not in target_tickers: target_tickers.append(candidate[0])
    reference=[]
    for ticker in target_tickers:
        row=conn.execute("SELECT company_id FROM lifecycle_revised_result WHERE model_fingerprint=? AND ticker=? ORDER BY fiscal_sequence DESC LIMIT 1",(lifecycle.MODEL_FINGERPRINT,ticker)).fetchone()
        if not row: continue
        cid=int(row[0]); render_company_report(conn,company_id=cid,market_db=PRODUCTION["market"],output=reports/f"{ticker}_operating_income_v2.md"); s=repo.score_current(cid,model_fingerprint=score.MODEL_FINGERPRINT); v=repo.valuation_current(cid,model_fingerprint=valuation.MODEL_FINGERPRINT); reference.append({"ticker":ticker,"company_id":cid,"score":s["total_score"],"score_status":s["readiness_status"],"valuation":v["total_valuation_score"],"valuation_status":v["valuation_status"]})
    report_failure_before=physical_fingerprint(conn)
    try: render_company_report(conn,company_id=-1,market_db=PRODUCTION["market"],output=reports/"invalid.md")
    except LookupError: report_failure=True
    else: report_failure=False
    report_failure_preserved=report_failure_before==physical_fingerprint(conn); final_schema=schema_inventory(conn); object_rows=[dict(r) for r in conn.execute("SELECT name,SUM(pgsize) used_bytes,COUNT(*) pages FROM dbstat GROUP BY name ORDER BY name")]; conn.close()
    failure_db=output/"failure_injection.db"; source=sqlite3.connect(destination); target=sqlite3.connect(failure_db); source.backup(target); source.close(); target.row_factory=sqlite3.Row; target.execute("PRAGMA foreign_keys=ON"); target.execute(f"DELETE FROM operating_income_v2_package_manifest"); target.commit(); baseline=physical_fingerprint(target)
    failures={}
    for point in ("score","lifecycle","valuation","delta","diagnostic","relative","activation"):
        try: apply_package(target,calculated,applied_at=stamp,inject_failure_at=point)
        except RuntimeError as exc: failures[point]={"error":str(exc),"previous_state_preserved":physical_fingerprint(target)==baseline}
    target.close(); failure_db.unlink()
    failures["wrong_model_fingerprint"]={"rejected":False}
    conn=sqlite3.connect(destination)
    try: ParallelModelRepository(conn).score_current(1,model_fingerprint="WRONG")
    except ValueError: failures["wrong_model_fingerprint"]={"rejected":True}
    conn.close(); failures["report_generation"]={"failed":report_failure,"persisted_state_preserved":report_failure_preserved}
    diagnostic_rows=[]
    counts=Counter((r["flag_name"],r["status"],r["reason_code"]) for r in calculated["diagnostics_full"])
    for (flag,status,reason),count in sorted(counts.items()): diagnostic_rows.append({"flag":flag,"status":status,"reason":reason,"count":count})
    _write_csv(output/"diagnostic_count_reconciliation.csv",diagnostic_rows); _write_csv(output/"relative_position_row_reconciliation.csv",_relative_reconciliation(calculated,PRODUCTION["analysis"])); _write_csv(output/"reference_company_checks.csv",reference); _write_csv(output/"storage_by_stage.csv",storage); _write_csv(output/"storage_by_object.csv",object_rows); _write_csv(output/"reader_latency.csv",reader_latency)
    v1_counts={table:before["analysis"]["key_row_counts"].get(table) for table in before["analysis"]["key_row_counts"]}; _write_csv(output/"v1_v2_row_counts.csv",[{"family":"V1",**v1_counts},{"family":"V2",**first.rows}])
    _write_json(output/"schema_object_inventory_after.json",final_schema); _write_json(output/"v2_package_manifest.json",{"family_version":contract.FAMILY_VERSION,"family_fingerprint":contract.FAMILY_FINGERPRINT,"persistence_fingerprint":PACKAGE_FINGERPRINT,"models":MODEL_MAP}); _write_json(output/"v2_persistence_fingerprints.json",{"economic":first.economic_result_fingerprint,"physical":first.physical_content_fingerprint,"package":PACKAGE_FINGERPRINT}); _write_json(output/"deep_replay_reconciliation.json",deep); _write_json(output/"failure_injection_results.json",failures)
    plan={"authorized":False,"phase":"9E","order":["online backups","additive migration","Score V2","Lifecycle V2","Valuation V2","Delta V2","Diagnostic V2","Relative V2","deep reconciliation","second no-op","coherent reader activation","Snapshot V2","Scheduler smoke","pipeline smoke without provider"]}; _write_json(output/"phase9e_production_plan.json",plan)
    (output/"recommended_phase9e_scope.md").write_text("# Recommended Phase 9E scope\n\nUse the locked package and runbook only after explicit production authorization. Preserve V1 and activate the complete V2 bundle atomically.\n",encoding="utf-8")
    (output/"wal_investigation.md").write_text(f"# WAL investigation\n\n`data/analysis.db-wal` belongs to `{PRODUCTION['taxonomy']}`. At preflight it was {before['taxonomy']['wal']['size'] if before['taxonomy']['wal'] else 0} bytes. No RawCandle/Scheduler process held it open. It contains committed taxonomy state newer than the main file and must be read through SQLite `mode=ro`; `immutable=1` was unsafe because it ignored WAL frames. No checkpoint, deletion, rename, truncation or process stop was performed. Snapshot readers now use WAL-aware read-only transactions.\n",encoding="utf-8")
    (output/"commands_run.txt").write_text("python3 -m rawcandle.fundamentals.operating_income_v2.phase9d --apply --destination <artifact>/rehearsal_analysis.db --output <artifact>\n",encoding="utf-8")
    after=production_integrity(); _write_json(output/"production_integrity_after.json",after)
    integrity_comparison=compare_production_integrity(before,after); _write_json(output/"production_integrity_comparison.json",integrity_comparison)
    if not integrity_comparison["content_identical"]: raise RuntimeError("PHASE9D_PRODUCTION_DATABASE_CHANGED")
    summary={"migration":migration,"calculation_seconds":calculation_seconds,"stage_seconds":stage_times,"first_apply":first.__dict__,"second_apply":second.__dict__,"start_size":start,"first_size":first_size,"second_size":second_size,"deep_replay":deep,"production_content_identical":True,"production_exact_evidence_identical":before==after,"production_allowed_read_lock_metadata_changes":integrity_comparison["allowed_read_lock_metadata_changes"],"reports":target_tickers}
    _write_json(output/"rehearsal_result.json",summary)
    (output/"PHASE9D_PERSISTENCE_REHEARSAL_REPORT.md").write_text(f"# Phase 9D Persistence Rehearsal\n\nFirst apply: `{first.outcome}` with {first.logical_changes} logical inserted rows. Second apply: `{second.outcome}` with {second.logical_changes} changes. Deep replay: `{deep['ok']}`. Database grew from {start['main_bytes']} to {first_size['main_bytes']} bytes; second-apply growth was {second_size['main_bytes']-first_size['main_bytes']} bytes. Diagnostic identity is 50,585 x 7 = 354,095. Relative Position reconciled to 13,737 rows after correcting LFCR source-date selection. Production database and sidecar content remained identical; any byte-identical SHM mtime change from SQLite read locks is listed separately. Phase 9E remains separately authorized.\n",encoding="utf-8")
    for path in output.glob("*.json"): json.loads(path.read_text())
    for path in output.glob("*.csv"):
        with path.open(newline="",encoding="utf-8") as handle: list(csv.reader(handle))
    return summary


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--apply",action="store_true"); parser.add_argument("--destination",type=Path); parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.apply:
        print(json.dumps({"mode":"DRY_RUN","writes":False,"required_apply_arguments":["--destination","--output"]},sort_keys=True)); return
    if args.destination is None or args.output is None: parser.error("--apply requires --destination and --output")
    output=args.output.resolve(); destination=args.destination.absolute()
    if destination.parent.resolve()!=output: raise PermissionError("PHASE9D_DESTINATION_MUST_BE_DIRECT_CHILD_OF_OUTPUT")
    print(json.dumps(run(output,destination),sort_keys=True,default=str))


if __name__=="__main__": main()
