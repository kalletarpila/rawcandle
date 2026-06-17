# Datacenter Dashboard -päättelykerroksen spesifikaatio

## Tarkoitus

Tämä dokumentti kuvaa, miten **Datacenter Dashboard** tekee päättelyt raporttiriveistä.

Tämä on eri kerros kuin raporttigenerointi.

Raporttikerros tuottaa valmiita kenttiä kuten:

- `raw_status`
- `raw_action`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_reset_reason`
- `ma_break_status`
- `freshness_status`
- `high_exit_risk_days_count`

Dashboard-kerros lukee nämä ja muodostaa niiden päälle:

- `action`
- `severity`
- `primary_reason`
- `pullback_validity`
- `pullback_reason`
- `entry_readiness`
- `entry_readiness_reason`
- `candidate_priority`
- `candidate_priority_label`
- `candidate_priority_reason`


## Kanoninen totuus

Kanoninen toteutus on tiedostossa:

- [dev_tools/datacenter_dashboard_decisions.py](/home/kalle/projects/rawcandle/dev_tools/datacenter_dashboard_decisions.py:1)

Tämä dokumentti on ihmislukijalle tehty kuvaus nykyisestä toteutuksesta.
Jos dokumentti ja koodi ovat ristiriidassa, koodi voittaa.


## Inputit dashboard-päättelyyn

Dashboard käyttää parserin tuottamia rivejä:

- [dev_tools/datacenter_dashboard_parser.py](/home/kalle/projects/rawcandle/dev_tools/datacenter_dashboard_parser.py:1)

Yksi parseririvi on `DatacenterDashboardRow`.

Päättely käyttää erityisesti näitä kenttiä:

- `ticker`
- `horizon`
- `raw_action`
- `raw_status`
- `reason`
- `blocking_reasons`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_reset_reason`
- `distance_to_ema20`
- `high_exit_risk_days_count`
- `latest_bullish_signal_age_td`
- `latest_bearish_signal_age_td`
- `ma_break_status`
- `freshness_status`
- `structure_warning_overrides_bullish_signal`
- `raw_fields`


## Horizon-normalisointi

Dashboard normalisoi horizon-nimet funktiolla `_normalize_horizon(...)`.

Tunnistetut horizonit:

- `daily`
- `rolling 2d`
- `rolling 5d`
- `rolling 30d`

Esimerkiksi nämä normalisoituvat samaan:

- `rolling30d`
- `rolling_30d`
- `rolling 30d`


## Ticker-kohtainen ryhmittely

Päättely tehdään aina ticker-kohtaisesti.

`build_datacenter_ticker_decisions(...)`:

1. ryhmittelee kaikki parseririvit tickerin mukaan
2. normalisoi horizonit
3. kerää tekstiarvot sääntöjen token-matchausta varten
4. muodostaa yhden `DatacenterTickerDecision`-olion per ticker


## Dashboardin tuottama pääobjekti

Yksi ticker tuottaa tämän rakenteen:

- `action`
- `severity`
- `primary_reason`
- `reasons`
- `blocking_reasons`
- `horizons_present`
- `horizon_statuses`
- `distance_to_ema20`
- `high_exit_risk_days_count`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_reset_reason`
- `latest_bullish_signal_age_td`
- `latest_bearish_signal_age_td`
- `pullback_validity`
- `pullback_reason`
- `entry_readiness`
- `entry_readiness_reason`
- `candidate_priority`
- `candidate_priority_label`
- `candidate_priority_reason`
- `source_files`
- `decision_trace`


## Horizon-statuses

Dashboard muodostaa `horizon_statuses`-mapin näin:

- avain = normalisoitu horizon
- arvo = `row.raw_status or row.raw_action or ""`

Tämä on tärkeä ero:

- `horizon_statuses` ei ole dashboardin laskema final action
- se on horizon-kohtainen raportista luettu status/action-teksti


## Action-prioriteetti

Dashboardin lopullisten actionien järjestys on:

1. `SELL`
2. `REDUCE`
3. `TIGHTEN_STOP`
4. `BLOCKED`
5. `WAIT_PULLBACK`
6. `BUY_NOW`
7. `WATCH`
8. `NEUTRAL`

Tämä prioriteetti näkyy sekä:

- tickerien järjestyksessä
- action count -aggregoinneissa


## Severity-by-action

Dashboard ei laske severityä itsenäisesti jokaiselle tickerille erikseen.
Severity tulee suoraan actionista:

- `SELL -> CRITICAL`
- `REDUCE -> HIGH`
- `TIGHTEN_STOP -> MEDIUM`
- `BLOCKED -> HIGH`
- `WAIT_PULLBACK -> MEDIUM`
- `BUY_NOW -> HIGH`
- `WATCH -> LOW`
- `NEUTRAL -> INFO`


## Tekstipohjainen evidenssi

Dashboard ei päättele vain eksplisiittisistä kentistä.
Se käyttää myös token-matchausta tekstisisältöihin.

Tekstihaku tehdään kentistä:

- `raw_action`
- `raw_status`
- `reason`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_reset_reason`
- `blocking_reasons`
- sekä kaikki `raw_fields`-arvot

Tärkeät token-setit:

- hard sell:
  - `return_10d_lt_minus_8pct`
  - `sell`

- rolling 2d BOS down:
  - `bos_down`

- rolling 2d confirmation:
  - `reset`
  - `double_bos_down`
  - `high_exit_risk`
  - `failed_pullback`
  - `close_below_ema20`
  - `return_10d_lt_minus_8pct`
  - `sell`

- reduce:
  - `reduce`
  - `risk`
  - `high_exit_risk`
  - `exit_risk`
  - `subindustry_context_risk`

- rolling 30d positive:
  - `buy_zone`
  - `leader`
  - `positive_trend`
  - `up`
  - `hh`
  - `hl`
  - `bos_up`

- rolling 5d constructive:
  - `pullback`
  - `breakout`
  - `base_ready`
  - `support`
  - `reversal`

- daily positive:
  - `buy_now`
  - `bullish`
  - `dip`
  - `reversal`
  - `bos_up`
  - `support`


## Lopullisen actionin päättely

Dashboard käy action-säännöt läpi käytännössä ylhäältä alas.
Ensimmäinen vahvin osuma määrää actionin.

Alla on nykyinen looginen järjestys.


### 1. `SELL` SMA50 confirmed break

Jos `daily`- tai `rolling 2d` -kontekstissa löytyy:

- `ma_break_status == "SMA50_CONFIRMED_BREAK"`

niin:

- `action = SELL`
- `primary_reason = SELL_SIGNAL_DETECTED`


### 2. `SELL` EMA20 confirmed break

Jos `daily`- tai `rolling 2d` -kontekstissa löytyy:

- `ma_break_status == "EMA20_CONFIRMED_BREAK"`

niin:

- `action = SELL`
- `primary_reason = SELL_SIGNAL_DETECTED`


### 3. `SELL` hard sell -tokenit

Jos `daily`- tai `rolling 2d` -kontekstissa löytyy hard sell -evidenssiä:

- `sell`
- `return_10d_lt_minus_8pct`
- tai fallbackina `close_below_ema20`, jos acute MA status puuttuu

niin:

- `action = SELL`
- `primary_reason = SELL_SIGNAL_DETECTED`


### 4. `SELL` confirmed acute rolling 2d BOS_DOWN

Jos tickerillä on akuutti vahvistettu `rolling 2d BOS_DOWN`, dashboard myy.

Tämä tarkistetaan helperillä:

- `_has_acute_confirmed_rolling_2d_bos_down(...)`

Sen logiikka on:

1. rolling 2d -rivissä pitää olla `bos_down`
2. lisäksi pitää löytyä vähintään yksi vahvistava tekijä daily- tai rolling 2d -kontekstista:
   - rolling 2d confirmation token
   - rolling 2d reset
   - daily bearish confirmation
   - hard sell match
   - `high_exit_risk_days_count >= 1`

Jos tämä täyttyy:

- `action = SELL`
- `primary_reason = SELL_SIGNAL_DETECTED`


### 5. `REDUCE` rolling 2d BOS_DOWN + vain pidemmän horizonin vahvistus

Jos `rolling 2d` sisältää `bos_down`, mutta vahvistus tulee vain pidemmästä kontekstista:

- `rolling 30d`
- `rolling 5d`

niin action alennetaan:

- `action = REDUCE`
- `primary_reason = RISK_SIGNAL_DETECTED`

Tämä on käytännössä "ei vielä akuutti sell, mutta riskisignaali on oikea".


### 6. `REDUCE` SMA50 warning

Jos acute-kontekstissa on:

- `ma_break_status == "SMA50_WARNING"`

niin:

- `action = REDUCE`


### 7. `REDUCE` EMA20 warning

Jos acute-kontekstissa on:

- `ma_break_status == "EMA20_WARNING"`

niin:

- `action = REDUCE`


### 8. `REDUCE` direct reduce match

Jos acute-kontekstissa löytyy reduce-/risk-token-osuma:

- `reduce`
- `risk`
- `high_exit_risk`
- `exit_risk`
- `subindustry_context_risk`

niin:

- `action = REDUCE`


### 9. `REDUCE` unconfirmed rolling 2d BOS_DOWN

Jos `rolling 2d` sisältää `bos_down`, mutta acute confirmed sell -ehto ei täyty:

- `action = REDUCE`


### 10. `REDUCE` unconfirmed rolling 2d RESET

Jos `rolling 2d` sisältää `reset`, mutta vahvempi acute sell -ehto ei täyty:

- `action = REDUCE`


### 11. `TIGHTEN_STOP`

Jos:

- `high_exit_risk_days_count >= 1`

niin:

- `action = TIGHTEN_STOP`
- `primary_reason = HIGH_EXIT_RISK_DAYS_PRESENT`


### 12. `BLOCKED`

Jos tickerillä on ei-tyhjiä `blocking_reasons`-arvoja, eikä mikään vahvempi sääntö ole jo voittanut:

- `action = BLOCKED`
- `primary_reason = BLOCKING_REASONS_PRESENT`


### 13. `WAIT_PULLBACK`

Jos:

- `rolling_30_positive == True`
- ja `distance_to_ema20 > 15.0`

niin:

- `action = WAIT_PULLBACK`
- `primary_reason = STRETCHED_ABOVE_EMA20`


### 14. `BUY_NOW`

Jos kaikki täyttyvät:

- ei `freshness_structure_override`
- `rolling_30_positive`
- `rolling_5_constructive`
- `daily_positive`

niin:

- `action = BUY_NOW`
- `primary_reason = MULTI_HORIZON_ALIGNMENT`


### 15. `WATCH`

Jos:

- ei `freshness_structure_override`
- `rolling_30_positive`

mutta täydellinen multi-horizon alignment puuttuu, niin:

- `action = WATCH`
- `primary_reason = ROLLING_30_POSITIVE_ONLY`


### 16. `NEUTRAL`

Jos mikään muu sääntö ei osu:

- `action = NEUTRAL`
- `primary_reason = NO_DECISIVE_SIGNAL`


## Erikoistapaus: `BLOCKED` voidaan muuttaa `REDUCE`:ksi

Jos dashboard olisi muuten antamassa:

- `BLOCKED`

mutta acute-kontekstissa löytyy `direct_reduce_match`,
niin `BLOCKED` yliajetaan:

- `action = REDUCE`
- `primary_reason = RISK_SIGNAL_DETECTED`

Tämä on poikkeussääntö, joka estää liian heikon `BLOCKED`-tuloksen jäämisen voimaan, jos oikea riskisignaali löytyi.


## Pullback-validity

Dashboard laskee erikseen `pullback_validity`-luokituksen.

Mahdolliset arvot:

- `VALID_PULLBACK`
- `EARLY_PULLBACK`
- `STRUCTURE_BLOCKED_PULLBACK`
- `BREAKDOWN_NOT_PULLBACK`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

Tämä tehdään funktiolla:

- `_classify_pullback_validity(...)`


### Pullback-validityn peruslogiikka

1. Jos pullback-kontekstia ei löydy:
   - `NO_PULLBACK`

2. Jos rakenne-/freshness-konteksti puuttuu:
   - `INSUFFICIENT_DATA`

3. Jos acute-kontekstissa löytyy rakenteellinen blokkeri:
   - `STRUCTURE_BLOCKED_PULLBACK`

4. Jos löytyy acute confirmed rolling 2d BOS_DOWN:
   - `STRUCTURE_BLOCKED_PULLBACK`
   - reason:
     - `ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK`

5. Jos acute-kontekstissa löytyy confirmed MA break:
   - `BREAKDOWN_NOT_PULLBACK`

6. Jos on fresh bullish signal + hyväksyttävä MA-tila + ei structure overridea:
   - `VALID_PULLBACK`

7. Jos confirmed MA break puuttuu:
   - `EARLY_PULLBACK`

8. Muuten:
   - `INSUFFICIENT_DATA`


### Pullback-kontekstin tunnistus

Pullback-konteksti katsotaan löytyvän, jos:

- tekstissä esiintyy jokin seuraavista:
  - `pullback_candidate`
  - `early_pullback`
  - `failed_pullback`
- tai `raw_fields["pullback_days"] > 0`


### Rakenteelliset blokkerit pullbackille

Acute-horizonit ovat:

- `daily`
- `rolling 2d`

Jos näissä löytyy jokin seuraavista, pullback blokataan:

- `freshness_status == "STRUCTURE_WARNING_OVERRIDES_BULLISH"`
- `structure_warning_overrides_bullish_signal == 1`
- `latest_bos_event_type == "BOS_DOWN"` + fresh marker
- `latest_reset_reason` sisältää `DOUBLE_BOS_DOWN` + fresh marker
- `latest_reset_reason` sisältää `RESET` + fresh marker


### MA-breakdown -> not pullback

Jos acute-riveissä löytyy:

- `SMA50_CONFIRMED_BREAK`
- tai `EMA20_CONFIRMED_BREAK`

niin:

- `pullback_validity = BREAKDOWN_NOT_PULLBACK`


### Valid pullback

`VALID_PULLBACK` vaatii:

- hyväksyttävä MA-status:
  - `OK`
  - tai `EMA20_WARNING`
  - tai acute-riveissä ei ole lainkaan MA-statusta
- ei structure overridea
- vähintään yksi `freshness_status == "FRESH_BULLISH_SIGNAL"`


### Early pullback

Jos confirmed MA break puuttuu mutta rakenne ei vielä eksplisiittisesti blokkaa:

- `pullback_validity = EARLY_PULLBACK`
- reason:
  - `WAIT_FOR_BULLISH_CONFIRMATION`


## Entry readiness

Dashboard laskee pullback-validityn ja final actionin päälle `entry_readiness`-luokituksen.

Mahdolliset arvot:

- `READY_TO_WATCH`
- `NEEDS_STOP_STABILIZATION`
- `NEEDS_RISK_CLEARANCE`
- `EARLY_MONITOR`
- `NOT_READY`
- `INSUFFICIENT_DATA`

Tämä tehdään funktiolla:

- `_classify_entry_readiness(...)`


### Entry readiness -säännöt

Jos puuttuu:

- `pullback_validity`
- tai `action`

niin:

- `INSUFFICIENT_DATA`

Jos `pullback_validity == "VALID_PULLBACK"`:

- `WATCH` tai `NEUTRAL`
  - `READY_TO_WATCH`
- `TIGHTEN_STOP`
  - `NEEDS_STOP_STABILIZATION`
- `REDUCE`
  - `NEEDS_RISK_CLEARANCE`
- `SELL`
  - `NOT_READY`

Jos `pullback_validity == "EARLY_PULLBACK"`:

- `EARLY_MONITOR`

Jos `pullback_validity` on jokin seuraavista:

- `STRUCTURE_BLOCKED_PULLBACK`
- `BREAKDOWN_NOT_PULLBACK`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

niin:

- `NOT_READY`


## Candidate priority

Dashboard laskee vielä `candidate_priority`-tason.

Mahdolliset labelit:

- `P1_READY_TO_WATCH`
- `P2_STOP_STABILIZATION`
- `P3_RISK_CLEARANCE`
- `P4_EARLY_MONITOR`
- `P5_NOT_READY`
- `P9_NOT_CANDIDATE`

Tämä tehdään funktiolla:

- `_classify_candidate_priority(...)`


### Candidate priority -säännöt

- `READY_TO_WATCH`
  - `1 / P1_READY_TO_WATCH`

- `NEEDS_STOP_STABILIZATION`
  - `2 / P2_STOP_STABILIZATION`

- `NEEDS_RISK_CLEARANCE`
  - `3 / P3_RISK_CLEARANCE`

- `EARLY_MONITOR`
  - `4 / P4_EARLY_MONITOR`

- `NOT_READY`
  - `5 / P5_NOT_READY`

- kaikki muut tai puuttuvat
  - `9 / P9_NOT_CANDIDATE`


## Decision trace

Dashboard yrittää aina tallentaa myös perustelujäljen:

- `decision_trace`

Trace-rivi kertoo esimerkiksi:

- mikä sääntö osui
- missä horizonissa osuma löytyi
- mistä kentästä
- millä tokenilla
- mikä arvo osui

Trace on tärkeä debug-tarkoituksiin, mutta se ei itsessään päätä actionia.
Se vain selittää, miksi action syntyi.


## Aggregaatit batch-tasolla

Kun kaikki tickerit on päätelty, dashboard muodostaa batch-yhteenvedot:

- `action_counts`
- `pullback_counts`
- `pullback_action_counts`
- `entry_readiness_counts`
- `candidate_priority_counts`
- `warning_count`
- `warnings`

Kaikille tunnetuille action- ja luokitteluarvoille asetetaan zero-defaultit, vaikka niitä ei esiintyisi yhdessäkään tickerissä.


## Kriittinen ero reporttikerrokseen

Dashboard ei laske kaikkea tyhjästä.

Se käyttää reporttikerroksen kenttiä inputtina:

- reporttitaso kertoo, mitä eri horizonien riveillä näkyy
- dashboard-taso päättää, miten näistä riveistä tehdään yksi ticker-kohtainen lopputulkinta

Siksi:

- `raw_status` / `raw_action` eivät ole sama asia kuin dashboard `action`
- `watchlist_status` ei ole sama asia kuin dashboard `final action`
- rolling 5d pullback-state ei ole sama asia kuin dashboard `pullback_validity`


## Tulkintasäännöt ihmiselle

Kun ihminen lukee dashboard-logiikkaa, oikea malli on tämä:

1. Dashboard etsii ensin akuutit riskit daily- ja rolling 2d -kontekstista.
2. Vasta jos vahvaa riskiä ei löydy, se katsoo stop-tightening-, blocking- ja wait-pullback -tasot.
3. `BUY_NOW` vaatii aidon multi-horizon-alignmentin.
4. `WATCH` on heikompi positiivinen tila kuin `BUY_NOW`.
5. Pullback-validity on erillinen luokittelu, joka ei yksin määrää final actionia.
6. Entry readiness ja candidate priority ovat puhtaasti read-only diagnostisia luokituksia final actionin päälle.


## Käyttösäännöt tulevalle AI-chatille

Kun tuleva AI kuvaa dashboardin päättelyjä, sen tulee noudattaa näitä sääntöjä:

1. Erota aina reporttikerros ja dashboard-kerros toisistaan.
2. Älä sano, että dashboardin final action tulee suoraan yhdestä reporttistatuksesta.
3. Kuvaa mieluummin:
   - input-signaalit
   - action-prioriteetti
   - pullback-validity
   - readiness
   - candidate priority
4. Jos epävarmuutta jää, viittaa suoraan `datacenter_dashboard_decisions.py`-koodiin.
