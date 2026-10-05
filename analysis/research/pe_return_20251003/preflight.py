"""Read-only feasibility check; intentionally does not calculate a PIT dataset."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from rawcandle.fundamentals.generations import resolved_production_paths

START_DATE = "2025-10-03"
END_DATE = "2026-10-02"
CUTOFF_EXCLUSIVE = "2025-10-04"


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def inspect(root: Path) -> dict:
    paths = resolved_production_paths(root)
    with closing(readonly(paths["taxonomy"])) as connection:
        versions = connection.execute(
            "SELECT v.taxonomy_version_id,v.taxonomy_version_code,v.taxonomy_name "
            "FROM ec_taxonomy_version v JOIN ec_ecosystem e USING(ecosystem_id) "
            "WHERE e.ecosystem_code='DATACENTER' AND v.is_active=1"
        ).fetchall()
        if len(versions) != 1:
            raise RuntimeError("ACTIVE_TAXONOMY_NOT_UNIQUE")
        version = dict(versions[0])
        members = connection.execute(
            "SELECT e.ticker,m.membership_role FROM ec_membership m "
            "JOIN ec_entity e ON e.entity_id=m.child_entity_id "
            "WHERE m.taxonomy_version_id=? AND m.status='ACTIVE' "
            "AND m.membership_type='CONTAINS' AND e.entity_type='TICKER' "
            "AND e.ticker IS NOT NULL ORDER BY e.ticker,m.membership_id",
            (version["taxonomy_version_id"],),
        ).fetchall()
    tickers = sorted({r["ticker"].strip().upper() for r in members})
    if not tickers:
        raise RuntimeError("EMPTY_ACTIVE_TAXONOMY")
    placeholders = ",".join("?" for _ in tickers)
    with closing(readonly(paths["market"])) as connection:
        price_rows = connection.execute(
            f"SELECT osake,pvm,close FROM osakedata WHERE osake IN ({placeholders}) "
            "AND pvm IN (?,?)", (*tickers, START_DATE, END_DATE),
        ).fetchall()
    price_counts = Counter((r["osake"], r["pvm"]) for r in price_rows)
    price_coverage = {
        day: len({r["osake"] for r in price_rows if r["pvm"] == day and r["close"] is not None})
        for day in (START_DATE, END_DATE)
    }
    with closing(readonly(paths["canonical"])) as connection:
        fields = [r["name"] for r in connection.execute("PRAGMA table_info(v4_quarter_financials)")]
        securities = connection.execute(
            f"SELECT current_ticker,company_id FROM security WHERE active=1 "
            f"AND current_ticker IN ({placeholders})", tickers,
        ).fetchall()
        companies = sorted({r["company_id"] for r in securities})
        if companies:
            company_params = ",".join("?" for _ in companies)
            authority = connection.execute(
                "SELECT a.status,count(*) AS rows FROM v4_result_publication_authority a "
                f"WHERE a.company_id IN ({company_params}) "
                "AND a.result_publication_timestamp_utc < ? GROUP BY a.status",
                (*companies, CUTOFF_EXCLUSIVE),
            ).fetchall()
        else:
            authority = []
    with closing(readonly(paths["provider"])) as connection:
        times = dict(connection.execute(
            "SELECT min(fetched_at_utc) AS first_fetch,max(fetched_at_utc) AS last_fetch,"
            "min(observed_at_utc) AS first_observation FROM provider_observation"
        ).fetchone())
        stored_before = connection.execute(
            "SELECT count(*) FROM provider_observation WHERE fetched_at_utc < ? "
            "OR observed_at_utc < ?", (CUTOFF_EXCLUSIVE, CUTOFF_EXCLUSIVE),
        ).fetchone()[0]
        payload_coverage = dict(connection.execute(
            "SELECT count(*) AS arq_observations,"
            "sum(json_type(payload_json,'$.eps') IS NOT NULL) AS payload_eps_fields,"
            "sum(json_type(payload_json,'$.epsdil') IS NOT NULL) AS payload_epsdil_fields "
            f"FROM provider_observation WHERE dimension='ARQ' AND provider_ticker IN ({placeholders})",
            tickers,
        ).fetchone())
    security_counts = Counter(r["current_ticker"] for r in securities)
    return {
        "status": "STOP_INSUFFICIENT_ORIGINAL_PIT_EPS_HISTORY",
        "start_price_date": START_DATE,
        "end_price_date": END_DATE,
        "sources": {role: str(path) for role, path in paths.items()},
        "taxonomy": {
            **version, "tables": ["ec_taxonomy_version", "ec_ecosystem", "ec_membership", "ec_entity"],
            "membership_rows": len(members), "unique_tickers": len(tickers),
            "membership_roles": dict(Counter(r["membership_role"] for r in members)),
            "role_filter": "NONE",
        },
        "prices": {"table": "osakedata", "ticker_field": "osake", "date_field": "pvm",
                   "price_field": "close", "non_null_close_tickers_by_exact_date": price_coverage,
                   "duplicate_ticker_date_keys": sum(n > 1 for n in price_counts.values())},
        "fundamentals": {
            "quarter_table": "v4_quarter", "financial_table": "v4_quarter_financials",
            "canonical_eps_field": None, "canonical_financial_fields": fields,
            "publication_table": "v4_result_publication_authority",
            "publication_field": "result_publication_timestamp_utc",
            "pre_cutoff_authority_rows_for_exact_active_security_mapping": {r["status"]: r["rows"] for r in authority},
            "exact_active_security_mapped_tickers": len(security_counts),
            "non_unique_active_security_tickers": sum(n != 1 for n in security_counts.values()),
            "provider_times": times, "all_provider_observations_recorded_before_cutoff": stored_before,
            "taxonomy_provider_payload_coverage": payload_coverage,
            "eps_semantics": "NO_CANONICAL_REPORTED_EPS_CONTRACT;raw eps/epsdil are not approved PIT inputs",
            "history_contract": "REVISED_HISTORY_FROM_2026_SNAPSHOT_NOT_ORIGINAL_PIT",
        },
        "dataset_created": False, "regression_run": False, "external_requests": 0,
        "stop_reason": "Official result timestamp does not version the EPS value. Existing revised-history contract and later provider observations cannot prove the original EPS known at cutoff.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(inspect(args.repo_root.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
