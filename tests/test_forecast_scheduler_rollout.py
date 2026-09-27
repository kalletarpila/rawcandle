from __future__ import annotations

from pathlib import Path

import pytest

from rawcandle.cli import forecasts as cli
from rawcandle.forecasts.scheduler import (
    FORECAST_DAILY_COMMAND,
    FORECAST_INITIAL_MAX_SYMBOLS,
    FORECAST_SCHEDULE_LOCAL,
    FORECAST_TIMEOUT_SECONDS,
    install_scheduler,
    service_unit_text,
    timer_unit_text,
)
from rawcandle.forecasts.hardening import forecast_daily_lock


def test_registration_uses_exact_bounded_independent_command(tmp_path: Path) -> None:
    service = service_unit_text(tmp_path)
    timer = timer_unit_text()

    assert FORECAST_DAILY_COMMAND == (
        "/usr/bin/python3 -m rawcandle.cli.forecasts daily --max-symbols 100"
    )
    assert f"ExecStart={FORECAST_DAILY_COMMAND}" in service
    assert "stock-update-scheduler" not in service
    assert "fundamental" not in service.lower()
    assert "OnCalendar=*-*-* 07:30:00 Europe/Helsinki" in timer
    assert "Unit=rawcandle-forecast-daily.service" in timer


def test_initial_bound_timeout_and_no_automatic_retry() -> None:
    assert FORECAST_INITIAL_MAX_SYMBOLS == 100
    assert FORECAST_TIMEOUT_SECONDS == 1800
    assert "Restart=" not in service_unit_text("/tmp/repo")


def test_scheduler_install_dry_run_does_not_write(tmp_path: Path) -> None:
    result = install_scheduler(
        repo_root=tmp_path, user_unit_dir=tmp_path / "units", apply=False
    )

    assert result["mode"] == "DRY_RUN"
    assert result["max_symbols"] == 100
    assert result["automatic_retry"] is False
    assert not (tmp_path / "units").exists()


def test_scheduler_registration_writes_units_without_activation(tmp_path: Path) -> None:
    units = tmp_path / "units"
    result = install_scheduler(
        repo_root=tmp_path, user_unit_dir=units, apply=True, activate=False
    )

    assert result["activated"] is False
    assert (units / "rawcandle-forecast-daily.service").read_text() == service_unit_text(tmp_path)
    assert (units / "rawcandle-forecast-daily.timer").read_text() == timer_unit_text()


def test_daily_cli_requires_explicit_max_symbols() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["daily"])


@pytest.mark.parametrize(
    ("terminal_status", "exit_code"),
    [("SUCCESS", 0), ("PARTIAL", 2)],
)
def test_daily_cli_terminal_status_mapping(
    monkeypatch: pytest.MonkeyPatch, terminal_status: str, exit_code: int
) -> None:
    monkeypatch.setattr(
        cli, "daily_workflow",
        lambda **kwargs: {"terminal_status": terminal_status},
    )

    assert cli.main(["daily", "--max-symbols", "100"]) == exit_code


def test_daily_cli_failure_maps_to_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "daily_workflow",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("failed")),
    )

    assert cli.main(["daily", "--max-symbols", "100"]) == 1


def test_manual_acquire_cli_respects_daily_overlap_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "forecasts.db"
    with forecast_daily_lock(database):
        result = cli.main([
            "acquire", "--db", str(database),
            "--fundamentals-db", str(tmp_path / "fundamentals.db"),
            "--symbols", "TEST",
        ])

    assert result == 1
    assert "OVERLAP_ACTIVE" in capsys.readouterr().err
