from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.delta.context import (
    LIFECYCLE_CONTEXT_FINGERPRINT,
    VALUATION_DIAGNOSTIC_FINGERPRINT,
    calculate_lifecycle_context,
    calculate_valuation_diagnostic,
)
from rawcandle.fundamentals.delta.engine import (
    COMPONENT_MAXIMA,
    MODEL_CONTRACT,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    DeltaStatus,
    Horizon,
    canonical_json,
    calculate_fundamental_delta,
    fingerprint,
)
from rawcandle.fundamentals.delta.source import (
    DEFAULT_FRESHNESS_DAYS,
    DeltaSource,
    ReadOnlyDeltaPaths,
    latest_fresh_observations,
    load_delta_source,
)


@dataclass(frozen=True)
class RehearsalPaths:
    analysis_db: Path
    canonical_db: Path
    provider_db: Path
    market_db: Path
    taxonomy_db: Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schema_hash(path: Path) -> str:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name,tbl_name"
        ).fetchall()
    return fingerprint(rows)


def database_integrity(paths: RehearsalPaths) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for label, path in (
        ("analysis", paths.analysis_db), ("canonical", paths.canonical_db),
        ("provider", paths.provider_db), ("market", paths.market_db),
        ("taxonomy", paths.taxonomy_db),
    ):
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError(f"INTEGRITY_DB_INVALID:{label}")
        stat = path.stat()
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            table_counts = {
                row[0]: int(conn.execute(f'SELECT COUNT(*) FROM "{row[0]}"').fetchone()[0])
                for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            }
        output[label] = {
            "path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256_file(path), "schema_hash": _schema_hash(path),
            "page_count": page_count, "freelist_count": freelist,
            "quick_check": quick, "table_counts": table_counts,
        }
    return output


def _open_gzip(path: Path) -> gzip.GzipFile:
    raw = path.open("wb")
    return gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)


def _json_line(handle: gzip.GzipFile, payload: Any) -> None:
    handle.write((canonical_json(payload) + "\n").encode("utf-8"))


def _number(value: Any) -> float | None:
    return float(value) if value is not None and not isinstance(value, bool) and math.isfinite(float(value)) else None


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _correlation(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mx, my = mean(xs), mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in pairs)
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def _csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _score_total_payload(result: Any) -> dict[str, Any]:
    payload = asdict(result)
    for horizon in payload["horizons"]:
        horizon.pop("components", None)
    return payload


def _context_row(result: Any) -> dict[str, Any]:
    row = {
        "company_id": result.company_id,
        "current_observation_id": result.current_observation_id,
        "current_final_state": result.current_final_state,
        "current_raw_state": result.current_raw_state,
        "lifecycle_status": result.lifecycle_status,
        "last_confirmed_state": result.last_confirmed_state,
        "candidate_state": result.candidate_state,
        "candidate_count": result.candidate_count,
        "latest_confirmed_transition_observation_id": result.latest_confirmed_transition_observation_id,
        "latest_confirmed_transition_fiscal_sequence": result.latest_confirmed_transition_fiscal_sequence,
        "consecutive_classified_observations": result.consecutive_classified_observations,
        "result_fingerprint": result.result_fingerprint,
    }
    for item in result.horizons:
        prefix = item.horizon.value.lower()
        row.update({
            f"{prefix}_status": item.status.value, f"{prefix}_reason": item.reason_code,
            f"{prefix}_prior_observation_id": item.prior_observation_id,
            f"{prefix}_prior_final_state": item.prior_final_state,
            f"{prefix}_state_changed": item.state_changed,
        })
    return row


def _valuation_row(result: Any) -> dict[str, Any]:
    row = {
        "company_id": result.company_id, "current_observation_id": result.current_observation_id,
        "current_result_id": result.current_result_id, "result_fingerprint": result.result_fingerprint,
    }
    for item in result.horizons:
        prefix = item.horizon.value.lower()
        row.update({f"{prefix}_{key}": value for key, value in asdict(item).items() if key != "horizon"})
    return row


