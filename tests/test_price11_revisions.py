"""PRICE-11: native Source producer, immutable RC appends and hostile revisions."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import sqlite3
import tempfile

import pytest

from services import stockcore_price_provider as bridge
from services import stock_update_service as updater
from services.price_revision_policy import RevisionDiagnostics, difference


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.setattr('socket.socket.connect', lambda *a, **k: (_ for _ in ()).throw(AssertionError('NO_NETWORK')))
    lib = bridge.source_contract(str(bridge.SOURCE_ROOT))
    from stockcore.config import Config
    from stockcore.identity import import_projection
    from stockcore.universes import preview, apply
    from stockcore.source import SourceServices
    from stockcore.yahoo import Response, YahooAdapter
    spec = importlib.util.spec_from_file_location('price11_synthetic_sc_fixtures', bridge.SOURCE_ROOT/'tests/fixtures.py')
    fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
    root_base = Path('/tmp/stockcore-price11/Temp/tests'); root_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stockcore-revision-', dir=root_base) as folder:
        config = Config(Path(folder)); store = lib.Store(config); store.initialize()
        from stockcore.operation_store import initialize
        initialize(config)
        identity = fixtures.identities()
        for security in identity['securities']:
            security['currency'] = dict(value='USD', source='SYNTHETIC')
        import_projection(store, identity, fixture=True)
        with store.read() as c: manifest = preview(c, fixtures.snapshot(), as_of='2026-11-05')
        apply(store, manifest, authorize_source=manifest['source_hash'])
        days = ['2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30','2026-11-02','2026-11-03','2026-11-04','2026-11-05']
        cal = lib.Calendar(dict(format='stockcore.calendar.v1', synthetic=True, market='USA', timezone='America/New_York',
                                version='PRICE11_SYNTHETIC', start=days[0], end=days[-1], coverage='COMPLETE',
                                evidence='independent synthetic sessions', sessions=[dict(session=d, close='16:00') for d in days]))
        edits = {}
        class Transport:
            def fetch(self, request, *, cancelled):
                observations = []
                for day in request.sessions:
                    close = 115 if day == '2026-11-05' else 110 if day == '2026-11-04' else 100
                    item=dict(session=day, Open=close, High=close+2, Low=close-2, Close=close,
                              **{'Adj Close': close}, Volume=1000)
                    item.update(edits.get(day, {})); observations.append(item)
                return Response('COMPLETE','synthetic-native',tuple(observations),(),
                                dict(provider='yahoo',security_id=request.security_id,ticker=request.ticker,auto_adjust=False,
                                     start=request.start,end_exclusive=request.end_exclusive,observed_at='2026-11-05T04:00:00+00:00'),
                                dict(prices='YAHOO_SPLIT_ADJUSTED',volume='PROVIDER_REPORTED',
                                     evidence=dict(auto_adjust=False,repair=False,interface='Ticker.history',synthetic=True)))
        source = SourceServices(store, YahooAdapter(Transport()))
        initial = source.refresh(security_id=102, calendar=cal, now=datetime.fromisoformat('2026-11-04T07:00:00+00:00'),
                                 mode='repair', start=days[0], end='2026-11-03')
        assert initial['status']=='COMPLETE'
        rc = tmp_path/'prices.db'
        with sqlite3.connect(rc) as c:
            c.execute('CREATE TABLE osakedata(id INTEGER PRIMARY KEY,osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT,UNIQUE(osake,pvm))')
            c.execute('CREATE TABLE splits_data(osake TEXT,split_date TEXT,split_ratio REAL,is_price_data_corrected INTEGER)')
            c.executemany('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)',
                          [('BETA',d,100,102,98,100,1000,'usa') for d in days[:-2]])
        def publish(changes, now='2026-11-05T04:00:00+00:00'):
            with sqlite3.connect(config.db) as c:c.execute("UPDATE settings SET value='fixture' WHERE key='mode'")
            edits.clear(); edits.update(changes)
            result = source.refresh(security_id=102, calendar=cal, now=datetime.fromisoformat(now))
            assert result['status']=='COMPLETE',result
            with sqlite3.connect(config.db) as c:
                c.execute("UPDATE settings SET value='projection' WHERE key='mode'")
                c.execute('INSERT OR IGNORE INTO source_calendars VALUES(?,?)',(cal.fingerprint,json.dumps(cal.payload)))
                c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('calendar_binding:102',json.dumps(dict(calendar_hash=cal.fingerprint,start=cal.start,end=cal.end))))
            return result
        def factory(now='2026-11-05T04:00:00+00:00'):
            return bridge.ScheduledPriceFactory(rc_path=rc, source_path=config.db, market='usa', until=now[:10],
                       now=datetime.fromisoformat(now), yahoo_factory=lambda t: (_ for _ in ()).throw(AssertionError('NO_FALLBACK')),
                       diagnostic_dir=tmp_path/'diagnostics')
        yield dict(config=config,store=store,cal=cal,publish=publish,rc=rc,factory=factory,edits=edits)


def query(path, sql, args=()):
    with sqlite3.connect(path) as c: return c.execute(sql,args).fetchall()


def append(native, obj, day='2026-11-04'):
    latest=query(native['rc'],"SELECT max(pvm) FROM osakedata WHERE osake='BETA'")[0][0]
    plan = updater.StockUpdateTickerPlan(updater.StockUpdateTickerCandidate('BETA','2026-10-26',latest,'usa'), latest<day,
                   date_ranges=[updater.StockUpdateDateRange(day,(date.fromisoformat(day)+timedelta(days=1)).isoformat())])
    return updater.execute_ticker_ohlcv_update_plan(osakedata_db_path=str(native['rc']), stock=obj, plan=plan, market='usa')


@pytest.mark.parametrize('changes',[
    {'Volume':2000}, {'High':104}, {'Open':101,'High':104,'Low':97,'Volume':2000}, {'Adj Close':99.95},
])
def test_native_revisions_append_without_rewriting_history(native, changes):
    native['publish']({'2026-11-03':changes})
    old=query(native['rc'],'SELECT * FROM osakedata ORDER BY id')
    obj=native['factory']()('BETA');assert not obj.hold
    assert obj.revision_diagnostics[0]['classification']=='NON_BLOCKING_HISTORICAL_REVISION'
    result=append(native,obj);assert result.ohlcv_rows_inserted==1
    assert query(native['rc'],'SELECT * FROM osakedata WHERE pvm<=? ORDER BY id',('2026-11-03',))==old
    assert query(native['rc'],"SELECT open,high,low,close,volume FROM osakedata WHERE pvm='2026-11-04'")==[(110,112,108,110,1000)]
    factory=native['factory']();second=factory('BETA');assert not second.rows
    assert factory.counts['historical_revision_warnings_new']==0
    assert append(native,second).ohlcv_rows_inserted==0
    assert query(native['rc'],"SELECT count(*) FROM osakedata WHERE pvm='2026-11-04'")==[(1,)]


def test_true_price_and_inverse_volume_scale_stays_held(native):
    native['publish']({'2026-11-03':dict(Open=1000,High=1020,Low=980,Close=1000,Volume=100,**{'Adj Close':1000})})
    obj=native['factory']()('BETA');assert obj.hold=='UNEXPLAINED_PRICE_OR_FACTOR_BOUNDARY'
    assert not query(native['rc'],"SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


def test_source_head_changed_after_qualification_prevents_commit(native):
    native['publish']({'2026-11-03':{'Volume':2000}});obj=native['factory']()('BETA')
    with sqlite3.connect(native['config'].db) as c:c.execute('UPDATE source_heads SET revision=revision+1,dependency=json_set(dependency,\'$.source_revision\',\'999\') WHERE security_id=102')
    with pytest.raises(RuntimeError,match='SOURCE_CHANGED_AFTER_PREFLIGHT'):append(native,obj)
    assert not query(native['rc'],"SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


def test_rc_anchor_changed_after_qualification_prevents_commit(native):
    native['publish']({'2026-11-03':{'Volume':2000}});obj=native['factory']()('BETA')
    with sqlite3.connect(native['rc']) as c:c.execute("UPDATE osakedata SET volume=1100 WHERE pvm='2026-11-03'")
    with pytest.raises(RuntimeError,match='RC_STATE_CHANGED'):append(native,obj)


def test_revision_outside_reviewed_window_does_not_gain_exception(native):
    native['publish']({'2026-11-03':{'Volume':2000}})
    from services.price_revision_policy import revision_witness
    lib=bridge.source_contract(str(bridge.SOURCE_ROOT))
    with bridge.readonly(native['config'].db) as c:
        witness,reason=revision_witness(c,lib,security_id=102,session='2026-10-26',calendar=native['cal'],now=datetime.fromisoformat('2026-11-05T04:00:00+00:00'),anchor_receipt='unknown')
    assert witness is None and reason=='REVISION_OUTSIDE_SIX_COMPLETED_SESSIONS'


def test_mixed_daily_receipt_does_not_make_new_session_a_revision(native):
    native['publish']({'2026-11-03': {'Volume': 2000}})
    lib = bridge.source_contract(str(bridge.SOURCE_ROOT))
    from services.price_revision_policy import revision_witness
    with bridge.readonly(native['config'].db) as c:
        receipt = c.execute('SELECT receipt_id FROM source_heads WHERE security_id=102').fetchone()[0]
        witness, reason = revision_witness(
            c, lib, security_id=102, session='2026-11-04', calendar=native['cal'],
            now=datetime.fromisoformat('2026-11-05T04:00:00+00:00'), anchor_receipt=receipt)
        assert witness is None
        assert reason == 'REVISION_SESSION_PREVIOUS_ACCEPTANCE_REQUIRED'
        witness, reason = revision_witness(
            c, lib, security_id=102, session='2026-11-03', calendar=native['cal'],
            now=datetime.fromisoformat('2026-11-05T04:00:00+00:00'), anchor_receipt=receipt)
        assert reason is None and witness['changed_fields'] == ['Volume']


@pytest.mark.parametrize('missing_proof', ['held', 'other_session', 'wrong_change_id'])
def test_prior_acceptance_proof_must_be_native_and_session_specific(native, missing_proof):
    native['publish']({'2026-11-03': {'Volume': 2000}})
    with sqlite3.connect(native['config'].db) as c:
        if missing_proof == 'held':
            c.execute("UPDATE source_receipts SET status='HELD' WHERE mode='repair'")
        elif missing_proof == 'other_session':
            c.execute("UPDATE source_changes SET scope=json_set(scope,'$.changes',json('[]')) WHERE revision=1")
        else:
            c.execute("UPDATE source_changes SET change_id='not-a-native-key' WHERE revision=1")
    obj = native['factory']()('BETA')
    assert obj.hold == 'MATERIAL_VOLUME_BOUNDARY'
    assert not query(native['rc'], "SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


def test_diagnostics_deduplicate_values_and_keep_bounded_sessions(tmp_path):
    log=RevisionDiagnostics(tmp_path/'bounded')
    item=dict(security_id=1,session='2026-11-03',original_rc={'Volume':100},accepted_source={'Volume':200},classification='NON_BLOCKING_HISTORICAL_REVISION')
    assert log.record(item) is True
    assert log.record(dict(item,source_revision=2)) is False
    for day in range(1,10):log.record(dict(item,session=f'2026-11-{day:02d}'))
    assert len(json.loads((tmp_path/'bounded/1.json').read_text())['records'])==6


def test_multiple_successive_native_overlap_revisions(native):
    native['publish']({'2026-11-03':{'Volume':2000}})
    assert append(native,native['factory']()('BETA')).ohlcv_rows_inserted==1
    now='2026-11-06T04:00:00+00:00'
    native['publish']({'2026-11-04':{'Volume':2400}},now=now)
    obj=native['factory'](now)('BETA');assert not obj.hold
    assert append(native,obj,day='2026-11-05').ohlcv_rows_inserted==1
    assert query(native['rc'],"SELECT pvm,volume FROM osakedata WHERE pvm IN ('2026-11-03','2026-11-04','2026-11-05') ORDER BY pvm")==[
        ('2026-11-03',1000),('2026-11-04',1000),('2026-11-05',1000)]


@pytest.mark.parametrize('mode',['identity','calendar','wrong_ticker','critical_reverse_split','unit_hold'])
def test_native_revision_never_waives_qualification_or_actions(native,mode):
    native['publish']({'2026-11-03':{'Volume':2000}})
    with sqlite3.connect(native['config'].db) as c:
        if mode=='identity':
            payload=json.loads(c.execute('SELECT payload FROM securities WHERE security_id=102').fetchone()[0]);payload['currency']['source']='CHANGED_REFERENCE'
            c.execute('UPDATE securities SET payload=? WHERE security_id=102',(json.dumps(payload),))
        elif mode=='calendar':
            lib=bridge.source_contract(str(bridge.SOURCE_ROOT));payload=deepcopy(native['cal'].payload);payload['version']='CHANGED_CALENDAR';cal=lib.Calendar(payload)
            c.execute('INSERT INTO source_calendars VALUES(?,?)',(cal.fingerprint,json.dumps(cal.payload)))
            c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(dict(calendar_hash=cal.fingerprint,start=cal.start,end=cal.end)),'calendar_binding:102'))
        elif mode=='wrong_ticker':
            c.execute('UPDATE source_observations SET payload=json_set(payload,\'$.ticker\',\'OTHER\') WHERE security_id=102 AND session=\'2026-11-04\'')
        elif mode=='critical_reverse_split':
            c.execute('INSERT INTO corporate_actions VALUES(?,?,?,?,?,?,?,?)',('reverse',102,'v1','SPLIT','HELD',json.dumps(dict(type='SPLIT',ratio=.1,ratio_orientation='NEW_PER_OLD',effective_date='2026-11-04')),'REVIEW','held-receipt'))
        else:c.execute('INSERT INTO settings VALUES(?,?)',('source_quality_hold:102','{"active":true}'))
    obj=native['factory']()('BETA');assert obj.hold
    assert not query(native['rc'],"SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


def test_publication_failure_rolls_back_without_changing_accepted_history(native):
    native['publish']({'2026-11-03':{'Volume':2000}});obj=native['factory']()('BETA')
    before=query(native['rc'],'SELECT * FROM osakedata ORDER BY id')
    with sqlite3.connect(native['rc']) as c:
        c.execute("CREATE TRIGGER fixture_rollback BEFORE INSERT ON osakedata BEGIN SELECT RAISE(ABORT,'INJECTED_ROLLBACK'); END")
    with pytest.raises(sqlite3.IntegrityError,match='INJECTED_ROLLBACK'):append(native,obj)
    assert query(native['rc'],'SELECT * FROM osakedata ORDER BY id')==before


def test_corrupt_native_revision_receipt_fails_closed(native):
    native['publish']({'2026-11-03':{'Volume':2000}})
    with sqlite3.connect(native['config'].db) as c:
        c.execute("UPDATE source_receipts SET summary=json_set(summary,'$.accepted_sessions',999) WHERE receipt_id=(SELECT receipt_id FROM source_heads WHERE security_id=102)")
    factory=native['factory']();obj=factory('BETA');assert obj.hold=='MATERIAL_VOLUME_BOUNDARY'
    data=json.loads((factory.diagnostics.directory/'102.json').read_text())
    assert data['records'][0]['classification']=='SAFETY_HOLD'
    assert data['records'][0]['qualification_reason']=='REVISION_RECEIPT_UNQUALIFIED'


def test_real_native_head_advance_after_preflight_refuses_old_cached_rows(native):
    native['publish']({'2026-11-03':{'Volume':2000}});obj=native['factory']()('BETA')
    native['publish']({'2026-11-03':{'Volume':2200}})
    with pytest.raises(RuntimeError,match='SOURCE_CHANGED_AFTER_PREFLIGHT'):append(native,obj)
    assert not query(native['rc'],"SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


def test_critical_hold_added_after_preflight_blocks_publication(native):
    native['publish']({'2026-11-03':{'Volume':2000}});obj=native['factory']()('BETA')
    with sqlite3.connect(native['config'].db) as c:
        c.execute('INSERT INTO settings VALUES(?,?)',('source_quality_hold:102','{"active":true}'))
    with pytest.raises(bridge.SourceHold,match='SOURCE_UNIT_HOLD'):append(native,obj)
    assert not query(native['rc'],"SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")


@pytest.mark.parametrize('volume,looser_tolerance',[(1015,.02),(1025,.03),(1040,.05)])
def test_tolerance_would_miss_small_persistent_volume_unit_pattern(native, volume, looser_tolerance):
    # Three controlled common multipliers are an unproved unit pattern, even
    # though each candidate percentage threshold would let its anchor pass.
    assert abs(volume / 1000 - 1) < looser_tolerance
    native['publish']({day: {'Volume': volume} for day in ['2026-10-30','2026-11-02','2026-11-03']})
    obj = native['factory']()('BETA')
    assert obj.hold == 'MATERIAL_VOLUME_BOUNDARY'
    assert not query(native['rc'], "SELECT 1 FROM osakedata WHERE pvm='2026-11-04'")
