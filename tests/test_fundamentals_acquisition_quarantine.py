"""UPDATE-only source exclusions using real native capture and financial kernels."""

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import socket
from urllib.parse import parse_qs, urlsplit

import pytest

from rawcandle.fundamentals.admin import acquisition_snapshot as a, refresh_update as core
from rawcandle.fundamentals.admin import review_locality as locality
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.generations import resolve_active_generation
from tests.test_fundamentals_acquisition_rejections import Response
from tests.test_fundamentals_snapshot_integration import setup
from tests import test_fundamentals_snapshot_workflow as fixtures


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Live network forbidden in FIX2")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def configured(tmp_path, monkeypatch, change, *, degraded=False):
    workflow, native, histories, calls = setup(tmp_path, monkeypatch, held=True, degraded_count=1 if degraded else 0)
    histories["YYAI"] = fixtures.native._yyai_histories(current=False)
    for rows in histories["YYAI"].values():
        rows[-1]["revenue"] += 7
        rows[-1]["lastupdated"] = "2026-11-10"
    opener = workflow.client._opener

    def transport(request, timeout):
        response = opener(request, timeout)
        params = {k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()}
        if "ticker" in params:
            payload = json.loads(response.read())
            changed = change(params, payload)
            return changed if isinstance(changed, Response) else Response(changed)
        return response
    monkeypatch.setattr(workflow.client, "_opener", transport)
    return workflow, native, histories, calls


def snapshot(workflow, result):
    return a.open_snapshot(result["fetch_operation_id"], root=workflow.env.runs)


@pytest.mark.parametrize("dimension", ["ARQ", "MRQ"])
def test_empty_history_excludes_both_dimensions_and_continues_peers(tmp_path, monkeypatch, dimension):
    workflow, _, _, calls = configured(tmp_path, monkeypatch,
        lambda p, rows: {"count": 0, "data": []} if (p['ticker'], p['dimension']) == ('BBB', dimension) else rows)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after="fetch")
    assert result["outcome"] == "FETCH_SEALED", result
    snap = snapshot(workflow, result)
    assert list(snap.quarantines()) == ["BBB"]
    assert snap.quarantines()['BBB']['valid_partial_capture_obtained'] is True
    assert len(snap.quarantines()['BBB']['verified_partial_captures']) == 1
    assert snap.manifest["accounted_slots"] == 6
    assert snap.manifest["quarantined_slots"] == 2
    assert snap.manifest["complete_verified_slots"] == 5
    assert snap.manifest["nonquarantined_verified_slots"] == 4
    assert snap.manifest["pending_slots"] == 0
    assert ('AAA', 'MRQ') in calls and ('YYAI', 'ARQ') in calls and ('BBB', 'ARQ') in calls and ('BBB', 'MRQ') in calls
    for slot in snap.iter_slots():
        if slot["ticker"] == "BBB":
            with pytest.raises(a.SnapshotError, match="TICKER_ACQUISITION_QUARANTINED"):
                snap.read_slot(slot["slot"])
    assert "whole-ticker quarantines 1" in result["summary_rows"][-1]
    assert "quarantine is not complete history" in (workflow.env.directory() / "workflow_report.md").read_text()
    service = FundamentalsAdminUIService(run_root=workflow.env.runs,
        refresh_route='SNAPSHOT_V1', snapshot_workflow=workflow, recover_publication_on_startup=False)
    entry = next(e for e in service.history_entries() if e.run_id == result['run_id'])
    assert entry.outcome == 'FETCH_SEALED' and entry.report_available
    displayed = service._finalize(result, default_message='fixture')
    assert any('whole-ticker quarantines 1' in row for row in displayed.summary_rows)


