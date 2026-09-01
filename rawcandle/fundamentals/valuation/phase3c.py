from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.schema.migrations import migrate_canonical_valuation_copy
from rawcandle.fundamentals.schema.provenance import read_provenance
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT, select_price
from rawcandle.fundamentals.valuation.persistence import (
    CURRENT_FRESHNESS_DAYS,
    PERSISTENCE_SCHEMA_VERSION,
    ValuationRepository,
    build_persisted_results,
    ensure_schema,
    load_canonical_source,
    logical_fingerprint,
    quick_check,
    replace_results,
)


PROTECTED_NAMES = (
    "fundamentals_provider.db", "fundamentals_v4.db", "fundamentals_analysis.db", "osakedata.db",
)
BANDS = ((0, 20, "0_20"), (20, 40, "20_40"), (40, 60, "40_60"), (60, 80, "60_80"), (80, 100, "80_100"))
MARKET_CAP_BANDS = ((0, 300e6, "MICRO"), (300e6, 2e9, "SMALL"), (2e9, 10e9, "MID"), (10e9, math.inf, "LARGE"))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def database_evidence(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        schema_versions = [tuple(row) for row in conn.execute(
            "SELECT db_name,version,applied_at_utc FROM schema_version ORDER BY db_name"
        )] if "schema_version" in tables else []
    return {
        "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "quick_check": quick, "tables": sorted(tables), "page_size": page_size,
        "page_count": page_count, "freelist_count": freelist_count,
        "freelist_bytes": page_size * freelist_count, "schema_versions": schema_versions,
    }


def validate_destinations(
    repo_root: Path,
    *,
    canonical_source: Path,
    analysis_source: Path,
    provider_source: Path,
    market_source: Path,
    canonical_destination: Path | None,
    analysis_destination: Path | None,
    apply: bool,
) -> None:
    protected = {(repo_root / "data" / name).resolve() for name in PROTECTED_NAMES}
    sources = {canonical_source.resolve(), analysis_source.resolve(), provider_source.resolve(), market_source.resolve()}
    destinations = [canonical_destination, analysis_destination]
    if apply and any(path is None for path in destinations):
        raise ValueError("APPLY_REQUIRES_EXPLICIT_CANONICAL_AND_ANALYSIS_DESTINATIONS")
    for destination in (path for path in destinations if path is not None):
        resolved = destination.resolve()
        if resolved in protected:
            raise PermissionError("PHASE3C_PRODUCTION_DESTINATION_BLOCKED")
        if resolved in sources:
            raise ValueError("SOURCE_DATABASE_CANNOT_BE_DESTINATION")
        if destination.is_symlink():
            raise ValueError("SYMLINK_DESTINATION_BLOCKED")
    if canonical_destination and analysis_destination and canonical_destination.resolve() == analysis_destination.resolve():
        raise ValueError("CANONICAL_AND_ANALYSIS_DESTINATIONS_MUST_DIFFER")


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: Iterable[Any]) -> dict[str, Any]:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return {"valid_n": len(valid), "mean": sum(valid) / len(valid) if valid else None, **{
        f"p{int(p * 100):02d}": _quantile(valid, p) for p in (0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99)
    }}


def _correlation(rows: Sequence[Mapping[str, Any]], left: str, right: str) -> float | None:
    pairs = [(float(row[left]), float(row[right])) for row in rows if row.get(left) is not None and row.get(right) is not None]
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    xm, ym = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - xm) * (y - ym) for x, y in pairs)
    xv, yv = sum((x - xm) ** 2 for x in xs), sum((y - ym) ** 2 for y in ys)
    return numerator / math.sqrt(xv * yv) if xv and yv else None


