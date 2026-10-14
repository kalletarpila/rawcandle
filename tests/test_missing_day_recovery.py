from datetime import date
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from services import missing_day_recovery as recovery
from services import stock_update_service as update

TARGET = '2026-01-05'
DAYS = ['2026-01-02', TARGET, '2026-01-06']
BAR = dict(open=20., high=22., low=19., close=21., volume=100)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    db = tmp_path/'prices.db'
    with sqlite3.connect(db) as c:
        c.executescript('''CREATE TABLE osakedata(id INTEGER PRIMARY KEY AUTOINCREMENT,
          osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,
          market TEXT,sector TEXT,UNIQUE(osake,pvm));
          CREATE TABLE markets(abbreviation TEXT,yahoo_suffix TEXT);
          INSERT INTO markets VALUES('usa',''),('omxh','.HE');''')
        for ticker, days, market in [('AAA', [DAYS[0], DAYS[2]], 'usa'), ('EXIST', DAYS, 'usa'),
                                     ('^GSPC', [TARGET], 'usa'), ('OTHER.HE', [DAYS[0]], 'omxh')]:
            c.executemany('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market,sector) VALUES(?,?,?,?,?,?,?,?,?)',
                          [(ticker,d,*BAR.values(),market,'preserve') for d in days])
    pauses = []
    monkeypatch.setattr(update.time, 'sleep', pauses.append)
    return db, tmp_path, pauses


