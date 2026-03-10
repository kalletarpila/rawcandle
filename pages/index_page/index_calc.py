from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

IndexRow = Dict[str, object]
SchemaMap = Dict[str, str]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def introspect_schema(conn: sqlite3.Connection) -> SchemaMap:
    """Palauta sarake-nimien map käytettäväksi kyselyissä."""
    cursor = conn.execute("PRAGMA table_info(osakedata)")
    cols = {row["name"].lower(): row["name"] for row in cursor.fetchall()}
    mapping = {}
    for key in ("osake", "ticker"):
        if key in cols:
            mapping["ticker"] = cols[key]
            break
    for key in ("pvm", "date"):
        if key in cols:
            mapping["date"] = cols[key]
            break
    for key in ("close",):
        if key in cols:
            mapping["close"] = cols[key]
            break
    for key in ("volume",):
        if key in cols:
            mapping["volume"] = cols[key]
            break
    for key in ("market",):
        if key in cols:
            mapping["market"] = cols[key]
            break
    for key in ("sector",):
        if key in cols:
            mapping["sector"] = cols[key]
            break
    return mapping


def ensure_index_table(conn: sqlite3.Connection) -> None:
    desired_unique = {"date", "level", "market", "sector", "industry"}

    def _create_table():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS index_daily (
                date TEXT NOT NULL,
                level TEXT NOT NULL,
                market TEXT NOT NULL,
                sector TEXT,
                industry TEXT,
                index_value REAL NOT NULL,
                daily_return REAL,
                volume_sum REAL,
                n_stocks INTEGER,
                UNIQUE(date, level, market, sector, industry)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_index_daily_level_market_sector_industry_date ON index_daily(level, market, sector, industry, date)"
        )

    # Create if missing
    conn.execute("CREATE TABLE IF NOT EXISTS index_daily (date TEXT)")
    cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(index_daily)").fetchall()
    }
    if "industry" not in cols:
        conn.execute("ALTER TABLE index_daily ADD COLUMN industry TEXT")

    # Check if unique includes industry; if not, rebuild table to avoid conflicts
    def _has_desired_unique() -> bool:
        for idx in conn.execute("PRAGMA index_list(index_daily)").fetchall():
            idx_name = idx[1] if len(idx) > 1 else idx["name"]
            idx_unique = idx[2] if len(idx) > 2 else idx.get("unique")
            if not idx_unique:
                continue
            info = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
            names = {r[2] for r in info}
            if names == desired_unique:
                return True
        return False

    if not _has_desired_unique():
        # rebuild
        conn.execute("ALTER TABLE index_daily RENAME TO index_daily_old")
        _create_table()
        conn.execute(
            """
            INSERT OR IGNORE INTO index_daily (date, level, market, sector, industry, index_value, daily_return, volume_sum, n_stocks)
            SELECT date, level, market, sector, industry, index_value, daily_return, volume_sum, n_stocks
            FROM index_daily_old
            """
        )
        conn.execute("DROP TABLE IF EXISTS index_daily_old")
    else:
        _create_table()


def ensure_osakedata_indexes(conn: sqlite3.Connection, schema: SchemaMap) -> None:
    market_col = schema.get("market")
    ticker_col = schema.get("ticker")
    date_col = schema.get("date")
    sector_col = schema.get("sector")
    if not (market_col and ticker_col and date_col):
        return
    conn.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_osakedata_mkt_ticker_date
        ON osakedata({market_col}, {ticker_col}, {date_col})
        """
    )
    if sector_col:
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_osakedata_mkt_sec_ticker_date
            ON osakedata({market_col}, {sector_col}, {ticker_col}, {date_col})
            """
        )


