from types import SimpleNamespace

import pytest

from regression import view as regression_view_module


class DummyPage:
    def __init__(self):
        self.update_calls = 0

    def update(self):
        self.update_calls += 1


@pytest.fixture
def regression_view(monkeypatch):
    monkeypatch.setattr(
        regression_view_module,
        "list_markets",
        lambda: [{"name": "USA", "abbreviation": "usa"}],
    )
    page = DummyPage()
    view = regression_view_module.RegressionView(page, lambda: None)
    default_features = regression_view_module.run_regression.FEATURE_COLUMNS
    pattern_name = regression_view_module.run_regression.PATTERN_COLUMN
    market_name = regression_view_module.run_regression.MARKET_COLUMN
    view.feature_names = [
        default_features[0],
        default_features[1],
        default_features[2],
        "is_candle_day",
        pattern_name,
        market_name,
    ]
    view.feature_checkboxes = {
        default_features[0]: SimpleNamespace(value=True),
        default_features[1]: SimpleNamespace(value=False),
        default_features[2]: SimpleNamespace(value=True),
        "is_candle_day": SimpleNamespace(value=True),
        pattern_name: SimpleNamespace(value=True),
        market_name: SimpleNamespace(value=False),
    }
    view.market_dropdown = SimpleNamespace(value="__all__")
    view.pattern_dropdown = SimpleNamespace(value="__all__")
    view.horizon_checkboxes = {5: SimpleNamespace(value=True)}
    view.success_threshold_fields = {
        5: SimpleNamespace(value="0.03", error_text=None),
    }
    view.require_blackout_checkbox = SimpleNamespace(value=False)
    view.run_button = SimpleNamespace(disabled=False)
    view.status_text = SimpleNamespace(value="", color="")
    view.output_field = SimpleNamespace(value="")
    view.page = page
    return view


def test_get_selected_features_returns_selected_list(regression_view):
    defaults = regression_view_module.run_regression.FEATURE_COLUMNS
    pattern_name = regression_view_module.run_regression.PATTERN_COLUMN
    expected = [defaults[0], defaults[2], "is_candle_day", pattern_name]
    assert regression_view._get_selected_features() == expected


def test_get_selected_features_falls_back_to_defaults(regression_view):
    for checkbox in regression_view.feature_checkboxes.values():
        checkbox.value = False
    selected = regression_view._get_selected_features()
    assert selected == regression_view.feature_names.copy()


def test_on_run_clicked_passes_selected_features(monkeypatch, regression_view):
    captured = {}
    expected_features = regression_view._get_selected_features()

    def fake_run_regression_for_market(*args, **kwargs):
        captured["feature_columns"] = kwargs.get("feature_columns")
        return {
            "report": "OK",
            "warnings": [],
            "report_path": None,
            "success_horizons": kwargs.get("success_horizons", []),
            "horizons": {},
        }

    monkeypatch.setattr(
        regression_view_module.run_regression,
        "run_regression_for_market",
        fake_run_regression_for_market,
    )

    regression_view._on_run_clicked(None)

    expected_payload = expected_features + [
        regression_view_module.run_regression.FEATURE_SELECTION_MARKER
    ]
    assert captured["feature_columns"] == expected_payload
    assert regression_view.output_field.value == "OK"
