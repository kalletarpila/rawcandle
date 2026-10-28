"""Native ownership receipts exercise the shared cleanup owner, on copies only."""
from contextlib import nullcontext
import fcntl
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.admin import run_acceptance_cleanup as cleanup
from rawcandle.fundamentals.admin.production_transaction import production_lock
from tests.test_fundamentals_pb_ownership_publication import (
    setup, base_factory, do_publish, active, rotate,
)


@pytest.fixture
def published(setup):
    s = setup()
    preview = s['workflow'].preview(s['ids'])
    do_publish(s, preview)
    s['preview'] = preview
    s['run_id'] = preview['preview_id']
    s['lane'] = s['workflow'].lanes / s['run_id']
    s['kwargs'] = dict(run_root=s['workflow'].run_root,
                       backup_root=s['root'] / 'backups/fundamentals_admin_production',
                       journal_path=s['workflow'].journal_path, live_paths=active(s).role_paths())
    return s


def inspect(s):
    return cleanup.inspect_cleanup_eligibility(s['run_id'], **s['kwargs'])


def accept(s, lock_factory=nullcontext):
    return cleanup.accept_run_and_cleanup_backups(s['run_id'], **s['kwargs'], lock_factory=lock_factory)


def save(path, obj):
    path.write_text(json.dumps(obj))


def change_journal(s, mutate, *, archive=True):
    p = s['workflow'].journal_path
    j = json.loads(p.read_text())
    mutate(j)
    save(p, j)
    if archive:
        save(s['lane'] / 'completed_journal.json', j)


def test_native_receipts_select_exact_set_and_cleanup_preserves_all_other_files(published):
    s = published
    protected = s['kwargs']['backup_root'] / 'unrelated' / 'canonical.db'
    protected.parent.mkdir(); protected.write_bytes(b'unrelated')
    evidence = s['kwargs']['backup_root'] / s['run_id'] / 'publication_evidence' / 'report.json'
    evidence.parent.mkdir(); evidence.write_text('evidence')
    before = {p: p.read_bytes() for p in s['root'].rglob('*') if p.is_file()}
    eligible = inspect(s)
    assert eligible['status'] == 'ELIGIBLE' and eligible['run_kind'] == 'OWNERSHIP_PUBLICATION'
    selected = {s['kwargs']['backup_root'] / s['run_id'] / (r + '.db') for r in cleanup.KNOWN_ROLES}
    assert set(map(Path, eligible['backup_files'])) == selected and eligible['backup_count'] == 3
    assert eligible['bytes_freed'] == sum(p.stat().st_size for p in selected)
    result = accept(s)
    assert result['cleanup_outcome'] == 'COMPLETED' and result['run_kind'] == 'OWNERSHIP_PUBLICATION'
    assert set(map(Path, result['files_deleted'])) == selected
    assert result['bytes_freed'] == eligible['bytes_freed']
    assert result['published_generation_id'] == s['run_id']
    assert result['ownership_preview_hash'] == s['preview']['preview_hash']
    for path, content in before.items():
        assert not path.exists() if path in selected else path.read_bytes() == content
    assert inspect(s)['status'] == 'ALREADY_CLEANED'
    assert accept(s)['status'] == 'ALREADY_CLEANED'
    assert (s['lane'] / cleanup.CLEANUP_EVIDENCE_NAME).is_file()


@pytest.mark.parametrize(('field', 'value'), [
    ('state', 'PREPARED'), ('state', 'RECOVERED'), ('postflight_state', 'FAILED'),
    ('rollback_recovery_state', 'REQUIRED'), ('generation_activation_state', 'READY'),
    ('production_run_id', 'other'), ('new_generation_id', 'other'),
    ('operation_type', 'UNKNOWN'), ('refresh_set_fingerprint', 'a' * 64),
])
def test_terminal_owner_and_recovery_failure_refuse_all_deletion(published, field, value):
    s = published
    change_journal(s, lambda j: j.update({field: value}))
    assert inspect(s)['status'] == 'NOT_ELIGIBLE'
    with pytest.raises(cleanup.RunAcceptanceCleanupError):
        accept(s)
    assert all((s['kwargs']['backup_root'] / s['run_id'] / (r + '.db')).is_file() for r in cleanup.KNOWN_ROLES)


