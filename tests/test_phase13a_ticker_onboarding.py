from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.research.phase13a_ticker_onboarding import (
    REQUIRED_STATUSES,
    connect_ro,
    normalize_ticker_batch,
    preview_status_contract,
    stable_hash,
    write_csv,
    write_json,
)


def test_batch_normalization_keeps_first_order_and_dedupes() -> None:
    result = normalize_ticker_batch(" aapl,msft\nAAPL  brk.b invalid* ")
    assert result["normalized"] == ["AAPL", "MSFT", "BRK.B"]
    assert result["duplicates_removed"] == ["AAPL"]
    assert result["invalid_tokens"] == ["INVALID*"]
    assert result["within_limit"] is True


def test_batch_limit_is_enforced_without_reordering() -> None:
    payload = " ".join(f"T{i}" for i in range(26))
    result = normalize_ticker_batch(payload)
    assert len(result["normalized"]) == 26
    assert result["within_limit"] is False
    assert result["normalized"][0] == "T0"
    assert result["normalized"][-1] == "T25"


def test_preview_contract_contains_required_statuses_and_forbidden_payloads() -> None:
    contract = preview_status_contract()
    assert set(REQUIRED_STATUSES).issubset(contract["statuses"])
    forbidden = " ".join(contract["browser_must_never_receive"]).lower()
    assert "api keys" in forbidden
    assert "raw exception traces" in forbidden


def test_json_csv_outputs_are_deterministic_and_parseable(tmp_path: Path) -> None:
    payload = {"b": [2, 1], "a": "x"}
    write_json(tmp_path / "a.json", payload)
    write_json(tmp_path / "b.json", payload)
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == payload
    write_csv(tmp_path / "a.csv", [{"b": 2, "a": 1}, {"a": 0, "b": 3}])
    write_csv(tmp_path / "b.csv", [{"a": 0, "b": 3}, {"b": 2, "a": 1}])
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    with (tmp_path / "a.csv").open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 2
    assert len(stable_hash(payload)) == 64


def test_readonly_connection_blocks_writes(tmp_path: Path) -> None:
    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(value TEXT)")
    with connect_ro(database) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("INSERT INTO evidence VALUES('changed')")
