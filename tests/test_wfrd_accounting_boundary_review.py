from __future__ import annotations
from tests.provider_capture_fixtures import acquired, trusted_history

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import accounting_boundary_review as b
from rawcandle.fundamentals.admin import refresh_copy_runtime as runtime
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    FINANCIAL_FIELDS, load_current_history, validate_complete_history,
)
from rawcandle.fundamentals.admin.refresh_review_queue import classify_review_scope, partition_changes
from rawcandle.fundamentals.schema.migrations import (
    bootstrap_database, PROVIDER_SCHEMA_SQL, CANONICAL_SCHEMA_SQL,
)
from rawcandle.fundamentals.phase12d import _provider_winners

NOW='2026-10-26T12:00:00Z'


def row(key,label,**values):
    ticker,dimension,day,period=key
    r=dict.fromkeys(FINANCIAL_FIELDS)
    r.update(ticker=ticker,dimension=dimension,date=day,reportperiod=period,
             calendardate='2019-12-31' if period=='2019-12-13' else period,
             fiscalperiod=label,lastupdated='2026-07-22')
    r.update(values)
    return r


def trusts(arq,mrq):
    return {d:trusted_history(rows,ticker='WFRD',dimension=d)
            for d,rows in (('ARQ',arq),('MRQ',mrq))}


def receipt(p):
    r={'proposal_fingerprint':p['proposal_fingerprint'],'passed':True,'mode':'COPY_ONLY',
       'checks':{k:True for k in ('both_q4s','established_dates','no_existing_financial_change','unrelated_tickers','historical_only_archive','mrq_nonfinancial','pb_arq_binding')}}
    r['receipt_fingerprint']=fingerprint(r)
    return r


@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'_events',lambda:())
    provider=tmp_path/'provider.db';canonical=tmp_path/'canonical.db'
    bootstrap_database(provider,'fundamentals_provider',PROVIDER_SCHEMA_SQL,NOW)
    bootstrap_database(canonical,'fundamentals_v4',CANONICAL_SCHEMA_SQL,NOW)
    identity={'status':'KNOWN','ticker':'WFRD','company_id':1,'security_id':1,
              'company_key':'SEC_CIK:0001603923','current_ticker':'WFRD',
              'provider_security_id':'635310','provider_ticker':'WFRD','metadata_available':True}
    with sqlite3.connect(canonical) as c:
        for cid,ticker,pid in ((1,'WFRD','635310'),(2,'OTHER','200')):
            c.execute('INSERT INTO company VALUES(?,?,?,\'ACTIVE\',?,?)',(cid,identity['company_key'] if cid==1 else 'OTHER',ticker,NOW,NOW))
            c.execute("INSERT INTO security VALUES(?,?,?,'NASDAQ',1,NULL,NULL,?,?)",(cid,cid,ticker,NOW,NOW))
            c.execute("INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?,'fixture',?)",(pid,cid,ticker,NOW))
    arq=row(b.ARQ_KEY,'2019-Q4',assets=7293000000,cashneq=800000000,
            debt=2164000000,sharesbas=69999966,shareswa=69999966,
            equity=2880000000,equityusd=2880000000,price=7.25,pb=.176,marketcap=507499754,sharefactor=1)
    genuine=row(('WFRD','ARQ','2021-02-19','2020-12-31'),'2020-Q4',
                revenue=842000000,netinc=-200000000,sharesbas=70017356,
                equity=907000000,equityusd=907000000)
    old=row(b.OLD_MRQ_KEY,'2019-Q4',assets=7293000000,cashneq=800000000,
            debt=2456000000,sharesbas=69999966,shareswa=69999966)
    stub=row(b.CURRENT_MRQ_KEY,'2019-Q4',lastupdated='2026-10-22',
             ncfo=-68000000,capex=-73000000,fcf=-141000000,shareswa=1004000000)
    initial=trusts([arq,genuine],[old])
    other=row(('OTHER','ARQ','2021-02-19','2020-12-31'),'2020-Q4',revenue=99,sharesbas=10)
    otherhist={d:trusted_history([dict(other,dimension=d)],ticker='OTHER',dimension=d) for d in ('ARQ','MRQ')}
    runtime.replace_provider_histories(provider,{'WFRD':initial,'OTHER':otherhist},
        {'WFRD':identity,'OTHER':dict(identity,ticker='OTHER',company_id=2,security_id=2,provider_security_id='200')},applied_at=NOW)
    runtime.fresh_rebuild_canonical(provider,canonical,applied_at=NOW)
    incoming=trusts([dict(arq,fiscalperiod='2020-Q4',lastupdated='2026-10-22'),genuine],[stub])
    proposal=b.create_proposal(provider,canonical,incoming,identity,created_at=NOW)
    proof=b.rehearse(proposal,provider,canonical,incoming,identity,tmp_path/'approval_rehearsal')
    fixture_queue=tmp_path/'fixture_approval_queue.db'
    b.save_item(fixture_queue,proposal,rehearsal=proof)
    decision=b.approve_registered(fixture_queue,proposal['resolution_id'],operator='fixture-operator',
        proposal_fingerprint=proposal['proposal_fingerprint'],receipt_fingerprint=proof['receipt_fingerprint'],
        provider_db=provider,canonical_db=canonical,histories=incoming,identity=identity)['decision']
    return {'p':provider,'c':canonical,'h':incoming,'identity':identity,
            'proposal':proposal,'decision':decision,'receipt':proof,'tmp':tmp_path}


def approve_queue(case, queue, **overrides):
    arguments = dict(operator='fixture-operator', proposal_fingerprint=case['proposal']['proposal_fingerprint'],
                     receipt_fingerprint=case['receipt']['receipt_fingerprint'], provider_db=case['p'],
                     canonical_db=case['c'], histories=case['h'], identity=case['identity'])
    arguments.update(overrides)
    return b.approve_registered(queue, case['proposal']['resolution_id'], **arguments)


def apply(case):
    a=b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])
    assert a['applied'],a
    runtime.replace_provider_histories(case['p'],{'WFRD':case['h']},{'WFRD':case['identity']},
        applied_at=NOW,boundary_applications={'WFRD':a})
    runtime.fresh_rebuild_canonical(case['p'],case['c'],applied_at=NOW,affected_company_ids=[1])
    return a


def test_proposal_is_non_authoritative_and_binds_both_exact_actions(case):
    p=case['proposal'];e=b.verify(p)
    assert p['status']=='OPEN' and p['operator'] is None and p['production_authorized'] is False
    assert e['arq']['action']==b.PRESERVE and e['mrq']['action']==b.RETAIN
    assert e['arq']['accepted']['provider_observation']['observation_id']
    assert e['mrq']['accepted']['provider_observation']['payload_json']
    assert e['mrq']['absence_proof']['status']=='COMPLETE'
    assert not b.evaluate(case['p'],case['c'],case['h'],case['identity'])['applied']
    assert b.validate_pending(p,case['p'],case['c'],case['h'],case['identity'])


