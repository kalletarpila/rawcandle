from __future__ import annotations

import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_relative_valuation_phase11c import (
    _validate, build_parser,
)
from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.relative_valuation.engine import (
    HistoricalEndpoint, RelativeValuationInput, calculate_relative_valuation,
    canonical_json,
)
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT, MAX_BULK_SNAPSHOTS, MODEL_FINGERPRINT,
    PERSISTENCE_VERSION, RelativeValuationRepository, apply_snapshot,
    ensure_schema, migrate_analysis_copy, quick_check, schema_signature,
)
from rawcandle.fundamentals.schema.migrations import ANALYSIS_SCHEMA_SQL


NOW = "2026-09-08T13:00:00Z"


def _input(company_id: int, *, as_of: str = "2026-09-08") -> RelativeValuationInput:
    history = tuple(HistoricalEndpoint(
        fiscal_sequence=index, fiscal_year=2022 + (index - 1) // 4,
        fiscal_quarter=f"Q{(index - 1) % 4 + 1}",
        available_date=f"202{2 + (index - 1) // 4}-{(index - 1) % 4 * 3 + 1:02d}-15",
        valuation_status="VALUATION_FULL", market_cap=100.0, enterprise_value=100.0,
        ttm_operating_income=float(index), ttm_free_cashflow=float(index),
        ttm_reported_common_earnings=float(index),
    ) for index in range(1, 13))
    observation = valuation.ValuationObservation(
        company_id=company_id, security_id=company_id, ticker=f"T{company_id}",
        fiscal_year=2026, fiscal_quarter="Q2", quarter_id=company_id,
        period_end="2026-06-30", fundamental_available_date="2026-08-01",
        ttm_readiness_status="TTM_READY", ttm_blocker_codes=(),
        ttm_operating_income=10.0 + company_id, ttm_free_cashflow=9.0 + company_id,
        ttm_net_income_common=8.0 + company_id, net_income_common_4q_ready=True,
        shares_outstanding=100.0, cash=0.0, total_debt=0.0,
        sector="Technology", industry="Software",
    )
    return RelativeValuationInput(
        company_id=company_id, security_id=company_id, ticker=f"T{company_id}",
        sector="Technology", industry="Software", ecosystem_memberships=(),
        endpoint_available_date="2026-08-01", current_fresh=True,
        valuation_observation=observation,
        price_bars=(valuation.PriceBar(as_of, 1.0, 1.0, 1.0, 1.0),),
        filing_valuation={"quarter_id": company_id, "total_valuation_score": 10.0},
        filing_peer_results=(), history=history,
    )


def _snapshot(*, offset: float = 0.0, as_of: str = "2026-09-08"):
    inputs = tuple(_input(company_id, as_of=as_of) for company_id in (1, 2))
    if offset:
        inputs = tuple(replace(row, valuation_observation=replace(
            row.valuation_observation,
            ttm_operating_income=row.valuation_observation.ttm_operating_income + offset,
        )) for row in inputs)
    snapshot = calculate_relative_valuation(inputs, as_of_date=as_of,
                                            classification_fingerprint="c",
                                            taxonomy_fingerprint="t")
    return snapshot, inputs


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn, applied_at_utc=NOW)
    conn.commit()
    return conn


def test_identity_schema_and_fresh_upgrade_equivalence() -> None:
    assert len(LAYOUT_FINGERPRINT) == 64 and PERSISTENCE_VERSION.endswith("V1")
    upgraded = sqlite3.connect(":memory:")
    upgraded.execute("CREATE TABLE unrelated(value TEXT)")
    ensure_schema(upgraded, applied_at_utc=NOW)
    signature = schema_signature(upgraded)
    ensure_schema(upgraded, applied_at_utc="later")
    assert schema_signature(upgraded) == signature
    fresh = sqlite3.connect(":memory:")
    fresh.executescript(ANALYSIS_SCHEMA_SQL)
    assert schema_signature(fresh) == signature
    assert fresh.execute("SELECT name FROM sqlite_schema WHERE name='relative_valuation_company_result'").fetchone()


def test_first_apply_round_trip_reader_and_true_noop() -> None:
    conn = _connection()
    snapshot, inputs = _snapshot()
    first = apply_snapshot(conn, snapshot, inputs, applied_at_utc=NOW)
    before = conn.total_changes
    second = apply_snapshot(conn, snapshot, inputs, applied_at_utc="later")
    assert first.outcome == "ACTIVATED" and first.company_rows_inserted == 2
    assert first.peer_rows_inserted == 8 and first.component_rows_inserted == 6
    assert second.outcome == "NO_CHANGE" and second.logical_bulk_writes == 0
    assert conn.total_changes == before
    repository = RelativeValuationRepository(conn)
    assert repository.active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT) == first.snapshot_id
    assert repository.previous_snapshot_id(model_fingerprint=MODEL_FINGERPRINT) is None
    company = repository.company(1, model_fingerprint=MODEL_FINGERPRINT)
    assert company and len(company["peer_positions"]) == 4 and len(company["components"]) == 3
    assert len(repository.current_universe(model_fingerprint=MODEL_FINGERPRINT)) == 2
    assert len(repository.companies((1, 2), model_fingerprint=MODEL_FINGERPRINT)) == 2
    assert quick_check(conn)["ok"]


