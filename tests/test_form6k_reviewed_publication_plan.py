from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import reviewed_publication_plan as plans
from rawcandle.fundamentals.admin import form6k_reviewed_publication_plan as form6k
from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin.publication_journal import load_journal, sha256_file, PublicationRecoveredRetryRequired
from rawcandle.fundamentals.admin.production_transaction import SimulatedTransactionCrash
from rawcandle.fundamentals.generations import prepare_generation_from_candidates, activate_generation, resolve_active_generation
from rawcandle.fundamentals.form6k_authority import (
    FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1 as V1, natural_key, reviewed_evidence_payload,
)
from rawcandle.fundamentals.result_publication import SecClient, apply_resolution, SOURCE_RANK, yahoo_evidence_payload, store_secondary_evidence
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema, upgrade_form6k_candidate_schema
from tests.test_policy_reviewed_publication_plan import insert, forbid_network

DAY = "2026-10-07"
FIXTURE = Path(__file__).parent / "fixtures/form6k_authority_v1.json"
COHORT = json.loads(FIXTURE.read_text())


def seed(root, fixture=COHORT):
    root.mkdir(parents=True, exist_ok=True)
    roles = {role: root / (role + ".db") for role in ("canonical", "provider", "analysis")}
    for path in roles.values():
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE financial_sentinel(value REAL)")
            db.execute("INSERT INTO financial_sentinel VALUES(123456.78)")
    with sqlite3.connect(roles["canonical"]) as db:
        db.execute("CREATE TABLE company(company_id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE company_cik(company_id INTEGER,cik_normalized TEXT,status TEXT)")
        db.execute("CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,active INTEGER)")
        q = fixture["cases"][0]["quarter"]
        columns = {k: v for k, v in q.items() if k not in {"security_id", "sec_cik"}}
        db.execute("CREATE TABLE v4_quarter(" + ",".join(k + (" INTEGER" if type(v) is int else " TEXT") for k,v in columns.items()) + ")")
        ensure_result_publication_schema(db)
        for c in fixture["cases"]:
            q = c["quarter"]
            db.execute("INSERT OR IGNORE INTO company VALUES(?)", (q["company_id"],))
            if not db.execute("SELECT 1 FROM company_cik WHERE company_id=?", (q["company_id"],)).fetchone():
                db.execute("INSERT INTO company_cik VALUES(?,?,'ACTIVE')", (q["company_id"],q["sec_cik"]))
                db.execute("INSERT INTO security VALUES(?,?,?,1)", (q["security_id"],q["company_id"],c["ticker"]))
            insert(db,"v4_quarter", {k:q[k] for k in columns})
            insert(db,"v4_result_publication_authority",c["current_authority"])
        first = fixture["cases"][0]
        # Retain real existing SQL evidence both inside and outside prepared scope.
        for c in fixture["cases"]:
            e = yahoo_evidence_payload(c["quarter"],provider_symbol=c["ticker"],event_timestamp="2026-07-01T00:00:00Z",
                                       source_timezone="UTC",fetched_at_utc="2026-10-06T00:00:00Z")
            store_secondary_evidence(db,e)
        for i,status in enumerate(("VERIFIED","VERIFIED","NOT_FOUND","UNRESOLVED","AMBIGUOUS"), start=900001):
            q = {k:first["quarter"][k] for k in columns}
            q.update(quarter_id=i,fiscal_year=2000+i-900000)
            insert(db,"v4_quarter",q)
            e = yahoo_evidence_payload(q,provider_symbol="OUTSIDE",event_timestamp="2026-07-01T00:00:00Z",
                                      source_timezone="UTC",fetched_at_utc="2026-10-06T00:00:00Z")
            e.update(source_type="ISSUER_EARNINGS_RELEASE" if i==900001 else "SEC_8K_ITEM_2_02")
            apply_resolution(db,q,[e] if status=="VERIFIED" else [],unresolved=status=="UNRESOLVED")
            if status=="AMBIGUOUS":
                db.execute("UPDATE v4_result_publication_authority SET status='AMBIGUOUS' WHERE quarter_id=?",(i,))
    manifest = prepare_generation_from_candidates(roles,generation_id="form6k_source",project_root=root,source="TEST")
    activate_generation(manifest["manifest"],project_root=root)
    return root


