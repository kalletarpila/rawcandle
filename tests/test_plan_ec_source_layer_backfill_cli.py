import csv
import sqlite3
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_backfill import main, plan_ec_source_layer_backfill
from rawcandle.ec_datacenter_taxonomy_loader import _compute_source_hash


LATEST_SOURCE_DATE = "2026-06-05"
OLDER_SOURCE_DATE = "2026-06-04"
RANGE_START = "2026-06-03"
TAXONOMY_VERSION = "DC_TAXONOMY_FULL_V1"


def _layers() -> list[str]:
    return [f"Layer {index:02d}" for index in range(1, 17)]


def _subindustries() -> list[str]:
    return [f"Subindustry {index:02d}" for index in range(1, 38)]


def _ticker(index: int) -> str:
    return f"TK{index:03d}"


def _taxonomy_rows() -> list[list[object]]:
    layers = _layers()
    subindustries = _subindustries()
    rows: list[list[object]] = []
    for index in range(236):
        ticker = _ticker(index + 1)
        subindustry = subindustries[index % len(subindustries)]
        layer = layers[index % len(layers)]
        rows.append([TAXONOMY_VERSION, ticker, layer, subindustry, "CORE", 1, 1.0, ""])
    for index in range(93):
        ticker = _ticker(index + 1)
        subindustry = subindustries[(index + 7) % len(subindustries)]
        layer = layers[(index + 5) % len(layers)]
        rows.append([TAXONOMY_VERSION, ticker, layer, subindustry, "SECONDARY", 0, 0.5, ""])
    return rows


def _write_taxonomy_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerows(_taxonomy_rows())


def _write_taxonomy_csv_for_counts(
    path: Path,
    *,
    taxonomy_version: str,
    ticker_count: int,
    secondary_count: int,
) -> None:
    layers = _layers()
    subindustries = _subindustries()
    rows: list[list[object]] = []
    for index in range(ticker_count):
        rows.append(
            [
                taxonomy_version,
                _ticker(index + 1),
                layers[index % len(layers)],
                subindustries[index % len(subindustries)],
                "CORE",
                1,
                1.0,
                "",
            ]
        )
    for index in range(secondary_count):
        rows.append(
            [
                taxonomy_version,
                _ticker(index + 1),
                layers[(index + 5) % len(layers)],
                subindustries[(index + 7) % len(subindustries)],
                "SECONDARY",
                0,
                0.5,
                "",
            ]
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "taxonomy_version",
                "ticker",
                "layer",
                "subindustry",
                "report_group_status",
                "is_primary",
                "role_weight",
                "notes",
            ]
        )
        writer.writerows(rows)


def _watchlist_tickers() -> list[str]:
    return [_ticker(index + 1) for index in range(15)] + ["CRGY"]


def _write_watchlist(path: Path) -> None:
    path.write_text("\n".join(_watchlist_tickers()) + "\n", encoding="utf-8")


