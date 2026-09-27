from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from analysis.datacenter_indices.pipeline_watermark import upsert_pipeline_watermark
from analysis.datacenter_indices.swing_daily_report import _load_synthetic_rows
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    LEGACY_EQUAL_CALC_VERSION,
    WEIGHTED_CALC_VERSION,
    persist_datacenter_group_relative_ohlc,
    persist_datacenter_group_structure,
    persist_datacenter_group_synthetic_ohlc,
)
from rawcandle.ec_dc_fact_parity_audit import (
    audit_dc_ec_synthetic_ohlc_parity,
)
from rawcandle.ec_group_synthetic_ohlc_daily_loader import (
    load_ec_group_synthetic_ohlc_daily_from_dc,
)


DEFAULT_CHAIN_START_DATE = "2025-08-01"
DEFAULT_OUTPUT_ROOT = Path("temp/datacenter_weighting_v2_migration_rehearsal")
REBUILD_COMPONENTS = (
    "SYNTHETIC_OHLC_BASE",
    "SYNTHETIC_OHLC_RELATIVE",
    "SYNTHETIC_OHLC_STRUCTURE",
)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_sqlite_database(source: Path, target: Path) -> None:
    if target.exists():
        target.unlink()
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_conn:
        with sqlite3.connect(target) as target_conn:
            source_conn.backup(target_conn)


