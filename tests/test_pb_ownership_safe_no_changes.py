"""Financial STOPPED is preserved while an exact safe no-op may sequence ownership."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from rawcandle.fundamentals.admin import pb_ownership_future as future, publication_journal as journal
from rawcandle.fundamentals.admin.full_workflow import run_refresh_full_workflow
from rawcandle.fundamentals.admin.refresh_operational_decision import refresh_operational_decision
from rawcandle.fundamentals.admin.refresh_scheduler import _full_workflow_summary
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_refresh_full_workflow import _stage
from tests.test_pb_ownership_future import project, ordinary, factory


def preview_no_safe_changes(root, *, run_id='financial_preview', held_tickers=('FDX','RRC')):
    held=[dict(ticker=t,scope='TICKER_LOCAL_REVIEW',queue={'status':'OPEN'}) for t in held_tickers]
    decision=refresh_operational_decision(safe_effective_changes=0,held_items=held,global_blockers=[],
        future_test_authorized=False,test_reason_code='NO_SAFE_CHANGES_TO_PUBLISH')
    return _stage(root,run_id,mode='PREVIEW',outcome='REVIEW_REQUIRED',extra={
        'summary_counts':dict(safe_changes=0,effective_changed_known=0,global_blockers=0,held_for_review=len(held),REVIEW_REQUIRED=len(held)),
        'operational_decision':decision,
        'refresh_preview':dict(future_test_authorized=False,review_partition={'held':held},
            ticker_changes=[dict(ticker=t,classification='REVIEW_REQUIRED',review_reason='TRUE_SOURCE_REMOVAL') for t in held_tickers])})


def safe_result(root, *, held_tickers=('FDX','RRC')):
    return run_refresh_full_workflow(run_root=root,preview_stage=lambda cb:preview_no_safe_changes(root,held_tickers=held_tickers),
        test_stage=lambda *a:pytest.fail('No financial Test'),production_stage=lambda *a:pytest.fail('No financial Production'))


@pytest.mark.parametrize('held_tickers',[(),('FDX','RRC')])
def test_exact_native_financial_terminal_is_safe_without_relabelling(tmp_path,held_tickers):
    result=safe_result(tmp_path,held_tickers=held_tickers);original=deepcopy(result)
    assert result['outcome']==result['workflow_status']=='STOPPED'
    assert result['terminal_summary']['stop_kind']=='NO_SAFE_CHANGES'
    assert result['terminal_summary']['production_database_writes']==0
    assert future.financial_result_allows_ownership_reconciliation(result)
    assert result==original


@pytest.mark.parametrize('outcome',['COMPLETED','NO_CHANGE'])
def test_existing_safe_results_remain_accepted(outcome):
    assert future.financial_result_allows_ownership_reconciliation({'outcome':outcome})


UNSAFE=[
    ('outcome','REVIEW_REQUIRED'),('workflow_status','RUNNING'),('completed_at_utc',None),
    ('terminal_summary.stop_kind','TECHNICAL_FAILURE'),('terminal_summary.child_status','FAILED'),
    ('terminal_summary.child_outcome','FAILED'),('terminal_summary.production_entered',True),
    ('terminal_summary.production_database_writes',1),('terminal_summary.production_database_writes',False),
    ('production_database_writes',1),('production_completed',True),('current_stage','Production update'),
    ('source_summary.global_blockers',1),('source_summary.safe_changes',1),('source_summary.effective_changed_known',1),
    ('source_summary.classification_counts.global_blockers',1),
    ('operational_decision.global_blocker_count',1),('operational_decision.global_blockers',[{'reason':'blocked'}]),
    ('operational_decision.local_hold_blocked_safe_changes',True),('operational_decision.local_hold_blocked_safe_changes',None),
    ('operational_decision.test_gate.reason_code','MISSING_AUTHORIZATION'),
    ('operational_decision.test_gate.authorized',True),('operational_decision.production_gate.state','AUTHORIZED'),
    ('technical_failure','failed'),('errors',[{'message':'failed'}]),('write_boundary_crossed',True),
    ('postflight_state','FAILED'),('publication_outcome.postflight','FAILED'),('rollback_recovery_state','REQUIRED'),
    ('publication_recovery',{'status':'FAILED'}),('publication_journal_state','PREPARED'),
    ('publication_journal',{'state':'COMPLETED','postflight_state':'FAILED','rollback_recovery_state':'NOT_REQUIRED'}),
    ('generation_state','PREPARING'),('preparing_generation',True),
    ('terminal_summary.source','UNKNOWN'),('stages',[]),('source_summary',None),('operational_decision',None),
]


@pytest.mark.parametrize('path,value',UNSAFE)
def test_unsafe_or_ambiguous_stopped_is_rejected(tmp_path,path,value):
    result=safe_result(tmp_path);target=result;keys=path.split('.')
    for key in keys[:-1]:target=target.setdefault(key,{})
    target[keys[-1]]=value
    # Also exercise consistent unsafe decisions; rejection must not rely only
    # on the duplicate decision envelopes disagreeing.
    result['terminal_summary']['operational_decision']=deepcopy(result['operational_decision'])
    assert not future.financial_result_allows_ownership_reconciliation(result)


@pytest.mark.parametrize('trigger',['MANUAL','SCHEDULER'])
def test_shared_service_safe_stopped_runs_native_ownership_and_preserves_financial_stop(project,monkeypatch,trigger):
    w=project
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=w.run)
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:preview_no_safe_changes(w.runs))
    response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',trigger_source=trigger,ownership_auto_enabled=True)
    data=json.loads((Path(response.artifact_dir)/'workflow_result.json').read_text())
    assert data['outcome']==data['workflow_status']=='STOPPED' and data['production_completed'] is False
    assert data['ownership_auto']['financial_precondition']=='SAFE_FINANCIAL_NO_OP'
    assert data['ownership_auto']['status']=='COMPLETED' and data['ownership_auto']['published']==1
    assert [i['ticker'] for i in data['operational_decision']['held_items']]==['FDX','RRC']
    report=(Path(response.artifact_dir)/'workflow_report.md').read_text()
    assert 'Financial STOPPED is preserved' in report and 'SAFE_FINANCIAL_NO_OP' in report
    summary=_full_workflow_summary(response=response,payload=data,run_root=w.runs)
    assert summary['outcome']=='STOPPED' and summary['scheduler_summary_result']=='COMPLETED'
    assert summary['technical_failure'] is None
    assert summary['pb_ownership_auto']['financial_precondition']=='SAFE_FINANCIAL_NO_OP'
    assert summary['held_review_tickers']==['FDX','RRC']


@pytest.mark.parametrize('outcome',['COMPLETED','NO_CHANGE'])
def test_service_still_sequences_existing_safe_results(tmp_path,monkeypatch,outcome):
    result=safe_result(tmp_path);result.update(outcome=outcome,workflow_status='COMPLETED');calls=[]
    monkeypatch.setattr('rawcandle.fundamentals.admin.full_workflow.run_refresh_full_workflow',lambda **k:deepcopy(result))
    service=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False,
        ownership_auto_runner=lambda **k:calls.append(k) or future.summary(True,status='NO_AUTO_CANDIDATES'))
    service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',ownership_auto_enabled=True)
    assert len(calls)==1


def test_safe_stopped_disabled_switch_has_no_auto_decision(project,monkeypatch):
    w=project;before=w.queue.read_bytes()
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=w.run)
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:preview_no_safe_changes(w.runs))
    response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',ownership_auto_enabled=False)
    data=json.loads((Path(response.artifact_dir)/'workflow_result.json').read_text())
    assert data['ownership_auto']['status']=='DISABLED' and w.queue.read_bytes()==before


@pytest.mark.parametrize('field,value',[('state','PREPARED'),('postflight_state','FAILED'),('rollback_recovery_state','REQUIRED')])
def test_native_runtime_journal_gate_still_blocks_before_ownership_preview(project,monkeypatch,field,value):
    w=project;before=w.queue.read_bytes()
    evidence=dict(journal_format_version=journal.JOURNAL_FORMAT_VERSION,state='COMPLETED',postflight_state='PASSED',rollback_recovery_state='NOT_REQUIRED');evidence[field]=value
    journal._atomic_json(w.root/'data/.fundamentals_admin_publication_journal.json',evidence)
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=w.run)
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:preview_no_safe_changes(w.runs))
    response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',ownership_auto_enabled=True)
    data=json.loads((Path(response.artifact_dir)/'workflow_result.json').read_text())
    assert data['ownership_auto']['status']=='FAILED_OR_STALE'
    assert data['ownership_auto']['reason']=='PB_FUTURE_RECOVERY_REQUIRED'
    assert w.queue.read_bytes()==before and not (Path(response.artifact_dir)/'ownership_auto').exists()


@pytest.mark.parametrize('field',['scope','hold_proof','problem_scope'])
def test_unproven_local_quarantine_is_rejected(tmp_path,field):
    result=safe_result(tmp_path)
    if field=='scope': result['operational_decision']['held_items'][0]['scope']='GLOBAL_BLOCKING_REVIEW'
    elif field=='hold_proof':result['operational_decision'].pop('local_hold_blocked_safe_changes')
    else:result['terminal_summary']['problem_items'][0]['review_scope']='GLOBAL_BLOCKING_REVIEW'
    result['terminal_summary']['operational_decision']=deepcopy(result['operational_decision'])
    assert not future.financial_result_allows_ownership_reconciliation(result)


@pytest.mark.parametrize('field',['terminal_summary','operational_decision','source_summary','stages','workflow_status','completed_at_utc','production_completed'])
def test_missing_required_structured_guarantee_rejects(tmp_path,field):
    result=safe_result(tmp_path);result.pop(field)
    assert not future.financial_result_allows_ownership_reconciliation(result)


def test_native_preparing_generation_still_blocks_before_decision(project,monkeypatch):
    w=project;before=w.queue.read_bytes();(w.root/'data/fundamentals_generations/.pending.preparing').mkdir()
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=w.run)
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:preview_no_safe_changes(w.runs))
    response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',ownership_auto_enabled=True)
    data=json.loads((Path(response.artifact_dir)/'workflow_result.json').read_text())
    assert data['ownership_auto']['reason']=='PB_FUTURE_PREPARING_GENERATION'
    assert w.queue.read_bytes()==before and data['ownership_auto']['published']==0
