# Datacenter-raporttien statusten muodostumisen spesifikaatio

## Tarkoitus

Tämä dokumentti kuvaa, miten **raporttitason statukset** muodostuvat Datacenter-raporttiputkessa.

Rajaus:

- daily-raportti
- rolling 2d -raportti
- rolling 5d -raportti
- rolling 30d -raportti
- osake / ticker -taso
- alatoimiala / subindustry -taso
- layer-taso
- koko ecosystem-taso

Tämä dokumentti on tarkoituksella rajattu vain **raporttien generointiin**.

Se ei kuvaa:

- Datacenter Dashboardin final action -logiikkaa
- dashboardin decision-prioriteetteja
- `pullback_validity`-luokittelua
- `entry_readiness`-luokittelua
- `candidate_priority`-luokittelua

Ne muodostuvat vasta myöhemmin dashboard-kerroksessa raporttirivien päälle.


## Kanoninen totuus

Erillistä ulkoista spesifikaatiota, joka ohittaisi koodin, ei tällä hetkellä ole.

Kanoninen toteutus on näissä tiedostoissa:

- [analysis/datacenter_indices/swing_daily_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_daily_report.py:1)
- [analysis/datacenter_indices/swing_weekly_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_weekly_report.py:1)
- [analysis/datacenter_indices/taxonomy.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/taxonomy.py:1)

Jos tämä dokumentti ja koodi ovat ristiriidassa, koodi on ensisijainen totuus.


## Korkean tason malli

Datacenter-raportit rakentuvat kolmesta tietokerroksesta:

1. **Group signal -rivit**
   - lähdetaulu: `dc_group_swing_signal_daily`
   - käytetään ecosystem / layer / subindustry -tason timing- ja heat-tilaan
   - tärkeät statuskentät:
     - `timing_state`
     - `timing_reason`
     - `overheat_risk_level`
     - `data_quality_status`

2. **Ticker signal -rivit**
   - lähdetaulu: `dc_ticker_swing_signal_daily`
   - käytetään ticker-tason breakout / pullback / exit pressure -tilaan
   - tärkeät kentät:
     - `breakout_signal`
     - `pullback_signal`
     - `exit_risk_signal`
     - `exit_risk_severity`
     - `exit_reason`
     - `ticker_trend_state`
     - `latest_structure_label`
     - `latest_bos_event_type`
     - `latest_reset_reason`
     - `price_data_status`

3. **Synthetic structure -rivit**
   - lähdetaulu: `dc_group_synthetic_ohlc_daily`
   - käytetään group-rakenteen kontekstiin
   - tärkeät kentät:
     - `trend_classification`
     - `latest_structure_label`
     - `latest_structure_freshness`
     - `latest_bos_event_type`
     - `latest_bos_freshness`
     - `latest_reset_reason`
     - `latest_reset_freshness`
     - `distance_to_ema20_pct`


## Taxonomy ja scope

Datacenter-jäsenyys määritellään taxonomy-CSV:ssä:

- [analysis/datacenter_indices/taxonomy.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/taxonomy.py:1)

Tärkeät taxonomy-sarakkeet:

- `ticker`
- `layer`
- `subindustry`
- `report_group_status`

Sallitut taxonomy-statukset:

- `CORE`
- `EXTENDED`
- `WATCH_ONLY`
- `TOO_SMALL`

Taxonomy määrää:

- mihin layeriin ticker kuuluu
- mihin subindustryyn ticker kuuluu
- mitkä rivit kuuluvat Datacenter-ecosystemiin

Jos watchlist-tickeriä ei löydy raportin käyttämästä taxonomy-kontekstista, se käsitellään tilana:

- `NOT_PART_OF_DATACENTER_ECOSYSTEM`


## Statusten muodostuminen raporttityypeittäin

### Daily-raportti

Daily-logiikka on tiedostossa:

- [analysis/datacenter_indices/swing_daily_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_daily_report.py:1)

Daily-raportti sisältää sekä:

- group-tason statusnäkymät
- ticker-tason watchlist-statusnäkymät


### Rolling-raportit

Rolling-logiikka on tiedostossa:

- [analysis/datacenter_indices/swing_weekly_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_weekly_report.py:1)

