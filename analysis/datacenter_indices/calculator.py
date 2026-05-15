from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from statistics import median, pstdev
from typing import Sequence

from .taxonomy import DatacenterTaxonomyRow


CALC_VERSION = "DC_INDEX_CALC_V1"

_GROUP_TYPE_ORDER = {
    "ecosystem": 0,
    "layer": 1,
    "subindustry": 2,
}


@dataclass(frozen=True)
class DatacenterPriceRow:
    ticker: str
    date: str
    close: float


@dataclass(frozen=True)
class DatacenterGroupIndexRow:
    index_date: str
    taxonomy_version: str
    group_type: str
    group_name: str
    member_count: int
    eligible_count: int
    ma50_eligible_count: int
    ma200_eligible_count: int
    daily_return_equal: float | None
    median_return: float | None
    pct_positive: float | None
    pct_above_ma50: float | None
    pct_above_ma200: float | None
    index_level_equal: float | None
    return_20d: float | None
    return_60d: float | None
    return_120d: float | None
    volatility_20d: float | None
    volatility_60d: float | None
    relative_strength_spy_60d: float | None
    relative_strength_qqq_60d: float | None
    data_quality_status: str
    calc_version: str


@dataclass(frozen=True)
class _NormalizedPriceRow:
    ticker: str
    date: str
    close: float


@dataclass(frozen=True)
class _TickerDailyState:
    close: float
    daily_return: float | None
    ma50: float | None
    ma200: float | None


def _normalize_ticker(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _validate_taxonomy_rows(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
    taxonomy_version: str,
) -> list[DatacenterTaxonomyRow]:
    if not taxonomy_rows:
        raise ValueError(
            f"No taxonomy rows provided for taxonomy_version '{taxonomy_version}'"
        )

    normalized_rows = [
        DatacenterTaxonomyRow(
            taxonomy_version=str(row.taxonomy_version).strip(),
            ticker=_normalize_ticker(row.ticker),
            layer=str(row.layer).strip(),
            subindustry=str(row.subindustry).strip(),
            report_group_status=str(row.report_group_status).strip(),
            is_primary=int(row.is_primary),
            role_weight=float(row.role_weight),
            notes=row.notes,
        )
        for row in taxonomy_rows
    ]
    filtered = [
        row for row in normalized_rows if row.taxonomy_version == taxonomy_version
    ]
    if not filtered:
        raise ValueError(
            f"No taxonomy rows found for taxonomy_version '{taxonomy_version}'"
        )
    return filtered


def _validate_price_rows(
    price_rows: Sequence[DatacenterPriceRow],
) -> list[_NormalizedPriceRow]:
    normalized_rows: list[_NormalizedPriceRow] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in price_rows:
        ticker = _normalize_ticker(row.ticker)
        if not ticker:
            raise ValueError("Price row ticker must not be empty")
        date_value = _parse_iso_date(str(row.date), "price row date")
        try:
            close = float(row.close)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid close for ticker {ticker} on {date_value}") from exc
        if not isfinite(close) or close <= 0:
            raise ValueError(
                f"Price row close must be greater than 0 for ticker {ticker} on {date_value}"
            )

        key = (ticker, date_value)
        if key in seen_keys:
            raise ValueError(f"Duplicate price row for ticker {ticker} on {date_value}")
        seen_keys.add(key)
        normalized_rows.append(
            _NormalizedPriceRow(
                ticker=ticker,
                date=date_value,
                close=close,
            )
        )
    return normalized_rows


def _filter_and_validate_relevant_price_rows(
    price_rows: Sequence[DatacenterPriceRow],
    relevant_tickers: set[str],
) -> list[_NormalizedPriceRow]:
    normalized_rows: list[_NormalizedPriceRow] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in price_rows:
        ticker = _normalize_ticker(row.ticker)
        if ticker not in relevant_tickers:
            continue
        if not ticker:
            raise ValueError("Price row ticker must not be empty")
        date_value = _parse_iso_date(str(row.date), "price row date")
        try:
            close = float(row.close)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid close for ticker {ticker} on {date_value}"
            ) from exc
        if not isfinite(close) or close <= 0:
            raise ValueError(
                f"Price row close must be greater than 0 for ticker {ticker} on {date_value}"
            )
        key = (ticker, date_value)
        if key in seen_keys:
            raise ValueError(f"Duplicate price row for ticker {ticker} on {date_value}")
        seen_keys.add(key)
        normalized_rows.append(
            _NormalizedPriceRow(
                ticker=ticker,
                date=date_value,
                close=close,
            )
        )
    return normalized_rows


