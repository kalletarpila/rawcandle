"""Research-only bounded acquisition; explicit CLI use, no production writes."""
from pathlib import Path
from datetime import datetime,timezone
import logging,json
import numpy as np,pandas as pd,yfinance as yf
from yfinance import utils
from services import stock_update_service as update
from services import missing_day_recovery as recovery
from analysis.research.yahoo_price_basis_comparison_20261014 import reconstruct,yahoo_keepna_mask,OHLC

def main():
    ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/yahoo_price_basis_comparison_20261014'
    acq=json.loads((OUT/'acquisition.json').read_text())
    assert acq['status']=='false_history_complete'
    if (OUT/'equivalence.json').exists():raise RuntimeError('Validation exists; do not repeat calls')
    SAMPLES=[('NVDA','2024-06-03','2024-06-19'),('AMD','2023-09-01','2023-10-03'),
     ('AAPL','2024-08-01','2024-08-21'),('KO','2024-09-03','2024-10-03'),('O','2024-09-03','2024-10-03'),
     ('COST','2023-12-01','2024-01-11'),('F','2023-02-01','2023-03-02'),('WMT','2024-02-20','2024-03-06'),
     ('NFE','2022-12-20','2023-01-11'),('VATE','2020-05-01','2020-05-22'),('DEC','2023-06-28','2023-07-07')]
    result={'same_vintage_checks':[],'independent_samples':[],'requests':[],'status':'running'}
    def save():(OUT/'equivalence.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    class Watch(logging.Handler):
     signal=None
     def emit(self,r):
      s=r.getMessage()
      if any(k in s.lower() for k in ('rate limit','ratelimit','too many requests','http 429','response [429]')):self.signal=s
    watch=Watch();logging.getLogger('yfinance').addHandler(watch)
    class Options:
     def __init__(self,stock,adjust):self.stock=stock;self.adjust=adjust
     def history(self,**kwargs):return self.stock.history(**kwargs,auto_adjust=self.adjust)
    def get(stock,t,start,end,adjust):
     result['requests'].append({'ticker':t,'start':start,'end_exclusive':end,'auto_adjust':adjust,'at_utc':datetime.now(timezone.utc).isoformat()});save()
     try:
      f=update.fetch_history_for_date_ranges(stock=Options(stock,adjust),ticker=t,date_ranges=[update.StockUpdateDateRange(start,end)]).histories[0]
      if watch.signal:raise RuntimeError('RATE_LIMIT_SIGNAL: '+watch.signal)
      f=f.copy();f.index=pd.Index([d.strftime('%Y-%m-%d') for d in f.index],name='date');return f
     finally:update.sleep_after_legacy_stock_ticker(0)
    def measure(expected,actual):
     shared=expected.index.intersection(actual.index);a=expected.loc[shared,OHLC].to_numpy();b=actual.loc[shared,OHLC].to_numpy()
     finite=np.isfinite(a)&np.isfinite(b);delta=np.abs(a-b)
     denom=np.abs(a);rels=delta[finite&(denom>1e-12)]/denom[finite&(denom>1e-12)]
     strict=np.isclose(a,b,rtol=1e-10,atol=1e-10,equal_nan=True);practical=np.isclose(a,b,rtol=1e-6,atol=1e-6,equal_nan=True)
     aux={}
     for k in ('Volume','Dividends','Stock Splits'):
      aux[k]=int((expected.loc[shared,k].to_numpy()!=actual.loc[shared,k].to_numpy()).sum()) if k in expected and k in actual else None
     return {'common':len(shared),'expected_only':expected.index.difference(actual.index).tolist(),'actual_only':actual.index.difference(expected.index).tolist(),
       'strict_mismatch_rows':int((~strict).any(axis=1).sum()),'numerical_mismatch_rows_1ppm':int((~practical).any(axis=1).sum()),
       'max_abs':float(delta[finite].max()) if finite.any() else None,'max_rel':float(rels.max()) if len(rels) else None,'auxiliary_mismatches':aux}
    for t in acq['sample']:
     f=pd.read_csv(OUT/acq['tickers'][t]['file'],index_col='date',float_precision='round_trip')
     a,_=reconstruct(f);b=utils.auto_adjust(f)
     assert np.array_equal(a[OHLC].to_numpy(),b[OHLC].to_numpy(),equal_nan=True)
     result['same_vintage_checks'].append({'ticker':t,'rows':len(f),'exact_ohlc_equal':True})
    save();revision_checks=0
    try:
     with recovery.stock_update_operation_lock(ROOT/'data/osakedata.db'):
      for t,start,end in SAMPLES:
       f=pd.read_csv(OUT/acq['tickers'][t]['file'],index_col='date',float_precision='round_trip');f=f.loc[(f.index>=start)&(f.index<end)]
       expected,_=reconstruct(f);expected=expected.drop(columns='Adj Close');expected=expected.loc[yahoo_keepna_mask(expected)]
       stock=yf.Ticker(t);actual=get(stock,t,start,end,True)
       actual.to_csv(OUT/(t+'_true_validation.csv.gz'),compression='gzip',float_format='%.17g')
       stats={'ticker':t,'start':start,'end_exclusive':end,**measure(expected,actual)}
       if stats['strict_mismatch_rows'] and revision_checks<3:
        latest=get(stock,t,start,end,False);revision_checks+=1
        reconstructed,_=reconstruct(latest);reconstructed=reconstructed.drop(columns='Adj Close');reconstructed=reconstructed.loc[yahoo_keepna_mask(reconstructed)]
        stats['same_window_followup']=measure(reconstructed,actual)
        stats['false_ohlc_input_revisions']=measure(f,latest)
       shared=f.index.intersection(actual.index)
       old_adj=f.loc[shared,'Adj Close'].to_numpy();new_adj=actual.loc[shared,'Close'].to_numpy()
       stats['source_adj_close_response_difference']={'different_exact':int((old_adj!=new_adj).sum()),'max_abs':float(np.abs(old_adj-new_adj).max()) if len(shared) else None}
       stats['raw_false_rows']=len(f);stats['raw_false_only_dates']=f.index.difference(actual.index).tolist();stats['true_only_dates']=actual.index.difference(f.index).tolist()
       predicted=f.loc[shared].copy();predicted['Adj Close']=actual.loc[shared,'Close'];predicted,_=reconstruct(predicted)
       eq=np.isclose(predicted[OHLC],actual.loc[shared,OHLC],rtol=1e-10,atol=1e-10,equal_nan=True)
       stats['using_observed_true_close_as_adj_close_mismatch_rows']=int((~eq).any(axis=1).sum())
       result['independent_samples'].append(stats);save();print(t,json.dumps(stats),flush=True)
     result['status']='complete';save()
    finally:logging.getLogger('yfinance').removeHandler(watch)


if __name__ == "__main__":
    main()
