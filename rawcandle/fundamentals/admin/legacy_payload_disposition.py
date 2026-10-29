"""Ticker operating dispositions from exact source evidence, not financial policy.

The existing operational universe/security.active controls eligibility. This
small queue ledger records why; it cannot remove, reactivate or repair anything.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import sqlite3

from .contracts import utc_now
from .provider_payload import payload_fingerprint as digest

VERSION = 'FUNDAMENTALS_LEGACY_PAYLOAD_DISPOSITION_V1'
STATES = ('UNRESOLVED', 'INELIGIBLE_SOURCE_DATA', 'REPAIRABLE', 'HISTORICAL_ONLY', 'ELIGIBLE')
TABLE = 'fundamentals_source_disposition'


def decide(evidence):
    """Exactly one active ticker disposition; historical findings are separate."""
    e = evidence
    if (e.get('contradictions') or e.get('identity_exact') is not True
            or e.get('current_source_trusted') is not True
            or e.get('current_binding_known') is not True
            or e.get('current_incomplete') not in (True, False)
            or e.get('current_healthy') not in (True, False)
            or e['current_incomplete'] == e['current_healthy']):
        return 'UNRESOLVED'
    if e['current_incomplete']:
        if e.get('exact_repair_available') and e.get('unrecoverable_current_proven'):
            return 'UNRESOLVED'
        if (e.get('unrecoverable_current_proven') is True
                and e.get('authoritative_unavailability_proof')
                and e.get('exact_repair_unavailable_proven') is True):
            return 'INELIGIBLE_SOURCE_DATA'
        if (e.get('exact_repair_available') is True and e.get('native_repair_supported') is True
                and e.get('repair_evidence_fingerprint') and e.get('financial_drift') is False):
            return 'REPAIRABLE'
        return 'UNRESOLVED'
    if e.get('historical_only_count', 0) > 0:
        return 'HISTORICAL_ONLY' if e.get('historical_no_current_effect_proven') is True else 'UNRESOLVED'
    return 'ELIGIBLE'


def item(ticker, company_id, security_id, evidence, *, counts, reason, source_binding):
    if not ticker or not company_id or not security_id:
        raise ValueError('DISPOSITION_EXACT_IDENTITY_REQUIRED')
    result = dict(ticker=ticker.upper(), company_id=company_id, security_id=security_id,
        disposition=decide(evidence), reason_code=reason, evidence=evidence,
        observation_counts=counts, source_binding=source_binding)
    return {**result, 'item_fingerprint': digest(result)}


def seal(items, *, baseline, observations, evidence_reference, created_at=None):
    ordered = sorted(items, key=lambda i:i['ticker'])
    if len({i['ticker'] for i in ordered}) != len(ordered):
        raise ValueError('DISPOSITION_DUPLICATE_TICKER')
    if len({o['observation_id'] for o in observations}) != len(observations):
        raise ValueError('DISPOSITION_DUPLICATE_OBSERVATION')
    if set(o['ticker'] for o in observations) != set(i['ticker'] for i in ordered):
        raise ValueError('DISPOSITION_COHORT_MISMATCH')
    result = dict(schema=VERSION, created_at=created_at or utc_now(), baseline=baseline,
        items=ordered, observation_findings=observations, evidence_reference=evidence_reference)
    return {**result,'artifact_fingerprint':digest(result)}


def verify(artifact):
    if artifact.get('schema') != VERSION or artifact.get('artifact_fingerprint') != digest(
            {k:v for k,v in artifact.items() if k != 'artifact_fingerprint'}):
        raise ValueError('DISPOSITION_ARTIFACT_TAMPERED')
    seen=set(); observations=set()
    for row in artifact['items']:
        if (row['ticker'] in seen or row['disposition'] != decide(row['evidence'])
                or row['item_fingerprint'] != digest({k:v for k,v in row.items() if k != 'item_fingerprint'})):
            raise ValueError('DISPOSITION_ITEM_INVALID')
        seen.add(row['ticker'])
    for row in artifact['observation_findings']:
        if row['ticker'] not in seen or row['observation_id'] in observations:
            raise ValueError('DISPOSITION_OBSERVATION_INVALID')
        observations.add(row['observation_id'])
    if {o['ticker'] for o in artifact['observation_findings']} != seen:
        raise ValueError('DISPOSITION_COHORT_MISMATCH')
    return artifact


def summary(artifact):
    verify(artifact)
    # Ticker statuses partition the cohort. Observation flags can overlap and
    # are intentionally not added into the ticker counts.
    return dict(tickers=len(artifact['items']), observations=len(artifact['observation_findings']),
        dispositions={s:sum(i['disposition']==s for i in artifact['items']) for s in STATES},
        observation_categories={k:sum(bool(o.get(k)) for o in artifact['observation_findings'])
            for k in ('current_accepted_binding','frozen_accepted_binding','retained','fresh_exact_key',
                      'archive_completeness_only','repaired')})


def _schema(c):
    c.executescript(f'''CREATE TABLE IF NOT EXISTS {TABLE}(
        ticker TEXT PRIMARY KEY, company_id INTEGER NOT NULL, security_id INTEGER NOT NULL,
        disposition TEXT NOT NULL, reason_code TEXT NOT NULL, effective_at_utc TEXT NOT NULL,
        artifact_fingerprint TEXT NOT NULL, evidence_reference TEXT NOT NULL, record_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS {TABLE}_audit(
        audit_id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, occurred_at_utc TEXT NOT NULL,
        artifact_fingerprint TEXT NOT NULL, record_json TEXT NOT NULL);''')


def _write(queue_path, artifact, canonical_db):
    verify(artifact)
    with closing(sqlite3.connect(f'file:{Path(canonical_db).resolve()}?mode=ro',uri=True)) as c:
        for row in artifact['items']:
            security=c.execute('SELECT company_id,current_ticker,active FROM security WHERE security_id=?',(row['security_id'],)).fetchone()
            if security is None or security[:2] != (row['company_id'],row['ticker']):
                raise ValueError('DISPOSITION_CANONICAL_IDENTITY_DRIFT')
            if row['disposition']=='INELIGIBLE_SOURCE_DATA':
                active=c.execute('''SELECT 1 FROM fundamentals_operational_universe_member m
                    JOIN fundamentals_operational_universe_active_version a USING(universe_version_id)
                    WHERE m.company_id=? AND m.security_id=?''',(row['company_id'],row['security_id'])).fetchone()
                if security[2] or active:
                    raise ValueError('DISPOSITION_NATIVE_EXCLUSION_REQUIRED')
    with sqlite3.connect(queue_path) as c:
        _schema(c);c.execute('BEGIN IMMEDIATE')
        for row in artifact['items']:
            old=c.execute(f'SELECT record_json FROM {TABLE} WHERE ticker=?',(row['ticker'],)).fetchone()
            if old and json.loads(old[0])['item_fingerprint']==row['item_fingerprint']:
                continue
            record={**row,'effective_at_utc':artifact['created_at'],
                'artifact_fingerprint':artifact['artifact_fingerprint'],
                'evidence_reference':artifact['evidence_reference']}
            serialized=json.dumps(record,sort_keys=True)
            c.execute(f'INSERT OR REPLACE INTO {TABLE} VALUES(?,?,?,?,?,?,?,?,?)',
                (row['ticker'],row['company_id'],row['security_id'],row['disposition'],row['reason_code'],
                 artifact['created_at'],artifact['artifact_fingerprint'],artifact['evidence_reference'],serialized))
            c.execute(f'INSERT INTO {TABLE}_audit(ticker,occurred_at_utc,artifact_fingerprint,record_json) VALUES(?,?,?,?)',
                (row['ticker'],artifact['created_at'],artifact['artifact_fingerprint'],serialized))


def register(project_root, queue_path, artifact, *, authorized_artifact_fingerprint):
    """Record only a fully audited, exact-bound snapshot under existing locks."""
    from . import provider_payload_workflow as repair, publication_journal as journal
    from .artifacts import ROOT
    from rawcandle.scheduler.config import read_scheduler_config
    root=Path(project_root).resolve();queue=Path(queue_path).resolve();verify(artifact)
    if authorized_artifact_fingerprint != artifact['artifact_fingerprint']:
        raise PermissionError('DISPOSITION_EXACT_AUTHORIZATION_REQUIRED')
    if root==ROOT.resolve() and queue != (root/'fundamental_reports/fundamentals_refresh_review_queue.db').resolve():
        raise PermissionError('DISPOSITION_OPERATIONAL_QUEUE_REQUIRED')
    config=read_scheduler_config(str(root/'scheduler_config.json'))
    with repair.preflight(root,Path(config.log_dir)):
        if repair.baseline(root)!=artifact['baseline']:
            raise ValueError('DISPOSITION_BASELINE_STALE')
        roles=artifact['baseline']['roles']
        if any(row['stale'] and row['evidence'].get('current_binding_known') is True
               for row in current_views(artifact['items'],roles['canonical'],roles['provider'])):
            raise ValueError('DISPOSITION_CURRENT_BINDING_STALE')
        path=root/'fundamental_reports/source_dispositions'/f"{artifact['artifact_fingerprint']}.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and json.loads(path.read_text())!=artifact:
            raise ValueError('DISPOSITION_EVIDENCE_CONFLICT')
        if not path.exists():journal._atomic_json(path,artifact)
        _write(queue,artifact,Path(artifact['baseline']['roles']['canonical']))
    return summary(artifact)


def list_items(queue_path):
    path=Path(queue_path)
    if not path.exists():return []
    with closing(sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():return []
        rows=[json.loads(r[0]) for r in c.execute(f'SELECT record_json FROM {TABLE} ORDER BY ticker')]
    for row in rows:
        body={k:v for k,v in row.items() if k not in ('item_fingerprint','effective_at_utc','artifact_fingerprint','evidence_reference')}
        if row['disposition'] != decide(row['evidence']) or row['item_fingerprint']!=digest(body):
            raise ValueError('DISPOSITION_STORED_EVIDENCE_TAMPERED')
    return rows


def presentation(row):
    status='UNRESOLVED' if row.get('stale') else row['disposition']
    label,action={
        'ELIGIBLE':('Fundamentals eligible','Normal processing allowed by the existing universe and native policies.'),
        'REPAIRABLE':('Source repair available','Use the existing exact-source repair workflow; this does not approve ownership.'),
        'HISTORICAL_ONLY':('Historical evidence retained — no current action','No historical repair required for current operation.'),
        'INELIGIBLE_SOURCE_DATA':('Fundamentals ineligible','No automatic Fundamentals processing. Review only if you want to restore this ticker.'),
        'UNRESOLVED':('Source-data disposition unresolved','Inspect source/version evidence before repair or exclusion.'),
    }[status]
    counts=row.get('observation_counts') or {}
    return dict(label=label,next_action=action,needs_action=status in ('REPAIRABLE','UNRESOLVED'),
        lines=(f"{row['ticker']} · {label}",
            'Classification: '+('Insufficient reliable source data' if status=='INELIGIBLE_SOURCE_DATA' else status.replace('_',' ').capitalize()),
            f"Reason: {'CURRENT_BINDING_CHANGED_REEVALUATE' if row.get('stale') else row['reason_code']}",
            f"Legacy observations: {counts.get('legacy',0)} · frozen accepted rows: {counts.get('frozen',0)} · retained: {counts.get('retained',0)}",
            f"Next action: {action}",f"Evidence: {row.get('artifact_fingerprint') or row.get('item_fingerprint')}"))


def current_views(rows, canonical_db, provider_db):
    """Read-only invalidation: a stored disposition never authorizes new facts."""
    if not rows:return []
    with closing(sqlite3.connect(f'file:{Path(canonical_db).resolve()}?mode=ro',uri=True)) as c, closing(
            sqlite3.connect(f'file:{Path(provider_db).resolve()}?mode=ro',uri=True)) as p:
        result=[]
        for row in rows:
            binding=row['source_binding']
            latest=c.execute('''SELECT q.fiscal_year,q.fiscal_quarter,p.provider_observation_id
                FROM v4_quarter q LEFT JOIN v4_field_provenance p ON p.quarter_id=q.quarter_id
                AND p.canonical_field='shares_outstanding' WHERE q.company_id=?
                AND q.identity_status='ACCEPTED' ORDER BY q.fiscal_year DESC,q.fiscal_quarter DESC LIMIT 1''',
                (row['company_id'],)).fetchone()
            obs=p.execute('SELECT content_hash,payload_json FROM provider_observation WHERE observation_id=?',
                          (binding.get('observation_id'),)).fetchone()
            stale=(latest != (binding.get('fiscal_year'),binding.get('fiscal_quarter'),binding.get('observation_id'))
                or obs is None or obs[0]!=binding.get('content_hash') or digest(json.loads(obs[1]))!=binding.get('payload_fingerprint'))
            result.append({**row,'stale':stale})
    return result
