"""Rebuildable reporting-only parent book equity metrics; never a score input."""
from __future__ import annotations

import math
import sqlite3
from datetime import date
from typing import Any, Mapping

from rawcandle.fundamentals.schema.parent_equity import finite

CURRENT_CONTRACT = 'PB_CURRENT_PARENT_EQUITY_V1'
CURRENT_MODE = 'CURRENT_REVISED_REPORTING'
PROVIDER_MODE = 'PROVIDER_OBSERVATION_REFERENCE'
ROUNDING_TOLERANCE = 0.0005001
SHARE_AVERAGE_MAX_DIFFERENCE = 0.25
EVIDENCE_MAX_DIFFERENCE = 0.01
CAVEAT = 'Parent equity attributable to parent shareholders as supplied by Sharadar; preferred-capital exclusion is not proven.'


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
               category: str | None, active_classes: int) -> dict[str, Any]:
    today = date.fromisoformat(as_of)
    r = dict(row or {})
    result = {'contract': CURRENT_CONTRACT, 'semantic_mode': CURRENT_MODE, 'role': 'REPORTING_ONLY',
              'as_of_date': as_of, 'value': None, 'status': 'NOT_AVAILABLE', 'reason': 'MISSING_EQUITY',
              'parent_equity': finite(r.get('parent_equity')), 'parent_equity_usd': finite(r.get('parent_equity_usd')),
              'equity_fiscal_year': r.get('fiscal_year'), 'equity_fiscal_quarter': r.get('fiscal_quarter'),
              'equity_reportperiod': r.get('reportperiod'), 'equity_source_availability_date': r.get('source_availability_date'),
              'price_date': price.get('pvm') if price else None, 'price': finite(price.get('close')) if price else None,
              'market_cap': None, 'warnings': [], 'caveat': CAVEAT}
    def blocked(reason: str) -> dict[str, Any]:
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
    if (r.get('ownership_conflict') or category not in ('Domestic Common Stock','Canadian Common Stock') or factor != 1
        or active_classes != 1):
        return blocked('OWNERSHIP_BASIS_UNVERIFIED')
    shares = finite(r.get('shares_outstanding'))
    if shares is None or shares <= 0:
        return blocked('MISSING_SHARES')
    if shares != finite(r.get('sharesbas')):
        return blocked('SHARE_BASIS_UNVERIFIED')
    # Cover outstanding versus duration-average: a conservative discontinuity gate.
    avg = finite(r.get('shareswa'))
    if avg is None or avg <= 0 or abs(shares/avg-1) > SHARE_AVERAGE_MAX_DIFFERENCE:
        return blocked('SHARE_BASIS_UNVERIFIED')
    native_price, native_cap = finite(r.get('price')), finite(r.get('marketcap'))
    if (native_price is None or native_price <= 0 or native_cap is None or native_cap <= 0
        or abs(native_price*shares/native_cap-1) > EVIDENCE_MAX_DIFFERENCE):
        return blocked('SHARE_BASIS_UNVERIFIED')
    # Independently compare split bases using the provider-date close.
    evidence_close = finite(r.get('provider_date_market_close'))
    if evidence_close is None or evidence_close <= 0 or abs(evidence_close/native_price-1)>EVIDENCE_MAX_DIFFERENCE:
        return blocked('SHARE_BASIS_UNVERIFIED')
    cap = result['price']*shares
    value = cap/equity
    if not math.isfinite(cap) or not math.isfinite(value):
        return blocked('PB_NONFINITE')
    return {**result, 'market_cap': cap, 'value': value, 'status': 'OK', 'reason': 'OK',
            'warnings': ['NEAR_ZERO_EQUITY'] if equity <= 1_000_000 else []}


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
    present = canonical.execute("SELECT 1 FROM sqlite_master WHERE name='v4_parent_equity_source'").fetchone()
    if not present:
        return {'current': current_pb(None,as_of=as_of,price=None,category=None,active_classes=0),
                'provider': {'value': None, 'reason': 'PARENT_EQUITY_NOT_MIGRATED', 'semantic_mode': PROVIDER_MODE}, 'history': [], 'caveat': CAVEAT}
    # Limit quarters before validating P/B: never replace a missing latest slot by an older valid one.
    quarters = [dict(r) for r in canonical.execute("""SELECT q.quarter_id,q.fiscal_year,q.fiscal_quarter,
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
    current_price = _valid_price(market,ticker,market_name,as_of=as_of)
    if latest and latest.get('provider_date'):
        evidence = _valid_price(market,ticker,market_name,as_of=latest['provider_date'],exact=True)
        latest['provider_date_market_close'] = evidence['close'] if evidence else None
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
                         active_classes=len(securities) if any(r['current_ticker']==ticker for r in securities) else 0)
    return {'current': current, 'provider': provider_reference(latest or {}),
            'history': [provider_reference(r) for r in quarters], 'caveat': CAVEAT}
