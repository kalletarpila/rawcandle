# Downtrend Event Generator

## Yleiskuvaus

Downtrend-generaattori luo realistisia analyysitapahtumia etsimällä oikean osakedatan joukosta laskutrendipäiviä ja tallentamalla ne analysis-tietokantaan. Toisin kuin tavallinen satunnaisdatageneraattori, tämä käyttää todellista osakehistoriadataa ja etsii päiviä, jotka täyttävät määritellyt laskutrendikriteerit.

## Toimintaperiaate

### 1. Tietokannat

**Lähdekanta**: `data/osakedata.db`
- Taulu: `osakedata`
- Sarakkeet:
  - `osake` (TEXT) - Osakkeen tunniste (ticker)
  - `pvm` (TEXT) - Päivämäärä (YYYY-MM-DD)
  - `open` (REAL) - Avauskurssi
  - `high` (REAL) - Päivän ylin
  - `low` (REAL) - Päivän alin
  - `close` (REAL) - Päätöskurssi
  - `volume` (INTEGER) - Vaihdettu määrä

**Kohdekanta**: `analysis/analysis.db`
- Taulu: `analysis_findings`
- Tallennetaan löydetyt laskutrenditapahtumat

### 2. Generointiprosessi

Kun käyttäjä käynnistää generoinnin Candles-näkymästä:

1. **Osakkeen valinta**
   - Valitaan satunnaisesti osake osakedata-kannasta
   - SQL: `SELECT DISTINCT osake FROM osakedata WHERE pvm >= '2024-01-01' ORDER BY RANDOM() LIMIT 1`

2. **Päivän etsintä** (per osake, max 500 yritystä)
   - Valitaan satunnainen päivä (t0) osakkeen historiasta
   - Päivän on oltava >= 1.1.2024 (varmistaa että t-10 data on olemassa)
   - Haetaan 11 päivän hintadata: [t-10, t-9, ..., t-1, t0]

3. **Laskutrendikriteerien tarkistus** (kaikki kolme pakollisia)
   
   **Kriteeri 1: Porrastava lasku (aidosti laskeva)**
   ```
   close(t-10) > close(t-5) > close(t-2) > close(t0)
   ```
   Jokaisen tarkistuspisteen on oltava edellistä pienempi.
   
   **Kriteeri 2: Minimalasku 3%**
   ```
   lasku_% = ((close(t-10) - close(t0)) / close(t-10)) * 100
   lasku_% >= 3.0
   ```
   
   **Kriteeri 3: Liukuvien keskiarvojen suodatin**
   ```
   MA5 = keskiarvo([close(t-5), close(t-4), close(t-3), close(t-2), close(t-1)])
   MA10 = keskiarvo([close(t-10), close(t-9), ..., close(t-2), close(t-1)])
   
   Ehdot (molemmat pakollisia):
   - close(t0) < MA10
   - MA5 < MA10
   ```
   
   Huom: Liukuvat keskiarvot EI sisällä t0-päivää.

4. **Tallennus analysis-kantaan**
   
   Jos kaikki kriteerit täyttyvät, tallennetaan rivi:
   ```
   ticker          = osakkeen ticker
   date            = t0 päivämäärä
   pattern         = "downtrend"
   signal_strength = 1.0
   rsi14           = RSI(14) laskettuna t0-päivälle (vaatii vähintään 14 päivää historiaa)
   price           = close(t0)
   volume          = volume(t0)
   description     = "Auto-generated downtrend event"
   open_price      = open(t0)
   close_price     = close(t0)
   high_price      = high(t0)
   low_price       = low(t0)
   analysis_date   = nykyinen aikaleima
   ```

5. **Toisto**
   - Etsitään osakkeelle `events_per_ticker` tapahtumaa
   - Jos 500 yrityksen jälkeen ei löydy tarpeeksi, jatketaan seuraavaan osakkeeseen
   - Prosessoidaan yhteensä `num_tickers` osaketta
   - Generoinnin lopuksi täydennetään automaattisesti myös aiemmat laskutrendit, joilta puuttuu RSI14-arvo (mikäli historiadataa on riittävästi)

### 3. Käyttöliittymä

**Sijainti**: Candles-näkymä

**Kontrollit**:
- ☑️ "Tee random tapahtumia" -valintaruutu
- 🔢 "Anna osakkeiden lkm" (1-1000)
- 🔢 "Anna tapahtumien lkm per osake" (1-200)
- 🔘 "Generate" -painike

**Toiminta**:
1. Käyttäjä klikkaa "Generate"
2. Näytetään vahvistus-dialogi
3. Käyttäjä vahvistaa
4. Aukeaa progress-dialogi:
   - Progress bar: "Käsitelty X / Y osaketta"
   - "Keskeytä"-painike
5. Generointi tapahtuu taustasäikeessä
6. Valmistuttua dialogi sulkeutuu ja näytetään yhteenveto

**Keskeytys**:
- Käyttäjä voi keskeyttää generoinnin milloin vain
- Jo tallennetut tapahtumat jäävät kantaan

## Tekninen toteutus

### Moduuli: `analysis/downtrend_generator.py`

**Pääluokka**: `DowntrendGenerator`

**Julkinen funktio**:
```python
generate_random_findings(
    num_tickers: int = 100,
    events_per_ticker: int = 20,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    stock_db_path: str = "data/osakedata.db",
    analysis_db_path: str = "analysis/analysis.db"
) -> Tuple[int, List[str]]
```

**Paluuarvo**:
- `int`: Tallennettujen tapahtumien määrä
- `List[str]`: Lista virheviestejä (tyhjä jos ei virheitä)

**Callback-funktiot**:
- `progress_callback(current: int, total: int)`: Kutsutaan joka osakkeen jälkeen
- `cancel_check() -> bool`: Palauttaa True jos käyttäjä haluaa keskeyttää

### Yksityiset metodit

- `_get_stock_connection()`: Yhteys osakedata-kantaan
- `_get_analysis_connection()`: Yhteys analysis-kantaan
- `_select_random_ticker()`: Valitsee satunnaisen osakkeen
- `_get_ticker_dates()`: Hakee osakkeen kaikki päivämäärät
- `_get_price_data()`: Hakee hintadatan 11 päivälle
- `_check_downtrend_criteria()`: Tarkistaa kaikki kolme kriteeriä
- `_save_to_analysis()`: Tallentaa tapahtuman analysis-kantaan

## Virhetilanteet

Generaattori käsittelee ja raportoi seuraavat virheet:

1. **Tietokantayhteys epäonnistuu**
   - Virhe: "Database connection failed: [syy]"
   - Toimenpide: Lopettaa suorituksen

2. **Osakkeen valinta epäonnistuu**
   - Virhe: "Failed to select ticker N"
   - Toimenpide: Jatkaa seuraavaan

3. **Osakkeella ei tarpeeksi dataa**
   - Virhe: "Ticker [ticker]: insufficient data (< 11 days)"
   - Toimenpide: Jatkaa seuraavaan osakkeeseen

4. **Laskutrendipäiviä ei löydy**
   - Info-loki: "Ticker [ticker]: found only X/Y events after 500 attempts"
   - Toimenpide: Tallentaa mitä löytyi, jatkaa seuraavaan

5. **Tallennus epäonnistuu**
   - Virhe: "Failed to save to analysis: [syy]"
   - Toimenpide: Jatkaa seuraavaan tapahtumaan

## Esimerkkikäyttö

### Perus käyttö
```python
from analysis.downtrend_generator import generate_random_findings

# Generoi 50 osakkeelle 10 tapahtumaa per osake
total, errors = generate_random_findings(
    num_tickers=50,
    events_per_ticker=10
)

print(f"Tallennettu {total} tapahtumaa")
if errors:
    print("Virheet:", errors)
```

### Progress-seurannan kanssa
```python
def progress_update(current, total):
    print(f"Käsitelty {current}/{total} osaketta")

def check_cancelled():
    # Palauta True jos käyttäjä on keskeyttänyt
    return False

total, errors = generate_random_findings(
    num_tickers=100,
    events_per_ticker=20,
    progress_callback=progress_update,
    cancel_check=check_cancelled
)
```

## Suorituskyky

- **Yritykset per osake**: Max 500 satunnaista päivää
- **Keskimääräinen nopeus**: ~10-50 osaketta/sekunti (riippuu kannasta)
- **Muistin käyttö**: Minimaalinen (käsittelee yhden osakkeen kerrallaan)
- **Tietokantakuorma**: Kevyt (indeksoidut kyselyt, batch-tallennus)

## Rajoitukset

1. **Päivämääräväli**: Vain päivät >= 1.1.2024 (varmistaa t-10 datan)
2. **Max yritykset**: 500 per osake (estää ikuiset luupit)
3. **Tiukat kriteerit**: Kaikki kolme kriteeriä pakollisia (löytää vain vahvat laskunetrendit)
4. **Ei duplikaattien tarkistusta**: Sama päivä voidaan tallentaa useaan kertaan

## Ylläpito

### Testaus
Testit sijaitsevat: `tests/test_downtrend_generator.py`

### Lokitus
Generaattori käyttää Python logging -moduulia:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

### Debuggaus
Lisää debug-lokitusta muuttamalla:
```python
logger.setLevel(logging.DEBUG)
```

## Muutoshistoria

**v1.0** (2025-10-23)
- Ensimmäinen versio
- Tukee kolmen kriteerin laskutrendin tunnistusta
- Progress-seuranta ja keskeytysmahdollisuus
- Virheenkäsittely ja raportointi
