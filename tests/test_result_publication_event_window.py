from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication_research_export import EXPORT_COLUMNS
from rawcandle.research.result_publication_event_window import (
    EVENT_WINDOW_COLUMNS,
    build_event_window_dataset,
    summarize_event_windows,
    validate_publication_input,
)


def _publication(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in EXPORT_COLUMNS}
    row.update(
        {
            "company_id": "7",
            "ticker": "AAPL",
            "fiscal_year": "2025",
            "fiscal_quarter": "Q1",
            "research_status": "EXACT",
            "research_confidence": "EXACT",
            "research_method": "CANONICAL_VERIFIED",
            "research_publication_date": "2025-02-06",
            "research_publication_session": "AFTER_MARKET",
            "first_full_post_result_trading_date": "2025-02-07",
            "canonical_authority_status": "VERIFIED",
            "is_canonical": "True",
            "rule_version": "result_publication_daily_research_v1",
        }
    )
    row.update(overrides)
    return row


def _publication_files(tmp_path: Path, rows: list[dict[str, str]]) -> tuple[Path, Path]:
    publication = tmp_path / "publication.csv"
    with publication.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(publication.read_bytes()).hexdigest()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["research_status"]] = counts.get(row["research_status"], 0) + 1
    metadata = tmp_path / "publication.metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "artifact_version": "result_publication_research_export_v1",
                "projection_rule_version": "result_publication_daily_research_v1",
                "output": str(publication.resolve()),
                "output_sha256": digest,
                "exported_rows": len(rows),
                "status_counts": counts,
                "filters": {"include_unusable": False},
            }
        ),
        encoding="utf-8",
    )
    return publication, metadata


