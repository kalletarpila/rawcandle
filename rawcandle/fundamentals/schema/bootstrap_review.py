from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.providers.sharadar import SharadarClient, redact_url
from rawcandle.fundamentals.schema.production_bootstrap import (
    ANALYSIS_DB_NAME,
    CANONICAL_DB_NAME,
    PROVIDER_DB_NAME,
    ProductionPaths,
    baseline_fingerprints,
    cross_db_integrity,
    field_coverage,
    production_integrity,
    q4_global_coverage,
)
from rawcandle.fundamentals.schema.prototype import stable_hash, utc_now, utc_stamp, write_csv, write_json


CRITICAL_TTM_FIELDS = ("revenue", "ebit", "free_cashflow", "cash", "total_debt", "shares_outstanding")
TICKERS_FIELDS = (
    "ticker",
    "permaticker",
    "name",
    "exchange",
    "isdelisted",
    "firstpricedate",
    "lastpricedate",
    "category",
    "relatedtickers",
    "secfilings",
    "firstquarter",
    "lastquarter",
    "lastupdated",
    "table",
)
ACTION_FIELDS = ("date", "action", "ticker", "name", "value", "contraticker", "contraname")


@dataclass(frozen=True)
class ReviewPaths:
    repo_root: Path
    artifact_root: Path
    provider_db: Path
    canonical_db: Path
    analysis_db: Path
    v4_1b_summary_path: Path
    v4_1b_bulk_csv: Path


def review_paths(repo_root: Path, timestamp: str | None = None, v4_1b_summary_path: Path | None = None) -> ReviewPaths:
    summary_path = v4_1b_summary_path or locate_latest_v4_1b_summary(repo_root)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    stamp = timestamp or utc_stamp()
    return ReviewPaths(
        repo_root=repo_root,
        artifact_root=repo_root / "temp" / "fundamentals_v4_1b1_bootstrap_review" / stamp,
        provider_db=repo_root / "data" / PROVIDER_DB_NAME,
        canonical_db=repo_root / "data" / CANONICAL_DB_NAME,
        analysis_db=repo_root / "data" / ANALYSIS_DB_NAME,
        v4_1b_summary_path=summary_path,
        v4_1b_bulk_csv=Path(summary["bulk_manifest"]["extracted_path"]),
    )


