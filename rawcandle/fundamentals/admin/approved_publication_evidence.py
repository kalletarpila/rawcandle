"""Explicit, portable, copy-only input to the existing Policy V1 plan contract.

Receipt/proposal/snapshots and complete SecFiling payloads travel with the input.
Only explicitly listed semantic-input references are read at live preflight.
No database writes, runtime discovery, source acquisition or approval creation.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from rawcandle.fundamentals.admin import reviewed_publication_plan as legacy
from rawcandle.fundamentals.publication_event_policy import fingerprint, PUBLICATION_EVENT_POLICY_V1
from rawcandle.fundamentals.result_publication import resolve_sec_filings_with_event_policy

MODE = "APPROVED_FROZEN_REVIEW_EVIDENCE"
HANDOFF_VERSION = 1
PLAN_VERSION = 3


def _check(condition, reason):
    if not condition:
        raise ValueError("PUBLICATION_APPROVED_" + reason)


def _key(row):
    return legacy._key(row)


def _receipt_digest(value):
    return fingerprint({k: v for k, v in value.items() if k != "artifact_fingerprint"})


def compatible_evidence(stored, frozen):
    """Missing or exact matching rows only; nullable SQL columns normalize to None.

    Original approved payload fingerprints are never normalized. Extra non-null
    stored source facts, additional candidates and changed identifiers reject.
    SQL disposition/creation bookkeeping is ignored only when not approved.
    """
    if not stored:
        return True
    by_id = {r['evidence_id']: r for r in frozen}
    return (len(stored) == len(by_id) == len(frozen)
            and {r['evidence_id'] for r in stored} == set(by_id)
            and all(all(r.get(k) == by_id[r['evidence_id']].get(k)
                        for k in (set(r) | set(by_id[r['evidence_id']]))
                        if k not in {'disposition', 'created_at_utc'} or k in by_id[r['evidence_id']]) for r in stored))


def baseline_state(snapshot):
    s = snapshot['canonical']
    return dict(quarter=s['quarter'], authority=s['authority'], company=s['company'],
                ciks=sorted(s['ciks'], key=fingerprint),
                securities=sorted(s['security'], key=fingerprint))


def company_filings(company):
    capture = json.loads(company['capture_raw_json'])
    _check(capture['company_id'] == company['company_id'] and capture['complete'] is True,
           'COMPLETE_CAPTURE_REQUIRED')
    return capture['filings']


def validate_handoff(handoff, expected_approval_fingerprint):
    """Pure verification of immutable approval, exact source proofs and contexts."""
    try:
        _check(handoff['schema_version'] == HANDOFF_VERSION
               and type(handoff['schema_version']) is int and handoff['input_mode'] == MODE,
               'HANDOFF_VERSION_INVALID')
        _check(handoff['handoff_fingerprint'] == fingerprint(
            {k: v for k, v in handoff.items() if k != 'handoff_fingerprint'}), 'HANDOFF_TAMPERED')
        a, p, candidate = handoff['approval'], handoff['proposal'], handoff['review_candidate']
        _check(a['artifact_fingerprint'] == _receipt_digest(a) == expected_approval_fingerprint,
               'RECEIPT_FINGERPRINT_INVALID')
        _check(a['status'] == 'OPERATOR_APPROVED_REVIEW_EVIDENCE'
               and a['operator'].strip() and a['operator_note'].strip() and a['approved_at_utc'],
               'OPERATOR_CONFIRMATION_REQUIRED')
        _check(all(a.get(k) is False for k in ('runtime_use_permitted', 'publication_authorized',
                    'production_apply_authorized', 'authority_mutation_authorized')), 'RECEIPT_EXECUTION_FLAGS')
        _check(p['artifact_fingerprint'] == fingerprint({k: v for k, v in p.items()
                    if k not in {'artifact_fingerprint', 'artifact_fingerprint_contract'}})
               == a['proposal_artifact_fingerprint'], 'PROPOSAL_FINGERPRINT_INVALID')
        _check(p['status'] == 'PROPOSED' and p['approved'] is False
               and p['runtime_use_permitted'] is False, 'PROPOSAL_STATE_INVALID')
        _check(candidate['artifact_fingerprint'] == _receipt_digest(candidate) == a['candidate_fingerprint']
               and candidate['proposal_artifact_fingerprint'] == p['artifact_fingerprint']
               and candidate['current_state_fingerprint'] == a['current_state_fingerprint']
               and candidate['baseline_active_generation_id'] == a['baseline_active_generation_id']
               and candidate['proposal_baseline_fingerprint'] == a['proposal_baseline_fingerprint']
               and a['proposal_bundle_path'] == candidate['proposal_bundle_path'], 'REVIEW_CANDIDATE_INVALID')
        selection = a['selection']
        _check(selection['artifact_fingerprint'] == _receipt_digest(selection)
               and selection['candidate_fingerprint'] == candidate['artifact_fingerprint'],
               'SELECTION_INVALID')
        from rawcandle.fundamentals.admin.publication_observation_approval import select_cases
        _check(select_cases(candidate, approve=selection['approved_keys'], hold=selection['held_keys'],
                            reject=selection['rejected_keys']) == selection, 'SELECTION_INVALID')
        approved = {tuple(b['natural_key']): b for b in a['approved_cases']}
        _check(len(approved) == len(a['approved_cases']) and set(approved) ==
               {tuple(k) for k in selection['approved_keys']} and approved, 'APPROVED_MEMBERSHIP_INVALID')
        proposed = {tuple(b['natural_key']): b for b in p['proposal_bindings']}
        stable = {tuple(b['natural_key']): b for b in candidate['stable_cases']}
        sources = {_key(c['quarter']): c for c in p['proposed_policy_evidence']['cases']}
        _check(len(sources) == len(p['proposed_policy_evidence']['cases'])
               and not (set(approved) & {tuple(h['natural_key']) for h in p['holds']}), 'UNAPPROVED_KEY')
        snapshots = {tuple(r['natural_key']): r['snapshot'] for r in handoff['approved_snapshots']}
        _check(len(snapshots) == len(handoff['approved_snapshots']) and set(snapshots) == set(approved),
               'SNAPSHOT_MEMBERSHIP_INVALID')
        companies = {r['company_id']: r for r in handoff['companies']}
        _check(len(companies) == len(handoff['companies']) and set(companies) == {k[0] for k in approved},
               'COMPANY_CONTEXT_SCOPE_INVALID')
        for key, binding in approved.items():
            _check(binding == stable[key] and {k: v for k, v in binding.items()
                       if k != 'current_state_fingerprint'} == proposed[key], 'APPROVAL_BINDING_INVALID')
            snap, source = snapshots[key], sources[key]
            _check(fingerprint(snap) == binding['current_state_fingerprint'], 'APPROVED_STATE_CHANGED')
            _check(len(snap['canonical']['quarter']) == len(snap['canonical']['authority']) == 1
                   and snap['canonical']['quarter'][0] == source['quarter']
                   and source['quarter']['identity_status'] == 'ACCEPTED'
                   and source['quarter']['quarter_id'] == binding['current_canonical_quarter_id']
                   and fingerprint(snap['canonical']['authority'][0]) == binding['current_authority_fingerprint'],
                   'QUARTER_AUTHORITY_BINDING_INVALID')
            event, = source['events']
            e, o = event['evidence'], event['observation']
            _check(_key(e) == key and e['quarter_id'] == source['quarter']['quarter_id']
                   and fingerprint(e) == binding['complete_evidence_fingerprint']
                   and fingerprint(o) == binding['observation_fingerprint'], 'EVIDENCE_OBSERVATION_CHANGED')
            _check(fingerprint({k: v for k, v in e.items()
                       if k not in {'quarter_id', 'evidence_hash', 'evidence_id'}}) == e['evidence_hash'],
                   'EVIDENCE_HASH_CHANGED')
            company = companies[key[0]]
            _check(sha256(company['capture_raw_json'].encode()).hexdigest() == snap['company_capture_sha256'],
                   'COMPANY_CAPTURE_CHANGED')
            filings = [legacy._decode_filing(f) for f in company_filings(company)]
            _check(len({f.accession_number for f in filings}) == len(filings), 'DUPLICATE_CONTEXT')
            parent, = [f for f in filings if f.accession_number == e['accession_number']]
            _check(fingerprint(asdict(parent)) == binding['source_context_sha256']
                   == o['resolver_context_sha256'] == snap['resolver_context_sha256'], 'RESOLVER_CONTEXT_CHANGED')
            _check(parent.source_reference == e['source_reference']
                   and parent.form == e['filing_form'] and parent.primary_document == e['document_id']
                   and parent.acceptance_timestamp_utc == e['source_timestamp_utc'], 'SOURCE_CHANGED')
            texts = {f.source_reference: f.text for f in filings}
            for f in filings:
                texts.update({ex.source_reference: ex.text for ex in f.result_exhibits})
            for url, text in company['additional_document_texts'].items():
                _check(url not in texts or texts[url] == text, 'DOCUMENT_TEXT_CONFLICT')
                texts[url] = text
            for proof in o['documents']:
                text = texts[proof['source_reference']];loc = proof['locator']
                _check(proof['source_sha256'] == binding['source_hashes'][proof['source_reference']]
                       and sha256(text.encode()).hexdigest() == loc['extracted_text_sha256']
                       and text[loc['unicode_start']:loc['unicode_end']] == proof['excerpt']
                       and sha256(proof['excerpt'].encode()).hexdigest() == proof['excerpt_sha256'],
                       'SOURCE_EXCERPT_CHANGED')
            # Use full approved company quarter scope to detect retained competing context.
            result = resolve_sec_filings_with_event_policy(
                snap['company_open_scope'], filings, policy_version=PUBLICATION_EVENT_POLICY_V1,
                observations={e['evidence_id']: o}, relations=source['relations'])['event_policy_evaluations'][key]
            _check(result['final_result'] == 'UNIQUE' and result['selected_accession'] == e['accession_number'],
                   'COMPETING_OR_INELIGIBLE_CONTEXT')
            identity_tables_for_case(handoff, key, snap)
            expected_refs = {path: digest for path, digest in snap['reviewed_input_hashes'].items()
                             if Path(path).name not in {'policy_reviewed_publication_plan.py',
                                                       'identity.json', 'population.json'}}
            _check(handoff['semantic_input_references'] == expected_refs, 'POLICY_INPUT_SCOPE_CHANGED')
        return sources, snapshots, companies
    except (KeyError, TypeError, IndexError, AttributeError, StopIteration) as exc:
        raise ValueError('PUBLICATION_APPROVED_HANDOFF_SHAPE_INVALID') from exc


def identity_tables_for_case(handoff, key, snapshot):
    """Provider identity joins by security_id, never by a nonexistent company_id.

    Historical snapshots bound the full identity capture through its byte hash.
    Preserve that explicit immutable proof to recover the exact security rows.
    """
    paths = [p for p in snapshot['reviewed_input_hashes'] if Path(p).name == 'identity.json']
    _check(len(paths) <= 1, 'IDENTITY_INPUT_SCOPE_INVALID')
    if not paths:
        return snapshot['identity_tables']
    proof = handoff['identity_input']
    path = paths[0]
    _check(proof['source_reference'] == path and sha256(proof['raw_json'].encode()).hexdigest()
           == snapshot['reviewed_input_hashes'][path]
           == handoff['proposal']['input_fingerprints']['source_files'][path], 'IDENTITY_PROOF_CHANGED')
    capture = json.loads(proof['raw_json'])
    security_ids = {s['security_id'] for s in snapshot['canonical']['security']}
    structural = [r for r in capture['structural_events'] if r['company_id'] == key[0]]
    _check(sorted(structural,key=fingerprint) == sorted(
        snapshot['identity_tables']['fundamentals_economic_structural_event'],key=fingerprint),
        'IDENTITY_PROOF_CHANGED')
    return dict(provider_security_identity=[r for r in capture['provider_security_identity']
                    if r['security_id'] in security_ids], fundamentals_economic_structural_event=structural)


def resolver_quarters(snapshot):
    """Full reviewed context; these keys are context-only, never apply membership."""
    active_ciks = {r['cik_normalized'] for r in snapshot['canonical']['ciks'] if r['status']=='ACTIVE'}
    active_tickers = {r['current_ticker'] for r in snapshot['canonical']['security'] if r['active']}
    _check(len(active_ciks) == len(active_tickers) == 1, 'IDENTITY_CONTEXT_INVALID')
    cik, = active_ciks
    ticker, = active_tickers
    return [dict(quarter_id=q['canonical_quarter_id'],company_id=q['company_id'],
                 fiscal_year=q['fiscal_year'],fiscal_quarter=q['fiscal_quarter'],period_end=q['period_end'],
                 first_public_result_date=q['first_public_result_date'],
                 source_availability_date=q['source_availability_date'],cik_normalized=cik,current_ticker=ticker)
            for q in snapshot['company_open_scope']]


def check_live_inputs(handoff):
    for path, digest in handoff['semantic_input_references'].items():
        _check(sha256(Path(handoff.get('semantic_input_paths', {}).get(path, path)).read_bytes()).hexdigest() == digest, 'POLICY_INPUT_CHANGED')


def check_current_case(db, key, snapshot, frozen, *, identity_tables=None):
    _check(legacy.state_for_key(db, key) == baseline_state(snapshot), 'CURRENT_IDENTITY_AUTHORITY_CHANGED')
    stored = legacy._rows(db, 'SELECT * FROM v4_result_publication_evidence WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=? ORDER BY evidence_id', key)
    _check(compatible_evidence(stored, frozen), 'CONFLICTING_STORED_EVIDENCE')
    # Fiscal/open-company context and structural perimeter remain current too.
    rows = legacy._rows(db, "SELECT a.*,q.period_end,q.identity_status,q.first_public_result_date,q.source_availability_date,max(coalesce(q.first_public_result_date,''),coalesce(q.source_availability_date,'')) context_date,q.quarter_id canonical_quarter_id,c.company_key,c.company_name FROM v4_result_publication_authority a LEFT JOIN v4_quarter q USING(company_id,fiscal_year,fiscal_quarter) LEFT JOIN company c USING(company_id) WHERE a.status<>'VERIFIED' AND a.company_id=? ORDER BY a.company_id,a.fiscal_year,a.fiscal_quarter", (key[0],))
    _check(rows == snapshot['company_open_scope'], 'CURRENT_FISCAL_CONTEXT_CHANGED')
    security_ids = sorted({r['security_id'] for r in snapshot['canonical']['security']})
    for table, expected in (identity_tables if identity_tables is not None else snapshot['identity_tables']).items():
        _check(table in {'provider_security_identity', 'fundamentals_economic_structural_event'}, 'IDENTITY_TABLE_INVALID')
        exists = db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (table,)).fetchone()
        if not exists:
            actual = []
        elif table == 'provider_security_identity':
            actual = legacy._rows(db, 'SELECT * FROM '+table+' WHERE security_id IN ('+
                                  ','.join('?' for _ in security_ids)+')', security_ids) if security_ids else []
        else:
            actual = legacy._rows(db, 'SELECT * FROM '+table+' WHERE company_id=?', (key[0],))
        _check(sorted(actual,key=fingerprint) == sorted(expected,key=fingerprint), 'CURRENT_PERIMETER_CHANGED')


def validate_plan_extension(plan):
    _check(plan['candidate_evidence_provenance'] == MODE
           and plan['execution_context'] == 'APPROVED_FULL_COMPANY_RESOLVER_CONTEXT_V1' and all(plan.get(k) is False
               for k in ('publication_authorized', 'production_apply_authorized', 'executed')),
           'PLAN_EXECUTION_FLAGS')
    handoff = plan['approved_evidence_handoff']
    sources, snapshots, companies = validate_handoff(handoff, plan['approval_fingerprint'])
    _check(plan['policy_evidence_fingerprint'] == fingerprint(handoff['proposal']['proposed_policy_evidence'])
           and plan['proposal_fingerprint'] == handoff['proposal']['artifact_fingerprint']
           and plan['approved_handoff_fingerprint'] == handoff['handoff_fingerprint'], 'PLAN_APPROVAL_CHANGED')
    _check(set(map(tuple, plan['source_allowlist_keys'])) <= set(snapshots), 'UNAPPROVED_KEY')
    for case in plan['policy_cases']:
        key = _key(case);source = sources[key];record = plan['frozen_inputs'][case['frozen_input_reference']]
        _check(case['state'] == baseline_state(snapshots[key])
               and case['original_candidate_evidence'] == [source['events'][0]['evidence']]
               and case['observations'] == {source['events'][0]['evidence']['evidence_id']: source['events'][0]['observation']}
               and case['relations'] == source['relations']
               and record['filings'] == company_filings(companies[key[0]])
               and record['quarters'] == resolver_quarters(snapshots[key]), 'PLAN_FROZEN_INPUT_CHANGED')
    return snapshots


def revalidate_current(plan, db):
    snapshots = validate_plan_extension(plan)
    check_live_inputs(plan['approved_evidence_handoff'])
    for case in plan['policy_cases']:
        check_current_case(db, _key(case), snapshots[_key(case)], case['original_candidate_evidence'],
                           identity_tables=identity_tables_for_case(plan['approved_evidence_handoff'],
                                                                  _key(case), snapshots[_key(case)]))
