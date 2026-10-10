"""Terminal receipts and cleanup exercise only synthetic SQLite generations."""
import copy
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from tests.test_publication_drain_run_acceptance import (
    drain, RUN, ROLES, write, database, verification, persist, inspect,
)
from rawcandle.fundamentals.admin import publication_terminal_receipt as receipts
from rawcandle.fundamentals.admin import run_acceptance_cleanup as cleanup
from rawcandle.fundamentals.admin.reviewed_publication_plan import fingerprint


def create(s):
    s['result']['report_path']=str(s['run_dir']/'result.json');persist(s)
    plan=dict(prepared_keys=s['result']['scope_evidence']['applied_natural_keys'],frozen_inputs={},
              plan_fingerprint=s['result']['reviewed_plan']['plan_fingerprint'])
    return receipts.create_for_completed_run(s['result'],s['journal_path'],plan)


def advance(s):
    selected=copy.deepcopy(s['journal']);later=s['new'].parent/'later'
    checks={}
    for role in ROLES:
        database(later/(role+'.db'),'later-'+role);checks[role]=verification(later/(role+'.db'))
    manifest=dict(generation_id='later',roles={r:r+'.db' for r in ROLES},
                  role_verification={r:dict(sha256=checks[r]['sha256'],size_bytes=checks[r]['size'],quick_check='ok') for r in ROLES})
    write(later/'generation_manifest.json',manifest);write(s['pointer'],manifest)
    j=s['journal'];j.update(operation_type='REFRESH_FUNDAMENTALS',production_run_id='later',
        new_generation_id='later',new_generation_dir=str(later),new_generation_manifest=manifest,
        old_generation=dict(generation_id=RUN,generation_dir=str(s['new']),layout='GENERATION_DIRECTORY',
            manifest=selected['new_generation_manifest'],roles={r:str(s['new']/(r+'.db')) for r in ROLES}))
    for role in ROLES:
        j['roles'][role].update(production_path=str(later/(role+'.db')),
            backup_path=str(s['kwargs']['backup_root']/'later'/(role+'.db')),
            old_production_fingerprint=selected['roles'][role]['candidate_fingerprint'],
            candidate_fingerprint=checks[role]['sha256'])
    s['kwargs']['live_paths']={r:later/(r+'.db') for r in ROLES};persist(s)


def reseal(s, value):
    value['receipt_fingerprint']=fingerprint({k:v for k,v in value.items() if k!='receipt_fingerprint'})
    path=s['run_dir']/receipts.NAME;path.chmod(0o644);write(path,value)


def test_creation_determinism_exclusive_storage_and_current_acceptance(drain,monkeypatch):
    monkeypatch.setattr(receipts,'utc_now',lambda:'2026-10-10T06:00:00Z')
    path=create(drain);value=receipts.load(drain['run_dir'])
    assert path.stat().st_mode & 0o222 == 0
    assert inspect(drain)['status']=='ELIGIBLE'
    assert value==receipts.assemble(drain['result'],operation_path=Path(drain['result']['report_path']),
        old_manifest_path=drain['old']/'generation_manifest.json',published_manifest_path=drain['new']/'generation_manifest.json',
        terminal_journal_sha256=receipts.sha256_file(drain['journal_path']),context_only_count=0,
        created_at_utc='2026-10-10T06:00:00Z')
    assert json.loads(Path(drain['result']['report_path']).read_text())==drain['result']
    with pytest.raises(ValueError,match='ALREADY_EXISTS'):create(drain)


@pytest.mark.parametrize(('where','field','value'),[
 ('result','status','FAILED'),('result','rollback',{'status':'RESTORED'}),
 ('journal','state','PREPARED'),('journal','generation_activation_state','READY'),
 ('journal','postflight_state','FAILED'),('journal','rollback_recovery_state','RECOVERY_REQUIRED')])
