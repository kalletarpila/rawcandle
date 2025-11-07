# Deprecated Functions

Tämä dokumentti listaa funktiot ja koodit jotka on siirretty pois käytöstä.

## analysis/print_results.py

### Poistettu toiminnallisuus (2024-11-07):

- **`.txt` ja `.csv` tiedostojen generointi** 
  - Poistettu rivit 103-136 (tiedostokirjoitus)
  - Säilytetty: analysis.log kirjoitus ja tietokantatallennus
  - Tulokset tallentuvat nyt vain analysis.db:hen ja analysis.log:iin
  - UI voi lukea tulokset suoraan tietokannasta

## candles/ (koko hakemisto)

### Siirretty kokonaan deprecated/-hakemistoon (2024-11-07):

**Syy:** Ei käytetty missään, korvattu `analysis/candlestick_patterns.py`:llä

- **`candles/patterns.py`** - Vanha pattern-tunnistus
  - 6 funktiota: is_hammer, is_bullish_engulfing, is_piercing_pattern, is_three_white_soldiers, is_morning_star, is_dragonfly_doji
  - Pandas Series -pohjainen toteutus
  - Korvattu modernilla row-based toteutuksella `analysis/candlestick_patterns.py`:ssä
  
- **`candles/results.py`** - Tyhjä tiedosto, ei sisältöä

- **`candles/utils.py`** - Tyhjä tiedosto, ei sisältöä

- **`candles/__init__.py`** - Tyhjä __init__

**Vaikutus:** Ei mitään, koska ei yhtään importtia koko projektissa

## results/generate_results.py

### Poistetut funktiot (2024-11-07):

1. **`_calculate_relative_stdev()`** - Ei käytetty missään
   - Laski suhteellisen standardipoikkeaman
   
2. **`_format_finnish_number()`** - Duplikaatti
   - Sama funktio löytyy `excel_cache.py`:stä
   - Ei käytetty `generate_results.py`:ssä

3. **`paivita_results_csv()`** - Vanha CSV-generointi
   - Käytetty vain sisäisesti, ei UI:ssa
   - Korvattu `ExcelResultsCache`:lla

4. **`paivita_results_csv_click()`** - Vanha event handler
   - Ei käytetty UI:ssa
   - Korvattu `view.py`:n uudella implementaatiolla

## results/divergence_cache.py

### Siirretty kokonaan deprecated/-hakemistoon (2024-11-07):

- **`DivergenceCache` luokka** - Ei käytössä tuotannossa
  - Divergenssit haetaan suoraan `analysis.db`:stä
  - Käytetään vain testeissä
  - Testi päivitetty käyttämään deprecated-versiota
