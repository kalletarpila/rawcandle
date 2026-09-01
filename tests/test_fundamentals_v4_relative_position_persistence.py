from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT,
    EcosystemMembership,
    PeerScope,
    RelativeMeasure,
    RelativeObservation,
    RelativeStatus,
    calculate_snapshot,
    recalculate_result_fingerprint,
)
from rawcandle.fundamentals.relative_position.persistence import (
    MAX_BULK_SNAPSHOTS_PER_MODEL,
    RelativePositionRepository,
    apply_snapshot,
    ensure_schema,
    quick_check,
    schema_signature,
    source_content_fingerprint,
    validate_snapshot,
)
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL


NOW = "2026-09-01T19:00:00Z"


def observation(
    company_id: int,
    score: float | None,
    measure: RelativeMeasure,
    *,
    eligible: bool = True,
    sector: str | None = "Technology",
    memberships: tuple[EcosystemMembership, ...] = (),
) -> RelativeObservation:
    status = (
        "SCORE_FULL"
        if measure == RelativeMeasure.FUNDAMENTAL_SCORE
        else "VALUATION_FULL"
    )
    if not eligible:
        status = (
            "SCORE_NOT_READY"
            if measure == RelativeMeasure.FUNDAMENTAL_SCORE
            else "VALUATION_NOT_APPLICABLE"
        )
    return RelativeObservation(
        source_observation_id=f"{measure.value}:{company_id}",
        company_id=company_id,
        security_id=company_id,
        ticker=f"T{company_id}",
        measure=measure,
        score=score,
        source_status=status,
        source_eligible=eligible,
        eligibility_reason="ELIGIBLE" if eligible else status,
        source_observation_date="2026-08-01",
        source_model_version="SOURCE_V1",
        source_model_fingerprint="source-model",
        source_result_fingerprint=f"source-result:{measure.value}:{company_id}:{score}",
        sector=sector,
        industry="Software",
        ecosystem_memberships=memberships,
    )


def make_snapshot(*, offset: float = 0.0, snapshot_date: str = "2026-09-01"):
    membership = (EcosystemMembership("DATACENTER", "CORE"),)
    rows: list[RelativeObservation] = []
    for measure in RelativeMeasure:
        for company_id in range(1, 21):
            rows.append(observation(
                company_id,
                float(company_id) + offset,
                measure,
                memberships=membership,
            ))
        rows.append(observation(99, None, measure, eligible=False, sector=None))
    return calculate_snapshot(
        rows,
        snapshot_date=snapshot_date,
        freshness_days=180,
        classification_fingerprint="classification",
        taxonomy_fingerprint="taxonomy",
    )


def resign(snapshot):
    return replace(snapshot, result_fingerprint=recalculate_result_fingerprint(snapshot))


def database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn, applied_at_utc=NOW)
    conn.commit()
    return conn


def active_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT snapshot_id FROM relative_position_active_snapshot WHERE model_fingerprint=?",
        (MODEL_FINGERPRINT,),
    ).fetchone()
    return str(row[0]) if row else None


def test_fresh_schema_upgrade_equivalence_idempotency_and_unrelated_object() -> None:
    upgraded = sqlite3.connect(":memory:")
    upgraded.execute("CREATE TABLE unrelated(value TEXT)")
    ensure_schema(upgraded, applied_at_utc=NOW)
    first = schema_signature(upgraded)
    ensure_schema(upgraded, applied_at_utc="later")
    assert schema_signature(upgraded) == first
    assert upgraded.execute(
        "SELECT name FROM sqlite_schema WHERE name='unrelated'"
    ).fetchone()

    fresh = sqlite3.connect(":memory:")
    fresh.executescript(ANALYSIS_SCHEMA_SQL)
    assert schema_signature(fresh) == first
    assert {row[1] for row in fresh.execute("PRAGMA index_list(relative_position_result)")} >= {
        "idx_relative_position_result_company",
        "idx_relative_position_result_group",
    }


def test_first_apply_reader_and_quick_check() -> None:
    conn = database()
    snapshot = make_snapshot()
    report = apply_snapshot(conn, snapshot, applied_at_utc=NOW)
    assert report.outcome == "ACTIVATED"
    assert report.result_rows_inserted == len(snapshot.results)
    assert report.activation_changes == 1
    assert report.retained_snapshot_count == 1

    repository = RelativePositionRepository(conn)
    metadata = repository.active_metadata(model_fingerprint=MODEL_FINGERPRINT)
    assert metadata and metadata["result_fingerprint"] == snapshot.result_fingerprint
    assert metadata["validated_through_date"] == "2026-09-01"
    company = repository.current_company(1, model_fingerprint=MODEL_FINGERPRINT)
    assert len(company) == 8
    assert [(row["measure"], row["peer_scope"], row["peer_group_id"]) for row in company] == sorted(
        (row["measure"], row["peer_scope"], row["peer_group_id"]) for row in company
    )
    universe = repository.current_universe(
        model_fingerprint=MODEL_FINGERPRINT,
        measure="FUNDAMENTAL_SCORE",
        peer_scope="UNIVERSE",
    )
    assert len(universe) == 20
    assert universe[0]["peer_count"] == 20
    assert universe[0]["rank_low"] == universe[0]["rank_high"] == 1
    assert quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)["ok"]


