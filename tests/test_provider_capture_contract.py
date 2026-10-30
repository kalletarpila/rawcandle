"""Canonical field states, capture integrity, bounded profiles and raw round trips."""
from copy import deepcopy
from pathlib import Path
import json,sqlite3
import pytest
from rawcandle.fundamentals import source_capture as cap
from rawcandle.fundamentals.admin import provider_payload as payload,refresh_fundamentals as refresh
from rawcandle.fundamentals.schema.prototype import int_or_none
from tests.provider_capture_fixtures import acquired,full_row
from tests.test_fundamentals_admin_refresh_copy_test import source_row


@pytest.fixture(autouse=True)
def active(monkeypatch):monkeypatch.setattr(cap,'ACTIVE',True)


def raw():
    return full_row({**source_row(ticker='AAA'), 'sharefactor':1,'sharesbas':100,'equity':500,
        'equityusd':500,'price':10,'marketcap':1000,'pb':2})


@pytest.mark.parametrize('field,value,state',[
    ('sharefactor',None,'EXPLICIT_NULL'),('sharefactor','','EXPLICIT_NULL'),('sharefactor','  ','EXPLICIT_NULL'),
    ('sharefactor','NULL','EXPLICIT_NULL'),('sharefactor',0,'VALUE'),('sharefactor','0','VALUE'),
    ('sharefactor',1,'VALUE'),('sharefactor','1','VALUE'),('sharefactor','0.125','VALUE'),
    ('unknown_text','','VALUE'),('unknown_text','null','VALUE'),('unknown_extra',{'a':1},'VALUE'),
])
def test_canonical_states_do_not_guess_or_globally_reinterpret_text(field,value,state):
    row={field:value};before=deepcopy(row)
    assert cap.field_state(row,field)==state==payload.field_state(row,field)
    assert cap.field_state({},field)=='ABSENT'
    assert row==before


def test_native_numeric_acceptance_agrees_for_null_and_zero():
    for value in (None,'','  ','NULL','null','None'):
        assert refresh._normalize_number(value,'revenue') is None
        assert int_or_none(value) is None
    for value in (0,'0',1,'1'):
        assert cap.field_state({'revenue':value},'revenue')=='VALUE'
        assert refresh._normalize_number(value,'revenue')==int_or_none(value)==int(value)


def test_full_source_and_projection_stay_distinct_unknown_fields_roundtrip():
    r=raw();r['_future_provider_object']={'unknown':[1,None,'']};r['future_metric']=None
    captured=acquired([r],full=False)[0]
    assert isinstance(captured,cap.CapturedRecord) and dict(captured)==r
    wire=cap.wire(captured);assert cap.raw_payload(wire)==r
    loaded=json.loads(json.dumps(wire));proof=cap.require(loaded,cap.REPAIR)
    assert proof==captured.capture
    assert proof['raw_payload_fingerprint']==payload.payload_fingerprint(r)
    assert proof['normalized_projection_fingerprint']==payload.payload_fingerprint(refresh.normalize_source_row(r))
    assert cap.raw_payload(loaded)['_future_provider_object']==r['_future_provider_object']


@pytest.mark.parametrize('operation',[cap.BASE,cap.PB,cap.FREEZE,cap.REPAIR])
def test_projected_dictionary_never_attests_full_source(operation):
    captured=acquired([raw()],full=False)[0]
    reduced=refresh.normalize_source_row(captured)
    assert len(reduced)==29
    with pytest.raises(cap.CaptureError,match=cap.UNVERIFIED):cap.require(reduced,operation)
    assert cap.envelope(reduced) is None
    # Even a successful unprojected endpoint cannot bless the known projection.
    projected=acquired([reduced],full=False)[0]
    with pytest.raises(cap.CaptureError):cap.require(projected,operation)


def test_discovery_projection_does_not_receive_full_capture():
    projected=acquired([raw()],full=False,fields=['ticker','lastupdated'])[0]
    assert not isinstance(projected,cap.CapturedRecord)
    with pytest.raises(cap.CaptureError,match=cap.UNVERIFIED):cap.require(projected)


@pytest.mark.parametrize('mutation',['raw','keyset','capture','projection','wire','origin'])
def test_capture_tampering_is_rejected(mutation):
    wire=json.loads(json.dumps(cap.wire(acquired([raw()],full=False)[0])))
    if mutation=='raw':wire['_acquisition_payload']['sharefactor']=2
    elif mutation=='keyset':wire['_acquisition_payload'].pop('equity')
    elif mutation=='capture':wire['_capture_envelope']['acquired_at_utc']='changed'
    elif mutation=='projection':wire['_capture_envelope']['normalized_projection_fingerprint']='other'
    elif mutation=='wire':wire['revenue']=999
    elif mutation=='origin':wire['_capture_envelope']['acquisition_source']['kind']='LOCAL_NORMALIZED_ROW'
    with pytest.raises(cap.CaptureError):cap.require(wire)


def test_profiles_separate_presence_null_and_usable_values():
    r=raw();r.pop('sharefactor');captured=acquired([r],full=False)[0]
    assert cap.require(captured,cap.BASE)
    for profile in (cap.PB,cap.FREEZE,cap.REPAIR):
        report=cap.profile_report(captured,profile)
        assert report['reason']==cap.INCOMPLETE and 'sharefactor' in report['missing_keys']
    r=raw();r['sharefactor']='';r['equityusd']=None;captured=acquired([r],full=False)[0]
    assert cap.require(captured,cap.BASE) and cap.require(captured,cap.FREEZE) and cap.require(captured,cap.REPAIR)
    report=cap.profile_report(captured,cap.PB)
    assert report['reason']==cap.INCOMPLETE and set(report['unusable_fields'])=={'sharefactor','equityusd'}
    assert cap.raw_payload(captured)['sharefactor']==''


def test_legacy_readability_is_not_new_full_capture_authority():
    r=raw();report=cap.profile_report(r,cap.BASE,legacy_accepted=True)
    assert report['capture_status']=='LEGACY_ACCEPTED_UNATTESTED'
    assert report['eligible_existing_accepted_use'] and not report['eligible_authoritative_full_source']
    with pytest.raises(cap.CaptureError):cap.require(r)
    old={k:'NULL' if v is None else 'VALUE' for k,v in r.items()}
    proof=dict(key_states=old,key_count=len(old),completeness_fingerprint=payload.payload_fingerprint(old),payload_fingerprint=payload.payload_fingerprint(r))
    assert payload.matches_completeness(proof,r)
    assert proof!=payload.completeness(r)


def test_refresh_validation_requires_capture_and_keeps_technical_reason():
    captured=acquired([raw()],full=False)[0]
    trust=refresh.validate_complete_history([captured],ticker='AAA',dimension='ARQ')
    assert trust.status=='COMPLETE' and cap.require(trust.rows[0])
    trust=refresh.validate_complete_history([refresh.normalize_source_row(raw())],ticker='AAA',dimension='ARQ')
    assert trust.status=='INCOMPLETE' and trust.capture_failures[0]['reason']==cap.UNVERIFIED
    assert trust.evidence()['source_capture_failures'][0]['profile']==cap.BASE