def test_unapproved_and_unsupported_reviews_stay_global(case):
    current={d:load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    raw=b.comparison('WFRD',current,case['h'],{'applied':False})
    raw['identity']=case['identity']
    assert classify_review_scope(raw)['scope']=='GLOBAL_BLOCKING_REVIEW'
    assert len(partition_changes([raw])['global_blockers'])==1
    other=deepcopy(raw);other['ticker']='OTHER'
    assert classify_review_scope(other)['scope']=='GLOBAL_BLOCKING_REVIEW'


def test_both_actions_required_and_exact_approved_comparison_is_explicit(case):
    current={d:load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    a=b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])
    r=b.comparison('WFRD',current,case['h'],a);r['identity']=case['identity']
    assert r['classification']!='REVIEW_REQUIRED'
    assert r['accounting_boundary_resolution']['applied']
    assert r['effective_canonical_identity']['provider_label']=='2020-Q4'
    assert r['effective_canonical_identity']['effective_label']=='2019-Q4'
    assert {x['event'] for x in r['reviewed_accounting_events']}=={'FISCAL_IDENTITY_REVISION','TRUE_SOURCE_REMOVAL'}
    assert not partition_changes([r])['global_blockers']
    assert 'fiscal_revision_approval' not in r and 'true_removal_approval' not in r


@pytest.mark.parametrize('dimension,field,value',[
    ('ARQ','revenue',1),('ARQ','fiscalperiod','2021-Q4'),('ARQ','date','2020-03-17'),
    ('ARQ','reportperiod','2019-12-30'),('ARQ','lastupdated','2026-10-23'),
    ('ARQ','ticker','OTHER'),('ARQ','dimension','MRQ'),('ARQ','equity',1),
    ('MRQ','ncfo',-1),('MRQ','fiscalperiod','2020-Q4'),('MRQ','date','2019-12-14'),
    ('MRQ','reportperiod','2019-12-14'),('MRQ','lastupdated','2026-10-23')])
def test_source_drift_fails_closed(case,dimension,field,value):
    h=case['h'].copy();rows=[deepcopy(r.get('_acquisition_payload',r)) for r in h[dimension].rows]
    index=next(i for i,r in enumerate(rows) if r['reportperiod']==('2019-12-31' if dimension=='ARQ' else '2019-12-13'))
    rows[index][field]=value
    h[dimension]=trusted_history(rows,ticker='WFRD',dimension=dimension)
    a=b.evaluate(case['p'],case['c'],h,case['identity'],decision=case['decision'])
    assert a['stale'] and not a['applied']


@pytest.mark.parametrize('field,value',[('company_id',2),('security_id',2),('provider_security_id','200'),('company_key','OTHER'),('current_ticker','OTHER')])
def test_identity_drift_rejects(case,field,value):
    i=dict(case['identity'],**{field:value})
    assert b.evaluate(case['p'],case['c'],case['h'],i,decision=case['decision'])['stale']


@pytest.mark.parametrize('table,sql',[
    ('canonical',"UPDATE v4_quarter SET quarter_id=99 WHERE fiscal_year=2019"),
    ('canonical',"UPDATE v4_quarter SET fiscal_year=2018 WHERE fiscal_year=2019"),
    ('canonical',"UPDATE v4_quarter SET first_public_result_date='2020-03-17' WHERE fiscal_year=2019"),
    ('provider',"UPDATE provider_observation SET observation_id=observation_id||'changed' WHERE observation_id=(SELECT observation_id FROM sharadar_fundamental_observation WHERE ticker='WFRD' AND dimension='ARQ' AND reportperiod='2019-12-31')"),
    ('provider',"UPDATE provider_observation SET payload_json='{}' WHERE observation_id=(SELECT observation_id FROM sharadar_fundamental_observation WHERE ticker='WFRD' AND dimension='MRQ')")])
def test_accepted_evidence_and_baseline_drift_rejects(case,table,sql):
    with sqlite3.connect(case['c'] if table=='canonical' else case['p']) as c:c.execute(sql)
    assert b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])['stale']


def test_mrq_reappearance_and_incomplete_response_reject(case):
    old=case['proposal']['evidence']['mrq']['accepted']['normalized']
    rows=[r['_acquisition_payload'] for r in case['h']['MRQ'].rows]+[old]
    h={**case['h'],'MRQ':trusted_history(rows,ticker='WFRD',dimension='MRQ')}
    assert b.evaluate(case['p'],case['c'],h,case['identity'],decision=case['decision'])['stale']
    h['MRQ']=validate_complete_history(rows[:1],ticker='WFRD',dimension='MRQ',response_reached_limit=True)
    assert b.evaluate(case['p'],case['c'],h,case['identity'],decision=case['decision'])['stale']


@pytest.mark.parametrize('section,field,value',[
    ('mrq','historical_calculation_eligible',True),('mrq','current_role','ORDINARY_QUARTER'),
    ('arq','accepted_label','2020-Q4'),('mrq','context',{'calculation_eligible':True})])
def test_tampered_proposal_rejects(case,section,field,value):
    d=deepcopy(case['decision']);d['proposal']['evidence'][section][field]=value
    a=b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=d)
    assert a['stale']


def test_queue_registration_does_not_approve_and_stale_reopens_separate_global_item(case):
    q=case['tmp']/'queue.db';p=case['proposal']
    b.save_item(q,p,rehearsal=case['receipt'])
    assert b.read_items(q)[0]['status']=='OPEN' and b.queued_decision(q,'WFRD') is None
    approved=approve_queue(case,q)
    assert b.queued_decision(q,'OTHER') is None
    assert b.queued_decision(q,'WFRD')==approved['decision']
    b.save_item(q,p,stale_reason='financial drift')
    assert b.read_items(q)[0]['status']=='STALE' and b.queued_decision(q,'WFRD') is None
    with sqlite3.connect(q) as c:assert c.execute(f'SELECT count(*) FROM {b.QUEUE}_audit').fetchone()[0]==3


