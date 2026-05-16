from __future__ import annotations

import argparse
from pathlib import Path

from main import RawCandleApp


class _FakeLoadingText:
    def __init__(self):
        self.value = ""
        self.color = None


class _FakeButton:
    def __init__(self):
        self.disabled = False


class _FakePage:
    def __init__(self):
        self.update_count = 0

    def update(self):
        self.update_count += 1


class _FakeField:
    def __init__(self, value: str):
        self.value = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Developer UI opt-in smoke runner for stock update."
    )
    parser.add_argument("--osakedata-db", required=True)
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--start-override")
    return parser


def _print_failed(error: str) -> int:
    print("SUMMARY status=FAILED")
    print(f"SUMMARY error={error}")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print("This is a developer UI opt-in smoke runner. Use copied databases.")

    osakedata_db_path = Path(args.osakedata_db)
    if not osakedata_db_path.exists():
        return _print_failed(f"Missing osakedata db: {osakedata_db_path}")

    analysis_db_path = Path(args.analysis_db)
    if not analysis_db_path.exists():
        return _print_failed(f"Missing analysis db: {analysis_db_path}")

    app = object.__new__(RawCandleApp)
    app.osakedata_db_path = str(osakedata_db_path)
    app.analysis_db_path = str(analysis_db_path)
    app.data_dir = str(osakedata_db_path.resolve().parent)
    app._use_stock_update_service = True
    app._stock_update_in_progress = False
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField(args.market)
    app.update_start_input = _FakeField(args.start_override or "")

    try:
        app.update_stock_data(None)
    except Exception as exc:
        return _print_failed(str(exc))

    ui_optin_completed = 1
    loading_text_present = 1 if app.loading_text.value else 0
    button_disabled = 1 if app.update_stock_button.disabled else 0
    stock_update_in_progress = 1 if app._stock_update_in_progress else 0
    status = (
        "OK"
        if not app.update_stock_button.disabled and not app._stock_update_in_progress
        else "FAILED"
    )

    print(f"SUMMARY ui_optin_completed={ui_optin_completed}")
    print(f"SUMMARY loading_text_present={loading_text_present}")
    print(f"SUMMARY button_disabled={button_disabled}")
    print(f"SUMMARY stock_update_in_progress={stock_update_in_progress}")
    print(f"SUMMARY page_update_count={app.page.update_count}")
    print(f"SUMMARY status={status}")
    print("=== LOADING TEXT ===")
    print(app.loading_text.value)

    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
