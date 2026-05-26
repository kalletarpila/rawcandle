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
from dev_tools.run_datacenter_dashboard_enrichment_parity_diagnosis import main


def _dashboard_input(
    *,
    report_date: str = "2026-05-22",
    ticker_symbols: list[str] | None = None,
    watchlist_tickers: list[str] | None = None,
    action_rows: list[tuple[str, int]] | None = None,
    layer_name: str = "Infrastructure",
    subindustry_name: str = "AI Accelerators",
    decision_trace_counts: dict[str, int] | None = None,
) -> EcosystemDashboardInput:
    tickers = ticker_symbols or ["AAA", "BBB"]
    watchlist = watchlist_tickers or []
    actions = action_rows or [("WATCH", len(tickers))]
    trace_counts = decision_trace_counts or {"AAA": 1}
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path=f"/tmp/{report_date}.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=len(tickers),
                status="OK",
            )
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=action,
                action_label=action,
                ticker_count=count,
                weight_sum=None,
                notes=None,
            )
            for action, count in actions
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=0,
                subindustry_order=0,
                layer_name=layer_name,
                subindustry_name=subindustry_name,
                ticker_count=len(tickers),
                watchlist_count=len(watchlist),
                avg_return_5d=0.1,
                avg_return_20d=0.2,
                avg_return_60d=0.3,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=actions[0][0] if actions else None,
            )
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=ticker,
                company_name=f"{ticker} Corp",
                layer_name=layer_name,
                subindustry_name=subindustry_name,
                action_bucket="WATCH",
                action_label="WATCH",
                watchlist_reason="momentum",
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
                ticker=ticker,
                company_name=f"{ticker} Corp",
                layer_name=layer_name,
                subindustry_name=subindustry_name,
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
                bullish_candle_signal=1,
                bullish_divergence_signal=0,
                hidden_bullish_divergence_signal=0,
                action_bucket="WATCH",
                action_label="WATCH",
                data_status="READY",
            )
            for ticker in tickers
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=ticker,
                trace_order=index,
                rule_group="daily",
                rule_name="RULE",
                input_value="signal",
                decision="WATCH",
                reason="momentum",
            )
            for ticker, count in sorted(trace_counts.items())
            for index in range(count)
        ],
        readiness="READY",
        total_parsed_rows=len(tickers),
        total_parse_warnings=0,
    )


def _persist(db_path: Path, dashboard_input: EcosystemDashboardInput, *, run_id: str) -> str:
    return persist_ecosystem_dashboard_input(
        dashboard_db=str(db_path),
        dashboard_input=dashboard_input,
        mode="insert",
        run_id=run_id,
    )


