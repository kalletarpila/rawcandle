"""Narrow terminal lifecycle for scheduler-owned EC pre-write images.

Unregistered, interrupted and failed images never expire automatically. The latest
accepted pre-write image remains the rollback point; only an earlier accepted
image for the same database/ecosystem/taxonomy can be superseded.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
from pathlib import Path

from rawcandle.io_atomic import write_text_atomic

SUFFIX = '.ec-owner.json'
FAMILY = ('analysis__ec_source_layer_backfill__', 'analysis__ec_source_layer_refresh__')


def _mount_points() -> set[str]:
    # is_mount() alone misses a same-filesystem bind mount of a regular file.
    return {
        re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), line.split()[4])
        for line in Path('/proc/self/mountinfo').read_text().splitlines()
    }


def file_identity(path: Path) -> dict:
    s = path.lstat()
    if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
            or s.st_uid != os.getuid() or path.is_mount() or str(path) in _mount_points()
            or path.parent.resolve() != path.parent
            or s.st_dev != path.parent.stat().st_dev):
        raise ValueError(f'Unsafe EC file identity: {path}')
    return {k: getattr(s, k) for k in (
        'st_dev', 'st_ino', 'st_nlink', 'st_uid', 'st_mode',
        'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_blocks')}


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _save(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        file_identity(path)
    write_text_atomic(path, json.dumps(value, indent=2, sort_keys=True) + '\n')
    # Atomic rename plus directory sync makes the release receipt durable.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def register_backup(path: Path, *, db_path: str, ecosystem: str, taxonomy: str) -> None:
    """Creation alone is never acceptance, including process death after copying."""
    path = path.absolute()
    identity = file_identity(path)
    manifest = Path(str(path) + SUFFIX)
    if manifest.exists() or manifest.is_symlink():
        raise ValueError('EC backup ownership already exists')
    _save(manifest, dict(version=1, path=str(path), identity=identity,
                        scope=[str(Path(db_path).resolve()), ecosystem, taxonomy],
                        state='RECOVERY_REQUIRED', sha256=_hash(path)))


def _accepted(summary: dict, path: Path) -> bool:
    # Overall scheduler FAILED/PARTIAL can be an independent Fundamentals result.
    # EC partial writes are BACKFILL_FAILED today and retain their rollback image.
    return (summary.get('ec_source_layer_backup_path') == str(path)
            and summary.get('ec_source_layer_status') in {'BACKFILL_COMPLETED', 'REFRESH_COMPLETED'}
            and summary.get('ec_bridge_status') == 'OK'
            and summary.get('ec_bridge_retry_required') is False
            and summary.get('ec_source_layer_coverage_status') in {'OK', 'OK_WITH_WARNINGS'}
            and summary.get('ec_source_layer_parity_status') in {'OK', 'OK_WITH_WARNINGS'}
            and summary.get('ec_source_layer_total_mismatch_count') == 0
            and summary.get('ec_source_layer_watermark_rows', 0) >= 4
            and bool(summary.get('finished_at_utc')))


def _load(path: Path) -> dict:
    file_identity(path)
    value = json.loads(path.read_text())
    if value.get('version') != 1:
        raise ValueError('Unknown EC receipt version')
    return value


def _verify(path: Path, owner: dict) -> None:
    if not path.name.startswith(FAMILY) or path.suffix != '.sqlite':
        raise ValueError('Not an EC source-layer image')
    if owner['path'] != str(path) or file_identity(path) != owner['identity']:
        raise ValueError('EC backup changed since creation')
    if any(Path(str(path) + suffix).exists() or Path(str(path) + suffix).is_symlink()
           for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('EC image has SQLite sidecars')
    if _hash(path) != owner['sha256']:
        raise ValueError('EC backup content changed')
    receipt = Path(owner['acceptance_path'])
    file_identity(receipt)
    if _hash(receipt) != owner['acceptance_sha256'] or not _accepted(json.loads(receipt.read_text()), path):
        raise ValueError('EC acceptance evidence changed')


def _not_open(path: Path) -> None:
    # Fail closed on missing lsof, warnings, permission failures or open handles.
    check = subprocess.run(['lsof', '-nP', '-t', '--', str(path)], capture_output=True, text=True)
    if check.returncode != 1 or check.stdout or check.stderr:
        raise ValueError('EC image has an open reference or ownership scan failed')


def terminal_retention(summary_path: str | Path) -> dict:
    """Called under the existing scheduler execution lock after durable reporting.

    No globbed SQLite deletion: only identity-bound, accepted owner receipts for
    this scope qualify. Errors retain evidence and are reported without changing
    an already committed production outcome. Re-entry retries partial unlink failures.
    """
    summary_path = Path(summary_path).absolute()
    summary = json.loads(summary_path.read_text())
    path = Path(str(summary.get('ec_source_layer_backup_path', 'NONE'))).absolute()
    result = {'deleted': [], 'held': []}
    if not _accepted(summary, path):
        return result
    manifest = Path(str(path) + SUFFIX)
    if not manifest.exists():
        return result  # Historical/unregistered recovery ownership is never inferred.
    lock_path = path.parent / '.ec-backup-retention.lock'
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        file_identity(lock_path)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner = _load(manifest)
        if owner['state'] == 'RETIRED':
            return result
        if owner['state'] not in {'RECOVERY_REQUIRED', 'ACCEPTED'}:
            result['held'].append({'owner': str(manifest), 'reason': 'UNRESOLVED_OWNER_STATE'})
            return result
        if owner.get('protection_reason'):
            result['held'].append({'owner': str(manifest), 'reason': owner['protection_reason']})
            return result
        hold_path = path.parent / '.ec-backup-retention-hold.json'
        if hold_path.exists() or hold_path.is_symlink():
            hold = _load(hold_path)
            if hold.get('scope') == owner['scope'] and hold.get('state') != 'RELEASED':
                result['held'].append({'owner': str(hold_path), 'reason': hold.get('reason', 'RECOVERY_HOLD')})
                return result
            if hold.get('scope') == owner['scope'] and hold.get('state') == 'RELEASED' and hold.get('general_recovery'):
                _qualified_general_point(hold)
        if not _publication_clear(owner['scope'][0]):
            result['held'].append({'owner': str(manifest), 'reason': 'UNRESOLVED_PUBLICATION_JOURNAL'})
            return result
        owner.update(acceptance_path=str(summary_path), acceptance_sha256=_hash(summary_path))
        try:
            _not_open(path)
        except ValueError as exc:
            result['held'].append({'owner': str(manifest), 'reason': str(exc)})
            return result
        _verify(path, owner)
        connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('Retained EC rollback image failed integrity')
        finally:
            connection.close()
        owner['state'] = 'ACCEPTED'
        _save(manifest, owner)
        for prior_manifest in sorted(path.parent.glob('*' + SUFFIX)):
            if prior_manifest == manifest:
                continue
            try:
                prior = _load(prior_manifest)
                if prior['state'] != 'ACCEPTED' or prior['scope'] != owner['scope']:
                    continue
                if prior.get('protection_reason'):
                    continue
                if (hold_path.exists() and hold.get('scope') == owner['scope']
                        and hold.get('general_recovery', {}).get('path') == prior.get('path')):
                    continue  # Explicit general recovery obligation outlives EC supersession.

                old = Path(prior['path'])
                if old.parent != path.parent or prior_manifest != Path(str(old) + SUFFIX):
                    raise ValueError('EC owner path mismatch')
                previous = json.loads(Path(prior['acceptance_path']).read_text())
                if previous.get('finished_at_utc', '') >= summary['finished_at_utc']:
                    continue  # Replaying an old terminal receipt cannot prune a later point.
                _verify(old, prior)
                _not_open(old)
                # Recheck immediately before the only destructive action.
                if file_identity(old) != prior['identity']:
                    raise ValueError('EC image changed before unlink')
                prior['retirement_authority'] = str(manifest)
                prior['state'] = 'RETIRE_PENDING'
                _save(prior_manifest, prior)
                try:
                    old.unlink()
                except OSError:
                    prior['state'] = 'ACCEPTED'
                    _save(prior_manifest, prior)
                    raise
                prior['state'] = 'RETIRED'
                _save(prior_manifest, prior)
                result['deleted'].append(str(old))
            except (OSError, ValueError, KeyError) as exc:
                result['held'].append({'owner': str(prior_manifest), 'reason': str(exc)})
                break  # Ownership/content ambiguity stops this destructive pass.
        return result
    finally:
        os.close(lock_fd)


def create_prewrite_backup(path: Path, *, db_path: str, ecosystem: str, taxonomy: str) -> Path:
    """Exclusive SQLite backup; failed copy scratch expires before any EC writes."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    reserved = file_identity(path)
    complete = False
    try:
        source = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            target = sqlite3.connect(str(path))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        complete = True
        register_backup(path, db_path=db_path, ecosystem=ecosystem, taxonomy=taxonomy)
        return path
    except BaseException as exc:
        if not complete:
            # A failed destination cannot restore anything, and no EC writer has
            # run yet. Preserve diagnostics first; unknown sidecars/owners hold it.
            try:
                current = file_identity(path)
                if any(current[k] != reserved[k] for k in ('st_dev', 'st_ino', 'st_uid')):
                    raise ValueError('Failed EC destination changed owner')
                if any(Path(str(path) + s).exists() or Path(str(path) + s).is_symlink()
                       for s in ('-wal', '-shm', '-journal')):
                    raise ValueError('Failed EC destination has diagnostic sidecars')
                _not_open(path)
                diagnostic = Path(str(path) + SUFFIX)
                value = dict(version=1, path=str(path), identity=current,
                             state='COPY_FAILED', error=f'{type(exc).__name__}: {exc}')
                _save(diagnostic, value)
                if file_identity(path) != current:
                    raise ValueError('Failed EC destination changed before unlink')
                path.unlink()
                value['state'] = 'SCRATCH_REMOVED'
                _save(diagnostic, value)
            except (OSError, ValueError):
                pass  # Keep ambiguous scratch; never conceal the original failure.
        raise


