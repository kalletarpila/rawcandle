from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import rawcandle.forecasts.hardening as hardening
from rawcandle.forecasts.contracts import FORECAST_FAMILIES
from rawcandle.forecasts.hardening import (
    DailyWorkflowError,
    ForecastDailyAlreadyRunningError,
    backup_retention,
    classify_drift,
    cleanup_raw_evidence,
    create_backup,
    daily_workflow,
    forecast_daily_lock,
    health_report,
    restore_backup,
    restore_rehearsal,
    universe_preview,
)
from rawcandle.forecasts.operator import acquire_run, migrate_database
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db
from tests.test_forecast_operator import FakeTransport, _fundamentals


def _populated(tmp_path: Path) -> tuple[Path, Path]:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    migrate_database(forecast)
    acquire_run(
        forecast_db=forecast,
        fundamentals_db=fundamentals,
        symbols=["TEST"],
        transport=FakeTransport(),
        run_id="initial-run",
    )
    return forecast, fundamentals


def _universe(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE fundamentals_operational_universe_active_version(
                singleton INTEGER PRIMARY KEY, universe_version_id TEXT NOT NULL
            );
            CREATE TABLE fundamentals_operational_universe_member(
                universe_version_id TEXT NOT NULL, company_id INTEGER NOT NULL,
                security_id INTEGER, current_ticker TEXT,
                membership_status TEXT NOT NULL
            );
            INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'u1');
            INSERT INTO fundamentals_operational_universe_member
                VALUES('u1',1,10,'TEST','ACTIVE_SINGLE_SECURITY');
            INSERT INTO fundamentals_operational_universe_member
                VALUES('u1',2,NULL,NULL,'HISTORICAL_RETAINED_NO_ACTIVE_SECURITY');
            """
        )


def test_known_ignored_and_unknown_drift_are_separate() -> None:
    result = classify_drift(
        ["financialData.totalCash", "financialData.brandNew", "financialData.brandNew"]
    )

    assert result["known_ignored_count"] == 1
    assert result["unknown_drift_count"] == 2
    assert result["distinct_unknown_paths"] == ["financialData.brandNew"]
    assert result["policy_version"] == "yahoo_known_ignored_fields_v1"


def test_health_report_aggregates_database_run_and_history(tmp_path: Path) -> None:
    forecast, _ = _populated(tmp_path)

    health = health_report(
        forecast_db=forecast, lookback_days=2, now_utc="2026-09-28T00:00:00Z"
    )

    assert health["database"]["quick_check"] == "ok"
    assert health["latest_run_status"] == "SUCCESS"
    assert health["recent_acquisition"]["runs"] == 1
    assert health["recent_acquisition"]["fetches"] == 3
    assert health["recent_acquisition"]["SUCCESS_CHANGED"] == 3
    assert health["history"]["snapshot_count_by_family"] == {
        family: 1 for family in FORECAST_FAMILIES
    }
    assert health["provider_quality"]["raw_evidence_rows"] == 3


def test_cleanup_dry_run_and_apply_preserve_canonical_history(tmp_path: Path) -> None:
    forecast, _ = _populated(tmp_path)
    with connect_forecasts_db(forecast) as connection:
        connection.execute(
            "UPDATE forecast_raw_evidence SET retain_until_utc='2026-01-01T00:00:00Z'"
        )
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("forecast_fetch", "forecast_snapshot", "forecast_estimate")
        }

    dry = cleanup_raw_evidence(
        forecast_db=forecast, now_utc="2026-09-27T00:00:00Z"
    )
    assert dry["eligible_rows"] == 3
    assert dry["deleted_rows"] == 0

    applied = cleanup_raw_evidence(
        forecast_db=forecast, apply=True, now_utc="2026-09-27T00:00:00Z"
    )
    assert applied["deleted_rows"] == 3
    assert applied["quick_check"] == "ok"
    with connect_forecasts_db(forecast) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_raw_evidence").fetchone()[0] == 0
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        assert before == after
        assert connection.execute(
            "SELECT COUNT(*) FROM forecast_fetch WHERE raw_evidence_hash IS NOT NULL"
        ).fetchone()[0] == 0


def test_backup_manifest_fingerprint_and_restore_guards(tmp_path: Path) -> None:
    forecast, _ = _populated(tmp_path)
    backups = tmp_path / "backups"
    manifest = create_backup(
        source=forecast,
        destination=backups,
        created_at_utc="2026-09-27T12:00:00Z",
    )
    backup = Path(manifest["backup_path"])

    assert backup.stat().st_mode & 0o222 == 0
    assert manifest["quick_check"] == "ok"
    assert len(manifest["backup_fingerprint_sha256"]) == 64
    persisted = json.loads(Path(manifest["manifest_path"]).read_text())
    assert persisted["core_counts"] == manifest["core_counts"]

    with pytest.raises(PermissionError):
        restore_backup(backup=backup, target=Path(__file__).parents[1] / "data" / "forecasts.db")

    target = tmp_path / "restored.db"
    restored = restore_backup(backup=backup, target=target, backup_dir=backups)
    assert restored["quick_check"] == "ok"
    with connect_forecasts_db(target) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 3

    safety = restore_backup(backup=backup, target=target, backup_dir=backups)
    assert safety["safety_backup"] is not None

    unrelated = tmp_path / "unrelated.db"
    with sqlite3.connect(unrelated) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(ValueError, match="not a valid forecast database"):
        restore_backup(backup=backup, target=unrelated, backup_dir=backups)


def test_backup_retention_dry_run_apply_protects_newest(tmp_path: Path) -> None:
    forecast, _ = _populated(tmp_path)
    backups = tmp_path / "backups"
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    created: list[Path] = []
    for days in (0, 1, 15, 16, 90, 91, 400):
        timestamp = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
        created.append(Path(create_backup(
            source=forecast, destination=backups, created_at_utc=timestamp
        )["backup_path"]))

    dry = backup_retention(
        backup_dir=backups, now_utc="2026-09-27T00:00:00Z"
    )
    assert dry["mode"] == "DRY_RUN"
    assert dry["selected_files"] > 0
    assert all(path.exists() for path in created)

    applied = backup_retention(
        backup_dir=backups, apply=True, now_utc="2026-09-27T00:00:00Z"
    )
    assert applied["deleted_backups"] > 0
    assert created[0].exists()
    assert applied["remaining_newest_valid_backup"] == str(created[0])


def test_interrupted_run_resumes_only_missing_attempts(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    migrate_database(forecast)
    transport = FakeTransport()
    repository = ForecastRepository(forecast, adapter_version="test", raw_retention_days=30)
    run_id = repository.start_run(
        run_id="interrupted",
        scope={"symbols": ["TEST"], "families": list(FORECAST_FAMILIES), "mode": "OPERATOR"},
    )
    first_family = FORECAST_FAMILIES[0]
    repository.record_fetch(
        run_id, transport.fetch("TEST", first_family), company_id=1, security_id=10
    )

    resumed_transport = FakeTransport()
    result = acquire_run(
        forecast_db=forecast,
        fundamentals_db=fundamentals,
        transport=resumed_transport,
        resume_run_id=run_id,
    )

    assert result.run_id == run_id
    assert resumed_transport.calls == [("TEST", family) for family in FORECAST_FAMILIES[1:]]
    assert result.counters == {"SUCCESS_CHANGED": 3}
    with connect_forecasts_db(forecast) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 3
        assert connection.execute(
            "SELECT status FROM forecast_run WHERE run_id=?", (run_id,)
        ).fetchone()[0] == "SUCCESS"


def test_universe_preview_and_bounded_daily_workflow(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    _universe(fundamentals)
    migrate_database(forecast)

    preview = universe_preview(
        fundamentals_db=fundamentals, minimum_interval_seconds=0.75
    )
    assert preview["symbols"] == ["TEST"]
    assert preview["symbols_count"] == 1
    assert preview["excluded_count"] == 1
    assert preview["excluded_reasons"] == {
        "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY": 1
    }
    assert preview["estimated_requests_per_day"] == 3
    assert preview["ideal_minimum_runtime_seconds"] == 2.25

    result = daily_workflow(
        max_symbols=1,
        forecast_db=forecast,
        fundamentals_db=fundamentals,
        backup_dir=tmp_path / "backups",
        transport=FakeTransport(),
    )
    assert Path(result["backup"]["backup_path"]).exists()
    assert result["report"]["run_status"] == "SUCCESS"
    assert result["terminal_status"] == "SUCCESS"
    assert result["universe"]["selected_symbols"] == 1
    assert "INDIVIDUAL_FAILURE_PARTIAL" in result["failure_policy"]


def test_full_bounded_daily_workflow_requires_explicit_mode(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    _universe(fundamentals)
    migrate_database(forecast)

    result = daily_workflow(
        full_bounded_universe=True,
        forecast_db=forecast,
        fundamentals_db=fundamentals,
        backup_dir=tmp_path / "backups",
        transport=FakeTransport(),
    )

    assert result["terminal_status"] == "SUCCESS"
    assert result["universe"]["full_bounded_universe"] is True
    assert result["universe"]["max_symbols"] is None
    assert result["universe"]["universe_version_id"] == "u1"
    with connect_forecasts_db(forecast) as connection:
        scope = json.loads(connection.execute(
            "SELECT scope_json FROM forecast_run WHERE run_id=?", (result["run_id"],)
        ).fetchone()[0])
    assert scope["universe"] == {
        "authority": (
            "fundamentals_v4."
            "fundamentals_operational_universe_active_version/member"
        ),
        "eligible_symbol_count": 1,
        "selected_symbol_count": 1,
        "selection_mode": "FULL_BOUNDED_UNIVERSE",
        "version_id": "u1",
    }


def test_daily_workflow_rejects_implicit_or_conflicting_scope(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        daily_workflow(forecast_db=tmp_path / "forecasts.db")
    with pytest.raises(ValueError, match="exactly one"):
        daily_workflow(
            max_symbols=1,
            full_bounded_universe=True,
            forecast_db=tmp_path / "forecasts.db",
        )


def test_daily_workflow_fails_closed_when_preflight_fails(tmp_path: Path) -> None:
    with pytest.raises(DailyWorkflowError) as caught:
        daily_workflow(
            symbols=["TEST"],
            forecast_db=tmp_path / "missing.db",
            fundamentals_db=tmp_path / "fundamentals.db",
            backup_dir=tmp_path / "backups",
            transport=FakeTransport(),
        )
    assert caught.value.code == "DB_PREFLIGHT_FAILED"
    assert not (tmp_path / "backups").exists()


def test_daily_workflow_fails_closed_when_backup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forecast, fundamentals = _populated(tmp_path)
    monkeypatch.setattr(
        hardening, "create_backup",
        lambda **kwargs: (_ for _ in ()).throw(OSError("backup unavailable")),
    )
    transport = FakeTransport()

    with pytest.raises(DailyWorkflowError) as caught:
        daily_workflow(
            symbols=["TEST"], forecast_db=forecast,
            fundamentals_db=fundamentals, transport=transport,
        )

    assert caught.value.code == "BACKUP_FAILED"
    assert transport.calls == []


def test_daily_overlap_guard_rejects_second_writer(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    with forecast_daily_lock(forecast):
        with pytest.raises(ForecastDailyAlreadyRunningError):
            with forecast_daily_lock(forecast):
                pass


def test_restore_rehearsal_validates_manifest_counts_and_pit_parity(tmp_path: Path) -> None:
    forecast, _ = _populated(tmp_path)
    backups = tmp_path / "backups"
    created = create_backup(
        source=forecast, destination=backups,
        created_at_utc="2026-09-27T12:00:00Z",
    )

    result = restore_rehearsal(
        backup_dir=backups, target=tmp_path / "rehearsal.db"
    )

    assert result["status"] == "RESTORE_REHEARSAL_PASS"
    assert result["backup_path"] == created["backup_path"]
    assert result["quick_check"] == "ok"
    assert result["core_counts"]["forecast_run"] == 1
    assert result["core_counts"]["forecast_fetch"] == 3
    assert result["core_counts"]["forecast_snapshot"] == 3
    assert result["representative_pit_row"] is not None


def test_daily_link_failure_preserves_acquisition_and_returns_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    migrate_database(forecast)
    monkeypatch.setattr(
        hardening, "link_run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("link down"))
    )

    result = daily_workflow(
        symbols=["TEST"], forecast_db=forecast, fundamentals_db=fundamentals,
        backup_dir=tmp_path / "backups", transport=FakeTransport(),
    )

    assert result["terminal_status"] == "PARTIAL"
    assert "link down" in result["errors"]["link"]
    assert result["report"]["family_fetches_attempted"] == 3
