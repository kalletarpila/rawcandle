"""Workflow cleanup selection; real deletion is exercised only in tiny tmp fixtures."""
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page,admin_report_download_url
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.admin import run_acceptance_cleanup as backend
from tests.test_run_history_scheduler_grouping import workflow,record
from tests.test_fundamentals_run_history_continuations import _row_ids
from tests.test_fundamentals_admin_ui import _Page


def service(root,state=None):
    inspected=[];applied=[];cleaned=set()
    state=state if state is not None else dict(eligible=True,status='ELIGIBLE',backup_count=3,bytes_freed=30,backup_files=['provider.db','canonical.db','analysis.db'])
    def inspect(run):
        inspected.append(run)
        return dict(state,run_id=run) if run not in cleaned else dict(eligible=False,status='ALREADY_CLEANED',run_id=run,backup_count=3,bytes_freed=30,reason='Accepted / backups cleaned')
    def apply(run):
        applied.append(run);already=run in cleaned;cleaned.add(run)
        return dict(status='ALREADY_CLEANED' if already else 'COMPLETED',files_deleted=['a','b','c'],bytes_freed=30)
    s=FundamentalsAdminUIService(run_root=root,cleanup_inspect=inspect,cleanup_apply=apply,recover_publication_on_startup=False)
    return s,inspected,applied,cleaned


def test_parent_action_details_authorization_and_technical_view_share_child(tmp_path):
    parent,children=workflow(tmp_path);child=children[2];s,inspected,applied,cleaned=service(tmp_path)
    page=_Page();c=build_fundamentals_admin_page(page=page,service=s)
    assert _row_ids(c)==[parent] and inspected==[child]
    row=c.history_column.controls[0];assert row.controls[-1].tooltip=='Accept run and cleanup backups'
    row.controls[7].on_click(None)
    assert parent in c.history_detail_field.value and 'Full workflow' in c.history_detail_field.value
    assert child in c.cleanup_status_field.value and 'Cleanup target: Production child' in c.cleanup_status_field.value
    row.controls[8].on_click(None);assert page.launched_urls[-1]==admin_report_download_url(parent,'workflow_report.md')
    row.controls[-1].on_click(None)
    assert parent in page.dialog.content.value and child in page.dialog.content.value
    assert 'provider.db' in page.dialog.content.value and 'Exact bytes: 30' in page.dialog.content.value
    page.dialog.actions[1].on_click(None)
    assert applied==[child] and set(inspected)=={child}
    assert c.history_column.controls[0].controls[-1].tooltip=='Backups cleaned'
    assert child in c.cleanup_status_field.value and 'ALREADY_CLEANED' in c.cleanup_status_field.value
    assert not (tmp_path/parent/'backup_cleanup.json').exists()
    c.show_technical_history_checkbox.value=True;c.show_technical_history_checkbox.on_change(None)
    rows=dict(zip(_row_ids(c),c.history_column.controls))
    assert rows[parent].controls[-1].tooltip==rows[child].controls[-1].tooltip=='Backups cleaned'
    rows[child].controls[8].on_click(None);assert page.launched_urls[-1]==admin_report_download_url(child)
    assert parent not in inspected+applied


@pytest.mark.parametrize('status',['ALREADY_CLEANED','NOT_ELIGIBLE'])
def test_child_nonactive_states_drive_parent_controls(tmp_path,status):
    parent,children=workflow(tmp_path)
    s,*_=service(tmp_path,dict(eligible=False,status=status,backup_count=0,bytes_freed=0,reason='child state'))
    page=_Page();c=build_fundamentals_admin_page(page=page,service=s);row=c.history_column.controls[0]
    if status=='ALREADY_CLEANED':assert row.controls[-1].tooltip=='Backups cleaned'
    else:assert len(row.controls)==9
    row.controls[7].on_click(None)
    assert status in c.cleanup_status_field.value and children[2] in c.cleanup_status_field.value
    assert not c.cleanup_button.visible


