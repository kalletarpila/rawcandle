# Fundamentals V4 Company Snapshot V1

## Tarkoitus

`CURRENT_REVISED_COMPANY_SNAPSHOT_V1` kokoaa yhden yhtiön tuotannolliset Fundamentals V4 -tulokset luettavaan Markdown-raporttiin. Raportti on koonti- ja tarkastelutyökalu. Se ei muodosta uutta scorea, tuottoennustetta, teknistä entry-signaalia eikä BUY/SELL-suositusta.

Raportin historia on **currently revised**. Se käyttää tietokannassa nyt olevia revisioituja arvoja eikä rekonstruoi alkuperäisen julkaisuhetken point-in-time-tietoa. Aikaisempi `report_date` estää tulevaisuuden saatavuuspäivien ja hintojen käytön, mutta myöhemmin tietokantaan tulleet restatementit voivat silti näkyä.

## Ankkuri ja historia

Ankkuri on yhtiön uusin canonical TTM -fiscal endpoint, jonka kirjattu saatavuuspäivä on enintään `report_date`. Sama `company_id`, `quarter_id`, fiscal year ja fiscal quarter sitovat Score-, Delta-, Lifecycle-, Valuation- ja Diagnostic-tulokset yhteen. Puuttuvaa ankkuritulosta ei korvata toisen kerroksen vanhemmalla tuloksella.

Score- ja Valuation-taulukot sisältävät tiukan ketjun `t-4...t`. `t-4` merkitään yksiselitteisesti YoY-vertailupisteeksi. Puuttuva kvartaali näytetään viivana eikä sitä korvata lähimmällä havainnolla. Lifecycle näyttää neljä uusinta tiukkaa fiscal-endpointia. Neljän havainnon Valuation-keskiarvo lasketaan vain `t-3...t`:stä ja vain, jos kaikki neljä tulosta ovat `VALUATION_FULL`.

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

## Three-point valuation multiples

Raportin Valuation-osio sisältää kuvailevan kolmen pisteen vertailun. Sarakkeet ovat:

1. `Current moment`: viimeisin raporttipäivänä tai sitä ennen kelvollinen markkinahinta yhdistettynä uusimman filing-ankkurin fundamentteihin, osakkeisiin, velkaan ja kassaan. Tämä on indikatiivinen esityslaskelma, ei persisted valuation -havainto.
2. `Latest filing`: uusimman ankkurin oma persisted Valuation V1 -hinta ja sen todellinen hintapäivä sekä saman ankkurin fundamentit.
3. `Previous filing (Q−1)`: täsmälleen edeltävä fiscal-havainto `fiscal_sequence - 1`, sen oma saatavuuspäivä, persisted filing-hinta ja omat TTM- ja tasearvot. Lähintä aikaisempaa kalenterihavaintoa, Q−2:ta tai uusimman filingin fundamentteja ei korvata puuttuvan Q−1:n tilalle.

Kontekstitaulukko näyttää jokaiselle pisteelle fiscal-kvartaalin, fundamentin saatavuuspäivän, todellisen hintapäivän, hinnan, valuutan silloin kun validoitu valuuttakenttä on saatavilla sekä authoritative valuation -statuksen. Nykyisissä validoiduissa lähdetauluissa ei ole hintavaluuttaa, joten sitä ei päätellä provider-payloadista vaan se näytetään `N/A`:na.

Taulukossa on täsmälleen nämä kymmenen mittaria, jotka lasketaan pyöristämättömistä lähdearvoista:

```text
Market Capitalization = price * shares outstanding
Enterprise Value = Market Capitalization + total debt - cash
P/E = Market Capitalization / TTM common earnings
Earnings Yield = TTM common earnings / Market Capitalization
P/FCF = Market Capitalization / TTM free cash flow
FCF Yield = TTM free cash flow / Market Capitalization
EV/EBIT = Enterprise Value / TTM EBIT
EBIT Yield = TTM EBIT / Enterprise Value
EV/Sales = Enterprise Value / TTM revenue
P/S = Market Capitalization / TTM revenue
```

`N/A` tarkoittaa, että vaadittu lähdearvo tai koko evaluation point puuttuu tai ei ole kelvollinen. `N/M` tarkoittaa, että lähdearvot ovat olemassa mutta suhdeluku ei ole taloudellisesti mielekäs: esimerkiksi earnings, FCF, EBIT tai revenue on enintään nolla, Market Cap ei ole positiivinen tai EV-pohjaisen suhdeluvun EV ei ole positiivinen. Puuttuvaa arvoa ei muuteta nollaksi eikä imputoida. Negatiivinen EV voidaan näyttää absoluuttisena tasekäsitteenä, mutta EV-pohjaiset suhdeluvut ovat silloin `N/M`.

