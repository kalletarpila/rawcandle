"""Workflow-level disposable acceptance for the future capture contract."""
from dataclasses import replace
import csv
import json
import sqlite3

import pytest

from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.admin import refresh_fundamentals as refresh
from rawcandle.fundamentals.admin import refresh_review_queue as reviews
from rawcandle.fundamentals.admin import provider_payload as repair
from rawcandle.fundamentals.admin.review_presentation import provider_review
from rawcandle.fundamentals.admin.review_evidence_presentation import evidence_summary
from rawcandle.fundamentals.generations import resolve_active_generation
from tests import test_fundamentals_admin_refresh_full_workflow_production_parity as native
from tests.test_provider_capture_contract import raw
from tests.provider_capture_fixtures import acquired


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(capture, 'ACTIVE', True)


@pytest.mark.parametrize('safe_peer', [False, True], ids=['lossy-refresh-rejected', 'safe-peer-continues'])
def test_native_refresh_capture_hold_preserves_source_and_generation_contract(tmp_path, monkeypatch, safe_peer):
    fixture = native._fixture(tmp_path, monkeypatch)
    if safe_peer:
        for dimension in ('ARQ', 'MRQ'):
            fixture.client.histories['BBB'][dimension][-1]['revenue'] += 19
            fixture.client.histories['BBB'][dimension][-1]['lastupdated'] = '2026-09-20'
    project = native._migrate_refresh_fixture_to_generation_layout(fixture, monkeypatch)
    old = resolve_active_generation(project, require_generation=True)
    old_hashes = {role: capture._sha(path) for role, path in old.role_paths().items()}
    held_before = native._published_financial_fingerprint(fixture.paths, ticker='AAA', company_id=1)
    with sqlite3.connect(old.role_paths()['provider']) as conn:
        raw_before = conn.execute("SELECT * FROM provider_observation WHERE provider_ticker='AAA' ORDER BY observation_id").fetchall()
    journal_before = fixture.journal_path.read_bytes() if fixture.journal_path.exists() else None
    original = fixture.client.fundamentals

    def projected_response(**kwargs):
        result = original(**kwargs)
        if kwargs.get('ticker') == 'AAA' and not kwargs.get('fields'):
            projected = [refresh.normalize_source_row(row) for row in result.records]
            return replace(result, records=projected, payload=projected)
        return result

    monkeypatch.setattr(fixture.client, 'fundamentals', projected_response)
    service = native._service(fixture, actual_production=True)
    result = service.full_workflow(operation_type='REFRESH_FUNDAMENTALS', raw_inputs='', ownership_auto_enabled=False)
    workflow = native._workflow_payload(result)
    active = resolve_active_generation(project, require_generation=True)
    queue = service.refresh_review_queue()
    assert len(queue) == 1 and queue[0]['ticker'] == 'AAA'
    assert capture.UNVERIFIED in queue[0]['reason_codes']
    assert queue[0]['status'] == 'OPEN'
    assert 'accept_retained_history_eligible' not in queue[0]
    queue_path = reviews.queue_path_for_run_root(fixture.run_root)
    queue_before = capture._sha(queue_path)
    presented = reviews.present_review_item(queue[0])
    assert presented['classification'] == capture.UNVERIFIED
    assert not presented['accept_retained_history_eligible']
    assert capture._sha(queue_path) == queue_before
    assert native._published_financial_fingerprint(
        type(fixture.paths)(*(active.role_paths().get(role, fixture.paths.as_dict()[role])
            for role in ('provider', 'canonical', 'analysis', 'market', 'taxonomy'))),
        ticker='AAA', company_id=1) == held_before
    with sqlite3.connect(active.role_paths()['provider']) as conn:
        assert conn.execute("SELECT * FROM provider_observation WHERE provider_ticker='AAA' ORDER BY observation_id").fetchall() == raw_before
    assert {role: capture._sha(path) for role, path in old.role_paths().items()} == old_hashes
    if safe_peer:
        assert result.outcome == 'COMPLETED', result
        assert active.generation_id != old.generation_id
        production = native._stage_payload(workflow, 'Production update')
        assert production['provider_candidate']['ticker_count'] == 1
        assert production['quarantine_evidence']['held_tickers'] == ['AAA']
        journal = json.loads(fixture.journal_path.read_text())
        assert journal['state'] == 'COMPLETED' and journal['postflight_state'] == 'PASSED'
        assert journal['generation_activation_state'] == 'ACTIVATED_AND_VERIFIED'
        assert production['terminal_cleanup']['cleanup_verification']['status'] == 'PASSED'
    else:
        assert active.generation_id == old.generation_id
        assert workflow['operational_decision']['decision_code'] == 'NO_SAFE_CHANGES'
        assert not any(stage['stage'] in ('Test on copies', 'Production update') for stage in workflow['stages'])
        assert (fixture.journal_path.read_bytes() if fixture.journal_path.exists() else None) == journal_before
    native._assert_terminal_lane_cleanup(fixture)


