"""Bounded, read-only analyst price-target event research; no trading inference."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from rawcandle.fundamentals.generations import resolve_requested_role_path
from rawcandle.fundamentals.result_publication_daily_research_service import DailyResearchPublicationService, QuarterKey
from rawcandle.research.forecast_revision_research import instant, readonly, sha256
from rawcandle.research.result_publication_event_window import _load_ticker_history, _at, _pct

VERSION = 'price_target_event_research_v1'
STATS = ('mean', 'median', 'high', 'low')
EASTERN = ZoneInfo('America/New_York')


def number(state):
    if state.get('state') not in ('NUMERIC_VALUE', 'NUMERIC_ZERO'):
        return None
    raw = state.get('value')
    try:
        value = float(raw) if raw is not None else None
    except (ValueError, TypeError):
        return None
    return value if value is not None and math.isfinite(value) else None


def vector(obs):
    return {s: number((obs or {}).get('states', {}).get(s, {})) for s in STATS}


def changed(a, b):
    av, bv = vector(a), vector(b)
    return any(av[s] is not None and bv[s] is not None and av[s] != bv[s] for s in STATS)


def anomalies(a, b):
    av, bv = vector(a), vector(b)
    flags = set()
    for obs in (a, b):
        if obs and any(state.get('state') in ('NUMERIC_VALUE', 'NUMERIC_ZERO') and number(state) is None
                       for state in obs.get('states', {}).values()):
            flags.add('INVALID_NUMERIC_TARGET')
    if any(v is not None and v < 0 for v in (*av.values(), *bv.values())):
        flags.add('INVALID_TARGET_VALUE')
    for v in (av, bv):
        if v['high'] is not None and v['low'] is not None and v['low'] > v['high']:
            flags.add('INVERTED_TARGET_RANGE')
    # Conservative explicit scale screen, not a diagnosis of a split.
    if av['mean'] is not None and bv['mean'] is not None and av['mean'] > 0 and bv['mean'] > 0:
        ratio = bv['mean'] / av['mean']
        if ratio >= 5 or ratio <= .2:
            flags.add('SCALE_CHANGE_REVIEW')
    if a and b and a.get('currency') and b.get('currency') and a['currency'] != b['currency']:
        flags.add('CURRENCY_CHANGE_REVIEW')
    return flags


def magnitudes(a, b, flags=()):
    av, bv = vector(a), vector(b)
    out = {}
    for s in STATS:
        x, y = av[s], bv[s]
        out[s+'_change_abs'] = y-x if x is not None and y is not None else None
        out[s+'_change_pct'] = ((y-x)/x*100 if x is not None and y is not None
                                   and x >= 1e-8 and y >= 0 and not flags else None)
    return out


def trend(observations):
    directions = []
    for a, b in zip(observations, observations[1:]):
        x, y = vector(a)['mean'], vector(b)['mean']
        if x is not None and y is not None:
            directions.append((y>x)-(y<x))
    if not directions:
        return 'INSUFFICIENT_HISTORY'
    up, down = 1 in directions, -1 in directions
    return 'MIXED' if up and down else 'RISING' if up else 'FALLING' if down else 'FLAT'


def analyze_event(event, observations, history_end):
    """Exact timestamps; equal-boundary fetches excluded with an explicit count."""
    stamp = instant(event['publication_timestamp_utc'])
    observations = sorted(observations, key=lambda o: (instant(o['fetched_at_utc']), o['fetch_order']))
    usable = [o for o in observations if any(v is not None for v in vector(o).values())]
    before = [o for o in usable if instant(o['fetched_at_utc']) < stamp]
    after = [o for o in usable if instant(o['fetched_at_utc']) > stamp]
    pre = before[-1] if before else None
    first = next((o for o in after if pre and changed(pre, o)), None)
    lookback = [o for o in before if instant(o['fetched_at_utc']) >= stamp-timedelta(days=7)]
    flags = anomalies(pre, pre) if pre else set()
    for a, b in zip(lookback, lookback[1:]):
        flags.update(anomalies(a, b))
    if first:
        flags.update(anomalies(pre, first))
    count = 0
    previous = pre
    for obs in after:
        if instant(obs['fetched_at_utc']) > stamp+timedelta(days=7):
            break
        if previous:
            flags.update(anomalies(previous, obs))
            count += changed(previous, obs)
        previous = obs
    # Preserve endpoint states and IDs even when flagged or uncomparable.
    out = dict(event, pre_available=pre is not None, post_revision_available=first is not None,
               equal_publication_fetch_count=sum(instant(o['fetched_at_utc']) == stamp for o in observations),
               pre_result_target_trend=trend(lookback), post_result_revision_count_7d=count,
               post_7d_window_complete=instant(history_end) >= stamp+timedelta(days=7))
    for prefix, obs in (('pre', pre), ('first_post', first)):
        out[prefix+'_fetch_at'] = obs['fetched_at_utc'] if obs else None
        out[prefix+'_fetch_id'] = obs['fetch_id'] if obs else None
        out[prefix+'_snapshot_id'] = obs['snapshot_id'] if obs else None
        out[prefix+'_states_json'] = json.dumps(obs['states'] if obs else {}, sort_keys=True, separators=(',', ':'))
        for s, v in vector(obs).items():
            out[prefix+'_'+s] = v
    out['first_post_revision_fetch_at'] = out.pop('first_post_fetch_at')
    out['revision_lag_hours'] = (instant(first['fetched_at_utc'])-stamp).total_seconds()/3600 if first else None
    out['revision_lag_calendar_days'] = ((instant(first['fetched_at_utc']).astimezone(EASTERN).date()-stamp.astimezone(EASTERN).date()).days if first else None)
    checkpoints = {}
    for days in (1, 3, 7):
        candidates = [o for o in after if instant(o['fetched_at_utc']) <= stamp+timedelta(days=days)]
        checkpoints[days] = candidates[-1] if candidates else None
        if pre and checkpoints[days]:
            flags.update(anomalies(pre, checkpoints[days]))
    endpoints = magnitudes(pre, first, flags) if pre and first else {s+'_change_'+k: None for s in STATS for k in ('abs', 'pct')}
    out.update(endpoints)
    for days in (1, 3, 7):
        checkpoint = checkpoints[days]
        out[f'latest_{days}d_mean'] = vector(checkpoint)['mean']
        out[f'checkpoint_{days}d_json'] = json.dumps({
            'usable': checkpoint is not None,
            'window_complete': instant(history_end) >= stamp+timedelta(days=days),
            'fetch_at': checkpoint['fetched_at_utc'] if checkpoint else None,
            'fetch_id': checkpoint['fetch_id'] if checkpoint else None,
            'snapshot_id': checkpoint['snapshot_id'] if checkpoint else None,
            'states': checkpoint['states'] if checkpoint else {},
            'values': vector(checkpoint),
            'changes_vs_pre': magnitudes(pre, checkpoint, flags) if pre and checkpoint else None,
        }, sort_keys=True, separators=(',', ':'))
    if flags:
        for s in STATS:
            out[s+'_change_pct'] = None
    deltas = [out[s+'_change_abs'] for s in STATS if out[s+'_change_abs'] is not None]
    mean_delta = out['mean_change_abs']
    out['event_classification'] = ('NO_PRE_TARGET' if not pre else 'ANOMALY_REVIEW' if flags else
        'NO_POST_REVISION_YET' if not first else
        'POST_REVISION_MIXED' if any(d>0 for d in deltas) and any(d<0 for d in deltas) else
        'POST_REVISION_UP' if mean_delta is not None and mean_delta>0 else
        'POST_REVISION_DOWN' if mean_delta is not None and mean_delta<0 else 'POST_REVISION_FLAT_OR_NON_MEAN_CHANGE')
    out['anomaly_flag'] = '|'.join(sorted(flags))
    return out


def attach_outcomes(row, days):
    """Existing observed-session offsets and D-1 close return convention."""
    boundary = row['first_full_post_result_trading_date']
    index = next((i for i, day in enumerate(days) if day.trading_date == boundary), None)
    previous = _at(days, index, -1) if index is not None else None
    for offset in (0, 5, 20, 30, 60):
        day = _at(days, index, offset) if index is not None else None
        value = _pct(day.close if day else None, previous.close if previous else None)
        row[f'd{offset}_available'] = value is not None
        row[f'd{offset}_return'] = value
        row[f'd{offset}_status'] = ('AVAILABLE' if value is not None else
            'BOUNDARY_UNAVAILABLE' if boundary is None else
            'PENDING_D0' if index is None and (not days or boundary > days[-1].trading_date) else
            'MISSING_D0' if index is None else 'PENDING_FOLLOWUP' if day is None else 'MISSING_PRICE')
    if row['first_post_revision_fetch_at'] and days:
        a = instant(row['publication_timestamp_utc']).astimezone(EASTERN).date().isoformat()
        b = instant(row['first_post_revision_fetch_at']).astimezone(EASTERN).date().isoformat()
        row['revision_lag_trading_days'] = sum(a<d.trading_date<=b for d in days) if days[-1].trading_date >= b else None
    else:
        row['revision_lag_trading_days'] = None


def summarize(rows):
    post = [r for r in rows if r['post_revision_available']]
    ordinary = [r for r in post if not r['anomaly_flag']]
    lag = Counter('0–1d' if r['revision_lag_calendar_days']<=1 else '2–3d' if r['revision_lag_calendar_days']<=3 else
                  '4–7d' if r['revision_lag_calendar_days']<=7 else '>7d' for r in post)
    return {'publication_events': len(rows), 'pre_available': sum(r['pre_available'] for r in rows),
            'post_revision_available': len(post), 'pre_and_post_revision': len(post),
            'no_revision_yet_with_pre': sum(r['pre_available'] and not r['post_revision_available'] for r in rows),
            'no_pre': sum(not r['pre_available'] for r in rows),
            'anomaly_events': sum(bool(r['anomaly_flag']) for r in rows), 'timing_distribution': dict(lag),
            'median_revision_lag_hours': median([r['revision_lag_hours'] for r in post]) if post else None,
            'mean_raised': sum(r['mean_change_abs'] is not None and r['mean_change_abs']>0 for r in ordinary),
            'mean_lowered': sum(r['mean_change_abs'] is not None and r['mean_change_abs']<0 for r in ordinary),
            'non_mean_only': sum(r['mean_change_abs'] in (0, None) for r in ordinary),
            'pre_trend': dict(Counter(r['pre_result_target_trend'] for r in rows)),
            'outcomes': {f'D{k}':sum(r[f'd{k}_available'] for r in rows) for k in (0,5,20,30,60)}}


def build_price_target_event_research(forecasts_db, canonical_db, ohlc_db, output, metadata_output):
    forecasts_db, ohlc_db, output, metadata_output = map(Path, (forecasts_db, ohlc_db, output, metadata_output))
    canonical_db = resolve_requested_role_path('canonical', canonical_db)
    sources = {'forecasts': forecasts_db, 'canonical': canonical_db, 'ohlc': ohlc_db}
    if output.resolve() in {p.resolve() for p in sources.values()} or metadata_output.resolve() in {p.resolve() for p in sources.values()} or output.resolve() == metadata_output.resolve():
        raise ValueError('OUTPUT_MUST_NOT_OVERWRITE_INPUT')
    production_data = Path(__file__).resolve().parents[2] / 'data'
    if any(production_data in p.resolve().parents for p in (output, metadata_output)):
        raise ValueError('OUTPUT_MUST_NOT_WRITE_PRODUCTION_DATA_DIRECTORY')
    if output.suffix != '.csv' or metadata_output.suffix != '.json':
        raise ValueError('OUTPUT_SUFFIX_MUST_BE_CSV_AND_JSON')
    before = {k:sha256(p) for k,p in sources.items()}
    fc, cc, oc = readonly(forecasts_db), readonly(canonical_db), readonly(ohlc_db)
    try:
        fetches = [dict(r) for r in fc.execute("SELECT rowid fetch_order,* FROM forecast_fetch WHERE forecast_family='PRICE_TARGET' ORDER BY fetched_at_utc,rowid")]
        if not fetches:
            raise ValueError('NO_PRICE_TARGET_HISTORY')
        start, end = fetches[0]['fetched_at_utc'], fetches[-1]['fetched_at_utc']
        states = defaultdict(dict)
        currencies = defaultdict(set)
        for r in fc.execute('SELECT * FROM forecast_price_target'):
            if r['statistic'] in STATS:
                states[r['snapshot_id']][r['statistic']] = {'state':r['value_state'], 'value':r['value_numeric']}
                if r['currency']:
                    currencies[r['snapshot_id']].add(r['currency'])
        observations = defaultdict(list)
        for f in fetches:
            if f['status'] in ('SUCCESS_CHANGED','SUCCESS_UNCHANGED') and f['snapshot_id']:
                observations[(f['company_id'], f['security_id'])].append(dict(f, states=states[f['snapshot_id']],
                    currency=next(iter(currencies[f['snapshot_id']])) if len(currencies[f['snapshot_id']])==1 else None))
        authorities = [dict(r) for r in cc.execute("SELECT a.*,q.source_availability_date FROM v4_result_publication_authority a JOIN v4_quarter q ON q.company_id=a.company_id AND q.fiscal_year=a.fiscal_year AND q.fiscal_quarter=a.fiscal_quarter WHERE a.status='VERIFIED' AND a.result_publication_timestamp_utc>=? AND a.result_publication_timestamp_utc<=? ORDER BY a.company_id,a.fiscal_year,a.fiscal_quarter", (start,end))]
        securities = defaultdict(list)
        for r in cc.execute('SELECT company_id,security_id,current_ticker FROM security WHERE active=1'):
            securities[r['company_id']].append(dict(r))
        keys = [QuarterKey(a['company_id'],a['fiscal_year'],a['fiscal_quarter']) for a in authorities]
        with DailyResearchPublicationService(canonical_db, ohlc_db) as service:
            projected = {}
            for p in service.get_daily_research_results(keys):
                d = p.to_dict(); projected[(d['company_id'],d['fiscal_year'],d['fiscal_quarter'])] = d
        rows, excluded = [], Counter()
        for a in authorities:
            security = securities[a['company_id']]
            if len(security)!=1 or not security[0]['current_ticker']:
                excluded['ambiguous_or_missing_active_security'] += 1
                continue
            p = projected[(a['company_id'],a['fiscal_year'],a['fiscal_quarter'])]
            if p['research_status'] != 'EXACT':
                excluded['not_exact_projection'] += 1
                continue
            sec = security[0]
            event = {'company_id':a['company_id'], 'ticker':sec['current_ticker'], 'fiscal_year':a['fiscal_year'],
                'fiscal_quarter':a['fiscal_quarter'], 'publication_timestamp_utc':a['result_publication_timestamp_utc'],
                'publication_confidence':a['result_publication_confidence'], 'publication_source':a['result_publication_source'],
                'publication_evidence_id':a['selected_evidence_id'], 'source_availability_date':a['source_availability_date'],
                'first_full_post_result_trading_date':p['first_full_post_result_trading_date']}
            row = analyze_event(event, observations[(a['company_id'],sec['security_id'])], end)
            attach_outcomes(row, _load_ticker_history(oc, sec['current_ticker']))
            rows.append(row)
        checks = {k:[r[0] for r in c.execute('PRAGMA quick_check')] for k,c in [('forecasts',fc),('canonical',cc),('ohlc',oc)]}
        if any(v!=['ok'] for v in checks.values()):
            raise ValueError('SOURCE_INTEGRITY_FAILED')
    finally:
        fc.close(); cc.close(); oc.close()
    after = {k:sha256(p) for k,p in sources.items()}
    if before != after:
        raise ValueError('SOURCE_DATABASE_CHANGED_DURING_RESEARCH')
    summary = {'full':summarize(rows), 'october':summarize([r for r in rows if instant(r['publication_timestamp_utc']).astimezone(EASTERN).strftime('%Y-%m')=='2026-10'])}
    metadata = {'artifact_version':VERSION, 'history_start':start, 'history_end':end, 'summary':summary,
        'authority_events_inside_history':len(authorities), 'excluded_events':dict(excluded),
        'source_paths':{k:str(p.resolve()) for k,p in sources.items()}, 'source_sha256_before':before,
        'source_sha256_after':after, 'quick_check':checks, 'output_rows':len(rows)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['company_id','ticker'],lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    metadata['output_sha256'] = sha256(output)
    metadata_output.parent.mkdir(parents=True,exist_ok=True)
    metadata_output.write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
    return metadata
