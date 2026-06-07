# Ecosystem V3 `eco_*` tables reference

## Purpose of this document

Tämä dokumentti kuvaa V3 `eco_*` -taulut tiedostossa `data/analysis.db`: mitä ne sisältävät, millä rakeella ne elävät, miten ne täyttyvät, mitä koodipolkuja ne lukevat ja miten ne suhteutuvat legacy Datacenter `dc_*` -rakenteisiin.

Dokumentin tarkoitus on auttaa myöhempää päättelyä V3-ekosysteemimallin tietolinjasta, datan täydellisyydestä, raportoinnin riippuvuuksista ja legacy `dc_*` -riippuvuuksien turvallisesta poistamisesta.

Legacy `dc_*` -taulujen merkitykset on kuvattu erikseen dokumentissa [docs/datacenter_dc_tables_reference.md](/home/kalle/projects/rawcandle/docs/datacenter_dc_tables_reference.md), ja legacy-raporttien muodostus dokumentissa [docs/datacenter_legacy_report_generation_reference.md](/home/kalle/projects/rawcandle/docs/datacenter_legacy_report_generation_reference.md).

## Scope

Tarkastuksessa löytyivät seuraavat `eco_*` -taulut:

- `eco_ecosystem`
- `eco_taxonomy_version`
- `eco_entity`
- `eco_taxonomy_entity_relation`
- `eco_watchlist`
- `eco_watchlist_member`
- `eco_report_window`
- `eco_report_run`
- `eco_entity_window_snapshot`
- `eco_entity_metric_value`
- `eco_entity_coverage`
- `eco_quality_summary`
- `eco_signal_observation`
- `eco_signal_relevance`
- `eco_entity_event`
- `eco_classification_decision`

Viimeinen taulu, `eco_classification_decision`, on lisätty myöhemmin kuin pyynnön minimilista, mutta se on tällä hetkellä sekä skeemassa että nykyisessä `data/analysis.db`:ssa.

## Executive summary

| Table | Category | Short meaning | Granularity | Main producer | Main consumers | Status / role |
|---|---|---|---|---|---|---|
| `eco_ecosystem` | dimension/master | ekosysteemien master-lista | yksi rivi per ekosysteemi | taxonomy/watchlist importerit | base builder, inspect CLI, V3 query layer | seeded dimension |
| `eco_taxonomy_version` | dimension/master | ekosysteemin versionoitu taksonomia | yksi rivi per taxonomy version | taxonomy importer | base builder, inspect CLI, V3 query layer | populated by importer |
| `eco_entity` | dimension/master | geneerinen entity-rekisteri | yksi rivi per entity | taxonomy importer, watchlist importer | lähes kaikki V3 builderit ja queryt | populated by importer |
| `eco_taxonomy_entity_relation` | taxonomy relation | versionoitu parent-child / membership-suhde | yksi rivi per taxonomy version + parent + child + relation_type | taxonomy importer | base builder, V3 query layer | populated by importer |
| `eco_watchlist` | watchlist | ekosysteemikohtainen watchlist-määrittely | yksi rivi per watchlist | watchlist importer | base builder, inspect CLI, V3 query layer | populated by importer |
| `eco_watchlist_member` | watchlist | watchlistin jäsenet | yksi rivi per watchlist + entity | watchlist importer | base builder, V3 query layer | populated by importer |
| `eco_report_window` | dimension/master | vakioidut analyysi-ikkunat | yksi rivi per window_code | migraation seed-data | base builder, kaikki windowed builderit, query layer | seeded dimension |
| `eco_report_run` | report metadata | yhden V3-build-ajon metatieto | yksi rivi per run_id | `build_canonical_v3_base_run` | kaikki myöhemmät builderit, latest-markdown CLI, query layer | active V3 table |
| `eco_entity_window_snapshot` | snapshot fact | entity/window/date-yhteenvetotila | yksi rivi per run + date + taxonomy + window + entity | `build_canonical_v3_window_snapshots` | V3 query layer / Markdown-raportit | active V3 table |
| `eco_entity_metric_value` | metric fact | geneeriset V3-metriikat | yksi rivi per run + date + taxonomy + window + entity + metric_name | useat V3 metric builderit | V3 query layer / Markdown-raportit / freshness builderit | active V3 table |
| `eco_entity_coverage` | coverage fact | entityn lähdepeitto ja saatavuus per ikkuna | yksi rivi per run + date + taxonomy + window + entity | `build_canonical_v3_base_run` | snapshot builder, V3 query layer | active V3 table |
| `eco_quality_summary` | quality fact | laadun yhteenveto run/window/scope-tasolla | yksi rivi per run + date + taxonomy + window + quality_scope + scope_entity | `build_canonical_v3_base_run` | snapshot builder, V3 query layer | active V3 table |
| `eco_signal_observation` | signal fact | havaitut signaalit | yksi rivi per run + date + taxonomy + window + entity + signal_name + observed_date | MA/freshness/signal-relevance builderit | V3 query layer / Markdown-raportit | active V3 table |
| `eco_signal_relevance` | signal fact | signaalin relevanssitulkinta | yksi rivi per signal observation + relevance_label | `build_canonical_v3_signal_relevance` | V3 query layer / daily V3 reports | active V3 table |
| `eco_entity_event` | event fact | entityyn liitetty tapahtumahistoria | yksi rivi per run + taxonomy + entity + event_date + event_type + event_key | ticker/group event builderit | V3 query layer / Markdown-raportit / freshness builder | active V3 table |
| `eco_classification_decision` | event fact | canonical classifier / decision output | yksi rivi per run + date + taxonomy + window + entity + classification_type | daily/rolling replacement classifier builderit | snapshot builder, V3 query layer / Markdown-raportit | active V3 table; transitional inputs |

## V3 table groups

### Master data and dimensions

- `eco_ecosystem`
- `eco_taxonomy_version`
- `eco_entity`
- `eco_report_window`

Nämä taulut kuvaavat pitkäikäistä rakennetta, jota myöhemmät V3-faktataulut käyttävät viiteavaimina.

### Taxonomy and membership relations

- `eco_taxonomy_entity_relation`

Tämä taulu määrittää hierarkian ja membership-suhteet saman taksonomiaversion sisällä.

### Watchlists

- `eco_watchlist`
- `eco_watchlist_member`

Nämä siirtävät watchlistit TXT-runtime-lähteestä pysyväksi V3-master-dataksi.

### Report metadata

- `eco_report_run`

Tämä ankkuroi kaikki yhden build-ajon V3-faktit samaan `run_id`:hen.

### Snapshots, metrics, coverage and quality

