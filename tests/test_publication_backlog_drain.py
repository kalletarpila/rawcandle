import json
import sqlite3
from pathlib import Path

import pytest

from tests.test_candidate_publication import database, open_status, Offline
from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin.candidate_publication import select_candidate_scope, run_candidate_publication
from rawcandle.fundamentals.generations import prepare_generation_from_candidates, activate_generation, resolve_active_generation
from rawcandle.fundamentals.admin.production_transaction import SimulatedTransactionCrash
from rawcandle.fundamentals.admin.publication_journal import recover_if_required, sha256_file
from rawcandle.cli.result_publication_backlog_drain import main


def root_fixture(root, count=3):
    root.mkdir()
    roles = {r: database(root / (r+'.db'), count) for r in ('provider','canonical','analysis')}
    prepared = prepare_generation_from_candidates(roles, generation_id='old', project_root=root, source='TEST')
    activate_generation(prepared['manifest'], project_root=root)
    return root


def test_all_selection_normal_cap_overrides_and_determinism(tmp_path):
    db = database(tmp_path/'c.db', 225)
    open_status(db, 1, 'UNRESOLVED')
    open_status(db, 2, 'NOT_FOUND')
    open_status(db, 3, 'AMBIGUOUS')
    open_status(db, 4, 'NOT_FOUND', '2020-01-01')
    normal = select_candidate_scope(db, [(225,2026,'Q3')], as_of_date='2026-10-04')
    assert normal['retry_selected']==100 and normal['new_quarters']==[(225,2026,'Q3')]
    for cap in (10,150):
        assert select_candidate_scope(db, [], as_of_date='2026-10-04', retry_max_quarters=cap)['retry_selected']==cap
    scope = select_candidate_scope(db, [], as_of_date='2026-10-04', retry_max_quarters=None)
    assert scope['retry_selected']==224 and scope['retry_quarters'][-3:]==[(1,2026,'Q3'),(2,2026,'Q3'),(3,2026,'Q3')]
    assert scope==select_candidate_scope(db, [], as_of_date='2026-10-04', retry_max_quarters=None)


def test_dry_run_read_only_and_confirmation(tmp_path):
    root = root_fixture(tmp_path/'root')
    active = resolve_active_generation(root)
    before = {r:sha256_file(p) for r,p in active.role_paths().items()}
    report = drain.run_backlog_drain(project_root=root, as_of_date='2026-10-04')
    assert report['status']=='DRY_RUN' and report['scope']['retry_selected']==3
    assert not (root/'fundamental_reports').exists()
    assert before=={r:sha256_file(p) for r,p in active.role_paths().items()}
    with pytest.raises(PermissionError): drain.run_backlog_drain(project_root=root, apply=True)


def test_partial_activation_immutable_sources_and_manifest(tmp_path):
    root = root_fixture(tmp_path/'root')
    active = resolve_active_generation(root)
    before = {r:sha256_file(p) for r,p in active.role_paths().items()}
    sentinel = root/'data/forecasts.db'
    sentinel.write_bytes(b'forecast must not change')
    result = drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                                    client=Offline(), as_of_date='2026-10-04')
    assert result['status']=='PARTIAL' and result['attempted_current_backlog']==3
    assert result['still_open_after_attempt']==3 and result['remaining_status_counts']=={'UNRESOLVED':3}
    assert before=={r:sha256_file(p) for r,p in active.role_paths().items()}
    assert sentinel.read_bytes()==b'forecast must not change'
    new = resolve_active_generation(root)
    assert new.generation_id!=active.generation_id
    for role,path in new.role_paths().items():
        assert sha256_file(path)==new.manifest['role_verification'][role]['sha256']
    with sqlite3.connect(new.role_paths()['canonical']) as c:
        assert c.execute('SELECT COUNT(*) FROM v4_result_publication_evidence').fetchone()[0]==0
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert result['publication']['retry_max_quarters'] is None


@pytest.mark.parametrize('stage',['AFTER_PREPARED','AFTER_NEW_GENERATION_READY','AFTER_GENERATION_ACTIVATION'])
def test_crash_uses_existing_generation_recovery(tmp_path,stage):
    root = root_fixture(tmp_path/'root')
    with pytest.raises(SimulatedTransactionCrash):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                               client=Offline(), as_of_date='2026-10-04', inject_crash_at=stage)
    recovered = recover_if_required(root/'data/.fundamentals_admin_publication_journal.json')
    assert recovered['recovered'] and resolve_active_generation(root).generation_id=='old'


