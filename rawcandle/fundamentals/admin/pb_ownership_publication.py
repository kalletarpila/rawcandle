"""Selected ownership publication using the existing generation journal/locks/recovery.

Approval evidence is immutable input. Every publication rebases financial roles
from the current active generation; no P/B.12 financial candidate is published.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import json
import hashlib
from pathlib import Path
import shutil
import sqlite3
import uuid

from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin import publication_journal as journal_api
from rawcandle.fundamentals.admin.artifacts import ADMIN_RUN_ROOT, ROOT, sha256_file
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.contracts import fingerprint, utc_now
from rawcandle.fundamentals.admin.pb_ownership_review import (
    CASE_TABLE, REVIEW_TYPE, _audit, _ro, latest_basis, serialize, proposed_record,
)
from rawcandle.fundamentals.admin.production_transaction import production_lock, _no_sidecars
from rawcandle.fundamentals.admin.refresh_production import _verified_backups, _candidate_manifest
from rawcandle.fundamentals.admin.refresh_review_queue import _connect, queue_path_for_run_root
from rawcandle.fundamentals.book_value import book_value_report
from rawcandle.fundamentals.generations import (
    active_manifest_path, prepare_generation_from_candidates, resolve_active_generation,
)
from rawcandle.fundamentals.ownership_basis import BINDING
from rawcandle.fundamentals.pb_reporting_contract import ARTIFACT_TABLE, TABLE, generation_ownership_artifact

def exact_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


OPERATION = 'PUBLISH_PB_OWNERSHIP_REVIEWS'
BINDING_FIELDS = (*BINDING, 'fiscal_year', 'fiscal_quarter', 'reportperiod')
CODE_FILES = (
    'rawcandle/fundamentals/admin/pb_ownership_publication.py',
    'rawcandle/fundamentals/admin/pb_ownership_review.py',
    'rawcandle/fundamentals/admin/publication_journal.py',
    'rawcandle/fundamentals/admin/production_transaction.py',
    'rawcandle/fundamentals/admin/refresh_production.py',
    'rawcandle/fundamentals/admin/refresh_review_queue.py',
    'rawcandle/fundamentals/admin/ui_service.py',
    'rawcandle/fundamentals/generations.py',
    'rawcandle/fundamentals/book_value.py',
    'rawcandle/fundamentals/ownership_basis.py',
    'rawcandle/fundamentals/pb_reporting_contract.py',
    'dev_tools/fundamentals_admin_page.py',
    'rawcandle/fundamentals/ownership_reviews_v1.json',
    'rawcandle/fundamentals/ownership_reviews_v2.json',
)


class PublicationQueueSyncRequired(RuntimeError):
    """Activation/postflight succeeded; durable receipt permits queue-only retry."""


def merge_artifact(active: dict, records: list[dict]) -> dict:
    merged = deepcopy(active)
    supported = {tuple(r[k] for k in BINDING[:4]) for r in active['records']
                 if r['evidence_status'] == 'REVIEWED_SUPPORTED'}
    for record in sorted(records, key=lambda r: tuple(str(r[k]) for k in BINDING_FIELDS)):
        if tuple(record[k] for k in BINDING[:4]) not in supported:
            raise ValueError('PB_PUBLICATION_UNSUPPORTED_SCOPE')
        matches = [r for r in merged['records'] if all(r[k] == record[k] for k in BINDING_FIELDS)]
        if matches:
            raise ValueError('PB_PUBLICATION_DUPLICATE_OR_CONFLICTING_BINDING')
        merged['records'].append(deepcopy(record))
    return merged


def _canonical_content(path: Path) -> dict:
    """Bind every original schema/table, including publication authority, in bounded memory."""
    with _ro(path) as c:
        excluded = (TABLE, ARTIFACT_TABLE)
        schema = [list(r) for r in c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')
                  if r['tbl_name'] not in excluded]
        tables = {}
        import hashlib
        for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            name = row['name']
            if name in excluded:
                continue
            quoted = '"'+name.replace('"','""')+'"'
            columns = c.execute(f'PRAGMA table_info({quoted})').fetchall()
            order = ','.join('"'+r['name'].replace('"','""')+'"' for r in columns)
            digest = hashlib.sha256()
            for values in c.execute(f'SELECT * FROM {quoted} ORDER BY {order}'):
                # SQLite values can include blobs. Length-prefixed repr preserves their type.
                data = repr(tuple(values)).encode()
                digest.update(len(data).to_bytes(8,'big'));digest.update(data)
            tables[name] = digest.hexdigest()
    return {'schema': fingerprint(schema), 'tables': tables}


def _record_matches(case: dict, record: dict) -> bool:
    new = case['new']
    return (all(record.get(k) == new.get(k) for k in BINDING_FIELDS)
        and all(record.get(a) == new.get(b) for a,b in (
            ('accepted_sharesbas','sharesbas'),('provider_declared_factor','sharefactor'),
            ('accepted_category','category'),('accepted_provider_date','provider_date'),
            ('accepted_source_availability_date','source_availability_date'),
            ('parent_equity','parent_equity'),('parent_equity_usd','parent_equity_usd')))
        and record.get('approval_mode') == 'OPERATOR_CONFIRMED'
        and record.get('evidence_status') == 'REVIEWED_SUPPORTED'
        and record.get('prior_review_hash') == case['prior_review_hash'])


def _selected(queue: sqlite3.Connection, canonical: Path, case_ids: list[str], *, as_of: str) -> list[dict]:
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError('PB_PUBLICATION_EXPLICIT_UNIQUE_SELECTION_REQUIRED')
    with _ro(canonical) as c:
        artifact, _ = generation_ownership_artifact(c)
        selected = []
        for case_id in sorted(case_ids):
            row = queue.execute(f'SELECT * FROM {CASE_TABLE} WHERE case_id=?',(case_id,)).fetchone()
            if row is None or row['status'] != 'APPROVED':
                raise ValueError('PB_PUBLICATION_APPROVED_CASE_REQUIRED:'+case_id)
            case = json.loads(row['candidate_json']);approval = json.loads(row['approval_json'])
            result = json.loads(row['result_json']);record = approval['record']
            if (case['review_type'] != REVIEW_TYPE or case['case_id'] != case_id
                or case['candidate_hash'] != row['candidate_hash']
                or approval['candidate_hash'] != case['candidate_hash']
                or not _record_matches(case,record)
                or case['classification'] != 'CONTINUATION_CANDIDATE'):
                raise ValueError('PB_PUBLICATION_APPROVAL_BINDING_INVALID')
            unhashed = {k:v for k,v in case.items() if k != 'candidate_hash'}
            if fingerprint(unhashed) != case['candidate_hash']:
                raise ValueError('PB_PUBLICATION_CANDIDATE_HASH_INVALID')
            expected_record=proposed_record(case,approved_at=approval['approved_at'],operator=approval['operator'],note=approval['note'])
            if record!=expected_record:
                raise ValueError('PB_PUBLICATION_REVIEW_RECORD_CHANGED')
            if latest_basis(c,case['company_id'],as_of=as_of) != case['new']:
                raise ValueError('PB_PUBLICATION_STALE_ACCEPTED_BASIS:'+case_id)
            prior = [r for r in artifact['records'] if fingerprint(r) == case['prior_review_hash']]
            if len(prior) != 1 or any(all(r[k]==record[k] for k in BINDING_FIELDS) for r in artifact['records']):
                raise ValueError('PB_PUBLICATION_ACTIVE_HISTORY_CONFLICT')
            # Verify the original approval artifact/candidate as evidence, never as publication roles.
            export = Path(result['registry_artifact']);candidate = Path(result['candidate_canonical'])
            if export.is_symlink() or candidate.is_symlink() or sha256_file(export) != result['registry_sha256']:
                raise ValueError('PB_PUBLICATION_APPROVAL_ARTIFACT_CHANGED')
            approved_artifact = json.loads(export.read_text())
            with _ro(candidate) as old:
                embedded, sha = generation_ownership_artifact(old)
            if (sha != result['registry_sha256'] or embedded != approved_artifact
                or record not in embedded['records'] or result['previous_registry_sha256'] != case['registry_sha256']):
                raise ValueError('PB_PUBLICATION_APPROVAL_ARTIFACT_BINDING_INVALID')
            selected.append({'case':case,'approval':approval,'record':record,
                             'approval_hash':fingerprint(approval),'candidate_hash':case['candidate_hash']})
    return selected


def _finish_queue(queue: sqlite3.Connection, receipt: dict) -> None:
    scope = receipt['scope_evidence']
    for item in scope['selected']:
        case_id=item['case_id']
        row=queue.execute(f'SELECT * FROM {CASE_TABLE} WHERE case_id=?',(case_id,)).fetchone()
        if row is None:
            raise ValueError('PB_PUBLICATION_QUEUE_CASE_MISSING')
        result=json.loads(row['result_json'])
        metadata = dict(generation_id=receipt['new_generation_id'],artifact_sha256=scope['artifact_sha256'],
            published_at=scope['published_at'],candidate_hash=item['candidate_hash'],approval_hash=item['approval_hash'],
            operator=scope['operator'],publication_run_id=receipt['production_run_id'])
        if row['status']=='PUBLISHED' and result.get('publication')==metadata:
            continue
        if (row['status']!='APPROVED' or row['candidate_hash']!=item['candidate_hash']
            or fingerprint(json.loads(row['approval_json']))!=item['approval_hash']):
            raise ValueError('PB_PUBLICATION_QUEUE_APPROVAL_CHANGED')
        result['publication']=metadata
        queue.execute(f"UPDATE {CASE_TABLE} SET status='PUBLISHED',result_json=? WHERE case_id=?",(json.dumps(result,sort_keys=True),case_id))
        _audit(queue,json.loads(row['candidate_json']),'PUBLISHED',receipt['production_run_id'],metadata)


def synchronize(queue_path: Path, canonical: Path, *, journal_path: Path = journal_api.ACTIVE_JOURNAL_PATH) -> int:
    """Only a completed, postflight-passed durable receipt can consume exact cases."""
    receipt=journal_api.load_journal(journal_path)
    if (not receipt or receipt.get('operation_type')!=OPERATION or receipt.get('state')!='COMPLETED'
        or receipt.get('postflight_state')!='PASSED' or not queue_path.exists()):
        return 0
    root=Path(receipt['active_generation_manifest_path']).parent.parent
    active=resolve_active_generation(root,require_generation=True)
    if active.generation_id!=receipt['new_generation_id'] or canonical.resolve()!=active.role_paths()['canonical'].resolve():
        return 0
    for role,path in active.role_paths().items():
        if sha256_file(path)!=receipt['roles'][role]['candidate_fingerprint']:
            raise ValueError('PB_PUBLICATION_RECEIPT_ROLE_MISMATCH')
    with _ro(canonical) as c:
        artifact,sha=generation_ownership_artifact(c)
    if sha!=receipt['scope_evidence']['artifact_sha256']:
        raise ValueError('PB_PUBLICATION_RECEIPT_ARTIFACT_MISMATCH')
    with _connect(queue_path) as q:
        q.execute('BEGIN IMMEDIATE')
        for item in receipt['scope_evidence']['selected']:
            if not any(fingerprint(r)==item['record_hash'] for r in artifact['records']):
                raise ValueError('PB_PUBLICATION_RECEIPT_RECORD_MISSING')
        _finish_queue(q,receipt)
    return len(receipt['scope_evidence']['selected'])


class OwnershipPublicationWorkflow:
    def __init__(self, *, project_root: Path=ROOT, run_root: Path=ADMIN_RUN_ROOT, as_of: str|None=None):
        self.root=project_root.resolve();self.run_root=run_root.resolve();self.as_of=as_of
        if self.root==ROOT.resolve() and self.run_root!=ADMIN_RUN_ROOT.resolve():
            raise PermissionError('PB_PUBLICATION_PRODUCTION_GUARD_OVERRIDE_REJECTED')
        self.queue_path=queue_path_for_run_root(self.run_root)
        self.journal_path=self.root/'data/.fundamentals_admin_publication_journal.json'
        self.lanes=self.run_root/'pb_ownership_publications'

    @contextmanager
    def _locked(self):
        with production_lock(lock_path=self.root/'temp/.fundamentals_admin_production.lock',
                scheduler_log_dir=None if self.root==ROOT.resolve() else str(self.root/'scheduler_logs')):
            with taxonomy_operation_lock_context(deployment_id=OPERATION,operation_type=OPERATION,
                    evidence_root=None if self.root==ROOT.resolve() else ROOT/'temp/pb_ownership_rehearsal_locks'/fingerprint(str(self.root))[:24]):
                yield

    def _sources(self) -> tuple[object,dict]:
        active=resolve_active_generation(self.root,require_generation=True)
        roles=active.role_paths()
        if self.root!=ROOT.resolve():
            real=set(resolve_active_generation(ROOT).role_paths().values())
            if any(p.resolve() in real for p in roles.values()):
                raise PermissionError('PB_PUBLICATION_REHEARSAL_MUST_USE_COPIES')
        for p in roles.values():_no_sidecars(p)
        inputs={}
        for name in ('osakedata.db','analysis.db'):
            path=self.root/'data'/name
            inputs[name]={suffix:sha256_file(Path(str(path)+suffix)) if Path(str(path)+suffix).exists() else None
                          for suffix in ('','-wal')}
        role_hashes={r:sha256_file(p) for r,p in roles.items()}
        if any(role_hashes[r]!=(active.manifest.get('role_verification',{}).get(r) or {}).get('sha256') for r in roles):
            raise ValueError('PB_PUBLICATION_ACTIVE_MANIFEST_ROLE_MISMATCH')
        config=self.root/'scheduler_config.json'
        return active,dict(generation_id=active.generation_id,manifest_sha256=sha256_file(active_manifest_path(self.root)),
            role_hashes=role_hashes,inputs=inputs,
            scheduler_sha256=sha256_file(config) if config.exists() else None,
            code={p:sha256_file(ROOT/p) for p in CODE_FILES})

    def _recover_and_sync(self):
        journal_api.guard_production_writes(self.journal_path)
        active=resolve_active_generation(self.root,require_generation=True)
        synchronize(self.queue_path,active.role_paths()['canonical'],journal_path=self.journal_path)

    def inspect(self, case_id: str) -> dict:
        try:
            active=resolve_active_generation(self.root,require_generation=True)
            with _ro(self.queue_path) as q:
                selected=_selected(q,active.role_paths()['canonical'],[case_id],as_of=self.as_of or utc_now()[:10])
            return {'status':'READY','source_generation':active.generation_id,
                    'source_canonical_sha256':sha256_file(active.role_paths()['canonical']),
                    'approval_hash':selected[0]['approval_hash']}
        except (OSError,sqlite3.DatabaseError,ValueError,KeyError) as exc:
            return {'status':'STALE_OR_UNAVAILABLE','reason':str(exc)}

    def preview(self, case_ids: list[str]) -> dict:
        as_of=self.as_of or utc_now()[:10];date.fromisoformat(as_of)
        with self._locked():
            self._recover_and_sync()
            active,source=self._sources()
            with _ro(self.queue_path) as q:
                selected=_selected(q,active.role_paths()['canonical'],case_ids,as_of=as_of)
            key=fingerprint({'source':source,'selected':selected,'as_of':as_of})
            self.lanes.mkdir(parents=True,exist_ok=True)
            cache=self.lanes/(key+'.json')
            if cache.exists():
                saved=json.loads(cache.read_text())
                if (saved.get('source')==source and saved.get('selected')==selected and saved.get('as_of')==as_of
                    and saved.get('preview_hash')==exact_hash({k:v for k,v in saved.items() if k!='preview_hash'})
                    and all(Path(p).is_file() and not Path(p).is_symlink() and sha256_file(Path(p))==saved['candidate_hashes'][r] for r,p in saved['candidates'].items())
                    and Path(saved['market']).is_file() and sha256_file(Path(saved['market']))==saved['market_sha256']):
                    return saved
            run_id='pb_ownership_'+uuid.uuid4().hex
            lane=self.lanes/run_id;lane.mkdir()
            try:
                required=3*sum(p.stat().st_size for p in active.role_paths().values())+(self.root/'data/osakedata.db').stat().st_size
                if shutil.disk_usage(lane).free<required:raise RuntimeError('PB_PUBLICATION_INSUFFICIENT_DISK')
                candidates={r:lane/(r+'.db') for r in active.role_paths()}
                for role,path in active.role_paths().items():shutil.copyfile(path,candidates[role])
                from rawcandle.fundamentals.phase13b_foundation import online_backup
                market=lane/'market.db';online_backup(self.root/'data/osakedata.db',market)
                with _ro(active.role_paths()['canonical']) as c:artifact,old_sha=generation_ownership_artifact(c)
                merged=merge_artifact(artifact,[s['record'] for s in selected]);payload=serialize(merged)
                import hashlib
                new_sha=hashlib.sha256(payload.encode()).hexdigest()
                with sqlite3.connect(candidates['canonical']) as c:
                    c.execute(f'CREATE TABLE IF NOT EXISTS {ARTIFACT_TABLE}(singleton INTEGER PRIMARY KEY CHECK(singleton=1),artifact_json TEXT NOT NULL)')
                    c.execute(f'INSERT OR REPLACE INTO {ARTIFACT_TABLE} VALUES(1,?)',(payload,))
                    c.execute(f'UPDATE {TABLE} SET review_artifact_sha256=? WHERE singleton=1',(new_sha,))
                checks={r:journal_api.sqlite_verification(p) for r,p in candidates.items()}
                hashes={r:v['sha256'] for r,v in checks.items()}
                financial=_canonical_content(active.role_paths()['canonical'])
                if _canonical_content(candidates['canonical'])!=financial:raise RuntimeError('PB_PUBLICATION_FINANCIAL_INVARIANCE_FAILED')
                if any(hashes[r]!=source['role_hashes'][r] for r in ('provider','analysis')):raise RuntimeError('PB_PUBLICATION_SCORE_PROVIDER_INVARIANCE_FAILED')
                comparisons=self._compare(selected,active.role_paths()['canonical'],candidates['canonical'],market,as_of)
                if self._sources()[1]!=source:raise ValueError('PB_PUBLICATION_SOURCE_DRIFT')
                result=dict(operation_type=OPERATION,preview_id=run_id,selection=sorted(case_ids),as_of=as_of,source=source,
                    selected=selected,candidate_generation_id=run_id,candidates={r:str(p) for r,p in candidates.items()},
                    candidate_hashes=hashes,market=str(market),market_sha256=sha256_file(market),
                    active_artifact_sha256=old_sha,artifact_sha256=new_sha,artifact=merged,financial=financial,
                    comparisons=comparisons,score_invariance='PASSED',source_revalidation='PASSED',queue_transition='APPROVED → PUBLISHED')
                result['preview_hash']=exact_hash(result)
                journal_api._atomic_json(lane/'preview.json',result);journal_api._atomic_json(cache,result)
                return result
            except BaseException:
                shutil.rmtree(lane,ignore_errors=True)
                raise

    @staticmethod
    def _compare(selected, before, after, market, as_of):
        comparisons=[]
        with _ro(before) as old,_ro(after) as new,_ro(market) as m:
            for s in selected:
                case=s['case'];args=dict(company_id=case['company_id'],ticker=case['ticker'],as_of=as_of)
                a=book_value_report(old,m,**args);b=book_value_report(new,m,**args)
                if (a['provider'],a['history'])!=(b['provider'],b['history']):raise RuntimeError('PB_PUBLICATION_PROVIDER_HISTORY_CHANGED')
                if a['current']['value'] is not None:raise ValueError('PB_PUBLICATION_ALREADY_AVAILABLE')
                basis=b['current'].get('ownership_basis')
                # Independent price/equity gates can run before ownership evaluation.
                if basis and basis.get('review_content_hash')!=exact_hash(s['record']):raise RuntimeError('PB_PUBLICATION_CURRENT_REVIEW_MISMATCH')
                if b['current']['reason'] in ('OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED','OWNERSHIP_REVIEW_UNVERIFIED'):
                    raise RuntimeError('PB_PUBLICATION_OWNERSHIP_NOT_ACTIVATED')
                if b['current']['value'] is not None:
                    ratio=s['record']['exact_factor_numerator']/s['record']['exact_factor_denominator'] if s['record']['economic_unit_rule']=='ADS_EQUIVALENTS' else 1
                    expected=b['current']['price']*case['new']['sharesbas']*ratio/case['new']['parent_equity_usd']
                    if abs(b['current']['value']-expected)>max(1e-12,abs(expected)*1e-12):raise RuntimeError('PB_PUBLICATION_CURRENT_FORMULA_MISMATCH')
                comparisons.append(dict(case_id=case['case_id'],ticker=case['ticker'],before=a['current'],candidate=b['current']))
        return comparisons

    def publish(self, preview_id: str, *, preview_hash: str, operator: str,
                confirmed: bool=False, production_intent: bool=False, rehearsal: bool=False,
                inject_failure_at: str|None=None) -> dict:
        if confirmed is not True or not operator.strip():raise PermissionError('PB_PUBLICATION_EXPLICIT_PRODUCTION_CONFIRMATION_REQUIRED')
        if (self.root==ROOT.resolve()) != (production_intent is True and rehearsal is False):
            raise PermissionError('PB_PUBLICATION_EXPLICIT_PRODUCTION_INTENT_REQUIRED')
        if self.root!=ROOT.resolve() and not rehearsal:raise PermissionError('PB_PUBLICATION_COPY_REHEARSAL_REQUIRED')
        if not preview_id.startswith('pb_ownership_') or not preview_id[13:].isalnum():raise ValueError('PB_PUBLICATION_PREVIEW_ID_INVALID')
        path=self.lanes/preview_id/'preview.json'
        saved=json.loads(path.read_text())
        if saved.get('preview_hash')!=preview_hash or exact_hash({k:v for k,v in saved.items() if k!='preview_hash'})!=preview_hash:
            raise ValueError('PB_PUBLICATION_PREVIEW_BINDING_INVALID')
        with self._locked():
            self._recover_and_sync()
            # A retried successful invocation returns its original durable receipt.
            receipt=journal_api.load_journal(self.journal_path)
            if receipt and receipt.get('production_run_id')==preview_id and receipt.get('state')=='COMPLETED':
                return {'outcome':'ALREADY_PUBLISHED','generation_id':receipt['new_generation_id']}
            active,source=self._sources()
            with _ro(self.queue_path) as retry_queue, _ro(active.role_paths()['canonical']) as retry_canonical:
                rows=[retry_queue.execute(f'SELECT status,result_json FROM {CASE_TABLE} WHERE case_id=?',(cid,)).fetchone() for cid in saved['selection']]
                records=generation_ownership_artifact(retry_canonical)[0]['records']
                if (rows and all(r and r['status']=='PUBLISHED' and json.loads(r['result_json']).get('publication',{}).get('publication_run_id')==preview_id for r in rows)
                    and all(s['record'] in records for s in saved['selected'])):
                    return {'outcome':'ALREADY_PUBLISHED','generation_id':preview_id}
            if source!=saved['source'] or (self.as_of or utc_now()[:10])!=saved['as_of']:raise ValueError('PB_PUBLICATION_SOURCE_DRIFT_REBUILD_REQUIRED')
            journal=None;completed=False
            try:
                with _connect(self.queue_path) as queue:
                    queue.execute('BEGIN IMMEDIATE')
                    selected=_selected(queue,active.role_paths()['canonical'],saved['selection'],as_of=saved['as_of'])
                    if selected!=saved['selected']:raise ValueError('PB_PUBLICATION_APPROVAL_CHANGED')
                    candidates={r:Path(p) for r,p in saved['candidates'].items()}
                    def gate(paths):
                        if self._sources()[1]!=source:raise ValueError('PB_PUBLICATION_FINAL_SOURCE_DRIFT')
                        if _selected(queue,active.role_paths()['canonical'],saved['selection'],as_of=saved['as_of'])!=selected:raise ValueError('PB_PUBLICATION_FINAL_APPROVAL_DRIFT')
                        if any(sha256_file(p)!=saved['candidate_hashes'][r] for r,p in paths.items()):raise ValueError('PB_PUBLICATION_CANDIDATE_DRIFT')
                        if sha256_file(Path(saved['market']))!=saved['market_sha256']:raise ValueError('PB_PUBLICATION_MARKET_PREVIEW_DRIFT')
                    gate(candidates)
                    with _ro(active.role_paths()['canonical']) as c:
                        current_artifact,_=generation_ownership_artifact(c)
                    expected_artifact=merge_artifact(current_artifact,[s['record'] for s in selected])
                    with _ro(candidates['canonical']) as c:
                        candidate_artifact,candidate_sha=generation_ownership_artifact(c)
                    if (candidate_artifact!=expected_artifact or candidate_sha!=saved['artifact_sha256']
                        or expected_artifact!=saved['artifact']
                        or _canonical_content(active.role_paths()['canonical'])!=saved['financial']
                        or _canonical_content(candidates['canonical'])!=saved['financial']
                        or any(saved['candidate_hashes'][r]!=source['role_hashes'][r] for r in ('provider','analysis'))):
                        raise ValueError('PB_PUBLICATION_CANDIDATE_VALIDATION_CHANGED')
                    if self._compare(selected,active.role_paths()['canonical'],candidates['canonical'],Path(saved['market']),saved['as_of'])!=saved['comparisons']:
                        raise ValueError('PB_PUBLICATION_PREVIEW_EFFECT_CHANGED')
                    try:
                        paths=BatchAddTickerPaths(*(active.role_paths()[r] for r in ('provider','canonical','analysis')),self.root/'data/osakedata.db',self.root/'data/analysis.db')
                        backup_dir=self.root/'backups/fundamentals_admin_production'/preview_id
                        backups=_verified_backups(paths,backup_dir,immutable_generation=True)
                        roles=_candidate_manifest(candidates,backups)
                        scope=dict(selected=[dict(case_id=s['case']['case_id'],candidate_hash=s['candidate_hash'],approval_hash=s['approval_hash'],record_hash=fingerprint(s['record'])) for s in selected],
                            artifact_sha256=saved['artifact_sha256'],operator=operator.strip(),published_at=utc_now())
                        journal=journal_api.prepare_journal(path=self.journal_path,operation_type=OPERATION,run_id=preview_id,
                            preview_run_id=preview_id,test_run_id=preview_id,refresh_set_fingerprint=preview_hash,
                            old_source_watermark=None,new_source_watermark=saved['as_of'],source_schema_fingerprint=saved['financial']['schema'],
                            roles=roles,publication_mode='GENERATION_POINTER',old_generation=active.evidence()|{'manifest':dict(active.manifest)},
                            new_generation_id=preview_id,active_generation_manifest_path=active_manifest_path(self.root),scope_evidence=scope)
                        prepared=prepare_generation_from_candidates(candidates,generation_id=preview_id,project_root=self.root,source=OPERATION)
                        journal=journal_api.update_journal(self.journal_path,journal,current_publication_step='NEW_GENERATION_READY',generation_activation_state='READY',
                            new_generation_manifest=prepared['manifest'],new_generation_dir=prepared['generation_dir'])
                        ready={r:Path(p) for r,p in prepared['roles'].items()}
                        gate(ready)
                        if journal_api.load_journal(self.journal_path)!=journal:raise ValueError('PB_PUBLICATION_JOURNAL_DRIFT')
                        if inject_failure_at=='BEFORE_ACTIVATION':raise RuntimeError('INJECTED_BEFORE_ACTIVATION')
                        journal=journal_api.activate_prepared_generation(journal,new_manifest=prepared['manifest'],journal_path=self.journal_path)
                        journal=journal_api.update_journal(self.journal_path,journal,state='POSTFLIGHT',postflight_state='RUNNING')
                        if inject_failure_at=='POSTFLIGHT':raise RuntimeError('INJECTED_POSTFLIGHT')
                        live=resolve_active_generation(self.root,require_generation=True)
                        if live.generation_id!=preview_id:raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_GENERATION_MISMATCH')
                        if any(journal_api.sqlite_verification(p)['sha256']!=saved['candidate_hashes'][r] for r,p in live.role_paths().items()):raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_ROLE_MISMATCH')
                        if _canonical_content(live.role_paths()['canonical'])!=saved['financial']:raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_FINANCIAL_CHANGED')
                        with _ro(live.role_paths()['canonical']) as c:
                            artifact,sha=generation_ownership_artifact(c)
                        if artifact!=saved['artifact'] or sha!=saved['artifact_sha256']:raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_ARTIFACT_CHANGED')
                        post_source=self._sources()[1]
                        if any(post_source[k]!=source[k] for k in ('inputs','scheduler_sha256','code')):
                            raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_INPUT_DRIFT')
                        comparisons=self._compare(selected,active.role_paths()['canonical'],live.role_paths()['canonical'],Path(saved['market']),saved['as_of'])
                        if comparisons!=saved['comparisons']:raise RuntimeError('PB_PUBLICATION_POSTFLIGHT_REPORT_CHANGED')
                        scope['published_at']=utc_now()
                        journal=journal_api.update_journal(self.journal_path,journal,state='COMPLETED',postflight_state='PASSED',current_publication_step='COMPLETED',scope_evidence=scope)
                        completed=True
                        journal_api._atomic_json(path.parent/'completed_journal.json',journal)
                        if inject_failure_at=='QUEUE_FINALIZATION':raise RuntimeError('INJECTED_QUEUE_FINALIZATION')
                        _finish_queue(queue,journal)
                    except Exception as exc:
                        if completed:
                            raise PublicationQueueSyncRequired(f'Generation {preview_id} published and postflight PASSED; retry queue synchronization from the durable receipt: {exc}') from exc
                        if journal and not completed:
                            journal_api.restore_old_generation(journal,journal_path=self.journal_path)
                        raise
            except Exception as exc:
                if not completed:
                    # Invalidate failed attempt copies, even if backup/journal preparation failed early.
                    # The next preview rebuilds into a fresh lane; backups/receipts remain auditable.
                    for owned in saved['candidates'].values():
                        candidate=Path(owned)
                        if not candidate.is_symlink() and candidate.resolve().is_relative_to(path.parent.resolve()):
                            candidate.unlink(missing_ok=True)
                if completed and not isinstance(exc,PublicationQueueSyncRequired):
                    raise PublicationQueueSyncRequired(f'Generation {preview_id} published and postflight PASSED; retry queue synchronization from the durable receipt: {exc}') from exc
                raise
            return {'outcome':'COMPLETED','generation_id':preview_id,'artifact_sha256':saved['artifact_sha256'],
                    'published_cases':saved['selection'],'postflight':'PASSED','publication_run_id':preview_id}
