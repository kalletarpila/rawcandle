from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from rawcandle.forecasts import backup_lifecycle as life
from rawcandle.forecasts import contracts
from rawcandle.forecasts.hardening import backup_retention, create_backup, restore_backup, daily_workflow, cleanup_raw_evidence
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db, migrate_forecasts_db, remove_exact_duplicate_indexes
from tests.test_forecast_operational_hardening import _populated
from tests.test_forecast_operator import FakeTransport
from tests.test_forecast_persistence_v1 import fixture, raw_result


class SimulatedCrash(BaseException):
    pass


@pytest.mark.parametrize("phase", ["pin_persisted", "sqlite_created", "sqlite_verified", "gzip_created", "gzip_verified", "image_published", "manifest_published", "before_promotion"])
@pytest.mark.parametrize("failure", [OSError, SimulatedCrash])
def test_failed_replacement_keeps_old_good(tmp_path, monkeypatch, phase, failure):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    old = create_backup(source=db, destination=directory)
    old_spec = life.read_owner(directory)["last_good"]
    def fail(at):
        if at == phase:
            raise failure(at)
    monkeypatch.setattr(life, "checkpoint", fail)
    with pytest.raises(failure):
        create_backup(source=db, destination=directory)
    assert life.read_owner(directory)["last_good"] == old_spec
    assert life.validate(Path(old["backup_path"]))
    monkeypatch.setattr(life, "checkpoint", lambda _: None)
    backup_retention(backup_dir=directory, apply=True)
    assert Path(old["backup_path"]).exists()
    inventory = backup_retention(backup_dir=directory)["inventory"]
    assert all(r["classification"] != "SAFE_TO_DELETE" for r in inventory)


@pytest.mark.parametrize("phase", ["promoted", "before_unlink", "artifact_unlinked"])
def test_crash_after_promotion_retirement_is_retryable(tmp_path, monkeypatch, phase):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    old = create_backup(source=db, destination=directory)
    def crash(at):
        if at == phase:
            raise SimulatedCrash(at)
    monkeypatch.setattr(life, "checkpoint", crash)
    with pytest.raises(SimulatedCrash):
        create_backup(source=db, destination=directory)
    good = Path(life.read_owner(directory)["last_good"]["path"])
    assert str(good) != old["backup_path"]
    assert life.validate(good)
    monkeypatch.setattr(life, "checkpoint", lambda _: None)
    backup_retention(backup_dir=directory, apply=True)
    backup_retention(backup_dir=directory, apply=True)
    assert not Path(old["backup_path"]).exists()
    assert list(directory.glob("*.db.gz")) == [good]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_bad_latest_prevents_old_retirement(tmp_path, monkeypatch, damage):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    old = create_backup(source=db, destination=directory)
    monkeypatch.setattr(life, "checkpoint", lambda at: (_ for _ in ()).throw(SimulatedCrash()) if at == "promoted" else None)
    with pytest.raises(SimulatedCrash):
        create_backup(source=db, destination=directory)
    good = Path(life.read_owner(directory)["last_good"]["path"])
    good.chmod(0o600)
    if damage == "missing":
        good.unlink()
    else:
        good.write_bytes(b"corrupt gzip")
    with pytest.raises((ValueError, FileNotFoundError)):
        backup_retention(backup_dir=directory, apply=True)
    assert life.validate(Path(old["backup_path"]))


def test_recovery_pin_protects_previous_and_unknown_files(tmp_path):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    old = create_backup(source=db, destination=directory)
    old_path = Path(old["backup_path"])
    token = life.pin(old_path, "EXPLICIT_RECOVERY")
    new = create_backup(source=db, destination=directory)
    unknown = directory / "forecast_unregistered.db.gz"
    unknown.write_bytes(b"unregistered")
    result = backup_retention(backup_dir=directory, apply=True)
    assert old_path.exists() and unknown.exists()
    assert next(r for r in result["inventory"] if r["path"] == str(old_path))["classification"] == "KEEP_RECOVERY_PINNED"
    life.unpin(old_path, token)
    backup_retention(backup_dir=directory, apply=True)
    assert not old_path.exists()
    assert life.validate(Path(new["backup_path"]))


