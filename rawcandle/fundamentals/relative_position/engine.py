from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import Enum
from numbers import Real
from typing import Any, Iterable, Sequence


MODEL_VERSION = "CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V1"
CURRENT_FRESHNESS_DAYS = 180


class RelativeMeasure(str, Enum):
    FUNDAMENTAL_SCORE = "FUNDAMENTAL_SCORE"
    ABSOLUTE_VALUATION_SCORE = "ABSOLUTE_VALUATION_SCORE"


class PeerScope(str, Enum):
    UNIVERSE = "UNIVERSE"
    SECTOR = "SECTOR"
    INDUSTRY = "INDUSTRY"
    ECOSYSTEM = "ECOSYSTEM"


class RelativeStatus(str, Enum):
    READY = "RELATIVE_POSITION_READY"
    SOURCE_NOT_ELIGIBLE = "SOURCE_MEASURE_NOT_ELIGIBLE"
    CLASSIFICATION_MISSING = "PEER_CLASSIFICATION_MISSING"
    NOT_ECOSYSTEM_MEMBER = "NOT_ECOSYSTEM_MEMBER"
    PEER_GROUP_TOO_SMALL = "PEER_GROUP_TOO_SMALL"
    INVALID_SOURCE_VALUE = "INVALID_SOURCE_VALUE"
    IDENTITY_MAPPING_UNRESOLVED = "IDENTITY_MAPPING_UNRESOLVED"


MINIMUM_PEERS = {
    PeerScope.UNIVERSE: 2,
    PeerScope.SECTOR: 20,
    PeerScope.INDUSTRY: 10,
    PeerScope.ECOSYSTEM: 20,
}
QUALIFYING_ECOSYSTEM_ROLES = frozenset({"CORE", "EXTENDED"})
ELIGIBLE_SOURCE_STATUSES = {
    RelativeMeasure.FUNDAMENTAL_SCORE: "SCORE_FULL",
    RelativeMeasure.ABSOLUTE_VALUATION_SCORE: "VALUATION_FULL",
}
MISSING_CLASSIFICATION_VALUES = frozenset(
    {"", "null", "none", "n/a", "na", "unknown", "unclassified"}
)

MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "semantic_mode": "CURRENT_REVISED_SNAPSHOT",
    "measures": [measure.value for measure in RelativeMeasure],
    "peer_scopes": [scope.value for scope in PeerScope],
    "eligibility": {
        "observation_selection": "latest_available_on_or_before_snapshot_per_company_and_measure",
        "maximum_age_calendar_days": CURRENT_FRESHNESS_DAYS,
        "fundamental_required_status": "SCORE_FULL",
        "valuation_required_status": "VALUATION_FULL",
        "measure_denominators": "independent",
    },
    "classification": {
        "sector_and_industry": "current_snapshot_ticker_meta",
        "historical_pit": False,
    },
    "percentile": {
        "direction": "ascending_higher_score_is_higher_percentile",
        "rank": "average_rank_midrank_for_exact_ties",
        "formula": "100*(average_rank-1)/(peer_count-1)",
        "scale": "0_to_100",
        "rounding": None,
        "nonfinite": "invalid_source_value",
        "boolean": "invalid_source_value",
    },
    "minimum_peers": {scope.value: count for scope, count in MINIMUM_PEERS.items()},
    "ecosystem": {
        "qualifying_roles": sorted(QUALIFYING_ECOSYSTEM_ROLES),
        "company_deduplication": "once_per_measure_and_ecosystem",
        "watch_only": "excluded",
        "taxonomy_layer_ranking": False,
    },
    "fallback": None,
    "imputation": None,
    "cross_measure_denominator": False,
    "statuses": [status.value for status in RelativeStatus],
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


MODEL_FINGERPRINT = _hash(MODEL_CONTRACT)


@dataclass(frozen=True)
class EcosystemMembership:
    ecosystem_id: str
    role: str
    membership_id: str | None = None


@dataclass(frozen=True)
class RelativeObservation:
    source_observation_id: str
    company_id: int | None
    security_id: int | None
    ticker: str | None
    measure: RelativeMeasure
    score: Any
    source_status: str
    source_eligible: bool
    eligibility_reason: str
    source_observation_date: str | None
    source_model_version: str
    source_model_fingerprint: str
    source_result_fingerprint: str
    sector: str | None = None
    industry: str | None = None
    ecosystem_memberships: tuple[EcosystemMembership, ...] = ()


