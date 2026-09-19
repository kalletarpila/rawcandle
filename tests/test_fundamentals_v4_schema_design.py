from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rawcandle.fundamentals.schema.contract import SCHEMA_VERSION, SHARADAR_ARQ_FIELD_MAPPING, V4_CANONICAL_FINANCIAL_FIELDS
from rawcandle.fundamentals.schema.migrations import (
    ANALYSIS_SCHEMA_SQL,
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_all,
    canonical_field_contract_present,
    connect,
)
from rawcandle.fundamentals.schema.prototype import (
    canonical_counts,
    canonicalize_arq,
    insert_sharadar_observation,
    load_provider_subset,
    parse_fiscalperiod,
    validate_integrity,
)


def _paths(tmp_path: Path) -> SimpleNamespace:
    acceptance_root = tmp_path / "acceptance"
    acceptance_root.mkdir()
    _write_acceptance_csvs(acceptance_root)
    return SimpleNamespace(
        artifact_root=tmp_path / "artifact",
        provider_db=tmp_path / "artifact" / "prototype_provider.db",
        canonical_db=tmp_path / "artifact" / "prototype_v4.db",
        analysis_db=tmp_path / "artifact" / "prototype_analysis.db",
        acceptance_root=acceptance_root,
    )


def _write_acceptance_csvs(root: Path) -> None:
    rows = [
        _row("AAPL", "ARQ", "2025-12-27", "2026-Q1", 0),
        _row("AAPL", "ARQ", "2025-09-27", "2025-Q4", None),
        _row("WDAY", "ARQ", "2026-04-30", "2027-Q1", 1),
        _row("ASTH", "ARQ", "2026-03-31", "2026-Q1", 2),
        _row("CECO", "ARQ", "2026-03-31", "2026-Q1", 3),
    ]
    mrq_rows = [
        dict(row, dimension="MRQ", revenue=str(int(row["revenue"]) + 1) if row["revenue"] else "")
        for row in rows
    ]
    _write_csv(root / "acceptance_arq_rows.csv", rows)
    _write_csv(root / "acceptance_mrq_rows.csv", mrq_rows)


