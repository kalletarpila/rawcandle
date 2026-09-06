from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.score import engine as score_v1
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_V1_FINGERPRINT
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_V1_FINGERPRINT
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_V1_FINGERPRINT

from . import delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation
from .contract import FAMILY_FINGERPRINT, TTM_MODEL_VERSION, fingerprint


AS_OF = date(2026, 9, 6)
FRESHNESS_DAYS = 180

KEY_TABLES = {
    "canonical": ("v4_quarter_financials", "v4_ttm_values"),
    "analysis": (
        "score_result", "score_component", "lifecycle_revised_result",
        "valuation_revised_result", "fundamental_delta_result",
        "relative_position_result", "diagnostic_flag_evaluation",
    ),
    "market": ("ticker_meta",),
    "provider": ("provider_observation", "sharadar_fundamental_observation"),
    "taxonomy": ("ec_entity", "ec_membership", "ec_ecosystem"),
}


def _ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_integrity(paths: Mapping[str, Path]) -> dict[str, Any]:
    output = {}
    for name, path in sorted(paths.items()):
        stat = path.stat()
        with _ro(path) as connection:
            schema = [row[0] for row in connection.execute("SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name")]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            row_counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in KEY_TABLES[name]
                if table in tables
            }
            foreign_keys = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        output[name] = {
            "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256(path), "schema_hash": fingerprint(schema), "quick_check": quick,
            "foreign_key_check": foreign_keys, "key_row_counts": row_counts,
            "wal_exists": Path(str(path) + "-wal").exists(),
            "shm_exists": Path(str(path) + "-shm").exists(),
        }
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _load_ttm(canonical: Path) -> list[dict[str, Any]]:
    with _ro(canonical) as connection:
        return [dict(row) for row in connection.execute("""
            SELECT t.*,s.current_ticker ticker,q.source_availability_date AS quarter_source_available_date
            FROM v4_ttm_values t JOIN security s USING(security_id)
            JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id
            WHERE t.model_version='V4_TTM_EBIT_FIRST_V1'
            ORDER BY t.company_id,t.endpoint_fiscal_year,
              CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,t.ttm_id
        """)]


def _load_quarter_revenues(canonical: Path, rows: Sequence[Mapping[str, Any]]) -> dict[int, tuple[float | None, ...]]:
    with _ro(canonical) as connection:
        values = {int(row[0]): row[1] for row in connection.execute("SELECT quarter_id,revenue FROM v4_quarter_financials")}
    return {int(row["ttm_id"]): tuple(values.get(int(qid)) for qid in json.loads(row["input_quarter_ids_json"])) for row in rows}


def _load_split_events(market: Path) -> dict[str, list[dict[str, Any]]]:
    output = defaultdict(list)
    with _ro(market) as connection:
        for row in connection.execute(
            "SELECT osake AS ticker,split_date,split_ratio,is_price_data_corrected "
            "FROM splits_data ORDER BY osake,split_date"
        ):
            output[str(row["ticker"])].append(dict(row))
    return output


def _load_v1_scores(analysis: Path) -> dict[tuple[int, int], dict[str, Any]]:
    with _ro(analysis) as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM score_result WHERE model_fingerprint=? ORDER BY company_id,quarter_id", (SCORE_V1_FINGERPRINT,))]
        components = defaultdict(list)
        for row in connection.execute("SELECT r.company_id,r.quarter_id,c.component_name,c.component_score FROM score_component c JOIN score_result r USING(score_result_id) WHERE r.model_fingerprint=? ORDER BY r.company_id,r.quarter_id,c.component_name", (SCORE_V1_FINGERPRINT,)):
            components[(int(row[0]), int(row[1]))].append({"component_name": row[2], "component_score": row[3]})
    return {(int(row["company_id"]), int(row["quarter_id"])): {**row, "components": components[(int(row["company_id"]), int(row["quarter_id"]))]} for row in rows}


