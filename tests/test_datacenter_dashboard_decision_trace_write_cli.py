import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_decision_trace_write import main
from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_source_table_only(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT NULL,
                primary_subindustry TEXT NULL,
                close REAL NULL,
                return_5d REAL NULL,
                return_10d REAL NULL,
                return_20d REAL NULL,
                return_60d REAL NULL,
                action TEXT NULL,
                severity TEXT NULL,
                primary_reason TEXT NULL,
                current_status TEXT NULL,
                start_status_30d TEXT NULL,
                status_change_30d TEXT NULL,
                status_change_5d TEXT NULL,
                window_status_30d TEXT NULL,
                window_status_5d TEXT NULL,
                window_status_2d TEXT NULL,
                ma_break_status TEXT NULL,
                freshness_status TEXT NULL,
                trend_state TEXT NULL,
                trend_state_age_td INTEGER NULL,
                latest_structure_label TEXT NULL,
                latest_structure_age_td INTEGER NULL,
                latest_bos_event_type TEXT NULL,
                latest_bos_age_td INTEGER NULL,
                latest_reset_reason TEXT NULL,
                latest_reset_age_td INTEGER NULL,
                latest_candle TEXT NULL,
                latest_candle_age_td INTEGER NULL,
                latest_divergence TEXT NULL,
                latest_divergence_age_td INTEGER NULL,
                latest_chart_pattern TEXT NULL,
                latest_chart_pattern_age_td INTEGER NULL,
                pullback_validity TEXT NULL,
                entry_readiness TEXT NULL,
                candidate_priority TEXT NULL,
                candidate_priority_label TEXT NULL,
                daily_status TEXT NULL,
                rolling_2d_status TEXT NULL,
                rolling_5d_status TEXT NULL,
                rolling_30d_status TEXT NULL,
                horizons_present TEXT NULL,
                source_run_ids TEXT NULL,
                source_components TEXT NULL,
                is_watchlist INTEGER NOT NULL DEFAULT 0,
                data_quality_status TEXT NOT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, ticker)
            )
            """
        )


def _create_source_and_destination_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_ticker_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, severity, primary_reason,
                current_status, pullback_validity, entry_readiness, candidate_priority,
                candidate_priority_label, daily_status, rolling_2d_status, rolling_5d_status,
                rolling_30d_status, horizons_present, trend_state, latest_structure_label,
                latest_bos_event_type, latest_reset_reason, is_watchlist, data_quality_status,
                calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_default_trace_source_rows(path: Path) -> None:
    _insert_ticker_rows(
        path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
                "HIGH",
                "risk_exit",
                "EXIT_ZONE",
                None,
                None,
                None,
                None,
                "SELL_PRESSURE",
                None,
                "PULLBACK",
                None,
                None,
                "DOWN",
                "LL",
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            )
        ],
    )


def _destination_rows(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                """
                SELECT *
                FROM dc_dashboard_decision_trace_daily
                ORDER BY ticker ASC, trace_index ASC
                """
            ).fetchall()
        )


def _destination_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM dc_dashboard_decision_trace_daily").fetchone()
    return int(row[0])


def test_missing_analysis_db_fails_clearly_and_does_not_create_file(tmp_path, capsys):
    db_path = tmp_path / "missing-analysis.db"

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not db_path.exists()
    assert captured.out == ""
    assert "analysis_db not found:" in captured.err


def test_missing_source_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_empty_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_decision_trace_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                trace_index INTEGER NOT NULL,
                action TEXT NULL,
                matched_rule TEXT NULL,
                matched_token TEXT NULL,
                matched_value TEXT NULL,
                horizon TEXT NULL,
                field TEXT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, ticker, trace_index)
            )
            """
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required source table: dc_dashboard_ticker_enrichment_daily" in captured.err


