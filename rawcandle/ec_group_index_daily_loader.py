from __future__ import annotations

import sqlite3

from rawcandle.ec_group_signal_daily_loader import _resolve_group_entity
from rawcandle.ec_ticker_signal_daily_loader import (
    _canonical_json,
    _connect_readonly,
    _connect_readwrite,
    _fetch_single_value,
    _now_utc_iso,
    _require_columns,
    _require_table,
    _require_tables,
    _resolve_target_context,
    _row_hash,
)


REQUIRED_SOURCE_TABLE = "dc_group_index_daily"
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_signal_run",
    "ec_group_index_daily",
)
REQUIRED_SOURCE_COLUMNS = (
    "index_date",
    "taxonomy_version",
    "group_type",
    "group_name",
    "member_count",
    "eligible_count",
    "ma50_eligible_count",
    "ma200_eligible_count",
    "daily_return_equal",
    "median_return",
    "pct_positive",
    "index_level_equal",
    "return_20d",
    "return_60d",
    "return_120d",
    "pct_above_ma50",
    "pct_above_ma200",
    "volatility_20d",
    "volatility_60d",
    "relative_strength_spy_60d",
    "relative_strength_qqq_60d",
    "data_quality_status",
    "calc_version",
    "run_id",
    "created_at_utc",
)
EXPECTED_UNMAPPED_SOURCE_COLUMNS: tuple[str, ...] = ()
EXPECTED_UNMAPPED_TARGET_COLUMNS = (
    "return_5d",
    "return_10d",
    "trend_breadth",
    "weakness_breadth",
    "relative_strength_20d",
)


def _resolve_signal_date(conn: sqlite3.Connection, signal_date: str | None) -> str:
    if signal_date is not None:
        return signal_date
    resolved = _fetch_single_value(
        conn,
        f"SELECT MAX(index_date) FROM {REQUIRED_SOURCE_TABLE}",
        (),
    )
    if resolved is None:
        raise ValueError("Could not resolve latest index_date from dc_group_index_daily")
    return resolved


def _resolve_calc_version(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    calc_version: str | None,
) -> str:
    if calc_version is not None:
        return calc_version
    rows = conn.execute(
        """
        SELECT DISTINCT calc_version
        FROM dc_group_index_daily
        WHERE index_date = ?
        ORDER BY calc_version
        """,
        (signal_date,),
    ).fetchall()
    versions = [str(row[0]) for row in rows if row[0] is not None]
    if not versions:
        raise ValueError(f"No source rows found for index_date {signal_date!r}")
    if len(versions) > 1:
        raise ValueError(
            "Multiple calc_version values found for selected index_date; "
            "calc_version must be provided explicitly"
        )
    return versions[0]


def _resolve_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    calc_version: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_index_daily
        WHERE index_date = ?
          AND calc_version = ?
        ORDER BY group_type, group_name
        """,
        (signal_date, calc_version),
    ).fetchall()
    if not rows:
        raise ValueError(
            "No source rows found for "
            f"index_date={signal_date!r}, calc_version={calc_version!r}"
        )
    return rows


def _target_scope_row_count(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    calc_version: str,
) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_group_index_daily
            WHERE ecosystem_id = ?
              AND taxonomy_version_id = ?
              AND signal_date = ?
              AND calc_version = ?
              AND source_table = ?
            """,
            (
                ecosystem_id,
                taxonomy_version_id,
                signal_date,
                calc_version,
                REQUIRED_SOURCE_TABLE,
            ),
        ).fetchone()[0]
    )


def _ensure_replace_policy(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    calc_version: str,
    replace_existing: bool,
) -> None:
    existing_count = _target_scope_row_count(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
        calc_version=calc_version,
    )
    if existing_count == 0:
        return
    if not replace_existing:
        raise ValueError(
            "Target group index fact rows already exist for ecosystem/taxonomy/date/version scope; "
            "use replace_existing=True to replace them"
        )
    conn.execute(
        """
        DELETE FROM ec_group_index_daily
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND signal_date = ?
          AND calc_version = ?
        """,
        (ecosystem_id, taxonomy_version_id, signal_date, calc_version),
    )


