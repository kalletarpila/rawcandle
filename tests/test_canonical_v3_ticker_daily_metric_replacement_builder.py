import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_ticker_daily_metric_replacement_builder import (
    build_canonical_v3_ticker_daily_direct_metrics,
)


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"
LOWER_LEVEL_RUN_ID = "DC_TICKER_SWING_20260603_DC_SWING_SIGNAL_V1"


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
    ticker: str | None = None,
) -> int:
    return int(
        conn.execute(
            """
            INSERT INTO eco_entity (
                ecosystem_id, entity_type, entity_code, entity_name, ticker, status
            ) VALUES (?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (ecosystem_id, entity_type, entity_code, entity_name, ticker),
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


def _create_source_table(conn: sqlite3.Connection, *, include_run_id: bool = True) -> None:
    source_run_sql = ", run_id TEXT NOT NULL" if include_run_id else ""
    conn.execute(
        f"""
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            distance_to_ema10_pct REAL,
            distance_to_ema20_pct REAL,
            return_5d REAL,
            return_10d REAL,
            return_20d REAL,
            return_60d REAL,
            latest_bos_age_trading_days INTEGER,
            latest_reset_age_trading_days INTEGER,
            latest_structure_age_trading_days INTEGER,
            signal_version TEXT NOT NULL
            {source_run_sql}
        )
        """
    )


def _insert_source_rows(conn: sqlite3.Connection, *, include_run_id: bool = True) -> None:
    rows = [
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "AAA",
            0.11,
            0.22,
            1.1,
            2.2,
            3.3,
            4.4,
            5,
            6,
            7,
            "DC_SWING_SIGNAL_V1",
            LOWER_LEVEL_RUN_ID,
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "BBB",
            0.44,
            None,
            8.8,
            None,
            9.9,
            None,
            10,
            None,
            11,
            "DC_SWING_SIGNAL_V1",
            LOWER_LEVEL_RUN_ID,
        ),
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            "DDD",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "DC_SWING_SIGNAL_V1",
            LOWER_LEVEL_RUN_ID,
        ),
    ]
    if include_run_id:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    else:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [row[:-1] for row in rows],
        )


def _insert_existing_target_metric_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_ids: dict[str, int],
) -> None:
    percent_metrics = {
        "distance_to_ema10_pct",
        "distance_to_ema20_pct",
        "return_5d",
        "return_10d",
        "return_20d",
        "return_60d",
    }
    age_metrics = {
        "latest_bos_age_trading_days",
        "latest_reset_age_trading_days",
        "latest_structure_age_trading_days",
    }
    rows = []
    for entity_id in entity_ids.values():
        for metric_name in (*percent_metrics, *age_metrics):
            rows.append(
                (
                    RUN_ID,
                    ecosystem_id,
                    SIGNAL_DATE,
                    taxonomy_version_id,
                    "daily",
                    entity_id,
                    metric_name,
                    999.0,
                    None,
                    "percent" if metric_name in percent_metrics else "trading_days",
                    "OK",
                    SOURCE_RUN_ID,
                )
            )
    conn.executemany(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'freshness_latest_bos_age_trading_days', 12, NULL, 'trading_days', 'OK', 'DC_TICKER_SWING_OLD')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'distance_to_ema20_pct', 55.0, NULL, 'percent', 'OK', 'KEEP_ROLLING')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'group_current_status', NULL, 'BUY_ZONE', NULL, 'OK', 'KEEP_GROUP')
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
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'OK', 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
            quality_scope, scope_entity_id, quality_status
        ) VALUES (?, ?, ?, ?, 'daily', 'RUN', ?, 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'TEST_SIGNAL', 'TEST', 'UP', 'YES', ?, 'src', 'src_run', 'evt1', 'ACTIVE')
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
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'daily_trigger', 'NO_TRIGGER', 'NONE',
                  'daily_trigger_classifier', 'V3', 'SRC', 'OK')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, entity_id),
    )


def _setup_db(db_path: str, *, include_run: bool = True, include_run_id_column: bool = True) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    if include_run:
        _insert_run(conn, ecosystem_id, taxonomy_version_id)

    entity_ids = {
        "AAA": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="AAA", entity_name="AAA", ticker="AAA"),
        "BBB": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="BBB", entity_name="BBB", ticker="BBB"),
        "CCC": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="CCC", entity_name="CCC", ticker="CCC"),
        "DDD": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="DDD", entity_name="DDD", ticker="DDD"),
        "LAYER_ONE": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="LAYER_ONE", entity_name="Layer one"),
    }

    _create_source_table(conn, include_run_id=include_run_id_column)
    _insert_source_rows(conn, include_run_id=include_run_id_column)
    if include_run:
        for ticker in ("AAA", "BBB", "CCC", "DDD"):
            _insert_coverage(
                conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                entity_id=entity_ids[ticker],
                window_code="daily",
            )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["AAA"],
            window_code="rolling5",
        )
        _insert_existing_target_metric_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_ids={ticker: entity_ids[ticker] for ticker in ("AAA", "BBB", "CCC", "DDD")},
        )
        _insert_preserved_rows(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            ticker_entity_id=entity_ids["AAA"],
            layer_entity_id=entity_ids["LAYER_ONE"],
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


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    _setup_db(str(db_path), include_run=False)

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=True)


def test_replace_existing_false_rejects_existing_target_rows(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    _setup_db(str(db_path))

    with pytest.raises(ValueError, match="replace_existing=False"):
        build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=False)


def test_builder_replaces_only_target_daily_ticker_metrics_and_preserves_other_rows(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    entity_ids = _setup_db(str(db_path))
    conn = _connect(str(db_path))
    pre_counts = {
        "signals": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
        "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
        "events": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
        "classifications": conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0],
        "snapshots": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
        "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
        "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
        "runs": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
    }
    conn.close()

    summary = build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert summary["entity_type"] == "TICKER"
    assert summary["window_code"] == "daily"
    assert summary["selected_ticker_entity_count"] == 4
    assert summary["source_rows_read"] == 3
    assert summary["source_rows_mapped"] == 2
    assert summary["source_rows_skipped"] == 1
    assert summary["missing_source_tickers"] == ["CCC"]
    assert summary["metric_rows_inserted"] == 14
    assert summary["rows_deleted_on_replace"] == 36
    assert summary["warning_count"] == 1
    assert "Missing lower-level ticker row for daily ticker 'CCC'" in summary["warnings"]
    assert summary["metric_name_counts"] == {
        "distance_to_ema10_pct": 2,
        "distance_to_ema20_pct": 1,
        "return_5d": 2,
        "return_10d": 1,
        "return_20d": 2,
        "return_60d": 1,
        "latest_bos_age_trading_days": 2,
        "latest_reset_age_trading_days": 1,
        "latest_structure_age_trading_days": 2,
    }
    assert summary["metric_unit_counts"] == {"percent": 9, "trading_days": 5}
    assert summary["metric_value_status_counts"] == {"OK": 14}
    assert summary["source_run_id_counts"] == {LOWER_LEVEL_RUN_ID: 14}
    assert "replaces only ticker daily direct metrics" in summary["limitations"]

    conn = _connect(str(db_path))
    target_rows = conn.execute(
        """
        SELECT e.entity_code, m.metric_name, m.metric_value_num, m.metric_unit, m.source_run_id
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.window_code = 'daily'
          AND e.entity_type = 'TICKER'
          AND m.metric_name IN (
            'distance_to_ema10_pct','distance_to_ema20_pct','return_5d','return_10d',
            'return_20d','return_60d','latest_bos_age_trading_days',
            'latest_reset_age_trading_days','latest_structure_age_trading_days'
          )
        ORDER BY e.entity_code, m.metric_name
        """,
        (RUN_ID,),
    ).fetchall()
    assert len(target_rows) == 14
    assert {row["entity_code"] for row in target_rows} == {"AAA", "BBB"}
    assert {
        (row["entity_code"], row["metric_name"], row["metric_unit"], row["source_run_id"])
        for row in target_rows
    } >= {
        ("AAA", "distance_to_ema10_pct", "percent", LOWER_LEVEL_RUN_ID),
        ("AAA", "latest_bos_age_trading_days", "trading_days", LOWER_LEVEL_RUN_ID),
        ("BBB", "distance_to_ema10_pct", "percent", LOWER_LEVEL_RUN_ID),
        ("BBB", "latest_structure_age_trading_days", "trading_days", LOWER_LEVEL_RUN_ID),
    }
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND window_code = 'daily'
          AND entity_id = ?
          AND metric_name IN (
            'distance_to_ema20_pct','return_10d','return_60d','latest_reset_age_trading_days'
          )
        """,
        (RUN_ID, entity_ids["BBB"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND window_code = 'daily'
          AND entity_id = ?
          AND metric_name IN (
            'distance_to_ema10_pct','distance_to_ema20_pct','return_5d','return_10d',
            'return_20d','return_60d','latest_bos_age_trading_days',
            'latest_reset_age_trading_days','latest_structure_age_trading_days'
          )
        """,
        (RUN_ID, entity_ids["CCC"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND window_code = 'daily'
          AND entity_id = ?
          AND metric_name IN (
            'distance_to_ema10_pct','distance_to_ema20_pct','return_5d','return_10d',
            'return_20d','return_60d','latest_bos_age_trading_days',
            'latest_reset_age_trading_days','latest_structure_age_trading_days'
          )
        """,
        (RUN_ID, entity_ids["DDD"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND metric_name = 'freshness_latest_bos_age_trading_days'
        """,
        (RUN_ID,),
    ).fetchone()[0] == "DC_TICKER_SWING_OLD"
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND window_code = 'rolling5' AND metric_name = 'distance_to_ema20_pct'
        """,
        (RUN_ID,),
    ).fetchone()[0] == "KEEP_ROLLING"
    preserved_group_row = conn.execute(
        """
        SELECT source_run_id, metric_value_text
        FROM eco_entity_metric_value
        WHERE run_id = ? AND metric_name = 'group_current_status'
        """,
        (RUN_ID,),
    ).fetchone()
    assert tuple(preserved_group_row) == ("KEEP_GROUP", "BUY_ZONE")
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == pre_counts["signals"]
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == pre_counts["relevance"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == pre_counts["events"]
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == pre_counts["classifications"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == pre_counts["snapshots"]
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == pre_counts["coverage"]
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == pre_counts["quality"]
    assert conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0] == pre_counts["runs"]
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND value_status = 'MISSING'
        """,
        (RUN_ID,),
    ).fetchone()[0] == 0
    conn.close()


def test_replace_existing_true_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    _setup_db(str(db_path))

    first = build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=True)
    second = build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert first["metric_rows_inserted"] == second["metric_rows_inserted"] == 14
    assert second["rows_deleted_on_replace"] == 14
    conn = _connect(str(db_path))
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND m.window_code = 'daily'
          AND e.entity_type = 'TICKER'
          AND m.metric_name IN (
            'distance_to_ema10_pct','distance_to_ema20_pct','return_5d','return_10d',
            'return_20d','return_60d','latest_bos_age_trading_days',
            'latest_reset_age_trading_days','latest_structure_age_trading_days'
          )
        """,
        (RUN_ID,),
    ).fetchone()[0] == 14
    conn.close()


def test_builder_uses_signal_version_when_run_id_missing(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    _setup_db(str(db_path), include_run_id_column=False)

    summary = build_canonical_v3_ticker_daily_direct_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert summary["source_run_id_counts"] == {"DC_SWING_SIGNAL_V1": 14}
    conn = _connect(str(db_path))
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND source_run_id = 'DC_SWING_SIGNAL_V1'
        """,
        (RUN_ID,),
    ).fetchone()[0] == 14
    conn.close()
