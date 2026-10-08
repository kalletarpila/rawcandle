"""Bounded, immutable-evidence ownership reviews for reporting-only Current P/B."""
from __future__ import annotations

from datetime import date
from copy import deepcopy
import hashlib
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Mapping

OWNERSHIP_CONTRACT = 'PB_OWNERSHIP_BASIS_V1'
QUARTERLY_OWNERSHIP_CONTRACT = 'PB_OWNERSHIP_BASIS_V2'
BINDING = ('company_id', 'company_key', 'security_id', 'canonical_ticker',
           'observation_id', 'content_hash')


@lru_cache(maxsize=1)
def ownership_reviews() -> tuple[dict[str, Any], ...]:
    artifact = json.loads(Path(__file__).with_name('ownership_reviews_v1.json').read_text())
    if artifact['contract'] != OWNERSHIP_CONTRACT:
        raise ValueError('Unsupported ownership review contract')
    return tuple(artifact['records'])


def reviewed_ownership(row: Mapping[str, Any], *, as_of: str,
                       price_date: str, contract: str = OWNERSHIP_CONTRACT,
                       review_records: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any] | None:
    if contract == QUARTERLY_OWNERSHIP_CONTRACT:
        return reviewed_quarterly_ownership(row, as_of=as_of, price_date=price_date, review_records=review_records)
    if contract != OWNERSHIP_CONTRACT:
        raise ValueError('Unsupported ownership review contract')
    return _reviewed_ownership_v1(row, as_of=as_of, price_date=price_date)