def protect_reused_backup(path: Path) -> None:
    """An explicit recovery/rebuild reuse starts a new rollback obligation."""
    path = path.absolute()
    manifest = Path(str(path) + SUFFIX)
    if not manifest.exists() and not manifest.is_symlink():
        return  # Unregistered images are already excluded from terminal pruning.
    lock = path.parent / '.ec-backup-retention.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        file_identity(lock)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner = _load(manifest)
        if file_identity(path) != owner['identity']:
            raise ValueError('Reused EC recovery image identity changed')
        owner.update(state='RECOVERY_REQUIRED', protection_reason='EXPLICIT_BACKUP_REUSE')
        _save(manifest, owner)
    finally:
        os.close(fd)


def _publication_clear(db_path: str) -> bool:
    """A completed EC branch cannot discharge an unresolved whole-DB publication."""
    journal = Path(db_path).parent / '.fundamentals_admin_publication_journal.json'
    if not journal.exists() and not journal.is_symlink():
        return True  # Databases outside the Fundamentals publication owner.
    file_identity(journal)
    value = json.loads(journal.read_text())
    return (value.get('state') == 'COMPLETED' and value.get('postflight_state') == 'PASSED'
            and value.get('rollback_recovery_state') in {'NOT_REQUIRED', 'COMPLETED', 'ROLLED_BACK'})


