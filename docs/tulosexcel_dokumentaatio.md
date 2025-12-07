# Tulosexcelin tulkintaopas (RawCandle)

Tämä opas selittää, mitä kukin tulosexcelin (results_data-taulu -> Excel-vienti) sarake kuvaa, millä laskentasäännöillä arvot syntyvät ja miten kynttilä- ja divergenssisignaalit sekä laskutrendifiltterit toimivat. Tavoite on, että ulkopuolinen analyytikko voi tulkita Exceliä ilman koodiin kurkkaamista.

## 1. Rakenne ja normalisointi
- Jokainen rivi = yksittäinen ticker-päivä (*t0*), jolloin jokin kynttilä- tai divergenssipatterni täyttyy.
- Excelissä 99 saraketta: perusfeaturet (1–87) + uudet jatkoanalyysifeaturet (88–99, `compute_new_features.py`).
- Hintahistoria normalisoidaan t0:n hintaan:
  - Osakkeet: historia t-1 ja taaksepäin `t0_low = 100`; t0 ja tulevat `t0_close = 100`.
  - Indeksit (SPX/NDX): aina `t0_close = 100`.
- Volyymit raportoidaan prosenttina suhteessa viimeisen 100 pörssipäivän keskiarvoon ennen tarkasteltavaa jaksoa.
- Weekday on ISO-koodi 1=ma ... 7=su (`datetime.isoweekday`).

### 1.1 Exceliin viedyt sarakkeet (results/excel_exporter.py)
- Exceliin viedään **kaikki** results_data-sarakkeet id:tä lukuun ottamatta (ml. market, combo- ja same-day -liput, blackout-/sektori-/trendikentät, BullDiv-offsetit ja bearish_divergence).
- Otsikoissa käytetään samaa järjestystä kuin HEADERS-listassa; `kynttila` = candle_pattern-numero, `vahvuus` = signal_strength.

## 2. Kynttiläkuviot ja numerokoodit
| Koodi | Kuvio | Merkitys |
|-------|-------|----------|
|0|Downtrend|Täyttää laskutrendifiltterin (ks. luku 8), toimii myös placeholderina|
|1|Hammer|Pitkä alavarjo, pieni runko -> mahdollinen käänne|
|2|Bullish Engulfing|Nouseva kynttilä nielee edellisen laskupäivän rungon|
|3|Piercing Pattern|Avaa edellisen päätöksen alle, sulkee vähintään edellisen rungon puolivälin ylle|
|4|Three White Soldiers|Kolme peräkkäistä pitkää nousevaa kynttilää|
|5|Morning Star|Lasku -> pieni runko (tai doji) -> vahva nousupäivä|
|6|Dragonfly Doji|Doji, erittäin pieni runko, pitkä alavarjo|
|7|Bullish Divergence|Hinta tekee alemman pohjan, RSI tekee korkeamman|
|8|Bearish Divergence|Hinta tekee korkeamman huipun, RSI tekee matalamman (tallennetaan kantaan, ei viedä Exceliin)|

### 2.1 Kuviokohtaiset tunnistussäännöt (koodi-exakti)
- **Hammer (1)**: `body < 0.4 * (high-low)`, `lower_shadow > 2 * body`, `upper_shadow < body`.
- **Bullish Engulfing (2)**: Päivä t-1 laskeva, t0 nouseva. `open_t0 < close_{t-1}` ja `close_t0 > open_{t-1}`.
- **Piercing Pattern (3)**: Päivä t-1 laskeva; t0 avaa alle edellisen päätöksen ja sulkee > (edellisen rungon puoliväli), mutta < edellisen avauksen.
- **Three White Soldiers (4)**: Kolme peräkkäistä nousevaa kynttilää, joissa jokainen avaa ja sulkee edellistä korkeammalle.
- **Morning Star (5)**: Päivä1 laskeva; päivä2 rungon koko < 50 % päivä1 rungosta; päivä3 nouseva ja sulkee yli (päivä1 avaus + päätös) / 2.
- **Dragonfly Doji (6)**: `body < 0.1*(range)`, `lower_shadow > 0.6*(range)`, `upper_shadow < 0.1*(range)`.
- **Bullish Divergence (7)**: ks. luku 4 (trendipohjainen, RSI- ja hintapohjien vertailu).
- **Bearish Divergence (8)**: ks. luku 4 (huippujen vertailu).

