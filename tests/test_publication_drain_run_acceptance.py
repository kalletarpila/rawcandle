"""P1.7 report shape with small synthetic SQLite generations/backups only."""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import run_acceptance_cleanup as cleanup
from rawcandle.fundamentals.admin.artifacts import sha256_file

RUN = 'publication_drain_synthetic'
ROLES = ('provider', 'canonical', 'analysis')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def database(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sentinel(value TEXT)')
        db.execute('INSERT INTO sentinel VALUES(?)', (value,))


def verification(path):
    return dict(sha256=sha256_file(path),size=path.stat().st_size,quick_check='ok',foreign_key_errors=0)


@pytest.fixture
def drain(tmp_path):
    reports=tmp_path/'fundamental_reports';run_dir=reports/'publication_drains'/RUN
    root=tmp_path/'data/fundamentals_generations';old=root/'old';new=root/RUN
    pointer=tmp_path/'data/fundamentals_active_generation.json';backup_root=tmp_path/'backups'
    old_roles={};new_roles={};backups={};source={};post={};journal_roles={}
    for role in ROLES:
        old_path=old/(role+'.db');new_path=new/(role+'.db');backup=backup_root/RUN/(role+'.db')
        database(old_path,'old-'+role);database(new_path,'new-'+role)
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old_path,backup)
        old_roles[role]=str(old_path);new_roles[role]=new_path
        source[role]=verification(old_path);post[role]=verification(new_path)
        backups[role]=dict(source=str(old_path),backup=str(backup),source_sha256=source[role]['sha256'],verification=verification(backup))
        journal_roles[role]=dict(backup_path=str(backup),production_path=str(new_path),old_production_fingerprint=source[role]['sha256'],verified_backup_fingerprint=source[role]['sha256'],candidate_fingerprint=post[role]['sha256'],candidate_replacement_verified=True,replacement_state='GENERATION_ACTIVATED_AND_VERIFIED')
    def manifest(gid,checks):
        return dict(generation_id=gid,roles={r:r+'.db' for r in ROLES},role_verification={r:dict(sha256=checks[r]['sha256'],size_bytes=checks[r]['size'],quick_check='ok') for r in ROLES})
    original=manifest('old',source);published=manifest(RUN,post)
    write(old/'generation_manifest.json',original);write(new/'generation_manifest.json',published);write(pointer,published)
    keys=[[1,2025,'Q1']]
    key_hash=hashlib.sha256(json.dumps(keys,separators=(',',':')).encode()).hexdigest()
    reviewed=dict(scope_mode='REVIEWED_APPLY_PLAN',plan_fingerprint='a'*64,prepared_key_count=1,prepared_keys_fingerprint=key_hash)
    scope={**reviewed,'applied_count':1,'selected_count':1,'selected_natural_keys':keys,'applied_natural_keys':keys}
    publication=dict(status='SUCCESS',total_processed=1,new_verified=1,applied_count=1,unprocessed_selected=0,skipped_error_natural_keys=[],applied_natural_keys=keys)
    result=dict(operation='RESULT_PUBLICATION_BACKLOG_DRAIN',run_id=RUN,apply=True,status='SUCCESS',journal_state='COMPLETED',rollback=dict(status='NOT_REQUIRED'),source_generation='old',activated_generation=RUN,reviewed_plan=reviewed,scope_evidence=scope,publication=publication,source_verification=source,backups=backups,postflight=post)
    journal=dict(journal_format_version=1,operation_type=result['operation'],state='COMPLETED',current_publication_step='COMPLETED',postflight_state='PASSED',rollback_recovery_state='NOT_REQUIRED',generation_activation_state='ACTIVATED_AND_VERIFIED',production_run_id=RUN,publication_mode='GENERATION_POINTER',new_generation_id=RUN,new_generation_dir=str(new),new_generation_manifest=published,active_generation_manifest_path=str(pointer),old_generation=dict(generation_id='old',generation_dir=str(old),layout='GENERATION_DIRECTORY',roles=old_roles,manifest=original),roles=journal_roles,scope_evidence=scope)
    journal_path=tmp_path/'data/journal.json';write(journal_path,journal);write(run_dir/'result.json',result)
    kwargs=dict(run_root=reports/'admin_runs',backup_root=backup_root,journal_path=journal_path,live_paths=new_roles)
    return dict(tmp=tmp_path,run_dir=run_dir,result=result,journal=journal,kwargs=kwargs,journal_path=journal_path,old=old,new=new,pointer=pointer)


