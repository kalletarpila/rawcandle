"""Controlled repair receipts and journalled publication, on isolated projects."""
from tests.provider_capture_fixtures import acquired
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin import provider_payload_workflow as w
from rawcandle.fundamentals.admin import provider_payload as p
from rawcandle.fundamentals.admin import refresh_fundamentals as f
from rawcandle.fundamentals.admin import publication_journal as journal
from rawcandle.fundamentals.generations import prepare_generation_from_candidates, activate_generation, resolve_active_generation
from tests.test_fundamentals_pb_new_quarter_review import factory as base_factory, ASOF


@pytest.fixture
def setup(base_factory, tmp_path):
    sample = base_factory()
    with sqlite3.connect(sample['pp']) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM provider_observation WHERE fiscalperiod='2026-Q3'").fetchone()
        full = json.loads(row['payload_json'])
        old = f.normalize_source_row(full)
        from rawcandle.fundamentals.admin.contracts import fingerprint
        content_hash = fingerprint(f._raw_row(old))
        c.execute("UPDATE provider_observation SET provenance_json='{}',payload_json=?,content_hash=?,company_id=1,security_id=1,provider_security_id='1',provider_ticker='AAA' WHERE observation_id=?",
                  (json.dumps(old), content_hash, row['observation_id']))
    with sqlite3.connect(sample['cp']) as c:
        c.execute("INSERT OR IGNORE INTO provider_security_identity VALUES('SHARADAR','1',1,'AAA','TEST',?)", (ASOF,))
        c.execute("INSERT OR IGNORE INTO provider_company_identity VALUES('SHARADAR','PERMATICKER','1',1,'AAA','TEST','TEST','1',?)", (ASOF,))
        qid = c.execute("SELECT quarter_id FROM v4_quarter WHERE fiscal_quarter='Q3'").fetchone()[0]
        c.execute('UPDATE v4_quarter_financials SET parent_equity=NULL,parent_equity_usd=NULL WHERE quarter_id=?', (qid,))
        c.execute('UPDATE v4_parent_equity_source SET content_hash=?,sharefactor=NULL,price=NULL,marketcap=NULL,pb=NULL WHERE quarter_id=?', (content_hash, qid))
    root = tmp_path / 'isolated_project'; (root / 'data').mkdir(parents=True)
    inputs = {}
    for role, key in (('provider', 'pp'), ('canonical', 'cp'), ('analysis', 'ap')):
        path = root / 'data' / (role + '.db'); shutil.copyfile(sample[key], path); inputs[role] = path
    prepared = prepare_generation_from_candidates(inputs, generation_id='old_repair_baseline', project_root=root, source='TEST')
    activate_generation(prepared['manifest'], project_root=root)
    shutil.copyfile(sample['mp'], root / 'data/osakedata.db')
    shutil.copyfile(sample['ap'], root / 'data/analysis.db')
    (root / 'scheduler_config.json').write_text(json.dumps({'log_dir': str(root / 'scheduler_logs'),
        'enabled_markets': ['usa'], 'run_time': '04:30',
        'analysis_db_path': str(root / 'data/analysis.db'), 'osakedata_db_path': str(root / 'data/osakedata.db')}))
    queue = root / 'queue.db'; shutil.copyfile(sample['queue'], queue)
    history = f.validate_complete_history(acquired([full]), ticker='AAA', dimension='ARQ')
    proposal = w.proposal(root, f.source_key(full), history, fetched_at_utc=ASOF + 'T12:00:00Z')
    receipts = w.rehearse(root, [proposal], {('AAA', 'ARQ'): history}, root / 'candidate', as_of=ASOF)
    return SimpleNamespace(root=root, queue=queue, history=history, histories={('AAA', 'ARQ'): history},
                           proposals=[proposal], receipts=receipts, full=full)


def register(s):
    return w.register(s.root, s.queue, s.proposals, s.receipts, s.histories)


def fake_client(s, mutation=None):
    class Client:
        def fundamentals(self, **kw):
            row = deepcopy(s.full)
            if mutation:
                row.update(mutation)
            return SimpleNamespace(ok=True, records=acquired([row]))
    return Client()


def publish(s, **kw):
    return w.publish_batch(s.root, s.queue, [s.proposals[0]['repair_id']],
        authorized_batch_fingerprint=w.batch(s.proposals)['batch_fingerprint'],
        confirmed=True, rehearsal=True, client=fake_client(s), **kw)


