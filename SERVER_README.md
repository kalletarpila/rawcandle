# RawCandle Server Käynnistysscriptit

Tässä hakemistossa on kaksi käynnistysscriptiä RawCandle-sovellukselle:

## Linux/macOS: `start_server`

Bash-scripti joka:
- Vapauttaa portin 8888 (tappaa mahdolliset vanhat prosessit)
- Käynnistää sovelluksen virtuaaliympäristössä
- Käyttää aina kiinteää porttia 8888

### Käyttö:
```bash
./start_server
```

## Windows: `start_server.bat`

Batch-scripti joka:
- Vapauttaa portin 8888 (tappaa mahdolliset vanhat prosessit)
- Käynnistää sovelluksen virtuaaliympäristössä
- Käyttää aina kiinteää porttia 8888

### Käyttö:
```cmd
start_server.bat
```

## Sovelluksen käyttö

Kun scripti on käynnistetty, avaa selaimessa:
**http://localhost:8888**

## Vaatimukset

- Python virtuaaliympäristö hakemistossa `venv/`
- Flet ja muut riippuvuudet asennettuna virtuaaliympäristöön
- Linux/macOS: `lsof` komento porttien tarkistamiseen
- Windows: `netstat` ja `taskkill` komentojen saatavuus

## Huomioitavaa

Scriptit tapattavat automaattisesti kaikki prosessit jotka käyttävät porttia 8888 tai ajaa `main.py` tiedostoa. Tämä varmistaa että sovellus voi käynnistyä puhtaasti.

Jos haluat käyttää eri porttia, voit:
1. Muokata scriptiä
2. Tai käynnistää sovelluksen manuaalisesti: `python main.py --port <portti>`
3. Tai asettaa ympäristömuuttuja: `export FLET_PORT=<portti>`