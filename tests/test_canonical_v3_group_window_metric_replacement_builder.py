import sqlite3

import pytest

from rawcandle.report_canonical_v3_group_window_metric_replacement_builder import (
    build_canonical_v3_group_window_metrics,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
V2_SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"
GROUP_SOURCE_RUN_ID = "DC_GROUP_SWING_20260604_DC_SWING_SIGNAL_V1"
SYNTH_SOURCE_RUN_ID = "DC_GROUP_SYNTH_OHLC_20250801_20260604_DC_SWING_OHLC_V1"
TARGET_ENTITY_TYPES = ("LAYER", "SUBINDUSTRY")
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
TARGET_METRICS = (
    "pct_above_ema20",
    "return_5d",
    "synthetic_close",
    "trend_breadth",
    "weakness_breadth",
    "valid_signal_dates",
)
ROLLING2_DATES = ["2026-05-28", "2026-05-29"]
ROLLING5_DATES = ["2026-05-22", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
ROLLING30_DATES = [
    "2026-04-17",
    "2026-04-20",
    "2026-04-21",
    "2026-04-22",
    "2026-04-23",
    "2026-04-24",
    "2026-04-27",
    "2026-04-28",
    "2026-04-29",
    "2026-04-30",
    "2026-05-01",
    "2026-05-04",
    "2026-05-05",
    "2026-05-06",
    "2026-05-07",
    "2026-05-08",
    "2026-05-11",
    "2026-05-12",
    "2026-05-13",
    "2026-05-14",
    "2026-05-15",
    "2026-05-18",
    "2026-05-19",
    "2026-05-20",
    "2026-05-21",
    "2026-05-22",
    "2026-05-26",
    "2026-05-27",
    "2026-05-28",
    "2026-05-29",
]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_ecosystem (ecosystem_code, ecosystem_name, status)
            VALUES ('DATACENTER', 'Datacenter', 'ACTIVE')
            """
        ).lastrowid
    )


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_taxonomy_version (
                ecosystem_id, version_code, version_label, is_active, status
            ) VALUES (?, 'DC_TAXONOMY_FULL_V1', 'V1', 1, 'ACTIVE')
            """,
            (ecosystem_id,),
        ).lastrowid
    )


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date, run_type, status, warning_count, error_count
        ) VALUES (?, ?, ?, ?, 'BUILD', 'OK', 0, 0)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE),
    )


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str,
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, status
            ) VALUES (?, ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, entity_type, entity_code, entity_name),
        ).lastrowid
    )


def _insert_coverage(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
    window_code: str,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_coverage (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            in_taxonomy, in_watchlist, has_instrument, has_price_data, has_daily_signal,
            has_window_context, coverage_status, source_row_count, missing_component_count
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 1, 1, 'OK', 1, 0)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, window_code, entity_id),
    )


