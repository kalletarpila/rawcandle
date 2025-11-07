# Deprecated Functions

Tämä dokumentti listaa funktiot jotka on siirretty pois käytöstä.

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
