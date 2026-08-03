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


REQUIRED_SOURCE_TABLE = "dc_group_synthetic_ohlc_daily"
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_signal_run",
    "ec_group_synthetic_ohlc_daily",
)
REQUIRED_SOURCE_COLUMNS = (
    "ohlc_date",
    "taxonomy_version",
    "group_type",
    "group_name",
    "member_count",
    "eligible_count",
    "synthetic_open",
    "synthetic_high",
    "synthetic_low",
    "synthetic_close",
    "synthetic_volume",
    "ma20",
    "ema20",
    "distance_to_ema20_pct",
    "volatility_20d",
    "pivot_radius",
    "latest_pivot_high_date",
    "latest_pivot_high_value",
    "latest_pivot_low_date",
    "latest_pivot_low_value",
    "latest_structure_label",
    "trend_classification",
    "relative_base_window",
    "relative_open_20",
    "relative_high_20",
    "relative_low_20",
    "relative_close_20",
    "relative_upper_wick_20",
    "relative_lower_wick_20",
    "relative_close_extension_20",
    "relative_high_extension_20",
    "relative_low_extension_20",
    "relative_eligible_count",
    "data_quality_status",
    "calc_version",
    "run_id",
    "created_at_utc",
    "latest_structure_age_trading_days",
    "latest_structure_freshness",
    "latest_bos_event_type",
    "latest_bos_event_date",
    "latest_bos_confirmed_as_of_date",
    "latest_bos_age_trading_days",
    "latest_bos_freshness",
    "latest_reset_event_date",
    "latest_reset_confirmed_as_of_date",
    "latest_reset_reason",
    "latest_reset_age_trading_days",
    "latest_reset_freshness",
)
EXPECTED_UNMAPPED_SOURCE_COLUMNS: tuple[str, ...] = ()
EXPECTED_UNMAPPED_TARGET_COLUMNS = (
    "latest_structure_date",
    "structure_state",
    "relative_strength_5d",
    "relative_strength_20d",
)


def _resolve_signal_date(conn: sqlite3.Connection, signal_date: str | None) -> str:
    if signal_date is not None:
        return signal_date
    resolved = _fetch_single_value(
        conn,
        f"SELECT MAX(ohlc_date) FROM {REQUIRED_SOURCE_TABLE}",
        (),
    )
    if resolved is None:
        raise ValueError("Could not resolve latest ohlc_date from dc_group_synthetic_ohlc_daily")
    return resolved


def _resolve_ohlc_calc_version(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    ohlc_calc_version: str | None,
) -> str:
    if ohlc_calc_version is not None:
        row_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM dc_group_synthetic_ohlc_daily
                WHERE ohlc_date = ?
                  AND calc_version = ?
                  AND taxonomy_version = ?
                """,
                (signal_date, ohlc_calc_version, taxonomy_version_code),
            ).fetchone()[0]
        )
        if row_count == 0:
            raise ValueError(
                "No source rows found for requested taxonomy/calc scope: "
                f"ohlc_date={signal_date!r}, calc_version={ohlc_calc_version!r}, "
                f"taxonomy_version={taxonomy_version_code!r}"
            )
        return ohlc_calc_version
    rows = conn.execute(
        """
        SELECT DISTINCT calc_version
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
          AND taxonomy_version = ?
        ORDER BY calc_version
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    versions = [str(row[0]) for row in rows if row[0] is not None]
    if not versions:
        raise ValueError(
            "No source rows found for requested taxonomy/date scope: "
            f"ohlc_date={signal_date!r}, taxonomy_version={taxonomy_version_code!r}"
        )
    if len(versions) > 1:
        raise ValueError(
            "Multiple calc_version values found for selected taxonomy/date scope; "
            "ohlc_calc_version must be provided explicitly"
        )
    return versions[0]


