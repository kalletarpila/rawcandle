# Ecosystem V3 report generation reference

## Purpose of this document

Tämä dokumentti kuvaa, miten V3 ecosystem `daily`, `rolling30`, `rolling5` ja `rolling2` Markdown-raportit muodostetaan `eco_*`-tauluista, mitä CLI- ja Python-koodipolkuja ne käyttävät ja miten ne eroavat legacy Datacenter `dc_*` -raporteista.

Tämä dokumentti keskittyy raporttien renderöintipolkuun. V3 `eco_*` -taulujen skeema, merkitys ja lineage on kuvattu erikseen dokumentissa [docs/ecosystem_v3_eco_tables_reference.md](/home/kalle/projects/rawcandle/docs/ecosystem_v3_eco_tables_reference.md).

Vertailukontekstina legacy-polku on kuvattu dokumenteissa [docs/datacenter_legacy_report_generation_reference.md](/home/kalle/projects/rawcandle/docs/datacenter_legacy_report_generation_reference.md) ja [docs/datacenter_dc_tables_reference.md](/home/kalle/projects/rawcandle/docs/datacenter_dc_tables_reference.md).

## Scope

Tämä dokumentti kattaa:

- V3 `daily`
- V3 `rolling30`
- V3 `rolling5`
- V3 `rolling2`

Tämä dokumentti ei kata:

- legacy `dc_*` -raporttien sisäistä muodostusta muuten kuin vertailuna
- `eco_*`-taulujen yksityiskohtaista skeemadokumentaatiota
- dashboard-UI:n muodostusta
- uutta dashboard-designia
- upstream V3 builderien sisäistä laskentaa muuten kuin raporttien esivaatimuksena

## Executive summary

| Report | Window code | Main CLI / entrypoint | Main query/writer modules | Main `eco_*` source tables | Output file pattern | Status / role |
|---|---|---|---|---|---|---|
| V3 `daily` | `daily` | `rawcandle/cli/write_latest_v3_markdown_reports.py` tai `rawcandle/cli/write_v3_markdown_prototypes.py` | `rawcandle.reporting_v3_query`, `rawcandle.reporting_v3_markdown` | `eco_report_run`, `eco_entity`, `eco_taxonomy_entity_relation`, `eco_watchlist`, `eco_watchlist_member`, `eco_entity_coverage`, `eco_quality_summary`, `eco_entity_window_snapshot`, `eco_entity_metric_value`, `eco_classification_decision`, `eco_signal_observation`, `eco_signal_relevance`, `eco_entity_event` | `datacenter_v3_daily_<signal_date>.md` | active V3 report; runs alongside legacy |
| V3 `rolling30` | `rolling30` | `rawcandle/cli/write_latest_v3_markdown_reports.py` tai `rawcandle/cli/write_v3_markdown_prototypes.py` | `rawcandle.reporting_v3_query`, `rawcandle.reporting_v3_markdown` | samat ydintaulut kuin daily, mutta `rolling30`-ikkunalla | `datacenter_v3_rolling30_<signal_date>.md` | active V3 report; runs alongside legacy |
| V3 `rolling5` | `rolling5` | `rawcandle/cli/write_latest_v3_markdown_reports.py` tai `rawcandle/cli/write_v3_markdown_prototypes.py` | `rawcandle.reporting_v3_query`, `rawcandle.reporting_v3_markdown` | samat ydintaulut kuin daily, mutta `rolling5`-ikkunalla | `datacenter_v3_rolling5_<signal_date>.md` | active V3 report; runs alongside legacy |
| V3 `rolling2` | `rolling2` | `rawcandle/cli/write_latest_v3_markdown_reports.py` tai `rawcandle/cli/write_v3_markdown_prototypes.py` | `rawcandle.reporting_v3_query`, `rawcandle.reporting_v3_markdown` | samat ydintaulut kuin daily, mutta `rolling2`-ikkunalla | `datacenter_v3_rolling2_<signal_date>.md` | active V3 report; runs alongside legacy |

## V3 report generation flow

V3 Markdown -raportit ovat read-only-renderöijiä `eco_*`-taulujen yli. Ne eivät tarkastetun koodin perusteella kirjoita takaisin `eco_*`-tauluihin eivätkä luo uusia `eco_report_run`-rivejä. Varsinainen V3 data rakennetaan ensin erillisellä build-polulla, jonka jälkeen raporttien CLI valitsee sopivan `eco_report_run`-ajon ja renderöi siitä Markdownit.

