"""Rebuildable reporting-only parent book equity metrics; never a score input."""
from __future__ import annotations

import math
import sqlite3
from datetime import date
from typing import Any, Mapping

from rawcandle.fundamentals.schema.parent_equity import finite
from rawcandle.fundamentals.book_value_reviews import unresolved_basis_review
from rawcandle.fundamentals.ownership_basis import reviewed_ownership, OWNERSHIP_CONTRACT, QUARTERLY_OWNERSHIP_CONTRACT
from rawcandle.fundamentals.pb_reporting_contract import reporting_ownership_contract, reporting_ownership_records

CURRENT_CONTRACT = 'PB_CURRENT_PARENT_EQUITY_V1'
CURRENT_MODE = 'CURRENT_REVISED_REPORTING'
PROVIDER_MODE = 'PROVIDER_OBSERVATION_REFERENCE'
ROUNDING_TOLERANCE = 0.0005001
SHARE_AVERAGE_WARNING_DIFFERENCE = 0.25
EVIDENCE_MAX_DIFFERENCE = 0.01
CAVEAT = 'Parent equity attributable to parent shareholders as supplied by Sharadar; preferred-capital exclusion is not proven.'
QUARTERLY_DISCLOSURE = ('Current P/B uses the latest market price with the latest accepted quarterly share basis and parent equity. '
                        'Share changes after that quarterly basis may not yet be reflected.')


def provider_reference(row: Mapping[str, Any]) -> dict[str, Any]:
    equity, cap, pb = (finite(row.get(k)) for k in ('parent_equity_usd','marketcap','pb'))
    reason = 'OK'
    if equity is None:
        reason = 'MISSING_EQUITY'
    elif equity <= 0:
        reason = 'ZERO_EQUITY' if equity == 0 else 'NEGATIVE_EQUITY'
    elif cap is None or cap <= 0 or pb is None or pb <= 0:
        reason = 'PROVIDER_INPUTS_INVALID'
    elif abs(cap / equity - pb) > ROUNDING_TOLERANCE:
        reason = 'PROVIDER_PB_ARITHMETIC_MISMATCH'
    elif row.get('dimension') != 'ARQ' or not row.get('provider_date'):
        reason = 'PROVIDER_OBSERVATION_INVALID'
    return {k: row.get(k) for k in ('fiscal_year','fiscal_quarter','reportperiod','provider_date','observation_id','content_hash','source_availability_date','acceptance_rule')} | {
        'value': pb if reason == 'OK' else None, 'reason': reason,
        'semantic_mode': PROVIDER_MODE,
    }


