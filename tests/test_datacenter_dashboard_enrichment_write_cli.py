import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.run_datacenter_dashboard_enrichment_write import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_source_tables(path: Path) -> None:
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
        conn.execute(
            """
            CREATE TABLE dc_group_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                timing_state TEXT,
                overheat_risk_level TEXT,
                pct_above_ema20 REAL,
                pct_above_ma10 REAL,
                ema20_breadth_delta_5d REAL,
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_60d REAL,
                data_quality_status TEXT,
                signal_version TEXT,
                run_id TEXT
            )
            """
        )


def _create_source_and_destination_db(path: Path) -> None:
    _create_source_tables(path)
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)


def _insert_ticker_source_row(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
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
        )


def _insert_group_source_row(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name, timing_state,
                overheat_risk_level, pct_above_ema20, pct_above_ma10, ema20_breadth_delta_5d,
                return_5d, return_10d, return_20d, return_60d, data_quality_status,
                signal_version, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "layer",
                "Infrastructure",
                "BREAKOUT_CANDIDATE",
                "MEDIUM",
                58.0,
                57.0,
                2.0,
                0.11,
                0.16,
                0.21,
                0.41,
                "OK",
                "SIG_V1",
                "RUN_SWING_A",
            ),
        )


def _count_selection(path: Path, table_name: str) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE signal_date = ? AND taxonomy_version = ?
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1"),
        ).fetchone()
    return int(row[0])


def _create_watchlist_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _run_rows(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                """
                SELECT *
                FROM dc_dashboard_enrichment_run_daily
                ORDER BY created_at_utc ASC, run_id ASC
                """
            ).fetchall()
        )


def _patch_orchestrator_stages_for_argv_capture(monkeypatch, captured: dict[str, list[str]]):
    def _ticker(argv):
        captured["ticker"] = list(argv)
        return 0

    def _group(argv):
        captured["group"] = list(argv)
        return 0

    def _ticker_decision(argv):
        captured["ticker_decision"] = list(argv)
        print(
            "SUMMARY "
            "datacenter_dashboard_ticker_decision_enrichment_write.updated_rows=0"
        )
        return 0

    def _action_summary(argv):
        captured["action_summary"] = list(argv)
        return 0

    def _decision_trace(argv):
        captured["decision_trace"] = list(argv)
        return 0

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.ticker_main",
        _ticker,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.group_main",
        _group,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.ticker_decision_main",
        _ticker_decision,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.action_summary_main",
        _action_summary,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.decision_trace_main",
        _decision_trace,
    )


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


def test_full_replace_date_run_with_real_v0_sources_writes_partial_metadata(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)

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
            "RUN_ORCH_PARTIAL",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _count_selection(db_path, "dc_dashboard_ticker_enrichment_daily") == 1
    assert _count_selection(db_path, "dc_dashboard_group_enrichment_daily") == 1
    assert _count_selection(db_path, "dc_dashboard_action_summary_daily") == 1
    assert _count_selection(db_path, "dc_dashboard_decision_trace_daily") > 0
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "RUN_ORCH_PARTIAL"
    assert rows[0]["status"] == "OK"
    assert rows[0]["readiness"] == "READY"
    assert rows[0]["ticker_rows"] == 1
    assert rows[0]["group_rows"] == 1
    assert rows[0]["action_summary_rows"] == 1
    assert rows[0]["decision_trace_rows"] > 0
    assert "SUMMARY datacenter_dashboard_enrichment_write.status=OK" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.ticker_decision_attempted=1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.metadata_written=1" in output


