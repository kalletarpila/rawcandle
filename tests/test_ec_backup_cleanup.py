import json
import os
import sqlite3
from pathlib import Path

import pytest

from rawcandle import ec_backup_cleanup as cleanup
from rawcandle import ec_backup_retention as retention


@pytest.fixture
def approved(tmp_path):
    candidates = []
    records = []
    for number in range(24):
        path = tmp_path / f'analysis__ec_source_layer_backfill__approved__{number}.sqlite'
        with sqlite3.connect(path) as c:
            c.execute('create table fact(value)')
            c.execute('insert into fact values (?)', (number,))
        i = retention.file_identity(path)
        old = dict(path=str(path), dev=i['st_dev'], inode=i['st_ino'], nlink=i['st_nlink'], uid=i['st_uid'],
                   mode=i['st_mode'], size=i['st_size'], mtime_ns=i['st_mtime_ns'], ctime_ns=i['st_ctime_ns'], allocated=i['st_blocks']*512)
        row = dict(path=str(path), identity=i, sha256=retention._hash(path), sidecars=[],
                   allocated_bytes=i['st_blocks']*512, decision='RETIRE_CANDIDATE')
        if number < 23:
            records.append(row)
            candidates.append(dict(path=str(path), identity=old, sha256=row['sha256'], allocated_bytes=row['allocated_bytes']))
        else:
            retained = row
    proposal = tmp_path / 'proposal.json'
    retention._save(proposal, dict(version=1, candidates=candidates, retained=[retained['path']],
                                   expected_reclaimed_allocated_bytes=sum(r['allocated_bytes'] for r in records)))
    plan = tmp_path / 'plan.json'
    retention._save(plan, dict(version=1, proposal_path=str(proposal), proposal_sha256=retention._hash(proposal),
                              candidates=records, retained=retained))
    # Real open-file protection has its own integration test; keep this 24-image matrix fast.
    return plan, retention._hash(proposal)


def apply(approved, guard=lambda: None):
    plan, digest = approved
    return cleanup.retire_approved_images(plan, proposal_sha256=digest, owner_guard=guard)


def test_exact_23_reconciliation_idempotence_and_unrelated_preservation(approved, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    other = tmp_path/'forecast.sqlite'; other.write_bytes(b'keep')
    result = apply(approved)
    assert result['state'] == 'COMPLETE' and result['deleted_images'] == 23
    assert result['deleted_allocated_bytes'] == sum(v['allocated_bytes'] for v in result['images'].values())
    assert Path(result['retained']['path']).exists() and other.read_bytes() == b'keep'
    assert apply(approved) == result


@pytest.mark.parametrize('hazard', ['extra', 'required', 'identity', 'sidecar', 'journal', 'missing', 'associated', 'proposal'])
def test_whole_set_rejected_before_any_deletion(approved, monkeypatch, hazard):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    plan, _ = approved
    value = json.loads(plan.read_text()); last = Path(value['candidates'][-1]['path'])
    if hazard == 'extra':
        value['candidates'].append(value['retained'])
    elif hazard == 'required':
        value['retained'] = value['candidates'][0]
    elif hazard == 'identity':
        last.touch()
    elif hazard == 'sidecar':
        Path(str(last)+'-wal').write_bytes(b'committed?')
    elif hazard == 'journal':
        Path(str(last)+'-journal').write_bytes(b'rollback')
    elif hazard == 'missing':
        last.unlink()
    elif hazard == 'associated':
        Path(str(last)+'.unknown').write_bytes(b'unknown')
    elif hazard == 'proposal':
        Path(value['proposal_path']).write_text('{}')
    retention._save(plan, value)
    with pytest.raises((ValueError, FileNotFoundError)):
        apply(approved)
    assert Path(value['candidates'][0]['path']).exists()


def test_idle_sidecars_are_bound_and_preserved(approved, monkeypatch):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    plan, _ = approved; value = json.loads(plan.read_text())
    p = Path(value['candidates'][0]['path']); wal = Path(str(p)+'-wal'); shm = Path(str(p)+'-shm')
    wal.write_bytes(b''); shm.write_bytes(b'reader metadata')
    value['candidates'][0]['sidecars'] = cleanup.sidecars(p); retention._save(plan, value)
    assert apply(approved)['state'] == 'COMPLETE'
    assert wal.exists() and shm.read_bytes() == b'reader metadata'


def test_active_owner_prevents_all_deletion(approved):
    def busy(): raise RuntimeError('active owner')
    with pytest.raises(RuntimeError, match='active owner'): apply(approved, busy)
    value = json.loads(approved[0].read_text())
    assert all(Path(r['path']).exists() for r in value['candidates'])


def test_owner_start_mid_pass_stops_with_partial(approved, monkeypatch):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    calls = 0
    def owner():
        nonlocal calls
        calls += 1
        if calls > 2: raise RuntimeError('owner began')
    result = apply(approved, owner)
    assert result['state'] == 'PARTIAL'
    assert sum(r['state'] == 'DELETED' for r in result['images'].values()) == 1
    assert apply(approved)['state'] == 'COMPLETE'


def test_crash_after_unlink_reconciles_durable_intent(approved, monkeypatch):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    unlink = Path.unlink; calls = []
    def crash(p, *args, **kwargs):
        unlink(p, *args, **kwargs)
        calls.append(str(p))
        raise KeyboardInterrupt('crash after unlink')
    monkeypatch.setattr(Path, 'unlink', crash)
    with pytest.raises(KeyboardInterrupt): apply(approved)
    monkeypatch.setattr(Path, 'unlink', unlink)
    result = apply(approved)
    assert result['state'] == 'COMPLETE'
    assert result['images'][calls[0]]['state'] == 'RECONCILED_ABSENT'


def release_fixture(approved):
    plan, _ = approved; value = json.loads(plan.read_text()); result = apply(approved)
    retained = value['retained']; directory = plan.parent
    qualification = directory/'qualification.json'
    retention._save(qualification, dict(version=1, result='PASS', path=retained['path'], identity=retained['identity'],
                                       sha256=retained['sha256'], quick_check='ok', schema_exact=True))
    scope = [str(directory/'live.db'), 'EC', 'V1']
    hold = directory/'.ec-backup-retention-hold.json'
    retention._save(hold, dict(version=1, state='BLOCKED_UNCERTAIN', scope=scope, reason='historical'))
    evidence = directory/'release.json'; ledger = Path(str(plan)+'.execution.json')
    retention._save(evidence, dict(version=1, scope=scope, result='PASS', historical_obligations_discharged=True,
        decision_matrix_valid=True, retained_recovery_qualified=True, no_active_recovery=True,
        cleanup_execution_path=str(ledger), cleanup_execution_sha256=retention._hash(ledger),
        approved_image_count=23, approved_allocated_bytes=result['deleted_allocated_bytes'],
        retained_qualification_path=str(qualification), retained_qualification_sha256=retention._hash(qualification),
        general_recovery={k:retained[k] for k in ['path','identity','sha256']},
        recovery_artifacts={str(plan):retention._hash(plan)}))
    return hold, evidence


@pytest.mark.parametrize('hazard', [None, 'prerequisite', 'image', 'evidence', 'journal', 'ledger', 'active'])
def test_hold_release_requires_recovery_invariants(approved, monkeypatch, hazard):
    monkeypatch.setattr(retention, '_not_open', lambda p: None)
    hold, evidence = release_fixture(approved); e = json.loads(evidence.read_text())
    if hazard == 'prerequisite': e['historical_obligations_discharged'] = False
    elif hazard == 'image': Path(e['general_recovery']['path']).touch()
    elif hazard == 'evidence': next(iter(e['recovery_artifacts'])); e['recovery_artifacts'][str(approved[0])] = 'bad'
    elif hazard == 'journal': (hold.parent/'.fundamentals_admin_publication_journal.json').write_text('{"state":"PUBLISHING"}')
    elif hazard == 'ledger': Path(e['cleanup_execution_path']).write_text('{}')
    retention._save(evidence, e)
    def guard():
        if hazard == 'active': raise RuntimeError('active recovery')
    if hazard:
        with pytest.raises((ValueError, KeyError, RuntimeError)):
            retention.release_historical_hold(hold, release_evidence=evidence, owner_guard=guard)
        assert json.loads(hold.read_text())['state'] == 'BLOCKED_UNCERTAIN'
    else:
        result = retention.release_historical_hold(hold, release_evidence=evidence, owner_guard=guard)
        assert result['state'] == 'RELEASED' and result['previous_state'] == 'BLOCKED_UNCERTAIN'
        assert Path(result['general_recovery']['path']).exists()
        assert retention.release_historical_hold(hold, release_evidence=evidence, owner_guard=guard)['state'] == 'RELEASED'