def _resolve_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    ohlc_calc_version: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
          AND calc_version = ?
          AND taxonomy_version = ?
        ORDER BY group_type, group_name
        """,
        (signal_date, ohlc_calc_version, taxonomy_version_code),
    ).fetchall()
    if not rows:
        raise ValueError(
            "No source rows found for "
            f"ohlc_date={signal_date!r}, calc_version={ohlc_calc_version!r}, "
            f"taxonomy_version={taxonomy_version_code!r}"
        )
    return rows


def _source_scope_failed_summary(
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
    signal_date: str,
    ohlc_calc_version: str | None,
    error_code: str,
    error: str,
) -> dict[str, object]:
    return {
        "status": "FAILED",
        "loader_status": "FAILED",
        "loader_error_code": error_code,
        "loader_error": error,
        "synthetic_loader_error": error,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "requested_taxonomy_version": taxonomy_version_code,
        "source_taxonomy_version": None,
        "source_taxonomy_versions": [],
        "source_taxonomy_match": False,
        "signal_date": signal_date,
        "ohlc_calc_version": ohlc_calc_version,
        "source_table": REQUIRED_SOURCE_TABLE,
        "source_row_count": 0,
        "source_distinct_group_count": 0,
        "duplicate_source_group_count": 0,
        "duplicate_source_groups": [],
        "unexpected_taxonomy_version_count": 0,
        "unexpected_taxonomy_version_groups": [],
        "unexpected_calc_version_count": 0,
        "unexpected_calc_version_groups": [],
        "null_required_source_key_count": 0,
        "null_required_source_key_groups": [],
        "group_type_counts": {},
        "data_quality_status_counts": {},
        "loaded_row_count": 0,
        "failed_row_count": 0,
        "mapped_row_count": 0,
        "distinct_target_key_count": 0,
        "duplicate_target_key_count": 0,
        "duplicate_target_keys": [],
        "null_target_key_count": 0,
        "null_target_key_groups": [],
        "unresolved_group_count": 0,
        "unresolved_groups": [],
        "multiple_source_to_same_target_count": 0,
        "multiple_source_to_same_target": [],
        "missing_group_entities": [],
        "missing_group_aliases": [],
        "multiple_group_matches": [],
        "source_run_ids": [],
        "created_signal_run_count": 0,
        "reused_signal_run_count": 0,
        "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
        "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
        "group_count_by_type": {},
        "warnings": [],
    }


def _source_group_key(row: sqlite3.Row) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    return (
        str(row["ohlc_date"]) if row["ohlc_date"] is not None else None,
        str(row["taxonomy_version"]) if row["taxonomy_version"] is not None else None,
        str(row["group_type"]) if row["group_type"] is not None else None,
        str(row["group_name"]) if row["group_name"] is not None else None,
        str(row["calc_version"]) if row["calc_version"] is not None else None,
    )


def _group_ref(row: sqlite3.Row) -> str:
    return (
        f"{row['taxonomy_version']}:{row['group_type']}:{row['group_name']}:"
        f"{row['ohlc_date']}:{row['calc_version']}"
    )


def _source_validation_summary(
    rows: list[sqlite3.Row],
    *,
    requested_taxonomy_version: str,
    requested_calc_version: str,
) -> dict[str, object]:
    source_taxonomy_versions = sorted({str(row["taxonomy_version"]) for row in rows if row["taxonomy_version"] is not None})
    group_type_counts: dict[str, int] = {}
    data_quality_status_counts: dict[str, int] = {}
    duplicate_source_groups: list[dict[str, object]] = []
    unexpected_taxonomy_groups: list[str] = []
    unexpected_calc_groups: list[str] = []
    null_required_groups: list[str] = []
    key_counts: dict[tuple[str | None, str | None, str | None, str | None, str | None], int] = {}

    for row in rows:
        group_type = str(row["group_type"]) if row["group_type"] is not None else "<NULL>"
        group_type_counts[group_type] = group_type_counts.get(group_type, 0) + 1
        quality = str(row["data_quality_status"]) if row["data_quality_status"] is not None else "<NULL>"
        data_quality_status_counts[quality] = data_quality_status_counts.get(quality, 0) + 1
        key = _source_group_key(row)
        key_counts[key] = key_counts.get(key, 0) + 1
        if str(row["taxonomy_version"]) != requested_taxonomy_version:
            unexpected_taxonomy_groups.append(_group_ref(row))
        if str(row["calc_version"]) != requested_calc_version:
            unexpected_calc_groups.append(_group_ref(row))
        if any(value is None for value in key):
            null_required_groups.append(_group_ref(row))

    for key, count in sorted(key_counts.items(), key=lambda item: tuple("" if value is None else value for value in item[0])):
        if count > 1:
            duplicate_source_groups.append(
                {
                    "ohlc_date": key[0],
                    "taxonomy_version": key[1],
                    "group_type": key[2],
                    "group_name": key[3],
                    "calc_version": key[4],
                    "count": count,
                }
            )

    return {
        "requested_taxonomy_version": requested_taxonomy_version,
        "source_taxonomy_version": source_taxonomy_versions[0] if len(source_taxonomy_versions) == 1 else None,
        "source_taxonomy_versions": source_taxonomy_versions,
        "source_taxonomy_match": source_taxonomy_versions == [requested_taxonomy_version],
        "source_row_count": len(rows),
        "source_distinct_group_count": len(key_counts),
        "duplicate_source_group_count": len(duplicate_source_groups),
        "duplicate_source_groups": duplicate_source_groups,
        "unexpected_taxonomy_version_count": len(unexpected_taxonomy_groups),
        "unexpected_taxonomy_version_groups": sorted(unexpected_taxonomy_groups),
        "unexpected_calc_version_count": len(unexpected_calc_groups),
        "unexpected_calc_version_groups": sorted(unexpected_calc_groups),
        "null_required_source_key_count": len(null_required_groups),
        "null_required_source_key_groups": sorted(null_required_groups),
        "group_type_counts": dict(sorted(group_type_counts.items())),
        "data_quality_status_counts": dict(sorted(data_quality_status_counts.items())),
    }


def _target_key_validation_summary(
    target_keys: list[tuple[int | None, int | None, str | None, int | None, str | None, str]],
) -> dict[str, object]:
    key_counts: dict[tuple[int | None, int | None, str | None, int | None, str | None], list[str]] = {}
    null_groups: list[str] = []
    for ecosystem_id, taxonomy_version_id, signal_date, entity_id, calc_version, source_group in target_keys:
        key = (ecosystem_id, taxonomy_version_id, signal_date, entity_id, calc_version)
        key_counts.setdefault(key, []).append(source_group)
        if any(value is None for value in key):
            null_groups.append(source_group)

    duplicate_target_keys = []
    multiple_source_to_same_target = []
    for key, source_groups in sorted(key_counts.items(), key=lambda item: tuple("" if value is None else str(value) for value in item[0])):
        if len(source_groups) > 1:
            entry = {
                "ecosystem_id": key[0],
                "taxonomy_version_id": key[1],
                "signal_date": key[2],
                "entity_id": key[3],
                "calc_version": key[4],
                "count": len(source_groups),
                "source_groups": sorted(source_groups),
            }
            duplicate_target_keys.append(entry)
            multiple_source_to_same_target.append(entry)

    return {
        "distinct_target_key_count": len(key_counts),
        "duplicate_target_key_count": len(duplicate_target_keys),
        "duplicate_target_keys": duplicate_target_keys,
        "null_target_key_count": len(null_groups),
        "null_target_key_groups": sorted(null_groups),
        "multiple_source_to_same_target_count": len(multiple_source_to_same_target),
        "multiple_source_to_same_target": multiple_source_to_same_target,
    }


def _target_scope_row_count(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    ohlc_calc_version: str,
) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM ec_group_synthetic_ohlc_daily
            WHERE ecosystem_id = ?
              AND taxonomy_version_id = ?
              AND signal_date = ?
              AND ohlc_calc_version = ?
              AND source_table = ?
            """,
            (
                ecosystem_id,
                taxonomy_version_id,
                signal_date,
                ohlc_calc_version,
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
    ohlc_calc_version: str,
    replace_existing: bool,
) -> None:
    existing_count = _target_scope_row_count(
        conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
        ohlc_calc_version=ohlc_calc_version,
    )
    if existing_count == 0:
        return
    if not replace_existing:
        raise ValueError(
            "Target synthetic OHLC fact rows already exist for ecosystem/taxonomy/date/version scope; "
            "use replace_existing=True to replace them"
        )
    conn.execute(
        """
        DELETE FROM ec_group_synthetic_ohlc_daily
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND signal_date = ?
          AND ohlc_calc_version = ?
        """,
        (ecosystem_id, taxonomy_version_id, signal_date, ohlc_calc_version),
    )


