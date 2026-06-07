import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_pipeline_watermark_loader import load_ec_pipeline_watermark_from_dc
from rawcandle.ec_sidecar_migration import apply_ec_sidecar_migration


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_source_db(path: Path, rows: list[dict[str, object]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE dc_pipeline_watermark (
                component_name TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                market TEXT NULL,
                signal_version TEXT NULL,
                calc_version TEXT NULL,
                start_date TEXT NULL,
                end_date TEXT NULL,
                row_count INTEGER NULL,
                status TEXT NOT NULL,
                last_successful_run_id TEXT NULL,
                last_successful_at_utc TEXT NULL,
                notes TEXT NULL,
                PRIMARY KEY (component_name, taxonomy_version, market, signal_version, calc_version)
            )
            """
        )
        columns = list(rows[0].keys()) if rows else []
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO dc_pipeline_watermark ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _source_row(
    *,
    component_name: str,
    market: str = "usa",
    signal_version: str | None = "DC_SWING_SIGNAL_V1",
    calc_version: str | None = None,
    end_date: str = "2026-06-05",
    status: str = "OK",
    last_successful_run_id: str | None = None,
    last_successful_at_utc: str | None = None,
) -> dict[str, object]:
    return {
        "component_name": component_name,
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": market,
        "signal_version": signal_version,
        "calc_version": calc_version,
        "start_date": "2020-01-01",
        "end_date": end_date,
        "row_count": 42,
        "status": status,
        "last_successful_run_id": last_successful_run_id,
        "last_successful_at_utc": last_successful_at_utc,
        "notes": None,
    }


def _setup_target_db(tmp_path) -> Path:
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    target_db = tmp_path / "target.db"
    apply_ec_sidecar_migration(str(target_db))
    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_ecosystem (
                ecosystem_code,
                ecosystem_name,
                status
            ) VALUES (?, ?, ?)
            """,
            ("DATACENTER", "Datacenter", "ACTIVE"),
        )
        conn.commit()
    return target_db


def test_loader_maps_known_components_and_existing_run_ids(tmp_path) -> None:
    source_db = tmp_path / "source.db"
    target_db = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(
                component_name="GROUP_INDEX",
                signal_version=None,
                last_successful_run_id="existing-run",
                last_successful_at_utc="2026-06-07T05:10:00Z",
            ),
            _source_row(
                component_name="TICKER_SWING_BASE",
                calc_version=None,
                last_successful_run_id=None,
                last_successful_at_utc=None,
            ),
        ],
    )

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_signal_run (
                run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, source_mode, status, started_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("existing-run", 1, None, "2026-06-05", "GROUP_INDEX", "TEST", "OK", "2026-06-07T05:10:00Z"),
        )
        conn.commit()

    summary = load_ec_pipeline_watermark_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT pipeline_name, source_table, latest_signal_date, latest_run_id, status
            FROM ec_pipeline_watermark
            ORDER BY pipeline_name
            """
        ).fetchall()
        assert rows == [
            ("GROUP_INDEX", "dc_group_index_daily", "2026-06-05", "existing-run", "OK"),
            ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily", "2026-06-05", None, "OK"),
        ]
        assert conn.execute("SELECT COUNT(*) FROM ec_ticker_signal_daily").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ec_group_synthetic_ohlc_daily").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ec_group_index_daily").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ec_signal_run WHERE run_id != 'existing-run'").fetchone()[0] == 0

    assert summary == {
        "status": "OK_WITH_WARNINGS",
        "ecosystem_code": "DATACENTER",
        "taxonomy_version_code": "DC_TAXONOMY_FULL_V1",
        "source_table": "dc_pipeline_watermark",
        "source_row_count": 2,
        "loaded_row_count": 2,
        "failed_row_count": 0,
        "component_count": 2,
        "component_name_to_source_table": {
            "GROUP_INDEX": "dc_group_index_daily",
            "TICKER_SWING_BASE": "dc_ticker_swing_signal_daily",
        },
        "unknown_components": [],
        "empty_last_successful_run_id_count": 1,
        "unmatched_latest_run_ids": [],
        "warnings": [
            "Source watermark rows had empty last_successful_run_id: 1",
        ],
    }


def test_loader_unmatched_run_id_is_left_null_without_creating_fake_run(tmp_path) -> None:
    source_db = tmp_path / "source_unmatched_run.db"
    target_db = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(
                component_name="GROUP_SWING_BASE",
                market="",
                calc_version="",
                last_successful_run_id="missing-run",
                last_successful_at_utc="2026-06-07T05:15:00Z",
            ),
        ],
    )

    summary = load_ec_pipeline_watermark_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    with _connect(str(target_db)) as conn:
        row = conn.execute(
            """
            SELECT latest_run_id, created_at_utc
            FROM ec_pipeline_watermark
            WHERE pipeline_name = 'GROUP_SWING_BASE'
            """
        ).fetchone()
        assert row[0] is None
        assert row[1] == "2026-06-07T05:15:00Z"
        assert conn.execute("SELECT COUNT(*) FROM ec_signal_run").fetchone()[0] == 0

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["unmatched_latest_run_ids"] == ["missing-run"]


def test_loader_unknown_component_maps_to_unknown_prefix_with_warning(tmp_path) -> None:
    source_db = tmp_path / "source_unknown_component.db"
    target_db = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(
                component_name="WEEKLY_REPORT",
                market="",
                calc_version="DC_SWING_OHLC_V1",
                last_successful_run_id=None,
            ),
        ],
    )

    summary = load_ec_pipeline_watermark_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )

    with _connect(str(target_db)) as conn:
        row = conn.execute(
            """
            SELECT source_table, latest_run_id
            FROM ec_pipeline_watermark
            WHERE pipeline_name = 'WEEKLY_REPORT'
            """
        ).fetchone()
        assert row == ("UNKNOWN:WEEKLY_REPORT", None)

    assert summary["status"] == "OK_WITH_WARNINGS"
    assert summary["unknown_components"] == ["WEEKLY_REPORT"]
    assert summary["component_name_to_source_table"]["WEEKLY_REPORT"] == "UNKNOWN:WEEKLY_REPORT"


def test_loader_duplicate_scope_requires_replace_existing_and_replace_is_scoped(tmp_path) -> None:
    source_db = tmp_path / "source_replace.db"
    target_db = _setup_target_db(tmp_path)
    _create_source_db(
        source_db,
        [
            _source_row(component_name="GROUP_INDEX", signal_version=None),
        ],
    )

    first_summary = load_ec_pipeline_watermark_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
    )
    assert first_summary["loaded_row_count"] == 1

    with pytest.raises(ValueError, match="Target pipeline watermark rows already exist"):
        load_ec_pipeline_watermark_from_dc(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            replace_existing=False,
        )

    with _connect(str(target_db)) as conn:
        conn.execute(
            """
            INSERT INTO ec_pipeline_watermark (
                ecosystem_id, pipeline_name, source_table, latest_signal_date, latest_run_id, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "TICKER_SWING_BASE", "dc_ticker_swing_signal_daily", "2026-06-04", None, "WARN", "2026-06-07T00:00:00Z"),
        )
        conn.commit()

    _create_source_db(
        source_db,
        [
            _source_row(component_name="GROUP_INDEX", signal_version=None, end_date="2026-06-06", status="WARN"),
        ],
    )
    summary = load_ec_pipeline_watermark_from_dc(
        source_db_path=str(source_db),
        target_db_path=str(target_db),
        replace_existing=True,
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT pipeline_name, source_table, latest_signal_date, status
            FROM ec_pipeline_watermark
            ORDER BY pipeline_name
            """
        ).fetchall()
        assert rows == [
            ("GROUP_INDEX", "dc_group_index_daily", "2026-06-06", "WARN"),
            ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily", "2026-06-04", "WARN"),
        ]
    assert summary["loaded_row_count"] == 1

