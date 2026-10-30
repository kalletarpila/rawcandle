from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import historical_freeze as freeze
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    compare_ticker_histories, load_current_history, validate_complete_history, resolve_identity,
)
from rawcandle.fundamentals.admin.refresh_copy_runtime import fresh_rebuild_canonical, replace_provider_histories, _quarter_rows
from rawcandle.fundamentals.admin.refresh_review_queue import (
    RefreshReviewQueue, classify_review_scope, partition_changes, match_true_removal_approval,
    CONFIRM_TRUE_SOURCE_REMOVAL,
)
from rawcandle.fundamentals.schema.migrations import bootstrap_database, CANONICAL_SCHEMA_SQL, PROVIDER_SCHEMA_SQL
from tests import test_fundamentals_admin_refresh_full_workflow_production_parity as native

POLICY = {'as_of_date': date(2026, 9, 22), 'historical_source_window_review_years': 0}

from tests.provider_capture_fixtures import trusted_history as validate_complete_history


def trusted(histories):
    return {d: validate_complete_history(rows, ticker=rows[0]['ticker'], dimension=d)
            for d, rows in histories.items()}


@pytest.fixture
def sources(tmp_path, monkeypatch):
    p = BatchAddTickerPaths(*(tmp_path / f'{r}.db' for r in ('provider','canonical','analysis','market','taxonomy')))
    bootstrap_database(p.provider_db, 'fundamentals_provider', PROVIDER_SCHEMA_SQL, native.NOW)
    bootstrap_database(p.canonical_db, 'fundamentals_v4', CANONICAL_SCHEMA_SQL, native.NOW)
    native._insert_identities(p.canonical_db)
    h = {t:{d:[native._source_row(t,d,y,q) for y in (2024,2025) for q in range(1,5)]
            for d in ('ARQ','MRQ')} for t in ('AAA','BBB')}
    identities = {t:{'company_id':i,'security_id':i*10,'provider_security_id':str(i*100)} for i,t in enumerate(h,1)}
    replace_provider_histories(p.provider_db, {t:trusted(v) for t,v in h.items()}, identities, applied_at=native.NOW)
    monkeypatch.setattr('rawcandle.fundamentals.admin.refresh_copy_runtime._events', lambda: ())
    fresh_rebuild_canonical(p.provider_db, p.canonical_db, applied_at=native.NOW)
    return p,h,identities


def evaluate(p, ticker, history, approval=None):
    current = {d:load_current_history(p.provider_db,ticker,d) for d in ('ARQ','MRQ')}
    histories = trusted(history)
    c = compare_ticker_histories(ticker,current,histories,true_removal_approval=approval,**POLICY)
    c['identity'] = resolve_identity(p,ticker)
    return freeze.apply_to_comparison(c,canonical_db=p.canonical_db,provider_db=p.provider_db,
        current=current,histories=histories,policy_args=POLICY)


def change(history, case):
    h = deepcopy(history)
    row = h['ARQ'][1]  # interior accepted 2024 Q2
    if case == 'payload':row['revenue'] += 77
    elif case == 'key':row['date'] = '2024-08-12'
    elif case == 'disappearance':h['ARQ'].pop(1)
    elif case == 'replacement':
        row['date'] = '2024-08-12';row['revenue'] += 77
    elif case == 'equity':row.update(equity=333, equityusd=333)
    elif case == 'factor':row['sharefactor'] = 2
    elif case == 'metadata':row['lastupdated'] = '2026-09-20'
    return h


def file_hashes(p):
    return {r:hashlib.sha256(Path(x).read_bytes()).hexdigest() for r,x in p.as_dict().items() if Path(x).exists()}


