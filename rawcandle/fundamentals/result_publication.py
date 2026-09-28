from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen

from rawcandle.fundamentals.admin.contracts import utc_now
from rawcandle.fundamentals.schema.result_publication import (
    RESULT_PUBLICATION_RULE_VERSION,
    ensure_result_publication_schema,
)


SEC_USER_AGENT = "RawCandle result-publication research admin@rawcandle.local"
SOURCE_RANK = {
    "ISSUER_EARNINGS_RELEASE": 4,
    "SEC_8K_ITEM_2_02": 3,
    "SEC_FILING_FALLBACK": 2,
    "MANUAL_REVIEW": 1,
}
QUARTER_WORDS = {"Q1": "first", "Q2": "second", "Q3": "third", "Q4": "fourth"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def filing_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def normalize_utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("RESULT_PUBLICATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_item_2_02(form: str, items: str, text: str) -> bool:
    return form.upper() == "8-K" and "2.02" in {part.strip() for part in items.split(",")} and bool(
        re.search(r"item\s+2\.02\.?\s+results\s+of\s+operations", text, flags=re.I)
    )


def match_quarter_context(text: str, quarter: Mapping[str, Any]) -> str | None:
    compact = " ".join(text.split())
    period_end = datetime.strptime(str(quarter["period_end"]), "%Y-%m-%d")
    date_tokens = {
        period_end.strftime("%B %d, %Y"),
        period_end.strftime("%B %d %Y"),
        f"{period_end.strftime('%B')} {period_end.day}, {period_end.year}",
    }
    if any(token.lower() in compact.lower() for token in date_tokens):
        return "CIK_ITEM_2_02_EXACT_PERIOD_END"
    word = QUARTER_WORDS[str(quarter["fiscal_quarter"])]
    year = int(quarter["fiscal_year"])
    patterns = (
        rf"\b{word}\s+(?:fiscal\s+)?quarter(?:\s+(?:of\s+)?(?:fiscal\s+year\s+)?)?{year}\b",
        rf"\bq{str(quarter['fiscal_quarter'])[1]}\s+(?:fy\s*)?{year}\b",
    )
    if any(re.search(pattern, compact, flags=re.I) for pattern in patterns):
        return "CIK_ITEM_2_02_EXPLICIT_FISCAL_QUARTER"
    return None


def pit_result_side(fetched_at_utc: str, authority: Mapping[str, Any]) -> str | None:
    if authority.get("status") != "VERIFIED" or not authority.get("result_publication_timestamp_utc"):
        return None
    fetched = normalize_utc_timestamp(fetched_at_utc)
    boundary = normalize_utc_timestamp(str(authority["result_publication_timestamp_utc"]))
    return "PRE_RESULT" if fetched < boundary else "POST_RESULT"


@dataclass(frozen=True)
class SecFiling:
    accession_number: str
    form: str
    items: str
    acceptance_timestamp_utc: str
    primary_document: str
    source_reference: str
    text: str


class SecClient:
    def __init__(
        self,
        *,
        fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
        fetch_text: Callable[[str], str] | None = None,
        minimum_interval_seconds: float = 0.12,
    ) -> None:
        self._fetch_json = fetch_json or self._get_json
        self._fetch_text = fetch_text or self._get_text
        self._minimum_interval_seconds = minimum_interval_seconds
        self._last_request = 0.0

    def _request(self, url: str) -> bytes:
        delay = self._minimum_interval_seconds - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        try:
            request = Request(url, headers={"Accept": "application/json,text/html", "User-Agent": SEC_USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read()
        finally:
            self._last_request = time.monotonic()

    def _get_json(self, url: str) -> Mapping[str, Any]:
        return json.loads(self._request(url))

    def _get_text(self, url: str) -> str:
        return self._request(url).decode("utf-8", errors="replace")

    def item_2_02_filings(self, cik: str, *, from_calendar_year: int = 2024) -> list[SecFiling]:
        normalized = cik.zfill(10)
        payload = self._fetch_json(f"https://data.sec.gov/submissions/CIK{normalized}.json")
        batches = [payload["filings"]["recent"]]
        for archived in payload["filings"].get("files", []):
            if str(archived.get("filingTo", "")) >= f"{from_calendar_year}-01-01":
                batches.append(self._fetch_json(f"https://data.sec.gov/submissions/{archived['name']}"))
        results: list[SecFiling] = []
        for recent in batches:
            for index, form in enumerate(recent.get("form", [])):
                items = str(recent.get("items", [""] * len(recent["form"]))[index] or "")
                if str(form).upper() != "8-K" or "2.02" not in {part.strip() for part in items.split(",")}:
                    continue
                accession = str(recent["accessionNumber"][index])
                document = str(recent["primaryDocument"][index])
                archive_cik = str(int(normalized))
                accession_path = accession.replace("-", "")
                reference = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession_path}/{document}"
                text = filing_text(self._fetch_text(reference))
                if not is_item_2_02(str(form), items, text):
                    continue
                results.append(SecFiling(
                    accession_number=accession,
                    form=str(form),
                    items=items,
                    acceptance_timestamp_utc=normalize_utc_timestamp(str(recent["acceptanceDateTime"][index])),
                    primary_document=document,
                    source_reference=reference,
                    text=text,
                ))
        return results


def _evidence_payload(quarter: Mapping[str, Any], filing: SecFiling, method: str) -> dict[str, Any]:
    stable = {
        "company_id": int(quarter["company_id"]),
        "fiscal_year": int(quarter["fiscal_year"]),
        "fiscal_quarter": str(quarter["fiscal_quarter"]),
        "source_type": "SEC_8K_ITEM_2_02",
        "source_timestamp_utc": filing.acceptance_timestamp_utc,
        "accession_number": filing.accession_number,
        "document_id": filing.primary_document,
        "filing_form": filing.form,
        "item_2_02_status": "PRESENT_AND_DOCUMENT_CONFIRMED",
        "source_reference": filing.source_reference,
        "matching_method": method,
        "rule_version": RESULT_PUBLICATION_RULE_VERSION,
        "reviewed_manual": 0,
    }
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        **stable,
        "quarter_id": int(quarter["quarter_id"]),
        "evidence_hash": digest,
        "evidence_id": f"rpe_{digest[:24]}",
    }


def resolve_sec_filings(
    quarters: Sequence[Mapping[str, Any]], filings: Sequence[SecFiling]
) -> tuple[dict[tuple[int, int, str], list[dict[str, Any]]], set[tuple[int, int, str]]]:
    matches: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    unresolved: set[tuple[int, int, str]] = set()
    for filing in filings:
        accepted = datetime.fromisoformat(filing.acceptance_timestamp_utc.replace("Z", "+00:00")).date()
        plausible = []
        for quarter in quarters:
            period_end = datetime.strptime(str(quarter["period_end"]), "%Y-%m-%d").date()
            if period_end <= accepted and (accepted - period_end).days <= 180:
                plausible.append(quarter)
        filing_matches = [(quarter, match_quarter_context(filing.text, quarter)) for quarter in plausible]
        filing_matches = [(quarter, method) for quarter, method in filing_matches if method]
        if len(filing_matches) == 1:
            quarter, method = filing_matches[0]
            key = (int(quarter["company_id"]), int(quarter["fiscal_year"]), str(quarter["fiscal_quarter"]))
            matches[key].append(_evidence_payload(quarter, filing, str(method)))
        elif len(filing_matches) > 1:
            for quarter, _ in filing_matches:
                unresolved.add((int(quarter["company_id"]), int(quarter["fiscal_year"]), str(quarter["fiscal_quarter"])))
        else:
            unresolved.update(
                (int(q["company_id"]), int(q["fiscal_year"]), str(q["fiscal_quarter"])) for q in plausible
            )
    return matches, unresolved


def _insert_evidence(connection: sqlite3.Connection, evidence: Mapping[str, Any], disposition: str, now: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO v4_result_publication_evidence(
            evidence_id,quarter_id,company_id,fiscal_year,fiscal_quarter,source_type,
            source_timestamp_utc,source_timestamp_original,source_timezone,observed_at_utc,fetched_at_utc,
            provider_symbol,security_id,accession_number,document_id,filing_form,item_2_02_status,
            source_reference,matching_method,rule_version,reviewed_manual,evidence_hash,disposition,created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            evidence["evidence_id"], evidence["quarter_id"], evidence["company_id"], evidence["fiscal_year"],
            evidence["fiscal_quarter"], evidence["source_type"], evidence["source_timestamp_utc"],
            evidence.get("source_timestamp_original"), evidence.get("source_timezone"), evidence.get("observed_at_utc"),
            evidence.get("fetched_at_utc"), evidence.get("provider_symbol"), evidence.get("security_id"),
            evidence.get("accession_number"), evidence.get("document_id"), evidence.get("filing_form"),
            evidence.get("item_2_02_status"), evidence["source_reference"], evidence["matching_method"],
            evidence["rule_version"], evidence.get("reviewed_manual", 0), evidence["evidence_hash"], disposition, now,
        ),
    )


def yahoo_evidence_payload(
    quarter: Mapping[str, Any],
    *,
    provider_symbol: str,
    event_timestamp: str,
    source_timezone: str | None,
    fetched_at_utc: str,
    security_id: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_utc_timestamp(event_timestamp)
    stable = {
        "company_id": int(quarter["company_id"]),
        "fiscal_year": int(quarter["fiscal_year"]),
        "fiscal_quarter": str(quarter["fiscal_quarter"]),
        "source_type": "YAHOO_EARNINGS_CALENDAR",
        "source_timestamp_utc": normalized,
        "source_timestamp_original": event_timestamp,
        "source_timezone": source_timezone,
        "observed_at_utc": fetched_at_utc,
        "fetched_at_utc": fetched_at_utc,
        "provider_symbol": provider_symbol,
        "security_id": security_id,
        "source_reference": "yfinance.Ticker.get_earnings_dates",
        "matching_method": "SECONDARY_CALENDAR_CORROBORATION",
        "rule_version": RESULT_PUBLICATION_RULE_VERSION,
        "reviewed_manual": 0,
    }
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        **stable,
        "quarter_id": int(quarter["quarter_id"]),
        "evidence_hash": digest,
        "evidence_id": f"rpe_{digest[:24]}",
    }


def store_secondary_evidence(
    connection: sqlite3.Connection, evidence: Mapping[str, Any], *, now: str | None = None
) -> None:
    if evidence.get("source_type") != "YAHOO_EARNINGS_CALENDAR":
        raise ValueError("SECONDARY_EVIDENCE_SOURCE_NOT_ALLOWED")
    _insert_evidence(connection, evidence, "REJECTED", now or utc_now())


def apply_resolution(
    connection: sqlite3.Connection,
    quarter: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    *,
    unresolved: bool = False,
    now: str | None = None,
) -> str:
    now = now or utc_now()
    key = (int(quarter["company_id"]), int(quarter["fiscal_year"]), str(quarter["fiscal_quarter"]))
    existing = connection.execute(
        "SELECT * FROM v4_result_publication_authority WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?", key
    ).fetchone()
    for row in evidence:
        if str(row["source_type"]) not in SOURCE_RANK:
            _insert_evidence(connection, row, "REJECTED", now)
    candidates = sorted(
        (row for row in evidence if str(row["source_type"]) in SOURCE_RANK),
        key=lambda row: (-SOURCE_RANK[str(row["source_type"])], str(row["source_timestamp_utc"])),
    )
    status = "UNRESOLVED" if unresolved else "NOT_FOUND"
    reason = "ITEM_2_02_CONTEXT_DID_NOT_RESOLVE_UNIQUELY" if unresolved else "NO_AUTHORITATIVE_EVIDENCE_FOUND"
    selected: Mapping[str, Any] | None = None
    if candidates:
        top_rank = SOURCE_RANK[str(candidates[0]["source_type"])]
        top = [row for row in candidates if SOURCE_RANK[str(row["source_type"])] == top_rank]
        timestamps = {str(row["source_timestamp_utc"]) for row in top}
        if len(timestamps) == 1:
            selected = top[0]
            status, reason = "VERIFIED", "AUTHORITATIVE_EVIDENCE_RESOLVED"
        else:
            status, reason = "AMBIGUOUS", "SAME_PRIORITY_AUTHORITATIVE_EVIDENCE_CONFLICT"
    if existing is not None and existing["status"] == "VERIFIED" and selected is not None:
        old_rank = SOURCE_RANK[str(existing["result_publication_source"])]
        new_rank = SOURCE_RANK[str(selected["source_type"])]
        if old_rank > new_rank:
            selected = None
            status, reason = "VERIFIED", "EXISTING_HIGHER_PRIORITY_AUTHORITY_PRESERVED"
        elif old_rank == new_rank and existing["result_publication_timestamp_utc"] != selected["source_timestamp_utc"]:
            selected = None
            status, reason = "AMBIGUOUS", "EXISTING_SAME_PRIORITY_EVIDENCE_CONFLICT"
    elif existing is not None and existing["status"] == "VERIFIED" and not candidates:
        return "VERIFIED"
    for row in candidates:
        disposition = "ACCEPTED" if selected is not None and row["evidence_id"] == selected["evidence_id"] else (
            "CONFLICT" if status == "AMBIGUOUS" else "REJECTED"
        )
        _insert_evidence(connection, row, disposition, now)
    if reason == "EXISTING_HIGHER_PRIORITY_AUTHORITY_PRESERVED":
        return "VERIFIED"
    values = {
        "timestamp": selected["source_timestamp_utc"] if selected else None,
        "source": selected["source_type"] if selected else None,
        "confidence": ("HIGH" if selected and selected["source_type"] in {"ISSUER_EARNINGS_RELEASE", "SEC_8K_ITEM_2_02"} else "MEDIUM") if selected else None,
        "reference": selected["source_reference"] if selected else None,
        "evidence_id": selected["evidence_id"] if selected else None,
        "verified": now if selected else None,
    }
    if existing is not None and existing["status"] == "VERIFIED" and status == "AMBIGUOUS":
        values = {
            "timestamp": existing["result_publication_timestamp_utc"],
            "source": existing["result_publication_source"],
            "confidence": existing["result_publication_confidence"],
            "reference": existing["result_publication_evidence_reference"],
            "evidence_id": existing["selected_evidence_id"],
            "verified": existing["verified_at_utc"],
        }
    connection.execute(
        """
        INSERT INTO v4_result_publication_authority(
            company_id,fiscal_year,fiscal_quarter,quarter_id,status,result_publication_timestamp_utc,
            result_publication_source,result_publication_confidence,result_publication_evidence_reference,
            selected_evidence_id,verified_at_utc,rule_version,status_reason,updated_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(company_id,fiscal_year,fiscal_quarter) DO UPDATE SET
            quarter_id=excluded.quarter_id,status=excluded.status,
            result_publication_timestamp_utc=excluded.result_publication_timestamp_utc,
            result_publication_source=excluded.result_publication_source,
            result_publication_confidence=excluded.result_publication_confidence,
            result_publication_evidence_reference=excluded.result_publication_evidence_reference,
            selected_evidence_id=excluded.selected_evidence_id,verified_at_utc=excluded.verified_at_utc,
            rule_version=excluded.rule_version,status_reason=excluded.status_reason,updated_at_utc=excluded.updated_at_utc
        """,
        (*key, int(quarter["quarter_id"]), status, values["timestamp"], values["source"], values["confidence"],
         values["reference"], values["evidence_id"], values["verified"], RESULT_PUBLICATION_RULE_VERSION, reason, now),
    )
    return status


def scoped_quarters(connection: sqlite3.Connection, from_fiscal_year: int, tickers: Sequence[str]) -> list[dict[str, Any]]:
    params: list[Any] = [from_fiscal_year]
    ticker_clause = ""
    if tickers:
        ticker_clause = f" AND UPPER(s.current_ticker) IN ({','.join('?' for _ in tickers)})"
        params.extend(ticker.upper() for ticker in tickers)
    rows = connection.execute(
        f"""
        SELECT q.quarter_id,q.company_id,q.fiscal_year,q.fiscal_quarter,q.period_end,
               q.first_public_result_date,q.source_availability_date,c.cik_normalized,s.current_ticker
        FROM v4_quarter q
        JOIN company_cik c ON c.company_id=q.company_id AND c.status='ACTIVE'
        LEFT JOIN security s ON s.company_id=q.company_id AND s.active=1
        WHERE q.fiscal_year>=? {ticker_clause}
        GROUP BY q.quarter_id
        HAVING COUNT(DISTINCT c.cik_normalized)=1
        ORDER BY q.company_id,q.fiscal_year,q.fiscal_quarter
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _lag_bucket(days: int) -> str:
    if days == 0:
        return "SAME_CALENDAR_DATE"
    if abs(days) == 1:
        return "+/-1_DAY"
    if abs(days) <= 7:
        return "2_TO_7_DAYS"
    return ">7_DAYS"


def coverage_audit(connection: sqlite3.Connection, quarters: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    confidence: Counter[str] = Counter()
    lag_first: Counter[str] = Counter()
    lag_availability: Counter[str] = Counter()
    exact = 0
    for quarter in quarters:
        row = connection.execute(
            """SELECT * FROM v4_result_publication_authority
               WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?""",
            (quarter["company_id"], quarter["fiscal_year"], quarter["fiscal_quarter"]),
        ).fetchone()
        if row is None:
            statuses["UNRESOLVED"] += 1
            continue
        status = str(row["status"])
        statuses[status] += 1
        if status != "VERIFIED":
            continue
        sources[str(row["result_publication_source"])] += 1
        confidence[str(row["result_publication_confidence"])] += 1
        timestamp = str(row["result_publication_timestamp_utc"])
        exact += int("T" in timestamp)
        publication_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
        for field, output in (("first_public_result_date", lag_first), ("source_availability_date", lag_availability)):
            if quarter.get(field):
                comparison = datetime.strptime(str(quarter[field]), "%Y-%m-%d").date()
                output[_lag_bucket((publication_date - comparison).days)] += 1
    verified = statuses["VERIFIED"]
    return {
        "total_quarters": len(quarters),
        "status_counts": {name: statuses[name] for name in ("VERIFIED", "UNRESOLVED", "AMBIGUOUS", "NOT_FOUND")},
        "coverage_percent": round(100.0 * verified / len(quarters), 2) if quarters else 0.0,
        "timestamp_precision_percent": round(100.0 * exact / verified, 2) if verified else 0.0,
        "source_distribution": dict(sorted(sources.items())),
        "confidence_distribution": dict(sorted(confidence.items())),
        "lag_vs_first_public_result_date": dict(sorted(lag_first.items())),
        "lag_vs_source_availability_date": dict(sorted(lag_availability.items())),
    }


def enrich_database(
    canonical_db: Path,
    *,
    from_fiscal_year: int = 2025,
    tickers: Sequence[str] = (),
    client: SecClient | None = None,
    apply: bool = False,
    refresh_existing: bool = False,
) -> dict[str, Any]:
    client = client or SecClient()
    with sqlite3.connect(canonical_db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        if apply:
            ensure_result_publication_schema(connection)
        quarters = scoped_quarters(connection, from_fiscal_year, tickers)
        if not refresh_existing and connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='v4_result_publication_authority'"
        ).fetchone():
            verified = {
                (int(row[0]), int(row[1]), str(row[2]))
                for row in connection.execute(
                    "SELECT company_id,fiscal_year,fiscal_quarter FROM v4_result_publication_authority WHERE status='VERIFIED'"
                )
            }
            quarters = [
                row for row in quarters
                if (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])) not in verified
            ]
        by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for quarter in quarters:
            by_company[int(quarter["company_id"])].append(quarter)
        counts: Counter[str] = Counter()
        errors: list[dict[str, Any]] = []
        preview: list[dict[str, Any]] = []
        for company_id, company_quarters in by_company.items():
            try:
                earliest_period_year = min(int(str(row["period_end"])[:4]) for row in company_quarters)
                filings = client.item_2_02_filings(
                    str(company_quarters[0]["cik_normalized"]), from_calendar_year=earliest_period_year
                )
                matches, unresolved = resolve_sec_filings(company_quarters, filings)
                for quarter in company_quarters:
                    key = (company_id, int(quarter["fiscal_year"]), str(quarter["fiscal_quarter"]))
                    status = "VERIFIED" if len(matches.get(key, ())) == 1 else (
                        "AMBIGUOUS" if len(matches.get(key, ())) > 1 else ("UNRESOLVED" if key in unresolved else "NOT_FOUND")
                    )
                    if apply:
                        status = apply_resolution(connection, quarter, matches.get(key, ()), unresolved=key in unresolved)
                    counts[status] += 1
                    preview.append({"ticker": quarter["current_ticker"], "fiscal_year": key[1], "fiscal_quarter": key[2], "status": status,
                                    "timestamp_utc": matches.get(key, [{}])[0].get("source_timestamp_utc") if len(matches.get(key, ())) == 1 else None})
                if apply:
                    connection.commit()
            except Exception as exc:
                connection.rollback()
                errors.append({"company_id": company_id, "ticker": company_quarters[0]["current_ticker"], "error": type(exc).__name__, "reason": str(exc)})
        audit = coverage_audit(connection, quarters) if apply else None
        return {
            "rule_version": RESULT_PUBLICATION_RULE_VERSION,
            "from_fiscal_year": from_fiscal_year,
            "scope_quarters": len(quarters),
            "scope_companies": len(by_company),
            "applied": apply,
            "refresh_existing": refresh_existing,
            "status_counts": {name: counts[name] for name in ("VERIFIED", "UNRESOLVED", "AMBIGUOUS", "NOT_FOUND")},
            "errors": errors,
            "results": preview,
            "coverage_audit": audit,
        }
