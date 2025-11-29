# results_data kenttien laskentaspeksit (versio 1)

Tämä dokumentti kokoaa results_generatorin (analysis/results_generator.py) laskemat kentät ja niiden kaavat / lähdelogiikan. Kaavat on kuvattu konseptitasolla – kaikki laskenta tapahtuu t0-päivään ankkuroituna (idx = t0 rivin indeksi stock_df:ssä). Normalisoinnit tehdään t0_close-arvoon, ellei toisin mainita.

## Perusmetatiedot
- `ticker`, `date`, `market`: siirtyvät suoraan findingsista/osakedata-indeksistä.
- `candle_pattern`: numeromappi PATTERN_MAPPING: Hammer=1, Bullish Engulfing=2, Piercing Pattern=3, Three White Soldiers=4, Morning Star=5, Dragonfly Doji=6, Bullish Divergence=7, Bearish Divergence=8, downtrend=0.
- `signal_strength`: findingsin signal_strength, float.
- `weekday`: `pd.Timestamp(date).weekday()` (0=maanantai).

## Kynttilädetaljit (t-1, t0, t1)
- Jokaisella aikaleimalla lasketaan:
  - alin/ylin: `(low|high) / norm * 100`, missä norm = t0_low historiassa (t-1) ja t0_close t0/t1:lle
  - bodi-%: `abs(close - open) / (high - low) * 100` (0 jos range=0)
  - bodi_colour: 1 jos `close > open`, muuten 0.
- Kentät: `t_1_alin`, `t_1_ylin`, `t_1_bodi`, `t_1_bodi_colour`, vastaavasti `t0_*`, `t1_*`.
- Johdettu lisäkenttä: `t0_alinMiinusClose = t0_alin - 100` eli `(low_t0 - close_t0) / close_t0 * 100` (yleensä ≤ 0).

## Hintapolku (t-2…t-20, normalisoitu t0_low:iin)
- `t_2`, `t_5`, `t_10`, `t_15`, `t_20`: `close(t-2|5|10|15|20) / t0_low * 100`.
- `t2`, `t5`, `t10`, `t20`: absoluuttiset hinnat (ei normalisoituja).
- Hajonnat: `t_2_hajonta`, … `t_20_hajonta` = `pstdev(normalized closes over window)` (historiaan taaksepäin, normalisoitu t0_low:iin).

## Volyymit
- `t_2_volyymi`, `t_5_volyymi`, `t_10_volyymi`, `t_15_volyymi`, `t_20_volyymi`: keskiarvo volyymeista ikkunassa t-2…t-20 (taaksepäin).
- `t0_volyymi`: t0 volume.
- `t2_volyymi`, `t5_volyymi`, `t10_volyymi`, `t20_volyymi`: tulevaisuuden volyymit t+2, t+5, t+10, t+20 (jos saatavilla).
- `Volume_impulse`: (keskiarvo volyymeista t-5…t-1) / (keskiarvo volyymeista t-105…t-6) * 100.

## Liukuvat keskiarvot (hinta)
- `t_2_5p_liukuva`, `t_2_10p_liukuva`, `t_2_20p_liukuva`: MA5/MA10/MA20 päättyen t-2, normalisoitu t0_low:lla. Vastaavat t-5, t-10, t-15, t-20 (sama kaava).
- `t0_50p_liukuva`, `t0_200p_liukuva`: MA50/MA200 päättyen t0, normalisoitu t0_low:lla.
- `t0_20p_liukuva`: MA20 päättyen t0, normalisoitu t0_low:lla.
- `t0_close_norm`: 100.0 (t0/t0_close).

## Indeksisarjat (SPX ja NDX)
- Normalisoidaan t0 indeksin closeen:
  - `SPX_0` … `SPX_20` ja `SPX2`, `SPX5`, `SPX10`, `SPX15`, `SPX20` (tulevat päivät jos olemassa).
  - Vastaavat NDX-kentät.
- `SPX_volatility_10`, `NDX_volatility_10`: pstdev indeksin normalisoiduista arvoista t-10…t-1.

## RSI ja divergence
- `RSI14_t0`: RSI(14) t0:lle (osakedata closeista).
- `bearish_divergence`, `bullish_divergence`: sama päivän strengthit (analysis_findings tai divergence_data fallback).
- `BullDiv_strength`: t0 Bullish Divergence signal_strength (jos pattern 7).
- `BullDiv_recent_strength`: maksimi bullish_strength 3 päivän sisällä (t0, t-1, t-2, t-3) kun löytyy divergence_records.
- `BullDiv_recent_offset`: offset (0=today,1=昨日,…) jolta BullDiv_recent_strength tuli, muutoin 99.
- `Has_BullDiv_recent`: 1 jos BullDiv_recent_strength > 0 muutoin 0.
- `RSI_slope_5`: `RSI14_t0 - RSI14_t-5`.

