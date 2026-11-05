"""Helsinki exchange clocks and exact provisional-row publication/recovery."""
from datetime import datetime
from copy import deepcopy
import json
import sqlite3

import pytest

from services.market_sessions import completed_fetch_until, last_completed_helsinki_session, is_helsinki_session
from services.price_history_maintenance import (prepare_omxh_finalization, apply_omxh_finalization,
                                               restore_omxh_finalization, validate_plan)


@pytest.mark.parametrize('clock,expected',[
    ('2026-11-05T06:00:00+02:00','2026-11-04'),
    ('2026-11-05T18:29:00+02:00','2026-11-04'),
    ('2026-11-05T18:59:59+02:00','2026-11-04'),
    ('2026-11-05T19:00:00+02:00','2026-11-05'),
    ('2026-11-08T12:00:00+02:00','2026-11-06'),
    ('2026-06-19T20:00:00+03:00','2026-06-18'),
    ('2026-04-06T20:00:00+03:00','2026-04-02'),
    ('2027-12-06T20:00:00+02:00','2027-12-03'),
])
def test_completed_session_uses_helsinki_holidays_and_close_buffer(clock,expected):
    assert last_completed_helsinki_session(datetime.fromisoformat(clock))==expected


def test_cap_is_market_specific_and_calendar_horizon_fails_closed():
    clock=datetime.fromisoformat('2026-11-05T11:00:00+02:00')
    assert completed_fetch_until('omxh','2026-11-06',now=clock)=='2026-11-05'
    assert completed_fetch_until('usa','2026-11-06',now=clock)=='2026-11-06'
    assert completed_fetch_until('omxh','2026-01-01',now=clock)=='2026-01-01'
    assert not is_helsinki_session('2026-06-19')
    with pytest.raises(ValueError,match='CALENDAR_REVIEW'):last_completed_helsinki_session(datetime.fromisoformat('2028-11-05T20:00:00+02:00'))
    with pytest.raises(ValueError,match='AWARE'):last_completed_helsinki_session(datetime(2026,11,5))


@pytest.fixture
def provisional(tmp_path):
    path=tmp_path/'prices.db';log=tmp_path/'logs';log.mkdir();evidence=tmp_path/'durable'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE osakedata(id INTEGER PRIMARY KEY,osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT,UNIQUE(osake,pvm))')
        c.executemany('INSERT INTO osakedata VALUES(?,?,?,?,?,?,?,?,?)',[
            (1,'TEST.HE','2026-11-04',10,11,9,10,100,'omxh'),
            (2,'OTHER.HE','2026-11-04',20,21,19,20,200,'omxh'),
            (3,'AAPL','2026-11-03',100,101,99,100,1000,'usa')])
        c.row_factory=sqlite3.Row;originals=[dict(r) for r in c.execute("SELECT * FROM osakedata WHERE market='omxh'")]
    bars=[dict(ticker=r['osake'],date=r['pvm'],open=r['open'],high=r['high']+1,low=r['low'],close=r['close']+.5,volume=r['volume']*2) for r in originals]
    def prepare(selected=bars):
        return prepare_omxh_finalization(database=path,originals=originals,final_bars=selected,
            provisional_at='2026-11-04T11:17:03+00:00',final_observed_at='2026-11-05T07:00:00+00:00',
            provider_evidence_hash='a'*64,provisional_evidence_hash='b'*64)
    return dict(path=path,log=log,evidence=evidence,originals=originals,bars=bars,prepare=prepare)


def run(case,plan,**kw):
    return apply_omxh_finalization(plan,evidence_dir=case['evidence'],scheduler_log_dir=case['log'],preflight=lambda:None,**kw)


def rows(case):
    with sqlite3.connect(case['path']) as c:return c.execute('SELECT * FROM osakedata ORDER BY id').fetchall()


def test_exact_final_replacement_idempotency_and_restoration(provisional):
    before=rows(provisional);plan=provisional['prepare']();result=run(provisional,plan)
    assert result['replaced_rows']==2 and result['derived_obligation']['dow']=='REBUILD_REQUIRED'
    after=rows(provisional);assert after[2]==before[2]
    assert after[0][3:8]==(10,12,9,10.5,200)
    evidence=(provisional['evidence']/(plan['plan_id']+'.original.json')).read_bytes()
    second=run(provisional,plan);assert second['replaced_rows']==0 and second['original_replaced_rows']==2
    assert rows(provisional)==after
    assert (provisional['evidence']/(plan['plan_id']+'.original.json')).read_bytes()==evidence
    restore_omxh_finalization(plan,evidence_dir=provisional['evidence'],scheduler_log_dir=provisional['log'],preflight=lambda:None)
    assert rows(provisional)==before
    with pytest.raises(ValueError,match='RESTORED_PLAN'):run(provisional,plan)


def test_transaction_fault_rolls_back_all_rows_and_requires_explicit_recovery(provisional):
    before=rows(provisional);plan=provisional['prepare']()
    def fail(stage,n):
        if stage=='after_row' and n==1:raise RuntimeError('INJECTED_DEATH')
    with pytest.raises(RuntimeError,match='INJECTED'):run(provisional,plan,fault=fail)
    assert rows(provisional)==before
    with pytest.raises(ValueError,match='EXPLICIT_RECOVERY'):run(provisional,plan)
    assert run(provisional,plan,recover=True)['replaced_rows']==2


