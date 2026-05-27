from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardInput,
    EcosystemDashboardSourceReportInput,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.run_datacenter_dashboard_market_map_parity_diagnosis import main


def _base_dashboard_input(report_date: str = "2026-05-22") -> EcosystemDashboardInput:
    return EcosystemDashboardInput(
        ecosystem_code="DATACENTER",
        report_date=report_date,
        source_reports=[
            EcosystemDashboardSourceReportInput(
                source_report_path="/tmp/source.md",
                source_report_type="daily",
                source_report_date=report_date,
                loaded_row_count=0,
                status="OK",
            )
        ],
        action_summary=[],
        market_map=[],
        watchlist=[],
        tickers=[],
        decision_trace=[],
        readiness="READY",
        total_parsed_rows=0,
        total_parse_warnings=0,
    )


def _persist_dashboard(db_path: Path, *, run_id: str, report_date: str = "2026-05-22") -> str:
    return persist_ecosystem_dashboard_input(
        dashboard_db=str(db_path),
        dashboard_input=_base_dashboard_input(report_date=report_date),
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
    conn = sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM ecosystem_dashboard_market_map WHERE run_id = ?",
        (run_id,),
    )
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
                row["market_level"],
                row["name"],
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
    conn.commit()
    conn.close()


def _create_analysis_copy(
    db_path: Path,
    *,
    signal_date: str,
    rows: list[dict[str, object]],
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dc_dashboard_group_enrichment_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            market_level TEXT,
            taxonomy_key TEXT,
            name TEXT,
            parent_name TEXT,
            layer TEXT,
            subindustry TEXT,
            taxonomy_path TEXT,
            current_status TEXT,
            source_horizons TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO dc_dashboard_group_enrichment_daily (
            signal_date,
            taxonomy_version,
            market_level,
            taxonomy_key,
            name,
            parent_name,
            layer,
            subindustry,
            taxonomy_path,
            current_status,
            source_horizons
        ) VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                signal_date,
                row.get("market_level"),
                row.get("taxonomy_key"),
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
    conn.commit()
    conn.close()


def _run_cli(
    capsys,
    *,
    reports_db: Path,
    reports_run_id: str,
    enrichment_db: Path,
    enrichment_run_id: str,
    analysis_db: Path,
    report_date: str = "2026-05-22",
    max_examples: int = 100,
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
            report_date,
            "--max-examples",
            str(max_examples),
        ]
    )
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_market_map_key_shape_mismatch_detected(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    report_date = "2026-05-22"
    reports_run_id = _persist_dashboard(reports_db, run_id="REPORTS_RUN", report_date=report_date)
    enrichment_run_id = _persist_dashboard(
        enrichment_db, run_id="ENRICHMENT_RUN", report_date=report_date
    )
    _replace_market_map_rows(
        reports_db,
        run_id=reports_run_id,
        report_date=report_date,
        rows=[
            {
                "market_level": "SUBINDUSTRY",
                "name": "AI Accelerators",
                "parent_name": "Infrastructure",
                "layer": "Infrastructure",
                "subindustry": "AI Accelerators",
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL > Infrastructure > AI Accelerators",
                "current_status": "READY",
                "source_horizons": "daily,rolling 2d",
            }
        ],
    )
    _replace_market_map_rows(
        enrichment_db,
        run_id=enrichment_run_id,
        report_date=report_date,
        rows=[
            {
                "market_level": "SUBINDUSTRY",
                "name": "AI Accelerators",
                "parent_name": "",
                "layer": "",
                "subindustry": "AI Accelerators",
                "taxonomy_path": "SUBINDUSTRY|AI Accelerators",
                "current_status": "READY",
                "source_horizons": "",
            }
        ],
    )
    _create_analysis_copy(
        analysis_db,
        signal_date=report_date,
        rows=[
            {
                "market_level": "SUBINDUSTRY",
                "taxonomy_key": "SUBINDUSTRY:AI Accelerators",
                "name": "AI Accelerators",
                "parent_name": "",
                "layer": "",
                "subindustry": "AI Accelerators",
                "taxonomy_path": "SUBINDUSTRY|AI Accelerators",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )

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
    assert (
        "possible_key_matches;DC_ECOSYSTEM_TOTAL > Infrastructure > AI Accelerators;"
        "SUBINDUSTRY|AI Accelerators;SAME_SUBINDUSTRY_NAME_DIFFERENT_KEY"
    ) in output
    assert (
        "hypothesis_summary;MARKET_MAP_DIFF_IS_KEY_SHAPE_NOT_CONTENT;LIKELY;"
    ) in output
    assert (
        "hypothesis_summary;ENRICHMENT_MISSING_PARENT_LAYER_FOR_SUBINDUSTRIES;LIKELY;"
    ) in output
    assert (
        "hypothesis_summary;SOURCE_HORIZONS_MISSING_IN_ENRICHMENT;LIKELY;"
    ) in output


def test_market_map_extra_taxonomy_group_detected(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    report_date = "2026-05-22"
    reports_run_id = _persist_dashboard(reports_db, run_id="REPORTS_RUN", report_date=report_date)
    enrichment_run_id = _persist_dashboard(
        enrichment_db, run_id="ENRICHMENT_RUN", report_date=report_date
    )
    _replace_market_map_rows(
        reports_db,
        run_id=reports_run_id,
        report_date=report_date,
        rows=[],
    )
    _replace_market_map_rows(
        enrichment_db,
        run_id=enrichment_run_id,
        report_date=report_date,
        rows=[
            {
                "market_level": "SUBINDUSTRY",
                "name": "Virtualization / cloud software",
                "parent_name": "",
                "layer": "",
                "subindustry": "Virtualization / cloud software",
                "taxonomy_path": "SUBINDUSTRY|Virtualization / cloud software",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    _create_analysis_copy(analysis_db, signal_date=report_date, rows=[])

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert "hypothesis_summary;ENRICHMENT_HAS_EXTRA_TAXONOMY_GROUPS;LIKELY;" in output
    assert (
        "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.unmatched_enrichment=1"
        in output
    )


def test_market_map_ecosystem_key_mismatch_detected(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    report_date = "2026-05-22"
    reports_run_id = _persist_dashboard(reports_db, run_id="REPORTS_RUN", report_date=report_date)
    enrichment_run_id = _persist_dashboard(
        enrichment_db, run_id="ENRICHMENT_RUN", report_date=report_date
    )
    _replace_market_map_rows(
        reports_db,
        run_id=reports_run_id,
        report_date=report_date,
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "DC_ECOSYSTEM_TOTAL",
                "parent_name": "",
                "layer": "",
                "subindustry": "",
                "taxonomy_path": "DC_ECOSYSTEM_TOTAL",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    _replace_market_map_rows(
        enrichment_db,
        run_id=enrichment_run_id,
        report_date=report_date,
        rows=[
            {
                "market_level": "ECOSYSTEM",
                "name": "ECOSYSTEM",
                "parent_name": "",
                "layer": "",
                "subindustry": "",
                "taxonomy_path": "ECOSYSTEM|ECOSYSTEM",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    _create_analysis_copy(analysis_db, signal_date=report_date, rows=[])

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 0
    assert "hypothesis_summary;ECOSYSTEM_KEY_MISMATCH;LIKELY;" in output


def test_market_map_read_only_behavior(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    report_date = "2026-05-22"
    reports_run_id = _persist_dashboard(reports_db, run_id="REPORTS_RUN", report_date=report_date)
    enrichment_run_id = _persist_dashboard(
        enrichment_db, run_id="ENRICHMENT_RUN", report_date=report_date
    )
    _replace_market_map_rows(reports_db, run_id=reports_run_id, report_date=report_date, rows=[])
    _replace_market_map_rows(
        enrichment_db, run_id=enrichment_run_id, report_date=report_date, rows=[]
    )
    _create_analysis_copy(
        analysis_db,
        signal_date=report_date,
        rows=[
            {
                "market_level": "LAYER",
                "taxonomy_key": "LAYER:Infrastructure",
                "name": "Infrastructure",
                "parent_name": "DC_ECOSYSTEM_TOTAL",
                "layer": "Infrastructure",
                "subindustry": "",
                "taxonomy_path": "LAYER|Infrastructure",
                "current_status": "READY",
                "source_horizons": "daily",
            }
        ],
    )
    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_group_enrichment_daily"
        ).fetchone()[0]

    exit_code, output, _ = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_group_enrichment_daily"
        ).fetchone()[0]

    assert exit_code == 0
    assert before == after
    assert "SUMMARY datacenter_dashboard_market_map_parity_diagnosis.status=OK" in output


def test_market_map_missing_analysis_table_fails_clearly(tmp_path, capsys):
    reports_db = tmp_path / "reports.db"
    enrichment_db = tmp_path / "enrichment.db"
    analysis_db = tmp_path / "analysis.db"
    report_date = "2026-05-22"
    reports_run_id = _persist_dashboard(reports_db, run_id="REPORTS_RUN", report_date=report_date)
    enrichment_run_id = _persist_dashboard(
        enrichment_db, run_id="ENRICHMENT_RUN", report_date=report_date
    )
    sqlite3.connect(analysis_db).close()

    exit_code, output, error = _run_cli(
        capsys,
        reports_db=reports_db,
        reports_run_id=reports_run_id,
        enrichment_db=enrichment_db,
        enrichment_run_id=enrichment_run_id,
        analysis_db=analysis_db,
    )

    assert exit_code == 1
    assert output == ""
    assert "required table missing: dc_dashboard_group_enrichment_daily" in error