### 2.2 Signaalin vahvuus per kuvio (0–1 ellei toisin mainita)
Lähde: `analysis/analyzer.py::calculate_signal_strength`.

- **Doji (Dragonfly Doji käyttää samaa pohjaa)**: `1 - body / (high-low)` -> mitä pienempi runko, sitä vahvempi.
- **Hammer**: `(lower_shadow / body) / 3`, rajataan maks. 0.9.
- **Shooting Star** (taustalla, ei vietä Exceliin): `(upper_shadow / body) / 3`, maks. 0.9.
- **Engulfing (Bullish/Bearish)**: kiinteä 0.8.
- **Muut (Piercing, Morning Star, Three White Soldiers, Downtrend placeholder)**: perusarvo 0.5 ellei laskettu erikseen.
- **Volyymi-kerroin**: jos volyymi > 100 000, vahvuus * 1.1 (katkaistaan 1.0).
- **Divergenssit**: erillinen 1–3 asteikko (ks. luku 4).
- **Tulkinta**: 0.0–0.4 heikko, 0.4–0.7 keskivahva, 0.7–1.0 vahva. Divergensseissä 1=heikko, 2=keski, 3=vahva.

## 3. RSI14_t0 – laskentasääntö
Funktio `calculate_rsi(period=14)`:
1. `delta = close_t - close_{t-1}`
2. `gain = max(delta, 0)`, `loss = max(-delta, 0)`
3. `avg_gain = rolling_mean(gain, 14)`, `avg_loss = rolling_mean(loss, 14)` (yksinkertainen keskiarvo, ei Wilder-smoothingia).
4. `RS = avg_gain / loss` (nollat korvataan inf:llä).
5. `RSI = 100 - 100 / (1 + RS)`.
Sarake `RSI14_t0` poimii arvon t0-päivältä (divergence_data/findings).

## 4. Divergenssit
Lähde: `analysis/candlestick_patterns.py`.

### 4.1 Bullish Divergence (koodi 7)
- **Trendivaatimus**: laskutrendi (t-10 > t-5 > t-2 > t0, MA5 < MA10 ja close_t0 < MA10).
- **Paikalliset pohjat**: t0 on 7 päivän ikkunan alin; edellinen pohja haetaan 30 pv taaksepäin, min. 3 pv väli.
- **Ehto**: hinta laskee pohjasta (`price_change < 0`), RSI nousee >= 3 pistettä.
- **Vahvuus 1–3** = `rsi_comp + price_comp + duration_comp`, missä
  - `rsi_comp = min(1, |delta_RSI| / 5)`
  - `price_comp = min(1, |delta_hinta| / 10%)`
  - `duration_comp = min(1, days_between / 20)`
  - rajataan [1,3], pyöristys 2 desimaalia.

### 4.2 Bearish Divergence (koodi 8, ei Excelissä)
- **Trendivaatimus**: nousutrendi (t-10 < t-5 < t-2 < t0, MA5 > MA10 ja close_t0 > MA10).
- **Huiput**: t0 on 7 päivän ikkunan ylin; edellinen huippu 30 pv sisällä, min. 3 pv väli.
- **Ehto**: hinta nousee (`price_change > 0`), RSI laskee <= -3.
- **Vahvuus**: sama 1–3 kaava kuin yllä. Tallennetaan `divergence_data`-tauluun, ei viedä Exceliin.

### 4.3 Excelissä näkyvät divergence-kentät
- `BullDiv_strength`: t0-päivän bullish_strength (1–3) jos pattern 7.
- `BullDiv_recent_strength`: maksimi bullish_strength ikkunassa t0…t-5 (lähin divergenssi 0–5 pv).
- `BullDiv_recent_offset`: offset jolta edellinen löytyi (0=t0, 1=t-1, ..., 5=t-5, 99 jos ei löydy).
- `Has_BullDiv_recent`: 1 jos `BullDiv_recent_strength > 0`, muutoin 0.
- `bullish_divergence`, `bearish_divergence`: päiväkohtaiset strengthit talletettuna results_dataan (bearish ei näy UI:ssa, mutta viedään Exceliin).

## 5. Sarakkeet ja kaavat (ryhmitelty)
### 5.1 Perusmeta
- `ticker`, `date`, `market`: suoraan findingsista/osakedata-indeksistä.
- `candle_pattern`: koodi 0–8 (taulukko luvussa 2).
- `signal_strength`: luvun 2.2 mukainen vahvuus.
- `weekday`: ISO 1–7.