def _create_group_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            pct_above_ema20 REAL,
            return_5d REAL,
            trend_breadth REAL,
            weakness_breadth REAL,
            signal_version TEXT,
            run_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL,
            calc_version TEXT,
            run_id TEXT
        )
        """
    )


def _insert_group_swing_rows(conn: sqlite3.Connection) -> None:
    all_dates = ["2026-04-16", *ROLLING30_DATES]
    rows = []
    for current_date in all_dates:
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "layer",
                "AI Compute",
                72.5 if current_date == SIGNAL_DATE else 70.0,
                0.115 if current_date == SIGNAL_DATE else 0.09,
                61.0 if current_date == SIGNAL_DATE else 59.0,
                18.0 if current_date == SIGNAL_DATE else 20.0,
                "GROUP_SIGNAL_V1",
                GROUP_SOURCE_RUN_ID,
            )
        )
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "subindustry",
                "GPU",
                83.0 if current_date == SIGNAL_DATE else 82.0,
                0.225 if current_date == SIGNAL_DATE else 0.2,
                75.0 if current_date == SIGNAL_DATE else 74.0,
                None if current_date == SIGNAL_DATE else 9.0,
                "GROUP_SIGNAL_V1",
                GROUP_SOURCE_RUN_ID,
            )
        )
        mixed_run_id = "MIXED_A" if int(current_date[-2:]) % 2 == 0 else "MIXED_B"
        mixed_signal_version = "MIXED_SV_A" if int(current_date[-2:]) % 2 == 0 else "MIXED_SV_B"
        if current_date == SIGNAL_DATE:
            mixed_run_id = GROUP_SOURCE_RUN_ID
            mixed_signal_version = "GROUP_SIGNAL_V1"
        rows.append(
            (
                current_date,
                "DC_TAXONOMY_FULL_V1",
                "subindustry",
                "Networking",
                44.0 if current_date == SIGNAL_DATE else 43.0,
                0.035 if current_date == SIGNAL_DATE else 0.03,
                39.0 if current_date == SIGNAL_DATE else 38.0,
                28.0 if current_date == SIGNAL_DATE else 29.0,
                mixed_signal_version,
                mixed_run_id,
            )
        )
    conn.executemany(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, group_type, group_name,
            pct_above_ema20, return_5d, trend_breadth, weakness_breadth, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_group_synthetic_rows(conn: sqlite3.Connection) -> None:
    rows = [
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "layer",
            "AI Compute",
            150.5,
            "GROUP_SYNTH_V1",
            SYNTH_SOURCE_RUN_ID,
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "subindustry",
            "GPU",
            275.25,
            "GROUP_SYNTH_V1",
            SYNTH_SOURCE_RUN_ID,
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "subindustry",
            "Networking",
            88.0,
            "GROUP_SYNTH_V1",
            SYNTH_SOURCE_RUN_ID,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, group_type, group_name, synthetic_close, calc_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_existing_target_metric_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_ids: dict[str, int],
) -> None:
    unit_by_metric = {
        "pct_above_ema20": "percent",
        "return_5d": "percent",
        "synthetic_close": "points",
        "trend_breadth": "percent",
        "weakness_breadth": "percent",
        "valid_signal_dates": "count",
    }
    rows = []
    for entity_key in ("AI_LAYER", "GPU_SUB", "NET_SUB", "MISSING_LAYER"):
        for window_code in TARGET_WINDOWS:
            for metric_name in TARGET_METRICS:
                if metric_name == "valid_signal_dates" and window_code == "daily":
                    continue
                rows.append(
                    (
                        RUN_ID,
                        ecosystem_id,
                        SIGNAL_DATE,
                        taxonomy_version_id,
                        window_code,
                        entity_ids[entity_key],
                        metric_name,
                        999.0,
                        None,
                        unit_by_metric[metric_name],
                        "OK",
                        V2_SOURCE_RUN_ID,
                    )
                )
    conn.executemany(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_preserved_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    ticker_entity_id: int,
    layer_entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'distance_to_ema20_pct', 77.0, NULL, 'percent', 'OK', 'KEEP_TICKER')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'freshness_latest_bos_age_trading_days', 12.0, NULL, 'trading_days', 'OK', 'KEEP_FRESHNESS')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'group_current_status', NULL, 'BUY_ZONE', NULL, 'OK', 'KEEP_GROUP_STATUS')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, layer_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'group_timing_state', NULL, 'EXIT_ZONE', NULL, 'OK', 'KEEP_UNRELATED_GROUP_METRIC')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, layer_entity_id),
    )


def _insert_unrelated_fact_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            snapshot_status, quality_status
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'OK', 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
            quality_scope, scope_entity_id, quality_status
        ) VALUES (?, ?, ?, ?, 'rolling5', 'RUN', ?, 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'TEST_SIGNAL', 'TEST', 'UP', 'YES', ?, 'src', 'src_run', 'evt1', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )
    signal_observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label
        ) VALUES (?, 'RELEVANT')
        """,
        (signal_observation_id,),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id, event_date, event_type,
            source_table, source_run_id, source_event_id, event_key, event_status
        ) VALUES (?, ?, ?, ?, ?, 'BOS', 'src', 'src_run', 'evt1', 'event-key', 'ACTIVE')
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, entity_id, SIGNAL_DATE),
    )
    conn.execute(
        """
        INSERT INTO eco_classification_decision (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            classification_type, classification_state, primary_reason,
            source_classifier, classification_version, source_run_id, decision_status
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'rolling5_pullback', 'NO_PULLBACK', 'NONE',
                  'rolling5_pullback_classifier', 'V3', 'SRC', 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _setup_db(db_path: str, *, include_run: bool = True) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    if include_run:
        _insert_run(conn, ecosystem_id, taxonomy_version_id)

    entity_ids = {
        "AI_LAYER": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="AI_LAYER", entity_name="AI Compute"
        ),
        "GPU_SUB": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="SUBINDUSTRY", entity_code="GPU_SUB", entity_name="GPU"
        ),
        "NET_SUB": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="SUBINDUSTRY", entity_code="NET_SUB", entity_name="Networking"
        ),
        "MISSING_LAYER": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="MISSING_LAYER", entity_name="Power"
        ),
        "AAA": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="AAA", entity_name="AAA"
        ),
        "ECO": _insert_entity(
            conn, ecosystem_id=ecosystem_id, entity_type="ECOSYSTEM", entity_code="ECO", entity_name="Datacenter"
        ),
    }

    _create_group_source_tables(conn)
    _insert_group_swing_rows(conn)
    _insert_group_synthetic_rows(conn)

    if include_run:
        for entity_key in ("AI_LAYER", "GPU_SUB", "NET_SUB", "MISSING_LAYER"):
            for window_code in TARGET_WINDOWS:
                _insert_coverage(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_ids[entity_key],
                    window_code=window_code,
                )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["AAA"],
            window_code="daily",
        )
        _insert_existing_target_metric_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_ids=entity_ids,
        )
        _insert_preserved_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            ticker_entity_id=entity_ids["AAA"],
            layer_entity_id=entity_ids["AI_LAYER"],
        )
        _insert_unrelated_fact_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["AAA"],
        )

    conn.commit()
    conn.close()
    return entity_ids


def test_builder_requires_existing_run(tmp_path):
    db_path = tmp_path / "group-window-metrics-no-run.db"
    _setup_db(str(db_path), include_run=False)

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_group_window_metrics(str(db_path), RUN_ID, replace_existing=True)


def test_replace_existing_false_rejects_existing_target_rows(tmp_path):
    db_path = tmp_path / "group-window-metrics-existing.db"
    _setup_db(str(db_path))

    with pytest.raises(ValueError, match="existing target metric rows"):
        build_canonical_v3_group_window_metrics(str(db_path), RUN_ID, replace_existing=False)


def test_builder_replaces_only_group_window_target_scope_and_reports_summary(tmp_path):
    db_path = tmp_path / "group-window-metrics.db"
    entity_ids = _setup_db(str(db_path))

    summary = build_canonical_v3_group_window_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert summary["entity_types"] == ["LAYER", "SUBINDUSTRY"]
    assert summary["window_codes"] == ["daily", "rolling2", "rolling5", "rolling30"]
    assert summary["selected_group_entity_count_by_type"] == {"LAYER": 2, "SUBINDUSTRY": 2}
    assert summary["selected_group_entity_count_by_window"] == {
        "daily": 4,
        "rolling2": 4,
        "rolling5": 4,
        "rolling30": 4,
    }
    assert summary["selected_window_dates"]["daily"] == [SIGNAL_DATE]
    assert summary["selected_window_dates"]["rolling2"] == ROLLING2_DATES
    assert summary["selected_window_dates"]["rolling5"] == ROLLING5_DATES
    assert summary["selected_window_dates"]["rolling30"] == ROLLING30_DATES
    assert summary["rows_deleted_on_replace"] == 92
    assert summary["metric_rows_inserted"] == 62
    assert summary["metric_name_counts"] == {
        "pct_above_ema20": 12,
        "return_5d": 12,
        "synthetic_close": 12,
        "trend_breadth": 12,
        "valid_signal_dates": 6,
        "weakness_breadth": 8,
    }
    assert summary["metric_name_counts_by_window"]["daily"] == {
        "pct_above_ema20": 3,
        "return_5d": 3,
        "synthetic_close": 3,
        "trend_breadth": 3,
        "weakness_breadth": 2,
    }
    assert summary["metric_name_counts_by_entity_type"]["LAYER"]["synthetic_close"] == 4
    assert summary["metric_name_counts_by_entity_type"]["SUBINDUSTRY"]["valid_signal_dates"] == 3
    assert summary["source_run_id_counts"][GROUP_SOURCE_RUN_ID] == 50
    assert summary["source_run_id_counts"][SYNTH_SOURCE_RUN_ID] == 12
    assert summary["metric_unit_counts"] == {
        "percent": 44,
        "points": 12,
        "count": 6,
    }
    assert summary["metric_value_status_counts"] == {"OK": 62}
    assert summary["mixed_source_run_warning_count"] == 3
    assert summary["source_rows_read_by_table"] == {
        "dc_group_swing_signal_daily": 114,
        "dc_group_synthetic_ohlc_daily": 3,
    }
    assert summary["source_rows_mapped_by_table"] == {
        "dc_group_swing_signal_daily": 12,
        "dc_group_synthetic_ohlc_daily": 12,
    }
    assert summary["source_rows_skipped_by_table"] == {
        "dc_group_swing_signal_daily": 7,
        "dc_group_synthetic_ohlc_daily": 4,
    }
    assert any("Power" in warning for warning in summary["warnings"])
    assert any("Networking" in warning for warning in summary["warnings"])
    assert any(entry.startswith("dc_group_swing_signal_daily:LAYER:Power") for entry in summary["missing_source_groups"])
    assert any(
        entry.startswith("dc_group_synthetic_ohlc_daily:LAYER:Power") for entry in summary["missing_source_groups"]
    )
    assert "replaces only LAYER/SUBINDUSTRY group window metrics" in summary["limitations"]
    assert "ticker metrics are not modified" in summary["limitations"]

    conn = _connect(str(db_path))
    target_rows = conn.execute(
        """
        SELECT
            e.entity_type,
            e.entity_name,
            m.window_code,
            m.metric_name,
            m.metric_value_num,
            m.metric_unit,
            m.source_run_id
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND e.entity_type IN ('LAYER', 'SUBINDUSTRY')
          AND m.window_code IN ('daily', 'rolling2', 'rolling5', 'rolling30')
          AND m.metric_name IN ('pct_above_ema20', 'return_5d', 'synthetic_close', 'trend_breadth', 'weakness_breadth', 'valid_signal_dates')
        ORDER BY e.entity_type, e.entity_name, m.window_code, m.metric_name
        """,
        (RUN_ID,),
    ).fetchall()
    assert len(target_rows) == 62
    assert all(row["entity_type"] in TARGET_ENTITY_TYPES for row in target_rows)
    assert all(row["metric_name"] in TARGET_METRICS for row in target_rows)
    assert all(row["window_code"] in TARGET_WINDOWS for row in target_rows)

    rows_by_key = {
        (row["entity_name"], row["window_code"], row["metric_name"]): row for row in target_rows
    }
    assert rows_by_key[("AI Compute", "daily", "pct_above_ema20")]["metric_value_num"] == pytest.approx(72.5)
    assert rows_by_key[("AI Compute", "rolling30", "synthetic_close")]["metric_value_num"] == pytest.approx(150.5)
    assert rows_by_key[("GPU", "rolling5", "return_5d")]["metric_value_num"] == pytest.approx(0.225)
    assert rows_by_key[("GPU", "rolling2", "trend_breadth")]["metric_value_num"] == pytest.approx(75.0)
    assert ("GPU", "daily", "valid_signal_dates") not in rows_by_key
    assert ("GPU", "daily", "weakness_breadth") not in rows_by_key
    assert rows_by_key[("AI Compute", "rolling2", "valid_signal_dates")]["metric_value_num"] == pytest.approx(2.0)
    assert rows_by_key[("AI Compute", "rolling5", "valid_signal_dates")]["metric_value_num"] == pytest.approx(5.0)
    assert rows_by_key[("AI Compute", "rolling30", "valid_signal_dates")]["metric_value_num"] == pytest.approx(30.0)
    assert ("Networking", "rolling2", "valid_signal_dates") not in rows_by_key
    assert ("Networking", "rolling5", "valid_signal_dates") not in rows_by_key
    assert ("Networking", "rolling30", "valid_signal_dates") not in rows_by_key
    assert ("Power", "daily", "pct_above_ema20") not in rows_by_key
    assert all(row["metric_unit"] in ("percent", "points", "count") for row in target_rows)

    # Preserved rows and unrelated facts remain untouched.
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE entity_id = ? AND metric_name = 'distance_to_ema20_pct'
        """,
        (entity_ids["AAA"],),
    ).fetchone()[0] == "KEEP_TICKER"
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE entity_id = ? AND metric_name = 'group_current_status'
        """,
        (entity_ids["AI_LAYER"],),
    ).fetchone()[0] == "KEEP_GROUP_STATUS"
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == 1
    conn.close()


def test_builder_is_idempotent_with_replace_existing_true(tmp_path):
    db_path = tmp_path / "group-window-metrics-idempotent.db"
    _setup_db(str(db_path))

    first_summary = build_canonical_v3_group_window_metrics(str(db_path), RUN_ID, replace_existing=True)
    second_summary = build_canonical_v3_group_window_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert first_summary["metric_rows_inserted"] == second_summary["metric_rows_inserted"] == 62
    assert second_summary["rows_deleted_on_replace"] == 62

    conn = _connect(str(db_path))
    duplicate_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT entity_id, window_code, metric_name, COUNT(*) AS n
            FROM eco_entity_metric_value
            WHERE run_id = ?
              AND metric_name IN ('pct_above_ema20', 'return_5d', 'synthetic_close', 'trend_breadth', 'weakness_breadth', 'valid_signal_dates')
            GROUP BY entity_id, window_code, metric_name
            HAVING COUNT(*) > 1
        )
        """,
        (RUN_ID,),
    ).fetchone()[0]
    assert duplicate_count == 0
    conn.close()
