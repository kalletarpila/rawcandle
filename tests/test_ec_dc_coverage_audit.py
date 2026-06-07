import csv
import sqlite3
from pathlib import Path

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_datacenter_watchlist_loader import load_datacenter_watchlist_to_ec_sidecar
from rawcandle.ec_dc_coverage_audit import audit_dc_facts_against_ec_sidecar
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _write_taxonomy_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerow(["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""])
        writer.writerow(["DC_TAXONOMY_FULL_V1", "AMD", "Compute silicon", "GPUs", "WATCH_ONLY", 1, 0.7, ""])
        writer.writerow(["DC_TAXONOMY_FULL_V1", "AVGO", "Networking", "Switch silicon", "CORE", 1, 1.0, ""])


def _write_watchlist(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_analysis_db(path: Path, *, ticker_rows: list[tuple[str, str]], group_rows: list[tuple[str, str]], synthetic_rows: list[tuple[str, str]], index_rows: list[tuple[str, str]] | None = None, signal_date: str = "2026-06-05") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_group_index_daily (
                index_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO dc_ticker_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?)",
            [(signal_date, ticker) for _, ticker in ticker_rows],
        )
        conn.executemany(
            "INSERT INTO dc_group_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)",
            [(signal_date, group_type, group_name) for group_type, group_name in group_rows],
        )
        conn.executemany(
            "INSERT INTO dc_group_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)",
            [("2026-06-04", group_type, group_name) for group_type, group_name in group_rows[:1]],
        )
        conn.executemany(
            "INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)",
            [(signal_date, group_type, group_name) for group_type, group_name in synthetic_rows],
        )
        for rows in (index_rows or []):
            conn.execute(
                "INSERT INTO dc_group_index_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)",
                (signal_date, rows[0], rows[1]),
            )
        conn.commit()
    finally:
        conn.close()


def _setup_ec_db(tmp_path, watchlist_lines: list[str]) -> tuple[Path, Path]:
    ec_db_path = tmp_path / "ec.db"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    apply_ec_sidecar_migration(str(ec_db_path))
    _write_taxonomy_csv(taxonomy_path)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(ec_db_path),
        taxonomy_csv_path=str(taxonomy_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    _write_watchlist(watchlist_path, watchlist_lines)
    load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(ec_db_path),
        watchlist_path=str(watchlist_path),
    )
    return ec_db_path, watchlist_path


def _default_group_rows() -> list[tuple[str, str]]:
    return [
        ("ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ("layer", "Compute silicon"),
        ("layer", "Networking"),
        ("subindustry", "GPUs"),
        ("subindustry", "Switch silicon"),
    ]


def test_audit_returns_ok_when_all_tickers_groups_and_watchlist_map(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA", "AMD"])
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA"), ("2026-06-05", "AMD"), ("2026-06-05", "AVGO")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=_default_group_rows(),
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "OK"
    assert summary["dc_ticker_count"] == 3
    assert summary["ec_ticker_count"] == 3
    assert summary["matched_ticker_count"] == 3
    assert summary["missing_in_ec_tickers"] == []
    assert summary["watchlist_missing_tickers"] == []
    assert summary["dc_group_count"] == 5
    assert summary["matched_group_count"] == 5
    assert summary["dc_synthetic_group_count"] == 5
    assert summary["matched_synthetic_group_count"] == 5
    assert summary["dc_group_index_status"] == "CHECKED"
    assert summary["matched_group_index_count"] == 5


def test_audit_reports_watchlist_only_ticker_as_warning_not_failure(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA", "CRGY"])
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA"), ("2026-06-05", "AMD"), ("2026-06-05", "AVGO")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["watchlist_member_count"] == 2
    assert summary["watchlist_missing_tickers"] == []
    assert summary["watchlist_only_tickers"] == ["CRGY"]
    assert summary["watchlist_without_taxonomy_membership_tickers"] == ["CRGY"]
    assert summary["watchlist_without_dc_fact_tickers"] == ["CRGY"]
    assert summary["tickers_without_primary_group_l2"] == []
    assert summary["ticker_primary_membership_ok"] is True


def test_audit_fails_when_dc_ticker_is_missing_in_ec(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA"), ("2026-06-05", "CRGY")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert summary["missing_in_ec_tickers"] == ["CRGY"]


def test_audit_fails_when_ecosystem_alias_is_missing(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    with _connect(str(ec_db)) as conn:
        conn.execute("DELETE FROM ec_entity_alias WHERE alias_value = 'DC_ECOSYSTEM_TOTAL'")
        conn.commit()
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert {"group_type": "ecosystem", "group_name": "DC_ECOSYSTEM_TOTAL"} in summary["missing_group_rows"]


def test_audit_reports_ticker_without_primary_group_l2(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    with _connect(str(ec_db)) as conn:
        conn.execute(
            """
            UPDATE ec_membership
            SET is_primary = 0
            WHERE child_entity_id = (
                SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER' AND entity_code = 'NVDA'
            )
            """
        )
        conn.commit()
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert summary["ticker_primary_membership_ok"] is False
    assert summary["tickers_without_primary_group_l2"] == ["NVDA"]


def test_audit_fails_when_taxonomy_ticker_without_dc_fact_lacks_primary_group_l2(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    with _connect(str(ec_db)) as conn:
        conn.execute(
            """
            UPDATE ec_membership
            SET is_primary = 0
            WHERE child_entity_id = (
                SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER' AND entity_code = 'AMD'
            )
            """
        )
        conn.commit()
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA"), ("2026-06-05", "AVGO")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert summary["ticker_primary_membership_ok"] is False
    assert summary["tickers_without_primary_group_l2"] == ["AMD"]


def test_audit_reports_ticker_with_multiple_primary_group_l2(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    with _connect(str(ec_db)) as conn:
        nvda_id = conn.execute(
            "SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER' AND entity_code = 'NVDA'"
        ).fetchone()[0]
        accelerators_id = conn.execute(
            """
            INSERT INTO ec_entity (ecosystem_id, entity_type, entity_code, entity_name, ticker, status)
            VALUES (1, 'GROUP_L2', 'ACCELERATORS', 'Accelerators', NULL, 'ACTIVE')
            RETURNING entity_id
            """
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO ec_membership (
                ecosystem_id, taxonomy_version_id, parent_entity_id, child_entity_id,
                membership_type, membership_role, is_primary, role_weight, status, source_note
            ) VALUES (1, 1, ?, ?, 'CONTAINS', 'EXTENDED', 1, 0.5, 'ACTIVE', NULL)
            """,
            (accelerators_id, nvda_id),
        )
        conn.commit()
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert summary["tickers_with_multiple_primary_group_l2"] == ["NVDA"]


def test_audit_reports_group_l2_without_parent_group_l1(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    with _connect(str(ec_db)) as conn:
        conn.execute(
            """
            DELETE FROM ec_membership
            WHERE parent_entity_id IN (
                SELECT entity_id FROM ec_entity WHERE entity_type = 'GROUP_L1'
            )
              AND child_entity_id IN (
                SELECT entity_id FROM ec_entity WHERE entity_type = 'GROUP_L2' AND entity_name = 'GPUs'
            )
            """
        )
        conn.commit()
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db))

    assert summary["status"] == "FAILED"
    assert summary["group_l2_without_parent_group_l1"] == ["GPUs"]


def test_audit_resolves_latest_signal_date_when_not_provided(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.db"
    ec_db, _ = _setup_ec_db(tmp_path, ["NVDA"])
    _create_analysis_db(
        analysis_db,
        ticker_rows=[("2026-06-05", "NVDA")],
        group_rows=_default_group_rows(),
        synthetic_rows=_default_group_rows(),
        index_rows=[],
        signal_date="2026-06-05",
    )

    summary = audit_dc_facts_against_ec_sidecar(str(analysis_db), str(ec_db), signal_date=None)

    assert summary["selected_signal_date"] == "2026-06-05"
    assert summary["selected_synthetic_date"] == "2026-06-05"
