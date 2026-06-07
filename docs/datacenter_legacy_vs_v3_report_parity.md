# Datacenter legacy vs V3 report parity

## Purpose of this document

Tämä dokumentti vertailee legacy Datacenter -raportteja `datacenter_daily`, `datacenter_rolling_30`, `datacenter_rolling_5` ja `datacenter_rolling_2` vastaaviin V3-raportteihin `daily`, `rolling30`, `rolling5` ja `rolling2`.

Tavoite on arvioida raporttien sisältöpariteettia, jäljellä olevia eroja, tunnettuja puutteita ja sitä, missä määrin V3-polku on valmis korvaamaan legacy-polun.

## Scope

Tämä dokumentti kattaa:

- legacy-raporttien ja V3-raporttien sisällöllisen pariteetin
- source- ja lineage-erot `dc_*`- ja `eco_*` -polkujen välillä
- output- ja operointierot, kuten `CSV output`
- korvausvalmiuden karkean arvion

Tämä dokumentti ei kata:

- uusien builderien suunnittelua
- runtime-logiikan muutoksia
- dashboard-UI:n yksityiskohtaista pariteettia

## Executive summary

V3-raportit ovat jo selvästi lähempänä legacy-raportteja kuin eri raporttisukupolvi yleensä olisi: daily-rakenne on suurelta osin sama, ja rolling-raporteissa horizon-kohtaiset ydinluokitukset ovat mukana myös V3:ssa. Suurimmat erot eivät ole perusotsikoissa vaan muutamassa operatiivisesti merkittävässä kohdassa.

Vahvimmat parity gapit ovat:

- legacy tuottaa Markdownin lisäksi CSV:n, mutta V3 renderöi vain Markdownia
- legacy daily sisältää täydemmän dashboard-yhteenvedon; V3 daily ilmoittaa itse, että full legacy dashboard aggregation ei ole nykyisestä query-datasta saatavilla
- legacy rolling -raporteissa on eksplisiittiset `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot, joille V3 rolling -polussa ei näy täysin saman nimistä tai saman rakenteista vastinetta
- legacy sisältää taxonomy listing -osion, jota V3 Markdown -polku ei näytä

Samalla V3:ssa on jo joitakin vahvuuksia, joita legacyssä ei ole samalla tavalla eriytetty:

- renderöinti tapahtuu suoraan `eco_*`-faktamallista
- rolling-raporteissa on eksplisiittiset `Structural events`, `Signal observations` ja `V3 metadata / limitations appendix` -osiot
- latest-run-valinta on sidottu `eco_report_run`-metatietoon eikä vain tiedostonimipohjaiseen raporttigenerointiin

## High-level comparison

| Pair | Legacy source model | V3 source model | Output parity | Section parity | Replacement view |
|---|---|---|---|---|---|
| `datacenter_daily` vs V3 `daily` | suora `dc_*` render | suora `eco_*` render | partial | near parity | close, but not full |
| `datacenter_rolling_30` vs V3 `rolling30` | suora `dc_*` render | suora `eco_*` render | partial | partial to near parity | usable with gaps |
| `datacenter_rolling_5` vs V3 `rolling5` | suora `dc_*` render | suora `eco_*` render | partial | partial to near parity | usable with gaps |
| `datacenter_rolling_2` vs V3 `rolling2` | suora `dc_*` render | suora `eco_*` render | partial | partial to near parity | usable with gaps |

## Report section parity matrix

| Section / capability | Legacy daily | V3 daily | Legacy rolling | V3 rolling | Parity assessment |
|---|---|---|---|---|---|
| Title and run metadata | yes | yes | yes | yes | full |
| Watchlist Summary | yes | yes | yes | yes | full or near full |
| Dashboard | yes | yes | no | no | partial; V3 daily weaker |
| Rotation Risk / Overheat Index | yes | yes | as progression | as progression | near full |
| Subindustry timing sections | yes | yes | yes | yes | near full |
| Synthetic OHLC Structure Summary | yes | yes | no | no | near full in daily |
| Group Structure Breaks / Resets | yes | yes | no | no | near full in daily |
| Breakout / Pullback / Exit-Risk ticker scanners | yes | yes | repeated variants | repeated variants | near full |
| Daily Triggers | yes | yes | no | no | near full |
| `Rolling 30 Buy Filter` | no | no | yes | yes | near full |
| `Rolling 30 Exit Prefilter` | no | no | yes | yes | near full |
| `Rolling 5 Pullback Alerts` | no | no | yes | yes | near full |
| `Rolling 2 Sell Pressure` | no | no | yes | yes | near full |
| `Swing MA Break Status` | yes | yes | yes | not explicit | partial |
| `Swing Signal Freshness` | yes | yes | yes | not explicit | partial |
| Data Quality | yes | yes | yes | yes | near full |
| Missing / Incomplete Inputs Summary | yes | yes | yes | yes | near full |
| Technical Relevance Context | optional yes | conditional yes | yes | not explicit | partial |
| Taxonomy listing | yes | no | yes | no | missing in V3 |
| `CSV output` | yes | no | yes | no | missing in V3 |
| `Structural events` | no explicit named section | limited via daily content | no explicit named section | yes | V3-only emphasis |
| `Signal observations` | no explicit named section | implicit via daily sections | no explicit named section | yes | V3-only emphasis |
| `V3 metadata / limitations appendix` | no | yes | no | yes | V3-only |

## Daily parity

### `datacenter_daily` vs V3 `daily`

Daily-pari on lähimpänä täyttä korvattavuutta. V3 `daily` säilyttää lähes kaikki legacy daily -raportin näkyvät pääosiot: `Watchlist Summary`, `Dashboard`, `Rotation Risk / Overheat Index`, `Subindustry Timing States`, zone-osiot, `Synthetic OHLC Structure Summary`, `Group Structure Breaks / Resets`, ticker-scannerit, `Daily Triggers`, `Swing MA Break Status`, `Swing Signal Freshness`, `Data Quality`, `Missing / Incomplete Inputs Summary` ja `Technical Relevance Context`.

Selvin daily-gap on dashboardissa. Tarkastettu V3-renderer lisää näkyvän rajoitusviestin siitä, että full legacy dashboard aggregation ei ole nykyisestä query-datasta saatavilla. Tämä tarkoittaa, että daily-rakenne on otsikkotasolla lähellä legacyä, mutta kaikki legacy-koonnit eivät vielä näytä siirtyneen V3 query -malliin.

Toinen näkyvä daily-ero on taxonomy listing. Legacy-dokumentaation mukaan daily voi näyttää Datacenter taxonomy listing -osion, mutta V3 daily päättyy sen sijaan `V3 metadata / limitations appendix` -osioon.

Parity assessment: `near parity with known dashboard and taxonomy gaps`.

## Rolling 30 parity

### `datacenter_rolling_30` vs V3 `rolling30`

Tässä parissa ydinikkunalogiikka ja tärkeimmät watchlist-/classification-osiot ovat pääosin mukana molemmissa. Legacy `datacenter_rolling_30` ja V3 `rolling30` sisältävät `Window summary`, `Watchlist Summary`, `Ecosystem window change`, `Overheat / rotation risk progression`, subindustry-persistence- ja deterioration/improvement-näkymät, repeated ticker -osiot sekä `Rolling 30 Buy Filter`- ja `Rolling 30 Exit Prefilter` -osiot.

Suurin sisällöllinen ero on siinä, että V3 rolling -polku painottaa enemmän geneerisiä `Structural events`- ja `Signal observations` -kokonaisuuksia, kun taas legacy rolling nostaa näkyvämmin `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot omilla otsikoillaan. Tarkastetun rendererin perusteella tämä ei ole yksi yhteen -pariteetti.

Operatiivinen ero on sama kuin muuallakin: legacy tuottaa Markdownin lisäksi CSV:n, V3 ei.

Parity assessment: `partial to near parity; missing explicit rolling MA/freshness parity and CSV`.

## Rolling 5 parity

### `datacenter_rolling_5` vs V3 `rolling5`

Legacy `datacenter_rolling_5` ja V3 `rolling5` näyttävät molemmat saman horizonin olennaisen erikoisosion `Rolling 5 Pullback Alerts`. Myös yleinen rolling-rakenne, kuten `Watchlist Summary`, window change / progression -osiot ja repeated ticker -osiot, on mukana molemmissa.

