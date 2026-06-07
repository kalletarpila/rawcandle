from __future__ import annotations

import sqlite3
from pathlib import Path

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


REQUIRED_SOURCE_TABLE = "dc_group_swing_signal_daily"
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_signal_run",
    "ec_group_signal_daily",
)
REQUIRED_SOURCE_COLUMNS = (
    "signal_date",
    "taxonomy_version",
    "group_type",
    "group_name",
    "member_count",
    "eligible_count",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "pct_above_ma10",
    "pct_above_ema20",
    "pct_above_rising_ema20",
    "ma10_breadth_delta_5d",
    "ema20_breadth_delta_5d",
    "trend_breadth",
    "weakness_breadth",
    "overheat_risk_level",
    "timing_state",
    "timing_reason",
    "data_quality_status",
    "signal_version",
    "run_id",
    "created_at_utc",
)
EXPECTED_UNMAPPED_SOURCE_COLUMNS: tuple[str, ...] = ()
EXPECTED_UNMAPPED_TARGET_COLUMNS = (
    "valid_price_count",
    "return_1d",
    "return_120d",
    "pct_above_sma50",
    "pct_above_sma200",
)


def _resolve_signal_date(conn: sqlite3.Connection, signal_date: str | None) -> str:
    if signal_date is not None:
        return signal_date
    resolved = _fetch_single_value(
        conn,
        f"SELECT MAX(signal_date) FROM {REQUIRED_SOURCE_TABLE}",
        (),
    )
    if resolved is None:
        raise ValueError("Could not resolve latest signal_date from dc_group_swing_signal_daily")
    return resolved


def _resolve_signal_version(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str | None,
) -> str:
    if signal_version is not None:
        return signal_version
    rows = conn.execute(
        """
        SELECT DISTINCT signal_version
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
        ORDER BY signal_version
        """,
        (signal_date,),
    ).fetchall()
    versions = [str(row[0]) for row in rows if row[0] is not None]
    if not versions:
        raise ValueError(f"No source rows found for signal_date {signal_date!r}")
    if len(versions) > 1:
        raise ValueError(
            "Multiple signal_version values found for selected signal_date; "
            "signal_version must be provided explicitly"
        )
    return versions[0]


def _resolve_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    signal_version: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
          AND signal_version = ?
        ORDER BY group_type, group_name
        """,
        (signal_date, signal_version),
    ).fetchall()
    if not rows:
        raise ValueError(
            "No source rows found for "
            f"signal_date={signal_date!r}, signal_version={signal_version!r}"
        )
    return rows


def _target_scope_row_count(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    signal_version: str,
) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_group_signal_daily
            WHERE ecosystem_id = ?
              AND taxonomy_version_id = ?
              AND signal_date = ?
              AND signal_version = ?
              AND source_table = ?
            """,
            (
                ecosystem_id,
                taxonomy_version_id,
                signal_date,
                signal_version,
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
    signal_version: str,
    replace_existing: bool,
) -> None:
    existing_count = _target_scope_row_count(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
        signal_version=signal_version,
    )
    if existing_count == 0:
        return
    if not replace_existing:
        raise ValueError(
            "Target group fact rows already exist for ecosystem/taxonomy/date/version scope; "
            "use replace_existing=True to replace them"
        )
    conn.execute(
        """
        DELETE FROM ec_group_signal_daily
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND signal_date = ?
          AND signal_version = ?
        """,
        (ecosystem_id, taxonomy_version_id, signal_date, signal_version),
    )


