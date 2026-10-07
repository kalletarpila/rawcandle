from copy import deepcopy
from contextlib import closing
import json
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin import production_transaction as transaction
from rawcandle.fundamentals.admin import form6k_reviewed_publication_plan as form6k
from rawcandle.fundamentals.admin import reviewed_publication_plan as plans
from rawcandle.fundamentals.admin.publication_journal import (
    load_journal, sha256_file, PublicationRecoveredRetryRequired, PublicationRecoveryError,
)
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.result_publication import SecClient, SecFiling, SOURCE_RANK
from tests.test_form6k_reviewed_publication_plan import prepare, reseal, DAY
from tests.test_policy_reviewed_publication_plan import forbid_network


def production_mode(monkeypatch, root):
    """Exercise ROOT equality and real locks without any production file access."""
    monkeypatch.setattr(drain, "ROOT", root)
    monkeypatch.setattr(transaction, "ROOT", root)
    (root / "scheduler_config.json").write_text(json.dumps({
        "enabled_markets": ["usa"], "run_time": "04:30",
        "osakedata_db_path": str(root / "data/osakedata.db"),
        "analysis_db_path": str(root / "data/analysis.db"), "log_dir": str(root / "logs"),
    }))


def hashes(root):
    b = resolve_active_generation(root, require_generation=True)
    return {k: sha256_file(p) for k, p in b.role_paths().items()}


def run(root, path, **kwargs):
    return drain.run_backlog_drain(project_root=root, reviewed_apply_plan=path, apply=True,
                                   confirm_production=True, as_of_date=DAY, **kwargs)


def test_valid_production_mode_gate_uses_candidate_only(tmp_path, monkeypatch):
    forbid_network(monkeypatch)
    root, path, plan, _ = prepare(tmp_path)
    production_mode(monkeypatch, root)
    old = resolve_active_generation(root, require_generation=True)
    old_hashes = hashes(root)
    config_hash = sha256_file(root / "scheduler_config.json")
    financial = plans._canonical_digest(old.role_paths()["canonical"])
    keys = tuple(tuple(k) for k in plan["prepared_keys"])
    outside = plans._canonical_digest(old.role_paths()["canonical"], excluded_keys=keys, publication_only=True)
    original_upgrade = form6k.upgrade_form6k_candidate_schema
    called = []

    def candidate_only(db):
        actual = db.execute("PRAGMA database_list").fetchone()[2]
        assert "/temp/publication_drain_" in actual and actual != str(old.role_paths()["canonical"])
        assert db.in_transaction
        with closing(sqlite3.connect(old.role_paths()["canonical"].as_uri() + "?mode=ro", uri=True)) as source:
            assert "SEC_FORM_6K_RESULT" not in source.execute(
                "SELECT sql FROM sqlite_master WHERE name='v4_result_publication_authority'").fetchone()[0]
        called.append(actual)
        return original_upgrade(db)

    monkeypatch.setattr(form6k, "upgrade_form6k_candidate_schema", candidate_only)
    result = run(root, path)
    assert result["status"] == "SUCCESS" and len(called) == 1
    assert result["publication"]["applied_count"] == 9
    assert result["publication"]["network"]["network_requests"] == 0
    new = resolve_active_generation(root, require_generation=True)
    assert plans._canonical_digest(new.role_paths()["canonical"]) == financial
    assert plans._canonical_digest(new.role_paths()["canonical"], excluded_keys=keys, publication_only=True) == outside
    assert {k: sha256_file(p) for k,p in old.role_paths().items()} == old_hashes
    assert sha256_file(root / "scheduler_config.json") == config_hash
    assert (root / "logs/scheduler.lock").exists() or list((root / "logs").glob("*lock*"))
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    assert journal["state"] == "COMPLETED" and journal["postflight_state"] == "PASSED"
    for key,value in plans.plan_scope_evidence(plan).items(): assert journal["scope_evidence"][key] == value


@pytest.mark.parametrize("field,value",[("schema_version",1),("schema_version",2),("policy_mode","OTHER"),
    ("authority_version","OTHER"),("source_type","SEC_FILING_FALLBACK"),("source_rank",3),
    ("confidence","HIGH"),("prepared_keys",[]),("aggregate_decision_fingerprint","0"*64),
    ("reviewed_cohort_fingerprint","0"*64),("prepared_keys_fingerprint","0"*64)])
def test_live_gate_contract_substitution_rejected(tmp_path,monkeypatch,field,value):
    root,path,plan,_=prepare(tmp_path)
    production_mode(monkeypatch,root)
    before=hashes(root)
    plan[field]=value; reseal(plan)
    changed=tmp_path/"forged.json"; changed.write_text(json.dumps(plan))
    with pytest.raises(ValueError): run(root,changed)
    assert hashes(root)==before
    assert not (root/"data/.fundamentals_admin_publication_journal.json").exists()


