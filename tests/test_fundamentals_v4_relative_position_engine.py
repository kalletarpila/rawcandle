from __future__ import annotations

import math
from dataclasses import replace

import pytest

from rawcandle.fundamentals.relative_position.engine import (
    MODEL_CONTRACT,
    MODEL_FINGERPRINT,
    EcosystemMembership,
    PeerScope,
    RelativeMeasure,
    RelativeObservation,
    RelativeStatus,
    calculate_snapshot,
)


def observation(
    company_id: int,
    score: object,
    *,
    measure: RelativeMeasure = RelativeMeasure.FUNDAMENTAL_SCORE,
    sector: str | None = "Technology",
    industry: str | None = "Software - Application",
    memberships: tuple[EcosystemMembership, ...] = (),
    eligible: bool = True,
    source_status: str = "SCORE_FULL",
) -> RelativeObservation:
    return RelativeObservation(
        source_observation_id=f"{measure.value}:{company_id}",
        company_id=company_id,
        security_id=company_id,
        ticker=f"T{company_id}",
        measure=measure,
        score=score,
        source_status=source_status,
        source_eligible=eligible,
        eligibility_reason="ELIGIBLE" if eligible else source_status,
        source_observation_date="2026-08-01",
        source_model_version="SOURCE_V1",
        source_model_fingerprint="source-model",
        source_result_fingerprint=f"source-result-{company_id}",
        sector=sector,
        industry=industry,
        ecosystem_memberships=memberships,
    )


def snapshot(rows: list[RelativeObservation]):
    return calculate_snapshot(
        rows,
        snapshot_date="2026-09-01",
        freshness_days=180,
        classification_fingerprint="classification",
        taxonomy_fingerprint="taxonomy",
    )


def results_for(result, scope: PeerScope, group: str = "ALL"):
    return [
        row for row in result.results
        if row.peer_scope == scope and row.peer_group_id == group
    ]


def test_unique_values_use_locked_endpoints_and_ignore_input_order() -> None:
    ascending = snapshot([observation(1, 10.0), observation(2, 20.0), observation(3, 30.0)])
    descending = snapshot([observation(3, 30.0), observation(2, 20.0), observation(1, 10.0)])
    rows = results_for(ascending, PeerScope.UNIVERSE)
    assert [(row.company_id, row.percentile, row.average_rank) for row in rows] == [
        (1, 0.0, 1.0), (2, 50.0, 2.0), (3, 100.0, 3.0)
    ]
    assert ascending.to_json() == descending.to_json()
    assert ascending.source_fingerprint == descending.source_fingerprint
    assert ascending.result_fingerprint == descending.result_fingerprint


def test_two_member_group_is_zero_and_100_but_one_member_is_not_ready() -> None:
    two = results_for(snapshot([observation(1, 1.0), observation(2, 2.0)]), PeerScope.UNIVERSE)
    assert [row.percentile for row in two] == [0.0, 100.0]
    one = results_for(snapshot([observation(1, 1.0)]), PeerScope.UNIVERSE)
    assert len(one) == 1
    assert one[0].status == RelativeStatus.PEER_GROUP_TOO_SMALL
    assert one[0].percentile is None
    assert one[0].peer_count == one[0].tie_count == 1


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([0.0, 0.0, 50.0], [25.0, 25.0, 100.0]),
        ([0.0, 50.0, 50.0, 100.0], [0.0, 50.0, 50.0, 100.0]),
        ([0.0, 50.0, 100.0, 100.0], [0.0, 33.333333333333336, 83.33333333333333, 83.33333333333333]),
        ([100.0, 100.0, 100.0], [50.0, 50.0, 50.0]),
        ([0.0, 0.0, 0.0, 100.0, 100.0], [25.0, 25.0, 25.0, 87.5, 87.5]),
    ],
)
def test_exact_ties_use_average_rank(values: list[float], expected: list[float]) -> None:
    result = snapshot([observation(index + 1, value) for index, value in enumerate(values)])
    rows = results_for(result, PeerScope.UNIVERSE)
    assert [row.percentile for row in rows] == pytest.approx(expected)
    by_score: dict[float, set[tuple[float, int, int]]] = {}
    for row in rows:
        by_score.setdefault(row.score, set()).add(
            (row.average_rank, row.tie_count, int(row.percentile or 0))
        )
    assert all(len(values_for_score) == 1 for values_for_score in by_score.values())


