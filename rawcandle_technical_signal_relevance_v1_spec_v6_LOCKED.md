# RawCandle Technical Signal Relevance V1 — Speksi V6 LOCKED

## 1. Tarkoitus

Tämän speksin tarkoitus on lisätä RawCandleen teknisten havaintojen kontekstuaalinen merkitysluokitus.

RawCandle osaa jo laskea kynttiläkuvioita, divergenssejä ja Dow-rakennetta. Tämä uusi kerros ei muuta sitä, **löytyykö tekninen havainto**, vaan arvioi, onko havainto Dow-rakenteen, BOS-tapahtumien ja RESET-tilan perusteella:

```text
RELEVANT
WEAK_CONTEXT
NOISE
```

Tavoite on vähentää teknisten signaalien kohinaa ennen kuin SwingMaster käyttää niitä snapshotissa, signaaliraportoinnissa tai myöhemmässä mallinnuksessa.

### 1.1 Lukitustila

Tämä V6-versio on speksin lukittu ensimmäinen toteutusversio.

```text
SPEC_STATUS = LOCKED_FOR_CODEX_WORK_PACKAGE_1
```

Ensimmäinen toteutustyöpaketti saa muuttaa vain koodia tämän speksin mukaisesti. Speksiä ei pidä laajentaa ensimmäisen työpaketin aikana ilman erillistä päätöstä.

---

## 2. Arkkitehtuuriperiaate

RawCandle vastaa teknisestä analyysistä.

SwingMaster ei saa joutua arvaamaan, onko kynttiläkuvio tai divergenssi relevantti vai kohinaa.

Työnjako:

```text
RawCandle
  -> laskee kynttiläkuviot
  -> laskee divergenssit
  -> laskee Dow-rakenteen
  -> laskee BOS- ja RESET-tapahtumat
  -> antaa tekniselle havainnolle relevance_class-arvon

SwingMaster
  -> lukee RawCandlen tekniset havainnot
  -> käyttää relevance_class-arvoa raportoinnissa ja signaalikontekstissa
  -> ei laske kynttilöiden/divergenssien relevanssia uudelleen
```

---

## 3. Keskeinen periaate

Kynttilä tai divergenssi ei itsessään ole vielä signaali.

Se on ensin vain havainto.

```text
technical observation != trading signal
```

Vasta Dow/BOS/RESET-konteksti tekee havainnosta:

```text
RELEVANT
WEAK_CONTEXT
NOISE
```

Esimerkki:

```text
Hammer UP-trendin HL-dipissä
=> RELEVANT

Hammer DOWN-trendin keskellä
=> NOISE

Hammer RESETin jälkeen mahdollisen pohjan lähellä
=> WEAK_CONTEXT tai RELEVANT
```

---

## 4. Scope V1

### 4.0 Timeframe ja bar-käsite

V5-speksi ei lukitse relevance-laskentaa vain daily-aikatasolle.

Keskeinen aikayksikkö on:

```text
bar = yksi analysoitu OHLCV-kynttilä valitussa timeframe:ssa
```

Esimerkkejä:

```text
Daily-osakedatalla:
1 bar = 1 pörssin trading day

Intraday-datalla:
1 bar = 1 intraday-kynttilä, esimerkiksi 1h tai 4h

Kryptodatalla:
1 daily bar = 1 kalenteripäivän kynttilä
```

Tästä syystä V1/V5 käyttää konfiguraatioissa `*_bars`-termejä, ei `*_trading_days`-termejä.

Jokaisella teknisellä havainnolla ja relevance-rivillä pitää olla eksplisiittinen:

```text
timeframe
```

Alustava daily-oletusarvo nykyisessä RawCandle-ympäristössä voi olla esimerkiksi:

```text
1d
```

tai muu koodikannassa jo käytetty vakiomuotoinen daily-arvo.

### 4.1 Mukaan otettavat bullish-havainnot

RawCandle Technical Signal Relevance V1 käsittelee kaikki jo laskettavat bullish-kuviot.

```text
Hammer
Bullish Engulfing
Piercing Pattern
Three White Soldiers
Morning Star
Dragonfly Doji
Bullish Abandoned Baby
Bullish Flag
Bull Rectangle
Ascending Triangle
Bullish Pennant
Cup and Handle
Bullish Divergence
Hidden Bullish Divergence
```

### 4.2 Mukaan otettavat bearish-havainnot

```text
Bearish Engulfing
Shooting Star
Dark Cloud Cover
Evening Star
Hanging Man
Falling Three Methods
Bearish Flag
Bear Rectangle
Descending Triangle
Bearish Pennant
Bearish Divergence
Hidden Bearish Divergence
```

---

## 5. Signaaliperheet

Jokainen havainto saa `signal_family`-luokan.

### 5.1 REVERSAL_STRONG

Vahvat käännekuviot.

```text
Bullish Engulfing
Bearish Engulfing
Morning Star
Evening Star
Bullish Abandoned Baby
```

### 5.2 REVERSAL_MEDIUM

Keskivahvat käännekuviot.

```text
Hammer
Shooting Star
Dark Cloud Cover
Piercing Pattern
Hanging Man
Dragonfly Doji
```

### 5.3 CONTINUATION

Trendin jatkumiseen liittyvät kuviot.

```text
Bullish Flag
Bearish Flag
Bullish Pennant
Bearish Pennant
Bull Rectangle
Bear Rectangle
Falling Three Methods
Three White Soldiers
```

### 5.4 STRUCTURAL_PATTERN

Laajemmat rakenteelliset patternit.

```text
Ascending Triangle
Descending Triangle
Cup and Handle
```

### 5.5 DIVERGENCE

```text
Bullish Divergence
Bearish Divergence
```

### 5.6 HIDDEN_DIVERGENCE

```text
Hidden Bullish Divergence
Hidden Bearish Divergence
```

---

## 6. Technical observation

Tekninen havainto on yksittäinen kynttiläkuvio tai divergenssi tietyllä tickerillä ja päivällä.

Esimerkki:

```text
ticker = AEIS
timeframe = 1d
signal_date = 2026-05-14
signal_name = Bearish Engulfing
signal_direction = BEARISH
```

---

## 7. Contextual relevance

Kontekstuaalinen relevanssi kertoo, onko havainto merkityksellinen vallitsevassa Dow-rakenteessa.

Mahdolliset arvot:

```text
RELEVANT
WEAK_CONTEXT
NOISE
```

### 7.1 RELEVANT

Havainto tukee Dow-rakennetta, BOS-kontekstia tai RESETin jälkeistä uuden rakenteen muodostumista.

Tätä saa käyttää SwingMasterissa varsinaisena teknisenä kontekstina.

### 7.2 WEAK_CONTEXT

Havainto ei ole täysin kohinaa, mutta se ei yksinään riitä vahvaksi tulkinnaksi.

Tätä saa käyttää varoituksena, lisähuomiona tai matalamman painon teknisenä kontekstina.

### 7.3 NOISE

Havainto on teknisesti olemassa, mutta sen konteksti on heikko tai ristiriitainen.

Sitä ei pidä käyttää ostoa/myyntiä tukevana signaalina.

---

## 8. Dow-konteksti

Relevanssi lasketaan aina suhteessa Dow-rakenteeseen.

Mahdolliset trenditilat:

```text
UP
DOWN
NEUTRAL
```

Lisäksi tarvitaan tarkempi konteksti:

```text
NORMAL
AFTER_BOS
AFTER_RESET
NO_STRUCTURE
```

### 8.1 UP

UP tarkoittaa, että Dow-rakenne on nouseva.

Tällöin ensisijaisesti relevantteja ovat:

```text
bullish continuation
bullish dip reversal
hidden bullish divergence
```

Bearish-kuvioita ei pidä tulkita vahvoina ilman BOS_DOWN- tai RESET-kontekstia.

### 8.2 DOWN

DOWN tarkoittaa, että Dow-rakenne on laskeva.

Tällöin ensisijaisesti relevantteja ovat:

```text
bearish continuation
bearish pullback reversal
hidden bearish divergence
```

Bullish-kuvioita ei pidä tulkita vahvoina ilman BOS_UP- tai RESET-kontekstia.

### 8.3 NEUTRAL

NEUTRAL tarkoittaa, että selkeä trendirakenne puuttuu.

Tässä tilassa kohina on suurinta.

NEUTRAL-tilassa relevantteja voivat olla lähinnä:

```text
vahvat reversal-kuviot
divergenssit
rakenteelliset breakout-kuviot
RESETin jälkeiset uuden suunnan merkit
```

