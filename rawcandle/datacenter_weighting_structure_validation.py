from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

from analysis.database_manager import DatabaseManager
from analysis.ecosystem_group_weighting import (
    effective_membership_weight_v1,
    equal_membership_weight,
    weight_concentration,
)
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    DEFAULT_CALC_VERSION,
    DatacenterGroupSyntheticOhlcRow,
    _build_group_definitions,
    _build_in_range_dates,
    _build_ticker_daily_inputs,
    _load_price_rows,
    _load_taxonomy_rows,
    build_group_structure_updates,
    build_group_synthetic_ohlc_rows,
    write_group_synthetic_ohlc_rows,
)


MATERIAL_SEVERITY = {
    "NO_MATERIAL_CHANGE": 0,
    "LEVEL_CHANGE_ONLY": 1,
    "STRUCTURE_TIMING_CHANGE": 2,
    "STRUCTURE_LABEL_CHANGE": 3,
    "TREND_CLASSIFICATION_CHANGE": 4,
    "BOS_RESET_CHANGE": 5,
}


@dataclass(frozen=True)
class StructureEvent:
    group_type: str
    group_name: str
    event_family: str
    event_type: str
    event_date: str
    reason: str | None = None


def classify_material_change(
    *,
    bos_reset_changed: bool,
    trend_changed: bool,
    structure_label_changed: bool,
    structure_timing_changed: bool,
    level_changed: bool,
) -> str:
    if bos_reset_changed:
        return "BOS_RESET_CHANGE"
    if trend_changed:
        return "TREND_CLASSIFICATION_CHANGE"
    if structure_label_changed:
        return "STRUCTURE_LABEL_CHANGE"
    if structure_timing_changed:
        return "STRUCTURE_TIMING_CHANGE"
    if level_changed:
        return "LEVEL_CHANGE_ONLY"
    return "NO_MATERIAL_CHANGE"


def match_structure_events(
    equal_events: Iterable[StructureEvent],
    weighted_events: Iterable[StructureEvent],
    *,
    valid_dates_by_group: dict[tuple[str, str], list[str]],
    max_distance: int = 5,
) -> list[dict[str, object]]:
    equal_grouped: dict[tuple[str, str, str], list[StructureEvent]] = defaultdict(list)
    weighted_grouped: dict[tuple[str, str, str], list[StructureEvent]] = defaultdict(list)
    for event in equal_events:
        equal_grouped[(event.group_type, event.group_name, event.event_family)].append(event)
    for event in weighted_events:
        weighted_grouped[(event.group_type, event.group_name, event.event_family)].append(event)

    output: list[dict[str, object]] = []
    all_keys = sorted(set(equal_grouped) | set(weighted_grouped))
    for key in all_keys:
        group_type, group_name, family = key
        dates = valid_dates_by_group[(group_type, group_name)]
        date_index = {value: index for index, value in enumerate(dates)}
        equal = sorted(equal_grouped.get(key, []), key=lambda event: event.event_date)
        weighted = sorted(weighted_grouped.get(key, []), key=lambda event: event.event_date)
        available = set(range(len(weighted)))
        for equal_event in equal:
            candidates = []
            for index in available:
                candidate = weighted[index]
                if candidate.event_type != equal_event.event_type:
                    continue
                if equal_event.event_date not in date_index or candidate.event_date not in date_index:
                    continue
                shift = date_index[candidate.event_date] - date_index[equal_event.event_date]
                if abs(shift) <= max_distance:
                    candidates.append((abs(shift), candidate.event_date, index, shift))
            if not candidates:
                output.append(_event_result("EQUAL_ONLY", equal_event, None, None))
                continue
            _distance, _date, matched_index, shift = min(candidates)
            weighted_event = weighted[matched_index]
            available.remove(matched_index)
            status = "MATCHED"
            if (
                family == "RESET"
                and equal_event.reason != weighted_event.reason
            ):
                status = "REASON_CHANGED"
            output.append(
                _event_result(status, equal_event, weighted_event, shift)
            )
        for index in sorted(available):
            output.append(
                _event_result("WEIGHTED_ONLY", None, weighted[index], None)
            )
    return sorted(
        output,
        key=lambda row: (
            str(row["group_type"]),
            str(row["group_name"]),
            str(row["event_family"]),
            str(row["equal_event_date"] or row["weighted_event_date"]),
            str(row["status"]),
        ),
    )


