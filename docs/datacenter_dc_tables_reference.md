# Datacenter `dc_` tables reference

## Purpose of this document

Tämä dokumentti kuvaa valitut `dc_`-taulut tiedostossa `data/analysis.db`: mitä ne sisältävät, miten ne muodostetaan, miten ne liittyvät datacenter swing -putkeen ja miten ne suhteutuvat uudempiin V3 / `eco_*` -rakenteisiin.

Dokumentti perustuu tarkastettuihin skeemoihin, CLI-entrypointeihin, builder-moduuleihin, raporttien lukupolkuihin, testeihin ja nykyisen `data/analysis.db`:n havaintoihin. Jos jotakin asiaa ei voitu vahvistaa suoraan koodista tai datasta, se on merkitty epävarmaksi.

## Scope

Tämä dokumentti kattaa tasan seuraavat taulut:

- `dc_ecosystem_membership`
- `dc_group_index_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_pipeline_watermark`
- `dc_ticker_swing_signal_daily`

## Executive summary

| Table | Short meaning | Granularity | Main producer | Main consumers | Status / role |
|---|---|---|---|---|---|
| `dc_ecosystem_membership` | Skeemassa varattu membership-taulu tickerin, layerin ja subindustryn suhteille | yksi rivi per `taxonomy_version` + `ticker` + `layer` + `subindustry` | Ei vahvistettua writeria tarkastetuissa tiedostoissa | Ei vahvistettuja lukijoita tarkastetuissa tiedostoissa | `unclear / possibly unused schema placeholder` |
| `dc_group_index_daily` | Datacenter-ryhmien päivittäinen equal-weight-indeksi ja breadth/return-mittarit | yksi rivi per päivä + taxonomy + group | `run_datacenter_indices.py` / `analysis.datacenter_indices.persistence` | index-reportointi, group swing -builder, dashboard-enrichment, putken valid date -logiikka | `active dc pipeline table` |
| `dc_ticker_swing_signal_daily` | Ticker-tason päivittäinen swing snapshot ja scanner-kentät | yksi rivi per päivä + taxonomy + ticker + signal_version | `run_datacenter_ticker_swing_signals.py` / `analysis.datacenter_indices.swing_ticker_persistence` | daily/rolling datacenter-raportit, dashboard-auditit, V3 ticker/group builders | `active dc pipeline table; transitional V3 source` |
| `dc_group_swing_signal_daily` | Ryhmätason swing breadth, return, timing ja overheat-konteksti | yksi rivi per päivä + taxonomy + group + signal_version | `run_datacenter_group_swing_signals.py` / `analysis.datacenter_indices.swing_group_persistence` | daily/rolling datacenter-raportit, dashboard enrichment, useat V3 replacement builderit | `active dc pipeline table; transitional V3 source` |
| `dc_group_synthetic_ohlc_daily` | Layer/subindustry-tason synteettinen OHLC, relative OHLC ja rakennekonteksti | yksi rivi per päivä + taxonomy + group + calc_version | `run_datacenter_group_synthetic_ohlc.py` / `analysis.datacenter_indices.swing_group_synthetic_ohlc` | daily/rolling datacenter-raportit, dashboard enrichment, useat V3 replacement builderit | `active dc pipeline table; transitional V3 source` |
| `dc_pipeline_watermark` | Putkivaiheiden viimeisin onnistunut date-range / status metadata | yksi rivi per komponentti + taxonomy + market + version-dimensio | `analysis.datacenter_indices.swing_pipeline_orchestrator` via `pipeline_watermark.upsert_pipeline_watermark` | watermark CLI, pipeline planner, scheduler UI | `active operational metadata` |

## Table-by-table reference

### `dc_ecosystem_membership`

#### Meaning

Taulu on skeemassa oleva membership-rakenne, joka mallintaa tickerin kuulumista layer- ja subindustry-ryhmiin tietylle `taxonomy_version`-versiolle.

#### Granularity

Yksi rivi per:

- `taxonomy_version`
- `ticker`
- `layer`
- `subindustry`

Primaariavain on `(taxonomy_version, ticker, layer, subindustry)`.

#### Important columns

- `taxonomy_version`: taksonomiaversio.
- `ticker`: ticker.
- `layer`: tickerin layer.
- `subindustry`: tickerin subindustry.
- `report_group_status`: ryhmästatus, mutta käyttöä ei voitu vahvistaa.
- `is_primary`: kertoo onko membership primary-roolissa.
- `role_weight`: painokerroin membershipille.
- `notes`: vapaa tekstikenttä.
- `created_at_utc`: luontiaika.

#### How it is populated

Taulu luodaan skeemaan `analysis/database_manager.py`:ssa.

Tarkastetuista tiedostoista ei löytynyt writeria, joka tekisi `INSERT`, `UPDATE`, `DELETE` tai `UPSERT` -operaatioita tähän tauluun. Nykyisessä `data/analysis.db`:ssa taulussa oli tarkastushetkellä `0` riviä.

Siksi tarkkaa refresh-tapaa ei ole vahvistettu.

#### How it is used

Tarkastetuista tiedostoista ei löytynyt selkeitä aktiivisia lukijoita.

V3-ekosysteemimallin design-dokumentissa on erikseen todettu, että tarkastettu `dc_ecosystem_membership` on olemassa mutta tyhjä, ja että nykyinen taksonomia näyttää tulevan CSV:stä eikä tietokannasta.

#### Notes / caveats

- Taulu vaikuttaa olevan schema-valmius ennemmin kuin aktiivinen tuotantotaulu.
- Dokumentoidun käytön puute ei kuitenkaan yksin todista, että taulu olisi lopullisesti poistunut käytöstä.
- Luokitus on johdonmukaisesti `unclear / possibly unused schema placeholder`.

### `dc_group_index_daily`

#### Meaning

Taulu tallentaa datacenter-ryhmille päivittäiset indeksirivit: equal-weight-hintaindeksin, breadth-mittarit, returnit, volatiliteetin ja benchmark-suhteelliset mittarit.

Ryhmä voi olla:

- koko ekosysteemi (`ecosystem`)
- layer
- subindustry

#### Granularity

Yksi rivi per:

- `index_date`
- `taxonomy_version`
- `group_type`
- `group_name`

Primaariavain on `(index_date, taxonomy_version, group_type, group_name)`.

#### Important columns

- `index_date`: indeksipäivä.
- `taxonomy_version`: taksonomiaversio.
- `group_type`, `group_name`: ryhmän identiteetti.
- `member_count`: ryhmän jäsenmäärä.
- `eligible_count`: niiden tickerien määrä, joilta saatiin päivän laskentaan kelvollinen data.
- `ma50_eligible_count`, `ma200_eligible_count`: kelvolliset määrät MA50/MA200-laskentoihin.
- `daily_return_equal`, `median_return`: päivätuottoja.
- `pct_positive`, `pct_above_ma50`, `pct_above_ma200`: breadth-mittareita.
- `index_level_equal`: equal-weight-indeksitaso.
- `return_20d`, `return_60d`, `return_120d`: pidemmät tuotot.
- `volatility_20d`, `volatility_60d`: volatiliteetti.
- `relative_strength_spy_60d`, `relative_strength_qqq_60d`: suhteellinen vahvuus benchmarkeihin.
- `data_quality_status`: datan laatu.
- `calc_version`, `run_id`, `created_at_utc`: lineage / ajometadata.

#### How it is populated

Pää-writer on `run_datacenter_indices.py`, joka kutsuu `analysis.datacenter_indices.persistence.run_datacenter_indices`.

Laskenta:

- lataa taxonomy-rivit CSV:stä
- lataa OHLCV-close-historian `osakedata`-taulusta price DB:stä
- laskee ryhmätasoiset indeksirivit `calculate_datacenter_group_indices`-logiikalla
- kirjoittaa rivit `dc_group_index_daily`-tauluun

Kirjoitustapa on vahvistetusti `replace-range`:

- ensin `DELETE` valitulta date-rangelta ja taxonomy-versiolta
- sitten `INSERT` kaikille uudelleen lasketuille riveille

Lähdedata:

- datacenter taxonomy CSV
- OHLCV price DB (`osakedata`)

#### How it is used

Vahvistettuja lukijoita:

- `run_datacenter_index_report.py` / `analysis.datacenter_indices.reporting`
- `dc_group_swing_signal_daily`-builder, joka hakee ryhmän returnit ja `pct_above_ma200`-arvot tästä taulusta
- `persist_datacenter_group_swing_signal_range`, joka käyttää `dc_group_index_daily`-päiviä valid signal date -lähteenä
- dashboard enrichment writer, jossa `dc_group_index_daily` on optional source
- scheduler/smoke/test-polut, jotka validoivat indeksivaiheen valmistumista

#### Notes / caveats

- Taulu on selkeästi aktiivinen.
- Se ei näytä olevan V3 `eco_*` -mallin ydinloppumuoto, mutta se on edelleen usean downstream-vaiheen lähde.
- Toisin kuin `dc_group_synthetic_ohlc_daily`, tämä taulu kattaa myös `ecosystem`-tason ryhmän.

