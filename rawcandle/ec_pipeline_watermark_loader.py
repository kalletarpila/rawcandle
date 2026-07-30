from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.ec_ticker_signal_daily_loader import (
    _connect_readonly,
    _connect_readwrite,
    _now_utc_iso,
    _require_columns,
    _require_table,
)


REQUIRED_SOURCE_TABLE = "dc_pipeline_watermark"
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_pipeline_watermark",
)
REQUIRED_SOURCE_COLUMNS = (
    "component_name",
    "taxonomy_version",
    "market",
    "signal_version",
    "calc_version",
    "start_date",
    "end_date",
    "row_count",
    "status",
    "last_successful_run_id",
    "last_successful_at_utc",
    "notes",
)
KNOWN_COMPONENT_SOURCE_TABLES = {
    "TICKER_SWING_BASE": "dc_ticker_swing_signal_daily",
    "GROUP_SWING_BASE": "dc_group_swing_signal_daily",
    "SYNTHETIC_OHLC_BASE": "dc_group_synthetic_ohlc_daily",
    "SYNTHETIC_OHLC_RELATIVE": "dc_group_synthetic_ohlc_daily",
    "GROUP_INDEX": "dc_group_index_daily",
}
HISTORICAL_BACKFILL_CANONICAL_FACT_WATERMARKS = (
    ("TICKER_SWING_BASE", "dc_ticker_swing_signal_daily"),
    ("GROUP_SWING_BASE", "dc_group_swing_signal_daily"),
    ("SYNTHETIC_OHLC_BASE", "dc_group_synthetic_ohlc_daily"),
    ("GROUP_INDEX", "dc_group_index_daily"),
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def _require_tables(conn: sqlite3.Connection, table_names: tuple[str, ...], label: str) -> None:
    existing = _table_names(conn)
    missing = [table_name for table_name in table_names if table_name not in existing]
    if missing:
        raise ValueError(f"Missing required {label} tables: {missing}")


def _resolve_ecosystem_id(conn: sqlite3.Connection, ecosystem_code: str) -> int:
    row = conn.execute(
        """
        SELECT ecosystem_id
        FROM ec_ecosystem
        WHERE ecosystem_code = ?
        """,
        (ecosystem_code,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Required ec_ecosystem row not found for ecosystem_code {ecosystem_code!r}")
    return int(row[0])


def _resolve_source_rows(
    conn: sqlite3.Connection,
    *,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_pipeline_watermark
        WHERE taxonomy_version = ?
        ORDER BY component_name, market, signal_version, calc_version
        """,
        (taxonomy_version_code,),
    ).fetchall()
    if not rows:
        raise ValueError(
            "No source watermark rows found for "
            f"taxonomy_version={taxonomy_version_code!r}"
        )
    return rows


def _map_component_to_source_table(component_name: str) -> tuple[str, bool]:
    mapped = KNOWN_COMPONENT_SOURCE_TABLES.get(component_name)
    if mapped is not None:
        return mapped, False
    return f"UNKNOWN:{component_name}", True


def _has_signal_run_table(conn: sqlite3.Connection) -> bool:
    return "ec_signal_run" in _table_names(conn)


def _signal_run_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM ec_signal_run WHERE run_id = ?", (run_id,)).fetchone()
    return row is not None


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_replace_policy(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    scoped_keys: list[tuple[str, str]],
    replace_existing: bool,
) -> None:
    existing_keys = [
        key
        for key in scoped_keys
        if conn.execute(
            """
            SELECT 1
            FROM ec_pipeline_watermark
            WHERE ecosystem_id = ?
              AND pipeline_name = ?
              AND source_table = ?
            """,
            (ecosystem_id, key[0], key[1]),
        ).fetchone()
        is not None
    ]
    if not existing_keys:
        return
    if not replace_existing:
        raise ValueError(
            "Target pipeline watermark rows already exist for selected ecosystem/component scope; "
            "use replace_existing=True to replace them"
        )
    conn.executemany(
        """
        DELETE FROM ec_pipeline_watermark
        WHERE ecosystem_id = ?
          AND pipeline_name = ?
          AND source_table = ?
        """,
        [(ecosystem_id, pipeline_name, source_table) for pipeline_name, source_table in existing_keys],
    )


def load_ec_pipeline_watermark_from_dc(
    source_db_path: str | Path,
    target_db_path: str | Path,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    replace_existing: bool = False,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_table(source_conn, REQUIRED_SOURCE_TABLE, "source")
        _require_columns(source_conn, REQUIRED_SOURCE_TABLE, REQUIRED_SOURCE_COLUMNS, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        source_rows = _resolve_source_rows(source_conn, taxonomy_version_code=taxonomy_version_code)
        ecosystem_id = _resolve_ecosystem_id(target_conn, ecosystem_code)
        loader_timestamp_utc = _now_utc_iso()
        signal_run_table_exists = _has_signal_run_table(target_conn)

        component_name_to_source_table: dict[str, str] = {}
        unknown_components: set[str] = set()
        unmatched_latest_run_ids: set[str] = set()
        empty_last_successful_run_id_count = 0
        scoped_keys: list[tuple[str, str]] = []
        pending_rows: list[tuple[str, str, str | None, str | None, str, str, str | None]] = []

        for row in source_rows:
            component_name = str(row["component_name"])
            source_table, is_unknown = _map_component_to_source_table(component_name)
            component_name_to_source_table[component_name] = source_table
            if is_unknown:
                unknown_components.add(component_name)

            last_successful_run_id = _normalize_text(row["last_successful_run_id"])
            latest_run_id: str | None = None
            if last_successful_run_id is None:
                empty_last_successful_run_id_count += 1
            elif signal_run_table_exists and _signal_run_exists(target_conn, last_successful_run_id):
                latest_run_id = last_successful_run_id
            else:
                unmatched_latest_run_ids.add(last_successful_run_id)

            source_last_successful_at_utc = _normalize_text(row["last_successful_at_utc"])
            created_at_utc = source_last_successful_at_utc or loader_timestamp_utc
            updated_at_utc = loader_timestamp_utc
            latest_signal_date = _normalize_text(row["end_date"])
            status = str(row["status"])

            scoped_keys.append((component_name, source_table))
            pending_rows.append(
                (
                    component_name,
                    source_table,
                    latest_signal_date,
                    latest_run_id,
                    status,
                    created_at_utc,
                    updated_at_utc,
                )
            )

        warnings: list[str] = []
        if unknown_components:
            warnings.append(
                "Unknown pipeline components mapped with UNKNOWN: prefix: "
                + ", ".join(sorted(unknown_components))
            )
        if empty_last_successful_run_id_count:
            warnings.append(
                "Source watermark rows had empty last_successful_run_id: "
                f"{empty_last_successful_run_id_count}"
            )
        if unmatched_latest_run_ids:
            warnings.append(
                "Source watermark run ids did not match ec_signal_run and were left NULL: "
                + ", ".join(sorted(unmatched_latest_run_ids))
            )

        with target_conn:
            _ensure_replace_policy(
                target_conn,
                ecosystem_id=ecosystem_id,
                scoped_keys=scoped_keys,
                replace_existing=replace_existing,
            )
            target_conn.executemany(
                """
                INSERT INTO ec_pipeline_watermark (
                    ecosystem_id,
                    pipeline_name,
                    source_table,
                    latest_signal_date,
                    latest_run_id,
                    status,
                    created_at_utc,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        ecosystem_id,
                        pipeline_name,
                        source_table,
                        latest_signal_date,
                        latest_run_id,
                        status,
                        created_at_utc,
                        updated_at_utc,
                    )
                    for (
                        pipeline_name,
                        source_table,
                        latest_signal_date,
                        latest_run_id,
                        status,
                        created_at_utc,
                        updated_at_utc,
                    ) in pending_rows
                ],
            )

        status = "OK_WITH_WARNINGS" if warnings else "OK"
        return {
            "status": status,
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "source_table": REQUIRED_SOURCE_TABLE,
            "source_row_count": len(source_rows),
            "loaded_row_count": len(pending_rows),
            "failed_row_count": 0,
            "component_count": len(component_name_to_source_table),
            "component_name_to_source_table": dict(sorted(component_name_to_source_table.items())),
            "unknown_components": sorted(unknown_components),
            "empty_last_successful_run_id_count": empty_last_successful_run_id_count,
            "unmatched_latest_run_ids": sorted(unmatched_latest_run_ids),
            "warnings": warnings,
        }
    finally:
        source_conn.close()
        target_conn.close()


def advance_ec_pipeline_watermarks_after_historical_backfill(
    *,
    target_db_path: str | Path,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    latest_signal_date: str,
) -> dict[str, object]:
    if not _normalize_text(latest_signal_date):
        raise ValueError("latest_signal_date is required for historical backfill watermark advancement")

    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        ecosystem_id = _resolve_ecosystem_id(target_conn, ecosystem_code)
        loader_timestamp_utc = _now_utc_iso()
        rows_inserted = 0
        rows_updated = 0
        rows_unchanged = 0

        with target_conn:
            for pipeline_name, source_table in HISTORICAL_BACKFILL_CANONICAL_FACT_WATERMARKS:
                row = target_conn.execute(
                    """
                    SELECT latest_signal_date
                    FROM ec_pipeline_watermark
                    WHERE ecosystem_id = ?
                      AND pipeline_name = ?
                      AND source_table = ?
                    """,
                    (ecosystem_id, pipeline_name, source_table),
                ).fetchone()
                if row is None:
                    target_conn.execute(
                        """
                        INSERT INTO ec_pipeline_watermark (
                            ecosystem_id,
                            pipeline_name,
                            source_table,
                            latest_signal_date,
                            latest_run_id,
                            status,
                            created_at_utc,
                            updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ecosystem_id,
                            pipeline_name,
                            source_table,
                            latest_signal_date,
                            None,
                            "OK",
                            loader_timestamp_utc,
                            loader_timestamp_utc,
                        ),
                    )
                    rows_inserted += 1
                    continue

                existing_latest_signal_date = _normalize_text(row[0])
                if existing_latest_signal_date is None or existing_latest_signal_date < latest_signal_date:
                    target_conn.execute(
                        """
                        UPDATE ec_pipeline_watermark
                        SET latest_signal_date = ?,
                            latest_run_id = NULL,
                            status = ?,
                            updated_at_utc = ?
                        WHERE ecosystem_id = ?
                          AND pipeline_name = ?
                          AND source_table = ?
                        """,
                        (
                            latest_signal_date,
                            "OK",
                            loader_timestamp_utc,
                            ecosystem_id,
                            pipeline_name,
                            source_table,
                        ),
                    )
                    rows_updated += 1
                else:
                    rows_unchanged += 1

        rows_total = len(HISTORICAL_BACKFILL_CANONICAL_FACT_WATERMARKS)
        return {
            "status": "OK",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "watermark_policy": "ADVANCE_CANONICAL_FACT_HEADS_AFTER_VALIDATED_BACKFILL",
            "watermark_refresh_performed": True,
            "watermark_advanced": (rows_inserted + rows_updated) > 0,
            "watermark_candidate_latest_signal_date": latest_signal_date,
            "watermark_rows_inserted": rows_inserted,
            "watermark_rows_updated": rows_updated,
            "watermark_rows_unchanged": rows_unchanged,
            "watermark_rows_total": rows_total,
            "watermark_advance_status": "OK",
            "canonical_component_to_source_table": dict(HISTORICAL_BACKFILL_CANONICAL_FACT_WATERMARKS),
        }
    finally:
        target_conn.close()
