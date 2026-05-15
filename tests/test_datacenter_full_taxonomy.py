from __future__ import annotations

from collections import Counter
from pathlib import Path

from analysis.datacenter_indices import load_datacenter_taxonomy_csv
from run_datacenter_taxonomy_validate import main as validate_main


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_CSV_PATH = REPO_ROOT / "data" / "datacenter_ecosystem_taxonomy_v1.csv"
FULL_CSV_PATH = REPO_ROOT / "data" / "datacenter_ecosystem_taxonomy_full_v1.csv"


def test_full_taxonomy_csv_loads_successfully():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 310
    assert rows[0].taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert rows[0].notes is None


def test_full_taxonomy_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 310
    assert len({row.ticker for row in rows}) == 218
    assert len({row.layer for row in rows}) == 16
    assert len({row.subindustry for row in rows}) == 36


def test_full_taxonomy_report_group_status_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    status_counts = Counter(row.report_group_status for row in rows)

    assert status_counts["CORE"] == 153
    assert status_counts["EXTENDED"] == 130
    assert status_counts["WATCH_ONLY"] == 27
    assert status_counts["TOO_SMALL"] == 0


def test_full_taxonomy_is_primary_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    primary_counts = Counter(row.is_primary for row in rows)

    assert primary_counts[1] == 218
    assert primary_counts[0] == 92


def test_full_taxonomy_has_no_duplicate_normalized_keys():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    keys = {
        (row.taxonomy_version, row.ticker, row.layer, row.subindustry)
        for row in rows
    }

    assert len(keys) == len(rows)


def test_full_taxonomy_allows_same_ticker_in_multiple_group_combinations():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    vrt_rows = [row for row in rows if row.ticker == "VRT"]

    assert len(vrt_rows) > 1
    assert len({(row.layer, row.subindustry) for row in vrt_rows}) > 1


def test_full_taxonomy_erikoismetallit_contains_expected_tickers():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Upstream materials" and row.subindustry == "Erikoismetallit"
    }

    assert tickers == {"MP", "UUUU", "NB", "IPX", "USAR"}


def test_full_taxonomy_broadened_glass_subindustry_contains_expected_tickers():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Upstream materials"
        and row.subindustry == "Lasi / optical materials / specialty glass"
    }

    assert tickers == {"GLW", "COHR", "FN"}


def test_full_taxonomy_old_glass_subindustry_name_no_longer_exists():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert all(
        row.subindustry != "Lasi / silica / specialty glass"
        for row in rows
    )


def test_full_taxonomy_cohr_primary_flags_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    upstream_row = next(
        row
        for row in rows
        if row.ticker == "COHR"
        and row.layer == "Upstream materials"
        and row.subindustry == "Lasi / optical materials / specialty glass"
    )
    verkot_row = next(
        row
        for row in rows
        if row.ticker == "COHR"
        and row.layer == "Verkot"
        and row.subindustry == "Optiikka / fotoniikka / high-speed connectivity"
    )

    assert upstream_row.is_primary == 1
    assert verkot_row.is_primary == 0


def test_full_taxonomy_fn_primary_flags_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    upstream_row = next(
        row
        for row in rows
        if row.ticker == "FN"
        and row.layer == "Upstream materials"
        and row.subindustry == "Lasi / optical materials / specialty glass"
    )
    verkot_row = next(
        row
        for row in rows
        if row.ticker == "FN"
        and row.layer == "Verkot"
        and row.subindustry == "Optiikka / fotoniikka / high-speed connectivity"
    )

    assert upstream_row.is_primary == 1
    assert verkot_row.is_primary == 0


def test_seed_taxonomy_csv_still_loads_successfully():
    rows = load_datacenter_taxonomy_csv(
        SEED_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_V1",
    )

    assert len(rows) == 12


def test_validation_cli_prints_summary_lines_for_full_csv(capsys):
    exit_code = validate_main(
        [
            "--taxonomy-csv",
            str(FULL_CSV_PATH),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.strip().splitlines() == [
        "SUMMARY taxonomy_version=DC_TAXONOMY_FULL_V1",
        "SUMMARY taxonomy_rows=310",
        "SUMMARY unique_tickers=218",
        "SUMMARY layer_count=16",
        "SUMMARY subindustry_count=36",
        "SUMMARY core_rows=153",
        "SUMMARY extended_rows=130",
        "SUMMARY watch_only_rows=27",
        "SUMMARY too_small_rows=0",
        "SUMMARY duplicate_rows=0",
        "SUMMARY validation_status=OK",
    ]