### `dc_ticker_swing_signal_daily`

#### Meaning

Taulu on ticker-tason päivittäinen swing snapshot. Se yhdistää:

- OHLCV-pohjaiset momentum- ja MA-mittarit
- Dow-rakenteen rikastuksen
- divergence-rikastuksen
- candlestick-rikastuksen
- myöhemmin päivitetyt scanner-kentät, kuten breakout, pullback ja exit-risk

#### Granularity

Yksi rivi per:

- `signal_date`
- `taxonomy_version`
- `ticker`
- `signal_version`

Primaariavain on `(signal_date, taxonomy_version, ticker, signal_version)`.

#### Important columns

- identiteetti:
  - `signal_date`, `taxonomy_version`, `ticker`, `signal_version`
- taxonomy-konteksti:
  - `primary_layer`, `primary_subindustry`
- hinta/momentum:
  - `close`, `volume`
  - `return_5d`, `return_10d`, `return_20d`, `return_60d`
  - `ma10`, `ema10`, `ema20`
  - `distance_to_ma10_pct`, `distance_to_ema10_pct`, `distance_to_ema20_pct`
  - `above_ma10`, `above_ema10`, `above_ema20`
  - `ema10_slope_positive`, `ema20_slope_positive`
  - `highest_close_20d`, `volume_avg_20d`, `volume_vs_avg20`
- rakenne/BOS/RESET:
  - `latest_structure_label`
  - `latest_structure_confirmed_as_of_date`
  - `latest_structure_age_trading_days`
  - `latest_structure_freshness`
  - `ticker_trend_state`
  - `structure_epoch_id`
  - `latest_bos_*`
  - `latest_reset_*`
- divergence ja candle:
  - `bullish_divergence_signal`, `bearish_divergence_signal`
  - `hidden_bullish_divergence_signal`, `hidden_bearish_divergence_signal`
  - `bullish_candle_signal`, `bearish_candle_signal`
- scanner-kentät:
  - `breakout_signal`
  - `fast_ema10_pullback_signal`
  - `conservative_ema20_pullback_signal`
  - `pullback_signal`
  - `exit_risk_signal`, `exit_reason`, `exit_risk_severity`
- `price_data_status`: oliko tickerillä kelvollinen päivädata / riittävä historia.

#### How it is populated

Pää-CLI on `run_datacenter_ticker_swing_signals.py`.

Perusvaihe:

- `persist_datacenter_ticker_swing_snapshots`
- lataa taxonomy CSV:n
- valitsee primary taxonomy-rivit
- lataa tickerin rajatun OHLCV-historian price DB:stä
- lukee `analysis.db`:sta ticker-kohtaisen Dow-, divergence- ja candlestick-rikastuksen
- rakentaa snapshot-rivit
- kirjoittaa ne `dc_ticker_swing_signal_daily`-tauluun

Scanner-vaihe:

- sama CLI `--scanner-only`-tilassa
- `persist_datacenter_ticker_scanner_signals`
- lukee jo olemassa olevat `dc_ticker_swing_signal_daily`-rivit
- hakee tickerin `primary_subindustry`-ryhmän `timing_state`-arvon taulusta `dc_group_swing_signal_daily`
- päivittää scanner-kentät olemassa oleville riveille

Kirjoitustavat:

- base snapshot: `insert-missing`, `upsert`, `replace-date`
- scanner update: `update-existing`, `replace-scanner-range`

Lähdedata:

- datacenter taxonomy CSV
- OHLCV price DB
- `analysis.db`-rikastukset Dow/divergence/candlestick -tauluista
- scanner-vaiheessa `dc_group_swing_signal_daily`

#### How it is used

Vahvistettuja lukijoita:

- datacenter daily/rolling report -polut
- useat dashboard audit- ja enrichment-CLI:t
- `analysis.datacenter_indices.technical_relevance_context`
- V3 builders, mm. `rawcandle/report_canonical_v3_base_builder.py`
- V3 ticker rolling-window replacement builderit
- V3 snapshot- ja classification-builderit testien perusteella

#### Notes / caveats

- Taulu on aktiivinen ja selvä source-of-truth datacenter swing -tickerkontekstille.
- Kaikki scanner-kentät eivät synny samalla ajolla kuin perussnapshot; ne täydennetään myöhemmässä vaiheessa.
- `primary_subindustry` on nykyinen yksinkertaistus. V3-designissa on erikseen huomioitu, että multi-membership pitäisi mallintaa eksplisiittisemmin.

