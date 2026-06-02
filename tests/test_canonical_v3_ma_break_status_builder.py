import sqlite3
from datetime import date, timedelta

import pytest

import rawcandle.report_canonical_v3_ma_break_status_builder as ma_break_builder_module
from analysis.datacenter_indices.swing_ma_break_status import (
    build_swing_ma_break_status_rows,
    load_ticker_ma_history_rows,
)
from rawcandle.report_canonical_v3_ma_break_status_builder import build_canonical_v3_ma_break_status
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"
SOURCE_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
SOURCE_RUN_ID = "MA_BREAK_SOURCE_RUN"


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
            close REAL NULL,
            ema20 REAL NULL,
            signal_version TEXT NULL,
            run_id TEXT NULL
        )
        """
    )


def _insert_price_history(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    closes: list[float | None],
    ema20_overrides: dict[int, float | None] | None = None,
    signal_version: str = SOURCE_SIGNAL_VERSION,
    run_id: str = SOURCE_RUN_ID,
) -> None:
    ema20_overrides = ema20_overrides or {}
    start_day = date.fromisoformat(SIGNAL_DATE) - timedelta(days=len(closes) - 1)
    for offset, close_value in enumerate(closes):
        signal_day = (start_day + timedelta(days=offset)).isoformat()
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date,
                taxonomy_version,
                ticker,
                close,
                ema20,
                signal_version,
                run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_day,
                "DC_TAXONOMY_FULL_V1",
                ticker,
                close_value,
                ema20_overrides.get(offset),
                signal_version,
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
    abb_id = _insert_entity(
        conn,
        ecosystem_id=ecosystem_id,
        entity_type="TICKER",
        entity_code="ABB",
        entity_name="ABB",
        ticker="ABB",
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
    for entity_id in (nvda_id, amd_id, abb_id, crgy_id):
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=entity_id,
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

    ok_closes = [100.0 + float(i) for i in range(55)]
    break_closes = [100.0 + float(i) for i in range(50)] + [96.0, 95.0, 94.0, 93.0, 92.0]
    insufficient_closes = [50.0 + float(i) for i in range(10)]
    _insert_price_history(conn, ticker="NVDA", closes=ok_closes)
    _insert_price_history(conn, ticker="AMD", closes=break_closes)
    _insert_price_history(conn, ticker="ABB", closes=insufficient_closes)
    _insert_price_history(conn, ticker="ORCL", closes=ok_closes)

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
            "MA10_STATUS",
            "MA_STATUS",
            "UP",
            "ABOVE_MA10",
            SIGNAL_DATE,
            "dc_ticker_swing_signal_daily",
            "ma-status-run",
            "ma_status:NVDA",
            "ACTIVE",
        ),
    )
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
        "abb_id": abb_id,
        "crgy_id": crgy_id,
        "layer_id": layer_id,
    }


def _expected_algorithm_rows(db_path: str) -> list[dict[str, object]]:
    conn = _connect(db_path)
    latest_rows = [
        {key: row[key] for key in row.keys()}
        for row in conn.execute(
            """
            SELECT ticker, signal_date, close, ema20, signal_version, run_id
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker
            """,
            (SIGNAL_DATE, "DC_TAXONOMY_FULL_V1"),
        ).fetchall()
        if row["ticker"] in {"NVDA", "AMD", "ABB"}
    ]
    history_rows = load_ticker_ma_history_rows(
        conn,
        tickers=["NVDA", "AMD", "ABB"],
        as_of_date=SIGNAL_DATE,
        signal_version=SOURCE_SIGNAL_VERSION,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )
    conn.close()
    return build_swing_ma_break_status_rows(
        latest_rows=latest_rows,
        history_rows=history_rows,
        as_of_date=SIGNAL_DATE,
    )


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "ma-break-missing-run.db"
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    _create_source_table(conn)
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_ma_break_status(str(db_path), RUN_ID)


def test_builder_reuses_algorithm_and_writes_rows(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ma-break.db"
    ids = _seed_db(str(db_path))
    expected_rows = _expected_algorithm_rows(str(db_path))
    called = {"value": False}
    actual_func = ma_break_builder_module.build_swing_ma_break_status_rows

    def _wrapped(**kwargs):
        called["value"] = True
        return actual_func(**kwargs)

    monkeypatch.setattr(ma_break_builder_module, "build_swing_ma_break_status_rows", _wrapped)

    summary = build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)

    assert called["value"] is True
    assert summary["source_classifications"] == {"dc_ticker_swing_signal_daily": "DERIVED_FROM_RAW_SOURCE"}
    assert summary["selected_ticker_entity_count"] == 4
    assert summary["source_rows_read"] == 3
    assert summary["algorithm_rows_produced"] == 3
    assert summary["source_rows_mapped"] == 3
    assert summary["source_rows_skipped"] == 0
    assert summary["missing_source_tickers"] == ["CRGY"]
    assert summary["signal_observations_inserted"] == 3
    assert summary["signal_name_counts"] == {"MA_BREAK_STATUS": 3}
    assert "uses existing swing_ma_break_status algorithm" in summary["limitations"]
    assert "daily/TICKER only" in summary["limitations"]

    conn = _connect(str(db_path))
    rows = conn.execute(
        """
        SELECT entity_id, window_code, signal_name, signal_family, signal_value, signal_direction, signal_status,
               source_table, source_run_id, source_event_id
        FROM eco_signal_observation
        WHERE signal_family = 'MA_BREAK_STATUS'
        ORDER BY entity_id
        """
    ).fetchall()
    assert len(rows) == 3
    assert {row["window_code"] for row in rows} == {"daily"}
    assert {row["signal_name"] for row in rows} == {"MA_BREAK_STATUS"}
    assert {row["signal_family"] for row in rows} == {"MA_BREAK_STATUS"}
    assert {row["source_table"] for row in rows} == {"dc_ticker_swing_signal_daily"}
    assert not any(row["entity_id"] == ids["layer_id"] for row in rows)
    assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value WHERE metric_name != 'baseline_metric'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 0
    conn.close()

    expected_by_ticker = {row["ticker"]: row for row in expected_rows}
    conn = _connect(str(db_path))
    actual_by_ticker = {
        row["entity_code"]: row
        for row in conn.execute(
            """
            SELECT e.entity_code, o.signal_value, o.signal_direction, o.signal_status
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE o.signal_family = 'MA_BREAK_STATUS'
            ORDER BY e.entity_code
            """
        ).fetchall()
    }
    conn.close()
    for ticker, expected in expected_by_ticker.items():
        actual = actual_by_ticker[ticker]
        assert actual["signal_value"] == expected["ma_break_status"]


def test_value_mapping_and_scope(tmp_path) -> None:
    db_path = tmp_path / "ma-break-values.db"
    _seed_db(str(db_path))
    expected_rows = {row["ticker"]: row for row in _expected_algorithm_rows(str(db_path))}

    build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)

    conn = _connect(str(db_path))
    rows = conn.execute(
        """
        SELECT e.entity_code, o.window_code, o.signal_name, o.signal_value, o.signal_direction, o.signal_status
        FROM eco_signal_observation o
        JOIN eco_entity e ON e.entity_id = o.entity_id
        WHERE o.signal_family = 'MA_BREAK_STATUS'
        ORDER BY e.entity_code
        """
    ).fetchall()
    conn.close()

    assert [row["window_code"] for row in rows] == ["daily", "daily", "daily"]
    expected_directions = {}
    expected_statuses = {}
    for ticker, row in expected_rows.items():
        status = row["ma_break_status"]
        if status == "OK":
            expected_directions[ticker] = "NEUTRAL"
            expected_statuses[ticker] = "ACTIVE"
        elif status == "INSUFFICIENT_DATA":
            expected_directions[ticker] = "UNKNOWN"
            expected_statuses[ticker] = "UNKNOWN"
        else:
            expected_directions[ticker] = "DOWN"
            expected_statuses[ticker] = "ACTIVE"

    for row in rows:
        ticker = row["entity_code"]
        assert row["signal_name"] == "MA_BREAK_STATUS"
        assert row["signal_value"] == expected_rows[ticker]["ma_break_status"]
        assert row["signal_direction"] == expected_directions[ticker]
        assert row["signal_status"] == expected_statuses[ticker]


def test_replace_existing_is_idempotent_and_preserves_other_signal_families(tmp_path) -> None:
    db_path = tmp_path / "ma-break-replace.db"
    _seed_db(str(db_path))

    first_summary = build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)
    second_summary = build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)

    assert first_summary["signal_observations_inserted"] == 3
    assert second_summary["signal_observations_inserted"] == 3

    conn = _connect(str(db_path))
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'MA_BREAK_STATUS'"
    ).fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM eco_signal_observation WHERE signal_family = 'MA_STATUS'"
    ).fetchone()[0] == 1
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
    db_path = tmp_path / "ma-break-relevance.db"
    _seed_db(str(db_path))

    build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)
    with pytest.raises(ValueError, match="MA_BREAK_STATUS signal rows already exist"):
        build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=False)

    conn = _connect(str(db_path))
    signal_observation_id = conn.execute(
        """
        SELECT signal_observation_id
        FROM eco_signal_observation
        WHERE signal_family = 'MA_BREAK_STATUS'
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
        build_canonical_v3_ma_break_status(str(db_path), RUN_ID, replace_existing=True)