def _weekdays(start: date, count: int) -> list[date]:
    values: list[date] = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def _ohlc(tmp_path: Path, *, stock_count: int = 70) -> Path:
    path = tmp_path / "ohlc.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE osakedata (id INTEGER PRIMARY KEY, osake TEXT, pvm TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume INTEGER)"
    )
    days = _weekdays(date(2025, 1, 1), 70)
    rows = []
    for index, day in enumerate(days):
        if index < stock_count:
            close = 100.0 + index
            rows.append(("AAPL", day.isoformat(), close - 1, close + 1, close - 2, close, 1000 + index))
        spy_close = 200.0 + index * 0.5
        rows.append(("SPY", day.isoformat(), spy_close - 1, spy_close + 1, spy_close - 2, spy_close, 2000 + index))
    connection.executemany(
        "INSERT INTO osakedata(osake,pvm,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    connection.execute("CREATE UNIQUE INDEX idx_osake_pvm ON osakedata(osake,pvm)")
    connection.commit()
    connection.close()
    return path


def _build(tmp_path: Path, rows: list[dict[str, str]], *, stock_count: int = 70):
    publication, metadata = _publication_files(tmp_path, rows)
    output = tmp_path / "events.csv"
    output_metadata = tmp_path / "events.metadata.json"
    result = build_event_window_dataset(
        publication,
        metadata,
        _ohlc(tmp_path, stock_count=stock_count),
        output,
        output_metadata,
        generated_at_utc="2026-09-29T00:00:00Z",
    )
    with output.open(newline="", encoding="utf-8") as handle:
        output_rows = list(csv.DictReader(handle))
    return result, output_rows, output, output_metadata


def test_exact_boundary_offsets_and_weekend(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    row = rows[0]
    assert row["D0_date"] == "2025-02-07"
    assert row["date_Dm1"] == "2025-02-06"
    assert row["date_Dp1"] == "2025-02-10"
    assert (row["Dm1_close"], row["D0_open"], row["D0_close"], row["Dp1_close"]) == (
        "126.0",
        "126.0",
        "127.0",
        "128.0",
    )
    assert row["first_full_post_result_trading_date"] == row["D0_date"]


def test_gap_d0_forward_and_post_d0_returns(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    row = rows[0]
    dm1_close = 126.0
    assert float(row["gap_pct"]) == pytest.approx((126.0 / dm1_close - 1) * 100)
    assert float(row["D0_close_return_pct"]) == pytest.approx((127.0 / dm1_close - 1) * 100)
    assert float(row["return_D5"]) == pytest.approx((132.0 / dm1_close - 1) * 100)
    assert float(row["post_D0_to_D5"]) == pytest.approx((132.0 / 127.0 - 1) * 100)


def test_volume_and_range_context_use_twenty_prior_rows(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    row = rows[0]
    assert row["volume_history_sufficient"] == "True"
    assert float(row["avg_volume_Dm20_to_Dm1"]) == pytest.approx(sum(range(1007, 1027)) / 20)
    assert float(row["D0_volume_vs_avg20"]) == pytest.approx(1027 / (sum(range(1007, 1027)) / 20))
    assert row["avg_range_pct_Dm20_to_Dm1"]
    assert row["D0_range_vs_avg20"]


def test_insufficient_history_leaves_context_null(tmp_path: Path) -> None:
    publication = _publication(first_full_post_result_trading_date="2025-01-15")
    _, rows, _, _ = _build(tmp_path, [publication])
    row = rows[0]
    assert row["volume_history_sufficient"] == "False"
    assert row["avg_volume_Dm20_to_Dm1"] == ""
    assert row["avg_range_pct_Dm20_to_Dm1"] == ""


def test_missing_future_d20_preserves_event(tmp_path: Path) -> None:
    publication = _publication(first_full_post_result_trading_date="2025-03-25")
    _, rows, _, _ = _build(tmp_path, [publication], stock_count=62)
    row = rows[0]
    assert row["has_D0"] == "True"
    assert row["has_D20"] == "False"
    assert "D+20" in row["missing_offsets"]
    assert row["return_D20"] == ""
    assert row["event_window_status"] == "PARTIAL"


def test_null_publication_boundary_is_preserved(tmp_path: Path) -> None:
    publication = _publication(first_full_post_result_trading_date="")
    _, rows, _, _ = _build(tmp_path, [publication])
    assert rows[0]["event_window_status"] == "BOUNDARY_UNAVAILABLE"
    assert rows[0]["has_D0"] == "False"


def test_spy_relative_return_uses_same_observed_dates(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    row = rows[0]
    expected_spy = (216.0 / 213.0 - 1) * 100
    expected_stock = (132.0 / 126.0 - 1) * 100
    assert float(row["spy_return_D5"]) == pytest.approx(expected_spy)
    assert float(row["relative_return_D5"]) == pytest.approx(expected_stock - expected_spy)
    assert row["spy_available"] == "True"


def test_event_day_shift_diagnostic(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    row = rows[0]
    assert row["largest_move_day"] == "D0"
    assert float(row["D0_abs_close_move_pct"]) > float(row["D1_abs_close_move_pct"])


def test_summary_groups_status_canonical_method_and_percentiles(tmp_path: Path) -> None:
    _, rows, _, _ = _build(tmp_path, [_publication()])
    parsed = [{key: _coerce(value) for key, value in rows[0].items()}]
    summary = summarize_event_windows(parsed)
    assert summary["groups"]["ALL"]["event_count"] == 1
    assert summary["groups"]["STATUS:EXACT"]["complete_D20_count"] == 1
    assert summary["groups"]["IS_CANONICAL:true"]["distributions"]["return_D5"]["p50"] is not None
    assert summary["groups"]["METHOD:CANONICAL_VERIFIED"]["event_count"] == 1
    assert summary["method_shift_diagnostic"]["CANONICAL_VERIFIED"]["small_sample"] is True


def _coerce(value: str):
    if value == "":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    try:
        return float(value)
    except ValueError:
        return value


def test_publication_hash_mismatch_stops_preflight(tmp_path: Path) -> None:
    publication, metadata = _publication_files(tmp_path, [_publication()])
    publication.write_text(publication.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        validate_publication_input(publication, metadata)


def test_unusable_publication_is_rejected(tmp_path: Path) -> None:
    publication, metadata = _publication_files(
        tmp_path, [_publication(research_status="UNUSABLE")]
    )
    with pytest.raises(ValueError, match="STATUS_REJECTED"):
        validate_publication_input(publication, metadata)


def test_duplicate_event_identity_is_rejected(tmp_path: Path) -> None:
    publication, metadata = _publication_files(tmp_path, [_publication(), _publication()])
    with pytest.raises(ValueError, match="DUPLICATE_QUARTER"):
        validate_publication_input(publication, metadata)


def test_output_is_deterministic_and_retains_provenance(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    _, first_rows, first_output, _ = _build(first_dir, [_publication(warning="Research only")])
    _, second_rows, second_output, _ = _build(second_dir, [_publication(warning="Research only")])
    assert first_output.read_bytes() == second_output.read_bytes()
    assert first_rows[0]["research_confidence"] == "EXACT"
    assert first_rows[0]["canonical_authority_status"] == "VERIFIED"
    assert first_rows[0]["warning"] == "Research only"
    assert tuple(first_rows[0]) == EVENT_WINDOW_COLUMNS
