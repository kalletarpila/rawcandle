"""Explicit, identity-bound retirement of an owner-qualified historical allowlist.

No discovery supplies deletion authority. The caller must hold the production,
scheduler and existing temporary-cleanup locks and supply a fresh owner guard.
SQLite sidecars are recorded and preserved, never inferred disposable here.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Callable

from rawcandle import ec_backup_retention as retention

SIDECARS = ('-wal', '-shm', '-journal')


def historical_identity(value: dict) -> dict:
    mapping = dict(dev='st_dev', inode='st_ino', nlink='st_nlink', uid='st_uid',
                   mode='st_mode', size='st_size', mtime_ns='st_mtime_ns', ctime_ns='st_ctime_ns')
    return {target: value[source] for source, target in mapping.items()} | {
        'st_blocks': value['allocated'] // 512}


def sidecars(path: Path) -> list[dict]:
    found = []
    for suffix in SIDECARS:
        p = Path(str(path) + suffix)
        if p.exists() or p.is_symlink():
            identity = retention.file_identity(p)
            if suffix == '-journal' or (suffix == '-wal' and identity['st_size']):
                raise ValueError('Unresolved SQLite recovery sidecar')
            retention._not_open(p)
            found.append(dict(path=str(p), identity=identity, sha256=retention._hash(p)))
    return found


def _verify_image(record: dict) -> None:
    path = Path(record['path'])
    if str(path.resolve()) != str(path) or not path.name.startswith(retention.FAMILY) or path.suffix != '.sqlite':
        raise ValueError('Unsafe historical image path')
    if retention.file_identity(path) != record['identity']:
        raise ValueError('Historical image identity changed')
    retention._not_open(path)
    if sidecars(path) != record['sidecars']:
        raise ValueError('Historical image sidecars changed')
    known = {str(path)} | {r['path'] for r in record['sidecars']}
    # An unqualified receipt or other associated file starts a new obligation.
    if any(str(p) not in known for p in path.parent.iterdir() if p.name.startswith(path.name)):
        raise ValueError('Unknown associated historical image file')


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def retire_approved_images(plan_path: Path, *, proposal_sha256: str,
                          owner_guard: Callable[[], None]) -> dict:
    """Reconcile a durable exact plan; an interrupted unlink can be resumed.

    Content hashes from prior qualification are reused only under full unchanged
    inode/size/ctime/mtime/allocation witnesses. No new/unlisted image is selected.
    """
    plan = retention._load(plan_path)
    proposal_path = Path(plan['proposal_path'])
    retention.file_identity(proposal_path)
    if retention._hash(proposal_path) != proposal_sha256 or plan['proposal_sha256'] != proposal_sha256:
        raise ValueError('Approved proposal changed')
    proposal = json.loads(proposal_path.read_text())
    expected = {r['path']: r for r in proposal['candidates']}
    records = plan['candidates']
    if len(expected) != len(records) or {r['path'] for r in records} != set(expected):
        raise ValueError('Deletion allowlist differs from approved proposal')
    if plan['retained']['path'] not in proposal['retained'] or plan['retained']['path'] in expected:
        raise ValueError('Required recovery image selected for deletion')
    for r in records:
        original = expected[r['path']]
        if (r['identity'] != historical_identity(original['identity']) or r['sha256'] != original['sha256']
                or r['allocated_bytes'] != original['allocated_bytes'] or r['decision'] != 'RETIRE_CANDIDATE'):
            raise ValueError('Approved candidate identity changed in plan')
    total = sum(r['allocated_bytes'] for r in records)
    if total != proposal['expected_reclaimed_allocated_bytes']:
        raise ValueError('Approved allocation mismatch')
    directories = {Path(r['path']).parent for r in records} | {Path(plan['retained']['path']).parent}
    if len(directories) != 1:
        raise ValueError('Historical images have different owners')
    directory = directories.pop()
    lock = directory / '.ec-backup-retention.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        retention.file_identity(lock)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner_guard()
        _verify_image(plan['retained'])
        ledger_path = Path(str(plan_path) + '.execution.json')
        plan_hash = retention._hash(plan_path)
        if ledger_path.exists() or ledger_path.is_symlink():
            ledger = retention._load(ledger_path)
            if ledger['plan_sha256'] != plan_hash:
                raise ValueError('Cleanup restart plan changed')
        else:
            ledger = dict(version=1, plan_sha256=plan_hash, state='PLANNED',
                          images={r['path']: dict(state='PENDING', allocated_bytes=r['allocated_bytes']) for r in records})
            retention._save(ledger_path, ledger)
        if set(ledger['images']) != set(expected):
            raise ValueError('Cleanup ledger differs from allowlist')
        # Validate the entire remaining set before the first unlink.
        for r in records:
            p = Path(r['path']); item = ledger['images'][str(p)]
            if not p.exists() and not p.is_symlink():
                if item['state'] not in {'UNLINK_PENDING', 'DELETED', 'RECONCILED_ABSENT'}:
                    raise ValueError('Candidate absent without durable deletion intent')
            else:
                if item['state'] in {'DELETED', 'RECONCILED_ABSENT'}:
                    raise ValueError('Deleted candidate path reappeared')
                _verify_image(r)
        for r in records:
            p = Path(r['path']); item = ledger['images'][str(p)]
            try:
                owner_guard()
                _verify_image(plan['retained'])
                if not p.exists() and not p.is_symlink():
                    if item['state'] == 'UNLINK_PENDING':
                        item['state'] = 'RECONCILED_ABSENT'
                        _sync_directory(directory)
                        retention._save(ledger_path, ledger)
                    continue
                _verify_image(r)
                item['state'] = 'UNLINK_PENDING'
                retention._save(ledger_path, ledger)
                # All cooperating owners are excluded; check once more after intent persistence.
                if retention.file_identity(p) != r['identity']:
                    raise ValueError('Image changed immediately before unlink')
                p.unlink()
                _sync_directory(directory)
                item['state'] = 'DELETED'
                retention._save(ledger_path, ledger)
            except (OSError, ValueError, RuntimeError) as exc:
                ledger.update(state='PARTIAL', blocker=str(exc))
                retention._save(ledger_path, ledger)
                return ledger
        ledger.update(state='COMPLETE', deleted_images=len(records), deleted_allocated_bytes=total,
                      sidecars_deleted=0, retained=plan['retained'])
        ledger.pop('blocker', None)
        retention._save(ledger_path, ledger)
        return ledger
    finally:
        os.close(fd)
