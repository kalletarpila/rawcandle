"""Exact-source, linked accounting-boundary decisions; no implicit approvals.

Proposal creation and validation are read-only. Store installation is restricted to
inactive provider copies. Historical evidence is deliberately outside native joins.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .contracts import fingerprint, utc_now

VERSION = 'WFRD_ACCOUNTING_BOUNDARY_REVIEW_V1'
PRESERVE = 'PRESERVE_ACCEPTED_FISCAL_IDENTITY'
RETAIN = 'RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE'
ARQ_KEY = ('WFRD', 'ARQ', '2020-03-16', '2019-12-31')
OLD_MRQ_KEY = ('WFRD', 'MRQ', '2019-12-31', '2019-12-31')
CURRENT_MRQ_KEY = ('WFRD', 'MRQ', '2019-12-13', '2019-12-13')
ARCHIVE = 'reviewed_historical_provider_observation'
DECISIONS = 'reviewed_accounting_boundary_resolution'
CONTEXT = 'reviewed_provider_observation_context'
QUEUE = 'accounting_boundary_review_item'
REHEARSAL_CHECKS = ('both_q4s','established_dates','no_existing_financial_change','unrelated_tickers','historical_only_archive','mrq_nonfinancial','pb_arq_binding')


class BoundaryReviewError(ValueError):
    pass


def _refresh():
    # Lazy to keep canonical readers independent of admin import cycles.
    from . import refresh_fundamentals
    return refresh_fundamentals


def _ro(path):
    c = sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c


def _has(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def authority():
    root = Path(__file__).resolve().parents[3]
    names = ('wfrd_fiscal_identity_review_2026-10-25.md', 'wfrd_mrq_disposition_policy.md')
    import hashlib
    return {'accession': '0001603923-20-000017', 'form': '10-K', 'fiscal_year': 2019,
            'fiscal_period': 'FY', 'boundary': '2019-12-13',
            'url': 'https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R8.htm',
            'policy_hashes': {n: hashlib.sha256((root/'docs/fundamentals_v4'/n).read_bytes()).hexdigest() for n in names}}


def _key(row):
    return _refresh().source_key(row)


def _row(row):
    return _refresh()._raw_row(_refresh().normalize_source_row(row))


def _financial(row):
    return fingerprint({k: row.get(k) for k in _refresh().FINANCIAL_FIELDS})


def _acquired(c, key):
    native = c.execute('SELECT * FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=? ORDER BY lastupdated DESC,observation_id', key).fetchall()
    if len(native) != 1:
        raise BoundaryReviewError('BOUNDARY_ACCEPTED_OBSERVATION_NOT_UNIQUE')
    s = dict(native[0])
    po = c.execute('SELECT * FROM provider_observation WHERE observation_id=?', (s['observation_id'],)).fetchone()
    return {'provider_observation': dict(po), 'native_observation': s,
            'normalized': _row(s), 'normalized_fingerprint': fingerprint(_row(s)),
            'financial_fingerprint': _financial(_row(s))}


def _incoming(history, key):
    if history.status != 'COMPLETE':
        raise BoundaryReviewError('BOUNDARY_INCOMPLETE_SOURCE')
    rows = [r for r in history.rows if _key(r) == key]
    if len(rows) != 1:
        raise BoundaryReviewError('BOUNDARY_CURRENT_KEY_MISSING_OR_DUPLICATED')
    r = rows[0]
    return {'normalized': _row(r), 'normalized_fingerprint': fingerprint(_row(r)),
            'financial_fingerprint': _financial(_row(r)),
            'acquisition_payload': deepcopy(r.get('_acquisition_payload', _row(r)))}


def _quarter(c, company_id, year):
    r = c.execute("SELECT quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_reportperiod,source_availability_date,first_public_result_date FROM v4_quarter WHERE company_id=? AND fiscal_year=? AND fiscal_quarter='Q4' AND identity_status='ACCEPTED' AND identity_provider='SHARADAR_ARQ'", (company_id,year)).fetchone()
    if r is None:
        raise BoundaryReviewError('BOUNDARY_CANONICAL_QUARTER_MISSING')
    return dict(r)


def create_proposal(provider_db, canonical_db, histories, identity, *, created_at=None):
    """Build a non-authoritative, immutable-by-fingerprint review proposal."""
    if identity.get('status') != 'KNOWN' or identity.get('ticker') != 'WFRD' or any(not identity.get(k) for k in ('company_id','security_id','company_key','provider_security_id','provider_ticker')):
        raise BoundaryReviewError('BOUNDARY_IDENTITY_INCOMPLETE')
    with _ro(provider_db) as p, _ro(canonical_db) as c:
        old_arq, old_mrq = _acquired(p, ARQ_KEY), _acquired(p, OLD_MRQ_KEY)
        quarters = [_quarter(c,identity['company_id'],y) for y in (2019,2020)]
        provenance = c.execute("SELECT provider_observation_id FROM v4_field_provenance WHERE quarter_id=? AND canonical_field='shares_outstanding' AND provider='SHARADAR'", (quarters[0]['quarter_id'],)).fetchall()
        if len(provenance)!=1 or provenance[0][0]!=old_arq['provider_observation']['observation_id']:
            raise BoundaryReviewError('BOUNDARY_ACCEPTED_ARQ_PROVENANCE_MISMATCH')
        # Bind both the supplied resolver result and actual published mappings.
        security = c.execute('SELECT company_id,current_ticker FROM security WHERE security_id=?',(identity['security_id'],)).fetchone()
        if security is None or tuple(security) != (identity['company_id'],'WFRD'):
            raise BoundaryReviewError('BOUNDARY_SECURITY_MISMATCH')
        mappings = [tuple(r) for r in c.execute('SELECT provider,provider_security_id,security_id,provider_ticker FROM provider_security_identity WHERE security_id=? ORDER BY provider,provider_security_id',(identity['security_id'],))]
        if ('SHARADAR',str(identity['provider_security_id']),identity['security_id'],'WFRD') not in mappings:
            raise BoundaryReviewError('BOUNDARY_PROVIDER_IDENTITY_MISMATCH')
        refresh_state = [dict(r) for r in p.execute('SELECT * FROM sharadar_refresh_state')] if _has(p,'sharadar_refresh_state') else []
    incoming_arq = _incoming(histories['ARQ'],ARQ_KEY)
    incoming_mrq = _incoming(histories['MRQ'],CURRENT_MRQ_KEY)
    if any(_key(r)==OLD_MRQ_KEY for r in histories['MRQ'].rows):
        raise BoundaryReviewError('BOUNDARY_REMOVED_KEY_REAPPEARED')
    if (old_arq['normalized']['fiscalperiod'],incoming_arq['normalized']['fiscalperiod'],old_mrq['normalized']['fiscalperiod'],incoming_mrq['normalized']['fiscalperiod']) != ('2019-Q4','2020-Q4','2019-Q4','2019-Q4'):
        raise BoundaryReviewError('BOUNDARY_LABEL_MISMATCH')
    expected_flows = {'ncfo':-68000000,'capex':-73000000,'fcf':-141000000,'shareswa':1004000000}
    if any(incoming_mrq['normalized'].get(f)!=expected_flows.get(f) for f in _refresh().FINANCIAL_FIELDS) or any(old_mrq['normalized'].get(f) is not None for f in ('ncfo','capex','fcf','revenue','netinc')):
        raise BoundaryReviewError('BOUNDARY_UNSUPPORTED_ACCOUNTING_PAYLOAD')
    if old_arq['financial_fingerprint'] != incoming_arq['financial_fingerprint']:
        raise BoundaryReviewError('BOUNDARY_ARQ_FINANCIAL_DRIFT')
    if quarters[0]['period_end'] != ARQ_KEY[3] or quarters[0]['first_public_result_date'] != ARQ_KEY[2] or quarters[1]['period_end'] != '2020-12-31' or quarters[1]['first_public_result_date'] != '2021-02-19':
        raise BoundaryReviewError('BOUNDARY_PUBLICATION_IDENTITY_MISMATCH')
    manifest = Path(provider_db).parent/'generation_manifest.json'
    baseline = {'generation': Path(provider_db).parent.name,
                'manifest_fingerprint': fingerprint(json.loads(manifest.read_text())) if manifest.exists() else None,
                'refresh_state':refresh_state, 'quarters':quarters, 'provider_mappings':[list(x) for x in mappings]}
    context = {'current_provider_evidence':True,'accounting_basis':'PREDECESSOR',
               'observation_role':'PARTIAL_PERIOD_FLOW','full_quarter_eligible':False,
               'canonical_eligible':False,'ttm_eligible':False,'share_pb_eligible':False,
               'stock_fallback_eligible':False,'calculation_eligible':False,
               'relationship':'DISTINCT_ACCOUNTING_OBSERVATION',
               'derived_interval':{'start':'2019-10-01','end':'2019-12-13','source':'DERIVED_REVIEW_EVIDENCE'}}
    evidence = {'provider':'SHARADAR','dataset':'fundamentals','identity':dict(identity),
                'baseline':baseline,'authority':authority(),
                'arq':{'action':PRESERVE,'source_key':list(ARQ_KEY),'accepted_label':'2019-Q4','provider_label':'2020-Q4','accepted':old_arq,'incoming':incoming_arq},
                'mrq':{'action':RETAIN,'removed_key':list(OLD_MRQ_KEY),'current_key':list(CURRENT_MRQ_KEY),
                       'accepted':old_mrq,'incoming':incoming_mrq,'absence_proof':histories['MRQ'].evidence(),
                       'historical_role':'SUCCESSOR_YEAR_END_STOCKS','historical_calculation_eligible':False,
                       'current_role':'PREDECESSOR_PARTIAL_PERIOD_FLOWS','context':context}}
    evidence["baseline_fingerprint"] = fingerprint(baseline)
    for section in ("arq", "mrq"):
        evidence[section]["evidence_fingerprint"] = fingerprint(evidence[section])
    ef = fingerprint(evidence)
    proposal = {'schema_version':VERSION,'resolution_id':f'boundary_{ef}',
                'created_at':created_at or utc_now(),'status':'OPEN','operator':None,
                'stale':False,'production_authorized':False,'evidence':evidence,'evidence_fingerprint':ef}
    proposal['proposal_fingerprint'] = fingerprint(proposal)
    return proposal


def verify(proposal):
    p = dict(proposal); expected = p.pop('proposal_fingerprint',None)
    if expected != fingerprint(p) or p.get('schema_version') != VERSION or p.get('status') != 'OPEN' or p.get('operator') is not None or p.get('stale') is not False or p.get('production_authorized') is not False or p.get('evidence_fingerprint') != fingerprint(p.get('evidence')) or p.get('resolution_id') != 'boundary_'+str(p.get('evidence_fingerprint')):
        raise BoundaryReviewError('BOUNDARY_PROPOSAL_INTEGRITY')
    e = p['evidence']
    if e.get('baseline_fingerprint')!=fingerprint(e.get('baseline')) or any(e[section].get('evidence_fingerprint')!=fingerprint({k:v for k,v in e[section].items() if k!='evidence_fingerprint'}) for section in ('arq','mrq')):
        raise BoundaryReviewError('BOUNDARY_SECTION_INTEGRITY')
    if tuple(e['arq']['source_key']) != ARQ_KEY or tuple(e['mrq']['removed_key']) != OLD_MRQ_KEY or tuple(e['mrq']['current_key']) != CURRENT_MRQ_KEY or e['arq']['action'] != PRESERVE or e['mrq']['action'] != RETAIN or e['authority'] != authority():
        raise BoundaryReviewError('BOUNDARY_SCOPE_OR_AUTHORITY_DRIFT')
    context=e['mrq']['context']
    flags=('full_quarter_eligible','canonical_eligible','ttm_eligible','share_pb_eligible','stock_fallback_eligible','calculation_eligible')
    if (e['arq']['accepted_label']!='2019-Q4' or e['arq']['provider_label']!='2020-Q4'
            or e['mrq']['historical_role']!='SUCCESSOR_YEAR_END_STOCKS'
            or e['mrq']['current_role']!='PREDECESSOR_PARTIAL_PERIOD_FLOWS'
            or e['mrq']['historical_calculation_eligible'] is not False
            or any(context.get(k) is not False for k in flags)
            or context.get('current_provider_evidence') is not True
            or context.get('accounting_basis')!='PREDECESSOR'
            or context.get('observation_role')!='PARTIAL_PERIOD_FLOW'
            or context.get('relationship')!='DISTINCT_ACCOUNTING_OBSERVATION'
            or context.get('derived_interval')!={'start':'2019-10-01','end':'2019-12-13','source':'DERIVED_REVIEW_EVIDENCE'}):
        raise BoundaryReviewError('BOUNDARY_ACCOUNTING_SEMANTICS_INVALID')
    return e


def validate_pending(proposal, provider_db, canonical_db, histories, identity):
    verify(proposal)
    actual = create_proposal(provider_db,canonical_db,histories,identity)
    if actual['evidence_fingerprint'] != proposal['evidence_fingerprint']:
        raise BoundaryReviewError('BOUNDARY_EVIDENCE_STALE')
    return True


def approve(proposal, *, operator, rehearsal):
    """Explicit operator action, never invoked by proposal generation/Preview."""
    verify(proposal)
    if not all(rehearsal.get('checks',{}).get(k) is True for k in REHEARSAL_CHECKS) or not str(operator).strip() or rehearsal.get('proposal_fingerprint') != proposal['proposal_fingerprint'] or rehearsal.get('passed') is not True or rehearsal.get('receipt_fingerprint') != fingerprint({k:v for k,v in rehearsal.items() if k!='receipt_fingerprint'}):
        raise BoundaryReviewError('BOUNDARY_OPERATOR_AND_REHEARSAL_REQUIRED')
    validate_rehearsal_receipt(proposal,rehearsal)
    decision = {'proposal':deepcopy(proposal),'status':'APPROVED','operator':operator,
                'approved_at':utc_now(),'rehearsal':dict(rehearsal),'copy_only':False}
    decision['decision_fingerprint'] = fingerprint(decision)
    return decision


def verify_decision(decision):
    d = dict(decision); fp = d.pop('decision_fingerprint',None)
    if fp != fingerprint(d) or d.get('status')!='APPROVED' or not str(d.get('operator') or '').strip():
        raise BoundaryReviewError('BOUNDARY_NOT_APPROVED')
    verify(d['proposal'])
    if d.get('copy_only') is True and d['operator']!='COPY_ONLY_REHEARSAL_NOT_RUNTIME_APPROVAL':
        raise BoundaryReviewError('BOUNDARY_REHEARSAL_SCOPE_INVALID')
    r=d['rehearsal']
    if not all(r.get('checks',{}).get(k) is True for k in REHEARSAL_CHECKS) or r.get('passed') is not True or r.get('proposal_fingerprint')!=d['proposal']['proposal_fingerprint'] or r.get('receipt_fingerprint')!=fingerprint({k:v for k,v in r.items() if k!='receipt_fingerprint'}):
        raise BoundaryReviewError('BOUNDARY_REHEARSAL_INVALID')
    if d.get('copy_only') is not True and (set(r.get('candidate_sha256',{}))!={'provider','canonical'} or any(len(str(v))!=64 for v in r['candidate_sha256'].values())):
        raise BoundaryReviewError('BOUNDARY_REHEARSAL_PHYSICAL_PROOF_REQUIRED')
    return d['proposal']['evidence']


def ensure_store(c):
    # Caller owns the inactive-copy transaction. No FK to replaceable native rows.
    for table,key in ((ARCHIVE,'observation_id'),(DECISIONS,'resolution_id'),(CONTEXT,'source_key')):
        c.execute(f'CREATE TABLE IF NOT EXISTS {table} ({key} TEXT PRIMARY KEY, record_json TEXT NOT NULL, record_fingerprint TEXT NOT NULL)')
        for operation in ('UPDATE','DELETE'):
            c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE_BOUNDARY_EVIDENCE'); END")


def _insert(c,table,key,record):
    fp=fingerprint(record)
    old=c.execute(f'SELECT record_fingerprint FROM {table} WHERE {"observation_id" if table==ARCHIVE else "resolution_id" if table==DECISIONS else "source_key"}=?',(key,)).fetchone()
    if old:
        if old[0]!=fp: raise BoundaryReviewError('BOUNDARY_IMMUTABLE_RECORD_CONFLICT')
        return
    c.execute(f'INSERT INTO {table} VALUES(?,?,?)',(key,json.dumps(record,sort_keys=True),fp))


def _records(c,table):
    if not _has(c,table): return []
    out=[]
    for row in c.execute(f'SELECT record_json,record_fingerprint FROM {table}'):
        r=json.loads(row[0])
        if fingerprint(r)!=row[1]: raise BoundaryReviewError('BOUNDARY_STORE_TAMPERED')
        out.append(r)
    return out


def historical_evidence(provider_db):
    with _ro(provider_db) as c:return _records(c,ARCHIVE)


def installed_decisions(provider_db):
    with _ro(provider_db) as c:return _records(c,DECISIONS)


def install_on_copy(provider_db, decision):
    from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy
    assert_inactive_copy(Path(provider_db))
    e=verify_decision(decision);p=decision['proposal'];rid=p['resolution_id']
    archive={'original':e['mrq']['accepted'],'identity':e['identity'],
             'accepted_generation':e['baseline'],'absence_proof':e['mrq']['absence_proof'],
             'accounting_role':e['mrq']['historical_role'],'calculation_eligible':False,
             'membership':'HISTORICAL_ONLY','reason':RETAIN,'resolution_id':rid,'created_at':decision['approved_at']}
    ctx={'source_key':list(CURRENT_MRQ_KEY),'row_fingerprint':e['mrq']['incoming']['normalized_fingerprint'],
         'resolution_id':rid,**e['mrq']['context']}
    with sqlite3.connect(provider_db) as c:
        c.execute('BEGIN IMMEDIATE');ensure_store(c)
        _insert(c,ARCHIVE,e['mrq']['accepted']['provider_observation']['observation_id'],archive)
        _insert(c,CONTEXT,json.dumps(list(CURRENT_MRQ_KEY)),ctx)
        _insert(c,DECISIONS,rid,dict(decision))


def effective_fiscalperiod(c, row):
    """Exact approved identity projection; never edits a vendor/native field."""
    value=row.get('fiscalperiod')
    if _key(row)!=ARQ_KEY:return value
    for d in _records(c,DECISIONS):
        e=verify_decision(d)
        if _key(row)==tuple(e['arq']['source_key']):
            if fingerprint(_row(row))!=e['arq']['incoming']['normalized_fingerprint'] or row.get('company_id',e['identity']['company_id'])!=e['identity']['company_id'] or row.get('security_id',e['identity']['security_id'])!=e['identity']['security_id']:
                raise BoundaryReviewError('BOUNDARY_CANONICAL_SOURCE_DRIFT')
            return e['arq']['accepted_label']
    return value


def current_context(provider_db, row):
    with _ro(provider_db) as c:
        for ctx in _records(c,CONTEXT):
            if tuple(ctx['source_key'])==_key(row):
                if ctx['row_fingerprint']!=fingerprint(_row(row)):raise BoundaryReviewError('BOUNDARY_CONTEXT_STALE')
                return ctx
    return None


def combined_evidence(provider_db, ticker='WFRD'):
    r=_refresh();out=[]
    for dimension in ('ARQ','MRQ'):
        for row in r.load_current_history(Path(provider_db),ticker,dimension)['rows']:
            out.append({'membership':'CURRENT_STORED','observation':_row(row),'context':current_context(provider_db,row)})
    out.extend({'membership':'HISTORICAL_ONLY',**h} for h in historical_evidence(provider_db) if h['original']['normalized']['ticker']==ticker)
    return out


def _published_valid(decision,provider_db,canonical_db,histories,identity):
    e=verify_decision(decision)
    validate_store(provider_db)
    if dict(identity)!=e['identity']:raise BoundaryReviewError('BOUNDARY_PUBLISHED_IDENTITY_STALE')
    if _incoming(histories['ARQ'],ARQ_KEY)!=e['arq']['incoming'] or _incoming(histories['MRQ'],CURRENT_MRQ_KEY)!=e['mrq']['incoming']:
        raise BoundaryReviewError('BOUNDARY_PUBLISHED_SOURCE_STALE')
    if any(_key(r)==OLD_MRQ_KEY for r in histories['MRQ'].rows):raise BoundaryReviewError('BOUNDARY_REMOVED_KEY_REAPPEARED')
    with _ro(canonical_db) as c:
        for q in e['baseline']['quarters']:
            actual=_quarter(c,identity['company_id'],q['fiscal_year'])
            if {k:v for k,v in actual.items() if k!='quarter_id'}!={k:v for k,v in q.items() if k!='quarter_id'}:
                raise BoundaryReviewError('BOUNDARY_PUBLISHED_CANONICAL_STALE')
    archives=historical_evidence(provider_db)
    if not any(a['original']==e['mrq']['accepted'] for a in archives):raise BoundaryReviewError('BOUNDARY_ARCHIVE_MISSING')
    # Unrelated new periods may append; other same-period observations may not.
    expected={ARQ_KEY,CURRENT_MRQ_KEY}
    for h in histories.values():
        for row in h.rows:
            if (row['reportperiod'] in (ARQ_KEY[3],CURRENT_MRQ_KEY[3]) or row['fiscalperiod']=='2019-Q4') and _key(row) not in expected:
                raise BoundaryReviewError('BOUNDARY_NEW_ACCOUNTING_CONFLICT')


def evaluate(provider_db,canonical_db,histories,identity, *, decision=None):
    """Return an exact validated application, or a fail-closed diagnostic."""
    if identity.get("ticker") != "WFRD" and decision is None:
        return {"applied":False,"stale":False}
    installed=[d for d in installed_decisions(provider_db) if d['proposal']['evidence']['identity']['ticker']==identity.get('ticker')]
    if decision is None and not installed:return {'applied':False,'stale':False}
    try:
        if installed:
            if len(installed)!=1:raise BoundaryReviewError('BOUNDARY_AMBIGUOUS_DECISIONS')
            decision=installed[0];_published_valid(decision,provider_db,canonical_db,histories,identity)
            phase='PUBLISHED'
        else:
            verify_decision(decision);validate_pending(decision['proposal'],provider_db,canonical_db,histories,identity);phase='PENDING'
        return {'applied':True,'stale':False,'phase':phase,'decision':deepcopy(decision),
                'proposal_fingerprint':decision['proposal']['proposal_fingerprint'],
                'absence_attestation':histories['MRQ'].evidence()}
    except (BoundaryReviewError,KeyError,TypeError,ValueError) as exc:
        return {'applied':False,'stale':True,'reason':str(exc)}


def comparison(ticker,current,histories,application,**policy):
    """Consume only these two exact events; leave unrelated review evidence intact."""
    r=_refresh()
    if not application.get('applied'):
        result=r.compare_ticker_histories(ticker,current,histories,**policy)
        if application.get('stale') or application.get('pending'):
            result.update(classification='REVIEW_REQUIRED',review_reason='ACCOUNTING_BOUNDARY_REVIEW_STALE' if application.get('stale') else 'ACCOUNTING_BOUNDARY_REVIEW_PENDING',accounting_boundary_resolution=dict(application))
            # Never let a stale published overlay become a ticker-local hold.
        return result
    verify_decision(application['decision'])
    # Existing comparators operate on untouched native rows. Their approvals are
    # not broadened: run once diagnostically, then verify *every* consumed event.
    raw=r.compare_ticker_histories(ticker,current,histories,**policy)
    events=raw.get('source_history_events',[])
    for event in events:
        k=_key(event.get('source_identity',{}))
        if (event['event']=='FISCAL_IDENTITY_REVISION' and k==ARQ_KEY) or (event['event']=='TRUE_SOURCE_REMOVAL' and k==OLD_MRQ_KEY):continue
        if event['event']=='AGED_OUT_OF_SOURCE_WINDOW':continue
        return raw
    # Additive semantic path: never manufacture a legacy acceptance approval.
    result=r.compare_ticker_histories(ticker,current,histories,accounting_boundary_application=application,**policy)
    result.pop('fiscal_revision_approval',None)
    result.pop('true_removal_approval',None)
    result['accounting_boundary_resolution']=deepcopy(application)
    result['reviewed_accounting_events']=events
    result['effective_canonical_identity']={'source_key':list(ARQ_KEY),'provider_label':'2020-Q4','effective_label':'2019-Q4'}
    return result


def read_items(queue_db):
    if not Path(queue_db).exists():return []
    with _ro(queue_db) as c:
        if not _has(c,QUEUE):return []
        return [json.loads(r[0]) for r in c.execute(f'SELECT record_json FROM {QUEUE} ORDER BY resolution_id')]


def save_item(queue_db, proposal, *, decision=None, stale_reason=None, rejected_reason=None):
    """Explicit review registration/action. Never called by proposal creation."""
    verify(proposal)
    if decision is not None:
        verify_decision(decision)
        if decision.get('copy_only'):
            raise BoundaryReviewError('BOUNDARY_COPY_ONLY_IS_NOT_OPERATOR_APPROVAL')
        if decision['proposal']!=proposal:raise BoundaryReviewError('BOUNDARY_QUEUE_PROPOSAL_MISMATCH')
    item={'proposal':deepcopy(proposal),'decision':decision,'status':'REJECTED' if rejected_reason else 'STALE' if stale_reason else 'APPROVED' if decision else 'OPEN','stale_reason':stale_reason,'rejected_reason':rejected_reason}
    from .refresh_review_queue import _connect as connect_queue
    with connect_queue(Path(queue_db)) as c:
        c.execute(f'CREATE TABLE IF NOT EXISTS {QUEUE}(resolution_id TEXT PRIMARY KEY,record_json TEXT NOT NULL)')
        c.execute(f'CREATE TABLE IF NOT EXISTS {QUEUE}_audit(id INTEGER PRIMARY KEY,record_json TEXT NOT NULL)')
        old=c.execute(f'SELECT record_json FROM {QUEUE} WHERE resolution_id=?',(proposal['resolution_id'],)).fetchone()
        if old and json.loads(old[0])['proposal']!=proposal:raise BoundaryReviewError('BOUNDARY_IMMUTABLE_PROPOSAL_CONFLICT')
        c.execute(f'INSERT OR REPLACE INTO {QUEUE} VALUES(?,?)',(proposal['resolution_id'],json.dumps(item,sort_keys=True)))
        c.execute(f'INSERT INTO {QUEUE}_audit(record_json) VALUES(?)',(json.dumps(item,sort_keys=True),))
    return item


def queued_decision(queue_db,ticker):
    matches=[i['decision'] for i in read_items(queue_db) if i['status']=='APPROVED' and i['proposal']['evidence']['identity']['ticker']==ticker]
    if len(matches)>1:raise BoundaryReviewError('BOUNDARY_AMBIGUOUS_QUEUE')
    return matches[0] if matches else None


def validate_store(provider_db):
    """Fail closed before a copy can pass candidate validation."""
    with _ro(provider_db) as c:
        for decision in _records(c,DECISIONS):
            e=verify_decision(decision)
            for key,expected in ((ARQ_KEY,e['arq']['incoming']), (CURRENT_MRQ_KEY,e['mrq']['incoming'])):
                row=c.execute('SELECT s.*,p.company_id,p.security_id FROM sharadar_fundamental_observation s JOIN provider_observation p USING(observation_id) WHERE ticker=? AND s.dimension=? AND s.date=? AND s.reportperiod=?',key).fetchall()
                import hashlib
                expected_id = hashlib.sha256(f"SHARADAR|fundamentals|{'|'.join(key)}|{expected['normalized_fingerprint']}".encode()).hexdigest()
                if len(row)!=1 or row[0]['observation_id']!=expected_id or fingerprint(_row(dict(row[0])))!=expected['normalized_fingerprint'] or row[0]['company_id']!=e['identity']['company_id'] or row[0]['security_id']!=e['identity']['security_id']:
                    raise BoundaryReviewError('BOUNDARY_CANDIDATE_SOURCE_MISMATCH')
                if key==ARQ_KEY and effective_fiscalperiod(c,dict(row[0]))!='2019-Q4':
                    raise BoundaryReviewError('BOUNDARY_CANDIDATE_OVERLAY_MISSING')
            if c.execute('SELECT 1 FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?',OLD_MRQ_KEY).fetchone():
                raise BoundaryReviewError('BOUNDARY_CANDIDATE_OLD_KEY_ACTIVE')
            if not any(a['original']==e['mrq']['accepted'] and a['calculation_eligible'] is False and a['membership']=='HISTORICAL_ONLY' and a['accounting_role']=='SUCCESSOR_YEAR_END_STOCKS' for a in _records(c,ARCHIVE)):
                raise BoundaryReviewError('BOUNDARY_CANDIDATE_ARCHIVE_MISSING')
            contexts=_records(c,CONTEXT)
            if len(contexts)!=1 or contexts[0]['source_key']!=list(CURRENT_MRQ_KEY) or contexts[0]['row_fingerprint']!=e['mrq']['incoming']['normalized_fingerprint'] or contexts[0]['resolution_id']!=decision['proposal']['resolution_id'] or {k:contexts[0][k] for k in e['mrq']['context']}!=e['mrq']['context']:
                raise BoundaryReviewError('BOUNDARY_CANDIDATE_CONTEXT_MISMATCH')
    return {'historical_rows':len(historical_evidence(provider_db)), 'validated':True}


def current_provider_history(provider_db,ticker,dimension):
    """Explicit current-response membership, excluding source-window carry-forward."""
    return [{'observation':_row(r),'context':current_context(provider_db,r)}
            for r in _refresh().load_current_history(Path(provider_db),ticker,dimension)['rows']
            if not r.get('_history_retention_status')]


def validate_candidate_input(application, histories):
    e=verify_decision(application['decision'])
    for dim,key,expected in (('ARQ',ARQ_KEY,e['arq']['incoming']),('MRQ',CURRENT_MRQ_KEY,e['mrq']['incoming'])):
        if _incoming(histories[dim],key)!=expected:
            raise BoundaryReviewError('BOUNDARY_CANDIDATE_INPUT_STALE')
    if histories['MRQ'].status!='COMPLETE' or any(_key(r)==OLD_MRQ_KEY for r in histories['MRQ'].rows):
        raise BoundaryReviewError('BOUNDARY_CANDIDATE_ABSENCE_STALE')
    if application['phase']=='PENDING' and histories['MRQ'].evidence()!=e['mrq']['absence_proof']:
        raise BoundaryReviewError('BOUNDARY_CANDIDATE_RESPONSE_STALE')


def rehearse(proposal, provider_db, canonical_db, histories, identity, output_dir):
    """Complete provider/canonical copy rehearsal. Never calls a workflow or queue."""
    from rawcandle.fundamentals.phase13b_foundation import online_backup
    from .refresh_copy_runtime import replace_provider_histories, fresh_rebuild_canonical
    from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy
    validate_pending(proposal,provider_db,canonical_db,histories,identity)
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=False)
    p,c=output_dir/'provider.db',output_dir/'canonical.db'
    online_backup(Path(provider_db),p);online_backup(Path(canonical_db),c)
    assert_inactive_copy(p);assert_inactive_copy(c)
    receipt={'proposal_fingerprint':proposal['proposal_fingerprint'],'passed':True,'mode':'COPY_ONLY','checks':{k:True for k in REHEARSAL_CHECKS}}
    receipt['receipt_fingerprint']=fingerprint(receipt)
    synthetic={'proposal':deepcopy(proposal),'status':'APPROVED','operator':'COPY_ONLY_REHEARSAL_NOT_RUNTIME_APPROVAL',
               'approved_at':utc_now(),'rehearsal':receipt,'copy_only':True}
    synthetic['decision_fingerprint']=fingerprint(synthetic)
    application=evaluate(provider_db,canonical_db,histories,identity,decision=synthetic)
    if not application.get('applied'):raise BoundaryReviewError('BOUNDARY_REHEARSAL_STALE')
    r=_refresh();current={d:r.load_current_history(Path(provider_db),'WFRD',d) for d in ('ARQ','MRQ')}
    raw=comparison('WFRD',current,histories,application)
    if raw['classification']=='REVIEW_REQUIRED':raise BoundaryReviewError('BOUNDARY_UNRESOLVED_EVENT')
    merge=r.build_source_history_merge('WFRD',current,histories)
    replaced=replace_provider_histories(p,{'WFRD':histories},{'WFRD':identity},applied_at=utc_now(),merge_plans={'WFRD':merge},boundary_applications={'WFRD':application})
    # Snapshot canonical values/identity before rebuilding, ignoring internal IDs/timestamps.
    def rows(path):
        with _ro(path) as conn:
            data=[dict(x) for x in conn.execute('SELECT q.*,f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)')]
        return {(x['company_id'],x['fiscal_year'],x['fiscal_quarter']):{k:v for k,v in x.items() if k not in ('quarter_id','created_at_utc','updated_at_utc','source_fiscalperiod')} for x in data}
    before=rows(c)
    rebuilt=fresh_rebuild_canonical(p,c,applied_at=utc_now(),affected_company_ids=[identity['company_id']])
    after=rows(c)
    # Current acquisition may independently add a new quarter; no existing value
    # is allowed to change or disappear because of this reviewed interpretation.
    if any(after.get(k)!=v for k,v in before.items()):raise BoundaryReviewError('BOUNDARY_REHEARSAL_EXISTING_QUARTER_CHANGED')
    added=[k for k in after.keys()-before.keys()]
    if any(k[0]!=identity['company_id'] for k in added):raise BoundaryReviewError('BOUNDARY_REHEARSAL_UNRELATED_TICKER_CHANGED')
    with _ro(c) as cc:
        for q in proposal['evidence']['baseline']['quarters']:
            result=_quarter(cc,identity['company_id'],q['fiscal_year'])
            if {k:v for k,v in result.items() if k!='quarter_id'}!={k:v for k,v in q.items() if k!='quarter_id'}:raise BoundaryReviewError('BOUNDARY_REHEARSAL_DATE_OR_KEY_CHANGED')
        pb=cc.execute("SELECT effective_fiscalperiod,dimension FROM v4_parent_equity_source s JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=? AND q.fiscal_year=2019 AND q.fiscal_quarter='Q4'",(identity['company_id'],)).fetchone()
        if pb is None or tuple(pb)!=('2019-Q4','ARQ'):raise BoundaryReviewError('BOUNDARY_REHEARSAL_PB_BINDING')
    validate_store(p)
    receipt={'proposal_fingerprint':proposal['proposal_fingerprint'],'passed':True,'mode':'COPY_ONLY',
             'checks':{'both_q4s':True,'established_dates':True,'no_existing_financial_change':True,
                       'unrelated_tickers':True,'historical_only_archive':True,'mrq_nonfinancial':True,'pb_arq_binding':True},
             'independent_new_quarters':[list(k) for k in sorted(added)],
             'provider_candidate':str(p),'canonical_candidate':str(c),
             'candidate_sha256':{'provider':file_fingerprint(p),'canonical':file_fingerprint(c)},
             'provider_validation':replaced['verification'],'canonical_impact':rebuilt['impact']}
    receipt['receipt_fingerprint']=fingerprint(receipt)
    return receipt


def interpretation(c,row):
    effective=effective_fiscalperiod(c,row)
    rid=None
    if effective!=row.get('fiscalperiod'):
        matches=[d['proposal']['resolution_id'] for d in _records(c,DECISIONS) if tuple(d['proposal']['evidence']['arq']['source_key'])==_key(row)]
        if len(matches)!=1:raise BoundaryReviewError('BOUNDARY_INTERPRETATION_AMBIGUOUS')
        rid=matches[0]
    return {'provider_fiscalperiod':row.get('fiscalperiod'),'effective_fiscalperiod':effective,'resolution_id':rid}


def evaluate_for_refresh(provider_db, canonical_db, histories, identity, queue_db):
    all_items=read_items(queue_db)
    if any(i['status'] in ('STALE','REJECTED') and i['proposal']['evidence']['identity']['ticker']==identity.get('ticker') for i in all_items):
        return {'applied':False,'stale':True,'reason':'BOUNDARY_REAPPROVAL_REQUIRED'}
    decision=queued_decision(queue_db,identity.get('ticker'))
    result=evaluate(provider_db,canonical_db,histories,identity,decision=decision)
    if result.get('applied') and result['decision'].get('copy_only'):
        return {'applied':False,'stale':True,'reason':'BOUNDARY_COPY_ONLY_NOT_RUNTIME_AUTHORITY'}
    if result.get('applied') or result.get('stale'):
        return result
    items=[i for i in read_items(queue_db) if i['proposal']['evidence']['identity']['ticker']==identity.get('ticker')]
    if items:
        try:
            if len(items)!=1 or items[0]['status']!='OPEN':
                raise BoundaryReviewError('BOUNDARY_REVIEW_REQUIRES_REAPPROVAL')
            validate_pending(items[0]['proposal'],provider_db,canonical_db,histories,identity)
            return {'applied':False,'stale':False,'pending':True,'proposal_fingerprint':items[0]['proposal']['proposal_fingerprint']}
        except (BoundaryReviewError,KeyError,ValueError,TypeError) as exc:
            return {'applied':False,'stale':True,'reason':str(exc)}
    return result


def comparison_authorized(application,current,histories,revisions,events):
    if not application.get('applied') or application.get('phase') not in ('PENDING','PUBLISHED'):
        return False
    validate_candidate_input(application,histories)
    e=verify_decision(application['decision'])
    if application['phase']=='PENDING':
        for dim,key,expected in (('ARQ',ARQ_KEY,e['arq']['accepted']),('MRQ',OLD_MRQ_KEY,e['mrq']['accepted'])):
            rows=[r for r in current[dim]['rows'] if _key(r)==key]
            if len(rows)!=1 or fingerprint(_row(rows[0]))!=expected['normalized_fingerprint']:
                raise BoundaryReviewError('BOUNDARY_COMPARISON_BASELINE_STALE')
    return (all(_key(r['source_identity'])==ARQ_KEY for r in revisions)
            and all(ev['event']=='AGED_OUT_OF_SOURCE_WINDOW' or
                    (ev['event']=='TRUE_SOURCE_REMOVAL' and _key(ev['source_identity'])==OLD_MRQ_KEY)
                    for ev in events))


def file_fingerprint(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def validate_rehearsal_receipt(proposal,receipt):
    """Approval requires the real, unchanged candidate artifacts, not booleans."""
    from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy
    if receipt.get('mode')!='COPY_ONLY' or set(receipt.get('candidate_sha256',{}))!={'provider','canonical'}:
        raise BoundaryReviewError('BOUNDARY_REHEARSAL_PHYSICAL_PROOF_REQUIRED')
    for role in ('provider','canonical'):
        path=Path(receipt[f'{role}_candidate'])
        assert_inactive_copy(path)
        if file_fingerprint(path)!=receipt['candidate_sha256'][role]:
            raise BoundaryReviewError('BOUNDARY_REHEARSAL_CANDIDATE_CHANGED')
    validate_store(receipt['provider_candidate'])
    with _ro(receipt['provider_candidate']) as p:
        decisions=_records(p,DECISIONS)
        if len(decisions)!=1 or decisions[0]['proposal']!=proposal or not decisions[0].get('copy_only'):
            raise BoundaryReviewError('BOUNDARY_REHEARSAL_PROPOSAL_MISMATCH')
    with _ro(receipt['canonical_candidate']) as c:
        for q in proposal['evidence']['baseline']['quarters']:
            actual=_quarter(c,proposal['evidence']['identity']['company_id'],q['fiscal_year'])
            if {k:v for k,v in actual.items() if k!='quarter_id'}!={k:v for k,v in q.items() if k!='quarter_id'}:
                raise BoundaryReviewError('BOUNDARY_REHEARSAL_PUBLICATION_MISMATCH')
    return True
