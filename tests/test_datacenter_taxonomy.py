from __future__ import annotations

from pathlib import Path

import pytest

from analysis.datacenter_indices import load_datacenter_taxonomy_csv
from run_datacenter_taxonomy_validate import main as validate_main


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CSV_PATH = REPO_ROOT / "data" / "datacenter_ecosystem_taxonomy_v1.csv"


def _write_csv(tmp_path, content: str) -> Path:
    path = tmp_path / "taxonomy.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_loader_accepts_seed_csv():
    rows = load_datacenter_taxonomy_csv(
        SEED_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_V1",
    )

    assert len(rows) == 12
    assert rows[0].taxonomy_version == "DC_TAXONOMY_V1"
    assert rows[0].notes is None


def test_loader_normalizes_ticker_to_uppercase(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            'DC_TAXONOMY_V1, vrt ,Cooling,"Air and liquid cooling",CORE,1,1.0,\n'
        ),
    )

    rows = load_datacenter_taxonomy_csv(csv_path)

    assert rows[0].ticker == "VRT"


def test_loader_rejects_missing_required_columns(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight\n"
        "DC_TAXONOMY_V1,VRT,Cooling,Sub,CORE,1,1.0\n",
    )

    with pytest.raises(ValueError, match="Invalid taxonomy CSV columns"):
        load_datacenter_taxonomy_csv(csv_path)


def test_loader_rejects_invalid_report_group_status(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            "DC_TAXONOMY_V1,VRT,Cooling,Sub,INVALID,1,1.0,\n"
        ),
    )

    with pytest.raises(ValueError, match="invalid report_group_status"):
        load_datacenter_taxonomy_csv(csv_path)


def test_loader_rejects_invalid_is_primary(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            "DC_TAXONOMY_V1,VRT,Cooling,Sub,CORE,2,1.0,\n"
        ),
    )

    with pytest.raises(ValueError, match="is_primary must be 0 or 1"):
        load_datacenter_taxonomy_csv(csv_path)


def test_loader_rejects_role_weight_less_than_or_equal_to_zero(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            "DC_TAXONOMY_V1,VRT,Cooling,Sub,CORE,1,0,\n"
        ),
    )

    with pytest.raises(ValueError, match="role_weight must be greater than 0"):
        load_datacenter_taxonomy_csv(csv_path)


def test_loader_rejects_duplicate_normalized_taxonomy_rows(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            'DC_TAXONOMY_V1,vrt,Cooling,"Air and liquid cooling",CORE,1,1.0,\n'
            ' DC_TAXONOMY_V1 , VRT , Cooling ,"Air and liquid cooling",CORE,1,1.0,\n'
        ),
    )

    with pytest.raises(ValueError, match="duplicate taxonomy row"):
        load_datacenter_taxonomy_csv(csv_path)


def test_loader_allows_same_ticker_in_multiple_layer_subindustry_combinations(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            'DC_TAXONOMY_V1,VRT,Cooling,"Air and liquid cooling",CORE,1,1.0,\n'
            'DC_TAXONOMY_V1,VRT,Electrical & power systems,"UPS, switchgear, PDU",CORE,0,1.0,\n'
        ),
    )

    rows = load_datacenter_taxonomy_csv(csv_path)

    assert len(rows) == 2
    assert {row.layer for row in rows} == {"Cooling", "Electrical & power systems"}


def test_loader_rejects_mismatched_expected_taxonomy_version(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        (
            "taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes\n"
            "DC_TAXONOMY_V1,VRT,Cooling,Sub,CORE,1,1.0,\n"
        ),
    )

    with pytest.raises(ValueError, match="does not match expected"):
        load_datacenter_taxonomy_csv(
            csv_path,
            expected_taxonomy_version="DC_TAXONOMY_V2",
        )


def test_validation_cli_prints_summary_lines_for_seed_csv(capsys):
    exit_code = validate_main(
        [
            "--taxonomy-csv",
            str(SEED_CSV_PATH),
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.strip().splitlines() == [
        "SUMMARY taxonomy_version=DC_TAXONOMY_V1",
        "SUMMARY taxonomy_rows=12",
        "SUMMARY unique_tickers=11",
        "SUMMARY layer_count=5",
        "SUMMARY subindustry_count=8",
        "SUMMARY core_rows=11",
        "SUMMARY extended_rows=0",
        "SUMMARY watch_only_rows=1",
        "SUMMARY too_small_rows=0",
        "SUMMARY duplicate_rows=0",
        "SUMMARY validation_status=OK",
    ]
