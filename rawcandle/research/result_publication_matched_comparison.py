from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


MATCHED_COMPARISON_VERSION = "result_publication_exact_vs_high_matched_v1"
EXPECTED_EVENT_WINDOW_VERSION = "result_publication_event_window_v1"
EXPECTED_EVENT_WINDOW_SHA256 = (
    "85eda92a912299d7beea3b3e11da2d118cd5d53a682b2735983f2b0a7d732af1"
)
EXPECTED_EVENT_WINDOW_ROWS = 13_352
ALLOWED_STATUSES = {"EXACT", "HEURISTIC_HIGH"}
SAME_EFFECTIVE_DAY_METHOD = "ALL_CANDIDATES_SAME_EFFECTIVE_DAY"
HIGH_METHODS = (
    "YAHOO_NEAR_UNIQUE_SEC",
    "SEC_V2_STRONG_INITIAL",
    SAME_EFFECTIVE_DAY_METHOD,
)
OUTCOMES = (
    "gap_pct",
    "D0_close_return_pct",
    "return_D5",
    "return_D10",
    "return_D20",
    "relative_return_D5",
    "relative_return_D20",
)
PAIRED_OUTCOMES = (
    "D0_close_return_pct",
    "return_D5",
    "return_D10",
    "return_D20",
    "relative_return_D5",
    "relative_return_D20",
)
GAP_BUCKETS = ("0_TO_1", "1_TO_3", "3_TO_5", "5_TO_10", "GT_10")
TREND_BUCKETS = (
    "STRONG_NEGATIVE",
    "NEGATIVE",
    "FLAT",
    "POSITIVE",
    "STRONG_POSITIVE",
)


@dataclass(frozen=True)
class MatchedComparison:
    rows: list[dict[str, Any]]
    unmatched_high: list[dict[str, Any]]
    summary: dict[str, Any]
    market_cap: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _identity(row: Mapping[str, Any]) -> tuple[int, int, str]:
    return int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])