Pienet reversal-kuviot ja continuation-kuviot ovat usein kohinaa.

---

## 9. BOS-konteksti

BOS eli Break of Structure tarkoittaa, että hinta rikkoo aktiivisen rakenteellisen Dow-tason.

RawCandlen nykyisen logiikan mukaan:

```text
UP-trendissä:
low < active_bos_low_price
=> BOS_DOWN

DOWN-trendissä:
high > active_bos_high_price
=> BOS_UP
```

Ensimmäinen vastasuuntainen BOS on varoitus.

Toinen vastasuuntainen BOS ennen toipumista aiheuttaa RESETin.

---

## 10. RESET-konteksti

RESET tarkoittaa, että vanha Dow-rakenne ei ole enää luotettava.

RESETin jälkeen:

```text
trend_state = NEUTRAL
active_bos_high/low tyhjennetään
last labels tyhjennetään
bos_up_count = 0
bos_down_count = 0
structure_epoch_id kasvaa
```

Tulkinnallisesti RESET tarkoittaa:

```text
vanha trendi on rikki
uusi rakenne ei ole vielä valmis
vanhat continuation-kuviot eivät ole luotettavia
vahvat reversal-kuviot ja divergenssit voivat olla kiinnostavia
```

RESETin jälkeinen NEUTRAL pitää erottaa tavallisesta NEUTRAL-tilasta.

Johdettu konteksti:

```text
NEUTRAL_AFTER_RESET
```

---

## 11. Pattern bar count -luokitus

V1/V5 lukitsee patternien bar-luokituksen, jotta `signal_confirmed_as_of_date` voidaan määrittää deterministisesti.

### 11.1 Single-bar patterns

Nämä ovat havaittavissa kyseisen kynttilän sulkeuduttua.

```text
Hammer
Dragonfly Doji
Shooting Star
Hanging Man
```

Sääntö:

```text
signal_confirmed_as_of_date = signal_date
```

edellyttäen, että `signal_date` viittaa kyseisen kynttilän sulkeutumishetkeen / päivään.

### 11.2 Two-bar patterns

Nämä ovat havaittavissa vasta toisen kynttilän sulkeuduttua.

```text
Bullish Engulfing
Bearish Engulfing
Piercing Pattern
Dark Cloud Cover
```

Sääntö:

```text
signal_confirmed_as_of_date = second/final pattern bar close date/time
```

V1-suositus:

```text
signal_date = second/final pattern bar date/time
```

### 11.3 Three-bar patterns

Nämä ovat havaittavissa vasta kolmannen kynttilän sulkeuduttua.

```text
Morning Star
Evening Star
Three White Soldiers
```

Sääntö:

```text
signal_confirmed_as_of_date = third/final pattern bar close date/time
```

V1-suositus:

```text
signal_date = third/final pattern bar date/time
```

### 11.4 Multi-bar / structural patterns

Nämä vaativat useita kynttilöitä tai rakenteellisen muodostelman valmistumisen.

```text
Bullish Abandoned Baby
Falling Three Methods
Bullish Flag
Bearish Flag
Bull Rectangle
Bear Rectangle
Ascending Triangle
Descending Triangle
Bullish Pennant
Bearish Pennant
Cup and Handle
```

Sääntö:

```text
signal_confirmed_as_of_date = final bar close date/time of the completed pattern
```

V1-suositus:

```text
signal_date = final bar date/time of the completed pattern
```

Jos nykyinen RawCandle-tallennusmalli käyttää kuvion alkupäivää `signal_date`-arvona, se on sallittua vain, jos `signal_confirmed_as_of_date` tallennetaan erikseen ja vastaa aina final barin sulkeutumista.

### 11.5 Multi-bar lookahead -kielto

Monen kynttilän kuviota ei saa koskaan näyttää havaittavana ennen kuvion viimeisen kynttilän sulkeutumista.

Kielletty tilanne:

```text
pattern_start_date = 2026-05-01
final_pattern_bar_date = 2026-05-03
signal_confirmed_as_of_date = 2026-05-01
```

Sallittu tilanne:

```text
pattern_start_date = 2026-05-01
final_pattern_bar_date = 2026-05-03
signal_confirmed_as_of_date = 2026-05-03
```

---

## 12. No-lookahead-vaatimus

Relevance-luokitus ei saa käyttää tulevaisuuden dataa.

Yleissääntö:

```text
A context object is usable only if:
context.confirmed_as_of_date <= observation.signal_confirmed_as_of_date
```

Tämä koskee kaikkia kontekstilähteitä:

```text
technical observation
pivot event
BOS event
RESET event
trend_state snapshot
Dow status
```

Relevance-luokitus ei saa käyttää pelkkää `event_date`-vertailua.

Väärä sääntö:

```text
pivot.event_date <= signal_date
```

Oikea sääntö:

```text
pivot.confirmed_as_of_date <= signal_confirmed_as_of_date
```

Jos pivotin `event_date` on ennen signaalipäivää, mutta pivotin `confirmed_as_of_date` on signaalin confirmed-päivän jälkeen, pivotia ei saa käyttää signaalin kontekstissa.

---

## 13. Signal timing

V1 erottaa kaksi päivämäärää:

```text
signal_date
signal_confirmed_as_of_date
```

### 12.1 signal_date

`signal_date` on päivä, jolle tekninen havainto kirjataan.

Esimerkiksi Hammer-kandidaatti kirjataan sille päivälle, jonka kynttilä muodostaa Hammerin.

### 12.2 signal_confirmed_as_of_date

`signal_confirmed_as_of_date` on päivä, jolloin havainto on aidosti tiedossa ilman lookaheadia.

Yhden kynttilän kuviot ovat tiedossa saman päivän close-barin jälkeen.

Esimerkkejä:

```text
Hammer
Shooting Star
Hanging Man
Dragonfly Doji
```

Näillä alustava sääntö:

```text
signal_confirmed_as_of_date = signal_date
```

Monen kynttilän kuviot ovat tiedossa vasta kuvion viimeisen kynttilän sulkeuduttua.

Esimerkkejä:

```text
Morning Star
Evening Star
Three White Soldiers
Falling Three Methods
```

Näillä alustava sääntö:

```text
signal_confirmed_as_of_date = final_pattern_bar_date
```

Ehdoton V1/V5-sääntö:

```text
For multi-bar patterns, signal_confirmed_as_of_date must always be the final pattern bar close date/time.
```

Suositus V1/V5-toteutukseen:

```text
For multi-bar patterns, signal_date should also be the final pattern bar date/time.
```

Jos nykyinen RawCandle-tallennusmalli käyttää monen kynttilän kuviolle kuvion alkamispäivää `signal_date`-arvona, se on sallittua vain, jos `signal_confirmed_as_of_date` tallennetaan erikseen ja on aina final pattern barin sulkeutumispäivä/aika.

Backtest- ja as-of-lukukerroksen pitää käyttää confirmed-tietona aina:

```text
signal_confirmed_as_of_date
```

ei pelkkää `signal_date`-arvoa.

Multi-bar patternia ei saa koskaan näyttää havaittavana ennen final pattern barin sulkeutumista.

---

## 14. TECH_SIGNAL_MAPPING_V1 — single source of truth

`TECH_SIGNAL_MAPPING_V1` on ainoa sallittu lähde seuraaville tiedoille:

```text
accepted signal_name values
signal_direction
signal_family
signal_source_type
```

`signal_source_type` mahdolliset arvot:

```text
CANDLE
DIVERGENCE
```

Mapping ei saa olla hajautettuna eri tiedostoihin tai eri sääntöfunktioihin.

Jos mapping muuttuu, muutoksesta pitää seurata vähintään mapping-version muutos. Jos muutos vaikuttaa relevance-luokituksiin, myös `relevance_rule_version` pitää arvioida uudelleen.

### 13.1 Alustava mapping

Lopulliset `signal_name`-arvot pitää lukita koodin nykyisten nimien perusteella ennen toteutusta. Alla oleva taulukko kuvaa tavoitemappingin ihmislukuisilla nimillä.

| signal_name | signal_direction | signal_family | signal_source_type |
|---|---|---|---|
| Hammer | BULLISH | REVERSAL_MEDIUM | CANDLE |
| Bullish Engulfing | BULLISH | REVERSAL_STRONG | CANDLE |
| Piercing Pattern | BULLISH | REVERSAL_MEDIUM | CANDLE |
| Three White Soldiers | BULLISH | CONTINUATION | CANDLE |
| Morning Star | BULLISH | REVERSAL_STRONG | CANDLE |
| Dragonfly Doji | BULLISH | REVERSAL_MEDIUM | CANDLE |
| Bullish Abandoned Baby | BULLISH | REVERSAL_STRONG | CANDLE |
| Bullish Flag | BULLISH | CONTINUATION | CANDLE |
| Bull Rectangle | BULLISH | CONTINUATION | CANDLE |
| Ascending Triangle | BULLISH | STRUCTURAL_PATTERN | CANDLE |
| Bullish Pennant | BULLISH | CONTINUATION | CANDLE |
| Cup and Handle | BULLISH | STRUCTURAL_PATTERN | CANDLE |
| Bullish Divergence | BULLISH | DIVERGENCE | DIVERGENCE |
| Hidden Bullish Divergence | BULLISH | HIDDEN_DIVERGENCE | DIVERGENCE |
| Bearish Engulfing | BEARISH | REVERSAL_STRONG | CANDLE |
| Shooting Star | BEARISH | REVERSAL_MEDIUM | CANDLE |
| Dark Cloud Cover | BEARISH | REVERSAL_MEDIUM | CANDLE |
| Evening Star | BEARISH | REVERSAL_STRONG | CANDLE |
| Hanging Man | BEARISH | REVERSAL_MEDIUM | CANDLE |
| Falling Three Methods | BEARISH | CONTINUATION | CANDLE |
| Bearish Flag | BEARISH | CONTINUATION | CANDLE |
| Bear Rectangle | BEARISH | CONTINUATION | CANDLE |
| Descending Triangle | BEARISH | STRUCTURAL_PATTERN | CANDLE |
| Bearish Pennant | BEARISH | CONTINUATION | CANDLE |
| Bearish Divergence | BEARISH | DIVERGENCE | DIVERGENCE |
| Hidden Bearish Divergence | BEARISH | HIDDEN_DIVERGENCE | DIVERGENCE |

---

## 15. signal_source_id semantiikka

`signal_source_id` tunnistaa signaalin alalähteen tai indikaattorin silloin, kun `signal_name` ei yksin riitä yksilöimään havaintoa.

Perussääntö:

```text
signal_source_id identifies the sub-source or indicator behind the signal when signal_name alone is not unique.
```

V1-oletukset:

```text
Candlestick patterns:
signal_source_type = CANDLE
signal_source_id = CANDLE

Current RSI divergence:
signal_source_type = DIVERGENCE
signal_source_id = RSI
```

Tulevaisuuden mahdollisia arvoja:

```text
MACD
STOCH
OBV
VOLUME
```

Sääntö:

```text
signal_source_id must be deterministic.
```

Jos `signal_source_type = CANDLE`, V1:ssä käytetään aina:

```text
signal_source_id = CANDLE
```

Jos `signal_source_type = DIVERGENCE` ja nykyinen data tulee `divergence_data`-taulun RSI-pohjaisesta logiikasta, V1:ssä käytetään:

```text
signal_source_id = RSI
```

Jos lähdettä ei voida päätellä deterministisesti, havainto ei saa saada hiljaista oletusarvoa. Tällöin toteutuksen pitää joko:

```text
1. palauttaa UNKNOWN_SIGNAL_NAME / INSUFFICIENT_CONTEXT -tyyppinen fallback
```

tai

```text
2. epäonnistua kontrolloidusti validointivaiheessa
```

V1-suositus:

```text
Unknown or missing signal_source_id should be treated as a validation error for known mapped signals.
```

Tuntemattomalle `signal_name`-arvolle sovelletaan erillistä unknown signal fallback -sääntöä.

---

## 16. TECH_SIGNAL_RELEVANCE_REASON_V1 — enum

`relevance_reason` ei saa olla vapaatekstiä.

Kaikki syyt pitää tulla keskitetystä enum-listasta:

```text
TECH_SIGNAL_RELEVANCE_REASON_V1
```

### 14.1 Yleiset reason-arvot

```text
NO_DOW_CONTEXT_AVAILABLE
UNKNOWN_SIGNAL_NAME
MAPPING_VERSION_MISSING
INSUFFICIENT_CONTEXT
```

### 14.2 UP-trendin reason-arvot

```text
UP_TREND_BULLISH_CONTINUATION
UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW
UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT
UP_TREND_HIDDEN_BULLISH_DIVERGENCE
UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK
UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS
UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS
UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN
UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN
UP_TREND_BEARISH_CONTINUATION_WITHOUT_BEARISH_STRUCTURE
```

### 14.3 DOWN-trendin reason-arvot

```text
DOWN_TREND_BEARISH_CONTINUATION
DOWN_TREND_BEARISH_PULLBACK_REVERSAL_NEAR_PIVOT_HIGH
DOWN_TREND_BEARISH_REVERSAL_WITHOUT_PIVOT_CONTEXT
DOWN_TREND_HIDDEN_BEARISH_DIVERGENCE
DOWN_TREND_REGULAR_BEARISH_DIVERGENCE_WEAK
DOWN_TREND_COUNTER_BULLISH_REVERSAL_STRONG_WITHOUT_BOS
DOWN_TREND_COUNTER_BULLISH_REVERSAL_MEDIUM_WITHOUT_BOS
DOWN_TREND_BULLISH_REVERSAL_AFTER_BOS_UP
DOWN_TREND_BULLISH_DIVERGENCE_AFTER_BOS_UP
DOWN_TREND_BULLISH_CONTINUATION_WITHOUT_BULLISH_STRUCTURE
```

### 14.4 NEUTRAL reason-arvot

```text
NEUTRAL_CONTINUATION_NO_TREND
NEUTRAL_REVERSAL_STRONG_WEAK_CONTEXT
NEUTRAL_REVERSAL_MEDIUM_NOISE
NEUTRAL_DIVERGENCE_WEAK_CONTEXT
NEUTRAL_STRUCTURAL_PATTERN_WEAK_CONTEXT
```

### 14.5 NEUTRAL_AFTER_RESET reason-arvot

```text
NEUTRAL_AFTER_RESET_STRONG_REVERSAL
NEUTRAL_AFTER_RESET_DIVERGENCE
NEUTRAL_AFTER_RESET_HIDDEN_DIVERGENCE_WEAK
NEUTRAL_AFTER_RESET_CONTINUATION_WITHOUT_TREND
NEUTRAL_AFTER_RESET_MEDIUM_REVERSAL_WEAK
```

### Unknown signal fallback

Jos `signal_name` ei löydy `TECH_SIGNAL_MAPPING_V1`-mappingista, luokittelu ei saa epäonnistua epädeterministisesti eikä havaintoa saa hiljaisesti pudottaa.

Sääntö:

```text
relevance_class = WEAK_CONTEXT
relevance_reason = UNKNOWN_SIGNAL_NAME
signal_direction = NULL
signal_family = NULL
signal_source_type = NULL
signal_source_id = NULL
```

`rule_trace`-kenttään pitää lisätä vähintään:

```text
unknown_signal_name=true
mapping_version=TECH_SIGNAL_MAPPING_V1
```

Tulkinta:

```text
UNKNOWN_SIGNAL_NAME is a mapping/data-quality issue, not a market signal.
```

SwingMaster ei saa käyttää `UNKNOWN_SIGNAL_NAME`-rivejä ostoa/myyntiä tukevina teknisinä signaaleina.

Jos tuotantoputkessa halutaan tiukempi käytös, batch-CLI voi erikseen tarjota `--strict-mapping`-tyyppisen option, joka epäonnistuu tuntemattomaan signaaliin. Puhtaan `classify_relevance(...)`-funktion default on kuitenkin deterministinen fallback.

---

## 17. Config parameters

V1 käyttää eksplisiittisiä konfiguraatioarvoja.

Default-arvot:

```text
near_pivot_window_bars = 5
recent_bos_window_bars = 10
recent_reset_window_bars = 20
near_bos_level_pct = 3.0
```

Näitä ei saa hajauttaa eri toteutuskohtiin. Niiden pitää tulla yhdestä config-rakenteesta.

Jos config-arvo muuttuu, muutos pitää näkyä auditoinnissa `config_snapshot_json`-kentässä. Jos config-muutos muuttaa luokittelujen semantiikkaa, pitää harkita `relevance_rule_version`-version nostoa.

---

## 18. config_snapshot_json

Jokaiselle ajolle pitää tallentaa config snapshot.

Suositeltu kenttä:

```text
config_snapshot_json TEXT NOT NULL
```

Esimerkki:

```json
{
  "rule_version": "TECH_SIGNAL_RELEVANCE_V1",
  "mapping_version": "TECH_SIGNAL_MAPPING_V1",
  "reason_version": "TECH_SIGNAL_RELEVANCE_REASON_V1",
  "near_pivot_window_bars": 5,
  "recent_bos_window_bars": 10,
  "recent_reset_window_bars": 20,
  "near_bos_level_pct": 3.0
}
```

Tämä on auditointia varten. Downstream-logiikan ei pidä parsia `config_snapshot_json`-kenttää päätöksentekoon.

---

## 19. Pivot-konteksti

Technical Signal Relevance V1 ei määrittele pivot-validiutta uudelleen.

Se käyttää vain Dow-laskennan jo vahvistamia pivot-eventtejä.

`near_latest_pivot` saa käyttää vain pivotteja, joilla on:

```text
event_type IN ('PIVOT_LOW', 'PIVOT_HIGH')
confirmed_as_of_date <= signal_confirmed_as_of_date
```

Lisäksi pivotin pitää kuulua yhteensopivaan rakennekontekstiin. Jos Dow-moottori tuottaa `structure_epoch_id`-tiedon, relevance-laskennan pitää käyttää vain signaalin kontekstiin sopivan epochin pivotteja, ellei nimenomaisesti käsitellä RESETin jälkeistä tilaa.

Bullish-signaalille relevantti pivot:

```text
latest confirmed PIVOT_LOW
```

Bearish-signaalille relevantti pivot:

```text
latest confirmed PIVOT_HIGH
```

`near_latest_pivot = 1`, jos havainto on enintään `near_pivot_window_bars` barin päässä relevantista pivotista.

---

## 20. BOS- ja RESET-kontekstin käyttö

`recent_bos = 1`, jos viimeisin samaan suuntaan relevantti BOS on tapahtunut enintään `recent_bos_window_bars` ennen havaintoa ja on vahvistettu viimeistään havaintoon mennessä.

Ehto:

```text
bos_event.confirmed_as_of_date <= signal_confirmed_as_of_date
```

`recent_reset = 1`, jos viimeisin RESET on tapahtunut enintään `recent_reset_window_bars` ennen havaintoa ja on vahvistettu viimeistään havaintoon mennessä.

Ehto:

```text
reset_event.confirmed_as_of_date <= signal_confirmed_as_of_date
```

---

## 21. bars_since_* -kaavat

V1/V5 käyttää `bars_since_*`-kentissä kalenteripäivien sijasta analysoitujen OHLCV-kynttilöiden määrää.

### 19.1 bars_since_latest_bos

Kaava:

```text
bars_since_latest_bos =
number of analyzed bars between latest usable BOS confirmed_as_of_date
and observation.signal_confirmed_as_of_date
within the same ticker + timeframe.
```

Jos käyttökelpoista BOS-tapahtumaa ei ole:

```text
bars_since_latest_bos = NULL
```

Sääntöjä:

```text
Calendar days must not be used.
Exchange holidays must not be counted.
Missing OHLCV rows must not be counted.
Only actual OHLCV bars in the analyzed timeframe are counted.
```

Jos BOS ja havainto vahvistuvat samalla barilla:

```text
bars_since_latest_bos = 0
```

Jos BOS vahvistui edellisellä analysoidulla barilla:

```text
bars_since_latest_bos = 1
```

### 19.2 bars_since_latest_reset

Kaava:

```text
bars_since_latest_reset =
number of analyzed bars between latest usable RESET confirmed_as_of_date
and observation.signal_confirmed_as_of_date
within the same ticker + timeframe.
```

Jos käyttökelpoista RESET-tapahtumaa ei ole:

```text
bars_since_latest_reset = NULL
```

Jos RESET ja havainto vahvistuvat samalla barilla:

```text
bars_since_latest_reset = 0
```

Jos RESET vahvistui edellisellä analysoidulla barilla:

```text
bars_since_latest_reset = 1
```

### 19.3 Käyttö recent-lipuissa

`recent_bos = 1`, jos:

```text
bars_since_latest_bos IS NOT NULL
AND bars_since_latest_bos <= recent_bos_window_bars
```

`recent_reset = 1`, jos:

```text
bars_since_latest_reset IS NOT NULL
AND bars_since_latest_reset <= recent_reset_window_bars
```

### 19.4 Bar-indeksin lähde

Toteutuksen pitää laskea `bars_since_*` samasta OHLCV-sarjasta, jota käytetään kyseisen tickerin ja timeframe:n tekniseen analyysiin.

Jos bar-sarjaa ei ole saatavilla, funktio ei saa käyttää kalenteripäiväfallbackia hiljaisesti.

Sallittu fallback vain eksplisiittisesti:

```text
bars_since_latest_bos = NULL
bars_since_latest_reset = NULL
relevance_reason may remain otherwise deterministic
rule_trace must include missing_bar_index=true
```

---

## 22. Same-bar event precedence

Primary rule:

```text
Technical Signal Relevance must consume Dow engine persisted output.
It must not recompute Dow event ordering.
```

Relevance-luokittelu ei saa keksiä omaa Dow-eventtien järjestystä.

Sen pitää käyttää Dow-moottorin tuottamia tapahtumia, statusta ja `confirmed_as_of_date`-arvoja.

Jos usealla Dow-eventillä on sama `confirmed_as_of_date`, tulkinnan pitää vastata Dow-moottorin omaa event-putkea.

Fallback rule:

```text
If persisted Dow ordering is not available in tests or pure function fixtures,
use deterministic precedence:
RESET > BOS_UP/BOS_DOWN > TREND_CHANGE > PIVOT_HIGH/PIVOT_LOW
```

Tätä fallbackia saa käyttää vain testifixtureissä tai pure function -tasolla, kun Dow-moottorin persistoidut eventit eivät sisällä eksplisiittistä järjestystä.

Nykyisen Dow-putken mukainen looginen järjestys on:

```text
1. pivot handling
2. trend_state update
3. active BOS level sync
4. BOS check
5. possible RESET
```

Relevance-laskennan ensisijainen tapa on lukea Dow-moottorin tuottama lopputila samalle `as_of_date`:lle eikä laskea tätä järjestystä uudelleen.

Jos toteutuksessa tarvitaan eksplisiittinen järjestys saman confirmed-päivän tapahtumille, alustava deterministinen järjestys on:

```text
PIVOT_HIGH / PIVOT_LOW
TREND_CHANGE
BOS_UP / BOS_DOWN
RESET
```

Mutta jos tämä on ristiriidassa Dow-moottorin todellisen persistoidun event-järjestyksen kanssa, Dow-moottorin persistoidut tapahtumat voittavat.

---

## 23. Lähikontekstin käsitteet

### 20.1 near_latest_pivot

```text
near_latest_pivot = 1
```

jos havainto on enintään `near_pivot_window_bars` barin päässä viimeisimmästä relevantista vahvistetusta pivotista.

### 20.2 near_active_bos_level

```text
near_active_bos_level = 1
```

jos havainto tapahtuu lähellä aktiivista BOS-tasoa.

Default:

```text
distance_pct <= near_bos_level_pct
```

### near_active_bos_level -kaava

Tason valinta:

```text
For bullish observations:
use active_bos_low_price when available.

For bearish observations:
use active_bos_high_price when available.
```

Etäisyys:

```text
distance_pct = abs(signal_close_price - active_bos_level_price) / active_bos_level_price * 100
```

Lippu:

```text
near_active_bos_level = 1 if distance_pct <= near_bos_level_pct
else 0
```

Jos aktiivista BOS-tasoa ei ole:

```text
near_active_bos_level = 0
```

Jos `signal_close_price` ei ole saatavilla:

```text
near_active_bos_level = 0
rule_trace must include missing_signal_close_price=true
```

V1/V5-rajaus:

```text
near_active_bos_level is computed and stored for context, audit and future analysis.
In V1/V5, near_active_bos_level must not upgrade or downgrade relevance_class.
```

Tämä tarkoittaa, että `near_active_bos_level` ei esiinny V1/V5-sääntömatriisin päätöksentekijänä. Se voidaan myöhemmin ottaa mukaan erillisessä V2-säännössä, jos halutaan arvioida signaalin sijaintia suhteessa aktiiviseen BOS-tasoon.

### 20.3 recent BOS

```text
recent_bos = 1
```

jos viimeisin relevantti BOS on tapahtunut enintään `recent_bos_window_bars` baria ennen havaintoa.

### 20.4 recent RESET

```text
recent_reset = 1
```

jos viimeisin RESET on tapahtunut enintään `recent_reset_window_bars` baria ennen havaintoa.

---

## 24. Missing data policy

Puuttuva data ei saa hiljaisesti tuottaa vahvempaa `relevance_class`-arvoa.

Perussääntö:

```text
Missing data must never silently produce a stronger relevance_class.
```

### Dow-konteksti puuttuu

Jos Dow-konteksti puuttuu kokonaan:

```text
relevance_class = WEAK_CONTEXT
relevance_reason = NO_DOW_CONTEXT_AVAILABLE
rule_trace includes missing_dow_context=true
```

### Bar-indeksi puuttuu

Jos bar-indeksiä ei voida muodostaa samalle ticker + timeframe -sarjalle:

```text
bars_since_latest_bos = NULL
bars_since_latest_reset = NULL
rule_trace includes missing_bar_index=true
```

Toteutus ei saa käyttää kalenteripäiväfallbackia hiljaisesti.

### Pivot-konteksti puuttuu

Jos pivot-data puuttuu tai yhtään käyttökelpoista no-lookahead-pivotia ei ole:

```text
near_latest_pivot = 0
rule_trace includes missing_pivot_context=true
```

Tämä ei saa automaattisesti muuttaa signaalia `RELEVANT`-luokkaan.

### BOS/RESET-historia puuttuu

Jos BOS/RESET-eventtejä ei ole saatavilla:

```text
recent_bos = 0
recent_reset = 0
bars_since_latest_bos = NULL
bars_since_latest_reset = NULL
rule_trace includes missing_event_context=true
```

### signal_close_price puuttuu

Jos `signal_close_price` puuttuu:

```text
near_active_bos_level = 0
rule_trace includes missing_signal_close_price=true
```

### Unknown signal

Tuntematon `signal_name` käsitellään deterministisesti erillisellä fallback-säännöllä:

```text
relevance_class = WEAK_CONTEXT
relevance_reason = UNKNOWN_SIGNAL_NAME
rule_trace includes unknown_signal_name=true
```


---

## 25. Deterministinen luokittelujärjestys

Säännöt pitää ajaa tietyssä järjestyksessä, jotta tulos on deterministinen.

Suositeltu järjestys:

```text
1. Tarkista onko havainto tunnistettu TECH_SIGNAL_MAPPING_V1-mappingissa.
2. Määritä signal_direction, signal_family ja signal_source_type mappingista.
3. Tarkista signal_confirmed_as_of_date.
4. Hae Dow trend_state havaintoon nähden ilman lookaheadia.
5. Hae viimeisin käyttökelpoinen BOS ilman lookaheadia.
6. Hae viimeisin käyttökelpoinen RESET ilman lookaheadia.
7. Hae viimeisin käyttökelpoinen relevantti pivot ilman lookaheadia.
8. Laske near_latest_pivot.
9. Laske near_active_bos_level.
10. Päätä dow_context_state.
11. Päätä is_trend_aligned ja is_counter_trend.
12. Päätä relevance_class sääntömatriisilla.
13. Kirjoita relevance_reason enumista.
14. Kirjoita rule_trace debug/audit-käyttöön.
```

Jos Dow-kontekstia ei ole:

```text
relevance_class = WEAK_CONTEXT
relevance_reason = NO_DOW_CONTEXT_AVAILABLE
```

Ei siis automaattisesti NOISE, koska havainto voi olla teknisesti oikea mutta kontekstiton.

---

## 26. Sääntömatriisi V1

### 22.1 Kun Dow = UP

#### Bullish continuation

Esimerkkejä:

```text
Bullish Flag
Bullish Pennant
Bull Rectangle
Three White Soldiers
Ascending Triangle
Cup and Handle
```

Luokitus:

```text
UP + bullish continuation
=> RELEVANT
```

Reason:

```text
UP_TREND_BULLISH_CONTINUATION
```

#### Bullish reversal / dip reversal

Esimerkkejä:

```text
Hammer
Bullish Engulfing
Piercing Pattern
Morning Star
Dragonfly Doji
Bullish Abandoned Baby
```

Luokitus:

```text
UP + bullish reversal + near_latest_pivot
=> RELEVANT
```

Reason:

```text
UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW
```

Luokitus ilman pivot-kontekstia:

```text
UP + bullish reversal + not near_latest_pivot
=> WEAK_CONTEXT
```

Reason:

```text
UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT
```

#### Hidden bullish divergence

```text
UP + Hidden Bullish Divergence
=> RELEVANT
```

Reason:

```text
UP_TREND_HIDDEN_BULLISH_DIVERGENCE
```

#### Regular bullish divergence

```text
UP + Bullish Divergence
=> WEAK_CONTEXT
```

Reason:

```text
UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK
```

#### Bearish reversal ilman BOS_DOWNia

```text
UP + bearish REVERSAL_STRONG + no recent BOS_DOWN
=> WEAK_CONTEXT
```

Reason:

```text
UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS
```

Tärkeä tulkintarajaus:

```text
Counter-trend WEAK_CONTEXT is not a trend reversal signal.
It is only a warning/context note.
SwingMaster must not treat it as a trade trigger without BOS confirmation.
```

```text
UP + bearish REVERSAL_MEDIUM + no recent BOS_DOWN
=> NOISE
```

Reason:

```text
UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS
```

#### Bearish reversal BOS_DOWNin jälkeen

```text
UP + bearish reversal + recent BOS_DOWN
=> RELEVANT
```

Reason:

```text
UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN
```

#### Bearish divergence BOS_DOWNin jälkeen

```text
UP + Bearish Divergence + recent BOS_DOWN
=> RELEVANT
```

Reason:

```text
UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN
```

#### Bearish continuation UP-trendissä

```text
UP + bearish continuation + no recent BOS_DOWN
=> NOISE
```

Reason:

```text
UP_TREND_BEARISH_CONTINUATION_WITHOUT_BEARISH_STRUCTURE
```

---

### 22.2 Kun Dow = DOWN

#### Bearish continuation

Esimerkkejä:

```text
Bearish Flag
Bearish Pennant
Bear Rectangle
Falling Three Methods
Descending Triangle
```

Luokitus:

```text
DOWN + bearish continuation
=> RELEVANT
```

Reason:

```text
DOWN_TREND_BEARISH_CONTINUATION
```

#### Bearish reversal / pullback reversal

Esimerkkejä:

```text
Bearish Engulfing
Shooting Star
Dark Cloud Cover
Evening Star
Hanging Man
```

Luokitus:

```text
DOWN + bearish reversal + near_latest_pivot
=> RELEVANT
```

Reason:

```text
DOWN_TREND_BEARISH_PULLBACK_REVERSAL_NEAR_PIVOT_HIGH
```

Luokitus ilman pivot-kontekstia:

```text
DOWN + bearish reversal + not near_latest_pivot
=> WEAK_CONTEXT
```

Reason:

```text
DOWN_TREND_BEARISH_REVERSAL_WITHOUT_PIVOT_CONTEXT
```

#### Hidden bearish divergence

```text
DOWN + Hidden Bearish Divergence
=> RELEVANT
```

Reason:

```text
DOWN_TREND_HIDDEN_BEARISH_DIVERGENCE
```

#### Regular bearish divergence

```text
DOWN + Bearish Divergence
=> WEAK_CONTEXT
```

Reason:

```text
DOWN_TREND_REGULAR_BEARISH_DIVERGENCE_WEAK
```

#### Bullish reversal ilman BOS_UPia

```text
DOWN + bullish REVERSAL_STRONG + no recent BOS_UP
=> WEAK_CONTEXT
```

Reason:

```text
DOWN_TREND_COUNTER_BULLISH_REVERSAL_STRONG_WITHOUT_BOS
```

Tärkeä tulkintarajaus:

```text
Counter-trend WEAK_CONTEXT is not a trend reversal signal.
It is only a warning/context note.
SwingMaster must not treat it as a trade trigger without BOS confirmation.
```

```text
DOWN + bullish REVERSAL_MEDIUM + no recent BOS_UP
=> NOISE
```

Reason:

```text
DOWN_TREND_COUNTER_BULLISH_REVERSAL_MEDIUM_WITHOUT_BOS
```

#### Bullish reversal BOS_UPin jälkeen

```text
DOWN + bullish reversal + recent BOS_UP
=> RELEVANT
```

Reason:

```text
DOWN_TREND_BULLISH_REVERSAL_AFTER_BOS_UP
```

#### Bullish divergence BOS_UPin jälkeen

```text
DOWN + Bullish Divergence + recent BOS_UP
=> RELEVANT
```

Reason:

```text
DOWN_TREND_BULLISH_DIVERGENCE_AFTER_BOS_UP
```

#### Bullish continuation DOWN-trendissä

```text
DOWN + bullish continuation + no recent BOS_UP
=> NOISE
```

Reason:

```text
DOWN_TREND_BULLISH_CONTINUATION_WITHOUT_BULLISH_STRUCTURE
```

---

### 22.3 Kun Dow = NEUTRAL

#### Tavallinen NEUTRAL

```text
NEUTRAL + continuation
=> NOISE
```

Reason:

```text
NEUTRAL_CONTINUATION_NO_TREND
```

```text
NEUTRAL + REVERSAL_STRONG
=> WEAK_CONTEXT
```

Reason:

```text
NEUTRAL_REVERSAL_STRONG_WEAK_CONTEXT
```

```text
NEUTRAL + REVERSAL_MEDIUM
=> NOISE
```

Reason:

```text
NEUTRAL_REVERSAL_MEDIUM_NOISE
```

```text
NEUTRAL + DIVERGENCE
=> WEAK_CONTEXT
```

Reason:

```text
NEUTRAL_DIVERGENCE_WEAK_CONTEXT
```

```text
NEUTRAL + STRUCTURAL_PATTERN
=> WEAK_CONTEXT
```

Reason:

```text
NEUTRAL_STRUCTURAL_PATTERN_WEAK_CONTEXT
```

#### NEUTRAL_AFTER_RESET

```text
NEUTRAL_AFTER_RESET + REVERSAL_STRONG
=> RELEVANT
```

Reason:

```text
NEUTRAL_AFTER_RESET_STRONG_REVERSAL
```

```text
NEUTRAL_AFTER_RESET + DIVERGENCE
=> RELEVANT
```

Reason:

```text
NEUTRAL_AFTER_RESET_DIVERGENCE
```

```text
NEUTRAL_AFTER_RESET + HIDDEN_DIVERGENCE
=> WEAK_CONTEXT
```

Reason:

```text
NEUTRAL_AFTER_RESET_HIDDEN_DIVERGENCE_WEAK
```

```text
NEUTRAL_AFTER_RESET + CONTINUATION
=> NOISE
```

Reason:

```text
NEUTRAL_AFTER_RESET_CONTINUATION_WITHOUT_TREND
```

```text
NEUTRAL_AFTER_RESET + REVERSAL_MEDIUM
=> WEAK_CONTEXT
```

Reason:

```text
NEUTRAL_AFTER_RESET_MEDIUM_REVERSAL_WEAK
```

---

## 27. Suositellut kentät

Uuteen relevance-kerrokseen tarvitaan vähintään seuraavat loogiset kentät.

```text
ticker
timeframe
signal_date
signal_confirmed_as_of_date
signal_name
signal_close_price
signal_direction
signal_family
signal_source_type
signal_source_id
dow_trend_state
dow_context_state
latest_bos_direction
bars_since_latest_bos
latest_reset_reason
bars_since_latest_reset
near_latest_pivot
near_active_bos_level
is_trend_aligned
is_counter_trend
relevance_class
relevance_reason
relevance_rule_version
mapping_version
reason_version
rule_trace
created_at_utc
run_id
```

### 23.1 relevance_class

```text
RELEVANT
WEAK_CONTEXT
NOISE
```

### 23.2 signal_direction

```text
BULLISH
BEARISH
```

### 23.3 signal_family

```text
REVERSAL_STRONG
REVERSAL_MEDIUM
CONTINUATION
STRUCTURAL_PATTERN
DIVERGENCE
HIDDEN_DIVERGENCE
```

### 23.4 signal_source_type

```text
CANDLE
DIVERGENCE
```

### 23.5 dow_context_state

```text
NORMAL
AFTER_BOS
AFTER_RESET
NO_STRUCTURE
```

---

## 28. Tallennusmalli V1

V5 erottaa ajometadatan ja yksittäiset relevance-rivit.

Tämä vähentää konfiguraation duplikointia ja tekee auditoinnista selkeämmän.

### 24.1 Run metadata -taulu

Suositeltu taulu:

```text
technical_signal_relevance_runs
```

Alustava looginen rakenne:

```sql
run_id TEXT PRIMARY KEY NOT NULL
relevance_rule_version TEXT NOT NULL
mapping_version TEXT NOT NULL
reason_version TEXT NOT NULL
config_snapshot_json TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

`config_snapshot_json` tallennetaan kerran per `run_id`.

### 24.2 Relevance result -taulu

Suositeltu taulu:

```text
technical_signal_relevance
```

Alustava looginen rakenne:

```sql
ticker TEXT NOT NULL
timeframe TEXT NOT NULL
signal_date TEXT NOT NULL
signal_confirmed_as_of_date TEXT NOT NULL
signal_name TEXT NOT NULL
signal_close_price REAL NULL
signal_direction TEXT NOT NULL
signal_family TEXT NOT NULL
signal_source_type TEXT NOT NULL
signal_source_id TEXT NULL
dow_trend_state TEXT NULL
dow_context_state TEXT NULL
latest_bos_direction TEXT NULL
bars_since_latest_bos INTEGER NULL
latest_reset_reason TEXT NULL
bars_since_latest_reset INTEGER NULL
near_latest_pivot INTEGER NOT NULL
near_active_bos_level INTEGER NOT NULL
is_trend_aligned INTEGER NOT NULL
is_counter_trend INTEGER NOT NULL
relevance_class TEXT NOT NULL
relevance_reason TEXT NOT NULL
relevance_rule_version TEXT NOT NULL
mapping_version TEXT NOT NULL
reason_version TEXT NOT NULL
rule_trace TEXT NULL
created_at_utc TEXT NOT NULL
run_id TEXT NOT NULL
```

`signal_source_id` on varautumiskenttä useille signaalilähteille.

Esimerkkejä:

```text
CANDLE
RSI
MACD
STOCH
```

Nykyiselle RSI-pohjaiselle divergence_data-lähteelle alustava arvo voi olla:

```text
RSI
```

Jos lähde ei ole erillisesti määritelty, kenttä voi olla `NULL`.

Mahdollinen primary key:

```sql
PRIMARY KEY (
  ticker,
  timeframe,
  signal_date,
  signal_name,
  signal_source_type,
  relevance_rule_version
)
```

Jos V1-toteutuksessa sallitaan useita saman `signal_name`-arvon havaintoja samalle tickerille, timeframe:lle ja signal_date:lle eri lähteistä, pitää primary keyyn lisätä myös:

```text
signal_source_id
```

tai ottaa käyttöön erillinen surrogate id.

Suositellut indeksit:

```sql
CREATE INDEX idx_technical_signal_relevance_ticker_tf_date
ON technical_signal_relevance(ticker, timeframe, signal_date);

CREATE INDEX idx_technical_signal_relevance_ticker_tf_class_date
ON technical_signal_relevance(ticker, timeframe, relevance_class, signal_date);

