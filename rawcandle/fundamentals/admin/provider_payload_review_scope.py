"""Prove that current payload repair cannot consume another review's authority."""
from __future__ import annotations

from pathlib import Path

from . import historical_freeze as freeze
from .contracts import fingerprint
from .provider_payload import payload_fingerprint
from .refresh_review_queue import RefreshReviewQueue
from .refresh_fundamentals import source_key


def prove(proposals, queue_path, canonical_db, provider_db):
    """Read-only, fail closed on any relevant review except proven disjoint freeze.

    A disjoint review remains OPEN. No permission to change its source, financial
    state or decision is returned. The whole proof is fingerprinted for Test/live.
    """
    from .provider_payload_workflow import _ro
    reviews={r['ticker']:r for r in RefreshReviewQueue(Path(queue_path)).list_items()}
    items=[]
    with _ro(Path(canonical_db)) as c:
        for proposal in proposals:
            ticker=proposal['ticker'];identity=proposal['identity'];oid=proposal['comparison']['old_observation_id']
            rows=c.execute('''SELECT q.* FROM v4_quarter q JOIN v4_field_provenance p USING(quarter_id)
                WHERE p.canonical_field='shares_outstanding' AND p.provider_observation_id=?
                AND q.identity_status='ACCEPTED' ''',(oid,)).fetchall()
            if (len(rows)!=1 or rows[0]['company_id']!=identity['company_id']
                    or rows[0]['period_end']<=freeze.CUTOFF):
                raise ValueError('PAYLOAD_REVIEW_CURRENT_NONFROZEN_BINDING_REQUIRED')
            q=rows[0]
            selected=tuple(proposal['source_key']);review=reviews.get(ticker)
            record=dict(ticker=ticker,proposal_fingerprint=proposal['proposal_fingerprint'],
                quarter_id=q['quarter_id'],observation_id=oid,review_fingerprint=None,
                proof='NO_OPEN_SOURCE_REVIEW',frozen_conflict_count=0)
            if review:
                context=review.get('review_context') or {};history=context.get('historical_freeze') or {}
                binding=context.get('identity_binding') or {}
                if (review['review_type']!=freeze.REVIEW_REASON
                        or set(review.get('reason_codes') or [])!={freeze.REVIEW_REASON}
                        or context.get('scope')!='TICKER_LOCAL_REVIEW'
                        or binding.get('status')!='KNOWN'
                        or any(binding.get(k)!=identity.get(k) for k in ('company_id','security_id','provider_security_id'))
                        or history.get('policy')!=freeze.VERSION or history.get('cutoff')!=freeze.CUTOFF
                        or not history.get('conflicts') or not review.get('affected_source_keys')):
                    raise ValueError('PAYLOAD_REVIEW_AUTHORITY_UNRESOLVED:'+ticker)
                accepted={ (r['company_id'],r['fiscal_year'],r['fiscal_quarter']):r
                    for r in freeze.accepted_history(canonical_db,provider_db,identity['company_id']) }
                examined=set();seen=set()
                for conflict in history['conflicts']:
                    key=tuple(conflict['identity']);actual=accepted.get(key)
                    if (key in seen or actual is None or conflict.get('decision')!=freeze.HELD
                            or conflict.get('repair_binding') or conflict.get('policy')!=freeze.VERSION
                            or conflict.get('cutoff')!=freeze.CUTOFF
                            or conflict.get('evidence_fingerprint')!=fingerprint({k:v for k,v in conflict.items() if k!='evidence_fingerprint'})
                            or conflict.get('accepted')!=freeze.financial_state(actual)
                            or conflict.get('accepted_source')!=actual['_accepted_source']
                            or conflict.get('period_end')!=actual['period_end']):
                        raise ValueError('PAYLOAD_REVIEW_FROZEN_EVIDENCE_STALE:'+ticker)
                    seen.add(key)
                    sources=[conflict['accepted_source'],conflict.get('incoming_source'),*(conflict.get('incoming_candidates') or [])]
                    for source in (s for s in sources if s is not None):
                        sk=source_key(source)
                        if (sk[0]!=ticker or sk[1]!='ARQ' or sk[3]>freeze.CUTOFF
                                or sk==selected or source.get('_provider_observation_id')==oid):
                            raise ValueError('PAYLOAD_REVIEW_SOURCE_SCOPE_COLLISION:'+ticker)
                        examined.add(sk)
                affected={tuple(r[k] for k in ('ticker','dimension','date','reportperiod')) for r in review['affected_source_keys']}
                if not affected.issubset(examined) or selected in affected:
                    raise ValueError('PAYLOAD_REVIEW_AFFECTED_SCOPE_UNPROVEN:'+ticker)
                record.update(review_fingerprint=payload_fingerprint(review),
                    proof='DISJOINT_FROZEN_REVIEW_PRESERVED',frozen_conflict_count=len(seen))
            items.append(record)
    value={'schema':'PROVIDER_PAYLOAD_REVIEW_SCOPE_V1','items':sorted(items,key=lambda r:r['ticker'])}
    return {**value,'fingerprint':payload_fingerprint(value)}
