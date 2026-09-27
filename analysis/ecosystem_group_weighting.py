from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence


SUPPORTED_GROUP_TYPES = frozenset({"layer", "subindustry"})
SUPPORTED_REPORT_GROUP_STATUSES = frozenset(
    {"CORE", "EXTENDED", "WATCH_ONLY", "TOO_SMALL"}
)


class MembershipWeightPolicy(Protocol):
    def __call__(
        self,
        *,
        group_type: str,
        is_primary: int,
        report_group_status: str,
    ) -> float: ...


@dataclass(frozen=True)
class GroupMembershipRoute:
    ticker: str
    group_type: str
    group_name: str
    is_primary: int
    report_group_status: str


@dataclass(frozen=True)
class CanonicalGroupMembership:
    ticker: str
    group_type: str
    group_name: str
    is_primary: int
    report_group_status: str
    effective_weight: float
    source_route_count: int
    source_statuses: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalGroup:
    group_type: str
    group_name: str
    memberships: tuple[CanonicalGroupMembership, ...]


@dataclass(frozen=True)
class WeightedMean:
    value: float | None
    total_weight: float
    positive_weight_count: int


@dataclass(frozen=True)
class WeightConcentration:
    effective_member_count: float
    largest_normalized_weight: float
    top3_normalized_weight_share: float


def effective_membership_weight_v1(
    *,
    group_type: str,
    is_primary: int,
    report_group_status: str,
) -> float:
    if group_type not in SUPPORTED_GROUP_TYPES:
        raise ValueError(f"Unsupported group_type: {group_type!r}")
    if is_primary not in (0, 1):
        raise ValueError(f"is_primary must be 0 or 1, got {is_primary!r}")
    if report_group_status not in SUPPORTED_REPORT_GROUP_STATUSES:
        raise ValueError(
            f"Unsupported report_group_status: {report_group_status!r}"
        )
    if report_group_status in {"WATCH_ONLY", "TOO_SMALL"}:
        return 0.0
    if is_primary == 1:
        return 1.0
    if group_type == "subindustry":
        return 0.33
    return 0.25


def equal_membership_weight(
    *,
    group_type: str,
    is_primary: int,
    report_group_status: str,
) -> float:
    effective_membership_weight_v1(
        group_type=group_type,
        is_primary=is_primary,
        report_group_status=report_group_status,
    )
    return 1.0


def canonicalize_group_memberships(
    routes: Iterable[GroupMembershipRoute],
    *,
    weight_policy: MembershipWeightPolicy = effective_membership_weight_v1,
) -> tuple[CanonicalGroupMembership, ...]:
    grouped: dict[tuple[str, str, str], list[tuple[GroupMembershipRoute, float]]] = {}
    for route in routes:
        ticker = str(route.ticker).strip().upper()
        group_name = str(route.group_name).strip()
        if not ticker:
            raise ValueError("Membership ticker must not be empty")
        if not group_name:
            raise ValueError("Membership group_name must not be empty")
        weight = weight_policy(
            group_type=route.group_type,
            is_primary=route.is_primary,
            report_group_status=route.report_group_status,
        )
        normalized = GroupMembershipRoute(
            ticker=ticker,
            group_type=route.group_type,
            group_name=group_name,
            is_primary=route.is_primary,
            report_group_status=route.report_group_status,
        )
        grouped.setdefault(
            (ticker, normalized.group_type, normalized.group_name), []
        ).append((normalized, weight))

    status_rank = {"TOO_SMALL": 0, "WATCH_ONLY": 1, "EXTENDED": 2, "CORE": 3}
    canonical: list[CanonicalGroupMembership] = []
    for (ticker, group_type, group_name), candidates in grouped.items():
        winning_route, winning_weight = max(
            candidates,
            key=lambda item: (
                item[1],
                item[0].is_primary,
                status_rank[item[0].report_group_status],
            ),
        )
        canonical.append(
            CanonicalGroupMembership(
                ticker=ticker,
                group_type=group_type,
                group_name=group_name,
                is_primary=winning_route.is_primary,
                report_group_status=winning_route.report_group_status,
                effective_weight=winning_weight,
                source_route_count=len(candidates),
                source_statuses=tuple(
                    sorted({route.report_group_status for route, _weight in candidates})
                ),
            )
        )
    return tuple(
        sorted(
            canonical,
            key=lambda membership: (
                membership.group_type,
                membership.group_name,
                membership.ticker,
            ),
        )
    )


def build_canonical_groups(
    routes: Iterable[GroupMembershipRoute],
    *,
    weight_policy: MembershipWeightPolicy = effective_membership_weight_v1,
) -> tuple[CanonicalGroup, ...]:
    grouped: dict[tuple[str, str], list[CanonicalGroupMembership]] = {}
    for membership in canonicalize_group_memberships(
        routes,
        weight_policy=weight_policy,
    ):
        grouped.setdefault(
            (membership.group_type, membership.group_name), []
        ).append(membership)
    return tuple(
        CanonicalGroup(
            group_type=group_type,
            group_name=group_name,
            memberships=tuple(sorted(memberships, key=lambda item: item.ticker)),
        )
        for (group_type, group_name), memberships in sorted(grouped.items())
    )


def weight_concentration(weights: Sequence[float]) -> WeightConcentration:
    if any(weight < 0 for weight in weights):
        raise ValueError("Weights must be non-negative")
    total_weight = sum(weight for weight in weights if weight > 0)
    normalized = sorted(
        (float(weight) / total_weight for weight in weights if weight > 0),
        reverse=True,
    ) if total_weight else []
    return WeightConcentration(
        effective_member_count=(
            1.0 / sum(weight * weight for weight in normalized)
            if normalized
            else 0.0
        ),
        largest_normalized_weight=normalized[0] if normalized else 0.0,
        top3_normalized_weight_share=sum(normalized[:3]),
    )


def weighted_mean(
    values_and_weights: Sequence[tuple[float, float]],
) -> WeightedMean:
    if any(weight < 0 for _value, weight in values_and_weights):
        raise ValueError("Weights must be non-negative")
    positive = [
        (float(value), float(weight))
        for value, weight in values_and_weights
        if weight > 0
    ]
    total_weight = sum(weight for _value, weight in positive)
    if total_weight == 0:
        return WeightedMean(
            value=None,
            total_weight=0.0,
            positive_weight_count=0,
        )
    return WeightedMean(
        value=sum(value * weight for value, weight in positive) / total_weight,
        total_weight=total_weight,
        positive_weight_count=len(positive),
    )
