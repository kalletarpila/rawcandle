"""Native Refresh/generation binding qualification, with isolated authorities."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.admin import refresh_production as production
from rawcandle.fundamentals.admin.publication_journal import (
    PublicationRecoveredRetryRequired, PublicationRecoveryError, guard_production_writes,
)
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_admin_refresh_full_workflow_production_parity as native


def sqlite_identity(path):
    data=Path(path).read_bytes()
    offsets={'file_change_counter':24,'database_pages':28,'schema_cookie':40,
             'version_valid_for':92,'sqlite_version':96}
    with sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True) as c:
        logical=hashlib.sha256('\n'.join(c.iterdump()).encode()).hexdigest()
    return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),
            'header':{k:int.from_bytes(data[n:n+4],'big') for k,n in offsets.items()},'logical_dump_sha256':logical}


def _crashed_fixture(tmp_path,monkeypatch,point):
    f=native._fixture(tmp_path,monkeypatch)
    project=native._migrate_refresh_fixture_to_generation_layout(f,monkeypatch)
    old=resolve_active_generation(project)
    before={r:sqlite_identity(p) for r,p in old.role_paths().items()}
    with pytest.raises(production.SimulatedPublicationCrash):
        native._service(f,actual_production=True,inject_crash_at=point).full_workflow(
            operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
    journal=json.loads(f.journal_path.read_text())
    receipt={'old_manifest':dict(old.manifest),'journal_before_recovery':journal,
             'active_at_recovery':dict(resolve_active_generation(project).manifest),'roles':{}}
    for role,record in journal['roles'].items():
        backup=sqlite_identity(record['backup_path'])
        new=Path(journal['new_generation_dir'])/old.manifest['roles'][role] if journal.get('new_generation_dir') else None
        receipt['roles'][role]={'old':before[role],'backup':backup,
            'new':sqlite_identity(new) if new and new.exists() else None}
    (tmp_path/'recovery_binding_receipt.json').write_text(json.dumps(receipt,indent=2))
    return f,project,old,before,journal,receipt


@pytest.mark.parametrize('point',[
    'AFTER_NEW_GENERATION_READY','AFTER_GENERATION_ACTIVATION',
    'AFTER_ALL_REPLACEMENTS_BEFORE_POSTFLIGHT','AFTER_POSTFLIGHT_BEFORE_COMPLETED',
])
def test_native_immutable_crash_restores_exact_old_and_requires_fresh_retry(tmp_path,monkeypatch,point):
    f,project,old,before,journal,receipt=_crashed_fixture(tmp_path,monkeypatch,point)
    for role in production.PUBLICATION_ROLES:
        assert receipt['roles'][role]['old']['sha256']==receipt['roles'][role]['backup']['sha256']
        assert journal['roles'][role]['old_production_fingerprint']==receipt['roles'][role]['backup']['sha256']
    with pytest.raises(PublicationRecoveredRetryRequired):guard_production_writes(f.journal_path)
    terminal=json.loads(f.journal_path.read_text())
    assert terminal['state']=='RECOVERED'
    assert terminal['rollback_recovery_state']=='OLD_GENERATION_RESTORED_AND_VERIFIED'
    assert set(terminal['old_generation_verification'])==set(production.PUBLICATION_ROLES)
    active=resolve_active_generation(project)
    assert active.generation_id==old.generation_id
    assert {r:sqlite_identity(p)['sha256'] for r,p in active.role_paths().items()}=={r:v['sha256'] for r,v in before.items()}
    # The first invocation performs recovery only; a second guard does no work.
    assert guard_production_writes(f.journal_path)=={'status':'RECOVERED','recovered':False}
    if point == 'AFTER_NEW_GENERATION_READY':
        fresh=native._service(f,actual_production=True).full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
        assert fresh.outcome=='COMPLETED'
        assert json.loads(f.journal_path.read_text())['state']=='COMPLETED'


@pytest.mark.parametrize('swapped',[False,True])
def test_native_activation_intent_boundary_recovers_old(tmp_path,monkeypatch,swapped):
    from rawcandle.fundamentals.admin import publication_journal as pj
    f=native._fixture(tmp_path,monkeypatch);project=native._migrate_refresh_fixture_to_generation_layout(f,monkeypatch)
    old=resolve_active_generation(project);original=pj.activate_generation
    def crash_at_swap(*args,**kwargs):
        if swapped:original(*args,**kwargs)
        raise production.SimulatedPublicationCrash('ACTIVATION_INTENT_BOUNDARY')
    monkeypatch.setattr(pj,'activate_generation',crash_at_swap)
    with pytest.raises(production.SimulatedPublicationCrash):
        native._service(f,actual_production=True).full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
    j=json.loads(f.journal_path.read_text());assert j['generation_activation_state']=='ACTIVATING'
    assert (resolve_active_generation(project).generation_id!=old.generation_id)==swapped
    monkeypatch.setattr(pj,'activate_generation',original)
    with pytest.raises(PublicationRecoveredRetryRequired):guard_production_writes(f.journal_path)
    assert resolve_active_generation(project).generation_id==old.generation_id
    assert json.loads(f.journal_path.read_text())['state']=='RECOVERED'


@pytest.mark.parametrize('point',['AFTER_BACKUPS_BEFORE_PREPARED','BEFORE_CANDIDATE_PUBLICATION'])
def test_native_pre_boundary_failure_does_not_require_recovery(tmp_path,monkeypatch,point):
    f=native._fixture(tmp_path,monkeypatch);project=native._migrate_refresh_fixture_to_generation_layout(f,monkeypatch)
    old=resolve_active_generation(project)
    with pytest.raises(production.SimulatedPublicationCrash):
        native._service(f,actual_production=True,inject_crash_at=point).full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
    assert resolve_active_generation(project).generation_id==old.generation_id
    assert guard_production_writes(f.journal_path)=={'status':'NO_JOURNAL','recovered':False}


@pytest.mark.parametrize('point',['POSTFLIGHT','AFTER_GENERATION_ACTIVATION'])
def test_native_ordinary_rollback_has_verified_terminal_state(tmp_path,monkeypatch,point):
    f=native._fixture(tmp_path,monkeypatch);project=native._migrate_refresh_fixture_to_generation_layout(f,monkeypatch)
    old=resolve_active_generation(project)
    result=native._service(f,actual_production=True,inject_failure_at=point).full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
    w=native._workflow_payload(result);p=native._stage_payload(w,'Production update')
    assert p['outcome']=='FAILED_ROLLED_BACK'
    assert p['journal']['state']=='ROLLED_BACK'
    assert p['journal']['rollback_recovery_state']=='OLD_GENERATION_RESTORED_AND_VERIFIED'
    assert resolve_active_generation(project).generation_id==old.generation_id
    assert all(r['rollback_restoration_verified'] for r in p['journal']['roles'].values())


@pytest.mark.parametrize('role',['provider','canonical','analysis'])
def test_prepared_journal_role_tampering_remains_fail_closed(tmp_path,role):
    from tests.test_fundamentals_generations import _publication_fixture
    from rawcandle.fundamentals.admin.publication_journal import update_journal
    path,j,prepared=_publication_fixture(tmp_path)
    j['roles'][role]['verified_backup_fingerprint']='0'*64
    update_journal(path,j)
    with pytest.raises(PublicationRecoveryError,match='CRITICAL_RECOVERY_FAILED'):guard_production_writes(path)
    assert json.loads(path.read_text())['state']=='RECOVERY_FAILED'


@pytest.mark.parametrize('defect',['manifest_hash','missing_old','tampered_old'])
def test_old_manifest_and_role_integrity_remain_fail_closed(tmp_path,defect):
    from tests.test_fundamentals_generations import _publication_fixture
    from rawcandle.fundamentals.admin.publication_journal import update_journal
    path,j,prepared=_publication_fixture(tmp_path);old=resolve_active_generation(tmp_path)
    if defect=='manifest_hash':j['old_generation']['manifest']['role_verification']['provider']['sha256']='0'*64
    elif defect=='missing_old':old.role_paths()['provider'].unlink()
    else:
        with sqlite3.connect(old.role_paths()['provider']) as c:c.execute("UPDATE generation SET value='tampered'")
    update_journal(path,j)
    with pytest.raises(PublicationRecoveryError,match='CRITICAL_RECOVERY_FAILED'):guard_production_writes(path)
    assert json.loads(path.read_text())['state']=='RECOVERY_FAILED'


@pytest.mark.parametrize('role',['provider','canonical','analysis'])
def test_backup_binding_mismatch_fails_before_prepare(tmp_path,role):
    from tests.test_fundamentals_generations import _publication_fixture
    path,j,prepared=_publication_fixture(tmp_path);old=resolve_active_generation(tmp_path)
    backups={r:{'source':str(old.role_paths()[r]),'source_sha256':old.manifest['role_verification'][r]['sha256'],
                'verification':{'sha256':old.manifest['role_verification'][r]['sha256']}} for r in production.PUBLICATION_ROLES}
    backups[role]['verification']['sha256']='0'*64
    with pytest.raises(RuntimeError,match='OLD_BACKUP_BINDING_MISMATCH:'+role):
        production._validate_generation_backup_binding(old,backups)


@pytest.fixture(autouse=True)
def _isolated_legacy_route(monkeypatch):
    # These fixtures exercise legacy recovery, independently of live routing.
    from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
    monkeypatch.setattr(FundamentalsAdminUIService, 'selected_refresh_route', lambda self: 'LEGACY')
