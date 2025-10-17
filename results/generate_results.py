import threading
import sqlite3
import pandas as pd
import csv
from pathlib import Path
import traceback

import flet as ft


def _identify_columns(cur, table_name: str):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table_name})").fetchall()]
    lower = {c.lower(): c for c in cols}
    return cols, lower


def paivita_results_csv(page: ft.Page):
    """Starts a background job that builds/updates data/results.csv from
    analysis/analysis.db and data/osakedata.db.

    Behaviour:
    - Skips analysis rows for which we can't find a full t-1, t0, t1 sequence
    - Appends to data/results.csv, creating it (with header) if missing
    - Shows a SnackBar on completion (green) or on error (red)
    """

    def worker():
        try:
            base = Path(__file__).resolve().parents[1]
            analysis_db = base / 'analysis' / 'analysis.db'
            osake_db = base / 'data' / 'osakedata.db'
            csv_path = base / 'data' / 'results.csv'

            if not analysis_db.exists():
                sb = ft.SnackBar(ft.Text("❌ analysis.db ei löytynyt."), bgcolor=ft.Colors.RED_600, duration=3000)
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return
            if not osake_db.exists():
                sb = ft.SnackBar(ft.Text("❌ osakedata.db ei löytynyt."), bgcolor=ft.Colors.RED_600, duration=3000)
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return

            # Read analysis rows. Try common table/column name variants.
            with sqlite3.connect(analysis_db) as aconn:
                acur = aconn.cursor()
                # find a suitable table name
                tbls = [r[0] for r in acur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                candidates = ['analysis', 'analysis_findings', 'findings', 'analysis_rows']
                table_name = None
                for c in candidates:
                    if c in tbls:
                        table_name = c
                        break
                if table_name is None:
                    # fallback: pick first table that looks like it has date and ticker-like columns
                    for t in tbls:
                        info = acur.execute(f"PRAGMA table_info({t})").fetchall()
                        cols = [r[1].lower() for r in info]
                        if any(x in cols for x in ('date', 'pvm')) and any(x in cols for x in ('ticker', 'osake', 'symbol')):
                            table_name = t
                            break
                if table_name is None:
                    raise RuntimeError('analysis table not found in analysis.db')

                # introspect columns to pick date, ticker and pattern columns
                info = acur.execute(f"PRAGMA table_info({table_name})").fetchall()
                col_names = [r[1] for r in info]
                lower = {c.lower(): c for c in col_names}
                date_col = lower.get('date') or lower.get('pvm') or lower.get('pvm')
                ticker_col_a = lower.get('ticker') or lower.get('osake') or lower.get('symbol')
                pattern_col = lower.get('kynttila') or lower.get('pattern') or lower.get('pattern_name') or lower.get('kyntti')
                if not date_col or not ticker_col_a:
                    raise RuntimeError(f'Cannot find date/ticker columns in table {table_name}: {col_names}')

                q = f"SELECT \"{date_col}\", \"{ticker_col_a}\""
                if pattern_col:
                    q += f", \"{pattern_col}\""
                q += f" FROM \"{table_name}\""
                acur.execute(q)
                rows = acur.fetchall()

            if not rows:
                sb = ft.SnackBar(ft.Text("ℹ️ Ei rivejä analyysitietokannassa."), bgcolor=ft.Colors.ORANGE_600, duration=2000)
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return

            # group by ticker for per-ticker DB reads
            by_ticker = {}
            for rec in rows:
                if len(rec) == 3:
                    date, ticker, kynttila = rec
                elif len(rec) == 2:
                    date, ticker = rec
                    kynttila = ''
                else:
                    # unexpected shape
                    continue
                if not ticker:
                    continue
                by_ticker.setdefault(str(ticker), []).append((str(date), kynttila))

            output_rows = []

            # For each ticker, read osakedata once into pandas and process
            with sqlite3.connect(osake_db) as oconn:
                ocur = oconn.cursor()
                # check schema
                cols, lower = _identify_columns(ocur, 'osakedata')
                # determine column names
                ticker_col = lower.get('osake') or lower.get('ticker') or lower.get('symbol')
                pvm_col = lower.get('pvm') or lower.get('date') or lower.get('pvm')
                open_col = lower.get('open')
                high_col = lower.get('high')
                low_col = lower.get('low')
                close_col = lower.get('close')

                if not ticker_col or not pvm_col or not open_col or not high_col or not low_col or not close_col:
                    sb = ft.SnackBar(ft.Text("❌ osakedata-taulussa puuttuu odotettu sarakenimi."), bgcolor=ft.Colors.RED_600, duration=3000)
                    if sb not in page.overlay:
                        page.overlay.append(sb)
                    sb.open = True
                    page.update()
                    return

                for ticker, items in by_ticker.items():
                    # read the history for this ticker
                    try:
                        df = pd.read_sql_query(f"SELECT * FROM osakedata WHERE \"{ticker_col}\" = ? ORDER BY \"{pvm_col}\" ASC", oconn, params=(ticker,))
                    except Exception:
                        # fallback: try case-insensitive matching by reading all and filtering
                        df = pd.read_sql_query("SELECT * FROM osakedata ORDER BY \"{}\" ASC".format(pvm_col), oconn)
                        if ticker_col in df.columns:
                            df = df[df[ticker_col] == ticker]

                    if df.empty:
                        continue

                    # normalize pvm column to YYYY-MM-DD strings
                    try:
                        df[pvm_col] = pd.to_datetime(df[pvm_col]).dt.strftime('%Y-%m-%d')
                    except Exception:
                        # leave as-is
                        pass

                    df = df.reset_index(drop=True)

                    # build quick lookup: map date -> index
                    date_to_idx = {str(r[pvm_col]): idx for idx, r in df.iterrows()}

                    for date, kynttila in items:
                        if date not in date_to_idx:
                            # skip if t0 not found
                            continue
                        idx = date_to_idx[date]
                        if idx - 1 < 0 or idx + 1 >= len(df):
                            # missing neighbor days -> skip
                            continue

                        r_m1 = df.loc[idx - 1]
                        r0 = df.loc[idx]
                        r1 = df.loc[idx + 1]

                        def safe_get(row, col):
                            try:
                                v = row[col]
                                if pd.isna(v):
                                    return None
                                return float(v)
                            except Exception:
                                return None

                        def compute_bodi(o, h, l, c):
                            try:
                                if h is None or l is None or (h - l) == 0:
                                    return 0.0
                                bodi = abs(c - o) / (h - l) * 100.0
                                return float(bodi)
                            except Exception:
                                return 0.0

                        # extract values
                        t1_low = safe_get(r_m1, low_col)
                        t1_high = safe_get(r_m1, high_col)
                        t1_open = safe_get(r_m1, open_col)
                        t1_close = safe_get(r_m1, close_col)

                        t0_low = safe_get(r0, low_col)
                        t0_high = safe_get(r0, high_col)
                        t0_open = safe_get(r0, open_col)
                        t0_close = safe_get(r0, close_col)

                        t_1_bodi = compute_bodi(t1_open or 0.0, t1_high or 0.0, t1_low or 0.0, t1_close or 0.0)
                        t_1_bodi_colour = 1 if (t1_close or 0.0) > (t1_open or 0.0) else 0

                        t0_bodi = compute_bodi(t0_open or 0.0, t0_high or 0.0, t0_low or 0.0, t0_close or 0.0)
                        t0_bodi_colour = 1 if (t0_close or 0.0) > (t0_open or 0.0) else 0

                        t1_low_v = safe_get(r1, low_col)
                        t1_high_v = safe_get(r1, high_col)
                        t1_open_v = safe_get(r1, open_col)
                        t1_close_v = safe_get(r1, close_col)

                        t1_bodi = compute_bodi(t1_open_v or 0.0, t1_high_v or 0.0, t1_low_v or 0.0, t1_close_v or 0.0)
                        t1_bodi_colour = 1 if (t1_close_v or 0.0) > (t1_open_v or 0.0) else 0

                        out = [
                            ticker,
                            date,
                            kynttila,
                            (t1_low if t1_low is not None else ''),
                            (t1_high if t1_high is not None else ''),
                            round(t_1_bodi, 6),
                            t_1_bodi_colour,
                            (t0_low if t0_low is not None else ''),
                            (t0_high if t0_high is not None else ''),
                            round(t0_bodi, 6),
                            t0_bodi_colour,
                            (t1_low_v if t1_low_v is not None else ''),
                            (t1_high_v if t1_high_v is not None else ''),
                            round(t1_bodi, 6),
                            t1_bodi_colour,
                        ]

                        output_rows.append(out)

            # ensure data dir exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            header = [
                'osake', 'date', 'kynttila',
                't_1_alin', 't_1_ylin', 't_1_bodi', 't_1_bodi_colour',
                't0_alin', 't0_ylin', 't0_bodi', 't0_bodi_colour',
                't1_alin', 't1_ylin', 't1_bodi', 't1_bodi_colour',
            ]

            added = 0
            # open file, write header if missing
            if not csv_path.exists():
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(header)

            if output_rows:
                with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    for r in output_rows:
                        writer.writerow(r)
                        added += 1

            # show success snackbar
            sb = ft.SnackBar(ft.Text(f"✅ Lisätty {added} riviä results.csv:ään"), bgcolor=ft.Colors.GREEN_600, duration=3000)
            if sb not in page.overlay:
                page.overlay.append(sb)
            sb.open = True
            page.update()

        except Exception as ex:
            # show error snackbar and log
            tb = traceback.format_exc()
            try:
                sb = ft.SnackBar(ft.Text(f"❌ Virhe: {str(ex)}"), bgcolor=ft.Colors.RED_600, duration=4000)
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
            except Exception:
                pass
            # also print traceback to console for debugging
            print(tb)

    threading.Thread(target=worker, daemon=True).start()


def paivita_results_csv_click(e):
    """Convenience click handler: tries to extract page from event and call paivita_results_csv."""
    try:
        page = e.page
    except Exception:
        try:
            page = e.control.page
        except Exception:
            page = None
    if page is not None:
        paivita_results_csv(page)