@pytest.mark.parametrize("phase", ["restore_before_replace", "restore_replaced"])
def test_restore_crash_keeps_source_pin(tmp_path, monkeypatch, phase):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    backup = Path(create_backup(source=db, destination=directory)["backup_path"])
    monkeypatch.setattr(life, "checkpoint", lambda at: (_ for _ in ()).throw(SimulatedCrash()) if at == phase else None)
    with pytest.raises(SimulatedCrash):
        restore_backup(backup=backup, target=tmp_path / "restored.db", backup_dir=directory)
    assert life.read_owner(directory)["pins"][backup.name]["reason"] == "RESTORE_IN_PROGRESS"
    assert life.validate(backup)


def test_gzip_restore_exact_bytes_and_corruption_rejected(tmp_path):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    manifest = create_backup(source=db, destination=directory)
    path = Path(manifest["backup_path"])
    target = tmp_path / "restore.db"
    restore_backup(backup=path, target=target, backup_dir=directory)
    assert life.sha256(target) == manifest["uncompressed_sha256"]
    assert not life.read_owner(directory)["pins"]
    path.chmod(0o600)
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 255
    path.write_bytes(data)
    with pytest.raises(ValueError):
        restore_backup(backup=path, target=tmp_path / "bad.db", backup_dir=directory)
    assert not (tmp_path / "bad.db").exists()


def test_partial_daily_does_not_promote_or_rotate(tmp_path, monkeypatch):
    import rawcandle.forecasts.hardening as hardening
    db, fundamentals = _populated(tmp_path)
    directory = tmp_path / "backups"
    good = create_backup(source=db, destination=directory)
    monkeypatch.setattr(hardening, "link_run", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("link failed")))
    result = daily_workflow(symbols=["TEST"], forecast_db=db, fundamentals_db=fundamentals, backup_dir=directory, transport=FakeTransport())
    assert result["terminal_status"] == "PARTIAL"
    assert life.read_owner(directory)["last_good"]["path"] == good["backup_path"]
    assert Path(result["backup"]["backup_path"]).name in life.read_owner(directory)["pins"]


def test_v1_v2_current_only_reuse_raw_and_mixed_pit(tmp_path, monkeypatch):
    import rawcandle.forecasts.repository as persistence
    db = tmp_path / "forecasts.db"
    migrate_forecasts_db(db)
    repo = ForecastRepository(db, adapter_version="test")
    run = repo.start_run(run_id="mixed")
    payload = fixture("price_targets_aapl.real_compact.json")
    original = persistence.parse_payload
    v1 = contracts.canonicalize_price_targets(payload, contract_version=contracts.PRICE_TARGET_CONTRACT_VERSION_V1)
    monkeypatch.setattr(persistence, "parse_payload", lambda *a: contracts.ParsedPayload(contracts.STATUS_SUCCESS_WITH_DATA, v1))
    def record(body, hour):
        raw = json.dumps(body, separators=(",", ":"))
        return repo.record_fetch(run, raw_result(body, family=contracts.FAMILY_PRICE_TARGET,
                                raw_hash=hashlib.sha256(raw.encode()).hexdigest(), fetched_at=f"2026-09-27T{hour:02}:00:00Z"))
    old = record(payload, 10)
    with connect_forecasts_db(db) as conn:
        old_rows = [tuple(r) for r in conn.execute("SELECT * FROM forecast_price_target ORDER BY price_target_id")]
    monkeypatch.setattr(persistence, "parse_payload", original)
    first = record(payload, 11)
    changed = copy.deepcopy(payload)
    changed["quoteSummary"]["result"][0]["financialData"]["currentPrice"] = 999
    second = record(changed, 12)
    assert first.snapshot_id == second.snapshot_id != old.snapshot_id
    assert second.status == contracts.STATUS_SUCCESS_UNCHANGED
    with connect_forecasts_db(db) as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM forecast_price_target WHERE snapshot_id=? ORDER BY price_target_id", (old.snapshot_id,))] == old_rows
        assert conn.execute("SELECT COUNT(*) FROM forecast_price_target WHERE snapshot_id=?", (first.snapshot_id,)).fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM forecast_price_target WHERE statistic='current'").fetchone()[0] == 1
        raw = conn.execute("SELECT r.body_text FROM forecast_fetch f JOIN forecast_raw_evidence r ON r.raw_hash=f.raw_evidence_hash WHERE f.fetch_id=?", (second.fetch_id,)).fetchone()[0]
        assert json.loads(raw)["quoteSummary"]["result"][0]["financialData"]["currentPrice"] == 999
        assert conn.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 3
    for hour, version, count in ((10, contracts.PRICE_TARGET_CONTRACT_VERSION_V1, 5), (12, contracts.PRICE_TARGET_CONTRACT_VERSION, 4)):
        pit = repo.as_known_at(forecast_family=contracts.FAMILY_PRICE_TARGET, timestamp_utc=f"2026-09-27T{hour:02}:30:00Z", provider_symbol="AAPL")
        assert pit["snapshot"]["contract_version"] == version and len(pit["records"]) == count
    assert cleanup_raw_evidence(forecast_db=db, apply=True, now_utc="2027-01-01T00:00:00Z")["deleted_rows"] == 0


