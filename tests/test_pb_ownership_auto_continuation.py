"""Ordinary policy gates and inactive decisions; live data is never a fixture."""
from tests.provider_capture_fixtures import acquired
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import pb_ownership_auto as auto, pb_ownership_review as review
from rawcandle.fundamentals.admin import pb_ownership_publication as publication
from rawcandle.fundamentals.generations import prepare_generation_from_candidates,activate_generation,resolve_active_generation
from rawcandle.fundamentals.schema.prototype import stable_hash
from rawcandle.fundamentals.admin.provider_payload import payload_fingerprint, completeness
from tests.test_fundamentals_pb_new_quarter_review import factory, ASOF, ro, report, digest_db


@pytest.fixture
def ordinary(factory):
    f=factory()
    with sqlite3.connect(f['pp']) as c:
        c.execute("UPDATE sharadar_ticker_metadata SET table_name='fundamentals'")
        c.execute("UPDATE provider_observation SET company_id=1,security_id=1,provider_security_id='1'")
        oid=c.execute("SELECT observation_id FROM provider_observation WHERE fiscalperiod='2026-Q3'").fetchone()[0]
        raw=dict.fromkeys(auto.SF1_FIELDS)
        raw.update(f['provider_row'](3,120,2000))
        c.execute('UPDATE provider_observation SET payload_json=?,content_hash=? WHERE observation_id=?',(json.dumps(raw),stable_hash(raw),oid))
    with sqlite3.connect(f['cp']) as c:
        c.execute("INSERT OR REPLACE INTO provider_security_identity VALUES('SHARADAR','1',1,'AAA','test','2026-08-01T00:00:00Z')")
        c.execute("UPDATE v4_parent_equity_source SET content_hash=? WHERE observation_id=?",(stable_hash(raw),oid))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='full_source')
    f['case']=review.list_cases(f['queue'])[0]
    return f


def evaluate(f, case=None):
    return auto.evaluate(case or f['case'],canonical_db=f['cp'],provider_db=f['pp'],market_db=f['mp'],as_of=ASOF,queue_path=f['queue'])


def mutate_raw(f, change):
    oid=f['case']['new']['observation_id']
    with sqlite3.connect(f['pp']) as c:
        raw=json.loads(c.execute('SELECT payload_json FROM provider_observation WHERE observation_id=?',(oid,)).fetchone()[0]);change(raw)
        c.execute('UPDATE provider_observation SET payload_json=? WHERE observation_id=?',(json.dumps(raw),oid))


def reconcile(f, enabled=True):
    return auto.reconcile(f['queue'],f['cp'],f['pp'],f['mp'],output_root=f['output'],as_of=ASOF,run_id='auto_test',enabled=enabled)


@pytest.mark.parametrize('ticker,delta', [('AMT',-.471390843),('BA',.263157755),('DHR',.077492433),('GM',-3.8637026),('PNR',.010481217),('PSA',6.390070913)])
def test_cohort_delta_is_diagnostic_not_an_arbitrary_threshold(ordinary,ticker,delta):
    f=ordinary;shares=100*(1+delta/100);oid=f['case']['new']['observation_id']
    with sqlite3.connect(f['pp']) as c:
        raw=json.loads(c.execute('SELECT payload_json FROM provider_observation WHERE observation_id=?',(oid,)).fetchone()[0])
        raw.update(sharesbas=shares,marketcap=shares*10,pb=shares*10/2000)
        capture=acquired([raw],full=False)[0].capture
        c.execute("UPDATE provider_observation SET provenance_json=? WHERE observation_id=?",(json.dumps({'source_capture':capture}),oid))
        c.execute('UPDATE provider_observation SET payload_json=?,content_hash=? WHERE observation_id=?',(json.dumps(raw),stable_hash(raw),oid))
        c.execute('UPDATE sharadar_fundamental_observation SET sharesbas=? WHERE observation_id=?',(shares,oid))
    with sqlite3.connect(f['cp']) as c:
        c.execute('UPDATE v4_parent_equity_source SET sharesbas=?,marketcap=?,pb=?,content_hash=? WHERE observation_id=?',(shares,shares*10,shares*10/2000,stable_hash(raw),oid))
        c.execute("UPDATE v4_quarter_financials SET shares_outstanding=? WHERE quarter_id IN (SELECT quarter_id FROM v4_quarter WHERE fiscal_quarter='Q3')",(shares,))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='cohort_'+ticker);f['case']=review.list_cases(f['queue'])[0]
    d=evaluate(f)
    assert d['partition']=='AUTO_CONTINUE',d
    assert d['evidence']['shares_delta']['shares_percent']==pytest.approx(delta)
    assert 'CORPORATE_ACTION_COVERAGE_INCOMPLETE' in d['warnings']


