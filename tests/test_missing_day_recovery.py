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
          INSERT INTO markets VALUES('usa',''),('omxh','.HE');
          CREATE TABLE splits_data(osake TEXT,is_price_data_corrected INTEGER);''')
        for ticker,days,market in [('AAA',[DAYS[0],DAYS[2]],'usa'),('EXIST',DAYS,'usa'),
                                   ('^GSPC',[TARGET],'usa'),('OTHER.HE',[DAYS[0],DAYS[2]],'omxh')]:
            c.executemany('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market,sector) VALUES(?,?,?,?,?,?,?,?,?)',
                          [(ticker,d,*BAR.values(),market,'preserve') for d in days])
    pauses = []
    monkeypatch.setattr(update.time, 'sleep', pauses.append)
    return db, tmp_path, pauses


class Stock:
    def __init__(self, ticker, *, rows=None, error=None, metadata=None):
        self.ticker = ticker
        self.rows = rows or {d:BAR.copy() for d in DAYS}
        self.error = error
        self.calls = []
        self.history_metadata = metadata or dict(symbol=ticker,instrumentType='EQUITY',
                 exchangeTimezoneName='America/New_York',firstTradeDate=946684800)

    def history(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return pd.DataFrame([{k.title():v for k,v in b.items()} for b in self.rows.values()],
                            index=pd.to_datetime(list(self.rows)))


def run(environment, factory=None, **kwargs):
    db, tmp, _ = environment
    return recovery.run_missing_day_recovery(db_path=db, market=kwargs.pop('market','usa'),
        requested_date=kwargs.pop('requested_date',TARGET), stock_factory=factory or (lambda t:Stock(t)),
        report_dir=tmp/'reports',backup_dir=tmp/'backups',
        identity_evidence=kwargs.pop('identity_evidence',recovery.ExistingIdentityEvidence()),
        today=date(2026,10,13), **kwargs)


def all_rows(db):
    with sqlite3.connect(db) as c:
        return c.execute('SELECT * FROM osakedata ORDER BY id').fetchall()


@pytest.mark.parametrize('value',['bad','2026-1-05','2026-02-30','2027-01-05','2026-10-13','2026-01-04'])
def test_invalid_future_today_weekend_never_fetch_or_write(environment,value):
    before = all_rows(environment[0])
    result = run(environment, factory=lambda t:pytest.fail('provider must not run'),requested_date=value)
    assert result.status == 'failed' and result.inserted_rows == 0
    assert all_rows(environment[0]) == before
    assert not (environment[1]/'backups').exists()


def test_success_exact_market_date_existing_preserved_backup_restore_and_idempotence(environment,monkeypatch):
    db,tmp,pauses = environment
    before = all_rows(db)
    verified_backups=[]
    cleanup=recovery.delete_verified_temporary_backup
    def verify_restore_then_cleanup(backup):
        path=Path(backup['destination'])
        assert all_rows(path)==before
        # Restore only this small synthetic fixture into memory.
        with sqlite3.connect(path) as source,sqlite3.connect(':memory:') as restored:
            source.backup(restored)
            assert restored.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert restored.execute('select count(*) from osakedata').fetchone()[0]==len(before)
        verified_backups.append(path)
        cleanup(backup)
    monkeypatch.setattr(recovery,'delete_verified_temporary_backup',verify_restore_then_cleanup)
    stock = Stock('AAA'); calls=[]; events=[]
    result = run(environment, factory=lambda t:calls.append(t) or stock,progress_callback=events.append)
    assert result.status == 'completed'
    assert result.inserted_rows == 1 and result.missing_candidates == 1
    assert result.remaining_missing_rows == 0 and result.skipped_existing == 2
    assert calls == ['AAA']  # Neither another market nor already-present rows are fetched.
    assert stock.calls == [{'start':'2026-01-02','end':'2026-01-07'}]
    assert 0.1 in pauses and 1.5 in pauses
    after=all_rows(db)
    assert after[:len(before)] == before
    assert after[-1][1:3] == ('AAA',TARGET) and after[-1][8] == 'usa'
    assert events[0].event_type == update.EVENT_STARTED and events[-1].event_type == update.EVENT_COMPLETED
    report=json.loads(Path(result.report_path).read_text())
    assert report['inserted_rows'] == 1 and report['existing_rows_modified'] == 0
    backup=Path(result.backup['destination'])
    assert result.backup['quick_check']=='ok' and result.backup['state']=='deleted'
    assert verified_backups==[backup] and not backup.exists()
    repeat=run(environment,factory=lambda t:pytest.fail('idempotent run must not fetch'))
    assert repeat.status=='completed' and repeat.inserted_rows==0
    assert len(list((tmp/'backups').glob('*.db')))==0
    assert all_rows(db)==after


@pytest.mark.parametrize('case,expected',[('unavailable','unavailable'),('error','provider_failure'),
 ('invalid','held'),('mismatch','held'),('identity','held'),('zero_volume','inserted')])
def test_provider_and_validation_outcomes(environment,case,expected):
    rows={d:BAR.copy() for d in DAYS};meta=None;error=None
    if case=='unavailable': rows.pop(TARGET)
    if case=='error': error=RuntimeError('provider failed')
    if case=='invalid': rows[TARGET]['high']=18
    if case=='mismatch': rows[DAYS[0]]['open']=20.1
    if case=='identity': meta=dict(symbol='DIFFERENT',instrumentType='EQUITY')
    if case=='zero_volume': rows[TARGET]['volume']=0
    result=run(environment,factory=lambda t:Stock(t,rows=rows,error=error,metadata=meta))
    record=next(r for r in result.records if r['ticker']=='AAA')
    assert record['status']==expected
    assert result.inserted_rows==int(expected=='inserted')


@pytest.mark.parametrize('field,value',[('open',float('inf')),('close',float('nan')),('volume',-1),('low',0)])
def test_invalid_numeric_bar(field,value):
    bar=BAR.copy();bar[field]=value
    assert not recovery.valid_bar(bar)


def test_partial_success_does_not_depend_on_held_peer(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'BAD',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")
    result=run(environment,factory=lambda t:Stock(t,metadata={'symbol':'WRONG'} if t=='BAD' else None))
    assert result.status=='partial' and result.inserted_rows==1
    assert result.identity_adjustment_holds==1 and result.remaining_missing_rows==1


def test_database_failure_rolls_back_all_pending_records(environment):
    db,_,_=environment;before=all_rows(db)
    with sqlite3.connect(db) as c:
        # Deliberately unsupported table trigger: writer must refuse before any insert.
        c.execute("CREATE TRIGGER refuse_recovery BEFORE INSERT ON osakedata BEGIN SELECT RAISE(ABORT,'fixture refusal'); END")
    result=run(environment)
    assert result.status=='failed' and result.database_failures and result.inserted_rows==0
    assert all_rows(db)==before
    assert result.backup['state']=='retained' and Path(result.backup['destination']).exists()


def test_real_second_insert_failure_rolls_back_first(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'ZZZ',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")
        c.execute('ALTER TABLE osakedata ADD COLUMN constraint_test INTEGER CHECK(osake<>\'ZZZ\' OR pvm<>\'2026-01-05\')')
    before=all_rows(db)
    result=run(environment)
    assert result.inserted_rows==0 and result.status=='failed'
    assert all_rows(db)==before


def test_unverified_session_stops_without_stock_fetch(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:c.execute("DELETE FROM osakedata WHERE osake='^GSPC'")
    calls=[]
    result=run(environment,factory=lambda t:calls.append(t) or Stock(t,rows={DAYS[0]:BAR}))
    assert calls==['^GSPC'] and result.status=='failed' and result.inserted_rows==0


def test_existing_scheduler_lock_rejects_duplicate(environment):
    from rawcandle.scheduler.runner import acquire_scheduler_lock,release_scheduler_lock
    db,tmp,_=environment;handle=acquire_scheduler_lock(str(tmp/'logs'))
    try:
        result=run(environment,factory=lambda t:pytest.fail('duplicate must not fetch'))
        assert result.status=='failed' and 'SchedulerAlreadyRunningError' in result.errors
    finally:release_scheduler_lock(handle)


def test_known_identity_evidence_is_guard_not_universe(environment):
    _,tmp,_=environment;canonical=tmp/'identities.db'
    with sqlite3.connect(canonical) as c:
        c.executescript("""CREATE TABLE company(company_id INTEGER,status TEXT);
            CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,exchange TEXT,valid_from TEXT,valid_to TEXT);
            CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT,valid_from TEXT,valid_to TEXT);
            INSERT INTO company VALUES(1,'ACTIVE');
            INSERT INTO security VALUES(1,1,'AAA','NASDAQ','2026-01-06',NULL);""")
    evidence=recovery.ExistingIdentityEvidence(canonical)
    result=run(environment,factory=lambda t:pytest.fail('pre-start security must not fetch'),identity_evidence=evidence)
    assert result.legitimately_unavailable==1 and result.inserted_rows==0
    assert result.tickers_examined==3  # Remains the market's stored universe.


def test_stale_anchors_skip_one_peer_inside_transaction(environment):
    db,_,_=environment
    accepted=[dict(ticker='AAA',date=TARGET,market='usa',bar=BAR,anchors={DAYS[0]:dict(BAR,close=20)})]
    inserted,changed=recovery.insert_validated_rows(db,accepted,TARGET,'usa')
    assert inserted==0 and changed[0]['reason']=='ANCHOR_CHANGED_BEFORE_WRITE'


def test_post_commit_verification_failure_retains_temporary_backup(environment,monkeypatch):
    before=all_rows(environment[0])
    def fail(*args):raise RuntimeError('synthetic post-commit verification failure')
    monkeypatch.setattr(recovery,'verify_committed_rows',fail)
    result=run(environment)
    assert result.status=='failed' and result.inserted_rows==1
    assert not result.writes_verified and result.backup['state']=='retained'
    assert all_rows(Path(result.backup['destination']))==before
    assert all_rows(environment[0])[:len(before)]==before
    report=json.loads(Path(result.report_path).read_text())
    assert report['backup']['destination']==result.backup['destination']


def test_cleanup_leaves_unrelated_backup_and_wal_shm_names(environment):
    _,tmp,_=environment
    backup_dir=tmp/'backups';backup_dir.mkdir()
    unrelated=backup_dir/'unrelated.db';unrelated.write_bytes(b'not this operation')
    for suffix in ['-wal','-shm']:(backup_dir/('unrelated.db'+suffix)).write_bytes(b'untouched')
    result=run(environment)
    assert result.backup['state']=='deleted' and unrelated.read_bytes()==b'not this operation'
    assert (backup_dir/'unrelated.db-wal').read_bytes()==b'untouched'
    assert (backup_dir/'unrelated.db-shm').read_bytes()==b'untouched'


def test_partial_holds_with_conclusive_safe_writes_clean_backup(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'BAD',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")
    result=run(environment,factory=lambda t:Stock(t,metadata={'symbol':'WRONG'} if t=='BAD' else None))
    assert result.status=='partial' and result.inserted_rows==1 and result.writes_verified
    assert result.backup['state']=='deleted'


def test_legacy_pacing_values_unchanged(environment):
    pauses=environment[2]
    update.sleep_after_legacy_stock_ticker(0)
    update.sleep_after_legacy_stock_ticker(50)
    update.sleep_legacy_stock_batch(499)
    update.sleep_legacy_stock_batch(500)
    assert pauses==[1.5,1.0,30]


def test_raised_rate_limit_stops_later_requests_without_retries(environment):
    from yfinance.exceptions import YFRateLimitError
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'ZZZ',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")
    calls=[]
    result=run(environment,factory=lambda t:calls.append(t) or Stock(t,error=YFRateLimitError()))
    assert calls==['AAA'] and result.provider_failures==1 and result.inserted_rows==0
    assert any('Yahoo-rajoitus' in e for e in result.errors)


def test_empty_market_does_not_silently_use_default(environment):
    result=run(environment,market='',factory=lambda t:pytest.fail('no market chosen'))
    assert result.status=='failed' and result.inserted_rows==0


def test_writer_rejects_outside_date_and_market(environment):
    before=all_rows(environment[0])
    for day,market in [('2026-01-06','usa'),(TARGET,'omxh')]:
        record=dict(ticker='AAA',date=day,market=market,bar=BAR,anchors={})
        with pytest.raises(ValueError,match='OUTSIDE_VALIDATED'):
            recovery.insert_validated_rows(environment[0],[record],TARGET,'usa')
        assert all_rows(environment[0])==before


def test_bad_stored_anchor_is_local_hold_and_safe_peer_continues(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) SELECT 'BAD',pvm,open,high,low,close,volume,market FROM osakedata WHERE osake='AAA'")
        c.execute("UPDATE osakedata SET high=1 WHERE osake='BAD' AND pvm='2026-01-02'")
    calls=[]
    result=run(environment,factory=lambda t:calls.append(t) or Stock(t))
    assert calls==['AAA'] and result.inserted_rows==1 and result.identity_adjustment_holds==1
    assert next(r for r in result.records if r['ticker']=='BAD')['reason']=='INVALID_STORED_ANCHOR'


def test_wrong_market_existing_key_is_held_without_fetch(environment):
    db,_,_=environment
    with sqlite3.connect(db) as c:
        c.execute('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)',('AAA',TARGET,*BAR.values(),'omxh'))
    before=all_rows(db)
    result=run(environment,factory=lambda t:pytest.fail('occupied key cannot be repaired'))
    assert result.identity_adjustment_holds==1 and result.remaining_missing_rows==1
    assert all_rows(db)==before


def test_interrupted_transaction_retains_backup_and_rolls_back(environment,monkeypatch):
    db,tmp,_=environment;before=all_rows(db)
    def interrupted(db,accepted,ds,market):
        with sqlite3.connect(db) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)',('AAA',TARGET,*BAR.values(),'usa'))
            raise KeyboardInterrupt()
    monkeypatch.setattr(recovery,'insert_validated_rows',interrupted)
    with pytest.raises(KeyboardInterrupt):run(environment)
    assert all_rows(db)==before
    backups=list((tmp/'backups').glob('*.db'))
    assert len(backups)==1 and all_rows(backups[0])==before


def test_undated_alias_and_approved_successor_guards_use_small_fixtures(tmp_path):
    canonical=tmp_path/'identity_fixture.db'
    with sqlite3.connect(canonical) as c:
        c.executescript("""CREATE TABLE company(company_id INTEGER,status TEXT);
          CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,exchange TEXT,valid_from TEXT,valid_to TEXT);
          CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT,valid_from TEXT,valid_to TEXT);
          INSERT INTO company VALUES(1,'ACTIVE');
          INSERT INTO security VALUES(1,1,'NEW','NASDAQ',NULL,NULL);
          INSERT INTO ticker_alias VALUES(1,'OLD',NULL,NULL);""")
    evidence=recovery.ExistingIdentityEvidence(canonical)
    assert evidence.hold_reason('NEW',TARGET,DAYS[0],DAYS[2])=='UNDATED_OR_CROSSING_ALIAS_BOUNDARY'
    assert evidence.hold_reason('OLD',TARGET,DAYS[0],DAYS[2])=='FORMER_TICKER_REQUIRES_REVIEW'
    registry=tmp_path/'review_fixture.json'
    registry.write_text(json.dumps({'records':[{'subject_ticker':'NEW','predecessor_ticker':'OLD',
                      'effective_date':'2026-01-05','review_status':'APPROVED'}]}))
    evidence=recovery.ExistingIdentityEvidence(registry=registry)
    assert evidence.hold_reason('NEW','2026-01-02','2026-01-01','2026-01-03')=='TARGET_BEFORE_REVIEWED_SUCCESSOR'
    assert evidence.hold_reason('OLD',TARGET,DAYS[0],DAYS[2])=='TARGET_AFTER_REVIEWED_SUCCESSOR'
