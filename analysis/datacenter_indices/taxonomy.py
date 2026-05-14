from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


DATACENTER_TAXONOMY_REQUIRED_COLUMNS = (
    "taxonomy_version",
    "ticker",
    "layer",
    "subindustry",
    "report_group_status",
    "is_primary",
    "role_weight",
    "notes",
)

DATACENTER_TAXONOMY_STATUSES = {
    "CORE",
    "EXTENDED",
    "WATCH_ONLY",
    "TOO_SMALL",
}


@dataclass(frozen=True)
class DatacenterTaxonomyRow:
    taxonomy_version: str
    ticker: str
    layer: str
    subindustry: str
    report_group_status: str
    is_primary: int
    role_weight: float
    notes: str | None


def _normalize_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_datacenter_taxonomy_csv(
    path: str | Path,
    expected_taxonomy_version: str | None = None,
) -> list[DatacenterTaxonomyRow]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if fieldnames != DATACENTER_TAXONOMY_REQUIRED_COLUMNS:
            raise ValueError(
                "Invalid taxonomy CSV columns: "
                f"expected {list(DATACENTER_TAXONOMY_REQUIRED_COLUMNS)}, got {list(fieldnames)}"
            )

        rows: list[DatacenterTaxonomyRow] = []
        seen_keys: set[tuple[str, str, str, str]] = set()
        for row_number, raw_row in enumerate(reader, start=2):
            taxonomy_version = _normalize_str(raw_row["taxonomy_version"])
            ticker = _normalize_str(raw_row["ticker"]).upper()
            layer = _normalize_str(raw_row["layer"])
            subindustry = _normalize_str(raw_row["subindustry"])
            report_group_status = _normalize_str(raw_row["report_group_status"])
            is_primary_raw = _normalize_str(raw_row["is_primary"])
            role_weight_raw = _normalize_str(raw_row["role_weight"])
            notes_raw = _normalize_str(raw_row["notes"])

            if not taxonomy_version:
                raise ValueError(f"Row {row_number}: taxonomy_version must not be empty")
            if not ticker:
                raise ValueError(f"Row {row_number}: ticker must not be empty")
            if not layer:
                raise ValueError(f"Row {row_number}: layer must not be empty")
            if not subindustry:
                raise ValueError(f"Row {row_number}: subindustry must not be empty")
            if report_group_status not in DATACENTER_TAXONOMY_STATUSES:
                raise ValueError(
                    f"Row {row_number}: invalid report_group_status '{report_group_status}'"
                )

            try:
                is_primary = int(is_primary_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Row {row_number}: invalid is_primary '{is_primary_raw}'"
                ) from exc
            if is_primary not in (0, 1):
                raise ValueError(
                    f"Row {row_number}: is_primary must be 0 or 1, got {is_primary}"
                )

            try:
                role_weight = float(role_weight_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Row {row_number}: invalid role_weight '{role_weight_raw}'"
                ) from exc
            if role_weight <= 0:
                raise ValueError(
                    f"Row {row_number}: role_weight must be greater than 0, got {role_weight}"
                )

            if (
                expected_taxonomy_version is not None
                and taxonomy_version != expected_taxonomy_version
            ):
                raise ValueError(
                    "Row "
                    f"{row_number}: taxonomy_version '{taxonomy_version}' does not match "
                    f"expected '{expected_taxonomy_version}'"
                )

            duplicate_key = (taxonomy_version, ticker, layer, subindustry)
            if duplicate_key in seen_keys:
                raise ValueError(
                    "Row "
                    f"{row_number}: duplicate taxonomy row for key {duplicate_key}"
                )
            seen_keys.add(duplicate_key)

            rows.append(
                DatacenterTaxonomyRow(
                    taxonomy_version=taxonomy_version,
                    ticker=ticker,
                    layer=layer,
                    subindustry=subindustry,
                    report_group_status=report_group_status,
                    is_primary=is_primary,
                    role_weight=role_weight,
                    notes=notes_raw or None,
                )
            )

    return rows