- `eco_entity_window_snapshot`
- `eco_entity_metric_value`
- `eco_entity_coverage`
- `eco_quality_summary`

Nämä muodostavat V3:n varsinaisen analyysifaktakerroksen per entity, ikkuna ja päivämäärä.

### Signals and events

- `eco_signal_observation`
- `eco_signal_relevance`
- `eco_entity_event`
- `eco_classification_decision`

Nämä kuvaavat signaaleja, tulkittua relevanssia, tapahtumia ja raporttimaisia classifier-päätöksiä.

## Table-by-table reference

### `eco_ecosystem`

#### Meaning

Ekosysteemien master-lista. Tällä hetkellä käytössä oleva esimerkki on `DATACENTER`.

#### Category

`dimension/master`

#### Granularity

Yksi rivi per ekosysteemi.

#### Important columns

- `ecosystem_id`: tekninen pääavain.
- `ecosystem_code`: vakaa koodi kuten `DATACENTER`.
- `ecosystem_name`: käyttäjäystävällinen nimi.
- `status`: `ACTIVE`, `INACTIVE`, `PLANNED` tai `ARCHIVED`.
- `created_at_utc`, `updated_at_utc`: audit-aikaleimat.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- Datacenter-rivi luodaan tarvittaessa importerien `_ensure_ecosystem(...)`-poluissa:
  - `rawcandle/report_canonical_v3_taxonomy_import.py`
  - `rawcandle/report_canonical_v3_watchlist_import.py`
- Käynnistyy käytännössä taxonomy- ja watchlist-importeista.
- Ei riipu legacy `dc_*` -tauluista, vaan importer-koodin kovakoodatusta `DATACENTER`-identiteetistä.

#### How it is used

- `build_canonical_v3_base_run(...)` resolvoi `ecosystem_code`-arvon tästä.
- `inspect_canonical_v3.py` listaa ekosysteemit.
- `reporting_v3_query.py` liittyy tähän run-header- ja raporttikontekstissa.

#### Current data status

- Kevyessä DB-tarkistuksessa `data/analysis.db`:ssa 1 rivi.
- Nykyinen rivi: `DATACENTER`, status `ACTIVE`.

#### Notes / caveats

- Malli on multi-ecosystem-valmis, vaikka nykyinen data näyttää vain Datacenterin.

### `eco_taxonomy_version`

#### Meaning

Versionoitu taksonomia yhdelle ekosysteemille.

#### Category

`dimension/master`

#### Granularity

Yksi rivi per ekosysteemi + taxonomy version.

#### Important columns

- `taxonomy_version_id`: tekninen pääavain.
- `ecosystem_id`: viite `eco_ecosystem`-tauluun.
- `version_code`, `version_label`: version tunniste ja nimi.
- `source_type`, `source_reference`: mistä taksonomia on importoitu.
- `effective_from`, `effective_to`: voimassaolorajat.
- `is_active`, `status`: aktiivisen version tila.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- `import_datacenter_taxonomy_to_v3(...)` luo tai varmistaa version.
- Lähde on CSV, joka luetaan `analysis.datacenter_indices.taxonomy.load_datacenter_taxonomy_csv(...)`-polun kautta.
- Ei suoraa legacy `dc_*` -tauluriippuvuutta.

#### How it is used

- Base builder resolvoi aktiivisen tai eksplisiittisen taxonomy version tästä.
- Query- ja inspect-CLIt näyttävät version koodin ja lähdeviitteen.
- Kaikki faktataulut viittaavat `taxonomy_version_id`:hen.

#### Current data status

- `data/analysis.db`:ssa 1 rivi.
- Nykyinen aktiivinen versio: `DC_TAXONOMY_FULL_V1`, `source_type=CSV`.

#### Notes / caveats

- Koodi sallii useita versioita, mutta base builder vaatii, että aktiivinen versio on yksikäsitteinen, jos koodia ei anneta parametrina.

### `eco_entity`

#### Meaning

Geneerinen V3-entity-rekisteri kaikille ekosysteemin solmuille: `ECOSYSTEM`, `LAYER`, `SUBINDUSTRY`, `TICKER`.

#### Category

`dimension/master`

#### Granularity

Yksi rivi per canonical entity.

#### Important columns

- `entity_id`: tekninen pääavain.
- `ecosystem_id`: ekosysteemiviite.
- `entity_type`: `ECOSYSTEM`, `LAYER`, `SUBINDUSTRY`, `TICKER`.
- `entity_code`, `entity_name`: vakaa koodi ja näyttönimi.
- `ticker`, `exchange`, `market`, `currency`: instrumenttitason lisätiedot.
- `status`: `ACTIVE`, `WATCH_ONLY`, jne.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- Taxonomy importer luo `ECOSYSTEM`, `LAYER`, `SUBINDUSTRY` ja taxonomyssa näkyvät `TICKER`-entityt.
- Watchlist importer voi luoda puuttuvia `TICKER`-entityjä tilalla `WATCH_ONLY`, jos `create_missing_ticker_entities=True`.
- Ei suoraan täyty `dc_*`-tauluista, mutta taxonomy/watching importit ovat Datacenter-spesifejä siirtopolkuja.

#### How it is used

- Lähes kaikki builderit joinittavat `eco_entity`-tauluun entity-tyypin tai koodin ratkaisemiseksi.
- V3 query layer lukee entity-rakenteen, tickerit ja hierarkiat tästä.

#### Current data status

- `data/analysis.db`:ssa 291 riviä.

#### Notes / caveats

- Watchlist importer ja taxonomy importer voivat yhdessä tuoda `WATCH_ONLY`-tickereitä, jotka eivät ole aktiivisessa taxonomy-hierarkiassa.

### `eco_taxonomy_entity_relation`

#### Meaning

Versionoitu parent-child- ja membership-mappi entityjen välillä.

#### Category

`taxonomy relation`

#### Granularity

Yksi rivi per `taxonomy_version_id + parent_entity_id + child_entity_id + relation_type`.

#### Important columns

- `relation_id`: tekninen pääavain.
- `taxonomy_version_id`, `ecosystem_id`: konteksti.
- `parent_entity_id`, `child_entity_id`: hierarkia- tai membership-solmut.
- `relation_type`: tällä hetkellä käytössä erityisesti `CONTAINS`.
- `membership_role`: `CORE`, `ADJACENT`, `WATCH_ONLY`, `OPTIONAL`.
- `weight`, `is_primary`, `sort_order`: membershipin lisäattribuutit.
- `status`, `effective_from`, `effective_to`: voimassaolo.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- Taxonomy importer muodostaa suhteet Datacenter-taxonomy CSV:stä.
- `report_group_status` mapataan membership-rooliksi `_STATUS_TO_MEMBERSHIP_ROLE`-taulukolla.
- Ei suoraa `dc_*`-tauluriippuvuutta.

