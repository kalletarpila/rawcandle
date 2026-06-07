import csv
import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_datacenter_taxonomy_loader import load_datacenter_taxonomy_to_ec_sidecar
from rawcandle.ec_datacenter_watchlist_loader import (
    _parse_watchlist_tickers,
    load_datacenter_watchlist_to_ec_sidecar,
)
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


def _setup_db_with_taxonomy(tmp_path) -> tuple[Path, Path]:
    db_path = tmp_path / "watchlist_loader.db"
    taxonomy_path = tmp_path / "taxonomy.csv"
    apply_ec_sidecar_migration(str(db_path))
    _write_taxonomy_csv(taxonomy_path)
    load_datacenter_taxonomy_to_ec_sidecar(
        db_path=str(db_path),
        taxonomy_csv_path=str(taxonomy_path),
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
    )
    return db_path, taxonomy_path


def test_watchlist_loader_creates_watchlist_and_members(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["NVDA", "AMD", "AVGO"])

    summary = load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )

    conn = _connect(str(db_path))
    try:
        watchlist_row = conn.execute(
            """
            SELECT watchlist_code, watchlist_name, source_type, source_reference, status
            FROM ec_watchlist
            """
        ).fetchone()
        assert watchlist_row == (
            "DATACENTER_WATCHLIST",
            "Datacenter Watchlist",
            "TXT",
            str(watchlist_path),
            "ACTIVE",
        )

        member_rows = conn.execute(
            """
            SELECT e.entity_code, wm.member_role, wm.status, wm.active_from
            FROM ec_watchlist_member wm
            JOIN ec_entity e ON e.entity_id = wm.entity_id
            ORDER BY e.entity_code
            """
        ).fetchall()
        assert member_rows == [
            ("AMD", "WATCH", "ACTIVE", "1900-01-01"),
            ("AVGO", "WATCH", "ACTIVE", "1900-01-01"),
            ("NVDA", "WATCH", "ACTIVE", "1900-01-01"),
        ]

        assert summary == {
            "status": "OK",
            "ecosystem_code": "DATACENTER",
            "watchlist_code": "DATACENTER_WATCHLIST",
            "watchlist_name": "Datacenter Watchlist",
            "source_ticker_count": 3,
            "unique_ticker_count": 3,
            "loaded_member_count": 3,
            "missing_ticker_count": 0,
            "missing_tickers": [],
            "duplicate_ticker_count": 0,
            "warnings": [],
        }
    finally:
        conn.close()


def test_watchlist_loader_deduplicates_in_file_order_and_ignores_comments(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["# comment", " nvda ", "", "AMD", "NVDA", "avgo", "AMD"])

    parsed = _parse_watchlist_tickers(watchlist_path)
    assert parsed == (["NVDA", "AMD", "AVGO"], 5, 2)

    summary = load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["source_ticker_count"] == 5
    assert summary["unique_ticker_count"] == 3
    assert summary["duplicate_ticker_count"] == 2


def test_watchlist_loader_reports_missing_ticker_and_loads_valid_members(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["NVDA", "CRGY", "AMD"])

    summary = load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )

    conn = _connect(str(db_path))
    try:
        member_count = conn.execute("SELECT COUNT(*) FROM ec_watchlist_member").fetchone()[0]
        assert member_count == 2
        assert summary["status"] == "OK_WITH_WARNINGS"
        assert summary["loaded_member_count"] == 2
        assert summary["missing_ticker_count"] == 1
        assert summary["missing_tickers"] == ["CRGY"]
    finally:
        conn.close()


def test_watchlist_loader_returns_no_valid_members_when_all_tickers_are_missing(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["CRGY", "XYZX"])

    summary = load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )

    conn = _connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM ec_watchlist").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ec_watchlist_member").fetchone()[0] == 0
        assert summary["status"] == "NO_VALID_MEMBERS"
        assert summary["loaded_member_count"] == 0
        assert summary["missing_tickers"] == ["CRGY", "XYZX"]
    finally:
        conn.close()


def test_watchlist_loader_refuses_duplicate_load_when_replace_existing_false(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["NVDA"])

    load_datacenter_watchlist_to_ec_sidecar(
        db_path=str(db_path),
        watchlist_path=str(watchlist_path),
    )

    with pytest.raises(ValueError, match="Target watchlist already exists"):
        load_datacenter_watchlist_to_ec_sidecar(
            db_path=str(db_path),
            watchlist_path=str(watchlist_path),
            replace_existing=False,
        )


def test_watchlist_loader_replace_existing_true_not_implemented(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["NVDA"])

    with pytest.raises(NotImplementedError, match="replace_existing=True is not implemented"):
        load_datacenter_watchlist_to_ec_sidecar(
            db_path=str(db_path),
            watchlist_path=str(watchlist_path),
            replace_existing=True,
        )


def test_watchlist_loader_fails_when_ecosystem_is_missing(tmp_path) -> None:
    db_path = tmp_path / "missing_ecosystem.db"
    watchlist_path = tmp_path / "watchlist.txt"
    apply_ec_sidecar_migration(str(db_path))
    _write_watchlist(watchlist_path, ["NVDA"])

    with pytest.raises(ValueError, match="Required ec_ecosystem row not found"):
        load_datacenter_watchlist_to_ec_sidecar(
            db_path=str(db_path),
            watchlist_path=str(watchlist_path),
        )


def test_watchlist_loader_fails_when_required_ec_tables_are_missing(tmp_path) -> None:
    db_path = tmp_path / "missing_tables.db"
    watchlist_path = tmp_path / "watchlist.txt"
    sqlite3.connect(db_path).close()
    _write_watchlist(watchlist_path, ["NVDA"])

    with pytest.raises(ValueError, match="Missing required ec_ sidecar tables"):
        load_datacenter_watchlist_to_ec_sidecar(
            db_path=str(db_path),
            watchlist_path=str(watchlist_path),
        )


def test_watchlist_loader_fails_when_no_valid_tickers_found(tmp_path) -> None:
    db_path, _ = _setup_db_with_taxonomy(tmp_path)
    watchlist_path = tmp_path / "watchlist.txt"
    _write_watchlist(watchlist_path, ["", "   ", "# comment"])

    with pytest.raises(ValueError, match="did not contain any valid tickers"):
        load_datacenter_watchlist_to_ec_sidecar(
            db_path=str(db_path),
            watchlist_path=str(watchlist_path),
        )