def test_candidate_preserves_raw_arq_both_quarters_dates_and_pb(case):
    apply(case)
    with b._ro(case['p']) as p:
        arq=dict(p.execute("SELECT * FROM sharadar_fundamental_observation WHERE ticker='WFRD' AND dimension='ARQ' AND reportperiod='2019-12-31'").fetchone())
        assert arq['fiscalperiod']=='2020-Q4'
        assert b.effective_fiscalperiod(p,arq)=='2019-Q4'
        for key,value in (('ticker','OTHER'),('dimension','MRQ'),('date','2020-03-17'),('reportperiod','2020-12-31')):
            assert b.effective_fiscalperiod(p,dict(arq,**{key:value}))=='2020-Q4'
    with b._ro(case['c']) as c:
        qs=[tuple(r) for r in c.execute("SELECT fiscal_year,period_end,first_public_result_date FROM v4_quarter WHERE company_id=1 ORDER BY fiscal_year")]
        assert qs==[(2019,'2019-12-31','2020-03-16'),(2020,'2020-12-31','2021-02-19')]
        assert tuple(c.execute("SELECT f.parent_equity,s.fiscalperiod,s.effective_fiscalperiod,s.dimension FROM v4_parent_equity_source s JOIN v4_quarter q USING(quarter_id) JOIN v4_quarter_financials f USING(quarter_id) WHERE q.company_id=1 AND q.fiscal_year=2019").fetchone())==(2880000000,'2020-Q4','2019-Q4','ARQ')
        assert c.execute('SELECT revenue FROM v4_quarter_financials f JOIN v4_quarter q USING(quarter_id) WHERE company_id=2').fetchone()[0]==99
        assert c.execute('SELECT operating_cashflow FROM v4_quarter_financials f JOIN v4_quarter q USING(quarter_id) WHERE company_id=1 AND fiscal_year=2019').fetchone()[0] is None


def test_archive_is_immutable_separate_queryable_and_survives_replacement(case):
    apply(case);archive=b.historical_evidence(case['p'])
    assert len(archive)==1 and archive[0]['original']==case['proposal']['evidence']['mrq']['accepted']
    assert archive[0]['calculation_eligible'] is False
    current=b.current_provider_history(case['p'],'WFRD','MRQ')
    assert len(current)==1 and b._key(current[0]['observation'])==b.CURRENT_MRQ_KEY
    context=current[0]['context']
    assert all(context[k] is False for k in ('calculation_eligible','full_quarter_eligible','canonical_eligible','ttm_eligible','share_pb_eligible','stock_fallback_eligible'))
    assert current[0]['observation']['assets'] is None and archive[0]['original']['normalized']['ncfo'] is None
    with sqlite3.connect(case['p']) as c:
        for op in (f'DELETE FROM {b.ARCHIVE}',f"UPDATE {b.ARCHIVE} SET record_json='{{}}'"):
            with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE'):c.execute(op)
    runtime.replace_provider_histories(case['p'],{'WFRD':case['h']},{'WFRD':case['identity']},applied_at='2026-10-27T12:00:00Z')
    assert b.historical_evidence(case['p'])==archive
    assert len(load_current_history(case['p'],'WFRD','MRQ')['rows'])==1
    assert _provider_winners(case['p'])[1]['winner_rows']==3
    assert len([x for x in b.combined_evidence(case['p']) if x['membership']=='HISTORICAL_ONLY'])==1


def test_published_lifecycle_allows_unrelated_quarter_and_rejects_reappearance(case):
    apply(case)
    rows=[r['_acquisition_payload'] for r in case['h']['ARQ'].rows]
    rows.append(row(('WFRD','ARQ','2021-05-01','2021-03-31'),'2021-Q1',revenue=1))
    h={**case['h'],'ARQ':trusted_history(rows,ticker='WFRD',dimension='ARQ')}
    a=b.evaluate(case['p'],case['c'],h,case['identity'])
    assert a['applied'] and a['phase']=='PUBLISHED'
    current={d:load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    result=b.comparison('WFRD',current,h,a)
    assert result['classification']!='REVIEW_REQUIRED'
    assert not any(e['event']=='TRUE_SOURCE_REMOVAL' for e in result['source_history_events'])
    old=case['proposal']['evidence']['mrq']['accepted']['normalized']
    h['MRQ']=trusted_history([r['_acquisition_payload'] for r in h['MRQ'].rows]+[old],ticker='WFRD',dimension='MRQ')
    a=b.evaluate(case['p'],case['c'],h,case['identity'])
    assert a['stale']
    result=b.comparison('WFRD',current,h,a);result['identity']=case['identity']
    assert classify_review_scope(result)['scope']=='GLOBAL_BLOCKING_REVIEW'
    assert len(b.historical_evidence(case['p']))==1


def test_complete_copy_rehearsal_preserves_source_databases_and_proposal(case):
    import hashlib
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (case['p'],case['c'])}
    report=b.rehearse(case['proposal'],case['p'],case['c'],case['h'],case['identity'],case['tmp']/'rehearsal')
    assert report['passed'] and all(report['checks'].values())
    assert case['proposal']['status']=='OPEN'
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    assert not b.installed_decisions(case['p'])


def test_new_synthetic_preview_required_and_revalidates_approved_combined_artifact(case,monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    from rawcandle.fundamentals.admin import refresh_fundamentals as r
    from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
    from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue,queue_path_for_run_root
    others=[]
    for name in ('analysis','market','taxonomy'):
        p=case['tmp']/f'{name}.db'
        with sqlite3.connect(p) as c:c.execute('CREATE TABLE fixture(value)')
        others.append(p)
    paths=BatchAddTickerPaths(case['p'],case['c'],*others)
    monkeypatch.setattr(r,'resolve_identity',lambda *_:case['identity'])
    monkeypatch.setattr(runtime,'resolve_identity',lambda *_:case['identity'])
    class Client:
        def schema(self,_):return SimpleNamespace(ok=True,records=[],payload=[{'name':k} for k in r.REFRESH_REQUEST_FIELDS])
        def fundamentals(self,**kwargs):
            d=kwargs['dimension']
            records=([deepcopy(x['_acquisition_payload']) for x in case['h'][d].rows] if kwargs.get('ticker') else
                     [{'ticker':'WFRD','dimension':d,'lastupdated':'2026-10-22'}])
            if kwargs.get('ticker'):
                # Model a full HTTP acquisition without filling or changing any
                # source field. Discovery remains intentionally projected.
                captured=acquired(records,full=False)
                assert [dict(row) for row in captured]==records
                records=captured
            return SimpleNamespace(ok=True,records=records)
    runs=case['tmp']/'runs';q=queue_path_for_run_root(runs)
    b.save_item(q,case['proposal'],rehearsal=case['receipt'])
    first=r.run_preview(source_paths=paths,run_root=runs,client=Client(),as_of_date=date(2026,10,25))
    old=json.loads(Path(first['artifacts']['refresh_preview']).read_text())
    assert old['future_test_authorized'] is False and len(old['review_partition']['global_blockers'])==1
    assert b.read_items(q)[0]['status']=='OPEN'
    approve_queue(case,q)
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):
        runtime._load_bound_preview(Path(first['artifacts']['refresh_preview']),first['preview_fingerprint'],runs)
    second=r.run_preview(source_paths=paths,run_root=runs,client=Client(),as_of_date=date(2026,10,26))
    assert second['outcome']=='COMPLETED',second
    preview=json.loads(Path(second['artifacts']['refresh_preview']).read_text())
    assert preview['future_test_authorized'] and not preview['review_partition']['global_blockers']
    assert not preview['review_partition']['held']
    actual=runtime.revalidate_bound_source(preview,paths,Client(),review_queue=RefreshReviewQueue(q))
    assert actual['ticker_changes'][0]['accounting_boundary_resolution']['applied']
    assert not b.historical_evidence(case['p'])  # Preview never installs on published sources.