def _reviewed_ownership_v1(row: Mapping[str, Any], *, as_of: str,
                          price_date: str) -> dict[str, Any] | None:
    """A known review scope cannot fall back to unreviewed ownership on mismatch.

    Future absence of actions is not inferred: effective_to bounds the completed
    evidence review. No ratios are inferred from provider marketcap or P/B.
    """
    candidates = [r for r in ownership_reviews() if any(
        row.get(k) is not None and row.get(k) == r[k]
        for k in ('company_id', 'security_id', 'canonical_ticker', 'observation_id'))]
    if not candidates:
        return None
    exact = [r for r in candidates if all(row.get(k) == r[k] for k in BINDING)]
    if len(exact) != 1:
        return {'reason': 'OWNERSHIP_REVIEW_UNVERIFIED'}
    r = deepcopy(exact[0])
    metadata = {k: r[k] for k in (
        *BINDING, 'reviewed_security_type', 'ownership_interpretation',
        'effective_from', 'effective_to', 'unit_effective_from', 'share_source_date',
        'share_source_date_basis', 'reviewed_at', 'review_version', 'evidence_reference',
        'evidence_urls', 'economic_unit_rule', 'provider_declared_factor',
        'identity_override', 'release_type', 'evidence_status', 'notes',
        'preferred_exclusion_proven')}
    metadata['contract'] = OWNERSHIP_CONTRACT
    metadata['review_content_hash'] = hashlib.sha256(
        json.dumps(r, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def held(reason: str) -> dict[str, Any]:
        return {'reason': reason, 'metadata': {**metadata, 'evidence_status': reason}}

    try:
        today, quoted = date.fromisoformat(as_of), date.fromisoformat(price_date)
        source = date.fromisoformat(r['share_source_date'])
        date.fromisoformat(r['effective_from'])
        date.fromisoformat(r['effective_to'])
        date.fromisoformat(r['unit_effective_from'])
        if ((row.get('security_valid_from') and row['security_valid_from'] > as_of)
            or (row.get('security_valid_to') and row['security_valid_to'] < as_of)):
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        if (as_of < r['effective_from'] or not r['effective_to']
            or as_of > r['effective_to'] or r['reviewed_at'][:10] > as_of
            or r['unit_effective_from'] > price_date
            or r['unit_effective_from'] > row['provider_date']
            or source > quoted or source > today or r['share_source_date'] > row['provider_date']
            or (today-source).days > min(r['max_carry_forward_days'], 180)):
            return held('OWNERSHIP_REVIEW_STALE')
        changes = [*r['known_share_changes'], *row.get('ownership_share_changes', [])]
        if row.get('newer_share_count_required') or any(
            source < date.fromisoformat(e['effective_date']) <= today
            for e in changes):
            # A Boolean cannot prove settlement. A refreshed bound observation
            # and share-source date must cover the action before reuse.
            return held('NEWER_SHARE_COUNT_REQUIRED')
        if r['evidence_status'] != 'REVIEWED_SUPPORTED':
            return held(r['hold_reason'] or 'OWNERSHIP_BASIS_UNVERIFIED')
        if (r['ownership_interpretation'] != 'WHOLE_PARENT_COMMON_ECONOMIC_UNITS'
            or row.get('sharesbas') != r['accepted_sharesbas']
            or row.get('sharefactor') != r['provider_declared_factor']
            or not r['evidence_urls']):
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        if r['economic_unit_rule'] == 'ORDINARY_COMMON':
            if r['reviewed_security_type'] != 'COMMON_OR_ORDINARY':
                return held('OWNERSHIP_REVIEW_UNVERIFIED')
            factor = 1.0
        elif r['economic_unit_rule'] == 'ADS_EQUIVALENTS':
            if r['reviewed_security_type'] != 'ADS':
                return held('ADR_FACTOR_UNVERIFIED')
            numerator, denominator = r['exact_factor_numerator'], r['exact_factor_denominator']
            if not isinstance(numerator, int) or not isinstance(denominator, int) or numerator <= 0 or denominator <= 0:
                return held('ADR_FACTOR_UNVERIFIED')
            factor = numerator / denominator
            metadata['reviewed_factor'] = factor
            metadata['reviewed_factor_ratio'] = {'numerator': numerator, 'denominator': denominator}
        else:
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        units = row['sharesbas'] * factor
        if not math.isfinite(units) or units <= 0:
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        metadata['economic_units'] = units
        return {'reason': 'OK', 'economic_units': units, 'metadata': metadata}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return held('OWNERSHIP_REVIEW_UNVERIFIED')


@lru_cache(maxsize=1)
def _quarterly_artifact() -> tuple[dict[str, Any], str]:
    raw = Path(__file__).with_name('ownership_reviews_v2.json').read_bytes()
    artifact = json.loads(raw)
    if artifact['contract'] != QUARTERLY_OWNERSHIP_CONTRACT:
        raise ValueError('Unsupported quarterly ownership review contract')
    return artifact, hashlib.sha256(raw).hexdigest()


def ownership_reviews_v2() -> tuple[dict[str, Any], ...]:
    return tuple(_quarterly_artifact()[0]['records'])


def ownership_reviews_v2_hash() -> str:
    return _quarterly_artifact()[1]


def reviewed_quarterly_ownership(row: Mapping[str, Any], *, as_of: str,
                                 price_date: str, review_records: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any] | None:
    """Validate the latest accepted observation supplied by the canonical reader.

    This is quarterly evidence, not assurance of unchanged daily shares. Known
    contradictions remain hard holds. No prior-observation units are returned
    when the authoritative observation changes, including same-Q revisions.
    """
    candidates = [r for r in (ownership_reviews_v2() if review_records is None else review_records) if any(
        row.get(k) is not None and row.get(k) == r[k]
        for k in ('company_id', 'company_key', 'security_id', 'canonical_ticker', 'observation_id'))]
    if not candidates:
        return None
    identity = [r for r in candidates if all(row.get(k) == r[k] for k in BINDING[:4])]
    if not identity:
        return {'reason': 'OWNERSHIP_REVIEW_UNVERIFIED'}
    observation_binding = (*BINDING, 'fiscal_year', 'fiscal_quarter', 'reportperiod')
    exact = [r for r in identity if all(row.get(k) == r[k] for k in observation_binding)]
    if not exact:
        previous = max(identity, key=lambda r:(r['fiscal_year'],r['fiscal_quarter'],r['reviewed_at']))
        return {'reason': 'OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED', 'review_context': {
            'prior_reviewed_quarter': f"{previous['fiscal_year']}-{previous['fiscal_quarter']}",
            'new_accepted_quarter': f"{row.get('fiscal_year')}-{row.get('fiscal_quarter')}",
            'review_status': 'NEW_QUARTER_REVIEW_REQUIRED'}}
    if len(exact) != 1:
        return {'reason': 'OWNERSHIP_REVIEW_UNVERIFIED'}
    r = deepcopy(exact[0])
    metadata = deepcopy(r)
    metadata['contract'] = QUARTERLY_OWNERSHIP_CONTRACT
    metadata['review_content_hash'] = hashlib.sha256(
        json.dumps(r, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def held(reason: str) -> dict[str, Any]:
        return {'reason': reason, 'metadata': {**metadata, 'evidence_status': reason}}

    try:
        today, quoted = date.fromisoformat(as_of), date.fromisoformat(price_date)
        source = date.fromisoformat(r['share_source_date'])
        unit = date.fromisoformat(r['unit_effective_from'])
        provider = date.fromisoformat(row['provider_date'])
        activated = date.fromisoformat(r['valid_from_as_of'])
        reviewed = date.fromisoformat(r['reviewed_at'][:10])
        if (r['validity_mode'] != 'LATEST_ACCEPTED_QUARTER_OBSERVATION'
            or r['approval_mode'] != 'OPERATOR_CONFIRMED'
            or not r['evidence_reference'] or not r['evidence_urls']
            or not r['share_source_date_basis'] or not r['review_version']
            or row.get('category') != r['accepted_category']
            or row.get('provider_date') != r['accepted_provider_date']
            or row.get('source_availability_date') != r['accepted_source_availability_date']
            or row.get('sharesbas') != r['accepted_sharesbas']
            or row.get('sharefactor') != r['provider_declared_factor']
            or (row.get('security_valid_from') and row['security_valid_from'] > as_of)
            or (row.get('security_valid_to') and row['security_valid_to'] < as_of)):
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        # No effective_to or source-age expiry: validity follows the accepted Q.
        if activated > today or reviewed > today or source > min(quoted, today, provider) or unit > min(quoted, provider):
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        if r['evidence_status'] != 'REVIEWED_SUPPORTED':
            return held(r['hold_reason'] or 'OWNERSHIP_BASIS_UNVERIFIED')
        if any(not isinstance(url, str) or not url.startswith('https://') for url in r['evidence_urls']):
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        changes = [*r['known_share_changes'], *row.get('ownership_share_changes', [])]
        if row.get('newer_share_count_required') or any(
            source < date.fromisoformat(e['effective_date']) <= today for e in changes):
            return held('NEWER_SHARE_COUNT_REQUIRED')
        if r['ownership_interpretation'] != 'WHOLE_PARENT_COMMON_ECONOMIC_UNITS':
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        if r['economic_unit_rule'] == 'ORDINARY_COMMON':
            if r['reviewed_security_type'] != 'COMMON_OR_ORDINARY':
                return held('OWNERSHIP_REVIEW_UNVERIFIED')
            factor = 1.0
        elif r['economic_unit_rule'] == 'ADS_EQUIVALENTS':
            numerator, denominator = r['exact_factor_numerator'], r['exact_factor_denominator']
            if (r['reviewed_security_type'] != 'ADS'
                or type(numerator) is not int or type(denominator) is not int
                or numerator <= 0 or denominator <= 0):
                return held('ADR_FACTOR_UNVERIFIED')
            factor = numerator / denominator
            metadata['reviewed_factor'] = factor
            metadata['reviewed_factor_ratio'] = {'numerator': numerator, 'denominator': denominator}
        else:
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        units = row['sharesbas'] * factor
        if isinstance(row['sharesbas'], bool) or not math.isfinite(units) or units <= 0:
            return held('OWNERSHIP_REVIEW_UNVERIFIED')
        metadata['economic_units'] = units
        return {'reason': 'OK', 'economic_units': units, 'metadata': metadata}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return held('OWNERSHIP_REVIEW_UNVERIFIED')
