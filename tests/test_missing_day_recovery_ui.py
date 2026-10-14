from types import SimpleNamespace
import inspect

import pytest
import main
from services import missing_day_recovery as recovery


@pytest.fixture
def app():
    app=main.RawCandleApp.__new__(main.RawCandleApp)
    app.page=SimpleNamespace(update=lambda:None)
    app.osakedata_db_path='/tmp/synthetic_prices.db'
    app.update_market_dropdown=SimpleNamespace(value='omxh',disabled=False)
    app.update_stock_button=SimpleNamespace(disabled=False)
    app._stock_update_in_progress=False
    app._build_stock_update_service_adapters=lambda:{'stock_factory':object()}
    app._build_missing_day_controls()
    app.missing_day_date.value='2026-01-05'
    return app


def test_controls_exact_text_and_existing_market_placement(app):
    controls=app._build_missing_day_controls()
    assert controls.controls[0].value=='Hae puuttuva päivä'
    assert controls.controls[1].value=='Hakee valitulta päivältä vain puuttuvat osakkeiden OHLCV-tiedot. Olemassa olevia tietoja ei muuteta.'
    assert app.missing_day_button.text=='Hae puuttuvan päivän tiedot'
    assert app.missing_day_button.on_click==app.recover_missing_day
    source=inspect.getsource(main.RawCandleApp)
    assert 'self.update_stock_button,' in source and 'self.missing_day_controls,' in source


def test_reuses_selected_market_progress_duplicate_guard_terminal_report(app,monkeypatch):
    workers=[];calls=[]
    app._start_missing_day_worker=workers.append
    def run(**kwargs):
        calls.append(kwargs)
        from services.stock_update_service import StockUpdateProgressEvent,EVENT_TICKER_UPDATED
        kwargs['progress_callback'](StockUpdateProgressEvent(EVENT_TICKER_UPDATED,message='1/2: AAA',index=1,total=2))
        assert app.missing_day_progress.value==0.5
        return recovery.MissingDayResult(date='2026-01-05',market='omxh',status='partial',tickers_examined=2,
             missing_candidates=2,inserted_rows=1,identity_adjustment_holds=1,remaining_missing_rows=1,
             report_path='/tmp/synthetic_report.json',backup={'state':'not_created'})
    monkeypatch.setattr(recovery,'run_missing_day_recovery',run)
    app.recover_missing_day()
    assert app.missing_day_button.disabled and app.update_stock_button.disabled
    assert app.update_market_dropdown.disabled and app._stock_update_in_progress
    app.recover_missing_day()
    assert len(workers)==1
    workers[0]()
    assert calls[0]['market']=='omxh' and calls[0]['requested_date']=='2026-01-05'
    assert not app.missing_day_button.disabled and not app.update_stock_button.disabled
    assert not app._stock_update_in_progress and not app.missing_day_progress.visible
    assert 'partial' in app.missing_day_status.value and 'Lisätty: 1' in app.missing_day_status.value
    assert 'Puuttuu edelleen: 1' in app.missing_day_status.value
    assert '/tmp/synthetic_report.json' in app.missing_day_report.value and 'not_created' in app.missing_day_report.value


def test_invalid_date_never_starts_worker(app):
    app.missing_day_date.value='2026-01-04'
    app._start_missing_day_worker=lambda worker:pytest.fail('invalid date must not start')
    app.recover_missing_day()
    assert not app._stock_update_in_progress
    assert 'pörssipäivä' in app.missing_day_status.value


def test_worker_failure_restores_controls(app,monkeypatch):
    def fail(**kwargs):raise RuntimeError('synthetic failure')
    monkeypatch.setattr(recovery,'run_missing_day_recovery',fail)
    app._start_missing_day_worker=lambda worker:worker()
    app.recover_missing_day()
    assert not app._stock_update_in_progress and not app.missing_day_button.disabled
    assert 'epäonnistui' in app.missing_day_status.value
    assert not app._missing_day_submit_lock.locked()


def test_normal_update_is_blocked_while_missing_day_busy(app):
    app._stock_update_in_progress=True
    app._use_stock_update_service=True
    app._update_stock_data_via_service_ui_flow=lambda e:None
    # Existing normal service UI guard returns; no acquisition or new lock.
    app.update_stock_data(None)
    assert app._stock_update_in_progress


def test_all_markets_selection_requires_explicit_one_market(app):
    app.update_market_dropdown.value=''
    app._start_missing_day_worker=lambda worker:pytest.fail('no market chosen')
    app.recover_missing_day()
    assert 'Valitse yksi markkina' in app.missing_day_status.value


def test_ui_to_real_backend_on_small_synthetic_database(tmp_path,monkeypatch,app):
    import sqlite3
    import pandas as pd
    from services import stock_update_service as update
    db=tmp_path/'small_fixture.db'
    with sqlite3.connect(db) as c:
        c.executescript("""CREATE TABLE osakedata(id INTEGER PRIMARY KEY,osake TEXT,pvm TEXT,
          open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT,UNIQUE(osake,pvm));
          CREATE TABLE markets(abbreviation TEXT);INSERT INTO markets VALUES('usa');
          CREATE TABLE splits_data(osake TEXT,is_price_data_corrected INTEGER);""")
        c.executemany('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)',
          [('AAA','2026-01-02',10,12,9,11,100,'usa'),('AAA','2026-01-06',10,12,9,11,100,'usa'),
           ('^GSPC','2026-01-05',10,12,9,11,100,'usa')])
    class Stock:
        history_metadata=dict(symbol='AAA',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',firstTradeDate=946684800)
        def history(self,**kwargs):
            return pd.DataFrame(dict(Open=[10,10,10],High=[12,12,12],Low=[9,9,9],Close=[11,11,11],Volume=[100,100,100]),
                                index=pd.to_datetime(['2026-01-02','2026-01-05','2026-01-06']))
    app.osakedata_db_path=str(db);app.update_market_dropdown.value='usa'
    app._build_stock_update_service_adapters=lambda:{'stock_factory':lambda t:Stock()}
    app._start_missing_day_worker=lambda worker:worker()
    monkeypatch.setattr(update.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(main,'__file__',str(tmp_path/'main.py'))
    real_run=recovery.run_missing_day_recovery
    monkeypatch.setattr(recovery,'run_missing_day_recovery',lambda **kwargs:real_run(**kwargs,identity_evidence=recovery.ExistingIdentityEvidence()))
    app.recover_missing_day()
    assert 'completed' in app.missing_day_status.value and 'Lisätty: 1' in app.missing_day_status.value
    assert 'not_created' in app.missing_day_report.value and not list((tmp_path/'backups').rglob('*.db'))
    with sqlite3.connect(db) as c:assert c.execute('SELECT count(*) FROM osakedata').fetchone()[0]==4