def current_pb(row: Mapping[str, Any] | None, *, as_of: str, price: Mapping[str, Any] | None,
               category: str | None, active_classes: int,
               ownership_contract: str = OWNERSHIP_CONTRACT,
               review_records: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    if ownership_contract not in (OWNERSHIP_CONTRACT, QUARTERLY_OWNERSHIP_CONTRACT):
        raise ValueError('Unsupported ownership review contract')
    today = date.fromisoformat(as_of)
    r = dict(row or {})
    result = {'contract': CURRENT_CONTRACT, 'semantic_mode': CURRENT_MODE, 'role': 'REPORTING_ONLY',
              'as_of_date': as_of, 'value': None, 'status': 'NOT_AVAILABLE', 'reason': 'MISSING_EQUITY',
              'parent_equity': finite(r.get('parent_equity')), 'parent_equity_usd': finite(r.get('parent_equity_usd')),
              'equity_fiscal_year': r.get('fiscal_year'), 'equity_fiscal_quarter': r.get('fiscal_quarter'),
              'equity_reportperiod': r.get('reportperiod'), 'equity_source_availability_date': r.get('source_availability_date'),
              'price_date': price.get('pvm') if price else None, 'price': finite(price.get('close')) if price else None,
              'market_cap': None, 'warnings': [], 'caveat': CAVEAT}
    quarterly = ownership_contract == QUARTERLY_OWNERSHIP_CONTRACT
    if quarterly:
        result.update(ownership_contract=ownership_contract,
                      share_basis_fiscal_year=r.get('fiscal_year'), share_basis_fiscal_quarter=r.get('fiscal_quarter'),
                      share_basis_reportperiod=r.get('reportperiod'), share_basis_date=r.get('provider_date'),
                      share_basis_date_basis='PROVIDER_FILING_DATE_PROXY', ownership_basis_status='NOT_VALIDATED',
                      market_cap_semantics='CURRENT_PRICE_QUARTERLY_SHARE_BASIS_PROXY',
                      quarterly_basis_disclosure=QUARTERLY_DISCLOSURE)
    shares, avg = (finite(r.get(k)) for k in ('shares_outstanding', 'shareswa'))
    if shares is not None and shares > 0 and avg is not None and avg > 0:
        if abs(shares / avg - 1) > SHARE_AVERAGE_WARNING_DIFFERENCE:
            result['warnings'].append('LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE')
    native_price = finite(r.get('price'))
    evidence_close = finite(r.get('provider_date_market_close'))
    if evidence_close is None or evidence_close <= 0:
        result['warnings'].append('HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE')
    elif r.get('provider_date_ohlc_incomplete'):
        result['warnings'].append('HISTORICAL_OHLC_INCOMPLETE')
    historical_mismatch = (
        evidence_close is not None and evidence_close > 0 and native_price is not None
        and native_price > 0 and abs(evidence_close / native_price - 1) > EVIDENCE_MAX_DIFFERENCE
    )
    if historical_mismatch:
        result['warnings'].append('HISTORICAL_PRICE_MISMATCH')
    review = unresolved_basis_review(r, as_of=as_of)
    if review:
        result['basis_review'] = review
        result['warnings'].append('REVIEWED_UNRESOLVED_BASIS')
    def blocked(reason: str) -> dict[str, Any]:
        if quarterly:
            result['ownership_basis_status'] = 'NEW_QUARTER_REVIEW_REQUIRED' if reason == 'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED' else 'HELD'
        return {**result, 'reason': reason}
    equity = result['parent_equity_usd']
    if equity is None:
        return blocked('MISSING_EQUITY')
    if equity <= 0:
        return blocked('ZERO_EQUITY' if equity == 0 else 'NEGATIVE_EQUITY')
    available = r.get('source_availability_date')
    if not available or available > as_of:
        return blocked('EQUITY_AVAILABILITY_UNVERIFIED')
    if (today - date.fromisoformat(available)).days > 180:
        return blocked('STALE_EQUITY')
    if not price or result['price'] is None or result['price'] <= 0 or price['pvm'] > as_of:
        return blocked('MISSING_PRICE')
    if (today-date.fromisoformat(price['pvm'])).days > 3:
        return blocked('STALE_PRICE')
    factor = finite(r.get('sharefactor'))
    ownership = reviewed_ownership(r, as_of=as_of, price_date=price['pvm'], contract=ownership_contract, review_records=review_records)
    if ownership:
        if ownership.get('review_context'):
            result['ownership_review'] = ownership['review_context']
        if ownership.get('metadata'):
            result['ownership_basis'] = ownership['metadata']
            if quarterly:
                result.update(share_basis_date=ownership['metadata']['share_source_date'],
                              share_basis_date_basis=ownership['metadata']['share_source_date_basis'])
        if ownership['reason'] != 'OK':
            return blocked(ownership['reason'])
    if active_classes != 1 or (not ownership and (
        r.get('ownership_conflict') or category not in ('Domestic Common Stock','Canadian Common Stock') or factor != 1)):
        return blocked('OWNERSHIP_BASIS_UNVERIFIED')
    shares = finite(r.get('shares_outstanding'))
    if shares is None or shares <= 0:
        return blocked('MISSING_SHARES')
    if shares != finite(r.get('sharesbas')):
        return blocked('SHARE_BASIS_UNVERIFIED')
    if ownership:
        shares = ownership['economic_units']
    native_price, native_cap = finite(r.get('price')), finite(r.get('marketcap'))
    if (native_price is None or native_price <= 0 or native_cap is None or native_cap <= 0
        or abs(native_price*shares/native_cap-1) > EVIDENCE_MAX_DIFFERENCE):
        return blocked('SHARE_BASIS_UNVERIFIED')
    # Missing history is diagnostic; demonstrated contradictory bases still need review.
    if historical_mismatch or review:
        return blocked('SHARE_BASIS_UNVERIFIED')
    cap = result['price']*shares
    value = cap/equity
    if not math.isfinite(cap) or not math.isfinite(value) or value <= 0:
        return blocked('PB_NONFINITE')
    if equity <= 1_000_000:
        result['warnings'].append('NEAR_ZERO_EQUITY')
    if quarterly:
        result['ownership_basis_status'] = 'OPERATOR_CONFIRMED_QUARTER' if ownership else 'EXISTING_UNREVIEWED_COMMON_RULE'
    return {**result, 'market_cap': cap, 'value': value, 'status': 'OK', 'reason': 'OK',
            'warnings': result['warnings']}


def _valid_price(conn: sqlite3.Connection, ticker: str, market: str, *, as_of: str, exact: bool=False) -> dict[str, Any] | None:
    row = conn.execute(f"""SELECT pvm,close FROM osakedata WHERE osake=? AND market=?
        AND pvm{'=' if exact else '<='}? AND open>0 AND high>0 AND low>0 AND close>0
        AND high>=max(open,close,low) AND low<=min(open,close,high)
        ORDER BY pvm DESC LIMIT 1""", (ticker,market,as_of)).fetchone()
    return dict(row) if row else None


def book_value_report(canonical: sqlite3.Connection, market: sqlite3.Connection, *, company_id: int,
                      ticker: str, as_of: str) -> dict[str, Any]:
    """Query canonical accepted values/evidence only; no provider JSON in reporting."""
    date.fromisoformat(as_of)
    ownership_contract = reporting_ownership_contract(canonical, as_of=as_of)
    review_records = reporting_ownership_records(canonical, as_of=as_of)
    present = canonical.execute("SELECT 1 FROM sqlite_master WHERE name='v4_parent_equity_source'").fetchone()
    if not present:
        return {'current': current_pb(None,as_of=as_of,price=None,category=None,active_classes=0,ownership_contract=ownership_contract),
                'provider': {'value': None, 'reason': 'PARENT_EQUITY_NOT_MIGRATED', 'semantic_mode': PROVIDER_MODE}, 'history': [], 'caveat': CAVEAT}
    # Limit quarters before validating P/B: never replace a missing latest slot by an older valid one.
    quarters = [dict(r) for r in canonical.execute("""SELECT q.quarter_id,q.company_id,q.fiscal_year,q.fiscal_quarter,
        q.source_reportperiod AS reportperiod,
        CASE WHEN s.quarter_id IS NOT NULL THEN f.parent_equity END AS parent_equity,
        CASE WHEN s.quarter_id IS NOT NULL THEN f.parent_equity_usd END AS parent_equity_usd,
        f.shares_outstanding,
        s.observation_id,s.content_hash,s.dimension,s.provider_date,s.source_availability_date,
        s.acceptance_rule,s.category,s.pb,s.marketcap,s.price,s.sharesbas,s.shareswa,s.shareswadil,s.sharefactor
        FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id)
        LEFT JOIN v4_parent_equity_source s ON s.quarter_id=q.quarter_id
          AND EXISTS(SELECT 1 FROM v4_field_provenance sp WHERE sp.quarter_id=q.quarter_id
                     AND sp.canonical_field='shares_outstanding' AND sp.provider_observation_id=s.observation_id)
        WHERE q.company_id=? AND q.identity_status='ACCEPTED' AND q.source_availability_date<=?
          AND (s.source_availability_date IS NULL OR s.source_availability_date<=?)
        ORDER BY q.fiscal_year DESC,q.fiscal_quarter DESC LIMIT 4""", (company_id,as_of,as_of))]
    latest = quarters[0] if quarters else None
    tm = market.execute('SELECT market FROM ticker_meta WHERE ticker=?',(ticker,)).fetchone()
    market_name = str(tm['market'] or 'usa').lower() if tm else 'usa'
    if market_name in ('nasdaq','nyse','nysemkt','amex','arca','otc','otcqx','otcqb'):
        market_name = 'usa'
    securities = canonical.execute('SELECT current_ticker FROM security WHERE company_id=? AND active=1',(company_id,)).fetchall()
    if latest:
        identity = canonical.execute('''SELECT s.security_id,s.current_ticker,s.valid_from,s.valid_to,c.company_key
            FROM security s JOIN company c USING(company_id)
            WHERE s.company_id=? AND s.current_ticker=? AND s.active=1''',(company_id,ticker)).fetchall()
        if len(identity) == 1:
            latest.update(security_id=identity[0]['security_id'],
                          canonical_ticker=identity[0]['current_ticker'],company_key=identity[0]['company_key'],
                          security_valid_from=identity[0]['valid_from'],security_valid_to=identity[0]['valid_to'])
    current_price = _valid_price(market,ticker,market_name,as_of=as_of)
    if latest and latest.get('provider_date'):
        # Corroborating history needs a usable close, not valuation-quality OHLC.
        evidence = market.execute("""SELECT close,open,high,low FROM osakedata
            WHERE osake=? AND market=? AND pvm=?""", (ticker,market_name,latest['provider_date'])).fetchone()
        latest['provider_date_market_close'] = evidence['close'] if evidence else None
        valid_ohlc = _valid_price(market,ticker,market_name,as_of=latest['provider_date'],exact=True)
        latest['provider_date_ohlc_incomplete'] = bool(evidence and not valid_ohlc)
    if latest and canonical.execute("SELECT 1 FROM sqlite_master WHERE name='v4_result_publication_authority'").fetchone():
        evidence = canonical.execute("""SELECT e.matching_method FROM v4_result_publication_authority a
            JOIN v4_result_publication_evidence e ON e.evidence_id=a.selected_evidence_id
            WHERE a.quarter_id=? AND a.status='VERIFIED' AND a.result_publication_source='SEC_FORM_6K_RESULT'""",
            (latest['quarter_id'],)).fetchone()
        if evidence:
            import json

            try:
                identity = json.loads(evidence['matching_method']).get('frozen_case', {}).get('candidates', [])
                latest['ownership_conflict'] = any(
                    candidate.get('identity', {}).get('provider_type_conflict')
                    or candidate.get('identity', {}).get('is_adr_or_ads')
                    for candidate in identity
                )
            except (TypeError, ValueError):
                latest['ownership_conflict'] = True
    current = current_pb(latest,as_of=as_of,price=current_price,category=latest.get('category') if latest else None,
                         active_classes=len(securities) if any(r['current_ticker']==ticker for r in securities) else 0,
                         ownership_contract=ownership_contract, review_records=review_records)
    return {'current': current, 'provider': provider_reference(latest or {}),
            'history': [provider_reference(r) for r in quarters], 'caveat': CAVEAT}
