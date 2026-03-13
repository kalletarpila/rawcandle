"""
Tulostiedon generointi tietokantaan.

Tämä moduuli toteuttaa älykkään inkrementaalisen päivityslogiikan:
- Ensimmäisellä kerralla generoidaan kaikki data
- Seuraavilla kerroilla haetaan vain:
  1. Uudet päivämäärät olemassa oleville osakkeille
  2. Kaikki data täysin uusille osakkeille

Laskee KAIKKI 89 saraketta kuten laajennetussa generate_results.py:ssä (market + 88 mittaria, mukaan lukien BullDiv-mittarit).
"""

import logging
import sqlite3
from datetime import datetime
from statistics import mean, pstdev
from typing import Callable, List, Optional, Tuple

import pandas as pd

from market_repository import ensure_market_schema, get_market_for_ticker
from .database_manager import DatabaseManager
from .preprocess_utils import load_blackout_dates

CRISIS_START = datetime(2025, 3, 1).date()
CRISIS_END = datetime(2025, 4, 30).date()


class ResultsGenerator:
    """Generoi results_data tauluun kaikki 89 saraketta."""

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
        "BullDiv & Hammer": 71,
        "BullDiv & Bullish Engulfing": 72,
        "BullDiv & Piercing Pattern": 73,
        "BullDiv & Three White Soldiers": 74,
        "BullDiv & Morning Star": 75,
        "BullDiv & Dragonfly Doji": 76,
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
        self._blackout_by_ticker: dict[str, pd.DataFrame] = {}
        self._sector_warning_logged = False
        self._load_blackout_data()
        self._parity_checked = False

    def generate_results(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        ticker_filter: Optional[list] = None,
        pattern_filter: Optional[list] = None,
        divergence_combo_filter: bool = False,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[int, float]:
        """
        Generoi tulokset tietokantaan inkrementaalisesti.

        Args:
            progress_callback: Callback(ticker, current, total)
            ticker_filter: Lista tickereistä joille generoidaan (None = kaikki)
            pattern_filter: Lista pattern-numeroista joita generoidaan (None = kaikki)
            divergence_combo_filter: Jos True, generoi vain kynttilämalli + divergenssi yhdistelmät
            start_date: Alkupäivämäärä YYYY-MM-DD (valinnainen, ohittaa inkrementaalisen logiikan)
            end_date: Loppupäivämäärä YYYY-MM-DD (valinnainen, ohittaa inkrementaalisen logiikan)

        Returns:
            (rows_inserted, processing_time_seconds)
        """
        import time

        start_time = time.time()

        try:
            # 1. Hae uudet findings
            findings = self._fetch_new_findings(
                ticker_filter=ticker_filter,
                pattern_filter=pattern_filter,
                start_date=start_date,
                end_date=end_date,
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

                aggregates_by_date = {}

                # Prosessoi kaikki findingit tälle tickerille
                ticker_results = []
                processed_count = 0
                for finding in ticker_findings:
                    result = self._process_finding(
                        finding,
                        stock_data,
                        ticker,
                        ticker_market,
                        aggregates_by_date.get(finding["date"]),
                    )
                    if result:
                        if not self._parity_checked:
                            self._schema_parity_check(result)
                            self._parity_checked = True
                        ticker_results.append(result)
                        processed_count += 1

                # Debug downtrend-progress
                if any(f.get("pattern") == "downtrend" for f in ticker_findings):
                    self.logger.info(
                        f"🔍 Downtrend {ticker}: {processed_count}/{len(ticker_findings)} käsitelty onnistuneesti"
                    )

                if not ticker_results:
                    continue

                inserted = self.db_manager.bulk_insert_results(
                    ticker_results, batch_size=100
                )
                total_inserted += inserted
                self.logger.debug(
                    f"Inserted {inserted} event rows for {ticker} ({idx}/{total_tickers})"
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

        # Valmiiksi koodatut kombokuviot (71–76)
        combo_patterns = {
            "BullDiv & Hammer",
            "BullDiv & Bullish Engulfing",
            "BullDiv & Piercing Pattern",
            "BullDiv & Three White Soldiers",
            "BullDiv & Morning Star",
            "BullDiv & Dragonfly Doji",
        }

        # Divergenssi patternit
        divergence_patterns = {"Bullish Divergence", "Bearish Divergence"}

        # Rakenna (ticker, date) -> patterns mapping
        ticker_date_patterns = {}
        for finding in findings:
            key = (finding.get("ticker"), finding.get("date"))
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

        # Lisää jo valmiiksi kombokoodatut rivit
        combo_keys |= {
            (f.get("ticker"), f.get("date"))
            for f in findings
            if f.get("pattern") in combo_patterns
        }

        # Lisää t0/t-1 divergenssiparit kannasta (koodit 1–6)
        try:
            combo_keys |= self.db_manager.get_divergence_combo_pairs(
                candle_patterns=[1, 2, 3, 4, 5, 6]
            )
        except Exception as exc:
            self.logger.warning(f"Divergence combo pair fetch failed: {exc}")

        # Suodata findings jotka kuuluvat combo_keys:iin
        filtered: List[dict] = []
        seen_keys = set()
        for f in findings:
            key = (f.get("ticker"), f.get("date"))
            if key in combo_keys and key not in seen_keys:
                filtered.append(f)
                seen_keys.add(key)

        self.logger.info(
            f"Divergence combo filter: {len(filtered)}/{len(findings)} findings "
            f"({len(combo_keys)} unique ticker+date combos)"
        )

        return filtered

    def _fetch_new_findings(
        self,
        ticker_filter: Optional[list] = None,
        pattern_filter: Optional[list] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[dict]:
        """
        Hae uudet findings inkrementaalisesti (two-query approach).

        Args:
            ticker_filter: Lista tickereistä joita haetaan (None = kaikki)
            pattern_filter: Lista pattern-nimistä joita haetaan (None = kaikki)
                           Esim: ["Hammer", "Bullish Engulfing"]
            start_date: Alkupäivämäärä YYYY-MM-DD (valinnainen, ohittaa inkrementaalisen logiikan)
            end_date: Loppupäivämäärä YYYY-MM-DD (valinnainen, ohittaa inkrementaalisen logiikan)

        Returns:
            Lista findings dictejä
        """
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            # Muunna pattern_filter numeroiksi jos tarvitaan max_date/existing_tickers hakua varten
            pattern_number_filter = None
            pattern_numbers = dict(self.PATTERN_MAPPING)
            if pattern_filter and all(isinstance(p, int) for p in pattern_filter):
                pattern_number_filter = pattern_filter
            elif pattern_filter:
                # Käänteinen mappaus: nimi -> numero
                pattern_number_filter = [
                    pattern_numbers[name]
                    for name in pattern_filter
                    if name in pattern_numbers
                ]

            # Tarkista onko results_data taulussa dataa (suodatettuna patternilla)
            # Jos päivämääräsuodatus on annettu, ohitetaan inkrementaalinen logiikka
            if start_date or end_date:
                max_date = None
                existing_tickers = set()
                self.logger.info(
                    f"Date filter specified (start: {start_date}, end: {end_date}) - fetching all findings in range"
                )
            else:
                max_date = self.db_manager.get_results_max_date(
                    pattern_filter=pattern_number_filter
                )
                existing_tickers = self.db_manager.get_existing_results_tickers(
                    pattern_filter=pattern_number_filter
                )

            # Jos pattern_filter on numeroita, muunna ne nimiksi
            if pattern_filter and all(isinstance(p, int) for p in pattern_filter):
                # Käänteinen mappaus: numero -> nimi
                pattern_names = {num: name for name, num in pattern_numbers.items()}
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

            # Lisää päivämääräsuodatus jos annettu
            if start_date:
                filter_clauses.append("date >= ?")
                filter_params.append(start_date)
            if end_date:
                filter_clauses.append("date <= ?")
                filter_params.append(end_date)

            filter_sql = (
                " AND " + " AND ".join(filter_clauses) if filter_clauses else ""
            )
            has_filter = bool(filter_clauses)

            if max_date is None or start_date or end_date:
                # Ensimmäinen generointi tai päivämääräsuodatus - hae kaikki
                mode_desc = (
                    "First generation"
                    if max_date is None
                    else f"Date filter ({start_date or 'start'} to {end_date or 'end'})"
                )
                self.logger.info(f"{mode_desc} - fetching all findings")
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
        self,
        finding: dict,
        stock_df: pd.DataFrame,
        ticker: str,
        market: str,
        same_day_features: Optional[dict] = None,
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
            finding_rsi14_t0 = (
                float(rsi14_from_db) if rsi14_from_db is not None else None
            )

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

            def calc_candle_details(row_data, base_normalizer: Optional[float]):
                """Laske kynttilän detaljit (alin, ylin, bodi%, väri)"""
                if row_data is None:
                    return None, None, None, None

                low = safe_float(row_data["low"])
                high = safe_float(row_data["high"])
                open_val = safe_float(row_data["open"])
                close_val = safe_float(row_data["close"])

                if any(x is None for x in [low, high, open_val, close_val]):
                    return None, None, None, None

                # Normalisoi annetulla perusarvolla
                norm_low = (
                    (low / base_normalizer * 100)
                    if base_normalizer is not None and base_normalizer > 0
                    else None
                )
                norm_high = (
                    (high / base_normalizer * 100)
                    if base_normalizer is not None and base_normalizer > 0
                    else None
                )

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

                # Historia (offset < 0) normalisoidaan t0_low:lla, t0 ja tulevat t0_close:lla
                base = t0_low if offset < 0 else t0_close
                if base is None or base <= 0:
                    return None
                return (close_val / base) * 100

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

                base_norm = t0_low if t0_low and t0_low > 0 else None
                if not base_norm:
                    return None
                norm_values = [(v / base_norm) * 100 for v in values]
                try:
                    return pstdev(norm_values)
                except Exception:
                    return None

            def calc_volume_ratio(window, offset):
                """
                Laske volyymisuhde:
                - period_avg: keskiarvo volyymeista ikkunassa, joka päättyy offsetiin (esim. offset=-5, window=5 => t-5..t-1)
                - baseline_avg: 100 päivän keskiarvo ennen tuota ikkunaa (start-100 .. start-1)
                Palauttaa (period_avg / baseline_avg) * 100.
                """
                try:
                    end_idx = idx + offset
                    start_idx = end_idx - window + 1
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

                    baseline_end = start_idx - 1
                    baseline_start = baseline_end - 99
                    if baseline_start < 0 or baseline_end >= len(stock_df):
                        return None

                    baseline_subset = stock_df.iloc[baseline_start : baseline_end + 1]
                    baseline_vols = [
                        safe_float(row["volume"]) for _, row in baseline_subset.iterrows()
                    ]
                    baseline_vols = [v for v in baseline_vols if v is not None and v > 0]
                    if not baseline_vols:
                        return None
                    baseline_avg = mean(baseline_vols)
                    if baseline_avg <= 0:
                        return None
                    return (period_avg / baseline_avg) * 100
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

                base_norm = t0_low if t0_low and t0_low > 0 else None
                if not base_norm:
                    return None
                return (ma_val / base_norm) * 100

            def calc_price_slope(normalized_value, horizon):
                """Laske hintaslope normalisoidusta arvosta"""
                if normalized_value is None or horizon <= 0:
                    return None
                try:
                    return (100.0 - float(normalized_value)) / float(horizon)
                except Exception:
                    return None

            def calc_index_volatility(index_ticker: str) -> Optional[float]:
                """Laske indeksin 10 päivän volatiliteetti (t-10..t-1)"""
                values = []
                for offset in range(-10, 0):
                    val = get_index_normalized(index_ticker, offset)
                    if val is not None:
                        values.append(val)
                if len(values) < 2:
                    return None
                try:
                    return pstdev(values)
                except Exception:
                    return None

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

            def calc_ma_series(end_idx, period):
                """Laske raakadatasta liukuva keskiarvo ilman normalisointia"""
                start_idx = end_idx - period + 1
                if start_idx < 0 or end_idx >= len(stock_df):
                    return None
                subset = stock_df.iloc[start_idx : end_idx + 1]
                closes = [safe_float(row["close"]) for _, row in subset.iterrows()]
                closes = [c for c in closes if c is not None]
                if len(closes) != period:
                    return None
                return mean(closes)

            def calc_slope(end_idx, period, lookback=5):
                """Laske MA-slope t-1 päättyvälle jaksolle normalisoituna"""
                if end_idx - lookback < 0:
                    return None
                ma_today = calc_ma_series(end_idx, period)
                ma_prev = calc_ma_series(end_idx - lookback, period)
                if ma_today is None or ma_prev is None:
                    return None
                base = t0_low if t0_low and t0_low > 0 else None
                if not base:
                    return None
                return ((ma_today - ma_prev) / lookback) / base * 100.0

            def calc_regime(short_ma, long_ma):
                if short_ma is None or long_ma is None:
                    return None
                return int(short_ma > long_ma)

            def calc_atr(end_idx, period=14):
                if end_idx - period < 0:
                    return None
                trs = []
                for i in range(end_idx - period + 1, end_idx + 1):
                    if i <= 0:
                        continue
                    curr = stock_df.iloc[i]
                    prev = stock_df.iloc[i - 1]
                    curr_high = safe_float(curr["high"])
                    curr_low = safe_float(curr["low"])
                    prev_close = safe_float(prev["close"])
                    if curr_high is None or curr_low is None or prev_close is None:
                        continue
                    tr = max(
                        curr_high - curr_low,
                        abs(curr_high - prev_close),
                        abs(curr_low - prev_close),
                    )
                    trs.append(tr)
                if len(trs) < period * 0.7:
                    return None
                return mean(trs)

            def calc_ema(values: List[float], span: int) -> List[float]:
                alpha = 2 / (span + 1)
                ema_values: List[float] = []
                ema_val = None
                for value in values:
                    if value is None:
                        return []
                    ema_val = (
                        value
                        if ema_val is None
                        else alpha * value + (1 - alpha) * ema_val
                    )
                    ema_values.append(ema_val)
                return ema_values

            def calc_macd(end_idx):
                if end_idx < 26:
                    return None, None, None
                closes = [
                    safe_float(stock_df.iloc[i]["close"]) for i in range(end_idx + 1)
                ]
                if any(c is None for c in closes):
                    return None, None, None
                ema12 = calc_ema(closes, 12)
                ema26 = calc_ema(closes, 26)
                if len(ema12) != len(closes) or len(ema26) != len(closes):
                    return None, None, None
                macd_line = [a - b for a, b in zip(ema12, ema26)]
                signal = calc_ema(macd_line, 9)
                if not macd_line or not signal:
                    return None, None, None
                line = macd_line[-1]
                sig = signal[-1]
                hist = line - sig
                return line, sig, hist

            def calc_pivot_low_strength(window):
                start_idx = idx - window
                if start_idx < 0:
                    return None
                subset = stock_df.iloc[start_idx:idx]
                lows = [safe_float(row["low"]) for _, row in subset.iterrows()]
                lows = [val for val in lows if val]
                if len(lows) < window * 0.7:
                    return None
                prev_min = min(lows)
                if not prev_min or prev_min <= 0 or not t0_low or t0_low <= 0:
                    return None
                return (prev_min - t0_low) / prev_min * 100.0

            def calc_pivot_high_strength(window):
                start_idx = idx - window
                if start_idx < 0:
                    return None
                subset = stock_df.iloc[start_idx:idx]
                highs = [safe_float(row["high"]) for _, row in subset.iterrows()]
                highs = [val for val in highs if val]
                if len(highs) < window * 0.7:
                    return None
                prev_max = max(highs)
                if not prev_max or prev_max <= 0 or not t0_high or t0_high <= 0:
                    return None
                return (t0_high - prev_max) / prev_max * 100.0

            # === LASKE KAIKKI SARAKKEET ===

            # Kynttilä detaljit (5-16)
            r_m1 = stock_df.iloc[idx - 1] if idx > 0 else None
            r1 = stock_df.iloc[idx + 1] if idx + 1 < len(stock_df) else None
            t0_open = safe_float(r0["open"])
            t0_high = safe_float(r0["high"])
            prev_close = safe_float(r_m1["close"]) if r_m1 is not None else None

            base_low = t0_low if t0_low and t0_low > 0 else None
            base_close = t0_close if t0_close and t0_close > 0 else None

            t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour = calc_candle_details(
                r_m1, base_low
            )
            t0_alin, t0_ylin, t0_bodi, t0_bodi_colour = calc_candle_details(
                r0, base_close
            )
            t1_alin, t1_ylin, t1_bodi, t1_bodi_colour = calc_candle_details(
                r1, base_close
            )
            t0_alin_minus_close = t0_alin - 100.0 if t0_alin is not None else None

            # Historialliset hinnat (17-21)
            t_2 = get_normalized_close(-2)
            t_5 = get_normalized_close(-5)
            t_10 = get_normalized_close(-10)
            t_15 = get_normalized_close(-15)
            t_20 = get_normalized_close(-20)
            price_slope_5 = calc_price_slope(t_5, 5)
            price_slope_10 = calc_price_slope(t_10, 10)
            price_acceleration_5_10 = (
                price_slope_5 - price_slope_10
                if price_slope_5 is not None and price_slope_10 is not None
                else None
            )

            # Volatiliteetti (22-26)
            t_2_hajonta = calc_volatility(2)
            t_5_hajonta = calc_volatility(5)
            t_10_hajonta = calc_volatility(10)
            t_15_hajonta = calc_volatility(15)
            t_20_hajonta = calc_volatility(20)
            if (
                t_10_hajonta is not None
                and t_20_hajonta is not None
                and t_20_hajonta > 0
            ):
                volatility_ratio_10_20 = t_10_hajonta / t_20_hajonta
            else:
                volatility_ratio_10_20 = None

            # Tulevat hinnat (27-30)
            t2 = get_normalized_close(2)
            t5 = get_normalized_close(5)
            t10 = get_normalized_close(10)
            t20 = get_normalized_close(20)

            # Volyymit (31-40) - kaikki suhteina 100pv baselineen ennen ikkunaa
            t0_volume = safe_float(r0["volume"])
            t_2_volyymi = calc_volume_ratio(2, -1)   # t-2..t-1 vs t-102..t-3
            t_5_volyymi = calc_volume_ratio(5, -1)   # t-5..t-1 vs t-105..t-6
            t_10_volyymi = calc_volume_ratio(10, -1)  # t-10..t-1 vs t-110..t-11
            t_15_volyymi = calc_volume_ratio(15, -1)
            t_20_volyymi = calc_volume_ratio(20, -1)

            # t0 volyymi suhteessa t-100..t-1 baselineen
            t0_volyymi = calc_volume_ratio(1, 0)

            def calc_volume_impulse_ratio() -> Optional[float]:
                if t0_volume is None or t0_volume <= 0:
                    return None
                start_idx = max(0, idx - 5)
                end_idx = idx - 1
                if start_idx > end_idx:
                    return None
                subset = stock_df.iloc[start_idx : end_idx + 1]
                prev_volumes = [
                    safe_float(row["volume"]) for _, row in subset.iterrows()
                ]
                prev_volumes = [v for v in prev_volumes if v is not None and v > 0]
                if not prev_volumes:
                    return None
                avg_prev5 = mean(prev_volumes)
                if avg_prev5 is None or avg_prev5 <= 0:
                    return None
                return t0_volume / avg_prev5

            volume_impulse = calc_volume_impulse_ratio()
            gap_down_strength = None
            if (
                prev_close is not None
                and prev_close > 0
                and t0_open is not None
                and base_low is not None
            ):
                gap_value = ((t0_open - prev_close) / base_low) * 100.0
                gap_down_strength = abs(gap_value) if gap_value < 0 else 0.0

            if (
                t0_high is not None
                and t0_low is not None
                and t0_open is not None
                and t0_close is not None
                and t0_high > t0_low
            ):
                candle_range_raw = t0_high - t0_low
                body_value = abs(t0_close - t0_open)
                lower_shadow = max(min(t0_open, t0_close) - t0_low, 0.0)
                upper_shadow = max(t0_high - max(t0_open, t0_close), 0.0)
                body_ratio = body_value / candle_range_raw if candle_range_raw else None
                shadow_ratio = (
                    (lower_shadow + upper_shadow) / candle_range_raw
                    if candle_range_raw
                    else None
                )
            else:
                body_ratio = None
                shadow_ratio = None

            depth_component = abs(t_10 - 100.0) / 10.0 if t_10 is not None else None
            volatility_component = (
                (t_10_hajonta / 2.0) if t_10_hajonta is not None else None
            )
            volume_component = (
                (volume_impulse - 1.0) if volume_impulse is not None else None
            )
            if None not in (depth_component, volatility_component, volume_component):
                reversal_context_score = (
                    depth_component + volatility_component + volume_component
                )
            else:
                reversal_context_score = None

            # Tulevien päivien volyymit (yksi päivä) suhteessa 100pv baselineen ennen kyseistä päivää
            t2_volyymi = calc_volume_ratio(1, 2) if idx + 2 < len(stock_df) else None
            t5_volyymi = calc_volume_ratio(1, 5) if idx + 5 < len(stock_df) else None
            t10_volyymi = calc_volume_ratio(1, 10) if idx + 10 < len(stock_df) else None
            t20_volyymi = calc_volume_ratio(1, 20) if idx + 20 < len(stock_df) else None

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

            t0_20p_liukuva = calc_ma_normalized(0, 20)
            t0_50p_liukuva = calc_ma_normalized(0, 50)
            t0_200p_liukuva = calc_ma_normalized(0, 200) if idx >= 199 else None

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
            SPX_volatility_10 = calc_index_volatility("^GSPC")
            NDX_volatility_10 = calc_index_volatility("^NDX")
            VIX_10 = get_index_normalized("^VIX", -10)
            VIX_norm_10 = (VIX_10 - 100.0) / 100.0 if VIX_10 is not None else None

            ma5 = calc_ma_series(idx - 1, 5)
            ma20 = calc_ma_series(idx - 1, 20)
            ma50 = calc_ma_series(idx - 1, 50)
            ma200 = calc_ma_series(idx - 1, 200)

            t0_50p_slope = calc_slope(idx - 1, 50, lookback=5)
            t0_200p_slope = calc_slope(idx - 1, 200, lookback=5)

            trend_regime_5_20 = calc_regime(ma5, ma20)
            trend_regime_20_50 = calc_regime(ma20, ma50)
            trend_regime_50_200 = calc_regime(ma50, ma200)

            ATR_14 = calc_atr(idx - 1, 14)
            ATR_ratio_14 = (
                (ATR_14 / t0_low) * 100.0 if ATR_14 is not None and t0_low else None
            )

            MACD_line, MACD_signal, MACD_hist = calc_macd(idx - 1)

            pivot_low_strength_3 = calc_pivot_low_strength(3)
            pivot_low_strength_5 = calc_pivot_low_strength(5)
            pivot_high_strength_3 = calc_pivot_high_strength(3)
            pivot_high_strength_5 = calc_pivot_high_strength(5)

            blackout_flags = self._compute_blackout_flags(ticker, date)
            sector_features = self._get_sector_features(ticker)

            # Normalisoitu close (81)
            t0_close_norm = 100.0 if t0_close and t0_close > 0 else None

            # Divergenssit (82-83)
            check_points = []
            for offset in [0, -1, -2, -3, -4, -5]:
                check_idx = idx + offset
                if 0 <= check_idx < len(stock_df):
                    check_date = str(stock_df.iloc[check_idx]["pvm"])
                    check_points.append((offset, check_date))

            check_dates = [date for _, date in check_points]
            divergence_records = self.db_manager.get_divergence_records(
                ticker=ticker, dates=check_dates
            )
            BullDiv_strength = 0.0
            BullDiv_recent_strength = 0.0
            BullDiv_recent_offset = -1
            bearish_divergence = 0.0
            rsi_values_by_offset: dict[int, float] = {}

            for relative_offset, check_date in check_points:
                record = divergence_records.get(check_date)
                if not record:
                    continue

                abs_offset = abs(relative_offset)
                bullish_strength = record.get("bullish_strength") or 0.0
                bearish_strength = record.get("bearish_strength") or 0.0

                if abs_offset == 0 and bullish_strength > 0:
                    BullDiv_strength = bullish_strength

                if bullish_strength > BullDiv_recent_strength:
                    BullDiv_recent_strength = bullish_strength

                if bullish_strength > 0 and BullDiv_recent_offset == -1:
                    BullDiv_recent_offset = abs_offset

                if bearish_strength > bearish_divergence:
                    bearish_divergence = bearish_strength

                rsi_val = record.get("rsi")
                if rsi_val is not None:
                    try:
                        rsi_values_by_offset[abs_offset] = float(rsi_val)
                    except (TypeError, ValueError):
                        continue

            divergence_rsi_t0 = rsi_values_by_offset.get(0)
            RSI14_t0 = (
                divergence_rsi_t0
                if divergence_rsi_t0 is not None
                else finding_rsi14_t0
            )

            rsi_t0_value = (
                RSI14_t0 if RSI14_t0 is not None else rsi_values_by_offset.get(0)
            )
            rsi_t5_value = rsi_values_by_offset.get(5)
            if rsi_t0_value is not None and rsi_t5_value is not None:
                RSI_slope_5 = (rsi_t0_value - rsi_t5_value) / 5.0
            else:
                RSI_slope_5 = None

            Has_BullDiv_recent = 1 if BullDiv_recent_strength > 0 else 0
            if not Has_BullDiv_recent:
                BullDiv_recent_offset = -1

            if BullDiv_recent_strength > 0:
                bullish_divergence = BullDiv_recent_strength
            else:
                bullish_divergence = 0.0

            # Pattern numero (3)
            candle_pattern = self.PATTERN_MAPPING.get(pattern, 0)
            is_candle_day = int(candle_pattern in {1, 2, 3, 4, 5, 6, 71, 72, 73, 74, 75, 76})

            bull_div_offset_value = (
                BullDiv_recent_offset if BullDiv_recent_offset != -1 else 99
            )
            bull_div_general = {
                "bullDiv_offset": bull_div_offset_value,
                "bullDiv_last_1d": 1 if bull_div_offset_value == 0 else 0,
                "bullDiv_last_2d": 1 if bull_div_offset_value in (0, 1) else 0,
                "bullDiv_last_3d": 1 if bull_div_offset_value in (0, 1, 2) else 0,
                "bullDiv_last_3d_any": 1 if bull_div_offset_value in (0, 1, 2) else 0,
            }
            # Viikonpäivä (84)
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday = date_obj.isoweekday()  # 1=Ma, 7=Su
            date_only = date_obj.date()
            is_crisis = 1 if CRISIS_START <= date_only <= CRISIS_END else 0

            # Muodosta tulos dictionary (KAIKKI sarakkeet)
            result = {
                "ticker": ticker,
                "date": date,
                "market": market,
                "candle_pattern": candle_pattern,
                "is_candle_day": is_candle_day,
                "signal_strength": signal_strength,
                "t_1_alin": t_1_alin,
                "t_1_ylin": t_1_ylin,
                "t_1_bodi": t_1_bodi,
                "t_1_bodi_colour": t_1_bodi_colour,
                "t0_alin": t0_alin,
                "t0_ylin": t0_ylin,
                "t0_bodi": t0_bodi,
                "t0_bodi_colour": t0_bodi_colour,
                "t0_alinMiinusClose": t0_alin_minus_close,
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
                "t0_20p_liukuva": t0_20p_liukuva,
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
                "BullDiv_strength": BullDiv_strength,
                "BullDiv_recent_strength": BullDiv_recent_strength,
                "BullDiv_recent_offset": BullDiv_recent_offset,
                "Has_BullDiv_recent": Has_BullDiv_recent,
                "RSI_slope_5": RSI_slope_5,
                "Price_slope_5": price_slope_5,
                "Price_slope_10": price_slope_10,
                "Price_acceleration_5_10": price_acceleration_5_10,
                "Volatility_ratio_10_20": volatility_ratio_10_20,
                "Gap_down_strength": gap_down_strength,
                "Body_ratio": body_ratio,
                "Shadow_ratio": shadow_ratio,
                "Volume_impulse": volume_impulse,
                "Reversal_Context_Score": reversal_context_score,
                "SPX_volatility_10": SPX_volatility_10,
                "NDX_volatility_10": NDX_volatility_10,
                "t0_50p_slope": t0_50p_slope,
                "t0_200p_slope": t0_200p_slope,
                "trend_regime_5_20": trend_regime_5_20,
                "trend_regime_20_50": trend_regime_20_50,
                "trend_regime_50_200": trend_regime_50_200,
                "ATR_14": ATR_14,
                "ATR_ratio_14": ATR_ratio_14,
                "MACD_line": MACD_line,
                "MACD_signal": MACD_signal,
                "MACD_hist": MACD_hist,
                "pivot_low_strength_3": pivot_low_strength_3,
                "pivot_low_strength_5": pivot_low_strength_5,
                "pivot_high_strength_3": pivot_high_strength_3,
                "pivot_high_strength_5": pivot_high_strength_5,
                "VIX_10": VIX_10,
                "VIX_norm_10": VIX_norm_10,
                "is_crisis": is_crisis,
                "weekday": weekday,
            }
            result.update(bull_div_general)
            result.update(blackout_flags)
            result.update(sector_features)
            return result

        except Exception as e:
            self.logger.error(f"Process finding failed: {e}", exc_info=True)
            return None

    def _load_blackout_data(self) -> None:
        """Lataa blackout-datan ja indeksoi ticker-tasolla."""
        try:
            df = load_blackout_dates(self.db_manager.db_path)
        except Exception as exc:
            self.logger.warning(
                f"Failed to load blackout dates ({exc}). Proceeding without blackout data."
            )
            self._blackout_by_ticker = {}
            return

        if df.empty:
            self._blackout_by_ticker = {}
            return

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        grouped = {}
        for ticker, group in df.groupby("ticker"):
            grouped[str(ticker)] = group.copy()
        self._blackout_by_ticker = grouped

    def _compute_blackout_flags(self, ticker: str, date: str) -> dict:
        flags = {
            "is_earnings_t0": 0,
            "is_dividend_t0": 0,
            "is_earnings_window": 0,
            "is_dividend_window": 0,
            "is_blackout_t0": 0,
            "is_blackout_window": 0,
            "exclude_from_regression": 0,
            "has_blackout_data": 0,
        }
        events = self._blackout_by_ticker.get(ticker)
        if events is None or events.empty:
            return flags

        date_ts = pd.to_datetime(date, errors="coerce")
        if pd.isna(date_ts):
            return flags

        deltas = (events["date"] - date_ts).dt.days
        earnings_mask = events["event"].str.lower() == "earnings"
        dividend_mask = events["event"].str.lower() == "dividend"

        flags["has_blackout_data"] = 1
        flags["is_earnings_t0"] = int(((deltas == 0) & earnings_mask).any())
        flags["is_dividend_t0"] = int(((deltas == 0) & dividend_mask).any())
        flags["is_earnings_window"] = int(
            (((deltas >= 0) & (deltas <= 2)) & earnings_mask).any()
        )
        flags["is_dividend_window"] = int(
            (((deltas >= 0) & (deltas <= 1)) & dividend_mask).any()
        )
        flags["is_blackout_t0"] = int(
            flags["is_earnings_t0"] == 1 or flags["is_dividend_t0"] == 1
        )
        flags["is_blackout_window"] = int(
            flags["is_earnings_window"] == 1 or flags["is_dividend_window"] == 1
        )
        flags["exclude_from_regression"] = flags["is_blackout_window"]
        return flags

    def _get_sector_features(self, ticker: str) -> dict:
        if not self._sector_warning_logged:
            self.logger.warning(
                "Sector data not available; sector features will be null."
            )
            self._sector_warning_logged = True
        return {
            "sector": None,
            "sector_momentum_5": None,
            "sector_momentum_20": None,
            "sector_volatility_20": None,
        }

    def _schema_parity_check(self, sample_result: dict) -> None:
        """
        Varmista että results_data taulussa on kaikki generoidut sarakkeet.
        """
        try:
            columns = self.db_manager.get_table_columns("results_data")
        except Exception as exc:
            self.logger.warning(
                "Unable to fetch results_data columns for parity check (%s)", exc
            )
            return

        allowed_extra = {"id", "created_at"}
        keys = set(sample_result.keys())
        missing = keys - columns
        extra = (columns - keys) - allowed_extra

        if missing:
            raise ValueError(
                f"results_data missing expected columns: {sorted(missing)}"
            )
        if extra:
            self.logger.warning(
                "results_data contains extra columns not generated anymore: %s",
                sorted(extra),
            )


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
