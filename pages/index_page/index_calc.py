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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS index_daily (
            date TEXT NOT NULL,
            level TEXT NOT NULL,
            market TEXT NOT NULL,
            sector TEXT,
            index_value REAL NOT NULL,
            daily_return REAL,
            volume_sum REAL,
            n_stocks INTEGER,
            UNIQUE(date, level, market, sector)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_index_daily_level_market_sector_date ON index_daily(level, market, sector, date)"
    )


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


def get_available_markets(conn: sqlite3.Connection, schema: SchemaMap) -> List[str]:
    market_col = schema.get("market")
    if not market_col:
        return []
    cursor = conn.execute(
        f"SELECT DISTINCT LOWER({market_col}) AS m FROM osakedata WHERE {market_col} IS NOT NULL ORDER BY m"
    )
    return [row["m"] for row in cursor.fetchall() if row["m"]]


def get_sectors_for_market(
    conn: sqlite3.Connection, schema: SchemaMap, market: str
) -> List[str]:
    market_col = schema.get("market")
    sector_col = schema.get("sector")
    if not market_col or not sector_col:
        return []
    cursor = conn.execute(
        f"""
        SELECT DISTINCT {sector_col} AS sector
        FROM osakedata
        WHERE LOWER({market_col}) = LOWER(?)
          AND {sector_col} IS NOT NULL
          AND TRIM({sector_col}) <> ''
        ORDER BY sector
        """,
        (market,),
    )
    return [row["sector"] for row in cursor.fetchall()]


def get_tickers_for_market_sectors(
    conn: sqlite3.Connection, schema: SchemaMap, market: str, sectors: Sequence[str]
) -> List[str]:
    ticker_col = schema.get("ticker")
    market_col = schema.get("market")
    sector_col = schema.get("sector")
    if not ticker_col or not market_col:
        return []
    params: List[object] = [market]
    sector_filter = ""
    if sectors and sector_col:
        placeholders = ",".join(["?"] * len(sectors))
        sector_filter = f" AND {sector_col} IN ({placeholders})"
        params.extend(sectors)
    cursor = conn.execute(
        f"""
        SELECT DISTINCT {ticker_col} AS ticker
        FROM osakedata
        WHERE LOWER({market_col}) = LOWER(?)
        {sector_filter}
        ORDER BY ticker
        """,
        params,
    )
    return [row["ticker"] for row in cursor.fetchall() if row["ticker"]]


