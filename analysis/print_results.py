def print_analysis_results(results: dict, ticker: str, output_path: str = None):
    """
    Tulostaa analyysitulokset (montako kutakin kynttilätyyppiä löytyi) sekä pop-upiin että tiedostoon.
    Palauttaa tulosteen tekstimuodossa (string).
    """
    from collections import Counter
    all_found = []
    for pats in results.values():
        all_found.extend(pats)
    count = Counter(all_found)
    if not count:
        msg = "Ei yhtään valittua kynttiläkuviota löytynyt."
    else:
        msg = f"Analyysitulokset tickerille {ticker}\n"
        msg += "\n".join(f"{k}: {v} kpl" for k, v in count.items())
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
    return msg
