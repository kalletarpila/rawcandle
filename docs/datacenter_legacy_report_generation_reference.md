# Datacenter legacy report generation reference

## Purpose of this document

Tämä dokumentti kuvaa, miten legacy-datacenter-raportit `datacenter_rolling_30`, `datacenter_rolling_5`, `datacenter_rolling_2` ja `datacenter_daily` tuotetaan, mitä koodipolkuja ne käyttävät, mitä lähdetauluja ne lukevat ja miten ne eroavat uudemmasta V3 / `eco_*` -raporttipolusta.

Tämä dokumentti keskittyy nimenomaan vanhaan raporttipolkuun. `dc_*`-taulujen yksityiskohtainen merkitys on kuvattu erillisessä dokumentissa [docs/datacenter_dc_tables_reference.md](/home/kalle/projects/rawcandle/docs/datacenter_dc_tables_reference.md).

## Scope

Tämä dokumentti kattaa:

- legacy `datacenter_rolling_30`
- legacy `datacenter_rolling_5`
- legacy `datacenter_rolling_2`
- legacy `datacenter_daily`

Tämä dokumentti ei kata:

- V3 / `eco_*` -raporttien sisäistä muodostusta muuten kuin vertailuna
- dashboard-UI:n muodostusta
- uutta dashboard-designia
- scheduler-käyttäytymistä siltä osin kuin se ei käynnistä näiden raporttien tuotantoa

## Executive summary

| Report | Main CLI / entrypoint | Main builder / formatter | Main source tables | Output files | Status / role |
|---|---|---|---|---|---|
| `datacenter_daily` | `run_datacenter_daily_signal_report.py` | `analysis.datacenter_indices.swing_daily_report` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily` | `datacenter_daily_<date>_<hhmm>_full.md`, `datacenter_daily_<date>_<hhmm>_full.csv` | `active legacy report; runs alongside V3` |
| `datacenter_rolling_30` | `run_datacenter_rolling_swing_report.py` tai pipeline-vaihe `rolling_30_report` | `analysis.datacenter_indices.swing_weekly_report` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily` | `datacenter_rolling_30_<date>_<hhmm>_full.md`, `datacenter_rolling_30_<date>_<hhmm>_full.csv` | `active legacy report; runs alongside V3` |
| `datacenter_rolling_5` | `run_datacenter_rolling_swing_report.py` tai pipeline-vaihe `rolling_5_report` | `analysis.datacenter_indices.swing_weekly_report` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily` | `datacenter_rolling_5_<date>_<hhmm>_full.md`, `datacenter_rolling_5_<date>_<hhmm>_full.csv` | `active legacy report; runs alongside V3` |
| `datacenter_rolling_2` | `run_datacenter_rolling_swing_report.py` tai pipeline-vaihe `rolling_2_report` | `analysis.datacenter_indices.swing_weekly_report` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily` | `datacenter_rolling_2_<date>_<hhmm>_full.md`, `datacenter_rolling_2_<date>_<hhmm>_full.csv` | `active legacy report; runs alongside V3` |

## Legacy report generation flow

Legacy-raportit ovat read-only-renderöijiä. Ne eivät laske datacenter-putken upstream-signaaleja uudelleen, vaan lukevat jo valmiiksi persistoidut `dc_*`-taulut `analysis.db`:stä ja muodostavat niistä Markdown- ja CSV-raportit.

### 1. Preconditions / source data

Raporttien edellytys on, että ainakin seuraavat taulut on jo täytetty:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Legacy daily- ja rolling-raportit eivät tarkastetun koodin perusteella lue `dc_group_index_daily`-taulua suoraan. Sen vaikutus tulee epäsuorasti upstream-vaiheiden kautta, koska osa group-swing-kentistä on johdettu indeksitaulusta ennen raportointia.

Price DB:tä ei lueta suoraan raportin perusrenderöinnissä. OHLCV-data luetaan upstream-builder-vaiheissa, jotka ovat jo täyttäneet `dc_*`-taulut ennen raportointia.

Raportit lukevat kuitenkin raportoinnin aikana:

- `analysis.db`
- watchlist-tekstifilen
- optionaalisesti technical relevance -taulun, jos `--technical-relevance-run-id` annetaan

Taxonomy CSV:tä ei lueta raportin renderöintivaiheessa. Taxonomy-versio päätellään tai annetaan parametrina, ja raportti lukee datan `dc_*`-tauluista.