def _qualified_general_point(hold: dict) -> None:
    point = hold['general_recovery']
    if file_identity(Path(point['path'])) != point['identity']:
        raise ValueError('Qualified general Analysis recovery point changed')
    for suffix in ('-wal', '-journal'):
        sidecar = Path(point['path'] + suffix)
        if sidecar.is_symlink() or (sidecar.exists() and (suffix == '-journal' or sidecar.stat().st_size)):
            raise ValueError('General Analysis recovery image has unresolved sidecars')
    evidence = Path(hold['release_evidence_path'])
    file_identity(evidence)
    if _hash(evidence) != hold['release_evidence_sha256']:
        raise ValueError('Historical hold release evidence changed')
    for name, digest in hold['recovery_artifacts'].items():
        path = Path(name)
        file_identity(path)
        if _hash(path) != digest:
            raise ValueError('Required compact recovery evidence changed')


def release_historical_hold(hold_path: Path, *, release_evidence: Path, owner_guard) -> dict:
    """Supported BLOCKED -> RELEASED transition under qualified owner evidence.

    Caller holds existing Production/scheduler and temporary-cleanup ownership.
    Preserve the old hold and its reason; never unlink it to bypass recovery.
    """
    fd = os.open(hold_path.parent / '.ec-backup-retention.lock',
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        file_identity(hold_path.parent / '.ec-backup-retention.lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner_guard()
        hold = _load(hold_path)
        evidence = _load(release_evidence)
        if evidence['scope'] != hold['scope'] or evidence.get('result') != 'PASS':
            raise ValueError('Historical recovery qualification not accepted')
        for key in ('historical_obligations_discharged', 'decision_matrix_valid',
                    'retained_recovery_qualified', 'no_active_recovery'):
            if evidence.get(key) is not True:
                raise ValueError(f'Hold release prerequisite missing: {key}')
        ledger_path = Path(evidence['cleanup_execution_path'])
        ledger = _load(ledger_path)
        if (_hash(ledger_path) != evidence['cleanup_execution_sha256'] or ledger.get('state') != 'COMPLETE'
                or ledger.get('deleted_images') != evidence['approved_image_count']
                or ledger.get('deleted_allocated_bytes') != evidence['approved_allocated_bytes']
                or len(ledger['images']) != evidence['approved_image_count']):
            raise ValueError('Historical cleanup not reconciled')
        for name, item in ledger['images'].items():
            if item['state'] not in {'DELETED', 'RECONCILED_ABSENT'} or Path(name).exists() or Path(name).is_symlink():
                raise ValueError('Historical cleanup incomplete')
        qualification = Path(evidence['retained_qualification_path'])
        value = _load(qualification)
        if (_hash(qualification) != evidence['retained_qualification_sha256'] or value.get('result') != 'PASS'
                or value.get('quick_check') != 'ok' or value.get('schema_exact') is not True
                or value['path'] != evidence['general_recovery']['path']
                or value['identity'] != evidence['general_recovery']['identity']
                or value['sha256'] != evidence['general_recovery']['sha256']):
            raise ValueError('Required general Analysis image is not qualified')
        if not _publication_clear(hold['scope'][0]):
            raise ValueError('Unresolved publication journal')
        updated = dict(hold, state='RELEASED', previous_state=hold.get('previous_state', hold['state']),
                       release_reason='G-OPS-05 obligations qualified; G-OPS-06 exact cleanup reconciled',
                       release_evidence_path=str(release_evidence), release_evidence_sha256=_hash(release_evidence),
                       general_recovery=evidence['general_recovery'], recovery_artifacts=evidence['recovery_artifacts'])
        _qualified_general_point(updated)
        owner_guard()
        _save(hold_path, updated)
        return updated
    finally:
        os.close(fd)
