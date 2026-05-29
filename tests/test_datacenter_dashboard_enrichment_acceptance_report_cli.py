from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.run_datacenter_dashboard_enrichment_acceptance_report import main


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    source_report_count: int = 1,
    ticker_rows: list[dict[str, object]] | None = None,
    watchlist_tickers: list[str] | None = None,
    market_map_rows: list[dict[str, object]] | None = None,
    trace_count_per_ticker: int = 1,
) -> EcosystemDashboardInput:
    rows = ticker_rows or []
    watchlist = watchlist_tickers or []
    action_counts: dict[str, int] = {}
    for row in rows:
        action = str(row.get("action") or "").strip()
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    market_rows = market_map_rows or [
        {
            "market_level": "ECOSYSTEM",
            "name": "DC_ECOSYSTEM_TOTAL",
            "parent_name": None,
            "layer": None,
            "subindustry": None,
            "taxonomy_path": "DC_ECOSYSTEM_TOTAL",
        }
    ]
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path=f"/tmp/report_{index}.md",
                source_report_type=["daily", "rolling_2d", "rolling_5d", "rolling_30d"][index % 4],
                source_report_date=report_date,
                loaded_row_count=len(rows),
                status="OK",
            )
            for index in range(source_report_count)
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=action,
                action_label=action,
                ticker_count=count,
                weight_sum=None,
                notes=None,
            )
            for action, count in sorted(action_counts.items())
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                market_level=row.get("market_level"),
                name=row.get("name"),
                parent_name=row.get("parent_name"),
                layer_name=row.get("layer"),
                subindustry_name=row.get("subindustry"),
                taxonomy_path=row.get("taxonomy_path"),
                layer_order=0,
                subindustry_order=0,
                ticker_count=len(rows),
                watchlist_count=len(watchlist),
                avg_return_5d=None,
                avg_return_20d=None,
                avg_return_60d=None,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=next(iter(action_counts), None),
            )
            for row in market_rows
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=ticker,
                company_name=f"{ticker} Corp",
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                action_bucket="WATCH",
                action_label="WATCH",
                watchlist_reason="reason",
                last_close=10.0,
                return_5d=1.0,
                return_20d=2.0,
                return_60d=3.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason=None,
                bullish_candle_signal=1,
                bullish_divergence_signal=0,
                hidden_bullish_divergence_signal=0,
                data_status="READY",
            )
            for ticker in watchlist
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=str(row["ticker"]),
                company_name=None,
                layer_name="Infrastructure",
                subindustry_name="AI Accelerators",
                last_close=10.0,
                return_5d=1.0,
                return_20d=2.0,
                return_60d=3.0,
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_bos_freshness="FRESH",
                latest_reset_reason=None,
                latest_reset_freshness=None,
                bullish_candle_signal=None,
                bullish_divergence_signal=None,
                hidden_bullish_divergence_signal=None,
                pullback_validity=row.get("pullback_validity"),
                entry_readiness=row.get("entry_readiness"),
                candidate_priority=row.get("candidate_priority"),
                candidate_priority_label=row.get("candidate_priority_label"),
                action_bucket=row.get("action"),
                action_label=row.get("action"),
                data_status="READY",
            )
            for row in rows
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=str(row["ticker"]),
                trace_order=index,
                rule_group="daily",
                rule_name="RULE",
                input_value="signal",
                decision=row.get("action"),
                reason=row.get("reason"),
            )
            for row in rows
            for index in range(trace_count_per_ticker)
        ],
        readiness="READY",
        total_parsed_rows=len(rows),
        total_parse_warnings=0,
    )


def _persist(db_path: Path, dashboard_input: EcosystemDashboardInput, *, run_id: str) -> str:
    return persist_ecosystem_dashboard_input(
        dashboard_db=str(db_path),
        dashboard_input=dashboard_input,
        mode="insert",
        run_id=run_id,
    )


