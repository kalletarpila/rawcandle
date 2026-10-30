from copy import deepcopy
import json
import sqlite3

import pytest

from rawcandle.fundamentals.admin import accounting_boundary_review as b
from rawcandle.fundamentals.admin import refresh_copy_runtime as runtime, refresh_production as production
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.admin.refresh_fundamentals import validate_complete_history
from rawcandle.fundamentals.phase13b_foundation import online_backup
from tests.test_wfrd_accounting_boundary_review import case, row, NOW
from tests.provider_capture_fixtures import acquired
from rawcandle.fundamentals import source_capture as capture


def application(case):
    result=b.evaluate(case['p'],case['c'],case['h'],case['identity'],decision=case['decision'])
    assert result['applied'] and not result['stale']
    return result


def changes(case, app):
    current={d:runtime.load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    change=b.comparison('WFRD',current,case['h'],app);change['identity']=case['identity']
    return [change]


def build(case, name='production', app=None):
    app=application(case) if app is None else app
    provider=case['tmp']/f'{name}_provider.db';canonical=case['tmp']/f'{name}_canonical.db'
    online_backup(case['p'],provider);online_backup(case['c'],canonical)
    production.build_provider_candidate(provider,{'WFRD':case['h']},{'WFRD':case['identity']},
        changes=changes(case,app),applied_at=NOW)
    return provider,canonical,app


def semantics(provider):
    with b._ro(provider) as c:
        effective=[(list(b._key(dict(r))),b.effective_fiscalperiod(c,dict(r))) for r in c.execute("SELECT * FROM sharadar_fundamental_observation WHERE ticker='WFRD' ORDER BY dimension,date,reportperiod")]
        context=b._records(c,b.CONTEXT)
    return {'native':{d:b.current_provider_history(provider,'WFRD',d) for d in ('ARQ','MRQ')},
            'archive':b.historical_evidence(provider),'context':context,
            'decisions':b.installed_decisions(provider),'effective':effective}


def test_production_provider_and_canonical_match_test_semantics(case):
    before={p:b.file_fingerprint(p) for p in (case['p'],case['c'])}
    provider,canonical,app=build(case)
    test_provider=case['tmp']/'test_provider.db';test_canonical=case['tmp']/'test_canonical.db'
    online_backup(case['p'],test_provider);online_backup(case['c'],test_canonical)
    runtime.replace_provider_histories(test_provider,{'WFRD':case['h']},{'WFRD':case['identity']},
        applied_at='2026-10-27T12:00:00Z',boundary_applications=b.applied_applications(changes(case,app)))
    assert semantics(provider)==semantics(test_provider)
    assert b.installed_decisions(provider)==[case['decision']]
    assert b.historical_evidence(provider)[0]['original']==case['proposal']['evidence']['mrq']['accepted']
    for path in (provider,test_provider):
        native=b.current_provider_history(path,'WFRD','MRQ')
        assert len(native)==1 and b._key(native[0]['observation'])==b.CURRENT_MRQ_KEY
        assert native[0]['context']['calculation_eligible'] is False
        assert b.historical_evidence(path)[0]['calculation_eligible'] is False
    production.fresh_rebuild_canonical(provider,canonical,applied_at=NOW,affected_company_ids=[1])
    runtime.fresh_rebuild_canonical(test_provider,test_canonical,applied_at=NOW,affected_company_ids=[1])
    assert b.validate_expected_store(provider,{'WFRD':app},canonical_db=canonical)['validated']
    def projection(path):
        with b._ro(path) as c:
            return [tuple(r) for r in c.execute("SELECT q.company_id,q.fiscal_year,q.fiscal_quarter,q.period_end,q.first_public_result_date,f.revenue,f.shares_outstanding,f.parent_equity,s.dimension,s.fiscalperiod,s.effective_fiscalperiod,s.fiscal_identity_resolution_id FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) JOIN v4_parent_equity_source s USING(quarter_id) ORDER BY q.company_id,q.fiscal_year,q.fiscal_quarter")]
    assert projection(canonical)==projection(test_canonical)
    data=projection(canonical)
    assert [(r[1],r[3],r[4]) for r in data if r[0]==1]==[(2019,'2019-12-31','2020-03-16'),(2020,'2020-12-31','2021-02-19')]
    assert data[0][8:]==('ARQ','2020-Q4','2019-Q4',case['proposal']['resolution_id'])
    assert data[1][8:]==('ARQ','2020-Q4','2020-Q4',None)
    assert data[2][5]==99  # Unrelated company remains unchanged.
    assert before=={p:b.file_fingerprint(p) for p in before}


def test_extraction_is_generic_ordered_and_ignores_unapplied():
    first={'applied':True};second={'applied':True}
    items=[{'ticker':'FIRST','accounting_boundary_resolution':first},
           {'ticker':'NONE'}, {'ticker':'FALSE','accounting_boundary_resolution':{'applied':False}},
           {'ticker':'SECOND','accounting_boundary_resolution':second}]
    actual=b.applied_applications(items)
    assert list(actual)==['FIRST','SECOND'] and actual['FIRST'] is first and actual['SECOND'] is second
    with pytest.raises(b.BoundaryReviewError,match='AMBIGUOUS'):
        b.applied_applications(items+[items[0]])


def test_production_dispatches_all_selected_objects_without_queue_lookup(case,monkeypatch):
    candidate=case['tmp']/'candidate.db';online_backup(case['p'],candidate)
    apps=[{'ticker':ticker,'accounting_boundary_resolution':{'applied':True,'decision':{}}} for ticker in ('A','B')]
    seen=[]
    monkeypatch.setattr(production,'replace_provider_histories',lambda *a,**kw:seen.append(kw['boundary_applications']) or {})
    production.build_provider_candidate(candidate,{}, {},changes=apps,applied_at=NOW)
    assert set(seen[0])=={'A','B'}
    production.build_provider_candidate(candidate,{}, {},changes=[{'ticker':'A'}],applied_at=NOW)
    assert seen[1]=={}


@pytest.mark.parametrize('mutation',['stale','phase','decision','missing_decision','malformed_decision','missing_key','ticker','conflict','proposal_link','synthetic'])
def test_invalid_candidate_application_fails_before_installation(case,mutation):
    app=deepcopy(application(case));histories=deepcopy(case['h']);ticker='WFRD'
    if mutation=='stale':app['stale']=True
    elif mutation=='phase':app['phase']='UNKNOWN'
    elif mutation=='decision':app['decision']['operator']='tampered'
    elif mutation=='missing_decision':app.pop('decision')
    elif mutation=='malformed_decision':app['decision']=[]
    elif mutation=='proposal_link':app['proposal_fingerprint']='0'*64
    elif mutation=='ticker':ticker='OTHER'
    elif mutation=='missing_key':
        raw=[deepcopy(r['_acquisition_payload']) for r in histories['ARQ'].rows]
        captured=acquired(raw,full=False)
        assert [dict(r) for r in captured]==raw
        # Omit the reviewed key from the candidate after full acquisition.
        histories['ARQ']=validate_complete_history([r for r in captured if b._key(r)!=b.ARQ_KEY],ticker='WFRD',dimension='ARQ')
    elif mutation=='conflict':
        raw=[deepcopy(r['_acquisition_payload']) for r in histories['MRQ'].rows]
        # Retain the full synthetic provider shape and every original conflict
        # value. The extra metrics already declared by the fixture stay NULL.
        conflict=row(('WFRD','MRQ','2019-12-14','2019-12-13'),'2019-Q4',ncfo=1)
        conflict_raw={**raw[0],**conflict}
        assert {k:conflict_raw[k] for k in conflict}==conflict
        captured=acquired(raw,full=False)
        extra=acquired([conflict_raw],full=False)
        assert [dict(r) for r in captured]==raw and dict(extra[0])==conflict_raw
        histories['MRQ']=validate_complete_history([*captured,*extra],ticker='WFRD',dimension='MRQ')
    else:app['decision']['copy_only']=True
    if mutation in ('missing_key','conflict'):
        assert all(h.status=='COMPLETE' and not h.capture_failures for h in histories.values())
        assert all(capture.require(r) for h in histories.values() for r in h.rows)
    provider=case['tmp']/'invalid_provider.db';online_backup(case['p'],provider)
    before=b.file_fingerprint(provider)
    reason={'missing_key':'BOUNDARY_CURRENT_KEY_MISSING_OR_DUPLICATED',
            'conflict':'BOUNDARY_NEW_ACCOUNTING_CONFLICT'}.get(mutation)
    with pytest.raises((b.BoundaryReviewError,KeyError),match=reason):
        production.build_provider_candidate(provider,{ticker:histories},{ticker:case['identity']},
            changes=[{'ticker':ticker,'accounting_boundary_resolution':app}],applied_at=NOW)
    assert b.installed_decisions(provider)==[] and b.file_fingerprint(provider)==before


def test_production_postflight_detects_missing_expected_state(case):
    provider=case['tmp']/'missing_state.db';online_backup(case['p'],provider)
    # Reproduce the pre-fix candidate: valid native input, no reviewed state.
    runtime.replace_provider_histories(provider,{'WFRD':case['h']},{'WFRD':case['identity']},applied_at=NOW)
    from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
    paths=BatchAddTickerPaths(provider,case['c'],case['tmp']/'analysis.db',case['tmp']/'market.db',case['tmp']/'taxonomy.db')
    with pytest.raises(b.BoundaryReviewError,match='EXPECTED_DECISION_MISSING'):
        production._postflight(paths=paths,histories={'WFRD':case['h']},merge_plans=None,
            canonical_result={},analysis_result={},expected_roles={},refresh_state={},as_of_date='2026-10-27',
            boundary_applications={'WFRD':application(case)})


@pytest.mark.parametrize('corruption',['lineage','payload','date','pb'])
def test_expected_state_checks_lineage_payload_dates_and_pb(case,corruption):
    provider,canonical,app=build(case)
    production.fresh_rebuild_canonical(provider,canonical,applied_at=NOW,affected_company_ids=[1])
    if corruption=='lineage':
        app=deepcopy(app);d=app['decision'];d['operator']='different-operator'
        d['decision_fingerprint']=fingerprint({k:v for k,v in d.items() if k!='decision_fingerprint'})
    elif corruption=='payload':
        with sqlite3.connect(provider) as c:
            row=c.execute("SELECT po.observation_id,po.payload_json FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) WHERE s.ticker='WFRD' AND s.dimension='ARQ' AND s.reportperiod='2019-12-31'").fetchone()
            payload=json.loads(row[1]);payload['equity']=1
            c.execute('UPDATE provider_observation SET payload_json=? WHERE observation_id=?',(json.dumps(payload),row[0]))
    else:
        with sqlite3.connect(canonical) as c:
            c.execute("UPDATE v4_quarter SET first_public_result_date='2020-03-17' WHERE fiscal_year=2019" if corruption=='date' else "UPDATE v4_parent_equity_source SET fiscal_identity_resolution_id='wrong' WHERE quarter_id=(SELECT quarter_id FROM v4_quarter WHERE fiscal_year=2019)")
    with pytest.raises(b.BoundaryReviewError):b.validate_expected_store(provider,{'WFRD':app},canonical_db=canonical)


def test_actual_production_path_forwards_revalidated_application_before_canonical(case,monkeypatch):
    from tests.test_fundamentals_admin_refresh_production import _rehearsal_fixture,_install_rehearsal_doubles
    paths,runs,preview,fp,test_id=_rehearsal_fixture(case['tmp'])
    paths.provider_db.unlink();online_backup(case['p'],paths.provider_db)
    _install_rehearsal_doubles(monkeypatch,paths)
    app=application(case);change=changes(case,app)[0]
    assert change['classification'] in production.REPLACEMENT_CLASSES
    current={d:runtime.load_current_history(case['p'],'WFRD',d) for d in ('ARQ','MRQ')}
    merge=runtime.build_source_history_merge('WFRD',current,case['h'])
    actual={'state':{},'schema':{'schema_fingerprint':'schema'},'discovery':{'observed_source_max_lastupdated':'2026-10-22'},
            'ticker_changes':[change],'histories':{'WFRD':case['h']},'merge_plans':{'WFRD':merge},
            'refresh_set_fingerprint':fp,'review_partition':{'held':[],'global_blockers':[]}}
    monkeypatch.setattr(production,'revalidate_bound_source',lambda *a,**kw:actual)
    seen=[]
    def replace(*args,**kwargs):
        seen.append(kwargs['boundary_applications'])
        return runtime.replace_provider_histories(*args,**kwargs)
    monkeypatch.setattr(production,'replace_provider_histories',replace)
    def stop_after_provider(provider,*args,**kwargs):
        assert b.validate_expected_store(provider,{'WFRD':app})['validated']
        raise RuntimeError('FIXTURE_STOP_BEFORE_PUBLICATION')
    monkeypatch.setattr(production,'fresh_rebuild_canonical',stop_after_provider)
    monkeypatch.setattr(b,'queued_decision',lambda *a,**kw:pytest.fail('Candidate builder must not look up approvals independently'))
    result=production.run_production_apply(preview_payload_path=preview,preview_fingerprint=fp,test_run_id=test_id,
        source_paths=paths,run_root=runs,temp_root=case['tmp']/'lanes',backup_root=case['tmp']/'backups',
        journal_path=case['tmp']/'journal.json',lock_path=case['tmp']/'production.lock',
        scheduler_log_dir=str(case['tmp']/'scheduler'),confirm_production=True,rehearsal=True)
    assert seen==[{'WFRD':app}]
    assert result['outcome']=='FAILED' and result['failed_stage']=='CANONICAL_CANDIDATE'
    assert not result['write_boundary_crossed'] and 'FIXTURE_STOP' in result['error']
