from __future__ import annotations

from datetime import date, timedelta
from statistics import pstdev

import pytest

from analysis.datacenter_indices import (
    CALC_VERSION,
    DatacenterPriceRow,
    DatacenterTaxonomyRow,
    calculate_datacenter_group_indices,
)


def _taxonomy_row(
    ticker: str,
    *,
    layer: str = "Power",
    subindustry: str = "UPS",
    taxonomy_version: str = "DC_TAXONOMY_V1",
) -> DatacenterTaxonomyRow:
    return DatacenterTaxonomyRow(
        taxonomy_version=taxonomy_version,
        ticker=ticker,
        layer=layer,
        subindustry=subindustry,
        report_group_status="CORE",
        is_primary=1,
        role_weight=1.0,
        notes=None,
    )


def _price_row(ticker: str, date: str, close: float) -> DatacenterPriceRow:
    return DatacenterPriceRow(ticker=ticker, date=date, close=close)


def _find_row(rows, index_date: str, group_type: str, group_name: str):
    for row in rows:
        if (
            row.index_date == index_date
            and row.group_type == group_type
            and row.group_name == group_name
        ):
            return row
    raise AssertionError(
        f"Row not found for {index_date} {group_type} {group_name}"
    )


def test_calculator_rejects_empty_taxonomy_rows():
    with pytest.raises(ValueError, match="taxonomy_version"):
        calculate_datacenter_group_indices(
            taxonomy_rows=[],
            price_rows=[],
            taxonomy_version="DC_TAXONOMY_V1",
        )


def test_calculator_rejects_missing_taxonomy_version_after_filtering():
    with pytest.raises(ValueError, match="taxonomy_version"):
        calculate_datacenter_group_indices(
            taxonomy_rows=[_taxonomy_row("AAA", taxonomy_version="OTHER_VERSION")],
            price_rows=[_price_row("AAA", "2024-01-01", 100.0)],
            taxonomy_version="DC_TAXONOMY_V1",
        )