def _replace_market_map_rows(
    db_path: Path,
    *,
    run_id: str,
    report_date: str,
    rows: list[dict[str, object]],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM ecosystem_dashboard_market_map WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO ecosystem_dashboard_market_map (
                run_id,
                ecosystem_code,
                report_date,
                market_level,
                name,
                parent_name,
                layer,
                subindustry,
                taxonomy_path,
                taxonomy_version,
                current_status,
                start_status_30d,
                status_change_30d,
                status_change_5d,
                window_status_30d,
                window_status_5d,
                window_status_2d,
                overheat_risk,
                pct_above_ema20,
                pct_above_ma10,
                ema20_breadth_delta_5d,
                return_5d,
                return_10d,
                return_20d,
                return_60d,
                dow_trend_state,
                dow_trend_state_age_td,
                latest_structure_label,
                latest_structure_age_td,
                latest_bos_event_type,
                latest_bos_age_td,
                latest_reset_reason,
                latest_reset_age_td,
                latest_candle,
                latest_candle_age_td,
                latest_divergence,
                latest_divergence_age_td,
                latest_chart_pattern,
                latest_chart_pattern_age_td,
                source_horizons,
                source_files,
                created_at_utc
            ) VALUES (?, 'DATACENTER', ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, '2026-05-27T00:00:00Z')
            """,
            [
                (
                    run_id,
                    report_date,
                    row.get("market_level"),
                    row.get("name"),
                    row.get("parent_name"),
                    row.get("layer"),
                    row.get("subindustry"),
                    row.get("taxonomy_path"),
                    row.get("current_status"),
                    row.get("source_horizons"),
                )
                for row in rows
            ],
        )


def _create_analysis_copy(path: Path, *, report_date: str = "2026-05-22", trace_rows: int = 0) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_group_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                taxonomy_key TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_action_summary_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                action TEXT NOT NULL,
                count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_decision_trace_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                trace_index INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_enrichment_run_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                run_id TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'AAA')
            """,
            (report_date,),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'ECOSYSTEM|DC_ECOSYSTEM_TOTAL')
            """,
            (report_date,),
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_action_summary_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'SELL', 1)
            """,
            (report_date,),
        )
        conn.executemany(
            """
            INSERT INTO dc_dashboard_decision_trace_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)
            """,
            [(report_date, "AAA", index) for index in range(trace_rows)],
        )
        conn.execute(
            """
            INSERT INTO dc_dashboard_enrichment_run_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', 'RUN')
            """,
            (report_date,),
        )


def _run_cli(
    capsys,
    *,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
    analysis_db: Path,
    fmt: str = "text",
):
    exit_code = main(
        [
            "--reports-dashboard-db",
            str(reports_db),
            "--reports-run-id",
            reports_run_id,
            "--enrichment-dashboard-db",
            str(enrichment_db),
            "--enrichment-run-id",
            enrichment_run_id,
            "--analysis-db-copy",
            str(analysis_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--format",
            fmt,
        ]
    )
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_basic_ok_report_with_accepted_differences(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            source_report_count=4,
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "BBB", "action": "REDUCE"},
                {"ticker": "CCC", "action": "TIGHTEN_STOP"},
            ],
            watchlist_tickers=["AAA", "BBB", "CRGY"],
            trace_count_per_ticker=1,
        ),
        run_id="REPORTS_RUN",
    )
    _replace_market_map_rows(
        reports_db,
        run_id=reports_run_id,
        report_date="2026-05-22",
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "DC_ECOSYSTEM_TOTAL",
                "parent_name": None,
                "layer": None,
                "subindustry": None,
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            source_report_count=1,
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL"},
                {"ticker": "BBB", "action": "TIGHTEN_STOP"},
                {"ticker": "CCC", "action": "TIGHTEN_STOP"},
            ],
            watchlist_tickers=["AAA", "BBB"],
            trace_count_per_ticker=3,
        ),
        run_id="ENRICH_RUN",
    )
    _replace_market_map_rows(
        enrichment_db,
        run_id=enrichment_run_id,
        report_date="2026-05-22",
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "DC_ECOSYSTEM_TOTAL",
                "parent_name": None,
                "layer": None,
                "subindustry": None,
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL",
                "current_status": "READY",
                "source_horizons": "daily",
            },
            {
                "market_level": "SUBINDUSTRY",
                "name": "CPUs",
                "parent_name": "Infrastructure",
                "layer": "Infrastructure",
                "subindustry": "CPUs",
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL > Infrastructure > CPUs",
                "current_status": "READY",
                "source_horizons": "daily",
            },
        ],
    )
    _create_analysis_copy(analysis_db, trace_rows=5)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_enrichment_acceptance_report.status=OK" in output
    assert (
        "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation="
        "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    ) in output
    assert "watchlist_acceptance;missing_watchlist_tickers;1;1;ACCEPTED_DIFF;CRGY_NOT_PART_OF_DATACENTER_ECOSYSTEM" in output


def test_large_unexplained_action_gap_creates_blocker(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL", "pullback_validity": "VALID_PULLBACK"},
                {"ticker": "BBB", "action": "SELL"},
                {"ticker": "CCC", "action": "SELL"},
                {"ticker": "DDD", "action": "SELL"},
                {"ticker": "EEE", "action": "SELL"},
                {"ticker": "FFF", "action": "SELL"},
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "REDUCE", "pullback_validity": "NO_PULLBACK"},
                {"ticker": "BBB", "action": "REDUCE"},
                {"ticker": "CCC", "action": "REDUCE"},
                {"ticker": "DDD", "action": "REDUCE"},
                {"ticker": "EEE", "action": "REDUCE"},
                {"ticker": "FFF", "action": "REDUCE"},
            ],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(analysis_db)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "blockers;action_parity;BLOCKING;UNEXPLAINED_ACTION_GAP" in output
    assert (
        "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation="
        "NOT_READY_NEEDS_MORE_FIXES"
    ) in output