def prepare(tmp_path, fixture=COHORT):
    root = seed(tmp_path / "source",fixture)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(fixture))
    keys = tmp_path / "keys.csv"
    with keys.open("w",newline="") as f:
        w = csv.writer(f); w.writerow(("company_id","fiscal_year","fiscal_quarter"))
        w.writerows(natural_key(c["quarter"]) for c in fixture["cases"])
    path = tmp_path / "plan.json"
    report = plans.prepare_reviewed_plan(project_root=root,allowlist_path=keys,output_plan=path,
        policy_evidence_path=evidence,publication_authority_mode=V1,as_of_date=DAY)
    return root,path,plans.load_plan(path),report


def reseal(plan):
    plan["plan_fingerprint"] = plans.fingerprint({k:v for k,v in plan.items() if k!="plan_fingerprint"})


def test_prepare_partition_and_bindings(tmp_path, monkeypatch):
    forbid_network(monkeypatch)
    root,path,plan,report = prepare(tmp_path)
    assert report["classification_counts"] == {"UNIQUE":9,"REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT":2,
        "MULTIPLE_COMPETING_EVENTS":6,"WRONG_PERIOD":5,"IDENTITY_TEMPORAL_REVIEW":1}
    assert {c["ticker"] for c in plan["per_case"]} == {"WDH","CAN","NEGG","VNET","PAAS","BTDR","CAMT","WPM","NVMI"}
    assert sum(len(c["frozen_case"]["candidates"]) for c in plan["form6k_cases"]) == 30
    assert plan["prepared_key_count"] == 9 and plan["source_rank"] == 2 and plan["confidence"] == "MEDIUM"
    assert len(plans.plan_scope_evidence(plan)["form6k_decision_fingerprints"]) == 23
    assert path.stat().st_mode & 0o222 == 0
    assert next(c for c in plan["per_case"] if c["ticker"]=="NVMI")["current_60d_scope"] == "OUTSIDE"
    with pytest.raises(FileExistsError):
        plans.prepare_reviewed_plan(project_root=root,allowlist_path=tmp_path/"keys.csv",output_plan=path,
            policy_evidence_path=tmp_path/"evidence.json",publication_authority_mode=V1,as_of_date=DAY)


@pytest.mark.parametrize("field,value",[("authority_version","OTHER"),("policy_mode","LEGACY"),
    ("source_type","SEC_FILING_FALLBACK"),("source_rank",3),("confidence","HIGH"),
    ("frozen_fixture_version","OTHER"),("prepared_keys",[]),("aggregate_decision_fingerprint","0"*64),
    ("reviewed_cohort_fingerprint","0"*64),("canonical_authority_fingerprint","0"*64)])
def test_resealed_plan_tamper_fails(tmp_path,field,value):
    _,_,plan,_=prepare(tmp_path)
    plan[field]=value; reseal(plan)
    with pytest.raises(ValueError): plans.validate_plan(plan)


@pytest.mark.parametrize("kind",["acceptance","identity","relation","selected_accession","state","evidence","held_decision","missing_mode"])
def test_context_tamper_fails_after_outer_reseal(tmp_path,kind):
    _,_,plan,_=prepare(tmp_path)
    case=plan["per_case"][0]
    if kind=="acceptance": case["frozen_case"]["candidates"][0]["acceptance"]["submissions_utc"]="2026-01-01T00:00:00Z"
    elif kind=="identity": case["frozen_case"]["candidates"][0]["identity"]["filer_role"]="DEPOSITARY_BANK"
    elif kind=="relation": next(c for c in plan["form6k_cases"] if c["ticker"]=="CLLS")["frozen_case"]["relations"][0]["relation_type"]="INITIAL_RESULT_TO_REVISION"
    elif kind=="selected_accession": case["decision"]["selected_accession"]="0000000000-26-000000"
    elif kind=="state": case["state"]["securities"][0]["company_id"]=-1
    elif kind=="evidence": case["evidence"]["source_timestamp_utc"]="2026-01-01T00:00:00Z"
    elif kind=="held_decision": next(c for c in plan["form6k_cases"] if c["ticker"]=="BABA")["decision"]["final_result"]="UNIQUE"
    else: plan.pop("policy_mode")
    reseal(plan)
    with pytest.raises(ValueError): plans.validate_plan(plan)


