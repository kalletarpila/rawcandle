import csv
import sqlite3
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_refresh import main, plan_ec_source_layer_refresh
from rawcandle.ec_datacenter_taxonomy_loader import _compute_source_hash


LATEST_SOURCE_DATE = "2026-06-06"
LOADED_DATE = "2026-06-05"
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


def _watchlist_tickers() -> list[str]:
    return [_ticker(index + 1) for index in range(15)] + ["CRGY"]


def _write_watchlist(path: Path) -> None:
    path.write_text("\n".join(_watchlist_tickers()) + "\n", encoding="utf-8")


def _create_source_tables(conn: sqlite3.Connection, *, source_date: str, mismatched_synth_date: str | None = None) -> None:
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
    ticker_rows = []
    for index in range(236):
        ticker_rows.append(
            (
                source_date,
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

    group_signal_rows = [(source_date, TAXONOMY_VERSION, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")]
    group_signal_rows.extend(
        (source_date, TAXONOMY_VERSION, "layer", layer, "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")
        for layer in layers
    )
    group_signal_rows.extend(
        (source_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_SWING_SIGNAL_V1", "RUN_GROUP", "2026-06-07T00:00:00Z")
        for subindustry in subindustries
    )
    conn.executemany("INSERT INTO dc_group_swing_signal_daily VALUES (?, ?, ?, ?, ?, ?, ?)", group_signal_rows)

    synth_date = mismatched_synth_date or source_date
    synth_rows = [
        (synth_date, TAXONOMY_VERSION, "layer", layer, "DC_SWING_OHLC_V1", "RUN_SYNTH", "2026-06-07T00:00:00Z")
        for layer in layers
    ]
    synth_rows.extend(
        (synth_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_SWING_OHLC_V1", "RUN_SYNTH", "2026-06-07T00:00:00Z")
        for subindustry in subindustries
    )
    conn.executemany("INSERT INTO dc_group_synthetic_ohlc_daily VALUES (?, ?, ?, ?, ?, ?, ?)", synth_rows)

    index_rows = [(source_date, TAXONOMY_VERSION, "ecosystem", "DC_ECOSYSTEM_TOTAL", "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")]
    index_rows.extend(
        (source_date, TAXONOMY_VERSION, "layer", layer, "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")
        for layer in layers
    )
    index_rows.extend(
        (source_date, TAXONOMY_VERSION, "subindustry", subindustry, "DC_INDEX_CALC_V1", "RUN_INDEX", "2026-06-07T00:00:00Z")
        for subindustry in subindustries
    )
    conn.executemany("INSERT INTO dc_group_index_daily VALUES (?, ?, ?, ?, ?, ?, ?)", index_rows)

    conn.execute(
        """
        INSERT INTO dc_pipeline_watermark VALUES
        ('TICKER_SWING_BASE', ?, 'USA', 'DC_SWING_SIGNAL_V1', NULL, '2026-01-01', ?, 236, 'OK', NULL, NULL, NULL)
        """,
        (TAXONOMY_VERSION, source_date),
    )


def _create_ec_schema(
    conn: sqlite3.Connection,
    *,
    taxonomy_csv_path: Path,
    loaded_fact_date: str = LOADED_DATE,
    include_ec_schema: bool = True,
    partial_selected_tables: set[str] | None = None,
    include_selected_in_all: bool = False,
    include_selected_replace_date: str = LATEST_SOURCE_DATE,
    missing_group_l1_name: str | None = None,
) -> None:
    if not include_ec_schema:
        return

    partial_selected_tables = partial_selected_tables or set()

    conn.execute(
        """
        CREATE TABLE ec_ecosystem (
            ecosystem_id INTEGER PRIMARY KEY,
            ecosystem_code TEXT NOT NULL
        )
        """
    )
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
        """
        INSERT INTO ec_taxonomy_version VALUES (?, 1, ?, ?, ?, 'ACTIVE', 1)
        """,
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
    entity_id += 1

    conn.execute(
        "INSERT INTO ec_entity_alias VALUES (1, 1, ?, 'DC_GROUP_NAME', 'DC_ECOSYSTEM_TOTAL', 'dc_group_facts')",
        (ecosystem_entity_id,),
    )
    conn.execute("INSERT INTO ec_watchlist VALUES (1, 1, 'DATACENTER_WATCH')")
    watchlist_members = _watchlist_tickers()
    for member_index, ticker in enumerate(watchlist_members, start=1):
        entity_code = ticker
        entity_row = conn.execute(
            "SELECT entity_id FROM ec_entity WHERE entity_code = ? AND entity_type = 'TICKER'",
            (entity_code,),
        ).fetchone()
        assert entity_row is not None
        conn.execute("INSERT INTO ec_watchlist_member VALUES (?, 1, ?)", (member_index, int(entity_row[0])))

    for table_name in (
        "ec_ticker_signal_daily",
        "ec_group_signal_daily",
        "ec_group_synthetic_ohlc_daily",
        "ec_group_index_daily",
    ):
        if table_name == "ec_ticker_signal_daily":
            conn.execute(f"INSERT INTO {table_name} VALUES (?, 'TK001')", (loaded_fact_date,))
        else:
            conn.execute(f"INSERT INTO {table_name} VALUES (?, 1)", (loaded_fact_date,))

    if include_selected_in_all:
        for table_name in (
            "ec_ticker_signal_daily",
            "ec_group_signal_daily",
            "ec_group_synthetic_ohlc_daily",
            "ec_group_index_daily",
        ):
            if table_name == "ec_ticker_signal_daily":
                conn.execute(f"INSERT INTO {table_name} VALUES (?, 'TK001')", (include_selected_replace_date,))
            else:
                conn.execute(f"INSERT INTO {table_name} VALUES (?, 1)", (include_selected_replace_date,))
    else:
        for table_name in partial_selected_tables:
            if table_name == "ec_ticker_signal_daily":
                conn.execute(f"INSERT INTO {table_name} VALUES (?, 'TK001')", (include_selected_replace_date,))
            else:
                conn.execute(f"INSERT INTO {table_name} VALUES (?, 1)", (include_selected_replace_date,))


def _create_refresh_fixture(
    tmp_path: Path,
    *,
    include_ec_schema: bool = True,
    include_selected_in_all: bool = False,
    partial_selected_tables: set[str] | None = None,
    mismatched_synth_date: str | None = None,
    missing_group_l1_name: str | None = None,
) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "analysis.sqlite"
    taxonomy_path = tmp_path / "taxonomy.csv"
    watchlist_path = tmp_path / "watchlist.txt"
    _write_taxonomy_csv(taxonomy_path)
    _write_watchlist(watchlist_path)
    conn = sqlite3.connect(db_path)
    try:
        _create_source_tables(conn, source_date=LATEST_SOURCE_DATE, mismatched_synth_date=mismatched_synth_date)
        _create_ec_schema(
            conn,
            taxonomy_csv_path=taxonomy_path,
            include_ec_schema=include_ec_schema,
            include_selected_in_all=include_selected_in_all,
            partial_selected_tables=partial_selected_tables,
            missing_group_l1_name=missing_group_l1_name,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, taxonomy_path, watchlist_path


def _base_args(db_path: Path, taxonomy_path: Path, watchlist_path: Path) -> list[str]:
    return [
        "--db",
        str(db_path),
        "--ecosystem",
        "DATACENTER",
        "--taxonomy-version",
        TAXONOMY_VERSION,
        "--taxonomy-csv",
        str(taxonomy_path),
        "--watchlist",
        str(watchlist_path),
        "--format",
        "text",
    ]


def test_blocks_when_true_ec_schema_missing(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, include_ec_schema=False)
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_EC_SCHEMA_MISSING"


def test_ready_refresh_new_date_when_source_is_newer(tmp_path: Path, capsys) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path)
    exit_code = main(_base_args(db_path, taxonomy_path, watchlist_path))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Plan Status" in output
    assert "status=READY_REFRESH_NEW_DATE" in output
    assert "selected_signal_date=2026-06-06" in output
    assert "watchlist_contains_crgy=True" in output
    assert "dc_ticker_missing_primary_taxonomy_membership=[]" in output


def test_skip_up_to_date_when_selected_date_already_loaded(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, include_selected_in_all=True)
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "SKIP_UP_TO_DATE"


def test_ready_refresh_replace_date_when_selected_date_exists_and_replace_allowed(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, include_selected_in_all=True)
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
        allow_replace_date=True,
    )
    assert summary["status"] == "READY_REFRESH_REPLACE_DATE"


def test_blocks_partial_existing_date_without_replace(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(
        tmp_path,
        partial_selected_tables={"ec_ticker_signal_daily", "ec_group_signal_daily"},
    )
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_EXISTING_DATE_WITHOUT_REPLACE"


def test_blocks_when_source_dates_do_not_align(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, mismatched_synth_date="2026-06-05")
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_DATE_MISMATCH"


def test_blocks_when_taxonomy_hash_differs(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path)
    with taxonomy_path.open("a", encoding="utf-8") as handle:
        handle.write("# changed bytes\n")

    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_TAXONOMY_SOURCE"


def test_watchlist_only_crgy_does_not_block(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path)
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "READY_REFRESH_NEW_DATE"
    compatibility = summary["compatibility_summary"]
    assert compatibility["watchlist_missing_in_loaded"] == []
    assert compatibility["watchlist_loaded_only"] == []


def test_blocks_when_group_mapping_missing(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, missing_group_l1_name="Layer 03")
    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_UNCLEAR_MAPPING"
    assert "Layer 03" in summary["mapping_summary"]["missing_group_l1_entities"]


def test_eco_tables_do_not_count_as_ec_schema(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path, include_ec_schema=False)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE eco_report_run (report_run_id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
        taxonomy_csv_path=str(taxonomy_path),
        watchlist_path=str(watchlist_path),
    )
    assert summary["status"] == "BLOCKED_EC_SCHEMA_MISSING"


def test_planner_does_not_write_db_state(tmp_path: Path) -> None:
    db_path, taxonomy_path, watchlist_path = _create_refresh_fixture(tmp_path)
    before_conn = sqlite3.connect(db_path)
    try:
        before_counts = {
            "ec_ticker_signal_daily": before_conn.execute("SELECT COUNT(*) FROM ec_ticker_signal_daily").fetchone()[0],
            "ec_group_signal_daily": before_conn.execute("SELECT COUNT(*) FROM ec_group_signal_daily").fetchone()[0],
        }
    finally:
        before_conn.close()

    summary = plan_ec_source_layer_refresh(
        db_path=str(db_path),
        ecosystem_code="DATACENTER",
        taxonomy_version_code=TAXONOMY_VERSION,
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

    assert summary["status"] == "READY_REFRESH_NEW_DATE"
    assert before_counts == after_counts