### 5.2 Kynttilädetaljit (t-1, t0, t+1)
Normalisointi: t-1 hinnat / t0_low *100, t0 ja t+1 / t0_close *100.
- `t_1_alin`, `t_1_ylin`, `t_1_bodi`, `t_1_bodi_colour` (1=vihreä).
- `t0_*` ja `t1_*` vastaavasti.
- Johdettu: `t0_alinMiinusClose = t0_alin - 100` (kuinka paljon päivän alin jäi päätöksestä).

### 5.3 Historialliset hinnat ja volatiliteetti
- `t_2`, `t_5`, `t_10`, `t_15`, `t_20`: sulkuhinnat / t0_low *100 (offset taaksepäin).
- `t_2_hajonta` ... `t_20_hajonta`: `pstdev(normalisoidut sulut idx-offset ... idx-1)`.
- `t2`, `t5`, `t10`, `t20`: sulkuhinnat / t0_close *100 (offset eteenpäin).
- `Price_slope_5` = `(100 - t_5) / 5`, `Price_slope_10` = `(100 - t_10) / 10`, `Price_acceleration_5_10` = `slope5 - slope10`.

### 5.4 Volyymit ja impulssi
Kaikki suhteessa 100 pv baselineen ennen jaksoa (keskiarvo positiivisista volyymeista).
- Menneisyys: `t_2_volyymi`, `t_5_volyymi`, `t_10_volyymi`, `t_15_volyymi`, `t_20_volyymi` = (ikkunan keskiarvo) / (t-102...t-3 keskiarvo) *100 (ikkunasta riippuen).
- `t0_volyymi`: `volume_t0 / avg(volume_{t-100...t-1}) *100`.
- Tulevat: `t2_volyymi`, `t5_volyymi`, `t10_volyymi`, `t20_volyymi`: yhden päivän volyymi `t+offset` suhteessa sitä edeltävän 100 päivän keskiarvoon.
- `Volume_impulse`: t0 volyymi / (t-5...t-1 keskiarvo).

### 5.5 Gapit ja kynttiläsuhteet
- `Gap_down_strength`: jos avaus < edellinen close, `|(open_t0-close_{t-1}) / t0_low| *100`, muuten 0.
- `Body_ratio`: `|close-open| / (high-low)` (t0 raakahinnoista).
- `Shadow_ratio`: `(lower_shadow + upper_shadow) / (high-low)`.
- `t0_close_norm`: aina 100.

### 5.6 Liukuvat keskiarvot
- `t_X_Yp_liukuva`: MA(Y) päättyen `t+X`, normalisoitu t0_low:lla osakkeilla, t0_close:lla indekseillä.
  - X in {-2,-5,-10,-15,-20, 0}; Y in {5,10,20}. Lisäksi `t0_50p_liukuva`, `t0_200p_liukuva`.
- Slope-mittarit: `t0_50p_slope`, `t0_200p_slope` = MA-slope / t0_low *100 (5 päivän lookback).
- Trendiregiimit: `trend_regime_5_20`, `trend_regime_20_50`, `trend_regime_50_200` = 1 jos lyhyt MA > pitkä MA, muuten 0.

### 5.7 Indeksivertailut ja volatiliteetti
- SPX/NDX normalisoidut hinnat: `SPX_0`...`SPX_20`, `SPX2`...`SPX20` (vastaavasti NDX). `*_0` = 100.
- `SPX_volatility_10`, `NDX_volatility_10`: `pstdev` indeksin normalisoiduista arvoista t-10...t-1.
- `VIX_10`: `(VIX_t0 / VIX_{t-10}) *100` (jos dataa); `VIX_norm_10` = `(VIX_10 - 100) / 100`.