def ensure_ticker_metadata(conn: sqlite3.Connection, schema: SchemaMap) -> None:
    """Luo ja täytä ticker-metadatataulu (ticker_meta) sektorin/industrystä."""
    ticker_col = schema.get("ticker")
    market_col = schema.get("market")
    date_col = schema.get("date")
    sector_col = schema.get("sector")
    industry_col = schema.get("industry")
    if not (ticker_col and market_col and date_col):
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_meta (
            ticker TEXT PRIMARY KEY,
            market TEXT,
            sector TEXT,
            industry TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticker_meta_market ON ticker_meta(market)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ticker_meta_market_sector ON ticker_meta(market, sector)"
    )

    # Täytä sektoritieto: käytä viimeisintä ei-tyhjää sektoria; fallback viimeisin rivi.
    if not sector_col:
        return

    industry_sel = industry_col if industry_col else "NULL"
    conn.execute(
        f"""
        WITH last_with_sector AS (
            SELECT o.{ticker_col} AS ticker,
                   LOWER(o.{market_col}) AS market,
                   o.{sector_col} AS sector,
                   {industry_sel} AS industry
            FROM osakedata o
            JOIN (
                SELECT {ticker_col} AS ticker, MAX({date_col}) AS pvm
                FROM osakedata
                WHERE {sector_col} IS NOT NULL AND TRIM({sector_col}) <> ''
                GROUP BY {ticker_col}
            ) m ON o.{ticker_col} = m.ticker AND o.{date_col} = m.pvm
        ),
        last_any AS (
            SELECT o.{ticker_col} AS ticker,
                   LOWER(o.{market_col}) AS market,
                   o.{sector_col} AS sector,
                   {industry_sel} AS industry
            FROM osakedata o
            JOIN (
                SELECT {ticker_col} AS ticker, MAX({date_col}) AS pvm
                FROM osakedata
                GROUP BY {ticker_col}
            ) m ON o.{ticker_col} = m.ticker AND o.{date_col} = m.pvm
        ),
        combined AS (
            SELECT * FROM last_with_sector
            UNION ALL
            SELECT * FROM last_any WHERE ticker NOT IN (SELECT ticker FROM last_with_sector)
        )
        INSERT OR REPLACE INTO ticker_meta (ticker, market, sector, industry)
        SELECT
            c.ticker,
            c.market,
            COALESCE((SELECT t.sector FROM ticker_meta t WHERE t.ticker = c.ticker), c.sector),
            COALESCE((SELECT t.industry FROM ticker_meta t WHERE t.ticker = c.ticker), c.industry)
        FROM combined c
        """
    )


def get_available_markets(conn: sqlite3.Connection, schema: SchemaMap) -> List[str]:
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ticker_meta (ticker TEXT PRIMARY KEY, market TEXT, sector TEXT, industry TEXT)"
        )
        cursor = conn.execute(
            "SELECT DISTINCT LOWER(market) AS m FROM ticker_meta WHERE market IS NOT NULL ORDER BY m"
        )
        return [row["m"] for row in cursor.fetchall() if row["m"]]
    except Exception:
        return []


def get_sectors_for_market(
    conn: sqlite3.Connection, schema: SchemaMap, market: str
) -> List[str]:
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ticker_meta (ticker TEXT PRIMARY KEY, market TEXT, sector TEXT, industry TEXT)"
        )
        cursor = conn.execute(
            """
            SELECT DISTINCT sector
            FROM ticker_meta
            WHERE LOWER(market) = LOWER(?)
              AND sector IS NOT NULL
              AND TRIM(sector) <> ''
            ORDER BY sector
            """,
            (market,),
        )
        return [row["sector"] for row in cursor.fetchall()]
    except Exception:
        return []


def get_tickers_for_market_sectors(
    conn: sqlite3.Connection, schema: SchemaMap, market: str, sectors: Sequence[str]
) -> List[str]:
    params: List[object] = [market]
    sector_filter = ""
    if sectors:
        placeholders = ",".join(["?"] * len(sectors))
        sector_filter = f" AND sector IN ({placeholders})"
        params.extend(sectors)
    cursor = conn.execute(
        f"""
        SELECT ticker
        FROM ticker_meta
        WHERE LOWER(market) = LOWER(?)
        {sector_filter}
        ORDER BY ticker
        """,
        params,
    )
    return [row["ticker"] for row in cursor.fetchall() if row["ticker"]]


