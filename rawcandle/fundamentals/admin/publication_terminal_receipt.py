"""Small immutable terminal proofs for reviewed publication-drain acceptance."""
from __future__ import annotations

import json
import re
from pathlib import Path

from rawcandle.fundamentals.admin.publication_journal import load_journal, sha256_file
from rawcandle.fundamentals.admin.reviewed_publication_plan import fingerprint, publish_plan, read_unique_json
from rawcandle.fundamentals.admin.contracts import utc_now

NAME = 'publication_drain_terminal_receipt_v1.json'
TERMINAL = dict(state='COMPLETED', current_publication_step='COMPLETED', postflight_state='PASSED',
                generation_activation_state='ACTIVATED_AND_VERIFIED', rollback_recovery_state='NOT_REQUIRED')
ROLES = {'provider', 'canonical', 'analysis'}


def require(condition, reason):
    if not condition:
        raise ValueError('PUBLICATION_TERMINAL_' + reason)


def validate(receipt):
    require(receipt['schema_version'] == 1 and type(receipt['schema_version']) is int
            and receipt['run_kind'] == 'PUBLICATION_DRAIN', 'SCHEMA')
    require(receipt['receipt_fingerprint'] == fingerprint({k:v for k,v in receipt.items() if k!='receipt_fingerprint'}), 'FINGERPRINT')
    require(receipt['terminal'] == TERMINAL and receipt['rollback'] == receipt['recovery'] == 'NOT_REQUIRED', 'NOT_SUCCESSFUL')
    require(receipt['published_generation']['generation_id'] == receipt['run_id']
            and receipt['old_generation']['generation_id'] != receipt['run_id'], 'GENERATION')
    for value in [receipt['operation_sha256'], receipt['plan_fingerprint'], receipt['membership_fingerprint'],
                  receipt['terminal_journal_sha256'], receipt['old_generation']['manifest_fingerprint'],
                  receipt['published_generation']['manifest_fingerprint'], receipt['scope_fingerprint']]:
        require(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None, 'HASH')
    require(type(receipt['writable_count']) is int and receipt['writable_count'] > 0
            and type(receipt['context_only_count']) is int and receipt['context_only_count'] >= 0, 'COUNTS')
    require(set(receipt['roles']) == ROLES, 'ROLES')
    require(isinstance(receipt['operation_reference'],str) and isinstance(receipt['created_at_utc'],str)
            and isinstance(receipt['proof_references'],list), 'REQUIRED_FIELDS')
    from rawcandle.fundamentals.result_publication import normalize_utc_timestamp
    normalize_utc_timestamp(receipt['created_at_utc'])
    for role,record in receipt['roles'].items():
        require(set(record) == {'old_source','published_path','backup_path','backup_sha256','backup_size',
                                'published_sha256','published_size'}, 'ROLE_FIELDS')
        require(type(record['backup_size']) is int and record['backup_size'] > 0
                and type(record['published_size']) is int and record['published_size'] > 0, 'ROLE_SIZE')
        for k in ('backup_sha256','published_sha256'):
            require(re.fullmatch('[a-f0-9]{64}',record[k]) is not None,'ROLE_HASH')
    if receipt['authorization_fingerprint'] is not None:
        require(re.fullmatch('[a-f0-9]{64}',receipt['authorization_fingerprint']) is not None,'AUTHORIZATION')
    return receipt


def assemble(result, *, operation_path, old_manifest_path, published_manifest_path,
             terminal_journal_sha256, context_only_count, authorization_fingerprint=None,
             proof_references=(), created_at_utc=None):
    """Seal proven inputs; callers must establish terminal authority before publishing."""
    old=read_unique_json(old_manifest_path);new=read_unique_json(published_manifest_path)
    require(result['apply'] is True and result['status']=='SUCCESS'
            and result['journal_state']=='COMPLETED' and result['rollback']=={'status':'NOT_REQUIRED'}, 'RESULT')
    roles={}
    for role in sorted(ROLES):
        b=result['backups'][role];p=result['postflight'][role]
        roles[role]=dict(old_source=b['source'],published_path=str(published_manifest_path.parent/new['roles'][role]),
                         backup_path=b['backup'],backup_sha256=b['verification']['sha256'],backup_size=b['verification']['size'],
                         published_sha256=p['sha256'],published_size=p['size'])
    reviewed=result['reviewed_plan']
    receipt=dict(schema_version=1,run_kind='PUBLICATION_DRAIN',run_id=result['run_id'],
        operation_reference=str(operation_path),operation_sha256=sha256_file(operation_path),
        old_generation=dict(generation_id=old['generation_id'],manifest_path=str(old_manifest_path),manifest_fingerprint=fingerprint(old)),
        published_generation=dict(generation_id=new['generation_id'],manifest_path=str(published_manifest_path),manifest_fingerprint=fingerprint(new)),
        plan_fingerprint=reviewed['plan_fingerprint'],membership_fingerprint=reviewed['prepared_keys_fingerprint'],
        writable_count=reviewed['prepared_key_count'],context_only_count=context_only_count,
        scope_fingerprint=fingerprint(result['scope_evidence']),terminal=dict(TERMINAL),rollback='NOT_REQUIRED',recovery='NOT_REQUIRED',
        roles=roles,terminal_journal_sha256=terminal_journal_sha256,authorization_fingerprint=authorization_fingerprint,
        proof_references=list(proof_references),created_at_utc=created_at_utc or utc_now())
    receipt['receipt_fingerprint']=fingerprint(receipt)
    return validate(receipt)


