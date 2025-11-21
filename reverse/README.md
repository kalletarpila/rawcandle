# Reverse Module

`reverse/` sisältää RawCandle-sovelluksen reverse-engineering analytiikan.

Pääkomponentit:

- `view.py`: Flet-pohjainen käyttöliittymä, joka kokoaa dashboardin parametreilla,
  lokilla, tauluilla ja kuvaajilla.
- `controller.py`: Orkestraattori, joka hoitaa analyysin ajon, raporttien viennin
  sekä progressi-/lokipalautteet.
- `analysis.py`: Varsinaiset data-analyysifunktiot (universe-valinta, top-N
  filtteröinti, feature-vertailu, klusterointi).
- `reporting.py`: Tulosten tallennus CSV/Markdown -raportteihin sekä kuvatiedostot
  `data/reverse/`-hakemistoon.
- `plots.py`: Matplotlib-pohjaiset visualisoinnit UI:lle ja raportteihin.
- `queries.py`: SQL-lauseiden generointi ja turvallinen suoritus
  `results_data`-taulua vasten.
- `schema.py`: Feature-listat ja validointiapurit.
- `utils.py`: Yleiskäyttöiset helperit (timestampit, hakemistot, logging-helperit).

Kaikki reverse-komponentit ja niiden väliaikaiset tuotokset pysyvät omassa
hakemistorakenteessaan. Raportit ja muut tuotokset löytyvät `data/reverse/`
polusta. Testit reverse-moduulille löytyvät `tests/test_reverse_module.py`.
