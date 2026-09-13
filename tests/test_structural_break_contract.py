from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rawcandle.fundamentals import structural_break


def _schema(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY, company_key TEXT, company_name TEXT);
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                current_ticker TEXT NOT NULL,
                active INTEGER NOT NULL
            );
            CREATE TABLE provider_security_identity(
                provider TEXT NOT NULL,
                provider_security_id TEXT NOT NULL,
                security_id INTEGER NOT NULL,
                provider_ticker TEXT,
                source TEXT,
                created_at_utc TEXT
            );
            CREATE TABLE v4_quarter(
                quarter_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                fiscal_year INTEGER NOT NULL,
                fiscal_quarter TEXT NOT NULL,
                period_end TEXT NOT NULL,
                source_fiscalperiod TEXT NOT NULL,
                source_reportperiod TEXT NOT NULL,
                identity_provider TEXT NOT NULL,
                identity_status TEXT NOT NULL,
                source_availability_date TEXT,
                first_public_result_date TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                UNIQUE(company_id,fiscal_year,fiscal_quarter)
            );
            CREATE TABLE v4_ttm_values(
                ttm_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                security_id INTEGER,
                endpoint_quarter_id INTEGER NOT NULL,
                endpoint_fiscal_year INTEGER NOT NULL,
                endpoint_fiscal_quarter TEXT NOT NULL,
                period_end TEXT NOT NULL,
                model_version TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                readiness_status TEXT NOT NULL,
                blocker_codes_json TEXT NOT NULL,
                blocker_details_json TEXT NOT NULL,
                ttm_source_available_date TEXT,
                input_quarter_ids_json TEXT NOT NULL,
                output_fingerprint TEXT NOT NULL
            );
            """
        )
        conn.executemany(
            "INSERT INTO company VALUES(?,?,?)",
            [(1, "VMRK", "Vivakor"), (2, "IA", "Innovative Solutions")],
        )
        conn.executemany(
            "INSERT INTO security VALUES(?,?,?,?)",
            [(11, 1, "VMRK", 1), (22, 2, "IA", 1)],
        )
        conn.executemany(
            "INSERT INTO provider_security_identity VALUES(?,?,?,?,?,?)",
            [
                ("SHARADAR", "197624", 11, "VMRK", "test", "2026-09-13T00:00:00Z"),
                ("SHARADAR", "198182", 22, "IA", "test", "2026-09-13T00:00:00Z"),
            ],
        )
        quarters = [
            (101, 1, 2025, "Q3", "2025-09-30", "2025-Q3", "2025-09-30", "SHARADAR", "OK", "2025-11-01"),
            (102, 1, 2025, "Q4", "2025-12-31", "2025-Q4", "2025-12-31", "SHARADAR", "OK", "2026-02-01"),
            (103, 1, 2026, "Q1", "2026-03-31", "2026-Q1", "2026-03-31", "SHARADAR", "OK", "2026-05-01"),
            (104, 1, 2026, "Q2", "2026-06-30", "2026-Q2", "2026-06-30", "SHARADAR", "OK", "2026-08-01"),
            (105, 1, 2026, "Q3", "2026-09-30", "2026-Q3", "2026-09-30", "SHARADAR", "OK", "2026-11-01"),
            (201, 2, 2025, "Q3", "2025-09-30", "2025-Q3", "2025-09-30", "SHARADAR", "OK", "2025-11-01"),
            (202, 2, 2025, "Q4", "2025-12-31", "2025-Q4", "2025-12-31", "SHARADAR", "OK", "2026-02-01"),
            (203, 2, 2026, "Q1", "2026-03-31", "2026-Q1", "2026-03-31", "SHARADAR", "OK", "2026-05-01"),
            (204, 2, 2026, "Q2", "2026-06-30", "2026-Q2", "2026-06-30", "SHARADAR", "OK", "2026-08-01"),
        ]
        conn.executemany(
            "INSERT INTO v4_quarter VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(qid, cid, year, q, end, sfp, srp, provider, status, avail, None, "now", "now") for qid, cid, year, q, end, sfp, srp, provider, status, avail in quarters],
        )
        conn.executemany(
            "INSERT INTO v4_ttm_values VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1001, 1, 11, 104, 2026, "Q2", "2026-06-30", "V4_TTM_EBIT_FIRST_V1", "calc", "TTM_READY", "[]", "{}", "2026-08-01", json.dumps([101, 102, 103, 104]), "fp1"),
                (1002, 1, 11, 105, 2026, "Q3", "2026-09-30", "V4_TTM_EBIT_FIRST_V1", "calc", "TTM_READY", "[]", "{}", "2026-11-01", json.dumps([102, 103, 104, 105]), "fp2"),
                (2001, 2, 22, 204, 2026, "Q2", "2026-06-30", "V4_TTM_EBIT_FIRST_V1", "calc", "TTM_READY", "[]", "{}", "2026-08-01", json.dumps([201, 202, 203, 204]), "fp3"),
            ],
        )


def test_material_break_preserves_pre_event_history_but_blocks_post_event_current(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _schema(db)
    events = [
        {
            "successor_ticker": "VMRK",
            "predecessor_ticker": "EQR",
            "event_type": "MAJOR_BUSINESS_COMBINATION",
            "event_date": "2026-08-17",
            "effective_date": "2026-08-18",
            "comparability_status": "MAJOR_BUSINESS_COMBINATION",
            "review_status": "ACCEPTED",
            "provider": "SHARADAR",
            "provider_security_id": "197624",
            "reason": "merger close",
            "evidence": {"source": "test"},
        },
        {
            "successor_ticker": "IA",
            "predecessor_ticker": "ISSC",
            "event_type": "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE",
            "event_date": "2026-08-18",
            "effective_date": "2026-08-18",
            "comparability_status": "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE",
            "review_status": "ACCEPTED",
            "provider": "SHARADAR",
            "provider_security_id": "198182",
            "reason": "ticker-only change",
            "evidence": {"source": "test"},
        },
    ]
    report = structural_break.apply_contract(db, events=events, applied_at_utc="2026-09-13T00:00:00Z")
    assert report["event_count"] == 2
    assert report["ttm_regime_counts"]["PRE_EVENT_COHERENT"] == 1
    assert report["ttm_regime_counts"]["SINGLE_CONTINUOUS_REGIME"] == 1

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        eligible_before, _ = structural_break.latest_ttm_eligibility(conn, as_of_date="2026-08-01")
        eligible_after, metadata = structural_break.latest_ttm_eligibility(conn, as_of_date="2026-09-12")
        history = structural_break.allowed_history_quarter_ids(conn, company_id=1, current_quarter_id=104)

    assert eligible_before[1].eligible is True
    assert eligible_after[1].eligible is False
    assert eligible_after[1].reason_code == "CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM"
    assert eligible_after[2].eligible is True
    assert history == {104}
    assert metadata["fingerprint"]


def test_period_after_material_event_without_period_start_is_unresolved(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _schema(db)
    structural_break.apply_contract(
        db,
        events=[
            {
                "successor_ticker": "VMRK",
                "event_type": "MAJOR_BUSINESS_COMBINATION",
                "event_date": "2026-08-17",
                "comparability_status": "MAJOR_BUSINESS_COMBINATION",
                "review_status": "ACCEPTED",
                "provider": "SHARADAR",
                "provider_security_id": "197624",
                "reason": "merger close",
                "evidence": {},
            }
        ],
        applied_at_utc="2026-09-13T00:00:00Z",
    )
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            f"SELECT economic_regime,regime_reason FROM {structural_break.QUARTER_TABLE} WHERE quarter_id=105"
        ).fetchone()
        ttm = conn.execute(
            f"SELECT ttm_regime_status,regime_reason FROM {structural_break.TTM_TABLE} WHERE ttm_id=1002"
        ).fetchone()

    assert tuple(row) == ("UNRESOLVED", "UNRESOLVED_FISCAL_BOUNDARY")
    assert tuple(ttm) == ("STRUCTURAL_NOT_READY", "UNRESOLVED_FISCAL_BOUNDARY")


def test_availability_after_event_does_not_reclassify_pre_event_period(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _schema(db)
    structural_break.apply_contract(
        db,
        events=[
            {
                "successor_ticker": "VMRK",
                "event_type": "MAJOR_BUSINESS_COMBINATION",
                "event_date": "2026-07-15",
                "comparability_status": "MAJOR_BUSINESS_COMBINATION",
                "review_status": "ACCEPTED",
                "provider": "SHARADAR",
                "provider_security_id": "197624",
                "reason": "event after Q2 period end but before Q2 filing availability",
                "evidence": {},
            }
        ],
        applied_at_utc="2026-09-13T00:00:00Z",
    )
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        q2 = conn.execute(
            f"SELECT economic_regime,regime_reason FROM {structural_break.QUARTER_TABLE} WHERE quarter_id=104"
        ).fetchone()
        ttm = conn.execute(
            f"SELECT ttm_regime_status,regime_reason FROM {structural_break.TTM_TABLE} WHERE ttm_id=1001"
        ).fetchone()
        eligibility, _ = structural_break.latest_ttm_eligibility(conn, as_of_date="2026-09-12")

    assert tuple(q2) == ("PRE_EVENT", "PERIOD_END_BEFORE_EVENT")
    assert tuple(ttm) == ("PRE_EVENT_COHERENT", "FOUR_PRE_EVENT_INPUT_QUARTERS")
    assert eligibility[1].eligible is False
    assert eligibility[1].reason_code == "CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM"


def test_boundary_events_fail_closed_without_period_start(tmp_path: Path) -> None:
    for event_date in ("2026-06-29", "2026-06-30"):
        db = tmp_path / f"canonical-{event_date}.db"
        _schema(db)
        structural_break.apply_contract(
            db,
            events=[
                {
                    "successor_ticker": "VMRK",
                    "event_type": "MAJOR_BUSINESS_COMBINATION",
                    "event_date": event_date,
                    "comparability_status": "MAJOR_BUSINESS_COMBINATION",
                    "review_status": "ACCEPTED",
                    "provider": "SHARADAR",
                    "provider_security_id": "197624",
                    "reason": "boundary event",
                    "evidence": {},
                }
            ],
            applied_at_utc="2026-09-13T00:00:00Z",
        )
        with sqlite3.connect(db) as conn:
            q2 = conn.execute(
                f"SELECT economic_regime,regime_reason FROM {structural_break.QUARTER_TABLE} WHERE quarter_id=104"
            ).fetchone()
            ttm = conn.execute(
                f"SELECT ttm_regime_status,regime_reason FROM {structural_break.TTM_TABLE} WHERE ttm_id=1001"
            ).fetchone()
        assert tuple(q2) == ("UNRESOLVED", "UNRESOLVED_FISCAL_BOUNDARY")
        assert tuple(ttm) == ("STRUCTURAL_NOT_READY", "UNRESOLVED_FISCAL_BOUNDARY")


def test_missing_event_date_and_no_event_companies_fail_safely(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _schema(db)
    structural_break.apply_contract(
        db,
        events=[
            {
                "successor_ticker": "VMRK",
                "event_type": "UNRESOLVED_EVENT_DATE",
                "event_date": None,
                "comparability_status": "UNRESOLVED_EVENT_DATE",
                "review_status": "REVIEW_REQUIRED",
                "provider": "SHARADAR",
                "provider_security_id": "197624",
                "reason": "missing event date",
                "evidence": {},
            }
        ],
        applied_at_utc="2026-09-13T00:00:00Z",
    )
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        eligibility, metadata = structural_break.latest_ttm_eligibility(conn, as_of_date="2026-09-12")

    assert eligibility[1].eligible is False
    assert eligibility[1].reason_code == "UNRESOLVED_EVENT_DATE"
    assert 2 not in eligibility
    assert metadata["eligibility_reason_counts"] == {"UNRESOLVED_EVENT_DATE": 1}


def test_no_fixed_90_day_clean_quarter_inference(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _schema(db)
    structural_break.apply_contract(
        db,
        events=[
            {
                "successor_ticker": "VMRK",
                "event_type": "MAJOR_BUSINESS_COMBINATION",
                "event_date": "2026-07-01",
                "comparability_status": "MAJOR_BUSINESS_COMBINATION",
                "review_status": "ACCEPTED",
                "provider": "SHARADAR",
                "provider_security_id": "197624",
                "reason": "no fixed-day inference",
                "evidence": {},
            }
        ],
        applied_at_utc="2026-09-13T00:00:00Z",
    )
    with sqlite3.connect(db) as conn:
        q3 = conn.execute(
            f"SELECT economic_regime,regime_reason FROM {structural_break.QUARTER_TABLE} WHERE quarter_id=105"
        ).fetchone()
        ttm = conn.execute(
            f"SELECT ttm_regime_status,regime_reason FROM {structural_break.TTM_TABLE} WHERE ttm_id=1002"
        ).fetchone()

    assert tuple(q3) == ("UNRESOLVED", "UNRESOLVED_FISCAL_BOUNDARY")
    assert tuple(ttm) == ("STRUCTURAL_NOT_READY", "UNRESOLVED_FISCAL_BOUNDARY")
