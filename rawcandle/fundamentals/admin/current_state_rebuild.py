"""Explicit, receipt-bound current source-version advancement, never exact repair.

Preview is read-only. Test changes disposable copies. Publication requires an exact
Test, fresh authoritative acquisition and the native immutable-generation locks,
journal, postflight and rollback. Ordinary Refresh never calls this operation.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import fcntl
import json
import shutil
import sqlite3

from . import provider_payload as payload, provider_payload_workflow as strict
from . import publication_journal as journal, refresh_fundamentals as source
from .contracts import utc_now
from .provider_payload_review_scope import prove
from rawcandle.fundamentals.generations import resolve_active_generation, active_manifest_path
from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy

VERSION = 'FUNDAMENTALS_CONTROLLED_CURRENT_STATE_REBUILD_V1'
OPERATION = 'CONTROLLED_CURRENT_STATE_REBUILD'
PREVIEW = VERSION + '_PREVIEW'
TEST = VERSION + '_TEST'
TABLE = 'fundamentals_current_state_rebuild'
digest = payload.payload_fingerprint
CODE = tuple(Path(__file__).with_name(n) for n in (
    'current_state_rebuild.py', 'current_state_rebuild_acceptance.py',
    'refresh_copy_runtime.py', 'legacy_payload_disposition.py', 'full_v2_downstream.py',
)) + (Path(__file__).parents[1] / 'phase12d.py',)


def require(condition, reason):
    if not condition:
        raise ValueError('CURRENT_REBUILD_' + reason)


def seal(value, field):
    return {**value, field: digest(value)}


def verify(value, schema, field):
    require(isinstance(value, dict) and value.get('schema') == schema and
        value.get(field) == digest({k:v for k,v in value.items() if k != field}), 'EVIDENCE_INVALID')


def acquire(ticker, *, client=None):
    """Only the native unprojected Sharadar endpoints establish acquisition evidence."""
    from rawcandle.fundamentals.providers.sharadar import SharadarClient, extract_schema_fields
    client = client or SharadarClient()
    schema = client.schema('fundamentals')
    require(schema.ok, 'SCHEMA_ACQUISITION_FAILED')
    fields = sorted(extract_schema_fields(schema.payload))
    require(set(source.REFRESH_REQUEST_FIELDS).issubset(fields) and
        {'equity','equityusd','sharefactor'}.issubset(fields), 'FULL_SCHEMA_REQUIRED')
    histories = {}
    for dimension in ('ARQ','MRQ'):
        result = client.fundamentals(ticker=ticker, dimension=dimension, limit=source.DISCOVERY_LIMIT)
        require(result.ok, 'AUTHORITATIVE_ACQUISITION_FAILED')
        histories[dimension] = result.records
    value = dict(schema=VERSION + '_ACQUISITION', provider='SHARADAR', table='fundamentals',
        endpoint=source.SOURCE_ENDPOINT, ticker=ticker, acquired_at=utc_now(), fields=fields, histories=histories)
    return seal(value, 'acquisition_fingerprint')


def trusted(acquisition, ticker, *, dimensions=('ARQ','MRQ'), full_capture=True):
    verify(acquisition, VERSION + '_ACQUISITION', 'acquisition_fingerprint')
    require(acquisition['provider']=='SHARADAR' and acquisition['table']=='fundamentals' and
        acquisition['endpoint']==source.SOURCE_ENDPOINT and acquisition['ticker']==ticker, 'UNSUPPORTED_SOURCE')
    fetched = datetime.fromisoformat(acquisition['acquired_at'].replace('Z','+00:00'))
    require(fetched.tzinfo is not None and -60 <= (datetime.now(timezone.utc)-fetched).total_seconds() <= 86400,
            'STALE_ACQUISITION')
    fields = set(acquisition['fields'])
    require(set(source.REFRESH_REQUEST_FIELDS).issubset(fields) and
        {'equity','equityusd','sharefactor'}.issubset(fields), 'FULL_SCHEMA_REQUIRED')
    result = {}
    for dimension in dimensions:
        raw = acquisition['histories'][dimension]
        trust = source.validate_complete_history(raw,ticker=ticker,dimension=dimension,
            response_reached_limit=len(raw)>=source.DISCOVERY_LIMIT)
        require(trust.status=='COMPLETE', 'AMBIGUOUS_OR_INCOMPLETE_HISTORY')
        if full_capture:
            require(all(fields.issubset(row['_acquisition_payload']) for row in trust.rows), 'INCOMPLETE_PAYLOAD')
        result[dimension] = trust
    return result


def baseline(root, queue):
    root = Path(root)
    from .production_transaction import _no_sidecars
    jpath = root/'data/.fundamentals_admin_publication_journal.json'
    journal.guard_production_writes(jpath)
    taxonomy = root/'data/analysis.db'
    _no_sidecars(taxonomy)
    base = strict.baseline(root)
    base.update(taxonomy=str(taxonomy),taxonomy_sha256=journal.sha256_file(taxonomy),
        journal_sha256=journal.sha256_file(jpath) if jpath.exists() else None,
        queue_content=strict._content(Path(queue)),
        rebuild_code={str(p):journal.sha256_file(p) for p in CODE})
    return base


def assess(root, key, acquisition, *, source_baseline):
    """General administration ordering: strict repair, explicit rebuild, unresolved.

    Rejection raises a structured reason; callers retain UNRESOLVED. No failed
    repair is automatically converted to a rebuild or an exclusion.
    """
    # Exact repair keeps its native ARQ prerequisites; rebuild-only full-capture
    # and MRQ requirements cannot obstruct a successful exact repair.
    histories = trusted(acquisition,key[0],dimensions=('ARQ',),full_capture=False)
    try:
        exact = strict.proposal(Path(root),key,histories['ARQ'],
            fetched_at_utc=acquisition['acquired_at'],source_baseline=source_baseline)
    except ValueError as error:
        require(str(error)=='PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR','STRICT_REJECTION_NOT_VERSION_ADVANCEMENT')
    else:
        return dict(path='EXACT_REPAIR',proposal=exact)
    histories = trusted(acquisition,key[0])
    require(key[1]=='ARQ', 'CURRENT_ARQ_REQUIRED')
    current = source.load_current_history(Path(source_baseline['roles']['provider']),key[0],'ARQ')
    require(not current['invalid_rows'] and not current['legacy_source_version_ambiguities'], 'AMBIGUOUS_STORED_SOURCE')
    old = [r for r in current['rows'] if source.source_key(r)==tuple(key)]
    new = [r for r in histories['ARQ'].rows if source.source_key(r)==tuple(key)]
    require(len(old)==len(new)==1, 'EXACT_UNIQUE_CURRENT_KEY_REQUIRED')
    old,new = old[0],new[0]
    comparison = payload.compare_payload(old,new)
    require(comparison and comparison['reason']=='SOURCE_PAYLOAD_VALUE_REVISION' and
        comparison.get('financial_fields_changed') is False and not comparison.get('fields_changed') and
        not comparison.get('fields_removed') and comparison.get('fields_restored'), 'VERSION_ONLY_REQUIRED')
    changed = {k for k in source.REFRESH_REQUEST_FIELDS if old[k]!=new[k]}
    require(changed=={'lastupdated'} and new['lastupdated']>old['lastupdated'] and
        source._effective_row(old)==source._effective_row(new), 'FINANCIAL_OR_IDENTITY_REVISION')
    from rawcandle.fundamentals.publication_dates import select_valid_publication_winner
    peers=[r for r in histories['ARQ'].rows if r['fiscalperiod']==new['fiscalperiod']]
    require(len(peers)==1, 'AMBIGUOUS_CURRENT_FISCAL_SOURCE')
    winner=select_valid_publication_winner(peers)
    require(source.source_key(winner)==tuple(key), 'FRESH_CURRENT_SOURCE_REPLACEMENT')
    require(max(source.fiscal_identity(r['fiscalperiod']) for r in histories['ARQ'].rows)==
        source.fiscal_identity(new['fiscalperiod']), 'FRESH_LATEST_FISCAL_CHANGED')
    identity = source.resolve_identity(SimpleNamespace(provider_db=Path(source_baseline['roles']['provider']),
        canonical_db=Path(source_baseline['roles']['canonical'])),key[0])
    require(identity.get('status')=='KNOWN' and identity.get('company_key') and all(
        identity.get(k) and identity[k]==old['_provider_identity'].get(k)
        for k in ('company_id','security_id','provider_security_id')), 'IDENTITY_MISMATCH')
    for dimension in histories.values():
        for row in dimension.rows:
            raw = row['_acquisition_payload']
            for name, expected in (('permaticker',identity['provider_security_id']),
                ('provider_security_id',identity['provider_security_id']),('company_id',identity['company_id']),
                ('security_id',identity['security_id'])):
                require(name not in raw or str(raw[name])==str(expected), 'PROVIDER_IDENTITY_MISMATCH')
    oid = comparison['old_observation_id']
    with strict._ro(Path(source_baseline['roles']['provider'])) as p:
        header = p.execute('SELECT * FROM provider_observation WHERE observation_id=?',(oid,)).fetchone()
        require(header is not None and header['provider_status']=='SUCCESS' and
            header['provider']=='SHARADAR' and header['native_table']=='fundamentals' and
            not json.loads(header['provenance_json'] or '{}'), 'REVIEWED_OR_RETAINED_SOURCE')
        require(p.execute('SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?',key).fetchone()[0]==1,
            'DUPLICATE_CURRENT_KEY')
        from . import accounting_boundary_review as boundary
        native = dict(p.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?',(oid,)).fetchone())
        require(not boundary.interpretation(p,native)['resolution_id'] and not boundary.current_context(Path(source_baseline['roles']['provider']),native), 'BOUNDARY_SOURCE_UNSUPPORTED')
    with strict._ro(Path(source_baseline['roles']['canonical'])) as c:
        q = c.execute('''SELECT q.* FROM v4_quarter q JOIN v4_field_provenance p USING(quarter_id)
            WHERE p.canonical_field='shares_outstanding' AND p.provider_observation_id=?''',(oid,)).fetchall()
        require(len(q)==1, 'EXACT_ACCEPTED_BINDING_REQUIRED')
        q = dict(q[0])
        from . import historical_freeze as freeze
        require(q['identity_status']=='ACCEPTED' and q['company_id']==identity['company_id'] and
            q['period_end']>freeze.CUTOFF and q['source_reportperiod']==new['reportperiod'] and
            f"{q['fiscal_year']}-{q['fiscal_quarter']}"==new['fiscalperiod'], 'CURRENT_NONFROZEN_FISCAL_BINDING_REQUIRED')
        latest = c.execute("SELECT quarter_id FROM v4_quarter WHERE company_id=? AND identity_status='ACCEPTED' ORDER BY fiscal_year DESC,fiscal_quarter DESC LIMIT 1",(identity['company_id'],)).fetchone()[0]
        require(latest==q['quarter_id'], 'LATEST_ACCEPTED_REQUIRED')
        from rawcandle.fundamentals.phase12d import SHARADAR_ARQ_FIELD_MAPPING
        financial = dict(c.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?',(q['quarter_id'],)).fetchone())
        require(all(financial[k]==(float(new[v]) if new[v] is not None else None)
            for k,v in SHARADAR_ARQ_FIELD_MAPPING.items()), 'ACCEPTED_FINANCIAL_CONTRADICTION')
    value = dict(ticker=key[0],source_key=list(key),identity=identity,comparison=comparison,
        quarter=q,financial_fingerprint=digest(source._effective_row(new)),
        old_lastupdated=old['lastupdated'],new_lastupdated=new['lastupdated'],
        acquisition=acquisition,strict_rejection='PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR')
    return dict(path='CURRENT_STATE_REBUILD',proposal=seal(value,'proposal_fingerprint'))


def preview(root, queue, selections, *, source_baseline=None):
    """Selections are explicit (exact source key, native acquisition) pairs."""
    base = source_baseline or baseline(root,queue)
    proposals = []
    for key,acquisition in selections:
        result = assess(root,tuple(key),acquisition,source_baseline=base)
        require(result['path']=='CURRENT_STATE_REBUILD', 'EXACT_REPAIR_MUST_BE_USED')
        proposals.append(result['proposal'])
    proposals.sort(key=lambda p:p['ticker'])
    require(proposals and len({p['identity']['company_id'] for p in proposals})==len(proposals), 'UNIQUE_SELECTION_REQUIRED')
    review = prove(proposals,queue,base['roles']['canonical'],base['roles']['provider'])
    return seal(dict(schema=PREVIEW,policy=VERSION,baseline=base,proposals=proposals,source_review_guard=review), 'preview_fingerprint')


def revalidate(root, queue, plan, *, acquisitions=None):
    verify(plan,PREVIEW,'preview_fingerprint')
    base = baseline(root,queue)
    require(base==plan['baseline'], 'STALE_BASELINE')
    selections=[]
    for p in plan['proposals']:
        a = acquisitions[p['ticker']] if acquisitions is not None else p['acquisition']
        # A fresh fetch may have a different timestamp; source content/schema must
        # match exactly, then use the original timestamp for receipt identity.
        trusted(a,p['ticker'])
        old=p['acquisition']
        require({k:v for k,v in a.items() if k not in ('acquired_at','acquisition_fingerprint')}==
            {k:v for k,v in old.items() if k not in ('acquired_at','acquisition_fingerprint')}, 'STALE_SOURCE')
        selections.append((p['source_key'],old))
    require(preview(root,queue,selections,source_baseline=base)==plan, 'STALE_ELIGIBILITY')


def generation_id(plan):
    return 'current_rebuild_' + plan['preview_fingerprint'][:32]


def provenance(plan,p):
    from .refresh_copy_runtime import _observation_id
    return dict(policy=VERSION,previous_generation=plan['baseline']['generation_id'],
        previous_observation_id=p['comparison']['old_observation_id'],
        previous_content_hash=p['comparison']['old_content_hash'],source_key=p['source_key'],
        acquisition_fingerprint=p['acquisition']['acquisition_fingerprint'],
        source_fetch_timestamp=p['acquisition']['acquired_at'],
        new_observation_id=_observation_id('|'.join(p['source_key']),p['comparison']['new']['payload_fingerprint']),
        new_content_hash=p['comparison']['new']['payload_fingerprint'],
        normalized_financial_fingerprint=p['financial_fingerprint'],
        old_lastupdated=p['old_lastupdated'],new_lastupdated=p['new_lastupdated'],
        preview_fingerprint=plan['preview_fingerprint'],publication_generation=generation_id(plan))


def _scoped_content(path, ids=(), quarters=(), run_id=None):
    with strict._ro(Path(path)) as c:
        result={}
        for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if table=='sqlite_sequence':continue
            columns={r['name'] for r in c.execute('PRAGMA table_info("'+table.replace('"','""')+'")')}
            where,args='',()
            if table in ('provider_observation','sharadar_fundamental_observation') and ids:
                where,args='WHERE observation_id NOT IN ('+','.join('?' for _ in ids)+')',tuple(ids)
            elif table=='provider_run' and run_id:
                where,args='WHERE run_id<>?',(run_id,)
            elif table in ('v4_quarter','v4_quarter_financials','v4_field_provenance',
                    'v4_common_earnings_provenance','v4_operating_working_capital_provenance',
                    'v4_parent_equity_source','v4_parent_equity_provenance') and quarters:
                where,args='WHERE quarter_id NOT IN ('+','.join('?' for _ in quarters)+')',tuple(quarters)
            result[table]=strict._table_digest(c,table,where,args)
        return result


def measure(plan,candidates):
    """Independently check installed current versions and every unselected row."""
    verify(plan,PREVIEW,'preview_fingerprint')
    base=plan['baseline'];proofs=[provenance(plan,p) for p in plan['proposals']]
    ids=[v[k] for v in proofs for k in ('previous_observation_id','new_observation_id')]
    qids=[p['quarter']['quarter_id'] for p in plan['proposals']]
    run=generation_id(plan)
    require(_scoped_content(base['roles']['provider'],ids,run_id=run)==
        _scoped_content(candidates['provider'],ids,run_id=run), 'UNRELATED_PROVIDER_CHANGED')
    require(_scoped_content(base['roles']['canonical'],quarters=qids)==
        _scoped_content(candidates['canonical'],quarters=qids), 'UNRELATED_CANONICAL_CHANGED')
    outcomes={}
    with strict._ro(Path(base['roles']['provider'])) as op, strict._ro(Path(candidates['provider'])) as np, \
         strict._ro(Path(base['roles']['canonical'])) as oc, strict._ro(Path(candidates['canonical'])) as nc:
        from rawcandle.fundamentals.pb_reporting_contract import generation_ownership_artifact
        require(generation_ownership_artifact(oc)==generation_ownership_artifact(nc),'OWNERSHIP_CHANGED')
        for p,proof in zip(plan['proposals'],proofs,strict=True):
            old=dict(op.execute('SELECT * FROM provider_observation WHERE observation_id=?',(proof['previous_observation_id'],)).fetchone())
            new=dict(np.execute('SELECT * FROM provider_observation WHERE observation_id=?',(proof['new_observation_id'],)).fetchone())
            require(old['content_hash']==proof['previous_content_hash'] and
                payload.completeness(json.loads(new['payload_json']))==p['comparison']['new'] and
                new['content_hash']==proof['new_content_hash'] and
                json.loads(new['provenance_json'])=={'current_state_rebuild':proof},'SOURCE_PROVENANCE_MISMATCH')
            mutable={'observation_id','run_id','provider_record_key','content_hash','payload_json','provenance_json','fetched_at_utc','observed_at_utc'}
            require({k:v for k,v in old.items() if k not in mutable}=={k:v for k,v in new.items() if k not in mutable}
                and new['observed_at_utc']==p['new_lastupdated'] and new['fetched_at_utc']==p['acquisition']['acquired_at']
                and new['run_id']==run and new['provider_record_key']=='|'.join(p['source_key']),'SOURCE_HEADER_MISMATCH')
            require(np.execute('SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?',p['source_key']).fetchone()[0]==1,'DUPLICATE_CANDIDATE_KEY')
            before=dict(op.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?',(proof['previous_observation_id'],)).fetchone())
            after=dict(np.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?',(proof['new_observation_id'],)).fetchone())
            require({k:v for k,v in before.items() if k not in ('observation_id','lastupdated')}==
                {k:v for k,v in after.items() if k not in ('observation_id','lastupdated')} and after['lastupdated']==p['new_lastupdated'], 'NATIVE_FINANCIAL_CHANGED')
            qid=p['quarter']['quarter_id']
            b=dict(oc.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?',(qid,)).fetchone())
            a=dict(nc.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?',(qid,)).fetchone())
            mutable={'parent_equity','parent_equity_usd','updated_at_utc'}
            require({k:v for k,v in b.items() if k not in mutable}=={k:v for k,v in a.items() if k not in mutable}
                and all(b[k] is None or b[k]==a[k] for k in ('parent_equity','parent_equity_usd')), 'CANONICAL_FINANCIAL_CHANGED')
            q=dict(nc.execute('SELECT * FROM v4_quarter WHERE quarter_id=?',(qid,)).fetchone())
            require({k:v for k,v in q.items() if k!='updated_at_utc'}=={k:v for k,v in p['quarter'].items() if k!='updated_at_utc'},'CANONICAL_IDENTITY_CHANGED')
            bindings={r[0] for r in nc.execute('SELECT provider_observation_id FROM v4_field_provenance WHERE quarter_id=?',(qid,))}
            require(bindings=={proof['new_observation_id']}, 'NATIVE_ACCEPTED_BINDING_MISMATCH')
            parent=dict(nc.execute('SELECT * FROM v4_parent_equity_source WHERE quarter_id=?',(qid,)).fetchone())
            raw=json.loads(new['payload_json'])
            from rawcandle.fundamentals.schema.parent_equity import finite
            require(parent['observation_id']==proof['new_observation_id'] and parent['lastupdated']==p['new_lastupdated']
                and a['parent_equity']==finite(raw['equity']) and a['parent_equity_usd']==finite(raw['equityusd'])
                and parent['sharefactor']==finite(raw['sharefactor']), 'NATIVE_PARENT_EQUITY_MISMATCH')
            outcomes[p['ticker']]=dict(current_complete=True,normalized_financial_unchanged=True,
                old_observation_preserved_in=base['generation_id'],new_observation_id=proof['new_observation_id'],
                new_lastupdated=after['lastupdated'],parent_equity=a['parent_equity'],parent_equity_usd=a['parent_equity_usd'])
    checks={role:journal.sqlite_verification(Path(path)) for role,path in candidates.items()}
    require(all(c['quick_check']=='ok' and c['foreign_key_errors']==0 for c in checks.values()), 'SQLITE_VERIFICATION_FAILED')
    return dict(outcomes=outcomes,unrelated_provider_unchanged=True,unrelated_canonical_unchanged=True,
        ownership_unchanged=True,candidate_hashes={k:v['sha256'] for k,v in checks.items()})


def test_on_copies(root,queue,plan,output,*,as_of):
    revalidate(root,queue,plan)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    base=plan['baseline'];candidates={}
    for role in ('provider','canonical'):
        target=output/(role+'.db');shutil.copyfile(base['roles'][role],target)
        require(journal.sha256_file(target)==base['role_hashes'][role],'COPY_SOURCE_DRIFT')
        candidates[role]=target
    from .refresh_copy_runtime import insert_provider_source_row
    run=generation_id(plan)
    assert_inactive_copy(candidates['provider'])
    with sqlite3.connect(candidates['provider']) as c:
        c.execute('PRAGMA foreign_keys=ON');c.execute('BEGIN IMMEDIATE')
        stamp=max(p['acquisition']['acquired_at'] for p in plan['proposals'])
        c.execute("INSERT INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,source_version,metadata_json) VALUES(?,'SHARADAR',?,?,'COMPLETED',?,?,?)",
            (run,stamp,stamp,OPERATION,VERSION,json.dumps({'preview_fingerprint':plan['preview_fingerprint']})))
        for p in plan['proposals']:
            old=p['comparison']['old_observation_id']
            # Only this current key is replaced, in an inactive candidate. All old
            # source evidence remains intact in the immutable baseline generation.
            for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                if table in ('provider_observation','sharadar_fundamental_observation'):continue
                for fk in c.execute('PRAGMA foreign_key_list("'+table.replace('"','""')+'")'):
                    require(fk[2]!='provider_observation','UNSUPPORTED_PROVIDER_DEPENDENCY')
            c.execute('DELETE FROM provider_observation WHERE observation_id=?',(old,))
            rows=trusted(p['acquisition'],p['ticker'])['ARQ'].rows
            row=next(r for r in rows if source.source_key(r)==tuple(p['source_key']))
            inserted=insert_provider_source_row(c,row,p['identity'],run_id=run,
                applied_at=p['acquisition']['acquired_at'],source_provenance={'current_state_rebuild':provenance(plan,p)},full_payload_hash=True)
            require(inserted==provenance(plan,p)['new_observation_id'],'NATIVE_INSERT_ID_MISMATCH')
    from rawcandle.fundamentals.phase12d import reconcile_canonical
    keys={(p['identity']['company_id'],p['quarter']['fiscal_year'],p['quarter']['fiscal_quarter']) for p in plan['proposals']}
    native=reconcile_canonical(candidates['provider'],candidates['canonical'],applied_at=stamp,quarter_keys=keys)
    # Accepted normalized TTM inputs are identical. Rebuilding all TTM rows
    # would churn unrelated historical lineage merely for parent-equity data,
    # which the existing native parent acceptance contract keeps separate.
    ttm=dict(action='UNCHANGED_NORMALIZED_FINANCIAL_INPUTS',logical_writes=0)
    # Native full analysis reads protected copies, never the mutable live inputs.
    paths=dict(candidates)
    for role,src in (('market',base['market']),('taxonomy',base['taxonomy'])):
        target=output/(role+'.db');shutil.copyfile(src,target)
        require(journal.sha256_file(target)==base[role+'_sha256'],'ANALYSIS_INPUT_DRIFT')
        paths[role]=target
    from .full_v2_downstream import run_full_v2_downstream
    downstream=run_full_v2_downstream(paths,output=output/'downstream',as_of_date=as_of)
    candidates['analysis']=Path(downstream['candidate_analysis_db'])
    result=measure(plan,candidates)
    require(baseline(root,queue)==base,'POST_TEST_BASELINE_DRIFT')
    receipt=seal(dict(schema=TEST,policy=VERSION,preview_fingerprint=plan['preview_fingerprint'],
        baseline=base,candidates={r:str(p.resolve()) for r,p in candidates.items()},
        result=result,native_canonical=native,native_ttm=ttm,native_analysis=downstream,
        as_of=as_of,passed=True), 'test_fingerprint')
    journal._atomic_json(output/'test_receipt.json',receipt)
    return receipt


def verify_test(plan,receipt):
    verify(plan,PREVIEW,'preview_fingerprint');verify(receipt,TEST,'test_fingerprint')
    require(receipt.get('passed') is True and receipt['preview_fingerprint']==plan['preview_fingerprint']
        and receipt['baseline']==plan['baseline'] and receipt['native_analysis']['status']=='READY'
        and receipt['native_analysis']['action']=='FULL_V2_REBUILD'
        and receipt['native_analysis']['invocation_counts']['full_v2_rebuild']==1,'TEST_BINDING_INVALID')
    require(measure(plan,{r:Path(p) for r,p in receipt['candidates'].items()})==receipt['result'],'STALE_TEST_CANDIDATE')


def publish(root,queue,plan,receipt,*,authorized_preview_fingerprint,production_intent=False,
            rehearsal=False,client=None,inject_failure_at=None):
    """An explicit administration operation; enabling/rendering UI cannot call it."""
    from .artifacts import ROOT
    from .production_transaction import production_lock
    from .refresh_production import _verified_backups, _candidate_manifest
    from .batch_add_tickers import BatchAddTickerPaths
    from rawcandle.fundamentals.generations import prepare_generation_from_candidates
    from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
    from rawcandle.scheduler.config import read_scheduler_config
    root=Path(root).resolve();queue=Path(queue);real=root==ROOT.resolve()
    require(authorized_preview_fingerprint==plan['preview_fingerprint'],'EXACT_AUTHORIZATION_REQUIRED')
    require((real and production_intent is True and not rehearsal and client is None and inject_failure_at is None)
        or (not real and rehearsal is True),'PUBLICATION_INTENT_REQUIRED')
    require(not queue.is_symlink() and (not real or queue.resolve()==root/'fundamental_reports/fundamentals_refresh_review_queue.db'),'OPERATIONAL_QUEUE_REQUIRED')
    run=generation_id(plan);config=read_scheduler_config(str(root/'scheduler_config.json'))
    jp=root/'data/.fundamentals_admin_publication_journal.json'
    with ExitStack() as stack:
        lock=root/'fundamental_reports/.fundamentals_admin_ui_operation.lock'
        if not real:lock.parent.mkdir(parents=True,exist_ok=True);lock.touch(exist_ok=True)
        fd=stack.enter_context(lock.open('r'));fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stack.enter_context(production_lock(lock_path=root/'temp/.fundamentals_admin_production.lock',scheduler_log_dir=config.log_dir))
        stack.enter_context(taxonomy_operation_lock_context(deployment_id=OPERATION,operation_type=OPERATION,
            evidence_root=None if real else ROOT/'temp/current_rebuild_rehearsal_locks'/digest(str(root))[:24]))
        journal.guard_production_writes(jp)
        acquisitions={p['ticker']:acquire(p['ticker'],client=client) for p in plan['proposals']}
        revalidate(root,queue,plan,acquisitions=acquisitions);verify_test(plan,receipt)
        active=resolve_active_generation(root,require_generation=True)
        base=plan['baseline']
        with sqlite3.connect(queue) as q:
            q.execute('BEGIN IMMEDIATE')
            require(baseline(root,queue)==base,'FINAL_BASELINE_DRIFT')
            paths=BatchAddTickerPaths(*(active.role_paths()[r] for r in ('provider','canonical','analysis')),
                root/'data/osakedata.db',root/'data/analysis.db')
            candidates={r:Path(p) for r,p in receipt['candidates'].items()}
            owned=root/'temp'/run/'publication_candidates';owned.mkdir(parents=True,exist_ok=False)
            for role,path in list(candidates.items()):
                target=owned/(role+'.db');shutil.copyfile(path,target);journal.fsync_file(target)
                require(journal.sha256_file(target)==receipt['result']['candidate_hashes'][role],'OWNED_CANDIDATE_DRIFT')
                candidates[role]=target
            backups=_verified_backups(paths,root/'backups/fundamentals_admin_production'/run,immutable_generation=True)
            roles=_candidate_manifest(candidates,backups)
            scope=dict(policy=VERSION,preview=plan,test=receipt,candidate_hashes=receipt['result']['candidate_hashes'])
            current=None;completed=False
            try:
                current=journal.prepare_journal(path=jp,operation_type=OPERATION,run_id=run,
                    preview_run_id=plan['preview_fingerprint'],test_run_id=receipt['test_fingerprint'],
                    refresh_set_fingerprint=plan['preview_fingerprint'],old_source_watermark=base['watermark'],
                    new_source_watermark=base['watermark'],source_schema_fingerprint=digest(base),roles=roles,
                    publication_mode='GENERATION_POINTER',old_generation=active.evidence()|{'manifest':dict(active.manifest)},
                    new_generation_id=run,active_generation_manifest_path=active_manifest_path(root),scope_evidence=scope)
                prepared=prepare_generation_from_candidates(candidates,generation_id=run,project_root=root,source=OPERATION)
                current=journal.update_journal(jp,current,current_publication_step='NEW_GENERATION_READY',
                    generation_activation_state='READY',new_generation_manifest=prepared['manifest'],new_generation_dir=prepared['generation_dir'])
                # Preparing our journal changes its hash, intentionally. Every
                # other baseline component must still match the exact Test.
                final=baseline_without_journal(root,queue)
                require(final=={k:v for k,v in base.items() if k!='journal_sha256'},'FINAL_GATE_DRIFT')
                require(prove(plan['proposals'],queue,base['roles']['canonical'],base['roles']['provider'])==plan['source_review_guard'],'REVIEW_SCOPE_STALE')
                ready={r:Path(p) for r,p in prepared['roles'].items()}
                require(measure(plan,ready)==receipt['result'] and journal.load_journal(jp)==current,'FINAL_CANDIDATE_DRIFT')
                if inject_failure_at=='BEFORE_ACTIVATION':raise RuntimeError('INJECTED_BEFORE_ACTIVATION')
                current=journal.activate_prepared_generation(current,new_manifest=prepared['manifest'],journal_path=jp)
                current=journal.update_journal(jp,current,state='POSTFLIGHT',postflight_state='RUNNING')
                if inject_failure_at=='POSTFLIGHT':raise RuntimeError('INJECTED_POSTFLIGHT')
                live=resolve_active_generation(root,require_generation=True)
                require(live.generation_id==run and measure(plan,live.role_paths())==receipt['result'],'POSTFLIGHT_MISMATCH')
                current=journal.update_journal(jp,current,state='COMPLETED',postflight_state='PASSED',current_publication_step='COMPLETED')
                completed=True
                if inject_failure_at=='QUEUE_FINALIZATION':raise RuntimeError('CURRENT_REBUILD_QUEUE_SYNC_REQUIRED')
                q.execute(f'CREATE TABLE IF NOT EXISTS {TABLE}(generation_id TEXT PRIMARY KEY,preview_fingerprint TEXT NOT NULL,test_fingerprint TEXT NOT NULL,record_json TEXT NOT NULL)')
                q.execute(f'INSERT INTO {TABLE} VALUES(?,?,?,?)',(run,plan['preview_fingerprint'],receipt['test_fingerprint'],json.dumps(scope,sort_keys=True)))
            except BaseException:
                if current and not completed:journal.restore_old_generation(current,journal_path=jp)
                raise
    result=dict(generation_id=run,journal_state='COMPLETED',postflight='PASSED',ownership_approved=False,pb_approved=False)
    record_dispositions(root,queue,plan,receipt)
    return result


def baseline_without_journal(root,queue):
    """Final gate while our own native journal is PREPARED; never grants recovery."""
    # The production lock is already held. Avoid the public healthy-journal gate
    # only for this comparison; the exact owned journal is checked by the caller.
    base=strict.baseline(Path(root))
    taxonomy=Path(root)/'data/analysis.db'
    from .production_transaction import _no_sidecars
    _no_sidecars(taxonomy)
    return {**base,'taxonomy':str(taxonomy),'taxonomy_sha256':journal.sha256_file(taxonomy),
        'queue_content':strict._content(Path(queue)),
        'rebuild_code':{str(p):journal.sha256_file(p) for p in CODE}}


def record_dispositions(root,queue,plan,receipt):
    from rawcandle.scheduler.config import read_scheduler_config
    config=read_scheduler_config(str(Path(root)/'scheduler_config.json'))
    with strict.preflight(Path(root),Path(config.log_dir)):
        require(prove(plan['proposals'],queue,plan['baseline']['roles']['canonical'],
            plan['baseline']['roles']['provider'])==plan['source_review_guard'],'COMPLETED_REVIEW_CHANGED')
        return _record_dispositions(root,queue,plan,receipt)


def _record_dispositions(root,queue,plan,receipt):
    """Idempotent operational finalization from an actual completed publication.

    A failed finalization leaves the exact completed journal available for retry;
    it never re-publishes or resolves a frozen/ownership review.
    """
    from . import legacy_payload_disposition as dispositions
    root=Path(root);queue=Path(queue)
    j=journal.load_journal(root/'data/.fundamentals_admin_publication_journal.json')
    require(j and j.get('state')=='COMPLETED' and j.get('postflight_state')=='PASSED'
        and j.get('new_generation_id')==generation_id(plan) and j.get('operation_type')==OPERATION
        and j['scope_evidence']['preview']==plan and j['scope_evidence']['test']==receipt,'COMPLETED_PUBLICATION_REQUIRED')
    active=resolve_active_generation(root,require_generation=True)
    require(active.generation_id==generation_id(plan) and measure(plan,active.role_paths())==receipt['result'],'COMPLETED_RESULT_CHANGED')
    old={r['ticker']:r for r in dispositions.list_items(queue)}
    rows=[];observations=[]
    with strict._ro(active.role_paths()['provider']) as p:
        for proposal in plan['proposals']:
            ticker=proposal['ticker'];previous=old.get(ticker,{})
            proof=provenance(plan,proposal)
            scope=next(r for r in plan['source_review_guard']['items'] if r['ticker']==ticker)
            evidence=dict(identity_exact=True,current_source_trusted=True,current_binding_known=True,
                current_incomplete=False,current_healthy=True,contradictions=[],financial_drift=False,
                historical_only_count=previous.get('evidence',{}).get('historical_only_count',0),
                historical_no_current_effect_proven=True,
                current_state_rebuild=seal(dict(policy=VERSION,postflight='PASSED',
                    observation_id=proof['new_observation_id'],payload_fingerprint=proof['new_content_hash'],
                    generation_id=active.generation_id,test_fingerprint=receipt['test_fingerprint'],
                    preview_fingerprint=plan['preview_fingerprint'],frozen_conflict_count=scope['frozen_conflict_count']), 'proof_fingerprint'))
            counts={**previous.get('observation_counts',{})}
            counts['legacy']=sum(
                len(json.loads(r[0]))==len(source.REFRESH_REQUEST_FIELDS) for r in p.execute('SELECT payload_json FROM provider_observation WHERE provider_ticker=?',(ticker,)))
            counts['current_rebuilt']=1
            binding=dict(observation_id=proof['new_observation_id'],content_hash=proof['new_content_hash'],
                payload_fingerprint=proof['new_content_hash'],fiscal_year=proposal['quarter']['fiscal_year'],
                fiscal_quarter=proposal['quarter']['fiscal_quarter'])
            rows.append(dispositions.item(ticker,proposal['identity']['company_id'],proposal['identity']['security_id'],
                evidence,counts=counts,reason=VERSION,source_binding=binding))
            observations.append(dict(ticker=ticker,observation_id=proof['new_observation_id'],
                current_accepted_binding=True,frozen_accepted_binding=False,retained=False,
                fresh_exact_key=True,archive_completeness_only=False,repaired=False,current_rebuilt=True))
    # This public ledger writer reacquires native preflight locks and binds the
    # new active generation; only the selected ticker ledger rows are updated.
    artifact=dispositions.seal(rows,baseline=strict.baseline(root),observations=observations,
        evidence_reference=str(root/'fundamental_reports/admin_runs'/active.generation_id/'result.json'),
        created_at=receipt['as_of']+'T00:00:00Z')
    dispositions.register(root,queue,artifact,authorized_artifact_fingerprint=artifact['artifact_fingerprint'])
    return artifact


def sync_completed(root,queue):
    """Recover only our completed typed decision after an interrupted queue commit.

    Native generation rollback/recovery remains owned by publication_journal.
    This cannot approve a review, rerun reconciliation or publish a generation.
    """
    from rawcandle.scheduler.config import read_scheduler_config
    root=Path(root);queue=Path(queue)
    from .artifacts import ROOT
    require(not queue.is_symlink() and (root.resolve()!=ROOT.resolve() or
        queue.resolve()==ROOT/'fundamental_reports/fundamentals_refresh_review_queue.db'), 'OPERATIONAL_QUEUE_REQUIRED')
    config=read_scheduler_config(str(root/'scheduler_config.json'))
    with strict.preflight(root,Path(config.log_dir)):
        jp=root/'data/.fundamentals_admin_publication_journal.json';j=journal.load_journal(jp)
        require(j and j.get('operation_type')==OPERATION and j.get('state')=='COMPLETED'
            and j.get('postflight_state')=='PASSED','COMPLETED_PUBLICATION_REQUIRED')
        scope=j['scope_evidence'];plan=scope['preview'];test=scope['test']
        verify(plan,PREVIEW,'preview_fingerprint');verify(test,TEST,'test_fingerprint')
        active=resolve_active_generation(root,require_generation=True);run=generation_id(plan)
        require(active.generation_id==j.get('new_generation_id')==run and test['passed'] is True
            and test['preview_fingerprint']==plan['preview_fingerprint'] and test['baseline']==plan['baseline']
            and j['test_run_id']==test['test_fingerprint'] and measure(plan,active.role_paths())==test['result'],
            'COMPLETED_RESULT_CHANGED')
        require(prove(plan['proposals'],queue,plan['baseline']['roles']['canonical'],
            plan['baseline']['roles']['provider'])==plan['source_review_guard'],'COMPLETED_REVIEW_CHANGED')
        with sqlite3.connect(queue) as q:
            q.row_factory=sqlite3.Row;q.execute('BEGIN IMMEDIATE')
            exists=q.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLE,)).fetchone()
            row=q.execute(f'SELECT * FROM {TABLE} WHERE generation_id=?',(run,)).fetchone() if exists else None
            if row:
                require(row['preview_fingerprint']==plan['preview_fingerprint'] and
                    row['test_fingerprint']==test['test_fingerprint'] and json.loads(row['record_json'])==scope,'COMPLETED_TYPED_CONFLICT')
            else:
                require(strict._content(queue)==plan['baseline']['queue_content'],'COMPLETED_QUEUE_DRIFT')
                q.execute(f'CREATE TABLE IF NOT EXISTS {TABLE}(generation_id TEXT PRIMARY KEY,preview_fingerprint TEXT NOT NULL,test_fingerprint TEXT NOT NULL,record_json TEXT NOT NULL)')
                q.execute(f'INSERT INTO {TABLE} VALUES(?,?,?,?)',(run,plan['preview_fingerprint'],test['test_fingerprint'],json.dumps(scope,sort_keys=True)))
        record_dispositions(root,queue,plan,test)
    return dict(generation_id=run,journal_state='COMPLETED',postflight='PASSED',ownership_approved=False,pb_approved=False)
