import unittest
from unittest.mock import MagicMock, patch
from main import RawCandleApp
import flet as ft

class TestDatabaseView(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock(spec=ft.Page)
        self.page.overlay = []
        self.page.snack_bar = None
        self.app = RawCandleApp(self.page)

    def test_nayta_tietokannan_tiedot_shows_dialog(self):
        # Simulate pressing the button
        try:
            self.app.nayta_tietokannan_tiedot(None)
        except Exception as ex:
            self.fail(f"Exception raised when showing database info: {ex}")
        # Should set snack_bar or dialog
        snack = getattr(self.page, 'snack_bar', None)
        dialog = None
        if hasattr(self.page, 'overlay'):
            for item in self.page.overlay:
                if hasattr(item, 'title') and hasattr(item, 'open'):
                    dialog = item
        self.assertTrue(snack or dialog, "No output shown when pressing 'Näytä tietokannan tiedot'")

    def test_database_view_has_export_button(self):
        view = self.app.create_database_view()
        # Traverse the view hierarchy to find the export button
        found = False
        for control in view.controls:
            if isinstance(control, ft.Container):
                col = control.content
                if isinstance(col, ft.Column):
                    for row in col.controls:
                        if isinstance(row, ft.Row):
                            for btn in row.controls:
                                if isinstance(btn, ft.ElevatedButton) and "Siirrä tietokantaan" in btn.text:
                                    found = True
        self.assertTrue(found, "Export button not found in database view")

    @patch.object(RawCandleApp, 'luo_tietokanta')
    @patch.object(RawCandleApp, 'csv_tietokantaan')
    def test_on_database_export_click_success(self, mock_csv, mock_luo):
        mock_luo.return_value = '/fake/path/osakedata.db'
        self.page.snack_bar = None
        self.app.on_database_export_click(None)
        self.assertIsNotNone(self.page.snack_bar)
        self.assertIn("CSV-tiedot tallennettu", self.page.snack_bar.content.value)

    @patch.object(RawCandleApp, 'luo_tietokanta', side_effect=Exception("DB error"))
    def test_on_database_export_click_failure(self, mock_luo):
        self.page.snack_bar = None
        self.app.on_database_export_click(None)
        self.assertIsNotNone(self.page.snack_bar)
        self.assertIn("Virhe tietokannan käsittelyssä", self.page.snack_bar.content.value)

if __name__ == "__main__":
    unittest.main()
