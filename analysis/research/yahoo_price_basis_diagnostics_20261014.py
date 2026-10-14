"""Offline split-boundary and floating-point candle diagnostics; no provider/DB calls."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from analysis import candlestick_patterns as candle
from analysis.research.yahoo_price_basis_comparison_20261014 import OHLC, PRIMARY_START, reconstruct, valid_rows


def main():
    out=Path(__file__).resolve().parents[2]/'outputs/yahoo_price_basis_comparison_20261014'
    acquisition=json.loads((out/'acquisition.json').read_text())
    cases=[];splits=[]
    functions={'Hammer':candle.is_hammer,'DragonflyDoji':candle.is_dragonfly_doji,
               'ShootingStar':candle.is_shooting_star,'HangingMan':candle.is_hanging_man}
    for ticker in acquisition['sample']:
        frame=pd.read_csv(out/acquisition['tickers'][ticker]['file'],index_col='date',float_precision='round_trip')
        adjusted,_=reconstruct(frame)
        eligible=valid_rows(frame)&valid_rows(adjusted)&pd.Series(frame.index>=PRIMARY_START.get(ticker,'2018-01-01'),index=frame.index)
        for day in frame.index[eligible]:
            ordinary,transformed=frame.loc[day],adjusted.loc[day]
            for name,fn in functions.items():
                if bool(fn(ordinary))!=bool(fn(transformed)):
                    a=(ordinary[OHLC]/ordinary.Close).to_numpy(float)
                    b=(transformed[OHLC]/transformed.Close).to_numpy(float)
                    cases.append({'ticker':ticker,'date':day,'pattern':name,
                                  'max_normalized_price_delta':float(np.max(np.abs(a-b))),
                                  'equal_normalized_at_12dp':bool(np.array_equal(a.round(12),b.round(12)))})
        for i in range(1,len(frame)):
            current,previous=frame.iloc[i],frame.iloc[i-1]
            if current.get('Stock Splits',0):
                splits.append({'ticker':ticker,'date':frame.index[i],'split':current['Stock Splits'],
                    'prev_close_false':previous.Close,'close_false':current.Close,
                    'ordinary_return':current.Close/previous.Close-1,
                    'prev_adj_close':previous['Adj Close'],'adj_close':current['Adj Close'],
                    'adjusted_return':current['Adj Close']/previous['Adj Close']-1 if previous['Adj Close'] else None})
    pd.DataFrame(cases).to_csv(out/'single_candle_numerical_sensitivity.csv',index=False)
    pd.DataFrame(splits).to_csv(out/'split_boundary_diagnostics.csv',index=False)
    print('Offline diagnostics:',len(cases),'single-candle flips;',len(splits),'split boundaries')


if __name__=='__main__':
    main()