def load_event_window(
    csv_path: str | Path,
    metadata_path: str | Path,
    *,
    expected_sha256: str = EXPECTED_EVENT_WINDOW_SHA256,
    expected_rows: int = EXPECTED_EVENT_WINDOW_ROWS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = Path(csv_path)
    metadata_source = Path(metadata_path)
    actual_sha = _sha256(source)
    if actual_sha != expected_sha256:
        raise ValueError("EVENT_WINDOW_SHA256_MISMATCH")
    try:
        metadata = json.loads(metadata_source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("EVENT_WINDOW_METADATA_INVALID") from exc
    if metadata.get("artifact_version") != EXPECTED_EVENT_WINDOW_VERSION:
        raise ValueError("EVENT_WINDOW_VERSION_INVALID")
    if metadata.get("output_csv_sha256") != actual_sha:
        raise ValueError("EVENT_WINDOW_METADATA_SHA256_MISMATCH")

    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected_rows:
        raise ValueError("EVENT_WINDOW_ROW_COUNT_MISMATCH")
    statuses = {row.get("research_status") for row in rows}
    if statuses != ALLOWED_STATUSES:
        raise ValueError(f"EVENT_WINDOW_STATUSES_INVALID:{sorted(str(value) for value in statuses)}")
    identities = [_identity(row) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("EVENT_WINDOW_DUPLICATE_IDENTITY")
    required = {
        "D0_date",
        "gap_pct",
        "return_Dm5_to_Dm1",
        "largest_move_day",
        *OUTCOMES,
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError("EVENT_WINDOW_COLUMNS_INVALID")
    return rows, metadata


def load_latest_market_caps(database: str | Path) -> dict[int, float]:
    connection = _readonly(Path(database))
    try:
        rows = connection.execute(
            """
            SELECT company_id,market_cap,fiscal_sequence
            FROM valuation_revised_result
            WHERE market_cap IS NOT NULL AND market_cap > 0
            ORDER BY company_id,fiscal_sequence DESC
            """
        ).fetchall()
    finally:
        connection.close()
    latest: dict[int, float] = {}
    for row in rows:
        latest.setdefault(int(row["company_id"]), float(row["market_cap"]))
    return latest


def market_cap_tertiles(
    event_rows: Sequence[Mapping[str, Any]], market_caps: Mapping[int, float]
) -> tuple[float, float]:
    company_ids = sorted(
        {int(row["company_id"]) for row in event_rows if int(row["company_id"]) in market_caps}
    )
    values = sorted(float(market_caps[company_id]) for company_id in company_ids)
    if len(values) < 3:
        raise ValueError("MARKET_CAP_SAMPLE_TOO_SMALL")
    return values[len(values) // 3], values[(2 * len(values)) // 3]


def market_cap_bucket(value: float | None, cutoffs: tuple[float, float]) -> str | None:
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    low, high = cutoffs
    if value < low:
        return "SMALL"
    if value < high:
        return "MID"
    return "LARGE"


def absolute_gap_bucket(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    absolute = abs(value)
    if absolute < 1:
        return "0_TO_1"
    if absolute < 3:
        return "1_TO_3"
    if absolute < 5:
        return "3_TO_5"
    if absolute < 10:
        return "5_TO_10"
    return "GT_10"


def pre_event_trend_bucket(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    if value <= -5:
        return "STRONG_NEGATIVE"
    if value < -1:
        return "NEGATIVE"
    if value <= 1:
        return "FLAT"
    if value < 5:
        return "POSITIVE"
    return "STRONG_POSITIVE"


def _prepared_row(
    row: Mapping[str, Any], market_caps: Mapping[int, float], cutoffs: tuple[float, float]
) -> dict[str, Any]:
    result = dict(row)
    cap = market_caps.get(int(row["company_id"]))
    result.update(
        {
            "event_year": int(str(row["D0_date"])[:4]) if row.get("D0_date") else None,
            "market_cap_proxy": cap,
            "market_cap_bucket": market_cap_bucket(cap, cutoffs),
            "absolute_gap_pct": abs(_float(row.get("gap_pct")))
            if _float(row.get("gap_pct")) is not None
            else None,
            "absolute_gap_bucket": absolute_gap_bucket(_float(row.get("gap_pct"))),
            "pre_event_trend": _float(row.get("return_Dm5_to_Dm1")),
            "pre_event_trend_bucket": pre_event_trend_bucket(
                _float(row.get("return_Dm5_to_Dm1"))
            ),
        }
    )
    return result


def _stratum(row: Mapping[str, Any]) -> tuple[Any, ...] | None:
    values = (
        row.get("event_year"),
        row.get("market_cap_bucket"),
        row.get("absolute_gap_bucket"),
        row.get("pre_event_trend_bucket"),
    )
    return values if all(value is not None for value in values) else None


def _match_row(high: Mapping[str, Any], exact: Mapping[str, Any], match_id: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "match_id": match_id,
        "event_year": high["event_year"],
        "market_cap_bucket": high["market_cap_bucket"],
        "absolute_gap_bucket": high["absolute_gap_bucket"],
        "pre_event_trend_bucket": high["pre_event_trend_bucket"],
        "high_company_id": int(high["company_id"]),
        "high_ticker": high["ticker"],
        "high_fiscal_year": int(high["fiscal_year"]),
        "high_fiscal_quarter": high["fiscal_quarter"],
        "high_method": high["research_method"],
        "high_market_cap_proxy": high["market_cap_proxy"],
        "high_absolute_gap_pct": high["absolute_gap_pct"],
        "high_pre_event_trend": high["pre_event_trend"],
        "exact_company_id": int(exact["company_id"]),
        "exact_ticker": exact["ticker"],
        "exact_fiscal_year": int(exact["fiscal_year"]),
        "exact_fiscal_quarter": exact["fiscal_quarter"],
        "exact_market_cap_proxy": exact["market_cap_proxy"],
        "exact_absolute_gap_pct": exact["absolute_gap_pct"],
        "exact_pre_event_trend": exact["pre_event_trend"],
        "absolute_gap_distance": abs(high["absolute_gap_pct"] - exact["absolute_gap_pct"]),
        "pre_event_trend_distance": abs(high["pre_event_trend"] - exact["pre_event_trend"]),
        "high_largest_move_day": high.get("largest_move_day"),
        "exact_largest_move_day": exact.get("largest_move_day"),
    }
    for outcome in OUTCOMES:
        high_value = _float(high.get(outcome))
        exact_value = _float(exact.get(outcome))
        result[f"high_{outcome}"] = high_value
        result[f"exact_{outcome}"] = exact_value
        result[f"difference_{outcome}"] = (
            high_value - exact_value
            if high_value is not None and exact_value is not None
            else None
        )
    return result


def match_events(
    event_rows: Sequence[Mapping[str, Any]], market_caps: Mapping[int, float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[float, float], list[dict[str, Any]]]:
    if not event_rows:
        raise ValueError("EVENT_WINDOW_EMPTY")
    cutoffs = market_cap_tertiles(event_rows, market_caps)
    prepared = [_prepared_row(row, market_caps, cutoffs) for row in event_rows]
    exact_by_stratum: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in prepared:
        if row.get("research_status") == "EXACT" and _stratum(row) is not None:
            exact_by_stratum[_stratum(row)].append(row)  # type: ignore[index]
    for rows in exact_by_stratum.values():
        rows.sort(key=_identity)

    matches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used: set[tuple[int, int, str]] = set()
    high_rows = sorted(
        (row for row in prepared if row.get("research_status") == "HEURISTIC_HIGH"),
        key=lambda row: (_stratum(row) or (9999, "", "", ""), _identity(row)),
    )
    for high in high_rows:
        stratum = _stratum(high)
        if stratum is None:
            reason = "MARKET_CAP_UNAVAILABLE" if high.get("market_cap_bucket") is None else "MATCHING_FIELD_UNAVAILABLE"
            unmatched.append({**high, "unmatched_reason": reason})
            continue
        candidates = [row for row in exact_by_stratum.get(stratum, ()) if _identity(row) not in used]
        if not candidates:
            unmatched.append({**high, "unmatched_reason": "NO_UNUSED_EXACT_IN_STRATUM"})
            continue
        exact = min(
            candidates,
            key=lambda row: (
                abs(high["absolute_gap_pct"] - row["absolute_gap_pct"]),
                abs(high["pre_event_trend"] - row["pre_event_trend"]),
                _identity(row),
            ),
        )
        used.add(_identity(exact))
        matches.append(_match_row(high, exact, len(matches) + 1))
    return matches, unmatched, cutoffs, prepared


def _percentile(values: Sequence[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _stats(values: Sequence[float | None]) -> dict[str, Any]:
    usable = [float(value) for value in values if value is not None]
    return {
        "n": len(usable),
        "median": median(usable) if usable else None,
        "p25": _percentile(usable, 25),
        "p75": _percentile(usable, 75),
        "mean": mean(usable) if usable else None,
        "positive_pct": sum(value > 0 for value in usable) / len(usable) * 100 if usable else None,
    }


def _distribution(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    counts = Counter(str(row[field]) for row in rows if row.get(field) is not None)
    total = sum(counts.values())
    return {
        key: {"count": count, "pct": count / total * 100 if total else None}
        for key, count in sorted(counts.items())
    }


def _total_variation(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(
        abs(float(left.get(key, {}).get("pct") or 0) - float(right.get(key, {}).get("pct") or 0))
        for key in keys
    )


def _balance_pair(
    high_rows: Sequence[Mapping[str, Any]], exact_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    fields = ("event_year", "market_cap_bucket", "absolute_gap_bucket", "pre_event_trend_bucket")
    result: dict[str, Any] = {}
    for field in fields:
        high = _distribution(high_rows, field)
        exact = _distribution(exact_rows, field)
        result[field] = {
            "high": high,
            "exact": exact,
            "total_variation_percentage_points": _total_variation(high, exact),
        }
    return result


def _numeric_balance(
    high_rows: Sequence[Mapping[str, Any]], exact_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("market_cap_proxy", "absolute_gap_pct", "pre_event_trend"):
        high = [_float(row.get(field)) for row in high_rows]
        exact = [_float(row.get(field)) for row in exact_rows]
        high_values = [value for value in high if value is not None]
        exact_values = [value for value in exact if value is not None]
        high_mean = mean(high_values) if high_values else None
        exact_mean = mean(exact_values) if exact_values else None
        variances = []
        for values, value_mean in ((high_values, high_mean), (exact_values, exact_mean)):
            if len(values) > 1 and value_mean is not None:
                variances.append(sum((value - value_mean) ** 2 for value in values) / (len(values) - 1))
        pooled_sd = math.sqrt(sum(variances) / len(variances)) if variances else None
        result[field] = {
            "HIGH": _stats(high_values),
            "EXACT": _stats(exact_values),
            "standardized_mean_difference": (
                (high_mean - exact_mean) / pooled_sd
                if high_mean is not None and exact_mean is not None and pooled_sd
                else None
            ),
        }
    return result


def summarize_matched_comparison(
    matches: Sequence[Mapping[str, Any]],
    unmatched_high: Sequence[Mapping[str, Any]],
    prepared_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matched_high = [
        {
            "event_year": row["event_year"],
            "market_cap_bucket": row["market_cap_bucket"],
            "absolute_gap_bucket": row["absolute_gap_bucket"],
            "pre_event_trend_bucket": row["pre_event_trend_bucket"],
            "market_cap_proxy": row["high_market_cap_proxy"],
            "absolute_gap_pct": row["high_absolute_gap_pct"],
            "pre_event_trend": row["high_pre_event_trend"],
        }
        for row in matches
    ]
    matched_exact = [
        {
            "event_year": row["event_year"],
            "market_cap_bucket": row["market_cap_bucket"],
            "absolute_gap_bucket": row["absolute_gap_bucket"],
            "pre_event_trend_bucket": row["pre_event_trend_bucket"],
            "market_cap_proxy": row["exact_market_cap_proxy"],
            "absolute_gap_pct": row["exact_absolute_gap_pct"],
            "pre_event_trend": row["exact_pre_event_trend"],
        }
        for row in matches
    ]
    eligible_high = [
        row for row in prepared_rows if row.get("research_status") == "HEURISTIC_HIGH" and _stratum(row)
    ]
    eligible_exact = [
        row for row in prepared_rows if row.get("research_status") == "EXACT" and _stratum(row)
    ]
    outcome_summary: dict[str, Any] = {}
    for outcome in OUTCOMES:
        outcome_summary[outcome] = {
            "HIGH": _stats([row.get(f"high_{outcome}") for row in matches]),
            "EXACT": _stats([row.get(f"exact_{outcome}") for row in matches]),
        }
    paired = {
        outcome: _stats([row.get(f"difference_{outcome}") for row in matches])
        for outcome in PAIRED_OUTCOMES
    }
    methods: dict[str, Any] = {}
    for method in HIGH_METHODS:
        subset = [row for row in matches if row.get("high_method") == method]
        methods[method] = {
            "matched_events": len(subset),
            "outcomes": {
                outcome: {
                    "HIGH": _stats([row.get(f"high_{outcome}") for row in subset]),
                    "EXACT": _stats([row.get(f"exact_{outcome}") for row in subset]),
                    "paired_difference": _stats(
                        [row.get(f"difference_{outcome}") for row in subset]
                    ),
                }
                for outcome in OUTCOMES
            },
        }
    controls = Counter(
        (int(row["exact_company_id"]), int(row["exact_fiscal_year"]), str(row["exact_fiscal_quarter"]))
        for row in matches
    )
    shift = {
        "HIGH": dict(sorted(Counter(str(row.get("high_largest_move_day") or "UNAVAILABLE") for row in matches).items())),
        "EXACT": dict(sorted(Counter(str(row.get("exact_largest_move_day") or "UNAVAILABLE") for row in matches).items())),
    }
    return {
        "coverage": {
            "high_total": sum(row.get("research_status") == "HEURISTIC_HIGH" for row in prepared_rows),
            "high_eligible": len(eligible_high),
            "high_matched": len(matches),
            "high_unmatched": len(unmatched_high),
            "unmatched_reasons": dict(sorted(Counter(str(row["unmatched_reason"]) for row in unmatched_high).items())),
            "exact_controls_used": len(controls),
            "control_reuse": {
                "maximum_uses": max(controls.values(), default=0),
                "controls_used_more_than_once": sum(value > 1 for value in controls.values()),
                "reuse_rate_pct": sum(value > 1 for value in controls.values()) / len(controls) * 100 if controls else None,
            },
        },
        "balance": {
            "before": {
                "categorical": _balance_pair(eligible_high, eligible_exact),
                "numeric": _numeric_balance(eligible_high, eligible_exact),
            },
            "after": {
                "categorical": _balance_pair(matched_high, matched_exact),
                "numeric": _numeric_balance(matched_high, matched_exact),
            },
        },
        "outcomes": outcome_summary,
        "paired_differences_high_minus_exact": paired,
        "high_method_results": methods,
        "matched_shift_diagnostic": shift,
    }


def build_matched_comparison(
    event_rows: Sequence[Mapping[str, Any]], market_caps: Mapping[int, float]
) -> MatchedComparison:
    matches, unmatched, cutoffs, prepared = match_events(event_rows, market_caps)
    summary = summarize_matched_comparison(matches, unmatched, prepared)
    available_companies = {int(row["company_id"]) for row in prepared if row.get("market_cap_proxy") is not None}
    return MatchedComparison(
        rows=matches,
        unmatched_high=unmatched,
        summary=summary,
        market_cap={
            "semantics": "latest positive valuation_revised_result.market_cap per company by fiscal_sequence",
            "bucket_basis": "tertiles across distinct event companies with an available proxy",
            "available_event_companies": len(available_companies),
            "small_mid_cutoff": cutoffs[0],
            "mid_large_cutoff": cutoffs[1],
        },
    )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _session(local: datetime) -> str:
    if local.time() < time(9, 30):
        return "PRE_MARKET"
    if local.time() < time(16, 0):
        return "REGULAR_HOURS"
    return "AFTER_MARKET"


def _implied_boundary(local: datetime, event: Mapping[str, Any]) -> str | None:
    local_date = local.date().isoformat()
    d0 = str(event.get("date_D0") or "")
    dm1 = str(event.get("date_Dm1") or "")
    session = _session(local)
    if local_date == d0 and session == "PRE_MARKET":
        return d0
    if local_date == dm1 and session in {"REGULAR_HOURS", "AFTER_MARKET"}:
        return d0
    return None


def review_same_effective_day_cases(
    event_rows: Sequence[Mapping[str, Any]],
    canonical_db: str | Path,
    yahoo_observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    cases = [row for row in event_rows if row.get("research_method") == SAME_EFFECTIVE_DAY_METHOD]
    yahoo = {_identity(row): row for row in yahoo_observations}
    connection = _readonly(Path(canonical_db))
    results: list[dict[str, Any]] = []
    try:
        for event in sorted(cases, key=_identity):
            key = _identity(event)
            evidence = connection.execute(
                """
                SELECT source_timestamp_utc,source_reference,accession_number
                FROM v4_result_publication_evidence
                WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?
                  AND source_type='SEC_8K_ITEM_2_02' AND disposition='CONFLICT'
                ORDER BY source_timestamp_utc,source_reference
                """,
                key,
            ).fetchall()
            candidate_details = []
            for row in evidence:
                local = _parse_timestamp(str(row["source_timestamp_utc"])).astimezone(
                    ZoneInfo("America/New_York")
                )
                candidate_details.append(
                    {
                        "timestamp_utc": str(row["source_timestamp_utc"]),
                        "timestamp_et": local.isoformat(),
                        "local_date": local.date().isoformat(),
                        "session": _session(local),
                        "implied_boundary": _implied_boundary(local, event),
                        "accession_number": row["accession_number"],
                        "source_reference": row["source_reference"],
                    }
                )
            yahoo_row = yahoo.get(key)
            yahoo_timestamp = str(yahoo_row.get("yahoo_event_timestamp")) if yahoo_row else None
            yahoo_boundary = None
            if yahoo_timestamp:
                yahoo_local = _parse_timestamp(yahoo_timestamp).astimezone(ZoneInfo("America/New_York"))
                yahoo_boundary = _implied_boundary(yahoo_local, event)
            expected = str(event.get("first_full_post_result_trading_date") or "")
            candidate_boundaries = {row["implied_boundary"] for row in candidate_details}
            alternative = candidate_boundaries != {expected}
            if not candidate_details or alternative:
                classification = "BOUNDARY_QUESTIONABLE"
            elif yahoo_boundary == expected:
                classification = "BOUNDARY_CONFIRMED"
            else:
                classification = "BOUNDARY_PLAUSIBLE"
            results.append(
                {
                    "company_id": key[0],
                    "ticker": event["ticker"],
                    "fiscal_year": key[1],
                    "fiscal_quarter": key[2],
                    "candidate_count": len(candidate_details),
                    "competing_candidates_json": json.dumps(candidate_details, sort_keys=True),
                    "common_first_full_post_result_trading_date": expected,
                    "date_Dm1": event.get("date_Dm1"),
                    "Dm1_close": _float(event.get("Dm1_close")),
                    "date_D0": event.get("date_D0"),
                    "D0_open": _float(event.get("D0_open")),
                    "D0_close": _float(event.get("D0_close")),
                    "date_Dp1": event.get("date_Dp1"),
                    "Dp1_close": _float(event.get("Dp1_close")),
                    "D0_abs_close_move_pct": _float(event.get("D0_abs_close_move_pct")),
                    "D1_abs_close_move_pct": _float(event.get("D1_abs_close_move_pct")),
                    "largest_move_day": event.get("largest_move_day"),
                    "yahoo_event_timestamp": yahoo_timestamp,
                    "yahoo_implied_boundary": yahoo_boundary,
                    "candidate_implies_different_boundary": alternative,
                    "event_day_selection_defensible": not alternative,
                    "classification": classification,
                }
            )
    finally:
        connection.close()
    return results


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("OUTPUT_ROWS_EMPTY")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_research_outputs(
    comparison: MatchedComparison,
    qa_rows: Sequence[Mapping[str, Any]],
    output_csv: str | Path,
    output_metadata: str | Path,
    qa_csv: str | Path,
    *,
    input_event_csv: str | Path,
    input_event_metadata: str | Path,
    market_cap_db: str | Path,
    canonical_db: str | Path,
    yahoo_observations_path: str | Path,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    output = Path(output_csv)
    qa_output = Path(qa_csv)
    _write_csv(output, comparison.rows)
    _write_csv(qa_output, qa_rows)
    metadata = {
        "artifact_version": MATCHED_COMPARISON_VERSION,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "input_event_window": str(Path(input_event_csv).resolve()),
        "input_event_window_sha256": _sha256(Path(input_event_csv)),
        "input_event_window_metadata": str(Path(input_event_metadata).resolve()),
        "input_event_window_metadata_sha256": _sha256(Path(input_event_metadata)),
        "market_cap_source": str(Path(market_cap_db).resolve()),
        "market_cap_source_sha256": _sha256(Path(market_cap_db)),
        "canonical_evidence_source": str(Path(canonical_db).resolve()),
        "canonical_evidence_source_sha256": _sha256(Path(canonical_db)),
        "yahoo_observations_source": str(Path(yahoo_observations_path).resolve()),
        "yahoo_observations_source_sha256": _sha256(Path(yahoo_observations_path)),
        "matching": {
            "ratio": "1:1",
            "replacement": False,
            "exact_strata": [
                "event_year",
                "market_cap_bucket",
                "absolute_gap_bucket",
                "pre_event_trend_bucket",
            ],
            "candidate_order": [
                "nearest_absolute_gap",
                "nearest_pre_event_trend",
                "company_id_fiscal_year_fiscal_quarter",
            ],
            "gap_buckets_pct": ["[0,1)", "[1,3)", "[3,5)", "[5,10)", "[10,infinity)"],
            "trend_buckets_pct": ["(-infinity,-5]", "(-5,-1)", "[-1,1]", "(1,5)", "[5,infinity)"],
        },
        "market_cap": comparison.market_cap,
        "summary": comparison.summary,
        "same_effective_day_qa": {
            "case_count": len(qa_rows),
            "classification_counts": dict(
                sorted(Counter(str(row["classification"]) for row in qa_rows).items())
            ),
            "questionable_cases": [
                f"{row['ticker']} {row['fiscal_year']}-{row['fiscal_quarter']}"
                for row in qa_rows
                if row["classification"] == "BOUNDARY_QUESTIONABLE"
            ],
        },
        "output_csv": str(output.resolve()),
        "output_csv_sha256": _sha256(output),
        "qa_csv": str(qa_output.resolve()),
        "qa_csv_sha256": _sha256(qa_output),
    }
    metadata_path = Path(output_metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