Kuten `rolling30`-parissa, parity ei kuitenkaan ole täydellinen. Legacy näyttää eksplisiittisiä MA break- ja freshness-yhteenvetoja sekä taxonomy listingin, kun taas V3 rolling -render painottaa enemmän V3-signaali- ja event-rakennetta eikä tuota taxonomy listingiä tai CSV:tä.

Parity assessment: `partial to near parity; good horizon coverage, but not output-complete`.

## Rolling 2 parity

### `datacenter_rolling_2` vs V3 `rolling2`

Legacy `datacenter_rolling_2` ja V3 `rolling2` kohtaavat hyvin horizon-kohtaisessa päätehtävässään: molemmissa näkyy `Rolling 2 Sell Pressure` sekä yleinen rolling-yhteenvetorakenne. Tämä viittaa siihen, että lyhimmän rolling-horizonin ydinluokitus on jo siirretty V3:een melko hyvin.

Jäljellä olevat erot ovat käytännössä samat kuin muissa rolling-pareissa: V3 ei renderöi CSV:tä, taxonomy listing puuttuu, eikä legacy-tyyppisiä `Swing MA Break Status`- ja `Swing Signal Freshness` -otsikoita näy rolling-raportissa samalla tavalla.

Parity assessment: `partial to near parity; core sell-pressure view exists, but legacy operational parity is incomplete`.

## Source and lineage differences

Legacy-raportit renderöivät suoraan `dc_*`-tauluista. Tämän dokumentin kannalta keskeiset lähteet ovat:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- epäsuorana upstream-lähteenä myös `dc_group_index_daily`

V3-raportit renderöivät tarkastetun query- ja Markdown-polun perusteella suoraan `eco_*`-tauluista, erityisesti:

- `eco_report_run`
- `eco_entity_window_snapshot`
- `eco_entity_metric_value`
- `eco_entity_coverage`
- `eco_quality_summary`
- `eco_signal_observation`
- `eco_signal_relevance`
- `eco_entity_event`
- `eco_classification_decision`

Tärkeä ero on, että render-vaiheessa V3 on `eco_*`-only, mutta osa V3 facts -kerroksesta on edelleen transitional ja saa sisältöä legacy-henkisistä upstream-lähteistä. Tämä tarkoittaa, että V3 renderöinti on arkkitehtuurisesti uudempi, mutta koko datalinja ei ole vielä varmasti täysin irti legacy-ajattelusta.

## Output and operational differences

Legacy-polku tuottaa per raportti Markdownin ja CSV:n. Tiedostonimissä on tyypillisesti raporttipäivä ja ajonaikainen kellonaika sekä `_full`-suffiksi. V3-polku tuottaa vain yhden Markdown-tiedoston per horizon, ilman CSV-vastinetta ja ilman legacy-tyyppistä `_full`-nimeämistä.

V3 latest-run-polku valitsee raporttiajon `eco_report_run`-taulusta statuksen, taxonomy-version, ekosysteemin ja `signal_date`-järjestyksen perusteella. Legacy-polku on suoraviivaisempi writer-CLI datacenter-raporttien yli.

Scheduler-kontekstissa legacy- ja V3-raportit kulkevat erillisinä tulosryhminä. Tämä tukee tulkintaa, että tuotantokäytössä ne on suunniteltu rinnakkaisiksi eikä vielä kovaksi yksi-yhteen -korvaukseksi.

## Replacement readiness assessment

| Pair | Readiness | Main blockers / caveats |
|---|---|---|
| `datacenter_daily` -> V3 `daily` | medium-high | dashboard parity ei täysi, taxonomy listing puuttuu, ei CSV:tä |
| `datacenter_rolling_30` -> V3 `rolling30` | medium | ei CSV:tä, explicit MA/freshness parity epäselvä, taxonomy listing puuttuu |
| `datacenter_rolling_5` -> V3 `rolling5` | medium | ei CSV:tä, explicit MA/freshness parity epäselvä, taxonomy listing puuttuu |
| `datacenter_rolling_2` -> V3 `rolling2` | medium | ei CSV:tä, explicit MA/freshness parity epäselvä, taxonomy listing puuttuu |

