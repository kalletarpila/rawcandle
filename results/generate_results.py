import threading
import sqlite3
import pandas as pd
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


def _build_output_rows(analysis_db: Path, osake_db: Path):
    """Synchronous builder for output rows according to spec.

    Returns (header, output_rows).
    """
    # --- read analysis rows ---
    with sqlite3.connect(analysis_db) as aconn:
        acur = aconn.cursor()
        tbls = [r[0] for r in acur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        candidates = ['analysis_findings', 'analysis', 'findings', 'analysis_rows']
        table_name = next((c for c in candidates if c in tbls), None)
        if table_name is None:
            # fallback heuristic
            for t in tbls:
                info = acur.execute(f"PRAGMA table_info({t})").fetchall()
                cols = [r[1].lower() for r in info]
                if any(x in cols for x in ('date', 'pvm')) and any(x in cols for x in ('ticker', 'osake', 'symbol')):
                    table_name = t
                    break
        if table_name is None:
            raise RuntimeError('analysis table not found in analysis.db')

        info = acur.execute(f"PRAGMA table_info({table_name})").fetchall()
        col_names = [r[1] for r in info]
        lower = {c.lower(): c for c in col_names}
        date_col = lower.get('date') or lower.get('pvm')
        ticker_col = lower.get('ticker') or lower.get('osake') or lower.get('symbol')
        pattern_col = lower.get('kynttila') or lower.get('pattern') or lower.get('pattern_name')
        if not date_col or not ticker_col:
            raise RuntimeError(f'Cannot find date/ticker columns in {table_name}: {col_names}')

        q = f"SELECT \"{date_col}\", \"{ticker_col}\""
        if pattern_col:
            q += f", \"{pattern_col}\""
        q += f" FROM \"{table_name}\""
        acur.execute(q)
        rows = acur.fetchall()

    if not rows:
        return [], []

    by_ticker = {}
    for rec in rows:
        if len(rec) == 3:
            date, ticker, pattern = rec
        elif len(rec) == 2:
            date, ticker = rec
            pattern = ''
        else:
            continue
        if not ticker:
            continue
        by_ticker.setdefault(str(ticker), []).append((str(date), pattern))

    output_rows = []

    # --- read osakedata per ticker ---
    with sqlite3.connect(osake_db) as oconn:
        ocur = oconn.cursor()
        cols, lower = _identify_columns(ocur, 'osakedata')
        tcol = lower.get('osake') or lower.get('ticker') or lower.get('symbol')
        pcol = lower.get('pvm') or lower.get('date')
        ocol = lower.get('open')
        hcol = lower.get('high')
        lcol = lower.get('low')
        ccol = lower.get('close')

        if not tcol or not pcol or not ocol or not hcol or not lcol or not ccol:
            raise RuntimeError('osakedata table missing expected column names')

        for ticker, items in by_ticker.items():
            try:
                df = pd.read_sql_query(f"SELECT * FROM osakedata WHERE \"{tcol}\" = ? ORDER BY \"{pcol}\" ASC", oconn, params=(ticker,))
            except Exception:
                df = pd.read_sql_query(f"SELECT * FROM osakedata ORDER BY \"{pcol}\" ASC", oconn)
                if tcol in df.columns:
                    df = df[df[tcol] == ticker]

            if df.empty:
                continue

            try:
                df[pcol] = pd.to_datetime(df[pcol]).dt.strftime('%Y-%m-%d')
            except Exception:
                pass

            df = df.reset_index(drop=True)
            date_to_idx = {str(r[pcol]): idx for idx, r in df.iterrows()}

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
                    if o is None or h is None or l is None or c is None:
                        return None
                    if (h - l) == 0:
                        return None
                    return float(abs(c - o) / (h - l) * 100.0)
                except Exception:
                    return None

            for date, pattern in items:
                if date not in date_to_idx:
                    continue
                idx = date_to_idx[date]
                if idx - 1 < 0 or idx + 1 >= len(df):
                    continue

                r_m1 = df.loc[idx - 1]
                r0 = df.loc[idx]
                r1 = df.loc[idx + 1]

                t1_open = safe_get(r_m1, ocol)
                t1_high = safe_get(r_m1, hcol)
                t1_low = safe_get(r_m1, lcol)
                t1_close = safe_get(r_m1, ccol)

                t0_open = safe_get(r0, ocol)
                t0_high = safe_get(r0, hcol)
                t0_low = safe_get(r0, lcol)
                t0_close = safe_get(r0, ccol)

                t_1_bodi = compute_bodi(t1_open, t1_high, t1_low, t1_close)
                t_1_bodi_colour = 1 if (t1_open is not None and t1_close is not None and t1_close > t1_open) else ''

                t0_bodi = compute_bodi(t0_open, t0_high, t0_low, t0_close)
                t0_bodi_colour = 1 if (t0_open is not None and t0_close is not None and t0_close > t0_open) else ''

                t1_open_v = safe_get(r1, ocol)
                t1_high_v = safe_get(r1, hcol)
                t1_low_v = safe_get(r1, lcol)
                t1_close_v = safe_get(r1, ccol)

                t1_bodi = compute_bodi(t1_open_v, t1_high_v, t1_low_v, t1_close_v)
                t1_bodi_colour = 1 if (t1_open_v is not None and t1_close_v is not None and t1_close_v > t1_open_v) else ''

                def fmt_bodi(v):
                    return (round(v, 6) if v is not None else '')

                out = [
                    ticker,
                    date,
                    pattern,
                    (t1_low if t1_low is not None else ''),
                    (t1_high if t1_high is not None else ''),
                    fmt_bodi(t_1_bodi),
                    (t_1_bodi_colour if t_1_bodi_colour != '' else ''),
                    (t0_low if t0_low is not None else ''),
                    (t0_high if t0_high is not None else ''),
                    fmt_bodi(t0_bodi),
                    (t0_bodi_colour if t0_bodi_colour != '' else ''),
                    (t1_low_v if t1_low_v is not None else ''),
                    (t1_high_v if t1_high_v is not None else ''),
                    fmt_bodi(t1_bodi),
                    (t1_bodi_colour if t1_bodi_colour != '' else ''),
                ]

                output_rows.append(out)

    header = [
        'osake', 'date', 'kynttilä',
        't_1_alin', 't_1_ylin', 't_1_bodi', 't_1_bodi_colour',
        't0_alin', 't0_ylin', 't0_bodi', 't0_bodi_colour',
        't1_alin', 't1_ylin', 't1_bodi', 't1_bodi_colour',
    ]

    return header, output_rows


def paivita_results_csv(page: ft.Page):
    """Starts a background job that builds/updates data/results.csv and shows a SnackBar when done."""

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

            header, output_rows = _build_output_rows(analysis_db, osake_db)

            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # write header if missing
            if not csv_path.exists():
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(header)

            added = 0
            if output_rows:
                with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    for r in output_rows:
                        writer.writerow(r)
                        added += 1

            sb = ft.SnackBar(ft.Text(f"✅ Lisätty {added} riviä results.csv:ään"), bgcolor=ft.Colors.GREEN_600, duration=3000)
            if sb not in page.overlay:
                page.overlay.append(sb)
            sb.open = True
            page.update()

        except Exception as ex:
            tb = traceback.format_exc()
            try:
                sb = ft.SnackBar(ft.Text(f"❌ Virhe: {str(ex)}"), bgcolor=ft.Colors.RED_600, duration=4000)
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
            except Exception:
                pass
            print(tb)

    threading.Thread(target=worker, daemon=True).start()


def paivita_results_csv_click(e):
    try:
        page = e.page
    except Exception:
        try:
            page = e.control.page
        except Exception:
            page = None
    if page is not None:
        paivita_results_csv(page)


def generate_results_now(write: bool = True):
    base = Path(__file__).resolve().parents[1]
    analysis_db = base / 'analysis' / 'analysis.db'
    osake_db = base / 'data' / 'osakedata.db'
    csv_path = base / 'data' / 'results.csv'

    header, output_rows = _build_output_rows(analysis_db, osake_db)

    if not output_rows:
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if write and not csv_path.exists():
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)

    added = 0
    if write:
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for r in output_rows:
                writer.writerow(r)
                added += 1
    else:
        added = len(output_rows)

    return added

