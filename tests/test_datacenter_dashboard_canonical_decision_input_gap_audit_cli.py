from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.datacenter_dashboard_parser import DatacenterDashboardParseResult, DatacenterDashboardRow
from dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit import main


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
    freshness_status: str | None = None,
    latest_bos_event_type: str | None = None,
    latest_reset_reason: str | None = None,
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
        latest_bos_event_type=latest_bos_event_type,
        latest_reset_reason=latest_reset_reason,
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
        freshness_status=freshness_status,
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
    tickers: str | None = None,
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: SimpleNamespace(
            reports=[SimpleNamespace(horizon="rolling 5d", path="/tmp/report.md")]
        ),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit.parse_datacenter_dashboard_file",
        lambda path, horizon: DatacenterDashboardParseResult(rows=reports_rows, warnings=[]),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit._taxonomy_version_for_report_date",
        lambda analysis_db, report_date: "DC_TAXONOMY_FULL_V1",
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit.load_ticker_enrichment_rows",
        lambda analysis_db, report_date, taxonomy_version: enrichment_table_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit.build_dashboard_rows_from_ticker_enrichment_rows",
        lambda rows: enrichment_adapter_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_canonical_decision_input_gap_audit._load_source_rows",
        lambda analysis_db, report_date, taxonomy_version: source_rows_by_ticker,
    )

    argv = [
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
    if tickers is not None:
        argv.extend(["--tickers", tickers])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_field_present_in_enrichment_table_but_missing_from_adapter(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="rolling 5d", raw_fields={"pullback_days": "3"})]
    enrichment_table_rows = [{"ticker": "AAA", "pullback_days": 3}]
    enrichment_adapter_rows = [_row(ticker="AAA", horizon="rolling 5d")]

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=enrichment_table_rows,
        enrichment_adapter_rows=enrichment_adapter_rows,
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert error == ""
    assert "per_ticker_gap_attribution;AAA;MISSING_FIELD;pullback_days;3;;PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER;" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.top_gap=pullback_days" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.top_gap_attribution=PRESENT_IN_ENRICHMENT_TABLE_NOT_ADAPTER" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.recommended_fix_type=ADAPTER_EXPOSURE_FIX" in output


def test_field_present_in_source_but_missing_from_enrichment(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="daily", ma_break_status="EMA20_BREAK_CONFIRMED")]

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="daily")],
        source_rows_by_ticker={"AAA": {"ma_break_status": "EMA20_BREAK_CONFIRMED"}},
    )

    assert exit_code == 0
    assert "per_ticker_gap_attribution;AAA;MISSING_FIELD;ma_break_status;EMA20_BREAK_CONFIRMED;;PRESENT_IN_SOURCE_NOT_ENRICHMENT;" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.top_gap_attribution=PRESENT_IN_SOURCE_NOT_ENRICHMENT" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.recommended_fix_type=ENRICHMENT_WRITER_MAPPING_FIX" in output


def test_field_present_only_in_reports(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="rolling 5d", raw_fields={"return_10d_lt_minus_8pct": "1"})]

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="rolling 5d")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert "per_ticker_gap_attribution;AAA;MISSING_FIELD;return_10d_lt_minus_8pct;1;;PRESENT_IN_REPORTS_ONLY;" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.recommended_fix_type=REPORTS_ONLY_SEMANTIC" in output


def test_field_present_with_different_name(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="rolling 5d", blocking_reasons="recent_bos_down")]
    enrichment_table_rows = [{"ticker": "AAA", "blocking_reason": "recent_bos_down"}]
    enrichment_adapter_rows = [_row(ticker="AAA", horizon="rolling 5d", raw_fields={"blocking_reason": "recent_bos_down"})]

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=enrichment_table_rows,
        enrichment_adapter_rows=enrichment_adapter_rows,
        source_rows_by_ticker={"AAA": {}},
        tickers="AAA",
    )

    assert exit_code == 0
    assert "per_ticker_gap_attribution;AAA;DIFFERENT_FIELD_NAME;blocking_reason;recent_bos_down;recent_bos_down;PRESENT_WITH_DIFFERENT_NAME;" in output


def test_top_explanatory_gap_ranks_deterministically(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"},
            {"ticker": "BBB", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"},
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"},
            {"ticker": "BBB", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"},
        ]
    )
    reports_rows = [
        _row(ticker="AAA", horizon="rolling 5d", raw_fields={"pullback_days": "3"}),
        _row(ticker="BBB", horizon="rolling 5d", raw_fields={"pullback_days": "2"}),
    ]
    enrichment_adapter_rows = [
        _row(ticker="AAA", horizon="rolling 5d"),
        _row(ticker="BBB", horizon="rolling 5d"),
    ]

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_table_rows=[{"ticker": "AAA"}, {"ticker": "BBB"}],
        enrichment_adapter_rows=enrichment_adapter_rows,
        source_rows_by_ticker={"AAA": {}, "BBB": {}},
    )

    assert exit_code == 0
    assert "top_explanatory_gaps;1;pullback_days;2;DERIVABLE_FROM_SHARED_HELPER;AAA,BBB;SHARED_HELPER_PAYLOAD_FIX" in output


def test_factual_parity_blocker_confirmed_when_pullback_differences_exist(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="rolling 5d")],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="rolling 5d")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert "hypothesis_summary;FACTUAL_PARITY_BLOCKER_CONFIRMED;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.factual_parity_blocker_confirmed=1" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=[_row(ticker="AAA", horizon="rolling 5d")],
        enrichment_table_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=[_row(ticker="AAA", horizon="rolling 5d")],
        source_rows_by_ticker={"AAA": {}},
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_canonical_decision_input_gap_audit.status=OK" in output
    with sqlite3.connect(analysis_db) as conn:
        value = conn.execute("SELECT value FROM marker").fetchone()[0]
    assert value == "ok"