@dataclass(frozen=True)
class RelativePositionResult:
    model_version: str
    model_fingerprint: str
    snapshot_date: str
    source_fingerprint: str
    company_id: int
    security_id: int | None
    ticker: str | None
    measure: RelativeMeasure
    peer_scope: PeerScope
    peer_group_id: str
    source_observation_id: str
    source_observation_date: str
    score: float
    percentile: float | None
    rank_low: int
    rank_high: int
    average_rank: float
    peer_count: int
    tie_count: int
    status: RelativeStatus
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageRecord:
    snapshot_date: str
    source_observation_id: str
    company_id: int | None
    measure: RelativeMeasure
    peer_scope: PeerScope
    peer_group_id: str | None
    status: RelativeStatus
    reason_code: str
    peer_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelativeSnapshot:
    model_version: str
    model_fingerprint: str
    semantic_mode: str
    snapshot_date: str
    source_fingerprint: str
    result_fingerprint: str
    results: tuple[RelativePositionResult, ...]
    coverage: tuple[CoverageRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def _result_fingerprint_payload(
    *,
    snapshot_date: str,
    source_fingerprint: str,
    results: Sequence[RelativePositionResult],
    coverage: Sequence[CoverageRecord],
) -> dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "semantic_mode": "CURRENT_REVISED_SNAPSHOT",
        "snapshot_date": snapshot_date,
        "source_fingerprint": source_fingerprint,
        "results": [result.to_dict() for result in results],
        "coverage": [record.to_dict() for record in coverage],
    }


def recalculate_result_fingerprint(snapshot: RelativeSnapshot) -> str:
    return _hash(_result_fingerprint_payload(
        snapshot_date=snapshot.snapshot_date,
        source_fingerprint=snapshot.source_fingerprint,
        results=snapshot.results,
        coverage=snapshot.coverage,
    ))


def normalize_classification(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return None if normalized.casefold() in MISSING_CLASSIFICATION_VALUES else normalized


def _observation_payload(observation: RelativeObservation) -> dict[str, Any]:
    def fingerprint_safe(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return {"non_finite": str(value)}
        if isinstance(value, dict):
            return {key: fingerprint_safe(child) for key, child in value.items()}
        if isinstance(value, (list, tuple)):
            return [fingerprint_safe(child) for child in value]
        return value

    payload = fingerprint_safe(asdict(observation))
    payload["ecosystem_memberships"] = sorted(
        payload["ecosystem_memberships"],
        key=lambda item: (
            item["ecosystem_id"], item["role"], item["membership_id"] or ""
        ),
    )
    return payload


def source_fingerprint(
    observations: Sequence[RelativeObservation],
    *,
    snapshot_date: str,
    freshness_days: int,
    classification_fingerprint: str,
    taxonomy_fingerprint: str,
) -> str:
    payload = {
        "snapshot_date": snapshot_date,
        "freshness_days": freshness_days,
        "classification_fingerprint": classification_fingerprint,
        "taxonomy_fingerprint": taxonomy_fingerprint,
        "observations": sorted(
            (_observation_payload(observation) for observation in observations),
            key=lambda item: (
                item["measure"],
                item["company_id"] if item["company_id"] is not None else -1,
                item["source_observation_id"],
            ),
        ),
    }
    return _hash(payload)


def _numeric_score(value: Any) -> tuple[float | None, str | None]:
    if value is None:
        return None, "SOURCE_SCORE_MISSING"
    if isinstance(value, bool):
        return None, "SOURCE_SCORE_BOOLEAN"
    if not isinstance(value, Real):
        return None, "SOURCE_SCORE_NOT_NUMERIC"
    number = float(value)
    if not math.isfinite(number):
        return None, "SOURCE_SCORE_NONFINITE"
    if not 0.0 <= number <= 100.0:
        return None, "SOURCE_SCORE_OUT_OF_RANGE"
    return number, None


def _qualifying_ecosystems(observation: RelativeObservation) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                membership.ecosystem_id.strip()
                for membership in observation.ecosystem_memberships
                if membership.ecosystem_id.strip()
                and membership.role.strip().upper() in QUALIFYING_ECOSYSTEM_ROLES
            }
        )
    )


def _coverage(
    observation: RelativeObservation,
    snapshot_date: str,
    scope: PeerScope,
    status: RelativeStatus,
    reason_code: str,
    *,
    group_id: str | None = None,
    peer_count: int | None = None,
) -> CoverageRecord:
    return CoverageRecord(
        snapshot_date=snapshot_date,
        source_observation_id=observation.source_observation_id,
        company_id=observation.company_id,
        measure=observation.measure,
        peer_scope=scope,
        peer_group_id=group_id,
        status=status,
        reason_code=reason_code,
        peer_count=peer_count,
    )


