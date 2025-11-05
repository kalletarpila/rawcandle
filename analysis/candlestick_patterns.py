import pandas as pd
import numpy as np


def calculate_rsi(df, period=14, close_col="Close"):
    """
    Laskee Relative Strength Index (RSI) -indikaattorin.

    Args:
        df: DataFrame jossa close-sarake
        period: RSI-jakso (oletuksena 14 päivää)
        close_col: Close-sarakkeen nimi (oletuksena "Close")

    Returns:
        DataFrame jossa alkuperäiset sarakkeet + 'RSI' sarake
    """
    df = df.copy()
    delta = df[close_col].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Vältetään jakaminen nollalla
    rs = gain / loss.replace(0, np.inf)
    df["RSI"] = 100 - (100 / (1 + rs))

    return df


def find_local_extremes(series, window=14, extreme_type="min"):
    """
    Löytää paikalliset minimit tai maksimit sarjasta.

    Args:
        series: Pandas Series josta etsitään ääriarvot
        window: Ikkunan koko (esim. 14 = alhaisin/ylin 14 päivän sisällä)
        extreme_type: 'min' tai 'max'

    Returns:
        Boolean Series jossa True merkitsee paikallista ääriarvoa
    """
    if extreme_type == "min":
        # Paikallinen minimi: alempi kuin kaikki window/2 päivää ennen ja jälkeen
        rolling_min = series.rolling(window=window, center=True).min()
        is_extreme = (series == rolling_min) & series.notna()
    else:
        # Paikallinen maksimi: korkeampi kuin kaikki window/2 päivää ennen ja jälkeen
        rolling_max = series.rolling(window=window, center=True).max()
        is_extreme = (series == rolling_max) & series.notna()

    return is_extreme


def is_hammer(row):
    open_ = row["Open"]
    close = row["Close"]
    high = row["High"]
    low = row["Low"]
    body = abs(close - open_)
    lower_shadow = min(open_, close) - low
    upper_shadow = high - max(open_, close)
    return body < (high - low) * 0.4 and lower_shadow > body * 2 and upper_shadow < body


def is_bullish_engulfing(prev_row, row):
    return (
        prev_row["Close"] < prev_row["Open"]
        and row["Close"] > row["Open"]
        and row["Open"] < prev_row["Close"]
        and row["Close"] > prev_row["Open"]
    )


def is_piercing_pattern(prev_row, row):
    return (
        prev_row["Close"] < prev_row["Open"]
        and row["Open"] < prev_row["Close"]
        and row["Close"] > (prev_row["Open"] + prev_row["Close"]) / 2
        and row["Close"] < prev_row["Open"]
    )


def is_three_white_soldiers(df, idx):
    if idx < 2:
        return False
    r1, r2, r3 = df.iloc[idx - 2], df.iloc[idx - 1], df.iloc[idx]
    return (
        all(r["Close"] > r["Open"] for r in [r1, r2, r3])
        and r2["Open"] > r1["Open"]
        and r2["Close"] > r1["Close"]
        and r3["Open"] > r2["Open"]
        and r3["Close"] > r2["Close"]
    )


def is_morning_star(df, idx):
    if idx < 2:
        return False
    r1, r2, r3 = df.iloc[idx - 2], df.iloc[idx - 1], df.iloc[idx]
    return (
        r1["Close"] < r1["Open"]
        and abs(r2["Close"] - r2["Open"]) < (r1["Open"] - r1["Close"]) * 0.5
        and r3["Close"] > r3["Open"]
        and r3["Close"] > ((r1["Open"] + r1["Close"]) / 2)
    )


def is_dragonfly_doji(row):
    open_ = row["Open"]
    close = row["Close"]
    high = row["High"]
    low = row["Low"]
    body = abs(close - open_)
    lower_shadow = min(open_, close) - low
    upper_shadow = high - max(open_, close)
    return (
        body < (high - low) * 0.1
        and lower_shadow > (high - low) * 0.6
        and upper_shadow < (high - low) * 0.1
    )


