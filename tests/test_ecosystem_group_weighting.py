from __future__ import annotations

import pytest

from analysis.ecosystem_group_weighting import (
    GroupMembershipRoute,
    build_canonical_groups,
    canonicalize_group_memberships,
    effective_membership_weight_v1,
    weight_concentration,
    weighted_mean,
)


@pytest.mark.parametrize(
    ("group_type", "is_primary", "status", "expected"),
    [
        ("subindustry", 1, "CORE", 1.00),
        ("subindustry", 1, "EXTENDED", 1.00),
        ("subindustry", 0, "CORE", 0.33),
        ("subindustry", 0, "EXTENDED", 0.33),
        ("layer", 1, "CORE", 1.00),
        ("layer", 0, "CORE", 0.25),
        ("layer", 0, "EXTENDED", 0.25),
        ("subindustry", 1, "WATCH_ONLY", 0.00),
        ("layer", 0, "TOO_SMALL", 0.00),
    ],
)
def test_effective_membership_weight_v1(
    group_type, is_primary, status, expected
):
    assert effective_membership_weight_v1(
        group_type=group_type,
        is_primary=is_primary,
        report_group_status=status,
    ) == pytest.approx(expected)


def test_effective_membership_weight_rejects_invalid_status_and_group_type():
    with pytest.raises(ValueError, match="report_group_status"):
        effective_membership_weight_v1(
            group_type="layer",
            is_primary=1,
            report_group_status="UNKNOWN",
        )
    with pytest.raises(ValueError, match="group_type"):
        effective_membership_weight_v1(
            group_type="ecosystem",
            is_primary=1,
            report_group_status="CORE",
        )


def _route(
    ticker: str,
    group_type: str,
    group_name: str,
    is_primary: int,
    status: str = "CORE",
) -> GroupMembershipRoute:
    return GroupMembershipRoute(
        ticker=ticker,
        group_type=group_type,
        group_name=group_name,
        is_primary=is_primary,
        report_group_status=status,
    )


def test_canonicalization_uses_max_weight_without_accumulating_routes():
    memberships = canonicalize_group_memberships(
        [
            _route("AAA", "layer", "Power", 0),
            _route("AAA", "layer", "Power", 1),
            _route("BBB", "layer", "Power", 0),
            _route("BBB", "layer", "Power", 0),
            _route("CCC", "layer", "Power", 0, "WATCH_ONLY"),
            _route("CCC", "layer", "Power", 0, "EXTENDED"),
        ]
    )
    by_ticker = {membership.ticker: membership for membership in memberships}

    assert len(memberships) == 3
    assert by_ticker["AAA"].effective_weight == pytest.approx(1.0)
    assert by_ticker["AAA"].is_primary == 1
    assert by_ticker["BBB"].effective_weight == pytest.approx(0.25)
    assert by_ticker["BBB"].source_route_count == 2
    assert by_ticker["CCC"].effective_weight == pytest.approx(0.25)
    assert by_ticker["CCC"].report_group_status == "EXTENDED"


def test_canonicalization_keeps_distinct_subindustries():
    groups = build_canonical_groups(
        [
            _route("AAA", "subindustry", "UPS", 1),
            _route("AAA", "subindustry", "Switchgear", 0),
        ]
    )
    assert [(group.group_name, len(group.memberships)) for group in groups] == [
        ("Switchgear", 1),
        ("UPS", 1),
    ]


def test_weight_concentration_reuses_normalized_weight_diagnostics():
    result = weight_concentration([1.0, 0.25, 0.0])

    assert result.effective_member_count == pytest.approx(1.4705882353)
    assert result.largest_normalized_weight == pytest.approx(0.8)
    assert result.top3_normalized_weight_share == pytest.approx(1.0)


def test_weighted_mean_normalizes_positive_weights_only():
    result = weighted_mean([(10.0, 1.0), (20.0, 0.25), (999.0, 0.0)])
    assert result.value == pytest.approx(12.0)
    assert result.total_weight == pytest.approx(1.25)
    assert result.positive_weight_count == 2
