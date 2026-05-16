from __future__ import annotations

import inspect

import pytest

from services.stock_update_service import (
    execute_final_dow_update,
    execute_stock_update_batch,
    run_stock_data_update,
)


def test_execute_final_dow_update_success_calls_callable_with_expected_kwargs() -> None:
    calls = {}

    def calculate_dow_structures(**kwargs):
        calls.update(kwargs)
        return {"processed": 10, "updated": 3, "status": "OK"}

    result = execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path="analysis.db",
        osakedata_db_path="osakedata.db",
        market="usa",
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dry_run=False,
    )

    assert result.attempted is True
    assert result.success is True
    assert result.dow_summary == {"processed": 10, "updated": 3, "status": "OK"}
    assert result.warning is None
    assert calls == {
        "analysis_db_path": "analysis.db",
        "osakedata_db_path": "osakedata.db",
        "market": "usa",
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
        "dry_run": False,
    }


def test_execute_final_dow_update_omits_optional_kwargs_when_none() -> None:
    calls = {}

    def calculate_dow_structures(**kwargs):
        calls.update(kwargs)
        return {}

    execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path="analysis.db",
        osakedata_db_path="osakedata.db",
        market="usa",
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dry_run=False,
        run_id=None,
        created_at_utc=None,
    )

    assert "run_id" not in calls
    assert "created_at_utc" not in calls


def test_execute_final_dow_update_includes_optional_kwargs_when_provided() -> None:
    calls = {}

    def calculate_dow_structures(**kwargs):
        calls.update(kwargs)
        return {}

    execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path="analysis.db",
        osakedata_db_path="osakedata.db",
        market="usa",
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dry_run=False,
        run_id="TEST_RUN",
        created_at_utc="2026-05-16T00:00:00Z",
    )

    assert calls["run_id"] == "TEST_RUN"
    assert calls["created_at_utc"] == "2026-05-16T00:00:00Z"


def test_execute_final_dow_update_catches_exception_as_warning() -> None:
    def calculate_dow_structures(**kwargs):
        raise RuntimeError("dow failed")

    result = execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path="analysis.db",
        osakedata_db_path="osakedata.db",
        market="usa",
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dry_run=False,
    )

    assert result.attempted is True
    assert result.success is False
    assert result.dow_summary is None
    assert "Dow-rakenteiden paivitys epaonnistui" in result.warning
    assert "dow failed" in result.warning


def test_execute_final_dow_update_passes_market_through_unchanged() -> None:
    calls = {}

    def calculate_dow_structures(**kwargs):
        calls.update(kwargs)
        return {}

    execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path="analysis.db",
        osakedata_db_path="osakedata.db",
        market=" USA ",
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dry_run=False,
    )

    assert calls["market"] == " USA "


def test_execute_stock_update_batch_signature_has_no_dow_callable() -> None:
    signature = inspect.signature(execute_stock_update_batch)

    assert "calculate_dow_structures" not in signature.parameters
    assert "dow_update" not in signature.parameters
    assert "dow_callable" not in signature.parameters

