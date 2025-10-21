import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging


class ExcelResultsCache:
    """Optimoitu Excel-tulosten generointi staging-tietokannan avulla"""

    def __init__(
        self,
        analysis_db_path: str = "analysis/analysis.db",
        osake_db_path: str = "data/osakedata.db",
        results_db_path: str = "data/results.db",
    ):

        self.analysis_db = analysis_db_path
        self.osake_db = osake_db_path
        self.results_db = results_db_path

        # Luo results.db ja tarvittavat taulut
        self._init_results_database()

    def _init_results_database(self):
        """Alusta results.db tietokanta"""
        with sqlite3.connect(self.results_db) as conn:
            conn.executescript(
                """
                -- Staging-taulu Excel-tuloksia varten
                CREATE TABLE IF NOT EXISTS excel_staging (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    candle TEXT NOT NULL,
                    
                    -- Kynttilädetaljit
                    t_1_alin REAL,
                    t_1_ylin REAL,
                    t_1_bodi REAL,
                    t_1_bodi_colour TEXT,
                    t0_alin REAL,
                    t0_ylin REAL,
                    t0_bodi REAL,
                    t0_bodi_colour TEXT,
                    t1_alin REAL,
                    t1_ylin REAL,
                    t1_bodi REAL,
                    t1_bodi_colour TEXT,
                    
                    -- Historialliset hinnat (normalisoitu t0_alin:lla)
                    t_2 REAL,
                    t_5 REAL,
                    t_10 REAL,
                    t_15 REAL,
                    t_20 REAL,
                    
                    -- Tulevat hinnat (normalisoitu t0_alin:lla)
                    t2 REAL,
                    t5 REAL,
                    t10 REAL,
                    t20 REAL,
                    
                    -- Volatiliteetti (suhteellinen keskihajonta)
                    t_2_hajonta REAL,
                    t_5_hajonta REAL,
                    t_10_hajonta REAL,
                    t_15_hajonta REAL,
                    t_20_hajonta REAL,
                    
                    -- Volyymit (suhde 100pv keskiarvoon)
                    t_2_volyymi REAL,
                    t_5_volyymi REAL,
                    t_10_volyymi REAL,
                    t_15_volyymi REAL,
                    t_20_volyymi REAL,
                    t0_volyymi REAL,
                    t2_volyymi REAL,
                    t5_volyymi REAL,
                    t10_volyymi REAL,
                    t20_volyymi REAL,
                    
                    -- Liukuvat keskiarvot (normalisoitu t0_alin:lla)
                    t2_5p_liukuva REAL,
                    t2_10p_liukuva REAL,
                    t2_20p_liukuva REAL,
                    t5_5p_liukuva REAL,
                    t5_10p_liukuva REAL,
                    t5_20p_liukuva REAL,
                    t10_5p_liukuva REAL,
                    t10_10p_liukuva REAL,
                    t10_20p_liukuva REAL,
                    t15_5p_liukuva REAL,
                    t15_10p_liukuva REAL,
                    t15_20p_liukuva REAL,
                    t20_5p_liukuva REAL,
                    t20_10p_liukuva REAL,
                    t20_20p_liukuva REAL,
                    t50_50p_liukuva REAL,
                    t200_200p_liukuva REAL,
                    
                    -- S&P 500 indeksi (normalisoitu ^GSPC t0_alin:lla)
                    SPX_0 REAL,
                    SPX_2 REAL,
                    SPX_5 REAL,
                    SPX_10 REAL,
                    SPX_15 REAL,
                    SPX_20 REAL,
                    SPX2 REAL,
                    SPX5 REAL,
                    SPX10 REAL,
                    SPX15 REAL,
                    SPX20 REAL,
                    
                    -- Nasdaq 100 indeksi (normalisoitu ^NDX t0_alin:lla)
                    NDX_0 REAL,
                    NDX_2 REAL,
                    NDX_5 REAL,
                    NDX_10 REAL,
                    NDX_15 REAL,
                    NDX_20 REAL,
                    NDX2 REAL,
                    NDX5 REAL,
                    NDX10 REAL,
                    NDX15 REAL,
                    NDX20 REAL,
                    
                    -- Metadata
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(ticker, date, candle)
                );
                
                -- Indeksit nopeaa hakua varten
                CREATE INDEX IF NOT EXISTS idx_excel_staging_ticker ON excel_staging(ticker);
                CREATE INDEX IF NOT EXISTS idx_excel_staging_date ON excel_staging(date);
                CREATE INDEX IF NOT EXISTS idx_excel_staging_ticker_date ON excel_staging(ticker, date);
                
                -- Cache-metatieto
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

    def is_cache_fresh(self) -> bool:
        """Tarkista onko cache tuoreempi kuin lähdedata"""
        try:
            with sqlite3.connect(self.results_db) as conn:
                cache_ts = conn.execute(
                    """
                    SELECT value FROM cache_metadata 
                    WHERE key = 'last_full_rebuild'
                """
                ).fetchone()

            if not cache_ts:
                return False

            # Tarkista analysis.db:n viimeinen muutos
            with sqlite3.connect(self.analysis_db) as conn:
                source_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM analysis_findings
                """
                ).fetchone()[0]

            with sqlite3.connect(self.results_db) as conn:
                cached_count = conn.execute(
                    """
                    SELECT value FROM cache_metadata 
                    WHERE key = 'source_count'
                """
                ).fetchone()

            if not cached_count or int(cached_count[0]) != source_count:
                return False

            return True

        except Exception as e:
            logging.warning(f"Cache freshness check failed: {e}")
            return False

    def rebuild_staging_optimized(
        self, progress_callback=None, limit_rows: int = None, ticker_filter: str = None
    ):
        """Rakenna staging-taulu optimoidusti SQL:llä"""

        def update_progress(step: str, current: int, total: int):
            if progress_callback:
                progress_callback(step, current, total)

        update_progress("Alustetaan staging-taulua...", 0, 100)

        # Tyhjennä vanha staging
        with sqlite3.connect(self.results_db) as conn:
            conn.execute("DELETE FROM excel_staging")
            conn.execute("DELETE FROM cache_metadata")

        update_progress("Haetaan löydökset...", 10, 100)

        # Hae löydökset analysis.db:stä (ticker-filtterillä jos annettu)
        with sqlite3.connect(self.analysis_db) as analysis_conn:
            if ticker_filter:
                print(f"🎯 Suodatetaan ticker: {ticker_filter}")
                findings = analysis_conn.execute(
                    """
                    SELECT ticker, date, candle 
                    FROM analysis_findings 
                    WHERE candle IS NOT NULL AND candle != '' AND ticker = ?
                    ORDER BY ticker, date
                """,
                    (ticker_filter,),
                ).fetchall()
            else:
                print("🌐 Haetaan kaikki tickerit")
                findings = analysis_conn.execute(
                    """
                    SELECT ticker, date, candle 
                    FROM analysis_findings 
                    WHERE candle IS NOT NULL AND candle != ''
                    ORDER BY ticker, date
                """
                ).fetchall()

        if not findings:
            logging.warning("Ei löydöksiä analysis.db:ssä")
            return

        update_progress("Ryhmitellään osakkeittain...", 20, 100)

        # Ryhmittele osakkeittain
        by_ticker = {}
        for ticker, date, candle in findings:
            if ticker not in by_ticker:
                by_ticker[ticker] = []
            by_ticker[ticker].append((date, candle))

        total_tickers = len(by_ticker)
        processed_tickers = 0

        # Rajoita prosessoitavien osakkeiden määrää limit_rows:n perusteella
        if limit_rows:
            ticker_limit = min(limit_rows, total_tickers)
            by_ticker = dict(list(by_ticker.items())[:ticker_limit])
            total_tickers = len(by_ticker)  # Prosessoi osake kerrallaan
        with sqlite3.connect(self.osake_db) as osake_conn:
            with sqlite3.connect(self.results_db) as results_conn:

                for ticker, ticker_findings in by_ticker.items():
                    self._process_ticker_optimized(
                        ticker, ticker_findings, osake_conn, results_conn
                    )

                    processed_tickers += 1
                    progress_pct = 20 + int((processed_tickers / total_tickers) * 70)
                    update_progress(f"Prosessoidaan {ticker}...", progress_pct, 100)

        # Päivitä cache-metadata
        with sqlite3.connect(self.results_db) as conn:
            source_count = len(findings)
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_metadata (key, value) VALUES 
                ('last_full_rebuild', datetime('now')),
                ('source_count', ?)
            """,
                (source_count,),
            )

        update_progress("Valmis!", 100, 100)

    def _process_ticker_optimized(
        self, ticker: str, findings: List[Tuple[str, str]], osake_conn, results_conn
    ):
        """Prosessoi yhden osakkeen kaikki löydökset optimoidusti"""

        # Hae kaikki osakkeen hinnat kerralla
        try:
            df = pd.read_sql(
                """
                SELECT pvm as Date, open as Open, high as High, low as Low, close as Close, volume as Volume 
                FROM osakedata 
                WHERE osake = ? 
                ORDER BY pvm
            """,
                osake_conn,
                params=[ticker],
            )

            if df.empty:
                logging.warning(f"Ei hintadataa osakkeelle {ticker}")
                return

        except Exception as e:
            logging.warning(f"Virhe haettaessa dataa osakkeelle {ticker}: {e}")
            return

        # Konvertoi päivämäärät ja aseta indeksiksi
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)

        # Hae indeksitiedot kerralla
        spx_df = self._get_index_data(
            osake_conn, "^GSPC", df.index.min(), df.index.max()
        )
        ndx_df = self._get_index_data(
            osake_conn, "^NDX", df.index.min(), df.index.max()
        )

        # Laske liukuvat keskiarvot kerralla
        df["ma5"] = df["Close"].rolling(window=5).mean()
        df["ma10"] = df["Close"].rolling(window=10).mean()
        df["ma20"] = df["Close"].rolling(window=20).mean()
        df["ma50"] = df["Close"].rolling(window=50).mean()
        df["ma200"] = df["Close"].rolling(window=200).mean()

        # Laske volyymien 100pv keskiarvo
        df["volume_100d_avg"] = df["Volume"].rolling(window=100).mean()

        # Prosessoi löydökset batcheissa
        batch_size = 100
        for i in range(0, len(findings), batch_size):
            batch = findings[i : i + batch_size]
            self._process_findings_batch(
                ticker, batch, df, spx_df, ndx_df, results_conn
            )

    def _get_index_data(
        self, osake_conn, symbol: str, start_date, end_date
    ) -> pd.DataFrame:
        """Hae indeksidata annetulta aikaväliltä"""
        try:
            df = pd.read_sql(
                """
                SELECT pvm as Date, close as Close 
                FROM osakedata 
                WHERE osake = ? AND pvm BETWEEN ? AND ?
                ORDER BY pvm
            """,
                osake_conn,
                params=[
                    symbol,
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                ],
            )

            if not df.empty:
                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", inplace=True)

            return df

        except Exception as e:
            logging.warning(f"Virhe haettaessa indeksidataa {symbol}: {e}")
            return pd.DataFrame()

    def _process_findings_batch(
        self,
        ticker: str,
        findings_batch: List[Tuple[str, str]],
        df: pd.DataFrame,
        spx_df: pd.DataFrame,
        ndx_df: pd.DataFrame,
        results_conn,
    ):
        """Prosessoi löydösten batch optimoidusti"""

        batch_data = []

        for date_str, candle in findings_batch:
            try:
                date = pd.to_datetime(date_str)

                if date not in df.index:
                    continue

                # Laske kaikki arvot tälle löydökselle
                row_data = self._calculate_all_values(
                    ticker, date, candle, df, spx_df, ndx_df
                )

                if row_data:
                    batch_data.append(row_data)

            except Exception as e:
                logging.warning(f"Virhe prosessoitaessa {ticker} {date_str}: {e}")
                continue

        # Tallenna batch kerralla
        if batch_data:
            results_conn.executemany(
                """
                INSERT OR REPLACE INTO excel_staging 
                (ticker, date, candle, t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour,
                 t0_alin, t0_ylin, t0_bodi, t0_bodi_colour, t1_alin, t1_ylin, t1_bodi, t1_bodi_colour,
                 t_2, t_5, t_10, t_15, t_20, t2, t5, t10, t20,
                 t_2_hajonta, t_5_hajonta, t_10_hajonta, t_15_hajonta, t_20_hajonta,
                 t_2_volyymi, t_5_volyymi, t_10_volyymi, t_15_volyymi, t_20_volyymi,
                 t0_volyymi, t2_volyymi, t5_volyymi, t10_volyymi, t20_volyymi,
                 t2_5p_liukuva, t2_10p_liukuva, t2_20p_liukuva, t5_5p_liukuva, t5_10p_liukuva, t5_20p_liukuva,
                 t10_5p_liukuva, t10_10p_liukuva, t10_20p_liukuva, t15_5p_liukuva, t15_10p_liukuva, t15_20p_liukuva,
                 t20_5p_liukuva, t20_10p_liukuva, t20_20p_liukuva, t50_50p_liukuva, t200_200p_liukuva,
                 SPX_0, SPX_2, SPX_5, SPX_10, SPX_15, SPX_20, SPX2, SPX5, SPX10, SPX15, SPX20,
                 NDX_0, NDX_2, NDX_5, NDX_10, NDX_15, NDX_20, NDX2, NDX5, NDX10, NDX15, NDX20)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                batch_data,
            )

    def _calculate_all_values(
        self,
        ticker: str,
        date: pd.Timestamp,
        candle: str,
        df: pd.DataFrame,
        spx_df: pd.DataFrame,
        ndx_df: pd.DataFrame,
    ) -> Optional[Tuple]:
        """Laske kaikki Excel-sarakkeiden arvot yhdellä kertaa"""

        try:
            # Etsi rivi DataFramesta
            if date not in df.index:
                return None

            # Hakemuksen helpoittamiseksi indeksiarvo
            date_idx = df.index.get_loc(date)
            total_rows = len(df)

            # Perustiedot
            row = df.iloc[date_idx]
            t0_low = row["Low"]
            t0_high = row["High"]
            t0_open = row["Open"]
            t0_close = row["Close"]
            t0_volume = row["Volume"]

            if t0_low is None or t0_low <= 0:
                return None

            # Kynttilädetaljit t-1, t0, t1
            def get_candle_data(offset):
                idx = date_idx + offset
                if idx < 0 or idx >= total_rows:
                    return None, None, None, None
                r = df.iloc[idx]
                alin = r["Low"]
                ylin = r["High"]
                bodi = (
                    abs(r["Close"] - r["Open"]) / alin * 100
                    if alin and alin > 0
                    else None
                )
                colour = "green" if r["Close"] > r["Open"] else "red"
                return alin, ylin, bodi, colour

            t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour = get_candle_data(-1)
            t0_alin, t0_ylin, t0_bodi, t0_bodi_colour = (
                t0_low,
                t0_high,
                abs(t0_close - t0_open) / t0_low * 100,
                "green" if t0_close > t0_open else "red",
            )
            t1_alin, t1_ylin, t1_bodi, t1_bodi_colour = get_candle_data(1)

            # Normalisoidut hinnat
            def get_normalized_close(offset):
                idx = date_idx + offset
                if idx < 0 or idx >= total_rows:
                    return None
                close_val = df.iloc[idx]["Close"]
                return (close_val / t0_low * 100) if close_val is not None else None

            t_2 = get_normalized_close(-2)
            t_5 = get_normalized_close(-5)
            t_10 = get_normalized_close(-10)
            t_15 = get_normalized_close(-15)
            t_20 = get_normalized_close(-20)

            t2 = get_normalized_close(2)
            t5 = get_normalized_close(5)
            t10 = get_normalized_close(10)
            t20 = get_normalized_close(20)

            # Volatiliteetti (suhteellinen keskihajonta)
            def calc_volatility(days_back):
                start_idx = max(0, date_idx - days_back)
                end_idx = date_idx + 1
                subset = df.iloc[start_idx:end_idx]["Close"].dropna()
                if len(subset) < 2:
                    return None
                mean_val = subset.mean()
                if mean_val == 0:
                    return None
                std_val = subset.std()
                return (std_val / mean_val) * 100

            t_2_hajonta = calc_volatility(2)
            t_5_hajonta = calc_volatility(5)
            t_10_hajonta = calc_volatility(10)
            t_15_hajonta = calc_volatility(15)
            t_20_hajonta = calc_volatility(20)

            # Volyymisuhde
            def calc_volume_ratio(offset_range=None, single_offset=None):
                if single_offset is not None:
                    idx = date_idx + single_offset
                    if idx < 0 or idx >= total_rows:
                        return None
                    vol = df.iloc[idx]["Volume"]
                    avg_vol = df.iloc[idx]["volume_100d_avg"]
                    return (vol / avg_vol) if avg_vol and avg_vol > 0 else None
                else:
                    start_offset, end_offset = offset_range
                    start_idx = max(0, date_idx + start_offset)
                    end_idx = min(total_rows, date_idx + end_offset + 1)
                    subset = df.iloc[start_idx:end_idx]
                    if subset.empty:
                        return None
                    avg_vol = subset["Volume"].mean()
                    avg_100d = subset["volume_100d_avg"].mean()
                    return (avg_vol / avg_100d) if avg_100d and avg_100d > 0 else None

            t_2_volyymi = calc_volume_ratio((-4, -2))
            t_5_volyymi = calc_volume_ratio((-7, -3))
            t_10_volyymi = calc_volume_ratio((-12, -8))
            t_15_volyymi = calc_volume_ratio((-17, -13))
            t_20_volyymi = calc_volume_ratio((-22, -18))

            t0_volyymi = calc_volume_ratio(single_offset=0)
            t2_volyymi = calc_volume_ratio(single_offset=2)
            t5_volyymi = calc_volume_ratio(single_offset=5)
            t10_volyymi = calc_volume_ratio(single_offset=10)
            t20_volyymi = calc_volume_ratio(single_offset=20)

            # Liukuvat keskiarvot (normalisoitu t0_low:lla)
            def get_normalized_ma(offset, ma_column):
                idx = date_idx + offset
                if idx < 0 or idx >= total_rows:
                    return None
                ma_val = df.iloc[idx][ma_column]
                return (ma_val / t0_low * 100) if ma_val is not None else None

            t2_5p_liukuva = get_normalized_ma(2, "ma5")
            t2_10p_liukuva = get_normalized_ma(2, "ma10")
            t2_20p_liukuva = get_normalized_ma(2, "ma20")
            t5_5p_liukuva = get_normalized_ma(5, "ma5")
            t5_10p_liukuva = get_normalized_ma(5, "ma10")
            t5_20p_liukuva = get_normalized_ma(5, "ma20")
            t10_5p_liukuva = get_normalized_ma(10, "ma5")
            t10_10p_liukuva = get_normalized_ma(10, "ma10")
            t10_20p_liukuva = get_normalized_ma(10, "ma20")
            t15_5p_liukuva = get_normalized_ma(15, "ma5")
            t15_10p_liukuva = get_normalized_ma(15, "ma10")
            t15_20p_liukuva = get_normalized_ma(15, "ma20")
            t20_5p_liukuva = get_normalized_ma(20, "ma5")
            t20_10p_liukuva = get_normalized_ma(20, "ma10")
            t20_20p_liukuva = get_normalized_ma(20, "ma20")
            t50_50p_liukuva = get_normalized_ma(50, "ma50")
            t200_200p_liukuva = get_normalized_ma(200, "ma200")

            # Indeksitiedot (normalisoitu vastaavan indeksin t0_low:lla)
            def get_index_values(index_df, symbol_name):
                if index_df.empty:
                    return [None] * 11

                # Etsi t0 arvo indeksistä
                t0_index_val = None
                if date in index_df.index:
                    t0_index_val = index_df.loc[date, "Close"]

                if t0_index_val is None or t0_index_val <= 0:
                    return [None] * 11

                # Laske suhteelliset arvot
                def get_index_normalized(offset):
                    target_date = date + pd.Timedelta(days=offset)
                    # Etsi lähisin kaupankäyntipäivä
                    available_dates = index_df.index
                    if offset < 0:
                        candidates = available_dates[available_dates <= target_date]
                        if len(candidates) == 0:
                            return None
                        closest_date = candidates.max()
                    else:
                        candidates = available_dates[available_dates >= target_date]
                        if len(candidates) == 0:
                            return None
                        closest_date = candidates.min()

                    if closest_date in index_df.index:
                        val = index_df.loc[closest_date, "Close"]
                        return (val / t0_index_val * 100) if val is not None else None
                    return None

                return [
                    100.0,  # t0 = 100% (self-reference)
                    get_index_normalized(-2),
                    get_index_normalized(-5),
                    get_index_normalized(-10),
                    get_index_normalized(-15),
                    get_index_normalized(-20),
                    get_index_normalized(2),
                    get_index_normalized(5),
                    get_index_normalized(10),
                    get_index_normalized(15),
                    get_index_normalized(20),
                ]

            spx_values = get_index_values(spx_df, "SPX")
            ndx_values = get_index_values(ndx_df, "NDX")

            # Palauta tuple kaikista arvoista
            return (
                ticker,
                date.strftime("%Y-%m-%d"),
                candle,
                t_1_alin,
                t_1_ylin,
                t_1_bodi,
                t_1_bodi_colour,
                t0_alin,
                t0_ylin,
                t0_bodi,
                t0_bodi_colour,
                t1_alin,
                t1_ylin,
                t1_bodi,
                t1_bodi_colour,
                t_2,
                t_5,
                t_10,
                t_15,
                t_20,
                t2,
                t5,
                t10,
                t20,
                t_2_hajonta,
                t_5_hajonta,
                t_10_hajonta,
                t_15_hajonta,
                t_20_hajonta,
                t_2_volyymi,
                t_5_volyymi,
                t_10_volyymi,
                t_15_volyymi,
                t_20_volyymi,
                t0_volyymi,
                t2_volyymi,
                t5_volyymi,
                t10_volyymi,
                t20_volyymi,
                t2_5p_liukuva,
                t2_10p_liukuva,
                t2_20p_liukuva,
                t5_5p_liukuva,
                t5_10p_liukuva,
                t5_20p_liukuva,
                t10_5p_liukuva,
                t10_10p_liukuva,
                t10_20p_liukuva,
                t15_5p_liukuva,
                t15_10p_liukuva,
                t15_20p_liukuva,
                t20_5p_liukuva,
                t20_10p_liukuva,
                t20_20p_liukuva,
                t50_50p_liukuva,
                t200_200p_liukuva,
                *spx_values,  # SPX_0, SPX_2, ..., SPX20
                *ndx_values,  # NDX_0, NDX_2, ..., NDX20
            )

        except Exception as e:
            logging.error(f"Virhe laskennassa {ticker} {date}: {e}")
            return None

    def export_to_excel_fast(
        self,
        excel_path: str = "data/results.xlsx",
        limit_rows: int = None,
        ticker_filter: str = None,
    ) -> bool:
        """Nopea Excel-export staging-taulusta"""
        try:
            # Lue kaikki data kerralla staging-taulusta
            with sqlite3.connect(self.results_db) as conn:
                # Rakenna SQL-kysely filttereiden kanssa
                base_query = """
                    SELECT 
                        ticker, date, candle,
                        t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour,
                        t0_alin, t0_ylin, t0_bodi, t0_bodi_colour,
                        t1_alin, t1_ylin, t1_bodi, t1_bodi_colour,
                        t_2, t_5, t_10, t_15, t_20,
                        t2, t5, t10, t20,
                        t_2_hajonta, t_5_hajonta, t_10_hajonta, t_15_hajonta, t_20_hajonta,
                        t_2_volyymi, t_5_volyymi, t_10_volyymi, t_15_volyymi, t_20_volyymi,
                        t0_volyymi, t2_volyymi, t5_volyymi, t10_volyymi, t20_volyymi,
                        t2_5p_liukuva, t2_10p_liukuva, t2_20p_liukuva,
                        t5_5p_liukuva, t5_10p_liukuva, t5_20p_liukuva,
                        t10_5p_liukuva, t10_10p_liukuva, t10_20p_liukuva,
                        t15_5p_liukuva, t15_10p_liukuva, t15_20p_liukuva,
                        t20_5p_liukuva, t20_10p_liukuva, t20_20p_liukuva,
                        t50_50p_liukuva, t200_200p_liukuva,
                        SPX_0, SPX_2, SPX_5, SPX_10, SPX_15, SPX_20,
                        SPX2, SPX5, SPX10, SPX15, SPX20,
                        NDX_0, NDX_2, NDX_5, NDX_10, NDX_15, NDX_20,
                        NDX2, NDX5, NDX10, NDX15, NDX20
                    FROM excel_staging"""

                # Lisää WHERE-lauseke ticker-filtteriä varten
                conditions = []
                params = []

                if ticker_filter:
                    conditions.append("ticker = ?")
                    params.append(ticker_filter)

                if conditions:
                    base_query += " WHERE " + " AND ".join(conditions)

                base_query += " ORDER BY ticker, date"

                if limit_rows:
                    query = base_query + f" LIMIT {limit_rows}"
                else:
                    query = base_query

                if params:
                    df = pd.read_sql(query, conn, params=params)
                else:
                    df = pd.read_sql(query, conn)

            if df.empty:
                logging.warning("Ei dataa staging-taulussa")
                return False

            # Muotoile numerot suomalaiseen muotoon
            numeric_columns = df.select_dtypes(include=[np.number]).columns
            for col in numeric_columns:
                df[col] = df[col].apply(self._format_finnish_number)

            # Tallenna Excel-tiedostoon
            Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
            df.to_excel(excel_path, index=False, engine="openpyxl")

            logging.info(f"Excel-tiedosto tallennettu: {excel_path} ({len(df)} riviä)")
            return True

        except Exception as e:
            logging.error(f"Virhe Excel-exportissa: {e}")
            return False

    def _format_finnish_number(self, value):
        """Muotoile numero suomalaiseen muotoon"""
        if value is None or pd.isna(value):
            return ""
        try:
            if isinstance(value, (int, float)):
                formatted = f"{float(value):.4f}".rstrip("0").rstrip(".")
                return formatted.replace(".", ",")
            return str(value).replace(".", ",")
        except:
            return str(value)

    def get_staging_stats(self) -> dict:
        """Hae staging-taulun tilastot"""
        try:
            with sqlite3.connect(self.results_db) as conn:
                stats = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as total_rows,
                        COUNT(DISTINCT ticker) as unique_tickers,
                        MIN(date) as earliest_date,
                        MAX(date) as latest_date
                    FROM excel_staging
                """
                ).fetchone()

                last_update = conn.execute(
                    """
                    SELECT value FROM cache_metadata 
                    WHERE key = 'last_full_rebuild'
                """
                ).fetchone()

                return {
                    "total_rows": stats[0] if stats else 0,
                    "unique_tickers": stats[1] if stats else 0,
                    "earliest_date": stats[2] if stats else None,
                    "latest_date": stats[3] if stats else None,
                    "last_update": last_update[0] if last_update else None,
                }
        except Exception as e:
            logging.error(f"Virhe tilastojen haussa: {e}")
            return {}
