from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, TypeVar

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardDecisionTraceInput,
    EcosystemDashboardInput,
    EcosystemDashboardMarketMapInput,
    EcosystemDashboardSourceReportInput,
    EcosystemDashboardTickerStatusInput,
    EcosystemDashboardWatchlistInput,
)

T = TypeVar("T")


def _field_names(dataclass_type: type[object]) -> set[str]:
    return {field.name for field in fields(dataclass_type)}


def _validate_mapping_keys(
    payload: dict[str, Any],
    *,
    allowed_keys: set[str],
    label: str,
) -> None:
    extra_keys = sorted(set(payload) - allowed_keys)
    if extra_keys:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(extra_keys)}")


def _require_mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _build_dataclass(dataclass_type: type[T], payload: dict[str, Any], *, label: str) -> T:
    _validate_mapping_keys(payload, allowed_keys=_field_names(dataclass_type), label=label)
    try:
        return dataclass_type(**payload)
    except TypeError as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc


def load_ecosystem_dashboard_input_json(path: str) -> EcosystemDashboardInput:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"structured input JSON not found: {path}")

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid structured input JSON: {exc}") from exc

    payload_dict = _require_mapping(payload, label="structured input JSON")
    _validate_mapping_keys(
        payload_dict,
        allowed_keys=_field_names(EcosystemDashboardInput),
        label="structured input JSON",
    )

    required_top_level_fields = (
        "ecosystem_code",
        "report_date",
        "source_reports",
        "action_summary",
        "market_map",
        "watchlist",
        "tickers",
        "decision_trace",
        "readiness",
        "total_parsed_rows",
        "total_parse_warnings",
    )
    missing_fields = [name for name in required_top_level_fields if name not in payload_dict]
    if missing_fields:
        raise ValueError(
            f"structured input JSON missing required fields: {', '.join(missing_fields)}"
        )

    return EcosystemDashboardInput(
        ecosystem_code=payload_dict["ecosystem_code"],
        report_date=payload_dict["report_date"],
        source_reports=[
            _build_dataclass(
                EcosystemDashboardSourceReportInput,
                _require_mapping(row, label="source_reports row"),
                label="source_reports row",
            )
            for row in _require_list(payload_dict["source_reports"], label="source_reports")
        ],
        action_summary=[
            _build_dataclass(
                EcosystemDashboardActionSummaryInput,
                _require_mapping(row, label="action_summary row"),
                label="action_summary row",
            )
            for row in _require_list(payload_dict["action_summary"], label="action_summary")
        ],
        market_map=[
            _build_dataclass(
                EcosystemDashboardMarketMapInput,
                _require_mapping(row, label="market_map row"),
                label="market_map row",
            )
            for row in _require_list(payload_dict["market_map"], label="market_map")
        ],
        watchlist=[
            _build_dataclass(
                EcosystemDashboardWatchlistInput,
                _require_mapping(row, label="watchlist row"),
                label="watchlist row",
            )
            for row in _require_list(payload_dict["watchlist"], label="watchlist")
        ],
        tickers=[
            _build_dataclass(
                EcosystemDashboardTickerStatusInput,
                _require_mapping(row, label="tickers row"),
                label="tickers row",
            )
            for row in _require_list(payload_dict["tickers"], label="tickers")
        ],
        decision_trace=[
            _build_dataclass(
                EcosystemDashboardDecisionTraceInput,
                _require_mapping(row, label="decision_trace row"),
                label="decision_trace row",
            )
            for row in _require_list(payload_dict["decision_trace"], label="decision_trace")
        ],
        readiness=payload_dict["readiness"],
        total_parsed_rows=payload_dict["total_parsed_rows"],
        total_parse_warnings=payload_dict["total_parse_warnings"],
    )


def dump_ecosystem_dashboard_input_json(
    dashboard_input: EcosystemDashboardInput,
    path: str,
) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(asdict(dashboard_input), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
