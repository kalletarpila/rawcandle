from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from rawcandle.research.phase12c1_audit import (
    _phase12b_feasibility, analyze_source, connect_ro, discover_history_policy, redact_command,
    result_fingerprint, write_csv, write_json,
)


FIELDS = [
    "ticker", "dimension", "calendardate", "reportperiod", "fiscalperiod",
    "date", "lastupdated", "revenue", "opinc", "fcf", "cashneq", "debt",
    "sharesbas",
]


def _source(path: Path) -> None:
    rows = [
        ["OLD", "ARQ", "2014-12-31", "2014-12-31", "2014-Q4", "2015-02-01", "2020-01-01", "1", "1", "1", "1", "0", "1"],
        ["AAA", "ARQ", "2015-06-30", "2015-06-30", "2015-Q2", "2015-08-01", "2020-01-01", "2", "1", "1", "1", "0", "1"],
        ["AAA", "ARQ", "2015-06-30", "2015-06-30", "2015-Q2", "2015-08-01", "2021-01-01", "3", "1", "1", "1", "0", "1"],
        ["AAA", "MRQ", "2015-06-30", "2015-06-30", "2015-Q2", "2015-08-01", "2021-01-01", "3", "1", "1", "1", "0", "1"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(rows)


def test_policy_discovery_finds_five_year_regression_path(tmp_path: Path) -> None:
    for relative in ("rawcandle/fundamentals/schema", "tests", "docs/fundamentals_v4"):
        (tmp_path / relative).mkdir(parents=True)
    (tmp_path / "rawcandle/fundamentals/schema/production_bootstrap.py").write_text(
        "download_sharadar_5y_bulk()\n# years=5\n", encoding="utf-8")
    (tmp_path / "rawcandle/fundamentals/schema/phase12c_backfill.py").write_text(
        "# years=10\n", encoding="utf-8")
    policy, locations = discover_history_policy(tmp_path)
    assert policy["verdict"] == "HISTORY_POLICY_CORRECTION_REQUIRED"
    assert policy["can_regress_to_five_years"] is True
    assert {row["path"] for row in locations} == {
        "rawcandle/fundamentals/schema/phase12c_backfill.py",
        "rawcandle/fundamentals/schema/production_bootstrap.py",
    }


def test_global_target_earliest_and_revision_counts_reconcile(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    _source(source)
    result = analyze_source(
        source, {"AAA"}, {"AAA"}, {},
        {"OLD": {"first_date": "2018-01-01", "last_date": "2019-01-01", "rows": 5}},
        {}, "2015-06-30",
    )
    assert result["source"]["rows_by_dimension"]["ARQ"] == 3
    assert result["target_rows"]["ARQ"] == 2
    assert result["global_base_period_counts"]["ARQ"] == 2
    assert result["revision_extra_rows"]["ARQ"] == 1
    assert result["early_arq_rows"][0]["reason"] == "OUTSIDE_CURRENT_TARGET_UNIVERSE"
    assert result["excluded_identities"][0]["direct_market_match"] is True


def test_machine_outputs_are_deterministic_and_parseable(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    payload = {"z": [2, 1], "a": {"x": None}}
    write_json(first, payload)
    write_json(second, payload)
    assert first.read_bytes() == second.read_bytes()
    assert result_fingerprint(payload) == result_fingerprint(payload)
    write_csv(tmp_path / "a.csv", [{"b": 2, "a": 1}])
    write_csv(tmp_path / "b.csv", [{"a": 1, "b": 2}])
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()


def test_read_only_connection_prevents_production_style_write(tmp_path: Path) -> None:
    database = tmp_path / "database.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(value TEXT)")
    with connect_ro(database) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("INSERT INTO evidence VALUES('changed')")


def test_credential_redaction() -> None:
    command = "SHARADAR_API_KEY=top-secret python -m audit"
    redacted = redact_command(command)
    assert "top-secret" not in redacted
    assert "<REDACTED>" in redacted


def test_phase12b_feasibility_separates_fiscal_and_availability_years() -> None:
    latest = {}
    for offset in range(8):
        index = 2021 * 4 + 3 - offset
        fiscal_year, quarter_index = divmod(index, 4)
        fiscalperiod = f"{fiscal_year}-Q{quarter_index + 1}"
        row = {
            "fiscalperiod": fiscalperiod,
            "date": "2022-01-15" if offset == 0 else "2021-01-15",
            "revenue": "1", "opinc": "1", "fcf": "1", "cashneq": "1",
            "debt": "0", "sharesbas": "1",
        }
        latest[("AAA", fiscalperiod)] = (("2022-01-15", "", str(offset)), row)
    rows = _phase12b_feasibility(latest)["by_year"]
    fiscal_2021 = next(row for row in rows if row["basis"] == "FISCAL_PERIOD_YEAR" and row["year"] == "2021")
    available_2022 = next(row for row in rows if row["basis"] == "AVAILABILITY_YEAR" and row["year"] == "2022")
    assert fiscal_2021["score_raw_feasible"] == 1
    assert available_2022["score_raw_feasible"] == 1