def test_preseeded_insert_missing_run_can_write_ready_metadata(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, severity, primary_reason,
                current_status, daily_status, rolling_5d_status, trend_state,
                latest_structure_label, is_watchlist, data_quality_status,
                calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "SELL",
                "HIGH",
                "risk_exit",
                "EXIT_ZONE",
                "SELL_PRESSURE",
                "PULLBACK",
                "DOWN",
                "LL",
                0,
                "OK",
                "SEED",
                "SEED_RUN",
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
            "insert-missing",
            "--run-id",
            "RUN_ORCH_READY",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "RUN_ORCH_READY"
    assert rows[0]["readiness"] == "READY"
    assert rows[0]["ticker_rows"] == 1
    assert rows[0]["group_rows"] == 1
    assert rows[0]["action_summary_rows"] == 1
    assert rows[0]["decision_trace_rows"] > 0
    assert "SUMMARY datacenter_dashboard_enrichment_write.readiness=READY" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.ticker_decision_attempted=1" in output


def test_dry_run_writes_no_metadata_and_leaves_database_unchanged(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)
    before = {
        "ticker": _count_selection(db_path, "dc_dashboard_ticker_enrichment_daily"),
        "group": _count_selection(db_path, "dc_dashboard_group_enrichment_daily"),
        "action_summary": _count_selection(db_path, "dc_dashboard_action_summary_daily"),
        "decision_trace": _count_selection(db_path, "dc_dashboard_decision_trace_daily"),
    }

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
            "RUN_ORCH_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    after = {
        "ticker": _count_selection(db_path, "dc_dashboard_ticker_enrichment_daily"),
        "group": _count_selection(db_path, "dc_dashboard_group_enrichment_daily"),
        "action_summary": _count_selection(db_path, "dc_dashboard_action_summary_daily"),
        "decision_trace": _count_selection(db_path, "dc_dashboard_decision_trace_daily"),
    }
    assert exit_code == 0
    assert before == after
    assert _run_rows(db_path) == []
    assert "SUMMARY datacenter_dashboard_enrichment_write.status=DRY_RUN" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.ticker_decision_attempted=1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.metadata_written=0" in output


def test_orchestrator_passes_watchlist_file_to_ticker_stage(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    watchlist_file = _create_watchlist_file(tmp_path / "watchlist.txt", "NVDA\n")
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)

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
            "RUN_ORCH_WATCHLIST",
            "--watchlist-file",
            str(watchlist_file),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        is_watchlist = conn.execute(
            """
            SELECT is_watchlist
            FROM dc_dashboard_ticker_enrichment_daily
            WHERE signal_date = ? AND taxonomy_version = ? AND ticker = ?
            """,
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "NVDA"),
        ).fetchone()[0]
    assert is_watchlist == 1
    assert (
        f"SUMMARY datacenter_dashboard_enrichment_write.watchlist_file={watchlist_file}"
        in output
    )


