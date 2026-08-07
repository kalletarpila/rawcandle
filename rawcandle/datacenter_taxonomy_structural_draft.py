from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from analysis.datacenter_indices.taxonomy import (
    DATACENTER_TAXONOMY_REQUIRED_COLUMNS,
    DatacenterTaxonomyRow,
    load_datacenter_taxonomy_csv,
)
from rawcandle.datacenter_taxonomy_change_orchestrator import build_taxonomy_diff


@dataclass(frozen=True)
class DraftMembership:
    ticker: str
    layer: str
    subindustry: str
    report_group_status: str
    is_primary: int
    role_weight: float = 1.0
    notes: str = ""


@dataclass(frozen=True)
class StructuralDraftRequest:
    base_taxonomy_csv: Path
    base_taxonomy_version: str
    draft_taxonomy_version: str
    output_dir: Path
    primary_memberships: tuple[DraftMembership, ...]
    secondary_memberships: tuple[DraftMembership, ...] = ()
    excluded_tickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructuralDraftResult:
    output_dir: Path
    draft_csv: Path
    change_log_csv: Path
    added_tickers_csv: Path
    changed_memberships_csv: Path
    structural_changes_csv: Path
    validation_summary_json: Path
    validation_summary: dict[str, object]


def build_structural_taxonomy_draft(request: StructuralDraftRequest) -> StructuralDraftResult:
    base_rows = load_datacenter_taxonomy_csv(
        request.base_taxonomy_csv,
        expected_taxonomy_version=request.base_taxonomy_version,
    )
    excluded = {_ticker(ticker) for ticker in request.excluded_tickers}
    rows = [_row_to_dict(row, request.draft_taxonomy_version) for row in base_rows]
    base_tickers = {row.ticker for row in base_rows}
    existing_keys = {_membership_key(row) for row in rows}
    added_tickers: set[str] = set()
    changed_memberships: list[dict[str, str]] = []
    change_log: list[dict[str, str]] = []
    secondary_added = 0
    secondary_skipped: list[dict[str, str]] = []

    for membership in request.primary_memberships:
        _validate_requested_membership(membership, excluded=excluded, expected_primary=1)
        ticker = _ticker(membership.ticker)
        previous_primary = _primary_row(rows, ticker)
        target_key = _membership_key_from_values(ticker, membership.layer, membership.subindustry)
        if previous_primary is not None and _membership_key(previous_primary) != target_key:
            secondary_membership = DraftMembership(
                ticker=ticker,
                layer=membership.layer,
                subindustry=membership.subindustry,
                report_group_status=membership.report_group_status,
                is_primary=0,
                role_weight=membership.role_weight,
                notes=membership.notes,
            )
            if target_key in {_membership_key(row) for row in rows}:
                secondary_skipped.append(
                    {
                        "ticker": ticker,
                        "layer": membership.layer,
                        "subindustry": membership.subindustry,
                        "reason": "membership_already_exists",
                    }
                )
                continue
            _upsert_membership_row(
                rows,
                secondary_membership,
                request.draft_taxonomy_version,
                force_primary=False,
            )
            secondary_added += 1
            changed_memberships.append(
                {
                    "change_type": "secondary_membership_added",
                    "ticker": ticker,
                    "from_layer": "",
                    "from_subindustry": "",
                    "to_layer": membership.layer,
                    "to_subindustry": membership.subindustry,
                    "status": membership.report_group_status,
                }
            )
            change_log.append(
                {
                    "change_type": "primary_preserved_secondary_membership_added",
                    "ticker": ticker,
                    "layer": membership.layer,
                    "subindustry": membership.subindustry,
                    "status": membership.report_group_status,
                    "is_primary": "0",
                }
            )
            continue
        action = _upsert_membership_row(
            rows,
            membership,
            request.draft_taxonomy_version,
            force_primary=True,
        )
        existing_keys.add(target_key)
        if ticker not in base_tickers:
            added_tickers.add(ticker)
        change_log.append(
            {
                "change_type": action,
                "ticker": ticker,
                "layer": membership.layer,
                "subindustry": membership.subindustry,
                "status": membership.report_group_status,
                "is_primary": "1",
            }
        )

    for membership in request.secondary_memberships:
        _validate_requested_membership(membership, excluded=excluded, expected_primary=0)
        ticker = _ticker(membership.ticker)
        if ticker not in {_ticker(row["ticker"]) for row in rows}:
            secondary_skipped.append(
                {
                    "ticker": ticker,
                    "layer": membership.layer,
                    "subindustry": membership.subindustry,
                    "reason": "ticker_missing_after_primary_processing",
                }
            )
            continue
        key = _membership_key_from_values(ticker, membership.layer, membership.subindustry)
        if key in {_membership_key(row) for row in rows}:
            secondary_skipped.append(
                {
                    "ticker": ticker,
                    "layer": membership.layer,
                    "subindustry": membership.subindustry,
                    "reason": "membership_already_exists",
                }
            )
            continue
        _upsert_membership_row(
            rows,
            membership,
            request.draft_taxonomy_version,
            force_primary=False,
        )
        secondary_added += 1
        changed_memberships.append(
            {
                "change_type": "secondary_membership_added",
                "ticker": ticker,
                "from_layer": "",
                "from_subindustry": "",
                "to_layer": membership.layer,
                "to_subindustry": membership.subindustry,
                "status": membership.report_group_status,
            }
        )
        change_log.append(
            {
                "change_type": "secondary_membership_added",
                "ticker": ticker,
                "layer": membership.layer,
                "subindustry": membership.subindustry,
                "status": membership.report_group_status,
                "is_primary": "0",
            }
        )

    output_dir = request.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    draft_csv = output_dir / "datacenter_taxonomy_full_v3.csv"
    _write_taxonomy_csv(draft_csv, rows)
    draft_rows = load_datacenter_taxonomy_csv(
        draft_csv,
        expected_taxonomy_version=request.draft_taxonomy_version,
    )
    diff = build_taxonomy_diff(
        current_taxonomy_csv=request.base_taxonomy_csv,
        current_taxonomy_version=request.base_taxonomy_version,
        proposed_taxonomy_csv=draft_csv,
        proposed_taxonomy_version=request.draft_taxonomy_version,
    )
    validation = _build_validation_summary(
        request=request,
        base_rows=base_rows,
        draft_rows=draft_rows,
        diff=diff,
        added_tickers=added_tickers,
        changed_memberships=changed_memberships,
        secondary_added=secondary_added,
        secondary_skipped=secondary_skipped,
    )

    change_log_csv = output_dir / "change_log.csv"
    added_tickers_csv = output_dir / "added_tickers.csv"
    changed_memberships_csv = output_dir / "changed_memberships.csv"
    structural_changes_csv = output_dir / "structural_changes.csv"
    validation_summary_json = output_dir / "validation_summary.json"
    _write_dict_csv(change_log_csv, change_log, ["change_type", "ticker", "layer", "subindustry", "status", "is_primary"])
    _write_dict_csv(
        added_tickers_csv,
        [{"ticker": ticker} for ticker in sorted(added_tickers)],
        ["ticker"],
    )
    _write_dict_csv(
        changed_memberships_csv,
        changed_memberships + [
            {
                "change_type": "secondary_membership_skipped",
                "ticker": item["ticker"],
                "from_layer": "",
                "from_subindustry": "",
                "to_layer": item["layer"],
                "to_subindustry": item["subindustry"],
                "status": item["reason"],
            }
            for item in secondary_skipped
        ],
        ["change_type", "ticker", "from_layer", "from_subindustry", "to_layer", "to_subindustry", "status"],
    )
    structural_rows = [
        {"change_type": "layer_added", "name": layer}
        for layer in diff["added_layers"]
    ] + [
        {"change_type": "subindustry_added", "name": subindustry}
        for subindustry in diff["added_subindustries"]
    ]
    _write_dict_csv(structural_changes_csv, structural_rows, ["change_type", "name"])
    validation_summary_json.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StructuralDraftResult(
        output_dir=output_dir,
        draft_csv=draft_csv,
        change_log_csv=change_log_csv,
        added_tickers_csv=added_tickers_csv,
        changed_memberships_csv=changed_memberships_csv,
        structural_changes_csv=structural_changes_csv,
        validation_summary_json=validation_summary_json,
        validation_summary=validation,
    )