def test_bound_authority_context_and_absence_response_reject_even_with_new_checksums(case,monkeypatch):
    for mutation in ('authority','context','response'):
        p=deepcopy(case['proposal'])
        if mutation=='authority':p['evidence']['authority']['fiscal_year']=2020
        elif mutation=='context':p['evidence']['mrq']['context']['calculation_eligible']=True
        else:p['evidence']['mrq']['absence_proof']['row_count']+=1
        p['evidence_fingerprint']=fingerprint(p['evidence']);p['resolution_id']='boundary_'+p['evidence_fingerprint']
        p['proposal_fingerprint']=fingerprint({k:v for k,v in p.items() if k!='proposal_fingerprint'})
        try:b.receipt_binding(p,receipt(p))
        except b.BoundaryReviewError:continue
        pytest.fail('Tampered proposal received a registered receipt binding')
    original=b.authority
    monkeypatch.setattr(b,'authority',lambda:dict(original(),boundary='2019-12-14'))
    assert b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])['stale']


def test_archive_does_not_supply_watermark_or_source_completeness(case):
    from rawcandle.fundamentals.admin.refresh_fundamentals import resolve_refresh_state
    apply(case)
    assert resolve_refresh_state(case['p']).derived_watermark=='2026-10-22'
    trust=trusted_history([x['observation'] for x in b.current_provider_history(case['p'],'WFRD','MRQ')],ticker='WFRD',dimension='MRQ')
    assert trust.row_count==1 and trust.status=='COMPLETE'
    assert b.historical_evidence(case['p'])[0]['original']['normalized']['date']=='2019-12-31'
    with b._ro(case['c']) as c:
        assert c.execute("SELECT count(*) FROM v4_ttm_input_quarter i JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id WHERE q.period_end='2019-12-13'").fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM v4_parent_equity_source WHERE dimension!='ARQ'").fetchone()[0]==0


def test_rejected_resolution_keeps_global_review(case):
    q=case['tmp']/'queue.db'
    b.save_item(q,case['proposal'],rejected_reason='Operator keeps blocked')
    a=b.evaluate_for_refresh(case['p'],case['c'],case['h'],case['identity'],q)
    assert a['stale'] and not a['applied']
    assert b.queued_decision(q,'WFRD') is None


def test_review_ui_backend_registration_exposes_both_actions_without_approval(case,monkeypatch):
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'runs',recover_publication_on_startup=False)
    from types import SimpleNamespace
    monkeypatch.setattr(svc,'_accounting_boundary_evidence',lambda:(SimpleNamespace(provider_db=case['p'],canonical_db=case['c']),case['h'],case['identity']))
    item=svc.register_accounting_boundary_proposal(case['proposal'],rehearsal=case['receipt'])
    assert item['status']=='OPEN' and item['decision'] is None
    visible=svc.list_accounting_boundary_reviews()
    assert len(visible)==1
    evidence=visible[0]['proposal']['evidence']
    assert evidence['arq']['action']==b.PRESERVE and evidence['mrq']['action']==b.RETAIN
    assert not evidence['mrq']['context']['calculation_eligible']


def test_stale_published_decision_does_not_silently_reactivate(case):
    apply(case);q=case['tmp']/'queue.db'
    b.save_item(q,case['proposal'],stale_reason='Observed reappearance requires new review')
    a=b.evaluate_for_refresh(case['p'],case['c'],case['h'],case['identity'],q)
    assert a['stale'] and not a['applied']


def test_archived_and_current_context_are_immutable_in_candidate(case):
    apply(case)
    with sqlite3.connect(case['p']) as c:
        for table in (b.ARCHIVE,b.CONTEXT,b.DECISIONS):
            with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE'):
                c.execute(f'DELETE FROM {table}')
    assert b.validate_store(case['p'])['validated']


@pytest.mark.parametrize('period',['2019-12-13','2019-12-14'])
def test_new_same_period_conflict_is_not_ignored_after_publication(case,period):
    apply(case)
    rows=[r['_acquisition_payload'] for r in case['h']['MRQ'].rows]
    rows.append(row(('WFRD','MRQ','2019-12-14',period),'2019-Q4',ncfo=1))
    h={**case['h'],'MRQ':trusted_history(rows,ticker='WFRD',dimension='MRQ')}
    assert b.evaluate(case['p'],case['c'],h,case['identity'])['stale']


def test_registration_requires_real_unchanged_rehearsal_candidates(case):
    with pytest.raises(b.BoundaryReviewError,match='RECEIPT_INVALID'):
        b.receipt_binding(case['proposal'],receipt(case['proposal']))
    proof=case['receipt']
    with sqlite3.connect(proof['canonical_candidate']) as c:
        c.execute('CREATE TABLE changed_after_rehearsal(value)')
    with pytest.raises(b.BoundaryReviewError,match='CANDIDATE_CHANGED'):
        b.receipt_binding(case['proposal'],proof)
    assert case['proposal']['status']=='OPEN'


def test_copy_only_decision_cannot_be_registered_as_live_approval(case):
    synthetic=b.installed_decisions(case['receipt']['provider_candidate'])[0]
    assert synthetic['copy_only']
    with pytest.raises(b.BoundaryReviewError,match='COPY_ONLY_IS_NOT_OPERATOR_APPROVAL'):
        b.save_item(case['tmp']/'queue.db',case['proposal'],decision=synthetic)


def signed_receipt(proof, **changes):
    value = deepcopy(proof)
    value.update(changes)
    value['receipt_fingerprint'] = fingerprint({k:v for k,v in value.items() if k!='receipt_fingerprint'})
    return value


def queue_audit(queue):
    with b._ro(queue) as c:
        return [json.loads(r[0]) for r in c.execute(f'SELECT record_json FROM {b.QUEUE}_audit ORDER BY id')]


def test_registration_requires_actual_receipt(case):
    q=case['tmp']/'queue.db'
    with pytest.raises(b.BoundaryReviewError,match='RECEIPT_REQUIRED'):
        b.save_item(q,case['proposal'])
    assert not q.exists()