def test_commit_before_receipt_recovers_without_second_write(provisional):
    plan=provisional['prepare']()
    def fail(stage,n):
        if stage=='after_commit':raise RuntimeError('COMMIT_BEFORE_RECEIPT')
    with pytest.raises(RuntimeError,match='COMMIT_BEFORE'):run(provisional,plan,fault=fail)
    after=rows(provisional)
    with pytest.raises(ValueError,match='EXPLICIT_RECOVERY'):run(provisional,plan)
    result=run(provisional,plan,recover=True);assert result['replaced_rows']==0 and len(result['already_final_row_ids'])==2
    assert rows(provisional)==after


def test_conflicting_original_rolls_back_peer_and_never_replaces_usa(provisional):
    plan=provisional['prepare']()
    with sqlite3.connect(provisional['path']) as c:c.execute('UPDATE osakedata SET volume=999 WHERE id=2')
    before=rows(provisional)
    with pytest.raises(ValueError,match='VERSION_CONFLICT'):run(provisional,plan)
    assert rows(provisional)==before
    bad=deepcopy(plan);bad['rows'][0]['before']['market']='usa'
    from services.price_revision_policy import digest
    bad['plan_id']=digest({k:v for k,v in bad.items() if k!='plan_id'})
    with pytest.raises(ValueError,match='OMXH_IDENTITY'):validate_plan(bad)


def test_missing_final_bar_is_retained(provisional):
    before=rows(provisional);plan=provisional['prepare'](provisional['bars'][:1]);assert len(plan['rows'])==1
    assert run(provisional,plan)['replaced_rows']==1
    assert rows(provisional)[1:]==before[1:]


def test_preflight_refusal_changes_no_prices(provisional):
    plan=provisional['prepare']();before=rows(provisional)
    def refuse():raise RuntimeError('BUSY_OWNER')
    with pytest.raises(RuntimeError,match='BUSY_OWNER'):
        apply_omxh_finalization(plan,evidence_dir=provisional['evidence'],scheduler_log_dir=provisional['log'],preflight=refuse)
    assert rows(provisional)==before and not provisional['evidence'].exists()


def test_helsinki_uses_exchange_holiday_and_dst_not_usa_calendar():
    assert not is_helsinki_session('2026-05-01')
    assert not is_helsinki_session('2026-05-14')
    assert last_completed_helsinki_session(datetime.fromisoformat('2026-06-18T15:59:59+00:00'))=='2026-06-17'
    assert last_completed_helsinki_session(datetime.fromisoformat('2026-06-18T16:00:00+00:00'))=='2026-06-18'


def test_legacy_ui_does_not_fetch_in_progress_helsinki_bar(tmp_path, monkeypatch):
    from collections import defaultdict
    from types import SimpleNamespace
    import datetime as clocks
    import main
    import services.market_sessions as sessions
    import analysis.stock_dow_structure as dow

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 5, 12, tzinfo=tz)

    monkeypatch.setattr(clocks, 'datetime', Clock)
    monkeypatch.setattr(sessions, 'datetime', Clock)
    database = tmp_path / 'legacy.db'
    with sqlite3.connect(database) as c:
        c.execute('CREATE TABLE osakedata(osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT)')
        c.execute("INSERT INTO osakedata VALUES('TEST.HE','2026-11-04',10,11,9,10,100,'omxh')")
    def no_provider(*args, **kwargs):
        pytest.fail('An intraday OMXH request reached Yahoo')
    monkeypatch.setattr(main.yf, 'Ticker', no_provider)
    monkeypatch.setattr(main, 'validate_market', lambda *a, **k: True)
    monkeypatch.setattr(main, '_today_exclusive_end_date', lambda: '2026-11-06')
    monkeypatch.setattr(dow, 'calculate_missing_or_outdated_stock_dow_structures', lambda **k: defaultdict(int))
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = str(database)
    app.update_market_dropdown = SimpleNamespace(value='omxh')
    app.update_start_input = SimpleNamespace(value='')
    app.update_stock_button = SimpleNamespace(disabled=False)
    app.loading_text = SimpleNamespace(value='', color=None)
    app.page = SimpleNamespace(update=lambda: None)
    main.RawCandleApp.update_stock_data.__wrapped__(app, None)
    assert 'Päivitetty: 0' in app.loading_text.value
    assert 'Ohitettu: 1' in app.loading_text.value
    with sqlite3.connect(database) as c:
        assert c.execute('SELECT COUNT(*) FROM osakedata').fetchone()[0] == 1


def test_invalid_evidence_does_not_leave_an_empty_original(tmp_path):
    from services.price_history_maintenance import durable_json
    path = tmp_path / 'durable' / 'original.json'
    with pytest.raises(ValueError):
        durable_json(path, {'invalid': float('nan')}, exclusive=True)
    assert not path.exists()
