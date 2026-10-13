"""Exact scheduler stage references, visible-row paging and stored provenance."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page, admin_report_download_url
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_run_history_continuations import _service, _row_ids, _drain
from tests.test_fundamentals_admin_ui import _Page


def record(root,run_id,mode,trigger='MANUAL',**extra):
    d=root/run_id;d.mkdir(parents=True)
    value=dict(run_id=run_id,operation_type='REFRESH_FUNDAMENTALS',mode=mode,trigger_source=trigger,
        outcome='COMPLETED',completed_at_utc='2026-10-13T12:03:00Z',summary_counts={'effective_changed_known':2},**extra)
    (d/'result.json').write_text(json.dumps(value))
    (d/'operation_report.md').write_text('# '+mode)
    if mode=='FULL_WORKFLOW':(d/'workflow_report.md').write_text('# workflow')
    return d


def workflow(root,hour=12,trigger='SCHEDULER'):
    prefix=f'20261013T{hour:02d}'
    children=[]
    for minute,(stage,mode) in enumerate([('Preview','PREVIEW'),('Test on copies','COPY_ONLY_APPLY'),('Production update','PRODUCTION_APPLY')],1):
        run=f'{prefix}{minute:02d}00Z_refresh_fundamentals_child{minute}'
        record(root,run,mode,trigger if minute!=2 else 'MANUAL');children.append((run,stage))
    parent=f'{prefix}0000Z_refresh_fundamentals_full_workflow_parent'
    record(root,parent,'FULL_WORKFLOW',trigger,stages=[dict(stage=s,run_id=r) for r,s in children],terminal_summary={'changed_ticker_count':2})
    return parent,[r for r,s in children]


def test_default_parent_and_technical_exact_children_provenance_and_count(tmp_path):
    parent,children=workflow(tmp_path);service=_service(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert [r.run_id for r in service.history_entries()]==[parent]
    rows=service.history_entries(include_technical=True)
    assert {r.run_id for r in rows}=={parent,*children}
    assert all(r.trigger_source=='SCHEDULER' for r in rows)
    child_rows=[r for r in rows if r.run_id in children]
    assert all(r.workflow_parent_run_id==parent for r in child_rows)
    assert [r.run_id for r in child_rows if r.provenance_inherited]==[children[1]]
    summary=next(r for r in rows if r.run_id==parent)
    assert summary.primary_count==2 and summary.count_label=='2 changed tickers'
    assert summary.completed_at_utc=='2026-10-13T12:03:00Z'
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('mode,trigger',[('PREVIEW','MANUAL'),('COPY_ONLY_APPLY','MANUAL'),('PRODUCTION_APPLY','MANUAL'),('PREVIEW','SCHEDULER'),('PRODUCTION_APPLY','SCHEDULER')])
def test_standalone_and_nearby_runs_are_never_suppressed(tmp_path,mode,trigger):
    parent,children=workflow(tmp_path)
    standalone='20261013T120230Z_refresh_fundamentals_standalone'
    record(tmp_path,standalone,mode,trigger)
    assert {r.run_id for r in _service(tmp_path).history_entries()}=={parent,standalone}


@pytest.mark.parametrize('contradiction',['missing_parent','manual_parent','wrong_mode','wrong_operation','wrong_run_id','ambiguous','corrupt_parent'])
def test_suppression_requires_one_valid_exact_parent_reference(tmp_path,contradiction):
    parent,children=workflow(tmp_path);p=tmp_path/parent/'result.json';v=json.loads(p.read_text())
    target=tmp_path/children[1]/'result.json';child=json.loads(target.read_text())
    if contradiction=='missing_parent':v['stages']=[s for s in v['stages'] if s['run_id']!=children[1]]
    elif contradiction=='manual_parent':v['trigger_source']='MANUAL'
    elif contradiction=='wrong_mode':child['mode']='PREVIEW'
    elif contradiction=='wrong_operation':child['operation_type']='ADD_TICKERS'
    elif contradiction=='wrong_run_id':child['run_id']='other'
    elif contradiction=='ambiguous':
        other=parent.replace('parent','other');record(tmp_path,other,'FULL_WORKFLOW','SCHEDULER',stages=v['stages'])
    elif contradiction=='corrupt_parent':v['stages']=[{'stage':[],'run_id':children[1]}]
    p.write_text(json.dumps(v));target.write_text(json.dumps(child))
    assert children[1] in {r.run_id for r in _service(tmp_path).history_entries()}


def test_grouped_cursor_fills_visible_8_16_24_and_keeps_newest_first(tmp_path):
    parents=[]
    for hour in range(24):parents.append(workflow(tmp_path,hour)[0])
    class Counting(FundamentalsAdminUIService):
        def _history_projection(self,path):
            reads[path]=reads.get(path,0)+1
            return super()._history_projection(path)
    reads={};service=Counting(run_root=tmp_path,recover_publication_on_startup=False)
    cursor=service.history_cursor()
    for limit in (8,16,24):
        assert [r.run_id for r in cursor.fill(limit)]==list(reversed(parents))[:limit]
    assert max(reads.values())==1
    assert len(cursor.fill(24))==24  # Children never consume visible capacity.


@pytest.mark.parametrize('deferred',[False,True])
def test_ui_refresh_toggle_and_workflow_child_actions(tmp_path,deferred,monkeypatch):
    if deferred:
        async def inline(function):return function()
        monkeypatch.setattr('dev_tools.deferred_ui.asyncio.to_thread',inline)
    parent,children=workflow(tmp_path)
    legacy=tmp_path/'legacy_record';legacy.mkdir();(legacy/'old.md').write_text('old')
    page=_Page();controls=build_fundamentals_admin_page(page=page,service=_service(tmp_path),defer_initial_load=deferred)
    if deferred:controls.activate();_drain(page)
    assert _row_ids(controls)==[parent]
    row=controls.history_column.controls[0]
    row.controls[7].on_click(None)
    assert parent in controls.history_detail_field.value
    row.controls[8].on_click(None)
    assert page.launched_urls[-1]==admin_report_download_url(parent,'workflow_report.md')
    assert len(row.controls)==9  # No child Production cleanup action attached to parent.
    controls.show_technical_history_checkbox.value=True;controls.show_technical_history_checkbox.on_change(None);_drain(page)
    assert set(_row_ids(controls))=={parent,*children,'legacy_record'}
    for row,run in zip(controls.history_column.controls,_row_ids(controls)):
        if run in children:
            assert '[Scheduler]' in row.controls[1].value
            assert 'workflow_parent='+parent in row.controls[5].tooltip
            row.controls[7].on_click(None);assert run in controls.history_detail_field.value
            row.controls[8].on_click(None);assert page.launched_urls[-1]==admin_report_download_url(run)
    controls.show_technical_history_checkbox.value=False;controls.show_technical_history_checkbox.on_change(None);_drain(page)
    later,_=workflow(tmp_path,13)
    assert _row_ids(controls)==[parent]  # Existing cursor snapshot is intentional.
    controls.history_refresh_button.on_click(None);_drain(page)
    assert _row_ids(controls)==[later,parent]


def test_full_workflow_forwards_scheduler_origin_to_copy_test(tmp_path,monkeypatch):
    from rawcandle.fundamentals.admin import full_workflow
    received=[]
    def copy_backend(**kwargs):
        received.append(kwargs['trigger_source'])
        return dict(mode='COPY_ONLY_APPLY',outcome='COMPLETED')
    def orchestrator(**kwargs):
        kwargs['test_stage'](SimpleNamespace(preview_payload_path='preview.json',preview_fingerprint='fp'),lambda _e:None)
        return {}
    monkeypatch.setattr(full_workflow,'run_refresh_full_workflow',orchestrator)
    service=FundamentalsAdminUIService(run_root=tmp_path,refresh_apply=copy_backend,recover_publication_on_startup=False)
    service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',trigger_source='SCHEDULER')
    service.copy_apply('REFRESH_FUNDAMENTALS',preview_payload_path='manual.json',preview_fingerprint='fp')
    assert received==['SCHEDULER','MANUAL']


@pytest.mark.parametrize('trigger',['SCHEDULER','MANUAL'])
def test_copy_test_persists_supplied_origin_even_on_failure(tmp_path,monkeypatch,trigger):
    from rawcandle.fundamentals.admin import refresh_copy_runtime as runtime
    monkeypatch.setattr(runtime,'_production_file_state',lambda _paths:{})
    monkeypatch.setattr(runtime,'SharadarClient',lambda:object())
    def fail(*args):raise RuntimeError('synthetic binding failure')
    monkeypatch.setattr(runtime,'_load_bound_preview',fail)
    result=runtime.run_apply(preview_payload_path=tmp_path/'missing.json',preview_fingerprint='f'*64,
        run_root=tmp_path/'runs',temp_root=tmp_path/'temp',confirm_apply=True,trigger_source=trigger)
    assert result['trigger_source']==trigger and result['outcome']=='FAILED'
    directory=Path(result['artifact_dir'])
    assert json.loads((directory/'request.json').read_text())['trigger_source']==trigger
    assert json.loads((directory/'result.json').read_text())['trigger_source']==trigger


@pytest.mark.parametrize('outcome',['FAILED','STOPPED','NO_CHANGE'])
def test_parent_final_result_remains_authoritative(tmp_path,outcome):
    parent,_=workflow(tmp_path);p=tmp_path/parent/'result.json';value=json.loads(p.read_text())
    value['outcome']=outcome;p.write_text(json.dumps(value))
    rows=_service(tmp_path).history_entries()
    assert len(rows)==1 and rows[0].run_id==parent and rows[0].outcome==outcome


def test_hidden_parent_does_not_hide_unrepresented_stage_records(tmp_path):
    parent,children=workflow(tmp_path);service=_service(tmp_path)
    # Existing hide-only history semantics must not turn into cascading deletion.
    service.history.hide_run(parent)
    assert {r.run_id for r in service.history_entries()}==set(children)
    assert (tmp_path/parent/'result.json').exists()
