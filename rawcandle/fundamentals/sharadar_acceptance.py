from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from rawcandle.fundamentals.providers.sharadar import (
    STATUS_FREE_TIER_LIMIT,
    STATUS_SUCCESS,
    SharadarClient,
    SharadarResult,
)


DIFFICULT_TICKERS = ("AAPL", "WDAY", "ASTH", "CECO", "BBY", "DELL", "GCO", "HAE", "MRVL", "RL", "SAIC", "TJX", "TRNS")
CONTROL_TICKERS = ("GOOGL", "META", "AMZN", "XOM", "KO")
ACCEPTANCE_TICKERS = DIFFICULT_TICKERS + CONTROL_TICKERS
SUBSCRIPTION_SCOPE = "Sharadar Fundamentals 5 Years"
FIELD_PROJECTION = (
    "ticker",
    "dimension",
    "calendardate",
    "reportperiod",
    "fiscalperiod",
    "date",
    "lastupdated",
    "revenue",
    "gp",
    "opinc",
    "ebit",
    "ebitda",
    "netinc",
    "netinccmn",
    "ncfo",
    "capex",
    "fcf",
    "cashneq",
    "debt",
    "debtc",
    "debtnc",
    "sharesbas",
    "shareswa",
    "shareswadil",
    "permaticker",
)
CRITICAL_FIELDS = ("revenue", "ebit", "ebitda", "ncfo", "capex", "fcf", "cashneq", "debt", "sharesbas")
ARQ_MRQ_COMPARE_FIELDS = ("revenue", "ebit", "ebitda", "fcf", "debt", "sharesbas")

KNOWN_TRUTH: dict[str, dict[str, str]] = {
    "AAPL": {"2025-12-27": "2026-Q1"},
    "WDAY": {
        "2026-07-31": "2027-Q2",
        "2026-04-30": "2027-Q1",
        "2026-01-31": "2026-Q4",
        "2025-10-31": "2026-Q3",
        "2025-07-31": "2026-Q2",
        "2025-04-30": "2026-Q1",
        "2025-01-31": "2025-Q4",
    },
    "ASTH": {"2026-03-31": "2026-Q1"},
    "CECO": {"2026-03-31": "2026-Q1"},
}


@dataclass(frozen=True)
class AcceptancePaths:
    artifact_root: Path


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[Mapping[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def result_summary(result: SharadarResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "auth_status": result.auth_status,
        "http_status": result.http_status,
        "records": len(result.records),
        "request_count": result.request_count,
        "endpoint": result.endpoint,
        "url": result.url,
        "error": result.error,
    }


def confirm_paid_entitlement(client: SharadarClient) -> tuple[str, SharadarResult]:
    result = client.fundamentals(ticker="WDAY", dimension="ARQ", limit=80)
    if result.status == STATUS_SUCCESS and result.records:
        return "PAID_5Y_ENTITLEMENT_CONFIRMED", result
    if result.status == STATUS_FREE_TIER_LIMIT:
        return "PAID_ENTITLEMENT_NOT_ACTIVE_OR_KEY_NOT_REFRESHED", result
    return "PAID_ENTITLEMENT_CHECK_FAILED", result


def normalize_reportperiod(value: Any) -> str:
    return str(value or "").strip()[:10]


def parse_num(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_fiscalperiod(value: Any) -> tuple[int, int] | None:
    text = str(value or "").strip().upper()
    if "-Q" not in text:
        return None
    fy_text, q_text = text.split("-Q", 1)
    try:
        fy = int(fy_text)
        q = int(q_text)
    except ValueError:
        return None
    if q not in {1, 2, 3, 4}:
        return None
    return fy, q


def is_within_day_equivalence(provider_period: str, official_period: str, tolerance_days: int = 7) -> bool:
    try:
        provider = date.fromisoformat(provider_period)
        official = date.fromisoformat(official_period)
    except ValueError:
        return False
    return abs((provider - official).days) <= tolerance_days


def validate_fiscal_identity(arq_rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for row in arq_rows:
        ticker = str(row.get("ticker") or "").upper()
        reportperiod = normalize_reportperiod(row.get("reportperiod"))
        fiscalperiod = str(row.get("fiscalperiod") or "").strip()
        expected = KNOWN_TRUTH.get(ticker, {}).get(reportperiod)
        if expected is None:
            status = "LOCAL_TRUTH_UNAVAILABLE"
        elif expected == fiscalperiod:
            status = "MATCH_OFFICIAL"
        else:
            status = "MISMATCH_OFFICIAL"
        rows.append(
            {
                "ticker": ticker,
                "reportperiod": reportperiod,
                "fiscalperiod": fiscalperiod,
                "expected_fiscalperiod": expected or "",
                "status": status,
            }
        )
    counts = Counter(row["status"] for row in rows)
    systematic_calendar_issue = any(
        row["status"] == "MISMATCH_OFFICIAL"
        and row["reportperiod"][:4]
        and row["fiscalperiod"].startswith(row["reportperiod"][:4])
        for row in rows
    )
    return rows, {
        "rows_compared_to_local_truth": counts["MATCH_OFFICIAL"] + counts["MISMATCH_OFFICIAL"],
        "match_official": counts["MATCH_OFFICIAL"],
        "mismatch_official": counts["MISMATCH_OFFICIAL"],
        "local_truth_unavailable": counts["LOCAL_TRUTH_UNAVAILABLE"],
        "transition_case": counts["TRANSITION_CASE"],
        "systematic_fiscal_convention_issue": "YES" if systematic_calendar_issue else "NO",
    }


def validate_reportperiod(arq_rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for row in arq_rows:
        ticker = str(row.get("ticker") or "").upper()
        reportperiod = normalize_reportperiod(row.get("reportperiod"))
        expected_periods = set(KNOWN_TRUTH.get(ticker, {}))
        if not expected_periods:
            status = "LOCAL_TRUTH_UNAVAILABLE"
            expected = ""
        elif reportperiod in expected_periods:
            status = "EXACT_MATCH"
            expected = reportperiod
        else:
            within = [period for period in expected_periods if is_within_day_equivalence(reportperiod, period)]
            if within:
                status = "WITHIN_7_DAY_EQUIVALENCE"
                expected = within[0]
            else:
                status = "LOCAL_TRUTH_UNAVAILABLE"
                expected = ""
        rows.append({"ticker": ticker, "reportperiod": reportperiod, "expected_reportperiod": expected, "status": status})
    counts = Counter(row["status"] for row in rows)
    return rows, {
        "exact_matches": counts["EXACT_MATCH"],
        "within_7_day_equivalence": counts["WITHIN_7_DAY_EQUIVALENCE"],
        "material_differences": counts["MATERIAL_DIFFERENCE"],
        "unresolved": counts["LOCAL_TRUTH_UNAVAILABLE"],
    }


def validate_quarter_continuity(rows_by_ticker: Mapping[str, list[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    out = []
    for ticker, rows in rows_by_ticker.items():
        parsed = [(parse_fiscalperiod(row.get("fiscalperiod")), normalize_reportperiod(row.get("reportperiod"))) for row in rows]
        parsed = [(fq, rp) for fq, rp in parsed if fq is not None]
        keys = [fq for fq, _ in parsed]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        status = "CONTINUOUS"
        issue = ""
        if duplicates:
            status = "DUPLICATE"
            issue = ";".join(f"{fy}-Q{q}" for fy, q in duplicates)
        else:
            ordered = sorted(keys)
            for prev, cur in zip(ordered, ordered[1:]):
                expected = (prev[0], prev[1] + 1) if prev[1] < 4 else (prev[0] + 1, 1)
                if cur != expected:
                    status = "GAP"
                    issue = f"{prev[0]}-Q{prev[1]}->{cur[0]}-Q{cur[1]}"
                    break
        if not parsed:
            status = "AMBIGUOUS"
            issue = "no_parseable_fiscalperiod"
        out.append({"ticker": ticker, "status": status, "issue": issue, "quarters": len(parsed)})
    return out, dict(Counter(row["status"] for row in out))


def validate_q4_coverage(rows_by_ticker: Mapping[str, list[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    for ticker, rows in rows_by_ticker.items():
        quarters_by_fy: dict[int, set[int]] = defaultdict(set)
        for row in rows:
            fiscal = parse_fiscalperiod(row.get("fiscalperiod"))
            if fiscal:
                quarters_by_fy[fiscal[0]].add(fiscal[1])
        completed = sorted((fy for fy, quarters in quarters_by_fy.items() if 4 in quarters), reverse=True)[:3]
        for fy in sorted(completed):
            quarters = quarters_by_fy[fy]
            if quarters == {1, 2, 3, 4}:
                status = "FULL_Q1_Q4_SEQUENCE"
            elif 4 not in quarters:
                status = "Q4_MISSING"
            else:
                status = "OTHER_QUARTER_MISSING"
            out.append({"ticker": ticker, "fiscal_year": fy, "quarters": ",".join(f"Q{q}" for q in sorted(quarters)), "status": status})
    counts = Counter(row["status"] for row in out)
    years = len(out)
    present = counts["FULL_Q1_Q4_SEQUENCE"]
    return out, {
        "completed_fiscal_years_evaluated": years,
        "explicit_q4_present": present,
        "q4_missing": counts["Q4_MISSING"],
        "q4_coverage_pct": round((present / years * 100.0), 2) if years else 0.0,
        "systematic_q4_weakness": "YES" if counts["Q4_MISSING"] > 0 else "NO",
    }


def coverage_pct(rows: list[Mapping[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    covered = sum(1 for row in rows if parse_num(row.get(field)) is not None)
    return round(covered / len(rows) * 100.0, 2)


def validate_field_coverage(rows_by_ticker: Mapping[str, list[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    out = []
    latest8_all = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: normalize_reportperiod(row.get("reportperiod")), reverse=True)
        latest8 = ordered[:8]
        latest4 = ordered[:4]
        latest8_all.extend(latest8)
        row: dict[str, Any] = {"ticker": ticker, "arq_rows": len(rows), "latest8_rows": len(latest8), "latest4_rows": len(latest4)}
        for field in CRITICAL_FIELDS:
            row[f"{field}_all_pct"] = coverage_pct(list(rows), field)
            row[f"{field}_latest8_pct"] = coverage_pct(latest8, field)
            row[f"{field}_latest4_pct"] = coverage_pct(latest4, field)
        out.append(row)
    summary = {field: coverage_pct(latest8_all, field) for field in CRITICAL_FIELDS}
    return out, summary


def classify_reconciliation(actual: float | None, expected: float | None) -> str:
    if actual is None or expected is None:
        return "MISSING_COMPONENT"
    diff = abs(actual - expected)
    if diff <= 1e-9:
        return "EXACT_RECONCILIATION"
    if diff <= max(1.0, abs(actual) * 1e-6):
        return "ROUNDING_DIFFERENCE"
    return "SEMANTIC_DIFFERENCE"


def validate_fcf(arq_rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    for row in arq_rows:
        ncfo = parse_num(row.get("ncfo"))
        capex = parse_num(row.get("capex"))
        fcf = parse_num(row.get("fcf"))
        expected = ncfo + capex if ncfo is not None and capex is not None else None
        status = classify_reconciliation(fcf, expected)
        rows.append(
            {
                "ticker": row.get("ticker", ""),
                "reportperiod": normalize_reportperiod(row.get("reportperiod")),
                "fiscalperiod": row.get("fiscalperiod", ""),
                "ncfo": row.get("ncfo", ""),
                "capex": row.get("capex", ""),
                "fcf": row.get("fcf", ""),
                "expected_fcf": expected if expected is not None else "",
                "status": status,
            }
        )
    counts = Counter(row["status"] for row in rows)
    return rows, {
        "comparable_rows": counts["EXACT_RECONCILIATION"] + counts["ROUNDING_DIFFERENCE"] + counts["SEMANTIC_DIFFERENCE"],
        "exact_or_rounding": counts["EXACT_RECONCILIATION"] + counts["ROUNDING_DIFFERENCE"],
        "semantic_differences": counts["SEMANTIC_DIFFERENCE"],
        "unresolved": counts["MISSING_COMPONENT"],
    }


def validate_debt(arq_rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    for row in arq_rows:
        debt = parse_num(row.get("debt"))
        debtc = parse_num(row.get("debtc"))
        debtnc = parse_num(row.get("debtnc"))
        expected = debtc + debtnc if debtc is not None and debtnc is not None else None
        status = classify_reconciliation(debt, expected)
        rows.append(
            {
                "ticker": row.get("ticker", ""),
                "reportperiod": normalize_reportperiod(row.get("reportperiod")),
                "fiscalperiod": row.get("fiscalperiod", ""),
                "debt": row.get("debt", ""),
                "debtc": row.get("debtc", ""),
                "debtnc": row.get("debtnc", ""),
                "expected_debt": expected if expected is not None else "",
                "status": status,
            }
        )
    counts = Counter(row["status"] for row in rows)
    return rows, {
        "comparable_rows": counts["EXACT_RECONCILIATION"] + counts["ROUNDING_DIFFERENCE"] + counts["SEMANTIC_DIFFERENCE"],
        "exact_or_rounding": counts["EXACT_RECONCILIATION"] + counts["ROUNDING_DIFFERENCE"],
        "other_component_cases": counts["OTHER_DEBT_COMPONENTS_PRESENT"],
        "semantic_differences": counts["SEMANTIC_DIFFERENCE"],
        "unresolved": counts["MISSING_COMPONENT"],
    }


def validate_shares(rows_by_ticker: Mapping[str, list[Mapping[str, Any]]], actions_by_ticker: Mapping[str, list[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    total_latest8 = 0
    covered_latest8 = 0
    unexplained = 0
    split_explained = 0
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: normalize_reportperiod(row.get("reportperiod")))
        jumps = []
        for prev, cur in zip(ordered, ordered[1:]):
            prev_shares = parse_num(prev.get("sharesbas"))
            cur_shares = parse_num(cur.get("sharesbas"))
            if prev_shares and cur_shares:
                ratio = cur_shares / prev_shares
                if ratio >= 3.0 or ratio <= 1 / 3.0:
                    jumps.append((normalize_reportperiod(prev.get("reportperiod")), normalize_reportperiod(cur.get("reportperiod")), ratio))
        latest8 = sorted(rows, key=lambda row: normalize_reportperiod(row.get("reportperiod")), reverse=True)[:8]
        total_latest8 += len(latest8)
        covered_latest8 += sum(1 for row in latest8 if parse_num(row.get("sharesbas")) is not None)
        actions = actions_by_ticker.get(ticker, [])
        action_text = json.dumps(actions, default=str).lower()
        if not jumps:
            status = "SHARE_HISTORY_CONSISTENT"
        elif "split" in action_text:
            status = "SPLIT_EXPLAINED"
            split_explained += len(jumps)
        else:
            status = "UNEXPLAINED_DISCONTINUITY"
            unexplained += len(jumps)
        out.append(
            {
                "ticker": ticker,
                "sharesbas_latest8_pct": coverage_pct(latest8, "sharesbas"),
                "shareswa_latest8_pct": coverage_pct(latest8, "shareswa"),
                "shareswadil_latest8_pct": coverage_pct(latest8, "shareswadil"),
                "large_share_jumps": len(jumps),
                "actions_rows": len(actions),
                "status": status,
            }
        )
    coverage = round(covered_latest8 / total_latest8 * 100.0, 2) if total_latest8 else 0.0
    if coverage >= 95.0 and unexplained == 0:
        acceptance = "SHARESBAS_ACCEPT"
    elif coverage >= 95.0:
        acceptance = "SHARESBAS_ACCEPT_WITH_GUARD"
    else:
        acceptance = "SHARESBAS_REJECT"
    return out, {
        "sharesbas_latest8_coverage": coverage,
        "unexplained_share_discontinuities": unexplained,
        "split_explained_cases": split_explained,
        "sharesbas_acceptance_status": acceptance,
    }


def validate_arq_vs_mrq(arq_by_ticker: Mapping[str, list[Mapping[str, Any]]], mrq_by_ticker: Mapping[str, list[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    for ticker, arq_rows in arq_by_ticker.items():
        mrq_index = {
            (row.get("fiscalperiod"), normalize_reportperiod(row.get("reportperiod"))): row
            for row in mrq_by_ticker.get(ticker, [])
        }
        for arq in arq_rows:
            key = (arq.get("fiscalperiod"), normalize_reportperiod(arq.get("reportperiod")))
            mrq = mrq_index.get(key)
            if not mrq:
                continue
            field_statuses = []
            for field in ARQ_MRQ_COMPARE_FIELDS:
                a_val = parse_num(arq.get(field))
                m_val = parse_num(mrq.get(field))
                if a_val is None or m_val is None:
                    continue
                if abs(a_val - m_val) <= max(1e-9, abs(a_val) * 1e-9):
                    field_statuses.append("SAME")
                elif abs(a_val - m_val) <= max(1.0, abs(a_val) * 0.02):
                    field_statuses.append("RESTATED_OR_UPDATED")
                else:
                    field_statuses.append("MATERIAL_DIFFERENCE")
            if not field_statuses or all(status == "SAME" for status in field_statuses):
                status = "SAME"
            elif "MATERIAL_DIFFERENCE" in field_statuses:
                status = "MATERIAL_DIFFERENCE"
            else:
                status = "RESTATED_OR_UPDATED"
            out.append({"ticker": ticker, "reportperiod": key[1], "fiscalperiod": key[0], "status": status})
    counts = Counter(row["status"] for row in out)
    return out, {
        "matching_periods": len(out),
        "same": counts["SAME"],
        "updated_or_restated": counts["RESTATED_OR_UPDATED"],
        "material_differences": counts["MATERIAL_DIFFERENCE"],
        "arq_point_in_time_suitability": "YES" if len(out) > 0 else "NO",
    }


def validate_identity(
    rows_by_ticker: Mapping[str, list[Mapping[str, Any]]],
    metadata_by_ticker: Mapping[str, list[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    permaticker_ok = 0
    cik_ok = 0
    ticker_change_continuity = "LOCAL_TRUTH_UNAVAILABLE"
    for ticker, rows in rows_by_ticker.items():
        row_permatickers = {str(row.get("permaticker") or "").strip() for row in rows if str(row.get("permaticker") or "").strip()}
        metadata = metadata_by_ticker.get(ticker, [])
        meta_permatickers = {str(row.get("permaticker") or "").strip() for row in metadata if str(row.get("permaticker") or "").strip()}
        ciks = {str(row.get("cik") or "").strip() for row in metadata if str(row.get("cik") or "").strip()}
        if row_permatickers or meta_permatickers:
            permaticker_ok += 1
        if ciks:
            cik_ok += 1
        status = "COMPLETE" if (row_permatickers or meta_permatickers) and ciks else "PARTIAL"
        out.append(
            {
                "ticker": ticker,
                "row_permatickers": ";".join(sorted(row_permatickers)),
                "metadata_permatickers": ";".join(sorted(meta_permatickers)),
                "ciks": ";".join(sorted(ciks)),
                "metadata_rows": len(metadata),
                "status": status,
            }
        )
        if ticker == "ASTH" and (row_permatickers or meta_permatickers) and rows:
            ticker_change_continuity = "PRESERVED_BY_PROVIDER_ROWS"
    total = len(rows_by_ticker)
    return out, {
        "permaticker_coverage": round(permaticker_ok / total * 100.0, 2) if total else 0.0,
        "cik_coverage": round(cik_ok / total * 100.0, 2) if total else 0.0,
        "ticker_change_continuity": ticker_change_continuity,
        "identity_model_concerns": "permaticker is provider-stable metadata, not RawCandle global primary key",
    }


def acceptance_result_for_ticker(
    ticker: str,
    fiscal_rows: list[Mapping[str, Any]],
    continuity_status: str,
    q4_rows: list[Mapping[str, Any]],
    field_row: Mapping[str, Any],
    shares_status: str,
) -> tuple[str, str]:
    issues = []
    if any(row["status"] == "MISMATCH_OFFICIAL" for row in fiscal_rows if row["ticker"] == ticker):
        issues.append("fiscal_identity_mismatch")
    if continuity_status in {"GAP", "DUPLICATE", "AMBIGUOUS"}:
        issues.append(f"quarter_continuity_{continuity_status.lower()}")
    if any(row["status"] == "Q4_MISSING" for row in q4_rows if row["ticker"] == ticker):
        issues.append("q4_missing")
    for field in ("revenue", "ebit", "fcf", "cashneq", "debt", "sharesbas"):
        if float(field_row.get(f"{field}_latest8_pct", 0.0)) < 90.0:
            issues.append(f"{field}_coverage_low")
    if shares_status == "UNEXPLAINED_DISCONTINUITY":
        issues.append("unexplained_share_discontinuity")
    if issues:
        return "REVIEW", ";".join(issues)
    if any(row["status"] == "LOCAL_TRUTH_UNAVAILABLE" for row in fiscal_rows if row["ticker"] == ticker):
        return "PASS_WITH_MINOR_LIMITATION", "local_truth_not_available_for_all_rows"
    return "PASS", ""


def build_scorecard(
    ticker_kinds: Mapping[str, str],
    arq_by_ticker: Mapping[str, list[Mapping[str, Any]]],
    mrq_by_ticker: Mapping[str, list[Mapping[str, Any]]],
    fiscal_rows: list[Mapping[str, Any]],
    continuity_rows: list[Mapping[str, Any]],
    q4_rows: list[Mapping[str, Any]],
    coverage_rows: list[Mapping[str, Any]],
    fcf_rows: list[Mapping[str, Any]],
    debt_rows: list[Mapping[str, Any]],
    shares_rows: list[Mapping[str, Any]],
    arq_mrq_rows: list[Mapping[str, Any]],
    identity_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    continuity_by_ticker = {row["ticker"]: row["status"] for row in continuity_rows}
    coverage_by_ticker = {row["ticker"]: row for row in coverage_rows}
    shares_by_ticker = {row["ticker"]: row for row in shares_rows}
    identity_by_ticker = {row["ticker"]: row for row in identity_rows}
    out = []
    for ticker, kind in ticker_kinds.items():
        field_row = coverage_by_ticker.get(ticker, {})
        result, issues = acceptance_result_for_ticker(
            ticker,
            fiscal_rows,
            continuity_by_ticker.get(ticker, "AMBIGUOUS"),
            q4_rows,
            field_row,
            str(shares_by_ticker.get(ticker, {}).get("status", "")),
        )
        out.append(
            {
                "ticker": ticker,
                "control_or_difficult": kind,
                "ARQ rows": len(arq_by_ticker.get(ticker, [])),
                "MRQ rows": len(mrq_by_ticker.get(ticker, [])),
                "fiscal_identity_status": _dominant_ticker_status(fiscal_rows, ticker),
                "period_end_status": "EVALUATED",
                "quarter_continuity_status": continuity_by_ticker.get(ticker, "AMBIGUOUS"),
                "Q4_status": _dominant_ticker_status(q4_rows, ticker),
                "revenue_coverage": field_row.get("revenue_latest8_pct", 0.0),
                "ebit_coverage": field_row.get("ebit_latest8_pct", 0.0),
                "ebitda_coverage": field_row.get("ebitda_latest8_pct", 0.0),
                "fcf_coverage": field_row.get("fcf_latest8_pct", 0.0),
                "cash_coverage": field_row.get("cashneq_latest8_pct", 0.0),
                "debt_coverage": field_row.get("debt_latest8_pct", 0.0),
                "sharesbas_coverage": field_row.get("sharesbas_latest8_pct", 0.0),
                "FCF_consistency_status": _dominant_ticker_status(fcf_rows, ticker),
                "debt_consistency_status": _dominant_ticker_status(debt_rows, ticker),
                "shares_status": shares_by_ticker.get(ticker, {}).get("status", ""),
                "actions_status": shares_by_ticker.get(ticker, {}).get("status", ""),
                "ARQ_MRQ_status": _dominant_ticker_status(arq_mrq_rows, ticker),
                "identity_metadata_status": identity_by_ticker.get(ticker, {}).get("status", ""),
                "material_issues": issues,
                "acceptance_result": result,
            }
        )
    return out


def _dominant_ticker_status(rows: Iterable[Mapping[str, Any]], ticker: str) -> str:
    counts = Counter(str(row.get("status") or "") for row in rows if row.get("ticker") == ticker)
    if not counts:
        return "NOT_EVALUATED"
    return counts.most_common(1)[0][0]


def final_provider_classification(summary: Mapping[str, Any], scorecard: list[Mapping[str, Any]]) -> tuple[str, str, str]:
    if summary["entitlement"]["status"] != "PAID_5Y_ENTITLEMENT_CONFIRMED":
        return "SHARADAR_NEEDS_ADDITIONAL_ACCEPTANCE", "paid entitlement not confirmed", "NO"
    hard_failures = [
        summary["fiscal_identity"]["mismatch_official"],
        summary["quarter_continuity"].get("GAP", 0),
        summary["quarter_continuity"].get("DUPLICATE", 0),
        summary["q4"]["q4_missing"],
        summary["fcf"]["semantic_differences"],
        summary["debt"]["semantic_differences"],
    ]
    fail_count = sum(1 for row in scorecard if row["acceptance_result"] == "FAIL")
    review_count = sum(1 for row in scorecard if row["acceptance_result"] == "REVIEW")
    if fail_count or any(value for value in hard_failures[:4]):
        return "SHARADAR_NEEDS_ADDITIONAL_ACCEPTANCE", "hard fiscal/sequence/Q4 issue requires targeted review", "NO"
    if review_count or summary["identity"]["cik_coverage"] < 100.0 or summary["shares"]["sharesbas_acceptance_status"] != "SHARESBAS_ACCEPT":
        return "SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER_WITH_GUARDS", "identity/actions/share guards remain for canonical design", "YES"
    return "SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER", "", "YES"


def run_paid_acceptance(paths: AcceptancePaths, *, client: SharadarClient | None = None) -> dict[str, Any]:
    paths.artifact_root.mkdir(parents=True, exist_ok=True)
    client = client or SharadarClient(max_retries=1)
    ticker_kinds = {ticker: "difficult" for ticker in DIFFICULT_TICKERS}
    ticker_kinds.update({ticker: "control" for ticker in CONTROL_TICKERS})
    write_csv(
        paths.artifact_root / "acceptance_ticker_set.csv",
        [{"ticker": ticker, "set": kind} for ticker, kind in ticker_kinds.items()],
        ["ticker", "set"],
    )

    entitlement_status, wday_result = confirm_paid_entitlement(client)
    entitlement = {
        "status": entitlement_status,
        "old_free_tier_403_gone": "YES" if entitlement_status == "PAID_5Y_ENTITLEMENT_CONFIRMED" else "NO",
        "subscription_scope": SUBSCRIPTION_SCOPE,
        "wday_request": result_summary(wday_result),
    }
    write_json(paths.artifact_root / "paid_entitlement_check.json", entitlement)
    if entitlement_status != "PAID_5Y_ENTITLEMENT_CONFIRMED":
        summary = {
            "classification": "SHARADAR_NEEDS_ADDITIONAL_ACCEPTANCE",
            "entitlement": entitlement,
            "network_requests": client.request_count,
            "artifact_root": str(paths.artifact_root),
            "next_action": "CONFIRM SHARADAR 5-YEAR FUNDAMENTALS ENTITLEMENT FOR THE EXISTING API KEY AND RERUN V4-0D",
        }
        write_json(paths.artifact_root / "sharadar_acceptance_summary.json", summary)
        (paths.artifact_root / "next_action.md").write_text(summary["next_action"] + "\n", encoding="utf-8")
        return summary

    arq_by_ticker: dict[str, list[dict[str, Any]]] = {"WDAY": wday_result.records}
    mrq_by_ticker: dict[str, list[dict[str, Any]]] = {}
    metadata_by_ticker: dict[str, list[dict[str, Any]]] = {}
    actions_by_ticker: dict[str, list[dict[str, Any]]] = {}
    request_results: list[dict[str, Any]] = [{"ticker": "WDAY", "kind": "ARQ_ENTITLEMENT", **result_summary(wday_result)}]

    for ticker in ACCEPTANCE_TICKERS:
        if ticker != "WDAY":
            arq = client.fundamentals(ticker=ticker, dimension="ARQ", limit=80)
            arq_by_ticker[ticker] = arq.records
            request_results.append({"ticker": ticker, "kind": "ARQ", **result_summary(arq)})
        mrq = client.fundamentals(ticker=ticker, dimension="MRQ", limit=80)
        mrq_by_ticker[ticker] = mrq.records
        request_results.append({"ticker": ticker, "kind": "MRQ", **result_summary(mrq)})
        metadata = client.table("tickers", ticker=ticker, limit=20)
        metadata_by_ticker[ticker] = metadata.records
        request_results.append({"ticker": ticker, "kind": "TICKERS", **result_summary(metadata)})
        actions = client.table("actions", ticker=ticker, limit=100)
        actions_by_ticker[ticker] = actions.records
        request_results.append({"ticker": ticker, "kind": "ACTIONS", **result_summary(actions)})

    all_arq = [row for rows in arq_by_ticker.values() for row in rows]
    all_mrq = [row for rows in mrq_by_ticker.values() for row in rows]
    fiscal_rows, fiscal_summary = validate_fiscal_identity(all_arq)
    reportperiod_rows, reportperiod_summary = validate_reportperiod(all_arq)
    continuity_rows, continuity_summary = validate_quarter_continuity(arq_by_ticker)
    q4_rows, q4_summary = validate_q4_coverage(arq_by_ticker)
    coverage_rows, coverage_summary = validate_field_coverage(arq_by_ticker)
    fcf_rows, fcf_summary = validate_fcf(all_arq)
    debt_rows, debt_summary = validate_debt(all_arq)
    shares_rows, shares_summary = validate_shares(arq_by_ticker, actions_by_ticker)
    arq_mrq_rows, arq_mrq_summary = validate_arq_vs_mrq(arq_by_ticker, mrq_by_ticker)
    identity_rows, identity_summary = validate_identity(arq_by_ticker, metadata_by_ticker)

    scorecard = build_scorecard(
        ticker_kinds,
        arq_by_ticker,
        mrq_by_ticker,
        fiscal_rows,
        continuity_rows,
        q4_rows,
        coverage_rows,
        fcf_rows,
        debt_rows,
        shares_rows,
        arq_mrq_rows,
        identity_rows,
    )
    scorecard_counts = Counter(row["acceptance_result"] for row in scorecard)
    summary: dict[str, Any] = {
        "entitlement": entitlement,
        "acceptance_set": {
            "difficult_tickers": list(DIFFICULT_TICKERS),
            "control_tickers": list(CONTROL_TICKERS),
            "total_tickers": len(ACCEPTANCE_TICKERS),
        },
        "known_truth_cases": known_truth_case_summary(fiscal_rows),
        "fiscal_identity": fiscal_summary,
        "reportperiod": reportperiod_summary,
        "quarter_continuity": continuity_summary,
        "q4": q4_summary,
        "field_coverage_latest8q": coverage_summary,
        "fcf": fcf_summary,
        "debt": debt_summary,
        "shares": shares_summary,
        "arq_vs_mrq": arq_mrq_summary,
        "identity": identity_summary,
        "scorecard_counts": dict(scorecard_counts),
        "safety": {
            "bulk_download_performed": "NO",
            "v4_production_db_created": "NO",
            "v3_modified": "NO",
            "swingmaster_runtime_dependency": "NO",
            "api_key_exposure": "NO",
        },
        "network_requests": client.request_count,
        "artifact_root": str(paths.artifact_root),
    }
    classification, limitations, schema_may_be_designed = final_provider_classification(summary, scorecard)
    summary["classification"] = classification
    summary["limitations"] = limitations
    summary["v4_canonical_schema_may_now_be_designed"] = schema_may_be_designed
    summary["next_action"] = (
        "PROCEED TO V4-1 PROVIDER STORE + CANONICAL SCHEMA DESIGN IN RAWCANDLE, USING SHARADAR ARQ AS THE PRIMARY QUARTERLY SOURCE AND KEEPING YAHOO/SEC AS COMPLEMENTARY PROVIDERS"
        if schema_may_be_designed == "YES"
        else "RESOLVE ONLY THE SPECIFIC PROVIDER LIMITATIONS FOUND; DO NOT BROADEN THE TEST SET WITHOUT A MATERIAL REASON"
    )

    write_csv(paths.artifact_root / "acceptance_arq_rows.csv", all_arq)
    write_csv(paths.artifact_root / "acceptance_mrq_rows.csv", all_mrq)
    write_csv(paths.artifact_root / "request_results.csv", request_results)
    write_csv(paths.artifact_root / "fiscal_identity_validation.csv", fiscal_rows)
    write_csv(paths.artifact_root / "reportperiod_validation.csv", reportperiod_rows)
    write_csv(paths.artifact_root / "quarter_continuity_validation.csv", continuity_rows)
    write_csv(paths.artifact_root / "q4_coverage_validation.csv", q4_rows)
    write_csv(paths.artifact_root / "critical_field_coverage.csv", coverage_rows)
    write_csv(paths.artifact_root / "fcf_reconciliation.csv", fcf_rows)
    write_csv(paths.artifact_root / "debt_reconciliation.csv", debt_rows)
    write_csv(paths.artifact_root / "sharesbas_validation.csv", shares_rows)
    write_csv(paths.artifact_root / "corporate_actions_validation.csv", [{"ticker": ticker, "actions_rows": len(rows)} for ticker, rows in actions_by_ticker.items()])
    write_csv(paths.artifact_root / "arq_vs_mrq_validation.csv", arq_mrq_rows)
    write_csv(paths.artifact_root / "permaticker_identity_validation.csv", identity_rows)
    write_csv(paths.artifact_root / "sharadar_acceptance_scorecard.csv", scorecard)
    write_json(paths.artifact_root / "sharadar_acceptance_summary.json", summary)
    (paths.artifact_root / "next_action.md").write_text(summary["next_action"] + "\n", encoding="utf-8")
    return summary


def known_truth_case_summary(fiscal_rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup = {(row["ticker"], row["reportperiod"]): row for row in fiscal_rows}
    cases = {
        "AAPL": ("2025-12-27", "2026-Q1"),
        "WDAY": ("2026-04-30", "2027-Q1"),
        "ASTH": ("2026-03-31", "2026-Q1"),
        "CECO": ("2026-03-31", "2026-Q1"),
    }
    return {
        ticker: {
            "reportperiod": reportperiod,
            "fiscalperiod": lookup.get((ticker, reportperiod), {}).get("fiscalperiod", ""),
            "expected": expected,
            "result": lookup.get((ticker, reportperiod), {}).get("status", "NOT_FOUND"),
        }
        for ticker, (reportperiod, expected) in cases.items()
    }