Sama moottori parametrisoidaan `window_size`-arvolla.

Dashboard-yhteensopivissa raporteissa tarkoitetut ikkunat ovat:

- 2
- 5
- 30

Rolling-raportit käyttävät samoja daily-lähdetauluja, mutta aggregoivat ne päiväikkunan yli.


## Ticker / osake -status daily-raportissa

Daily-ticker-status muodostuu funktioissa:

- `_build_daily_report_ticker_row(...)`
- `_classify_daily_watchlist_status(...)`

Relevantti kohta:

- [analysis/datacenter_indices/swing_daily_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_daily_report.py:794)

Daily-ticker-rivi rikastetaan ensin näillä tiedoilla:

- primary layer
- primary subindustry
- tickerin rakennekentät
- subindustryn timing / overheat -konteksti
- layerin timing / overheat -konteksti

Sen jälkeen `watchlist_status` annetaan tällä prioriteettijärjestyksellä:

1. `NOT_PART_OF_DATACENTER_ECOSYSTEM`
   - jos `in_datacenter_ecosystem == "NO"`

2. `MISSING_PRICE`
   - jos `price_data_status` on jokin seuraavista:
     - `MISSING_AS_OF_DATE`
     - `MISSING_CLOSE_AS_OF_DATE`

3. `HIGH_EXIT_RISK`
   - jos `exit_risk_severity == "HIGH"`

4. `MEDIUM_EXIT_RISK`
   - jos `exit_risk_severity == "MEDIUM"`

5. `BREAKOUT_CANDIDATE`
   - jos `breakout_signal == 1`

6. `PULLBACK_CANDIDATE`
   - jos `pullback_signal == 1`

7. `GROUP_RISK`
   - jos group-konteksti on riskinen:
     - subindustryn `timing_state` on `EXIT_ZONE` tai `TRIM_WATCH`
     - tai layerin `timing_state` on `EXIT_ZONE` tai `TRIM_WATCH`
     - tai subindustryn `overheat_risk_level` on `HIGH` tai `EXTREME`
     - tai layerin `overheat_risk_level` on `HIGH` tai `EXTREME`

8. `NEUTRAL_MONITOR`
   - fallback, jos mikään yllä olevista ei täyty

Tämä on daily-raportin pääasiallinen ticker-statusluokittelu.


## Subindustry- ja layer-context risk daily-raportissa

Daily context risk -liput eivät ole erillisiä decision-outputteja.
Ne johdetaan group-tason timing- ja overheat-kontekstista.

Relevantit helperit:

- `_has_subindustry_context_risk(...)`
- `_has_layer_context_risk(...)`
- `_daily_context_risk_value(...)`

Säännöt:

- context risk on `YES`, jos:
  - timing state on `EXIT_ZONE` tai `TRIM_WATCH`
  - tai overheat risk level on `HIGH` tai `EXTREME`

- context risk on `NO`, jos ticker kuuluu Datacenter-ecosystemiin mutta tällaista riskiä ei ole

- context risk on tyhjä merkkijono, jos ticker ei kuulu Datacenter-ecosystemiin

Tästä syntyvät kentät:

- `subindustry_context_risk`
- `layer_context_risk`


## Subindustry- ja layer-status daily taxonomy listingissä

Daily taxonomy listing rakennetaan funktiossa:

- `_build_daily_taxonomy_listing_rows(...)`

Relevantti kohta:

- [analysis/datacenter_indices/swing_daily_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_daily_report.py:877)

`LAYER`-riveille:

- `status = layer_group_row["timing_state"]`

`SUBINDUSTRY`-riveille:

- `status = subindustry_group_row["timing_state"]`

`TICKER`-riveille:

- `status = ticker_output_row["watchlist_status"]`

Eli daily taxonomy listingissä:

- layer-status tulee suoraan layer group -rivin timing-statuksesta
- subindustry-status tulee suoraan subindustry group -rivin timing-statuksesta
- ticker-status tulee yllä kuvatusta daily watchlist -luokittelusta


## Ecosystem-status daily-raportissa

Daily-raportti käyttää erityistä ecosystem-riviä:

- `group_type == "ecosystem"`
- `group_name == "DC_ECOSYSTEM_TOTAL"`

Relevantti kohta:

- [analysis/datacenter_indices/swing_daily_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_daily_report.py:1327)

Daily-raportin dashboard-lohko ei rakenna ecosystemille erillistä ticker-tyyppistä statuslabelia.
Sen sijaan se näyttää ecosystem-mittarit ecosystem group -riviltä, erityisesti:

- `return_5d`
- `return_10d`
- `return_20d`
- `return_60d`
- `pct_above_ema20`
- `pct_above_ma10`
- `ema20_breadth_delta_5d`
- `overheat_risk_level`

Tärkeä tulkinta:

- ecosystem-status esitetään ennen kaikkea **group timing / breadth / overheat** -kenttien kautta
- ei daily `watchlist_status` -tyyppisenä statuksena


## Rolling ticker-status: current vs window

Rolling-raporteissa käytetään kahta erillistä ticker-statuskäsitettä:

- `current_watchlist_status`
- `window_watchlist_status`

Ne rakennetaan funktioissa:

- `_build_rolling_watchlist_rows(...)`
- `_classify_rolling_current_watchlist_status(...)`
- `_classify_rolling_window_watchlist_status(...)`

Relevantit kohdat:

- [analysis/datacenter_indices/swing_weekly_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_weekly_report.py:1257)
- [analysis/datacenter_indices/swing_weekly_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_weekly_report.py:1300)


## Rolling current ticker-status

`current_watchlist_status` kuvaa **ikkunan viimeisintä päivää**.

Prioriteettijärjestys:

1. `NOT_PART_OF_DATACENTER_ECOSYSTEM`
2. `MISSING_PRICE`
3. `HIGH_EXIT_RISK`
   - jos viimeisin `exit_risk_severity == "HIGH"`
4. `MEDIUM_EXIT_RISK`
   - jos viimeisin `exit_risk_severity == "MEDIUM"`
5. `BREAKOUT_CANDIDATE`
   - jos viimeisin `breakout_signal == 1`
6. `PULLBACK_CANDIDATE`
   - jos viimeisin `pullback_signal == 1`
7. `GROUP_RISK`
   - jos viimeisin layer/subindustry-konteksti on riskinen
8. `NEUTRAL_MONITOR`

Tämä on käytännössä daily-ticker-statuksen rolling-vastine, mutta arvioituna ikkunan viimeisestä rivistä.


## Rolling window ticker-status

`window_watchlist_status` kuvaa, tapahtuiko **missä tahansa ikkunan sisällä** merkittävää tilaa.

Prioriteettijärjestys:

1. `NOT_PART_OF_DATACENTER_ECOSYSTEM`
2. `MISSING_PRICE`
3. `HIGH_EXIT_RISK`
   - jos `high_exit_risk_days > 0`
4. `MEDIUM_EXIT_RISK`
   - jos `medium_exit_risk_days > 0`
5. `BREAKOUT_CANDIDATE`
   - jos `breakout_days > 0`
6. `PULLBACK_CANDIDATE`
   - jos `pullback_days > 0`
7. `GROUP_RISK`
   - jos viimeisin group-konteksti on riskinen
8. `NEUTRAL_MONITOR`

Tämä on ikkuna-aggrekaatti, ei vain viimeisen päivän snapshot.


## Layer- ja subindustry-status rolling taxonomy listingissä

Rolling taxonomy listing rakennetaan funktiossa:

- `_build_rolling_taxonomy_listing_rows(...)`

Relevantti kohta:

- [analysis/datacenter_indices/swing_weekly_report.py](/home/kalle/projects/rawcandle/analysis/datacenter_indices/swing_weekly_report.py:1425)

`LAYER`-riveille:

- `current_status = viimeisin layer timing_state`
- `window_status = pahin timing_state koko ikkunassa`

`SUBINDUSTRY`-riveille:

- `current_status = viimeisin subindustry timing_state`
- `window_status = pahin timing_state koko ikkunassa`

Rolling group window statusin vakavuusjärjestys on:

1. `EXIT_ZONE`
2. `TRIM_WATCH`
3. `ADD_ON_PULLBACK`
4. `BUY_ZONE`
5. `NEUTRAL`