def test_floating_point_values_are_not_rounded_before_ranking() -> None:
    result = snapshot([
        observation(1, 0.1 + 0.2),
        observation(2, 0.3),
        observation(3, 0.3000000000000001),
    ])
    rows = results_for(result, PeerScope.UNIVERSE)
    assert [row.score for row in rows] == [0.30000000000000004, 0.3, 0.3000000000000001]
    assert {row.percentile for row in rows} == {0.0, 50.0, 100.0}


@pytest.mark.parametrize("value", [None, math.nan, math.inf, -math.inf, True, "5", -1.0, 101.0])
def test_invalid_source_values_are_classified_without_entering_peers(value: object) -> None:
    result = snapshot([observation(1, value)])
    assert not result.results
    assert len(result.coverage) == 4
    assert {row.status for row in result.coverage} == {RelativeStatus.INVALID_SOURCE_VALUE}


def test_source_not_eligible_and_unresolved_identity_have_explicit_audit_rows() -> None:
    limited = observation(1, 20.0, eligible=False, source_status="SCORE_LIMITED")
    unresolved = replace(observation(2, 30.0), company_id=None)
    result = snapshot([limited, unresolved])
    assert not result.results
    assert sum(row.status == RelativeStatus.SOURCE_NOT_ELIGIBLE for row in result.coverage) == 4
    assert sum(row.status == RelativeStatus.IDENTITY_MAPPING_UNRESOLVED for row in result.coverage) == 4


def test_engine_defensively_enforces_status_date_and_locked_freshness() -> None:
    wrong_status = replace(observation(1, 20.0), source_status="SCORE_LIMITED")
    stale = replace(observation(2, 30.0), source_observation_date="2026-03-04")
    result = snapshot([wrong_status, stale])
    assert not result.results
    assert sum(row.status == RelativeStatus.SOURCE_NOT_ELIGIBLE for row in result.coverage) == 8
    with pytest.raises(ValueError, match="FRESHNESS_MUST_BE_180_DAYS"):
        calculate_snapshot(
            [observation(3, 40.0)],
            snapshot_date="2026-09-01",
            freshness_days=179,
            classification_fingerprint="classification",
            taxonomy_fingerprint="taxonomy",
        )


def test_fundamental_and_valuation_denominators_are_independent() -> None:
    rows = [observation(1, 10.0), observation(2, 20.0)]
    rows += [
        observation(1, 30.0, measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE, source_status="VALUATION_FULL"),
        observation(3, 40.0, measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE, source_status="VALUATION_FULL"),
        observation(4, None, measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE, eligible=False, source_status="VALUATION_NOT_APPLICABLE"),
    ]
    result = snapshot(rows)
    fundamental = results_for(result, PeerScope.UNIVERSE)
    valuation = [row for row in fundamental if row.measure == RelativeMeasure.ABSOLUTE_VALUATION_SCORE]
    fundamental = [row for row in fundamental if row.measure == RelativeMeasure.FUNDAMENTAL_SCORE]
    assert {row.company_id for row in fundamental} == {1, 2}
    assert {row.company_id for row in valuation} == {1, 3}
    assert all(row.peer_count == 2 for row in fundamental + valuation)


