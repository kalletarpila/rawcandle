import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.run_datacenter_dashboard_group_enrichment_write import main
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


def _create_empty_db(path: Path) -> None:
    with sqlite3.connect(path):
        pass


def _create_taxonomy_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    path.write_text(
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
        + "\n".join(
            f"DC_TAXONOMY_FULL_V1,T{index},{layer},{subindustry},CORE,1,1.0,"
            for index, (layer, subindustry) in enumerate(rows, start=1)
        )
        + "\n",
        encoding="utf-8",
    )


def _create_group_source_table_only(path: Path) -> None:
    with sqlite3.connect(path) as conn:
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
    _create_group_source_table_only(path)
    with sqlite3.connect(path) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                primary_layer TEXT,
                primary_subindustry TEXT,
                signal_version TEXT,
                run_id TEXT
            )
            """
        )


def _create_synthetic_table(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_group_synthetic_ohlc_daily (
                ohlc_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                group_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                trend_classification TEXT,
                latest_structure_label TEXT,
                latest_structure_age_trading_days INTEGER,
                latest_bos_event_type TEXT,
                latest_bos_age_trading_days INTEGER,
                latest_reset_reason TEXT,
                latest_reset_age_trading_days INTEGER,
                calc_version TEXT,
                run_id TEXT
            )
            """
        )


def _insert_group_source_rows(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name, timing_state,
                overheat_risk_level, pct_above_ema20, pct_above_ma10, ema20_breadth_delta_5d,
                return_5d, return_10d, return_20d, return_60d, data_quality_status,
                signal_version, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ecosystem",
                    "DC_ECOSYSTEM_TOTAL",
                    "BUY_ZONE",
                    "LOW",
                    60.0,
                    55.0,
                    3.0,
                    0.10,
                    0.15,
                    0.20,
                    0.40,
                    "OK",
                    "SIG_V1",
                    "RUN_SWING_A",
                ),
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
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "subindustry",
                    "AI Accelerators",
                    "TRIM_WATCH",
                    "HIGH",
                    40.0,
                    42.0,
                    -1.0,
                    -0.10,
                    -0.15,
                    -0.20,
                    -0.30,
                    "WARN",
                    "SIG_V1",
                    "RUN_SWING_B",
                ),
            ],
        )


def _insert_ticker_taxonomy_rows(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date,
                taxonomy_version,
                ticker,
                primary_layer,
                primary_subindustry,
                signal_version,
                run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "NVDA",
                    "Compute silicon",
                    "AI Accelerators",
                    "SIG_V1",
                    "RUN_TICKER_A",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "SMCI",
                    "Infrastructure",
                    "Servers / ODM / EMS",
                    "SIG_V1",
                    "RUN_TICKER_A",
                ),
            ],
        )


def _insert_synthetic_rows(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name, trend_classification,
                latest_structure_label, latest_structure_age_trading_days,
                latest_bos_event_type, latest_bos_age_trading_days,
                latest_reset_reason, latest_reset_age_trading_days,
                calc_version, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "ecosystem",
                    "DC_ECOSYSTEM_TOTAL",
                    "UP",
                    "HL",
                    4,
                    "BOS_UP",
                    2,
                    None,
                    None,
                    "CALC_V1",
                    "RUN_SYNTH_A",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "layer",
                    "Infrastructure",
                    "UP",
                    "HH",
                    3,
                    "BOS_UP",
                    1,
                    None,
                    None,
                    "CALC_V1",
                    "RUN_SYNTH_A",
                ),
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "subindustry",
                    "AI Accelerators",
                    "DOWN",
                    "LL",
                    5,
                    "BOS_DOWN",
                    2,
                    "PULLBACK_RESET",
                    3,
                    "CALC_V1",
                    "RUN_SYNTH_B",
                ),
            ],
        )


def _destination_rows(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(
                """
                SELECT *
                FROM dc_dashboard_group_enrichment_daily
                ORDER BY market_level ASC, name ASC
                """
            ).fetchall()
        )