@pytest.mark.parametrize("mutation",["tamper","missing_decision","widen","held_identity","held_time"])
def test_live_gate_exact_frozen_plan_required(tmp_path,monkeypatch,mutation):
    root,_,plan,_=prepare(tmp_path)
    production_mode(monkeypatch,root)
    if mutation=="tamper": plan["plan_id"]="CHANGED"
    elif mutation=="missing_decision": plan["form6k_cases"][0].pop("decision_fingerprint"); reseal(plan)
    elif mutation=="widen": plan["prepared_keys"].append([2525,2026,"Q2"]); reseal(plan)
    else:
        held=next(c for c in plan["form6k_cases"] if c["ticker"]==("IQMX" if mutation=="held_identity" else "BABA"))
        held["decision"]["final_result"]="UNIQUE"; reseal(plan)
    path=tmp_path/"forged.json"; path.write_text(json.dumps(plan))
    with pytest.raises(ValueError): run(root,path)


@pytest.mark.parametrize("drift",["generation","authority","security","cik","issuer_verified","8k_verified","rank2_conflict"])
def test_live_gate_state_drift_fails_before_candidate(tmp_path,monkeypatch,drift):
    root,path,plan,_=prepare(tmp_path)
    production_mode(monkeypatch,root)
    original=drain.revalidate_plan_state
    key=tuple(plan["prepared_keys"][0])

    def changed(plan,binding,**kwargs):
        # Supply an inactive source copy as the bound role, never mutate finalized DBs.
        clone=tmp_path/"drift.db"; shutil.copyfile(binding.role_paths()["canonical"],clone)
        with sqlite3.connect(clone) as db:
            if drift=="authority": db.execute("UPDATE v4_result_publication_authority SET status_reason='DRIFT' WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?",key)
            elif drift=="security": db.execute("UPDATE security SET security_id=security_id+100000 WHERE company_id=?",key[:1])
            elif drift=="cik": db.execute("UPDATE company_cik SET cik_normalized='0000000001' WHERE company_id=?",key[:1])
            elif drift.endswith("verified") or drift=="rank2_conflict":
                from rawcandle.fundamentals.result_publication import apply_resolution
                c=plan["per_case"][0]
                e={**c["evidence"],"source_type":{"issuer_verified":"ISSUER_EARNINGS_RELEASE", "8k_verified":"SEC_8K_ITEM_2_02","rank2_conflict":"SEC_FILING_FALLBACK"}[drift],
                   "source_timestamp_utc":"2026-01-01T00:00:00Z","evidence_id":"drift","evidence_hash":"drift"}
                db.row_factory=sqlite3.Row; apply_resolution(db,c["state"]["quarter"][0],[e])
        class Bound:
            generation_id="CHANGED" if drift=="generation" else binding.generation_id
            manifest=binding.manifest
            def role_paths(self): return {**binding.role_paths(),"canonical":clone}
        return original(plan,Bound(),**kwargs)

    monkeypatch.setattr(drain,"revalidate_plan_state",changed)
    def deny(*a,**kw): raise AssertionError("CANDIDATE_FORBIDDEN")
    monkeypatch.setattr(drain,"run_plan_candidate",deny)
    before=hashes(root)
    with pytest.raises(RuntimeError,match="DRIFT"): run(root,path)
    assert hashes(root)==before


def test_live_gate_confirmation_required_before_lock(tmp_path,monkeypatch):
    root,path,_,_=prepare(tmp_path); production_mode(monkeypatch,root)
    def deny(*a,**kw): raise AssertionError("LOCK_FORBIDDEN")
    monkeypatch.setattr(drain,"production_lock",deny)
    with pytest.raises(PermissionError,match="CONFIRMATION_REQUIRED"):
        drain.run_backlog_drain(project_root=root,apply=True,reviewed_apply_plan=path,as_of_date=DAY)


def test_live_gate_migration_failure_never_activates(tmp_path,monkeypatch):
    root,path,_,_=prepare(tmp_path); production_mode(monkeypatch,root)
    before=hashes(root)
    original=form6k.upgrade_form6k_candidate_schema
    def fail(db):
        original(db)
        raise RuntimeError("INJECTED_MIGRATION_FAILURE")
    monkeypatch.setattr(form6k,"upgrade_form6k_candidate_schema",fail)
    with pytest.raises(RuntimeError,match="INJECTED_MIGRATION_FAILURE"): run(root,path)
    assert hashes(root)==before
    assert not (root/"data/.fundamentals_admin_publication_journal.json").exists()
    assert not list((root/"temp").glob("publication_drain_*"))