## Hintaslopet ja volatiliteetti
- `Price_slope_5`: `(100 - t_5) / 5` (historia normalisoitu t0_low:lla).
- `Price_slope_10`: `(100 - t_10) / 10`.
- `Price_acceleration_5_10`: `(Price_slope_5 - Price_slope_10)`.
- `Volatility_ratio_10_20`: (pstdev t-10…t-1) / (pstdev t-20…t-1) * 100, molemmat t0_low-normalisoituja.
- `Gap_down_strength`: `(open_t0 - close_t-1) / t0_low * 100` (negatiivinen gap -> positiivinen arvo, muu 0).
- `Body_ratio`: `abs(close - open) / (high - low)` (0 jos range=0).
- `Shadow_ratio`: `((high - max(open, close)) + (min(open, close) - low)) / (high - low)` (0 jos range=0).
- `t0_50p_slope`, `t0_200p_slope`: ((MA(period, t0) - MA(period, t-5)) / 5) / t0_low * 100.
- `trend_regime_5_20`, `trend_regime_20_50`, `trend_regime_50_200`: 1 jos lyhyt MA > pitkä MA, muuten 0.
- `ATR_14`: Average True Range 14 päivää (t-13…t0, tarvitsee >=10 validia).
- `ATR_ratio_14`: ATR_14 / t0_low * 100.
- `MACD_line`, `MACD_signal`, `MACD_hist`: MACD(12,26,9) closeista (hist=line-signal).
- Pivotit:
  - `pivot_low_strength_3/5`: `(min(low window) - low_t0) / low_t0 * 100` positiivinen jos t0 on local low.
  - `pivot_high_strength_3/5`: `(high_t0 - max(high window)) / high_t0 * 100` (local high).
- `VIX_10`: VIX-normalisoitu: (VIX_t0 / VIX_t-10) * 100.
- `VIX_norm_10`: pstdev VIX arvoista t-10…t-1 (normalisoituna t0:aan).

## Tuottojen normalisointi
- `t0_close_norm`: perus 100 (t0_close-pohjainen).
- Tulevaisuuden tuottojen normalisoidut kentät: `t2`, `t5`, `t10`, `t20` = (close_{t+offset} / t0_close) * 100.
- Historiatuotot (`t_2`, `t_5`, `t_10`, `t_15`, `t_20`) ovat t0_low-normalisoituja.

## Divergenssien perusfeaturet (BULL_DIV_GENERAL_FEATURES)
- `bullDiv_offset`: päivien määrä edellisestä Bullish Divergence -patternista (99 jos ei löytynyt viimeiseen 100 päivään).
- `bullDiv_last_1d`, `bullDiv_last_2d`, `bullDiv_last_3d`, `bullDiv_last_3d_any`: binäärilippuja onko divergointi t0/t-1/t-2/t-3.

## Kynttilä + BullDiv kombofeaturet (COMBO_FEATURE_COLUMNS, 30 kpl)
- Jokaiselle kuviolle (Hammer, Bullish Engulfing, Piercing Pattern, Three White Soldiers, Morning Star, Dragonfly Doji) ja BullDiv-läsnäololle binary-liput:
  - `is_<slug>_only_t0`
  - `is_<slug>_and_BullDiv_t0`
  - `is_<slug>_and_BullDiv_recent_2d/3d/5d`
- Kaikki integer 0/1.

## Same-day aggregaatit
- Lasketaan kaikista findingseista samalla ticker+date:
  - `signal_count_same_day`: rivien määrä.
  - `unique_patterns_same_day`: uniikkien pattern-koodien määrä (pois lukien 0).
  - `max_strength_same_day`, `second_best_strength_same_day`, `sum_strength_same_day`: signal_strength -aggregaatit.
  - `signal_combo_code`: 0 = ei kynttilää/ei divergenssiä, 1 = 1 kynttilä, 2 = >=2 kynttilää, 3 = kynttilä + divergenssi, 4 = pelkkä divergenssi.
  - `num_candles_same_day`: kynttilöiden lukumäärä (koodit 1–6).
  - `has_multi_candle_combo`: 1 jos num_candles >= 2.
  - `has_bullish_divergence_same_day`: 1 jos pattern 7 mukana.
  - `has_same_day_reversal_cluster`: 1 jos has_multi tai (is_candle_day ja divergenssi).
  - `is_candle_day`: 1 jos num_candles > 0.

## Blackout-liput (earnings/dividend)
- `has_blackout_data`: 1 jos tickerillä blackout-data saatavilla.
- `is_earnings_t0`, `is_dividend_t0`: 1 jos tapahtuma t0.
- `is_earnings_window`, `is_dividend_window`: 1 jos tapahtuma +-3pv ikkunassa.
- `is_blackout_t0`, `is_blackout_window`: yhdistelmäikkuna tapahtumille.
- `exclude_from_regression`: 1 jos blackout_window ja tapahtuma löydetty.

## Sektori
- `sector`: tekstikenttä (jos sektoridata saatavilla; muuten None).
- `sector_momentum_5`: `(sector_close_t0 / sector_close_t-5 - 1) * 100`.
- `sector_momentum_20`: vastaavasti 20 päivän liike.
- `sector_volatility_20`: pstdev sektorin päivätuotoista t-20…t-1.

## Mallin laatuvarmistukset
- results_generator tarkistaa taulusarakkeet parity-tyyppisesti DatabaseManager.ensure_results_schema:n kautta, mutta 100 % tarkkuuden validointi tulee tehdä kultaisella datalla ja oracle-laskennalla (suunnitelma kuvattu erikseen).

Huomio: results_data-taulussa on enemmän kenttiä kuin varsinaiset 84 laskentakenttää; yllä on listattu kaikki create table -mukaiset arvot sekä BULL_DIV_GENERAL_FEATURES ja COMBO_FEATURE_COLUMNS. Tämä dokumentti toimii version 1 spesifikaationa jatkovarmennusta varten.