### `dc_group_swing_signal_daily`

#### Meaning

Taulu on ryhmätason swing-signaalitaulu. Se kuvaa ryhmän breadthiä, returneja, timing-tilaa ja overheat-riskiä tietylle signal-päivälle.

#### Granularity

Yksi rivi per:

- `signal_date`
- `taxonomy_version`
- `group_type`
- `group_name`
- `signal_version`

Primaariavain on `(signal_date, taxonomy_version, group_type, group_name, signal_version)`.

#### Important columns

- `group_type`, `group_name`: ryhmän identiteetti.
- `member_count`, `eligible_count`: ryhmän kokonais- ja kelvollinen peitto.
- `return_5d`, `return_10d`, `return_20d`, `return_60d`: ryhmätuotot.
- `pct_above_ma10`, `pct_above_ema20`, `pct_above_rising_ema20`: breadth-mittarit.
- `ma10_breadth_delta_5d`, `ema20_breadth_delta_5d`: breadthin muutos aiempaan kelvolliseen päivään.
- `trend_breadth`, `weakness_breadth`: nousu-/heikkousbreadth.
- `timing_state`, `timing_reason`: buy/add/trim/exit/neutraali -luokitus.
- `overheat_risk_level`: LOW/ELEVATED/HIGH/EXTREME tai NULL.
- `data_quality_status`, `signal_version`, `run_id`, `created_at_utc`.

#### How it is populated

Pää-CLI on `run_datacenter_group_swing_signals.py`.

Base-vaihe:

- `persist_datacenter_group_swing_signals`
- lataa taxonomy CSV:n
- rakentaa group-definitions-rakenteen (`ecosystem`, `layer`, `subindustry`)
- lukee ticker snapshotit `dc_ticker_swing_signal_daily`-taulusta
- laskee breadth-mittarit ticker-riveistä
- laskee returnit `dc_group_index_daily.index_level_equal` -historiasta
- kirjoittaa base-rivit ilman timing/overheat-arvoja

Timing-vaihe:

- sama CLI `--timing-only`
- päivittää olemassa oleville riveille `timing_state` ja `timing_reason`

Overheat-vaihe:

- sama CLI `--overheat-only`
- päivittää olemassa oleville riveille `overheat_risk_level`
- käyttää apuna `dc_group_index_daily.pct_above_ma200` -arvoa ja aiempaa breadth-deltaa

Kirjoitustavat:

- base: `insert-missing`, `upsert`, `replace-date`
- timing: `update-existing`, `replace-timing-range`
- overheat: `update-existing`, `replace-overheat-range`

Lähdedata:

- datacenter taxonomy CSV
- `dc_ticker_swing_signal_daily`
- `dc_group_index_daily`
- aiemmat `dc_group_swing_signal_daily`-rivit breadth-delta- ja timing/overheat-jatkologiikassa

#### How it is used

Vahvistettuja lukijoita:

- datacenter daily/rolling reportit
- ticker scanner -vaihe `dc_ticker_swing_signal_daily`-taulun päivittämiseksi
- dashboard group enrichment
- V3 `report_canonical_v3_group_status_replacement_builder.py`
- V3 `report_canonical_v3_group_window_metric_replacement_builder.py`
- muut V3 rolling/classification-builderit testien perusteella

#### Notes / caveats

- Taulu on aktiivinen ja myös V3-siirtymän kannalta merkittävä transitional source.
- `persist_datacenter_group_swing_signal_range` käyttää valid päiviä `dc_group_index_daily`-taulusta, ei kalenteripäiviä.
- Base-rivi ja siitä johdetut timing/overheat-kentät syntyvät eri alavaiheissa.

### `dc_group_synthetic_ohlc_daily`

#### Meaning

Taulu sisältää ryhmätasoisen synteettisen OHLC-aikasarjan sekä myöhemmin siihen päivitetyn relative-OHLC- ja rakennekontekstin.

Tämä ei ole tickerin oikea markkinakynttilä, vaan ryhmän jäsenistä johdettu synteettinen sarja.

#### Granularity

Yksi rivi per:

- `ohlc_date`
- `taxonomy_version`
- `group_type`
- `group_name`
- `calc_version`

Primaariavain on `(ohlc_date, taxonomy_version, group_type, group_name, calc_version)`.

#### Important columns

- identiteetti:
  - `ohlc_date`, `taxonomy_version`, `group_type`, `group_name`, `calc_version`
- synteettinen OHLC:
  - `synthetic_open`, `synthetic_high`, `synthetic_low`, `synthetic_close`, `synthetic_volume`
