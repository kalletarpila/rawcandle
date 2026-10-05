"""Publication-constrained revised-history quarterly P/E research, not PIT."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, closing
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from rawcandle.fundamentals.generations import resolved_production_paths
from preflight import readonly, START_DATE, END_DATE, CUTOFF_EXCLUSIVE

EXCLUSIONS = (
    'MISSING_START_PRICE', 'MISSING_END_PRICE', 'NO_ELIGIBLE_PUBLISHED_QUARTER',
    'INCOMPLETE_PUBLICATION_AUTHORITY', 'MISSING_EPSDIL', 'ZERO_EPS', 'NEGATIVE_EPS',
    'INVALID_EPS_BASIS', 'OTHER_INVALID_DATA',
)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def select_quarter(quarters, evidence_dates):
    eligible = [q for q in quarters if q['status'] == 'VERIFIED'
                and q['publication'] and q['publication'] < CUTOFF_EXCLUSIVE]
    if not eligible:
        return None, 'NO_ELIGIBLE_PUBLISHED_QUARTER', []
    latest = max(q['publication'] for q in eligible)
    winners = [q for q in eligible if q['publication'] == latest]
    if len(winners) != 1:
        return None, 'INCOMPLETE_PUBLICATION_AUTHORITY', ['SAME_TIMESTAMP_QUARTER_CONFLICT']
    winner = winners[0]
    blocking = []
    for q in quarters:
        if q['quarter_id'] == winner['quarter_id'] or q['period_end'] > START_DATE:
            continue
        hints = [d for d in (q['source_availability_date'], q['first_public_result_date']) if d]
        unverified = q['status'] != 'VERIFIED' or not q['publication']
        has_hint = any(d <= START_DATE and
                       (q['period_end'] >= winner['period_end'] or d >= latest[:10]) for d in hints)
        has_evidence = any(latest <= d < CUTOFF_EXCLUSIVE for d in evidence_dates.get(q['quarter_id'], []))
        if unverified and (has_hint or has_evidence):
            blocking.append(q['quarter_id'])
    if blocking:
        return None, 'INCOMPLETE_PUBLICATION_AUTHORITY', blocking
    return winner, None, []


def valid_basis(payload, metadata, split_dates, period_end):
    if not metadata or metadata['category'] not in ('Domestic Common Stock', 'Domestic Common Stock Primary Class'):
        return False, 'NOT_CONFIRMED_DOMESTIC_PRIMARY_COMMON_STOCK'
    if number(payload.get('fxusd')) != 1.0:
        return False, 'NON_USD_OR_MISSING_FXUSD'
    if number(payload.get('sharefactor')) != 1.0:
        return False, 'NON_UNIT_OR_MISSING_SHAREFACTOR'
    eps, epsusd = number(payload.get('eps')), number(payload.get('epsusd'))
    if eps is None or epsusd is None or not math.isclose(eps, epsusd, rel_tol=1e-8, abs_tol=1e-8):
        return False, 'BASIC_EPS_USD_CROSSCHECK_FAILED'
    if not number(payload.get('shareswadil')) or number(payload.get('shareswadil')) <= 0:
        return False, 'MISSING_DILUTED_SHARE_BASIS'
    if any(d > period_end for d in split_dates):
        return False, 'LATER_SPLIT_OR_UNCORRECTED_SPLIT_BASIS_NOT_PROVEN'
    return True, 'USD_UNIT_SHAREFACTOR_NO_KNOWN_LATER_SPLIT'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def statistics(values):
    a = np.array(values, dtype=float)
    if not len(a):
        return {'N': 0}
    return dict(N=len(a), minimum=float(a.min()), P10=float(np.percentile(a, 10)),
                median=float(np.median(a)), mean=float(a.mean()), P90=float(np.percentile(a, 90)), maximum=float(a.max()))


def relationship(rows):
    x = np.array([r['pe'] for r in rows], dtype=float)
    y = np.array([r['return'] for r in rows], dtype=float)
    if len(x) < 2 or np.var(x) == 0 or np.var(y) == 0:
        return {'N': len(x), 'alpha': None, 'beta': None, 'R2': None, 'Pearson': None}
    xc, yc = x-x.mean(), y-y.mean()
    beta = float(np.dot(xc, yc) / np.dot(xc, xc))
    alpha = float(y.mean() - beta*x.mean())
    r2 = float(1 - np.sum((y-(alpha+beta*x))**2) / np.dot(yc, yc))
    return dict(N=len(x), alpha=alpha, beta=beta, R2=r2, Pearson=float(np.corrcoef(x, y)[0, 1]))


def run(root, output):
    paths = resolved_production_paths(root)
    watched = {**paths, 'pointer': root/'data/fundamentals_active_generation.json'}
    before = {k: sha256(p) for k, p in watched.items()}
    with ExitStack() as stack:
        db = {k: stack.enter_context(closing(readonly(p))) for k, p in paths.items() if k != 'analysis'}
        tax = db['taxonomy']
        versions = tax.execute(
            "SELECT v.* FROM ec_taxonomy_version v JOIN ec_ecosystem e USING(ecosystem_id) "
            "WHERE e.ecosystem_code='DATACENTER' AND v.is_active=1"
        ).fetchall()
        if len(versions) != 1 or versions[0]['taxonomy_version_code'] != 'DC_TAXONOMY_FULL_V2_1':
            raise RuntimeError('ACTIVE_TAXONOMY_DRIFT')
        members = tax.execute(
            "SELECT e.ticker,m.membership_role FROM ec_membership m JOIN ec_entity e ON e.entity_id=m.child_entity_id "
            "WHERE m.taxonomy_version_id=? AND m.status='ACTIVE' AND m.membership_type='CONTAINS' "
            "AND e.entity_type='TICKER' AND e.ticker IS NOT NULL", (versions[0]['taxonomy_version_id'],),
        ).fetchall()
        tickers = sorted({r['ticker'].strip().upper() for r in members})
        if len(members) != 350 or len(tickers) != 257:
            raise RuntimeError('TAXONOMY_COHORT_DRIFT')
        canon, provider, market = db['canonical'], db['provider'], db['market']
        evidence = defaultdict(list)
        for r in canon.execute("SELECT quarter_id,source_timestamp_utc FROM v4_result_publication_evidence WHERE source_type != 'YAHOO_EARNINGS_CALENDAR' AND source_timestamp_utc IS NOT NULL"):
            evidence[r['quarter_id']].append(r['source_timestamp_utc'])
        accepted, audit, counts = [], [], Counter()
        coverage = Counter()
        for ticker in tickers:
            detail = {'ticker': ticker}
            def exclude(reason, note):
                counts[reason] += 1
                detail.update(exclusion=reason, note=note)
                audit.append(detail)
            prices = market.execute('SELECT pvm,close,market FROM osakedata WHERE osake=? AND pvm IN (?,?)', (ticker, START_DATE, END_DATE)).fetchall()
            days = Counter(r['pvm'] for r in prices)
            if any(n != 1 for n in days.values()):
                exclude('OTHER_INVALID_DATA', 'DUPLICATE_PRICE_DATE'); continue
            price_map = {r['pvm']: r for r in prices}
            for day, name in ((START_DATE,'start'), (END_DATE,'end')):
                if day in price_map and number(price_map[day]['close']) is not None and number(price_map[day]['close']) > 0:
                    coverage['valid_'+name+'_prices'] += 1
            if START_DATE not in price_map or price_map[START_DATE]['close'] is None:
                exclude('MISSING_START_PRICE', START_DATE); continue
            if END_DATE not in price_map or price_map[END_DATE]['close'] is None:
                exclude('MISSING_END_PRICE', END_DATE); continue
            start, end = number(price_map[START_DATE]['close']), number(price_map[END_DATE]['close'])
            if start is None or end is None or start <= 0 or end <= 0:
                exclude('OTHER_INVALID_DATA', 'NONPOSITIVE_OR_NONFINITE_PRICE'); continue
            identities = canon.execute('SELECT * FROM security WHERE current_ticker=? AND active=1', (ticker,)).fetchall()
            if len(identities) != 1:
                exclude('OTHER_INVALID_DATA', 'ACTIVE_SECURITY_IDENTITY_NOT_UNIQUE'); continue
            identity = identities[0]
            quarters = [dict(r) for r in canon.execute(
                "SELECT q.*,a.status,a.result_publication_timestamp_utc AS publication,a.quarter_id AS authority_quarter_id,"
                "a.result_publication_source,a.result_publication_evidence_reference "
                "FROM v4_quarter q LEFT JOIN v4_result_publication_authority a USING(company_id,fiscal_year,fiscal_quarter) "
                "WHERE q.company_id=?", (identity['company_id'],),
            )]
            q, reason, blockers = select_quarter(quarters, evidence)
            if reason:
                exclude(reason, blockers); continue
            coverage['publication_selected'] += 1
            detail.update(company_id=identity['company_id'], security_id=identity['security_id'], quarter_id=q['quarter_id'],
                          fiscal_year=q['fiscal_year'], fiscal_quarter=q['fiscal_quarter'],period_end=q['period_end'],
                          publication=q['publication'], publication_source=q['result_publication_source'], publication_reference=q['result_publication_evidence_reference'])
            if q['identity_status'] != 'ACCEPTED' or q['quarter_id'] != q['authority_quarter_id'] or q['period_end'] > q['publication'][:10]:
                exclude('OTHER_INVALID_DATA', 'CANONICAL_PUBLICATION_IDENTITY_CONFLICT'); continue
            provenance = canon.execute(
                "SELECT DISTINCT provider_observation_id FROM v4_common_earnings_provenance "
                "WHERE quarter_id=? AND canonical_field='net_income_common' AND provider='SHARADAR'", (q['quarter_id'],),
            ).fetchall()
            if len(provenance) != 1:
                exclude('MISSING_EPSDIL', 'CANONICAL_PROVIDER_OBSERVATION_NOT_UNIQUE'); continue
            observation = provider.execute('SELECT * FROM provider_observation WHERE observation_id=?', (provenance[0][0],)).fetchone()
            if observation is None:
                exclude('MISSING_EPSDIL', 'PROVENANCE_OBSERVATION_MISSING'); continue
            payload = json.loads(observation['payload_json'])
            identities_provider = {str(r[0]) for r in canon.execute("SELECT provider_security_id FROM provider_security_identity WHERE security_id=? AND provider='SHARADAR'", (identity['security_id'],))}
            permaticker = observation['provider_security_id']
            identity_ok = str(permaticker) in identities_provider
            if permaticker is None:
                identity_ok = (observation['company_id'] == identity['company_id']
                               and observation['security_id'] == identity['security_id']
                               and len(identities_provider) == 1)
                if identity_ok:
                    permaticker = next(iter(identities_provider))
            if (observation['dimension'] != 'ARQ' or observation['reportperiod'] != q['period_end'] or observation['fiscalperiod'] != q['source_fiscalperiod'] or not identity_ok):
                exclude('INVALID_EPS_BASIS', 'PROVIDER_PERMANENT_OR_FISCAL_IDENTITY_MISMATCH'); continue
            detail.update(observation_id=observation['observation_id'], observation_hash=observation['content_hash'],
                          provider_date=observation['source_availability_date'], fetched_at=observation['fetched_at_utc'], lastupdated=payload.get('lastupdated'),
                          permaticker=permaticker,identity_resolution='EXPLICIT_PERMATICKER' if observation['provider_security_id'] else 'DURABLE_COMPANY_SECURITY_ID_WITH_UNIQUE_PROVIDER_MAPPING')
            raw_eps = payload.get('epsdil')
            if raw_eps in (None, ''):
                exclude('MISSING_EPSDIL', 'JSON_EPSDIL_MISSING'); continue
            eps = number(raw_eps)
            if eps is None:
                exclude('OTHER_INVALID_DATA', 'NONFINITE_EPSDIL'); continue
            coverage['finite_epsdil_selected'] += 1
            detail['epsdil'] = eps
            if eps == 0:
                exclude('ZERO_EPS', 'SELECTED_QUARTER_EPSDIL_ZERO'); continue
            if eps < 0:
                exclude('NEGATIVE_EPS', 'SELECTED_QUARTER_EPSDIL_NEGATIVE'); continue
            coverage['positive_epsdil_selected'] += 1
            metadata_rows = provider.execute("SELECT * FROM sharadar_ticker_metadata WHERE table_name='fundamentals' AND permaticker=?", (permaticker,)).fetchall()
            metadata = metadata_rows[0] if len(metadata_rows) == 1 else None
            split_rows = market.execute('SELECT split_date,is_price_data_corrected FROM splits_data WHERE osake=?', (ticker,)).fetchall()
            split_dates = [r['split_date'] for r in split_rows]
            split_dates.extend(r[0] for r in provider.execute("SELECT date FROM sharadar_action_metadata WHERE ticker=? AND action IN ('split','spinoff','adratio')", (ticker,)))
            basis, note = valid_basis(payload, metadata, split_dates, q['period_end'])
            if (not basis or any(r['is_price_data_corrected'] != 1 for r in split_rows)
                    or any(str(r['market']).lower() != 'usa' for r in prices)):
                exclude('INVALID_EPS_BASIS', note if not basis else 'UNCORRECTED_SPLIT_OR_NON_US_PRICE'); continue
            pe, ret = start/(eps*4), (end/start-1)*100
            if not math.isfinite(pe) or not math.isfinite(ret):
                exclude('OTHER_INVALID_DATA', 'NONFINITE_CALCULATION'); continue
            detail.update(exclusion=None, close_start=start,close_end=end,start_date=START_DATE,end_date=END_DATE,
                          pe=pe,return_12m_pct=ret,eps_basis=note)
            audit.append(detail)
            accepted.append({'ticker':ticker,'pe':pe,'return':ret})
    after = {k: sha256(p) for k, p in watched.items()}
    if before != after:
        raise RuntimeError('SOURCE_CHANGED_DURING_READ_ONLY_ANALYSIS')
    accepted.sort(key=lambda r: (r['pe'],r['ticker']))
    assert len(audit) == len(tickers) == len(accepted)+sum(counts.values())
    assert len({r['ticker'] for r in accepted}) == len(accepted)
    assert all(r['ticker'] in tickers and r['pe'] > 0 for r in accepted)
    summary = dict(semantic='revised_quarter_PE_2025_10_03;NOT_ORIGINAL_PIT',
                   taxonomy_version='DC_TAXONOMY_FULL_V2_1',taxonomy_rows=len(members),taxonomy_unique_tickers=len(tickers),
                   membership_roles=dict(Counter(r['membership_role'] for r in members)),sources={k:str(p) for k,p in paths.items()},
                   source_hashes=before,source_hashes_unchanged=True,coverage=dict(coverage),
                   exclusions={name:counts[name] for name in EXCLUSIONS},final_sample_size=len(accepted),
                   pe_statistics=statistics([r['pe'] for r in accepted]),return_statistics=statistics([r['return'] for r in accepted]),
                   relationship=relationship(accepted),audit=audit,
                   outliers=dict(high_pe=sorted(accepted,key=lambda r:r['pe'],reverse=True)[:3],
                                 high_return=sorted(accepted,key=lambda r:r['return'],reverse=True)[:3],
                                 low_return=sorted(accepted,key=lambda r:r['return'])[:3]))
    output.mkdir(parents=True,exist_ok=True)
    with (output/'revised_quarter_pe_returns.csv').open('w',newline='') as handle:
        writer = csv.writer(handle,lineterminator='\n')
        writer.writerow(['ticker','pe_2025_10_03','return_12m_pct'])
        writer.writerows((r['ticker'],f"{r['pe']:.2f}",f"{r['return']:.2f}") for r in accepted)
    (output/'validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10,6))
    x = np.array([r['pe'] for r in accepted])
    y = np.array([r['return'] for r in accepted])
    ax.scatter(x,y,s=24,color='#216e80',alpha=.75,label=f"Stocks (N={len(x)})")
    fit = summary['relationship']
    if fit['beta'] is not None:
        line = np.array([x.min(),x.max()])
        ax.plot(line,fit['alpha']+fit['beta']*line,color='#ad2947',label='OLS')
    ax.axhline(0,color='#555555',linewidth=.8)
    if accepted:
        for row, offset, align in ((max(accepted,key=lambda r:r['pe']),(-8,8),'right'),
                                   (max(accepted,key=lambda r:r['return']),(10,-4),'left')):
            ax.annotate(row['ticker'],(row['pe'],row['return']),xytext=offset,textcoords='offset points',
                        ha=align,fontsize=9)
    ax.set(xlabel='pe_2025_10_03',ylabel='return_12m_pct')
    ax.set_title('Annualized quarterly P/E vs subsequent 12-month return',fontsize=13)
    ax.grid(alpha=.2)
    ax.legend()
    fig.text(.08,.02,'P/E = 2025-10-03 Close / (latest published quarter revised diluted EPS x 4)\n'
             'Return = 2025-10-03 to 2026-10-02; EPS is revised historical data, not original PIT.',fontsize=9)
    fig.tight_layout(rect=(0,.10,1,1))
    fig.savefig(output/'scatter.png',dpi=160)
    plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('audit','source_hashes')},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent/'revised_outputs')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output != Path(__file__).resolve().parent/'revised_outputs' and Path('/tmp') not in output.parents:
        parser.error('Outputs must use the research output directory or /tmp, never production data.')
    run(args.repo_root.resolve(),output)