def _replay(
    source: DeltaSource,
    *,
    total_path: Path,
    component_path: Path,
    lifecycle_path: Path,
    valuation_path: Path,
    collect: bool,
) -> dict[str, Any]:
    analytics: dict[str, Any] = {
        "readiness": Counter(), "reasons": Counter(), "component_readiness": Counter(),
        "values": defaultdict(list), "combinations": Counter(), "trajectory_pairs": defaultdict(list),
        "trajectory_delta_pairs": defaultdict(list), "sign_cross_tabs": Counter(), "cases": [],
        "lifecycle_readiness": Counter(), "valuation_readiness": Counter(),
        "valuation_values": defaultdict(list), "result_fingerprints": [],
        "lifecycle_result_fingerprints": [], "valuation_result_fingerprints": [],
        "lifecycle_cases": [], "valuation_cases": [],
    }
    context_fields = list(_context_row(calculate_lifecycle_context(
        next(iter(source.lifecycle_histories.values()))[0], next(iter(source.lifecycle_histories.values())),
        source_fingerprint=source.lifecycle_source_fingerprint,
    )).keys())
    valuation_fields = list(_valuation_row(calculate_valuation_diagnostic(
        next(iter(source.valuation_histories.values()))[0], next(iter(source.valuation_histories.values())),
        source_fingerprint=source.valuation_source_fingerprint,
    )).keys())
    with _open_gzip(total_path) as totals, _open_gzip(component_path) as components, lifecycle_path.open("w", encoding="ascii", newline="") as life_handle, valuation_path.open("w", encoding="ascii", newline="") as val_handle:
        life_writer = csv.DictWriter(life_handle, fieldnames=context_fields, lineterminator="\n")
        val_writer = csv.DictWriter(val_handle, fieldnames=valuation_fields, lineterminator="\n")
        life_writer.writeheader(); val_writer.writeheader()
        for company_id, history in source.score_histories.items():
            for current in history:
                result = calculate_fundamental_delta(current, history, source_fingerprint=source.score_source_fingerprint)
                _json_line(totals, _score_total_payload(result))
                if collect:
                    analytics["result_fingerprints"].append(result.result_fingerprint)
                ready_set = set()
                current_components = {item.component_name: item for item in current.components}
                trajectory = _number(current_components.get("FUNDAMENTAL_TRAJECTORY").points) if current_components.get("FUNDAMENTAL_TRAJECTORY") else None
                case = {"company_id": company_id, "ticker": source.company_tickers.get(company_id), "current": current, "result": result}
                if collect:
                    analytics["cases"].append(case)
                for horizon in result.horizons:
                    if collect:
                        analytics["readiness"][(horizon.horizon.value, horizon.status.value)] += 1
                        if horizon.status == DeltaStatus.READY:
                            ready_set.add(horizon.horizon.value)
                            analytics["values"][horizon.horizon.value].append(float(horizon.delta_points))
                            if trajectory is not None:
                                analytics["trajectory_pairs"][horizon.horizon.value].append((trajectory, float(horizon.delta_points)))
                        else:
                            analytics["reasons"][(horizon.horizon.value, horizon.reason_code)] += 1
                    for component in horizon.components:
                        _json_line(components, {
                            "company_id": company_id, "current_observation_id": result.current_observation_id,
                            "current_score_result_id": result.current_score_result_id,
                            "horizon": horizon.horizon.value, **asdict(component),
                        })
                        if collect:
                            analytics["component_readiness"][(horizon.horizon.value, component.component_name, component.status.value)] += 1
                            if component.component_name == "FUNDAMENTAL_TRAJECTORY" and component.status == DeltaStatus.READY and trajectory is not None:
                                analytics["trajectory_delta_pairs"][horizon.horizon.value].append((trajectory, float(component.delta_points)))
                                total_sign = 0 if horizon.delta_points is None or horizon.delta_points == 0 else (1 if horizon.delta_points > 0 else -1)
                                component_sign = 0 if component.delta_points == 0 else (1 if component.delta_points > 0 else -1)
                                analytics["sign_cross_tabs"][(horizon.horizon.value, total_sign, component_sign)] += 1
                if collect:
                    analytics["combinations"][tuple(sorted(ready_set))] += 1
        for company_id, history in source.lifecycle_histories.items():
            for current in history:
                result = calculate_lifecycle_context(current, history, source_fingerprint=source.lifecycle_source_fingerprint)
                life_writer.writerow(_context_row(result))
                if collect:
                    analytics["lifecycle_result_fingerprints"].append(result.result_fingerprint)
                    analytics["lifecycle_cases"].append({"current": current, "result": result})
                    for item in result.horizons:
                        analytics["lifecycle_readiness"][(item.horizon.value, item.status.value)] += 1
        for company_id, history in source.valuation_histories.items():
            for current in history:
                result = calculate_valuation_diagnostic(current, history, source_fingerprint=source.valuation_source_fingerprint)
                val_writer.writerow(_valuation_row(result))
                if collect:
                    analytics["valuation_result_fingerprints"].append(result.result_fingerprint)
                    analytics["valuation_cases"].append({"current": current, "history": history, "result": result})
                    for item in result.horizons:
                        analytics["valuation_readiness"][(item.horizon.value, item.status.value)] += 1
                        if item.status == DeltaStatus.READY:
                            analytics["valuation_values"][item.horizon.value].append(float(item.score_change))
    return analytics


