"""Controlled current-state rebuild receipts for the existing locked backup cleanup owner.

This module never publishes, repairs or deletes a file. It verifies the native
journal, generation lineage and completed typed rows before adapting their receipt.
Only the current completed journal/generation can release rollback backups.
"""
from pathlib import Path
import sqlite3

from . import publication_journal as journal
from .provider_payload import payload_fingerprint as digest

SCHEMA='CONTROLLED_CURRENT_STATE_REBUILD_ACCEPTANCE_V1'


def _check(condition, reason):
    from .run_acceptance_cleanup import RunAcceptanceCleanupError
    if not condition:raise RunAcceptanceCleanupError('CURRENT_REBUILD_ACCEPTANCE_'+reason)


def record_completed(project_root, queue_path, publication):
    """Persist the actual completed native publication, never a fabricated Apply."""
    from . import current_state_rebuild as w
    root=Path(project_root).resolve();queue=Path(queue_path)
    jp=root/'data/.fundamentals_admin_publication_journal.json';j=journal.load_journal(jp)
    _check(publication.get('journal_state')=='COMPLETED' and publication.get('postflight')=='PASSED'
        and publication.get('ownership_approved') is False and publication.get('pb_approved') is False
        and j and j.get('new_generation_id')==publication.get('generation_id')
        and j.get('operation_type')==w.OPERATION,'NATIVE_PUBLICATION_REQUIRED')
    run_id=publication['generation_id'];directory=root/'fundamental_reports/admin_runs'/run_id
    _check(not directory.is_symlink() and not queue.is_symlink(),'PATH_INVALID')
    directory.mkdir(parents=True,exist_ok=True)
    value=dict(schema=SCHEMA,operation=w.OPERATION,run_id=run_id,queue_path=str(queue.resolve()),
        batch_fingerprint=j['scope_evidence']['preview']['preview_fingerprint'],
        candidate_hashes=j['scope_evidence']['candidate_hashes'],journal_sha256=journal.sha256_file(jp),
        current_state_rebuild_only=True,ownership_approved=False,pb_approved=False)
    receipt={**value,'receipt_fingerprint':digest(value)}
    for name,obj in (('completed_journal.json',j),('result.json',receipt)):
        path=directory/name
        if path.exists():
            from .run_acceptance_cleanup import _load_json
            _check(_load_json(path)==obj,'RECEIPT_CONFLICT')
        else:journal._atomic_json(path,obj)
    from rawcandle.fundamentals.generations import resolve_active_generation
    for_cleanup(receipt,directory=directory,run_id=run_id,journal_path=jp,
        backup_root=root/'backups/fundamentals_admin_production',
        live_paths=resolve_active_generation(root,require_generation=True).role_paths())
    return directory/'result.json'


