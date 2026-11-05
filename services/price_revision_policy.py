"""Bounded, read-only proof of ordinary Source revisions; never rewrite RC prices."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

FIELDS = ('Open', 'High', 'Low', 'Close', 'Volume')
RC_FIELDS = ('open', 'high', 'low', 'close', 'volume')
POLICY = 'IMMUTABLE_RC_SOURCE_REVISIONS_V1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def difference(*, ticker, security_id, anchor, raw, adjusted, dependency):
    before = {field: anchor[key] for field, key in zip(FIELDS, RC_FIELDS)}
    after = dict(zip(FIELDS, adjusted))
    fields = [k for k in FIELDS if not math.isclose(before[k], after[k], rel_tol=1e-12, abs_tol=1e-12)]
    if not fields:
        return None
    return dict(policy=POLICY, reason='HISTORICAL_SOURCE_REVISION_DIFFERENCE', ticker=ticker,
                security_id=security_id, session=anchor['pvm'], original_rc=before,
                accepted_source=after, accepted_source_raw=raw, changed_fields=fields,
                absolute_differences={k: abs(after[k]-before[k]) for k in fields},
                relative_differences={k: abs(after[k]-before[k])/abs(before[k]) if before[k] else None for k in fields},
                source_dependency=dependency, source_revision=dependency['source_revision'])


def revision_witness(c, lib, *, security_id, session, calendar, now, anchor_receipt):
    """An actual revised observation in the last six completed exchange sessions.

    Initial imports are not revision evidence. A retained earlier overlap receipt
    may qualify, but an old date never gets an unbounded exception.
    """
    completed = calendar.completed(now)
    if session not in completed[-6:]:
        return None, 'REVISION_OUTSIDE_SIX_COMPLETED_SESSIONS'
    stored = c.execute('SELECT * FROM source_receipts WHERE receipt_id=? AND security_id=?',
                       (anchor_receipt, security_id)).fetchone()
    if not stored or stored['status'] != 'COMPLETE':
        return None, 'REVISION_ACCEPTED_RECEIPT_REQUIRED'
    summary = json.loads(stored['summary'])
    revision = summary.get('revision')
    # Native changes are keyed by the producer, not an unindexed history search.
    key = lib.fingerprint([security_id, revision, anchor_receipt])
    change = c.execute('SELECT * FROM source_changes WHERE change_id=?', (key,)).fetchone()
    if not change:
        return None, 'REVISION_CHANGE_RECEIPT_REQUIRED'
    try:
        authoritative = lib.acceptance_receipt(c, stored, summary)
    except (ValueError, TypeError, KeyError, lib.ContractError):
        return None, 'REVISION_RECEIPT_UNQUALIFIED'
    if (authoritative.get('mode') != 'daily' or
            authoritative.get('changed_sessions', 0) <= authoritative.get('missing_inserted', 0)):
        return None, 'ORDINARY_OVERLAP_REVISION_REQUIRED'
    scope = json.loads(change['scope'])
    if scope.get('critical_hold') or scope.get('identity_or_calendar_changed'):
        return None, 'REVISION_IDENTITY_OR_ACTION_CHANGED'
    if any(a.get('change') not in {'UNCHANGED'} or a.get('status') != 'RECORDED' for a in scope.get('actions', [])):
        return None, 'REVISION_ACTION_REVIEW_REQUIRED'
    item = next((r for r in scope.get('changes', []) if r.get('session') == session), None)
    if not item or not item.get('fields'):
        return None, 'REVISION_SESSION_NOT_CHANGED'
    # A daily receipt can revise an old bar AND insert another one. Its aggregate
    # counts do not prove that this particular session was an overlap revision.
    # Require a native earlier accepted change for the same session; initial
    # insertion in a mixed receipt must never qualify as revision provenance.
    previous = c.execute('''
        SELECT prior.change_id, prior.revision, prior.receipt_id
        FROM source_changes AS prior
        JOIN source_receipts AS receipt
          ON receipt.receipt_id=prior.receipt_id
         AND receipt.security_id=prior.security_id
        WHERE prior.security_id=? AND prior.revision<?
          AND receipt.status='COMPLETE'
          AND json_extract(receipt.summary,'$.revision')=prior.revision
          AND json_extract(receipt.summary,'$.accepted_sessions')>0
          AND EXISTS (
              SELECT 1 FROM json_each(prior.scope,'$.changes') AS bar
              WHERE json_extract(bar.value,'$.session')=?
                AND json_array_length(bar.value,'$.fields')>0
          )
    ''', (security_id, revision, session))
    if not any(row['change_id'] == lib.fingerprint([security_id, row['revision'], row['receipt_id']])
               for row in previous):
        return None, 'REVISION_SESSION_PREVIOUS_ACCEPTANCE_REQUIRED'
    head = c.execute('SELECT dependency FROM source_heads WHERE security_id=?', (security_id,)).fetchone()
    dep = json.loads(head[0])
    old_dep = authoritative['source_dependency']
    if (old_dep['security_id'] != security_id or old_dep['identity_version'] != dep['identity_version'] or
            old_dep['calendar_version'] != dep['calendar_version']):
        return None, 'REVISION_REFERENCE_CHANGED'
    return dict(receipt_id=anchor_receipt, revision=revision, changed_fields=item['fields'],
                source_dependency=old_dep, window=completed[-6:]), None


def ordinary_revision(*, diagnostic, witness, context, prices_match, volumes_match):
    """Prove units with nearby accepted context; retain genuine scale barriers.

    No relaxed Volume percentage is introduced. One compatible historical peer
    plus native revision provenance supports common reported units. Persistent
    coherent rescaling is still rejected by the existing independent gate.
    """
    if not witness:
        return False, 'ORDINARY_REVISION_PROVENANCE_REQUIRED'
    old, new = diagnostic['original_rc'], diagnostic['accepted_source']
    ratios = [new[k]/old[k] for k in FIELDS[:4]]
    # A material common price multiplier is a unit/factor question, not a
    # nonuniform OHLC correction. Dividend exceptions remain in the owner.
    if max(ratios)-min(ratios) <= 1e-6 and abs(sum(ratios)/4-1) > .001 + 1e-12:
        return False, 'SUSPECTED_PRICE_UNIT_CHANGE'
    if abs(new['Close']-old['Close'])/old['Close'] > .001 + 1e-12:
        return False, 'ECONOMIC_CLOSE_CONTINUITY_UNPROVEN'
    # At least one independently compatible old session, not just the ticker.
    if not any(prices_match(a[:4], b[:4]) and volumes_match(a[4], b[4]) for a, b in context):
        return False, 'HISTORICAL_UNIT_CONTEXT_UNPROVEN'
    changed = {k for k in diagnostic['changed_fields'] if k == 'Volume' or
               abs(new[k]-old[k])/old[k] > .001 + 1e-12}
    supported = set(witness['changed_fields'])
    if 'Adj Close' in supported:
        supported.update(FIELDS[:4])
    if not changed <= supported:
        return False, 'RC_DIFFERENCE_NOT_BOUND_TO_SOURCE_REVISION'
    return True, 'NATIVE_OVERLAP_REVISION_WITH_COMPATIBLE_UNITS'


class RevisionDiagnostics:
    """At most six session records per security; deterministic value deduplication.

    Detailed evidence is outside the price DB. Repeated unchanged differences do
    not generate new warnings even if the Source head revision advances.
    """
    def __init__(self, directory):
        self.directory = Path(directory)

    def record(self, item, *, update=False):
        path = self.directory
        if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
            raise RuntimeError('UNSAFE_REVISION_DIAGNOSTIC_PATH')
        path.mkdir(parents=True, exist_ok=True)
        lock = path / 'diagnostics.lock'
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_nlink != 1:
                raise RuntimeError('UNSAFE_REVISION_DIAGNOSTIC_LOCK')
            fcntl.flock(fd, fcntl.LOCK_EX)
            target = path / (str(item['security_id']) + '.json')
            if target.is_symlink() or target.exists() and (target.stat().st_nlink != 1 or target.stat().st_size > 256000):
                raise RuntimeError('UNSAFE_REVISION_DIAGNOSTIC_FILE')
            data = json.loads(target.read_text()) if target.exists() else {'policy': POLICY, 'records': []}
            key = digest([item['security_id'], item['session'], item['original_rc'], item['accepted_source'], item['classification']])
            exists = any(r.get('dedup_key') == key for r in data['records'])
            if exists and not update:
                return False
            data['records'] = [r for r in data['records'] if r['session'] != item['session']]
            data['records'].append(dict(item, dedup_key=key))
            data['records'] = sorted(data['records'], key=lambda r: r['session'])[-6:]
            tmp_fd, tmp = tempfile.mkstemp(prefix='.revision-', dir=path)
            try:
                with os.fdopen(tmp_fd, 'w') as stream:
                    stream.write(canonical(data)); stream.flush(); os.fsync(stream.fileno())
                os.replace(tmp, target)
                directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
            return not exists
        finally:
            os.close(fd)
