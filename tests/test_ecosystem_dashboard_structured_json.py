from __future__ import annotations

import json

import pytest

from dev_tools.ecosystem_dashboard_input_model import (
    EcosystemDashboardActionSummaryInput,
    EcosystemDashboardInput,
    EcosystemDashboardSourceReportInput,
)
from dev_tools.ecosystem_dashboard_structured_json import (
    load_ecosystem_dashboard_input_json,
)


def _minimal_payload() -> dict[str, object]:
    return {
        "ecosystem_code": "DATACENTER",
        "report_date": "2026-05-22",
        "readiness": "READY",
        "total_parsed_rows": 1,
        "total_parse_warnings": 0,
        "source_reports": [
            {
                "source_report_path": "structured://test",
                "source_report_type": "structured",
                "source_report_date": "2026-05-22",
                "loaded_row_count": 1,
                "status": "OK",
            }
        ],
        "action_summary": [
            {
                "action_bucket": "WATCH",
                "action_label": "Watch Candidate",
                "ticker_count": 1,
                "weight_sum": 1.5,
                "notes": None,
            }
        ],
        "market_map": [],
        "watchlist": [],
        "tickers": [],
        "decision_trace": [],
    }


def test_load_ecosystem_dashboard_input_json_loads_minimal_valid_json(tmp_path):
    json_path = tmp_path / "dashboard_input.json"
    json_path.write_text(json.dumps(_minimal_payload()), encoding="utf-8")

    dashboard_input = load_ecosystem_dashboard_input_json(str(json_path))

    assert isinstance(dashboard_input, EcosystemDashboardInput)
    assert isinstance(
        dashboard_input.source_reports[0], EcosystemDashboardSourceReportInput
    )
    assert isinstance(
        dashboard_input.action_summary[0], EcosystemDashboardActionSummaryInput
    )
    assert dashboard_input.ecosystem_code == "DATACENTER"
    assert dashboard_input.report_date == "2026-05-22"


def test_load_ecosystem_dashboard_input_json_preserves_none_and_numeric_types(tmp_path):
    payload = _minimal_payload()
    payload["action_summary"][0]["notes"] = None
    payload["action_summary"][0]["weight_sum"] = 1.5
    json_path = tmp_path / "dashboard_input.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    dashboard_input = load_ecosystem_dashboard_input_json(str(json_path))

    assert dashboard_input.action_summary[0].notes is None
    assert dashboard_input.action_summary[0].weight_sum == 1.5
    assert isinstance(dashboard_input.action_summary[0].weight_sum, float)
    assert dashboard_input.source_reports[0].loaded_row_count == 1
    assert isinstance(dashboard_input.source_reports[0].loaded_row_count, int)


def test_load_ecosystem_dashboard_input_json_missing_required_top_level_fields_fails(
    tmp_path,
):
    payload = _minimal_payload()
    del payload["ecosystem_code"]
    json_path = tmp_path / "dashboard_input.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required fields: ecosystem_code"):
        load_ecosystem_dashboard_input_json(str(json_path))
