import pandas as pd
import numpy as np


def _is_in_downtrend(df, idx, close_col="Close", use_ma_filter=True):
    """
    Tarkista onko osake laskutrendissä käyttäen samaa logiikkaa kuin analysis-vaiheen suodatin.

    Kriteerit:
    1. Porrastava lasku: t-10 > t-5 > t-2 > t0
    2. MA-suodatin: t0 < MA(10) JA MA(5) < MA(10)

    Args:
        df: DataFrame jossa hintadata
        idx: Tarkistettava indeksi
        close_col: Close-sarakkeen nimi
        use_ma_filter: Käytetäänkö MA-suodatinta (oletus True)

    Returns:
        bool: True jos laskutrendissä
    """
    # Tarvitaan vähintään 10 päivää dataa
    if idx < 10:
        return False

    try:
        # 1. Porrastava lasku: t-10 > t-5 > t-2 > t0
        t0 = df.iloc[idx][close_col]
        t_2 = df.iloc[idx - 2][close_col]
        t_5 = df.iloc[idx - 5][close_col]
        t_10 = df.iloc[idx - 10][close_col]

        if pd.isna(t0) or pd.isna(t_2) or pd.isna(t_5) or pd.isna(t_10):
            return False

        if not (t_10 > t_5 > t_2 > t0):
            return False

        # 2. MA-suodatin
        if use_ma_filter:
            # Laske MA(5) ja MA(10)
            ma5_prices = df.iloc[idx - 4 : idx + 1][close_col]
            ma10_prices = df.iloc[idx - 9 : idx + 1][close_col]

            if len(ma5_prices) < 5 or len(ma10_prices) < 10:
                return False

            ma5 = ma5_prices.mean()
            ma10 = ma10_prices.mean()

            if pd.isna(ma5) or pd.isna(ma10):
                return False

            # t0 < MA(10) JA MA(5) < MA(10)
            if not (t0 < ma10 and ma5 < ma10):
                return False

        return True

    except Exception:
        return False


def _is_in_uptrend(df, idx, close_col="Close", use_ma_filter=True):
    """
    Tarkista onko osake nousutrendissä (päinvastainen laskutrendille).

    Kriteerit:
    1. Porrastava nousu: t-10 < t-5 < t-2 < t0
    2. MA-suodatin: t0 > MA(10) JA MA(5) > MA(10)

    Args:
        df: DataFrame jossa hintadata
        idx: Tarkistettava indeksi
        close_col: Close-sarakkeen nimi
        use_ma_filter: Käytetäänkö MA-suodatinta (oletus True)

    Returns:
        bool: True jos nousutrendissä
    """
    # Tarvitaan vähintään 10 päivää dataa
    if idx < 10:
        return False

    try:
        # 1. Porrastava nousu: t-10 < t-5 < t-2 < t0
        t0 = df.iloc[idx][close_col]
        t_2 = df.iloc[idx - 2][close_col]
        t_5 = df.iloc[idx - 5][close_col]
        t_10 = df.iloc[idx - 10][close_col]

        if pd.isna(t0) or pd.isna(t_2) or pd.isna(t_5) or pd.isna(t_10):
            return False

        if not (t_10 < t_5 < t_2 < t0):
            return False

        # 2. MA-suodatin
        if use_ma_filter:
            # Laske MA(5) ja MA(10)
            ma5_prices = df.iloc[idx - 4 : idx + 1][close_col]
            ma10_prices = df.iloc[idx - 9 : idx + 1][close_col]

            if len(ma5_prices) < 5 or len(ma10_prices) < 10:
                return False

            ma5 = ma5_prices.mean()
            ma10 = ma10_prices.mean()

            if pd.isna(ma5) or pd.isna(ma10):
                return False

            # t0 > MA(10) JA MA(5) > MA(10)
            if not (t0 > ma10 and ma5 > ma10):
                return False

        return True

    except Exception:
        return False


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


