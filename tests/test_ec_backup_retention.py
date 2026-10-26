import json
import os
import sqlite3
from pathlib import Path

import pytest

from rawcandle import ec_backup_retention as retention


@pytest.fixture
def points(tmp_path):
    def make(number, **changes):
        path = tmp_path / f'analysis__ec_source_layer_backfill__fixture__{number}.sqlite'
        with sqlite3.connect(path) as connection:
            connection.execute('create table ec_fact(value integer)')
            connection.execute('insert into ec_fact values (?)', (number,))
        retention.register_backup(path, db_path=str(tmp_path / 'live.db'), ecosystem='EC', taxonomy='V1')
        summary = dict(ec_source_layer_backup_path=str(path), ec_source_layer_status='BACKFILL_COMPLETED',
                       ec_bridge_status='OK', ec_bridge_retry_required=False,
                       ec_source_layer_coverage_status='OK', ec_source_layer_parity_status='OK_WITH_WARNINGS',
                       ec_source_layer_total_mismatch_count=0, ec_source_layer_watermark_rows=4,
                       finished_at_utc=f'2026-10-{number:02}T04:00:00Z', overall_status='OK')
        summary.update(changes)
        receipt = tmp_path / f'summary{number}.json'
        receipt.write_text(json.dumps(summary))
        return path, receipt
    return make


def test_accepted_supersedes_only_closed_scope_and_is_idempotent(points, tmp_path):
    old, first = points(1)
    unresolved, _ = points(2)
    unrelated = tmp_path / 'forecasts.sqlite'
    unrelated.write_bytes(b'protected')
    assert retention.terminal_retention(first)['deleted'] == []
    new, second = points(3)
    assert retention.terminal_retention(second)['deleted'] == [str(old)]
    assert new.exists() and unresolved.exists() and unrelated.read_bytes() == b'protected'
    assert retention.terminal_retention(second)['deleted'] == []
    assert retention.terminal_retention(first)['deleted'] == []
    assert json.loads(Path(str(old) + retention.SUFFIX).read_text())['state'] == 'RETIRED'
    with sqlite3.connect(f'file:{new}?mode=ro', uri=True) as connection:
        assert connection.execute('select value from ec_fact').fetchall() == [(3,)]


@pytest.mark.parametrize('overall', ['OK', 'PARTIAL', 'FAILED', 'OK_WITH_WARNINGS'])
def test_accepted_ec_with_independent_scheduler_outcome(points, overall):
    old, first = points(1)
    retention.terminal_retention(first)
    new, receipt = points(2, overall_status=overall)
    assert retention.terminal_retention(receipt)['deleted'] == [str(old)]
    assert new.exists()


@pytest.mark.parametrize('changes', [
    {'ec_source_layer_status': 'BACKFILL_FAILED'},
    {'ec_source_layer_status': 'CANCELLED'},
    {'ec_source_layer_status': 'PARTIAL'},
    {'ec_bridge_retry_required': True},
    {'finished_at_utc': None},
    {'ec_source_layer_watermark_rows': 0},
    {'ec_source_layer_total_mismatch_count': 1},
])
def test_failed_cancelled_partial_interrupted_preserve(points, changes):
    old, first = points(1)
    retention.terminal_retention(first)
    new, receipt = points(2, **changes)
    assert retention.terminal_retention(receipt)['deleted'] == []
    assert old.exists() and new.exists()


@pytest.mark.parametrize('hazard', ['symlink', 'hardlink', 'sidecar', 'changed', 'owner', 'open', 'mount'])
def test_candidate_hazards_fail_closed(points, tmp_path, monkeypatch, hazard):
    old, first = points(1)
    retention.terminal_retention(first)
    if hazard == 'symlink':
        moved = tmp_path / 'saved.sqlite'
        old.rename(moved)
        old.symlink_to(moved)
    elif hazard == 'hardlink':
        os.link(old, tmp_path / 'alias.sqlite')
    elif hazard == 'sidecar':
        Path(str(old) + '-journal').write_bytes(b'diagnostic')
    elif hazard == 'changed':
        old.touch()
    elif hazard == 'mount':
        monkeypatch.setattr(retention, '_mount_points', lambda: {str(old)})
    elif hazard == 'owner':
        owner = Path(str(old) + retention.SUFFIX)
        content = owner.read_text()
        owner.unlink()
        target = tmp_path / 'owner.json'
        target.write_text(content)
        owner.symlink_to(target)
    else:
        def busy(_):
            raise ValueError('active recovery owner')
        monkeypatch.setattr(retention, '_not_open', busy)
    _, receipt = points(2)
    result = retention.terminal_retention(receipt)
    assert not result['deleted'] and result['held']
    assert old.exists()