Kokonaisarvio: V3 näyttää jo riittävän kypsältä sisällölliseen rinnakkaisajoon ja monessa osassa myös käytännön lukuraportiksi, mutta tarkastetun evidenssin perusteella sitä ei vielä pitäisi kutsua täysin parity-complete legacy-korvaajaksi.

## Recommended next development candidates

- Selvitä, onko `CSV output` tuotannossa vielä pakollinen downstream-kuluttajille; jos on, tämä on konkreettinen parity blocker.
- Tarkenna, pitääkö legacy daily -dashboardin kaikki aggregaatit toistaa V3:ssa vai riittääkö nykyinen osittainen dashboard-versio.
- Päätä, ovatko legacy rolling -raporttien `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot pakollisia omilla otsikoillaan vai riittääkö niiden sisällöllinen kattavuus V3 signal observation -mallissa.
- Päätä, onko taxonomy listing edelleen raporttituotevaatimus vai legacy-apuosa, jonka voi poistaa myös vertailukriteereistä.

## Evidence inspected

### Primary comparison docs

- `docs/datacenter_legacy_report_generation_reference.md`: varmisti legacy daily- ja rolling-raporttien osiot, lähdetaulut, output-muodot ja scheduler-kontekstin.
- `docs/ecosystem_v3_report_generation_reference.md`: varmisti V3 daily- ja rolling-raporttien osiot, `eco_*`-render-polun, output-muodon ja latest-run-valinnan.
- `docs/ecosystem_v3_eco_tables_reference.md`: varmisti, mitä `eco_*`-tauluja V3 renderöinti ja upstream facts -kerros käyttävät.
- `docs/datacenter_dc_tables_reference.md`: varmisti legacy `dc_*` -taulujen merkityksen ja sen, miten ne liittyvät raporttien lukupolkuun.

### Targeted code paths

- `analysis/datacenter_indices/swing_daily_report.py`: varmisti legacy daily -raportin näkyvät pääosiot ja sen, että daily-polku kokoaa myös CSV-sisällön.
- `analysis/datacenter_indices/swing_weekly_report.py`: varmisti legacy rolling -raporttien yhteisen rakenteen, horizon-kohtaiset erikoisosiot ja CSV-polun.
- `rawcandle/reporting_v3_markdown.py`: varmisti V3 daily- ja rolling-renderöinnin otsikot, parity gapit ja V3-only-osiot.
- `rawcandle/cli/write_latest_v3_markdown_reports.py`: varmisti latest-run-valinnan `eco_report_run`-taulusta ja V3 Markdown -outputin horizon-kohtaisen kirjoituksen.
- `rawcandle/scheduler/runner.py`: varmisti, että scheduler käsittelee legacy- ja V3-raportit erillisinä tulosryhminä rinnakkaisajossa.
- `rawcandle/cli/run_stock_update_scheduler.py`: varmisti scheduler-CLI:n käyttävän runner-polkuja eikä yhdistävän legacy- ja V3-raportteja yhdeksi raporttituotteeksi.

### Tests and sample output

- `tests/test_write_latest_v3_markdown_reports_cli.py`: varmisti latest-run-valinnan järjestyksen ja V3 output-polkujen nimet.
- `temp/v3_latest_wrapper_smoke_20260606_signal_date_072500/datacenter_v3_daily_2026-06-04.md`: varmisti käytännön daily-otsikoinnin ja sen, että V3 daily sisältää limitation-tekstiä dashboard-pariteetista.

## Open questions

- Onko `CSV output` edelleen pakollinen jollekin schedulerin, dashboardin tai ulkoisen jatkokäsittelyn downstream-kuluttajalle?
- Riittääkö V3 daily -dashboard nykyisellä aggregaatiotasolla, vai vaaditaanko sille täysi legacy-pariteetti ennen korvausta?
- Pitääkö legacy rolling -raporttien `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot säilyttää eksplisiittisinä otsikkoina myös V3:ssa?
- Onko taxonomy listing edelleen tuotannollinen vaatimus vai vain legacy-luettavuusapu?
- Ovatko kaikki rolling-ikkunat varmasti yhdenmukaisesti valid trading day -pohjaisia myös V3 query -tasolla kaikissa reunaehdoissa?
