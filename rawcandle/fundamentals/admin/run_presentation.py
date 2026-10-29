"""Operational wording from retained structured facts; never an authorization gate."""
from __future__ import annotations
from typing import Any, Mapping

NO_ACTION = 'NO_ACTION'
REVIEW_WHEN_APPROPRIATE = 'REVIEW_WHEN_APPROPRIATE'
ACTION_REQUIRED = 'ACTION_REQUIRED'


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _display(value):
    return str(value) if value is not None else 'not recorded'


def source_scan(result: Mapping[str,Any]) -> dict:
    preview=result.get('refresh_preview') or {};discovery=preview.get('discovery') or {}
    source=result.get('source_summary') or {};counts=result.get('summary_counts') or {}
    decision=result.get('operational_decision') or {}
    candidates=_count(discovery.get('unique_changed_source_tickers'))
    if candidates is None:candidates=_count(source.get('discovered_tickers'))
    effective=_count(counts.get('effective_changed_known'))
    if effective is None:effective=_count(source.get('effective_changed_known'))
    safe=_count(decision.get('safe_effective_changes'))
    if safe is None:safe=_count(counts.get('safe_changes',source.get('safe_changes')))
    reviews=_count(decision.get('held_item_count'))
    if reviews is None:reviews=_count(counts.get('held_for_review',source.get('held_for_review')))
    return dict(source_candidates=candidates,effective_changes=effective,safe_changes=safe,reviews=reviews,
        rows=(f'Latest source scan: {_display(candidates)} source-change candidates flagged for comparison',
              f'Relevant Fundamentals changes: {_display(effective)} · Publishable safe changes: {_display(safe)}',
              f'Separate review items: {_display(reviews)}'))


