from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dev_tools.datacenter_dashboard_decisions import build_datacenter_ticker_decisions
from dev_tools.datacenter_dashboard_parser import parse_datacenter_dashboard_reports
from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status
from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)
from dev_tools.ecosystem_dashboard_persistence import (
    assert_run_id_missing,
    connect_dashboard_db,
    delete_runs_for_ecosystem_date,
    ensure_dashboard_schema,
    insert_many,
    persist_ecosystem_dashboard_input,
)
from dev_tools.run_datacenter_dashboard_html import (
    _REPORT_DATE_RE,
    _collect_rows,
    build_dashboard_market_map_model,
    build_dashboard_ticker_model,
    build_dashboard_watchlist_model,
    generate_datacenter_dashboard_html_file,
)

DEFAULT_DASHBOARD_DB = "/home/kalle/projects/rawcandle/data/ecosystem_dashboard.db"
SUPPORTED_ECOSYSTEM_CODES = ("DATACENTER",)
ACTION_ORDER = (
    "SELL",
    "REDUCE",
    "TIGHTEN_STOP",
    "BLOCKED",
    "WAIT_PULLBACK",
    "BUY_NOW",
    "WATCH",
    "NEUTRAL",
)
SOURCE_REPORT_KIND = "dashboard_report"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and persist ecosystem dashboard snapshots into a separate SQLite DB."
    )
    parser.add_argument("--dashboard-db", required=True)
    parser.add_argument("--ecosystem-code", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--input-mode", default="reports")
    parser.add_argument("--mode", choices=("replace-date", "insert"), default="replace-date")
    parser.add_argument("--run-id")
    parser.add_argument("--render-html", action="store_true")
    parser.add_argument("--html-output")
    parser.add_argument("--title")
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_run_id(ecosystem_code: str, report_date: str, generated_at_utc: str) -> str:
    timestamp = generated_at_utc.replace("-", "").replace(":", "")
    return f"ECO_DASHBOARD_{ecosystem_code}_{report_date}_{timestamp}"


def _modified_at_utc(path: str | None) -> str | None:
    if not path:
        return None
    stat_result = Path(path).stat()
    return datetime.fromtimestamp(
        stat_result.st_mtime, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_ecosystem_code(ecosystem_code: str) -> str:
    normalized = ecosystem_code.strip().upper()
    if normalized not in SUPPORTED_ECOSYSTEM_CODES:
        raise ValueError(
            f"unsupported ecosystem_code={ecosystem_code}; currently supported: DATACENTER"
        )
    return normalized


def _market_map_hierarchy_fields(
    market_level: str,
    name: str,
    layer: str | None,
) -> tuple[str | None, str | None, str | None]:
    if market_level == "ECOSYSTEM":
        return None, None, None
    if market_level == "LAYER":
        taxonomy_path = f"DC_ECOSYSTEM_TOTAL > {name}"
        return "DC_ECOSYSTEM_TOTAL", None, taxonomy_path
    taxonomy_path = f"DC_ECOSYSTEM_TOTAL > {layer or '-'} > {name}"
    return layer, name, taxonomy_path


def _validate_input_mode(input_mode: str) -> str:
    normalized = input_mode.strip().lower()
    if normalized != "reports":
        raise ValueError(f"unsupported input_mode={input_mode}; currently supported: reports")
    return normalized


def _build_dashboard_input_from_reports(
    *,
    ecosystem_code: str,
    reports_dir: str,
    report_date: str,
) -> tuple[EcosystemDashboardInput, str]:
    dashboard_status = discover_datacenter_dashboard_status(
        reports_dir,
        report_date=report_date,
    )
    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    if found_reports == 0:
        raise FileNotFoundError(
            f"no reports found for report_date={report_date} in {reports_dir}"
        )

    parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    market_map_rows = build_dashboard_market_map_model(dashboard_status)
    watchlist_rows = build_dashboard_watchlist_model(parsed_rows, decision_result.decisions)
    ticker_rows = build_dashboard_ticker_model(parsed_rows, decision_result.decisions)

    dashboard_input = EcosystemDashboardInput(
        ecosystem_code=ecosystem_code,
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path=report.path,
                source_report_type=report.horizon,
                source_report_date=report_date,
                loaded_row_count=None,
                status=report.status,
            )
            for report in dashboard_status.reports
        ],
        action_summary=[
            EcosystemDashboardActionSummaryInput(
                action_bucket=action,
                action_label=action,
                ticker_count=decision_result.action_counts.get(action, 0),
                weight_sum=None,
                notes=None,
            )
            for action in ACTION_ORDER
        ],
        market_map=[
            EcosystemDashboardMarketMapInput(
                layer_order=None,
                subindustry_order=None,
                layer_name=row.layer,
                subindustry_name=row.name if row.market_level == "SUBINDUSTRY" else None,
                ticker_count=None,
                watchlist_count=None,
                avg_return_5d=row.return_5d,
                avg_return_20d=row.return_20d,
                avg_return_60d=row.return_60d,
                avg_trend_score=None,
                avg_action_score=None,
                dominant_action_bucket=row.current_status,
            )
            for row in market_map_rows
        ],
        watchlist=[
            EcosystemDashboardWatchlistInput(
                ticker=row.ticker,
                company_name=None,
                layer_name=None,
                subindustry_name=None,
                action_bucket=row.action,
                action_label=row.severity,
                watchlist_reason=row.primary_reason,
                last_close=None,
                return_5d=None,
                return_20d=None,
                return_60d=None,
                trend_state=row.trend_state,
                latest_structure_label=row.latest_structure_label,
                latest_bos_event_type=row.latest_bos_event_type,
                latest_reset_reason=row.latest_reset_reason,
                bullish_candle_signal=row.latest_candle_age_td,
                bullish_divergence_signal=row.latest_divergence_age_td,
                hidden_bullish_divergence_signal=row.latest_chart_pattern_age_td,
                data_status=row.current_status,
            )
            for row in watchlist_rows
        ],
        tickers=[
            EcosystemDashboardTickerStatusInput(
                ticker=row.ticker,
                company_name=None,
                layer_name=None,
                subindustry_name=None,
                last_close=None,
                return_5d=None,
                return_20d=None,
                return_60d=None,
                trend_state=row.trend_state,
                latest_structure_label=row.latest_structure_label,
                latest_bos_event_type=row.latest_bos_event_type,
                latest_bos_freshness=row.freshness_status,
                latest_reset_reason=row.latest_reset_reason,
                latest_reset_freshness=row.freshness_status,
                bullish_candle_signal=row.latest_candle_age_td,
                bullish_divergence_signal=row.latest_divergence_age_td,
                hidden_bullish_divergence_signal=row.latest_chart_pattern_age_td,
                action_bucket=row.action,
                action_label=row.severity,
                data_status=row.current_status,
            )
            for row in ticker_rows
        ],
        decision_trace=[
            EcosystemDashboardDecisionTraceInput(
                ticker=decision.ticker,
                trace_order=trace_index,
                rule_group=trace.horizon,
                rule_name=trace.matched_rule,
                input_value=trace.matched_value,
                decision=trace.action,
                reason=trace.field_name,
            )
            for decision in decision_result.decisions
            for trace_index, trace in enumerate(decision.decision_trace)
        ],
        readiness=dashboard_status.overall_status,
        total_parsed_rows=parse_result.total_row_count,
        total_parse_warnings=parse_result.total_warning_count,
    )
    return dashboard_input, dashboard_status.overall_status


