from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import first_public_result_date_bootstrap as bootstrap
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.schema.migrations import CANONICAL_SCHEMA_SQL, bootstrap_database


NOW = "2026-09-20T12:00:00Z"


def _sqlite(path: Path, schema: str = "CREATE TABLE marker(value TEXT)") -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)


def _paths(tmp_path: Path, rows: list[tuple] | None = None) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
    canonical = tmp_path / "canonical.db"
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, NOW)
    with sqlite3.connect(canonical) as connection:
        connection.execute("INSERT INTO company VALUES(1,'TEST','Test','ACTIVE',?,?)", (NOW, NOW))
        connection.execute("INSERT INTO security VALUES(1,1,'TEST','NASDAQ',1,NULL,NULL,?,?)", (NOW, NOW))
        for row in rows or [(1, 1, 2025, "Q1", "2025-05-01", None)]:
            quarter_id, company_id, year, quarter, source_date, first_date = row
            connection.execute(
                "INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,"
                "source_fiscalperiod,source_reportperiod,identity_provider,identity_status,"
                "source_availability_date,first_public_result_date,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?,'2025-Q1','2025-03-31','SHARADAR_ARQ','ACCEPTED',?,?,?,?)",
                (quarter_id, company_id, year, quarter, f"{year}-03-31", source_date, first_date, NOW, NOW),
            )
            connection.execute(
                "INSERT INTO v4_quarter_financials(quarter_id,revenue,canonical_source_policy,created_at_utc,updated_at_utc) "
                "VALUES(?,123,'fixture',?,?)", (quarter_id, NOW, NOW),
            )
    provider = tmp_path / "provider.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    for path in (provider, analysis, market, taxonomy):
        _sqlite(path)
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def _result_path(result: dict) -> Path:
    return Path(result["artifact_dir"]) / "bootstrap_result.json"


