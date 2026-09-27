from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from analysis.database_manager import DatabaseManager
from analysis.ecosystem_group_weighting import equal_membership_weight
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    build_group_synthetic_ohlc_rows,
    write_group_synthetic_ohlc_rows,
)
from rawcandle.cli import run_datacenter_weighting_structure_validation as cli
from rawcandle.datacenter_weighting_structure_validation import (
    StructureEvent,
    classify_material_change,
    match_structure_events,
    run_structure_validation,
)


def _event(date, *, family="BOS", event_type="BOS_UP", reason=None):
    return StructureEvent("layer", "Power", family, event_type, date, reason)


def test_event_matching_is_nearest_one_to_one_and_within_five_days():
    dates = [f"2024-01-{day:02d}" for day in range(1, 16)]
    rows = match_structure_events(
        [_event("2024-01-05"), _event("2024-01-10")],
        [_event("2024-01-03"), _event("2024-01-06"), _event("2024-01-15")],
        valid_dates_by_group={("layer", "Power"): dates},
    )
    assert sorted((row["status"], row["timing_shift_trading_days"] if row["timing_shift_trading_days"] is not None else 99) for row in rows) == sorted([
        ("MATCHED", 1),
        ("MATCHED", 5),
        ("WEIGHTED_ONLY", 99),
    ])


def test_event_matching_reports_equal_only_and_rejects_outside_window():
    dates = [f"2024-01-{day:02d}" for day in range(1, 16)]
    rows = match_structure_events(
        [_event("2024-01-01")],
        [_event("2024-01-10")],
        valid_dates_by_group={("layer", "Power"): dates},
    )
    assert [row["status"] for row in rows] == ["EQUAL_ONLY", "WEIGHTED_ONLY"]


def test_reset_reason_change_is_not_forced_to_matched():
    dates = [f"2024-01-{day:02d}" for day in range(1, 8)]
    rows = match_structure_events(
        [_event("2024-01-03", family="RESET", event_type="RESET", reason="DOUBLE_BOS_UP")],
        [_event("2024-01-04", family="RESET", event_type="RESET", reason="DOUBLE_BOS_DOWN")],
        valid_dates_by_group={("layer", "Power"): dates},
    )
    assert rows[0]["status"] == "REASON_CHANGED"
    assert rows[0]["timing_shift_trading_days"] == 1


def test_material_change_classification_uses_required_priority():
    assert classify_material_change(
        bos_reset_changed=True,
        trend_changed=True,
        structure_label_changed=True,
        structure_timing_changed=True,
        level_changed=True,
    ) == "BOS_RESET_CHANGE"
    assert classify_material_change(
        bos_reset_changed=False,
        trend_changed=True,
        structure_label_changed=True,
        structure_timing_changed=True,
        level_changed=True,
    ) == "TREND_CLASSIFICATION_CHANGE"
    assert classify_material_change(
        bos_reset_changed=False,
        trend_changed=False,
        structure_label_changed=False,
        structure_timing_changed=False,
        level_changed=True,
    ) == "LEVEL_CHANGE_ONLY"


def test_cli_forwards_validation_arguments(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "OK"}

    monkeypatch.setattr(cli, "run_structure_validation", fake_run)
    output = Path("temp/datacenter_effective_weight_structure_validation/test")
    result = cli.main(
        [
            "--analysis-db", str(tmp_path / "analysis.db"),
            "--price-db", str(tmp_path / "prices.db"),
            "--taxonomy-csv", str(tmp_path / "taxonomy.csv"),
            "--taxonomy-version", "DC_TAXONOMY_V1",
            "--chain-start-date", "2024-01-01",
            "--comparison-start-date", "2024-01-02",
            "--comparison-end-date", "2024-01-31",
            "--market", "usa",
            "--output-dir", str(output),
        ]
    )

    assert result == 0
    assert captured["output_dir"] == output
    assert captured["chain_start_date"] == "2024-01-01"
    assert "SUMMARY status=OK" in capsys.readouterr().out


def test_chain_safe_validation_reproduces_equal_baseline_and_is_deterministic(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,0,1.0,
""",
        encoding="utf-8",
    )
    price_db = tmp_path / "prices.db"
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(price_db) as conn:
        conn.execute(
            "CREATE TABLE osakedata (osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT)"
        )
        rows = []
        for day in range(1, 32):
            for ticker, scale in (("AAA", 1.0), ("BBB", 1.5)):
                close = 100.0 + (day * scale) + ((day % 5) * scale)
                rows.append((ticker, f"2024-01-{day:02d}", close, close + 1, close - 1, close, 100, "usa"))
        conn.executemany("INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    DatabaseManager(str(analysis_db)).close()
    equal_rows, _ = build_group_synthetic_ohlc_rows(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy,
        start_date="2024-01-02",
        end_date="2024-01-31",
        market="usa",
        calc_version="DC_SWING_OHLC_V1",
        run_id="equal",
        created_at_utc="2026-09-27T00:00:00Z",
        membership_weight_policy=equal_membership_weight,
    )
    write_group_synthetic_ohlc_rows(
        analysis_db_path=analysis_db,
        rows=equal_rows,
        start_date="2024-01-02",
        end_date="2024-01-31",
        calc_version="DC_SWING_OHLC_V1",
        write_mode="upsert",
    )

    summaries = []
    for lane in ("a", "b"):
        output = Path(
            "temp/datacenter_effective_weight_structure_validation"
        ) / lane
        summaries.append(
            run_structure_validation(
                analysis_db=analysis_db,
                price_db=price_db,
                taxonomy_csv=taxonomy,
                taxonomy_version="DC_TAXONOMY_V1",
                chain_start_date="2024-01-02",
                comparison_start_date="2024-01-02",
                comparison_end_date="2024-01-31",
                market="usa",
                output_dir=output,
            )
        )
        assert json.loads((output / "summary.json").read_text()) == summaries[-1]

    assert summaries[0] == summaries[1]
    assert summaries[0]["equal_baseline_reproduction_mismatch_count"] == 0
    assert summaries[0]["shared_structure_engine"] == "build_group_structure_updates"