@pytest.mark.parametrize('bad',['no_stage','duplicate','missing_child','mode','operation','run_id','failed','stage_failed','traversal','symlink','parent_operation'])
def test_invalid_workflow_child_never_reaches_inspector_or_cleanup(tmp_path,bad):
    parent,children=workflow(tmp_path);p=tmp_path/parent/'result.json';v=json.loads(p.read_text())
    target=tmp_path/children[2]/'result.json';child=json.loads(target.read_text())
    if bad=='no_stage':v['stages']=v['stages'][:2]
    elif bad=='duplicate':v['stages'].append(v['stages'][-1])
    elif bad=='missing_child':target.unlink()
    elif bad=='mode':child['mode']='COPY_ONLY_APPLY'
    elif bad=='operation':child['operation_type']='ADD_TICKERS'
    elif bad=='run_id':child['run_id']='wrong'
    elif bad=='failed':child['outcome']='FAILED'
    elif bad=='stage_failed':v['stages'][-1]['status']='FAILED'
    elif bad=='traversal':v['stages'][-1]['run_id']='../outside'
    elif bad=='symlink':target.rename(target.with_name('saved.json'));target.symlink_to(target.with_name('saved.json'))
    elif bad=='parent_operation':v['operation_type']='ADD_TICKERS'
    p.write_text(json.dumps(v))
    if bad not in {'missing_child','symlink'}:target.write_text(json.dumps(child))
    s,inspected,applied,_=service(tmp_path)
    assert not s.cleanup_eligibility(parent)['eligible']
    with pytest.raises(ValueError):s.accept_run_and_cleanup_backups(parent)
    assert inspected==applied==[]


@pytest.mark.parametrize('change',['reference','eligibility','inventory','receipt'])
def test_dialog_authorization_rejects_changed_child_or_evidence(tmp_path,change):
    parent,children=workflow(tmp_path);s,inspected,applied,_=service(tmp_path)
    page=_Page();c=build_fundamentals_admin_page(page=page,service=s)
    c.history_column.controls[0].controls[-1].on_click(None)
    if change=='reference':
        other='20261013T130300Z_refresh_fundamentals_other';record(tmp_path,other,'PRODUCTION_APPLY')
        p=tmp_path/parent/'result.json';v=json.loads(p.read_text());v['stages'][-1]['run_id']=other;p.write_text(json.dumps(v))
    else:
        original=s._cleanup_inspect
        def changed(run):
            value=dict(original(run))
            if change=='eligibility':value.update(eligible=False,status='NOT_ELIGIBLE')
            elif change=='inventory':value['bytes_freed']=31
            else:value['terminal_receipt']={'receipt_fingerprint':'changed'}
            return value
        s._cleanup_inspect=changed
    page.dialog.actions[1].on_click(None)
    assert applied==[] and 'stopped' in c.cleanup_status_field.value


@pytest.mark.parametrize('historical',[False,True])
def test_child_inspector_evidence_is_preserved_opaque_and_child_owned(tmp_path,historical):
    parent,children=workflow(tmp_path)
    state=dict(eligible=True,status='ELIGIBLE',backup_count=3,bytes_freed=30,journal_state='COMPLETED')
    if historical:state['terminal_receipt']={'receipt_fingerprint':'f'*64,'file_sha256':'a'*64,'path':'exact-child-receipt'}
    s,inspected,applied,_=service(tmp_path,state)
    result=s.cleanup_eligibility(parent)
    assert all(result[k]==v for k,v in state.items()) and result['cleanup_target_run_id']==children[2]
    s.accept_run_and_cleanup_backups(children[2],workflow_parent_run_id=parent,expected_eligibility=result)
    assert applied==[children[2]]
    s.accept_run_and_cleanup_backups(parent)
    assert applied==[children[2],children[2]]  # Existing child idempotent path, no parent audit.


