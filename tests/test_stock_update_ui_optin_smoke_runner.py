from __future__ import annotations

from pathlib import Path

from dev_tools import run_stock_update_ui_optin_smoke as runner


def _touch(path: Path) -> None:
    path.write_text("", encoding="utf-8")


def test_ui_optin_smoke_runner_missing_osakedata_db_fails_before_update_call(
    tmp_path, capsys
):
    analysis_db = tmp_path / "analysis.db"
    _touch(analysis_db)

    code = runner.main(
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


def test_ui_optin_smoke_runner_missing_analysis_db_fails_before_update_call(
    tmp_path, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    _touch(osakedata_db)

    code = runner.main(
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


def test_ui_optin_smoke_runner_success_calls_update_stock_data_with_optin_enabled(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    calls = {}

    def fake_update_stock_data(self, event):
        calls["event"] = event
        calls["use_service"] = self._use_stock_update_service
        calls["osakedata_db_path"] = self.osakedata_db_path
        calls["analysis_db_path"] = self.analysis_db_path
        calls["data_dir"] = self.data_dir
        calls["market"] = self.update_market_dropdown.value
        calls["start_override"] = self.update_start_input.value
        self.loading_text.value = "FAKE RESULT"
        self.update_stock_button.disabled = False
        self._stock_update_in_progress = False

    monkeypatch.setattr(runner.RawCandleApp, "update_stock_data", fake_update_stock_data)

    code = runner.main(
        [
            "--osakedata-db",
            str(osakedata_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "omxh",
            "--start-override",
            "2026-01-01",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert calls == {
        "event": None,
        "use_service": True,
        "osakedata_db_path": str(osakedata_db),
        "analysis_db_path": str(analysis_db),
        "data_dir": str(osakedata_db.resolve().parent),
        "market": "omxh",
        "start_override": "2026-01-01",
    }
    assert "SUMMARY ui_optin_completed=1" in captured.out
    assert "SUMMARY status=OK" in captured.out
    assert "=== LOADING TEXT ===" in captured.out
    assert "FAKE RESULT" in captured.out


def test_ui_optin_smoke_runner_does_not_call_raw_candle_app_init(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        runner.RawCandleApp,
        "__init__",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("__init__ should not be called")
        ),
    )

    def fake_update_stock_data(self, event):
        self.loading_text.value = "FAKE RESULT"
        self.update_stock_button.disabled = False
        self._stock_update_in_progress = False

    monkeypatch.setattr(runner.RawCandleApp, "update_stock_data", fake_update_stock_data)

    code = runner.main(
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


def test_ui_optin_smoke_runner_update_stock_data_exception_becomes_failed_summary(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    monkeypatch.setattr(
        runner.RawCandleApp,
        "update_stock_data",
        lambda self, event: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    code = runner.main(
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


def test_ui_optin_smoke_runner_button_left_disabled_causes_failed_status(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    def fake_update_stock_data(self, event):
        self.loading_text.value = "FAKE RESULT"
        self.update_stock_button.disabled = True
        self._stock_update_in_progress = False

    monkeypatch.setattr(runner.RawCandleApp, "update_stock_data", fake_update_stock_data)

    code = runner.main(
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
    assert "SUMMARY button_disabled=1" in captured.out


def test_ui_optin_smoke_runner_guard_left_in_progress_causes_failed_status(
    tmp_path, monkeypatch, capsys
):
    osakedata_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _touch(osakedata_db)
    _touch(analysis_db)

    def fake_update_stock_data(self, event):
        self.loading_text.value = "FAKE RESULT"
        self.update_stock_button.disabled = False
        self._stock_update_in_progress = True

    monkeypatch.setattr(runner.RawCandleApp, "update_stock_data", fake_update_stock_data)

    code = runner.main(
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
    assert "SUMMARY stock_update_in_progress=1" in captured.out
