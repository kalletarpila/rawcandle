import numpy as np
import pandas as pd
from yfinance import utils
from analysis.research import yahoo_price_basis_comparison_20261014 as research


def frame(n=230,factor=.8):
    close=np.arange(n,dtype=float)+100
    return pd.DataFrame({'Open':close-.5,'High':close+1,'Low':close-1,'Close':close,
        'Adj Close':close*factor,'Volume':1000,'Dividends':0.,'Stock Splits':0.},
        index=pd.date_range('2020-01-01',periods=n).strftime('%Y-%m-%d'))


def test_reconstruction_matches_installed_yfinance_on_same_vintage():
    f=frame();a,_=research.reconstruct(f);b=utils.auto_adjust(f)
    for k in research.OHLC:np.testing.assert_array_equal(a[k],b[k])
    np.testing.assert_array_equal(a.Volume,f.Volume)


def test_nonpositive_factor_is_reproducible_but_not_numerically_eligible():
    f=frame(3);f['Adj Close']=[0,-1,np.nan]
    adjusted,factor=research.reconstruct(f)
    assert factor.eq(0).sum()==1 and factor.lt(0).sum()==1
    assert not research.valid_rows(adjusted).any()


def test_zero_denominator_is_not_repaired_or_filled():
    f=frame(1);f['Close']=0
    adjusted,factor=research.reconstruct(f)
    assert np.isinf(factor.iloc[0]) and not research.valid_rows(adjusted).any()


def test_keepna_filter_retains_missingness_difference_explicitly():
    f=frame(2);f.loc[f.index[0],research.OHLC+['Volume','Dividends','Stock Splits']]=0
    assert research.yahoo_keepna_mask(f).tolist()==[True,True]  # Adj Close still positive.
    adjusted,_=research.reconstruct(f);adjusted=adjusted.drop(columns='Adj Close')
    adjusted.loc[adjusted.index[0],research.OHLC]=0
    assert research.yahoo_keepna_mask(adjusted).tolist()==[False,True]


def test_constant_positive_factor_scales_levels_but_not_relative_features_or_classes():
    f=frame();a,_=research.reconstruct(f);ff,aa=research.features(f),research.features(a)
    for k in ('EMA10','EMA20','SMA50','SMA200','High20','Low60','ATR14'):
        np.testing.assert_allclose(aa[k],ff[k]*.8,rtol=1e-12,atol=1e-12)
    for k in ('DailyReturn','Gap','RSI14'):
        np.testing.assert_allclose(aa[k],ff[k],rtol=1e-10,atol=1e-10)
    pd.testing.assert_frame_equal(research.classifications(ff),research.classifications(aa))


def test_factor_change_changes_gap_even_with_same_calendar_and_raw_prices():
    f=frame(30,1);f['Adj Close']=f.Close;f.loc[f.index[:15],'Adj Close']=f.Close.iloc[:15]*.9
    adjusted,_=research.reconstruct(f)
    raw_gap=research.features(f).Gap.iloc[15]
    adj_gap=research.features(adjusted).Gap.iloc[15]
    assert adj_gap>raw_gap+.1
    assert f.index.equals(adjusted.index)


def test_quality_gaps_are_not_compressed_and_reset_warmup():
    f=frame(30);mask=pd.Series(True,index=f.index);mask.iloc[15]=False
    segments=list(research.contiguous_segments(f,mask,'TEST'))
    assert len(segments)==2 and len(segments[0])==15 and len(segments[1])==14
    assert research.features(f.loc[segments[1]]).SMA50.isna().all()


def test_dow_classifications_invariant_to_constant_positive_scale():
    f=frame();f['Close']=100+10*np.sin(np.arange(len(f))/4)
    f['Open']=f.Close-.3;f['High']=f.Close+1;f['Low']=f.Close-1;f['Adj Close']=f.Close*.8
    a,_=research.reconstruct(f)
    stats=research.dow_compare(research.dow_events('TEST',f),research.dow_events('TEST',a))
    assert stats['false_pivots']>0
    assert stats['false_only_classified_events']==stats['true_only_classified_events']==0
    assert stats['pivot_label_mismatches']==0


def test_known_split_unit_discontinuity_does_not_enter_return_or_indicator_warmup():
    f=frame(30)
    f.index=pd.date_range('2026-08-25',periods=30).strftime('%Y-%m-%d')
    segments=list(research.contiguous_segments(f,pd.Series(True,index=f.index),'NFE'))
    assert len(segments)==2 and segments[1][0]=='2026-09-14'
    computed=research.features(f.loc[segments[1]])
    assert np.isnan(computed.DailyReturn.iloc[0])
    assert computed.SMA50.isna().all()
