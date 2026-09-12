from __future__ import annotations

from rawcandle.fundamentals.phase13d3_closure import RETIRED_V3_TESTS, _active_test_collection_audit


def test_phase13d3_retired_manifest_contains_only_real_csv_fixture_tests() -> None:
    assert len(RETIRED_V3_TESTS) == 14
    assert all("test_fundamentals_v4_identity_calendar_bootstrap.py" in node for node in RETIRED_V3_TESTS)
    assert not any("test_header_mapping_detected" in node for node in RETIRED_V3_TESTS)
    assert not any("test_bootstrap_replay_idempotent" in node for node in RETIRED_V3_TESTS)


def test_phase13d3_active_test_audit_uses_marker_boundary() -> None:
    audit = _active_test_collection_audit()

    assert audit["retired_marker"] == "retired_v3"
    assert audit["default_expression"] == "not retired_v3"
    assert audit["fixture_not_restored"] == "temp/v3_active_tickers_99_27.csv"