### 1. Preconditions / source data

Raporttien renderöinti edellyttää, että ainakin seuraavat `eco_*`-taulut ovat olemassa ja täytetty:

- `eco_report_run`
- `eco_entity`
- `eco_taxonomy_entity_relation`
- `eco_watchlist`
- `eco_watchlist_member`
- `eco_entity_coverage`
- `eco_quality_summary`
- `eco_entity_window_snapshot`
- `eco_entity_metric_value`
- `eco_classification_decision`
- `eco_signal_observation`
- `eco_signal_relevance`
- `eco_entity_event`
- `eco_report_window`
- `eco_ecosystem`
- `eco_taxonomy_version`

`rawcandle/reporting_v3_query.py` tarkistaa nämä taulut eksplisiittisesti `REQUIRED_TABLES`-listalla.

Tarkastetun renderöintikoodin perusteella V3 Markdown -raportit lukevat report generation -vaiheessa `eco_*`-tauluja, eivät legacy `dc_*` -tauluja suoraan. Legacy-riippuvuus on tässä vaiheessa epäsuora: osa `eco_*`-tauluista on yhä upstream-buildereissä täytetty transitional `dc_*`-lähteistä.

Price DB:tä ei tarkastetun V3 report render -polun perusteella lueta suoraan raportoinnin aikana.

Taxonomy CSV:tä tai watchlist TXT -tiedostoa ei tarkastetun V3 report render -polun perusteella lueta suoraan raportoinnin aikana. Niiden vaikutus tulee aiemmin materialisoitujen `eco_*` master data -taulujen kautta.

### 2. Report run selection

Latest-run-valinta tapahtuu CLI:ssä `rawcandle/cli/write_latest_v3_markdown_reports.py`.

Valintalogiikka:

- suodattaa `eco_report_run`-rivejä `ecosystem_code`-arvolla
- suodattaa `taxonomy_version_code`-arvolla
- suodattaa sallituilla status-arvoilla
- suodattaa optionaalisesti eksplisiittisellä `signal_date`-parametrilla
- järjestää tulokset:
  - `signal_date DESC`
  - `COALESCE(created_at_utc, '') DESC`
  - `run_id DESC`
- valitsee `LIMIT 1`

Oletusstatusfiltteri on `OK,OK_WITH_WARNINGS`.

Raportit voidaan generoida:

- eksplisiittisellä `run_id`:llä käyttämällä `rawcandle/cli/write_v3_markdown_prototypes.py`
- uusimmalla matching-runilla käyttämällä `rawcandle/cli/write_latest_v3_markdown_reports.py`
- schedulerin kautta, joka ensin resolvoi latest-runin ja kutsuu sitten writeria

### 3. Report generation

Kaksi pää-CLI-polkuja:

- `rawcandle/cli/write_latest_v3_markdown_reports.py`
  - valitsee latest matching `eco_report_run`-ajon
  - kutsuu `write_reports(...)`
- `rawcandle/cli/write_v3_markdown_prototypes.py`
  - ottaa eksplisiittisen `--run-id`-parametrin
  - kutsuu horizon-kohtaisia query builder -funktioita
  - renderöi niiden tulokset Markdowniksi

Horizon-valinta:

- `rolling30` -> `build_rolling30_report_query_data(...)` + `render_rolling30_markdown_report(...)`
- `rolling5` -> `build_rolling5_report_query_data(...)` + `render_rolling5_markdown_report(...)`
- `rolling2` -> `build_rolling2_report_query_data(...)` + `render_rolling2_markdown_report(...)`
- `daily` -> `build_daily_report_query_data(...)` + `render_daily_markdown_report(...)`

Writer käyttää yhtä yhteistä orchestrator-polkuja, mutta erillisiä query builder -funktioita ja render-wrapper-funktioita per horizon. Varsinainen Markdown-kokoonpano tapahtuu yhteisessä `rawcandle/reporting_v3_markdown.py`-moduulissa.

### 4. Outputs

Tarkastetun koodin perusteella V3 report render -polku tuottaa:

- Markdown-tiedostoja

Tarkastetun koodin perusteella se ei tuota:

- CSV-tiedostoja

Tarkastetun writer-polun perusteella ei ole erillisiä full/summary-variantteja. Output on yksi Markdown per horizon.

Nimikaava muodostuu `rawcandle/cli/write_v3_markdown_prototypes.py`-funktiossa `_filename_for(...)`:

- `<ecosystem_code lower>_v3_<window_code>_<signal_date>.md`

Datacenter-esimerkit:

- `datacenter_v3_daily_2026-06-04.md`
- `datacenter_v3_rolling30_2026-06-04.md`
- `datacenter_v3_rolling5_2026-06-04.md`
- `datacenter_v3_rolling2_2026-06-04.md`

### 5. Scheduler / pipeline integration

Scheduler-integraatio on tarkastetun koodin perusteella erillinen legacy datacenter pipeline -polusta.

`rawcandle/scheduler/runner.py`:

- ajaa legacy datacenter pipeline -raportit ensin
- yrittää tämän jälkeen ajaa V3 Markdown -raportit, jos `datacenter_v3_reports_enabled` on päällä
- resolvoi latest-runin `resolve_latest_run(...)`-funktiolla
- kirjoittaa raportit `write_reports(...)`-funktiolla

Schedulerin tulosmallissa legacy- ja V3-raportit kulkevat erillisinä kenttinä:

- `datacenter_pipeline.*`
- `v3_reports.*`

V3 report generation voidaan tarkastetun runner-koodin perusteella:

- ottaa käyttöön tai pois päältä konfiguraatiolla `datacenter_v3_reports_enabled`
- ohjata omaan output base dir -hakemistoon `datacenter_v3_reports_output_dir`
- rajata tiettyyn ecosystem- ja taxonomy-version -pariin konfiguraatiolla

## Report-by-report reference

### V3 `daily`

Tarkoitus:

- tuottaa yhden `signal_date`-päivän V3 Markdown -raportti
- näyttää saman päivän ecosystem-, group-, ticker-, classification-, signal- ja quality-kontekstin `eco_*`-tauluista

Window code:

- `daily`

Erotus rolling-raportteihin:

- käyttää yhtä päivää, ei monen päivän ikkuna-summarya
- sisältää daily-kohtaiset ticker scanner -osiot
- sisältää `Daily Triggers` -classification-osion

Koodipolku:

- latest-polku: `rawcandle/cli/write_latest_v3_markdown_reports.py`
- explicit-run-polku: `rawcandle/cli/write_v3_markdown_prototypes.py`
- query builder: `build_daily_report_query_data(...)`
- Markdown renderer: `render_daily_markdown_report(...)`

Pääasialliset `eco_*`-lähteet:

- `eco_report_run`
- `eco_watchlist`, `eco_watchlist_member`
- `eco_taxonomy_entity_relation`
- `eco_entity_coverage`
- `eco_quality_summary`
- `eco_entity_window_snapshot`
- `eco_entity_metric_value`
- `eco_classification_decision`
- `eco_signal_observation`
- `eco_signal_relevance`
- `eco_entity_event`

Pääosiot tarkastetun renderer-koodin perusteella:

- title and run metadata
- Watchlist Summary
- Dashboard
- Rotation Risk / Overheat Index
- Subindustry Timing States
- Buy-Zone Subindustries
- Add-On Pullback Subindustries
- Trim/Watch Subindustries
- Exit-Zone Subindustries
- Synthetic OHLC Structure Summary
- Group Structure Breaks / Resets
- Breakout Ticker Scanner
- Pullback Ticker Scanner
- Exit-Risk Ticker Scanner
- Daily Triggers
- Swing MA Break Status
- Swing Signal Freshness
- Data Quality
- Missing / Incomplete Inputs Summary
- Technical Relevance Context
- V3 metadata / limitations appendix

Keskeiset kentät / sisällöt:

- `daily_trigger`-classificationit `eco_classification_decision`-taulusta
- ticker daily -metriikat kuten `return_5d`, `return_10d`, `distance_to_ema20_pct`
- snapshot trend/summary/freshness/quality
- signal observationit erityisesti `MA_STATUS`- ja `FRESHNESS`-perheistä
- structural events group- ja ecosystem-tasolla

Output-nimikaava:

- `datacenter_v3_daily_<signal_date>.md`

