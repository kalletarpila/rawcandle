"""Quarter-bound V2, immutable V1, explicit activation and normal refresh integration."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals import ownership_basis as ownership, phase12d
from rawcandle.fundamentals.book_value import book_value_report, current_pb, provider_reference, QUARTERLY_DISCLOSURE
from rawcandle.fundamentals.pb_reporting_contract import (
    activate_quarterly_ownership, reporting_ownership_contract, TABLE,
)
from rawcandle.fundamentals.schema.parent_equity import migrate_parent_equity
from rawcandle.fundamentals.snapshot.renderer import _book_value_sections
from tests.test_fundamentals_pb_reporting import ordinary, sources
from tests.test_phase12d_operational_rebuild import _databases, _row, _insert

V2 = ownership.QUARTERLY_OWNERSHIP_CONTRACT


@pytest.fixture
def review(monkeypatch):
    r = deepcopy(next(r for r in ownership.ownership_reviews_v2() if r['release_type'] == 'ORDINARY_COMMON'))
    r.update(company_id=1000000, security_id=1000001, company_key='fixture', canonical_ticker='UNIT',
             observation_id='accepted', content_hash='hash', accepted_sharesbas=100,
             provider_declared_factor=1, share_source_date='2026-08-01', unit_effective_from='2026-08-01',
             fiscal_year=2026, fiscal_quarter='Q2', reportperiod='2026-06-30',
             accepted_category='Domestic Common Stock Primary Class',
             accepted_provider_date='2026-08-01', accepted_source_availability_date='2026-08-01')
    monkeypatch.setattr(ownership, 'ownership_reviews_v2', lambda: (r,))
    return r


def row_for(r):
    return ordinary() | {k: r[k] for k in ownership.BINDING} | {'category': r['accepted_category']}


def calc(row, *, as_of='2026-10-08', close=20, active_classes=1, price_date=None):
    return current_pb(row, as_of=as_of, price=dict(pvm=price_date or as_of, close=close),
                      category=row['category'], active_classes=active_classes, ownership_contract=V2)


@pytest.mark.parametrize('day', ['2026-10-08', '2026-10-09', '2026-10-30'])
def test_same_accepted_quarter_remains_eligible(review, day):
    original = deepcopy(review); row = row_for(review)
    a = calc(row, as_of=day)
    assert a['value'] == 2
    assert a['ownership_basis_status'] == 'OPERATOR_CONFIRMED_QUARTER'
    assert a['ownership_basis']['economic_units'] == 100
    assert review == original and calc(row, as_of=day) == a
    a['ownership_basis']['evidence_urls'].append('tampered')
    assert review == original


def test_daily_price_independent_and_no_separate_share_age_expiry(review):
    review.update(share_source_date='2026-04-01', unit_effective_from='2026-04-01')
    row = row_for(review)
    assert calc(row)['value'] == 2
    assert calc(row, as_of='2026-10-09', close=30)['value'] == 3
    assert calc(row, as_of='2026-10-09')['share_basis_date'] == '2026-04-01'


def test_identity_override_survives_later_date(review):
    review.update(identity_override=True, release_type='IDENTITY_OVERRIDE', accepted_category='ADR Common Stock')
    row = row_for(review) | {'ownership_conflict': True}
    assert calc(row, as_of='2026-10-09')['value'] == 2
    assert row['category'] == 'ADR Common Stock' and row['ownership_conflict'] is True


@pytest.mark.parametrize('declared,denominator', [(0.333, 3), (0.077, 13), (0, 40000)])
def test_exact_ads_ratio_and_raw_zero_preserved(review, declared, denominator):
    review.update(economic_unit_rule='ADS_EQUIVALENTS', reviewed_security_type='ADS',
                  exact_factor_numerator=1, exact_factor_denominator=denominator,
                  provider_declared_factor=declared, release_type='ADR_FACTOR', accepted_category='ADR Common Stock')
    row = row_for(review) | dict(sharefactor=declared, marketcap=1000/denominator, pb=1/denominator)
    before = deepcopy(row)
    assert calc(row, as_of='2026-10-09')['value'] == pytest.approx(2/denominator)
    assert calc(row)['ownership_basis']['reviewed_factor_ratio'] == dict(numerator=1, denominator=denominator)
    assert row == before
    assert calc(row_for(review) | dict(sharefactor=declared, observation_id='new'))['reason'] == 'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'


@pytest.mark.parametrize('changed', [dict(observation_id='new'), dict(content_hash='revised'),
                                     dict(fiscal_quarter='Q3'), dict(reportperiod='2026-09-30')])
def test_supersession_and_revision_require_explicit_new_review(review, changed):
    a = calc(row_for(review) | changed)
    assert a['reason'] == 'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'
    assert a['value'] is None and a['market_cap'] is None and 'ownership_basis' not in a


@pytest.mark.parametrize('changed', [dict(company_id=999), dict(company_key='other'), dict(security_id=999),
                                     dict(canonical_ticker='OTHER'), dict(sharesbas=101), dict(sharefactor=.5),
                                     dict(category='Other'), dict(provider_date='2026-08-02')])
def test_identity_count_factor_and_provenance_fail_closed(review, changed):
    assert calc(row_for(review) | changed)['reason'] == 'OWNERSHIP_REVIEW_UNVERIFIED'


@pytest.mark.parametrize('reason', ['MULTI_CLASS_UNVERIFIED', 'NEWER_SHARE_COUNT_REQUIRED', 'OWNERSHIP_BASIS_UNVERIFIED'])
def test_existing_explicit_holds_remain_held(review, reason):
    review.update(evidence_status='REVIEWED_HOLD', economic_unit_rule='HOLD', hold_reason=reason)
    assert calc(row_for(review), as_of='2026-10-09')['reason'] == reason


def test_multiclass_and_known_conflicts_are_not_released(review):
    assert calc(row_for(review), active_classes=2)['reason'] == 'OWNERSHIP_BASIS_UNVERIFIED'
    assert calc(row_for(review) | {'newer_share_count_required': True})['reason'] == 'NEWER_SHARE_COUNT_REQUIRED'
    assert calc(row_for(review) | {'ownership_share_changes': [dict(effective_date='2026-09-01', reconciled=True)]})['reason'] == 'NEWER_SHARE_COUNT_REQUIRED'


@pytest.mark.parametrize('change', [dict(share_source_date='2026-10-10'), dict(unit_effective_from='2026-10-10'),
                                     dict(valid_from_as_of='2026-10-10'), dict(reviewed_at='2026-10-10T00:00:00Z'),
                                     dict(approval_mode='CANDIDATE'), dict(evidence_urls=[])])
def test_dates_and_unapproved_evidence_fail_closed(review, change):
    review.update(change)
    assert calc(row_for(review))['reason'] == 'OWNERSHIP_REVIEW_UNVERIFIED'


def test_price_equity_hard_gates_unreviewed_cases_and_disclosure(review):
    row = row_for(review)
    assert calc(row, price_date='2026-10-04')['reason'] == 'STALE_PRICE'
    assert calc(row | dict(source_availability_date='2026-01-01'))['reason'] == 'STALE_EQUITY'
    assert calc(row | dict(provider_date_market_close=30))['reason'] == 'SHARE_BASIS_UNVERIFIED'
    result = calc(row)
    assert result['share_basis_fiscal_year'] == 2026 and result['share_basis_fiscal_quarter'] == 'Q2'
    assert result['share_basis_date'] == '2026-08-01' and result['price_date'] == '2026-10-08'
    text = '\n'.join(_book_value_sections({'book_value': dict(current=result, provider=provider_reference(row), history=[], caveat='parent')}))
    assert 'Share basis quarter' in text and 'Ownership basis status' in text and QUARTERLY_DISCLOSURE in text
    unreviewed = row | {k: 'unreviewed' for k in ownership.BINDING}
    assert calc(unreviewed)['reason'] == 'OWNERSHIP_BASIS_UNVERIFIED'
    unreviewed['category'] = 'Domestic Common Stock'
    assert calc(unreviewed)['ownership_basis_status'] == 'EXISTING_UNREVIEWED_COMMON_RULE'
    assert calc(unreviewed)['share_basis_date_basis'] == 'PROVIDER_FILING_DATE_PROXY'


def test_registry_migrates_only_existing_reviews_and_v1_is_immutable():
    v1 = Path(ownership.__file__).with_name('ownership_reviews_v1.json')
    assert hashlib.sha256(v1.read_bytes()).hexdigest() == '0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf'
    before, after = ownership.ownership_reviews(), ownership.ownership_reviews_v2()
    assert len(before) == len(after) == 63
    for a, b in zip(before, after):
        for key in (*ownership.BINDING, 'accepted_sharesbas', 'provider_declared_factor', 'release_type',
                    'exact_factor_numerator', 'exact_factor_denominator', 'evidence_status', 'hold_reason',
                    'share_source_date', 'evidence_urls'):
            assert a[key] == b[key]
    from collections import Counter
    assert Counter(r['release_type'] for r in after if r['evidence_status'] == 'REVIEWED_SUPPORTED') == {
        'ORDINARY_COMMON': 16, 'ADR_FACTOR': 6, 'IDENTITY_OVERRIDE': 9}


def test_activation_is_explicit_historical_v1_and_provider_history_unchanged(sources, review):
    cp, pp, mp = sources
    migrate_parent_equity(pp, cp, accepted_at='2026-10-08')
    review.update(company_id=1, company_key='fixture-company', security_id=1, canonical_ticker='TEST',
                  observation_id='1', content_hash='hash1', accepted_category='Domestic Common Stock')
    with sqlite3.connect(cp) as c, sqlite3.connect(mp) as m:
        c.row_factory = m.row_factory = sqlite3.Row
        old = book_value_report(c, m, company_id=1, ticker='TEST', as_of='2026-10-07')
        assert reporting_ownership_contract(c, as_of='2026-10-08') == ownership.OWNERSHIP_CONTRACT
    activate_quarterly_ownership(cp, effective_from='2026-10-08')
    activate_quarterly_ownership(cp, effective_from='2026-10-08')
    with sqlite3.connect(cp) as c, sqlite3.connect(mp) as m:
        c.row_factory = m.row_factory = sqlite3.Row
        assert book_value_report(c, m, company_id=1, ticker='TEST', as_of='2026-10-07') == old
        a = book_value_report(c, m, company_id=1, ticker='TEST', as_of='2026-10-08')
        assert a['current']['value'] == 2 and a['current']['ownership_contract'] == V2
        assert (a['provider'], a['history']) == (old['provider'], old['history'])
        c.execute(f"UPDATE {TABLE} SET review_artifact_sha256='tampered'")
        with pytest.raises(ValueError, match='ARTIFACT_MISMATCH'):
            reporting_ownership_contract(c, as_of='2026-10-08')
        assert reporting_ownership_contract(c, as_of='2026-10-07') == ownership.OWNERSHIP_CONTRACT
    with pytest.raises(ValueError, match='TOO_EARLY'):
        activate_quarterly_ownership(cp, effective_from='2026-10-07')
    with pytest.raises(ValueError, match='CONFLICT'):
        activate_quarterly_ownership(cp, effective_from='2026-10-09')


def test_activation_rejects_finalized_generations(tmp_path):
    db = tmp_path / 'canonical.db'; db.touch()
    (tmp_path / 'generation_manifest.json').write_text('{}')
    with pytest.raises(PermissionError, match='INACTIVE_COPY_REQUIRED'):
        activate_quarterly_ownership(db, effective_from='2026-10-08')


def test_normal_reconciliation_supersedes_review_and_operator_confirmed_new_q_restores(tmp_path, review):
    pp, cp, _ = _databases(tmp_path)
    def new_row(q, shares, equity, cap, day):
        r = _row(q)
        r.update(fiscalperiod=f'2026-Q{q}', reportperiod=f'2026-{ {2:"06-30",3:"09-30"}[q]}',
                 calendardate=f'2026-{ {2:"06-30",3:"09-30"}[q]}', date=day,
                 lastupdated=day, sharesbas=shares, sharefactor=1, equity=equity, equityusd=equity,
                 price=10, marketcap=cap, pb=cap/equity)
        return r
    _insert(pp, new_row(2, 100, 1000, 1000, '2026-08-01'))
    phase12d.reconcile_canonical(pp, cp, applied_at='2026-10-08')
    mp = tmp_path / 'market.db'
    with sqlite3.connect(mp) as m:
        m.executescript("CREATE TABLE ticker_meta(ticker,market); CREATE TABLE osakedata(osake,market,pvm,open,high,low,close);")
        m.executemany("INSERT INTO osakedata VALUES('AAA','usa',?,?,?,?,?)", [
            ('2026-08-01',10,11,9,10), ('2026-10-08',10,11,9,10), ('2026-10-09',20,21,19,20)])
    def latest():
        with sqlite3.connect(cp) as c:
            c.row_factory = sqlite3.Row
            return dict(c.execute('SELECT q.fiscal_year,q.fiscal_quarter,q.source_reportperiod AS reportperiod,s.* FROM v4_quarter q JOIN v4_parent_equity_source s USING(quarter_id) ORDER BY fiscal_year DESC,fiscal_quarter DESC LIMIT 1').fetchone())
    def bind(r, q):
        r.update(company_id=1, company_key='AAA', security_id=1, canonical_ticker='AAA',
                 **{k:q[k] for k in ('observation_id','content_hash','fiscal_year','fiscal_quarter','reportperiod')},
                 accepted_sharesbas=q['sharesbas'], provider_declared_factor=q['sharefactor'],
                 accepted_category=q['category'], accepted_provider_date=q['provider_date'],
                 accepted_source_availability_date=q['source_availability_date'], share_source_date=q['provider_date'],
                 unit_effective_from=q['provider_date'])
    bind(review, latest())
    activate_quarterly_ownership(cp, effective_from='2026-10-08')
    def report():
        with sqlite3.connect(cp) as c, sqlite3.connect(mp) as m:
            c.row_factory = m.row_factory = sqlite3.Row
            return book_value_report(c, m, company_id=1, ticker='AAA', as_of='2026-10-09')
    before = report(); assert before['current']['value'] == 2
    old_review = deepcopy(review)
    _insert(pp, new_row(3, 120, 2000, 1200, '2026-10-08'))
    phase12d.reconcile_canonical(pp, cp, applied_at='2026-10-09')
    held = report()
    assert held['current']['reason'] == 'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED'
    assert held['current']['market_cap'] is None and held['current']['parent_equity_usd'] == 2000
    assert held['provider']['value'] == .6 and held['history'][0]['fiscal_quarter'] == 'Q3'
    assert held['history'][1] == before['history'][0]
    bind(review, latest())  # Simulated explicit operator confirmation; refresh itself never writes reviews.
    restored = report()
    assert restored['current']['value'] == 1.2 and restored['current']['market_cap'] == 2400
    assert restored['current']['ownership_basis']['economic_units'] == 120
    assert restored['current']['price_date'] == '2026-10-09'
    assert old_review['accepted_sharesbas'] == 100
    assert (held['provider'], held['history']) == (restored['provider'], restored['history'])
    phase12d.reconcile_canonical(pp, cp, applied_at='2026-10-09')
    assert report() == restored


def test_explicit_candidate_repin_requires_expected_previous_artifact(tmp_path, monkeypatch):
    from rawcandle.fundamentals import pb_reporting_contract as config
    db = tmp_path / 'canonical.db'
    with sqlite3.connect(db):
        pass
    config.activate_quarterly_ownership(db, effective_from='2026-10-08')
    previous = config.ownership_reviews_v2_hash()
    monkeypatch.setattr(config, 'ownership_reviews_v2_hash', lambda: 'operator-reviewed-next-registry')
    with sqlite3.connect(db) as c:
        with pytest.raises(ValueError, match='ARTIFACT_MISMATCH'):
            config.reporting_ownership_contract(c, as_of='2026-10-09')
    with pytest.raises(ValueError, match='REPIN_CONFLICT'):
        config.repin_quarterly_reviews(db, expected_artifact_sha256='wrong')
    config.repin_quarterly_reviews(db, expected_artifact_sha256=previous)
    with sqlite3.connect(db) as c:
        assert config.reporting_ownership_contract(c, as_of='2026-10-09') == V2
        assert config.reporting_ownership_contract(c, as_of='2026-10-07') == ownership.OWNERSHIP_CONTRACT


@pytest.mark.parametrize('ticker', ['BIAF','BRCC','DBVT','GPMT','LEXX','NRDY','SEGG'])
def test_archived_local_hold_evidence_preserves_original_reason(ticker):
    r = next(r for r in ownership.ownership_reviews_v2() if r['canonical_ticker'] == ticker)
    row = {k:r[k] for k in (*ownership.BINDING,'fiscal_year','fiscal_quarter','reportperiod')}
    row.update(category=r['accepted_category'], provider_date=r['accepted_provider_date'],
               source_availability_date=r['accepted_source_availability_date'],
               sharesbas=r['accepted_sharesbas'], sharefactor=r['provider_declared_factor'])
    result = ownership.reviewed_ownership(row, as_of='2026-10-09', price_date='2026-10-08', contract=V2)
    assert result['reason'] == r['hold_reason'] and 'economic_units' not in result
