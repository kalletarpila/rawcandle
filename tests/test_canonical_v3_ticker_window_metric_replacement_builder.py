import sqlite3
from datetime import date, timedelta

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_ticker_window_metric_replacement_builder import (
    build_canonical_v3_ticker_window_metrics,
)


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29"
LOWER_LEVEL_RUN_ID = "DC_TICKER_SWING_20260603_DC_SWING_SIGNAL_V1"
FALLBACK_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1_FALLBACK"
TARGET_WINDOWS = ("rolling2", "rolling5", "rolling30")
TARGET_METRICS = (
    "breakout_days",
    "pullback_days",
    "exit_risk_days",
    "high_exit_risk_days",
    "medium_exit_risk_days",
    "valid_signal_dates",
    "distance_to_ema20_pct",
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


def _create_group_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            signal_version TEXT
        )
        """
    )


def _create_ticker_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            breakout_signal INTEGER,
            pullback_signal INTEGER,
            exit_risk_signal INTEGER,
            exit_risk_severity TEXT,
            distance_to_ema20_pct REAL,
            signal_version TEXT,
            run_id TEXT
        )
        """
    )


def _insert_group_source_rows(conn: sqlite3.Connection) -> None:
    rows = [("2026-04-16", "DC_TAXONOMY_FULL_V1", "layer", "DATACENTER", "DC_SWING_SIGNAL_V1")]
    rows.extend(
        (current_date, "DC_TAXONOMY_FULL_V1", "layer", "DATACENTER", "DC_SWING_SIGNAL_V1")
        for current_date in ROLLING30_DATES
    )
    conn.executemany(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, group_type, group_name, signal_version
        ) VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def _aaa_source_row(current_date: str) -> tuple:
    breakout = 1 if current_date in {"2026-05-22", "2026-05-28", "2026-04-24"} else 0
    pullback = 1 if current_date in {"2026-05-27", "2026-05-14"} else 0
    exit_risk = 1 if current_date in {"2026-05-29", "2026-05-26", "2026-05-08"} else 0
    severity = None
    if current_date in {"2026-05-29", "2026-05-14"}:
        severity = "HIGH"
    elif current_date in {"2026-05-26", "2026-05-08"}:
        severity = "MEDIUM"
    distance = 9.29 if current_date == SIGNAL_DATE else round(len(current_date) / 100.0, 4)
    return (
        current_date,
        "DC_TAXONOMY_FULL_V1",
        "AAA",
        breakout,
        pullback,
        exit_risk,
        severity,
        distance,
        "DC_SWING_SIGNAL_V1",
        LOWER_LEVEL_RUN_ID,
    )


def _bbb_source_row(current_date: str) -> tuple:
    breakout = 1 if current_date == "2026-05-29" else 0
    pullback = 1 if current_date == "2026-05-27" else 0
    exit_risk = 1 if current_date == "2026-05-28" else 0
    severity = "MEDIUM" if current_date == "2026-05-28" else None
    distance = None if current_date == SIGNAL_DATE else 1.5
    return (
        current_date,
        "DC_TAXONOMY_FULL_V1",
        "BBB",
        breakout,
        pullback,
        exit_risk,
        severity,
        distance,
        FALLBACK_SIGNAL_VERSION,
        None,
    )


def _ddd_source_row(current_date: str) -> tuple:
    latest_five = set(ROLLING5_DATES)
    if current_date in latest_five:
        signal_version = "DDD_OK"
        run_id = LOWER_LEVEL_RUN_ID
    else:
        signal_version = "DDD_MIX_A" if int(current_date[-2:]) % 2 == 0 else "DDD_MIX_B"
        run_id = "DDD_RUN_A" if int(current_date[-2:]) % 2 == 0 else "DDD_RUN_B"
    breakout = 1 if current_date in {"2026-05-28", "2026-05-21"} else 0
    pullback = 1 if current_date == "2026-05-27" else 0
    exit_risk = 1 if current_date == "2026-05-29" else 0
    severity = "HIGH" if current_date == "2026-05-29" else None
    distance = 4.2 if current_date == SIGNAL_DATE else 2.2
    return (
        current_date,
        "DC_TAXONOMY_FULL_V1",
        "DDD",
        breakout,
        pullback,
        exit_risk,
        severity,
        distance,
        signal_version,
        run_id,
    )