def _candle_geometry(row):
    open_ = row["Open"]
    close = row["Close"]
    high = row["High"]
    low = row["Low"]
    candle_range = high - low
    body = abs(close - open_)
    upper_shadow = high - max(open_, close)
    lower_shadow = min(open_, close) - low
    body_top = max(open_, close)
    body_bottom = min(open_, close)
    return {
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "candle_range": candle_range,
        "body": body,
        "upper_shadow": upper_shadow,
        "lower_shadow": lower_shadow,
        "body_top": body_top,
        "body_bottom": body_bottom,
    }


def _gap_tolerance(*prices):
    reference = max((abs(float(price)) for price in prices if pd.notna(price)), default=0.0)
    return max(reference * 0.001, 1e-9)


def is_bearish_engulfing(prev_row, row):
    return (
        prev_row["Close"] > prev_row["Open"]
        and row["Close"] < row["Open"]
        and row["Open"] >= prev_row["Close"]
        and row["Close"] <= prev_row["Open"]
    )


def is_shooting_star(row):
    geometry = _candle_geometry(row)
    candle_range = geometry["candle_range"]
    if candle_range <= 0:
        return False

    body = geometry["body"]
    upper_shadow = geometry["upper_shadow"]
    lower_shadow = geometry["lower_shadow"]
    low = geometry["low"]
    close = geometry["close"]
    body_top = geometry["body_top"]
    small_body_floor = max(candle_range * 0.05, 1e-9)

    return (
        body / candle_range <= 0.35
        and upper_shadow >= 2.0 * max(body, small_body_floor)
        and lower_shadow <= 0.5 * max(body, small_body_floor)
        and (body_top <= low + 0.45 * candle_range or close <= low + 0.45 * candle_range)
    )


def is_dark_cloud_cover(prev_row, row):
    prev_open = prev_row["Open"]
    prev_close = prev_row["Close"]
    return (
        prev_close > prev_open
        and row["Close"] < row["Open"]
        and row["Open"] > prev_close
        and row["Close"] < prev_open + 0.5 * (prev_close - prev_open)
        and row["Close"] > prev_open
    )


def is_evening_star(df, idx):
    if idx < 2:
        return False

    c1 = df.iloc[idx - 2]
    c2 = df.iloc[idx - 1]
    c3 = df.iloc[idx]
    g1 = _candle_geometry(c1)
    g2 = _candle_geometry(c2)

    if g1["candle_range"] <= 0 or g2["candle_range"] <= 0:
        return False

    c1_open = c1["Open"]
    c1_close = c1["Close"]
    c2_body = g2["body"]
    c3_open = c3["Open"]
    c3_close = c3["Close"]

    return (
        c1_close > c1_open
        and g1["body"] / g1["candle_range"] >= 0.45
        and c2_body / g2["candle_range"] <= 0.35
        and c3_close < c3_open
        and c3_close < c1_open + 0.5 * (c1_close - c1_open)
    )


def is_hanging_man(row):
    geometry = _candle_geometry(row)
    candle_range = geometry["candle_range"]
    if candle_range <= 0:
        return False

    body = geometry["body"]
    lower_shadow = geometry["lower_shadow"]
    upper_shadow = geometry["upper_shadow"]
    low = geometry["low"]
    close = geometry["close"]
    body_bottom = geometry["body_bottom"]
    small_body_floor = max(candle_range * 0.05, 1e-9)

    return (
        body / candle_range <= 0.35
        and lower_shadow >= 2.0 * max(body, small_body_floor)
        and upper_shadow <= 0.5 * max(body, small_body_floor)
        and (
            body_bottom >= low + 0.55 * candle_range
            or close >= low + 0.55 * candle_range
        )
    )


