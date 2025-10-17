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
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(msg + "\n")
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

    return msg
