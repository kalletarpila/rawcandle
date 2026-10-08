"""Quarterly ownership cases in the operational Review Queue; no live DB writes.

This bounded typed table shares the queue's audit log. Its observation case key
avoids overwriting ticker-keyed provider/publication reviews or old Q history.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from rawcandle.fundamentals.admin.contracts import fingerprint, utc_now
from rawcandle.fundamentals.admin.artifacts import sha256_file
from rawcandle.fundamentals.ownership_basis import BINDING, QUARTERLY_OWNERSHIP_CONTRACT
from rawcandle.fundamentals.pb_reporting_contract import (
    TABLE, ARTIFACT_TABLE, generation_ownership_artifact, reporting_ownership_contract,
)
from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy, finite

REVIEW_TYPE = 'PB_OWNERSHIP_NEW_QUARTER'
CASE_TABLE = 'pb_ownership_review'
COMMON = {'Domestic Common Stock', 'Canadian Common Stock', 'Domestic Common Stock Primary Class', 'Canadian Common Stock Primary Class'}
SCHEMA = f'''CREATE TABLE IF NOT EXISTS {CASE_TABLE} (
    case_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, company_id INTEGER NOT NULL,
    candidate_hash TEXT NOT NULL, candidate_json TEXT NOT NULL, status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, run_id TEXT NOT NULL,
    approval_json TEXT, result_json TEXT);
'''


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def serialize(artifact: dict) -> str:
    return json.dumps(artifact, sort_keys=True, indent=2, allow_nan=False) + '\n'


def latest_basis(conn: sqlite3.Connection, company_id: int, *, as_of: str) -> dict | None:
    row = conn.execute('''SELECT q.company_id,c.company_key,q.fiscal_year,q.fiscal_quarter,
        q.source_reportperiod AS reportperiod, f.parent_equity,f.parent_equity_usd,f.shares_outstanding,
        s.observation_id,s.content_hash,s.provider_date,s.source_availability_date,s.category,
        s.sharesbas,s.sharefactor,s.price,s.marketcap,s.pb,s.dimension,s.shareswa,
        p.provider_observation_id AS shares_provenance_observation_id
        FROM v4_quarter q JOIN company c USING(company_id)
        JOIN v4_quarter_financials f USING(quarter_id)
        LEFT JOIN v4_parent_equity_source s ON s.quarter_id=q.quarter_id AND EXISTS (
          SELECT 1 FROM v4_field_provenance fp WHERE fp.quarter_id=q.quarter_id
          AND fp.canonical_field='shares_outstanding' AND fp.provider_observation_id=s.observation_id)
        LEFT JOIN v4_field_provenance p ON p.quarter_id=q.quarter_id AND p.canonical_field='shares_outstanding'
          AND p.provider_observation_id=s.observation_id
        WHERE q.company_id=? AND q.identity_status='ACCEPTED' AND q.source_availability_date<=?
          AND (s.source_availability_date IS NULL OR s.source_availability_date<=?)
        ORDER BY q.fiscal_year DESC,q.fiscal_quarter DESC LIMIT 1''', (company_id,as_of,as_of)).fetchone()
    if row is None:
        return None
    result = dict(row)
    securities = [dict(r) for r in conn.execute('''SELECT security_id,current_ticker AS canonical_ticker,
        valid_from AS security_valid_from,valid_to AS security_valid_to FROM security
        WHERE company_id=? AND active=1 ORDER BY security_id''', (company_id,))]
    result['active_securities'] = securities
    result['active_classes'] = len(securities)
    if len(securities) == 1:
        result.update(securities[0])
        result['security_active_as_of'] = (not result['security_valid_from'] or result['security_valid_from'] <= as_of) and (not result['security_valid_to'] or result['security_valid_to'] >= as_of)
    return result


def _classify(previous: dict, new: dict) -> str:
    if new['active_classes'] > 1 or new.get('class_or_perimeter_conflict'):
        return 'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE'
    if any(previous[k] != new.get(k) for k in BINDING[:4]) or not new.get('security_active_as_of'):
        return 'REVIEW_REQUIRED_IDENTITY_CHANGE'
    if (new['active_classes'] != 1 or new.get('class_or_perimeter_conflict')):
        return 'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE'
    shares = finite(new.get('sharesbas'))
    if (shares is None or shares <= 0 or shares != finite(new.get('shares_outstanding'))
        or new.get('shares_provenance_observation_id') != new.get('observation_id')
        or not new.get('observation_id') or not new.get('content_hash')):
        return 'REVIEW_REQUIRED_INVALID_SHARE_BASIS'
    if new.get('sharefactor') != previous['provider_declared_factor']:
        return 'REVIEW_REQUIRED_FACTOR_CHANGE'
    category = new.get('category')
    compatible = category == previous['accepted_category'] or (
        previous['economic_unit_rule'] == 'ORDINARY_COMMON' and category in COMMON) or (previous.get('identity_override') is True and category in COMMON)
    if not compatible:
        return 'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE'
    if (not new.get('provider_date') or not new.get('source_availability_date')
        or new.get('newer_share_count_required') or previous.get('known_share_changes')):
        return 'REVIEW_REQUIRED_OTHER'
    return 'CONTINUATION_CANDIDATE'


def detect(conn: sqlite3.Connection, *, as_of: str) -> list[dict]:
    if reporting_ownership_contract(conn, as_of=as_of) != QUARTERLY_OWNERSHIP_CONTRACT:
        return []
    artifact, version = generation_ownership_artifact(conn)
    supported = [r for r in artifact['records'] if r['evidence_status'] == 'REVIEWED_SUPPORTED']
    companies = sorted({r['company_id'] for r in supported})
    cases = []
    for company_id in companies:
        reviews = [r for r in supported if r['company_id'] == company_id and r['valid_from_as_of'] <= as_of]
        if not reviews:
            continue
        new = latest_basis(conn, company_id, as_of=as_of)
        if not new:
            continue
        binding = (*BINDING, 'fiscal_year', 'fiscal_quarter', 'reportperiod')
        if any(all(new.get(k) == r.get(k) for k in binding) for r in reviews):
            continue
        prior = max(reviews, key=lambda r:(r['fiscal_year'],r['fiscal_quarter'],r['reviewed_at'],fingerprint(r)))
        previous = {**deepcopy(prior), 'parent_equity': prior.get('parent_equity'), 'parent_equity_usd': prior.get('parent_equity_usd')}
        old_equity = conn.execute('''SELECT f.parent_equity,f.parent_equity_usd FROM v4_parent_equity_source s
            JOIN v4_quarter_financials f USING(quarter_id) JOIN v4_quarter q USING(quarter_id)
            WHERE q.company_id=? AND s.observation_id=? AND s.content_hash=?''',
            (company_id,prior['observation_id'],prior['content_hash'])).fetchone()
        if old_equity:
            previous.update(dict(old_equity))
        old_shares, new_shares = finite(prior['accepted_sharesbas']), finite(new.get('sharesbas'))
        old_parent, new_parent = finite(previous.get('parent_equity_usd')), finite(new.get('parent_equity_usd'))
        ratio = (prior['exact_factor_numerator']/prior['exact_factor_denominator']
                 if prior['economic_unit_rule']=='ADS_EQUIVALENTS' else 1)
        case = dict(review_type=REVIEW_TYPE,company_id=company_id,company_key=new['company_key'],
            ticker=new.get('canonical_ticker',prior['canonical_ticker']),security_id=new.get('security_id'),
            registry_sha256=version,prior_review_hash=fingerprint(prior),prior_review_reference=prior['evidence_reference'],
            previous=previous,new=new,classification=_classify(prior,new),
            hypothetical_economic_units=new_shares*ratio if new_shares is not None else None,
            current_pb_status='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED',
            recommended_action='Inspect quarterly basis and explicitly approve continuation, or keep on hold',
            deltas=dict(shares_absolute=new_shares-old_shares if old_shares is not None and new_shares is not None else None,
                shares_percent=100*(new_shares/old_shares-1) if old_shares and new_shares is not None else None,
                provider_factor_changed=new.get('sharefactor')!=prior['provider_declared_factor'],
                category_changed=new.get('category')!=prior['accepted_category'],
                identity_changed=any(new.get(k)!=prior[k] for k in BINDING[:4]),
                quarter_changed=(new['fiscal_year'],new['fiscal_quarter'],new['reportperiod'])!=(prior['fiscal_year'],prior['fiscal_quarter'],prior['reportperiod']),
                parent_equity_change=new_parent-old_parent if old_parent is not None and new_parent is not None else None,
                provenance_changed=new.get('shares_provenance_observation_id')!=prior['observation_id']))
        case['case_id'] = fingerprint({k:case[k] for k in ('company_id',)} | {k:new.get(k) for k in ('observation_id','content_hash','fiscal_year','fiscal_quarter','reportperiod')})
        case['candidate_hash'] = fingerprint(case)
        cases.append(case)
    return cases


def _audit(conn, case, event, run_id, evidence):
    conn.execute('''INSERT INTO refresh_review_queue_audit(ticker,event_type,occurred_at_utc,run_id,evidence_json)
        VALUES(?,?,?,?,?)''',(case['ticker'],'PB_OWNERSHIP_'+event,utc_now(),run_id,
                             json.dumps({'case_id':case['case_id'],**evidence},sort_keys=True)))


def sync(queue_path: Path, canonical_db: Path, *, as_of: str, run_id: str) -> dict:
    from rawcandle.fundamentals.admin.refresh_review_queue import _connect
    with _ro(canonical_db) as canonical:
        if reporting_ownership_contract(canonical, as_of=as_of) != QUARTERLY_OWNERSHIP_CONTRACT:
            return {'candidate_count':0,'created':0}
        cases = detect(canonical, as_of=as_of)
    if not cases and not queue_path.exists():
        return {'candidate_count':0,'created':0}
    from .pb_ownership_publication import synchronize
    synchronize(queue_path,canonical_db)
    created = 0
    with _connect(queue_path) as conn:
        conn.executescript(SCHEMA);conn.execute('BEGIN IMMEDIATE')
        for case in cases:
            prior = conn.execute(f'SELECT * FROM {CASE_TABLE} WHERE case_id=?',(case['case_id'],)).fetchone()
            if prior is None:
                now=utc_now();conn.execute(f'INSERT INTO {CASE_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (case['case_id'],case['ticker'],case['company_id'],case['candidate_hash'],json.dumps(case,sort_keys=True),
                     'OPEN',now,now,run_id,None,None));created+=1;_audit(conn,case,'CREATED',run_id,case)
            elif prior['candidate_hash']!=case['candidate_hash'] and prior['status'] in ('OPEN','HELD'):
                conn.execute(f"UPDATE {CASE_TABLE} SET candidate_hash=?,candidate_json=?,status='OPEN',last_seen_at=?,run_id=? WHERE case_id=?",
                    (case['candidate_hash'],json.dumps(case,sort_keys=True),utc_now(),run_id,case['case_id']))
                _audit(conn,case,'UPDATED',run_id,case)
        # Historical cases remain visible; completed postflight receipts consume exact approvals above.
        for row in conn.execute(f"SELECT * FROM {CASE_TABLE} WHERE status IN ('OPEN','HELD','APPROVED')").fetchall():
            case=json.loads(row['candidate_json'])
            if row['status'] in ('OPEN','HELD') and any(c['company_id']==row['company_id'] and c['case_id']!=row['case_id'] for c in cases):
                conn.execute(f"UPDATE {CASE_TABLE} SET status='SUPERSEDED' WHERE case_id=?",(row['case_id'],));_audit(conn,case,'SUPERSEDED',run_id,{})
    return {'candidate_count':len(cases),'created':created}


def list_cases(queue_path: Path, *, include_resolved: bool=False) -> list[dict]:
    if not queue_path.exists():
        return []
    with _ro(queue_path) as conn:
        if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?',(CASE_TABLE,)).fetchone():
            return []
        rows=conn.execute(f'SELECT * FROM {CASE_TABLE} ORDER BY ticker,first_seen_at,case_id').fetchall()
    result=[]
    for row in rows:
        if not include_resolved and row['status'] not in ('OPEN','HELD','APPROVED'):
            continue
        case=json.loads(row['candidate_json']);case.update(status=row['status'],approval=json.loads(row['approval_json']) if row['approval_json'] else None,
                                                         result=json.loads(row['result_json']) if row['result_json'] else None)
        result.append(case)
    return result


def _current(conn: sqlite3.Connection, case: dict, *, as_of: str) -> dict:
    matches=[c for c in detect(conn,as_of=as_of) if c['case_id']==case['case_id']]
    if len(matches)!=1 or matches[0]['candidate_hash']!=case['candidate_hash']:
        raise ValueError('PB_OWNERSHIP_STALE_CANDIDATE')
    return matches[0]


def proposed_record(case: dict, *, approved_at: str, operator: str, note: str) -> dict:
    r=deepcopy(case['previous']);new=case['new']
    r.update({k:new[k] for k in (*BINDING,'fiscal_year','fiscal_quarter','reportperiod')})
    r.update(accepted_sharesbas=new['sharesbas'],provider_declared_factor=new['sharefactor'],accepted_category=new['category'],
        accepted_provider_date=new['provider_date'],accepted_source_availability_date=new['source_availability_date'],
        share_source_date=new['provider_date'],share_source_date_basis='ACCEPTED_PROVIDER_DATE_QUARTERLY_REVIEW',
        unit_effective_from=new['provider_date'],valid_from_as_of=approved_at[:10],reviewed_at=approved_at,
        review_version='PB.12_OPERATOR_NEW_QUARTER_V2',approval_mode='OPERATOR_CONFIRMED',
        evidence_reference=REVIEW_TYPE+':'+case['case_id'],prior_review_hash=case['prior_review_hash'],
        prior_evidence_reference=case['prior_review_reference'],operator=operator,operator_note=note,
        parent_equity=new['parent_equity'],parent_equity_usd=new['parent_equity_usd'])
    return r


def preview(case: dict, canonical_db: Path, market_db: Path, *, as_of: str) -> dict:
    from rawcandle.fundamentals.book_value import book_value_report,current_pb
    with _ro(canonical_db) as c, _ro(market_db) as m:
        c.execute('BEGIN');case=_current(c,case,as_of=as_of)
        held=book_value_report(c,m,company_id=case['company_id'],ticker=case['ticker'],as_of=as_of)
        row=deepcopy(case['new'])
        witness=m.execute("SELECT close FROM osakedata WHERE osake=? AND pvm=? AND market='usa'",(case['ticker'],row['provider_date'])).fetchone()
        row['provider_date_market_close']=witness['close'] if witness else None
        proposed=proposed_record(case,approved_at=as_of+'T00:00:00Z',operator='HYPOTHETICAL',note='Preview only')
        artifact,_=generation_ownership_artifact(c)
        previous_row=deepcopy(case['previous'])
        previous_row.update(sharesbas=previous_row['accepted_sharesbas'], sharefactor=previous_row['provider_declared_factor'],
            provider_date=previous_row['accepted_provider_date'], source_availability_date=previous_row['accepted_source_availability_date'],
            category=previous_row['accepted_category'], shares_outstanding=previous_row['accepted_sharesbas'])
        prior_reference_as_of=case['previous']['valid_from_as_of']
        previous_price=m.execute("SELECT pvm,close FROM osakedata WHERE osake=? AND market='usa' AND pvm<=? ORDER BY pvm DESC LIMIT 1",
            (case['ticker'],prior_reference_as_of)).fetchone()
        previous_current=current_pb(previous_row,as_of=prior_reference_as_of,price=dict(previous_price) if previous_price else None,
            category=previous_row['category'],active_classes=1,ownership_contract=QUARTERLY_OWNERSHIP_CONTRACT,review_records=tuple(artifact['records']))
        hypothetical=current_pb(row,as_of=as_of,price={'pvm':held['current']['price_date'],'close':held['current']['price']} if held['current']['price_date'] else None,
            category=row['category'],active_classes=row['active_classes'],ownership_contract=QUARTERLY_OWNERSHIP_CONTRACT,
            review_records=tuple([*artifact['records'],proposed])) if case['classification']=='CONTINUATION_CANDIDATE' else None
    return {'label':'HYPOTHETICAL_NOT_APPROVED','case_id':case['case_id'],'candidate_hash':case['candidate_hash'],
        'prior_current_reference':previous_current,'prior_reference_as_of':prior_reference_as_of,'prior_reference_price_date':previous_price['pvm'] if previous_price else None,
        'held_current':held['current'],'hypothetical_current':hypothetical,'provider':held['provider'],'history':held['history']}


def approve(queue_path: Path, case_id: str, *, candidate_hash: str, canonical_db: Path, market_db: Path,
            output_root: Path, as_of: str, operator: str, note: str, confirmed: bool=False) -> dict:
    """Write approved operational evidence and an inactive rehearsal only; never publish."""
    from rawcandle.fundamentals.admin.refresh_review_queue import _connect
    from rawcandle.fundamentals.book_value import book_value_report
    if confirmed is not True or not operator.strip() or not note.strip():
        raise PermissionError('PB_OWNERSHIP_EXPLICIT_CONFIRMATION_REQUIRED')
    with _connect(queue_path) as queue, _ro(canonical_db) as source:
        queue.executescript(SCHEMA);queue.execute('BEGIN IMMEDIATE');source.execute('BEGIN')
        row=queue.execute(f'SELECT * FROM {CASE_TABLE} WHERE case_id=?',(case_id,)).fetchone()
        if row is None or row['status']!='OPEN':
            raise ValueError('PB_OWNERSHIP_REVIEW_NOT_OPEN')
        if candidate_hash!=row['candidate_hash']:
            raise ValueError('PB_OWNERSHIP_STALE_CANDIDATE')
        case=_current(source,json.loads(row['candidate_json']),as_of=as_of)
        if case['classification']!='CONTINUATION_CANDIDATE':
            raise ValueError('PB_OWNERSHIP_MANUAL_EVIDENCE_REVIEW_REQUIRED')
        effect=preview(case,canonical_db,market_db,as_of=as_of)
        record=proposed_record(case,approved_at=utc_now(),operator=operator.strip(),note=note.strip())
        if record['reviewed_at'][:10]>as_of:
            raise ValueError('PB_OWNERSHIP_APPROVAL_DATE_AFTER_AS_OF')
        artifact,old_sha=generation_ownership_artifact(source);old_records=deepcopy(artifact['records'])
        previous_approvals=[json.loads(r[0])['record'] for r in queue.execute(f"SELECT approval_json FROM {CASE_TABLE} WHERE status IN ('APPROVED','PUBLISHED') ORDER BY first_seen_at,case_id")]
        supported_scopes = {(r['company_id'], r['company_key'], r['security_id'], r['canonical_ticker'])
                            for r in old_records if r['evidence_status']=='REVIEWED_SUPPORTED'}
        for r in [*previous_approvals,record]:
            if tuple(r[k] for k in BINDING[:4]) not in supported_scopes:
                raise ValueError('PB_OWNERSHIP_UNSUPPORTED_SCOPE')
            if r in artifact['records']:
                continue
            binding=(*BINDING,'fiscal_year','fiscal_quarter','reportperiod')
            if any(all(existing.get(k)==r.get(k) for k in binding) for existing in artifact['records']):
                raise ValueError('PB_OWNERSHIP_DUPLICATE_REVIEW_BINDING')
            artifact['records'].append(r)
        assert artifact['records'][:len(old_records)]==old_records
        payload=serialize(artifact);new_sha=hashlib.sha256(payload.encode()).hexdigest()
        # The output lane is content-bound and created exclusively; existing files are never overwritten.
        lane=output_root/case_id/new_sha;lane.mkdir(parents=True,exist_ok=False)
        candidate=lane/'canonical.db';export=lane/f'ownership_reviews_v2.{new_sha}.json'
        try:
            with sqlite3.connect(candidate) as destination:source.backup(destination)
            assert_inactive_copy(candidate)
            with sqlite3.connect(candidate) as c:
                c.execute('BEGIN IMMEDIATE')
                pinned=c.execute(f'SELECT review_artifact_sha256 FROM {TABLE} WHERE singleton=1').fetchone()[0]
                if pinned!=old_sha:
                    raise ValueError('PB_OWNERSHIP_REGISTRY_VERSION_CHANGED')
                c.execute(f'CREATE TABLE IF NOT EXISTS {ARTIFACT_TABLE}(singleton INTEGER PRIMARY KEY CHECK(singleton=1),artifact_json TEXT NOT NULL)')
                c.execute(f'INSERT OR REPLACE INTO {ARTIFACT_TABLE} VALUES(1,?)',(payload,))
                c.execute(f'UPDATE {TABLE} SET review_artifact_sha256=? WHERE singleton=1',(new_sha,))
            export.write_text(payload)
            with _ro(candidate) as c,_ro(market_db) as m:
                after=book_value_report(c,m,company_id=case['company_id'],ticker=case['ticker'],as_of=as_of)
            assert after['provider']==effect['provider'] and after['history']==effect['history']
            assert after['current']['reason']==effect['hypothetical_current']['reason']
            assert after['current']['value']==effect['hypothetical_current']['value']
            result={'case_id':case_id,'status':'APPROVED_PENDING_PUBLICATION','candidate_canonical':str(candidate.resolve()),
                'registry_artifact':str(export.resolve()),'registry_sha256':new_sha,'previous_registry_sha256':old_sha,
                'source_canonical_sha256':sha256_file(canonical_db),
                'current':after['current'],'publication_required':True}
            approval={'record':record,'candidate_hash':candidate_hash,'approved_at':record['reviewed_at'],'operator':operator.strip(),'note':note.strip()}
            queue.execute(f"UPDATE {CASE_TABLE} SET status='APPROVED',approval_json=?,result_json=? WHERE case_id=?",
                (json.dumps(approval,sort_keys=True),json.dumps(result,sort_keys=True),case_id))
            _audit(queue,case,'APPROVED',None,approval)
        except BaseException:
            shutil.rmtree(lane,ignore_errors=True)
            raise
    return result


def keep_on_hold(queue_path: Path, case_id: str, *, candidate_hash: str, note: str) -> None:
    from rawcandle.fundamentals.admin.refresh_review_queue import _connect
    if not note.strip():
        raise ValueError('PB_OWNERSHIP_HOLD_NOTE_REQUIRED')
    with _connect(queue_path) as conn:
        conn.executescript(SCHEMA);conn.execute('BEGIN IMMEDIATE')
        row=conn.execute(f'SELECT * FROM {CASE_TABLE} WHERE case_id=?',(case_id,)).fetchone()
        if row is None or row['status'] not in ('OPEN','HELD') or row['candidate_hash']!=candidate_hash:
            raise ValueError('PB_OWNERSHIP_STALE_CANDIDATE')
        if row['status']=='HELD':
            return
        case=json.loads(row['candidate_json']);conn.execute(f"UPDATE {CASE_TABLE} SET status='HELD',result_json=? WHERE case_id=?",(json.dumps({'note':note}),case_id))
        _audit(conn,case,'HELD',None,{'note':note})