def test_identical_and_date_only_second_apply_are_bulk_noops() -> None:
    conn = database()
    first = make_snapshot()
    initial = apply_snapshot(conn, first, applied_at_utc=NOW)
    for candidate in (first, make_snapshot(snapshot_date="2026-09-02")):
        report = apply_snapshot(conn, candidate, applied_at_utc="2026-09-02T19:00:00Z")
        assert report.outcome == "NO_CHANGE"
        assert report.result_rows_inserted == report.result_rows_deleted == 0
        assert report.activation_changes == 0
        assert report.snapshot_id == initial.snapshot_id
    metadata = RelativePositionRepository(conn).active_metadata(
        model_fingerprint=MODEL_FINGERPRINT
    )
    assert metadata and metadata["validated_through_date"] == "2026-09-02"


def test_changed_source_activation_eliminates_stale_rows_and_bounds_retention() -> None:
    conn = database()
    reports = []
    for index in range(4):
        reports.append(apply_snapshot(
            conn,
            make_snapshot(offset=float(index)),
            applied_at_utc=f"2026-09-0{index + 1}T19:00:00Z",
        ))
    assert reports[-1].activation_changes == 1
    assert reports[-1].snapshots_deleted == 1
    assert conn.execute("SELECT COUNT(*) FROM relative_position_snapshot").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(DISTINCT snapshot_id) FROM relative_position_result").fetchone()[0] == 2
    assert MAX_BULK_SNAPSHOTS_PER_MODEL == 2
    current = RelativePositionRepository(conn).company_scope(
        1,
        model_fingerprint=MODEL_FINGERPRINT,
        measure="FUNDAMENTAL_SCORE",
        peer_scope="UNIVERSE",
    )
    assert current[0]["source_score"] == 4.0
    assert quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)["ok"]


@pytest.mark.parametrize("failure", ["metadata", "results", "before_activation"])
def test_failure_before_activation_rolls_back_and_preserves_reader(failure: str) -> None:
    conn = database()
    first = make_snapshot()
    apply_snapshot(conn, first, applied_at_utc=NOW)
    old_id = active_id(conn)
    with pytest.raises(RuntimeError, match="INJECTED"):
        apply_snapshot(
            conn,
            make_snapshot(offset=1.0),
            applied_at_utc="2026-09-02T19:00:00Z",
            inject_failure_at=failure,
        )
    assert active_id(conn) == old_id
    assert RelativePositionRepository(conn).company_scope(
        1,
        model_fingerprint=MODEL_FINGERPRINT,
        measure="FUNDAMENTAL_SCORE",
        peer_scope="UNIVERSE",
    )[0]["source_score"] == 1.0
    assert quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)["ok"]


def test_cleanup_failure_rolls_back_activation_and_deletion() -> None:
    conn = database()
    apply_snapshot(conn, make_snapshot(), applied_at_utc=NOW)
    apply_snapshot(conn, make_snapshot(offset=1.0), applied_at_utc="2026-09-02T19:00:00Z")
    old_id = active_id(conn)
    with pytest.raises(RuntimeError, match="CLEANUP"):
        apply_snapshot(
            conn,
            make_snapshot(offset=2.0),
            applied_at_utc="2026-09-03T19:00:00Z",
            inject_failure_at="cleanup",
        )
    assert active_id(conn) == old_id
    assert conn.execute("SELECT COUNT(*) FROM relative_position_snapshot").fetchone()[0] == 2
    assert quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)["ok"]


def test_wrong_fingerprint_and_no_active_snapshot_return_nothing() -> None:
    conn = database()
    repository = RelativePositionRepository(conn)
    assert repository.active_metadata(model_fingerprint=MODEL_FINGERPRINT) is None
    assert repository.current_company(1, model_fingerprint="wrong") == []
    assert repository.company_scope(
        1,
        model_fingerprint="wrong",
        measure="FUNDAMENTAL_SCORE",
        peer_scope="UNIVERSE",
    ) == []