#### How it is used

- Base builder käyttää relaatioita valitakseen taxonomyyn kuuluvat entityt.
- `reporting_v3_query.py` rakentaa ticker-subindustry-layer-polkuja näistä riveistä.

#### Current data status

- `data/analysis.db`:ssa 382 riviä.

#### Notes / caveats

- Tämä on V3:n tärkein korvaaja legacy-ajattelulle, jossa ryhmäjäsenyyksiä päätellään epäsuoremmin Datacenter-rakenteesta.

### `eco_watchlist`

#### Meaning

Pysyvä watchlist-määrittely per ekosysteemi.

#### Category

`watchlist`

#### Granularity

Yksi rivi per watchlist.

#### Important columns

- `watchlist_id`: tekninen pääavain.
- `ecosystem_id`: ekosysteemiviite.
- `watchlist_code`, `watchlist_name`: tunniste ja nimi.
- `source_type`, `source_reference`: mistä watchlist on importoitu.
- `status`: aktiivinen/arkistoitu tila.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- `import_datacenter_watchlist_to_v3(...)` luo watchlist-rivin.
- Lähde on TXT-watchlist.
- Ei suoraa `dc_*`-tauluriippuvuutta.

#### How it is used

- Base builder poimii aktiivisten watchlistien jäsenet tästä ja `eco_watchlist_member`-taulusta.
- Inspect CLI näyttää watchlistit ja jäsenmäärät.
- Query layer käyttää tätä watchlist-summaryyn ja watchlist-suodattimiin.

#### Current data status

- `data/analysis.db`:ssa 1 rivi.

#### Notes / caveats

- Watchlist on jo DB:ssä, mutta importtilähde on edelleen TXT, joten lähdepolku on transitional vaikka kohdetila on V3-native.

### `eco_watchlist_member`

#### Meaning

Watchlistin entity-jäsenyydet.

#### Category

`watchlist`

#### Granularity

Yksi rivi per `watchlist_id + entity_id`.

#### Important columns

- `watchlist_member_id`: tekninen pääavain.
- `watchlist_id`, `entity_id`: jäsenyyden viitteet.
- `member_role`, `member_status`: rooli ja tila.
- `effective_from`, `effective_to`, `sort_order`: lisäkonteksti.
- `added_at_utc`, `removed_at_utc`, `notes`: auditointi.

#### How it is populated

- Skeema luodaan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- `import_datacenter_watchlist_to_v3(...)` lisää rivit watchlist-TXT:n perusteella.
- Voi käyttää aiemmin luotuja ticker-entityjä tai luoda puuttuvat `WATCH_ONLY`-tickerit.

#### How it is used

- Base builder poimii tästä watchlistiin kuuluvat entityt coverage-valintaa varten.
- Query layer lukee tästä watchlist-summaryn jäsenet.

#### Current data status

- `data/analysis.db`:ssa 16 riviä.

#### Notes / caveats

- Testit vahvistavat, että watchlist-membership on riippumaton taxonomy-relationsista.

### `eco_report_window`

#### Meaning

Vakioitu ikkuna-dimensio V3-analyyseille.

#### Category

`dimension/master`

#### Granularity

Yksi rivi per `window_code`.

#### Important columns

- `window_code`: pääavain, tällä hetkellä `daily`, `rolling2`, `rolling5`, `rolling30`.
- `window_label`: näyttönimi.
- `window_days`: ikkunan pituus.
- `is_active`, `sort_order`: käytettävyys ja järjestys.

#### How it is populated

- Luodaan ja seedataan migraatiossa `015_create_eco_base_dimensions_v3.sql`.
- Ei erillistä runtime-importeria.

#### How it is used

- Base builder lataa aktiiviset ikkunat tästä.
- Kaikki windowed faktataulut viittaavat `window_code`:en.
- Inspect CLI listaa ikkunat.

#### Current data status

- `data/analysis.db`:ssa 4 riviä.
- Kaikki neljä oletusikkunaa ovat aktiivisia.

#### Notes / caveats

- `window_days` tallentaa nimellisen ikkunakoon. Varsinainen valid trading day -käytäntö riippuu builder-kohtaisesta lähdelogiikasta.

### `eco_report_run`

#### Meaning

Yhden V3-build-ajon operational metadata.

#### Category

`report metadata`

#### Granularity

Yksi rivi per `run_id`.

#### Important columns

- `run_id`: pääavain.
- `ecosystem_id`, `taxonomy_version_id`, `signal_date`: build-konteksti.
- `run_type`: `BUILD`, `IMPORT`, `SMOKE`, `BACKFILL`.
- `status`: `STARTED`, `OK`, `OK_WITH_WARNINGS`, `FAILED`, jne.
- `warning_count`, `error_count`, `notes`: yhteenvetometadata.
- `created_at_utc`, `completed_at_utc`: ajon aikaleimat.

#### How it is populated

- Skeema luodaan migraatiossa `016_create_eco_core_facts_v3.sql`.
- Varsinainen writer on `build_canonical_v3_base_run(...)` tiedostossa `rawcandle/report_canonical_v3_base_builder.py`.
- `run_canonical_v3_latest_build.py` käynnistää base builderin ensimmäisenä vaiheena.
- Nykyinen base builder käyttää coverage-rivien laskennassa myös legacy `dc_ticker_swing_signal_daily` -taulua.
- Muista tarkastetuista runtime-writereistä ei löytynyt `INSERT INTO eco_report_run`.

#### How it is used

- Kaikki myöhemmät V3 builderit resolvoivat tästä `run_id`-kontekstin.
- `write_latest_v3_markdown_reports.py` valitsee tästä uusimman sopivan ajon.
- `reporting_v3_query.py` käyttää tätä raportin headeriin ja run metadataan.

#### Current data status

- `data/analysis.db`:ssa 2 riviä.
- Tarkistetut ajot:
  - `V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1`
  - `V3_BASE_DATACENTER_2026_06_04_DC_TAXONOMY_FULL_V1`
- Molempien status oli tarkistushetkellä `OK_WITH_WARNINGS`.

#### Notes / caveats

- Taulu kuvaa build-runia, ei Markdown-raportin write-runia. Nykyisestä evidenssistä ei löytynyt erillistä report writer -metadataa tähän tauluun.

### `eco_entity_window_snapshot`

#### Meaning