### 5.8 Momentum, RSI ja kombot
- `RSI14_t0`: luvun 3 mukainen RSI.
- `RSI_slope_5`: `RSI14_t0 - RSI14_{t-5}` (divergence_data-historia).
- Divergenssikentät: ks. luku 4.3.
- Komboliput (30 kpl): `is_<kuvio>_only_t0`, `is_<kuvio>_and_BullDiv_t0`, `is_<kuvio>_and_BullDiv_recent_2d/3d/5d` jokaiselle kuviolle 1–6 (binääriset).
- Same-day aggregaatit: `signal_count_same_day`, `unique_patterns_same_day`, `max_strength_same_day`, `second_best_strength_same_day`, `sum_strength_same_day`, `num_candles_same_day`, `has_multi_candle_combo`, `has_bullish_divergence_same_day`, `signal_combo_code` (0=ei kynttilää/divergenssiä, 1=1 kynttilä, 2=vähintään 2 kynttilää, 3=kynttilä+divergenssi, 4=pelkkä divergenssi), `has_same_day_reversal_cluster`, `is_candle_day`.

### 5.9 Riskitekijät ja blackoutit
- `has_blackout_data`: 1 jos tickerille on blackout-aineisto.
- `is_earnings_t0`, `is_dividend_t0`: tulos- tai osinkopäivä täsmälleen t0.
- `is_earnings_window`, `is_dividend_window`: +/- 3 päivän ikkuna.
- `is_blackout_t0`, `is_blackout_window`: yhdistelmäflagit; `exclude_from_regression` = 1 jos blackout_window.

### 5.10 Sektori
- `sector`: sektori-teksti jos saatavilla.
- `sector_momentum_5/20`: `(sector_close_t0 / sector_close_{t-5/20} - 1) *100`.
- `sector_volatility_20`: `pstdev` sektorin päivätuotoista t-20...t-1.

### 5.11 Lisäfeaturet (88–99)
- `Volatility_ratio_10_20`: `t_10_hajonta / t_20_hajonta` (0/NaN -> tyhjä).
- `Reversal_Context_Score`: `(abs(t_10 - 100)/10) + (t_10_hajonta/2) + (Volume_impulse - 1)` jos kaikki osat saatavilla.
- Muut: `Gap_down_strength`, `Body_ratio`, `Shadow_ratio`, `Volume_impulse`, `RSI_slope_5`, `Price_slope_5/10`, `Price_acceleration_5_10`, `SPX_volatility_10`, `NDX_volatility_10`, `BullDiv_strength`, `BullDiv_recent_strength`, `BullDiv_recent_offset`, `Has_BullDiv_recent`.