def publish(receipt, directory):
    validate(receipt)
    require(directory.is_dir() and not any(p.is_symlink() for p in (directory,*directory.parents)), 'SYMLINK')
    require(not list(directory.glob('publication_drain_terminal_receipt_v*.json')), 'ALREADY_EXISTS')
    path=directory/NAME
    publish_plan(receipt,path)
    return path


def load(directory):
    require(not any(p.is_symlink() for p in (directory,*directory.parents)), 'SYMLINK')
    paths=list(directory.glob('publication_drain_terminal_receipt_v*.json'))
    require(paths == [directory/NAME], 'MISSING_OR_CONTRADICTORY_RECEIPTS')
    require(not paths[0].is_symlink(), 'SYMLINK')
    return validate(read_unique_json(paths[0]))


def create_for_completed_run(result, journal_path, plan):
    """Called under the existing publication lock, after final result persistence."""
    from rawcandle.fundamentals.admin import run_acceptance_cleanup as acceptance
    journal=load_journal(journal_path)
    require(journal is not None and all(journal.get(k)==v for k,v in TERMINAL.items()), 'NOT_TERMINAL')
    operation=Path(result['report_path'])
    persisted=read_unique_json(operation)
    require(fingerprint(persisted)==fingerprint(result), 'OPERATION_CHANGED')
    result=persisted  # JSON normalizes tuple keys to lists in the durable operation.
    require(plan['plan_fingerprint']==result['reviewed_plan']['plan_fingerprint']
            and fingerprint(plan['prepared_keys'])==result['reviewed_plan']['prepared_keys_fingerprint']
            and len(plan['prepared_keys'])==result['reviewed_plan']['prepared_key_count'], 'PLAN_CHANGED')
    role_paths={r:Path(journal['roles'][r]['production_path']) for r in ROLES}
    backup_root=Path(result['backups']['canonical']['backup']).parent.parent
    acceptance._publication_drain_result(result,run_id=result['run_id'],journal_path=journal_path,
                                          backup_root=backup_root,live_paths=role_paths)
    keys=set(map(tuple,plan['prepared_keys']))
    context={ (q['company_id'],q['fiscal_year'],q['fiscal_quarter'])
              for record in plan['frozen_inputs'].values() for q in record['quarters'] }
    receipt=assemble(result,operation_path=operation,
        old_manifest_path=Path(journal['old_generation']['generation_dir'])/'generation_manifest.json',
        published_manifest_path=Path(journal['new_generation_dir'])/'generation_manifest.json',
        terminal_journal_sha256=sha256_file(journal_path),context_only_count=len(context-keys),
        authorization_fingerprint=plan.get('execution_authorization_fingerprint'))
    return publish(receipt,operation.parent)


