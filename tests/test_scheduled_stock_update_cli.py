from __future__ import annotations

from pathlib import Path

import pytest

from rawcandle.cli import run_scheduled_stock_update as cli
from services.stock_update_service import STATUS_OK, StockUpdateResult


def _touch(path: Path) -> None:
    path.write_text("", encoding="utf-8")


def test_scheduled_stock_update_cli_missing_osakedata_db_fails_before_service_call(
    tmp_path, capsys
):
    analysis_db = tmp_path / "analysis.db"
    _touch(analysis_db)

    code = cli.main(
        [
            "--osakedata-db",
            str(tmp_path / "missing-osakedata.db"),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY status=FAILED" in captured.out


def test_scheduled_stock_update_cli_missing_analysis_db_fails_before_service_call(
    tmp_path, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    _touch(osakedata_db)

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(tmp_path / "missing-analysis.db"),
            "--market",
            "omxh",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY status=FAILED" in captured.out


def test_scheduled_stock_update_cli_different_db_directories_fail(tmp_path, capsys):
    osakedata_dir = tmp_path / "osakedata_dir"
    analysis_dir = tmp_path / "analysis_dir"
    osakedata_dir.mkdir()
    analysis_dir.mkdir()
    osakedata_db = osakedata_dir / "osakedata.db"
    analysis_db = analysis_dir / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY status=FAILED" in captured.out
    assert "same directory" in captured.out or "data_dir" in captured.out


def test_scheduled_stock_update_cli_success_calls_service_wrapper(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    calls = {}

    def fake_run_stock_update_via_service(self, **kwargs):
        calls["self"] = self
        calls["kwargs"] = kwargs
        return StockUpdateResult(market="omxh", status=STATUS_OK)

    monkeypatch.setattr(
        cli.RawCandleApp,
        "_run_stock_update_via_service",
        fake_run_stock_update_via_service,
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_format_stock_update_service_result_for_ui",
        lambda self, result: "UI RESULT",
    )

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
            "--start-override",
            "2026-01-01",
            "--today",
            "2026-05-16",
            "--fetch-until-exclusive",
            "2026-05-17",
        ]
    )

    capsys.readouterr()
    assert code == 0
    assert calls["kwargs"] == {
        "market": "omxh",
        "start_override": "2026-01-01",
        "today": "2026-05-16",
        "fetch_until_exclusive": "2026-05-17",
    }
    assert calls["self"].osakedata_db_path == str(osakedata_db)
    assert calls["self"].analysis_db_path == str(analysis_db)
    assert calls["self"].data_dir == str(osakedata_db.resolve().parent)


def test_scheduled_stock_update_cli_prints_summary_lines(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        cli.RawCandleApp,
        "_run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(
            market="omxh",
            tickers_checked=2,
            tickers_updated=1,
            status=STATUS_OK,
        ),
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_format_stock_update_service_result_for_ui",
        lambda self, result: "UI RESULT",
    )

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY market=omxh" in captured.out
    assert "SUMMARY tickers_checked=2" in captured.out
    assert "SUMMARY status=OK" in captured.out
    assert "=== UI SUMMARY ===" in captured.out


def test_scheduled_stock_update_cli_service_exception_becomes_failed_summary(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        cli.RawCandleApp,
        "_run_stock_update_via_service",
        lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY status=FAILED" in captured.out
    assert "SUMMARY error=boom" in captured.out


def test_scheduled_stock_update_cli_does_not_instantiate_full_ui_app(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        cli.RawCandleApp,
        "__init__",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("__init__ should not be called")
        ),
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market="omxh", status=STATUS_OK),
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_format_stock_update_service_result_for_ui",
        lambda self, result: "UI RESULT",
    )

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    capsys.readouterr()
    assert code == 0


def test_scheduled_stock_update_cli_does_not_call_update_stock_data(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        cli.RawCandleApp,
        "update_stock_data",
        lambda self, event: (_ for _ in ()).throw(
            AssertionError("update_stock_data should not be called")
        ),
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_run_stock_update_via_service",
        lambda self, **kwargs: StockUpdateResult(market="omxh", status=STATUS_OK),
    )
    monkeypatch.setattr(
        cli.RawCandleApp,
        "_format_stock_update_service_result_for_ui",
        lambda self, result: "UI RESULT",
    )

    code = cli.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
        ]
    )

    capsys.readouterr()
    assert code == 0


def test_scheduled_stock_update_cli_parser_rejects_dry_run():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "--osakedata-db",
                "a.db",
                "--analysis-db",
                "b.db",
                "--market",
                "omxh",
                "--dry-run",
            ]
        )
