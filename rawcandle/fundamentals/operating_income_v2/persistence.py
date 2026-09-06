from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.delta import persistence as delta_v1
from rawcandle.fundamentals.diagnostic_flags import persistence as diagnostic_v1

from . import contract, delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation


PRODUCTION_ANALYSIS_DB = Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db")
HISTORY_MODE = "REVISED_HISTORY"
DIAGNOSTIC_HISTORY_MODE = "CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_HISTORY"
PERSISTENCE_VERSION = "OPERATING_INCOME_V2_PARALLEL_PERSISTENCE_V1"
MANIFEST_TABLE = "operating_income_v2_package_manifest"
EVIDENCE_FIELD_TABLE = "operating_income_v2_diagnostic_evidence_field"
NON_NUMERIC_EVIDENCE = {
    "applicability_classification", "applicability_reason",
    "current_fiscal_quarter", "current_fiscal_year", "current_period_end",
    "current_source_available_date", "current_ttm_status",
    "fiscal_chain_consecutive", "prior_fiscal_quarter", "prior_fiscal_year",
    "prior_period_end", "prior_source_available_date", "prior_ttm_status",
    "valuation_reason", "valuation_status",
    "boundary_operator", "margin_operator", "trajectory_operator", "missing_inputs",
    "metric_value", "threshold", "current_revenue", "prior_revenue",
}

