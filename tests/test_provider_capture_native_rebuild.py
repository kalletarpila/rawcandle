"""Captured current-version rebuild with the actual bounded analysis engine."""
from copy import deepcopy
import json
import sqlite3

from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.admin import current_state_rebuild as rebuild
from rawcandle.fundamentals.admin import refresh_fundamentals as source
from rawcandle.fundamentals.admin.refresh_review_queue import _connect
from rawcandle.fundamentals.admin.contracts import utc_now
from rawcandle.fundamentals.pb_reporting_contract import activate_quarterly_ownership
from tests import test_fundamentals_admin_refresh_full_workflow_production_parity as native
from tests.provider_capture_fixtures import acquired


def test_current_rebuild_runs_real_analysis_and_preserves_original_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, 'ACTIVE', True)
    fixture = native._fixture(tmp_path, monkeypatch)
    with sqlite3.connect(fixture.paths.provider_db) as conn:
        oid, payload = conn.execute("SELECT observation_id,payload_json FROM provider_observation "
            "WHERE provider_ticker='AAA' AND dimension='ARQ' ORDER BY reportperiod DESC LIMIT 1").fetchone()
        raw = json.loads(payload)
        # Model accepted pre-V1 capture loss only on this disposable baseline.
        projected = source.normalize_source_row(raw)
        conn.execute("UPDATE provider_observation SET payload_json=?,provenance_json='{}' WHERE observation_id=?",
            (json.dumps(projected, sort_keys=True), oid))
    activate_quarterly_ownership(fixture.paths.canonical_db, effective_from='2026-10-08')
    project = native._migrate_refresh_fixture_to_generation_layout(fixture, monkeypatch)
    queue = project/'fundamental_reports/reviews.db'
    queue.parent.mkdir(parents=True)
    with _connect(queue) as conn:
        conn.execute('CREATE TABLE unrelated_review_marker(value)')
        conn.execute("INSERT INTO unrelated_review_marker VALUES('preserved')")
    fresh = {**raw, 'lastupdated': '2026-10-30'}
    acquisition = rebuild.seal(dict(schema=rebuild.VERSION+'_ACQUISITION', provider='SHARADAR',
        table='fundamentals', endpoint=source.SOURCE_ENDPOINT, ticker='AAA', acquired_at=utc_now(),
        fields=sorted(raw), histories={dimension: [capture.wire(acquired([
            {**fresh, 'dimension': dimension}], full=False)[0])] for dimension in ('ARQ', 'MRQ')}),
        'acquisition_fingerprint')
    monkeypatch.setattr(rebuild, 'acquire', lambda ticker, client=None: deepcopy(acquisition))
    baseline = rebuild.baseline(project, queue)
    plan = rebuild.preview(project, queue, [(source.source_key(fresh), acquisition)], source_baseline=baseline)
    receipt = rebuild.test_on_copies(project, queue, plan, tmp_path/'real-analysis-rebuild', as_of=native.AS_OF)
    rebuild.verify_test(plan, receipt)
    assert receipt['native_analysis']['invocation_counts']['full_v2_rebuild'] == 1
    assert receipt['result']['outcomes']['AAA']['current_complete']
    assert receipt['result']['ownership_unchanged']
    assert receipt['result']['unrelated_provider_unchanged']
    assert receipt['result']['unrelated_canonical_unchanged']
    assert rebuild.baseline(project, queue) == baseline
    with sqlite3.connect(receipt['candidates']['provider']) as conn:
        payload, provenance = conn.execute("SELECT payload_json,provenance_json FROM provider_observation "
            "WHERE provider_ticker='AAA' AND dimension='ARQ' ORDER BY reportperiod DESC LIMIT 1").fetchone()
    assert json.loads(payload) == fresh
    proof = json.loads(provenance)['source_capture']
    assert capture.profile_report(fresh, capture.REPAIR, capture=proof)['eligible_authoritative_full_source']
