from __future__ import annotations

import importlib

import pytest

from dev_tools.report_canonical_v2_retired import RETIRED_MESSAGE


CANONICAL_V2_CLI_MODULES = (
    "dev_tools.run_report_canonical_v2_all_outputs_smoke",
    "dev_tools.run_report_canonical_v2_daily_csv",
    "dev_tools.run_report_canonical_v2_daily_markdown",
    "dev_tools.run_report_canonical_v2_daily_markdown_smoke",
    "dev_tools.run_report_canonical_v2_output",
    "dev_tools.run_report_canonical_v2_parity_audit",
    "dev_tools.run_report_canonical_v2_publish_outputs",
    "dev_tools.run_report_canonical_v2_rolling2_csv",
    "dev_tools.run_report_canonical_v2_rolling2_markdown",
    "dev_tools.run_report_canonical_v2_rolling30_csv",
    "dev_tools.run_report_canonical_v2_rolling30_markdown",
    "dev_tools.run_report_canonical_v2_rolling5_csv",
    "dev_tools.run_report_canonical_v2_rolling5_markdown",
)


@pytest.mark.parametrize("module_name", CANONICAL_V2_CLI_MODULES)
def test_canonical_v2_dev_tool_entrypoint_is_retired(module_name: str, capsys) -> None:
    module = importlib.import_module(module_name)

    exit_code = module.main(["--db", "/should/not/be/opened.sqlite"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == RETIRED_MESSAGE
