"""Fixed period-end protection for ordinary Refresh; no persisted override state.

The accepted source observation, not a fiscal label or rolling source horizon,
binds the canonical row. Exceptions consume existing exact source-removal or
accounting-boundary evidence. Native validation runs before this projection.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .contracts import fingerprint
from rawcandle.fundamentals.schema.contract import SHARADAR_ARQ_FIELD_MAPPING
from rawcandle.fundamentals.schema.parent_equity import finite
from rawcandle.fundamentals.publication_dates import select_valid_publication_winner

VERSION = "FUNDAMENTALS_HISTORICAL_FREEZE_V1"
CUTOFF = "2024-12-31"
HELD = "FROZEN_PROVIDER_CONFLICT_HELD"
ALLOWED = "FROZEN_REVIEWED_REPAIR_ALLOWED"
REVIEW_REASON = "FROZEN_HISTORICAL_PROVIDER_CONFLICT"
KEY = ("ticker", "dimension", "date", "reportperiod")
FINANCIAL = (*SHARADAR_ARQ_FIELD_MAPPING, "parent_equity", "parent_equity_usd")
METADATA = ("period_end", "source_reportperiod", "source_fiscalperiod",
            "source_availability_date", "first_public_result_date")


def policy_evidence():
    return {'policy': VERSION, 'cutoff': CUTOFF, 'cutoff_field': 'period_end'}


def financial_state(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in (*FINANCIAL, *METADATA)}


def _key(row):
    return tuple(str(row[k]) for k in KEY)


def _sql_number(value):
    # Refresh serializes non-integral normalized decimals as strings; SQLite's
    # numeric affinity stores those as REAL. Compare the projected stored value.
    return float(value) if isinstance(value, str) else value


def _parent_value(source, native):
    # Native parent-equity acceptance requires the accepted shares provenance.
    # A source equity number alone is not an accepted canonical equity value.
    if source.get('sharesbas') is None:
        return None
    return finite((source.get('_acquisition_payload') or source).get(native))


@contextmanager
def _ro(path):
    c = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    try:
        yield c
    finally:
        c.close()


def accepted_history(canonical_db, provider_db, company_id):
    """Read exact accepted financial/source bindings, failing closed on ambiguity."""
    from .refresh_fundamentals import normalize_source_row
    with _ro(canonical_db) as c, _ro(provider_db) as p:
        periods = [date.fromisoformat(r[0]) for r in c.execute(
            "SELECT period_end FROM v4_quarter WHERE company_id=?",
            (company_id,))]
        if not any(d <= date.fromisoformat(CUTOFF) for d in periods):
            return []
        rows = [dict(r) for r in c.execute(
            "SELECT q.*,f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) "
            "WHERE q.company_id=? AND q.identity_status='ACCEPTED' AND q.period_end<=? ORDER BY q.fiscal_year,q.fiscal_quarter",
            (company_id,CUTOFF))]
        for row in rows:
            # Parse every accepted date; malformed dates must never become recent.
            period = date.fromisoformat(row['period_end'])
            if period > date.fromisoformat(CUTOFF):
                continue
            ids = {str(r[0]) for table in (
                "v4_field_provenance", "v4_common_earnings_provenance",
                "v4_operating_working_capital_provenance",
            ) for r in c.execute(
                f"SELECT DISTINCT provider_observation_id FROM {table} WHERE quarter_id=?",
                (row['quarter_id'],))}
            if len(ids) != 1:
                raise ValueError('HISTORICAL_FREEZE_ACCEPTED_SOURCE_AMBIGUOUS')
            source = p.execute(
                "SELECT s.*,po.payload_json,po.content_hash,po.company_id FROM "
                "sharadar_fundamental_observation s JOIN provider_observation po USING(observation_id) "
                "WHERE po.observation_id=?", (next(iter(ids)),)).fetchone()
            if source is None:
                raise ValueError('HISTORICAL_FREEZE_ACCEPTED_SOURCE_MISSING')
            source = dict(source)
            if (source['company_id'] != company_id or source['dimension'] != 'ARQ'
                    or source['reportperiod'] != row['source_reportperiod']
                    or source['fiscalperiod'] != row['source_fiscalperiod']
                    or source['date'] != row['source_availability_date']
                    or any(row[k] != source[v] for k, v in SHARADAR_ARQ_FIELD_MAPPING.items())):
                raise ValueError('HISTORICAL_FREEZE_ACCEPTED_SOURCE_CONTRADICTION')
            row['_accepted_source'] = {**normalize_source_row(source),
                '_acquisition_payload': json.loads(source['payload_json']),
                '_provider_observation_id': source['observation_id'],
                '_provider_content_hash': source['content_hash']}
            if any(row.get(k) != _parent_value(row['_accepted_source'], v) for k,v in
                   (('parent_equity','equity'), ('parent_equity_usd','equityusd'))):
                raise ValueError('HISTORICAL_FREEZE_ACCEPTED_EQUITY_CONTRADICTION')
    return rows


def historical_financial_freeze_decision(accepted, incoming):
    """Pure decision on one authoritative accepted row and projected ARQ winner."""
    if date.fromisoformat(accepted['period_end']) > date.fromisoformat(CUTOFF):
        return {'decision': 'NOT_FROZEN'}
    old = accepted['_accepted_source']
    changed = []
    if incoming is None:
        changed.append('SOURCE_DISAPPEARED')
    else:
        if accepted['period_end'] != incoming['reportperiod']:
            changed.append('PERIOD_END_CHANGED')
        if _key(old) != _key(incoming):
            changed.append('SOURCE_KEY_CHANGED')
        if any(old[k] != incoming[k] for k in ('fiscalperiod', 'calendardate')):
            changed.append('SOURCE_IDENTITY_CHANGED')
        if any(accepted[k] != _sql_number(incoming.get(v)) for k, v in SHARADAR_ARQ_FIELD_MAPPING.items()):
            changed.append('FINANCIAL_PAYLOAD_CHANGED')
        from .refresh_fundamentals import FINANCIAL_FIELDS
        if any(old.get(k) != incoming.get(k) for k in FINANCIAL_FIELDS):
            changed.append('FINANCIAL_PAYLOAD_CHANGED')
        if finite((old.get('_acquisition_payload') or old).get('sharefactor')) != finite(
                (incoming.get('_acquisition_payload') or incoming).get('sharefactor')):
            changed.append('ECONOMIC_SOURCE_FACTOR_CHANGED')
        for field, native in (('parent_equity', 'equity'), ('parent_equity_usd', 'equityusd')):
            if field in accepted and accepted[field] != _parent_value(incoming, native):
                changed.append('FINANCIAL_PAYLOAD_CHANGED')
    if not changed:
        return {'decision': 'FROZEN_NO_CONFLICT'}
    values = {}
    if incoming is not None:
        projected = {k:_sql_number(incoming.get(v)) for k,v in SHARADAR_ARQ_FIELD_MAPPING.items()}
        projected.update(parent_equity=_parent_value(incoming,'equity'), parent_equity_usd=_parent_value(incoming,'equityusd'))
        values = {k:{'accepted':accepted.get(k),'incoming':v} for k,v in projected.items() if accepted.get(k) != v}
        old_factor = finite((old.get('_acquisition_payload') or old).get('sharefactor'))
        new_factor = finite((incoming.get('_acquisition_payload') or incoming).get('sharefactor'))
        if old_factor != new_factor:
            values['provider_sharefactor'] = {'accepted':old_factor,'incoming':new_factor}
    evidence = {'policy': VERSION, 'cutoff': CUTOFF,
        'identity': [accepted['company_id'], accepted['fiscal_year'], accepted['fiscal_quarter']],
        'period_end': accepted['period_end'], 'accepted': financial_state(accepted),
        'accepted_source': old, 'incoming_source': dict(incoming) if incoming else None,
        'reason_codes': sorted(set(changed)), 'value_changes': values, 'decision': HELD}
    return {**evidence, 'evidence_fingerprint': fingerprint(evidence)}


def apply_to_comparison(change, *, canonical_db, provider_db, current, histories,
                        policy_args):
    """Enrich an existing review, or create one ticker-local hold in its queue."""
    from .refresh_fundamentals import build_source_history_merge
    identity = change.get('identity') or {}
    if identity.get('status') != 'KNOWN' or any(histories[d].status != 'COMPLETE' for d in ('ARQ','MRQ')):
        return change
    if any(current[d].get('invalid_rows') or current[d].get('legacy_source_version_ambiguities') for d in ('ARQ','MRQ')):
        return change  # existing native global blocker remains authoritative
    if change.get('classification') in {'NO_EFFECTIVE_CHANGE', 'SOURCE_ONLY_METADATA_CHANGE'}:
        # Native Refresh does not replace this ticker's provider rows. Do not
        # invent a different winner by simulating observation-ID regeneration.
        return change
    accepted = accepted_history(canonical_db, provider_db, identity['company_id'])
    merge = build_source_history_merge(change['ticker'], current, histories,
        retained_history_approval=change.get('retained_history_approval'), **policy_args)
    incoming = merge['dimensions']['ARQ']['merged_rows']
    conflicts = []
    for row in accepted:
        if row['period_end'] > CUTOFF:
            continue
        old = row['_accepted_source']
        candidates = [r for r in incoming if r['fiscalperiod'] == row['source_fiscalperiod']]
        # A fiscal relabel can retain the exact key; the old label must not hide it.
        candidates += [r for r in incoming if _key(r) == _key(old) and r not in candidates]
        # Match the native candidate order, including its deterministic tie ID.
        from .refresh_copy_runtime import _observation_id
        from .refresh_fundamentals import _raw_row
        candidates.sort(key=lambda r: _observation_id('|'.join(_key(r)), fingerprint(_raw_row(r))))
        candidates.sort(key=lambda r: (r['reportperiod'], r.get('lastupdated') or r['date']), reverse=True)
        winner = select_valid_publication_winner(candidates) if candidates else None
        decision = historical_financial_freeze_decision(row, winner)
        if decision['decision'] == HELD:
            decision['incoming_candidates'] = [dict(r) for r in candidates]
            conflicts.append(decision)
    if not conflicts:
        return change
    # No new approval contract. Native exact removal approval covers only the
    # accepted source keys named by its verified binding, never other revisions.
    approval = change.get('true_removal_approval') or {}
    if approval.get('applied'):
        from .refresh_review_queue import TRUE_REMOVAL_APPROVAL_VERSION
        binding = approval.get('approved_binding') or {}
        if (approval.get('resolution_contract_version') != TRUE_REMOVAL_APPROVAL_VERSION
                or approval.get('operator_reviewed') is not True
                or approval.get('approval_evidence_fingerprint') != fingerprint(binding)
                or approval.get('approved_source_keys') != binding.get('affected_source_keys')):
            raise ValueError('HISTORICAL_FREEZE_REPAIR_EVIDENCE_INVALID')
        keys = {_key(k) for k in approval['approved_source_keys']}
        for decision in conflicts:
            if _key(decision['accepted_source']) in keys:
                decision['decision'] = ALLOWED
                decision['repair_binding'] = dict(approval)
    # Accounting-boundary evidence remains native; a pending application is
    # validated by that contract before this projection. Only its exact ARQ key
    # may be repaired; never unrelated rows from the ticker.
    application = change.get('accounting_boundary_resolution') or {}
    if application.get('applied'):
        from . import accounting_boundary_review as boundary
        boundary.validate_candidate_input(application, histories)
        for decision in conflicts:
            if _key(decision['accepted_source']) == boundary.ARQ_KEY:
                decision['decision'] = ALLOWED
                decision['repair_binding'] = dict(application)
    for decision in conflicts:
        decision['evidence_fingerprint'] = fingerprint({k:v for k,v in decision.items() if k != 'evidence_fingerprint'})
    result = {**change, 'historical_freeze': {'policy': VERSION, 'cutoff': CUTOFF, 'conflicts': conflicts}}
    held = [d for d in conflicts if d['decision'] == HELD]
    if held and change.get('classification') != 'REVIEW_REQUIRED':
        result.update(classification='REVIEW_REQUIRED', review_reason=REVIEW_REASON)
        result['source_history_events'] = [*change.get('source_history_events', []), *[
            {'ticker': change['ticker'], 'dimension': 'ARQ', 'event': REVIEW_REASON,
             'classification_reason': REVIEW_REASON,
             'source_identity': {k:d['accepted_source'][k] for k in KEY},
             'fiscal_identity': dict(zip(('fiscal_year','fiscal_quarter'), d['identity'][1:])),
             'historical_freeze_evidence': d} for d in held]]
    return result


def _existing_boundary_label_repair(row, new, provider_db, canonical_db):
    """Preserve the existing exact boundary rehearsal/publication contract.

    It changes only the recorded provider label; all accepted financial values,
    economic identity and dates must stay identical. Native installed-store and
    canonical proofs apply unchanged, including copy-only rehearsal evidence.
    """
    if new is None or provider_db is None or canonical_db is None:
        return False
    expected = financial_state(row)
    expected['source_fiscalperiod'] = new.get('source_fiscalperiod')
    if expected != financial_state(new):
        return False
    from . import accounting_boundary_review as boundary
    for decision in boundary.installed_decisions(provider_db):
        e = boundary.verify_decision(decision)
        if (row['company_id'] != e['identity']['company_id']
                or row['source_reportperiod'] != e['arq']['source_key'][3]
                or row['source_availability_date'] != e['arq']['source_key'][2]
                or row['source_fiscalperiod'] != e['arq']['accepted_label']
                or new['source_fiscalperiod'] != e['arq']['provider_label']):
            continue
        application = {'applied': True, 'stale': False, 'phase': 'PUBLISHED',
            'decision': decision, 'proposal_fingerprint': decision['proposal']['proposal_fingerprint']}
        boundary.validate_expected_store(provider_db, {e['identity']['ticker']: application}, canonical_db=canonical_db)
        return True
    return False


def validate_candidate(before, after, changes=(), *, provider_db=None, canonical_db=None):
    """Final copy-only defence: repairs must match both exact old and new states."""
    repairs = {}
    for change in changes:
        for d in (change.get('historical_freeze') or {}).get('conflicts', []):
            if d.get('evidence_fingerprint') != fingerprint({k:v for k,v in d.items() if k != 'evidence_fingerprint'}):
                raise ValueError('HISTORICAL_FREEZE_CANDIDATE_EVIDENCE_TAMPERED')
            if d['decision'] == ALLOWED:
                repairs[tuple(d['identity'])] = d
    for key, row in before.items():
        if row.get('identity_status') != 'ACCEPTED' or date.fromisoformat(row['period_end']) > date.fromisoformat(CUTOFF):
            continue
        new = after.get(key)
        preserved = financial_state(row)
        # Keep the existing audited bootstrap for an unestablished date. This
        # never moves a previously established first-public date.
        preserved['first_public_result_date'] = row.get('first_public_result_date') or row.get('source_availability_date')
        if new is not None and preserved == financial_state(new):
            continue
        if _existing_boundary_label_repair(row, new, provider_db, canonical_db):
            continue
        d = repairs.get(key)
        if d is None or d['accepted'] != financial_state(row):
            raise ValueError('HISTORICAL_FREEZE_CANONICAL_MUTATION_BLOCKED')
        proposed = d['incoming_source']
        if proposed is None:
            if new is not None:
                raise ValueError('HISTORICAL_FREEZE_REPAIR_CANDIDATE_MISMATCH')
        else:
            expected = {**preserved, **{k:_sql_number(proposed.get(v)) for k,v in SHARADAR_ARQ_FIELD_MAPPING.items()},
                'period_end': proposed['reportperiod'], 'source_reportperiod': proposed['reportperiod'],
                'source_fiscalperiod': proposed['fiscalperiod'], 'source_availability_date': proposed['date']}
            expected.update(parent_equity=_parent_value(proposed,'equity'), parent_equity_usd=_parent_value(proposed,'equityusd'))
            if new is None or expected != financial_state(new):
                raise ValueError('HISTORICAL_FREEZE_REPAIR_CANDIDATE_MISMATCH')
