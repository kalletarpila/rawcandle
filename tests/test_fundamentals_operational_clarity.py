"""Wording/urgency from structured results, and bounded UI history paging."""
from copy import deepcopy
from dataclasses import replace
import asyncio
import ast
import json
from pathlib import Path
import subprocess

import flet as ft
import pytest

from rawcandle.fundamentals.admin.run_presentation import run_meaning,source_scan,NO_ACTION,REVIEW_WHEN_APPROPRIATE,ACTION_REQUIRED
from rawcandle.fundamentals.admin.refresh_operational_decision import refresh_operational_decision
from rawcandle.fundamentals.admin.operation_report import final_status_message
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService,AdminUIRunResult,AdminUIHistoryEntry
from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page
from tests.test_fundamentals_admin_ui import _Page,_write_run
from tests.test_fundamentals_operational_presentation import OperationalService,page_for,workflow
from tests.test_fundamentals_review_action_first import text,walk,provider


def preview(safe=0,held=2,global_count=0,*,technical=None,authorized=None):
    authorized=(safe>0 and global_count==0) if authorized is None else authorized
    d=refresh_operational_decision(safe_effective_changes=safe,held_items=[{'ticker':t,'scope':'TICKER_LOCAL_REVIEW'} for t in ('FDX','RRC')[:held]],
        global_blockers=[{'ticker':'BLOCK'}]*global_count,future_test_authorized=authorized,
        test_reason_code='SAFE_CHANGES_TEST_AUTHORIZED' if authorized else 'NO_SAFE_CHANGES_TO_PUBLISH',technical_failure=technical)
    return dict(operation_type='REFRESH_FUNDAMENTALS',mode='PREVIEW',outcome='FAILED' if technical else 'REVIEW_REQUIRED' if held or global_count else 'COMPLETED' if safe else 'NO_CHANGE',
        completed_at_utc='2026-10-29T17:00:00Z',operational_decision=d,
        summary_counts=dict(effective_changed_known=safe,safe_changes=safe,held_for_review=held,global_blockers=global_count),
        refresh_preview={'discovery':{'unique_changed_source_tickers':51}},preview_payload_path='/tmp/bound.json',preview_fingerprint='a'*64)


def test_successful_local_review_preview_has_no_false_failure_and_exact_audit_outcome(tmp_path):
    raw=preview();original=deepcopy(raw);view=run_meaning(raw)
    assert 'Preview completed' in view['headline'] and 'no new publishable changes' in view['headline']
    assert view['category']==REVIEW_WHEN_APPROPRIATE and 'FDX, RRC' in '\n'.join(view['rows'])
    assert 'did not block safe peer changes' in '\n'.join(view['rows'])
    assert final_status_message(raw)==view['headline'] and raw==original
    result=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)._finalize(raw,default_message='done')
    assert result.status=='COMPLETED' and result.outcome=='REVIEW_REQUIRED'
    class Reader(OperationalService):
        def preview(self,*args,**kwargs):return result
    _,c=page_for(Reader());c.operation_dropdown.value='REFRESH_FUNDAMENTALS';c.operation_dropdown.on_change(None)
    c.preview_button.on_click(None)
    assert 'Preview failed' not in text(c.summary_column) and 'Preview completed' in text(c.summary_column)
    assert not c.copy_apply_button.visible and c.production_apply_button.disabled
    assert 'REVIEW_REQUIRED' in text(c.technical_details_column)
    assert 'NO_SAFE_CHANGES_TO_PUBLISH' in text(c.technical_details_column)