def _build_group_definitions(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
) -> list[tuple[str, str, tuple[str, ...]]]:
    ecosystem_tickers = tuple(sorted({row.ticker for row in taxonomy_rows}))
    layer_map: dict[str, set[str]] = {}
    subindustry_map: dict[str, set[str]] = {}
    for row in taxonomy_rows:
        layer_map.setdefault(row.layer, set()).add(row.ticker)
        subindustry_map.setdefault(row.subindustry, set()).add(row.ticker)

    groups: list[tuple[str, str, tuple[str, ...]]] = [
        ("ecosystem", "DC_ECOSYSTEM_TOTAL", ecosystem_tickers)
    ]
    groups.extend(
        ("layer", layer, tuple(sorted(tickers)))
        for layer, tickers in sorted(layer_map.items())
    )
    groups.extend(
        ("subindustry", subindustry, tuple(sorted(tickers)))
        for subindustry, tickers in sorted(subindustry_map.items())
    )
    return groups


def _build_ticker_daily_states(
    price_rows: Sequence[_NormalizedPriceRow],
) -> tuple[dict[str, dict[str, _TickerDailyState]], list[str]]:
    rows_by_ticker: dict[str, list[_NormalizedPriceRow]] = {}
    all_dates: set[str] = set()
    for row in price_rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)
        all_dates.add(row.date)

    ticker_states: dict[str, dict[str, _TickerDailyState]] = {}
    for ticker, ticker_rows in rows_by_ticker.items():
        sorted_rows = sorted(ticker_rows, key=lambda item: item.date)
        history: list[float] = []
        previous_close: float | None = None
        daily_map: dict[str, _TickerDailyState] = {}
        for row in sorted_rows:
            history.append(row.close)
            daily_return = None
            if previous_close is not None:
                daily_return = (row.close / previous_close) - 1.0
            previous_close = row.close

            ma50 = None
            ma200 = None
            if len(history) >= 50:
                ma50 = sum(history[-50:]) / 50.0
            if len(history) >= 200:
                ma200 = sum(history[-200:]) / 200.0

            daily_map[row.date] = _TickerDailyState(
                close=row.close,
                daily_return=daily_return,
                ma50=ma50,
                ma200=ma200,
            )
        ticker_states[ticker] = daily_map

    return ticker_states, sorted(all_dates)


def _group_minimum(
    group_type: str,
    min_eligible_count_layer: int,
    min_eligible_count_subindustry: int,
    min_eligible_count_ecosystem: int,
) -> int:
    if group_type == "ecosystem":
        return min_eligible_count_ecosystem
    if group_type == "layer":
        return min_eligible_count_layer
    return min_eligible_count_subindustry


def _calculate_return_from_valid_levels(
    valid_levels: list[float],
    lookback: int,
) -> float | None:
    if len(valid_levels) <= lookback:
        return None
    return (valid_levels[-1] / valid_levels[-1 - lookback]) - 1.0


def _calculate_volatility(
    valid_returns: list[float],
    window: int,
) -> float | None:
    if len(valid_returns) < window:
        return None
    # Use population standard deviation for deterministic simplicity.
    return pstdev(valid_returns[-window:])


def _build_benchmark_return_map(
    ticker_states: dict[str, dict[str, _TickerDailyState]],
    benchmark_ticker: str,
    lookback: int,
) -> dict[str, float | None]:
    benchmark_daily = ticker_states.get(benchmark_ticker, {})
    if not benchmark_daily:
        return {}

    valid_closes: list[float] = []
    return_map: dict[str, float | None] = {}
    for current_date in sorted(benchmark_daily):
        state = benchmark_daily[current_date]
        valid_closes.append(state.close)
        if len(valid_closes) <= lookback:
            return_map[current_date] = None
        else:
            return_map[current_date] = (valid_closes[-1] / valid_closes[-1 - lookback]) - 1.0
    return return_map


