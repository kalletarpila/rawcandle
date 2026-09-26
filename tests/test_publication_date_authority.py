from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals import phase12d
from rawcandle.fundamentals.admin import first_public_result_date_bootstrap as bootstrap
from rawcandle.fundamentals.admin.refresh_fundamentals import publication_date_gate_authorized
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.schema.migrations import bootstrap_all
from rawcandle.fundamentals.schema.production_bootstrap import (
    insert_production_sharadar_observation,
)
from rawcandle.fundamentals.phase13b_foundation import online_backup


NOW = "2026-09-26T12:00:00Z"


def _source_row(
    ticker: str,
    company_id: int,
    *,
    fiscalperiod: str = "2025-Q1",
    reportperiod: str = "2025-03-31",
    filing_date: str = "2025-05-01",
    lastupdated: str = "2026-09-01",
    assets: int = 100,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "permaticker": str(company_id),
        "dimension": "ARQ",
        "calendardate": reportperiod,
        "reportperiod": reportperiod,
        "fiscalperiod": fiscalperiod,
        "date": filing_date,
        "lastupdated": lastupdated,
        "assets": assets,
        "revenue": 10,
    }


def _financial_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        for table in (
            "v4_quarter_financials",
            "v4_ttm_contract",
            "v4_ttm_values",
            "v4_ttm_input_quarter",
        ):
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            digest.update(repr(rows).encode("utf-8"))
    return digest.hexdigest()