def test_open_binding_and_audit_are_compact_immutable_and_idempotent(case):
    q=case['tmp']/'queue.db';p=deepcopy(case['proposal']);proof=case['receipt']
    before={f:b.file_fingerprint(f) for f in (case['p'],case['c'])}
    item=b.save_item(q,p,rehearsal=proof);binding=item['rehearsal_receipt_binding']
    assert item['schema_version']==b.ITEM_VERSION
    assert item['status']=='OPEN' and item['decision'] is None
    assert item['proposal']==p==case['proposal']
    assert binding['receipt_fingerprint']==proof['receipt_fingerprint']
    assert binding['proposal_fingerprint']==p['proposal_fingerprint']
    assert binding['resolution_id']==p['resolution_id']
    assert binding['passed'] is True and binding['receipt_schema_version']==b.RECEIPT_VERSION
    assert binding['baseline_generation']==p['evidence']['baseline']['generation']
    assert binding['baseline_manifest_fingerprint']==p['evidence']['baseline']['manifest_fingerprint']
    assert binding['baseline_state_fingerprint']==p['evidence']['baseline_fingerprint']
    assert binding['candidate_sha256']==proof['candidate_sha256']
    assert binding['linked_actions']==[b.PRESERVE,b.RETAIN]
    assert binding['source_keys']['arq']==list(b.ARQ_KEY)
    assert '/tmp' not in json.dumps(binding)
    assert 'provider_candidate' not in binding and 'canonical_candidate' not in binding
    assert b.save_item(q,p,rehearsal=proof)==item
    assert b.read_items(q)==[item]
    audit=queue_audit(q)
    assert len(audit)==1
    assert audit[0]['event_type']=='REGISTERED_OPEN' and audit[0]['status']=='OPEN'
    assert audit[0]['receipt_fingerprint']==proof['receipt_fingerprint']
    assert audit[0]['proposal_fingerprint']==p['proposal_fingerprint']
    assert audit[0]['resolution_id']==p['resolution_id']
    assert audit[0]['baseline_generation']==binding['baseline_generation']
    assert audit[0]['candidate_sha256']==proof['candidate_sha256']
    assert audit[0]['receipt_passed'] is True and audit[0]['timestamp']
    assert audit[0]['item']==item and item['proposal']['operator'] is None
    assert item['proposal']['production_authorized'] is False
    with sqlite3.connect(q) as c:
        for sql in (f'DELETE FROM {b.QUEUE}_audit',f"UPDATE {b.QUEUE}_audit SET record_json='{{}}'"):
            with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_BOUNDARY_AUDIT'):c.execute(sql)
        changed=deepcopy(item);changed['rehearsal_receipt_binding']['receipt_fingerprint']='0'*64
        with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_BOUNDARY_RECEIPT_BINDING'):
            c.execute(f'UPDATE {b.QUEUE} SET record_json=?',(json.dumps(changed,sort_keys=True),))
    assert before=={f:b.file_fingerprint(f) for f in before}
    assert b.queued_decision(q,'WFRD') is None
    assert b.evaluate_for_refresh(case['p'],case['c'],case['h'],case['identity'],q)['pending']
    assert not b.historical_evidence(case['p'])


@pytest.mark.parametrize('changes',[
    {'schema_version':'unsupported'}, {'proposal_fingerprint':'0'*64},
    {'resolution_id':'other'}, {'passed':False}, {'mode':'LIVE'},
    {'candidate_sha256':{}}, {'candidate_sha256':{'provider':'bad','canonical':'0'*64}},
    {'baseline_generation':'other'}, {'baseline_manifest_fingerprint':'0'*64},
    {'baseline_state_fingerprint':None}, {'accepted_state_fingerprint':None},
    {'linked_actions':[b.PRESERVE]}, {'source_keys':{}}, {'created_at':None},
    {'result_fingerprint':'0'*64}, {'checks':None}, {'source_histories':{}},
    {'provider_candidate':None}, {'canonical_candidate':'/nonexistent/wfrd/canonical.db'},
])
def test_invalid_receipt_rejects_before_queue_write(case,changes):
    q=case['tmp']/'queue.db'
    proof=signed_receipt(case['receipt'],**changes)
    with pytest.raises(b.BoundaryReviewError):b.save_item(q,case['proposal'],rehearsal=proof)
    assert not q.exists()


@pytest.mark.parametrize('check',b.REHEARSAL_CHECKS)
def test_failed_rehearsal_assertion_rejects_registration(case,check):
    checks={**case['receipt']['checks'],check:False}
    with pytest.raises(b.BoundaryReviewError):
        b.save_item(case['tmp']/'queue.db',case['proposal'],rehearsal=signed_receipt(case['receipt'],checks=checks))


@pytest.mark.parametrize('field',['receipt_fingerprint','baseline_state_fingerprint','baseline_manifest_fingerprint','candidate_sha256'])
def test_missing_receipt_binding_data_rejects(case,field):
    proof=deepcopy(case['receipt']);proof.pop(field)
    if field!='receipt_fingerprint':proof=signed_receipt(proof)
    with pytest.raises(b.BoundaryReviewError):
        b.save_item(case['tmp']/'queue.db',case['proposal'],rehearsal=proof)


def test_conflicting_receipt_and_changed_proposal_leave_original_unchanged(case):
    q=case['tmp']/'queue.db';p=case['proposal'];proof=case['receipt']
    original=b.save_item(q,p,rehearsal=proof);audit=queue_audit(q)
    other=signed_receipt(proof,created_at='2026-10-27T12:00:00Z')
    b.receipt_binding(p,other)  # A different passing receipt, not just an invalid checksum.
    with pytest.raises(b.BoundaryReviewError,match='IMMUTABLE_RECEIPT_CONFLICT'):
        b.save_item(q,p,rehearsal=other)
    changed=deepcopy(p);changed['created_at']='2026-10-27T12:00:00Z'
    changed['proposal_fingerprint']=fingerprint({k:v for k,v in changed.items() if k!='proposal_fingerprint'})
    # The existing registered proposal is checked before any attempted replacement.
    with pytest.raises(b.BoundaryReviewError,match='IMMUTABLE_PROPOSAL_CONFLICT'):
        b.save_item(q,changed,rehearsal=proof)
    assert b.read_items(q)==[original] and queue_audit(q)==audit


@pytest.mark.parametrize('field',['proposal_fingerprint','receipt_fingerprint'])
def test_approval_rejects_wrong_registered_fingerprint(case,field):
    q=case['tmp']/'queue.db';item=b.save_item(q,case['proposal'],rehearsal=case['receipt'])
    with pytest.raises(b.BoundaryReviewError,match='FINGERPRINT_MISMATCH'):
        approve_queue(case,q,**{field:'0'*64})
    assert b.read_items(q)==[item] and len(queue_audit(q))==1


def test_approval_rejects_different_valid_receipt(case):
    q=case['tmp']/'queue.db';b.save_item(q,case['proposal'],rehearsal=case['receipt'])
    different=signed_receipt(case['receipt'],created_at='2026-10-27T12:00:00Z')
    b.receipt_binding(case['proposal'],different)
    with pytest.raises(b.BoundaryReviewError,match='FINGERPRINT_MISMATCH'):
        approve_queue(case,q,receipt_fingerprint=different['receipt_fingerprint'])