class Stock:
    def __init__(self, ticker, *, rows=None, error=None, metadata=None):
        self.rows = {TARGET: BAR.copy()} if rows is None else rows
        self.error = error
        self.calls = []
        self.history_metadata = (dict(symbol=ticker, instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York', firstTradeDate=946684800)
            if metadata is None else metadata)

    def history(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return pd.DataFrame([{k.title():v for k,v in b.items()} for b in self.rows.values()],
                            index=pd.to_datetime(list(self.rows)))


def run(environment, factory=None, **kwargs):
    db, tmp, _ = environment
    return recovery.run_missing_day_recovery(db_path=db, market=kwargs.pop('market','usa'),
        requested_date=kwargs.pop('requested_date',TARGET), stock_factory=factory or Stock,
        report_dir=tmp/'reports',
        identity_evidence=kwargs.pop('identity_evidence',recovery.ExistingIdentityEvidence()),
        today=date(2026,10,14), **kwargs)


def all_rows(db):
    with sqlite3.connect(db) as c:
        return c.execute('SELECT * FROM osakedata ORDER BY id').fetchall()


def aaa(result):
    return next(r for r in result.records if r['ticker']=='AAA')


@pytest.mark.parametrize('value',['bad','2026-1-05','2026-02-30','2027-01-05','2026-10-14','2026-01-04'])
def test_invalid_date_never_fetches_or_writes(environment,value):
    before=all_rows(environment[0])
    result=run(environment, factory=lambda t:pytest.fail('must not fetch'), requested_date=value)
    assert result.status=='failed' and all_rows(environment[0])==before


def test_success_existing_skips_preservation_scope_pacing_and_restart(environment):
    db,tmp,pauses=environment;before=all_rows(db);calls=[];events=[];stock=Stock('AAA')
    result=run(environment,factory=lambda t:calls.append(t) or stock,progress_callback=events.append)
    assert result.status=='completed' and result.inserted_rows==1 and result.writes_verified
    assert result.tickers_examined==3 and result.missing_candidates==1 and result.skipped_existing==2
    assert result.remaining_missing_rows==0 and calls==['AAA']
    assert stock.calls==[{'start':TARGET,'end':'2026-01-06'}]
    assert pauses==[0.1,1.5] and events[-1].event_type==update.EVENT_COMPLETED
    after=all_rows(db)
    assert after[:len(before)]==before and after[-1][1:3]==('AAA',TARGET) and after[-1][8]=='usa'
    assert json.loads(Path(result.report_path).read_text())['inserted_rows']==1
    repeat=run(environment,factory=lambda t:pytest.fail('restart must skip'))
    assert repeat.inserted_rows==0 and repeat.status=='completed' and all_rows(db)==after
    assert result.backup['state']=='not_created' and not (tmp/'backups').exists()


@pytest.mark.parametrize('instrument',['EQUITY','ETF','INDEX','MUTUALFUND'])
def test_instrument_type_and_absent_fundamentals_or_start_do_not_gate(environment,instrument):
    stock=Stock('AAA',metadata=dict(symbol='AAA',instrumentType=instrument,
                                  exchangeTimezoneName='America/New_York'))
    result=run(environment,factory=lambda t:stock)
    assert aaa(result)['status']=='inserted'


@pytest.mark.parametrize('variant',['no_following','no_previous','invalid_neighbor','changed_neighbor'])
def test_anchors_not_required_or_compared(environment,variant):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        if variant=='no_following':c.execute("DELETE FROM osakedata WHERE osake='AAA' AND pvm>?",(TARGET,))
        if variant=='no_previous':c.execute("DELETE FROM osakedata WHERE osake='AAA' AND pvm<?",(TARGET,))
        if variant=='invalid_neighbor':c.execute("UPDATE osakedata SET high=1 WHERE osake='AAA'")
    stock=Stock('AAA',rows={DAYS[0]:dict(BAR,open=20.1,volume=107),TARGET:BAR,DAYS[2]:dict(BAR,volume=1000)})
    assert run(environment,factory=lambda t:stock).inserted_rows==1


@pytest.mark.parametrize('field,value',[('open',float('inf')),('close',float('nan')),('volume',-1),
                                        ('low',0),('high',18),('volume',float('inf'))])
def test_invalid_target_rejected(environment,field,value):
    result=run(environment,factory=lambda t:Stock(t,rows={TARGET:dict(BAR,**{field:value})}))
    assert result.inserted_rows==0 and aaa(result)['status']=='invalid_data'
    assert result.invalid_records==1


def test_zero_volume_accepted(environment):
    assert run(environment,factory=lambda t:Stock(t,rows={TARGET:dict(BAR,volume=0)})).inserted_rows==1


@pytest.mark.parametrize('metadata',[
    dict(symbol='WRONG',exchangeTimezoneName='America/New_York'),
    dict(symbol='AAA',exchangeTimezoneName='Europe/Helsinki'),
    dict(symbol='AAA'),
    dict(symbol='AAA',exchangeTimezoneName='America/New_York',firstTradeDate=1893456000)])
def test_provider_symbol_market_or_demonstrated_start_conflict_held(environment,metadata):
    result=run(environment,factory=lambda t:Stock(t,metadata=metadata))
    assert result.inserted_rows==0 and aaa(result)['status']=='held'


def test_wrong_session_not_inserted(environment):
    result=run(environment,factory=lambda t:Stock(t,rows={DAYS[2]:BAR}))
    assert result.inserted_rows==0 and aaa(result)['status']=='unavailable'


@pytest.mark.parametrize('side,expected',[('before','POST_DELISTING_POSSIBLE'),
    ('after','PRE_LISTING_POSSIBLE'),('both','NO_TRADING_DATA'),('neither','UNKNOWN')])
def test_no_data_diagnostic_context_at_most_14_days(environment,side,expected):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        if side in ('before','neither'):c.execute("DELETE FROM osakedata WHERE osake='AAA' AND pvm>?",(TARGET,))
        if side in ('after','neither'):c.execute("DELETE FROM osakedata WHERE osake='AAA' AND pvm<?",(TARGET,))
    if side=='neither':
        with sqlite3.connect(db) as c:
            c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES('AAA','2025-01-02',20,22,19,21,100,'usa')")
    stock=Stock('AAA',rows={})
    result=run(environment,factory=lambda t:stock)
    assert result.inserted_rows==0 and aaa(result)['reason']==expected
    for call in stock.calls:
        assert (date.fromisoformat(call['end'])-date.fromisoformat(call['start'])).days<=14
    assert len(stock.calls)==(1 if side=='both' else 2)


def test_dated_reviewed_conflicts_hold_with_exact_evidence(environment):
    _,tmp,_=environment;registry=tmp/'identity.json'
    entry=dict(subject_ticker='AAA',predecessor_ticker='OLD',effective_date='2026-01-06',
               review_status='APPROVED',resolution_class='REORGANIZATION_SUCCESSOR',
               evidence=[{'fact':'dated successor starts January 6'}])
    registry.write_text(json.dumps({'records':[entry]}))
    identity=recovery.ExistingIdentityEvidence(registry)
    result=run(environment,identity_evidence=identity,factory=lambda t:pytest.fail('known conflict'))
    assert aaa(result)['status']=='held' and aaa(result)['identity_evidence']['evidence']==entry['evidence']
    assert identity.conflict('OLD','2026-01-06')['reason']=='TARGET_AFTER_REVIEWED_SUCCESSOR'
    assert identity.conflict('AAA','2026-01-06') is None


@pytest.mark.parametrize('review,effective',[('PROPOSED',None),('APPROVED',None),('PROPOSED','2026-01-06')])
def test_undated_or_unapproved_metadata_not_proven_conflict(environment,review,effective):
    _,tmp,_=environment;registry=tmp/'identity.json'
    registry.write_text(json.dumps({'records':[dict(subject_ticker='AAA',review_status=review,effective_date=effective)]}))
    assert run(environment,identity_evidence=recovery.ExistingIdentityEvidence(registry)).inserted_rows==1


def add_zzz(db):
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'ZZZ',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")


def test_incremental_commit_survives_interruption_and_restart(environment):
    db,tmp,_=environment;add_zzz(db);before=all_rows(db)
    def factory(ticker):
        if ticker=='ZZZ':raise KeyboardInterrupt()
        return Stock(ticker)
    with pytest.raises(KeyboardInterrupt):run(environment,factory=factory)
    after=all_rows(db)
    assert after[:len(before)]==before and after[-1][1:3]==('AAA',TARGET)
    report=json.loads(next((tmp/'reports').glob('*.json')).read_text())
    assert report['status']=='interrupted' and report['inserted_rows']==1
    calls=[]
    result=run(environment,factory=lambda t:calls.append(t) or Stock(t))
    assert calls==['ZZZ'] and result.inserted_rows==1 and result.status=='completed'


def test_later_database_failure_does_not_rollback_committed_peer(environment):
    db,_,_=environment;add_zzz(db)
    with sqlite3.connect(db) as c:
        c.execute("ALTER TABLE osakedata ADD COLUMN constraint_test INTEGER CHECK(osake<>'ZZZ' OR pvm<>'2026-01-05')")
    result=run(environment)
    assert result.inserted_rows==1 and result.database_failures==1 and result.status=='failed'
    assert aaa(result)['status']=='inserted'
    assert not any(r[1]=='ZZZ' and r[2]==TARGET for r in all_rows(db))


def test_peer_provider_failure_independent(environment):
    db,_,_=environment;add_zzz(db)
    result=run(environment,factory=lambda t:Stock(t,error=RuntimeError() if t=='ZZZ' else None))
    assert result.inserted_rows==1 and result.provider_failures==1 and result.status=='partial'


def test_raised_rate_limit_stops_later_requests_no_retries(environment):
    from yfinance.exceptions import YFRateLimitError
    db,_,_=environment;add_zzz(db);calls=[]
    result=run(environment,factory=lambda t:calls.append(t) or Stock(t,error=YFRateLimitError()))
    assert calls==['AAA'] and result.provider_failures==1 and result.inserted_rows==0


def test_existing_scheduler_lock_rejects_duplicate(environment):
    from rawcandle.scheduler.runner import acquire_scheduler_lock,release_scheduler_lock
    _,tmp,_=environment;handle=acquire_scheduler_lock(str(tmp/'logs'))
    try:
        result=run(environment,factory=lambda t:pytest.fail('locked operation'))
        assert result.status=='failed' and 'SchedulerAlreadyRunningError' in result.errors
    finally:release_scheduler_lock(handle)


def test_writer_concurrent_key_and_invalid_scope(environment):
    db,_,_=environment;before=all_rows(db)
    record=dict(ticker='EXIST',date=TARGET,market='usa',bar=BAR)
    inserted,changed=recovery.insert_validated_rows(db,[record],TARGET,'usa')
    assert inserted==0 and changed[0]['status']=='existing' and all_rows(db)==before
    for day,market in [('2026-01-06','usa'),(TARGET,'omxh')]:
        with pytest.raises(ValueError,match='OUTSIDE_VALIDATED'):
            recovery.insert_validated_rows(db,[dict(record,ticker='AAA',date=day,market=market)],TARGET,'usa')
    assert all_rows(db)==before


def test_trigger_table_refused_without_backup_or_writes(environment):
    db,tmp,_=environment;before=all_rows(db)
    with sqlite3.connect(db) as c:c.execute("CREATE TRIGGER refuse BEFORE INSERT ON osakedata BEGIN SELECT RAISE(ABORT,'no'); END")
    result=run(environment)
    assert result.inserted_rows==0 and result.database_failures==1 and all_rows(db)==before
    assert not (tmp/'backups').exists()


def test_postcommit_verification_failure_reports_real_insert(environment,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('verification failure')
    monkeypatch.setattr(recovery,'verify_committed_rows',fail)
    result=run(environment)
    assert result.inserted_rows==1 and not result.writes_verified and result.status=='failed'
    assert aaa(result)['status']=='committed_unverified'
    assert any(r[1:3]==('AAA',TARGET) for r in all_rows(environment[0]))


def test_empty_market_does_not_use_default(environment):
    assert run(environment,market='',factory=lambda t:pytest.fail('no selection')).status=='failed'


def test_legacy_pacing_unchanged(environment):
    update.sleep_after_legacy_stock_ticker(0)
    update.sleep_after_legacy_stock_ticker(50)
    update.sleep_legacy_stock_batch(499)
    update.sleep_legacy_stock_batch(500)
    assert environment[2]==[1.5,1.0,30]


def test_empty_history_without_provider_metadata_is_no_data_not_identity_hold(environment):
    result=run(environment,factory=lambda t:Stock(t,rows={},metadata={}))
    assert aaa(result)['status']=='unavailable' and aaa(result)['reason']=='NO_TRADING_DATA'


def test_context_wrong_provider_identity_is_held(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:c.execute("DELETE FROM osakedata WHERE osake='AAA' AND pvm>?",(TARGET,))
    stock=Stock('AAA',rows={})
    original=stock.history
    def history(**kwargs):
        data=original(**kwargs)
        if len(stock.calls)==2:stock.history_metadata['symbol']='WRONG'
        return data
    stock.history=history
    result=run(environment,factory=lambda t:stock)
    assert aaa(result)['status']=='held' and aaa(result)['reason']=='PROVIDER_SYMBOL_MISMATCH'


@pytest.mark.parametrize('field,value',[('ticker','OTHER'),('market','omxh')])
def test_converted_row_scope_checked_before_assignment(environment,monkeypatch,field,value):
    row=dict(ticker='AAA',date=TARGET,market='usa',**BAR)
    row[field]=value
    monkeypatch.setattr(update,'convert_histories_to_ohlcv_rows',lambda **kwargs:[update.StockOhlcvRow(**row)])
    result=run(environment)
    assert result.inserted_rows==0 and aaa(result)['reason']=='PROVIDER_ROW_IDENTITY_MISMATCH'


def test_transaction_failure_rolls_back_active_batch(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("ALTER TABLE osakedata ADD COLUMN constraint_test INTEGER CHECK(osake<>'ZZZ' OR pvm<>'2026-01-05')")
    before=all_rows(db)
    records=[dict(ticker=t,date=TARGET,market='usa',bar=BAR) for t in ['AAA','ZZZ']]
    with pytest.raises(sqlite3.IntegrityError):recovery.insert_validated_rows(db,records,TARGET,'usa')
    assert all_rows(db)==before


def test_unique_key_required(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.executescript('ALTER TABLE osakedata RENAME TO old; CREATE TABLE osakedata AS SELECT * FROM old; DROP TABLE old;')
    result=run(environment)
    assert result.inserted_rows==0 and result.database_failures==1


def test_report_failure_does_not_relabel_committed_insert(environment,monkeypatch):
    real=recovery.write_text_atomic
    def write(path,*args,**kwargs):
        content=json.loads(args[0])
        if content['inserted_rows']:
            raise OSError('synthetic report failure after commit')
        return real(path,*args,**kwargs)
    monkeypatch.setattr(recovery,'write_text_atomic',write)
    result=run(environment)
    assert result.inserted_rows==1 and aaa(result)['status']=='inserted' and result.status=='failed'
    assert any(r[1:3]==('AAA',TARGET) for r in all_rows(environment[0]))


def test_network_oserror_is_independent_provider_failure(environment):
    db,_,_=environment;add_zzz(db)
    result=run(environment,factory=lambda t:Stock(t,error=OSError('network') if t=='AAA' else None))
    assert aaa(result)['status']=='provider_failure' and result.provider_failures==1
    assert result.inserted_rows==1 and result.status=='partial'


def test_concurrent_insert_after_fetch_is_skipped_without_overwrite(environment):
    db,_,_=environment
    stock=Stock('AAA');history=stock.history
    def fetch(**kwargs):
        with sqlite3.connect(db) as c:
            c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES('AAA',?,30,32,29,31,150,'usa')",(TARGET,))
        return history(**kwargs)
    stock.history=fetch
    result=run(environment,factory=lambda t:stock)
    assert result.inserted_rows==0 and aaa(result)['status']=='existing'
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT open,volume FROM osakedata WHERE osake='AAA' AND pvm=?",(TARGET,)).fetchone()==(30,150)


def test_duplicate_provider_dates_rejected(environment):
    stock=Stock('AAA')
    stock.history=lambda **kwargs:pd.DataFrame([dict(Open=20,High=22,Low=19,Close=21,Volume=100)]*2,
                                             index=pd.to_datetime([TARGET,TARGET]))
    result=run(environment,factory=lambda t:stock)
    assert result.inserted_rows==0 and aaa(result)['reason']=='DUPLICATE_PROVIDER_DATES'
