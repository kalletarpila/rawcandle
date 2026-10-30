"""Native disposable storage paths reject lossy evidence before authority changes."""
from dataclasses import replace
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
import csv
import io
import json
import sqlite3
import zipfile

import pytest

from rawcandle.fundamentals import source_capture as cap
from rawcandle.fundamentals.admin import batch_add_tickers as add
from rawcandle.fundamentals.admin import historical_freeze as freeze
from rawcandle.fundamentals.admin import refresh_fundamentals as refresh
from rawcandle.fundamentals.admin import refresh_copy_runtime as runtime
from rawcandle.fundamentals.admin import refresh_review_queue as reviews
from rawcandle.fundamentals.schema.production_bootstrap import insert_production_sharadar_observation
from tests.provider_capture_fixtures import acquired, full_row
from tests.test_phase12d_operational_rebuild import _databases
from tests.test_provider_capture_contract import raw


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(cap, 'ACTIVE', True)


@pytest.mark.parametrize('entrypoint', ['bootstrap', 'refresh_insert', 'refresh_replace', 'add'])
@pytest.mark.parametrize('unattested', ['projection', 'full_shape'])
def test_native_authoritative_writers_reject_unattested_without_mutation(tmp_path, entrypoint, unattested):
    provider, canonical, analysis = _databases(tmp_path)
    row = refresh.normalize_source_row(raw()) if unattested == 'projection' else raw()
    before = {p: cap._sha(p) for p in (provider, canonical, analysis)}
    identity = dict(company_id=1, security_id=1, provider_security_id='1')
    with pytest.raises(cap.CaptureError, match=cap.UNVERIFIED):
        if entrypoint == 'bootstrap':
            with sqlite3.connect(provider) as conn:
                insert_production_sharadar_observation(conn, row, 'run', 'now', company_id=1, security_id=1)
        elif entrypoint == 'refresh_insert':
            with sqlite3.connect(provider) as conn:
                runtime.insert_provider_source_row(conn, row, identity, run_id='run', applied_at='now')
        elif entrypoint == 'refresh_replace':
            good = refresh.validate_complete_history(acquired([raw()]), ticker='AAA', dimension='ARQ')
            forged = replace(good, rows=(row,))  # COMPLETE cannot substitute for capture.
            runtime.replace_provider_histories(provider, {'AAA': {'ARQ': forged, 'MRQ': forged}},
                {'AAA': identity}, applied_at='now')
        else:
            paths = add.BatchAddTickerPaths(provider, canonical, analysis, tmp_path/'market', tmp_path/'taxonomy')
            add._stage_generic_provider_rows(paths, [dict(ticker='AAA', rows=[row])], applied_at='now')
    assert {p: cap._sha(p) for p in before} == before


def test_raw_capture_persistence_reload_and_consumers(tmp_path):
    provider, canonical, analysis = _databases(tmp_path)
    original = raw()
    original.update(_unknown_upstream={'nested': [None, 0, '']}, empty_extra='', optional_extra=None)
    captured = acquired([original], full=False)[0]
    with sqlite3.connect(provider) as conn:
        insert_production_sharadar_observation(conn, captured, 'run', 'accepted', company_id=1, security_id=1)
        payload, provenance = conn.execute('SELECT payload_json,provenance_json FROM provider_observation').fetchone()
    assert json.loads(payload) == original
    assert json.loads(provenance)['source_capture'] == captured.capture
    loaded = refresh.load_current_history(provider, 'AAA', 'ARQ')['rows'][0]
    assert cap.raw_payload(loaded) == original
    for profile in (cap.BASE, cap.PB, cap.FREEZE, cap.REPAIR):
        assert cap.require(loaded, profile) == captured.capture
    from rawcandle.fundamentals.admin.provider_payload import compare_payload
    assert compare_payload(loaded, cap.wire(captured))['reason'] == 'NO_PAYLOAD_CHANGE'
    assert cap.field_state(cap.raw_payload(loaded), 'optional_extra') == 'EXPLICIT_NULL'
    assert cap.field_state(cap.raw_payload(loaded), 'absent_extra') == 'ABSENT'