def _source_pk_json(row: sqlite3.Row) -> str:
    return _canonical_json(
        {
            "calc_version": row["calc_version"],
            "group_name": row["group_name"],
            "group_type": row["group_type"],
            "ohlc_date": row["ohlc_date"],
            "run_id": row["run_id"],
            "taxonomy_version": row["taxonomy_version"],
        }
    )


def _ensure_synthetic_ohlc_signal_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    ohlc_calc_version: str,
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
            "SYNTHETIC_OHLC",
            None,
            ohlc_calc_version,
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
        INSERT INTO ec_group_synthetic_ohlc_daily (
            ecosystem_id,
            taxonomy_version_id,
            signal_date,
            entity_id,
            entity_type,
            ohlc_calc_version,
            member_count,
            eligible_count,
            synthetic_open,
            synthetic_high,
            synthetic_low,
            synthetic_close,
            synthetic_volume,
            ma20,
            ema20,
            distance_to_ema20_pct,
            volatility_20d,
            pivot_radius,
            latest_pivot_high_date,
            latest_pivot_high_value,
            latest_pivot_low_date,
            latest_pivot_low_value,
            latest_structure_label,
            latest_structure_date,
            latest_structure_age_trading_days,
            structure_freshness,
            latest_bos_event_type,
            latest_bos_date,
            latest_bos_confirmed_as_of_date,
            latest_bos_age_trading_days,
            bos_freshness,
            latest_reset_reason,
            latest_reset_date,
            latest_reset_confirmed_as_of_date,
            latest_reset_age_trading_days,
            reset_freshness,
            trend_state,
            structure_state,
            relative_base_window,
            relative_open_20,
            relative_high_20,
            relative_low_20,
            relative_close_20,
            relative_upper_wick_20,
            relative_lower_wick_20,
            relative_close_extension_20,
            relative_high_extension_20,
            relative_low_extension_20,
            relative_eligible_count,
            relative_strength_5d,
            relative_strength_20d,
            data_quality_status,
            source_table,
            source_pk_json,
            source_row_hash,
            source_run_id,
            created_at_utc
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            ecosystem_id,
            taxonomy_version_id,
            row["ohlc_date"],
            entity_id,
            entity_type,
            row["calc_version"],
            row["member_count"],
            row["eligible_count"],
            row["synthetic_open"],
            row["synthetic_high"],
            row["synthetic_low"],
            row["synthetic_close"],
            row["synthetic_volume"],
            row["ma20"],
            row["ema20"],
            row["distance_to_ema20_pct"],
            row["volatility_20d"],
            row["pivot_radius"],
            row["latest_pivot_high_date"],
            row["latest_pivot_high_value"],
            row["latest_pivot_low_date"],
            row["latest_pivot_low_value"],
            row["latest_structure_label"],
            None,
            row["latest_structure_age_trading_days"],
            row["latest_structure_freshness"],
            row["latest_bos_event_type"],
            row["latest_bos_event_date"],
            row["latest_bos_confirmed_as_of_date"],
            row["latest_bos_age_trading_days"],
            row["latest_bos_freshness"],
            row["latest_reset_reason"],
            row["latest_reset_event_date"],
            row["latest_reset_confirmed_as_of_date"],
            row["latest_reset_age_trading_days"],
            row["latest_reset_freshness"],
            row["trend_classification"],
            None,
            row["relative_base_window"],
            row["relative_open_20"],
            row["relative_high_20"],
            row["relative_low_20"],
            row["relative_close_20"],
            row["relative_upper_wick_20"],
            row["relative_lower_wick_20"],
            row["relative_close_extension_20"],
            row["relative_high_extension_20"],
            row["relative_low_extension_20"],
            row["relative_eligible_count"],
            None,
            None,
            row["data_quality_status"],
            REQUIRED_SOURCE_TABLE,
            _source_pk_json(row),
            _row_hash(row),
            row["run_id"],
            loader_timestamp_utc,
        ),
    )