def ai_software_v3_request(
    *,
    base_taxonomy_csv: Path = Path("data/datacenter_taxonomy_full_v2_1.csv"),
    output_dir: Path = Path("temp/datacenter_taxonomy_v3_ai_software_layer"),
) -> StructuralDraftRequest:
    layer = "AI software & data workloads"
    primary = [
        ("PLTR", "Enterprise AI operating platforms", "CORE"),
        ("AI", "Enterprise AI operating platforms", "CORE"),
        ("IBM", "Enterprise AI operating platforms", "EXTENDED"),
        ("BBAI", "Enterprise AI operating platforms", "WATCH_ONLY"),
        ("MDB", "AI data cloud / vector data platforms", "CORE"),
        ("CFLT", "AI data cloud / vector data platforms", "EXTENDED"),
        ("TDC", "AI data cloud / vector data platforms", "EXTENDED"),
        ("CRM", "Agentic automation / workflow AI", "CORE"),
        ("PATH", "Agentic automation / workflow AI", "CORE"),
        ("TEAM", "Agentic automation / workflow AI", "EXTENDED"),
        ("GTLB", "Agentic automation / workflow AI", "EXTENDED"),
        ("MNDY", "Agentic automation / workflow AI", "EXTENDED"),
        ("NET", "AI edge delivery / inference gateways", "CORE"),
        ("AKAM", "AI edge delivery / inference gateways", "EXTENDED"),
        ("FSLY", "AI edge delivery / inference gateways", "WATCH_ONLY"),
        ("APP", "Vertical AI applications / monetization engines", "CORE"),
        ("ADBE", "Vertical AI applications / monetization engines", "EXTENDED"),
        ("TEM", "Vertical AI applications / monetization engines", "EXTENDED"),
        ("DUOL", "Vertical AI applications / monetization engines", "EXTENDED"),
        ("UPST", "Vertical AI applications / monetization engines", "EXTENDED"),
        ("SOUN", "Vertical AI applications / monetization engines", "WATCH_ONLY"),
    ]
    secondary = [
        ("SNOW", "AI data cloud / vector data platforms", "EXTENDED"),
        ("ESTC", "AI data cloud / vector data platforms", "EXTENDED"),
        ("DDOG", "AI observability / agent operations", "EXTENDED"),
        ("DT", "AI observability / agent operations", "EXTENDED"),
        ("NOW", "Agentic automation / workflow AI", "EXTENDED"),
        ("GTLB", "AI observability / agent operations", "EXTENDED"),
        ("MSFT", "Agentic automation / workflow AI", "EXTENDED"),
        ("GOOGL", "AI data cloud / vector data platforms", "EXTENDED"),
        ("AMZN", "AI edge delivery / inference gateways", "EXTENDED"),
        ("ORCL", "AI data cloud / vector data platforms", "EXTENDED"),
        ("PANW", "AI observability / agent operations", "EXTENDED"),
        ("FTNT", "AI edge delivery / inference gateways", "EXTENDED"),
        ("CRWD", "AI observability / agent operations", "EXTENDED"),
    ]
    return StructuralDraftRequest(
        base_taxonomy_csv=base_taxonomy_csv,
        base_taxonomy_version="DC_TAXONOMY_FULL_V2_1",
        draft_taxonomy_version="DC_TAXONOMY_FULL_V3",
        output_dir=output_dir,
        primary_memberships=tuple(
            DraftMembership(
                ticker=ticker,
                layer=layer,
                subindustry=subindustry,
                report_group_status=status,
                is_primary=1,
                notes="v3_draft: AI software and data workload exposure",
            )
            for ticker, subindustry, status in primary
        ),
        secondary_memberships=tuple(
            DraftMembership(
                ticker=ticker,
                layer=layer,
                subindustry=subindustry,
                report_group_status=status,
                is_primary=0,
                notes="v3_draft: secondary AI software and data workload exposure",
            )
            for ticker, subindustry, status in secondary
        ),
        excluded_tickers=("AAPL", "TSLA", "META", "NFLX", "SHOP", "UBER", "ABNB", "SEZL", "RDDT", "HOOD"),
    )