def test_unavailable_reader_distinguishes_reasons_and_never_falls_back() -> None:
    conn = database()
    apply_snapshot(conn, make_snapshot(), applied_at_utc=NOW)
    repository = RelativePositionRepository(conn)
    ecosystem = repository.explain_unavailable(
        99,
        model_fingerprint=MODEL_FINGERPRINT,
        measure="ABSOLUTE_VALUATION_SCORE",
        peer_scope="ECOSYSTEM",
    )
    assert {row["coverage_status"] for row in ecosystem} == {"SOURCE_MEASURE_NOT_ELIGIBLE"}
    assert not repository.current_universe(
        model_fingerprint=MODEL_FINGERPRINT,
        measure="FUNDAMENTAL_SCORE",
        peer_scope="TAXONOMY_LAYER",
    )


def test_unavailable_reader_distinguishes_classification_membership_and_small_group() -> None:
    conn = database()
    rows = []
    for measure in RelativeMeasure:
        rows.extend([
            observation(1, 10.0, measure, sector=None),
            observation(2, 20.0, measure, sector=None),
        ])
    snapshot = calculate_snapshot(
        rows,
        snapshot_date="2026-09-01",
        freshness_days=180,
        classification_fingerprint="classification",
        taxonomy_fingerprint="taxonomy",
    )
    apply_snapshot(conn, snapshot, applied_at_utc=NOW)
    repository = RelativePositionRepository(conn)
    cases = {
        "SECTOR": "PEER_CLASSIFICATION_MISSING",
        "INDUSTRY": "PEER_GROUP_TOO_SMALL",
        "ECOSYSTEM": "NOT_ECOSYSTEM_MEMBER",
    }
    for scope, expected in cases.items():
        rows = repository.explain_unavailable(
            1,
            model_fingerprint=MODEL_FINGERPRINT,
            measure="FUNDAMENTAL_SCORE",
            peer_scope=scope,
        )
        assert {row.get("coverage_status", row.get("result_status")) for row in rows} == {
            expected
        }


def test_schema_constraints_and_foreign_keys_reject_invalid_rows() -> None:
    conn = database()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO relative_position_active_snapshot VALUES (?,?,?)",
            (MODEL_FINGERPRINT, "missing", NOW),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO relative_position_coverage(
                   snapshot_id,source_observation_id,company_id,measure,peer_scope,
                   peer_group_id,coverage_status,reason_code,peer_count
               ) VALUES ('missing','x',1,'FUNDAMENTAL_SCORE','TAXONOMY_LAYER','x',
                         'RELATIVE_POSITION_READY','x',20)"""
        )


def test_snapshot_validator_rejects_wrong_fingerprint_partial_duplicate_and_mixed_model() -> None:
    snapshot = make_snapshot()
    with pytest.raises(ValueError, match="RESULT_FINGERPRINT"):
        validate_snapshot(replace(snapshot, result_fingerprint="wrong"))

    partial = replace(snapshot, coverage=snapshot.coverage[:-1])
    with pytest.raises(ValueError, match="PARTIAL_SOURCE_COVERAGE"):
        validate_snapshot(resign(partial))

    duplicate = replace(snapshot, results=snapshot.results + (snapshot.results[-1],))
    duplicate = replace(duplicate, results=tuple(sorted(
        duplicate.results,
        key=lambda row: (row.measure.value, row.peer_scope.value, row.peer_group_id, row.company_id),
    )))
    with pytest.raises(ValueError, match="DUPLICATE"):
        validate_snapshot(resign(duplicate))

    mixed_row = replace(snapshot.results[0], model_fingerprint="wrong")
    mixed = replace(snapshot, results=(mixed_row,) + snapshot.results[1:])
    with pytest.raises(ValueError, match="SNAPSHOT_MISMATCH"):
        validate_snapshot(resign(mixed))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("measure", "AAA_INVALID", "MEASURE_INVALID"),
        ("peer_scope", "AAA_INVALID", "SCOPE_INVALID"),
        ("status", "INVALID_STATUS", "STATUS_INVALID"),
    ],
)
def test_snapshot_validator_rejects_invalid_result_vocabulary(
    field: str, value: str, message: str
) -> None:
    snapshot = make_snapshot()
    changed = replace(snapshot.results[0], **{field: value})
    results = tuple(sorted(
        (changed,) + snapshot.results[1:],
        key=lambda row: (
            getattr(row.measure, "value", row.measure),
            getattr(row.peer_scope, "value", row.peer_scope),
            row.peer_group_id,
            row.company_id,
        ),
    ))
    with pytest.raises(ValueError, match=message):
        validate_snapshot(resign(replace(snapshot, results=results)))


def test_source_content_fingerprint_ignores_only_nominal_snapshot_date() -> None:
    first = make_snapshot()
    next_day = make_snapshot(snapshot_date="2026-09-02")
    changed = make_snapshot(offset=1.0)
    assert first.source_fingerprint != next_day.source_fingerprint
    assert first.result_fingerprint != next_day.result_fingerprint
    assert source_content_fingerprint(first) == source_content_fingerprint(next_day)
    assert source_content_fingerprint(first) != source_content_fingerprint(changed)
