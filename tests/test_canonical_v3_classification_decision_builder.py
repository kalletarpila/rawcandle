import sqlite3

import pytest

from rawcandle.report_canonical_v3_classification_decision_builder import (
    build_canonical_v3_classification_decisions,
)
from rawcandle.report_canonical_v3_migration import apply_report_canonical_v3_migration


RUN_ID = "V3_BASE_DATACENTER_2026_05_29_DC_TAXONOMY_FULL_V1"
SIGNAL_DATE = "2026-05-29"


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


def _insert_ticker_entity(conn: sqlite3.Connection, ecosystem_id: int, ticker: str) -> int:
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
        (ecosystem_id, "TICKER", ticker, ticker, ticker, None, None, None, "ACTIVE"),
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
        CREATE TABLE dc_report_classification_v2 (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            market TEXT NULL,
            ticker TEXT NOT NULL,
            horizon TEXT NOT NULL,
            classification_type TEXT NOT NULL,
            classification_state TEXT NOT NULL,
            primary_reason TEXT NULL,
            blocking_reason TEXT NULL,
            risk_reason TEXT NULL,
            next_action TEXT NULL,
            classification_status TEXT NOT NULL,
            classification_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            candidate_priority REAL NULL,
            candidate_priority_label TEXT NULL,
            rank INTEGER NULL,
            source_classifier TEXT NULL,
            created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _insert_source_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    horizon: str,
    classification_type: str,
    classification_state: str,
    primary_reason: str | None = None,
    blocking_reason: str | None = None,
    risk_reason: str | None = None,
    next_action: str | None = None,
    candidate_priority: float | None = None,
    candidate_priority_label: str | None = None,
    rank: int | None = None,
    source_classifier: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_report_classification_v2 (
            signal_date,
            taxonomy_version,
            market,
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            classification_status,
            classification_version,
            run_id,
            candidate_priority,
            candidate_priority_label,
            rank,
            source_classifier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SIGNAL_DATE,
            "DC_TAXONOMY_FULL_V1",
            None,
            ticker,
            horizon,
            classification_type,
            classification_state,
            primary_reason,
            blocking_reason,
            risk_reason,
            next_action,
            "OK",
            "V2",
            "source-run-1",
            candidate_priority,
            candidate_priority_label,
            rank,
            source_classifier,
        ),
    )