Tunnetut caveatit:

- rendererissä on näkyviä limitation-rivejä kuten “Full legacy dashboard aggregation is not available from current V3 query data”
- daily Technical Relevance Context näkyy vain, jos relevance-label-rivejä on saatavilla `eco_signal_relevance`-polun kautta

### V3 `rolling30`

Tarkoitus:

- tuottaa 30 päivän V3 rolling Markdown -raportti
- korostaa pidemmän ikkunan watchlist-, classification-, progression- ja ecosystem window change -kontekstia

Window code:

- `rolling30`

Erotus muihin:

- käyttää rolling-ikkuna-summarya ja valid signal dates -listaa
- sisältää `rolling30_buy`- ja `rolling30_exit` -classification-osiot
- korostaa pidemmän horizonin change/progression-näkymiä

Koodipolku:

- query builder: `build_rolling30_report_query_data(...)`
- renderer: `render_rolling30_markdown_report(...)`

Pääasialliset `eco_*`-lähteet:

- `eco_report_run`
- `eco_entity_window_snapshot`
- `eco_classification_decision`
- `eco_entity_metric_value`
- `eco_watchlist` / `eco_watchlist_member`
- `eco_quality_summary`
- `eco_entity_coverage`
- `eco_entity_event`
- `eco_signal_observation`
- `eco_taxonomy_entity_relation`

Pääosiot tarkastetun renderer-koodin perusteella:

- Title and run metadata
- Window summary
- Watchlist Summary
- Ecosystem window change
- Overheat / rotation risk progression
- Subindustry timing persistence
- Subindustry improvement / deterioration
- Repeated breakout tickers
- Repeated pullback tickers
- Repeated exit-risk tickers
- `Rolling 30 Buy Filter`
- `Rolling 30 Exit Prefilter`
- Data quality over the window
- Missing / incomplete inputs summary
- V3 metadata / limitations appendix
- Structural events
- Signal observations

Keskeiset kentät / sisällöt:

- `rolling30_buy` ja `rolling30_exit` classificationit
- rolling ticker -metriikat kuten `breakout_days`, `pullback_days`, `exit_risk_days`, `valid_signal_dates`
- rolling group -metriikat kuten `group_timing_state`, `group_overheat_risk_level`, `pct_above_ema20`
- structural events ja signal observations ikkunakontekstissa

Output-nimikaava:

- `datacenter_v3_rolling30_<signal_date>.md`

Tunnetut caveatit:

- classification_source tulee rendererin metadata-liitteessä erikseen `eco_classification_decision`-taulusta
- snapshotin `classification_state` ei ole ensisijainen source tämän horizonin classificationeille

### V3 `rolling5`

Tarkoitus:

- tuottaa 5 päivän V3 rolling Markdown -raportti
- korostaa lyhyen aikavälin pullback-kontekstia

Window code:

- `rolling5`

Erotus muihin:

- käyttää `rolling5_pullback`-classification-osiota
- ei sisällä rolling30 buy/exit -esiseulontaa
- on lyhyempi swing-ikkuna kuin rolling30

Koodipolku:

- query builder: `build_rolling5_report_query_data(...)`
- renderer: `render_rolling5_markdown_report(...)`

Pääasialliset `eco_*`-lähteet:

- samat ydintaulut kuin rolling30, mutta `rolling5`-ikkunan riveillä

Pääosiot tarkastetun renderer-koodin perusteella:

- sama rolling-shell-rakenne kuin rolling30-raportissa
- horizon-kohtaisena classification-osiona `Rolling 5 Pullback Alerts`

Keskeiset kentät / sisällöt:

- `rolling5_pullback`-classificationit
- rolling 5 -ikkunan ticker- ja group-metriikat
- rolling-window summary ja watchlist summary

Output-nimikaava:

- `datacenter_v3_rolling5_<signal_date>.md`

Tunnetut caveatit:

- rolling-shell-renderer on yhteinen muiden rolling-horizonien kanssa, joten osa otsikkorakenteesta on jaettua eikä täysin horizon-kohtaisesti eriytettyä

### V3 `rolling2`

Tarkoitus:

- tuottaa 2 päivän V3 rolling Markdown -raportti
- korostaa hyvin lyhyen aikavälin sell-pressure- ja exit-risk-kontekstia

Window code:

- `rolling2`

Erotus muihin:

- käyttää `rolling2_sell_pressure`-classification-osiota
- fokus on lyhyessä varoitusikkunassa, ei pidemmän trendin progressiossa

Koodipolku:

- query builder: `build_rolling2_report_query_data(...)`
- renderer: `render_rolling2_markdown_report(...)`

Pääasialliset `eco_*`-lähteet:

- samat ydintaulut kuin rolling30- ja rolling5-raporteissa, mutta `rolling2`-ikkunan riveillä

Pääosiot tarkastetun renderer-koodin perusteella:

- sama rolling-shell-rakenne kuin muissa rolling-raporteissa
- horizon-kohtaisena classification-osiona `Rolling 2 Sell Pressure`

Keskeiset kentät / sisällöt:

- `rolling2_sell_pressure`-classificationit
- rolling ticker -päivälaskennat
- watchlist severity -järjestys

Output-nimikaava:

- `datacenter_v3_rolling2_<signal_date>.md`

Tunnetut caveatit:

- rolling2 käyttää samaa yleistä writer-shelliä kuin muutkin rolling-raportit, joten osa esitysmuodosta on yhteinen eikä ప్రత్యేకisesti rolling2:lle räätälöity

## Source table mapping

| Report content area | Main `eco_*` source table(s) | Used by which V3 reports | Notes / uncertainty |
|---|---|---|---|
| report header / run metadata | `eco_report_run`, `eco_ecosystem`, `eco_taxonomy_version` | kaikki | confirmed |
| entity hierarchy / taxonomy context | `eco_taxonomy_entity_relation`, `eco_entity` | kaikki | confirmed |
| watchlist context | `eco_watchlist`, `eco_watchlist_member`, `eco_entity` | kaikki | confirmed |
| snapshots / summary states | `eco_entity_window_snapshot`, `eco_entity` | kaikki | confirmed |
| metric values | `eco_entity_metric_value`, `eco_entity` | kaikki | confirmed |
| coverage and quality | `eco_entity_coverage`, `eco_quality_summary`, `eco_entity` | kaikki | confirmed |
| signal observations | `eco_signal_observation`, `eco_entity` | kaikki | confirmed |
| signal relevance | `eco_signal_relevance` yhdessä `eco_signal_observation`-taulun kanssa | daily varmasti, rollingit mahdollisesti signal-observation-liitteessä | relevance näkyy eksplisiittisesti daily-taulukoissa; rolling-puolella signal-riveihin voi tulla relevance-labeleitä, mutta käyttö on vähäisempi |
| entity events / BOS / RESET / structure | `eco_entity_event`, `eco_entity` | kaikki | confirmed |
| classification decisions | `eco_classification_decision`, `eco_entity` | kaikki | confirmed |
| freshness fields | `eco_entity_window_snapshot`, `eco_entity_metric_value`, `eco_signal_observation` | kaikki | confirmed |
| rolling window summaries | `eco_entity_metric_value`, `eco_entity_window_snapshot`, `eco_report_run` | rolling30, rolling5, rolling2 | confirmed |
| ticker sections | `eco_entity_metric_value`, `eco_entity_window_snapshot`, `eco_classification_decision`, `eco_signal_observation`, `eco_entity_coverage` | kaikki | confirmed |
| group/layer/subindustry sections | `eco_entity_metric_value`, `eco_entity_window_snapshot`, `eco_entity_event`, `eco_taxonomy_entity_relation` | kaikki | confirmed |

## What is calculated during V3 report rendering

Tarkastetun koodin perusteella merkittävä osa sisältöarvoista tulee valmiiksi materialisoituina `eco_*`-tauluista, mutta query- ja render-kerros laskee silti useita johdettuja esitysrakenteita.

Valmiiksi `eco_*`-tauluissa olevia arvoja:

- snapshot state -kentät
- metric-arvot
- coverage- ja quality-rivit
- classification-state- ja reason-rivit
- signal observation -rivit
- signal relevance -rivit
- entity event -rivit

`rawcandle/reporting_v3_query.py`-tasolla lasketaan tai johdetaan ainakin:

