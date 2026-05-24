from __future__ import annotations

from pathlib import Path

from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status


def _touch_report(path: Path, *, mtime: int) -> None:
    path.write_text("report", encoding="utf-8")
    path.touch()
    Path(path).chmod(0o644)
    import os

    os.utime(path, (mtime, mtime))


def test_discover_datacenter_dashboard_status_returns_missing_when_no_files(tmp_path):
    status = discover_datacenter_dashboard_status(str(tmp_path))

    assert status.overall_status == "MISSING"
    assert [report.status for report in status.reports] == [
        "MISSING",
        "MISSING",
        "MISSING",
        "MISSING",
    ]


def test_discover_datacenter_dashboard_status_returns_partial_when_some_files_exist(tmp_path):
    _touch_report(tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.md", mtime=100)
    _touch_report(tmp_path / "datacenter_daily_2026-05-22_0000_full.csv", mtime=200)

    status = discover_datacenter_dashboard_status(str(tmp_path))

    assert status.overall_status == "PARTIAL"
    assert {report.horizon: report.status for report in status.reports} == {
        "rolling 30d": "OK",
        "rolling 5d": "MISSING",
        "rolling 2d": "MISSING",
        "daily": "OK",
    }


def test_discover_datacenter_dashboard_status_returns_ready_when_all_files_exist(tmp_path):
    _touch_report(tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.md", mtime=100)
    _touch_report(tmp_path / "datacenter_rolling_5_2026-05-22_0000_full.md", mtime=110)
    _touch_report(tmp_path / "datacenter_rolling_2_2026-05-22_0000_full.md", mtime=120)
    _touch_report(tmp_path / "datacenter_daily_2026-05-22_0000_full.md", mtime=130)

    status = discover_datacenter_dashboard_status(str(tmp_path))

    assert status.overall_status == "READY"
    assert all(report.status == "OK" for report in status.reports)


def test_discover_datacenter_dashboard_status_selects_newest_matching_file_deterministically(
    tmp_path,
):
    older = tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.csv"
    newer = tmp_path / "datacenter_rolling_30_2026-05-22_0100_full.md"
    _touch_report(older, mtime=100)
    _touch_report(newer, mtime=200)

    status = discover_datacenter_dashboard_status(str(tmp_path))

    rolling_30 = next(report for report in status.reports if report.horizon == "rolling 30d")
    assert rolling_30.path == str(newer)
    assert rolling_30.status == "OK"
    assert rolling_30.modified_at is not None


def test_discover_datacenter_dashboard_status_ignores_unrelated_files(tmp_path):
    _touch_report(tmp_path / "datacenter_weekly_2026-05-22_0000_full.md", mtime=100)
    _touch_report(tmp_path / "notes.txt", mtime=200)

    status = discover_datacenter_dashboard_status(str(tmp_path))

    assert status.overall_status == "MISSING"
    assert all(report.path is None for report in status.reports)
