from copy import deepcopy
from pathlib import Path
import json,sqlite3
import pytest
from rawcandle.fundamentals.admin import legacy_payload_disposition as d
from tests.test_fundamentals_pb_new_quarter_review import factory


def evidence(**updates):
    return dict(identity_exact=True,current_source_trusted=True,current_binding_known=True,
        current_incomplete=False,current_healthy=True,**updates)


def repairable():
    e=evidence();e.update(current_incomplete=True,current_healthy=False,exact_repair_available=True,
        native_repair_supported=True,repair_evidence_fingerprint='exact',financial_drift=False)
    return e


def ineligible():
    e=evidence();e.update(current_incomplete=True,current_healthy=False,unrecoverable_current_proven=True,
        exact_repair_unavailable_proven=True,authoritative_unavailability_proof='provider-attestation')
    return e


@pytest.mark.parametrize('facts,expected',[
    (evidence(),'ELIGIBLE'),(repairable(),'REPAIRABLE'),(ineligible(),'INELIGIBLE_SOURCE_DATA'),
    (evidence(historical_only_count=12,historical_no_current_effect_proven=True),'HISTORICAL_ONLY'),
    ({},'UNRESOLVED'),({**repairable(),'contradictions':['financial source drift']},'UNRESOLVED'),
    ({**ineligible(),'contradictions':['identity mismatch']},'UNRESOLVED'),
    ({**repairable(),'historical_only_count':2000,'historical_no_current_effect_proven':True},'REPAIRABLE'),
    ({**ineligible(),'historical_only_count':2000,'historical_no_current_effect_proven':True},'INELIGIBLE_SOURCE_DATA'),
    ({**repairable(),'financial_drift':True},'UNRESOLVED'),
    ({**repairable(),'repair_evidence_fingerprint':None},'UNRESOLVED'),
    ({**repairable(),'unrecoverable_current_proven':True},'UNRESOLVED'),
    ({**ineligible(),'authoritative_unavailability_proof':None},'UNRESOLVED'),
    (evidence(legacy_count=2000),'ELIGIBLE'),
    (evidence(historical_only_count=1),'UNRESOLVED'),
])
def test_one_ticker_status_and_precedence(facts,expected):
    old=deepcopy(facts);assert d.decide(facts)==expected;assert facts==old


def artifact(row):
    return d.seal([row],baseline={},observations=[dict(ticker=row['ticker'],observation_id='old',
        frozen_accepted_binding=True,retained=True,current_accepted_binding=False)],evidence_reference='fixture')


def record(facts=None):
    return d.item('AAA',1,11,evidence() if facts is None else facts,counts={'legacy':1,'frozen':1,'retained':1},
        reason='EXACT_SOURCE_EVIDENCE',source_binding={})


def test_observation_categories_overlap_without_competing_ticker_statuses():
    a=artifact(record());s=d.summary(a)
    assert s['tickers']==1 and sum(s['dispositions'].values())==1
    assert s['observations']==1
    assert s['observation_categories']['retained']==s['observation_categories']['frozen_accepted_binding']==1
    with pytest.raises(ValueError,match='DUPLICATE_TICKER'):
        d.seal([record(),record()],baseline={},observations=[],evidence_reference='x')
    a['items'][0]['disposition']='INELIGIBLE_SOURCE_DATA'
    with pytest.raises(ValueError,match='TAMPERED'):d.verify(a)