def _validate_requested_membership(
    membership: DraftMembership,
    *,
    excluded: set[str],
    expected_primary: int,
) -> None:
    ticker = _ticker(membership.ticker)
    if ticker in excluded:
        raise ValueError(f"excluded ticker requested for draft membership: {ticker}")
    if membership.is_primary != expected_primary:
        raise ValueError(f"{ticker}: expected is_primary={expected_primary}, got {membership.is_primary}")


def _row_to_dict(row: DatacenterTaxonomyRow, taxonomy_version: str) -> dict[str, str]:
    return {
        "taxonomy_version": taxonomy_version,
        "ticker": row.ticker,
        "layer": row.layer,
        "subindustry": row.subindustry,
        "report_group_status": row.report_group_status,
        "is_primary": str(row.is_primary),
        "role_weight": _format_weight(row.role_weight),
        "notes": row.notes or "",
    }


def _upsert_membership_row(
    rows: list[dict[str, str]],
    membership: DraftMembership,
    taxonomy_version: str,
    *,
    force_primary: bool,
) -> str:
    ticker = _ticker(membership.ticker)
    key = _membership_key_from_values(ticker, membership.layer, membership.subindustry)
    for row in rows:
        if _membership_key(row) == key:
            row["report_group_status"] = membership.report_group_status
            row["is_primary"] = "1" if force_primary else str(membership.is_primary)
            row["role_weight"] = _format_weight(membership.role_weight)
            row["notes"] = membership.notes
            return "membership_updated"
    rows.append(
        {
            "taxonomy_version": taxonomy_version,
            "ticker": ticker,
            "layer": membership.layer,
            "subindustry": membership.subindustry,
            "report_group_status": membership.report_group_status,
            "is_primary": "1" if force_primary else str(membership.is_primary),
            "role_weight": _format_weight(membership.role_weight),
            "notes": membership.notes,
        }
    )
    return "membership_added"