def historical_journal(receipt, result, current, *, live_paths):
    """Only an explicit healthy direct successor is presently provable."""
    validate(receipt)
    require(current is not None and all(current.get(k)==v for k,v in TERMINAL.items()), 'CURRENT_NOT_CLEAN')
    selected=receipt['published_generation'];old=read_unique_json(Path(receipt['old_generation']['manifest_path']))
    published=read_unique_json(Path(selected['manifest_path']))
    require(fingerprint(old)==receipt['old_generation']['manifest_fingerprint']
            and fingerprint(published)==selected['manifest_fingerprint']
            and old['generation_id']==receipt['old_generation']['generation_id']
            and published['generation_id']==selected['generation_id'], 'MANIFEST_CHANGED')
    require(receipt['run_id']==result['run_id'] and receipt['operation_sha256']==sha256_file(Path(receipt['operation_reference']))
            and read_unique_json(Path(receipt['operation_reference']))==result, 'OPERATION_CHANGED')
    require(receipt['plan_fingerprint']==result['reviewed_plan']['plan_fingerprint']
            and receipt['membership_fingerprint']==result['reviewed_plan']['prepared_keys_fingerprint']
            and receipt['writable_count']==result['reviewed_plan']['prepared_key_count']
            and receipt['scope_fingerprint']==fingerprint(result['scope_evidence']), 'SCOPE_CHANGED')
    for role, record in receipt['roles'].items():
        backup=result['backups'][role];post=result['postflight'][role]
        require(record['backup_path']==backup['backup'] and record['old_source']==backup['source']
                and record['backup_sha256']==backup['verification']['sha256']
                and record['backup_size']==backup['verification']['size']
                and record['published_sha256']==post['sha256'] and record['published_size']==post['size'],
                'ROLE_METADATA_CHANGED')
    require(current['old_generation']['generation_id']==selected['generation_id']
            and current['old_generation']['manifest']==published, 'UNKNOWN_ANCESTRY')
    require(current['old_generation']['generation_dir']==str(Path(selected['manifest_path']).parent)
            and all(current['old_generation']['roles'][r]==receipt['roles'][r]['published_path']
                    and current['roles'][r]['old_production_fingerprint']==receipt['roles'][r]['published_sha256']
                    for r in ROLES), 'SUCCESSOR_OLD_ROLE_MISMATCH')
    require(current['publication_mode']=='GENERATION_POINTER'
            and current['operation_type'] in {'REFRESH_FUNDAMENTALS','RESULT_PUBLICATION_BACKLOG_DRAIN'}
            and current['new_generation_id'] != selected['generation_id'], 'SUCCESSOR_INVALID')
    active=read_unique_json(Path(current['active_generation_manifest_path']))
    current_dir=Path(current['new_generation_dir'])
    require(current_dir==Path(current['active_generation_manifest_path']).parent/'fundamentals_generations'/current['new_generation_id']
            and not any(p.is_symlink() for p in (current_dir,*current_dir.parents)), 'CURRENT_GENERATION_PATH')
    require(active==current['new_generation_manifest']
            and active==read_unique_json(Path(current['new_generation_dir'])/'generation_manifest.json')
            and active['generation_id']==current['new_generation_id'], 'CURRENT_MANIFEST_CHANGED')
    # Selected rollback files must not be referenced anywhere in current recovery evidence.
    strings=json.dumps(current)
    require(all(r['backup_path'] not in strings for r in receipt['roles'].values()), 'CURRENT_BACKUP_DEPENDENCY')
    for role in ROLES:
        path=Path(live_paths[role]);jr=current['roles'][role]
        name=active['roles'][role]
        require(isinstance(name,str) and Path(name).name==name and path==current_dir/name
                and str(path)==jr['production_path'] and sha256_file(path)==jr['candidate_fingerprint']
                ==active['role_verification'][role]['sha256'] and jr['candidate_replacement_verified'] is True
                and jr['replacement_state']=='GENERATION_ACTIVATED_AND_VERIFIED'
                and path.stat().st_size==active['role_verification'][role]['size_bytes'],
                'CURRENT_ROLE_CHANGED')
        from rawcandle.fundamentals.admin.run_acceptance_cleanup import _integrity
        _integrity(path)
    # A normalized terminal view from the receipt and hash-bound operation, never a stored journal rewrite.
    roles={r:dict(production_path=v['published_path'],backup_path=v['backup_path'],
                 old_production_fingerprint=v['backup_sha256'],verified_backup_fingerprint=v['backup_sha256'],
                 candidate_fingerprint=v['published_sha256'],candidate_replacement_verified=True,
                 replacement_state='GENERATION_ACTIVATED_AND_VERIFIED') for r,v in receipt['roles'].items()}
    return dict(receipt['terminal'],operation_type='RESULT_PUBLICATION_BACKLOG_DRAIN',production_run_id=receipt['run_id'],
                publication_mode='GENERATION_POINTER',new_generation_id=receipt['run_id'],
                new_generation_dir=str(Path(selected['manifest_path']).parent),new_generation_manifest=published,
                active_generation_manifest_path=current['active_generation_manifest_path'],
                old_generation=dict(generation_id=old['generation_id'],generation_dir=str(Path(receipt['old_generation']['manifest_path']).parent),
                                    layout='GENERATION_DIRECTORY',manifest=old,roles={r:v['old_source'] for r,v in receipt['roles'].items()}),
                roles=roles,scope_evidence=result['scope_evidence'])