- trend/momentum:
  - `ma20`, `ema20`, `distance_to_ema20_pct`, `volatility_20d`
- rakenne:
  - `pivot_radius`
  - `latest_pivot_high_*`, `latest_pivot_low_*`
  - `latest_structure_label`
  - `latest_structure_age_trading_days`, `latest_structure_freshness`
  - `latest_bos_*`
  - `latest_reset_*`
  - `trend_classification`
- relative OHLC:
  - `relative_base_window`
  - `relative_open_20`, `relative_high_20`, `relative_low_20`, `relative_close_20`
  - `relative_upper_wick_20`, `relative_lower_wick_20`
  - `relative_close_extension_20`, `relative_high_extension_20`, `relative_low_extension_20`
  - `relative_eligible_count`
- laatu:
  - `member_count`, `eligible_count`, `data_quality_status`

#### How it is populated

Pää-CLI on `run_datacenter_group_synthetic_ohlc.py`.

Base-vaihe:

- `persist_datacenter_group_synthetic_ohlc`
- lataa taxonomy CSV:n
- lataa OHLCV-rivit price DB:stä
- rakentaa ryhmille synteettisen OHLC-sarjan päivittäisistä member-returneista
- kirjoittaa base-rivit

Relative-vaihe:

- sama CLI `--relative-only`
- laskee rolling 20 -ikkunaan sidotut relative OHLC -kentät
- päivittää vain olemassa olevia base-rivejä

Structure-vaihe:

- sama CLI `--structure-only`
- lukee `dc_group_synthetic_ohlc_daily`-historian tiettyyn päivään asti
- laskee pivotit, rakenne-etiketit, BOS/RESET-tapahtumat ja freshness-kentät
- päivittää vain olemassa olevia rivejä

Kirjoitustavat:

- base: `insert-missing`, `upsert`, `replace-range`
- relative: `update-existing`, `replace-relative-range`
- structure: `update-existing`, `replace-structure-range`

Lähdedata:

- datacenter taxonomy CSV
- OHLCV price DB
- relative/structure-vaiheissa taulun oma aiempi base-data

#### How it is used

Vahvistettuja lukijoita:

- datacenter daily/rolling reportit
- dashboard group enrichment
- `rawcandle/report_canonical_v3_group_event_builder.py`
- `rawcandle/report_canonical_v3_group_window_metric_replacement_builder.py`
- `rawcandle/report_canonical_v3_window_snapshot_replacement_builder.py`
- `rawcandle/report_canonical_v3_freshness_builder.py`

#### Notes / caveats

- Taulu on aktiivinen.
- Koodin perusteella base- ja relative-laskenta käyttävät `layer`- ja `subindustry`-ryhmiä; `ecosystem`-ryhmän käsittely näyttää epävarmemmalta, koska yhteenvedoissa korostuu `layer,subindustry`.
- Structure-luokitus on eksplisiittisesti ryhmätason johdettua logiikkaa, ei suoraan ticker-rakenteen kopio.

### `dc_pipeline_watermark`

#### Meaning

Taulu tallentaa putken komponenttikohtaisen viimeisimmän onnistuneen ajon kattaman date-rangen ja statuksen. Se on operatiivista metadataa, ei markkina- tai signaalidataa.

#### Granularity

Yksi rivi per:

- `component_name`
- `taxonomy_version`
- `market`
- `signal_version`
- `calc_version`

Primaariavain on `(component_name, taxonomy_version, market, signal_version, calc_version)`.

#### Important columns

- identiteetti:
  - `component_name`
  - `taxonomy_version`
  - `market`
  - `signal_version`
  - `calc_version`
- kattavuus:
  - `start_date`, `end_date`
  - `row_count`
- status/lineage:
  - `status`
  - `last_successful_run_id`
  - `last_successful_at_utc`
  - `notes`

#### How it is populated

Writer on `analysis.datacenter_indices.pipeline_watermark.upsert_pipeline_watermark`.

Tätä kutsuu `analysis.datacenter_indices.swing_pipeline_orchestrator`, joka kirjoittaa watermark-rivit kunkin onnistuneen vaiheen jälkeen. Tarkastetuissa vaiheissa mukana ovat esimerkiksi:

- `GROUP_INDEX`
- `TICKER_SWING_BASE`
- `GROUP_SWING_BASE`
- `SYNTHETIC_OHLC_BASE`
- `SYNTHETIC_OHLC_RELATIVE`
- `SYNTHETIC_OHLC_STRUCTURE`
- `GROUP_TIMING`
- `GROUP_OVERHEAT`
- `TICKER_SCANNER`
- `PIPELINE_AUDIT`
- raporttivaiheiden watermarkit

Kirjoitustapa on `INSERT ... ON CONFLICT DO UPDATE`, eli upsert per komponentti-identiteetti.

#### How it is used

Vahvistettuja lukijoita:

- `run_datacenter_pipeline_watermark.py`
- `run_datacenter_swing_pipeline_plan.py`
- `analysis.datacenter_indices.pipeline_plan`
- scheduler UI:n watermark-näkymä

#### Notes / caveats

- Runbookin mukaan taulu on nykyvaiheessa visibility/audit-metadataa.
- Sitä ei vielä käytetä automaattiseen vaiheiden skip-päätökseen pääputkessa.
- Luokitus on johdonmukaisesti `active operational metadata`.

## Relationship between the tables

Tarkastetun koodin perusteella todennäköisin ja vahvistettu päävirta on:

1. Datacenter taxonomy CSV määrittää tickerit, layerit ja subindustryt.
2. `dc_group_index_daily` muodostetaan taxonomy CSV:stä ja OHLCV-price DB:stä.
3. `dc_ticker_swing_signal_daily` muodostetaan taxonomy CSV:stä, price DB:stä ja `analysis.db`:n ticker-rikastuksista.
4. `dc_group_swing_signal_daily` muodostetaan yhdistämällä:
   - group definitions taxonomy CSV:stä
   - breadth ticker-riveistä taulusta `dc_ticker_swing_signal_daily`
   - ryhmätuotot taulusta `dc_group_index_daily`
5. `dc_group_synthetic_ohlc_daily` muodostetaan taxonomy CSV:stä ja price DB:stä, jonka jälkeen siihen päivitetään:
   - relative OHLC -kentät
   - structure / BOS / RESET -kentät
6. `dc_ticker_swing_signal_daily` saa myöhemmässä scanner-vaiheessa lisäkentät, jotka riippuvat osittain `dc_group_swing_signal_daily`-taulun subindustry timing -tilasta.
7. `dc_pipeline_watermark` seuraa kunkin vaiheen viimeisintä onnistunutta kattavuutta.

`dc_ecosystem_membership` ei kytkeytynyt tarkastetuissa write/read-poluissa tähän aktiiviseen virtaan.

## Build / refresh flow

Nykyinen vahvistettu refresh-järjestys löytyy runbookista ja `run_datacenter_swing_pipeline.py`:n orchestratorista.

Keskeiset CLI-entrypointit:

```bash
python3 run_datacenter_indices.py \
  --ohlcv-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --market usa \
  --index-base-date 2020-01-01 \
  --start-date <START_DATE> \
  --end-date <END_DATE> \
  --write-mode replace-range
```

```bash
python3 run_datacenter_ticker_swing_signals.py \
  --price-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --market usa \
  --write-mode replace-date
```

```bash
python3 run_datacenter_group_swing_signals.py \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --signal-version DC_SWING_SIGNAL_V1 \
  --write-mode replace-date
```

```bash
python3 run_datacenter_group_synthetic_ohlc.py \
  --price-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --market usa \
  --write-mode replace-range
```

```bash
python3 run_datacenter_group_synthetic_ohlc.py \
  --price-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --market usa \
  --write-mode replace-relative-range \
  --relative-only
```

```bash
python3 run_datacenter_group_synthetic_ohlc.py \
  --analysis-db data/analysis.db \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --write-mode replace-structure-range \
  --structure-only
```

```bash
python3 run_datacenter_group_swing_signals.py \
  --analysis-db data/analysis.db \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --write-mode replace-timing-range \
  --timing-only
```

```bash
python3 run_datacenter_group_swing_signals.py \
  --analysis-db data/analysis.db \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --write-mode replace-overheat-range \
  --overheat-only
```

```bash
python3 run_datacenter_ticker_swing_signals.py \
  --analysis-db data/analysis.db \
  --start-date <START_DATE> \
  --end-date <SIGNAL_DATE> \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --write-mode replace-scanner-range \
  --scanner-only
```

Koko putken wrapper:

```bash
python3 run_datacenter_swing_pipeline.py \
  --price-db data/osakedata.db \
  --analysis-db data/analysis.db \
  --taxonomy-csv data/datacenter_ecosystem_taxonomy_full_v1.csv \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --market usa \
  --signal-date <SIGNAL_DATE> \
  --start-date <START_DATE> \
  --index-base-date 2020-01-01 \
  --output-dir swing_reports
```

Watermark-inspektio:

```bash
python3 run_datacenter_pipeline_watermark.py \
  --analysis-db data/analysis.db \
  --taxonomy-version DC_TAXONOMY_FULL_V1
```

## Current role versus V3 `eco_*` model

Tarkastetun koodin perusteella suhde V3-malliin on seuraava:

### `dc_ecosystem_membership`

Luokitus: `unclear / possibly unused schema placeholder`

Perusteet:

- writeria ei löytynyt tarkastetuista tiedostoista
- lukijoita ei löytynyt tarkastetuista tiedostoista
- nykyisessä `data/analysis.db`:ssa taulu oli tyhjä
- V3 design -dokumentti toteaa erikseen, että taulu on olemassa mutta tyhjä

### `dc_group_index_daily`

Luokitus: `active dc pipeline table`

Perusteet:

- aktiivinen writer `run_datacenter_indices.py`
- aktiivinen raporttilukija `run_datacenter_index_report.py`
- downstream group swing -builder lukee tätä taulua
- dashboard enrichment voi lukea tätä taulua

V3-suhde:

- ei näytä olevan pääasiallinen `eco_*`-replacement source samalla tavalla kuin group/ticker swing -taulut
- mutta se on yhä aktiivinen osa datacenter-putkea

### `dc_ticker_swing_signal_daily`

Luokitus: `active dc pipeline table; transitional V3 source`

Perusteet:

- aktiivinen datacenter-writer
- nykyiset daily/rolling datacenter-raportit lukevat tätä suoraan
- V3 base/window/classification-builderit lukevat tätä source-tauluna

### `dc_group_swing_signal_daily`

Luokitus: `active dc pipeline table; transitional V3 source`

Perusteet:

- aktiivinen datacenter-writer
- nykyiset datacenter-raportit lukevat tätä suoraan
- ticker scanner -vaihe riippuu siitä
- useat V3 replacement builderit lukevat tätä source-tauluna

### `dc_group_synthetic_ohlc_daily`

Luokitus: `active dc pipeline table; transitional V3 source`

Perusteet:

- aktiivinen datacenter-writer
- nykyiset datacenter-raportit lukevat tätä suoraan
- useat V3 builders lukevat tätä source-tauluna group structure-, freshness- ja window-metriikoille

### `dc_pipeline_watermark`

Luokitus: `active operational metadata`

Perusteet:

- aktiivinen writer orchestratorissa
- aktiiviset lukijat watermark CLI:ssa, pipeline plannerissa ja scheduler UI:ssa

V3-suhde:

- ei ole domain-source V3 `eco_*` -faktoille
- se on putken operatiivinen kontrolli-/näkyvyysmetadata

## Evidence inspected

### migrations/schema

- `analysis/database_manager.py`: tästä varmistettiin kuuden `dc_`-taulun skeemat, indeksit, primaariavaimet ja mahdolliset `ALTER TABLE` -lisäykset.

### builders/writers

- `analysis/datacenter_indices/persistence.py`: tästä varmistettiin `dc_group_index_daily`-taulun laskenta- ja `replace-range`-kirjoituspolku.
- `analysis/datacenter_indices/swing_ticker_persistence.py`: tästä varmistettiin `dc_ticker_swing_signal_daily`-taulun base-snapshot- ja scanner-update -kirjoituslogiikka.
- `analysis/datacenter_indices/swing_group_persistence.py`: tästä varmistettiin `dc_group_swing_signal_daily`-taulun base-, timing- ja overheat-vaiheet.
- `analysis/datacenter_indices/swing_group_synthetic_ohlc.py`: tästä varmistettiin `dc_group_synthetic_ohlc_daily`-taulun base-, relative- ja structure-vaiheet.
- `analysis/datacenter_indices/pipeline_watermark.py`: tästä varmistettiin `dc_pipeline_watermark`-taulun upsert- ja lukuoperaatiot.
- `rawcandle/report_canonical_v3_base_builder.py`: tästä varmistettiin, että V3 builder voi lukea `dc_ticker_swing_signal_daily`-taulua.
- `rawcandle/report_canonical_v3_group_status_replacement_builder.py`: tästä varmistettiin, että V3 replacement builder lukee `dc_group_swing_signal_daily`-taulua.
- `rawcandle/report_canonical_v3_group_window_metric_replacement_builder.py`: tästä varmistettiin `dc_group_swing_signal_daily`- ja `dc_group_synthetic_ohlc_daily`-taulujen V3 window-metric -käyttö.
- `rawcandle/report_canonical_v3_ticker_window_metric_replacement_builder.py`: tästä varmistettiin `dc_ticker_swing_signal_daily`-taulun käyttö V3 ticker window -metrikoissa.