- horizon-kohtainen run header
- watchlist summaryn countit
- watchlist severity/status -luokitukset renderiä varten
- taxonomy-polusta johdetut `primary_layer` / `primary_subindustry`
- rolling window summary
- ecosystem window change -payloadit
- overheat / rotation risk progression -payloadit
- subindustry timing persistence -payloadit
- subindustry improvement / deterioration -payloadit
- daily ticker scanner -listat
- truncation-, sorting- ja stratified selection -käyttäytyminen
- metadata / limitations -liitteiden kenttiä

`rawcandle/reporting_v3_markdown.py`-tasolla lasketaan tai tehdään ainakin:

- osioiden lopullinen järjestys
- taulukoiden renderöinti Markdown-taulukoiksi
- fallback-tekstit kuten “Not available from current V3 query data...”
- state-count-listat classification-osioihin
- horizon-kohtaisten osioiden valinta yhteisestä rolling-shellistä

Selvä rajanveto:

- `eco_*` sisältää datafaktit
- `reporting_v3_query.py` muodostaa raportin read-modelin
- `reporting_v3_markdown.py` muodostaa lopullisen Markdown-tekstin

## Markdown output generation

Markdown assembled:

- query-data rakennetaan `rawcandle/reporting_v3_query.py`-moduulissa
- Markdown assembled `rawcandle/reporting_v3_markdown.py`-moduulissa
- tiedostoksi kirjoitus tapahtuu `rawcandle/cli/write_v3_markdown_prototypes.py`-moduulissa

CSV:

- tarkastetun V3 report writer -polun perusteella CSV:tä ei generoida

Shared writer vai per-window writer:

- V3 raportit käyttävät yhtä yhteistä writer-orchestration-polkuja
- query builderit ovat horizon-kohtaisia
- render wrapperit ovat horizon-kohtaisia
- varsinainen shell-rendereri on suurelta osin yhteinen, erityisesti rolling-raporteissa

Section ordering:

- section ordering on hard-coded rendererissä

Filename behavior:

- sisältää `ecosystem_code`-arvon pienillä kirjaimilla
- sisältää `v3`
- sisältää `window_code`
- sisältää `signal_date`
- ei sisällä `run_id`:tä
- ei sisällä timestampia

Naming style suhteessa legacyyn:

- legacy käyttää muotoa `datacenter_<legacy_name>_<date>_<hhmm>_full.md` ja tuottaa myös CSV:t
- V3 käyttää muotoa `datacenter_v3_<window>_<date>.md` eikä tarkastetun koodin perusteella lisää `HHMM`-suffiksia

## Manual commands

V3 data build:

```bash
python3 -m rawcandle.cli.run_canonical_v3_latest_build \
  --db <ANALYSIS_DB> \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --signal-date <SIGNAL_DATE> \
  --run-id <RUN_ID> \
  --confirm-run-id <RUN_ID> \
  --backup-dir <BACKUP_DIR> \
  --format text
```

V3 Markdownit eksplisiittiselle `run_id`:lle:

```bash
python3 -m rawcandle.cli.write_v3_markdown_prototypes \
  --db <ANALYSIS_DB> \
  --run-id <RUN_ID> \
  --out-dir <OUTPUT_DIR>
```

V3 Markdownit latest matching-runille:

```bash
python3 -m rawcandle.cli.write_latest_v3_markdown_reports \
  --db <ANALYSIS_DB> \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --out-dir <OUTPUT_DIR> \
  --format text
```

Yksittäinen horizon:

```bash
python3 -m rawcandle.cli.write_v3_markdown_prototypes \
  --db <ANALYSIS_DB> \
  --run-id <RUN_ID> \
  --out-dir <OUTPUT_DIR> \
  --only rolling30
```

## Scheduler / pipeline integration

Tarkastetun evidenssin perusteella normaali scheduler voi tuottaa V3 Markdown -raportit.

Keskeinen polku:

- `rawcandle/scheduler/runner.py`
  - `resolve_latest_run(...)`
  - `write_reports(...)`
- `rawcandle/cli/run_stock_update_scheduler.py`
  - tulostaa `SUMMARY v3_reports.*`-kentät erillään legacy `datacenter_pipeline.*` -kentistä

Vahvistetut havainnot:

