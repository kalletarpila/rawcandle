# Kynttiläkuvio-Excel Dokumentaatio

**Versio:** 1.0  
**Päivämäärä:** 25.10.2025  
**Tekijä:** Rawcandle-järjestelmä

---

## 1. Johdanto

Tämä dokumentaatio selittää **kynttiläkuvio-Excel-tiedoston** sisällön, sarakkeiden merkityksen ja laskentalogiikan. Excel-tiedosto sisältää teknisen analyysin indikaattoreita ja historiadataa osakkeiden kynttiläkuvioiden tunnistamiseen perustuen.

**Tiedoston tarkoitus:**
- Tunnistaa tietyt kynttiläkuviot (Hammer, Doji, Shooting Star, Engulfing)
- Laskea signaalin vahvuus kullekin kuviolle
- Tarjota historiallista ja tulevaa hintadataa normalisoituna (t₀ = 100)
- Tarjota volatiliteetti-, volyymi-, liukuvan keskiarvon ja indeksitietoja analyysiä varten

---

## 2. Kynttiläkuviot ja Numerokoodit

Järjestelmä tunnistaa seuraavat **kynttiläkuviot** (Pattern) ja niiden numerokoodit:

| Numerokoodi | Kuvion nimi        | Lyhyt kuvaus                                                      |
|-------------|-------------------|-------------------------------------------------------------------|
| 0           | **Laskutrendi**    | Arvottu osake arvottuna päivänä laskutrendin aikana (suodatettu)  |
| 1           | **Hammer**         | Nousevan trendin kääntymiskuvio, pitkä alavarjo, pieni runko     |
| 2           | **Bullish Engulfing** | Bullish Engulfing, nykyinen kynttilä "nielee" edellisen laskeva kynttilän |
| 3           | **Piercing Pattern** | Nousevan kääntymisen kuvio, toinen kynttilä sulkeutuu edellisen rungon yläpuolelle |
| 4           | **Three White Soldiers** | Kolme peräkkäistä nousevaa kynttilää, vahva noususignaali |
| 5           | **Morning Star**   | Kolmen kynttilän nouseva kääntymiskuvio (laskeva → doji → nouseva) |
| 6           | **Dragonfly Doji** | Doji-muunnelma, pitkä alavarjo, ei ylävarjoa                      |

**HUOM:** Numerokoodi **0** käytetään kun:
- Laskutrendi-suodatin on käytössä ja osake täyttää laskutrendin kriteerit
- Kynttilä ei kuulu mihinkään tunnettuun kuvioon (tuntematon pattern)

### 2.1 Kynttiläkuvioiden tunnistuslogiikka

**HUOM:** Kynttiläkuvioiden tunnistus tapahtuu analysis-moduulissa. Alla esimerkkejä tärkeimmistä kuvioista.

#### **Hammer** (Numerokoodi 1)
- **Tunnistus:**  
  - Pitkä alavarjo (lower shadow): `alavarjo ≥ 2 × runko`
  - Lyhyt ylävarjo (upper shadow): `ylävarjo ≤ 0.5 × runko`
  - Pieni runko verrattuna koko kynttiläkuvioon

- **Merkitys:**  
  Hammer-kuvio voi merkitä **nousevan trendin alkua** tai laskutrendin kääntymistä, erityisesti kun se esiintyy laskevan trendin jälkeen. Kuvio kertoo ostajien vahvasta paluusta.

- **Kuinka tulkita:**  
  - Vahva signaali (lähellä 1.0) tarkoittaa, että alavarjo on huomattavan pitkä ja runko pieni → vahva ostopaine päivän lopussa
  - Heikko signaali (lähellä 0.0) tarkoittaa, että kuvio on vain hiukan Hammerin muotoinen

#### **Bullish Engulfing** (Numerokoodi 2)
- **Tunnistus:**  
  - Edellinen kynttilä laskeva (close < open)
  - Nykyinen kynttilä nouseva ja "nielee" edellisen
  - Nykyinen open < edellinen close JA nykyinen close > edellinen open

- **Merkitys:**  
  Bullish Engulfing kuvaa **voimakasta nousevan trendin alkua**. Ostajat ottavat selkeän vallan myyjiltä.

#### **Morning Star** (Numerokoodi 5)
- **Tunnistus:**  
  - Kolmen kynttilän kuvio
  - 1. kynttilä: laskeva (pitkä punainen)
  - 2. kynttilä: pieni runko (Doji tai lyhyt kynttilä)
  - 3. kynttilä: nouseva (pitkä vihreä)

- **Merkitys:**  
  Morning Star on vahva **kääntymissignaali laskutrendistä nousutrendiin**.

