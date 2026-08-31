from __future__ import annotations

import csv
import json
from pathlib import Path

from rawcandle.fundamentals.schema.bootstrap_review import (
    ReviewPaths,
    analyze_debt_mismatch,
    classify_share_discontinuity,
    ensure_metadata_schema,
    identity_fingerprint,
    insert_actions_metadata,
    insert_tickers_metadata,
    metadata_counts,
    populate_identity_metadata,
    reclassify_gaps,
    reclassify_shares,
    replay_review,
    resolve_unmatched_tickers,
    run_bootstrap_review,
    share_discontinuity_flags,
    ttm_input_readiness,
)
from rawcandle.fundamentals.schema.migrations import bootstrap_all
from rawcandle.fundamentals.schema.production_bootstrap import baseline_fingerprints
from rawcandle.fundamentals.schema.prototype import stable_id


def _paths(tmp_path: Path) -> ReviewPaths:
    artifact = tmp_path / "artifact"
    summary = artifact / "v4_1b_summary.json"
    bulk = artifact / "bulk.csv"
    return ReviewPaths(
        repo_root=tmp_path,
        artifact_root=artifact / "review",
        provider_db=tmp_path / "data" / "fundamentals_provider.db",
        canonical_db=tmp_path / "data" / "fundamentals_v4.db",
        analysis_db=tmp_path / "data" / "fundamentals_analysis.db",
        v4_1b_summary_path=summary,
        v4_1b_bulk_csv=bulk,
    )


def _seed(paths: ReviewPaths) -> None:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    ensure_metadata_schema(paths.provider_db)
    import sqlite3

    c = sqlite3.connect(paths.canonical_db)
    c.executescript(
        """
        INSERT INTO company(company_id, company_key, company_name, status, created_at_utc, updated_at_utc)
        VALUES (1,'AAA','AAA','ACTIVE','now','now'),(2,'BBB','BBB','ACTIVE','now','now'),(3,'CCC','CCC','ACTIVE','now','now');
        INSERT INTO security(security_id, company_id, current_ticker, active, created_at_utc, updated_at_utc)
        VALUES (10,1,'AAA',1,'now','now'),(20,2,'BBB',1,'now','now'),(30,3,'CCC',1,'now','now');
        INSERT INTO company_cik(company_id,cik_normalized,cik_display,source,status,created_at_utc)
        VALUES (3,'0000000003','0000000003','test','ACCEPTED','now');
        """
    )
    c.commit()
    c.close()
    p = sqlite3.connect(paths.provider_db)
    p.execute(
        "INSERT INTO provider_run(run_id,provider,started_at_utc,completed_at_utc,status,request_scope,metadata_json) VALUES ('run','SHARADAR','now','now','SUCCESS','test','{}')"
    )
    for ticker, company_id, security_id, fyqs in [
        ("AAA", 1, 10, [("2025", "Q1"), ("2025", "Q2"), ("2025", "Q3"), ("2025", "Q4")]),
        ("BBB", 2, 20, [("2025", "Q1"), ("2025", "Q3"), ("2025", "Q4"), ("2026", "Q1")]),
    ]:
        for year, quarter in fyqs:
            reportperiod = f"{year}-{int(quarter[1]) * 3:02d}-30"
            observation_id = stable_id(ticker, year, quarter)
            p.execute(
                """
                INSERT INTO provider_observation(
                    observation_id, run_id, provider, provider_record_key, company_id, security_id,
                    provider_ticker, native_table, dimension, reportperiod, fiscalperiod,
                    fetched_at_utc, content_hash, provider_status, payload_json
                ) VALUES (?, 'run', 'SHARADAR', ?, ?, ?, ?, 'fundamentals', 'ARQ', ?, ?, 'now', ?, 'SUCCESS', '{}')
                """,
                (observation_id, observation_id, company_id, security_id, ticker, reportperiod, f"{year}-{quarter}", observation_id),
            )
            p.execute(
                """
                INSERT INTO sharadar_fundamental_observation(
                    observation_id,ticker,dimension,reportperiod,fiscalperiod,revenue,ebit,fcf,cashneq,debt,debtc,debtnc,sharesbas,shareswa,shareswadil
                ) VALUES (?,?,'ARQ',?,?,10,7,3,2,3,1,2,100,100,100)
                """,
                (observation_id, ticker, reportperiod, f"{year}-{quarter}"),
            )
            qid = int(year) * 10 + int(quarter[1]) + company_id * 100000
            c = sqlite3.connect(paths.canonical_db)
            c.execute(
                """
                INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,identity_provider,identity_status,created_at_utc,updated_at_utc)
                VALUES (?,?,?,?,?,?,?,'SHARADAR_ARQ','ACCEPTED','now','now')
                """,
                (qid, company_id, int(year), quarter, reportperiod, f"{year}-{quarter}", reportperiod),
            )
            c.execute(
                """
                INSERT INTO v4_quarter_financials(quarter_id,revenue,ebit,free_cashflow,cash,total_debt,shares_outstanding,canonical_source_policy,created_at_utc,updated_at_utc)
                VALUES (?,10,7,3,2,3,100,'SHARADAR_ARQ_PRIMARY','now','now')
                """,
                (qid,),
            )
            for field, native in [
                ("revenue", "revenue"),
                ("ebit", "ebit"),
                ("free_cashflow", "fcf"),
                ("cash", "cashneq"),
                ("total_debt", "debt"),
                ("shares_outstanding", "sharesbas"),
            ]:
                c.execute(
                    """
                    INSERT INTO v4_field_provenance(
                        quarter_id, canonical_field, provider, provider_observation_id, source_native_field,
                        transformation, accepted_at_utc, rule_version, confidence
                    ) VALUES (?, ?, 'SHARADAR', ?, ?, 'DIRECT', 'now', 'test', 'HIGH')
                    """,
                    (qid, field, observation_id, native),
                )
            c.commit()
            c.close()
    p.execute(
        """
        INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,provider_ticker,native_table,dimension,reportperiod,fiscalperiod,fetched_at_utc,content_hash,provider_status,payload_json)
        VALUES ('debt','run','SHARADAR','debt','CORZ','fundamentals','MRQ','2024-12-31','2024-Q4','now','debt','SUCCESS','{}')
        """
    )
    p.execute(
        """
        INSERT INTO sharadar_fundamental_observation(observation_id,ticker,dimension,reportperiod,fiscalperiod,debt,debtc,debtnc)
        VALUES ('debt','CORZ','MRQ','2024-12-31','2024-Q4',1073990000,27933000,1073990000)
        """
    )
    p.commit()
    p.close()
    _write_bulk(paths.v4_1b_bulk_csv)
    from rawcandle.fundamentals.schema.production_bootstrap import ProductionPaths

    prod = ProductionPaths(paths.repo_root, paths.artifact_root, paths.provider_db, paths.canonical_db, paths.analysis_db, paths.repo_root / "bootstrap.csv", paths.v4_1b_bulk_csv.with_suffix(".zip"), paths.v4_1b_bulk_csv)
    paths.v4_1b_summary_path.parent.mkdir(parents=True, exist_ok=True)
    paths.v4_1b_summary_path.write_text(json.dumps({"bulk_manifest": {"extracted_path": str(paths.v4_1b_bulk_csv)}, "baseline_fingerprints": baseline_fingerprints(prod)}), encoding="utf-8")


