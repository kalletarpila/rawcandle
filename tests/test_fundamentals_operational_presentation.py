"""Operational display from structured facts, with native actions untouched."""
from copy import deepcopy
from dataclasses import replace
import json

import flet as ft
import pytest

from rawcandle.fundamentals.admin.operational_presentation import (
    NORMAL, REVIEW, DEEP_REVIEW, review_route, boundary_route, workflow_view, normal_summary,
)
from rawcandle.fundamentals.admin.review_presentation import provider_review, ownership_review
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService, AdminUIRunResult, AdminUIHistoryEntry
from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
from tests.test_fundamentals_admin_ui import _Page
from tests.test_fundamentals_review_action_first import Service, provider, ownership, policy, diagnostic, text, walk


def workflow(outcome='COMPLETED', **changes):
    result=dict(mode='FULL_WORKFLOW',operation_type='REFRESH_FUNDAMENTALS',outcome=outcome,
                production_completed=outcome=='COMPLETED',
                terminal_summary=dict(review_required_count=0,reporting_integrity_error_count=0),
                publication_outcome=dict(postflight='PASSED',rollback_recovery='NOT_REQUIRED'))
    result.update(changes)
    return result


class OperationalService(Service):
    def publication_safety_status(self):return {'status':'CLEAR','production_writes_blocked':False}
    def operational_settings(self):return dict(full_workflow=True,ownership_enabled=True)
    def list_accounting_boundary_reviews(self):return []


def page_for(service):
    page=_Page();controls=build_fundamentals_admin_page(page=page,service=service)
    return page,controls


def boundary():
    return dict(status='OPEN',proposal=dict(proposal_fingerprint='c'*64,evidence=dict(
        arq=dict(source_key=['AAA','ARQ','2020-01-01','2019-12-31'],provider_label='2020-Q4',accepted_label='2019-Q4',action='PRESERVE'),
        mrq=dict(removed_key=['old'],current_key=['new'],historical_role='HISTORICAL_ONLY',current_role='CURRENT',action='RETAIN'),authority={'receipt':'d'*64})))


def test_zero_review_landing_is_normal_and_details_history_are_secondary():
    _,c=page_for(OperationalService(owners=[ownership('PAST',status='PUBLISHED')]))
    assert 'Fundamentals: NORMAL' in c.operational_summary_field.value
    assert 'Current reviews requiring action: 0' in c.operational_summary_field.value
    assert 'Deep reviews requiring action: 0' in c.operational_summary_field.value
    assert 'no action required' in c.operational_summary_field.value
    assert 'P/B auto-continuation: enabled' in c.operational_summary_field.value
    assert not c.review_section.controls[0].expanded and not c.deep_review_section.controls[0].expanded
    assert c.review_section.controls[0].header.title.value=='Review — current exceptions'
    assert 'PAST' not in text(c.content) and 'PAST' in text(c.content,collapsed=True)
    assert 'Run history' not in text(c.content) or 'Run history and cleanup evidence' in text(c.content)


@pytest.mark.parametrize('outcome',['COMPLETED','NO_CHANGE'])
def test_success_and_no_change_operational_results_are_concise(outcome):
    raw=workflow(outcome);view=workflow_view(raw)
    assert view['mode']==NORMAL and f'Financial workflow: {outcome}' in view['rows']
    assert 'Action required: No' in view['rows']
    assert len(view['rows'])<=7


def test_safe_stopped_financial_and_completed_ownership_are_separate():
    raw=workflow('STOPPED',ownership_auto=dict(financial_outcome='STOPPED',financial_precondition='SAFE_FINANCIAL_NO_OP',status='COMPLETED',published=1))
    original=deepcopy(raw);view=workflow_view(raw);shown='\n'.join(view['rows'])
    assert 'STOPPED — safe no-op (NO_SAFE_CHANGES)' in shown
    assert 'P/B auto-continuation: COMPLETED · published 1' in shown
    assert 'Financial publication: No' in shown and view['mode']==NORMAL
    assert raw==original


@pytest.mark.parametrize('change,visible',[
    ({'outcome':'FAILED'},'Financial workflow: FAILED'),
    ({'publication_outcome':{'postflight':'FAILED'}},'Financial postflight: FAILED'),
    ({'publication_outcome':{'postflight':'NOT_RUN'}},'Financial postflight: NOT_RUN'),
    ({'publication_outcome':{'rollback_recovery':'RECOVERY_FAILED'}},'Financial recovery: RECOVERY_FAILED'),
    ({'ownership_auto':{'status':'FAILED_OR_STALE','failed_stale':1}},'P/B auto-continuation failed or became stale'),
    ({'ownership_auto':{'status':'COMPLETED','cleanup':{'cleanup_outcome':'NOT_ELIGIBLE'}}},'Ownership cleanup: NOT_ELIGIBLE'),
    ({'terminal_summary':{'terminal_cleanup':{'status':'FAILED'}}},'Financial cleanup: FAILED'),
])
def test_anomalies_remain_primary_and_route_to_deep(change,visible):
    view=workflow_view(workflow(**change))
    assert view['mode']==DEEP_REVIEW and visible in '\n'.join(view['rows'])


