"""Concise structured display only; raw evidence and backend rules stay intact."""
from __future__ import annotations
from typing import Any, Mapping

from .review_presentation import ReviewPresentation, classification_label, provider_review, ownership_review
from .operational_presentation import NORMAL, boundary_route


def decision_label(item: Mapping[str, Any]) -> str:
    approval = item.get('approval') or {}
    return str(approval.get('decision_type') or (approval.get('record') or {}).get('approval_mode') or 'Not recorded')


def historical_classification(code: str) -> str:
    return {'REVIEW_REQUIRED_FACTOR_CHANGE':'Factor change',
            'REVIEW_REQUIRED_IDENTITY_CHANGE':'Identity change',
            'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE':'Class / perimeter change',
            'REVIEW_REQUIRED_INVALID_SHARE_BASIS':'Share basis',
            'REVIEW_REQUIRED_OTHER':'Ownership evidence',
            'CONTINUATION_CANDIDATE':'Quarterly continuation'}.get(code,classification_label(code))


def provider_card_fields(item: Mapping[str, Any], view: ReviewPresentation) -> tuple[str, ...]:
    codes = set(view.reason_codes)
    reason = (view.reason if view.classification == 'FROZEN_HISTORICAL_PROVIDER_CONFLICT' else
              'Same-fiscal source key replacement detected' if 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT' in codes else
              'Interior source key disappeared' if 'INTERIOR_SOURCE_KEY_REMOVAL' in codes else view.reason)
    rows = [f'Reason: {reason}']
    if view.classification == 'FROZEN_HISTORICAL_PROVIDER_CONFLICT':
        rows.append('Accepted history changed: No · Provider evidence changed: Yes')
    staged = (item.get('status')=='OPEN' and view.classification=='TRUE_SOURCE_REMOVAL'
              and not item.get('approval_pending_publication')
              and item.get('accept_retained_history_eligible') is False and
              bool(codes & {'INTERIOR_SOURCE_KEY_REMOVAL','SAME_FISCAL_SOURCE_KEY_REPLACEMENT'}) and
              not any(action in view.allowed_actions for action in ('ACCEPT_FISCAL_IDENTITY_REVISION','CONFIRM_TRUE_SOURCE_REMOVAL')))
    if staged:
        if 'WAIT_FOR_PROVIDER' in view.allowed_actions:rows.append('Recommended now: Wait for Providers')
        if 'RETRY_REEVALUATION' in view.allowed_actions:rows.append('Then: Retry after later provider/source refresh')
        rows.append('If replacement persists: Inspect old vs new source binding / financial payload before any retained-history or repair decision'
                    if 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT' in codes else
                    'If still unresolved: Investigate source history manually')
    else:
        rows.append('Recommended now: '+view.next_action)
        if view.next_action_explanation:rows.append(view.next_action_explanation)
    rows.append('Approval: '+('available — inspect exact evidence' if any(a in view.allowed_actions for a in
        ('ACCEPT_RETAINED_HISTORY','ACCEPT_FISCAL_IDENTITY_REVISION','CONFIRM_TRUE_SOURCE_REMOVAL')) else 'unavailable'))
    return tuple(rows)


def evidence_summary(kind: str, item: Mapping[str, Any], *, view: ReviewPresentation | None = None) -> tuple[str, ...]:
    if kind == 'ownership':
        view = view or ownership_review(item)
        previous,new = item.get('previous') or {},item.get('new') or {}
        result = item.get('result') or {};publication = result.get('publication') or {}
        rows = [f"Ticker: {item.get('ticker','Not recorded')}",f"Review status: {item.get('status','Not recorded')}",
                'Decision: '+decision_label(item),f"Ownership type: {previous.get('release_type') or previous.get('economic_unit_rule') or 'Not recorded'}",
                f"Provider factor: {previous.get('provider_declared_factor','Not recorded')} → {new.get('sharefactor','Not recorded')}",
                f"Shares: {previous.get('accepted_sharesbas','Not recorded')} → {new.get('sharesbas','Not recorded')} · delta {(item.get('deltas') or {}).get('shares_percent','Not recorded')}%"]
        for label,value in (
            ('Publication generation',publication.get('generation_id')),
            ('Postflight',publication.get('postflight') or result.get('postflight')),
            ('Recovery',publication.get('recovery') or result.get('recovery')),
            ('Cleanup',result.get('cleanup') or publication.get('cleanup'))):
            if isinstance(value, Mapping):value=value.get('cleanup_outcome') or value.get('status')
            if value is not None:rows.append(f'{label}: {value}')
        rows.append('Action required: '+('Yes' if view.needs_action else 'No'))
        return tuple(rows)
    if kind == 'provider':
        view = view or provider_review(item)
        freeze_rows = []
        for d in ((item.get('review_context') or {}).get('historical_freeze') or {}).get('conflicts', []):
            old, new = d.get('accepted_source') or {}, d.get('incoming_source') or {}
            freeze_rows.extend((f"Period end: {d.get('period_end')} · Fiscal identity: {d.get('identity')}",
                f"Accepted source: {old.get('date')} / {old.get('reportperiod')} · Incoming: {new.get('date', 'absent')} / {new.get('reportperiod', 'absent')}",
                *[f"{field}: accepted {values.get('accepted')} → provider {values.get('incoming')}"
                  for field,values in (d.get('value_changes') or {}).items()],
                f"Evidence fingerprint: {d.get('evidence_fingerprint')}",
                'Repair eligibility: existing exact reviewed evidence required; ordinary provider evidence grants no repair.'))
        return (f"Ticker: {item.get('ticker','Not recorded')}",f"Review status: {item.get('status','Not recorded')}",
                'Classification: '+classification_label(view.classification),*provider_card_fields(item,view),
                'Approval availability: '+(view.blocked_action_reason or 'See permitted actions and exact evidence.'), *freeze_rows)
    if kind == 'boundary':
        proposal = item.get('proposal') or {};evidence=proposal.get('evidence') or {}
        arq,mrq=evidence.get('arq') or {},evidence.get('mrq') or {}
        return (f"Accounting-boundary review — {item.get('status','Not recorded')}",
                f"Ticker: {(evidence.get('identity') or {}).get('ticker','Not recorded')}",
                f"ARQ source: {arq.get('source_key','Not recorded')}",
                f"Fiscal labels: {arq.get('provider_label','Not recorded')} → {arq.get('accepted_label','Not recorded')}",
                f"MRQ historical source: {mrq.get('removed_key','Not recorded')}",
                f"MRQ current source: {mrq.get('current_key','Not recorded')}",
                'Action required: '+('No — operator review recorded; this does not assert publication.' if boundary_route(item).mode==NORMAL else 'Yes — inspect current accounting-boundary evidence.'))
    if kind == 'publication':
        return (f"Selected approved cases: {len(item.get('selection') or [])}",
                f"Score invariance: {item.get('score_invariance','Not recorded')}",
                f"Source revalidation: {item.get('source_revalidation','Not recorded')}")
    if kind == 'diagnostic':
        case=item.get('case') or {}
        return (f"Ticker: {item.get('ticker') or case.get('ticker','Not recorded')}",
                f"Policy partition: {item.get('partition','Not recorded')}",
                'No matching persisted review row; inspect current source diagnostics before any decision.')
    return tuple(f'{key}: {value}' for key,value in item.items())
