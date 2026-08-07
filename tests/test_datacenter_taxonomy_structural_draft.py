from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from analysis.datacenter_indices.taxonomy import load_datacenter_taxonomy_csv
from rawcandle.datacenter_taxonomy_structural_draft import (
    DraftMembership,
    StructuralDraftRequest,
    ai_software_v3_request,
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


def test_existing_primary_membership_is_preserved_and_ai_membership_is_secondary(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        _request(
            tmp_path,
            primary=(DraftMembership("BBB", "AI software", "Operations AI", "CORE", 1),),
        )
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V2")
    bbb_rows = [row for row in rows if row.ticker == "BBB"]
    assert sum(row.is_primary for row in bbb_rows) == 1
    assert next(row for row in bbb_rows if row.is_primary == 1).subindustry == "Observability"
    assert any(row.layer == "AI software" and row.subindustry == "Operations AI" and row.is_primary == 0 for row in bbb_rows)
    assert result.validation_summary["changed_primary_membership_count"] == 0
    assert result.validation_summary["secondary_membership_added_count"] == 1


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


def test_ai_v3_request_preserves_existing_primary_memberships_and_adds_secondary_ai_memberships(tmp_path: Path):
    result = build_structural_taxonomy_draft(
        ai_software_v3_request(output_dir=tmp_path / "draft")
    )

    rows = load_datacenter_taxonomy_csv(result.draft_csv, "DC_TAXONOMY_FULL_V3")
    by_ticker = {}
    for row in rows:
        by_ticker.setdefault(row.ticker, []).append(row)
    expected_base_primary = {
        "SNOW": ("Operations", "Observability / ITSM / data platform"),
        "ESTC": ("Operations", "Observability / ITSM / data platform"),
        "DDOG": ("Operations", "Observability / ITSM / data platform"),
        "DT": ("Operations", "Observability / ITSM / data platform"),
        "NOW": ("Operations", "Observability / ITSM / data platform"),
    }
    expected_secondary = {
        "SNOW": "AI data cloud / vector data platforms",
        "ESTC": "AI data cloud / vector data platforms",
        "DDOG": "AI observability / agent operations",
        "DT": "AI observability / agent operations",
        "NOW": "Agentic automation / workflow AI",
    }
    extended_secondary = {
        "MSFT": "Agentic automation / workflow AI",
        "GOOGL": "AI data cloud / vector data platforms",
        "AMZN": "AI edge delivery / inference gateways",
        "ORCL": "AI data cloud / vector data platforms",
        "PANW": "AI observability / agent operations",
        "FTNT": "AI edge delivery / inference gateways",
        "CRWD": "AI observability / agent operations",
    }
    watch_only_primary = {
        "BBAI": "Enterprise AI operating platforms",
        "FSLY": "AI edge delivery / inference gateways",
        "SOUN": "Vertical AI applications / monetization engines",
    }
    for ticker, primary in expected_base_primary.items():
        primary_rows = [row for row in by_ticker[ticker] if row.is_primary == 1]
        assert [(row.layer, row.subindustry) for row in primary_rows] == [primary]
        assert any(
            row.layer == "AI software & data workloads"
            and row.subindustry == expected_secondary[ticker]
            and row.report_group_status == "CORE"
            and row.is_primary == 0
            for row in by_ticker[ticker]
        )
    for ticker, subindustry in extended_secondary.items():
        assert any(
            row.layer == "AI software & data workloads"
            and row.subindustry == subindustry
            and row.report_group_status == "EXTENDED"
            and row.is_primary == 0
            for row in by_ticker[ticker]
        )
    assert result.validation_summary["changed_primary_membership_count"] == 0
    assert result.validation_summary["secondary_membership_added_count"] == 13
    primary_counts = Counter(row.ticker for row in rows if row.is_primary == 1)
    assert [ticker for ticker, count in primary_counts.items() if count > 1] == []
    assert any(
        row.ticker == "PLTR"
        and row.layer == "AI software & data workloads"
        and row.subindustry == "Enterprise AI operating platforms"
        and row.report_group_status == "CORE"
        and row.is_primary == 1
        for row in rows
    )
    for ticker, subindustry in watch_only_primary.items():
        assert any(
            row.layer == "AI software & data workloads"
            and row.subindustry == subindustry
            and row.report_group_status == "WATCH_ONLY"
            and row.is_primary == 1
            for row in by_ticker[ticker]
        )
    excluded = {"AAPL", "TSLA", "META", "NFLX", "SHOP", "UBER", "ABNB", "SEZL", "RDDT", "HOOD"}
    assert [
        row.ticker
        for row in rows
        if row.ticker in excluded and row.layer == "AI software & data workloads"
    ] == []