def load_ec_group_synthetic_ohlc_daily_from_dc(
    source_db_path: str,
    target_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
    ohlc_calc_version: str | None = None,
    replace_existing: bool = False,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readwrite(target_db_path)
    try:
        _require_table(source_conn, REQUIRED_SOURCE_TABLE, "source")
        _require_columns(source_conn, REQUIRED_SOURCE_TABLE, REQUIRED_SOURCE_COLUMNS, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")

        selected_signal_date = _resolve_signal_date(source_conn, signal_date)
        try:
            selected_ohlc_calc_version = _resolve_ohlc_calc_version(
                source_conn,
                signal_date=selected_signal_date,
                taxonomy_version_code=taxonomy_version_code,
                ohlc_calc_version=ohlc_calc_version,
            )
        except ValueError as exc:
            message = str(exc)
            error_code = (
                "SOURCE_CALC_VERSION_AMBIGUOUS"
                if "Multiple calc_version" in message
                else "SOURCE_SCOPE_UNAVAILABLE"
            )
            return _source_scope_failed_summary(
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                signal_date=selected_signal_date,
                ohlc_calc_version=ohlc_calc_version,
                error_code=error_code,
                error=message,
            )
        try:
            rows = _resolve_source_rows(
                source_conn,
                signal_date=selected_signal_date,
                ohlc_calc_version=selected_ohlc_calc_version,
                taxonomy_version_code=taxonomy_version_code,
            )
        except ValueError as exc:
            return _source_scope_failed_summary(
                ecosystem_code=ecosystem_code,
                taxonomy_version_code=taxonomy_version_code,
                signal_date=selected_signal_date,
                ohlc_calc_version=selected_ohlc_calc_version,
                error_code="SOURCE_SCOPE_UNAVAILABLE",
                error=str(exc),
            )
        source_validation = _source_validation_summary(
            rows,
            requested_taxonomy_version=taxonomy_version_code,
            requested_calc_version=selected_ohlc_calc_version,
        )
        if (
            not source_validation["source_taxonomy_match"]
            or int(source_validation["duplicate_source_group_count"]) > 0
            or int(source_validation["unexpected_taxonomy_version_count"]) > 0
            or int(source_validation["unexpected_calc_version_count"]) > 0
            or int(source_validation["null_required_source_key_count"]) > 0
        ):
            return {
                "status": "FAILED",
                "loader_status": "FAILED",
                "loader_error_code": "SOURCE_SCOPE_INVALID",
                "loader_error": "Synthetic OHLC source rows failed taxonomy scope validation",
                "synthetic_loader_error": "Synthetic OHLC source rows failed taxonomy scope validation",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "signal_date": selected_signal_date,
                "ohlc_calc_version": selected_ohlc_calc_version,
                "source_table": REQUIRED_SOURCE_TABLE,
                **source_validation,
                "loaded_row_count": 0,
                "failed_row_count": len(rows),
                "mapped_row_count": 0,
                "distinct_target_key_count": 0,
                "duplicate_target_key_count": 0,
                "duplicate_target_keys": [],
                "null_target_key_count": 0,
                "null_target_key_groups": [],
                "unresolved_group_count": 0,
                "unresolved_groups": [],
                "multiple_source_to_same_target_count": 0,
                "multiple_source_to_same_target": [],
                "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                "missing_group_entities": [],
                "missing_group_aliases": [],
                "multiple_group_matches": [],
                "source_run_ids": [],
                "created_signal_run_count": 0,
                "reused_signal_run_count": 0,
                "group_count_by_type": dict(source_validation["group_type_counts"]),
                "warnings": [],
            }
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
                ohlc_calc_version=selected_ohlc_calc_version,
                replace_existing=replace_existing,
            )

            created_signal_run_count = 0
            reused_signal_run_count = 0
            seen_source_runs: set[str] = set()
            pending_rows: list[tuple[sqlite3.Row, int, str]] = []
            target_keys: list[tuple[int | None, int | None, str | None, int | None, str | None, str]] = []

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
                    created = _ensure_synthetic_ohlc_signal_run(
                        target_conn,
                        run_id=run_id,
                        ecosystem_id=ecosystem_id,
                        taxonomy_version_id=taxonomy_version_id,
                        signal_date=selected_signal_date,
                        ohlc_calc_version=selected_ohlc_calc_version,
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
                target_keys.append(
                    (
                        ecosystem_id,
                        taxonomy_version_id,
                        str(row["ohlc_date"]) if row["ohlc_date"] is not None else None,
                        int(entity_id),
                        str(row["calc_version"]) if row["calc_version"] is not None else None,
                        f"{row['taxonomy_version']}:{row['group_type']}:{row['group_name']}",
                    )
                )

            target_key_validation = _target_key_validation_summary(target_keys)
            unresolved_groups = sorted(
                set(missing_group_entities)
                | {f"ecosystem:{group_name}" for group_name in missing_group_aliases}
                | set(multiple_group_matches)
            )

            if failed_row_count > 0:
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "loader_status": "FAILED",
                    "loader_error_code": "TARGET_MAPPING_UNRESOLVED",
                    "loader_error": "Synthetic OHLC rows could not be resolved to one EC group entity",
                    "synthetic_loader_error": "Synthetic OHLC rows could not be resolved to one EC group entity",
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "ohlc_calc_version": selected_ohlc_calc_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    **source_validation,
                    "loaded_row_count": 0,
                    "failed_row_count": failed_row_count,
                    "mapped_row_count": len(pending_rows),
                    **target_key_validation,
                    "unresolved_group_count": len(unresolved_groups),
                    "unresolved_groups": unresolved_groups,
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
            if (
                int(target_key_validation["duplicate_target_key_count"]) > 0
                or int(target_key_validation["null_target_key_count"]) > 0
                or int(target_key_validation["multiple_source_to_same_target_count"]) > 0
            ):
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "loader_status": "FAILED",
                    "loader_error_code": "TARGET_KEY_INVALID",
                    "loader_error": "Synthetic OHLC rows produced duplicate or null EC target keys",
                    "synthetic_loader_error": "Synthetic OHLC rows produced duplicate or null EC target keys",
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "ohlc_calc_version": selected_ohlc_calc_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    **source_validation,
                    "loaded_row_count": 0,
                    "failed_row_count": len(rows),
                    "mapped_row_count": len(pending_rows),
                    **target_key_validation,
                    "unresolved_group_count": 0,
                    "unresolved_groups": [],
                    "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                    "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                    "missing_group_entities": [],
                    "missing_group_aliases": [],
                    "multiple_group_matches": [],
                    "source_run_ids": source_run_ids,
                    "created_signal_run_count": 0,
                    "reused_signal_run_count": 0,
                    "group_count_by_type": group_count_by_type,
                    "warnings": warnings,
                }

            try:
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
            except sqlite3.Error as exc:
                target_conn.rollback()
                return {
                    "status": "FAILED",
                    "loader_status": "FAILED",
                    "loader_error_code": "SQL_INSERT_FAILED",
                    "loader_error": str(exc),
                    "synthetic_loader_error": str(exc),
                    "ecosystem_code": ecosystem_code,
                    "taxonomy_version_code": taxonomy_version_code,
                    "signal_date": selected_signal_date,
                    "ohlc_calc_version": selected_ohlc_calc_version,
                    "source_table": REQUIRED_SOURCE_TABLE,
                    **source_validation,
                    "loaded_row_count": 0,
                    "failed_row_count": len(rows),
                    "mapped_row_count": len(pending_rows),
                    **target_key_validation,
                    "unresolved_group_count": 0,
                    "unresolved_groups": [],
                    "unmapped_source_columns": list(EXPECTED_UNMAPPED_SOURCE_COLUMNS),
                    "unmapped_target_columns": list(EXPECTED_UNMAPPED_TARGET_COLUMNS),
                    "missing_group_entities": [],
                    "missing_group_aliases": [],
                    "multiple_group_matches": [],
                    "source_run_ids": source_run_ids,
                    "created_signal_run_count": 0,
                    "reused_signal_run_count": 0,
                    "group_count_by_type": group_count_by_type,
                    "warnings": warnings,
                }

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
            "ohlc_calc_version": selected_ohlc_calc_version,
            "source_table": REQUIRED_SOURCE_TABLE,
            **source_validation,
            "loaded_row_count": len(rows),
            "failed_row_count": 0,
            "loader_status": status,
            "loader_error_code": "NONE",
            "loader_error": None,
            "synthetic_loader_error": None,
            "mapped_row_count": len(pending_rows),
            **target_key_validation,
            "unresolved_group_count": 0,
            "unresolved_groups": [],
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
