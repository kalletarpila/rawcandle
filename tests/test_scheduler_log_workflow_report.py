"""Scheduler report listing and actual inline HTTP response, with temporary roots."""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from dev_tools import stock_update_scheduler_ui as ui
from rawcandle.fundamentals.admin.operation_report import resolve_operation_report_download


@pytest.fixture
def report(tmp_path,monkeypatch):
    root=tmp_path/'admin_runs';run='20261013T041843Z_refresh_fundamentals_full_workflow_test'
    directory=root/run;directory.mkdir(parents=True)
    path=directory/'workflow_report.md';path.write_text('# Workflow\n\n<script>alert("text only")</script>\n')
    result=dict(run_id=run,mode='FULL_WORKFLOW',operation_type='REFRESH_FUNDAMENTALS',trigger_source='SCHEDULER',
                started_at_utc='2026-10-13T04:18:43Z',completed_at_utc='2026-10-13T04:35:56Z')
    (directory/'result.json').write_text(json.dumps(result))
    monkeypatch.setattr(ui,'resolve_operation_report_download',lambda run,name:resolve_operation_report_download(run,name,root=root))
    return dict(root=root,path=path,run=run,result=result,latest={'fundamentals_refresh_preview_report':str(path)})


def normal_logs(tmp_path):
    for name in ['stock_update_usa_20261013T0500Z.txt','ec_source_layer_usa_20261013T0418Z.txt','datacenter_pipeline_usa_20261013T0417Z.txt']:
        (tmp_path/name).write_text('log')
    return ui.list_scheduler_log_files(str(tmp_path))


def test_timestamped_artifact_is_sorted_by_parent_completion_not_mtime(report,tmp_path):
    path=report['path'];before=path.read_bytes();os.utime(path,(1,1))
    entries=ui.scheduler_log_artifacts(normal_logs(tmp_path),report['latest'])
    assert [e['filename'] for e in entries]==[
        'stock_update_usa_20261013T0500Z.txt','fundamentals_full_workflow_20261013T043556Z.md',
        'ec_source_layer_usa_20261013T0418Z.txt','datacenter_pipeline_usa_20261013T0417Z.txt']
    entry=entries[1]
    assert entry['timestamp']=='20261013T043556Z' and entry['metadata_status']=='KNOWN'
    assert entry['path']==str(path) and entry['media_type']=='text/plain'
    assert entry['open_url']==ui.SCHEDULER_FUNDAMENTALS_VIEW_ROUTE+'/'+report['run']
    assert entry['download_url']==ui.FUNDAMENTALS_ADMIN_DOWNLOAD_ROUTE+'/'+report['run']+'/workflow_report.md'
    assert path.name=='workflow_report.md' and path.read_bytes()==before


@pytest.mark.parametrize('change',['missing','corrupt','wrong_run','wrong_mode','naive','invalid_time'])
def test_unbound_report_stays_visible_without_invented_timestamp(report,change):
    p=report['path'].parent/'result.json';v=report['result']
    if change=='missing':p.unlink()
    elif change=='corrupt':p.write_text('{bad json')
    else:
        if change=='wrong_run':v['run_id']='other'
        elif change=='wrong_mode':v['mode']='PREVIEW'
        else:
            v.pop('started_at_utc');v['completed_at_utc']='2026-10-13T04:35:56' if change=='naive' else 'bad'
        p.write_text(json.dumps(v))
    entries=ui.scheduler_log_artifacts([],report['latest'])
    assert len(entries)==1 and entries[0]['timestamp'] is None
    assert entries[0]['filename']=='fundamentals_full_workflow_unknown_timestamp.md'
    assert entries[0]['metadata_status']=='UNKNOWN'
    assert entries[0]['open_url']


def test_running_parent_uses_exact_started_timestamp(report):
    v=report['result'];v['completed_at_utc']=None
    (report['path'].parent/'result.json').write_text(json.dumps(v))
    assert ui.scheduler_log_artifacts([],report['latest'])[0]['timestamp']=='20261013T041843Z'


