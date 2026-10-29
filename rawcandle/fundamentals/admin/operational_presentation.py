"""Read-only operational views; never authorize an action or infer persistence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .review_presentation import ReviewPresentation

NORMAL = 'NORMAL'
REVIEW = 'REVIEW'
DEEP_REVIEW = 'DEEP_REVIEW'


@dataclass(frozen=True)
class OperationalRoute:
    mode: str
    deep_guidance: str = ''


def review_route(view: ReviewPresentation, *, policy: Mapping[str, Any] | None = None) -> OperationalRoute:
    if view.history_or_terminal:
        return OperationalRoute(NORMAL)
    if policy and policy.get('partition') == 'DEEP_REVIEW/BLOCKED':
        return OperationalRoute(DEEP_REVIEW, 'Inspect ownership evidence before any decision.')
    # These codes supply conditional investigation advice, not a claim that
    # OPEN has persisted or that the backend has escalated the review.
    if 'SAME_FISCAL_SOURCE_KEY_REPLACEMENT' in view.reason_codes:
        guidance = 'If replacement persists: inspect old vs new source binding and financial payload before any retained-history or repair decision.'
    elif 'INTERIOR_SOURCE_KEY_REMOVAL' in view.reason_codes:
        guidance = 'If still unresolved: investigate source history manually.'
    else:
        guidance = ''
    return OperationalRoute(REVIEW if view.needs_action else NORMAL, guidance)


def boundary_route(item: Mapping[str, Any]) -> OperationalRoute:
    # Completed operator review belongs to audit. APPROVED still does not mean
    # published or authorize Production; this only controls operator attention.
    if item.get('status') in ('APPROVED','RESOLVED','PUBLISHED','SUPERSEDED'):
        return OperationalRoute(NORMAL)
    return OperationalRoute(DEEP_REVIEW, 'Inspect the recorded accounting-boundary status and exact evidence; approval does not authorize Production.')


def workflow_view(result: Mapping[str, Any]) -> dict[str, Any]:
    """Compact structured outcome display, separate from native report/gates."""
    from .run_presentation import run_meaning, ACTION_REQUIRED
    interpreted = run_meaning(result)
    terminal = result.get('terminal_summary') or {}
    own = result.get('ownership_auto') or {}
    financial = own.get('financial_outcome') or result.get('outcome') or 'UNKNOWN'
    safe_noop = financial == 'STOPPED' and (own.get('financial_precondition') == 'SAFE_FINANCIAL_NO_OP' or interpreted['safe_noop'])
    running = result.get('status') == 'running' or result.get('workflow_status') == 'RUNNING'
    rows = [f"Financial workflow: {financial}" + (' — safe no-op (NO_SAFE_CHANGES)' if safe_noop else '')]
    financial_published = result.get('production_completed')
    rows.append('Financial publication: ' + ('Yes' if financial_published is True else 'No' if financial_published is False else 'Not recorded'))
    publication = result.get('publication_outcome') or {}
    own_publication = own.get('publication') or {}
    reviews = terminal.get('review_required_count', (result.get('source_summary') or {}).get('held_for_review'))
    rows.append('Waiting for financial review: ' + (str(reviews) if reviews is not None else 'Not recorded'))
    if own:
        rows.append(f"P/B auto-continuation: {own.get('status', 'UNKNOWN')} · published {own.get('published', 0)} · manual {own.get('manual_review', 0)} / deep {own.get('deep_review', 0)}")
    else:
        rows.append('P/B auto-continuation: Not recorded')
    anomalies = []
    for label, source in (('Financial', publication), ('Ownership', own_publication)):
        postflight = source.get('postflight')
        recovery = source.get('recovery') or source.get('rollback_recovery')
        if postflight and (postflight not in ('PASSED', 'NOT_RUN') or
                          (postflight == 'NOT_RUN' and (financial_published is True if label == 'Financial' else own.get('published')))):
            anomalies.append(f'{label} postflight: {postflight}')
        if recovery and recovery != 'NOT_REQUIRED':
            anomalies.append(f'{label} recovery: {recovery}')
    for label, cleanup in (('Financial', terminal.get('terminal_cleanup') or {}), ('Ownership', own.get('cleanup') or {})):
        state = cleanup.get('cleanup_outcome') or cleanup.get('status')
        if state and state not in ('COMPLETED', 'ALREADY_CLEANED', 'NOT_REQUIRED'):
            anomalies.append(f'{label} cleanup: {state}')
    if result.get('errors') or terminal.get('reporting_integrity_error_count'):
        anomalies.append('Workflow errors or reporting-integrity problems recorded')
    if own.get('failed_stale') or own.get('status') == 'FAILED_OR_STALE':
        anomalies.append('P/B auto-continuation failed or became stale')
    failed = financial not in ('COMPLETED', 'NO_CHANGE') and not safe_noop
    stage = terminal.get('failure_stage') or terminal.get('authoritative_stage') or result.get('current_stage')
    if failed and not running and stage:
        rows.append(f'Failed/stopped stage: {stage}')
    deep = bool(anomalies) or interpreted['category']==ACTION_REQUIRED
    attention = bool(reviews or own.get('manual_review') or own.get('deep_review'))
    mode = DEEP_REVIEW if deep or own.get('deep_review') else REVIEW if attention or failed else NORMAL
    if running:
        mode = DEEP_REVIEW if anomalies else NORMAL
        rows.insert(0, 'Full Workflow: running')
        next_action = 'Wait for the current workflow result.'
    elif mode == DEEP_REVIEW:
        next_action = 'Open Deep Review / workflow evidence before retrying.'
    elif mode == REVIEW:
        next_action = 'Review local exceptions separately when appropriate.' if interpreted['safe_noop'] else 'Review current exceptions; safe automatic work remains separate.'
    else:
        next_action = 'None — no corrective workflow action required.'
    rows.extend(anomalies)
    rows.append('Action required: ' + ('No immediate action while running' if running else 'No' if mode == NORMAL else
        'No immediate corrective workflow action; review separately' if mode==REVIEW and interpreted['safe_noop'] else 'Yes'))
    rows.append('Next action: ' + next_action)
    return dict(mode=mode, rows=tuple(rows), financial_outcome=financial, running=running,
                ownership_status=own.get('status'), ownership_published=own.get('published'),
                human_summary=interpreted['headline'] if interpreted['category'] is not None else rows[0])


def normal_summary(*, loaded: bool, review_count: int, deep_count: int,
                   safety: Mapping[str, Any], settings: Mapping[str, Any],
                   last_workflow: Mapping[str, Any] | None = None, running: bool = False,
                   error: str = '', pending_reviews: int = 0) -> tuple[str, ...]:
    last_workflow = last_workflow or {}
    running = running or bool(last_workflow.get('running'))
    blocked = safety.get('production_writes_blocked') is True
    safety_unknown = safety.get('status') in (None,'UNKNOWN','CHECKING')
    mode = DEEP_REVIEW if blocked or deep_count or last_workflow.get('mode') == DEEP_REVIEW else REVIEW if review_count or error or not loaded or safety_unknown or last_workflow.get('mode') == REVIEW else NORMAL
    rows = [f"Fundamentals: {'REVIEW REQUIRED' if mode == REVIEW else mode}" + (' — running' if running or last_workflow.get('running') else '')]
    if blocked:
        rows.append('Publication/recovery requires attention; production writes remain blocked.')
    elif safety_unknown:
        rows.append('Publication safety: not loaded / checking.')
    if error:rows.append(error)
    rows.append('Safe publication within Full Workflow: automatic' if settings.get('full_workflow') is True else 'Safe publication: Full Workflow only; scheduler setting unavailable or not FULL_WORKFLOW')
    enabled = settings.get('ownership_enabled')
    rows.append('P/B auto-continuation: ' + ('enabled' if enabled is True else 'disabled' if enabled is False else 'not loaded'))
    rows.append(f'Current reviews requiring action: {review_count}' if loaded else 'Current reviews: not loaded')
    if pending_reviews:rows.append(f'Current reviews waiting on provider/workflow: {pending_reviews}')
    rows.append(f'Deep reviews requiring action: {deep_count}' if loaded else 'Deep reviews: not loaded')
    if last_workflow.get('rows'):
        rows.append('Last workflow: ' + (last_workflow.get('human_summary') or last_workflow['rows'][0]))
    else:
        rows.append('Last workflow: not loaded / no retained Full Workflow found')
    if last_workflow.get('ownership_status'):
        rows.append(f"Last P/B auto-continuation: {last_workflow['ownership_status']} · published {last_workflow.get('ownership_published',0)}")
    rows.append('Next action: ' + ('Wait for the running workflow.' if running else
                'Open Deep Review.' if mode == DEEP_REVIEW else 'Review current exceptions.' if mode == REVIEW else 'None — no action required.'))
    return tuple(rows)
