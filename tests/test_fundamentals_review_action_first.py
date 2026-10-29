"""Action-first review UI from existing state/eligibility, never new decisions."""
from copy import deepcopy
from dataclasses import fields
import json
import pytest
import flet as ft
from rawcandle.fundamentals.admin.review_presentation import (
    ReviewPresentation,provider_review,ownership_review,review_groups,
)
from tests.test_fundamentals_admin_ui import _Page
from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page


def provider(ticker='AAA', *, reason='INTERIOR_SOURCE_KEY_REMOVAL',status='OPEN'):
    return dict(ticker=ticker,status=status,classification='TRUE_SOURCE_REMOVAL',review_scope='TICKER_LOCAL_REVIEW',
        reason_codes=[reason,'OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW','RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON'],
        reason_explanations=['Exact published source observation no longer returned.'],
        human_summary='Source review',accept_retained_history_eligible=False,
        accept_retained_history_reason='Review reasons are not retained-history compatible.',
        accept_fiscal_revision_eligible=False,confirm_true_removal_eligible=False,
        affected_source_keys=[dict(ticker=ticker,dimension='MRQ',date='2025-08-31',reportperiod='2025-08-31')],
        fiscal_identities=[dict(fiscal_year=2026,fiscal_quarter='Q1')])


def ownership(ticker='AAA', *, status='OPEN',classification='CONTINUATION_CANDIDATE'):
    item=dict(ticker=ticker,case_id='case_'+ticker+'_'+status,candidate_hash='bound',status=status,classification=classification,
        current_pb_status='OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED',
        previous=dict(fiscal_year=2026,fiscal_quarter='Q2',release_type='ORDINARY_COMMON',economic_unit_rule='ORDINARY_COMMON',accepted_sharesbas=100,provider_declared_factor=1,accepted_category='Common'),
        new=dict(fiscal_year=2026,fiscal_quarter='Q3',sharesbas=120,sharefactor=1,category='Common',observation_id='obs',content_hash='hash'),deltas={'shares_percent':20})
    if status in ('PUBLISHED','AUTO_CONTINUED'):
        item['approval']={'decision_type':'AUTO_CONTINUED','policy_version':'PB_ORDINARY_AUTO_CONTINUATION_V1','record':{'approval_mode':'AUTO_CONTINUED'}}
    return item


def diagnostic(items=(), *, enabled=True):
    return dict(enabled=enabled,policy_version='PB_ORDINARY_AUTO_CONTINUATION_V1',items=list(items),
        auto_continue=sum(i['partition']=='AUTO_CONTINUE' for i in items),manual_review=sum(i['partition']=='MANUAL_REVIEW' for i in items),deep_review=sum(i['partition']=='DEEP_REVIEW/BLOCKED' for i in items))


def policy(item,partition='MANUAL_REVIEW',reason='EXPLICIT_POLICY_HOLD'):
    return dict(case=item,ticker=item['ticker'],partition=partition,reasons=[{'reason':reason}],warnings=[])


class Service:
    def __init__(self,providers=(),owners=(),diag=None):
        self.providers=list(providers);self.owners=list(owners);self.diag=diag or diagnostic();self.reads=[];self.actions=[]
    def capabilities(self):return ()
    def history_entries(self,**kwargs):return []
    def list_refresh_review_queue(self,*,active_only=True):
        self.reads.append(('provider',active_only));items=[i for i in self.providers if not active_only or i['status']!='RESOLVED']
        return {'status':'READY' if items else 'EMPTY','items':items}
    def list_pb_ownership_reviews(self,*,include_resolved=False):
        self.reads.append(('ownership',include_resolved));return self.owners
    def pb_ownership_auto_diagnostics(self):return self.diag
    def resolve_refresh_review(self,*a,**k):self.actions.append((a,k));pytest.fail('Rendering must not mutate provider reviews')
    def approve_pb_ownership_review(self,*a,**k):pytest.fail('Rendering must not approve ownership')
    def hold_pb_ownership_review(self,*a,**k):pytest.fail('Rendering must not hold ownership')
    def publish_pb_ownership_reviews(self,*a,**k):pytest.fail('Rendering must not publish ownership')


def render(service):
    controls=build_fundamentals_admin_page(page=_Page(),service=service)
    controls.review_queue_refresh_button.on_click(None)
    return controls