Yksi koontirivi per entity, ikkuna ja päivämäärä. Tarkoitus on tiivistää summary-state, timing, trend, classification, freshness ja quality samaan rakeeseen.

#### Category

`snapshot fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + entity_id`.

#### Important columns

- yhdistelmäpääavain: `run_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`
- `snapshot_status`
- `timing_state`, `trend_state`, `summary_state`, `classification_state`
- `freshness_status`, `quality_status`
- `asof_observed_at`
- `source_run_id`
- audit-aikaleimat

#### How it is populated

- Skeema luodaan migraatiossa `016_create_eco_core_facts_v3.sql`.
- Nykyinen aktiivinen writer latest-build-polussa on `build_canonical_v3_window_snapshots(...)`.
- `plan_canonical_v3_latest_build.py` mukaan tämän builderin lähteet ovat:
  - `dc_ticker_swing_signal_daily`
  - `dc_group_synthetic_ohlc_daily`
  - `eco_entity_coverage`
  - `eco_quality_summary`
  - `eco_classification_decision`
  - `eco_entity_metric_value`
- Tämä on siis selvästi transitional V3 -taulu, koska se riippuu edelleen `dc_*`-tauluista sekä muista `eco_*`-välifakteista.

#### How it is used

- `reporting_v3_query.py` lukee snapshotteja suoraan raporttiosioihin.
- Snapshot builderin metahuomiot query-layereissa sanovat, että `classification_state` ei ole kaikkien raporttien ensisijainen classification-lähde; siihen käytetään `eco_classification_decision`-taulua.

#### Current data status

- `data/analysis.db`:ssa 2328 riviä.
- Ikkunajakauma: `daily` 582, `rolling2` 582, `rolling5` 582, `rolling30` 582.

#### Notes / caveats

- Snapshot on kompakti summary-kerros, ei täydellinen päätöksentekotason lähde.

### `eco_entity_metric_value`

#### Meaning

Geneerinen V3-metriikkafaktataulu sekä numeerisille että tekstipohjaisille metric-riveille.

#### Category

`metric fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + entity_id + metric_name`.

#### Important columns

- yhdistelmäpääavain: `run_id`, `signal_date`, `taxonomy_version_id`, `window_code`, `entity_id`, `metric_name`
- `metric_value_num`, `metric_value_text`, `metric_unit`
- `value_status`
- `source_run_id`
- audit-aikaleimat

#### How it is populated

- Skeema luodaan migraatiossa `016_create_eco_core_facts_v3.sql`.
- Latest-build-polun pääwriterit tämän taulun täyttämiseen ovat:
  - `build_canonical_v3_ticker_daily_direct_metrics`
  - `build_canonical_v3_group_status_from_group_swing`
  - `build_canonical_v3_group_window_status_from_group_swing`
  - `build_canonical_v3_ticker_window_metrics`
  - `build_canonical_v3_group_window_metrics`
  - `build_canonical_v3_group_historical_metrics`
  - `build_canonical_v3_ticker_freshness_from_signal_daily`
  - `build_canonical_v3_group_freshness_metrics`
- `plan_canonical_v3_latest_build.py` mukaan suurin osa näistä writer-polkuista käyttää transitional lähteinä `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` ja/tai `dc_group_synthetic_ohlc_daily`.
- Poikkeus: `build_canonical_v3_group_freshness_metrics` käyttää jo myös V3-lähteitä `eco_entity_event`, `eco_entity_metric_value`, `eco_entity`, `eco_report_run`.

#### How it is used

- `reporting_v3_query.py` käyttää tätä erittäin laajasti ryhmä-, ticker-, ecosystem- ja freshness-metriikoihin.
- Snapshot builder lukee tästä mm. group timing/window status -metriikoita.
- Myöhemmät V3 builderit käyttävät osaa metriikoista toisten derived-metriikoiden pohjana.

#### Current data status

- `data/analysis.db`:ssa 43772 riviä.
- Ikkunajakauma:
  - `daily` 8295
  - `rolling2` 6899
  - `rolling5` 8340
  - `rolling30` 20238
- Usein esiintyviä metric-nimiä tarkistuksessa olivat mm. `return_5d`, `pct_above_ema20`, `group_timing_state`, `distance_to_ema20_pct`, `valid_signal_dates`, `pullback_days`, `exit_risk_days`.

#### Notes / caveats

- Osa builder-koodeista huomauttaa, ettei `source_table`-lineage-kenttää ole tässä taulussa, joten metric-kohtainen lähdetaululinja ei ole täysin eksplisiittinen itse datassa.

### `eco_entity_coverage`

#### Meaning

Coverage- ja completeness-fakta, joka kuvaa kuuluuko entity taxonomyyn/watchlistiin ja löytyykö siltä odotetut syöttökomponentit.

#### Category

`coverage fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + entity_id`.

#### Important columns

- `in_taxonomy`, `in_watchlist`
- `has_instrument`, `has_price_data`, `has_daily_signal`, `has_window_context`
- `coverage_status`
- `source_row_count`, `missing_component_count`, `coverage_notes`

#### How it is populated

- Skeema luodaan migraatiossa `016_create_eco_core_facts_v3.sql`.
- `build_canonical_v3_base_run(...)` laskee nämä rivit.
- Builder käyttää:
  - `eco_entity`
  - `eco_taxonomy_entity_relation`
  - `eco_watchlist`
  - `eco_watchlist_member`
  - `eco_report_window`
  - sekä transitional lähteenä `dc_ticker_swing_signal_daily`, josta päätellään tickerin daily-signal-saatavuus.
- Käytännössä insert-only per uusi `run_id`, replace-run tilassa vanhat saman runin rivit poistetaan.

#### How it is used

- Snapshot builder lukee coverage-rivejä snapshot-grainin kohdejoukon muodostamiseen.
- V3 query layer käyttää peitto- ja watchlist-summariesiin.

#### Current data status

- `data/analysis.db`:ssa 2328 riviä.
- Ikkunajakauma sama kuin snapshoteissa: 582 per ikkuna.

#### Notes / caveats

- Base builderin ticker-availability-logiikka on tarkoituksella konservatiivinen, eikä se vielä kuvaa täydellistä instrumentti-/price-peittoa geneerisesti.

### `eco_quality_summary`

#### Meaning

Laadun yhteenvetorivit run-, window- tai muun scope-tason aggregaateille.

#### Category

`quality fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + quality_scope + scope_entity_id`.

#### Important columns

