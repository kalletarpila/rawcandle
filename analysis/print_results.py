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

    def _extract_rsi(entry):
        """Poimii RSI-arvon löydöksestä"""
        if isinstance(entry, dict):
            rsi = entry.get("rsi14")
            if rsi is not None:
                try:
                    return float(rsi)
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

    # Tiedostojen kirjoitus poistettu - käytetään vain analysis.log ja tietokantaa

    # Kirjataan löydökset logiin
    if output_path:
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

    # Tallenna löydökset tietokantaan (ilman divergenssien laskentaa)
    if output_path:
        try:
            from analysis.database_manager import DatabaseManager

            db_manager = DatabaseManager(db_path="data/analysis.db")

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
                    rsi14 = _extract_rsi(entry)

                    db_manager.save_finding(
                        ticker=t,
                        date=d,
                        pattern=pattern_name,
                        signal_strength=strength if strength is not None else 1.0,
                        rsi14=rsi14,
                    )

            db_manager.close()

        except Exception:
            # non-fatal persistence failure
            pass

    return msg, None  # Ei palauteta csv_path:ia enää


def calculate_and_save_divergences(
    ticker: str, osakedata_db_path: str = "data/osakedata.db"
) -> bool:
    """
    Laske divergenssit kaikille tickerin päiville ja tallenna analysis.db:hen.

    Args:
        ticker: Osakkeen symboli
        osakedata_db_path: Polku osakedata-tietokantaan

    Returns:
        True jos onnistui
    """
    import sqlite3
    import pandas as pd
    from analysis.candlestick_patterns import (
        calculate_rsi,
        is_bullish_divergence,
        is_bearish_divergence,
    )
    from analysis.database_manager import DatabaseManager

    # Normalisoi ticker: isot kirjaimet, trimmattu
    ticker = (ticker or "").strip().upper()

    try:
        # Lue data
        with sqlite3.connect(osakedata_db_path) as conn:
            df = pd.read_sql_query(
                "SELECT pvm, close FROM osakedata WHERE osake = ? ORDER BY pvm",
                conn,
                params=[ticker],
            )

        if df.empty:
            print(f"⚠️ Ei dataa tickerille {ticker}")
            return False

        # Laske RSI
        df = calculate_rsi(df, period=14, close_col="close")

        if "RSI" not in df.columns:
            print(f"⚠️ RSI-laskenta epäonnistui tickerille {ticker}")
            return False

        # Laske divergenssit kaikille päiville
        divergence_records = []

        for idx in range(len(df)):
            date = str(df.iloc[idx]["pvm"])
            rsi = df.iloc[idx]["RSI"]

            bullish_strength = 0.0
            bearish_strength = 0.0

            # Tarvitaan vähintään 30 päivää historiaa divergenssien tunnistukseen
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

        # Tallenna tietokantaan
        db_manager = DatabaseManager(db_path="data/analysis.db")
        success = db_manager.save_divergence_batch(ticker, divergence_records)
        db_manager.close()

        if success:
            print(
                f"✅ Tallennettu {len(divergence_records)} divergenssipäivää tickerille {ticker}"
            )

        return success

    except Exception as e:
        print(f"❌ Divergenssien laskenta epäonnistui tickerille {ticker}: {e}")
        return False