def test_action_mismatches_do_not_block_when_factual_candidate_parity_is_clean(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    base_fields = {
        "pullback_validity": "VALID_PULLBACK",
        "entry_readiness": "READY",
        "candidate_priority": 1,
        "candidate_priority_label": "P1_READY",
    }
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "SELL", **base_fields},
                {"ticker": "BBB", "action": "SELL", **base_fields},
                {"ticker": "CCC", "action": "SELL", **base_fields},
                {"ticker": "DDD", "action": "SELL", **base_fields},
                {"ticker": "EEE", "action": "SELL", **base_fields},
                {"ticker": "FFF", "action": "SELL", **base_fields},
                {"ticker": "GGG", "action": "SELL", **base_fields},
                {"ticker": "HHH", "action": "SELL", **base_fields},
                {"ticker": "III", "action": "SELL", **base_fields},
                {"ticker": "JJJ", "action": "SELL", **base_fields},
                {"ticker": "KKK", "action": "SELL", **base_fields},
                {"ticker": "LLL", "action": "SELL", **base_fields},
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {"ticker": "AAA", "action": "REDUCE", **base_fields},
                {"ticker": "BBB", "action": "REDUCE", **base_fields},
                {"ticker": "CCC", "action": "REDUCE", **base_fields},
                {"ticker": "DDD", "action": "REDUCE", **base_fields},
                {"ticker": "EEE", "action": "REDUCE", **base_fields},
                {"ticker": "FFF", "action": "REDUCE", **base_fields},
                {"ticker": "GGG", "action": "REDUCE", **base_fields},
                {"ticker": "HHH", "action": "REDUCE", **base_fields},
                {"ticker": "III", "action": "REDUCE", **base_fields},
                {"ticker": "JJJ", "action": "REDUCE", **base_fields},
                {"ticker": "KKK", "action": "REDUCE", **base_fields},
                {"ticker": "LLL", "action": "REDUCE", **base_fields},
            ],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(analysis_db)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "factual_candidate_parity;pullback_validity_differences;0;0;OK;" in output
    assert "factual_candidate_parity;entry_readiness_differences;0;0;OK;" in output
    assert "factual_candidate_parity;candidate_priority_label_differences;0;0;OK;" in output
    assert (
        "action_acceptance;major_action_mismatches;12;12;ACCEPTED_DIFF;"
        "SELL_TO_REDUCE=12,REDUCE_TO_TIGHTEN_STOP=0"
    ) in output
    assert "blockers;action_parity;NON_BLOCKING;FACTUAL_CANDIDATE_PARITY_CLEAN" in output
    assert (
        "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation="
        "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    ) in output


def test_action_mismatches_still_block_when_factual_candidate_parity_is_not_clean(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[
                {
                    "ticker": "AAA",
                    "action": "SELL",
                    "pullback_validity": "VALID_PULLBACK",
                    "entry_readiness": "READY",
                    "candidate_priority": 1,
                    "candidate_priority_label": "P1_READY",
                }
            ],
        ),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[
                {
                    "ticker": "AAA",
                    "action": "REDUCE",
                    "pullback_validity": "NO_PULLBACK",
                    "entry_readiness": "NOT_READY",
                    "candidate_priority": 5,
                    "candidate_priority_label": "P5_NOT_READY",
                }
            ],
        ),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(analysis_db)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "factual_candidate_parity;pullback_validity_differences;1;1;REVIEW;" in output
    assert "blockers;action_parity;BLOCKING;UNEXPLAINED_ACTION_GAP" in output
    assert (
        "SUMMARY datacenter_dashboard_enrichment_acceptance_report.recommendation="
        "NOT_READY_NEEDS_MORE_FIXES"
    ) in output


