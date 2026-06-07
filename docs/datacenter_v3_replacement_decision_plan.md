# Datacenter V3 replacement decision plan

## Purpose of this document

Tämä dokumentti muuntaa legacy vs V3 parity -havainnot priorisoiduksi päätös- ja toimintasuunnitelmaksi, jonka avulla voidaan edetä rinnakkaisajosta kohti mahdollista V3-korvausta hallitusti.

Tavoite ei ole toteuttaa korjauksia, vaan päättää mitä pitää ratkaista ennen korvausta, mitä voidaan todennäköisesti hyväksyä tarkoituksellisina V3-eroina ja mitä kannattaa jättää myöhemmiksi Codex-toteutustehtäviksi.

## Scope

Tämä dokumentti kattaa:

- legacy vs V3 report replacement -päätössuunnittelun
- parity gapit raporteissa `datacenter_daily`, `datacenter_rolling_30`, `datacenter_rolling_5` ja `datacenter_rolling_2`
- output- ja operointierot
- source-lineage- ja transition-riskit

Tämä dokumentti ei kata:

- implementointia
- koodimuutoksia
- skeemamuutoksia
- dashboard-UI:n uudelleensuunnittelua
- uutta raporttidesignia parity-päätösten ulkopuolella

## Executive summary

Nykyisen evidenssin perusteella V3 ei ole vielä varovaisella tulkinnalla valmis korvaamaan legacy-raportteja yksinään. V3 daily on sisällöllisesti lähellä legacy dailyä, mutta rolling-raporttien operatiivinen pariteetti ei vielä näytä täydeltä ja muutama päätöskohta on edelleen auki.

