from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.ec_ticker_signal_daily_loader import _connect_readonly, _require_table, _require_tables, _resolve_target_context


MAX_EXAMPLES = 20
REQUIRED_SOURCE_TABLES = (
    "dc_ticker_swing_signal_daily",
    "dc_group_swing_signal_daily",
    "dc_group_synthetic_ohlc_daily",
    "dc_group_index_daily",
    "dc_pipeline_watermark",
)
REQUIRED_TARGET_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_entity_alias",
    "ec_ticker_signal_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_group_index_daily",
    "ec_pipeline_watermark",
)

TICKER_ACCEPTED_UNMAPPED_TARGET_FIELDS = [
    "return_1d",
    "distance_to_sma50_pct",
    "distance_to_sma200_pct",
    "data_quality_status",
]
GROUP_SIGNAL_ACCEPTED_UNMAPPED_TARGET_FIELDS = [
    "valid_price_count",
    "return_1d",
    "return_120d",
    "pct_above_sma50",
    "pct_above_sma200",
]
SYNTH_ACCEPTED_UNMAPPED_TARGET_FIELDS = [
    "latest_structure_date",
    "structure_state",
    "relative_strength_5d",
    "relative_strength_20d",
]
GROUP_INDEX_ACCEPTED_UNMAPPED_TARGET_FIELDS = [
    "return_5d",
    "return_10d",
    "trend_breadth",
    "weakness_breadth",
    "relative_strength_20d",
]
KNOWN_COMPONENT_SOURCE_TABLES = {
    "TICKER_SWING_BASE": "dc_ticker_swing_signal_daily",
    "GROUP_SWING_BASE": "dc_group_swing_signal_daily",
    "SYNTHETIC_OHLC_BASE": "dc_group_synthetic_ohlc_daily",
    "SYNTHETIC_OHLC_RELATIVE": "dc_group_synthetic_ohlc_daily",
    "GROUP_INDEX": "dc_group_index_daily",
}