def _table_scope_fingerprint(
    db_path: Path,
    *,
    table: str,
    version_field: str,
    version: str,
    taxonomy_field: str,
    taxonomy_version: str,
) -> tuple[int, str]:
    with _readonly_connection(db_path) as connection:
        columns = [
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        order_fields = [
            field
            for field in (
                "ohlc_date",
                "signal_date",
                "group_type",
                "group_name",
                "entity_id",
                version_field,
            )
            if field in columns
        ]
        rows = connection.execute(
            f"SELECT * FROM {table} WHERE {version_field}=? AND {taxonomy_field}=? "
            f"ORDER BY {', '.join(order_fields)}",
            (version, taxonomy_version),
        ).fetchall()
    payload = json.dumps(
        [[row[column] for column in columns] for row in rows],
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


def _ec_scope_fingerprint(
    db_path: Path,
    *,
    ecosystem_code: str,
    taxonomy_version: str,
    calc_version: str,
) -> tuple[int, str]:
    with _readonly_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT f.*
            FROM ec_group_synthetic_ohlc_daily f
            JOIN ec_ecosystem e ON e.ecosystem_id=f.ecosystem_id
            JOIN ec_taxonomy_version tv ON tv.taxonomy_version_id=f.taxonomy_version_id
            WHERE e.ecosystem_code=?
              AND tv.taxonomy_version_code=?
              AND f.ohlc_calc_version=?
            ORDER BY f.signal_date, f.entity_type, f.entity_id
            """,
            (ecosystem_code, taxonomy_version, calc_version),
        ).fetchall()
        columns = [str(item[0]) for item in connection.execute(
            "SELECT name FROM pragma_table_info('ec_group_synthetic_ohlc_daily') ORDER BY cid"
        ).fetchall()]
    payload = json.dumps(
        [[row[column] for column in columns] for row in rows],
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


def resolve_v2_rebuild_boundary(
    *,
    analysis_db: Path,
    taxonomy_version: str,
    requested_end_date: str | None,
    validated_chain_start_date: str = DEFAULT_CHAIN_START_DATE,
) -> tuple[str, str]:
    with _readonly_connection(analysis_db) as connection:
        row = connection.execute(
            """
            SELECT MIN(ohlc_date), MAX(ohlc_date)
            FROM dc_group_synthetic_ohlc_daily
            WHERE taxonomy_version=? AND calc_version=?
            """,
            (taxonomy_version, LEGACY_EQUAL_CALC_VERSION),
        ).fetchone()
    current_start, current_end = row[0], row[1]
    if current_start is None or current_end is None:
        raise ValueError("No current V1 synthetic generation found")
    if str(current_start) != validated_chain_start_date:
        raise ValueError(
            "Current V1 chain start does not match validated safe anchor: "
            f"current={current_start}, validated={validated_chain_start_date}"
        )
    end_date = str(current_end) if requested_end_date is None else requested_end_date
    if end_date > str(current_end):
        raise ValueError(
            "requested_end_date exceeds current published V1 end date: "
            f"requested={end_date}, current={current_end}"
        )
    if end_date < validated_chain_start_date:
        raise ValueError("requested_end_date precedes chain start")
    return validated_chain_start_date, end_date


def _persist_v2_stages(
    *,
    candidate_db: Path,
    price_db: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    market: str,
    start_date: str,
    end_date: str,
    run_id: str,
    created_at_utc: str,
    fail_after_stage: str | None,
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    base = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=candidate_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=start_date,
        end_date=end_date,
        market=market,
        calc_version=WEIGHTED_CALC_VERSION,
        run_id=run_id,
        created_at_utc=created_at_utc,
        write_mode="replace-range",
    )
    summaries.append({"stage": "base", **base})
    if fail_after_stage == "base":
        raise RuntimeError("Injected rehearsal failure after base")

    relative = persist_datacenter_group_relative_ohlc(
        analysis_db_path=candidate_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=start_date,
        end_date=end_date,
        market=market,
        calc_version=WEIGHTED_CALC_VERSION,
        run_id=run_id,
        created_at_utc=created_at_utc,
        write_mode="replace-relative-range",
    )
    summaries.append({"stage": "relative", **relative})
    if fail_after_stage == "relative":
        raise RuntimeError("Injected rehearsal failure after relative")

    structure = persist_datacenter_group_structure(
        analysis_db_path=candidate_db,
        start_date=start_date,
        end_date=end_date,
        calc_version=WEIGHTED_CALC_VERSION,
        run_id=run_id,
        created_at_utc=created_at_utc,
        write_mode="replace-structure-range",
    )
    summaries.append({"stage": "structure", **structure})
    if fail_after_stage == "structure":
        raise RuntimeError("Injected rehearsal failure after structure")

    for component, stage_summary in zip(REBUILD_COMPONENTS, summaries):
        row_count = max(
            int(stage_summary.get("inserted_count") or 0),
            int(stage_summary.get("updated_count") or 0),
            int(stage_summary.get("upserted_count") or 0),
        )
        upsert_pipeline_watermark(
            analysis_db_path=candidate_db,
            component_name=component,
            taxonomy_version=taxonomy_version,
            market=market,
            calc_version=WEIGHTED_CALC_VERSION,
            start_date=start_date,
            end_date=end_date,
            row_count=row_count,
            status="OK",
            last_successful_run_id=run_id,
            last_successful_at_utc=created_at_utc,
            notes="PHASE5_V2_CANDIDATE_BUILD",
        )
    return summaries


def build_v2_candidate_generation(
    *,
    analysis_db: Path,
    price_db: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    market: str,
    requested_end_date: str | None = None,
    validated_chain_start_date: str = DEFAULT_CHAIN_START_DATE,
    run_id: str | None = None,
    created_at_utc: str | None = None,
    fail_after_stage: str | None = None,
) -> dict[str, object]:
    if fail_after_stage not in {None, "base", "relative", "structure"}:
        raise ValueError("Unsupported fail_after_stage")
    start_date, end_date = resolve_v2_rebuild_boundary(
        analysis_db=analysis_db,
        taxonomy_version=taxonomy_version,
        requested_end_date=requested_end_date,
        validated_chain_start_date=validated_chain_start_date,
    )
    resolved_run_id = run_id or (
        f"DC_GROUP_SYNTH_OHLC_{start_date.replace('-', '')}_"
        f"{end_date.replace('-', '')}_{WEIGHTED_CALC_VERSION}"
    )
    resolved_created_at = created_at_utc or "1970-01-01T00:00:00Z"
    v1_before = _table_scope_fingerprint(
        analysis_db,
        table="dc_group_synthetic_ohlc_daily",
        version_field="calc_version",
        version=LEGACY_EQUAL_CALC_VERSION,
        taxonomy_field="taxonomy_version",
        taxonomy_version=taxonomy_version,
    )
    stages = _persist_v2_stages(
        candidate_db=analysis_db,
        price_db=price_db,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version=taxonomy_version,
        market=market,
        start_date=start_date,
        end_date=end_date,
        run_id=resolved_run_id,
        created_at_utc=resolved_created_at,
        fail_after_stage=fail_after_stage,
    )
    v1_after = _table_scope_fingerprint(
        analysis_db,
        table="dc_group_synthetic_ohlc_daily",
        version_field="calc_version",
        version=LEGACY_EQUAL_CALC_VERSION,
        taxonomy_field="taxonomy_version",
        taxonomy_version=taxonomy_version,
    )
    if v1_before != v1_after:
        raise RuntimeError("V1 DC rows changed during V2 candidate build")
    scope = _dc_scope_summary(
        analysis_db,
        taxonomy_version=taxonomy_version,
        start_date=start_date,
        end_date=end_date,
    )
    if scope["minimum_date"] != start_date or scope["maximum_date"] != end_date:
        raise RuntimeError("V2 chain boundary mismatch")
    if int(scope["unexpected_chain_discontinuity_count"]) != 0:
        raise RuntimeError("Unexpected V2 chain discontinuity")
    return {
        "status": "OK",
        "calc_version": WEIGHTED_CALC_VERSION,
        "chain_start_date": start_date,
        "end_date": end_date,
        "run_id": resolved_run_id,
        "v1_dc_unchanged": True,
        "dc_scope": scope,
        "stages": stages,
    }


def project_v2_to_ec_range(
    *,
    source_db: Path,
    target_db: Path,
    ecosystem_code: str,
    taxonomy_version: str,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    with _readonly_connection(source_db) as connection:
        dates = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT ohlc_date
                FROM dc_group_synthetic_ohlc_daily
                WHERE taxonomy_version=? AND calc_version=?
                  AND ohlc_date BETWEEN ? AND ?
                ORDER BY ohlc_date
                """,
                (taxonomy_version, WEIGHTED_CALC_VERSION, start_date, end_date),
            ).fetchall()
        ]
    if not dates or dates[0] != start_date or dates[-1] != end_date:
        raise ValueError("DC V2 source does not cover the requested projection boundary")

    projected_rows = 0
    parity_mismatches = 0
    for signal_date in dates:
        load_summary = load_ec_group_synthetic_ohlc_daily_from_dc(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version,
            signal_date=signal_date,
            ohlc_calc_version=WEIGHTED_CALC_VERSION,
            replace_existing=True,
        )
        if load_summary.get("status") not in {"OK", "OK_WITH_WARNINGS"}:
            raise RuntimeError(
                f"EC V2 projection failed on {signal_date}: {load_summary.get('loader_error')}"
            )
        projected_rows += int(load_summary["loaded_row_count"])
        parity = audit_dc_ec_synthetic_ohlc_parity(
            source_db_path=str(source_db),
            target_db_path=str(target_db),
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version,
            signal_date=signal_date,
            ohlc_calc_version=WEIGHTED_CALC_VERSION,
        )
        parity_mismatches += int(parity["total_mismatch_count"])
        if parity["status"] not in {"OK", "OK_WITH_WARNINGS"} or int(
            parity["total_mismatch_count"]
        ) != 0:
            raise RuntimeError(f"DC/EC V2 parity failed on {signal_date}")
    return {
        "status": "OK",
        "ohlc_calc_version": WEIGHTED_CALC_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "projected_date_count": len(dates),
        "projected_row_count": projected_rows,
        "parity_mismatch_count": parity_mismatches,
    }