CREATE INDEX idx_technical_signal_relevance_run_id
ON technical_signal_relevance(run_id);
```

### 24.3 Config snapshot -periaate

`technical_signal_relevance`-rivillä ei tarvitse olla `config_snapshot_json`-kenttää, koska se löytyy `run_id`-viittauksen kautta run-taulusta.

Downstream-lukijan pitää käyttää varsinaisissa riveissä olevia eksplisiittisiä kenttiä, ei parsia `config_snapshot_json`-arvoa päätöksentekoa varten.

---

## 29. Rule version

Ensimmäinen sääntöversio:

```text
TECH_SIGNAL_RELEVANCE_V1
```

Mapping-versio:

```text
TECH_SIGNAL_MAPPING_V1
```

Reason-versio:

```text
TECH_SIGNAL_RELEVANCE_REASON_V1
```

Kaikki kirjoitetut rivit saavat nämä arvot.

Näitä ei saa kovakoodata epäselvästi eri paikkoihin, vaan niiden pitää tulla keskitetystä vakio- tai config-rakenteesta.

---

## 30. rule_trace

`rule_trace` on debug- ja audit-käyttöön tarkoitettu kenttä.

Se voidaan tallentaa esimerkiksi JSON-listana.

### rule_trace minimum fields

`rule_trace` must include at minimum:

```text
mapping_version
reason_version
relevance_rule_version
selected relevance_reason
used latest_bos_event_id, if available
used latest_reset_event_id, if available
used latest_pivot_event_id, if available
dow_structure_epoch_id, if available
run_id or config_snapshot_hash
missing_bar_index flag
missing_dow_context flag
missing_pivot_context flag
missing_event_context flag
missing_signal_close_price flag
unknown_signal_name flag
```

Jos jokin event-id ei ole saatavilla, kentän voi merkitä eksplisiittisesti `null`-arvolla tai jättää pois, kunhan `rule_trace` sisältää vastaavan missing-flagin.

Esimerkki:

```json
[
  "mapping_version=TECH_SIGNAL_MAPPING_V1",
  "reason_version=TECH_SIGNAL_RELEVANCE_REASON_V1",
  "relevance_rule_version=TECH_SIGNAL_RELEVANCE_V1",
  "signal_family=REVERSAL_STRONG",
  "dow_trend_state=UP",
  "dow_structure_epoch_id=4",
  "latest_bos_event_id=bos_123",
  "latest_reset_event_id=null",
  "latest_pivot_event_id=pivot_456",
  "latest_bos_direction=BOS_DOWN",
  "recent_bos=true",
  "missing_bar_index=false",
  "missing_dow_context=false",
  "missing_pivot_context=false",
  "missing_event_context=false",
  "missing_signal_close_price=false",
  "unknown_signal_name=false",
  "class=RELEVANT",
  "reason=UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN"
]
```

Sääntö:

```text
rule_trace must never be used as downstream decision logic.
```

SwingMaster saa käyttää:

```text
relevance_class
relevance_reason
```

SwingMaster ei saa käyttää `rule_trace`-kenttää päätöksenteon lähteenä.

---

## 31. Pure rule function contract

Ensimmäinen toteutus pitää tehdä puhtaana, yksikkötestattavana sääntöfunktiona ilman tietokantakirjoitusta.

Suositeltu funktiosopimus:

```python
classify_relevance(
    observation,
    dow_state,
    events,
    pivots,
    config,
) -> relevance_record
```

### 27.1 observation

Sisältää vähintään:

```text
ticker
timeframe
signal_date
signal_confirmed_as_of_date
signal_name
```

### 27.2 dow_state

Sisältää havaintoon nähden no-lookahead-suodatetun Dow-tilan:

```text
trend_state
active_bos_high_price
active_bos_low_price
structure_epoch_id
as_of_date
```

### 27.3 events

Sisältää no-lookahead-suodatetut tapahtumat:

```text
BOS_UP
BOS_DOWN
RESET
TREND_CHANGE
```

Kaikkien tapahtumien pitää täyttää:

```text
confirmed_as_of_date <= signal_confirmed_as_of_date
```

`classify_relevance(...)` ei saa luottaa kutsujan antamaan järjestykseen.

Funktion pitää joko:

```text
sortata events deterministisesti itse
```

tai kutsusopimuksen pitää olla testein varmistettu niin, että events-lista on aina valmiiksi järjestetty.

Suositeltu sisäinen deterministinen järjestys:

```text
confirmed_as_of_date DESC
event_date DESC
event_precedence DESC
```

missä saman confirmed-päivän alustava precedence on:

```text
RESET > BOS_UP/BOS_DOWN > TREND_CHANGE > PIVOT_HIGH/PIVOT_LOW
```

Jos Dow-moottorin persistoidussa tapahtumajärjestyksessä on tästä poikkeava eksplisiittinen järjestys, Dow-moottorin järjestys voittaa.

### 27.4 pivots

Sisältää no-lookahead-suodatetut vahvistetut pivotit:

```text
PIVOT_HIGH
PIVOT_LOW
```

Kaikkien pivotien pitää täyttää:

```text
confirmed_as_of_date <= signal_confirmed_as_of_date
```

`classify_relevance(...)` ei saa luottaa kutsujan antamaan pivot-listan järjestykseen.

Funktion pitää sortata pivotit deterministisesti tai kutsusopimuksen pitää olla testein varmistettu.

Suositeltu sisäinen deterministinen järjestys:

```text
confirmed_as_of_date DESC
event_date DESC
```

Kun `structure_epoch_id` on saatavilla, pivot-kontekstin pitää ensisijaisesti käyttää nykyisen `dow_state.structure_epoch_id`-arvon pivotteja.

RESET-kontekstissa viimeisin RESET voi olla tapahtuma, joka aloitti nykyisen epochin. Tällöin RESET-eventti voi kuulua edeltävän ja nykyisen epochin rajalle, mutta pivot-kontekstissa ei saa käyttää vanhan epochin pivotteja uuden epochin trenditulkinnan tukena.

### 27.5 config

Sisältää vähintään:

```text
rule_version
mapping_version
reason_version
near_pivot_window_bars
recent_bos_window_bars
recent_reset_window_bars
near_bos_level_pct
```

### 27.6 relevance_record

Palauttaa vähintään:

```text
signal_direction
signal_family
signal_source_type
signal_source_id
dow_trend_state
dow_context_state
latest_bos_direction
bars_since_latest_bos
latest_reset_reason
bars_since_latest_reset
near_latest_pivot
near_active_bos_level
is_trend_aligned
is_counter_trend
relevance_class
relevance_reason
relevance_rule_version
mapping_version
reason_version
rule_trace
```

---

## 32. Esimerkkiluokituksia

### 28.1 Hammer UP-trendissä HL:n lähellä

```text
signal_name = Hammer
signal_direction = BULLISH
signal_family = REVERSAL_MEDIUM
dow_trend_state = UP
near_latest_pivot = 1
is_trend_aligned = 1
relevance_class = RELEVANT
relevance_reason = UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW
```

### 28.2 Shooting Star UP-trendissä ilman BOS_DOWNia

```text
signal_name = Shooting Star
signal_direction = BEARISH
signal_family = REVERSAL_MEDIUM
dow_trend_state = UP
latest_bos_direction = NULL
is_counter_trend = 1
relevance_class = NOISE
relevance_reason = UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS
```

### 28.3 Bearish Engulfing UP-trendissä BOS_DOWNin jälkeen

```text
signal_name = Bearish Engulfing
signal_direction = BEARISH
signal_family = REVERSAL_STRONG
dow_trend_state = UP
latest_bos_direction = BOS_DOWN
bars_since_latest_bos = 3
is_counter_trend = 1
relevance_class = RELEVANT
relevance_reason = UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN
```

### 28.4 Bullish Flag RESETin jälkeen

```text
signal_name = Bullish Flag
signal_direction = BULLISH
signal_family = CONTINUATION
dow_context_state = AFTER_RESET
relevance_class = NOISE
relevance_reason = NEUTRAL_AFTER_RESET_CONTINUATION_WITHOUT_TREND
```

### 28.5 Bullish Divergence RESETin jälkeen

```text
signal_name = Bullish Divergence
signal_direction = BULLISH
signal_family = DIVERGENCE
dow_context_state = AFTER_RESET
relevance_class = RELEVANT
relevance_reason = NEUTRAL_AFTER_RESET_DIVERGENCE
```

### 28.6 Pivot event_date ennen signaalia mutta confirmed_as_of_date myöhemmin

```text
signal_date = 2026-05-10
signal_confirmed_as_of_date = 2026-05-10
pivot.event_date = 2026-05-08
pivot.confirmed_as_of_date = 2026-05-13
```

Tulkinta:

```text
pivot must not be usable for this signal
```

---

## 33. Testimatriisi V1

### 29.1 Perusluokitustestit

Vähintään yksi testi jokaiselle seuraavista:

```text
UP + bullish continuation => RELEVANT
UP + bullish reversal near pivot low => RELEVANT
UP + bullish reversal without pivot context => WEAK_CONTEXT
UP + hidden bullish divergence => RELEVANT
UP + bearish medium reversal without BOS_DOWN => NOISE
UP + bearish strong reversal without BOS_DOWN => WEAK_CONTEXT
UP + bearish reversal after BOS_DOWN => RELEVANT
UP + bearish continuation without bearish structure => NOISE

DOWN + bearish continuation => RELEVANT
DOWN + bearish reversal near pivot high => RELEVANT
DOWN + bearish reversal without pivot context => WEAK_CONTEXT
DOWN + hidden bearish divergence => RELEVANT
DOWN + bullish medium reversal without BOS_UP => NOISE
DOWN + bullish strong reversal without BOS_UP => WEAK_CONTEXT
DOWN + bullish reversal after BOS_UP => RELEVANT
DOWN + bullish continuation without bullish structure => NOISE