### 5.12 Uusien kenttien selitteet ja kaavat
- `BullDiv_strength` / `BullDiv_recent_strength` / `BullDiv_recent_offset` / `Has_BullDiv_recent`: ks. luku 4.3; recent-ikkuna 0–5 pv taaksepäin, offset pienin löydetty (0=t0, 5=t-5, 99 jos ei löydy).
- `bearish_divergence` / `bullish_divergence`: sama päivän strength divergence_data/analysis_findings-taulusta (bearish talletetaan, ei UI:ssa, mutta viedään Exceliin).
- `RSI_slope_5`: `(RSI_t0 - RSI_t-5) / 5`, käyttää divergence_data.rsi-arvoja (ei normalisointia).
- `Price_slope_5`, `Price_slope_10`: `(100 - t_5)/5`, `(100 - t_10)/10` (historia normalisoitu t0_low:iin).
- `Price_acceleration_5_10`: `Price_slope_5 - Price_slope_10` (positiivinen = jyrkkenevä lasku).
- `Volatility_ratio_10_20`: `t_10_hajonta / t_20_hajonta` (pstdev, t0_low-normalisoidut hinnat).
- `Gap_down_strength`: jos avaus < edellinen close, `|(open_t0 - close_{t-1}) / t0_low| * 100`, muuten 0.
- `Body_ratio`: `|close-open| / (high-low)` (t0 raakahinnoista), `Shadow_ratio`: `(lower_shadow + upper_shadow)/(high-low)` (raw).
- `SPX_volatility_10`, `NDX_volatility_10`: pstdev indeksin normalisoiduista arvoista t-10...t-1 (t0_close = 100).
- `Volume_impulse`: `volume_t0 / avg(volume_{t-5...t-1})` (raaka volyymi, ei normalisointia).
- `Reversal_Context_Score`: painotettu summa (luku 5.11) käyttäen t_10 (t0_low-normalisoitu), t_10_hajonta (pstdev, t0_low) ja Volume_impulse.
- `bullDiv_offset`, `bullDiv_last_1d/2d/3d/3d_any`: yleiset BullDiv-liput (offset 0=t0, 99=ei 100 pv sisällä; liput 1 jos divergenssi löytyy annetussa ikkunassa).
- `is_*_only_t0`, `is_*_and_BullDiv_*`: komboliput pattern-slugien (Hammer, Bullish_Engulfing, Piercing_Pattern, Three_White_Soldiers, Morning_Star, Dragonfly_Doji) ja BullDiv-offsetin perusteella; 1 jos pattern t0 ja BullDiv offset <=2/3/5 tai t0.
- `is_candle_day`, `signal_combo_code` (0 ei signaalia, 1 yksi kynttilä, 2 vähintään 2 kynttilää, 3 kynttilä+BullDiv, 4 pelkkä divergenssi), `num_candles_same_day`, `has_multi_candle_combo`, `has_bullish_divergence_same_day`, `signal_count_same_day`, `unique_patterns_same_day`, `max_strength_same_day`, `second_best_strength_same_day`, `sum_strength_same_day`, `has_same_day_reversal_cluster`: same-day aggregaatit kaikista saman ticker+date löydöksistä.
- `is_crisis`: 1 jos date välillä 2025-03-01 ... 2025-04-30.
- Blackout-liput: `has_blackout_data`, `is_earnings_t0`, `is_earnings_window` (+/-2 pv), `is_dividend_t0`, `is_dividend_window` (+/-1 pv), `is_blackout_t0`, `is_blackout_window`, `exclude_from_regression` (kopio window-lipusta).
- `t0_50p_slope`, `t0_200p_slope`: MA-slope 5 pv lookbackista (MA(t0) - MA(t-5)) / 5 / t0_low * 100.
- `trend_regime_5_20`, `trend_regime_20_50`, `trend_regime_50_200`: 1 jos lyhyt MA > pitkä MA, muuten 0.
- `ATR_14`: Average True Range 14 päivän TR:stä; `ATR_ratio_14` = `ATR_14 / t0_low * 100`.
- `MACD_line`, `MACD_signal`, `MACD_hist`: MACD(12,26,9) sulkuhinnoista (ei normalisointia).
- `pivot_low_strength_3/5`: `(min low ikkunassa - t0_low) / min low * 100` 3/5 pv taakse; `pivot_high_strength_3/5`: `(t0_high - max high ikkunassa) / max high * 100`.
- `VIX_10`: `(VIX_t0 / VIX_{t-10}) * 100`; `VIX_norm_10` = `(VIX_10 - 100) / 100`.
- `sector`: sektori-teksti, `sector_momentum_5/20`: `(sector_close_t0 / sector_close_{t-5/20} - 1) * 100`, `sector_volatility_20`: pstdev sektorin päivätuotoista t-20...t-1.
- `weekday`: ISO 1=ma ... 7=su.
## 6. Results_data lisakentät (eivat Excelissa)
- **Perusmeta**: `market` (Yahoo-suffixiin sidottu markkina), `candle_pattern` (0–8), `signal_strength`, `is_crisis` (1 jos pvm 2025-03-01 ... 2025-04-30).
- **BullDiv yleiset liput**: `bullDiv_offset` (0=t0, 99=ei 100p sisalla), `bullDiv_last_1d/2d/3d/3d_any` (binääriset).
- **Kynttilä + BullDiv -kombot** (CANDLE_PATTERN_TO_SLUG: Hammer, Bullish_Engulfing, Piercing_Pattern, Three_White_Soldiers, Morning_Star, Dragonfly_Doji): `is_<slug>_only_t0`, `is_<slug>_and_BullDiv_t0`, `is_<slug>_and_BullDiv_recent_2d/3d/5d`.
- **Same-day aggregaatit**: `signal_count_same_day`, `unique_patterns_same_day`, `max_strength_same_day`, `second_best_strength_same_day`, `sum_strength_same_day`, `signal_combo_code` (0 ei signaaleja, 1 yksi kynttila, 2 = vähintään 2 kynttilää, 3 kynttila+divergenssi, 4 pelkka divergenssi), `num_candles_same_day`, `has_multi_candle_combo`, `has_bullish_divergence_same_day`, `has_same_day_reversal_cluster`, `is_candle_day`.
- **Trendimittarit**: `t0_20p_liukuva` (MA20 paattyen t0, norm t0_low tai t0_close), `t0_50p_slope`, `t0_200p_slope` (MA-slope 5 pv lookback jaettu t0_low:lla *100), `trend_regime_5_20`, `trend_regime_20_50`, `trend_regime_50_200` (1 jos lyhyt MA > pidempi).
- **Volatiliteetti ja ATR**: `ATR_14` (ATR 14 pv, True Range kaava, raakahinnoista), `ATR_ratio_14` = `ATR_14 / t0_low * 100`.
- **MACD**: `MACD_line`, `MACD_signal`, `MACD_hist` laskettu sulkuhinnoista (EMA12 - EMA26, signal=EMA9, hist=line-signal).
- **Pivotit**: `pivot_low_strength_3/5` = `(edellisen minimin low - t0_low) / edellinen minimi *100` 3/5 pv takaa; `pivot_high_strength_3/5` = `(t0_high - edellinen maksimi) / edellinen maksimi *100`.
- **VIX ja kriisilippu**: `VIX_10` = `(VIX_t0 / VIX_{t-10}) *100`, `VIX_norm_10` = `(VIX_10 - 100) / 100`.
- **Bearish/Bullish divergence raakakentät**: `bearish_divergence`, `bullish_divergence` (päiväkohtaiset strengthit, ei UI:ssa).
- **Blackout-liput**: `has_blackout_data`, `is_earnings_t0`, `is_dividend_t0`, `is_earnings_window`, `is_dividend_window`, `is_blackout_t0`, `is_blackout_window`, `exclude_from_regression` (1 jos blackout_window).
- **Sektorit**: `sector`, `sector_momentum_5`, `sector_momentum_20`, `sector_volatility_20` (momentumit = tuottoprosentti, volatiliteetti = pstdev sektorituotoista t-20...t-1).

## 7. Volatiliteettilaskenta (eksakti)
- Funktio `calc_volatility(window)` käyttää `statistics.pstdev`-keskihajontaa.
- Input-sarja: normalisoidut sulkuhinnat (historia) `close / t0_low * 100` ikkunoissa (t-window ... t-1).
- Indeksien volatiliteetit käyttävät samaa `pstdev`-funktiota indeksin normalisoiduista arvoista.
- `Volatility_ratio_10_20` = `pstdev_10 / pstdev_20`; 0-arvot ja puuttuvat palauttavat tyhjän.

## 8. Laskutrendifiltterit (Downtrend-generatori)
Käytetään analyysissä ja divergenssien taustafiltterinä:
1. Porrastava lasku: `close_{t-10} > close_{t-5} > close_{t-2} > close_t`.
2. MA-suodatin: `close_t < MA10` ja `MA5 < MA10` (MA:t yksinkertaisia keskiarvoja).
3. Minimilasku: vähintään 3 % pudotus 10 päivässä (parametri `min_decline_percent`).
4. Valinnainen volyymifiltteri: viimeisten 5 päivän keskiarvo >= 1.2 x keskiarvo (t-25...t-5).
Vain ehdot täyttävät päivät kirjautuvat `downtrend`-patterniksi tai kelpaavat divergenssin pohjaksi.

## 9. Markkinat, weekday ja muut koodit
- Markkinat (taulu `markets`, defaultit `market_repository.py`): Yhdysvallat (`usa`, suffix ""), Suomi (`suomi`, ".HE"), Ruotsi (`ruotsi`, ".ST"), Saksa (`saksa`, ".DE"). Minivolyymit: 100k / 25k / 40k / 80k.
- Sarake `market` tallentaa lyhenteen ja ohjaa UI-filtterit sekä minivolyymirajat.
- Weekday: 1=ma, 2=ti, 3=ke, 4=to, 5=pe, 6=la, 7=su (pörssidatassa käytännössä 1–5).

## 10. Käyttövinkit tulkintaan
- Vahva signaali: `signal_strength >= 0.7` tai `BullDiv_strength >= 2`. Tarkista samana päivänä muiden kynttilöiden määrä (`num_candles_same_day`) ja divergenssi-liput.
- Volyymi > 150 (prosenttipisteinä) indikoi poikkeavaa kiinnostusta; yhdistä `Volume_impulse` ja `t0_volyymi`.
- Volatiliteetti: korkea `t_10_hajonta` + korkea `Volatility_ratio_10_20` = kiihtyvä heilunta; matalat arvot = stabiilimpi trendi.
- Trendiregiimit ja liukuvat keskiarvot auttavat varmistamaan, onko kuvio todellisen laskutrendin pohjalla vai vain lyhyessä korjauksessa.
