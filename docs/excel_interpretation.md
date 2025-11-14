# Excel-tulosten tulkintaopas

Tämä dokumentti täydentää RawCandle-järjestelmän tulosexceliä (96 saraketta) ja kuvaa sarakkeiden sisällön, laskentasäännöt sekä tärkeimmät filtteri- ja tulkintasäännöt. Ensimmäiset 84 saraketta vastaavat alkuperäistä generate_results-rakennetta, ja sarakkeet 85–96 sisältävät `compute_new_features.py`-skriptin tuottamat jatkoanalyysimittarit. Dokumentti on suunnattu analyytikoille, jotka hyödyntävät `results_data`-taulua tai siitä tehtyä Excel-vientiä.

## 1. Yleisrakenne ja normalisointi
- Jokainen rivi kuvaa yksittäistä osake- tai indeksihavaintoa päivänä *t0* (kuviopäivä).
- Excelissä on 84 saraketta (`osake` ... `weekday`). Tietokannan `results_data`-taulussa on lisäksi `market` (lyhenne) samasta rivistä.
- Hintasarjat normalisoidaan:
  - Osakkeet: `t0_low = 100`, jolloin kaikki hintasarakkeet ovat prosentteja päivän alimman hinnan tasosta.
  - Indeksit (SPX, NDX): `t0_close = 100`.
- Volyymit esitetään prosentteina suhteessa edeltävän 100 pörssipäivän keskiarvoon.
- Negatiiviset offsetit (`t_-2`, `t_-5`, ...) viittaavat historiaan; positiiviset (`t2`, `t5`, ...) t0:n jälkeisiin päiviin.

## 2. Sarakkeet ja laskentasäännöt
### 2.1 Perusmeta (1–4)
| # | Sarake | Kuvaus | Kaava / lähde |
|---|--------|--------|---------------|
|1|`osake`|Ticker|`analysis_findings.ticker`|
|2|`date`|t0-päivä|`analysis_findings.date`|
|3|`kynttila`|Kuvion nimi|Analyzerin tunnistus|
|4|`vahvuus`|Signaalin vahvuus 0–1|`calculate_signal_strength()` (luku 7)|

Tietokannan puolella mukana on myös `market` (lyhenne, ks. luku 10).

### 2.2 Kynttiläkomponentit (5–16)
Kaikki arvot ovat prosentteja `t0_low`-tasosta.

| Sarakkeet | Merkitys | Kaava |
|-----------|----------|-------|
|`t_1_alin`, `t_1_ylin`, `t_1_bodi`, `t_1_bodi_colour`|t-1 päivän alin/ylin, rungon koko (%) ja väri (1=vihreä)|`low/high` normalisoidaan `(hinta / t0_low)*100`; `bodi = |close-open|/(high-low)`; väri = 1 jos `close > open`|
|`t0_*`-sarakkeet|Sama logiikka t0-päivälle|Kuten yllä|
|`t1_*`|Sama logiikka t+1-päivälle|Kuten yllä|

### 2.3 Historialliset hinnat ja volatiliteetti (17–26)
| Sarakkeet | Kuvaus | Kaava |
|-----------|--------|-------|
|`t_2`, `t_5`, `t_10`, `t_15`, `t_20`|Sulkuhinta `offset`-päivää ennen t0|`(close_{t-offset} / t0_low) * 100`|
|`t_2_hajonta`, `t_5_hajonta`, `t_10_hajonta`, `t_15_hajonta`, `t_20_hajonta`|Volatiliteetti (populaatiokeskihajonta) viimeisten `offset` päivien normalisoiduista sulkuhinnoista|`pstdev( (close_i / t0_low)*100 )` päiville `[t-offset, ..., t-1]`|

### 2.4 Tulevat hinnat (27–30)
| Sarake | Kuvaus | Kaava |
|--------|--------|-------|
|`t2`, `t5`, `t10`, `t20`|Sulkuhinta `offset` päivää t0:n jälkeen|`(close_{t+offset} / t0_low) * 100`|

