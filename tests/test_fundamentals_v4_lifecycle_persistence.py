from __future__ import annotations

import dataclasses
import inspect
import random
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_lifecycle_pit import _production_analysis_path, run
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.lifecycle.persistence import (
    PIT_MODE,
    REVISED_MODE,
    LifecycleQuarterVersion,
    LifecycleResultRepository,
    build_knowledge_batches,
    ensure_lifecycle_pit_schema,
    replay_pit_versions,
    replay_revised_history,
)


def quarter(
    index: int,
    *,
    available: str | None = None,
    revenue: float = 100.0,
    ebit: float = 10.0,
    fcf: float = 10.0,
    fingerprint: str | None = None,
    precedence: int = 0,
) -> LifecycleQuarterVersion:
    year = 2023 + (index - 1) // 4
    q = ((index - 1) % 4) + 1
    return LifecycleQuarterVersion(
        company_id=1,
        security_id=11,
        quarter_id=index,
        fiscal_year=year,
        fiscal_quarter=f"Q{q}",
        period_end=f"{year}-{q * 3:02d}-28",
        knowledge_date=available or f"2025-{index:02d}-15",
        source_version=f"VERSION_{fingerprint or index}",
        source_fingerprint=fingerprint or f"FP_{index}",
        revenue=revenue,
        ebit=ebit,
        free_cashflow=fcf,
        cash=20.0,
        total_debt=5.0,
        shares_outstanding=10.0,
        canonical_precedence=precedence,
    )


def growth_history(*, same_day_last_two: bool = False) -> list[LifecycleQuarterVersion]:
    rows = [quarter(index) for index in range(1, 9)]
    date9 = "2025-09-15"
    date10 = date9 if same_day_last_two else "2025-10-15"
    rows.append(quarter(9, available=date9, revenue=200.0, ebit=10.0, fcf=10.0))
    rows.append(quarter(10, available=date10, revenue=200.0, ebit=10.0, fcf=10.0))
    return rows


def corrected_q9(*, ebit: float = 200.0, fcf: float = 10.0) -> LifecycleQuarterVersion:
    return quarter(
        9,
        available="2025-11-15",
        revenue=200.0,
        ebit=ebit,
        fcf=fcf,
        fingerprint=f"FP_9_REVISED_{ebit}_{fcf}",
        precedence=1,
    )


def database(tmp_path: Path) -> tuple[sqlite3.Connection, LifecycleResultRepository]:
    conn = sqlite3.connect(tmp_path / "analysis.db")
    conn.row_factory = sqlite3.Row
    ensure_lifecycle_pit_schema(conn, applied_at_utc="2026-01-01T00:00:00Z")
    return conn, LifecycleResultRepository(conn)


def test_same_day_distinct_quarters_are_atomic_and_ordered_by_fiscal_sequence() -> None:
    rows = growth_history(same_day_last_two=True)
    batches = build_knowledge_batches(reversed(rows))
    final_batch = batches[-1]
    assert [row.quarter_id for row in final_batch.quarter_versions] == [9, 10]
    results = replay_pit_versions(rows, generated_at_utc="now")
    same_day = [row for row in results if row.knowledge_date == "2025-09-15"]
    assert [row.quarter_id for row in same_day] == [9, 10]
    assert same_day[0].candidate_state == "GROWTH"
    assert same_day[0].candidate_count == 1
    assert same_day[1].final_state == "GROWTH"


def test_same_day_duplicate_versions_choose_explicit_canonical_winner_once() -> None:
    low = quarter(1, available="2025-01-15", fingerprint="LOW", precedence=0)
    high = quarter(1, available="2025-01-15", fingerprint="HIGH", precedence=2)
    duplicate = dataclasses.replace(high)
    batches = build_knowledge_batches([duplicate, low, high])
    assert len(batches) == 1
    assert batches[0].quarter_versions == (high,)
    assert len(replay_pit_versions([duplicate, low, high], generated_at_utc="now")) == 1


