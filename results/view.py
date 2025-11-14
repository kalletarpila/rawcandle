import datetime
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

import flet as ft

from analysis.database_manager import DatabaseManager
from analysis.results_generator import ResultsGenerator
from compute_new_features import FeatureEnrichmentSummary, run_feature_enrichment
from results.excel_exporter import ExcelExporter

# Note: this module implements the whole "Tulokset" page and its handlers
# as free functions that operate on the main app instance passed as `app`.
# This keeps the page implementation isolated inside the `results` package.


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


def generate_results_to_database(
    app,
    progress_callback=None,
    ticker_filter=None,
    pattern_filter=None,
    divergence_combo_filter=False,
    force_rebuild=False,
):
    """
    Generoi tulokset tietokantaan ResultsGeneratorilla.

    Args:
        app: App instance
        progress_callback: Progress callback function
        ticker_filter: Lista tickereistä joille generoidaan (None = kaikki)
        pattern_filter: Lista pattern-numeroista joita generoidaan (None = kaikki)
        divergence_combo_filter: Jos True, generoi vain kynttilämalli + divergenssi yhdistelmät
        force_rebuild: Jos True, tyhjennä ensin results_data taulu

    Returns:
        Tuple[int, float, str, Optional[FeatureEnrichmentSummary], Optional[str]]:
        (rows_inserted, processing_time, error_msg, feature_summary, feature_error)
    """
    try:
        # Hae polut
        analysis_db = "data/analysis.db"
        stock_db = "data/osakedata.db"

        if not os.path.exists(analysis_db):
            return (
                0,
                0.0,
                f"Analysis-tietokantaa ei löydy: {analysis_db}",
                None,
                None,
            )

        if not os.path.exists(stock_db):
            return (
                0,
                0.0,
                f"Stock-tietokantaa ei löydy: {stock_db}",
                None,
                None,
            )

        # Luo generaattori
        db_manager = DatabaseManager(analysis_db)

        # Tyhjennä vain suodatetut rivit jos force_rebuild
        if force_rebuild:
            # Jos on filttereitä, poista vain ne rivit jotka vastaavat filttereitä
            if pattern_filter or ticker_filter:
                deleted = db_manager.delete_results_by_filters(
                    pattern_filter=pattern_filter, ticker_filter=ticker_filter
                )
                # Log info
                print(
                    f"🗑️ Force rebuild: poistettu {deleted} riviä filttereiden perusteella"
                )
            else:
                # Ei filttereitä = tyhjennä koko taulu
                db_manager.clear_results_data()

        generator = ResultsGenerator(db_manager, stock_db)

        # Generoi suodattimilla
        rows, time_taken = generator.generate_results(
            progress_callback=progress_callback,
            ticker_filter=ticker_filter,
            pattern_filter=pattern_filter,
            divergence_combo_filter=divergence_combo_filter,
        )

        feature_summary = None
        feature_error = None
        try:
            feature_summary = run_feature_enrichment(
                analysis_db_path=analysis_db,
                stock_db_path=stock_db,
                create_backup=False,
                verbose=False,
            )
        except Exception as exc:  # pragma: no cover - surfaced to UI
            feature_error = str(exc)

        return rows, time_taken, None, feature_summary, feature_error

    except Exception as e:
        return 0, 0.0, str(e), None, None


def clear_results_database(app):
    """
    Tyhjennä results_data taulu.

    Returns:
        Tuple[int, str]: (deleted_rows, error_msg)
    """
    try:
        analysis_db = "data/analysis.db"

        if not os.path.exists(analysis_db):
            return 0, f"Analysis-tietokantaa ei löydy: {analysis_db}"

        db_manager = DatabaseManager(analysis_db)
        deleted = db_manager.clear_results_data()

        return deleted, None

    except Exception as e:
        return 0, str(e)


def get_results_metadata(app):
    """
    Hae viimeisin metadata results_metadata taulusta.

    Returns:
        dict tai None
    """
    try:
        analysis_db = "data/analysis.db"

        if not os.path.exists(analysis_db):
            return None

        db_manager = DatabaseManager(analysis_db)
        return db_manager.get_latest_results_metadata()

    except Exception:
        return None