Tämä tarkoittaa, että rolling window status on **worst-case-yhteenveto**, ei keskiarvo.


## Ticker-status rolling taxonomy listingissä

Rolling taxonomy listingin `TICKER`-riveillä:

- `current_status = current_watchlist_status`
- `window_status = window_watchlist_status`

Siksi rolling ticker -rivillä on aina kaksi näkymää:

- mitä viimeisin päivä sanoo juuri nyt
- mitä koko ikkuna kertoo tapahtuneen jakson aikana


## Ecosystem-status rolling-raporteissa

Rolling-raportit eivät rakenna ecosystemille erillistä itsenäistä watchlist-statuslabelia tickerien tapaan.

Sen sijaan rolling ecosystem -tila näkyy:

- rolling group -rivien kautta, jotka tulevat taulusta `dc_group_swing_signal_daily`
- erityisesti ecosystem group -rivin timing- ja breadth-kentissä
- sekä window-yhteenvedoissa, jotka syntyvät toistuvista daily-riveistä

Käytännössä:

- ecosystem-tason tulkinta on ennen kaikkea **group timing / breadth / overheat** -kontekstia
- ei rolling `current_watchlist_status` / `window_watchlist_status` -paria


## Rolling 30d:n erikoisstatukset

Rolling 30d -raportti lisää tickerille kaksi erityistä report-layer-luokitusta:

- `rolling_30_buy_state`
- `rolling_30_exit_state`

Nämä ovat raporttitason statuksia, eivät dashboardin final actioneita.


### 30d buy state

Muodostetaan funktiossa:

- `_classify_rolling_30_buy_row(...)`

Mahdolliset arvot:

- `BUY_ZONE`
- `WATCH_ZONE`
- `AVOID`
- `INSUFFICIENT_DATA`

Korkean tason tarkoitus:

- `BUY_ZONE`
  - toistuvaa buy-aktiivisuutta
  - rakenne hyväksyttävä
  - ei vahvaa exit-painetta

- `WATCH_ZONE`
  - rakenne on sekoittunut tai vahvistumaton

- `AVOID`
  - selvä rakenteellinen tai exit-riskiblokkeri
  - esimerkiksi down trend, fresh BOS down, fresh reset, eksplisiittinen high exit risk tai selvästi bearish relevance


### 30d exit state

Muodostetaan funktiossa:

- `_classify_rolling_30_exit_row(...)`

Mahdolliset arvot:

- `EXTREME`
- `EXIT_ZONE`
- `WATCH`
- `NORMAL`
- `INSUFFICIENT_DATA`

Korkean tason tarkoitus:

- `EXTREME`
  - erittäin vahva exit-paine
- `EXIT_ZONE`
  - kohonnut exit-riski
- `WATCH`
  - lievä tai vahvistumaton exit-riski
- `NORMAL`
  - ei olennaista exit-painetta


## Rolling 5d:n erikoisstatus: pullback

Muodostetaan funktiossa:

- `_classify_rolling_5_pullback_row(...)`

Mahdolliset arvot:

- `PULLBACK_CANDIDATE`
- `EARLY_PULLBACK`
- `FAILED_PULLBACK`
- `SHORT_TERM_BREAKDOWN`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

Tämä on raporttitason lyhyen ikkunan pullback-luokittelu.

Korkean tason merkitys:

- `PULLBACK_CANDIDATE`
  - pullback-evidenssiä on
  - rakenne on hyväksyttävä
  - vahvaa blokkia ei ole

- `EARLY_PULLBACK`
  - pullback-evidenssiä on jonkin verran, mutta vahvistus ei vielä riitä

- `FAILED_PULLBACK`
  - pullback-asetelma on olemassa, mutta rakenne tai riski blokkaa sen

- `SHORT_TERM_BREAKDOWN`
  - pullback-asetelmaa ei ole, ja lyhyen aikavälin breakdown dominoi

- `NO_PULLBACK`
  - merkityksellistä pullback-evidenssiä ei ole


## Rolling 2d:n erikoisstatus: sell pressure

Muodostetaan funktiossa:

- `_classify_rolling_2_sell_pressure_row(...)`