def test_ecosystem_group_deduplicates_tickers_globally():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA", layer="Power", subindustry="UPS"),
            _taxonomy_row("AAA", layer="Cooling", subindustry="Liquid cooling"),
            _taxonomy_row("BBB", layer="Power", subindustry="UPS"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-02", 100.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    ecosystem_row = _find_row(rows, "2024-01-02", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    assert ecosystem_row.member_count == 2


def test_layer_group_deduplicates_same_ticker_inside_one_layer():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA", layer="Power", subindustry="UPS"),
            _taxonomy_row("AAA", layer="Power", subindustry="Electrical controls"),
            _taxonomy_row("BBB", layer="Power", subindustry="UPS"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-02", 100.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    layer_row = _find_row(rows, "2024-01-02", "layer", "Power")
    assert layer_row.member_count == 2


def test_same_ticker_is_allowed_to_contribute_to_different_layers():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA", layer="Power", subindustry="UPS"),
            _taxonomy_row("AAA", layer="Cooling", subindustry="Liquid cooling"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    power_row = _find_row(rows, "2024-01-02", "layer", "Power")
    cooling_row = _find_row(rows, "2024-01-02", "layer", "Cooling")
    assert power_row.eligible_count == 1
    assert cooling_row.eligible_count == 1
    assert power_row.daily_return_equal == pytest.approx(0.10)
    assert cooling_row.daily_return_equal == pytest.approx(0.10)


def test_subindustry_groups_use_exact_subindustry_values():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA", subindustry="UPS"),
            _taxonomy_row("BBB", subindustry="Kupari"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-02", 100.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    assert _find_row(rows, "2024-01-02", "subindustry", "UPS").member_count == 1
    assert _find_row(rows, "2024-01-02", "subindustry", "Kupari").member_count == 1


def test_group_daily_metrics_are_calculated_correctly():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA"),
            _taxonomy_row("BBB"),
            _taxonomy_row("CCC"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("CCC", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-02", 90.0),
            _price_row("CCC", "2024-01-02", 100.0),
            _price_row("AAA", "2024-01-03", 121.0),
            _price_row("BBB", "2024-01-03", 99.0),
            _price_row("CCC", "2024-01-03", 100.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    first_row = _find_row(rows, "2024-01-02", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    second_row = _find_row(rows, "2024-01-03", "ecosystem", "DC_ECOSYSTEM_TOTAL")

    assert first_row.eligible_count == 3
    assert first_row.daily_return_equal == pytest.approx(0.0)
    assert first_row.median_return == pytest.approx(0.0)
    assert first_row.pct_positive == pytest.approx(33.3333333333)
    assert first_row.index_level_equal == pytest.approx(100.0)
    assert first_row.return_20d is None
    assert first_row.volatility_20d is None
    assert first_row.data_quality_status == "OK"
    assert first_row.relative_strength_spy_60d is None
    assert first_row.relative_strength_qqq_60d is None
    assert first_row.calc_version == CALC_VERSION

    assert second_row.daily_return_equal == pytest.approx(0.0666666667)
    assert second_row.median_return == pytest.approx(0.10)
    assert second_row.pct_positive == pytest.approx(66.6666666667)
    assert second_row.index_level_equal == pytest.approx(106.6666666667)


def test_first_ticker_observation_has_no_valid_daily_return():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[_taxonomy_row("AAA")],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-01",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    first_row = _find_row(rows, "2024-01-01", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    assert first_row.eligible_count == 0
    assert first_row.daily_return_equal is None
    assert first_row.data_quality_status == "NO_DATA"


def test_ticker_daily_return_uses_previous_available_observation_without_forward_fill():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[_taxonomy_row("AAA")],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-03", 110.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    row = _find_row(rows, "2024-01-03", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    assert row.daily_return_equal == pytest.approx(0.10)


def test_data_quality_status_variants_are_assigned_correctly():
    taxonomy_rows = [
        _taxonomy_row("AAA"),
        _taxonomy_row("BBB"),
        _taxonomy_row("CCC"),
        _taxonomy_row("DDD"),
        _taxonomy_row("EEE"),
    ]
    price_rows = [
        _price_row("AAA", "2024-01-01", 100.0),
        _price_row("BBB", "2024-01-01", 100.0),
        _price_row("CCC", "2024-01-01", 100.0),
        _price_row("DDD", "2024-01-01", 100.0),
        _price_row("EEE", "2024-01-01", 100.0),
        _price_row("AAA", "2024-01-02", 110.0),
        _price_row("BBB", "2024-01-02", 90.0),
        _price_row("AAA", "2024-01-03", 121.0),
        _price_row("BBB", "2024-01-03", 81.0),
        _price_row("CCC", "2024-01-03", 100.0),
    ]

    rows = calculate_datacenter_group_indices(
        taxonomy_rows=taxonomy_rows,
        price_rows=price_rows,
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-01",
        min_eligible_count_ecosystem=3,
        min_eligible_count_layer=3,
        min_eligible_count_subindustry=2,
    )

    no_data_row = _find_row(rows, "2024-01-01", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    too_small_row = _find_row(rows, "2024-01-02", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    partial_row = _find_row(rows, "2024-01-03", "ecosystem", "DC_ECOSYSTEM_TOTAL")

    assert no_data_row.data_quality_status == "NO_DATA"
    assert too_small_row.data_quality_status == "TOO_SMALL"
    assert partial_row.data_quality_status == "PARTIAL_DATA"

    ok_taxonomy_rows = [
        _taxonomy_row("AAA"),
        _taxonomy_row("BBB"),
        _taxonomy_row("CCC"),
        _taxonomy_row("DDD"),
    ]
    ok_price_rows = [
        _price_row("AAA", "2024-01-01", 100.0),
        _price_row("BBB", "2024-01-01", 100.0),
        _price_row("CCC", "2024-01-01", 100.0),
        _price_row("DDD", "2024-01-01", 100.0),
        _price_row("AAA", "2024-01-02", 110.0),
        _price_row("BBB", "2024-01-02", 90.0),
        _price_row("AAA", "2024-01-03", 121.0),
        _price_row("BBB", "2024-01-03", 81.0),
        _price_row("CCC", "2024-01-03", 100.0),
    ]
    ok_rows = calculate_datacenter_group_indices(
        taxonomy_rows=ok_taxonomy_rows,
        price_rows=ok_price_rows,
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-01",
        min_eligible_count_ecosystem=2,
        min_eligible_count_layer=2,
        min_eligible_count_subindustry=2,
    )
    ok_row = _find_row(ok_rows, "2024-01-03", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    assert ok_row.data_quality_status == "OK"


def test_too_small_and_no_data_rows_do_not_update_index_level():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("AAA"),
            _taxonomy_row("BBB"),
            _taxonomy_row("CCC"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("CCC", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-02", 90.0),
            _price_row("CCC", "2024-01-02", 100.0),
            _price_row("AAA", "2024-01-03", 121.0),
            _price_row("AAA", "2024-01-04", 133.1),
            _price_row("BBB", "2024-01-04", 99.0),
            _price_row("CCC", "2024-01-04", 100.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-01-01",
        end_date="2024-01-04",
        min_eligible_count_ecosystem=3,
        min_eligible_count_layer=3,
        min_eligible_count_subindustry=3,
    )

    row_2024_01_01 = _find_row(rows, "2024-01-01", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    row_2024_01_02 = _find_row(rows, "2024-01-02", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    row_2024_01_03 = _find_row(rows, "2024-01-03", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    row_2024_01_04 = _find_row(rows, "2024-01-04", "ecosystem", "DC_ECOSYSTEM_TOTAL")

    assert row_2024_01_01.index_level_equal is None
    assert row_2024_01_02.index_level_equal == pytest.approx(100.0)
    assert row_2024_01_03.index_level_equal is None
    assert row_2024_01_04.index_level_equal == pytest.approx(106.6666666667)


def test_return_20d_and_volatility_20d_are_calculated_from_valid_history():
    taxonomy_rows = [_taxonomy_row("AAA"), _taxonomy_row("BBB")]
    price_rows = []
    aaa_close = 100.0
    bbb_close = 100.0
    daily_returns = []
    for offset in range(22):
        current_date = f"2024-01-{offset + 1:02d}"
        price_rows.append(_price_row("AAA", current_date, aaa_close))
        price_rows.append(_price_row("BBB", current_date, bbb_close))
        if offset > 0:
            group_return = 0.01 if offset % 2 == 1 else -0.005
            daily_returns.append(group_return)
            aaa_close *= 1.0 + (0.02 if offset % 2 == 1 else -0.01)
            bbb_close *= 1.0 + (0.0 if offset % 2 == 1 else 0.0)

    rows = calculate_datacenter_group_indices(
        taxonomy_rows=taxonomy_rows,
        price_rows=price_rows,
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    last_row = _find_row(rows, "2024-01-22", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    valid_levels = []
    current_level = 100.0
    for idx, group_return in enumerate(daily_returns):
        if idx == 0:
            current_level = 100.0
        else:
            current_level = current_level * (1.0 + group_return)
        valid_levels.append(current_level)
    expected_return_20d = (valid_levels[-1] / valid_levels[-21]) - 1.0
    expected_volatility_20d = pstdev(daily_returns[-20:])

    assert last_row.return_20d == pytest.approx(expected_return_20d)
    assert last_row.volatility_20d == pytest.approx(expected_volatility_20d)
    assert last_row.return_60d is None
    assert last_row.return_120d is None
    assert last_row.volatility_60d is None


def test_ma50_and_ma200_eligibility_and_percentages_are_calculated_correctly():
    taxonomy_rows = [_taxonomy_row("AAA"), _taxonomy_row("BBB")]
    price_rows = []
    start = date(2024, 1, 1)
    for offset in range(200):
        current_date = (start + timedelta(days=offset)).isoformat()
        price_rows.append(_price_row("AAA", current_date, 100.0 + offset))
        price_rows.append(_price_row("BBB", current_date, 300.0 - offset))

    rows = calculate_datacenter_group_indices(
        taxonomy_rows=taxonomy_rows,
        price_rows=price_rows,
        taxonomy_version="DC_TAXONOMY_V1",
        start_date="2024-02-19",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    ma50_row = _find_row(rows, "2024-02-19", "ecosystem", "DC_ECOSYSTEM_TOTAL")
    ma200_row = _find_row(rows, "2024-07-18", "ecosystem", "DC_ECOSYSTEM_TOTAL")

    assert ma50_row.ma50_eligible_count == 2
    assert ma50_row.pct_above_ma50 == pytest.approx(50.0)
    assert ma50_row.ma200_eligible_count == 0
    assert ma50_row.pct_above_ma200 is None

    assert ma200_row.ma200_eligible_count == 2
    assert ma200_row.pct_above_ma200 == pytest.approx(50.0)


def test_calculator_rejects_duplicate_ticker_date_price_rows():
    with pytest.raises(ValueError, match="Duplicate price row"):
        calculate_datacenter_group_indices(
            taxonomy_rows=[_taxonomy_row("AAA")],
            price_rows=[
                _price_row("AAA", "2024-01-01", 100.0),
                _price_row("AAA", "2024-01-01", 101.0),
            ],
            taxonomy_version="DC_TAXONOMY_V1",
        )


def test_calculator_rejects_non_positive_close_values():
    with pytest.raises(ValueError, match="greater than 0"):
        calculate_datacenter_group_indices(
            taxonomy_rows=[_taxonomy_row("AAA")],
            price_rows=[_price_row("AAA", "2024-01-01", 0.0)],
            taxonomy_version="DC_TAXONOMY_V1",
        )


def test_output_sorting_is_deterministic():
    rows = calculate_datacenter_group_indices(
        taxonomy_rows=[
            _taxonomy_row("BBB", layer="Zeta", subindustry="B"),
            _taxonomy_row("AAA", layer="Alpha", subindustry="A"),
        ],
        price_rows=[
            _price_row("AAA", "2024-01-01", 100.0),
            _price_row("AAA", "2024-01-02", 110.0),
            _price_row("BBB", "2024-01-01", 100.0),
            _price_row("BBB", "2024-01-02", 90.0),
        ],
        taxonomy_version="DC_TAXONOMY_V1",
        min_eligible_count_ecosystem=1,
        min_eligible_count_layer=1,
        min_eligible_count_subindustry=1,
    )

    actual = [
        (row.index_date, row.group_type, row.group_name)
        for row in rows
        if row.index_date == "2024-01-02"
    ]
    assert actual == [
        ("2024-01-02", "ecosystem", "DC_ECOSYSTEM_TOTAL"),
        ("2024-01-02", "layer", "Alpha"),
        ("2024-01-02", "layer", "Zeta"),
        ("2024-01-02", "subindustry", "A"),
        ("2024-01-02", "subindustry", "B"),
    ]
