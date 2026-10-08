"""Operational quarter review: real reconcile, queue lifecycle, approval and isolated evidence."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sqlite3

import pytest

from rawcandle.fundamentals import ownership_basis as own, phase12d
from rawcandle.fundamentals.admin import pb_ownership_review as workflow
from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue, _connect
from rawcandle.fundamentals.pb_reporting_contract import activate_quarterly_ownership, generation_ownership_artifact
from rawcandle.fundamentals.book_value import book_value_report
from tests.test_phase12d_operational_rebuild import _databases, _row, _insert

ASOF='2026-10-09'


def ro(p):
    c=sqlite3.connect(f'file:{p}?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c


def report(cp,mp,day=ASOF):
    with ro(cp) as c,ro(mp) as m:return book_value_report(c,m,company_id=1,ticker='AAA',as_of=day)


def digest_db(p):
    with ro(p) as c:
        result={}
        for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name in ('v4_pb_reporting_contract','v4_pb_ownership_artifact'):continue
            rows=[list(r) for r in c.execute(f'SELECT * FROM "{name}"')]
            result[name]=workflow.fingerprint(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)))
    return result


@pytest.fixture
def factory(tmp_path,monkeypatch):
    template=deepcopy(next(r for r in own.ownership_reviews_v2() if r['release_type']=='ORDINARY_COMMON'))
    def create(kind='ordinary'):
        folder=tmp_path/kind;folder.mkdir();pp,cp,ap=_databases(folder);mp=folder/'market.db';queue=folder/'queue.db'
        factor,ratio,category=1,1,'Domestic Common Stock Primary Class'
        if kind=='identity':category='ADR Common Stock'
        if kind in ('adr','zero'):
            factor,ratio,category=(.333,1/3,'ADR Common Stock') if kind=='adr' else (0,1/40000,'ADR Common Stock')
        def provider_row(q,shares,equity):
            row=_row(q);end={2:'2026-06-30',3:'2026-09-30',4:'2026-12-31'}[q];day={2:'2026-08-01',3:'2026-10-08',4:'2027-01-15'}[q]
            row.update(fiscalperiod=f'2026-Q{q}',reportperiod=end,calendardate=end,date=day,lastupdated=day,
                sharesbas=shares,equity=equity,equityusd=equity,price=10,marketcap=10*shares*ratio,
                pb=10*shares*ratio/equity,sharefactor=factor)
            return row
        with sqlite3.connect(pp) as c:

            c.execute("INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,category,payload_json,fetched_at_utc) VALUES('SF1','AAA','1',?,'{}','2026-10-08')",(category,))
        _insert(pp,provider_row(2,100,1000));phase12d.reconcile_canonical(pp,cp,applied_at='2026-10-08')
        with sqlite3.connect(mp) as c:
            c.executescript('CREATE TABLE ticker_meta(ticker,market);CREATE TABLE osakedata(osake,market,pvm,open,high,low,close);')
            c.executemany("INSERT INTO osakedata VALUES('AAA','usa',?,?,?,?,?)",[
                ('2026-08-01',10,11,9,10),('2026-10-08',10,11,9,10),('2026-10-09',20,21,19,20),('2026-10-10',30,31,29,30)])
        with ro(cp) as c:q=workflow.latest_basis(c,1,as_of=ASOF)
        r=deepcopy(template);r.update({k:q[k] for k in (*own.BINDING,'fiscal_year','fiscal_quarter','reportperiod')})
        r.update(accepted_sharesbas=100,provider_declared_factor=factor,accepted_category=category,
            accepted_provider_date='2026-08-01',accepted_source_availability_date='2026-08-01',
            share_source_date='2026-08-01',unit_effective_from='2026-08-01',identity_override=kind=='identity')
        if kind=='identity':r['release_type']='IDENTITY_OVERRIDE'
        if kind in ('adr','zero'):r.update(release_type='ADR_FACTOR',economic_unit_rule='ADS_EQUIVALENTS',reviewed_security_type='ADS',exact_factor_numerator=1,exact_factor_denominator=3 if kind=='adr' else 40000)
        artifact={'contract':own.QUARTERLY_OWNERSHIP_CONTRACT,'records':[r]}
        monkeypatch.setattr(own,'_quarterly_artifact',lambda:(deepcopy(artifact),hashlib.sha256(workflow.serialize(artifact).encode()).hexdigest()))
        activate_quarterly_ownership(cp,effective_from='2026-10-08')
        before=report(cp,mp);assert before['current']['value']==pytest.approx(2*ratio)
        def refresh():return phase12d.reconcile_canonical(pp,cp,applied_at=ASOF,ownership_review_queue_path=queue)
        _insert(pp,provider_row(3,120,2000));result=refresh()
        assert 'pb_ownership_review_error' not in result,result
        items=RefreshReviewQueue(queue).ownership_items();assert len(items)==1
        return dict(pp=pp,cp=cp,ap=ap,mp=mp,queue=queue,case=items[0],artifact=artifact,ratio=ratio,
                    before=before,refresh=refresh,provider_row=provider_row,output=folder/'output')
    return create


def approve(f,**changes):
    kw=dict(candidate_hash=f['case']['candidate_hash'],canonical_db=f['cp'],market_db=f['mp'],output_root=f['output'],
            as_of=ASOF,operator='Fixture operator',note='Confirmed accepted quarterly basis and prior official evidence',confirmed=True)
    kw.update(changes)
    return workflow.approve(f['queue'],f['case']['case_id'],**kw)


@pytest.mark.parametrize('kind',['ordinary','identity','adr','zero'])
def test_end_to_end_reconcile_review_approval_and_generation_rehearsal(factory,kind,monkeypatch):
    f=factory(kind);case=f['case'];source_bytes=f['cp'].read_bytes();financial_before=digest_db(f['cp']);held=report(f['cp'],f['mp'])
    assert held['current']['reason']=='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'
    assert held['current']['ownership_review']['prior_reviewed_quarter']=='2026-Q2'
    assert held['current']['parent_equity_usd']==2000 and held['provider']['value']==pytest.approx(.6*f['ratio'])
    assert held['history'][0]['fiscal_quarter']=='Q3' and held['history'][1]==f['before']['history'][0]
    assert case['classification']=='CONTINUATION_CANDIDATE'
    assert case['deltas']['shares_absolute']==20 and case['deltas']['shares_percent']==pytest.approx(20)
    assert case['hypothetical_economic_units']==pytest.approx(120*f['ratio'])
    assert case['previous']['parent_equity_usd']==1000 and case['new']['parent_equity_usd']==2000
    preview=workflow.preview(case,f['cp'],f['mp'],as_of=ASOF)
    assert preview['label']=='HYPOTHETICAL_NOT_APPROVED' and preview['hypothetical_current']['value']==pytest.approx(1.2*f['ratio'])
    assert f['cp'].read_bytes()==source_bytes and not f['output'].exists()
    old=deepcopy(f['artifact']['records']);result=approve(f)
    assert result['publication_required'] is True
    assert f['cp'].read_bytes()==source_bytes and report(f['cp'],f['mp'])==held
    candidate=Path(result['candidate_canonical']);after=report(candidate,f['mp'])
    assert after['current']['value']==pytest.approx(1.2*f['ratio'])
    assert after['current']['ownership_basis']['economic_units']==pytest.approx(120*f['ratio'])
    assert after['current']['parent_equity_usd']==2000
    assert (after['provider'],after['history'])==(held['provider'],held['history'])
    assert digest_db(candidate)==financial_before
    with ro(candidate) as c:
        revised,sha=generation_ownership_artifact(c)
        assert revised['records'][:len(old)]==old and len(revised['records'])==len(old)+1
        record=revised['records'][-1]
        assert all(record[k]==case['new'][k] for k in (*own.BINDING,'fiscal_year','fiscal_quarter','reportperiod'))
        assert record['accepted_sharesbas']==120 and record['provider_declared_factor']==case['new']['sharefactor']
        assert record['approval_mode']=='OPERATOR_CONFIRMED' and record['evidence_urls']==old[0]['evidence_urls']
        assert sha==result['registry_sha256']==hashlib.sha256(Path(result['registry_artifact']).read_bytes()).hexdigest()
        assert Path(result['registry_artifact']).read_text()==workflow.serialize(revised)
    assert report(candidate,f['mp'],day='2026-10-10')['current']['value']==pytest.approx(1.8*f['ratio'])
    f['refresh']();assert len(RefreshReviewQueue(f['queue']).ownership_items())==1
    assert RefreshReviewQueue(f['queue']).ownership_items()[0]['status']=='APPROVED'
    # A separately published generation containing this record consumes approval; no publication is done here.
    outcome=workflow.sync(f['queue'],candidate,as_of=ASOF,run_id='candidate-consumption-rehearsal')
    assert outcome['candidate_count']==0
    assert RefreshReviewQueue(f['queue']).ownership_items()[0]['status']=='APPROVED'
    monkeypatch.setattr(workflow,'_is_active_canonical',lambda path: path==candidate)
    workflow.sync(f['queue'],candidate,as_of=ASOF,run_id='simulated-published-binding')
    history=RefreshReviewQueue(f['queue']).ownership_items(include_resolved=True)
    assert history[0]['status']=='PUBLISHED'
    with ro(f['queue']) as c:
        events=[r[0] for r in c.execute('select event_type from refresh_review_queue_audit order by audit_id')]
    assert events==['PB_OWNERSHIP_CREATED','PB_OWNERSHIP_APPROVED','PB_OWNERSHIP_PUBLISHED']


def test_repeated_refresh_one_logical_case_no_duplicate_audit(factory):
    f=factory();case=f['case'];f['refresh']();f['refresh']()
    assert RefreshReviewQueue(f['queue']).ownership_items()[0]['case_id']==case['case_id']
    with ro(f['queue']) as c:assert c.execute('select count(*) from refresh_review_queue_audit').fetchone()[0]==1


@pytest.mark.parametrize('sql,reason',[
    ("UPDATE security SET security_id=2",'REVIEW_REQUIRED_IDENTITY_CHANGE'),
    ("UPDATE company SET company_key='other'",'REVIEW_REQUIRED_IDENTITY_CHANGE'),
    ("UPDATE security SET current_ticker='OTHER'",'REVIEW_REQUIRED_IDENTITY_CHANGE'),
    ("UPDATE v4_parent_equity_source SET category='Foreign Preferred Stock' WHERE fiscalperiod='2026-Q3'",'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE'),
    ("UPDATE v4_parent_equity_source SET sharefactor=.5 WHERE fiscalperiod='2026-Q3'",'REVIEW_REQUIRED_FACTOR_CHANGE'),
    ("UPDATE v4_parent_equity_source SET sharesbas=0 WHERE fiscalperiod='2026-Q3'",'REVIEW_REQUIRED_INVALID_SHARE_BASIS'),
    ("UPDATE v4_quarter_financials SET shares_outstanding=121 WHERE shares_outstanding=120",'REVIEW_REQUIRED_INVALID_SHARE_BASIS'),
    ("UPDATE security SET valid_to='2026-10-08'",'REVIEW_REQUIRED_IDENTITY_CHANGE'),
])
def test_classification_and_stale_approval_on_changed_binding(factory,sql,reason):
    f=factory()
    with sqlite3.connect(f['cp']) as c:c.execute(sql)
    with ro(f['cp']) as c:cases=workflow.detect(c,as_of=ASOF)
    assert cases[0]['classification']==reason
    with pytest.raises(ValueError,match='STALE_CANDIDATE'):approve(f)
    workflow.sync(f['queue'],f['cp'],as_of=ASOF,run_id='regenerate')
    f['case']=RefreshReviewQueue(f['queue']).ownership_items()[0]
    with pytest.raises(ValueError,match='MANUAL_EVIDENCE_REVIEW_REQUIRED'):approve(f)


@pytest.mark.parametrize('changed', ["UPDATE v4_parent_equity_source SET content_hash='revision' WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_parent_equity_source SET observation_id='revision' WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_quarter_financials SET parent_equity_usd=2100 WHERE shares_outstanding=120"])
def test_stale_candidate_hash_observation_equity_cannot_approve(factory,changed):
    f=factory()
    with sqlite3.connect(f['cp']) as c:c.execute(changed)
    with pytest.raises(ValueError,match='STALE_CANDIDATE'):approve(f)
    assert not f['output'].exists()


def test_registry_version_change_prevents_approval(factory,monkeypatch):
    f=factory();old=deepcopy(f['artifact']);old['changed']='new version'
    monkeypatch.setattr(own,'_quarterly_artifact',lambda:(old,hashlib.sha256(workflow.serialize(old).encode()).hexdigest()))
    with pytest.raises(ValueError,match='ARTIFACT_MISMATCH'):approve(f)


@pytest.mark.parametrize('changes',[{'confirmed':False},{'confirmed':1},{'operator':''},{'note':''}])
def test_explicit_confirmation_and_operator_evidence_required(factory,changes):
    f=factory()
    with pytest.raises(PermissionError,match='EXPLICIT_CONFIRMATION'):approve(f,**changes)
    assert not f['output'].exists()


def test_wrong_candidate_hash_and_duplicate_approval_rejected_safely(factory):
    f=factory()
    with pytest.raises(ValueError,match='STALE_CANDIDATE'):approve(f,candidate_hash='wrong')
    result=approve(f)
    with pytest.raises(ValueError,match='NOT_OPEN'):approve(f)
    assert Path(result['registry_artifact']).exists()
    with ro(f['queue']) as c:assert c.execute("select count(*) from refresh_review_queue_audit where event_type='PB_OWNERSHIP_APPROVED'").fetchone()[0]==1


def test_hold_history_retry_and_separate_provider_review_not_overwritten(factory):
    f=factory()
    with _connect(f['queue']) as c:
        c.execute("INSERT INTO refresh_review_queue(ticker,review_type,reason_codes_json,affected_source_keys_json,fiscal_identities_json,source_evidence_fingerprint,first_seen_at_utc,first_seen_run_id,last_seen_at_utc,last_seen_run_id,status) VALUES('AAA','TICKER_LOCAL_REVIEW','[]','[]','[]','provider','now','run','now','run','OPEN')")
    provider=RefreshReviewQueue(f['queue']).get('AAA')
    workflow.keep_on_hold(f['queue'],f['case']['case_id'],candidate_hash=f['case']['candidate_hash'],note='Need evidence')
    f['refresh']()
    assert RefreshReviewQueue(f['queue']).get('AAA')==provider
    assert RefreshReviewQueue(f['queue']).ownership_items()[0]['status']=='HELD'
    with pytest.raises(ValueError,match='NOT_OPEN'):approve(f)


@pytest.mark.parametrize('reason',['MULTI_CLASS_UNVERIFIED','NEWER_SHARE_COUNT_REQUIRED','OWNERSHIP_BASIS_UNVERIFIED'])
def test_unsupported_explicit_holds_excluded(factory,reason):
    f=factory();r=f['artifact']['records'][0];r.update(evidence_status='REVIEWED_HOLD',hold_reason=reason,economic_unit_rule='HOLD')
    # A separate held-only generation fixture; never revisit or upgrade held scopes.
    with sqlite3.connect(f['cp']) as c:c.execute('update v4_pb_reporting_contract set review_artifact_sha256=?',(hashlib.sha256(workflow.serialize(f['artifact']).encode()).hexdigest(),))
    with ro(f['cp']) as c:assert workflow.detect(c,as_of=ASOF)==[]


def test_large_share_change_still_requires_human_approval(factory):
    f=factory()
    with sqlite3.connect(f['cp']) as c:
        c.execute("UPDATE v4_parent_equity_source SET sharesbas=10000 WHERE fiscalperiod='2026-Q3'")
        c.execute('UPDATE v4_quarter_financials SET shares_outstanding=10000 WHERE shares_outstanding=120')
    with ro(f['cp']) as c:case=workflow.detect(c,as_of=ASOF)[0]
    assert case['classification']=='CONTINUATION_CANDIDATE' and case['deltas']['shares_percent']==9900
    assert RefreshReviewQueue(f['queue']).ownership_items()[0]['status']=='OPEN'


def test_generation_artifact_tampering_fails_closed(factory):
    f=factory();result=approve(f);candidate=Path(result['candidate_canonical'])
    with sqlite3.connect(candidate) as c:c.execute("UPDATE v4_pb_ownership_artifact SET artifact_json='{}'")
    with pytest.raises(ValueError,match='ARTIFACT_MISMATCH'):report(candidate,f['mp'])


def test_queue_failure_does_not_block_financial_acceptance(factory):
    f=factory();bad=f['output'];bad.write_text('not a directory')
    outcome=phase12d.reconcile_canonical(f['pp'],f['cp'],applied_at=ASOF,ownership_review_queue_path=bad/'queue.db')
    assert 'pb_ownership_review_error' in outcome
    assert report(f['cp'],f['mp'])['current']['reason']=='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'


def test_v1_and_bundled_v2_files_unchanged():
    folder=Path(own.__file__).parent
    assert hashlib.sha256((folder/'ownership_reviews_v1.json').read_bytes()).hexdigest()=='0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf'
    assert hashlib.sha256((folder/'ownership_reviews_v2.json').read_bytes()).hexdigest()=='7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6'


def test_admin_ui_explicit_dialog_before_action():
    from tests.test_fundamentals_admin_ui import _Page
    from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
    case=dict(case_id='case',candidate_hash='hash',ticker='AAA',classification='CONTINUATION_CANDIDATE',status='OPEN',current_pb_status='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED',
              previous=dict(fiscal_year=2026,fiscal_quarter='Q2',release_type='ORDINARY_COMMON',economic_unit_rule='ORDINARY_COMMON',accepted_sharesbas=100,provider_declared_factor=1,accepted_category='Common'),
              new=dict(fiscal_year=2026,fiscal_quarter='Q3',sharesbas=120,sharefactor=1,category='Common',observation_id='new',content_hash='newhash',parent_equity_usd=2000),deltas={'shares_percent':20})
    calls=[]
    class Service:
        def capabilities(self):return ()
        def publication_safety(self):return {'status':'CLEAR','production_writes_blocked':False}
        def list_history(self,limit=20):return []
        def list_refresh_review_queue(self,**kw):return {'status':'EMPTY','items':[]}
        def list_pb_ownership_reviews(self,**kw):return [case]
        def preview_pb_ownership_review(self,*args,**kw):return dict(held_current={'reason':'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'},hypothetical_current={'value':1.2,'reason':'OK','price':20})
        def approve_pb_ownership_review(self,*args,**kw):calls.append((args,kw));return {'candidate_canonical':'inactive/canonical.db'}
    page=_Page();controls=build_fundamentals_admin_page(page=page,service=Service())
    assert controls.pb_ownership_status_field.value=='Not loaded.'
    controls.review_queue_refresh_button.on_click(None)
    row=controls.pb_ownership_column.controls[0];row.controls[1].controls[0].on_click(None)
    assert calls==[] and page.dialog.actions[1].disabled is True
    content=page.dialog.content.controls;operator=content[1];confirmed=content[2];note=content[3]
    operator.value='Operator';note.value='Reviewed exact new-Q evidence';confirmed.value=True;confirmed.on_change(None)
    assert page.dialog.actions[1].disabled is False
    page.dialog.actions[1].on_click(None)
    assert calls[0][0]==('case',) and calls[0][1]['candidate_hash']=='hash' and calls[0][1]['confirmed'] is True


def test_later_observation_creates_new_case_preserving_held_history(factory):
    f=factory();old=f['case']
    workflow.keep_on_hold(f['queue'],old['case_id'],candidate_hash=old['candidate_hash'],note='Inspect revision')
    with sqlite3.connect(f['cp']) as c:
        c.execute("UPDATE v4_parent_equity_source SET content_hash='later-revision' WHERE fiscalperiod='2026-Q3'")
    workflow.sync(f['queue'],f['cp'],as_of=ASOF,run_id='later-revision')
    cases=RefreshReviewQueue(f['queue']).ownership_items(include_resolved=True)
    assert len(cases)==2 and {c['status'] for c in cases}=={'SUPERSEDED','OPEN'}
    assert next(c for c in cases if c['case_id']==old['case_id'])['result']['note']=='Inspect revision'


def test_identity_override_compatible_category_continuation(factory):
    f=factory('identity')
    with sqlite3.connect(f['cp']) as c:
        c.execute("UPDATE v4_parent_equity_source SET category='Domestic Common Stock' WHERE fiscalperiod='2026-Q3'")
    with ro(f['cp']) as c:case=workflow.detect(c,as_of=ASOF)[0]
    assert case['classification']=='CONTINUATION_CANDIDATE'
    assert case['deltas']['category_changed'] is True


def test_scores_and_provider_storage_unchanged_by_approval(factory):
    f=factory();before={p:digest_db(f[p]) for p in ('ap','pp')}
    approve(f)
    assert {p:digest_db(f[p]) for p in ('ap','pp')}==before


def test_legacy_repin_cannot_drop_embedded_history(factory):
    from rawcandle.fundamentals.pb_reporting_contract import repin_quarterly_reviews
    f=factory();result=approve(f);candidate=Path(result['candidate_canonical']);before=candidate.read_bytes()
    with pytest.raises(ValueError,match='USE_VERSIONED_REVIEW_WORKFLOW'):
        repin_quarterly_reviews(candidate,expected_artifact_sha256=result['registry_sha256'])
    assert candidate.read_bytes()==before


def test_new_active_class_blocks_continuation(factory):
    f=factory()
    with sqlite3.connect(f['cp']) as c:
        c.execute("INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) VALUES(2,1,'AAA.B',1,'n','n')")
    with ro(f['cp']) as c:case=workflow.detect(c,as_of=ASOF)[0]
    assert case['classification']=='REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE'
    with pytest.raises(ValueError,match='STALE_CANDIDATE'):approve(f)
