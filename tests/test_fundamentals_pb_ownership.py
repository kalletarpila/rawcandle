"""Reviewed ownership rules, adversarial evidence bindings and reporting isolation."""
from copy import deepcopy
import json

import pytest

from rawcandle.fundamentals import ownership_basis as ownership
from rawcandle.fundamentals.book_value import current_pb, provider_reference, book_value_report
from rawcandle.fundamentals.schema.parent_equity import migrate_parent_equity
from rawcandle.fundamentals.snapshot.renderer import _book_value_sections
from tests.test_fundamentals_pb_reporting import ordinary, sources


@pytest.fixture
def review(monkeypatch):
    r = deepcopy(next(r for r in ownership.ownership_reviews() if r['release_type']=='ORDINARY_COMMON'))
    r.update(company_id=1000000,security_id=1000001,company_key='fixture',canonical_ticker='UNIT',
             observation_id='accepted',content_hash='hash',accepted_sharesbas=100,
             provider_declared_factor=1,share_source_date='2026-08-01',unit_effective_from='2026-08-01')
    monkeypatch.setattr(ownership,'ownership_reviews',lambda:(r,))
    return r


def row_for(r):
    return ordinary() | {k:r[k] for k in ownership.BINDING}


def calc(row,**kw):
    return current_pb(row,as_of=kw.pop('as_of','2026-10-07'),
        price=kw.pop('price',dict(pvm='2026-10-06',close=20)),
        category=kw.pop('category','Domestic Common Stock Primary Class'),active_classes=kw.pop('active_classes',1))


def test_primary_class_review_release_and_immutable_diagnostics(review):
    row=row_for(review);before=deepcopy(row)
    a=calc(row); assert a['value']==2 and row==before
    assert a['ownership_basis']['contract']=='PB_OWNERSHIP_BASIS_V1'
    assert a['ownership_basis']['share_source_date']=='2026-08-01'
    assert a['ownership_basis']['provider_declared_factor']==1
    assert calc(row)==a
    a['ownership_basis']['evidence_urls'].append('tampered')
    assert calc(row)['ownership_basis']['evidence_urls']==review['evidence_urls']
    text='\n'.join(_book_value_sections({'book_value':dict(current=calc(row),provider=provider_reference(row),history=[],caveat='parent')}))
    assert 'Ownership basis' in text and 'Reviewed' in text and 'Share source date' in text


def test_reviewed_direct_common_identity_override(review):
    review.update(identity_override=True,release_type='IDENTITY_OVERRIDE')
    row=row_for(review)|{'ownership_conflict':True}
    assert calc(row,category='ADR Common Stock')['value']==2
    assert calc(row,category='ADR Common Stock')['ownership_basis']['identity_override'] is True
    assert row['ownership_conflict'] is True


@pytest.mark.parametrize('declared,denominator',[(.333,3),(.077,13),(0,40000),(None,5)])
def test_exact_ads_conversion_requires_independent_review(review,declared,denominator,monkeypatch):
    review.update(economic_unit_rule='ADS_EQUIVALENTS',reviewed_security_type='ADS',
                  exact_factor_numerator=1,exact_factor_denominator=denominator,
                  provider_declared_factor=declared,release_type='ADR_FACTOR')
    row=row_for(review)|dict(sharefactor=declared,marketcap=1000/denominator,pb=1/denominator)
    before=deepcopy(row); p=provider_reference(row)
    result=calc(row,category='ADR Common Stock')
    assert result['value']==pytest.approx(2/denominator)
    assert result['ownership_basis']['reviewed_factor']==1/denominator
    assert result['ownership_basis']['provider_declared_factor']==declared
    assert row==before and provider_reference(row)==p
    monkeypatch.setattr(ownership,'ownership_reviews',lambda:())
    assert calc(row,category='ADR Common Stock')['reason']=='OWNERSHIP_BASIS_UNVERIFIED'


@pytest.mark.parametrize('field,value',[
    ('company_id',2000000),('company_key','other'),('security_id',2000001),
    ('canonical_ticker','OTHER'),('observation_id','new'),('content_hash','revised'),
    ('sharesbas',101),('sharefactor',.5)])
def test_review_cannot_transfer_binding(review,field,value):
    assert calc(row_for(review)|{field:value})['reason']=='OWNERSHIP_REVIEW_UNVERIFIED'


