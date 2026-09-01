from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.score import engine


def ttm_row(index: int, *, shares: float = 10.0, core_ready: int = 1, available: bool = True) -> dict[str, object]:
    year = 2022 + (index - 1) // 4
    quarter = (index - 1) % 4 + 1
    revenue = 100.0 * (1.10 ** ((index - 1) / 4.0))
    return {
        "ttm_id": index,
        "company_id": 1,
        "security_id": 1,
        "ticker": "TEST",
        "endpoint_quarter_id": index,
        "endpoint_fiscal_year": year,
        "endpoint_fiscal_quarter": f"Q{quarter}",
        "period_end": f"{year}-{quarter * 3:02d}-28",
        "ttm_source_available_date": f"{year}-{quarter * 3:02d}-29" if available else None,
        "ttm_revenue": revenue,
        "ttm_ebit": revenue * 0.10,
        "ttm_free_cashflow": revenue * 0.08,
        "cash": 20.0,
        "total_debt": 10.0,
        "shares_outstanding": shares,
        "core_ttm_ready": core_ready,
    }


def compute(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return engine.compute_score_rows(rows, {}, generated_at="2026-01-01T00:00:00Z", run_id="TEST_RUN")


def component(result: dict[str, object], name: str) -> dict[str, object]:
    return next(item for item in result["components"] if item["component_name"] == name)  # type: ignore[index,union-attr]


def create_analysis_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE analysis_model_run (
            run_id TEXT PRIMARY KEY, model_type TEXT NOT NULL, model_version TEXT NOT NULL,
            model_fingerprint TEXT NOT NULL, generated_at_utc TEXT NOT NULL,
            status TEXT NOT NULL, metadata_json TEXT NOT NULL
        );
        CREATE TABLE score_result (
            score_result_id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL,
            quarter_id INTEGER NOT NULL, model_version TEXT NOT NULL,
            model_fingerprint TEXT NOT NULL, total_score REAL,
            readiness_status TEXT NOT NULL, missing_input_reason TEXT,
            generated_at_utc TEXT NOT NULL,
            run_id TEXT REFERENCES analysis_model_run(run_id)
        );
        CREATE TABLE score_component (
            score_component_id INTEGER PRIMARY KEY,
            score_result_id INTEGER NOT NULL REFERENCES score_result(score_result_id) ON DELETE CASCADE,
            component_name TEXT NOT NULL, component_score REAL,
            evidence_json TEXT NOT NULL, UNIQUE(score_result_id, component_name)
        );
        """
    )


def test_full_score_has_seven_observed_components_and_direct_sum() -> None:
    result = compute([ttm_row(index) for index in range(1, 9)])[-1]
    assert result["readiness_status"] == "SCORE_FULL"
    assert len(result["components"]) == 7
    assert {item["component_name"] for item in result["components"]} == set(engine.COMPONENTS)  # type: ignore[union-attr]
    assert "CONSISTENCY" not in engine.COMPONENTS
    direct_sum = sum(item["component_score"] for item in result["components"])  # type: ignore[arg-type,union-attr]
    assert result["total_score"] == pytest.approx(direct_sum)
    assert component(result, "FUNDAMENTAL_TRAJECTORY")["component_score"] > 5.0


def test_five_snapshots_produce_full_score_without_imputation() -> None:
    result = compute([ttm_row(index) for index in range(1, 6)])[-1]
    assert result["readiness_status"] == "SCORE_FULL"
    trajectory = component(result, "FUNDAMENTAL_TRAJECTORY")
    assert trajectory["component_score"] is not None
    assert '"value_status":"OBSERVED"' in trajectory["evidence_json"]


def test_trajectory_flat_is_neutral_and_growth_or_decline_moves_score() -> None:
    flat = [ttm_row(index) for index in range(1, 6)]
    for item in flat:
        item.update(ttm_revenue=100.0, ttm_ebit=10.0, ttm_free_cashflow=8.0)
    flat_rows = {engine.fiscal_ordinal(item["endpoint_fiscal_year"], item["endpoint_fiscal_quarter"]): item for item in flat}
    flat_score, _ = engine.trajectory_points(max(flat_rows), flat_rows)
    assert flat_score == 5.0

    growth = [dict(item) for item in flat]
    for index in range(1, len(growth)):
        previous = growth[index - 1]
        current = growth[index]
        current["ttm_revenue"] = float(previous["ttm_revenue"]) * 1.05
        previous_margin = float(previous["ttm_ebit"]) / float(previous["ttm_revenue"])
        current["ttm_ebit"] = float(current["ttm_revenue"]) * (previous_margin + 0.05)
        current["ttm_free_cashflow"] = float(previous["ttm_free_cashflow"]) + 0.10 * float(previous["ttm_revenue"])
    growth_rows = {engine.fiscal_ordinal(item["endpoint_fiscal_year"], item["endpoint_fiscal_quarter"]): item for item in growth}
    growth_score, _ = engine.trajectory_points(max(growth_rows), growth_rows)
    assert growth_score == pytest.approx(10.0)

    decline = [dict(item) for item in flat]
    for index in range(1, len(decline)):
        previous = decline[index - 1]
        current = decline[index]
        current["ttm_revenue"] = float(previous["ttm_revenue"]) * 0.95
        previous_margin = float(previous["ttm_ebit"]) / float(previous["ttm_revenue"])
        current["ttm_ebit"] = float(current["ttm_revenue"]) * (previous_margin - 0.05)
        current["ttm_free_cashflow"] = float(previous["ttm_free_cashflow"]) - 0.10 * float(previous["ttm_revenue"])
    decline_rows = {engine.fiscal_ordinal(item["endpoint_fiscal_year"], item["endpoint_fiscal_quarter"]): item for item in decline}
    decline_score, _ = engine.trajectory_points(max(decline_rows), decline_rows)
    assert decline_score == pytest.approx(0.0)


def test_large_positive_share_change_is_scored_as_genuine_dilution() -> None:
    rows = [ttm_row(index) for index in range(1, 9)]
    rows[-1]["shares_outstanding"] = 20.0
    result = compute(rows)[-1]
    dilution = component(result, "DILUTION")
    assert dilution["component_score"] == 0.0
    assert "ASSUMED_GENUINE_DILUTION_BY_POLICY" in dilution["evidence_json"]
    assert result["readiness_status"] == "SCORE_FULL"


def test_not_ready_ttm_has_no_total_score() -> None:
    rows = [ttm_row(index) for index in range(1, 9)]
    rows[-1]["core_ttm_ready"] = 0
    result = compute(rows)[-1]
    assert result["readiness_status"] == "SCORE_NOT_READY"
    assert result["total_score"] is None


def test_apply_replaces_only_same_model_and_replays_identically() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_analysis_schema(conn)
    rows = compute([ttm_row(index) for index in range(1, 9)])
    first = engine.apply_scores(conn, rows, run_id="TEST_RUN", generated_at="2026-01-01T00:00:00Z")
    first_fingerprint = engine.score_fingerprint(conn)
    second = engine.apply_scores(conn, rows, run_id="TEST_RUN", generated_at="2026-01-01T00:00:00Z")
    second_fingerprint = engine.score_fingerprint(conn)
    assert first["rows_after"] == second["rows_after"] == len(rows)
    assert first_fingerprint == second_fingerprint
    assert conn.execute("SELECT COUNT(*) FROM score_component").fetchone()[0] == 7 * len(rows)


def test_engine_has_no_swingmaster_or_network_runtime_dependency() -> None:
    source = inspect.getsource(engine).lower()
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source
    assert "requests." not in source
    assert "sec.gov" not in source


def test_score_pipeline_refreshes_lifecycle_only_after_score_commit() -> None:
    source = inspect.getsource(engine.run_score)
    assert source.index("apply_scores(conn, rows") < source.index("conn.commit()")
    assert source.index("conn.commit()") < source.index("refresh_lifecycle_after_score(paths)")


def test_post_score_lifecycle_failure_leaves_committed_score_data_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis = tmp_path / "analysis.db"
    with sqlite3.connect(analysis) as conn:
        create_analysis_schema(conn)
        rows = compute([ttm_row(index) for index in range(1, 9)])
        engine.apply_scores(conn, rows, run_id="TEST_RUN", generated_at="2026-01-01T00:00:00Z")
        conn.commit()
        before = engine.score_fingerprint(conn)
    paths = engine.ScorePaths(tmp_path, tmp_path / "artifacts", tmp_path / "canonical.db", analysis, tmp_path / "market.db")

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("forced lifecycle failure")

    import rawcandle.fundamentals.lifecycle.revised_history as revised
    monkeypatch.setattr(revised, "refresh_revised_history", fail)
    with pytest.raises(RuntimeError, match="forced lifecycle failure"):
        engine.refresh_lifecycle_after_score(paths)
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        assert engine.score_fingerprint(conn) == before