def _fetch_latest_dates(conn: sqlite3.Connection) -> dict[str, str | None]:
    return {
        "dc_ticker_swing_signal_daily": conn.execute(
            "SELECT MAX(signal_date) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0],
        "dc_group_swing_signal_daily": conn.execute(
            "SELECT MAX(signal_date) FROM dc_group_swing_signal_daily"
        ).fetchone()[0],
        "dc_group_synthetic_ohlc_daily": conn.execute(
            "SELECT MAX(ohlc_date) FROM dc_group_synthetic_ohlc_daily"
        ).fetchone()[0],
        "dc_group_index_daily": conn.execute(
            "SELECT MAX(index_date) FROM dc_group_index_daily"
        ).fetchone()[0],
    }


def _fetch_explicit_date_source_counts(conn: sqlite3.Connection, signal_date: str) -> dict[str, int]:
    return {
        "dc_ticker_swing_signal_daily": int(
            conn.execute(
                "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]
        ),
        "dc_group_swing_signal_daily": int(
            conn.execute(
                "SELECT COUNT(*) FROM dc_group_swing_signal_daily WHERE signal_date = ?",
                (signal_date,),
            ).fetchone()[0]
        ),
        "dc_group_synthetic_ohlc_daily": int(
            conn.execute(
                "SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily WHERE ohlc_date = ?",
                (signal_date,),
            ).fetchone()[0]
        ),
        "dc_group_index_daily": int(
            conn.execute(
                "SELECT COUNT(*) FROM dc_group_index_daily WHERE index_date = ?",
                (signal_date,),
            ).fetchone()[0]
        ),
    }


def _resolve_aligned_signal_date(
    conn: sqlite3.Connection,
    signal_date: str | None,
) -> tuple[str | None, dict[str, str | None], str]:
    latest_dates = _fetch_latest_dates(conn)
    if signal_date is not None:
        explicit_counts = _fetch_explicit_date_source_counts(conn, signal_date)
        if all(row_count > 0 for row_count in explicit_counts.values()):
            return signal_date, latest_dates, "EXPLICIT_DATE_ALIGNED"
        return None, latest_dates, "EXPLICIT_DATE_MISSING_SOURCE_ROWS"

    selected_values = {value for value in latest_dates.values() if value is not None}
    if len(selected_values) != 1:
        return None, latest_dates, "MISMATCH"
    selected_signal_date = next(iter(selected_values))
    if any(value != selected_signal_date for value in latest_dates.values()):
        return None, latest_dates, "MISMATCH"
    return str(selected_signal_date), latest_dates, "OK"


def _to_key_dict(key_fields: tuple[str, ...], key: tuple[object, ...]) -> dict[str, object]:
    return {field: value for field, value in zip(key_fields, key)}


def _row_key(row: sqlite3.Row, key_fields: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(row[field] for field in key_fields)


def _compare_value(
    source_value: object,
    target_value: object,
    *,
    numeric_tolerance: float,
    is_numeric: bool,
) -> bool:
    if source_value is None and target_value is None:
        return True
    if source_value is None or target_value is None:
        return False
    if is_numeric:
        return abs(float(source_value) - float(target_value)) <= numeric_tolerance
    return source_value == target_value


def _build_section_result(
    *,
    section_name: str,
    source_rows: dict[tuple[object, ...], sqlite3.Row],
    target_rows: dict[tuple[object, ...], sqlite3.Row],
    key_fields: tuple[str, ...],
    numeric_fields: list[tuple[str, str]],
    text_fields: list[tuple[str, str]],
    extra_checks: list[tuple[str, callable]],
    accepted_unmapped_target_fields: list[str],
    numeric_tolerance: float,
) -> dict[str, object]:
    source_keys = set(source_rows)
    target_keys = set(target_rows)
    missing_in_target = sorted(source_keys - target_keys)
    extra_in_target = sorted(target_keys - source_keys)
    target_available_fields: set[str] = set()
    if target_rows:
        target_available_fields = set(next(iter(target_rows.values())).keys())

    filtered_numeric_fields: list[tuple[str, str]] = []
    filtered_text_fields: list[tuple[str, str]] = []
    skipped_target_fields: list[str] = []
    for source_field, target_field in numeric_fields:
        if target_field in target_available_fields:
            filtered_numeric_fields.append((source_field, target_field))
        else:
            skipped_target_fields.append(target_field)
    for source_field, target_field in text_fields:
        if target_field in target_available_fields:
            filtered_text_fields.append((source_field, target_field))
        else:
            skipped_target_fields.append(target_field)

    field_mismatch_examples: list[dict[str, object]] = []
    field_mismatch_count = 0

    def add_mismatch(key: tuple[object, ...], field: str, source_value: object, target_value: object) -> None:
        nonlocal field_mismatch_count
        field_mismatch_count += 1
        if len(field_mismatch_examples) < MAX_EXAMPLES:
            field_mismatch_examples.append(
                {
                    "key": _to_key_dict(key_fields, key),
                    "field": field,
                    "source": source_value,
                    "target": target_value,
                }
            )

    for key in sorted(source_keys & target_keys):
        source_row = source_rows[key]
        target_row = target_rows[key]

        for source_field, target_field in filtered_numeric_fields:
            if not _compare_value(
                source_row[source_field],
                target_row[target_field],
                numeric_tolerance=numeric_tolerance,
                is_numeric=True,
            ):
                add_mismatch(key, target_field, source_row[source_field], target_row[target_field])

        for source_field, target_field in filtered_text_fields:
            if not _compare_value(
                source_row[source_field],
                target_row[target_field],
                numeric_tolerance=numeric_tolerance,
                is_numeric=False,
            ):
                add_mismatch(key, target_field, source_row[source_field], target_row[target_field])

        for field_name, checker in extra_checks:
            source_value, target_value, ok = checker(source_row, target_row)
            if not ok:
                add_mismatch(key, field_name, source_value, target_value)

    warnings = []
    if accepted_unmapped_target_fields:
        warnings.append(
            f"Accepted unmapped target fields: {', '.join(accepted_unmapped_target_fields)}"
        )
    if skipped_target_fields:
        warnings.append(
            "Skipped parity fields absent from target schema: "
            + ", ".join(sorted(set(skipped_target_fields)))
        )

    status = "FAILED" if (missing_in_target or extra_in_target or field_mismatch_count) else (
        "OK_WITH_WARNINGS" if warnings else "OK"
    )

    return {
        "status": status,
        "source_row_count": len(source_rows),
        "target_row_count": len(target_rows),
        "missing_in_target": [_to_key_dict(key_fields, key) for key in missing_in_target[:MAX_EXAMPLES]],
        "extra_in_target": [_to_key_dict(key_fields, key) for key in extra_in_target[:MAX_EXAMPLES]],
        "field_mismatch_count": field_mismatch_count,
        "field_mismatch_examples": field_mismatch_examples,
        "accepted_unmapped_target_fields": accepted_unmapped_target_fields,
        "warnings": warnings,
    }


def _non_empty(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _normalized_string_equal(source_value: object, target_value: object) -> bool:
    if source_value is None and target_value is None:
        return True
    if source_value is None or target_value is None:
        return False
    return str(source_value) == str(target_value)


def _lineage_checker(expected_source_table: str, source_run_field: str = "run_id") -> list[tuple[str, callable]]:
    return [
        (
            "source_table",
            lambda source_row, target_row: (
                expected_source_table,
                target_row["source_table"],
                target_row["source_table"] == expected_source_table,
            ),
        ),
        (
            "source_pk_json",
            lambda source_row, target_row: (
                "NON_EMPTY",
                target_row["source_pk_json"],
                _non_empty(target_row["source_pk_json"]),
            ),
        ),
        (
            "source_row_hash",
            lambda source_row, target_row: (
                "NON_EMPTY",
                target_row["source_row_hash"],
                _non_empty(target_row["source_row_hash"]),
            ),
        ),
        (
            "source_run_id",
            lambda source_row, target_row: (
                source_row[source_run_field],
                target_row["source_run_id"],
                source_row[source_run_field] == target_row["source_run_id"],
            ),
        ),
    ]


def _fetch_ticker_source_rows(conn: sqlite3.Connection, signal_date: str) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date = ?
        ORDER BY ticker, signal_version
        """,
        (signal_date,),
    ).fetchall()
    key_fields = ("ticker", "signal_date", "signal_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_ticker_target_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM ec_ticker_signal_daily
        WHERE ecosystem_id = ?
          AND taxonomy_version_id = ?
          AND signal_date = ?
        ORDER BY ticker, signal_version
        """,
        (ecosystem_id, taxonomy_version_id, signal_date),
    ).fetchall()
    key_fields = ("ticker", "signal_date", "signal_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_group_signal_source_rows(conn: sqlite3.Connection, signal_date: str) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_swing_signal_daily
        WHERE signal_date = ?
        ORDER BY group_type, group_name, signal_version
        """,
        (signal_date,),
    ).fetchall()
    key_fields = ("group_type", "group_name", "signal_date", "signal_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_group_signal_target_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT t.*,
               CASE
                   WHEN t.entity_type = 'ECOSYSTEM' THEN 'ecosystem'
                   WHEN t.entity_type = 'GROUP_L1' THEN 'layer'
                   WHEN t.entity_type = 'GROUP_L2' THEN 'subindustry'
               END AS group_type,
               CASE
                   WHEN t.entity_type = 'ECOSYSTEM' THEN a.alias_value
                   ELSE e.entity_name
               END AS group_name
        FROM ec_group_signal_daily t
        JOIN ec_entity e ON e.entity_id = t.entity_id
        LEFT JOIN ec_entity_alias a
          ON a.entity_id = e.entity_id
         AND a.alias_type = 'DC_GROUP_NAME'
         AND a.source_system = 'dc_group_facts'
        WHERE t.ecosystem_id = ?
          AND t.taxonomy_version_id = ?
          AND t.signal_date = ?
        ORDER BY group_type, group_name, signal_version
        """,
        (ecosystem_id, taxonomy_version_id, signal_date),
    ).fetchall()
    key_fields = ("group_type", "group_name", "signal_date", "signal_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_synth_source_rows(conn: sqlite3.Connection, signal_date: str) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_synthetic_ohlc_daily
        WHERE ohlc_date = ?
        ORDER BY group_type, group_name, calc_version
        """,
        (signal_date,),
    ).fetchall()
    key_fields = ("group_type", "group_name", "ohlc_date", "calc_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_synth_target_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT t.*,
               CASE
                   WHEN t.entity_type = 'GROUP_L1' THEN 'layer'
                   WHEN t.entity_type = 'GROUP_L2' THEN 'subindustry'
               END AS group_type,
               e.entity_name AS group_name,
               t.signal_date AS ohlc_date,
               t.ohlc_calc_version AS calc_version
        FROM ec_group_synthetic_ohlc_daily t
        JOIN ec_entity e ON e.entity_id = t.entity_id
        WHERE t.ecosystem_id = ?
          AND t.taxonomy_version_id = ?
          AND t.signal_date = ?
        ORDER BY group_type, group_name, calc_version
        """,
        (ecosystem_id, taxonomy_version_id, signal_date),
    ).fetchall()
    key_fields = ("group_type", "group_name", "ohlc_date", "calc_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_group_index_source_rows(conn: sqlite3.Connection, signal_date: str) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_group_index_daily
        WHERE index_date = ?
        ORDER BY group_type, group_name, calc_version
        """,
        (signal_date,),
    ).fetchall()
    key_fields = ("group_type", "group_name", "index_date", "calc_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_group_index_target_rows(
    conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT t.*,
               CASE
                   WHEN t.entity_type = 'ECOSYSTEM' THEN 'ecosystem'
                   WHEN t.entity_type = 'GROUP_L1' THEN 'layer'
                   WHEN t.entity_type = 'GROUP_L2' THEN 'subindustry'
               END AS group_type,
               CASE
                   WHEN t.entity_type = 'ECOSYSTEM' THEN a.alias_value
                   ELSE e.entity_name
               END AS group_name,
               t.signal_date AS index_date
        FROM ec_group_index_daily t
        JOIN ec_entity e ON e.entity_id = t.entity_id
        LEFT JOIN ec_entity_alias a
          ON a.entity_id = e.entity_id
         AND a.alias_type = 'DC_GROUP_NAME'
         AND a.source_system = 'dc_group_facts'
        WHERE t.ecosystem_id = ?
          AND t.taxonomy_version_id = ?
          AND t.signal_date = ?
        ORDER BY group_type, group_name, calc_version
        """,
        (ecosystem_id, taxonomy_version_id, signal_date),
    ).fetchall()
    key_fields = ("group_type", "group_name", "index_date", "calc_version")
    return {_row_key(row, key_fields): row for row in rows}


def _fetch_watermark_source_rows(
    conn: sqlite3.Connection,
    taxonomy_version_code: str,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM dc_pipeline_watermark
        WHERE taxonomy_version = ?
        ORDER BY component_name, market, signal_version, calc_version
        """,
        (taxonomy_version_code,),
    ).fetchall()
    mapped_rows: dict[tuple[object, ...], sqlite3.Row] = {}
    for row in rows:
        component_name = str(row["component_name"])
        source_table = KNOWN_COMPONENT_SOURCE_TABLES.get(component_name, f"UNKNOWN:{component_name}")
        mapped_rows[(component_name, source_table)] = row
    return mapped_rows


def _fetch_watermark_target_rows(
    conn: sqlite3.Connection,
    ecosystem_id: int,
) -> dict[tuple[object, ...], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM ec_pipeline_watermark
        WHERE ecosystem_id = ?
        ORDER BY pipeline_name, source_table
        """,
        (ecosystem_id,),
    ).fetchall()
    return {(row["pipeline_name"], row["source_table"]): row for row in rows}


def _ticker_parity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    numeric_tolerance: float,
) -> dict[str, object]:
    source_rows = _fetch_ticker_source_rows(source_conn, signal_date)
    target_rows = _fetch_ticker_target_rows(
        target_conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
    )
    return _build_section_result(
        section_name="ticker",
        source_rows=source_rows,
        target_rows=target_rows,
        key_fields=("ticker", "signal_date", "signal_version"),
        numeric_fields=[
            ("close", "close"),
            ("volume", "volume"),
            ("return_5d", "return_5d"),
            ("return_10d", "return_10d"),
            ("return_20d", "return_20d"),
            ("return_60d", "return_60d"),
            ("ma10", "ma10"),
            ("ema10", "ema10"),
            ("ema20", "ema20"),
            ("distance_to_ma10_pct", "distance_to_ma10_pct"),
            ("distance_to_ema10_pct", "distance_to_ema10_pct"),
            ("distance_to_ema20_pct", "distance_to_ema20_pct"),
            ("highest_close_20d", "highest_close_20d"),
            ("volume_avg_20d", "volume_avg_20d"),
            ("volume_vs_avg20", "volume_vs_avg20"),
            ("above_ma10", "above_ma10"),
            ("above_ema10", "above_ema10"),
            ("above_ema20", "above_ema20"),
            ("ema10_slope_positive", "ema10_slope_positive"),
            ("ema20_slope_positive", "ema20_slope_positive"),
            ("ema10_slope_lookback", "ema10_slope_lookback"),
            ("ema20_slope_lookback", "ema20_slope_lookback"),
            ("breakout_signal", "breakout_signal"),
            ("pullback_signal", "pullback_signal"),
            ("exit_risk_signal", "exit_risk_signal"),
            ("bullish_divergence_signal", "bullish_divergence_signal"),
            ("bearish_divergence_signal", "bearish_divergence_signal"),
            ("hidden_bullish_divergence_signal", "hidden_bullish_divergence_signal"),
            ("hidden_bearish_divergence_signal", "hidden_bearish_divergence_signal"),
            ("bullish_candle_signal", "bullish_candle_signal"),
            ("bearish_candle_signal", "bearish_candle_signal"),
            ("latest_structure_age_trading_days", "latest_structure_age_trading_days"),
            ("latest_bos_age_trading_days", "latest_bos_age_trading_days"),
            ("latest_reset_age_trading_days", "latest_reset_age_trading_days"),
        ],
        text_fields=[
            ("ticker_trend_state", "ticker_trend_state"),
            ("latest_structure_label", "latest_structure_label"),
            ("latest_structure_confirmed_as_of_date", "latest_structure_date"),
            ("latest_structure_freshness", "latest_structure_freshness"),
            ("latest_bos_event_type", "latest_bos_event_type"),
            ("latest_bos_event_date", "latest_bos_date"),
            ("latest_bos_confirmed_as_of_date", "latest_bos_confirmed_as_of_date"),
            ("latest_bos_freshness", "latest_bos_freshness"),
            ("latest_reset_reason", "latest_reset_reason"),
            ("latest_reset_event_date", "latest_reset_date"),
            ("latest_reset_confirmed_as_of_date", "latest_reset_confirmed_as_of_date"),
            ("latest_reset_freshness", "latest_reset_freshness"),
            ("exit_risk_severity", "exit_risk_severity"),
            ("exit_reason", "exit_reason"),
            ("price_data_status", "price_data_status"),
        ],
        extra_checks=_lineage_checker("dc_ticker_swing_signal_daily")
        + [
            (
                "structure_epoch_id",
                lambda source_row, target_row: (
                    source_row["structure_epoch_id"],
                    target_row["structure_epoch_id"],
                    _normalized_string_equal(source_row["structure_epoch_id"], target_row["structure_epoch_id"]),
                ),
            )
        ],
        accepted_unmapped_target_fields=TICKER_ACCEPTED_UNMAPPED_TARGET_FIELDS,
        numeric_tolerance=numeric_tolerance,
    )


def _group_signal_parity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    numeric_tolerance: float,
) -> dict[str, object]:
    source_rows = _fetch_group_signal_source_rows(source_conn, signal_date)
    target_rows = _fetch_group_signal_target_rows(
        target_conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
    )
    result = _build_section_result(
        section_name="group_signal",
        source_rows=source_rows,
        target_rows=target_rows,
        key_fields=("group_type", "group_name", "signal_date", "signal_version"),
        numeric_fields=[
            ("member_count", "member_count"),
            ("eligible_count", "eligible_count"),
            ("return_5d", "return_5d"),
            ("return_10d", "return_10d"),
            ("return_20d", "return_20d"),
            ("return_60d", "return_60d"),
            ("pct_above_ma10", "pct_above_ma10"),
            ("pct_above_ema20", "pct_above_ema20"),
            ("pct_above_rising_ema20", "pct_above_rising_ema20"),
            ("ma10_breadth_delta_5d", "ma10_breadth_delta_5d"),
            ("ema20_breadth_delta_5d", "ema20_breadth_delta_5d"),
            ("trend_breadth", "trend_breadth"),
            ("weakness_breadth", "weakness_breadth"),
        ],
        text_fields=[
            ("timing_state", "timing_state"),
            ("timing_reason", "timing_reason"),
            ("overheat_risk_level", "overheat_risk_level"),
            ("data_quality_status", "data_quality_status"),
        ],
        extra_checks=_lineage_checker("dc_group_swing_signal_daily"),
        accepted_unmapped_target_fields=GROUP_SIGNAL_ACCEPTED_UNMAPPED_TARGET_FIELDS,
        numeric_tolerance=numeric_tolerance,
    )
    source_type_counts: dict[str, int] = {}
    target_type_counts: dict[str, int] = {}
    for key in source_rows:
        source_type_counts[str(key[0])] = source_type_counts.get(str(key[0]), 0) + 1
    for key in target_rows:
        target_type_counts[str(key[0])] = target_type_counts.get(str(key[0]), 0) + 1
    result["source_group_type_counts"] = source_type_counts
    result["target_group_type_counts"] = target_type_counts
    if source_type_counts != target_type_counts:
        result["field_mismatch_count"] += 1
        if len(result["field_mismatch_examples"]) < MAX_EXAMPLES:
            result["field_mismatch_examples"].append(
                {
                    "key": {"section": "group_type_counts"},
                    "field": "group_type_counts",
                    "source": source_type_counts,
                    "target": target_type_counts,
                }
            )
        result["status"] = "FAILED"
    return result


def _synthetic_ohlc_parity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    numeric_tolerance: float,
) -> dict[str, object]:
    source_rows = _fetch_synth_source_rows(source_conn, signal_date)
    target_rows = _fetch_synth_target_rows(
        target_conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
    )
    return _build_section_result(
        section_name="synthetic_ohlc",
        source_rows=source_rows,
        target_rows=target_rows,
        key_fields=("group_type", "group_name", "ohlc_date", "calc_version"),
        numeric_fields=[
            ("member_count", "member_count"),
            ("eligible_count", "eligible_count"),
            ("synthetic_open", "synthetic_open"),
            ("synthetic_high", "synthetic_high"),
            ("synthetic_low", "synthetic_low"),
            ("synthetic_close", "synthetic_close"),
            ("synthetic_volume", "synthetic_volume"),
            ("ma20", "ma20"),
            ("ema20", "ema20"),
            ("distance_to_ema20_pct", "distance_to_ema20_pct"),
            ("volatility_20d", "volatility_20d"),
            ("pivot_radius", "pivot_radius"),
            ("latest_pivot_high_value", "latest_pivot_high_value"),
            ("latest_pivot_low_value", "latest_pivot_low_value"),
            ("relative_base_window", "relative_base_window"),
            ("relative_open_20", "relative_open_20"),
            ("relative_high_20", "relative_high_20"),
            ("relative_low_20", "relative_low_20"),
            ("relative_close_20", "relative_close_20"),
            ("relative_upper_wick_20", "relative_upper_wick_20"),
            ("relative_lower_wick_20", "relative_lower_wick_20"),
            ("relative_close_extension_20", "relative_close_extension_20"),
            ("relative_high_extension_20", "relative_high_extension_20"),
            ("relative_low_extension_20", "relative_low_extension_20"),
            ("relative_eligible_count", "relative_eligible_count"),
            ("latest_structure_age_trading_days", "latest_structure_age_trading_days"),
            ("latest_bos_age_trading_days", "latest_bos_age_trading_days"),
            ("latest_reset_age_trading_days", "latest_reset_age_trading_days"),
        ],
        text_fields=[
            ("latest_pivot_high_date", "latest_pivot_high_date"),
            ("latest_pivot_low_date", "latest_pivot_low_date"),
            ("latest_structure_label", "latest_structure_label"),
            ("latest_structure_freshness", "structure_freshness"),
            ("latest_bos_event_type", "latest_bos_event_type"),
            ("latest_bos_event_date", "latest_bos_date"),
            ("latest_bos_confirmed_as_of_date", "latest_bos_confirmed_as_of_date"),
            ("latest_bos_freshness", "bos_freshness"),
            ("latest_reset_reason", "latest_reset_reason"),
            ("latest_reset_event_date", "latest_reset_date"),
            ("latest_reset_confirmed_as_of_date", "latest_reset_confirmed_as_of_date"),
            ("latest_reset_freshness", "reset_freshness"),
            ("trend_classification", "trend_state"),
            ("data_quality_status", "data_quality_status"),
        ],
        extra_checks=_lineage_checker("dc_group_synthetic_ohlc_daily"),
        accepted_unmapped_target_fields=SYNTH_ACCEPTED_UNMAPPED_TARGET_FIELDS,
        numeric_tolerance=numeric_tolerance,
    )