def test_integrated_quarantine_preserves_old_through_build_and_disposable_publication(tmp_path, monkeypatch):
    workflow, _, _, _ = configured(tmp_path, monkeypatch,
        lambda p, rows: [] if (p['ticker'], p['dimension']) == ('BBB', 'ARQ') else rows)
    paths = workflow.env.paths()
    from rawcandle.fundamentals.admin.refresh_fundamentals import resolve_identity
    identity = resolve_identity(paths, 'BBB')
    old = locality.authority(paths.provider_db, paths.canonical_db, 'BBB', identity, validate=True)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after="fetch")
    assert result["outcome"] == "FETCH_SEALED", result
    result = workflow.advance(result["run_id"], stop_after="validate")
    assert result["outcome"] == "VALIDATED", result
    decisions = core._read(workflow.env.runs / result["validation_id"] / "decisions.json")
    assert {x["ticker"] for x in decisions["safe"]} == {'AAA', 'YYAI'}
    assert [x["ticker"] for x in decisions["held"]] == ['BBB']
    assert decisions["held"][0]["change"]["acquisition_quarantine"]["incoming_financial_input_eligible"] is False
    assert core._queue_binding(workflow.env) is None  # No financial review invented.
    report = (workflow.env.runs/result['validation_id']/'operation_report.md').read_text()
    assert 'EMPTY_OR_LIMIT_COVERAGE_UNPROVEN' in report and 'fetch/quarantines/000002.json' in report
    result = workflow.advance(result["run_id"], stop_after="build")
    assert result["outcome"] == "CANDIDATE_READY", result
    assert resolve_active_generation(workflow.env.project).generation_id == 'old'
    build = core._read(workflow.env.runs / result["validation_id"] / "build.json")
    assert build["held_preservation"]["unchanged"]
    roles = build['prepared']['roles']
    assert locality.authority(Path(roles['provider']), Path(roles['canonical']), 'BBB', identity) == old
    result = workflow.advance(result["run_id"], confirm_publish=True)
    assert result["outcome"] == "COMPLETED", result
    current = workflow.env.paths()
    assert locality.authority(current.provider_db, current.canonical_db, 'BBB', identity) == old
    assert core.journals.load_journal(workflow.env.journal)['postflight_state'] == 'PASSED'
    assert not result.get('ownership_production_completed')
    assert snapshot(workflow, result).quarantines()['BBB']['state'] == 'LOCAL_ACQUISITION_QUARANTINE'


@pytest.mark.parametrize('defect', ['both_empty', 'malformed_member', 'wrong_ticker', 'wrong_dimension', 'mixed_dimensions', 'duplicate', 'out_of_window', 'bad_source_key', 'missing_field', 'bad_value', 'projected'])
def test_isolatable_source_failures_account_for_ticker_and_continue(tmp_path, monkeypatch, defect):
    def change(p, rows):
        if p['ticker'] != 'BBB' or (p['dimension'] != 'ARQ' and defect != 'both_empty'):
            return rows
        if defect == 'both_empty': return []
        if defect == 'malformed_member': return rows + [None]
        if defect == 'wrong_ticker':
            for r in rows: r['ticker'] = 'FOREIGN'
        if defect == 'wrong_dimension':
            for r in rows: r['dimension'] = 'MRQ'
        if defect == 'mixed_dimensions': return rows + [{**rows[0], 'dimension': 'MRQ'}]
        if defect == 'duplicate': return rows + [rows[0]]
        if defect == 'out_of_window': rows[0]['date'] = '2010-01-01'
        if defect == 'bad_source_key': rows[0]['date'] = 'not-a-date'
        if defect == 'missing_field': del rows[0]['revenue']
        if defect == 'bad_value': rows[0]['revenue'] = 'not-a-number'
        if defect == 'projected':
            return [{k: v for k, v in row.items() if k in a.REFRESH_REQUEST_FIELDS} for row in rows]
        return rows
    workflow, _, _, _ = configured(tmp_path, monkeypatch, change)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FETCH_SEALED', result
    snap = snapshot(workflow, result)
    assert set(snap.quarantines()) == {'BBB'}
    assert snap.quarantines()['BBB']['valid_partial_capture_obtained'] is (defect != 'both_empty')
    assert snap.manifest['accounted_slots'] == 6 and snap.manifest['pending_slots'] == 0
    assert snap.manifest['nonquarantined_verified_slots'] == 4
    for ref in snap.quarantines()['BBB']['receipts']:
        record = a._read(snap._run.verify(ref, 'QUARANTINE'))
        assert record['history_complete'] is False and record['absence_authorizes_deletion'] is False
        with pytest.raises(a.SnapshotError, match='ARTIFACT_TYPE_INVALID'):
            snap._run.ref(record['body']['relative_path'], 'BODY')


@pytest.mark.parametrize('status', [401, 403, 429, 503])
def test_shared_auth_and_transport_errors_never_become_local_quarantines(tmp_path, monkeypatch, status):
    workflow, _, _, _ = configured(tmp_path, monkeypatch,
        lambda p, rows: Response({'error': 'shared failure'}, status=status) if p['ticker'] == 'BBB' else rows)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == ('FETCH_PAUSED' if status == 429 else 'FETCH_BLOCKED'), result
    directory = workflow.env.runs / result['fetch_operation_id']
    assert not (directory / 'fetch/seal.json').exists()
    assert not list((directory / 'fetch/quarantines').glob('*.json'))