### CLIs/pipeline

- `run_datacenter_indices.py`: tästä varmistettiin `dc_group_index_daily`-taulun pää-CLI.
- `run_datacenter_ticker_swing_signals.py`: tästä varmistettiin `dc_ticker_swing_signal_daily`-taulun CLI-rajapinta ja scanner-only -tila.
- `run_datacenter_group_swing_signals.py`: tästä varmistettiin `dc_group_swing_signal_daily`-taulun CLI-rajapinta sekä timing-only- ja overheat-only -tilat.
- `run_datacenter_group_synthetic_ohlc.py`: tästä varmistettiin `dc_group_synthetic_ohlc_daily`-taulun CLI-rajapinta sekä relative-only- ja structure-only -tilat.
- `run_datacenter_swing_pipeline.py`: tästä varmistettiin koko datacenter swing -putken ajettava wrapper ja vaiheistus.
- `analysis/datacenter_indices/swing_pipeline_orchestrator.py`: tästä varmistettiin vaihekohtaiset watermark-kirjoitukset ja putken ajonjärjestys.
- `run_datacenter_index_report.py`: tästä varmistettiin, että index-reportti lukee `dc_group_index_daily`-taulua.
- `run_datacenter_pipeline_watermark.py`: tästä varmistettiin `dc_pipeline_watermark`-taulun read-only-inspektio.

### tests

- `tests/test_datacenter_swing_pipeline_smoke.py`: tästä varmistettiin, että putken smoke-testi odottaa `dc_group_index_daily`, `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` ja `dc_group_synthetic_ohlc_daily` -taulujen täyttyvän.
- `tests/test_run_datacenter_ticker_swing_signals_cli.py`: tästä varmistettiin ticker swing -CLI:n base- ja scanner-only -käyttäytyminen sekä riippuvuus `dc_group_swing_signal_daily`-taulusta scanner-vaiheessa.
- `tests/test_run_datacenter_index_report_cli.py`: tästä varmistettiin, että index-report CLI lukee `dc_group_index_daily`-taulua ja epäonnistuu, jos rivejä ei ole.

### docs

- `docs/datacenter_swing_signal_runbook.md`: tästä varmistettiin nykyinen build / refresh flow sekä `dc_pipeline_watermark`-taulun nykyinen visibility/audit-rooli.
- `docs/archive/canonical_report_v2/datacenter_report_canonical_v2_architecture.md`: tästä historiallisesta taustadokumentista varmistettiin, että nykyiset daily/rolling datacenter-raportit lukevat edelleen `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` ja `dc_group_synthetic_ohlc_daily` -tauluja.
- `docs/canonical_v3_ecosystem_entity_model_design.md`: tästä varmistettiin V3-siirtymän tavoitetila sekä huomio siitä, että `dc_ecosystem_membership` on tarkastetussa tilassa tyhjä ja nykyinen taksonomia näyttää tulevan CSV:stä.

## Open questions

- Onko `dc_ecosystem_membership` tarkoitettu jäämään tulevaksi skeemapaikaksi, vai pitäisikö se myöhemmin poistaa, jos taksonomia siirtyy kokonaan `eco_*`-master-dataan?
- Lukevatko kaikki nykyiset daily/rolling-raportit edelleen suoraan `dc_*`-tauluja, vai onko osa raportointiketjusta jo siirtynyt käyttämään `eco_*`-rakenteita tuotannossa?
- Millä ehdolla `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` ja `dc_group_synthetic_ohlc_daily` lakkaavat olemasta V3 transitional source -tauluja?
- Tuleeko `dc_pipeline_watermark` myöhemmin ohjaamaan automaattisia skip/resume-päätöksiä, vai jääkö se vain visibility/audit-metadataksi?

## Evidence notes from current `data/analysis.db`

Tarkastushetkellä `data/analysis.db`:ssa oli seuraavat rivimäärät:

- `dc_ecosystem_membership`: `0`
- `dc_group_index_daily`: `88512`
- `dc_group_swing_signal_daily`: `19362`
- `dc_group_synthetic_ohlc_daily`: `20130`
- `dc_pipeline_watermark`: `15`
- `dc_ticker_swing_signal_daily`: `84318`

Tämä tukee sitä tulkintaa, että viisi kuudesta tarkastetusta taulusta ovat aktiivisesti käytössä, kun taas `dc_ecosystem_membership` vaikuttaa tämänhetkisessä datassa käyttämättömältä.