def test_backend_review_stop_is_review_not_technical_success():
    view=workflow_view(workflow('STOPPED',terminal_summary={'stop_kind':'REVIEW_REQUIRED','review_required_count':1}))
    assert view['mode']==REVIEW and 'Action required: Yes' in view['rows']
    assert 'Financial workflow: STOPPED' in view['rows']


def test_running_is_explicit_without_inventing_scheduler_activity():
    view=workflow_view(workflow('RUNNING',workflow_status='RUNNING'))
    assert view['running'] and view['rows'][0]=='Full Workflow: running'
    lines=normal_summary(loaded=True,review_count=0,deep_count=0,safety={},settings={},last_workflow=view)
    assert 'running' in lines[0] and lines[-1]=='Next action: Wait for the running workflow.'


def test_recovery_block_and_unloaded_state_never_show_false_all_clear():
    for loaded,safety in ((False,{}),(True,{'production_writes_blocked':True})):
        shown='\n'.join(normal_summary(loaded=loaded,review_count=0,deep_count=0,safety=safety,settings={}))
        assert 'no action required' not in shown


def test_current_provider_reviews_keep_staged_guidance_and_conditional_deep_advice():
    item=provider();original=deepcopy(item)
    route=review_route(provider_review(item))
    assert route.mode==REVIEW and 'If still unresolved:' in route.deep_guidance
    _,c=page_for(OperationalService(providers=[item,provider('SECOND',reason='SAME_FISCAL_SOURCE_KEY_REPLACEMENT')]))
    assert 'Current reviews requiring action: 2' in c.operational_summary_field.value
    assert 'Recommended now: Wait for Providers' in text(c.review_queue_column)
    assert 'Then: Retry after later provider/source refresh' in text(c.review_queue_column)
    assert 'If replacement persists:' in text(c.review_queue_column)
    assert item==original and not c.review_queue_column.controls[0].controls[9].visible


def test_accounting_boundary_deep_evidence_not_exposed_on_landing_or_review():
    class BoundaryService(OperationalService):
        def list_accounting_boundary_reviews(self):return [boundary()]
    _,c=page_for(BoundaryService());stored=boundary();original=deepcopy(stored)
    assert boundary_route(stored).mode==DEEP_REVIEW and stored==original
    assert 'Deep reviews requiring action: 1' in c.operational_summary_field.value
    assert 'c'*64 not in text(c.content) and 'c'*64 not in text(c.review_queue_column)
    assert 'c'*64 in text(c.deep_review_column,collapsed=True)
    assert 'Accounting-boundary review — OPEN' in text(c.deep_review_column)


def test_ownership_policy_deep_case_remains_actionable_without_frontend_reclassification():
    item=ownership(classification='REVIEW_REQUIRED_IDENTITY_CHANGE');p=policy(item,'DEEP_REVIEW/BLOCKED')
    route=review_route(ownership_review(item,p),policy=p)
    assert route.mode==DEEP_REVIEW
    _,c=page_for(OperationalService(owners=[item],diag=diagnostic([p])))
    assert 'Deep reviews requiring action: 1' in c.operational_summary_field.value
    assert 'AAA' not in text(c.pb_ownership_column) and 'AAA' in text(c.deep_review_column)
    assert 'Keep on hold' in [b.text for b in walk(c.deep_review_column) if isinstance(b,ft.TextButton)]


def test_ordinary_approval_optional_name_note_and_required_hold_note_preserved():
    item=ownership();item['new']['parent_equity_usd']=1000
    class Approvals(OperationalService):
        def preview_pb_ownership_review(self,*a,**k):
            return dict(held_current={'reason':'HELD'},hypothetical_current={'value':2,'reason':'OK'})
        def approve_pb_ownership_review(self,*a,**k):
            self.actions.append(k);return {'candidate_canonical':'inactive'}
    service=Approvals(owners=[item]);page,c=page_for(service)
    actions=c.pb_ownership_column.controls[0].controls[1].controls
    actions[0].on_click(None);dialog=page.dialog
    assert '(optional)' in dialog.content.controls[1].label and '(optional)' in dialog.content.controls[3].label
    assert 'Hash:' not in dialog.content.controls[0].value
    confirm=dialog.content.controls[2];confirm.value=True;confirm.on_change(None)
    assert not dialog.actions[1].disabled
    dialog.actions[1].on_click(None)
    assert service.actions[-1]['operator']==service.actions[-1]['note']==''
    actions[1].on_click(None)
    assert page.dialog.actions[1].disabled and page.dialog.content.controls[1].label=='Hold reason'


