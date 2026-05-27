from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SOURCE_TABLE = "dc_group_swing_signal_daily"
OPTIONAL_SYNTHETIC_TABLE = "dc_group_synthetic_ohlc_daily"
OPTIONAL_INDEX_TABLE = "dc_group_index_daily"
OPTIONAL_TICKER_SOURCE_TABLE = "dc_ticker_swing_signal_daily"
DESTINATION_TABLE = "dc_dashboard_group_enrichment_daily"
CALC_VERSION = "DATACENTER_DASHBOARD_GROUP_ENRICHMENT_V1"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write Datacenter group enrichment rows into analysis.db."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("insert-missing", "upsert", "replace-date"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_run_id(signal_date: str, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return f"DC_DASH_GROUP_ENRICH_{signal_date}_{_utc_now_text()}"


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_read_write(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(normalized)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _normalize_signal_date(value: str) -> str:
    normalized = value.strip()
    parts = normalized.split("-")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid signal_date format: {normalized}")
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(f"invalid signal_date format: {normalized}")
    return normalized


def _normalize_taxonomy_version(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("taxonomy_version must be non-empty")
    return normalized


def _resolve_latest_version(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    version_column: str,
    signal_date: str,
    taxonomy_version: str,
) -> str | None:
    columns = _table_columns(conn, table_name)
    if version_column not in columns:
        return None
    row = conn.execute(
        f"""
        SELECT {version_column}
        FROM {table_name}
        WHERE {date_column} = ? AND taxonomy_version = ?
        ORDER BY {version_column} DESC
        LIMIT 1
        """,
        (signal_date, taxonomy_version),
    ).fetchone()
    if row is None or row[0] in {None, ""}:
        return None
    return str(row[0])


def _load_swing_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> list[sqlite3.Row]:
    columns = _table_columns(conn, SOURCE_TABLE)
    signal_version = _resolve_latest_version(
        conn,
        table_name=SOURCE_TABLE,
        date_column="signal_date",
        version_column="signal_version",
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
    )
    if "signal_version" in columns and signal_version is not None:
        return list(
            conn.execute(
                f"""
                SELECT
                    signal_date,
                    taxonomy_version,
                    group_type,
                    group_name,
                    timing_state,
                    overheat_risk_level,
                    pct_above_ema20,
                    pct_above_ma10,
                    ema20_breadth_delta_5d,
                    return_5d,
                    return_10d,
                    return_20d,
                    return_60d,
                    data_quality_status,
                    run_id
                FROM {SOURCE_TABLE}
                WHERE signal_date = ? AND taxonomy_version = ? AND signal_version = ?
                ORDER BY group_type ASC, group_name ASC
                """,
                (signal_date, taxonomy_version, signal_version),
            ).fetchall()
        )
    return list(
        conn.execute(
            f"""
            SELECT
                signal_date,
                taxonomy_version,
                group_type,
                group_name,
                timing_state,
                overheat_risk_level,
                pct_above_ema20,
                pct_above_ma10,
                ema20_breadth_delta_5d,
                return_5d,
                return_10d,
                return_20d,
                return_60d,
                data_quality_status,
                run_id
            FROM {SOURCE_TABLE}
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY group_type ASC, group_name ASC
            """,
            (signal_date, taxonomy_version),
        ).fetchall()
    )


def _load_optional_rows(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    version_column: str,
    signal_date: str,
    taxonomy_version: str,
    selected_fields: tuple[str, ...],
) -> dict[tuple[str, str], sqlite3.Row]:
    if not _table_exists(conn, table_name):
        return {}
    columns = _table_columns(conn, table_name)
    version = _resolve_latest_version(
        conn,
        table_name=table_name,
        date_column=date_column,
        version_column=version_column,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
    )
    where_sql = f"{date_column} = ? AND taxonomy_version = ?"
    params: list[object] = [signal_date, taxonomy_version]
    if version_column in columns and version is not None:
        where_sql += f" AND {version_column} = ?"
        params.append(version)
    rows = conn.execute(
        f"""
        SELECT group_type, group_name, {", ".join(selected_fields)}
        FROM {table_name}
        WHERE {where_sql}
        ORDER BY group_type ASC, group_name ASC
        """,
        tuple(params),
    ).fetchall()
    return {(str(row["group_type"]).strip(), str(row["group_name"]).strip()): row for row in rows}


def _market_level(group_type: object) -> str:
    normalized = str(group_type or "").strip()
    lowered = normalized.lower()
    if lowered in {"ecosystem", "total"}:
        return "ECOSYSTEM"
    if lowered == "layer":
        return "LAYER"
    if lowered == "subindustry":
        return "SUBINDUSTRY"
    return normalized.upper()


def _load_subindustry_to_layer(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> dict[str, str]:
    if not _table_exists(conn, OPTIONAL_TICKER_SOURCE_TABLE):
        return {}
    columns = _table_columns(conn, OPTIONAL_TICKER_SOURCE_TABLE)
    required_columns = {"primary_layer", "primary_subindustry", "signal_date", "taxonomy_version"}
    if not required_columns.issubset(columns):
        return {}

    signal_version = _resolve_latest_version(
        conn,
        table_name=OPTIONAL_TICKER_SOURCE_TABLE,
        date_column="signal_date",
        version_column="signal_version",
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
    )
    where_sql = "signal_date = ? AND taxonomy_version = ?"
    params: list[object] = [signal_date, taxonomy_version]
    if "signal_version" in columns and signal_version is not None:
        where_sql += " AND signal_version = ?"
        params.append(signal_version)

    rows = conn.execute(
        f"""
        SELECT primary_layer, primary_subindustry
        FROM {OPTIONAL_TICKER_SOURCE_TABLE}
        WHERE {where_sql}
        ORDER BY primary_subindustry ASC, primary_layer ASC
        """,
        tuple(params),
    ).fetchall()

    candidates: dict[str, set[str]] = {}
    for row in rows:
        layer = str(row["primary_layer"] or "").strip()
        subindustry = str(row["primary_subindustry"] or "").strip()
        if not layer or not subindustry:
            continue
        candidates.setdefault(subindustry, set()).add(layer)

    return {
        subindustry: next(iter(layers))
        for subindustry, layers in candidates.items()
        if len(layers) == 1
    }


def _group_identity(
    row: sqlite3.Row,
    *,
    subindustry_to_layer: dict[str, str],
) -> tuple[str, str, str, str | None, str | None, str | None, str]:
    market_level = _market_level(row["group_type"])
    name = str(row["group_name"]).strip()
    if market_level == "ECOSYSTEM":
        return (
            market_level,
            "DC_ECOSYSTEM_TOTAL",
            "ECOSYSTEM|DC_ECOSYSTEM_TOTAL",
            None,
            None,
            None,
            "DC_ECOSYSTEM_TOTAL",
        )
    if market_level == "LAYER":
        return (
            market_level,
            name,
            f"LAYER|{name}",
            "DC_ECOSYSTEM_TOTAL",
            name,
            None,
            f"DC_ECOSYSTEM_TOTAL > {name}",
        )
    if market_level == "SUBINDUSTRY":
        layer_name = subindustry_to_layer.get(name)
        if layer_name:
            return (
                market_level,
                name,
                f"SUBINDUSTRY|{layer_name}|{name}",
                layer_name,
                layer_name,
                name,
                f"DC_ECOSYSTEM_TOTAL > {layer_name} > {name}",
            )
        return (
            market_level,
            name,
            f"SUBINDUSTRY|{name}",
            None,
            None,
            name,
            f"SUBINDUSTRY|{name}",
        )
    return (
        market_level,
        name,
        f"{market_level}|{name}",
        None,
        None,
        None,
        f"{market_level}|{name}",
    )


def _map_destination_row(
    row: sqlite3.Row,
    *,
    subindustry_to_layer: dict[str, str],
    synthetic_row: sqlite3.Row | None,
    index_row: sqlite3.Row | None,
    use_index_daily: bool,
    source_run_ids: str | None,
    source_components: str,
    run_id: str,
    created_at_utc: str,
) -> tuple[object, ...]:
    market_level, name, taxonomy_key, parent_name, layer, subindustry, taxonomy_path = _group_identity(
        row,
        subindustry_to_layer=subindustry_to_layer,
    )
    values = [
        row["signal_date"],
        row["taxonomy_version"],
        market_level,
        taxonomy_key,
        name,
        parent_name,
        layer,
        subindustry,
        taxonomy_path,
        row["timing_state"],
        None,
        None,
        None,
        None,
        None,
        None,
        row["overheat_risk_level"],
        row["pct_above_ema20"],
        row["pct_above_ma10"],
        row["ema20_breadth_delta_5d"],
        row["return_5d"],
        row["return_10d"],
        row["return_20d"] if row["return_20d"] is not None else (
            index_row["return_20d"] if use_index_daily and index_row is not None else None
        ),
        row["return_60d"] if row["return_60d"] is not None else (
            index_row["return_60d"] if use_index_daily and index_row is not None else None
        ),
        synthetic_row["trend_classification"] if synthetic_row is not None else None,
        None,
        synthetic_row["latest_structure_label"] if synthetic_row is not None else None,
        synthetic_row["latest_structure_age_trading_days"] if synthetic_row is not None else None,
        synthetic_row["latest_bos_event_type"] if synthetic_row is not None else None,
        synthetic_row["latest_bos_age_trading_days"] if synthetic_row is not None else None,
        synthetic_row["latest_reset_reason"] if synthetic_row is not None else None,
        synthetic_row["latest_reset_age_trading_days"] if synthetic_row is not None else None,
        None,
        None,
        None,
        None,
        None,
        None,
        "daily",
        source_run_ids,
        source_components,
        row["data_quality_status"],
        CALC_VERSION,
        run_id,
        created_at_utc,
    ]
    assert len(values) == 45
    return tuple(values)


def _existing_keys(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> set[tuple[str, str, str, str]]:
    rows = conn.execute(
        f"""
        SELECT signal_date, taxonomy_version, market_level, taxonomy_key
        FROM {DESTINATION_TABLE}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    ).fetchall()
    return {
        (
            str(row["signal_date"]),
            str(row["taxonomy_version"]),
            str(row["market_level"]),
            str(row["taxonomy_key"]),
        )
        for row in rows
    }


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_group_enrichment_write.{name}={value}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        signal_date = _normalize_signal_date(args.signal_date)
        taxonomy_version = _normalize_taxonomy_version(args.taxonomy_version)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")

        connector = _connect_read_only if args.dry_run else _connect_read_write
        with connector(args.analysis_db) as conn:
            if not _table_exists(conn, SOURCE_TABLE):
                raise ValueError(f"missing required source table: {SOURCE_TABLE}")
            if not _table_exists(conn, DESTINATION_TABLE):
                raise ValueError(f"missing required destination table: {DESTINATION_TABLE}")

            synthetic_exists = _table_exists(conn, OPTIONAL_SYNTHETIC_TABLE)
            index_exists = _table_exists(conn, OPTIONAL_INDEX_TABLE)

            source_rows = _load_swing_rows(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            valid_rows_all = list(source_rows)
            valid_rows = valid_rows_all[: args.limit] if args.limit is not None else valid_rows_all

            synthetic_rows = _load_optional_rows(
                conn,
                table_name=OPTIONAL_SYNTHETIC_TABLE,
                date_column="ohlc_date",
                version_column="calc_version",
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                selected_fields=(
                    "trend_classification",
                    "latest_structure_label",
                    "latest_structure_age_trading_days",
                    "latest_bos_event_type",
                    "latest_bos_age_trading_days",
                    "latest_reset_reason",
                    "latest_reset_age_trading_days",
                    "run_id",
                ),
            )
            index_rows = _load_optional_rows(
                conn,
                table_name=OPTIONAL_INDEX_TABLE,
                date_column="index_date",
                version_column="calc_version",
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                selected_fields=("return_20d", "return_60d", "run_id"),
            )
            subindustry_to_layer = _load_subindustry_to_layer(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )

            run_id = _resolve_run_id(signal_date, args.run_id)
            created_at_utc = _utc_now_text()
            existing_keys = _existing_keys(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )

            row_specs: list[tuple[tuple[str, str, str, str], tuple[object, ...], bool, bool]] = []
            used_synthetic_ohlc = 0
            used_index_daily = 0
            unknown_subindustry_layer_count = 0
            for row in valid_rows:
                group_type = str(row["group_type"]).strip()
                group_name = str(row["group_name"]).strip()
                synthetic_row = synthetic_rows.get((group_type, group_name))
                index_row = index_rows.get((group_type, group_name))
                use_index_for_row = bool(
                    index_row is not None
                    and (
                        row["return_20d"] is None
                        or row["return_60d"] is None
                    )
                )
                used_run_ids = []
                if row["run_id"] not in {None, ""}:
                    used_run_ids.append(str(row["run_id"]))
                if synthetic_row is not None and synthetic_row["run_id"] not in {None, ""}:
                    used_run_ids.append(str(synthetic_row["run_id"]))
                if use_index_for_row and index_row is not None and index_row["run_id"] not in {None, ""}:
                    used_run_ids.append(str(index_row["run_id"]))
                source_components = ["dc_group_swing_signal_daily"]
                if synthetic_row is not None:
                    source_components.append("dc_group_synthetic_ohlc_daily")
                    used_synthetic_ohlc = 1
                if use_index_for_row:
                    source_components.append("dc_group_index_daily")
                    used_index_daily = 1
                market_level, name, taxonomy_key, _, _, _, _ = _group_identity(
                    row,
                    subindustry_to_layer=subindustry_to_layer,
                )
                if market_level == "SUBINDUSTRY" and group_name not in subindustry_to_layer:
                    unknown_subindustry_layer_count += 1
                row_specs.append(
                    (
                        (
                            str(row["signal_date"]),
                            str(row["taxonomy_version"]),
                            market_level,
                            taxonomy_key,
                        ),
                        _map_destination_row(
                            row,
                            subindustry_to_layer=subindustry_to_layer,
                            synthetic_row=synthetic_row,
                            index_row=index_row,
                            use_index_daily=use_index_for_row,
                            source_run_ids=(
                                ",".join(sorted(set(used_run_ids))) if used_run_ids else None
                            ),
                            source_components=",".join(source_components),
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                        ),
                        synthetic_row is not None,
                        use_index_for_row,
                    )
                )

            selected_keys = {item[0] for item in row_specs}
            inserted_rows = 0
            updated_rows = 0
            deleted_existing_rows = 0
            skipped_existing_rows = 0

            if args.mode == "insert-missing":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                skipped_existing_rows = sum(1 for key in selected_keys if key in existing_keys)
                rows_to_write = [values for key, values, _, _ in row_specs if key not in existing_keys]
                if not args.dry_run and rows_to_write:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            market_level,
                            taxonomy_key,
                            name,
                            parent_name,
                            layer,
                            subindustry,
                            taxonomy_path,
                            current_status,
                            start_status_30d,
                            status_change_30d,
                            status_change_5d,
                            window_status_30d,
                            window_status_5d,
                            window_status_2d,
                            overheat_risk,
                            pct_above_ema20,
                            pct_above_ma10,
                            ema20_breadth_delta_5d,
                            return_5d,
                            return_10d,
                            return_20d,
                            return_60d,
                            dow_trend_state,
                            dow_trend_state_age_td,
                            latest_structure_label,
                            latest_structure_age_td,
                            latest_bos_event_type,
                            latest_bos_age_td,
                            latest_reset_reason,
                            latest_reset_age_td,
                            latest_candle,
                            latest_candle_age_td,
                            latest_divergence,
                            latest_divergence_age_td,
                            latest_chart_pattern,
                            latest_chart_pattern_age_td,
                            source_horizons,
                            source_run_ids,
                            source_components,
                            data_quality_status,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows_to_write,
                    )
            elif args.mode == "upsert":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                updated_rows = sum(1 for key in selected_keys if key in existing_keys)
                if not args.dry_run and row_specs:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            market_level,
                            taxonomy_key,
                            name,
                            parent_name,
                            layer,
                            subindustry,
                            taxonomy_path,
                            current_status,
                            start_status_30d,
                            status_change_30d,
                            status_change_5d,
                            window_status_30d,
                            window_status_5d,
                            window_status_2d,
                            overheat_risk,
                            pct_above_ema20,
                            pct_above_ma10,
                            ema20_breadth_delta_5d,
                            return_5d,
                            return_10d,
                            return_20d,
                            return_60d,
                            dow_trend_state,
                            dow_trend_state_age_td,
                            latest_structure_label,
                            latest_structure_age_td,
                            latest_bos_event_type,
                            latest_bos_age_td,
                            latest_reset_reason,
                            latest_reset_age_td,
                            latest_candle,
                            latest_candle_age_td,
                            latest_divergence,
                            latest_divergence_age_td,
                            latest_chart_pattern,
                            latest_chart_pattern_age_td,
                            source_horizons,
                            source_run_ids,
                            source_components,
                            data_quality_status,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_date, taxonomy_version, market_level, taxonomy_key) DO UPDATE SET
                            name=excluded.name,
                            parent_name=excluded.parent_name,
                            layer=excluded.layer,
                            subindustry=excluded.subindustry,
                            taxonomy_path=excluded.taxonomy_path,
                            current_status=excluded.current_status,
                            start_status_30d=excluded.start_status_30d,
                            status_change_30d=excluded.status_change_30d,
                            status_change_5d=excluded.status_change_5d,
                            window_status_30d=excluded.window_status_30d,
                            window_status_5d=excluded.window_status_5d,
                            window_status_2d=excluded.window_status_2d,
                            overheat_risk=excluded.overheat_risk,
                            pct_above_ema20=excluded.pct_above_ema20,
                            pct_above_ma10=excluded.pct_above_ma10,
                            ema20_breadth_delta_5d=excluded.ema20_breadth_delta_5d,
                            return_5d=excluded.return_5d,
                            return_10d=excluded.return_10d,
                            return_20d=excluded.return_20d,
                            return_60d=excluded.return_60d,
                            dow_trend_state=excluded.dow_trend_state,
                            dow_trend_state_age_td=excluded.dow_trend_state_age_td,
                            latest_structure_label=excluded.latest_structure_label,
                            latest_structure_age_td=excluded.latest_structure_age_td,
                            latest_bos_event_type=excluded.latest_bos_event_type,
                            latest_bos_age_td=excluded.latest_bos_age_td,
                            latest_reset_reason=excluded.latest_reset_reason,
                            latest_reset_age_td=excluded.latest_reset_age_td,
                            latest_candle=excluded.latest_candle,
                            latest_candle_age_td=excluded.latest_candle_age_td,
                            latest_divergence=excluded.latest_divergence,
                            latest_divergence_age_td=excluded.latest_divergence_age_td,
                            latest_chart_pattern=excluded.latest_chart_pattern,
                            latest_chart_pattern_age_td=excluded.latest_chart_pattern_age_td,
                            source_horizons=excluded.source_horizons,
                            source_run_ids=excluded.source_run_ids,
                            source_components=excluded.source_components,
                            data_quality_status=excluded.data_quality_status,
                            calc_version=excluded.calc_version,
                            run_id=excluded.run_id,
                            created_at_utc=excluded.created_at_utc
                        """,
                        [values for _, values, _, _ in row_specs],
                    )
            else:
                deleted_existing_rows = len(existing_keys)
                inserted_rows = len(valid_rows)
                if not args.dry_run:
                    conn.execute(
                        f"""
                        DELETE FROM {DESTINATION_TABLE}
                        WHERE signal_date = ? AND taxonomy_version = ?
                        """,
                        (signal_date, taxonomy_version),
                    )
                    if row_specs:
                        conn.executemany(
                            f"""
                            INSERT INTO {DESTINATION_TABLE} (
                                signal_date,
                                taxonomy_version,
                                market_level,
                                taxonomy_key,
                                name,
                                parent_name,
                                layer,
                                subindustry,
                                taxonomy_path,
                                current_status,
                                start_status_30d,
                                status_change_30d,
                                status_change_5d,
                                window_status_30d,
                                window_status_5d,
                                window_status_2d,
                                overheat_risk,
                                pct_above_ema20,
                                pct_above_ma10,
                                ema20_breadth_delta_5d,
                                return_5d,
                                return_10d,
                                return_20d,
                                return_60d,
                                dow_trend_state,
                                dow_trend_state_age_td,
                                latest_structure_label,
                                latest_structure_age_td,
                                latest_bos_event_type,
                                latest_bos_age_td,
                                latest_reset_reason,
                                latest_reset_age_td,
                                latest_candle,
                                latest_candle_age_td,
                                latest_divergence,
                                latest_divergence_age_td,
                                latest_chart_pattern,
                                latest_chart_pattern_age_td,
                                source_horizons,
                                source_run_ids,
                                source_components,
                                data_quality_status,
                                calc_version,
                                run_id,
                                created_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [values for _, values, _, _ in row_specs],
                        )

            if not args.dry_run:
                conn.commit()

        warnings: list[str] = []
        if not synthetic_exists:
            warnings.append("SYNTHETIC_OHLC_SOURCE_MISSING")
        if not index_exists:
            warnings.append("INDEX_DAILY_SOURCE_MISSING")
        if len(source_rows) == 0:
            warnings.append("NO_GROUP_ROWS_FOR_SELECTION")

        _emit_summary("status", "OK")
        _emit_summary("analysis_db", args.analysis_db)
        _emit_summary("signal_date", signal_date)
        _emit_summary("taxonomy_version", taxonomy_version)
        _emit_summary("mode", args.mode)
        _emit_summary("dry_run", 1 if args.dry_run else 0)
        _emit_summary("source_rows", len(source_rows))
        _emit_summary("valid_group_rows", len(valid_rows))
        _emit_summary("inserted_rows", inserted_rows)
        _emit_summary("updated_rows", updated_rows)
        _emit_summary("deleted_existing_rows", deleted_existing_rows)
        _emit_summary("skipped_existing_rows", skipped_existing_rows)
        _emit_summary("run_id", run_id)
        _emit_summary("used_synthetic_ohlc", used_synthetic_ohlc)
        _emit_summary("used_index_daily", used_index_daily)
        _emit_summary("subindustry_layer_mapped_rows", len(subindustry_to_layer))
        _emit_summary("subindustry_layer_unknown_rows", unknown_subindustry_layer_count)
        for warning in warnings:
            _emit_summary("warning", warning)
        if unknown_subindustry_layer_count > 0:
            _emit_summary("warning", "SUBINDUSTRY_LAYER_UNKNOWN")
        return 0
    except (FileNotFoundError, sqlite3.Error, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