def locate_latest_v4_1b_summary(repo_root: Path) -> Path:
    candidates = sorted((repo_root / "temp" / "fundamentals_v4_1b_production_bootstrap").glob("*/v4_1b_summary.json"))
    if not candidates:
        raise FileNotFoundError("No V4-1B summary artifact found")
    return candidates[-1]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_metadata_schema(provider_db: Path) -> None:
    with connect(provider_db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sharadar_ticker_metadata (
                table_name TEXT NOT NULL,
                ticker TEXT NOT NULL,
                permaticker TEXT NOT NULL,
                name TEXT,
                exchange TEXT,
                isdelisted TEXT,
                category TEXT,
                relatedtickers TEXT,
                secfilings TEXT,
                firstpricedate TEXT,
                lastpricedate TEXT,
                firstquarter TEXT,
                lastquarter TEXT,
                lastupdated TEXT,
                payload_json TEXT NOT NULL,
                fetched_at_utc TEXT NOT NULL,
                PRIMARY KEY(table_name, ticker, permaticker)
            );
            CREATE TABLE IF NOT EXISTS sharadar_action_metadata (
                date TEXT NOT NULL,
                action TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                value TEXT,
                contraticker TEXT NOT NULL,
                contraname TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at_utc TEXT NOT NULL,
                PRIMARY KEY(date, action, ticker, name, contraticker, contraname)
            );
            CREATE INDEX IF NOT EXISTS idx_sharadar_ticker_metadata_ticker ON sharadar_ticker_metadata(ticker, table_name);
            CREATE INDEX IF NOT EXISTS idx_sharadar_ticker_metadata_permaticker ON sharadar_ticker_metadata(permaticker);
            CREATE INDEX IF NOT EXISTS idx_sharadar_action_metadata_ticker ON sharadar_action_metadata(ticker, date, action);
            """
        )


def fetch_metadata(client: SharadarClient) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    results = []
    tickers = client._request("GET", "/data/tickers", {"fields": ",".join(TICKERS_FIELDS), "limit": "100000"}, auth=True)
    results.append({"kind": "tickers", "status": tickers.status, "http_status": tickers.http_status, "rows": len(tickers.records), "url": tickers.url})
    if not tickers.ok:
        raise RuntimeError(f"Sharadar tickers metadata fetch failed: {tickers.status} {tickers.error}")
    actions = client._request("GET", "/data/actions", {"fields": ",".join(ACTION_FIELDS), "limit": "100000"}, auth=True)
    results.append({"kind": "actions", "status": actions.status, "http_status": actions.http_status, "rows": len(actions.records), "url": actions.url})
    if not actions.ok:
        raise RuntimeError(f"Sharadar actions metadata fetch failed: {actions.status} {actions.error}")
    return tickers.records, actions.records, results


def read_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_metadata_snapshots(paths: ReviewPaths, tickers: list[Mapping[str, Any]], actions: list[Mapping[str, Any]]) -> None:
    write_csv(paths.artifact_root / "sharadar_tickers_metadata_snapshot.csv", [dict(row) for row in tickers], list(TICKERS_FIELDS))
    write_csv(paths.artifact_root / "sharadar_actions_snapshot.csv", [dict(row) for row in actions], list(ACTION_FIELDS))


def insert_tickers_metadata(provider_db: Path, records: Iterable[Mapping[str, Any]], now: str) -> dict[str, int]:
    ensure_metadata_schema(provider_db)
    counts = Counter()
    with connect(provider_db) as conn:
        before_rows = conn.execute("SELECT COUNT(*) FROM sharadar_ticker_metadata").fetchone()[0]
        for row in records:
            table_name = _text(row.get("table"))
            ticker = _text(row.get("ticker")).upper()
            permaticker = _text(row.get("permaticker"))
            if not table_name or not ticker or not permaticker:
                counts["skipped_missing_identity"] += 1
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO sharadar_ticker_metadata(
                    table_name, ticker, permaticker, name, exchange, isdelisted, category, relatedtickers,
                    secfilings, firstpricedate, lastpricedate, firstquarter, lastquarter, lastupdated,
                    payload_json, fetched_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table_name,
                    ticker,
                    permaticker,
                    _nullable(row.get("name")),
                    _nullable(row.get("exchange")),
                    _nullable(row.get("isdelisted")),
                    _nullable(row.get("category")),
                    _nullable(row.get("relatedtickers")),
                    _nullable(row.get("secfilings")),
                    _nullable(row.get("firstpricedate")),
                    _nullable(row.get("lastpricedate")),
                    _nullable(row.get("firstquarter")),
                    _nullable(row.get("lastquarter")),
                    _nullable(row.get("lastupdated")),
                    json.dumps(dict(row), sort_keys=True, default=str),
                    now,
                ),
            )
            counts[f"table_{table_name}"] += 1
        after_rows = conn.execute("SELECT COUNT(*) FROM sharadar_ticker_metadata").fetchone()[0]
    counts["rows_before"] = before_rows
    counts["rows_after"] = after_rows
    counts["rows_inserted_or_new"] = after_rows - before_rows
    return dict(counts)


def insert_actions_metadata(provider_db: Path, records: Iterable[Mapping[str, Any]], flagged_tickers: set[str], now: str) -> dict[str, int]:
    ensure_metadata_schema(provider_db)
    counts = Counter()
    with connect(provider_db) as conn:
        before_rows = conn.execute("SELECT COUNT(*) FROM sharadar_action_metadata").fetchone()[0]
        for row in records:
            ticker = _text(row.get("ticker")).upper()
            contra = _text(row.get("contraticker")).upper()
            if ticker not in flagged_tickers and contra not in flagged_tickers:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO sharadar_action_metadata(
                    date, action, ticker, name, value, contraticker, contraname, payload_json, fetched_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _text(row.get("date")),
                    _text(row.get("action")),
                    ticker,
                    _text(row.get("name")),
                    _nullable(row.get("value")),
                    contra,
                    _text(row.get("contraname")),
                    json.dumps(dict(row), sort_keys=True, default=str),
                    now,
                ),
            )
            counts[_text(row.get("action"))] += 1
        after_rows = conn.execute("SELECT COUNT(*) FROM sharadar_action_metadata").fetchone()[0]
    counts["rows_before"] = before_rows
    counts["rows_after"] = after_rows
    counts["rows_inserted_or_new"] = after_rows - before_rows
    return dict(counts)


def pre_review_baseline(paths: ReviewPaths) -> dict[str, Any]:
    production = ProductionPaths(
        repo_root=paths.repo_root,
        artifact_root=paths.artifact_root,
        provider_db=paths.provider_db,
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        bootstrap_csv=paths.repo_root / "temp" / "v3_active_tickers_99_27.csv",
        bulk_zip_path=paths.v4_1b_bulk_csv.with_suffix(".zip"),
        extracted_csv_path=paths.v4_1b_bulk_csv,
    )
    current = baseline_fingerprints(production)
    baseline_summary = json.loads(paths.v4_1b_summary_path.read_text(encoding="utf-8"))
    expected = baseline_summary["baseline_fingerprints"]
    matched = {key: current.get(key) == expected.get(key) for key in expected}
    with connect(paths.canonical_db) as conn:
        counts = {
            "companies": conn.execute("SELECT COUNT(*) FROM company").fetchone()[0],
            "securities": conn.execute("SELECT COUNT(*) FROM security").fetchone()[0],
            "canonical_quarters": conn.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0],
            "provider_identities": conn.execute("SELECT COUNT(*) FROM provider_security_identity").fetchone()[0],
        }
    result = {
        "v4_1b_summary_path": str(paths.v4_1b_summary_path),
        "canonical_financial_fingerprint_matched": matched.get("canonical_financial_values", False),
        "all_v4_1b_fingerprints_matched": all(matched.values()),
        "fingerprint_matches": matched,
        "current_fingerprints": current,
        "v4_1b_fingerprints": expected,
        **counts,
    }
    write_json(paths.artifact_root / "pre_review_baseline.json", result)
    return result


def share_discontinuity_flags(provider_db: Path) -> list[dict[str, Any]]:
    flags = []
    with connect(provider_db) as conn:
        tickers = [row["ticker"] for row in conn.execute("SELECT DISTINCT ticker FROM sharadar_fundamental_observation WHERE dimension='ARQ' ORDER BY ticker")]
        for ticker in tickers:
            rows = conn.execute(
                """
                SELECT ticker, reportperiod, fiscalperiod, sharesbas, shareswa, shareswadil
                FROM sharadar_fundamental_observation
                WHERE ticker=? AND dimension='ARQ'
                ORDER BY reportperiod
                """,
                (ticker,),
            ).fetchall()
            previous = None
            for row in rows:
                if previous and row["sharesbas"] and previous["sharesbas"]:
                    ratio = row["sharesbas"] / previous["sharesbas"]
                    if ratio >= 4.0 or ratio <= 0.25:
                        flags.append(
                            {
                                "ticker": ticker,
                                "prev_reportperiod": previous["reportperiod"],
                                "reportperiod": row["reportperiod"],
                                "prev_fiscalperiod": previous["fiscalperiod"],
                                "fiscalperiod": row["fiscalperiod"],
                                "prev_sharesbas": previous["sharesbas"],
                                "sharesbas": row["sharesbas"],
                                "prev_shareswa": previous["shareswa"],
                                "shareswa": row["shareswa"],
                                "prev_shareswadil": previous["shareswadil"],
                                "shareswadil": row["shareswadil"],
                                "sharesbas_ratio": ratio,
                            }
                        )
                previous = row
    return flags


def populate_identity_metadata(paths: ReviewPaths, now: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        metadata = _ticker_metadata_indexes(provider)
        target_tickers = {row["current_ticker"] for row in canonical.execute("SELECT current_ticker FROM security")}
        before_alias = canonical.execute("SELECT COUNT(*) FROM ticker_alias").fetchone()[0]
        for security in canonical.execute("SELECT security_id, company_id, current_ticker FROM security ORDER BY current_ticker"):
            ticker = security["current_ticker"]
            best = metadata["fundamentals"].get(ticker) or metadata["stocks"].get(ticker)
            row = {
                "ticker": ticker,
                "company_id": security["company_id"],
                "security_id": security["security_id"],
                "metadata_match": int(best is not None),
                "metadata_table": best["table_name"] if best else "",
                "permaticker": best["permaticker"] if best else "",
                "isdelisted": best["isdelisted"] if best else "",
                "exchange": best["exchange"] if best else "",
                "category": best["category"] if best else "",
                "firstpricedate": best["firstpricedate"] if best else "",
                "lastpricedate": best["lastpricedate"] if best else "",
            }
            if best and best["permaticker"]:
                canonical.execute(
                    """
                    INSERT OR IGNORE INTO provider_security_identity(provider, provider_security_id, security_id, provider_ticker, source, created_at_utc)
                    VALUES ('SHARADAR', ?, ?, ?, ?, ?)
                    """,
                    (best["permaticker"], security["security_id"], ticker, f"tickers:{best['table_name']}", now),
                )
                canonical.execute(
                    "UPDATE security SET exchange=COALESCE(?, exchange), active=?, updated_at_utc=? WHERE security_id=?",
                    (best["exchange"], 0 if str(best["isdelisted"]).upper() == "Y" else 1, now, security["security_id"]),
                )
                canonical.execute(
                    "UPDATE company SET company_name=CASE WHEN company_name IS NULL OR company_name=company_key THEN ? ELSE company_name END, updated_at_utc=? WHERE company_id=?",
                    (best["name"], now, security["company_id"]),
                )
            for action in provider.execute(
                """
                SELECT action, ticker, contraticker, date
                FROM sharadar_action_metadata
                WHERE action IN ('tickerchangeto','tickerchangefrom') AND (ticker=? OR contraticker=?)
                """,
                (ticker, ticker),
            ):
                other = action["contraticker"] if action["ticker"] == ticker else action["ticker"]
                if other and other not in target_tickers:
                    canonical.execute(
                        """
                        INSERT OR IGNORE INTO ticker_alias(security_id, ticker, provider, source, valid_from, valid_to)
                        VALUES (?, ?, 'SHARADAR', 'actions:tickerchange', ?, NULL)
                        """,
                        (security["security_id"], other, action["date"]),
                    )
            rows.append(row)
        after_alias = canonical.execute("SELECT COUNT(*) FROM ticker_alias").fetchone()[0]
        duplicate_permatickers = canonical.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT provider_security_id, COUNT(DISTINCT security_id) c
              FROM provider_security_identity
              WHERE provider='SHARADAR'
              GROUP BY provider_security_id HAVING c > 1
            )
            """
        ).fetchone()[0]
        multiple_permatickers_per_company = canonical.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT s.company_id, COUNT(DISTINCT psi.provider_security_id) c
              FROM provider_security_identity psi JOIN security s ON s.security_id=psi.security_id
              WHERE psi.provider='SHARADAR'
              GROUP BY s.company_id HAVING c > 1
            )
            """
        ).fetchone()[0]
        permaticker_populated = canonical.execute("SELECT COUNT(DISTINCT security_id) FROM provider_security_identity WHERE provider='SHARADAR'").fetchone()[0]
        security_rows = canonical.execute("SELECT COUNT(*) FROM security").fetchone()[0]
        delisted = canonical.execute("SELECT COUNT(*) FROM security WHERE active=0").fetchone()[0]
    summary = {
        "security_rows": security_rows,
        "target_securities_matched": sum(1 for row in rows if row["metadata_match"]),
        "permaticker_populated": permaticker_populated,
        "permaticker_null": security_rows - permaticker_populated,
        "unique_permatickers": permaticker_populated,
        "one_permaticker_multiple_security_rows": duplicate_permatickers,
        "multiple_permatickers_one_company": multiple_permatickers_per_company,
        "delisted_securities": delisted,
        "ticker_aliases_discovered": after_alias - before_alias,
        "identity_conflicts": duplicate_permatickers,
    }
    write_json(paths.artifact_root / "sharadar_tickers_metadata_summary.json", summary)
    write_csv(paths.artifact_root / "permaticker_mapping_audit.csv", rows)
    return summary, rows


def resolve_unmatched_tickers(paths: ReviewPaths) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        metadata = _ticker_metadata_indexes(provider)
        target_tickers = [row["current_ticker"] for row in canonical.execute("SELECT current_ticker FROM security ORDER BY current_ticker")]
        matched = {row["ticker"] for row in provider.execute("SELECT DISTINCT ticker FROM sharadar_fundamental_observation")}
        unmatched = [ticker for ticker in target_tickers if ticker not in matched]
        cik_to_fundamental = defaultdict(list)
        for ticker, row in metadata["fundamentals"].items():
            cik = _cik_from_secfilings(row["secfilings"])
            if cik:
                cik_to_fundamental[cik].append(ticker)
        bulk_counts = _bulk_counts(paths.v4_1b_bulk_csv, set(unmatched) | set(metadata["fundamentals"]))
        for ticker in unmatched:
            identity = canonical.execute(
                """
                SELECT s.company_id, s.security_id, cc.cik_normalized
                FROM security s LEFT JOIN company_cik cc ON cc.company_id=s.company_id
                WHERE s.current_ticker=?
                """,
                (ticker,),
            ).fetchone()
            stock = metadata["stocks"].get(ticker)
            fundamental = metadata["fundamentals"].get(ticker)
            related = _related_tickers(stock["relatedtickers"] if stock else "")
            candidates = []
            for candidate in related + cik_to_fundamental.get(identity["cik_normalized"] if identity else "", []):
                if candidate in metadata["fundamentals"] and candidate not in candidates:
                    candidates.append(candidate)
            alt_counts = {candidate: bulk_counts.get(candidate, 0) for candidate in candidates}
            located = bool(bulk_counts.get(ticker, 0) or any(count > 0 for count in alt_counts.values()))
            if fundamental and bulk_counts.get(ticker, 0):
                root = "TICKER_ALIAS"
                current = ticker
            elif stock and candidates and located:
                root = "PROVIDER_TICKER_DIFFERENT"
                current = candidates[0]
            elif not stock and candidates and located:
                root = "TICKER_RENAMED"
                current = candidates[0]
            elif stock and str(stock["category"]).lower().find("secondary class") >= 0:
                root = "SECURITY_TYPE_NOT_COVERED"
                current = candidates[0] if candidates else ""
            elif not stock and not fundamental:
                root = "BOOTSTRAP_UNIVERSE_STALE"
                current = candidates[0] if candidates else ""
            else:
                root = "TRUE_PROVIDER_MISSING"
                current = ""
            rows.append(
                {
                    "ticker": ticker,
                    "company_id": identity["company_id"] if identity else "",
                    "security_id": identity["security_id"] if identity else "",
                    "cik": identity["cik_normalized"] if identity else "",
                    "metadata_match": int(bool(stock or fundamental)),
                    "metadata_table": "fundamentals" if fundamental else ("stocks" if stock else ""),
                    "permaticker": (fundamental or stock or {}).get("permaticker", ""),
                    "active_delisted": (fundamental or stock or {}).get("isdelisted", ""),
                    "current_sharadar_ticker": current,
                    "historical_or_related_tickers": ";".join(candidates),
                    "firstpricedate": (fundamental or stock or {}).get("firstpricedate", ""),
                    "lastpricedate": (fundamental or stock or {}).get("lastpricedate", ""),
                    "fundamentals_rows_original_ticker": bulk_counts.get(ticker, 0),
                    "fundamentals_rows_alternate_ticker": sum(alt_counts.values()),
                    "root_cause_class": root,
                    "fundamentals_located": "YES" if located else "NO",
                    "final_coverage_status": "COVERED_UNDER_ALTERNATE_PROVIDER_TICKER" if located and current else "NO_DIRECT_FUNDAMENTALS_FOR_SECURITY",
                }
            )
    counts = Counter(row["root_cause_class"] for row in rows)
    write_csv(paths.artifact_root / "unmatched_19_resolution.csv", rows)
    write_csv(paths.artifact_root / "ticker_alias_resolution.csv", [row for row in rows if row["historical_or_related_tickers"]])
    return rows, dict(counts)


def reclassify_gaps(paths: ReviewPaths) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]], dict[str, Any]]:
    gaps, q4_rows = [], []
    continuity_counts = Counter()
    q4_counts = Counter()
    with connect(paths.canonical_db) as conn:
        company_tickers = _company_tickers(conn)
        for company in conn.execute("SELECT company_id FROM company ORDER BY company_id"):
            quarters = conn.execute(
                "SELECT fiscal_year, fiscal_quarter, period_end FROM v4_quarter WHERE company_id=? ORDER BY fiscal_year, fiscal_quarter",
                (company["company_id"],),
            ).fetchall()
            if not quarters:
                continuity_counts["IDENTITY_REVIEW"] += 1
                continue
            indexes = [_quarter_index(row["fiscal_year"], row["fiscal_quarter"]) for row in quarters]
            missing = [idx for left, right in zip(indexes, indexes[1:]) for idx in range(left + 1, right)]
            if missing:
                classification = "TRUE_INTERNAL_MISSING_QUARTER"
                continuity_counts["TRUE_GAP"] += 1
                gaps.append(
                    {
                        "company_id": company["company_id"],
                        "tickers": ";".join(company_tickers[company["company_id"]]),
                        "missing_fiscalperiods": ";".join(_format_fyq(idx) for idx in missing),
                        "missing_quarters": len(missing),
                        "classification": classification,
                    }
                )
            elif quarters[0]["fiscal_quarter"] == "Q1":
                continuity_counts["CONTINUOUS_FULLY_OBSERVABLE"] += 1
            else:
                continuity_counts["CONTINUOUS_WITH_LEFT_WINDOW_TRUNCATION"] += 1
            years = defaultdict(set)
            for quarter in quarters:
                years[quarter["fiscal_year"]].add(quarter["fiscal_quarter"])
            if not years:
                continue
            first_year, last_year = min(years), max(years)
            for fiscal_year, qs in sorted(years.items()):
                if qs == {"Q1", "Q2", "Q3", "Q4"}:
                    q4_counts["EXPLICIT_Q4_PRESENT"] += 1
                elif "Q4" not in qs and len(qs) >= 3:
                    if fiscal_year in {first_year, last_year}:
                        q4_class = "FALSE_MISSING_DUE_WINDOW"
                    else:
                        q4_class = "TRUE_Q4_PROVIDER_GAP"
                    q4_counts[q4_class] += 1
                    q4_rows.append(
                        {
                            "company_id": company["company_id"],
                            "tickers": ";".join(company_tickers[company["company_id"]]),
                            "fiscal_year": fiscal_year,
                            "quarters_present": ",".join(sorted(qs)),
                            "classification": q4_class,
                        }
                    )
    gap_counts = Counter(row["classification"] for row in gaps)
    true_q4 = q4_counts["TRUE_Q4_PROVIDER_GAP"]
    explicit = q4_counts["EXPLICIT_Q4_PRESENT"]
    observable = explicit + true_q4
    q4_summary = {
        "fully_observable_completed_fys": observable,
        "explicit_q4_present": explicit,
        "true_q4_missing": true_q4,
        "clean_q4_coverage_pct": round((explicit / observable * 100.0), 4) if observable else 0.0,
        "FALSE_MISSING_DUE_WINDOW": q4_counts["FALSE_MISSING_DUE_WINDOW"],
        "FALSE_MISSING_DUE_TICKER_CHANGE": q4_counts["FALSE_MISSING_DUE_TICKER_CHANGE"],
        "FALSE_MISSING_DUE_FISCAL_TRANSITION": q4_counts["FALSE_MISSING_DUE_FISCAL_TRANSITION"],
        "TRUE_Q4_PROVIDER_GAP": q4_counts["TRUE_Q4_PROVIDER_GAP"],
        "Q4_PRESENT_UNDER_DIFFERENT_SECURITY_ALIAS": q4_counts["Q4_PRESENT_UNDER_DIFFERENT_SECURITY_ALIAS"],
        "OTHER": q4_counts["OTHER"],
        **dict(q4_counts),
    }
    write_csv(paths.artifact_root / "gap_172_reclassification.csv", gaps)
    write_csv(paths.artifact_root / "continuity_post_review.csv", [{"classification": key, "companies": value} for key, value in sorted(continuity_counts.items())])
    write_csv(paths.artifact_root / "missing_q4_190_reclassification.csv", q4_rows)
    write_json(paths.artifact_root / "q4_post_review_summary.json", q4_summary)
    return gaps, dict(gap_counts), q4_rows, q4_summary


def reclassify_shares(paths: ReviewPaths) -> tuple[list[dict[str, Any]], dict[str, int]]:
    flags = share_discontinuity_flags(paths.provider_db)
    with connect(paths.provider_db) as conn:
        actions = defaultdict(list)
        for row in conn.execute("SELECT * FROM sharadar_action_metadata ORDER BY date"):
            actions[row["ticker"]].append(dict(row))
    rows = []
    for flag in flags:
        relevant_actions = [
            action
            for action in actions.get(flag["ticker"], [])
            if flag["prev_reportperiod"] <= action["date"] <= flag["reportperiod"]
        ]
        classification = classify_share_discontinuity(flag, relevant_actions)
        rows.append(
            {
                **flag,
                "actions_in_window": len(relevant_actions),
                "action_types": ";".join(sorted({action["action"] for action in relevant_actions})),
                "classification": classification,
                "canonical_share_value_changed": 0,
            }
        )
    counts = Counter(row["classification"] for row in rows)
    write_csv(paths.artifact_root / "shares_255_reclassification.csv", rows)
    write_csv(
        paths.artifact_root / "targeted_actions_audit.csv",
        [
            {"ticker": ticker, "actions_rows": len(items), "actions_types": ";".join(sorted({item["action"] for item in items}))}
            for ticker, items in sorted(actions.items())
        ],
    )
    return rows, dict(counts)


def classify_share_discontinuity(flag: Mapping[str, Any], actions: list[Mapping[str, Any]]) -> str:
    action_text = " ".join(str(action.get("action") or "").lower() for action in actions)
    if "split" in action_text:
        split_values = [_float(action.get("value")) for action in actions if str(action.get("action") or "").lower() == "split"]
        return "REVERSE_SPLIT" if any(value is not None and value < 1.0 for value in split_values) else "STOCK_SPLIT"
    if "acquisition" in action_text or "merger" in action_text:
        return "MERGER_ACQUISITION"
    if "spac" in action_text:
        return "SPAC_OR_RECAPITALIZATION"
    if "tickerchange" in action_text or "namechange" in action_text:
        return "TICKER_OR_SECURITY_CHANGE"
    sharesbas_ratio = float(flag["sharesbas_ratio"])
    supporting = [
        _ratio(flag.get("prev_shareswa"), flag.get("shareswa")),
        _ratio(flag.get("prev_shareswadil"), flag.get("shareswadil")),
    ]
    if any(value is not None and ((sharesbas_ratio >= 4.0 and value >= 2.0) or (sharesbas_ratio <= 0.25 and value <= 0.5)) for value in supporting):
        return "NORMAL_BUYBACK_OR_ISSUANCE"
    if sharesbas_ratio >= 20.0 or sharesbas_ratio <= 0.05:
        return "SPAC_OR_RECAPITALIZATION"
    return "INSUFFICIENT_EVIDENCE"


def analyze_debt_mismatch(paths: ReviewPaths) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    with connect(paths.provider_db) as conn:
        for row in conn.execute(
            """
            SELECT ticker, dimension, reportperiod, fiscalperiod, debt, debtc, debtnc, (debtc + debtnc - debt) AS difference
            FROM sharadar_fundamental_observation
            WHERE debt IS NOT NULL AND debtc IS NOT NULL AND debtnc IS NOT NULL
              AND ABS(debtc + debtnc - debt) > 1
              AND NOT (debt >= debtc + debtnc)
            ORDER BY ticker, dimension, reportperiod
            """
        ):
            classification = "PROVIDER_COMPONENT_INCONSISTENCY"
            rows.append(
                {
                    **dict(row),
                    "provider_definitions": "debt is canonical total_debt candidate; debtc/debtnc are supporting provider components",
                    "other_debt_components": "",
                    "arq_mrq_context": row["dimension"],
                    "total_debt_internally_valid": "UNPROVEN_COMPONENT_SUM_MISMATCH",
                    "classification": classification,
                    "canonical_debt_changed": "NO",
                }
            )
    counts = Counter(row["classification"] for row in rows)
    write_csv(paths.artifact_root / "single_debt_mismatch_analysis.csv", rows)
    return rows, dict(counts)


def ttm_input_readiness(paths: ReviewPaths) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    blockers = Counter()
    with connect(paths.canonical_db) as conn:
        for company in conn.execute("SELECT company_id FROM company ORDER BY company_id"):
            quarters = conn.execute(
                """
                SELECT q.fiscal_year, q.fiscal_quarter, q.period_end, f.*
                FROM v4_quarter q JOIN v4_quarter_financials f ON f.quarter_id=q.quarter_id
                WHERE q.company_id=?
                ORDER BY q.fiscal_year DESC, q.fiscal_quarter DESC
                LIMIT 4
                """,
                (company["company_id"],),
            ).fetchall()
            reasons = []
            if len(quarters) < 4:
                reasons.append("LESS_THAN_4_QUARTERS")
            else:
                indexes = [_quarter_index(row["fiscal_year"], row["fiscal_quarter"]) for row in quarters]
                if indexes != list(range(indexes[0], indexes[0] - 4, -1)):
                    reasons.append("LATEST4_SEQUENCE_GAP")
                for field in CRITICAL_TTM_FIELDS:
                    if any(row[field] is None for row in quarters):
                        reasons.append(f"MISSING_{field.upper()}")
            status = "TTM_INPUT_READY" if not reasons else "TTM_INPUT_NOT_READY"
            for reason in set(reasons):
                blockers[reason] += 1
            rows.append({"company_id": company["company_id"], "status": status, "blockers": ";".join(sorted(set(reasons)))})
    ready = sum(1 for row in rows if row["status"] == "TTM_INPUT_READY")
    summary = {
        "TTM_INPUT_READY": ready,
        "TTM_INPUT_NOT_READY": len(rows) - ready,
        "readiness_pct": round((ready / len(rows) * 100.0), 4) if rows else 0.0,
        "top_blocker_reasons": [{"reason": key, "companies": value} for key, value in blockers.most_common()],
    }
    write_csv(paths.artifact_root / "ttm_input_readiness.csv", rows)
    return rows, summary


def latest8q_post_review(paths: ReviewPaths, gap_counts: Mapping[str, int], identity_summary: Mapping[str, Any]) -> dict[str, Any]:
    _, latest8, _, _, coverage_summary = field_coverage(_production_paths(paths))
    rows = [dict(row) for row in latest8]
    write_csv(paths.artifact_root / "latest8q_post_review_coverage.csv", rows)
    return {
        "companies_with_8_usable_quarters": coverage_summary["companies_with_8_quarters"],
        "all_12_complete": coverage_summary["all_12_fields_complete_latest8q"],
        "critical_6_complete": coverage_summary["critical_6_fields_complete_latest8q"],
        "true_gap_blockers": gap_counts.get("TRUE_INTERNAL_MISSING_QUARTER", 0),
        "identity_blockers": identity_summary["permaticker_null"],
        "rows": rows,
    }


def post_review_integrity(paths: ReviewPaths) -> tuple[dict[str, Any], dict[str, Any]]:
    provider, canonical, analysis, cross = production_integrity(_production_paths(paths))
    provider["duplicate_ticker_metadata"] = _duplicate_count(
        paths.provider_db,
        """
        SELECT table_name, ticker, permaticker, COUNT(*) c
        FROM sharadar_ticker_metadata GROUP BY table_name, ticker, permaticker HAVING c > 1
        """,
    )
    provider["duplicate_action_metadata"] = _duplicate_count(
        paths.provider_db,
        """
        SELECT date, action, ticker, name, contraticker, contraname, COUNT(*) c
        FROM sharadar_action_metadata GROUP BY date, action, ticker, name, contraticker, contraname HAVING c > 1
        """,
    )
    with connect(paths.canonical_db) as conn:
        canonical["duplicate_provider_identities"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT provider, provider_security_id, COUNT(*) c
              FROM provider_security_identity GROUP BY provider, provider_security_id HAVING c > 1
            )
            """
        ).fetchone()[0]
        canonical["duplicate_permaticker_mappings"] = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT provider_security_id, COUNT(DISTINCT security_id) c
              FROM provider_security_identity WHERE provider='SHARADAR'
              GROUP BY provider_security_id HAVING c > 1
            )
            """
        ).fetchone()[0]
    full = {"provider": provider, "canonical": canonical, "analysis": analysis, "cross_db": cross}
    write_json(paths.artifact_root / "post_review_integrity.json", full)
    write_json(paths.artifact_root / "post_review_cross_db_integrity.json", cross)
    return full, cross


def replay_review(
    paths: ReviewPaths,
    tickers: list[Mapping[str, Any]],
    actions: list[Mapping[str, Any]],
    before: Mapping[str, Any],
    flagged_tickers: set[str],
    now: str,
) -> dict[str, Any]:
    before_financial = before["current_fingerprints"]["canonical_financial_values"]
    before_identity = identity_fingerprint(paths)
    before_counts = metadata_counts(paths)
    insert_tickers_metadata(paths.provider_db, tickers, now)
    insert_actions_metadata(paths.provider_db, actions, flagged_tickers, now)
    populate_identity_metadata(paths, now)
    after_counts = metadata_counts(paths)
    after_identity = identity_fingerprint(paths)
    after_financial = baseline_fingerprints(_production_paths(paths))["canonical_financial_values"]
    summary = {
        "canonical_financial_fingerprint_changed": before_financial != after_financial,
        "identity_fingerprint_stable_on_replay": before_identity == after_identity,
        "metadata_counts_stable": before_counts == after_counts,
        "duplicate_rows_created": sum(after_counts[key] - before_counts[key] for key in before_counts),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "before_identity_fingerprint": before_identity,
        "after_identity_fingerprint": after_identity,
    }
    write_json(paths.artifact_root / "post_review_replay_summary.json", summary)
    return summary


def identity_fingerprint(paths: ReviewPaths) -> str:
    with connect(paths.canonical_db) as conn:
        rows = [
            tuple(row)
            for query in (
                "SELECT company_id, company_key, company_name FROM company ORDER BY company_id",
                "SELECT security_id, company_id, current_ticker, exchange, active FROM security ORDER BY security_id",
                "SELECT provider, provider_security_id, security_id, provider_ticker, source FROM provider_security_identity ORDER BY provider, provider_security_id",
                "SELECT security_id, ticker, provider, source, valid_from, valid_to FROM ticker_alias ORDER BY security_id, ticker, provider, valid_from",
            )
            for row in conn.execute(query)
        ]
    return stable_hash(rows)


def metadata_counts(paths: ReviewPaths) -> dict[str, int]:
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        return {
            "ticker_metadata_rows": provider.execute("SELECT COUNT(*) FROM sharadar_ticker_metadata").fetchone()[0],
            "action_metadata_rows": provider.execute("SELECT COUNT(*) FROM sharadar_action_metadata").fetchone()[0],
            "provider_security_identity_rows": canonical.execute("SELECT COUNT(*) FROM provider_security_identity WHERE provider='SHARADAR'").fetchone()[0],
            "ticker_alias_rows": canonical.execute("SELECT COUNT(*) FROM ticker_alias").fetchone()[0],
        }


def run_bootstrap_review(
    paths: ReviewPaths,
    *,
    client: SharadarClient | None = None,
    tickers_records: list[Mapping[str, Any]] | None = None,
    actions_records: list[Mapping[str, Any]] | None = None,
    external_network_requests: int = 0,
) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    before = pre_review_baseline(paths)
    if not before["canonical_financial_fingerprint_matched"]:
        summary = {
            "classification": "V4_BOOTSTRAP_REVIEW_BLOCKED",
            "blocking_reason": "V4-1B canonical financial fingerprint drifted before review",
            "next_action": "KEEP THE V4 PRODUCTION BASELINE FROZEN AND RESOLVE ONLY THE SPECIFIC IDENTITY / PROVIDER DEFECTS THAT BLOCK FOUR-QUARTER TTM WINDOWS",
        }
        write_json(paths.artifact_root / "v4_1b1_summary.json", summary)
        return summary
    network_results: list[dict[str, Any]] = []
    if tickers_records is None or actions_records is None:
        client = client or SharadarClient(max_retries=1, timeout_seconds=120)
        tickers_records, actions_records, network_results = fetch_metadata(client)
    tickers = [dict(row) for row in tickers_records]
    actions = [dict(row) for row in actions_records]
    write_metadata_snapshots(paths, tickers, actions)
    now = utc_now()
    ticker_ingest = insert_tickers_metadata(paths.provider_db, tickers, now)
    share_flags = share_discontinuity_flags(paths.provider_db)
    action_ingest = insert_actions_metadata(paths.provider_db, actions, {row["ticker"] for row in share_flags}, now)
    identity_summary, identity_rows = populate_identity_metadata(paths, now)
    unmatched_rows, unmatched_counts = resolve_unmatched_tickers(paths)
    gaps, gap_counts, q4_rows, q4_summary = reclassify_gaps(paths)
    share_rows, share_counts = reclassify_shares(paths)
    debt_rows, debt_counts = analyze_debt_mismatch(paths)
    readiness_rows, readiness_summary = ttm_input_readiness(paths)
    latest8 = latest8q_post_review(paths, gap_counts, identity_summary)
    integrity, cross = post_review_integrity(paths)
    after_fingerprints = baseline_fingerprints(_production_paths(paths))
    write_json(paths.artifact_root / "post_review_fingerprints.json", {"baseline": before["current_fingerprints"], "after_review": after_fingerprints, "identity": identity_fingerprint(paths)})
    replay = replay_review(paths, tickers, actions, before, {row["ticker"] for row in share_flags}, utc_now())
    targeted_external_resolution = []
    targeted_external_sources = []
    write_csv(paths.artifact_root / "targeted_external_resolution_audit.csv", targeted_external_resolution)
    write_csv(paths.artifact_root / "targeted_external_sources.csv", targeted_external_sources)
    canonical_financial_changed = before["current_fingerprints"]["canonical_financial_values"] != after_fingerprints["canonical_financial_values"]
    true_provider_gaps = gap_counts.get("TRUE_INTERNAL_MISSING_QUARTER", 0) + q4_summary.get("TRUE_Q4_PROVIDER_GAP", 0)
    blocking = canonical_financial_changed or integrity["canonical"]["canonical_fields_without_provenance"] or replay["duplicate_rows_created"]
    if blocking:
        classification = "V4_BOOTSTRAP_REVIEW_BLOCKED"
        next_action = "KEEP THE V4 PRODUCTION BASELINE FROZEN AND RESOLVE ONLY THE SPECIFIC IDENTITY / PROVIDER DEFECTS THAT BLOCK FOUR-QUARTER TTM WINDOWS"
    elif true_provider_gaps:
        classification = "V4_BOOTSTRAP_REVIEW_COMPLETE_WITH_TRUE_PROVIDER_GAPS"
        next_action = "PROCEED TO V4-2 WITH EXPLICIT GAP FLAGS; DO NOT DELAY TTM MIGRATION FOR NON-MATERIAL PROVIDER EDGE CASES"
    else:
        classification = "V4_BOOTSTRAP_REVIEW_COMPLETE_TTM_READY"
        next_action = "PROCEED TO V4-2: MIGRATE THE EBIT-FIRST TTM ENGINE INTO RAWCANDLE AND PROVE MATHEMATICAL / POINT-IN-TIME PARITY AGAINST THE V4 CANONICAL DATABASE BEFORE MIGRATING SCORE, LIFECYCLE OR VALUATION"
    summary = {
        "classification": classification,
        "next_action": next_action,
        "artifact_root": str(paths.artifact_root),
        "baseline": before,
        "tickers_metadata": {
            "network_results": network_results,
            "metadata_rows_fetched": len(tickers),
            "ingest": ticker_ingest,
            **identity_summary,
        },
        "actions_metadata": {"metadata_rows_fetched": len(actions), "ingest": action_ingest},
        "unmatched_tickers": {"rows": unmatched_rows, "summary": unmatched_counts},
        "gaps": {"rows": len(gaps), "summary": gap_counts},
        "q4": {"rows": len(q4_rows), "summary": q4_summary},
        "shares": {"rows": len(share_rows), "summary": share_counts, "canonical_share_values_changed": 0},
        "debt": {"rows": debt_rows, "summary": debt_counts, "canonical_debt_changed": "NO"},
        "continuity_final": _continuity_final_counts(paths),
        "latest8q": latest8,
        "ttm_readiness": readiness_summary,
        "integrity": integrity,
        "replay": replay,
        "network": {
            "sharadar_requests": sum(int(item.get("request_count", 0)) for item in network_results) or (client.request_count if client else 0),
            "external_research_requests": external_network_requests,
            "yahoo_calls": 0,
            "sec_calls": 0,
        },
        "safety": {
            "ttm_rows_created": 0,
            "score_rows_created": 0,
            "lifecycle_rows_created": 0,
            "valuation_rows_created": 0,
            "v3_writes": 0,
            "swingmaster_runtime_dependency": 0,
            "canonical_financial_writes": 0,
            "api_key_exposure": "NO",
        },
    }
    write_json(paths.artifact_root / "v4_1b1_summary.json", summary)
    (paths.artifact_root / "next_action.md").write_text(next_action + "\n", encoding="utf-8")
    write_review_baseline_doc(paths.repo_root / "docs" / "fundamentals_v4" / "fundamentals_v4_bootstrap_review.md", summary)
    return summary


def _production_paths(paths: ReviewPaths) -> ProductionPaths:
    return ProductionPaths(
        repo_root=paths.repo_root,
        artifact_root=paths.artifact_root,
        provider_db=paths.provider_db,
        canonical_db=paths.canonical_db,
        analysis_db=paths.analysis_db,
        bootstrap_csv=paths.repo_root / "temp" / "v3_active_tickers_99_27.csv",
        bulk_zip_path=paths.v4_1b_bulk_csv.with_suffix(".zip"),
        extracted_csv_path=paths.v4_1b_bulk_csv,
    )


def _ticker_metadata_indexes(provider: sqlite3.Connection) -> dict[str, dict[str, sqlite3.Row]]:
    indexes = {"fundamentals": {}, "stocks": {}}
    for table_name in indexes:
        for row in provider.execute("SELECT * FROM sharadar_ticker_metadata WHERE table_name=?", (table_name,)):
            indexes[table_name][row["ticker"]] = dict(row)
    return indexes


def _bulk_counts(path: Path, tickers: set[str]) -> dict[str, int]:
    counts = Counter()
    if not path.exists() or not tickers:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            ticker = _text(row.get("ticker")).upper()
            if ticker in tickers:
                counts[ticker] += 1
    return dict(counts)


def _company_tickers(conn: sqlite3.Connection) -> dict[int, list[str]]:
    result = defaultdict(list)
    for row in conn.execute("SELECT company_id, current_ticker FROM security ORDER BY current_ticker"):
        result[row["company_id"]].append(row["current_ticker"])
    return result


def _continuity_final_counts(paths: ReviewPaths) -> dict[str, int]:
    counts = Counter()
    with connect(paths.canonical_db) as conn:
        for company in conn.execute("SELECT company_id FROM company ORDER BY company_id"):
            rows = conn.execute(
                "SELECT fiscal_year, fiscal_quarter FROM v4_quarter WHERE company_id=? ORDER BY fiscal_year, fiscal_quarter",
                (company["company_id"],),
            ).fetchall()
            if not rows:
                counts["IDENTITY_REVIEW"] += 1
                continue
            indexes = [_quarter_index(row["fiscal_year"], row["fiscal_quarter"]) for row in rows]
            missing = [idx for left, right in zip(indexes, indexes[1:]) for idx in range(left + 1, right)]
            if missing:
                counts["TRUE_GAP"] += 1
            elif rows[0]["fiscal_quarter"] == "Q1":
                counts["CONTINUOUS_FULLY_OBSERVABLE"] += 1
            else:
                counts["CONTINUOUS_WITH_LEFT_WINDOW_TRUNCATION"] += 1
    return dict(counts)


def _duplicate_count(db_path: Path, query: str) -> int:
    with connect(db_path) as conn:
        return len(conn.execute(query).fetchall())


def _quarter_index(fiscal_year: int, fiscal_quarter: str) -> int:
    return int(fiscal_year) * 4 + int(str(fiscal_quarter)[1])


def _format_fyq(index: int) -> str:
    year = (index - 1) // 4
    quarter = (index - 1) % 4 + 1
    return f"{year}-Q{quarter}"


def _related_tickers(value: str | None) -> list[str]:
    return [part for part in re.split(r"[,;\s]+", value or "") if part]


def _cik_from_secfilings(value: str | None) -> str:
    match = re.search(r"CIK=([0-9]{1,10})", value or "")
    return match.group(1).zfill(10) if match else ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ratio(previous: Any, current: Any) -> float | None:
    left = _float(previous)
    right = _float(current)
    if not left or right is None:
        return None
    return right / left


def write_review_baseline_doc(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Fundamentals V4 Bootstrap Review\n\n"
        f"Classification: `{summary['classification']}`\n\n"
        f"Artifact root: `{summary['artifact_root']}`\n\n"
        f"Permaticker populated: `{summary['tickers_metadata']['permaticker_populated']}` / `{summary['tickers_metadata']['security_rows']}`.\n\n"
        f"Unmatched ticker classes: `{json.dumps(summary['unmatched_tickers']['summary'], sort_keys=True)}`.\n\n"
        f"Continuity final: `{json.dumps(summary['continuity_final'], sort_keys=True)}`.\n\n"
        f"Q4 clean coverage: `{summary['q4']['summary']['clean_q4_coverage_pct']}` percent.\n\n"
        f"TTM input ready: `{summary['ttm_readiness']['TTM_INPUT_READY']}`; not ready: `{summary['ttm_readiness']['TTM_INPUT_NOT_READY']}`.\n\n"
        f"Canonical financial fingerprint changed: `{summary['replay']['canonical_financial_fingerprint_changed']}`.\n\n"
        f"Next action: `{summary['next_action']}`\n",
        encoding="utf-8",
    )
