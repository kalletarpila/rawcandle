from __future__ import annotations

import os
from pathlib import Path


def test_start_dc_dashboard_ui_script_exists_and_is_executable():
    script_path = Path("/home/kalle/projects/rawcandle/start_dc_dashboard_ui")

    assert script_path.exists()
    assert os.access(script_path, os.X_OK)


def test_start_dc_dashboard_ui_script_contains_expected_commands():
    script_path = Path("/home/kalle/projects/rawcandle/start_dc_dashboard_ui")
    text = script_path.read_text(encoding="utf-8")

    assert 'EXPECTED_REPO_ROOT="/home/kalle/projects/rawcandle"' in text
    assert 'REPORTS_DIR="/home/kalle/projects/rawcandle/temp"' in text
    assert 'OUTPUT_HTML="/home/kalle/projects/rawcandle/temp/datacenter_dashboard.html"' in text
    assert "dev_tools/run_datacenter_dashboard_html.py" in text
    assert "--reports-dir" in text
    assert "--output" in text
    assert "SUMMARY html_output=" in text
    assert "command -v firefox" in text
    assert "command -v firefox.exe" in text
    assert "command -v xdg-open" in text
    assert "command -v explorer.exe" in text