def _source_pk_json(row: sqlite3.Row) -> str:
    return _canonical_json(
        {
            "calc_version": row["calc_version"],
            "group_name": row["group_name"],
            "group_type": row["group_type"],
            "index_date": row["index_date"],
            "run_id": row["run_id"],
            "taxonomy_version": row["taxonomy_version"],
        }
    )


def _ensure_group_index_signal_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    source_created_at_utc: str | None,
    loader_timestamp_utc: str,
) -> bool:
    existing = conn.execute("SELECT 1 FROM ec_signal_run WHERE run_id = ?", (run_id,)).fetchone()
    if existing is not None:
        return False

    started_at_utc = source_created_at_utc or loader_timestamp_utc
    conn.execute(
        """
        INSERT INTO ec_signal_run (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            run_type,
            signal_version,
            ohlc_calc_version,
            source_mode,
            status,
            started_at_utc,
            finished_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            "GROUP_INDEX",
            None,
            None,
            "DC_BACKFILL",
            "OK",
            started_at_utc,
            source_created_at_utc,
        ),
    )
    return True


def _insert_target_row(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    loader_timestamp_utc: str,
    entity_id: int,
    entity_type: str,
    row: sqlite3.Row,
) -> None:
    conn.execute(
        """
        INSERT INTO ec_group_index_daily (
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            entity_id,
            entity_type,
            calc_version,
            index_value,
            return_1d,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            return_120d,
            volatility_20d,
            trend_breadth,
            weakness_breadth,
            relative_strength_20d,
            data_quality_status,
            ma50_eligible_count,
            ma200_eligible_count,
            median_return,
            pct_positive,
            pct_above_ma50,
            pct_above_ma200,
            volatility_60d,
            relative_strength_spy_60d,
            relative_strength_qqq_60d,
            source_table,
            source_pk_json,
            source_row_hash,
            source_run_id,
            created_at_utc
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            row["index_date"],
            entity_id,
            entity_type,
            row["calc_version"],
            row["index_level_equal"],
            row["daily_return_equal"],
            None,
            None,
            row["return_20d"],
            row["return_60d"],
            row["return_120d"],
            row["volatility_20d"],
            None,
            None,
            None,
            row["data_quality_status"],
            row["ma50_eligible_count"],
            row["ma200_eligible_count"],
            row["median_return"],
            row["pct_positive"],
            row["pct_above_ma50"],
            row["pct_above_ma200"],
            row["volatility_60d"],
            row["relative_strength_spy_60d"],
            row["relative_strength_qqq_60d"],
            REQUIRED_SOURCE_TABLE,
            _source_pk_json(row),
            _row_hash(row),
            row["run_id"],
            loader_timestamp_utc,
        ),
    )