@pytest.mark.parametrize("field", ["targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice"])
def test_consensus_change_remains_semantic(field):
    payload = fixture("price_targets_aapl.real_compact.json")
    original = contracts.canonicalize_price_targets(payload)
    payload["quoteSummary"]["result"][0]["financialData"][field] = 999
    assert contracts.canonicalize_price_targets(payload).content_hash != original.content_hash


def test_current_only_payload_is_not_consensus():
    payload = {"quoteSummary": {"result": [{"financialData": {"currentPrice": 42}}], "error": None}}
    assert contracts.parse_payload(contracts.FAMILY_PRICE_TARGET, payload).status == contracts.STATUS_VALID_NO_DATA


def test_exact_indexes_only_migration_is_idempotent(tmp_path):
    db, _ = _populated(tmp_path)
    with connect_forecasts_db(db) as conn:
        conn.execute("CREATE INDEX idx_forecast_price_target_snapshot ON forecast_price_target(snapshot_id,statistic)")
        conn.execute("CREATE INDEX idx_forecast_history_snapshot ON forecast_earnings_history_reference(snapshot_id,occurrence_index)")
        before = list(conn.execute("SELECT * FROM forecast_price_target"))
        assert remove_exact_duplicate_indexes(conn) == ["idx_forecast_price_target_snapshot", "idx_forecast_history_snapshot"]
        assert remove_exact_duplicate_indexes(conn) == []
        assert [tuple(r) for r in before] == [tuple(r) for r in conn.execute("SELECT * FROM forecast_price_target ORDER BY price_target_id")]
        assert "sqlite_autoindex_forecast_price_target_1" in {r[1] for r in conn.execute("PRAGMA index_list(forecast_price_target)")}
        assert conn.execute("EXPLAIN QUERY PLAN SELECT * FROM forecast_price_target WHERE snapshot_id=? AND statistic=?", ("x", "mean")).fetchone()[3].find("sqlite_autoindex_forecast_price_target_1") >= 0
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_forecast_estimate_snapshot'").fetchone()
        conn.execute("CREATE INDEX idx_forecast_price_target_snapshot ON forecast_price_target(snapshot_id,statistic DESC)")
        assert remove_exact_duplicate_indexes(conn) == []
    migrate_forecasts_db(db)
    with connect_forecasts_db(db) as conn:
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name='idx_forecast_price_target_snapshot'").fetchone()[0].endswith("DESC)")


def test_historical_close_uses_ohlc_at_explicit_date(tmp_path):
    from rawcandle.research.result_publication_event_window import _load_ticker_history
    path = tmp_path / "osakedata.db"
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE osakedata(osake,pvm,open,high,low,close,volume)")
        conn.executemany("INSERT INTO osakedata VALUES('AAPL',?,1,2,1,?,100)", [("2026-10-23", 2), ("2026-10-26", 9)])
        history = _load_ticker_history(conn, "AAPL")
    assert next(day.close for day in history if day.trading_date == "2026-10-23") == 2