- `quality_summary_id`: tekninen pääavain.
- `quality_scope`: `RUN`, `WINDOW`, `ECOSYSTEM`, `LAYER`, `SUBINDUSTRY`, `TICKER`, `SOURCE`.
- `scope_entity_id`
- `quality_status`
- `expected_count`, `actual_count`, `missing_count`, `incomplete_count`, `stale_count`, `warning_count`, `error_count`
- `summary_note`

#### How it is populated

- Skeema luodaan migraatiossa `016_create_eco_core_facts_v3.sql`.
- Nykyinen writer on `build_canonical_v3_base_run(...)`.
- Summary-rivit johdetaan coverage-riveistä, eli käytännössä sama transitional riippuvuus kuin coverage-taulussa.

#### How it is used

- Snapshot builder lukee quality-rivejä täydentääkseen snapshotin `quality_status`-kontekstia.
- Query layer lukee quality summary -osioita V3-raportteihin.

#### Current data status

- `data/analysis.db`:ssa 16 riviä.
- Tämä vastaa nykyisessä datassa 2 runia × 4 ikkunaa × 2 scopea (`RUN` ja `WINDOW`).

#### Notes / caveats

- Nykyisessä base builderissä laadun summary näyttää keskittyvän lähinnä `RUN`- ja `WINDOW`-tasoihin.

### `eco_signal_observation`

#### Meaning

Havaittujen signaalien faktataulu.

#### Category

`signal fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + entity_id + signal_name + observed_date`.

#### Important columns

- `signal_observation_id`: tekninen pääavain.
- run- ja entity-kontekstisarakkeet.
- `signal_name`, `signal_family`, `signal_direction`, `signal_value`
- `observed_date`
- `source_table`, `source_run_id`, `source_event_id`
- `signal_status`

#### How it is populated

- Skeema luodaan migraatiossa `017_create_eco_signal_event_facts_v3.sql`.
- Latest-build-polussa writerit ovat:
  - `build_canonical_v3_ticker_freshness_from_signal_daily`
  - `build_canonical_v3_ma_status`
  - `build_canonical_v3_ma_break_status`
  - `build_canonical_v3_signal_relevance`
- `plan_canonical_v3_latest_build.py` mukaan lähteet ovat:
  - `dc_ticker_swing_signal_daily` MA- ja freshness-signaaleille
  - `technical_signal_relevance` technical relevance -pilotille
- Tämä taulu on siis aktiivinen mutta osin transitional, koska suuri osa signaaleista tulee yhä `dc_*`-taulusta.

#### How it is used

- `reporting_v3_query.py` lukee daily- ja rolling-raporttien signal-observation-osioita tästä.
- `eco_signal_relevance` linkittyy tähän `signal_observation_id`:n kautta.

#### Current data status

- `data/analysis.db`:ssa 8125 riviä.
- Ikkunajakauma:
  - `daily` 3514
  - `rolling2` 1537
  - `rolling5` 1537
  - `rolling30` 1537
- `source_table`-jakauma tarkistushetkellä:
  - `dc_ticker_swing_signal_daily` 7408
  - `dc_group_synthetic_ohlc_daily` 628
  - `technical_signal_relevance` 89

#### Notes / caveats

- Technical relevance -pilot koskee tarkastetun builderin perusteella vain `window_code='daily'`.

### `eco_signal_relevance`

#### Meaning

Signaalin relevanssitulkinta yhdelle signal observation -riville.

#### Category

`signal fact`

#### Granularity

Yksi rivi per `signal_observation_id + relevance_label`.

#### Important columns

- `signal_relevance_id`
- `signal_observation_id`
- `relevance_label`, `relevance_score`, `relevance_reason`
- `trend_alignment`, `dow_context`, `bos_context`, `reset_context`, `counter_trend_context`
- `assigned_at_utc`

#### How it is populated

- Skeema luodaan migraatiossa `017_create_eco_signal_event_facts_v3.sql`.
- Writer on `build_canonical_v3_signal_relevance(...)`.
- Builder lukee lähteensä `technical_signal_relevance`-taulusta ja kirjoittaa samalla tarvittavat `eco_signal_observation`-rivit.
- Ei nojaa legacy `dc_*` -tauluihin, mutta nojaa erilliseen `technical_signal_relevance`-pilottilähteeseen.

#### How it is used

- `reporting_v3_query.py` left-joinaa relevanssirivejä signal observation -osioihin.
- Daily V3 -raporteissa tätä käytetään optionaalisena lisäkontekstina.

#### Current data status

- `data/analysis.db`:ssa 89 riviä.

#### Notes / caveats

- Tämä näyttää vielä rajatummalta pilotilta kuin muut signaalifaktit.

### `eco_entity_event`

#### Meaning

Entityyn liitetty tapahtumahistoria kuten BOS, RESET, structure change ja trend state change.

#### Category

`event fact`

#### Granularity

Yksi rivi per `run_id + taxonomy_version_id + entity_id + event_date + event_type + event_key`.

#### Important columns

- `entity_event_id`
- run- ja entity-kontekstisarakkeet
- `event_date`, `event_type`, `event_key`, `event_label`
- `event_direction`, `event_status`
- `source_table`, `source_run_id`, `source_event_id`, `event_payload_ref`

#### How it is populated

- Skeema luodaan migraatiossa `017_create_eco_signal_event_facts_v3.sql`.
- Latest-build-polun writerit:
  - `build_canonical_v3_ticker_structure_events`
  - `build_canonical_v3_group_structure_events`
- Lähteet plan-CLI:n mukaan:
  - `stock_dow_structure_events`
  - `dc_group_synthetic_ohlc_daily`
- Taulu on siis aktiivinen, mutta group-event-polku on edelleen transitional `dc_*`-lähteeseen sidottu.

#### How it is used

- `reporting_v3_query.py` lukee structural event -osioita tästä.
- `build_canonical_v3_group_freshness_metrics(...)` käyttää tätä derived freshness -metriikoiden lähteenä.

#### Current data status

- `data/analysis.db`:ssa 13213 riviä.
- `source_table`-jakauma:
  - `stock_dow_structure_events` 11668
  - `dc_group_synthetic_ohlc_daily` 1545
- `event_type`-jakaumassa näkyivät tarkistuksessa ainakin `BOS`, `RESET`, `STRUCTURE_CHANGE`, `TREND_STATE_CHANGE`.

#### Notes / caveats

- Ticker-eventit näyttävät vähemmän transitional kuin group-eventit, koska niiden päälähde ei ole `dc_*`.

### `eco_classification_decision`

#### Meaning

Canonical V3 classifier / decision -taulu raporttimaisille tiloille kuten `daily_trigger`, `rolling2_sell_pressure`, `rolling5_pullback`, `rolling30_buy`, `rolling30_exit`.

