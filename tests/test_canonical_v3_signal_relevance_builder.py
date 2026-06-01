import sqlite3

import pytest

from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration
from rawcandle.report_canonical_v3_signal_relevance_builder import (
    build_canonical_v3_signal_relevance,
)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_ecosystem(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_ecosystem (
            ecosystem_code, ecosystem_name, description, status
        ) VALUES (?, ?, ?, ?)
        """,
        ("DATACENTER", "Datacenter", None, "ACTIVE"),
    )
    return int(cursor.lastrowid)


def _insert_taxonomy_version(conn: sqlite3.Connection, ecosystem_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_taxonomy_version (
            ecosystem_id, version_code, version_label, source_type, source_reference,
            effective_from, effective_to, is_active, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ecosystem_id,
            "DC_TAXONOMY_FULL_V1",
            "DC_TAXONOMY_FULL_V1",
            None,
            None,
            None,
            None,
            1,
            "ACTIVE",
        ),
    )
    return int(cursor.lastrowid)


def _insert_ticker_entity(conn: sqlite3.Connection, ecosystem_id: int, ticker: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO eco_entity (
            ecosystem_id, entity_type, entity_code, entity_name, ticker,
            exchange, market, currency, status
        ) VALUES (?, 'TICKER', ?, ?, ?, NULL, NULL, NULL, 'ACTIVE')
        """,
        (ecosystem_id, ticker, ticker, ticker),
    )
    return int(cursor.lastrowid)


def _insert_run(conn: sqlite3.Connection, ecosystem_id: int, taxonomy_version_id: int) -> None:
    conn.execute(
        """
        INSERT INTO eco_report_run (
            run_id, ecosystem_id, taxonomy_version_id, signal_date,
            run_type, status, warning_count, error_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            ecosystem_id,
            taxonomy_version_id,
            "2026-05-29",
            "BUILD",
            "OK",
            0,
            0,
            None,
        ),
    )


def _create_source_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE technical_signal_relevance_runs (
            run_id TEXT PRIMARY KEY NOT NULL,
            relevance_rule_version TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            reason_version TEXT NOT NULL,
            config_snapshot_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE technical_signal_relevance (
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            signal_confirmed_as_of_date TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            signal_close_price REAL NULL,
            signal_direction TEXT NULL,
            signal_family TEXT NULL,
            signal_source_type TEXT NOT NULL,
            signal_source_id TEXT NOT NULL,
            dow_trend_state TEXT NULL,
            dow_context_state TEXT NULL,
            latest_bos_direction TEXT NULL,
            bars_since_latest_bos INTEGER NULL,
            latest_reset_reason TEXT NULL,
            bars_since_latest_reset INTEGER NULL,
            near_latest_pivot INTEGER NOT NULL,
            near_active_bos_level INTEGER NOT NULL,
            is_trend_aligned INTEGER NOT NULL,
            is_counter_trend INTEGER NOT NULL,
            relevance_class TEXT NOT NULL,
            relevance_reason TEXT NOT NULL,
            relevance_rule_version TEXT NOT NULL,
            mapping_version TEXT NOT NULL,
            reason_version TEXT NOT NULL,
            rule_trace TEXT NULL,
            created_at_utc TEXT NOT NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (
                run_id,
                ticker,
                timeframe,
                signal_date,
                signal_name,
                signal_source_type,
                signal_source_id,
                relevance_rule_version
            )
        )
        """
    )