def create_results_view(app) -> ft.View:
    """Builds and returns the /tulokset ft.View and wires handlers to use
    functions defined in this module. The `app` parameter is the
    RawCandleApp instance from main.py (we use app.page, app.file_picker, ...).
    """
    # controls
    app.results_checkboxes = [
        ft.Checkbox(label="downtrend", value=False),
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
    def toggle_all_results(e):
        """Valitse tai poista valinta kaikista analyysityypeistä"""
        for cb in app.results_checkboxes:
            cb.value = app.results_select_all.value
        app.page.update()

    app.results_select_all = ft.Checkbox(
        label="Kaikki", value=False, on_change=toggle_all_results
    )

    # Laskutrendi-suodattimet
    app.results_downtrend_filter = ft.Checkbox(
        label="🔻 Suodata vain laskutrendien kynttilät", value=True
    )
    app.results_min_decline_percent = ft.TextField(
        label="Min. lasku (%)", width=120, value="3.0", hint_text="3.0"
    )
    app.results_ma_filter = ft.Checkbox(
        label="Lisää liukuva keskiarvo -suodatin", value=True
    )
    app.results_volume_filter = ft.Checkbox(label="Lisää volyymi-suodatin", value=False)

    # Generointi-asetukset
    app.results_force_rebuild = ft.Checkbox(
        label="🔄 Poista ensin valitut patternit/tickerit ennen generointia",
        value=False,
        tooltip="Valittuna: Poistaa VAIN valittujen patternien/tickerien rivit results_data:sta ennen uudelleengenerointia.\nEi valittuna: Lisää vain uusia löydöksiä (inkrementaalinen päivitys - ei poista mitään).",
    )

    # Divergenssi-yhdistelmä filtteri
    app.results_divergence_combo_filter = ft.Checkbox(
        label="Vain kynttilämalli + divergenssi -yhdistelmät",
        value=False,
        tooltip="Näytä vain tapahtumat joissa samalla tickerillä samana päivänä on sekä kynttilämalli (1-6) että divergenssi (7-8)",
    )

    app.results_ticker_field = ft.TextField(
        label="Osakkeen ticker (esim. AAPL)",
        width=250,
        hint_text="Jätä tyhjäksi analysoidaksesi kaikki",
    )

    # Painike CSV-tiedoston lataamiseen
    def load_tickers_from_csv_results(e):
        """Lataa tickerit tickers.txt tiedostosta results-sivulle."""
        import os
        from analysis.logger import setup_logger

        logger = setup_logger()
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
                if sb not in app.page.overlay:
                    app.page.overlay.append(sb)
                sb.open = True
                app.page.update()
                return

            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            tickers = []
            for raw_line in lines:
                line = raw_line.split("#", 1)[0].strip()
                if not line:
                    continue
                if "," in line:
                    line = line.split(",", 1)[0]
                if ";" in line:
                    line = line.split(";", 1)[0]
                if line:
                    tickers.append(line.upper())

            if not tickers:
                sb = ft.SnackBar(
                    ft.Text("❌ Tiedosto on tyhjä", color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
                if sb not in app.page.overlay:
                    app.page.overlay.append(sb)
                sb.open = True
                app.page.update()
                return

            tickers_str = ",".join(tickers)

            app.results_ticker_field.value = tickers_str
            app.results_ticker_field.update()

            # Vaihda radio valinta "single" tilaan
            app.results_radio_group.value = "single"
            app.results_radio_group.update()

            sb = ft.SnackBar(
                ft.Text(
                    f"✅ Ladattu {len(tickers)} tickeriä tiedostosta",
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.GREEN_600,
                duration=2000,
            )
            if sb not in app.page.overlay:
                app.page.overlay.append(sb)
            sb.open = True
            app.page.update()

        except Exception as ex:
            logger.exception("Virhe ladattaessa tickereitä CSV:stä (results)")
            sb = ft.SnackBar(
                ft.Text(f"❌ Virhe: {ex}", color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_600,
                duration=3000,
            )
            if sb not in app.page.overlay:
                app.page.overlay.append(sb)
            sb.open = True
            app.page.update()

    app.results_load_csv_button = ft.ElevatedButton(
        "Lue CSV:stä",
        icon=ft.Icons.UPLOAD_FILE,
        on_click=load_tickers_from_csv_results,
        bgcolor=ft.Colors.BLUE_400,
        color=ft.Colors.WHITE,
        width=150,
    )

    app.results_radio_group = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(label="Analysoi annettu ticker", value="single"),
                ft.Radio(label="Analysoi kaikki osakkeet", value="all"),
            ],
            spacing=20,
        ),
        value="single",
    )
    app.results_date_radio_group = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(label="Kaikki päivät", value="all"),
                ft.Radio(label="Valitse aikaväli", value="range"),
            ],
            spacing=20,
        ),
        value="all",
    )
    app.results_start_date = ft.DatePicker(disabled=True, visible=False)
    app.results_end_date = ft.DatePicker(disabled=True, visible=False)
    app.results_start_date_text = ft.TextField(
        label="Alkupäivä (YYYY-MM-DD)",
        width=200,
        visible=False,
        hint_text="esim. 2025-01-31",
    )
    app.results_end_date_text = ft.TextField(
        label="Loppupäivä (YYYY-MM-DD)",
        width=200,
        visible=False,
        hint_text="esim. 2025-06-30",
    )

    def on_start_text_change(e):
        v = (
            app.results_start_date_text.value.strip()
            if app.results_start_date_text.value
            else ""
        )
        d = try_parse_date(v)
        if d:
            try:
                app.results_start_date.value = d
                app.results_start_date.update()
            except Exception:
                pass

    def on_end_text_change(e):
        v = (
            app.results_end_date_text.value.strip()
            if app.results_end_date_text.value
            else ""
        )
        d = try_parse_date(v)
        if d:
            try:
                app.results_end_date.value = d
                app.results_end_date.update()
            except Exception:
                pass

    app.results_start_date_text.on_change = on_start_text_change
    app.results_end_date_text.on_change = on_end_text_change

    def on_date_radio_change(e):
        is_range = app.results_date_radio_group.value == "range"
        app.results_start_date.disabled = not is_range
        app.results_end_date.disabled = not is_range
        app.results_start_date.visible = is_range
        app.results_end_date.visible = is_range
        app.results_start_date_text.visible = is_range
        app.results_end_date_text.visible = is_range
        try:
            app.results_start_date.update()
        except Exception:
            pass
        try:
            app.results_end_date.update()
        except Exception:
            pass
        try:
            app.results_start_date_text.update()
        except Exception:
            pass
        try:
            app.results_end_date_text.update()
        except Exception:
            pass

    app.results_date_radio_group.on_change = on_date_radio_change

    # Buttons
    # wire the generate button to the implementation in results.excel_cache
    try:
        # Käytä uutta optimoitua Excel-cachetä
        def paivita_excel_cache_click(e):
            """Päivitä Excel-tiedosto uudella optimoidulla cachellä"""

            progress_dialog = None
            progress_title = ft.Text("Generoidaan Excel-tiedostoa")
            progress_text = ft.Text("Aloitetaan Excel-generointi...")
            progress_bar = ft.ProgressBar(width=400)

            try:
                progress_dialog = ft.AlertDialog(
                    modal=True,
                    title=progress_title,
                    content=ft.Column(
                        [
                            progress_text,
                            progress_bar,
                            ft.Text("Tämä voi kestää hetken..."),
                        ],
                        tight=True,
                        height=120,
                    ),
                    actions=[],
                )

                if progress_dialog not in app.page.overlay:
                    app.page.overlay.append(progress_dialog)
                e.page.dialog = progress_dialog
                progress_dialog.open = True
                e.page.update()

                def close_progress_dialog():
                    try:
                        if progress_dialog:
                            try:
                                if hasattr(app, "close_dialog"):
                                    app.close_dialog(progress_dialog)
                                    return
                            except Exception:
                                pass
                            progress_dialog.open = False
                            if progress_dialog in e.page.overlay:
                                e.page.overlay.remove(progress_dialog)
                            e.page.dialog = None
                            e.page.update()
                    except Exception:
                        pass

                def update_progress(step: str, current: int, total: int):
                    """Päivitä progress-dialog"""
                    try:
                        if progress_dialog and progress_dialog.open:
                            progress_text.value = f"{step} {current}% valmiina"
                            if total > 0:
                                progress_bar.value = current / total
                            else:
                                progress_bar.value = None
                            e.page.update()
                    except Exception:
                        pass

                # Hae ticker-filtteri app-objektista
                ticker_filter = None
                ticker_list = None
                try:
                    ticker_mode = app.results_radio_group.value
                    ticker = (
                        app.results_ticker_field.value.strip().upper()
                        if app.results_ticker_field.value
                        else ""
                    )

                    if ticker_mode == "single" and ticker:
                        # Jos ticker sisältää pilkkuja, käsitellään se listana
                        if "," in ticker:
                            ticker_list = [
                                t.strip() for t in ticker.split(",") if t.strip()
                            ]
                            update_progress(
                                f"Suodatetaan {len(ticker_list)} tickeriä", 10, 100
                            )
                            print(f"🔍 Ticker-lista: {len(ticker_list)} tickeriä")
                        else:
                            ticker_filter = ticker
                            update_progress(
                                f"Suodatetaan ticker: {ticker_filter}", 10, 100
                            )
                            print(f"🔍 Ticker-suodatin: {ticker_filter}")
                    else:
                        update_progress("Generoidaan kaikille tickereille", 10, 100)
                        print("🌐 Haetaan kaikki tickerit")

                except Exception as ex:
                    print(f"Virhe ticker-filterin lukemisessa: {ex}")

                def show_modal_message(title: str, message: str):
                    """Näytä modaalinen dialogi tulokset-sivulla"""
                    try:
                        dialog = ft.AlertDialog(
                            modal=True,
                            title=ft.Text(title),
                            content=ft.Text(message),
                            actions=[
                                ft.TextButton(
                                    "OK",
                                    on_click=lambda _: app.close_dialog(dialog),
                                )
                            ],
                        )
                        if dialog not in app.page.overlay:
                            app.page.overlay.append(dialog)
                        dialog.open = True
                        app.page.update()
                    except Exception as err:
                        print(f"Dialogin näyttö epäonnistui: {err}")

                # Varmista että ticker löytyy analysis-tietokannasta ennen jatkamista
                tickers_to_check = []
                if ticker_filter:
                    tickers_to_check = [ticker_filter]
                elif ticker_list:
                    tickers_to_check = ticker_list

                if tickers_to_check:
                    try:
                        base = Path(__file__).resolve().parents[1]
                        analysis_db_path = base / "data" / "analysis.db"
                        missing_tickers = []

                        if analysis_db_path.exists():
                            with sqlite3.connect(analysis_db_path) as conn:
                                tables = [
                                    row[0]
                                    for row in conn.execute(
                                        "SELECT name FROM sqlite_master WHERE type='table'"
                                    ).fetchall()
                                ]
                                table_name = next(
                                    (
                                        t
                                        for t in (
                                            "analysis_findings",
                                            "analysis",
                                            "findings",
                                            "analysis_rows",
                                        )
                                        if t in tables
                                    ),
                                    None,
                                )

                                if table_name:
                                    info = conn.execute(
                                        f'PRAGMA table_info("{table_name}")'
                                    ).fetchall()
                                    lower_cols = {
                                        col[1].lower(): col[1] for col in info
                                    }
                                    ticker_col = (
                                        lower_cols.get("ticker")
                                        or lower_cols.get("osake")
                                        or lower_cols.get("symbol")
                                    )

                                    if ticker_col:
                                        # Tarkista jokainen ticker
                                        for check_ticker in tickers_to_check:
                                            res = conn.execute(
                                                f'SELECT 1 FROM "{table_name}" WHERE UPPER("{ticker_col}") = ? LIMIT 1',
                                                (check_ticker,),
                                            ).fetchone()
                                            if res is None:
                                                missing_tickers.append(check_ticker)
                        else:
                            missing_tickers = tickers_to_check

                        if missing_tickers:
                            if progress_dialog and progress_dialog.open:
                                close_progress_dialog()

                            if len(missing_tickers) == 1:
                                msg = f"Tickeriä {missing_tickers[0]} ei löytynyt analyysidatasta."
                            elif len(missing_tickers) <= 10:
                                msg = f"{len(missing_tickers)} tickeriä ei löytynyt analyysidatasta:\n{', '.join(missing_tickers)}"
                            else:
                                msg = f"{len(missing_tickers)} tickeriä ei löytynyt analyysidatasta:\n{', '.join(missing_tickers[:10])}... (+{len(missing_tickers)-10} muuta)"

                            print(f"❌ Puuttuvat tickerit: {missing_tickers}")
                            show_modal_message("⚠️ Tickereitä puuttuu", msg)
                            return
                    except Exception as ex:
                        print(f"Tickereiden tarkistus epäonnistui: {ex}")
                        if progress_dialog and progress_dialog.open:
                            close_progress_dialog()

                        show_modal_message(
                            "❌ Virhe",
                            "Tickereiden tarkistus epäonnistui. Tarkista analysis.db.",
                        )
                        return
                update_progress("Haetaan analyysit", 20, 100)

                base = Path(__file__).resolve().parents[1]
                analysis_db = base / "data" / "analysis.db"
                osake_db = base / "data" / "osakedata.db"
                excel_path = base / "data" / "results.xlsx"

                def fallback_progress(message, fraction):
                    try:
                        progress_value = min(max(fraction, 0.0), 1.0)
                        update_progress(message, int(progress_value * 100), 100)
                    except Exception:
                        pass

                # Jos ticker_list on asetettu, muodosta ticker_filter siitä
                final_ticker_filter = ticker_filter
                if ticker_list and not ticker_filter:
                    # Käytä ensimmäistä tickeriä filterinä tai None jos halutaan kaikki
                    # Tai voidaan välittää koko lista - riippuu _build_output_rows toteutuksesta
                    # Tarkistetaan miten _build_output_rows toimii ticker_list:n kanssa
                    final_ticker_filter = ticker_list  # Välitetään koko lista

                # Hae valitut kynttiläkuviot checkboxeista ja muunna numeroiksi
                selected_pattern_numbers = None
                try:
                    if hasattr(app, "results_checkboxes"):
                        selected_pattern_names = [
                            cb.label for cb in app.results_checkboxes if cb.value
                        ]
                        if selected_pattern_names:
                            # Muunna nimet numeroiksi (käänteinen mappaus ExcelExporterin PATTERN_NAMES:sta)
                            pattern_name_to_num = {
                                "downtrend": 0,
                                "Hammer": 1,
                                "Bullish Engulfing": 2,
                                "Piercing Pattern": 3,
                                "Three White Soldiers": 4,
                                "Morning Star": 5,
                                "Dragonfly Doji": 6,
                                "Bullish Divergence": 7,
                                "Bearish Divergence": 8,
                            }
                            selected_pattern_numbers = [
                                pattern_name_to_num.get(name)
                                for name in selected_pattern_names
                                if name in pattern_name_to_num
                            ]
                            print(
                                f"🔍 Kuviosuodatin: {len(selected_pattern_numbers)} kuviota valittu: {selected_pattern_numbers}"
                            )
                        else:
                            print("🌐 Ei kuviosuodatinta - käytetään kaikkia")
                except Exception as ex:
                    print(f"Virhe kuviosuodattimen lukemisessa: {ex}")

                # Vie tietokannasta Exceliin ExcelExporterilla
                update_progress("Viedään tuloksia Exceliin...", 80, 100)
                exporter = ExcelExporter(str(analysis_db))
                success, message = exporter.export_to_excel(
                    str(excel_path), selected_patterns=selected_pattern_numbers
                )

                if success:
                    update_progress("Valmis!", 100, 100)
                    progress_bar.value = 1
                    progress_title.value = "✅ Valmis!"
                    progress_text.value = (
                        "Excel-tiedosto 'data/results.xlsx' päivitetty onnistuneesti.\n"
                        "Paina OK sulkeaksesi."
                    )
                    progress_dialog.actions = [
                        ft.TextButton("OK", on_click=lambda _: close_progress_dialog())
                    ]
                    progress_dialog.actions_alignment = ft.MainAxisAlignment.END
                    print("✅ Excel-tiedosto päivitetty onnistuneesti!")

                    try:
                        progress_dialog.update()
                    except Exception:
                        e.page.update()
                    else:
                        e.page.update()

                else:
                    print(f"❌ Excel-tiedoston päivitys epäonnistui: {message}")
                    progress_title.value = "❌ Virhe"
                    progress_text.value = (
                        f"Excel-tiedoston päivitys epäonnistui.\n{message}\n"
                        "Paina OK sulkeaksesi."
                    )
                    progress_bar.value = None
                    progress_dialog.actions = [
                        ft.TextButton("OK", on_click=lambda _: close_progress_dialog())
                    ]
                    progress_dialog.actions_alignment = ft.MainAxisAlignment.END
                    try:
                        progress_dialog.update()
                    except Exception:
                        e.page.update()
                    else:
                        e.page.update()

            except Exception as ex:
                print(f"Virhe Excel-päivityksessä: {ex}")

                # Sulje progress-dialog jos avoinna
                if progress_dialog and progress_dialog.open:
                    progress_title.value = "❌ Kriittinen virhe"
                    progress_text.value = (
                        f"Excel-generoinnissa tapahtui virhe:\n{str(ex)}\n"
                        "Tarkista terminaali lisätietoja varten ja paina OK."
                    )
                    progress_bar.value = None
                    progress_dialog.actions = [
                        ft.TextButton("OK", on_click=lambda _: close_progress_dialog())
                    ]
                    progress_dialog.actions_alignment = ft.MainAxisAlignment.END
                    try:
                        progress_dialog.update()
                    except Exception:
                        e.page.update()
                    else:
                        e.page.update()

        # UUDET PAINIKKEET: Generoi tietokantaan + Vie Exceliin + Tyhjennä

        def generoi_tietokantaan_click(e):
            """Generoi tulokset tietokantaan"""
            progress_dialog = None
            progress_title = ft.Text("Generoidaan tuloksia tietokantaan")
            progress_text = ft.Text("Aloitetaan...")
            progress_bar = ft.ProgressBar(width=400, value=0)

            # Keskeytys-lippu
            cancel_flag = {"cancelled": False}

            try:

                def cancel_generation(e_cancel):
                    """Keskeytä generointi"""
                    cancel_flag["cancelled"] = True
                    progress_text.value = "Keskeytetään..."
                    e_cancel.page.update()

                progress_dialog = ft.AlertDialog(
                    modal=True,
                    title=progress_title,
                    content=ft.Column(
                        [
                            progress_text,
                            progress_bar,
                        ],
                        tight=True,
                        height=80,
                    ),
                    actions=[
                        ft.TextButton(
                            "Keskeytä",
                            on_click=cancel_generation,
                        )
                    ],
                )

                app.page.overlay.append(progress_dialog)
                progress_dialog.open = True
                e.page.update()

                def progress_callback(ticker, current, total):
                    """Päivitä progress bar ja tarkista keskeytys"""
                    try:
                        # Palauta True jos keskeytetty
                        if cancel_flag["cancelled"]:
                            return True

                        progress_text.value = (
                            f"Käsitellään: {ticker} ({current}/{total})"
                        )
                        progress_bar.value = current / total if total > 0 else 0
                        e.page.update()
                        return False
                    except Exception:
                        return False

                def run_generation():
                    # Lue ticker-suodatin
                    ticker_filter = None
                    try:
                        ticker_mode = app.results_radio_group.value
                        ticker_value = (
                            app.results_ticker_field.value.strip().upper()
                            if app.results_ticker_field.value
                            else ""
                        )

                        if ticker_mode == "single" and ticker_value:
                            # Pilkulla erotettu lista
                            if "," in ticker_value:
                                ticker_filter = [
                                    t.strip()
                                    for t in ticker_value.split(",")
                                    if t.strip()
                                ]
                            else:
                                ticker_filter = [ticker_value]
                    except Exception as ex:
                        print(f"Virhe ticker-suodattimen lukemisessa: {ex}")

                    # Lue pattern-suodatin
                    pattern_filter = None
                    try:
                        pattern_mapping = {
                            "downtrend": 0,
                            "Hammer": 1,
                            "Bullish Engulfing": 2,
                            "Piercing Pattern": 3,
                            "Three White Soldiers": 4,
                            "Morning Star": 5,
                            "Dragonfly Doji": 6,
                            "Bullish Divergence": 7,
                            "Bearish Divergence": 8,
                        }

                        selected_patterns = []
                        for cb in app.results_checkboxes:
                            if cb.value and cb.label in pattern_mapping:
                                selected_patterns.append(pattern_mapping[cb.label])

                        if selected_patterns:
                            pattern_filter = selected_patterns
                    except Exception as ex:
                        print(f"Virhe pattern-suodattimen lukemisessa: {ex}")

                    # Lue force_rebuild -asetus
                    force_rebuild = (
                        app.results_force_rebuild.value
                        if hasattr(app.results_force_rebuild, "value")
                        else False
                    )

                    # Lue divergence_combo_filter -asetus
                    divergence_combo_filter = (
                        app.results_divergence_combo_filter.value
                        if hasattr(app.results_divergence_combo_filter, "value")
                        else False
                    )

                    # Generoi suodattimilla
                    (
                        rows,
                        time_taken,
                        error,
                        feature_summary,
                        feature_error,
                    ) = generate_results_to_database(
                        app,
                        progress_callback,
                        ticker_filter=ticker_filter,
                        pattern_filter=pattern_filter,
                        divergence_combo_filter=divergence_combo_filter,
                        force_rebuild=force_rebuild,
                    )
                    if feature_error and not error:
                        error = feature_error

                    # Päivitä UI pääsäikeessä
                    try:
                        progress_dialog.open = False
                        e.page.update()

                        if error:
                            result_dialog = ft.AlertDialog(
                                title=ft.Text("Virhe"),
                                content=ft.Text(
                                    f"Tulosten generointi epäonnistui:\n{error}"
                                ),
                                actions=[
                                    ft.TextButton(
                                        "OK",
                                        on_click=lambda _: app.close_dialog(
                                            result_dialog
                                        ),
                                    )
                                ],
                            )
                        elif cancel_flag["cancelled"]:
                            result_dialog = ft.AlertDialog(
                                title=ft.Text("⚠️ Keskeytetty"),
                                content=ft.Text(
                                    f"Generointi keskeytetty käyttäjän toimesta\n"
                                    f"Generoitu {rows} riviä ennen keskeytystä\n"
                                    f"Aikaa kului: {time_taken:.2f}s"
                                ),
                                actions=[
                                    ft.TextButton(
                                        "OK",
                                        on_click=lambda _: app.close_dialog(
                                            result_dialog
                                        ),
                                    )
                                ],
                            )
                        else:
                            msg = (
                                f"Generoitu {rows} riviä tietokantaan\n"
                                f"Aikaa kului: {time_taken:.2f}s"
                            )
                            if feature_summary:
                                msg += (
                                    f"\nLisäfeaturet päivitetty {feature_summary.total_rows} riville"
                                )

                            result_dialog = ft.AlertDialog(
                                title=ft.Text("✅ Valmis!"),
                                content=ft.Text(msg),
                                actions=[
                                    ft.TextButton(
                                        "OK",
                                        on_click=lambda _: app.close_dialog(
                                            result_dialog
                                        ),
                                    )
                                ],
                            )

                        app.page.overlay.append(result_dialog)
                        result_dialog.open = True

                        # Päivitä metadata-näyttö
                        metadata = get_results_metadata(app)
                        if metadata and hasattr(app, "results_metadata_text"):
                            gen_time = metadata.get("generated_at", "")
                            total = metadata.get("total_rows", 0)
                            app.results_metadata_text.value = (
                                f"Tulokset generoitu: {gen_time} ({total} riviä)"
                            )

                        e.page.update()
                    except Exception as ex:
                        print(f"Error showing result: {ex}")

                threading.Thread(target=run_generation, daemon=True).start()

            except Exception as ex:
                if progress_dialog:
                    progress_dialog.open = False
                e.page.snack_bar = ft.SnackBar(ft.Text(f"Virhe: {ex}"), open=True)
                e.page.update()

        def vie_exceliin_click(e):
            """Avaa Excel-vienti dialogi valintoineen"""
            try:
                # Tarkista onko tuloksia
                metadata = get_results_metadata(app)
                if not metadata or metadata.get("total_rows", 0) == 0:
                    e.page.snack_bar = ft.SnackBar(
                        ft.Text(
                            "Ei tuloksia vietäväksi. Generoi ensin tulokset tietokantaan."
                        ),
                        open=True,
                    )
                    e.page.update()
                    return

                total_count = metadata.get("total_rows", 0)

                # Radio-painikkeiden tila
                export_mode = ft.Ref[ft.RadioGroup]()
                sample_size_field = ft.Ref[ft.TextField]()

                def on_mode_change(e_mode):
                    """Aktivoi/deaktivoi määräkenttä."""
                    is_random = export_mode.current.value == "random"
                    sample_size_field.current.disabled = not is_random
                    sample_size_field.current.update()

                def close_dialog(e_close):
                    """Sulje dialogi."""
                    export_dlg.open = False
                    e.page.update()

                def export_action(e_export):
                    """Suorita Excel-vienti valinnalla."""
                    mode = export_mode.current.value

                    # Määritä ID-filtteri satunnaisotannalle
                    id_filter = None
                    sample_info = ""

                    if mode == "random":
                        try:
                            requested_count = int(
                                sample_size_field.current.value or "0"
                            )
                            if requested_count <= 0:
                                e.page.snack_bar = ft.SnackBar(
                                    ft.Text("Anna positiivinen määrä"), open=True
                                )
                                e.page.update()
                                return

                            # Hae kaikki ID:t tietokannasta
                            from analysis.database_manager import DatabaseManager

                            db_mgr = DatabaseManager("data/analysis.db")
                            all_results = db_mgr.get_results_data()

                            # Tarkista ylimitoitus
                            if requested_count > len(all_results):
                                sample_info = f" (pyydetty {requested_count}, saatavilla {len(all_results)})"
                                # Vie kaikki
                            else:
                                # Satunnaisotanta ID:istä
                                import random

                                sampled_results = random.sample(
                                    all_results, requested_count
                                )
                                id_filter = [
                                    r.get("id") for r in sampled_results if r.get("id")
                                ]
                                sample_info = (
                                    f" (arvottu {requested_count}/{len(all_results)})"
                                )

                        except ValueError:
                            e.page.snack_bar = ft.SnackBar(
                                ft.Text("Virheellinen määrä"), open=True
                            )
                            e.page.update()
                            return

                    # Sulje dialogi
                    close_dialog(None)

                    # Kutsu varsinaista export-funktiota
                    vie_exceliin_with_filters(e, id_filter, sample_info)

                # Luo dialogi
                export_dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("📊 Vie Exceliin"),
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"Tuloksia tietokannassa: {total_count}",
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Divider(),
                                ft.RadioGroup(
                                    ref=export_mode,
                                    value="all",
                                    on_change=on_mode_change,
                                    content=ft.Column(
                                        [
                                            ft.Radio(
                                                value="all",
                                                label=f"Vie kaikki {total_count} tapahtumaa",
                                            ),
                                            ft.Radio(
                                                value="random",
                                                label="Satunnainen osajoukko:",
                                            ),
                                        ]
                                    ),
                                ),
                                ft.Container(
                                    content=ft.TextField(
                                        ref=sample_size_field,
                                        label="Tapahtumien määrä",
                                        hint_text=f"1 - {total_count}",
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        disabled=True,
                                        width=200,
                                    ),
                                    padding=ft.padding.only(left=30),
                                ),
                            ],
                            tight=True,
                            spacing=10,
                        ),
                        width=400,
                        height=200,
                    ),
                    actions=[
                        ft.TextButton("Peruuta", on_click=close_dialog),
                        ft.ElevatedButton(
                            "Vie Excel",
                            icon=ft.Icons.FILE_DOWNLOAD,
                            on_click=export_action,
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )

                # Näytä dialogi
                app.page.overlay.append(export_dlg)
                export_dlg.open = True
                e.page.update()

            except Exception as ex:
                e.page.snack_bar = ft.SnackBar(ft.Text(f"Virhe: {ex}"), open=True)
                e.page.update()

        def vie_exceliin_with_filters(e, id_filter=None, sample_info=""):
            """Vie results_data Exceliin progress dialogilla (sisäinen funktio)"""
            try:
                # Tarkista onko tuloksia
                metadata = get_results_metadata(app)
                if not metadata or metadata.get("total_rows", 0) == 0:
                    e.page.snack_bar = ft.SnackBar(
                        ft.Text(
                            "Ei tuloksia vietäväksi. Generoi ensin tulokset tietokantaan."
                        ),
                        open=True,
                    )
                    e.page.update()
                    return

                # Keskeytys-lippu
                cancel_flag = {"cancelled": False}

                def cancel_export(e_cancel):
                    """Keskeytä Excel-vienti"""
                    cancel_flag["cancelled"] = True
                    progress_text.value = "Keskeytetään..."
                    e_cancel.page.update()

                # Luo progress dialog
                progress_title = ft.Text("Viedään tuloksia Exceliin")
                progress_text = ft.Text("Valmistellaan...")
                progress_bar = ft.ProgressBar(width=400, value=None)

                progress_dialog = ft.AlertDialog(
                    modal=True,
                    title=progress_title,
                    content=ft.Column(
                        [
                            progress_text,
                            progress_bar,
                        ],
                        tight=True,
                        height=80,
                    ),
                    actions=[
                        ft.TextButton(
                            "Keskeytä",
                            on_click=cancel_export,
                        )
                    ],
                )

                app.page.overlay.append(progress_dialog)
                progress_dialog.open = True
                e.page.update()

                # Hae suodattimet
                pattern_mapping = {
                    "downtrend": 0,
                    "Hammer": 1,
                    "Bullish Engulfing": 2,
                    "Piercing Pattern": 3,
                    "Three White Soldiers": 4,
                    "Morning Star": 5,
                    "Dragonfly Doji": 6,
                    "Bullish Divergence": 7,
                    "Bearish Divergence": 8,
                }

                selected_patterns = []
                for cb in app.results_checkboxes:
                    if cb.value and cb.label in pattern_mapping:
                        selected_patterns.append(pattern_mapping[cb.label])

                if not selected_patterns:
                    selected_patterns = None

                ticker_filter = None
                try:
                    ticker_mode = app.results_radio_group.value
                    ticker_value = (
                        app.results_ticker_field.value.strip().upper()
                        if app.results_ticker_field.value
                        else ""
                    )

                    if ticker_mode == "single" and ticker_value:
                        if "," in ticker_value:
                            ticker_filter = [
                                t.strip() for t in ticker_value.split(",") if t.strip()
                            ]
                        else:
                            ticker_filter = [ticker_value]
                except Exception as ex:
                    print(f"Virhe ticker-suodattimen lukemisessa: {ex}")

                # Lue divergence_combo_filter
                divergence_combo_filter = (
                    app.results_divergence_combo_filter.value
                    if hasattr(app.results_divergence_combo_filter, "value")
                    else False
                )

                # Jos divergence_combo_filter on päällä JA ei ole id_filteriä random samplesta,
                # suodata ID:t divergenssi-yhdistelmille
                if divergence_combo_filter and id_filter is None:
                    try:
                        from analysis.database_manager import DatabaseManager

                        db_mgr = DatabaseManager("data/analysis.db")
                        all_results = db_mgr.get_results_data()

                        combo_pairs = db_mgr.get_divergence_combo_pairs()
                        combo_ids = [
                            result.get("id")
                            for result in all_results
                            if result.get("id")
                            and (
                                result.get("ticker"),
                                result.get("date"),
                            )
                            in combo_pairs
                        ]

                        if combo_ids:
                            id_filter = combo_ids
                            print(
                                f"🔍 Divergenssi-yhdistelmä: {len(id_filter)} tapahtumaa"
                            )
                        else:
                            print("⚠️ Ei divergenssi-yhdistelmiä löytynyt")
                    except Exception as ex:
                        print(f"Virhe divergenssi-yhdistelmä suodattimessa: {ex}")

                # Progress callback
                def progress_callback(current, total):
                    """Päivitä progress ja tarkista keskeytys"""
                    try:
                        if cancel_flag["cancelled"]:
                            return True

                        progress_text.value = f"Viedään riviä {current}/{total}..."
                        progress_bar.value = current / total if total > 0 else 0
                        e.page.update()
                        return False
                    except Exception:
                        return False

                # Päivitä progress
                progress_text.value = "Viedään tietoja Exceliin..."
                progress_bar.value = 0.1
                e.page.update()

                # Käytä data/results.xlsx oletuspolkuna
                from pathlib import Path

                base = Path(__file__).resolve().parents[1]
                excel_path = base / "data" / "results.xlsx"

                # Vie Excel
                exporter = ExcelExporter("data/analysis.db")
                success, message = exporter.export_to_excel(
                    str(excel_path),
                    selected_patterns=selected_patterns,
                    ticker_filter=ticker_filter,
                    id_filter=id_filter,  # Lisätty ID-suodatin
                    progress_callback=progress_callback,
                )

                # Sulje progress ja näytä tulos
                progress_dialog.open = False
                e.page.update()

                if success:
                    result_dialog = ft.AlertDialog(
                        title=ft.Text("✅ Valmis!"),
                        content=ft.Text(
                            f"{message}{sample_info}\n\nTiedosto tallennettu: data/results.xlsx"
                        ),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda _: app.close_dialog(result_dialog),
                            )
                        ],
                    )
                elif cancel_flag["cancelled"]:
                    result_dialog = ft.AlertDialog(
                        title=ft.Text("⚠️ Keskeytetty"),
                        content=ft.Text(f"Excel-vienti keskeytetty:\n{message}"),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda _: app.close_dialog(result_dialog),
                            )
                        ],
                    )
                else:
                    result_dialog = ft.AlertDialog(
                        title=ft.Text("❌ Virhe"),
                        content=ft.Text(f"Excel-vienti epäonnistui:\n{message}"),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda _: app.close_dialog(result_dialog),
                            )
                        ],
                    )

                app.page.overlay.append(result_dialog)
                result_dialog.open = True
                e.page.update()

            except Exception as ex:
                # Sulje progress jos avoinna
                try:
                    if progress_dialog and progress_dialog.open:
                        progress_dialog.open = False
                        e.page.update()
                except Exception:
                    pass

                e.page.snack_bar = ft.SnackBar(ft.Text(f"Virhe: {ex}"), open=True)
                e.page.update()

        def tyhjenna_tulokset_click(e):
            """Tyhjennä results_data vahvistuksen jälkeen"""

            def confirm_clear(confirm_e):
                if confirm_e.control.text == "Kyllä":
                    deleted, error = clear_results_database(app)

                    if error:
                        e.page.snack_bar = ft.SnackBar(
                            ft.Text(f"Virhe: {error}"), open=True
                        )
                    else:
                        e.page.snack_bar = ft.SnackBar(
                            ft.Text(f"✅ Poistettu {deleted} riviä"), open=True
                        )

                        # Päivitä metadata-näyttö
                        if hasattr(app, "results_metadata_text"):
                            app.results_metadata_text.value = "Ei generoituja tuloksia"

                app.close_dialog(confirm_dialog)
                e.page.update()

            confirm_dialog = ft.AlertDialog(
                title=ft.Text("Vahvista tyhjennys"),
                content=ft.Text(
                    "Haluatko varmasti tyhjentää kaikki generoidut tulokset tietokannasta?"
                ),
                actions=[
                    ft.TextButton("Kyllä", on_click=confirm_clear),
                    ft.TextButton(
                        "Peruuta", on_click=lambda _: app.close_dialog(confirm_dialog)
                    ),
                ],
            )

            app.page.overlay.append(confirm_dialog)
            confirm_dialog.open = True
            e.page.update()

        # Luo uudet painikkeet
        generoi_db_btn = ft.ElevatedButton(
            "� Generoi tulokset",
            icon=ft.Icons.STORAGE,
            bgcolor=ft.colors.BLUE_700,
            color=ft.colors.WHITE,
            on_click=generoi_tietokantaan_click,
            width=220,
            tooltip="Luo tulokset analysis_findings taulusta ja tallenna results_data tauluun. Inkrementaalinen päivitys - lisää vain uudet rivit.",
        )

        vie_excel_btn = ft.ElevatedButton(
            "📊 Vie Exceliin",
            icon=ft.Icons.TABLE_CHART,
            bgcolor=ft.colors.GREEN_600,
            color=ft.colors.WHITE,
            on_click=vie_exceliin_click,
            width=220,
            tooltip="Vie results_data taulun tulokset Excel-tiedostoon. Voit valita mitkä kynttiläkuviot viedään.",
        )

        tyhjenna_btn = ft.ElevatedButton(
            "🗑️ Tyhjennä tulokset",
            icon=ft.Icons.DELETE_OUTLINE,
            bgcolor=ft.colors.RED_700,
            color=ft.colors.WHITE,
            on_click=tyhjenna_tulokset_click,
            width=220,
            tooltip="Tyhjennä kaikki generoidut tulokset results_data taulusta. Ei poista analysis_findings dataa.",
        )

        # Metadata-näyttö
        metadata = get_results_metadata(app)
        if metadata:
            gen_time = metadata.get("generated_at", "")
            total = metadata.get("total_rows", 0)
            metadata_text = f"Tulokset generoitu: {gen_time} ({total} riviä)"
        else:
            metadata_text = "Ei generoituja tuloksia"

        app.results_metadata_text = ft.Text(
            metadata_text,
            size=12,
            color=ft.colors.GREY_700,
            italic=True,
        )

        # Vanha painike (pidetään vielä)
        generate_btn = ft.ElevatedButton(
            "🚀 Generoi tulokset (vanha)",
            icon=ft.Icons.TABLE_CHART,
            bgcolor=ft.colors.ORANGE_600,
            color=ft.colors.WHITE,
            disabled=False,
            on_click=paivita_excel_cache_click,  # Käytä uutta funktiota
            width=220,
            visible=False,  # Piilotetaan toistaiseksi
        )
    except Exception as ex:
        # Jos vanha generate-funktio ei toimi, luodaan placeholder-painikkeet
        print(f"Warning: Old generate function failed: {ex}")
        generoi_db_btn = ft.ElevatedButton(
            "� Generoi tulokset",
            icon=ft.Icons.STORAGE,
            bgcolor=ft.colors.BLUE_700,
            color=ft.colors.WHITE,
            disabled=True,
            tooltip="Virhe ladattaessa: " + str(ex),
            width=220,
        )
        vie_excel_btn = ft.ElevatedButton(
            "📊 Vie Exceliin",
            icon=ft.Icons.TABLE_CHART,
            bgcolor=ft.colors.GREEN_600,
            color=ft.colors.WHITE,
            disabled=True,
            tooltip="Ei käytettävissä - virhe ladattaessa",
            width=220,
        )
        tyhjenna_btn = ft.ElevatedButton(
            "🗑️ Tyhjennä tulokset",
            icon=ft.Icons.DELETE_OUTLINE,
            bgcolor=ft.colors.RED_700,
            color=ft.colors.WHITE,
            disabled=True,
            tooltip="Ei käytettävissä - virhe ladattaessa",
            width=220,
        )
        app.results_metadata_text = ft.Text(
            "Virhe ladattaessa", size=12, color=ft.colors.RED
        )

    app.results_banner = ft.Text(value="", color=ft.colors.BLUE_600)

    view = ft.View(
        "/tulokset",
        [
            app.create_appbar(),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Tulokset",
                            size=32,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.ORANGE_700,
                        ),
                        ft.Text(
                            "Generoi analyysitulokset CSV-muotoon ja tarkastele niitä.",
                            size=16,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Container(height=16),
                        # Metadata-näyttö
                        ft.Row(
                            [app.results_metadata_text],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Container(height=8),
                        # Uudet painikkeet
                        ft.Row(
                            [
                                generoi_db_btn,
                                vie_excel_btn,
                                tyhjenna_btn,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=20,
                        ),
                        ft.Container(height=8),
                        # Generointi-asetus heti painikkeen alle
                        ft.Row(
                            [app.results_force_rebuild],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Container(content=app.results_banner),
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
                                                app.results_select_all,
                                                ft.Divider(
                                                    height=1, color=ft.Colors.GREY_300
                                                ),
                                                ft.Column(
                                                    app.results_checkboxes, spacing=12
                                                ),
                                                ft.Divider(
                                                    height=1, color=ft.Colors.GREY_300
                                                ),
                                                app.results_divergence_combo_filter,
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
                                                        app.results_radio_group,
                                                        ft.Row(
                                                            [
                                                                app.results_ticker_field,
                                                                app.results_load_csv_button,
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
                                                        app.results_date_radio_group,
                                                        ft.Row(
                                                            [
                                                                ft.ElevatedButton(
                                                                    "Ota aikaväli käyttöön",
                                                                    on_click=lambda e: (
                                                                        setattr(
                                                                            app.results_date_radio_group,
                                                                            "value",
                                                                            "range",
                                                                        ),
                                                                        app.results_date_radio_group.on_change(
                                                                            None
                                                                        ),
                                                                        app.page.update(),
                                                                    ),
                                                                    width=220,
                                                                    bgcolor=ft.Colors.ORANGE_300,
                                                                    color=ft.Colors.WHITE,
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
                                                                        app.results_start_date,
                                                                        app.results_start_date_text,
                                                                    ]
                                                                ),
                                                                ft.Column(
                                                                    [
                                                                        ft.Text(
                                                                            "Loppupäivä"
                                                                        ),
                                                                        app.results_end_date,
                                                                        app.results_end_date_text,
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
                                        ft.Card(
                                            content=ft.Container(
                                                content=ft.Column(
                                                    [
                                                        ft.Text(
                                                            "Laskutrendi-suodatin",
                                                            size=18,
                                                            weight=ft.FontWeight.BOLD,
                                                            color=ft.Colors.ORANGE_600,
                                                        ),
                                                        app.results_downtrend_filter,
                                                        ft.Container(height=8),
                                                        ft.Text(
                                                            "Suodattimen asetukset:",
                                                            size=14,
                                                            weight=ft.FontWeight.W_500,
                                                            color=ft.Colors.GREY_700,
                                                        ),
                                                        ft.Row(
                                                            [
                                                                ft.Text(
                                                                    "Min. lasku:",
                                                                    width=80,
                                                                ),
                                                                app.results_min_decline_percent,
                                                                ft.Text("%", width=20),
                                                            ],
                                                            spacing=5,
                                                        ),
                                                        app.results_ma_filter,
                                                        app.results_volume_filter,
                                                        ft.Container(height=8),
                                                        ft.Divider(
                                                            height=1,
                                                            color=ft.Colors.GREY_300,
                                                        ),
                                                        ft.Text(
                                                            "📊 Kriteerit:",
                                                            size=12,
                                                            color=ft.Colors.GREY_600,
                                                        ),
                                                        ft.Text(
                                                            "• t-10 > t-5 > t-2 > t0 (porrastava lasku)",
                                                            size=11,
                                                            color=ft.Colors.GREY_600,
                                                        ),
                                                        ft.Text(
                                                            "• MA(5) < MA(10) (jos MA-suodatin)",
                                                            size=11,
                                                            color=ft.Colors.GREY_600,
                                                        ),
                                                        ft.Text(
                                                            "• Volyymi > 1.2x (jos volyymi-suodatin)",
                                                            size=11,
                                                            color=ft.Colors.GREY_600,
                                                        ),
                                                    ],
                                                    horizontal_alignment=ft.CrossAxisAlignment.START,
                                                    spacing=8,
                                                ),
                                                padding=20,
                                                bgcolor=ft.Colors.GREY_50,
                                                border_radius=8,
                                                width=420,
                                            ),
                                            elevation=2,
                                        ),
                                    ]
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=40,
                        ),
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

    return view


def show_results_csv(app, e):
    from analysis.logger import setup_logger

    logger = setup_logger()
    csv_path = os.path.join(
        os.path.dirname(__file__), "..", "analysis", "analysis_results.csv"
    )
    csv_path = os.path.normpath(csv_path)
    if not os.path.exists(csv_path):
        sb = ft.SnackBar(
            ft.Text("ℹ️ CSV-tiedostoa ei löytynyt.", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.ORANGE_600,
            duration=2000,
        )
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
        logger.info(
            "analysis_results.csv not found when attempting to show results CSV (results.view)"
        )
        return
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as ex:
        logger.exception("Virhe avattaessa CSV-tiedostoa (results.view)")
        sb = ft.SnackBar(
            ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE),
            bgcolor=ft.Colors.RED_600,
            duration=3000,
        )
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
        return

    content_control = ft.Text(content, selectable=True)

    save_button = ft.ElevatedButton(
        "Tallenna CSV",
        icon=ft.Icons.FILE_DOWNLOAD,
        on_click=lambda ev: (
            setattr(
                app.file_picker,
                "on_result",
                lambda ev2: save_csv_from_analysis(app, ev2, csv_path),
            ),
            app.file_picker.save_file(),
        ),
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Analyysin CSV-tulokset"),
        content=ft.Column([content_control], tight=True),
        actions=[
            save_button,
            ft.TextButton("Sulje", on_click=lambda _: app.close_dialog(dlg)),
        ],
    )
    if dlg not in app.page.overlay:
        app.page.overlay.append(dlg)
    dlg.open = True
    app.page.update()


def save_csv_from_analysis(app, e, src_path: str):
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
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
    except Exception as ex:
        from analysis.logger import setup_logger

        logger = setup_logger()
        logger.exception("Virhe tallennettaessa CSV:ää (results.view)")
        sb = ft.SnackBar(
            ft.Text(f"❌ Virhe tallennuksessa: {ex}"),
            bgcolor=ft.Colors.RED_600,
            duration=3000,
        )
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