def test_equal_precedence_conflict_fails_closed_and_order_never_breaks_tie() -> None:
    first = quarter(1, fingerprint="A")
    second = quarter(1, fingerprint="B")
    with pytest.raises(ValueError, match="WINNER_AMBIGUOUS"):
        build_knowledge_batches([first, second])


def test_input_row_order_does_not_change_deterministic_results() -> None:
    rows = growth_history(same_day_last_two=True)
    shuffled = list(rows)
    random.Random(42).shuffle(shuffled)
    first = replay_pit_versions(rows, generated_at_utc="same")
    second = replay_pit_versions(shuffled, generated_at_utc="same")
    assert first == second


def test_repeated_ingestion_of_same_source_version_is_not_confirmation() -> None:
    rows = growth_history()[:9]
    repeated = dataclasses.replace(rows[-1], knowledge_date="2025-10-15")
    results = replay_pit_versions([*rows, repeated], generated_at_utc="now")
    q9 = [row for row in results if row.quarter_id == 9]
    assert len(q9) == 1
    assert q9[0].candidate_state == "GROWTH"
    assert q9[0].candidate_count == 1


def test_restatement_replays_suffix_and_changes_later_final_state() -> None:
    rows = [*growth_history(), corrected_q9()]
    results = replay_pit_versions(rows, generated_at_utc="now")
    correction = [row for row in results if row.knowledge_date == "2025-11-15"]
    assert [row.quarter_id for row in correction] == [9, 10]
    assert correction[0].final_state == "TRANSITION"
    assert correction[0].candidate_state == "SCALING"
    assert correction[1].final_state == "SCALING"


def test_restatement_of_latest_quarter_changes_only_that_quarter() -> None:
    rows = growth_history()
    correction = dataclasses.replace(
        rows[-1],
        knowledge_date="2025-11-15",
        source_fingerprint="FP_10_REVISED",
        source_version="VERSION_10_REVISED",
        ebit=200.0,
    )
    results = replay_pit_versions([*rows, correction], generated_at_utc="now")
    revised = [row for row in results if row.knowledge_date == "2025-11-15"]
    assert [row.quarter_id for row in revised] == [10]


def test_restatement_can_trigger_immediate_distressed_entry() -> None:
    results = replay_pit_versions(
        [*growth_history(), corrected_q9(ebit=-300.0, fcf=-300.0)],
        generated_at_utc="now",
    )
    correction = [row for row in results if row.knowledge_date == "2025-11-15"]
    assert correction[0].raw_state == "DISTRESSED"
    assert correction[0].final_state == "DISTRESSED"
    assert correction[0].candidate_state is None


def test_before_and_after_restatement_asof_results_preserve_original_rows(tmp_path: Path) -> None:
    results = replay_pit_versions([*growth_history(), corrected_q9()], generated_at_utc="now")
    conn, repository = database(tmp_path)
    try:
        write = repository.append(results)
        conn.commit()
        before = repository.as_of_pit(1, "2025-10-31", model_fingerprint=MODEL_FINGERPRINT)
        after = repository.as_of_pit(1, "2025-11-15", model_fingerprint=MODEL_FINGERPRINT)
        assert before is not None and before["final_state"] == "GROWTH"
        assert after is not None and after["final_state"] == "SCALING"
        assert write["revised_version"] >= 2
        assert repository.fiscal_quarter_history(
            1, 2025, "Q1", model_fingerprint=MODEL_FINGERPRINT
        )[0]["final_state"] == "TRANSITION"
    finally:
        conn.close()