def test_active_cleanup_owner_protected(points):
    import fcntl
    old, receipt = points(1)
    lock = old.parent / '.ec-backup-retention.lock'
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            retention.terminal_retention(receipt)
    assert old.exists()


def test_partial_unlink_failure_retries_other_candidates(points, monkeypatch):
    old, first = points(1)
    retention.terminal_retention(first)
    new, second = points(2)
    unlink = Path.unlink
    def fail(path, *args, **kwargs):
        if path == old:
            raise PermissionError('injected')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail)
    assert retention.terminal_retention(second)['held']
    assert old.exists() and new.exists()
    monkeypatch.setattr(Path, 'unlink', unlink)
    assert retention.terminal_retention(second)['deleted'] == [str(old)]


def test_invalid_retained_image_never_releases_old(points):
    old, first = points(1)
    retention.terminal_retention(first)
    new, receipt = points(2)
    new.write_bytes(b'broken')
    with pytest.raises(ValueError):
        retention.terminal_retention(receipt)
    assert old.exists()


def test_unregistered_and_other_scope_preserved(points, tmp_path):
    old, first = points(1)
    owner = Path(str(old) + retention.SUFFIX)
    value = json.loads(owner.read_text())
    value['scope'][2] = 'OTHER'
    owner.write_text(json.dumps(value))
    retention.terminal_retention(first)
    _, second = points(2)
    unknown = tmp_path / 'analysis__ec_source_layer_refresh__unknown.sqlite'
    unknown.write_bytes(b'unknown')
    retention.terminal_retention(second)
    assert old.exists() and unknown.read_bytes() == b'unknown'


def test_real_open_file_scan_protects(points):
    old, first = points(1)
    retention.terminal_retention(first)
    _, second = points(2)
    with old.open('rb'):
        assert retention.terminal_retention(second)['held']
    assert old.exists()


def test_backup_creation_is_exclusive_and_registered(tmp_path, monkeypatch):
    from rawcandle.cli.run_ec_source_layer_backfill import _create_backup
    monkeypatch.setattr('rawcandle.cli.run_ec_source_layer_backfill._backup_filename',
                        lambda **_: 'analysis__ec_source_layer_backfill__fixed.sqlite')
    db = tmp_path / 'analysis.db'
    with sqlite3.connect(db) as conn:
        conn.execute('create table fixture(value)')
        conn.execute('insert into fixture values (42)')
    args = dict(db_path=str(db), backup_dir=tmp_path, ecosystem_code='EC',
                taxonomy_version_code='V1', date_from='2026-10-01', date_to='2026-10-02')
    path = _create_backup(**args)
    assert json.loads(Path(str(path) + retention.SUFFIX).read_text())['state'] == 'RECOVERY_REQUIRED'
    with pytest.raises(FileExistsError):
        _create_backup(**args)
    assert sqlite3.connect(path).execute('select value from fixture').fetchone() == (42,)


def test_windows_cleanup_coexists_without_touching_ec(points, tmp_path):
    import shlex
    import subprocess
    import time
    old, first = points(1)
    retention.terminal_retention(first)
    empty = tmp_path / 'analysis__ec_source_layer_refresh__interrupted.sqlite'
    empty.touch()
    unknown = tmp_path / 'forecasts.sqlite'
    unknown.write_bytes(b'protected forecast')
    ancient = time.time() - 40 * 86400
    os.utime(empty, (ancient, ancient))
    script = Path('scripts/rawcandle_temp_cleanup.sh').read_text()
    script = script.replace('TEMP_DIR="/home/kalle/projects/rawcandle/temp"',
                            'TEMP_DIR=' + shlex.quote(str(tmp_path)))
    script = script.replace('LOG_DIR="/home/kalle/logs/rawcandle_temp_cleanup"',
                            'LOG_DIR=' + shlex.quote(str(tmp_path / 'logs')))
    script = script.replace('LOCK_FILE="/tmp/rawcandle_temp_cleanup.lock"',
                            'LOCK_FILE=' + shlex.quote(str(tmp_path / 'cleanup.lock')))
    subprocess.run(['bash', '-c', script, 'fixture', '--apply'], check=True, capture_output=True)
    assert old.exists() and empty.exists() and unknown.read_bytes() == b'protected forecast'