@pytest.mark.parametrize('loss',['unverified_projection','absent_factor'])
def test_local_capture_loss_protects_frozen_values_without_financial_conflict(sources,loss):
    from tests.provider_capture_fixtures import acquired
    from rawcandle.fundamentals import source_capture as capture
    from rawcandle.fundamentals.admin.refresh_fundamentals import validate_complete_history as native_validate
    p,h,_=sources
    before=file_hashes(p)
    accepted=freeze.accepted_history(p.canonical_db,p.provider_db,1)[0]
    raw=capture.raw_payload(accepted['_accepted_source'])
    if loss=='unverified_projection':
        incoming={k:v for k,v in accepted['_accepted_source'].items() if not k.startswith('_')}
    else:
        raw.pop('sharefactor')
        incoming=native_validate(acquired([raw],full=False),ticker='AAA',dimension='ARQ').rows[0]
    decision=freeze.historical_financial_freeze_decision(accepted,incoming)
    assert decision['decision']==freeze.HELD
    assert decision['reason_codes']==[capture.UNVERIFIED if loss=='unverified_projection' else capture.INCOMPLETE]
    assert decision['value_changes']=={}
    assert 'FINANCIAL_PAYLOAD_CHANGED' not in decision['reason_codes']
    assert file_hashes(p)==before


def test_verified_provider_null_is_real_frozen_source_evidence(sources):
    from tests.provider_capture_fixtures import acquired
    from rawcandle.fundamentals import source_capture as capture
    from rawcandle.fundamentals.admin.refresh_fundamentals import validate_complete_history as native_validate
    p,h,_=sources
    accepted=freeze.accepted_history(p.canonical_db,p.provider_db,1)[0]
    # Pure decision fixture: the accepted economic factor was explicitly 1.
    accepted['_accepted_source']['_acquisition_payload']['sharefactor']=1
    raw=capture.raw_payload(accepted['_accepted_source']);raw['sharefactor']=None
    incoming=native_validate(acquired([raw],full=False),ticker='AAA',dimension='ARQ').rows[0]
    decision=freeze.historical_financial_freeze_decision(accepted,incoming)
    assert decision['reason_codes']==['ECONOMIC_SOURCE_FACTOR_CHANGED']
    assert decision['value_changes']['provider_sharefactor']=={'accepted':1.0,'incoming':None}
    assert 'capture_integrity' not in decision


@pytest.mark.parametrize('period,expected',[('2024-12-31','FROZEN_NO_CONFLICT'),('2025-01-01','NOT_FROZEN')])
def test_exact_authoritative_cutoff(sources,period,expected):
    p,_,_ = sources
    row = freeze.accepted_history(p.canonical_db,p.provider_db,1)[-1]
    row['period_end'] = period
    # Fiscal label deliberately disagrees with the cutoff: period_end wins.
    row['fiscal_year'] = 2030
    assert freeze.historical_financial_freeze_decision(row,row['_accepted_source'])['decision'] == expected
    changed = dict(row['_accepted_source'], revenue=row['revenue'] + 1)
    assert freeze.historical_financial_freeze_decision(row,changed)['decision'] == (
        freeze.HELD if period == freeze.CUTOFF else 'NOT_FROZEN')
    if period == freeze.CUTOFF:
        row['period_end'] = '2024-12-30'
        held = freeze.historical_financial_freeze_decision(row,row['_accepted_source'])
        assert held['decision'] == freeze.HELD and 'PERIOD_END_CHANGED' in held['reason_codes']


@pytest.mark.parametrize('case',['payload','key','disappearance','replacement','equity','factor'])
def test_frozen_conflicts_held_with_exact_evidence_and_local_partition(sources,case):
    p,h,_ = sources
    before = file_hashes(p)
    c = evaluate(p,'AAA',change(h['AAA'],case))
    assert c['classification'] == 'REVIEW_REQUIRED'
    d = c['historical_freeze']['conflicts'][0]
    assert d['decision'] == freeze.HELD
    assert d['accepted']['period_end'] == '2024-06-30'
    assert d['accepted_source']['_provider_observation_id']
    assert d['evidence_fingerprint'] == freeze.fingerprint({k:v for k,v in d.items() if k!='evidence_fingerprint'})
    assert d['incoming_source'] is not None or case == 'disappearance'
    if case == 'equity':
        assert d['value_changes']['parent_equity'] == {'accepted':None,'incoming':333}
    assert classify_review_scope(c)['scope'] == 'TICKER_LOCAL_REVIEW'
    partition = partition_changes([c,{'ticker':'BBB','classification':'HISTORICAL_REVISION'}])
    assert not partition['global_blockers']
    assert [x['ticker'] for x in partition['safe_changes']] == ['BBB']
    assert file_hashes(p) == before


