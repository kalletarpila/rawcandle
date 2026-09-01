from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    PeerScope,
    RelativeMeasure,
    RelativeObservation,
    RelativePositionResult,
    RelativeSnapshot,
    RelativeStatus,
    calculate_snapshot,
)
from rawcandle.fundamentals.relative_position.source import (
    DEFAULT_FRESHNESS_DAYS,
    ReadOnlySourcePaths,
    load_current_relative_source,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _group_statistics(snapshot: RelativeSnapshot) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[RelativePositionResult]] = defaultdict(list)
    for result in snapshot.results:
        grouped[(result.measure.value, result.peer_scope.value, result.peer_group_id)].append(result)
    output: list[dict[str, Any]] = []
    for (measure, scope, group_id), rows in sorted(grouped.items()):
        scores = [row.score for row in rows]
        output.append({
            "measure": measure,
            "peer_scope": scope,
            "peer_group_id": group_id,
            "peer_count": len(rows),
            "distinct_score_count": len(set(scores)),
            "ready_count": sum(row.status == RelativeStatus.READY for row in rows),
            "too_small_count": sum(
                row.status == RelativeStatus.PEER_GROUP_TOO_SMALL for row in rows
            ),
            "exact_zero_count": sum(score == 0.0 for score in scores),
            "exact_100_count": sum(score == 100.0 for score in scores),
            "largest_tie": max(row.tie_count for row in rows),
        })
    return output


def _case_payload(
    ticker: str,
    observations: Sequence[RelativeObservation],
    snapshot: RelativeSnapshot,
) -> dict[str, Any]:
    company_ids = {
        observation.company_id
        for observation in observations
        if observation.ticker == ticker and observation.company_id is not None
    }
    return {
        "ticker": ticker,
        "company_ids": sorted(company_ids),
        "source": [
            asdict(observation)
            for observation in observations
            if observation.company_id in company_ids
        ],
        "results": [
            result.to_dict()
            for result in snapshot.results
            if result.company_id in company_ids
        ],
        "coverage": [
            record.to_dict()
            for record in snapshot.coverage
            if record.company_id in company_ids
        ],
    }


def _representative_cases(
    observations: Sequence[RelativeObservation],
    snapshot: RelativeSnapshot,
) -> dict[str, Any]:
    requested = {
        "high_fundamental_high_valuation": "INSW",
        "high_fundamental_low_valuation": "SITM",
        "low_fundamental_high_valuation": "HOV",
        "valuation_zero_tie": "NNDM",
        "valuation_100_tie": "IRWD",
        "small_industry": "AIN",
        "missing_or_unavailable": "LION",
        "ecosystem_member": "SITM",
        "multiple_taxonomy_memberships": "VRT",
        "valuation_not_applicable": "O",
        "crmd": "CRMD",
    }
    roles_by_company: dict[int, set[str]] = defaultdict(set)
    ticker_by_company: dict[int, str] = {}
    for observation in observations:
        if observation.company_id is None:
            continue
        ticker_by_company[observation.company_id] = observation.ticker or ""
        roles_by_company[observation.company_id].update(
            membership.role.strip().upper()
            for membership in observation.ecosystem_memberships
        )
    watch_only = sorted(
        ticker_by_company[company_id]
        for company_id, roles in roles_by_company.items()
        if roles == {"WATCH_ONLY"} and ticker_by_company[company_id]
    )
    if watch_only:
        requested["watch_only_exclusion"] = watch_only[0]
    return {
        label: _case_payload(ticker, observations, snapshot)
        for label, ticker in requested.items()
    }


