#!/usr/bin/env python3
"""
Yksikkötesti RawCandle CSV-export toiminnallisuudelle
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Lisää main.py polku
sys.path.append('/home/kalle/projects/rawcandle')

# Mock Flet-komponentit testaamista varten
class MockPage:
    def __init__(self):
        self.overlay = []

    def update(self):
        pass

    def set_clipboard(self, text):
        print(f"CLIPBOARD: {text[:100]}...")

    def go(self, route):
        pass

    def go(self, route):
        pass

class MockTextField:
    def __init__(self, value="AAPL", **kwargs):
        self.value = value
        for k, v in kwargs.items():
            setattr(self, k, v)

    def strip(self):
        return self

    def upper(self):
        return self.value.upper()

class MockText:
    def __init__(self, value="", color=None, **kwargs):
        self.value = value
        self.color = color
        for k, v in kwargs.items():
            setattr(self, k, v)

# Korvaa Flet-komponentit testeissä
import flet as ft
ft.Page = MockPage
ft.TextField = MockTextField
ft.Text = MockText

# Varmista, että kaikki värit ovat käytössä ennen main.py:n tuontia
ft.Colors = type('Colors', (), {
    'BLUE_600': 'blue',
    'RED_600': 'red',
    'GREEN_600': 'green',
    'GREEN_700': 'darkgreen',
    'GREY_400': 'grey',
    'GREY_300': 'lightgrey',
    'GREY_100': 'verylightgrey',
    'WHITE': 'white',
    'ORANGE_300': 'orange',
    'ORANGE_700': 'darkorange',
    'GREY_50': 'superlightgrey',
    'TRANSPARENT': 'transparent',
})()

# Tuo testattava luokka
from main import RawCandleApp

class TestCSVExport(unittest.TestCase):
    """Testaa CSV-export toiminnallisuutta"""
    
    def setUp(self):
        """Asettaa testiympäristön"""
        self.mock_page = MockPage()
        self.app = RawCandleApp(self.mock_page)
        
        # Luo test-data (simuloi Yahoo Finance -dataa)
        dates = pd.date_range('2024-09-01', '2024-09-30', freq='D')
        # Simuloi vain arkipäiviä (ma-pe)
        weekdays = [d for d in dates if d.weekday() < 5]
        
        self.test_data = pd.DataFrame({
            'Open': [100 + i * 0.5 for i in range(len(weekdays))],
            'High': [105 + i * 0.5 for i in range(len(weekdays))], 
            'Low': [95 + i * 0.5 for i in range(len(weekdays))],
            'Close': [102 + i * 0.5 for i in range(len(weekdays))],
            'Volume': [1000000 + i * 10000 for i in range(len(weekdays))]
        }, index=weekdays)
        
        # Aseta test-data sovellukseen
        self.app.stock_data = self.test_data
        self.app.ticker_field.value = "AAPL"

    def test_csv_generation_with_valid_data(self):
        """Testaa CSV:n luomista kelvollisella datalla (uusi muoto: yksi rivi, ticker + data)"""
        print("\n=== Testaa CSV-luontia kelvollisella datalla (uusi muoto) ===")

        # Varmista että meillä on dataa
        self.assertIsNotNone(self.app.stock_data)
        self.assertGreater(len(self.app.stock_data), 0)

        # Simuloi download_csv_data kutsu
        class MockEvent:
            pass
        self.app.ticker_field.value = "AAPL"
        self.app.download_csv_data(MockEvent())

        # Etsi tallennettu tiedosto /tmp-hakemistosta
        import os
        filename = "AAPL_osakedata_syyskuu2024.csv"
        file_path = os.path.join("/tmp", filename)
        self.assertTrue(os.path.exists(file_path), f"CSV-tiedostoa ei löytynyt: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            csv_string = f.read()

        print(f"CSV-tiedoston sisältö: {csv_string[:200]}...")

        # Tarkista että CSV:ssä on vain yksi rivi
        lines = csv_string.strip().split('\n')
        self.assertEqual(len(lines), 1, "CSV:ssä pitää olla vain yksi rivi")

        # Tarkista että ensimmäinen sarake on ticker
        first_col = lines[0].split(',')[0]
        self.assertEqual(first_col, "AAPL", "Ensimmäisen sarakkeen pitää olla ticker")

        # Tarkista että perässä tulee oikea määrä dataa
        # (päivämäärä, open, close, high, low, volume per päivä)
        n_days = len(self.app.stock_data)
        expected_cols = 1 + n_days * 6
        actual_cols = len(lines[0].split(','))
        self.assertEqual(actual_cols, expected_cols, f"CSV:ssä pitää olla {expected_cols} saraketta, nyt {actual_cols}")

    def test_csv_export_without_data(self):
        """Testaa CSV-exportin käyttäytymistä ilman dataa"""
        print("\n=== Testaa CSV-exportia ilman dataa ===")
        
        # Poista data
        self.app.stock_data = None
        
        class MockEvent:
            pass
        
        # Testaa että funktio ei kaadu
        try:
            self.app.download_csv_data(MockEvent())
            print("CSV-export käsitteli tyhjän datan oikein")
        except Exception as e:
            self.fail(f"CSV-export kaatui tyhjällä datalla: {e}")

    def test_csv_data_validation(self):
        """Testaa CSV-datan validointia"""
        print("\n=== Testaa CSV-datan validointia ===")
        
        # Testaa puutteellisella datalla (puuttuu sarake)
        bad_data = self.test_data.copy()
        bad_data = bad_data.drop('Volume', axis=1)
        
        self.app.stock_data = bad_data
        
        try:
            df = self.app.stock_data.copy()
            df = df.select_dtypes(include=[float, int])
            csv_string = df.to_csv()
            
            print(f"Puutteellinen data käsiteltiin, CSV pituus: {len(csv_string)}")
            self.assertGreater(len(csv_string), 0)
            
        except Exception as e:
            print(f"Puutteellinen data aiheutti virheen (odotettavissa): {e}")

    def test_data_formatting(self):
        """Testaa datan formatointia"""
        print("\n=== Testaa datan formatointia ===")
        
        # Testaa että numerot formatoidaan oikein
        sample_data = self.test_data.head(3).copy()
        
        # Lisää NaN-arvoja testaamista varten
        sample_data.iloc[1, 0] = np.nan
        
        formatted_data = sample_data.round(2)
        
        print("Alkuperäinen data:")
        print(sample_data.head())
        
        print("\nFormatoitu data:")
        print(formatted_data.head())
        
        # Tarkista että round toimii
        self.assertTrue(all(formatted_data.dtypes.apply(lambda x: x in ['float64', 'int64', 'object'])))

def run_tests():
    """Ajaa kaikki testit"""
    print("🧪 Aloitetaan CSV-export testit...")
    
    # Luo test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestCSVExport)
    
    # Aja testit
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n📊 Testien tulokset:")
    print(f"✅ Onnistuneet: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ Epäonnistuneet: {len(result.failures)}")
    print(f"🚫 Virheet: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ Epäonnistuneet testit:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\n🚫 Virheet:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)