Mahdolliset arvot:

- `EMERGENCY_SELL_PRESSURE`
- `SHARP_2D_DROP`
- `WATCH_PRESSURE`
- `NO_EMERGENCY`
- `INSUFFICIENT_DATA`

Korkean tason merkitys:

- `EMERGENCY_SELL_PRESSURE`
  - vahvistettu akuutti lyhyen aikavälin sell pressure

- `SHARP_2D_DROP`
  - jyrkkä mutta ei kaikkein äärimmäisin lyhyen aikavälin vaurio

- `WATCH_PRESSURE`
  - lievä tai vahvistumaton lyhyen aikavälin paine

- `NO_EMERGENCY`
  - ei merkittävää 2 päivän sell pressurea


## Yhteenveto: mistä statukset tulevat tasoittain

### Ticker / osake

Daily:

- päästatuskenttä: `watchlist_status`

Rolling:

- päästatuskentät:
  - `current_watchlist_status`
  - `window_watchlist_status`
- lisäksi erikoisstatuksia:
  - 30d: buy / exit
  - 5d: pullback
  - 2d: sell pressure


### Subindustry

Daily:

- `status = timing_state` group-riviltä

Rolling:

- `current_status = viimeisin timing_state`
- `window_status = pahin timing_state ikkunassa`


### Layer

Daily:

- `status = timing_state` group-riviltä

Rolling:

- `current_status = viimeisin timing_state`
- `window_status = pahin timing_state ikkunassa`


### Ecosystem

Daily:

- esitetään ecosystem group -rivillä `DC_ECOSYSTEM_TOTAL`
- keskeiset kentät:
  - breadth-mittarit
  - return-mittarit
  - `overheat_risk_level`

Rolling:

- esitetään rolling group -kontekstina
- ei ticker-tyyppisenä watchlist-statuslabelina


## Tärkeä ero suhteessa dashboard-logiikkaan

Raporttikerros päättyy tähän.

Se tuottaa statuskenttiä kuten:

- `watchlist_status`
- `current_watchlist_status`
- `window_watchlist_status`
- `timing_state`
- `current_status`
- `window_status`
- `rolling_30_buy_state`
- `rolling_30_exit_state`
- `rolling_5_pullback_state`
- `rolling_2_sell_pressure_state`

Dashboard-kerros lukee nämä rivit myöhemmin ja rakentaa niiden päälle:

- final action
- pullback validity
- entry readiness
- candidate priority

Ne eivät ole sama asia kuin raporttien statuskentät.


## Tulkintasäännöt ihmiselle

Kun ihminen lukee raportteja, oikea mentaalimalli on tämä:

1. **Ticker-status** on suora osaketason luokittelu.
2. **Subindustry- ja layer-status** ovat group timing state -luokituksia, eivät ticker-decisioneita.
3. **Context risk** tarkoittaa, että ympäröivä group-tausta on riskinen, vaikka ticker itse ei olisi vielä pahimmassa tilassa.
4. **Rolling current status** tarkoittaa: mitä viimeisin päivä sanoo nyt.
5. **Rolling window status** tarkoittaa: mitä tapahtui ainakin kerran valitun ikkunan aikana.
6. **30d / 5d / 2d erikoisstatukset** ovat erillisiä report-näkymiä eri taktisiin kysymyksiin:
   - 30d: laajempi buy / exit -asento
   - 5d: pullbackin laatu
   - 2d: akuutti sell pressure


## Käyttösäännöt tulevalle AI-chatille

Kun tuleva AI kuvaa Datacenter-raporttien statuksia, sen pitää noudattaa näitä sääntöjä:

1. Älä sekoita raporttistatusta dashboardin final actioniin.
2. Älä väitä tickerin olevan `SELL` / `WATCH` / `BUY_NOW` pelkkien raporttirivien perusteella.
3. Käytä mahdollisuuksien mukaan täsmällisiä kenttänimiä.
4. Jos olet epävarma, viittaa tämän dokumentin lähdekooditiedostoihin.
5. Käsittele tätä dokumenttia ihmislukijalle kirjoitettuna selityksenä nykyisestä toteutuksesta, ei koodista riippumattomana totuutena.
