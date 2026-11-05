"""Explicit bounded OMXH provisional-bar finalization with exact restoration.

This is not an ordinary updater or an unrestricted historical price writer.
USA history replacement is rejected. Preparation does not write price databases.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from services.market_sessions import HELSINKI, is_helsinki_session, last_completed_helsinki_session
from services.price_revision_policy import canonical, digest
from services.stockcore_price_provider import readonly, valid_prices, valid_volume

FORMAT = 'OMXH_PROVISIONAL_FINALIZATION_V1'
PRICE_FIELDS = ('open', 'high', 'low', 'close', 'volume')
ROW_FIELDS = ('id', 'osake', 'pvm', *PRICE_FIELDS, 'market')


def physical(path):
    path = Path(path)
    if (not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)) or
            any(p in {'.git','.codex','.agents','.aws'} for p in path.parts)):
        raise ValueError('UNSAFE_MAINTENANCE_PATH')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('UNSAFE_MAINTENANCE_FILE')
    return path


def existing_database(path):
    path=physical(path)
    if not path.is_file():raise ValueError('EXISTING_PRICE_DATABASE_REQUIRED')
    for suffix in ('-wal','-shm','-journal'):
        physical(str(path)+suffix)
    return path


def validate_plan(plan):
    payload = {k:v for k,v in plan.items() if k != 'plan_id'}
    if plan.get('format') != FORMAT or plan.get('plan_id') != digest(payload):
        raise ValueError('EXACT_FINALIZATION_PLAN_REQUIRED')
    rows = plan.get('rows', [])
    if not 1 <= len(rows) <= 96 or len({r['before']['id'] for r in rows}) != len(rows):
        raise ValueError('BOUNDED_UNIQUE_PROVISIONAL_ROWS_REQUIRED')
    if (any(type(r['before']['id']) is not int or r['before']['id'] <= 0 for r in rows) or
            len({(r['before']['osake'],r['before']['pvm']) for r in rows}) != len(rows)):
        raise ValueError('EXACT_UNIQUE_ROW_IDENTITIES_REQUIRED')
    if len({r['before']['pvm'] for r in rows}) != 1:
        raise ValueError('ONE_REVIEWED_SESSION_REQUIRED')
    session = rows[0]['before']['pvm']
    provisional = datetime.fromisoformat(plan['provisional_at'])
    final = datetime.fromisoformat(plan['final_observed_at'])
    if provisional.tzinfo is None or final.tzinfo is None:
        raise ValueError('AWARE_PROVENANCE_REQUIRED')
    if (not is_helsinki_session(session) or provisional.astimezone(HELSINKI).date().isoformat() != session or
            last_completed_helsinki_session(provisional) >= session or last_completed_helsinki_session(final) < session):
        raise ValueError('PROVEN_PROVISIONAL_AND_COMPLETED_SESSION_REQUIRED')
    hashes=[plan.get(k) for k in ['provider_evidence_hash','provisional_evidence_hash']]
    if any(not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):
        raise ValueError('IMMUTABLE_PROVIDER_AND_ORIGINAL_EVIDENCE_REQUIRED')
    for row in rows:
        before, after = row['before'], row['after']
        if set(before) != set(ROW_FIELDS) or set(after) != set(ROW_FIELDS):
            raise ValueError('EXACT_ROW_SHAPE_REQUIRED')
        if before['market'] != 'omxh' or any(before[k] != after[k] for k in ['id','osake','pvm','market']):
            raise ValueError('OMXH_IDENTITY_PRESERVATION_REQUIRED')
        if not before['osake'].endswith('.HE') and before['osake'] != '^OMXH25':
            raise ValueError('HELSINKI_INSTRUMENT_REQUIRED')
        if not valid_prices([after[k] for k in PRICE_FIELDS[:4]]) or not valid_volume(after['volume']):
            raise ValueError('VALID_FINAL_OHLCV_REQUIRED')
        if any(isinstance(after[k], bool) for k in PRICE_FIELDS):
            raise ValueError('NUMERIC_FINAL_OHLCV_REQUIRED')
        ratios = [after[k]/before[k] for k in PRICE_FIELDS[:4]] if valid_prices([before[k] for k in PRICE_FIELDS[:4]]) else []
        if ratios and max(ratios)-min(ratios) < 1e-6 and abs(sum(ratios)/4-1) > .1:
            raise ValueError('PROVISIONAL_UNIT_CHANGE_REQUIRES_SEPARATE_REVIEW')
    return rows


def prepare_omxh_finalization(*, database, originals, final_bars, provisional_at,
                              final_observed_at, provider_evidence_hash, provisional_evidence_hash):
    database = existing_database(database)
    finals = {(r['ticker'], r['date']): r for r in final_bars}
    if len(finals) != len(final_bars):
        raise ValueError('DUPLICATE_FINAL_OBSERVATION')
    rows = []
    with readonly(database) as c:
        for original in originals:
            before = {k:original[k] for k in ROW_FIELDS}
            current = c.execute('SELECT '+','.join(ROW_FIELDS)+' FROM osakedata WHERE id=?', (before['id'],)).fetchone()
            if current is None or dict(current) != before:
                raise ValueError('ORIGINAL_PROVISIONAL_ROW_CHANGED')
            final = finals.get((before['osake'],before['pvm']))
            if not final:
                continue  # Missing final observations remain untouched and explicit.
            rows.append(dict(before=before, after={**before, **{k:final[k] for k in PRICE_FIELDS}}))
    plan = dict(format=FORMAT,database=str(database),provisional_at=provisional_at,final_observed_at=final_observed_at,
                provider_evidence_hash=provider_evidence_hash,provisional_evidence_hash=provisional_evidence_hash,
                rows=rows,derived_obligation=dict(dow='REBUILD_REQUIRED',other_price_consumers='REVIEW_REQUIRED'))
    plan['plan_id'] = digest(plan)
    validate_plan(plan)
    return plan


def durable_json(path, data, *, exclusive=False):
    encoded = canonical(data)  # Reject nonfinite/unserializable evidence before creating a file.
    path = physical(path); path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive:
        try:
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if json.loads(path.read_text()) != data:
                raise ValueError('EXISTING_RESTORATION_EVIDENCE_CONFLICT')
            return
        with os.fdopen(fd,'w') as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    else:
        fd, temporary = tempfile.mkstemp(prefix='.price-receipt-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def apply_omxh_finalization(plan, *, evidence_dir, scheduler_log_dir, preflight, recover=False, fault=None):
    rows = validate_plan(plan); database = existing_database(plan['database']); evidence_dir=Path(evidence_dir)
    if datetime.fromisoformat(plan['final_observed_at']) > datetime.now(timezone.utc):
        raise ValueError('FUTURE_FINAL_OBSERVATION_NOT_ACCEPTED')
    if not callable(preflight): raise ValueError('FRESH_OPERATIONAL_PREFLIGHT_REQUIRED')
    from rawcandle.scheduler.runner import acquire_scheduler_lock_context
    with acquire_scheduler_lock_context(str(scheduler_log_dir)):
        preflight()
        original_path=evidence_dir/(plan['plan_id']+'.original.json')
        receipt_path=evidence_dir/(plan['plan_id']+'.result.json')
        if original_path.exists() and not receipt_path.exists() and not recover:
            raise ValueError('EXPLICIT_RECOVERY_REQUIRED_FOR_UNCERTAIN_ATTEMPT')
        durable_json(original_path,plan,exclusive=True)
        prior=None
        if receipt_path.exists():
            prior=json.loads(physical(receipt_path).read_text())
            if prior.get('status')=='RESTORED': raise ValueError('RESTORED_PLAN_CANNOT_AUTOMATICALLY_REAPPLY')
        c=sqlite3.connect(database,timeout=2);c.row_factory=sqlite3.Row
        changed=[];already=[]
        try:
            c.execute('PRAGMA foreign_keys=ON');c.execute('BEGIN IMMEDIATE')
            for row in rows:
                current=c.execute('SELECT '+','.join(ROW_FIELDS)+' FROM osakedata WHERE id=?',(row['before']['id'],)).fetchone()
                if current is None: raise ValueError('PROVISIONAL_ROW_MISSING')
                if dict(current)==row['after']:
                    already.append(row['before']['id']);continue
                if prior is not None:
                    raise ValueError('COMMITTED_FINALIZATION_ROW_CHANGED')
                if dict(current)!=row['before']: raise ValueError('PROVISIONAL_ROW_VERSION_CONFLICT')
                c.execute('UPDATE osakedata SET open=?,high=?,low=?,close=?,volume=? WHERE id=? AND osake=? AND pvm=? AND market=\'omxh\'',
                          tuple(row['after'][k] for k in PRICE_FIELDS)+(row['before']['id'],row['before']['osake'],row['before']['pvm']))
                if c.execute('SELECT changes()').fetchone()[0]!=1: raise ValueError('EXACT_ONE_ROW_REPLACEMENT_REQUIRED')
                changed.append(row['before']['id'])
                if fault: fault('after_row',len(changed))
            c.commit()
            if fault: fault('after_commit',len(changed))
        except BaseException:
            c.rollback();raise
        finally:c.close()
        result=dict(plan_id=plan['plan_id'],status='PRICE_COMMITTED_DERIVED_PENDING',replaced_rows=len(changed),
                    changed_row_ids=changed,already_final_row_ids=already,restoration_evidence=str(original_path),
                    derived_obligation=plan['derived_obligation'])
        if prior is None:
            durable_json(receipt_path,result)
        else:
            result['original_replaced_rows']=prior['replaced_rows']
        return result


def restore_omxh_finalization(plan, *, evidence_dir, scheduler_log_dir, preflight):
    rows=validate_plan(plan);database=existing_database(plan['database']);path=Path(evidence_dir)/(plan['plan_id']+'.original.json')
    if json.loads(physical(path).read_text())!=plan: raise ValueError('EXACT_RESTORATION_EVIDENCE_REQUIRED')
    from rawcandle.scheduler.runner import acquire_scheduler_lock_context
    with acquire_scheduler_lock_context(str(scheduler_log_dir)):
        preflight();c=sqlite3.connect(database,timeout=2);c.row_factory=sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE')
            for row in rows:
                current=c.execute('SELECT '+','.join(ROW_FIELDS)+' FROM osakedata WHERE id=?',(row['after']['id'],)).fetchone()
                if current is None or dict(current) not in (row['before'],row['after']):raise ValueError('RESTORATION_ROW_VERSION_CONFLICT')
                c.execute('UPDATE osakedata SET open=?,high=?,low=?,close=?,volume=? WHERE id=? AND osake=? AND pvm=? AND market=\'omxh\'',
                          tuple(row['before'][k] for k in PRICE_FIELDS)+(row['before']['id'],row['before']['osake'],row['before']['pvm']))
            c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
        durable_json(Path(evidence_dir)/(plan['plan_id']+'.result.json'),dict(plan_id=plan['plan_id'],status='RESTORED',derived_obligation=plan['derived_obligation']))