def is_bullish_divergence(
    df, idx, lookback_days=30, min_rsi_gain=3.0, min_days_between=3, close_col="Close"
):
    """
    Tunnistaa Bullish Divergence -kuvion.

    Kriteerit:
    - Hinta tekee matalamman pohjan (lower low)
    - RSI tekee korkeamman pohjan (higher low)
    - Pohjien välillä vähintään min_days_between päivää
    - RSI-nousu vähintään min_rsi_gain pistettä
    - **UUSI: Vaaditaan laskeva trendi** (hinta alle 20 päivän EMA)

    Args:
        df: DataFrame jossa Close, RSI sarakkeet ja pvm-indeksi
        idx: Tarkistettavan rivin indeksi
        lookback_days: Kuinka kauaksi taaksepäin etsitään edellistä pohjaa (oletus 30)
        min_rsi_gain: RSI:n minimaalinen nousu pohjien välillä (oletus 3.0)
        min_days_between: Minimietäisyys pohjien välillä päivinä (oletus 3)
        close_col: Close-sarakkeen nimi (oletuksena "Close")

    Returns:
        dict: {'found': bool, 'strength': float, 'price_change': float, 'rsi_change': float}
              tai None jos ei tarpeeksi dataa
    """
    # Tarvitaan vähintään lookback_days + 20 (EMA-laskentaan) dataa
    if idx < max(lookback_days + 20, 34):
        return None

    # Varmistetaan että RSI-sarake on laskettu
    if "RSI" not in df.columns:
        return None

    # UUSI: Tarkista että ollaan laskutrendissä
    # Lasketaan 20 päivän EMA nykyiselle hinnalle
    current_price = df.iloc[idx][close_col]

    if pd.isna(current_price):
        return None

    # Yksinkertainen trenditarkistus: hinta alle 20-päivän liukuvan keskiarvon
    ema_window = 20
    if idx >= ema_window:
        ema_prices = df.iloc[idx - ema_window + 1 : idx + 1][close_col]
        ema_20 = ema_prices.ewm(span=ema_window, adjust=False).mean().iloc[-1]

        # Jos hinta yli EMA20, ei ole laskutrendissä -> ei bullish divergenssiä
        if current_price >= ema_20:
            return None
    # Etsi nykyinen paikallinen minimi (t2)
    current_rsi = df.iloc[idx]["RSI"]

    if pd.isna(current_rsi):
        return None

    # Tarkista onko nykyinen indeksi paikallinen minimi hinnan suhteen
    # (alempi kuin 7 päivää ennen ja jälkeen)
    window = 7
    start_check = max(0, idx - window)
    end_check = min(len(df), idx + window + 1)
    local_min_prices = df.iloc[start_check:end_check][close_col]

    if current_price != local_min_prices.min():
        return None  # Ei ole paikallinen minimi

    # Etsi edellinen paikallinen minimi (t1) lookback-alueelta
    search_start = max(0, idx - lookback_days)
    search_end = idx - min_days_between  # Vähintään min_days_between päivää väliä

    if search_end <= search_start:
        return None

    # Käy läpi mahdolliset edelliset pohjat
    prev_bottom_idx = None
    prev_bottom_price = None
    prev_bottom_rsi = None

    for i in range(search_end, search_start - 1, -1):
        # Tarkista onko paikallinen minimi
        i_start = max(0, i - window)
        i_end = min(len(df), i + window + 1)
        i_local_prices = df.iloc[i_start:i_end][close_col]
        i_price = df.iloc[i][close_col]
        i_rsi = df.iloc[i]["RSI"]

        if pd.isna(i_price) or pd.isna(i_rsi):
            continue

        if i_price == i_local_prices.min():
            prev_bottom_idx = i
            prev_bottom_price = i_price
            prev_bottom_rsi = i_rsi
            break

    # Jos ei löytynyt edellistä pohjaa
    if prev_bottom_idx is None:
        return None

    # Tarkista divergenssi-kriteerit
    price_change = ((current_price - prev_bottom_price) / prev_bottom_price) * 100
    rsi_change = current_rsi - prev_bottom_rsi

    # Bullish divergence: hinta alemmas (price_change < 0) JA RSI ylös (rsi_change > min_rsi_gain)
    is_divergence = (price_change < 0) and (rsi_change >= min_rsi_gain)

    if not is_divergence:
        return None

    # Laske vahvuus yhdistelmäkaavalla (1-3 asteikolla):
    # - RSI:n muutos (0-1 pistettä per 5 pistettä RSI-muutosta)
    # - Hinnan muutos (0-1 pistettä per 10% hinnan muutos)
    # - Keston vaikutus (0-1 pistettä per 20 päivää)
    days_between = idx - prev_bottom_idx

    rsi_component = min(1.0, abs(rsi_change) / 5.0)
    price_component = min(1.0, abs(price_change) / 10.0)
    duration_component = min(1.0, days_between / 20.0)

    strength = rsi_component + price_component + duration_component
    strength = max(1.0, min(3.0, strength))  # Skaalaa välille 1-3
    strength = round(strength, 2)  # Kahden desimaalin tarkkuus

    return {
        "found": True,
        "strength": strength,
        "price_change": round(price_change, 2),
        "rsi_change": round(rsi_change, 2),
        "prev_date": df.iloc[prev_bottom_idx].get("pvm", prev_bottom_idx),
        "days_between": days_between,
    }