def test_real_writer_rehearsal(tmp_path,monkeypatch):
    forbid_network(monkeypatch)
    root,path,plan,_=prepare(tmp_path)
    source=resolve_active_generation(root,require_generation=True)
    hashes={k:sha256_file(p) for k,p in source.role_paths().items()}
    result=plans.rehearse_reviewed_plan(project_root=root,plan_path=path,rehearsal_root=tmp_path/"rehearsal",as_of_date=DAY)
    assert result["status"]=="PASS" and result["unrelated_changes"]==0
    writer=result["writer_result"]
    assert writer["status"]=="SUCCESS" and writer["rollback"]["status"]=="NOT_REQUIRED"
    copied=resolve_active_generation(tmp_path/"rehearsal",require_generation=True)
    assert copied.generation_id != source.generation_id
    assert hashes=={k:sha256_file(p) for k,p in source.role_paths().items()}
    journal=load_journal(tmp_path/"rehearsal/data/.fundamentals_admin_publication_journal.json")
    assert journal["state"]=="COMPLETED"
    for k,v in plans.plan_scope_evidence(plan).items(): assert journal["scope_evidence"][k]==v
    with sqlite3.connect(copied.role_paths()["canonical"]) as db:
        db.row_factory=sqlite3.Row
        for c in plan["form6k_cases"]:
            state=plans.state_for_key(db,natural_key(c))
            if c not in plan["per_case"]:
                assert state==c["state"]
            else:
                a=state["authority"][0]
                assert a["status"]=="VERIFIED" and a["rule_version"]==V1
                assert a["result_publication_source"]=="SEC_FORM_6K_RESULT" and a["result_publication_confidence"]=="MEDIUM"
                stored=db.execute("SELECT * FROM v4_result_publication_evidence WHERE evidence_id=?",(a["selected_evidence_id"],)).fetchone()
                proof=json.loads(stored["matching_method"])
                assert proof["source_rank"]==2 and proof["frozen_case"]["candidates"]==c["frozen_case"]["candidates"]
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert not list((tmp_path/"rehearsal/temp").glob("publication_drain_*"))
    with pytest.raises(ValueError,match="FINALIZED"):
        form6k.run_form6k_candidate(copied.role_paths()["canonical"],plan,as_of_date=DAY)


@pytest.mark.parametrize("stage",["AFTER_PREPARED","AFTER_NEW_GENERATION_READY","AFTER_GENERATION_ACTIVATION"])
def test_crash_recovery_exact_same_plan(tmp_path,monkeypatch,stage):
    forbid_network(monkeypatch)
    root,path,plan,_=prepare(tmp_path)
    source=resolve_active_generation(root,require_generation=True)
    hashes={k:sha256_file(p) for k,p in source.role_paths().items()}
    kwargs=dict(project_root=root,apply=True,confirm_production=True,as_of_date=DAY,reviewed_apply_plan=path)
    with pytest.raises(SimulatedTransactionCrash): drain.run_backlog_drain(**kwargs,inject_crash_at=stage)
    with pytest.raises(PublicationRecoveredRetryRequired): drain.run_backlog_drain(**kwargs)
    active=resolve_active_generation(root,require_generation=True)
    assert active.generation_id==source.generation_id
    assert hashes=={k:sha256_file(p) for k,p in active.role_paths().items()}
    with pytest.raises(RuntimeError,match="SAME_PLAN"):
        drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,as_of_date=DAY)
    assert drain.run_backlog_drain(**kwargs)["status"]=="SUCCESS"


@pytest.mark.parametrize("field",["policy_mode","authority_version","source_type","prepared_keys_fingerprint",
    "aggregate_decision_fingerprint","form6k_decision_fingerprints","reviewed_cohort_fingerprint"])
def test_recovery_missing_binding_rejected(tmp_path,monkeypatch,field):
    forbid_network(monkeypatch)
    root,path,_,_=prepare(tmp_path)
    kwargs=dict(project_root=root,apply=True,confirm_production=True,as_of_date=DAY,reviewed_apply_plan=path)
    with pytest.raises(SimulatedTransactionCrash): drain.run_backlog_drain(**kwargs,inject_crash_at="AFTER_PREPARED")
    with pytest.raises(PublicationRecoveredRetryRequired): drain.run_backlog_drain(**kwargs)
    journal_path=root/"data/.fundamentals_admin_publication_journal.json"
    journal=json.loads(journal_path.read_text()); journal["scope_evidence"].pop(field)
    journal_path.write_text(json.dumps(journal))
    with pytest.raises(RuntimeError,match="FORM6K_RECOVERY_SAME_PLAN"):
        drain.run_backlog_drain(**kwargs)


def test_live_root_confirmation_guard(tmp_path,monkeypatch):
    root,path,_,_=prepare(tmp_path)
    monkeypatch.setattr(drain,"ROOT",root)
    with pytest.raises(PermissionError,match="CONFIRMATION_REQUIRED"):
        drain.run_backlog_drain(project_root=root,apply=True,reviewed_apply_plan=path)