def _group_index_parity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_id: int,
    signal_date: str,
    numeric_tolerance: float,
) -> dict[str, object]:
    source_rows = _fetch_group_index_source_rows(source_conn, signal_date)
    target_rows = _fetch_group_index_target_rows(
        target_conn,
        ecosystem_id=ecosystem_id,
        taxonomy_version_id=taxonomy_version_id,
        signal_date=signal_date,
    )
    return _build_section_result(
        section_name="group_index",
        source_rows=source_rows,
        target_rows=target_rows,
        key_fields=("group_type", "group_name", "index_date", "calc_version"),
        numeric_fields=[
            ("member_count", "member_count"),
            ("eligible_count", "eligible_count"),
            ("ma50_eligible_count", "ma50_eligible_count"),
            ("ma200_eligible_count", "ma200_eligible_count"),
            ("daily_return_equal", "return_1d"),
            ("median_return", "median_return"),
            ("pct_positive", "pct_positive"),
            ("index_level_equal", "index_value"),
            ("return_20d", "return_20d"),
            ("return_60d", "return_60d"),
            ("return_120d", "return_120d"),
            ("pct_above_ma50", "pct_above_ma50"),
            ("pct_above_ma200", "pct_above_ma200"),
            ("volatility_20d", "volatility_20d"),
            ("volatility_60d", "volatility_60d"),
            ("relative_strength_spy_60d", "relative_strength_spy_60d"),
            ("relative_strength_qqq_60d", "relative_strength_qqq_60d"),
        ],
        text_fields=[
            ("data_quality_status", "data_quality_status"),
        ],
        extra_checks=_lineage_checker("dc_group_index_daily"),
        accepted_unmapped_target_fields=GROUP_INDEX_ACCEPTED_UNMAPPED_TARGET_FIELDS,
        numeric_tolerance=numeric_tolerance,
    )


