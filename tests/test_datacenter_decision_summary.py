from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from rawcandle.datacenter_decision_summary import (
    DecisionSummaryError,
    SECTION_DESCRIPTIONS,
    build_decision_summary,
    compare_watchlist_status,
    extract_section,
    first_table,
)


CURRENT_DAILY = """# Datacenter Daily Swing Signal Report

## 1. Title and run metadata
signal_date: 2026-08-03
signal_version: DC_SWING_SIGNAL_V1
ohlc_calc_version: DC_SWING_OHLC_V1
taxonomy_version: DC_TAXONOMY_FULL_V1
generated_at_utc: 2026-08-04T05:14:33Z

## Watchlist Summary
| metric | value |
| --- | --- |
| watchlist_tickers_total | 3 |
| watchlist_in_datacenter_taxonomy | 2 |
| watchlist_not_in_datacenter_taxonomy | 1 |
| watchlist_missing_price | 0 |
| watchlist_subindustry_context_risk_count | 1 |
| watchlist_layer_context_risk_count | 2 |
| watchlist_both_context_risk_count | 1 |
| watchlist_breakout_count | 1 |
| watchlist_pullback_count | 0 |
| watchlist_high_exit_risk_count | 1 |
| watchlist_medium_exit_risk_count | 0 |

| ticker | watchlist_status | in_datacenter_ecosystem | primary_layer | primary_subindustry | close | return_5d | return_10d | return_20d | distance_to_ema20_pct | ticker_trend_state | latest_structure_label | latest_bos_event_type | latest_bos_freshness | latest_reset_reason | latest_reset_freshness | breakout_signal | pullback_signal | exit_risk_signal | exit_risk_severity | exit_reason | subindustry_timing_state | subindustry_overheat_risk_level | layer_timing_state | layer_overheat_risk_level | price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMZN | BREAKOUT_CANDIDATE | YES | Cloud | Hyperscalers | 100 | 0.1 | 0.2 | 0.3 | 0.05 | UP | HH | BOS_UP | FRESH | DOUBLE_BOS_UP | FRESH | 1 | 0 | 0 |  |  | BUY_ZONE | LOW | BUY_ZONE | LOW | OK |
| GFS | HIGH_EXIT_RISK | YES | Semis | Foundry | 50 | -0.1 | -0.2 | -0.3 | -0.1 | DOWN | LL | BOS_DOWN | FRESH | DOUBLE_BOS_DOWN | FRESH | 0 | 0 | 1 | HIGH | close_below_ema20 | EXIT_ZONE | LOW | EXIT_ZONE | LOW | OK |
| POET | NOT_PART_OF_DATACENTER_ECOSYSTEM | NO |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## 6. Buy-Zone Subindustries
| group_name | timing_state | return_5d | return_10d | return_20d | return_60d | pct_above_ema20 | ema20_breadth_delta_5d | trend_breadth | weakness_breadth | data_quality_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hyperscalers | BUY_ZONE | 0.1 | 0.2 | 0.3 | 0.4 | 80 | 20 | 70 | 30 | OK |

## 7. Add-On Pullback Subindustries
No rows.

## 8. Trim/Watch Subindustries
No rows.

## 9. Exit-Zone Subindustries
| group_name | timing_state | return_5d | return_10d | return_20d | return_60d | pct_above_ema20 | ema20_breadth_delta_5d | trend_breadth | weakness_breadth | data_quality_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Foundry | EXIT_ZONE | -0.1 | -0.2 | -0.3 | -0.4 | 10 | -20 | 0 | 100 | OK |

## 12. Breakout Ticker Scanner
| ticker | primary_layer | primary_subindustry | close | return_5d | return_10d | return_20d | distance_to_ema20_pct | volume_vs_avg20 | latest_structure_label | ticker_trend_state | latest_bos_event_type | latest_bos_freshness | latest_reset_reason | latest_reset_freshness | price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMZN | Cloud | Hyperscalers | 100 | 0.1 | 0.2 | 0.3 | 0.05 | 1.4 | HH | UP | BOS_UP | FRESH | DOUBLE_BOS_UP | FRESH | OK |

## 13. Pullback Ticker Scanner
No rows.

## 14. Exit-Risk Ticker Scanner
| ticker | primary_layer | primary_subindustry | close | return_5d | return_10d | return_20d | distance_to_ema20_pct | latest_structure_label | ticker_trend_state | exit_risk_severity | exit_reason | price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GFS | Semis | Foundry | 50 | -0.1 | -0.2 | -0.3 | -0.1 | LL | DOWN | HIGH | close_below_ema20 | OK |
"""


PREVIOUS_DAILY = CURRENT_DAILY.replace("2026-08-03", "2026-07-31").replace(
    "| AMZN | BREAKOUT_CANDIDATE", "| AMZN | NEUTRAL_MONITOR"
).replace("| GFS | HIGH_EXIT_RISK", "| GFS | MEDIUM_EXIT_RISK").replace(
    "| watchlist_breakout_count | 1 |", "| watchlist_breakout_count | 0 |"
).replace(
    "| watchlist_high_exit_risk_count | 1 |", "| watchlist_high_exit_risk_count | 0 |"
)