@pytest.mark.parametrize('change',[
    {'effective_from':'2026-10-08'}, {'effective_to':'2026-10-06'},
    {'share_source_date':'2026-10-07'}, {'share_source_date':'2026-03-01'},
    {'unit_effective_from':'2026-10-07'}, {'reviewed_at':'2026-10-08T00:00:00Z'}])
def test_review_dates_fail_closed(review,change):
    review.update(change)
    assert calc(row_for(review))['reason']=='OWNERSHIP_REVIEW_STALE'


def test_future_calculation_requires_new_review(review):
    assert calc(row_for(review),as_of='2026-10-08',price=dict(pvm='2026-10-08',close=20))['reason']=='OWNERSHIP_REVIEW_STALE'


@pytest.mark.parametrize('kind',['ISSUANCE','REPURCHASE','SPLIT','ADS_RATIO','CLASS_CHANGE'])
def test_known_intervening_action_requires_settled_new_base(review,kind):
    event=dict(effective_date='2026-09-01',kind=kind,reconciled=False)
    assert calc(row_for(review)|dict(ownership_share_changes=[event]))['reason']=='NEWER_SHARE_COUNT_REQUIRED'
    review['known_share_changes']=[event]
    assert calc(row_for(review))['reason']=='NEWER_SHARE_COUNT_REQUIRED'


@pytest.mark.parametrize('reason',['NEWER_SHARE_COUNT_REQUIRED','MULTI_CLASS_UNVERIFIED','OWNERSHIP_BASIS_UNVERIFIED'])
def test_reviewed_newer_multiclass_treasury_holds(review,reason):
    review.update(evidence_status='REVIEWED_HOLD',economic_unit_rule='HOLD',hold_reason=reason)
    assert calc(row_for(review))['reason']==reason


def test_invalid_ratio_and_active_classes_are_not_bypassed(review):
    review.update(economic_unit_rule='ADS_EQUIVALENTS',reviewed_security_type='ADS',exact_factor_numerator=1,exact_factor_denominator=0)
    assert calc(row_for(review))['reason']=='ADR_FACTOR_UNVERIFIED'
    review.update(economic_unit_rule='ORDINARY_COMMON')
    review['reviewed_security_type']='COMMON_OR_ORDINARY'
    assert calc(row_for(review),active_classes=2)['reason']=='OWNERSHIP_BASIS_UNVERIFIED'


@pytest.mark.parametrize('price,reason',[(None,'MISSING_PRICE'),(dict(pvm='2026-10-08',close=20),'MISSING_PRICE'),(dict(pvm='2026-10-03',close=20),'STALE_PRICE')])
def test_review_does_not_relax_price_gates(review,price,reason):
    assert calc(row_for(review),price=price)['reason']==reason


def test_actual_price_contradiction_and_share_provenance_remain_hard(review):
    assert calc(row_for(review)|{'provider_date_market_close':20})['reason']=='SHARE_BASIS_UNVERIFIED'
    assert calc(row_for(review)|{'shares_outstanding':101})['reason']=='SHARE_BASIS_UNVERIFIED'


def test_reviewed_report_provider_history_rebuild_and_invalid_current_ohlc(sources,review):
    import sqlite3
    cp,pp,mp=sources
    migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    with sqlite3.connect(cp) as c,sqlite3.connect(mp) as m:
        c.row_factory=m.row_factory=sqlite3.Row
        before=book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
        review.update(company_id=1,company_key='fixture-company',security_id=1,canonical_ticker='TEST',observation_id='1',content_hash='hash1')
        c.execute("UPDATE v4_parent_equity_source SET category='Domestic Common Stock Primary Class' WHERE quarter_id=1")
        candidate=book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
        assert candidate['current']['value']==2 and 'ownership_basis' in candidate['current']
        assert candidate['provider']==before['provider'] and candidate['history']==before['history']
        assert candidate==book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
        m.execute("UPDATE osakedata SET high=1 WHERE pvm='2026-10-06'")
        assert book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')['current']['reason']=='STALE_PRICE'


@pytest.mark.parametrize('change',[{'security_valid_from':'2026-10-08'},{'security_valid_to':'2026-10-06'}])
def test_canonical_security_validity_cannot_be_bypassed(review,change):
    assert calc(row_for(review)|change)['reason']=='OWNERSHIP_REVIEW_UNVERIFIED'


def test_reconciled_boolean_does_not_prove_updated_settled_shares(review):
    event=dict(effective_date='2026-09-01',kind='ISSUANCE',reconciled=True)
    assert calc(row_for(review)|dict(ownership_share_changes=[event]))['reason']=='NEWER_SHARE_COUNT_REQUIRED'
