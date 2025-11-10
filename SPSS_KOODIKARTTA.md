# Kynttilä-pattern koodikartta SPSS:ää varten

## Kynttilä-sarakkeen numerokoodit

Excel-tiedoston sarake **"kynttila"** (sarake 3) sisältää numerokoodin:

| Koodi | Kynttilän nimi           | Tyyppi       |
|-------|--------------------------|--------------|
| 0     | downtrend                | Indikaattori |
| 1     | Hammer                   | Nouseva      |
| 2     | Bullish Engulfing        | Nouseva      |
| 3     | Piercing Pattern         | Nouseva      |
| 4     | Three White Soldiers     | Nouseva      |
| 5     | Morning Star             | Nouseva      |
| 6     | Dragonfly Doji           | Neutraali    |
| 7     | Bullish Divergence       | Indikaattori |
| 8     | Bearish Divergence       | Indikaattori |

## SPSS Value Labels

Kopioi nämä SPSS:ään määrittääksesi arvonimikkeet (Value Labels):

```spss
VALUE LABELS kynttila
  0 'downtrend'
  1 'Hammer'
  2 'Bullish Engulfing'
  3 'Piercing Pattern'
  4 'Three White Soldiers'
  5 'Morning Star'
  6 'Dragonfly Doji'
  7 'Bullish Divergence'
  8 'Bearish Divergence'.
```

## Muuttujatyypit

- **kynttila**: Numeerinen (Numeric), Scale/Nominal
- Kaikki muut REAL-sarakkeet: Numeerinen (Numeric), Scale
- **weekday**: Numeerinen (Numeric), Ordinal (1=maanantai, ..., 5=perjantai)
- **_colour sarakkeet**: Numeerinen (Numeric), Nominal (0=punainen, 1=vihreä)

## Huomioita

1. Kaikki numeeriset arvot ovat pyöristetty 2 desimaaliin
2. `kynttila`-sarake on numeerinen, jolloin SPSS voi tehdä:
   - Frekvenssitaulukot
   - Ristiintaulukoinnit
   - Keskiarvot patterneittain (jos järkevää)
3. Värikoodi-sarakkeet (t_1_bodi_colour, t0_bodi_colour, t1_bodi_colour):
   - 0 = Punainen kynttilä (close < open)
   - 1 = Vihreä kynttilä (close > open)