def _summary(
    source_metadata: Mapping[str, Any],
    snapshot: RelativeSnapshot,
    *,
    replay_sha256: str,
    replay_bytes_identical: bool,
) -> dict[str, Any]:
    ready_counts = Counter(
        (result.measure.value, result.peer_scope.value)
        for result in snapshot.results
        if result.status == RelativeStatus.READY
    )
    unavailable_counts = Counter(
        (record.measure.value, record.peer_scope.value, record.status.value)
        for record in snapshot.coverage
        if record.status != RelativeStatus.READY
    )
    group_rows = _group_statistics(snapshot)
    below_minimum = [row for row in group_rows if row["too_small_count"] > 0]
    tie_blocks: Counter[tuple[str, str]] = Counter()
    seen_ties: set[tuple[str, str, str, float]] = set()
    for result in snapshot.results:
        key = (
            result.measure.value,
            result.peer_scope.value,
            result.peer_group_id,
            result.score,
        )
        if result.tie_count > 1 and key not in seen_ties:
            tie_blocks[(result.measure.value, result.peer_scope.value)] += 1
            seen_ties.add(key)
    crmd = [
        result.to_dict()
        for result in snapshot.results
        if result.ticker == "CRMD"
        and result.measure == RelativeMeasure.ABSOLUTE_VALUATION_SCORE
    ]
    valuation_universe = [
        result for result in snapshot.results
        if result.measure == RelativeMeasure.ABSOLUTE_VALUATION_SCORE
        and result.peer_scope == PeerScope.UNIVERSE
    ]
    return {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "semantic_mode": snapshot.semantic_mode,
        "snapshot_date": snapshot.snapshot_date,
        "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint,
        "replay_sha256": replay_sha256,
        "replay_bytes_identical": replay_bytes_identical,
        "source": dict(source_metadata),
        "result_rows": len(snapshot.results),
        "coverage_rows": len(snapshot.coverage),
        "ready_counts": {
            f"{measure}:{scope}": count
            for (measure, scope), count in sorted(ready_counts.items())
        },
        "unavailable_counts": {
            f"{measure}:{scope}:{status}": count
            for (measure, scope, status), count in sorted(unavailable_counts.items())
        },
        "peer_groups": group_rows,
        "peer_groups_below_minimum": below_minimum,
        "tie_block_counts": {
            f"{measure}:{scope}": count
            for (measure, scope), count in sorted(tie_blocks.items())
        },
        "valuation_universe_exact_zero": {
            "companies": sum(result.score == 0.0 for result in valuation_universe),
            "percentiles": sorted({
                result.percentile for result in valuation_universe if result.score == 0.0
            }),
            "tie_counts": sorted({
                result.tie_count for result in valuation_universe if result.score == 0.0
            }),
        },
        "valuation_universe_exact_100": {
            "companies": sum(result.score == 100.0 for result in valuation_universe),
            "percentiles": sorted({
                result.percentile for result in valuation_universe if result.score == 100.0
            }),
            "tie_counts": sorted({
                result.tie_count for result in valuation_universe if result.score == 100.0
            }),
        },
        "crmd_valuation": crmd,
        "taxonomy_layer_scope_present": any(
            result.peer_scope.value == "TAXONOMY_LAYER" for result in snapshot.results
        ),
    }


def run_full_universe_rehearsal(
    paths: ReadOnlySourcePaths,
    *,
    as_of_date: str,
    output_dir: Path,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    source_paths = {
        path.resolve() for path in (
            paths.analysis_db, paths.canonical_db, paths.market_db, paths.taxonomy_db
        )
    }
    if output_dir in source_paths:
        raise ValueError("OUTPUT_DIRECTORY_CANNOT_BE_A_SOURCE_DATABASE")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = load_current_relative_source(
        paths, as_of_date=as_of_date, freshness_days=freshness_days
    )
    arguments = {
        "snapshot_date": as_of_date,
        "freshness_days": freshness_days,
        "classification_fingerprint": source.classification_fingerprint,
        "taxonomy_fingerprint": source.taxonomy_fingerprint,
    }
    first = calculate_snapshot(source.observations, **arguments)
    second = calculate_snapshot(source.observations, **arguments)
    first_bytes = (first.to_json() + "\n").encode("ascii")
    second_bytes = (second.to_json() + "\n").encode("ascii")
    identical = first_bytes == second_bytes
    if not identical:
        raise RuntimeError("RELATIVE_POSITION_REPLAY_NOT_BYTE_IDENTICAL")
    replay_sha256 = _sha256_bytes(first_bytes)
    (output_dir / "relative_snapshot_run1.json").write_bytes(first_bytes)
    (output_dir / "relative_snapshot_run2.json").write_bytes(second_bytes)

    result_rows = [result.to_dict() for result in first.results]
    coverage_rows = [record.to_dict() for record in first.coverage]
    _write_csv(
        output_dir / "relative_positions.csv",
        result_rows,
        tuple(result_rows[0]) if result_rows else (),
    )
    _write_csv(
        output_dir / "relative_position_coverage.csv",
        coverage_rows,
        tuple(coverage_rows[0]) if coverage_rows else (),
    )
    taxonomy_fields = tuple(source.taxonomy_audit[0]) if source.taxonomy_audit else ()
    _write_csv(
        output_dir / "taxonomy_mapping_audit.csv",
        source.taxonomy_audit,
        taxonomy_fields,
    )
    cases = _representative_cases(source.observations, first)
    (output_dir / "representative_cases.json").write_text(
        json.dumps(cases, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = _summary(
        source.metadata,
        first,
        replay_sha256=replay_sha256,
        replay_bytes_identical=identical,
    )
    (output_dir / "rehearsal_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary
