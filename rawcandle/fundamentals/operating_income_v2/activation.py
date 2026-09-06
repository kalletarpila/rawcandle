from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from . import contract
from .persistence import MODEL_MAP, PACKAGE_FINGERPRINT
from .readers import ParallelModelRepository


ACTIVATION_TABLE = "fundamentals_active_model_family"
ACTIVATION_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {ACTIVATION_TABLE}(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 family_version TEXT NOT NULL,
 family_fingerprint TEXT NOT NULL,
 persistence_fingerprint TEXT NOT NULL,
 model_manifest_json TEXT NOT NULL,
 activated_at_utc TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class ActiveFamily:
    family_version: str
    family_fingerprint: str
    persistence_fingerprint: str
    activated_at_utc: str


def ensure_activation_schema(conn: sqlite3.Connection) -> None:
    conn.execute(ACTIVATION_SCHEMA)


def active_family(conn: sqlite3.Connection) -> ActiveFamily | None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",
        (ACTIVATION_TABLE,),
    ).fetchone()
    if not exists:
        return None
    row = conn.execute(
        f"SELECT family_version,family_fingerprint,persistence_fingerprint,activated_at_utc "
        f"FROM {ACTIVATION_TABLE} WHERE singleton=1"
    ).fetchone()
    return ActiveFamily(*row) if row else None


def assert_v2_active(conn: sqlite3.Connection) -> ActiveFamily:
    active = active_family(conn)
    if active is None:
        raise LookupError("OPERATING_INCOME_V2_NOT_ACTIVE")
    expected = (contract.FAMILY_VERSION, contract.FAMILY_FINGERPRINT, PACKAGE_FINGERPRINT)
    observed = (active.family_version, active.family_fingerprint, active.persistence_fingerprint)
    if observed != expected:
        raise ValueError("OPERATING_INCOME_V2_ACTIVE_PACKAGE_MISMATCH")
    ParallelModelRepository(conn).assert_v2_bundle()
    return active


def activate_v2(conn: sqlite3.Connection, *, activated_at: str) -> ActiveFamily:
    repository = ParallelModelRepository(conn)
    repository.assert_v2_bundle()
    manifest = repository.package_manifest()
    if manifest["status"] != "COMPLETE":
        raise RuntimeError("OPERATING_INCOME_V2_PACKAGE_INCOMPLETE")
    ensure_activation_schema(conn)
    conn.execute(
        f"INSERT OR REPLACE INTO {ACTIVATION_TABLE} VALUES(1,?,?,?,?,?)",
        (
            contract.FAMILY_VERSION,
            contract.FAMILY_FINGERPRINT,
            PACKAGE_FINGERPRINT,
            json.dumps(MODEL_MAP, sort_keys=True, separators=(",", ":")),
            activated_at,
        ),
    )
    return assert_v2_active(conn)


def deactivate_v2(conn: sqlite3.Connection) -> None:
    ensure_activation_schema(conn)
    conn.execute(f"DELETE FROM {ACTIVATION_TABLE} WHERE singleton=1")