#### **Dragonfly Doji** (Numerokoodi 6)
- **Tunnistus:**  
  - Hyvin pieni runko (avaus ≈ päätös ≈ ylin)
  - Pitkä alavarjo
  - Ei käytännössä ylävarjoa

- **Merkitys:**  
  Dragonfly Doji viittaa mahdolliseen **nousevaan kääntymiseen**. Myyjät painoivat hintaa alas, mutta ostajat nostivat sen takaisin.

---

## 3. Signaalin Vahvuus (Signal Strength)

Järjestelmä laskee jokaiselle tunnistetulle kynttiläkuviolle **signaalin vahvuuden** välillä **0.0 – 1.0**. Vahvuus kuvaa, kuinka hyvin kuvio vastaa ideaalia muotoa ja kuinka luotettavana sitä voidaan pitää.

### 3.1 Signaalin vahvuuden laskentasäännöt kuvioperusteisesti

#### **Hammer** – Signaalin vahvuus
- **Peruskaava:**  
  `vahvuus = min(0.9, (alavarjon pituus / rungon koko) / 3.0)`
  
- **Selitys:**  
  Mitä pidempi alavarjo suhteessa runkoon, sitä vahvempi signaali. Jos alavarjo on yli 3× runko, vahvuus on lähes maksimi (0.9).

- **Tulkinta:**  
  - **Vahva signaali (0.7–1.0):** Alakaarjo selvästi pitkä, runko pieni → luotettava Hammer
  - **Keskivahva (0.5–0.7):** Alakaarjo kohtalaisen pitkä
  - **Heikko (0.0–0.5):** Vain osittain Hammer-muotoinen, kuvio epävarma

#### **Muut kuviot** – Signaalin vahvuus
Muiden kynttiläkuvioiden (Bullish Engulfing, Piercing Pattern, Three White Soldiers, Morning Star, Dragonfly Doji) signaalin vahvuus lasketaan analysis-moduulissa kuviokohtaisten sääntöjen mukaan.

**Yleinen periaate:**
- Vahvuus 0.7–1.0 = vahva signaali
- Vahvuus 0.5–0.7 = keskivahva signaali
- Vahvuus 0.0–0.5 = heikko signaali



## 4. Excel-sarakkeet ja niiden laskentalogiikka

Excel-tiedostossa on yhteensä **80 saraketta**. Alla on lista sarakkeiden nimistä, numerosta, merkityksestä ja laskentasäännöstä.

### 4.1 Perustiedot (sarakkeet 1–4)

| # | Sarake      | Merkitys                                      | Laskenta/Lähde                               |
|---|------------|-----------------------------------------------|---------------------------------------------|
| 1 | **osake**   | Osakkeen tunniste (ticker)                    | Haetaan analysis-tietokannasta              |
| 2 | **date**    | Kynttiläpäivän päivämäärä (t₀)                | Haetaan analysis-tietokannasta              |
| 3 | **kynttilä**| Kynttiläkuvion nimi (Hammer, Doji, ...)       | Tunnistettu kuvio analysis-tietokannasta    |
| 4 | **vahvuus** | Signaalin vahvuus 0.0–1.0                     | Laskettu `calculate_signal_strength()`       |

---

### 4.2 Kynttiläkomponentit (sarakkeet 5–16)

Kaikki kynttiläkomponentit ovat **normalisoitu** siten, että **t₀ alin hinta = 100**.

**HUOM:** **bodi** tarkoittaa **kynttilän rungon kokoa prosentteina** koko kynttilän vaihteluvälistä (high - low), **EI päätöskurssia**.

**Bodi-laskenta:**
```
candle_range = high - low
body_size = |close - open|
bodi (%) = (body_size / candle_range) × 100
```

Eli:
- **bodi = 0%** → Doji-tyyppinen kynttilä (avaus ≈ päätös)
- **bodi = 100%** → Täysin runkoa, ei lainkaan varjoja (low = open JA high = close, tai päinvastoin)
- **bodi = 50%** → Runko on puolet kynttilän kokonaispituudesta

#### **Päivän t₋₁** (edellinen päivä)

| # | Sarake             | Merkitys                       | Laskenta                                          |
|---|--------------------|-------------------------------|--------------------------------------------------|
| 5 | **t_1_alin**        | t₋₁ alin hinta (normalisoitu)  | `(low_t-1 / t0_low) × 100`                        |
| 6 | **t_1_ylin**        | t₋₁ ylin hinta (normalisoitu)  | `(high_t-1 / t0_low) × 100`                       |
| 7 | **t_1_bodi**        | t₋₁ rungon koko (% kynttilästä)| `(|close_t-1 - open_t-1| / (high_t-1 - low_t-1)) × 100` |
| 8 | **t_1_bodi_colour** | t₋₁ kynttilän väri             | `1` jos nouseva (close > open), `0` jos laskeva  |

#### **Päivän t₀** (tarkastelupäivä, kuviopäivä)

| # | Sarake             | Merkitys                       | Laskenta                                          |
|---|--------------------|-------------------------------|--------------------------------------------------|
| 9 | **t0_alin**         | t₀ alin hinta (normalisoitu)   | **Aina 100** (normalisointiperusta)               |
| 10| **t0_ylin**         | t₀ ylin hinta (normalisoitu)   | `(high_t0 / t0_low) × 100`                        |
| 11| **t0_bodi**         | t₀ rungon koko (% kynttilästä) | `(|close_t0 - open_t0| / (high_t0 - low_t0)) × 100` |
| 12| **t0_bodi_colour**  | t₀ kynttilän väri              | `1` nouseva (close > open), `0` laskeva           |

#### **Päivän t₁** (seuraava päivä)

| # | Sarake             | Merkitys                       | Laskenta                                          |
|---|--------------------|-------------------------------|--------------------------------------------------|
| 13| **t1_alin**         | t₁ alin hinta (normalisoitu)   | `(low_t1 / t0_low) × 100`                         |
| 14| **t1_ylin**         | t₁ ylin hinta (normalisoitu)   | `(high_t1 / t0_low) × 100`                        |
| 15| **t1_bodi**         | t₁ rungon koko (% kynttilästä) | `(|close_t1 - open_t1| / (high_t1 - low_t1)) × 100` |
| 16| **t1_bodi_colour**  | t₁ kynttilän väri              | `1` nouseva (close > open), `0` laskeva           |

---

### 4.3 Historialliset päätöskurssit (sarakkeet 17–21)

Kaikki normalisoitu t₀ alin hintaan (t₀ = 100).

| # | Sarake   | Merkitys                                | Laskenta                      |
|---|----------|-----------------------------------------|------------------------------|
| 17| **t_2**  | Päätöskurssi 2 päivää ennen t₀          | `(close_t-2 / t0_low) × 100`  |
| 18| **t_5**  | Päätöskurssi 5 päivää ennen t₀          | `(close_t-5 / t0_low) × 100`  |
| 19| **t_10** | Päätöskurssi 10 päivää ennen t₀         | `(close_t-10 / t0_low) × 100` |
| 20| **t_15** | Päätöskurssi 15 päivää ennen t₀         | `(close_t-15 / t0_low) × 100` |
| 21| **t_20** | Päätöskurssi 20 päivää ennen t₀         | `(close_t-20 / t0_low) × 100` |

---

### 4.4 Volatiliteetti (sarakkeet 22–26)

Volatiliteetti mitataan **standardipoikkeamana** päätöskurssien normalisoiduista arvoista taaksepäin katsottuna (HUOM: EI sisällä t₀-päivää, vaan vain t0:aa edeltävät päivät). Normalisointi: jokainen arvo on (close_t-i / low_t0) * 100.

**HUOM:** Volatiliteetti lasketaan normalisoiduista arvoista: jokainen arvo on (close_t-i / low_t0) * 100. Lopputulos on näiden arvojen standardipoikkeama (ei valuuttayksikköä, vaan prosenttipohjainen hajonta).

#### Laskentasääntö

Volatiliteetti lasketaan käyttäen **Pythonin `statistics.pstdev`-funktiota**, joka laskee **populaation standardipoikkeaman** (population standard deviation):


$$
\sigma = \sqrt{\frac{1}{n} \sum_{i=1}^{n} (x_i - \bar{x})^2}
$$


jossa:
- $n$ = päivien lukumäärä (esim. 2, 5, 10, 15 tai 20)
- $x_i$ = normalisoitu päätöskurssi päivänä $i$ (eli $(close_{t-i}/low_{t0})*100$)
- $\bar{x}$ = normalisoitujen päätöskurssien keskiarvo


**HUOM:** Käytetään populaatiohajontaa (n jakajana, ei n−1). Tämä antaa hieman pienemmän arvon kuin otoshajonta.

**Laskentajakso:**

| # | Sarake         | Merkitys                           | Laskenta                                             |
|---|----------------|-----------------------------------|-----------------------------------------------------|
| 22| **t_2_hajonta** | Volatiliteetti 2 päivän ajalta     | `pstdev([(close_t-2/low_t0)*100, (close_t-1/low_t0)*100])`                       |
| 23| **t_5_hajonta** | Volatiliteetti 5 päivän ajalta     | `pstdev([(close_t-5/low_t0)*100, ..., (close_t-1/low_t0)*100])`                  |
| 24| **t_10_hajonta**| Volatiliteetti 10 päivän ajalta    | `pstdev([(close_t-10/low_t0)*100, ..., (close_t-1/low_t0)*100])`                 |
| 25| **t_15_hajonta**| Volatiliteetti 15 päivän ajalta    | `pstdev([(close_t-15/low_t0)*100, ..., (close_t-1/low_t0)*100])`                 |
| 26| **t_20_hajonta**| Volatiliteetti 20 päivän ajalta    | `pstdev([(close_t-20/low_t0)*100, ..., (close_t-1/low_t0)*100])`                 |

**Tulkinta:**
- **Korkea volatiliteetti:** Osakkeen hinta vaihtelee voimakkaasti → suurempi riski ja mahdollisuus
- **Matala volatiliteetti:** Osakkeen hinta pysyy vakaana → vähemmän volatiliteettia, vähemmän riskiä

---

### 4.5 Tulevat päätöskurssit (sarakkeet 27–30)

Normalisoitu t₀ alin hintaan (t₀ = 100).

| # | Sarake  | Merkitys                                 | Laskenta                      |
|---|---------|------------------------------------------|------------------------------|
| 27| **t2**  | Päätöskurssi 2 päivää t₀:n jälkeen       | `(close_t+2 / t0_low) × 100`  |
| 28| **t5**  | Päätöskurssi 5 päivää t₀:n jälkeen       | `(close_t+5 / t0_low) × 100`  |
| 29| **t10** | Päätöskurssi 10 päivää t₀:n jälkeen      | `(close_t+10 / t0_low) × 100` |
| 30| **t20** | Päätöskurssi 20 päivää t₀:n jälkeen      | `(close_t+20 / t0_low) × 100` |

**Käyttö:** Nämä sarakkeet mahdollistavat kynttiläkuvion **ennustearvon tarkistamisen**: jos esim. t₀ oli Hammer (ostosignaali), voidaan tarkistaa nousiko hinta seuraavien 2–20 päivän aikana.

---

## 4.7 Laskutrendi-suodattimet

Tulosten generoinnissa voidaan käyttää **laskutrendi-suodattimia**, jotka rajaavat tuloksia vain sellaisiin kynttilöihin, jotka esiintyvät laskutrendin aikana. Tämä on hyödyllistä erityisesti nousevien kääntymiskuvioiden (kuten Hammer) analysoinnissa.

### 4.7.1 Suodattimen parametrit

| Parametri | Oletusarvo | Kuvaus |
|-----------|-----------|--------|
| `downtrend_filter` | `False` | Jos `True`, suodatetaan vain laskutrendien kynttilät |
| `min_decline_percent` | `3.0` | Minimalasku prosentteina 10 päivän ajalta |
| `use_ma_filter` | `True` | Käytetäänkö liukuva keskiarvo -suodatinta |
| `use_volume_filter` | `False` | Käytetäänkö volyymi-suodatinta |

### 4.7.2 Laskutrendin tunnistuskriteerit

Kynttilä luokitellaan laskutrendiin kuuluvaksi, jos **kaikki** seuraavat ehdot täyttyvät:

#### 1. Peruskriteeri: Porrastava lasku
- **t₋₁₀ > t₋₅ > t₋₂ > t₀**
- Eli hinnan tulee laskea johdonmukaisesti ilman merkittäviä nousupiikkejä

#### 2. Minimalasku
- **Laskuprosentti ≥ `min_decline_percent`** (oletuksena 3%)
- Lasketaan: `((t₋₁₀ - t₀) / t₋₁₀) × 100`
- Esimerkki: Jos t₋₁₀ = 100 ja t₀ = 96, lasku = 4% ✅

#### 3. Liukuva keskiarvo -suodatin (jos `use_ma_filter = True`)
Tarkistetaan kaksi ehtoa:
- **t₀ < MA(10)** — Nykyinen hinta on alle 10 päivän liukuvan keskiarvon
- **MA(5) < MA(10)** — Lyhyempi liukuva keskiarvo on alle pidemmän (vahvistaa laskutrendin)

#### 4. Volyymi-suodatin (jos `use_volume_filter = True`)
- **Viimeisen 5 päivän keskivolyymi > historiallinen keskivolyymi (20 päivää)**
- Varmistaa, että lasku tapahtuu korkealla volyymilla (ei pelkkä hiljaisuus)
- Historiallinen volyymi lasketaan päivistä t₋₂₅ ... t₋₅

### 4.7.3 Käyttöesimerkki

Jos `downtrend_filter = True`:
- Numerokoodi **0** annetaan kynttilöille, jotka täyttävät laskutrendin kriteerit
- Muut kynttilät (jotka eivät ole laskutrendissä) suodatetaan pois tuloksista
- Tämä auttaa löytämään **kääntymissignaaleja laskutrendin pohjalta**

**Tulkinta:**
- **Hammer laskutrendissä** (koodi 1 + laskutrendi-suodatin täyttyy) = vahva ostosignaali
- **Morning Star laskutrendissä** (koodi 5) = kääntyminen nousuun todennäköisempää

---

## 4.8 Volyymit (sarakkeet 31–40)


Volyymidata sisältää sekä **historialliset** että **tulevat volyymisuhdeluvut prosentteina**.

**HUOM:** Volyymit **EI ole absoluuttisia arvoja**, vaan **prosentteja** verrattuna **100 päivän keskiarvoon** (päättyen t₋₁:een).

#### Laskentalogiikka

Kaikki volyymisarakkeet lasketaan seuraavasti:

1. **Jakson keskiarvo**: Lasketaan volyymin keskiarvo tietyllä jaksolla
2. **100 päivän vertailukeskiarvo**: Lasketaan 100 päivän volyymien keskiarvo **päättyen t₋₁:een** (ei sisällä t₀)
3. **Prosenttiluku**: Jakson keskiarvo jaetaan 100 päivän keskiarvolla ja kerrotaan 100:lla

**Tulkinta:**
- **Arvo 100** = jakson volyymi on sama kuin 100 päivän keskiarvo
- **Arvo > 100** = jakson volyymi ylittää 100 päivän keskiarvon (esim. 150 = 150%)
- **Arvo < 100** = jakson volyymi alittaa 100 päivän keskiarvon (esim. 80 = 80%)

| # | Sarake         | Merkitys                                 | Laskenta           |
|---|----------------|------------------------------------------|-------------------|
| 31| **t_2_volyymi** | Volyymisuhde t₋₂...t₋₁ jaksolla          | `mean([vol_t-2, vol_t-1]) / 100d_avg`       |
| 32| **t_5_volyymi** | Volyymisuhde t₋₅...t₋₁ jaksolla          | `mean([vol_t-5...vol_t-1]) / 100d_avg`       |
| 33| **t_10_volyymi**| Volyymisuhde t₋₁₀...t₋₁ jaksolla         | `mean([vol_t-10...vol_t-1]) / 100d_avg`      |
| 34| **t_15_volyymi**| Volyymisuhde t₋₁₅...t₋₁ jaksolla         | `mean([vol_t-15...vol_t-1]) / 100d_avg`      |
| 35| **t_20_volyymi**| Volyymisuhde t₋₂₀...t₋₁ jaksolla         | `mean([vol_t-20...vol_t-1]) / 100d_avg`      |
| 36| **t0_volyymi**  | Volyymisuhde t₀ (yksittäinen päivä)      | `vol_t0 / 100d_avg`        |
| 37| **t2_volyymi**  | Volyymisuhde t₊₁...t₊₂ jaksolla          | `mean([vol_t+1, vol_t+2]) / 100d_avg`       |
| 38| **t5_volyymi**  | Volyymisuhde t₊₁...t₊₅ jaksolla          | `mean([vol_t+1...vol_t+5]) / 100d_avg`       |
| 39| **t10_volyymi** | Volyymisuhde t₊₁...t₊₁₀ jaksolla         | `mean([vol_t+1...vol_t+10]) / 100d_avg`      |
| 40| **t20_volyymi** | Volyymisuhde t₊₁...t₊₂₀ jaksolla         | `mean([vol_t+1...vol_t+20]) / 100d_avg`      |

**HUOM:** 100 päivän keskiarvo lasketaan **aina samalla tavalla** kaikille sarakkeille: päättyen t₋₁:een, joten se ei sisällä t₀ eikä tulevia päiviä.

---

## 4.9 Liukuvat keskiarvot (sarakkeet 41–57)


Liukuvat keskiarvot (sarakkeet 41–55) lasketaan **aina t₀-päivää edeltävältä ajanjaksolta**, eikä t₀-päivää oteta mukaan.

**Laskentalogiikka (esim. t₂_5p_liukuva):**
- Ajanhetki: t₊₂ (eli 2 päivää t₀:n jälkeen)
- Keskiarvon pituus: 5 päivää
- Lasketaan: `mean([close_t-2, close_t-3, close_t-4, close_t-5, close_t-6])`
- **Normalisointi:** Jaetaan t₀ alin hinnalla ja kerrotaan 100:lla

| # | Sarake           | Merkitys                                          | Laskenta                                  |
|---|------------------|--------------------------------------------------|------------------------------------------|
| 41| **t_2_5p_liukuva** | 5 päivän liukuva keskiarvo, ajanjakso t-2...t-6           | `mean([t-2, t-3, t-4, t-5, t-6]) / t0_low × 100`        |
| 42| **t_2_10p_liukuva**| 10 päivän liukuva keskiarvo, ajanjakso t-2...t-11         | `mean([t-2, ..., t-11]) / t0_low × 100`        |
| 43| **t_2_20p_liukuva**| 20 päivän liukuva keskiarvo, ajanjakso t-2...t-21         | `mean([t-2, ..., t-21]) / t0_low × 100`       |
| 44| **t_5_5p_liukuva** | 5 päivän liukuva keskiarvo, ajanjakso t-5...t-9           | `mean([t-5, t-6, t-7, t-8, t-9]) / t0_low × 100`        |
| 45| **t_5_10p_liukuva**| 10 päivän liukuva keskiarvo, ajanjakso t-5...t-14         | `mean([t-5, ..., t-14]) / t0_low × 100`        |
| 46| **t_5_20p_liukuva**| 20 päivän liukuva keskiarvo, ajanjakso t-5...t-24         | `mean([t-5, ..., t-24]) / t0_low × 100`       |
| 47| **t_10_5p_liukuva**| 5 päivän liukuva keskiarvo, ajanjakso t-10...t-14         | `mean([t-10, t-11, t-12, t-13, t-14]) / t0_low × 100`       |
| 48| **t_10_10p_liukuva**| 10 päivän liukuva keskiarvo, ajanjakso t-10...t-19        | `mean([t-10, ..., t-19]) / t0_low × 100`       |
| 49| **t_10_20p_liukuva**| 20 päivän liukuva keskiarvo, ajanjakso t-10...t-29        | `mean([t-10, ..., t-29]) / t0_low × 100`       |
| 50| **t_15_5p_liukuva**| 5 päivän liukuva keskiarvo, ajanjakso t-15...t-19         | `mean([t-15, t-16, t-17, t-18, t-19]) / t0_low × 100`      |
| 51| **t_15_10p_liukuva**| 10 päivän liukuva keskiarvo, ajanjakso t-15...t-24        | `mean([t-15, ..., t-24]) / t0_low × 100`       |
| 52| **t_15_20p_liukuva**| 20 päivän liukuva keskiarvo, ajanjakso t-15...t-34        | `mean([t-15, ..., t-34]) / t0_low × 100`       |
| 53| **t_20_5p_liukuva**| 5 päivän liukuva keskiarvo, ajanjakso t-20...t-24         | `mean([t-20, t-21, t-22, t-23, t-24]) / t0_low × 100`      |
| 54| **t_20_10p_liukuva**| 10 päivän liukuva keskiarvo, ajanjakso t-20...t-29        | `mean([t-20, ..., t-29]) / t0_low × 100`      |
| 55| **t_20_20p_liukuva**| 20 päivän liukuva keskiarvo, ajanjakso t-20...t-39        | `mean([t-20, ..., t-39]) / t0_low × 100`       |
| 56| **t0_50p_liukuva**| 50 päivän liukuva keskiarvo, päättyen t₀           | `mean([t-49...t0]) / t0_low × 100`        |
| 57| **t0_200p_liukuva**| 200 päivän liukuva keskiarvo, päättyen t₀          | `mean([t-199...t0]) / t0_low × 100`       |

**HUOM:** 200 päivän liukuva keskiarvo lasketaan vain jos dataa on riittävästi. Jos ei ole, arvo on tyhjä (None).

---

## 4.10 S&P 500 Indeksi (sarakkeet 58–68)

Nämä sarakkeet sisältävät S&P 500 -indeksin (^GSPC) **päätösarvot** vastaavina päivinä kuin osakedata.

**HUOM:** Indeksidata **NORMALISOIDAAN** indeksin omaan t₀ päätöskurssiin (t0_close = 100). **EI normalisoida osakkeen t₀ alin hintaan.**

| # | Sarake   | Merkitys                            | Laskenta                                |
|---|----------|-------------------------------------|-----------------------------------------|
| 58| **SPX_0**| S&P 500 päätösarvo t₀-päivänä (normalisoitu) | **Aina 100** (normalisointiperusta)      |
| 59| **SPX_2**| S&P 500 päätösarvo t₋₂-päivänä (normalisoitu) | `(^GSPC close_t-2 / ^GSPC close_t0) × 100` |
| 60| **SPX_5**| S&P 500 päätösarvo t₋₅-päivänä (normalisoitu) | `(^GSPC close_t-5 / ^GSPC close_t0) × 100` |
| 61| **SPX_10**| S&P 500 päätösarvo t₋₁₀-päivänä (normalisoitu)| `(^GSPC close_t-10 / ^GSPC close_t0) × 100`|
| 62| **SPX_15**| S&P 500 päätösarvo t₋₁₅-päivänä (normalisoitu)| `(^GSPC close_t-15 / ^GSPC close_t0) × 100`|
| 63| **SPX_20**| S&P 500 päätösarvo t₋₂₀-päivänä (normalisoitu)| `(^GSPC close_t-20 / ^GSPC close_t0) × 100`|
| 64| **SPX2** | S&P 500 päätösarvo t₊₂-päivänä (normalisoitu) | `(^GSPC close_t+2 / ^GSPC close_t0) × 100` |
| 65| **SPX5** | S&P 500 päätösarvo t₊₅-päivänä (normalisoitu) | `(^GSPC close_t+5 / ^GSPC close_t0) × 100` |
| 66| **SPX10**| S&P 500 päätösarvo t₊₁₀-päivänä (normalisoitu)| `(^GSPC close_t+10 / ^GSPC close_t0) × 100`|
| 67| **SPX15**| S&P 500 päätösarvo t₊₁₅-päivänä (normalisoitu)| `(^GSPC close_t+15 / ^GSPC close_t0) × 100`|
| 68| **SPX20**| S&P 500 päätösarvo t₊₂₀-päivänä (normalisoitu)| `(^GSPC close_t+20 / ^GSPC close_t0) × 100`|

**Käyttö:** Voidaan vertailla osakkeen kehitystä markkinoihin (beta, korrelaatio). SPX_0 on aina 100, muut arvot suhteessa siihen.

---

## 4.11 Nasdaq 100 Indeksi (sarakkeet 69–79)

Nämä sarakkeet sisältävät Nasdaq 100 -indeksin (^NDX) **päätösarvot** vastaavina päivinä.

**HUOM:** Indeksidata **NORMALISOIDAAN** indeksin omaan t₀ päätöskurssiin (t0_close = 100). **EI normalisoida osakkeen t₀ alin hintaan.**

| # | Sarake   | Merkitys                            | Laskenta                                |
|---|----------|-------------------------------------|-----------------------------------------|
| 69| **NDX_0**| Nasdaq 100 päätösarvo t₀-päivänä (normalisoitu) | **Aina 100** (normalisointiperusta)      |
| 70| **NDX_2**| Nasdaq 100 päätösarvo t₋₂-päivänä (normalisoitu)| `(^NDX close_t-2 / ^NDX close_t0) × 100` |
| 71| **NDX_5**| Nasdaq 100 päätösarvo t₋₅-päivänä (normalisoitu)| `(^NDX close_t-5 / ^NDX close_t0) × 100` |
| 72| **NDX_10**| Nasdaq 100 päätösarvo t₋₁₀-päivänä (normalisoitu)| `(^NDX close_t-10 / ^NDX close_t0) × 100`|
| 73| **NDX_15**| Nasdaq 100 päätösarvo t₋₁₅-päivänä (normalisoitu)| `(^NDX close_t-15 / ^NDX close_t0) × 100`|
| 74| **NDX_20**| Nasdaq 100 päätösarvo t₋₂₀-päivänä (normalisoitu)| `(^NDX close_t-20 / ^NDX close_t0) × 100`|
| 75| **NDX2** | Nasdaq 100 päätösarvo t₊₂-päivänä (normalisoitu)| `(^NDX close_t+2 / ^NDX close_t0) × 100` |
| 76| **NDX5** | Nasdaq 100 päätösarvo t₊₅-päivänä (normalisoitu)| `(^NDX close_t+5 / ^NDX close_t0) × 100` |
| 77| **NDX10**| Nasdaq 100 päätösarvo t₊₁₀-päivänä (normalisoitu)| `(^NDX close_t+10 / ^NDX close_t0) × 100`|
| 78| **NDX15**| Nasdaq 100 päätösarvo t₊₁₅-päivänä (normalisoitu)| `(^NDX close_t+15 / ^NDX close_t0) × 100`|
| 79| **NDX20**| Nasdaq 100 päätösarvo t₊₂₀-päivänä (normalisoitu)| `(^NDX close_t+20 / ^NDX close_t0) × 100`|

---

## 4.12 RSI14_t0 (sarake 80)

**RSI** (Relative Strength Index) on momentum-indikaattori, joka mittaa hinnan muutosten nopeutta ja suuruutta. Se vaihtelee välillä **0–100**.

#### Laskentalogiikka (Wilderin menetelmä)

RSI lasketaan **14 päivän** jaksolle käyttäen **eksponentiaalista liukuvaa keskiarvoa** (EMA):

1. **Lasketaan päivittäiset muutokset (delta):**
   $$
   \Delta_i = \text{close}_i - \text{close}_{i-1}
   $$

2. **Erotellaan nousut ja laskut:**
   - Nousu (gain): $\text{gain}_i = \max(0, \Delta_i)$
   - Lasku (loss): $\text{loss}_i = \max(0, -\Delta_i)$

3. **Lasketaan eksponentiaaliset liukuvat keskiarvot:**
   - $\alpha = \frac{1}{14}$ (Wilderin suositus)
   - `avg_gain = EMA(gain, alpha=1/14, min_periods=14)`
   - `avg_loss = EMA(loss, alpha=1/14, min_periods=14)`

4. **Lasketaan suhteellinen vahvuus (RS):**
   $$
   RS = \frac{\text{avg\_gain}}{\text{avg\_loss}}
   $$

5. **Lasketaan RSI:**
   $$
   RSI = 100 - \frac{100}{1 + RS}
   $$

6. **Erikoistapaukset:**
   - Jos $\text{avg\_loss} = 0$ (ei laskuja): $RSI = 100$
   - Jos $\text{avg\_gain} = 0$ (ei nousuja): $RSI = 0$
   - Jos molemmat nolla (ei liikettä): $RSI = 50$

#### Tulkinta

| RSI-arvo | Tulkinta                              |
|----------|--------------------------------------|
| **0–30** | **Ylimyyty** — osake saattaa olla liian halpa, mahdollinen ostomahdollisuus |
| **30–50**| Neutraali, lähempänä heikkoutta      |
| **50–70**| Neutraali, lähempänä vahvuutta       |
| **70–100**| **Yliostettu** — osake saattaa olla yliarvostettu, mahdollinen myyntisignaali |

**HUOM:** RSI lasketaan t₀-päivän tietoihin perustuen, käyttäen 14 päivän historiaa.

---

## 5. Yhteenveto ja Käyttöohjeet

### 5.1 Miten tulkita Excel-tiedostoa?

1. **Tunnista kynttilä:** Katso **kynttilä**-saraketta (sarake 3) ja **vahvuus**-saraketta (sarake 4).
2. **Arvioi signaali:** Vahvuus 0.7–1.0 = vahva signaali, 0.5–0.7 = keskivahva, 0.0–0.5 = heikko.
3. **Tarkista konteksti:**
   - Katso historiallisia hintoja (t₋₂, t₋₅, ...) ja volatiliteettia (t_2_hajonta, ...)
   - Katso tulevaa kehitystä (t₂, t₅, t₁₀, t₂₀) ja arvioi, toteutuiko signaali
4. **Vertaa indekseihin:** SPX ja NDX sarakkeet kertovat markkinoiden yleisen tilanteen
5. **Tarkista RSI:** Jos RSI < 30 JA Hammer-signaali vahva → vahva ostosignaali

### 5.2 Esimerkkitulkinta

**Rivi 1:**
- **osake:** AAPL
- **kynttilä:** Hammer
- **vahvuus:** 0.85
- **t0_bodi:** 102.5 (päätöskurssi normalisoitu)
- **t5:** 107.3 (hinta nousi 7.3 % viidessä päivässä)
- **RSI14_t0:** 28 (ylimyyty)

**Tulkinta:** Vahva Hammer-signaali ylimyydyssä tilassa. Hinta nousi todella seuraavan 5 päivän aikana → signaali toimi hyvin.

---

## 6. Tekniset Huomiot

- **Normalisointi:** 
  - **Osakkeiden hinnat:** Normalisoidaan t₀ alin hintaan (t0_low = 100)
  - **Indeksit (S&P 500, Nasdaq 100):** Normalisoidaan **indeksin omaan** t₀ päätöskurssiin (t0_close = 100)
  - **Volyymit:** Ilmaistaan **suhdelukuina** verrattuna 100 päivän keskiarvoon (päättyen t₋₁)
  - **Volatiliteetit:** EI normalisoida (absoluuttiset standardipoikkeamat)
- **Volatiliteetti:** Lasketaan standardipoikkeamana (ei normalisoida).
- **Liukuvat keskiarvot:** Normalisoidaan osakkeen t₀ alin hintaan (kuten hinnat).
- **RSI:** Käytetään Wilderin eksponentiaalista menetelmää, 14 päivän jakso.
- **Indeksit:** S&P 500 ja Nasdaq 100 normalisoidaan omaan t₀-arvoonsa, jolloin vertailu osakkeen kehitykseen on helpompaa (molemmat alkavat arvosta 100).
- **Volyymisuhdeluvut:** Kaikki volyymidata on normalisoitu samaan 100 päivän keskiarvoon (päättyen t₋₁), mikä mahdollistaa volyymiaktiivisuuden vertailun eri ajanjaksoilla.

---

## 7. Yhteystiedot ja Tuki

Kysymykset dokumentaatiosta tai Excelin käytöstä:
- **Projekti:** Rawcandle
- **Versio:** 1.0
- **Päivitetty:** 25.10.2025

---

**Dokumentin loppu**