@pytest.mark.parametrize('kind', ['technical','global','blocked_peers','postflight','recovery','cleanup','test_gate'])
def test_critical_structured_signals_take_precedence_over_noop(kind):
    raw=preview()
    if kind=='technical':raw=preview(technical='Source schema failed')
    if kind=='global':raw['operational_decision']['global_blocker_count']=1
    if kind=='blocked_peers':raw['operational_decision']['local_hold_blocked_safe_changes']=True
    if kind=='postflight':raw['publication_outcome']={'postflight':'FAILED'}
    if kind=='recovery':raw['publication_outcome']={'rollback_recovery':'RECOVERY_REQUIRED'}
    if kind=='cleanup':raw['terminal_summary']={'terminal_cleanup':{'status':'FAILED'}}
    if kind=='test_gate':raw=preview(safe=3,authorized=False)
    view=run_meaning(raw)
    assert view['category']==ACTION_REQUIRED and not view['safe_noop']
    if kind=='technical':assert 'Preview failed' in view['headline']


def test_ready_preview_and_publication_success_meaning():
    ready=run_meaning(preview(safe=5,held=0))
    assert 'ready for Test' in ready['headline'] and ready['action']=='Proceed to Test on copies'
    raw=workflow();raw['operational_decision']=refresh_operational_decision(safe_effective_changes=51,held_items=[],global_blockers=[],
        future_test_authorized=True,test_reason_code='SAFE_CHANGES_TEST_AUTHORIZED',stage='Production update',completed=True)
    assert '51 tickers published' in run_meaning(raw)['meaning']


def test_safe_stopped_and_unknown_stopped_have_different_meaning_without_prose_parsing():
    raw=preview();raw.update(mode='FULL_WORKFLOW',outcome='STOPPED')
    v=run_meaning(raw);assert v['category']==NO_ACTION and 'No immediate action required' in v['action']
    raw['operational_decision']={};raw['message']='No safe changes to publish';raw['stop_reason']='Everything is okay'
    assert run_meaning(raw)['category'] is None


def test_source_counts_are_distinct_and_missing_is_not_recorded():
    scan=source_scan(preview());assert (scan['source_candidates'],scan['effective_changes'],scan['reviews'])==(51,0,2)
    assert 'candidates flagged for comparison' in scan['rows'][0]
    assert 'Relevant Fundamentals changes: 0' in scan['rows'][1]
    assert 'Separate review items: 2' in scan['rows'][2]
    unknown=source_scan({});assert all('not recorded' in row for row in unknown['rows'])
    assert unknown['source_candidates'] is None


def test_landing_and_history_summary_and_accounting_header_are_compact():
    from rawcandle.fundamentals.admin.operational_presentation import workflow_view,normal_summary
    from tests.test_fundamentals_ui_final_polish import with_boundary
    raw=preview();raw.update(mode='FULL_WORKFLOW',outcome='STOPPED',ownership_auto={'status':'COMPLETED','published':1})
    view=workflow_view(raw)
    shown='\n'.join(normal_summary(loaded=True,review_count=2,deep_count=0,safety={'status':'CLEAR'},settings={'full_workflow':True},last_workflow=view))
    assert 'Safe publication within Full Workflow: automatic' in shown
    assert 'Last workflow: No new safe financial changes to publish' in shown
    assert 'STOPPED' not in shown and 'Financial workflow: STOPPED' in '\n'.join(view['rows'])
    class Reader(with_boundary('APPROVED')):
        def history_entries(self,**kwargs):
            return [AdminUIHistoryEntry(run_id='parent',operation_type='REFRESH_FUNDAMENTALS',outcome='STOPPED',status='stopped',mode='FULL_WORKFLOW',completed_at_utc=None,report_available=False)]
        def history_operational_summary(self,*args,**kwargs):return view
    _,c=page_for(Reader(providers=[provider('FDX'),provider('RRC')]))
    assert 'APPROVED' not in text(c.accounting_history_column)
    assert 'APPROVED' in text(c.accounting_history_column,collapsed=True)
    compact=[n.value for n in walk(c.content,collapsed=True) if isinstance(n,ft.Text) and n.value.startswith('Latest Full Workflow:')]
    assert len(compact)==1 and '\n' not in compact[0]


