"""Completeness-only source repair: exact identity, immutable evidence, no approvals."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest

from rawcandle.fundamentals.admin import provider_payload as p
from rawcandle.fundamentals.admin.contracts import fingerprint
from rawcandle.fundamentals.admin import refresh_fundamentals as f
from tests.test_fundamentals_admin_refresh_copy_test import (
    create_provider, source_row, _insert_legacy_version,
)

NOW = '2026-10-28T13:00:00Z'
EXTRAS = {'sharefactor': 1.0, 'equity': 1000, 'equityusd': 1000,
          'price': 10.0, 'marketcap': 50, 'pb': .05}


def fixture(tmp_path, old_extras=None, new_extras=None, ticker='TEST'):
    db = tmp_path / 'provider.db'
    create_provider(db)
    raw = source_row(ticker=ticker)
    old = {**raw, **(old_extras or {})}
    new = {**raw, **(EXTRAS if new_extras is None else new_extras)}
    with sqlite3.connect(db) as c:
        for dimension in f.REFRESH_DIMENSIONS:
            r = {**old, 'dimension': dimension}
            _insert_legacy_version(c, r, 'old_' + dimension)
            c.execute('UPDATE provider_observation SET provider_ticker=?,provider_record_key=?,payload_json=?,content_hash=? WHERE observation_id=?',
                      (ticker, '|'.join(f.source_key(r)), json.dumps(r), fingerprint(f._raw_row(r)), 'old_' + dimension))
            c.execute('UPDATE sharadar_fundamental_observation SET ticker=? WHERE observation_id=?', (ticker, 'old_' + dimension))
    current = {d: f.load_current_history(db, ticker, d) for d in f.REFRESH_DIMENSIONS}
    histories = {d: f.validate_complete_history([{**new, 'dimension': d}], ticker=ticker, dimension=d) for d in f.REFRESH_DIMENSIONS}
    return db, current, histories


def candidate(current, histories, dimension='ARQ'):
    old, new = current[dimension]['rows'][0], histories[dimension].rows[0]
    comparison = p.compare_payload(old, new)
    return {'old_observation_id': old['_provider_observation_id'],
            'old_content_hash': old['_provider_content_hash'],
            'comparison_fingerprint': fingerprint(comparison)}


def repair(db, current, histories, candidates=None):
    t = histories['ARQ'].ticker
    return p.repair_payloads_on_copy(db, candidates or [candidate(current, histories)],
        source_histories={(t, d): h for d, h in histories.items()}, fetched_at_utc=NOW)


def test_projected_to_full_is_separate_from_financial_fingerprints(tmp_path):
    db, current, histories = fixture(tmp_path)
    old, new = current['ARQ']['rows'][0], histories['ARQ'].rows[0]
    assert f.semantic_row_fingerprints(old) == f.semantic_row_fingerprints(new)
    result = f.compare_ticker_histories('TEST', current, histories)
    assert result['classification'] == p.REPAIR
    assert result['changed_count'] == 0
    assert len(result['source_payload_changes']) == 2
    assert f.refresh_binding_change(result)['source_payload_change_fingerprint']
    # This phase prepares explicit copy-only repair candidates; ordinary
    # financial replacement does not silently apply a new repair operation.
    assert p.REPAIR not in f.REFRESH_REPLACEMENT_CLASSES


def test_full_same_full_is_no_change_with_explicit_nulls(tmp_path):
    extras = {**EXTRAS, 'optional': None}
    _, current, histories = fixture(tmp_path, extras, extras)
    assert f.compare_ticker_histories('TEST', current, histories)['classification'] == 'NO_EFFECTIVE_CHANGE'
    assert p.compare_payload(current['ARQ']['rows'][0], histories['ARQ'].rows[0])['reason'] == 'NO_PAYLOAD_CHANGE'


@pytest.mark.parametrize('field', tuple(EXTRAS))
@pytest.mark.parametrize('state,reason,classification', [
    ('absent_null', p.REPAIR, p.REPAIR),
    ('absent_value', p.REPAIR, p.REPAIR),
    ('null_value', 'SOURCE_PAYLOAD_VALUE_REVISION', 'HISTORICAL_REVISION'),
    ('value_absent', 'SOURCE_PAYLOAD_KEY_REGRESSION', 'REVIEW_REQUIRED'),
    ('value_changed', 'SOURCE_PAYLOAD_VALUE_REVISION', 'HISTORICAL_REVISION'),
])
def test_absent_null_value_are_distinct(tmp_path, field, state, reason, classification):
    old, new = {**EXTRAS}, {**EXTRAS}
    if state.startswith('absent'):
        old.pop(field)
    if state == 'absent_null':
        new[field] = None
    if state == 'null_value':
        old[field] = None
    if state == 'value_absent':
        new.pop(field)
    if state == 'value_changed':
        new[field] = 999
    _, current, histories = fixture(tmp_path, old, new)
    comparison = p.compare_payload(current['ARQ']['rows'][0], histories['ARQ'].rows[0])
    assert comparison['reason'] == reason
    assert f.compare_ticker_histories('TEST', current, histories)['classification'] == classification
    if state.startswith('absent'):
        assert p.field_state(current['ARQ']['rows'][0]['_acquisition_payload'], field) == 'ABSENT'
        assert comparison['fields_restored'] == [field]
        assert comparison['fields_restored_with_null'] == ([field] if state == 'absent_null' else [])


@pytest.mark.parametrize('ticker,shares,date', [
    ('GE', 1033351921, '2026-10-20'), ('RTX', 1349440548, '2026-10-20'), ('T', 6736473433, '2026-10-21'),
])
def test_exact_focus_shape_and_new_immutable_payload_identity(tmp_path, ticker, shares, date):
    db, current, histories = fixture(tmp_path, ticker=ticker)
    # Above fixture uses exactly the same 29-field financial projection shape
    # as GE/RTX/T. This case also checks their source-key/count shape directly.
    raw = source_row(ticker=ticker, date=date, reportperiod='2026-09-30', fiscalperiod='2026-Q3')
    raw['sharesbas'] = shares
    old = {**f.normalize_source_row(raw), '_acquisition_payload': raw}
    new = {**f.normalize_source_row(raw), '_acquisition_payload': {**raw, **EXTRAS}}
    assert len(raw) == 29 and p.compare_payload(old, new)['reason'] == p.REPAIR
    mrq_before = None
    with sqlite3.connect(db) as c:
        mrq_before = c.execute("SELECT * FROM provider_observation WHERE observation_id='old_MRQ'").fetchone()
    result = repair(db, current, histories)
    assert result['repaired_count'] == 1 and result['integrity_check'] == 'ok'
    binding = result['repairs'][0]
    assert binding['old_observation_id'] != binding['new_observation_id']
    assert binding['old_content_hash'] != binding['new_content_hash']
    assert binding['financial_fields_changed'] is False
    assert binding['source_fetch_timestamp'] == NOW
    with sqlite3.connect(db) as c:
        new_row = c.execute('SELECT payload_json,content_hash,provenance_json FROM provider_observation WHERE observation_id=?', (binding['new_observation_id'],)).fetchone()
        assert json.loads(new_row[0]) == histories['ARQ'].rows[0]['_acquisition_payload']
        assert new_row[1] == fingerprint(json.loads(new_row[0]))
        assert json.loads(new_row[2])['source_payload_repair'] == binding
        assert c.execute("SELECT * FROM provider_observation WHERE observation_id='old_MRQ'").fetchone() == mrq_before
    after = f.load_current_history(db, ticker, 'ARQ')
    assert p.compare_payload(after['rows'][0], histories['ARQ'].rows[0])['reason'] == 'NO_PAYLOAD_CHANGE'


@pytest.mark.parametrize('factor', [1.0, .125, 0])
def test_ordinary_ads_and_zero_factor_are_source_evidence_not_inferred(tmp_path, factor):
    db, current, histories = fixture(tmp_path, new_extras={**EXTRAS, 'sharefactor': factor})
    result = repair(db, current, histories)
    assert result['repairs'][0]['new']['key_states']['sharefactor'] == 'VALUE'
    assert f.load_current_history(db, 'TEST', 'ARQ')['rows'][0]['_acquisition_payload']['sharefactor'] == factor


def test_absent_to_null_records_information_without_value_recovery(tmp_path):
    db, current, histories = fixture(tmp_path, new_extras={'sharefactor': None})
    result = repair(db, current, histories)
    assert result['repairs'][0]['fields_restored_with_null'] == ['sharefactor']
    assert result['repairs'][0]['fields_restored_with_value'] == []


@pytest.mark.parametrize('drift', ['date', 'fiscalperiod', 'ticker', 'dimension', 'reportperiod', 'permaticker', 'financial', 'contradictory_payload'])
def test_identity_and_financial_contradictions_do_not_repair(tmp_path, drift):
    db, current, histories = fixture(tmp_path)
    old, new = current['ARQ']['rows'][0], deepcopy(histories['ARQ'].rows[0])
    if drift == 'financial':
        new['revenue'] += 1
        new['_acquisition_payload']['revenue'] += 1
    elif drift == 'contradictory_payload':
        new['_acquisition_payload']['revenue'] += 1
    elif drift == 'permaticker':
        new['_acquisition_payload']['permaticker'] = 'OTHER'
    else:
        value = {'date': '2026-09-17', 'fiscalperiod': '2026-Q3', 'ticker': 'OTHER',
                 'dimension': 'MRQ', 'reportperiod': '2026-07-30'}[drift]
        new[drift] = new['_acquisition_payload'][drift] = value
    comparison = p.compare_payload(old, new)
    assert comparison['reason'] != p.REPAIR
    altered = {**histories, 'ARQ': replace(histories['ARQ'], rows=(new,))}
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='PAYLOAD_REPAIR_'):
        repair(db, current, altered, [candidate(current, histories)])
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('problem', ['stale_hash', 'stale_payload', 'duplicate_selection', 'duplicate_source', 'incomplete_history', 'duplicate_stored_key', 'linked_evidence', 'reviewed_provenance'])
def test_repair_fails_closed_and_preserves_copy_on_invalid_selection(tmp_path, problem):
    db, current, histories = fixture(tmp_path)
    candidates = [candidate(current, histories)]
    if problem == 'stale_hash':
        candidates[0]['old_content_hash'] = 'wrong'
    elif problem == 'stale_payload':
        candidates[0]['comparison_fingerprint'] = 'wrong'
    elif problem == 'duplicate_selection':
        candidates.append(candidates[0])
    elif problem == 'duplicate_source':
        histories['ARQ'] = replace(histories['ARQ'], rows=histories['ARQ'].rows * 2)
    elif problem == 'incomplete_history':
        histories['ARQ'] = replace(histories['ARQ'], status='INCOMPLETE')
    elif problem == 'duplicate_stored_key':
        with sqlite3.connect(db) as c:
            old = source_row();_insert_legacy_version(c, old, 'duplicate')
    elif problem == 'linked_evidence':
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE retained_evidence(observation_id REFERENCES provider_observation(observation_id) ON DELETE CASCADE)')
            c.execute("INSERT INTO retained_evidence VALUES('old_ARQ')")
    elif problem == 'reviewed_provenance':
        with sqlite3.connect(db) as c:
            c.execute("UPDATE provider_observation SET provenance_json=? WHERE observation_id='old_ARQ'",
                      (json.dumps({"reviewed": True}),))
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='PAYLOAD_REPAIR_'):
        repair(db, current, histories, candidates)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_shared_max_versions_with_different_payload_values_are_ambiguous(tmp_path):
    db, current, histories = fixture(tmp_path)
    with sqlite3.connect(db) as c:
        r = source_row();_insert_legacy_version(c, r, 'duplicate')
        c.execute('UPDATE provider_observation SET payload_json=? WHERE observation_id=?',
                  (json.dumps({**r, 'sharefactor': .5}), 'duplicate'))
    loaded = f.load_current_history(db, 'TEST', 'ARQ')
    assert loaded['legacy_source_version_ambiguities']
    assert f.compare_ticker_histories('TEST', {**current, 'ARQ': loaded}, histories)['classification'] == 'REVIEW_REQUIRED'


def test_current_payload_change_is_bound_even_if_financials_equal(tmp_path):
    _, current, histories = fixture(tmp_path)
    first = f.compare_ticker_histories('TEST', current, histories)
    rows = [deepcopy(histories['ARQ'].rows[0])]
    rows[0]['_acquisition_payload']['sharefactor'] = None
    later = f.compare_ticker_histories('TEST', current, {**histories, 'ARQ': replace(histories['ARQ'], rows=tuple(rows))})
    assert first['source_effective_fingerprint'] == later['source_effective_fingerprint']
    assert f.refresh_binding_change(first) != f.refresh_binding_change(later)


def test_payload_fingerprint_preserves_every_source_key():
    assert p.payload_fingerprint({'run_id': 'one'}) != p.payload_fingerprint({'run_id': 'two'})
    assert p.completeness({'run_id': None}) != p.completeness({})


@pytest.mark.parametrize('kind', ['interpretation', 'context'])
def test_reviewed_provider_state_is_never_repaired(tmp_path, monkeypatch, kind):
    from rawcandle.fundamentals.admin import accounting_boundary_review as boundary
    db, current, histories = fixture(tmp_path)
    if kind == 'interpretation':
        monkeypatch.setattr(boundary, 'interpretation', lambda *a: {'resolution_id': 'reviewed'})
    else:
        monkeypatch.setattr(boundary, 'current_context', lambda *a: {'accounting_role': 'reviewed'})
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='PAYLOAD_REPAIR_REVIEWED'):
        repair(db, current, histories)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('field', ['company_id', 'security_id', 'provider_security_id'])
def test_source_company_security_identity_cannot_drift(tmp_path, field):
    db, current, histories = fixture(tmp_path)
    row = deepcopy(histories['ARQ'].rows[0])
    row['_acquisition_payload'][field] = 'different'
    histories['ARQ'] = replace(histories['ARQ'], rows=(row,))
    assert p.compare_payload(current['ARQ']['rows'][0], row)['reason'] == 'SOURCE_PAYLOAD_IDENTITY_MISMATCH'
    with pytest.raises(ValueError, match='PAYLOAD_REPAIR_NOT_COMPATIBLE'):
        repair(db, current, histories)