def test_failed_copy_removes_only_owned_scratch(tmp_path):
    destination = tmp_path / 'analysis__ec_source_layer_backfill__failed.sqlite'
    other = tmp_path / 'forecast.sqlite'
    other.write_bytes(b'protected')
    with pytest.raises(sqlite3.OperationalError):
        retention.create_prewrite_backup(destination, db_path=str(tmp_path / 'missing.db'),
                                         ecosystem='EC', taxonomy='V1')
    assert not destination.exists() and other.read_bytes() == b'protected'
    assert json.loads(Path(str(destination) + retention.SUFFIX).read_text())['state'] == 'SCRATCH_REMOVED'


def test_explicit_recovery_reuse_reopens_obligation(points):
    old, first = points(1)
    retention.terminal_retention(first)
    retention.protect_reused_backup(old)
    assert retention.terminal_retention(first)['held']
    _, second = points(2)
    assert retention.terminal_retention(second)['deleted'] == []
    assert old.exists()


def test_crash_during_retirement_is_not_inferred_closed(points):
    old, first = points(1)
    retention.terminal_retention(first)
    owner = Path(str(old) + retention.SUFFIX)
    value = json.loads(owner.read_text())
    value['state'] = 'RETIRE_PENDING'
    owner.write_text(json.dumps(value))
    assert retention.terminal_retention(first)['held']
    _, second = points(2)
    assert retention.terminal_retention(second)['deleted'] == []
    assert old.exists()


def test_unresolved_scope_hold_blocks_even_complete_ec_acceptance(points):
    old, first = points(1)
    retention.terminal_retention(first)
    owner = json.loads(Path(str(old) + retention.SUFFIX).read_text())
    hold = old.parent / '.ec-backup-retention-hold.json'
    hold.write_text(json.dumps(dict(version=1, scope=owner['scope'], state='BLOCKED_UNCERTAIN',
                                    reason='Historical semantic and required-lineage mismatch')))
    new, second = points(2)
    result = retention.terminal_retention(second)
    assert not result['deleted'] and result['held']
    assert old.exists() and new.exists()
    assert json.loads(Path(str(new) + retention.SUFFIX).read_text())['state'] == 'RECOVERY_REQUIRED'


def released_hold(point):
    evidence = point.parent / 'qualified_release.json'
    evidence.write_text('{"qualification":"fixture"}')
    hold = point.parent / '.ec-backup-retention-hold.json'
    owner = json.loads(Path(str(point)+retention.SUFFIX).read_text())
    hold.write_text(json.dumps(dict(version=1, state='RELEASED', scope=owner['scope'],
        general_recovery=dict(path=str(point), identity=retention.file_identity(point), sha256=retention._hash(point)),
        release_evidence_path=str(evidence), release_evidence_sha256=retention._hash(evidence), recovery_artifacts={})))
    return hold


def test_released_hold_preserves_general_point_and_bounds_later_accepted_images(points):
    general, first = points(1)
    retention.terminal_retention(first)
    released_hold(general)
    previous, second = points(2, overall_status='PARTIAL')
    assert retention.terminal_retention(second)['deleted'] == []
    newest, third = points(3)
    assert retention.terminal_retention(third)['deleted'] == [str(previous)]
    assert general.exists() and newest.exists()


@pytest.mark.parametrize('hazard', ['image', 'evidence', 'wal'])
def test_released_hold_blocks_if_general_recovery_loses_qualification(points, hazard):
    general, first = points(1); retention.terminal_retention(first)
    released_hold(general)
    if hazard == 'image': general.touch()
    elif hazard == 'evidence': (general.parent/'qualified_release.json').write_text('changed')
    else: Path(str(general)+'-wal').write_bytes(b'unresolved')
    new, second = points(2)
    with pytest.raises(ValueError): retention.terminal_retention(second)
    assert general.exists() and new.exists()


@pytest.mark.parametrize('state', ['PREPARED', 'PUBLISHING', 'RECOVERY_REQUIRED', 'FAILED'])
def test_unresolved_publication_protects_ec_accepted_images(points, state):
    old, first = points(1); retention.terminal_retention(first)
    journal = old.parent/'.fundamentals_admin_publication_journal.json'
    journal.write_text(json.dumps(dict(state=state, postflight_state='PASSED', rollback_recovery_state='NOT_REQUIRED')))
    new, second = points(2, overall_status='PARTIAL')
    result = retention.terminal_retention(second)
    assert not result['deleted'] and result['held'][0]['reason'] == 'UNRESOLVED_PUBLICATION_JOURNAL'
    assert old.exists() and new.exists()
    journal.write_text(json.dumps(dict(state='COMPLETED', postflight_state='PASSED', rollback_recovery_state='NOT_REQUIRED')))
    assert retention.terminal_retention(second)['deleted'] == [str(old)]