def _insert_source_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute(
        """
        INSERT INTO technical_signal_relevance_runs (
            run_id, relevance_rule_version, mapping_version, reason_version,
            config_snapshot_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, "rv1", "mv1", "reason1", "{}", "2026-05-29T00:00:00Z"),
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    signal_name: str,
    signal_direction: str | None,
    signal_family: str,
    relevance_class: str,
    relevance_reason: str,
    signal_source_id: str,
    is_trend_aligned: int,
    is_counter_trend: int,
) -> None:
    conn.execute(
        """
        INSERT INTO technical_signal_relevance (
            ticker, timeframe, signal_date, signal_confirmed_as_of_date, signal_name,
            signal_close_price, signal_direction, signal_family, signal_source_type,
            signal_source_id, dow_trend_state, dow_context_state, latest_bos_direction,
            bars_since_latest_bos, latest_reset_reason, bars_since_latest_reset,
            near_latest_pivot, near_active_bos_level, is_trend_aligned, is_counter_trend,
            relevance_class, relevance_reason, relevance_rule_version, mapping_version,
            reason_version, rule_trace, created_at_utc, run_id
        ) VALUES (?, '1d', '2026-05-29', '2026-05-29', ?, NULL, ?, ?, 'SRC', ?, 'UP', 'NORMAL', 'BOS_UP', 3, 'RESET', 5, 0, 0, ?, ?, ?, ?, 'rv1', 'mv1', 'reason1', NULL, '2026-05-29T00:00:00Z', ?)
        """,
        (
            ticker,
            signal_name,
            signal_direction,
            signal_family,
            signal_source_id,
            is_trend_aligned,
            is_counter_trend,
            relevance_class,
            relevance_reason,
            run_id,
        ),
    )


def _setup_minimal_state(db_path: str) -> None:
    with _connect(db_path) as conn:
        ecosystem_id = _insert_ecosystem(conn)
        taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
        _insert_ticker_entity(conn, ecosystem_id, "NVDA")
        _insert_ticker_entity(conn, ecosystem_id, "AMD")
        _insert_run(conn, ecosystem_id, taxonomy_version_id)
        _create_source_tables(conn)
        source_run_id = "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29"
        _insert_source_run(conn, source_run_id)
        _insert_source_row(
            conn,
            run_id=source_run_id,
            ticker="NVDA",
            signal_name="Hidden Bullish Divergence",
            signal_direction="BULLISH",
            signal_family="HIDDEN_DIVERGENCE",
            relevance_class="RELEVANT",
            relevance_reason="reason relevant",
            signal_source_id="src1",
            is_trend_aligned=1,
            is_counter_trend=0,
        )
        _insert_source_row(
            conn,
            run_id=source_run_id,
            ticker="AMD",
            signal_name="Bearish Divergence",
            signal_direction="BEARISH",
            signal_family="DIVERGENCE",
            relevance_class="WEAK_CONTEXT",
            relevance_reason="reason weak",
            signal_source_id="src2",
            is_trend_aligned=0,
            is_counter_trend=1,
        )
        _insert_source_row(
            conn,
            run_id=source_run_id,
            ticker="MISSING",
            signal_name="Hammer",
            signal_direction="SIDEWAYS",
            signal_family="REVERSAL",
            relevance_class="NOISE",
            relevance_reason="reason noise",
            signal_source_id="src3",
            is_trend_aligned=0,
            is_counter_trend=0,
        )
        conn.commit()


def test_signal_relevance_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "signal_missing_run.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    with _connect(str(db_path)) as conn:
        _create_source_tables(conn)
        _insert_source_run(conn, "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29")
        conn.commit()
    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_signal_relevance(str(db_path), "missing-run")


def test_signal_relevance_builder_maps_rows_and_discovers_source_run(tmp_path) -> None:
    db_path = tmp_path / "signal_builder.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))

    summary = build_canonical_v3_signal_relevance(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        technical_relevance_run_id=None,
        window_code="daily",
        replace_existing=False,
    )

    assert summary["source_rows_read"] == 3
    assert summary["source_rows_mapped"] == 2
    assert summary["source_rows_skipped"] == 1
    assert summary["signal_observations_inserted"] == 2
    assert summary["signal_relevance_rows_inserted"] == 2
    assert summary["relevance_label_counts"] == {"RELEVANT": 1, "WEAK_CONTEXT": 1}
    assert summary["signal_family_counts"] == {"DIVERGENCE": 1, "HIDDEN_DIVERGENCE": 1}
    assert any("Missing V3 ticker entity for source ticker 'MISSING'" in warning for warning in summary["warnings"])

    with _connect(str(db_path)) as conn:
        observations = conn.execute(
            """
            SELECT signal_name, signal_direction, signal_family, signal_value, source_run_id, signal_status
            FROM eco_signal_observation
            ORDER BY signal_name
            """
        ).fetchall()
        assert [tuple(row) for row in observations] == [
            ("Bearish Divergence", "BEARISH", "DIVERGENCE", "WEAK_CONTEXT", "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29", "ACTIVE"),
            ("Hidden Bullish Divergence", "BULLISH", "HIDDEN_DIVERGENCE", "RELEVANT", "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29", "ACTIVE"),
        ]

        relevance_rows = conn.execute(
            """
            SELECT r.relevance_label, r.trend_alignment, r.counter_trend_context, r.relevance_reason
            FROM eco_signal_relevance r
            JOIN eco_signal_observation o ON o.signal_observation_id = r.signal_observation_id
            ORDER BY o.signal_name
            """
        ).fetchall()
        assert [tuple(row) for row in relevance_rows] == [
            ("WEAK_CONTEXT", "NOT_ALIGNED", "COUNTER_TREND", "reason weak"),
            ("RELEVANT", "ALIGNED", "NOT_COUNTER_TREND", "reason relevant"),
        ]
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0] == 0


def test_signal_relevance_builder_rejects_non_daily_and_maps_unknowns(tmp_path) -> None:
    db_path = tmp_path / "signal_builder_unknowns.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))

    with pytest.raises(ValueError, match="Only window_code='daily' is supported"):
        build_canonical_v3_signal_relevance(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
            window_code="rolling5",
        )

    with _connect(str(db_path)) as conn:
        _insert_source_row(
            conn,
            run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
            ticker="NVDA",
            signal_name="Hammer",
            signal_direction="SIDEWAYS",
            signal_family="REVERSAL",
            relevance_class="NOISE",
            relevance_reason="unknown direction",
            signal_source_id="src4",
            is_trend_aligned=0,
            is_counter_trend=0,
        )
        conn.commit()

    summary = build_canonical_v3_signal_relevance(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
        replace_existing=False,
    )
    assert summary["relevance_label_counts"] == {"NOISE": 1, "RELEVANT": 1, "WEAK_CONTEXT": 1}
    assert any("source_signal_direction:SIDEWAYS->UNKNOWN" in warning for warning in summary["warnings"])

    with _connect(str(db_path)) as conn:
        unknown_row = conn.execute(
            """
            SELECT signal_direction
            FROM eco_signal_observation
            WHERE signal_name = 'Hammer'
            """
        ).fetchone()
        assert unknown_row is not None
        assert unknown_row["signal_direction"] == "UNKNOWN"


def test_signal_relevance_builder_replace_existing_and_rollback(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "signal_builder_replace.sqlite"
    apply_report_canonical_v3_migration(str(db_path))
    _setup_minimal_state(str(db_path))

    build_canonical_v3_signal_relevance(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
        replace_existing=False,
    )

    with pytest.raises(ValueError, match="already exist"):
        build_canonical_v3_signal_relevance(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
            replace_existing=False,
        )

    summary = build_canonical_v3_signal_relevance(
        db_path=str(db_path),
        run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
        technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
        replace_existing=True,
    )
    assert summary["signal_observations_inserted"] == 2

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0] == 0

    from rawcandle import report_canonical_v3_signal_relevance_builder as builder_module

    def _boom(conn: sqlite3.Connection, observation_ids: list[int], relevance_rows: list[dict[str, object]]) -> None:
        raise RuntimeError("forced relevance insert failure")

    monkeypatch.setattr(builder_module, "_insert_relevance_rows", _boom)

    with pytest.raises(RuntimeError, match="forced relevance insert failure"):
        build_canonical_v3_signal_relevance(
            db_path=str(db_path),
            run_id="V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1",
            technical_relevance_run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_29",
            replace_existing=True,
        )

    with _connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0] == 2
