import sqlite3

import pytest

from rawcandle.report_canonical_v3_ma_status_builder import build_canonical_v3_ma_status
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_RUN_ID = "MA_STATUS_SOURCE_RUN"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code,
            ecosystem_name,
            description,
            status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id,
            version_code,
            version_label,
            source_type,
            source_reference,
            effective_from,
            effective_to,
            is_active,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, "DC_TAXONOMY_FULL_V1", "V1", None, None, None, None, 1, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    entity_type: str,
    entity_code: str,
    entity_name: str,
    ticker: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id,
            entity_type,
            entity_code,
            entity_name,
            ticker,
            exchange,
            market,
            currency,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ecosystem_id, entity_type, entity_code, entity_name, ticker, None, None, None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            run_type,
            status,
            warning_count,
            error_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, taxonomy_version_id, SIGNAL_DATE, "BUILD", "OK", 0, 0),
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
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            in_taxonomy,
            in_watchlist,
            has_instrument,
            has_price_data,
            has_daily_signal,
            has_window_context,
            coverage_status,
            source_row_count,
            missing_component_count,
            coverage_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            window_code,
            entity_id,
            1,
            1,
            1,
            1,
            1,
            1,
            "OK",
            1,
            0,
            None,
        ),
    )


def _create_source_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            above_ma10 INTEGER NULL,
            above_ema10 INTEGER NULL,
            above_ema20 INTEGER NULL,
            distance_to_ma10_pct REAL NULL,
            distance_to_ema10_pct REAL NULL,
            distance_to_ema20_pct REAL NULL,
            ema10_slope_positive INTEGER NULL,
            ema20_slope_positive INTEGER NULL,
            price_data_status TEXT NULL,
            signal_version TEXT NULL,
            run_id TEXT NULL
        )
        """
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    above_ma10: int | None,
    above_ema10: int | None,
    above_ema20: int | None,
    run_id: str = SOURCE_RUN_ID,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date,
            taxonomy_version,
            ticker,
            above_ma10,
            above_ema10,
            above_ema20,
            distance_to_ma10_pct,
            distance_to_ema10_pct,
            distance_to_ema20_pct,
            ema10_slope_positive,
            ema20_slope_positive,
            price_data_status,
            signal_version,
            run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            ticker,
            above_ma10,
            above_ema10,
            above_ema20,
            None,
            None,
            None,
            None,
            None,
            "OK",
            "signal-v1",
            run_id,
        ),
    )


def _insert_supporting_rows(
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
            snapshot_status, timing_state, trend_state, summary_state, classification_state,
            freshness_status, quality_status, asof_observed_at, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            entity_id,
            "OK",
            None,
            None,
            None,
            None,
            None,
            "OK",
            SIGNAL_DATE,
            "baseline",
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
            quality_scope, scope_entity_id, quality_status, expected_count, actual_count,
            missing_count, incomplete_count, stale_count, warning_count, error_count, summary_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            "RUN",
            entity_id,
            "OK",
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            "baseline",
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            entity_id,
            "baseline_metric",
            1.0,
            None,
            None,
            "OK",
            "baseline",
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id, ecosystem_id, taxonomy_version_id, entity_id,
            event_date, event_type, source_table, source_run_id, source_event_id,
            event_key, event_label, event_direction, event_status, event_payload_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            taxonomy_version_id,
            entity_id,
            SIGNAL_DATE,
            "UNKNOWN",
            "baseline",
            "baseline",
            "1",
            f"baseline:{entity_id}",
            "baseline",
            "NONE",
            "ACTIVE",
            None,
        ),
    )


def _seed_db(db_path: str) -> dict[str, int]:
    apply_report_canonical_v3_migration(db_path)
    conn = _connect(db_path)
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    nvda_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="TICKER",
        entity_code="NVDA",
        entity_name="NVIDIA",
        ticker="NVDA",
    )
    amd_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="TICKER",
        entity_code="AMD",
        entity_name="AMD",
        ticker="AMD",
    )
    crgy_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="TICKER",
        entity_code="CRGY",
        entity_name="Crescent Energy",
        ticker="CRGY",
    )
    layer_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="LAYER",
        entity_code="AI_COMPUTE",
        entity_name="AI Compute",
    )
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=nvda_id,
        window_code="daily",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=amd_id,
        window_code="daily",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=crgy_id,
        window_code="daily",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=nvda_id,
        window_code="rolling2",
    )
    _insert_coverage(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=layer_id,
        window_code="daily",
    )
    _create_source_table(conn)
    _insert_source_row(conn, ticker="NVDA", above_ma10=1, above_ema10=0, above_ema20=None)
    _insert_source_row(conn, ticker="AMD", above_ma10=0, above_ema10=1, above_ema20=1)
    _insert_source_row(conn, ticker="ORCL", above_ma10=1, above_ema10=1, above_ema20=1)
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
            signal_name, signal_family, signal_direction, signal_value, observed_date,
            source_table, source_run_id, source_event_id, signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            nvda_id,
            "STRUCTURE_FRESHNESS",
            "FRESHNESS",
            "UNKNOWN",
            "FRESH",
            SIGNAL_DATE,
            "dc_report_context_daily_v2",
            "freshness-run",
            "freshness:NVDA",
            "ACTIVE",
        ),
    )
    _insert_supporting_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=nvda_id,
    )
    conn.commit()
    conn.close()
    return {
        "ecosystem_id": ecosystem_id,
        "taxonomy_version_id": taxonomy_version_id,
        "nvda_id": nvda_id,
        "amd_id": amd_id,
        "crgy_id": crgy_id,
        "layer_id": layer_id,
    }


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "ma-status-missing-run.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    _create_source_table(conn)
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_ma_status(str(db_path), RUN_ID)


def test_builder_writes_ma_status_signal_rows_and_summary(tmp_path) -> None:
    db_path = tmp_path / "ma-status.db"
    ids = _seed_db(str(db_path))

    summary = build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)

    assert summary["source_classifications"] == {"dc_ticker_swing_signal_daily": "DERIVED_FROM_RAW_SOURCE"}
    assert summary["selected_ticker_entity_count"] == 3
    assert summary["source_rows_read"] == 2
    assert summary["source_rows_mapped"] == 2
    assert summary["source_rows_skipped"] == 0
    assert summary["missing_source_tickers"] == ["CRGY"]
    assert summary["signal_observations_inserted"] == 6
    assert summary["signal_name_counts"] == {
        "EMA10_STATUS": 2,
        "EMA20_STATUS": 2,
        "MA10_STATUS": 2,
    }
    assert "this is MA_STATUS, not MA_BREAK" in summary["limitations"]
    assert "daily/TICKER only" in summary["limitations"]

    conn = _connect(str(db_path))
    rows = conn.execute(
        """
        SELECT entity_id, window_code, signal_name, signal_family, signal_value, signal_direction, signal_status,
               source_table, source_run_id, source_event_id
        FROM eco_signal_observation
        WHERE signal_family = 'MA_STATUS'
        ORDER BY entity_id, signal_name
        """
    ).fetchall()
    assert len(rows) == 6
    assert {row["window_code"] for row in rows} == {"daily"}
    assert {row["signal_family"] for row in rows} == {"MA_STATUS"}
    assert {row["source_table"] for row in rows} == {"dc_ticker_swing_signal_daily"}
    assert {row["source_run_id"] for row in rows} == {SOURCE_RUN_ID}
    assert not any(row["entity_id"] == ids["layer_id"] for row in rows)
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name != 'baseline_metric'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 0
    conn.close()


def test_value_mapping_covers_above_below_and_unknown(tmp_path) -> None:
    db_path = tmp_path / "ma-status-values.db"
    ids = _seed_db(str(db_path))

    build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)

    conn = _connect(str(db_path))
    nvda = conn.execute(
        """
        SELECT signal_name, signal_value, signal_direction, signal_status
        FROM eco_signal_observation
        WHERE signal_family = 'MA_STATUS' AND entity_id = ?
        ORDER BY signal_name
        """,
        (ids["nvda_id"],),
    ).fetchall()
    amd = conn.execute(
        """
        SELECT signal_name, signal_value, signal_direction, signal_status
        FROM eco_signal_observation
        WHERE signal_family = 'MA_STATUS' AND entity_id = ?
        ORDER BY signal_name
        """,
        (ids["amd_id"],),
    ).fetchall()
    conn.close()

    assert [tuple(row) for row in nvda] == [
        ("EMA10_STATUS", "BELOW_EMA10", "DOWN", "ACTIVE"),
        ("EMA20_STATUS", "UNKNOWN", "UNKNOWN", "UNKNOWN"),
        ("MA10_STATUS", "ABOVE_MA10", "UP", "ACTIVE"),
    ]
    assert [tuple(row) for row in amd] == [
        ("EMA10_STATUS", "ABOVE_EMA10", "UP", "ACTIVE"),
        ("EMA20_STATUS", "ABOVE_EMA20", "UP", "ACTIVE"),
        ("MA10_STATUS", "BELOW_MA10", "DOWN", "ACTIVE"),
    ]


def test_replace_existing_is_idempotent_and_preserves_other_signal_families(tmp_path) -> None:
    db_path = tmp_path / "ma-status-replace.db"
    _seed_db(str(db_path))

    first_summary = build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)
    second_summary = build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)

    assert first_summary["signal_observations_inserted"] == 6
    assert second_summary["signal_observations_inserted"] == 6

    conn = _connect(str(db_path))
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'MA_STATUS'"
    ).fetchone()[0] == 6
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'FRESHNESS'"
    ).fetchone()[0] == 1
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_signal_observation
        GROUP BY run_id, signal_date, taxonomy_version_id, window_code, entity_id, signal_name, observed_date
        HAVING COUNT(*) > 1
        """
    ).fetchall() == []
    conn.close()


def test_replace_existing_false_rejects_and_relevance_blocks_replacement(tmp_path) -> None:
    db_path = tmp_path / "ma-status-relevance.db"
    _seed_db(str(db_path))

    build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)
    with pytest.raises(ValueError, match="MA_STATUS signal rows already exist"):
        build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=False)

    conn = _connect(str(db_path))
    signal_observation_id = conn.execute(
        """
        SELECT signal_observation_id
        FROM eco_signal_observation
        WHERE signal_family = 'MA_STATUS'
        ORDER BY signal_observation_id
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id, relevance_label, relevance_score, relevance_reason,
            trend_alignment, dow_context, bos_context, reset_context, counter_trend_context
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (signal_observation_id, "RELEVANT", 1.0, "block replace", None, None, None, None, None),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="relevance rows exist"):
        build_canonical_v3_ma_status(str(db_path), RUN_ID, replace_existing=True)