def test_unchanged_and_metadata_only_do_not_invent_freeze_conflict(sources):
    p,h,_ = sources
    for history in (h['AAA'],change(h['AAA'],'metadata')):
        c = evaluate(p,'AAA',history)
        assert 'historical_freeze' not in c
        assert c['classification'] != 'REVIEW_REQUIRED'


def test_native_missing_shares_parent_equity_guard_and_empty_payload(sources):
    p,_,_ = sources
    row = freeze.accepted_history(p.canonical_db,p.provider_db,1)[0]
    row.update(shares_outstanding=None, parent_equity=None, parent_equity_usd=None)
    source = deepcopy(row['_accepted_source'])
    source['sharesbas'] = None
    source['_acquisition_payload'].update(sharesbas=None,equity=777,equityusd=777)
    row['_accepted_source'] = source
    assert freeze.historical_financial_freeze_decision(row,source)['decision'] == 'FROZEN_NO_CONFLICT'
    source = deepcopy(source);source['sharesbas'] = 100
    assert freeze.historical_financial_freeze_decision(row,source)['decision'] == freeze.HELD


def test_existing_publication_date_bootstrap_preserved(sources):
    p,_,_ = sources
    before = _quarter_rows(p.canonical_db);after = deepcopy(before)
    key = (1,2024,'Q1');before[key]['first_public_result_date'] = None
    freeze.validate_candidate(before,after)
    after[key]['first_public_result_date'] = '2026-01-01'
    with pytest.raises(ValueError,match='CANONICAL_MUTATION_BLOCKED'):
        freeze.validate_candidate(before,after)


def test_recent_payload_change_remains_safe(sources):
    p,h,_ = sources
    updated = deepcopy(h['AAA']);updated['ARQ'][-1]['revenue'] += 77
    c = evaluate(p,'AAA',updated)
    assert c['classification'] == 'HISTORICAL_REVISION'
    assert 'historical_freeze' not in c


def test_review_queue_reused_and_guidance_is_presentation_only(sources,tmp_path):
    from rawcandle.fundamentals.admin.review_presentation import provider_review
    from rawcandle.fundamentals.admin.operational_presentation import review_route
    from rawcandle.fundamentals.admin.review_evidence_presentation import evidence_summary
    from rawcandle.fundamentals.admin.refresh_review_queue import present_review_item
    p,h,_ = sources;c = evaluate(p,'AAA',change(h['AAA'],'payload'))
    q = RefreshReviewQueue(tmp_path/'queue.db');scope = classify_review_scope(c)
    for run in ('preview1','preview2'):
        q.upsert_local(scope,run_id=run,published_binding='baseline')
    assert len(q.list_items()) == 1
    assert len([e for e in q.audit_history('AAA') if e['event_type']=='HISTORICAL_PROVIDER_CONFLICT_OBSERVED']) == 1
    original = q.get('AAA');v = provider_review(present_review_item(original))
    from tests.test_fundamentals_review_action_first import Service, render, text
    service = Service(providers=[present_review_item(original)])
    rendered = render(service)
    visible = text(rendered.review_queue_column)
    assert 'Historical value preserved' in visible and 'No immediate action required' in visible
    assert 'Frozen historical provider conflict' in visible
    assert not service.actions
    assert v.display_status == 'Historical value preserved'
    assert not v.needs_action and review_route(v).mode == 'REVIEW'
    assert v.next_action == 'No immediate action required.'
    assert not any(a.startswith('ACCEPT') or a == CONFIRM_TRUE_SOURCE_REMOVAL for a in v.allowed_actions)
    assert 'WAIT_FOR_PROVIDER' in v.allowed_actions and 'RETRY_REEVALUATION' in v.allowed_actions
    assert any('Evidence fingerprint:' in r for r in evidence_summary('provider',original))
    assert q.get('AAA') == original
    changed = change(h['AAA'],'payload');changed['ARQ'][1]['revenue'] += 1
    q.upsert_local(classify_review_scope(evaluate(p,'AAA',changed)),run_id='preview3',published_binding='baseline')
    audit = [e for e in q.audit_history('AAA') if e['event_type']=='HISTORICAL_PROVIDER_CONFLICT_OBSERVED']
    assert len(audit) == 2 and len(q.list_items()) == 1
    assert audit[0]['evidence']['historical_freeze']['conflicts'][0]['incoming_source']['revenue'] == h['AAA']['ARQ'][1]['revenue']+77
    terminal = {**original,'status':'RESOLVED'}
    assert provider_review(terminal).history_or_terminal
    assert provider_review(terminal).display_status != 'Historical value preserved'
    # Existing boundary exceptions remain routed by their separate native DTO.
    from rawcandle.fundamentals.admin.operational_presentation import boundary_route
    assert boundary_route({'status':'OPEN'}).mode == 'DEEP_REVIEW'