### 2. Report generation

Päiväraportti:

- CLI: `run_datacenter_daily_signal_report.py`
- writer-funktio: `write_daily_swing_signal_report(...)`
- datan lataus: `load_daily_swing_report_data(...)`
- Markdown-rakenne: `build_markdown_daily_swing_report(...)`
- CSV-rakenne: `build_csv_daily_swing_report(...)`

Rolling-raportit:

- yleinen weekly/rolling CLI: `run_datacenter_weekly_swing_report.py`
- erillinen rolling-wrapper: `run_datacenter_rolling_swing_report.py`
- writer-funktio: `write_weekly_swing_report(...)`
- datan lataus: `load_weekly_swing_report_data(...)`
- Markdown-rakenne: `build_markdown_weekly_swing_report(...)`
- CSV-rakenne: `build_csv_weekly_swing_report(...)`

Päiväraportti käyttää yhtä `signal_date`-päivää.

Rolling-raportit käyttävät `end_date`-päivää ja valitsevat siitä taaksepäin viimeiset N valid trading day -päivät, missä N on `window_size`.

### 3. Outputs

Kaikki legacy-raportit tuottavat:

- Markdown-tiedoston
- CSV-tiedoston

Pipeline-polussa käytetyt nimet ovat:

- `datacenter_daily_<signal_date>_full.md`
- `datacenter_daily_<signal_date>_full.csv`
- `datacenter_rolling_30_<signal_date>_full.md`
- `datacenter_rolling_30_<signal_date>_full.csv`
- `datacenter_rolling_5_<signal_date>_full.md`
- `datacenter_rolling_5_<signal_date>_full.csv`
- `datacenter_rolling_2_<signal_date>_full.md`
- `datacenter_rolling_2_<signal_date>_full.csv`

CLI lisää tiedostonimeen myös kellonajan `HHMM`, jos tiedostonimessä on päivämäärä. Siksi lopullinen tiedosto on käytännössä muotoa:

- `datacenter_daily_2026-05-15_1200_full.md`
- `datacenter_rolling_30_2026-05-15_1200_full.csv`

`run_datacenter_rolling_swing_report.py` osaa myös luoda oletusnimet automaattisesti, jos output-polkuja ei anneta.

Tarkastetun koodin perusteella nämä ovat full-variantteja. Erillistä kevyttä summary-outputia ei tuoteta omana tiedostomuotonaan näissä legacy-CLI-polkuissa.

### 4. Scheduler / pipeline integration

`run_datacenter_swing_pipeline.py` tuottaa legacy-raportit osana datacenter swing V1 -putkea, ellei `--skip-reports` ole käytössä.

Pipeline-vaiheet sisältävät erikseen:

- `daily_report`
- `rolling_30_report`
- `rolling_5_report`
- `rolling_2_report`

Lisäksi putki ajaa myös yhden geneerisen weekly-raportin (`datacenter_weekly_<date>_full.*`) parametrilla `--weekly-window-size`, mutta tämän dokumentin fokus on nimenomaan legacy `daily`, `rolling_30`, `rolling_5` ja `rolling_2` -raporteissa.

Scheduler-puolella legacy datacenter pipeline -raportit raportoidaan omana tulosryhmänään. Tarkastettu scheduler-koodi raportoi:

- `datacenter_pipeline.daily_report_path`
- `datacenter_pipeline.rolling_30_report_path`
- `datacenter_pipeline.rolling_5_report_path`
- `datacenter_pipeline.rolling_2_report_path`

Retired V3 scheduler/config/output compatibility fields have been removed. This supports the narrower current interpretation: legacy Datacenter reports are still active, but the old V3/eco report output surface is no longer a current scheduler output group.

## Report-by-report reference

### `datacenter_rolling_30`

Tarkoitus:

- tuottaa 30 valid trading day -ikkunan legacy rolling-raportti
- korostaa pidemmän ikkunan buy- ja exit-esiseulontaa watchlist-tasolla

Erotus muihin:

- eroaa `rolling_5`-raportista siinä, että se tuottaa `Rolling 30 Buy Filter`- ja `Rolling 30 Exit Prefilter` -osiot
- eroaa `rolling_2`-raportista siinä, että se ei keskity lyhyen aikavälin myyntipaineeseen
- eroaa `daily`-raportista siinä, että lähde on usean valid päivän ikkuna eikä yksi päivä

Koodipolku:

- `run_datacenter_rolling_swing_report.py --window-size 30`
- tai `run_datacenter_weekly_swing_report.py --window-size 30`
- molemmat päätyvät funktioon `write_weekly_swing_report(...)`
- varsinainen sisältö rakennetaan moduulissa `analysis.datacenter_indices.swing_weekly_report`

Lähdetaulut:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Pääsisältöä:

- window summary
- watchlist summary
- ecosystem window change
- overheat / rotation risk progression
- subindustry timing persistence
- subindustry improvement / deterioration
- repeated breakout / pullback / exit-risk tickers
- `Rolling 30 Buy Filter`
- `Rolling 30 Exit Prefilter`
- swing MA break status
- swing signal freshness
- data quality
- taxonomy listing, jos sitä ei ole poistettu parametrilla

Keskeiset kentät / metriikat:

- `rolling_30_buy_state`
- `rolling_30_exit_state`
- breakout / pullback / exit-risk päiväluennat
- viimeisimmät trendi-, structure-, BOS- ja RESET-kentät

Output-nimikaava:

- Markdown: `datacenter_rolling_30_<date>_<hhmm>_full.md`
- CSV: `datacenter_rolling_30_<date>_<hhmm>_full.csv`

Tunnetut caveatit:

- raportti käyttää valid trading day -ikkunaa, ei kalenterikuukautta
- jos `window_size`-päiviä ei löydy, raportti voi merkitä ikkunan epätäydelliseksi
- technical relevance on optionaalinen lisäkonteksti, ei raportin perusedellytys

### `datacenter_rolling_5`

Tarkoitus:

- tuottaa 5 valid trading day -ikkunan legacy rolling-raportti
- korostaa lyhyen swing-pullbackin alertteja

Erotus muihin:

- tuottaa erillisen `Rolling 5 Pullback Alerts` -osion
- ei sisällä `rolling_30`-buy/exit-esiseulontaa
- ei sisällä `rolling_2`-sell-pressure -osiota

Koodipolku:

- `run_datacenter_rolling_swing_report.py --window-size 5`
- tai `run_datacenter_weekly_swing_report.py --window-size 5`
- taustalla `write_weekly_swing_report(...)`

Lähdetaulut:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Pääsisältöä:

- samat yleiset window/watchlist/group/ticker-osat kuin weekly-pohjassa
- lisäksi `Rolling 5 Pullback Alerts`

Keskeiset kentät / metriikat:

- `rolling_5_pullback_state`
- `pullback_days`
- `fast_ema10_pullback_days`
- `conservative_ema20_pullback_days`
- viimeisimmät ticker- ja group-kontekstikentät

Output-nimikaava:

- Markdown: `datacenter_rolling_5_<date>_<hhmm>_full.md`
- CSV: `datacenter_rolling_5_<date>_<hhmm>_full.csv`

Tunnetut caveatit:

- `window_size=5` on erikoistapaus, joka aktivoi nimenomaan rolling-5-luokitusosion
- suurempi yleinen weekly-ikkuna, esimerkiksi 20, ei tuota tätä osiota

### `datacenter_rolling_2`

Tarkoitus:

- tuottaa 2 valid trading day -ikkunan legacy rolling-raportti
- korostaa hyvin lyhyen aikavälin myyntipainetta

Erotus muihin:

- tuottaa erillisen `Rolling 2 Sell Pressure` -osion
- ei sisällä rolling-30- tai rolling-5-erikoisosioita

Koodipolku:

- `run_datacenter_rolling_swing_report.py --window-size 2`
- tai `run_datacenter_weekly_swing_report.py --window-size 2`
- taustalla `write_weekly_swing_report(...)`

Lähdetaulut:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Pääsisältöä:

- samat yleiset window/watchlist/group/ticker-osat kuin weekly-pohjassa
- lisäksi `Rolling 2 Sell Pressure`

Keskeiset kentät / metriikat:

- `rolling_2_sell_pressure_state`
- `exit_risk_days`
- `high_exit_risk_days`
- viimeisimmät exit-, trendi-, BOS- ja RESET-kentät

Output-nimikaava:

- Markdown: `datacenter_rolling_2_<date>_<hhmm>_full.md`
- CSV: `datacenter_rolling_2_<date>_<hhmm>_full.csv`

Tunnetut caveatit:

- kyse on 2 valid trading day -ikkunasta, ei kahdesta kalenteripäivästä
- tämän raportin tarkoitus on varoitus-/paine-signaali, ei yleinen weekly-yhteenveto