def test_approval_uses_durable_binding_after_candidate_files_are_gone(case):
    q=case['tmp']/'queue.db';item=b.save_item(q,case['proposal'],rehearsal=case['receipt'])
    before={f:b.file_fingerprint(f) for f in (case['p'],case['c'])}
    for key in ('provider_candidate','canonical_candidate'):Path(case['receipt'][key]).unlink()
    approved=approve_queue(case,q)
    assert approved['status']=='APPROVED' and approved['decision']['operator']=='fixture-operator'
    assert approved['rehearsal_receipt_binding']==item['rehearsal_receipt_binding']
    assert approved['decision']['rehearsal_receipt_binding']==item['rehearsal_receipt_binding']
    assert 'rehearsal' not in approved['decision']
    assert '/tmp' not in json.dumps(approved)
    assert b.verify_decision(approved['decision'])==case['proposal']['evidence']
    assert [a['event_type'] for a in queue_audit(q)]==['REGISTERED_OPEN','APPROVED']
    assert all(a['receipt_fingerprint']==case['receipt']['receipt_fingerprint'] for a in queue_audit(q))
    assert before=={f:b.file_fingerprint(f) for f in before}
    assert not b.historical_evidence(case['p'])


@pytest.mark.parametrize('drift',['source','baseline','date','pb','identity','old_key','new_boundary','complete_arq'])
def test_registered_approval_rejects_fresh_evidence_drift_and_preserves_binding(case,drift):
    q=case['tmp']/'queue.db';item=b.save_item(q,case['proposal'],rehearsal=case['receipt'])
    args={}
    if drift in ('baseline','date','pb'):
        with sqlite3.connect(case['c']) as c:
            sql={'baseline':"UPDATE v4_quarter SET period_end='2019-12-30' WHERE fiscal_year=2019",
                 'date':"UPDATE v4_quarter SET first_public_result_date='2020-03-17' WHERE fiscal_year=2019",
                 'pb':"UPDATE v4_parent_equity_source SET observation_id=observation_id||'drift' WHERE quarter_id=(SELECT quarter_id FROM v4_quarter WHERE fiscal_year=2019)"}[drift]
            c.execute(sql)
    elif drift=='identity':args['identity']={**case['identity'],'provider_security_id':'other'}
    else:
        h=case['h'].copy();d='MRQ' if drift in ('old_key','new_boundary') else 'ARQ'
        rows=[deepcopy(r['_acquisition_payload']) for r in h[d].rows]
        if drift=='source':rows[0]['lastupdated']='2026-10-23'
        elif drift=='old_key':rows.append(case['proposal']['evidence']['mrq']['accepted']['normalized'])
        elif drift=='new_boundary':rows.append(row(('WFRD','MRQ','2019-12-14','2019-12-13'),'2019-Q4',ncfo=1))
        else:rows.append(row(('WFRD','ARQ','2021-05-01','2021-03-31'),'2021-Q1',revenue=1))
        h[d]=trusted_history(rows,ticker='WFRD',dimension=d);args['histories']=h
    with pytest.raises(b.BoundaryReviewError):approve_queue(case,q,**args)
    assert b.read_items(q)==[item] and len(queue_audit(q))==1
    b.save_item(q,case['proposal'],stale_reason=drift)
    stale=b.read_items(q)[0]
    assert stale['status']=='STALE' and stale['rehearsal_receipt_binding']==item['rehearsal_receipt_binding']
    assert queue_audit(q)[0]['item']==item
    with pytest.raises(b.BoundaryReviewError,match='NOT_OPEN'):approve_queue(case,q)


def test_old_open_item_is_readable_but_not_approvable_or_silently_upgraded(case):
    q=case['tmp']/'legacy_queue.db';p=case['proposal']
    old={'proposal':p,'decision':None,'status':'OPEN','stale_reason':None,'rejected_reason':None}
    with sqlite3.connect(q) as c:
        c.execute(f'CREATE TABLE {b.QUEUE}(resolution_id TEXT PRIMARY KEY,record_json TEXT NOT NULL)')
        c.execute(f'INSERT INTO {b.QUEUE} VALUES(?,?)',(p['resolution_id'],json.dumps(old,sort_keys=True)))
    assert b.read_items(q)==[old]
    with pytest.raises(b.BoundaryReviewError,match='REGISTERED_RECEIPT_REQUIRED'):approve_queue(case,q)
    with pytest.raises(b.BoundaryReviewError,match='IMMUTABLE_RECEIPT_CONFLICT'):
        b.save_item(q,p,rehearsal=case['receipt'])
    assert b.read_items(q)==[old]


def test_service_confirmation_and_exact_approval_use_fresh_evidence(case,monkeypatch):
    from types import SimpleNamespace
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'runs',recover_publication_on_startup=False)
    calls=[]
    def current():
        calls.append(True)
        return SimpleNamespace(provider_db=case['p'],canonical_db=case['c']),case['h'],case['identity']
    monkeypatch.setattr(svc,'_accounting_boundary_evidence',current)
    monkeypatch.setattr('rawcandle.fundamentals.admin.publication_journal.safety_status',lambda:{'production_writes_blocked':False})
    p=case['proposal'];proof=case['receipt']
    with pytest.raises(TypeError):svc.register_accounting_boundary_proposal(p)
    item=svc.register_accounting_boundary_proposal(p,rehearsal=proof)
    display=svc.accounting_boundary_approval_confirmation(p['resolution_id'])
    assert display==dict(resolution_id=p['resolution_id'],linked_actions=[b.PRESERVE,b.RETAIN],
                         status='OPEN',proposal_fingerprint=p['proposal_fingerprint'],
                         receipt_fingerprint=proof['receipt_fingerprint'],receipt_passed=True,
                         baseline_generation=p['evidence']['baseline']['generation'],candidate_sha256=proof['candidate_sha256'])
    display['candidate_sha256']['provider']='bad'  # Presentation cannot mutate stored identity.
    assert svc.list_accounting_boundary_reviews()==[item]
    with pytest.raises(b.BoundaryReviewError,match='FINGERPRINT_MISMATCH'):
        svc.approve_accounting_boundary_review(p['resolution_id'],operator='operator',
            proposal_fingerprint=p['proposal_fingerprint'],receipt_fingerprint='0'*64)
    assert len(calls)==1
    approved=svc.approve_accounting_boundary_review(p['resolution_id'],operator='operator',
        proposal_fingerprint=p['proposal_fingerprint'],receipt_fingerprint=proof['receipt_fingerprint'])
    assert len(calls)==2 and approved['status']=='APPROVED'


def test_service_fetches_complete_source_again_for_registration_and_approval(case,monkeypatch):
    from types import SimpleNamespace
    from rawcandle.fundamentals.admin import refresh_fundamentals as refresh
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    calls=[]
    class Client:
        def fundamentals(self,**kwargs):
            calls.append(kwargs)
            rows=[deepcopy(r['_acquisition_payload']) for r in case['h'][kwargs['dimension']].rows]
            return SimpleNamespace(ok=True,records=acquired(rows,full=False))
    monkeypatch.setattr(refresh,'resolve_identity',lambda *_:case['identity'])
    monkeypatch.setattr('rawcandle.fundamentals.admin.publication_journal.safety_status',lambda:{'production_writes_blocked':False})
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'runs',recover_publication_on_startup=False,
        accounting_boundary_paths=SimpleNamespace(provider_db=case['p'],canonical_db=case['c']),accounting_boundary_client=Client())
    svc.register_accounting_boundary_proposal(case['proposal'],rehearsal=case['receipt'])
    svc.approve_accounting_boundary_review(case['proposal']['resolution_id'],operator='operator',
        proposal_fingerprint=case['proposal']['proposal_fingerprint'],receipt_fingerprint=case['receipt']['receipt_fingerprint'])
    assert [r['dimension'] for r in calls]==['ARQ','MRQ','ARQ','MRQ']
    assert all(r['ticker']=='WFRD' and r['limit']==refresh.DISCOVERY_LIMIT for r in calls)


