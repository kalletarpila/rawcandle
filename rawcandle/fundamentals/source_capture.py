"""Provider acquisition integrity; raw evidence is never a normalized projection.

Only acquisition boundaries create captured records. JSON wire transport carries
one raw object and a compact envelope; persistence stores the envelope alongside
that raw object in provider_observation.provenance_json. Legacy accepted evidence
is readable, but cannot independently attest a new acquisition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from collections.abc import Mapping
import csv
import hashlib
import io
import json
import zipfile

VERSION = 'PROVIDER_PAYLOAD_COMPLETENESS_V1'
ACTIVE = True  # Future authoritative ingestion; accepted legacy evidence remains grandfathered.
UNVERIFIED = 'SOURCE_PAYLOAD_CAPTURE_UNVERIFIED'
INCOMPLETE = 'SOURCE_PAYLOAD_INCOMPLETE'
BASE = 'BASE_FINANCIAL_SOURCE'
PB = 'PB_OWNERSHIP_SOURCE'
FREEZE = 'HISTORICAL_FREEZE_SOURCE'
REPAIR = 'PAYLOAD_REPAIR_SOURCE'
TEXT_FIELDS = frozenset(('ticker','dimension','date','reportperiod','calendardate','fiscalperiod','lastupdated'))
SF1_FIELDS = frozenset('''accoci assets assetsavg assetsc assetsnc assetturnover bvps calendardate capex cashneq cashnequsd consolinc cor currentratio date de debt debtc debtnc debtusd deferredrev depamor deposits dimension divyield dps ebit ebitda ebitdamargin ebitdausd ebitusd ebt eps epsdil epsusd equity equityavg equityusd ev evebit evebitda fcf fcfps fiscalperiod fxusd gp grossmargin intangibles intexp invcap invcapavg inventory investments investmentsc investmentsnc lastupdated liabilities liabilitiesc liabilitiesnc marketcap ncf ncfbus ncfcommon ncfdebt ncfdiv ncff ncfi ncfinv ncfo ncfx netinc netinccmn netinccmnusd netincdis netincnci netmargin opex opinc payables payoutratio pb pe pe1 ppnenet prefdivis price ps ps1 receivables reportperiod retearn revenue revenueusd rnd roa roe roic ros sbcomp sgna sharefactor sharesbas shareswa shareswadil sps tangibles taxassets taxexp taxliabilities tbvps ticker workingcapital'''.split())
NUMERIC_FIELDS = SF1_FIELDS - TEXT_FIELDS
_NULL_NUMERIC = frozenset(('', 'None', 'NULL', 'null'))
_BOUNDARY = object()


class CaptureError(ValueError):
    def __init__(self, reason, details):
        self.reason = reason
        self.details = details
        super().__init__(reason)


class CapturedRecord(dict):
    """Raw provider keys only; provenance is deliberately a separate attribute."""
    def __init__(self, raw, envelope, *, _boundary):
        if _boundary is not _BOUNDARY:
            raise ValueError(UNVERIFIED)
        super().__init__(raw)
        self.capture = envelope


def digest(value):
    from .admin.provider_payload import payload_fingerprint
    return payload_fingerprint(value)


def seal(value):
    return {**value, 'capture_fingerprint': digest(value)}


def numeric_null(value):
    return value is None or (isinstance(value, str) and value.strip() in _NULL_NUMERIC)


def field_state(raw, field):
    if field not in raw:
        return 'ABSENT'
    if raw[field] is None or (field in NUMERIC_FIELDS and numeric_null(raw[field])):
        return 'EXPLICIT_NULL'
    return 'VALUE'


def _usable(value, numeric):
    if numeric:
        if isinstance(value, bool) or numeric_null(value):
            return False
        try:
            return Decimal(str(value).strip()).is_finite()
        except (InvalidOperation,ValueError,TypeError):
            return False
    return value is not None and bool(str(value).strip())


def projection(raw):
    # Use native normalization, never substitute provider values. Nonquarterly
    # retained dimensions use the same numeric parser without inventing Q labels.
    from .admin.refresh_fundamentals import normalize_source_row, REFRESH_REQUEST_FIELDS, _normalize_number
    if str(raw.get('dimension','')).upper() in ('ARQ','MRQ'):
        return normalize_source_row(raw)
    return {k: (str(raw[k]).strip().upper() if k in ('ticker','dimension','fiscalperiod') and raw.get(k) is not None
                else raw.get(k) if k in TEXT_FIELDS else _normalize_number(raw.get(k),k))
            for k in REFRESH_REQUEST_FIELDS}


def definitions(profile):
    from .admin.refresh_fundamentals import REFRESH_REQUEST_FIELDS
    base=set(REFRESH_REQUEST_FIELDS)
    keys={BASE:base, PB:base|{'sharefactor','equity','equityusd','price','marketcap','pb'},
        FREEZE:base|{'equity','equityusd','sharefactor'},REPAIR:set(SF1_FIELDS)}[profile]
    usable=set(TEXT_FIELDS)
    if profile==PB:
        usable|={'sharefactor','sharesbas','equity','equityusd','price','marketcap','pb'}
    return keys, usable


def raw_payload(row):
    if isinstance(row,CapturedRecord):
        return dict(row)
    if isinstance(row.get('_acquisition_payload'),Mapping) and (row.get('_capture_transport')==VERSION or row.get('_provider_observation_id')):
        return dict(row['_acquisition_payload'])
    return dict(row)


def envelope(row):
    if isinstance(row,CapturedRecord):return row.capture
    return row.get('_capture_envelope') if row.get('_capture_transport')==VERSION else None


def wire(row):
    """Serialize capture metadata without duplicating the complete raw payload."""
    raw=raw_payload(row);proof=envelope(row)
    if proof is None:return dict(row)
    from .admin.refresh_fundamentals import REFRESH_REQUEST_FIELDS
    return {**{k:raw[k] for k in (*REFRESH_REQUEST_FIELDS,'permaticker') if k in raw},
        '_acquisition_payload':raw,'_capture_envelope':proof,'_capture_transport':VERSION}


def _envelope(raw, *, origin, acquired_at):
    from .admin.refresh_fundamentals import HistoryValidationError
    try:
        normal=digest(projection(raw));error=None
    except (ValueError,TypeError,HistoryValidationError):
        normal=None;error=INCOMPLETE
    from .admin.refresh_fundamentals import REFRESH_REQUEST_FIELDS
    # A successful endpoint alone must not relabel the known reduced projection.
    projected=set(raw).issubset(set(REFRESH_REQUEST_FIELDS)|{'permaticker','observation_id'})
    relevant=set().union(*(definitions(p)[0] for p in (BASE,PB,FREEZE)))
    value=dict(policy=VERSION,authoritative_acquisition=True,acquisition_source=origin,
        acquired_at_utc=acquired_at,raw_payload_fingerprint=digest(raw),
        raw_key_set_fingerprint=digest(sorted(raw)),raw_key_state_fingerprint=digest({k:field_state(raw,k) for k in sorted(raw)}),
        normalized_projection_fingerprint=normal,projection_contract='NATIVE_SHARADAR_FINANCIAL_V1',
        required_profile_field_states={k:field_state(raw,k) for k in sorted(relevant)},
        raw_key_count=len(raw),source_identity={k:raw.get(k) for k in TEXT_FIELDS},
        full_capture_shape_verified=not projected,eligible_authoritative_full_source=not projected and error is None)
    return seal(value)


def _http_records(records, *, endpoint, parameters, acquired_at, base_url, response_sha256):
    """Called only by the native successful unprojected HTTP response boundary."""
    if base_url!='https://api.sharadar.com/v1.0' or endpoint not in ('/data/fundamentals','/data/SF1') or any(k in parameters for k in ('fields','columns','select')):
        return records
    origin=dict(provider='SHARADAR',kind='FULL_HTTP_RESPONSE',endpoint=endpoint,
                request_fingerprint=digest(parameters),source_path=base_url+endpoint,response_sha256=response_sha256,status='SUCCESS')
    return [CapturedRecord(r,_envelope(r,origin=origin,acquired_at=acquired_at),_boundary=_BOUNDARY) for r in records]


def profile_report(row, profile, *, capture=None, legacy_accepted=False):
    from .admin.refresh_fundamentals import HistoryValidationError
    raw=raw_payload(row) if capture is None else dict(row)
    cap=envelope(row) if capture is None else capture
    keys,usable=definitions(profile)
    missing=sorted(keys-set(raw));nulls=sorted(k for k in keys if field_state(raw,k)=='EXPLICIT_NULL')
    unusable=sorted(k for k in usable if field_state(raw,k)!='VALUE' or not _usable(raw.get(k),k in NUMERIC_FIELDS))
    try:
        raw_projection=projection(raw);projection_error=None
    except (ValueError,TypeError,HistoryValidationError) as error:
        raw_projection=None;projection_error=str(error)
    verified=False
    if isinstance(cap,Mapping):
        try:
            origin=cap.get('acquisition_source') or {}
            timestamp=datetime.fromisoformat(cap['acquired_at_utc'].replace('Z','+00:00'))
            from .admin.refresh_fundamentals import REFRESH_REQUEST_FIELDS
            wire_matches=(capture is not None or isinstance(row,CapturedRecord) or not isinstance(row.get('_acquisition_payload'),Mapping)
                or (raw_projection is not None and projection(row)==raw_projection and
                    all(k in raw and row[k]==raw[k] for k in row if not str(k).startswith('_') and k not in REFRESH_REQUEST_FIELDS)))
            verified=(wire_matches and cap.get('policy')==VERSION and cap.get('capture_fingerprint')==digest({k:v for k,v in cap.items() if k!='capture_fingerprint'})
                and cap.get('authoritative_acquisition') is True and cap.get('full_capture_shape_verified') is True
                and timestamp.tzinfo is not None and origin.get('provider')=='SHARADAR' and origin.get('status')=='SUCCESS'
                and origin.get('kind') in ('FULL_HTTP_RESPONSE','VERIFIED_BULK_CSV','VERIFIED_ARCHIVE_REPLAY')
                and origin.get('endpoint') in ('/data/fundamentals','/data/SF1')
                and (origin.get('kind')!='FULL_HTTP_RESPONSE' or (origin.get('source_path')=='https://api.sharadar.com/v1.0'+origin.get('endpoint')
                    and len(origin.get('response_sha256') or '')==64 and len(origin.get('request_fingerprint') or '')==64))
                and cap['raw_payload_fingerprint']==digest(raw) and cap['raw_key_set_fingerprint']==digest(sorted(raw))
                and cap['raw_key_state_fingerprint']==digest({k:field_state(raw,k) for k in sorted(raw)})
                and cap['normalized_projection_fingerprint']==(digest(raw_projection) if raw_projection is not None else None)
                and cap.get('raw_key_count')==len(raw)
                and cap.get('projection_contract')=='NATIVE_SHARADAR_FINANCIAL_V1'
                and cap.get('source_identity')=={k:raw.get(k) for k in TEXT_FIELDS}
                and cap['required_profile_field_states']=={k:field_state(raw,k) for k in set().union(*(definitions(p)[0] for p in (BASE,PB,FREEZE)))})
        except (ValueError,TypeError,KeyError,AttributeError,HistoryValidationError):verified=False
    reason=None if verified else UNVERIFIED
    if verified and (missing or unusable or projection_error):reason=INCOMPLETE
    metadata=cap if isinstance(cap,Mapping) else {}
    existing=legacy_accepted and cap is None and not missing and not unusable and not projection_error
    return dict(policy=VERSION,profile=profile,reason=reason,missing_keys=missing,explicit_null_keys=nulls,
        unusable_fields=unusable,capture_verified=verified,
        capture_status='VERIFIED_FULL_CAPTURE' if verified else 'LEGACY_ACCEPTED_UNATTESTED' if existing else 'UNVERIFIED',
        eligible_authoritative_full_source=verified and reason is None,
        eligible_existing_accepted_use=existing or (verified and reason is None),
        raw_payload_fingerprint=digest(raw),normalized_projection_fingerprint=metadata.get('normalized_projection_fingerprint'),
        capture_provenance=metadata.get('acquisition_source'),capture_fingerprint=cap.get('capture_fingerprint') if isinstance(cap,Mapping) else None)



def review_report(report):
    """Bind review decisions to row evidence, not a later HTTP capture time.

    Fresh acquisitions are verified independently. Request/response-wide hashes
    and the timestamped capture seal remain in provider provenance, while the
    review binds exact raw/projection fingerprints, profile and verified status.
    This is presentation/binding evidence, never an acquisition envelope.
    """
    result={k:v for k,v in report.items() if k!='capture_fingerprint'}
    origin=result.get('capture_provenance')
    if isinstance(origin,Mapping):
        result['capture_provenance']={k:origin.get(k) for k in ('provider','kind','endpoint','source_path','status')}
    return result


def binding_row(row, profile=BASE):
    if row is None:return None
    result=dict(row)
    if envelope(row) is not None:
        result.pop('_capture_envelope',None)
        result.pop('_capture_transport',None)
        result['_source_capture_binding']=review_report(profile_report(row,profile))
    return result


def review_row(row):
    return binding_row(row, FREEZE)


def require(row, profile=BASE):
    result=profile_report(row,profile)
    if not result['eligible_authoritative_full_source']:
        raise CaptureError(result['reason'],result)
    return envelope(row)


def guard(row, profile=BASE):
    return require(row,profile) if ACTIVE else envelope(row)


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def archive_records(path, manifest_path=None, *, tickers=None):
    """Read complete raw rows from a checksum-bound managed provider artifact.

    Manifestless arbitrary CSV/ZIP files cannot attest acquisition. Download and
    archive manifests bind original bytes and unprojected upstream request scope.
    """
    path=Path(path);mp=Path(manifest_path) if manifest_path else path.parent/'archive_manifest.json'
    if not mp.is_file():raise CaptureError(UNVERIFIED,dict(source=str(path),reason='ACQUISITION_MANIFEST_REQUIRED'))
    manifest=json.loads(mp.read_text());expected=manifest.get('sha256') or manifest.get('extraction_sha256') or manifest.get('payload_sha256')
    endpoint=manifest.get('endpoint') or str(manifest.get('upstream_request_scope') or '')
    if not expected or _sha(path)!=expected or '/data/fundamentals' not in endpoint or 'fields=' in endpoint:
        raise CaptureError(UNVERIFIED,dict(source=str(path),reason='ACQUISITION_MANIFEST_MISMATCH'))
    acquired=manifest.get('acquired_at_utc') or manifest.get('downloaded_at_utc')
    origin=dict(provider='SHARADAR',kind='VERIFIED_ARCHIVE_REPLAY' if 'sha256' in manifest else 'VERIFIED_BULK_CSV',
        endpoint='/data/fundamentals',status='SUCCESS',artifact_sha256=expected,manifest_fingerprint=digest(manifest),source_path=str(path.resolve()))
    def read(handle):
        for row in csv.DictReader(handle):
            if tickers is None or str(row.get('ticker') or '').strip().upper() in tickers:
                yield CapturedRecord(row,_envelope(row,origin=origin,acquired_at=acquired),_boundary=_BOUNDARY)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            members=[n for n in z.namelist() if n.lower().endswith('.csv')]
            if len(members)!=1:raise CaptureError(UNVERIFIED,dict(reason='AMBIGUOUS_ARCHIVE_MEMBER'))
            with z.open(members[0]) as f:
                yield from read(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
    else:
        with path.open(encoding='utf-8-sig',newline='') as f:yield from read(f)