def _write_bulk(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"ticker": "AAA", "dimension": "ARQ"},
        {"ticker": "BBB", "dimension": "ARQ"},
        {"ticker": "DDD", "dimension": "ARQ"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "dimension"])
        writer.writeheader()
        writer.writerows(rows)


def _tickers() -> list[dict[str, str]]:
    return [
        {"table": "fundamentals", "ticker": "AAA", "permaticker": "1001", "name": "AAA Inc", "exchange": "NYSE", "isdelisted": "N", "category": "Domestic Common Stock", "relatedtickers": "", "secfilings": "", "firstpricedate": "2020-01-01", "lastpricedate": "2026-01-01", "firstquarter": "2020-03-31", "lastquarter": "2026-06-30", "lastupdated": "2026-08-31"},
        {"table": "fundamentals", "ticker": "BBB", "permaticker": "1002", "name": "BBB Inc", "exchange": "NYSE", "isdelisted": "N", "category": "Domestic Common Stock", "relatedtickers": "", "secfilings": "", "firstpricedate": "2020-01-01", "lastpricedate": "2026-01-01", "firstquarter": "2020-03-31", "lastquarter": "2026-06-30", "lastupdated": "2026-08-31"},
        {"table": "stocks", "ticker": "CCC", "permaticker": "1003", "name": "CCC Secondary", "exchange": "NASDAQ", "isdelisted": "N", "category": "Domestic Common Stock Secondary Class", "relatedtickers": "DDD", "secfilings": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000000003", "firstpricedate": "2021-01-01", "lastpricedate": "2026-01-01", "firstquarter": "", "lastquarter": "", "lastupdated": "2026-08-31"},
        {"table": "fundamentals", "ticker": "DDD", "permaticker": "1004", "name": "CCC Primary", "exchange": "NASDAQ", "isdelisted": "N", "category": "Domestic Common Stock", "relatedtickers": "CCC", "secfilings": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000000003", "firstpricedate": "2021-01-01", "lastpricedate": "2026-01-01", "firstquarter": "2021-03-31", "lastquarter": "2026-06-30", "lastupdated": "2026-08-31"},
    ]


def _actions() -> list[dict[str, str]]:
    return [
        {"date": "2025-02-01", "action": "split", "ticker": "AAA", "name": "AAA Inc", "value": "0.1", "contraticker": "", "contraname": ""},
        {"date": "2025-02-01", "action": "tickerchangefrom", "ticker": "OLD", "name": "Old", "value": "", "contraticker": "AAA", "contraname": "AAA Inc"},
    ]


def test_tickers_metadata_ingest_idempotent_and_permaticker_population(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    insert_tickers_metadata(paths.provider_db, _tickers(), "now")
    first = metadata_counts(paths)
    insert_tickers_metadata(paths.provider_db, _tickers(), "later")
    assert metadata_counts(paths) == first
    summary, _ = populate_identity_metadata(paths, "now")
    assert summary["permaticker_populated"] == 3
    assert summary["unique_permatickers"] == 3
    assert summary["identity_conflicts"] == 0
    assert identity_fingerprint(paths)


def test_ticker_alias_mapping_delisted_handling_and_unmatched_stays_in_universe(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    insert_tickers_metadata(paths.provider_db, _tickers(), "now")
    insert_actions_metadata(paths.provider_db, _actions(), {"AAA"}, "now")
    populate_identity_metadata(paths, "now")
    rows, counts = resolve_unmatched_tickers(paths)
    ccc = [row for row in rows if row["ticker"] == "CCC"][0]
    assert ccc["root_cause_class"] == "PROVIDER_TICKER_DIFFERENT"
    assert ccc["current_sharadar_ticker"] == "DDD"
    assert ccc["fundamentals_located"] == "YES"
    assert counts["PROVIDER_TICKER_DIFFERENT"] == 1


def test_window_gap_true_gap_and_false_q4_window_no_reconstruction(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    gaps, gap_counts, q4_rows, q4_summary = reclassify_gaps(paths)
    assert gap_counts["TRUE_INTERNAL_MISSING_QUARTER"] == 1
    assert not any(row["classification"] == "ENTITLEMENT_WINDOW_BOUNDARY" for row in gaps)
    assert q4_summary["FALSE_MISSING_DUE_WINDOW"] >= 0
    assert all("derived" not in json.dumps(row).lower() for row in q4_rows)


def test_share_classifications_and_no_canonical_write(tmp_path: Path) -> None:
    assert classify_share_discontinuity({"sharesbas_ratio": 10, "prev_shareswa": 1, "shareswa": 10}, []) == "NORMAL_BUYBACK_OR_ISSUANCE"
    assert classify_share_discontinuity({"sharesbas_ratio": 10}, [{"action": "split", "value": "0.1"}]) == "REVERSE_SPLIT"
    assert classify_share_discontinuity({"sharesbas_ratio": 2}, []) == "INSUFFICIENT_EVIDENCE"
    paths = _paths(tmp_path)
    _seed(paths)
    before = identity_fingerprint(paths)
    assert share_discontinuity_flags(paths.provider_db) == []
    reclassify_shares(paths)
    assert identity_fingerprint(paths) == before


def test_single_debt_mismatch_classified_and_canonical_debt_unchanged(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    rows, counts = analyze_debt_mismatch(paths)
    assert rows[0]["ticker"] == "CORZ"
    assert rows[0]["classification"] == "PROVIDER_COMPONENT_INCONSISTENCY"
    assert rows[0]["canonical_debt_changed"] == "NO"
    assert counts["PROVIDER_COMPONENT_INCONSISTENCY"] == 1


def test_ttm_readiness_no_ttm_execution(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    _, summary = ttm_input_readiness(paths)
    assert summary["TTM_INPUT_READY"] >= 1
    assert summary["TTM_INPUT_NOT_READY"] >= 1


def test_metadata_replay_idempotent_and_financial_fingerprint_stable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    before = json.loads(paths.v4_1b_summary_path.read_text())["baseline_fingerprints"]
    baseline = {"current_fingerprints": before}
    insert_tickers_metadata(paths.provider_db, _tickers(), "now")
    insert_actions_metadata(paths.provider_db, _actions(), {"AAA"}, "now")
    populate_identity_metadata(paths, "now")
    replay = replay_review(paths, _tickers(), _actions(), baseline, {"AAA"}, "later")
    assert replay["canonical_financial_fingerprint_changed"] is False
    assert replay["identity_fingerprint_stable_on_replay"] is True
    assert replay["metadata_counts_stable"] is True
    assert replay["duplicate_rows_created"] == 0


def test_full_review_run_with_injected_metadata_no_yahoo_sec_or_model_outputs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed(paths)
    summary = run_bootstrap_review(paths, tickers_records=_tickers(), actions_records=_actions())
    assert summary["network"]["yahoo_calls"] == 0
    assert summary["network"]["sec_calls"] == 0
    assert summary["safety"]["ttm_rows_created"] == 0
    assert summary["safety"]["score_rows_created"] == 0
    assert summary["safety"]["canonical_financial_writes"] == 0
    assert summary["replay"]["duplicate_rows_created"] == 0
    assert summary["classification"] in {
        "V4_BOOTSTRAP_REVIEW_COMPLETE_TTM_READY",
        "V4_BOOTSTRAP_REVIEW_COMPLETE_WITH_TRUE_PROVIDER_GAPS",
    }