- V3-report generation on erikseen enable/disable konfiguroitavissa kentällä `datacenter_v3_reports_enabled`
- scheduler voi ajaa legacy- ja V3-raportit side by side
- jos V3 latest-runia ei löydy tai writer epäonnistuu, legacy-datacenter pipeline voi silti onnistua ja scheduler raportoi V3-puolen varoituksena/virheenä
- scheduler käyttää V3-output-hakemistona joko konfiguroitua base-dir:iä tai oletuksena datacenter-output-dir `/v3`-alihakemistoa
- scheduler rakentaa lopullisen output-polun muodossa:
  - `<base_output_dir>/<ecosystem_code lower>/<signal_date>/`

Tarkastetuista scheduler-testeistä ei löytynyt viitteitä siihen, että V3 Markdown -renderöinti lukisi suurta OHLCV price DB:tä suoraan. Schedulerin V3 report -testit mockkaavat resolver- ja writer-kutsut eikä raporttipolku skannaa tuotannon OHLCV-DB:tä.

## Relationship to legacy reports

V3-raportit eivät ole legacy `dc_*` -raportteja.

Tarkastetun evidenssin perusteella:

- V3 report rendering lukee `eco_*`-tauluja query-layerin kautta
- legacy report rendering lukee suoraan `dc_*`-tauluja
- V3 report rendering ei tarkastetussa render-polussa lue `dc_*`-tauluja suoraan
- mutta monet `eco_*`-taulut on upstream-vaiheessa edelleen täytetty transitional `dc_*`-lähteistä

Tästä seuraa:

- `dc_*`-taulujen poistaminen liian aikaisin voi rikkoa V3 builderit
- mutta tarkastetun evidenssin perusteella itse V3 Markdown render -vaihe on jo `eco_*`-only

Nykyinen tuotantorooli näyttää olevan:

- legacy-raportit ovat edelleen aktiivisia
- V3-raportit ovat myös aktiivisia
- scheduler käsittelee niitä rinnakkaisina output-ryhminä

## Current status and risks

Lyhyt arvio tarkastetun evidenssin perusteella:

- V3 Markdown -raportit ovat aktiivisia
- ne tuotetaan edelleen legacy-raporttien rinnalla, jos scheduler-konfiguraatio sallii sen
- render-vaihe näyttää olevan `eco_*`-sourced
- upstream V3 facts ovat silti edelleen osin transitional `dc_*`-riippuvaisia

Jos `dc_*`-taulut poistettaisiin liian aikaisin, todennäköisesti rikkoutuisivat ainakin:

- V3 latest build -polun metric-builderit
- classification-builderit
- snapshot-builderi
- osa signal- ja group-event-builder-polusta

Mitä ei nykyisestä evidenssistä voi väittää liian vahvasti:

- täydellinen parity legacy-raporttien kanssa
- kaikkien rolling-ikkunoiden täsmällinen valid trading day -semantiikka pelkän render-koodin perusteella
- se, tuleeko V3-raporttien rinnakkaisajo jäämään pitkäaikaiseksi tuotantokäytännöksi

## Evidence inspected

### V3 report CLIs / entrypoints

- `rawcandle/cli/write_latest_v3_markdown_reports.py`: varmisti latest matching `eco_report_run` -ajon valinnan sekä ecosystem/taxonomy/status/signal-date -filtterit.
- `rawcandle/cli/write_v3_markdown_prototypes.py`: varmisti eksplisiittisen `run_id`-polun, horizon-valinnan, tiedostonimikaavan ja Markdown-tiedostojen kirjoituksen.

### V3 query layer / report writers

- `rawcandle/reporting_v3_query.py`: varmisti mitä `eco_*`-tauluja raportit lukevat, miten query-data rakennetaan per horizon ja mitä johdettuja yhteenvetoja renderöintiä varten lasketaan.
- `rawcandle/reporting_v3_markdown.py`: varmisti osiojärjestyksen, daily- ja rolling-shellin, Markdown-taulukoiden kokoonpanon ja sen, ettei CSV:tä tuoteta tällä polulla.

### V3 build prerequisites

- `rawcandle/cli/run_canonical_v3_latest_build.py`: varmisti, että V3 Markdown -raportit nojaavat erikseen rakennettuun `eco_report_run`-ajoon eivätkä itse rakenna upstream-faktatauluja.
- `rawcandle/cli/plan_canonical_v3_latest_build.py`: varmisti taustakontekstin siitä, että monet nykyiset `eco_*`-taulut täyttyvät edelleen transitional `dc_*`-lähteistä.
- `docs/ecosystem_v3_eco_tables_reference.md`: tarjosi taustakontekstin `eco_*`-taulujen rooleille ja transitional lineage -riippuvuuksille.