def _acceptance_paths(tmp_path: Path) -> BatchAddTickerPaths:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    bootstrap_all(provider, canonical, analysis, NOW)
    for path in (market, taxonomy):
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE marker(value TEXT)")
    with sqlite3.connect(provider) as connection:
        connection.execute(
            "INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) "
            "VALUES('run','SHARADAR',?,'COMPLETE','fixture')",
            (NOW,),
        )
        for company_id in range(1, 1016):
            ticker = f"T{company_id:04d}"
            assert insert_production_sharadar_observation(
                connection,
                _source_row(ticker, company_id),
                "run",
                NOW,
                company_id=company_id,
                security_id=company_id,
            )
        valid_spcb = _source_row(
            "SPCB", 2000,
            fiscalperiod="2022-Q4",
            reportperiod="2022-12-31",
            filing_date="2023-04-20",
            lastupdated="2026-04-29",
            assets=42_040_000,
        )
        invalid_spcb = dict(
            valid_spcb,
            date="2022-05-20",
            lastupdated="2026-09-08",
            assets=45_077_000,
        )
        for row in (valid_spcb, invalid_spcb):
            assert insert_production_sharadar_observation(
                connection, row, "run", NOW, company_id=2000, security_id=2000,
            )
    with sqlite3.connect(canonical) as connection:
        for company_id in [*range(1, 1016), 2000]:
            ticker = "SPCB" if company_id == 2000 else f"T{company_id:04d}"
            connection.execute(
                "INSERT INTO company(company_id,company_key,company_name,status,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,'ACTIVE',?,?)",
                (company_id, ticker, ticker, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO security(security_id,company_id,current_ticker,active,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,1,?,?)",
                (company_id, company_id, ticker, NOW, NOW),
            )
            spcb = company_id == 2000
            year, quarter = (2022, "Q4") if spcb else (2025, "Q1")
            period_end = "2022-12-31" if spcb else "2025-03-31"
            source_date = "2022-05-20" if spcb else "2025-05-01"
            fiscalperiod = f"{year}-{quarter}"
            cursor = connection.execute(
                "INSERT INTO v4_quarter(company_id,fiscal_year,fiscal_quarter,period_end,"
                "source_fiscalperiod,source_reportperiod,identity_provider,identity_status,"
                "source_availability_date,first_public_result_date,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?,?,'SHARADAR_ARQ','ACCEPTED',?,NULL,?,?)",
                (
                    company_id, year, quarter, period_end, fiscalperiod, period_end,
                    source_date, NOW, NOW,
                ),
            )
            connection.execute(
                "INSERT INTO v4_quarter_financials(quarter_id,revenue,total_assets,"
                "canonical_source_policy,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,'SHARADAR_ARQ_PRIMARY',?,?)",
                (
                    int(cursor.lastrowid), 10,
                    45_077_000 if spcb else 100,
                    NOW, NOW,
                ),
            )
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def test_exact_1015_copy_only_bootstrap_and_generic_spcb_repair(tmp_path: Path) -> None:
    paths = _acceptance_paths(tmp_path / "source")
    candidate = tmp_path / "candidate.db"
    online_backup(paths.canonical_db, candidate)
    candidate_paths = BatchAddTickerPaths(
        paths.provider_db, candidate, paths.analysis_db, paths.market_db, paths.taxonomy_db,
    )
    established_before = bootstrap._established_first_public_values(candidate)
    identity_before = bootstrap.audit_canonical(candidate)["identity_fingerprint"]
    non_target_before = bootstrap.audit_canonical(candidate)["non_target_canonical_fingerprint"]
    financial_before = _financial_fingerprint(candidate)

    initial = bootstrap.authorized_bootstrap_plan(candidate_paths)
    assert initial["eligible_count"] == 1015
    assert initial["repair_required_count"] == 1
    assert initial["repair_required"][0]["company_id"] == 2000

    stale_item = initial["eligible"][0]
    with sqlite3.connect(candidate) as connection:
        connection.execute(
            "UPDATE v4_quarter SET source_availability_date='2025-05-02' WHERE quarter_id=?",
            (stale_item["quarter_id"],),
        )
    with pytest.raises(bootstrap.StaleBootstrapPreview, match="AUTHORIZED_BOOTSTRAP_PLAN_STALE"):
        bootstrap.apply_authorized_bootstrap(candidate, initial)
    with sqlite3.connect(candidate) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM v4_quarter WHERE first_public_result_date IS NOT NULL"
        ).fetchone()[0] == 0
        connection.execute(
            "UPDATE v4_quarter SET source_availability_date=? WHERE quarter_id=?",
            (stale_item["source_availability_date"], stale_item["quarter_id"]),
        )

    assert bootstrap.apply_authorized_bootstrap(candidate, initial) == 1015
    assert bootstrap._established_first_public_values(candidate).items() >= established_before.items()
    assert bootstrap.audit_canonical(candidate)["identity_fingerprint"] == identity_before
    assert bootstrap.audit_canonical(candidate)["non_target_canonical_fingerprint"] == non_target_before
    assert _financial_fingerprint(candidate) == financial_before

    after_bootstrap = bootstrap.authorized_bootstrap_plan(candidate_paths)
    assert after_bootstrap["eligible_count"] == 0
    assert after_bootstrap["repair_required_count"] == 1

    phase12d.reconcile_canonical(paths.provider_db, candidate, applied_at=NOW)
    after_winner_fix = bootstrap.authorized_bootstrap_plan(candidate_paths)
    assert after_winner_fix["eligible_count"] == 1
    assert after_winner_fix["repair_required_count"] == 0
    assert after_winner_fix["eligible"][0]["accepted_winner_date"] == "2023-04-20"
    assert bootstrap.apply_authorized_bootstrap(candidate, after_winner_fix) == 1

    final = bootstrap.authorized_bootstrap_plan(candidate_paths)
    assert final["eligible_count"] == 0
    assert final["repair_required_count"] == 0
    assert publication_date_gate_authorized({
        "historical_bootstrap_eligible": final["eligible_count"],
        "repair_required": final["repair_required_count"],
    }) is True
    with sqlite3.connect(candidate) as connection:
        spcb = connection.execute(
            "SELECT q.source_availability_date,q.first_public_result_date,f.total_assets "
            "FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) "
            "WHERE q.company_id=2000"
        ).fetchone()
    assert spcb == ("2023-04-20", "2023-04-20", 42_040_000)
    assert bootstrap._established_first_public_values(candidate).items() >= established_before.items()
