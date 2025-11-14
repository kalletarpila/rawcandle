"""
Tulostiedon generointi tietokantaan.

Tämä moduuli toteuttaa älykkään inkrementaalisen päivityslogiikan:
- Ensimmäisellä kerralla generoidaan kaikki data
- Seuraavilla kerroilla haetaan vain:
  1. Uudet päivämäärät olemassa oleville osakkeille
  2. Kaikki data täysin uusille osakkeille

Laskee KAIKKI 85 saraketta kuten alkuperäisessä generate_results.py:ssä (market + 84 mittaria).
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Callable, List, Optional, Tuple

import pandas as pd

from market_repository import ensure_market_schema, get_market_for_ticker

from .database_manager import DatabaseManager


class ResultsGenerator:
    """Generoi results_data tauluun kaikki 85 saraketta."""

    # Kynttilöiden numerointi (sama kuin generate_results.py)
    PATTERN_MAPPING = {
        "Hammer": 1,
        "Bullish Engulfing": 2,
        "Piercing Pattern": 3,
        "Three White Soldiers": 4,
        "Morning Star": 5,
        "Dragonfly Doji": 6,
        "Bullish Divergence": 7,
        "Bearish Divergence": 8,
        "downtrend": 0,
    }

    def __init__(self, db_manager: DatabaseManager, stock_db_path: str):
        """
        Args:
            db_manager: DatabaseManager instance (analysis.db)
            stock_db_path: Polku osakedata.db tiedostoon
        """
        self.db_manager = db_manager
        self.stock_db_path = stock_db_path
        self.logger = logging.getLogger(__name__)
        ensure_market_schema(stock_db_path)
        self._market_cache: dict[str, str] = {}

    def generate_results(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        ticker_filter: Optional[list] = None,
        pattern_filter: Optional[list] = None,
        divergence_combo_filter: bool = False,
    ) -> Tuple[int, float]:
        """
        Generoi tulokset tietokantaan inkrementaalisesti.

        Args:
            progress_callback: Callback(ticker, current, total)
            ticker_filter: Lista tickereistä joille generoidaan (None = kaikki)
            pattern_filter: Lista pattern-numeroista joita generoidaan (None = kaikki)
            divergence_combo_filter: Jos True, generoi vain kynttilämalli + divergenssi yhdistelmät

        Returns:
            (rows_inserted, processing_time_seconds)
        """
        import time

        start_time = time.time()

        try:
            # 1. Hae uudet findings
            findings = self._fetch_new_findings(
                ticker_filter=ticker_filter, pattern_filter=pattern_filter
            )
            if not findings:
                self.logger.info("No new findings to process")
                return 0, 0.0

            # Debug: Laske patternit
            pattern_counts = {}
            for f in findings:
                p = f.get("pattern", "unknown")
                pattern_counts[p] = pattern_counts.get(p, 0) + 1
            self.logger.info(f"📊 Haetut findings: {dict(pattern_counts)}")

            # 2. Suodata divergenssi-yhdistelmät jos valittu
            if divergence_combo_filter:
                findings = self._filter_divergence_combos(findings)
                if not findings:
                    self.logger.info("No divergence combos found after filtering")
                    return 0, 0.0

            self.logger.info(f"Processing {len(findings)} new findings")

            # 2. Ryhmittele tickereittäin
            by_ticker = {}
            for finding in findings:
                ticker = finding["ticker"]
                by_ticker.setdefault(ticker, []).append(finding)

            # 3. Prosessoi jokainen ticker
            total_tickers = len(by_ticker)
            total_inserted = 0

            for idx, (ticker, ticker_findings) in enumerate(by_ticker.items(), 1):
                # Tarkista keskeytys
                if progress_callback:
                    cancelled = progress_callback(ticker, idx, total_tickers)
                    if cancelled:
                        self.logger.info(
                            f"Generation cancelled by user at {idx}/{total_tickers}"
                        )
                        processing_time = time.time() - start_time
                        return total_inserted, processing_time

                # Hae osakedata tälle tickerille
                stock_data = self._fetch_stock_data(ticker)
                if stock_data is None or stock_data.empty:
                    self.logger.warning(f"No stock data for {ticker}")
                    continue

                ticker_market = self._get_market(ticker)

                # Prosessoi kaikki findingit tälle tickerille
                ticker_results = []
                processed_count = 0
                for finding in ticker_findings:
                    result = self._process_finding(
                        finding, stock_data, ticker, ticker_market
                    )
                    if result:
                        ticker_results.append(result)
                        processed_count += 1

                # Debug downtrend-progress
                if any(f.get("pattern") == "downtrend" for f in ticker_findings):
                    self.logger.info(
                        f"🔍 Downtrend {ticker}: {processed_count}/{len(ticker_findings)} käsitelty onnistuneesti"
                    )

                # Tallenna tämän tickerin tulokset heti kantaan
                if ticker_results:
                    inserted = self.db_manager.bulk_insert_results(
                        ticker_results, batch_size=100
                    )
                    total_inserted += inserted
                    self.logger.debug(
                        f"Inserted {inserted} rows for {ticker} ({idx}/{total_tickers})"
                    )

            # 4. Tallenna metadata lopuksi
            if total_inserted > 0:
                processing_time = time.time() - start_time
                self.db_manager.insert_results_metadata(
                    total_rows=total_inserted, processing_time=processing_time
                )
                self.logger.info(
                    f"Total inserted {total_inserted} rows to results_data"
                )

                return total_inserted, processing_time

            return 0, 0.0

        except Exception as e:
            self.logger.error(f"Generate results failed: {e}", exc_info=True)
            return 0, 0.0

    def _filter_divergence_combos(self, findings: List[dict]) -> List[dict]:
        """
        Suodata vain kynttilämalli + divergenssi yhdistelmät.

        Palauttaa vain ne findings joissa samalla tickerillä samana päivänä on sekä:
        - Kynttilämalli (pattern: Hammer, Bullish Engulfing, Piercing Pattern, Three White Soldiers, Morning Star, Dragonfly Doji)
        - Divergenssi (pattern: Bullish Divergence, Bearish Divergence)

        Args:
            findings: Lista findings dictejä

        Returns:
            Suodatettu lista findings dictejä
        """
        # Kynttilämalli patternit (analysis_findings taulussa pattern-nimi)
        candle_patterns = {
            "downtrend",
            "Hammer",
            "Bullish Engulfing",
            "Piercing Pattern",
            "Three White Soldiers",
            "Morning Star",
            "Dragonfly Doji",
        }

        # Divergenssi patternit
        divergence_patterns = {"Bullish Divergence", "Bearish Divergence"}

        # Rakenna (ticker, date) -> patterns mapping
        ticker_date_patterns = {}
        for finding in findings:
            key = (finding.get("ticker"), finding.get("pvm"))
            pattern = finding.get("pattern")

            if key not in ticker_date_patterns:
                ticker_date_patterns[key] = set()
            ticker_date_patterns[key].add(pattern)

        # Etsi (ticker, date) yhdistelmät joissa on sekä kynttilämalli että divergenssi
        combo_keys = set()
        for key, patterns in ticker_date_patterns.items():
            has_candle = bool(patterns & candle_patterns)
            has_divergence = bool(patterns & divergence_patterns)

            if has_candle and has_divergence:
                combo_keys.add(key)

        # Suodata findings jotka kuuluvat combo_keys:iin
        filtered = [
            f for f in findings if (f.get("ticker"), f.get("pvm")) in combo_keys
        ]

        self.logger.info(
            f"Divergence combo filter: {len(filtered)}/{len(findings)} findings "
            f"({len(combo_keys)} unique ticker+date combos)"
        )

        return filtered

    def _fetch_new_findings(
        self,
        ticker_filter: Optional[list] = None,
        pattern_filter: Optional[list] = None,
    ) -> List[dict]:
        """
        Hae uudet findings inkrementaalisesti (two-query approach).

        Args:
            ticker_filter: Lista tickereistä joita haetaan (None = kaikki)
            pattern_filter: Lista pattern-nimistä joita haetaan (None = kaikki)
                           Esim: ["Hammer", "Bullish Engulfing"]

        Returns:
            Lista findings dictejä
        """
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            # Muunna pattern_filter numeroiksi jos tarvitaan max_date/existing_tickers hakua varten
            pattern_number_filter = None
            if pattern_filter and all(isinstance(p, int) for p in pattern_filter):
                pattern_number_filter = pattern_filter
            elif pattern_filter:
                # Käänteinen mappaus: nimi -> numero
                pattern_numbers = {
                    "downtrend": 0,
                    "Hammer": 1,
                    "Bullish Engulfing": 2,
                    "Piercing Pattern": 3,
                    "Three White Soldiers": 4,
                    "Morning Star": 5,
                    "Dragonfly Doji": 6,
                    "Bullish Divergence": 7,
                    "Bearish Divergence": 8,
                }
                pattern_number_filter = [
                    pattern_numbers[name]
                    for name in pattern_filter
                    if name in pattern_numbers
                ]

            # Tarkista onko results_data taulussa dataa (suodatettuna patternilla)
            max_date = self.db_manager.get_results_max_date(
                pattern_filter=pattern_number_filter
            )
            existing_tickers = self.db_manager.get_existing_results_tickers(
                pattern_filter=pattern_number_filter
            )

            # Jos pattern_filter on numeroita, muunna ne nimiksi
            if pattern_filter and all(isinstance(p, int) for p in pattern_filter):
                # Käänteinen mappaus: numero -> nimi
                pattern_names = {
                    0: "downtrend",
                    1: "Hammer",
                    2: "Bullish Engulfing",
                    3: "Piercing Pattern",
                    4: "Three White Soldiers",
                    5: "Morning Star",
                    6: "Dragonfly Doji",
                    7: "Bullish Divergence",
                    8: "Bearish Divergence",
                }
                pattern_filter = [
                    pattern_names[num] for num in pattern_filter if num in pattern_names
                ]
                self.logger.debug(
                    f"Converted pattern numbers to names: {pattern_filter}"
                )

            # Rakenna suodatinlausekkeet
            filter_clauses = []
            filter_params = []

            if ticker_filter:
                placeholders = ",".join("?" * len(ticker_filter))
                filter_clauses.append(f"ticker IN ({placeholders})")
                filter_params.extend(ticker_filter)

            if pattern_filter:
                placeholders = ",".join("?" * len(pattern_filter))
                filter_clauses.append(f"pattern IN ({placeholders})")
                filter_params.extend(pattern_filter)

            filter_sql = (
                " AND " + " AND ".join(filter_clauses) if filter_clauses else ""
            )
            has_filter = bool(filter_clauses)

            if max_date is None:
                # Ensimmäinen generointi - hae kaikki
                self.logger.info("First generation - fetching all findings")
                cursor.execute(
                    f"""
                    SELECT ticker, date, pattern, signal_strength, rsi14
                    FROM analysis_findings
                    WHERE 1=1{filter_sql}
                    ORDER BY date DESC
                    """,
                    filter_params,
                )
            else:
                # Inkrementaalinen päivitys - two-query approach
                self.logger.info(
                    f"Incremental update - max_date: {max_date}, existing tickers: {len(existing_tickers)}"
                )

                if existing_tickers:
                    # Query 1: Uudet päivämäärät olemassa oleville tickereille
                    # Query 2: Kaikki datat uusille tickereille
                    existing_placeholders = ",".join("?" * len(existing_tickers))

                    params = [max_date]
                    if has_filter:
                        params += filter_params
                    params += list(existing_tickers)
                    if has_filter:
                        params += filter_params

                    cursor.execute(
                        f"""
                        SELECT ticker, date, pattern, signal_strength, rsi14
                        FROM analysis_findings
                        WHERE date > ?{filter_sql}
                        UNION
                        SELECT ticker, date, pattern, signal_strength, rsi14
                        FROM analysis_findings
                        WHERE ticker NOT IN ({existing_placeholders}){filter_sql}
                        ORDER BY date DESC
                        """,
                        params,
                    )
                else:
                    # Ei olemassa olevia tickereitä, hae kaikki
                    cursor.execute(
                        f"""
                        SELECT ticker, date, pattern, signal_strength, rsi14
                        FROM analysis_findings
                        WHERE 1=1{filter_sql}
                        ORDER BY date DESC
                        """,
                        filter_params,
                    )

            rows = cursor.fetchall()
            findings = []
            for row in rows:
                ticker, date, pattern, signal_strength, rsi14 = row
                findings.append(
                    {
                        "ticker": ticker,
                        "date": date,
                        "pattern": pattern,
                        "signal_strength": signal_strength,
                        "rsi14": rsi14,
                    }
                )

            return findings

        except Exception as e:
            self.logger.error(f"Fetch new findings failed: {e}")
            return []

    def _fetch_stock_data(self, ticker: str) -> pd.DataFrame:
        """
        Hae osakkeen hintadata osakedata.db:stä.

        Args:
            ticker: Osakkeen symboli

        Returns:
            DataFrame jossa sarakkeet: pvm, open, high, low, close, volume
        """
        try:
            conn = sqlite3.connect(self.stock_db_path)
            df = pd.read_sql_query(
                """
                SELECT pvm, open, high, low, close, volume
                FROM osakedata
                WHERE osake = ?
                ORDER BY pvm ASC
                """,
                conn,
                params=(ticker,),
            )
            conn.close()

            if df.empty:
                return pd.DataFrame()

            # Normalisoi päivämäärät
            df["pvm"] = pd.to_datetime(df["pvm"]).dt.strftime("%Y-%m-%d")
            return df

        except Exception as e:
            self.logger.error(f"Fetch stock data failed for {ticker}: {e}")
            return pd.DataFrame()

    def _get_market(self, ticker: str) -> str:
        """Palauta tickerin markkina osakedata-kannasta (välimuistissa)."""
        cached = self._market_cache.get(ticker)
        if cached:
            return cached
        try:
            market = get_market_for_ticker(
                ticker, db_path=self.stock_db_path, default="usa"
            )
        except Exception:
            market = "usa"
        market = market or "usa"
        self._market_cache[ticker] = market
        return market

    def _get_index_data(self, ticker: str, date: str, offset: int) -> Optional[float]:
        """
        Hae indeksin close-arvo tietylle offsetille.

        Args:
            ticker: Indeksin ticker (^GSPC tai ^NDX)
            date: Päivämäärä (t0)
            offset: Offset päivistä (negatiivinen = menneisyys, positiivinen = tulevaisuus)

        Returns:
            Close-arvo tai None
        """
        try:
            conn = sqlite3.connect(self.stock_db_path)
            df = pd.read_sql_query(
                """
                SELECT pvm, close
                FROM osakedata
                WHERE osake = ?
                ORDER BY pvm ASC
                """,
                conn,
                params=(ticker,),
            )
            conn.close()

            if df.empty:
                return None

            df["pvm"] = pd.to_datetime(df["pvm"]).dt.strftime("%Y-%m-%d")
            date_to_idx = {str(row["pvm"]): idx for idx, row in df.iterrows()}

            if date not in date_to_idx:
                return None

            target_idx = date_to_idx[date] + offset
            if target_idx < 0 or target_idx >= len(df):
                return None

            return float(df.iloc[target_idx]["close"])

        except Exception as e:
            self.logger.error(f"Get index data failed for {ticker}: {e}")
            return None

    def _process_finding(
        self, finding: dict, stock_df: pd.DataFrame, ticker: str, market: str
    ) -> Optional[dict]:
        """
        Käsittele yksittäinen finding ja laske KAIKKI 84 saraketta.

        Args:
            finding: Finding dict (ticker, date, pattern, signal_strength, rsi14)
            stock_df: Osakkeen DataFrame
            ticker: Ticker string

        Returns:
            Dictionary kaikilla 84 sarakkeella tai None
        """
        try:
            date = finding["date"]
            pattern = finding["pattern"]
            signal_strength = finding["signal_strength"]
            rsi14_from_db = finding.get("rsi14")

            # Tarkista onko ticker indeksi
            is_index = ticker.startswith("^")

            # Etsi päivämäärän indeksi
            date_to_idx = {str(row["pvm"]): idx for idx, row in stock_df.iterrows()}
            if date not in date_to_idx:
                if pattern == "downtrend":
                    self.logger.warning(
                        f"⚠️ Downtrend {ticker} {date}: Päivämäärää ei löydy stock_df:stä"
                    )
                return None

            idx = date_to_idx[date]

            # Tarkista että on tarpeeksi dataa (20 päivää taakse, 20 eteenpäin)
            if idx < 20 or idx + 20 >= len(stock_df):
                if pattern == "downtrend":
                    self.logger.warning(
                        f"⚠️ Downtrend {ticker} {date}: Ei tarpeeksi dataa (idx={idx}, len={len(stock_df)}, tarvitaan 20 edellä ja jälkeen)"
                    )
                return None

            # Hae t0 rivit
            r0 = stock_df.iloc[idx]
            t0_low = float(r0["low"]) if pd.notna(r0["low"]) else None
            t0_high = float(r0["high"]) if pd.notna(r0["high"]) else None
            t0_open = float(r0["open"]) if pd.notna(r0["open"]) else None
            t0_close = float(r0["close"]) if pd.notna(r0["close"]) else None

            if not t0_low or not t0_close or t0_low <= 0 or t0_close <= 0:
                return None

            # === HELPER FUNCTIONS ===

            def safe_float(value):
                """Muunna arvo floatiksi tai None"""
                try:
                    if pd.isna(value):
                        return None
                    return float(value)
                except Exception:
                    return None

            def calc_candle_details(row_data):
                """Laske kynttilän detaljit (alin, ylin, bodi%, väri)"""
                if row_data is None:
                    return None, None, None, None

                low = safe_float(row_data["low"])
                high = safe_float(row_data["high"])
                open_val = safe_float(row_data["open"])
                close_val = safe_float(row_data["close"])

                if any(x is None for x in [low, high, open_val, close_val]):
                    return None, None, None, None

                # Normalisoi t0_low:lla
                norm_low = (low / t0_low * 100) if t0_low > 0 else None
                norm_high = (high / t0_low * 100) if t0_low > 0 else None

                # Body prosentti
                candle_range = high - low
                body_size = abs(close_val - open_val)
                body_percent = (
                    (body_size / candle_range * 100) if candle_range > 0 else 0
                )

                # Väri: 1=vihreä (close > open), 0=punainen
                color = 1 if close_val > open_val else 0

                return norm_low, norm_high, body_percent, color

            def get_normalized_close(offset):
                """Hae normalisoitu close-arvo offsetille"""
                target_idx = idx + offset
                if target_idx < 0 or target_idx >= len(stock_df):
                    return None
                target_row = stock_df.iloc[target_idx]
                close_val = safe_float(target_row["close"])

                if close_val is None:
                    return None

                if is_index:
                    # Indeksit: normalisoi t0_close=100
                    return (close_val / t0_close * 100) if t0_close > 0 else None
                else:
                    # Osakkeet: normalisoi t0_low=100
                    return (close_val / t0_low * 100) if t0_low > 0 else None

            def calc_volatility(days_back):
                """Laske volatiliteetti (stdev normalisoiduista arvoista)"""
                if idx - days_back < 0:
                    return None
                start_idx = idx - days_back
                end_idx = idx - 1  # Ei sisällä t0
                subset = stock_df.iloc[start_idx : end_idx + 1]

                values = [safe_float(row["close"]) for _, row in subset.iterrows()]
                values = [v for v in values if v is not None]
                if len(values) < 2:
                    return None

                # Normalisoi t0_low:lla
                norm_values = [(v / t0_low) * 100 for v in values]
                try:
                    return pstdev(norm_values)
                except Exception:
                    return None

            def calc_volume_ratio(days_count, offset_start):
                """Laske volyymisuhde speksin mukaan"""
                try:
                    # Laske periodin volyymi keskiarvo
                    start_idx = idx + offset_start
                    end_idx = start_idx + days_count - 1

                    if start_idx < 0 or end_idx >= len(stock_df):
                        return None

                    subset = stock_df.iloc[start_idx : end_idx + 1]
                    volumes = [
                        safe_float(row["volume"]) for _, row in subset.iterrows()
                    ]
                    volumes = [v for v in volumes if v is not None and v > 0]

                    if not volumes:
                        return None

                    period_avg = mean(volumes)

                    # Laske 100-päivän keskiarvo päätyen t-1:een
                    hundred_start = max(0, idx - 100)
                    hundred_end = idx - 1

                    if hundred_end < hundred_start:
                        return None

                    hundred_subset = stock_df.iloc[hundred_start : hundred_end + 1]
                    hundred_volumes = [
                        safe_float(row["volume"])
                        for _, row in hundred_subset.iterrows()
                    ]
                    hundred_volumes = [
                        v for v in hundred_volumes if v is not None and v > 0
                    ]

                    if not hundred_volumes:
                        return None

                    hundred_avg = mean(hundred_volumes)

                    if hundred_avg <= 0:
                        return None

                    return (period_avg / hundred_avg) * 100

                except Exception:
                    return None

            def calc_ma_normalized(days_offset, ma_period):
                """Laske liukuva keskiarvo normalisoituna"""
                end_idx = idx + days_offset
                start_idx = end_idx - ma_period + 1

                if start_idx < 0 or end_idx < 0 or end_idx >= len(stock_df):
                    return None

                subset = stock_df.iloc[start_idx : end_idx + 1]
                values = [safe_float(row["close"]) for _, row in subset.iterrows()]
                values = [v for v in values if v is not None]

                if len(values) != ma_period:
                    return None

                ma_val = mean(values)

                if is_index:
                    return (ma_val / t0_close * 100) if t0_close > 0 else None
                else:
                    return (ma_val / t0_low * 100) if t0_low > 0 else None

            def get_index_normalized(index_ticker, offset):
                """Hae indeksin arvo normalisoituna"""
                index_t0_close = self._get_index_data(index_ticker, date, 0)
                if index_t0_close is None or index_t0_close <= 0:
                    return None

                index_value = self._get_index_data(index_ticker, date, offset)
                return (
                    (index_value / index_t0_close * 100)
                    if index_value is not None
                    else None
                )

            # === LASKE KAIKKI SARAKKEET ===

            # Kynttilä detaljit (5-16)
            r_m1 = stock_df.iloc[idx - 1] if idx > 0 else None
            r1 = stock_df.iloc[idx + 1] if idx + 1 < len(stock_df) else None

            t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour = calc_candle_details(r_m1)
            t0_alin, t0_ylin, t0_bodi, t0_bodi_colour = calc_candle_details(r0)
            t1_alin, t1_ylin, t1_bodi, t1_bodi_colour = calc_candle_details(r1)

            # Historialliset hinnat (17-21)
            t_2 = get_normalized_close(-2)
            t_5 = get_normalized_close(-5)
            t_10 = get_normalized_close(-10)
            t_15 = get_normalized_close(-15)
            t_20 = get_normalized_close(-20)

            # Volatiliteetti (22-26)
            t_2_hajonta = calc_volatility(2)
            t_5_hajonta = calc_volatility(5)
            t_10_hajonta = calc_volatility(10)
            t_15_hajonta = calc_volatility(15)
            t_20_hajonta = calc_volatility(20)

            # Tulevat hinnat (27-30)
            t2 = get_normalized_close(2)
            t5 = get_normalized_close(5)
            t10 = get_normalized_close(10)
            t20 = get_normalized_close(20)

            # Volyymit (31-40)
            t_2_volyymi = calc_volume_ratio(2, -2)
            t_5_volyymi = calc_volume_ratio(5, -5)
            t_10_volyymi = calc_volume_ratio(10, -10)
            t_15_volyymi = calc_volume_ratio(15, -15)
            t_20_volyymi = calc_volume_ratio(20, -20)

            # t0 volyymi
            t0_volume = safe_float(r0["volume"])
            hundred_start = max(0, idx - 100)
            hundred_end = idx - 1
            if hundred_end >= hundred_start:
                hundred_subset = stock_df.iloc[hundred_start : hundred_end + 1]
                hundred_volumes = [
                    safe_float(row["volume"]) for _, row in hundred_subset.iterrows()
                ]
                hundred_volumes = [
                    v for v in hundred_volumes if v is not None and v > 0
                ]
                hundred_avg = mean(hundred_volumes) if hundred_volumes else None
                t0_volyymi = (
                    (t0_volume / hundred_avg) * 100
                    if t0_volume and hundred_avg and hundred_avg > 0
                    else None
                )
            else:
                t0_volyymi = None

            t2_volyymi = calc_volume_ratio(2, 1)
            t5_volyymi = calc_volume_ratio(5, 1)
            t10_volyymi = calc_volume_ratio(10, 1)
            t20_volyymi = calc_volume_ratio(20, 1)

            # Liukuvat keskiarvot (41-57)
            t_2_5p_liukuva = calc_ma_normalized(-2, 5)
            t_2_10p_liukuva = calc_ma_normalized(-2, 10)
            t_2_20p_liukuva = calc_ma_normalized(-2, 20)

            t_5_5p_liukuva = calc_ma_normalized(-5, 5)
            t_5_10p_liukuva = calc_ma_normalized(-5, 10)
            t_5_20p_liukuva = calc_ma_normalized(-5, 20)

            t_10_5p_liukuva = calc_ma_normalized(-10, 5)
            t_10_10p_liukuva = calc_ma_normalized(-10, 10)
            t_10_20p_liukuva = calc_ma_normalized(-10, 20)

            t_15_5p_liukuva = calc_ma_normalized(-15, 5)
            t_15_10p_liukuva = calc_ma_normalized(-15, 10)
            t_15_20p_liukuva = calc_ma_normalized(-15, 20)

            t_20_5p_liukuva = calc_ma_normalized(-20, 5)
            t_20_10p_liukuva = calc_ma_normalized(-20, 10)
            t_20_20p_liukuva = calc_ma_normalized(-20, 20)

            t0_50p_liukuva = calc_ma_normalized(0, 50)
            t0_200p_liukuva = calc_ma_normalized(0, 200) if idx >= 199 else 0

            # S&P 500 indeksi (58-68)
            SPX_0 = 100.0  # t0_close normalisoitu 100:ksi
            SPX_2 = get_index_normalized("^GSPC", -2)
            SPX_5 = get_index_normalized("^GSPC", -5)
            SPX_10 = get_index_normalized("^GSPC", -10)
            SPX_15 = get_index_normalized("^GSPC", -15)
            SPX_20 = get_index_normalized("^GSPC", -20)
            SPX2 = get_index_normalized("^GSPC", 2)
            SPX5 = get_index_normalized("^GSPC", 5)
            SPX10 = get_index_normalized("^GSPC", 10)
            SPX15 = get_index_normalized("^GSPC", 15)
            SPX20 = get_index_normalized("^GSPC", 20)

            # Nasdaq 100 indeksi (69-79)
            NDX_0 = 100.0
            NDX_2 = get_index_normalized("^NDX", -2)
            NDX_5 = get_index_normalized("^NDX", -5)
            NDX_10 = get_index_normalized("^NDX", -10)
            NDX_15 = get_index_normalized("^NDX", -15)
            NDX_20 = get_index_normalized("^NDX", -20)
            NDX2 = get_index_normalized("^NDX", 2)
            NDX5 = get_index_normalized("^NDX", 5)
            NDX10 = get_index_normalized("^NDX", 10)
            NDX15 = get_index_normalized("^NDX", 15)
            NDX20 = get_index_normalized("^NDX", 20)

            # RSI (80)
            RSI14_t0 = float(rsi14_from_db) if rsi14_from_db is not None else None

            # Normalisoitu close (81)
            t0_close_norm = (t0_close / t0_low * 100) if t0_low > 0 else None

            # Divergenssit (82-83)
            # Hae divergenssit t0, t-1, t-2, t-3 päiviltä
            check_dates = []
            for offset in [0, -1, -2, -3]:
                check_idx = idx + offset
                if 0 <= check_idx < len(stock_df):
                    check_date = str(stock_df.iloc[check_idx]["pvm"])
                    check_dates.append(check_date)

            bearish_divergence, bullish_divergence = (
                self.db_manager.get_divergences_for_dates(
                    ticker=ticker, dates=check_dates
                )
            )

            # Pattern numero (3)
            candle_pattern = self.PATTERN_MAPPING.get(pattern, 0)

            # Viikonpäivä (84)
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday = date_obj.isoweekday()  # 1=Ma, 7=Su

            # Muodosta tulos dictionary (KAIKKI 85 saraketta)
            return {
                "ticker": ticker,
                "date": date,
                "market": market,
                "candle_pattern": candle_pattern,
                "signal_strength": signal_strength,
                "t_1_alin": t_1_alin,
                "t_1_ylin": t_1_ylin,
                "t_1_bodi": t_1_bodi,
                "t_1_bodi_colour": t_1_bodi_colour,
                "t0_alin": t0_alin,
                "t0_ylin": t0_ylin,
                "t0_bodi": t0_bodi,
                "t0_bodi_colour": t0_bodi_colour,
                "t1_alin": t1_alin,
                "t1_ylin": t1_ylin,
                "t1_bodi": t1_bodi,
                "t1_bodi_colour": t1_bodi_colour,
                "t_2": t_2,
                "t_5": t_5,
                "t_10": t_10,
                "t_15": t_15,
                "t_20": t_20,
                "t_2_hajonta": t_2_hajonta,
                "t_5_hajonta": t_5_hajonta,
                "t_10_hajonta": t_10_hajonta,
                "t_15_hajonta": t_15_hajonta,
                "t_20_hajonta": t_20_hajonta,
                "t2": t2,
                "t5": t5,
                "t10": t10,
                "t20": t20,
                "t_2_volyymi": t_2_volyymi,
                "t_5_volyymi": t_5_volyymi,
                "t_10_volyymi": t_10_volyymi,
                "t_15_volyymi": t_15_volyymi,
                "t_20_volyymi": t_20_volyymi,
                "t0_volyymi": t0_volyymi,
                "t2_volyymi": t2_volyymi,
                "t5_volyymi": t5_volyymi,
                "t10_volyymi": t10_volyymi,
                "t20_volyymi": t20_volyymi,
                "t_2_5p_liukuva": t_2_5p_liukuva,
                "t_2_10p_liukuva": t_2_10p_liukuva,
                "t_2_20p_liukuva": t_2_20p_liukuva,
                "t_5_5p_liukuva": t_5_5p_liukuva,
                "t_5_10p_liukuva": t_5_10p_liukuva,
                "t_5_20p_liukuva": t_5_20p_liukuva,
                "t_10_5p_liukuva": t_10_5p_liukuva,
                "t_10_10p_liukuva": t_10_10p_liukuva,
                "t_10_20p_liukuva": t_10_20p_liukuva,
                "t_15_5p_liukuva": t_15_5p_liukuva,
                "t_15_10p_liukuva": t_15_10p_liukuva,
                "t_15_20p_liukuva": t_15_20p_liukuva,
                "t_20_5p_liukuva": t_20_5p_liukuva,
                "t_20_10p_liukuva": t_20_10p_liukuva,
                "t_20_20p_liukuva": t_20_20p_liukuva,
                "t0_50p_liukuva": t0_50p_liukuva,
                "t0_200p_liukuva": t0_200p_liukuva,
                "SPX_0": SPX_0,
                "SPX_2": SPX_2,
                "SPX_5": SPX_5,
                "SPX_10": SPX_10,
                "SPX_15": SPX_15,
                "SPX_20": SPX_20,
                "SPX2": SPX2,
                "SPX5": SPX5,
                "SPX10": SPX10,
                "SPX15": SPX15,
                "SPX20": SPX20,
                "NDX_0": NDX_0,
                "NDX_2": NDX_2,
                "NDX_5": NDX_5,
                "NDX_10": NDX_10,
                "NDX_15": NDX_15,
                "NDX_20": NDX_20,
                "NDX2": NDX2,
                "NDX5": NDX5,
                "NDX10": NDX10,
                "NDX15": NDX15,
                "NDX20": NDX20,
                "RSI14_t0": RSI14_t0,
                "t0_close_norm": t0_close_norm,
                "bearish_divergence": bearish_divergence,
                "bullish_divergence": bullish_divergence,
                "weekday": weekday,
            }

        except Exception as e:
            self.logger.error(f"Process finding failed: {e}", exc_info=True)
            return None


if __name__ == "__main__":
    # Testi
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    db_manager = DatabaseManager("analysis.db")
    stock_db = "data/osakedata.db"

    generator = ResultsGenerator(db_manager, stock_db)

    def progress(ticker, current, total):
        print(f"Progress: {ticker} ({current}/{total})")

    rows, time_taken = generator.generate_results(progress_callback=progress)
    print(f"\nGenerated {rows} rows in {time_taken:.2f}s")

    # Hae metadata
    metadata = db_manager.get_latest_results_metadata()
    print(f"Metadata: {metadata}")