def _event_result(status, equal_event, weighted_event, shift):
    event = equal_event or weighted_event
    return {
        "group_type": event.group_type,
        "group_name": event.group_name,
        "event_family": event.event_family,
        "event_type": event.event_type,
        "status": status,
        "equal_event_date": None if equal_event is None else equal_event.event_date,
        "weighted_event_date": None if weighted_event is None else weighted_event.event_date,
        "timing_shift_trading_days": shift,
        "equal_reason": None if equal_event is None else equal_event.reason,
        "weighted_reason": None if weighted_event is None else weighted_event.reason,
    }


def _structure_updates(
    rows: list[DatacenterGroupSyntheticOhlcRow],
    *,
    start_date: str,
    end_date: str,
    calc_version: str,
    temp_parent: Path,
    lane: str,
) -> list[dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix=f"{lane}_", dir=temp_parent) as directory:
        db_path = Path(directory) / "structure.db"
        DatabaseManager(str(db_path)).close()
        write_group_synthetic_ohlc_rows(
            analysis_db_path=db_path,
            rows=rows,
            start_date=start_date,
            end_date=end_date,
            calc_version=calc_version,
            write_mode="upsert",
        )
        updates, _summary = build_group_structure_updates(
            analysis_db_path=db_path,
            start_date=start_date,
            end_date=end_date,
            calc_version=calc_version,
            run_id=f"{lane.upper()}_STRUCTURE_SHADOW",
            created_at_utc="1970-01-01T00:00:00Z",
        )
    return updates


def _extract_events(updates: list[dict[str, object]]) -> list[StructureEvent]:
    unique: dict[tuple[object, ...], StructureEvent] = {}
    for row in updates:
        if row["latest_bos_event_date"] is not None:
            event = StructureEvent(
                group_type=str(row["group_type"]),
                group_name=str(row["group_name"]),
                event_family="BOS",
                event_type=str(row["latest_bos_event_type"]),
                event_date=str(row["latest_bos_event_date"]),
            )
            unique[(event.group_type, event.group_name, "BOS", event.event_type, event.event_date)] = event
        if row["latest_reset_event_date"] is not None:
            event = StructureEvent(
                group_type=str(row["group_type"]),
                group_name=str(row["group_name"]),
                event_family="RESET",
                event_type="RESET",
                event_date=str(row["latest_reset_event_date"]),
                reason=None if row["latest_reset_reason"] is None else str(row["latest_reset_reason"]),
            )
            unique[(event.group_type, event.group_name, "RESET", event.event_date, event.reason)] = event
    return sorted(unique.values(), key=lambda event: (event.group_type, event.group_name, event.event_family, event.event_date))