def _build_validation_summary(
    *,
    request: StructuralDraftRequest,
    base_rows: list[DatacenterTaxonomyRow],
    draft_rows: list[DatacenterTaxonomyRow],
    diff: dict[str, object],
    added_tickers: set[str],
    changed_memberships: list[dict[str, str]],
    secondary_added: int,
    secondary_skipped: list[dict[str, str]],
) -> dict[str, object]:
    errors = _validate_draft_rows(request=request, base_rows=base_rows, draft_rows=draft_rows)
    primary_changed = [item for item in changed_memberships if item["change_type"] == "primary_membership_changed"]
    return {
        "validation_status": "OK" if not errors else "FAILED",
        "errors": errors,
        "base_taxonomy_csv": str(request.base_taxonomy_csv),
        "base_taxonomy_version": request.base_taxonomy_version,
        "draft_taxonomy_version": request.draft_taxonomy_version,
        "draft_row_count": len(draft_rows),
        "base_row_count": len(base_rows),
        "new_entity_count": len(added_tickers),
        "new_membership_count": len(draft_rows) - len(base_rows),
        "changed_primary_membership_count": len(primary_changed),
        "secondary_membership_added_count": secondary_added,
        "secondary_membership_skipped_count": len(secondary_skipped),
        "secondary_memberships_skipped": secondary_skipped,
        "added_layers": diff["added_layers"],
        "added_subindustries": diff["added_subindustries"],
        "removed_layers": diff["removed_layers"],
        "removed_subindustries": diff["removed_subindustries"],
        "removed_tickers": diff["removed_tickers"],
        "added_tickers": sorted(added_tickers),
        "changed_primary_memberships": primary_changed,
        "computational_taxonomy_change": bool(diff["structural_change_detected"]),
        "production_activation_performed": False,
        "ordering_rule": "Preserve base CSV row order; append requested V3 primary rows in proposal order, then requested secondary rows in proposal order.",
    }


