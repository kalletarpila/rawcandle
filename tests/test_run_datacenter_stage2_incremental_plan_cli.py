from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from run_datacenter_stage2_incremental_plan import main as run_stage2_plan_main


TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"
SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"


def _create_analysis_db(path: Path) -> None:
    DatabaseManager(str(path)).close()


def _create_price_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.commit()


def _write_taxonomy_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes",
                f"{TAXONOMY_VERSION},AAA,Power,UPS,CORE,1,1.0,",
            ]
        ),
        encoding="utf-8",
    )


def _weekdays(start: str, count: int) -> list[str]:
    cursor = date.fromisoformat(start)
    values: list[str] = []
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _insert_prices(price_db: Path, dates: list[str]) -> None:
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", signal_date, 100, 101, 99, 100, 1000, "usa")
                for signal_date in dates
            ],
        )
        conn.commit()


def _watermark_count(analysis_db: Path) -> int:
    with sqlite3.connect(analysis_db) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM dc_pipeline_watermark").fetchone()[0])


def test_stage2_incremental_plan_cli_outputs_json_and_remains_read_only(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "osakedata.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    dates = _weekdays("2026-07-01", 8)
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)
    _write_taxonomy_csv(taxonomy_csv)
    _insert_prices(price_db, dates)
    upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="TICKER_SWING_BASE",
        taxonomy_version=TAXONOMY_VERSION,
        market="usa",
        signal_version=SIGNAL_VERSION,
        start_date=dates[0],
        end_date=dates[5],
        status="OK",
        last_successful_at_utc="2026-07-20T08:00:00Z",
    )
    before_count = _watermark_count(analysis_db)

    exit_code = run_stage2_plan_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            TAXONOMY_VERSION,
            "--market",
            "usa",
            "--requested-start",
            dates[0],
            "--requested-end",
            dates[-1],
            "--format",
            "json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["component"] == "TICKER_SWING_BASE"
    assert output["mode"] == "INCREMENTAL"
    assert output["reason_code"] == "NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP"
    assert [item["stage_number"] for item in output["downstream_stage_plans"]] == [3, 7, 8, 9]
    assert _watermark_count(analysis_db) == before_count


def test_stage2_incremental_plan_cli_rejects_invalid_overlap(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    price_db = tmp_path / "osakedata.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    dates = _weekdays("2026-07-01", 2)
    _create_analysis_db(analysis_db)
    _create_price_db(price_db)
    _write_taxonomy_csv(taxonomy_csv)
    _insert_prices(price_db, dates)

    exit_code = run_stage2_plan_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            TAXONOMY_VERSION,
            "--market",
            "usa",
            "--requested-start",
            dates[0],
            "--requested-end",
            dates[-1],
            "--stage2-overlap-trading-days",
            "-1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "overlap_trading_days" in captured.err