def test_native_exclusion_preserves_history_and_safe_peers_and_reactivation_fails_closed(tmp_path):
    from tests.test_fundamentals_admin_remove_tickers import _paths
    from rawcandle.fundamentals.admin.remove_tickers import _mutate_candidate_universe,_canonical_plan
    from rawcandle.fundamentals.admin.refresh_fundamentals import resolve_identity
    from rawcandle.fundamentals.admin.batch_add_tickers import _canonical_identity
    from rawcandle.fundamentals.ttm.engine import load_canonical_rows
    paths=_paths(tmp_path/'isolated');a=artifact(record(ineligible()));queue=tmp_path/'queue.db'
    provider=paths.provider_db.read_bytes()
    with sqlite3.connect(paths.canonical_db) as c:
        before={t:c.execute(f'SELECT * FROM {t} ORDER BY rowid').fetchall() for t in ('v4_quarter','v4_quarter_financials','ticker_alias')}
    with pytest.raises(ValueError,match='NATIVE_EXCLUSION_REQUIRED'):
        d._write(queue,a,paths.canonical_db)
    assert not queue.exists()
    _mutate_candidate_universe(paths.canonical_db,[dict(company_id=1,security_id=11,removal_eligible=True)],applied_at='2026-10-30T00:00:00Z')
    d._write(queue,a,paths.canonical_db);d._write(queue,a,paths.canonical_db)
    assert len(d.list_items(queue))==1
    assert resolve_identity(paths,'AAA')['status']=='NOT_IN_CANONICAL_UNIVERSE'
    assert _canonical_plan(paths.canonical_db,'AAA')['classification']=='ALREADY_ABSENT'
    assert _canonical_identity(paths,'AAA',{})['exists'] is True # Add cannot silently make a new active identity.
    assert not any(r['company_id']==1 for r in load_canonical_rows(paths.canonical_db))
    assert any(r['company_id']==2 for r in load_canonical_rows(paths.canonical_db))
    with sqlite3.connect(paths.canonical_db) as c:
        after={t:c.execute(f'SELECT * FROM {t} ORDER BY rowid').fetchall() for t in before}
    assert before==after and paths.provider_db.read_bytes()==provider
    with sqlite3.connect(queue) as c:assert c.execute(f'SELECT COUNT(*) FROM {d.TABLE}_audit').fetchone()[0]==1


def test_stored_status_tampering_is_detected(tmp_path):
    from tests.test_fundamentals_admin_remove_tickers import _paths
    p=_paths(tmp_path/'db');q=tmp_path/'queue.db';d._write(q,artifact(record()),p.canonical_db)
    with sqlite3.connect(q) as c:
        raw=json.loads(c.execute(f'SELECT record_json FROM {d.TABLE}').fetchone()[0]);raw['reason_code']='changed'
        c.execute(f'UPDATE {d.TABLE} SET record_json=?',(json.dumps(raw),))
    with pytest.raises(ValueError,match='STORED_EVIDENCE_TAMPERED'):d.list_items(q)


@pytest.mark.parametrize('facts,label,attention',[
    (evidence(),'Fundamentals eligible',False),(repairable(),'Source repair available',True),
    (ineligible(),'Fundamentals ineligible',False),
    (evidence(historical_only_count=1,historical_no_current_effect_proven=True),'Historical evidence retained',False),
    ({},'Source-data disposition unresolved',True),
])
def test_ui_summary_first_no_mutation(facts,label,attention):
    from tests.test_fundamentals_review_action_first import Service,render,text
    row=record(facts);original=deepcopy(row)
    class S(Service):
        def list_source_dispositions(self):return [row]
    service=S();controls=render(service)
    view=d.presentation(row)
    assert label in view['label'] and view['needs_action']==attention
    expanded=text(controls.source_disposition_column,collapsed=True)
    assert label in expanded and 'Next action:' in expanded and 'Raw technical evidence' in expanded
    assert row==original and not service.actions


def test_inactive_security_does_not_create_pb_continuation_case(factory):
    from tests.test_fundamentals_pb_new_quarter_review import ASOF
    from rawcandle.fundamentals.admin import pb_ownership_review as own
    f=factory()
    with sqlite3.connect(f['cp']) as c:c.execute('UPDATE security SET active=0')
    with sqlite3.connect(f['cp']) as c:
        c.row_factory=sqlite3.Row
        assert own.detect(c,as_of=ASOF)==[]
    from rawcandle.fundamentals.admin.pb_ownership_future import partition
    scheduled=partition(f['cp'],f['pp'],f['mp'],f['queue'],as_of=ASOF,enabled=True)
    assert scheduled['evaluated']==0 and scheduled['auto_continue']==0