Market Cap ja EV esitetään lyhennetyssä rahaformaatissa, multiplet `x`-muodossa ja yieldit prosentteina. Hyvin pienille positiivisille yieldeille säilytetään lisädesimaaleja. Näyttöpyöristyksen negatiivinen nolla normalisoidaan nollaksi. Laskentaa ei koskaan tehdä pyöristetyistä näyttöarvoista tai pyöristetyn yieldin käänteislukuna.

Rekonsiliaatio tarkistaa pyöristämättömistä arvoista `P/E * Earnings Yield`, `P/FCF * FCF Yield` ja `EV/EBIT * EBIT Yield` vasten yhtä. Latest filingin ja Q−1:n uudelleen lasketut Market Cap ja EV täsmäytetään persisted valuation -evidenssiin. Lisäksi tarkistetaan latest/current-fundamenttipohjan identtisyys, exact fiscal Q−1, current-hinnan yläraja ja filing-hintojen Valuation V1 -fallback-ikkuna.

Current momentin ja Latest filingin ero johtuu pääosin hinnasta, koska fundamenttipohja on sama. Latest filingin ja Q−1:n ero yhdistää hinnan, osakemäärän, taseen ja TTM-fundamenttien muutokset, joten taulukko ei ole puhdas valuation-trendin dekompositio. Mittarit ovat kuvailevia eivätkä muuta Valuation Scorea, sen sovellettavuutta, pisteitä tai fingerprintiä. P/B:tä, P/TBV:tä, PEG:iä, EV/EBITDA:ta, EV/FCF:ää, osinkotuottoa tai forward-multipleita ei lasketa.

Filing-date valuation käyttää kunkin fundamenttihavainnon saatavuuspäivään valittua markkinahintaa. Indicative current-price valuation käyttää viimeisintä raporttipäivälle kelvollista hintaa mutta pitää anchor-fundamentit vakiona. Raportti näyttää näiden hinnat, päivät, absoluuttisen ja prosentuaalisen hintaeron sekä Score-eron. Filing-historian hintamuutokset näytetään QoQ-, 2Q- ja YoY-horisonteilla. Filing-date Valuation Scoren muutos voi johtua sekä fundamenttien että filing-hinnan muutoksesta, joten sitä ei tulkita puhtaaksi trendiksi.

## Lifecycle-esitys

Lifecycle-osio käyttää persisted revised Lifecycle -historiaa. Neljän rivin taulukossa näytetään saatavuuspäivä, `raw_state`, julkinen vahvistettu `final_state` ja deterministinen siirtymätila. Nykytilasta näytetään lisäksi published status, vahvistettu tila, peräkkäisistä authoritative-riveistä johdettu tenure sekä ensimmäinen fiscal-kausi ja saatavuuspäivä, josta tila on ollut yhtäjaksoisesti voimassa.

Siirtymäehdokas näytetään vain persisted `candidate_state` / `candidate_count` -kenttien perusteella. Tavallinen siirtymä ja poistuminen `DISTRESSED`-tilasta vaativat kaksi samaa peräkkäistä raw-tilaa. Ensimmäinen havainto on `1/2`, toinen vahvistaa siirtymän. Uusi raw-tila korvaa vanhan ehdokkaan, `UNCLASSIFIED` nollaa ehdokkaan ja `DISTRESSED` astuu voimaan välittömästi. `last_confirmed_state` on vain tilakonehistoriaa: `LIFECYCLE_NOT_READY`-havaintoa ei esitetä sen avulla nykyisenä vahvistettuna tilana.

## Esityshuomiot

Fundamental- ja Valuation-komponenteille näytetään pistekattohuomio, kun nykyinen komponentti on maksimissaan. Huomio kertoo, että raw-mittari voi edelleen parantua ilman lisäpisteitä; 100 pisteen Valuation ei voi nousta yli 100:n. Näytetyt Fundamental-kokonaispisteet perustuvat pyöristämättömiin komponentteihin.

Revenue Growth -historia saa informatiivisen base effect -huomion, kun absoluuttinen YoY-kasvu on vähintään 100 % ja YoY-vertailupohja on pienempi kuin `max(10 miljoonaa USD, 10 % nykyisestä TTM-liikevaihdosta)`. Tarkka laskettu kasvu, vertailupohja ja raja säilyvät näkyvissä. Huomio ei muuta laskentaa, pisteitä, statuksia tai diagnostiikkalippuja.