def test_empty_backlog_skips_without_generation(tmp_path):
    root = root_fixture(tmp_path/'root')
    # All quarters outside the requested horizon; VERIFIED exclusion tested by existing selector suite.
    result = drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                                    as_of_date='2028-10-04',client=Offline())
    assert result['status']=='SKIPPED' and resolve_active_generation(root).generation_id=='old'


def test_normal_and_operator_network_budgets(tmp_path,monkeypatch):
    from rawcandle.fundamentals.admin import candidate_publication
    seen=[]
    def client(**kwargs):
        seen.append(kwargs['maximum_runtime_seconds']);return Offline()
    monkeypatch.setattr(candidate_publication,'SecClient',client)
    p=database(tmp_path/'c.db')
    run_candidate_publication(p,[],as_of_date='2026-10-04')
    run_candidate_publication(p,[],as_of_date='2026-10-04',retry_max_quarters=None,network_budget_seconds=1800)
    assert seen==[300,1800]
    with pytest.raises(ValueError): run_candidate_publication(p,[],as_of_date='2026-10-04',network_budget_seconds=0)


def test_cli_is_dry_run_by_default(monkeypatch,capsys):
    import rawcandle.cli.result_publication_backlog_drain as cli
    calls=[]
    def run(**kwargs):
        calls.append(kwargs);return {'status':'DRY_RUN'}
    monkeypatch.setattr(cli,'run_backlog_drain',run)
    assert main([])==0 and calls[0]['apply'] is False
    assert json.loads(capsys.readouterr().out)['status']=='DRY_RUN'


def test_drain_verified_exclusion_and_evidence_dedup(tmp_path):
    from rawcandle.fundamentals.result_publication import SecClient
    root = root_fixture(tmp_path/'root')
    old = resolve_active_generation(root)
    payload={'filings':{'recent':{'form':['8-K'],'items':['2.02'],
        'acceptanceDateTime':['2026-09-30T12:00:00Z'],'accessionNumber':['1-26-1'],'primaryDocument':['a.htm']}}}
    def client():
        return SecClient(fetch_json=lambda _:payload, fetch_text=lambda _:"Item 2.02 Results of Operations. Quarter ended August 31, 2026.",minimum_interval_seconds=0)
    result = drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,
                                    client=client(),as_of_date='2026-10-04')
    assert result['status']=='SUCCESS' and result['publication']['new_verified']==3
    current = resolve_active_generation(root)
    before = sha256_file(current.role_paths()['canonical'])
    again = drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,
                                   client=client(),as_of_date='2026-10-04')
    assert again['status']=='SKIPPED' and resolve_active_generation(root).generation_id==current.generation_id
    assert sha256_file(current.role_paths()['canonical'])==before
    with sqlite3.connect(current.role_paths()['canonical']) as c:
        assert c.execute('SELECT COUNT(*) FROM v4_result_publication_evidence').fetchone()[0]==3


def test_ordinary_activation_exception_rolls_back(tmp_path,monkeypatch):
    root = root_fixture(tmp_path/'root')
    original = drain.activate_prepared_generation
    def failure(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('controlled postactivation failure')
    monkeypatch.setattr(drain,'activate_prepared_generation',failure)
    with pytest.raises(RuntimeError,match='postactivation'):
        drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,
                               client=Offline(),as_of_date='2026-10-04')
    assert resolve_active_generation(root).generation_id=='old'
    report = json.loads(next((root/'fundamental_reports/publication_drains').glob('*/result.json')).read_text())
    assert report['status']=='FAILED' and report['rollback']['status']=='RECOVERED'


def test_normal_production_cap_and_finite_budget():
    from inspect import signature
    from rawcandle.fundamentals.admin.refresh_production import run_production_apply
    assert signature(run_production_apply).parameters['result_publication_retry_max_quarters'].default==100
    for budget in (float('inf'),float('nan'),0):
        with pytest.raises(ValueError,match='BUDGET'):
            drain.run_backlog_drain(network_budget_seconds=budget)


def test_exhausted_network_budget_never_activates(tmp_path):
    from collections import Counter
    class Exhausted(Offline):
        stats=Counter(budget_exhausted=1)
    root = root_fixture(tmp_path/'root')
    with pytest.raises(RuntimeError,match='NETWORK_BUDGET_EXHAUSTED'):
        drain.run_backlog_drain(project_root=root,apply=True,confirm_production=True,
                               client=Exhausted(),as_of_date='2026-10-04')
    assert resolve_active_generation(root).generation_id=='old'