def test_period_end_never_controls_asof_visibility(tmp_path: Path) -> None:
    late = dataclasses.replace(quarter(1), period_end="2020-03-31", knowledge_date="2025-01-15")
    result = replay_pit_versions([late], generated_at_utc="now")
    conn, repository = database(tmp_path)
    try:
        repository.append(result)
        assert repository.as_of_pit(1, "2024-12-31", model_fingerprint=MODEL_FINGERPRINT) is None
        assert repository.as_of_pit(1, "2025-01-15", model_fingerprint=MODEL_FINGERPRINT) is not None
    finally:
        conn.close()


def test_append_is_idempotent_and_never_updates_original(tmp_path: Path) -> None:
    results = replay_pit_versions(growth_history(), generated_at_utc="now")
    conn, repository = database(tmp_path)
    try:
        first = repository.append(results)
        snapshot = [tuple(row) for row in conn.execute("SELECT * FROM lifecycle_pit_result ORDER BY result_id")]
        rerun = tuple(dataclasses.replace(row, generated_at_utc="later") for row in results)
        second = repository.append(rerun)
        assert first["inserted"] == len(results)
        assert second["inserted"] == 0
        assert second["duplicate_skipped"] == len(results)
        assert snapshot == [tuple(row) for row in conn.execute("SELECT * FROM lifecycle_pit_result ORDER BY result_id")]
    finally:
        conn.close()


def test_changed_model_fingerprint_and_replay_mode_coexist(tmp_path: Path) -> None:
    pit = replay_pit_versions(growth_history(), generated_at_utc="now")[-1]
    revised = replay_revised_history(
        growth_history(), as_of_date="2025-12-31", generated_at_utc="now"
    )[-1]
    other_model = dataclasses.replace(pit, result_id="OTHER_MODEL_RESULT", model_fingerprint="OTHER_MODEL")
    conn, repository = database(tmp_path)
    try:
        assert repository.append([pit, revised, other_model])["inserted"] == 3
        assert conn.execute("SELECT COUNT(DISTINCT replay_mode) FROM lifecycle_pit_result").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(DISTINCT model_fingerprint) FROM lifecycle_pit_result").fetchone()[0] == 2
    finally:
        conn.close()


def test_revised_history_is_separate_and_uses_latest_versions() -> None:
    rows = [*growth_history(), corrected_q9()]
    original = replay_revised_history(rows, as_of_date="2025-10-31", generated_at_utc="now")
    revised = replay_revised_history(rows, as_of_date="2025-11-15", generated_at_utc="now")
    assert original[-1].replay_mode == REVISED_MODE
    assert original[-1].final_state == "GROWTH"
    assert revised[-1].final_state == "SCALING"


def test_unclassified_persistence_never_publishes_last_confirmed_as_current(tmp_path: Path) -> None:
    rows = growth_history()[:8]
    missing = dataclasses.replace(
        quarter(9, revenue=200.0),
        cash=None,
        source_fingerprint="MISSING_CORE",
    )
    results = replay_pit_versions([*rows, missing], generated_at_utc="now")
    latest = results[-1]
    assert latest.raw_state == "UNCLASSIFIED"
    assert latest.lifecycle_status == "LIFECYCLE_NOT_READY"
    assert latest.final_state is None
    assert latest.last_confirmed_state == "TRANSITION"
    assert latest.candidate_state is None


def test_current_and_quarter_history_require_explicit_model_filter(tmp_path: Path) -> None:
    results = replay_pit_versions(growth_history(), generated_at_utc="now")
    conn, repository = database(tmp_path)
    try:
        repository.append(results)
        current = repository.current_pit(1, model_fingerprint=MODEL_FINGERPRINT)
        assert current is not None and current["quarter_id"] == 10
        assert repository.current_pit(1, model_fingerprint="OTHER") is None
        history = repository.fiscal_quarter_history(
            1, 2025, "Q2", model_fingerprint=MODEL_FINGERPRINT, replay_mode=PIT_MODE
        )
        assert [row["knowledge_date"] for row in history] == sorted(row["knowledge_date"] for row in history)
    finally:
        conn.close()