def test_existing_unrelated_queue_tables_and_rows_are_unchanged(case):
    from rawcandle.fundamentals.admin.refresh_review_queue import _connect
    q=case['tmp']/'queue.db'
    with _connect(q) as c:
        c.execute("INSERT INTO refresh_review_queue_audit(ticker,event_type,occurred_at_utc,evidence_json) VALUES('OTHER','WAIT_FOR_PROVIDER',?,'{}')",(NOW,))
        c.execute('CREATE TABLE pb_ownership_review(id PRIMARY KEY,record_json TEXT)')
        c.execute("INSERT INTO pb_ownership_review VALUES(1,'existing P/B review')")
    def old_state():
        with b._ro(q) as c:
            schemas=[tuple(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'accounting_boundary_%' ORDER BY name")]
            return schemas,{n:[tuple(r) for r in c.execute(f'SELECT * FROM {n} ORDER BY rowid')] for n,_ in schemas}
    before=old_state()
    b.save_item(q,case['proposal'],rehearsal=case['receipt']);approve_queue(case,q)
    assert old_state()==before


def test_post_approval_complete_source_drift_requires_fresh_review(case):
    q=case['tmp']/'queue.db';b.save_item(q,case['proposal'],rehearsal=case['receipt']);approve_queue(case,q)
    rows=[deepcopy(r['_acquisition_payload']) for r in case['h']['ARQ'].rows]
    rows.append(row(('WFRD','ARQ','2021-05-01','2021-03-31'),'2021-Q1',revenue=1))
    h={**case['h'],'ARQ':trusted_history(rows,ticker='WFRD',dimension='ARQ')}
    result=b.evaluate_for_refresh(case['p'],case['c'],h,case['identity'],q)
    assert result['stale'] and not result['applied']


def test_fingerprint_only_and_legacy_approval_entry_points_are_not_registration(case):
    q=case['tmp']/'queue.db'
    for proof in (case['receipt']['receipt_fingerprint'],{'receipt_fingerprint':case['receipt']['receipt_fingerprint']}):
        with pytest.raises(b.BoundaryReviewError):b.save_item(q,case['proposal'],rehearsal=proof)
    with pytest.raises(b.BoundaryReviewError,match='APPROVAL_REQUIRES_CURRENT_EVIDENCE'):
        b.save_item(q,case['proposal'],decision=case['decision'])
    with pytest.raises(b.BoundaryReviewError,match='APPROVAL_REQUIRES_REGISTERED_RECEIPT'):
        b.approve(case['proposal'],operator='operator',rehearsal=case['receipt'])
    assert not q.exists()


def test_manifested_generation_binding_is_preserved_and_drift_rejected(case):
    manifest=case['tmp']/'generation_manifest.json'
    value={'generation_id':case['tmp'].name,'fixture_version':1}
    manifest.write_text(json.dumps(value))
    p=b.create_proposal(case['p'],case['c'],case['h'],case['identity'],created_at=NOW)
    proof=b.rehearse(p,case['p'],case['c'],case['h'],case['identity'],case['tmp']/'manifested_rehearsal')
    q=case['tmp']/'manifested_queue.db';item=b.save_item(q,p,rehearsal=proof)
    binding=item['rehearsal_receipt_binding']
    assert binding['baseline_manifest_fingerprint']==fingerprint(value)
    assert binding['baseline_state_fingerprint']==p['evidence']['baseline_fingerprint']
    manifest.write_text(json.dumps({**value,'fixture_version':2}))
    with pytest.raises(b.BoundaryReviewError,match='EVIDENCE_STALE'):
        b.approve_registered(q,p['resolution_id'],operator='operator',
            proposal_fingerprint=p['proposal_fingerprint'],receipt_fingerprint=proof['receipt_fingerprint'],
            provider_db=case['p'],canonical_db=case['c'],histories=case['h'],identity=case['identity'])
    assert b.read_items(q)==[item]


@pytest.fixture
def confirmation_case(case):
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    from rawcandle.fundamentals.admin.refresh_review_queue import queue_path_for_run_root
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'confirmation'/'runs',recover_publication_on_startup=False)
    queue=queue_path_for_run_root(svc.run_root)
    item=b.save_item(queue,case['proposal'],rehearsal=case['receipt'])
    return svc,queue,item


def malformed_confirmation(case, item, *, stored_id=None, raw_json=None):
    """An isolated corrupt/legacy fixture, never an edit of an immutable live item."""
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    from rawcandle.fundamentals.admin.refresh_review_queue import queue_path_for_run_root
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'malformed_confirmation'/'runs',recover_publication_on_startup=False)
    queue=queue_path_for_run_root(svc.run_root);queue.parent.mkdir(parents=True)
    with sqlite3.connect(queue) as c:
        c.execute(f'CREATE TABLE {b.QUEUE}(resolution_id TEXT PRIMARY KEY,record_json TEXT NOT NULL)')
        c.execute(f'INSERT INTO {b.QUEUE} VALUES(?,?)',
                  (stored_id or case['proposal']['resolution_id'],
                   raw_json if raw_json is not None else json.dumps(item,sort_keys=True)))
    return svc,queue


