from __future__ import annotations

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
    return {d:validate_complete_history(rows,ticker='WFRD',dimension=d)
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
    otherhist={d:validate_complete_history([dict(other,dimension=d)],ticker='OTHER',dimension=d) for d in ('ARQ','MRQ')}
    runtime.replace_provider_histories(provider,{'WFRD':initial,'OTHER':otherhist},
        {'WFRD':identity,'OTHER':dict(identity,ticker='OTHER',company_id=2,security_id=2,provider_security_id='200')},applied_at=NOW)
    runtime.fresh_rebuild_canonical(provider,canonical,applied_at=NOW)
    incoming=trusts([dict(arq,fiscalperiod='2020-Q4',lastupdated='2026-10-22'),genuine],[stub])
    proposal=b.create_proposal(provider,canonical,incoming,identity,created_at=NOW)
    proof=b.rehearse(proposal,provider,canonical,incoming,identity,tmp_path/'approval_rehearsal')
    decision=b.approve(proposal,operator='fixture-operator',rehearsal=proof)
    return {'p':provider,'c':canonical,'h':incoming,'identity':identity,
            'proposal':proposal,'decision':decision,'tmp':tmp_path}


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
    h[dimension]=validate_complete_history(rows,ticker='WFRD',dimension=dimension)
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
    h={**case['h'],'MRQ':validate_complete_history(rows,ticker='WFRD',dimension='MRQ')}
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
    b.save_item(q,p)
    assert b.read_items(q)[0]['status']=='OPEN' and b.queued_decision(q,'WFRD') is None
    b.save_item(q,p,decision=case['decision'])
    assert b.queued_decision(q,'OTHER') is None
    assert b.queued_decision(q,'WFRD')==case['decision']
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
    h={**case['h'],'ARQ':validate_complete_history(rows,ticker='WFRD',dimension='ARQ')}
    a=b.evaluate(case['p'],case['c'],h,case['identity'])
    assert a['applied'] and a['phase']=='PUBLISHED'
    current={d:load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    result=b.comparison('WFRD',current,h,a)
    assert result['classification']!='REVIEW_REQUIRED'
    assert not any(e['event']=='TRUE_SOURCE_REMOVAL' for e in result['source_history_events'])
    old=case['proposal']['evidence']['mrq']['accepted']['normalized']
    h['MRQ']=validate_complete_history([r['_acquisition_payload'] for r in h['MRQ'].rows]+[old],ticker='WFRD',dimension='MRQ')
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
            return SimpleNamespace(ok=True,records=records)
    runs=case['tmp']/'runs';q=queue_path_for_run_root(runs)
    b.save_item(q,case['proposal'])
    first=r.run_preview(source_paths=paths,run_root=runs,client=Client(),as_of_date=date(2026,10,25))
    old=json.loads(Path(first['artifacts']['refresh_preview']).read_text())
    assert old['future_test_authorized'] is False and len(old['review_partition']['global_blockers'])==1
    b.save_item(q,case['proposal'],decision=case['decision'])
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
        try:d=b.approve(p,operator='fixture',rehearsal=receipt(p))
        except b.BoundaryReviewError:continue
        assert b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=d)['stale']
    original=b.authority
    monkeypatch.setattr(b,'authority',lambda:dict(original(),boundary='2019-12-14'))
    assert b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])['stale']


def test_archive_does_not_supply_watermark_or_source_completeness(case):
    from rawcandle.fundamentals.admin.refresh_fundamentals import resolve_refresh_state
    apply(case)
    assert resolve_refresh_state(case['p']).derived_watermark=='2026-10-22'
    trust=validate_complete_history([x['observation'] for x in b.current_provider_history(case['p'],'WFRD','MRQ')],ticker='WFRD',dimension='MRQ')
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


def test_review_ui_backend_registration_exposes_both_actions_without_approval(case):
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    svc=FundamentalsAdminUIService(run_root=case['tmp']/'runs',recover_publication_on_startup=False)
    item=svc.register_accounting_boundary_proposal(case['proposal'])
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
    h={**case['h'],'MRQ':validate_complete_history(rows,ticker='WFRD',dimension='MRQ')}
    assert b.evaluate(case['p'],case['c'],h,case['identity'])['stale']


def test_approval_requires_real_unchanged_rehearsal_candidates(case):
    with pytest.raises(b.BoundaryReviewError,match='PHYSICAL_PROOF'):
        b.approve(case['proposal'],operator='fixture',rehearsal=receipt(case['proposal']))
    proof=case['decision']['rehearsal']
    with sqlite3.connect(proof['canonical_candidate']) as c:
        c.execute('CREATE TABLE changed_after_rehearsal(value)')
    with pytest.raises(b.BoundaryReviewError,match='CANDIDATE_CHANGED'):
        b.approve(case['proposal'],operator='fixture',rehearsal=proof)
    assert case['proposal']['status']=='OPEN'


def test_copy_only_decision_cannot_be_registered_as_live_approval(case):
    synthetic=b.installed_decisions(case['decision']['rehearsal']['provider_candidate'])[0]
    assert synthetic['copy_only']
    with pytest.raises(b.BoundaryReviewError,match='COPY_ONLY_IS_NOT_OPERATOR_APPROVAL'):
        b.save_item(case['tmp']/'queue.db',case['proposal'],decision=synthetic)