def test_deterministic_proposal_receipt_and_read_only_confirmation(setup):
    s = setup; before = journal.sha256_file(s.queue)
    rebuilt = w.proposal(s.root, f.source_key(s.full), s.history,
                         fetched_at_utc=s.proposals[0]['source_fetch_timestamp'])
    assert rebuilt == s.proposals[0]
    assert journal.sha256_file(s.queue) == before
    ids = register(s)
    registered = journal.sha256_file(s.queue)
    item = w.confirmation(s.root, s.queue, ids[0], s.history)
    assert item['status'] == 'OPEN' and item['decision'] is None and not item['live_repair_authorized']
    assert item['financial_values_changed'] is False and item['receipt_pass'] is True
    assert journal.sha256_file(s.queue) == registered
    assert s.receipts[0]['result']['outcomes'][ids[0]]['ownership_classification'] == 'CONTINUATION_CANDIDATE'
    assert s.receipts[0]['result']['outcomes'][ids[0]]['hypothetical_pb'] == pytest.approx(1.2)


def test_duplicate_registration_is_idempotent_and_preserves_ownership_queue(setup):
    s = setup
    with w._ro(s.queue) as c:
        before = [dict(r) for r in c.execute('SELECT * FROM pb_ownership_review')]
    register(s); register(s)
    with w._ro(s.queue) as c:
        assert before == [dict(r) for r in c.execute('SELECT * FROM pb_ownership_review')]
        assert c.execute("SELECT COUNT(*) FROM refresh_review_queue_audit WHERE event_type='PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN'").fetchone()[0] == 1
        assert c.execute(f'SELECT decision_json FROM {w.TABLE}').fetchone()[0] is None


@pytest.mark.parametrize('field', ['proposal_fingerprint', 'source_key', 'baseline', 'comparison', 'passed', 'result_fingerprint'])
def test_tampered_receipt_is_not_registerable(setup, field):
    s = setup; receipts = deepcopy(s.receipts); receipts[0][field] = None
    before = journal.sha256_file(s.queue)
    with pytest.raises((ValueError, TypeError, KeyError)):
        w.register(s.root, s.queue, s.proposals, receipts, s.histories)
    assert journal.sha256_file(s.queue) == before


@pytest.mark.parametrize('field', ['sharefactor', 'equityusd', 'revenue', 'fiscalperiod', 'reportperiod', 'date', 'permaticker'])
def test_fresh_source_drift_stops_without_decision(setup, field):
    s = setup; changed = deepcopy(s.full)
    changed[field] = {'fiscalperiod': '2027-Q3', 'reportperiod': '2026-09-29', 'date': '2026-10-07', 'permaticker': 'OTHER'}.get(field, 999)
    history = f.validate_complete_history([changed], ticker='AAA', dimension='ARQ')
    before = journal.sha256_file(s.queue)
    with pytest.raises(ValueError):
        w.register(s.root, s.queue, s.proposals, s.receipts, {('AAA', 'ARQ'): history})
    assert journal.sha256_file(s.queue) == before


def test_candidate_hash_and_active_generation_drift_reject(setup):
    s = setup
    with sqlite3.connect(s.receipts[0]['candidates']['provider']) as c:
        c.execute('CREATE TABLE tampered(value)')
    with pytest.raises(ValueError):
        register(s)
    baseline = deepcopy(s.proposals[0]['baseline']); baseline['generation_id'] = 'different'
    with pytest.raises(ValueError, match='STALE_BASELINE'):
        w.revalidate(s.root, s.proposals[0], s.history, source_baseline=baseline)


@pytest.mark.parametrize('part', ['native', 'canonical', 'header'])
def test_recomputed_receipt_cannot_hide_selected_candidate_corruption(setup, part):
    s = setup
    path = s.receipts[0]['candidates']['canonical' if part == 'canonical' else 'provider']
    with sqlite3.connect(path) as c:
        if part == 'native':
            c.execute("UPDATE sharadar_fundamental_observation SET revenue=999 WHERE fiscalperiod='2026-Q3'")
        elif part == 'canonical':
            c.execute('UPDATE v4_quarter_financials SET parent_equity_usd=999 WHERE parent_equity_usd IS NOT NULL')
        else:
            c.execute("UPDATE provider_observation SET security_id=999 WHERE fiscalperiod='2026-Q3'")
    with pytest.raises(ValueError):
        w.measure(s.proposals, s.receipts[0]['candidates'], s.receipts[0]['result']['repairs'], as_of=ASOF)