### `datacenter_daily`

Tarkoitus:

- tuottaa yhden `signal_date`-päivän legacy daily swing -raportti
- esittää saman päivän ecosystem-, group- ja ticker-kontekstin ilman rolling-window-aggregointia

Erotus muihin:

- ei käytä usean päivän ikkunaa
- sisältää `Daily Triggers` -osion, joka on päiväraportin oma
- rolling-30/5/2-erikoisosiot eivät kuulu daily-raporttiin

Koodipolku:

- `run_datacenter_daily_signal_report.py`
- taustalla `write_daily_swing_signal_report(...)`
- sisältömoduuli `analysis.datacenter_indices.swing_daily_report`

Lähdetaulut:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Pääsisältöä:

- title and run metadata
- watchlist summary
- dashboard
- rotation risk / overheat index
- subindustry timing states
- buy-zone / add-on / trim-watch / exit-zone subindustry -osiot
- synthetic OHLC structure summary
- group structure breaks / resets
- breakout / pullback / exit-risk ticker scanner -osiot
- `Daily Triggers`
- swing MA break status
- swing signal freshness
- data quality
- missing / incomplete inputs summary
- taxonomy listing

Keskeiset kentät / metriikat:

- ticker scanner -kentät
- group timing / overheat
- synthetic structure / BOS / RESET
- `daily_trigger_state`

Output-nimikaava:

- Markdown: `datacenter_daily_<date>_<hhmm>_full.md`
- CSV: `datacenter_daily_<date>_<hhmm>_full.csv`

Tunnetut caveatit:

- raportti ei laske upstream-signaaleja uudelleen
- jos watchlist-tiedostoa ei löydy, raportti onnistuu silti ja watchlist-osio jää tyhjäksi

## Source table mapping

| Content area | Main source | Notes |
|---|---|---|
| ticker swing state / ticker observations | `dc_ticker_swing_signal_daily` | close, returnit, MA-etäisyydet, trendi, structure, BOS, RESET, breakout, pullback, exit-risk |
| group timing / group breadth | `dc_group_swing_signal_daily` | timing, overheat, breadth, returnit, data quality |
| synthetic OHLC / group structure / BOS / RESET | `dc_group_synthetic_ohlc_daily` | synthetic close, EMA-etäisyys, trend_classification, latest structure, BOS, RESET, relative OHLC |
| group index / benchmark-relative metrics | ei lueta suoraan legacy daily/rolling-renderöinnissä | vaikutus tulee upstream-vaiheista `dc_group_swing_signal_daily`-kenttien kautta |
| watchlist context | watchlist-tekstifile + `dc_ticker_swing_signal_daily` + `dc_group_swing_signal_daily` + `dc_group_synthetic_ohlc_daily` | watchlist-status rakennetaan renderöinnin aikana yhdistämällä watchlist ja `dc_*`-taulut |
| data quality / valid dates | `dc_group_swing_signal_daily`, `dc_ticker_swing_signal_daily`, `dc_group_synthetic_ohlc_daily` | rolling-raportti valitsee valid signal dates -päivät group-swing-taulusta |
| report metadata / run id | raportin parametrit + `dc_*`-taulujen kentät | Markdown-otsikon metakentät ja summary-rivit tulevat report writeristä; varsinaista erillistä report-run-taulua legacy-polku ei käytä |
| technical relevance companion fields | `technical_signal_relevance` optionaalisesti | käytössä vain jos `--technical-relevance-run-id` annetaan |

## What is calculated during report generation

Kaikki sisältö ei tule suoraan taulusta sellaisenaan. Legacy-raportit laskevat renderöinnin aikana ainakin seuraavia asioita:

- watchlist-yhteenvedot
- watchlist-status-luokitukset
- section-kohtaiset top-N-listat
- day-count- ja repeat-count-yhteenvedot rolling-raporteissa
- `rolling_30_buy_state`- ja `rolling_30_exit_state` -luokitukset
- `rolling_5_pullback_state` -luokitus
- `rolling_2_sell_pressure_state` -luokitus
- daily trigger -rivit
- swing MA break status -osio
- swing signal freshness -osio
- CSV-rakenne Markdownista sekä eräät lisätyt CSV-sektiot

Tärkeä tarkennus:

- nämä laskennat tapahtuvat raportointikerroksessa lukemalla jo persistoitua `dc_*`-dataa
- ne eivät muuta tietokantaa eivätkä korvaa upstream builder -vaiheita