def test_preview_progress_detail_functions_are_unchanged_from_task_start():
    path='dev_tools/fundamentals_admin_page.py'
    baseline=subprocess.check_output(['git','show','1be8ea1155f45ce663a265061e077617b2aae0b5:'+path],text=True)
    current=Path(path).read_text()
    names={'render_progress','progress_callback','on_progress_scroll','apply_capabilities','on_copy_apply','on_production_apply','on_preview'}
    def parts(source):
        tree=ast.parse(source)
        return {n.name:ast.get_source_segment(source,n) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names}
    assert parts(current)==parts(baseline)


@pytest.mark.parametrize('safe,held,available',[(0,2,False),(5,0,True)])
def test_individual_preview_and_existing_test_production_controls(tmp_path,safe,held,available):
    raw=preview(safe=safe,held=held)
    response=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)._finalize(raw,default_message='done')
    class Reader(OperationalService):
        def preview(self,*a,**kwargs):return response
    _,c=page_for(Reader());c.operation_dropdown.value='REFRESH_FUNDAMENTALS';c.operation_dropdown.on_change(None)
    assert c.preview_button.visible and not c.preview_button.disabled
    c.preview_button.on_click(None)
    assert c.copy_apply_button.visible==available
    assert c.production_apply_button.disabled


class HistoryOnly:
    def __init__(self,service):self.service=service;self.cursors=[]
    def capabilities(self):return ()
    def history_cursor(self,**kwargs):
        cursor=self.service.history_cursor(**kwargs);self.cursors.append(cursor);return cursor
    def progress(self,*args,**kwargs):return self.service.progress(*args,**kwargs)
    def history_result_summary(self,*args,**kwargs):return self.service.history_result_summary(*args,**kwargs)
    def cleanup_eligibility(self,*args,**kwargs):return {'eligible':False,'status':'NOT_ELIGIBLE','reason':'fixture'}


def rows(c):
    return [r.controls[5].tooltip.split(';')[0].removeprefix('run_id=') for r in c.history_column.controls if isinstance(r,ft.Row)]


def make_history(tmp_path):
    ids=[f'20261029T12{i:02d}00Z_add_tickers_page{i:02d}' for i in range(25)]
    for run_id in ids:_write_run(tmp_path,run_id)
    for minute in (18,23):
        lane=tmp_path/f'20261029T12{minute:02d}30Z_legacy_evidence';lane.mkdir();(lane/'legacy.json').write_text('{}')
    return sorted(ids,reverse=True)


def test_show_more_sync_is_bounded_ordered_duplicate_free_updates_and_preserves_selection(tmp_path,monkeypatch):
    expected=make_history(tmp_path)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    service=FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False)
    original=service._history_projection;reads=[]
    def tracked(path):reads.append(path);return original(path)
    monkeypatch.setattr(service,'_history_projection',tracked)
    monkeypatch.setattr(service,'history_entries',lambda **kwargs:pytest.fail('Use incremental cursor, not a load-all API'))
    proxy=HistoryOnly(service);page=_Page();c=build_fundamentals_admin_page(page=page,service=proxy)
    assert rows(c)==expected[:8] and len(reads)<len(expected)
    c.history_column.controls[0].controls[7].on_click(None);selected=c.history_detail_field.value
    for count in (16,24,25):
        previous=page.update_count;c.history_show_more_button.on_click(None)
        assert rows(c)==expected[:count] and len(set(rows(c)))==count
        assert page.update_count>previous and c.history_detail_field.value==selected
    assert not c.history_show_more_button.visible
    assert len(reads)==len(set(reads))
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_filter_change_resets_paging_and_filtered_continuation_stays_filtered(tmp_path):
    expected=make_history(tmp_path);proxy=HistoryOnly(FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False))
    c=build_fundamentals_admin_page(page=_Page(),service=proxy);c.history_show_more_button.on_click(None)
    assert rows(c)==expected[:16]
    c.show_technical_history_checkbox.value=True;c.show_technical_history_checkbox.on_change(None)
    assert len(rows(c))==8 and proxy.cursors[-1].include_technical
    all_expected=sorted(expected+[p.name for p in tmp_path.iterdir() if 'legacy_evidence' in p.name],reverse=True)
    assert rows(c)==all_expected[:8]
    c.history_show_more_button.on_click(None);assert rows(c)==all_expected[:16]
    c.show_technical_history_checkbox.value=False;c.show_technical_history_checkbox.on_change(None)
    assert rows(c)==expected[:8] and not proxy.cursors[-1].include_technical


