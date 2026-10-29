"""Shared, source-bound ownership Preview/Test/Production after a safe Refresh.

Financial Refresh remains its own transaction. Ownership failure cannot roll back
that completed publication. V1 owns eligibility; the native ownership workflow
owns all activation/recovery and the existing cleanup owner owns deletion.
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from . import pb_ownership_auto as policy, pb_ownership_review as review
from . import pb_ownership_publication as publication, publication_journal as journal
from .artifacts import ROOT, ADMIN_RUN_ROOT
from .contracts import utc_now
from .production_transaction import production_lock
from .run_acceptance_cleanup import accept_run_and_cleanup_backups, inspect_cleanup_eligibility
from .refresh_review_queue import queue_path_for_run_root
from rawcandle.fundamentals.generations import resolve_active_generation, prepare_generation_from_candidates, activate_generation

FLAG = 'pb_ownership_auto_continuation_enabled'


def configured(config_path: Path = ROOT / 'scheduler_config.json') -> bool:
    from rawcandle.scheduler.config import read_scheduler_config
    return read_scheduler_config(str(config_path)).pb_ownership_auto_continuation_enabled


def partition(canonical: Path, provider: Path, market: Path, queue: Path, *, as_of: str, enabled: bool) -> dict:
    with closing(review._ro(canonical)) as c:
        cases = review.detect(c, as_of=as_of)
    items = [dict(ticker=c['ticker'],case=c,**policy.evaluate(c,canonical_db=canonical,
             provider_db=provider,market_db=market,queue_path=queue,as_of=as_of)) for c in cases]
    return dict(enabled=enabled,policy_version=policy.POLICY,items=items,
                evaluated=len(items),auto_continue=sum(i['partition']=='AUTO_CONTINUE' for i in items),
                manual_review=sum(i['partition']=='MANUAL_REVIEW' for i in items),
                deep_review=sum(i['partition']=='DEEP_REVIEW/BLOCKED' for i in items))


def summary(enabled: bool, **values) -> dict:
    return dict(enabled=enabled,policy_version=policy.POLICY,evaluated=0,auto_continued=0,
                manual_review=0,deep_review=0,published=0,failed_stale=0,**values)


class FutureOwnershipWorkflow:
    def __init__(self, *, project_root=ROOT, run_root=ADMIN_RUN_ROOT, as_of=None, scheduler_log_dir=None):
        self.root=Path(project_root).resolve();self.runs=Path(run_root).resolve()
        if self.root==ROOT.resolve() and self.runs!=ADMIN_RUN_ROOT.resolve():
            raise PermissionError('PB_FUTURE_PRODUCTION_RUN_ROOT_INVALID')
        self.as_of=as_of or utc_now()[:10];self.queue=queue_path_for_run_root(self.runs)
        self.log_dir=scheduler_log_dir if self.root==ROOT.resolve() else str(self.root/'scheduler_logs')

    def _lock(self, *, reentrant=True):
        return production_lock(lock_path=self.root/'temp/.fundamentals_admin_production.lock',
                               scheduler_log_dir=self.log_dir,allow_reentrant=reentrant)

    def _source(self):
        active=resolve_active_generation(self.root,require_generation=True)
        jp=self.root/'data/.fundamentals_admin_publication_journal.json'
        j=journal.load_journal(jp)
        if j and any(j.get(k)!=v for k,v in dict(state='COMPLETED',postflight_state='PASSED',rollback_recovery_state='NOT_REQUIRED').items()):
            raise ValueError('PB_FUTURE_RECOVERY_REQUIRED')
        if any(p.name.endswith('.preparing') for p in (self.root/'data/fundamentals_generations').iterdir()):
            raise ValueError('PB_FUTURE_PREPARING_GENERATION')
        from .production_transaction import _no_sidecars
        for p in active.role_paths().values():_no_sidecars(p)
        roles={r:journal.sha256_file(p) for r,p in active.role_paths().items()}
        if any(roles[r]!=active.manifest['role_verification'][r]['sha256'] for r in roles):
            raise ValueError('PB_FUTURE_ACTIVE_ROLE_CHANGED')
        from .provider_payload_workflow import _content
        source=dict(generation_id=active.generation_id,roles=roles,
            manifest=journal.sha256_file(active.manifest_path),queue=_content(self.queue) if self.queue.exists() else {},
            journal=journal.sha256_file(jp) if jp.exists() else None,
            inputs={name:{suffix:journal.sha256_file(Path(str(self.root/'data'/name)+suffix)) if Path(str(self.root/'data'/name)+suffix).exists() else None
                    for suffix in ('','-wal')} for name in ('osakedata.db','analysis.db')},
            config=journal.sha256_file(self.root/'scheduler_config.json') if (self.root/'scheduler_config.json').exists() else None,
            code={name:journal.sha256_file(ROOT/name) for name in (*publication.CODE_FILES,
                  'rawcandle/fundamentals/admin/pb_ownership_future.py','rawcandle/fundamentals/admin/run_acceptance_cleanup.py')})
        return active,source

    def preview(self, *, enabled: bool) -> dict:
        active,source=self._source();paths=active.role_paths()
        result=partition(paths['canonical'],paths['provider'],self.root/'data/osakedata.db',self.queue,as_of=self.as_of,enabled=enabled)
        result.update(source=source,as_of=self.as_of)
        if self._source()[1]!=source:raise ValueError('PB_FUTURE_PREVIEW_DRIFT')
        result['fingerprint']=publication.exact_hash(result)
        return result

    def _decide(self, plan, output):
        active=resolve_active_generation(self.root,require_generation=True);paths=active.role_paths()
        review.sync(self.queue,paths['canonical'],as_of=self.as_of,run_id='PB_FUTURE_RECONCILIATION')
        selected=[i for i in plan['items'] if i['partition']=='AUTO_CONTINUE']
        for item in selected:
            case=item['case']
            fresh=policy.evaluate(case,canonical_db=paths['canonical'],provider_db=paths['provider'],
                   market_db=self.root/'data/osakedata.db',queue_path=self.queue,as_of=self.as_of)
            if fresh!={k:v for k,v in item.items() if k not in ('ticker','case')}:
                raise ValueError('PB_FUTURE_DECISION_DRIFT')
            review._approve(self.queue,case['case_id'],candidate_hash=case['candidate_hash'],
                canonical_db=paths['canonical'],provider_db=paths['provider'],market_db=self.root/'data/osakedata.db',
                output_root=output,as_of=self.as_of,confirmed=True,automatic=fresh,decision_run_id='PB_FUTURE_AUTO_RECONCILIATION')
        return [i['case']['case_id'] for i in selected]

    def test(self, plan: dict, directory: Path) -> dict:
        if self._source()[1]!=plan['source']:raise ValueError('PB_FUTURE_TEST_SOURCE_DRIFT')
        directory.mkdir(parents=True,exist_ok=False);root=directory/'project'
        active=resolve_active_generation(self.root,require_generation=True);inputs={}
        for role,src in active.role_paths().items():
            dest=root/'inputs'/(role+'.db');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);inputs[role]=dest
        prepared=prepare_generation_from_candidates(inputs,generation_id=active.generation_id,project_root=root,source='PB_FUTURE_COPY_TEST')
        activate_generation(prepared['manifest'],project_root=root)
        def backup(src,dst):
            dst.parent.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(f'file:{src}?mode=ro',uri=True)) as s,closing(sqlite3.connect(dst)) as d:s.backup(d)
        for name in ('osakedata.db','analysis.db'):backup(self.root/'data'/name,root/'data'/name)
        clone=FutureOwnershipWorkflow(project_root=root,run_root=root/'reports/admin_runs',as_of=self.as_of)
        if self.queue.exists():backup(self.queue,clone.queue)
        else:
            from .refresh_review_queue import _connect
            with _connect(clone.queue) as q:q.executescript(review.SCHEMA)
        with clone._lock(reentrant=False):
            ids=clone._decide(plan,clone.runs/'pb_ownership_candidates')
            w=publication.OwnershipPublicationWorkflow(project_root=root,run_root=clone.runs,as_of=self.as_of)
            preview=w.preview(ids)
            published=w.publish(preview['preview_id'],preview_hash=preview['preview_hash'],operator='SYSTEM:COPY_TEST',confirmed=True,rehearsal=True)
            current=resolve_active_generation(root,require_generation=True)
            eligible=inspect_cleanup_eligibility(published['generation_id'],run_root=clone.runs,
                backup_root=root/'backups/fundamentals_admin_production',journal_path=w.journal_path,live_paths=current.role_paths())
            if not eligible['eligible']:raise ValueError('PB_FUTURE_TEST_CLEANUP_NOT_ELIGIBLE')
        if self._source()[1]!=plan['source']:raise ValueError('PB_FUTURE_TEST_SOURCE_DRIFT')
        result=dict(status='PASSED',plan_fingerprint=plan['fingerprint'],source=plan['source'],selection=ids,
                    decisions=[i for i in plan['items'] if i['partition']=='AUTO_CONTINUE'],publication=published,
                    cleanup_eligibility=eligible,candidate_hashes=preview['candidate_hashes'],
                    completed_journal_sha256=journal.sha256_file(w.journal_path))
        result['fingerprint']=publication.exact_hash(result)
        journal._atomic_json(directory/'test_receipt.json',result)
        return result

    def production(self, plan, receipt_path: Path, *, trigger_source: str):
        if receipt_path.is_symlink() or not receipt_path.is_file():raise ValueError('PB_FUTURE_TEST_RECEIPT_INVALID')
        receipt=json.loads(receipt_path.read_text())
        if (receipt.get('status')!='PASSED' or receipt.get('plan_fingerprint')!=plan['fingerprint']
            or receipt.get('source')!=plan['source'] or receipt.get('fingerprint')!=publication.exact_hash({k:v for k,v in receipt.items() if k!='fingerprint'})
            or receipt.get('decisions')!=[i for i in plan['items'] if i['partition']=='AUTO_CONTINUE']
            or receipt.get('selection')!=[i['case']['case_id'] for i in plan['items'] if i['partition']=='AUTO_CONTINUE']):
            raise ValueError('PB_FUTURE_MATCHING_TEST_REQUIRED')
        tested_root=receipt_path.parent/'project';tested_journal=tested_root/'data/.fundamentals_admin_publication_journal.json'
        j=journal.load_journal(tested_journal)
        if (journal.sha256_file(tested_journal)!=receipt['completed_journal_sha256']
            or any(j.get(k)!=v for k,v in dict(state='COMPLETED',postflight_state='PASSED',rollback_recovery_state='NOT_REQUIRED',
                new_generation_id=receipt['publication']['generation_id']).items())):
            raise ValueError('PB_FUTURE_TEST_PUBLICATION_CHANGED')
        tested=resolve_active_generation(tested_root,require_generation=True)
        if any(journal.sha256_file(p)!=receipt['candidate_hashes'][r] for r,p in tested.role_paths().items()):
            raise ValueError('PB_FUTURE_TEST_ROLES_CHANGED')
        if self._source()[1]!=plan['source'] or self.preview(enabled=True)!=plan:
            raise ValueError('PB_FUTURE_PRODUCTION_SOURCE_DRIFT')
        ids=self._decide(plan,self.runs/'pb_ownership_candidates')
        if ids!=receipt['selection']:raise ValueError('PB_FUTURE_TEST_SELECTION_CHANGED')
        w=publication.OwnershipPublicationWorkflow(project_root=self.root,run_root=self.runs,as_of=self.as_of,scheduler_log_dir=self.log_dir)
        preview=w.preview(ids)
        published=w.publish(preview['preview_id'],preview_hash=preview['preview_hash'],operator='SYSTEM:'+trigger_source,
                            confirmed=True,production_intent=self.root==ROOT.resolve(),rehearsal=self.root!=ROOT.resolve())
        # Cleanup failure must never roll back an already healthy publication.
        try:
            cleanup=accept_run_and_cleanup_backups(published['generation_id'],run_root=self.runs,
                backup_root=self.root/'backups/fundamentals_admin_production',journal_path=w.journal_path,
                live_paths=resolve_active_generation(self.root,require_generation=True).role_paths(),
                lock_factory=None if self.root==ROOT.resolve() else self._lock,
                scheduler_managed_locks=True,scheduler_log_dir=self.log_dir)
        except Exception as exc:
            cleanup={'status':'STOPPED','reason':str(exc)}
        return dict(selection=ids,publication=published,cleanup=cleanup)

    def run(self, *, enabled: bool, directory: Path, trigger_source='FULL_WORKFLOW', apply=True) -> dict:
        if not enabled:return summary(False,status='DISABLED')
        with self._lock():
            plan=self.preview(enabled=True);directory.mkdir(parents=True,exist_ok=False)
            journal._atomic_json(directory/'preview.json',plan)
            result=summary(True,status='NO_AUTO_CANDIDATES')
            result.update(evaluated=plan['evaluated'],manual_review=plan['manual_review'],deep_review=plan['deep_review'],
                          preview_path=str(directory/'preview.json'))
            if not plan['auto_continue']:
                return result
            try:
                self.test(plan,directory/'test')
                result.update(status='TEST_PASSED',test_receipt=str(directory/'test/test_receipt.json'))
                if apply:
                    live=self.production(plan,directory/'test/test_receipt.json',trigger_source=trigger_source)
                    result.update(status='COMPLETED',auto_continued=len(live['selection']),published=len(live['selection']),
                                  cleanup_status=live['cleanup'].get('cleanup_outcome',live['cleanup'].get('status')),**live)
            except Exception as exc:
                result.update(status='FAILED_OR_STALE',failed_stale=plan['auto_continue'],reason=str(exc))
            journal._atomic_json(directory/'result.json',result)
            return result