## Markdown and CSV output formation

Markdown muodostetaan ensin.

Daily-polku:

- `build_markdown_daily_swing_report(...)`

Rolling-polku:

- `build_markdown_weekly_swing_report(...)`

CSV muodostetaan tämän jälkeen pääosin Markdownista:

- Markdown parsitaan riveiksi `_build_csv_rows_from_markdown(...)`
- CSV kirjoitetaan puolipiste-eroteltuna (`;`)
- perusotsikko on muotoa `section;value_1;value_2;...`

Lisäksi joitakin roolikohtaisia osioita lisätään CSV:hen erikseen ennen taxonomy listing -osiota, esimerkiksi:

- `daily_triggers`
- `rolling_30_buy_filter`
- `rolling_30_exit_prefilter`
- `rolling_5_pullback_alerts`
- `rolling_2_sell_pressure`
- `swing_ma_break_status`
- `swing_signal_freshness`
- optionaalisesti technical relevance -osio

Siksi CSV ei ole pelkkä suora taulukoitu versio Markdownista, vaan siihen injektoidaan joitakin lisäsektioita ohjelmallisesti.

## CLI and file naming reference

Manual daily:

```bash
python3 run_datacenter_daily_signal_report.py \
  --analysis-db data/analysis.db \
  --signal-date 2026-05-15 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --output-md swing_reports/datacenter_daily_2026-05-15_full.md \
  --output-csv swing_reports/datacenter_daily_2026-05-15_full.csv
```

Manual rolling 30:

```bash
python3 run_datacenter_rolling_swing_report.py \
  --analysis-db data/analysis.db \
  --end-date 2026-05-15 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --window-size 30 \
  --output-md swing_reports/datacenter_rolling_30_2026-05-15_full.md \
  --output-csv swing_reports/datacenter_rolling_30_2026-05-15_full.csv
```

Manual rolling 5:

```bash
python3 run_datacenter_rolling_swing_report.py \
  --analysis-db data/analysis.db \
  --end-date 2026-05-15 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --window-size 5 \
  --output-md swing_reports/datacenter_rolling_5_2026-05-15_full.md \
  --output-csv swing_reports/datacenter_rolling_5_2026-05-15_full.csv
```

Manual rolling 2:

```bash
python3 run_datacenter_rolling_swing_report.py \
  --analysis-db data/analysis.db \
  --end-date 2026-05-15 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --window-size 2 \
  --output-md swing_reports/datacenter_rolling_2_2026-05-15_full.md \
  --output-csv swing_reports/datacenter_rolling_2_2026-05-15_full.csv
```

## Legacy path versus V3 / `eco_*` path

Legacy-polku:

- lukee suoraan `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` ja `dc_group_synthetic_ohlc_daily`
- rakentaa osan luokituksista vasta raportin generoinnin aikana
- tuottaa legacy Markdown/CSV-raportit suoraan näistä lähteistä

Retired V3-polku:

- käytti erillisiä `eco_*`-tauluja
- ei ole enää current scheduler/CLI output -pinta
- ei ole tämän dokumentin pääaihe

Tarkastetun evidenssin perusteella legacy-raportit ovat edelleen aktiivisia ja ne nojaavat yhä `dc_*`-lähteisiin. Vanha V3/eco output -pinta ei ole enää rinnakkainen scheduler-output.

## Status assessment

- `datacenter_daily`: `active legacy report; runs alongside V3`
- `datacenter_rolling_30`: `active legacy report; runs alongside V3`
- `datacenter_rolling_5`: `active legacy report; runs alongside V3`
- `datacenter_rolling_2`: `active legacy report; runs alongside V3`

Epävarmuus:

- tuotannossa voi olla lisäksi muita geneerisiä weekly-ikkunoita, kuten `window_size=20`, mutta ne eivät ole tämän dokumentin varsinaista legacy-scopea
- V3-puolen nykyinen tuotantopaino suhteessa legacy-polkuun ei selviä pelkästään tarkastetuista tiedostoista

## Open questions