def test_default_orchestrator_does_not_pass_upstream_rolling5_flag(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    captured: dict[str, list[str]] = {}
    _patch_orchestrator_stages_for_argv_capture(monkeypatch, captured)

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
            "RUN_ORCH_DEFAULT_FLAGS",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--use-upstream-rolling5-pullback" not in captured["ticker"]
    assert "--pullback-lookback-rows" not in captured["ticker"]
    assert (
        "SUMMARY datacenter_dashboard_enrichment_write.use_upstream_rolling5_pullback=0"
        in output
    )
    assert "SUMMARY datacenter_dashboard_enrichment_write.pullback_lookback_rows=" in output


def test_orchestrator_passes_upstream_rolling5_flag_and_lookback_rows_to_ticker_stage(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    captured: dict[str, list[str]] = {}
    _patch_orchestrator_stages_for_argv_capture(monkeypatch, captured)

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
            "RUN_ORCH_UPSTREAM_FLAGS",
            "--use-upstream-rolling5-pullback",
            "--pullback-lookback-rows",
            "5",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--use-upstream-rolling5-pullback" in captured["ticker"]
    assert captured["ticker"][
        captured["ticker"].index("--pullback-lookback-rows") + 1
    ] == "5"
    assert "--use-upstream-rolling5-pullback" not in captured["group"]
    assert "--pullback-lookback-rows" not in captured["group"]
    assert (
        "SUMMARY datacenter_dashboard_enrichment_write.use_upstream_rolling5_pullback=1"
        in output
    )
    assert "SUMMARY datacenter_dashboard_enrichment_write.pullback_lookback_rows=5" in output


def test_dry_run_passes_upstream_flags_but_writes_no_run_metadata(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    captured: dict[str, list[str]] = {}
    _patch_orchestrator_stages_for_argv_capture(monkeypatch, captured)

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
            "RUN_ORCH_DRY_UPSTREAM",
            "--dry-run",
            "--use-upstream-rolling5-pullback",
            "--pullback-lookback-rows",
            "5",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "--dry-run" in captured["ticker"]
    assert "--use-upstream-rolling5-pullback" in captured["ticker"]
    assert captured["ticker"][
        captured["ticker"].index("--pullback-lookback-rows") + 1
    ] == "5"
    assert _run_rows(db_path) == []
    assert "SUMMARY datacenter_dashboard_enrichment_write.status=DRY_RUN" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.metadata_written=0" in output


def test_skip_ticker_decision_results_in_partial_metadata(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, is_watchlist,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                0,
                "OK",
                "SEED",
                "SEED_RUN",
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
            "insert-missing",
            "--run-id",
            "RUN_ORCH_SKIP",
            "--skip-ticker-decision",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["readiness"] == "PARTIAL"
    assert "SUMMARY datacenter_dashboard_enrichment_write.ticker_decision_attempted=0" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.readiness=PARTIAL" in output


def test_skip_decision_trace_results_in_partial_metadata(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, is_watchlist,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                0,
                "OK",
                "SEED",
                "SEED_RUN",
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
            "insert-missing",
            "--run-id",
            "RUN_ORCH_SKIP_TRACE",
            "--skip-decision-trace",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["readiness"] == "PARTIAL"
    assert rows[0]["decision_trace_rows"] == 0
    assert "SUMMARY datacenter_dashboard_enrichment_write.decision_trace_attempted=0" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.ticker_decision_attempted=1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_write.readiness=PARTIAL" in output


def test_replace_date_metadata_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily (
                run_id, signal_date, taxonomy_version, status, readiness,
                ticker_rows, group_rows, action_summary_rows, decision_trace_rows,
                warnings, calc_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "OLD_SAME",
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "OK",
                    "PARTIAL",
                    1,
                    1,
                    0,
                    0,
                    None,
                    "OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "KEEP_DATE",
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "OK",
                    "PARTIAL",
                    1,
                    1,
                    0,
                    0,
                    None,
                    "OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "KEEP_TAXONOMY",
                    "2026-05-22",
                    "DC_TAXONOMY_OTHER_V1",
                    "OK",
                    "PARTIAL",
                    1,
                    1,
                    0,
                    0,
                    None,
                    "OLD",
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
            "RUN_ORCH_SCOPE",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = _run_rows(db_path)
    assert {(row["run_id"], row["signal_date"], row["taxonomy_version"]) for row in rows} == {
        ("KEEP_DATE", "2026-05-21", "DC_TAXONOMY_FULL_V1"),
        ("KEEP_TAXONOMY", "2026-05-22", "DC_TAXONOMY_OTHER_V1"),
        ("RUN_ORCH_SCOPE", "2026-05-22", "DC_TAXONOMY_FULL_V1"),
    }


def test_insert_missing_metadata_keeps_existing_run_row_unchanged(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily (
                run_id, signal_date, taxonomy_version, status, readiness,
                ticker_rows, group_rows, action_summary_rows, decision_trace_rows,
                warnings, calc_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RUN_ORCH_EXISTING",
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "OK",
                "READY",
                9,
                9,
                9,
                9,
                None,
                "OLD",
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
            "RUN_ORCH_EXISTING",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["ticker_rows"] == 9
    assert rows[0]["calc_version"] == "OLD"
    assert "SUMMARY datacenter_dashboard_enrichment_write.metadata_written=0" in output


def test_upsert_metadata_updates_existing_run_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily (
                run_id, signal_date, taxonomy_version, status, readiness,
                ticker_rows, group_rows, action_summary_rows, decision_trace_rows,
                warnings, calc_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RUN_ORCH_UPSERT",
                "2026-05-21",
                "DC_TAXONOMY_OLD",
                "OK",
                "PARTIAL",
                0,
                0,
                0,
                0,
                None,
                "OLD",
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
            "RUN_ORCH_UPSERT",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    rows = _run_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["signal_date"] == "2026-05-22"
    assert rows[0]["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert rows[0]["calc_version"] == "DATACENTER_DASHBOARD_ENRICHMENT_ORCHESTRATOR_V1"


def test_stage_failure_stops_execution_and_writes_no_metadata(tmp_path, capsys):
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
            "--run-id",
            "RUN_ORCH_FAIL",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "status=OK" not in captured.out
    assert "ticker stage failed" in captured.err
    assert _run_rows(db_path) == []


def test_ticker_decision_stage_failure_stops_before_action_summary_and_trace(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)

    def fail_stage(argv):
        print("ERROR: forced ticker decision failure", file=__import__("sys").stderr)
        return 1

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_enrichment_write.ticker_decision_main",
        fail_stage,
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
            "RUN_ORCH_DECISION_FAIL",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "SUMMARY datacenter_dashboard_enrichment_write.status=OK" not in captured.out
    assert "ticker_decision stage failed" in captured.err
    assert _count_selection(db_path, "dc_dashboard_action_summary_daily") == 0
    assert _count_selection(db_path, "dc_dashboard_decision_trace_daily") == 0
    assert _run_rows(db_path) == []


def test_audit_after_orchestrator_matches_written_sections(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_ticker_source_row(db_path)
    _insert_group_source_row(db_path)

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
            "RUN_ORCH_AUDIT",
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
    assert "section_readiness;decision_trace;READY;" in output
    assert "section_readiness;overall;READY;" in output