def calculate_datacenter_group_indices(
    taxonomy_rows: Sequence[DatacenterTaxonomyRow],
    price_rows: Sequence[DatacenterPriceRow],
    taxonomy_version: str,
    start_date: str | None = None,
    end_date: str | None = None,
    min_eligible_count_layer: int = 3,
    min_eligible_count_subindustry: int = 2,
    min_eligible_count_ecosystem: int = 10,
    spy_ticker: str = "SPY",
    qqq_ticker: str = "QQQ",
) -> list[DatacenterGroupIndexRow]:
    filtered_taxonomy = _validate_taxonomy_rows(taxonomy_rows, taxonomy_version)
    taxonomy_ticker_set = {row.ticker for row in filtered_taxonomy}
    normalized_spy_ticker = _normalize_ticker(spy_ticker)
    normalized_qqq_ticker = _normalize_ticker(qqq_ticker)
    if normalized_spy_ticker == normalized_qqq_ticker:
        raise ValueError("spy_ticker and qqq_ticker must not be the same")
    if normalized_spy_ticker in taxonomy_ticker_set:
        raise ValueError(
            f"spy_ticker overlaps taxonomy ticker set for taxonomy_version '{taxonomy_version}'"
        )
    if normalized_qqq_ticker in taxonomy_ticker_set:
        raise ValueError(
            f"qqq_ticker overlaps taxonomy ticker set for taxonomy_version '{taxonomy_version}'"
        )

    relevant_tickers = set(taxonomy_ticker_set)
    relevant_tickers.add(normalized_spy_ticker)
    relevant_tickers.add(normalized_qqq_ticker)
    relevant_prices = _filter_and_validate_relevant_price_rows(price_rows, relevant_tickers)

    start_iso = _parse_iso_date(start_date, "start_date") if start_date else None
    end_iso = _parse_iso_date(end_date, "end_date") if end_date else None
    if start_iso and end_iso and start_iso > end_iso:
        raise ValueError(
            f"Invalid date range: start_date {start_iso} is after end_date {end_iso}"
        )

    ticker_states, all_dates = _build_ticker_daily_states(relevant_prices)
    groups = _build_group_definitions(filtered_taxonomy)
    taxonomy_all_dates = sorted(
        {
            current_date
            for ticker, state_by_date in ticker_states.items()
            if ticker in taxonomy_ticker_set
            for current_date in state_by_date
        }
    )
    spy_return_60d_by_date = _build_benchmark_return_map(
        ticker_states, normalized_spy_ticker, 60
    )
    qqq_return_60d_by_date = _build_benchmark_return_map(
        ticker_states, normalized_qqq_ticker, 60
    )

    if start_iso is None:
        calculable_dates = [
            current_date
            for current_date in taxonomy_all_dates
            if any(
                state_by_date[current_date].daily_return is not None
                for ticker, state_by_date in ticker_states.items()
                if ticker in taxonomy_ticker_set and current_date in state_by_date
            )
        ]
        if not calculable_dates:
            return []
        effective_start = calculable_dates[0]
    else:
        effective_start = start_iso
    effective_end = (
        end_iso if end_iso is not None else (taxonomy_all_dates[-1] if taxonomy_all_dates else None)
    )
    if effective_end is None:
        return []

    output_dates = [
        current_date
        for current_date in taxonomy_all_dates
        if effective_start <= current_date <= effective_end
    ]
    if not output_dates:
        return []

    valid_index_levels_by_group: dict[tuple[str, str], list[float]] = {}
    valid_returns_by_group: dict[tuple[str, str], list[float]] = {}
    previous_index_level_by_group: dict[tuple[str, str], float] = {}
    output_rows: list[DatacenterGroupIndexRow] = []

    for current_date in output_dates:
        for group_type, group_name, group_tickers in groups:
            member_count = len(group_tickers)
            eligible_returns: list[float] = []
            ma50_values: list[bool] = []
            ma200_values: list[bool] = []

            for ticker in group_tickers:
                ticker_daily = ticker_states.get(ticker, {})
                state = ticker_daily.get(current_date)
                if state is None:
                    continue
                if state.daily_return is not None:
                    eligible_returns.append(state.daily_return)
                if state.ma50 is not None:
                    ma50_values.append(state.close > state.ma50)
                if state.ma200 is not None:
                    ma200_values.append(state.close > state.ma200)

            eligible_count = len(eligible_returns)
            ma50_eligible_count = len(ma50_values)
            ma200_eligible_count = len(ma200_values)

            daily_return_equal = (
                sum(eligible_returns) / eligible_count if eligible_returns else None
            )
            median_return_value = median(eligible_returns) if eligible_returns else None
            pct_positive = (
                100.0
                * sum(1 for value in eligible_returns if value > 0.0)
                / eligible_count
                if eligible_returns
                else None
            )
            pct_above_ma50 = (
                100.0 * sum(1 for value in ma50_values if value) / ma50_eligible_count
                if ma50_values
                else None
            )
            pct_above_ma200 = (
                100.0 * sum(1 for value in ma200_values if value) / ma200_eligible_count
                if ma200_values
                else None
            )

            minimum_count = _group_minimum(
                group_type,
                min_eligible_count_layer=min_eligible_count_layer,
                min_eligible_count_subindustry=min_eligible_count_subindustry,
                min_eligible_count_ecosystem=min_eligible_count_ecosystem,
            )
            if eligible_count == 0:
                data_quality_status = "NO_DATA"
            elif eligible_count < minimum_count:
                data_quality_status = "TOO_SMALL"
            elif member_count > 0 and (eligible_count / member_count) < 0.70:
                data_quality_status = "PARTIAL_DATA"
            else:
                data_quality_status = "OK"

            group_key = (group_type, group_name)
            index_level_equal = None
            return_20d = None
            return_60d = None
            return_120d = None
            volatility_20d = None
            volatility_60d = None
            relative_strength_spy_60d = None
            relative_strength_qqq_60d = None

            if data_quality_status in {"OK", "PARTIAL_DATA"} and daily_return_equal is not None:
                previous_valid = previous_index_level_by_group.get(group_key)
                if previous_valid is None:
                    index_level_equal = 100.0
                else:
                    index_level_equal = previous_valid * (1.0 + daily_return_equal)
                previous_index_level_by_group[group_key] = index_level_equal

                valid_index_levels = valid_index_levels_by_group.setdefault(group_key, [])
                valid_index_levels.append(index_level_equal)
                valid_group_returns = valid_returns_by_group.setdefault(group_key, [])
                valid_group_returns.append(daily_return_equal)

                return_20d = _calculate_return_from_valid_levels(valid_index_levels, 20)
                return_60d = _calculate_return_from_valid_levels(valid_index_levels, 60)
                return_120d = _calculate_return_from_valid_levels(valid_index_levels, 120)
                volatility_20d = _calculate_volatility(valid_group_returns, 20)
                volatility_60d = _calculate_volatility(valid_group_returns, 60)
                spy_return_60d = spy_return_60d_by_date.get(current_date)
                qqq_return_60d = qqq_return_60d_by_date.get(current_date)
                if return_60d is not None and spy_return_60d is not None:
                    relative_strength_spy_60d = return_60d - spy_return_60d
                if return_60d is not None and qqq_return_60d is not None:
                    relative_strength_qqq_60d = return_60d - qqq_return_60d

            output_rows.append(
                DatacenterGroupIndexRow(
                    index_date=current_date,
                    taxonomy_version=taxonomy_version,
                    group_type=group_type,
                    group_name=group_name,
                    member_count=member_count,
                    eligible_count=eligible_count,
                    ma50_eligible_count=ma50_eligible_count,
                    ma200_eligible_count=ma200_eligible_count,
                    daily_return_equal=daily_return_equal,
                    median_return=median_return_value,
                    pct_positive=pct_positive,
                    pct_above_ma50=pct_above_ma50,
                    pct_above_ma200=pct_above_ma200,
                    index_level_equal=index_level_equal,
                    return_20d=return_20d,
                    return_60d=return_60d,
                    return_120d=return_120d,
                    volatility_20d=volatility_20d,
                    volatility_60d=volatility_60d,
                    relative_strength_spy_60d=relative_strength_spy_60d,
                    relative_strength_qqq_60d=relative_strength_qqq_60d,
                    data_quality_status=data_quality_status,
                    calc_version=CALC_VERSION,
                )
            )

    output_rows.sort(
        key=lambda row: (
            row.index_date,
            _GROUP_TYPE_ORDER[row.group_type],
            row.group_name,
        )
    )
    return output_rows