def test_normal_workflow_one_click_existing_owner_and_compact_result_with_details(tmp_path):
    raw=workflow();raw.update(run_id='run',artifact_dir=str(tmp_path),preview_fingerprint='f'*64)
    service=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)
    response=service._finalize(raw,default_message='done')
    assert response.operational_summary==workflow_view(raw)
    class Runner(OperationalService):
        def full_workflow(self,**kwargs):
            self.actions.append(kwargs)
            assert 'running' in c.operational_summary_field.value
            assert c.normal_workflow_button.disabled
            kwargs['progress_callback']({'current_stage_id':'Preview','message':'f'*64})
            assert not c.progress_details.controls[0].expanded
            return replace(response,summary_rows=('Technical receipt '+'f'*64,))
    runner=Runner();page,c=page_for(runner)
    c.normal_workflow_button.on_click(None)
    assert len(runner.actions)==1 and runner.actions[0]['operation_type']=='REFRESH_FUNDAMENTALS'
    assert not page.opened_dialogs
    assert 'Financial workflow: COMPLETED' in c.status_field.value and 'f'*64 not in c.status_field.value
    assert 'f'*64 in text(c.technical_details_column)
    assert not c.progress_details.controls[0].expanded
    assert 'f'*64 not in text(c.content)


def test_last_retained_workflow_read_is_presentation_only(tmp_path):
    directory=tmp_path/'record';directory.mkdir()
    raw=workflow('NO_CHANGE');(directory/'result.json').write_text(json.dumps(raw))
    original=(directory/'result.json').read_bytes()
    service=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)
    assert service.history_operational_summary('record')==workflow_view(raw)
    assert (directory/'result.json').read_bytes()==original


def test_unregistered_deep_diagnostic_stays_visible_in_summary():
    item=ownership();_,c=page_for(OperationalService(diag=diagnostic([policy(item,'DEEP_REVIEW/BLOCKED')])))
    assert 'Deep reviews requiring action: 1' in c.operational_summary_field.value
    assert 'no action required' not in c.operational_summary_field.value
    assert 'Current deep source diagnostic' in text(c.deep_review_column)
    assert 'No deep review action required' not in text(c.deep_review_column)


def test_running_retained_workflow_does_not_require_a_final_result():
    class Running(OperationalService):
        def history_entries(self,**kwargs):
            return [AdminUIHistoryEntry(run_id='running',operation_type='REFRESH_FUNDAMENTALS',
                outcome='RUNNING',status='running',mode='FULL_WORKFLOW',completed_at_utc=None,report_available=False)]
        def history_operational_summary(self,*a,**k):raise ValueError('No final result yet')
    _,c=page_for(Running())
    assert 'running' in c.operational_summary_field.value
    assert 'Wait for the running workflow.' in c.operational_summary_field.value
    assert 'Full Workflow result unavailable' not in c.operational_summary_field.value


def test_unavailable_operational_config_is_not_reported_as_healthy():
    class Unavailable(OperationalService):
        def operational_settings(self):raise OSError('Config unreadable')
    _,c=page_for(Unavailable())
    assert 'Operational settings unavailable.' in c.operational_summary_field.value
    assert 'no action required' not in c.operational_summary_field.value


def test_info_opens_evidence_without_changing_review_state():
    service=OperationalService(providers=[provider()]);_,c=page_for(service)
    evidence=c.review_section.controls[0].content.controls[3]
    assert not evidence.controls[0].expanded
    c.review_queue_column.controls[0].controls[6].on_click(None)
    assert evidence.controls[0].expanded and not service.actions


def test_execution_exception_cannot_leave_a_normal_landing_summary():
    class Failing(OperationalService):
        def full_workflow(self,**kwargs):raise RuntimeError('Failed to start workflow')
    _,c=page_for(Failing());c.normal_workflow_button.on_click(None)
    assert 'Fundamentals: DEEP_REVIEW' in c.operational_summary_field.value
    assert 'Administration run failed' in c.status_field.value


def test_history_read_failure_is_visible_outside_collapsed_history():
    class Unreadable(OperationalService):
        def history_entries(self,**kwargs):raise OSError('History unreadable')
    _,c=page_for(Unreadable())
    assert 'Administration history could not be loaded' in c.operational_summary_field.value
    assert 'no action required' not in c.operational_summary_field.value
