from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.relative_valuation.candidate_snapshot import (
    CANDIDATE_REPORT_CONTRACT,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths,
    _bars,
    _validate_paths,
)


AS_OF_DATE = "2026-09-08"


def test_candidate_module_can_be_imported_directly() -> None:
    assert CANDIDATE_REPORT_CONTRACT.endswith("RELATIVE_VALUATION_CANDIDATE")


def test_source_paths_must_be_distinct_regular_files(tmp_path: Path) -> None:
    files = []
    for name in ("a.db", "b.db", "c.db", "d.db"):
        path = tmp_path / name
        sqlite3.connect(path).close()
        files.append(path)
    _validate_paths(ReadOnlySourcePaths(*files))
    with pytest.raises(ValueError, match="MUST_BE_DISTINCT"):
        _validate_paths(ReadOnlySourcePaths(files[0], files[0], files[2], files[3]))
    alias = tmp_path / "alias.db"
    alias.symlink_to(files[0])
    with pytest.raises(FileNotFoundError):
        _validate_paths(ReadOnlySourcePaths(alias, files[1], files[2], files[3]))


def test_market_bar_adapter_prefers_exact_ticker_and_never_reads_future(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE osakedata(osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL)"
        )
        connection.executemany(
            "INSERT INTO osakedata VALUES(?,?,?,?,?,?)",
            (
                ("Abc", "2026-09-07", 1.0, 1.0, 1.0, 1.0),
                ("ABC", "2026-09-08", 2.0, 2.0, 2.0, 2.0),
                ("ABC", "2026-09-09", 3.0, 3.0, 3.0, 3.0),
            ),
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        bars = _bars(connection, "ABC", AS_OF_DATE)
    finally:
        connection.close()
    assert [(bar.price_date, bar.close) for bar in bars] == [("2026-09-08", 2.0)]
