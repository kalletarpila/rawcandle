from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence

from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    _build_group_definitions,
    _build_ticker_daily_inputs,
    _load_price_rows,
    _load_taxonomy_rows,
)
from analysis.ecosystem_group_weighting import weight_concentration


CONCENTRATION_CLASSES = (
    "HEALTHY_WEIGHTED_GROUP",
    "CONCENTRATED_BUT_USABLE",
    "STRUCTURALLY_THIN",
    "NO_EFFECTIVE_COVERAGE",
)
GUARDRAIL_CANDIDATES = ("A", "B", "C", "D")


def classify_constituent_breadth(count: int) -> str:
    if count >= 4:
        return "HEALTHY"
    if count >= 2:
        return "THIN"
    if count == 1:
        return "SINGLE_MEMBER"
    return "NO_EFFECTIVE_MEMBERS"


def classify_effective_member_count(value: float) -> str:
    if value >= 3.0:
        return "HEALTHY"
    if value >= 1.5:
        return "CONCENTRATED"
    return "HIGHLY_CONCENTRATED"


def classify_largest_member_weight(value: float) -> str:
    if value <= 0.40:
        return "HEALTHY"
    if value <= 0.60:
        return "ELEVATED"
    return "DOMINANT"


def classify_top3_share(value: float) -> str:
    if value <= 0.80:
        return "HEALTHY"
    if value <= 0.95:
        return "ELEVATED"
    return "EXTREME"


def classify_group_concentration(
    rows: Sequence[Mapping[str, object]],
) -> str:
    if not rows:
        raise ValueError("Group concentration classification requires date rows")
    no_effective_share = sum(
        int(row["eligible_positive_weight_member_count"]) == 0 for row in rows
    ) / len(rows)
    if no_effective_share >= 0.90:
        return "NO_EFFECTIVE_COVERAGE"
    median_effective = median(float(row["effective_member_count"]) for row in rows)
    median_largest = median(float(row["largest_normalized_weight"]) for row in rows)
    single_share = sum(
        int(row["eligible_positive_weight_member_count"]) == 1 for row in rows
    ) / len(rows)
    if (
        median_effective >= 3.0
        and median_largest <= 0.40
        and single_share <= 0.10
    ):
        return "HEALTHY_WEIGHTED_GROUP"
    if (
        median_effective >= 1.5
        and median_largest <= 0.60
        and single_share <= 0.25
    ):
        return "CONCENTRATED_BUT_USABLE"
    return "STRUCTURALLY_THIN"


def guardrail_date_usable(
    candidate: str,
    *,
    eligible_positive_weight_member_count: int,
    effective_member_count: float,
) -> bool:
    if candidate not in GUARDRAIL_CANDIDATES:
        raise ValueError(f"Unsupported guardrail candidate: {candidate!r}")
    if candidate == "A":
        return True
    breadth_ok = eligible_positive_weight_member_count >= 2
    concentration_ok = effective_member_count >= 1.5
    if candidate == "B":
        return breadth_ok
    if candidate == "C":
        return concentration_ok
    return breadth_ok and concentration_ok


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)


def _float(row: Mapping[str, object], field: str) -> float:
    value = row.get(field)
    return 0.0 if value in (None, "") else float(value)