def test_unsuccessful_or_nonterminal_has_no_receipt(drain,where,field,value):
    drain[where][field]=value
    with pytest.raises((ValueError,cleanup.RunAcceptanceCleanupError)):create(drain)
    assert not list(drain['run_dir'].glob('publication_drain_terminal_receipt*'))


def test_historical_acceptance_and_existing_cleanup_boundary(drain):
    path=create(drain);before=path.read_bytes();advance(drain)
    generations={p:p.read_bytes() for p in drain['new'].parent.rglob('*') if p.is_file()}
    journal=drain['journal_path'].read_bytes();operation=(drain['run_dir']/'result.json').read_bytes()
    assert inspect(drain)['status']=='ELIGIBLE'
    result=cleanup.accept_run_and_cleanup_backups(RUN,**drain['kwargs'],lock_factory=nullcontext)
    assert len(result['files_deleted'])==3
    assert set(result['files_deleted'])=={v['backup'] for v in drain['result']['backups'].values()}
    assert all(p.read_bytes()==data for p,data in generations.items())
    assert path.read_bytes()==before and drain['journal_path'].read_bytes()==journal
    assert (drain['run_dir']/'result.json').read_bytes()==operation


@pytest.mark.parametrize('change',[
 'fingerprint','run','operation_hash','old_generation','new_generation','manifest','plan','membership',
 'terminal','rollback','recovery','backup_path','backup_hash','backup_size','published_size','missing',
 'duplicate','symlink','missing_receipt','operation_changed','nonterminal','current_recovery',
 'dependency','unknown_ancestry','rollback_lineage','current_corrupt','selected_manifest_changed'])
def test_historical_tampering_and_unsafe_lineage_reject(drain,change):
    create(drain);advance(drain);v=receipts.load(drain['run_dir']);role=v['roles']['canonical']
    if change=='fingerprint':v['receipt_fingerprint']='f'*64
    elif change=='run':v['run_id']='other'
    elif change=='operation_hash':v['operation_sha256']='f'*64
    elif change=='old_generation':v['old_generation']['generation_id']='other'
    elif change=='new_generation':v['published_generation']['generation_id']='other'
    elif change=='manifest':v['published_generation']['manifest_fingerprint']='f'*64
    elif change=='plan':v['plan_fingerprint']='f'*64
    elif change=='membership':v['membership_fingerprint']='f'*64
    elif change=='terminal':v['terminal']['state']='PREPARED'
    elif change=='rollback':v['rollback']='RESTORED'
    elif change=='recovery':v['recovery']='REQUIRED'
    elif change=='backup_path':role['backup_path']=str(drain['old']/'canonical.db')
    elif change=='backup_hash':role['backup_sha256']='f'*64
    elif change=='backup_size':role['backup_size']+=1
    elif change=='published_size':role['published_size']+=1
    elif change=='missing':del v['terminal_journal_sha256']
    elif change=='duplicate':write(drain['run_dir']/'publication_drain_terminal_receipt_v2.json',v)
    elif change=='symlink':
        p=drain['run_dir']/receipts.NAME;target=p.with_name('redirect.json');p.rename(target);p.symlink_to(target)
    elif change=='missing_receipt':(drain['run_dir']/receipts.NAME).unlink()
    elif change=='operation_changed':drain['result']['unexpected']='tampered';persist(drain)
    elif change=='nonterminal':drain['journal']['state']='PREPARED';persist(drain)
    elif change=='current_recovery':drain['journal']['rollback_recovery_state']='RECOVERY_REQUIRED';persist(drain)
    elif change=='dependency':drain['journal']['recovery_dependency']=role['backup_path'];persist(drain)
    elif change=='unknown_ancestry':drain['journal']['old_generation']['generation_id']='unknown';persist(drain)
    elif change=='rollback_lineage':drain['journal']['old_generation']=dict(generation_id='old');persist(drain)
    elif change=='current_corrupt':Path(drain['kwargs']['live_paths']['canonical']).write_bytes(b'corrupt')
    elif change=='selected_manifest_changed':write(drain['new']/'generation_manifest.json',{})
    if change in {'fingerprint','run','operation_hash','old_generation','new_generation','manifest','plan','membership',
                  'terminal','rollback','recovery','backup_path','backup_hash','backup_size','published_size','missing'}:
        if change=='fingerprint':
            p=drain['run_dir']/receipts.NAME;p.chmod(0o644);write(p,v)
        else:reseal(drain,v)
    assert inspect(drain)['status']=='NOT_ELIGIBLE'
    assert all(Path(b['backup']).exists() for b in drain['result']['backups'].values())
    assert not (drain['run_dir']/cleanup.CLEANUP_EVIDENCE_NAME).exists()


