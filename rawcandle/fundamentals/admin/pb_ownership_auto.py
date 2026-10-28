"""Fail-closed ordinary-quarter decisions; publication remains a separate owner."""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, localcontext
import json
import math
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from . import pb_ownership_review as review
from .contracts import fingerprint
from .provider_payload import completeness, payload_fingerprint

POLICY = 'PB_ORDINARY_AUTO_CONTINUATION_V1'
# Versioned full SF1 acquisition shape observed in the current/recent cohort.
# Nullable metrics remain nullable; removing any field is a completeness gap.
SF1_FIELDS = frozenset('''accoci assets assetsavg assetsc assetsnc assetturnover bvps calendardate capex cashneq cashnequsd consolinc cor currentratio date de debt debtc debtnc debtusd deferredrev depamor deposits dimension divyield dps ebit ebitda ebitdamargin ebitdausd ebitusd ebt eps epsdil epsusd equity equityavg equityusd ev evebit evebitda fcf fcfps fiscalperiod fxusd gp grossmargin intangibles intexp invcap invcapavg inventory investments investmentsc investmentsnc lastupdated liabilities liabilitiesc liabilitiesnc marketcap ncf ncfbus ncfcommon ncfdebt ncfdiv ncff ncfi ncfinv ncfo ncfx netinc netinccmn netinccmnusd netincdis netincnci netmargin opex opinc payables payoutratio pb pe pe1 ppnenet prefdivis price ps ps1 receivables reportperiod retearn revenue revenueusd rnd roa roe roic ros sbcomp sgna sharefactor sharesbas shareswa shareswadil sps tangibles taxassets taxexp taxliabilities tbvps ticker workingcapital'''.split())