Todennäköisimmät korvausblokkerit ovat `CSV output` -vaatimuksen avoin status, valid trading day -semantiikan vahvistamattomuus V3 rolling -polussa ja daily-dashboardin täyden legacy-pariteetin avoin vaatimus. Tärkeitä mutta mahdollisesti ei-blokkaavia kohtia ovat rolling-raporttien eksplisiittiset `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot sekä taxonomy listingin tarve.

Suositeltu seuraava askel on pitää legacy ja V3 rinnakkain, päättää ensin blokkereiksi mahdollisesti nousevat tuotantovaatimukset ja vasta sen jälkeen tehdä kohdennetut toteutustehtävät.

## Decision matrix

| Item | Current evidence | Replacement impact | Decision needed | Recommended decision | Priority | Implementation later? | Notes |
|---|---|---|---|---|---|---|---|
| `CSV output` | legacy tuottaa Markdownin ja CSV:n; V3 renderöi vain Markdownia | user decision required | kyllä | verify before replacement | P0 blocker | kyllä | jos downstream-kuluttaja tarvitsee CSV:n, tämä blokkaa korvauksen |
| V3 daily dashboard aggregation parity | V3 daily sisältää dashboardin, mutta ei full legacy dashboard aggregationia | likely blocks replacement | kyllä | decide requirement before replacement | P0 blocker | kyllä | vain jos käyttäjän workflow tarvitsee legacy-tason dashboard-koonnit |
| Rolling `Swing MA Break Status` | legacy rolling näyttää eksplisiittisen osion; V3 rollingissä ei näy yksi-yhteen -vastinetta | unclear | kyllä | verify before replacement | P1 important | kyllä | voi olla sisällöllisesti osin katettu muilla V3-osioilla |
| Rolling `Swing Signal Freshness` | legacy rolling näyttää eksplisiittisen osion; V3 rollingissä ei näy yksi-yhteen -vastinetta | unclear | kyllä | verify before replacement | P1 important | kyllä | sama arvio kuin MA break -osiossa |
| Taxonomy listing | legacy näyttää taxonomy listingin; V3 ei | user decision required | kyllä | accept as intentional V3 difference if not operationally needed | P2 useful | ehkä | ei nykyisen evidenssin perusteella näytä tekniseltä blokkerilta |
| Valid trading day semantics | legacy rolling käyttää eksplisiittisesti valid trading day -ikkunaa; V3:n vastaavuus tarvitsee vahvistuksen | likely blocks replacement | kyllä | verify before replacement | P0 blocker | kyllä | koskee erityisesti rolling30, rolling5 ja rolling2 |
| V3 vs legacy filename conventions | legacy käyttää `_full`- ja `HHMM`-painotteista nimeämistä; V3 käyttää `datacenter_v3_<window>_<signal_date>.md` | does not block replacement | kyllä | document only | P3 optional | ei välttämättä | nousee blokkeriksi vain jos jokin ulkoinen kuluttaja olettaa legacy-nimeämisen |
| V3 report metadata / limitations appendix | V3 sisältää oman appendix-osion, legacy ei | does not block replacement | ei välttämättä | accept as intentional V3 difference | no action | ei | V3-only-lisäarvo, ei havaittu regressio |
| V3-only `Structural events` | V3 rolling painottaa tätä osiota; legacyssä ei vastaavaa nimettyä osiota | does not block replacement | ei välttämättä | accept as intentional V3 difference | no action | ei | V3-only-laajennus |
| V3-only `Signal observations` | V3 rolling painottaa tätä osiota; legacyssä ei vastaavaa nimettyä osiota | does not block replacement | ei välttämättä | accept as intentional V3 difference | no action | ei | V3-only-laajennus |
| `eco_*` render-only path | V3 render-vaihe näyttää lukevan vain `eco_*`-tauluja | does not block replacement | ei | document only | no action | ei | tämä on arkkitehtuurinen vahvuus, ei parity-gap |
| Transitional `dc_*` upstream dependencies | osa V3 facts -kerroksesta on edelleen transitional `dc_*` -riippuvainen upstreamissa | user decision required | kyllä | keep side-by-side for now | P1 important | kyllä myöhemmin | ei suoraan render-gap, mutta riski liian aikaiselle legacy-poistolle |
| Scheduler side-by-side output | scheduler osaa tuottaa legacy- ja V3-raportit rinnakkain | does not block replacement | kyllä | keep side-by-side for now | P1 important | ei välttämättä | tämä on suositeltu siirtymätila eikä ongelma itsessään |
| Legacy report retirement criteria | nykyinen evidenssi ei vielä määritä kovia poistokriteerejä | user decision required | kyllä | define before replacement | P0 blocker | kyllä | ilman selviä kriteerejä korvauspäätös jää liian epämääräiseksi |

## Recommended replacement phases

### Phase 0 — Keep side-by-side reporting

Purpose:

- pidä legacy- ja V3-raportit rinnakkain tuotannossa
- käytä V3-raportteja arviointiin, ei vielä ainoana korvaajana

Exit criteria:

- päätösmatriisin kriittiset kohdat on luokiteltu
- käyttäjä on arvioinut daily- ja rolling V3 -raporttien käytettävyyden
- mitään ilmeistä puuttuvaa kriittistä osiota ei ole jäänyt epähuomiossa avoimeksi

### Phase 1 — Resolve replacement blockers

Purpose:

- ratkaise tai vahvista kohdat, jotka voivat estää korvauksen

Todennäköiset kohteet:

- päätä, onko `CSV output` pakollinen
- vahvista valid trading day -semantiikka V3 rolling -raporteille
- päätä, vaaditaanko daily-dashboardille täysi legacy-pariteetti
- määritä legacy report retirement criteria

### Phase 2 — Implement important parity items

Purpose:

- toteuta vain ne parity-korjaukset, jotka päätettiin oikeasti tarpeellisiksi

Todennäköiset kohteet:

- eksplisiittinen rolling `Swing MA Break Status`, jos käyttäjä tarvitsee sen
- eksplisiittinen rolling `Swing Signal Freshness`, jos käyttäjä tarvitsee sen
- daily-dashboardin lisäpariteetti, jos se päätetään pakolliseksi
- mahdollinen `CSV output`, jos se todetaan operatiiviseksi vaatimukseksi

### Phase 3 — Decide intentional differences

Purpose:

- erottele hyväksyttävät V3-erot tarpeettomista parity-velvoitteista

Todennäköiset kohteet:

- taxonomy listing
- filename convention
- `V3 metadata / limitations appendix`
- V3-only `Structural events`
- V3-only `Signal observations`

### Phase 4 — Retirement readiness

Purpose:

- määritä, milloin legacy voidaan sammuttaa hallitusti

Exit criteria:

- kaikki P0 blocker -kohdat on ratkaistu
- käyttäjä hyväksyy V3-sisällön päivittäiseen käyttöön
- rinnakkaisajojakso on suoritettu onnistuneesti
- rollback-polku on kuvattu
- `dc_*` upstream -riippuvuuksien rooli ymmärretään eikä niitä poisteta vahingossa liian aikaisin

## Report-specific readiness

| Report pair | Current readiness | Must resolve before replacement | Nice to resolve | Suggested user review focus |
|---|---|---|---|---|
| `datacenter_daily` -> V3 `daily` | nearly replacement-ready | `CSV output` -päätös, dashboard-pariteetin vaatimus | taxonomy listing, filename convention | riittääkö daily-dashboard käytännön workflow’hun |
| `datacenter_rolling_30` -> V3 `rolling30` | review-ready | valid trading day -vahvistus, `CSV output` -päätös | eksplisiittinen `Swing MA Break Status`, eksplisiittinen `Swing Signal Freshness`, taxonomy listing | ovatko watchlist- ja exit/buy-näkymät riittävät ilman legacy-otsikointia |
| `datacenter_rolling_5` -> V3 `rolling5` | review-ready | valid trading day -vahvistus, `CSV output` -päätös | eksplisiittinen `Swing MA Break Status`, eksplisiittinen `Swing Signal Freshness`, taxonomy listing | riittääkö `Rolling 5 Pullback Alerts` nykyisessä V3-rakenteessa |
| `datacenter_rolling_2` -> V3 `rolling2` | review-ready | valid trading day -vahvistus, `CSV output` -päätös | eksplisiittinen `Swing MA Break Status`, eksplisiittinen `Swing Signal Freshness`, taxonomy listing | riittääkö `Rolling 2 Sell Pressure` ilman legacy-operatiivisia sivuformaatteja |

## Items that should likely be implemented later

- `CSV output` for V3 reports
  - reason: voi olla korvausblokkeri, jos downstream-käyttö edellyttää CSV:tä
  - likely files/modules: `rawcandle/cli/write_latest_v3_markdown_reports.py`, `rawcandle/cli/write_v3_markdown_prototypes.py`, `rawcandle/reporting_v3_markdown.py`, mahdollisesti uusi query/export-polku
  - prerequisite decision: vahvistus siitä, että CSV on operatiivisesti pakollinen
  - estimated risk: medium

- Rolling `Swing MA Break Status` explicit section parity
  - reason: rolling legacy -raportit näyttävät tämän eksplisiittisesti, V3 parity on epäselvä
  - likely files/modules: `rawcandle/reporting_v3_markdown.py`, mahdollisesti `rawcandle/reporting_v3_query.py`
  - prerequisite decision: päätös siitä, että eksplisiittinen otsikkotason parity vaaditaan
  - estimated risk: medium

- Rolling `Swing Signal Freshness` explicit section parity
  - reason: rolling legacy -raportit näyttävät tämän eksplisiittisesti, V3 parity on epäselvä
  - likely files/modules: `rawcandle/reporting_v3_markdown.py`, mahdollisesti `rawcandle/reporting_v3_query.py`
  - prerequisite decision: päätös siitä, että eksplisiittinen otsikkotason parity vaaditaan
  - estimated risk: medium

- Daily dashboard aggregation parity
  - reason: V3 daily ei nykyisen evidenssin perusteella kata full legacy dashboard aggregationia
  - likely files/modules: `rawcandle/reporting_v3_query.py`, `rawcandle/reporting_v3_markdown.py`, mahdollisesti upstream V3 builderit
  - prerequisite decision: vaatimus siitä, että täysi legacy-dashboard on pakollinen ennen korvausta
  - estimated risk: high

- Valid trading day semantics verification and possible adjustment
  - reason: rolling-korvauksen luotettavuus riippuu tästä
  - likely files/modules: ensin dokumentaatio- ja verifiointikohteet; mahdolliset koodit myöhemmin `rawcandle/reporting_v3_query.py` ja upstream window-builderit
  - prerequisite decision: vahvistus siitä, että nykyinen semantiikka ei ole jo hyväksyttävä
  - estimated risk: medium

## Items that should probably not be implemented yet

- tarkka legacy-muotoilun yksi-yhteen -pariteetti
- taxonomy listing, jos sen operatiivista tarvetta ei vahvisteta
- `CSV output`, jos mikään downstream-kuluttaja ei sitä tarvitse
- legacy-raporttien poistaminen ennen selviä retirement criteria -päätöksiä
- `dc_*` upstream -riippuvuuksien poistaminen ennen kuin niiden transitional rooli on täysin ymmärretty

## Retirement criteria for legacy reports

Seuraavien ehtojen pitäisi todennäköisesti täyttyä ennen kuin legacy-raportit poistetaan käytöstä:

- käyttäjä hyväksyy V3-raporttisisällön päivittäiseen workflow’hun
- kaikki P0 blocker -kohdat on ratkaistu
- `CSV output` -päätös on tehty
- valid trading day -semantiikka on vahvistettu
- schedulerin side-by-side -jakso on suoritettu onnistuneesti
- rollback-polku on olemassa
- `dc_*` upstream -riippuvuuksien rooli ymmärretään eikä niitä poisteta liian aikaisin

## Risks if legacy is retired too early

- piilossa oleva CSV-riippuvuus voi katketa
- käyttäjä voi menettää daily- tai rolling-osioita, joita käyttää päätöksenteossa
- rolling-ikkunoiden mahdollinen valid trading day -ero voi muuttaa raporttien tulkintaa
- taxonomy listingiin voi olla hiljaista käyttöä, jota dokumentit eivät yksin paljasta
- V3 upstream facts voivat edelleen nojata `dc_*`-lähteisiin, joten liian varhainen legacy-purku voi rikkoa siirtymäpolun
- parity-testien puute voi jättää regressioita näkymättä ennen tuotantokäyttöä

## Evidence inspected

### Primary docs

- `docs/datacenter_legacy_vs_v3_report_parity.md`: toimi päätösdokumentin pääasiallisena parity-lähteenä ja luokittelun perustana.
- `docs/ecosystem_v3_report_generation_reference.md`: varmisti V3-render-polun, output-erot ja schedulerin rinnakkaisajon.
- `docs/ecosystem_v3_eco_tables_reference.md`: varmisti `eco_*`-lineagen sekä transitional `dc_*` upstream -riippuvuuksien nykytilan.
- `docs/datacenter_legacy_report_generation_reference.md`: varmisti legacy-raporttien outputit, valid trading day -kuvauksen ja rolling-osioiden rakenteen.
- `docs/datacenter_dc_tables_reference.md`: varmisti, mitä legacy `dc_*` -tauluja parity- ja replacement-päätökset koskevat.

## Open questions

- Onko `CSV output` operatiivisesti pakollinen?
- Vaaditaanko full legacy daily dashboard parity ennen korvausta?
- Ovatko rolling `Swing MA Break Status`- ja `Swing Signal Freshness` -osiot pakollisia eksplisiittisinä raporttiosioina?
- Onko taxonomy listing edelleen tarpeellinen?
- Ovatko V3 rolling -ikkunat vahvistetusti valid trading day -mielessä legacyä vastaavia?
- Kuinka pitkän side-by-side -jakson käyttäjä haluaa ennen retirement-päätöstä?
- Mikä on vähimmäishyväksyntäkriteeri sille, että V3 saa korvata legacy-raportit?
