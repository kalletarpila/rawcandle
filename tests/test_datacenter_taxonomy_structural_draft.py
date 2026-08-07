from __future__ import annotations

import csv
from pathlib import Path

import pytest

from analysis.datacenter_indices.taxonomy import load_datacenter_taxonomy_csv
from rawcandle.datacenter_taxonomy_structural_draft import (
    DraftMembership,
    StructuralDraftRequest,
    build_structural_taxonomy_draft,
)


HEADER = "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"


def _write_base(path: Path) -> Path:
    path.write_text(
        HEADER
        + "DC_TAXONOMY_FULL_V1,AAA,Compute,GPU,CORE,1,1.0,base\n"
        + "DC_TAXONOMY_FULL_V1,BBB,Operations,Observability,CORE,1,1.0,base\n"
        + "DC_TAXONOMY_FULL_V1,CCC,Cloud,Hyperscalers,CORE,1,1.0,base\n"
        + "DC_TAXONOMY_FULL_V1,CCC,Operations,Virtualization,CORE,0,1.0,base\n",
        encoding="utf-8",
    )
    return path


def _request(tmp_path: Path, *, primary: tuple[DraftMembership, ...], secondary: tuple[DraftMembership, ...] = ()) -> StructuralDraftRequest:
    return StructuralDraftRequest(
        base_taxonomy_csv=_write_base(tmp_path / "base.csv"),
        base_taxonomy_version="DC_TAXONOMY_FULL_V1",
        draft_taxonomy_version="DC_TAXONOMY_FULL_V2",
        output_dir=tmp_path / "draft",
        primary_memberships=primary,
        secondary_memberships=secondary,
        excluded_tickers=("NOPE",),
    )


def test_structural_draft_adds_new_layer_and_subindustries(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(
                DraftMembership("NEW1", "AI software", "Platforms", "CORE", 1),
                DraftMembership("NEW2", "AI software", "Data", "EXTENDED", 1),
            ),
        )
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V2")
    assert result.validation_summary["validation_status"] == "OK"
    assert result.validation_summary["added_layers"] == ["AI software"]
    assert result.validation_summary["added_subindustries"] == ["Data", "Platforms"]
    assert {row.subindustry for row in rows if row.layer == "AI software"} == {"Platforms", "Data"}


def test_primary_memberships_under_new_subindustries_validate(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(DraftMembership("NEW1", "AI software", "Platforms", "WATCH_ONLY", 1),),
        )
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V2")
    row = next(row for row in rows if row.ticker == "NEW1")
    assert row.layer == "AI software"
    assert row.subindustry == "Platforms"
    assert row.report_group_status == "WATCH_ONLY"
    assert row.is_primary == 1


def test_existing_primary_membership_is_moved_without_duplicate_primary(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(DraftMembership("BBB", "AI software", "Operations AI", "CORE", 1),),
        )
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V2")
    bbb_rows = [row for row in rows if row.ticker == "BBB"]
    assert sum(row.is_primary for row in bbb_rows) == 1
    assert next(row for row in bbb_rows if row.is_primary == 1).subindustry == "Operations AI"
    assert result.validation_summary["changed_primary_membership_count"] == 1


def test_excluded_ticker_is_not_added(tmp_path: Path):
    with pytest.raises(ValueError, match="excluded ticker"):
        build_structural_taxonomy_draft(
            _request(
                tmp_path,
                primary=(DraftMembership("NOPE", "AI software", "Platforms", "CORE", 1),),
            )
        )


def test_watch_only_structural_additions_are_preserved(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(DraftMembership("BBAI", "AI software", "Platforms", "WATCH_ONLY", 1),),
        )
    )

    with result.draft_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(
        row["ticker"] == "BBAI"
        and row["report_group_status"] == "WATCH_ONLY"
        and row["is_primary"] == "1"
        for row in rows
    )


def test_existing_taxonomy_rows_are_preserved_and_secondary_added(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(DraftMembership("NEW1", "AI software", "Platforms", "CORE", 1),),
            secondary=(DraftMembership("CCC", "AI software", "Platforms", "EXTENDED", 0),),
        )
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V2")
    assert any(row.ticker == "AAA" and row.layer == "Compute" and row.is_primary == 1 for row in rows)
    assert any(row.ticker == "CCC" and row.layer == "Cloud" and row.is_primary == 1 for row in rows)
    assert any(row.ticker == "CCC" and row.layer == "AI software" and row.is_primary == 0 for row in rows)
    assert result.validation_summary["secondary_membership_added_count"] == 1