def test_preview_ready_and_reports_exact_counts(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    result = bootstrap.run_preview(paths=paths, run_root=tmp_path / "runs")
    assert result["outcome"] == "READY"
    assert result["audit"]["counts"] == {
        "total_rows": 1, "null_first_public": 1, "established_first_public": 0,
        "eligible": 1, "unresolved": 0, "established_source_differences": 0,
    }
    assert result["audit"]["expected_post_bootstrap_non_null"] == 1
    assert result["production_state_unchanged"] is True


def test_preview_already_bootstrapped_allows_source_date_to_differ(tmp_path: Path) -> None:
    paths = _paths(tmp_path, [(1, 1, 2025, "Q1", "2025-06-01", "2025-05-01")])
    result = bootstrap.run_preview(paths=paths, run_root=tmp_path / "runs")
    assert result["outcome"] == "ALREADY_BOOTSTRAPPED"
    assert result["audit"]["counts"]["established_source_differences"] == 1
    assert result["audit"]["blockers"] == []


def test_preview_partial_bootstrap_requires_review(tmp_path: Path) -> None:
    paths = _paths(tmp_path, [
        (1, 1, 2025, "Q1", "2025-05-01", "2025-05-01"),
        (2, 1, 2025, "Q2", "2025-08-01", None),
    ])
    result = bootstrap.run_preview(paths=paths, run_root=tmp_path / "runs")
    assert result["outcome"] == "REVIEW_REQUIRED"
    assert result["audit"]["partial_bootstrap"] is True


def test_preview_blocks_unresolved_and_malformed_source_dates(tmp_path: Path) -> None:
    unresolved = _paths(tmp_path / "unresolved", [(1, 1, 2025, "Q1", None, None)])
    result = bootstrap.run_preview(paths=unresolved, run_root=tmp_path / "runs-a")
    assert result["outcome"] == "BLOCKED"
    assert "NULL_SOURCE_AVAILABILITY_DATE" in result["audit"]["blockers"]

    malformed = _paths(tmp_path / "malformed", [(1, 1, 2025, "Q1", "not-a-date", None)])
    result = bootstrap.run_preview(paths=malformed, run_root=tmp_path / "runs-b")
    assert result["outcome"] == "BLOCKED"
    assert "MALFORMED_PUBLICATION_DATE" in result["audit"]["blockers"]


def test_duplicate_stable_identity_fails_closed(tmp_path: Path) -> None:
    canonical = tmp_path / "duplicate.db"
    _sqlite(canonical, """
        CREATE TABLE company(company_id INTEGER PRIMARY KEY);
        CREATE TABLE security(security_id INTEGER PRIMARY KEY, company_id INTEGER);
        CREATE TABLE v4_quarter(
          quarter_id INTEGER PRIMARY KEY, company_id INTEGER, fiscal_year INTEGER,
          fiscal_quarter TEXT, source_availability_date TEXT, first_public_result_date TEXT
        );
        INSERT INTO company VALUES(1);
        INSERT INTO security VALUES(1,1);
        INSERT INTO v4_quarter VALUES(1,1,2025,'Q1','2025-05-01',NULL);
        INSERT INTO v4_quarter VALUES(2,1,2025,'Q1','2025-05-01',NULL);
    """)
    result = bootstrap.audit_canonical(canonical)
    assert result["outcome"] == "BLOCKED"
    assert "DUPLICATE_STABLE_QUARTER_IDENTITY" in result["blockers"]


def test_test_copy_changes_only_target_and_cleans_copy(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "db")
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "copies"
    preview = bootstrap.run_preview(paths=paths, run_root=run_root)
    result = bootstrap.run_test(
        preview_result_path=_result_path(preview), paths=paths,
        run_root=run_root, temp_root=temp_root,
    )
    assert result["outcome"] == "COMPLETED"
    assert result["updated_count"] == 1
    assert all(result["validation"].values())
    assert result["test_copy_cleaned"] is True
    assert not list(temp_root.rglob("*.db"))
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT first_public_result_date FROM v4_quarter").fetchone()[0] is None


def test_stale_preview_rejected_before_candidate_copy_exists(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "db")
    run_root = tmp_path / "runs"
    temp_root = tmp_path / "copies"
    preview = bootstrap.run_preview(paths=paths, run_root=run_root)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE v4_quarter SET source_availability_date='2025-05-02'")
    with pytest.raises(bootstrap.StaleBootstrapPreview):
        bootstrap.run_test(
            preview_result_path=_result_path(preview), paths=paths,
            run_root=run_root, temp_root=temp_root,
        )
    assert not temp_root.exists()
    assert not list(tmp_path.rglob("canonical_test.db"))


def test_bootstrap_preserves_established_date_when_source_later_changes(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "db")
    preview = bootstrap.run_preview(paths=paths, run_root=tmp_path / "runs")
    test = bootstrap.run_test(
        preview_result_path=_result_path(preview), paths=paths,
        run_root=tmp_path / "runs", temp_root=tmp_path / "copies",
    )
    sample = test["sample"][0]
    assert sample["first_public_after"] == "2025-05-01"
    # This mirrors the routine Refresh invariant: source may move, established first-public may not.
    copy = tmp_path / "later-refresh.db"
    bootstrap.online_backup(paths.canonical_db, copy)
    with sqlite3.connect(copy) as connection:
        bootstrap._apply_bootstrap(connection)
        connection.execute("UPDATE v4_quarter SET source_availability_date='2025-06-01'")
        dates = connection.execute(
            "SELECT source_availability_date,first_public_result_date FROM v4_quarter"
        ).fetchone()
    assert dates == ("2025-06-01", "2025-05-01")


def _production_evidence(tmp_path: Path):
    paths = _paths(tmp_path / "db")
    run_root = tmp_path / "runs"
    preview = bootstrap.run_preview(paths=paths, run_root=run_root)
    test = bootstrap.run_test(
        preview_result_path=_result_path(preview), paths=paths,
        run_root=run_root, temp_root=tmp_path / "copies",
    )
    return paths, run_root, _result_path(preview), _result_path(test)


@pytest.mark.parametrize("point", ["BEFORE_TRANSACTION", "AFTER_BEGIN", "AFTER_UPDATE", "AFTER_VALIDATION"])
def test_production_failure_before_commit_rolls_back_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str,
) -> None:
    paths, run_root, preview_path, test_path = _production_evidence(tmp_path)
    monkeypatch.setattr(bootstrap, "production_lock", lambda: nullcontext({}))
    monkeypatch.setattr(bootstrap, "guard_production_writes", lambda _path: {"status": "CLEAR"})
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    def fail(at: str) -> None:
        if at == point:
            raise RuntimeError(f"injected:{point}")

    with pytest.raises(RuntimeError, match="injected"):
        bootstrap.run_production(
            preview_result_path=preview_path, test_result_path=test_path,
            confirm_production=True, paths=paths, run_root=run_root,
            backup_root=backup_root, journal_path=tmp_path / "journal.json",
            fault_injector=fail,
        )
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT first_public_result_date FROM v4_quarter").fetchone()[0] is None