- Vahvistetaanko tuotantoajosta, että kaikki neljä legacy-raporttia syntyvät edelleen joka päivä normaalin scheduler-ajon yhteydessä?
- Ovatko Markdown- ja CSV-polut kaikissa tilanteissa samasta intermediate-mallista johdettuja, vai onko joissakin osioissa CSV:llä oma lisälogiikka?
- Onko mikään legacy-raportin osio jo siirtynyt lukemaan `eco_*`-tauluja, vai ovatko kaikki legacy-osiot edelleen `dc_*`-pohjaisia?
- Onko `run_datacenter_weekly_swing_report.py` enää tuotantopolussa olennainen vai käytetäänkö käytännössä `run_datacenter_rolling_swing_report.py`-wrapperia 30d/5d/2d-raportteihin?
- Ovatko kaikki rolling-ikkunat varmasti valid trading day -pohjaisia tuotantoraporteissa?
- Onko tiedostonimien kellonaikaleima aina deterministinen scheduler-ajossa vai ajonaikainen `HHMM`?

## Evidence inspected

### CLI entrypoints

- `run_datacenter_daily_signal_report.py`: varmisti daily-raportin CLI-parametrit, output-nimikaavan ja kutsun daily writeriin.
- `run_datacenter_weekly_swing_report.py`: varmisti geneerisen weekly/rolling-CLI:n parametrit ja sen, miten `window_size` ohjaa legacy rolling -raporttia.
- `run_datacenter_rolling_swing_report.py`: varmisti 30d/5d/2d-wrapperin oletuspolut, tiedostonimien muodostuksen ja delegoinnin weekly-writeriin.
- `run_datacenter_swing_pipeline.py`: varmisti, että legacy daily- ja rolling-raportit kuuluvat datacenter swing -putken raportointivaiheisiin.

### Legacy report builders / formatters

- `analysis/datacenter_indices/swing_daily_report.py`: varmisti daily-raportin datan latauksen, Markdown-rakenteen, CSV-rakenteen ja daily-kohtaiset osiot.
- `analysis/datacenter_indices/swing_weekly_report.py`: varmisti rolling-raporttien ikkunalogiikan, lähdetaulut, osiokohtaiset erot ja CSV-injektiot.
- `analysis/datacenter_indices/swing_ma_break_status.py`: varmisti, miten swing MA break status -osio muodostetaan raportointikerroksessa.
- `analysis/datacenter_indices/swing_signal_freshness.py`: varmisti, miten swing signal freshness -osio muodostetaan ja lisätään raportteihin.
- `analysis/datacenter_indices/technical_relevance_context.py`: varmisti optionaalisen technical relevance -lisäkontekstin lähteen ja kytkennän raportteihin.

### Pipeline / scheduler integration

- `analysis/datacenter_indices/swing_pipeline_orchestrator.py`: varmisti pipeline-vaiheiden nimet, legacy-output-polut ja raporttien ajon osana orkestrointia.
- `rawcandle/scheduler/runner.py`: varmisti, että scheduler tulkitsee legacy datacenter -raportit ja V3-raportit erillisinä tulosryhminä.
- `rawcandle/cli/run_stock_update_scheduler.py`: varmisti scheduler-CLI:n yhteenvedot ja sen, miten legacy- ja V3-raporttipolut näytetään erikseen.

### Tests

- `tests/test_run_datacenter_daily_signal_report_cli.py`: varmisti daily-CLI:n odotetut argumentit ja output-käyttäytymisen.
- `tests/test_run_datacenter_weekly_swing_report_cli.py`: varmisti geneerisen weekly-CLI:n argumentit ja rolling-ikkunoihin liittyvän käytön.
- `tests/test_run_datacenter_rolling_swing_report_cli.py`: varmisti rolling-wrapperin oletusnimet ja window-size-kohtaisen output-logiikan.
- `tests/test_datacenter_swing_pipeline_smoke.py`: varmisti, että pipeline-smoke kattaa legacy-raporttien tuotannon osana putkea.
- `tests/test_stock_update_scheduler_ui.py`: varmisti scheduler-UI:n näkyvät legacy-raporttipolut ja niiden erottelun V3-raporteista.

### Existing docs

- `docs/datacenter_swing_signal_runbook.md`: tarjosi olemassa olevan käyttö- ja ajokontekstin datacenter swing -raporteille.
- `docs/archive/canonical_report_v2/datacenter_report_canonical_v2_architecture.md`: tarjosi historiallista taustakontekstia vanhemman raporttiarkkitehtuurin rakenteesta ja käsitteistä.
- `docs/datacenter_dc_tables_reference.md`: tarjosi erillisen viitteen legacy-raporttien käyttämien `dc_*`-taulujen rooleihin.