def persist(s):
    write(s['run_dir']/'result.json',s['result']);write(s['journal_path'],s['journal'])


def inspect(s, **kwargs):
    return cleanup.inspect_cleanup_eligibility(RUN,**(s['kwargs']|kwargs))


def test_p17_shape_resolves_known_root_and_is_eligible(drain):
    s=drain;raw=(s['run_dir']/'result.json').read_bytes()
    assert 'mode' not in s['result'] and 'outcome' not in s['result'] and 'journal' not in s['result']
    # These fields caused the legacy mode/outcome/embedded-journal rejection.
    eligible=inspect(s)
    assert eligible['status']=='ELIGIBLE' and eligible['run_kind']=='PUBLICATION_DRAIN'
    assert eligible['backup_count']==3 and eligible['bytes_freed']==sum(Path(b['backup']).stat().st_size for b in s['result']['backups'].values())
    assert inspect(s,run_root=s['run_dir'].parent)['status']=='ELIGIBLE'
    assert (s['run_dir']/'result.json').read_bytes()==raw
    assert not (s['run_dir']/cleanup.CLEANUP_EVIDENCE_NAME).exists()


@pytest.mark.parametrize(('location','field','value'), [
 ('result','apply',False),('result','apply',1),('result','status','FAILED'),('result','status','RUNNING'),
 ('result','journal_state','PREPARED'),('result','run_id','other'),('result','activated_generation','other'),
 ('result','source_generation','other'),('result','operation','UNKNOWN'),
 ('result','rollback',{'status':'RESTORED'}),('result','postflight',{}),('result','publication',{}),
 ('journal','state','PREPARED'),('journal','postflight_state','FAILED'),
 ('journal','generation_activation_state','READY'),('journal','rollback_recovery_state','RECOVERY_FAILED'),
 ('journal','production_run_id','other'),('journal','operation_type','other'),('journal','new_generation_id','other'),
 ('journal','scope_evidence',{}),('journal','new_generation_manifest',{}),
])
def test_terminal_or_lineage_drift_rejects_without_deletion(drain,location,field,value):
    s=drain;s[location][field]=value;persist(s)
    assert inspect(s)['status']=='NOT_ELIGIBLE'
    with pytest.raises(cleanup.RunAcceptanceCleanupError):
        cleanup.accept_run_and_cleanup_backups(RUN,**s['kwargs'],lock_factory=nullcontext)
    assert len(list((s['kwargs']['backup_root']/RUN).iterdir()))==3


@pytest.mark.parametrize('role',ROLES)
def test_each_missing_role_rejects(drain,role):
    s=drain;Path(s['result']['backups'][role]['backup']).unlink()
    assert inspect(s)['status']=='NOT_ELIGIBLE'