def distribution_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    full = [row for row in rows if row["valuation_status"] == "VALUATION_FULL"]
    scores = [float(row["total_valuation_score"]) for row in full]
    bands = Counter()
    for score in scores:
        for lower, upper, label in BANDS:
            if lower <= score < upper or label == "80_100" and score == 100:
                bands[label] += 1
                break
    exact_zero = sum(score == 0 for score in scores)
    exact_100 = sum(score == 100 for score in scores)
    return {
        "companies": len({row["company_id"] for row in rows}),
        "observations": len(rows),
        "status_counts": dict(sorted(Counter(row["valuation_status"] for row in rows).items())),
        "not_ready_reasons": dict(sorted(Counter(row["reason_code"] for row in rows if row["valuation_status"] == "VALUATION_NOT_READY").items())),
        "not_applicable_reasons": dict(sorted(Counter(row["reason_code"] for row in rows if row["valuation_status"] == "VALUATION_NOT_APPLICABLE").items())),
        "score_distribution": _distribution(scores),
        "score_bands": {label: bands[label] for _, _, label in BANDS},
        "band_semantics": "[0,20),[20,40),[40,60),[60,80),[80,100]",
        "exact_zero_count": exact_zero,
        "exact_zero_share": exact_zero / len(scores) if scores else None,
        "exact_100_count": exact_100,
        "exact_100_share": exact_100 / len(scores) if scores else None,
        "components": {field: _distribution(row.get(field) for row in full) for field in (
            "ebit_yield", "ebit_points", "fcf_yield", "fcf_points", "earnings_yield", "earnings_points"
        )},
        "component_correlations": {
            "ebit_fcf": _correlation(full, "ebit_points", "fcf_points"),
            "ebit_earnings": _correlation(full, "ebit_points", "earnings_points"),
            "fcf_earnings": _correlation(full, "fcf_points", "earnings_points"),
        },
    }


def sign_pattern(row: Mapping[str, Any]) -> str:
    return "/".join("positive" if float(row[field]) > 0 else "nonpositive" for field in (
        "ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common"
    ))


def zero_score_audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_identities: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    full = [row for row in rows if row["valuation_status"] == "VALUATION_FULL"]
    patterns = Counter(sign_pattern(row) for row in full)
    zero = [row for row in full if row["total_valuation_score"] == 0]
    violations = [row for row in zero if any(row.get(field) is None or not math.isfinite(float(row[field])) or float(row[field]) > 0 for field in (
        "ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common"
    ))]
    all_nonpositive = patterns["nonpositive/nonpositive/nonpositive"]
    if violations or all_nonpositive != len(zero):
        raise RuntimeError(f"ZERO_SCORE_HARD_GATE_FAILED:{len(violations)}:{all_nonpositive}:{len(zero)}")
    current_keys = current_identities or set()
    def grouped(field: str, value_fn=None) -> dict[str, int]:
        if value_fn is None:
            value_fn = lambda row: row.get(field) or "UNKNOWN"
        return dict(sorted(Counter(str(value_fn(row)) for row in zero).items()))
    return {
        "passed": True,
        "full_rows": len(full),
        "zero_observations": len(zero),
        "zero_companies": len({row["company_id"] for row in zero}),
        "sign_patterns": {key: {"count": value, "share": value / len(full)} for key, value in sorted(patterns.items())},
        "zero_by_availability_year": grouped("fundamental_available_date", lambda row: str(row["fundamental_available_date"])[:4]),
        "zero_current_vs_historical": grouped("quarter_id", lambda row: "CURRENT" if (int(row["company_id"]), int(row["quarter_id"])) in current_keys else "HISTORICAL_ONLY"),
        "zero_by_lifecycle": grouped("lifecycle"),
        "zero_by_sector": grouped("sector"),
        "zero_by_industry": grouped("industry"),
        "zero_by_security_status": grouped("security_active", lambda row: "ACTIVE" if row.get("security_active") == 1 else "INACTIVE" if row.get("security_active") == 0 else "UNKNOWN"),
        "zero_by_market_cap_band": grouped("market_cap", lambda row: next(label for low, high, label in MARKET_CAP_BANDS if low <= float(row["market_cap"]) < high)),
    }