def for_cleanup(receipt, *, directory, run_id, journal_path, backup_root, live_paths):
    from . import current_state_rebuild as w
    from .provider_payload_review_scope import prove
    from .run_acceptance_cleanup import _load_json, _generation_publication_sources, KNOWN_ROLES
    from .production_transaction import _no_sidecars
    _check(receipt.get('schema')==SCHEMA and receipt.get('operation')==w.OPERATION
        and receipt.get('run_id')==run_id and receipt.get('current_state_rebuild_only') is True
        and receipt.get('ownership_approved') is False and receipt.get('pb_approved') is False
        and receipt.get('receipt_fingerprint')==digest({k:v for k,v in receipt.items() if k!='receipt_fingerprint'}),'RECEIPT_INVALID')
    j=journal.load_journal(journal_path)
    _check(isinstance(j,dict) and j==_load_json(directory/'completed_journal.json')
        and journal.sha256_file(journal_path)==receipt['journal_sha256'],'JOURNAL_CHANGED')
    _check(j.get('operation_type')==w.OPERATION and j.get('new_generation_id')==run_id
        and j.get('production_run_id')==run_id and j.get('publication_mode')=='GENERATION_POINTER','OWNER_INVALID')
    sources=_generation_publication_sources({'journal':j},run_id=run_id)
    _check(sources is not None and set(j['roles'])==KNOWN_ROLES,'GENERATION_REQUIRED')
    active_path=Path(j['active_generation_manifest_path']);root=active_path.parent.parent
    _check(directory==root/'fundamental_reports/admin_runs'/run_id,'RECEIPT_LOCATION_INVALID')
    old=j['old_generation'];old_dir=Path(old['generation_dir']);new_dir=Path(j['new_generation_dir'])
    generation_root=root/'data/fundamentals_generations'
    _check(old_dir==generation_root/old['generation_id'] and new_dir==generation_root/run_id
        and old_dir!=new_dir and not any(p.is_symlink() for p in (generation_root,old_dir,new_dir)),'GENERATION_PATH_INVALID')
    original=_load_json(old_dir/'generation_manifest.json');published=_load_json(new_dir/'generation_manifest.json')
    _check(original==old['manifest'] and published==j['new_generation_manifest']==_load_json(active_path)
        and published['generation_id']==run_id,'MANIFEST_CHANGED')
    scope=j['scope_evidence'];plan=scope['preview'];test=scope['test']
    w.verify(plan,w.PREVIEW,'preview_fingerprint');w.verify(test,w.TEST,'test_fingerprint')
    _check(scope.get('policy')==w.VERSION and plan['policy']==w.VERSION and test['passed'] is True
        and plan['preview_fingerprint']==receipt['batch_fingerprint']==j['refresh_set_fingerprint']
        and test['preview_fingerprint']==plan['preview_fingerprint']
        and test['baseline']==plan['baseline'] and test['test_fingerprint']==j['test_run_id']
        and receipt['candidate_hashes']==scope['candidate_hashes']==test['result']['candidate_hashes'], 'BATCH_MISMATCH')
    queue=Path(receipt['queue_path']);_check(not queue.is_symlink() and queue.is_file(),'QUEUE_INVALID')
    from .artifacts import ROOT
    if root.resolve()==ROOT.resolve():
        _check(queue==root/'fundamental_reports/fundamentals_refresh_review_queue.db','QUEUE_INVALID')
    with w.strict._ro(queue) as c:
        row=c.execute(f'SELECT * FROM {w.TABLE} WHERE generation_id=?',(run_id,)).fetchone()
        _check(row is not None and row['preview_fingerprint']==plan['preview_fingerprint']
            and row['test_fingerprint']==test['test_fingerprint']
            and __import__('json').loads(row['record_json'])==scope,'TYPED_DECISION_CHANGED')
    _check(plan['baseline']['generation_id']==old['generation_id']
        and plan['baseline']['roles']=={r:str(sources[r]) for r in KNOWN_ROLES}
        and plan['baseline']['role_hashes']=={r:original['role_verification'][r]['sha256'] for r in KNOWN_ROLES},'TYPED_SOURCE_LINEAGE_CHANGED')
    _check(prove(plan['proposals'],queue,sources['canonical'],sources['provider'])==plan['source_review_guard'],'REVIEW_CHANGED')
    _check(w.measure(plan,live_paths)==test['result'],'POSTFLIGHT_CHANGED')
    expected_dir=backup_root.resolve()/run_id
    _check(expected_dir.is_dir() and not expected_dir.is_symlink()
        and {p.name for p in expected_dir.iterdir() if p.suffix=='.db'}=={r+'.db' for r in KNOWN_ROLES},'BACKUP_INVENTORY_INVALID')
    backups={};postflight={}
    for role in sorted(KNOWN_ROLES):
        _check(all(isinstance(n,str) and Path(n).name==n and n not in ('','.','..')
            for n in (original['roles'][role],published['roles'][role])),'ROLE_PATH_INVALID')
        before=original['role_verification'][role];after=published['role_verification'][role];jr=j['roles'][role]
        old_path=old_dir/original['roles'][role];new_path=new_dir/published['roles'][role];backup=expected_dir/(role+'.db')
        _check(sources[role]==old_path.resolve() and Path(live_paths[role]).resolve()==new_path.resolve()
            and jr['backup_path']==str(backup) and jr['production_path']==str(new_path)
            and before['sha256']==jr['old_production_fingerprint']==jr['verified_backup_fingerprint']
            and after['sha256']==jr['candidate_fingerprint']==receipt['candidate_hashes'][role]
            and jr.get('candidate_replacement_verified') is True
            and jr.get('replacement_state')=='GENERATION_ACTIVATED_AND_VERIFIED','ROLE_LINEAGE_INVALID')
        _check(not backup.samefile(old_path) and not backup.samefile(new_path),'BACKUP_IN_USE')
        for db,proof in ((old_path,before),(new_path,after),(backup,before)):
            _check(not db.is_symlink() and db.is_file(),'DATABASE_PATH_INVALID')
            from .run_acceptance_cleanup import RunAcceptanceCleanupError
            try:
                _no_sidecars(db)
                checked=journal.sqlite_verification(db)
            except (sqlite3.Error,RuntimeError) as error:
                raise RunAcceptanceCleanupError('CURRENT_REBUILD_ACCEPTANCE_DATABASE_VERIFICATION_FAILED') from error
            _check(checked['sha256']==proof['sha256'] and db.stat().st_size==proof['size_bytes']
                and checked['quick_check']=='ok' and checked['foreign_key_errors']==0,'DATABASE_VERIFICATION_FAILED')
        backups[role]=dict(source=str(old_path),backup=str(backup),verification=dict(sha256=before['sha256'],size=before['size_bytes']))
        postflight[role]=dict(sha256=after['sha256'],size=after['size_bytes'])
    _check(journal.load_journal(journal_path)==j and _load_json(directory/'result.json')==receipt
        and _load_json(active_path)==published,'FINAL_EVIDENCE_CHANGED')
    return dict(run_id=run_id,mode='PRODUCTION_APPLY',outcome='COMPLETED',journal=j,
        rollback={'status':'NOT_REQUIRED'},postflight=postflight,backups=backups,
        acceptance_run_kind='CURRENT_STATE_REBUILD',batch_fingerprint=plan['preview_fingerprint'],
        payload_receipt_fingerprint=receipt['receipt_fingerprint'])