def write_archive(path, rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=sorted(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fundamentals.csv', out.getvalue())
    manifest = path.parent/'archive_manifest.json'
    manifest.write_text(json.dumps(dict(sha256=cap._sha(path),
        acquired_at_utc='2026-10-30T00:00:00Z', upstream_request_scope='/data/fundamentals?years=10')))
    return manifest


def test_managed_archive_capture_and_local_reuse_preserve_original_origin(tmp_path):
    provider, canonical, analysis = _databases(tmp_path)
    archive = tmp_path/'source.zip'; manifest = write_archive(archive, [raw()])
    captured = next(cap.archive_records(archive))
    assert cap.require(captured, cap.REPAIR)['acquired_at_utc'] == '2026-10-30T00:00:00Z'
    with sqlite3.connect(provider) as conn:
        insert_production_sharadar_observation(conn, captured, 'run', 'accepted', company_id=1, security_id=1)
        before = conn.execute('SELECT * FROM provider_observation').fetchall()
    paths = add.BatchAddTickerPaths(provider, canonical, analysis, tmp_path/'market', tmp_path/'taxonomy')
    local = add._local_provider_rows(paths, 'AAA')
    assert cap.require(local[0]) == captured.capture
    add._stage_generic_provider_rows(paths, [dict(ticker='AAA', rows=local)], applied_at='later')
    with sqlite3.connect(provider) as conn:
        assert conn.execute('SELECT * FROM provider_observation').fetchall() == before
    manifest.unlink()
    with pytest.raises(cap.CaptureError, match=cap.UNVERIFIED): list(cap.archive_records(archive))
    assert add._archive_rows(archive, {'AAA'}) == {'AAA': ()}


def test_archive_checksum_and_projected_bulk_fail_closed(tmp_path):
    archive = tmp_path/'source.zip'
    write_archive(archive, [refresh.normalize_source_row(raw())])
    projected = next(cap.archive_records(archive))
    with pytest.raises(cap.CaptureError, match=cap.UNVERIFIED): cap.require(projected)
    archive.write_bytes(archive.read_bytes() + b'changed')
    with pytest.raises(cap.CaptureError, match=cap.UNVERIFIED): list(cap.archive_records(archive))


def test_one_capture_failure_is_local_and_safe_peer_continues_without_queue_write(tmp_path):
    provider, canonical, analysis = _databases(tmp_path)
    # The current source can remain grandfathered accepted evidence. No V1
    # re-attestation of it occurs while comparing a new failed acquisition.
    current_row = refresh.normalize_source_row(raw())
    current = {d: dict(rows=[dict(current_row, dimension=d)], invalid_rows=[],
        legacy_source_version_ambiguities=[], current_row_count=1) for d in ('ARQ', 'MRQ')}
    histories = {d: refresh.validate_complete_history([dict(current_row, dimension=d)],
        ticker='AAA', dimension=d) for d in ('ARQ', 'MRQ')}
    change = refresh.compare_ticker_histories('AAA', current, histories)
    change['identity'] = dict(status='KNOWN', company_id=1, security_id=1, provider_security_id='1')
    before = {p: cap._sha(p) for p in (provider, canonical, analysis)}
    partition = reviews.partition_changes([change, dict(ticker='BBB', classification='NEW_QUARTER')])
    assert partition['binding']['safe_tickers'] == ['BBB']
    assert partition['held'][0]['ticker'] == 'AAA'
    assert not partition['global_blockers']
    assert {p: cap._sha(p) for p in before} == before


def test_review_binding_ignores_recapture_time_but_keeps_exact_payload():
    first, second = acquired([raw()])[0], acquired([raw()])[0]
    assert first.capture['capture_fingerprint'] != second.capture['capture_fingerprint']
    assert cap.review_row(cap.wire(first)) == cap.review_row(cap.wire(second))
    changed = raw(); changed['sharefactor'] = None
    assert cap.review_row(cap.wire(acquired([changed])[0])) != cap.review_row(cap.wire(first))
    # Review evidence cannot be promoted back to fresh acquisition authority.
    with pytest.raises(cap.CaptureError): cap.require(cap.review_row(cap.wire(first)))


def test_network_add_revalidation_binds_exact_rows_independently_of_capture_time(tmp_path):
    from tests.test_fundamentals_admin_batch_add_tickers import _generic_paths, _archive_row
    paths = _generic_paths(tmp_path/'source')
    class Client:
        request_count = 0
        def fundamentals(self, **kwargs):
            self.request_count += 1
            return SimpleNamespace(ok=True, status='SUCCESS', auth_status='AUTH_OK', http_status=200,
                endpoint='/data/fundamentals', url='https://api.sharadar.com/v1.0/data/fundamentals',
                records=acquired([_archive_row('NEWC')]))
    def plan():
        return add.build_generic_batch_plan(paths, add.parse_batch_tickers('NEWC'),
            now='2026-10-30T00:00:00Z', archive_path=tmp_path/'missing.zip',
            network_allowed=True, network_client=Client()).safe_dict(include_rows=True)
    first, second = plan(), plan()
    assert first['items'][0]['status'] == 'ELIGIBLE'
    assert first['items'][0]['rows'][0]['_capture_envelope'] != second['items'][0]['rows'][0]['_capture_envelope']
    assert first['items'][0]['source_fingerprint'] == second['items'][0]['source_fingerprint']
    assert first['plan_fingerprint'] == second['plan_fingerprint']


@pytest.mark.parametrize('legacy_projection', [False, True])
def test_legacy_local_cache_requires_reacquisition_and_is_never_relabelled(tmp_path, legacy_projection):
    provider, canonical, analysis = _databases(tmp_path)
    with sqlite3.connect(provider) as conn:
        insert_production_sharadar_observation(conn, acquired([raw()])[0], 'run', 'old', company_id=1, security_id=1)
        conn.execute("UPDATE provider_observation SET provenance_json='{}'")
        if legacy_projection:
            projected=refresh.normalize_source_row(raw())
            assert len(projected)==29
            conn.execute('UPDATE provider_observation SET payload_json=?', (json.dumps(projected),))
    before = cap._sha(provider)
    paths = add.BatchAddTickerPaths(provider, canonical, analysis, tmp_path/'market', tmp_path/'taxonomy')
    failures = {}
    assert add._local_provider_rows(paths, 'AAA', capture_failures=failures) == ()
    assert failures['AAA'][0]['reason'] == cap.UNVERIFIED
    assert cap._sha(provider) == before


def test_malformed_native_record_is_captured_as_incomplete_without_client_crash():
    row = raw(); row['date'] = 'not-a-date'
    captured = acquired([row], full=False)[0]
    assert cap.profile_report(captured, cap.BASE)['reason'] == cap.INCOMPLETE
    with pytest.raises(cap.CaptureError, match=cap.INCOMPLETE): cap.require(captured)