def _result_sort_key(result: RelativePositionResult) -> tuple[str, str, str, int]:
    return (
        result.measure.value,
        result.peer_scope.value,
        result.peer_group_id,
        result.company_id,
    )


def _coverage_sort_key(record: CoverageRecord) -> tuple[str, int, str, str, str]:
    return (
        record.measure.value,
        record.company_id if record.company_id is not None else -1,
        record.peer_scope.value,
        record.peer_group_id or "",
        record.source_observation_id,
    )


def _validate_observation_identities(observations: Iterable[RelativeObservation]) -> None:
    source_ids: set[str] = set()
    company_measures: set[tuple[int, RelativeMeasure]] = set()
    for observation in observations:
        if not observation.source_observation_id:
            raise ValueError("SOURCE_OBSERVATION_ID_REQUIRED")
        if observation.source_observation_id in source_ids:
            raise ValueError(
                f"DUPLICATE_SOURCE_OBSERVATION:{observation.source_observation_id}"
            )
        source_ids.add(observation.source_observation_id)
        if observation.company_id is None:
            continue
        if isinstance(observation.company_id, bool) or observation.company_id <= 0:
            raise ValueError(f"INVALID_COMPANY_ID:{observation.company_id}")
        identity = (observation.company_id, observation.measure)
        if identity in company_measures:
            raise ValueError(
                f"DUPLICATE_COMPANY_MEASURE:{observation.company_id}:{observation.measure.value}"
            )
        company_measures.add(identity)