def test_same_proposal_different_receipt_rejects(setup):
    s = setup; register(s)
    other = deepcopy(s.receipts[0]); other['rehearsal_nonce'] = 'different'
    other = w._seal({k: v for k, v in other.items() if k != 'receipt_fingerprint'}, 'receipt_fingerprint')
    with pytest.raises(ValueError, match='CONFLICTING_RECEIPT'):
        w.register(s.root, s.queue, s.proposals, [other], s.histories)


def test_same_key_different_proposal_requires_terminal_old_item(setup):
    s = setup; register(s)
    new = w.proposal(s.root, f.source_key(s.full), s.history, fetched_at_utc=ASOF + 'T13:00:00Z')
    receipts = w.rehearse(s.root, [new], s.histories, s.root / 'second_candidate', as_of=ASOF)
    with pytest.raises(ValueError, match='CONFLICTING_PROPOSAL'):
        w.register(s.root, s.queue, [new], receipts, s.histories)
    w.close_item(s.queue, s.proposals[0]['repair_id'], status='STALE', reason='Explicit replacement review')
    w.register(s.root, s.queue, [new], receipts, s.histories)


@pytest.mark.parametrize('field,value', [('binding_json', None), ('status', 'UNKNOWN'), ('decision_json', '{}'), ('source_key', '[]')])
def test_malformed_or_unbound_items_are_non_approvable(setup, field, value):
    s = setup; ids = register(s)
    with sqlite3.connect(s.queue) as c:
        c.execute(f'UPDATE {w.TABLE} SET {field}=? WHERE repair_id=?', (value, ids[0]))
    with pytest.raises(ValueError):
        w.confirmation(s.root, s.queue, ids[0], s.history)


def test_explicit_authorization_and_production_intent_required(setup):
    s = setup; register(s)
    with pytest.raises(PermissionError):
        w.publish_batch(s.root, s.queue, [s.proposals[0]['repair_id']], authorized_batch_fingerprint='wrong')
    with pytest.raises(PermissionError):
        w.publish_batch(s.root, s.queue, [s.proposals[0]['repair_id']], authorized_batch_fingerprint=w.batch(s.proposals)['batch_fingerprint'], confirmed=True)
    with pytest.raises(PermissionError):
        w.publish_batch(s.root, s.queue, [s.proposals[0]['repair_id']], authorized_batch_fingerprint='wrong', confirmed=True, rehearsal=True)


def test_source_only_immutable_generation_publication_on_isolated_project(setup):
    s = setup; register(s)
    with w._ro(s.queue) as c:
        ownership_before = [dict(r) for r in c.execute('SELECT * FROM pb_ownership_review')]
    result = publish(s)
    assert result['postflight'] == 'PASSED' and not result['ownership_approved'] and not result['pb_approved']
    assert resolve_active_generation(s.root).generation_id == result['generation_id']
    with w._ro(s.queue) as c:
        assert ownership_before == [dict(r) for r in c.execute('SELECT * FROM pb_ownership_review')]
        assert c.execute(f'SELECT status FROM {w.TABLE}').fetchone()[0] == 'APPROVED'
    assert journal.safety_status(s.root / 'data/.fundamentals_admin_publication_journal.json')['production_writes_blocked'] is False


@pytest.mark.parametrize('failure', ['BEFORE_ACTIVATION', 'POSTFLIGHT'])
def test_existing_journal_restores_full_old_generation(setup, failure):
    s = setup; register(s); old = w.baseline(s.root)
    with pytest.raises(RuntimeError, match='INJECTED'):
        publish(s, inject_failure_at=failure)
    assert w.baseline(s.root) == old
    assert journal.load_journal(s.root / 'data/.fundamentals_admin_publication_journal.json')['state'] == 'RECOVERED'
    with w._ro(s.queue) as c:
        assert c.execute(f'SELECT status FROM {w.TABLE}').fetchone()[0] == 'OPEN'


def test_postflight_complete_queue_retry_does_not_republish_or_rollback(setup):
    s = setup; register(s)
    with pytest.raises(RuntimeError, match='QUEUE_SYNC_REQUIRED'):
        publish(s, inject_failure_at='QUEUE_FINALIZATION')
    generation = resolve_active_generation(s.root).generation_id
    assert journal.load_journal(s.root / 'data/.fundamentals_admin_publication_journal.json')['state'] == 'COMPLETED'
    assert w.synchronize_completed(s.root, s.queue)
    assert w.synchronize_completed(s.root, s.queue)
    assert resolve_active_generation(s.root).generation_id == generation
    with w._ro(s.queue) as c:
        assert c.execute("SELECT COUNT(*) FROM refresh_review_queue_audit WHERE event_type='PROVIDER_PAYLOAD_REPAIR_APPROVED_SOURCE_REPAIR'").fetchone()[0] == 1


@pytest.mark.parametrize('mutation', ['assertion', 'repair_timestamp', 'repair_scope'])
def test_resealed_receipt_cannot_relax_assertions_or_binding(setup, mutation):
    s = setup; receipt = deepcopy(s.receipts[0])
    if mutation == 'assertion':
        receipt['result']['assertions']['financial_values_unchanged'] = False
        receipt['result_fingerprint'] = w.digest(receipt['result'])
    elif mutation == 'repair_timestamp':
        receipt['repair']['source_fetch_timestamp'] = '2099-01-01T00:00:00Z'
    else:
        receipt['repair']['new_observation_id'] = 'different'
    receipt = w._seal({k: v for k, v in receipt.items() if k != 'receipt_fingerprint'}, 'receipt_fingerprint')
    with pytest.raises(ValueError):
        w.binding(s.proposals[0], receipt)


def test_registered_audit_binding_is_immutable(setup):
    s = setup; ids = register(s)
    with sqlite3.connect(s.queue) as c:
        c.execute("UPDATE refresh_review_queue_audit SET evidence_json='{}' WHERE event_type='PROVIDER_PAYLOAD_REPAIR_REGISTERED_OPEN'")
    with pytest.raises(ValueError, match='REGISTRATION_AUDIT'):
        w.confirmation(s.root, s.queue, ids[0], s.history)


def test_existing_nonnull_equity_cannot_be_changed_by_source_repair(setup):
    s = setup
    old = Path(s.proposals[0]['baseline']['roles']['canonical'])
    # Corrupt only the isolated baseline fixture, then directly measure to prove
    # the economic assertion is independent of top-level baseline hash gates.
    with sqlite3.connect(old) as c:
        c.execute("UPDATE v4_quarter_financials SET parent_equity_usd=999 WHERE quarter_id IN (SELECT quarter_id FROM v4_quarter WHERE fiscal_quarter='Q3')")
    with pytest.raises(ValueError, match='EXISTING_EQUITY'):
        w.measure(s.proposals, s.receipts[0]['candidates'], s.receipts[0]['result']['repairs'], as_of=ASOF)


@pytest.mark.parametrize('blocked', ['scheduler', 'journal', 'taxonomy'])
def test_preflight_stops_conflicting_operations_without_rewriting_lock_owners(tmp_path, monkeypatch, blocked):
    import fcntl
    from rawcandle.scheduler import runner
    from rawcandle import datacenter_taxonomy_operation_log as taxonomy

    locks = [tmp_path / 'fundamental_reports/.fundamentals_admin_ui_operation.lock',
             tmp_path / 'temp/.fundamentals_admin_production.lock',
             tmp_path / 'logs/stock_update_scheduler.lock']
    for lock in locks:
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('original owner evidence\n')
    monkeypatch.setattr(runner, 'scheduler_lock_path', lambda _: locks[2])
    monkeypatch.setattr(taxonomy, 'inspect_taxonomy_operation_lock', lambda: {'lock_active': blocked == 'taxonomy'})
    monkeypatch.setattr(journal, 'safety_status', lambda _: {'production_writes_blocked': blocked == 'journal'})
    with locks[2].open('r') as owner:
        if blocked == 'scheduler':
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((BlockingIOError, ValueError)):
            with w.preflight(tmp_path, tmp_path / 'logs'):
                pytest.fail('An active operation must stop registration preflight')
    assert all(lock.read_text() == 'original owner evidence\n' for lock in locks)