def test_copy_defence_blocks_bypassed_ordinary_mutation(sources,tmp_path):
    p,h,ids = sources
    pc,cc = tmp_path/'candidate-provider.db',tmp_path/'candidate-canonical.db'
    shutil.copy2(p.provider_db,pc);shutil.copy2(p.canonical_db,cc)
    replace_provider_histories(pc,{'AAA':trusted(change(h['AAA'],'payload'))},{'AAA':ids['AAA']},applied_at='2026-09-23T00:00:00Z')
    with pytest.raises(ValueError,match='HISTORICAL_FREEZE_CANONICAL_MUTATION_BLOCKED'):
        fresh_rebuild_canonical(pc,cc,applied_at='2026-09-23T00:00:00Z')


def test_exact_reviewed_repair_and_later_reverse_refresh_protected(sources,tmp_path):
    p,h,ids = sources
    replacement = change(h['AAA'],'replacement')
    c = evaluate(p,'AAA',replacement);scope = classify_review_scope(c)
    assert scope['review_type'] == 'TRUE_SOURCE_REMOVAL'
    q = RefreshReviewQueue(tmp_path/'review.db')
    q.upsert_local(scope,run_id='preview',published_binding='baseline')
    accepted = q.apply_action('AAA',CONFIRM_TRUE_SOURCE_REMOVAL,evidence={'source':'fixture','comment':'exact old vs new binding reviewed'})
    approval = match_true_removal_approval(accepted,scope,published_binding='baseline')
    assert approval['applied']
    approved = evaluate(p,'AAA',replacement,approval)
    d = approved['historical_freeze']['conflicts'][0]
    assert d['decision'] == freeze.ALLOWED
    assert approved['classification'] != 'REVIEW_REQUIRED'
    stale = change(replacement,'payload')
    assert not match_true_removal_approval(accepted,classify_review_scope(evaluate(p,'AAA',stale)),published_binding='baseline')['applied']
    tampered = deepcopy(approval);tampered['approval_evidence_fingerprint'] = 'tampered'
    with pytest.raises(ValueError,match='REPAIR_EVIDENCE_INVALID'):
        evaluate(p,'AAA',replacement,tampered)
    extra = deepcopy(replacement);extra['ARQ'][2]['revenue'] += 1
    mixed = evaluate(p,'AAA',extra,approval)
    assert mixed['classification'] == 'REVIEW_REQUIRED'
    assert {d['decision'] for d in mixed['historical_freeze']['conflicts']} == {freeze.ALLOWED,freeze.HELD}
    assert classify_review_scope(mixed)['scope'] == 'TICKER_LOCAL_REVIEW'
    before = _quarter_rows(p.canonical_db)
    pc,cc = tmp_path/'provider-copy.db',tmp_path/'canonical-copy.db'
    shutil.copy2(p.provider_db,pc);shutil.copy2(p.canonical_db,cc)
    replace_provider_histories(pc,{'AAA':trusted(replacement)},{'AAA':ids['AAA']},applied_at='2026-09-23T00:00:00Z')
    fresh_rebuild_canonical(pc,cc,applied_at='2026-09-23T00:00:00Z',historical_freeze_changes=[approved])
    after = _quarter_rows(cc)
    for key,row in before.items():
        if key == (1,2024,'Q2'):
            assert after[key]['revenue'] == row['revenue'] + 77
            assert after[key]['first_public_result_date'] == row['first_public_result_date']
        else:assert freeze.financial_state(after[key]) == freeze.financial_state(row)
    repaired_paths = BatchAddTickerPaths(pc,cc,p.analysis_db,p.market_db,p.taxonomy_db)
    reverse = evaluate(repaired_paths,'AAA',h['AAA'])
    assert reverse['classification'] == 'REVIEW_REQUIRED'
    assert reverse['historical_freeze']['conflicts'][0]['decision'] == freeze.HELD
    altered = deepcopy(approved);altered['historical_freeze']['conflicts'][0]['incoming_source']['revenue'] += 1
    with pytest.raises(ValueError,match='EVIDENCE_TAMPERED'):
        freeze.validate_candidate(before,after,[altered])


