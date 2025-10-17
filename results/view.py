import flet as ft
import datetime
import os
import sqlite3
import threading

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
            return datetime.datetime.strptime(s, '%Y-%m-%d').date()
        except Exception:
            return None


def create_results_view(app) -> ft.View:
    """Builds and returns the /tulokset ft.View and wires handlers to use
    functions defined in this module. The `app` parameter is the
    RawCandleApp instance from main.py (we use app.page, app.file_picker, ...).
    """
    # controls
    app.results_checkboxes = [
        ft.Checkbox(label="Hammer", value=False),
        ft.Checkbox(label="Bullish Engulfing", value=False),
        ft.Checkbox(label="Piercing Pattern", value=False),
        ft.Checkbox(label="Three White Soldiers", value=False),
        ft.Checkbox(label="Morning Star", value=False),
        ft.Checkbox(label="Dragonfly Doji", value=False),
    ]
    app.results_ticker_field = ft.TextField(
        label="Osakkeen ticker (esim. AAPL)",
        width=250,
        hint_text="Jätä tyhjäksi analysoidaksesi kaikki",
    )
    app.results_radio_group = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(label="Analysoi annettu ticker", value="single"),
            ft.Radio(label="Analysoi kaikki osakkeet", value="all"),
        ], spacing=20),
        value="single"
    )
    app.results_date_radio_group = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(label="Kaikki päivät", value="all"),
            ft.Radio(label="Valitse aikaväli", value="range"),
        ], spacing=20),
        value="all"
    )
    app.results_start_date = ft.DatePicker(disabled=True, visible=False)
    app.results_end_date = ft.DatePicker(disabled=True, visible=False)
    app.results_start_date_text = ft.TextField(label="Alkupäivä (YYYY-MM-DD)", width=200, visible=False, hint_text="esim. 2025-01-31")
    app.results_end_date_text = ft.TextField(label="Loppupäivä (YYYY-MM-DD)", width=200, visible=False, hint_text="esim. 2025-06-30")

    def on_start_text_change(e):
        v = app.results_start_date_text.value.strip() if app.results_start_date_text.value else ''
        d = try_parse_date(v)
        if d:
            try:
                app.results_start_date.value = d
                app.results_start_date.update()
            except Exception:
                pass

    def on_end_text_change(e):
        v = app.results_end_date_text.value.strip() if app.results_end_date_text.value else ''
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
    # Buttons are currently inactive; handlers removed until user specifies behavior.
    generate_btn = ft.ElevatedButton(
        "Generoi CSV",
        icon=ft.Icons.FILE_UPLOAD,
        bgcolor=ft.colors.ORANGE_400,
        color=ft.colors.WHITE,
        disabled=True,
        tooltip="Ei vielä käytössä",
        width=220,
    )
    show_btn = ft.ElevatedButton(
        "Näytä CSV",
        icon=ft.Icons.VISIBILITY,
        bgcolor=ft.colors.BLUE_600,
        color=ft.colors.WHITE,
        disabled=True,
        tooltip="Ei vielä käytössä",
        width=220,
    )
    app.results_banner = ft.Text(value="", color=ft.colors.BLUE_600)

    view = ft.View(
        "/tulokset",
        [
            app.create_appbar(),
            ft.Container(
                content=ft.Column([
                    ft.Text("Tulokset", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700),
                    ft.Text("Generoi analyysitulokset CSV-muotoon ja tarkastele niitä.", size=16, color=ft.Colors.GREY_600),
                    ft.Container(height=16),
                    ft.Row([generate_btn, show_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
                    ft.Container(content=app.results_banner),
                    ft.Divider(height=30, color=ft.Colors.TRANSPARENT),
                    ft.Row([
                        ft.Card(
                            content=ft.Container(
                                content=ft.Column([
                                    ft.Text("Analyysityypit", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_600),
                                    ft.Column(app.results_checkboxes, spacing=12),
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
                                        app.results_radio_group,
                                        app.results_ticker_field,
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
                                            app.results_date_radio_group,
                                            ft.Row([
                                                ft.ElevatedButton(
                                                    "Ota aikaväli käyttöön",
                                                    on_click=lambda e: (setattr(app.results_date_radio_group, 'value', 'range'),
                                                                       app.results_date_radio_group.on_change(None),
                                                                       app.page.update()),
                                                    width=220,
                                                    bgcolor=ft.Colors.ORANGE_300,
                                                    color=ft.Colors.WHITE,
                                                ),
                                            ], alignment=ft.MainAxisAlignment.START),
                                            ft.Row([
                                                    ft.Column([ft.Text('Alkupäivä'), app.results_start_date, app.results_start_date_text]),
                                                    ft.Column([ft.Text('Loppupäivä'), app.results_end_date, app.results_end_date_text]),
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
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=30, scroll=ft.ScrollMode.AUTO, expand=True),
                padding=40,
                expand=True,
            ),
        ],
        vertical_alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return view


def start_results_generation(app, e):
    # Delegates to the existing analysis runner and print_results module.
    from analysis.run_analysis import run_candlestick_analysis
    from analysis.print_results import print_analysis_results
    from analysis.logger import setup_logger

    logger = setup_logger()
    logger.info("start_results_generation called (results.view)")

    sb = ft.SnackBar(ft.Text("🔄 Generoidaan CSV...", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_600, duration=1500)
    if sb not in app.page.overlay:
        app.page.overlay.append(sb)
    sb.open = True
    app.page.update()

    selected_patterns = [cb.label for cb in app.results_checkboxes if cb.value]
    if not selected_patterns:
        dlg = ft.AlertDialog(title=ft.Text("Valitse vähintään yksi analyysi!"))
        if dlg not in app.page.overlay:
            app.page.overlay.append(dlg)
        dlg.open = True
        app.page.update()
        return

    ticker_mode = app.results_radio_group.value
    ticker = app.results_ticker_field.value.strip().upper()
    if ticker_mode == 'single' and not ticker:
        dlg = ft.AlertDialog(title=ft.Text("Syötä osakkeen ticker!"))
        if dlg not in app.page.overlay:
            app.page.overlay.append(dlg)
        dlg.open = True
        app.page.update()
        return
    if ticker_mode == 'all':
        ticker = None

    date_mode = app.results_date_radio_group.value
    if date_mode == 'range':
        sd = app.results_start_date.value
        ed = app.results_end_date.value
        if sd is None or ed is None or sd > ed:
            dlg = ft.AlertDialog(title=ft.Text("Täytä kelvollinen aikaväli."))
            if dlg not in app.page.overlay:
                app.page.overlay.append(dlg)
            dlg.open = True
            app.page.update()
            return
        start_date = sd.isoformat()
        end_date = ed.isoformat()
    else:
        start_date = None
        end_date = None

    def worker():
        try:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'osakedata.db')
            db_path = os.path.normpath(db_path)
            if ticker is None:
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT osake FROM osakedata ORDER BY osake")
                    rows = [r[0] for r in cur.fetchall()]
                results = {}
                for idx, t in enumerate(rows):
                    res = run_candlestick_analysis(db_path, t, selected_patterns, start_date, end_date)
                    for k, v in res.items():
                        results[k] = results.get(k, []) + v
            else:
                results = run_candlestick_analysis(db_path, ticker, selected_patterns, start_date, end_date)

            data_dir = os.path.join(os.path.dirname(__file__), '..', 'analysis')
            data_dir = os.path.normpath(data_dir)
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
                app.results_banner.value = banner
                app.results_banner.color = ft.Colors.GREEN_600
                app.page.update()
            except Exception:
                pass

            logger.info(f"Results generation done (results.view): {ticker} - {str(text_msg)[:200]}")
            if csv_path:
                logger.info(f"Results CSV written: {csv_path}")

        except Exception as ex:
            logger.exception("Virhe generoitaessa tuloksia (results.view)")
            sb2 = ft.SnackBar(ft.Text(f"❌ Virhe generoitaessa: {ex}", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, duration=3000)
            if sb2 not in app.page.overlay:
                app.page.overlay.append(sb2)
            sb2.open = True
            app.page.update()

    threading.Thread(target=worker, daemon=True).start()


def show_results_csv(app, e):
    from analysis.logger import setup_logger
    logger = setup_logger()
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'analysis_results.csv')
    csv_path = os.path.normpath(csv_path)
    if not os.path.exists(csv_path):
        sb = ft.SnackBar(ft.Text("ℹ️ CSV-tiedostoa ei löytynyt.", color=ft.Colors.WHITE), bgcolor=ft.Colors.ORANGE_600, duration=2000)
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
        logger.info("analysis_results.csv not found when attempting to show results CSV (results.view)")
        return
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as ex:
        logger.exception("Virhe avattaessa CSV-tiedostoa (results.view)")
        sb = ft.SnackBar(ft.Text(f"❌ Virhe tiedostoa avattaessa: {ex}", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, duration=3000)
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
        return

    content_control = ft.Text(content, selectable=True)

    save_button = ft.ElevatedButton(
        "Tallenna CSV",
        icon=ft.Icons.FILE_DOWNLOAD,
        on_click=lambda ev: (setattr(app.file_picker, 'on_result', lambda ev2: save_csv_from_analysis(app, ev2, csv_path)), app.file_picker.save_file()),
    )

    dlg = ft.AlertDialog(
        title=ft.Text('Analyysin CSV-tulokset'),
        content=ft.Column([content_control], tight=True),
        actions=[
            save_button,
            ft.TextButton('Sulje', on_click=lambda _: app.close_dialog(dlg)),
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
        with open(src_path, 'r', encoding='utf-8') as src:
            data = src.read()
        with open(e.path, 'w', encoding='utf-8') as dst:
            dst.write(data)
        sb = ft.SnackBar(ft.Text(f"✅ CSV tallennettu: {e.path}"), bgcolor=ft.Colors.GREEN_600, duration=2000)
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
    except Exception as ex:
        from analysis.logger import setup_logger
        logger = setup_logger()
        logger.exception("Virhe tallennettaessa CSV:ää (results.view)")
        sb = ft.SnackBar(ft.Text(f"❌ Virhe tallennuksessa: {ex}"), bgcolor=ft.Colors.RED_600, duration=3000)
        if sb not in app.page.overlay:
            app.page.overlay.append(sb)
        sb.open = True
        app.page.update()