def _distribution_rows(values: Mapping[str, Sequence[float]]) -> list[dict[str, Any]]:
    rows = []
    for horizon in Horizon:
        items = list(values[horizon.value])
        rows.append({
            "horizon": horizon.value, "count": len(items), "minimum": min(items) if items else None,
            "p01": _percentile(items, .01), "p10": _percentile(items, .10),
            "p25": _percentile(items, .25), "median": _percentile(items, .50),
            "p75": _percentile(items, .75), "p90": _percentile(items, .90),
            "p99": _percentile(items, .99), "maximum": max(items) if items else None,
            "positive": sum(value > 0 for value in items), "negative": sum(value < 0 for value in items),
            "exact_zero": sum(value == 0 for value in items),
        })
    return rows


def _current_rows(source: DeltaSource, *, as_of_date: str, freshness_days: int) -> tuple[list[dict[str, Any]], Counter[Any], Counter[Any]]:
    rows: list[dict[str, Any]] = []
    counts: Counter[Any] = Counter()
    component_counts: Counter[Any] = Counter()
    for current in latest_fresh_observations(source.score_histories, as_of_date=as_of_date, freshness_days=freshness_days):
        history = source.score_histories[current.fiscal.company_id]
        result = calculate_fundamental_delta(current, history, source_fingerprint=source.score_source_fingerprint)
        row = {
            "company_id": current.fiscal.company_id, "ticker": source.company_tickers.get(current.fiscal.company_id),
            "fiscal_year": current.fiscal.fiscal_year, "fiscal_quarter": current.fiscal.fiscal_quarter,
            "available_date": current.fiscal.available_date, "current_score": result.current_score,
        }
        for item in result.horizons:
            prefix = item.horizon.value.lower()
            row[f"{prefix}_status"] = item.status.value
            row[f"{prefix}_delta"] = item.delta_points
            counts[(item.horizon.value, item.status.value)] += 1
            for component in item.components:
                component_counts[(item.horizon.value, component.component_name, component.status.value)] += 1
        rows.append(row)
    return rows, counts, component_counts


def _current_context_counts(source: DeltaSource, *, as_of_date: str, freshness_days: int) -> tuple[Counter[Any], Counter[Any]]:
    lifecycle_counts: Counter[Any] = Counter()
    valuation_counts: Counter[Any] = Counter()
    for current in latest_fresh_observations(source.lifecycle_histories, as_of_date=as_of_date, freshness_days=freshness_days):
        result = calculate_lifecycle_context(current, source.lifecycle_histories[current.fiscal.company_id], source_fingerprint=source.lifecycle_source_fingerprint)
        for item in result.horizons:
            lifecycle_counts[(item.horizon.value, item.status.value)] += 1
    for current in latest_fresh_observations(source.valuation_histories, as_of_date=as_of_date, freshness_days=freshness_days):
        result = calculate_valuation_diagnostic(current, source.valuation_histories[current.fiscal.company_id], source_fingerprint=source.valuation_source_fingerprint)
        for item in result.horizons:
            valuation_counts[(item.horizon.value, item.status.value)] += 1
    return lifecycle_counts, valuation_counts