@pytest.mark.parametrize("point", ["AFTER_COMMIT", "POSTFLIGHT"])
def test_production_failure_after_commit_restores_verified_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str,
) -> None:
    paths, run_root, preview_path, test_path = _production_evidence(tmp_path)
    monkeypatch.setattr(bootstrap, "production_lock", lambda: nullcontext({}))
    monkeypatch.setattr(bootstrap, "guard_production_writes", lambda _path: {"status": "CLEAR"})
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    def fail(at: str) -> None:
        if at == point:
            raise RuntimeError(f"injected:{point}")

    with pytest.raises(RuntimeError, match="injected"):
        bootstrap.run_production(
            preview_result_path=preview_path, test_result_path=test_path,
            confirm_production=True, paths=paths, run_root=run_root,
            backup_root=backup_root, journal_path=tmp_path / "journal.json",
            fault_injector=fail,
        )
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT first_public_result_date FROM v4_quarter").fetchone()[0] is None


def test_production_requires_confirmation_and_matching_test(tmp_path: Path) -> None:
    paths, run_root, preview_path, test_path = _production_evidence(tmp_path)
    with pytest.raises(bootstrap.BootstrapValidationError, match="EXPLICIT_CONFIRMATION"):
        bootstrap.run_production(
            preview_result_path=preview_path, test_result_path=test_path,
            confirm_production=False, paths=paths, run_root=run_root,
        )
    payload = json.loads(test_path.read_text(encoding="utf-8"))
    payload["preview_run_id"] = "wrong"
    test_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapValidationError, match="MATCHING_SUCCESSFUL_TEST"):
        bootstrap.run_production(
            preview_result_path=preview_path, test_result_path=test_path,
            confirm_production=True, paths=paths, run_root=run_root,
        )


def test_nonterminal_publication_guard_blocks_before_backup_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, run_root, preview_path, test_path = _production_evidence(tmp_path)
    monkeypatch.setattr(bootstrap, "production_lock", lambda: nullcontext({}))
    monkeypatch.setattr(
        bootstrap, "guard_production_writes",
        lambda _path: (_ for _ in ()).throw(RuntimeError("INCOMPLETE_PUBLICATION_RECOVERED_RETRY_REQUIRED")),
    )
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    with pytest.raises(RuntimeError, match="RETRY_REQUIRED"):
        bootstrap.run_production(
            preview_result_path=preview_path, test_result_path=test_path,
            confirm_production=True, paths=paths, run_root=run_root,
            backup_root=backup_root, journal_path=tmp_path / "journal.json",
        )
    assert list(backup_root.iterdir()) == []
    with sqlite3.connect(paths.canonical_db) as connection:
        assert connection.execute("SELECT first_public_result_date FROM v4_quarter").fetchone()[0] is None