def test_automatic_decision_no_operator_no_active_write_idempotent(ordinary):
    f=ordinary;before=f['cp'].read_bytes();financial=digest_db(f['cp'])
    assert reconcile(f,enabled=False)[0]['partition']=='AUTO_CONTINUE'
    assert review.list_cases(f['queue'])[0]['status']=='OPEN'
    assert reconcile(f)[0]['partition']=='AUTO_CONTINUE'
    case=review.list_cases(f['queue'])[0];a=case['approval']
    assert case['status']==a['decision_type']=='AUTO_CONTINUED'
    assert 'operator' not in a and 'note' not in a and 'operator' not in a['record']
    assert a['policy_version']==auto.POLICY and a['record']['approval_mode']=='AUTO_CONTINUED'
    assert a['decision']['evidence']['observation_id']==case['new']['observation_id']
    assert case['result']['publication_required'] is True
    assert f['cp'].read_bytes()==before and digest_db(Path(case['result']['candidate_canonical']))==financial
    current=report(Path(case['result']['candidate_canonical']),f['mp'])['current']
    assert current['reason']=='OK' and current['ownership_basis_status']=='AUTO_CONTINUED_QUARTER'
    assert reconcile(f)==[]
    with ro(f['queue']) as c:
        assert c.execute("SELECT COUNT(*) FROM refresh_review_queue_audit WHERE event_type='PB_OWNERSHIP_AUTO_CONTINUED'").fetchone()[0]==1


@pytest.mark.parametrize('mutation', ['absent_factor','null_factor','factor_change','missing_field','category','security',
    'source_key','duplicate','corporate_action','adr','equity','price','stale','provenance','policy_hold','unknown_factor',
    'prior_factor_null','history_anomaly','source_review'])
def test_exception_partition_never_decides(ordinary,mutation):
    f=ordinary
    if mutation=='absent_factor': mutate_raw(f,lambda r:r.pop('sharefactor'))
    elif mutation=='null_factor': mutate_raw(f,lambda r:r.update(sharefactor=None))
    elif mutation=='factor_change': mutate_raw(f,lambda r:r.update(sharefactor=2))
    elif mutation=='missing_field': mutate_raw(f,lambda r:r.pop('roa'))
    elif mutation=='source_key': mutate_raw(f,lambda r:r.update(ticker='OTHER'))
    elif mutation=='unknown_factor': mutate_raw(f,lambda r:r.update(sharefactor=0))
    elif mutation in {'category','security','equity','provenance'}:
        sql={'category':"UPDATE v4_parent_equity_source SET category='Other' WHERE fiscalperiod='2026-Q3'",
             'security':"UPDATE security SET security_id=2",'equity':"UPDATE v4_quarter_financials SET parent_equity_usd=NULL",
             'provenance':"UPDATE v4_field_provenance SET transformation='FALLBACK' WHERE canonical_field='shares_outstanding'"}[mutation]
        with sqlite3.connect(f['cp']) as c:c.execute(sql)
    elif mutation=='price':
        with sqlite3.connect(f['mp']) as c:c.execute('DELETE FROM osakedata')
    elif mutation=='duplicate':
        with sqlite3.connect(f['pp']) as c:
            c.row_factory=sqlite3.Row
            for table in ('provider_observation','sharadar_fundamental_observation'):
                row=dict(c.execute(f'SELECT * FROM {table} WHERE observation_id=?',(f['case']['new']['observation_id'],)).fetchone());row['observation_id']='duplicate'
                if table=='provider_observation':row['content_hash']='different-version'
                c.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",tuple(row.values()))
    elif mutation=='corporate_action':
        with sqlite3.connect(f['mp']) as c:
            c.execute('CREATE TABLE splits_data(osake,split_date,split_ratio)');c.execute("INSERT INTO splits_data VALUES('AAA','2026-10-08',2)")
    elif mutation=='adr':
        case=deepcopy(f['case']);case['previous']['economic_unit_rule']='ADS_EQUIVALENTS'
        # Exact stale binding must fail before trusting a modified interpretation.
        f['case']=case
    elif mutation=='stale': f['case']=deepcopy(f['case']);f['case']['candidate_hash']='stale'
    elif mutation=='prior_factor_null':
        f['case']=deepcopy(f['case']);f['case']['previous']['provider_declared_factor']=None
        # Altered candidate bodies cannot be trusted merely by retaining their hash.
        f['case']['candidate_hash']='stale'
    elif mutation=='policy_hold': review.keep_on_hold(f['queue'],f['case']['case_id'],candidate_hash=f['case']['candidate_hash'],note='Hold')
    elif mutation=='history_anomaly':
        with sqlite3.connect(f['pp']) as c:c.execute("UPDATE provider_observation SET provenance_json='{\"history_retention_status\":\"UNKNOWN\"}' WHERE observation_id=?",(f['case']['new']['observation_id'],))
    elif mutation=='source_review':
        with sqlite3.connect(f['queue']) as c:c.execute("INSERT INTO refresh_review_queue(ticker,review_type,reason_codes_json,affected_source_keys_json,fiscal_identities_json,source_evidence_fingerprint,first_seen_at_utc,first_seen_run_id,last_seen_at_utc,last_seen_run_id,status) VALUES('AAA','TICKER_LOCAL_REVIEW','[]','[]','[]','x','now','run','now','run','OPEN')")
    d=evaluate(f);assert d['partition']!='AUTO_CONTINUE',d
    if mutation in {'absent_factor','null_factor','missing_field'}:
        assert 'SOURCE_PAYLOAD_INCOMPLETE' in {r['reason'] for r in d['reasons']}
    with ro(f['queue']) as c: assert c.execute("SELECT COUNT(*) FROM pb_ownership_review WHERE status='AUTO_CONTINUED'").fetchone()[0]==0


def test_pb_reconstruction_failure_blocks(ordinary,monkeypatch):
    original=review.preview
    def broken(*args,**kw):
        r=original(*args,**kw);r['hypothetical_current']['value']*=2;return r
    monkeypatch.setattr(review,'preview',broken)
    assert 'PB_RECONSTRUCTION_FAILED' in {r['reason'] for r in evaluate(ordinary)['reasons']}


@pytest.mark.parametrize('previous,current',[(None,1),(1,None),(1,2),(2,1),(2,2),(2,3)])
def test_exact_factor_transition_matrix(ordinary,previous,current):
    f=ordinary;f['artifact']['records'][0]['provider_declared_factor']=previous
    oid=f['case']['new']['observation_id']
    with sqlite3.connect(f['pp']) as c:
        raw=json.loads(c.execute('SELECT payload_json FROM provider_observation WHERE observation_id=?',(oid,)).fetchone()[0]);raw['sharefactor']=current
        c.execute('UPDATE provider_observation SET payload_json=?,content_hash=? WHERE observation_id=?',(json.dumps(raw),stable_hash(raw),oid))
    with sqlite3.connect(f['cp']) as c:
        c.execute('UPDATE v4_pb_reporting_contract SET review_artifact_sha256=?',(hashlib.sha256(review.serialize(f['artifact']).encode()).hexdigest(),))
        c.execute('UPDATE v4_parent_equity_source SET sharefactor=?,content_hash=? WHERE observation_id=?',(current,stable_hash(raw),oid))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='factor_matrix');f['case']=review.list_cases(f['queue'])[0]
    d=evaluate(f)
    assert d['partition']!='AUTO_CONTINUE'
    assert ('SOURCE_PAYLOAD_INCOMPLETE' if previous is None or current is None else 'FACTOR_REVIEW_REQUIRED') in {r['reason'] for r in d['reasons']}


def test_exact_ads_interpretation_is_manual(ordinary):
    f=ordinary;f['artifact']['records'][0].update(economic_unit_rule='ADS_EQUIVALENTS',reviewed_security_type='ADS',release_type='ADR_FACTOR',exact_factor_numerator=1,exact_factor_denominator=1)
    with sqlite3.connect(f['cp']) as c:c.execute('UPDATE v4_pb_reporting_contract SET review_artifact_sha256=?',(hashlib.sha256(review.serialize(f['artifact']).encode()).hexdigest(),))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='adr');f['case']=review.list_cases(f['queue'])[0]
    d=evaluate(f)
    assert d['partition']=='MANUAL_REVIEW' and 'UNSUPPORTED_OWNERSHIP_TYPE' in {r['reason'] for r in d['reasons']}


def test_auto_evidence_change_after_partition_blocks_decision(ordinary):
    f=ordinary;d=evaluate(f);mutate_raw(f,lambda r:r.update(sharefactor=None))
    with pytest.raises(ValueError,match='AUTO_EVIDENCE_CHANGED'):
        review._approve(f['queue'],f['case']['case_id'],candidate_hash=f['case']['candidate_hash'],canonical_db=f['cp'],
            market_db=f['mp'],provider_db=f['pp'],output_root=f['output'],as_of=ASOF,confirmed=True,automatic=d)


