from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.providers.sharadar import (
    AUTH_OK,
    STATUS_SUCCESS,
    SharadarResult,
)
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
)
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema


NOW = "2026-09-22T12:00:00Z"


@dataclass
class ParityFixture:
    paths: BatchAddTickerPaths
    rows: dict[str, list[dict[str, Any]]]
    expected_arq: dict[str, int]


class FixtureSharadarClient:
    calls: list[dict[str, Any]] = []
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {}

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.request_count = 0

    def fundamentals(self, **kwargs: Any) -> SharadarResult:
        self.request_count += 1
        self.calls.append(dict(kwargs))
        ticker = str(kwargs["ticker"]).upper()
        rows = [dict(row) for row in self.rows_by_ticker.get(ticker, ())]
        return SharadarResult(
            status=STATUS_SUCCESS,
            auth_status=AUTH_OK,
            http_status=200,
            endpoint="fundamentals",
            url=f"fixture://sharadar/fundamentals/{ticker}",
            request_count=self.request_count,
            records=rows,
            payload=rows,
        )


def _quarter_rows(ticker: str, *, start_year: int, start_quarter: int, count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(count):
        sequence = start_year * 4 + start_quarter - 1 + offset
        year, zero_quarter = divmod(sequence, 4)
        quarter = zero_quarter + 1
        month = quarter * 3
        period = f"{year}-{month:02d}-28"
        publication = f"{year + 1}-02-20" if month == 12 else f"{year}-{month + 1:02d}-20"
        base = {
            "ticker": ticker,
            "calendardate": period,
            "reportperiod": period,
            "fiscalperiod": f"{year}-Q{quarter}",
            "date": publication,
            "lastupdated": publication,
            "revenue": 100.0 + offset * 8,
            "gp": 60.0 + offset * 4,
            "opinc": 20.0 + offset * 2,
            "ebit": 19.0 + offset * 2,
            "ebitda": 24.0 + offset * 2,
            "netinc": 12.0 + offset,
            "netinccmn": 11.0 + offset,
            "ncfo": 18.0 + offset,
            "capex": -5.0,
            "fcf": 13.0 + offset,
            "cashneq": 50.0 + offset,
            "debt": 20.0,
            "debtc": 5.0,
            "debtnc": 15.0,
            "sharesbas": 10.0,
            "shareswa": 10.0,
            "shareswadil": 10.0,
            "receivables": 12.0,
            "inventory": 8.0,
            "payables": 7.0,
            "deferredrev": 3.0,
            "assets": 250.0,
            "permaticker": None,
        }
        rows.extend((dict(base, dimension="ARQ"), dict(base, dimension="MRQ")))
    return rows


def _provider(path: Path) -> None:
    bootstrap_database(path, "fundamentals_provider", PROVIDER_SCHEMA_SQL, NOW)
    rows = (
        ("CYCN", "111101", "Cyclerion Therapeutics", "0001755237"),
        ("BBCQ", "646033", "Blaize Holdings", "0002088295"),
        ("QVCAQ", "194557", "Old QVC Group", "0001355096"),
    )
    with sqlite3.connect(path) as connection:
        for ticker, permaticker, name, cik in rows:
            connection.execute(
                "INSERT INTO sharadar_ticker_metadata("
                "table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,"
                "secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json,fetched_at_utc"
                ") VALUES('fundamentals',?,?,?,'NASDAQ','N','Domestic Common Stock','',?,?,?, ?,?,?, '{}',?)",
                (
                    ticker, permaticker, name,
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                    "2020-01-01", "2026-09-21", "2020-03-31", "2026-06-30", "2026-09-21", NOW,
                ),
            )


def _canonical(path: Path) -> None:
    bootstrap_database(path, "fundamentals_v4", CANONICAL_SCHEMA_SQL, NOW)
    with sqlite3.connect(path) as connection:
        ensure_ttm_schema(connection)
        connection.execute(
            "INSERT INTO company VALUES(627,'SEC_CIK:0001755237','Cyclerion Therapeutics','ACTIVE',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO security VALUES(628,627,'CYCN','NASDAQ',1,'2019-01-01',NULL,?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO company_cik(company_id,cik_normalized,cik_display,source,status,created_at_utc) "
            "VALUES(627,'0001755237','0001755237','fixture','ACTIVE',?)",
            (NOW,),
        )
        for company_id, security_id, ticker, name in (
            (700, 700, "BBCQ", "Blaize Holdings"),
            (701, 701, "QVCAQ", "Old QVC Group"),
        ):
            connection.execute(
                "INSERT INTO company VALUES(?,?,?,'INACTIVE',?,?)",
                (company_id, f"FIXTURE:{ticker}", name, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,'NASDAQ',0,'2020-01-01','2026-09-01',?,?)",
                (security_id, company_id, ticker, NOW, NOW),
            )
        for company_id, ticker in enumerate(("VMRK", "IA", "VAI", "NXH", "NMAD"), start=800):
            connection.execute(
                "INSERT INTO company VALUES(?,?,?,'ACTIVE',?,?)",
                (company_id, f"FIXTURE:{ticker}", ticker, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,'NASDAQ',1,'2020-01-01',NULL,?,?)",
                (company_id, company_id, ticker, NOW, NOW),
            )


def _market(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ticker_meta(ticker TEXT,market TEXT,sector TEXT,industry TEXT);
            CREATE TABLE osakedata(
                id INTEGER PRIMARY KEY,osake TEXT,market TEXT,pvm TEXT,
                open REAL,high REAL,low REAL,close REAL
            );
            CREATE TABLE splits_data(
                osake TEXT,split_date TEXT,split_ratio REAL,is_price_data_corrected INTEGER
            );
            """
        )
        for ticker, price in (("KRSA", 11.0), ("PSQL", 9.0), ("QVCG", 14.0)):
            connection.execute(
                "INSERT INTO ticker_meta VALUES(?,'usa','Technology','Software - Application')",
                (ticker,),
            )
            connection.executemany(
                "INSERT INTO osakedata(osake,market,pvm,open,high,low,close) "
                "VALUES(?,'usa',?,?,?,?,?)",
                (
                    (ticker, price_date, price, price + 1, price - 1, price)
                    for price_date in ("2024-01-02", "2026-07-01", "2026-09-20")
                ),
            )


def _taxonomy(path: Path, root: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE dc_ecosystem_membership(
                taxonomy_version TEXT NOT NULL,ticker TEXT NOT NULL,layer TEXT NOT NULL,
                subindustry TEXT NOT NULL,report_group_status TEXT NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 0,role_weight REAL NOT NULL DEFAULT 1.0,
                notes TEXT,created_at_utc TEXT NOT NULL,
                PRIMARY KEY(taxonomy_version,ticker,layer,subindustry)
            )
            """
        )
    apply_ec_sidecar_migration(str(path))
    csv_path = root / "taxonomy.csv"
    csv_path.write_text(
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
        "DC_PARITY_V1,KRSA,Compute,Software,CORE,1,1.0,\n"
        "DC_PARITY_V1,QVCG,Compute,Software,CORE,1,1.0,\n",
        encoding="utf-8",
    )
    load_datacenter_taxonomy_to_ec_sidecar(path, csv_path, "DC_PARITY_V1", mark_active=True)


def build_parity_fixture(root: Path) -> ParityFixture:
    root.mkdir(parents=True, exist_ok=True)
    paths = BatchAddTickerPaths(
        root / "provider.db",
        root / "canonical.db",
        root / "analysis.db",
        root / "market.db",
        root / "taxonomy.db",
    )
    _provider(paths.provider_db)
    _canonical(paths.canonical_db)
    with sqlite3.connect(paths.analysis_db) as connection:
        connection.execute("CREATE TABLE fixture_generation(value TEXT NOT NULL)")
        connection.execute("INSERT INTO fixture_generation VALUES('OLD')")
    _market(paths.market_db)
    _taxonomy(paths.taxonomy_db, root)
    rows = {
        "KRSA": _quarter_rows("KRSA", start_year=2024, start_quarter=3, count=8),
        "PSQL": _quarter_rows("PSQL", start_year=2025, start_quarter=4, count=3),
        "QVCG": _quarter_rows("QVCG", start_year=2024, start_quarter=3, count=8),
    }
    return ParityFixture(paths, rows, {ticker: len(values) // 2 for ticker, values in rows.items()})
