"""Generic current-version rebuild, strict ordering and fail-closed lifecycle."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import current_state_rebuild as r
from rawcandle.fundamentals.admin import current_state_rebuild_acceptance as acceptance
from rawcandle.fundamentals.admin import legacy_payload_disposition as disposition
from rawcandle.fundamentals.admin import provider_payload_workflow as strict
from rawcandle.fundamentals.admin import publication_journal as journal
from rawcandle.fundamentals.admin import refresh_fundamentals as source
from rawcandle.fundamentals.admin import full_v2_downstream
from rawcandle.fundamentals.admin.run_acceptance_cleanup import accept_run_and_cleanup_backups,RunAcceptanceCleanupError
from rawcandle.fundamentals.generations import resolve_active_generation
from tests.test_provider_payload_workflow import setup,base_factory


def acquisition(full):
    return r.seal(dict(schema=r.VERSION+'_ACQUISITION',provider='SHARADAR',table='fundamentals',
        endpoint=source.SOURCE_ENDPOINT,ticker='AAA',acquired_at=datetime.now(timezone.utc).isoformat(),
        fields=sorted(full),histories=dict(ARQ=[full],MRQ=[{**full,'dimension':'MRQ'}])), 'acquisition_fingerprint')


@pytest.fixture
def case(setup,monkeypatch):
    s=setup
    full={**s.full,'lastupdated':'2026-10-29'}
    a=acquisition(full)
    base=r.baseline(s.root,s.queue)
    key=tuple(s.proposals[0]['source_key'])
    plan=r.preview(s.root,s.queue,[(key,a)],source_baseline=base)
    # Policy/lifecycle unit fixtures substitute only the expensive downstream
    # calculation. Actual native full-analysis rebuild is exercised in the
    # documented current-state disposable-copy rehearsal.
    def downstream(paths,*,output,as_of_date):
        output.mkdir(parents=True)
        target=output/'analysis_candidate.db'
        shutil.copyfile(base['roles']['analysis'],target)
        return dict(status='READY',action='FULL_V2_REBUILD',candidate_analysis_db=str(target),
            invocation_counts={'full_v2_rebuild':1})
    monkeypatch.setattr(full_v2_downstream,'run_full_v2_downstream',downstream)
    monkeypatch.setattr(r,'acquire',lambda ticker,client=None:deepcopy(a))
    return SimpleNamespace(s=s,a=a,base=base,key=key,plan=plan)


def test_strict_repair_first_never_rebuilds(setup):
    s=setup;a=acquisition(s.full)
    before=s.queue.read_bytes();base=r.baseline(s.root,s.queue)
    answer=r.assess(s.root,tuple(s.proposals[0]['source_key']),a,source_baseline=base)
    assert answer['path']=='EXACT_REPAIR'
    assert answer['proposal']['comparison']['reason']=='SOURCE_PAYLOAD_COMPLETENESS_REPAIR'
    with pytest.raises(ValueError,match='EXACT_REPAIR_MUST_BE_USED'):
        r.preview(s.root,s.queue,[(tuple(s.proposals[0]['source_key']),a)],source_baseline=base)
    assert before==s.queue.read_bytes()


def test_version_preview_is_readonly_and_strict_still_rejects(case):
    c=case;s=c.s;before=s.queue.read_bytes()
    with pytest.raises(ValueError,match='NOT_COMPLETENESS_REPAIR'):
        strict.proposal(s.root,c.key,r.trusted(c.a,'AAA')['ARQ'],fetched_at_utc=c.a['acquired_at'],source_baseline=c.base)
    assert r.preview(s.root,s.queue,[(c.key,c.a)],source_baseline=c.base)==c.plan
    assert s.queue.read_bytes()==before
    assert c.plan['proposals'][0]['new_lastupdated']=='2026-10-29'
    assert r.baseline(s.root,s.queue)==c.base


@pytest.mark.parametrize('mutation',[
    'revenue','reportperiod','fiscalperiod','calendardate','date','company_id','security_id',
    'permaticker','duplicate','competing','incomplete','provider','stale','same_stamp','backwards',
    'removed_old_field','existing_extra_revision','bad_mrq','schema','payload_contradiction',
])
def test_unsafe_fallback_rejected_without_writes(case,mutation):
    c=case;a=deepcopy(c.a);raw=a['histories']['ARQ'][0]
    if mutation in ('revenue','company_id','security_id','permaticker'):raw[mutation]=999
    elif mutation=='reportperiod':raw[mutation]='2026-09-29'
    elif mutation=='fiscalperiod':raw[mutation]='2027-Q3'
    elif mutation=='calendardate':raw[mutation]='2026-12-31'
    elif mutation=='date':raw['date']='2026-10-27'
    elif mutation=='duplicate':a['histories']['ARQ'].append(deepcopy(raw))
    elif mutation=='competing':a['histories']['ARQ'].append({**raw,'date':'2026-10-30','revenue':999})
    elif mutation=='incomplete':raw.pop('equityusd')
    elif mutation=='provider':a['provider']='OTHER'
    elif mutation=='stale':a['acquired_at']='2025-01-01T00:00:00Z'
    elif mutation=='same_stamp':raw['lastupdated']=c.s.history.rows[0]['lastupdated']
    elif mutation=='backwards':raw['lastupdated']='2020-01-01'
    elif mutation=='removed_old_field':raw.pop('sharesbas')
    elif mutation=='existing_extra_revision':raw['currency']='OTHER'
    elif mutation=='bad_mrq':a['histories']['MRQ']=[]
    elif mutation=='schema':a['fields']=list(source.REFRESH_REQUEST_FIELDS)
    elif mutation=='payload_contradiction':raw['dimension']='MRQ'
    if mutation=='same_stamp':
        # This is safe ONLY through strict repair, never through rebuild.
        a=r.seal({k:v for k,v in a.items() if k!='acquisition_fingerprint'},'acquisition_fingerprint')
        with pytest.raises(ValueError,match='EXACT_REPAIR_MUST_BE_USED'):
            r.preview(c.s.root,c.s.queue,[(c.key,a)],source_baseline=c.base)
        return
    if mutation=='existing_extra_revision':
        # The legacy fixture has no currency field to compare. Demonstrate an
        # existing financial payload revision instead of inventing old evidence.
        raw['revenue']=999
    a=r.seal({k:v for k,v in a.items() if k!='acquisition_fingerprint'},'acquisition_fingerprint')
    before=c.s.queue.read_bytes()
    with pytest.raises((ValueError,KeyError)):
        r.preview(c.s.root,c.s.queue,[(c.key,a)],source_baseline=c.base)
    assert before==c.s.queue.read_bytes()


def test_stale_source_and_baseline_are_rejected(case):
    c=case
    changed=deepcopy(c.a);changed['histories']['ARQ'][0]['equity']=999
    changed=r.seal({k:v for k,v in changed.items() if k!='acquisition_fingerprint'},'acquisition_fingerprint')
    with pytest.raises(ValueError,match='STALE_SOURCE'):
        r.revalidate(c.s.root,c.s.queue,c.plan,acquisitions={'AAA':changed})
    with sqlite3.connect(c.s.queue) as q:q.execute('CREATE TABLE unrelated_new_review(x)')
    with pytest.raises(ValueError,match='STALE_BASELINE'):
        r.revalidate(c.s.root,c.s.queue,c.plan)


def test_unsafe_publication_journal_rejected(case):
    c=case
    path=c.s.root/'data/.fundamentals_admin_publication_journal.json'
    path.write_text(json.dumps({'state':'PREPARED','recovery_state':'REQUIRED'}))
    with pytest.raises((ValueError,RuntimeError)):
        r.revalidate(c.s.root,c.s.queue,c.plan)


def test_native_current_rebuild_preserves_history_ownership_and_old_generation(case):
    c=case;s=c.s
    receipt=r.test_on_copies(s.root,s.queue,c.plan,s.root/'rebuild_test',as_of='2026-10-30')
    r.verify_test(c.plan,receipt)
    assert receipt['result']['outcomes']['AAA']['current_complete']
    assert receipt['result']['ownership_unchanged']
    assert receipt['result']['unrelated_canonical_unchanged']
    assert receipt['result']['unrelated_provider_unchanged']
    assert r.baseline(s.root,s.queue)==c.base
    proof=r.provenance(c.plan,c.plan['proposals'][0])
    with strict._ro(Path(c.base['roles']['provider'])) as old:
        assert old.execute('SELECT payload_json FROM provider_observation WHERE observation_id=?',(proof['previous_observation_id'],)).fetchone()
    with strict._ro(Path(receipt['candidates']['provider'])) as new:
        row=new.execute('SELECT * FROM provider_observation WHERE observation_id=?',(proof['new_observation_id'],)).fetchone()
        assert json.loads(row['payload_json'])==c.a['histories']['ARQ'][0]
        assert row['observed_at_utc']=='2026-10-29'
        assert json.loads(row['provenance_json'])=={'current_state_rebuild':proof}


def publish(c,receipt,**kw):
    return r.publish(c.s.root,c.s.queue,c.plan,receipt,
        authorized_preview_fingerprint=c.plan['preview_fingerprint'],rehearsal=True,**kw)


@pytest.fixture
def published(case):
    c=case
    receipt=r.test_on_copies(c.s.root,c.s.queue,c.plan,c.s.root/'rebuild_test',as_of='2026-10-30')
    result=publish(c,receipt)
    path=acceptance.record_completed(c.s.root,c.s.queue,result)
    return c,receipt,result,path


def cleanup(c,result):
    return accept_run_and_cleanup_backups(result['generation_id'],
        run_root=c.s.root/'fundamental_reports/admin_runs',backup_root=c.s.root/'backups/fundamentals_admin_production',
        journal_path=c.s.root/'data/.fundamentals_admin_publication_journal.json',
        live_paths=resolve_active_generation(c.s.root,require_generation=True).role_paths(),lock_factory=nullcontext)


def test_immutable_publication_disposition_and_native_cleanup_are_idempotent(published):
    c,receipt,result,path=published
    j=journal.load_journal(c.s.root/'data/.fundamentals_admin_publication_journal.json')
    assert j['state']=='COMPLETED' and j['postflight_state']=='PASSED'
    assert j['old_generation']['generation_id']==c.base['generation_id']
    assert disposition.list_items(c.s.queue)[0]['disposition']=='ELIGIBLE'
    view=disposition.current_views(disposition.list_items(c.s.queue),*[
        resolve_active_generation(c.s.root,require_generation=True).role_paths()[k] for k in ('canonical','provider')])[0]
    assert not view['stale']
    assert disposition.presentation(view)['label']=='Current provider state rebuilt from fresh authoritative source'
    assert 'Historical accepted data was preserved' in disposition.presentation(view)['lines']
    unrelated=c.s.root/'backups/fundamentals_admin_production/unrelated.db';unrelated.write_bytes(b'preserved')
    first=cleanup(c,result)
    assert len(first['files_deleted'])==3 and first['live_databases_unchanged']
    assert unrelated.read_bytes()==b'preserved'
    again=cleanup(c,result)
    assert again['status']=='ALREADY_CLEANED'
    assert {k:v for k,v in again.items() if k!='status'}=={k:v for k,v in first.items() if k!='status'}


@pytest.mark.parametrize('failure',['BEFORE_ACTIVATION','POSTFLIGHT'])
def test_native_rollback_restores_exact_old_generation(case,failure):
    c=case;s=c.s;queue_before=s.queue.read_bytes()
    receipt=r.test_on_copies(s.root,s.queue,c.plan,s.root/'rebuild_test',as_of='2026-10-30')
    with pytest.raises(RuntimeError,match='INJECTED'):
        publish(c,receipt,inject_failure_at=failure)
    assert resolve_active_generation(s.root,require_generation=True).generation_id==c.base['generation_id']
    assert strict.baseline(s.root)['role_hashes']==c.base['role_hashes']
    assert queue_before==s.queue.read_bytes()
    assert not journal.safety_status(s.root/'data/.fundamentals_admin_publication_journal.json')['production_writes_blocked']


@pytest.mark.parametrize('part',['test','provider','canonical','analysis','authorization'])
def test_tampered_test_cannot_publish(case,part):
    c=case;s=c.s
    receipt=r.test_on_copies(s.root,s.queue,c.plan,s.root/'rebuild_test',as_of='2026-10-30')
    if part=='test':receipt['preview_fingerprint']='changed'
    elif part=='authorization':
        with pytest.raises(ValueError,match='EXACT_AUTHORIZATION'):
            r.publish(s.root,s.queue,c.plan,receipt,authorized_preview_fingerprint='different',rehearsal=True)
        return
    else:
        with sqlite3.connect(receipt['candidates'][part]) as db:db.execute('CREATE TABLE tampered(x)')
    with pytest.raises(ValueError):publish(c,receipt)
    assert resolve_active_generation(s.root,require_generation=True).generation_id==c.base['generation_id']


@pytest.mark.parametrize('mutation',['scope','receipt','queue','backup','active','journal','extra_backup','symlink','hardlink'])
def test_rebuild_cleanup_fails_closed(published,mutation):
    c,receipt,result,path=published;root=c.s.root;run=result['generation_id']
    jp=root/'data/.fundamentals_admin_publication_journal.json';j=json.loads(jp.read_text())
    backup=root/'backups/fundamentals_admin_production'/run/'provider.db'
    if mutation=='scope':j['scope_evidence']['preview']['policy']='OTHER'
    elif mutation=='receipt':v=json.loads(path.read_text());v['batch_fingerprint']='other';path.write_text(json.dumps(v))
    elif mutation=='queue':
        with sqlite3.connect(c.s.queue) as db:db.execute(f"UPDATE {r.TABLE} SET test_fingerprint='other'")
    elif mutation=='backup':
        with sqlite3.connect(backup) as db:db.execute('CREATE TABLE tampered(x)')
    elif mutation=='active':
        active=root/'data/fundamentals_active_generation.json';v=json.loads(active.read_text());v['source']='other';active.write_text(json.dumps(v))
    elif mutation=='journal':j['postflight_state']='FAILED'
    elif mutation=='extra_backup':(backup.parent/'extra.db').write_bytes(b'not owned')
    elif mutation in ('symlink','hardlink'):
        import os
        original=resolve_active_generation(root,require_generation=True).role_paths()['provider'];backup.unlink()
        if mutation=='symlink':backup.symlink_to(original)
        else:os.link(original,backup)
    if mutation in ('scope','journal'):jp.write_text(json.dumps(j))
    with pytest.raises((RunAcceptanceCleanupError,ValueError)):
        cleanup(c,result)
    assert backup.exists()


def test_disposition_rebuild_is_current_only_and_keeps_historical_counts():
    proof=r.seal(dict(policy=r.VERSION,postflight='PASSED',observation_id='new',payload_fingerprint='full',
        generation_id='generation',test_fingerprint='test',preview_fingerprint='preview',frozen_conflict_count=13),'proof_fingerprint')
    e=dict(identity_exact=True,current_source_trusted=True,current_binding_known=True,current_incomplete=False,
        current_healthy=True,contradictions=[],historical_only_count=1,historical_no_current_effect_proven=True,current_state_rebuild=proof)
    row=disposition.item('GENERIC',1,1,e,counts={'legacy':20,'frozen':13},reason=r.VERSION,
        source_binding={'observation_id':'new','payload_fingerprint':'full'})
    assert row['disposition']=='ELIGIBLE' and row['observation_counts']['legacy']==20
    assert 'Frozen historical review remains separate' in disposition.presentation(row)['lines']
    assert disposition.presentation({**row,'stale':True})['label']=='Source-data disposition unresolved'
    assert disposition.decide({**e,'contradictions':['conflict']})=='UNRESOLVED'
    assert disposition.decide({**e,'current_healthy':False,'current_incomplete':True})=='UNRESOLVED'
    proof['postflight']='FAILED'
    assert disposition.decide(e)=='UNRESOLVED'


from tests.test_provider_payload_rebaseline import reviewed
from tests.test_fundamentals_historical_freeze import sources
from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue


def test_generic_separated_frozen_review_can_preview_rebuild_without_consuming_authority(reviewed,tmp_path):
    paths,queue,selected,scope=reviewed
    old=next(x for x in source.load_current_history(paths.provider_db,'AAA','ARQ')['rows']
        if x['_provider_observation_id']==selected['comparison']['old_observation_id'])
    full={**old['_acquisition_payload'],'lastupdated':'2026-10-29','equity':120,'equityusd':100,'sharefactor':1}
    a=acquisition(full)
    base=dict(roles={'provider':str(paths.provider_db),'canonical':str(paths.canonical_db)})
    before={p:p.read_bytes() for p in (queue,paths.provider_db,paths.canonical_db)}
    plan=r.preview(tmp_path,queue,[(tuple(selected['source_key']),a)],source_baseline=base)
    assert plan['source_review_guard']['items'][0]['frozen_conflict_count']==1
    assert plan['source_review_guard']['items'][0]['proof']=='DISJOINT_FROZEN_REVIEW_PRESERVED'
    assert RefreshReviewQueue(queue).get('AAA')['status']=='OPEN'
    assert all(p.read_bytes()==data for p,data in before.items())
    scope=deepcopy(scope);scope['affected_source_keys'].append(dict(zip(('ticker','dimension','date','reportperiod'),selected['source_key'])))
    RefreshReviewQueue(queue).upsert_local(scope,run_id='collision',published_binding='baseline')
    with pytest.raises(ValueError,match='PAYLOAD_REVIEW'):
        r.preview(tmp_path,queue,[(tuple(selected['source_key']),a)],source_baseline=base)


def test_scoped_native_parent_rebuild_empty_scope_leaves_existing_evidence(case,tmp_path):
    from rawcandle.fundamentals.schema.parent_equity import accept_parent_equity
    c=case;target=tmp_path/'canonical.db';shutil.copyfile(c.base['roles']['canonical'],target)
    before=strict._content(target)
    with sqlite3.connect(target) as conn, strict._ro(Path(c.base['roles']['provider'])) as provider:
        conn.row_factory=sqlite3.Row
        assert accept_parent_equity(conn,provider,accepted_at='2026-10-30T00:00:00Z',quarter_ids=[])['bound_quarters']==0
    assert strict._content(target)==before


def test_completed_queue_interruption_recovers_without_republication(case):
    c=case;s=c.s
    receipt=r.test_on_copies(s.root,s.queue,c.plan,s.root/'rebuild_test',as_of='2026-10-30')
    with pytest.raises(RuntimeError,match='QUEUE_SYNC_REQUIRED'):
        publish(c,receipt,inject_failure_at='QUEUE_FINALIZATION')
    active=resolve_active_generation(s.root,require_generation=True)
    assert active.generation_id==r.generation_id(c.plan)
    hashes={k:journal.sha256_file(v) for k,v in active.role_paths().items()}
    answer=r.sync_completed(s.root,s.queue)
    assert answer==r.sync_completed(s.root,s.queue)
    assert hashes=={k:journal.sha256_file(v) for k,v in active.role_paths().items()}
    assert disposition.list_items(s.queue)[0]['disposition']=='ELIGIBLE'
    acceptance.record_completed(s.root,s.queue,answer)


def test_remaining_uniform_capture_gap_is_explicit_and_rebuild_rejects_it(case):
    c=case
    reduced={k:c.a['histories']['ARQ'][0].get(k) for k in source.REFRESH_REQUEST_FIELDS}
    # Existing general HistoryTrust is a normalized-history contract, not a full
    # capture contract. The separate rebuild gate must not inherit that weakness.
    assert source.validate_complete_history([reduced],ticker='AAA',dimension='ARQ').status=='COMPLETE'
    a=deepcopy(c.a);a['histories']['ARQ']=[reduced]
    a=r.seal({k:v for k,v in a.items() if k!='acquisition_fingerprint'},'acquisition_fingerprint')
    with pytest.raises(ValueError,match='INCOMPLETE_PAYLOAD'):
        r.preview(c.s.root,c.s.queue,[(c.key,a)],source_baseline=c.base)


def test_rebuild_only_mrq_gate_does_not_obstruct_native_strict_repair(setup):
    s=setup;a=acquisition(s.full);a['histories']['MRQ']=[]
    a=r.seal({k:v for k,v in a.items() if k!='acquisition_fingerprint'},'acquisition_fingerprint')
    answer=r.assess(s.root,tuple(s.proposals[0]['source_key']),a,source_baseline=r.baseline(s.root,s.queue))
    assert answer['path']=='EXACT_REPAIR'


@pytest.mark.parametrize('frozen_count',[0,13],ids=['current-only','separated-frozen-review'])
def test_rebuilt_state_uses_existing_hobby_history_and_details_without_mutation(frozen_count):
    from tests.test_fundamentals_review_action_first import Service,render,text
    proof=r.seal(dict(policy=r.VERSION,postflight='PASSED',observation_id='new',payload_fingerprint='full',
        generation_id='generation',test_fingerprint='test',preview_fingerprint='preview',frozen_conflict_count=frozen_count),'proof_fingerprint')
    e=dict(identity_exact=True,current_source_trusted=True,current_binding_known=True,current_incomplete=False,
        current_healthy=True,contradictions=[],historical_only_count=1,historical_no_current_effect_proven=True,current_state_rebuild=proof)
    row=disposition.item('GENERIC',1,1,e,counts={'legacy':20},reason=r.VERSION,
        source_binding={'observation_id':'new','payload_fingerprint':'full'})
    before=deepcopy(row)
    class S(Service):
        def list_source_dispositions(self):return [row]
    service=S();controls=render(service)
    shown=text(controls.source_disposition_column,collapsed=True)
    assert 'Source-data disposition history / no current action' in shown
    assert 'Current provider state rebuilt from fresh authoritative source' in shown
    assert 'Historical accepted data was preserved' in shown
    assert ('Frozen historical review remains separate' in shown)==bool(frozen_count)
    assert 'Raw technical evidence / JSON' in shown
    assert 'Raw technical evidence / JSON' not in text(controls.source_disposition_column)
    assert row==before and service.actions==[]