### Scheduler / pipeline integration

- `rawcandle/scheduler/runner.py`: varmisti, että scheduler ajaa V3 report generation -vaiheen erillään legacy-pipeline-vaiheesta ja että output-hakemisto muodostuu ecosystem/signal-date -rakenteella.
- `rawcandle/cli/run_stock_update_scheduler.py`: varmisti, että scheduler tulostaa `v3_reports.*`-summary-kentät erillään `datacenter_pipeline.*`-kentistä.

### Tests

- `tests/test_write_latest_v3_markdown_reports_cli.py`: varmisti latest-run-valinnan järjestyksen, statusfiltterin, signal-date-filtterin ja sen, että writer saa oikean `run_id`:n.
- `tests/test_write_v3_markdown_prototypes_cli.py`: varmisti kaikkien neljän horizonin tiedostonimet, kirjoitusjärjestyksen, `--only`-rajauksen ja overwrite-käyttäytymisen.
- `tests/test_reporting_v3_daily_query.py`: varmisti daily query-datan minimirakenteen ja sen, mitä `eco_*`-tauluja daily-polku odottaa.
- `tests/test_reporting_v3_rolling30_query.py`: varmisti rolling30 query-datan minimirakenteen ja rolling-puolen ikkunakohtaiset payloadit.
- `tests/test_stock_update_scheduler_runner.py`: varmisti, että scheduler voi ajaa legacy- ja V3-raportit rinnakkain, että V3 voidaan disabloida ja että V3-virheet eivät automaattisesti poista legacy-outputeja.
- `tests/test_stock_update_scheduler_cli.py`: varmisti, että CLI raportoi `v3_reports.*`-summary-kentät erikseen ja näkyvästi.

### Existing docs

- `docs/ecosystem_v3_eco_tables_reference.md`: tarjosi V3-taulujen lineage- ja statuskontekstin raporttirenderöinnin taustaksi.
- `docs/datacenter_legacy_report_generation_reference.md`: tarjosi vertailukohdan legacy daily/rolling Markdown+CSV -polulle.
- `docs/datacenter_dc_tables_reference.md`: tarjosi legacy `dc_*` -taulujen merkityskontekstin transitional riippuvuuksien arviointiin.

### Sample outputs

- `temp/v3_latest_wrapper_smoke_20260606_signal_date_072500/datacenter_v3_daily_2026-06-04.md`: varmisti daily-rendererin otsikkorakenteen ja esimerkkiosioiden toteutuneen ulostulon.
- `temp/v3_latest_wrapper_smoke_20260606_signal_date_072500/datacenter_v3_rolling30_2026-06-04.md`: varmisti rolling30-rendererin otsikkorakenteen, window summaryn ja tiedostonimen toteutuneen ulostulon.

### Lightweight DB inspection

- `data/analysis.db`: varmisti nykyiset `eco_report_run`-rivit, joita latest-run resolver voi valita.

## Open questions

- Ovatko kaikki nykyiset V3 report sections varmasti täysin `eco_*`-sourced render-vaiheessa vai onko jokin reunaosio edelleen epäsuorasti sidottu johonkin muuhun query helperiin, jota tämä rajattu tarkastus ei osunut?
- Onko CSV:n puuttuminen V3 report writer -polusta lopullinen tavoitetila vai vain nykyinen vaiheistus?
- Ovatko kaikkien rolling-horizonien `window_start_date` ja `valid_signal_dates_included` varmasti kaikissa build-polun versioissa valid trading day -pohjaisia?
- Onko schedulerissä tarkoitus pitää V3 ja legacy side by side pitkään vai onko tämä vain siirtymävaiheen tuotantotila?
- Kuinka täydellinen osiopariteetti V3 daily/rolling -raporteilla on suhteessa legacy daily/rolling -raportteihin?
- Kirjoittaako jokin muu, tämän tarkastuksen ulkopuolelle jäänyt tuotantopolku report-renderöinnin yhteydessä metadataa takaisin `eco_report_run`-tauluun, vai onko current evidence todella täysin read-only renderöinnin puolella?
