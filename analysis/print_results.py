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
        # Add a compact per-date listing after the summary
        msg_lines = lines
        # results is a dict {date: [patterns]}
        if results:
            msg_lines.append("")
            msg_lines.append("Löydetyt tapahtumat (päivämäärä: kuviot):")
            for d in sorted(results.keys()):
                pats = ", ".join(results[d])
                msg_lines.append(f"{d}: {pats}")
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
