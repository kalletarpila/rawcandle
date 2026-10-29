"""Compact ownership display from returned results and bound legacy JSON only.

No database reads, lifecycle operations or persistence. New publication results
carry all display metadata. Older results may use their retained native receipts.
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping


def _exact_hash(value: Any) -> str:
    # Native ownership artifacts bind every field, including run-local identity.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _reason(value: Any) -> str:
    return re.sub(r'[0-9a-fA-F]{64}', '[see detailed artifacts]', str(value))


def _legacy_details(result: Mapping[str, Any], publication: Mapping[str, Any]) -> dict:
    """Read an older run's exact live receipt, never its copied Test generation."""
    run_id = publication.get('publication_run_id') or publication.get('generation_id')
    if not (isinstance(run_id, str) and run_id.startswith('pb_ownership_') and run_id[13:].isalnum()
            and result.get('artifact_dir') and publication.get('published_cases')):
        return {}
    lane = Path(result['artifact_dir']).parent / 'pb_ownership_publications' / run_id
    try:
        paths = [lane / 'preview.json', lane / 'completed_journal.json']
        if lane.is_symlink() or any(p.is_symlink() for p in paths):
            return {}
        preview, journal = [json.loads(p.read_text()) for p in paths]
        if not (preview['preview_id'] == journal['production_run_id'] == run_id
                and journal['new_generation_id'] == publication['generation_id']
                and journal['state'] == 'COMPLETED' and journal['postflight_state'] == publication['postflight']
                and preview['selection'] == publication['published_cases']
                and [s['case_id'] for s in journal['scope_evidence']['selected']] == publication['published_cases']
                and preview['artifact_sha256'] == journal['scope_evidence']['artifact_sha256'] == publication['artifact_sha256']
                and preview['preview_hash'] == journal['refresh_set_fingerprint']
                and preview['preview_hash'] == _exact_hash({k:v for k,v in preview.items() if k != 'preview_hash'})):
            return {}
        receipt_hash = _mapping(_mapping(result.get('ownership_auto')).get('cleanup')).get('ownership_receipt_hash')
        if receipt_hash and receipt_hash != _exact_hash(journal):
            return {}
        selected = preview['selected']
        if [s['case']['case_id'] for s in selected] != publication['published_cases']:
            return {}
        return dict(published_tickers=[s['case']['ticker'] for s in selected],
                    decision_types=sorted({s['approval'].get('decision_type') or s['record']['approval_mode'] for s in selected}),
                    queue_state='PUBLISHED', recovery=journal['rollback_recovery_state'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def ownership_summary_rows(result: Mapping[str, Any], *, include_artifacts: bool = False) -> tuple[str, ...]:
    own = _mapping(result.get('ownership_auto'))
    if not own:
        return ()
    rows = ['P/B ownership auto-continuation',
            f"Policy: {'enabled' if own.get('enabled') else 'disabled'} — {own.get('policy_version', 'not recorded')}",
            f"Financial precondition: {own.get('financial_precondition', 'not recorded')}; financial workflow: {own.get('financial_outcome', result.get('outcome', 'not recorded'))}"]
    if own.get('financial_reason_code'):
        rows[-1] += '; reason: ' + str(own['financial_reason_code'])
    if own.get('financial_precondition') == 'SAFE_FINANCIAL_NO_OP':
        rows.append('Financial STOPPED is preserved; local financial quarantines remain separate.')
    status = own.get('status', 'not recorded')
    rows.append('Ownership status: ' + str(status))
    if status == 'NO_AUTO_CANDIDATES':
        rows.append('No automatic ownership candidates; no publication in this run.'
                    + (' Manual/deep reviews remain held.' if own.get('manual_review') or own.get('deep_review') else ''))
    if own.get('reason'):
        rows.append('Ownership reason: ' + _reason(own['reason']))
    publication = dict(_mapping(own.get('publication')))
    published = bool(own.get('published')) and publication.get('outcome') in ('COMPLETED', 'ALREADY_PUBLISHED')
    if published:
        needed = ('published_tickers', 'decision_types', 'queue_state', 'recovery')
        if any(not publication.get(k) for k in needed):
            for key, value in _legacy_details(result, publication).items():
                if not publication.get(key):
                    publication[key] = value
        tickers = ', '.join(publication.get('published_tickers') or [])
        decisions = ', '.join(publication.get('decision_types') or [])
        rows.append(f"Published: {tickers or 'ticker not recorded'}" + (f' — {decisions}' if decisions else ''))
        rows.append('Ownership publication: ' + str(publication['outcome'])
                    + (' / ' + publication['queue_state'] if publication.get('queue_state') else ''))
        if publication.get('generation_id'):
            rows.append('Ownership generation: ' + publication['generation_id'])
        rows.append('Postflight: ' + str(publication.get('postflight') or 'not recorded'))
        rows.append('Recovery: ' + str(publication.get('recovery') or 'not recorded'))
        if not tickers or not decisions:
            rows.append('Some publication details are unavailable; see the original run artifacts.')
        cleanup = _mapping(own.get('cleanup'))
        cleanup_status = cleanup.get('cleanup_outcome') or cleanup.get('status') or own.get('cleanup_status')
        if cleanup_status:
            text = 'Cleanup: ' + str(cleanup_status)
            deleted, freed = cleanup.get('files_deleted'), cleanup.get('bytes_freed')
            if isinstance(deleted, list):
                text += f' — {len(deleted)} backups'
            if type(freed) is int and freed >= 0:
                text += f' / {freed / 1_000_000_000:.2f} GB ({freed:,} bytes freed)'
            rows.append(text)
            if cleanup.get('reason'):
                rows.append('Cleanup reason: ' + _reason(cleanup['reason']))
    elif publication.get('outcome'):
        rows.append('Ownership publication: ' + str(publication['outcome']))
        for label, key in (('Postflight', 'postflight'), ('Recovery', 'recovery')):
            if publication.get(key):
                rows.append(label + ': ' + str(publication[key]))
    rows.append(f"Evaluated {own.get('evaluated',0)} | Automatic {own.get('auto_continued',0)} | "
                f"Manual {own.get('manual_review',0)} | Deep {own.get('deep_review',0)} | "
                f"Published {own.get('published',0)} | Failed/stale {own.get('failed_stale',0)}")
    if include_artifacts:
        if own.get('preview_path'):
            rows.append('Ownership Preview (observations, factors, deltas, warnings and P/B): ' + str(own['preview_path']))
        if own.get('test_receipt'):
            rows.append('Ownership Test receipt: ' + str(own['test_receipt']))
    return tuple(rows)