@pytest.mark.parametrize('ticker',['GE','RTX','T'])
def test_complete_repaired_factor_one_is_eligible(ordinary,ticker):
    f=ordinary;oid=f['case']['new']['observation_id']
    with sqlite3.connect(f['pp']) as c:
        raw=json.loads(c.execute('SELECT payload_json FROM provider_observation WHERE observation_id=?',(oid,)).fetchone()[0])
        binding={'new_observation_id':oid,'new_content_hash':payload_fingerprint(raw),'new':completeness(raw)}
        c.execute('UPDATE provider_observation SET content_hash=?,provenance_json=? WHERE observation_id=?',
                  (binding['new_content_hash'],json.dumps({'source_payload_repair':binding,'source_capture':acquired([raw],full=False)[0].capture}),oid))
    with sqlite3.connect(f['cp']) as c:c.execute('UPDATE v4_parent_equity_source SET content_hash=? WHERE observation_id=?',(binding['new_content_hash'],oid))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='repaired_'+ticker);f['case']=review.list_cases(f['queue'])[0]
    assert evaluate(f)['partition']=='AUTO_CONTINUE'


def test_counterparty_corporate_action_blocks(ordinary):
    f=ordinary
    with sqlite3.connect(f['pp']) as c:
        c.execute("INSERT INTO sharadar_action_metadata(date,action,ticker,name,value,contraticker,contraname,payload_json,fetched_at_utc) VALUES('2026-10-08','spinoff','OTHER','Other',1,'AAA','AAA','{}','now')")
    assert 'CORPORATE_ACTION_BLOCKER' in {r['reason'] for r in evaluate(f)['reasons']}


def test_registry_reconciliation_invalidates_automatic_evidence_with_audit(ordinary):
    f=ordinary;reconcile(f);old=review.list_cases(f['queue'])[0]
    f['artifact']['registry_revision']='unrelated_change'
    with sqlite3.connect(f['cp']) as c:c.execute('UPDATE v4_pb_reporting_contract SET review_artifact_sha256=?',(hashlib.sha256(review.serialize(f['artifact']).encode()).hexdigest(),))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='registry_change')
    fresh=review.list_cases(f['queue'])[0]
    assert fresh['status']=='OPEN' and fresh['approval'] is None and fresh['result'] is None
    assert fresh['candidate_hash']!=old['candidate_hash']
    with ro(f['queue']) as c:
        event=json.loads(c.execute("SELECT evidence_json FROM refresh_review_queue_audit WHERE event_type='PB_OWNERSHIP_AUTO_INVALIDATED'").fetchone()[0])
    assert event['previous_approval']==old['approval'] and event['previous_result']==old['result']
    assert reconcile(f)[0]['partition']=='AUTO_CONTINUE'


def test_reconciled_hold_cannot_be_cleared_by_automatic_policy(ordinary):
    f=ordinary
    review.keep_on_hold(f['queue'],f['case']['case_id'],candidate_hash=f['case']['candidate_hash'],note='Explicit interpretation hold')
    f['artifact']['registry_revision']='unrelated_change'
    with sqlite3.connect(f['cp']) as c:c.execute('UPDATE v4_pb_reporting_contract SET review_artifact_sha256=?',(hashlib.sha256(review.serialize(f['artifact']).encode()).hexdigest(),))
    review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='hold_rebind');f['case']=review.list_cases(f['queue'])[0]
    d=evaluate(f)
    assert d['partition']=='MANUAL_REVIEW' and 'EXPLICIT_POLICY_HOLD' in {r['reason'] for r in d['reasons']}


def test_automatic_decision_uses_existing_generation_lifecycle(ordinary,tmp_path):
    f=ordinary;reconcile(f)
    root=tmp_path/'project';inputs={}
    for role,key in [('provider','pp'),('canonical','cp'),('analysis','ap')]:
        p=root/'inputs'/(role+'.db');p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f[key],p);inputs[role]=p
    generation=prepare_generation_from_candidates(inputs,generation_id='before_auto',project_root=root,source='TEST')
    activate_generation(generation['manifest'],project_root=root)
    shutil.copyfile(f['mp'],root/'data/osakedata.db');shutil.copyfile(f['ap'],root/'data/analysis.db')
    w=publication.OwnershipPublicationWorkflow(project_root=root,run_root=root/'reports/admin_runs',as_of=ASOF)
    w.queue_path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f['queue']) as s,sqlite3.connect(w.queue_path) as d:s.backup(d)
    p=w.preview([f['case']['case_id']])
    result=w.publish(p['preview_id'],preview_hash=p['preview_hash'],operator='Publication operator',confirmed=True,rehearsal=True)
    assert result['outcome']=='COMPLETED'
    current=resolve_active_generation(root)
    assert report(current.role_paths()['canonical'],root/'data/osakedata.db')['current']['ownership_basis']['approval_mode']=='AUTO_CONTINUED'
    assert review.list_cases(w.queue_path,include_resolved=True)[0]['status']=='PUBLISHED'
    assert review.detect(ro(current.role_paths()['canonical']),as_of=ASOF)==[]