def load_ec_group_index_daily_from_dc(
    source_db_path: str,
    target_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
    calc_version: str | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_table(source_conn, REQUIRED_SOURCE_TABLE, "source")
        _require_columns(source_conn, REQUIRED_SOURCE_TABLE, REQUIRED_SOURCE_COLUMNS, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        selected_signal_date = _resolve_signal_date(source_conn, signal_date)
        selected_calc_version = _resolve_calc_version(
            source_conn,
            signal_date=selected_signal_date,
            calc_version=calc_version,
        )
        rows = _resolve_source_rows(
            source_conn,
            signal_date=selected_signal_date,
            calc_version=selected_calc_version,
        )
        ecosystem_id, taxonomy_version_id = _resolve_target_context(
            target_conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )
        loader_timestamp_utc = _now_utc_iso()
        source_run_ids = sorted({str(row["run_id"]) for row in rows})

        warnings: list[str] = []
        missing_group_entities: list[str] = []
        missing_group_aliases: list[str] = []
        multiple_group_matches: list[str] = []
        failed_row_count = 0
        group_count_by_type = {"ecosystem": 0, "layer": 0, "subindustry": 0}

        with target_conn:
            _ensure_replace_policy(
                target_conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
                signal_date=selected_signal_date,
                calc_version=selected_calc_version,
                replace_existing=replace_existing,
            )

            created_signal_run_count = 0
            reused_signal_run_count = 0
            seen_source_runs: set[str] = set()
            pending_rows: list[tuple[sqlite3.Row, int, str]] = []

            for row in rows:
                source_group_type = str(row["group_type"])
                group_count_by_type[source_group_type] = group_count_by_type.get(source_group_type, 0) + 1
                status, entity_id, entity_type = _resolve_group_entity(
                    target_conn,
                    ecosystem_id=ecosystem_id,
                    group_type=source_group_type,
                    group_name=str(row["group_name"]),
                )
                if status == "missing_entity":
                    missing_group_entities.append(f"{source_group_type}:{row['group_name']}")
                    failed_row_count += 1
                    continue
                if status == "missing_alias":
                    missing_group_aliases.append(str(row["group_name"]))
                    failed_row_count += 1
                    continue
                if status == "multiple_match":
                    multiple_group_matches.append(f"{source_group_type}:{row['group_name']}")
                    failed_row_count += 1
                    continue

                run_id = str(row["run_id"])
                if run_id not in seen_source_runs:
                    created = _ensure_group_index_signal_run(
                        target_conn,
                        run_id=run_id,
                        ecosystem_id=ecosystem_id,
                        taxonomy_version_id=taxonomy_version_id,
                        signal_date=selected_signal_date,
                        source_created_at_utc=(
                            str(row["created_at_utc"]) if row["created_at_utc"] is not None else None
                        ),
                        loader_timestamp_utc=loader_timestamp_utc,
                    )
                    if created:
                        created_signal_run_count += 1
                    else:
                        reused_signal_run_count += 1
                    seen_source_runs.add(run_id)

                pending_rows.append((row, int(entity_id), str(entity_type)))

            if failed_row_count > 0:
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "calc_version": selected_calc_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    "source_row_count": len(rows),
                    "loaded_row_count": 0,
                    "failed_row_count": failed_row_count,
                    "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                    "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                    "missing_group_entities": sorted(missing_group_entities),
                    "missing_group_aliases": sorted(missing_group_aliases),
                    "multiple_group_matches": sorted(multiple_group_matches),
                    "source_run_ids": source_run_ids,
                    "created_signal_run_count": 0,
                    "reused_signal_run_count": 0,
                    "group_count_by_type": group_count_by_type,
                    "warnings": warnings,
                }

            for row, entity_id, entity_type in pending_rows:
                _insert_target_row(
                    target_conn,
                    ecosystem_id=ecosystem_id,
                    taxonomy_version_id=taxonomy_version_id,
                    loader_timestamp_utc=loader_timestamp_utc,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    row=row,
                )

        unmapped_source_columns = list(EXPECTED_UNMAPPED_SOURCE_COLUMNS)
        unmapped_target_columns = list(EXPECTED_UNMAPPED_TARGET_COLUMNS)
        if unmapped_target_columns:
            warnings.append(
                "Target columns left NULL because current dc source has no values: "
                + ", ".join(unmapped_target_columns)
            )

        status = "OK_WITH_WARNINGS" if warnings else "OK"
        return {
            "status": status,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "signal_date": selected_signal_date,
            "calc_version": selected_calc_version,
            "source_table": REQUIRED_SOURCE_TABLE,
            "source_row_count": len(rows),
            "loaded_row_count": len(pending_rows),
            "failed_row_count": 0,
            "unmapped_source_columns": unmapped_source_columns,
            "unmapped_target_columns": unmapped_target_columns,
            "missing_group_entities": [],
            "missing_group_aliases": [],
            "multiple_group_matches": [],
            "source_run_ids": source_run_ids,
            "created_signal_run_count": created_signal_run_count,
            "reused_signal_run_count": reused_signal_run_count,
            "group_count_by_type": group_count_by_type,
            "warnings": warnings,
        }
    finally:
        source_conn.close()
        target_conn.close()