ROLLING2 = """# Datacenter Rolling Swing Report

## 1. Title and run metadata
signal_date: 2026-08-03

## 4. Ecosystem window change
| metric | first_value | last_value | change |
| --- | --- | --- | --- |
| return_5d | -0.01 | 0.02 | 0.03 |
| return_10d | 0.01 | 0.02 | 0.01 |
| return_20d | -0.04 | -0.03 | 0.01 |
| pct_above_ma10 | 45 | 65 | 20 |
| pct_above_ema20 | 35 | 50 | 15 |
| ema20_breadth_delta_5d | 8 | 20 | 12 |
| trend_breadth | 30 | 32 | 2 |
| weakness_breadth | 70 | 68 | -2 |
| timing_state | EXIT_ZONE | BUY_ZONE | EXIT_ZONE -> BUY_ZONE |
| overheat_risk_level | LOW | LOW | LOW -> LOW |
| data_quality_status | OK | OK | OK -> OK |
"""


ROLLING5 = """# Datacenter Rolling Swing Report

## 1. Title and run metadata
signal_date: 2026-08-03

## 8. Repeated breakout tickers
| ticker | breakout_days | first_signal_date | last_signal_date | last_primary_layer | last_primary_subindustry | last_close | last_return_5d | last_return_10d | last_volume_vs_avg20 | last_latest_structure_label | last_ticker_trend_state | last_latest_bos_event_type | last_latest_bos_freshness | last_latest_reset_reason | last_latest_reset_freshness | last_price_data_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMZN | 1 | 2026-08-03 | 2026-08-03 | Cloud | Hyperscalers | 100 | 0.1 | 0.2 | 1.4 | HH | UP | BOS_UP | FRESH | DOUBLE_BOS_UP | FRESH | OK |

## 9. Repeated pullback tickers
No rows.

## Rolling 5 Pullback Alerts
No rows.
"""


ROLLING30 = """# Datacenter Rolling Swing Report

## 1. Title and run metadata
signal_date: 2026-08-03

## Rolling 30 Buy Filter
| ticker | rolling_30_buy_state | primary_layer | primary_subindustry | window_watchlist_status | current_watchlist_status | breakout_days | pullback_days | exit_risk_days | latest_ticker_trend_state | latest_structure_label | primary_reason | blocking_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMZN | WATCH_ZONE | Cloud | Hyperscalers | HIGH_EXIT_RISK | BREAKOUT_CANDIDATE | 1 | 0 | 3 | UP | HH | MIXED | HISTORICAL_WINDOW_HIGH_EXIT_RISK |

## Rolling 30 Exit Prefilter
| ticker | rolling_30_exit_state | primary_layer | primary_subindustry | window_watchlist_status | current_watchlist_status | exit_risk_days | latest_exit_risk_severity | latest_exit_reason | latest_ticker_trend_state | primary_reason | risk_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GFS | EXTREME | Semis | Foundry | HIGH_EXIT_RISK | HIGH_EXIT_RISK | 30 | HIGH | close_below_ema20 | DOWN | EXTREME_EXIT_RISK | HIGH_SEVERITY_WITH_FRESH_BREAKDOWN |
"""


def test_markdown_table_extraction() -> None:
    section = extract_section(CURRENT_DAILY, "12. Breakout Ticker Scanner")
    rows = first_table(section)
    assert rows[0]["ticker"] == "AMZN"
    assert rows[0]["primary_subindustry"] == "Hyperscalers"


def test_missing_required_section_raises() -> None:
    with pytest.raises(DecisionSummaryError):
        extract_section(CURRENT_DAILY, "Missing Section")


def test_current_vs_previous_status_comparison() -> None:
    current = first_table(extract_section(CURRENT_DAILY, "Watchlist Summary").split("\n\n", 1)[1])
    previous = first_table(extract_section(PREVIOUS_DAILY, "Watchlist Summary").split("\n\n", 1)[1])
    changes = compare_watchlist_status(current, previous)
    assert {"ticker": "AMZN", "previous_status": "NEUTRAL_MONITOR", "current_status": "BREAKOUT_CANDIDATE", "previous_rank": "4", "current_rank": "5"} in changes["improved"]
    assert {"ticker": "GFS", "previous_status": "MEDIUM_EXIT_RISK", "current_status": "HIGH_EXIT_RISK", "previous_rank": "2", "current_rank": "1"} in changes["deteriorated"]