def generate_ecosystem_dashboard_build(
    *,
    dashboard_db: str,
    ecosystem_code: str,
    reports_dir: str,
    report_date: str,
    input_mode: str = "reports",
    mode: str,
    run_id: str | None = None,
) -> tuple[str, list[str]]:
    normalized_report_date = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized_report_date):
        raise ValueError(f"invalid report_date format: {normalized_report_date}")

    normalized_ecosystem_code = _validate_ecosystem_code(ecosystem_code)
    normalized_input_mode = _validate_input_mode(input_mode)

    dashboard_status = discover_datacenter_dashboard_status(
        reports_dir,
        report_date=normalized_report_date,
    )
    found_reports = sum(1 for report in dashboard_status.reports if report.status == "OK")
    missing_reports = sum(1 for report in dashboard_status.reports if report.status != "OK")
    if found_reports == 0:
        raise FileNotFoundError(
            f"no reports found for report_date={normalized_report_date} in {reports_dir}"
        )

    parse_result = parse_datacenter_dashboard_reports(dashboard_status.reports)
    parsed_rows = _collect_rows(dashboard_status)
    decision_result = build_datacenter_ticker_decisions(parsed_rows)
    market_map_rows = build_dashboard_market_map_model(dashboard_status)
    watchlist_rows = build_dashboard_watchlist_model(parsed_rows, decision_result.decisions)
    ticker_rows = build_dashboard_ticker_model(parsed_rows, decision_result.decisions)
    trace_rows = [
        (decision.ticker, trace_index, trace)
        for decision in decision_result.decisions
        for trace_index, trace in enumerate(decision.decision_trace)
    ]

    generated_at_utc = _utc_now_text()
    selected_run_id = run_id or _default_run_id(
        normalized_ecosystem_code,
        normalized_report_date,
        generated_at_utc,
    )

    conn = connect_dashboard_db(dashboard_db)
    ensure_dashboard_schema(conn)
    try:
        conn.execute("BEGIN")
        if mode == "replace-date":
            delete_runs_for_ecosystem_date(
                conn,
                ecosystem_code=normalized_ecosystem_code,
                report_date=normalized_report_date,
            )
        else:
            assert_run_id_missing(conn, selected_run_id)

        source_report_rows = [
            (
                selected_run_id,
                normalized_ecosystem_code,
                normalized_report_date,
                report.horizon,
                SOURCE_REPORT_KIND,
                report.path if report.path and report.path.lower().endswith(".md") else None,
                report.path if report.path and report.path.lower().endswith(".csv") else None,
                _modified_at_utc(report.path) if report.path else None,
                report.status,
                generated_at_utc,
            )
            for report in dashboard_status.reports
        ]
        insert_many(
            conn,
            """
            INSERT INTO ecosystem_dashboard_source_reports (
                run_id,
                ecosystem_code,
                report_date,
                horizon,
                report_kind,
                markdown_path,
                csv_path,
                modified_at_utc,
                status,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            source_report_rows,
        )

        conn.execute(
            """
            INSERT INTO ecosystem_dashboard_runs (
                run_id,
                ecosystem_code,
                report_date,
                taxonomy_version,
                generated_at_utc,
                reports_dir,
                selection_mode,
                readiness,
                found_reports,
                missing_reports,
                total_parsed_rows,
                total_parse_warnings,
                decision_total,
                market_map_rows,
                watchlist_rows,
                ticker_rows,
                source_reports_count,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selected_run_id,
                normalized_ecosystem_code,
                normalized_report_date,
                None,
                generated_at_utc,
                reports_dir,
                "report_date",
                dashboard_status.overall_status,
                found_reports,
                missing_reports,
                parse_result.total_row_count,
                parse_result.total_warning_count,
                len(decision_result.decisions),
                len(market_map_rows),
                len(watchlist_rows),
                len(ticker_rows),
                len(source_report_rows),
                generated_at_utc,
            ),
        )

        insert_many(
            conn,
            """
            INSERT INTO ecosystem_dashboard_action_summary (
                run_id,
                ecosystem_code,
                action,
                count,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    selected_run_id,
                    normalized_ecosystem_code,
                    action,
                    decision_result.action_counts.get(action, 0),
                    generated_at_utc,
                )
                for action in ACTION_ORDER
            ],
        )

        insert_many(
            conn,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    selected_run_id,
                    normalized_ecosystem_code,
                    normalized_report_date,
                    row.market_level,
                    row.name,
                    _market_map_hierarchy_fields(row.market_level, row.name, row.layer)[0],
                    row.layer,
                    _market_map_hierarchy_fields(row.market_level, row.name, row.layer)[1],
                    _market_map_hierarchy_fields(row.market_level, row.name, row.layer)[2],
                    None,
                    row.current_status,
                    row.start_status_30d,
                    row.status_change_30d,
                    row.status_change_5d,
                    row.window_status_30d,
                    row.window_status_5d,
                    row.window_status_2d,
                    row.overheat_risk,
                    row.pct_above_ema20,
                    row.pct_above_ma10,
                    row.ema20_breadth_delta_5d,
                    row.return_5d,
                    row.return_10d,
                    row.return_20d,
                    row.return_60d,
                    row.dow_trend_state,
                    row.dow_trend_state_age_td,
                    row.latest_structure_label,
                    row.latest_structure_age_td,
                    row.latest_bos_event_type,
                    row.latest_bos_age_td,
                    row.latest_reset_reason,
                    row.latest_reset_age_td,
                    row.latest_candle,
                    row.latest_candle_age_td,
                    row.latest_divergence,
                    row.latest_divergence_age_td,
                    row.latest_chart_pattern,
                    row.latest_chart_pattern_age_td,
                    row.source_horizons,
                    row.source_files,
                    generated_at_utc,
                )
                for row in market_map_rows
            ],
        )

        insert_many(
            conn,
            """
            INSERT INTO ecosystem_dashboard_watchlist_status (
                run_id,
                ecosystem_code,
                report_date,
                ticker,
                action,
                severity,
                primary_reason,
                current_status,
                start_status_30d,
                status_change_30d,
                status_change_5d,
                window_status_30d,
                window_status_5d,
                window_status_2d,
                ma_break_status,
                freshness_status,
                trend_state,
                trend_state_age_td,
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
                pullback_validity,
                entry_readiness,
                candidate_priority,
                candidate_priority_label,
                daily_status,
                rolling_2d_status,
                rolling_5d_status,
                rolling_30d_status,
                horizons_present,
                source_files,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    selected_run_id,
                    normalized_ecosystem_code,
                    normalized_report_date,
                    row.ticker,
                    row.action,
                    row.severity,
                    row.primary_reason,
                    row.current_status,
                    row.start_status_30d,
                    row.status_change_30d,
                    row.status_change_5d,
                    row.window_status_30d,
                    row.window_status_5d,
                    row.window_status_2d,
                    row.ma_break_status,
                    row.freshness_status,
                    row.trend_state,
                    row.trend_state_age_td,
                    row.latest_structure_label,
                    row.latest_structure_age_td,
                    row.latest_bos_event_type,
                    row.latest_bos_age_td,
                    row.latest_reset_reason,
                    row.latest_reset_age_td,
                    row.latest_candle,
                    row.latest_candle_age_td,
                    row.latest_divergence,
                    row.latest_divergence_age_td,
                    row.latest_chart_pattern,
                    row.latest_chart_pattern_age_td,
                    row.pullback_validity,
                    row.entry_readiness,
                    row.candidate_priority,
                    row.candidate_priority_label,
                    row.daily_status,
                    row.rolling_2d_status,
                    row.rolling_5d_status,
                    row.rolling_30d_status,
                    row.horizons_present,
                    row.source_files,
                    generated_at_utc,
                )
                for row in watchlist_rows
            ],
        )

        insert_many(
            conn,
            """
            INSERT INTO ecosystem_dashboard_ticker_status (
                run_id,
                ecosystem_code,
                report_date,
                ticker,
                action,
                severity,
                primary_reason,
                current_status,
                start_status_30d,
                status_change_30d,
                status_change_5d,
                window_status_30d,
                window_status_5d,
                window_status_2d,
                ma_break_status,
                freshness_status,
                trend_state,
                trend_state_age_td,
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
                pullback_validity,
                entry_readiness,
                candidate_priority,
                candidate_priority_label,
                daily_status,
                rolling_2d_status,
                rolling_5d_status,
                rolling_30d_status,
                horizons_present,
                source_files,
                is_watchlist,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    selected_run_id,
                    normalized_ecosystem_code,
                    normalized_report_date,
                    row.ticker,
                    row.action,
                    row.severity,
                    row.primary_reason,
                    row.current_status,
                    row.start_status_30d,
                    row.status_change_30d,
                    row.status_change_5d,
                    row.window_status_30d,
                    row.window_status_5d,
                    row.window_status_2d,
                    row.ma_break_status,
                    row.freshness_status,
                    row.trend_state,
                    row.trend_state_age_td,
                    row.latest_structure_label,
                    row.latest_structure_age_td,
                    row.latest_bos_event_type,
                    row.latest_bos_age_td,
                    row.latest_reset_reason,
                    row.latest_reset_age_td,
                    row.latest_candle,
                    row.latest_candle_age_td,
                    row.latest_divergence,
                    row.latest_divergence_age_td,
                    row.latest_chart_pattern,
                    row.latest_chart_pattern_age_td,
                    row.pullback_validity,
                    row.entry_readiness,
                    row.candidate_priority,
                    row.candidate_priority_label,
                    row.daily_status,
                    row.rolling_2d_status,
                    row.rolling_5d_status,
                    row.rolling_30d_status,
                    row.horizons_present,
                    row.source_files,
                    row.is_watchlist,
                    generated_at_utc,
                )
                for row in ticker_rows
            ],
        )

        insert_many(
            conn,
            """
            INSERT INTO ecosystem_dashboard_decision_trace (
                run_id,
                ecosystem_code,
                ticker,
                trace_index,
                action,
                matched_rule,
                matched_token,
                matched_value,
                horizon,
                field,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    selected_run_id,
                    normalized_ecosystem_code,
                    ticker,
                    trace_index,
                    trace.action,
                    trace.matched_rule,
                    trace.matched_token,
                    trace.matched_value,
                    trace.horizon,
                    trace.field_name,
                    generated_at_utc,
                )
                for ticker, trace_index, trace in trace_rows
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary_lines = [
        "SUMMARY ecosystem_dashboard_build.status=OK",
        f"SUMMARY ecosystem_dashboard_build.run_id={selected_run_id}",
        f"SUMMARY ecosystem_dashboard_build.ecosystem_code={normalized_ecosystem_code}",
        f"SUMMARY ecosystem_dashboard_build.report_date={normalized_report_date}",
        f"SUMMARY ecosystem_dashboard_build.input_mode={normalized_input_mode}",
        f"SUMMARY ecosystem_dashboard_build.dashboard_db={dashboard_db}",
        f"SUMMARY ecosystem_dashboard_build.reports_dir={reports_dir}",
        f"SUMMARY ecosystem_dashboard_build.readiness={dashboard_status.overall_status}",
        f"SUMMARY ecosystem_dashboard_build.source_reports_count={len(source_report_rows)}",
        f"SUMMARY ecosystem_dashboard_build.total_parsed_rows={parse_result.total_row_count}",
        f"SUMMARY ecosystem_dashboard_build.total_parse_warnings={parse_result.total_warning_count}",
        f"SUMMARY ecosystem_dashboard_build.decision_total={len(decision_result.decisions)}",
        f"SUMMARY ecosystem_dashboard_build.market_map_rows={len(market_map_rows)}",
        f"SUMMARY ecosystem_dashboard_build.watchlist_rows={len(watchlist_rows)}",
        f"SUMMARY ecosystem_dashboard_build.ticker_rows={len(ticker_rows)}",
        f"SUMMARY ecosystem_dashboard_build.trace_rows={len(trace_rows)}",
        f"SUMMARY ecosystem_dashboard_build.mode={mode}",
    ]
    return selected_run_id, summary_lines


def _validate_render_html_args(
    *,
    render_html: bool,
    html_output: str | None,
    ecosystem_code: str,
) -> str | None:
    normalized_output = html_output.strip() if html_output is not None and html_output.strip() else None
    if render_html and normalized_output is None:
        raise ValueError("--html-output is required when --render-html is provided")
    if not render_html and normalized_output is not None:
        raise ValueError("--html-output requires --render-html")
    if not render_html:
        return None
    if ecosystem_code.strip().upper() != "DATACENTER":
        raise ValueError(
            f"--render-html is currently supported only for ecosystem_code=DATACENTER; got {ecosystem_code}"
        )
    output_parent = Path(normalized_output).parent
    if not output_parent.exists():
        raise ValueError(f"html output parent directory does not exist: {output_parent}")
    return normalized_output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        normalized_html_output = _validate_render_html_args(
            render_html=args.render_html,
            html_output=args.html_output,
            ecosystem_code=args.ecosystem_code,
        )
        built_run_id, summary_lines = generate_ecosystem_dashboard_build(
            dashboard_db=args.dashboard_db,
            ecosystem_code=args.ecosystem_code,
            reports_dir=args.reports_dir,
            report_date=args.report_date,
            input_mode=args.input_mode,
            mode=args.mode,
            run_id=args.run_id,
        )
    except ValueError as exc:
        print("SUMMARY ecosystem_dashboard_build.status=FAILED")
        print(f"ERROR: {exc}")
        return 2
    except (FileNotFoundError, sqlite3.DatabaseError, OSError) as exc:
        print("SUMMARY ecosystem_dashboard_build.status=FAILED")
        print(f"ERROR: {exc}")
        return 1
    if args.render_html:
        try:
            generate_datacenter_dashboard_html_file(
                dashboard_db=args.dashboard_db,
                ecosystem_code="DATACENTER",
                run_id=built_run_id,
                output=normalized_html_output,
                report_date=None,
                title=args.title,
            )
        except (ValueError, FileNotFoundError, sqlite3.DatabaseError, OSError) as exc:
            for line in summary_lines:
                print(line)
            print("SUMMARY ecosystem_dashboard_build.render_html_requested=1")
            print(f"SUMMARY ecosystem_dashboard_build.html_output_path={normalized_html_output}")
            print(f"ERROR: HTML render failed after successful build: {exc}")
            return 1
    for line in summary_lines:
        print(line)
    if args.render_html:
        print("SUMMARY ecosystem_dashboard_build.render_html_requested=1")
        print(f"SUMMARY ecosystem_dashboard_build.html_output_path={normalized_html_output}")
        print("SUMMARY ecosystem_dashboard_build.html_render_status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
