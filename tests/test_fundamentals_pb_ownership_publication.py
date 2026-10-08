"""Copy-only real generation/journal publication of explicitly approved ownership."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import pb_ownership_publication as pub
from rawcandle.fundamentals.admin import pb_ownership_review as review
from rawcandle.fundamentals.admin import publication_journal as journal
from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue, _connect
from rawcandle.fundamentals.generations import prepare_generation_from_candidates,activate_generation,resolve_active_generation
from rawcandle.fundamentals.pb_reporting_contract import generation_ownership_artifact
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals import phase12d
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation
from tests.test_fundamentals_pb_new_quarter_review import factory as base_factory,approve,ro,report,digest_db,ASOF


@pytest.fixture
def setup(base_factory,tmp_path):
    def create(kind='ordinary',two=False):
        f=base_factory(kind)
        if two:
            with sqlite3.connect(f['cp']) as c:
                c.execute("INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) VALUES(2,'BBB','BBB','ACTIVE','n','n')")
                c.execute("INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) VALUES(2,2,'BBB',1,'n','n')")
            with sqlite3.connect(f['pp']) as c:
                c.row_factory=sqlite3.Row
                c.execute("INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,category,payload_json,fetched_at_utc) VALUES('SF1','BBB','2','Domestic Common Stock Primary Class','{}','2026-10-08')")
                for q,shares,equity in [(2,100,1000),(3,120,2000)]:
                    row=f['provider_row'](q,shares,equity)|{'ticker':'BBB','permaticker':'2'}
                    assert insert_production_sharadar_observation(c,row,'run','accepted',company_id=2,security_id=2)
            phase12d.reconcile_canonical(f['pp'],f['cp'],applied_at=ASOF)
            with ro(f['cp']) as c:
                q=c.execute("SELECT q.fiscal_year,q.fiscal_quarter,q.source_reportperiod AS reportperiod,s.observation_id,s.content_hash FROM v4_quarter q JOIN v4_parent_equity_source s USING(quarter_id) WHERE q.company_id=2 AND q.fiscal_quarter='Q2'").fetchone()
            r=deepcopy(f['artifact']['records'][0]);r.update(dict(q));r.update(company_id=2,company_key='BBB',security_id=2,canonical_ticker='BBB')
            f['artifact']['records'].append(r)
            with sqlite3.connect(f['cp']) as c:c.execute('UPDATE v4_pb_reporting_contract SET review_artifact_sha256=?',(hashlib.sha256(review.serialize(f['artifact']).encode()).hexdigest(),))
            with sqlite3.connect(f['mp']) as c:
                c.execute("INSERT INTO osakedata SELECT 'BBB',market,pvm,open,high,low,close FROM osakedata WHERE osake='AAA'")
            review.sync(f['queue'],f['cp'],as_of=ASOF,run_id='two-companies')
        cases=RefreshReviewQueue(f['queue']).ownership_items()
        for case in cases:
            f['case']=case;approve(f)
        root=tmp_path/'isolated_project';(root/'data').mkdir(parents=True)
        inputs={r:root/'data'/(r+'.db') for r in ('provider','canonical','analysis')}
        for r,key in [('provider','pp'),('canonical','cp'),('analysis','ap')]:shutil.copyfile(f[key],inputs[r])
        prepared=prepare_generation_from_candidates(inputs,generation_id='before_ownership_publication',project_root=root,source='ISOLATED_TEST')
        activate_generation(prepared['manifest'],project_root=root)
        shutil.copyfile(f['mp'],root/'data/osakedata.db');shutil.copyfile(f['ap'],root/'data/analysis.db')
        run_root=root/'reports/admin_runs';run_root.mkdir(parents=True)
        workflow=pub.OwnershipPublicationWorkflow(project_root=root,run_root=run_root,as_of=ASOF)
        online_backup(f['queue'],workflow.queue_path)
        ids=[case['case_id'] for case in sorted(cases,key=lambda c:c['ticker'])]
        return dict(f=f,workflow=workflow,root=root,ids=ids,ratio=f['ratio'])
    return create


def cases(s):return RefreshReviewQueue(s['workflow'].queue_path).ownership_items(include_resolved=True)
def active(s):return resolve_active_generation(s['root'],require_generation=True)
def do_publish(s,preview=None,**kw):
    p=preview or s['workflow'].preview(s['ids'])
    return s['workflow'].publish(p['preview_id'],preview_hash=p['preview_hash'],operator='Publishing operator',confirmed=True,rehearsal=True,**kw)


@pytest.mark.parametrize('kind',['ordinary','identity','adr','zero'])
def test_representative_real_pointer_publication_and_postflight(setup,kind):
    s=setup(kind);w=s['workflow'];old=active(s);old_hashes={r:pub.sha256_file(p) for r,p in old.role_paths().items()};old_financial=digest_db(old.role_paths()['canonical'])
    p=w.preview(s['ids'])
    assert active(s).generation_id==old.generation_id and cases(s)[0]['status']=='APPROVED'
    assert p['comparisons'][0]['before']['reason']=='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'
    assert p['comparisons'][0]['candidate']['value']==pytest.approx(1.2*s['ratio'])
    assert p['score_invariance']=='PASSED'
    result=do_publish(s,p);new=active(s)
    assert result['outcome']=='COMPLETED' and new.generation_id==p['candidate_generation_id']
    assert {r:pub.sha256_file(v) for r,v in old.role_paths().items()}==old_hashes
    assert digest_db(new.role_paths()['canonical'])==old_financial
    assert all(pub.sha256_file(new.role_paths()[r])==old_hashes[r] for r in ('provider','analysis'))
    current=report(new.role_paths()['canonical'],s['root']/'data/osakedata.db')
    assert current['current']['value']==pytest.approx(1.2*s['ratio'])
    assert current['current']['ownership_basis']['economic_units']==pytest.approx(120*s['ratio'])
    assert current['current']['parent_equity_usd']==2000
    case=cases(s)[0];assert case['status']=='PUBLISHED'
    metadata=case['result']['publication']
    assert metadata['generation_id']==new.generation_id and metadata['artifact_sha256']==p['artifact_sha256']
    assert metadata['operator']=='Publishing operator' and metadata['candidate_hash']==case['candidate_hash']
    assert metadata['approval_hash']==pub.fingerprint(case['approval']) and metadata['published_at']
    receipt=journal.load_journal(w.journal_path)
    assert receipt['state']=='COMPLETED' and receipt['postflight_state']=='PASSED'
    assert do_publish(s,p)['outcome']=='ALREADY_PUBLISHED'


def rotate(s, mutate=None):
    old=active(s);lane=s['root']/('refresh_'+str(len(list((s['root']/'data/fundamentals_generations').iterdir()))));lane.mkdir()
    paths={r:lane/(r+'.db') for r in old.role_paths()}
    for r,p in old.role_paths().items():shutil.copyfile(p,paths[r])
    if mutate:mutate(paths)
    gen=prepare_generation_from_candidates(paths,generation_id=lane.name,project_root=s['root'],source='SYNTHETIC_OTHER_PUBLICATION')
    activate_generation(gen['manifest'],project_root=s['root'],expected_active_generation_id=old.generation_id)
    return active(s)


def test_explicit_multi_case_bundle_and_deterministic_merge(setup):
    s=setup(two=True);w=s['workflow'];old=active(s)
    with ro(old.role_paths()['canonical']) as c:before,_=generation_ownership_artifact(c)
    p=w.preview(list(reversed(s['ids'])))
    assert w.preview(s['ids'])==p
    assert len(p['artifact']['records'])==len(before['records'])+2
    assert p['artifact']['records'][:len(before['records'])]==before['records']
    assert pub.merge_artifact(before,[v['record'] for v in reversed(p['selected'])])==p['artifact']
    do_publish(s,p)
    assert {c['status'] for c in cases(s)}=={'PUBLISHED'}
    assert {c['result']['publication']['generation_id'] for c in cases(s)}=={p['candidate_generation_id']}


def test_sequential_A_B_rebases_preserves_history_and_unselected_approval(setup):
    s=setup(two=True);w=s['workflow'];before_b=next(c for c in cases(s) if c['case_id']==s['ids'][1])
    pa=w.preview([s['ids'][0]]);do_publish(s,pa)
    assert next(c for c in cases(s) if c['case_id']==s['ids'][1])==before_b
    with ro(active(s).role_paths()['canonical']) as c:after_a,_=generation_ownership_artifact(c)
    # A selected publication must ignore B even though B's old P/B.12 artifact includes A.
    assert len(after_a['records'])==3
    pb=w.preview([s['ids'][1]])
    assert pb['source']['generation_id']==pa['candidate_generation_id']
    assert pb['artifact']['records'][:len(after_a['records'])]==after_a['records']
    assert len(pb['artifact']['records'])==4
    do_publish(s,pb)
    assert {c['status'] for c in cases(s)}=={'PUBLISHED'}
    with ro(active(s).role_paths()['canonical']) as c:after_b,_=generation_ownership_artifact(c)
    assert after_b==pb['artifact']


@pytest.mark.parametrize('status',['OPEN','HELD','PUBLISHED'])
def test_only_approved_case_is_eligible(setup,status):
    s=setup();w=s['workflow']
    with _connect(w.queue_path) as c:c.execute(f'UPDATE {review.CASE_TABLE} SET status=?',(status,))
    with pytest.raises(ValueError,match='APPROVED_CASE_REQUIRED'):w.preview(s['ids'])
    assert not w.journal_path.exists()


@pytest.mark.parametrize('selection',[[],['duplicate','duplicate'],['unknown']])
def test_explicit_selection_required(setup,selection):
    s=setup()
    with pytest.raises(ValueError):s['workflow'].preview(selection)


@pytest.mark.parametrize('sql',[
    "UPDATE v4_parent_equity_source SET observation_id='revised' WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_parent_equity_source SET content_hash='revised' WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_parent_equity_source SET sharesbas=121 WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_parent_equity_source SET sharefactor=.5 WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_parent_equity_source SET category='Preferred Stock' WHERE fiscalperiod='2026-Q3'",
    "UPDATE v4_quarter_financials SET parent_equity_usd=3000 WHERE shares_outstanding=120",
    "UPDATE security SET current_ticker='CHANGED'",
])
def test_stale_approved_binding_fails_closed(setup,sql):
    s=setup()
    def mutate(paths):
        with sqlite3.connect(paths['canonical']) as c:c.execute(sql)
    rotate(s,mutate)
    with pytest.raises(ValueError,match='STALE_ACCEPTED_BASIS'):s['workflow'].preview(s['ids'])
    assert cases(s)[0]['status']=='APPROVED'


def test_newer_accepted_quarter_rejects_old_approval_and_requires_new_case(setup):
    from tests.test_phase12d_operational_rebuild import _insert
    s=setup();w=s['workflow'];f=s['f'];_insert(f['pp'],f['provider_row'](4,140,2400))
    def mutate(paths):
        shutil.copyfile(f['pp'],paths['provider'])
        phase12d.reconcile_canonical(paths['provider'],paths['canonical'],applied_at='2027-01-16',ownership_review_queue_path=w.queue_path)
    rotate(s,mutate);w.as_of='2027-01-16'
    with pytest.raises(ValueError,match='STALE_ACCEPTED_BASIS'):w.preview(s['ids'])
    items=cases(s)
    assert len(items)==2 and {c['new']['fiscal_quarter'] for c in items}=={'Q3','Q4'}
    with ro(active(s).role_paths()['canonical']) as c:
        assert review.detect(c,as_of=w.as_of)[0]['new']['sharesbas']==140


@pytest.mark.parametrize('part',['artifact','candidate_pin','record','type'])
def test_exact_artifact_and_approval_binding(setup,part):
    s=setup();case=cases(s)[0]
    if part=='artifact':Path(case['result']['registry_artifact']).write_text('{}')
    elif part=='candidate_pin':
        with sqlite3.connect(case['result']['candidate_canonical']) as c:c.execute("UPDATE v4_pb_reporting_contract SET review_artifact_sha256='wrong'")
    else:
        with _connect(s['workflow'].queue_path) as c:
            if part=='record':
                approval=case['approval'];approval['record']['exact_factor_denominator']=2
                c.execute(f'UPDATE {review.CASE_TABLE} SET approval_json=?',(json.dumps(approval),))
            else:
                candidate={k:v for k,v in case.items() if k not in ('approval','status','result')};candidate['review_type']='OTHER'
                c.execute(f'UPDATE {review.CASE_TABLE} SET candidate_json=?',(json.dumps(candidate),))
    with pytest.raises(ValueError):s['workflow'].preview(s['ids'])


def test_old_approval_financial_candidate_is_never_reused(setup):
    s=setup();case=cases(s)[0]
    with sqlite3.connect(case['result']['candidate_canonical']) as c:c.execute('UPDATE v4_quarter_financials SET revenue=999999')
    p=s['workflow'].preview(s['ids']);do_publish(s,p)
    with ro(active(s).role_paths()['canonical']) as c:
        assert c.execute('SELECT MAX(revenue) FROM v4_quarter_financials').fetchone()[0]==100


def test_rebase_after_unrelated_refresh_copies_current_analysis(setup):
    s=setup()
    def mutate(paths):
        with sqlite3.connect(paths['analysis']) as c:
            c.execute('CREATE TABLE later_score_state(value)');c.execute("INSERT INTO later_score_state VALUES('preserve fresh state')")
    current=rotate(s,mutate);p=s['workflow'].preview(s['ids'])
    assert p['source']['generation_id']==current.generation_id
    assert p['candidate_hashes']['analysis']==pub.sha256_file(current.role_paths()['analysis'])
    do_publish(s,p)
    with ro(active(s).role_paths()['analysis']) as c:assert c.execute('SELECT value FROM later_score_state').fetchone()[0]=='preserve fresh state'


@pytest.mark.parametrize('changes',[{'confirmed':False},{'confirmed':1},{'operator':''},{'production_intent':True,'rehearsal':False}])
def test_explicit_separate_production_confirmation(setup,changes):
    s=setup();p=s['workflow'].preview(s['ids']);kwargs=dict(preview_hash=p['preview_hash'],operator='Operator',confirmed=True,rehearsal=True)
    kwargs.update(changes)
    with pytest.raises(PermissionError):s['workflow'].publish(p['preview_id'],**kwargs)
    assert cases(s)[0]['status']=='APPROVED' and not s['workflow'].journal_path.exists()


@pytest.mark.parametrize('failure',['BEFORE_ACTIVATION','POSTFLIGHT'])
def test_failure_and_existing_restore_old_recovery_keep_approved_then_retry(setup,failure):
    s=setup();w=s['workflow'];old=active(s);p=w.preview(s['ids'])
    with pytest.raises(RuntimeError,match='INJECTED'):do_publish(s,p,inject_failure_at=failure)
    assert active(s).generation_id==old.generation_id and cases(s)[0]['status']=='APPROVED'
    receipt=journal.load_journal(w.journal_path)
    assert receipt['rollback_recovery_state']=='OLD_GENERATION_RESTORED_AND_VERIFIED'
    assert pub.synchronize(w.queue_path,old.role_paths()['canonical'],journal_path=w.journal_path)==0
    fresh=w.preview(s['ids']);assert fresh['preview_id']!=p['preview_id']
    assert do_publish(s,fresh)['outcome']=='COMPLETED'


@pytest.mark.parametrize('drift',['market','candidate','source','approval','code','date','preview'])
def test_final_gate_rejects_drift(setup,drift,monkeypatch):
    s=setup();w=s['workflow'];p=w.preview(s['ids'])
    if drift=='market':
        with sqlite3.connect(s['root']/'data/osakedata.db') as c:c.execute('UPDATE osakedata SET close=close+1')
    elif drift=='candidate':
        with sqlite3.connect(p['candidates']['analysis']) as c:c.execute('CREATE TABLE changed(value)')
    elif drift=='source':rotate(s)
    elif drift=='approval':
        with _connect(w.queue_path) as c:
            approval=cases(s)[0]['approval'];approval['note']='changed'
            c.execute(f'UPDATE {review.CASE_TABLE} SET approval_json=?',(json.dumps(approval),))
    elif drift=='code':
        original=w._sources
        def changed():
            active,binding=original();binding['code']['changed']='yes';return active,binding
        monkeypatch.setattr(w,'_sources',changed)
    elif drift=='date':w.as_of='2026-10-10'
    else:
        path=w.lanes/p['preview_id']/'preview.json';v=json.loads(path.read_text());v['selection']=[];path.write_text(json.dumps(v))
    with pytest.raises(ValueError):do_publish(s,p)
    assert cases(s)[0]['status']=='APPROVED'


def test_queue_commit_gap_recovered_from_completed_receipt_and_sync_idempotency(setup):
    s=setup();w=s['workflow'];p=w.preview(s['ids'])
    with pytest.raises(RuntimeError,match='QUEUE_FINALIZATION'):do_publish(s,p,inject_failure_at='QUEUE_FINALIZATION')
    assert active(s).generation_id==p['candidate_generation_id'] and cases(s)[0]['status']=='APPROVED'
    assert journal.load_journal(w.journal_path)['postflight_state']=='PASSED'
    for _ in range(2):pub.synchronize(w.queue_path,active(s).role_paths()['canonical'],journal_path=w.journal_path)
    assert cases(s)[0]['status']=='PUBLISHED'
    with ro(w.queue_path) as c:assert c.execute("SELECT COUNT(*) FROM refresh_review_queue_audit WHERE event_type='PB_OWNERSHIP_PUBLISHED'").fetchone()[0]==1


def test_postflight_in_progress_and_inactive_copy_never_consume_approval(setup):
    s=setup();w=s['workflow'];p=w.preview(s['ids']);do_publish(s,p)
    with _connect(w.queue_path) as c:c.execute(f"UPDATE {review.CASE_TABLE} SET status='APPROVED'")
    receipt=journal.load_journal(w.journal_path)
    assert pub.synchronize(w.queue_path,Path(s['f']['case']['new'].get('unused','/tmp/inactive.db')),journal_path=w.journal_path)==0
    journal.update_journal(w.journal_path,receipt,state='POSTFLIGHT',postflight_state='RUNNING')
    assert pub.synchronize(w.queue_path,active(s).role_paths()['canonical'],journal_path=w.journal_path)==0
    assert cases(s)[0]['status']=='APPROVED'


@pytest.mark.parametrize('other_status',['APPROVED','OPEN','HELD'])
def test_only_explicitly_selected_case_changes_queue(setup,other_status):
    s=setup(two=True);w=s['workflow']
    with _connect(w.queue_path) as c:c.execute(f'UPDATE {review.CASE_TABLE} SET status=? WHERE case_id=?',(other_status,s['ids'][1]))
    before=next(c for c in cases(s) if c['case_id']==s['ids'][1])
    do_publish(s,w.preview([s['ids'][0]]))
    assert next(c for c in cases(s) if c['case_id']==s['ids'][1])==before


def test_approval_and_normal_refresh_never_activate_generation(setup):
    s=setup();before=active(s).generation_id;w=s['workflow']
    # Approval was performed by the real P/B.12 helper during setup, without activation.
    assert before=='before_ownership_publication' and cases(s)[0]['status']=='APPROVED'
    review.sync(w.queue_path,active(s).role_paths()['canonical'],as_of=ASOF,run_id='normal-refresh')
    assert active(s).generation_id==before and cases(s)[0]['status']=='APPROVED'


def test_merge_rejects_duplicate_and_conflicting_binding(setup):
    s=setup();p=s['workflow'].preview(s['ids']);record=p['selected'][0]['record']
    for duplicate in (record,record|{'operator_note':'conflict'}):
        with pytest.raises(ValueError,match='DUPLICATE_OR_CONFLICTING'):pub.merge_artifact(p['artifact'],[duplicate])


def test_admin_ui_separate_publication_preview_and_confirmation():
    from tests.test_fundamentals_admin_ui import _Page
    from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
    case=dict(case_id='selected',candidate_hash='approvedhash',ticker='AAA',classification='CONTINUATION_CANDIDATE',status='APPROVED',current_pb_status='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED',
        previous=dict(fiscal_year=2026,fiscal_quarter='Q2',release_type='ORDINARY_COMMON',economic_unit_rule='ORDINARY_COMMON',accepted_sharesbas=100,provider_declared_factor=1,accepted_category='Common'),
        new=dict(fiscal_year=2026,fiscal_quarter='Q3',sharesbas=120,sharefactor=1,category='Common',observation_id='observation',content_hash='content',parent_equity_usd=2000),deltas={'shares_percent':20},
        approval={'approved_at':'2026-10-08','operator':'Reviewing operator'},result={'registry_sha256':'artifact','source_canonical_sha256':'source'},publication_eligibility={'status':'READY','source_generation':'active'})
    calls=[]
    class Service:
        def capabilities(self):return ()
        def publication_safety(self):return {'status':'CLEAR','production_writes_blocked':False}
        def list_history(self,limit=20):return []
        def list_refresh_review_queue(self,**kw):return {'status':'EMPTY','items':[]}
        def list_pb_ownership_reviews(self,**kw):return [case]
        def preview_pb_ownership_publication(self,ids):
            calls.append(('preview',ids))
            return dict(selection=ids,preview_id='preview',preview_hash='previewhash',source={'generation_id':'active','role_hashes':{'canonical':'canonical'}},candidate_generation_id='candidate',
                active_artifact_sha256='old',artifact_sha256='new',score_invariance='PASSED',source_revalidation='PASSED',candidate_hashes={'provider':'p','canonical':'c','analysis':'a'},
                comparisons=[{'ticker':'AAA','before':{'reason':'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED','value':None},'candidate':{'reason':'OK','value':1.2}}])
        def publish_pb_ownership_reviews(self,*args,**kwargs):calls.append(('publish',args,kwargs));return {'outcome':'COMPLETED','generation_id':'candidate'}
    page=_Page();controls=build_fundamentals_admin_page(page=page,service=Service())
    controls.review_queue_refresh_button.on_click(None)
    row=controls.pb_ownership_column.controls[1];actions=row.controls[1].controls
    assert actions[0].disabled is True and actions[1].disabled is True
    actions[2].on_click(None)
    assert calls==[('preview',['selected'])] and page.dialog.actions[1].disabled is True
    page.dialog.actions[1].on_click(None)
    assert len(calls)==1
    fields=page.dialog.content.controls;fields[1].value='Publishing operator';fields[2].value=True;fields[2].on_change(None)
    assert page.dialog.actions[1].disabled is False
    page.dialog.actions[1].on_click(None)
    assert calls[1][0]=='publish' and calls[1][2]['confirmed'] is True and calls[1][2]['preview_hash']=='previewhash'


def test_admin_service_keeps_publication_distinct_and_binds_preview(tmp_path):
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    calls=[]
    class Workflow:
        def preview(self,ids):calls.append(('preview',ids));return {'preview_id':'id'}
        def publish(self,*args,**kw):calls.append(('publish',args,kw));return {'outcome':'COMPLETED'}
    service=FundamentalsAdminUIService(run_root=tmp_path/'runs',recover_publication_on_startup=False,ownership_publication_workflow=Workflow())
    assert service.preview_pb_ownership_publication(['exact-case'])=={'preview_id':'id'}
    assert len(calls)==1
    service.publish_pb_ownership_reviews('id',preview_hash='hash',operator='Operator',confirmed=True)
    assert calls[1][2]==dict(preview_hash='hash',operator='Operator',confirmed=True,production_intent=True)


def test_crash_after_activation_uses_existing_recovery_and_fresh_retry(setup,monkeypatch):
    s=setup();w=s['workflow'];p=w.preview(s['ids']);old=active(s)
    class Crash(BaseException):pass
    original=journal.activate_prepared_generation
    def crash(*args,**kw):
        original(*args,**kw);raise Crash()
    with monkeypatch.context() as m:
        m.setattr(journal,'activate_prepared_generation',crash)
        with pytest.raises(Crash):do_publish(s,p)
    assert active(s).generation_id==p['candidate_generation_id'] and cases(s)[0]['status']=='APPROVED'
    with pytest.raises(journal.PublicationRecoveredRetryRequired):w.preview(s['ids'])
    assert active(s).generation_id==old.generation_id and cases(s)[0]['status']=='APPROVED'
    assert do_publish(s)['outcome']=='COMPLETED'


@pytest.mark.parametrize('drift',['market','candidate','journal'])
def test_final_gate_after_generation_preparation_before_activation(setup,monkeypatch,drift):
    s=setup();w=s['workflow'];p=w.preview(s['ids']);old=active(s);original=pub.prepare_generation_from_candidates
    def changed(*args,**kw):
        prepared=original(*args,**kw)
        if drift=='market':
            with sqlite3.connect(s['root']/'data/osakedata.db') as c:c.execute('UPDATE osakedata SET close=close+1')
        elif drift=='candidate':
            with sqlite3.connect(prepared['roles']['analysis']) as c:c.execute('CREATE TABLE drift(value)')
        else:
            # The wrapper runs before our READY journal transition. Inject at the final gate instead.
            original_sources=w._sources;calls=[0]
            def sources():
                active,binding=original_sources();calls[0]+=1
                if calls[0]==1:
                    receipt=journal.load_journal(w.journal_path)
                    journal.update_journal(w.journal_path,receipt,unexpected_drift=True)
                return active,binding
            monkeypatch.setattr(w,'_sources',sources)
        return prepared
    monkeypatch.setattr(pub,'prepare_generation_from_candidates',changed)
    with pytest.raises(ValueError):do_publish(s,p)
    assert active(s).generation_id==old.generation_id and cases(s)[0]['status']=='APPROVED'


def test_already_published_A_is_idempotent_after_B_publication(setup):
    s=setup(two=True);w=s['workflow'];a=w.preview([s['ids'][0]]);do_publish(s,a)
    b=w.preview([s['ids'][1]]);do_publish(s,b)
    assert do_publish(s,a)['outcome']=='ALREADY_PUBLISHED'
    assert active(s).generation_id==b['candidate_generation_id']


def test_independent_stale_price_gate_does_not_force_availability(setup):
    s=setup();w=s['workflow'];w.as_of='2026-10-20'
    p=w.preview(s['ids']);assert p['comparisons'][0]['candidate']['reason']=='STALE_PRICE'
    do_publish(s,p)
    assert cases(s)[0]['status']=='PUBLISHED'
    assert report(active(s).role_paths()['canonical'],s['root']/'data/osakedata.db',day=w.as_of)['current']['value'] is None


def test_publication_timestamp_is_successful_postflight_time(setup,monkeypatch):
    s=setup();p=s['workflow'].preview(s['ids'])
    times=iter(['2026-10-08T12:00:00Z','2026-10-08T12:05:00Z'])
    monkeypatch.setattr(pub,'utc_now',lambda:next(times))
    do_publish(s,p)
    assert cases(s)[0]['result']['publication']['published_at']=='2026-10-08T12:05:00Z'


def test_queue_transaction_commit_failure_reports_success_receipt_and_recovers(setup,monkeypatch):
    from contextlib import contextmanager
    s=setup();w=s['workflow'];p=w.preview(s['ids']);original=pub._connect
    @contextmanager
    def cannot_commit(path):
        with original(path) as c:
            yield c
            raise sqlite3.OperationalError('simulated queue commit failure')
    with monkeypatch.context() as m:
        m.setattr(pub,'_connect',cannot_commit)
        with pytest.raises(pub.PublicationQueueSyncRequired,match='published and postflight PASSED'):
            do_publish(s,p)
    assert active(s).generation_id==p['candidate_generation_id'] and cases(s)[0]['status']=='APPROVED'
    assert pub.synchronize(w.queue_path,active(s).role_paths()['canonical'],journal_path=w.journal_path)==1
    assert cases(s)[0]['status']=='PUBLISHED'


def test_retry_after_backup_preparation_failure_rebuilds_fresh_attempt(setup,monkeypatch):
    s=setup();w=s['workflow'];p=w.preview(s['ids']);old=active(s);original=pub._verified_backups
    def fail(*args,**kw):
        original(*args,**kw);raise OSError('backup storage failure before journal')
    with monkeypatch.context() as m:
        m.setattr(pub,'_verified_backups',fail)
        with pytest.raises(OSError,match='backup storage failure'):do_publish(s,p)
    assert active(s).generation_id==old.generation_id and cases(s)[0]['status']=='APPROVED'
    fresh=w.preview(s['ids']);assert fresh['preview_id']!=p['preview_id']
    assert do_publish(s,fresh)['outcome']=='COMPLETED'