def test_build_summary_contains_required_headers_and_no_rows(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    output = tmp_path / "datacenter_decision_summary_2026-08-03_0813_full.md"
    build_decision_summary(output=output, **paths)
    text = output.read_text(encoding="utf-8")
    assert "## 1. Title and run metadata" in text
    assert "## 3. Ecosystem dashboard change" in text
    assert "| pct_above_ema20 | 35 | 50 | 15 |" in text
    assert "### B. Daily Pullback Ticker Scanner\nNo rows." in text
    assert "### Not in Datacenter taxonomy" in text
    assert "| POET | NOT_PART_OF_DATACENTER_ECOSYSTEM | NO |  |" in text
    assert "| daily_breakouts | MONITOR_BREAKOUT_CONFIRMATION | AMZN |" in text
    assert "| watchlist_exit_risk | REVIEW_EXIT_RISK | watchlist_high_exit_risk_count=1 |" in text


def test_build_summary_without_csv_keeps_markdown_output_unchanged(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    markdown_only = tmp_path / "markdown_only.md"
    with_csv = tmp_path / "with_csv.md"
    csv_output = tmp_path / "with_csv.csv"

    build_decision_summary(output=markdown_only, **paths)
    build_decision_summary(output=with_csv, output_csv=csv_output, **paths)

    assert markdown_only.read_text(encoding="utf-8") == with_csv.read_text(encoding="utf-8")
    assert csv_output.exists()


def test_build_summary_writes_semicolon_csv_with_representative_rows(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    output = tmp_path / "summary.md"
    output_csv = tmp_path / "summary.csv"

    build_decision_summary(output=output, output_csv=output_csv, **paths)

    text = output_csv.read_text(encoding="utf-8")
    assert text.startswith("section;subsection;row_type;field;value;previous_value;current_value;change;ticker;group_name;metric;notes\n")
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    assert any(row["section"] == "1. Title and run metadata" and row["field"] == "current_signal_date" and row["value"] == "2026-08-03" for row in rows)
    assert any(row["section"] == "2. Executive signal" and row["field"] == "ecosystem_timing" and row["value"] == "BUY_ZONE" for row in rows)
    assert any(row["section"] == "7. Watchlist ticker decision table" and row["ticker"] == "AMZN" and row["field"] == "watchlist_status" and row["value"] == "BREAKOUT_CANDIDATE" for row in rows)
    assert any(row["section"] == "8. Scanner output" and row["subsection"] == "A. Daily Breakout Ticker Scanner" and row["ticker"] == "AMZN" for row in rows)
    assert any(row["section"] == "10. Action summary" and row["field"] == "watchlist_exit_risk" and row["value"] == "REVIEW_EXIT_RISK" for row in rows)


def test_section_descriptions_are_inserted_under_sections_2_through_10(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    output = tmp_path / "datacenter_decision_summary_2026-08-03_0813_full.md"
    build_decision_summary(output=output, **paths)
    text = output.read_text(encoding="utf-8")

    for section, description in SECTION_DESCRIPTIONS.items():
        heading = f"## {section}"
        assert f"{heading}\n\n{description}\n\n" in text

    assert "## 1. Title and run metadata\n\nThis section" not in text
    assert "## 1. Title and run metadata\n| field | value |" in text
    assert "| signal | value |" in text
    assert "| metric | previous_value | current_value | change |" in text
    assert "| area | label | basis |" in text


def test_cli_requires_inputs(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "rawcandle.cli.build_datacenter_decision_summary", "--output", str(tmp_path / "out.md")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--current-daily" in result.stderr


def test_cli_creates_output_file(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    output = tmp_path / "summary.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rawcandle.cli.build_datacenter_decision_summary",
            "--current-daily",
            str(paths["current_daily"]),
            "--previous-daily",
            str(paths["previous_daily"]),
            "--current-rolling2",
            str(paths["current_rolling2"]),
            "--current-rolling5",
            str(paths["current_rolling5"]),
            "--current-rolling30",
            str(paths["current_rolling30"]),
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert output.exists()
    assert "wrote" in result.stdout


def test_cli_accepts_output_csv_and_creates_csv_file(tmp_path: Path) -> None:
    paths = _write_fixture_set(tmp_path)
    output = tmp_path / "summary.md"
    output_csv = tmp_path / "summary.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rawcandle.cli.build_datacenter_decision_summary",
            "--current-daily",
            str(paths["current_daily"]),
            "--previous-daily",
            str(paths["previous_daily"]),
            "--current-rolling2",
            str(paths["current_rolling2"]),
            "--current-rolling5",
            str(paths["current_rolling5"]),
            "--current-rolling30",
            str(paths["current_rolling30"]),
            "--output",
            str(output),
            "--output-csv",
            str(output_csv),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert output.exists()
    assert output_csv.exists()
    assert "wrote" in result.stdout


def _write_fixture_set(tmp_path: Path) -> dict[str, Path]:
    files = {
        "current_daily": CURRENT_DAILY,
        "previous_daily": PREVIOUS_DAILY,
        "current_rolling2": ROLLING2,
        "current_rolling5": ROLLING5,
        "current_rolling30": ROLLING30,
    }
    paths: dict[str, Path] = {}
    for name, content in files.items():
        path = tmp_path / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths
