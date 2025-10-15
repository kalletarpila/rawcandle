import flet as ft
import yfinance as yf
import datetime
import pandas as pd
import io
import base64

class RawCandleApp:
    def fetch_and_save_from_file(self, e):
        import os
        tickers_file = os.path.join(os.path.dirname(__file__), "tickers.txt")
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        file_path = os.path.join(data_dir, "osakedata.csv")
        if not os.path.exists(tickers_file):
            self.loading_text.value = f"❌ Tiedostoa ei löytynyt: {tickers_file}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        try:
            with open(tickers_file, 'r', encoding='utf-8') as f:
                tickers = [line.strip() for line in f if line.strip()]
            if not tickers:
                self.loading_text.value = "❌ Tiedostossa ei ole tickereitä!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return
            results = []
            for ticker in tickers:
                self.loading_text.value = f"🔄 Haetaan dataa: {ticker}..."
                self.loading_text.color = ft.Colors.BLUE_600
                self.page.update()
                try:
                    stock = yf.Ticker(ticker)
                    start_date = "2023-07-01"
                    end_date = "2025-09-30"
                    hist = stock.history(start=start_date, end=end_date)
                    if hist.empty:
                        msg = f"{ticker}: Ei dataa"
                        self.loading_text.value = msg
                        self.loading_text.color = ft.Colors.RED_600
                        self.page.update()
                        results.append(msg)
                        continue
                    df = hist.copy().sort_index(ascending=False)
                    df.index = df.index.strftime('%Y-%m-%d')
                    row_data = [ticker]
                    for date, row in df.iterrows():
                        date_str = date
                        open_val = f"{row['Open']:.2f}" if 'Open' in row and pd.notna(row['Open']) else ""
                        close_val = f"{row['Close']:.2f}" if 'Close' in row and pd.notna(row['Close']) else ""
                        high_val = f"{row['High']:.2f}" if 'High' in row and pd.notna(row['High']) else ""
                        low_val = f"{row['Low']:.2f}" if 'Low' in row and pd.notna(row['Low']) else ""
                        volume_val = f"{int(row['Volume'])}" if 'Volume' in row and pd.notna(row['Volume']) else ""
                        row_data.extend([date_str, open_val, close_val, high_val, low_val, volume_val])
                    csv_string = ','.join(row_data) + '\n'
                    try:
                        with open(file_path, 'a', encoding='utf-8') as f:
                            f.write(csv_string)
                        msg = f"{ticker}: OK ({len(df)} päivää) - Tallennus OK"
                        self.loading_text.value = msg
                        self.loading_text.color = ft.Colors.GREEN_600
                        self.page.update()
                        results.append(msg)
                    except Exception as write_ex:
                        msg = f"{ticker}: OK ({len(df)} päivää) - Tallennus VIRHE: {str(write_ex)}"
                        self.loading_text.value = msg
                        self.loading_text.color = ft.Colors.RED_600
                        self.page.update()
                        results.append(msg)
                except Exception as ex:
                    msg = f"{ticker}: Virhe ({str(ex)})"
                    self.loading_text.value = msg
                    self.loading_text.color = ft.Colors.RED_600
                    self.page.update()
                    results.append(msg)
            self.loading_text.value = "\n".join(results)
            self.loading_text.color = ft.Colors.GREEN_600
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe tiedostoa käsitellessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
        self.page.update()
    def __init__(self, page: ft.Page):
        self.page = page
        self.setup_page()
        self.setup_routing()
        
        # Osakedata-komponentit
        self.ticker_field = ft.TextField(
            label="Osakkeen ticker (esim. AAPL, TSLA)", 
            width=300,
            hint_text="Kirjoita osakkeen symboli",
            on_submit=self.fetch_stock_data
        )
        self.loading_text = ft.Text(value="", color=ft.Colors.BLUE_600)
        self.stock_data = None
        self.download_button = None
        # FilePicker CSV-tiedoston tallennukseen
        self.file_picker = ft.FilePicker(on_result=self.save_csv_to_path)
        self.page.overlay.append(self.file_picker)
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Päivä", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Open", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("High", weight=ft.FontWeight.BOLD)), 
                ft.DataColumn(ft.Text("Low", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Close", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Volume", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Kynttilä", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=8,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
        )
        
        # Aloita etusivulta
        self.page.go("/")

    def setup_page(self):
        """Asettaa sivun perusasetukset"""
        self.page.title = "RawCandle - Flet Web App"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 800
        self.page.window_height = 600
        
    def setup_routing(self):
        """Asettaa reitityksen"""
        self.page.on_route_change = self.route_change
        
    def create_appbar(self):
        """Luo yläpalkin navigaatiolla"""
        return ft.AppBar(
            leading=ft.Icon(ft.Icons.WHATSHOT),
            leading_width=40,
            title=ft.Text("RawCandle", size=20, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.Colors.ORANGE_300,
            actions=[
                ft.IconButton(
                    ft.Icons.HOME,
                    tooltip="Home",
                    on_click=lambda _: self.page.go("/")
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS,
                    tooltip="Settings", 
                    on_click=lambda _: self.page.go("/settings")
                ),
            ],
        )

    def create_home_view(self):
        """Luo etusivun näkymän"""
        return ft.View(
            "/",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "🌕 Welcome to RawCandle!",
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700
                            ),
                            ft.Text(
                                "A modern Flet web application",
                                size=16,
                                color=ft.Colors.GREY_600
                            ),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.Text("📈 Yahoo Finance Data", size=20, weight=ft.FontWeight.BOLD),
                                        ft.Text("Hae osakkeen tiedot syyskuulta 2024", size=14, color=ft.Colors.GREY_600),
                                        ft.Row([
                                            self.ticker_field,
                                            ft.ElevatedButton(
                                                "Hae Data",
                                                icon=ft.Icons.DOWNLOAD,
                                                on_click=self.fetch_stock_data
                                            ),
                                        ], alignment=ft.MainAxisAlignment.CENTER),
                                        self.loading_text,
                                        ft.Row([
                                            ft.ElevatedButton(
                                                "Näytä Tiedot",
                                                icon=ft.Icons.TABLE_VIEW,
                                                on_click=self.show_stock_data,
                                                disabled=False
                                            ),
                                            ft.ElevatedButton(
                                                "Talleta Tiedot",
                                                icon=ft.Icons.SAVE_ALT,
                                                on_click=self.download_csv_data,
                                                disabled=False
                                            ),
                                            ft.ElevatedButton(
                                                "Hae ja tallenna tiedot tiedostosta",
                                                icon=ft.Icons.FILE_DOWNLOAD,
                                                on_click=self.fetch_and_save_from_file,
                                                disabled=False
                                            ),
                                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                                    padding=20,
                                ),
                                elevation=3,
                            ),
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column([
                                        ft.Text("📊 Osakedata", size=18, weight=ft.FontWeight.BOLD),
                                        ft.Container(
                                            content=ft.Column([
                                                self.data_table,
                                            ], scroll=ft.ScrollMode.AUTO),
                                            height=400,
                                            width=950,
                                            bgcolor=ft.Colors.GREY_50,
                                            padding=10,
                                            border_radius=8,
                                        ),
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                    padding=20,
                                ),
                                elevation=3,
                            ),
                            ft.Container(height=20),
                            ft.ElevatedButton(
                                "Back to Home",
                                icon=ft.Icons.HOME,
                                on_click=lambda _: self.page.go("/")
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
                    ),
                    padding=40,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def route_change(self, route):
        """Käsittelee reitityksen muutokset"""
        self.page.views.clear()
        
        # Lisää näkymä reitin perusteella
        if self.page.route == "/" or self.page.route == "/home":
            self.page.views.append(self.create_home_view())
        elif self.page.route == "/settings":
            self.page.views.append(self.create_settings_view())
        else:
            # 404 - palaa etusivulle
            self.page.go("/")
            
        self.page.update()

    def toggle_theme(self, e):
        """Vaihtaa teeman tumman ja vaalean välillä"""
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.update()

    def fetch_stock_data(self, e):
        """Hakee osakedata Yahoo Financesta syyskuulta"""
        ticker = self.ticker_field.value.strip().upper()
        
        if not ticker:
            self.loading_text.value = "❌ Syötä osakkeen ticker!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return
            
        self.loading_text.value = f"🔄 Haetaan dataa tickerille {ticker}..."
        self.loading_text.color = ft.Colors.BLUE_600
        self.page.update()
        
        try:
            stock = yf.Ticker(ticker)
            start_date = "2023-07-01"
            end_date = "2025-09-30"
            
            # Hae historiallinen data
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                self.loading_text.value = f"❌ Ei dataa löytynyt tickerille {ticker} syyskuulta 2024"
                self.loading_text.color = ft.Colors.RED_600
                self.stock_data = None
            else:
                self.stock_data = hist
                self.loading_text.value = f"✅ Data haettu onnistuneesti! ({len(hist)} päivää)"
                self.loading_text.color = ft.Colors.GREEN_600
                
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe dataa hakiessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.stock_data = None
            
        self.page.update()

    def download_csv_data(self, e):
        """Tallentaa osakedata CSV-tiedostona"""
        if self.stock_data is None:
            self.loading_text.value = "❌ Ei dataa tallennettavaksi. Hae ensin data!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        # Muodosta CSV-data
        df = self.stock_data.copy().sort_index(ascending=False)
        df.index = df.index.strftime('%Y-%m-%d')
        ticker = self.ticker_field.value.strip().upper()
        row_data = [ticker]
        for date, row in df.iterrows():
            date_str = date
            open_val = f"{row['Open']:.2f}" if 'Open' in row and pd.notna(row['Open']) else ""
            close_val = f"{row['Close']:.2f}" if 'Close' in row and pd.notna(row['Close']) else ""
            high_val = f"{row['High']:.2f}" if 'High' in row and pd.notna(row['High']) else ""
            low_val = f"{row['Low']:.2f}" if 'Low' in row and pd.notna(row['Low']) else ""
            volume_val = f"{int(row['Volume'])}" if 'Volume' in row and pd.notna(row['Volume']) else ""
            row_data.extend([date_str, open_val, close_val, high_val, low_val, volume_val])
        csv_string = ','.join(row_data) + '\n'

        # Luo datauri-linkki CSV-tiedostolle
        import urllib.parse
        filename = f"{ticker}_osakedata_syyskuu2024.csv"
        csv_b64 = urllib.parse.quote(csv_string)
        # Tallennetaan CSV-tiedosto data-hakemistoon, tiedoston nimi aina 'osakedata.csv'
        import os
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        file_path = os.path.join(data_dir, "osakedata.csv")
        try:
            # Lisää uusi rivi tiedoston loppuun
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(csv_string)
            save_msg = f"✅ Rivi lisätty tiedostoon: {file_path}"
            save_color = ft.Colors.GREEN_600
        except Exception as ex:
            save_msg = f"❌ Virhe tallennuksessa: {str(ex)}"
            save_color = ft.Colors.RED_600

        # Näytä CSV-esikatselu ja Kopioi CSV -painike
        csv_preview = csv_string[:500] + "..." if len(csv_string) > 500 else csv_string

        def copy_to_clipboard(e):
            self.page.set_clipboard(csv_string)
            copy_button.text = "✅ Kopioitu!"
            self.page.update()

        copy_button = ft.TextButton("📋 Kopioi CSV", on_click=copy_to_clipboard)

        dialog = ft.AlertDialog(
            title=ft.Text(f"📊 CSV-data valmis: {filename}"),
            content=ft.Column([
                ft.Text(save_msg, color=save_color),
                ft.Text("CSV-data on valmis. Voit kopioida sen leikepöydälle ja liittää esim. Exceliin:"),
                ft.Container(
                    content=ft.Text(
                        csv_preview,
                        size=10,
                        selectable=True
                    ),
                    bgcolor=ft.Colors.GREY_100,
                    padding=10,
                    border_radius=5,
                    height=200,
                    width=500,
                ),
                ft.Text(f"Yksi rivi, {len(df)} päivää dataa", size=12, italic=True),
            ], tight=True, scroll=ft.ScrollMode.AUTO),
            actions=[
                copy_button,
                ft.TextButton("Sulje", on_click=lambda _: self.close_dialog(dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.loading_text.value = save_msg
        self.loading_text.color = save_color
        self.page.update()

    def close_dialog(self, dialog):
        dialog.open = False
        self.page.update()

    def save_csv_to_path(self, e: ft.FilePickerResultEvent):
        """Tallentaa CSV-tiedoston käyttäjän valitsemaan polkuun"""
        if not e.path or self.stock_data is None:
            self.loading_text.value = "❌ Tallennus peruttu tai ei dataa!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        try:
            df = self.stock_data.copy().sort_index(ascending=False)
            df.index = df.index.strftime('%Y-%m-%d')
            ticker = self.ticker_field.value.strip().upper()
            row_data = [ticker]
            for date, row in df.iterrows():
                date_str = date
                open_val = f"{row['Open']:.2f}" if 'Open' in row and pd.notna(row['Open']) else ""
                close_val = f"{row['Close']:.2f}" if 'Close' in row and pd.notna(row['Close']) else ""
                high_val = f"{row['High']:.2f}" if 'High' in row and pd.notna(row['High']) else ""
                low_val = f"{row['Low']:.2f}" if 'Low' in row and pd.notna(row['Low']) else ""
                volume_val = f"{int(row['Volume'])}" if 'Volume' in row and pd.notna(row['Volume']) else ""
                row_data.extend([date_str, open_val, close_val, high_val, low_val, volume_val])
            csv_string = ','.join(row_data) + '\n'
            with open(e.path, 'w', encoding='utf-8') as f:
                f.write(csv_string)
            self.loading_text.value = f"✅ CSV-tiedosto tallennettu: {e.path}"
            self.loading_text.color = ft.Colors.GREEN_600
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe tallennuksessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
        self.page.update()

    def create_candlestick(self, open_price, high_price, low_price, close_price):
        """Luo japanilaisen kynttilän visualisoinnin"""
        try:
            # Validoi hintatiedot
            if pd.isna(open_price) or pd.isna(high_price) or pd.isna(low_price) or pd.isna(close_price):
                return ft.Text("📊", size=12)
            
            # Määritä kynttilän väri (vihreä jos nousu, punainen jos lasku)
            is_bullish = close_price >= open_price
            candle_color = ft.Colors.GREEN_600 if is_bullish else ft.Colors.RED_600
            
            # Laske kynttilän mittasuhteet
            price_range = high_price - low_price
            if price_range <= 0:
                price_range = 0.01  # Estä nollajako
                
            body_height = abs(close_price - open_price)
            
            # Laske sydämen pituudet
            top_wick_length = high_price - max(open_price, close_price)
            bottom_wick_length = min(open_price, close_price) - low_price
            
            # Muunna pixel-arvoiksi (20px = max korkeus)
            scale_factor = 15 / price_range
            top_wick_px = max(1, int(top_wick_length * scale_factor))
            body_px = max(3, int(body_height * scale_factor))
            bottom_wick_px = max(1, int(bottom_wick_length * scale_factor))
            
            # Rajoita maksimiarvot
            top_wick_px = min(top_wick_px, 8)
            body_px = min(body_px, 12)
            bottom_wick_px = min(bottom_wick_px, 8)
            
            # Luo kynttilä-rakenne
            components = []
            
            # Yläsydän
            if top_wick_px > 1:
                components.append(ft.Container(
                    width=1,
                    height=top_wick_px,
                    bgcolor=candle_color,
                ))
            
            # Runko
            components.append(ft.Container(
                width=6,
                height=body_px,
                bgcolor=candle_color,
                border_radius=1,
            ))
            
            # Alasydän
            if bottom_wick_px > 1:
                components.append(ft.Container(
                    width=1,
                    height=bottom_wick_px,
                    bgcolor=candle_color,
                ))
            
            return ft.Column(
                components,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                tight=True
            )
            
        except Exception as e:
            # Fallback
            return ft.Text("📊", size=12)

    def show_stock_data(self, e):
        """Näyttää osakedata taulukossa laskevassa järjestyksessä"""
        if self.stock_data is None:
            self.loading_text.value = "❌ Ei dataa näytettäväksi. Hae ensin data!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return
            
        try:
            # Tyhjennä aiemmat rivit
            self.data_table.rows.clear()
            
            # Lajittele päivämäärän mukaan laskevasti (uusin ensin)
            sorted_data = self.stock_data.sort_index(ascending=False)
            
            # Validoi että meillä on tarvittavat sarakkeet
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in sorted_data.columns for col in required_columns):
                self.loading_text.value = "❌ Puutteellinen data - tarvitaan Open, High, Low, Close, Volume"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return
            
            # Lisää rivit taulukkoon
            for i, (date, row) in enumerate(sorted_data.iterrows()):
                try:
                    # Formatoi päivämäärä
                    date_str = date.strftime("%d.%m.%Y")
                    
                    # Formatoi numerot kahden desimaalin tarkkuudella
                    open_val = f"{row['Open']:.2f}" if pd.notna(row['Open']) else "N/A"
                    high_val = f"{row['High']:.2f}" if pd.notna(row['High']) else "N/A" 
                    low_val = f"{row['Low']:.2f}" if pd.notna(row['Low']) else "N/A"
                    close_val = f"{row['Close']:.2f}" if pd.notna(row['Close']) else "N/A"
                    volume_val = f"{int(row['Volume']):,}".replace(',', ' ') if pd.notna(row['Volume']) else "N/A"
                    
                    # Vaihtoehtoinen rivin väri (zebra-striping)
                    row_color = ft.Colors.GREY_100 if i % 2 == 0 else ft.Colors.WHITE
                    
                    # Luo japanilainen kynttilä tälle päivälle
                    candlestick = self.create_candlestick(
                        row['Open'], row['High'], row['Low'], row['Close']
                    )
                    
                    # Varmista että meillä on tasan 7 solua (vastaa 7 saraketta)
                    cells = [
                        ft.DataCell(ft.Text(date_str, size=12)),
                        ft.DataCell(ft.Text(open_val, size=12)),
                        ft.DataCell(ft.Text(high_val, size=12, color=ft.Colors.GREEN_700)),
                        ft.DataCell(ft.Text(low_val, size=12, color=ft.Colors.RED_700)),
                        ft.DataCell(ft.Text(close_val, size=12, weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(volume_val, size=11)),
                        ft.DataCell(
                            ft.Container(
                                content=candlestick,
                                width=30,
                                height=40,
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]
                    
                    # Varmista että solujen määrä on oikea
                    if len(cells) != 7:
                        print(f"VAROITUS: Rivissä {i} on {len(cells)} solua, pitäisi olla 7")
                        continue
                    
                    # Lisää rivi taulukkoon
                    self.data_table.rows.append(
                        ft.DataRow(cells=cells, color=row_color)
                    )
                    
                except Exception as e:
                    print(f"Virhe rivin {i} käsittelyssä: {e}")
                    # Jatka seuraavaan riviin
                    continue
            
            self.loading_text.value = f"📊 Näytetään {len(self.data_table.rows)} päivän tiedot (scrollaa nähdäksesi lisää)"
            self.loading_text.color = ft.Colors.GREEN_600
            
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe taulukon näyttämisessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            
        self.page.update()

def main(page: ft.Page):
    """Pääfunktio - luo sovelluksen instanssin"""
    app = RawCandleApp(page)

ft.app(target=main, port=8080, view=None)