def _fetch_last_index_info(
    conn: sqlite3.Connection,
    market: str,
    sector: Optional[str],
    industry: Optional[str] = None,
) -> Tuple[Optional[str], Optional[float]]:
    cursor = conn.execute(
        """
        SELECT date, index_value
        FROM index_daily
        WHERE level = ? AND market = ?
          AND (sector IS ? OR sector = ?)
          AND (industry IS ? OR industry = ?)
        ORDER BY date DESC
        LIMIT 1
        """,
        (
            "industry" if industry else ("sector" if sector else "market"),
            market,
            sector,
            sector,
            industry,
            industry,
        ),
    )
    row = cursor.fetchone()
    if not row:
        return None, None
    return row["date"], row["index_value"]


def compute_indices_incremental(
    conn: sqlite3.Connection,
    market: str,
    sectors: Sequence[str],
    *,
    start_date: str = "2024-01-01",
    logger=print,
    include_industries: bool = False,
) -> Dict[str, int]:
    """Laske markkina- ja sektoritasoiset indeksit incrementaalisesti."""
    schema = introspect_schema(conn)
    ticker_col = schema.get("ticker")
    date_col = schema.get("date")
    close_col = schema.get("close")
    volume_col = schema.get("volume")
    market_col = schema.get("market")
    if not (ticker_col and date_col and close_col and volume_col and market_col):
        raise RuntimeError("osakedata-taulusta puuttuu vaadittuja sarakkeita")

    ensure_index_table(conn)
    ensure_ticker_metadata(conn, schema)
    ensure_osakedata_indexes(conn, schema)

    target_sectors = list(sectors or [])
    groups: List[Tuple[str, Optional[str], Optional[str]]] = [
        ("market", None, None)
    ] + [("sector", sec, None) for sec in target_sectors]

    industries_by_sector: Dict[str, List[str]] = {}
    if include_industries:
        params_ind: List[object] = [market]
        sector_filter_ind = ""
        if target_sectors:
            placeholders = ",".join(["?"] * len(target_sectors))
            sector_filter_ind = f" AND sector IN ({placeholders})"
            params_ind.extend(target_sectors)
        rows_ind = conn.execute(
            f"""
            SELECT DISTINCT sector, industry
            FROM ticker_meta
            WHERE LOWER(market) = LOWER(?)
              {sector_filter_ind}
              AND sector IS NOT NULL AND TRIM(sector) <> ''
              AND industry IS NOT NULL AND TRIM(industry) <> ''
            ORDER BY sector, industry
            """,
            params_ind,
        ).fetchall()
        for r in rows_ind:
            sec = r[0]
            ind = r[1]
            industries_by_sector.setdefault(sec, []).append(ind)
        for sec, inds in industries_by_sector.items():
            for ind in inds:
                groups.append(("industry", sec, ind))

    summary = {"updated_rows": 0, "groups": len(groups)}

    for level, sector, industry in groups:
        last_date, last_value = _fetch_last_index_info(conn, market, sector, industry)
        base_start = last_date or start_date

        logger(
            f"[INDEX] {market} {level} {sector or ''} {industry or ''} start from {base_start} (last={last_date or 'none'})"
        )

        params: List[object] = [market]
        sector_filter = ""
        sector_filter_prev = ""
        industry_filter = ""
        industry_filter_prev = ""
        exclude_index = " AND tm.ticker NOT LIKE '^%'"
        if sector:
            sector_filter = " AND tm.sector = ?"
            sector_filter_prev = " AND tm2.sector = ?"
            params.append(sector)
        if industry:
            industry_filter = " AND tm.industry = ?"
            industry_filter_prev = " AND tm2.industry = ?"
            params.append(industry)

        rows: List[sqlite3.Row] = []
        try:
            conn.execute("SELECT LAG(1) OVER (ORDER BY 1)")
            use_lag = True
        except sqlite3.OperationalError:
            use_lag = False

        if use_lag:
            base_params = list(params)  # [market] or [market, sector]
            query_params = (
                base_params + [base_start] + base_params + [base_start] + [base_start]
            )
            rows = conn.execute(
                f"""
                WITH base_rows AS (
                    SELECT
                        o.{ticker_col} AS ticker,
                        o.{date_col} AS pvm,
                        o.{close_col} AS close,
                        o.{volume_col} AS volume
                    FROM osakedata o
                    JOIN ticker_meta tm ON tm.ticker = o.{ticker_col}
                    WHERE LOWER(tm.market) = LOWER(?)
                      {sector_filter}
                      {industry_filter}
                      {exclude_index}
                      AND o.{date_col} >= ?
                ),
                prev_rows AS (
                    SELECT
                        o.{ticker_col} AS ticker,
                        o.{date_col} AS pvm,
                        o.{close_col} AS close,
                        o.{volume_col} AS volume
                    FROM osakedata o
                    JOIN ticker_meta tm ON tm.ticker = o.{ticker_col}
                    JOIN (
                        SELECT {ticker_col} AS t, MAX({date_col}) AS max_pvm
                        FROM osakedata
                        JOIN ticker_meta tm2 ON tm2.ticker = {ticker_col}
                        WHERE LOWER(tm2.market) = LOWER(?)
                          {sector_filter_prev}
                          {industry_filter_prev}
                          AND tm2.ticker NOT LIKE '^%'
                          AND {date_col} < ?
                        GROUP BY {ticker_col}
                    ) p
                      ON o.{ticker_col} = p.t AND o.{date_col} = p.max_pvm
                ),
                all_rows AS (
                    SELECT * FROM prev_rows
                    UNION ALL
                    SELECT * FROM base_rows
                )
                SELECT
                    ticker,
                    pvm,
                    close,
                    volume,
                    LAG(close) OVER (PARTITION BY ticker ORDER BY pvm) AS prev_close
                FROM all_rows
                WHERE pvm >= ?
                ORDER BY ticker ASC, pvm ASC
                """,
                query_params,
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT o.{ticker_col} AS ticker,
                       o.{date_col} AS pvm,
                       o.{close_col} AS close,
                       o.{volume_col} AS volume
                FROM osakedata o
                JOIN ticker_meta tm ON tm.ticker = o.{ticker_col}
                WHERE LOWER(tm.market) = LOWER(?)
                  {sector_filter}
                  {industry_filter}
                  AND tm.ticker NOT LIKE '^%'
                  AND o.{date_col} >= ?
                ORDER BY o.{ticker_col} ASC, o.{date_col} ASC
                """,
                params + [base_start],
            ).fetchall()

        if not rows:
            continue

        per_date_returns: Dict[str, List[float]] = defaultdict(list)
        per_date_volume: Dict[str, float] = defaultdict(float)
        tickers_used: Dict[str, set] = defaultdict(set)
        last_close_by_ticker: Dict[str, float] = {}

        for row in rows:
            ticker = row["ticker"]
            date_str = row["pvm"]
            close_val = row["close"]
            vol_val = row["volume"] or 0.0
            if not ticker or date_str is None or close_val is None:
                continue
            prev = row["prev_close"] if "prev_close" in row.keys() else None
            if prev is None:
                prev = last_close_by_ticker.get(ticker)
            if prev is not None and prev != 0:
                ret = float(close_val) / float(prev) - 1.0
                # Suodata epärealistiset piikit (esim. >500%) jotka vääristävät indeksiä
                if abs(ret) <= 5.0:
                    per_date_returns[date_str].append(ret)
                    tickers_used[date_str].add(ticker)
            per_date_volume[date_str] += float(vol_val or 0.0)
            last_close_by_ticker[ticker] = float(close_val)

        dates_sorted = sorted(per_date_returns.keys())
        if last_date:
            dates_sorted = [d for d in dates_sorted if d > last_date]

        prev_value = last_value
        inserted = 0
        for d in dates_sorted:
            returns = per_date_returns.get(d, [])
            if not returns:
                continue
            daily_ret = sum(returns) / len(returns)
            if prev_value is None:
                index_value = 100.0
                daily_ret_to_store = None
            else:
                index_value = prev_value * (1.0 + daily_ret)
                daily_ret_to_store = daily_ret
            conn.execute(
                """
                INSERT OR REPLACE INTO index_daily
                    (date, level, market, sector, industry, index_value, daily_return, volume_sum, n_stocks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d,
                    level,
                    market,
                    sector,
                    industry,
                    index_value,
                    daily_ret_to_store,
                    per_date_volume.get(d, 0.0),
                    len(tickers_used.get(d, set())),
                ),
            )
            prev_value = index_value
            inserted += 1
        summary["updated_rows"] += inserted
        logger(
            f"[INDEX] {market} {level} {sector or ''} {industry or ''} inserted {inserted} rows"
        )

    conn.commit()
    return summary


