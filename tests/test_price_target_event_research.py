import copy
import json
import sqlite3
from pathlib import Path
import pytest
from rawcandle.research import price_target_event_research as r
from rawcandle.research.result_publication_daily_ohlc import OhlcDay


def obs(day, mean=10, **kw):
    states = {s:{'state':'NUMERIC_VALUE','value':str(kw.get(s,mean))} for s in r.STATS}
    return {'fetch_order':day,'fetch_id':str(day),'snapshot_id':str(day),
            'fetched_at_utc':f'2026-10-{day:02d}T12:00:00Z','states':states,'currentPrice':kw.get('current',5)}


def event():
    return {'company_id':1,'ticker':'T','publication_timestamp_utc':'2026-10-05T20:00:00Z',
            'first_full_post_result_trading_date':'2026-10-06'}


def analyze(rows):
    return r.analyze_event(event(),rows,'2026-10-14T12:00:00Z')


def test_current_price_and_unchanged_snapshots_do_not_create_revision():
    result=analyze([obs(5),obs(6,current=99),obs(7)])
    assert not result['post_revision_available']
    assert result['post_result_revision_count_7d']==0
    assert result['event_classification']=='NO_POST_REVISION_YET'


@pytest.mark.parametrize('stat',r.STATS)
def test_each_numeric_statistic_can_create_revision(stat):
    b=obs(6);b['states'][stat]['value']='11'
    result=analyze([obs(5),b])
    assert result['post_revision_available']
    assert result[stat+'_change_abs']==1


def test_latest_pre_first_post_and_unchanged_skipping():
    rows=[obs(3,9),obs(5,10),obs(6,10),obs(7,11),obs(8,12)]
    a=analyze(rows)
    assert a['pre_fetch_id']=='5'
    assert a['first_post_fetch_id']=='7'
    assert a['revision_lag_hours']==40
    assert a['mean_change_pct']==10
    assert a['post_result_revision_count_7d']==2
    assert json.loads(a['checkpoint_1d_json'])['fetch_id']=='6'
    assert a['latest_3d_mean']==12
    assert a==analyze(list(reversed(rows)))


@pytest.mark.parametrize('values,expected',[( [10,11,12],'RISING'),([12,11,10],'FALLING'),
    ([10,11,10],'MIXED'),([10,10,10],'FLAT'),([10],'INSUFFICIENT_HISTORY')])
def test_pre_trend(values,expected):
    assert analyze([obs(i+2,v) for i,v in enumerate(values)])['pre_result_target_trend']==expected


def test_availability_only_change_not_numeric_revision():
    a,b=obs(5),obs(6)
    b['states']['mean']={'state':'EXPLICIT_NULL','value':None}
    assert not r.changed(a,b)
    result=analyze([a,b]);assert not result['post_revision_available']
    assert r.vector(b)['mean'] is None


def test_anomaly_retains_evidence_and_suppresses_percent():
    a=analyze([obs(5),obs(6,50)])
    assert a['anomaly_flag']=='SCALE_CHANGE_REVIEW'
    assert a['event_classification']=='ANOMALY_REVIEW'
    assert a['first_post_mean']==50 and a['mean_change_abs']==40
    assert a['mean_change_pct'] is None
    assert json.loads(a['first_post_states_json'])['mean']['value']=='50'
    assert json.loads(a['checkpoint_1d_json'])['changes_vs_pre']['mean_change_pct'] is None


def test_exact_boundary_excluded_and_no_pre_not_synthesized():
    equal=obs(5,20);equal['fetched_at_utc']=event()['publication_timestamp_utc']
    result=analyze([obs(5,10),equal,obs(6,11)])
    assert result['equal_publication_fetch_count']==1
    assert result['pre_mean']==10 and result['first_post_mean']==11
    a=analyze([equal,obs(6,11)])
    assert not a['pre_available'] and not a['post_revision_available']
    assert a['event_classification']=='NO_PRE_TARGET'


def test_first_revision_compares_pre_not_availability_only_adjacent_state():
    missing=obs(6);missing['states']['mean']={'state':'EXPLICIT_NULL','value':None}
    result=analyze([obs(5),missing,obs(7,11)])
    assert result['first_post_fetch_id']=='7'


def test_7d_closed_window_and_checkpoint_not_carrying_pre():
    a=analyze([obs(5),obs(13,11)])
    assert a['post_result_revision_count_7d']==0
    assert a['post_revision_available']
    assert a['latest_7d_mean'] is None
    assert not json.loads(a['checkpoint_7d_json'])['usable']


def test_outcomes_use_observed_offsets_and_missing_followup():
    a=analyze([obs(5),obs(6,11)])
    days=[OhlcDay('2026-10-05',1,1,1,10,1),OhlcDay('2026-10-06',1,1,1,11,1)]
    r.attach_outcomes(a,days)
    assert a['d0_available'] and a['d0_return']==pytest.approx(10)
    assert not a['d5_available'] and a['d5_status']=='PENDING_FOLLOWUP'
    assert not a['d30_available'] and not a['d60_available']