def _pipeline_watermark_parity(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    ecosystem_id: int,
    taxonomy_version_code: str,
) -> dict[str, object]:
    source_rows = _fetch_watermark_source_rows(source_conn, taxonomy_version_code)
    target_rows = _fetch_watermark_target_rows(target_conn, ecosystem_id)
    key_fields = ("pipeline_name", "source_table")

    missing_in_target = sorted(set(source_rows) - set(target_rows))
    extra_in_target = sorted(set(target_rows) - set(source_rows))
    field_mismatch_examples: list[dict[str, object]] = []
    field_mismatch_count = 0
    unknown_components: list[str] = []

    for key in sorted(set(source_rows) & set(target_rows)):
        source_row = source_rows[key]
        target_row = target_rows[key]
        component_name, source_table = key
        if source_table.startswith("UNKNOWN:"):
            unknown_components.append(component_name)

        checks = [
            ("pipeline_name", component_name, target_row["pipeline_name"], component_name == target_row["pipeline_name"]),
            ("source_table", source_table, target_row["source_table"], source_table == target_row["source_table"]),
            ("latest_signal_date", source_row["end_date"], target_row["latest_signal_date"], source_row["end_date"] == target_row["latest_signal_date"]),
            ("status", source_row["status"], target_row["status"], source_row["status"] == target_row["status"]),
        ]

        source_run_id = source_row["last_successful_run_id"]
        if source_run_id is None or str(source_run_id).strip() == "":
            checks.append(("latest_run_id", None, target_row["latest_run_id"], target_row["latest_run_id"] is None))

        for field, source_value, target_value, ok in checks:
            if not ok:
                field_mismatch_count += 1
                if len(field_mismatch_examples) < MAX_EXAMPLES:
                    field_mismatch_examples.append(
                        {
                            "key": {"pipeline_name": component_name, "source_table": source_table},
                            "field": field,
                            "source": source_value,
                            "target": target_value,
                        }
                    )

    warnings = []
    if unknown_components:
        warnings.append(
            "Unknown watermark components explicitly represented as UNKNOWN: "
            + ", ".join(sorted(unknown_components))
        )

    status = "FAILED" if (missing_in_target or extra_in_target or field_mismatch_count) else (
        "OK_WITH_WARNINGS" if warnings else "OK"
    )
    return {
        "status": status,
        "source_row_count": len(source_rows),
        "target_row_count": len(target_rows),
        "missing_in_target": [
            {"pipeline_name": pipeline_name, "source_table": source_table}
            for pipeline_name, source_table in missing_in_target[:MAX_EXAMPLES]
        ],
        "extra_in_target": [
            {"pipeline_name": pipeline_name, "source_table": source_table}
            for pipeline_name, source_table in extra_in_target[:MAX_EXAMPLES]
        ],
        "field_mismatch_count": field_mismatch_count,
        "field_mismatch_examples": field_mismatch_examples,
        "accepted_unmapped_target_fields": [],
        "unknown_components": sorted(unknown_components),
        "warnings": warnings,
    }