def test_six_changed_snapshots_keep_active_and_previous_only() -> None:
    conn = _connection()
    reports = []
    for index in range(6):
        snapshot, inputs = _snapshot(offset=float(index))
        reports.append(apply_snapshot(conn, snapshot, inputs, applied_at_utc=f"2026-09-{index + 8:02d}T13:00:00Z"))
    assert reports[-1].snapshots_deleted == 1
    assert reports[-1].retained_snapshot_count == MAX_BULK_SNAPSHOTS == 2
    assert conn.execute("SELECT COUNT(DISTINCT snapshot_id) FROM relative_valuation_component_history").fetchone()[0] == 2
    repository = RelativeValuationRepository(conn)
    assert repository.previous_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
    assert quick_check(conn)["ok"]


@pytest.mark.parametrize("stage", [
    "metadata", "company", "peer", "own_history", "component", "before_reconciliation",
    "after_reconciliation", "after_activation", "cleanup",
])
def test_failure_injection_preserves_previous_active(stage: str) -> None:
    conn = _connection()
    first, first_inputs = _snapshot()
    apply_snapshot(conn, first, first_inputs, applied_at_utc=NOW)
    if stage == "cleanup":
        second, second_inputs = _snapshot(offset=1.0)
        apply_snapshot(conn, second, second_inputs, applied_at_utc="2026-09-09T13:00:00Z")
    old = RelativeValuationRepository(conn).active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
    changed, changed_inputs = _snapshot(offset=2.0)
    with pytest.raises(RuntimeError, match="INJECTED"):
        apply_snapshot(conn, changed, changed_inputs, applied_at_utc="2026-09-10T13:00:00Z", inject_failure_at=stage)
    assert RelativeValuationRepository(conn).active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT) == old
    assert quick_check(conn)["ok"]


def test_wrong_model_corrupt_result_and_source_set_are_rejected() -> None:
    snapshot, inputs = _snapshot()
    with pytest.raises(ValueError, match="MODEL_IDENTITY"):
        apply_snapshot(_connection(), replace(snapshot, model_fingerprint="wrong"), inputs, applied_at_utc=NOW)
    with pytest.raises(ValueError, match="RESULT_FINGERPRINT"):
        apply_snapshot(_connection(), replace(snapshot, result_fingerprint="wrong"), inputs, applied_at_utc=NOW)
    with pytest.raises(ValueError, match="SOURCE_COMPANY_SET"):
        apply_snapshot(_connection(), snapshot, inputs[:1], applied_at_utc=NOW)


def test_date_only_equal_bulk_uses_bounded_audit_without_rewriting() -> None:
    conn = _connection()
    snapshot, inputs = _snapshot()
    first = apply_snapshot(conn, snapshot, inputs, applied_at_utc=NOW)
    changed = replace(snapshot, as_of_date="2026-09-09", source_fingerprint="date-source")
    payload = {
        "model_version": changed.model_version, "model_fingerprint": changed.model_fingerprint,
        "semantic_mode": changed.semantic_mode, "as_of_date": changed.as_of_date,
        "source_fingerprint": changed.source_fingerprint,
        "companies": [asdict(row) for row in changed.companies],
    }
    import hashlib
    changed = replace(changed, result_fingerprint=hashlib.sha256(canonical_json(payload).encode("ascii")).hexdigest())
    report = apply_snapshot(conn, changed, inputs, applied_at_utc="2026-09-09T13:00:00Z")
    assert report.outcome == "DATE_ONLY_NO_CHANGE" and report.logical_bulk_writes == 0
    assert report.snapshot_id == first.snapshot_id
    audit = conn.execute("SELECT requested_as_of_date,outcome FROM relative_valuation_refresh_audit ORDER BY audit_id DESC LIMIT 1").fetchone()
    assert tuple(audit) == ("2026-09-09", "DATE_ONLY_NO_CHANGE")


def test_production_and_symlink_migration_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "analysis.db"
    sqlite3.connect(target).close()
    alias = tmp_path / "alias.db"
    alias.symlink_to(target)
    with pytest.raises(PermissionError):
        migrate_analysis_copy(alias, applied_at_utc=NOW)


def test_cli_defaults_dry_and_requires_safe_full_universe_destination(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    sources = []
    for name in ("canonical.db", "analysis.db", "market.db", "taxonomy.db"):
        path = tmp_path / name
        sqlite3.connect(path).close()
        sources.append(path)
    destination = tmp_path / "temp" / "copy.db"
    destination.parent.mkdir()
    sqlite3.connect(destination).close()
    base = [
        "--canonical-db", str(sources[0]), "--analysis-source-db", str(sources[1]),
        "--market-db", str(sources[2]), "--taxonomy-db", str(sources[3]),
        "--destination", str(destination), "--as-of-date", "2026-09-08",
        "--model-fingerprint", MODEL_FINGERPRINT,
    ]
    planned = build_parser().parse_args(base)
    assert not planned.apply
    _validate(planned)
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        _validate(build_parser().parse_args([*base, "--apply"]))
    _validate(build_parser().parse_args([*base, "--apply", "--full-universe"]))
    unsafe = list(base)
    unsafe[unsafe.index("--destination") + 1] = str(sources[0])
    with pytest.raises(PermissionError, match="DESTINATION_REJECTED"):
        _validate(build_parser().parse_args(unsafe))