#### Category

`event fact`

#### Granularity

Yksi rivi per `run_id + signal_date + taxonomy_version_id + window_code + entity_id + classification_type`.

#### Important columns

- `classification_id`
- run- ja entity-kontekstisarakkeet
- `classification_type`, `classification_state`
- `primary_reason`, `blocking_reason`, `risk_reason`, `next_action`
- `priority_score`, `priority_label`, `sort_rank`
- `source_classifier`, `classification_version`, `source_run_id`
- `decision_status`

#### How it is populated

- Skeema luodaan migraatiossa `018_create_eco_classification_decision_v3.sql`.
- Aktiivinen latest-build-polku ei käytä vanhaa `build_canonical_v3_classification_decisions(...)`-builderia, vaan neljää replacement-builderia:
  - `build_canonical_v3_daily_trigger_classifications`
  - `build_canonical_v3_rolling2_sell_pressure_classifications`
  - `build_canonical_v3_rolling5_pullback_classifications`
  - `build_canonical_v3_rolling30_watchlist_classifications`
- `plan_canonical_v3_latest_build.py` mukaan nämä kaikki nojaavat transitional lähteisiin:
  - `dc_ticker_swing_signal_daily`
  - `dc_group_swing_signal_daily`
- Vanha geneerinen builder `rawcandle/report_canonical_v3_classification_decision_builder.py` käyttää lähdettä `dc_report_classification_v2`, mutta se on plan-CLI:n mukaan bypassattu eikä kuulu sallittuun latest-build-sekvenssiin.

#### How it is used

- `reporting_v3_query.py` lukee classificationit tästä ja dokumentoi eksplisiittisesti, että tämä on ensisijainen classification-lähde.
- `build_canonical_v3_window_snapshots(...)` lukee tämän taulun classification-statejen poimintaan.
- `write_latest_v3_markdown_reports.py` käyttää tätä query-layerin kautta.

#### Current data status

- `data/analysis.db`:ssa 2362 riviä.
- Tarkistuksessa löytyneet classification-tyyppien rivimäärät:
  - `daily_trigger` 474
  - `rolling2_sell_pressure` 472
  - `rolling5_pullback` 472
  - `rolling30_buy` 472
  - `rolling30_exit` 472

#### Notes / caveats

- Taulu on jo aktiivinen ja käytössä, mutta sen lähteet ovat edelleen selvästi transitional `dc_*`-pohjaisia.

## Relationship between the `eco_*` tables

V3-datamallin tarkistettu virtaus näyttää tältä:

1. Migraatiot luovat `eco_*`-skeeman ja seedaavat `eco_report_window`-taulun.
2. Taxonomy importer luo `eco_ecosystem`, `eco_taxonomy_version`, `eco_entity` ja `eco_taxonomy_entity_relation` -rivit.
3. Watchlist importer luo `eco_watchlist`- ja `eco_watchlist_member` -rivit.
4. Base builder luo `eco_report_run`-rivin sekä saman ajon `eco_entity_coverage`- ja `eco_quality_summary` -rivit.
5. Metric-, signal-, event- ja classification-builderit materialisoivat varsinaiset V3-faktit:
   - `eco_entity_metric_value`
   - `eco_signal_observation`
   - `eco_signal_relevance`
   - `eco_entity_event`
   - `eco_classification_decision`
6. Snapshot builder kokoaa osan näistä yhteenvetotasoksi `eco_entity_window_snapshot`.
7. Query layer ja Markdown-raportit lukevat faktit pääosin `run_id + entity + window + signal_date` -rakeelta.

Suhteet tiivistettynä:

- `eco_ecosystem` määrittää ylimmän domainin.
- `eco_taxonomy_version` versioi rakenteen.
- `eco_entity` tallentaa kaikki solmut.
- `eco_taxonomy_entity_relation` yhdistää solmut hierarkiaksi.
- `eco_watchlist` ja `eco_watchlist_member` lisäävät käyttäjän fokusjoukon.
- `eco_report_window` vakioi horizonit.
- `eco_report_run` ankkuroi yhden materialisointiajon.
- `eco_entity_coverage` ja `eco_quality_summary` kuvaavat peittoa ja laatua.
- `eco_entity_metric_value`, `eco_signal_observation`, `eco_signal_relevance`, `eco_entity_event` ja `eco_classification_decision` kuvaavat varsinaisen analyysifaktakerroksen.
- `eco_entity_window_snapshot` on koontikerros, ei koko mallin ainoa source of truth.

## Source lineage and dependency mapping

| V3 table | Main source inputs | Legacy `dc_*` dependency? | Builder / importer | Notes |
|---|---|---|---|---|
| `eco_ecosystem` | importer-parametrit / kovakoodattu `DATACENTER` | no | taxonomy importer, watchlist importer | master-rivi varmistetaan importerissa |
| `eco_taxonomy_version` | taxonomy CSV metadata | no | taxonomy importer | `source_type=CSV` |
| `eco_entity` | taxonomy CSV, watchlist TXT | no | taxonomy importer, watchlist importer | watchlist importer voi luoda `WATCH_ONLY`-tickerit |
| `eco_taxonomy_entity_relation` | taxonomy CSV | no | taxonomy importer | membership-role mapataan source-statuksesta |
| `eco_watchlist` | watchlist TXT + importer-parametrit | no | watchlist importer | source tallennetaan `TXT`-viitteeksi |
| `eco_watchlist_member` | watchlist TXT + `eco_entity` | no | watchlist importer | riippuu olemassa olevista tai luoduista ticker-entityistä |
| `eco_report_window` | migraation seed-data | no | migration seed | ei erillistä runtime writeria |
| `eco_report_run` | `eco_*` master data + `dc_ticker_swing_signal_daily` saatavuustarkistus | yes, transitional | `build_canonical_v3_base_run` | run-status perustuu coverageyn |
| `eco_entity_coverage` | `eco_entity`, taxonomy relations, watchlistit, `dc_ticker_swing_signal_daily` | yes, transitional | `build_canonical_v3_base_run` | daily-signal-saatavuus tulee legacy daily -taulusta |
| `eco_quality_summary` | `eco_entity_coverage` | yes, transitional | `build_canonical_v3_base_run` | riippuu coverage-polun legacy-lähteestä |
| `eco_entity_metric_value` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, osin `eco_entity_event` | yes, transitional | useat V3 metric builderit | yksi taulu, monta writeria |
| `eco_classification_decision` | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily` | yes, transitional | daily/rolling replacement classifier builderit | vanha V2-lähteinen builder on bypassattu |
| `eco_entity_window_snapshot` | `dc_ticker_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, `eco_entity_coverage`, `eco_quality_summary`, `eco_classification_decision`, `eco_entity_metric_value` | yes, transitional | `build_canonical_v3_window_snapshots` | koontikerros useista lähteistä |
| `eco_signal_observation` | `dc_ticker_swing_signal_daily`, `technical_signal_relevance`, osin `dc_group_synthetic_ohlc_daily` | yes, transitional | MA/freshness/signal-relevance builderit | yksi taulu, monta signal-perhettä |
| `eco_signal_relevance` | `technical_signal_relevance`, `eco_signal_observation` | unclear | `build_canonical_v3_signal_relevance` | ei suoraa `dc_*`-lähdettä, mutta ei täysin V3-native source-of-truth |
| `eco_entity_event` | `stock_dow_structure_events`, `dc_group_synthetic_ohlc_daily` | yes, transitional | ticker/group event builderit | ticker- ja group-eventeillä eri source lineage |

