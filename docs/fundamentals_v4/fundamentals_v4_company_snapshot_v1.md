# Fundamentals V4 Company Snapshot V1

## Tarkoitus

`CURRENT_REVISED_COMPANY_SNAPSHOT_V1` kokoaa yhden yhtiön tuotannolliset Fundamentals V4 -tulokset luettavaan Markdown-raporttiin. Raportti on koonti- ja tarkastelutyökalu. Se ei muodosta uutta scorea, tuottoennustetta, teknistä entry-signaalia eikä BUY/SELL-suositusta.

Raportin historia on **currently revised**. Se käyttää tietokannassa nyt olevia revisioituja arvoja eikä rekonstruoi alkuperäisen julkaisuhetken point-in-time-tietoa. Aikaisempi `report_date` estää tulevaisuuden saatavuuspäivien ja hintojen käytön, mutta myöhemmin tietokantaan tulleet restatementit voivat silti näkyä.

## Ankkuri ja historia

Ankkuri on yhtiön uusin canonical TTM -fiscal endpoint, jonka kirjattu saatavuuspäivä on enintään `report_date`. Sama `company_id`, `quarter_id`, fiscal year ja fiscal quarter sitovat Score-, Delta-, Lifecycle-, Valuation- ja Diagnostic-tulokset yhteen. Puuttuvaa ankkuritulosta ei korvata toisen kerroksen vanhemmalla tuloksella.

Score- ja Valuation-taulukot sisältävät tiukan ketjun `t-4...t`. Puuttuva kvartaali näytetään viivana eikä sitä korvata lähimmällä havainnolla. Lifecycle näyttää kahdeksan tiukkaa endpointia. Neljän havainnon Valuation-keskiarvo lasketaan vain `t-3...t`:stä ja vain, jos kaikki neljä tulosta ovat `VALUATION_FULL`.

## Raporttipäivä ja hinta

`report_date` on pakollinen ja määrää tiedoston päivämäärän sekä markkinahinnan ylärajan. Indicative current-price valuation käyttää viimeisintä täydellistä ja validia OHLC-päätöskurssia raporttipäivänä tai sitä ennen. Kurssi saa olla enintään seitsemän kalenteripäivää vanha.

Nykyhintavaluation pitää uusimman ankkurin TTM EBITin, FCF:n, common earningsin, osakemäärän, velan ja kassan vakiona. Laskenta käyttää samaa Absolute Valuation Score V1 -moottoria ja sen ankkureita:

```text
market_cap = close * shares_outstanding
EV = market_cap + total_debt - cash
EBIT yield = TTM EBIT / EV
FCF yield = TTM FCF / market_cap
earnings yield = TTM common earnings / market_cap
```

Hintaa ja osakemäärää käytetään tuotannon split-yhteensopivassa tallennusmuodossa. Erillistä split-oikaisua ei tehdä. Jos hinta on liian vanha tai laskenta ei ole sovellettavissa, nykyhintavaluation näytetään puuttuvana eikä muuta raporttia estetä.

## Sisältö

Raportissa esitetään tässä järjestyksessä:

1. yhtiöidentiteetti, luokitus, taxonomy-jäsenyydet ja ankkuri
2. nykytilan yhteenveto ilman yhdistelmäarviota
3. Fundamental Score ja seitsemän komponenttia viideltä endpointilta
4. komponenttien raw-mittarit ja persisted Fundamental Delta
5. absoluuttiset tulos-, kassavirta- ja tasearvot
6. kahdeksan endpointin revised Lifecycle
7. filing-date Valuation, komponentit, raw-yieldit ja endpoint-vertailut
8. indicative current-price valuation
9. aktiivisen Relative Position -snapshotin prosenttipisteet ja peer-määrät
10. kaikki seitsemän Diagnostic Flag -statusta ja normalisoitu evidenssi
11. readiness-rajoitteet ja tekninen fingerprint-liite

Relative Position on current-only snapshot. Sitä näytetään vain, kun snapshotin päivä ei ole `report_date`:n jälkeen ja lähdehavainto vastaa raportin ankkuria. Pienen peer-ryhmän tulosta ei korvata laajemmalla ryhmällä. Nykyhintavaluationille ei lasketa omaa prosenttipistettä.

Diagnostic Flags esitetään review-candidate-havaintoina. Raportti ei päättele syytä, vahvista kertaluonteista tapahtumaa eikä muodosta severity-scorea.

## Determinismi ja lähdeturvallisuus

Kaikki viisi lähdekantaa avataan absoluuttisista poluista SQLite URI `mode=ro` -tilassa, `query_only` päällä. Ei-tyhjä WAL estää ajon, jotta immutable-luku ei ohita julkaisemattomia rivejä. Aktiivinen lähdetila luetaan ennen kokoamista ja tarkistetaan uudelleen ennen julkaisua. Muutos kesken ajon keskeyttää julkaisun.

Markdownissa ei ole ajonaikaa, prosessitunnusta, väliaikaista polkua eikä seinäkelloaikaa. Sisältöön upotettu SHA-256 lasketaan deterministisestä templaatista, jossa fingerprint-kentällä on vakioitu placeholder. Samat lähteet ja argumentit tuottavat tavutasolla saman tiedoston.

Kirjoitus tehdään samaan hakemistoon luotuun väliaikaistiedostoon, joka `fsync`-kutsun jälkeen nimetään atomisesti lopulliseksi tiedostoksi. Identtinen tiedosto palauttaa `NO_CHANGE`. Eri sisältö samalla nimellä vaatii `--overwrite`-valinnan.

## CLI

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_company_snapshot \
  --ticker CRMD \
  --report-date 2026-09-06 \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --output-dir /home/kalle/projects/rawcandle/fundamental_reports
```

Oletushakemisto on `fundamental_reports`. Nimi on `{CANONICAL_TICKER}_{REPORT_DATE}.md`. CLI tulostaa JSON-yhteenvedon, jonka status on `CREATED`, `NO_CHANGE`, `OVERWRITTEN` tai virhetilanteessa `FAILED`.

## Julkiset API:t

- `SnapshotPaths`: viiden read-only-lähteen eksplisiittinen sopimus
- `assemble_company_snapshot(...)`: deterministinen rakenteisen snapshotin kokoaminen ja reconciliations
- `render_snapshot(...)`: UTF-8 Markdown ja sisältöfingerprint
- `publish_report(...)`: suojattu atominen julkaisu
- `generate_company_snapshot(...)`: koko ketju lähdetarkistuksineen

## Tunnetut rajoitteet

- Historia ei ole alkuperäinen PIT-rekonstruktio.
- Sektori, toimiala ja taxonomy ovat nykytilaisia, eivät historiallisesti versioituja.
- Nykyhintavaluationin osakkeet, velka ja kassa ovat viimeisimmästä filing-endpointista.
- Valuation-historia yhdistää fundamenttien ja filing-date-hinnan muutoksen; se ei ole puhdas hintatrendi.
- Raportti ei hae verkosta tapahtumien syitä eikä esitä kvalitatiivista sijoitusanalyysiä.

Mahdollinen Phase 7B voi lisätä käyttöliittymäintegraation, erillisen koneellisesti luettavan export-formaatin ja hallitun usean yhtiön batch-ajon. Taloudellisia malleja tai current-price-prosenttipisteitä ei pidä lisätä ilman omaa menetelmäsopimusta ja koko universumin yhteistä markkinapäivää.
