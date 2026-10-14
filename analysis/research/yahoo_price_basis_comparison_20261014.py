"""Research-only price-basis comparison. No acquisition, SQLite access or production writes."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
from analysis import candlestick_patterns as candle
from analysis import chart_patterns as chart
from analysis.divergence_v1 import compute_rsi_wilder
from analysis.stock_dow_structure import PriceBar, calculate_ticker_events

OHLC = ['Open', 'High', 'Low', 'Close']
PRIMARY_START = {'DEC': '2023-12-18', 'VRT': '2020-02-10'}
# DEC legal domestication is not assumed to preserve security identity/warm-up.
IDENTITY_BREAKS = {'DEC': ['2025-11-24']}
# Both Yahoo bases show a 1:50 unit discontinuity: never calculate across it.
QUALITY_BREAKS = {'NFE': ['2026-09-14']}


def reconstruct(frame):
    result = frame.copy()
    factor = frame['Adj Close'] / frame['Close']
    for key in OHLC[:3]:
        result[key] = frame[key] * factor
    result['Close'] = frame['Adj Close']
    return result, factor


def yahoo_keepna_mask(frame):
    keys = [k for k in OHLC + ['Adj Close', 'Volume', 'Dividends', 'Stock Splits', 'Capital Gains'] if k in frame]
    return ~(frame[keys].isna() | frame[keys].eq(0)).all(axis=1)


def valid_rows(frame):
    a = frame[OHLC + ['Volume']]
    finite = np.isfinite(a).all(axis=1)
    scale = frame[OHLC].abs().max(axis=1).clip(lower=1.)
    eps = 1e-12 * scale  # Only arithmetic round-off in reconstructed extrema.
    return (finite & frame[OHLC].gt(0).all(axis=1) & frame['Volume'].ge(0)
            & frame['Low'].le(frame[['Open', 'Close']].min(axis=1) + eps)
            & frame['High'].ge(frame[['Open', 'Close']].max(axis=1) - eps)
            & frame['Low'].le(frame['High'] + eps))


def ema_sma_seed(values, n):
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        out[n-1] = np.mean(values[:n])
        alpha = 2. / (n+1)
        for i in range(n, len(values)):
            out[i] = alpha * values[i] + (1-alpha) * out[i-1]
    return out


def wilder(values, n):
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        out[n-1] = np.mean(values[:n])
        for i in range(n, len(values)):
            out[i] = ((n-1)*out[i-1]+values[i])/n
    return out


def features(frame):
    """One uninterrupted qualified segment; identical seeds/windows for both bases."""
    out = pd.DataFrame(index=frame.index)
    close = frame['Close']
    for n in (10,20):
        out[f'EMA{n}'] = ema_sma_seed(close.to_numpy(), n)
    for n in (50,200):
        out[f'SMA{n}'] = close.rolling(n, min_periods=n).mean()
    out['RSI14'] = compute_rsi_wilder(close.tolist(), period=14)
    out['DailyReturn'] = close.pct_change(fill_method=None)
    out['Gap'] = frame['Open']/close.shift(1)-1
    for n in (20,60):
        out[f'High{n}'] = frame['High'].shift(1).rolling(n,min_periods=n).max()
        out[f'Low{n}'] = frame['Low'].shift(1).rolling(n,min_periods=n).min()
    tr = pd.concat([frame['High']-frame['Low'],(frame['High']-close.shift(1)).abs(),
                    (frame['Low']-close.shift(1)).abs()],axis=1).max(axis=1)
    out['ATR14'] = wilder(tr.to_numpy(),14)  # Transparent research-only Wilder ATR.
    out['Close'] = close
    return out


def numeric_metrics(a,b):
    mask = np.isfinite(a) & np.isfinite(b)
    aa,bb = np.asarray(a)[mask],np.asarray(b)[mask]
    if not len(aa):
        return {'n':0,'different':0,'max_abs':None,'median_abs':None,'max_rel':None,'median_rel':None}
    delta = np.abs(bb-aa)
    rel = delta[np.abs(aa)>1e-12]/np.abs(aa[np.abs(aa)>1e-12])
    return {'n':len(aa),'different':int((~np.isclose(aa,bb,rtol=1e-8,atol=1e-8)).sum()),
            'max_abs':float(delta.max()),'median_abs':float(np.median(delta)),
            'max_rel':float(rel.max()) if len(rel) else None,'median_rel':float(np.median(rel)) if len(rel) else None}


def signs(a,b):
    delta = a-b
    eps = 1e-10*np.maximum(np.maximum(np.abs(a),np.abs(b)),1.)
    return np.where(delta>eps,1,np.where(delta < -eps,-1,0))


def classifications(f):
    out = pd.DataFrame(index=f.index)
    for name in ('EMA10','EMA20','SMA50','SMA200','High20','High60','Low20','Low60'):
        out[name] = pd.Series(signs(f['Close'],f[name]),index=f.index).where(f[name].notna())
    out['EMA10_vs_EMA20'] = pd.Series(signs(f.EMA10,f.EMA20),index=f.index).where(f.EMA20.notna())
    for cutoff in (30,50,70):
        out[f'RSI14_{cutoff}'] = pd.Series(signs(f.RSI14,cutoff),index=f.index).where(f.RSI14.notna())
    for feature,cutoff,name in [('DailyReturn',0,'ReturnSign'),('Gap',0,'GapSign'),('Gap',.02,'GapAbove2pct')]:
        out[name] = pd.Series(signs(f[feature],cutoff),index=f.index).where(f[feature].notna())
    out['ATR14_5pct'] = pd.Series(signs(f.ATR14/f.Close,.05),index=f.index).where(f.ATR14.notna())
    return out


def classification_coordinate(f, name):
    if name in ('EMA10','EMA20','SMA50','SMA200','High20','High60','Low20','Low60'):
        return f.Close/f[name]-1
    if name == 'EMA10_vs_EMA20':
        return f.EMA10/f.EMA20-1
    if name.startswith('RSI14_'):
        return f.RSI14
    if name == 'ReturnSign':
        return f.DailyReturn
    if name.startswith('Gap'):
        return f.Gap
    return f.ATR14/f.Close


def pattern_flags(frame):
    unary = {'Hammer':candle.is_hammer,'DragonflyDoji':candle.is_dragonfly_doji,
             'ShootingStar':candle.is_shooting_star,'HangingMan':candle.is_hanging_man}
    binary = {'BullishEngulfing':candle.is_bullish_engulfing,'BearishEngulfing':candle.is_bearish_engulfing,
              'Piercing':candle.is_piercing_pattern,'DarkCloud':candle.is_dark_cloud_cover}
    multi = {'MorningStar':(candle.is_morning_star,2),'EveningStar':(candle.is_evening_star,2),
             'BullishFlag':(chart.is_bullish_flag,5),'BearishFlag':(chart.is_bearish_flag,5),
             'CupHandle':(chart.is_cup_and_handle,204)}
    out = pd.DataFrame(index=frame.index)
    for name,fn in unary.items():out[name] = [int(fn(row)) for _,row in frame.iterrows()]
    for name,fn in binary.items():out[name] = [np.nan]+[int(fn(frame.iloc[i-1],frame.iloc[i])) for i in range(1,len(frame))]
    for name,(fn,warmup) in multi.items():out[name] = [np.nan if i<warmup else int(fn(frame,i)) for i in range(len(frame))]
    return out


def dow_events(ticker,frame):
    bars = [PriceBar(ticker,'usa',str(day),float(r.Open),float(r.High),float(r.Low),float(r.Close),int(r.Volume)) for day,r in frame.iterrows()]
    if not bars:return []
    return calculate_ticker_events(bars,pivot_radius=3,start_confirmed_as_of_date=bars[0].date,
                                  initial_state=None,run_id='research-only',created_at_utc='2026-10-14T00:00:00Z')


def dow_compare(a,b):
    fields = ('event_type','event_date','confirmed_as_of_date','dow_label_high','dow_label_low','trend_state','reset_reason')
    ca,cb = (Counter(tuple(r.get(k) for k in fields) for r in events) for events in (a,b))
    piv = lambda events:{(r['event_type'],r['event_date'],r['confirmed_as_of_date']):r for r in events if r['event_type'] in ('PIVOT_HIGH','PIVOT_LOW')}
    pa,pb = piv(a),piv(b);common = pa.keys()&pb.keys()
    mismatch = sum(any(pa[k][f]!=pb[k][f] for f in ('dow_label_high','dow_label_low')) for k in common)
    return {'false_events':len(a),'true_events':len(b),'false_only_classified_events':sum((ca-cb).values()),
            'true_only_classified_events':sum((cb-ca).values()),'false_pivots':len(pa),'true_pivots':len(pb),
            'common_pivots':len(common),'pivot_label_mismatches':mismatch,
            'false_only_pivot_dates':len(pa.keys()-pb.keys()),'true_only_pivot_dates':len(pb.keys()-pa.keys())}


def contiguous_segments(frame,mask,ticker):
    active=[]
    for i,day in enumerate(frame.index):
        if day in IDENTITY_BREAKS.get(ticker,[]) + QUALITY_BREAKS.get(ticker,[]) and active:
            yield active;active=[]
        if bool(mask.iloc[i]):active.append(day)
        elif active:yield active;active=[]
    if active:yield active


def run(out):
    acquisition=json.loads((out/'acquisition.json').read_text())
    if acquisition['status']!='false_history_complete':raise RuntimeError('Incomplete acquisition')
    coverage=[];nums=[];classes=[];patterns=[];dows=[];event_groups=[];examples=[];action_rows=[]
    for ticker in acquisition['sample']:
        info=acquisition['tickers'][ticker]
        false=pd.read_csv(out/info['file'],index_col='date',float_precision='round_trip').sort_index()
        true,factor=reconstruct(false)
        # Adj Close is not a surviving column in actual auto_adjust=True results.
        true=true.drop(columns=['Adj Close'])
        identity=pd.Series(false.index>=PRIMARY_START.get(ticker,'2018-01-01'),index=false.index)
        if info.get('identity_hold'):identity[:]=False
        keep=yahoo_keepna_mask(true)
        good_false,good_true=valid_rows(false),valid_rows(true)
        paired=identity & keep & good_false & good_true
        f_features=[];t_features=[];f_classes=[];t_classes=[];f_pat=[];t_pat=[];fe=[];te=[]
        for days in contiguous_segments(false,paired,ticker):
            ff,tf=false.loc[days],true.loc[days]
            fx,tx=features(ff),features(tf)
            f_features.append(fx);t_features.append(tx)
            f_classes.append(classifications(fx));t_classes.append(classifications(tx))
            f_pat.append(pattern_flags(ff));t_pat.append(pattern_flags(tf))
            fe.extend(dow_events(ticker,ff));te.extend(dow_events(ticker,tf))
        if not f_features:raise RuntimeError(f'No qualified observations: {ticker}')
        fa,ta=pd.concat(f_features),pd.concat(t_features)
        fc,tc=pd.concat(f_classes),pd.concat(t_classes)
        fp,tp=pd.concat(f_pat),pd.concat(t_pat)
        coverage.append({'ticker':ticker,'first':false.index[0],'last':false.index[-1],'false_rows':len(false),
            'identity_excluded':int((~identity).sum()),'true_keepna_dropped':int((~keep).sum()),
            'invalid_false':int((~good_false).sum()),'invalid_true':int((~good_true).sum()),'paired_qualified':int(paired.sum()),
            'close_zero':int(false.Close.eq(0).sum()),'close_negative':int(false.Close.lt(0).sum()),
            'denominator_missing':int(false.Close.isna().sum()),'factor_missing_nonfinite':int((~np.isfinite(factor)).sum()),
            'factor_zero':int(factor.eq(0).sum()),'factor_negative':int(factor.lt(0).sum()),
            'factor_min':float(factor.min()),'factor_max':float(factor.max()),
            'identity_breaks':len(IDENTITY_BREAKS.get(ticker,[])),
            'quality_breaks':len(QUALITY_BREAKS.get(ticker,[])),
            'dividend_events':int(false.get('Dividends',pd.Series(0,index=false.index)).ne(0).sum()),
            'split_events':int(false.get('Stock Splits',pd.Series(0,index=false.index)).ne(0).sum())})
        for k in OHLC:nums.append({'ticker':ticker,'feature':k,**numeric_metrics(false.loc[paired,k],true.loc[paired,k])})
        for k in fa:
            if k != 'Close':
                nums.append({'ticker':ticker,'feature':k,**numeric_metrics(fa[k],ta[k])})
        for k in fc:
            ok=fc[k].notna()&tc[k].notna();a,b=fc.loc[ok,k],tc.loc[ok,k]
            # Crossings require consecutive qualified rows in original provider index.
            original_positions=pd.Series(np.arange(len(false)),index=false.index).loc[a.index]
            consecutive=original_positions.diff().eq(1)
            ea=(a!=a.shift())&a.shift().notna()&consecutive
            eb=(b!=b.shift())&b.shift().notna()&consecutive
            shift=(classification_coordinate(ta,k)-classification_coordinate(fa,k)).abs().loc[a.index]
            material=0.01 if k.startswith('RSI14_') else 1e-4
            classes.append({'ticker':ticker,'feature':k,'n':int(ok.sum()),'classification_differences':int((a!=b).sum()),
                'false_crossing_dates':int(ea.sum()),'true_crossing_dates':int(eb.sum()),'crossing_date_differences':int((ea!=eb).sum()),
                'material_shift_classification_differences':int(((a!=b)&shift.ge(material)).sum()),
                'material_shift_threshold':material,'max_coordinate_shift':float(shift.max()) if len(shift) else None})
        for k in fp:
            ok=fp[k].notna()&tp[k].notna()
            patterns.append({'ticker':ticker,'pattern':k,'n':int(ok.sum()),'false_signals':int(fp.loc[ok,k].sum()),
                             'true_signals':int(tp.loc[ok,k].sum()),'signal_date_differences':int((fp.loc[ok,k]!=tp.loc[ok,k]).sum())})
        dows.append({'ticker':ticker,**dow_compare(fe,te)})
        dividends=false.get('Dividends',pd.Series(0,index=false.index)).ne(0)
        splits=false.get('Stock Splits',pd.Series(0,index=false.index)).ne(0)
        since=pd.Series(np.nan,index=false.index);last=None
        for i,day in enumerate(false.index):
            if dividends.iloc[i]:last=i
            if last is not None:since.iloc[i]=i-last
            if dividends.iloc[i] or splits.iloc[i]:
                action_rows.append({'ticker':ticker,'date':day,'dividend':float(false.loc[day].get('Dividends',0)),
                    'split':float(false.loc[day].get('Stock Splits',0)),'factor':float(factor.loc[day]),
                    'close_false':float(false.loc[day,'Close']),'close_true':float(true.loc[day,'Close']),
                    'qualified':bool(paired.loc[day])})
        buckets={'ex_date':since.eq(0),'1_4_after':since.between(1,4),'5_19_after':since.between(5,19),
                 '20_59_after':since.between(20,59),'60plus_after':since.ge(60),'no_previous_dividend':since.isna()}
        for name,mask in buckets.items():
            ids=fa.index.intersection(false.index[mask])
            for k in ('DailyReturn','Gap','RSI14','EMA20','SMA50','ATR14'):
                event_groups.append({'ticker':ticker,'bucket':name,'feature':k,**numeric_metrics(fa.loc[ids,k],ta.loc[ids,k])})
        near_split=pd.Series(False,index=false.index)
        for i in np.flatnonzero(splits.to_numpy()):near_split.iloc[max(0,i-3):i+4]=True
        ids=fa.index.intersection(false.index[near_split])
        for k in ('DailyReturn','Gap','RSI14','EMA20','ATR14'):
            event_groups.append({'ticker':ticker,'bucket':'split_plus_minus3','feature':k,**numeric_metrics(fa.loc[ids,k],ta.loc[ids,k])})
        for k in ('GapAbove2pct','EMA20','High20','RSI14_30'):
            dates=fc.index[(fc[k].notna()&tc[k].notna()&fc[k].ne(tc[k]))]
            for day in dates[:3]:
                examples.append({'ticker':ticker,'date':day,'feature':k,'class_false':int(fc.loc[day,k]),'class_true':int(tc.loc[day,k]),
                    'close_false':float(false.loc[day,'Close']),'close_true':float(true.loc[day,'Close']),
                    'dividend':float(false.loc[day].get('Dividends',0)),'split':float(false.loc[day].get('Stock Splits',0))})
        print('Analyzed',ticker,len(false),int(paired.sum()),flush=True)
    tables={'coverage':coverage,'numeric_metrics':nums,'classifications':classes,'patterns':patterns,'dow':dows,
            'event_window_metrics':event_groups,'action_events':action_rows,'classification_examples':examples}
    for name,rows in tables.items():pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    totals={'sample_size':len(coverage),'false_rows':sum(r['false_rows'] for r in coverage),
            'qualified_rows':sum(r['paired_qualified'] for r in coverage),'invalid_false':sum(r['invalid_false'] for r in coverage),
            'invalid_true':sum(r['invalid_true'] for r in coverage),'true_keepna_dropped':sum(r['true_keepna_dropped'] for r in coverage),
            'identity_excluded':sum(r['identity_excluded'] for r in coverage)}
    (out/'analysis_summary.json').write_text(json.dumps(totals,indent=2)+'\n')
    return tables,totals


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