def _create_analysis_copy(
    db_path: Path,
    *,
    signal_date: str = "2026-05-22",
    ticker_rows: list[tuple[str, int, str | None]] | None = None,
    trace_rows: int = 0,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dc_dashboard_ticker_enrichment_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NULL,
            is_watchlist INTEGER NOT NULL DEFAULT 0
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
        CREATE TABLE dc_dashboard_group_enrichment_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            market_level TEXT NOT NULL,
            taxonomy_key TEXT NOT NULL
        )
        """
    )
    selected_rows = ticker_rows or []
    conn.executemany(
        """
        INSERT INTO dc_dashboard_ticker_enrichment_daily (
            signal_date,
            taxonomy_version,
            ticker,
            action,
            is_watchlist
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, ?)
        """,
        [(signal_date, ticker, action, is_watchlist) for ticker, is_watchlist, action in selected_rows],
    )
    if selected_rows:
        counts: dict[str, int] = {}
        for _, _, action in selected_rows:
            normalized = (action or "").strip()
            if normalized:
                counts[normalized] = counts.get(normalized, 0) + 1
        conn.executemany(
            """
            INSERT INTO dc_dashboard_action_summary_daily (
                signal_date,
                taxonomy_version,
                action,
                count
            ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)
            """,
            [(signal_date, action, count) for action, count in sorted(counts.items())],
        )
    conn.executemany(
        """
        INSERT INTO dc_dashboard_decision_trace_daily (
            signal_date,
            taxonomy_version,
            ticker,
            trace_index
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?)
        """,
        [
            (signal_date, f"TRACE{i % 2}", i)
            for i in range(trace_rows)
        ],
    )
    conn.execute(
        """
        INSERT INTO dc_dashboard_group_enrichment_daily (
            signal_date,
            taxonomy_version,
            market_level,
            taxonomy_key
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', 'LAYER', 'LAYER:Infrastructure')
        """,
        (signal_date,),
    )
    conn.commit()
    conn.close()


def _run_cli(
    capsys,
    *,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
    analysis_db_copy: Path | None = None,
    max_examples: int = 50,
):
    argv = [
        "--reports-dashboard-db",
        str(reports_db),
        "--reports-run-id",
        reports_run_id,
        "--enrichment-dashboard-db",
        str(enrichment_db),
        "--enrichment-run-id",
        enrichment_run_id,
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--max-examples",
        str(max_examples),
    ]
    if analysis_db_copy is not None:
        argv.extend(["--analysis-db-copy", str(analysis_db_copy)])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_basic_diagnosis_outputs_sections_and_summary(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_symbols=["AAA", "BBB"], watchlist_tickers=["AAA"]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_symbols=["AAA", "CCC"], watchlist_tickers=[]),
        run_id="ENRICH_RUN",
    )

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert error == ""
    assert "section;section_counts" in output
    assert "section_counts;watchlist;1;0;-1" in output
    assert "SUMMARY datacenter_dashboard_enrichment_parity_diagnosis.status=OK" in output


def test_watchlist_source_missing_hypothesis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(watchlist_tickers=["AAA"]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(watchlist_tickers=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        ticker_rows=[("AAA", 0, "WATCH"), ("BBB", 0, "WATCH")],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "hypothesis_summary;WATCHLIST_SOURCE_MISSING;LIKELY;" in output


def test_watchlist_export_mapping_issue_hypothesis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(watchlist_tickers=["AAA"]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(watchlist_tickers=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        ticker_rows=[("AAA", 1, "WATCH"), ("BBB", 0, "WATCH")],
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    assert "hypothesis_summary;WATCHLIST_EXPORT_MAPPING_ISSUE;LIKELY;" in output


def test_action_collapse_hypothesis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(action_rows=[("BUY", 1), ("WATCH", 1)]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(action_rows=[("WATCH", 2)]),
        run_id="ENRICH_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert "hypothesis_summary;ACTION_COLLAPSE;LIKELY;" in output


def test_trace_too_verbose_hypothesis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(decision_trace_counts={"AAA": 1, "BBB": 1}),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(decision_trace_counts={"AAA": 5, "BBB": 5}),
        run_id="ENRICH_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert "hypothesis_summary;TRACE_TOO_VERBOSE;LIKELY;" in output


def test_market_map_key_differences_are_reported(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(layer_name="Infrastructure", subindustry_name="AI Accelerators"),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(layer_name="Platforms", subindustry_name="Cloud Tools"),
        run_id="ENRICH_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert "market_map_key_differences;ONLY_REPORTS;" in output
    assert "market_map_key_differences;ONLY_ENRICHMENT;" in output


def test_ticker_count_near_parity_hypothesis(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(
        reports_db,
        _dashboard_input(ticker_symbols=["AAA", "BBB", "CCC"]),
        run_id="REPORTS_RUN",
    )
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(ticker_symbols=["AAA", "BBB"]),
        run_id="ENRICH_RUN",
    )

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
    )

    assert exit_code == 0
    assert "hypothesis_summary;TICKER_COUNT_NEAR_PARITY;LIKELY;" in output


def test_missing_db_or_run_id_fails_clearly(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    reports_run_id = _persist(reports_db, _dashboard_input(), run_id="REPORTS_RUN")
    _persist(enrichment_db, _dashboard_input(), run_id="ENRICH_RUN")

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id="MISSING_RUN",
    )

    assert exit_code == 1
    assert output == ""
    assert "ERROR:" in error
    assert "status=OK" not in error


def test_read_only_behavior_does_not_mutate_row_counts(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    reports_run_id = _persist(reports_db, _dashboard_input(), run_id="REPORTS_RUN")
    enrichment_run_id = _persist(
        enrichment_db,
        _dashboard_input(watchlist_tickers=[]),
        run_id="ENRICH_RUN",
    )
    _create_analysis_copy(
        analysis_db,
        ticker_rows=[("AAA", 0, "WATCH"), ("BBB", 0, "WATCH")],
        trace_rows=4,
    )
    with sqlite3.connect(analysis_db) as conn:
        before_ticker_rows = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        before_trace_rows = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_decision_trace_daily"
        ).fetchone()[0]

    exit_code, _, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db_copy=analysis_db,
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        after_ticker_rows = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        after_trace_rows = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_decision_trace_daily"
        ).fetchone()[0]
    assert after_ticker_rows == before_ticker_rows
    assert after_trace_rows == before_trace_rows