def test_mixed_copy_preserves_frozen_history_and_publishes_current_peer(sources,tmp_path):
    p,h,ids = sources
    held = evaluate(p,'AAA',change(h['AAA'],'payload'))
    current = deepcopy(h['BBB']);current['ARQ'][-1]['revenue'] += 77
    safe = evaluate(p,'BBB',current)
    assert [x['ticker'] for x in partition_changes([held,safe])['safe_changes']] == ['BBB']
    pc,cc = tmp_path/'provider-copy.db',tmp_path/'canonical-copy.db'
    shutil.copy2(p.provider_db,pc);shutil.copy2(p.canonical_db,cc)
    before = _quarter_rows(cc)
    replace_provider_histories(pc,{'BBB':trusted(current)},{'BBB':ids['BBB']},applied_at='2026-09-23T00:00:00Z')
    fresh_rebuild_canonical(pc,cc,applied_at='2026-09-23T00:00:00Z',historical_freeze_changes=[safe])
    after = _quarter_rows(cc)
    assert after[(2,2025,'Q4')]['revenue'] == before[(2,2025,'Q4')]['revenue'] + 77
    for key,row in before.items():
        if row['period_end'] <= freeze.CUTOFF or key[0] == 1:
            assert freeze.financial_state(after[key]) == freeze.financial_state(row)


def test_aged_out_retention_and_changed_reappearance_share_existing_contract(sources,tmp_path):
    from rawcandle.fundamentals.admin.refresh_fundamentals import build_source_history_merge
    p,h,ids = sources
    incoming = {d:rows[1:] for d,rows in h['AAA'].items()}
    current = {d:load_current_history(p.provider_db,'AAA',d) for d in ('ARQ','MRQ')}
    histories = trusted(incoming)
    policy = {'as_of_date':date(2030,1,1),'historical_source_window_review_years':3}
    c = compare_ticker_histories('AAA',current,histories,**policy);c['identity'] = resolve_identity(p,'AAA')
    c = freeze.apply_to_comparison(c,canonical_db=p.canonical_db,provider_db=p.provider_db,current=current,histories=histories,policy_args=policy)
    assert c['source_history_action']['historical_retained_rows'] == 2
    assert c['classification'] != 'REVIEW_REQUIRED' and 'historical_freeze' not in c
    merge = build_source_history_merge('AAA',current,histories,**policy)
    pc,cc = tmp_path/'retained-provider.db',tmp_path/'retained-canonical.db'
    shutil.copy2(p.provider_db,pc);shutil.copy2(p.canonical_db,cc)
    before = _quarter_rows(cc)
    replace_provider_histories(pc,{'AAA':histories},{'AAA':ids['AAA']},applied_at='2030-01-01T00:00:00Z',merge_plans={'AAA':merge})
    fresh_rebuild_canonical(pc,cc,applied_at='2030-01-01T00:00:00Z')
    assert {k:freeze.financial_state(r) for k,r in before.items()} == {k:freeze.financial_state(r) for k,r in _quarter_rows(cc).items()}
    reappeared = deepcopy(h['AAA']);reappeared['ARQ'][0]['revenue'] += 1
    copied = BatchAddTickerPaths(pc,cc,p.analysis_db,p.market_db,p.taxonomy_db)
    held = evaluate(copied,'AAA',reappeared)
    assert held['classification'] == 'REVIEW_REQUIRED'
    assert held['source_history_action']['current_source_reappearances'] == 2