def test_creation_rejects_symlink_directory(drain):
    create(drain);value=receipts.load(drain['run_dir'])
    link=drain['tmp']/'redirect';link.symlink_to(drain['run_dir'],target_is_directory=True)
    with pytest.raises(ValueError,match='SYMLINK'):receipts.publish(value,link)


def test_successful_execution_integrates_receipt(tmp_path):
    from tests.test_reviewed_publication_plan import prepare,apply
    root,path,_,_=prepare(tmp_path)
    result=apply(root,path)
    assert result['status']=='SUCCESS',result
    assert result['terminal_acceptance_evidence']['status']=='CREATED',result['terminal_acceptance_evidence']
    directory=Path(result['report_path']).parent
    value=receipts.load(directory)
    assert value['operation_sha256']==receipts.sha256_file(Path(result['report_path']))
    assert len(list(directory.glob('publication_drain_terminal_receipt*')))==1


def test_auxiliary_receipt_failure_preserves_publication_success(tmp_path,monkeypatch):
    from tests.test_reviewed_publication_plan import prepare,apply
    from rawcandle.fundamentals.admin.publication_journal import load_journal
    root,path,_,_=prepare(tmp_path)
    def fail(*args):raise OSError('receipt disk unavailable')
    monkeypatch.setattr(receipts,'create_for_completed_run',fail)
    result=apply(root,path)
    assert result['status']=='SUCCESS' and result['rollback']['status']=='NOT_REQUIRED'
    assert result['terminal_acceptance_evidence']['status']=='UNAVAILABLE'
    assert load_journal(root/'data/.fundamentals_admin_publication_journal.json')['state']=='COMPLETED'
    assert not list(Path(result['report_path']).parent.glob('publication_drain_terminal_receipt*'))


@pytest.mark.parametrize('stage',['candidate','activation','postflight'])
def test_execution_failures_create_no_successful_receipt(tmp_path,monkeypatch,stage):
    from tests.test_reviewed_publication_plan import prepare,apply
    from rawcandle.fundamentals.admin import publication_backlog_drain as execution
    from rawcandle.fundamentals.admin.publication_journal import load_journal
    root,path,_,_=prepare(tmp_path)
    def fail(*args,**kwargs):raise RuntimeError('injected '+stage+' failure')
    if stage=='candidate':monkeypatch.setattr(execution,'run_plan_candidate',fail)
    elif stage=='activation':
        original=execution.activate_prepared_generation
        def activate(*args,**kwargs):original(*args,**kwargs);fail()
        monkeypatch.setattr(execution,'activate_prepared_generation',activate)
    else:
        original=execution.sqlite_verification
        def verify(db_path):
            if db_path.parent.name.startswith('publication_drain_'):fail()
            return original(db_path)
        monkeypatch.setattr(execution,'sqlite_verification',verify)
    with pytest.raises(RuntimeError,match='injected'):apply(root,path)
    assert not list((root/'fundamental_reports/publication_drains').glob('*/publication_drain_terminal_receipt*'))
    if stage!='candidate':assert load_journal(root/'data/.fundamentals_admin_publication_journal.json')['state']=='RECOVERED'