def walk(control, *, collapsed=False):
    if getattr(control,'visible',True) is False:return
    yield control
    if isinstance(control,ft.ExpansionPanel):
        if control.header:yield from walk(control.header,collapsed=collapsed)
        if collapsed or control.expanded:
            if control.content:yield from walk(control.content,collapsed=collapsed)
        return
    for name in ('controls',):
        for child in getattr(control,name,None) or ():yield from walk(child,collapsed=collapsed)
    for name in ('content','title'):
        child=getattr(control,name,None)
        if isinstance(child,ft.Control):yield from walk(child,collapsed=collapsed)


def text(control, *, collapsed=False):
    return '\n'.join(str(c.value) for c in walk(control,collapsed=collapsed) if isinstance(c,ft.Text))


@pytest.mark.parametrize('reason,expected',[('INTERIOR_SOURCE_KEY_REMOVAL','interior published source key disappeared'),('SAME_FISCAL_SOURCE_KEY_REPLACEMENT','same-fiscal source key replacement')])
def test_incompatible_source_exception_has_operational_explanation_and_no_approval(reason,expected):
    source=provider(reason=reason);original=deepcopy(source);service=Service(providers=[source]);controls=render(service)
    row=controls.review_queue_column.controls[0];visible=text(row)
    assert 'YES / REVIEW' in visible and expected in visible and 'Retained-history approval unavailable' in visible
    assert 'not retained-history compatible' in visible and 'Wait for Providers' in visible and 'Retry reevaluation after source data changes' in visible
    assert row.controls[7].visible and row.controls[8].visible and row.controls[9].visible is False
    assert source==original and service.actions==[]


@pytest.mark.parametrize('status',['OPEN','WAITING_PROVIDER','RETRY_REEVALUATION','RESOLVED'])
def test_wait_retry_availability_follows_backend_unresolved_status(status):
    view=provider_review(provider(status=status))
    assert ('WAIT_FOR_PROVIDER' in view.allowed_actions)==(status!='RESOLVED')
    assert ('RETRY_REEVALUATION' in view.allowed_actions)==(status!='RESOLVED')
    assert view.history_or_terminal==(status=='RESOLVED')
    assert view.needs_action==(status=='OPEN')


@pytest.mark.parametrize('reason,final_step',[
    ('INTERIOR_SOURCE_KEY_REMOVAL','If still unresolved: Investigate source history manually.'),
    ('SAME_FISCAL_SOURCE_KEY_REPLACEMENT','If replacement persists: Manually inspect old vs new source binding and financial payload before any retained-history or repair decision.'),
])
def test_open_source_guidance_is_staged_generic_and_does_not_change_actions(reason,final_step):
    item=provider('UNRELATED',reason=reason);original=deepcopy(item)
    service=Service(providers=[item]);controls=render(service)
    row=controls.review_queue_column.controls[0];shown=text(row)
    assert 'Recommended now: Wait for Providers.' in shown
    assert 'After later provider/source refresh: Retry reevaluation after source data changes.' in shown
    assert final_step in shown and 'no automatic escalation' in shown
    assert row.controls[9].visible is False and row.controls[7].visible and row.controls[8].visible
    assert provider_review(item).allowed_actions==('VIEW_DETAILS','WAIT_FOR_PROVIDER','RETRY_REEVALUATION')
    assert item==original and not service.actions


def test_replacement_guidance_takes_priority_without_losing_other_reason_evidence():
    item=provider();item['reason_codes'].append('SAME_FISCAL_SOURCE_KEY_REPLACEMENT')
    view=provider_review(item)
    assert 'If replacement persists:' in view.next_action_explanation
    assert 'interior published source key disappeared' in view.reason
    controls=render(Service(providers=[item]));row=controls.review_queue_column.controls[0]
    assert all(code in row.controls[3].tooltip for code in item['reason_codes'])


@pytest.mark.parametrize('status',['WAITING_PROVIDER','RETRY_REEVALUATION','RESOLVED'])
def test_staged_open_guidance_does_not_leak_to_waiting_pending_or_terminal(status):
    view=provider_review(provider(status=status))
    assert 'Recommended now:' not in view.next_action
    assert 'If still unresolved:' not in view.next_action_explanation
    assert 'After later provider/source refresh:' not in view.next_action_explanation