@pytest.mark.parametrize('defect', ['cross_ticker', 'pagination', 'body_binding', 'parameters', 'schema', 'provider_identity', 'provider_identity_quarantine', 'client_envelope'])
def test_global_source_contract_failures_stop(tmp_path, monkeypatch, defect):
    def change(p, rows):
        if p['ticker'] != 'BBB': return rows
        if defect == 'cross_ticker': return rows + [{**rows[0], 'ticker': 'AAA'}]
        if defect == 'pagination': return {'data': rows, 'next': 'unobserved'}
        if defect in {'provider_identity', 'provider_identity_quarantine'}:
            for row in rows: row['permaticker'] = 'foreign-security'
            if defect == 'provider_identity_quarantine': del rows[0]['revenue']
        return rows
    workflow, _, _, _ = configured(tmp_path, monkeypatch, change)
    if defect in {'body_binding', 'parameters', 'client_envelope'}:
        native = workflow.client.fundamentals
        def inconsistent(**kwargs):
            result = native(**kwargs)
            if kwargs.get('ticker') == 'BBB':
                if defect == 'client_envelope':
                    records = [a.capture.wire(row) for row in result.records]
                    envelope = records[0]['_capture_envelope']
                    envelope['projection_contract'] = 'BROKEN_CLIENT'
                    envelope['capture_fingerprint'] = a.capture.digest({k: v for k, v in envelope.items() if k != 'capture_fingerprint'})
                    return replace(result, records=records)
                return replace(result, response_body=result.response_body+b' ') if defect == 'body_binding' else replace(result, parameters={**result.parameters, 'limit': '1'})
            return result
        monkeypatch.setattr(workflow.client, 'fundamentals', inconsistent)
    if defect == 'schema':
        opener = workflow.client._opener
        monkeypatch.setattr(workflow.client, '_opener', lambda req, timeout: Response(['ticker']) if '/schema/' in req.full_url else opener(req, timeout))
    result = workflow.start(publication_intent=False, ownership_intent=False,
        stop_after='validate' if defect == 'provider_identity' else 'fetch')
    assert result['outcome'] == 'FAILED', result
    directory = workflow.env.runs / result['fetch_operation_id']
    if defect == 'provider_identity':
        # An otherwise valid captured history reaches the existing financial
        # identity gate; it must not become a financial candidate or quarantine.
        assert 'PHASE2_FOREIGN_PROVIDER_IDENTITY' in result['message']
        assert not result.get('validation_id') and not result['production_completed']
    else:
        assert not (directory / 'fetch/seal.json').exists()
    assert not list((directory / 'fetch/quarantines').glob('*.json'))


@pytest.mark.parametrize('failure', ['projected_schema', 'dimension_filter', 'reduced_projection'])
def test_repeated_shared_contract_signature_stops_without_numeric_threshold(tmp_path, monkeypatch, failure):
    def change(p, rows):
        if p['dimension'] == 'ARQ' and p['ticker'] in {'AAA', 'BBB'}:
            if failure == 'projected_schema':
                for row in rows: del row['revenue']
            elif failure == 'reduced_projection':
                return [{k: v for k, v in row.items() if k in a.REFRESH_REQUEST_FIELDS} for row in rows]
            else:
                for row in rows: row['dimension'] = 'MRQ'
        return rows
    workflow, _, _, _ = configured(tmp_path, monkeypatch, change)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FAILED' and result['message'] == 'SHARED_ACQUISITION_SOURCE_CONTRACT_FAILURE', result
    assert not (workflow.env.runs / result['fetch_operation_id'] / 'fetch/seal.json').exists()


def test_all_empty_sources_cannot_silently_seal_without_valid_peer_control(tmp_path, monkeypatch):
    workflow, _, _, _ = configured(tmp_path, monkeypatch, lambda p, rows: [])
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FAILED' and result['message'] == 'ACQUISITION_LOCALITY_WITHOUT_VALID_PEER_CONTROL', result
    assert not (workflow.env.runs / result['fetch_operation_id'] / 'fetch/seal.json').exists()


