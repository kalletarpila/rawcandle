"""Read-only availability gate for the first forecast-revision cohort."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from rawcandle.research.result_publication_event_window import validate_publication_input

VERSION = "forecast_revision_research_v1"
PUBLICATION_SHA = "76c6b5bb01e0849fbdfcc76058f6e14a997d84d86d332f75275c31a9b4d7cf52"
SUCCESS = {"SUCCESS_CHANGED", "SUCCESS_UNCHANGED"}
COLUMNS = (
    "company_id", "ticker", "result_fiscal_year", "result_fiscal_quarter",
    "result_publication_timestamp_utc", "first_full_post_result_trading_date",
    "publication_boundary_quality", "old_0q_last_seen_at_utc",
    "new_0q_first_seen_at_utc", "transition_interval_hours",
    "transition_trading_day_class", "target_fiscal_year", "target_fiscal_quarter",
    "pre_horizon", "post_horizon", "pre_fetch_at_utc", "post_fetch_at_utc",
    "pre_eps_avg", "post_eps_avg", "eps_revision_abs", "eps_revision_pct",
    "pre_revenue_avg", "post_revenue_avg", "revenue_revision_abs",
    "revenue_revision_pct", "pre_eps_analyst_count", "post_eps_analyst_count",
    "pre_revenue_analyst_count", "post_revenue_analyst_count",
    "eps_analyst_count_change", "revenue_analyst_count_change",
    "research_status", "data_quality_flags",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def ordered_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Each unchanged fetch remains an observation; failures do not replace state.
    return sorted(
        (row for row in rows if row["status"] in SUCCESS | {"VALID_NO_DATA"}),
        key=lambda row: (datetime.fromisoformat(row["fetched_at_utc"].replace("Z", "+00:00")), row["fetch_order"]),
    )


def summarize_forecast_revision_research(
    publications: list[dict[str, Any]], fetches: list[dict[str, Any]]
) -> dict[str, Any]:
    timestamps = [datetime.fromisoformat(row["fetched_at_utc"].replace("Z", "+00:00")) for row in fetches]
    if not timestamps:
        return {"history_start": None, "history_end": None, "events_inside_history_window": 0}
    start, end = min(timestamps), max(timestamps)
    start_day = start.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    end_day = end.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    cohort = []
    for row in publications:
        exact = row.get("canonical_timestamp_utc") if row.get("research_status") == "EXACT" else None
        if exact:
            instant = datetime.fromisoformat(exact.replace("Z", "+00:00"))
            inside = start <= instant <= end
        else:
            boundary = row.get("first_full_post_result_trading_date")
            inside = bool(boundary and start_day <= boundary <= end_day)
        if inside:
            cohort.append(row)
    return {
        "history_start": start.isoformat().replace("+00:00", "Z"),
        "history_end": end.isoformat().replace("+00:00", "Z"),
        "events_inside_history_window": len(cohort),
        "cohort_identities": [[int(row["company_id"]), int(row["fiscal_year"]), row["fiscal_quarter"]] for row in cohort],
        "successful_fiscal_fetches": sum(row["status"] in SUCCESS for row in fetches),
        "valid_no_data_fiscal_fetches": sum(row["status"] == "VALID_NO_DATA" for row in fetches),
        "fiscal_fetch_status_counts": {status: sum(row["status"] == status for row in fetches) for status in sorted({row["status"] for row in fetches})},
        "companies_observed": len({row["company_id"] for row in fetches if row.get("company_id") is not None}),
    }


def build_forecast_revision_research(
    publication_csv: Path, publication_metadata: Path, forecasts_db: Path,
    canonical_db: Path, ohlc_db: Path, output_csv: Path, output_metadata: Path,
    *, generated_at_utc: str | None = None,
) -> dict[str, Any]:
    if sha256(publication_csv) != PUBLICATION_SHA:
        raise ValueError("FROZEN_PUBLICATION_SHA_MISMATCH")
    validate_publication_input(publication_csv, publication_metadata)
    with publication_csv.open(newline="", encoding="utf-8") as handle:
        publications = list(csv.DictReader(handle))
    sources = {"forecasts": forecasts_db, "canonical": canonical_db, "ohlc": ohlc_db}
    before = {name: sha256(path) for name, path in sources.items()}
    connection = readonly(forecasts_db)
    try:
        fetches = [dict(row) for row in connection.execute(
            "SELECT rowid AS fetch_order,* FROM forecast_fetch WHERE forecast_family='FISCAL_ESTIMATE' ORDER BY fetched_at_utc,rowid"
        )]
        summary = summarize_forecast_revision_research(publications, fetches)
        health = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("forecast_run", "forecast_fetch", "forecast_snapshot")}
        health["fiscal_estimate_snapshots"] = connection.execute(
            "SELECT COUNT(*) FROM forecast_snapshot WHERE forecast_family='FISCAL_ESTIMATE'"
        ).fetchone()[0]
        health["recent_runs"] = [dict(row) for row in connection.execute(
            "SELECT run_id,started_at_utc,completed_at_utc,status,scope_json,counters_json FROM forecast_run ORDER BY started_at_utc DESC LIMIT 5"
        )]
        health["link_counts"] = [dict(row) for row in connection.execute(
            "SELECT knowledge_mode,link_status,COUNT(*) AS count FROM forecast_fiscal_link GROUP BY knowledge_mode,link_status"
        )]
    finally:
        connection.close()
    if summary["events_inside_history_window"]:
        raise ValueError("PRE_POST_COHORT_AVAILABLE_REQUIRES_REVISION_ANALYSIS")
    checks = {}
    for name, path in sources.items():
        connection = readonly(path)
        try:
            checks[name] = [row[0] for row in connection.execute("PRAGMA quick_check")]
        finally:
            connection.close()
        if checks[name] != ["ok"]:
            raise ValueError(f"DATABASE_INTEGRITY_FAILED:{name}")
    after = {name: sha256(path) for name, path in sources.items()}
    if before != after:
        raise ValueError("SOURCE_DATABASE_CHANGED_DURING_RESEARCH")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(COLUMNS)
    metadata = {
        "artifact_version": VERSION,
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "decision": "FORECAST_REVISION_RESEARCH_V1_INSUFFICIENT_HISTORY",
        "publication_csv": str(publication_csv.resolve()),
        "publication_sha256": PUBLICATION_SHA,
        "publication_rows": len(publications),
        "latest_frozen_boundary": max(row["first_full_post_result_trading_date"] for row in publications),
        "availability": summary,
        "health": health,
        "observations": {
            "events_with_pre": 0, "events_with_post": 0, "events_with_both": 0,
            "observed_transitions": 0, "not_yet_observed_transitions": 0,
            "comparable_next_quarter_events": 0,
            "median_transition_delay": None, "median_eps_revision": None,
            "median_revenue_revision": None,
            "same_day_transitions": 0, "next_day_transitions": 0, "later_transitions": 0,
        },
        "source_paths": {name: str(path.resolve()) for name, path in sources.items()},
        "source_sha256_before": before, "source_sha256_after": after,
        "quick_check": checks,
        "output_csv": str(output_csv.resolve()), "output_csv_sha256": sha256(output_csv),
        "output_rows": 0,
        "limitation": "Frozen publication coverage ends before forecast acquisition begins; revision and transition analysis deferred.",
    }
    output_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
