import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_action_summary_write import (
    main as action_summary_main,
)
from dev_tools.run_datacenter_dashboard_ticker_decision_enrichment_write import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_db_with_table(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, severity, primary_reason,
                current_status, ma_break_status, freshness_status, trend_state,
                latest_structure_label, latest_bos_event_type, latest_reset_reason,
                pullback_validity, entry_readiness, candidate_priority,
                candidate_priority_label, daily_status, rolling_2d_status,
                rolling_5d_status, rolling_30d_status, horizons_present,
                is_watchlist, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _default_row(
    *,
    signal_date: str = "2026-05-22",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    ticker: str = "NVDA",
    action=None,
    severity=None,
    primary_reason=None,
    current_status: str | None = "NEUTRAL",
    ma_break_status: str | None = None,
    freshness_status: str | None = None,
    trend_state: str | None = "UP",
    latest_structure_label: str | None = "HH",
    latest_bos_event_type: str | None = "BOS_UP",
    latest_reset_reason: str | None = None,
    pullback_validity=None,
    entry_readiness=None,
    candidate_priority=None,
    candidate_priority_label=None,
    daily_status: str | None = "NEUTRAL_MONITOR",
    rolling_2d_status: str | None = None,
    rolling_5d_status: str | None = None,
    rolling_30d_status: str | None = None,
    horizons_present=None,
) -> tuple[object, ...]:
    return (
        signal_date,
        taxonomy_version,
        ticker,
        action,
        severity,
        primary_reason,
        current_status,
        ma_break_status,
        freshness_status,
        trend_state,
        latest_structure_label,
        latest_bos_event_type,
        latest_reset_reason,
        pullback_validity,
        entry_readiness,
        candidate_priority,
        candidate_priority_label,
        daily_status,
        rolling_2d_status,
        rolling_5d_status,
        rolling_30d_status,
        horizons_present,
        0,
        "OK",
        "SRC_V1",
        "RUN_SRC",
        "2026-05-26T10:00:00Z",
    )


def _fetch_row(path: Path, ticker: str = "NVDA") -> sqlite3.Row:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", ticker),
        ).fetchone()
    assert row is not None
    return row


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
            "upsert",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not db_path.exists()
    assert "analysis_db not found:" in captured.err


def test_missing_ticker_enrichment_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_empty_db(db_path)

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
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required source table: dc_dashboard_ticker_enrichment_daily" in captured.err


def test_upsert_updates_decision_fields_for_existing_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(db_path, [_default_row()])

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
        ]
    )

    output = capsys.readouterr().out
    row = _fetch_row(db_path)
    assert exit_code == 0
    assert row["action"] == "NEUTRAL"
    assert row["severity"] == "INFO"
    assert row["primary_reason"] == "NO_DECISIVE_SIGNAL"
    assert row["pullback_validity"] is not None
    assert row["entry_readiness"] is not None
    assert row["candidate_priority"] is not None
    assert row["candidate_priority_label"] is not None
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.updated_rows=1" in output


def test_dry_run_does_not_mutate_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(db_path, [_default_row(action="STALE", primary_reason="OLD")])

    before = dict(_fetch_row(db_path))
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
            "--dry-run",
        ]
    )
    after = dict(_fetch_row(db_path))

    assert exit_code == 0
    assert before == after


def test_replace_date_clears_stale_fields_and_writes_new_decision_fields(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(
        db_path,
        [
            _default_row(
                action="STALE_ACTION",
                severity="STALE_SEVERITY",
                primary_reason="STALE_REASON",
                pullback_validity="STALE_PULLBACK",
                entry_readiness="STALE_ENTRY",
                candidate_priority=99,
                candidate_priority_label="STALE_PRIORITY",
                horizons_present="stale",
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
        ]
    )

    output = capsys.readouterr().out
    row = _fetch_row(db_path)
    assert exit_code == 0
    assert row["action"] == "NEUTRAL"
    assert row["primary_reason"] == "NO_DECISIVE_SIGNAL"
    assert row["action"] != "STALE_ACTION"
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.cleared_rows=1" in output
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.updated_rows=1" in output


def test_replace_date_scope_updates_only_selected_date_and_taxonomy(tmp_path):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(
        db_path,
        [
            _default_row(action="STALE"),
            _default_row(signal_date="2026-05-23", ticker="AAPL", action="KEEP_OTHER_DATE"),
            _default_row(
                taxonomy_version="OTHER_TAXONOMY",
                ticker="AMD",
                action="KEEP_OTHER_TAXONOMY",
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
        ]
    )

    assert exit_code == 0
    assert _fetch_row(db_path, "NVDA")["action"] == "NEUTRAL"
    with sqlite3.connect(db_path) as conn:
        aapl = conn.execute(
            """
            SELECT action FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-23' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
              AND ticker = 'AAPL'
            """
        ).fetchone()[0]
        amd = conn.execute(
            """
            SELECT action FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'OTHER_TAXONOMY'
              AND ticker = 'AMD'
            """
        ).fetchone()[0]
    assert aapl == "KEEP_OTHER_DATE"
    assert amd == "KEEP_OTHER_TAXONOMY"


def test_no_source_rows_warns_and_succeeds(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)

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
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert (
        "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.warning="
        "NO_TICKER_ENRICHMENT_ROWS_FOR_SELECTION"
    ) in output
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.updated_rows=0" in output


def test_adapter_returning_no_decisions_warns_and_writes_nothing(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(db_path, [_default_row()])

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_ticker_decision_enrichment_write.build_decisions_from_ticker_enrichment_rows",
        lambda rows: SimpleNamespace(decisions=[]),
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
        ]
    )

    output = capsys.readouterr().out
    row = _fetch_row(db_path)
    assert exit_code == 0
    assert row["action"] is None
    assert (
        "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.warning="
        "NO_DECISIONS_PRODUCED"
    ) in output
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.updated_rows=0" in output


def test_invalid_ticker_rows_are_ignored(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(
        db_path,
        [
            _default_row(ticker=""),
            _default_row(ticker="2026-05-22"),
            _default_row(ticker="NVDA"),
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
            "upsert",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.valid_ticker_rows=1" in output
    assert _fetch_row(db_path, "NVDA")["action"] == "NEUTRAL"


def test_action_summary_writer_can_use_updated_action_fields(tmp_path):
    db_path = tmp_path / "analysis.db"
    _create_db_with_table(db_path)
    _insert_rows(db_path, [_default_row()])

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
        ]
    )
    assert exit_code == 0

    summary_exit = action_summary_main(
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
    assert summary_exit == 0

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_action_summary_daily
            WHERE signal_date = ? AND taxonomy_version = ?
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1"),
        ).fetchone()[0]
    assert count > 0