def _load_lifecycle(analysis: Path) -> dict[tuple[int, int], dict[str, Any]]:
    with _ro(analysis) as connection:
        return {(int(row["company_id"]), int(row["quarter_id"])): dict(row) for row in connection.execute("SELECT * FROM lifecycle_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", (LIFECYCLE_V1_FINGERPRINT,))}


def _load_valuations(analysis: Path) -> list[dict[str, Any]]:
    with _ro(analysis) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM valuation_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", (VALUATION_V1_FINGERPRINT,))]


def _fresh(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    latest = {}
    for row in rows:
        available = row.get("ttm_source_available_date")
        if not available or str(available) > AS_OF.isoformat():
            continue
        company_id = int(row["company_id"])
        if company_id not in latest or (str(available), int(row["ttm_id"])) > (str(latest[company_id]["ttm_source_available_date"]), int(latest[company_id]["ttm_id"])):
            latest[company_id] = row
    return [row for row in latest.values() if (AS_OF - date.fromisoformat(str(row["ttm_source_available_date"]))).days <= FRESHNESS_DAYS]


def _lifecycle(rows: Sequence[Mapping[str, Any]], revenues: Mapping[int, tuple[float | None, ...]]) -> dict[tuple[int, int], lifecycle.StateMachineResult]:
    grouped = defaultdict(dict)
    for row in rows:
        sequence = int(row["endpoint_fiscal_year"]) * 4 + int(str(row["endpoint_fiscal_quarter"])[1])
        grouped[int(row["company_id"])][sequence] = row
    output = {}
    for company_id, history in sorted(grouped.items()):
        state = lifecycle.LifecycleMachineState()
        for sequence, row in sorted(history.items()):
            lag = history.get(sequence - 4)
            chain = lag is not None and all(value in history for value in range(sequence - 4, sequence + 1))
            observation = lifecycle.LifecycleObservation(
                company_id, int(row["endpoint_quarter_id"]), int(row["endpoint_fiscal_year"]),
                str(row["endpoint_fiscal_quarter"]), str(row["period_end"]), row.get("ttm_source_available_date"),
                bool(row.get("core_ttm_ready")), row.get("ttm_revenue"), row.get("ttm_operating_income"),
                row.get("ttm_free_cashflow"), lag.get("ttm_revenue") if chain else None,
                lag.get("ttm_operating_income") if chain else None, chain,
                revenues.get(int(row["ttm_id"]), ()), int(row["security_id"]) if row.get("security_id") else None,
            )
            raw = lifecycle.classify_raw_state(observation)
            state, result = lifecycle.advance_state_machine(state, raw)
            output[(company_id, int(row["endpoint_quarter_id"]))] = result
    return output


def _valuation(row: Mapping[str, Any], ttm: Mapping[str, Any]) -> valuation.ValuationResult:
    observation = valuation.ValuationObservation(
        int(row["company_id"]), int(row["security_id"]) if row["security_id"] else None, row["ticker"],
        int(row["fiscal_year"]), row["fiscal_quarter"], int(row["quarter_id"]), row["period_end"],
        row["fundamental_available_date"], str(ttm["readiness_status"]), tuple(json.loads(ttm["blocker_codes_json"])), ttm.get("ttm_operating_income"),
        row["ttm_free_cashflow"], row["ttm_net_income_common"], bool(ttm.get("net_income_common_4q_ready")), row["shares_outstanding"],
        row["cash"], row["total_debt"], row["sector"], row["industry"],
    )
    bars = ()
    if row["selected_price"] is not None and row["price_date"] is not None:
        price = float(row["selected_price"])
        bars = (valuation.PriceBar(row["price_date"], price, price, price, price),)
    return valuation.calculate_valuation(observation, bars)


def _score_delta_observation(row: Mapping[str, Any], ttm: Mapping[str, Any]) -> delta.ScoreObservation:
    sequence = int(ttm["endpoint_fiscal_year"]) * 4 + int(str(ttm["endpoint_fiscal_quarter"])[1])
    fiscal = delta.FiscalObservation(str(ttm["endpoint_quarter_id"]), int(ttm["company_id"]), int(ttm["endpoint_fiscal_year"]), str(ttm["endpoint_fiscal_quarter"]), sequence, str(ttm["period_end"]), str(ttm["ttm_source_available_date"]))
    maxima = dict(zip(score.COMPONENTS, (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0)))
    components = tuple(delta.ScoreComponentObservation(item["component_name"], item["component_score"], maxima[item["component_name"]], "OBSERVED" if item["component_score"] is not None else "MISSING") for item in row["components"])
    return delta.ScoreObservation(fiscal, int(ttm["endpoint_quarter_id"]), score.MODEL_VERSION, score.MODEL_FINGERPRINT, row["total_score"], row["readiness_status"], "TTM_READY" if ttm.get("core_ttm_ready") else "TTM_NOT_READY", components)


def calculate(paths: Mapping[str, Path]) -> dict[str, Any]:
    rows = _load_ttm(paths["canonical"]); ttm_index = {(int(row["company_id"]), int(row["endpoint_quarter_id"])): row for row in rows}
    fresh = _fresh(rows); fresh_keys = {(int(row["company_id"]), int(row["endpoint_quarter_id"])) for row in fresh}
    split_events = _load_split_events(paths["market"])
    v2_scores = score.compute_score_rows(rows, split_events, generated_at="REHEARSAL", run_id="PHASE9C")
    score_index = {(int(row["company_id"]), int(row["quarter_id"])): row for row in v2_scores}
    v1_scores = _load_v1_scores(paths["analysis"])
    v1_replay_rows = score_v1.compute_score_rows(rows, split_events, generated_at="REHEARSAL", run_id="PHASE9C_V1")
    v1_replay_index = {(int(row["company_id"]), int(row["quarter_id"])): row for row in v1_replay_rows}
    unaffected = {"REVENUE_GROWTH", "FCF_MARGIN", "DILUTION"}
    for key, persisted in v1_scores.items():
        replayed = v1_replay_index[key]
        assert persisted["readiness_status"] == replayed["readiness_status"]
        assert persisted["total_score"] == replayed["total_score"]
        persisted_components = {item["component_name"]: item["component_score"] for item in persisted["components"]}
        replayed_components = {item["component_name"]: item["component_score"] for item in replayed["components"]}
        v2_components = {item["component_name"]: item["component_score"] for item in score_index[key]["components"]}
        assert persisted_components == replayed_components
        assert all(v2_components[name] == persisted_components[name] for name in unaffected)
    life_v2 = _lifecycle(rows, _load_quarter_revenues(paths["canonical"], rows)); life_v1 = _load_lifecycle(paths["analysis"])
    valuation_v1 = _load_valuations(paths["analysis"])
    valuation_v1_index = {(int(row["company_id"]), int(row["quarter_id"])): row for row in valuation_v1}
    valuation_v2 = {}
    for row in valuation_v1:
        key = (int(row["company_id"]), int(row["quarter_id"])); valuation_v2[key] = _valuation(row, ttm_index[key])

    score_current=[]; lifecycle_current=[]; valuation_current=[]
    for key in sorted(fresh_keys):
        before=v1_scores[key]; after=score_index[key]
        score_current.append({"company_id":key[0],"quarter_id":key[1],"ticker":after["ticker"],"v1_status":before["readiness_status"],"v2_status":after["readiness_status"],"v1_score":before["total_score"],"v2_score":after["total_score"],"delta":None if before["total_score"] is None or after["total_score"] is None else after["total_score"]-before["total_score"]})
        b=life_v1[key]; a=life_v2[key]
        lifecycle_current.append({"company_id":key[0],"quarter_id":key[1],"ticker":after["ticker"],"v1_raw":b["raw_state"],"v2_raw":a.raw_result.raw_state.value,"v1_final":b["final_state"],"v2_final":a.final_state.value if a.final_state else None,"v1_status":b["lifecycle_status"],"v2_status":a.lifecycle_status.value})
        old=valuation_v1_index.get(key); new=valuation_v2.get(key)
        if old and new: valuation_current.append({"company_id":key[0],"quarter_id":key[1],"ticker":after["ticker"],"v1_status":old["valuation_status"],"v2_status":new.valuation_status,"v1_score":old["total_valuation_score"],"v2_score":new.total_valuation_score,"delta":None if old["total_valuation_score"] is None or new.total_valuation_score is None else new.total_valuation_score-old["total_valuation_score"]})

    histories=defaultdict(list); delta_observations={}
    for key,row in score_index.items():
        observation = _score_delta_observation(row,ttm_index[key])
        histories[key[0]].append(observation); delta_observations[key] = observation
    delta_full=[]; delta_results=[]
    for key in sorted(score_index):
        current=delta_observations[key]
        result=delta.calculate_fundamental_delta(current,histories[key[0]],source_fingerprint="PHASE9C")
        delta_results.append(result)
        delta_full.append({"company_id":key[0],"quarter_id":key[1],"ticker":score_index[key]["ticker"],**{item["horizon"].value:item["delta_points"] for item in result.horizons}})
    delta_current=[row for row in delta_full if (row["company_id"],row["quarter_id"]) in fresh_keys]

    with _ro(paths["market"]) as connection:
        classes={str(row[0]):(row[1],row[2]) for row in connection.execute("SELECT ticker,sector,industry FROM ticker_meta")}
    with _ro(paths["analysis"]) as connection:
        active=connection.execute("SELECT snapshot_id FROM relative_position_active_snapshot ORDER BY activated_at_utc DESC LIMIT 1").fetchone()[0]
        memberships=defaultdict(list)
        for row in connection.execute("SELECT DISTINCT company_id,peer_group_id FROM relative_position_result WHERE snapshot_id=? AND peer_scope='ECOSYSTEM' AND result_status='RELATIVE_POSITION_READY'",(active,)):
            memberships[int(row[0])].append(relative_position.EcosystemMembership(str(row[1]),"CORE"))
    relative_score_rows={}
    for row in rows:
        available=row.get("quarter_source_available_date")
        if not available or str(available)>AS_OF.isoformat(): continue
        company_id=int(row["company_id"]); current=relative_score_rows.get(company_id)
        sequence=int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1])
        if current is None or sequence>current[0]: relative_score_rows[company_id]=(sequence,row)
    relative_valuation_rows={}
    for key,value in valuation_v2.items():
        available=value.fundamental_available_date
        if not available or str(available)>AS_OF.isoformat(): continue
        sequence=value.fiscal_year*4+int(value.fiscal_quarter[1]); current=relative_valuation_rows.get(key[0])
        if current is None or sequence>current[0]: relative_valuation_rows[key[0]]=(sequence,key,value)
    relative_observations=[]
    for _,row in sorted(relative_score_rows.values(),key=lambda item:int(item[1]["company_id"])):
        key=(int(row["company_id"]),int(row["endpoint_quarter_id"])); ticker=str(row["ticker"]); sector,industry=classes.get(ticker,(None,None)); scored=score_index[key]
        relative_observations.append(relative_position.RelativeObservation(f"S:{key[0]}",key[0],int(row["security_id"]),ticker,relative_position.RelativeMeasure.FUNDAMENTAL_SCORE,scored["total_score"],scored["readiness_status"],scored["readiness_status"]=="SCORE_FULL",scored["readiness_status"],row["quarter_source_available_date"],score.MODEL_VERSION,score.MODEL_FINGERPRINT,f"S:{key}",sector,industry,tuple(memberships[key[0]])))
    for company_id,(_,key,value) in sorted(relative_valuation_rows.items()):
        source=ttm_index[key]; ticker=str(source["ticker"]); sector,industry=classes.get(ticker,(None,None))
        relative_observations.append(relative_position.RelativeObservation(f"V:{company_id}",company_id,int(source["security_id"]),ticker,relative_position.RelativeMeasure.ABSOLUTE_VALUATION_SCORE,value.total_valuation_score,value.valuation_status,value.valuation_status=="VALUATION_FULL",value.reason_code,value.fundamental_available_date,valuation.MODEL_VERSION,valuation.MODEL_FINGERPRINT,value.result_fingerprint,sector,industry,tuple(memberships[company_id])))
    relative=relative_position.calculate_snapshot(relative_observations,snapshot_date=AS_OF.isoformat(),freshness_days=FRESHNESS_DAYS,classification_fingerprint=fingerprint(classes),taxonomy_fingerprint=fingerprint({k:[asdict(x) for x in v] for k,v in memberships.items()}))

    diagnostics_full=[]
    sequence_index = {
        (int(row["company_id"]), int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1])): row
        for row in rows
    }
    for row in rows:
        key=(int(row["company_id"]),int(row["endpoint_quarter_id"])); sequence=int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1]); prior=sequence_index.get((key[0],sequence-1))
        def endpoint(source):
            source_key=(int(source["company_id"]),int(source["endpoint_quarter_id"]))
            val=valuation_v2.get(source_key)
            scored=score_index[source_key]
            traj=next((item["component_score"] for item in scored["components"] if item["component_name"]=="FUNDAMENTAL_TRAJECTORY"),None)
            valuation_source = valuation_v1_index.get(source_key, {})
            application=valuation.classify_applicability(valuation_source.get("sector"), valuation_source.get("industry"))
            diagnostic_classification="SUPPORTED" if application.supported is True else "NOT_APPLICABLE" if application.supported is False else None
            seq=int(source["endpoint_fiscal_year"])*4+int(str(source["endpoint_fiscal_quarter"])[1])
            return diagnostic_flags.DiagnosticEndpoint(source_key[0],int(source["endpoint_quarter_id"]),int(source["endpoint_fiscal_year"]),str(source["endpoint_fiscal_quarter"]),seq,str(source["period_end"]),source["ttm_source_available_date"],source["ttm_source_available_date"],source["ttm_source_available_date"],"TTM_READY" if source.get("core_ttm_ready") else "TTM_NOT_READY",source.get("ttm_revenue"),source.get("ttm_operating_income"),source.get("ttm_net_income_common"),source.get("ttm_operating_cashflow"),source.get("ttm_capex"),source.get("cash"),source.get("total_debt"),trajectory=traj,valuation_status=val.valuation_status if val else None,valuation_reason=val.reason_code if val else None,applicability_classification=diagnostic_classification,applicability_reason=application.reason_code,operating_income_yield=val.operating_income_yield if val else None,fcf_yield=val.fcf_yield if val else None,earnings_yield=val.earnings_yield if val else None)
        current_endpoint=endpoint(row); prior_endpoint=endpoint(prior) if prior else None
        consecutive=bool(prior and str(prior["period_end"])<str(row["period_end"]) and prior.get("ttm_source_available_date") and row.get("ttm_source_available_date") and str(prior["ttm_source_available_date"])<=str(row["ttm_source_available_date"]))
        for result in diagnostic_flags.evaluate_diagnostic_flags(diagnostic_flags.DiagnosticInput(current_endpoint,prior_endpoint,consecutive)):
            diagnostics_full.append({"company_id":key[0],"quarter_id":key[1],"ticker":row["ticker"],"flag_name":result.flag_name,"status":result.status.value,"reason_code":result.reason_code,"triggered":result.triggered,"comparison_quarter_id":result.comparison_quarter_id,"effective_available_date":result.effective_available_date,"evidence":{item.name:item.value for item in result.evidence},"model_version":result.model_version,"model_fingerprint":result.model_fingerprint})
    diagnostics=[row for row in diagnostics_full if (row["company_id"],row["quarter_id"]) in fresh_keys]

    snapshot.validate_model_bundle({layer:snapshot.ModelIdentity(*identity) for layer,identity in snapshot.MODEL_CONTRACT["required_models"].items()})
    outputs={"rows":rows,"fresh":fresh,"score_v2":v2_scores,"score_current":score_current,"v1_replay_rows":v1_replay_rows,"lifecycle_v2":life_v2,"lifecycle_current":lifecycle_current,"valuation_v1_rows":valuation_v1,"valuation_v2":valuation_v2,"valuation_current":valuation_current,"delta_results":delta_results,"delta_full":delta_full,"delta_current":delta_current,"relative":relative,"diagnostics_full":diagnostics_full,"diagnostics":diagnostics}
    outputs["fingerprints"]={"score":fingerprint(v2_scores),"lifecycle":fingerprint([asdict(life_v2[key]) for key in sorted(life_v2)]),"valuation":fingerprint([valuation_v2[key].to_dict() for key in sorted(valuation_v2)]),"delta":fingerprint(delta_full),"relative":relative.result_fingerprint,"diagnostic":fingerprint(diagnostics_full)}
    return outputs


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True,exist_ok=True)
    paths={"canonical":repo_root/"data/fundamentals_v4.db","analysis":repo_root/"data/fundamentals_analysis.db","market":repo_root/"data/osakedata.db","provider":repo_root/"data/fundamentals_provider.db","taxonomy":repo_root/"data/analysis.db"}
    before=database_integrity(paths); first=calculate(paths); second=calculate(paths); assert first["fingerprints"]==second["fingerprints"]
    _write_csv(output/"current_score_comparison.csv",first["score_current"]); _write_csv(output/"current_lifecycle_comparison.csv",first["lifecycle_current"]); _write_csv(output/"current_valuation_comparison.csv",first["valuation_current"]); _write_csv(output/"current_delta_comparison.csv",first["delta_current"])
    _write_csv(output/"current_relative_position_comparison.csv",[{"company_id":row["company_id"],"ticker":row["ticker"],"measure":row["measure"].value,"scope":row["peer_scope"].value,"percentile":row["percentile"],"rank":row["average_rank"],"status":row["status"].value} for row in first["relative"].results])
    _write_csv(output/"current_diagnostic_comparison.csv",first["diagnostics"])
    reconciliation=[]
    for name,rows in (("SCORE",first["score_current"]),("LIFECYCLE",first["lifecycle_current"]),("VALUATION",first["valuation_current"])):
        reconciliation.append({"layer":name,"rows":len(rows),"changed":sum((row.get("v1_score")!=row.get("v2_score")) if name!="LIFECYCLE" else row["v1_final"]!=row["v2_final"] for row in rows)})
    _write_csv(output/"v1_v2_reconciliation.csv",reconciliation)
    cases=[]
    targets=("AMZN","GOOG","NVDA","CRMD","APD","BA","LITE")
    for row in first["score_current"]:
        if row["ticker"] in targets:
            valuation_row=next((item for item in first["valuation_current"] if item["company_id"]==row["company_id"]),{})
            cases.append({**row,"v1_valuation":valuation_row.get("v1_score"),"v2_valuation":valuation_row.get("v2_score")})
    expected={"AMZN":(56.08,18.43),"GOOG":(77.53,27.82),"NVDA":(96.94,27.02),"CRMD":(91.08,100.0),"APD":(26.96,0.0)}
    indexed_cases={row["ticker"]:row for row in cases}
    for ticker,(expected_score,expected_valuation) in expected.items():
        assert abs(indexed_cases[ticker]["v2_score"]-expected_score)<=0.02
        assert abs(indexed_cases[ticker]["v2_valuation"]-expected_valuation)<=0.02
    _write_csv(output/"company_case_checks.csv",cases)
    versions={"family":FAMILY_FINGERPRINT,"score":(score.MODEL_VERSION,score.MODEL_FINGERPRINT),"lifecycle":(lifecycle.MODEL_VERSION,lifecycle.MODEL_FINGERPRINT),"valuation":(valuation.MODEL_VERSION,valuation.MODEL_FINGERPRINT),"delta":(delta.MODEL_VERSION,delta.MODEL_FINGERPRINT),"relative":(relative_position.MODEL_VERSION,relative_position.MODEL_FINGERPRINT),"diagnostic":(diagnostic_flags.MODEL_VERSION,diagnostic_flags.MODEL_FINGERPRINT),"snapshot":(snapshot.MODEL_VERSION,snapshot.MODEL_FINGERPRINT)}
    _write_json(output/"model_version_map.json",versions); _write_json(output/"v2_fingerprints.json",versions); _write_json(output/"result_fingerprints.json",{"first":first["fingerprints"],"second":second["fingerprints"],"identical":True})
    _write_json(output/"readiness_summary.json",{"ttm_rows":len(first["rows"]),"v1_score_replay_rows":len(first["v1_replay_rows"]),"v1_score_replay_identical":True,"unaffected_score_components_identical":True,"current_fresh":len(first["fresh"]),"score_full":sum(row["readiness_status"]=="SCORE_FULL" for row in first["score_v2"]),"current_score_full":sum(row["v2_status"]=="SCORE_FULL" for row in first["score_current"]),"valuation_calculated":len(first["valuation_v2"]),"lifecycle_rows":len(first["lifecycle_v2"]),"delta_history_rows":len(first["delta_full"]),"current_delta_rows":len(first["delta_current"]),"relative_rows":len(first["relative"].results),"diagnostic_history_rows":len(first["diagnostics_full"]),"diagnostic_rows":len(first["diagnostics"])})
    (output/"recommended_phase9d_scope.md").write_text("# Recommended Phase 9D scope\n\nDesign and rehearse parallel V2 persistence schemas, repositories, backfill packages and reader-bundle activation. Preserve V1 rows and rollback. Production migration, backfill and activation require separate authorization.\n",encoding="utf-8")
    after=database_integrity(paths); assert before==after; _write_json(output/"database_integrity_before.json",before); _write_json(output/"database_integrity_after.json",after)
    report=f"# Phase 9C implementation report\n\nParallel Operating-Income V2 pure engines are implemented. Full history: {len(first['rows'])} TTM, {len(first['score_v2'])} Score and {len(first['lifecycle_v2'])} Lifecycle rows. Current fresh: {len(first['fresh'])}. Two rehearsals produced identical fingerprints. No production writes or activation occurred.\n"
    (output/"PHASE9C_IMPLEMENTATION_REPORT.md").write_text(report,encoding="utf-8"); (output/"commands_run.txt").write_text("python -m rawcandle.fundamentals.operating_income_v2.rehearsal --output <temp>\n",encoding="utf-8")
    for path in output.glob("*.json"): json.loads(path.read_text())
    for path in output.glob("*.csv"):
        with path.open(newline="",encoding="utf-8") as handle: list(csv.reader(handle))
    required={"PHASE9C_IMPLEMENTATION_REPORT.md","model_version_map.json","v2_fingerprints.json","v1_v2_reconciliation.csv","current_score_comparison.csv","current_lifecycle_comparison.csv","current_valuation_comparison.csv","current_delta_comparison.csv","current_relative_position_comparison.csv","current_diagnostic_comparison.csv","company_case_checks.csv","readiness_summary.json","result_fingerprints.json","recommended_phase9d_scope.md","commands_run.txt"}
    assert not (required-{path.name for path in output.iterdir()})
    return {"output":str(output),"fingerprints":first["fingerprints"],"integrity_identical":True}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo-root",type=Path,default=Path.cwd()); parser.add_argument("--output",type=Path)
    args=parser.parse_args(); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); output=args.output or args.repo_root/"temp/fundamentals_v4_operating_income_v2_phase9c"/stamp
    print(json.dumps(run(args.repo_root.resolve(),output.resolve()),sort_keys=True))


if __name__=="__main__": main()
