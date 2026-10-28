"""Receipt-bound source repairs, separate from ownership and valuation approval.

Stage one creates candidates and typed OPEN items. Stage two requires an exact
explicit batch authorization and uses the existing immutable-generation journal.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from . import provider_payload as payload
from . import publication_journal as journal
from .contracts import utc_now
from .pb_ownership_review import _ro
from .refresh_fundamentals import (
    fetch_complete_history, load_current_history, resolve_identity,
    semantic_row_fingerprints, source_key,
)
from rawcandle.fundamentals.generations import resolve_active_generation, active_manifest_path
from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy, accept_parent_equity
from rawcandle.fundamentals.pb_reporting_contract import generation_ownership_artifact

PROPOSAL = 'PROVIDER_PAYLOAD_COMPLETENESS_REPAIR_V1'
RECEIPT = 'PROVIDER_PAYLOAD_COMPLETENESS_REHEARSAL_V1'
BINDING = 'PROVIDER_PAYLOAD_COMPLETENESS_RECEIPT_BINDING_V1'
ITEM = 'PROVIDER_PAYLOAD_COMPLETENESS_REPAIR_ITEM_V1'
BATCH = 'PROVIDER_PAYLOAD_COMPLETENESS_BATCH_V1'
OPERATION = 'REPAIR_PROVIDER_PAYLOAD_COMPLETENESS'
TABLE = 'provider_payload_repair_review'
STATES = {'OPEN', 'APPROVED', 'REJECTED', 'STALE'}
_PREFLIGHT = ContextVar('provider_payload_repair_preflight', default=None)
CODE = tuple(Path(__file__).with_name(name) for name in (
    'provider_payload_workflow.py', 'provider_payload.py', 'refresh_fundamentals.py',
    'publication_journal.py', 'production_transaction.py', 'pb_ownership_review.py',
)) + tuple(Path(__file__).parents[1] / name for name in (
    'book_value.py', 'ownership_basis.py', 'pb_reporting_contract.py',
    'schema/parent_equity.py', 'generations.py', 'ownership_reviews_v1.json', 'ownership_reviews_v2.json',
))
ASSERTIONS = (
    'exact_replacement', 'full_payload_matches', 'financial_values_unchanged',
    'completeness_matches', 'no_duplicate_keys', 'unrelated_provider_unchanged',
    'unrelated_canonical_unchanged', 'ownership_artifact_unchanged',
    'quick_check', 'foreign_key_check', 'integrity_check', 'no_ownership_or_pb_approval',
)


def digest(value):
    return payload.payload_fingerprint(value)


def _seal(value, field):
    return {**value, field: digest(value)}


def _verify(value, schema, field):
    if not isinstance(value, dict) or value.get('schema') != schema:
        raise ValueError('PAYLOAD_WORKFLOW_SCHEMA_INVALID')
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise ValueError('PAYLOAD_WORKFLOW_FINGERPRINT_INVALID')


def baseline(project_root: Path) -> dict:
    active = resolve_active_generation(project_root, require_generation=True)
    roles = active.role_paths()
    from .production_transaction import _no_sidecars
    for path in roles.values():
        _no_sidecars(path)
    hashes = {role: journal.sha256_file(path) for role, path in roles.items()}
    if any(hashes[role] != active.manifest['role_verification'][role]['sha256'] for role in roles):
        raise ValueError('PAYLOAD_WORKFLOW_ACTIVE_HASH_MISMATCH')
    market = project_root / 'data/osakedata.db'
    with _ro(roles['provider']) as c:
        watermark = None
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='sharadar_refresh_state'").fetchone():
            row = c.execute('SELECT published_source_watermark FROM sharadar_refresh_state WHERE singleton_id=1').fetchone()
            watermark = row[0] if row else None
    return {'generation_id': active.generation_id,
            'manifest_sha256': journal.sha256_file(active_manifest_path(project_root)),
            'roles': {k: str(v) for k, v in roles.items()}, 'role_hashes': hashes,
            'market': str(market), 'market_sha256': journal.sha256_file(market),
            'watermark': watermark,
            'scheduler_sha256': journal.sha256_file(project_root / 'scheduler_config.json')
                if (project_root / 'scheduler_config.json').exists() else None,
            'code': {str(path): journal.sha256_file(path) for path in CODE}}


@contextmanager
def preflight(project_root: Path, scheduler_log_dir: Path):
    """Read-open existing kernel locks; never perform recovery or write owners."""
    from rawcandle.scheduler.runner import scheduler_lock_path
    from rawcandle.datacenter_taxonomy_operation_log import inspect_taxonomy_operation_lock
    key = (str(project_root.resolve()), str(scheduler_log_dir.resolve()))
    if _PREFLIGHT.get() == key:
        yield
        return
    if inspect_taxonomy_operation_lock()['lock_active']:
        raise ValueError('PAYLOAD_WORKFLOW_TAXONOMY_OPERATION_ACTIVE')
    with ExitStack() as stack:
        for path in (project_root / 'fundamental_reports/.fundamentals_admin_ui_operation.lock',
                     project_root / 'temp/.fundamentals_admin_production.lock',
                     Path(scheduler_lock_path(str(scheduler_log_dir)))):
            fd = stack.enter_context(path.open('r'))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if journal.safety_status(project_root / 'data/.fundamentals_admin_publication_journal.json')['production_writes_blocked']:
            raise ValueError('PAYLOAD_WORKFLOW_RECOVERY_REQUIRED')
        token = _PREFLIGHT.set(key)
        try:
            yield
        finally:
            _PREFLIGHT.reset(token)


def proposal(project_root: Path, key: tuple[str, str, str, str], history, *, fetched_at_utc: str,
             source_baseline: dict | None = None) -> dict:
    base = source_baseline or baseline(project_root)
    if history.status != 'COMPLETE' or history.ticker != key[0] or history.dimension != key[1]:
        raise ValueError('PAYLOAD_WORKFLOW_COMPLETE_SOURCE_REQUIRED')
    if datetime.fromisoformat(fetched_at_utc.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('PAYLOAD_WORKFLOW_FETCH_TIME_REQUIRED')
    current = load_current_history(Path(base['roles']['provider']), key[0], key[1])
    if current['invalid_rows'] or current['legacy_source_version_ambiguities']:
        raise ValueError('PAYLOAD_WORKFLOW_AMBIGUOUS_STORED_SOURCE')
    old = [row for row in current['rows'] if source_key(row) == key]
    new = [row for row in history.rows if source_key(row) == key]
    if len(old) != 1 or len(new) != 1:
        raise ValueError('PAYLOAD_WORKFLOW_EXACT_UNIQUE_KEY_REQUIRED')
    old, new = old[0], new[0]
    from types import SimpleNamespace
    identity = resolve_identity(SimpleNamespace(provider_db=Path(base['roles']['provider']),
                                               canonical_db=Path(base['roles']['canonical'])), key[0])
    stored = old.get('_provider_identity') or {}
    if (identity.get('status') != 'KNOWN' or not identity.get('company_key')
        or any(not stored.get(k) or identity.get(k) != stored[k]
               for k in ('company_id', 'security_id', 'provider_security_id'))):
        raise ValueError('PAYLOAD_WORKFLOW_IDENTITY_MISMATCH')
    comparison = payload.compare_payload(old, new)
    if not comparison or comparison['reason'] != payload.REPAIR:
        raise ValueError('PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR')
    if not comparison['old_observation_id'] or not comparison['old_content_hash']:
        raise ValueError('PAYLOAD_WORKFLOW_OLD_IDENTITY_MISSING')
    value = {'schema': PROPOSAL, 'ticker': key[0], 'source_key': list(key),
             'identity': identity, 'provider': 'SHARADAR', 'source': 'fundamentals',
             'comparison': comparison, 'financial_fingerprints': semantic_row_fingerprints(new),
             'fresh_factor': new['_acquisition_payload'].get('sharefactor'),
             'source_fetch_timestamp': fetched_at_utc, 'baseline': base,
             'status': 'PROPOSED', 'stale': False, 'live_repair_authorized': False,
             'ownership_authorized': False, 'pb_authorized': False}
    value = _seal(value, 'proposal_fingerprint')
    return {'repair_id': 'ppr_' + value['proposal_fingerprint'], **value}


def validate_proposal(item):
    body = {k: v for k, v in item.items() if k != 'repair_id'}
    _verify(body, PROPOSAL, 'proposal_fingerprint')
    if (item.get('repair_id') != 'ppr_' + item['proposal_fingerprint']
        or item.get('status') != 'PROPOSED' or item.get('stale') is not False
        or any(item.get(k) is not False for k in ('live_repair_authorized', 'ownership_authorized', 'pb_authorized'))
        or item['comparison'].get('reason') != payload.REPAIR
        or item['comparison'].get('financial_fields_changed') is not False):
        raise ValueError('PAYLOAD_WORKFLOW_PROPOSAL_INVALID')


def revalidate(project_root: Path, item: dict, history, *, source_baseline: dict | None = None):
    validate_proposal(item)
    base = source_baseline or baseline(project_root)
    if base != item['baseline']:
        raise ValueError('PAYLOAD_WORKFLOW_STALE_BASELINE')
    rebuilt = proposal(project_root, tuple(item['source_key']), history,
                       fetched_at_utc=item['source_fetch_timestamp'], source_baseline=base)
    if rebuilt != item:
        raise ValueError('PAYLOAD_WORKFLOW_STALE_SOURCE')


def batch(proposals):
    if not proposals:
        raise ValueError('PAYLOAD_WORKFLOW_EMPTY_BATCH')
    for item in proposals:
        validate_proposal(item)
    ordered = sorted(proposals, key=lambda p: p['repair_id'])
    if (len({tuple(p['source_key']) for p in ordered}) != len(ordered)
        or len({p['identity']['company_id'] for p in ordered}) != len(ordered)
        or any(p['baseline'] != ordered[0]['baseline'] for p in ordered)):
        raise ValueError('PAYLOAD_WORKFLOW_BATCH_CONFLICT')
    return _seal({'schema': BATCH, 'proposals': [p['proposal_fingerprint'] for p in ordered],
                  'source_keys': [p['source_key'] for p in ordered],
                  'baseline_generation': ordered[0]['baseline']['generation_id']}, 'batch_fingerprint')


def _table_digest(c, table, where='', args=()):
    quoted = '"' + table.replace('"', '""') + '"'
    columns = [r['name'] for r in c.execute(f'PRAGMA table_info({quoted})')]
    order = ','.join('"' + name.replace('"', '""') + '"' for name in columns)
    h = hashlib.sha256()
    for row in c.execute(f'SELECT * FROM {quoted} {where} ORDER BY {order}', args):
        data = repr(tuple(row)).encode(); h.update(len(data).to_bytes(8, 'big')); h.update(data)
    return h.hexdigest()


def _content(path, *, exclude_ids=(), quarter_ids=()):
    with _ro(path) as c:
        result = {}
        for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if table == 'sqlite_sequence':
                continue  # selected projection inserts may advance its own sequence
            where, args = '', ()
            if table in ('provider_observation', 'sharadar_fundamental_observation') and exclude_ids:
                where, args = 'WHERE observation_id NOT IN (' + ','.join('?' for _ in exclude_ids) + ')', tuple(exclude_ids)
            if table in ('v4_quarter_financials', 'v4_field_provenance', 'v4_parent_equity_source', 'v4_parent_equity_provenance') and quarter_ids:
                where, args = 'WHERE quarter_id NOT IN (' + ','.join('?' for _ in quarter_ids) + ')', tuple(quarter_ids)
            result[table] = _table_digest(c, table, where, args)
        return result


def _project(canonical: Path, provider: Path, repairs):
    """Use the existing parent-equity acceptor on only the selected quarters."""
    assert_inactive_copy(canonical)
    with _ro(canonical) as old:
        mini = sqlite3.connect(':memory:'); mini.row_factory = sqlite3.Row
        quarter_ids = []
        for repair in repairs:
            matches = old.execute("SELECT q.* FROM v4_quarter q JOIN v4_field_provenance p USING(quarter_id) WHERE p.canonical_field='shares_outstanding' AND p.provider='SHARADAR' AND p.provider_observation_id=?", (repair['old_observation_id'],)).fetchall()
            if len(matches) != 1 or matches[0]['company_id'] != repair['provider_identity']['company_id']:
                raise ValueError('PAYLOAD_WORKFLOW_ACCEPTED_QUARTER_MISMATCH')
            quarter_ids.append(matches[0]['quarter_id'])
        marks = ','.join('?' for _ in quarter_ids)
        for table in ('v4_quarter', 'v4_quarter_financials', 'v4_field_provenance'):
            mini.execute(old.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0])
            for row in old.execute(f'SELECT * FROM {table} WHERE quarter_id IN ({marks})', tuple(quarter_ids)):
                values = dict(row)
                mini.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        for repair in repairs:
            mini.execute('UPDATE v4_field_provenance SET provider_observation_id=? WHERE provider_observation_id=?', (repair['new_observation_id'], repair['old_observation_id']))
        with _ro(provider) as p:
            # Stable source fetch time makes repeated calculations on the same
            # exact proposal deterministic; it is not an ownership review time.
            accept_parent_equity(mini, p, accepted_at=max(r['source_fetch_timestamp'] for r in repairs))
        mini.commit()
    try:
        with sqlite3.connect(canonical) as c:
            c.execute('PRAGMA foreign_keys=ON'); c.execute('BEGIN IMMEDIATE')
            for repair in repairs:
                c.execute(f'UPDATE v4_field_provenance SET provider_observation_id=? WHERE provider_observation_id=? AND quarter_id IN ({marks})', (repair['new_observation_id'], repair['old_observation_id'], *quarter_ids))
            for qid in quarter_ids:
                fin = mini.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?', (qid,)).fetchone()
                c.execute('UPDATE v4_quarter_financials SET parent_equity=?,parent_equity_usd=? WHERE quarter_id=?', (fin['parent_equity'], fin['parent_equity_usd'], qid))
                for table in ('v4_parent_equity_source', 'v4_parent_equity_provenance'):
                    c.execute(f'DELETE FROM {table} WHERE quarter_id=?', (qid,))
                    for row in mini.execute(f'SELECT * FROM {table} WHERE quarter_id=?', (qid,)):
                        values = dict(row); values.pop('provenance_id', None)
                        c.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
    finally:
        mini.close()
    return quarter_ids


def measure(proposals, candidates, repairs, *, as_of):
    """Recompute assertions from DBs, never trust caller-supplied PASS flags."""
    group = batch(proposals); base = proposals[0]['baseline']
    proposals = sorted(proposals, key=lambda p: p['comparison']['old_observation_id'])
    repairs = sorted(repairs, key=lambda r: r['old_observation_id'])
    if [p['comparison']['old_observation_id'] for p in proposals] != [r['old_observation_id'] for r in repairs]:
        raise ValueError('PAYLOAD_WORKFLOW_REPAIR_SCOPE_INVALID')
    old_ids = [p['comparison']['old_observation_id'] for p in proposals]
    new_ids = [r['new_observation_id'] for r in repairs]
    if len(set(new_ids)) != len(proposals):
        raise ValueError('PAYLOAD_WORKFLOW_REPAIR_SCOPE_INVALID')
    if _content(Path(base['roles']['provider']), exclude_ids=old_ids) != _content(Path(candidates['provider']), exclude_ids=new_ids):
        raise ValueError('PAYLOAD_WORKFLOW_UNRELATED_PROVIDER_CHANGED')
    from . import pb_ownership_review as ownership
    with _ro(Path(base['roles']['canonical'])) as old, _ro(Path(candidates['canonical'])) as new:
        qids = []
        for item, repair in zip(proposals, repairs, strict=True):
            rows = old.execute("SELECT quarter_id FROM v4_field_provenance WHERE canonical_field='shares_outstanding' AND provider_observation_id=?", (item['comparison']['old_observation_id'],)).fetchall()
            if len(rows) != 1:
                raise ValueError('PAYLOAD_WORKFLOW_QUARTER_BINDING_INVALID')
            qid = rows[0]['quarter_id']; qids.append(qid)
            a = dict(old.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?', (qid,)).fetchone())
            b = dict(new.execute('SELECT * FROM v4_quarter_financials WHERE quarter_id=?', (qid,)).fetchone())
            if {k: v for k, v in a.items() if k not in ('parent_equity', 'parent_equity_usd')} != {k: v for k, v in b.items() if k not in ('parent_equity', 'parent_equity_usd')}:
                raise ValueError('PAYLOAD_WORKFLOW_FINANCIAL_VALUES_CHANGED')
            if any(a[key] is not None and a[key] != b[key] for key in ('parent_equity', 'parent_equity_usd')):
                raise ValueError('PAYLOAD_WORKFLOW_EXISTING_EQUITY_CHANGED')
        if generation_ownership_artifact(old) != generation_ownership_artifact(new):
            raise ValueError('PAYLOAD_WORKFLOW_OWNERSHIP_ARTIFACT_CHANGED')
        before_cases = {c['company_id']: c for c in ownership.detect(old, as_of=as_of)}
        after_cases = {c['company_id']: c for c in ownership.detect(new, as_of=as_of)}
        selected = {p['identity']['company_id'] for p in proposals}
        if {k: v for k, v in before_cases.items() if k not in selected} != {k: v for k, v in after_cases.items() if k not in selected}:
            raise ValueError('PAYLOAD_WORKFLOW_UNRELATED_OWNERSHIP_CHANGED')
    if _content(Path(base['roles']['canonical']), quarter_ids=qids) != _content(Path(candidates['canonical']), quarter_ids=qids):
        raise ValueError('PAYLOAD_WORKFLOW_UNRELATED_CANONICAL_CHANGED')
    outcomes = {}
    with _ro(Path(candidates['provider'])) as c, _ro(Path(base['roles']['provider'])) as original, _ro(Path(candidates['canonical'])) as canonical:
        for item, repair in zip(proposals, repairs, strict=True):
            row = c.execute('SELECT * FROM provider_observation WHERE observation_id=?', (repair['new_observation_id'],)).fetchone()
            if row is None or row['content_hash'] != item['comparison']['new']['payload_fingerprint']:
                raise ValueError('PAYLOAD_WORKFLOW_CANDIDATE_SOURCE_MISMATCH')
            full = json.loads(row['payload_json'])
            if payload.completeness(full) != item['comparison']['new']:
                raise ValueError('PAYLOAD_WORKFLOW_CANDIDATE_COMPLETENESS_MISMATCH')
            old_header = dict(original.execute('SELECT * FROM provider_observation WHERE observation_id=?', (repair['old_observation_id'],)).fetchone())
            mutable = {'observation_id', 'content_hash', 'payload_json', 'provenance_json', 'fetched_at_utc'}
            if {k: v for k, v in old_header.items() if k not in mutable} != {k: row[k] for k in old_header if k not in mutable}:
                raise ValueError('PAYLOAD_WORKFLOW_PROVIDER_IDENTITY_CHANGED')
            if json.loads(row['provenance_json']) != {'source_payload_repair': repair} or row['fetched_at_utc'] != repair['source_fetch_timestamp']:
                raise ValueError('PAYLOAD_WORKFLOW_REPAIR_PROVENANCE_CHANGED')
            old_native = dict(original.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?', (repair['old_observation_id'],)).fetchone())
            new_native = dict(c.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?', (repair['new_observation_id'],)).fetchone())
            old_native.pop('observation_id'); new_native.pop('observation_id')
            if old_native != new_native:
                raise ValueError('PAYLOAD_WORKFLOW_NATIVE_FINANCIAL_CHANGED')
            key = item['source_key']
            if c.execute('SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?', key).fetchone()[0] != 1:
                raise ValueError('PAYLOAD_WORKFLOW_CANDIDATE_DUPLICATE_KEY')
            cid = item['identity']['company_id']; case = after_cases.get(cid)
            from rawcandle.fundamentals.schema.parent_equity import finite
            with _ro(Path(base['roles']['canonical'])) as old_canonical:
                qid = old_canonical.execute("SELECT quarter_id FROM v4_field_provenance WHERE canonical_field='shares_outstanding' AND provider_observation_id=?", (repair['old_observation_id'],)).fetchone()[0]
                expected_source = dict(old_canonical.execute('SELECT * FROM v4_parent_equity_source WHERE quarter_id=?', (qid,)).fetchone())
                old_provenance = [dict(v) for v in old_canonical.execute('SELECT * FROM v4_field_provenance WHERE quarter_id=? ORDER BY provenance_id', (qid,))]
            expected_source.update(observation_id=repair['new_observation_id'], content_hash=repair['new_content_hash'],
                                   fetched_at_utc=repair['source_fetch_timestamp'], accepted_at_utc=max(r['source_fetch_timestamp'] for r in repairs))
            for name in ('pb', 'marketcap', 'price', 'sharesbas', 'shareswa', 'shareswadil', 'sharefactor'):
                expected_source[name] = finite(full.get(name))
            actual_source = dict(canonical.execute('SELECT * FROM v4_parent_equity_source WHERE quarter_id=?', (qid,)).fetchone())
            if actual_source != expected_source:
                raise ValueError('PAYLOAD_WORKFLOW_SOURCE_PROJECTION_CHANGED')
            selected_equity = canonical.execute('SELECT parent_equity,parent_equity_usd FROM v4_quarter_financials WHERE quarter_id=?', (qid,)).fetchone()
            if tuple(selected_equity) != (finite(full.get('equity')), finite(full.get('equityusd'))):
                raise ValueError('PAYLOAD_WORKFLOW_CANONICAL_PROJECTION_MISMATCH')
            for provenance in old_provenance:
                if provenance['provider_observation_id'] == repair['old_observation_id']:
                    provenance['provider_observation_id'] = repair['new_observation_id']
            if old_provenance != [dict(v) for v in canonical.execute('SELECT * FROM v4_field_provenance WHERE quarter_id=? ORDER BY provenance_id', (qid,))]:
                raise ValueError('PAYLOAD_WORKFLOW_FIELD_PROVENANCE_CHANGED')
            from rawcandle.fundamentals.schema.parent_equity import RULE_VERSION
            expected_equity_provenance = [{
                'quarter_id': qid, 'canonical_field': field, 'provider': 'SHARADAR',
                'provider_observation_id': repair['new_observation_id'], 'source_native_field': native,
                'transformation': 'DIRECT', 'accepted_at_utc': max(r['source_fetch_timestamp'] for r in repairs),
                'rule_version': RULE_VERSION, 'confidence': 'HIGH',
            } for field, native in (('parent_equity', 'equity'), ('parent_equity_usd', 'equityusd')) if finite(full.get(native)) is not None]
            actual_equity_provenance = [{k: v for k, v in dict(row).items() if k != 'provenance_id'}
                for row in canonical.execute('SELECT * FROM v4_parent_equity_provenance WHERE quarter_id=? ORDER BY canonical_field', (qid,))]
            if actual_equity_provenance != sorted(expected_equity_provenance, key=lambda row: row['canonical_field']):
                raise ValueError('PAYLOAD_WORKFLOW_EQUITY_PROVENANCE_CHANGED')
            if case:
                effect = ownership.preview(case, Path(candidates['canonical']), Path(base['market']), as_of=as_of)
                ownership_classification = case['classification']
            else:
                from rawcandle.fundamentals.book_value import book_value_report
                with _ro(Path(base['market'])) as market:
                    report = book_value_report(canonical, market, company_id=cid, ticker=item['ticker'], as_of=as_of)
                effect = {'held_current': report['current'], 'hypothetical_current': None}
                ownership_classification = 'NO_QUARTERLY_OWNERSHIP_REVIEW_CASE'
            outcomes[item['repair_id']] = {'ownership_classification': ownership_classification,
                'fresh_factor': actual_source['sharefactor'], 'parent_equity_usd': selected_equity['parent_equity_usd'],
                'actual_current_reason': effect['held_current']['reason'],
                'hypothetical_pb': (effect['hypothetical_current'] or {}).get('value'),
                'ownership_approved': False, 'pb_approved': False}
    checks = {role: journal.sqlite_verification(Path(path)) for role, path in candidates.items()}
    with _ro(Path(candidates['provider'])) as c, _ro(Path(candidates['canonical'])) as n:
        if any(db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' for db in (c, n)):
            raise ValueError('PAYLOAD_WORKFLOW_INTEGRITY_FAILED')
    if checks['analysis']['sha256'] != base['role_hashes']['analysis']:
        raise ValueError('PAYLOAD_WORKFLOW_ANALYSIS_CHANGED')
    return {'batch_fingerprint': group['batch_fingerprint'], 'repairs': repairs,
            'quarter_ids': sorted(qids), 'outcomes': outcomes,
            'assertions': {key: True for key in ASSERTIONS},
            'candidate_hashes': {k: v['sha256'] for k, v in checks.items()}}


def rehearse(project_root: Path, proposals, histories, output_dir: Path, *, as_of: str):
    group = batch(proposals); base = baseline(project_root)
    for item in proposals:
        revalidate(project_root, item, histories[tuple(item['source_key'][:2])], source_baseline=base)
    output_dir.mkdir(parents=True, exist_ok=False)
    candidates = {role: output_dir / (role + '.db') for role in ('provider', 'canonical', 'analysis')}
    for role, target in candidates.items():
        # Finalized source generations have no SQLite sidecars. Preserve their
        # exact bytes, including the unchanged analysis role's page-one header.
        shutil.copyfile(Path(base['roles'][role]), target)
        journal.fsync_file(target)
        if journal.sha256_file(target) != base['role_hashes'][role]:
            raise ValueError('PAYLOAD_WORKFLOW_COPY_SOURCE_DRIFT')
    selected = [{
        'old_observation_id': p['comparison']['old_observation_id'],
        'old_content_hash': p['comparison']['old_content_hash'],
        'comparison_fingerprint': digest(p['comparison']),
        'source_fetch_timestamp': p['source_fetch_timestamp'],
    } for p in proposals]
    # The primitive uses the existing administrative comparison hash; source
    # payload fingerprints inside that comparison still bind every source key.
    from .contracts import fingerprint
    for selection, item in zip(selected, proposals, strict=True):
        selection['comparison_fingerprint'] = fingerprint(item['comparison'])
    result = payload.repair_payloads_on_copy(candidates['provider'], selected, source_histories=histories,
                                            fetched_at_utc=max(p['source_fetch_timestamp'] for p in proposals))
    _project(candidates['canonical'], candidates['provider'], result['repairs'])
    measured = measure(proposals, candidates, result['repairs'], as_of=as_of)
    receipts = []
    for item, repair in zip(proposals, result['repairs'], strict=True):
        value = {'schema': RECEIPT, 'proposal_fingerprint': item['proposal_fingerprint'],
                 'repair_id': item['repair_id'], 'source_key': item['source_key'],
                 'batch': group, 'baseline': base, 'comparison': item['comparison'],
                 'repair': repair, 'candidates': {k: str(v.resolve()) for k, v in candidates.items()},
                 'as_of': as_of, 'result': measured, 'result_fingerprint': digest(measured), 'passed': True}
        receipts.append(_seal(value, 'receipt_fingerprint'))
    return receipts


def binding(item, receipt):
    validate_proposal(item); _verify(receipt, RECEIPT, 'receipt_fingerprint')
    result = receipt.get('result') or {}
    expected_id = digest({'provider': 'SHARADAR', 'source': 'fundamentals',
                          'source_key': item['source_key'],
                          'payload_hash': item['comparison']['new']['payload_fingerprint']})
    expected_repair = {**item['comparison'], 'source_fetch_timestamp': item['source_fetch_timestamp'],
                       'new_observation_id': expected_id,
                       'new_content_hash': item['comparison']['new']['payload_fingerprint']}
    if (receipt.get('passed') is not True or receipt.get('proposal_fingerprint') != item['proposal_fingerprint']
        or receipt.get('repair_id') != item['repair_id'] or receipt.get('source_key') != item['source_key']
        or receipt.get('baseline') != item['baseline'] or receipt.get('comparison') != item['comparison']
        or receipt.get('result_fingerprint') != digest(result)
        or result.get('assertions') != {key: True for key in ASSERTIONS}
        or receipt['repair'] != expected_repair or receipt['repair'] not in result.get('repairs', [])
        or receipt['repair']['old_observation_id'] != item['comparison']['old_observation_id']
        or receipt['repair']['old_content_hash'] != item['comparison']['old_content_hash']
        or receipt['repair']['new_content_hash'] != item['comparison']['new']['payload_fingerprint']):
        raise ValueError('PAYLOAD_WORKFLOW_RECEIPT_BINDING_INVALID')
    return _seal({'schema': BINDING, 'proposal_fingerprint': item['proposal_fingerprint'],
                  'receipt_fingerprint': receipt['receipt_fingerprint'], 'source_key': item['source_key'],
                  'baseline_generation': item['baseline']['generation_id'],
                  'result_fingerprint': receipt['result_fingerprint'],
                  'candidate_hashes': result['candidate_hashes'], 'comparison': item['comparison'],
                  'batch_fingerprint': receipt['batch']['batch_fingerprint']}, 'binding_fingerprint')


def verify_receipts(proposals, receipts, *, check_files=True):
    if len(proposals) != len(receipts):
        raise ValueError('PAYLOAD_WORKFLOW_RECEIPT_SET_INVALID')
    group = batch(proposals)
    for item, receipt in zip(proposals, receipts, strict=True):
        binding(item, receipt)
        if receipt['batch'] != group or receipt['result'] != receipts[0]['result'] or receipt['candidates'] != receipts[0]['candidates']:
            raise ValueError('PAYLOAD_WORKFLOW_BATCH_RECEIPT_MISMATCH')
    if check_files:
        c = {k: Path(v) for k, v in receipts[0]['candidates'].items()}
        measured = measure(proposals, c, receipts[0]['result']['repairs'], as_of=receipts[0]['as_of'])
        if measured != receipts[0]['result']:
            raise ValueError('PAYLOAD_WORKFLOW_STALE_CANDIDATE')


def _schema(c):
    c.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
        repair_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, status TEXT NOT NULL,
        proposal_json TEXT NOT NULL, receipt_json TEXT NOT NULL, binding_json TEXT,
        decision_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS refresh_review_queue_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL,
        event_type TEXT NOT NULL, occurred_at_utc TEXT NOT NULL, run_id TEXT, evidence_json TEXT NOT NULL)''')


def _audit(c, item, event, evidence):
    c.execute('INSERT INTO refresh_review_queue_audit(ticker,event_type,occurred_at_utc,run_id,evidence_json) VALUES(?,?,?,?,?)',
              (item['ticker'], 'PROVIDER_PAYLOAD_REPAIR_' + event, utc_now(), item['repair_id'], json.dumps(evidence, sort_keys=True)))


def register(project_root: Path, queue_path: Path, proposals, receipts, histories):
    from .artifacts import ROOT
    from rawcandle.scheduler.config import read_scheduler_config
    if project_root.resolve() == ROOT.resolve():
        config = read_scheduler_config(str(project_root / 'scheduler_config.json'))
        with preflight(project_root, Path(config.log_dir)):
            return _register(project_root, queue_path, proposals, receipts, histories)
    return _register(project_root, queue_path, proposals, receipts, histories)


def _register(project_root: Path, queue_path: Path, proposals, receipts, histories):
    base = baseline(project_root)
    for item in proposals:
        revalidate(project_root, item, histories[tuple(item['source_key'][:2])], source_baseline=base)
    verify_receipts(proposals, receipts)
    with sqlite3.connect(queue_path) as c:
        c.row_factory = sqlite3.Row; c.execute('BEGIN IMMEDIATE'); _schema(c)
        for item, receipt in zip(proposals, receipts, strict=True):
            link = binding(item, receipt)
            existing = c.execute(f'SELECT * FROM {TABLE} WHERE repair_id=?', (item['repair_id'],)).fetchone()
            if existing:
                _read(c, item['repair_id'])
                if (json.loads(existing['proposal_json']) != item or json.loads(existing['receipt_json']) != receipt
                    or not existing['binding_json'] or json.loads(existing['binding_json']) != link):
                    raise ValueError('PAYLOAD_WORKFLOW_CONFLICTING_RECEIPT')
                continue
            conflicts = c.execute(f'SELECT status,decision_json FROM {TABLE} WHERE source_key=?', (json.dumps(item['source_key']),)).fetchall()
            if any(row['status'] not in ('REJECTED', 'STALE') for row in conflicts):
                raise ValueError('PAYLOAD_WORKFLOW_CONFLICTING_PROPOSAL')
            c.execute(f'INSERT INTO {TABLE} VALUES(?,?,?,?,?,?,NULL)',
                      (item['repair_id'], json.dumps(item['source_key']), 'OPEN', json.dumps(item, sort_keys=True),
                       json.dumps(receipt, sort_keys=True), json.dumps(link, sort_keys=True)))
            _audit(c, item, 'REGISTERED_OPEN', link)
    return [item['repair_id'] for item in proposals]


def _read(c, repair_id):
    row = c.execute(f'SELECT * FROM {TABLE} WHERE repair_id=?', (repair_id,)).fetchone()
    if row is None or row['status'] not in STATES or not row['binding_json']:
        raise ValueError('PAYLOAD_WORKFLOW_UNBOUND_OR_INVALID_ITEM')
    item, receipt, link = (json.loads(row[name]) for name in ('proposal_json', 'receipt_json', 'binding_json'))
    if (item['repair_id'] != repair_id or row['source_key'] != json.dumps(item['source_key'])
        or binding(item, receipt) != link):
        raise ValueError('PAYLOAD_WORKFLOW_ITEM_MISMATCH')
    registered = c.execute("SELECT evidence_json FROM refresh_review_queue_audit WHERE run_id=? AND event_type='PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN'", (repair_id,)).fetchall()
    if len(registered) != 1 or json.loads(registered[0][0]) != link:
        raise ValueError('PAYLOAD_WORKFLOW_REGISTRATION_AUDIT_MISMATCH')
    decision = json.loads(row['decision_json']) if row['decision_json'] else None
    if (row['status'] == 'OPEN') != (decision is None):
        raise ValueError('PAYLOAD_WORKFLOW_DECISION_STATE_MISMATCH')
    if row['status'] == 'APPROVED':
        _verify(decision, ITEM, 'decision_fingerprint')
        if (decision.get('repair_id') != repair_id or decision.get('binding_fingerprint') != link['binding_fingerprint']
            or decision.get('batch_fingerprint') != link['batch_fingerprint']
            or decision.get('applied') is not True or decision.get('source_repair_only') is not True
            or decision.get('ownership_authorized') is not False or decision.get('pb_authorized') is not False):
            raise ValueError('PAYLOAD_WORKFLOW_APPROVAL_SCOPE_INVALID')
    elif decision is not None and (decision.get('status') != row['status'] or decision.get('live_repair_authorized') is not False or not decision.get('reason')):
        raise ValueError('PAYLOAD_WORKFLOW_TERMINAL_DECISION_INVALID')
    return item, receipt, link, row['status'], decision


def confirmation(project_root: Path, queue_path: Path, repair_id: str, history):
    with _ro(queue_path) as c:
        item, receipt, link, status, decision = _read(c, repair_id)
    revalidate(project_root, item, history)
    for role, path in receipt['candidates'].items():
        if journal.sha256_file(Path(path)) != receipt['result']['candidate_hashes'][role]:
            raise ValueError('PAYLOAD_WORKFLOW_STALE_CANDIDATE')
    return {'schema': ITEM, 'repair_id': repair_id, 'ticker': item['ticker'],
            'source_key': item['source_key'], 'status': status, 'decision': decision,
            'old_observation_id': item['comparison']['old_observation_id'],
            'old_content_hash': item['comparison']['old_content_hash'],
            'fresh_source_fingerprint': item['comparison']['new']['payload_fingerprint'],
            'old_completeness': item['comparison']['old'],
            'restored_fields': item['comparison']['fields_restored'], 'fresh_factor': item['fresh_factor'],
            'financial_values_changed': False, 'proposal_fingerprint': item['proposal_fingerprint'],
            'receipt_fingerprint': receipt['receipt_fingerprint'], 'receipt_pass': True,
            'binding_fingerprint': link['binding_fingerprint'],
            'baseline_generation': item['baseline']['generation_id'],
            'candidate_hashes': receipt['result']['candidate_hashes'],
            'batch_fingerprint': receipt['batch']['batch_fingerprint'], 'live_repair_authorized': False,
            'approval_action': 'EXPLICIT_YES_SOURCE_REPAIR_ONLY', 'stale': False,
            'ownership_authorized': False, 'pb_authorized': False}


def close_item(queue_path: Path, repair_id: str, *, status: str, reason: str):
    if status not in ('REJECTED', 'STALE') or not reason.strip():
        raise ValueError('PAYLOAD_WORKFLOW_EXPLICIT_CLOSE_REQUIRED')
    with sqlite3.connect(queue_path) as c:
        c.row_factory = sqlite3.Row; c.execute('BEGIN IMMEDIATE')
        item, _, _, current, _ = _read(c, repair_id)
        if current != 'OPEN':
            raise ValueError('PAYLOAD_WORKFLOW_OPEN_REQUIRED')
        decision = {'status': status, 'reason': reason, 'at': utc_now(), 'live_repair_authorized': False}
        c.execute(f'UPDATE {TABLE} SET status=?,decision_json=? WHERE repair_id=?', (status, json.dumps(decision), repair_id))
        _audit(c, item, status, decision)


def fetch_for_proposals(proposals, *, client=None):
    from rawcandle.fundamentals.providers.sharadar import SharadarClient
    provider = client or SharadarClient()
    histories = {}
    for ticker, dimension in sorted({tuple(p['source_key'][:2]) for p in proposals}):
        result = fetch_complete_history(provider, ticker, dimension)
        if result.status != 'COMPLETE':
            raise ValueError('PAYLOAD_WORKFLOW_FRESH_SOURCE_INCOMPLETE')
        histories[(ticker, dimension)] = result
    return histories


def _authorized_decision(item, link, group, generation):
    return _seal({'schema': ITEM, 'status': 'APPROVED', 'applied': True,
                  'repair_id': item['repair_id'], 'binding_fingerprint': link['binding_fingerprint'],
                  'batch_fingerprint': group['batch_fingerprint'], 'generation_id': generation,
                  'authorization': 'EXPLICIT_OPERATOR_YES', 'approved_at': utc_now(),
                  'live_repair_authorized': True, 'source_repair_only': True,
                  'ownership_authorized': False, 'pb_authorized': False},
                 'decision_fingerprint')


def synchronize_completed(project_root: Path, queue_path: Path):
    """Retry only repair-queue finalization after a COMPLETED durable postflight."""
    record = journal.load_journal(project_root / 'data/.fundamentals_admin_publication_journal.json')
    if not record or record['operation_type'] != OPERATION or record['state'] != 'COMPLETED' or record['postflight_state'] != 'PASSED':
        return False
    scope = record.get('scope_evidence') or {}
    active = resolve_active_generation(project_root, require_generation=True)
    if active.generation_id != record['new_generation_id']:
        raise ValueError('PAYLOAD_WORKFLOW_COMPLETED_GENERATION_MISMATCH')
    if any(journal.sha256_file(path) != scope['candidate_hashes'][role] for role, path in active.role_paths().items()):
        raise ValueError('PAYLOAD_WORKFLOW_COMPLETED_ROLE_MISMATCH')
    with sqlite3.connect(queue_path) as c:
        c.row_factory = sqlite3.Row; c.execute('BEGIN IMMEDIATE')
        for selected in scope['selected']:
            item, receipt, link, status, decision = _read(c, selected['repair_id'])
            if link != selected['binding'] or receipt['batch'] != scope['batch']:
                raise ValueError('PAYLOAD_WORKFLOW_COMPLETED_BINDING_MISMATCH')
            expected = selected['decision']
            _verify(expected, ITEM, 'decision_fingerprint')
            if status == 'APPROVED' and decision == expected:
                continue
            if status != 'OPEN':
                raise ValueError('PAYLOAD_WORKFLOW_COMPLETED_QUEUE_CONFLICT')
            c.execute(f'UPDATE {TABLE} SET status=\'APPROVED\',decision_json=? WHERE repair_id=?',
                      (json.dumps(expected, sort_keys=True), item['repair_id']))
            _audit(c, item, 'APPROVED_SOURCE_REPAIR', expected)
    return True


def publish_batch(project_root: Path, queue_path: Path, repair_ids, *,
                  authorized_batch_fingerprint: str, confirmed: bool = False,
                  production_intent: bool = False, rehearsal: bool = False,
                  client=None, inject_failure_at=None):
    """Stage two only: explicit YES -> fresh gates -> journalled generation.

    This is a dedicated source-repair operation, not Refresh Preview/Test/
    Production, an ownership approval or a P/B approval. Never call from stage
    one or ordinary scheduled financial replacement.
    """
    from .artifacts import ROOT
    from .production_transaction import production_lock
    from .refresh_production import _verified_backups, _candidate_manifest
    from .batch_add_tickers import BatchAddTickerPaths
    from rawcandle.fundamentals.generations import prepare_generation_from_candidates
    from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
    from rawcandle.scheduler.config import read_scheduler_config
    root = project_root.resolve()
    if confirmed is not True or not authorized_batch_fingerprint:
        raise PermissionError('PAYLOAD_WORKFLOW_EXPLICIT_BATCH_YES_REQUIRED')
    real = root == ROOT.resolve()
    if (real and (production_intent is not True or rehearsal or client is not None or inject_failure_at)) or (not real and rehearsal is not True):
        raise PermissionError('PAYLOAD_WORKFLOW_PUBLICATION_INTENT_REQUIRED')
    if queue_path.is_symlink() or (real and queue_path.resolve() != (ROOT / 'fundamental_reports/fundamentals_refresh_review_queue.db').resolve()):
        raise PermissionError('PAYLOAD_WORKFLOW_LIVE_OPERATIONAL_QUEUE_REQUIRED')
    if not repair_ids or len(set(repair_ids)) != len(repair_ids):
        raise ValueError('PAYLOAD_WORKFLOW_EXPLICIT_UNIQUE_SELECTION_REQUIRED')
    config = read_scheduler_config(str(root / 'scheduler_config.json'))
    taxonomy_evidence = None if real else ROOT / 'temp/provider_payload_rehearsal_locks' / digest(str(root))[:24]
    journal_path = root / 'data/.fundamentals_admin_publication_journal.json'
    with ExitStack() as stack:
        ui_lock = root / 'fundamental_reports/.fundamentals_admin_ui_operation.lock'
        if not real:
            ui_lock.parent.mkdir(parents=True, exist_ok=True)
            ui_lock.touch(exist_ok=True)
        ui_fd = stack.enter_context(ui_lock.open('r'))
        fcntl.flock(ui_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # These are the existing publication locks, not a competing publisher.
        stack.enter_context(production_lock(lock_path=root / 'temp/.fundamentals_admin_production.lock',
                                            scheduler_log_dir=config.log_dir))
        stack.enter_context(taxonomy_operation_lock_context(deployment_id=OPERATION, operation_type=OPERATION,
                                                           evidence_root=taxonomy_evidence))
        journal.guard_production_writes(journal_path)
        active = resolve_active_generation(root, require_generation=True)
        source = baseline(root)
        with _ro(queue_path) as q:
            saved = [_read(q, rid) for rid in repair_ids]
        if any(status != 'OPEN' or decision is not None for _, _, _, status, decision in saved):
            raise ValueError('PAYLOAD_WORKFLOW_OPEN_REQUIRED')
        proposals = [s[0] for s in saved]; receipts = [s[1] for s in saved]
        group = batch(proposals)
        if group['batch_fingerprint'] != authorized_batch_fingerprint:
            raise PermissionError('PAYLOAD_WORKFLOW_AUTHORIZED_BATCH_MISMATCH')
        histories = fetch_for_proposals(proposals, client=client)
        for item in proposals:
            revalidate(root, item, histories[tuple(item['source_key'][:2])], source_baseline=source)
        verify_receipts(proposals, receipts)
        candidates = {k: Path(v) for k, v in receipts[0]['candidates'].items()}
        # Queue ownership rows are protected by the queue transaction throughout
        # publication; this operation writes only its own typed repair rows.
        with sqlite3.connect(queue_path) as q:
            q.row_factory = sqlite3.Row; q.execute('BEGIN IMMEDIATE')
            if [_read(q, rid) for rid in repair_ids] != saved:
                raise ValueError('PAYLOAD_WORKFLOW_QUEUE_DRIFT')
            if baseline(root) != source:
                raise ValueError('PAYLOAD_WORKFLOW_FINAL_BASELINE_DRIFT')
            verify_receipts(proposals, receipts)
            run_id = 'payload_repair_' + group['batch_fingerprint'][:16] + '_' + uuid.uuid4().hex[:12]
            owned = root / 'temp' / run_id / 'candidates'
            owned.mkdir(parents=True, exist_ok=False)
            owned_candidates = {}
            for role, path in candidates.items():
                target = owned / (role + '.db')
                shutil.copyfile(path, target); journal.fsync_file(target)
                if journal.sha256_file(target) != receipts[0]['result']['candidate_hashes'][role]:
                    raise ValueError('PAYLOAD_WORKFLOW_OWNED_CANDIDATE_DRIFT')
                owned_candidates[role] = target
            candidates = owned_candidates
            paths = BatchAddTickerPaths(*(active.role_paths()[role] for role in ('provider', 'canonical', 'analysis')),
                                        root / 'data/osakedata.db', root / 'data/analysis.db')
            backups = _verified_backups(paths, root / 'backups/fundamentals_admin_production' / run_id,
                                        immutable_generation=True)
            roles = _candidate_manifest(candidates, backups)
            scope = {'batch': group, 'candidate_hashes': receipts[0]['result']['candidate_hashes'],
                     'selected': [{'repair_id': item['repair_id'], 'binding': link,
                                   'decision': _authorized_decision(item, link, group, run_id)}
                                  for item, _, link, _, _ in saved]}
            current = None; completed = False
            try:
                current = journal.prepare_journal(path=journal_path, operation_type=OPERATION, run_id=run_id,
                    preview_run_id=group['batch_fingerprint'], test_run_id=receipts[0]['receipt_fingerprint'],
                    refresh_set_fingerprint=group['batch_fingerprint'], old_source_watermark=source['watermark'],
                    new_source_watermark=source['watermark'], source_schema_fingerprint=digest(source),
                    roles=roles, publication_mode='GENERATION_POINTER',
                    old_generation=active.evidence() | {'manifest': dict(active.manifest)}, new_generation_id=run_id,
                    active_generation_manifest_path=active_manifest_path(root), scope_evidence=scope)
                prepared = prepare_generation_from_candidates(candidates, generation_id=run_id,
                                                              project_root=root, source=OPERATION)
                current = journal.update_journal(journal_path, current, current_publication_step='NEW_GENERATION_READY',
                    generation_activation_state='READY', new_generation_manifest=prepared['manifest'],
                    new_generation_dir=prepared['generation_dir'])
                if baseline(root) != source or [_read(q, rid) for rid in repair_ids] != saved:
                    raise ValueError('PAYLOAD_WORKFLOW_FINAL_GATE_DRIFT')
                ready = {k: Path(v) for k, v in prepared['roles'].items()}
                if any(journal.sha256_file(path) != scope['candidate_hashes'][role] for role, path in ready.items()):
                    raise ValueError('PAYLOAD_WORKFLOW_FINAL_CANDIDATE_DRIFT')
                if journal.load_journal(journal_path) != current:
                    raise ValueError('PAYLOAD_WORKFLOW_JOURNAL_DRIFT')
                if inject_failure_at == 'BEFORE_ACTIVATION':
                    raise RuntimeError('INJECTED_BEFORE_ACTIVATION')
                current = journal.activate_prepared_generation(current, new_manifest=prepared['manifest'], journal_path=journal_path)
                current = journal.update_journal(journal_path, current, state='POSTFLIGHT', postflight_state='RUNNING')
                if inject_failure_at == 'POSTFLIGHT':
                    raise RuntimeError('INJECTED_POSTFLIGHT')
                live = resolve_active_generation(root, require_generation=True)
                live_paths = live.role_paths()
                if live.generation_id != run_id or any(journal.sqlite_verification(path)['sha256'] != scope['candidate_hashes'][role] for role, path in live_paths.items()):
                    raise ValueError('PAYLOAD_WORKFLOW_POSTFLIGHT_ROLE_MISMATCH')
                if measure(proposals, live_paths, receipts[0]['result']['repairs'], as_of=receipts[0]['as_of']) != receipts[0]['result']:
                    raise ValueError('PAYLOAD_WORKFLOW_POSTFLIGHT_RESULT_MISMATCH')
                current = journal.update_journal(journal_path, current, state='COMPLETED', postflight_state='PASSED',
                    current_publication_step='COMPLETED', scope_evidence=scope)
                completed = True
                if inject_failure_at == 'QUEUE_FINALIZATION':
                    raise RuntimeError('PAYLOAD_WORKFLOW_QUEUE_SYNC_REQUIRED')
                for item, _, link, _, _ in saved:
                    decision = next(s['decision'] for s in scope['selected'] if s['repair_id'] == item['repair_id'])
                    q.execute(f'UPDATE {TABLE} SET status=\'APPROVED\',decision_json=? WHERE repair_id=?',
                              (json.dumps(decision, sort_keys=True), item['repair_id']))
                    _audit(q, item, 'APPROVED_SOURCE_REPAIR', decision)
            except BaseException:
                if current and not completed:
                    journal.restore_old_generation(current, journal_path=journal_path)
                raise
        return {'generation_id': run_id, 'journal_state': 'COMPLETED', 'postflight': 'PASSED',
                'ownership_approved': False, 'pb_approved': False}
