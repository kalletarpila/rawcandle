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

    assert len(rows) == 329
    assert rows[0].taxonomy_version == "DC_TAXONOMY_FULL_V1"
    assert rows[0].notes is None


def test_full_taxonomy_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert len(rows) == 329
    assert len({row.ticker for row in rows}) == 236
    assert len({row.layer for row in rows}) == 16
    assert len({row.subindustry for row in rows}) == 37


def test_full_taxonomy_report_group_status_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    status_counts = Counter(row.report_group_status for row in rows)

    assert status_counts["CORE"] == 154
    assert status_counts["EXTENDED"] == 137
    assert status_counts["WATCH_ONLY"] == 38
    assert status_counts["TOO_SMALL"] == 0


def test_full_taxonomy_is_primary_counts_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    primary_counts = Counter(row.is_primary for row in rows)

    assert primary_counts[1] == 236
    assert primary_counts[0] == 93


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

    assert {
        "MP",
        "UUUU",
        "NB",
        "IPX",
        "USAR",
        "ATI",
        "HWM",
        "CRS",
        "ALOY",
        "ASPI",
        "ILU.AX",
    }.issubset(tickers)


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

    assert {"GLW", "COHR", "FN", "APD", "ATI", "AXTI", "IQE"}.issubset(tickers)


def test_full_taxonomy_alumiini_ja_teras_contains_cenx():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Upstream materials" and row.subindustry == "Alumiini ja teräs"
    }

    assert "CENX" in tickers


def test_full_taxonomy_foundry_and_packaging_contains_umc():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Semiconductor manufacturing"
        and row.subindustry == "Foundry & packaging / OSAT"
    }

    assert "UMC" in tickers


def test_full_taxonomy_test_and_process_control_contains_aehr():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Semiconductor manufacturing"
        and row.subindustry == "Testaus / prosessikontrolli"
    }

    assert "AEHR" in tickers


def test_full_taxonomy_semicap_contains_lpkf():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Semiconductor manufacturing"
        and row.subindustry == "Puolijohdelaitteet / semicap"
    }

    assert "LPKF" in tickers


def test_full_taxonomy_power_conversion_contains_amsc():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Electrical & power systems"
        and row.subindustry == "Power conversion & precision power"
    }

    assert "AMSC" in tickers


def test_full_taxonomy_ai_cloud_subindustry_exists_with_expected_tickers():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    tickers = {
        row.ticker
        for row in rows
        if row.layer == "Pilvi"
        and row.subindustry == "AI cloud / neocloud infrastructure"
    }

    assert tickers == {"NBIS", "CRWV", "IREN", "HUT"}


def test_full_taxonomy_hyperscalers_subindustry_still_exists():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert any(
        row.layer == "Pilvi"
        and row.subindustry == "Hyperscalers / cloud demand owners"
        for row in rows
    )


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


def test_full_taxonomy_ati_primary_flags_match_expected():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    glass_row = next(
        row
        for row in rows
        if row.ticker == "ATI"
        and row.layer == "Upstream materials"
        and row.subindustry == "Lasi / optical materials / specialty glass"
    )
    special_metals_row = next(
        row
        for row in rows
        if row.ticker == "ATI"
        and row.layer == "Upstream materials"
        and row.subindustry == "Erikoismetallit"
    )

    assert glass_row.is_primary == 1
    assert special_metals_row.is_primary == 0


def test_full_taxonomy_new_single_occurrence_tickers_are_primary():
    rows = load_datacenter_taxonomy_csv(
        FULL_CSV_PATH,
        expected_taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    expected_rows = {
        ("APD", "Upstream materials", "Lasi / optical materials / specialty glass"),
        ("CENX", "Upstream materials", "Alumiini ja teräs"),
        ("HWM", "Upstream materials", "Erikoismetallit"),
        ("CRS", "Upstream materials", "Erikoismetallit"),
        ("UMC", "Semiconductor manufacturing", "Foundry & packaging / OSAT"),
        ("ALOY", "Upstream materials", "Erikoismetallit"),
        ("ASPI", "Upstream materials", "Erikoismetallit"),
        ("ILU.AX", "Upstream materials", "Erikoismetallit"),
        ("AXTI", "Upstream materials", "Lasi / optical materials / specialty glass"),
        ("IQE", "Upstream materials", "Lasi / optical materials / specialty glass"),
        ("AEHR", "Semiconductor manufacturing", "Testaus / prosessikontrolli"),
        ("LPKF", "Semiconductor manufacturing", "Puolijohdelaitteet / semicap"),
        ("AMSC", "Electrical & power systems", "Power conversion & precision power"),
        ("NBIS", "Pilvi", "AI cloud / neocloud infrastructure"),
        ("CRWV", "Pilvi", "AI cloud / neocloud infrastructure"),
        ("IREN", "Pilvi", "AI cloud / neocloud infrastructure"),
        ("HUT", "Pilvi", "AI cloud / neocloud infrastructure"),
    }

    actual_rows = {
        (row.ticker, row.layer, row.subindustry): row.is_primary
        for row in rows
        if (row.ticker, row.layer, row.subindustry) in expected_rows
    }

    assert actual_rows == {
        ("APD", "Upstream materials", "Lasi / optical materials / specialty glass"): 1,
        ("CENX", "Upstream materials", "Alumiini ja teräs"): 1,
        ("HWM", "Upstream materials", "Erikoismetallit"): 1,
        ("CRS", "Upstream materials", "Erikoismetallit"): 1,
        ("UMC", "Semiconductor manufacturing", "Foundry & packaging / OSAT"): 1,
        ("ALOY", "Upstream materials", "Erikoismetallit"): 1,
        ("ASPI", "Upstream materials", "Erikoismetallit"): 1,
        ("ILU.AX", "Upstream materials", "Erikoismetallit"): 1,
        ("AXTI", "Upstream materials", "Lasi / optical materials / specialty glass"): 1,
        ("IQE", "Upstream materials", "Lasi / optical materials / specialty glass"): 1,
        ("AEHR", "Semiconductor manufacturing", "Testaus / prosessikontrolli"): 1,
        ("LPKF", "Semiconductor manufacturing", "Puolijohdelaitteet / semicap"): 1,
        ("AMSC", "Electrical & power systems", "Power conversion & precision power"): 1,
        ("NBIS", "Pilvi", "AI cloud / neocloud infrastructure"): 1,
        ("CRWV", "Pilvi", "AI cloud / neocloud infrastructure"): 1,
        ("IREN", "Pilvi", "AI cloud / neocloud infrastructure"): 1,
        ("HUT", "Pilvi", "AI cloud / neocloud infrastructure"): 1,
    }


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
        "SUMMARY taxonomy_rows=329",
        "SUMMARY unique_tickers=236",
        "SUMMARY layer_count=16",
        "SUMMARY subindustry_count=37",
        "SUMMARY core_rows=154",
        "SUMMARY extended_rows=137",
        "SUMMARY watch_only_rows=38",
        "SUMMARY too_small_rows=0",
        "SUMMARY duplicate_rows=0",
        "SUMMARY validation_status=OK",
    ]