def test_expired_orphans_only_are_removed(tmp_path):
    db, _ = _populated(tmp_path)
    with connect_forecasts_db(db) as conn:
        conn.execute("UPDATE forecast_raw_evidence SET retain_until_utc='2020-01-01T00:00:00Z'")
        conn.execute("INSERT INTO forecast_raw_evidence VALUES('orphan','YAHOO_FINANCE','PRICE_TARGET','{}','2020-01-01T00:00:00Z','2020-01-01T00:00:00Z')")
    result = cleanup_raw_evidence(forecast_db=db, apply=True, now_utc="2026-10-26T00:00:00Z")
    assert result["deleted_rows"] == 1
    with connect_forecasts_db(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM forecast_raw_evidence").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM forecast_fetch WHERE raw_evidence_hash IS NOT NULL").fetchone()[0] == 3


def test_legacy_v1_restore_still_supported(tmp_path):
    db, _ = _populated(tmp_path)
    directory = tmp_path / "backups"
    manifest = create_backup(source=db, destination=directory)
    packed = Path(manifest["backup_path"])
    legacy = directory / "forecast_legacy.db"
    with life.materialize(packed, tmp_path) as materialized:
        legacy.write_bytes(materialized.read_bytes())
    old = dict(manifest, contract_version="forecast_backup_v1", backup_path=str(legacy),
               backup_size_bytes=legacy.stat().st_size, backup_fingerprint_sha256=life.sha256(legacy))
    life.manifest_path(legacy).write_text(json.dumps(old))
    target = tmp_path / "legacy_restored.db"
    restore_backup(backup=legacy, target=target, backup_dir=directory)
    assert life.sha256(target) == old["backup_fingerprint_sha256"]


def test_complete_daily_promotes_with_terminal_acceptance(tmp_path):
    db, fundamentals = _populated(tmp_path)
    directory = tmp_path / "backups"
    old = create_backup(source=db, destination=directory)
    result = daily_workflow(symbols=["TEST"], forecast_db=db, fundamentals_db=fundamentals, backup_dir=directory, transport=FakeTransport())
    assert result["terminal_status"] == "SUCCESS"
    state = life.read_owner(directory)
    assert state["last_good"]["path"] == result["backup"]["backup_path"]
    assert state["acceptance"]["run_id"] == result["run_id"]
    assert state["acceptance"]["terminal_status"] == "SUCCESS"
    assert not Path(old["backup_path"]).exists()
    assert not state["pins"] and not state["retire"]


def test_version_boundary_is_not_analyst_revision():
    from rawcandle.research import price_target_event_research as research
    payload = fixture("price_targets_aapl.real_compact.json")
    v1 = contracts.canonicalize_price_targets(payload, contract_version=contracts.PRICE_TARGET_CONTRACT_VERSION_V1)
    v2 = contracts.canonicalize_price_targets(payload)
    assert v1.content_hash != v2.content_hash
    assert not research.changed({"states": v1.payload["values"]}, {"states": v2.payload["values"]})
    assert research.VERSION == "price_target_event_research_v1"


@pytest.mark.parametrize("field", ["targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice"])
def test_all_consensus_changes_create_new_persisted_snapshot(tmp_path, field):
    db = tmp_path / "forecasts.db"
    migrate_forecasts_db(db)
    repo = ForecastRepository(db, adapter_version="test")
    run = repo.start_run()
    payload = fixture("price_targets_aapl.real_compact.json")
    first = repo.record_fetch(run, raw_result(payload, family=contracts.FAMILY_PRICE_TARGET, raw_hash="before"))
    payload["quoteSummary"]["result"][0]["financialData"][field] = 999
    second = repo.record_fetch(run, raw_result(payload, family=contracts.FAMILY_PRICE_TARGET, raw_hash="after", fetched_at="2026-09-27T11:00:00Z"))
    assert first.snapshot_id != second.snapshot_id
    assert second.status == contracts.STATUS_SUCCESS_CHANGED