def evaluate(case: dict, *, canonical_db: Path, provider_db: Path, market_db: Path,
             as_of: str, queue_path: Path | None = None) -> dict:
    """Read-only policy result with deterministic evidence, suitable for rechecking."""
    from .refresh_fundamentals import load_current_history, resolve_identity, source_key, normalize_source_row, _raw_row
    from rawcandle.fundamentals.schema.prototype import stable_hash
    from rawcandle.fundamentals.schema.parent_equity import finite

    reasons = []; warnings = ['CORPORATE_ACTION_COVERAGE_INCOMPLETE', 'QUARTERLY_SHARES_ARE_A_DATED_APPROXIMATION']
    evidence = {'case_id': case['case_id'], 'candidate_hash': case['candidate_hash'], 'as_of': as_of,
                'prior_review_hash': case['prior_review_hash'], 'shares_delta': case['deltas'],
                'observation_id': case['new'].get('observation_id'), 'content_hash': case['new'].get('content_hash')}
    def block(reason, deep=True):
        reasons.append({'reason': reason, 'partition': 'DEEP_REVIEW/BLOCKED' if deep else 'MANUAL_REVIEW'})
    try:
        with closing(review._ro(canonical_db)) as c, closing(review._ro(provider_db)) as p, closing(review._ro(market_db)) as m:
            body={k:v for k,v in case.items() if k not in ('candidate_hash','status','approval','result')}
            if fingerprint(body)!=case['candidate_hash']:
                raise ValueError('PB_OWNERSHIP_CANDIDATE_HASH_INVALID')
            case=review._current(c, case, as_of=as_of)
            old, new = case['previous'], case['new']
            if (old.get('economic_unit_rule') != 'ORDINARY_COMMON' or old.get('reviewed_security_type') != 'COMMON_OR_ORDINARY'
                or old.get('identity_override') or old.get('release_type') != 'ORDINARY_COMMON'):
                block('UNSUPPORTED_OWNERSHIP_TYPE', False)
            if old.get('hold_reason') or new.get('explicit_policy_hold') or old.get('evidence_status') != 'REVIEWED_SUPPORTED':
                block('EXPLICIT_POLICY_HOLD', False)
            if (new.get('active_classes') != 1 or not new.get('security_active_as_of')
                or any(old[k] != new.get(k) for k in review.BINDING[:4])):
                block('SECURITY_IDENTITY_CHANGE')
            if new.get('category') != old.get('accepted_category') or new.get('category') not in review.COMMON:
                block('CATEGORY_CHANGE')
            if old.get('provider_declared_factor') is None or new.get('sharefactor') is None:
                block('SOURCE_PAYLOAD_INCOMPLETE')
            elif (isinstance(old['provider_declared_factor'],bool) or isinstance(new['sharefactor'],bool)
                  or old['provider_declared_factor'] != 1.0 or new['sharefactor'] != 1.0):
                block('FACTOR_REVIEW_REQUIRED')
            if (new.get('newer_share_count_required') or new.get('class_or_perimeter_conflict')
                or old.get('known_share_changes') or new.get('ownership_share_changes')):
                block('CORPORATE_ACTION_BLOCKER')
            identity = resolve_identity(SimpleNamespace(provider_db=provider_db, canonical_db=canonical_db), case['ticker'])
            evidence['source_identity'] = identity
            if identity.get('status') != 'KNOWN' or any(identity.get(k) != new.get(k) for k in ('company_id','company_key','security_id')):
                block('SOURCE_IDENTITY_AMBIGUOUS')
            metadata=[dict(r) for r in p.execute("SELECT * FROM sharadar_ticker_metadata WHERE table_name='fundamentals' AND ticker=?",(case['ticker'],))]
            evidence['provider_metadata']=metadata
            if len(metadata)!=1 or metadata[0].get('category')!=new.get('category') or str(metadata[0].get('isdelisted') or '').lower() in ('y','yes','true','1'):
                block('PROVIDER_LISTING_OR_CATEGORY_CONFLICT')
            obs = p.execute('SELECT * FROM provider_observation WHERE observation_id=?', (new.get('observation_id'),)).fetchone()
            if obs is None:
                block('SOURCE_OBSERVATION_MISSING')
            else:
                obs = dict(obs); raw = json.loads(obs['payload_json']); evidence['source_completeness'] = completeness(raw)
                if not SF1_FIELDS.issubset(raw) or any(raw.get(k) is None for k in ('sharefactor','sharesbas','equity','equityusd','price','marketcap','pb')):
                    block('SOURCE_PAYLOAD_INCOMPLETE')
                normal = normalize_source_row(raw)
                if (obs['provider_status'] != 'SUCCESS' or obs['provider'] != 'SHARADAR' or obs['native_table'] != 'fundamentals'
                    or obs['content_hash'] != new['content_hash'] or obs['dimension'] != new['dimension']
                    or new['dimension'] != 'ARQ' or obs['company_id'] != new['company_id'] or obs['security_id'] != new['security_id']
                    or obs['provider_ticker']!=case['ticker'] or obs['reportperiod']!=new['reportperiod']
                    or obs['source_availability_date']!=new['source_availability_date']
                    or str(obs['provider_security_id']) != str(identity.get('provider_security_id'))):
                    block('SOURCE_IDENTITY_MISMATCH')
                # Both existing acquisition hash conventions and exact raw-payload
                # repair hashes are retained; never reinterpret a missing factor.
                if obs['content_hash'] not in {fingerprint(_raw_row(normal)), stable_hash(raw), payload_fingerprint(raw)}:
                    block('SOURCE_CONTENT_HASH_MISMATCH')
                if (any(normal[k] != new[v] for k,v in (('ticker','canonical_ticker'),('date','provider_date'),('reportperiod','reportperiod')))
                    or normal['fiscalperiod']!=f"{new['fiscal_year']}-{new['fiscal_quarter']}"):
                    block('SOURCE_KEY_MISMATCH')
                if (raw.get('dimension') != new['dimension'] or raw.get('ticker') != case['ticker']
                    or str(raw.get('reportperiod')) != new['reportperiod'] or str(raw.get('date')) != new['provider_date']
                    or any(finite(raw.get(k)) != finite(new.get(v)) for k,v in (
                        ('sharesbas','sharesbas'),('sharefactor','sharefactor'),('equity','parent_equity'),('equityusd','parent_equity_usd')))):
                    block('SOURCE_KEY_OR_VALUES_MISMATCH')
                native = p.execute('SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?', source_key(normal)).fetchone()[0]
                if native != 1: block('DUPLICATE_SOURCE_OBSERVATION')
                previous = p.execute('SELECT * FROM provider_observation WHERE observation_id=?', (old['observation_id'],)).fetchone()
                stable = [dict(r) for r in c.execute("SELECT * FROM provider_security_identity WHERE provider='SHARADAR' AND security_id=?",(old['security_id'],))]
                evidence['previous_provider_identity'] = {'canonical_bindings':stable,'previous_observation_present':previous is not None}
                if (len(stable)!=1 or str(stable[0]['provider_security_id'])!=str(obs['provider_security_id'])
                    or not stable[0]['created_at_utc'] or stable[0]['created_at_utc']>old['reviewed_at']
                    or (previous is not None and any(previous[k] != obs[k] for k in ('provider','native_table','company_id','security_id','provider_security_id')))):
                    block('PROVIDER_STABLE_IDENTITY_CHANGE')
                provenance = json.loads(obs['provenance_json'] or '{}')
                if set(provenance) - {'source_payload_repair'}: block('SOURCE_HISTORY_OR_PROVENANCE_ANOMALY')
                if 'source_payload_repair' in provenance:
                    repair=provenance['source_payload_repair']
                    if (repair.get('new_observation_id')!=obs['observation_id']
                        or repair.get('new_content_hash')!=obs['content_hash'] or repair.get('new')!=completeness(raw)):
                        block('SOURCE_REPAIR_BINDING_MISMATCH')
                history = load_current_history(provider_db, case['ticker'], 'ARQ')
                evidence['history'] = {k: v for k,v in history.items() if k != 'rows'}
                unresolved_retention = [r for r in history['rows'] if r.get('_history_retention_status') and not (
                    r['_history_retention_status']=='RETAINED_OUTSIDE_SOURCE_WINDOW'
                    and (r.get('_history_retention_evidence') or {}).get('classification_reason')=='RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON'
                    and r.get('_provider_observation_id')!=new['observation_id'])]
                if history['invalid_rows'] or history['legacy_source_version_ambiguities'] or unresolved_retention:
                    block('SOURCE_HISTORY_OR_PROVENANCE_ANOMALY')
                matches = [r for r in history['rows'] if r.get('_provider_observation_id') == new['observation_id']]
                if len(matches) != 1 or fingerprint(_raw_row(matches[0])) != fingerprint(_raw_row(normal)):
                    block('SOURCE_NATIVE_PAYLOAD_MISMATCH')
            fp = [dict(r) for r in c.execute('''SELECT fp.* FROM v4_field_provenance fp JOIN v4_quarter q USING(quarter_id)
                WHERE q.company_id=? AND q.fiscal_year=? AND q.fiscal_quarter=? AND fp.canonical_field='shares_outstanding' ''',
                (new['company_id'],new['fiscal_year'],new['fiscal_quarter']))]
            evidence['shares_provenance'] = fp
            if len(fp) != 1 or any(fp[0].get(k) != v for k,v in {
                'provider':'SHARADAR','provider_observation_id':new['observation_id'],'source_native_field':'sharesbas',
                'transformation':'DIRECT','rule_version':'SHARADAR_ARQ_PRIMARY_V1','confidence':'HIGH'}.items()):
                block('UNSUPPORTED_SHARES_PROVENANCE')
            if finite(new.get('sharesbas')) is None or new['sharesbas'] <= 0 or new['sharesbas'] != new.get('shares_outstanding'):
                block('INVALID_SHARES')
            actions = []
            start = old['share_source_date']
            tables = {r[0] for r in p.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'sharadar_action_metadata' in tables:
                actions = [dict(r) for r in p.execute('''SELECT * FROM sharadar_action_metadata WHERE (ticker=? OR contraticker=?) AND date>? AND date<=?''',
                    (case['ticker'],case['ticker'],start,as_of))]
                # Routine dividends do not change the ownership unit basis.
                if any(str(r['action']).lower() not in {'dividend','cashdividend'} for r in actions): block('CORPORATE_ACTION_BLOCKER')
            splits = []
            if m.execute("SELECT 1 FROM sqlite_master WHERE name='splits_data'").fetchone():
                splits = [dict(r) for r in m.execute('SELECT * FROM splits_data WHERE osake=? AND split_date>? AND split_date<=?',(case['ticker'],start,as_of))]
                if splits: block('CORPORATE_ACTION_BLOCKER')
            evidence['corporate_actions'] = {'actions': actions, 'splits': splits, 'coverage': 'INCOMPLETE_INFORMATIONAL_WARNING'}
        if queue_path and queue_path.exists():
            with closing(review._ro(queue_path)) as q:
                row = q.execute(f'SELECT status,result_json FROM {review.CASE_TABLE} WHERE case_id=?',(case['case_id'],)).fetchone()
                prior_result=json.loads(row['result_json']) if row and row['result_json'] else {}
                if row and (row['status'] == 'HELD' or (row['status']=='OPEN' and prior_result.get('note'))):
                    block('EXPLICIT_POLICY_HOLD', False)
                if q.execute("SELECT 1 FROM refresh_review_queue WHERE ticker=? AND status IN ('OPEN','HELD','APPROVED')",(case['ticker'],)).fetchone():
                    block('UNRESOLVED_SOURCE_REVIEW')
        effect = review.preview(case,canonical_db,market_db,as_of=as_of)
        pb = effect.get('hypothetical_current') or {}
        evidence['hypothetical_current'] = pb
        if pb.get('status') != 'OK' or pb.get('reason') != 'OK' or any(finite(pb.get(k)) is None or pb[k] <= 0 for k in ('price','parent_equity_usd','value')):
            block('INVALID_HYPOTHETICAL_PB_INPUTS', False)
        else:
            with localcontext() as ctx:
                ctx.prec = 50
                reconstructed = Decimal(str(pb['price'])) * Decimal(str(case['new']['sharesbas'])) / Decimal(str(pb['parent_equity_usd']))
            evidence['pb_reconstruction'] = str(reconstructed)
            if not math.isclose(float(reconstructed),pb['value'],rel_tol=1e-12,abs_tol=1e-12): block('PB_RECONSTRUCTION_FAILED')
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as exc:
        block('EVIDENCE_UNAVAILABLE_OR_STALE')
        evidence['error'] = str(exc)
    partition = 'DEEP_REVIEW/BLOCKED' if any(r['partition']=='DEEP_REVIEW/BLOCKED' for r in reasons) else 'MANUAL_REVIEW' if reasons else 'AUTO_CONTINUE'
    return {'policy_version': POLICY, 'partition': partition, 'reasons': reasons, 'warnings': warnings, 'evidence': evidence}


def reconcile(queue_path: Path, canonical_db: Path, provider_db: Path, market_db: Path, *,
              output_root: Path, as_of: str, run_id: str, enabled: bool = False) -> list[dict]:
    """Explicit opt-in reconciliation; decisions wait for controlled publication.

    Default is read-only partitioning. Merely installing this policy never
    migrates existing OPEN cases or enables unattended live publication.
    """
    partitions = []
    for case in review.list_cases(queue_path):
        if case['status'] not in ('OPEN','HELD'):
            continue
        decision = evaluate(case,canonical_db=canonical_db,provider_db=provider_db,market_db=market_db,as_of=as_of,queue_path=queue_path)
        partitions.append({'ticker':case['ticker'],'case_id':case['case_id'],**decision})
        if enabled and decision['partition'] == 'AUTO_CONTINUE':
            review._approve(queue_path,case['case_id'],candidate_hash=case['candidate_hash'],canonical_db=canonical_db,
                market_db=market_db,output_root=output_root,as_of=as_of,confirmed=True,automatic=decision,
                provider_db=provider_db,decision_run_id=run_id)
    return partitions
