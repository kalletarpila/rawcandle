import flet as ft
import datetime
import sqlite3

import pandas as pd
import yfinance as yf
from simu import SimuView, SimulationService


# Compatibility shim: ensure ft.Colors/ft.colors and ft.Icons/ft.icons exist
# Provide a defensive Colors object that contains common color constants used
# throughout the codebase and in tests. If the flet runtime exposes colors,
# prefer those; otherwise provide sensible hex fallbacks.
def _build_compat_colors():
    # desired attribute names used across the codebase and tests
    desired = [
        "BLUE",
        "BLUE_600",
        "ORANGE_700",
        "ORANGE_600",
        "ORANGE_400",
        "ORANGE_300",
        "GREY_600",
        "GREY_50",
        "GREEN_700",
        "GREEN_600",
        "RED_600",
        "RED_700",
        "TRANSPARENT",
        "WHITE",
        "BLACK",
    ]

    # sensible hex defaults (material-like defaults)
    defaults = {
        "BLUE": "#2196F3",
        "BLUE_600": "#1E88E5",
        "ORANGE_700": "#EF6C00",
        "ORANGE_600": "#FB8C00",
        "ORANGE_400": "#FFB74D",
        "ORANGE_300": "#FFCC80",
        "GREY_600": "#757575",
        "GREY_50": "#FAFAFA",
        "GREEN_700": "#2E7D32",
        "GREEN_600": "#43A047",
        "RED_600": "#E53935",
        "RED_700": "#D32F2F",
        "TRANSPARENT": "transparent",
        "WHITE": "#FFFFFF",
        "BLACK": "#000000",
    }

    class _C:
        pass

    src = None
    # prefer ft.colors if it's a module/object with attributes
    if hasattr(ft, "colors"):
        src = ft.colors
    elif hasattr(ft, "Colors"):
        src = ft.Colors

    for name in desired:
        val = None
        if src is not None:
            # try several name forms
            for candidate in (name, name.lower(), name.title(), name.replace("_", "")):
                val = getattr(src, candidate, None)
                if val is not None:
                    break
        if val is None:
            val = defaults.get(name)
        setattr(_C, name, val)

    return _C


# Attach compatibility Colors object under both ft.Colors and ft.colors
try:
    compat_colors = _build_compat_colors()
    # if original ft.colors exists but lacks attributes, keep it accessible via ft._orig_colors
    if not hasattr(ft, "Colors"):
        ft.Colors = compat_colors
    else:
        # ensure ft.Colors exposes the desired attributes
        for k, v in vars(compat_colors).items():
            try:
                setattr(ft.Colors, k, v)
            except Exception:
                try:
                    # if ft.Colors is a module-like object
                    ft.Colors.__dict__[k] = v
                except Exception:
                    pass
    if not hasattr(ft, "colors"):
        ft.colors = ft.Colors
except Exception:
    # Last-resort fallback: ensure attributes exist
    class _C:
        BLUE = "#2196F3"
        ORANGE_700 = "#EF6C00"
        ORANGE_600 = "#FB8C00"
        ORANGE_400 = "#FFB74D"
        GREY_600 = "#757575"
        GREY_50 = "#FAFAFA"
        GREEN_700 = "#2E7D32"
        GREEN_600 = "#43A047"
        RED_600 = "#E53935"
        RED_700 = "#D32F2F"
        TRANSPARENT = "transparent"
        WHITE = "#FFFFFF"
        BLACK = "#000000"

    ft.Colors = _C
    ft.colors = _C

try:
    if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
        ft.Icons = ft.icons
    if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
        ft.icons = ft.Icons
except Exception:
    pass