def calculate_snapshot(
    observations: Sequence[RelativeObservation],
    *,
    snapshot_date: str,
    freshness_days: int,
    classification_fingerprint: str,
    taxonomy_fingerprint: str,
) -> RelativeSnapshot:
    if freshness_days != CURRENT_FRESHNESS_DAYS:
        raise ValueError(
            f"RELATIVE_POSITION_FRESHNESS_MUST_BE_{CURRENT_FRESHNESS_DAYS}_DAYS"
        )
    try:
        snapshot_day = date.fromisoformat(snapshot_date)
    except ValueError as exc:
        raise ValueError("INVALID_SNAPSHOT_DATE") from exc
    _validate_observation_identities(observations)
    ordered_observations = sorted(
        observations,
        key=lambda item: (
            item.measure.value,
            item.company_id if item.company_id is not None else -1,
            item.source_observation_id,
        ),
    )
    source_fp = source_fingerprint(
        ordered_observations,
        snapshot_date=snapshot_date,
        freshness_days=freshness_days,
        classification_fingerprint=classification_fingerprint,
        taxonomy_fingerprint=taxonomy_fingerprint,
    )

    groups: dict[
        tuple[RelativeMeasure, PeerScope, str], dict[int, tuple[RelativeObservation, float]]
    ] = defaultdict(dict)
    coverage: list[CoverageRecord] = []

    for observation in ordered_observations:
        if observation.company_id is None:
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.IDENTITY_MAPPING_UNRESOLVED,
                        "COMPANY_ID_UNRESOLVED",
                    )
                )
            continue
        required_status = ELIGIBLE_SOURCE_STATUSES[observation.measure]
        if not observation.source_eligible or observation.source_status != required_status:
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.SOURCE_NOT_ELIGIBLE,
                        observation.eligibility_reason
                        if not observation.source_eligible
                        else f"SOURCE_STATUS_NOT_ELIGIBLE:{observation.source_status}",
                    )
                )
            continue
        score, invalid_reason = _numeric_score(observation.score)
        if invalid_reason is not None:
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.INVALID_SOURCE_VALUE,
                        invalid_reason,
                    )
                )
            continue
        if not observation.source_observation_date:
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.INVALID_SOURCE_VALUE,
                        "SOURCE_OBSERVATION_DATE_MISSING",
                    )
                )
            continue
        try:
            observation_day = date.fromisoformat(observation.source_observation_date)
        except ValueError:
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.INVALID_SOURCE_VALUE,
                        "SOURCE_OBSERVATION_DATE_INVALID",
                    )
                )
            continue
        age_days = (snapshot_day - observation_day).days
        if age_days < 0 or age_days > freshness_days:
            reason = (
                "SOURCE_OBSERVATION_AFTER_SNAPSHOT"
                if age_days < 0
                else "SOURCE_OBSERVATION_STALE"
            )
            for scope in PeerScope:
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        RelativeStatus.SOURCE_NOT_ELIGIBLE,
                        reason,
                    )
                )
            continue
        assert score is not None
        groups[(observation.measure, PeerScope.UNIVERSE, "ALL")][
            observation.company_id
        ] = (observation, score)

        sector = normalize_classification(observation.sector)
        if sector is None:
            coverage.append(
                _coverage(
                    observation,
                    snapshot_date,
                    PeerScope.SECTOR,
                    RelativeStatus.CLASSIFICATION_MISSING,
                    "SECTOR_MISSING",
                )
            )
        else:
            groups[(observation.measure, PeerScope.SECTOR, sector)][
                observation.company_id
            ] = (observation, score)

        industry = normalize_classification(observation.industry)
        if industry is None:
            coverage.append(
                _coverage(
                    observation,
                    snapshot_date,
                    PeerScope.INDUSTRY,
                    RelativeStatus.CLASSIFICATION_MISSING,
                    "INDUSTRY_MISSING",
                )
            )
        else:
            groups[(observation.measure, PeerScope.INDUSTRY, industry)][
                observation.company_id
            ] = (observation, score)

        ecosystems = _qualifying_ecosystems(observation)
        if not ecosystems:
            coverage.append(
                _coverage(
                    observation,
                    snapshot_date,
                    PeerScope.ECOSYSTEM,
                    RelativeStatus.NOT_ECOSYSTEM_MEMBER,
                    "NO_QUALIFYING_CORE_OR_EXTENDED_MEMBERSHIP",
                )
            )
        for ecosystem_id in ecosystems:
            groups[(observation.measure, PeerScope.ECOSYSTEM, ecosystem_id)][
                observation.company_id
            ] = (observation, score)

    results: list[RelativePositionResult] = []
    for (measure, scope, group_id), members in sorted(
        groups.items(), key=lambda item: (item[0][0].value, item[0][1].value, item[0][2])
    ):
        peer_count = len(members)
        by_score: dict[float, list[tuple[int, RelativeObservation]]] = defaultdict(list)
        for company_id, (observation, score) in members.items():
            by_score[score].append((company_id, observation))
        below = 0
        for score in sorted(by_score):
            tied = sorted(by_score[score], key=lambda item: item[0])
            tie_count = len(tied)
            rank_low = below + 1
            rank_high = below + tie_count
            average_rank = (rank_low + rank_high) / 2.0
            ready = peer_count >= MINIMUM_PEERS[scope]
            percentile = (
                100.0 * (average_rank - 1.0) / (peer_count - 1.0)
                if ready
                else None
            )
            status = (
                RelativeStatus.READY if ready else RelativeStatus.PEER_GROUP_TOO_SMALL
            )
            reason = (
                "PERCENTILE_CALCULATED"
                if ready
                else "PEER_COUNT_BELOW_MINIMUM"
            )
            for company_id, observation in tied:
                assert observation.source_observation_date is not None
                result = RelativePositionResult(
                    model_version=MODEL_VERSION,
                    model_fingerprint=MODEL_FINGERPRINT,
                    snapshot_date=snapshot_date,
                    source_fingerprint=source_fp,
                    company_id=company_id,
                    security_id=observation.security_id,
                    ticker=observation.ticker,
                    measure=measure,
                    peer_scope=scope,
                    peer_group_id=group_id,
                    source_observation_id=observation.source_observation_id,
                    source_observation_date=observation.source_observation_date,
                    score=score,
                    percentile=percentile,
                    rank_low=rank_low,
                    rank_high=rank_high,
                    average_rank=average_rank,
                    peer_count=peer_count,
                    tie_count=tie_count,
                    status=status,
                    reason_code=reason,
                )
                results.append(result)
                coverage.append(
                    _coverage(
                        observation,
                        snapshot_date,
                        scope,
                        status,
                        reason,
                        group_id=group_id,
                        peer_count=peer_count,
                    )
                )
            below += tie_count

    ordered_results = tuple(sorted(results, key=_result_sort_key))
    ordered_coverage = tuple(sorted(coverage, key=_coverage_sort_key))
    provisional = RelativeSnapshot(
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        semantic_mode="CURRENT_REVISED_SNAPSHOT",
        snapshot_date=snapshot_date,
        source_fingerprint=source_fp,
        result_fingerprint="",
        results=ordered_results,
        coverage=ordered_coverage,
    )
    return replace(provisional, result_fingerprint=recalculate_result_fingerprint(provisional))
