"""Research-only bounded acquisition; explicit CLI use, no production writes."""
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from dataclasses import asdict
import json,logging,math,sqlite3
import pandas as pd
import yfinance as yf
from services import stock_update_service as update
from services import missing_day_recovery as recovery
from rawcandle.io_atomic import write_text_atomic

def main():
    ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/yahoo_price_basis_comparison_20261014';OUT.mkdir(parents=True,exist_ok=True)
    SAMPLE=['NVDA','AMD','AAPL','MSFT','AMZN','AVGO','ANET','MU','VRT','JPM','KO','XOM','O','MO','GOOGL','META','TSLA','PLTR','CRM','COST','WMT','PG','JNJ','PEP','ABBV','AGNC','F','DEC','NFE','VATE']
    manifest_path=OUT/'acquisition.json'
    if manifest_path.exists():raise RuntimeError('Existing acquisition evidence; refuse duplicate requests')
    now=datetime.now(ZoneInfo('America/New_York'));completed=now.date() if now.hour>=17 else now.date()-timedelta(days=1)
    while completed.weekday()>=5:completed-=timedelta(days=1)
    end=(completed+timedelta(days=1)).isoformat()
    manifest={'started_at_utc':datetime.now(timezone.utc).isoformat(),'end_exclusive':end,'completed_session_cutoff':completed.isoformat(),'yfinance_version':yf.__version__,'sample':SAMPLE,'requests':[],'tickers':{},'status':'running','production_writes':0}
    def save():write_text_atomic(manifest_path,json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    class RateWatch(logging.Handler):
     def __init__(self):super().__init__();self.signal=None
     def emit(self,record):
      text=record.getMessage()
      if any(s in text.lower() for s in ('too many requests','rate limit','ratelimit','http 429','response [429]')):self.signal=text
    watch=RateWatch();logging.getLogger('yfinance').addHandler(watch)
    class Options:
     def __init__(self,stock,adjust):self.stock=stock;self.adjust=adjust
     def history(self,**kwargs):return self.stock.history(**kwargs,auto_adjust=self.adjust)
    with recovery.readonly(ROOT/'data/osakedata.db') as c:
     first={t:c.execute('select min(pvm) from osakedata where osake=? and market=?',(t,'usa')).fetchone()[0] for t in SAMPLE}
    g=json.loads((ROOT/'data/fundamentals_active_generation.json').read_text());base=ROOT/'data/fundamentals_generations'/g['generation_id']
    with recovery.readonly(base/g['roles']['canonical']) as c,recovery.readonly(base/g['roles']['provider']) as p:
     identity={t:{'securities':[dict(r) for r in c.execute('select security_id,company_id,current_ticker,exchange,valid_from,valid_to,active from security where current_ticker=?',(t,))],
      'aliases':[dict(r) for r in c.execute('select ticker,valid_from,valid_to,provider,source from ticker_alias where security_id in(select security_id from security where current_ticker=?)',(t,))],
      'provider_stocks':[dict(r) for r in p.execute("select ticker,permaticker,name,category,exchange,isdelisted,relatedtickers,firstpricedate,lastpricedate from sharadar_ticker_metadata where table_name='stocks' and ticker=?",(t,))]} for t in SAMPLE}
    (OUT/'local_identity.json').write_text(json.dumps({'generation':g['generation_id'],'tickers':identity},indent=2)+'\n')
    # No unverified predecessor prices are used as Vertiv operating-company observations.
    starts={'NFE':'2019-01-31','PLTR':'2020-09-30','VRT':'2020-02-10','DEC':'2021-01-04'}
    save()
    try:
     with recovery.stock_update_operation_lock(ROOT/'data/osakedata.db'):
      for ti,t in enumerate(SAMPLE,1):
       stock=yf.Ticker(t);frames=[];start=starts.get(t,'2018-01-01')
       info={'fetch_start':start,'file':f'{t}_false.csv.gz','rows':0};manifest['tickers'][t]=info
       ranges=update.split_fetch_date_range(start_date=start,end_date_exclusive=end)
       for wi,window in enumerate(ranges,1):
        request={'ticker':t,'auto_adjust':False,'start':window.start_date,'end_exclusive':window.end_date_exclusive,'started_at_utc':datetime.now(timezone.utc).isoformat()}
        manifest['requests'].append(request);save()
        try:
         fetched=update.fetch_history_for_date_ranges(stock=Options(stock,False),ticker=t,date_ranges=[window])
         if watch.signal:raise RuntimeError('RATE_LIMIT_SIGNAL: '+watch.signal)
         for frame in fetched.histories:
          if frame is not None and not frame.empty:frames.append(frame)
         request['status']='returned';request['rows']=sum(len(f) for f in fetched.histories if f is not None)
         if frames:
          data=pd.concat(frames);data.index=pd.Index([d.strftime('%Y-%m-%d') for d in data.index],name='date')
          if data.index.duplicated().any():raise RuntimeError('DUPLICATE_PROVIDER_DATES')
          data.to_csv(OUT/info['file'],compression='gzip',float_format='%.17g');info['rows']=len(data)
         save();print(f'{ti}/30 {t} {wi}/{len(ranges)} rows={info["rows"]}',flush=True)
        except Exception as exc:
         request.update(status='error',error=type(exc).__name__+': '+str(exc));save();raise
        finally:
         # Reuse existing pauses between bounded work units; no faster batch transport.
         update.sleep_after_legacy_stock_ticker(0)
       metadata=stock.history_metadata or {}
       info['provider_identity']={k:metadata.get(k) for k in ('symbol','instrumentType','exchangeTimezoneName','firstTradeDate','currency','exchangeName','longName')}
       if metadata.get('symbol')!=t or metadata.get('instrumentType')!='EQUITY' or metadata.get('exchangeTimezoneName')!='America/New_York':
        info['identity_hold']='UNEXPECTED_YAHOO_IDENTITY'
       save();update.sleep_legacy_stock_batch(ti)
      manifest['status']='false_history_complete';save()
    except BaseException as exc:
     manifest.update(status='stopped',error=type(exc).__name__+': '+str(exc));save();raise
    finally:logging.getLogger('yfinance').removeHandler(watch)
    print('FALSE ACQUISITION COMPLETE',manifest_path,flush=True)


if __name__ == "__main__":
    main()