def test_zero_key_plan_never_falls_through(tmp_path,monkeypatch):
    fixture=deepcopy(COHORT)
    fixture["cases"]=[c for c in fixture["cases"] if c["expected_result"]!="UNIQUE"]
    fixture["fixture_fingerprint"]=plans.fingerprint({k:v for k,v in fixture.items() if k!="fixture_fingerprint"})
    root,path,plan,report=prepare(tmp_path,fixture)
    assert plan["prepared_keys"]==[] and report["status"]=="SKIPPED"
    def deny(*a,**kw): raise AssertionError("MUTATION_FORBIDDEN")
    monkeypatch.setattr(drain,"run_plan_candidate",deny)
    monkeypatch.setattr(form6k,"upgrade_form6k_candidate_schema",deny)
    assert drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,reviewed_apply_plan=path,as_of_date=DAY)["status"]=="SKIPPED"


def test_explicit_mode_and_cli(tmp_path,capsys):
    root,_,plan,_=prepare(tmp_path)
    with pytest.raises(ValueError,match="MODE_REQUIRED"):
        plans.prepare_reviewed_plan(project_root=root,allowlist_path=tmp_path/"keys.csv",output_plan=tmp_path/"no_mode.json",
                                    policy_evidence_path=tmp_path/"evidence.json")
    from rawcandle.cli.result_publication_backlog_drain import main
    assert main(["--prepare-reviewed-plan","--publication-authority-mode",V1,"--policy-evidence",str(tmp_path/"evidence.json"),
        "--exact-allowlist",str(tmp_path/"keys.csv"),"--output-plan",str(tmp_path/"cli_plan.json"),"--rehearsal-root",str(root)])==0
    assert plans.load_plan(tmp_path/"cli_plan.json")["prepared_keys"]==plan["prepared_keys"]
    with pytest.raises(SystemExit): main(["--publication-authority-mode",V1])


def test_migration_idempotent_and_transactional(tmp_path):
    root,_,plan,_=prepare(tmp_path)
    source=resolve_active_generation(root,require_generation=True).role_paths()["canonical"]
    candidate=tmp_path/"candidate.db"; shutil.copyfile(source,candidate)
    with sqlite3.connect(candidate) as db:
        db.row_factory=sqlite3.Row
        before=plans._rows(db,"SELECT * FROM v4_result_publication_evidence ORDER BY evidence_id")
        authorities=plans._rows(db,"SELECT * FROM v4_result_publication_authority ORDER BY quarter_id")
        db.execute("CREATE VIEW publication_view AS SELECT evidence_id FROM v4_result_publication_evidence")
        db.execute("CREATE INDEX custom_pub_index ON v4_result_publication_evidence(accession_number)")
        db.execute("CREATE TABLE audit_inserts(id TEXT)")
        db.execute("CREATE TRIGGER pub_audit AFTER INSERT ON v4_result_publication_evidence BEGIN INSERT INTO audit_inserts VALUES(new.evidence_id); END")
        db.commit(); db.execute("PRAGMA foreign_keys=ON"); db.execute("BEGIN IMMEDIATE")
        assert upgrade_form6k_candidate_schema(db)
        assert not upgrade_form6k_candidate_schema(db)
        assert plans._rows(db,"SELECT * FROM v4_result_publication_evidence ORDER BY evidence_id")==before
        assert plans._rows(db,"SELECT * FROM v4_result_publication_authority ORDER BY quarter_id")==authorities
        assert len(db.execute("SELECT * FROM publication_view").fetchall())==len(before)
        assert db.execute("SELECT * FROM audit_inserts").fetchall()==[]
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='custom_pub_index'").fetchone()
        db.rollback()
        assert "SEC_FORM_6K_RESULT" not in db.execute("SELECT sql FROM sqlite_master WHERE name='v4_result_publication_evidence'").fetchone()[0]
        db.execute("BEGIN IMMEDIATE"); upgrade_form6k_candidate_schema(db)
        for table,column in (("v4_result_publication_evidence","source_type"),("v4_result_publication_authority","result_publication_source")):
            with pytest.raises(sqlite3.IntegrityError): db.execute(f"UPDATE {table} SET {column}='ARBITRARY_6K'")
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]


@pytest.mark.parametrize("source,expected",[("ISSUER_EARNINGS_RELEASE","VERIFIED"),("SEC_8K_ITEM_2_02","VERIFIED"),
    ("SEC_FILING_FALLBACK","AMBIGUOUS"),("MANUAL_REVIEW","VERIFIED")])
