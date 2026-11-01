"""Real accepted-reader/SQLite integration, synthetic fixtures only; no providers."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

import pandas as pd
import pytest

from services import stockcore_price_provider as bridge
from services import stock_update_service as service

NOW = datetime(2024, 1, 5, 22, tzinfo=timezone.utc)


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr('socket.socket.connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('NO_NETWORK')))
    lib = bridge.source_contract(str(bridge.SOURCE_ROOT))
    from stockcore.config import Config
    base = Path('/tmp/stockcore-price03/Temp/tests')
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stockcore-', dir=base) as root:
        config = Config(Path(root))
        store = lib.Store(config)
        store.initialize()  # isolated owned Temp fixture, never operational migration
        source = config.db
        cal = lib.Calendar(dict(format='stockcore.calendar.v1', market='USA', timezone='America/New_York',
            calendar_id='SYNTHETIC', version='synthetic', start='2024-01-01', end='2024-01-10',
            coverage='COMPLETE', evidence='independent synthetic sessions',
            sessions=[dict(session=f'2024-01-0{i}', close='16:00') for i in range(2, 6)]))
        security = dict(security_id=1, company_id=1, market='USA', active=True,
                        eligible_from='2024-01-01', eligible_to=None, evidence={'synthetic': True},
                        security_type=dict(value='COMMON_STOCK', status='QUALIFIED', source='SYNTHETIC'),
                        currency=dict(value='USD', source='SYNTHETIC'))
        q = dict(ordinary_usable=True, adjusted_usable=True, volume_status='AVAILABLE',
                 price_units='YAHOO_SPLIT_ADJUSTED', volume_units='PROVIDER_REPORTED',
                 unit_evidence={'auto_adjust': False})
        with sqlite3.connect(source) as c:
            c.row_factory = sqlite3.Row
            c.execute("UPDATE settings SET value='projection' WHERE key='mode'")
            c.execute("INSERT INTO settings VALUES('identity_fingerprint','synthetic-accepted-identity')")
            c.execute('INSERT INTO companies VALUES(1,NULL,?)', (json.dumps({'synthetic': True}),))
            c.execute('INSERT INTO securities VALUES(1,1,\'USA\',1,?)', (json.dumps(security),))
            c.execute("INSERT INTO routes VALUES('r1',1,'yahoo','TEST','2024-01-01',NULL,1,'{}')")
            c.execute('INSERT INTO source_calendars VALUES(?,?)', (cal.fingerprint, json.dumps(cal.payload)))
            c.execute('INSERT INTO settings VALUES(?,?)', ('calendar_binding:1', json.dumps(dict(calendar_hash=cal.fingerprint, start=cal.start, end=cal.end))))
            dep = dict(security_id=1, identity_version=lib.identity_token(c, 1), calendar_version=cal.fingerprint, source_revision='1')
            c.execute('INSERT INTO source_receipts VALUES(?,?,?,?,?,?,?)', ('accepted', 1, 'fixture', 'COMPLETE', '{}', '{}', NOW.isoformat()))
            c.execute('INSERT INTO source_heads VALUES(1,1,?,?)', (json.dumps(dep), 'accepted'))
            c.execute('INSERT INTO source_quality VALUES(1,?)', (json.dumps(q),))
            for i in range(2, 5):
                ordinary = 110. if i == 4 else 100.
                payload = dict(Open=ordinary, High=ordinary+2, Low=ordinary-2, Close=ordinary,
                               Volume=1000, ticker='TEST', vintage='synthetic-same-frame')
                payload['Adj Close'] = ordinary * .8
                day = f'2024-01-0{i}'
                c.execute('INSERT INTO source_observations VALUES(?,?,?,?,?,?)', (1, day, json.dumps(payload), 1, '2024-01-01', 'accepted'))
                c.execute('INSERT INTO source_coverage VALUES(?,?,?,?)', (1, day, 'ACCEPTED', 'accepted'))
            c.execute('CREATE TABLE operation_schedules(schedule_id TEXT PRIMARY KEY,request TEXT)')
        rc = tmp_path / 'rc.sqlite'
        with sqlite3.connect(rc) as c:
            c.execute('CREATE TABLE osakedata(osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT,UNIQUE(osake,pvm))')
            c.execute('CREATE TABLE splits_data(osake TEXT,split_date TEXT,split_ratio REAL,is_price_data_corrected INTEGER,UNIQUE(osake,split_date))')
            c.executemany('INSERT INTO osakedata VALUES(?,?,?,?,?,?,?,?)', [('TEST', f'2024-01-0{i}', 80., 81.6, 78.4, 80., 1000, 'usa') for i in [2, 3]])
        calls = []
        def yahoo(ticker):
            calls.append(ticker)
            return ('YAHOO', ticker)
        factory = bridge.ScheduledPriceFactory(rc_path=rc, market='usa', until='2024-01-06', yahoo_factory=yahoo, source_path=source, now=NOW)
        yield type('Fixture', (), dict(source=source, rc=rc, lib=lib, cal=cal, factory=factory, yahoo_calls=calls))


def sql(path, statement, args=()):
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        return c.execute(statement, args).fetchall()


def action(d, kind='SPLIT', day='2024-01-02', ratio=2, status='PROCESSED'):
    p = dict(type=kind, effective_date=day, ratio=ratio, ratio_orientation='NEW_PER_OLD', amount=20)
    sql(d.source, 'INSERT INTO corporate_actions VALUES(?,?,?,?,?,?,?,?)',
        ('a'+day, 1, 'version1', kind, status, json.dumps(p), None, 'accepted'))


def history(stock):
    return stock.history(start='2024-01-04', end='2024-01-06')


def test_qualified_same_vintage_output_and_source_unchanged(data):
    before = data.source.read_bytes()
    s = data.factory('TEST'); f = history(s)
    assert list(f.columns) == bridge.COLUMNS
    assert list(f.iloc[0]) == pytest.approx([88., 89.6, 86.4, 88., 1000])
    assert f.Volume.dtype == 'int64' and all(str(f[k].dtype) == 'float64' for k in bridge.PRICE_FIELDS)
    assert str(f.index.tz) == 'America/New_York' and f.index.name == 'Date'
    assert data.yahoo_calls == [] and data.source.read_bytes() == before


@pytest.mark.parametrize('mode', ['missing', 'expired', 'inactive', 'unsupported_market'])
def test_only_proven_absence_or_ineligibility_routes_to_yahoo(data, mode):
    if mode == 'missing':
        sql(data.source, "DELETE FROM routes")
    elif mode == 'expired':
        sql(data.source, "UPDATE routes SET valid_to='2024-01-04'")
    elif mode == 'inactive':
        sql(data.source, 'UPDATE securities SET active=0')
    else:
        sql(data.source, "UPDATE securities SET market='OMXH'")
    assert data.factory('TEST') == ('YAHOO', 'TEST')
    assert data.yahoo_calls == ['TEST']


@pytest.mark.parametrize('mode', ['ambiguous', 'unqualified', 'operator', 'quality', 'currency', 'units', 'gap', 'bad_anchor', 'factor', 'volume', 'new_split', 'revised_split', 'rc_only_split', 'uncorrected_split', 'missing_binding'])
def test_known_unsafe_source_is_withheld_never_yahoo(data, mode):
    if mode == 'ambiguous':sql(data.source, "INSERT INTO routes SELECT 'r2',security_id,provider,ticker,valid_from,valid_to,accepted,evidence FROM routes")
    elif mode == 'unqualified':sql(data.source, 'UPDATE routes SET accepted=0')
    elif mode == 'operator':sql(data.source, "INSERT INTO operation_schedules VALUES('yahoo-daily',?)", (json.dumps({'held': {'1': {'reason': 'review'}}}),))
    elif mode == 'quality':sql(data.source, 'INSERT INTO settings VALUES(?,?)', ('source_quality_hold:1', '{"active":true}'))
    elif mode == 'currency':
        # Change quality-independent reference and rebind accepted identity to
        # ensure the currency gate, not stale-token detection, rejects it.
        row = json.loads(sql(data.source, 'SELECT payload FROM securities')[0][0]);row['currency']['value'] = 'EUR'
        sql(data.source, 'UPDATE securities SET payload=?', (json.dumps(row),));rebind(data)
    elif mode == 'units':sql(data.source, "UPDATE source_quality SET document=json_set(document,'$.price_units','UNSPLIT')")
    elif mode == 'gap':
        sql(data.source, "DELETE FROM source_observations WHERE session='2024-01-03'")
    elif mode == 'bad_anchor':sql(data.rc, "UPDATE osakedata SET open=0 WHERE pvm='2024-01-03'")
    elif mode == 'factor':sql(data.source, "UPDATE source_observations SET payload=json_set(payload,'$.\"Adj Close\"',50) WHERE session='2024-01-03'")
    elif mode == 'volume':sql(data.rc, "UPDATE osakedata SET volume=2000 WHERE pvm='2024-01-03'")
    elif mode == 'missing_binding':sql(data.source, "DELETE FROM settings WHERE key='calendar_binding:1'")
    elif mode in {'new_split', 'revised_split'}:
        action(data)
        if mode == 'revised_split':sql(data.rc, "INSERT INTO splits_data VALUES('TEST','2024-01-02',3,1)")
    else:sql(data.rc, 'INSERT INTO splits_data VALUES(?,?,?,?)', ('TEST','2024-01-02',2,int(mode != 'uncorrected_split')))
    before = data.rc.read_bytes();s = data.factory('TEST')
    assert history(s).empty
    assert data.yahoo_calls == [] and data.rc.read_bytes() == before
    with pytest.raises(RuntimeError, match='WITHHELD'):_ = s.splits


def rebind(d):
    with sqlite3.connect(d.source) as c:
        c.row_factory = sqlite3.Row
        dep = dict(security_id=1, identity_version=d.lib.identity_token(c, 1), calendar_version=d.cal.fingerprint, source_revision='1')
        c.execute('UPDATE source_heads SET dependency=?', (json.dumps(dep),))


def test_no_new_or_stale_source_does_not_fall_back(data):
    sql(data.source, "DELETE FROM source_observations WHERE session='2024-01-04'")
    s = data.factory('TEST')
    assert history(s).empty and data.yahoo_calls == []
    assert data.factory.counts['stockcore_no_new'] == 1


@pytest.mark.parametrize('mode', ['unexplained', 'recorded', 'held', 'reversed'])
def test_new_session_factor_steps_require_recorded_dividend_evidence(data,mode):
    value=66 if mode=='reversed' else 110
    sql(data.source,"UPDATE source_observations SET payload=json_set(payload,'$.\"Adj Close\"',?) WHERE session='2024-01-04'",(value,))
    if mode!='unexplained':action(data,kind='DIVIDEND',day='2024-01-04',status='HELD' if mode=='held' else 'RECORDED')
    s=data.factory('TEST')
    assert history(s).empty is (mode!='recorded')
    assert data.yahoo_calls==[]


def test_ineligible_operator_quarantine_does_not_become_fallback(data):
    sql(data.source, "UPDATE routes SET valid_to='2024-01-04'")
    sql(data.source, "INSERT INTO operation_schedules VALUES('yahoo-daily',?)", (json.dumps({'held': {'1': {'reason': 'identity review'}}}),))
    assert history(data.factory('TEST')).empty and data.yahoo_calls == []


@pytest.mark.parametrize('field,value', [('Close',0),('Adj Close',-1),('Volume',2**53+1),('High',1)])
def test_bad_accepted_payload_never_imported_even_if_quality_flag_lies(data,field,value):
    p = json.loads(sql(data.source,"SELECT payload FROM source_observations WHERE session='2024-01-04'")[0][0]);p[field]=value
    sql(data.source,"UPDATE source_observations SET payload=? WHERE session='2024-01-04'",(json.dumps(p),))
    assert history(data.factory('TEST')).empty and data.yahoo_calls == []


def test_foreign_schema_is_reader_failure_not_yahoo(data):
    sql(data.source,'PRAGMA application_id=0')
    with pytest.raises(Exception,match='FOREIGN_DATABASE'):data.factory('TEST')
    assert not data.yahoo_calls and data.factory.counts['reader_failures']==1


def test_materiality_and_real_matching_processed_splits(data):
    sql(data.rc, "UPDATE osakedata SET close=80.04 WHERE pvm='2024-01-03'")
    action(data);sql(data.rc, "INSERT INTO splits_data VALUES('TEST','2024-01-02',2,1)")
    s = data.factory('TEST')
    assert not history(s).empty and list(s.splits) == [2.]
    assert history(s).iloc[0].Close == 88.  # no second split adjustment


@pytest.mark.parametrize('mode',['historical_revision','price_multiplier','volume_multiplier'])
def test_bounded_context_distinguishes_old_revision_from_persistent_units(data,mode):
    sql(data.rc,"INSERT INTO osakedata VALUES('TEST','2024-01-04',88,89.6,86.4,88,1000,'usa')")
    sql(data.source,"INSERT INTO source_observations SELECT security_id,'2024-01-05',payload,quality_id,segment,receipt_id FROM source_observations WHERE session='2024-01-04'")
    sql(data.source,"INSERT INTO source_coverage VALUES(1,'2024-01-05','ACCEPTED','accepted')")
    if mode=='historical_revision':
        sql(data.rc,"UPDATE osakedata SET open=open*.5,high=high*.5,low=low*.5,close=close*.5 WHERE pvm='2024-01-02'")
    elif mode=='price_multiplier':
        sql(data.rc,'UPDATE osakedata SET open=open*1.0005,high=high*1.0005,low=low*1.0005,close=close*1.0005')
    else:sql(data.rc,'UPDATE osakedata SET volume=1005')
    s=data.factory('TEST');f=s.history(start='2024-01-05',end='2024-01-06')
    assert f.empty is (mode!='historical_revision')
    assert data.yahoo_calls==[]


def test_dividend_exception_requires_independent_action_and_ordinary_anchor(data):
    sql(data.rc, "UPDATE osakedata SET open=100,high=102,low=98,close=100 WHERE pvm='2024-01-03'")
    action(data, kind='DIVIDEND', day='2024-01-04', status='RECORDED')
    assert not history(data.factory('TEST')).empty
    assert data.factory.reasons['LEGACY_DIVIDEND_VINTAGE_CONFIRMED'] == 1


def test_no_provider_switch_or_data_revision_between_chunks(data):
    sql(data.rc, "DELETE FROM osakedata WHERE pvm='2024-01-03'")
    s = data.factory('TEST')
    assert len(s.history(start='2024-01-03',end='2024-01-04')) == 1
    sql(data.source, "UPDATE source_observations SET payload=json_set(payload,'$.\"Adj Close\"',999) WHERE session='2024-01-04'")
    assert history(s).iloc[0].Close == 88.
    assert data.yahoo_calls == []


def test_ro_enforcement_closure_on_reader_error_and_foreign_contract(data, monkeypatch):
    with bridge.readonly(data.source) as c:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):c.execute('DELETE FROM securities')
    with pytest.raises(sqlite3.ProgrammingError):c.execute('SELECT 1')
    def fail(**kwargs):raise RuntimeError('injected reader failure')
    monkeypatch.setattr(data.lib.PriceReader, 'read', lambda self,**kw:fail(**kw))
    with pytest.raises(RuntimeError, match='injected'):data.factory('TEST')
    c = sqlite3.connect(data.source, timeout=0);c.execute('BEGIN EXCLUSIVE');c.close()
    assert data.factory.counts['reader_failures'] == 1 and data.yahoo_calls == []


def test_atomic_old_snapshot_and_close_before_frame_conversion(data, monkeypatch):
    w = sqlite3.connect(data.source, timeout=0, isolation_level=None)
    original = data.factory._anchor
    def pause(*args):
        w.execute('BEGIN IMMEDIATE');w.execute("INSERT INTO settings VALUES('probe','new')")
        with pytest.raises(sqlite3.OperationalError, match='locked'):w.commit()
        return original(*args)
    monkeypatch.setattr(data.factory, '_anchor', pause)
    s = data.factory('TEST')
    w.commit();w.close()  # Source snapshot already closed, before history DataFrame
    assert history(s).iloc[0].Close == 88.


def test_omxh_uses_only_existing_yahoo_without_source_load(data, monkeypatch):
    data.factory.market = 'omxh'
    monkeypatch.setattr(bridge,'source_contract',lambda *a: (_ for _ in ()).throw(AssertionError('NO_SOURCE_FOR_OMXH')))
    assert data.factory('FIN.HE') == ('YAHOO','FIN.HE')
    assert data.factory.counts['omxh_yahoo'] == 1


def test_source_callback_guards_never_call_destructive_backfill(data, monkeypatch):
    def forbidden(*args):raise AssertionError('DESTRUCTIVE_YAHOO_CALLBACK')
    app = type('App', (), {})();app.osakedata_db_path = str(data.rc)
    app._build_stock_update_service_adapters = lambda: dict(stock_factory=data.factory.yahoo_factory, sync_splits=forbidden, maybe_backfill_splits=forbidden)
    with monkeypatch.context() as m:
        m.setattr(bridge,'ScheduledPriceFactory',lambda **kw:data.factory)
        adapters, factory = bridge.scheduled_adapters(app, market='usa', fetch_until_exclusive='2024-01-06')
    s = factory('TEST');assert not history(s).empty
    assert adapters['sync_splits']('TEST',s) == 0
    assert adapters['maybe_backfill_splits']('TEST') is False
    sql(data.rc, "INSERT INTO splits_data VALUES('TEST','2024-01-04',2,0)")
    with pytest.raises(RuntimeError,match='STATE_CHANGED'):history(s)
    with pytest.raises(RuntimeError,match='STATE_CHANGED'):adapters['maybe_backfill_splits']('TEST')


def test_existing_service_writer_callbacks_and_failed_ticker_continue(data,monkeypatch):
    calls=[]
    sql(data.rc,"INSERT INTO osakedata VALUES('FAIL','2024-01-03',80,82,78,80,1000,'usa')")
    class Yahoo:
        def history(self,**kw):raise RuntimeError('fixture Yahoo error')
    data.factory.yahoo_factory=lambda ticker:Yahoo()
    monkeypatch.setattr(service,'_sleep_yahoo_after_history_range',lambda:None)
    monkeypatch.setattr(service,'_sleep_yahoo_after_ticker',lambda *a:None)
    result=service.run_stock_data_update(osakedata_db_path=str(data.rc),analysis_db_path=str(data.rc),market='usa',today='2024-01-05',fetch_until_exclusive='2024-01-06',
        stock_factory=data.factory,sync_splits=lambda *a:calls.append('splits') or 0,
        maybe_backfill_splits=lambda *a:calls.append('backfill-noop') or False,
        calculate_divergences=lambda *a:calls.append('divergence') or (True,1,''),
        run_candlestick_analysis=lambda *a:calls.append('candles') or (1,None),
        calculate_dow_structures=lambda **k:calls.append('dow') or {'updated':1},pivot_radius=3,
        bounded_initial_from_date='2024-01-01',recalc_tail_trading_days=10)
    assert result.ohlcv_rows_inserted==1 and result.tickers_failed==1
    assert calls==['splits','backfill-noop','divergence','candles','dow']
    assert data.factory.counts['usa_yahoo_fallback']==1 and data.factory.counts['reader_failures']==0


def test_cli_opt_in_is_explicit_default_ui_callers_remain_unchanged(monkeypatch,capsys):
    from rawcandle.cli import run_stock_update_scheduler as cli
    from tests.test_stock_update_scheduler_cli import _result
    seen=[]
    monkeypatch.setattr(cli,'run_scheduler_config',lambda **kw:seen.append(kw) or _result('OK'))
    assert cli.main(['--config','fixture.json'])==0
    assert seen[-1]=={'config_path':'fixture.json'}
    assert cli.main(['--config','fixture.json','--stockcore-prices'])==0
    assert seen[-1]['price_adapter_factory'] is bridge.scheduled_adapters


def test_real_market_runner_reports_injected_factory_without_changing_defaults(data,monkeypatch,tmp_path):
    from rawcandle.scheduler import runner
    from rawcandle.scheduler.config import create_default_scheduler_config
    config=create_default_scheduler_config(osakedata_db_path=str(data.rc),analysis_db_path=str(tmp_path/'analysis.db'),log_dir=str(tmp_path/'logs'))
    seen=[]
    class App:
        def _run_stock_update_via_service(self,**kw):
            seen.append(kw);return service.StockUpdateResult(market=kw['market'])
        def _format_stock_update_service_result_for_ui(self,result):return 'fixture'
    monkeypatch.setattr(runner,'_build_app',lambda c:App())
    kwargs=dict(config=config,market='usa',run_started_at_utc=NOW.isoformat(),effective_today='2024-01-05',effective_fetch_until_exclusive='2024-01-06')
    result=runner._run_one_market(**kwargs,price_adapter_factory=lambda *a,**kw:({'stock_factory':data.factory},data.factory))
    assert seen[-1]['service_adapters']['stock_factory'] is data.factory
    assert any('price_bridge.usa_stockcore=' in s for s in result.summary_lines)
    runner._run_one_market(**kwargs)
    assert 'service_adapters' not in seen[-1]


@pytest.mark.parametrize('a,b,expected',[(5865,5900,True),(382054,392700,False),(1014,1000,True),(864,900,True),(202,300,False),(10,11,False),(0,1,False),(0,0,True)])
def test_materiality_volume_rules(a,b,expected):
    assert bridge.volumes_match(b,a) is expected
