from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.research.phase13a1_taxonomy_update import (
    connect_ro,
    stable_hash,
    taxonomy_change_classification_contract,
    taxonomy_ui_status_contract,
    write_csv,
    write_json,
)


def test_taxonomy_contract_separates_presentation_and_economic_changes() -> None:
    contract = taxonomy_change_classification_contract()
    assert "PRESENTATION_ONLY" in contract["impact_classes"]
    assert "PEER_GROUP_CHANGE" in contract["impact_classes"]
    assert "ACCOUNTING_APPLICABILITY_CHANGE" in contract["impact_classes"]
    assert contract["identity_key"].startswith("stable company_id/security_id")


def test_taxonomy_ui_status_contract_has_safe_apply_guards() -> None:
    contract = taxonomy_ui_status_contract()
    assert "ECONOMIC_CHANGES_REQUIRE_REBUILD" in contract["statuses"]
    assert "FAILED_ROLLED_BACK" in contract["statuses"]
    assert any("source changed" in item for item in contract["apply_rejects_if"])
    assert "raw SQL" in contract["browser_must_not_receive"]


def test_machine_outputs_are_deterministic_and_parseable(tmp_path: Path) -> None:
    payload = {"z": [2, 1], "a": "taxonomy"}
    write_json(tmp_path / "a.json", payload)
    write_json(tmp_path / "b.json", payload)
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == payload
    write_csv(tmp_path / "a.csv", [{"b": 2, "a": 1}, {"a": 0, "b": 3}])
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