def test_missing_destination_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_table_only(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert (
        "missing required destination table: dc_dashboard_decision_trace_daily"
        in captured.err
    )


def test_replace_date_writes_trace_rows_from_ticker_enrichment_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_trace_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_REPLACE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert [row["trace_index"] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(row["matched_rule"] == "ENRICHMENT_FIELD_PRESENT" for row in rows)
    assert [row["matched_token"] for row in rows] == [
        "action",
        "severity",
        "primary_reason",
        "current_status",
        "daily_status",
        "rolling_5d_status",
        "trend_state",
        "latest_structure_label",
    ]
    assert [row["matched_value"] for row in rows] == [
        "SELL",
        "HIGH",
        "risk_exit",
        "EXIT_ZONE",
        "SELL_PRESSURE",
        "PULLBACK",
        "DOWN",
        "LL",
    ]
    assert rows[4]["horizon"] == "daily"
    assert rows[5]["horizon"] == "rolling_5d"
    assert all(row["field"] == row["matched_token"] for row in rows)
    assert "SUMMARY datacenter_dashboard_decision_trace_write.trace_rows=8" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.inserted_rows=8" in output


def test_rows_with_null_or_empty_action_are_not_eligible(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                None,
                "HIGH",
                "risk_exit",
                "EXIT_ZONE",
                None,
                None,
                None,
                None,
                "SELL_PRESSURE",
                None,
                None,
                None,
                None,
                "DOWN",
                "LL",
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "   ",
                "HIGH",
                "risk_exit",
                "EXIT_ZONE",
                None,
                None,
                None,
                None,
                "SELL_PRESSURE",
                None,
                None,
                None,
                None,
                "DOWN",
                "LL",
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_EMPTY",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_decision_trace_write.eligible_ticker_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_decision_trace_write.warning=NO_ACTION_VALUES_FOR_SELECTION"
        in output
    )


def test_ticker_row_with_action_only_creates_action_trace_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            )
        ],
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_ACTION_ONLY",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = _destination_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["matched_token"] == "action"
    assert rows[0]["matched_value"] == "WATCH"


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_trace_source_rows(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_decision_trace_write.dry_run=1" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.inserted_rows=8" in output


def test_insert_missing_keeps_existing_trace_row_unchanged_and_inserts_new_rows(
    tmp_path, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "WATCH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_decision_trace_daily (
                signal_date, taxonomy_version, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                1,
                "OLD",
                "OLD_RULE",
                "action",
                "OLD_VALUE",
                None,
                "action",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "insert-missing",
            "--run-id",
            "RUN_TRACE_INSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {(row["ticker"], row["trace_index"]): row for row in _destination_rows(db_path)}
    assert rows[("AAA", 1)]["run_id"] == "OLD_RUN"
    assert rows[("AAA", 1)]["matched_value"] == "OLD_VALUE"
    assert rows[("BBB", 1)]["run_id"] == "RUN_TRACE_INSERT"
    assert "SUMMARY datacenter_dashboard_decision_trace_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.skipped_existing_rows=1" in output


def test_upsert_updates_existing_trace_row_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
                "HIGH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "WATCH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_decision_trace_daily (
                signal_date, taxonomy_version, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                1,
                "OLD",
                "OLD_RULE",
                "action",
                "OLD_VALUE",
                None,
                "action",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "upsert",
            "--run-id",
            "RUN_TRACE_UPSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {(row["ticker"], row["trace_index"]): row for row in _destination_rows(db_path)}
    assert rows[("AAA", 1)]["matched_value"] == "SELL"
    assert rows[("AAA", 1)]["run_id"] == "RUN_TRACE_UPSERT"
    assert rows[("AAA", 2)]["matched_token"] == "severity"
    assert rows[("BBB", 1)]["run_id"] == "RUN_TRACE_UPSERT"
    assert "SUMMARY datacenter_dashboard_decision_trace_write.inserted_rows=2" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.updated_rows=1" in output


def test_replace_date_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_trace_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_decision_trace_daily (
                signal_date, taxonomy_version, ticker, trace_index, action, matched_rule,
                matched_token, matched_value, horizon, field, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "OLD",
                    1,
                    "OLD",
                    "OLD_RULE",
                    "action",
                    "OLD",
                    None,
                    "action",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "KEEP_DATE",
                    1,
                    "KEEP",
                    "OLD_RULE",
                    "action",
                    "KEEP",
                    None,
                    "action",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_OTHER_V1",
                    "KEEP_TAXONOMY",
                    1,
                    "KEEP",
                    "OLD_RULE",
                    "action",
                    "KEEP",
                    None,
                    "action",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
            ],
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_SCOPE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute(
                """
                SELECT signal_date, taxonomy_version, ticker, trace_index
                FROM dc_dashboard_decision_trace_daily
                ORDER BY signal_date ASC, taxonomy_version ASC, ticker ASC, trace_index ASC
                """
            ).fetchall()
        )
    assert rows == [
        ("2026-05-21", "DC_TAXONOMY_FULL_V1", "KEEP_DATE", 1),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 2),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 3),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 4),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 5),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 6),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 7),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 8),
        ("2026-05-22", "DC_TAXONOMY_OTHER_V1", "KEEP_TAXONOMY", 1),
    ]
    assert "SUMMARY datacenter_dashboard_decision_trace_write.deleted_existing_rows=1" in output


def test_no_source_rows_warns_and_writes_nothing(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_NO_SOURCE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_decision_trace_write.source_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_decision_trace_write.warning=NO_TICKER_ENRICHMENT_ROWS_FOR_SELECTION"
        in output
    )


def test_source_rows_exist_but_all_actions_empty_warns_and_writes_nothing(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "   ",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_NO_ACTIONS",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_decision_trace_write.source_rows=2" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.eligible_ticker_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_decision_trace_write.warning=NO_ACTION_VALUES_FOR_SELECTION"
        in output
    )


def test_limit_processes_only_one_eligible_ticker_before_trace_expansion(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
                "HIGH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "WATCH",
                "MEDIUM",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_LIMIT",
            "--limit",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert {(row["ticker"], row["trace_index"]) for row in rows} == {("AAA", 1), ("AAA", 2)}
    assert "SUMMARY datacenter_dashboard_decision_trace_write.eligible_ticker_rows=1" in output
    assert "SUMMARY datacenter_dashboard_decision_trace_write.trace_rows=2" in output


def test_audit_reports_partial_after_ticker_group_action_and_trace_rows_exist(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_rows(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            )
        ],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "LAYER",
                "LAYER:Infrastructure",
                "Infrastructure",
                "OK",
                "V1",
                "RUN_GROUP",
                "2026-05-26T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "WATCH",
                1,
                "V1",
                "RUN_ACTION",
                "2026-05-26T10:00:00Z",
            ),
        )

    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--mode",
            "replace-date",
            "--run-id",
            "RUN_TRACE_AUDIT",
        ]
    )
    assert exit_code == 0
    _ = capsys.readouterr()

    audit_exit_code = audit_main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    output = capsys.readouterr().out
    assert audit_exit_code == 0
    assert "section_readiness;ticker_enrichment;READY;1;rows_available" in output
    assert "section_readiness;group_enrichment;READY;1;rows_available" in output
    assert "section_readiness;action_summary;READY;1;rows_available" in output
    assert "section_readiness;decision_trace;READY;1;rows_available" in output
    assert "section_readiness;enrichment_run;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;4;some_sections_empty" in output
