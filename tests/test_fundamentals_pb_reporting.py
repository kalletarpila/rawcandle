import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from rawcandle.fundamentals.book_value import (
    CAVEAT, CURRENT_MODE, PROVIDER_MODE, book_value_report, current_pb, provider_reference,
)
from rawcandle.fundamentals.schema.parent_equity import migrate_parent_equity
from rawcandle.fundamentals.schema.provenance import read_provenance
from rawcandle.fundamentals.snapshot.renderer import _book_value_sections


def ordinary():
    return dict(parent_equity=1000, parent_equity_usd=1000, shares_outstanding=100,
                sharesbas=100, shareswa=100, shareswadil=110, sharefactor=1,
                marketcap=1000, price=10, provider_date_market_close=10,
                source_availability_date='2026-08-01', provider_date='2026-08-01',
                fiscal_year=2026, fiscal_quarter='Q2', reportperiod='2026-06-30',
                dimension='ARQ', pb=1, observation_id='accepted', content_hash='hash')


def calculate(row=None, **kwargs):
    return current_pb(row if row is not None else ordinary(), as_of='2026-10-07',
                      price=kwargs.pop('price',dict(pvm='2026-10-06',close=20)),
                      category=kwargs.pop('category','Domestic Common Stock'),
                      active_classes=kwargs.pop('active_classes',1))


@pytest.mark.parametrize('changes,reason', [
    ({'parent_equity_usd':0},'ZERO_EQUITY'),
    ({'parent_equity_usd':-1},'NEGATIVE_EQUITY'),
    ({'parent_equity_usd':None},'MISSING_EQUITY'),
    ({'parent_equity_usd':float('nan')},'MISSING_EQUITY'),
    ({'source_availability_date':'2026-01-01'},'STALE_EQUITY'),
    ({'source_availability_date':'2026-10-08'},'EQUITY_AVAILABILITY_UNVERIFIED'),
    ({'sharefactor':0},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'sharefactor':.125},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'sharefactor':None},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'shareswa':1},'SHARE_BASIS_UNVERIFIED'),
    ({'ownership_conflict':True},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'shareswa':None},'SHARE_BASIS_UNVERIFIED'),
    ({'shares_outstanding':101},'SHARE_BASIS_UNVERIFIED'),
    ({'shares_outstanding':None},'MISSING_SHARES'),
    ({'marketcap':2000},'SHARE_BASIS_UNVERIFIED'),
    ({'provider_date_market_close':20},'SHARE_BASIS_UNVERIFIED'),
    ({'provider_date_market_close':None},'SHARE_BASIS_UNVERIFIED'),
])
def test_null_reasons(changes,reason):
    row=ordinary() | changes
    result=calculate(row)
    assert result['value'] is None and result['reason']==reason


@pytest.mark.parametrize('kwargs,reason',[
    ({'price':None},'MISSING_PRICE'),
    ({'price':{'pvm':'2026-10-03','close':20}},'STALE_PRICE'),
    ({'price':{'pvm':'2026-10-08','close':20}},'MISSING_PRICE'),
    ({'category':'ADR Common Stock'},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'category':'Domestic Common Stock Primary Class'},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'category':None},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'active_classes':2},'OWNERSHIP_BASIS_UNVERIFIED'),
    ({'active_classes':0},'OWNERSHIP_BASIS_UNVERIFIED'),
])
def test_price_and_ownership(kwargs,reason):
    assert calculate(**kwargs)['reason']==reason


def test_current_determinism_and_parent_caveat():
    original=ordinary(); before=deepcopy(original)
    a=calculate(original);b=calculate(original)
    assert a==b and original==before
    assert a['value']==2 and a['market_cap']==2000
    assert a['semantic_mode']==CURRENT_MODE and a['role']=='REPORTING_ONLY'
    assert a['warnings']==['NEAR_ZERO_EQUITY']
    assert 'preferred-capital exclusion is not proven' in a['caveat']
    assert 'common equity' not in a['caveat']


def test_provider_rounding_absolute_not_relative():
    row=ordinary() | {'marketcap':52.602519,'pb':.053}
    assert provider_reference(row)['value']==.053
    assert provider_reference(row | {'pb':.052})['reason']=='PROVIDER_PB_ARITHMETIC_MISMATCH'
    assert provider_reference(row | {'dimension':'MRQ'})['value'] is None
    assert provider_reference(row | {'parent_equity_usd':-1})['reason']=='NEGATIVE_EQUITY'
    assert provider_reference(row)['semantic_mode']==PROVIDER_MODE


@pytest.fixture
def sources(tmp_path):
    cp=tmp_path/'canonical.db';pp=tmp_path/'provider.db';mp=tmp_path/'market.db'
    c=sqlite3.connect(cp);c.row_factory=sqlite3.Row
    c.executescript('''CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY, company_id INTEGER,
        fiscal_year INTEGER,fiscal_quarter TEXT,source_reportperiod TEXT,
        source_availability_date TEXT,identity_status TEXT);
        CREATE TABLE v4_quarter_financials(quarter_id INTEGER PRIMARY KEY,shares_outstanding REAL,revenue REAL);
        CREATE TABLE v4_field_provenance(provenance_id INTEGER PRIMARY KEY,quarter_id INTEGER,
        canonical_field TEXT,provider TEXT,provider_observation_id TEXT,accepted_at_utc TEXT);
        CREATE TABLE security(company_id INTEGER,current_ticker TEXT,active INTEGER);''')
    c.execute("INSERT INTO security VALUES(1,'TEST',1)")
    p=sqlite3.connect(pp)
    p.executescript('''CREATE TABLE provider_observation(observation_id TEXT PRIMARY KEY,provider TEXT,
        payload_json TEXT,content_hash TEXT,source_availability_date TEXT,fetched_at_utc TEXT);
        CREATE TABLE sharadar_ticker_metadata(ticker TEXT,category TEXT,fetched_at_utc TEXT);''')
    p.execute("INSERT INTO sharadar_ticker_metadata VALUES('TEST','Domestic Common Stock','2026-10-07')")
    m=sqlite3.connect(mp)
    m.executescript('''CREATE TABLE ticker_meta(ticker TEXT,market TEXT);
        INSERT INTO ticker_meta VALUES('TEST','usa');
        CREATE TABLE osakedata(osake TEXT,market TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL);''')
    # Latest four accepted quarter keys; Q3 2025 is absent, no interpolation.
    periods=[(2026,'Q2','2026-06-30','2026-08-01'),(2026,'Q1','2026-03-31','2026-05-01'),
             (2025,'Q4','2025-12-31','2026-02-01'),(2025,'Q2','2025-06-30','2025-08-01'),
             (2025,'Q1','2025-03-31','2025-05-01')]
    for i,(y,q,end,day) in enumerate(periods,1):
        c.execute('INSERT INTO v4_quarter VALUES(?,1,?,?,?,?,?)',(i,y,q,end,day,'ACCEPTED'))
        c.execute('INSERT INTO v4_quarter_financials VALUES(?,100,123)',(i,))
        c.execute("INSERT INTO v4_field_provenance VALUES(?,?,'shares_outstanding','SHARADAR',?,'2026-10-07')",(i,i,str(i)))
        raw={'ticker':'TEST','dimension':'ARQ','fiscalperiod':f'{y}-{q}','reportperiod':end,'date':day,
             'equity':1000,'equityusd':1000,'sharesbas':100,'shareswa':100,'sharefactor':1,'price':10,'marketcap':1000,'pb':1}
        if i==2:raw.pop('pb')
        p.execute('INSERT INTO provider_observation VALUES(?,?,?,?,?,?)',(str(i),'SHARADAR',json.dumps(raw),'hash'+str(i),day,'2026-10-07'))
        m.execute("INSERT INTO osakedata VALUES('TEST','usa',?,10,11,9,10)",(day,))
    # Richer MRQ must not fill the missing accepted ARQ pb.
    raw['dimension']='MRQ';raw['fiscalperiod']='2026-Q1';raw['pb']=99
    p.execute('INSERT INTO provider_observation VALUES(?,?,?,?,?,?)',('richer','SHARADAR',json.dumps(raw),'rich','2026-05-01','2026-10-07'))
    m.execute("INSERT INTO osakedata VALUES('TEST','usa','2026-10-06',20,21,19,20)")
    c.commit();p.commit();m.commit();c.close();p.close();m.close()
    return cp,pp,mp


def test_canonical_mapping_provenance_and_four_quarter_report(sources):
    cp,pp,mp=sources
    before=sqlite3.connect(cp).execute('SELECT quarter_id,shares_outstanding,revenue FROM v4_quarter_financials').fetchall()
    migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    c=sqlite3.connect(cp);c.row_factory=sqlite3.Row;m=sqlite3.connect(mp);m.row_factory=sqlite3.Row
    assert [tuple(r) for r in c.execute('SELECT quarter_id,shares_outstanding,revenue FROM v4_quarter_financials')]==before
    assert tuple(c.execute('SELECT parent_equity,parent_equity_usd FROM v4_quarter_financials WHERE quarter_id=1').fetchone())==(1000,1000)
    prov=read_provenance(c,canonical_field='parent_equity_usd',quarter_id=1)
    assert prov[0]['source_native_field']=='equityusd' and prov[0]['provider_observation_id']=='1'
    report=book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
    assert report['current']['value']==2 and report['provider']['value']==1
    assert [(r['fiscal_year'],r['fiscal_quarter']) for r in report['history']]==[(2026,'Q2'),(2026,'Q1'),(2025,'Q4'),(2025,'Q2')]
    assert report['history'][1]['value'] is None and report['history'][1]['observation_id']=='2'
    assert all(r['semantic_mode']==PROVIDER_MODE for r in report['history'])
    text='\n'.join(_book_value_sections({'book_value':report}))
    assert 'Book Value / P/B' in text and '2026-08-01' in text and 'Provider P/B history' in text
    assert 'N/A' in text and 'preferred-capital exclusion is not proven' in text
    assert 'not PIT-safe' in text
    first=report
    c.close();m.close()
    migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    c=sqlite3.connect(cp);c.row_factory=sqlite3.Row;m=sqlite3.connect(mp);m.row_factory=sqlite3.Row
    assert first==book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
    c.close();m.close()


def test_cross_observation_mismatch_rolls_back(sources):
    cp,pp,mp=sources
    with sqlite3.connect(pp) as p:
        raw=json.loads(p.execute("SELECT payload_json FROM provider_observation WHERE observation_id='1'").fetchone()[0]);raw['fiscalperiod']='2026-Q1'
        p.execute("UPDATE provider_observation SET payload_json=? WHERE observation_id='1'",(json.dumps(raw),))
    with pytest.raises(ValueError,match='ACCEPTED_OBSERVATION_MISMATCH'):
        migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    with sqlite3.connect(cp) as c:
        assert 'parent_equity' not in {r[1] for r in c.execute('pragma table_info(v4_quarter_financials)')}


def test_finalized_generation_write_blocked(sources):
    cp,pp,mp=sources
    (cp.parent/'generation_manifest.json').write_text('{}')
    with pytest.raises(PermissionError,match='INACTIVE_COPY_REQUIRED'):
        migrate_parent_equity(pp,cp,accepted_at='2026-10-07')


def test_accepted_projection_must_follow_current_provenance(sources):
    cp,pp,mp=sources
    migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    with sqlite3.connect(cp) as c,sqlite3.connect(mp) as m:
        c.row_factory=m.row_factory=sqlite3.Row
        c.execute("UPDATE v4_field_provenance SET provider_observation_id='newer' WHERE quarter_id=1")
        report=book_value_report(c,m,company_id=1,ticker='TEST',as_of='2026-10-07')
        assert report['current']['reason']=='MISSING_EQUITY'
        assert report['provider']['value'] is None


def test_existing_generation_publish_accepts_additive_schema_on_fixtures(sources,tmp_path):
    from rawcandle.fundamentals.generations import prepare_generation_from_candidates,activate_generation

    cp,pp,mp=sources
    migrate_parent_equity(pp,cp,accepted_at='2026-10-07')
    analysis=tmp_path/'analysis.db'
    with sqlite3.connect(analysis) as c:
        c.execute('CREATE TABLE unchanged_score(value INTEGER)')
        c.execute('INSERT INTO unchanged_score VALUES(42)')
    project=tmp_path/'isolated_project'
    prepared=prepare_generation_from_candidates({'canonical':cp,'provider':pp,'analysis':analysis},
        generation_id='pb_fixture',project_root=project,source='PB_REPORTING_COPY_VALIDATION')
    activated=activate_generation(prepared['manifest'],project_root=project)
    with sqlite3.connect(f"file:{activated.role_paths()['canonical']}?mode=ro",uri=True) as c:
        assert c.execute('SELECT count(parent_equity_usd) FROM v4_quarter_financials').fetchone()[0]==5
    with sqlite3.connect(f"file:{activated.role_paths()['analysis']}?mode=ro",uri=True) as c:
        assert c.execute('SELECT value FROM unchanged_score').fetchone()[0]==42
