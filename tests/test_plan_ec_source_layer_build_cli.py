import csv
import sqlite3
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_build import main, plan_ec_source_layer_build


def _write_taxonomy_csv(path: Path, rows: list[list[object]], include_notes: bool = True) -> None:
    columns = [
        "taxonomy_version",
        "ticker",
        "layer",
        "subindustry",
        "report_group_status",
        "is_primary",
        "role_weight",
    ]
    if include_notes:
        columns.append("notes")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _write_watchlist(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def _create_source_db(path: Path, *, include_ec_table: bool = False, omit_table: str | None = None, date_shift: str | None = None) -> None:
    conn = sqlite3.connect(path)
    try:
        if include_ec_table:
            conn.execute("CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE eco_ecosystem (ecosystem_id INTEGER PRIMARY KEY)")

        if omit_table != "dc_ticker_swing_signal_daily":
            conn.execute(
                """
                CREATE TABLE dc_ticker_swing_signal_daily (
                    signal_date TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    primary_layer TEXT NOT NULL,
                    primary_subindustry TEXT NOT NULL,
                    signal_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (signal_date, taxonomy_version, ticker, signal_version)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily VALUES
                ('2026-06-05', 'DC_TAXONOMY_FULL_V1', 'NVDA', 'Compute silicon', 'GPUs', 'DC_SWING_SIGNAL_V1', 'RUN_TICKER', '2026-06-07T00:00:00Z')
                """
            )

        group_signal_date = "2026-06-05"
        synthetic_date = date_shift or "2026-06-05"
        index_date = "2026-06-05"

        if omit_table != "dc_group_swing_signal_daily":
            conn.execute(
                """
                CREATE TABLE dc_group_swing_signal_daily (
                    signal_date TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    group_type TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    signal_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (signal_date, taxonomy_version, group_type, group_name, signal_version)
                )
                """
            )
            conn.executemany(
                "INSERT INTO dc_group_swing_signal_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, 'DC_SWING_SIGNAL_V1', 'RUN_GROUP', '2026-06-07T00:00:00Z')",
                [
                    (group_signal_date, "ecosystem", "DC_ECOSYSTEM_TOTAL"),
                    (group_signal_date, "layer", "Compute silicon"),
                    (group_signal_date, "subindustry", "GPUs"),
                ],
            )

        if omit_table != "dc_group_synthetic_ohlc_daily":
            conn.execute(
                """
                CREATE TABLE dc_group_synthetic_ohlc_daily (
                    ohlc_date TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    group_type TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    calc_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (ohlc_date, taxonomy_version, group_type, group_name, calc_version)
                )
                """
            )
            conn.executemany(
                "INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, 'DC_SWING_OHLC_V1', 'RUN_SYNTH', '2026-06-07T00:00:00Z')",
                [
                    (synthetic_date, "layer", "Compute silicon"),
                    (synthetic_date, "subindustry", "GPUs"),
                ],
            )

        if omit_table != "dc_group_index_daily":
            conn.execute(
                """
                CREATE TABLE dc_group_index_daily (
                    index_date TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    group_type TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    calc_version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY (index_date, taxonomy_version, group_type, group_name)
                )
                """
            )
            conn.executemany(
                "INSERT INTO dc_group_index_daily VALUES (?, 'DC_TAXONOMY_FULL_V1', ?, ?, 'DC_INDEX_CALC_V1', 'RUN_INDEX', '2026-06-07T00:00:00Z')",
                [
                    (index_date, "ecosystem", "DC_ECOSYSTEM_TOTAL"),
                    (index_date, "layer", "Compute silicon"),
                    (index_date, "subindustry", "GPUs"),
                ],
            )

        if omit_table != "dc_pipeline_watermark":
            conn.execute(
                """
                CREATE TABLE dc_pipeline_watermark (
                    component_name TEXT NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    market TEXT NULL,
                    signal_version TEXT NULL,
                    calc_version TEXT NULL,
                    start_date TEXT NULL,
                    end_date TEXT NULL,
                    row_count INTEGER NULL,
                    status TEXT NOT NULL,
                    last_successful_run_id TEXT NULL,
                    last_successful_at_utc TEXT NULL,
                    notes TEXT NULL,
                    PRIMARY KEY (component_name, taxonomy_version, market, signal_version, calc_version)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO dc_pipeline_watermark VALUES
                ('TICKER_SWING_BASE', 'DC_TAXONOMY_FULL_V1', 'USA', 'DC_SWING_SIGNAL_V1', NULL, '2026-01-01', '2026-06-05', 1, 'OK', NULL, NULL, NULL)
                """
            )
        conn.commit()
    finally:
        conn.close()


def _base_args(db_path: Path, taxonomy_path: Path, watchlist_path: Path) -> list[str]:
    return [
        "--db",
        str(db_path),
        "--ecosystem",
        "DATACENTER",
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--taxonomy-csv",
        str(taxonomy_path),
        "--watchlist",
        str(watchlist_path),
        "--format",
        "text",
    ]


def test_plan_ready_no_write(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path)
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\nCRGY\n")

    exit_code = main(_base_args(db_path, taxonomy_path, watchlist_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "plan_status=READY_NO_WRITE_PLAN" in output
    assert "true_ec_tables=[]" in output
    assert "eco_tables=['eco_ecosystem']" in output
    assert "selected_signal_date=2026-06-05" in output
    assert "contains_crgy=True" in output
    assert "ticker_missing_in_taxonomy=[]" in output
    assert "taxonomy_only_tickers=[]" in output
    assert "Backup analysis.db" in output
    assert "Future write guardrails" in output


def test_plan_blocks_when_true_ec_schema_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path, include_ec_table=True)
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_EXISTING_EC_SCHEMA"


def test_plan_blocks_when_required_source_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path, omit_table="dc_group_index_daily")
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_MISSING_SOURCE"


def test_plan_blocks_when_latest_dates_do_not_align(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path, date_shift="2026-06-04")
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_DATE_MISMATCH"


def test_plan_blocks_when_taxonomy_version_mismatches(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path)
    _write_taxonomy_csv(
        taxonomy_path,
        [["WRONG_VERSION", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"


def test_plan_blocks_when_watchlist_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    _create_source_db(db_path)
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(tmp_path / "missing_watchlist.txt"),
    )

    assert summary["status"] == "BLOCKED_WATCHLIST_SOURCE"


def test_plan_blocks_when_universe_mapping_is_unclear(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path)
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "AMD", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "AMD\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_UNCLEAR_MAPPING"
    assert summary["mapping_summary"]["ticker_missing_in_taxonomy"] == ["NVDA"]
    assert summary["mapping_summary"]["taxonomy_only_tickers"] == ["AMD"]


def test_plan_allows_explicit_signal_date_when_covered(tmp_path: Path) -> None:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _create_source_db(db_path)
    _write_taxonomy_csv(
        taxonomy_path,
        [["DC_TAXONOMY_FULL_V1", "NVDA", "Compute silicon", "GPUs", "CORE", 1, 1.0, ""]],
    )
    _write_watchlist(watchlist_path, "NVDA\n")

    summary = plan_ec_source_layer_build(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V1",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
        signal_date="2026-06-05",
    )

    assert summary["status"] == "READY_NO_WRITE_PLAN"
    assert summary["selected_date_info"]["selected_signal_date"] == "2026-06-05"
