
import flet as ft
# Compatibility shim: ensure ft.colors and ft.icons exist for backwards compatibility
try:
    # If newer flet version has ft.colors, use it
    ft.Colors = ft.colors
except AttributeError:
    # If older flet version, create alias from ft.Colors to ft.colors
    try:
        ft.colors = ft.Colors
    except AttributeError:
        pass

try:
    ft.Icons = ft.icons
except AttributeError:
    try:
        ft.icons = ft.Icons
    except AttributeError:
        pass
import yfinance as yf
import datetime
import pandas as pd
import io
import base64
import sqlite3
import csv
from pathlib import Path


class RawCandleApp:


    def create_settings_view(self):
        """Palauttaa placeholder-näkymän asetuksille"""
        return ft.View(
            "/settings",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column([
                        ft.Text("Asetukset", size=28, weight=ft.FontWeight.BOLD, color=ft.colors.ORANGE_700),
                        ft.Text("Tämä on asetukset-sivu (toteutus puuttuu)", color=ft.colors.GREY_600),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20),
                    padding=40,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def create_candles_view(self):
        """Luo Candles-sivun näkymän kuudella analyysivalinnalla ja osakevalinnalla"""
        self.candles_checkboxes = [
            ft.Checkbox(label="Hammer", value=False),
            ft.Checkbox(label="Bullish Engulfing", value=False),
            ft.Checkbox(label="Piercing Pattern", value=False),
            ft.Checkbox(label="Three White Soldiers", value=False),
            ft.Checkbox(label="Morning Star", value=False),
            ft.Checkbox(label="Dragonfly Doji", value=False),
        ]
        self.candles_ticker_field = ft.TextField(
            label="Osakkeen ticker (esim. AAPL)",
            width=250,
            hint_text="Jätä tyhjäksi analysoidaksesi kaikki",
        )
        self.candles_radio_group = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(label="Analysoi annettu ticker", value="single"),
                ft.Radio(label="Analysoi kaikki osakkeet", value="all"),
            ], spacing=20),
            value="single"
        )
        # Uusi kortti: aikavälin valinta
        self.candles_date_radio_group = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(label="Kaikki päivät", value="all"),
                ft.Radio(label="Valitse aikaväli", value="range"),
            ], spacing=20),
            value="all"
        )
        # DatePickers for better UX (some Flet versions don't accept label in DatePicker)
        # Start hidden/disabled; we'll toggle both disabled and visible when radio changes
        self.candles_start_date = ft.DatePicker(
            disabled=True,
            visible=False,
        )
        self.candles_end_date = ft.DatePicker(
            disabled=True,
            visible=False,
        )
        # TextField fallbacks: some clients don't open the native DatePicker popup.
        # These allow manual YYYY-MM-DD input and are kept in sync with the DatePicker.
        self.candles_start_date_text = ft.TextField(
            label="Alkupäivä (YYYY-MM-DD)",
            width=200,
            visible=False,
            hint_text="esim. 2025-01-31",
        )
        self.candles_end_date_text = ft.TextField(
            label="Loppupäivä (YYYY-MM-DD)",
            width=200,
            visible=False,
            hint_text="esim. 2025-06-30",
        )

        # helper to control start button enabled state
        def update_start_button_enabled():
            # if date mode is 'range', require both dates filled to enable start
            if self.candles_date_radio_group.value == 'range':
                need = bool(self.candles_start_date.value and self.candles_end_date.value)
                try:
                    self.candles_start_button.disabled = not need
                except Exception:
                    pass
            else:
                try:
                    self.candles_start_button.disabled = False
                except Exception:
                    pass
            try:
                self.candles_start_button.update()
            except Exception:
                pass
        # Text fallback handlers: parse ISO date and push into DatePicker.value when valid
        def try_parse_date(s: str):
            if not s:
                return None
            try:
                d = datetime.date.fromisoformat(s)
                return d
            except Exception:
                try:
                    return datetime.datetime.strptime(s, '%Y-%m-%d').date()
                except Exception:
                    return None

        def on_start_text_change(e):
            v = self.candles_start_date_text.value.strip() if self.candles_start_date_text.value else ''
            d = try_parse_date(v)
            if d:
                try:
                    self.candles_start_date.value = d
                    self.candles_start_date.update()
                except Exception:
                    pass
            update_start_button_enabled()

        def on_end_text_change(e):
            v = self.candles_end_date_text.value.strip() if self.candles_end_date_text.value else ''
            d = try_parse_date(v)
            if d:
                try:
                    self.candles_end_date.value = d
                    self.candles_end_date.update()
                except Exception:
                    pass
            update_start_button_enabled()

        self.candles_start_date_text.on_change = on_start_text_change
        self.candles_end_date_text.on_change = on_end_text_change

        def on_date_radio_change(e):
            # Called when user toggles date mode. Some Flet clients may not re-render
            # disabled->enabled correctly unless we also toggle visibility.
            is_range = self.candles_date_radio_group.value == "range"
            # enable/disable
            self.candles_start_date.disabled = not is_range
            self.candles_end_date.disabled = not is_range
            # show/hide for better compatibility
            self.candles_start_date.visible = is_range
            self.candles_end_date.visible = is_range
            # show/hide fallback text fields
            self.candles_start_date_text.visible = is_range
            self.candles_end_date_text.visible = is_range
            update_start_button_enabled()
            try:
                self.candles_start_date.update()
            except Exception:
                pass
            try:
                self.candles_end_date.update()
            except Exception:
                pass
            try:
                self.candles_start_date_text.update()
            except Exception:
                pass
            try:
                self.candles_end_date_text.update()
            except Exception:
                pass
        self.candles_date_radio_group.on_change = on_date_radio_change

        # create buttons and keep reference to start button for enabling/disabling
        self.candles_start_button = ft.ElevatedButton(
            "Käynnistä analyysi",
            icon=ft.Icons.PLAY_ARROW,
            bgcolor=ft.colors.ORANGE_400,
            color=ft.colors.WHITE,
            on_click=self.start_candles_analysis,
            width=220,
        )
        # Result banner (mirrors main page `loading_text` style)
        self.candles_result_text = ft.Text(value="", color=ft.colors.BLUE_600)
        self.candles_show_button = ft.ElevatedButton(
            "Näytä tulokset",
            icon=ft.Icons.VISIBILITY,
            bgcolor=ft.colors.BLUE_600,
            color=ft.colors.WHITE,
            on_click=self.show_analysis_results if hasattr(self, 'show_analysis_results') else None,
            width=220,
        )

        # ensure initial button state
        update_start_button_enabled()

        return ft.View(
            "/candles",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column([
                            ft.Text(
                                "Candlestick-analyysit",
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700
                            ),
                            ft.Text(
                                "Valitse haluamasi analyysit ja osakkeet.",
                                size=16,
                                color=ft.Colors.GREY_600
                            ),
                            ft.Container(height=16),
                            ft.Row([
                                self.candles_start_button,
                                self.candles_show_button,
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
                            ft.Container(content=self.candles_result_text),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            ft.Row([
                                ft.Card(
                                    content=ft.Container(
                                        content=ft.Column([
                                            ft.Text("Analyysityypit", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_600),
                                            ft.Column(self.candles_checkboxes, spacing=12),
                                        ], horizontal_alignment=ft.CrossAxisAlignment.START),
                                        padding=20,
                                        bgcolor=ft.Colors.GREY_50,
                                        border_radius=8,
                                        width=320,
                                    ),
                                    elevation=2,
                                ),
                                ft.Column([
                                    ft.Card(
                                        content=ft.Container(
                                            content=ft.Column([
                                                ft.Text("Osakevalinta", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_600),
                                                self.candles_radio_group,
                                                self.candles_ticker_field,
                                            ], horizontal_alignment=ft.CrossAxisAlignment.START, spacing=10),
                                            padding=20,
                                            bgcolor=ft.Colors.GREY_50,
                                            border_radius=8,
                                            width=420,
                                        ),
                                        elevation=2,
                                    ),
                                    ft.Container(height=16),
                                    ft.Card(
                                        content=ft.Container(
                                            content=ft.Column([
                                                ft.Text("Aikaväli", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_600),
                                                    self.candles_date_radio_group,
                                                    # Fallback button: some clients don't trigger RadioGroup change properly;
                                                    # provide an explicit enable button that sets the radio and calls the handler.
                                                    ft.Row([
                                                        ft.ElevatedButton(
                                                            "Ota aikaväli käyttöön",
                                                            on_click=lambda e: (setattr(self.candles_date_radio_group, 'value', 'range'),
                                                                               self.candles_date_radio_group.on_change(None),
                                                                               self.page.update()),
                                                            width=220,
                                                            bgcolor=ft.Colors.ORANGE_300,
                                                            color=ft.Colors.WHITE,
                                                        ),
                                                    ], alignment=ft.MainAxisAlignment.START),
                                                    ft.Row([
                                                            ft.Column([ft.Text('Alkupäivä'), self.candles_start_date, self.candles_start_date_text]),
                                                            ft.Column([ft.Text('Loppupäivä'), self.candles_end_date, self.candles_end_date_text]),
                                                        ], spacing=20),
                                            ], horizontal_alignment=ft.CrossAxisAlignment.START, spacing=10),
                                            padding=20,
                                            bgcolor=ft.Colors.GREY_50,
                                            border_radius=8,
                                            width=420,
                                        ),
                                        elevation=2,
                                    ),
                                ])
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=40),
                            # ...painonappi siirretty ylös...
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=30, scroll=ft.ScrollMode.AUTO, expand=True),
                    padding=40,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # (duplicate settings view removed)
    def create_results_view(self):
        # Delegates to the standalone results.view module to keep the page
        # implementation inside the `results` package.
        try:
            from results.view import create_results_view as _create
            return _create(self)
        except Exception:
            # On import failure, fall back to a minimal placeholder view so the app doesn't crash.
            return ft.View(
                "/tulokset",
                [
                    self.create_appbar(),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Tulokset"),
                            ft.Text("Tulokset-moduulia ei voitu ladata."),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=40,
                    ),
                ],
            )
    def show_analysis_results(self, e):
        import os
        from analysis.logger import setup_logger
        logger = setup_logger()
        output_path = os.path.join(os.path.dirname(__file__), 'analysis', 'analysis_results.txt')
        if not os.path.exists(output_path):
            sb = ft.SnackBar(
                ft.Text("ℹ️ Tulostiedostoa ei löytynyt.", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.ORANGE_600,
                duration=2000
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            logger.info("analysis_results.txt not found when attempting to show results")
            return
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as ex:
            logger.exception("Virhe avattaessa analyysitulostiedostoa")
            sb = ft.SnackBar(
                ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_600,
                duration=3000
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            return
        # Dialog content: display the file content (selectable) and add a download button
        content_control = ft.Text(content, selectable=True)

        def on_save_analysis_result(e: ft.FilePickerResultEvent):
            # event.path contains the destination path the user chose
            try:
                if not e.path:
                    return
                with open(output_path, 'r', encoding='utf-8') as src:
                    data = src.read()
                with open(e.path, 'w', encoding='utf-8') as dst:
                    dst.write(data)
                sb = ft.SnackBar(ft.Text(f"✅ Tiedosto tallennettu: {e.path}"), bgcolor=ft.Colors.GREEN_600, duration=2000)
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()
            except Exception as ex:
                logger.exception("Virhe tallennettaessa analyysitulosta käyttäjän valitsemaan polkuun")
                sb = ft.SnackBar(ft.Text(f"❌ Virhe tallennuksessa: {ex}"), bgcolor=ft.Colors.RED_600, duration=3000)
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()

        save_button = ft.ElevatedButton(
            "Lataa tiedosto",
            icon=ft.Icons.FILE_DOWNLOAD,
            on_click=lambda _: (setattr(self.file_picker, 'on_result', on_save_analysis_result), self.file_picker.save_file()),
        )

        dlg = ft.AlertDialog(
            title=ft.Text('Analyysin tulokset'),
            content=ft.Column([content_control], tight=True),
            # replace simple close with a handler that closes the results dialog and
            # opens a modal acknowledgement dialog that requires explicit OK
            actions=[
                save_button,
                ft.TextButton('Sulje', on_click=lambda e: on_close_and_ack(dlg)),
            ],
        )
        # Use Page.overlay for dialogs (dialog property deprecated)
        if dlg not in self.page.overlay:
            self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

        def on_close_and_ack(results_dialog):
            try:
                # close the results dialog
                self.close_dialog(results_dialog)
            except Exception:
                pass
            try:
                # create a modal acknowledgement dialog that user must click OK to dismiss
                ack_dlg = ft.AlertDialog(
                    title=ft.Text('Huom!'),
                    content=ft.Text('Analyysitulokset ovat tallennettu. Paina OK kuittaaksesi.'),
                    actions=[ft.TextButton('OK', on_click=lambda _: self.close_dialog(ack_dlg))],
                    modal=True,
                )
                if ack_dlg not in self.page.overlay:
                    self.page.overlay.append(ack_dlg)
                ack_dlg.open = True
                self.page.update()
            except Exception:
                # fallback: show a normal snackbar that times out if dialog creation fails
                try:
                    sb = ft.SnackBar(ft.Text('Analyysitulokset kirjoitettu.'), bgcolor=ft.Colors.BLUE_600, duration=3000)
                    if sb not in self.page.overlay:
                        self.page.overlay.append(sb)
                    sb.open = True
                    self.page.update()
                except Exception:
                    pass

    def start_candles_analysis(self, e):
        import os
        import threading
        from analysis.run_analysis import run_candlestick_analysis
        from analysis.print_results import print_analysis_results
        from analysis.logger import setup_logger
        logger = setup_logger()

        logger.info("start_candles_analysis called")
        # immediate user feedback
        sb = ft.SnackBar(
            ft.Text("🔄 Analyysi käynnistyy...", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_600,
            duration=1500
        )
        if sb not in self.page.overlay:
            self.page.overlay.append(sb)
        sb.open = True
        self.page.update()

        # Kerää valitut analyysit
        selected_patterns = [cb.label for cb in self.candles_checkboxes if cb.value]
        if not selected_patterns:
            dlg = ft.AlertDialog(title=ft.Text("Valitse vähintään yksi analyysi!"))
            if dlg not in self.page.overlay:
                self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
            return

        # Ticker: respect radio selection (single or all)
        ticker_mode = self.candles_radio_group.value
        ticker = self.candles_ticker_field.value.strip().upper()
        if ticker_mode == 'single':
            if not ticker:
                dlg = ft.AlertDialog(title=ft.Text("Syötä osakkeen ticker!"))
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
        else:
            # analyze all tickers if radio group set to 'all'
            ticker = None

        # Aikaväli
        date_mode = self.candles_date_radio_group.value
        # DatePicker.value is either None or a datetime.date
        if date_mode == "range":
            sd = self.candles_start_date.value
            ed = self.candles_end_date.value
            if sd is None or ed is None:
                dlg = ft.AlertDialog(title=ft.Text("Täytä sekä alkupäivä että loppupäivä."))
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
            # ensure start <= end
            if sd > ed:
                dlg = ft.AlertDialog(title=ft.Text("Alkupäivä ei voi olla myöhemmin kuin loppupäivä."))
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
            start_date = sd.isoformat()
            end_date = ed.isoformat()
        else:
            start_date = None
            end_date = None

        # Progress dialog
        progress = ft.ProgressBar(width=400)
        status = ft.Text("Aloitetaan analyysi...")
        dialog = ft.AlertDialog(
            title=ft.Text("Analyysi käynnissä"),
            content=ft.Column([status, progress]),
            actions=[ft.TextButton("Sulje", on_click=lambda _: self.close_dialog(dialog))],
            modal=True
        )
        if dialog not in self.page.overlay:
            self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

        data_dir = os.path.join(os.path.dirname(__file__), 'analysis')
        output_path = os.path.join(data_dir, 'analysis_results.txt')

        def worker():
            try:
                # suorita analyysi
                import time
                last_update_time = 0.0
                last_fraction = 0.0

                def progress_cb(fraction: float):
                    # Throttle UI updates: update only if fraction increased by >=2% or >0.2s passed
                    nonlocal last_update_time, last_fraction
                    try:
                        now = time.time()
                        if fraction - last_fraction >= 0.02 or (now - last_update_time) > 0.2 or fraction >= 1.0:
                            last_fraction = fraction
                            last_update_time = now
                            progress.value = max(0.0, min(1.0, fraction))
                            status.value = f"Käsitelty {int(progress.value * 100)} %"
                            self.page.update()
                    except Exception:
                        pass
                db_path = os.path.join(os.path.dirname(__file__), 'data', 'osakedata.db')
                results = {}
                if ticker is None:
                    # analyze all tickers in DB and aggregate results
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT DISTINCT osake FROM osakedata ORDER BY osake")
                        rows = [r[0] for r in cur.fetchall()]
                    total_tickers = len(rows)
                    for idx, t in enumerate(rows):
                        # map per-ticker fraction into overall progress
                        def per_ticker_progress(fraction: float, idx=idx, total=total_tickers):
                            overall = (idx + fraction) / max(1, total)
                            progress_cb(overall)
                        res = run_candlestick_analysis(db_path, t, selected_patterns, start_date, end_date, progress_callback=per_ticker_progress)
                        # merge results
                        for k, v in res.items():
                            results[k] = results.get(k, []) + v
                else:
                    results = run_candlestick_analysis(db_path, ticker, selected_patterns, start_date, end_date, progress_callback=progress_cb)
                # tallenna ja muodosta viesti
                result = print_analysis_results(results, ticker, output_path)
                # print_analysis_results may return (msg, csv_path) or a plain string
                if isinstance(result, tuple):
                    text_msg, csv_path = result
                else:
                    text_msg = result
                    csv_path = None
                # päivitykset UI:hin
                status.value = "Analyysi tehty"
                progress.value = 1.0
                self.page.update()
                safe_msg = str(text_msg).replace("\n", " | ")
                logger.info(f"Analyysi valmis: {ticker} - {safe_msg}")
                if csv_path:
                    logger.info(f"Analysis CSV written: {csv_path}")
                # Update Candles result banner: show analyzed ticker(s) and total matches
                try:
                    total_matches = sum(len(v) for v in results.values())
                    if ticker is None:
                        banner = f"Analyysi valmis: kaikki tickereitä, löydetty yhteensä {total_matches} tapahtumaa."
                    else:
                        banner = f"Analyysi valmis: {ticker}, löydetty yhteensä {total_matches} tapahtumaa."
                    self.candles_result_text.value = banner
                    # green on success
                    self.candles_result_text.color = ft.Colors.GREEN_600
                    self.page.update()
                except Exception:
                    pass
                # Näytä yhteenveto-ikkuna: montako matchia ja montako tickeriä sisältää tuloksia
                try:
                    total_matches = sum(len(v) for v in results.values())
                    tickers_with_results = 1 if results else 0
                    summary = f"Analyysi valmis: {ticker}\nLöydetty yhteensä {total_matches} tapahtumaa.\nTickereitä joissa tuloksia: {tickers_with_results}"
                    summary_dlg = ft.AlertDialog(
                        title=ft.Text('Analyysin yhteenveto'),
                        content=ft.Text(summary),
                        actions=[
                            ft.TextButton('Näytä tiedosto', on_click=lambda _: self.show_analysis_results(None)),
                            ft.TextButton('Sulje', on_click=lambda _: self.close_dialog(summary_dlg)),
                        ],
                    )
                    if summary_dlg not in self.page.overlay:
                        self.page.overlay.append(summary_dlg)
                    summary_dlg.open = True
                    self.page.update()
                except Exception:
                    # älä kaada jos yhteenvetonäyttö epäonnistuu
                    pass
            except Exception as ex:
                status.value = f"Virhe: {ex}"
                self.page.update()
                logger.exception("Virhe analyysissä")
                # Näytä snack bar käyttäjälle
                sb = ft.SnackBar(
                    ft.Text(f"❌ Virhe analyysissä: {str(ex)}", color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()

        # startataan worker-säie
        threading.Thread(target=worker, daemon=True).start()

    def start_results_generation(self, e):
        """Starts generating CSV results based on selections in the Tulokset view."""
        import os
        import threading
        from analysis.run_analysis import run_candlestick_analysis
        from analysis.print_results import print_analysis_results
        from analysis.logger import setup_logger

        logger = setup_logger()
        logger.info("start_results_generation called")

        # immediate feedback
        sb = ft.SnackBar(ft.Text("🔄 Generoidaan CSV...", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_600, duration=1500)
        if sb not in self.page.overlay:
            self.page.overlay.append(sb)
        sb.open = True
        self.page.update()

        selected_patterns = [cb.label for cb in self.results_checkboxes if cb.value]
        if not selected_patterns:
            dlg = ft.AlertDialog(title=ft.Text("Valitse vähintään yksi analyysi!"))
            if dlg not in self.page.overlay:
                self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
            return

        ticker_mode = self.results_radio_group.value
        ticker = self.results_ticker_field.value.strip().upper()
        if ticker_mode == 'single' and not ticker:
            dlg = ft.AlertDialog(title=ft.Text("Syötä osakkeen ticker!"))
            if dlg not in self.page.overlay:
                self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
            return
        if ticker_mode == 'all':
            ticker = None

        date_mode = self.results_date_radio_group.value
        if date_mode == 'range':
            sd = self.results_start_date.value
            ed = self.results_end_date.value
            if sd is None or ed is None or sd > ed:
                dlg = ft.AlertDialog(title=ft.Text("Täytä kelvollinen aikaväli."))
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
            start_date = sd.isoformat()
            end_date = ed.isoformat()
        else:
            start_date = None
            end_date = None

        def worker():
            try:
                db_path = os.path.join(os.path.dirname(__file__), 'data', 'osakedata.db')
                if ticker is None:
                    # aggregate across all tickers
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT DISTINCT osake FROM osakedata ORDER BY osake")
                        rows = [r[0] for r in cur.fetchall()]
                    results = {}
                    total = len(rows)
                    for idx, t in enumerate(rows):
                        res = run_candlestick_analysis(db_path, t, selected_patterns, start_date, end_date)
                        for k, v in res.items():
                            results[k] = results.get(k, []) + v
                else:
                    results = run_candlestick_analysis(db_path, ticker, selected_patterns, start_date, end_date)

                data_dir = os.path.join(os.path.dirname(__file__), 'analysis')
                output_path = os.path.join(data_dir, 'analysis_results.txt')
                result = print_analysis_results(results, ticker, output_path)
                if isinstance(result, tuple):
                    text_msg, csv_path = result
                else:
                    text_msg = result
                    csv_path = None

                total_matches = sum(len(v) for v in results.values())
                if ticker is None:
                    banner = f"CSV generoitu: kaikki tickereitä, löydetty yhteensä {total_matches} tapahtumaa."
                else:
                    banner = f"CSV generoitu: {ticker}, löydetty yhteensä {total_matches} tapahtumaa."
                try:
                    self.results_banner.value = banner
                    self.results_banner.color = ft.Colors.GREEN_600
                    self.page.update()
                except Exception:
                    pass

                logger.info(f"Results generation done: {ticker} - {str(text_msg)[:200]}")
                if csv_path:
                    logger.info(f"Results CSV written: {csv_path}")

            except Exception as ex:
                logger.exception("Virhe generoitaessa tuloksia")
                sb2 = ft.SnackBar(ft.Text(f"❌ Virhe generoitaessa: {ex}", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, duration=3000)
                if sb2 not in self.page.overlay:
                    self.page.overlay.append(sb2)
                sb2.open = True
                self.page.update()

        threading.Thread(target=worker, daemon=True).start()

    def show_results_csv(self, e):
        """Opens the canonical analysis CSV if exists or notifies the user."""
        import os
        from analysis.logger import setup_logger
        logger = setup_logger()
        csv_path = os.path.join(os.path.dirname(__file__), 'analysis', 'analysis_results.csv')
        if not os.path.exists(csv_path):
            sb = ft.SnackBar(ft.Text("ℹ️ CSV-tiedostoa ei löytynyt.", color=ft.Colors.WHITE), bgcolor=ft.Colors.ORANGE_600, duration=2000)
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            logger.info("analysis_results.csv not found when attempting to show results CSV")
            return
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as ex:
            logger.exception("Virhe avattaessa CSV-tiedostoa")
            sb = ft.SnackBar(ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, duration=3000)
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            return

        content_control = ft.Text(content, selectable=True)

        save_button = ft.ElevatedButton(
            "Tallenna CSV",
            icon=ft.Icons.FILE_DOWNLOAD,
            on_click=lambda _: (setattr(self.file_picker, 'on_result', lambda ev: self.save_csv_from_analysis(ev, csv_path)), self.file_picker.save_file()),
        )

        dlg = ft.AlertDialog(
            title=ft.Text('Analyysin CSV-tulokset'),
            content=ft.Column([content_control], tight=True),
            actions=[
                save_button,
                ft.TextButton('Sulje', on_click=lambda _: self.close_dialog(dlg)),
            ],
        )
        if dlg not in self.page.overlay:
            self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def save_csv_from_analysis(self, e: ft.FilePickerResultEvent, src_path: str):
        if not e.path:
            return
        try:
            with open(src_path, 'r', encoding='utf-8') as src:
                data = src.read()
            with open(e.path, 'w', encoding='utf-8') as dst:
                dst.write(data)
            sb = ft.SnackBar(ft.Text(f"✅ CSV tallennettu: {e.path}"), bgcolor=ft.Colors.GREEN_600, duration=2000)
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
        except Exception as ex:
            from analysis.logger import setup_logger
            logger = setup_logger()
            logger.exception("Virhe tallennettaessa CSV:ää")
            sb = ft.SnackBar(ft.Text(f"❌ Virhe tallennuksessa: {ex}"), bgcolor=ft.Colors.RED_600, duration=3000)
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
    def fetch_and_save_from_file(self, e):
        import os
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        tickers_file = os.path.join(data_dir, "tickers.txt")
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
            import time
            for idx, ticker in enumerate(tickers):
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
                        # Kirjoita lokiin
                        loki_path = os.path.join(data_dir, "loki.txt")
                        from datetime import datetime
                        log_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_entry = f"{log_date}, {ticker}, {len(df)} päivää\n"
                        with open(loki_path, 'a', encoding='utf-8') as loki:
                            loki.write(log_entry)
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
                # 1 sekunnin tauko jokaisen osakkeen jälkeen
                time.sleep(1)
                # 1 minuutin tauko joka 100. osakkeen jälkeen
                if (idx + 1) % 100 == 0:
                    self.loading_text.value = f"⏳ 100 osaketta luettu, pidetään minuutin tauko..."
                    self.loading_text.color = ft.Colors.ORANGE_600
                    self.page.update()
                    time.sleep(60)
            self.loading_text.value = "\n".join(results)
            self.loading_text.color = ft.Colors.GREEN_600
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe tiedostoa käsitellessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
        self.page.update()
        import os
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        tickers_file = os.path.join(data_dir, "tickers.txt")
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
            import time
            for idx, ticker in enumerate(tickers):
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
                        # Kirjoita lokiin
                        loki_path = os.path.join(data_dir, "loki.txt")
                        from datetime import datetime
                        log_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_entry = f"{log_date}, {ticker}, {len(df)} päivää\n"
                        with open(loki_path, 'a', encoding='utf-8') as loki:
                            loki.write(log_entry)
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
                # 1 sekunnin tauko jokaisen osakkeen jälkeen
                time.sleep(1)
                # 1 minuutin tauko joka 100. osakkeen jälkeen
                if (idx + 1) % 100 == 0:
                    self.loading_text.value = f"⏳ 100 osaketta luettu, pidetään minuutin tauko..."
                    self.loading_text.color = ft.Colors.ORANGE_600
                    self.page.update()
                    time.sleep(60)
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
        try:
            # Page.window was introduced in newer Flet; set width/height when available
            if hasattr(self.page, 'window') and self.page.window is not None:
                self.page.window.width = 800
                self.page.window.height = 600
        except Exception:
            # fallback - ignore if attribute not present
            pass
        
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
                ft.IconButton(
                    ft.Icons.FLARE,
                    tooltip="Candles",
                    on_click=lambda _: self.page.go("/candles")
                ),
                ft.IconButton(
                    ft.Icons.INSIGHTS,
                    tooltip="Tulokset",
                    on_click=lambda _: self.page.go("/tulokset")
                ),
                ft.IconButton(
                    ft.Icons.EXIT_TO_APP,
                    tooltip="Lopeta ohjelma",
                    on_click=self.quit_app,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE),
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
                                        ft.Text("Hae osakkeen tiedot alkaen heinäkuusta 2023", size=14, color=ft.Colors.GREY_600),
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
                            ft.ElevatedButton(
                                "Lopeta ohjelma",
                                icon=ft.Icons.EXIT_TO_APP,
                                on_click=self.quit_app,
                                bgcolor=ft.Colors.RED_400,
                                color=ft.Colors.WHITE,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
                    ),
                    padding=40,
                    expand=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    def quit_app(self, e):
        import sys
        sb = ft.SnackBar(
            ft.Text("Ohjelma lopetettu", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_400,
            duration=1500
        )
        if sb not in self.page.overlay:
            self.page.overlay.append(sb)
        sb.open = True
        self.page.update()
        import threading
        def delayed_exit():
            import time
            time.sleep(1.5)
            sys.exit(0)
        threading.Thread(target=delayed_exit).start()

    def route_change(self, route):
        """Käsittelee reitityksen muutokset"""
        self.page.views.clear()
        # Lisää näkymä reitin perusteella
        if self.page.route == "/" or self.page.route == "/home":
            self.page.views.append(self.create_home_view())
        elif self.page.route == "/settings":
            self.page.views.append(self.create_settings_view())
        elif self.page.route == "/candles":
            self.page.views.append(self.create_candles_view())
        elif self.page.route == "/tulokset":
            self.page.views.append(self.create_results_view())
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
                self.loading_text.value = f"❌ Ei dataa löytynyt tickerille {ticker} Sori! "
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
            # Kirjoita lokiin
            loki_path = os.path.join(data_dir, "loki.txt")
            from datetime import datetime
            log_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{log_date}, {ticker}, {len(df)} päivää\n"
            with open(loki_path, 'a', encoding='utf-8') as loki:
                loki.write(log_entry)
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


if __name__ == "__main__":
    # Start the Flet app only when executed as a script. This avoids
    # binding the webserver port during imports (useful for tests/tools).
    ft.app(target=main, port=8080, view=None)
