"""Review coexistence and exact native source-repair acceptance, on copies."""
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
import json,sqlite3
import pytest
from rawcandle.fundamentals.admin import provider_payload_workflow as w,provider_payload_acceptance as acceptance,run_acceptance_cleanup as cleanup
from rawcandle.fundamentals.admin.provider_payload_review_scope import prove
from rawcandle.fundamentals.admin.refresh_review_queue import RefreshReviewQueue,classify_review_scope
from rawcandle.fundamentals.generations import resolve_active_generation
from tests.test_provider_payload_workflow import setup,base_factory,register,publish
from tests.test_fundamentals_historical_freeze import sources,evaluate,change


@pytest.fixture
def reviewed(sources,tmp_path):
    p,h,ids=sources
    scope=classify_review_scope(evaluate(p,'AAA',change(h['AAA'],'equity')))
    queue=tmp_path/'review.db';RefreshReviewQueue(queue).upsert_local(scope,run_id='freeze',published_binding='baseline')
    row=w.load_current_history(p.provider_db,'AAA','ARQ')['rows'][-1]
    proposal=dict(ticker='AAA',identity=scope['identity_binding'],source_key=list(w.source_key(row)),
        comparison={'old_observation_id':row['_provider_observation_id']},proposal_fingerprint='current')
    return p,queue,proposal,scope


def test_current_repair_and_frozen_conflict_coexist_without_consuming_authority(reviewed):
    p,q,proposal,_=reviewed;before={path:path.read_bytes() for path in (p.provider_db,p.canonical_db,q)}
    result=prove([proposal],q,p.canonical_db,p.provider_db)
    assert result['items'][0]['proof']=='DISJOINT_FROZEN_REVIEW_PRESERVED'
    assert result['items'][0]['frozen_conflict_count']==1
    assert RefreshReviewQueue(q).get('AAA')['status']=='OPEN'
    assert all(path.read_bytes()==data for path,data in before.items())


@pytest.mark.parametrize('conflict',['selected_key','identity','unproven','allowed_repair','stale_financial','mixed_reason'])
def test_conflicting_or_incomplete_review_proof_blocks_current_repair(reviewed,conflict):
    p,q,proposal,scope=reviewed;scope=deepcopy(scope)
    if conflict=='selected_key':scope['affected_source_keys'].append(dict(zip(('ticker','dimension','date','reportperiod'),proposal['source_key'])))
    elif conflict=='identity':scope['identity_binding']['security_id']=999
    elif conflict=='unproven':scope['historical_freeze']['conflicts']=[]
    elif conflict=='allowed_repair':scope['historical_freeze']['conflicts'][0]['decision']='FROZEN_REVIEWED_REPAIR_ALLOWED'
    elif conflict=='stale_financial':scope['historical_freeze']['conflicts'][0]['accepted']['revenue']=999
    elif conflict=='mixed_reason':scope['reason_codes'].append('SAME_FISCAL_SOURCE_KEY_REPLACEMENT')
    RefreshReviewQueue(q).upsert_local(scope,run_id='changed',published_binding='baseline')
    before=q.read_bytes()
    with pytest.raises(ValueError,match='PAYLOAD_REVIEW'):prove([proposal],q,p.canonical_db,p.provider_db)
    assert q.read_bytes()==before


def test_fresh_baseline_produces_new_cohort_receipt_and_old_one_stays_stale(setup):
    s=setup;old=deepcopy(s.proposals[0]);register(s)
    with sqlite3.connect(s.root/'data/osakedata.db') as c:c.execute('CREATE TABLE new_quote_source(x)')
    with pytest.raises(ValueError,match='STALE_BASELINE'):w.revalidate(s.root,old,s.history)
    new=w.proposal(s.root,tuple(old['source_key']),s.history,fetched_at_utc=old['source_fetch_timestamp'])
    assert new['comparison']==old['comparison'] and new['repair_id']!=old['repair_id']
    assert w.batch([new])['batch_fingerprint']!=w.batch([old])['batch_fingerprint']
    fresh=w.rehearse(s.root,[new],s.histories,s.root/'fresh_copy',as_of='2026-10-09')
    w.verify_receipts([new],fresh)
    with pytest.raises(ValueError):w.verify_receipts([old],fresh)
    for changed_cohort in ([],[new,new]):
        with pytest.raises(ValueError,match='RECEIPT_SET_INVALID'):w.verify_receipts(changed_cohort,fresh)
    with pytest.raises(ValueError,match='CONFLICTING_PROPOSAL'):
        w.register(s.root,s.queue,[new],fresh,s.histories)
    stable=w.baseline(s.root)
    w.close_item(s.queue,old['repair_id'],status='STALE',reason='Exact prior market baseline changed')
    assert w.register(s.root,s.queue,[new],fresh,s.histories)==[new['repair_id']]
    with w._ro(s.queue) as c:
        assert w._read(c,old['repair_id'])[3]=='STALE' and w._read(c,new['repair_id'])[3]=='OPEN'
        assert w._read(c,old['repair_id'])[0]==old
    assert w.baseline(s.root)==stable
    assert old==s.proposals[0]


