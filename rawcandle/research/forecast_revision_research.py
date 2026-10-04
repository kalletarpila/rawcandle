"""Read-only fetch-specific AS_KNOWN forecast revision research."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from collections import Counter
from statistics import median

from rawcandle.forecasts.fiscal_linker import LINK_RULE_VERSION
from rawcandle.forecasts.identity import IDENTITY_RULE_VERSION

from rawcandle.research.result_publication_event_window import validate_publication_input

VERSION = "forecast_revision_research_v1"
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
COLUMNS += ("transition_status", "hours_publication_to_new_0q_first_seen",
            "calendar_days_publication_to_new_0q", "trading_days_publication_to_new_0q",
            "pre_fetch_id", "post_fetch_id", "pre_snapshot_id", "post_snapshot_id",
            "pre_resolution_id", "post_resolution_id", "pre_link_id", "post_link_id",
            "pre_value_states_json", "post_value_states_json", "checkpoints_json",
            "pre_eps_low", "pre_eps_high", "post_eps_low", "post_eps_high",
            "pre_revenue_low", "pre_revenue_high", "post_revenue_low", "post_revenue_high",
            "eps_range_width_change", "revenue_range_width_change")


def instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed


def reconstruct_fetch(connection: sqlite3.Connection, fetch: dict[str, Any]) -> list[dict[str, Any]]:
    """Use only this fetch's snapshot, identity and acquisition-time fiscal links."""
    if fetch["status"] not in SUCCESS or not fetch.get("snapshot_id"):
        return []
    snapshot = connection.execute("SELECT forecast_family FROM forecast_snapshot WHERE snapshot_id=?",
                                  (fetch["snapshot_id"],)).fetchone()
    if not snapshot or snapshot["forecast_family"] != "FISCAL_ESTIMATE":
        return []
    links = connection.execute(
        "SELECT rowid AS link_order,* FROM forecast_fiscal_link WHERE fetch_id=? "
        "AND knowledge_mode='AS_KNOWN' AND link_rule_version=? "
        "ORDER BY linked_at_utc DESC,rowid DESC", (fetch["fetch_id"], LINK_RULE_VERSION))
    latest = {}
    for raw in links:
        link = dict(raw)
        if instant(link["fundamentals_as_of_utc"]) <= instant(fetch["fetched_at_utc"]):
            latest.setdefault(link["occurrence_index"], link)
    result = []
    for occurrence, link in sorted(latest.items()):
        if link["link_status"] != "LINKED" or link["snapshot_id"] != fetch["snapshot_id"]:
            continue
        identity = connection.execute(
            "SELECT * FROM forecast_identity_resolution WHERE resolution_id=? AND fetch_id=? "
            "AND identity_rule_version=?", (link["resolution_id"], fetch["fetch_id"], IDENTITY_RULE_VERSION)).fetchone()
        if not identity or identity["identity_status"] != "RESOLVED":
            continue
        if (identity["company_id"], identity["security_id"]) != (link["company_id"], link["security_id"]):
            continue
        if instant(identity["acquisition_timestamp_utc"]) != instant(fetch["fetched_at_utc"]):
            continue
        estimates = [dict(row) for row in connection.execute(
            "SELECT * FROM forecast_estimate WHERE snapshot_id=? AND occurrence_index=? ORDER BY estimate_id",
            (fetch["snapshot_id"], occurrence))]
        states = {f'{row["metric"]}:{row["statistic"]}': {"state": row["value_state"],
                  "numeric": row["value_numeric"], "text": row["value_text"]} for row in estimates}
        result.append({**fetch, "company_id": link["company_id"], "horizon": link["provider_horizon"],
                       "target": (link["company_id"], link["expected_fiscal_year"], link["expected_fiscal_quarter"]),
                       "canonical_quarter_id": link["canonical_quarter_id"], "link_id": link["link_id"],
                       "resolution_id": identity["resolution_id"], "states": states})
    return result


def classify_fetch(event: dict[str, Any], stamp: str) -> str:
    if event["research_status"] == "EXACT":
        return "PRE_RESULT" if instant(stamp) < instant(event["canonical_timestamp_utc"]) else "POST_RESULT"
    day = instant(stamp).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if day >= event["first_full_post_result_trading_date"]:
        return "POST_RESULT"
    # The uncertain event day is not a usable pre-result baseline.
    publication_day = event.get("research_publication_date")
    return "PRE_RESULT" if publication_day and day < publication_day else "BOUNDARY_UNCERTAIN"