### 2.5 Volyymit (31–40)
| Sarake | Kuvaus | Kaava |
|--------|--------|-------|
|`t_2_volyymi`, `t_5_volyymi`, `t_10_volyymi`, `t_15_volyymi`, `t_20_volyymi`|Suhteellinen volyymi|`(avg(volume_{ikkuna}) / avg(volume_{t-100...t-1})) * 100`|
|`t0_volyymi`|t0-päivän volyymi suhteessa 100 pv keskiarvoon|`(volume_{t0} / avg(volume_{t-100...t-1})) * 100`|
|`t2_volyymi` ... `t20_volyymi`|Jälkiperiodien volyymit|Kuten yllä, mutta tulevien päivien keskiarvo suhteessa edeltävään 100 pv keskiarvoon|

### 2.6 Liukuvat keskiarvot (41–58)
` t_X_Yp_liukuva ` kuvaa X päivän päähän siirrettyä liukuvaa keskiarvoa, jossa `Y` on ikkuna. Kaava:
```
MA_{offset,period} = avg(close_{idx+offset-period+1 ... idx+offset}) / norm * 100
```
- `norm = t0_low` osakkeille ja `t0_close` indekseille.
- Esim. `t_5_20p_liukuva` = MA20 päättyen päivään `t-5`.
- `t0_50p_liukuva`, `t0_200p_liukuva` = perinteiset MA50/MA200 päätettynä t0:aan.

### 2.7 Indeksivertailut (59–78)
| Sarake | Kuvaus | Kaava |
|--------|--------|-------|
|`SPX_0`|Perustaso|Kiinteä 100|
|`SPX_2` ... `SPX_20`|S&P 500 (^GSPC) historia t-2 ... t-20|`(spx_close_{t-offset}/spx_close_{t0})*100`|
|`SPX2` ... `SPX20`|S&P 500 tulevat päivät|Sama kaava, mutta offset > 0|
|`NDX_*`|Vastaavat sarjat Nasdaq 100:lle (^NDX)|Kuten SPX|

### 2.8 Momentum, divergenssit ja metadata (79–84)
| # | Sarake | Kuvaus / kaava |
|---|--------|----------------|
|79|`RSI14_t0`|14 päivän RSI (ks. luku 3) haetaan `analysis_findings.rsi14`|
|80|`t0_close_norm`|`(t0_close / t0_low) * 100`, mittaa päätöksen sijaintia päivän vaihteluvälissä|
|81|`Bearish Divergence`|Vahvin arvo (1–3), jos t0...t-3 välillä löytyi laskeva divergenssi (luku 4)|
|82|`Bullish Divergence`|Vahvin arvo (1–3), jos löytyi nouseva divergenssi|
|83|`weekday`|ISO-koodi 1=ma ... 7=su (luku 9)|
|84|`RSI10_t0` (laajennetut raportit)|10 päivän RSI, sama laskenta kuin RSI14 (luku 3) |

> Huom: vakio-Excel sisältää nyt 96 saraketta. Jos jokin uusi feature puuttuu laskennan lähdedatasta, sen soluun kirjoitetaan tyhjä arvo (NaN) mutta perusrivit silti viedään.

### 2.9 Lisätyt analyysifeaturet (85–96)
Sarakkeet 85–96 sijaitsevat otsikkorivin lopussa ja syntyvät `compute_new_features.py`-skriptin ajon yhteydessä ennen Excel-vientiä.