@pytest.mark.parametrize('mutation', [
    'missing_role', 'extra_role', 'owner', 'old_source', 'hash', 'missing_backup',
    'extra_backup', 'symlink', 'hardlink', 'sidecar', 'preview', 'scope',
    'archive_disagrees', 'duplicate_root', 'active_changed', 'live_changed', 'old_changed',
])
def test_provenance_and_generation_fail_closed(published, mutation):
    s = published
    backup = s['kwargs']['backup_root'] / s['run_id'] / 'provider.db'
    if mutation == 'missing_role':
        change_journal(s, lambda j: j['roles'].pop('provider'))
    elif mutation == 'extra_role':
        change_journal(s, lambda j: j['roles'].update(unrelated=j['roles']['provider']))
    elif mutation == 'owner':
        change_journal(s, lambda j: j['roles']['provider'].update(backup_path=str(backup.parent.parent / 'other/provider.db')))
    elif mutation == 'old_source':
        change_journal(s, lambda j: j['old_generation']['roles'].update(provider=str(backup)))
    elif mutation == 'hash':
        change_journal(s, lambda j: j['roles']['provider'].update(verified_backup_fingerprint='f' * 64))
    elif mutation == 'missing_backup': backup.unlink()
    elif mutation == 'extra_backup': (backup.parent / 'unrelated.db').write_bytes(b'extra')
    elif mutation == 'symlink':
        backup.unlink(); backup.symlink_to(active(s).role_paths()['provider'])
    elif mutation == 'hardlink':
        backup.unlink(); backup.hardlink_to(active(s).role_paths()['provider'])
    elif mutation == 'sidecar': Path(str(backup) + '-wal').write_bytes(b'busy')
    elif mutation == 'preview':
        p = s['lane'] / 'preview.json'; v = json.loads(p.read_text()); v['selection'] = ['other']; save(p, v)
    elif mutation == 'scope': change_journal(s, lambda j: j['scope_evidence'].update(selected=[]))
    elif mutation == 'archive_disagrees': change_journal(s, lambda j: j.update(updated_at_utc='changed'), archive=False)
    elif mutation == 'duplicate_root': (s['workflow'].run_root / s['run_id']).mkdir()
    elif mutation == 'active_changed': rotate(s)
    elif mutation in {'live_changed', 'old_changed'}:
        path = active(s).role_paths()['provider'] if mutation == 'live_changed' else Path(json.loads(s['workflow'].journal_path.read_text())['old_generation']['roles']['provider'])
        with sqlite3.connect(path) as c: c.execute('CREATE TABLE unexpected (value TEXT)')
    assert inspect(s)['status'] == 'NOT_ELIGIBLE'
    remaining = {p: p.read_bytes() for p in backup.parent.iterdir() if p.is_file()}
    with pytest.raises(cleanup.RunAcceptanceCleanupError): accept(s)
    assert all(p.read_bytes() == content for p, content in remaining.items())


def test_changed_receipt_at_delete_boundary_refuses_every_file(published, monkeypatch):
    s = published
    original = cleanup._load_acceptance_result
    calls = 0
    def changed(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            change_journal(s, lambda j: j['scope_evidence'].update(selected=[]))
        return original(**kwargs)
    monkeypatch.setattr(cleanup, '_load_acceptance_result', changed)
    with pytest.raises(cleanup.RunAcceptanceCleanupError): accept(s)
    assert all((s['kwargs']['backup_root'] / s['run_id'] / (r + '.db')).is_file() for r in cleanup.KNOWN_ROLES)


def test_real_production_lock_conflict_prevents_cleanup(published):
    s = published
    lock = s['root'] / 'temp/.fundamentals_admin_production.lock'
    def factory(): return production_lock(lock_path=lock, scheduler_log_dir=str(s['root'] / 'scheduler_logs'))
    with lock.open('r') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='ALREADY_RUNNING'): accept(s, lock_factory=factory)
    assert inspect(s)['status'] == 'ELIGIBLE'
