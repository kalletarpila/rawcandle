"""D2 owner boundaries on tiny real SQLite copies; no native workflow execution."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import pb_rehearsal_closeout as storage


def database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE evidence(value)')
        connection.execute('INSERT INTO evidence VALUES (42)')
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    group = root / 'temp/rebuild'
    candidates = {role: database(group / 'native_test_final' / (role + '.db'))
                  for role in ('provider', 'canonical', 'analysis')}
    taxonomy = database(group / 'native_test_final/taxonomy.db')
    copied = database(group / 'superseded_project/data/canonical.db')
    receipt = group / 'test_receipt.json'
    receipt.write_text('{"historical_result":"PASSED"}\n')
    journal = dict(operation_type='CONTROLLED_CURRENT_STATE_REBUILD', state='COMPLETED',
                   postflight_state='PASSED', rollback_recovery_state='NOT_REQUIRED', test_run_id='sealed',
                   scope_evidence=dict(test=dict(passed=True, test_fingerprint='sealed',
                       candidates={r: str(p) for r, p in candidates.items()},
                       result=dict(candidate_hashes={r: storage.file_sha256(p) for r, p in candidates.items()}),
                       native_analysis=dict(candidate_analysis_db=str(candidates['analysis'].relative_to(root))))))
    jp = root / 'data/.fundamentals_admin_publication_journal.json'
    jp.parent.mkdir()
    storage.durable_json(jp, journal)
    return root, group, candidates, taxonomy, copied, receipt, jp


@pytest.mark.parametrize('owner', ['legacy-rebaseline', 'bmra-neov-targeted', 'current-state-rebuild'])
def test_completed_obsolete_d2_owner_archives_without_rewriting_receipt(project, tmp_path, owner):
    _, group, _, _, _, receipt, _ = project
    original = receipt.read_bytes()
    decision = storage.close(group, owner, tmp_path / 'closed.json', outcome='PASSED',
                             evidence=[receipt], capability_loss='Optional historical executable replay')
    assert all(row['decision'] == 'RETIRE_APPROVED' for row in decision['files'])
    assert decision['retained_gb'] == 0 and receipt.read_bytes() == original


def test_historical_stop_superseded_by_later_evidence_can_close(project, tmp_path):
    _, group, _, _, _, receipt, _ = project
    receipt.write_text('{"decision":"STOP_UNRESOLVED_SOURCE_VERSION"}')
    later = tmp_path / 'later_accepted.json'
    later.write_text('{"BMRA":"ELIGIBLE","NEOV":"ELIGIBLE","postflight":"PASSED"}')
    decision = storage.close(group, 'bmra-neov-targeted', tmp_path / 'closed.json', outcome='SUPERSEDED',
                             evidence=[receipt, later], capability_loss='Obsolete STOP replay; accepted successor resolves source-version issue')
    assert decision['state'] == 'ARCHIVED_EVIDENCE'
    assert json.loads(receipt.read_text())['decision'] == 'STOP_UNRESOLVED_SOURCE_VERSION'


def test_genuinely_open_stop_preserves_exact_evidence(project, tmp_path):
    _, group, candidates, _, _, receipt, _ = project
    hold = dict(owner='active-investigation', reason='Only exact source vintage reproduces an unresolved payload defect',
                end_event='Specific defect resolved and owner comparisons sealed')
    decision = storage.close(group, 'bmra-neov-targeted', tmp_path / 'closed.json', outcome='PASSED',
                             evidence=[receipt], capability_loss='Only other disposable copies may retire',
                             requirements={str(candidates['provider']): hold})
    retained = [row for row in decision['files'] if row['decision'] == 'RETAIN_REQUIRED']
    assert [row['path'] for row in retained] == [str(candidates['provider'])]
    assert retained[0]['necessity']['owner'] == 'active-investigation'


def test_current_test_holds_exact_candidates_without_retaining_entire_project(project, tmp_path):
    root, group, candidates, taxonomy, copied, receipt, jp = project
    before = jp.read_bytes()
    requirements = storage.rebuild_test_requirements(root)
    assert set(requirements) == {str(p) for p in candidates.values()}
    decision = storage.close(group, 'current-state-rebuild', tmp_path / 'closed.json', outcome='PASSED',
                             evidence=[receipt], capability_loss='Superseded project/full calculation replay only',
                             requirements=requirements)
    ledger = tmp_path / 'ledger.json'

    def check_live():
        assert jp.read_bytes() == before

    for row in decision['files']:
        if row['path'] in requirements:
            with pytest.raises(ValueError, match='NOT_APPROVED'):
                storage.retire_exact(row, ledger, check_live=check_live, check_busy=lambda _: None)
        else:
            storage.retire_exact(row, ledger, check_live=check_live, check_busy=lambda _: None)
    assert all(p.is_file() for p in candidates.values())
    assert not taxonomy.exists() and not copied.exists()
    assert jp.read_bytes() == before and len(json.loads(ledger.read_text())['files']) == 2


def test_active_rollback_image_and_sidecars_are_retained(project, tmp_path):
    _, group, _, _, _, receipt, _ = project
    backup = database(group / 'backups/rollback.db')
    connection = sqlite3.connect(backup)
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('INSERT INTO evidence VALUES (99)')
        decision = storage.close(group, 'current-state-rebuild', tmp_path / 'closed.json', outcome='PASSED',
                                 evidence=[receipt], capability_loss='Other completed scratch only', requirements={str(backup):
                                     dict(owner='recovery', reason='Pending restore-old operation', end_event='Verified restored terminal')})
        bound = [row for row in decision['files'] if row['main_path'] == str(backup)]
        assert len(bound) == 3 and all(row['decision'] == 'RETAIN_REQUIRED' for row in bound)
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.parametrize('mutation', ['nonterminal', 'recovery', 'relative_path', 'conflicting_analysis', 'test_identity'])
def test_uncertain_current_test_binding_fails_closed(project, mutation):
    root, _, _, _, _, _, jp = project
    journal = json.loads(jp.read_text())
    if mutation == 'nonterminal': journal['state'] = 'PREPARING'
    if mutation == 'recovery': journal['rollback_recovery_state'] = 'RESTORING_OLD_GENERATION'
    if mutation == 'relative_path': journal['scope_evidence']['test']['candidates']['provider'] = 'relative.db'
    if mutation == 'conflicting_analysis': journal['scope_evidence']['test']['native_analysis']['candidate_analysis_db'] = 'other.db'
    if mutation == 'test_identity': journal['test_run_id'] = 'different'
    storage.durable_json(jp, journal)
    with pytest.raises(ValueError): storage.rebuild_test_requirements(root)


def test_interrupted_d2_cleanup_does_not_retry_prepared_unlink(project, tmp_path):
    _, group, _, _, _, receipt, _ = project
    decision = storage.close(group, 'legacy-rebaseline', tmp_path / 'closed.json', outcome='PASSED',
                             evidence=[receipt], capability_loss='Completed optional copy replay')
    row = decision['files'][0]
    ledger = tmp_path / 'ledger.json'
    storage.durable_json(ledger, dict(files={row['path']: dict(outcome='PREPARED')}))
    with pytest.raises(ValueError, match='REQUIRES_RECONCILIATION'):
        storage.retire_exact(row, ledger, check_live=lambda: None, check_busy=lambda _: None)
    assert Path(row['path']).is_file()
