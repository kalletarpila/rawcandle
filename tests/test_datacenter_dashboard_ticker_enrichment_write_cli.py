import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.run_datacenter_dashboard_ticker_enrichment_write import main
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
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT,
                primary_layer TEXT,
                primary_subindustry TEXT,
                close REAL,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                price_data_status TEXT,
                ticker_trend_state TEXT,
                latest_structure_label TEXT,
                latest_structure_age_trading_days INTEGER,
                latest_structure_freshness TEXT,
                latest_bos_event_type TEXT,
                latest_bos_age_trading_days INTEGER,
                latest_reset_reason TEXT,
                latest_reset_age_trading_days INTEGER,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER
            )
            """
        )


def _create_source_and_destination_db(path: Path) -> None:
    _create_source_table_only(path)
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_source_rows(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_10d, return_20d, return_60d, price_data_status,
                ticker_trend_state, latest_structure_label, latest_structure_age_trading_days,
                latest_structure_freshness, latest_bos_event_type, latest_bos_age_trading_days,
                latest_reset_reason, latest_reset_age_trading_days, bullish_candle_signal,
                bullish_divergence_signal, hidden_bullish_divergence_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "NVDA",
                    "Infrastructure",
                    "AI Accelerators",
                    100.5,
                    1.2,
                    2.4,
                    4.5,
                    12.0,
                    "OK",
                    "UP",
                    "HH",
                    3,
                    "FRESH",
                    "BOS_UP",
                    2,
                    "EMA20_LOST",
                    5,
                    1,
                    1,
                    0,
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ANET",
                    "Infrastructure",
                    "Networking",
                    95.0,
                    0.5,
                    1.0,
                    2.0,
                    6.0,
                    "OK",
                    "UP",
                    "HL",
                    4,
                    "STALE",
                    "BOS_UP",
                    3,
                    None,
                    None,
                    0,
                    0,
                    0,
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    0.4,
                    "OK",
                    "UP",
                    "HH",
                    1,
                    "FRESH",
                    "BOS_UP",
                    1,
                    None,
                    None,
                    0,
                    0,
                    0,
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "2026-05-22",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    0.4,
                    "OK",
                    "UP",
                    "HH",
                    1,
                    "FRESH",
                    "BOS_UP",
                    1,
                    None,
                    None,
                    0,
                    0,
                    0,
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "Layer Header",
                    "Infrastructure",
                    "AI Accelerators",
                    10.0,
                    0.1,
                    0.2,
                    0.3,
                    0.4,
                    "OK",
                    "UP",
                    "HH",
                    1,
                    "FRESH",
                    "BOS_UP",
                    1,
                    None,
                    None,
                    0,
                    0,
                    0,
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
                FROM dc_dashboard_ticker_enrichment_daily
                ORDER BY ticker ASC
                """
            ).fetchall()
        )


def _destination_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily").fetchone()
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
        apply_datacenter_dashboard_enrichment_migration(conn)

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
    assert "missing required source table: dc_ticker_swing_signal_daily" in captured.err


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
        "missing required destination table: dc_dashboard_ticker_enrichment_daily"
        in captured.err
    )


def test_replace_date_inserts_valid_rows_and_excludes_pseudo_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

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
            "RUN_REPLACE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert [row["ticker"] for row in rows] == ["ANET", "NVDA"]
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.source_rows=5" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.valid_ticker_rows=2" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.excluded_pseudo_rows=3" in output
    )
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=2" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.updated_rows=0" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.deleted_existing_rows=0" in output
    )


def test_field_mapping_persists_expected_values(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

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
            "RUN_FIELDS",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    nvda = rows["NVDA"]
    assert nvda["primary_layer"] == "Infrastructure"
    assert nvda["primary_subindustry"] == "AI Accelerators"
    assert nvda["close"] == 100.5
    assert nvda["return_5d"] == 1.2
    assert nvda["return_10d"] == 2.4
    assert nvda["return_20d"] == 4.5
    assert nvda["return_60d"] == 12.0
    assert nvda["trend_state"] == "UP"
    assert nvda["latest_structure_label"] == "HH"
    assert nvda["latest_bos_event_type"] == "BOS_UP"
    assert nvda["latest_reset_reason"] == "EMA20_LOST"
    assert nvda["data_quality_status"] == "OK"
    assert nvda["calc_version"] == "DATACENTER_DASHBOARD_TICKER_ENRICHMENT_V1"
    assert nvda["run_id"] == "RUN_FIELDS"
    assert nvda["created_at_utc"] not in (None, "")
    assert nvda["is_watchlist"] == 0


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

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
            "RUN_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.dry_run=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=2" in output


def test_insert_missing_keeps_existing_row_unchanged_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, data_quality_status, calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OldLayer",
                "OldSub",
                1.0,
                "OLD",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
                0,
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
            "RUN_INSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["primary_layer"] == "OldLayer"
    assert rows["NVDA"]["data_quality_status"] == "OLD"
    assert rows["ANET"]["run_id"] == "RUN_INSERT"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.skipped_existing_rows=1" in output


def test_upsert_updates_existing_row_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, data_quality_status, calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OldLayer",
                "OldSub",
                1.0,
                "OLD",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
                0,
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
            "RUN_UPSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["ticker"]: row for row in _destination_rows(db_path)}
    assert rows["NVDA"]["primary_layer"] == "Infrastructure"
    assert rows["NVDA"]["data_quality_status"] == "OK"
    assert rows["NVDA"]["run_id"] == "RUN_UPSERT"
    assert rows["ANET"]["run_id"] == "RUN_UPSERT"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.updated_rows=1" in output


def test_replace_date_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, data_quality_status, calc_version,
                run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "OLD1",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
                ),
                (
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "KEEP_DATE",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
                ),
                (
                    "2026-05-22",
                    "OTHER_TAXONOMY",
                    "KEEP_TAX",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                    0,
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
            "RUN_SCOPE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        kept_date = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-21' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
        kept_tax = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'OTHER_TAXONOMY'
            """
        ).fetchone()[0]
        replaced_same_slice = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
    assert kept_date == 1
    assert kept_tax == 1
    assert replaced_same_slice == 2
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.deleted_existing_rows=1" in output
    )


def test_limit_works_deterministically(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

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
            "RUN_LIMIT",
            "--limit",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "ANET"
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.source_rows=5" in output
    assert "SUMMARY datacenter_dashboard_ticker_enrichment_write.valid_ticker_rows=1" in output
    assert (
        "SUMMARY datacenter_dashboard_ticker_enrichment_write.excluded_pseudo_rows=3" in output
    )


def test_audit_after_write_reports_ticker_ready_and_overall_partial(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_source_rows(db_path)

    write_exit_code = main(
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
            "RUN_AUDIT",
        ]
    )
    assert write_exit_code == 0
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
    assert "section_readiness;ticker_enrichment;READY;2;rows_available" in output
    assert "section_readiness;group_enrichment;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;2;some_sections_empty" in output
    assert "SUMMARY datacenter_dashboard_enrichment_audit.ticker_rows=2" in output