Taxonomy-jäsenyydet esitetään erillisessä ecosystem-, segment- ja membership type -taulukossa. Jäsenyys, ekosysteemipersentiilin kelpoisuus ja toteutunut Relative Position -tulos ovat erillisiä asioita. Jäsenyyden puuttuminen esitetään neutraalina tekstinä.

CAPEX näytetään sijoittajataulukossa positiivisena `Capex spend` -menon suuruutena. Canonical-arvo säilyy muuttumattomana ja negatiivinen canonical CAPEX tarkoittaa kassavirran ulosmenoa. Negatiivinen nettovelka näytetään positiivisena `Net cash` -määränä. Nämä ovat vain esitysmuutoksia.

Kaikki lukumuotoilijat normalisoivat vain näytöllä pyöristyvän negatiivisen tai etumerkillisen nollan muotoon `0.00`. Binääriarvot ja laskentatarkkuus eivät muutu. Diagnostic Flags -osiossa margin decelerationin EBIT-marginaalimuutos on QoQ, kun Fundamental Scoren EBIT Margin Direction on YoY.

## Sisältö

Raportissa esitetään tässä järjestyksessä:

1. yhtiöidentiteetti, luokitus ja ankkuri
2. erillinen taxonomy-jäsenyystaulukko
3. nykytilan yhteenveto ilman yhdistelmäarviota
4. Fundamental Score ja seitsemän komponenttia viideltä endpointilta
5. komponenttien raw-mittarit ja persisted Fundamental Delta
6. absoluuttiset tulos-, kassavirta- ja tasearvot
7. neljän endpointin revised Lifecycle, tenure ja persisted siirtymäehdokas
8. filing-date Valuation, komponentit, raw-yieldit, hintamuutokset ja endpoint-vertailut
9. indicative current-price valuation ja filing-vertailu
10. aktiivisen Relative Position -snapshotin prosenttipisteet ja peer-määrät
11. kaikki seitsemän Diagnostic Flag -statusta ja normalisoitu evidenssi
12. readiness-rajoitteet ja erillinen tekninen fingerprint-liite

Relative Position on current-only snapshot. Sitä näytetään vain, kun snapshotin päivä ei ole `report_date`:n jälkeen ja lähdehavainto vastaa raportin ankkuria. Pienen peer-ryhmän tulosta ei korvata laajemmalla ryhmällä. Nykyhintavaluationille ei lasketa omaa prosenttipistettä.

Diagnostic Flags esitetään review-candidate-havaintoina. Raportti ei päättele syytä, vahvista kertaluonteista tapahtumaa eikä muodosta severity-scorea.

## Determinismi ja lähdeturvallisuus

Kaikki viisi lähdekantaa avataan absoluuttisista poluista SQLite URI `mode=ro` -tilassa, `query_only` päällä. Ei-tyhjä WAL estää ajon, jotta immutable-luku ei ohita julkaisemattomia rivejä. Aktiivinen lähdetila luetaan ennen kokoamista ja tarkistetaan uudelleen ennen julkaisua. Muutos kesken ajon keskeyttää julkaisun.

Markdownissa ei ole ajonaikaa, prosessitunnusta, väliaikaista polkua eikä seinäkelloaikaa. Sisältöön upotettu SHA-256 lasketaan deterministisestä templaatista, jossa fingerprint-kentällä on vakioitu placeholder. Samat lähteet ja argumentit tuottavat tavutasolla saman tiedoston.

Raportin esitysmuutokset muuttavat report-content fingerprintin tarkoituksellisesti. Taloudellisten mallien fingerprintit ja persisted result fingerprintit eivät muutu. Täydet yksilöidyt model-, source- ja result-fingerprintit säilyvät teknisessä liitteessä omilla riveillään.

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
- Valuation-historia yhdistää fundamenttien ja filing-date-hinnan muutoksen; se ei ole puhdas hinta- eikä fundamenttitrendi.
- Raportti ei hae verkosta tapahtumien syitä eikä esitä kvalitatiivista sijoitusanalyysiä.
- Base effect -huomio tunnistaa dokumentoidun pienen Revenue Growth -vertailupohjan; se ei päättele liiketoiminnallista syytä eikä korjaa mittaria.
- Current-price-prosenttipistettä ei lasketa. Sen lisääminen vaatisi oman menetelmäsopimuksen ja koko universumin yhteisen markkinapäivän.