def run_meaning(result: Mapping[str,Any]) -> dict:
    d=result.get('operational_decision') or {};terminal=result.get('terminal_summary') or {}
    own=result.get('ownership_auto') or {};test=d.get('test_gate') or {};production=d.get('production_gate') or {}
    counts=result.get('summary_counts') or {};source=result.get('source_summary') or {}
    outcome=result.get('outcome');preview=result.get('mode')=='PREVIEW'
    safe=_count(d.get('safe_effective_changes',counts.get('safe_changes',source.get('safe_changes'))))
    held=_count(d.get('held_item_count',counts.get('held_for_review',source.get('held_for_review'))))
    global_count=_count(d.get('global_blocker_count',counts.get('global_blockers',source.get('global_blockers'))))
    peer_clear=d.get('local_hold_blocked_safe_changes') is False
    code=d.get('decision_code');anomalies=[]
    for label,p in (('Financial',result.get('publication_outcome') or {}),('Ownership',own.get('publication') or {})):
        postflight=p.get('postflight');recovery=p.get('recovery') or p.get('rollback_recovery')
        if postflight and postflight not in ('PASSED','NOT_RUN'):anomalies.append(label+' postflight requires attention')
        if postflight=='NOT_RUN' and (result.get('production_completed') if label=='Financial' else own.get('published')):anomalies.append(label+' postflight not completed')
        if recovery and recovery!='NOT_REQUIRED':anomalies.append(label+' recovery requires attention')
    for cleanup in (terminal.get('terminal_cleanup') or {},own.get('cleanup') or {}):
        state=cleanup.get('cleanup_outcome') or cleanup.get('status')
        if state and state not in ('COMPLETED','ALREADY_CLEANED','NOT_REQUIRED'):anomalies.append('Cleanup requires attention')
    technical=(code=='TECHNICAL_FAILURE' or terminal.get('stop_kind')=='TECHNICAL_FAILURE' or
        bool(result.get('errors') or result.get('failed_stage') or terminal.get('reporting_integrity_error_count')) or
        outcome in ('FAILED','ERROR','INTERRUPTED','CORRUPT_OR_INCOMPLETE','FAILED_ROLLED_BACK','CRITICAL_ROLLBACK_FAILED','RECOVERY_FAILED','ROLLED_BACK') or
        bool(own.get('failed_stale')) or own.get('status')=='FAILED_OR_STALE')
    blocked=bool(global_count or d.get('global_blockers') or d.get('local_hold_blocked_safe_changes') is True)
    noop=(code=='NO_SAFE_CHANGES' and safe==0 and global_count==0 and test.get('authorized') is False and
          test.get('reason_code')=='NO_SAFE_CHANGES_TO_PUBLISH' and production.get('state')=='NOT_APPLICABLE')
    # Existing orchestrator precondition supports older retained workflow receipts.
    legacy_noop=(result.get('mode')=='FULL_WORKFLOW' and own.get('financial_outcome')=='STOPPED' and own.get('financial_precondition')=='SAFE_FINANCIAL_NO_OP')
    category=None;headline='Operational meaning not recorded';action='Inspect Details';meaning=headline
    if technical or anomalies:
        category=ACTION_REQUIRED;headline=('Preview failed — technical error' if preview else 'Technical / publication issue requires attention')
        meaning='Technical error' if technical else '; '.join(anomalies);action='Action required — inspect technical evidence'
    elif blocked:
        category=ACTION_REQUIRED;headline='Preview completed — publication blocked' if preview else 'Publication blocked'
        meaning='Publication blocked by required review';action='Action required — resolve the blocking review'
    elif noop or legacy_noop:
        category=REVIEW_WHEN_APPROPRIATE if preview and held else NO_ACTION
        headline='Preview completed — no new publishable changes' if preview else 'No new safe financial changes to publish'
        meaning='No new publishable changes'
        if held:meaning+=f' · {held} local reviews'
        if global_count==0:meaning+=' · no critical blocker'
        if held and peer_clear:meaning+=' · safe peer work not blocked'
        action='Review separately when appropriate' if category==REVIEW_WHEN_APPROPRIATE else 'No immediate action required'
    elif code=='PUBLICATION_COMPLETED' or (result.get('production_completed') is True and outcome=='COMPLETED'):
        category=NO_ACTION;headline='Publication completed successfully';meaning=f'{safe} tickers published' if safe is not None else 'Publication successful';action='No corrective action needed'
    elif preview and test.get('authorized') is True and safe is not None and safe>0:
        category=REVIEW_WHEN_APPROPRIATE;headline='Preview completed — safe changes ready for Test'
        meaning=f'{safe} safe changes ready for Test';action='Proceed to Test on copies'
    elif code=='TEST_COMPLETED':
        category=REVIEW_WHEN_APPROPRIATE if production.get('state')=='AUTHORIZED' else ACTION_REQUIRED
        headline='Test on copies completed';meaning=headline;action='Review existing Production authorization' if production.get('state')=='AUTHORIZED' else 'Action required — inspect Production authorization'
    elif code=='TEST_NOT_AUTHORIZED':
        category=ACTION_REQUIRED;headline='Preview completed — Test authorization needs attention'
        meaning='Test authorization prerequisite unresolved';action='Action required — inspect Test authorization'
    elif preview and outcome=='REVIEW_REQUIRED':
        headline='Preview completed — review required';meaning='Review required'
        if held is not None and held>0 and global_count==0 and peer_clear:
            category=REVIEW_WHEN_APPROPRIATE;meaning=f'{held} local reviews · safe peer work not blocked';action='Review separately when appropriate'
    elif outcome=='NO_CHANGE':
        category=NO_ACTION;headline='Preview completed — no new publishable changes' if preview else 'No changes needed publication'
        meaning='No changes needed publication';action='No corrective action needed'
    elif outcome=='COMPLETED':
        headline='Preview completed' if preview else 'Run completed';meaning=headline
    secondary=[]
    if held:
        tickers=[str(i['ticker']) for i in d.get('held_items') or [] if i.get('ticker')]
        secondary.append((', '.join(tickers) if tickers else str(held)+' items')+' remain separate review items.')
        if peer_clear:secondary.append('They did not block safe peer changes.')
    if preview and (noop or outcome=='NO_CHANGE'):secondary.insert(0,'No new financial changes need publication.')
    if _count(own.get('published')):
        meaning+=f" · P/B published {own['published']}"
    rows=(headline,*secondary,'Next action: '+action)
    return dict(category=category,headline=headline,meaning=meaning,action=action,rows=rows,
                safe_noop=bool((noop or legacy_noop) and not technical and not blocked and not anomalies),
                technical_failure=bool(technical),preview=preview,held_count=held,global_count=global_count)