def _create_source_tables(
    conn: sqlite3.Connection,
    *,
    aligned_dates: list[str],
    omit_group_index_date: str | None = None,
) -> None:
    conn.execute("CREATE TABLE eco_ecosystem (ecosystem_id INTEGER PRIMARY KEY)")
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
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_index_daily (
            index_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        )
        """
    )
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
            notes TEXT NULL
        )
        """
    )

    layers = _layers()
    subindustries = _subindustries()
    for fact_date in aligned_dates:
        ticker_rows = []
        for index in range(236):
            ticker_rows.append(
                (
                    fact_date,
                    TAXONOMY_VERSION,
                    _ticker(index + 1),
                    layers[index % len(layers)],
                    subindustries[index % len(subindustries)],
                    "DC_SWING_SIGNAL_V1",
                    "RUN_TICKER",
                    "2026-06-07T00:00:00Z",
                )
            )
        conn.executemany("INSERT INTO dc_ticker_swing_signal_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ticker_rows)

        group_signal_rows = [(fact_date, TAXONOMY_VERSION, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")]
        group_signal_rows.extend(
            (fact_date, TAXONOMY_VERSION, "layer", layer, "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")
            for layer in layers
        )
        group_signal_rows.extend(
            (fact_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")
            for subindustry in subindustries
        )
        conn.executemany("INSERT INTO dc_group_swing_signal_daily VALUES (?, ?, ?, ?, ?, ?, ?)", group_signal_rows)

        synth_rows = [
            (fact_date, TAXONOMY_VERSION, "layer", layer, "DC_SWING_OHLC_V1", "RUN_SYNTH", "2026-06-07T00:00:00Z")
            for layer in layers
        ]
        synth_rows.extend(
            (fact_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_SWING_OHLC_V1", "RUN_SYNTH", "2026-06-07T00:00:00Z")
            for subindustry in subindustries
        )
        conn.executemany("INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, ?, ?, ?, ?, ?, ?)", synth_rows)

        if fact_date != omit_group_index_date:
            index_rows = [(fact_date, TAXONOMY_VERSION, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")]
            index_rows.extend(
                (fact_date, TAXONOMY_VERSION, "layer", layer, "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")
                for layer in layers
            )
            index_rows.extend(
                (fact_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")
                for subindustry in subindustries
            )
            conn.executemany("INSERT INTO dc_group_index_daily VALUES (?, ?, ?, ?, ?, ?, ?)", index_rows)

    conn.execute(
        """
        INSERT INTO dc_pipeline_watermark VALUES
        ('TICKER_SWING_BASE', ?, 'USA', 'DC_SWING_SIGNAL_V1', NULL, '2026-01-01', ?, 236, 'OK', NULL, NULL, NULL)
        """,
        (TAXONOMY_VERSION, max(aligned_dates)),
    )


def _create_ec_schema(
    conn: sqlite3.Connection,
    *,
    taxonomy_csv_path: Path,
    include_ec_schema: bool = True,
    loaded_dates: dict[str, list[str]] | None = None,
    partial_mismatch_date: str | None = None,
    missing_group_l1_name: str | None = None,
    loaded_watchlist_tickers: list[str] | None = None,
) -> None:
    if not include_ec_schema:
        return

    loaded_dates = loaded_dates or {}

    conn.execute("CREATE TABLE ec_ecosystem (ecosystem_id INTEGER PRIMARY KEY, ecosystem_code TEXT NOT NULL)")
    conn.execute(
        """
        CREATE TABLE ec_taxonomy_version (
            taxonomy_version_id INTEGER PRIMARY KEY,
            ecosystem_id INTEGER NOT NULL,
            taxonomy_version_code TEXT NOT NULL,
            source_reference TEXT NULL,
            source_hash TEXT NULL,
            status TEXT NULL,
            is_active INTEGER NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ec_entity (
            entity_id INTEGER PRIMARY KEY,
            ecosystem_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_code TEXT NOT NULL,
            entity_name TEXT NULL,
            ticker TEXT NULL,
            status TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ec_entity_alias (
            entity_alias_id INTEGER PRIMARY KEY,
            ecosystem_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            alias_type TEXT NOT NULL,
            alias_value TEXT NOT NULL,
            source_system TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE ec_membership (
            membership_id INTEGER PRIMARY KEY,
            taxonomy_version_id INTEGER NOT NULL,
            parent_entity_id INTEGER NOT NULL,
            child_entity_id INTEGER NOT NULL,
            membership_type TEXT NULL,
            is_primary INTEGER NULL
        )
        """
    )
    conn.execute("CREATE TABLE ec_watchlist (watchlist_id INTEGER PRIMARY KEY, ecosystem_id INTEGER NOT NULL, watchlist_code TEXT NOT NULL)")
    conn.execute("CREATE TABLE ec_watchlist_member (watchlist_member_id INTEGER PRIMARY KEY, watchlist_id INTEGER NOT NULL, entity_id INTEGER NOT NULL)")
    conn.execute("CREATE TABLE ec_signal_run (signal_run_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL)")
    conn.execute("CREATE TABLE ec_pipeline_watermark (ecosystem_id INTEGER NOT NULL, pipeline_name TEXT NOT NULL, source_table TEXT NOT NULL)")
    conn.execute("CREATE TABLE ec_ticker_signal_daily (signal_date TEXT NOT NULL, ticker TEXT NOT NULL)")
    conn.execute("CREATE TABLE ec_group_signal_daily (signal_date TEXT NOT NULL, entity_id INTEGER NOT NULL)")
    conn.execute("CREATE TABLE ec_group_synthetic_ohlc_daily (signal_date TEXT NOT NULL, entity_id INTEGER NOT NULL)")
    conn.execute("CREATE TABLE ec_group_index_daily (signal_date TEXT NOT NULL, entity_id INTEGER NOT NULL)")

    conn.execute("INSERT INTO ec_ecosystem VALUES (1, 'DATACENTER')")
    conn.execute(
        "INSERT INTO ec_taxonomy_version VALUES (?, 1, ?, ?, ?, 'ACTIVE', 1)",
        (
            1,
            TAXONOMY_VERSION,
            str(taxonomy_csv_path.resolve()),
            _compute_source_hash(taxonomy_csv_path),
        ),
    )

    entity_id = 1
    conn.execute("INSERT INTO ec_entity VALUES (?, 1, 'ECOSYSTEM', 'DATACENTER', 'Datacenter', NULL, 'ACTIVE')", (entity_id,))
    ecosystem_entity_id = entity_id
    entity_id += 1

    layer_entity_ids: dict[str, int] = {}
    for layer in _layers():
        if layer == missing_group_l1_name:
            continue
        conn.execute("INSERT INTO ec_entity VALUES (?, 1, 'GROUP_L1', ?, ?, NULL, 'ACTIVE')", (entity_id, layer.upper().replace(' ', '_'), layer))
        layer_entity_ids[layer] = entity_id
        conn.execute("INSERT INTO ec_membership VALUES (NULL, 1, ?, ?, 'CONTAINS', 1)", (ecosystem_entity_id, entity_id))
        entity_id += 1

    subindustry_entity_ids: dict[str, int] = {}
    for index, subindustry in enumerate(_subindustries()):
        conn.execute(
            "INSERT INTO ec_entity VALUES (?, 1, 'GROUP_L2', ?, ?, NULL, 'ACTIVE')",
            (entity_id, subindustry.upper().replace(' ', '_'), subindustry),
        )
        subindustry_entity_ids[subindustry] = entity_id
        parent_layer = _layers()[index % len(_layers())]
        if parent_layer in layer_entity_ids:
            conn.execute("INSERT INTO ec_membership VALUES (NULL, 1, ?, ?, 'CONTAINS', 1)", (layer_entity_ids[parent_layer], entity_id))
        entity_id += 1

    for index in range(236):
        ticker = _ticker(index + 1)
        subindustry = _subindustries()[index % len(_subindustries())]
        conn.execute(
            "INSERT INTO ec_entity VALUES (?, 1, 'TICKER', ?, ?, ?, 'ACTIVE')",
            (entity_id, ticker, ticker, ticker),
        )
        conn.execute("INSERT INTO ec_membership VALUES (NULL, 1, ?, ?, 'CONTAINS', 1)", (subindustry_entity_ids[subindustry], entity_id))
        if index < 93:
            secondary_subindustry = _subindustries()[(index + 7) % len(_subindustries())]
            conn.execute("INSERT INTO ec_membership VALUES (NULL, 1, ?, ?, 'CONTAINS', 0)", (subindustry_entity_ids[secondary_subindustry], entity_id))
        entity_id += 1

    crgy_entity_id = entity_id
    conn.execute("INSERT INTO ec_entity VALUES (?, 1, 'TICKER', 'CRGY', 'CRGY', 'CRGY', 'ACTIVE')", (crgy_entity_id,))
    conn.execute(
        "INSERT INTO ec_entity_alias VALUES (1, 1, ?, 'DC_GROUP_NAME', 'DC_ECOSYSTEM_TOTAL', 'dc_group_facts')",
        (ecosystem_entity_id,),
    )
    conn.execute("INSERT INTO ec_watchlist VALUES (1, 1, 'DATACENTER_WATCH')")

    for member_index, ticker in enumerate(loaded_watchlist_tickers or _watchlist_tickers(), start=1):
        entity_row = conn.execute(
            "SELECT entity_id FROM ec_entity WHERE entity_code = ? AND entity_type = 'TICKER'",
            (ticker,),
        ).fetchone()
        assert entity_row is not None
        conn.execute("INSERT INTO ec_watchlist_member VALUES (?, 1, ?)", (member_index, int(entity_row[0])))

    for table_name, dates in loaded_dates.items():
        for fact_date in dates:
            if table_name == "ec_ticker_signal_daily":
                row_total = 236
                if fact_date == partial_mismatch_date:
                    row_total = 10
                conn.executemany(
                    f"INSERT INTO {table_name} VALUES (?, ?)",
                    [(fact_date, _ticker(index + 1)) for index in range(row_total)],
                )
            else:
                row_total = 54
                if table_name == "ec_group_signal_daily" or table_name == "ec_group_index_daily":
                    row_total = 54
                elif table_name == "ec_group_synthetic_ohlc_daily":
                    row_total = 53
                if fact_date == partial_mismatch_date:
                    row_total = 1
                conn.executemany(
                    f"INSERT INTO {table_name} VALUES (?, ?)",
                    [(fact_date, 1) for _ in range(row_total)],
                )


def _create_fixture(
    tmp_path: Path,
    *,
    include_ec_schema: bool = True,
    loaded_dates: dict[str, list[str]] | None = None,
    partial_mismatch_date: str | None = None,
    omit_group_index_date: str | None = None,
    missing_group_l1_name: str | None = None,
    loaded_watchlist_tickers: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _write_taxonomy_csv(taxonomy_path)
    _write_watchlist(watchlist_path)
    conn = sqlite3.connect(db_path)
    try:
        _create_source_tables(conn, aligned_dates=[OLDER_SOURCE_DATE, LATEST_SOURCE_DATE], omit_group_index_date=omit_group_index_date)
        _create_ec_schema(
            conn,
            taxonomy_csv_path=taxonomy_path,
            include_ec_schema=include_ec_schema,
            loaded_dates=loaded_dates,
            partial_mismatch_date=partial_mismatch_date,
            missing_group_l1_name=missing_group_l1_name,
            loaded_watchlist_tickers=loaded_watchlist_tickers,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, taxonomy_path, watchlist_path


def _install_proposed_taxonomy_rebuild_fixture(
    db_path: Path,
    taxonomy_path: Path,
    *,
    taxonomy_version: str,
    deployment_id: int,
    ticker_count: int,
    secondary_count: int,
    deployment_status: str = "VALIDATION_REQUIRED",
    activation_status: str = "NOT_ACTIVE",
) -> Path:
    proposed_path = taxonomy_path.parent / f"{taxonomy_version.lower()}.csv"
    _write_taxonomy_csv_for_counts(
        proposed_path,
        taxonomy_version=taxonomy_version,
        ticker_count=ticker_count,
        secondary_count=secondary_count,
    )
    source_hash = _compute_source_hash(proposed_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (?, 1, ?, ?, ?, 'INACTIVE', 0)",
            (2, taxonomy_version, str(proposed_path), source_hash),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ec_taxonomy_change_deployment (
                taxonomy_change_id INTEGER PRIMARY KEY,
                ecosystem_code TEXT NOT NULL,
                previous_taxonomy_version TEXT NOT NULL,
                proposed_taxonomy_version TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                change_summary TEXT NOT NULL,
                added_ticker_count INTEGER NOT NULL,
                removed_ticker_count INTEGER NOT NULL,
                membership_change_count INTEGER NOT NULL,
                group_change_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                rebuild_required INTEGER NOT NULL,
                rebuild_start_date TEXT NOT NULL,
                activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVE',
                dc_rebuild_status TEXT NOT NULL DEFAULT 'OK',
                ec_rebuild_status TEXT NOT NULL DEFAULT 'FAILED'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                taxonomy_change_id, ecosystem_code, previous_taxonomy_version,
                proposed_taxonomy_version, source_reference, source_sha256,
                change_summary, added_ticker_count, removed_ticker_count,
                membership_change_count, group_change_count, status,
                rebuild_required, rebuild_start_date, activation_status
            ) VALUES (?, 'DATACENTER', ?, ?, ?, ?, '{}', 0, 0, 0, 0, ?, 1,
                      '2025-08-01', ?)
            """,
            (deployment_id, TAXONOMY_VERSION, taxonomy_version, str(proposed_path), source_hash, deployment_status, activation_status),
        )
        conn.execute(
            """
            INSERT INTO ec_membership (
                taxonomy_version_id, parent_entity_id, child_entity_id, membership_type, is_primary
            )
            SELECT 2, parent_entity_id, child_entity_id, membership_type, is_primary
            FROM ec_membership
            WHERE taxonomy_version_id = 1
              AND child_entity_id IN (
                  SELECT entity_id FROM ec_entity WHERE entity_type = 'GROUP_L2'
              )
            """
        )
        next_entity_id = int(conn.execute("SELECT COALESCE(MAX(entity_id), 0) + 1 FROM ec_entity").fetchone()[0])
        subindustry_ids = {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT entity_name, entity_id FROM ec_entity WHERE entity_type = 'GROUP_L2'")
        }
        subindustries = _subindustries()
        for index in range(ticker_count):
            entity_id = next_entity_id + index
            ticker = _ticker(index + 1)
            conn.execute(
                "INSERT INTO ec_entity VALUES (?, 1, 'TICKER', ?, ?, ?, 'ACTIVE')",
                (entity_id, ticker, ticker, ticker),
            )
            primary_subindustry = subindustries[index % len(subindustries)]
            conn.execute(
                "INSERT INTO ec_membership VALUES (NULL, 2, ?, ?, 'CONTAINS', 1)",
                (subindustry_ids[primary_subindustry], entity_id),
            )
            if index < secondary_count:
                secondary_subindustry = subindustries[(index + 7) % len(subindustries)]
                conn.execute(
                    "INSERT INTO ec_membership VALUES (NULL, 2, ?, ?, 'CONTAINS', 0)",
                    (subindustry_ids[secondary_subindustry], entity_id),
                )
        layers = _layers()
        for fact_date in [LATEST_SOURCE_DATE]:
            conn.executemany(
                "INSERT INTO dc_ticker_swing_signal_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        fact_date,
                        taxonomy_version,
                        _ticker(index + 1),
                        layers[index % len(layers)],
                        subindustries[index % len(subindustries)],
                        "DC_SWING_SIGNAL_V1",
                        "RUN_TICKER_V2",
                        "2026-06-07T00:00:00Z",
                    )
                    for index in range(ticker_count)
                ],
            )
            group_rows = [(fact_date, taxonomy_version, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_SWING_SIGNAL_V1", "RUN_GROUP_V2", "2026-06-07T00:00:00Z")]
            group_rows.extend((fact_date, taxonomy_version, "layer", layer, "DC_SWING_SIGNAL_V1", "RUN_GROUP_V2", "2026-06-07T00:00:00Z") for layer in layers)
            group_rows.extend((fact_date, taxonomy_version, "subindustry", subindustry, "DC_SWING_SIGNAL_V1", "RUN_GROUP_V2", "2026-06-07T00:00:00Z") for subindustry in subindustries)
            conn.executemany("INSERT INTO dc_group_swing_signal_daily VALUES (?, ?, ?, ?, ?, ?, ?)", group_rows)
            synth_rows = [(fact_date, taxonomy_version, "layer", layer, "DC_SWING_OHLC_V1", "RUN_SYNTH_V2", "2026-06-07T00:00:00Z") for layer in layers]
            synth_rows.extend((fact_date, taxonomy_version, "subindustry", subindustry, "DC_SWING_OHLC_V1", "RUN_SYNTH_V2", "2026-06-07T00:00:00Z") for subindustry in subindustries)
            conn.executemany("INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, ?, ?, ?, ?, ?, ?)", synth_rows)
            index_rows = [(fact_date, taxonomy_version, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_INDEX_CALC_V1", "RUN_INDEX_V2", "2026-06-07T00:00:00Z")]
            index_rows.extend((fact_date, taxonomy_version, "layer", layer, "DC_INDEX_CALC_V1", "RUN_INDEX_V2", "2026-06-07T00:00:00Z") for layer in layers)
            index_rows.extend((fact_date, taxonomy_version, "subindustry", subindustry, "DC_INDEX_CALC_V1", "RUN_INDEX_V2", "2026-06-07T00:00:00Z") for subindustry in subindustries)
            conn.executemany("INSERT INTO dc_group_index_daily VALUES (?, ?, ?, ?, ?, ?, ?)", index_rows)
        conn.commit()
    finally:
        conn.close()
    return proposed_path


def _base_args(db_path: Path, taxonomy_path: Path, watchlist_path: Path) -> list[str]:
    return [
        "--db",
        str(db_path),
        "--ecosystem",
        "DATACENTER",
        "--taxonomy-version",
        TAXONOMY_VERSION,
        "--date-from",
        RANGE_START,
        "--date-to",
        LATEST_SOURCE_DATE,
        "--taxonomy-csv",
        str(taxonomy_path),
        "--watchlist",
        str(watchlist_path),
        "--format",
        "text",
    ]


def test_blocks_when_ec_schema_missing(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path, include_ec_schema=False)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_EC_SCHEMA_MISSING"


def test_invalid_date_range_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from="2026-06-06",
        date_to="2026-06-05",
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_INVALID_DATE_RANGE"


def test_normal_backfill_blocks_ranges_over_60_days(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from="2026-01-01",
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_INVALID_DATE_RANGE"
    assert summary["rebuild_mode"] == "ORDINARY_BACKFILL"


def test_taxonomy_rebuild_plan_accepts_full_range_with_deployment(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = tmp_path / "taxonomy_v2.csv"
    text = taxonomy_path.read_text(encoding="utf-8").replace(TAXONOMY_VERSION, "DC_TAXONOMY_FULL_V2")
    v2_path.write_text(text, encoding="utf-8")
    source_hash = _compute_source_hash(v2_path)
    conn = sqlite3.connect(db_path)
    try:
        for table_name in [
            "dc_ticker_swing_signal_daily",
            "dc_group_swing_signal_daily",
            "dc_group_synthetic_ohlc_daily",
            "dc_group_index_daily",
        ]:
            conn.execute(f"UPDATE {table_name} SET taxonomy_version = 'DC_TAXONOMY_FULL_V2'")
        conn.execute(
            "INSERT INTO ec_taxonomy_version VALUES (?, 1, ?, ?, ?, 'INACTIVE', 0)",
            (2, "DC_TAXONOMY_FULL_V2", str(v2_path), source_hash),
        )
        conn.execute(
            """
            CREATE TABLE ec_taxonomy_change_deployment (
                taxonomy_change_id INTEGER PRIMARY KEY,
                ecosystem_code TEXT NOT NULL,
                previous_taxonomy_version TEXT NOT NULL,
                proposed_taxonomy_version TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                change_summary TEXT NOT NULL,
                added_ticker_count INTEGER NOT NULL,
                removed_ticker_count INTEGER NOT NULL,
                membership_change_count INTEGER NOT NULL,
                group_change_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                rebuild_required INTEGER NOT NULL,
                rebuild_start_date TEXT NOT NULL,
                activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVE'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ec_taxonomy_change_deployment (
                taxonomy_change_id, ecosystem_code, previous_taxonomy_version,
                proposed_taxonomy_version, source_reference, source_sha256,
                change_summary, added_ticker_count, removed_ticker_count,
                membership_change_count, group_change_count, status,
                rebuild_required, rebuild_start_date
            ) VALUES (7, 'DATACENTER', ?, 'DC_TAXONOMY_FULL_V2', ?, ?,
                      '{}', 0, 0, 0, 0, 'LOADED_NOT_ACTIVE', 1, '2025-08-01')
            """,
            (TAXONOMY_VERSION, str(v2_path), source_hash),
        )
        conn.execute(
            """
            INSERT INTO ec_membership (
                taxonomy_version_id, parent_entity_id, child_entity_id, membership_type, is_primary
            )
            SELECT 2, parent_entity_id, child_entity_id, membership_type, is_primary
            FROM ec_membership
            WHERE taxonomy_version_id = 1
            """
        )
        conn.commit()
    finally:
        conn.close()

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from="2026-01-01",
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "READY_TAXONOMY_REBUILD_PLAN"
    assert summary["rebuild_mode"] == "TAXONOMY_FULL_REBUILD"
    assert summary["deployment_id"] == 7


def test_taxonomy_rebuild_uses_proposed_v2_counts_not_active_v1_counts(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "READY_TAXONOMY_REBUILD_PLAN"
    compatibility = summary["compatibility_summary"]
    assert compatibility["taxonomy_validation_mode"] == "PROPOSED_TAXONOMY_REBUILD"
    assert compatibility["taxonomy_expected_source"] == "LOADED_PROPOSED_TAXONOMY"
    assert compatibility["taxonomy_expected_version"] == "DC_TAXONOMY_FULL_V2"
    assert compatibility["taxonomy_expected_row_count"] == 350
    assert compatibility["taxonomy_actual_row_count"] == 350
    assert compatibility["taxonomy_expected_ticker_count"] == 257
    assert compatibility["taxonomy_actual_ticker_count"] == 257
    assert compatibility["taxonomy_expected_layer_count"] == 16
    assert compatibility["taxonomy_actual_layer_count"] == 16
    assert compatibility["taxonomy_expected_subindustry_count"] == 37
    assert compatibility["taxonomy_actual_subindustry_count"] == 37
    assert compatibility["taxonomy_expected_primary_membership_count"] == 257
    assert compatibility["taxonomy_expected_secondary_membership_count"] == 93
    assert compatibility["taxonomy_source_match"] is True
    assert compatibility["taxonomy_source_error"] == "NONE"


def test_ordinary_backfill_still_blocks_v2_counts_against_active_v1_policy(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"
    compatibility = summary["compatibility_summary"]
    assert compatibility["taxonomy_validation_mode"] == "ACTIVE_TAXONOMY"
    assert compatibility["taxonomy_expected_row_count"] == 329
    assert compatibility["taxonomy_actual_row_count"] == 350
    assert compatibility["taxonomy_expected_ticker_count"] == 236
    assert compatibility["taxonomy_actual_ticker_count"] == 257


def test_taxonomy_rebuild_future_counts_are_derived_dynamically(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v3_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V3",
        deployment_id=8,
        ticker_count=240,
        secondary_count=10,
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V3",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v3_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=8,
    )

    assert summary["status"] == "READY_TAXONOMY_REBUILD_PLAN"
    compatibility = summary["compatibility_summary"]
    assert compatibility["taxonomy_expected_row_count"] == 250
    assert compatibility["taxonomy_actual_row_count"] == 250
    assert compatibility["taxonomy_expected_ticker_count"] == 240
    assert compatibility["taxonomy_actual_ticker_count"] == 240
    assert compatibility["taxonomy_expected_secondary_membership_count"] == 10


def test_taxonomy_rebuild_source_hash_mismatch_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )
    rows = list(csv.reader(v2_path.open("r", encoding="utf-8", newline="")))
    rows[1][-1] = "changed hash without changing counts"
    with v2_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"
    assert summary["compatibility_summary"]["taxonomy_source_match"] is False
    assert "source taxonomy hash differs" in summary["compatibility_summary"]["taxonomy_source_error"]


def test_taxonomy_rebuild_loaded_metadata_count_mismatch_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            DELETE FROM ec_membership
            WHERE taxonomy_version_id = 2
              AND child_entity_id IN (
                  SELECT entity_id FROM ec_entity WHERE entity_type = 'TICKER'
              )
              AND is_primary = 0
              AND rowid = (
                  SELECT MIN(rowid)
                  FROM ec_membership
                  WHERE taxonomy_version_id = 2 AND is_primary = 0
              )
            """
        )
        conn.commit()
    finally:
        conn.close()

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"
    assert "secondary_membership_count" in summary["compatibility_summary"]["taxonomy_source_error"]


def test_taxonomy_rebuild_deployment_version_mismatch_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE ec_taxonomy_change_deployment SET proposed_taxonomy_version = 'DC_TAXONOMY_FULL_OTHER' WHERE taxonomy_change_id = 7"
        )
        conn.commit()
    finally:
        conn.close()

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_REBUILD_DEPLOYMENT"
    assert "deployment proposed taxonomy does not match" in summary["error"]


def test_taxonomy_rebuild_missing_deployment_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=99,
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_REBUILD_DEPLOYMENT"
    assert "taxonomy deployment row not found" in summary["error"]


def test_taxonomy_rebuild_retry_from_failed_deployment_is_accepted(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
        deployment_status="VALIDATION_REQUIRED",
        activation_status="NOT_ACTIVE",
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "READY_TAXONOMY_REBUILD_PLAN"
    assert summary["deployment_summary"]["deployment"]["ec_rebuild_status"] == "FAILED"


def test_taxonomy_rebuild_active_deployment_is_rejected(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    v2_path = _install_proposed_taxonomy_rebuild_fixture(
        db_path,
        taxonomy_path,
        taxonomy_version="DC_TAXONOMY_FULL_V2",
        deployment_id=7,
        ticker_count=257,
        secondary_count=93,
        deployment_status="READY_TO_ACTIVATE",
        activation_status="ACTIVE",
    )

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code="DC_TAXONOMY_FULL_V2",
        date_from=LATEST_SOURCE_DATE,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(v2_path),
        watchlist_path=str(watchlist_path),
        taxonomy_rebuild=True,
        deployment_id=7,
    )

    assert summary["status"] == "BLOCKED_TAXONOMY_REBUILD_DEPLOYMENT"
    assert "deployment is already active" in summary["error"]


def test_aligned_missing_dates_produce_ready_plan(tmp_path: Path, capsys) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    exit_code = main(_base_args(db_path, taxonomy_path, watchlist_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Plan Status" in output
    assert "status=READY_BACKFILL_PLAN" in output
    assert "aligned_dates=['2026-06-04', '2026-06-05']" in output
    assert "missing_source_dates=['2026-06-03']" in output
    assert "classification=MISSING_IN_EC" in output


def test_already_loaded_full_range_produces_skip(tmp_path: Path) -> None:
    loaded_dates = {
        "ec_ticker_signal_daily": [OLDER_SOURCE_DATE, LATEST_SOURCE_DATE],
        "ec_group_signal_daily": [OLDER_SOURCE_DATE, LATEST_SOURCE_DATE],
        "ec_group_synthetic_ohlc_daily": [OLDER_SOURCE_DATE, LATEST_SOURCE_DATE],
        "ec_group_index_daily": [OLDER_SOURCE_DATE, LATEST_SOURCE_DATE],
    }
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path, loaded_dates=loaded_dates)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "SKIP_ALL_DATES_ALREADY_LOADED"


def test_partial_date_blocks_without_replace(tmp_path: Path) -> None:
    loaded_dates = {
        "ec_ticker_signal_daily": [OLDER_SOURCE_DATE],
        "ec_group_signal_daily": [OLDER_SOURCE_DATE],
        "ec_group_synthetic_ohlc_daily": [OLDER_SOURCE_DATE],
        "ec_group_index_daily": [OLDER_SOURCE_DATE],
    }
    db_path, taxonomy_path, watchlist_path = _create_fixture(
        tmp_path,
        loaded_dates=loaded_dates,
        partial_mismatch_date=OLDER_SOURCE_DATE,
    )
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_PARTIAL_EXISTING_DATES_WITHOUT_REPLACE"


def test_partial_date_ready_with_replace(tmp_path: Path) -> None:
    loaded_dates = {
        "ec_ticker_signal_daily": [OLDER_SOURCE_DATE],
        "ec_group_signal_daily": [OLDER_SOURCE_DATE],
        "ec_group_synthetic_ohlc_daily": [OLDER_SOURCE_DATE],
        "ec_group_index_daily": [OLDER_SOURCE_DATE],
    }
    db_path, taxonomy_path, watchlist_path = _create_fixture(
        tmp_path,
        loaded_dates=loaded_dates,
        partial_mismatch_date=OLDER_SOURCE_DATE,
    )
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
        allow_replace_existing=True,
    )
    assert summary["status"] == "READY_BACKFILL_PLAN"
    assert {"date": "2026-06-04", "action": "REPLACE_PARTIAL"} in summary["loaded_state"]["candidate_dates"]


def test_watchlist_membership_match_reports_match(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "READY_BACKFILL_PLAN"
    compatibility = summary["compatibility_summary"]
    assert compatibility["watchlist_membership_status"] == "MATCH"
    assert compatibility["watchlist_sync_required"] is False
    assert compatibility["watchlist_missing_in_loaded_count"] == 0
    assert compatibility["watchlist_loaded_only_count"] == 0


def test_watchlist_membership_drift_is_non_blocking_and_structured(tmp_path: Path) -> None:
    loaded_watchlist = _watchlist_tickers()[:14] + ["TK016"]
    db_path, taxonomy_path, watchlist_path = _create_fixture(
        tmp_path,
        loaded_watchlist_tickers=loaded_watchlist,
    )
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    assert summary["status"] == "READY_BACKFILL_PLAN"
    compatibility = summary["compatibility_summary"]
    assert compatibility["status"] == "OK"
    assert compatibility["watchlist_membership_status"] == "DRIFT_DETECTED"
    assert compatibility["watchlist_sync_required"] is True
    assert compatibility["watchlist_source_member_count"] == 16
    assert compatibility["watchlist_loaded_member_count"] == 15
    assert compatibility["watchlist_missing_in_loaded_count"] == 2
    assert compatibility["watchlist_loaded_only_count"] == 1
    assert compatibility["watchlist_missing_in_loaded"] == ["CRGY", "TK015"]
    assert compatibility["watchlist_loaded_only"] == ["TK016"]


def test_missing_source_date_reported_and_not_aligned(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path, omit_group_index_date=OLDER_SOURCE_DATE)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "READY_BACKFILL_PLAN"
    assert "2026-06-04" in summary["source_date_availability"]["missing_source_dates"]
    assert summary["source_date_availability"]["aligned_dates"] == ["2026-06-05"]


def test_taxonomy_hash_mismatch_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    with taxonomy_path.open("a", encoding="utf-8") as handle:
        handle.write("# changed bytes\n")

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"


def test_watchlist_only_crgy_does_not_block(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "READY_BACKFILL_PLAN"
    assert summary["compatibility_summary"]["watchlist_missing_in_loaded"] == []
    assert summary["compatibility_summary"]["watchlist_loaded_only"] == []


def test_missing_group_mapping_blocks(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path, missing_group_l1_name="Layer 03")
    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_UNCLEAR_MAPPING"
    assert "Layer 03" in summary["mapping_summary"]["missing_group_l1_entities"]


def test_planner_does_not_write_db_state(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_fixture(tmp_path)
    before_conn = sqlite3.connect(db_path)
    try:
        before_counts = {
            "ec_ticker_signal_daily": before_conn.execute("SELECT COUNT(*) FROM ec_ticker_signal_daily").fetchone()[0],
            "ec_group_signal_daily": before_conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0],
        }
    finally:
        before_conn.close()

    summary = plan_ec_source_layer_backfill(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        date_from=RANGE_START,
        date_to=LATEST_SOURCE_DATE,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )

    after_conn = sqlite3.connect(db_path)
    try:
        after_counts = {
            "ec_ticker_signal_daily": after_conn.execute("SELECT COUNT(*) FROM ec_ticker_signal_daily").fetchone()[0],
            "ec_group_signal_daily": after_conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0],
        }
    finally:
        after_conn.close()

    assert summary["status"] == "READY_BACKFILL_PLAN"
    assert before_counts == after_counts