@pytest.fixture
def accepted(setup):
    s=setup;register(s);result=publish(s)
    path=acceptance.record_completed(s.root,s.queue,result);s.run_id=result['generation_id'];s.receipt_path=path
    s.cleanup_kwargs=dict(run_root=s.root/'fundamental_reports/admin_runs',backup_root=s.root/'backups/fundamentals_admin_production',
        journal_path=s.root/'data/.fundamentals_admin_publication_journal.json',live_paths=resolve_active_generation(s.root).role_paths())
    return s


def test_native_payload_publication_acceptance_deletes_exact_owned_backups_only(accepted):
    s=accepted;protected=s.cleanup_kwargs['backup_root']/'unrelated/provider.db';protected.parent.mkdir();protected.write_bytes(b'keep')
    old={p:w.journal.sha256_file(p) for p in s.root.joinpath('data/fundamentals_generations').rglob('*.db')}
    before_queue=s.queue.read_bytes();j=s.cleanup_kwargs['journal_path'].read_bytes()
    view=cleanup.inspect_cleanup_eligibility(s.run_id,**s.cleanup_kwargs)
    assert view['eligible'] and view['run_kind']=='PROVIDER_PAYLOAD_REPAIR' and view['backup_count']==3
    result=cleanup.accept_run_and_cleanup_backups(s.run_id,**s.cleanup_kwargs,lock_factory=nullcontext)
    assert result['cleanup_outcome']=='COMPLETED' and result['bytes_freed']==view['bytes_freed']
    assert set(result['files_deleted'])==set(view['backup_files']) and result['run_kind']=='PROVIDER_PAYLOAD_REPAIR'
    assert protected.read_bytes()==b'keep' and s.queue.read_bytes()==before_queue and s.cleanup_kwargs['journal_path'].read_bytes()==j
    assert all(w.journal.sha256_file(p)==sha for p,sha in old.items())
    assert cleanup.inspect_cleanup_eligibility(s.run_id,**s.cleanup_kwargs)['status']=='ALREADY_CLEANED'
    assert cleanup.accept_run_and_cleanup_backups(s.run_id,**s.cleanup_kwargs,lock_factory=nullcontext)['status']=='ALREADY_CLEANED'


@pytest.mark.parametrize('mutation',['scope','receipt','queue','backup','active','journal','extra_backup','symlink','hardlink'])
def test_payload_cleanup_rejects_changed_scope_or_ownership_before_deletion(accepted,mutation):
    s=accepted;jp=s.cleanup_kwargs['journal_path'];j=json.loads(jp.read_text());backup=s.cleanup_kwargs['backup_root']/s.run_id/'provider.db'
    if mutation=='scope':j['scope_evidence']['selected']=[]
    elif mutation=='journal':j['postflight_state']='FAILED'
    elif mutation=='receipt':
        obj=json.loads(s.receipt_path.read_text());obj['batch_fingerprint']='other';s.receipt_path.write_text(json.dumps(obj))
    elif mutation=='queue':
        with sqlite3.connect(s.queue) as c:c.execute(f"UPDATE {w.TABLE} SET status='OPEN',decision_json=NULL")
    elif mutation=='backup':backup.write_bytes(b'wrong')
    elif mutation=='extra_backup':(backup.parent/'unrelated.db').write_bytes(b'keep')
    elif mutation in ('symlink','hardlink'):
        backup.unlink();getattr(backup,'symlink_to' if mutation=='symlink' else 'hardlink_to')(s.cleanup_kwargs['live_paths']['provider'])
    elif mutation=='active':
        with sqlite3.connect(s.cleanup_kwargs['live_paths']['provider']) as c:c.execute('CREATE TABLE corrupt(x)')
    if mutation in ('scope','journal'):
        jp.write_text(json.dumps(j));(s.receipt_path.parent/'completed_journal.json').write_text(json.dumps(j))
    remaining={p:p.read_bytes() for p in backup.parent.iterdir() if p.is_file()}
    assert not cleanup.inspect_cleanup_eligibility(s.run_id,**s.cleanup_kwargs)['eligible']
    with pytest.raises((cleanup.RunAcceptanceCleanupError,ValueError)):
        cleanup.accept_run_and_cleanup_backups(s.run_id,**s.cleanup_kwargs,lock_factory=nullcontext)
    assert all(p.read_bytes()==data for p,data in remaining.items())


def test_live_review_fingerprint_cannot_be_substituted_after_test(setup):
    s=setup;register(s);old=w.baseline(s.root)
    with pytest.raises(ValueError,match='REVIEW_SCOPE_STALE'):publish(s,expected_review_fingerprint='other')
    assert w.baseline(s.root)==old