def _insert_ticker_source_rows(conn: sqlite3.Connection) -> None:
    rows = [_aaa_source_row(current_date) for current_date in ROLLING30_DATES]
    rows.append(
        (
            "2026-05-25",
            "DC_TAXONOMY_FULL_V1",
            "AAA",
            1,
            1,
            1,
            "HIGH",
            99.0,
            "DC_SWING_SIGNAL_V1",
            LOWER_LEVEL_RUN_ID,
        )
    )
    rows.extend(_bbb_source_row(current_date) for current_date in ROLLING30_DATES)
    rows.extend(_ddd_source_row(current_date) for current_date in ROLLING30_DATES)
    conn.executemany(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, ticker, breakout_signal, pullback_signal,
            exit_risk_signal, exit_risk_severity, distance_to_ema20_pct, signal_version, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        "breakout_days": "trading_days",
        "pullback_days": "trading_days",
        "exit_risk_days": "trading_days",
        "high_exit_risk_days": "trading_days",
        "medium_exit_risk_days": "trading_days",
        "valid_signal_dates": "count",
        "distance_to_ema20_pct": "percent",
    }
    rows = []
    for entity_code in ("AAA", "BBB", "CCC", "DDD"):
        for window_code in TARGET_WINDOWS:
            for metric_name in TARGET_METRICS:
                rows.append(
                    (
                        RUN_ID,
                        ecosystem_id,
                        SIGNAL_DATE,
                        taxonomy_version_id,
                        window_code,
                        entity_ids[entity_code],
                        metric_name,
                        999.0,
                        None,
                        unit_by_metric[metric_name],
                        "OK",
                        SOURCE_RUN_ID,
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
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'distance_to_ema20_pct', 77.0, NULL, 'percent', 'OK', 'KEEP_DAILY')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'daily', ?, 'freshness_latest_bos_age_trading_days', 12, NULL, 'trading_days', 'OK', 'KEEP_FRESHNESS')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, ticker_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'group_current_status', NULL, 'BUY_ZONE', NULL, 'OK', 'KEEP_GROUP')
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, layer_entity_id),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, 'rolling5', ?, 'distance_to_ema20_pct', 11.0, NULL, 'percent', 'OK', 'KEEP_LAYER_SCOPE')
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
        "AAA": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="AAA", entity_name="AAA", ticker="AAA"),
        "BBB": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="BBB", entity_name="BBB", ticker="BBB"),
        "CCC": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="CCC", entity_name="CCC", ticker="CCC"),
        "DDD": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="TICKER", entity_code="DDD", entity_name="DDD", ticker="DDD"),
        "LAYER_ONE": _insert_entity(conn, ecosystem_id=ecosystem_id, entity_type="LAYER", entity_code="LAYER_ONE", entity_name="Layer one"),
    }

    _create_group_source_table(conn)
    _create_ticker_source_table(conn)
    _insert_group_source_rows(conn)
    _insert_ticker_source_rows(conn)
    if include_run:
        for ticker in ("AAA", "BBB", "CCC", "DDD"):
            for window_code in TARGET_WINDOWS:
                _insert_coverage(
                    conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    entity_id=entity_ids[ticker],
                    window_code=window_code,
                )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["AAA"],
            window_code="daily",
        )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_ids["LAYER_ONE"],
            window_code="rolling5",
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
        build_canonical_v3_ticker_window_metrics(str(db_path), RUN_ID, replace_existing=True)