def _destination_count(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM dc_dashboard_group_enrichment_daily").fetchone()
    return int(row[0])


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


def test_missing_required_source_table_fails_clearly(tmp_path, capsys):
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
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required source table: dc_group_swing_signal_daily" in captured.err


def test_missing_destination_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_group_source_table_only(db_path)

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
    assert (
        "missing required destination table: dc_dashboard_group_enrichment_daily" in captured.err
    )


def test_replace_date_inserts_valid_group_rows(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    _create_taxonomy_csv(taxonomy_csv, [("Compute silicon", "AI Accelerators")])

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
            "RUN_GROUP_REPLACE",
            "--taxonomy-csv",
            str(taxonomy_csv),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert len(rows) == 3
    assert {row["market_level"] for row in rows} == {"ECOSYSTEM", "LAYER", "SUBINDUSTRY"}
    assert {row["taxonomy_key"] for row in rows} == {
        "ECOSYSTEM|DC_ECOSYSTEM_TOTAL",
        "LAYER|Infrastructure",
        "SUBINDUSTRY|Compute silicon|AI Accelerators",
    }
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.source_rows=3" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.valid_group_rows=3" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.inserted_rows=3" in output


def test_field_mapping_persists_expected_values(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    _create_taxonomy_csv(taxonomy_csv, [("Compute silicon", "AI Accelerators")])

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
            "RUN_GROUP_FIELDS",
            "--taxonomy-csv",
            str(taxonomy_csv),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    ecosystem = rows["DC_ECOSYSTEM_TOTAL"]
    layer = rows["Infrastructure"]
    subindustry = rows["AI Accelerators"]
    assert ecosystem["taxonomy_key"] == "ECOSYSTEM|DC_ECOSYSTEM_TOTAL"
    assert ecosystem["taxonomy_path"] == "DC_ECOSYSTEM_TOTAL"
    assert layer["parent_name"] == "DC_ECOSYSTEM_TOTAL"
    assert layer["taxonomy_key"] == "LAYER|Infrastructure"
    assert layer["taxonomy_path"] == "DC_ECOSYSTEM_TOTAL > Infrastructure"
    assert subindustry["parent_name"] == "Compute silicon"
    assert subindustry["layer"] == "Compute silicon"
    assert subindustry["taxonomy_key"] == "SUBINDUSTRY|Compute silicon|AI Accelerators"
    assert subindustry["taxonomy_path"] == "DC_ECOSYSTEM_TOTAL > Compute silicon > AI Accelerators"
    assert ecosystem["current_status"] == "BUY_ZONE"
    assert ecosystem["overheat_risk"] == "LOW"
    assert ecosystem["pct_above_ema20"] == 60.0
    assert ecosystem["pct_above_ma10"] == 55.0
    assert ecosystem["ema20_breadth_delta_5d"] == 3.0
    assert ecosystem["return_5d"] == 0.10
    assert ecosystem["return_10d"] == 0.15
    assert ecosystem["return_20d"] == 0.20
    assert ecosystem["return_60d"] == 0.40
    assert ecosystem["data_quality_status"] == "OK"
    assert ecosystem["calc_version"] == "DATACENTER_DASHBOARD_GROUP_ENRICHMENT_V1"
    assert ecosystem["run_id"] == "RUN_GROUP_FIELDS"
    assert ecosystem["created_at_utc"] not in (None, "")
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.taxonomy_csv=" in output


def test_taxonomy_csv_is_primary_for_subindustry_layer_mapping(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    _create_taxonomy_csv(taxonomy_csv, [("Canonical Layer", "AI Accelerators")])

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
            "RUN_GROUP_CANON",
            "--taxonomy-csv",
            str(taxonomy_csv),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    subindustry = rows["AI Accelerators"]
    assert subindustry["parent_name"] == "Canonical Layer"
    assert subindustry["layer"] == "Canonical Layer"
    assert subindustry["taxonomy_key"] == "SUBINDUSTRY|Canonical Layer|AI Accelerators"
    assert (
        subindustry["taxonomy_path"]
        == "DC_ECOSYSTEM_TOTAL > Canonical Layer > AI Accelerators"
    )
    assert (
        f"SUMMARY datacenter_dashboard_group_enrichment_write.taxonomy_csv={taxonomy_csv}"
        in output
    )
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.taxonomy_csv_status=USED" in output


def test_explicit_missing_taxonomy_csv_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    missing_csv = tmp_path / "missing.csv"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)

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
            "--taxonomy-csv",
            str(missing_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert f"taxonomy_csv not found: {missing_csv}" in captured.err


def test_default_missing_taxonomy_csv_falls_back_to_source_mapping(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_group_enrichment_write.DEFAULT_TAXONOMY_CSV",
        str(tmp_path / "missing-default-taxonomy.csv"),
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
            "RUN_GROUP_FALLBACK",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    subindustry = rows["AI Accelerators"]
    assert subindustry["layer"] == "Compute silicon"
    assert (
        "SUMMARY datacenter_dashboard_group_enrichment_write.warning="
        "TAXONOMY_CSV_MISSING_USING_SOURCE_FALLBACK"
    ) in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.taxonomy_csv_status=MISSING_FALLBACK" in output


def test_ambiguous_taxonomy_csv_uses_fallback_identity_and_warning(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    taxonomy_csv = tmp_path / "taxonomy.csv"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _create_taxonomy_csv(
        taxonomy_csv,
        [
            ("Layer A", "AI Accelerators"),
            ("Layer B", "AI Accelerators"),
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
            "RUN_GROUP_AMBIG",
            "--taxonomy-csv",
            str(taxonomy_csv),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    subindustry = rows["AI Accelerators"]
    assert subindustry["parent_name"] in (None, "")
    assert subindustry["layer"] in (None, "")
    assert subindustry["taxonomy_key"] == "SUBINDUSTRY|AI Accelerators"
    assert subindustry["taxonomy_path"] == "SUBINDUSTRY|AI Accelerators"
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.taxonomy_csv_status=AMBIGUOUS" in output
    assert (
        "SUMMARY datacenter_dashboard_group_enrichment_write.warning="
        "TAXONOMY_CSV_AMBIGUOUS_SUBINDUSTRY:AI Accelerators"
    ) in output


def test_unknown_subindustry_layer_uses_fallback_identity_and_warning(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    with sqlite3.connect(db_path) as conn:
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
                "subindustry",
                "Unknown Group",
                "NEUTRAL",
                "LOW",
                10.0,
                10.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                "OK",
                "SIG_V1",
                "RUN_SWING_X",
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
            "replace-date",
            "--run-id",
            "RUN_GROUP_UNKNOWN",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    unknown = rows["Unknown Group"]
    assert unknown["parent_name"] in (None, "")
    assert unknown["layer"] in (None, "")
    assert unknown["taxonomy_key"] == "SUBINDUSTRY|Unknown Group"
    assert unknown["taxonomy_path"] == "SUBINDUSTRY|Unknown Group"
    assert (
        "SUMMARY datacenter_dashboard_group_enrichment_write.warning=SUBINDUSTRY_LAYER_UNKNOWN"
        in output
    )


def test_optional_synthetic_join_maps_fields(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _create_synthetic_table(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    _insert_synthetic_rows(db_path)

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
            "RUN_GROUP_SYNTH",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    subindustry = rows["AI Accelerators"]
    assert subindustry["dow_trend_state"] == "DOWN"
    assert subindustry["latest_structure_label"] == "LL"
    assert subindustry["latest_structure_age_td"] == 5
    assert subindustry["latest_bos_event_type"] == "BOS_DOWN"
    assert subindustry["latest_bos_age_td"] == 2
    assert subindustry["latest_reset_reason"] == "PULLBACK_RESET"
    assert subindustry["latest_reset_age_td"] == 3
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.used_synthetic_ohlc=1" in output


def test_missing_optional_synthetic_table_warns_and_succeeds(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)

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
            "RUN_GROUP_WARN",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.used_synthetic_ohlc=0" in output
    assert (
        "SUMMARY datacenter_dashboard_group_enrichment_write.warning=SYNTHETIC_OHLC_SOURCE_MISSING"
        in output
    )


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)

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
            "RUN_GROUP_DRY",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert _destination_count(db_path) == 0
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.dry_run=1" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.inserted_rows=3" in output


def test_insert_missing_keeps_existing_row_unchanged_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name,
                current_status, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "LAYER",
                "LAYER|Infrastructure",
                "Infrastructure",
                "OLD_STATUS",
                "OLD_QUALITY",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            DELETE FROM dc_group_swing_signal_daily
            WHERE group_type = 'ecosystem'
            """
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
            "RUN_GROUP_INSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    assert rows["Infrastructure"]["current_status"] == "OLD_STATUS"
    assert rows["Infrastructure"]["data_quality_status"] == "OLD_QUALITY"
    assert rows["AI Accelerators"]["run_id"] == "RUN_GROUP_INSERT"
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.skipped_existing_rows=1" in output


def test_upsert_updates_existing_row_and_inserts_new_row(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name,
                current_status, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "LAYER",
                "LAYER|Infrastructure",
                "Infrastructure",
                "OLD_STATUS",
                "OLD_QUALITY",
                "OLD_VERSION",
                "OLD_RUN",
                "2026-05-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            DELETE FROM dc_group_swing_signal_daily
            WHERE group_type = 'ecosystem'
            """
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
            "RUN_GROUP_UPSERT",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = {row["name"]: row for row in _destination_rows(db_path)}
    assert rows["Infrastructure"]["current_status"] == "BREAKOUT_CANDIDATE"
    assert rows["Infrastructure"]["data_quality_status"] == "OK"
    assert rows["Infrastructure"]["run_id"] == "RUN_GROUP_UPSERT"
    assert rows["AI Accelerators"]["run_id"] == "RUN_GROUP_UPSERT"
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.inserted_rows=1" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.updated_rows=1" in output


def test_replace_date_deletion_scope_is_exact(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_group_enrichment_daily (
                signal_date, taxonomy_version, market_level, taxonomy_key, name,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-05-22",
                    "DC_TAXONOMY_FULL_V1",
                    "LAYER",
                    "LAYER|OldLayer",
                    "OldLayer",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-21",
                    "DC_TAXONOMY_FULL_V1",
                    "LAYER",
                    "LAYER|KeepDate",
                    "KeepDate",
                    "OK",
                    "OLD",
                    "RUN_OLD",
                    "2026-05-01T00:00:00Z",
                ),
                (
                    "2026-05-22",
                    "OTHER_TAXONOMY",
                    "LAYER",
                    "LAYER|KeepTax",
                    "KeepTax",
                    "OK",
                    "OLD",
                    "RUN_OLD",
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
            "RUN_GROUP_SCOPE",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    with sqlite3.connect(db_path) as conn:
        kept_date = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_group_enrichment_daily
            WHERE signal_date = '2026-05-21' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
        kept_tax = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_group_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'OTHER_TAXONOMY'
            """
        ).fetchone()[0]
        replaced_same_slice = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_dashboard_group_enrichment_daily
            WHERE signal_date = '2026-05-22' AND taxonomy_version = 'DC_TAXONOMY_FULL_V1'
            """
        ).fetchone()[0]
    assert kept_date == 1
    assert kept_tax == 1
    assert replaced_same_slice == 3
    assert (
        "SUMMARY datacenter_dashboard_group_enrichment_write.deleted_existing_rows=1" in output
    )


def test_limit_works_deterministically(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)

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
            "RUN_GROUP_LIMIT",
            "--limit",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    rows = _destination_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["name"] == "DC_ECOSYSTEM_TOTAL"
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.source_rows=3" in output
    assert "SUMMARY datacenter_dashboard_group_enrichment_write.valid_group_rows=1" in output


def test_audit_after_ticker_and_group_write_reports_partial(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_source_and_destination_db(db_path)
    _insert_group_source_rows(db_path)
    _insert_ticker_taxonomy_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, data_quality_status,
                calc_version, run_id, created_at_utc, is_watchlist
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "NVDA",
                "OK",
                "DATACENTER_DASHBOARD_TICKER_ENRICHMENT_V1",
                "RUN_TICKER",
                "2026-05-26T10:00:00Z",
                0,
            ),
        )

    write_exit_code = main(
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
            "RUN_GROUP_AUDIT",
        ]
    )
    assert write_exit_code == 0
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
    assert "section_readiness;group_enrichment;READY;3;rows_available" in output
    assert "section_readiness;action_summary;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;decision_trace;EMPTY;0;no_rows_for_signal_date_taxonomy_version" in output
    assert "section_readiness;overall;PARTIAL;4;some_sections_empty" in output