def _int(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    return 0 if value in (None, "") else int(value)


def _date_diagnostics(
    *,
    comparison_rows: Sequence[Mapping[str, str]],
    taxonomy_csv: Path,
    taxonomy_version: str,
    price_db: Path,
    market: str | None,
    comparison_end_date: str,
) -> tuple[list[dict[str, object]], list[str]]:
    taxonomy_rows = [
        row
        for row in _load_taxonomy_rows(taxonomy_csv)
        if row.taxonomy_version == taxonomy_version
    ]
    groups = _build_group_definitions(taxonomy_rows)
    group_map = {(group.group_type, group.group_name): group for group in groups}
    prices = _load_price_rows(
        price_db_path=price_db,
        tickers=sorted({m.ticker for group in groups for m in group.memberships}),
        market=market,
        end_date=comparison_end_date,
    )
    ticker_inputs, _dates = _build_ticker_daily_inputs(prices)
    diagnostics: list[dict[str, object]] = []
    anomalies: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for comparison in comparison_rows:
        key = (
            comparison["group_type"],
            comparison["group_name"],
            comparison["date"],
        )
        if key in seen:
            anomalies.append(f"DUPLICATE_GROUP_DATE:{'|'.join(key)}")
            continue
        seen.add(key)
        group = group_map.get(key[:2])
        if group is None:
            anomalies.append(f"GROUP_NOT_IN_TAXONOMY:{key[0]}|{key[1]}")
            continue
        positive = [m for m in group.memberships if m.effective_weight > 0]
        eligible = [
            m
            for m in positive
            if m.ticker in ticker_inputs and key[2] in ticker_inputs[m.ticker]
        ]
        concentration = weight_concentration(
            [membership.effective_weight for membership in eligible]
        )
        diagnostics.append(
            {
                "group_type": key[0],
                "group_name": key[1],
                "date": key[2],
                "positive_weight_member_count": len(positive),
                "eligible_positive_weight_member_count": len(eligible),
                "effective_member_count": concentration.effective_member_count,
                "largest_normalized_weight": concentration.largest_normalized_weight,
                "top3_normalized_weight_share": concentration.top3_normalized_weight_share,
                "breadth_band": classify_constituent_breadth(len(eligible)),
                "effective_member_band": classify_effective_member_count(
                    concentration.effective_member_count
                ),
                "largest_member_band": classify_largest_member_weight(
                    concentration.largest_normalized_weight
                ),
                "top3_band": classify_top3_share(
                    concentration.top3_normalized_weight_share
                ),
            }
        )
    return diagnostics, anomalies


def _group_reviews(
    date_rows: Sequence[Mapping[str, object]],
    phase3_group_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in date_rows:
        grouped[(str(row["group_type"]), str(row["group_name"]))].append(row)
    phase3 = {
        (row["group_type"], row["group_name"]): row for row in phase3_group_rows
    }
    reviews: list[dict[str, object]] = []
    for key, rows in sorted(grouped.items()):
        source = phase3[key]
        concentration_class = classify_group_concentration(rows)
        counts = Counter(str(row["breadth_band"]) for row in rows)
        positive = [int(row["positive_weight_member_count"]) for row in rows]
        eligible = [int(row["eligible_positive_weight_member_count"]) for row in rows]
        effective = [float(row["effective_member_count"]) for row in rows]
        largest = [float(row["largest_normalized_weight"]) for row in rows]
        top3 = [float(row["top3_normalized_weight_share"]) for row in rows]
        compared = len(rows)
        causes = [value for value in source.get("mechanical_causes", "").split("|") if value]
        if min(positive) < 4:
            causes.append("NARROW_CURRENT_TAXONOMY")
        reviews.append(
            {
                "group_type": key[0],
                "group_name": key[1],
                "concentration_class": concentration_class,
                "compared_date_count": compared,
                "minimum_positive_weight_member_count": min(positive),
                "median_positive_weight_member_count": median(positive),
                "minimum_eligible_positive_weight_member_count": min(eligible),
                "median_eligible_positive_weight_member_count": median(eligible),
                "median_effective_member_count": median(effective),
                "minimum_effective_member_count": min(effective),
                "median_largest_normalized_weight": median(largest),
                "maximum_largest_normalized_weight": max(largest),
                "median_top3_normalized_weight_share": median(top3),
                "maximum_top3_normalized_weight_share": max(top3),
                "healthy_breadth_date_count": counts["HEALTHY"],
                "thin_breadth_date_count": counts["THIN"],
                "single_member_date_count": counts["SINGLE_MEMBER"],
                "no_effective_members_date_count": counts["NO_EFFECTIVE_MEMBERS"],
                "single_member_date_share": counts["SINGLE_MEMBER"] / compared,
                "no_effective_members_date_share": counts["NO_EFFECTIVE_MEMBERS"] / compared,
                "structure_label_change_count": _int(source, "structure_label_change_count"),
                "structure_label_change_share": _int(source, "structure_label_change_count") / compared,
                "trend_classification_change_count": _int(source, "trend_classification_change_count"),
                "trend_classification_change_share": _int(source, "trend_classification_change_count") / compared,
                "bos_matched_count": _int(source, "bos_matched_count"),
                "bos_equal_only_count": _int(source, "bos_equal_only_count"),
                "bos_weighted_only_count": _int(source, "bos_weighted_only_count"),
                "median_matched_bos_timing_shift": source.get("median_matched_bos_timing_shift", ""),
                "max_absolute_matched_bos_timing_shift": source.get("max_absolute_matched_bos_timing_shift", ""),
                "reset_matched_count": _int(source, "reset_matched_count"),
                "reset_equal_only_count": _int(source, "reset_equal_only_count"),
                "reset_weighted_only_count": _int(source, "reset_weighted_only_count"),
                "reset_reason_changed_count": _int(source, "reset_reason_changed_count"),
                "median_matched_reset_timing_shift": source.get("median_matched_reset_timing_shift", ""),
                "max_absolute_close_delta_pct": _float(source, "max_absolute_close_delta_pct"),
                "median_absolute_close_delta_pct": _float(source, "median_absolute_close_delta_pct"),
                "highest_material_change_class": source.get("highest_material_change_class", ""),
                "mechanical_causes": "|".join(dict.fromkeys(causes)),
            }
        )
    return reviews


def _guardrail_comparison(
    *,
    date_rows: Sequence[Mapping[str, object]],
    comparison_rows: Sequence[Mapping[str, str]],
    event_rows: Sequence[Mapping[str, str]],
    group_reviews: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    class_by_group = {
        (str(row["group_type"]), str(row["group_name"])): str(row["concentration_class"])
        for row in group_reviews
    }
    date_by_key = {
        (str(row["group_type"]), str(row["group_name"]), str(row["date"])): row
        for row in date_rows
    }
    weighted_events = [row for row in event_rows if row.get("weighted_event_date")]
    bos_events = [row for row in weighted_events if row["event_family"] == "BOS"]
    reset_events = [row for row in weighted_events if row["event_family"] == "RESET"]
    trend_keys = {
        (row["group_type"], row["group_name"], row["date"])
        for row in comparison_rows
        if row.get("weighted_trend_classification") not in (None, "")
    }
    thin_keys = {
        key
        for key in date_by_key
        if class_by_group[key[:2]] == "STRUCTURALLY_THIN"
    }
    healthy_keys = {
        key
        for key in date_by_key
        if class_by_group[key[:2]] == "HEALTHY_WEIGHTED_GROUP"
    }
    results: list[dict[str, object]] = []
    for candidate in GUARDRAIL_CANDIDATES:
        usable = {
            key: guardrail_date_usable(
                candidate,
                eligible_positive_weight_member_count=int(
                    row["eligible_positive_weight_member_count"]
                ),
                effective_member_count=float(row["effective_member_count"]),
            )
            for key, row in date_by_key.items()
        }
        suppressed = {key for key, is_usable in usable.items() if not is_usable}
        affected_groups = {key[:2] for key in suppressed}

        def event_retained(event: Mapping[str, str]) -> bool:
            key = (
                event["group_type"],
                event["group_name"],
                event["weighted_event_date"],
            )
            return usable.get(key, False)

        bos_retained = sum(event_retained(event) for event in bos_events)
        reset_retained = sum(event_retained(event) for event in reset_events)
        trend_retained = sum(usable.get(key, False) for key in trend_keys)
        results.append(
            {
                "candidate": candidate,
                "description": {
                    "A": "NO_GUARDRAIL",
                    "B": "MINIMUM_TWO_EFFECTIVE_MEMBERS",
                    "C": "MINIMUM_EFFECTIVE_MEMBER_COUNT_1_5",
                    "D": "COMBINED_CONSERVATIVE",
                }[candidate],
                "total_group_date_count": len(usable),
                "usable_group_date_count": len(usable) - len(suppressed),
                "usable_group_date_share": (len(usable) - len(suppressed)) / len(usable),
                "suppressed_group_date_count": len(suppressed),
                "suppressed_group_date_share": len(suppressed) / len(usable),
                "groups_affected_count": len(affected_groups),
                "groups_affected": "|".join(f"{group_type}:{group_name}" for group_type, group_name in sorted(affected_groups)),
                "bos_event_count": len(bos_events),
                "bos_retained_count": bos_retained,
                "bos_suppressed_count": len(bos_events) - bos_retained,
                "reset_event_count": len(reset_events),
                "reset_retained_count": reset_retained,
                "reset_suppressed_count": len(reset_events) - reset_retained,
                "trend_state_count": len(trend_keys),
                "trend_state_retained_count": trend_retained,
                "trend_state_suppressed_count": len(trend_keys) - trend_retained,
                "trend_classification_coverage": trend_retained / len(trend_keys) if trend_keys else 0.0,
                "structurally_thin_dates_filtered_pct": (
                    100.0 * len(suppressed & thin_keys) / len(thin_keys)
                    if thin_keys else 0.0
                ),
                "healthy_group_dates_filtered_pct": (
                    100.0 * len(suppressed & healthy_keys) / len(healthy_keys)
                    if healthy_keys else 0.0
                ),
            }
        )
    return results


def run_model_review(
    *,
    phase3_dir: Path,
    taxonomy_csv: Path,
    taxonomy_version: str,
    price_db: Path,
    market: str | None,
    output_dir: Path,
) -> dict[str, object]:
    allowed_root = Path("temp/datacenter_effective_weight_model_review").resolve()
    resolved_output = output_dir.resolve()
    try:
        resolved_output.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"output-dir must be under {allowed_root}") from exc
    resolved_output.mkdir(parents=True, exist_ok=True)

    phase3_summary = json.loads((phase3_dir / "summary.json").read_text(encoding="utf-8"))
    comparison_rows = _read_csv(phase3_dir / "group_date_structure_comparison.csv")
    phase3_group_rows = _read_csv(phase3_dir / "group_summary.csv")
    event_rows = _read_csv(phase3_dir / "event_comparison.csv")
    phase3_largest = _read_csv(phase3_dir / "largest_changes.csv")
    date_rows, anomalies = _date_diagnostics(
        comparison_rows=comparison_rows,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version=taxonomy_version,
        price_db=price_db,
        market=market,
        comparison_end_date=str(phase3_summary["comparison_end_date"]),
    )
    if phase3_summary.get("status") != "OK":
        anomalies.append("PHASE3_STATUS_NOT_OK")
    if len(date_rows) != len(comparison_rows):
        anomalies.append("GROUP_DATE_DIAGNOSTIC_COVERAGE_MISMATCH")
    date_keys = {
        (str(row["group_type"]), str(row["group_name"]), str(row["date"]))
        for row in date_rows
    }
    missing_event_dates = {
        (row["group_type"], row["group_name"], row["weighted_event_date"])
        for row in event_rows
        if row.get("weighted_event_date")
        and (row["group_type"], row["group_name"], row["weighted_event_date"])
        not in date_keys
    }
    if missing_event_dates:
        anomalies.append("WEIGHTED_EVENT_DATE_COVERAGE_MISMATCH")
    group_reviews = _group_reviews(date_rows, phase3_group_rows)
    group_review_by_key = {
        (str(row["group_type"]), str(row["group_name"])): row
        for row in group_reviews
    }
    expected_groups = {(row["group_type"], row["group_name"]) for row in phase3_group_rows}
    if set(group_review_by_key) != expected_groups:
        anomalies.append("GROUP_REVIEW_COVERAGE_MISMATCH")
    candidates = _guardrail_comparison(
        date_rows=date_rows,
        comparison_rows=comparison_rows,
        event_rows=event_rows,
        group_reviews=group_reviews,
    )
    thin = [
        row
        for row in group_reviews
        if row["concentration_class"] in {"STRUCTURALLY_THIN", "NO_EFFECTIVE_COVERAGE"}
    ]
    largest = [
        group_review_by_key[(row["group_type"], row["group_name"])]
        for row in phase3_largest
        if (row["group_type"], row["group_name"]) in group_review_by_key
    ]
    class_counts = Counter(str(row["concentration_class"]) for row in group_reviews)
    top10_class_counts = Counter(
        str(row["concentration_class"]) for row in largest[:10]
    )
    technical_conclusion = (
        "GUARDRAIL RECOMMENDED FOR REVIEW"
        if class_counts["STRUCTURALLY_THIN"] or class_counts["NO_EFFECTIVE_COVERAGE"]
        else "CURRENT V1 INTERNALLY CONSISTENT"
    )
    summary: dict[str, object] = {
        "status": "OK" if not anomalies else "ANOMALY",
        "taxonomy_version": taxonomy_version,
        "comparison_start_date": phase3_summary["comparison_start_date"],
        "comparison_end_date": phase3_summary["comparison_end_date"],
        "source_phase3_status": phase3_summary.get("status"),
        "group_count": len(group_reviews),
        "group_date_count": len(date_rows),
        "concentration_class_counts": {
            name: class_counts[name] for name in CONCENTRATION_CLASSES
        },
        "largest_10_structural_change_class_counts": dict(sorted(top10_class_counts.items())),
        "narrow_current_taxonomy_groups": [
            f"{row['group_type']}:{row['group_name']}"
            for row in group_reviews
            if "NARROW_CURRENT_TAXONOMY" in str(row["mechanical_causes"])
        ],
        "guardrail_candidates": candidates,
        "technical_conclusion": technical_conclusion,
        "weight_constants_changed": False,
        "production_mutation": False,
        "anomalies": anomalies,
    }
    _write_csv(resolved_output / "group_model_review.csv", group_reviews)
    _write_csv(resolved_output / "guardrail_candidate_comparison.csv", candidates)
    _write_csv(resolved_output / "thin_group_diagnostics.csv", thin)
    _write_csv(resolved_output / "largest_structural_changes.csv", largest)
    (resolved_output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