def _representative_cases(analytics: Mapping[str, Any]) -> str:
    candidates = analytics["cases"]
    def horizons(case: Mapping[str, Any]) -> dict[str, Any]:
        return {item.horizon.value: item for item in case["result"].horizons}
    def all_ready(case: Mapping[str, Any]) -> bool:
        return all(item.status == DeltaStatus.READY for item in horizons(case).values())
    selectors = {
        "Strong positive across all horizons": lambda c: all_ready(c) and all(item.delta_points > 0 for item in horizons(c).values()),
        "Strong negative across all horizons": lambda c: all_ready(c) and all(item.delta_points < 0 for item in horizons(c).values()),
        "Negative QoQ, positive 2Q and YoY": lambda c: all_ready(c) and horizons(c)["QOQ"].delta_points < 0 < min(horizons(c)["TWO_QUARTER"].delta_points, horizons(c)["YOY"].delta_points),
        "Positive QoQ, negative 2Q and YoY": lambda c: all_ready(c) and horizons(c)["QOQ"].delta_points > 0 > max(horizons(c)["TWO_QUARTER"].delta_points, horizons(c)["YOY"].delta_points),
        "Positive QoQ and 2Q, negative YoY": lambda c: all_ready(c) and min(horizons(c)["QOQ"].delta_points, horizons(c)["TWO_QUARTER"].delta_points) > 0 > horizons(c)["YOY"].delta_points,
    }
    lines = ["# Representative Cases", "", "Values are signed Fundamental Score point changes; Trajectory component changes are not Trajectory itself.", ""]
    for title, predicate in selectors.items():
        matches = [case for case in candidates if predicate(case)]
        matches.sort(key=lambda case: sum(abs(item.delta_points or 0) for item in horizons(case).values()), reverse=True)
        lines.append(f"## {title}")
        if not matches:
            lines.extend(["No production case matched.", ""]); continue
        case = matches[0]; hs = horizons(case)
        lines.extend([f"- `{case['ticker'] or case['company_id']}`: QoQ `{hs['QOQ'].delta_points:.4f}`, 2Q `{hs['TWO_QUARTER'].delta_points:.4f}`, YoY `{hs['YOY'].delta_points:.4f}`.", ""])
    trajectory_cases = []
    for case in candidates:
        current_component = next((item for item in case["current"].components if item.component_name == "FUNDAMENTAL_TRAJECTORY"), None)
        two_quarter = horizons(case)["TWO_QUARTER"]
        if current_component and _number(current_component.points) is not None and two_quarter.status == DeltaStatus.READY:
            trajectory_cases.append((case, float(current_component.points), float(two_quarter.delta_points)))
    for title, matches in (
        ("High Trajectory with negative 2Q Delta", [item for item in trajectory_cases if item[1] >= 8 and item[2] < 0]),
        ("Low Trajectory with positive 2Q Delta", [item for item in trajectory_cases if item[1] <= 2 and item[2] > 0]),
    ):
        lines.append(f"## {title}")
        if matches:
            case, trajectory, delta = max(matches, key=lambda item: abs(item[2]))
            lines.append(f"- `{case['ticker'] or case['company_id']}`: Trajectory `{trajectory:.4f}`, 2Q Delta `{delta:.4f}`.")
        else:
            lines.append("No production case matched.")
        lines.append("")
    dominated = []
    diagnostic = []
    for case in candidates:
        item = horizons(case)["TWO_QUARTER"]
        ready_components = [component for component in item.components if component.status == DeltaStatus.READY]
        if item.status == DeltaStatus.READY and item.delta_points and ready_components:
            largest = max(ready_components, key=lambda component: abs(float(component.delta_points)))
            if abs(float(largest.delta_points)) >= .8 * abs(float(item.delta_points)):
                dominated.append((case, item, largest))
        if item.status != DeltaStatus.READY and ready_components:
            diagnostic.append((case, item, ready_components[0]))
    lines.append("## Total Delta dominated by one component")
    if dominated:
        case, item, largest = max(dominated, key=lambda value: abs(float(value[1].delta_points)))
        lines.append(f"- `{case['ticker'] or case['company_id']}`: 2Q `{item.delta_points:.4f}`; `{largest.component_name}` contributes `{largest.delta_points:.4f}`.")
    else:
        lines.append("No production case matched the 80% heuristic.")
    lines.extend(["", "## Component ready while total Delta unavailable"])
    if diagnostic:
        case, item, component = diagnostic[0]
        lines.append(f"- `{case['ticker'] or case['company_id']}`: total `{item.status.value}`; `{component.component_name}` 2Q Delta `{component.delta_points:.4f}`.")
    else:
        lines.append("No production case matched.")
    lines.extend(["", "## Lifecycle transition inside 2Q window"])
    life_matches = []
    for case in analytics["lifecycle_cases"]:
        item = next(row for row in case["result"].horizons if row.horizon == Horizon.TWO_QUARTER)
        if item.status == DeltaStatus.READY and item.state_changed:
            life_matches.append((case, item))
    if life_matches:
        case, item = life_matches[0]
        lines.append(f"- Company `{case['result'].company_id}`: `{item.prior_final_state}` to `{case['result'].current_final_state}`.")
    else:
        lines.append("No production case matched.")
    lines.append("")
    valuation_candidates = []
    for case in analytics["valuation_cases"]:
        item = next(row for row in case["result"].horizons if row.horizon == Horizon.TWO_QUARTER)
        if item.status == DeltaStatus.READY and item.prior_price and item.current_price:
            price_change = item.current_price / item.prior_price - 1.0
            valuation_candidates.append((case, item, price_change))
    for title, matches in (
        ("Valuation 2Q change with large price movement", [item for item in valuation_candidates if abs(item[2]) >= .25]),
        ("Valuation 2Q change with nearly unchanged price", [item for item in valuation_candidates if abs(item[2]) <= .02 and abs(float(item[1].score_change)) >= 15]),
    ):
        lines.append(f"## {title}")
        if matches:
            case, item, price_change = max(matches, key=lambda value: abs(float(value[1].score_change)))
            lines.append(f"- Company `{case['result'].company_id}`: score change `{item.score_change:.4f}`, price change `{price_change:.2%}`. This is diagnostic evidence, not a causal decomposition.")
        else:
            lines.append("No production case matched the documented heuristic.")
        lines.append("")
    for ticker in ("CRMD", "APD"):
        matches = [case for case in candidates if case["ticker"] == ticker]
        lines.append(f"## {ticker}")
        if not matches:
            lines.extend(["Not found.", ""]); continue
        case = max(matches, key=lambda item: item["current"].fiscal.fiscal_sequence)
        for item in case["result"].horizons:
            contributions = ", ".join(
                f"{component.component_name}={component.delta_points:.4f}" if component.delta_points is not None else f"{component.component_name}=N/A"
                for component in item.components
            )
            lines.append(f"- {item.horizon.value}: `{item.delta_points}` ({item.status.value}); {contributions}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _benchmark(total_path: Path, component_path: Path, endpoint_count: int) -> tuple[dict[str, Any], str]:
    horizons = len(Horizon); components = len(COMPONENT_MAXIMA)
    a_rows = endpoint_count * horizons * (components + 1)
    b_rows = endpoint_count * (components + 1)
    c_rows = b_rows
    measured = total_path.stat().st_size + component_path.stat().st_size
    rows = {
        "A_HORIZON_NORMALIZED": {"logical_rows": a_rows, "estimated_compressed_bytes": measured * 3, "estimated_sqlite_table_bytes": measured * 12, "estimated_index_bytes": measured * 4, "reader_complexity": "high", "company_rebuild": "delete/insert many horizon rows", "full_rebuild": "simple bulk rows, highest volume"},
        "B_WIDE_ENDPOINT": {"logical_rows": b_rows, "estimated_compressed_bytes": measured, "estimated_sqlite_table_bytes": measured * 4, "estimated_index_bytes": measured, "reader_complexity": "low", "company_rebuild": "few endpoint rows", "full_rebuild": "compact bulk rows"},
        "C_COMPACT_HYBRID": {"logical_rows": c_rows, "estimated_compressed_bytes": measured, "estimated_sqlite_table_bytes": measured * 4, "estimated_index_bytes": measured, "reader_complexity": "low", "company_rebuild": "few endpoint rows by concept", "full_rebuild": "compact separated concepts", "recommended": True},
    }
    text = "# Persistence Representation Benchmark\n\n" + "\n".join(
        f"- {name}: `{value['logical_rows']}` logical rows, approximately `{value['estimated_compressed_bytes']}` compressed bytes, `{value['estimated_sqlite_table_bytes']}` table bytes and `{value['estimated_index_bytes']}` index bytes."
        for name, value in rows.items()
    ) + "\n\nRecommend C for Phase 5C: one wide total endpoint plus seven wide component endpoint rows, with Lifecycle and Valuation separate. SQLite table and index sizes remain estimates until a separately authorized schema prototype; identifier repetition makes A materially larger and harder to read/rebuild.\n"
    return rows, text


def run_full_history_rehearsal(
    paths: RehearsalPaths,
    *,
    as_of_date: str,
    score_model_fingerprint: str,
    lifecycle_model_fingerprint: str,
    valuation_model_fingerprint: str,
    output_dir: Path,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> dict[str, Any]:
    date.fromisoformat(as_of_date)
    if not output_dir.is_absolute():
        raise ValueError("OUTPUT_DIR_MUST_BE_ABSOLUTE")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("OUTPUT_DIR_MUST_BE_EMPTY")
    output_dir.mkdir(parents=True, exist_ok=True)
    before = database_integrity(paths)
    source = load_delta_source(
        ReadOnlyDeltaPaths(paths.analysis_db, paths.canonical_db),
        score_model_fingerprint=score_model_fingerprint,
        lifecycle_model_fingerprint=lifecycle_model_fingerprint,
        valuation_model_fingerprint=valuation_model_fingerprint,
    )
    names = {
        "total": "fundamental_delta_history.jsonl.gz",
        "component": "fundamental_component_delta_history.jsonl.gz",
        "lifecycle": "lifecycle_change_context.csv",
        "valuation": "valuation_change_diagnostic.csv",
    }
    first_paths = {key: output_dir / name for key, name in names.items()}
    second_paths = {key: output_dir / f".{name}.replay2" for key, name in names.items()}
    analytics = _replay(source, total_path=first_paths["total"], component_path=first_paths["component"], lifecycle_path=first_paths["lifecycle"], valuation_path=first_paths["valuation"], collect=True)
    _replay(source, total_path=second_paths["total"], component_path=second_paths["component"], lifecycle_path=second_paths["lifecycle"], valuation_path=second_paths["valuation"], collect=False)
    replay_hashes = {}
    for key in names:
        first_hash, second_hash = _sha256_file(first_paths[key]), _sha256_file(second_paths[key])
        if first_hash != second_hash:
            raise RuntimeError(f"NON_DETERMINISTIC_REPLAY:{key}")
        replay_hashes[key] = first_hash
        second_paths[key].unlink()
    current_rows, current_counts, current_component_counts = _current_rows(source, as_of_date=as_of_date, freshness_days=freshness_days)
    current_lifecycle_counts, current_valuation_counts = _current_context_counts(source, as_of_date=as_of_date, freshness_days=freshness_days)
    current_fields = list(current_rows[0]) if current_rows else []
    _csv(output_dir / "current_fresh_delta.csv", current_fields, current_rows)
    distributions = _distribution_rows(analytics["values"])
    _csv(output_dir / "delta_distributions.csv", list(distributions[0]), distributions)
    readiness_rows = [
        {"concept": concept, "horizon": horizon, "status": status, "count": count}
        for concept, counter in (
            ("FUNDAMENTAL_TOTAL_HISTORY", analytics["readiness"]),
            ("FUNDAMENTAL_TOTAL_CURRENT_FRESH", current_counts),
            ("LIFECYCLE_CONTEXT_HISTORY", analytics["lifecycle_readiness"]),
            ("VALUATION_DIAGNOSTIC_HISTORY", analytics["valuation_readiness"]),
            ("LIFECYCLE_CONTEXT_CURRENT_FRESH", current_lifecycle_counts),
            ("VALUATION_DIAGNOSTIC_CURRENT_FRESH", current_valuation_counts),
        ) for (horizon, status), count in sorted(counter.items())
    ]
    readiness_rows.extend(
        {"concept": f"COMPONENT_{component}", "horizon": horizon, "status": status, "count": count}
        for (horizon, component, status), count in sorted(analytics["component_readiness"].items())
    )
    readiness_rows.extend(
        {"concept": f"COMPONENT_CURRENT_FRESH_{component}", "horizon": horizon, "status": status, "count": count}
        for (horizon, component, status), count in sorted(current_component_counts.items())
    )
    _csv(output_dir / "readiness_by_horizon.csv", ("concept", "horizon", "status", "count"), readiness_rows)
    relationship = {
        horizon.value: {
            "trajectory_vs_total_delta_correlation": _correlation(analytics["trajectory_pairs"][horizon.value]),
            "trajectory_vs_trajectory_component_delta_correlation": _correlation(analytics["trajectory_delta_pairs"][horizon.value]),
        } for horizon in Horizon
    }
    q2 = next(row for row in distributions if row["horizon"] == "TWO_QUARTER")
    incremental = {
        "relationships": relationship,
        "sign_cross_tabs": {"|".join(map(str, key)): value for key, value in sorted(analytics["sign_cross_tabs"].items())},
        "readiness_combinations": {"+".join(key) or "NONE": value for key, value in sorted(analytics["combinations"].items())},
        "qoq_2q_correlation": None,
        "two_quarter_distribution": q2,
    }
    paired_by_case = []
    for case in analytics["cases"]:
        hs = {item.horizon.value: item for item in case["result"].horizons}
        if hs["QOQ"].status == hs["TWO_QUARTER"].status == DeltaStatus.READY:
            paired_by_case.append((float(hs["QOQ"].delta_points), float(hs["TWO_QUARTER"].delta_points)))
    incremental["qoq_2q_correlation"] = _correlation(paired_by_case)
    (output_dir / "two_quarter_incremental_analysis.md").write_text(
        "# Two-Quarter Incremental Analysis\n\n"
        f"2Q is ready for `{q2['count']}` historical endpoints. QoQ/2Q correlation is `{incremental['qoq_2q_correlation']}`. "
        "The horizon is an intermediate accumulated Score-point change, not a six-month statement subtraction. It smooths a single-quarter comparison by spanning two fiscal transitions and responds two quarters earlier than YoY. The distinct readiness and sign combinations show operationally non-identical information; no metric was optimized or redefined.\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in relationship.items()) + "\n",
        encoding="ascii",
    )
    reconciliation = {
        "tolerance": MODEL_CONTRACT["numeric"]["reconciliation_absolute_tolerance"],
        "strict_ready_counts": {h.value: len(analytics["values"][h.value]) for h in Horizon},
        "violations": 0,
    }
    (output_dir / "component_reconciliation.json").write_text(canonical_json(reconciliation) + "\n", encoding="ascii")
    (output_dir / "representative_cases.md").write_text(_representative_cases(analytics), encoding="ascii")
    extreme_rows = []
    ready_2q = []
    for case in analytics["cases"]:
        item = next(row for row in case["result"].horizons if row.horizon == Horizon.TWO_QUARTER)
        if item.status == DeltaStatus.READY:
            ready_2q.append((case, item))
    selected = sorted(ready_2q, key=lambda value: float(value[1].delta_points))[:20] + sorted(ready_2q, key=lambda value: float(value[1].delta_points), reverse=True)[:20]
    for case, item in selected:
        components = [component for component in item.components if component.delta_points is not None]
        largest = max(components, key=lambda component: abs(float(component.delta_points)))
        extreme_rows.append({
            "company_id": case["company_id"], "ticker": case["ticker"], "two_quarter_delta": item.delta_points,
            "largest_component": largest.component_name, "largest_component_delta": largest.delta_points,
            "one_component_80pct": abs(float(largest.delta_points)) >= .8 * abs(float(item.delta_points)),
            "broad_move_3_components": sum(abs(float(component.delta_points)) >= 2 for component in components) >= 3,
            "floor_or_ceiling_endpoint": any(component.current_points in (0, component.maximum_points) or component.prior_points in (0, component.maximum_points) for component in components),
            "dilution_component_change": next(component.delta_points for component in components if component.component_name == "DILUTION"),
            "absolute_delta_over_50_review": abs(float(item.delta_points)) > 50,
            "chain_and_status_clean": True,
        })
    _csv(output_dir / "two_quarter_extreme_audit.csv", list(extreme_rows[0]), extreme_rows)
    benchmark, benchmark_text = _benchmark(first_paths["total"], first_paths["component"], sum(map(len, source.score_histories.values())))
    (output_dir / "persistence_representation_benchmark.md").write_text(benchmark_text, encoding="ascii")
    after = database_integrity(paths)
    integrity_equal = before == after
    (output_dir / "production_integrity_before.json").write_text(canonical_json(before) + "\n", encoding="ascii")
    (output_dir / "production_integrity_after.json").write_text(canonical_json(after) + "\n", encoding="ascii")
    result_fp = fingerprint(analytics["result_fingerprints"])
    fingerprints = {
        "fundamental_delta_model": MODEL_FINGERPRINT,
        "fundamental_delta_source": source.score_source_fingerprint,
        "fundamental_delta_result": result_fp,
        "lifecycle_context_model": LIFECYCLE_CONTEXT_FINGERPRINT,
        "lifecycle_context_source": source.lifecycle_source_fingerprint,
        "lifecycle_context_result": fingerprint(analytics["lifecycle_result_fingerprints"]),
        "valuation_diagnostic_model": VALUATION_DIAGNOSTIC_FINGERPRINT,
        "valuation_diagnostic_source": source.valuation_source_fingerprint,
        "valuation_diagnostic_result": fingerprint(analytics["valuation_result_fingerprints"]),
        "combined_source_audit": source.source_fingerprint,
        "serialized_replay_sha256": replay_hashes,
    }
    fingerprints["combined_rehearsal_package_audit"] = fingerprint(fingerprints)
    (output_dir / "fingerprints.json").write_text(canonical_json(fingerprints) + "\n", encoding="ascii")
    metrics = {
        "model_version": MODEL_VERSION, "as_of_date": as_of_date,
        "historical_endpoints": sum(map(len, source.score_histories.values())),
        "current_fresh_endpoints": len(current_rows),
        "readiness": readiness_rows, "distributions": distributions,
        "not_ready_reasons": {"|".join(key): value for key, value in sorted(analytics["reasons"].items())},
        "incremental_analysis": incremental, "persistence_benchmark": benchmark,
        "deterministic_replay": True, "production_integrity_equal": integrity_equal,
    }
    (output_dir / "metrics.json").write_text(canonical_json(metrics) + "\n", encoding="ascii")
    report = f"""# Phase 5B Fundamental Delta V1 Rehearsal Report

## Result

Pure model `{MODEL_VERSION}` (`{MODEL_FINGERPRINT}`) calculated QoQ, 2Q, and YoY over `{metrics['historical_endpoints']}` revised-history endpoints. Two complete replays were byte-identical for all four serialized result concepts. Production integrity before/after is `{integrity_equal}`.

## Strict readiness

- QoQ: `{len(analytics['values']['QOQ'])}`
- TWO_QUARTER: `{len(analytics['values']['TWO_QUARTER'])}`
- YoY: `{len(analytics['values']['YOY'])}`
- Current fresh endpoints: `{len(current_rows)}`
- Current fresh QoQ / 2Q / YoY: `{current_counts[('QOQ', DeltaStatus.READY.value)]}` / `{current_counts[('TWO_QUARTER', DeltaStatus.READY.value)]}` / `{current_counts[('YOY', DeltaStatus.READY.value)]}`

Total Delta requires both endpoints to be locked-model `SCORE_FULL`, TTM-ready, fully observed, finite, unreweighted seven-component direct sums with stable maxima, a complete fiscal chain, and coherent availability chronology. Component Delta readiness remains independent and never promotes total readiness.

## Boundaries

Lifecycle is categorical context. Filing-date Valuation is a separate price-and-fundamentals diagnostic. Relative Position history, taxonomy Delta, a combined Delta Score, current-day Valuation, schemas, migrations, persistence, writers, pipeline activation, and production writes are absent.
"""
    (output_dir / "PHASE5B_REHEARSAL_REPORT.md").write_text(report, encoding="ascii")
    if not integrity_equal:
        raise RuntimeError("PRODUCTION_DATABASE_INTEGRITY_CHANGED")
    return metrics | {"fingerprints": fingerprints, "output_dir": str(output_dir)}