def reconstruct_p17(project_root, *, created_at_utc):
    """One bounded backfill from the two exact committed operator audit records."""
    import subprocess
    from rawcandle.fundamentals.admin import run_acceptance_cleanup as acceptance
    from rawcandle.fundamentals.admin import policy_reviewed_publication_plan as policy
    from rawcandle.fundamentals.generations import resolve_active_generation
    root=project_root.resolve();run='publication_drain_20261009T175136Z_e99387cf'
    proof_inputs=[
        ('13de79ae0d51d9e5e4991e33ec4ba26ae55cd6b0','docs/fundamentals_v4/fundamentals_v4_historical_publication_p17_execution.md',
         '0bc2c23a4d308f4d22697dc51a00cfe03c49bb7dc38dbcc85666e2a5cfd324c2'),
        ('a219365188a44afe0374dd1aac88ced2b38f0d10','docs/fundamentals_v4/fundamentals_v4_historical_publication_p17_acceptance.md',
         'c5f7af1d9bccba52defbbf1aaaa1cc728e7feadf162e64e61a06581486afbaff')]
    from hashlib import sha256
    proofs=[];texts=[]
    for commit,path,digest in proof_inputs:
        raw=subprocess.check_output(['git','show',commit+':'+path],cwd=root)
        require(sha256(raw).hexdigest()==digest,'BACKFILL_AUDIT_CHANGED')
        proofs.append(dict(git_commit=commit,path=path,sha256=digest));texts.append(raw.decode())
    require('Journal: **COMPLETED**; activation: **ACTIVATED_AND_VERIFIED**; postflight: **PASSED**; rollback/recovery: **NOT_REQUIRED**.' in texts[0]
            and 'all 85' in texts[0].lower(), 'BACKFILL_TERMINAL_UNPROVEN')
    journal_hash='a45cf8349978c76cd1f5e1cb82b24e13e008f463a48d865d5ee2484beba4a3f8'
    require('`'+str(root/'data/.fundamentals_admin_publication_journal.json')+'` | `'+journal_hash+'`' in texts[1],
            'BACKFILL_JOURNAL_HASH_UNPROVEN')
    directory=root/'fundamental_reports/publication_drains'/run;operation=directory/'result.json'
    result=read_unique_json(operation)
    require(sha256_file(operation)=='afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1','BACKFILL_OPERATION_CHANGED')
    docs=root/'docs/fundamentals_v4'
    plan_path=docs/'reviewed_publication_plans/historical_publication_policy_plan_v3.f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70.json'
    require(sha256_file(plan_path)=='6c6d05c835ce6c286ff37583aab966f6f2d9f4c92d46aaa16ce970ae1ab150d2','BACKFILL_PLAN_CHANGED')
    plan=policy.validate_policy_plan(read_unique_json(plan_path))
    authorization=docs/'review_execution_authorizations/historical_publication_execution_authorization_v1.1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d.json'
    auth=read_unique_json(authorization)
    require(auth['authorization_fingerprint']==fingerprint({k:v for k,v in auth.items() if k!='authorization_fingerprint'})
            =='1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d'
            and auth['plan_fingerprint']==plan['plan_fingerprint']==result['reviewed_plan']['plan_fingerprint']
            and auth['exact_writable_keys']==plan['prepared_keys'] and auth['operator_confirmation']=='YES'
            and auth['publication_authorized'] is True and auth['production_apply_authorized'] is True
            and auth['membership_fingerprint']==plan['prepared_keys_fingerprint']
            and auth['approved_handoff_fingerprint']==plan['approved_handoff_fingerprint']
            and auth['evidence_approval_fingerprint']==plan['approval_fingerprint']
            and auth['proposal_fingerprint']==plan['proposal_fingerprint'], 'BACKFILL_AUTHORIZATION')
    old_path=Path(result['backups']['canonical']['source']).parent/'generation_manifest.json'
    new_path=root/'data/fundamentals_generations'/run/'generation_manifest.json'
    require(fingerprint(read_unique_json(old_path))==auth['active_generation_manifest_fingerprint']
            ==plan['active_generation_manifest_fingerprint'], 'BACKFILL_OLD_MANIFEST')
    require(fingerprint(read_unique_json(new_path))=='ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a'
            and plan['active_generation_id']==result['source_generation']==auth['active_generation_id'], 'BACKFILL_GENERATION')
    context={(q['company_id'],q['fiscal_year'],q['fiscal_quarter']) for r in plan['frozen_inputs'].values() for q in r['quarters']}
    require(len(plan['prepared_keys'])==85 and len(context-set(map(tuple,plan['prepared_keys'])))==116, 'BACKFILL_CONTEXT')
    receipt=assemble(result,operation_path=operation,old_manifest_path=old_path,published_manifest_path=new_path,
        terminal_journal_sha256=journal_hash,context_only_count=116,authorization_fingerprint=auth['authorization_fingerprint'],
        proof_references=proofs+[dict(path=str(plan_path),sha256=sha256_file(plan_path)),dict(path=str(authorization),sha256=sha256_file(authorization))],
        created_at_utc=created_at_utc)
    current=resolve_active_generation(root,require_generation=True)
    acceptance._publication_drain_result(result,run_id=run,journal_path=root/'data/.fundamentals_admin_publication_journal.json',
        backup_root=root/'backups/fundamentals_admin_production',live_paths=current.role_paths(),directory=directory,terminal_receipt=receipt)
    return receipt