@pytest.mark.parametrize('reviewed_repair',[False,True])
def test_native_disposable_generation_publication_and_cleanup(tmp_path,monkeypatch,reviewed_repair):
    original = native._histories
    def with_frozen(**kwargs):
        histories = original(**kwargs)
        for ticker,dimensions in histories.items():
            for d,rows in dimensions.items():
                rows[:0] = [native._source_row(ticker,d,2024,q) for q in range(1,5)]
        return histories
    monkeypatch.setattr(native,'_histories',with_frozen)
    f = native._fixture(tmp_path,monkeypatch)
    f.client.histories['AAA'] = change(
        with_frozen(revised=False)['AAA'] if reviewed_repair else f.client.histories['AAA'],
        'replacement' if reviewed_repair else 'payload')
    f.client.histories['BBB']['ARQ'][-1]['revenue'] += 19
    f.client.histories['BBB']['ARQ'][-1]['lastupdated'] = '2026-09-20'
    from rawcandle.fundamentals.admin.refresh_production import _publish_refresh_state
    from rawcandle.fundamentals.admin.refresh_fundamentals import source_schema
    _publish_refresh_state(f.paths.provider_db,source_watermark='2026-08-15',
        schema_fingerprint=source_schema(f.client)['schema_fingerprint'],
        run_id='accepted-fixture-baseline',completed_at=native.NOW)
    project = native._migrate_refresh_fixture_to_generation_layout(f,monkeypatch)
    from rawcandle.fundamentals.generations import resolve_active_generation
    old = resolve_active_generation(project,require_generation=True)
    before = _quarter_rows(old.role_paths()['canonical'])
    service = native._service(f,actual_production=True)
    if reviewed_repair:
        preview = native.run_preview(source_paths=f.paths,run_root=f.run_root,client=f.client)
        assert preview['summary_counts']['held_for_review'] == 1
        service.resolve_refresh_review('AAA',CONFIRM_TRUE_SOURCE_REMOVAL,
            evidence={'source':'copy-only fixture','comment':'reviewed exact replacement and financial payload'})
    result = service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='')
    assert result.outcome == 'COMPLETED', result
    workflow = native._workflow_payload(result)
    production = native._stage_payload(workflow,'Production update')
    assert production['analysis_candidate']['invocation_counts']['full_v2_rebuild'] == 1
    assert production['postflight']['cross_role_lineage']['analysis_matches_validated_candidate'] is True
    assert production['quarantine_evidence']['derived_analysis_rebuild_policy'] == 'FULL_V2_RP_RV_FROM_PRESERVED_CANONICAL_AND_SHARED_INPUTS'
    new = resolve_active_generation(project,require_generation=True)
    assert new.generation_id != old.generation_id
    after = _quarter_rows(new.role_paths()['canonical'])
    for key,row in before.items():
        if reviewed_repair and key == (1,2024,'Q2'):
            assert after[key]['revenue'] == row['revenue'] + 77
            assert after[key]['first_public_result_date'] == row['first_public_result_date']
            continue
        if key[0] == 1 or row['period_end'] <= freeze.CUTOFF:
            assert freeze.financial_state(after[key]) == freeze.financial_state(row)
    assert after[(2,2025,'Q4')]['revenue'] == before[(2,2025,'Q4')]['revenue'] + 19
    journal = json.loads(f.journal_path.read_text())
    assert journal['state'] == 'COMPLETED'
    assert journal['postflight_state'] == 'PASSED'
    native._assert_terminal_lane_cleanup(f)