def deterministic_zero_sample(rows: Sequence[Mapping[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    zero = [dict(row) for row in rows if row["valuation_status"] == "VALUATION_FULL" and row["total_valuation_score"] == 0]
    selected: list[dict[str, Any]] = []
    def add(candidates: Iterable[dict[str, Any]]) -> None:
        for row in candidates:
            if all((row["company_id"], row["quarter_id"]) != (old["company_id"], old["quarter_id"]) for old in selected):
                selected.append(row)
                break
    for low, high, _ in MARKET_CAP_BANDS:
        add(sorted((row for row in zero if low <= row["market_cap"] < high), key=lambda row: (row["company_id"], row["quarter_id"])))
    add(sorted((row for row in zero if row.get("security_active") == 0), key=lambda row: (row["company_id"], row["quarter_id"])))
    for lifecycle in sorted({str(row.get("lifecycle")) for row in zero if row.get("lifecycle")}):
        add(sorted((row for row in zero if row.get("lifecycle") == lifecycle), key=lambda row: (row["company_id"], row["quarter_id"])))
    add(sorted(zero, key=lambda row: (row.get("fundamental_available_date") or "", row["company_id"]), reverse=True))
    add(sorted(zero, key=lambda row: (abs(row["ttm_ebit"]) + abs(row["ttm_free_cashflow"]) + abs(row["ttm_net_income_common"]), row["company_id"])))
    add(sorted(zero, key=lambda row: (row["ttm_ebit"] + row["ttm_free_cashflow"] + row["ttm_net_income_common"], row["company_id"])))
    for row in sorted(zero, key=lambda row: (row["company_id"], row["fiscal_sequence"])):
        if len(selected) >= limit:
            break
        add([row])
    return selected


def phase3a_bridge(
    source_rows: Sequence[Mapping[str, Any]],
    persisted: Sequence[Mapping[str, Any]],
    *,
    market_db: Path | None = None,
) -> dict[str, Any]:
    by_identity = {(row["company_id"], row["quarter_id"]): row for row in persisted}
    ready: list[Mapping[str, Any]] = []
    failures = Counter()
    changed_assumptions = Counter()
    market = sqlite3.connect(f"file:{market_db.resolve()}?mode=ro", uri=True) if market_db else None
    try:
        for item in source_rows:
            observation = item["observation"]
            price = select_price(item["price_bars"], observation.fundamental_available_date)
            selected_price = price.selected_price
            price_failure = price.reason_code
            if price_failure and market is not None and observation.ticker and observation.fundamental_available_date:
                relaxed = market.execute(
                    "SELECT pvm,close FROM osakedata WHERE osake=? AND pvm<=? AND close>0 ORDER BY pvm DESC LIMIT 1",
                    (observation.ticker, observation.fundamental_available_date),
                ).fetchone()
                if relaxed and (date.fromisoformat(observation.fundamental_available_date) - date.fromisoformat(relaxed[0])).days <= 3:
                    selected_price = float(relaxed[1])
                    price_failure = None
                    changed_assumptions["PHASE3B_COMPLETE_COHERENT_OHLC_NEW_EXCLUSION"] += 1
            checks = [
                (not observation.fundamental_available_date, "UNDATED"),
                (observation.ttm_readiness_status != "TTM_READY", "TTM_NOT_READY_OR_INVALID_CHAIN"),
                (price_failure is not None, price_failure or "PRICE_MISSING"),
                (observation.shares_outstanding is None or observation.shares_outstanding <= 0, "SHARES_MISSING_OR_NONPOSITIVE"),
                (observation.cash is None, "CASH_MISSING"),
                (observation.total_debt is None, "DEBT_MISSING"),
                (observation.ttm_ebit is None, "TTM_EBIT_MISSING"),
                (observation.ttm_free_cashflow is None, "TTM_FCF_MISSING"),
                (not observation.net_income_common_4q_ready or observation.ttm_net_income_common is None, "COMMON_EARNINGS_HISTORY_INCOMPLETE"),
            ]
            failure = next((reason for failed, reason in checks if failed), None)
            if failure:
                failures[failure] += 1
                continue
            assert selected_price is not None and observation.shares_outstanding is not None
            assert observation.cash is not None and observation.total_debt is not None
            enterprise_value = selected_price * observation.shares_outstanding + observation.total_debt - observation.cash
            if not math.isfinite(enterprise_value) or enterprise_value <= 0:
                failures["ENTERPRISE_VALUE_NONPOSITIVE"] += 1
                continue
            ready.append(by_identity[(observation.company_id, observation.quarter_id)])
    finally:
        if market is not None:
            market.close()
    return {
        "all_observations": len(source_rows),
        "dated_observations": sum(bool(item["observation"].fundamental_available_date) for item in source_rows),
        "phase3a_formula_ready_reconstructed": len(ready),
        "phase3a_reported_formula_ready": 41576,
        "ready_phase3b_outcomes": dict(sorted(Counter(row["valuation_status"] for row in ready).items())),
        "ready_phase3b_reasons": dict(sorted(Counter(row["reason_code"] for row in ready).items())),
        "not_formula_ready_bridge": dict(sorted(failures.items())),
        "changed_eligibility_or_formula_assumptions": dict(sorted(changed_assumptions.items())),
        "reconciles_reported": len(ready) == 41576,
    }


def export_zero_sample(path: Path, rows: Sequence[Mapping[str, Any]], canonical_db: Path, analysis_db: Path) -> None:
    lifecycle: dict[tuple[int, int], str | None] = {}
    with sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_revised_result'").fetchone():
            lifecycle = {(int(row[0]), int(row[1])): row[2] for row in conn.execute(
                "SELECT company_id,quarter_id,final_state FROM lifecycle_revised_result"
            )}
    common_inputs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    quarter_ids = [int(row["quarter_id"]) for row in rows]
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for quarter_id in quarter_ids:
            for item in conn.execute(
                """SELECT i.input_position,q.fiscal_year,q.fiscal_quarter,f.net_income_common,
                          i.input_quarter_id
                   FROM v4_ttm_values t JOIN v4_ttm_input_quarter i ON i.ttm_id=t.ttm_id
                   JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id
                   JOIN v4_quarter_financials f ON f.quarter_id=i.input_quarter_id
                   WHERE t.endpoint_quarter_id=? ORDER BY i.input_position""", (quarter_id,)
            ):
                record = dict(item)
                provenance = read_provenance(
                    conn,
                    quarter_id=int(record.pop("input_quarter_id")),
                    canonical_field="net_income_common",
                )
                record["provider_observation_id"] = provenance[0]["provider_observation_id"] if provenance else None
                record["source_native_field"] = provenance[0]["source_native_field"] if provenance else None
                common_inputs[quarter_id].append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["company_id", "ticker", "fiscal_year", "fiscal_quarter", "fundamental_available_date", "price_date", "selected_price", "shares_outstanding", "market_cap", "enterprise_value", "ttm_ebit", "ttm_free_cashflow", "ttm_net_income_common", "ebit_yield", "ebit_points", "fcf_yield", "fcf_points", "earnings_yield", "earnings_points", "total_valuation_score", "lifecycle", "sector", "industry", "valuation_status", "reason_code", "common_quarter_inputs_json"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            record = {field: row.get(field) for field in fields}
            record["lifecycle"] = lifecycle.get((int(row["company_id"]), int(row["quarter_id"])))
            record["common_quarter_inputs_json"] = json.dumps(common_inputs[int(row["quarter_id"])], sort_keys=True, separators=(",", ":"))
            writer.writerow(record)


def _lifecycle_lookup(analysis_db: Path) -> dict[tuple[int, int], str | None]:
    with sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_revised_result'").fetchone():
            return {}
        return {(int(row[0]), int(row[1])): row[2] for row in conn.execute(
            "SELECT company_id,quarter_id,final_state FROM lifecycle_revised_result"
        )}


def representative_current(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_ticker = {row.get("ticker"): row for row in rows if row.get("ticker")}
    requested = ("NVDA", "AAPL", "MSFT", "DAVE", "TSLA", "T", "VZ", "O", "CME")
    output = {ticker: by_ticker[ticker] for ticker in requested if ticker in by_ticker}
    real_estate = next((row for row in rows if row.get("sector") == "Real Estate" and row.get("applicability_classification") == "SUPPORTED"), None)
    financial = next((row for row in rows if row.get("industry") == "Financial Data & Stock Exchanges"), None)
    bank_insurer = next((row for row in rows if row.get("reason_code") in ("UNSUPPORTED_BANK_MODEL", "UNSUPPORTED_INSURANCE_MODEL")), None)
    output["NON_REIT_REAL_ESTATE"] = real_estate
    output["FINANCIAL_DATA_EXCHANGE"] = financial
    output["BANK_OR_INSURER"] = bank_insurer
    output["MATURE_PROFITABLE"] = next((row for row in rows if row.get("lifecycle") == "MATURE" and row.get("valuation_status") == "VALUATION_FULL" and row.get("ttm_net_income_common", 0) > 0), None)
    output["GROWTH"] = next((row for row in rows if row.get("lifecycle") == "GROWTH" and row.get("valuation_status") == "VALUATION_FULL"), None)
    output["LOSS_MAKING"] = next((row for row in rows if row.get("valuation_status") == "VALUATION_FULL" and row.get("ttm_net_income_common", 0) <= 0), None)
    output["LEVERAGED"] = next((row for row in rows if row.get("valuation_status") == "VALUATION_FULL" and row.get("net_debt", 0) > 0), None)
    output["NET_CASH"] = next((row for row in rows if row.get("valuation_status") == "VALUATION_FULL" and row.get("net_debt", 0) < 0), None)
    return output


def run_rehearsal(
    *, repo_root: Path, canonical_source: Path, provider_source: Path, analysis_source: Path,
    market_source: Path, canonical_destination: Path, analysis_destination: Path, output_dir: Path,
) -> dict[str, Any]:
    before = {name: database_evidence(path) for name, path in {
        "canonical": canonical_source, "provider": provider_source, "analysis": analysis_source, "market": market_source,
    }.items()}
    sqlite_backup(canonical_source, canonical_destination)
    sqlite_backup(analysis_source, analysis_destination)
    copy_initial = {"canonical": database_evidence(canonical_destination), "analysis": database_evidence(analysis_destination)}
    migration = migrate_canonical_valuation_copy(canonical_destination, provider_source, utc_now())
    source = load_canonical_source(canonical_destination, market_source)
    generated = utc_now()
    rows = build_persisted_results(source, calculated_at=generated)
    with sqlite3.connect(analysis_destination) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        conn.execute("INSERT OR REPLACE INTO schema_version(db_name,version,applied_at_utc) VALUES ('fundamentals_analysis',?,?)", (PERSISTENCE_SCHEMA_VERSION, generated))
        first = replace_results(conn, rows)
        first_check = quick_check(conn, expected_rows=rows)
        conn.commit()
        first_stored = [dict(row) for row in conn.execute("SELECT * FROM valuation_revised_result WHERE model_fingerprint=? ORDER BY company_id,fiscal_sequence", (MODEL_FINGERPRINT,))]
        second = replace_results(conn, rows)
        second_check = quick_check(conn, expected_rows=rows)
        conn.commit()
        repository = ValuationRepository(conn)
        with sqlite3.connect(f"file:{market_source.resolve()}?mode=ro", uri=True) as market:
            as_of = str(market.execute("SELECT MAX(pvm) FROM osakedata").fetchone()[0])
        current = repository.current_universe(model_fingerprint=MODEL_FINGERPRINT, as_of_date=as_of)
    if not first_check["ok"] or not second_check["ok"] or second.rows_inserted or second.rows_deleted:
        raise RuntimeError("VALUATION_PERSISTENCE_REHEARSAL_GATE_FAILED")
    lifecycle = _lifecycle_lookup(analysis_destination)
    for row in first_stored:
        row["lifecycle"] = lifecycle.get((int(row["company_id"]), int(row["quarter_id"])))
    for row in current:
        row["lifecycle"] = lifecycle.get((int(row["company_id"]), int(row["quarter_id"])))
    current_identities = {(int(row["company_id"]), int(row["quarter_id"])) for row in current}
    zero_audit = zero_score_audit(first_stored, current_identities=current_identities)
    sample = deterministic_zero_sample(first_stored)
    output_dir.mkdir(parents=True, exist_ok=True)
    export_zero_sample(output_dir / "zero_score_sample.csv", sample, canonical_destination, analysis_destination)
    bridge = phase3a_bridge(source.rows, first_stored, market_db=market_source)
    after = {name: database_evidence(path) for name, path in {
        "canonical": canonical_source, "provider": provider_source, "analysis": analysis_source, "market": market_source,
    }.items()}
    if before != after:
        raise RuntimeError("PRODUCTION_SOURCE_DATABASE_CHANGED")
    report = {
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_schema_version": PERSISTENCE_SCHEMA_VERSION,
        "production_before": before,
        "production_after": after,
        "production_unchanged": before == after,
        "copy_initial": copy_initial,
        "copy_final": {"canonical": database_evidence(canonical_destination), "analysis": database_evidence(analysis_destination)},
        "copy_growth_bytes": {
            "canonical": canonical_destination.stat().st_size - copy_initial["canonical"]["size"],
            "analysis": analysis_destination.stat().st_size - copy_initial["analysis"]["size"],
        },
        "canonical_migration": migration,
        "source_fingerprint": source.source_fingerprint,
        "result_fingerprint": logical_fingerprint(rows),
        "first_apply": first.__dict__, "second_apply": second.__dict__,
        "first_quick_check": first_check, "second_quick_check": second_check,
        "historical_distribution": distribution_summary(first_stored),
        "current_universe": {
            "as_of_date": as_of, "freshness_days": CURRENT_FRESHNESS_DAYS,
            **distribution_summary(current), "representative_results": representative_current(current),
        },
        "zero_score_audit": zero_audit,
        "zero_sample_rows": len(sample),
        "phase3a_bridge": bridge,
    }
    (output_dir / "phase3c_rehearsal.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return report
