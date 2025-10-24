def print_analysis_results(results: dict, ticker: str, output_path: str = None):
    """
    Tulostaa analyysitulokset (montako kutakin kynttilätyyppiä löytyi) sekä pop-upiin että tiedostoon.
    Palauttaa tulosteen tekstimuodossa (string).

    Parannukset:
    - Lisää aikaleiman tulosteen alkuun.
    - Jos ticker on None, näyttää "kaikille tickereille" sijaan "useille tickereille".
    - Suojaa tiedostokirjoituksen try/except:lla ja kirjaa virheen loggeriin jos saatavilla.
    """
    import datetime as _dt
    import os
    from collections import Counter

    def _extract_pattern(entry):
        value = None
        if isinstance(entry, dict):
            value = entry.get("pattern") or entry.get("name")
        else:
            value = entry
        if value is None:
            return ""
        name = str(value).strip()
        if not name:
            return ""
        normalized = name.replace("_", " ")
        # jos kaikki kirjaimet pieniä, nosta otsikkotyyliin
        if normalized.islower():
            normalized = normalized.title()
        return normalized

    def _extract_strength(entry):
        if isinstance(entry, dict):
            strength = entry.get("strength")
            if strength is not None:
                try:
                    return float(strength)
                except Exception:
                    return None
        return None

    pattern_list = []
    for pats in results.values():
        for entry in pats:
            pattern_name = _extract_pattern(entry)
            if pattern_name:
                pattern_list.append(pattern_name)

    count = Counter(pattern_list)

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target = f"tickerille {ticker}" if ticker else "kaikille tickereille"

    if not count:
        msg = f"Analyysi {now} — Ei yhtään valittua kynttiläkuviota löytynyt {target}."
    else:
        header = f"Analyysitulokset ({now}) — {target}"
        lines = [header]
        lines += [f"{k}: {v} kpl" for k, v in count.items()]

        # Add CSV-style per-finding lines: ticker,date,candle[,signal_strength]
        csv_lines = []
        for key in sorted(results.keys()):
            # expecting key format: 'TICKER|YYYY-MM-DD' from runner
            if "|" in key:
                t, d = key.split("|", 1)
            else:
                # backward compatibility: key might be just date
                t = ticker or ""
                d = key
            pats = results[key]
            for entry in pats:
                pattern_name = _extract_pattern(entry)
                strength = _extract_strength(entry)
                if strength is not None:
                    csv_lines.append(f"{t},{d},{pattern_name},{strength:.3f}")
                else:
                    csv_lines.append(f"{t},{d},{pattern_name}")

        msg_lines = lines
        msg_lines.append("")
        msg_lines.append(
            "Löydetyt tapahtumat (CSV: ticker,päivä,kuvio[,signal_strength]):"
        )
        msg_lines.extend(csv_lines)
        msg = "\n".join(msg_lines)

    if output_path:
        try:
            # create timestamped filename next to the provided output_path
            base_dir = os.path.dirname(output_path)
            base_name = os.path.splitext(os.path.basename(output_path))[0]
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            # archive existing analysis_results files
            try:
                archive_dir = os.path.join(base_dir, "archive")
                os.makedirs(archive_dir, exist_ok=True)
                for fname in os.listdir(base_dir):
                    if fname.startswith(base_name):
                        src = os.path.join(base_dir, fname)
                        dst = os.path.join(archive_dir, fname)
                        # if destination exists, add a suffix to avoid overwrite
                        if os.path.exists(dst):
                            dst = os.path.join(archive_dir, f"{fname}.{ts}")
                        try:
                            os.replace(src, dst)
                        except Exception:
                            # best-effort: ignore move failure
                            pass
            except Exception:
                # non-fatal if archiving fails
                pass
            timestamped_txt = os.path.join(base_dir, f"{base_name}_{ts}.txt")
            with open(timestamped_txt, "w", encoding="utf-8") as f:
                f.write(msg + "\n")
            # also update the canonical (non-timestamped) output file so UI can keep using it
            canonical_txt = os.path.join(base_dir, f"{base_name}.txt")
            try:
                with open(canonical_txt, "w", encoding="utf-8") as cf:
                    cf.write(msg + "\n")
            except Exception:
                # non-fatal
                pass
            # expose timestamped path to caller via output_path variable
            output_path = timestamped_txt
        except Exception as ex:
            # try to log via available logger, but don't require it
            try:
                from .logger import setup_logger

                logger = setup_logger()
                logger.exception("Virhe kirjoitettaessa analyysitulostiedostoa")
            except Exception:
                pass
            # append error note to returned message so UI can show it
            msg = msg + f"\n\n❌ Virhe tiedostoon kirjoitettaessa: {ex}"

    # Also write CSV file next to the text output if output_path provided
    csv_path = None
    if output_path:
        try:
            # write CSV with the same timestamped base name
            csv_path = os.path.splitext(output_path)[0] + ".csv"
            # if output_path ended with .txt, replace .txt with .csv
            if csv_path.lower().endswith(".txt.csv"):
                csv_path = csv_path[:-4]
            with open(csv_path, "w", encoding="utf-8") as cf:
                cf.write("ticker,date,candle,signal_strength\n")
                for key in sorted(results.keys()):
                    if "|" in key:
                        t, d = key.split("|", 1)
                    else:
                        t = ticker or ""
                        d = key
                    for entry in results[key]:
                        pattern_name = _extract_pattern(entry)
                        strength = _extract_strength(entry)
                        strength_str = f"{strength:.3f}" if strength is not None else ""
                        cf.write(f"{t},{d},{pattern_name},{strength_str}\n")
            # also log each finding as a separate log line (one finding per log row)
            try:
                from .logger import setup_logger

                logger = setup_logger()
                for key in sorted(results.keys()):
                    if "|" in key:
                        t, d = key.split("|", 1)
                    else:
                        t = ticker or ""
                        d = key
                    for entry in results[key]:
                        pattern_name = _extract_pattern(entry)
                        strength = _extract_strength(entry)
                        strength_str = f"{strength:.3f}" if strength is not None else ""
                        logger.info(f"{t},{d},{pattern_name},{strength_str}")
            except Exception:
                # non-fatal if logging fails
                pass
            # also persist findings to a small analysis DB (avoid duplicates)
            try:
                import sqlite3

                db_path = os.path.join(os.path.dirname(__file__), "analysis.db")
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                # Yhtenäistä skeema database_managerin kanssa
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_findings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        date TEXT NOT NULL,
                        pattern TEXT,
                        signal_strength REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticker, date, pattern)
                    )
                """
                )
                # Poista mahdolliset duplikaatit ennen uniikki-indeksin luontia
                cur.execute(
                    """
                    DELETE FROM analysis_findings
                    WHERE rowid NOT IN (
                        SELECT MIN(rowid)
                        FROM analysis_findings
                        GROUP BY ticker, date, pattern
                    )
                    """
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_finding ON analysis_findings(ticker, date, pattern)"
                )
                rows = []
                for key in sorted(results.keys()):
                    if "|" in key:
                        t, d = key.split("|", 1)
                    else:
                        t = ticker or ""
                        d = key
                        # ei tietoa muista tickereistä -> fallback tickerille
                    for entry in results[key]:
                        pattern_name = _extract_pattern(entry)
                        if not pattern_name:
                            continue
                        strength = _extract_strength(entry)
                        rows.append((t, d, pattern_name, strength if strength is not None else 1.0))
                if rows:
                    cur.executemany(
                        "INSERT OR REPLACE INTO analysis_findings (ticker, date, pattern, signal_strength) VALUES (?, ?, ?, ?)",
                        rows,
                    )
                    conn.commit()
                conn.close()
            except Exception:
                # non-fatal persistence failure
                pass
            # also update canonical CSV
            try:
                canonical_csv = os.path.join(base_dir, f"{base_name}.csv")
                with open(canonical_csv, "w", encoding="utf-8") as bcf:
                    bcf.write("ticker,date,candle,signal_strength\n")
                    for key in sorted(results.keys()):
                        if "|" in key:
                            t, d = key.split("|", 1)
                        else:
                            t = ticker or ""
                            d = key
                        for entry in results[key]:
                            pattern_name = _extract_pattern(entry)
                            strength = _extract_strength(entry)
                            strength_str = f"{strength:.3f}" if strength is not None else ""
                            bcf.write(f"{t},{d},{pattern_name},{strength_str}\n")
            except Exception:
                pass
        except Exception:
            csv_path = None

    return msg, csv_path