def fetch_index_series(
    conn: sqlite3.Connection,
    market: str,
    sectors: Sequence[str],
    *,
    include_market: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, List[IndexRow]]:
    """Hae indeksi- ja volyymisarjat."""
    level_params: List[object] = []
    where_params: List[object] = []
    where_clauses = []
    where_clauses.append("market = ?")
    where_params.append(market)
    if date_from:
        where_clauses.append("date >= ?")
        where_params.append(date_from)
    if date_to:
        where_clauses.append("date <= ?")
        where_params.append(date_to)
    level_filters = []
    if include_market:
        level_filters.append("(level = 'market')")
    if sectors:
        placeholders = ",".join(["?"] * len(sectors))
        level_filters.append(f"(level = 'sector' AND sector IN ({placeholders}))")
        level_params.extend(sectors)
    if not level_filters:
        return {}
    where_sql = " AND ".join(where_clauses)
    level_sql = " OR ".join(level_filters)
    query = f"""
        SELECT date, level, market, sector, industry, index_value, volume_sum, n_stocks
        FROM index_daily
        WHERE ({level_sql}) AND {where_sql}
        ORDER BY date ASC
    """
    params = level_params + where_params
    rows = conn.execute(query, params).fetchall()
    result: Dict[str, List[IndexRow]] = {}
    for row in rows:
        key = row["sector"] if row["level"] == "sector" else "MARKET"
        level = row["level"]
        market = row["market"]
        sector = row["sector"]
        industry = row["industry"]
        if level == "market":
            name = market
        elif level == "sector":
            name = " | ".join([p for p in (market, sector) if p])
        elif level == "industry":
            name = " | ".join([p for p in (market, sector, industry) if p])
        else:
            name = market
        result.setdefault(key, []).append(
            {
                "date": dt.date.fromisoformat(row["date"]),
                "value": float(row["index_value"]),
                "volume": float(row["volume_sum"] or 0.0),
                "n": int(row["n_stocks"] or 0),
                "level": row["level"],
                "scope": level,
                "name": name,
            }
        )
    return result