def _validate_draft_rows(
    *,
    request: StructuralDraftRequest,
    base_rows: list[DatacenterTaxonomyRow],
    draft_rows: list[DatacenterTaxonomyRow],
) -> list[str]:
    errors: list[str] = []
    primary_counts: dict[str, int] = {}
    subindustry_layers: dict[str, set[str]] = {}
    for row in draft_rows:
        primary_counts[row.ticker] = primary_counts.get(row.ticker, 0) + int(row.is_primary == 1)
        subindustry_layers.setdefault(row.subindustry, set()).add(row.layer)
    duplicate_primary = sorted(ticker for ticker, count in primary_counts.items() if count > 1)
    missing_primary = sorted(ticker for ticker, count in primary_counts.items() if count == 0)
    if duplicate_primary:
        errors.append("duplicate primary membership for tickers: " + ", ".join(duplicate_primary))
    if missing_primary:
        errors.append("missing primary membership for tickers: " + ", ".join(missing_primary))
    invalid_subindustries = {
        name: sorted(layers) for name, layers in subindustry_layers.items() if len(layers) > 1
    }
    if invalid_subindustries:
        errors.append("subindustry assigned to multiple layers: " + json.dumps(invalid_subindustries, sort_keys=True))
    base_tickers = {row.ticker for row in base_rows}
    draft_tickers = {row.ticker for row in draft_rows}
    missing_base_tickers = sorted(base_tickers - draft_tickers)
    if missing_base_tickers:
        errors.append("base tickers deleted: " + ", ".join(missing_base_tickers))
    requested_primary = {_membership_key_from_values(_ticker(row.ticker), row.layer, row.subindustry): row for row in request.primary_memberships}
    draft_keys = {_membership_key(row) for row in [_row_to_dict(row, row.taxonomy_version) for row in draft_rows]}
    for key, membership in requested_primary.items():
        if key not in draft_keys:
            errors.append(f"requested primary membership missing: {membership.ticker}")
    excluded = {_ticker(ticker) for ticker in request.excluded_tickers}
    draft_excluded_new_layer = sorted(
        row.ticker
        for row in draft_rows
        if row.ticker in excluded and row.layer == "AI software & data workloads"
    )
    if draft_excluded_new_layer:
        errors.append("excluded tickers added to V3 layer: " + ", ".join(draft_excluded_new_layer))
    return errors


def _primary_row(rows: list[dict[str, str]], ticker: str) -> dict[str, str] | None:
    matches = [row for row in rows if _ticker(row["ticker"]) == ticker and row["is_primary"] == "1"]
    if len(matches) > 1:
        raise ValueError(f"duplicate primary membership before draft processing: {ticker}")
    return matches[0] if matches else None


def _write_taxonomy_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    _write_dict_csv(path, list(rows), list(DATACENTER_TAXONOMY_REQUIRED_COLUMNS))


def _write_dict_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _ticker(value: str) -> str:
    return value.strip().upper()


def _membership_key(row: dict[str, str]) -> tuple[str, str, str]:
    return _membership_key_from_values(row["ticker"], row["layer"], row["subindustry"])


def _membership_key_from_values(ticker: str, layer: str, subindustry: str) -> tuple[str, str, str]:
    return (_ticker(ticker), layer.strip(), subindustry.strip())


def _format_weight(value: float) -> str:
    return f"{value:.1f}"