def test_confirmation_returns_authoritative_ordered_identity_and_is_read_only(case,confirmation_case,monkeypatch):
    svc,q,item=confirmation_case;p=item['proposal'];binding=item['rehearsal_receipt_binding']
    def forbidden_fetch():pytest.fail('Confirmation must not fetch provider evidence')
    monkeypatch.setattr(svc,'_accounting_boundary_evidence',forbidden_fetch)
    before={f:b.file_fingerprint(f) for f in (q,case['p'],case['c'])}
    audit=queue_audit(q)
    application=b.evaluate_for_refresh(case['p'],case['c'],case['h'],case['identity'],q)
    confirmation=svc.accounting_boundary_approval_confirmation(p['resolution_id'])
    assert confirmation=={
        'resolution_id':p['resolution_id'], 'linked_actions':binding['linked_actions'],
        'status':'OPEN', 'proposal_fingerprint':p['proposal_fingerprint'],
        'receipt_fingerprint':binding['receipt_fingerprint'], 'receipt_passed':True,
        'baseline_generation':binding['baseline_generation'], 'candidate_sha256':binding['candidate_sha256']}
    assert confirmation['linked_actions']==[p['evidence']['arq']['action'],p['evidence']['mrq']['action']]
    assert confirmation['linked_actions']==[b.PRESERVE,b.RETAIN]
    confirmation['linked_actions'].reverse();confirmation['candidate_sha256']['provider']='changed presentation'
    assert b.read_items(q)==[item] and queue_audit(q)==audit
    assert before=={f:b.file_fingerprint(f) for f in before}
    assert b.queued_decision(q,'WFRD') is None
    assert application['pending'] and not application['applied']
    assert application==b.evaluate_for_refresh(case['p'],case['c'],case['h'],case['identity'],q)
    current={d:load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    comparison=b.comparison('WFRD',current,case['h'],application);comparison['identity']=case['identity']
    assert classify_review_scope(comparison)['scope']=='GLOBAL_BLOCKING_REVIEW'


@pytest.mark.parametrize('path,value',[
    ('schema_version','unsupported'), ('schema_version','__MISSING__'),
    ('status','APPROVED'), ('status','STALE'), ('decision',{}), ('decision','__MISSING__'),
    ('stale_reason','source drift'), ('rejected_reason','operator rejected'),
    ('resolution_id','different item ID'),
    ('proposal',None), ('proposal','__MISSING__'),
    ('proposal.resolution_id','different proposal ID'),
    ('proposal.proposal_fingerprint','__MISSING__'),
    ('proposal.evidence.arq.action','__MISSING__'),
    ('proposal.evidence.arq.action',b.RETAIN),
    ('proposal.evidence.mrq.action','UNKNOWN_ACTION'),
    ('rehearsal_receipt_binding',None), ('rehearsal_receipt_binding','__MISSING__'),
    ('rehearsal_receipt_binding.resolution_id','different receipt ID'),
    ('rehearsal_receipt_binding.proposal_fingerprint','0'*64),
    ('rehearsal_receipt_binding.receipt_fingerprint','__MISSING__'),
    ('rehearsal_receipt_binding.binding_fingerprint','0'*64),
    ('rehearsal_receipt_binding.passed',False),
    ('rehearsal_receipt_binding.linked_actions','__MISSING__'),
    ('rehearsal_receipt_binding.linked_actions',[]),
    ('rehearsal_receipt_binding.linked_actions',[b.PRESERVE,b.PRESERVE]),
    ('rehearsal_receipt_binding.linked_actions',[b.PRESERVE,'UNKNOWN_ACTION']),
    ('rehearsal_receipt_binding.linked_actions',[b.RETAIN,b.PRESERVE]),
    ('rehearsal_receipt_binding.candidate_sha256','__MISSING__'),
    ('rehearsal_receipt_binding.candidate_sha256.provider','__MISSING__'),
    ('rehearsal_receipt_binding.candidate_sha256.canonical','bad hash'),
    ('rehearsal_receipt_binding.baseline_generation','__MISSING__'),
    ('rehearsal_receipt_binding.baseline_generation',''),
])
def test_confirmation_rejects_contradictory_or_missing_fields(case,confirmation_case,path,value):
    item=deepcopy(confirmation_case[2]);target=item;names=path.split('.')
    for name in names[:-1]:target=target[name]
    if value=='__MISSING__':target.pop(names[-1])
    else:target[names[-1]]=value
    binding=item.get('rehearsal_receipt_binding')
    if isinstance(binding,dict) and path!='rehearsal_receipt_binding.binding_fingerprint':
        # Preserve valid binding checksums so scope/semantic checks must also reject.
        binding['binding_fingerprint']=fingerprint({k:v for k,v in binding.items() if k!='binding_fingerprint'})
    svc,q=malformed_confirmation(case,item);before=b.file_fingerprint(q)
    with pytest.raises(b.BoundaryReviewError):
        svc.accounting_boundary_approval_confirmation(case['proposal']['resolution_id'])
    assert b.file_fingerprint(q)==before


def test_confirmation_validates_actual_queue_key_not_only_embedded_proposal(case,confirmation_case):
    item=confirmation_case[2];svc,q=malformed_confirmation(case,item,stored_id='different stored ID')
    with pytest.raises(b.BoundaryReviewError,match='NOT_OPEN'):
        svc.accounting_boundary_approval_confirmation(item['proposal']['resolution_id'])
    with pytest.raises(b.BoundaryReviewError,match='CONFIRMATION_INVALID'):
        svc.accounting_boundary_approval_confirmation('different stored ID')


@pytest.mark.parametrize('raw_json',['null','[]','"invalid item"','{broken json'])
def test_confirmation_rejects_malformed_record_with_domain_error(case,raw_json):
    svc,q=malformed_confirmation(case,None,raw_json=raw_json);before=b.file_fingerprint(q)
    with pytest.raises(b.BoundaryReviewError):
        svc.accounting_boundary_approval_confirmation(case['proposal']['resolution_id'])
    assert b.file_fingerprint(q)==before


@pytest.mark.parametrize('requested_id',['not registered','',None])
def test_confirmation_rejects_missing_or_invalid_requested_id(confirmation_case,requested_id):
    svc,_,_=confirmation_case
    with pytest.raises(b.BoundaryReviewError,match='NOT_OPEN'):
        svc.accounting_boundary_approval_confirmation(requested_id)


def test_confirmation_of_old_open_item_without_binding_remains_unavailable(case,confirmation_case):
    item=deepcopy(confirmation_case[2]);item.pop('rehearsal_receipt_binding')
    svc,_=malformed_confirmation(case,item)
    with pytest.raises(b.BoundaryReviewError,match='REGISTERED_RECEIPT_REQUIRED'):
        svc.accounting_boundary_approval_confirmation(case['proposal']['resolution_id'])


def test_confirmation_rejects_empty_baseline_even_with_consistent_recomputed_hashes(case,confirmation_case):
    item=deepcopy(confirmation_case[2]);p=item['proposal'];e=p['evidence'];binding=item['rehearsal_receipt_binding']
    e['baseline']['generation']='';e['baseline_fingerprint']=fingerprint(e['baseline'])
    p['evidence_fingerprint']=fingerprint(e);p['resolution_id']='boundary_'+p['evidence_fingerprint']
    p['proposal_fingerprint']=fingerprint({k:v for k,v in p.items() if k!='proposal_fingerprint'})
    binding.update(baseline_generation='',baseline_state_fingerprint=e['baseline_fingerprint'],
                   resolution_id=p['resolution_id'],proposal_fingerprint=p['proposal_fingerprint'])
    binding['binding_fingerprint']=fingerprint({k:v for k,v in binding.items() if k!='binding_fingerprint'})
    b.validate_receipt_binding(p,binding)  # Presentation adds the required nonempty baseline check.
    svc,_=malformed_confirmation(case,item,stored_id=p['resolution_id'])
    with pytest.raises(b.BoundaryReviewError,match='CONFIRMATION_INVALID'):
        svc.accounting_boundary_approval_confirmation(p['resolution_id'])
