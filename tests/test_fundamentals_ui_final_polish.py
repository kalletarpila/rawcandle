"""Final UI grouping/summary changes do not create or consume backend decisions."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import flet as ft
import pytest

from rawcandle.fundamentals.admin.operational_presentation import NORMAL, DEEP_REVIEW, boundary_route
from rawcandle.fundamentals.admin.review_evidence_presentation import evidence_summary
from tests.test_fundamentals_review_action_first import provider, ownership, text, walk, policy, diagnostic
from tests.test_fundamentals_operational_presentation import OperationalService, page_for, boundary, workflow
from rawcandle.fundamentals.admin.ui_service import AdminUIRunResult


@pytest.fixture(autouse=True)
def fixed_history_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,29,12,tzinfo=timezone.utc)
    monkeypatch.setattr('rawcandle.fundamentals.admin.recent_history.datetime',Clock)


def with_boundary(status):
    class Service(OperationalService):
        def list_accounting_boundary_reviews(self):
            item=boundary();item['status']=status;item['proposal']['evidence']['identity']={'ticker':'WFRD'}
            return [item]
    return Service


@pytest.mark.parametrize('status',['APPROVED','RESOLVED','PUBLISHED','SUPERSEDED'])
def test_completed_operator_boundary_evidence_is_history_not_current_deep(status):
    item=boundary();item['status']=status;original=deepcopy(item)
    assert boundary_route(item).mode==NORMAL and item==original
    _,c=page_for(with_boundary(status)(providers=[provider('FDX'),provider('RRC',reason='SAME_FISCAL_SOURCE_KEY_REPLACEMENT')]))
    assert 'Fundamentals: REVIEW REQUIRED' in c.operational_summary_field.value
    assert 'Current reviews requiring action: 2' in c.operational_summary_field.value
    assert 'Deep reviews requiring action: 0' in c.operational_summary_field.value
    assert 'Next action: Review current exceptions.' in c.operational_summary_field.value
    assert 'No deep review action required' in text(c.deep_review_column)
    assert status not in text(c.accounting_history_column) and status in text(c.accounting_history_column,collapsed=True)
    assert 'WFRD' in text(c.accounting_history_column,collapsed=True)
    assert 'c'*64 not in text(c.deep_review_column,collapsed=True)
    assert 'c'*64 in text(c.accounting_history_column,collapsed=True)


@pytest.mark.parametrize('status',['OPEN','STALE','REJECTED','UNKNOWN_UNRESOLVED'])
def test_unresolved_boundary_keeps_deep_attention_and_summary_first_evidence(status):
    _,c=page_for(with_boundary(status)())
    assert 'Fundamentals: DEEP_REVIEW' in c.operational_summary_field.value
    assert 'Deep reviews requiring action: 1' in c.operational_summary_field.value
    assert status in text(c.deep_review_column)
    assert not c.accounting_history_column.controls
    details=c.deep_review_column.controls[0].controls[1].controls[0]
    assert not details.expanded
    summary,raw=details.content.controls
    assert 'ARQ source:' in summary.value and 'proposal_fingerprint' not in summary.value
    assert not raw.controls[0].expanded
    assert json.loads(raw.controls[0].content.controls[0].value)['status']==status


def test_section_order_titles_and_empty_details_visibility():
    _,c=page_for(OperationalService())
    panels=[node for node in c.content.controls if isinstance(node,ft.ExpansionPanelList)]
    titles=[node.controls[0].header.title.value for node in panels]
    assert titles==['Run history and cleanup evidence','Review — current exceptions','Deep Review — exceptional evidence',
                    'Advanced — administration tools and workflow stages','Technical details']
    assert not c.technical_details_section.visible
    assert not c.selected_review_evidence.visible
    assert not c.provider_history_column.visible and not c.ownership_history_column.visible and not c.accounting_history_column.visible


@pytest.mark.parametrize('reason,brief,investigate',[
    ('INTERIOR_SOURCE_KEY_REMOVAL','Interior source key disappeared','If still unresolved:'),
    ('SAME_FISCAL_SOURCE_KEY_REPLACEMENT','Same-fiscal source key replacement detected','If replacement persists:'),
])
def test_generic_provider_compact_fields_and_no_long_hover(reason,brief,investigate):
    item=provider('GENERIC',reason=reason);original=deepcopy(item)
    service=OperationalService(providers=[item]);_,c=page_for(service);row=c.review_queue_column.controls[0]
    shown=text(row)
    assert brief in shown and 'Recommended now: Wait for Providers' in shown
    assert 'Then: Retry after later provider/source refresh' in shown and investigate in shown
    assert 'Approval: unavailable' in shown and 'Guidance only;' not in shown
    assert row.wrap and all(not getattr(control,'tooltip',None) for control in row.controls[:4])
    assert row.controls[7].visible and row.controls[8].visible and not row.controls[9].visible
    assert not c.selected_review_evidence.visible
    row.controls[6].on_click(None)
    assert c.selected_review_evidence.visible and c.selected_review_evidence.controls[0].expanded
    assert c.selected_review_evidence.controls[0].header.title.value=='Evidence for GENERIC'
    summary,raw=c.selected_review_evidence.controls[0].content.controls
    assert brief in summary.value and reason not in summary.value
    assert not raw.controls[0].expanded
    assert json.loads(raw.controls[0].content.controls[1].value)==item
    assert reason in text(c.selected_review_evidence,collapsed=True)
    assert item==original and not service.actions


def test_selection_clears_when_item_no_longer_in_visible_population():
    service=OperationalService(providers=[provider()]);_,c=page_for(service)
    c.review_queue_column.controls[0].controls[6].on_click(None)
    service.providers=[];c.review_queue_refresh_button.on_click(None)
    assert not c.selected_review_evidence.visible and not service.actions


def test_terminal_ownership_is_compact_audit_only_with_nested_exact_json():
    item=ownership('AMT',status='PUBLISHED')
    item['result']={'publication':{'published_at':'2026-10-29T06:00:00Z','generation_id':'generation',
                    'postflight':'PASSED','recovery':'NOT_REQUIRED'},'cleanup':{'cleanup_outcome':'COMPLETED'}}
    original=deepcopy(item);_,c=page_for(OperationalService(owners=[item]))
    assert c.pb_ownership_status_field.value.startswith('No action required') and not c.pb_ownership_column.controls
    assert 'PUBLISHED' not in text(c.review_section,collapsed=True)
    history=c.ownership_history_column.controls[0].controls[0]
    assert not history.expanded
    card=history.content.controls[0];assert card.controls[0].value=='AMT · PUBLISHED · AUTO_CONTINUED · 2026-10-29'
    assert 'Next action:' not in text(card) and 'Reason:' not in text(card)
    assert not any(isinstance(node,(ft.ElevatedButton,ft.TextButton,ft.IconButton)) for node in walk(card,collapsed=True))
    panel=card.controls[1].controls[0];assert not panel.expanded
    summary,raw=panel.content.controls
    for field in ('Ownership type:','Provider factor:','Shares:','Publication generation: generation','Postflight: PASSED','Recovery: NOT_REQUIRED','Cleanup: COMPLETED','Action required: No'):
        assert field in summary.value
    assert not raw.controls[0].expanded
    assert json.loads(raw.controls[0].content.controls[0].value)=={'stored_review':item}
    assert item==original


@pytest.mark.parametrize('status',['OPEN','HELD','APPROVED','AUTO_CONTINUED'])
def test_current_ownership_is_not_moved_to_completed_history(status):
    item=ownership('CURRENT',status=status);_,c=page_for(OperationalService(owners=[item]))
    assert 'CURRENT' in text(c.pb_ownership_column) and not c.ownership_history_column.controls


def test_nonempty_top_level_technical_details_available_but_collapsed():
    class Runner(OperationalService):
        def full_workflow(self,**kwargs):return AdminUIRunResult(status='FAILED',message='Failure',mode='FULL_WORKFLOW',outcome='FAILED',technical_error='Exact error')
    _,c=page_for(Runner());c.normal_workflow_button.on_click(None)
    assert c.technical_details_section.visible and not c.technical_details_section.controls[0].expanded
    assert 'Exact error' in text(c.technical_details_section,collapsed=True)
    assert 'Exact error' not in text(c.content)


def test_manual_and_deep_policy_routing_and_controls_are_preserved():
    item=ownership('DEEP',classification='REVIEW_REQUIRED_FACTOR_CHANGE');p=policy(item,'DEEP_REVIEW/BLOCKED')
    _,c=page_for(OperationalService(owners=[item],diag=diagnostic([p])))
    assert 'DEEP' in text(c.deep_review_column) and 'DEEP' not in text(c.ownership_history_column)
    assert 'Deep reviews requiring action: 1' in c.operational_summary_field.value
    assert 'Keep on hold' in [node.text for node in walk(c.deep_review_column) if isinstance(node,ft.TextButton)]
