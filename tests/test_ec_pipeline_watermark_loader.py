import sqlite3
from pathlib import Path

import pytest

from rawcandle.ec_pipeline_watermark_loader import (
    advance_ec_pipeline_watermarks_after_historical_backfill,
    load_ec_pipeline_watermark_from_dc,
)
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
        "taxonomy_version_id": None,
        "taxonomy_lineage_recorded": False,
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


def test_historical_backfill_advances_only_canonical_fact_watermarks_forward(tmp_path) -> None:
    target_db = _setup_target_db(tmp_path)
    with _connect(str(target_db)) as conn:
        conn.executemany(
            """
            INSERT INTO ec_pipeline_watermark (
                ecosystem_id,
                pipeline_name,
                source_table,
                latest_signal_date,
                latest_run_id,
                status,
                created_at_utc,
                updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "TICKER_SWING_BASE", "dc_ticker_swing_signal_daily", "2026-07-28", None, "OK", "2026-07-28T00:00:00Z", "2026-07-28T00:00:00Z"),
                (1, "GROUP_SWING_BASE", "dc_group_swing_signal_daily", "2026-07-30", None, "OK", "2026-07-30T00:00:00Z", "2026-07-30T00:00:00Z"),
                (1, "SYNTHETIC_OHLC_RELATIVE", "dc_group_synthetic_ohlc_daily", "2026-07-20", None, "OK", "2026-07-20T00:00:00Z", "2026-07-20T00:00:00Z"),
                (1, "DAILY_REPORT", "UNKNOWN:DAILY_REPORT", "2026-07-20", None, "OK", "2026-07-20T00:00:00Z", "2026-07-20T00:00:00Z"),
            ],
        )
        conn.commit()

    summary = advance_ec_pipeline_watermarks_after_historical_backfill(
        target_db_path=str(target_db),
        latest_signal_date="2026-07-29",
    )

    with _connect(str(target_db)) as conn:
        rows = conn.execute(
            """
            SELECT pipeline_name, source_table, latest_signal_date, status
            FROM ec_pipeline_watermark
            ORDER BY pipeline_name, source_table
            """
        ).fetchall()

    assert summary["status"] == "OK"
    assert summary["watermark_refresh_performed"] is True
    assert summary["watermark_advanced"] is True
    assert summary["watermark_candidate_latest_signal_date"] == "2026-07-29"
    assert summary["watermark_rows_inserted"] == 2
    assert summary["watermark_rows_updated"] == 1
    assert summary["watermark_rows_unchanged"] == 1
    assert summary["watermark_rows_total"] == 4
    assert rows == [
        ("DAILY_REPORT", "UNKNOWN:DAILY_REPORT", "2026-07-20", "OK"),
        ("GROUP_INDEX", "dc_group_index_daily", "2026-07-29", "OK"),
        ("GROUP_SWING_BASE", "dc_group_swing_signal_daily", "2026-07-30", "OK"),
        ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily", "2026-07-29", "OK"),
        ("SYNTHETIC_OHLC_RELATIVE", "dc_group_synthetic_ohlc_daily", "2026-07-20", "OK"),
        ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily", "2026-07-29", "OK"),
    ]


def test_historical_backfill_watermark_noops_when_canonical_heads_are_newer(tmp_path) -> None:
    target_db = _setup_target_db(tmp_path)
    canonical_rows = [
        ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily"),
        ("GROUP_SWING_BASE", "dc_group_swing_signal_daily"),
        ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily"),
        ("GROUP_INDEX", "dc_group_index_daily"),
    ]
    with _connect(str(target_db)) as conn:
        conn.executemany(
            """
            INSERT INTO ec_pipeline_watermark (
                ecosystem_id,
                pipeline_name,
                source_table,
                latest_signal_date,
                latest_run_id,
                status,
                created_at_utc,
                updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, pipeline_name, source_table, "2026-07-30", None, "OK", "2026-07-30T00:00:00Z", "2026-07-30T00:00:00Z")
                for pipeline_name, source_table in canonical_rows
            ],
        )
        conn.commit()

    summary = advance_ec_pipeline_watermarks_after_historical_backfill(
        target_db_path=str(target_db),
        latest_signal_date="2026-07-29",
    )

    with _connect(str(target_db)) as conn:
        latest_dates = [
            row[0]
            for row in conn.execute(
                "SELECT latest_signal_date FROM ec_pipeline_watermark ORDER BY pipeline_name"
            ).fetchall()
        ]

    assert summary["watermark_advanced"] is False
    assert summary["watermark_rows_inserted"] == 0
    assert summary["watermark_rows_updated"] == 0
    assert summary["watermark_rows_unchanged"] == 4
    assert latest_dates == ["2026-07-30", "2026-07-30", "2026-07-30", "2026-07-30"]


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