def test_refresh_updates_parent_after_independent_child_cleanup_and_hide_stays_parent_specific(tmp_path):
    parent,children=workflow(tmp_path);s,_,applied,cleaned=service(tmp_path)
    page=_Page();c=build_fundamentals_admin_page(page=page,service=s)
    cleaned.add(children[2]);c.history_refresh_button.on_click(None)
    assert c.history_column.controls[0].controls[-1].tooltip=='Backups cleaned'
    c.history_column.controls[0].controls[6].on_click(None);page.dialog.actions[1].on_click(None)
    assert parent not in _row_ids(c) and (tmp_path/parent/'result.json').exists()
    assert (tmp_path/children[2]/'result.json').exists() and applied==[]


def test_only_visible_workflow_children_are_inspected_and_paging_stays_full(tmp_path):
    parents=[]
    for hour in range(24):parents.append(workflow(tmp_path,hour)[0])
    s,inspected,_,_=service(tmp_path);c=build_fundamentals_admin_page(page=_Page(),service=s)
    for count in (8,16,24):
        assert len(_row_ids(c))==count and len(set(inspected))==count
        assert _row_ids(c)==list(reversed(parents))[:count]
        if count<24:c.history_show_more_button.on_click(None)
    assert len(inspected)==24


def test_synthetic_delegation_uses_existing_deletion_and_child_only_audit(tmp_path):
    from tests.test_fundamentals_admin_run_acceptance_cleanup import _fixture,RUN_ID
    f=_fixture(tmp_path);root=f['run_root'];child=RUN_ID
    p=root/child/'result.json';v=json.loads(p.read_text());v['operation_type']='REFRESH_FUNDAMENTALS';p.write_text(json.dumps(v))
    parent='20261013T120000Z_refresh_fundamentals_full_workflow_parent'
    record(root,parent,'FULL_WORKFLOW','SCHEDULER',stages=[dict(stage='Production update',run_id=child)])
    def inspect(run):return backend.inspect_cleanup_eligibility(run,run_root=root,backup_root=f['backup_root'],journal_path=f['journal_path'],live_paths=f['live_paths'])
    def apply(run):return backend.accept_run_and_cleanup_backups(run,run_root=root,backup_root=f['backup_root'],journal_path=f['journal_path'],live_paths=f['live_paths'],lock_factory=nullcontext)
    s=FundamentalsAdminUIService(run_root=root,cleanup_inspect=inspect,cleanup_apply=apply,recover_publication_on_startup=False)
    parent_before=(root/parent/'result.json').read_bytes();state=s.cleanup_eligibility(parent)
    assert state['status']=='ELIGIBLE'
    result=s.accept_run_and_cleanup_backups(child,workflow_parent_run_id=parent,expected_eligibility=state)
    assert result['cleanup_outcome']=='COMPLETED' and len(result['files_deleted'])==3
    assert (root/child/'backup_cleanup.json').exists() and not (root/parent/'backup_cleanup.json').exists()
    assert (root/parent/'result.json').read_bytes()==parent_before
    assert s.cleanup_eligibility(parent)['status']=='ALREADY_CLEANED'
    assert s.accept_run_and_cleanup_backups(parent)['status']=='ALREADY_CLEANED'


def test_technical_child_cleanup_updates_selected_parent_details(tmp_path):
    parent,children=workflow(tmp_path);s,_,applied,_=service(tmp_path)
    page=_Page();c=build_fundamentals_admin_page(page=page,service=s)
    c.history_column.controls[0].controls[7].on_click(None)
    c.show_technical_history_checkbox.value=True;c.show_technical_history_checkbox.on_change(None)
    rows=dict(zip(_row_ids(c),c.history_column.controls))
    rows[children[2]].controls[-1].on_click(None);page.dialog.actions[1].on_click(None)
    assert applied==[children[2]]
    assert children[2] in c.cleanup_status_field.value and 'ALREADY_CLEANED' in c.cleanup_status_field.value
    assert parent in c.history_detail_field.value