NEUTRAL + continuation => NOISE
NEUTRAL + reversal strong => WEAK_CONTEXT
NEUTRAL + reversal medium => NOISE
NEUTRAL + divergence => WEAK_CONTEXT
NEUTRAL_AFTER_RESET + reversal strong => RELEVANT
NEUTRAL_AFTER_RESET + divergence => RELEVANT
NEUTRAL_AFTER_RESET + continuation => NOISE
```

### 29.2 Edge-case-testit

Pakolliset edge-case-testit:

```text
BOS + pivot same confirmed_as_of_date
first BOS + recovery => no RESET
double BOS => RESET
pivot event_date <= signal_date but confirmed_as_of_date > signal_confirmed_as_of_date => pivot not usable
multi-bar pattern with signal_confirmed_as_of_date before final pattern bar => invalid / must fail
near_active_bos_level formula with active level missing => near_active_bos_level = 0
near_active_bos_level formula with close missing => near_active_bos_level = 0 + rule_trace marker
unknown signal_name => WEAK_CONTEXT + UNKNOWN_SIGNAL_NAME deterministic fallback
no Dow context => WEAK_CONTEXT + NO_DOW_CONTEXT_AVAILABLE
```

### 29.3 Determinismitestit

Sama input pitää tuottaa täsmälleen sama output:

```text
same relevance_class
same relevance_reason
same rule_trace
same config_snapshot_json
```

---

## 34. Hyväksymiskriteerit

V1 on valmis, kun seuraavat ehdot täyttyvät:

```text
1. Kaikki nykyiset RawCandlen laskemat kynttiläkuviot ja divergenssit voidaan mapata TECH_SIGNAL_MAPPING_V1-mappingilla.

2. Mapping on single source of truth eikä hajallaan eri toteutuskohdissa.

3. Jokainen havainto saa täsmälleen yhden relevance_class-arvon.

4. Relevance_class on aina yksi arvoista:
   RELEVANT
   WEAK_CONTEXT
   NOISE

5. Jokainen havainto saa deterministisen relevance_reason-arvon TECH_SIGNAL_RELEVANCE_REASON_V1-enumista.

6. Relevance_reason ei ole koskaan vapaatekstiä.

7. Luokitus käyttää vain havaintopäivään mennessä vahvistettua Dow-dataa:
   context.confirmed_as_of_date <= signal_confirmed_as_of_date

8. Pivotteja saa käyttää vain, jos pivot.confirmed_as_of_date <= signal_confirmed_as_of_date.

9. RESETin jälkeinen NEUTRAL erotetaan tavallisesta NEUTRAL-tilasta.

10. Continuation-kuvioita ei hyväksytä RELEVANT-luokkaan RESETin jälkeen.

11. Vastatrendisiä reversal-kuvioita ei hyväksytä RELEVANT-luokkaan ilman BOS-kontekstia.

12. Hidden divergence tulkitaan ensisijaisesti trendin jatkumisen havaintona.

13. Regular divergence tulkitaan ensisijaisesti mahdollisena käännehavaintona.

14. config_snapshot_json tallennetaan jokaiselle ajolle.

15. rule_trace tallennetaan debug/audit-käyttöön, mutta sitä ei käytetä downstream-päätöksenteossa.

16. Pure classify_relevance(...) -funktio on yksikkötestattu ennen DB-integraatiota.

17. Edge-case-testit kattavat same-bar BOS/pivot -tapauksen, first BOS + recovery -tapauksen, double BOS -> RESET -tapauksen ja pivot-confirmation lookahead -tapauksen.

18. Kaikilla relevance-riveillä on eksplisiittinen timeframe.

19. Aikaikkunat perustuvat bar-laskentaan, eivät kalenteripäiviin.

20. Multi-bar patternin signal_confirmed_as_of_date on aina final pattern bar close date/time.

21. near_active_bos_level tallennetaan V1/V5-kontekstiksi, mutta se ei muuta relevance_class-arvoa.

22. config_snapshot_json tallennetaan run-tauluun kerran per run_id.

23. structure_epoch_id-konteksti estää vanhan epochin pivotteja tukemasta uuden epochin trenditulkintaa.

24. bars_since_latest_bos ja bars_since_latest_reset lasketaan analysoitujen barien määränä samassa ticker + timeframe -sarjassa.

25. signal_source_id on deterministinen:
   CANDLE kynttilöille ja RSI nykyisille RSI-divergensseille.

26. Multi-bar patternien bar-luokitus on eksplisiittinen ja niiden signal_confirmed_as_of_date on aina final pattern bar close date/time.

27. near_active_bos_level-kaava on eksplisiittinen, mutta lippu ei muuta V1/V5 relevance_class-arvoa.

28. Unknown signal fallback on deterministinen:
   WEAK_CONTEXT + UNKNOWN_SIGNAL_NAME.

29. rule_trace sisältää V6:n minimikentät tai niitä vastaavat eksplisiittiset missing-flagit.

30. Puuttuva data ei saa hiljaisesti vahvistaa relevance_class-arvoa.

31. Same-bar precedence käyttää ensisijaisesti Dow-moottorin persistuoitua järjestystä ja vain test/fallback-tilanteessa eksplisiittistä fallback-precedenceä.

32. Config-muutokset noudattavat audit-only vs semantic config change -politiikkaa.

33. Speksi on lukittu ensimmäistä Codex-työpakettia varten.

34. SwingMaster voi lukea relevance_class-arvon ilman, että sen tarvitsee tietää kynttiläkuvioiden sisäistä logiikkaa.
```

---

## 35. Production hardening -suositellut metriikat

Nämä metriikat eivät kuulu ensimmäisen pure-function-työpaketin pakolliseen scopeen, mutta ne suositellaan tuotantokovennukseen.

Suositellut run-kohtaiset metriikat:

```text
unknown_signal_count per run_id
missing_bar_index_count per run_id
missing_dow_context_count per run_id
missing_pivot_context_count per run_id
missing_event_context_count per run_id
relevance_distribution by timeframe
relevance_distribution by ticker
relevance_distribution by relevance_class
```

Suositellut alert-aiheet:

```text
unknown_signal_count kasvaa odottamatta
missing_bar_index_count kasvaa odottamatta
relevance_distribution muuttuu äkillisesti, esimerkiksi RELEVANT -> NOISE -jakauma siirtyy voimakkaasti
Dow-context-missing kasvaa ajon jälkeen
```

Nämä metriikat auttavat havaitsemaan mapping-, OHLCV-, Dow-moottori- tai migration-ongelmia tuotannossa.


---

## 36. Mitä V1 ei vielä tee

V1 ei vielä:

```text
muuta alkuperäistä kynttilälaskentaa
muuta divergenssilaskentaa
muuta Dow-rakenteen laskentaa
määrittele pivot-validiutta uudelleen
tee osto- tai myyntipäätöksiä
anna pisteytystä 0–100
arvioi near_active_bos_level-lipun perusteella relevance_classia
arvioi volyymivahvistusta
arvioi markkinaregimeä
arvioi fundamenttikontekstia
korvaa SwingMasterin tulkintakerrosta
```

Volyymivahvistus voidaan lisätä myöhemmin erillisenä versiona, esimerkiksi:

```text
TECH_SIGNAL_RELEVANCE_V2_VOLUME_CONFIRMATION
```

---

## 37. Toteutusjärjestys

Suositeltu toteutusjärjestys:

```text
Step 1:
Lukitse koodin nykyiset signal_name-arvot ja nykyinen daily-timeframe-arvo.

Step 2:
Toteuta TECH_SIGNAL_MAPPING_V1 single source of truth.

Step 3:
Toteuta TECH_SIGNAL_RELEVANCE_REASON_V1 enum single source of truth.

Step 4:
Toteuta config-rakenne, *_bars-parametrit ja run-kohtainen config_snapshot_json.

Step 5:
Toteuta puhdas classify_relevance(...) -funktio ilman DB:tä.

Step 6:
Kirjoita unit-testit perusmatriisille ja edge-caseille.

Step 7:
Lisää run-taulu, relevance-taulu ja batch CLI vasta kun sääntöfunktio on vihreä.

Step 8:
Lisää SwingMaster-lukeminen vasta viimeisenä.
```

---

## 38. Ensimmäisen Codex-työpaketin rajaus

Ensimmäisen Codex-promptin ei pidä tehdä DB-migraatiota. Tämä V6-speksi on lukittu ensimmäisen Codex-työpaketin lähteeksi.

Ensimmäinen työpaketti:

```text
TECH_SIGNAL_MAPPING_V1
TECH_SIGNAL_RELEVANCE_REASON_V1
config-rakenne
timeframe- ja bar-käsitteet
classify_relevance(...) pure function
unit-testit
```

Ei mukaan ensimmäiseen työpakettiin:

```text
DB migration
batch CLI
SwingMaster integration
performance optimization
volume confirmation
```

Tämä pitää muutoksen pienenä, testattavana ja deterministisenä.