| # | Sarake | Kuvaus / kaava |
|---|--------|----------------|
|85|`RSI_slope_5`|RSI-momentum 5 päivän ikkunassa: `RSI14_t0 – RSI14_{t-5}` (`divergence_data`-taulun historiasta)|
|86|`Price_slope_5`|Keskimääräinen laskuvauhti 5 päivää ennen t0: `(100 − t_5) / 5`|
|87|`Price_slope_10`|Keskimääräinen laskuvauhti 10 päivää ennen t0: `(100 − t_10) / 10`|
|88|`Price_acceleration_5_10`|Trendin kiihtyvyys: `Price_slope_5 − Price_slope_10` (positiivinen = jyrkkenevä lasku)|
|89|`Volatility_ratio_10_20`|Lyhyen ja pitkän volatiliteetin suhde: `t_10_hajonta / t_20_hajonta` (0 ja NaN pistetään tyhjäksi)|
|90|`Gap_down_strength`|Mahdollinen gap ennen kuviota: `(open_raw − prev_close_raw) / prev_close_raw`, jossa `prev_close_raw` = t-1 päätös raakadatasta|
|91|`Body_ratio`|Rungon osuus kynttilän vaihteluvälistä: `|close_raw − open_raw| / (high_raw − low_raw)`|
|92|`Shadow_ratio`|Alavarjon suhde ylävarjoon: `lower_shadow / upper_shadow`, missä `lower_shadow = min(open,close) − low` ja `upper_shadow = high − max(open,close)`|
|93|`SPX_volatility_10`|S&P 500 (^GSPC) 10 päivän (edeltävä) sulkuhintojen keskihajonta; lasketaan `osakedata.db`-kannan indeksisarjoista|
|94|`NDX_volatility_10`|Nasdaq 100 (^NDX) vastaava 10 päivän volatiliteetti|
|95|`Volume_impulse`|t0-päivän volyymipiikki suhteessa edeltävän 10 päivän keskiarvoon: `t0_volume_raw / prev10_avg_volume` (raaka volyymit `osakedata`-kannasta)|
|96|`Reversal_Context_Score`|Yhdistetty kontekstimittari: `0.4 * drop_10 + 0.4 * bullish_divergence − 0.2 * t_10_hajonta`, missä `drop_10 = 100 − t_10`|

> Jos jokin lähtösarake puuttuu (esim. historiadataa ei ole), kyseinen lisäfeature jää tyhjäksi muttei estä Excel-vientiä. Varmista ennen vientiä, että `compute_new_features.py` on ajettu onnistuneesti (logitiedote kertoo, montako riviä päivitettiin).

## 3. RSI14_t0 ja RSI10_t0 – laskenta
`analysis/candlestick_patterns.calculate_rsi()` laskee RSI:n:
1. Päivittäinen muutos `Delta = close_t - close_{t-1}`.
2. `gain = max(Delta, 0)` ja `loss = max(-Delta, 0)`.
3. Lasketaan liukuvat keskiarvot pituudella `period` (14 tai 10):
   - `avg_gain = rolling_mean(gain, period)`
   - `avg_loss = rolling_mean(loss, period)`
4. `RS = avg_gain / max(avg_loss, epsilon)` (epsilon estää nollajaon).
5. `RSI = 100 - 100 / (1 + RS)`.

`RSI10_t0` käyttää samaa kaavaa mutta `period = 10`. Molemmat viittaavat t0-päivään.

## 4. Divergenssit
### 4.1 Bullish Divergence (koodi 7)
- Hinta tekee alemman pohjan, RSI korkeamman pohjan.
- Pohjien välissä vähintään 3 päivää, RSI-parannus >= 3 pistettä.
- `lookback_days = 30` edellisen pohjan löytämiseen.
- Vain laskutrendissä (`t-10 > t-5 > t-2 > t0`, `t0 < MA10`, `MA5 < MA10`).
- Vahvuus (1–3) = `clamp(rsi_component + price_component + duration_component)`, missä
  - `rsi_component = min(1, |DeltaRSI|/5)`
  - `price_component = min(1, |Deltahinta|/10%)`
  - `duration_component = min(1, days_between/20)`.