def test_pause_retains_quarantine_and_all_unattempted_slots_remain_pending(tmp_path, monkeypatch):
    paused = [False]
    def change(p, rows):
        if (p['ticker'],p['dimension']) == ('BBB','ARQ'): return []
        if (p['ticker'],p['dimension']) == ('BBB','MRQ') and not paused[0]:
            paused[0] = True
            return Response({}, status=429)
        return rows
    workflow, _, _, calls = configured(tmp_path, monkeypatch, change)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FETCH_PAUSED', result
    fetchdir = workflow.env.runs / result['fetch_operation_id']
    original = {p: p.read_bytes() for p in fetchdir.rglob('*') if p.is_file() and ('/checkpoints/' in str(p) or '/quarantines/' in str(p))}
    run = a._Run(workflow.env.runs, result['fetch_operation_id']);control=run.control()
    from rawcandle.fundamentals.admin import acquisition_quarantine as q
    rejected=q.load(run, control, workflow.env.project);checkpoints,times=a._checkpoints(run, control, rejected)
    with pytest.raises(a.SnapshotError, match='SNAPSHOT_COVERAGE_INCOMPLETE'):
        a._seal(run, control, checkpoints, times, fixtures.NOW, rejected=rejected, project_root=workflow.env.project)
    assert a._read(fetchdir/'result.json')['pending_slots'] == 3
    result = workflow.advance(result['run_id'], stop_after='fetch')
    assert result['outcome'] == 'FETCH_SEALED', result
    assert calls.count(('BBB','ARQ')) == 1 and calls.count(('AAA','ARQ')) == 1
    assert all(p.read_bytes()==body for p,body in original.items())
    count=len(calls);again=workflow.advance(result['run_id'], stop_after='fetch')
    assert again['outcome']=='FETCH_SEALED' and len(calls)==count


@pytest.mark.parametrize('artifact', ['quarantine_receipt', 'quarantine_body', 'quarantine_diagnostic', 'quarantine_index', 'counterpart_checkpoint'])
def test_sealed_quarantine_integrity_is_mandatory_for_validation(tmp_path, monkeypatch, artifact):
    workflow, _, _, calls = configured(tmp_path, monkeypatch, lambda p, rows: [] if (p['ticker'],p['dimension'])==('BBB','ARQ') else rows)
    result=workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome']=='FETCH_SEALED',result
    snap=snapshot(workflow,result);qref=snap.quarantines()['BBB']['receipts'][0];record=a._read(snap._run.verify(qref,'QUARANTINE'))
    targets={'quarantine_receipt':qref['relative_path'],'quarantine_body':record['body']['relative_path'],'quarantine_diagnostic':record['diagnostic']['relative_path'],'quarantine_index':'fetch/quarantine_index.jsonl','counterpart_checkpoint':'fetch/checkpoints/000003.json'}
    target=snap._run.path(targets[artifact]);target.unlink()
    calls_before=len(calls)
    result=workflow.advance(result['run_id'],stop_after='validate')
    assert result['outcome']=='FAILED' and not result.get('validation_id'),result
    assert len(calls)==calls_before  # No HTTP fallback after seal.
    assert resolve_active_generation(workflow.env.project).generation_id=='old'


def test_quarantined_sources_cannot_enter_publication_if_accounting_is_lost(tmp_path,monkeypatch):
    workflow, _, _, _ = configured(tmp_path,monkeypatch,lambda p,rows: [] if (p['ticker'],p['dimension'])==('BBB','MRQ') else rows)
    result=workflow.start(publication_intent=False,ownership_intent=False,stop_after='build')
    assert result['outcome']=='CANDIDATE_READY',result
    (workflow.env.runs/result['fetch_operation_id']/'fetch/checkpoints/000002.json').unlink()
    result=workflow.advance(result['run_id'],confirm_publish=True)
    assert result['outcome']=='FAILED' and not result['production_completed'],result
    assert resolve_active_generation(workflow.env.project).generation_id=='old'


def test_degraded_old_restrictions_survive_acquisition_quarantine(tmp_path,monkeypatch):
    workflow, _, _, _ = configured(tmp_path,monkeypatch,lambda p,rows: [] if p['ticker']=='HELD000' else rows,degraded=True)
    before=core.carry.snapshot(workflow.env.paths().canonical_db,10)
    result=workflow.start(publication_intent=False,ownership_intent=False,stop_after='build')
    assert result['outcome']=='CANDIDATE_READY',result
    decisions=core._read(workflow.env.runs/result['validation_id']/'decisions.json')
    held=next(x for x in decisions['held'] if x['ticker']=='HELD000')
    assert held['baseline_integrity_hold']['new_incoming_evidence_accepted'] is False
    build=core._read(workflow.env.runs/result['validation_id']/'build.json')
    after=core.carry.snapshot(Path(build['prepared']['roles']['canonical']),10)
    def semantic(state):
        return {table: sorted((tuple(sorted((k, v) for k, v in row.items() if k != 'provenance_id')) for row in rows), key=repr)
                for table, rows in state.items()}
    assert semantic(before)==semantic(after)