## Build / refresh flow

Tunnettu refresh-polku tarkastetun koodin perusteella:

1. V3-migraatiot:
   - `rawcandle/report_canonical_v3_migration.py`
   - SQL:t `015`, `016`, `017`, `018`
2. Taxonomy import:
   - Python-funktio `import_datacenter_taxonomy_to_v3(...)`
   - tarkka CLI-komento ei varmistunut tarkastetuista tiedostoista
3. Watchlist import:
   - Python-funktio `import_datacenter_watchlist_to_v3(...)`
   - tarkka CLI-komento ei varmistunut tarkastetuista tiedostoista
4. V3 latest build:
   - CLI `rawcandle/cli/run_canonical_v3_latest_build.py`
   - planner `rawcandle/cli/plan_canonical_v3_latest_build.py`
   - sallittu build-sekvenssi materialisoi nykyiset V3-faktit vaiheittain
5. Inspect / audit:
   - CLI `rawcandle/cli/inspect_canonical_v3.py`
6. Markdown-raporttien luku:
   - CLI `rawcandle/cli/write_latest_v3_markdown_reports.py`
   - tämä lukee `eco_*`-dataa, ei kirjoita sitä

Varmistettu V3 latest build -sekvenssi sisältää ainakin:

1. `build_canonical_v3_base_run`
2. metric-builderit
3. replacement classification-builderit
4. `build_canonical_v3_window_snapshots`
5. MA- ja relevance-signal-builderit
6. ticker/group event-builderit
7. `build_canonical_v3_group_freshness_metrics`

Tarkka taxonomy- tai watchlist-importin tuotanto-CLI ei varmistunut tarkastetuista tiedostoista.

## Current role versus legacy `dc_*` model

V3 `eco_*` -malli eroaa legacy Datacenter `dc_*` -mallista näin:

- `eco_*` on geneerinen ecosystem/entity-malli, kun taas `dc_*` on Datacenter-spesifi.
- V3 normalisoi master-datan erillisiin dimension- ja relation-tauluihin.
- V3 yrittää tehdä raporteista downstream-kuluttajia, ei ensisijaisia tietorakenteita.
- Legacy `dc_*` -mallissa moni raporttisemantiikka syntyy suoraan Datacenter-rakenteista tai renderöintikerroksessa.

Nykytilan tarkastettu tulkinta:

- master data -kerros (`eco_ecosystem`, `eco_taxonomy_version`, `eco_entity`, `eco_taxonomy_entity_relation`, `eco_watchlist`, `eco_watchlist_member`, `eco_report_window`) on jo selvästi V3-native
- operational ja facts -kerros on suurelta osin jo `eco_*`-tauluissa
- kuitenkin useimmat nykyiset writerit käyttävät edelleen transitional lähteinä legacy `dc_*` -tauluja

Selvimmin transitional `dc_*`-riippuvaisia näyttävät:

- `eco_report_run`
- `eco_entity_coverage`
- `eco_quality_summary`
- `eco_entity_window_snapshot`
- suuri osa `eco_entity_metric_value`-riveistä
- suuri osa `eco_signal_observation`-riveistä
- `eco_classification_decision`
- group-puolen osa `eco_entity_event`-riveistä

Tämä tarkoittaa, että `dc_*`-taulujen poistaminen liian aikaisin rikkoisi nykyisen V3 latest build -polun, vaikka V3-raportit jo lukevatkin `eco_*`-tauluja.

## Data completeness and known gaps

Kevyen DB-tarkistuksen perusteella kaikki löydetyt `eco_*` -taulut ovat olemassa `data/analysis.db`:ssa ja kaikissa niissä on rivejä.

Tiivis status:

- master/dimension-taulut ovat olemassa ja täytettyjä
- kaksi `eco_report_run`-ajoa löytyi
- coverage-, quality-, snapshot-, metric-, signal-, relevance-, event- ja classification-taulut ovat kaikki populated

Tunnettuja tai todennäköisiä aukkoja:

- `eco_entity_metric_value` ei sisällä omaa `source_table`-saraketta, joten metric-kohtainen lineage ei ole täysin eksplisiittinen itse taulussa
- `eco_signal_relevance` näyttää nykyisessä datassa paljon pienemmältä pilotilta kuin muu signal-kerros
- `eco_classification_decision` on aktiivinen, mutta syötteet ovat edelleen transitional `dc_*`-pohjaisia
- `eco_entity_window_snapshot.classification_state` ei ole query-layerin oman evidenssin mukaan ensisijainen classification-lähde
- watchlist-importin testit vahvistavat, että taxonomyssa puuttuvat tickerit voidaan joko jättää varoituksiksi tai luoda `WATCH_ONLY`-entityinä; tämä on tärkeä täydellisyyskäyttäytyminen

Valid trading day -ikkunat:

- `eco_report_window.window_days` tallentaa nimelliset päivämäärät 1/2/5/30
- builderien tuotantokäytäntö näyttää nojaavan Datacenterin valid signal / trading day -lähteisiin
- mutta kaikkien builderien tarkka window-day-semanttiikka ei selviä täydellisesti tästä rajatusta tarkastuksesta, joten asia jää osin avoimeksi

## Evidence inspected

### Migrations / schema