def _insert_supporting_fact_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    entity_id: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            snapshot_status,
            classification_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "OK", "SELL_TRIGGER"),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_metric_value (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            metric_name,
            metric_value_num,
            metric_value_text,
            metric_unit,
            value_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", entity_id, "metric_a", 1.0, None, None, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_quality_summary (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            quality_scope,
            scope_entity_id,
            quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (RUN_ID, ecosystem_id, SIGNAL_DATE, taxonomy_version_id, "daily", "TICKER", entity_id, "OK"),
    )
    conn.execute(
        """
        INSERT INTO eco_signal_observation (
            run_id,
            ecosystem_id,
            signal_date,
            taxonomy_version_id,
            window_code,
            entity_id,
            signal_name,
            signal_family,
            signal_direction,
            signal_value,
            observed_date,
            source_table,
            source_run_id,
            source_event_id,
            signal_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            SIGNAL_DATE,
            taxonomy_version_id,
            "daily",
            entity_id,
            "sig",
            "REVERSAL_MEDIUM",
            "UP",
            "yes",
            SIGNAL_DATE,
            "technical_signal_relevance",
            "source-run-1",
            "src-1",
            "ACTIVE",
        ),
    )
    signal_observation_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO eco_signal_relevance (
            signal_observation_id,
            relevance_label,
            relevance_score,
            relevance_reason
        ) VALUES (?, ?, ?, ?)
        """,
        (
            signal_observation_id,
            "RELEVANT",
            1.0,
            None,
        ),
    )
    conn.execute(
        """
        INSERT INTO eco_entity_event (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            entity_id,
            event_date,
            event_type,
            source_table,
            event_label,
            event_key,
            event_direction,
            event_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            ecosystem_id,
            taxonomy_version_id,
            entity_id,
            SIGNAL_DATE,
            "BOS",
            "stock_dow_structure_events",
            "BOS_UP",
            "ticker:test",
            "UP",
            "ACTIVE",
        ),
    )


def _setup_builder_fixture(db_path):
    apply_report_canonical_v3_migration(str(db_path))
    conn = _connect(str(db_path))
    ecosystem_id = _insert_ecosystem(conn)
    taxonomy_version_id = _insert_taxonomy_version(conn, ecosystem_id)
    nvda_id = _insert_ticker_entity(conn, ecosystem_id, "NVDA")
    amd_id = _insert_ticker_entity(conn, ecosystem_id, "AMD")
    _insert_run(conn, ecosystem_id, taxonomy_version_id)
    for window_code in ("daily", "rolling2", "rolling5"):
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=nvda_id,
            window_code=window_code,
        )
        _insert_coverage(
            conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            entity_id=amd_id,
            window_code=window_code,
        )
    _create_source_table(conn)
    _insert_supporting_fact_rows(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        entity_id=nvda_id,
    )
    conn.commit()
    return conn, ecosystem_id, taxonomy_version_id, nvda_id, amd_id


def test_builder_requires_existing_run(tmp_path) -> None:
    db_path = tmp_path / "classification_decision_missing_run.db"
    apply_report_canonical_v3_migration(str(db_path))

    with pytest.raises(ValueError, match="Missing eco_report_run"):
        build_canonical_v3_classification_decisions(str(db_path), RUN_ID)


def test_builder_builds_supported_types_and_maps_fields(tmp_path) -> None:
    db_path = tmp_path / "classification_decision_build.db"
    conn, ecosystem_id, taxonomy_version_id, nvda_id, amd_id = _setup_builder_fixture(db_path)
    try:
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="daily",
            classification_type="daily_trigger",
            classification_state="SELL_TRIGGER",
            primary_reason="HAS_EXIT_RISK",
            blocking_reason="BELOW_EMA20",
            next_action="REDUCE",
            candidate_priority=10.5,
            candidate_priority_label="HIGH",
            rank=1,
            source_classifier="daily_trigger",
        )
        _insert_source_row(
            conn,
            ticker="AMD",
            horizon="rolling2",
            classification_type="rolling2_sell_pressure",
            classification_state="WATCH_PRESSURE",
            primary_reason="MILD_OR_UNCONFIRMED_SELL_PRESSURE",
            risk_reason="GROUP_RISK",
            next_action="MONITOR",
            rank=2,
        )
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="rolling5",
            classification_type="rolling5_pullback",
            classification_state="PULLBACK_CANDIDATE",
            primary_reason="CONFIRMED_EMA20_PULLBACK_CONTEXT",
            blocking_reason="LOW_VOLUME",
            next_action="WAIT",
        )
        _insert_source_row(
            conn,
            ticker="MISSING",
            horizon="daily",
            classification_type="daily_trigger",
            classification_state="SELL_TRIGGER",
            primary_reason="NO_ENTITY",
        )
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="rolling30",
            classification_type="rolling30_buy",
            classification_state="BUY_ZONE",
            primary_reason="IGNORE_THIS_PHASE",
        )
        before_counts = {
            "snapshot": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
            "metric": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "signal": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "event": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "run": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
        conn.commit()

        summary = build_canonical_v3_classification_decisions(str(db_path), RUN_ID)

        assert summary["classification_types"] == [
            "daily_trigger",
            "rolling2_sell_pressure",
            "rolling5_pullback",
        ]
        assert summary["source_rows_read"] == 4
        assert summary["source_rows_mapped"] == 3
        assert summary["source_rows_skipped"] == 1
        assert summary["decision_rows_inserted"] == 3
        assert summary["classification_type_counts"] == {
            "daily_trigger": 1,
            "rolling2_sell_pressure": 1,
            "rolling5_pullback": 1,
        }
        assert summary["warning_count"] == 1

        rows = conn.execute(
            """
            SELECT classification_type, window_code, entity_id, classification_state,
                   primary_reason, blocking_reason, risk_reason, next_action,
                   priority_score, priority_label, sort_rank, source_classifier,
                   classification_version, source_run_id, decision_status
            FROM eco_classification_decision
            ORDER BY classification_type
            """
        ).fetchall()
        assert len(rows) == 3
        assert [row["classification_type"] for row in rows] == [
            "daily_trigger",
            "rolling2_sell_pressure",
            "rolling5_pullback",
        ]
        daily_row, rolling2_row, rolling5_row = rows
        assert daily_row["window_code"] == "daily"
        assert daily_row["entity_id"] == nvda_id
        assert daily_row["blocking_reason"] == "BELOW_EMA20"
        assert daily_row["priority_score"] == 10.5
        assert daily_row["priority_label"] == "HIGH"
        assert daily_row["sort_rank"] == 1
        assert daily_row["source_classifier"] == "daily_trigger"
        assert daily_row["classification_version"] == "V2"
        assert daily_row["source_run_id"] == "source-run-1"
        assert daily_row["decision_status"] == "OK"

        assert rolling2_row["window_code"] == "rolling2"
        assert rolling2_row["entity_id"] == amd_id
        assert rolling2_row["risk_reason"] == "GROUP_RISK"
        assert rolling2_row["source_classifier"] == "rolling2_sell_pressure_classifier"

        assert rolling5_row["window_code"] == "rolling5"
        assert rolling5_row["blocking_reason"] == "LOW_VOLUME"
        assert rolling5_row["source_classifier"] == "rolling5_pullback_classifier"

        assert conn.execute(
            "SELECT COUNT(*) FROM eco_classification_decision WHERE classification_type LIKE 'rolling30%'"
        ).fetchone()[0] == 0

        after_counts = {
            "snapshot": conn.execute("SELECT COUNT(*) FROM eco_entity_window_snapshot").fetchone()[0],
            "metric": conn.execute("SELECT COUNT(*) FROM eco_entity_metric_value").fetchone()[0],
            "coverage": conn.execute("SELECT COUNT(*) FROM eco_entity_coverage").fetchone()[0],
            "quality": conn.execute("SELECT COUNT(*) FROM eco_quality_summary").fetchone()[0],
            "signal": conn.execute("SELECT COUNT(*) FROM eco_signal_observation").fetchone()[0],
            "relevance": conn.execute("SELECT COUNT(*) FROM eco_signal_relevance").fetchone()[0],
            "event": conn.execute("SELECT COUNT(*) FROM eco_entity_event").fetchone()[0],
            "run": conn.execute("SELECT COUNT(*) FROM eco_report_run").fetchone()[0],
        }
        assert after_counts == before_counts
    finally:
        conn.close()


def test_builder_replace_behavior_is_idempotent_and_preserves_rolling30(tmp_path) -> None:
    db_path = tmp_path / "classification_decision_replace.db"
    conn, ecosystem_id, taxonomy_version_id, nvda_id, _amd_id = _setup_builder_fixture(db_path)
    try:
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="daily",
            classification_type="daily_trigger",
            classification_state="SELL_TRIGGER",
            primary_reason="HAS_EXIT_RISK",
        )
        conn.execute(
            """
            INSERT INTO eco_classification_decision (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
                entity_id, classification_type, classification_state, decision_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                RUN_ID,
                ecosystem_id,
                SIGNAL_DATE,
                taxonomy_version_id,
                "rolling30",
                nvda_id,
                "rolling30_buy",
                "BUY_ZONE",
                "OK",
            ),
        )
        conn.commit()

        summary = build_canonical_v3_classification_decisions(
            str(db_path),
            RUN_ID,
            replace_existing=True,
        )
        assert summary["decision_rows_inserted"] == 1

        with pytest.raises(ValueError, match="already exist"):
            build_canonical_v3_classification_decisions(str(db_path), RUN_ID)

        summary_second = build_canonical_v3_classification_decisions(
            str(db_path),
            RUN_ID,
            replace_existing=True,
        )
        assert summary_second["decision_rows_inserted"] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE classification_type = 'rolling30_buy'
            """
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE classification_type IN ('daily_trigger', 'rolling2_sell_pressure', 'rolling5_pullback')
            """
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_builder_rejects_unsupported_classification_types(tmp_path) -> None:
    db_path = tmp_path / "classification_decision_unsupported.db"
    conn, _ecosystem_id, _taxonomy_version_id, _nvda_id, _amd_id = _setup_builder_fixture(db_path)
    conn.close()

    with pytest.raises(ValueError, match="rolling30_buy"):
        build_canonical_v3_classification_decisions(
            str(db_path),
            RUN_ID,
            classification_types=["daily_trigger", "rolling30_buy"],
        )


def test_builder_rolls_back_on_insert_failure(tmp_path) -> None:
    db_path = tmp_path / "classification_decision_rollback.db"
    conn, _ecosystem_id, _taxonomy_version_id, _nvda_id, _amd_id = _setup_builder_fixture(db_path)
    try:
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="daily",
            classification_type="daily_trigger",
            classification_state="SELL_TRIGGER",
        )
        _insert_source_row(
            conn,
            ticker="NVDA",
            horizon="daily",
            classification_type="daily_trigger",
            classification_state="SELL_TRIGGER_DUPLICATE",
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            build_canonical_v3_classification_decisions(
                str(db_path),
                RUN_ID,
                classification_types=["daily_trigger"],
                replace_existing=True,
            )

        assert conn.execute("SELECT COUNT(*) FROM eco_classification_decision").fetchone()[0] == 0
    finally:
        conn.close()