def test_deferred_show_more_uses_existing_cursor_and_reaches_exhaustion(tmp_path,monkeypatch):
    expected=make_history(tmp_path);proxy=HistoryOnly(FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False))
    async def inline(fn):return fn()
    monkeypatch.setattr('asyncio.to_thread',inline)
    async def exercise():
        page=_Page();c=build_fundamentals_admin_page(page=page,service=proxy,defer_initial_load=True)
        c.activate();await c.history_loader._run(c.history_loader.generation)
        assert rows(c)==expected[:8]
        for count in (16,24,25):
            c.history_show_more_button.on_click(None);await c.history_loader._run(c.history_loader.generation)
            assert rows(c)==expected[:count]
        assert not c.history_show_more_button.visible and len(proxy.cursors)==1
    asyncio.run(exercise())


def test_history_rows_keep_technical_results_and_add_structured_urgency(tmp_path):
    for minute,mode,outcome,blockers in ((10,'FULL_WORKFLOW','STOPPED',0),(11,'PREVIEW','REVIEW_REQUIRED',0),(12,'PREVIEW','REVIEW_REQUIRED',1)):
        raw=preview(global_count=blockers);raw.update(mode=mode,outcome=outcome)
        run_id=f'20261029T13{minute:02d}00Z_refresh_fundamentals_fixture'+('_full_workflow' if mode=='FULL_WORKFLOW' else '')
        raw['run_id']=run_id;directory=tmp_path/run_id;directory.mkdir();(directory/'result.json').write_text(json.dumps(raw))
    service=HistoryOnly(FundamentalsAdminUIService(run_root=tmp_path,recover_publication_on_startup=False))
    c=build_fundamentals_admin_page(page=_Page(),service=service)
    critical,local,noop=[r.controls[3].value for r in c.history_column.controls]
    assert critical.startswith('Review required\n') and 'ACTION REQUIRED' in critical
    assert local.startswith('Review required\n') and '2 local reviews' in local and 'safe peer work not blocked' in local
    assert 'ACTION REQUIRED' not in local
    assert noop.startswith('STOPPED\n') and 'No immediate action required' in noop


def test_native_cursor_implementation_has_not_been_replaced_with_a_load_all_scan():
    path='rawcandle/fundamentals/admin/ui_service.py'
    before=subprocess.check_output(['git','show','1be8ea1155f45ce663a265061e077617b2aae0b5:'+path],text=True)
    after=Path(path).read_text()
    def cursor(source):
        node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.ClassDef) and n.name=='AdminHistoryCursor')
        return ast.get_source_segment(source,node)
    assert cursor(after)==cursor(before)


def test_waiting_reviews_are_counted_separately_from_immediate_operator_actions():
    _,c=page_for(OperationalService(providers=[provider('FDX',status='RETRY_REEVALUATION'),provider('RRC',status='RETRY_REEVALUATION')]))
    assert 'Current reviews requiring action: 0' in c.operational_summary_field.value
    assert 'Current reviews waiting on provider/workflow: 2' in c.operational_summary_field.value
    assert 'FDX' in text(c.review_queue_column) and 'RRC' in text(c.review_queue_column)


def test_financial_safe_noop_does_not_relabel_retained_skipped_ownership_result():
    from rawcandle.fundamentals.admin.operational_presentation import workflow_view
    raw=preview();raw.update(mode='FULL_WORKFLOW',outcome='STOPPED',ownership_auto={'status':'SKIPPED_UNSAFE_FINANCIAL_WORKFLOW','published':0},
        source_summary={'held_for_review':2})
    view=workflow_view(raw)
    assert 'No immediate corrective workflow action' in '\n'.join(view['rows'])
    assert view['ownership_status']=='SKIPPED_UNSAFE_FINANCIAL_WORKFLOW' and view['ownership_published']==0