def test_source_hierarchy_preserved(tmp_path,source,expected):
    root,_,plan,_=prepare(tmp_path)
    candidate=tmp_path/"candidate.db"
    shutil.copyfile(resolve_active_generation(root,require_generation=True).role_paths()["canonical"],candidate)
    case=plan["per_case"][0]; q=case["state"]["quarter"][0]; proof=form6k._proof(case["frozen_case"])
    with sqlite3.connect(candidate) as db:
        db.row_factory=sqlite3.Row; db.execute("BEGIN IMMEDIATE"); upgrade_form6k_candidate_schema(db)
        old={**case["evidence"],"source_type":source,"source_timestamp_utc":"2026-01-01T00:00:00Z",
             "evidence_id":"old_authority","evidence_hash":"old_authority"}
        apply_resolution(db,q,[old])
        before=plans.state_for_key(db,natural_key(q))["authority"][0]
        assert apply_resolution(db,q,[case["evidence"]],form6k_reviewed_case=proof)==expected
        after=plans.state_for_key(db,natural_key(q))["authority"][0]
        if source in {"ISSUER_EARNINGS_RELEASE","SEC_8K_ITEM_2_02"}: assert after==before
        elif source=="SEC_FILING_FALLBACK": assert after["result_publication_timestamp_utc"]==before["result_publication_timestamp_utc"]
        else: assert after["result_publication_source"]=="SEC_FORM_6K_RESULT"
    assert SOURCE_RANK=={"ISSUER_EARNINGS_RELEASE":4,"SEC_8K_ITEM_2_02":3,"SEC_FILING_FALLBACK":2,"MANUAL_REVIEW":1}


@pytest.mark.parametrize("source",["ISSUER_EARNINGS_RELEASE","SEC_8K_ITEM_2_02"])
def test_default_cannot_authorize_6k_but_can_upgrade_stored_6k(tmp_path,source):
    root,_,plan,_=prepare(tmp_path)
    candidate=tmp_path/"candidate.db"
    shutil.copyfile(resolve_active_generation(root,require_generation=True).role_paths()["canonical"],candidate)
    case=plan["per_case"][0]; q=case["state"]["quarter"][0]
    with sqlite3.connect(candidate) as db:
        db.row_factory=sqlite3.Row; db.execute("BEGIN IMMEDIATE"); upgrade_form6k_candidate_schema(db)
        assert apply_resolution(db,q,[case["evidence"]])=="NOT_FOUND"
        assert apply_resolution(db,q,[case["evidence"]],form6k_reviewed_case=form6k._proof(case["frozen_case"]))=="VERIFIED"
        issuer={**case["evidence"],"source_type":source,"evidence_id":"issuer","evidence_hash":"issuer"}
        assert apply_resolution(db,q,[issuer])=="VERIFIED"
        assert plans.state_for_key(db,natural_key(q))["authority"][0]["result_publication_source"]==source


@pytest.mark.parametrize("mutation",["timestamp","source","quarter","version","depositary","extra_evidence"])
def test_common_apply_rejects_forged_6k_payload(tmp_path,mutation):
    root,_,plan,_=prepare(tmp_path)
    candidate=tmp_path/"candidate.db"
    shutil.copyfile(resolve_active_generation(root,require_generation=True).role_paths()["canonical"],candidate)
    case=plan["per_case"][0]; q=deepcopy(case["state"]["quarter"][0]); proof=deepcopy(form6k._proof(case["frozen_case"]))
    evidence=deepcopy(case["evidence"])
    if mutation=="timestamp": evidence["source_timestamp_utc"]="2026-01-01T00:00:00Z"
    elif mutation=="source": evidence["source_type"]="SEC_8K_ITEM_2_02"
    elif mutation=="quarter": q["quarter_id"]=-1
    elif mutation=="version": proof["authority_version"]="OTHER"
    elif mutation=="depositary":
        from rawcandle.fundamentals.form6k_authority import candidate_binding
        proof["candidates"][0]["identity"]["filer_role"]="DEPOSITARY_BANK"
        proof["candidates"][0]["reviewed_binding"]=candidate_binding(proof["candidates"][0])
    with sqlite3.connect(candidate) as db:
        db.row_factory=sqlite3.Row; db.execute("BEGIN IMMEDIATE"); upgrade_form6k_candidate_schema(db)
        before=plans.state_for_key(db,natural_key(case))
        with pytest.raises(ValueError):
            apply_resolution(db,q,[evidence]* (2 if mutation=="extra_evidence" else 1),form6k_reviewed_case=proof)
        assert plans.state_for_key(db,natural_key(case))==before
