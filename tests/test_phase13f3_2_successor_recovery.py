from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.fundamentals.phase13f3_2_successor_recovery import (
    nxh_contamination_artifact,
    stage_provider_rows,
    structural_endpoint_policy,
)


def _minimal_provider(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE provider_run(
                run_id TEXT PRIMARY KEY,
                provider TEXT,
                started_at_utc TEXT,
                completed_at_utc TEXT,
                status TEXT,
                request_scope TEXT,
                entitlement_scope TEXT,
                source_version TEXT,
                metadata_json TEXT
            );
            CREATE TABLE provider_observation(
                observation_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES provider_run(run_id),
                provider TEXT NOT NULL,
                provider_record_key TEXT NOT NULL,
                company_id INTEGER,
                security_id INTEGER,
                provider_ticker TEXT,
                provider_security_id TEXT,
                native_table TEXT NOT NULL,
                dimension TEXT,
                calendardate TEXT,
                reportperiod TEXT,
                fiscalperiod TEXT,
                source_availability_date TEXT,
                observed_at_utc TEXT,
                fetched_at_utc TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provider_status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(provider,native_table,provider_record_key,content_hash)
            );
            CREATE TABLE sharadar_fundamental_observation(
                observation_id TEXT PRIMARY KEY REFERENCES provider_observation(observation_id) ON DELETE CASCADE,
                ticker TEXT NOT NULL,
                permaticker TEXT,
                dimension TEXT NOT NULL,
                calendardate TEXT,
                reportperiod TEXT NOT NULL,
                fiscalperiod TEXT,
                date TEXT,
                lastupdated TEXT,
                revenue INTEGER,
                gp INTEGER,
                opinc INTEGER,
                ebit INTEGER,
                ebitda INTEGER,
                netinc INTEGER,
                netinccmn INTEGER,
                ncfo INTEGER,
                capex INTEGER,
                fcf INTEGER,
                cashneq INTEGER,
                debt INTEGER,
                debtc INTEGER,
                debtnc INTEGER,
                sharesbas INTEGER,
                shareswa INTEGER,
                shareswadil INTEGER,
                receivables INTEGER,
                inventory INTEGER,
                payables INTEGER,
                deferredrev INTEGER,
                assets INTEGER
            );
            """
        )


def _minimal_canonical(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE security(company_id INTEGER,security_id INTEGER,current_ticker TEXT)")
        conn.executemany(
            "INSERT INTO security VALUES(?,?,?)",
            ((787, 788, "VMRK"), (1166, 1170, "IA"), (82, 82, "VAI"), (278, 278, "NXH"), (1304, 1311, "NMAD")),
        )


def _minimal_structural_canonical(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE security(company_id INTEGER,security_id INTEGER,current_ticker TEXT);
            CREATE TABLE v4_quarter(company_id INTEGER,period_end TEXT,source_availability_date TEXT);
            CREATE TABLE v4_ttm_values(
                company_id INTEGER,
                period_end TEXT,
                ttm_source_available_date TEXT,
                readiness_status TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO security VALUES(?,?,?)",
            ((787, 788, "VMRK"), (1166, 1170, "IA"), (82, 82, "VAI"), (278, 278, "NXH"), (1304, 1311, "NMAD")),
        )
        conn.executemany(
            "INSERT INTO v4_ttm_values VALUES(?,?,?,?)",
            (
                (787, "2026-06-30", "2026-08-30", "TTM_READY"),
                (1166, "2026-06-30", "2026-08-30", "TTM_READY"),
                (82, "2026-06-30", "2026-08-30", "TTM_READY"),
                (278, "2026-06-30", "2026-08-30", "TTM_READY"),
                (1304, "2026-06-30", "2026-08-30", "TTM_READY"),
            ),
        )


def test_nxh_contamination_artifact_rejects_bankrupt_ticker_rows() -> None:
    meta = {
        "NXH": {
            "permaticker": "195902",
            "secfilings": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001130713",
            "relatedtickers": "OSTK BBBY BYON",
        },
        "BBBYQ": {
            "permaticker": "197799",
            "secfilings": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000886158",
        },
    }

    clean = nxh_contamination_artifact([{"ticker": "NXH"}], meta)
    contaminated = nxh_contamination_artifact([{"ticker": "NXH"}, {"ticker": "BBBYQ"}], meta)

    assert clean["status"] == "PASS"
    assert contaminated["status"] == "FAIL"
    assert "NON_NXH_ROWS_PRESENT_IN_ACCEPTED_NXH_SET" in contaminated["contamination_conflicts"]


def test_stage_provider_rows_is_append_only_and_idempotent(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    _minimal_provider(provider)
    _minimal_canonical(canonical)
    rows = {
        "VMRK": [
            {
                "ticker": "VMRK",
                "permaticker": "197624",
                "dimension": "ARQ",
                "calendardate": "2026-06-30",
                "reportperiod": "2026-06-30",
                "fiscalperiod": "2026-Q2",
                "date": "2026-08-24",
                "lastupdated": "2026-08-28",
                "revenue": "",
                "ebit": "100",
                "fcf": "50",
                "cashneq": "10",
                "debt": "5",
                "sharesbas": "2",
            }
        ],
        "IA": [],
        "VAI": [],
        "NXH": [],
        "NMAD": [],
    }

    first = stage_provider_rows(provider, canonical, rows)
    second = stage_provider_rows(provider, canonical, rows)
    with sqlite3.connect(provider) as conn:
        normalized = conn.execute("SELECT revenue,ebit FROM sharadar_fundamental_observation").fetchone()

    assert first["logical_changes"] == 1
    assert second["logical_changes"] == 0
    assert normalized == (None, 100)


def test_structural_endpoint_policy_uses_period_end_not_availability_date(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    _minimal_structural_canonical(canonical)

    policy = structural_endpoint_policy(canonical)
    by_ticker = {row["ticker"]: row for row in policy["rows"]}

    assert by_ticker["VMRK"]["snapshot_endpoint_status"] == "STRUCTURALLY_LIMITED_NO_POST_TRANSITION_OBSERVED_ENDPOINT"
    assert by_ticker["NMAD"]["snapshot_endpoint_status"] == "STRUCTURALLY_LIMITED_NO_POST_TRANSITION_OBSERVED_ENDPOINT"