def test_read_only_and_input_overwrite_guard(tmp_path):
    p=tmp_path/'source.db'
    with sqlite3.connect(p) as c:c.execute('create table evidence(value)')
    before=r.sha256(p);c=r.readonly(p)
    with pytest.raises(sqlite3.OperationalError):c.execute('insert into evidence values(1)')
    c.close();assert r.sha256(p)==before
    with pytest.raises(ValueError,match='OUTPUT_MUST_NOT_OVERWRITE_INPUT'):
        r.build_price_target_event_research(p,p,p,p,tmp_path/'m.json')


def test_full_builder_hash_guard_and_deterministic_output(tmp_path,monkeypatch):
    from rawcandle.forecasts.schema import migrate_forecasts_db
    f,c,o=[tmp_path/(x+'.db') for x in ('f','c','o')];migrate_forecasts_db(f)
    with sqlite3.connect(f) as db:
        db.execute("insert into forecast_run(run_id,provider,adapter,adapter_version,started_at_utc,status) values('r','YAHOO_FINANCE','test','1','2026-10-01T12:00:00Z','SUCCESS')")
        db.execute("insert into forecast_fetch(fetch_id,run_id,provider,adapter,adapter_version,identity_key,provider_symbol,forecast_family,requested_at_utc,fetched_at_utc,status,attempt_count) values('f','r','YAHOO_FINANCE','test','1','1','T','PRICE_TARGET','2026-10-01T12:00:00Z','2026-10-01T12:00:00Z','VALID_NO_DATA',1)")
    with sqlite3.connect(c) as db:
        db.execute('create table v4_result_publication_authority(company_id,fiscal_year,fiscal_quarter,status,result_publication_timestamp_utc)')
        db.execute('create table v4_quarter(company_id,fiscal_year,fiscal_quarter,source_availability_date)')
        db.execute('create table security(company_id,security_id,current_ticker,active)')
    with sqlite3.connect(o) as db:db.execute('create table evidence(value)')
    class Service:
        def __init__(self,*a):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get_daily_research_results(self,keys):return []
    monkeypatch.setattr(r,'DailyResearchPublicationService',Service)
    monkeypatch.setattr(r,'resolve_requested_role_path',lambda role,path:path)
    output,meta=tmp_path/'out.csv',tmp_path/'out.json'
    first=r.build_price_target_event_research(f,c,o,output,meta)
    assert first==r.build_price_target_event_research(f,c,o,output,meta)
    assert first['source_sha256_before']==first['source_sha256_after']
    real=r.sha256;calls={}
    def drift(path):
        calls[path]=calls.get(path,0)+1
        return 'drift' if path==o and calls[path]>1 else real(path)
    monkeypatch.setattr(r,'sha256',drift)
    with pytest.raises(ValueError,match='SOURCE_DATABASE_CHANGED_DURING_RESEARCH'):
        r.build_price_target_event_research(f,c,o,tmp_path/'rejected.csv',tmp_path/'rejected.json')
    assert not (tmp_path/'rejected.csv').exists()


def test_missing_mean_never_substitutes_another_statistic():
    a,b=obs(5),obs(6,high=12)
    for o in (a,b):o['states']['mean']={'state':'FIELD_ABSENT','value':None}
    result=analyze([a,b])
    assert result['post_revision_available']
    assert result['mean_change_pct'] is None
    assert result['pre_result_target_trend']=='INSUFFICIENT_HISTORY'
    assert result['event_classification']=='POST_REVISION_FLAT_OR_NON_MEAN_CHANGE'


def test_invalid_values_zero_denominator_and_late_anomaly_suppress_percentages():
    assert r.number({'state':'NUMERIC_VALUE','value':'nan'}) is None
    assert r.number({'state':'NUMERIC_VALUE','value':'bad'}) is None
    assert r.magnitudes(obs(5,0),obs(6,1))['mean_change_pct'] is None
    negative=analyze([obs(5),obs(6,-1)])
    assert 'INVALID_TARGET_VALUE' in negative['anomaly_flag']
    assert negative['mean_change_pct'] is None
    late=analyze([obs(5),obs(6,11),obs(9,60)])
    assert late['mean_change_abs']==1 and late['mean_change_pct'] is None
    assert json.loads(late['checkpoint_1d_json'])['changes_vs_pre']['mean_change_pct'] is None


def test_return_offsets_30_60_use_actual_observed_sessions():
    a=analyze([obs(5),obs(6,11)])
    from datetime import date,timedelta
    days=[OhlcDay((date(2026,10,5)+timedelta(days=i)).isoformat(),1,1,1,10+i,1) for i in range(62)]
    r.attach_outcomes(a,days)
    assert a['d30_available'] and a['d30_return']==pytest.approx(310)
    assert a['d60_available'] and a['d60_return']==pytest.approx(610)


def test_pending_d0_not_confused_with_missing_publication_boundary():
    a=analyze([obs(5)])
    r.attach_outcomes(a,[OhlcDay('2026-10-05',1,1,1,10,1)])
    assert a['d0_status']=='PENDING_D0'
    a['first_full_post_result_trading_date']=None
    r.attach_outcomes(a,[])
    assert a['d0_status']=='BOUNDARY_UNAVAILABLE'