### 4.2 Bearish Divergence (koodi 8)
- Peilikuva yllä: hinta tekee korkeamman huipun, RSI matalamman.
- Nousutrendi-tausta (`t-10 < t-5 < t-2 < t0`, `t0 > MA10`, `MA5 > MA10`).
- RSI-lasku vähintään 3 pistettä; vahvuuskaava identtinen.

Tulokset tallentuvat `divergence_data`-tauluun. Exceliin nostetaan t0...t-3 päivien vahvin arvo; jos bullish-divergenssi löytyy, bearish-arvo pakotetaan nollaan ja päinvastoin.

## 5. Kynttiläkuviot ja numerokoodit
| Koodi | Kuvio | Kuvaus |
|-------|-------|--------|
|0|`downtrend`|Laskutrendifiltterin täyttävä havainto, toimii myös placeholderina tuntemattomille|
|1|Hammer|Pitkä alavarjo, pieni runko, käännesignaali|
|2|Bullish Engulfing|Nouseva kynttilä nielee edellisen laskupäivän rungon|
|3|Piercing Pattern|Toinen kynttilä sulkee vähintään edellisen rungon puolivälin yläpuolelle|
|4|Three White Soldiers|Kolme peräkkäistä nousevaa pitkää kynttilää|
|5|Morning Star|Laskeva -> pieni runko -> nouseva kolmikkokuvio|
|6|Dragonfly Doji|Doji, jossa pitkä alavarjo ja lähes olematon ylävarjo|
|7|Bullish Divergence|RSI nousee vaikka hinta laskee|
|8|Bearish Divergence|RSI laskee vaikka hinta nousee|

## 6. Kuviokohtaiset tunnistussäännöt
Perustuu `analysis/candlestick_patterns.py` -funktioihin.

- **Hammer**: `lower_shadow > 2 x body`, `upper_shadow < 0.5 x body`, runko < 40 % koko kynttilästä.
- **Bullish Engulfing**: edellinen päivä laskeva, nykyinen nouseva ja sen runko kattaa edellisen rungon (`open < prev_close`, `close > prev_open`).
- **Piercing Pattern**: päivä 1 laskeva; päivä 2 avaa edellisen päätöksen alapuolelta ja sulkee vähintään edellisen rungon puolivälin yläpuolelle muttei yli avauksen.
- **Three White Soldiers**: kolme peräkkäistä nousevaa kynttilää, joissa jokainen avaa ja sulkee edellistä korkeammalle.
- **Morning Star**: laskeva pitkärunkoinen kynttilä, keskimmäinen pieni runko (usein doji), kolmas nouseva joka sulkee vähintään ensimmäisen rungon puolivälin yläpuolelle.
- **Dragonfly Doji**: hyvin pieni runko (<10 %), pitkä alavarjo (>60 % koko kynttilästä), lähes olematon ylävarjo.
- **Bullish/Bearish Divergence**: ks. luku 4.
- **Downtrend**: täyttää laskutrendifiltterin (luku 8), tallennetaan erilliseksi patterniksi.

## 7. Signaalin vahvuus ja tulkinta
`analysis.analyzer.Analyzer.calculate_signal_strength()` tuottaa arvon 0–1 (divergenssit 1–3 skaalataan taulukossa). Tulkinta:
- **0.0–0.4**: heikko signaali.
- **0.4–0.7**: keskivahva, vaatii vahvistusta muista mittareista.
- **0.7–1.0**: vahva signaali.