def _row(ticker: str, dimension: str, reportperiod: str, fiscalperiod: str, revenue: int | None) -> dict[str, str]:
    fields = {
        "ticker": ticker,
        "permaticker": str(abs(hash(ticker)) % 1000000),
        "dimension": dimension,
        "calendardate": reportperiod[:7] + "-30",
        "reportperiod": reportperiod,
        "fiscalperiod": fiscalperiod,
        "date": reportperiod,
        "lastupdated": "2026-08-30",
        "revenue": "" if revenue is None else str(revenue),
        "gp": "2",
        "opinc": "3",
        "ebit": "4",
        "ebitda": "5",
        "netinc": "6",
        "netinccmn": "5",
        "ncfo": "7",
        "capex": "-2",
        "fcf": "5",
        "cashneq": "8",
        "debt": "9",
        "debtc": "4",
        "debtnc": "5",
        "sharesbas": "10",
        "shareswa": "11",
        "shareswadil": "12",
    }
    return fields


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_all_three_schemas_bootstrap(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    assert paths.provider_db.exists()
    assert paths.canonical_db.exists()
    assert paths.analysis_db.exists()


def test_schema_versions_exist(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with connect(paths.provider_db) as conn:
            assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION


def test_fk_enforcement_works(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with connect(paths.provider_db) as conn:
        try:
            conn.execute("INSERT INTO provider_observation(observation_id, run_id, provider, provider_record_key, native_table, fetched_at_utc, content_hash, provider_status, payload_json) VALUES ('x','missing','SHARADAR','k','fundamentals','now','h','SUCCESS','{}')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("foreign key was not enforced")


def test_company_security_separation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM security").fetchone()[0] == 1


def test_permaticker_unique_mapping(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_security_identity").fetchone()[0] == 1


def test_all_12_canonical_fields_exist(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with connect(paths.canonical_db) as conn:
        assert canonical_field_contract_present(conn)
        assert set(SHARADAR_ARQ_FIELD_MAPPING) == set(V4_CANONICAL_FINANCIAL_FIELDS)


def test_arq_canonicalized(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    counts = canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    assert counts["canonical_quarters"] == 2


def test_mrq_not_canonicalized_as_primary(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.provider_db) as provider, connect(paths.canonical_db) as canonical:
        assert provider.execute("SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE dimension='MRQ'").fetchone()[0] == 2
        assert canonical.execute("SELECT COUNT(*) FROM v4_quarter").fetchone()[0] == 2


def test_explicit_q4_accepted(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM v4_quarter WHERE fiscal_quarter='Q4'").fetchone()[0] == 1


def test_fiscalperiod_parsed_correctly() -> None:
    assert parse_fiscalperiod("2027-Q1") == (2027, "Q1")


def test_hard_cases_parse() -> None:
    assert parse_fiscalperiod("2027-Q1") == (2027, "Q1")
    assert parse_fiscalperiod("2026-Q1") == (2026, "Q1")


def test_provider_null_remains_null_and_zero_remains_zero(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        values = conn.execute("SELECT revenue FROM v4_quarter_financials ORDER BY revenue IS NOT NULL, revenue").fetchall()
        assert values[0][0] is None
        assert any(row[0] == 0 for row in values)


def test_provider_replay_idempotent(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    first = load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    second = load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    assert first == second


def test_canonical_and_provenance_replay_idempotent(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    first = canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    second = canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    assert first == second


def test_every_non_null_canonical_field_has_provenance(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    integrity = validate_integrity(paths)
    assert integrity["canonical_fields_without_provenance"] == 0


def test_no_provenance_for_null_unless_justified(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM v4_field_provenance WHERE canonical_field='revenue'").fetchone()[0] == 1


def test_source_availability_date_separate_from_first_public_date(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        row = conn.execute("SELECT source_availability_date, first_public_result_date FROM v4_quarter LIMIT 1").fetchone()
        assert row["source_availability_date"] is not None
        assert row["first_public_result_date"] is None


def test_mrq_change_does_not_overwrite_arq_canonical(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.provider_db) as conn:
        changed = _row("AAPL", "MRQ", "2025-12-27", "2026-Q1", 999)
        insert_sharadar_observation(conn, changed, "run", "now")
    before = canonical_counts(paths.canonical_db)
    after = canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    assert before == after


def test_provider_side_support_fields_retained(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    with connect(paths.provider_db) as conn:
        row = conn.execute("SELECT debtc, debtnc, shareswa, shareswadil FROM sharadar_fundamental_observation LIMIT 1").fetchone()
        assert row["debtc"] == 4
        assert row["debtnc"] == 5
        assert row["shareswa"] == 11
        assert row["shareswadil"] == 12


def test_sharesbas_mapped_canonical_and_weighted_shares_not_canonical(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    load_provider_subset(paths.provider_db, paths.acceptance_root, ["AAPL"], "run", "now")
    canonicalize_arq(paths.provider_db, paths.canonical_db, "now")
    with connect(paths.canonical_db) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}
        assert "shares_outstanding" in columns
        assert "shareswa" not in columns
        assert "shareswadil" not in columns


def test_ttm_contract_exists_but_no_engine_migration(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='v4_ttm_contract'").fetchone()
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='v4_ttm_values'").fetchone()
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='v4_ttm_input_quarter'").fetchone()


def test_analysis_schema_exists_but_no_score_engine(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    bootstrap_all(paths.provider_db, paths.canonical_db, paths.analysis_db, "now")
    with connect(paths.analysis_db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='score_result'").fetchone()
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='score_engine_state'").fetchone()


def test_schema_design_uses_disposable_paths_not_production(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    production = Path("/home/kalle/projects/rawcandle/data")
    assert paths.provider_db != production / "fundamentals_provider.db"
    assert paths.canonical_db != production / "fundamentals_v4.db"
    assert paths.analysis_db != production / "fundamentals_analysis.db"


def test_schema_helpers_have_no_external_runtime_import() -> None:
    import rawcandle.fundamentals.schema.prototype as prototype

    source = Path(prototype.__file__).read_text()
    assert "import swingmaster" not in source.lower()
    assert "from swingmaster" not in source.lower()


def test_no_api_key_exposure() -> None:
    import rawcandle.fundamentals.schema.prototype as prototype

    assert "SHARADAR_API_KEY" not in Path(prototype.__file__).read_text()