def fetch_stock_series(
    conn: sqlite3.Connection,
    schema: SchemaMap,
    ticker: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[IndexRow]:
    ticker_col = schema.get("ticker")
    date_col = schema.get("date")
    close_col = schema.get("close")
    high_col = schema.get("high")
    low_col = schema.get("low")
    if not (ticker_col and date_col and close_col):
        return []
    where = [f"{ticker_col} = ?"]
    params: List[object] = [ticker]
    if date_from:
        where.append(f"{date_col} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date_col} <= ?")
        params.append(date_to)

    # Hae high ja low jos saatavilla
    high_select = f"{high_col} AS high" if high_col else "NULL AS high"
    low_select = f"{low_col} AS low" if low_col else "NULL AS low"

    query = f"""
        SELECT {date_col} AS pvm, {close_col} AS close, {high_select}, {low_select}
        FROM osakedata
        WHERE {' AND '.join(where)}
        ORDER BY {date_col} ASC
    """
    rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        if r["close"] is not None and r["pvm"]:
            row_dict = {
                "date": dt.date.fromisoformat(r["pvm"]),
                "value": float(r["close"]),
                "close": float(r["close"]),
                "scope": "equity",
                "name": ticker,
            }
            if r["high"] is not None:
                row_dict["high"] = float(r["high"])
            if r["low"] is not None:
                row_dict["low"] = float(r["low"])
            result.append(row_dict)
    return result


def normalize_series_to_100(series: List[IndexRow]) -> List[IndexRow]:
    if not series:
        return []
    first = series[0]["value"]
    if not first:
        return series
    result = []
    for row in series:
        normalized = {
            **row,
            "value": (row["value"] / first) * 100.0 if first else row["value"],
        }
        # Normalisoi myös high ja low jos olemassa
        if "high" in row and row["high"] is not None:
            normalized["high"] = (row["high"] / first) * 100.0
        if "low" in row and row["low"] is not None:
            normalized["low"] = (row["low"] / first) * 100.0
        result.append(normalized)
    return result