def test_decision_trace_difference_accepted_as_verbose_v0(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}], trace_count_per_ticker=1),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}], trace_count_per_ticker=4),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(analysis_db, trace_rows=4)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "decision_trace_acceptance;trace_model;;enrichment_field_presence_v0;ACCEPTED_DIFF;CURRENT_STAGE_DECLARATION" in output
    assert "decision_trace_acceptance;trace_parity_required;;NO_FOR_CURRENT_STAGE;ACCEPTED_DIFF;TRACE_PARITY_NOT_REQUIRED_YET" in output


def test_market_map_ecosystem_identity_mismatch_creates_blocker(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
        ),
        run_id="REPORTS_RUN",
    )
    _replace_market_map_rows(
        reports_db,
        run_id=reports_run_id,
        report_date="2026-05-22",
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "DC_ECOSYSTEM_TOTAL",
                "parent_name": None,
                "layer": None,
                "subindustry": None,
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(
            ticker_rows=[{"ticker": "AAA", "action": "SELL"}],
        ),
        run_id="ENRICH_RUN",
    )
    _replace_market_map_rows(
        enrichment_db,
        run_id=enrichment_run_id,
        report_date="2026-05-22",
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "ECOSYSTEM",
                "parent_name": None,
                "layer": None,
                "subindustry": None,
                "taxonomy_path": "ECOSYSTEM",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    _create_analysis_copy(analysis_db)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "market_map_acceptance;ecosystem_identity_status;LIKELY_MISMATCH;LIKELY_MISMATCH;REVIEW;ECOSYSTEM_KEY_MISMATCH_LIKELY" in output
    assert "blockers;market_map_identity;BLOCKING;ECOSYSTEM_KEY_MISMATCH_LIKELY" in output


def test_missing_run_id_fails_clearly(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    _persist(reports_db, _dashboard_input(), run_id="REPORTS_RUN")
    _persist(enrichment_db, _dashboard_input(), run_id="ENRICH_RUN")
    _create_analysis_copy(analysis_db)

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id="MISSING_RUN",
        enrichment_db=enrichment_db,
        enrichment_run_id="ENRICH_RUN",
        analysis_db=analysis_db,
    )

    assert exit_code != 0
    assert output == ""
    assert "run_id not found" in error
    assert "status=OK" not in error


def test_read_only_behavior_keeps_row_counts_unchanged(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_rows=[{"ticker": "AAA", "action": "SELL"}]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(analysis_db, trace_rows=2)

    with sqlite3.connect(analysis_db) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_dashboard_ticker_enrichment_daily",
                "dc_dashboard_group_enrichment_daily",
                "dc_dashboard_action_summary_daily",
                "dc_dashboard_decision_trace_daily",
                "dc_dashboard_enrichment_run_daily",
            )
        }

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_enrichment_acceptance_report.status=OK" in output

    with sqlite3.connect(analysis_db) as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert after == before