- `rawcandle/report_canonical_v3_migration.py`: varmisti, mitkä migraatiot kuuluvat V3 `eco_*` -skeemaan.
- `rawcandle/sqlite/migrations/015_create_eco_base_dimensions_v3.sql`: varmisti dimension-, relation-, watchlist- ja window-taulujen rakenteen sekä seeded ikkunat.
- `rawcandle/sqlite/migrations/016_create_eco_core_facts_v3.sql`: varmisti run-, coverage-, quality-, snapshot- ja metric-faktataulujen skeeman.
- `rawcandle/sqlite/migrations/017_create_eco_signal_event_facts_v3.sql`: varmisti signal- ja event-faktataulujen skeeman.
- `rawcandle/sqlite/migrations/018_create_eco_classification_decision_v3.sql`: varmisti myöhemmin lisätyn `eco_classification_decision`-taulun skeeman.

### Importers / seeders

- `rawcandle/report_canonical_v3_taxonomy_import.py`: varmisti, miten taxonomy CSV materialisoidaan `eco_ecosystem`, `eco_taxonomy_version`, `eco_entity` ja `eco_taxonomy_entity_relation` -tauluihin.
- `rawcandle/report_canonical_v3_watchlist_import.py`: varmisti, miten watchlist TXT materialisoidaan `eco_watchlist`- ja `eco_watchlist_member` -tauluihin sekä miten puuttuvat ticker-entityt käsitellään.

### V3 builders / writers

- `rawcandle/report_canonical_v3_base_builder.py`: varmisti `eco_report_run`, `eco_entity_coverage` ja `eco_quality_summary` -taulujen writer-polun sekä niiden nykyisen riippuvuuden `dc_ticker_swing_signal_daily`-tauluun.
- `rawcandle/report_canonical_v3_window_snapshot_replacement_builder.py`: varmisti `eco_entity_window_snapshot`-taulun koontirakenteen ja riippuvuuden coverage-, quality-, classification-, metric- ja osin `dc_*`-lähteisiin.
- `rawcandle/report_canonical_v3_signal_relevance_builder.py`: varmisti `eco_signal_observation`- ja `eco_signal_relevance` -taulujen technical relevance -pilottilähteen.
- `rawcandle/report_canonical_v3_entity_event_builder.py`: varmisti ticker-eventtien materialisoinnin `eco_entity_event`-tauluun lähteestä `stock_dow_structure_events`.
- `rawcandle/report_canonical_v3_classification_decision_builder.py`: varmisti vanhemman geneerisen classification-builderin ja sen V2-lähteisen `dc_report_classification_v2` -riippuvuuden.

### V3 readers / reports

- `rawcandle/reporting_v3_query.py`: varmisti, mitä `eco_*`-tauluja V3 query layer ja Markdown-raportit lukevat sekä sen, että classificationit tulevat ensisijaisesti `eco_classification_decision`-taulusta.
- `rawcandle/cli/write_latest_v3_markdown_reports.py`: varmisti, että latest Markdown -CLI valitsee `eco_report_run`-ajon ja lukee V3-faktit report writerin kautta.

### CLIs / pipeline / scheduler

- `rawcandle/cli/run_canonical_v3_latest_build.py`: varmisti sallitun latest-build-sekvenssin, target-taulut ja replace-cleanup-logiikan.
- `rawcandle/cli/plan_canonical_v3_latest_build.py`: varmisti build-vaiheiden eksplisiittisen lähde- ja kohdetaulukartan sekä bypassatut V2-riippuvaiset builderit.
- `rawcandle/cli/inspect_canonical_v3.py`: varmisti virallisen inspect-CLI:n odottamat V3-taulut ja sen, mitä summary-dataa se näyttää.

### Tests

- `tests/test_canonical_v3_base_schema.py`: varmisti base-dimension-taulujen constraintit, uniqueness-säännöt ja `eco_report_window` seed-rivit.
- `tests/test_canonical_v3_core_fact_schema.py`: varmisti ydinfaktataulujen constraintit, rakeet ja indeksit.
- `tests/test_canonical_v3_taxonomy_import.py`: varmisti taxonomy-importin idempotenssin, relation-rakenteen ja multi-membership-käyttäytymisen.
- `tests/test_canonical_v3_watchlist_import.py`: varmisti watchlist-importin idempotenssin ja puuttuvien ticker-entityjen käsittelyn.
- `tests/test_inspect_canonical_v3_cli.py`: varmisti inspect-CLI:n lukutavan sekä sen, ettei CLI luo puuttuvia tauluja sivuvaikutuksena.
- `tests/test_run_canonical_v3_latest_build_cli.py`: varmisti latest-build-CLI:n hyväksytyn target-taulujoukon ja build-vaiheiden taulukohtaisen vaikutuksen.

### Existing docs

- `docs/canonical_v3_ecosystem_entity_model_design.md`: tarjosi V3-mallin tavoitearkkitehtuurin ja auttoi erottamaan suunnittelutavoitteen nykyisestä toteutuksesta.
- `docs/canonical_v3_classification_report_state_design.md`: tarjosi taustan `eco_classification_decision`-taulun roolille ja päätössemantiikalle.
- `docs/datacenter_dc_tables_reference.md`: tarjosi legacy `dc_*` -taulujen merkitykset V3 transition-contextia varten.
- `docs/datacenter_legacy_report_generation_reference.md`: tarjosi legacy-raporttipolun kontekstin, jota vasten V3-mallin riippuvuuksia voitiin verrata.

### Lightweight DB inspection

- `data/analysis.db`: varmisti nykyisen paikallisen DB-instanssin `eco_*`-taulut, rivimäärät, runit, ikkuna-jakaumat sekä joidenkin `source_table`- ja `classification_type`-jakaumien nykytilan.

## Open questions

- Mikä osa nykyisistä `eco_entity_metric_value`-metriikoista on tarkoitus siirtää täysin pois `dc_*`-lähteistä ja missä järjestyksessä?
- Onko `technical_signal_relevance` tarkoitus jäädä pysyväksi upstream-lähteeksi `eco_signal_relevance`-taululle vai korvautuuko se myöhemmin puhtaasti V3-native lähteellä?
- Ovatko kaikki nykyiset V3 Markdown -raporttiosiot jo kokonaan `eco_*`-taulupohjaisia, vai lukeeko jokin raporttikerros edelleen rinnalla suoraan legacy-tauluja?
- Onko kaikkien rolling-builderien ikkunasemantiikka varmasti valid trading day -pohjainen, vai perustuuko osa vielä johonkin muuhun lähteessä implisiittiseen päivälaskentaan?
- Milloin vanha `rawcandle/report_canonical_v3_classification_decision_builder.py` voidaan poistaa turvallisesti, kun replacement-builderit näyttävät jo olevan latest-build-polun aktiivinen reitti?
- Pitäisikö `eco_entity_metric_value`-tauluun lisätä joskus eksplisiittisempi source-lineage, vai riittääkö nykyinen builder-kohtainen dokumentaatio?