def audit_dc_ec_fact_parity(
    source_db_path: str,
    target_db_path: str,
    ecosystem_code: str = "DATACENTER",
    taxonomy_version_code: str = "DC_TAXONOMY_FULL_V1",
    signal_date: str | None = None,
    numeric_tolerance: float = 1e-9,
    include_pipeline_watermark: bool = True,
) -> dict[str, object]:
    source_conn = _connect_readonly(source_db_path)
    target_conn = _connect_readonly(target_db_path)
    try:
        _require_tables(source_conn, REQUIRED_SOURCE_TABLES, "source")
        _require_tables(target_conn, REQUIRED_TARGET_TABLES, "target")
        _require_table(target_conn, "ec_signal_run", "target")

        selected_signal_date, latest_dates, date_alignment = _resolve_aligned_signal_date(source_conn, signal_date)
        if selected_signal_date is None:
            explicit_date_source_counts = (
                _fetch_explicit_date_source_counts(source_conn, signal_date)
                if signal_date is not None
                else None
            )
            warning = "Source dc_ dates are not aligned for formal parity audit"
            if signal_date is not None and date_alignment == "EXPLICIT_DATE_MISSING_SOURCE_ROWS":
                warning = "Explicit signal_date is missing rows in one or more dc_ source tables"
            return {
                "status": "FAILED",
                "signal_date": signal_date,
                "date_alignment": date_alignment,
                "latest_dates": latest_dates,
                "explicit_date_source_counts": explicit_date_source_counts,
                "ticker_parity": None,
                "group_signal_parity": None,
                "synthetic_ohlc_parity": None,
                "group_index_parity": None,
                "pipeline_watermark_parity": None,
                "total_mismatch_count": 1,
                "warnings": [warning],
            }

        ecosystem_id, taxonomy_version_id = _resolve_target_context(
            target_conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )

        ticker_parity = _ticker_parity(
            source_conn,
            target_conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            signal_date=selected_signal_date,
            numeric_tolerance=numeric_tolerance,
        )
        group_signal_parity = _group_signal_parity(
            source_conn,
            target_conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            signal_date=selected_signal_date,
            numeric_tolerance=numeric_tolerance,
        )
        synthetic_ohlc_parity = _synthetic_ohlc_parity(
            source_conn,
            target_conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            signal_date=selected_signal_date,
            numeric_tolerance=numeric_tolerance,
        )
        group_index_parity = _group_index_parity(
            source_conn,
            target_conn,
            ecosystem_id=ecosystem_id,
            taxonomy_version_id=taxonomy_version_id,
            signal_date=selected_signal_date,
            numeric_tolerance=numeric_tolerance,
        )
        pipeline_watermark_parity = (
            _pipeline_watermark_parity(
                source_conn,
                target_conn,
                ecosystem_id=ecosystem_id,
                taxonomy_version_code=taxonomy_version_code,
            )
            if include_pipeline_watermark
            else {
                "status": "SKIPPED",
                "source_row_count": 0,
                "target_row_count": 0,
                "missing_in_target": [],
                "extra_in_target": [],
                "field_mismatch_count": 0,
                "field_mismatch_examples": [],
                "accepted_unmapped_target_fields": [],
                "unknown_components": [],
                "warnings": [
                    "Pipeline watermark parity skipped by caller policy",
                ],
            }
        )

        sections = [
            ticker_parity,
            group_signal_parity,
            synthetic_ohlc_parity,
            group_index_parity,
            pipeline_watermark_parity,
        ]
        total_mismatch_count = sum(
            len(section["missing_in_target"]) + len(section["extra_in_target"]) + int(section["field_mismatch_count"])
            for section in sections
        )
        warnings = [
            f"ticker: {warning}"
            for warning in ticker_parity["warnings"]
        ] + [
            f"group_signal: {warning}"
            for warning in group_signal_parity["warnings"]
        ] + [
            f"synthetic_ohlc: {warning}"
            for warning in synthetic_ohlc_parity["warnings"]
        ] + [
            f"group_index: {warning}"
            for warning in group_index_parity["warnings"]
        ] + [
            f"pipeline_watermark: {warning}"
            for warning in pipeline_watermark_parity["warnings"]
        ]

        if any(section["status"] == "FAILED" for section in sections):
            status = "FAILED"
        elif warnings:
            status = "OK_WITH_WARNINGS"
        else:
            status = "OK"

        return {
            "status": status,
            "signal_date": selected_signal_date,
            "date_alignment": date_alignment,
            "latest_dates": latest_dates,
            "ticker_parity": ticker_parity,
            "group_signal_parity": group_signal_parity,
            "synthetic_ohlc_parity": synthetic_ohlc_parity,
            "group_index_parity": group_index_parity,
            "pipeline_watermark_parity": pipeline_watermark_parity,
            "total_mismatch_count": total_mismatch_count,
            "warnings": warnings,
        }
    finally:
        source_conn.close()
        target_conn.close()
