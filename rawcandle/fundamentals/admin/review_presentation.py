"""Action-first views of existing review states and backend action eligibility.

Pure presentation: no evaluation, database access, state transitions or writes.
Unknown states remain visible as current work rather than being hidden as history.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .refresh_review_queue import OPEN_STATUSES, SUPPORTED_ACTIONS, BLOCKED_ACTIONS


@dataclass(frozen=True)
class ReviewPresentation:
    display_status: str
    classification: str
    needs_action: bool
    next_action: str
    next_action_explanation: str
    history_or_terminal: bool
    allowed_actions: tuple[str, ...]
    blocked_action_reason: str
    reason: str
    reason_codes: tuple[str, ...]


LABELS = {
    'SOURCE_PAYLOAD_CAPTURE_UNVERIFIED':'Provider capture is unverified',
    'SOURCE_PAYLOAD_INCOMPLETE':'Provider source evidence is incomplete',
    'TRUE_SOURCE_REMOVAL': 'Published source observation missing',
    'PROVIDER_ANOMALY_SUSPECTED': 'Provider history anomaly',
    'REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION': 'Fiscal identity change requires review',
    'CONTINUATION_CANDIDATE': 'Quarterly ownership continuation',
    'REVIEW_REQUIRED_FACTOR_CHANGE': 'Provider factor change requires review',
    'REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE': 'Security class or ownership perimeter review',
    'REVIEW_REQUIRED_IDENTITY_CHANGE': 'Security identity review',
    'REVIEW_REQUIRED_INVALID_SHARE_BASIS': 'Share evidence requires review',
    'REVIEW_REQUIRED_OTHER': 'Ownership evidence review',
}
REASONS = {
    'INTERIOR_SOURCE_KEY_REMOVAL': 'An interior published source key disappeared from the complete provider response.',
    'SAME_FISCAL_SOURCE_KEY_REPLACEMENT': 'A same-fiscal source key replacement was detected.',
    'BOUNDARY_FISCAL_WINDOW_TOO_SHORT': 'Provider history is shorter than the required rolling-history window.',
    'OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW': 'The oldest source observation reached the rolling-history boundary.',
    'RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON': 'Historical source evidence is retained outside the current review horizon.',
    'SOURCE_PAYLOAD_INCOMPLETE': 'Provider source evidence is incomplete for this operation.',
    'SOURCE_PAYLOAD_CAPTURE_UNVERIFIED': 'This record was not captured from a verified full provider payload.',
    'EXPLICIT_POLICY_HOLD': 'An explicit hold blocks automatic continuation.',
}


def classification_label(code: str) -> str:
    return LABELS.get(code, code.replace('_', ' ').capitalize())


def provider_review(item: Mapping[str, Any]) -> ReviewPresentation:
    status = str(item.get('status') or 'UNKNOWN')
    classification = str(item.get('classification') or item.get('review_type') or 'UNKNOWN')
    codes = tuple(str(c) for c in item.get('reason_codes') or ())
    terminal = status == 'RESOLVED'
    actions = ['VIEW_DETAILS']
    # Wait/Retry are supported for unresolved items by apply_action; approval
    # buttons additionally require the existing backend eligibility booleans.
    if status in OPEN_STATUSES:
        actions += [a for a in ('WAIT_FOR_PROVIDER', 'RETRY_REEVALUATION')
                    if a in SUPPORTED_ACTIONS and a not in BLOCKED_ACTIONS]
        for field, action in (('accept_retained_history_eligible', 'ACCEPT_RETAINED_HISTORY'),
                              ('accept_fiscal_revision_eligible', 'ACCEPT_FISCAL_IDENTITY_REVISION'),
                              ('confirm_true_removal_eligible', 'CONFIRM_TRUE_SOURCE_REMOVAL')):
            if item.get(field) is True and action in SUPPORTED_ACTIONS and action not in BLOCKED_ACTIONS:
                actions.append(action)
    reason = next((REASONS[c] for c in ('INTERIOR_SOURCE_KEY_REMOVAL', 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT') if c in codes), None)
    reason = reason or next(iter(item.get('reason_explanations') or ()), None) or item.get('human_summary') or 'Inspect the persisted source-history evidence.'
    blocked = ''
    if not terminal and item.get('accept_retained_history_eligible') is not True:
        blocked = 'Retained-history approval unavailable: ' + str(item.get('accept_retained_history_reason') or 'Backend eligibility has not been established.')
    waiting = status == 'WAITING_PROVIDER'
    pending = status == 'RETRY_REEVALUATION' or bool(item.get('approval_pending_publication'))
    needs_action = not terminal and not waiting and not pending
    explanation = ''
    if terminal:
        next_action = 'No action required.'
        reason = 'This source-history review is resolved.'
    elif item.get('approval_pending_publication'):
        next_action = 'Review the next normal workflow result.'
        explanation = 'Approval is already recorded; Preview/Test/Production still revalidate it.'
    elif waiting:
        next_action = 'Wait for Providers; Retry reevaluation after source data changes if needed.'
        explanation = 'Waiting is already recorded. No immediate operator action is required.'
    elif pending:
        next_action = 'Inspect the next normal Preview result.'
        explanation = 'Reevaluation is already requested; this is still a current review, not resolved history.'
    elif 'ACCEPT_RETAINED_HISTORY' in actions:
        next_action = 'Review exact retained-history evidence.'
    elif 'ACCEPT_FISCAL_IDENTITY_REVISION' in actions:
        next_action = 'Review the exact fiscal-revision evidence.'
    elif 'CONFIRM_TRUE_SOURCE_REMOVAL' in actions:
        next_action = 'Review the exact true source removal confirmation.'
    else:
        options = [label for action,label in (('WAIT_FOR_PROVIDER','Wait for Providers'),('RETRY_REEVALUATION','Retry reevaluation after source data changes')) if action in actions]
        next_action = ' or '.join(options) + '.' if options else 'Inspect persisted evidence.'
        explanation = 'Inspect the retained evidence if this persists. Wait/Retry does not grant approval.' if blocked else ''
        if (status == 'OPEN' and classification == 'TRUE_SOURCE_REMOVAL'
                and item.get('accept_retained_history_eligible') is False
                and {'INTERIOR_SOURCE_KEY_REMOVAL', 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT'}.intersection(codes)):
            # Guidance only: never add actions, infer persistence, or escalate state.
            if 'WAIT_FOR_PROVIDER' in actions:
                next_action = 'Recommended now: Wait for Providers.'
            stages = []
            if 'RETRY_REEVALUATION' in actions:
                stages.append('After later provider/source refresh: Retry reevaluation after source data changes.')
            if 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT' in codes:
                stages.append('If replacement persists: Manually inspect old vs new source binding and financial payload before any retained-history or repair decision.')
            else:
                stages.append('If still unresolved: Investigate source history manually.')
            stages.append('Guidance only; no automatic escalation. Wait/Retry does not grant approval.')
            explanation = '\n'.join(stages)
    if not terminal and {'SOURCE_PAYLOAD_INCOMPLETE','SOURCE_PAYLOAD_CAPTURE_UNVERIFIED'}.intersection(codes):
        next_action='Reacquire provider source, then Retry reevaluation.'
        explanation='Use controlled source repair or current-state rebuild where appropriate; no financial or historical approval is granted.'
        reason=REASONS[next(c for c in codes if c in ('SOURCE_PAYLOAD_INCOMPLETE','SOURCE_PAYLOAD_CAPTURE_UNVERIFIED'))]
    from .historical_freeze import HELD, REVIEW_REASON
    frozen = any(d.get('decision') == HELD for d in
                 ((item.get('review_context') or {}).get('historical_freeze') or {}).get('conflicts', []))
    display_status = str(item.get('operator_status_label') or (status + (' — no action required' if terminal else '')))
    if frozen and not terminal and not item.get('approval_pending_publication'):
        display_status = 'Historical value preserved'
        classification = REVIEW_REASON
        needs_action = False
        reason = 'Provider data changed for a period ending on or before 2024-12-31. Accepted history was preserved.'
        next_action = 'No immediate action required.'
        explanation = 'Review only if you intend to repair this historical period. Wait/Retry does not authorize a historical repair.'
    return ReviewPresentation(
        display_status=display_status, classification=classification,
        needs_action=needs_action, next_action=next_action, next_action_explanation=explanation,
        history_or_terminal=terminal, allowed_actions=tuple(actions), blocked_action_reason=blocked,
        reason=str(reason), reason_codes=codes)


def ownership_review(item: Mapping[str, Any], policy: Mapping[str, Any] | None = None, *, policy_enabled: bool | None = None) -> ReviewPresentation:
    status = str(item.get('status') or 'UNKNOWN')
    classification = str(item.get('classification') or 'UNKNOWN')
    policy = policy or {}
    codes = tuple(str(r['reason']) for r in policy.get('reasons') or () if isinstance(r, Mapping) and r.get('reason'))
    terminal = status in ('PUBLISHED', 'SUPERSEDED')
    actions = ['VIEW_DETAILS']
    if status == 'OPEN':
        if classification == 'CONTINUATION_CANDIDATE':actions.append('APPROVE_OWNERSHIP')
        actions.append('KEEP_ON_HOLD')
    eligibility = item.get('publication_eligibility') or {}
    if status in ('APPROVED', 'AUTO_CONTINUED') and eligibility.get('status') != 'STALE_OR_UNAVAILABLE':
        actions.append('PREVIEW_PUBLICATION')
    automatic = status == 'OPEN' and policy_enabled is True and policy.get('partition') == 'AUTO_CONTINUE'
    blocked = ''
    if status == 'PUBLISHED':
        reason, next_action = 'This exact ownership observation has already been published.', 'No action required.'
    elif status == 'SUPERSEDED':
        reason, next_action = 'A newer source observation superseded this case.', 'No action required; historical evidence only.'
    elif status in ('APPROVED','AUTO_CONTINUED'):
        reason = 'Automatic decision pending publication.' if status == 'AUTO_CONTINUED' else 'Operator approval pending publication.'
        next_action = 'Review the controlled publication Preview.' if 'PREVIEW_PUBLICATION' in actions else 'Inspect the stale or unavailable publication evidence.'
        if eligibility.get('status') == 'STALE_OR_UNAVAILABLE':blocked = str(eligibility.get('reason') or 'Publication evidence requires revalidation.')
    elif automatic:
        reason, next_action = 'Current policy evidence permits automatic continuation.', 'Normal Full Workflow evaluates this case automatically; manual approval is optional.'
    else:
        reason = '; '.join(REASONS.get(c,c.replace('_',' ').capitalize()) for c in codes[:2]) or classification_label(classification)
        next_action = 'Inspect held ownership evidence.' if status == 'HELD' else 'Review ownership evidence and available actions.'
        if 'APPROVE_OWNERSHIP' not in actions:
            blocked = 'Ordinary continuation approval is unavailable in this state/classification; inspect the evidence.'
    return ReviewPresentation(
        display_status=status + (' — no action required' if status == 'PUBLISHED' else ' — historical' if status == 'SUPERSEDED' else ''),
        classification=classification, needs_action=not terminal and not automatic, next_action=next_action,
        next_action_explanation=('Policy partition: ' + str(policy['partition']) if policy.get('partition') and not terminal else ''),
        history_or_terminal=terminal, allowed_actions=tuple(actions), blocked_action_reason=blocked,
        reason=reason, reason_codes=codes)


def review_groups(items: Sequence[Mapping[str, Any]], presenter: Callable[[Mapping[str, Any]], ReviewPresentation]):
    paired = [(item, presenter(item)) for item in items]
    paired.sort(key=lambda p:(not p[1].needs_action, str(p[0].get('ticker') or ''), str(p[0].get('case_id') or '')))
    return ([p for p in paired if not p[1].history_or_terminal], [p for p in paired if p[1].history_or_terminal])
