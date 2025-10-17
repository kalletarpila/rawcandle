def print_analysis_results(results: dict, ticker: str, output_path: str = None):
    """
    Tulostaa analyysitulokset (montako kutakin kynttilätyyppiä löytyi) sekä pop-upiin että tiedostoon.
    Palauttaa tulosteen tekstimuodossa (string).

    Parannukset:
    - Lisää aikaleiman tulosteen alkuun.
    - Jos ticker on None, näyttää "kaikille tickereille" sijaan "useille tickereille".
    - Suojaa tiedostokirjoituksen try/except:lla ja kirjaa virheen loggeriin jos saatavilla.
    """
    from collections import Counter
    import datetime as _dt
    import os

    all_found = []
    for pats in results.values():
        all_found.extend(pats)
    count = Counter(all_found)

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target = f"tickerille {ticker}" if ticker else "kaikille tickereille"

    if not count:
        msg = f"Analyysi {now} — Ei yhtään valittua kynttiläkuviota löytynyt {target}."
    else:
        header = f"Analyysitulokset ({now}) — {target}"
        lines = [header]
        lines += [f"{k}: {v} kpl" for k, v in count.items()]

        # Add CSV-style per-finding lines: ticker,date,pattern
        csv_lines = []
        for key in sorted(results.keys()):
            # expecting key format: 'TICKER|YYYY-MM-DD' from runner
            if '|' in key:
                t, d = key.split('|', 1)
            else:
                # backward compatibility: key might be just date
                t = ticker or ''
                d = key
            pats = results[key]
            for p in pats:
                csv_lines.append(f"{t},{d},{p}")

        msg_lines = lines
        msg_lines.append("")
        msg_lines.append("Löydetyt tapahtumat (yhden rivin CSV: ticker,päivä,kuvio):")
        msg_lines.extend(csv_lines)
        msg = "\n".join(msg_lines)

    if output_path:
        try:
            # create timestamped filename next to the provided output_path
            base_dir = os.path.dirname(output_path)
            base_name = os.path.splitext(os.path.basename(output_path))[0]
            ts = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
            # archive existing analysis_results files
            try:
                archive_dir = os.path.join(base_dir, 'archive')
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
            csv_path = os.path.splitext(output_path)[0] + '.csv'
            # if output_path ended with .txt, replace .txt with .csv
            if csv_path.lower().endswith('.txt.csv'):
                csv_path = csv_path[:-4]
            with open(csv_path, 'w', encoding='utf-8') as cf:
                cf.write('ticker,date,pattern\n')
                for key in sorted(results.keys()):
                    if '|' in key:
                        t, d = key.split('|', 1)
                    else:
                        t = ticker or ''
                        d = key
                    for p in results[key]:
                        cf.write(f"{t},{d},{p}\n")
            # also log each finding as a separate log line (one finding per log row)
            try:
                from .logger import setup_logger
                logger = setup_logger()
                for key in sorted(results.keys()):
                    if '|' in key:
                        t, d = key.split('|', 1)
                    else:
                        t = ticker or ''
                        d = key
                    for p in results[key]:
                        # log CSV-style line so it's easy to grep/parse
                        logger.info(f"{t},{d},{p}")
            except Exception:
                # non-fatal if logging fails
                pass
            # also update canonical CSV
            try:
                canonical_csv = os.path.join(base_dir, f"{base_name}.csv")
                with open(canonical_csv, 'w', encoding='utf-8') as bcf:
                    bcf.write('ticker,date,pattern\n')
                    for key in sorted(results.keys()):
                        if '|' in key:
                            t, d = key.split('|', 1)
                        else:
                            t = ticker or ''
                            d = key
                        for p in results[key]:
                            bcf.write(f"{t},{d},{p}\n")
            except Exception:
                pass
        except Exception:
            csv_path = None

    return msg, csv_path