def is_bearish_divergence(
    df, idx, lookback_days=30, min_rsi_drop=3.0, min_days_between=3, close_col="Close"
):
    """
    Tunnistaa Bearish Divergence -kuvion.

    Kriteerit:
    - Hinta tekee korkeamman huipun (higher high)
    - RSI tekee matalamman huipun (lower high)
    - Huippujen välillä vähintään min_days_between päivää
    - RSI-lasku vähintään min_rsi_drop pistettä
    - **UUSI: Vaaditaan nouseva trendi** (hinta yli 20 päivän EMA)

    Args:
        df: DataFrame jossa Close, RSI sarakkeet ja pvm-indeksi
        idx: Tarkistettavan rivin indeksi
        lookback_days: Kuinka kauaksi taaksepäin etsitään edellistä huippua (oletus 30)
        min_rsi_drop: RSI:n minimaalinen lasku huippujen välillä (oletus 3.0)
        min_days_between: Minimietäisyys huippujen välillä päivinä (oletus 3)
        close_col: Close-sarakkeen nimi (oletuksena "Close")

    Returns:
        dict: {'found': bool, 'strength': float, 'price_change': float, 'rsi_change': float}
              tai None jos ei tarpeeksi dataa
    """
    # Tarvitaan vähintään lookback_days + 20 (EMA-laskentaan) dataa
    if idx < max(lookback_days + 20, 34):
        return None

    # Varmistetaan että RSI-sarake on laskettu
    if "RSI" not in df.columns:
        return None

    # UUSI: Tarkista että ollaan nousutrendissä
    # Lasketaan 20 päivän EMA nykyiselle hinnalle
    current_price = df.iloc[idx][close_col]

    if pd.isna(current_price):
        return None

    # Yksinkertainen trenditarkistus: hinta yli 20-päivän liukuvan keskiarvon
    ema_window = 20
    if idx >= ema_window:
        ema_prices = df.iloc[idx - ema_window + 1 : idx + 1][close_col]
        ema_20 = ema_prices.ewm(span=ema_window, adjust=False).mean().iloc[-1]

        # Jos hinta alle EMA20, ei ole nousutrendissä -> ei bearish divergenssiä
        if current_price <= ema_20:
            return None
    # Etsi nykyinen paikallinen maksimi (t2)
    current_rsi = df.iloc[idx]["RSI"]

    if pd.isna(current_rsi):
        return None

    # Tarkista onko nykyinen indeksi paikallinen maksimi hinnan suhteen
    window = 7
    start_check = max(0, idx - window)
    end_check = min(len(df), idx + window + 1)
    local_max_prices = df.iloc[start_check:end_check][close_col]

    if current_price != local_max_prices.max():
        return None  # Ei ole paikallinen maksimi

    # Etsi edellinen paikallinen maksimi (t1) lookback-alueelta
    search_start = max(0, idx - lookback_days)
    search_end = idx - min_days_between

    if search_end <= search_start:
        return None

    # Käy läpi mahdolliset edelliset huiput
    prev_peak_idx = None
    prev_peak_price = None
    prev_peak_rsi = None

    for i in range(search_end, search_start - 1, -1):
        # Tarkista onko paikallinen maksimi
        i_start = max(0, i - window)
        i_end = min(len(df), i + window + 1)
        i_local_prices = df.iloc[i_start:i_end][close_col]
        i_price = df.iloc[i][close_col]
        i_rsi = df.iloc[i]["RSI"]

        if pd.isna(i_price) or pd.isna(i_rsi):
            continue

        if i_price == i_local_prices.max():
            prev_peak_idx = i
            prev_peak_price = i_price
            prev_peak_rsi = i_rsi
            break

    # Jos ei löytynyt edellistä huippua
    if prev_peak_idx is None:
        return None

    # Tarkista divergenssi-kriteerit
    price_change = ((current_price - prev_peak_price) / prev_peak_price) * 100
    rsi_change = current_rsi - prev_peak_rsi

    # Bearish divergence: hinta ylös (price_change > 0) JA RSI alas (rsi_change <= -min_rsi_drop)
    is_divergence = (price_change > 0) and (rsi_change <= -min_rsi_drop)

    if not is_divergence:
        return None

    # Laske vahvuus yhdistelmäkaavalla (1-3 asteikolla):
    # - RSI:n muutos (0-1 pistettä per 5 pistettä RSI-muutosta)
    # - Hinnan muutos (0-1 pistettä per 10% hinnan muutos)
    # - Keston vaikutus (0-1 pistettä per 20 päivää)
    days_between = idx - prev_peak_idx

    rsi_component = min(1.0, abs(rsi_change) / 5.0)
    price_component = min(1.0, abs(price_change) / 10.0)
    duration_component = min(1.0, days_between / 20.0)

    strength = rsi_component + price_component + duration_component
    strength = max(1.0, min(3.0, strength))  # Skaalaa välille 1-3
    strength = round(strength, 2)  # Kahden desimaalin tarkkuus

    return {
        "found": True,
        "strength": strength,
        "price_change": round(price_change, 2),
        "rsi_change": round(rsi_change, 2),
        "prev_date": df.iloc[prev_peak_idx].get("pvm", prev_peak_idx),
        "days_between": days_between,
    }