def _fetch_last_index_info(
    conn: sqlite3.Connection, market: str, sector: Optional[str]
) -> Tuple[Optional[str], Optional[float]]:
    cursor = conn.execute(
        """
        SELECT date, index_value
        FROM index_daily
        WHERE level = ? AND market = ? AND (sector IS ? OR sector = ?)
        ORDER BY date DESC
        LIMIT 1
        """,
        ("sector" if sector else "market", market, sector, sector),
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
) -> Dict[str, int]:
    """Laske markkina- ja sektoritasoiset indeksit incrementaalisesti."""
    schema = introspect_schema(conn)
    ticker_col = schema.get("ticker")
    date_col = schema.get("date")
    close_col = schema.get("close")
    volume_col = schema.get("volume")
    market_col = schema.get("market")
    sector_col = schema.get("sector")
    if not (ticker_col and date_col and close_col and volume_col and market_col):
        raise RuntimeError("osakedata-taulusta puuttuu vaadittuja sarakkeita")

    ensure_index_table(conn)
    ensure_osakedata_indexes(conn, schema)

    target_sectors = list(sectors or [])
    groups = [("market", None)] + [("sector", sec) for sec in target_sectors]

    summary = {"updated_rows": 0, "groups": len(groups)}

    for level, sector in groups:
        last_date, last_value = _fetch_last_index_info(conn, market, sector)
        base_start = last_date or start_date

        logger(
            f"[INDEX] {market} {('sector ' + sector) if sector else 'market'} start from {base_start} (last={last_date or 'none'})"
        )

        params: List[object] = [market]
        sector_filter = ""
        if sector and sector_col:
            sector_filter = f" AND {sector_col} = ?"
            params.append(sector)

        rows: List[sqlite3.Row] = []
        try:
            conn.execute("SELECT LAG(1) OVER (ORDER BY 1)")
            use_lag = True
        except sqlite3.OperationalError:
            use_lag = False

        if use_lag:
            base_params = list(params)  # [market] or [market, sector]
            query_params = base_params + [base_start] + base_params + [base_start] + [base_start]
            rows = conn.execute(
                f"""
                WITH base_rows AS (
                    SELECT
                        {ticker_col} AS ticker,
                        {date_col} AS pvm,
                        {close_col} AS close,
                        {volume_col} AS volume
                    FROM osakedata
                    WHERE LOWER({market_col}) = LOWER(?)
                      {sector_filter}
                      AND {date_col} >= ?
                ),
                prev_rows AS (
                    SELECT
                        o.{ticker_col} AS ticker,
                        o.{date_col} AS pvm,
                        o.{close_col} AS close,
                        o.{volume_col} AS volume
                    FROM osakedata o
                    JOIN (
                        SELECT {ticker_col} AS t, MAX({date_col}) AS max_pvm
                        FROM osakedata
                        WHERE LOWER({market_col}) = LOWER(?)
                          {sector_filter}
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
                SELECT {ticker_col} AS ticker,
                       {date_col} AS pvm,
                       {close_col} AS close,
                       {volume_col} AS volume
                FROM osakedata
                WHERE LOWER({market_col}) = LOWER(?)
                  {sector_filter}
                  AND {date_col} >= ?
                ORDER BY {ticker_col} ASC, {date_col} ASC
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
                    (date, level, market, sector, index_value, daily_return, volume_sum, n_stocks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d,
                    level,
                    market,
                    sector,
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
            f"[INDEX] {market} {('sector ' + sector) if sector else 'market'} inserted {inserted} rows"
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
    params: List[object] = []
    where_clauses = []
    where_clauses.append("market = ?")
    params.append(market)
    if date_from:
        where_clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("date <= ?")
        params.append(date_to)
    level_filters = []
    if include_market:
        level_filters.append("(level = 'market')")
    if sectors:
        placeholders = ",".join(["?"] * len(sectors))
        level_filters.append(f"(level = 'sector' AND sector IN ({placeholders}))")
        params.extend(sectors)
    if not level_filters:
        return {}
    where_sql = " AND ".join(where_clauses)
    level_sql = " OR ".join(level_filters)
    query = f"""
        SELECT date, level, market, sector, index_value, volume_sum, n_stocks
        FROM index_daily
        WHERE ({level_sql}) AND {where_sql}
        ORDER BY date ASC
    """
    rows = conn.execute(query, params).fetchall()
    result: Dict[str, List[IndexRow]] = {}
    for row in rows:
        key = row["sector"] if row["level"] == "sector" else "MARKET"
        result.setdefault(key, []).append(
            {
                "date": dt.date.fromisoformat(row["date"]),
                "value": float(row["index_value"]),
                "volume": float(row["volume_sum"] or 0.0),
                "n": int(row["n_stocks"] or 0),
                "level": row["level"],
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
    query = f"""
        SELECT {date_col} AS pvm, {close_col} AS close
        FROM osakedata
        WHERE {' AND '.join(where)}
        ORDER BY {date_col} ASC
    """
    rows = conn.execute(query, params).fetchall()
    return [
        {"date": dt.date.fromisoformat(r["pvm"]), "value": float(r["close"])}
        for r in rows
        if r["close"] is not None and r["pvm"]
    ]


def normalize_series_to_100(series: List[IndexRow]) -> List[IndexRow]:
    if not series:
        return []
    first = series[0]["value"]
    if not first:
        return series
    return [
        {
            **row,
            "value": (row["value"] / first) * 100.0 if first else row["value"],
        }
        for row in series
    ]