def _resolve_group_entity(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    group_type: str,
    group_name: str,
) -> tuple[str, int | None, str | None]:
    if group_type == "layer":
        entity_type = "GROUP_L1"
        rows = conn.execute(
            """
            SELECT entity_id
            FROM ec_entity
            WHERE ecosystem_id = ?
              AND entity_type = ?
              AND (entity_name = ? OR entity_code = ?)
            ORDER BY entity_id
            """,
            (ecosystem_id, entity_type, group_name, group_name),
        ).fetchall()
        if not rows:
            return "missing_entity", None, entity_type
        if len(rows) > 1:
            return "multiple_match", None, entity_type
        return "ok", int(rows[0][0]), entity_type

    if group_type == "subindustry":
        entity_type = "GROUP_L2"
        rows = conn.execute(
            """
            SELECT entity_id
            FROM ec_entity
            WHERE ecosystem_id = ?
              AND entity_type = ?
              AND (entity_name = ? OR entity_code = ?)
            ORDER BY entity_id
            """,
            (ecosystem_id, entity_type, group_name, group_name),
        ).fetchall()
        if not rows:
            return "missing_entity", None, entity_type
        if len(rows) > 1:
            return "multiple_match", None, entity_type
        return "ok", int(rows[0][0]), entity_type

    if group_type == "ecosystem":
        entity_type = "ECOSYSTEM"
        rows = conn.execute(
            """
            SELECT e.entity_id
            FROM ec_entity_alias a
            JOIN ec_entity e ON e.entity_id = a.entity_id
            WHERE a.ecosystem_id = ?
              AND a.alias_type = 'DC_GROUP_NAME'
              AND a.alias_value = ?
              AND a.source_system = 'dc_group_facts'
              AND e.entity_type = 'ECOSYSTEM'
            ORDER BY e.entity_id
            """,
            (ecosystem_id, group_name),
        ).fetchall()
        if not rows:
            return "missing_alias", None, entity_type
        if len(rows) > 1:
            return "multiple_match", None, entity_type
        return "ok", int(rows[0][0]), entity_type

    return "missing_entity", None, None


def _source_pk_json(row: sqlite3.Row) -> str:
    return _canonical_json(
        {
            "group_name": row["group_name"],
            "group_type": row["group_type"],
            "run_id": row["run_id"],
            "signal_date": row["signal_date"],
            "signal_version": row["signal_version"],
            "taxonomy_version": row["taxonomy_version"],
        }
    )


def _ensure_group_signal_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    signal_version: str,
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
            "GROUP_SIGNAL",
            signal_version,
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
        INSERT INTO ec_group_signal_daily (
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            entity_id,
            entity_type,
            signal_version,
            member_count,
            eligible_count,
            valid_price_count,
            return_1d,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            return_120d,
            pct_above_ma10,
            pct_above_ema20,
            pct_above_sma50,
            pct_above_sma200,
            ma10_breadth_delta_5d,
            ema20_breadth_delta_5d,
            trend_breadth,
            weakness_breadth,
            timing_state,
            timing_reason,
            overheat_risk_level,
            data_quality_status,
            pct_above_rising_ema20,
            source_table,
            source_pk_json,
            source_row_hash,
            source_run_id,
            created_at_utc
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            row["signal_date"],
            entity_id,
            entity_type,
            row["signal_version"],
            row["member_count"],
            row["eligible_count"],
            None,
            None,
            row["return_5d"],
            row["return_10d"],
            row["return_20d"],
            row["return_60d"],
            None,
            row["pct_above_ma10"],
            row["pct_above_ema20"],
            None,
            None,
            row["ma10_breadth_delta_5d"],
            row["ema20_breadth_delta_5d"],
            row["trend_breadth"],
            row["weakness_breadth"],
            row["timing_state"],
            row["timing_reason"],
            row["overheat_risk_level"],
            row["data_quality_status"],
            row["pct_above_rising_ema20"],
            REQUIRED_SOURCE_TABLE,
            _source_pk_json(row),
            _row_hash(row),
            row["run_id"],
            loader_timestamp_utc,
        ),
    )


def load_ec_group_signal_daily_from_dc(
    source_db_path: str,
    target_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
    signal_version: str | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_table(source_conn, REQUIRED_SOURCE_TABLE, "source")
        _require_columns(source_conn, REQUIRED_SOURCE_TABLE, REQUIRED_SOURCE_COLUMNS, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        selected_signal_date = _resolve_signal_date(source_conn, signal_date)
        selected_signal_version = _resolve_signal_version(
            source_conn,
            signal_date=selected_signal_date,
            signal_version=signal_version,
        )
        rows = _resolve_source_rows(
            source_conn,
            signal_date=selected_signal_date,
            signal_version=selected_signal_version,
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
                signal_version=selected_signal_version,
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
                    created = _ensure_group_signal_run(
                        target_conn,
                        run_id=run_id,
                        ecosystem_id=ecosystem_id,
                        taxonomy_version_id=taxonomy_version_id,
                        signal_date=selected_signal_date,
                        signal_version=selected_signal_version,
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
                    "signal_version": selected_signal_version,
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

        status = "OK_WITH_WARNINGS" if unmapped_target_columns else "OK"
        return {
            "status": status,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "signal_date": selected_signal_date,
            "signal_version": selected_signal_version,
            "source_table": REQUIRED_SOURCE_TABLE,
            "source_row_count": len(rows),
            "loaded_row_count": len(rows),
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
