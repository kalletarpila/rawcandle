import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_action_summary_write import main
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
                signal_date, taxonomy_version, ticker, action, is_watchlist,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_default_action_rows(path: Path) -> None:
    _insert_ticker_rows(
        path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
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
                "SELL",
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "CCC",
                "WATCH",
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "DDD",
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
                "EEE",
                "   ",
                0,
                "OK",
                "V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
            ),
        ],
    )


def _destination_rows(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                """
                SELECT *
                FROM dc_dashboard_action_summary_daily
                ORDER BY action ASC
                """
            ).fetchall()
        )


def _destination_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM dc_dashboard_action_summary_daily").fetchone()
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
            CREATE TABLE dc_dashboard_action_summary_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                action TEXT NOT NULL,
                count INTEGER NOT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                PRIMARY KEY (signal_date, taxonomy_version, action)
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
        "missing required destination table: dc_dashboard_action_summary_daily" in captured.err
    )


def test_replace_date_writes_action_counts_from_ticker_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)

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
            "RUN_ACTION_REPLACE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert [(row["action"], row["count"]) for row in rows] == [("SELL", 2), ("WATCH", 1)]
    assert "SUMMARY datacenter_dashboard_action_summary_write.source_rows=5" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.actionable_rows=3" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.distinct_actions=2" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.inserted_rows=2" in output


def test_field_mapping_persists_expected_values(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)

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
            "RUN_ACTION_FIELDS",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = {row["action"]: row for row in _destination_rows(db_path)}
    sell = rows["SELL"]
    assert sell["signal_date"] == "2026-05-22"
    assert sell["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert sell["action"] == "SELL"
    assert sell["count"] == 2
    assert sell["calc_version"] == "DATACENTER_DASHBOARD_ACTION_SUMMARY_V1"
    assert sell["run_id"] == "RUN_ACTION_FIELDS"
    assert sell["created_at_utc"] not in (None, "")


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)

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
            "RUN_ACTION_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_action_summary_write.dry_run=1" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.inserted_rows=2" in output


def test_insert_missing_keeps_existing_row_unchanged_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "SELL",
                99,
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
            "RUN_ACTION_INSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["action"]: row for row in _destination_rows(db_path)}
    assert rows["SELL"]["count"] == 99
    assert rows["SELL"]["run_id"] == "OLD_RUN"
    assert rows["WATCH"]["run_id"] == "RUN_ACTION_INSERT"
    assert "SUMMARY datacenter_dashboard_action_summary_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.skipped_existing_rows=1" in output


def test_upsert_updates_existing_row_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "SELL",
                99,
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
            "RUN_ACTION_UPSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["action"]: row for row in _destination_rows(db_path)}
    assert rows["SELL"]["count"] == 2
    assert rows["SELL"]["run_id"] == "RUN_ACTION_UPSERT"
    assert rows["WATCH"]["run_id"] == "RUN_ACTION_UPSERT"
    assert "SUMMARY datacenter_dashboard_action_summary_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.updated_rows=1" in output


def test_replace_date_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_default_action_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date, taxonomy_version, action, count, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "OLD",
                    9,
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "KEEP_DATE",
                    1,
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_OTHER_V1",
                    "KEEP_TAXONOMY",
                    1,
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
            "RUN_ACTION_SCOPE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute(
                """
                SELECT signal_date, taxonomy_version, action
                FROM dc_dashboard_action_summary_daily
                ORDER BY signal_date ASC, taxonomy_version ASC, action ASC
                """
            ).fetchall()
        )
    assert rows == [
        ("2026-05-21", "DC_TAXONOMY_FULL_V1", "KEEP_DATE"),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "SELL"),
        ("2026-05-22", "DC_TAXONOMY_FULL_V1", "WATCH"),
        ("2026-05-22", "DC_TAXONOMY_OTHER_V1", "KEEP_TAXONOMY"),
    ]
    assert "SUMMARY datacenter_dashboard_action_summary_write.deleted_existing_rows=1" in output


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
            "RUN_NO_SOURCE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_action_summary_write.source_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_action_summary_write.warning=NO_TICKER_ENRICHMENT_ROWS_FOR_SELECTION"
        in output
    )


def test_no_action_values_warns_and_writes_nothing(tmp_path, capsys):
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
            "RUN_NO_ACTIONS",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_action_summary_write.source_rows=2" in output
    assert "SUMMARY datacenter_dashboard_action_summary_write.actionable_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_action_summary_write.warning=NO_ACTION_VALUES_FOR_SELECTION"
        in output
    )


def test_audit_reports_partial_after_ticker_group_and_action_rows_exist(tmp_path, capsys):
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
            "RUN_ACTION_AUDIT",
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
    assert "section_readiness;decision_trace;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;3;some_sections_empty" in output