def request(app,url):
    async def get():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            return await client.get(url)
    # This restricted runner stalls AnyIO worker threads even for an unchanged
    # FileResponse. Execute test file I/O inline while retaining real ASGI routing,
    # response headers and body streaming. Production response code is unpatched.
    async def inline_file_io(function,*args,**kwargs):return function(*args)
    with patch("anyio.to_thread.run_sync",inline_file_io):
        return asyncio.run(get())


def test_inline_http_opens_exact_markdown_as_readable_text_and_download_unchanged(report):
    app=FastAPI();ui.add_scheduler_fundamentals_view_route(app);ui.add_fundamentals_admin_download_route(app)
    response=request(app,ui.scheduler_fundamentals_report_url(report['latest']))
    assert response.status_code==200 and response.content==report['path'].read_bytes()
    assert response.headers['content-type']=='text/plain; charset=utf-8'
    assert response.headers['content-disposition']=='inline; filename="fundamentals_full_workflow_20261013T043556Z.md"'
    assert response.headers['x-content-type-options']=='nosniff'
    download=request(app,ui.FUNDAMENTALS_ADMIN_DOWNLOAD_ROUTE+'/'+report['run']+'/workflow_report.md')
    assert download.status_code==200 and download.content==response.content
    assert download.headers['content-type'].startswith('text/markdown')
    assert download.headers['content-disposition']=='attachment; filename="workflow_report.md"'


@pytest.mark.parametrize('kind',['report_escape','report_inside_link','run_symlink','metadata_symlink'])
def test_symlinks_cannot_escape_inline_route_or_supply_timestamp(report,tmp_path,kind):
    path=report['path'];app=FastAPI();ui.add_scheduler_fundamentals_view_route(app)
    if kind=='metadata_symlink':
        metadata=path.parent/'result.json';other=tmp_path/'other.json';metadata.rename(other);metadata.symlink_to(other)
        assert ui.scheduler_log_artifacts([],report['latest'])[0]['timestamp'] is None
        assert request(app,ui.SCHEDULER_FUNDAMENTALS_VIEW_ROUTE+'/'+report['run']).status_code==200
        return
    if kind=='run_symlink':
        saved=tmp_path/'saved';path.parent.rename(saved);path.parent.symlink_to(saved,target_is_directory=True)
    else:
        target=tmp_path/'workflow_report.md' if kind=='report_escape' else path.with_name('operation_report.md')
        target.write_text('unapproved target');path.unlink();path.symlink_to(target)
    assert ui.scheduler_fundamentals_report_url(report['latest']) is None
    assert request(app,ui.SCHEDULER_FUNDAMENTALS_VIEW_ROUTE+'/'+report['run']).status_code==404


@pytest.mark.parametrize('suffix',['../outside','%2E%2E%2Foutside','run/workflow_report.md','run/data.bin'])
def test_inline_route_rejects_arbitrary_or_traversal_paths(report,suffix):
    app=FastAPI();ui.add_scheduler_fundamentals_view_route(app)
    assert request(app,ui.SCHEDULER_FUNDAMENTALS_VIEW_ROUTE+'/'+suffix).status_code==404


def test_binary_summary_reference_is_not_classified_as_workflow_text(report):
    path=report['path'].with_name('database.bin');path.write_bytes(b'\x00\xff')
    assert ui.scheduler_fundamentals_report_url({'fundamentals_refresh_preview_report':str(path)}) is None
    assert ui.scheduler_log_artifacts([],{'fundamentals_refresh_preview_report':str(path)})==[]


def test_seconds_and_minutes_share_one_chronological_sort(report):
    entries=[dict(filename='seconds.txt',sort_key='20261013T043557Z_0'),dict(filename='minutes.txt',sort_key='20261013T0435Z_0')]
    assert [e['filename'] for e in ui.scheduler_log_artifacts(entries,report['latest'])]==[
        'seconds.txt','fundamentals_full_workflow_20261013T043556Z.md','minutes.txt']