def test_replace_existing_false_rejects_existing_target_rows(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    _setup_db(str(db_path))

    with pytest.raises(ValueError, match="replace_existing=False"):
        build_canonical_v3_ticker_window_metrics(str(db_path), RUN_ID, replace_existing=False)


def test_builder_replaces_only_target_ticker_window_metrics_and_preserves_other_rows(tmp_path) -> None:
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

    summary = build_canonical_v3_ticker_window_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert summary["entity_type"] == "TICKER"
    assert summary["window_codes"] == list(TARGET_WINDOWS)
    assert summary["selected_ticker_entity_count_by_window"] == {
        "rolling2": 4,
        "rolling5": 4,
        "rolling30": 4,
    }
    assert summary["selected_window_dates"] == {
        "rolling2": ROLLING2_DATES,
        "rolling5": ROLLING5_DATES,
        "rolling30": ROLLING30_DATES,
    }
    assert summary["source_rows_read_by_window"] == {
        "rolling2": 6,
        "rolling5": 15,
        "rolling30": 90,
    }
    assert summary["source_rows_mapped_by_window"] == {
        "rolling2": 3,
        "rolling5": 3,
        "rolling30": 2,
    }
    assert summary["source_rows_skipped_by_window"] == {
        "rolling2": 0,
        "rolling5": 0,
        "rolling30": 1,
    }
    assert summary["missing_source_tickers_by_window"] == {
        "rolling2": ["CCC"],
        "rolling5": ["CCC"],
        "rolling30": ["CCC"],
    }
    assert summary["metric_rows_inserted"] == 53
    assert summary["rows_deleted_on_replace"] == 84
    assert summary["mixed_source_run_warning_count"] == 1
    assert summary["warning_count"] == 4
    assert "Missing lower-level ticker history for rolling2 ticker 'CCC'" in summary["warnings"]
    assert "Mixed lower-level lineage for rolling30 ticker 'DDD'" in " ".join(summary["warnings"])
    assert summary["metric_name_counts"] == {
        "breakout_days": 8,
        "pullback_days": 8,
        "exit_risk_days": 8,
        "high_exit_risk_days": 8,
        "medium_exit_risk_days": 8,
        "valid_signal_dates": 8,
        "distance_to_ema20_pct": 5,
    }
    assert summary["metric_name_counts_by_window"] == {
        "rolling2": {
            "breakout_days": 3,
            "pullback_days": 3,
            "exit_risk_days": 3,
            "high_exit_risk_days": 3,
            "medium_exit_risk_days": 3,
            "valid_signal_dates": 3,
            "distance_to_ema20_pct": 2,
        },
        "rolling5": {
            "breakout_days": 3,
            "pullback_days": 3,
            "exit_risk_days": 3,
            "high_exit_risk_days": 3,
            "medium_exit_risk_days": 3,
            "valid_signal_dates": 3,
            "distance_to_ema20_pct": 2,
        },
        "rolling30": {
            "breakout_days": 2,
            "pullback_days": 2,
            "exit_risk_days": 2,
            "high_exit_risk_days": 2,
            "medium_exit_risk_days": 2,
            "valid_signal_dates": 2,
            "distance_to_ema20_pct": 1,
        },
    }
    assert summary["metric_unit_counts"] == {
        "trading_days": 40,
        "count": 8,
        "percent": 5,
    }
    assert summary["metric_value_status_counts"] == {"OK": 53}
    assert summary["source_run_id_counts"] == {
        LOWER_LEVEL_RUN_ID: 35,
        FALLBACK_SIGNAL_VERSION: 18,
    }
    assert "latest-N valid signal_date semantics are used, not calendar-day semantics" in summary["limitations"]

    conn = _connect(str(db_path))
    assert conn.execute(
        """
        SELECT metric_value_num
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling5' AND metric_name = 'breakout_days'
        """,
        (RUN_ID, entity_ids["AAA"]),
    ).fetchone()[0] == 2
    assert conn.execute(
        """
        SELECT metric_value_num
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling2' AND metric_name = 'valid_signal_dates'
        """,
        (RUN_ID, entity_ids["AAA"]),
    ).fetchone()[0] == 2
    assert conn.execute(
        """
        SELECT metric_value_num
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling30' AND metric_name = 'valid_signal_dates'
        """,
        (RUN_ID, entity_ids["AAA"]),
    ).fetchone()[0] == 30
    assert conn.execute(
        """
        SELECT metric_value_num
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling5' AND metric_name = 'distance_to_ema20_pct'
        """,
        (RUN_ID, entity_ids["AAA"]),
    ).fetchone()[0] == 9.29
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND metric_name = 'distance_to_ema20_pct'
          AND window_code IN ('rolling2','rolling5','rolling30')
        """,
        (RUN_ID, entity_ids["BBB"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND metric_name IN (
            'breakout_days','pullback_days','exit_risk_days','high_exit_risk_days',
            'medium_exit_risk_days','valid_signal_dates'
        ) AND window_code IN ('rolling2','rolling5','rolling30')
        """,
        (RUN_ID, entity_ids["BBB"]),
    ).fetchone()[0] == 18
    assert [
        tuple(row)
        for row in conn.execute(
        """
        SELECT DISTINCT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code IN ('rolling2','rolling5','rolling30')
        ORDER BY source_run_id
        """,
        (RUN_ID, entity_ids["BBB"]),
    ).fetchall()
    ] == [(FALLBACK_SIGNAL_VERSION,)]
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code IN ('rolling2','rolling5','rolling30')
          AND metric_name IN ('breakout_days','pullback_days','exit_risk_days','high_exit_risk_days','medium_exit_risk_days','valid_signal_dates','distance_to_ema20_pct')
        """,
        (RUN_ID, entity_ids["CCC"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling30'
          AND metric_name IN ('breakout_days','pullback_days','exit_risk_days','high_exit_risk_days','medium_exit_risk_days','valid_signal_dates','distance_to_ema20_pct')
        """,
        (RUN_ID, entity_ids["DDD"]),
    ).fetchone()[0] == 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling5'
          AND metric_name IN ('breakout_days','pullback_days','exit_risk_days','high_exit_risk_days','medium_exit_risk_days','valid_signal_dates','distance_to_ema20_pct')
        """,
        (RUN_ID, entity_ids["DDD"]),
    ).fetchone()[0] == 7
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND window_code = 'daily' AND entity_id = ? AND metric_name = 'distance_to_ema20_pct'
        """,
        (RUN_ID, entity_ids["AAA"]),
    ).fetchone()[0] == "KEEP_DAILY"
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND metric_name = 'freshness_latest_bos_age_trading_days'
        """,
        (RUN_ID,),
    ).fetchone()[0] == "KEEP_FRESHNESS"
    preserved_group_row = conn.execute(
        """
        SELECT source_run_id, metric_value_text
        FROM eco_entity_metric_value
        WHERE run_id = ? AND metric_name = 'group_current_status'
        """,
        (RUN_ID,),
    ).fetchone()
    assert tuple(preserved_group_row) == ("KEEP_GROUP", "BUY_ZONE")
    assert conn.execute(
        """
        SELECT source_run_id
        FROM eco_entity_metric_value
        WHERE run_id = ? AND entity_id = ? AND window_code = 'rolling5' AND metric_name = 'distance_to_ema20_pct'
        """,
        (RUN_ID, entity_ids["LAYER_ONE"]),
    ).fetchone()[0] == "KEEP_LAYER_SCOPE"
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

    first = build_canonical_v3_ticker_window_metrics(str(db_path), RUN_ID, replace_existing=True)
    second = build_canonical_v3_ticker_window_metrics(str(db_path), RUN_ID, replace_existing=True)

    assert first["metric_rows_inserted"] == second["metric_rows_inserted"] == 53
    assert second["rows_deleted_on_replace"] == 53
    conn = _connect(str(db_path))
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND e.entity_type = 'TICKER'
          AND m.window_code IN ('rolling2','rolling5','rolling30')
          AND m.metric_name IN (
            'breakout_days','pullback_days','exit_risk_days','high_exit_risk_days',
            'medium_exit_risk_days','valid_signal_dates','distance_to_ema20_pct'
          )
        """,
        (RUN_ID,),
    ).fetchone()[0] == 53
    conn.close()
