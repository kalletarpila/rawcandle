from __future__ import annotations

import importlib.util
from pathlib import Path

import rawcandle.fundamentals.lifecycle as lifecycle
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT, MODEL_VERSION
from rawcandle.fundamentals.schema.migrations import bootstrap_all, connect


RETIRED_SCHEMA_OBJECTS = {
    "lifecycle_persistence_schema",
    "lifecycle_pit_result",
    "idx_lifecycle_pit_current",
    "idx_lifecycle_pit_asof",
    "idx_lifecycle_pit_quarter_audit",
}


def test_phase_2a_public_api_and_identity_remain_active() -> None:
    assert lifecycle.classify_raw_state
    assert lifecycle.advance_state_machine
    assert lifecycle.replay_state_machine
    assert MODEL_VERSION == "V4_FUNDAMENTAL_LIFECYCLE_V1"
    assert MODEL_FINGERPRINT == "db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f"


def test_retired_pit_modules_and_exports_are_absent() -> None:
    assert importlib.util.find_spec("rawcandle.fundamentals.lifecycle.persistence") is None
    assert importlib.util.find_spec("rawcandle.cli.run_fundamentals_v4_lifecycle_pit") is None
    for name in (
        "PERSISTENCE_SCHEMA_VERSION",
        "LifecycleResultRepository",
        "current_pit",
        "as_of_pit",
        "fiscal_quarter_history",
        "replay_pit_versions",
        "replay_revised_history",
    ):
        assert not hasattr(lifecycle, name)


def test_fresh_v4_analysis_schema_has_no_retired_pit_objects(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, "now")
    with connect(analysis) as conn:
        objects = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
            )
        }
    assert RETIRED_SCHEMA_OBJECTS.isdisjoint(objects)


def test_retired_pit_paths_are_not_present() -> None:
    root = Path(__file__).resolve().parents[1]
    retired_paths = (
        root / "rawcandle/fundamentals/lifecycle/persistence.py",
        root / "rawcandle/cli/run_fundamentals_v4_lifecycle_pit.py",
        root / "tests/test_fundamentals_v4_lifecycle_persistence.py",
        root / "docs/fundamentals_v4/fundamentals_v4_lifecycle_v1_pit_persistence.md",
    )
    assert not any(path.exists() for path in retired_paths)