@pytest.mark.parametrize(
    ("scope", "minimum", "field", "group"),
    [
        (PeerScope.SECTOR, 20, "sector", "Technology"),
        (PeerScope.INDUSTRY, 10, "industry", "Software - Application"),
        (PeerScope.ECOSYSTEM, 20, "ecosystem", "DATACENTER"),
    ],
)
def test_peer_minimum_is_exact_and_has_no_fallback(
    scope: PeerScope, minimum: int, field: str, group: str
) -> None:
    membership = (EcosystemMembership("DATACENTER", "CORE"),)
    rows = [
        observation(
            index,
            float(index),
            memberships=membership if field == "ecosystem" else (),
        )
        for index in range(1, minimum + 1)
    ]
    ready = results_for(snapshot(rows), scope, group)
    assert len(ready) == minimum
    assert {row.status for row in ready} == {RelativeStatus.READY}
    below = results_for(snapshot(rows[:-1]), scope, group)
    assert len(below) == minimum - 1
    assert {row.status for row in below} == {RelativeStatus.PEER_GROUP_TOO_SMALL}
    assert {row.percentile for row in below} == {None}
    assert all(row.peer_group_id == group for row in below)


def test_missing_classifications_and_no_membership_are_audited() -> None:
    result = snapshot([observation(1, 10.0, sector=" NULL ", industry=None)])
    statuses = {(row.peer_scope, row.status, row.reason_code) for row in result.coverage}
    assert (PeerScope.SECTOR, RelativeStatus.CLASSIFICATION_MISSING, "SECTOR_MISSING") in statuses
    assert (PeerScope.INDUSTRY, RelativeStatus.CLASSIFICATION_MISSING, "INDUSTRY_MISSING") in statuses
    assert (PeerScope.ECOSYSTEM, RelativeStatus.NOT_ECOSYSTEM_MEMBER, "NO_QUALIFYING_CORE_OR_EXTENDED_MEMBERSHIP") in statuses


def test_ecosystem_membership_is_deduplicated_and_distinct_ecosystems_are_retained() -> None:
    memberships = (
        EcosystemMembership("DATACENTER", "CORE", "layer-a"),
        EcosystemMembership("DATACENTER", "EXTENDED", "layer-b"),
        EcosystemMembership("AI", "CORE", "layer-c"),
        EcosystemMembership("DATACENTER", "CORE", "duplicate"),
    )
    rows = [observation(index, float(index), memberships=memberships) for index in range(1, 21)]
    result = snapshot(rows)
    datacenter = results_for(result, PeerScope.ECOSYSTEM, "DATACENTER")
    ai = results_for(result, PeerScope.ECOSYSTEM, "AI")
    assert len(datacenter) == len(ai) == 20
    assert {row.company_id for row in datacenter} == set(range(1, 21))
    assert all(row.peer_count == 20 for row in datacenter + ai)


def test_watch_only_is_excluded_and_taxonomy_layer_scope_does_not_exist() -> None:
    watch = (EcosystemMembership("DATACENTER", "WATCH_ONLY", "some-layer"),)
    result = snapshot([observation(1, 10.0, memberships=watch), observation(2, 20.0)])
    assert not results_for(result, PeerScope.ECOSYSTEM, "DATACENTER")
    audit = [row for row in result.coverage if row.company_id == 1 and row.peer_scope == PeerScope.ECOSYSTEM]
    assert audit[0].status == RelativeStatus.NOT_ECOSYSTEM_MEMBER
    assert {scope.value for scope in PeerScope} == {"UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"}
    assert "TAXONOMY_LAYER" not in str(MODEL_CONTRACT)


def test_duplicate_source_or_company_measure_is_rejected() -> None:
    first = observation(1, 10.0)
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_OBSERVATION"):
        snapshot([first, replace(first, company_id=2)])
    with pytest.raises(ValueError, match="DUPLICATE_COMPANY_MEASURE"):
        snapshot([first, replace(first, source_observation_id="different")])


def test_model_and_result_serialization_are_stable_and_nan_free() -> None:
    first = snapshot([observation(1, 10.0), observation(2, 20.0)])
    second = snapshot([observation(1, 10.0), observation(2, 20.0)])
    assert MODEL_FINGERPRINT == "983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2"
    assert first.to_json() == second.to_json()
    assert first.result_fingerprint == second.result_fingerprint
    assert "NaN" not in first.to_json()