def is_bullish_abandoned_baby(df, idx):
    if idx < 2:
        return False

    c1 = df.iloc[idx - 2]
    c2 = df.iloc[idx - 1]
    c3 = df.iloc[idx]
    g1 = _candle_geometry(c1)
    g2 = _candle_geometry(c2)
    g3 = _candle_geometry(c3)

    if g1["candle_range"] <= 0 or g2["candle_range"] <= 0 or g3["candle_range"] <= 0:
        return False

    tol = _gap_tolerance(
        c1["Open"],
        c1["Close"],
        c2["Open"],
        c2["Close"],
        c3["Open"],
        c3["Close"],
    )
    midpoint_c1 = c1["Close"] + 0.5 * (c1["Open"] - c1["Close"])

    return (
        c1["Close"] < c1["Open"]
        and g1["body"] / g1["candle_range"] >= 0.45
        and g2["body"] / g2["candle_range"] <= 0.12
        and c2["High"] < c1["Low"] + tol
        and c3["Close"] > c3["Open"]
        and g3["body"] / g3["candle_range"] >= 0.45
        and c3["Low"] > c2["High"] - tol
        and c3["Close"] > midpoint_c1
    )


def is_falling_three_methods(df, idx):
    if idx < 4:
        return False

    c1 = df.iloc[idx - 4]
    c2 = df.iloc[idx - 3]
    c3 = df.iloc[idx - 2]
    c4 = df.iloc[idx - 1]
    c5 = df.iloc[idx]
    g1 = _candle_geometry(c1)
    g5 = _candle_geometry(c5)

    if g1["candle_range"] <= 0 or g5["candle_range"] <= 0:
        return False

    tol = _gap_tolerance(c1["Open"], c1["Close"], c5["Open"], c5["Close"])
    inner_rows = [c2, c3, c4]
    body1 = max(g1["body"], 1e-9)

    for inner in inner_rows:
        gi = _candle_geometry(inner)
        if gi["candle_range"] <= 0:
            return False
        if gi["body"] > body1 * 0.6:
            return False
        if inner["High"] >= c1["Open"] + tol:
            return False
        if inner["Low"] <= c1["Close"] - tol:
            return False

    return (
        c1["Close"] < c1["Open"]
        and g1["body"] / g1["candle_range"] >= 0.45
        and c5["Close"] < c5["Open"]
        and g5["body"] / g5["candle_range"] >= 0.45
        and c5["Close"] < c1["Close"] - tol
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
    - **Vaaditaan laskutrendi:** Porrastava lasku (t-10 > t-5 > t-2 > t0) + MA-suodatin

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
    # Tarvitaan vähintään lookback_days + 10 (trenditarkistukseen) dataa
    if idx < max(lookback_days + 10, 34):
        return None

    # Varmistetaan että RSI-sarake on laskettu
    if "RSI" not in df.columns:
        return None

    # Tarkista että ollaan laskutrendissä
    if not _is_in_downtrend(df, idx, close_col=close_col, use_ma_filter=True):
        return None

    current_price = df.iloc[idx][close_col]

    if pd.isna(current_price):
        return None

    # Etsi nykyinen paikallinen minimi (t2)
    current_rsi = df.iloc[idx]["RSI"]

    if pd.isna(current_rsi):
        return None

    # Tarkista onko nykyinen indeksi paikallinen minimi hinnan suhteen
    # käyttäen vain mennyttä dataa (ei look-ahead)
    window = 7
    start_check = max(0, idx - window)
    end_check = idx + 1
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
        i_end = i + 1
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
    - **Vaaditaan nousutrendi:** Porrastava nousu (t-10 < t-5 < t-2 < t0) + MA-suodatin

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
    # Tarvitaan vähintään lookback_days + 10 (trenditarkistukseen) dataa
    if idx < max(lookback_days + 10, 34):
        return None

    # Varmistetaan että RSI-sarake on laskettu
    if "RSI" not in df.columns:
        return None

    # Tarkista että ollaan nousutrendissä
    if not _is_in_uptrend(df, idx, close_col=close_col, use_ma_filter=True):
        return None

    current_price = df.iloc[idx][close_col]

    if pd.isna(current_price):
        return None

    # Etsi nykyinen paikallinen maksimi (t2)
    current_rsi = df.iloc[idx]["RSI"]

    if pd.isna(current_rsi):
        return None

    # Tarkista onko nykyinen indeksi paikallinen maksimi hinnan suhteen
    # käyttäen vain mennyttä dataa (ei look-ahead)
    window = 7
    start_check = max(0, idx - window)
    end_check = idx + 1
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
        i_end = i + 1
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