def numeric(observation: dict[str, Any] | None, metric: str, statistic: str) -> float | None:
    state = (observation or {}).get("states", {}).get(f"{metric}:{statistic}", {})
    if state.get("state") not in {"NUMERIC_VALUE", "NUMERIC_ZERO"}:
        return None
    value = state.get("numeric")
    number = float(value) if value is not None else None
    return number if number is not None and math.isfinite(number) else None


def revision(pre: float | None, post: float | None) -> tuple[float | None, float | None, str | None]:
    if pre is None or post is None:
        return None, None, "MISSING_NUMERIC_VALUE"
    absolute = post - pre
    if abs(pre) < 1e-8 or pre * post < 0 or pre < 0:
        return absolute, None, "PERCENT_DENOMINATOR_UNSUITABLE"
    return absolute, absolute / pre * 100, None


def analyze_event(event: dict[str, Any], observations: list[dict[str, Any]],
                  next_target: tuple | None, trading_dates: list[str]) -> dict[str, Any]:
    company = int(event["company_id"])
    old_target = (company, int(event["fiscal_year"]), event["fiscal_quarter"])
    observations = sorted((row for row in observations if row["company_id"] == company),
                          key=lambda row: (instant(row["fetched_at_utc"]), row["fetch_order"]))
    pre = [row for row in observations if classify_fetch(event, row["fetched_at_utc"]) == "PRE_RESULT"]
    post = [row for row in observations if classify_fetch(event, row["fetched_at_utc"]) == "POST_RESULT"]
    old = [row for row in observations if row["horizon"] == "0q" and row["target"] == old_target]
    new = [row for row in observations if row["horizon"] == "0q" and next_target and row["target"] == next_target]
    first_new = new[0] if new else None
    old_before_new = [row for row in old if not first_new or instant(row["fetched_at_utc"]) < instant(first_new["fetched_at_utc"])]
    last_old = old_before_new[-1] if old_before_new else None
    if last_old and first_new:
        status = "OBSERVED"
    elif not any(row["horizon"] == "0q" for row in observations):
        status = "NO_USABLE_0Q"
    elif not last_old:
        status = "INSUFFICIENT_PRE_HISTORY"
    elif not any(row["horizon"] == "0q" for row in post):
        status = "INSUFFICIENT_POST_HISTORY"
    else:
        status = "NOT_YET_OBSERVED"
    baseline = next((row for row in reversed(pre) if row["horizon"] == "+1q" and next_target and row["target"] == next_target), None)
    after = next((row for row in post if row["horizon"] == "0q" and next_target and row["target"] == next_target), None)
    flags = []
    if not next_target:
        flags.append("NEXT_CANONICAL_QUARTER_UNAVAILABLE")
    if not baseline or not after:
        flags.append("NO_SAME_TARGET_PAIR")
    result = {"company_id": company, "ticker": event["ticker"], "result_fiscal_year": event["fiscal_year"],
              "result_fiscal_quarter": event["fiscal_quarter"], "publication_boundary_quality": event["research_status"],
              "result_publication_timestamp_utc": event.get("canonical_timestamp_utc") if event["research_status"] == "EXACT" else None,
              "first_full_post_result_trading_date": event.get("first_full_post_result_trading_date"),
              "transition_status": status, "research_status": event["research_status"],
              "target_fiscal_year": next_target[1] if next_target else None,
              "target_fiscal_quarter": next_target[2] if next_target else None,
              "pre_horizon": "+1q", "post_horizon": "0q",
              "old_0q_last_seen_at_utc": last_old["fetched_at_utc"] if last_old else None,
              "new_0q_first_seen_at_utc": first_new["fetched_at_utc"] if first_new else None,
              "transition_interval_hours": (instant(first_new["fetched_at_utc"]) - instant(last_old["fetched_at_utc"])).total_seconds()/3600 if status == "OBSERVED" else None,
              "has_pre": bool(pre), "has_post": bool(post), "comparable": bool(baseline and after)}
    for prefix, obs in (("pre", baseline), ("post", after)):
        result[f"{prefix}_fetch_at_utc"] = obs["fetched_at_utc"] if obs else None
        for field in ("fetch_id", "snapshot_id", "resolution_id", "link_id"):
            result[f"{prefix}_{field}"] = obs.get(field) if obs else None
        result[f"{prefix}_value_states_json"] = json.dumps(obs["states"] if obs else {}, sort_keys=True)
        for name, metric in (("eps", "EPS_ESTIMATE"), ("revenue", "REVENUE_ESTIMATE")):
            for statistic in ("avg", "low", "high"):
                result[f"{prefix}_{name}_{statistic}"] = numeric(obs, metric, statistic.upper())
            result[f"{prefix}_{name}_analyst_count"] = numeric(obs, "EPS_ANALYST_COUNT" if name == "eps" else "REVENUE_ANALYST_COUNT", "VALUE")
    for name in ("eps", "revenue"):
        absolute, percent, flag = revision(result[f"pre_{name}_avg"], result[f"post_{name}_avg"])
        result[f"{name}_revision_abs"], result[f"{name}_revision_pct"] = absolute, percent
        if flag:
            flags.append(f"{name.upper()}_{flag}")
        a, b = result[f"pre_{name}_analyst_count"], result[f"post_{name}_analyst_count"]
        result[f"{name}_analyst_count_change"] = b-a if a is not None and b is not None else None
        ranges = [result[f"{prefix}_{name}_{stat}"] for prefix in ("pre", "post") for stat in ("low", "high")]
        result[f"{name}_range_width_change"] = (ranges[3]-ranges[2])-(ranges[1]-ranges[0]) if all(x is not None for x in ranges) else None
    delay = None
    if first_new:
        new_time = instant(first_new["fetched_at_utc"])
        new_day = new_time.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        origin = event.get("research_publication_date") or event.get("first_full_post_result_trading_date")
        if event["research_status"] == "EXACT":
            delta = new_time - instant(event["canonical_timestamp_utc"])
            result["hours_publication_to_new_0q_first_seen"] = delta.total_seconds()/3600
            origin = instant(event["canonical_timestamp_utc"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            result["calendar_days_publication_to_new_0q"] = (new_time.astimezone(ZoneInfo("America/New_York")).date() - instant(event["canonical_timestamp_utc"]).astimezone(ZoneInfo("America/New_York")).date()).days
        if origin and trading_dates and trading_dates[-1] >= max(origin, new_day):
            delay = sum(origin < day <= new_day for day in trading_dates) if new_day >= origin else -sum(new_day < day <= origin for day in trading_dates)
        result["transition_trading_day_class"] = ("BEFORE_RESULT" if classify_fetch(event, first_new["fetched_at_utc"]) == "PRE_RESULT" else
            "SAME_RESULT_DAY" if delay == 0 else "NEXT_TRADING_DAY" if delay == 1 else
            "2_TO_3_TRADING_DAYS" if delay in (2,3) else "4_PLUS_TRADING_DAYS" if delay is not None and delay >= 4 else None)
    elif status == "NOT_YET_OBSERVED":
        result["transition_trading_day_class"] = "NOT_YET_OBSERVED"
    result["trading_days_publication_to_new_0q"] = delay
    checkpoints = {}
    if after:
        anchor = instant(after["fetched_at_utc"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        days = [day for day in trading_dates if day >= anchor]
        for offset in (1,2,5):
            candidate = next((obs for obs in post if obs["horizon"] == "0q" and obs["target"] == next_target and len(days)>offset
                              and instant(obs["fetched_at_utc"]).astimezone(ZoneInfo("America/New_York")).date().isoformat() >= days[offset]), None)
            checkpoints[str(offset)] = {"fetch_id": candidate["fetch_id"], "fetched_at_utc": candidate["fetched_at_utc"], "states": candidate["states"]} if candidate else None
    result["checkpoints_json"] = json.dumps(checkpoints, sort_keys=True)
    result["data_quality_flags"] = "|".join(sorted(set(flags)))
    return result


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


def next_fiscal_target(quarters: list[tuple], key: tuple,
                      observations: list[dict[str, Any]]) -> tuple | None:
    if key not in quarters:
        return None
    expected = (key[0], key[1]+1, "Q1") if key[2] == "Q4" else (key[0], key[1], f"Q{int(key[2][1])+1}")
    index = quarters.index(key)
    if index+1 < len(quarters):
        return expected if quarters[index+1] == expected else None
    # LINKED AS_KNOWN identities can legitimately precede a canonical quarter row.
    return expected if any(row["target"] == expected and row["horizon"] in {"0q", "+1q"}
                           for row in observations) else None


def transition_class_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(row.get("transition_trading_day_class") or "UNAVAILABLE" for row in rows))


def build_forecast_revision_research(
    publication_csv: Path, publication_metadata: Path, forecasts_db: Path,
    canonical_db: Path, ohlc_db: Path, output_csv: Path, output_metadata: Path,
    *, generated_at_utc: str | None = None,
) -> dict[str, Any]:
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
        identities = {tuple(key) for key in summary.get("cohort_identities", [])}
        cohort = [row for row in publications if (int(row["company_id"]), int(row["fiscal_year"]), row["fiscal_quarter"]) in identities]
        companies = {int(row["company_id"]) for row in cohort}
        reconstructed = [obs for fetch in ordered_observations(fetches)
                         if companies for obs in reconstruct_fetch(connection, fetch) if obs["company_id"] in companies]
        sample_fetches = [row for row in fetches if row["status"] in SUCCESS][:3]
        reconstruction_qa = [{"fetch_id": fetch["fetch_id"], "status": fetch["status"],
                              "targets": [{"horizon": obs["horizon"], "target": obs["target"],
                                           "link_id": obs["link_id"], "resolution_id": obs["resolution_id"],
                                           "snapshot_id": obs["snapshot_id"]}
                                          for obs in reconstruct_fetch(connection, fetch)]}
                             for fetch in sample_fetches]
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
    rows = []
    canonical = readonly(canonical_db)
    ohlc = readonly(ohlc_db)
    try:
        for event in cohort:
            quarters = [tuple(row) for row in canonical.execute(
                "SELECT company_id,fiscal_year,fiscal_quarter FROM v4_quarter WHERE company_id=? ORDER BY period_end,fiscal_year,fiscal_quarter",
                (int(event["company_id"]),))]
            key = (int(event["company_id"]), int(event["fiscal_year"]), event["fiscal_quarter"])
            target = next_fiscal_target(quarters, key, reconstructed)
            days = [row[0] for row in ohlc.execute("SELECT DISTINCT pvm FROM osakedata WHERE osake=? ORDER BY pvm", (event["ticker"],))]
            rows.append(analyze_event(event, reconstructed, target, days))
    finally:
        canonical.close()
        ohlc.close()
    observations = {
        "events_with_pre": sum(row["has_pre"] for row in rows),
        "events_with_post": sum(row["has_post"] for row in rows),
        "events_with_both": sum(row["has_pre"] and row["has_post"] for row in rows),
        "events_only_pre": sum(row["has_pre"] and not row["has_post"] for row in rows),
        "events_only_post": sum(row["has_post"] and not row["has_pre"] for row in rows),
        "events_without_usable_observations": sum(not row["has_pre"] and not row["has_post"] for row in rows),
        "comparable_next_quarter_events": sum(row["comparable"] for row in rows),
        "transition_status_counts": dict(Counter(row["transition_status"] for row in rows)),
        "transition_class_counts": transition_class_counts(rows),
    }
    for column in ("transition_interval_hours", "trading_days_publication_to_new_0q", "eps_revision_abs", "revenue_revision_abs", "eps_analyst_count_change", "revenue_analyst_count_change"):
        values = [row[column] for row in rows if row.get(column) is not None]
        observations[f"median_{column}"] = median(values) if values else None
    for name in ("eps", "revenue"):
        values = [row[f"{name}_revision_abs"] for row in rows if row.get(f"{name}_revision_abs") is not None]
        observations[f"{name}_positive_percent"] = 100*sum(x>0 for x in values)/len(values) if values else None
        observations[f"{name}_negative_percent"] = 100*sum(x<0 for x in values)/len(values) if values else None
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
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "artifact_version": VERSION,
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "decision": "FORECAST_REVISION_RESEARCH_V1_READY" if rows and (observations["comparable_next_quarter_events"] or observations["transition_status_counts"].get("OBSERVED")) else "FORECAST_REVISION_RESEARCH_V1_INSUFFICIENT_HISTORY",
        "publication_csv": str(publication_csv.resolve()),
        "publication_sha256": sha256(publication_csv),
        "publication_rows": len(publications),
        "latest_frozen_boundary": max((row["first_full_post_result_trading_date"] for row in publications), default=None),
        "availability": summary,
        "health": health,
        "observations": observations,
        "representative_qa": rows if len(rows) <= 20 else rows[::max(1,len(rows)//20)][:20],
        "reconstruction_qa": reconstruction_qa,
        "source_paths": {name: str(path.resolve()) for name, path in sources.items()},
        "source_sha256_before": before, "source_sha256_after": after,
        "quick_check": checks,
        "output_csv": str(output_csv.resolve()), "output_csv_sha256": sha256(output_csv),
        "output_rows": len(rows),
        "limitation": "Quarter comparisons only; annual horizons reconstructed but not compared. No estimates interpolated. Calendar delays require observed OHLC coverage.",
    }
    output_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
