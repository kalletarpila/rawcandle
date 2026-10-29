"""Operator visibility from structured ownership results, with no live operations."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from rawcandle.fundamentals.admin import pb_ownership_presentation as display
from rawcandle.fundamentals.admin.pb_ownership_publication import exact_hash
from rawcandle.fundamentals.admin.full_workflow import render_workflow_report, workflow_ui_summary
from rawcandle.fundamentals.admin.operation_report import build_operation_summary
from rawcandle.fundamentals.admin.refresh_scheduler import _full_workflow_summary
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService,AdminOperationCapability
from tests.test_pb_ownership_safe_no_changes import safe_result
from tests.test_pb_ownership_future import project,ordinary,factory
from tests.test_fundamentals_admin_ui import _Page
from dev_tools.fundamentals_admin_page import build_fundamentals_admin_page


@pytest.fixture
def result(tmp_path):
    value=safe_result(tmp_path)
    value['ownership_auto']=dict(enabled=True,policy_version='PB_ORDINARY_AUTO_CONTINUATION_V1',
        financial_precondition='SAFE_FINANCIAL_NO_OP',financial_outcome='STOPPED',financial_reason_code='NO_SAFE_CHANGES_TO_PUBLISH',
        status='COMPLETED',evaluated=1,auto_continued=1,manual_review=0,deep_review=0,published=1,failed_stale=0,
        preview_path=str(tmp_path/'ownership_preview.json'),test_receipt=str(tmp_path/'test_receipt.json'),cleanup_status='COMPLETED',
        publication=dict(outcome='COMPLETED',generation_id='pb_ownership_example123',publication_run_id='pb_ownership_example123',
            published_cases=['case1'],artifact_sha256='not-visible-in-primary-summary',postflight='PASSED',recovery='NOT_REQUIRED',
            published_tickers=['AAA'],decision_types=['AUTO_CONTINUED'],queue_state='PUBLISHED'),
        cleanup=dict(status='COMPLETED',cleanup_outcome='COMPLETED',files_deleted=['provider.db','canonical.db','analysis.db'],bytes_freed=2630086656))
    value['ownership_production_completed']=True
    return value


def test_all_acceptance_fields_in_report_current_ui_and_history_without_mutation(result,monkeypatch):
    before=deepcopy(result)
    monkeypatch.setattr(display,'_legacy_details',lambda *a:pytest.fail('New results need no artifact reads'))
    texts=[render_workflow_report(result),'\n'.join(workflow_ui_summary(result)),'\n'.join(build_operation_summary(result))]
    for text in texts:
        for expected in ('Published: AAA — AUTO_CONTINUED','PB_ORDINARY_AUTO_CONTINUATION_V1','pb_ownership_example123',
                         'Ownership status: COMPLETED','Ownership publication: COMPLETED / PUBLISHED','Postflight: PASSED',
                         'Recovery: NOT_REQUIRED','Cleanup: COMPLETED — 3 backups / 2.63 GB (2,630,086,656 bytes freed)',
                         'Evaluated 1 | Automatic 1 | Manual 0 | Deep 0 | Published 1 | Failed/stale 0',
                         'SAFE_FINANCIAL_NO_OP','financial workflow: STOPPED','FDX','RRC'):
            assert expected in text
        assert result['ownership_auto']['publication']['artifact_sha256'] not in text
    report=texts[0]
    assert result['ownership_auto']['preview_path'] in report and result['ownership_auto']['test_receipt'] in report
    assert 'Overall workflow result: STOPPED' in report and 'Production completed: No' in report
    assert result==before


@pytest.mark.parametrize('financial',['COMPLETED','NO_CHANGE'])
def test_existing_safe_financial_results_display_independently(result,financial):
    result.update(outcome='COMPLETED',production_completed=financial=='COMPLETED')
    result['ownership_auto'].update(financial_outcome=financial,financial_precondition='SAFE_FINANCIAL_RESULT')
    text='\n'.join(workflow_ui_summary(result))
    assert 'financial workflow: '+financial in text and 'Ownership status: COMPLETED' in text


@pytest.mark.parametrize('status',['NO_AUTO_CANDIDATES','DISABLED','FAILED_OR_STALE','TEST_PASSED','SKIPPED_UNSAFE_FINANCIAL_WORKFLOW'])
def test_no_publication_has_no_invented_identity_or_cleanup(result,monkeypatch,status):
    own=result['ownership_auto']
    for key in ('publication','cleanup','cleanup_status'):own.pop(key)
    own.update(status=status,published=0,auto_continued=0,enabled=status!='DISABLED')
    if status=='FAILED_OR_STALE':own.update(failed_stale=1,reason='PB_FUTURE_TEST_SOURCE_DRIFT')
    monkeypatch.setattr(display,'_legacy_details',lambda *a:pytest.fail('No-publication view must not look up publication artifacts'))
    text='\n'.join(display.ownership_summary_rows(result))
    assert 'Ownership status: '+status in text
    assert all(label not in text for label in ('Ownership generation:','Postflight:','Recovery:','Cleanup:'))
    if status=='NO_AUTO_CANDIDATES':assert 'no publication in this run' in text
    if status=='FAILED_OR_STALE':assert 'Failed/stale 1' in text and 'PB_FUTURE_TEST_SOURCE_DRIFT' in text
    if status=='DISABLED':assert 'Policy: disabled' in text


def test_manual_deep_only_partition_is_readable(result):
    own=result['ownership_auto'];own.pop('publication');own.pop('cleanup');own.pop('cleanup_status')
    own.update(status='NO_AUTO_CANDIDATES',evaluated=3,auto_continued=0,published=0,manual_review=2,deep_review=1)
    text='\n'.join(display.ownership_summary_rows(result))
    assert 'Manual/deep reviews remain held' in text
    assert 'Evaluated 3 | Automatic 0 | Manual 2 | Deep 1 | Published 0 | Failed/stale 0' in text


def test_successful_publication_and_cleanup_stop_stay_separate(result):
    result['ownership_auto'].update(cleanup={'status':'STOPPED','reason':'Backups still required'},cleanup_status='STOPPED')
    text=render_workflow_report(result)
    assert 'Ownership publication: COMPLETED / PUBLISHED' in text and 'Postflight: PASSED' in text
    assert 'Recovery: NOT_REQUIRED' in text and 'Cleanup: STOPPED' in text and 'Backups still required' in text
    assert 'Cleanup: COMPLETED' not in text and '0 backups' not in text


def test_internal_fingerprints_stay_in_artifacts_even_in_failure_reasons(result):
    sha='a1'*32
    result['ownership_auto']['reason']='Source mismatch '+sha
    result['ownership_auto'].update(cleanup={'status':'STOPPED','reason':'Backup mismatch '+sha},cleanup_status='STOPPED')
    text='\n'.join(display.ownership_summary_rows(result))
    assert sha not in text and 'Cleanup: STOPPED' in text and '[see detailed artifacts]' in text
    assert result['ownership_auto']['reason'].endswith(sha)


def test_failed_publication_shows_explicit_failure_without_final_generation(result):
    own=result['ownership_auto'];own.update(status='FAILED_OR_STALE',published=0,failed_stale=1)
    own['publication'].update(outcome='FAILED',postflight='FAILED',recovery='RECOVERY_REQUIRED')
    text='\n'.join(display.ownership_summary_rows(result))
    assert 'Ownership publication: FAILED' in text and 'Postflight: FAILED' in text and 'Recovery: RECOVERY_REQUIRED' in text
    assert 'Ownership generation:' not in text


def test_multiple_published_tickers_are_generic(result):
    result['ownership_auto']['publication']['published_tickers']=['AAA','BBB']
    result['ownership_auto'].update(published=2,auto_continued=2,evaluated=2)
    assert 'Published: AAA, BBB — AUTO_CONTINUED' in '\n'.join(display.ownership_summary_rows(result))


def legacy_artifacts(result):
    own=result['ownership_auto'];pub=own['publication']
    for key in ('published_tickers','decision_types','queue_state','recovery'):pub.pop(key)
    lane=Path(result['artifact_dir']).parent/'pb_ownership_publications'/pub['publication_run_id'];lane.mkdir(parents=True)
    preview=dict(preview_id=pub['publication_run_id'],selection=pub['published_cases'],artifact_sha256=pub['artifact_sha256'],
        created_at_utc='2026-10-29T12:00:00Z',artifact_dir=str(lane),
        selected=[dict(case={'case_id':'case1','ticker':'AAA'},approval={'decision_type':'AUTO_CONTINUED'},record={'approval_mode':'AUTO_CONTINUED'})])
    preview['preview_hash']=exact_hash(preview)
    journal=dict(production_run_id=pub['publication_run_id'],new_generation_id=pub['generation_id'],state='COMPLETED',postflight_state='PASSED',
        rollback_recovery_state='NOT_REQUIRED',created_at_utc='2026-10-29T12:01:00Z',
        scope_evidence={'selected':[{'case_id':'case1'}],'artifact_sha256':pub['artifact_sha256']},refresh_set_fingerprint=preview['preview_hash'])
    own['cleanup']['ownership_receipt_hash']=exact_hash(journal)
    (lane/'preview.json').write_text(json.dumps(preview));(lane/'completed_journal.json').write_text(json.dumps(journal))
    return lane


def test_legacy_live_shape_uses_bound_json_only_without_rewriting_result(result,monkeypatch):
    lane=legacy_artifacts(result);before=deepcopy(result);files={p:p.read_bytes() for p in lane.iterdir()}
    monkeypatch.setattr('sqlite3.connect',lambda *a,**k:pytest.fail('Display must never read databases'))
    text='\n'.join(build_operation_summary(result))
    assert 'Published: AAA — AUTO_CONTINUED' in text and 'Recovery: NOT_REQUIRED' in text
    assert 'Cleanup: COMPLETED — 3 backups' in text and result==before
    assert {p:p.read_bytes() for p in lane.iterdir()}==files


@pytest.mark.parametrize('failure',['missing','other_generation','other_selection','changed_preview','changed_journal'])
def test_legacy_missing_or_mismatched_receipt_never_invents_details(result,failure):
    lane=legacy_artifacts(result);path=lane/'completed_journal.json'
    if failure=='missing':path.unlink()
    elif failure=='changed_preview':
        p=lane/'preview.json';value=json.loads(p.read_text());value['selected'][0]['case']['ticker']='WRONG';p.write_text(json.dumps(value))
    else:
        value=json.loads(path.read_text())
        if failure=='other_generation':value['new_generation_id']='pb_ownership_other'
        elif failure=='other_selection':value['scope_evidence']['selected']=[{'case_id':'other'}]
        else:value['rollback_recovery_state']='REQUIRED'
        path.write_text(json.dumps(value))
    text='\n'.join(display.ownership_summary_rows(result))
    assert 'Published: AAA' not in text and 'Published: WRONG' not in text
    assert 'Recovery: NOT_REQUIRED' not in text and 'Some publication details are unavailable' in text


def test_scheduler_keeps_only_existing_concise_ownership_fields(result):
    response=SimpleNamespace(outcome='STOPPED',status='FAILED',run_id=result['run_id'],message='Financial no-op')
    summary=_full_workflow_summary(response=response,payload=result,run_root=Path(result['artifact_dir']).parent)['pb_ownership_auto']
    text=json.dumps(summary)
    assert 'AAA' not in text and 'example123' not in text and 'publication' not in summary and len(text)<800
    assert summary['published']==1 and summary['cleanup_status']=='COMPLETED'


def test_real_ui_summary_controls_display_the_service_rows(result):
    root=Path(result['artifact_dir']).parent
    response=FundamentalsAdminUIService(run_root=root,recover_publication_on_startup=False)._finalize(result,default_message='Completed')
    class ReplayService:
        def capabilities(self):return (AdminOperationCapability('REFRESH_FUNDAMENTALS',True,True,False),)
        def history_entries(self,**kwargs):return []
        def full_workflow(self,**kwargs):return response
    controls=build_fundamentals_admin_page(page=_Page(),service=ReplayService())
    controls.operation_dropdown.value='REFRESH_FUNDAMENTALS';controls.operation_dropdown.on_change(None)
    controls.full_workflow_button.on_click(None)
    text='\n'.join(c.value for c in controls.summary_column.controls)
    assert 'Published: AAA — AUTO_CONTINUED' in text and 'Recovery: NOT_REQUIRED' in text
    assert 'Cleanup: COMPLETED — 3 backups' in text and result['outcome']=='STOPPED'


def test_native_success_returns_authoritative_display_metadata(project):
    outcome=project.run(enabled=True,directory=project.runs/'display_metadata',trigger_source='MANUAL')
    assert outcome['status']=='COMPLETED',outcome
    pub=outcome['publication']
    assert pub['published_tickers']==['AAA'] and pub['decision_types']==['AUTO_CONTINUED']
    assert pub['queue_state']=='PUBLISHED' and pub['recovery']=='NOT_REQUIRED'