@pytest.mark.parametrize("stage",["AFTER_PREPARED","AFTER_NEW_GENERATION_READY","AFTER_GENERATION_ACTIVATION"])
def test_live_gate_recovery_requires_identical_plan(tmp_path,monkeypatch,stage):
    root,path,plan,_=prepare(tmp_path); production_mode(monkeypatch,root)
    before=hashes(root)
    with pytest.raises(transaction.SimulatedTransactionCrash): run(root,path,inject_crash_at=stage)
    with pytest.raises(PublicationRecoveredRetryRequired): run(root,path)
    assert hashes(root)==before
    with pytest.raises(RuntimeError,match="SAME_PLAN"):
        drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,as_of_date=DAY)
    with pytest.raises(RuntimeError,match="SAME_PLAN"):
        drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,as_of_date=DAY,exact_quarter_allowlist=plan["prepared_keys"])
    other=deepcopy(plan); other["plan_id"]="OTHER"; reseal(other)
    other_path=tmp_path/"other.json"; other_path.write_text(json.dumps(other))
    with pytest.raises(RuntimeError,match="SAME_PLAN"): run(root,other_path)
    from tests.test_reviewed_publication_plan import prepare as legacy_prepare
    from tests.test_policy_reviewed_publication_plan import prepare as policy_prepare
    for name,factory in (("legacy",legacy_prepare),("policy",policy_prepare)):
        directory=tmp_path/name; directory.mkdir()
        _,foreign_path,_,_=factory(directory)
        with pytest.raises(RuntimeError,match="SAME_PLAN"): run(root,foreign_path)
    assert run(root,path)["status"]=="SUCCESS"


def test_live_gate_recovery_failed_blocks_new_writer(tmp_path,monkeypatch):
    root,path,_,_=prepare(tmp_path); production_mode(monkeypatch,root)
    j=root/"data/.fundamentals_admin_publication_journal.json"
    j.write_text(json.dumps({"journal_format_version":1,"state":"RECOVERY_FAILED"}))
    with pytest.raises(PublicationRecoveryError,match="RECOVERY_FAILED"): run(root,path)


@pytest.mark.parametrize("scope",["default","exact"])
def test_live_root_default_and_exact_still_cannot_discover_6k(tmp_path,monkeypatch,scope):
    root,_,plan,_=prepare(tmp_path); production_mode(monkeypatch,root)
    class ForeignOnly(SecClient):
        def item_2_02_filings(self,cik,**kwargs):
            return [SecFiling(accession_number="0001213900-26-094402",form="6-K",items="2.02",
                acceptance_timestamp_utc="2026-08-27T20:30:01Z",primary_document="form6k.htm",
                source_reference="https://www.sec.gov/Archives/edgar/data/1474627/000121390026094402/form6k.htm",
                text="Item 2.02 Results of Operations. Quarter ended June 30, 2026. Revenue and net income.")]
    result=drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,as_of_date=DAY,client=ForeignOnly(),
        **({"exact_quarter_allowlist":plan["prepared_keys"]} if scope=="exact" else {}))
    with sqlite3.connect(resolve_active_generation(root,require_generation=True).role_paths()["canonical"]) as db:
        assert db.execute("SELECT count(*) FROM v4_result_publication_authority WHERE result_publication_source='SEC_FORM_6K_RESULT'").fetchone()[0]==0
        assert "SEC_FORM_6K_RESULT" not in db.execute("SELECT sql FROM sqlite_master WHERE name='v4_result_publication_authority'").fetchone()[0]
    assert "SEC_FORM_6K_RESULT" not in SOURCE_RANK


@pytest.mark.parametrize("mode",["legacy","policy"])
def test_other_reviewed_modes_keep_their_live_root_contract(tmp_path,monkeypatch,mode):
    from tests.test_reviewed_publication_plan import prepare as legacy_prepare
    from tests.test_policy_reviewed_publication_plan import prepare as policy_prepare
    factory=legacy_prepare if mode=="legacy" else policy_prepare
    root,path,plan,_=factory(tmp_path)
    production_mode(monkeypatch,root)
    forbid_network(monkeypatch)
    result=run(root,path)
    assert result["status"]=="SUCCESS"
    assert result["publication"]["applied_count"]==plan["prepared_key_count"]
    with sqlite3.connect(resolve_active_generation(root,require_generation=True).role_paths()["canonical"]) as db:
        assert "SEC_FORM_6K_RESULT" not in db.execute("SELECT sql FROM sqlite_master WHERE name='v4_result_publication_authority'").fetchone()[0]