def test_schema_migration_is_repeatable_on_clean_and_representative_database(tmp_path: Path) -> None:
    for name, existing in (("clean.db", False), ("existing.db", True)):
        conn = sqlite3.connect(tmp_path / name)
        if existing:
            conn.execute("CREATE TABLE score_result(score_result_id INTEGER PRIMARY KEY)")
        ensure_lifecycle_pit_schema(conn, applied_at_utc="first")
        ensure_lifecycle_pit_schema(conn, applied_at_utc="second")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "lifecycle_pit_result" in tables
        assert "idx_lifecycle_pit_current" in indexes
        assert "idx_lifecycle_pit_asof" in indexes
        assert "idx_lifecycle_pit_quarter_audit" in indexes
        if existing:
            assert "score_result" in tables
        conn.close()


def test_schema_migration_rejects_incompatible_existing_pit_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "incompatible.db")
    conn.execute("CREATE TABLE lifecycle_pit_result(result_id TEXT PRIMARY KEY)")
    with pytest.raises(ValueError, match="SCHEMA_COLUMNS_MISMATCH"):
        ensure_lifecycle_pit_schema(conn, applied_at_utc="now")
    conn.close()


def test_append_rolls_back_whole_call_on_nonduplicate_constraint_error(tmp_path: Path) -> None:
    results = replay_pit_versions(growth_history(), generated_at_utc="now")
    invalid = dataclasses.replace(results[-1], result_id="INVALID_MODE", replay_mode="INVALID")
    conn, repository = database(tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            repository.append([results[0], invalid])
        assert conn.execute("SELECT COUNT(*) FROM lifecycle_pit_result").fetchone()[0] == 0
    finally:
        conn.close()


def test_repository_has_no_update_delete_or_replace_write_path() -> None:
    source = inspect.getsource(LifecycleResultRepository).upper()
    assert "UPDATE LIFECYCLE" not in source
    assert "DELETE FROM LIFECYCLE" not in source
    assert "INSERT OR REPLACE" not in source


def test_restatement_cannot_change_stable_fiscal_identity() -> None:
    changed_identity = dataclasses.replace(
        corrected_q9(), quarter_id=999, source_fingerprint="CHANGED_IDENTITY"
    )
    with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
        replay_pit_versions([*growth_history(), changed_identity], generated_at_utc="now")


def test_restatement_can_change_distressed_recovery_suffix() -> None:
    rows = [quarter(index) for index in range(1, 9)]
    rows.extend(
        [
            quarter(9, revenue=200.0, ebit=-300.0, fcf=-300.0),
            quarter(10, revenue=200.0, ebit=500.0, fcf=500.0),
            quarter(11, revenue=200.0, ebit=500.0, fcf=500.0),
        ]
    )
    correction = dataclasses.replace(
        rows[9],
        knowledge_date="2025-12-15",
        source_fingerprint="Q10_DISTRESSED_CORRECTION",
        source_version="Q10_DISTRESSED_CORRECTION",
        ebit=-300.0,
        free_cashflow=-300.0,
    )
    results = replay_pit_versions([*rows, correction], generated_at_utc="now")
    before = [row for row in results if row.knowledge_date == rows[10].knowledge_date][-1]
    after = [row for row in results if row.knowledge_date == "2025-12-15"]
    assert before.final_state == "SCALING"
    assert [row.quarter_id for row in after] == [10, 11]
    assert after[0].final_state == "DISTRESSED"
    assert after[1].final_state == "DISTRESSED"
    assert after[1].candidate_count == 1


def create_canonical_source(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE security(security_id INTEGER PRIMARY KEY, company_id INTEGER, current_ticker TEXT);
        CREATE TABLE v4_quarter(
            quarter_id INTEGER PRIMARY KEY, company_id INTEGER, fiscal_year INTEGER,
            fiscal_quarter TEXT, period_end TEXT, source_availability_date TEXT,
            identity_provider TEXT, updated_at_utc TEXT
        );
        CREATE TABLE v4_quarter_financials(
            quarter_id INTEGER PRIMARY KEY, revenue REAL, ebit REAL, free_cashflow REAL,
            cash REAL, total_debt REAL, shares_outstanding REAL, canonical_source_policy TEXT
        );
        INSERT INTO security VALUES (11, 1, 'TEST');
        """
    )
    for row in growth_history():
        conn.execute(
            "INSERT INTO v4_quarter VALUES (?,?,?,?,?,?,?,?)",
            (
                row.quarter_id,
                row.company_id,
                row.fiscal_year,
                row.fiscal_quarter,
                row.period_end,
                row.knowledge_date,
                "TEST",
                row.source_version,
            ),
        )
        conn.execute(
            "INSERT INTO v4_quarter_financials VALUES (?,?,?,?,?,?,?,?)",
            (
                row.quarter_id,
                row.revenue,
                row.ebit,
                row.free_cashflow,
                row.cash,
                row.total_debt,
                row.shares_outstanding,
                "TEST",
            ),
        )
    conn.commit()
    conn.close()


def test_cli_is_dry_run_by_default_and_writes_only_explicit_temp_destination(tmp_path: Path) -> None:
    source = tmp_path / "canonical.db"
    destination = tmp_path / "lifecycle.db"
    create_canonical_source(source)
    dry = run(source_db=source, destination_db=None, apply=False, tickers=["TEST"], generated_at_utc="now")
    assert dry["dry_run"] is True
    assert not destination.exists()
    first = run(source_db=source, destination_db=destination, apply=True, generated_at_utc="now")
    second = run(source_db=source, destination_db=destination, apply=True, generated_at_utc="now")
    assert first["write"]["inserted"] > 0  # type: ignore[index]
    assert second["write"]["inserted"] == 0  # type: ignore[index]
    assert second["write"]["duplicate_skipped"] == first["write"]["inserted"]  # type: ignore[index]


def test_cli_rejects_apply_without_destination_and_source_destination_alias(tmp_path: Path) -> None:
    source = tmp_path / "canonical.db"
    create_canonical_source(source)
    with pytest.raises(ValueError, match="DESTINATION_REQUIRED"):
        run(source_db=source, destination_db=None, apply=True)
    with pytest.raises(ValueError, match="MUST_DIFFER"):
        run(source_db=source, destination_db=source, apply=True)


def test_cli_lower_date_filter_retains_replay_seed_history(tmp_path: Path) -> None:
    source = tmp_path / "canonical.db"
    create_canonical_source(source)
    summary = run(
        source_db=source,
        destination_db=None,
        apply=False,
        knowledge_date_from="2025-09-01",
        generated_at_utc="now",
    )
    assert summary["source_quarter_versions"] == 10
    assert summary["computed_results"] == 2
    assert summary["class_counts"] == {"GROWTH": 1, "TRANSITION": 1}


def test_cli_forbids_phase_2b_production_destination_before_source_read(tmp_path: Path) -> None:
    missing_source = tmp_path / "not-needed.db"
    with pytest.raises(ValueError, match="PRODUCTION_DESTINATION_FORBIDDEN"):
        run(
            source_db=missing_source,
            destination_db=_production_analysis_path(),
            apply=True,
        )


def test_cli_rejects_invalid_knowledge_date_range_before_source_read(tmp_path: Path) -> None:
    missing_source = tmp_path / "not-needed.db"
    with pytest.raises(ValueError, match="KNOWLEDGE_DATE_RANGE_INVALID"):
        run(
            source_db=missing_source,
            destination_db=None,
            apply=False,
            knowledge_date_from="2025-12-31",
            knowledge_date_to="2025-01-01",
        )
    with pytest.raises(ValueError):
        run(
            source_db=missing_source,
            destination_db=None,
            apply=False,
            knowledge_date_from="not-a-date",
        )