| Kuvio | Laskenta | Huomiot |
|-------|----------|---------|
|Downtrend (0)|Kiinteä 1.0 (`downtrend_generator` asettaa)|Edustaa suodatetun laskutrendin vahvuutta|
|Hammer (1)|`min(0.9, (lower_shadow/body)/3)`|Pitkä alavarjo nostaa vahvuutta; korkea volyymi (>100k) x1.1 (max 1)|
|Bullish Engulfing (2)|Perusarvo 0.8 (+volyymikerroin)|Kuvio on lähtökohtaisesti vahva|
|Piercing Pattern (3)|Oletus 0.5 (+volyymi)|Ei erillistä kaavaa -> neutraali vahvuus|
|Three White Soldiers (4)|Oletus 0.5 (+volyymi)|Kolmen päivän rakenne huomioidaan laadullisesti|
|Morning Star (5)|Oletus 0.5 (+volyymi)|
|Dragonfly Doji (6)|Doji-logiikka: `1 - body/total_range`|Mitä pienempi runko, sitä vahvempi|
|Bullish Divergence (7)|1–3 skaala; Excelissä tulkitaan 1=heikko, 2=keskivahva, 3=vahva|Arvo perustuu RSI-, hinta- ja kesto-komponentteihin|
|Bearish Divergence (8)|Sama kuin yllä|—|

Volyymikerroin: jos `volume > 100000`, vahvuus kerrotaan 1.1:llä (rajataan maksimiin 1.0).

## 8. Laskutrendifiltterit
Käytetään sekä analysoitaessa että `downtrend_generator`-moduulissa:
1. **Porrastava lasku**: `close_{t-10} > close_{t-5} > close_{t-2} > close_t`.
2. **Minimipudotus**: vähintään 3 % lasku 10 päivän aikana.
3. **MA-suodatin**: `close_t < MA10` ja `MA5 < MA10`.
4. **(Valinnainen) Volyymi-suodatin**: viimeisten 5 päivän keskimääräinen volyymi >= 1.2 x keskiarvoon (päivät t-25 ... t-5).

Vain ehdot täyttävät havainnot päätyvät `downtrend`-patterniksi tai divergenssien taustaksi.

## 9. Viikonpäiväkoodit (`weekday`)
| Arvo | Päivä |
|------|-------|
|1|Maanantai|
|2|Tiistai|
|3|Keskiviikko|
|4|Torstai|
|5|Perjantai|
|6|Lauantai (harvinainen)|
|7|Sunnuntai (harvinainen)|

Koodi vastaa `datetime.isoweekday()`-palautusta; käytännössä pörssidatassa arvoja 1–5.

## 10. Markkinat ja minivolyymit
`market_repository.py` ylläpitää oletusmarkkinoita.

| Nimi | Lyhenne | Yahoo-suffix | Minimi-volyymi |
|------|---------|--------------|----------------|
|Yhdysvallat|`usa`|`` (tyhjä)|100000|
|Suomi|`suomi`|`.HE`|25000|
|Ruotsi|`ruotsi`|`.ST`|40000|
|Saksa|`saksa`|`.DE`|80000|

Lyhenteet tallennetaan `results_data.market`-kenttään ja niitä käytetään UI:n markkina-filttereissä.

## 11. Volatiliteetin tulkinta
- `t_X_hajonta` käyttää `statistics.pstdev`-funktiota (populaatiokeskihajonta), joten arvo kuvaa todellista hajontaa eikä otosestimaattia.
- Normalisointi `t0_low=100` mahdollistaa volatiilisuuden vertailun eri hintatason osakkeiden välillä.
- Yhdessä `t0_close_norm`-arvon kanssa voidaan nähdä sulkeutuuko kynttilä lähellä päivän ääripäitä.

## 12. Tärpit käytännön tulkintaan
- **Volyymit** >150 viittaavat poikkeukselliseen aktiivisuuteen.
- **t0_close_norm ~ 100** → päätös lähellä päivän pohjaa; arvot >150 kertovat rajusta ostoryntäyksestä.
- **RSI14/RSI10** <30 vahvistaa ylimyytyä tilaa laskutrendeissä; >70 kertoo ylikuumentumisesta nousevissa kuvioissa.
- **Indeksivertailut** (SPX/NDX) näyttävät markkinan laajemman suunnan; jos molemmat ovat <100, ympäristö on laskenut.

Tämän oppaan avulla Excel-tietoja voi tulkita johdonmukaisesti, ymmärtäen sekä numeroiden taustalla olevat kaavat että niitä tukevat markkinafiltterit.