MODEL_MAP = {
    "score": (score.MODEL_VERSION, score.MODEL_FINGERPRINT),
    "lifecycle": (lifecycle.MODEL_VERSION, lifecycle.MODEL_FINGERPRINT),
    "valuation": (valuation.MODEL_VERSION, valuation.MODEL_FINGERPRINT),
    "delta": (delta.MODEL_VERSION, delta.MODEL_FINGERPRINT),
    "relative_position": (relative_position.MODEL_VERSION, relative_position.MODEL_FINGERPRINT),
    "diagnostic_flags": (diagnostic_flags.MODEL_VERSION, diagnostic_flags.MODEL_FINGERPRINT),
    "snapshot": (snapshot.MODEL_VERSION, snapshot.MODEL_FINGERPRINT),
}
PACKAGE_FINGERPRINT = contract.fingerprint({
    "persistence_version": PERSISTENCE_VERSION,
    "family_fingerprint": contract.FAMILY_FINGERPRINT,
    "models": MODEL_MAP,
    "tables": "existing versioned V1 tables plus additive operating-income columns",
})

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE}(
 family_fingerprint TEXT PRIMARY KEY,
 family_version TEXT NOT NULL,
 persistence_version TEXT NOT NULL,
 persistence_fingerprint TEXT NOT NULL,
 model_manifest_json TEXT NOT NULL,
 economic_result_fingerprint TEXT NOT NULL,
 physical_content_fingerprint TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('COMPLETE')),
 applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS {EVIDENCE_FIELD_TABLE}(
 model_fingerprint TEXT NOT NULL,
 flag_name TEXT NOT NULL,
 slot_number INTEGER NOT NULL CHECK(slot_number BETWEEN 1 AND 16),
 field_name TEXT NOT NULL,
 PRIMARY KEY(model_fingerprint,flag_name,slot_number),
 UNIQUE(model_fingerprint,flag_name,field_name)
) WITHOUT ROWID;
"""


@dataclass(frozen=True)
class ApplyReport:
    outcome: str
    economic_result_fingerprint: str
    physical_content_fingerprint: str
    rows: dict[str, int]
    logical_changes: int


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


def _enum(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _id(value: Any) -> int:
    return int(_hash(value)[:15], 16)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_SQL.split(";"):
        if statement.strip():
            conn.execute(statement)
    _add_column(conn, "lifecycle_revised_result", "operating_margin_ttm REAL")
    _add_column(conn, "lifecycle_revised_result", "operating_margin_direction REAL")
    _add_column(conn, "valuation_revised_result", "ttm_operating_income REAL")
    _add_column(conn, "valuation_revised_result", "operating_income_yield REAL")
    _add_column(conn, "valuation_revised_result", "operating_income_points REAL")


def migrate_copy(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not path.is_absolute() or path.is_symlink() or resolved == PRODUCTION_ANALYSIS_DB.resolve():
        raise PermissionError("OPERATING_INCOME_V2_PRODUCTION_OR_ALIAS_MIGRATION_BLOCKED")
    with sqlite3.connect(resolved) as conn:
        before = tuple(conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"))
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        conn.commit()
        after = tuple(conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"))
        return {"objects_before": len(before), "objects_after": len(after), "objects_added": len(after)-len(before), "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0]}


def economic_fingerprint(calculated: Mapping[str, Any]) -> str:
    return _hash({
        "score": [(r["company_id"], r["quarter_id"], r["total_score"], r["readiness_status"], [(c["component_name"], c["component_score"], c["evidence_json"]) for c in r["components"]]) for r in calculated["score_v2"]],
        "lifecycle": [(k, asdict(calculated["lifecycle_v2"][k])) for k in sorted(calculated["lifecycle_v2"])],
        "valuation": [(k, calculated["valuation_v2"][k].to_dict()) for k in sorted(calculated["valuation_v2"])],
        "delta": [r.to_dict() for r in calculated["delta_results"]],
        "diagnostic": calculated["diagnostics_full"],
        "relative": calculated["relative"].to_dict(),
    })


def validate_calculated_package(calculated: Mapping[str, Any]) -> None:
    score_keys=set()
    for row in calculated["score_v2"]:
        key=(int(row["company_id"]),int(row["quarter_id"])); score_keys.add(key)
        components=row["components"]
        if len(components)!=7 or {item["component_name"] for item in components}!=set(contract.COMPONENTS):
            raise ValueError(f"OPERATING_INCOME_V2_SCORE_COMPONENT_CONTRACT:{key}")
        observed=[item["component_score"] for item in components]
        if row["total_score"] is not None and abs(float(row["total_score"])-sum(float(value) for value in observed if value is not None))>1e-12:
            raise ValueError(f"OPERATING_INCOME_V2_SCORE_TOTAL_RECONCILIATION:{key}")
    layer_keys={
        "lifecycle":set(calculated["lifecycle_v2"]),
        "valuation":set(calculated["valuation_v2"]),
        "delta":{(int(row.company_id),int(row.current_observation_id)) for row in calculated["delta_results"]},
    }
    diagnostic_groups={}
    for row in calculated["diagnostics_full"]:
        key=(int(row["company_id"]),int(row["quarter_id"]))
        diagnostic_groups.setdefault(key,set()).add(row["flag_name"])
        if row["model_fingerprint"]!=diagnostic_flags.MODEL_FINGERPRINT:
            raise ValueError(f"OPERATING_INCOME_V2_DIAGNOSTIC_MODEL_MISMATCH:{key}")
    layer_keys["diagnostic"]=set(diagnostic_groups)
    for key,names in diagnostic_groups.items():
        if len(names)!=7:
            raise ValueError(f"OPERATING_INCOME_V2_DIAGNOSTIC_FLAG_CONTRACT:{key}")
    mismatches=[name for name,keys in layer_keys.items() if keys!=score_keys]
    if mismatches:
        raise ValueError("OPERATING_INCOME_V2_ENDPOINT_SET_MISMATCH:"+",".join(mismatches))


def _existing_manifest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    if MANIFEST_TABLE not in {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}:
        return None
    return conn.execute(f"SELECT * FROM {MANIFEST_TABLE} WHERE family_fingerprint=?", (contract.FAMILY_FINGERPRINT,)).fetchone()


def _score_rows(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM score_result WHERE model_fingerprint=?", (score.MODEL_FINGERPRINT,)).fetchone()[0])


def _apply_score(conn: sqlite3.Connection, rows: Sequence[Mapping[str, Any]], applied_at: str) -> None:
    conn.execute("DELETE FROM score_result WHERE model_fingerprint=?", (score.MODEL_FINGERPRINT,))
    conn.execute("DELETE FROM analysis_model_run WHERE model_fingerprint=?", (score.MODEL_FINGERPRINT,))
    run_id = f"phase9d-{score.MODEL_FINGERPRINT[:20]}"
    conn.execute("INSERT INTO analysis_model_run(run_id,model_type,model_version,model_fingerprint,generated_at_utc,status,metadata_json) VALUES(?,?,?,?,?,'COMPLETE',?)", (run_id, "SCORE", score.MODEL_VERSION, score.MODEL_FINGERPRINT, applied_at, json.dumps({"family_fingerprint": contract.FAMILY_FINGERPRINT}, sort_keys=True)))
    for row in rows:
        cursor = conn.execute("INSERT INTO score_result(company_id,quarter_id,model_version,model_fingerprint,total_score,readiness_status,missing_input_reason,generated_at_utc,run_id) VALUES(?,?,?,?,?,?,?,?,?)", (row["company_id"],row["quarter_id"],score.MODEL_VERSION,score.MODEL_FINGERPRINT,row["total_score"],row["readiness_status"],row["missing_input_reason"],applied_at,run_id))
        result_id = int(cursor.lastrowid)
        conn.executemany("INSERT INTO score_component(score_result_id,component_name,component_score,evidence_json) VALUES(?,?,?,?)", [(result_id,c["component_name"],c["component_score"],c["evidence_json"]) for c in row["components"]])


def _apply_lifecycle(conn: sqlite3.Connection, calculated: Mapping[str, Any], applied_at: str) -> None:
    conn.execute("DELETE FROM lifecycle_revised_result WHERE model_fingerprint=?", (lifecycle.MODEL_FINGERPRINT,))
    ttm = {(int(r["company_id"]),int(r["endpoint_quarter_id"])):r for r in calculated["rows"]}
    columns = ("company_id","security_id","ticker","quarter_id","fiscal_year","fiscal_quarter","fiscal_sequence","period_end","source_available_date","history_mode","model_version","model_fingerprint","source_input_fingerprint","raw_state","final_state","lifecycle_status","startup_profile","final_startup_profile","reason_code","transition_reason","missing_inputs_json","last_confirmed_state","candidate_state","candidate_count","revenue_growth_yoy_ttm","operating_margin_ttm","operating_margin_direction","fcf_margin_ttm","evidence_json","generated_at_utc")
    values=[]
    for key in sorted(calculated["lifecycle_v2"]):
        result=calculated["lifecycle_v2"][key]; raw=result.raw_result; source=ttm[key]
        row={"company_id":key[0],"security_id":source.get("security_id"),"ticker":source.get("ticker"),"quarter_id":key[1],"fiscal_year":raw.observation.endpoint_fiscal_year,"fiscal_quarter":raw.observation.endpoint_fiscal_quarter,"fiscal_sequence":raw.observation.endpoint_fiscal_year*4+int(raw.observation.endpoint_fiscal_quarter[1]),"period_end":raw.observation.period_end,"source_available_date":raw.observation.source_available_date,"history_mode":HISTORY_MODE,"model_version":lifecycle.MODEL_VERSION,"model_fingerprint":lifecycle.MODEL_FINGERPRINT,"source_input_fingerprint":source.get("output_fingerprint") or _hash(asdict(raw.observation)),"raw_state":raw.raw_state.value,"final_state":result.final_state.value if result.final_state else None,"lifecycle_status":result.lifecycle_status.value,"startup_profile":raw.startup_profile.value if raw.startup_profile else None,"final_startup_profile":result.final_startup_profile.value if result.final_startup_profile else None,"reason_code":raw.reason_code.value,"transition_reason":result.transition_reason.value,"missing_inputs_json":json.dumps(raw.missing_inputs,separators=(",",":")),"last_confirmed_state":result.last_confirmed_state.value if result.last_confirmed_state else None,"candidate_state":result.candidate_state.value if result.candidate_state else None,"candidate_count":result.candidate_count,"revenue_growth_yoy_ttm":raw.metrics.revenue_growth_yoy_ttm,"operating_margin_ttm":raw.metrics.operating_margin_ttm,"operating_margin_direction":raw.metrics.operating_margin_direction,"fcf_margin_ttm":raw.metrics.fcf_margin_ttm,"evidence_json":json.dumps({"ttm_model_version":raw.observation.ttm_model_version,"lag4_chain_valid":raw.observation.lag4_chain_valid,"input_quarter_revenues":raw.observation.input_quarter_revenues},sort_keys=True,separators=(",",":")),"generated_at_utc":applied_at}
        values.append([row[c] for c in columns])
    conn.executemany(f"INSERT INTO lifecycle_revised_result({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", values)


def _apply_valuation(conn: sqlite3.Connection, calculated: Mapping[str, Any], applied_at: str) -> None:
    conn.execute("DELETE FROM valuation_revised_result WHERE model_fingerprint=?", (valuation.MODEL_FINGERPRINT,))
    source_old={(int(r["company_id"]),int(r["quarter_id"])):r for r in calculated.get("valuation_v1_rows",())}
    columns=("company_id","security_id","ticker","security_active","fiscal_year","fiscal_quarter","fiscal_sequence","quarter_id","period_end","fundamental_available_date","price_date","price_age_calendar_days","selected_price","shares_outstanding","market_cap","cash","total_debt","net_debt","enterprise_value","ttm_operating_income","ttm_free_cashflow","ttm_net_income_common","operating_income_yield","operating_income_points","fcf_yield","fcf_points","earnings_yield","earnings_points","total_valuation_score","valuation_status","reason_code","applicability_classification","sector","industry","model_version","model_fingerprint","source_fingerprint","engine_result_fingerprint","result_fingerprint","history_mode","calculated_at_utc")
    values=[]
    for key in sorted(calculated["valuation_v2"]):
        result=calculated["valuation_v2"][key]; d=result.to_dict(); base=source_old.get(key,{})
        applicability=valuation.classify_applicability(base.get("sector"),base.get("industry")); classification="SUPPORTED" if applicability.supported is True else "NOT_APPLICABLE" if applicability.supported is False else "NOT_READY"
        row={**d,"security_active":base.get("security_active"),"fiscal_sequence":d["fiscal_year"]*4+int(d["fiscal_quarter"][1]),"applicability_classification":classification,"sector":base.get("sector"),"industry":base.get("industry"),"source_fingerprint":_hash({"quarter":key,"source":base.get("source_fingerprint"),"operating_income":d["ttm_operating_income"]}),"engine_result_fingerprint":d["result_fingerprint"],"history_mode":HISTORY_MODE,"calculated_at_utc":applied_at}
        row["result_fingerprint"]=_hash({c:row.get(c) for c in columns if c not in {"result_fingerprint","calculated_at_utc"}})
        values.append([row.get(c) for c in columns])
    conn.executemany(f"INSERT INTO valuation_revised_result({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",values)


def _code_id(conn: sqlite3.Connection, table: str, id_column: str, text_column: str, text: str) -> int:
    row=conn.execute(f"SELECT {id_column} FROM {table} WHERE {text_column}=?",(text,)).fetchone()
    if row is not None: return int(row[0])
    value=int(conn.execute(f"SELECT COALESCE(MAX({id_column}),0)+1 FROM {table}").fetchone()[0])
    conn.execute(f"INSERT INTO {table}({id_column},{text_column}) VALUES(?,?)",(value,text)); return value


def _apply_delta(conn: sqlite3.Connection, calculated: Mapping[str, Any], applied_at: str) -> None:
    package_id=_id((delta.MODEL_FINGERPRINT,HISTORY_MODE)); existing=conn.execute(f"SELECT package_id FROM {delta_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",(delta.MODEL_FINGERPRINT,)).fetchone()
    if existing:
        conn.execute(f"DELETE FROM {delta_v1.COMPONENT_TABLE} WHERE endpoint_id IN (SELECT endpoint_id FROM {delta_v1.TOTAL_TABLE} WHERE package_id=?)",(existing[0],))
        conn.execute(f"DELETE FROM {delta_v1.TOTAL_TABLE} WHERE package_id=?",(existing[0],))
        conn.execute(f"DELETE FROM {delta_v1.PACKAGE_TABLE} WHERE package_id=?",(existing[0],))
    score_ids={(int(r[0]),int(r[1])):int(r[2]) for r in conn.execute("SELECT company_id,quarter_id,score_result_id FROM score_result WHERE model_fingerprint=?",(score.MODEL_FINGERPRINT,))}
    component_ids={}
    for name,maximum in zip(contract.COMPONENTS,(20.,15.,15.,15.,15.,10.,10.)):
        row=conn.execute(f"SELECT component_id,maximum_points FROM {delta_v1.COMPONENT_TYPE_TABLE} WHERE component_name=?",(name,)).fetchone()
        if row is None:
            cid=int(conn.execute(f"SELECT COALESCE(MAX(component_id),0)+1 FROM {delta_v1.COMPONENT_TYPE_TABLE}").fetchone()[0]); conn.execute(f"INSERT INTO {delta_v1.COMPONENT_TYPE_TABLE} VALUES(?,?,?)",(cid,name,maximum))
        else: cid=int(row[0]); assert float(row[1])==maximum
        component_ids[name]=cid
    statuses={}; reasons={}
    for result in calculated["delta_results"]:
        for h in result.horizons:
            statuses[_enum(h["status"])]=None; reasons[h["reason_code"]]=None
            for c in h["components"]: statuses[_enum(c["status"])]=None; reasons[c["reason_code"]]=None
    for value in statuses: statuses[value]=_code_id(conn,delta_v1.STATUS_TABLE,"status_id","status_text",value)
    for value in reasons: reasons[value]=_code_id(conn,delta_v1.REASON_TABLE,"reason_id","reason_text",value)
    total_rows=[]; component_rows=[]
    for result in calculated["delta_results"]:
        key=(result.company_id,int(result.current_observation_id)); endpoint_id=_id((delta.MODEL_FINGERPRINT,result.company_id,result.current_fiscal_sequence)); horizons={_enum(h["horizon"]):h for h in result.horizons}
        def sid(h): return score_ids.get((result.company_id,int(h["prior_observation_id"]))) if h["prior_observation_id"] else None
        ready=[abs(float(h["reconciliation_error"])) for h in result.horizons if h["reconciliation_error"] is not None]
        vals=[endpoint_id,package_id,result.company_id,result.current_fiscal_year,int(result.current_fiscal_quarter[1]),result.current_fiscal_sequence,result.current_available_date,score_ids[key]]
        for name in ("QOQ","TWO_QUARTER","YOY"):
            h=horizons[name]; vals.extend((sid(h),h["delta_points"],statuses[_enum(h["status"])],reasons[h["reason_code"]]))
        vals.extend((1 if ready else 0,max(ready) if ready else None,result.result_fingerprint,_hash(vals)))
        total_rows.append(vals)
        current_components={c["component_name"]:c for c in horizons["QOQ"]["components"]}
        for cname in contract.COMPONENTS:
            row=[endpoint_id,component_ids[cname],current_components[cname]["current_points"]]
            for hname in ("QOQ","TWO_QUARTER","YOY"):
                c=next(x for x in horizons[hname]["components"] if x["component_name"]==cname); row.extend((c["prior_points"],c["delta_points"],statuses[_enum(c["status"])],reasons[c["reason_code"]]))
            row.append(_hash(row)); component_rows.append(row)
    economic=_hash([r.result_fingerprint for r in calculated["delta_results"]]); physical=_hash((total_rows,component_rows))
    values=(package_id,delta_v1.PERSISTENCE_VERSION,delta_v1.LAYOUT_FINGERPRINT,delta.MODEL_VERSION,delta.MODEL_FINGERPRINT,delta_v1.SEMANTIC_MODE,HISTORY_MODE,score.MODEL_FINGERPRINT,_hash(calculated["score_v2"]),_hash([r.result_fingerprint for r in calculated["delta_results"]]),lifecycle.MODEL_FINGERPRINT,_hash("lifecycle-source"),_hash([asdict(x) for x in calculated["lifecycle_v2"].values()]),valuation.MODEL_FINGERPRINT,_hash("valuation-source"),_hash([x.result_fingerprint for x in calculated["valuation_v2"].values()]),economic,physical,len(total_rows),len(component_rows),applied_at)
    conn.execute(f"INSERT INTO {delta_v1.PACKAGE_TABLE} VALUES({','.join('?' for _ in values)})",values)
    conn.executemany(f"INSERT INTO {delta_v1.TOTAL_TABLE} VALUES({','.join('?' for _ in range(24))})",total_rows)
    conn.executemany(f"INSERT INTO {delta_v1.COMPONENT_TABLE} VALUES({','.join('?' for _ in range(16))})",component_rows)


def _apply_diagnostics(conn: sqlite3.Connection, calculated: Mapping[str, Any], applied_at: str) -> None:
    pid=_id((diagnostic_flags.MODEL_FINGERPRINT,DIAGNOSTIC_HISTORY_MODE)); old=conn.execute(f"SELECT package_id FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",(diagnostic_flags.MODEL_FINGERPRINT,)).fetchone()
    if old:
        conn.execute(f"DELETE FROM {diagnostic_v1.EVALUATION_TABLE} WHERE endpoint_id IN (SELECT endpoint_id FROM {diagnostic_v1.ENDPOINT_TABLE} WHERE package_id=?)",(old[0],))
        conn.execute(f"DELETE FROM {diagnostic_v1.ENDPOINT_TABLE} WHERE package_id=?",(old[0],))
        conn.execute(f"DELETE FROM {diagnostic_v1.PACKAGE_TABLE} WHERE package_id=?",(old[0],))
    grouped={}
    for row in calculated["diagnostics_full"]: grouped.setdefault((row["company_id"],row["quarter_id"]),[]).append(row)
    ttm={(int(r["company_id"]),int(r["endpoint_quarter_id"])):r for r in calculated["rows"]}
    flag_ids={}; status_ids={}; reason_ids={}; source_ids={}
    for row in calculated["diagnostics_full"]:
        flag_ids[row["flag_name"]]=_code_id(conn,diagnostic_v1.FLAG_TABLE,"flag_id","flag_name",row["flag_name"])
        status_ids[row["status"]]=_code_id(conn,diagnostic_v1.STATUS_TABLE,"status_id","status_text",row["status"])
        reason_ids[row["reason_code"]]=_code_id(conn,diagnostic_v1.REASON_TABLE,"reason_id","reason_text",row["reason_code"])
    endpoint_rows=[]; evaluation_rows=[]
    evidence_layout={flag:tuple(diagnostic_flags._evidence_name(name) for name in diagnostic_v1.EVIDENCE_FIELDS[flag]) for flag in sorted(flag_ids)}
    boolean_layout={flag:tuple(diagnostic_flags._evidence_name(name) for name in diagnostic_v1.BOOLEAN_FIELDS.get(flag,())) for flag in sorted(flag_ids)}
    for key in sorted(grouped):
        source=ttm[key]; sequence=int(source["endpoint_fiscal_year"])*4+int(str(source["endpoint_fiscal_quarter"])[1]); eid=_id((diagnostic_flags.MODEL_FINGERPRINT,key[0],sequence)); source_status="TTM_READY" if source.get("core_ttm_ready") else "TTM_NOT_READY"; source_ids[source_status]=_code_id(conn,diagnostic_v1.SOURCE_STATUS_TABLE,"source_status_id","source_status_text",source_status)
        endpoint_rows.append((eid,pid,key[0],key[1],source["endpoint_fiscal_year"],int(str(source["endpoint_fiscal_quarter"])[1]),sequence,source["period_end"],source.get("ttm_source_available_date"),source.get("ttm_source_available_date"),source_ids[source_status],_hash((key,source_status))))
        assert len(grouped[key])==7
        for row in sorted(grouped[key],key=lambda x:x["flag_name"]):
            fields=evidence_layout[row["flag_name"]]
            boolean_fields=boolean_layout[row["flag_name"]]
            unknown=set(row["evidence"])-set(fields)-set(boolean_fields)-NON_NUMERIC_EVIDENCE
            if unknown: raise ValueError(f"OPERATING_INCOME_V2_DIAGNOSTIC_EVIDENCE_UNMAPPED:{row['flag_name']}:{sorted(unknown)}")
            numbers=[row["evidence"].get(name) for name in fields]+[None]*(16-len(fields))
            bool_mask=sum((1<<index) for index,name in enumerate(boolean_fields) if row["evidence"].get(name) is True)
            application=None
            evaluation=[eid,flag_ids[row["flag_name"]],status_ids[row["status"]],reason_ids[row["reason_code"]],application,row["comparison_quarter_id"],row["effective_available_date"],None if row["triggered"] is None else int(row["triggered"]),bool_mask,*numbers]
            evaluation.append(_hash(evaluation)); evaluation_rows.append(evaluation)
    economic=_hash(calculated["diagnostics_full"]); physical=_hash((endpoint_rows,evaluation_rows))
    values=(pid,PERSISTENCE_VERSION,_hash(evidence_layout),diagnostic_flags.MODEL_VERSION,diagnostic_flags.MODEL_FINGERPRINT,"CURRENTLY_REVISED_DIAGNOSTIC_FLAGS",DIAGNOSTIC_HISTORY_MODE,diagnostic_flags.EVIDENCE_SCHEMA_VERSION,_hash("diagnostic-source"),economic,physical,len(endpoint_rows),len(evaluation_rows),applied_at)
    conn.execute(f"INSERT INTO {diagnostic_v1.PACKAGE_TABLE} VALUES({','.join('?' for _ in values)})",values)
    conn.executemany(f"INSERT INTO {diagnostic_v1.ENDPOINT_TABLE} VALUES({','.join('?' for _ in range(12))})",endpoint_rows)
    conn.executemany(f"INSERT INTO {diagnostic_v1.EVALUATION_TABLE} VALUES({','.join('?' for _ in range(26))})",evaluation_rows)
    conn.execute(f"DELETE FROM {EVIDENCE_FIELD_TABLE} WHERE model_fingerprint=?",(diagnostic_flags.MODEL_FINGERPRINT,))
    conn.executemany(f"INSERT INTO {EVIDENCE_FIELD_TABLE} VALUES(?,?,?,?)",[(diagnostic_flags.MODEL_FINGERPRINT,flag,index+1,name) for flag,names in sorted(evidence_layout.items()) for index,name in enumerate(names)])


def _apply_relative(conn: sqlite3.Connection, calculated: Mapping[str, Any], applied_at: str) -> None:
    value=calculated["relative"]; content=_hash(value.to_dict()); snapshot_id=_hash((relative_position.MODEL_FINGERPRINT,content))
    conn.execute("DELETE FROM relative_position_active_snapshot WHERE model_fingerprint=?",(relative_position.MODEL_FINGERPRINT,))
    conn.execute("DELETE FROM relative_position_snapshot WHERE model_fingerprint=?",(relative_position.MODEL_FINGERPRINT,))
    results=[]
    for r in value.results:
        results.append((snapshot_id,r["company_id"],r["security_id"],r["ticker"],_enum(r["measure"]),_enum(r["peer_scope"]),r["peer_group_id"],r["source_observation_id"],r["source_observation_date"],r["score"],r["percentile"],r["rank_low"],r["rank_high"],r["average_rank"],r["peer_count"],r["tie_count"],_enum(r["status"]),r["reason_code"],relative_position.MODEL_VERSION,relative_position.MODEL_FINGERPRINT))
    coverage=[]
    for r in value.coverage:
        coverage.append((snapshot_id,r["source_observation_id"],r["company_id"],_enum(r["measure"]),_enum(r["peer_scope"]),r["peer_group_id"] or "",_enum(r["status"]),r["reason_code"],r["peer_count"]))
    conn.execute("INSERT INTO relative_position_snapshot VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(snapshot_id,relative_position.MODEL_VERSION,relative_position.MODEL_FINGERPRINT,"CURRENT_REVISED_SNAPSHOT",value.snapshot_date,value.source_fingerprint,content,value.result_fingerprint,"COMPLETE",len(results),len(coverage),sum(r[16]=="RELATIVE_POSITION_READY" for r in results),applied_at,applied_at))
    conn.executemany("INSERT INTO relative_position_result(snapshot_id,company_id,security_id,ticker,measure,peer_scope,peer_group_id,source_observation_id,source_observation_date,source_score,percentile,rank_low,rank_high,average_rank,peer_count,tie_count,result_status,reason_code,model_version,model_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",results)
    conn.executemany("INSERT INTO relative_position_coverage(snapshot_id,source_observation_id,company_id,measure,peer_scope,peer_group_id,coverage_status,reason_code,peer_count) VALUES(?,?,?,?,?,?,?,?,?)",coverage)
    conn.execute("INSERT INTO relative_position_active_snapshot VALUES(?,?,?)",(relative_position.MODEL_FINGERPRINT,snapshot_id,applied_at))


def physical_fingerprint(conn: sqlite3.Connection) -> str:
    digest = hashlib.sha256()

    def consume(name: str, sql: str, params: tuple[Any, ...]) -> None:
        digest.update(name.encode())
        for row in conn.execute(sql, params):
            digest.update(json.dumps(tuple(row), separators=(",", ":"), allow_nan=False, default=str).encode())
            digest.update(b"\n")

    consume("score", "SELECT company_id,quarter_id,total_score,readiness_status,missing_input_reason FROM score_result WHERE model_fingerprint=? ORDER BY company_id,quarter_id", (score.MODEL_FINGERPRINT,))
    consume("score_component", "SELECT r.company_id,r.quarter_id,c.component_name,c.component_score,c.evidence_json FROM score_component c JOIN score_result r USING(score_result_id) WHERE r.model_fingerprint=? ORDER BY r.company_id,r.quarter_id,c.component_name", (score.MODEL_FINGERPRINT,))
    consume("lifecycle", "SELECT company_id,quarter_id,raw_state,final_state,lifecycle_status,reason_code,last_confirmed_state,candidate_state,candidate_count,operating_margin_ttm,operating_margin_direction,evidence_json FROM lifecycle_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", (lifecycle.MODEL_FINGERPRINT,))
    consume("valuation", "SELECT company_id,quarter_id,total_valuation_score,valuation_status,reason_code,ttm_operating_income,operating_income_yield,operating_income_points,fcf_yield,fcf_points,earnings_yield,earnings_points,result_fingerprint FROM valuation_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", (valuation.MODEL_FINGERPRINT,))
    consume("delta_package", f"SELECT package_id,persistence_version,layout_fingerprint,model_version,model_fingerprint,semantic_mode,history_mode,score_model_fingerprint,fundamental_source_fingerprint,fundamental_result_fingerprint,lifecycle_model_fingerprint,lifecycle_source_fingerprint,lifecycle_result_fingerprint,valuation_model_fingerprint,valuation_source_fingerprint,valuation_result_fingerprint,economic_package_fingerprint,physical_content_fingerprint,total_row_count,component_row_count FROM {delta_v1.PACKAGE_TABLE} WHERE model_fingerprint=?", (delta.MODEL_FINGERPRINT,))
    consume("delta_result", f"SELECT r.* FROM {delta_v1.TOTAL_TABLE} r JOIN {delta_v1.PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint=? ORDER BY r.company_id,r.fiscal_sequence", (delta.MODEL_FINGERPRINT,))
    consume("delta_component", f"SELECT c.* FROM {delta_v1.COMPONENT_TABLE} c JOIN {delta_v1.TOTAL_TABLE} r USING(endpoint_id) JOIN {delta_v1.PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint=? ORDER BY r.company_id,r.fiscal_sequence,c.component_id", (delta.MODEL_FINGERPRINT,))
    consume("diagnostic_package", f"SELECT package_id,persistence_version,layout_fingerprint,model_version,model_fingerprint,semantic_mode,history_mode,evidence_schema_version,source_fingerprint,economic_result_fingerprint,physical_content_fingerprint,endpoint_count,evaluation_count FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?", (diagnostic_flags.MODEL_FINGERPRINT,))
    consume("diagnostic_endpoint", f"SELECT e.* FROM {diagnostic_v1.ENDPOINT_TABLE} e JOIN {diagnostic_v1.PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint=? ORDER BY e.company_id,e.fiscal_sequence", (diagnostic_flags.MODEL_FINGERPRINT,))
    consume("diagnostic_evaluation", f"SELECT v.* FROM {diagnostic_v1.EVALUATION_TABLE} v JOIN {diagnostic_v1.ENDPOINT_TABLE} e USING(endpoint_id) JOIN {diagnostic_v1.PACKAGE_TABLE} p USING(package_id) WHERE p.model_fingerprint=? ORDER BY e.company_id,e.fiscal_sequence,v.flag_id", (diagnostic_flags.MODEL_FINGERPRINT,))
    consume("diagnostic_evidence_layout", f"SELECT * FROM {EVIDENCE_FIELD_TABLE} WHERE model_fingerprint=? ORDER BY flag_name,slot_number", (diagnostic_flags.MODEL_FINGERPRINT,))
    consume("relative_snapshot", "SELECT snapshot_id,model_version,model_fingerprint,semantic_mode,snapshot_date,calculation_source_fingerprint,source_content_fingerprint,result_fingerprint,status,result_row_count,coverage_row_count,ready_row_count FROM relative_position_snapshot WHERE model_fingerprint=? ORDER BY snapshot_id", (relative_position.MODEL_FINGERPRINT,))
    consume("relative_result", "SELECT r.* FROM relative_position_result r JOIN relative_position_snapshot s USING(snapshot_id) WHERE s.model_fingerprint=? ORDER BY r.measure,r.peer_scope,r.peer_group_id,r.company_id", (relative_position.MODEL_FINGERPRINT,))
    consume("relative_coverage", "SELECT c.* FROM relative_position_coverage c JOIN relative_position_snapshot s USING(snapshot_id) WHERE s.model_fingerprint=? ORDER BY c.measure,c.peer_scope,c.peer_group_id,c.company_id", (relative_position.MODEL_FINGERPRINT,))
    consume("relative_active", "SELECT model_fingerprint,snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?", (relative_position.MODEL_FINGERPRINT,))
    return digest.hexdigest()


def row_counts(conn: sqlite3.Connection) -> dict[str,int]:
    delta_pid=conn.execute(f"SELECT package_id FROM {delta_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",(delta.MODEL_FINGERPRINT,)).fetchone(); diag_pid=conn.execute(f"SELECT package_id FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",(diagnostic_flags.MODEL_FINGERPRINT,)).fetchone(); snap=conn.execute("SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?",(relative_position.MODEL_FINGERPRINT,)).fetchone()
    return {"score":_score_rows(conn),"score_component":int(conn.execute("SELECT COUNT(*) FROM score_component c JOIN score_result r USING(score_result_id) WHERE r.model_fingerprint=?",(score.MODEL_FINGERPRINT,)).fetchone()[0]),"lifecycle":int(conn.execute("SELECT COUNT(*) FROM lifecycle_revised_result WHERE model_fingerprint=?",(lifecycle.MODEL_FINGERPRINT,)).fetchone()[0]),"valuation":int(conn.execute("SELECT COUNT(*) FROM valuation_revised_result WHERE model_fingerprint=?",(valuation.MODEL_FINGERPRINT,)).fetchone()[0]),"delta":0 if not delta_pid else int(conn.execute(f"SELECT COUNT(*) FROM {delta_v1.TOTAL_TABLE} WHERE package_id=?",(delta_pid[0],)).fetchone()[0]),"delta_component":0 if not delta_pid else int(conn.execute(f"SELECT COUNT(*) FROM {delta_v1.COMPONENT_TABLE} c JOIN {delta_v1.TOTAL_TABLE} r USING(endpoint_id) WHERE r.package_id=?",(delta_pid[0],)).fetchone()[0]),"diagnostic_endpoint":0 if not diag_pid else int(conn.execute(f"SELECT COUNT(*) FROM {diagnostic_v1.ENDPOINT_TABLE} WHERE package_id=?",(diag_pid[0],)).fetchone()[0]),"diagnostic_evaluation":0 if not diag_pid else int(conn.execute(f"SELECT COUNT(*) FROM {diagnostic_v1.EVALUATION_TABLE} v JOIN {diagnostic_v1.ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.package_id=?",(diag_pid[0],)).fetchone()[0]),"relative_result":0 if not snap else int(conn.execute("SELECT COUNT(*) FROM relative_position_result WHERE snapshot_id=?",(snap[0],)).fetchone()[0]),"relative_coverage":0 if not snap else int(conn.execute("SELECT COUNT(*) FROM relative_position_coverage WHERE snapshot_id=?",(snap[0],)).fetchone()[0])}


def apply_package(conn: sqlite3.Connection, calculated: Mapping[str, Any], *, applied_at: str, inject_failure_at: str | None=None, stage_callback: Callable[[str,sqlite3.Connection],None] | None=None) -> ApplyReport:
    validate_calculated_package(calculated)
    ensure_schema(conn); target=economic_fingerprint(calculated); existing=_existing_manifest(conn)
    if existing is not None and existing["economic_result_fingerprint"]==target:
        physical=physical_fingerprint(conn)
        if physical != existing["physical_content_fingerprint"]: raise RuntimeError("OPERATING_INCOME_V2_PHYSICAL_CONTENT_CHANGED")
        return ApplyReport("NO_CHANGE",target,physical,row_counts(conn),0)
    conn.execute("BEGIN IMMEDIATE")
    try:
        _apply_score(conn,calculated["score_v2"],applied_at)
        if stage_callback: stage_callback("score",conn)
        if inject_failure_at=="score": raise RuntimeError("INJECTED_PHASE9D_SCORE_FAILURE")
        _apply_lifecycle(conn,calculated,applied_at)
        if stage_callback: stage_callback("lifecycle",conn)
        if inject_failure_at=="lifecycle": raise RuntimeError("INJECTED_PHASE9D_LIFECYCLE_FAILURE")
        _apply_valuation(conn,calculated,applied_at)
        if stage_callback: stage_callback("valuation",conn)
        if inject_failure_at=="valuation": raise RuntimeError("INJECTED_PHASE9D_VALUATION_FAILURE")
        _apply_delta(conn,calculated,applied_at)
        if stage_callback: stage_callback("delta",conn)
        if inject_failure_at=="delta": raise RuntimeError("INJECTED_PHASE9D_DELTA_FAILURE")
        _apply_diagnostics(conn,calculated,applied_at)
        if stage_callback: stage_callback("diagnostic",conn)
        if inject_failure_at=="diagnostic": raise RuntimeError("INJECTED_PHASE9D_DIAGNOSTIC_FAILURE")
        _apply_relative(conn,calculated,applied_at)
        if stage_callback: stage_callback("relative",conn)
        if inject_failure_at in {"relative","activation"}: raise RuntimeError("INJECTED_PHASE9D_RELATIVE_FAILURE")
        physical=physical_fingerprint(conn)
        conn.execute(f"INSERT OR REPLACE INTO {MANIFEST_TABLE} VALUES(?,?,?,?,?,?,?,'COMPLETE',?)",(contract.FAMILY_FINGERPRINT,contract.FAMILY_VERSION,PERSISTENCE_VERSION,PACKAGE_FINGERPRINT,json.dumps(MODEL_MAP,sort_keys=True,separators=(",",":")),target,physical,applied_at))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    return ApplyReport("APPLIED",target,physical,row_counts(conn),sum(row_counts(conn).values()))


def validate_package(conn: sqlite3.Connection) -> dict[str,Any]:
    manifest=_existing_manifest(conn)
    if manifest is None: raise LookupError("OPERATING_INCOME_V2_PACKAGE_NOT_FOUND")
    if manifest["persistence_fingerprint"]!=PACKAGE_FINGERPRINT: raise ValueError("OPERATING_INCOME_V2_PERSISTENCE_FINGERPRINT_REJECTED")
    counts=row_counts(conn)
    expected={
        "score_component":counts["score"]*7,
        "lifecycle":counts["score"],
        "valuation":counts["score"],
        "delta":counts["score"],
        "delta_component":counts["delta"]*7,
        "diagnostic_endpoint":counts["score"],
        "diagnostic_evaluation":counts["diagnostic_endpoint"]*7,
    }
    errors=[f"{name}:{counts[name]}!={value}" for name,value in expected.items() if counts[name]!=value]
    errors.extend(row[0] for row in conn.execute("PRAGMA foreign_key_check"))
    if errors: raise RuntimeError("OPERATING_INCOME_V2_PACKAGE_INVALID:"+",".join(map(str,errors)))
    return {"ok":True,"counts":counts,"quick_check":conn.execute("PRAGMA quick_check").fetchone()[0],"physical_content_fingerprint":physical_fingerprint(conn)}
