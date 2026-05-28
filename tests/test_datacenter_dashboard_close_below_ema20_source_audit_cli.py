from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.datacenter_dashboard_parser import DatacenterDashboardParseResult, DatacenterDashboardRow
from dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit import main


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO marker (value) VALUES ('ok')")


def _row(
    *,
    ticker: str,
    horizon: str,
    raw_status: str | None = None,
    raw_action: str | None = None,
    reason: str | None = None,
    blocking_reasons: str | None = None,
    ma_break_status: str | None = None,
    raw_fields: dict[str, str] | None = None,
) -> DatacenterDashboardRow:
    return DatacenterDashboardRow(
        ticker=ticker,
        horizon=horizon,
        source_file=f"/tmp/{ticker}_{horizon}.md",
        section="watchlist",
        row_kind="ticker",
        raw_action=raw_action,
        raw_status=raw_status,
        reason=reason,
        trend_state=None,
        latest_structure_label=None,
        latest_bos_event_type=None,
        latest_reset_reason=None,
        distance_to_ema20=None,
        high_exit_risk_days_count=None,
        blocking_reasons=blocking_reasons,
        ma_break_status=ma_break_status,
        ema20_break_confirmed=None,
        sma50_break_confirmed=None,
        close_below_ema20=None,
        close_below_sma50=None,
        consecutive_closes_below_ema20=None,
        consecutive_closes_below_sma50=None,
        ema20_break_pct=None,
        sma50_break_pct=None,
        freshness_status=None,
        structure_warning_overrides_bullish_signal=None,
        latest_bullish_signal_age_td=None,
        latest_bearish_signal_age_td=None,
        latest_bos_up_age_td=None,
        latest_bos_down_age_td=None,
        latest_reset_age_td=None,
        raw_fields=raw_fields or {},
    )


def _run_cli(
    capsys,
    monkeypatch,
    *,
    analysis_db: Path,
    reports_snapshot,
    enrichment_snapshot,
    reports_rows: list[DatacenterDashboardRow],
    enrichment_table_rows: list[dict[str, object]],
    enrichment_adapter_rows: list[DatacenterDashboardRow],
    source_rows_by_ticker: dict[str, dict[str, object]],
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: SimpleNamespace(
            reports=[SimpleNamespace(horizon="rolling 5d", path="/tmp/report.md")]
        ),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit.parse_datacenter_dashboard_file",
        lambda path, horizon: DatacenterDashboardParseResult(rows=reports_rows, warnings=[]),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit._taxonomy_version_for_report_date",
        lambda analysis_db, report_date: "DC_TAXONOMY_FULL_V1",
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit.load_ticker_enrichment_rows",
        lambda analysis_db, report_date, taxonomy_version: enrichment_table_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit.build_dashboard_rows_from_ticker_enrichment_rows",
        lambda rows: enrichment_adapter_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_close_below_ema20_source_audit._load_source_rows",
        lambda analysis_db, report_date, taxonomy_version: source_rows_by_ticker,
    )

    exit_code = main(
        [
            "--reports-dir",
            "/tmp/reports",
            "--reports-dashboard-db",
            "/tmp/reports.db",
            "--reports-run-id",
            "REPORTS_RUN",
            "--enrichment-dashboard-db",
            "/tmp/enrichment.db",
            "--enrichment-run-id",
            "ENRICH_RUN",
            "--analysis-db",
            str(analysis_db),
            "--ecosystem-code",
            "DATACENTER",
            "--report-date",
            "2026-05-22",
            "--max-examples",
            "100",
        ]
    )
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_reports_token_detection(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])
    reports_rows = [_row(ticker="AAA", horizon="daily", raw_fields={"close_below_ema20": "1"})]

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.reports_close_below_ema20_tickers=1" in output


def test_enrichment_lacks_token_hypothesis(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="daily", raw_fields={"close_below_ema20": "1"})],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert "hypothesis_summary;ENRICHMENT_LACKS_CLOSE_BELOW_EMA20_TOKEN;LIKELY;" in output


def test_distance_derivation(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="daily", raw_fields={"close_below_ema20": "1"})],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {"distance_to_ema20": -0.23}},
    )

    assert exit_code == 0
    assert "per_ticker_close_below_context;AAA;close_below_ema20;1;;-0.2300" in output
    assert "DISTANCE_NEGATIVE_MATCHES_REPORTS_TOKEN" in output
    assert "hypothesis_summary;DISTANCE_TO_EMA20_CAN_DERIVE_TOKEN;LIKELY;" in output


def test_missing_structured_equivalent(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="daily", raw_fields={"close_below_ema20": "1"})],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert "hypothesis_summary;NEEDS_REPORTS_ONLY_SEMANTIC_EXTRACTION;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.needs_reports_only_semantic_extraction=1" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="daily")],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_close_below_ema20_source_audit.status=OK" in output
    with sqlite3.connect(analysis_db) as conn:
        value = conn.execute("SELECT value FROM marker").fetchone()[0]
    assert value == "ok"
