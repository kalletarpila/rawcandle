"""Shared future reconciliation with real copied ownership lifecycle and guards."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sqlite3
import pytest
from rawcandle.fundamentals.admin import pb_ownership_future as future, pb_ownership_review as review
from rawcandle.fundamentals.admin import pb_ownership_publication as pub
from rawcandle.fundamentals.generations import prepare_generation_from_candidates,activate_generation,resolve_active_generation
from rawcandle.scheduler.config import read_scheduler_config,write_scheduler_config,scheduler_config_from_dict
from tests.test_pb_ownership_auto_continuation import ordinary, factory
from tests.test_fundamentals_pb_new_quarter_review import ASOF
from tests.test_fundamentals_admin_refresh_full_workflow import _stage
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


@pytest.fixture
def project(ordinary,tmp_path):
    f=ordinary;root=tmp_path/'future_project';inputs={}
    for role,key in [('provider','pp'),('canonical','cp'),('analysis','ap')]:
        dest=root/'inputs'/(role+'.db');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f[key],dest);inputs[role]=dest
    gen=prepare_generation_from_candidates(inputs,generation_id='before_future',project_root=root,source='TEST')
    activate_generation(gen['manifest'],project_root=root)
    shutil.copyfile(f['mp'],root/'data/osakedata.db');shutil.copyfile(f['ap'],root/'data/analysis.db')
    w=future.FutureOwnershipWorkflow(project_root=root,run_root=root/'reports/admin_runs',as_of=ASOF)
    w.queue.parent.mkdir(parents=True)
    with closing(sqlite3.connect(f['queue'])) as s,closing(sqlite3.connect(w.queue)) as d:s.backup(d)
    return w


def test_enabled_exact_copy_test_production_cleanup_and_idempotency(project):
    w=project;old=resolve_active_generation(w.root);hashes={r:pub.sha256_file(p) for r,p in old.role_paths().items()}
    result=w.run(enabled=True,directory=w.runs/'first',trigger_source='SCHEDULER')
    assert result['status']=='COMPLETED',result
    assert result['evaluated']==result['auto_continued']==result['published']==1
    assert result['cleanup']['cleanup_outcome']=='COMPLETED'
    assert len(result['cleanup']['files_deleted'])==3
    cases=review.list_cases(w.queue,include_resolved=True);assert cases[0]['status']=='PUBLISHED'
    assert cases[0]['approval']['decision_type']=='AUTO_CONTINUED' and 'operator' not in cases[0]['approval']
    assert {r:pub.sha256_file(p) for r,p in old.role_paths().items()}==hashes
    count=len(cases)
    again=w.run(enabled=True,directory=w.runs/'second')
    assert again['status']=='NO_AUTO_CANDIDATES' and again['evaluated']==0
    assert len(review.list_cases(w.queue,include_resolved=True))==count


def test_disabled_is_old_manual_flow_and_does_not_create_artifacts(project):
    w=project;dest=w.runs/'disabled';before=w.queue.read_bytes()
    assert w.run(enabled=False,directory=dest)['status']=='DISABLED'
    assert not dest.exists() and w.queue.read_bytes()==before
    assert review.list_cases(w.queue)[0]['status']=='OPEN'


def test_copy_only_test_has_exact_decisions_and_no_live_changes(project):
    w=project;before=w._source()[1]
    r=w.run(enabled=True,directory=w.runs/'copy_only',apply=False)
    assert r['status']=='TEST_PASSED'
    assert w._source()[1]==before and review.list_cases(w.queue)[0]['status']=='OPEN'
    receipt=json.loads(Path(r['test_receipt']).read_text())
    preview=json.loads((w.runs/'copy_only/preview.json').read_text())
    assert receipt['source']==preview['source']
    assert receipt['decisions']==[i for i in preview['items'] if i['partition']=='AUTO_CONTINUE']


@pytest.mark.parametrize('mutation',['source','receipt','selection','hold'])
def test_test_binding_fails_closed(project,mutation):
    w=project;plan=w.preview(enabled=True);directory=w.runs/'test'
    w.test(plan,directory);receipt=directory/'test_receipt.json'
    if mutation in ('receipt','selection'):
        value=json.loads(receipt.read_text());value['status']='FAILED' if mutation=='receipt' else 'PASSED';value['selection']=['other'];receipt.write_text(json.dumps(value))
    elif mutation=='source':
        p=resolve_active_generation(w.root).role_paths()['provider']
        with sqlite3.connect(p) as c:c.execute('CREATE TABLE changed (x)')
    elif mutation=='hold':
        with sqlite3.connect(w.queue) as c:c.execute("UPDATE pb_ownership_review SET status='HELD',result_json='{\"note\":\"Hold\"}'")
    with pytest.raises(ValueError):w.production(plan,receipt,trigger_source='SCHEDULER')
    assert all(c['status']!='PUBLISHED' for c in review.list_cases(w.queue,include_resolved=True))


def test_explicit_hold_is_reported_not_released(project):
    w=project
    with sqlite3.connect(w.queue) as c:c.execute("UPDATE pb_ownership_review SET status='HELD',result_json='{\"note\":\"Hold\"}'")
    r=w.run(enabled=True,directory=w.runs/'hold')
    assert r['manual_review']==1 and r['published']==r['auto_continued']==0
    assert review.list_cases(w.queue)[0]['status']=='HELD'


def test_config_flag_strict_boolean_roundtrip_and_backward_compatibility(tmp_path):
    cfg=read_scheduler_config('scheduler_config.json');path=tmp_path/'scheduler.json'
    write_scheduler_config(str(path),replace(cfg,pb_ownership_auto_continuation_enabled=True))
    assert future.configured(path) is True
    raw=json.loads(path.read_text());raw.pop(future.FLAG)
    assert scheduler_config_from_dict(raw).pb_ownership_auto_continuation_enabled is False
    raw[future.FLAG]='true'
    with pytest.raises(ValueError,match='must be a bool'):scheduler_config_from_dict(raw)


@pytest.mark.parametrize('trigger',['MANUAL','SCHEDULER'])
def test_shared_full_workflow_owner_and_scheduler_lock_reentry(project,monkeypatch,trigger):
    w=project
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=w.run)
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:_stage(w.runs,'financial_preview',mode='PREVIEW',outcome='NO_CHANGE'))
    monkeypatch.setattr(service,'_copy_apply_unlocked',lambda *a,**k:pytest.fail('No unnecessary financial Test'))
    with w._lock():
        response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',trigger_source=trigger,
                                     ownership_auto_enabled=True,scheduler_managed_locks=trigger=='SCHEDULER')
    data=json.loads((Path(response.artifact_dir)/'workflow_result.json').read_text())
    assert data['outcome']=='COMPLETED' and data['ownership_production_completed']
    assert data['ownership_auto']['published']==1 and data['ownership_auto']['enabled'] is True
    assert 'P/B ownership auto-continuation' in (Path(response.artifact_dir)/'workflow_report.md').read_text()


def test_financial_failure_never_enters_ownership_segment(project,monkeypatch):
    w=project;calls=[]
    service=FundamentalsAdminUIService(run_root=w.runs,recover_publication_on_startup=False,ownership_auto_runner=lambda **k:calls.append(k))
    monkeypatch.setattr(service,'_preview_unlocked',lambda *a,**k:_stage(w.runs,'failed_preview',mode='PREVIEW',outcome='FAILED'))
    response=service.full_workflow(operation_type='REFRESH_FUNDAMENTALS',raw_inputs='',ownership_auto_enabled=True)
    assert not calls and response.outcome in ('FAILED','STOPPED')


def test_scheduler_summary_exposes_concise_auto_counts():
    from types import SimpleNamespace
    from rawcandle.fundamentals.admin.refresh_scheduler import _full_workflow_summary
    own=dict(future.summary(True,status='COMPLETED'),evaluated=3,published=1,auto_continued=1,manual_review=1,deep_review=1,secret_evidence='not in summary')
    value=_full_workflow_summary(response=SimpleNamespace(outcome='COMPLETED',status='COMPLETED',run_id='run',message='ok'),
        payload={'outcome':'COMPLETED','ownership_production_completed':True,'ownership_auto':own},run_root=Path('/tmp'))
    assert value['scheduler_summary_result']=='COMPLETED' and value['pb_ownership_auto']['enabled']
    assert value['pb_ownership_auto']['deep_review']==1 and 'secret_evidence' not in value['pb_ownership_auto']