def test_original_age_is_not_reset_by_quarantine_resume(tmp_path,monkeypatch):
    paused=[False]
    def change(p,rows):
        if (p['ticker'],p['dimension'])==('BBB','ARQ'):return []
        if (p['ticker'],p['dimension'])==('BBB','MRQ') and not paused[0]:paused[0]=True;return Response({},status=429)
        return rows
    workflow, _, _, calls=configured(tmp_path,monkeypatch,change)
    result=workflow.start(publication_intent=False,ownership_intent=False,stop_after='fetch');n=len(calls)
    assert result['outcome']=='FETCH_PAUSED',result
    workflow.now=lambda:fixtures.NOW+timedelta(hours=169)
    result=workflow.advance(result['run_id'],stop_after='fetch')
    assert result['outcome']=='FAILED' and 'EXPIRED' in result['message'],result
    assert len(calls)==n


def test_quarantine_kernel_is_bound_before_it_is_tracked(monkeypatch):
    before = core._code_binding()
    native_hash = core.sha256_file
    monkeypatch.setattr(core, 'sha256_file', lambda path: '0'*64
        if path.name == 'acquisition_quarantine.py' else native_hash(path))
    assert core._code_binding() != before


def test_interrupted_quarantine_receipt_is_adopted_without_refetch(tmp_path, monkeypatch):
    from rawcandle.fundamentals.admin import acquisition_quarantine as q
    workflow, _, _, calls = configured(tmp_path, monkeypatch,
        lambda p, rows: [] if (p['ticker'], p['dimension']) == ('BBB', 'ARQ') else rows)
    native_append = a._append
    def interrupted(path, value):
        if path.name == 'quarantine_index.jsonl':
            raise OSError('fixture crash after durable quarantine receipt')
        return native_append(path, value)
    monkeypatch.setattr(a, '_append', interrupted)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FAILED', result
    directory = workflow.env.runs / result['fetch_operation_id']
    receipt = directory/'fetch/quarantines/000002.json'
    retained = receipt.read_bytes()
    assert a._read(receipt)['state'] == q.STATE
    monkeypatch.setattr(a, '_append', native_append)
    result = workflow.advance(result['run_id'], stop_after='fetch')
    assert result['outcome'] == 'FETCH_SEALED', result
    assert calls.count(('BBB', 'ARQ')) == 1 and calls.count(('AAA', 'ARQ')) == 1
    assert receipt.read_bytes() == retained
    assert len(list(a._lines(directory/'fetch/quarantine_index.jsonl'))) == 1


@pytest.mark.parametrize('drift', ['configuration', 'old'])
def test_paused_quarantine_rejects_immutable_binding_drift(tmp_path, monkeypatch, drift):
    def change(p, rows):
        if (p['ticker'], p['dimension']) == ('BBB', 'ARQ'): return []
        if (p['ticker'], p['dimension']) == ('BBB', 'MRQ'): return Response({}, status=429)
        return rows
    workflow, _, _, calls = configured(tmp_path, monkeypatch, change)
    result = workflow.start(publication_intent=False, ownership_intent=False, stop_after='fetch')
    assert result['outcome'] == 'FETCH_PAUSED', result
    count = len(calls)
    if drift == 'configuration':
        workflow.env.configuration['unexpected'] = 'changed'
    else:
        active = resolve_active_generation(workflow.env.project)
        manifest = json.loads(active.manifest_path.read_text())
        manifest['fixture_drift'] = True
        active.manifest_path.write_text(json.dumps(manifest))
    result = workflow.advance(result['run_id'], stop_after='fetch')
    assert result['outcome'] == 'FAILED' and 'DRIFT' in result['message'], result
    assert len(calls) == count


def test_acquisition_quarantine_does_not_consume_existing_financial_approval(tmp_path, monkeypatch):
    from rawcandle.fundamentals.admin import refresh_review_queue as q
    workflow, _, histories, _ = setup(tmp_path, monkeypatch, held=True, established=True)
    first = workflow.start(stop_after='validate')
    assert first['outcome'] == 'VALIDATED', first
    queue = q.RefreshReviewQueue(workflow.env.queue)
    approved = queue.apply_action('YYAI', q.ACCEPT_RETAINED_HISTORY, evidence={'operator': 'fixture'})
    assert approved['status'] == 'RETRY_REEVALUATION'
    binding = core._queue_binding(workflow.env)
    histories['YYAI'] = {'ARQ': [], 'MRQ': []}
    second = workflow.start(stop_after='build')
    assert second['outcome'] == 'CANDIDATE_READY', second
    assert core._queue_binding(workflow.env) == binding
    assert queue.get('YYAI') == approved
    final = workflow.advance(second['run_id'], confirm_publish=True)
    assert final['outcome'] == 'COMPLETED', final
    assert core._queue_binding(workflow.env) == binding
    assert queue.get('YYAI') == approved