@pytest.mark.parametrize('blocked_action',['WAIT_FOR_PROVIDER','RETRY_REEVALUATION'])
def test_staged_guidance_does_not_recommend_backend_blocked_actions(monkeypatch,blocked_action):
    monkeypatch.setattr('rawcandle.fundamentals.admin.review_presentation.BLOCKED_ACTIONS',(blocked_action,))
    view=provider_review(provider())
    assert blocked_action not in view.allowed_actions
    if blocked_action=='WAIT_FOR_PROVIDER':assert 'Wait for Providers' not in view.next_action
    else:assert 'After later provider/source refresh:' not in view.next_action_explanation


def test_staged_guidance_does_not_override_existing_approval_or_pending_paths():
    for field in ('accept_retained_history_eligible','accept_fiscal_revision_eligible','confirm_true_removal_eligible','approval_pending_publication'):
        item=provider();item[field]=True
        view=provider_review(item)
        assert 'Recommended now:' not in view.next_action
        assert 'If still unresolved:' not in view.next_action_explanation


@pytest.mark.parametrize('field,action',[('accept_retained_history_eligible','ACCEPT_RETAINED_HISTORY'),('accept_fiscal_revision_eligible','ACCEPT_FISCAL_IDENTITY_REVISION'),('confirm_true_removal_eligible','CONFIRM_TRUE_SOURCE_REMOVAL')])
def test_only_explicit_backend_eligibility_exposes_approval(field,action):
    item=provider();assert action not in provider_review(item).allowed_actions
    item[field]=True;assert action in provider_review(item).allowed_actions
    item['status']='RESOLVED';assert action not in provider_review(item).allowed_actions


def test_source_history_collapsed_and_codes_still_in_details():
    service=Service(providers=[provider(),provider('DONE',status='RESOLVED')]);controls=render(service)
    controls.review_queue_include_resolved_checkbox.value=True;controls.review_queue_include_resolved_checkbox.on_change(None)
    current,history=controls.review_queue_column.controls
    assert current.controls[0].value=='AAA' and history.controls[0].expanded is False
    assert 'DONE' not in text(controls.review_queue_column) and 'DONE' in text(history,collapsed=True)
    historical_row=history.controls[0].content.controls[0]
    assert all(historical_row.controls[i].visible is False for i in range(7,12))
    current.controls[6].on_click(None)
    assert 'INTERIOR_SOURCE_KEY_REMOVAL' in controls.review_queue_detail_field.value
    assert 'AAA / MRQ / 2025-08-31 / 2025-08-31' in controls.review_queue_detail_field.value


@pytest.mark.parametrize('status',['PUBLISHED','SUPERSEDED'])
@pytest.mark.parametrize('ticker',['TMUS','AMT','BA','DHR','GE'])
def test_terminal_ownership_is_history_without_action_buttons(ticker,status):
    item=ownership(ticker,status=status);original=deepcopy(item);service=Service(owners=[item]);controls=render(service)
    assert 'No action required' in controls.pb_ownership_status_field.value
    assert 'automatic 0 / manual 0 / deep 0' in controls.pb_ownership_status_field.value
    assert 'Automatic continuation enabled · PB_ORDINARY_AUTO_CONTINUATION_V1' in controls.pb_ownership_status_field.value
    assert len(controls.pb_ownership_column.controls)==1
    history=controls.pb_ownership_column.controls[0];assert history.controls[0].expanded is False
    assert ticker not in text(history) and ticker in text(history,collapsed=True)
    assert status in text(history,collapsed=True) and 'No action required' in text(history,collapsed=True)
    assert not any(isinstance(c,(ft.ElevatedButton,ft.TextButton)) for c in walk(history,collapsed=True))
    assert item==original and ('ownership',True) in service.reads