@pytest.mark.parametrize('mutation',['hash','size','symlink','extra','source','backup_path','postflight_hash','old_hash','embedded_journal','corrupt_sqlite','live_sqlite','missing_manifest','later_journal','later_generation','duplicate_root','symlink_root'])
def test_backup_integrity_and_evidence_fail_closed(drain,mutation):
    s=drain;b=s['result']['backups']['canonical'];path=Path(b['backup'])
    if mutation=='hash':b['verification']['sha256']='f'*64
    elif mutation=='size':b['verification']['size']+=1
    elif mutation=='symlink':path.unlink();path.symlink_to(s['old']/'canonical.db')
    elif mutation=='extra':(path.parent/'extra.db').write_text('unexpected')
    elif mutation=='source':b['source']=str(s['new']/'canonical.db')
    elif mutation=='backup_path':b['backup']=str(s['old']/'canonical.db')
    elif mutation=='postflight_hash':s['result']['postflight']['canonical']['sha256']='f'*64
    elif mutation=='old_hash':s['journal']['roles']['canonical']['old_production_fingerprint']='f'*64
    elif mutation=='embedded_journal':s['result']['journal']={'production_run_id':'other'}
    elif mutation=='corrupt_sqlite':
        path.write_bytes(b'corrupt sqlite')
        # Make metadata/hashes agree, proving independent SQLite checks reject it.
        v=verification(path);b['verification']=v;b['source_sha256']=v['sha256'];s['result']['source_verification']['canonical']=v
        s['journal']['roles']['canonical'].update(old_production_fingerprint=v['sha256'],verified_backup_fingerprint=v['sha256'])
        old=s['journal']['old_generation']['manifest'];old['role_verification']['canonical']=dict(sha256=v['sha256'],size_bytes=v['size'],quick_check='ok');write(s['old']/'generation_manifest.json',old)
    elif mutation=='live_sqlite':(s['new']/'canonical.db').write_bytes(b'bad')
    elif mutation=='missing_manifest':(s['old']/'generation_manifest.json').unlink()
    elif mutation=='later_journal':s['journal']['production_run_id']='later_successful_run'
    elif mutation=='later_generation':write(s['pointer'],dict(generation_id='later_successful_run'))
    elif mutation=='duplicate_root':write(s['kwargs']['run_root']/RUN/'result.json',s['result'])
    else:
        target=s['run_dir'].parent;saved=target.with_name('saved');target.rename(saved);target.symlink_to(saved,target_is_directory=True)
    persist(s)
    assert inspect(s)['status']=='NOT_ELIGIBLE'
    assert not (s['run_dir']/cleanup.CLEANUP_EVIDENCE_NAME).exists()


def test_existing_delete_boundary_only_removes_selected_backups(drain):
    s=drain;before={str(p):p.read_bytes() for base in [s['old'],s['new'],s['run_dir']] for p in base.iterdir() if p.is_file()}
    other=s['kwargs']['backup_root']/'other_run'/'canonical.db';database(other,'other');other_bytes=other.read_bytes()
    outcome=cleanup.accept_run_and_cleanup_backups(RUN,**s['kwargs'],lock_factory=nullcontext)
    assert outcome['cleanup_outcome']=='COMPLETED' and len(outcome['files_deleted'])==3
    assert set(outcome['files_deleted'])=={b['backup'] for b in s['result']['backups'].values()}
    assert not (s['kwargs']['backup_root']/RUN).exists()
    assert all(Path(p).read_bytes()==data for p,data in before.items())
    assert other.read_bytes()==other_bytes
    assert inspect(s)['status']=='ALREADY_CLEANED'
    assert cleanup.accept_run_and_cleanup_backups(RUN,**s['kwargs'],lock_factory=nullcontext)['status']=='ALREADY_CLEANED'


@pytest.mark.parametrize('role',ROLES)
def test_missing_recorded_backup_role_rejects(drain,role):
    drain['result']['backups'].pop(role);persist(drain)
    assert inspect(drain)['status']=='NOT_ELIGIBLE'


def test_journal_change_during_verification_rejects(drain,monkeypatch):
    original=cleanup._integrity
    def drift(path):
        proof=original(path)
        drain['journal']['production_run_id']='later_successful_run'
        write(drain['journal_path'],drain['journal'])
        return proof
    monkeypatch.setattr(cleanup,'_integrity',drift)
    assert inspect(drain)['status']=='NOT_ELIGIBLE'
    assert all(Path(b['backup']).exists() for b in drain['result']['backups'].values())


@pytest.mark.parametrize(('field','value'), [('mode','PREVIEW'),('outcome','FAILED')])
def test_contradictory_result_fields_reject(drain,field,value):
    drain['result'][field]=value;persist(drain)
    assert inspect(drain)['status']=='NOT_ELIGIBLE'