def _dc_scope_summary(
    db_path: Path,
    *,
    taxonomy_version: str,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    with _readonly_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*), MIN(ohlc_date), MAX(ohlc_date),
                   SUM(CASE WHEN synthetic_close IS NULL
                                 AND data_quality_status <> 'NO_DATA' THEN 1 ELSE 0 END)
            FROM dc_group_synthetic_ohlc_daily
            WHERE taxonomy_version=? AND calc_version=?
              AND ohlc_date BETWEEN ? AND ?
            """,
            (taxonomy_version, WEIGHTED_CALC_VERSION, start_date, end_date),
        ).fetchone()
    return {
        "row_count": int(row[0]),
        "minimum_date": row[1],
        "maximum_date": row[2],
        "unexpected_chain_discontinuity_count": int(row[3] or 0),
    }


def _report_selector_probe(
    db_path: Path,
    *,
    signal_date: str,
    taxonomy_version: str,
    calc_version: str,
) -> list[dict[str, object]]:
    with _readonly_connection(db_path) as connection:
        return _load_synthetic_rows(
            connection,
            signal_date=signal_date,
            calc_version=calc_version,
            taxonomy_version=taxonomy_version,
        )


def run_v2_production_parity_rehearsal(
    *,
    source_analysis_db: Path,
    price_db: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    market: str,
    ecosystem_code: str,
    output_dir: Path,
    requested_end_date: str | None = None,
    validated_chain_start_date: str = DEFAULT_CHAIN_START_DATE,
    fail_after_stage: str | None = None,
) -> dict[str, object]:
    resolved_output = output_dir.resolve()
    allowed_root = DEFAULT_OUTPUT_ROOT.resolve()
    try:
        resolved_output.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"output-dir must be under {allowed_root}") from exc
    if fail_after_stage not in {None, "base", "relative", "structure"}:
        raise ValueError("Unsupported fail_after_stage")
    resolved_output.mkdir(parents=True, exist_ok=True)
    candidate_db = resolved_output / "candidate_analysis.db"
    summary_path = resolved_output / "summary.json"
    source_file_before = _file_sha256(source_analysis_db)
    start_date, end_date = resolve_v2_rebuild_boundary(
        analysis_db=source_analysis_db,
        taxonomy_version=taxonomy_version,
        requested_end_date=requested_end_date,
        validated_chain_start_date=validated_chain_start_date,
    )
    source_v1_before = _table_scope_fingerprint(
        source_analysis_db,
        table="dc_group_synthetic_ohlc_daily",
        version_field="calc_version",
        version=LEGACY_EQUAL_CALC_VERSION,
        taxonomy_field="taxonomy_version",
        taxonomy_version=taxonomy_version,
    )
    _copy_sqlite_database(source_analysis_db, candidate_db)
    candidate_v1_before = _table_scope_fingerprint(
        candidate_db,
        table="dc_group_synthetic_ohlc_daily",
        version_field="calc_version",
        version=LEGACY_EQUAL_CALC_VERSION,
        taxonomy_field="taxonomy_version",
        taxonomy_version=taxonomy_version,
    )
    candidate_ec_v1_before = _ec_scope_fingerprint(
        candidate_db,
        ecosystem_code=ecosystem_code,
        taxonomy_version=taxonomy_version,
        calc_version=LEGACY_EQUAL_CALC_VERSION,
    )
    run_id = f"DC_GROUP_SYNTH_OHLC_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{WEIGHTED_CALC_VERSION}"
    created_at_utc = "1970-01-01T00:00:00Z"
    summary: dict[str, object]
    try:
        first_stages = _persist_v2_stages(
            candidate_db=candidate_db,
            price_db=price_db,
            taxonomy_csv=taxonomy_csv,
            taxonomy_version=taxonomy_version,
            market=market,
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            created_at_utc=created_at_utc,
            fail_after_stage=fail_after_stage,
        )
        first_v2 = _table_scope_fingerprint(
            candidate_db,
            table="dc_group_synthetic_ohlc_daily",
            version_field="calc_version",
            version=WEIGHTED_CALC_VERSION,
            taxonomy_field="taxonomy_version",
            taxonomy_version=taxonomy_version,
        )
        second_stages = _persist_v2_stages(
            candidate_db=candidate_db,
            price_db=price_db,
            taxonomy_csv=taxonomy_csv,
            taxonomy_version=taxonomy_version,
            market=market,
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            created_at_utc=created_at_utc,
            fail_after_stage=None,
        )
        second_v2 = _table_scope_fingerprint(
            candidate_db,
            table="dc_group_synthetic_ohlc_daily",
            version_field="calc_version",
            version=WEIGHTED_CALC_VERSION,
            taxonomy_field="taxonomy_version",
            taxonomy_version=taxonomy_version,
        )
        if first_v2 != second_v2:
            raise RuntimeError("Repeated V2 rebuild was not idempotent")
        report_v2 = _report_selector_probe(
            candidate_db,
            signal_date=end_date,
            taxonomy_version=taxonomy_version,
            calc_version=WEIGHTED_CALC_VERSION,
        )
        report_v1 = _report_selector_probe(
            candidate_db,
            signal_date=end_date,
            taxonomy_version=taxonomy_version,
            calc_version=LEGACY_EQUAL_CALC_VERSION,
        )
        if not report_v2 or any(row["calc_version"] != WEIGHTED_CALC_VERSION for row in report_v2):
            raise RuntimeError("V2 report selector did not isolate V2 rows")
        if not report_v1 or any(row["calc_version"] != LEGACY_EQUAL_CALC_VERSION for row in report_v1):
            raise RuntimeError("V1 report selector did not isolate V1 rows")

        projection = project_v2_to_ec_range(
            source_db=candidate_db,
            target_db=candidate_db,
            ecosystem_code=ecosystem_code,
            taxonomy_version=taxonomy_version,
            start_date=start_date,
            end_date=end_date,
        )

        candidate_v1_after = _table_scope_fingerprint(
            candidate_db,
            table="dc_group_synthetic_ohlc_daily",
            version_field="calc_version",
            version=LEGACY_EQUAL_CALC_VERSION,
            taxonomy_field="taxonomy_version",
            taxonomy_version=taxonomy_version,
        )
        candidate_ec_v1_after = _ec_scope_fingerprint(
            candidate_db,
            ecosystem_code=ecosystem_code,
            taxonomy_version=taxonomy_version,
            calc_version=LEGACY_EQUAL_CALC_VERSION,
        )
        dc_scope = _dc_scope_summary(
            candidate_db,
            taxonomy_version=taxonomy_version,
            start_date=start_date,
            end_date=end_date,
        )
        if candidate_v1_before != candidate_v1_after:
            raise RuntimeError("Candidate V1 DC rows changed during V2 rehearsal")
        if candidate_ec_v1_before != candidate_ec_v1_after:
            raise RuntimeError("Candidate V1 EC rows changed during V2 rehearsal")
        if dc_scope["minimum_date"] != start_date or dc_scope["maximum_date"] != end_date:
            raise RuntimeError("V2 chain boundary mismatch")
        if int(dc_scope["unexpected_chain_discontinuity_count"]) != 0:
            raise RuntimeError("Unexpected V2 chain discontinuity")
        summary = {
            "status": "OK",
            "calc_version": WEIGHTED_CALC_VERSION,
            "legacy_calc_version": LEGACY_EQUAL_CALC_VERSION,
            "chain_start_date": start_date,
            "end_date": end_date,
            "candidate_db": str(candidate_db),
            "dc_scope": dc_scope,
            "v1_dc_unchanged": True,
            "v1_ec_unchanged": True,
            "v2_rebuild_idempotent": True,
            "v1_report_row_count": len(report_v1),
            "v2_report_row_count": len(report_v2),
            "ec_projected_date_count": projection["projected_date_count"],
            "ec_projected_row_count": projection["projected_row_count"],
            "dc_ec_v2_parity_mismatch_count": projection["parity_mismatch_count"],
            "first_build_stages": first_stages,
            "second_build_stages": second_stages,
            "production_mutation": False,
            "rollback_action": "KEEP_V1_CONSUMERS; DROP_OR_REBUILD_V2_VERSION_SCOPE",
        }
    except Exception as exc:
        candidate_v1_after = _table_scope_fingerprint(
            candidate_db,
            table="dc_group_synthetic_ohlc_daily",
            version_field="calc_version",
            version=LEGACY_EQUAL_CALC_VERSION,
            taxonomy_field="taxonomy_version",
            taxonomy_version=taxonomy_version,
        )
        summary = {
            "status": "FAILED",
            "calc_version": WEIGHTED_CALC_VERSION,
            "chain_start_date": start_date,
            "end_date": end_date,
            "candidate_db": str(candidate_db),
            "error": str(exc),
            "v1_dc_unchanged": candidate_v1_before == candidate_v1_after,
            "production_mutation": False,
            "rollback_action": "KEEP_V1_CONSUMERS; DROP_OR_REBUILD_V2_VERSION_SCOPE",
        }
    source_file_after = _file_sha256(source_analysis_db)
    source_v1_after = _table_scope_fingerprint(
        source_analysis_db,
        table="dc_group_synthetic_ohlc_daily",
        version_field="calc_version",
        version=LEGACY_EQUAL_CALC_VERSION,
        taxonomy_field="taxonomy_version",
        taxonomy_version=taxonomy_version,
    )
    summary["source_database_unchanged"] = (
        source_file_before == source_file_after and source_v1_before == source_v1_after
    )
    if not summary["source_database_unchanged"]:
        summary["status"] = "FAILED"
        summary["error"] = "Source analysis database changed during rehearsal"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
