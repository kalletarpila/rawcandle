# RawCandle Analysis Tests

Kattavat testit analysis-sivun toiminnoille.

## 📋 Testien Rakenne

```
tests/
├── __init__.py              # Test package
├── conftest.py             # Pytest konfiguraatio ja fixturet
├── test_database_manager.py # Yksikkötestit DatabaseManager
├── test_analyzer.py        # Yksikkötestit AnalysisEngine  
├── test_analysis_view.py   # Yksikkötestit AnalysisView
├── test_integration.py     # Integraatiotestit
└── test_performance.py     # Suorituskykytestit
```

## 🚀 Testien Ajaminen

### Nopea käynnistys
```bash
# Asenna riippuvuudet
pip install -r test-requirements.txt

# Aja kaikki testit
./run_tests.sh all

# Tai vain nopeat testit
./run_tests.sh quick
```

### Yksittäiset testiryhmät
```bash
# Yksikkötestit
./run_tests.sh unit

# Integraatiotestit  
./run_tests.sh integration

# Suorituskykytestit
./run_tests.sh performance

# Koodin laadun tarkistus
./run_tests.sh lint
```

### Pytest suoraan
```bash
# Kaikki testit
pytest tests/ -v

# Tietty testiluokka
pytest tests/test_database_manager.py::TestDatabaseManager -v

# Testit merkinnän mukaan
pytest -m "not slow" -v

# Testikattavuus
pytest tests/ --cov=analysis --cov-report=html
```

## 📊 Testikategoriat

### Unit Tests (Yksikkötestit)
- **TestDatabaseManager**: Tietokantaoperaatiot
  - Yhteyksien hallinta
  - CRUD operaatiot
  - Virheenkäsittely
  - SQL injection suojaus
  
- **TestAnalysisEngine**: Analyysimoottorin logiikka
  - Kynttiläkuvioiden tunnistus
  - Batch-analyysi
  - Suorituskyvyn mittaus
  - Datan validointi
  
- **TestAnalysisView**: Käyttöliittymä
  - UI komponenttien luonti
  - Datan suodatus ja haku
  - Progress dialogi
  - Responsiivinen suunnittelu

### Integration Tests (Integraatiotestit)
- **TestAnalysisIntegration**: Komponenttien yhteistoiminta
  - Täydellinen analyysiworkflow
  - Database ↔ View integraatio
  - Virhetilanteien eteneminen
  - Samanaikainen käyttö
  - Datan johdonmukaisuus

### Performance Tests (Suorituskykytestit)
- **TestAnalysisPerformance**: Suorituskyvyn mittaus
  - Analyysin nopeus
  - Muistin käyttö
  - Samanaikaiset operaatiot
  - Suurten datasetien käsittely
  - Stressitestit

## 🎯 Testityypit

### Merkinnät (Markers)
```python
@pytest.mark.unit          # Yksikkötesti
@pytest.mark.integration   # Integraatiotesti  
@pytest.mark.slow          # Hidas testi
@pytest.mark.database      # Vaatii tietokannan
@pytest.mark.ui            # UI-testi
```

### Fixturet
- `temp_db`: Väliaikainen analysis.db
- `temp_osakedata_db`: Väliaikainen osakedata.db
- `sample_analysis_data`: Valmis testidata
- `MockPage`: Mock Flet Page objekti
- `MockProgressDialog`: Mock progress dialog

## 📈 Testikattavuus

Tavoitteena on saavuttaa:
- **Yksikkötestit**: >90% kattavuus
- **Integraatiotestit**: Kaikki pääskenaariot
- **Suorituskykytestit**: Kriittiset pullonkaulat

### Kattavuusraportti
```bash
# Generoi HTML raportti
pytest tests/ --cov=analysis --cov-report=html:reports/coverage

# Avaa selaimessa
open reports/coverage/index.html
```

## 🔧 Mock ja Fixtures

### DatabaseManager Mock
```python
@patch('analysis.view.DatabaseManager')
def test_with_mock_db(mock_db_manager):
    mock_db_manager.return_value.get_all_findings.return_value = []
    # Testi logiikka...
```

### Testidata
```python
def test_with_sample_data(sample_analysis_data):
    # sample_analysis_data sisältää valmiita löydöksiä
    assert len(sample_analysis_data) == 2
```

## 🐛 Debugging

### Verbose output
```bash
pytest tests/ -v -s  # -s näyttää print lauseet
```

### Tietty testi
```bash
pytest tests/test_database_manager.py::TestDatabaseManager::test_get_all_findings_with_data -v -s
```

### Pysäytä ensimmäisessä virheessä
```bash
pytest tests/ -x
```

### Debug mode
```bash
pytest tests/ --pdb  # Avaa debugger virheessä
```

## 📋 Testien Ylläpito

### Uuden testin lisääminen
1. Luo testifunktio `test_` etuliitteellä
2. Käytä sopivia fixtureja
3. Lisää merkinnät (@pytest.mark.xxx)
4. Dokumentoi testi selkeästi

### Testitietokantojen hallinta
Testit käyttävät väliaikaisia tietokantoja jotka:
- Luodaan automaattisesti
- Siivotaan testien jälkeen
- Ovat eristettyjä toisistaan

### Continuous Integration
Testit voidaan integroida CI/CD pipeline:aan:
```yaml
# GitHub Actions esimerkki
- name: Run tests
  run: |
    pip install -r test-requirements.txt
    ./run_tests.sh all
```

## 🔍 Testitulokset

### Raportit generoituvat:
- `reports/all_tests.html` - HTML testiraportti
- `reports/coverage_all/index.html` - Kattavuusraportti  
- `reports/junit.xml` - JUnit XML (CI/CD)
- `reports/benchmark.html` - Suorituskykyraportti

### Tulkinta
- ✅ **PASSED**: Testi onnistui
- ❌ **FAILED**: Testi epäonnistui
- ⚠️ **SKIPPED**: Testi ohitettiin
- 🐌 **SLOW**: Hidas testi (>1s)

## 🔧 Vianmääritys

### Yleiset ongelmat
1. **ModuleNotFoundError**: Tarkista PYTHONPATH
2. **Database locked**: Sulje aiemmat yhteydet
3. **Permission denied**: Tarkista tiedosto-oikeudet
4. **Mock virheet**: Tarkista patch polut

### Testien nollaus
```bash
# Poista väliaikaiset tiedostot
rm -rf reports/ .pytest_cache/ .coverage
```

## 🎯 Testien Tavoitteet

1. **Luotettavuus**: Kaikki toiminnot testattu
2. **Suorituskyky**: Ei pullonkauloja
3. **Vikasietoisuus**: Virhetilanteet hallittu
4. **Ylläpidettävyys**: Selkeä testirakenne
5. **Dokumentaatio**: Testit dokumentoivat koodia