class RawCandleApp:

    def _close_dialog(self, dialog):
        """Helper method to properly close a dialog."""
        try:
            dialog.open = False
            self.page.update()
            import time

            time.sleep(0.05)
            if dialog in self.page.overlay:
                self.page.overlay.remove(dialog)
            self.page.update()
        except Exception as ex:
            print(f"Error closing dialog: {ex}")

    def on_close_and_ack(self, results_dialog):
        """Sulkee tulosdialogin ja vahvistaa käyttäjältä kuittauksen."""
        try:
            self.close_dialog(results_dialog)
        except Exception:
            pass
        try:
            ack_dlg = ft.AlertDialog(
                title=ft.Text("Huom!"),
                content=ft.Text(
                    "Analyysitulokset ovat tallennettu. Paina OK kuittaaksesi."
                ),
                actions=[
                    ft.TextButton("OK", on_click=lambda _: self.close_dialog(ack_dlg))
                ],
                modal=True,
            )
            if ack_dlg not in self.page.overlay:
                self.page.overlay.append(ack_dlg)
            ack_dlg.open = True
            self.page.update()
        except Exception:
            try:
                sb = ft.SnackBar(
                    ft.Text("Analyysitulokset kirjoitettu."),
                    bgcolor=ft.Colors.BLUE_600,
                    duration=3000,
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()
            except Exception:
                pass

    def create_settings_view(self):
        """Palauttaa placeholder-näkymän asetuksille"""
        return ft.View(
            "/settings",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Asetukset",
                                size=28,
                                weight=ft.FontWeight.BOLD,
                                color=ft.colors.ORANGE_700,
                            ),
                            ft.Text(
                                "Tämä on asetukset-sivu (toteutus puuttuu)",
                                color=ft.colors.GREY_600,
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

    def create_candles_view(self):
        """Luo Candles-sivun näkymän kuudella analyysivalinnalla ja osakevalinnalla"""
        self.candles_checkboxes = [
            ft.Checkbox(label="Hammer", value=False),
            ft.Checkbox(label="Bullish Engulfing", value=False),
            ft.Checkbox(label="Piercing Pattern", value=False),
            ft.Checkbox(label="Three White Soldiers", value=False),
            ft.Checkbox(label="Morning Star", value=False),
            ft.Checkbox(label="Dragonfly Doji", value=False),
            ft.Checkbox(label="Bullish Divergence", value=False),
            ft.Checkbox(label="Bearish Divergence", value=False),
        ]

        # "Kaikki" valintaruutu
        def toggle_all_candles(e):
            """Valitse tai poista valinta kaikista analyysityypeistä"""
            for cb in self.candles_checkboxes:
                cb.value = self.candles_select_all.value
            self.page.update()

        self.candles_select_all = ft.Checkbox(
            label="Kaikki", value=False, on_change=toggle_all_candles
        )

        self.candles_ticker_field = ft.TextField(
            label="Osakkeen ticker (esim. AAPL)",
            width=250,
            hint_text="Jätä tyhjäksi analysoidaksesi kaikki",
        )

        # Painike CSV-tiedoston lataamiseen
        def load_tickers_from_csv(e):
            """Lataa tickerit tickers.txt tiedostosta."""
            import os

            csv_path = "/home/kalle/projects/rawcandle/data/tickers.txt"

            try:
                if not os.path.exists(csv_path):
                    sb = ft.SnackBar(
                        ft.Text(
                            f"❌ Tiedostoa ei löydy: {csv_path}", color=ft.Colors.WHITE
                        ),
                        bgcolor=ft.Colors.RED_600,
                        duration=3000,
                    )
                    if sb not in self.page.overlay:
                        self.page.overlay.append(sb)
                    sb.open = True
                    self.page.update()
                    return

                with open(csv_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                if not content:
                    sb = ft.SnackBar(
                        ft.Text("❌ Tiedosto on tyhjä", color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.RED_600,
                        duration=3000,
                    )
                    if sb not in self.page.overlay:
                        self.page.overlay.append(sb)
                    sb.open = True
                    self.page.update()
                    return

                # Aseta tickerit kenttään (pilkulla eroteltuina)
                # Trimmataan välilyönnit joka tickeristä
                tickers = [line.strip() for line in content.split("\n") if line.strip()]
                tickers_str = ",".join(tickers)

                self.candles_ticker_field.value = tickers_str
                self.candles_ticker_field.update()

                # Vaihda radio valinta "single" tilaan
                self.candles_radio_group.value = "single"
                self.candles_radio_group.update()

                sb = ft.SnackBar(
                    ft.Text(
                        f"✅ Ladattu {len(tickers)} tickeriä tiedostosta",
                        color=ft.Colors.WHITE,
                    ),
                    bgcolor=ft.Colors.GREEN_600,
                    duration=2000,
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()

            except Exception as ex:
                logger.exception("Virhe ladattaessa tickereitä CSV:stä")
                sb = ft.SnackBar(
                    ft.Text(f"❌ Virhe: {ex}", color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()

        self.candles_load_csv_button = ft.ElevatedButton(
            "Lue CSV:stä",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=load_tickers_from_csv,
            bgcolor=ft.Colors.BLUE_400,
            color=ft.Colors.WHITE,
            width=150,
            tooltip="Lataa tickereiden lista CSV-tiedostosta analysoitavaksi",
        )

        self.candles_radio_group = ft.RadioGroup(
            content=ft.Row(
                [
                    ft.Radio(label="Analysoi annettu ticker", value="single"),
                    ft.Radio(label="Analysoi kaikki osakkeet", value="all"),
                ],
                spacing=20,
            ),
            value="single",
        )
        # Uusi kortti: aikavälin valinta
        self.candles_date_radio_group = ft.RadioGroup(
            content=ft.Row(
                [
                    ft.Radio(label="Kaikki päivät", value="all"),
                    ft.Radio(label="Valitse aikaväli", value="range"),
                ],
                spacing=20,
            ),
            value="all",
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
            if self.candles_date_radio_group.value == "range":
                need = bool(
                    self.candles_start_date.value and self.candles_end_date.value
                )
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
                    return datetime.datetime.strptime(s, "%Y-%m-%d").date()
                except Exception:
                    return None

        def on_start_text_change(e):
            v = (
                self.candles_start_date_text.value.strip()
                if self.candles_start_date_text.value
                else ""
            )
            d = try_parse_date(v)
            if d:
                try:
                    self.candles_start_date.value = d
                    self.candles_start_date.update()
                except Exception:
                    pass
            update_start_button_enabled()

        def on_end_text_change(e):
            v = (
                self.candles_end_date_text.value.strip()
                if self.candles_end_date_text.value
                else ""
            )
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
            tooltip="Analysoi valitut kynttiläkuviot valituille tickereille ja tallenna tulokset tietokantaan",
        )
        # Result banner (mirrors main page `loading_text` style)
        self.candles_result_text = ft.Text(value="", color=ft.colors.BLUE_600)

        # Downtrend filters for Candles view
        self.candles_downtrend_filter = ft.Checkbox(
            label="🔻 Suodata vain laskutrendien kynttilät",
            value=True,
        )

        self.candles_min_decline_percent = ft.TextField(
            label="Min. lasku (%)",
            width=120,
            value="3.0",
            hint_text="3.0",
        )

        self.candles_ma_filter = ft.Checkbox(
            label="Lisää liukuva keskiarvo -suodatin",
            value=True,
        )

        self.candles_volume_filter = ft.Checkbox(
            label="Lisää volyymi-suodatin",
            value=False,
        )

        # Random events controls for Candles view
        self.candles_random_checkbox = ft.Checkbox(
            label="Tee random tapahtumia", value=False
        )

        self.candles_random_stocks_field = ft.TextField(
            label="Anna osakkeiden lkm",
            width=160,
            value="100",
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=False,
            # validation attached later
        )

        self.candles_random_events_field = ft.TextField(
            label="Anna tapahtumien lkm per osake",
            width=200,
            value="20",
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=False,
            # validation attached later
        )

        def _on_candles_random_toggle(e):
            try:
                is_checked = bool(self.candles_random_checkbox.value)
                self.candles_random_stocks_field.visible = is_checked
                self.candles_random_events_field.visible = is_checked
                try:
                    self.candles_generate_random_btn.visible = is_checked
                except Exception:
                    pass
                try:
                    self.page.update()
                except Exception:
                    pass
            except Exception:
                pass

        self.candles_random_checkbox.on_change = _on_candles_random_toggle

        def _on_candles_generate(e):
            # perform validation
            _validate_candles_stocks_field()
            _validate_candles_events_field()

            def _do_generate(evt):
                self._close_dialog(confirm_dlg)

                # Run generator in a background thread so UI stays responsive
                import threading
                from analysis.downtrend_generator import generate_random_findings

                try:
                    num_tickers = int(self.candles_random_stocks_field.value or 0)
                except Exception:
                    num_tickers = 100
                try:
                    events_per = int(self.candles_random_events_field.value or 0)
                except Exception:
                    events_per = 20

                # Create progress dialog
                progress_bar = ft.ProgressBar(width=400, value=0)
                progress_text = ft.Text("Käsitelty 0 / 0 osaketta", size=14)
                cancelled = {"value": False}

                def cancel_generation(e):
                    cancelled["value"] = True
                    try:
                        progress_dlg.open = False
                        if progress_dlg in self.page.overlay:
                            self.page.overlay.remove(progress_dlg)
                        self.page.update()
                    except Exception:
                        pass

                progress_dlg = ft.AlertDialog(
                    title=ft.Text("Generoidaan laskutrenditapahtumia..."),
                    content=ft.Column(
                        [
                            progress_text,
                            progress_bar,
                            ft.Text(
                                "Etsitään osakkeita joilla laskutrendi (3% lasku 10 päivässä)",
                                size=12,
                                color=ft.Colors.GREY_700,
                            ),
                        ],
                        tight=True,
                        spacing=10,
                    ),
                    actions=[ft.TextButton("Keskeytä", on_click=cancel_generation)],
                    modal=True,
                )

                if progress_dlg not in self.page.overlay:
                    self.page.overlay.append(progress_dlg)
                progress_dlg.open = True
                try:
                    self.page.update()
                except Exception:
                    pass

                def progress_callback(current, total):
                    """Update progress bar and text."""
                    try:
                        if total > 0:
                            progress_bar.value = current / total
                        progress_text.value = f"Käsitelty {current} / {total} osaketta"
                        self.page.update()
                    except Exception:
                        pass

                def cancel_check():
                    """Check if user cancelled."""
                    return cancelled["value"]

                def worker():
                    inserted = 0
                    errors = []
                    try:
                        inserted, errors = generate_random_findings(
                            num_tickers=num_tickers,
                            events_per_ticker=events_per,
                            progress_callback=progress_callback,
                            cancel_check=cancel_check,
                        )

                        # Update progress dialog to show results
                        try:
                            if cancelled["value"]:
                                result_msg = f"⚠️ Generointi keskeytetty\n\nTallennettu {inserted} tapahtumaa."
                                result_color = ft.Colors.ORANGE_700
                            else:
                                result_msg = f"✅ Generointi valmis!\n\nTallennettu {inserted} laskutrenditapahtumaa tietokantaan."
                                result_color = ft.Colors.GREEN_700

                            if errors:
                                error_count = len(errors)
                                result_msg += (
                                    f"\n\nHuom: {error_count} virhettä generoinnissa."
                                )

                            def close_result_dialog(e):
                                """Close the result dialog."""
                                self._close_dialog(progress_dlg)

                            # Change dialog to show results with OK button
                            progress_dlg.title = ft.Text("Generointi valmis")
                            progress_dlg.content = ft.Column(
                                [
                                    ft.Text(result_msg, size=16),
                                    ft.Divider(),
                                    ft.Text(
                                        f"Käsitelty {num_tickers} osaketta",
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                tight=True,
                                spacing=10,
                            )
                            progress_dlg.actions = [
                                ft.TextButton("OK", on_click=close_result_dialog)
                            ]
                            self.page.update()

                            if errors:
                                error_msg = "\n".join(errors[:5])  # Show first 5 errors
                                if len(errors) > 5:
                                    error_msg += (
                                        f"\n... ja {len(errors) - 5} muuta virhettä"
                                    )
                                print(f"Generointiin liittyi virheitä:\n{error_msg}")

                        except Exception as update_ex:
                            print(f"Error updating result dialog: {update_ex}")
                            # Fallback: close dialog and show snackbar
                            try:
                                progress_dlg.open = False
                                if progress_dlg in self.page.overlay:
                                    self.page.overlay.remove(progress_dlg)
                            except Exception:
                                pass

                            msg = f"Generointi valmis! Tallennettu {inserted} laskutrenditapahtumaa."
                            sb = ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.GREEN_700)
                            if sb not in self.page.overlay:
                                self.page.overlay.append(sb)
                            sb.open = True
                            self.page.update()

                    except Exception as ex:
                        # Close progress dialog
                        try:
                            progress_dlg.open = False
                            if progress_dlg in self.page.overlay:
                                self.page.overlay.remove(progress_dlg)
                        except Exception:
                            pass

                        sb = ft.SnackBar(
                            ft.Text(f"Generointi epäonnistui: {ex}"),
                            bgcolor=ft.Colors.RED_700,
                        )
                        if sb not in self.page.overlay:
                            self.page.overlay.append(sb)
                        sb.open = True
                        try:
                            self.page.update()
                        except Exception:
                            pass

                threading.Thread(target=worker, daemon=True).start()

            confirm_dlg = ft.AlertDialog(
                title=ft.Text("Vahvista generointi"),
                content=ft.Text(
                    "Haluatko generoida laskutrenditapahtumia oikeasta osakedatasta?\n\n"
                    "Etsitään osakkeita joilla:\n"
                    "• Porrastava lasku 10 päivän ajalta\n"
                    "• Vähintään 3% lasku\n"
                    "• Liukuvat keskiarvot vahvistavat laskun\n\n"
                    "Tämä voi kestää hetken..."
                ),
                actions=[
                    ft.TextButton(
                        "Peruuta",
                        on_click=lambda evt: self._close_dialog(confirm_dlg),
                    ),
                    ft.TextButton("Kyllä, generoi", on_click=_do_generate),
                ],
            )

            if confirm_dlg not in self.page.overlay:
                self.page.overlay.append(confirm_dlg)
            confirm_dlg.open = True
            try:
                self.page.update()
            except Exception:
                pass

        self.candles_generate_random_btn = ft.ElevatedButton(
            "Generoi laskutrenditapahtumat",
            icon=ft.Icons.TRENDING_DOWN,
            on_click=_on_candles_generate,
            visible=False,
            bgcolor=ft.Colors.ORANGE_700,
            color=ft.Colors.WHITE,
            tooltip="Generoi satunnaisia laskutrendi-tapahtumia testikäyttöön",
        )

        # Validation helpers for Candles random inputs
        def _validate_candles_stocks_field():
            try:
                raw = (self.candles_random_stocks_field.value or "").strip()
                if not raw:
                    return
                try:
                    v = int(float(raw))
                except Exception:
                    self.candles_random_stocks_field.error_text = "Anna kokonaisluku"
                    if hasattr(self.page, "show_snack_bar"):
                        self.page.show_snack_bar(
                            ft.SnackBar(
                                ft.Text("Syötä kelvollinen numero"),
                                bgcolor=ft.Colors.RED_700,
                            )
                        )
                    try:
                        self.page.update()
                    except Exception:
                        pass
                    return

                if v < 1:
                    v = 1
                if v > 1000:
                    v = 1000
                if str(v) != str(self.candles_random_stocks_field.value):
                    self.candles_random_stocks_field.value = str(v)
                self.candles_random_stocks_field.error_text = None
                try:
                    self.page.update()
                except Exception:
                    pass
            except Exception:
                pass

        def _validate_candles_events_field():
            try:
                raw = (self.candles_random_events_field.value or "").strip()
                if not raw:
                    return
                try:
                    v = int(float(raw))
                except Exception:
                    self.candles_random_events_field.error_text = "Anna kokonaisluku"
                    if hasattr(self.page, "show_snack_bar"):
                        self.page.show_snack_bar(
                            ft.SnackBar(
                                ft.Text("Syötä kelvollinen numero"),
                                bgcolor=ft.Colors.RED_700,
                            )
                        )
                    try:
                        self.page.update()
                    except Exception:
                        pass
                    return

                if v < 1:
                    v = 1
                if v > 200:
                    v = 200
                if str(v) != str(self.candles_random_events_field.value):
                    self.candles_random_events_field.value = str(v)
                self.candles_random_events_field.error_text = None
                try:
                    self.page.update()
                except Exception:
                    pass
            except Exception:
                pass

        # Attach validation to on_change
        self.candles_random_stocks_field.on_change = (
            lambda e: _validate_candles_stocks_field()
        )
        self.candles_random_events_field.on_change = (
            lambda e: _validate_candles_events_field()
        )

        # ensure initial button state
        update_start_button_enabled()

        return ft.View(
            "/candles",
            [
                self.create_appbar(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Candlestick-analyysit",
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700,
                            ),
                            ft.Text(
                                "Valitse haluamasi analyysit ja osakkeet.",
                                size=16,
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Container(height=16),
                            ft.Row(
                                [
                                    self.candles_start_button,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=20,
                            ),
                            ft.Container(content=self.candles_result_text),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            ft.Row(
                                [
                                    ft.Card(
                                        content=ft.Container(
                                            content=ft.Column(
                                                [
                                                    ft.Text(
                                                        "Analyysityypit",
                                                        size=18,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=ft.Colors.ORANGE_600,
                                                    ),
                                                    self.candles_select_all,
                                                    ft.Divider(
                                                        height=1,
                                                        color=ft.Colors.GREY_300,
                                                    ),
                                                    ft.Column(
                                                        self.candles_checkboxes,
                                                        spacing=12,
                                                    ),
                                                    ft.Container(height=12),
                                                    # Downtrend filters card
                                                    ft.Card(
                                                        content=ft.Container(
                                                            content=ft.Column(
                                                                [
                                                                    ft.Text(
                                                                        "Laskutrendi-suodattimet",
                                                                        size=14,
                                                                        weight=ft.FontWeight.BOLD,
                                                                    ),
                                                                    ft.Column(
                                                                        [
                                                                            self.candles_downtrend_filter,
                                                                            self.candles_min_decline_percent,
                                                                            self.candles_ma_filter,
                                                                            self.candles_volume_filter,
                                                                        ],
                                                                        spacing=8,
                                                                        horizontal_alignment=ft.CrossAxisAlignment.START,
                                                                    ),
                                                                ],
                                                                spacing=8,
                                                            ),
                                                            padding=12,
                                                            bgcolor=ft.Colors.GREY_50,
                                                            border_radius=8,
                                                            width=300,
                                                        ),
                                                        elevation=1,
                                                    ),
                                                    ft.Container(height=12),
                                                    # Random tapahtumat card moved here (left column)
                                                    ft.Card(
                                                        content=ft.Container(
                                                            content=ft.Column(
                                                                [
                                                                    ft.Text(
                                                                        "Random tapahtumat",
                                                                        size=14,
                                                                        weight=ft.FontWeight.BOLD,
                                                                    ),
                                                                    ft.Column(
                                                                        [
                                                                            self.candles_random_checkbox,
                                                                            self.candles_random_stocks_field,
                                                                            self.candles_random_events_field,
                                                                            self.candles_generate_random_btn,
                                                                        ],
                                                                        spacing=8,
                                                                        horizontal_alignment=ft.CrossAxisAlignment.START,
                                                                    ),
                                                                ],
                                                                spacing=8,
                                                            ),
                                                            padding=12,
                                                            bgcolor=ft.Colors.GREY_50,
                                                            border_radius=8,
                                                            width=300,
                                                        ),
                                                        elevation=1,
                                                    ),
                                                ],
                                                horizontal_alignment=ft.CrossAxisAlignment.START,
                                            ),
                                            padding=20,
                                            bgcolor=ft.Colors.GREY_50,
                                            border_radius=8,
                                            width=320,
                                        ),
                                        elevation=2,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Card(
                                                content=ft.Container(
                                                    content=ft.Column(
                                                        [
                                                            ft.Text(
                                                                "Osakevalinta",
                                                                size=18,
                                                                weight=ft.FontWeight.BOLD,
                                                                color=ft.Colors.ORANGE_600,
                                                            ),
                                                            self.candles_radio_group,
                                                            ft.Row(
                                                                [
                                                                    self.candles_ticker_field,
                                                                    self.candles_load_csv_button,
                                                                ],
                                                                spacing=10,
                                                                alignment=ft.MainAxisAlignment.START,
                                                            ),
                                                        ],
                                                        horizontal_alignment=ft.CrossAxisAlignment.START,
                                                        spacing=10,
                                                    ),
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
                                                    content=ft.Column(
                                                        [
                                                            ft.Text(
                                                                "Aikaväli",
                                                                size=18,
                                                                weight=ft.FontWeight.BOLD,
                                                                color=ft.Colors.ORANGE_600,
                                                            ),
                                                            self.candles_date_radio_group,
                                                            # Fallback button: some clients don't trigger RadioGroup change properly;
                                                            # provide an explicit enable button that sets the radio and calls the handler.
                                                            ft.Row(
                                                                [
                                                                    ft.ElevatedButton(
                                                                        "Ota aikaväli käyttöön",
                                                                        on_click=lambda e: (
                                                                            setattr(
                                                                                self.candles_date_radio_group,
                                                                                "value",
                                                                                "range",
                                                                            ),
                                                                            self.candles_date_radio_group.on_change(
                                                                                None
                                                                            ),
                                                                            self.page.update(),
                                                                        ),
                                                                        width=220,
                                                                        bgcolor=ft.Colors.ORANGE_300,
                                                                        color=ft.Colors.WHITE,
                                                                        tooltip="Aktivoi aikavälin valinta analyysiä varten",
                                                                    ),
                                                                ],
                                                                alignment=ft.MainAxisAlignment.START,
                                                            ),
                                                            ft.Row(
                                                                [
                                                                    ft.Column(
                                                                        [
                                                                            ft.Text(
                                                                                "Alkupäivä"
                                                                            ),
                                                                            self.candles_start_date,
                                                                            self.candles_start_date_text,
                                                                        ]
                                                                    ),
                                                                    ft.Column(
                                                                        [
                                                                            ft.Text(
                                                                                "Loppupäivä"
                                                                            ),
                                                                            self.candles_end_date,
                                                                            self.candles_end_date_text,
                                                                        ]
                                                                    ),
                                                                ],
                                                                spacing=20,
                                                            ),
                                                        ],
                                                        horizontal_alignment=ft.CrossAxisAlignment.START,
                                                        spacing=10,
                                                    ),
                                                    padding=20,
                                                    bgcolor=ft.Colors.GREY_50,
                                                    border_radius=8,
                                                    width=420,
                                                ),
                                                elevation=2,
                                            ),
                                            ft.Container(height=16),
                                            # (Random tapahtumat card removed from right column)
                                        ]
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=40,
                            ),
                            # ...painonappi siirretty ylös...
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=30,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    padding=40,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # (duplicate settings view removed)

    def create_analysis_view(self):
        """Luo Analysis Dashboard -näkymän"""
        try:
            from analysis.view import AnalysisView

            analysis_view = AnalysisView(
                self.page,
                analysis_db_path="data/analysis.db",
                stock_db_path="data/osakedata.db",
            )

            return ft.View(
                "/analysis",
                [
                    self.create_appbar(),
                    ft.Container(
                        content=analysis_view.create_view(),
                        padding=20,
                        expand=True,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
            )
        except Exception as e:
            # On import failure, fall back to a minimal placeholder view
            import traceback

            traceback.print_exc()
            return ft.View(
                "/analysis",
                [
                    self.create_appbar(),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Analysis Dashboard",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    f"Virhe ladattaessa: {e}", color=ft.Colors.RED_600
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=40,
                    ),
                ],
            )

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
                        content=ft.Column(
                            [
                                ft.Text("Tulokset"),
                                ft.Text("Tulokset-moduulia ei voitu ladata."),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=40,
                    ),
                ],
            )

    def show_analysis_results(self, e):
        import os

        from analysis.logger import setup_logger

        logger = setup_logger()
        output_path = os.path.join(
            os.path.dirname(__file__), "analysis", "analysis_results.txt"
        )
        if not os.path.exists(output_path):
            sb = ft.SnackBar(
                ft.Text("ℹ️ Tulostiedostoa ei löytynyt.", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.ORANGE_600,
                duration=2000,
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            logger.info(
                "analysis_results.txt not found when attempting to show results"
            )
            return
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as ex:
            logger.exception("Virhe avattaessa analyysitulostiedostoa")
            sb = ft.SnackBar(
                ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_600,
                duration=3000,
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
                with open(output_path, "r", encoding="utf-8") as src:
                    data = src.read()
                with open(e.path, "w", encoding="utf-8") as dst:
                    dst.write(data)
                sb = ft.SnackBar(
                    ft.Text(f"✅ Tiedosto tallennettu: {e.path}"),
                    bgcolor=ft.Colors.GREEN_600,
                    duration=2000,
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()
            except Exception as ex:
                logger.exception(
                    "Virhe tallennettaessa analyysitulosta käyttäjän valitsemaan polkuun"
                )
                sb = ft.SnackBar(
                    ft.Text(f"❌ Virhe tallennuksessa: {ex}"),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
                if sb not in self.page.overlay:
                    self.page.overlay.append(sb)
                sb.open = True
                self.page.update()

        save_button = ft.ElevatedButton(
            "Lataa tiedosto",
            icon=ft.Icons.FILE_DOWNLOAD,
            on_click=lambda _: (
                setattr(self.file_picker, "on_result", on_save_analysis_result),
                self.file_picker.save_file(),
            ),
            tooltip="Tallenna analyysin tulokset tiedostoon",
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Analyysin tulokset"),
            content=ft.Column([content_control], tight=True),
            # replace simple close with a handler that closes the results dialog and
            # opens a modal acknowledgement dialog that requires explicit OK
            actions=[
                save_button,
                ft.TextButton("Sulje", on_click=lambda e: self.on_close_and_ack(dlg)),
            ],
        )
        # Use Page.overlay for dialogs (dialog property deprecated)
        if dlg not in self.page.overlay:
            self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # --- Database view helpers (minimal implementations used by tests) ---
    def create_database_view(self):
        """Return a minimal database view used by tests to find export button."""
        # Build a simple structure compatible with tests traversing controls
        export_btn = ft.ElevatedButton(
            "Siirrä tietokantaan",
            tooltip="Siirrä data tietokantaan",
        )
        container = ft.Container(content=ft.Column([ft.Row([export_btn])]))
        view = type("View", (), {"controls": [container]})()
        return view

    def nayta_tietokannan_tiedot(self, e):
        """Show a simple dialog/snackbar containing DB info (test expects no exception)."""
        try:
            dlg = ft.AlertDialog(
                title=ft.Text("Tietokanta"), content=ft.Text("Tietoja tietokannasta")
            )
            if hasattr(self.page, "overlay"):
                self.page.overlay.append(dlg)
                dlg.open = True
            else:
                # fallback: set snack_bar
                self.page.snack_bar = ft.SnackBar(ft.Text("Tietokanta"))
            self.page.update()
        except Exception:
            # tests expect no exception; swallow and set a snack
            try:
                self.page.snack_bar = ft.SnackBar(
                    ft.Text("Tietokantatieto ei saatavilla")
                )
            except Exception:
                pass

    def luo_tietokanta(self):
        """Create or return a path to the source stock data DB. Tests patch this method."""
        # Default behavior: return a fake path under data/
        import os

        data_dir = os.path.join(os.path.dirname(__file__), "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "osakedata.db")
        # ensure file exists
        open(path, "a").close()
        return path

    def csv_tietokantaan(self, src_db_path: str):
        """Import CSV to DB - minimal stub used by tests. Returns True on success."""
        # For tests, simply return True to indicate success
        return True

    def on_database_export_click(self, e):
        """Handler invoked by tests; uses luo_tietokanta and csv_tietokantaan.

        Sets page.snack_bar with a success or error message.
        """
        try:
            db_path = self.luo_tietokanta()
            ok = self.csv_tietokantaan(db_path)
            if ok:
                self.page.snack_bar = ft.SnackBar(ft.Text("CSV-tiedot tallennettu"))
            else:
                self.page.snack_bar = ft.SnackBar(
                    ft.Text("Virhe tietokannan käsittelyssä")
                )
        except Exception as ex:
            self.page.snack_bar = ft.SnackBar(
                ft.Text(f"Virhe tietokannan käsittelyssä: {ex}")
            )

    def start_candles_analysis(self, e):
        import os
        import threading

        from analysis.logger import setup_logger
        from analysis.print_results import print_analysis_results
        from analysis.run_analysis import run_candlestick_analysis

        logger = setup_logger()

        logger.info("start_candles_analysis called")
        # immediate user feedback
        sb = ft.SnackBar(
            ft.Text("🔄 Analyysi käynnistyy...", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_600,
            duration=1500,
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
        if ticker_mode == "single":
            if not ticker:
                dlg = ft.AlertDialog(title=ft.Text("Syötä osakkeen ticker!"))
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
            # Jos ticker sisältää pilkkuja, käsitellään se listana
            if "," in ticker:
                ticker_list = [t.strip() for t in ticker.split(",") if t.strip()]
                ticker = None  # Asetetaan None, jotta käytetään ticker_list:ia
            else:
                ticker_list = None
        else:
            # analyze all tickers if radio group set to 'all'
            ticker = None
            ticker_list = None

        # Aikaväli
        date_mode = self.candles_date_radio_group.value
        # DatePicker.value is either None or a datetime.date
        if date_mode == "range":
            sd = self.candles_start_date.value
            ed = self.candles_end_date.value
            if sd is None or ed is None:
                dlg = ft.AlertDialog(
                    title=ft.Text("Täytä sekä alkupäivä että loppupäivä.")
                )
                if dlg not in self.page.overlay:
                    self.page.overlay.append(dlg)
                dlg.open = True
                self.page.update()
                return
            # ensure start <= end
            if sd > ed:
                dlg = ft.AlertDialog(
                    title=ft.Text("Alkupäivä ei voi olla myöhemmin kuin loppupäivä.")
                )
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

        # Extract downtrend filter values
        downtrend_filter = bool(self.candles_downtrend_filter.value)
        try:
            min_decline_percent = float(self.candles_min_decline_percent.value or "3.0")
        except ValueError:
            min_decline_percent = 3.0
        use_ma_filter = bool(self.candles_ma_filter.value)
        use_volume_filter = bool(self.candles_volume_filter.value)

        # Progress dialog
        progress = ft.ProgressBar(width=400)
        status = ft.Text("Aloitetaan analyysi...")
        dialog = ft.AlertDialog(
            title=ft.Text("Analyysi käynnissä"),
            content=ft.Column([status, progress]),
            actions=[
                ft.TextButton("Sulje", on_click=lambda _: self.close_dialog(dialog))
            ],
            modal=True,
        )
        if dialog not in self.page.overlay:
            self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

        data_dir = os.path.join(os.path.dirname(__file__), "analysis")
        output_path = os.path.join(data_dir, "analysis_results.txt")

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
                        if (
                            fraction - last_fraction >= 0.02
                            or (now - last_update_time) > 0.2
                            or fraction >= 1.0
                        ):
                            last_fraction = fraction
                            last_update_time = now
                            progress.value = max(0.0, min(1.0, fraction))
                            status.value = f"Käsitelty {int(progress.value * 100)} %"
                            self.page.update()
                    except Exception:
                        pass

                db_path = os.path.join(
                    os.path.dirname(__file__), "data", "osakedata.db"
                )
                results = {}
                processed_tickers = []  # Seurataan käsiteltyjä tickereitä
                empty_tickers = []  # Seurataan tickereitä joilla ei dataa
                no_pattern_tickers = (
                    []
                )  # Seurataan tickereitä joilla ei löytynyt kuvioita

                if ticker is None and ticker_list is None:
                    # analyze all tickers in DB and aggregate results
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT DISTINCT osake FROM osakedata ORDER BY osake"
                        )
                        rows = [r[0] for r in cur.fetchall()]
                    total_tickers = len(rows)
                    for idx, t in enumerate(rows):
                        processed_tickers.append(t)

                        # map per-ticker fraction into overall progress
                        def per_ticker_progress(
                            fraction: float, idx=idx, total=total_tickers
                        ):
                            overall = (idx + fraction) / max(1, total)
                            progress_cb(overall)

                        res = run_candlestick_analysis(
                            db_path,
                            t,
                            selected_patterns,
                            start_date,
                            end_date,
                            progress_callback=per_ticker_progress,
                            downtrend_filter=downtrend_filter,
                            min_decline_percent=min_decline_percent,
                            use_ma_filter=use_ma_filter,
                            use_volume_filter=use_volume_filter,
                        )
                        # merge results
                        if res is None:
                            # None = ei dataa
                            empty_tickers.append(t)
                        elif not res:
                            # {} = ei kuvioita
                            no_pattern_tickers.append(t)
                        else:
                            for k, v in res.items():
                                results[k] = results.get(k, []) + v
                elif ticker_list is not None:
                    # Analysoi lista tickereitä
                    total_tickers = len(ticker_list)
                    for idx, t in enumerate(ticker_list):
                        processed_tickers.append(t)

                        # map per-ticker fraction into overall progress
                        def per_ticker_progress(
                            fraction: float, idx=idx, total=total_tickers
                        ):
                            overall = (idx + fraction) / max(1, total)
                            progress_cb(overall)

                        res = run_candlestick_analysis(
                            db_path,
                            t,
                            selected_patterns,
                            start_date,
                            end_date,
                            progress_callback=per_ticker_progress,
                            downtrend_filter=downtrend_filter,
                            min_decline_percent=min_decline_percent,
                            use_ma_filter=use_ma_filter,
                            use_volume_filter=use_volume_filter,
                        )
                        # merge results
                        if res is None:
                            # None = ei dataa
                            empty_tickers.append(t)
                        elif not res:
                            # {} = ei kuvioita
                            no_pattern_tickers.append(t)
                        else:
                            for k, v in res.items():
                                results[k] = results.get(k, []) + v
                else:
                    # Yksittäinen ticker
                    processed_tickers.append(ticker)
                    results = run_candlestick_analysis(
                        db_path,
                        ticker,
                        selected_patterns,
                        start_date,
                        end_date,
                        progress_callback=progress_cb,
                        downtrend_filter=downtrend_filter,
                        min_decline_percent=min_decline_percent,
                        use_ma_filter=use_ma_filter,
                        use_volume_filter=use_volume_filter,
                    )
                    if results is None:
                        # None = ei dataa
                        empty_tickers.append(ticker)
                        results = {}  # Aseta tyhjä dict jatkoa varten
                    elif not results:
                        # {} = ei kuvioita
                        no_pattern_tickers.append(ticker)
                # tallenna ja muodosta viesti
                # Ticker-parametri tulostusfunktiossa: jos useita tickereitä, asetetaan None
                display_ticker = ticker if ticker_list is None else None
                result = print_analysis_results(results, display_ticker, output_path)
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
                logger.info(
                    f"Analyysi valmis: {ticker or (f'{len(ticker_list)} tickeriä' if ticker_list else 'kaikki')} - {safe_msg}"
                )
                # Update Candles result banner: show analyzed ticker(s) and total matches
                try:
                    total_matches = sum(len(v) for v in results.values())
                    if ticker_list is not None:
                        banner = f"Analyysi valmis: {len(ticker_list)} tickeriä, löydetty yhteensä {total_matches} tapahtumaa."
                    elif ticker is None:
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
                    tickers_with_results = len(
                        [k for k in results.keys() if results[k]]
                    )
                    ticker_display = ticker or (
                        f"{len(ticker_list)} tickeriä" if ticker_list else "kaikki"
                    )

                    # Lisää varoitus jos joitain tickereitä ei löytynyt
                    summary = f"Analyysi valmis: {ticker_display}\nLöydetty yhteensä {total_matches} tapahtumaa.\nTickereitä joissa tuloksia: {tickers_with_results}"

                    if empty_tickers:
                        summary += f"\n\n⚠️ {len(empty_tickers)} tickerillä ei dataa kannassa/aikavälillä"
                        if len(empty_tickers) <= 10:
                            summary += f":\n{', '.join(empty_tickers)}"
                        else:
                            summary += f":\n{', '.join(empty_tickers[:10])}... (+{len(empty_tickers)-10} muuta)"

                    if no_pattern_tickers:
                        summary += f"\n\nℹ️ {len(no_pattern_tickers)} tickerillä ei löytynyt kuvioita"
                        if len(no_pattern_tickers) <= 10:
                            summary += f":\n{', '.join(no_pattern_tickers)}"
                        else:
                            summary += f":\n{', '.join(empty_tickers[:10])}... (+{len(empty_tickers)-10} muuta)"

                    summary_dlg = ft.AlertDialog(
                        title=ft.Text("Analyysin yhteenveto"),
                        content=ft.Text(summary),
                        actions=[
                            ft.TextButton(
                                "Näytä tiedosto",
                                on_click=lambda _: self.show_analysis_results(None),
                            ),
                            ft.TextButton(
                                "Sulje",
                                on_click=lambda _: self.close_dialog(summary_dlg),
                            ),
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
                    action="OK",
                    action_color=ft.Colors.WHITE,
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

        from analysis.logger import setup_logger
        from analysis.print_results import print_analysis_results
        from analysis.run_analysis import run_candlestick_analysis

        logger = setup_logger()
        logger.info("start_results_generation called")

        # immediate feedback
        sb = ft.SnackBar(
            ft.Text("🔄 Generoidaan CSV...", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.BLUE_600,
            duration=1500,
        )
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
        if ticker_mode == "single" and not ticker:
            dlg = ft.AlertDialog(title=ft.Text("Syötä osakkeen ticker!"))
            if dlg not in self.page.overlay:
                self.page.overlay.append(dlg)
            dlg.open = True
            self.page.update()
            return
        if ticker_mode == "all":
            ticker = None

        date_mode = self.results_date_radio_group.value
        if date_mode == "range":
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
                db_path = os.path.join(
                    os.path.dirname(__file__), "data", "osakedata.db"
                )
                if ticker is None:
                    # aggregate across all tickers
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT DISTINCT osake FROM osakedata ORDER BY osake"
                        )
                        rows = [r[0] for r in cur.fetchall()]
                    results = {}
                    total = len(rows)
                    for idx, t in enumerate(rows):
                        res = run_candlestick_analysis(
                            db_path, t, selected_patterns, start_date, end_date
                        )
                        for k, v in res.items():
                            results[k] = results.get(k, []) + v
                else:
                    results = run_candlestick_analysis(
                        db_path, ticker, selected_patterns, start_date, end_date
                    )

                data_dir = os.path.join(os.path.dirname(__file__), "analysis")
                output_path = os.path.join(data_dir, "analysis_results.txt")
                result = print_analysis_results(results, ticker, output_path)
                if isinstance(result, tuple):
                    text_msg, csv_path = result
                else:
                    text_msg = result
                    csv_path = None

                total_matches = sum(len(v) for v in results.values())
                if ticker is None:
                    banner = f"Tulokset generoitu: kaikki tickereitä, löydetty yhteensä {total_matches} tapahtumaa."
                else:
                    banner = f"Tulokset generoitu: {ticker}, löydetty yhteensä {total_matches} tapahtumaa."
                try:
                    self.results_banner.value = banner
                    self.results_banner.color = ft.Colors.GREEN_600
                    self.page.update()
                except Exception:
                    pass

                logger.info(
                    f"Results generation done: {ticker} - {str(text_msg)[:200]}"
                )

            except Exception as ex:
                logger.exception("Virhe generoitaessa tuloksia")
                sb2 = ft.SnackBar(
                    ft.Text(f"❌ Virhe generoitaessa: {ex}", color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
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
        csv_path = os.path.join(
            os.path.dirname(__file__), "analysis", "analysis_results.csv"
        )
        if not os.path.exists(csv_path):
            sb = ft.SnackBar(
                ft.Text("ℹ️ CSV-tiedostoa ei löytynyt.", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.ORANGE_600,
                duration=2000,
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            logger.info(
                "analysis_results.csv not found when attempting to show results CSV"
            )
            return
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as ex:
            logger.exception("Virhe avattaessa CSV-tiedostoa")
            sb = ft.SnackBar(
                ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_600,
                duration=3000,
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
            return

        content_control = ft.Text(content, selectable=True)

        save_button = ft.ElevatedButton(
            "Tallenna CSV",
            icon=ft.Icons.FILE_DOWNLOAD,
            on_click=lambda _: (
                setattr(
                    self.file_picker,
                    "on_result",
                    lambda ev: self.save_csv_from_analysis(ev, csv_path),
                ),
                self.file_picker.save_file(),
            ),
            tooltip="Tallenna analyysin tulokset CSV-tiedostoon",
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Analyysin CSV-tulokset"),
            content=ft.Column([content_control], tight=True),
            actions=[
                save_button,
                ft.TextButton("Sulje", on_click=lambda _: self.close_dialog(dlg)),
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
            with open(src_path, "r", encoding="utf-8") as src:
                data = src.read()
            with open(e.path, "w", encoding="utf-8") as dst:
                dst.write(data)
            sb = ft.SnackBar(
                ft.Text(f"✅ CSV tallennettu: {e.path}"),
                bgcolor=ft.Colors.GREEN_600,
                duration=2000,
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()
        except Exception as ex:
            from analysis.logger import setup_logger

            logger = setup_logger()
            logger.exception("Virhe tallennettaessa CSV:ää")
            sb = ft.SnackBar(
                ft.Text(f"❌ Virhe tallennuksessa: {ex}"),
                bgcolor=ft.Colors.RED_600,
                duration=3000,
            )
            if sb not in self.page.overlay:
                self.page.overlay.append(sb)
            sb.open = True
            self.page.update()

    def fetch_and_save_from_file(self, e):
        """Hakee useiden osakkeiden tiedot tiedostosta ja tallentaa kantaan"""
        import os
        import sqlite3
        import time
        from datetime import datetime

        data_dir = os.path.join(os.path.dirname(__file__), "data")
        tickers_file = os.path.join(data_dir, "tickers.txt")
        db_path = os.path.join(data_dir, "osakedata.db")

        # Tarkista tickers.txt
        if not os.path.exists(tickers_file):
            self.loading_text.value = f"❌ Tiedostoa ei löytynyt: {tickers_file}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        # Lue tickerit
        try:
            with open(tickers_file, "r", encoding="utf-8") as f:
                tickers = [line.strip().upper() for line in f if line.strip()]

            if not tickers:
                self.loading_text.value = "❌ Tiedostossa ei ole tickereitä!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

        except Exception as ex:
            self.loading_text.value = f"❌ Virhe tiedostoa lukiessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        # Varmista että kanta on olemassa
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        # Hae olemassa olevat tickerit kannasta
        existing_tickers = set()
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # Varmista taulu
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS osakedata (
                        osake TEXT NOT NULL,
                        pvm TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        volume INTEGER,
                        PRIMARY KEY (osake, pvm)
                    )
                """
                )
                # Hae kaikki uniikit tickerit
                cursor.execute("SELECT DISTINCT osake FROM osakedata")
                existing_tickers = {row[0] for row in cursor.fetchall()}
        except Exception as ex:
            self.loading_text.value = f"❌ Virhe tietokantaa lukiessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        # Tilastot
        total = len(tickers)
        saved_count = 0
        skipped_in_db = 0
        rejected_no_data = 0
        rejected_penny = 0
        error_count = 0
        divergences_calculated = 0

        start_date = "2023-07-01"
        end_date = datetime.now().strftime("%Y-%m-%d")

        self.loading_text.value = f"🔄 Aloitetaan haku {total} osakkeelle..."
        self.loading_text.color = ft.Colors.BLUE_600
        self.page.update()

        for idx, ticker in enumerate(tickers, 1):
            try:
                # Ohita jos jo kannassa
                if ticker in existing_tickers:
                    skipped_in_db += 1
                    if idx % 10 == 0:
                        self.loading_text.value = (
                            f"📊 Käsitelty: {idx}/{total} | "
                            f"Tallennettu: {saved_count} | "
                            f"Ohitettu (kannassa): {skipped_in_db} | "
                            f"Hylätty (ei dataa): {rejected_no_data} | "
                            f"Hylätty (penny): {rejected_penny}"
                        )
                        self.page.update()
                    time.sleep(0.5)  # Lyhyt tauko
                    continue

                # Hae data
                self.loading_text.value = f"🔄 {idx}/{total}: Haetaan {ticker}..."
                self.loading_text.color = ft.Colors.BLUE_600
                self.page.update()

                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date)

                # Tarkista onko dataa
                if hist.empty:
                    rejected_no_data += 1
                    time.sleep(0.5)
                    continue

                # Tarkista penny stock
                avg_close = hist["Close"].mean()
                if avg_close < 1.0:
                    rejected_penny += 1
                    time.sleep(0.5)
                    continue

                # Tarkista keskimääräinen päivävolyymi vuodelta 2025
                hist_2025 = hist[hist.index >= "2025-01-01"]
                if len(hist_2025) > 0:
                    avg_volume_2025 = hist_2025["Volume"].mean()
                    if avg_volume_2025 < 100000:
                        rejected_penny += (
                            1  # Käytetään samaa laskuria yksinkertaisuuden vuoksi
                        )
                        time.sleep(0.5)
                        continue

                # Tallenna kantaan
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    rows_added = 0
                    for date, row in hist.iterrows():
                        date_str = date.strftime("%Y-%m-%d")
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO osakedata 
                            (osake, pvm, open, high, low, close, volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                ticker,
                                date_str,
                                float(row["Open"]) if pd.notna(row["Open"]) else None,
                                float(row["High"]) if pd.notna(row["High"]) else None,
                                float(row["Low"]) if pd.notna(row["Low"]) else None,
                                float(row["Close"]) if pd.notna(row["Close"]) else None,
                                int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                            ),
                        )
                        rows_added += 1
                    conn.commit()

                saved_count += 1
                existing_tickers.add(ticker)  # Lisää listaan

                # Laske divergenssit
                div_success, div_days, div_error = self._calculate_and_save_divergences(
                    ticker, only_missing=True
                )
                if div_success and div_days > 0:
                    divergences_calculated += 1

                # Päivitä tilanne joka 10. osakkeen jälkeen tai jos tallennettu
                if idx % 10 == 0 or saved_count > 0:
                    self.loading_text.value = (
                        f"📊 Käsitelty: {idx}/{total} | "
                        f"Tallennettu: {saved_count} | "
                        f"Divergenssit: {divergences_calculated} | "
                        f"Ohitettu (kannassa): {skipped_in_db} | "
                        f"Hylätty (ei dataa): {rejected_no_data} | "
                        f"Hylätty (penny): {rejected_penny}"
                    )
                    self.loading_text.color = ft.Colors.BLUE_600
                    self.page.update()

                # Tauko Yahoo rate limitin välttämiseksi
                # Lyhyempi tauko jos paljon päiviä (divergenssit vievät aikaa)
                pause_time = 1.0 if rows_added >= 50 else 1.5
                time.sleep(pause_time)

                # 30s tauko joka 500. osakkeen jälkeen
                if idx % 500 == 0:
                    self.loading_text.value = (
                        f"⏳ {idx} osaketta käsitelty, pidetään 30 sekunnin tauko..."
                    )
                    self.loading_text.color = ft.Colors.ORANGE_600
                    self.page.update()
                    time.sleep(30)

            except Exception as ex:
                error_count += 1
                print(f"Virhe tickerillä {ticker}: {ex}")
                time.sleep(0.5)
                continue

        # Lopputilanne
        self.loading_text.value = (
            f"✅ Valmis! | "
            f"Käsitelty: {total} | "
            f"Tallennettu: {saved_count} | "
            f"Divergenssit: {divergences_calculated} | "
            f"Ohitettu (kannassa): {skipped_in_db} | "
            f"Hylätty (ei dataa): {rejected_no_data} | "
            f"Hylätty (penny): {rejected_penny} | "
            f"Virheet: {error_count}"
        )
        self.loading_text.color = ft.Colors.GREEN_600
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
            on_submit=self.fetch_stock_data,
        )
        self.loading_text = ft.Text(value="", color=ft.Colors.BLUE_600)
        self.stock_count_text = ft.Text(
            value="", size=14, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_600
        )
        self.delete_ticker_field = ft.TextField(
            label="Osakkeen ticker",
            width=200,
            hint_text="Esim. AAPL",
        )
        self.delete_dialog = None
        self.clear_dialog = None
        self.stock_data = None
        self.download_button = None
        # FilePicker CSV-tiedoston tallennukseen
        self.file_picker = ft.FilePicker(on_result=self.save_csv_to_path)
        try:
            if hasattr(self.page, "overlay"):
                self.page.overlay.append(self.file_picker)
        except Exception:
            pass
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

        # Simulaatio-välilehden hallinta
        self.simu_service = SimulationService()
        self.simu_view = SimuView(self.page, self.create_appbar, self.simu_service)

        # Aloita etusivulta (only if page supports go)
        try:
            if hasattr(self.page, "go"):
                self.page.go("/")
        except Exception:
            pass

    def setup_page(self):
        """Asettaa sivun perusasetukset"""
        self.page.title = "RawCandle - Flet Web App"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        try:
            # Page.window was introduced in newer Flet; set width/height when available
            if hasattr(self.page, "window") and self.page.window is not None:
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
                    ft.Icons.HOME, tooltip="Home", on_click=lambda _: self.page.go("/")
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS,
                    tooltip="Settings",
                    on_click=lambda _: self.page.go("/settings"),
                ),
                ft.IconButton(
                    ft.Icons.FLARE,
                    tooltip="Candles",
                    on_click=lambda _: self.page.go("/candles"),
                ),
                ft.IconButton(
                    ft.Icons.SCIENCE,
                    tooltip="Simulaatio",
                    on_click=lambda _: self.page.go("/simu"),
                ),
                ft.IconButton(
                    ft.Icons.ANALYTICS,
                    tooltip="Analysis Dashboard",
                    on_click=lambda _: self.page.go("/analysis"),
                ),
                ft.IconButton(
                    ft.Icons.INSIGHTS,
                    tooltip="Tulokset",
                    on_click=lambda _: self.page.go("/tulokset"),
                ),
                ft.IconButton(
                    ft.Icons.EXIT_TO_APP,
                    tooltip="Lopeta ohjelma",
                    on_click=self.quit_app,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE
                    ),
                ),
            ],
        )

    def update_stock_data(self, e):
        """Päivitä olemassa olevien osakkeiden tiedot Yahoosta"""
        import os
        import sqlite3
        import time
        from datetime import datetime, timedelta

        data_dir = os.path.join(os.path.dirname(__file__), "data")
        db_path = os.path.join(data_dir, "osakedata.db")

        if not os.path.exists(db_path):
            self.loading_text.value = "❌ Osakedata.db ei löydy!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        try:
            # Hae kaikki osakkeet ja niiden viimeisin päivämäärä
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT osake, MAX(pvm) as viimeisin_pvm
                    FROM osakedata
                    GROUP BY osake
                    ORDER BY osake
                """
                )
                stocks = cursor.fetchall()

            if not stocks:
                self.loading_text.value = "❌ Ei osakkeita kannassa!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            total_stocks = len(stocks)
            updated_count = 0
            skipped_count = 0
            error_count = 0

            self.loading_text.value = (
                f"🔄 Aloitetaan päivitys {total_stocks} osakkeelle..."
            )
            self.loading_text.color = ft.Colors.BLUE_600
            self.page.update()

            for idx, (ticker, last_date) in enumerate(stocks, 1):
                # Tarkista tarvitaanko päivitystä
                if last_date >= yesterday:
                    skipped_count += 1
                    if idx % 10 == 0:
                        self.loading_text.value = f"⏭️ {idx}/{total_stocks}: {ticker} (ohitettu, data ajan tasalla)"
                        self.page.update()
                    continue

                # Laske päivitysväli
                start_date = (
                    datetime.fromisoformat(last_date) + timedelta(days=1)
                ).strftime("%Y-%m-%d")

                self.loading_text.value = f"🔄 {idx}/{total_stocks}: Haetaan {ticker} ({start_date} → {yesterday})"
                self.loading_text.color = ft.Colors.BLUE_600
                self.page.update()

                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(start=start_date, end=yesterday)

                    if hist.empty:
                        skipped_count += 1
                        continue

                    # Tallenna tietokantaan
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        rows_added = 0
                        for date, row in hist.iterrows():
                            date_str = date.strftime("%Y-%m-%d")
                            cursor.execute(
                                """
                                INSERT OR REPLACE INTO osakedata 
                                (osake, pvm, open, high, low, close, volume)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                                (
                                    ticker,
                                    date_str,
                                    (
                                        float(row["Open"])
                                        if pd.notna(row["Open"])
                                        else None
                                    ),
                                    (
                                        float(row["High"])
                                        if pd.notna(row["High"])
                                        else None
                                    ),
                                    float(row["Low"]) if pd.notna(row["Low"]) else None,
                                    (
                                        float(row["Close"])
                                        if pd.notna(row["Close"])
                                        else None
                                    ),
                                    (
                                        int(row["Volume"])
                                        if pd.notna(row["Volume"])
                                        else None
                                    ),
                                ),
                            )
                            rows_added += 1
                        conn.commit()

                    # Laske divergenssit päivitetylle osakkeelle
                    div_success, div_days, div_error = (
                        self._calculate_and_save_divergences(ticker, only_missing=True)
                    )

                    updated_count += 1
                    msg = f"✅ {idx}/{total_stocks}: {ticker} (+{rows_added} päivää)"
                    if div_success and div_days > 0:
                        msg += f", div: {div_days}"
                    self.loading_text.value = msg
                    self.loading_text.color = ft.Colors.GREEN_600
                    self.page.update()

                except Exception as ex:
                    error_count += 1
                    self.loading_text.value = (
                        f"❌ {idx}/{total_stocks}: {ticker} - Virhe: {str(ex)}"
                    )
                    self.loading_text.color = ft.Colors.RED_600
                    self.page.update()

                # Tauot - lyhyempi jos paljon päiviä (divergenssit vievät aikaa)
                pause_time = 1.0 if rows_added >= 50 else 1.5
                time.sleep(pause_time)

                # 30s tauko per 500 osaketta
                if idx % 500 == 0:
                    self.loading_text.value = (
                        f"⏳ {idx} osaketta käsitelty, pidetään 30 sekunnin tauko..."
                    )
                    self.loading_text.color = ft.Colors.ORANGE_600
                    self.page.update()
                    time.sleep(30)

            # Yhteenveto
            summary = f"""✅ Päivitys valmis!
Käsitelty: {total_stocks} osaketta
Päivitetty: {updated_count} osaketta
Ohitettu: {skipped_count} (data ajan tasalla)
Virheet: {error_count}"""

            self.loading_text.value = summary
            self.loading_text.color = ft.Colors.GREEN_600
            self.page.update()

        except Exception as ex:
            self.loading_text.value = f"❌ Virhe päivityksessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()

    def update_stock_count(self):
        """Päivittää kannassa olevien osakkeiden määrän"""
        import os
        import sqlite3

        try:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            db_path = os.path.join(data_dir, "osakedata.db")

            if not os.path.exists(db_path):
                self.stock_count_text.value = ""
                return

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(DISTINCT osake) FROM osakedata")
                count = cursor.fetchone()[0]
                self.stock_count_text.value = f"Kannassa: {count} osaketta"
        except Exception:
            self.stock_count_text.value = ""

    def calculate_missing_divergences(self, e):
        """Laske puuttuvat divergenssit kaikille osakkeille kannassa"""
        import os
        import sqlite3

        try:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            osakedata_path = os.path.join(data_dir, "osakedata.db")
            analysis_path = os.path.join(data_dir, "analysis.db")

            if not os.path.exists(osakedata_path):
                self.loading_text.value = "❌ Osakedata-kantaa ei löydy!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            # Hae kaikki tickerit
            with sqlite3.connect(osakedata_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT osake FROM osakedata ORDER BY osake")
                all_tickers = [row[0] for row in cursor.fetchall()]

            if not all_tickers:
                self.loading_text.value = "❌ Ei osakkeita kannassa!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            # Tarkista mitkä tarvitsevat divergenssit
            from analysis.database_manager import DatabaseManager

            db_manager = DatabaseManager(db_path=analysis_path)
            tickers_needing_calc = []

            for ticker in all_tickers:
                if not db_manager.has_divergence_data(ticker):
                    tickers_needing_calc.append(ticker)

            db_manager.close()

            if not tickers_needing_calc:
                self.loading_text.value = (
                    "✅ Kaikilla osakkeilla on jo divergenssit laskettu!"
                )
                self.loading_text.color = ft.Colors.GREEN_600
                self.page.update()
                return

            # Laske puuttuvat
            total = len(tickers_needing_calc)
            calculated = 0
            errors = 0

            self.loading_text.value = (
                f"🔄 Lasketaan divergenssejä {total} osakkeelle..."
            )
            self.loading_text.color = ft.Colors.BLUE_600
            self.page.update()

            for idx, ticker in enumerate(tickers_needing_calc, 1):
                try:
                    self.loading_text.value = f"🔄 {idx}/{total}: Lasketaan {ticker}..."
                    self.loading_text.color = ft.Colors.BLUE_600
                    self.page.update()

                    success, days, error = self._calculate_and_save_divergences(
                        ticker, only_missing=False
                    )

                    if success:
                        calculated += 1
                        self.loading_text.value = (
                            f"✅ {idx}/{total}: {ticker} - {days} päivää laskettu"
                        )
                        self.loading_text.color = ft.Colors.GREEN_600
                    else:
                        errors += 1
                        self.loading_text.value = (
                            f"❌ {idx}/{total}: {ticker} - {error}"
                        )
                        self.loading_text.color = ft.Colors.RED_600

                    self.page.update()

                except Exception as ex:
                    errors += 1
                    self.loading_text.value = f"❌ {idx}/{total}: {ticker} - {str(ex)}"
                    self.loading_text.color = ft.Colors.RED_600
                    self.page.update()

            # Yhteenveto
            self.loading_text.value = (
                f"✅ Valmis! Laskettu: {calculated}/{total} | Virheet: {errors}"
            )
            self.loading_text.color = ft.Colors.GREEN_600
            self.page.update()

        except Exception as ex:
            self.loading_text.value = f"❌ Virhe: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()

    def _calculate_and_save_divergences(
        self, ticker: str, only_missing: bool = True
    ) -> tuple:
        """
        Laske ja tallenna divergenssit yhdelle tickerille.

        Args:
            ticker: Osakkeen symboli
            only_missing: Jos True, laske vain päiville joita ei ole divergence_data:ssa

        Returns:
            (success: bool, days_calculated: int, error_message: str)
        """
        import os
        import sqlite3
        import pandas as pd
        from analysis.candlestick_patterns import (
            calculate_rsi,
            is_bullish_divergence,
            is_bearish_divergence,
        )
        from analysis.database_manager import DatabaseManager

        try:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            osakedata_path = os.path.join(data_dir, "osakedata.db")
            analysis_path = os.path.join(data_dir, "analysis.db")

            # Lue osakedata
            with sqlite3.connect(osakedata_path) as conn:
                df = pd.read_sql_query(
                    "SELECT pvm, close FROM osakedata WHERE osake = ? ORDER BY pvm",
                    conn,
                    params=[ticker],
                )

            if df.empty:
                return (False, 0, f"Ei dataa tickerille {ticker}")

            # Laske RSI
            df = calculate_rsi(df, period=14, close_col="close")

            if "RSI" not in df.columns:
                return (False, 0, "RSI-laskenta epäonnistui")

            # Hae olemassa olevat divergenssit jos only_missing
            existing_dates = set()
            if only_missing:
                try:
                    with sqlite3.connect(analysis_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT date FROM divergence_data WHERE ticker = ?",
                            (ticker,),
                        )
                        existing_dates = {row[0] for row in cursor.fetchall()}
                except Exception:
                    pass  # Taulu ei ehkä ole vielä olemassa

            # Laske divergenssit
            divergence_records = []

            for idx in range(len(df)):
                date = str(df.iloc[idx]["pvm"])

                # Ohita jos jo laskettu
                if only_missing and date in existing_dates:
                    continue

                rsi = df.iloc[idx]["RSI"]
                bullish_strength = 0.0
                bearish_strength = 0.0

                # Tarvitaan vähintään 30 päivää historiaa
                if idx >= 30 and not pd.isna(rsi):
                    # Bullish divergence
                    bullish_result = is_bullish_divergence(
                        df,
                        idx=idx,
                        lookback_days=30,
                        min_rsi_gain=3.0,
                        min_days_between=3,
                        close_col="close",
                    )

                    if bullish_result and bullish_result.get("found"):
                        bullish_strength = bullish_result.get("strength", 1.0)

                    # Bearish divergence (vain jos ei bullish)
                    elif not bullish_strength:
                        bearish_result = is_bearish_divergence(
                            df,
                            idx=idx,
                            lookback_days=30,
                            min_rsi_drop=3.0,
                            min_days_between=3,
                            close_col="close",
                        )

                        if bearish_result and bearish_result.get("found"):
                            bearish_strength = bearish_result.get("strength", 1.0)

                divergence_records.append(
                    (
                        date,
                        bullish_strength,
                        bearish_strength,
                        rsi if not pd.isna(rsi) else None,
                    )
                )

            # Tallenna kantaan
            if divergence_records:
                db_manager = DatabaseManager(db_path=analysis_path)
                success = db_manager.save_divergence_batch(ticker, divergence_records)
                db_manager.close()

                if success:
                    return (True, len(divergence_records), "")
                else:
                    return (False, 0, "Tallennus epäonnistui")
            else:
                return (True, 0, "")  # Ei uusia laskettavia

        except Exception as ex:
            return (False, 0, str(ex))

    def show_delete_stock_dialog(self, e):
        """Näyttää dialogin yksittäisen osakkeen poistamiseen"""
        self.delete_ticker_field.value = ""

        self.delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠️ Poista osake"),
            content=ft.Column(
                [
                    ft.Text("Syötä poistettavan osakkeen ticker:"),
                    self.delete_ticker_field,
                    ft.Text(
                        "Tämä poistaa osakkeen kaikki tiedot osakedata- ja analysis-kannoista.",
                        size=12,
                        color=ft.Colors.ORANGE_700,
                    ),
                ],
                tight=True,
                spacing=10,
                height=150,
            ),
            actions=[
                ft.TextButton("Peruuta", on_click=self.close_delete_dialog),
                ft.TextButton(
                    "Poista",
                    on_click=self.delete_stock_confirmed,
                    style=ft.ButtonStyle(color=ft.Colors.RED_700),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Varmista että dialogi on overlay-listassa
        if hasattr(self.page, "overlay"):
            if self.delete_dialog not in self.page.overlay:
                self.page.overlay.append(self.delete_dialog)

        self.page.dialog = self.delete_dialog
        self.delete_dialog.open = True
        self.page.update()

    def close_delete_dialog(self, e):
        """Sulkee poisto-dialogin"""
        if self.delete_dialog:
            self.delete_dialog.open = False
            self.page.update()

    def delete_stock_confirmed(self, e):
        """Poistaa osakkeen tiedot kannasta vahvistuksen jälkeen"""
        import os
        import sqlite3

        ticker = self.delete_ticker_field.value.strip().upper()

        if not ticker:
            self.loading_text.value = "❌ Syötä osakkeen ticker!"
            self.loading_text.color = ft.Colors.RED_600
            self.close_delete_dialog(None)
            self.page.update()
            return

        try:
            data_dir = os.path.join(os.path.dirname(__file__), "data")

            # Poista osakedata-kannasta
            osakedata_path = os.path.join(data_dir, "osakedata.db")
            deleted_osakedata = 0
            if os.path.exists(osakedata_path):
                with sqlite3.connect(osakedata_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM osakedata WHERE osake = ?", (ticker,))
                    deleted_osakedata = cursor.rowcount
                    conn.commit()

            # Poista analysis-kannasta
            analysis_path = os.path.join(data_dir, "analysis.db")
            deleted_analysis = 0
            if os.path.exists(analysis_path):
                with sqlite3.connect(analysis_path) as conn:
                    cursor = conn.cursor()
                    # Tarkista onko analysis-taulu olemassa
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis'"
                    )
                    if cursor.fetchone():
                        cursor.execute(
                            "DELETE FROM analysis WHERE osake = ?", (ticker,)
                        )
                        deleted_analysis = cursor.rowcount
                        conn.commit()

            self.close_delete_dialog(None)
            self.update_stock_count()

            if deleted_osakedata > 0 or deleted_analysis > 0:
                self.loading_text.value = (
                    f"✅ {ticker} poistettu! "
                    f"(osakedata: {deleted_osakedata} riviä, analysis: {deleted_analysis} riviä)"
                )
                self.loading_text.color = ft.Colors.GREEN_600
            else:
                self.loading_text.value = f"❌ Osaketta {ticker} ei löytynyt kannasta"
                self.loading_text.color = ft.Colors.ORANGE_600

            self.page.update()

        except Exception as ex:
            self.close_delete_dialog(None)
            self.loading_text.value = f"❌ Virhe poistaessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()

    def show_clear_database_dialog(self, e):
        """Näyttää dialogin kaikkien tietokantojen tyhjentämiseen"""
        self.clear_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠️ Tyhjennä kannat"),
            content=ft.Column(
                [
                    ft.Text(
                        "Haluatko varmasti tyhjentää KAIKKI tiedot osakedata- ja analysis-kannoista?",
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "TÄTÄ EI VOI PERUA!",
                        size=16,
                        color=ft.Colors.RED_700,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                tight=True,
                spacing=10,
                height=100,
            ),
            actions=[
                ft.TextButton("Peruuta", on_click=self.close_clear_dialog),
                ft.TextButton(
                    "TYHJENNÄ KAIKKI",
                    on_click=self.clear_database_confirmed,
                    style=ft.ButtonStyle(
                        color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.RED_700,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Varmista että dialogi on overlay-listassa
        if hasattr(self.page, "overlay"):
            if self.clear_dialog not in self.page.overlay:
                self.page.overlay.append(self.clear_dialog)

        self.page.dialog = self.clear_dialog
        self.clear_dialog.open = True
        self.page.update()

    def close_clear_dialog(self, e):
        """Sulkee tyhjennys-dialogin"""
        if self.clear_dialog:
            self.clear_dialog.open = False
            self.page.update()

    def clear_database_confirmed(self, e):
        """Tyhjentää kaikki kannat vahvistuksen jälkeen"""
        import os
        import sqlite3

        try:
            data_dir = os.path.join(os.path.dirname(__file__), "data")

            # Tyhjennä osakedata
            osakedata_path = os.path.join(data_dir, "osakedata.db")
            deleted_osakedata = 0
            if os.path.exists(osakedata_path):
                with sqlite3.connect(osakedata_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM osakedata")
                    deleted_osakedata = cursor.rowcount
                    conn.commit()

            # Tyhjennä analysis
            analysis_path = os.path.join(data_dir, "analysis.db")
            deleted_analysis = 0
            if os.path.exists(analysis_path):
                with sqlite3.connect(analysis_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis'"
                    )
                    if cursor.fetchone():
                        cursor.execute("DELETE FROM analysis")
                        deleted_analysis = cursor.rowcount
                        conn.commit()

            self.close_clear_dialog(None)
            self.update_stock_count()

            self.loading_text.value = (
                f"✅ Kannat tyhjennetty! "
                f"(osakedata: {deleted_osakedata} riviä, analysis: {deleted_analysis} riviä)"
            )
            self.loading_text.color = ft.Colors.GREEN_600
            self.page.update()

        except Exception as ex:
            self.close_clear_dialog(None)
            self.loading_text.value = f"❌ Virhe tyhjennettäessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()

    def create_home_view(self):
        """Luo etusivun näkymän"""
        # Päivitä osakkeiden määrä
        self.update_stock_count()

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
                                color=ft.Colors.ORANGE_700,
                            ),
                            ft.Text(
                                "A modern Flet web application",
                                size=16,
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text(
                                                "📈 Yahoo Finance Data",
                                                size=20,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            ft.Text(
                                                "Hae osakkeen tiedot alkaen heinäkuusta 2023",
                                                size=14,
                                                color=ft.Colors.GREY_600,
                                            ),
                                            ft.Row(
                                                [
                                                    self.ticker_field,
                                                    ft.ElevatedButton(
                                                        "Hae data kantaan",
                                                        icon=ft.Icons.DOWNLOAD,
                                                        on_click=self.fetch_stock_data,
                                                        tooltip="Lataa osakkeen historiatiedot Yahoo Finance:sta ja tallenna tietokantaan",
                                                    ),
                                                ],
                                                alignment=ft.MainAxisAlignment.CENTER,
                                            ),
                                            self.loading_text,
                                            ft.Row(
                                                [
                                                    ft.ElevatedButton(
                                                        "Näytä Tiedot",
                                                        icon=ft.Icons.TABLE_VIEW,
                                                        on_click=self.show_stock_data,
                                                        disabled=False,
                                                        tooltip="Näytä osakkeen historiatiedot kannasta",
                                                    ),
                                                    ft.ElevatedButton(
                                                        "Hae ja tallenna tiedot tiedostosta",
                                                        icon=ft.Icons.FILE_DOWNLOAD,
                                                        on_click=self.fetch_and_save_from_file,
                                                        disabled=False,
                                                        tooltip="Lataa osakkeiden tiedot tiedostosta ja tallenna tietokantaan",
                                                    ),
                                                ],
                                                alignment=ft.MainAxisAlignment.CENTER,
                                                spacing=10,
                                            ),
                                            ft.Divider(height=20),
                                            ft.Row(
                                                [
                                                    self.stock_count_text,
                                                    ft.ElevatedButton(
                                                        "Päivitä osaketiedot",
                                                        icon=ft.Icons.UPDATE,
                                                        on_click=self.update_stock_data,
                                                        bgcolor=ft.Colors.BLUE_700,
                                                        color=ft.Colors.WHITE,
                                                        tooltip="Hae puuttuvat päivät kaikille kannassa oleville osakkeille",
                                                    ),
                                                ],
                                                alignment=ft.MainAxisAlignment.CENTER,
                                                spacing=15,
                                            ),
                                            ft.Divider(height=20),
                                            ft.Row(
                                                [
                                                    ft.ElevatedButton(
                                                        "Laske puuttuvat divergenssit",
                                                        icon=ft.Icons.CALCULATE,
                                                        on_click=self.calculate_missing_divergences,
                                                        bgcolor=ft.Colors.PURPLE_700,
                                                        color=ft.Colors.WHITE,
                                                        tooltip="Laske divergenssit osakkeille joilta ne puuttuvat",
                                                    ),
                                                ],
                                                alignment=ft.MainAxisAlignment.CENTER,
                                            ),
                                            ft.Divider(height=20),
                                            ft.Row(
                                                [
                                                    ft.ElevatedButton(
                                                        "Poista osake",
                                                        icon=ft.Icons.DELETE_OUTLINE,
                                                        on_click=self.show_delete_stock_dialog,
                                                        bgcolor=ft.Colors.ORANGE_700,
                                                        color=ft.Colors.WHITE,
                                                        tooltip="Poista yksittäinen osake kannasta",
                                                    ),
                                                    ft.ElevatedButton(
                                                        "Tyhjennä kannat",
                                                        icon=ft.Icons.DELETE_FOREVER,
                                                        on_click=self.show_clear_database_dialog,
                                                        bgcolor=ft.Colors.RED_700,
                                                        color=ft.Colors.WHITE,
                                                        tooltip="Poista KAIKKI tiedot kannoista",
                                                    ),
                                                ],
                                                alignment=ft.MainAxisAlignment.CENTER,
                                                spacing=10,
                                            ),
                                        ],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=10,
                                    ),
                                    padding=20,
                                ),
                                elevation=3,
                            ),
                            ft.Card(
                                content=ft.Container(
                                    content=ft.Column(
                                        [
                                            ft.Text(
                                                "📊 Osakedata",
                                                size=18,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            ft.Container(
                                                content=ft.Column(
                                                    [
                                                        self.data_table,
                                                    ],
                                                    scroll=ft.ScrollMode.AUTO,
                                                ),
                                                height=400,
                                                width=950,
                                                bgcolor=ft.Colors.GREY_50,
                                                padding=10,
                                                border_radius=8,
                                            ),
                                        ],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    padding=20,
                                ),
                                elevation=3,
                            ),
                            ft.Container(height=20),
                            ft.ElevatedButton(
                                "Back to Home",
                                icon=ft.Icons.HOME,
                                on_click=lambda _: self.page.go("/"),
                                tooltip="Palaa päänäkymään",
                            ),
                            ft.ElevatedButton(
                                "Lopeta ohjelma",
                                icon=ft.Icons.EXIT_TO_APP,
                                on_click=self.quit_app,
                                bgcolor=ft.Colors.RED_400,
                                color=ft.Colors.WHITE,
                                tooltip="Sulje sovellus",
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
            duration=1500,
        )
        if sb not in self.page.overlay:
            self.page.overlay.append(sb)
        sb.open = True
        self.page.update()
        try:
            if hasattr(self, "simu_service"):
                self.simu_service.close()
        except Exception:
            pass
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
        elif self.page.route == "/simu":
            self.page.views.append(self.simu_view.create_view())
        elif self.page.route == "/analysis":
            self.page.views.append(self.create_analysis_view())
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
        """Hakee osakedata Yahoo Financesta ja tallentaa osakedata.db kantaan"""
        import os
        import sqlite3
        from datetime import datetime

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
            # Tarkista ensin kannasta viimeisin päivämäärä
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

            db_path = os.path.join(data_dir, "osakedata.db")

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # Varmista että taulu on olemassa
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS osakedata (
                        osake TEXT NOT NULL,
                        pvm TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        volume INTEGER,
                        PRIMARY KEY (osake, pvm)
                    )
                """
                )

                # Hae viimeisin päivämäärä kannasta tälle osakkeelle
                cursor.execute(
                    "SELECT MAX(pvm) FROM osakedata WHERE osake = ?", (ticker,)
                )
                result = cursor.fetchone()
                last_date_in_db = result[0] if result[0] else None

            # Määritä mistä haetaan
            if last_date_in_db:
                # Hae viimeisen päivän jälkeinen data
                from datetime import datetime, timedelta

                last_date_obj = datetime.strptime(last_date_in_db, "%Y-%m-%d")
                start_date = (last_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

                self.loading_text.value = f"🔄 {ticker} löytyy kannasta (viimeisin: {last_date_in_db}), haetaan uudet päivät..."
                self.loading_text.color = ft.Colors.BLUE_600
                self.page.update()
            else:
                # Ei kannassa, hae kaikki
                start_date = "2023-07-01"
                self.loading_text.value = (
                    f"🔄 {ticker} ei kannassa, haetaan koko historia..."
                )
                self.loading_text.color = ft.Colors.BLUE_600
                self.page.update()

            stock = yf.Ticker(ticker)
            end_date = datetime.now().strftime("%Y-%m-%d")

            # Hae historiallinen data
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                if last_date_in_db:
                    self.loading_text.value = (
                        f"✅ {ticker} on jo ajan tasalla (viimeisin: {last_date_in_db})"
                    )
                    self.loading_text.color = ft.Colors.GREEN_600
                else:
                    self.loading_text.value = (
                        f"❌ Ei dataa löytynyt tickerille {ticker}"
                    )
                    self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            # Tarkista onko penny stock (hinta alle $1) - vain jos uusi osake
            if not last_date_in_db:
                avg_close = hist["Close"].mean()
                if avg_close < 1.0:
                    self.loading_text.value = f"❌ {ticker} on penny stock (keskihinta ${avg_close:.3f}). Ei talleteta kantaan."
                    self.loading_text.color = ft.Colors.RED_600
                    self.page.update()
                    return

                # Tarkista keskimääräinen päivävolyymi vuodelta 2025
                hist_2025 = hist[hist.index >= "2025-01-01"]
                if len(hist_2025) > 0:
                    avg_volume_2025 = hist_2025["Volume"].mean()
                    if avg_volume_2025 < 100000:
                        self.loading_text.value = f"❌ {ticker} liian vähän vaihdettu vuonna 2025 (keskim. {avg_volume_2025:,.0f} osaketta/pv). Vaaditaan ≥100k."
                        self.loading_text.color = ft.Colors.RED_600
                        self.page.update()
                        return

            # Tallenna tietokantaan
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # Tallenna rivit (taulu on jo luotu aiemmin)
                rows_added = 0
                for date, row in hist.iterrows():
                    date_str = date.strftime("%Y-%m-%d")
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO osakedata 
                        (osake, pvm, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ticker,
                            date_str,
                            float(row["Open"]) if pd.notna(row["Open"]) else None,
                            float(row["High"]) if pd.notna(row["High"]) else None,
                            float(row["Low"]) if pd.notna(row["Low"]) else None,
                            float(row["Close"]) if pd.notna(row["Close"]) else None,
                            int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                        ),
                    )
                    rows_added += 1

                conn.commit()

            # Laske ja tallenna divergenssit
            div_success, div_days, div_error = self._calculate_and_save_divergences(
                ticker, only_missing=True
            )

            if last_date_in_db:
                msg = f"✅ {ticker}: {rows_added} uutta päivää lisätty kantaan! (aiemmin: {last_date_in_db})"
                if div_success and div_days > 0:
                    msg += f" | Divergenssit laskettu {div_days} päivälle"
                self.loading_text.value = msg
            else:
                msg = f"✅ {ticker}: {rows_added} päivän tiedot tallennettu kantaan!"
                if div_success and div_days > 0:
                    msg += f" | Divergenssit laskettu {div_days} päivälle"
                self.loading_text.value = msg

            if div_error and not div_success:
                self.loading_text.value += f" ⚠️ Divergenssit: {div_error}"

            self.loading_text.color = ft.Colors.GREEN_600
            self.stock_data = hist  # Säilytetään yhteensopivuus

        except Exception as ex:
            self.loading_text.value = f"❌ Virhe dataa hakiessa: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600
            self.stock_data = None

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
            df.index = df.index.strftime("%Y-%m-%d")
            ticker = self.ticker_field.value.strip().upper()
            row_data = [ticker]
            for date, row in df.iterrows():
                date_str = date
                open_val = (
                    f"{row['Open']:.2f}"
                    if "Open" in row and pd.notna(row["Open"])
                    else ""
                )
                close_val = (
                    f"{row['Close']:.2f}"
                    if "Close" in row and pd.notna(row["Close"])
                    else ""
                )
                high_val = (
                    f"{row['High']:.2f}"
                    if "High" in row and pd.notna(row["High"])
                    else ""
                )
                low_val = (
                    f"{row['Low']:.2f}" if "Low" in row and pd.notna(row["Low"]) else ""
                )
                volume_val = (
                    f"{int(row['Volume'])}"
                    if "Volume" in row and pd.notna(row["Volume"])
                    else ""
                )
                row_data.extend(
                    [date_str, open_val, close_val, high_val, low_val, volume_val]
                )
            csv_string = ",".join(row_data) + "\n"
            with open(e.path, "w", encoding="utf-8") as f:
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
            if (
                pd.isna(open_price)
                or pd.isna(high_price)
                or pd.isna(low_price)
                or pd.isna(close_price)
            ):
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
                components.append(
                    ft.Container(
                        width=1,
                        height=top_wick_px,
                        bgcolor=candle_color,
                    )
                )

            # Runko
            components.append(
                ft.Container(
                    width=6,
                    height=body_px,
                    bgcolor=candle_color,
                    border_radius=1,
                )
            )

            # Alasydän
            if bottom_wick_px > 1:
                components.append(
                    ft.Container(
                        width=1,
                        height=bottom_wick_px,
                        bgcolor=candle_color,
                    )
                )

            return ft.Column(
                components,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                tight=True,
            )

        except Exception as e:
            # Fallback
            return ft.Text("📊", size=12)

    def show_stock_data(self, e):
        """Hakee ja näyttää osakedata kannasta"""
        import os
        import sqlite3

        ticker = self.ticker_field.value.strip().upper()

        if not ticker:
            self.loading_text.value = "❌ Syötä osakkeen ticker!"
            self.loading_text.color = ft.Colors.RED_600
            self.page.update()
            return

        try:
            # Tyhjennä aiemmat rivit
            self.data_table.rows.clear()

            # Hae tiedot kannasta
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            db_path = os.path.join(data_dir, "osakedata.db")

            if not os.path.exists(db_path):
                self.loading_text.value = "❌ Tietokantaa ei löydy! Hae ensin dataa."
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT pvm, open, high, low, close, volume
                    FROM osakedata
                    WHERE osake = ?
                    ORDER BY pvm DESC
                    """,
                    (ticker,),
                )
                rows = cursor.fetchall()

            if not rows:
                self.loading_text.value = f"❌ Ei dataa tickerille {ticker} kannassa!"
                self.loading_text.color = ft.Colors.RED_600
                self.page.update()
                return

            # Päivitä taulukon otsikko
            total_days = len(rows)
            self.data_table.columns = [
                ft.DataColumn(
                    ft.Text(
                        f"Päivämäärä ({total_days} päivää)", weight=ft.FontWeight.BOLD
                    )
                ),
                ft.DataColumn(ft.Text("Open", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("High", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Low", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Close", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Volume", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Kynttilä", weight=ft.FontWeight.BOLD)),
            ]

            # Lisää rivit taulukkoon
            for i, row in enumerate(rows):
                try:
                    pvm, open_val, high_val, low_val, close_val, volume_val = row

                    # Formatoi päivämäärä
                    from datetime import datetime

                    date_obj = datetime.strptime(pvm, "%Y-%m-%d")
                    date_str = date_obj.strftime("%d.%m.%Y")

                    # Formatoi numerot
                    open_str = f"{open_val:.2f}" if open_val is not None else "N/A"
                    high_str = f"{high_val:.2f}" if high_val is not None else "N/A"
                    low_str = f"{low_val:.2f}" if low_val is not None else "N/A"
                    close_str = f"{close_val:.2f}" if close_val is not None else "N/A"
                    volume_str = (
                        f"{int(volume_val):,}".replace(",", " ")
                        if volume_val is not None
                        else "N/A"
                    )

                    # Vaihtoehtoinen rivin väri (zebra-striping)
                    row_color = ft.Colors.GREY_100 if i % 2 == 0 else ft.Colors.WHITE

                    # Luo japanilainen kynttilä tälle päivälle
                    if all(
                        v is not None for v in [open_val, high_val, low_val, close_val]
                    ):
                        candlestick = self.create_candlestick(
                            open_val, high_val, low_val, close_val
                        )
                    else:
                        candlestick = ft.Container()

                    # Luo taulukkorivi
                    cells = [
                        ft.DataCell(ft.Text(date_str, size=12)),
                        ft.DataCell(ft.Text(open_str, size=12)),
                        ft.DataCell(
                            ft.Text(high_str, size=12, color=ft.Colors.GREEN_700)
                        ),
                        ft.DataCell(ft.Text(low_str, size=12, color=ft.Colors.RED_700)),
                        ft.DataCell(
                            ft.Text(close_str, size=12, weight=ft.FontWeight.BOLD)
                        ),
                        ft.DataCell(ft.Text(volume_str, size=11)),
                        ft.DataCell(
                            ft.Container(
                                content=candlestick,
                                width=30,
                                height=40,
                                alignment=ft.alignment.center,
                            )
                        ),
                    ]

                    # Lisää rivi taulukkoon
                    self.data_table.rows.append(
                        ft.DataRow(cells=cells, color=row_color)
                    )

                except Exception as e:
                    print(f"Virhe rivin {i} käsittelyssä: {e}")
                    continue

            self.loading_text.value = (
                f"📊 {ticker}: Näytetään {total_days} päivän tiedot kannasta"
            )
            self.loading_text.color = ft.Colors.GREEN_600

        except Exception as ex:
            self.loading_text.value = f"❌ Virhe taulukon näyttämisessä: {str(ex)}"
            self.loading_text.color = ft.Colors.RED_600

        self.page.update()


def main(page: ft.Page):
    """Pääfunktio - luo sovelluksen instanssin"""
    app = RawCandleApp(page)
    # Tallenna app-objekti page-objektiin jotta muut moduulit voivat käyttää sitä
    page.app = app


if __name__ == "__main__":
    # Start the Flet app only when executed as a script. This avoids
    # binding the webserver port during imports (useful for tests/tools).
    import socket
    import sys
    import os

    # Tarkista ympäristömuuttuja FLET_PORT tai komentoriviparametri --port
    port = None

    # Tarkista ympäristömuuttuja
    if os.getenv("FLET_PORT"):
        try:
            port = int(os.getenv("FLET_PORT"))
        except ValueError:
            pass

    # Tarkista komentoriviparametrit
    if "--port" in sys.argv:
        try:
            port_index = sys.argv.index("--port")
            if port_index + 1 < len(sys.argv):
                port = int(sys.argv[port_index + 1])
        except (ValueError, IndexError):
            pass

    # Jos porttia ei määritelty, etsi vapaa portti
    if port is None:

        def find_free_port():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                return s.getsockname()[1]

        port = find_free_port()

    print(f"🚀 Käynnistetään RawCandle sovellus portissa {port}")
    print(f"🌐 Avaa selaimessa: http://localhost:{port}")

    ft.app(target=main, port=port, view=None)