@pytest.fixture
def bound_disposition(tmp_path):
    canonical=tmp_path/'canonical.db';provider=tmp_path/'provider.db'
    with sqlite3.connect(canonical) as c:
        c.executescript('''CREATE TABLE security(security_id,company_id,current_ticker,active);
            INSERT INTO security VALUES(11,1,'AAA',1);
            CREATE TABLE v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,identity_status);
            INSERT INTO v4_quarter VALUES(1,1,2026,'Q3','ACCEPTED');
            CREATE TABLE v4_field_provenance(quarter_id,canonical_field,provider_observation_id);
            INSERT INTO v4_field_provenance VALUES(1,'shares_outstanding','source');''')
    with sqlite3.connect(provider) as p:
        p.execute('CREATE TABLE provider_observation(observation_id,content_hash,payload_json)')
        p.execute('INSERT INTO provider_observation VALUES(?,?,?)',('source','hash','{"source":1}'))
    row=record();row.pop('item_fingerprint')
    row['source_binding']=dict(observation_id='source',content_hash='hash',
        payload_fingerprint=d.digest({'source':1}),fiscal_year=2026,fiscal_quarter='Q3')
    row['item_fingerprint']=d.digest(row)
    a=artifact(row);a.pop('artifact_fingerprint')
    a['baseline']={'roles':{'canonical':str(canonical),'provider':str(provider)}}
    a['artifact_fingerprint']=d.digest(a)
    return a,canonical,provider


def test_changed_binding_is_unresolved_read_only(bound_disposition):
    a,c,p=bound_disposition
    assert not d.current_views(a['items'],c,p)[0]['stale']
    with sqlite3.connect(p) as db:db.execute("UPDATE provider_observation SET payload_json='{}'")
    before=(c.read_bytes(),p.read_bytes());original=deepcopy(a)
    row=d.current_views(a['items'],c,p)[0]
    assert row['stale'] and d.presentation(row)['needs_action']
    assert 'CURRENT_BINDING_CHANGED_REEVALUATE' in '\n'.join(d.presentation(row)['lines'])
    assert (c.read_bytes(),p.read_bytes())==before and a==original


@pytest.mark.parametrize('drift',['authorization','baseline','binding',None])
def test_registration_requires_exact_authorization_and_locked_fresh_evidence(
        tmp_path,monkeypatch,bound_disposition,drift):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from rawcandle.fundamentals.admin import provider_payload_workflow as repair
    from rawcandle.scheduler import config
    a,c,p=bound_disposition;q=tmp_path/'queue.db';entered=[]
    @contextmanager
    def preflight(*args):
        entered.append(True)
        try:yield
        finally:entered.pop()
    def baseline(*args):
        assert entered
        return {} if drift=='baseline' else a['baseline']
    monkeypatch.setattr(repair,'preflight',preflight);monkeypatch.setattr(repair,'baseline',baseline)
    monkeypatch.setattr(config,'read_scheduler_config',lambda _:SimpleNamespace(log_dir=tmp_path/'logs'))
    if drift=='binding':
        with sqlite3.connect(c) as db:db.execute("UPDATE v4_quarter SET fiscal_quarter='Q4'")
    before=(c.read_bytes(),p.read_bytes())
    if drift:
        with pytest.raises((PermissionError,ValueError),match={
                'authorization':'EXACT_AUTHORIZATION','baseline':'BASELINE_STALE','binding':'CURRENT_BINDING_STALE'}[drift]):
            d.register(tmp_path,q,a,authorized_artifact_fingerprint='wrong' if drift=='authorization' else a['artifact_fingerprint'])
        assert not q.exists() and not (tmp_path/'fundamental_reports/source_dispositions').exists()
    else:
        for _ in range(2):d.register(tmp_path,q,a,authorized_artifact_fingerprint=a['artifact_fingerprint'])
        assert len(d.list_items(q))==1
        with sqlite3.connect(q) as db:assert db.execute(f'SELECT COUNT(*) FROM {d.TABLE}_audit').fetchone()[0]==1
    assert not entered and (c.read_bytes(),p.read_bytes())==before