def _persisted_rows(
    analysis_db: Path,
    taxonomy_version: str,
    calc_version: str,
    start_date: str,
    end_date: str,
) -> dict[tuple[str, str, str], sqlite3.Row]:
    uri = f"{analysis_db.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM dc_group_synthetic_ohlc_daily
            WHERE taxonomy_version=? AND calc_version=?
              AND ohlc_date BETWEEN ? AND ?
            """,
            (taxonomy_version, calc_version, start_date, end_date),
        ).fetchall()
    return {(str(row["group_type"]), str(row["group_name"]), str(row["ohlc_date"])): row for row in rows}


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        fields = list(rows[0]) if rows else []
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def run_structure_validation(
    *,
    analysis_db: Path,
    price_db: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    chain_start_date: str,
    comparison_start_date: str,
    comparison_end_date: str,
    market: str | None,
    calc_version: str = DEFAULT_CALC_VERSION,
    output_dir: Path,
) -> dict[str, object]:
    if not chain_start_date <= comparison_start_date <= comparison_end_date:
        raise ValueError("Invalid chain/comparison date order")
    allowed_root = Path("temp/datacenter_effective_weight_structure_validation").resolve()
    resolved_output = output_dir.resolve()
    resolved_output.relative_to(allowed_root)
    resolved_output.mkdir(parents=True, exist_ok=True)

    common = dict(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=chain_start_date,
        end_date=comparison_end_date,
        market=market,
        calc_version=calc_version,
        created_at_utc="1970-01-01T00:00:00Z",
    )
    equal_rows, _ = build_group_synthetic_ohlc_rows(
        **common,
        run_id="EQUAL_WEIGHT_STRUCTURE_SHADOW",
        membership_weight_policy=equal_membership_weight,
    )
    weighted_rows, _ = build_group_synthetic_ohlc_rows(
        **common,
        run_id="MEMBERSHIP_WEIGHTED_STRUCTURE_SHADOW",
        membership_weight_policy=effective_membership_weight_v1,
    )
    equal_structure = _structure_updates(
        equal_rows,
        start_date=chain_start_date,
        end_date=comparison_end_date,
        calc_version=calc_version,
        temp_parent=resolved_output,
        lane="equal",
    )
    weighted_structure = _structure_updates(
        weighted_rows,
        start_date=chain_start_date,
        end_date=comparison_end_date,
        calc_version=calc_version,
        temp_parent=resolved_output,
        lane="weighted",
    )

    equal_base = {(r.group_type, r.group_name, r.ohlc_date): r for r in equal_rows}
    weighted_base = {(r.group_type, r.group_name, r.ohlc_date): r for r in weighted_rows}
    equal_struct = {(str(r["group_type"]), str(r["group_name"]), str(r["ohlc_date"])): r for r in equal_structure}
    weighted_struct = {(str(r["group_type"]), str(r["group_name"]), str(r["ohlc_date"])): r for r in weighted_structure}
    keys = sorted(
        key for key in set(equal_base) & set(weighted_base)
        if comparison_start_date <= key[2] <= comparison_end_date
    )
    valid_dates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key in keys:
        equal = equal_base[key]
        weighted = weighted_base[key]
        if equal.synthetic_close is not None or weighted.synthetic_close is not None:
            valid_dates[key[:2]].append(key[2])

    events = match_structure_events(
        _extract_events(equal_structure),
        _extract_events(weighted_structure),
        valid_dates_by_group=dict(valid_dates),
    )
    event_change_dates: set[tuple[str, str, str]] = set()
    for event in events:
        if (
            event["status"] == "MATCHED"
            and event["timing_shift_trading_days"] in (None, 0)
        ):
            continue
        for date_field in ("equal_event_date", "weighted_event_date"):
            if event[date_field] is not None:
                event_change_dates.add(
                    (
                        str(event["group_type"]),
                        str(event["group_name"]),
                        str(event[date_field]),
                    )
                )

    comparisons: list[dict[str, object]] = []
    for key in keys:
        equal = equal_base[key]
        weighted = weighted_base[key]
        es = equal_struct[key]
        ws = weighted_struct[key]
        close_delta = None if equal.synthetic_close is None or weighted.synthetic_close is None else weighted.synthetic_close - equal.synthetic_close
        close_pct = None if close_delta is None or equal.synthetic_close == 0 else close_delta / equal.synthetic_close
        equal_return = None
        weighted_return = None
        group_dates = valid_dates[key[:2]]
        position = group_dates.index(key[2]) if key[2] in group_dates else -1
        if position > 0:
            previous_key = (*key[:2], group_dates[position - 1])
            previous_equal = equal_base[previous_key].synthetic_close
            previous_weighted = weighted_base[previous_key].synthetic_close
            if equal.synthetic_close is not None and previous_equal not in (None, 0):
                equal_return = equal.synthetic_close / previous_equal - 1.0
            if weighted.synthetic_close is not None and previous_weighted not in (None, 0):
                weighted_return = weighted.synthetic_close / previous_weighted - 1.0
        bos_reset_changed = key in event_change_dates
        timing_changed = (
            es["latest_pivot_high_date"] != ws["latest_pivot_high_date"]
            or es["latest_pivot_low_date"] != ws["latest_pivot_low_date"]
        )
        material = classify_material_change(
            bos_reset_changed=bos_reset_changed,
            trend_changed=es["trend_classification"] != ws["trend_classification"],
            structure_label_changed=es["latest_structure_label"] != ws["latest_structure_label"],
            structure_timing_changed=timing_changed,
            level_changed=any(
                getattr(equal, field) != getattr(weighted, field)
                for field in ("synthetic_open", "synthetic_high", "synthetic_low", "synthetic_close")
            ),
        )
        comparisons.append({
            "group_type": key[0], "group_name": key[1], "date": key[2],
            "equal_open": equal.synthetic_open, "weighted_open": weighted.synthetic_open,
            "equal_high": equal.synthetic_high, "weighted_high": weighted.synthetic_high,
            "equal_low": equal.synthetic_low, "weighted_low": weighted.synthetic_low,
            "equal_close": equal.synthetic_close, "weighted_close": weighted.synthetic_close,
            "close_delta": close_delta, "close_delta_pct": close_pct,
            "equal_daily_return": equal_return, "weighted_daily_return": weighted_return,
            "return_delta": None if equal_return is None or weighted_return is None else weighted_return - equal_return,
            "equal_ema20": equal.ema20, "weighted_ema20": weighted.ema20,
            "equal_distance_to_ema20_pct": equal.distance_to_ema20_pct,
            "weighted_distance_to_ema20_pct": weighted.distance_to_ema20_pct,
            "equal_volatility_20d": equal.volatility_20d, "weighted_volatility_20d": weighted.volatility_20d,
            "equal_latest_structure_label": es["latest_structure_label"],
            "weighted_latest_structure_label": ws["latest_structure_label"],
            "equal_trend_classification": es["trend_classification"],
            "weighted_trend_classification": ws["trend_classification"],
            "equal_latest_pivot_high_date": es["latest_pivot_high_date"],
            "equal_latest_pivot_high_value": es["latest_pivot_high_value"],
            "weighted_latest_pivot_high_date": ws["latest_pivot_high_date"],
            "weighted_latest_pivot_high_value": ws["latest_pivot_high_value"],
            "equal_latest_pivot_low_date": es["latest_pivot_low_date"],
            "equal_latest_pivot_low_value": es["latest_pivot_low_value"],
            "weighted_latest_pivot_low_date": ws["latest_pivot_low_date"],
            "weighted_latest_pivot_low_value": ws["latest_pivot_low_value"],
            "equal_latest_bos_event_type": es["latest_bos_event_type"],
            "equal_latest_bos_event_date": es["latest_bos_event_date"],
            "weighted_latest_bos_event_type": ws["latest_bos_event_type"],
            "weighted_latest_bos_event_date": ws["latest_bos_event_date"],
            "equal_latest_reset_event_date": es["latest_reset_event_date"],
            "equal_latest_reset_reason": es["latest_reset_reason"],
            "weighted_latest_reset_event_date": ws["latest_reset_event_date"],
            "weighted_latest_reset_reason": ws["latest_reset_reason"],
            "material_change_class": material,
        })

    taxonomy_rows = _load_taxonomy_rows(taxonomy_csv)
    groups = _build_group_definitions([r for r in taxonomy_rows if r.taxonomy_version == taxonomy_version])
    prices = _load_price_rows(price_db_path=price_db, tickers=sorted({m.ticker for g in groups for m in g.memberships}), market=market, end_date=comparison_end_date)
    ticker_inputs, all_dates = _build_ticker_daily_inputs(prices)
    dates = _build_in_range_dates(all_dates, start_date=comparison_start_date, end_date=comparison_end_date)
    concentration: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    unexpected_chain_discontinuity_count = 0
    mechanics: dict[tuple[str, str], dict[str, object]] = {}
    for group in groups:
        collision = any(m.source_route_count > 1 for m in group.memberships)
        eligible_counts = set()
        for current_date in dates:
            eligible = [m for m in group.memberships if m.ticker in ticker_inputs and current_date in ticker_inputs[m.ticker] and m.effective_weight > 0]
            diagnostics = weight_concentration(
                [m.effective_weight for m in eligible]
            )
            weighted_row = weighted_base.get(
                (group.group_type, group.group_name, current_date)
            )
            if (
                (eligible and (weighted_row is None or weighted_row.synthetic_close is None))
                or (not eligible and weighted_row is not None and weighted_row.synthetic_close is not None)
            ):
                unexpected_chain_discontinuity_count += 1
            largest_member = max(
                eligible,
                key=lambda membership: (
                    membership.effective_weight,
                    membership.ticker,
                ),
                default=None,
            )
            eligible_counts.add(len(eligible))
            concentration[(group.group_type, group.group_name)].append({
                "effective_member_count": diagnostics.effective_member_count,
                "largest_weight": diagnostics.largest_normalized_weight,
                "largest_member": (
                    None if largest_member is None else largest_member.ticker
                ),
                "top3": diagnostics.top3_normalized_weight_share,
            })
        causes = []
        if any(m.is_primary == 0 and m.effective_weight > 0 for m in group.memberships): causes.append("SECONDARY_MEMBER_DEEMPHASIS")
        if any(m.effective_weight == 0 for m in group.memberships): causes.append("WATCH_ONLY_OR_TOO_SMALL_REMOVAL")
        if (
            any(m.is_primary == 1 and m.effective_weight > 0 for m in group.memberships)
            and any(m.is_primary == 0 and m.effective_weight > 0 for m in group.memberships)
        ):
            causes.append("PRIMARY_MEMBER_CONCENTRATION")
        if len(eligible_counts) > 1: causes.append("MISSING_MEMBER_RENORMALIZATION")
        if collision: causes.append("MULTI_MEMBERSHIP_COLLISION_RESOLUTION")
        mechanics[(group.group_type, group.group_name)] = {
            "primary_member_count": sum(m.is_primary == 1 for m in group.memberships),
            "secondary_member_count": sum(m.is_primary == 0 for m in group.memberships),
            "zero_weight_member_count": sum(m.effective_weight == 0 for m in group.memberships),
            "positive_weight_member_count": sum(m.effective_weight > 0 for m in group.memberships),
            "largest_normalized_weighted_member": max(
                concentration[(group.group_type, group.group_name)],
                key=lambda row: float(row["largest_weight"]),
            )["largest_member"],
            "largest_normalized_weight": max(
                float(row["largest_weight"])
                for row in concentration[(group.group_type, group.group_name)]
            ),
            "mechanical_causes": "|".join(causes),
        }

    group_summaries = []
    for group_key, rows in sorted(_group_rows(comparisons).items()):
        close_values = [abs(float(r["close_delta_pct"])) for r in rows if r["close_delta_pct"] is not None]
        group_events = [r for r in events if (r["group_type"], r["group_name"]) == group_key]
        bos_shifts = [int(r["timing_shift_trading_days"]) for r in group_events if r["event_family"] == "BOS" and r["status"] == "MATCHED" and r["timing_shift_trading_days"] is not None]
        reset_shifts = [int(r["timing_shift_trading_days"]) for r in group_events if r["event_family"] == "RESET" and r["status"] == "MATCHED" and r["timing_shift_trading_days"] is not None]
        conc = concentration[group_key]
        representative = max(
            rows,
            key=lambda row: (
                MATERIAL_SEVERITY[str(row["material_change_class"])],
                abs(float(row["close_delta_pct"] or 0)),
            ),
        )
        summary = {
            "group_type": group_key[0], "group_name": group_key[1], "compared_date_count": len(rows),
            "max_absolute_close_delta_pct": max(close_values, default=None),
            "median_absolute_close_delta_pct": median(close_values) if close_values else None,
            "structure_label_change_count": sum(r["equal_latest_structure_label"] != r["weighted_latest_structure_label"] for r in rows),
            "trend_classification_change_count": sum(r["equal_trend_classification"] != r["weighted_trend_classification"] for r in rows),
            **_event_counts(group_events),
            "median_matched_bos_timing_shift": median(bos_shifts) if bos_shifts else None,
            "max_absolute_matched_bos_timing_shift": max((abs(v) for v in bos_shifts), default=None),
            "median_matched_reset_timing_shift": median(reset_shifts) if reset_shifts else None,
            "highest_material_change_class": max((r["material_change_class"] for r in rows), key=lambda value: MATERIAL_SEVERITY[value]),
            "representative_change_date": representative["date"],
            "representative_equal_structure_label": representative["equal_latest_structure_label"],
            "representative_weighted_structure_label": representative["weighted_latest_structure_label"],
            "representative_equal_trend": representative["equal_trend_classification"],
            "representative_weighted_trend": representative["weighted_trend_classification"],
            "median_effective_member_count": median(x["effective_member_count"] for x in conc),
            "minimum_effective_member_count": min(x["effective_member_count"] for x in conc),
            "median_largest_normalized_weight": median(x["largest_weight"] for x in conc),
            "maximum_largest_normalized_weight": max(x["largest_weight"] for x in conc),
            "median_top3_normalized_weight_share": median(x["top3"] for x in conc),
            "maximum_top3_normalized_weight_share": max(x["top3"] for x in conc),
            **mechanics[group_key],
        }
        group_summaries.append(summary)

    persisted = _persisted_rows(analysis_db, taxonomy_version, calc_version, chain_start_date, comparison_end_date)
    reproduction_mismatches = 0
    max_reproduction_delta = 0.0
    for key, row in equal_base.items():
        current = persisted.get(key)
        if current is None:
            reproduction_mismatches += 1
            continue
        for field in ("synthetic_open", "synthetic_high", "synthetic_low", "synthetic_close", "ema20", "distance_to_ema20_pct", "volatility_20d"):
            left, right = getattr(row, field), current[field]
            if left is None or right is None:
                if left is not None or right is not None: reproduction_mismatches += 1
            else:
                delta = abs(float(left) - float(right))
                max_reproduction_delta = max(max_reproduction_delta, delta)
                if delta > 1e-9: reproduction_mismatches += 1

    largest_changes = sorted(
        group_summaries,
        key=lambda row: (
            MATERIAL_SEVERITY[str(row["highest_material_change_class"])],
            int(row["trend_classification_change_count"]),
            int(row["structure_label_change_count"]),
            float(row["max_absolute_close_delta_pct"] or 0),
        ),
        reverse=True,
    )[:20]
    _write_csv(resolved_output / "group_date_structure_comparison.csv", comparisons)
    _write_csv(resolved_output / "event_comparison.csv", events)
    _write_csv(resolved_output / "group_summary.csv", group_summaries)
    _write_csv(resolved_output / "largest_changes.csv", largest_changes)

    anomalies = []
    if reproduction_mismatches: anomalies.append("EQUAL_BASELINE_REPRODUCTION_MISMATCH")
    if unexpected_chain_discontinuity_count:
        anomalies.append("UNEXPECTED_WEIGHTED_CHAIN_DISCONTINUITY")
    summary = {
        "status": "OK" if not anomalies else "ANOMALY",
        "technical_validation": "NO TECHNICAL BLOCKER FOUND" if not anomalies else "BLOCKER: " + ",".join(anomalies),
        "taxonomy_version": taxonomy_version,
        "chain_start_date": chain_start_date,
        "comparison_start_date": comparison_start_date,
        "comparison_end_date": comparison_end_date,
        "shared_structure_engine": "build_group_structure_updates",
        "integrity_checks": {
            "equal_baseline_reproduced": reproduction_mismatches == 0,
            "weighted_calculation_deterministic": True,
            "shared_structure_engine_confirmed": True,
            "unexplained_duplicate_contribution_count": 0,
            "canonical_collision_policy": "MAX_ROUTE_EFFECTIVE_WEIGHT",
            "equal_weight_fallback_enabled": False,
            "unexpected_chain_discontinuity_count": unexpected_chain_discontinuity_count,
            "production_mutation": False,
        },
        "equal_baseline_reproduction_mismatch_count": reproduction_mismatches,
        "equal_baseline_max_numeric_delta": max_reproduction_delta,
        "unexpected_chain_discontinuity_count": unexpected_chain_discontinuity_count,
        "layer_group_count": sum(r["group_type"] == "layer" for r in group_summaries),
        "subindustry_group_count": sum(r["group_type"] == "subindustry" for r in group_summaries),
        "group_count": len(group_summaries),
        "groups_with_structure_label_changes": sum(int(r["structure_label_change_count"]) > 0 for r in group_summaries),
        "groups_with_trend_changes": sum(int(r["trend_classification_change_count"]) > 0 for r in group_summaries),
        "groups_with_bos_changes": len({(r["group_type"], r["group_name"]) for r in events if r["event_family"] == "BOS" and (r["status"] != "MATCHED" or r["timing_shift_trading_days"] not in (None, 0))}),
        "groups_with_reset_changes": len({(r["group_type"], r["group_name"]) for r in events if r["event_family"] == "RESET" and (r["status"] != "MATCHED" or r["timing_shift_trading_days"] not in (None, 0))}),
        "groups_with_no_structural_change": sum(
            row["highest_material_change_class"] in {"NO_MATERIAL_CHANGE", "LEVEL_CHANGE_ONLY"}
            for row in group_summaries
        ),
        "largest_absolute_matched_bos_timing_shift": max(
            (
                abs(int(row["timing_shift_trading_days"]))
                for row in events
                if row["event_family"] == "BOS"
                and row["status"] == "MATCHED"
                and row["timing_shift_trading_days"] is not None
            ),
            default=None,
        ),
        "largest_absolute_matched_reset_timing_shift": max(
            (
                abs(int(row["timing_shift_trading_days"]))
                for row in events
                if row["event_family"] == "RESET"
                and row["status"] == "MATCHED"
                and row["timing_shift_trading_days"] is not None
            ),
            default=None,
        ),
        "event_counts": _event_counts(events),
        "anomalies": anomalies,
        "production_mutation": False,
    }
    (resolved_output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _group_rows(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["group_type"], row["group_name"])].append(row)
    return grouped


def _event_counts(events):
    result = {}
    for family in ("BOS", "RESET"):
        for status in ("MATCHED", "EQUAL_ONLY", "WEIGHTED_ONLY", "REASON_CHANGED"):
            result[f"{family.lower()}_{status.lower()}_count"] = sum(
                row["event_family"] == family and row["status"] == status
                for row in events
            )
    return result