@pytest.mark.parametrize('partition,classification',[('MANUAL_REVIEW','CONTINUATION_CANDIDATE'),('DEEP_REVIEW/BLOCKED','REVIEW_REQUIRED_FACTOR_CHANGE')])
def test_manual_deep_current_ownership_remains_visible_with_correct_controls(partition,classification):
    item=ownership(classification=classification);p=policy(item,partition,reason='SOURCE_PAYLOAD_INCOMPLETE')
    service=Service(owners=[item,ownership('DONE',status='PUBLISHED')],diag=diagnostic([p]));controls=render(service)
    assert 'Needs your attention (1)' in controls.pb_ownership_status_field.value
    current_surface=controls.deep_review_column if partition=='DEEP_REVIEW/BLOCKED' else controls.pb_ownership_column
    assert 'AAA' in text(current_surface) and 'DONE' not in text(controls.pb_ownership_column)
    card=current_surface.controls[0];buttons=[c for c in walk(card) if isinstance(c,(ft.ElevatedButton,ft.TextButton))]
    labels=[b.text for b in buttons]
    assert 'Keep on hold' in labels
    assert ('Approve quarterly ownership continuation' in labels)==(classification=='CONTINUATION_CANDIDATE')
    assert 'SOURCE_PAYLOAD_INCOMPLETE' in text(card,collapsed=True)


def test_held_and_pending_ownership_are_not_history():
    items=[ownership('HOLD',status='HELD'),ownership('APP',status='APPROVED'),ownership('AUTO',status='AUTO_CONTINUED')]
    current,historical=review_groups(items,ownership_review)
    assert len(current)==3 and historical==[] and all(v.needs_action for _,v in current)
    assert 'APPROVE_OWNERSHIP' not in ownership_review(items[0]).allowed_actions
    assert 'PREVIEW_PUBLICATION' in ownership_review(items[1]).allowed_actions
    assert 'Automatic decision pending' in ownership_review(items[2]).reason


def test_policy_enabled_auto_candidate_is_current_without_manual_urgency():
    item=ownership();p=policy(item,'AUTO_CONTINUE');p['reasons']=[]
    assert ownership_review(item,p,policy_enabled=True).needs_action is False
    assert ownership_review(item,p,policy_enabled=False).needs_action is True
    controls=render(Service(owners=[item],diag=diagnostic([p])))
    assert 'awaiting normal workflow' in controls.pb_ownership_status_field.value
    assert 'AAA' in text(controls.pb_ownership_column) and 'automatic 1 / manual 0 / deep 0' in controls.pb_ownership_status_field.value


def test_current_diagnostics_without_queue_rows_cannot_show_false_all_clear():
    item=ownership();controls=render(Service(diag=diagnostic([policy(item)])))
    assert 'Needs attention:' in controls.pb_ownership_status_field.value
    assert 'No action required' not in controls.pb_ownership_status_field.value
    assert 'No approval controls are enabled' in text(controls.pb_ownership_column)


def test_additional_unregistered_case_is_visible_alongside_current_queue_items():
    queued=ownership('QUEUED');missing=ownership('MISSING')
    controls=render(Service(owners=[queued],diag=diagnostic([policy(queued),policy(missing,'DEEP_REVIEW/BLOCKED')])))
    assert '1 additional current source case' in controls.pb_ownership_status_field.value
    assert 'MISSING' in text(controls.pb_ownership_column,collapsed=True)
    assert 'No approval controls are enabled for these unregistered diagnostic cases' in text(controls.pb_ownership_column)
    assert controls.review_queue_blocked_actions.visible is False


def test_both_surfaces_share_model_and_do_not_hide_unknown_current_states():
    keys={f.name for f in fields(ReviewPresentation)}
    assert {'display_status','classification','needs_action','next_action','next_action_explanation','history_or_terminal','allowed_actions','blocked_action_reason'}<=keys
    for view in (provider_review(provider(status='UNKNOWN_CURRENT')),ownership_review(ownership(status='UNKNOWN_CURRENT'))):
        assert view.needs_action and not view.history_or_terminal and view.allowed_actions==('VIEW_DETAILS',)


def test_rendering_uses_structured_inputs_without_database_or_action_calls(monkeypatch):
    monkeypatch.setattr('sqlite3.connect',lambda *a,**k:pytest.fail('Presentation must not read or write databases'))
    owners=[ownership('DONE',status='PUBLISHED'),ownership()];providers=[provider()]
    before=deepcopy((owners,providers));service=Service(providers=providers,owners=owners)
    controls=render(service)
    assert before==(owners,providers) and service.actions==[]
    assert 'Next action:' in text(controls.pb_ownership_column) and 'Next action:' in text(controls.review_queue_column)