def test_operational_backfill_rejects_projected_managed_file_without_mutation(tmp_path):
    from tests.test_phase12c_sharadar_backfill import fixture_paths, _manifest
    from rawcandle.fundamentals.schema.phase12c_backfill import validate_staged_source, import_staged
    paths = fixture_paths(tmp_path)
    with paths.staged_csv.open(newline='') as stream:
        projected = [refresh.normalize_source_row(row) for row in csv.DictReader(stream)]
    with paths.staged_csv.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=refresh.REFRESH_REQUEST_FIELDS)
        writer.writeheader(); writer.writerows(projected)
    _manifest(paths.staged_csv)
    validation = validate_staged_source(paths.staged_csv, target={'AAA'}, old_oldest_arq='2020-09-30')
    before = {path: capture._sha(path) for path in (paths.provider_db, paths.canonical_db, paths.analysis_db)}
    with pytest.raises(capture.CaptureError, match=capture.UNVERIFIED):
        import_staged(paths, validation)
    assert {path: capture._sha(path) for path in before} == before


def test_strict_repair_rejects_projected_history_even_if_marked_complete(tmp_path):
    from tests.test_provider_payload_completeness import fixture, candidate
    db, current, histories = fixture(tmp_path)
    selected = candidate(current, histories)
    projected = refresh.normalize_source_row(histories['ARQ'].rows[0])
    forged = {**histories, 'ARQ': replace(histories['ARQ'], rows=(projected,))}
    before = capture._sha(db)
    with pytest.raises(capture.CaptureError, match=capture.UNVERIFIED):
        repair.repair_payloads_on_copy(db, [selected], source_histories={('TEST', d): h for d, h in forged.items()},
            fetched_at_utc='2026-10-30T00:00:00Z')
    assert capture._sha(db) == before


@pytest.mark.parametrize('reason', [capture.UNVERIFIED, capture.INCOMPLETE])
def test_existing_review_ui_exposes_capture_failure_without_mutation(tmp_path, reason):
    from tests.test_fundamentals_review_action_first import Service, render, text
    incoming = raw()
    if reason == capture.INCOMPLETE:
        incoming.pop('revenue')
        record = acquired([incoming], full=False)[0]
    else:
        record = refresh.normalize_source_row(incoming)
    report = capture.review_report(capture.profile_report(record, capture.BASE))
    assert report['reason'] == reason
    change = dict(ticker='AAA', classification='REVIEW_REQUIRED', review_reason=reason,
        identity=dict(status='KNOWN', company_id=1, security_id=1, provider_security_id='1'),
        capture_integrity=dict(current_history_valid=True, failures=[dict(report, ticker='AAA')]))
    queue = reviews.RefreshReviewQueue(tmp_path/'queue.db')
    queue.upsert_local(reviews.classify_review_scope(change), run_id='disposable-preview', published_binding='copy-baseline')
    item = reviews.present_review_item(queue.get('AAA'))
    before = capture._sha(queue.path)
    view = provider_review(item)
    assert 'Reacquire provider source' in view.next_action
    assert not item['accept_retained_history_eligible']
    assert not item['accept_fiscal_revision_eligible'] and not item['confirm_true_removal_eligible']
    details = '\n'.join(evidence_summary('provider', item))
    for label in ('Source profile:', 'Missing keys:', 'Explicit-null keys:', 'Unusable fields:',
                  'Capture provenance:', 'Raw fingerprint:', 'Normalized fingerprint:'):
        assert label in details
    service = Service(providers=[item])
    controls = render(service)
    primary = text(controls.review_queue_column)
    assert 'AAA' in primary and 'Reacquire provider source' in primary
    assert 'Source profile:' not in primary and 'Raw fingerprint:' not in primary
    assert not service.actions and capture._sha(queue.path) == before
