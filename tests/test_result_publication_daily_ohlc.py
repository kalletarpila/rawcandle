from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication_research_export import EXPORT_COLUMNS
from rawcandle.research.result_publication_daily_ohlc import ResultPublicationResearchDataset


def _row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in EXPORT_COLUMNS}
    row.update(
        {
            "company_id": "7",
            "ticker": "AAPL",
            "fiscal_year": "2026",
            "fiscal_quarter": "Q3",
            "research_status": "EXACT",
            "research_confidence": "EXACT",
            "research_method": "CANONICAL_VERIFIED",
            "first_full_post_result_trading_date": "2026-07-31",
            "canonical_authority_status": "VERIFIED",
            "is_canonical": "True",
            "rule_version": "result_publication_daily_research_v1",
        }
    )
    row.update(overrides)
    return row


def _csv(path: Path, rows: list[dict[str, str]], columns: tuple[str, ...] = EXPORT_COLUMNS) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _ohlc(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE osakedata (id INTEGER PRIMARY KEY, osake TEXT, pvm TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume INTEGER)"
    )
    connection.executemany(
        "INSERT INTO osakedata(osake,pvm,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [
            ("AAPL", "2026-07-30", 1, 2, 0.5, 1.5, 10),
            ("AAPL", "2026-07-31", 2, 3, 1.5, 2.5, 20),
            ("AAPL", "2026-08-03", 3, 4, 2.5, 3.5, 30),
        ],
    )
    connection.commit()
    connection.close()
    return path


def test_retained_style_csv_parsing_and_exact_lookup(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", [_row()]))
    result = dataset.require(7, 2026, "Q3")
    assert len(dataset) == 1
    assert result.research_status == "EXACT"
    assert result.first_full_post_result_trading_date == "2026-07-31"


def test_high_lookup_preserves_provenance(tmp_path: Path) -> None:
    row = _row(
        company_id="13",
        ticker="ABG",
        fiscal_year="2025",
        fiscal_quarter="Q1",
        research_status="HEURISTIC_HIGH",
        research_confidence="HIGH",
        research_method="YAHOO_NEAR_UNIQUE_SEC",
        is_canonical="False",
        warning="Research only",
    )
    result = ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", [row])).require(
        13, 2025, "Q1"
    )
    assert (result.research_method, result.is_canonical, result.rule_version, result.warning) == (
        "YAHOO_NEAR_UNIQUE_SEC",
        False,
        "result_publication_daily_research_v1",
        "Research only",
    )


def test_unusable_is_defensively_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RESEARCH_EXPORT_STATUS_REJECTED"):
        ResultPublicationResearchDataset.load(
            _csv(tmp_path / "research.csv", [_row(research_status="UNUSABLE")])
        )


def test_missing_quarter_has_optional_and_required_lookups(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", [_row()]))
    assert dataset.get(7, 2025, "Q4") is None
    with pytest.raises(KeyError, match="RESEARCH_QUARTER_NOT_FOUND"):
        dataset.require(7, 2025, "Q4")


def test_duplicate_quarter_identity_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RESEARCH_EXPORT_DUPLICATE_QUARTER"):
        ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", [_row(), _row()]))


def test_event_boundary_joins_exact_ohlc_date(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", [_row()]))
    window = dataset.get_ohlc_window(_ohlc(tmp_path / "ohlc.db"), 7, 2026, "Q3")
    assert window.availability == "AVAILABLE"
    assert window.previous_day.trading_date == "2026-07-30"
    assert window.boundary_day.trading_date == "2026-07-31"
    assert window.next_day.trading_date == "2026-08-03"


def test_future_boundary_is_pending_without_fallback(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(
        _csv(tmp_path / "research.csv", [_row(first_full_post_result_trading_date="2026-08-04")])
    )
    window = dataset.get_ohlc_window(_ohlc(tmp_path / "ohlc.db"), 7, 2026, "Q3")
    assert window.availability == "PENDING_OHLC"
    assert window.boundary_day is None


def test_missing_historical_boundary_is_not_reinterpreted(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(
        _csv(tmp_path / "research.csv", [_row(first_full_post_result_trading_date="2026-07-29")])
    )
    with pytest.raises(ValueError, match="BOUNDARY_NOT_IN_OHLC_CALENDAR"):
        dataset.get_ohlc_window(_ohlc(tmp_path / "ohlc.db"), 7, 2026, "Q3")


def test_null_boundary_is_preserved(tmp_path: Path) -> None:
    dataset = ResultPublicationResearchDataset.load(
        _csv(tmp_path / "research.csv", [_row(first_full_post_result_trading_date="")])
    )
    window = dataset.get_ohlc_window(_ohlc(tmp_path / "ohlc.db"), 7, 2026, "Q3")
    assert window.availability == "BOUNDARY_UNAVAILABLE"


def test_loader_is_deterministic_and_has_no_write_api(tmp_path: Path) -> None:
    source = _csv(tmp_path / "research.csv", [_row()])
    first = ResultPublicationResearchDataset.load(source)
    second = ResultPublicationResearchDataset.load(source)
    assert first.require(7, 2026, "Q3") == second.require(7, 2026, "Q3")
    assert not any(hasattr(first, name) for name in ("save", "insert", "update", "delete"))


@pytest.mark.parametrize(
    ("rows", "columns", "message"),
    [
        ([_row()], tuple(column for column in EXPORT_COLUMNS if column != "warning"), "COLUMNS_INVALID"),
        ([_row(is_canonical="yes")], EXPORT_COLUMNS, "CANONICAL_FLAG_INVALID"),
        ([_row(first_full_post_result_trading_date="not-a-date")], EXPORT_COLUMNS, "BOUNDARY_INVALID"),
        ([_row(research_method="")], EXPORT_COLUMNS, "PROVENANCE_INVALID"),
    ],
)
def test_malformed_export_is_rejected(
    tmp_path: Path, rows: list[dict[str, str]], columns: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ResultPublicationResearchDataset.load(_csv(tmp_path / "research.csv", rows, columns))
