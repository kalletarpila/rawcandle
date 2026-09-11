from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from . import contract
from .persistence import MODEL_MAP, PACKAGE_FINGERPRINT
from .readers import ParallelModelRepository


ACTIVATION_TABLE = "fundamentals_active_model_family"
PRE_PHASE9G_PACKAGE_FINGERPRINT = "cf4ce8134c362399ea94667e4659e27a32b1e8b9de199eaaba32c91b450a51bc"
TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT = "f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40"
PRE_PHASE9G_MODEL_MAP = {
    **MODEL_MAP,
    "diagnostic_flags": (
        contract.DIAGNOSTIC_MODEL_VERSION,
        "d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d",
    ),
    "snapshot": (
        contract.SNAPSHOT_MODEL_VERSION,
        "7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8",
    ),
}
KNOWN_PACKAGES = {
    PRE_PHASE9G_PACKAGE_FINGERPRINT: PRE_PHASE9G_MODEL_MAP,
    PACKAGE_FINGERPRINT: MODEL_MAP,
}


def known_packages() -> dict[str, dict[str, tuple[str, str]]]:
    from .phase10b import MODEL_MAP as PHASE10B_MODEL_MAP, PACKAGE_FINGERPRINT as PHASE10B_PACKAGE

    return {
        **KNOWN_PACKAGES,
        PHASE10B_PACKAGE: PHASE10B_MODEL_MAP,
        TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT: PHASE10B_MODEL_MAP,
    }
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


def active_model_manifest(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    row = conn.execute(
        f"SELECT model_manifest_json FROM {ACTIVATION_TABLE} WHERE singleton=1"
    ).fetchone()
    if row is None:
        raise LookupError("OPERATING_INCOME_V2_NOT_ACTIVE")
    payload = json.loads(row[0])
    return {name: tuple(identity) for name, identity in payload.items()}


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
    if (active.family_version, active.family_fingerprint) != (
        contract.FAMILY_VERSION, contract.FAMILY_FINGERPRINT,
    ):
        raise ValueError("OPERATING_INCOME_V2_ACTIVE_PACKAGE_MISMATCH")
    manifest = active_model_manifest(conn)
    expected_manifest = known_packages().get(active.persistence_fingerprint)
    if manifest != expected_manifest:
        raise ValueError("OPERATING_INCOME_V2_ACTIVE_PACKAGE_MISMATCH")
    package = ParallelModelRepository(conn).package_manifest(active.persistence_fingerprint)
    current_package = ParallelModelRepository(conn).package_manifest()
    if current_package["persistence_fingerprint"] != active.persistence_fingerprint:
        raise ValueError("OPERATING_INCOME_V2_ACTIVE_PACKAGE_CONTENT_REPLACED")
    if (
        package["persistence_fingerprint"] != active.persistence_fingerprint
        or json.loads(package["model_manifest_json"])
        != {name: list(identity) for name, identity in manifest.items()}
    ):
        raise ValueError("OPERATING_INCOME_V2_ACTIVE_PACKAGE_MISMATCH")
    ParallelModelRepository(conn).assert_v2_bundle(
        manifest, persistence_fingerprint=active.persistence_fingerprint
    )
    return active


def activate_v2(conn: sqlite3.Connection, *, activated_at: str) -> ActiveFamily:
    return activate_package(conn, PACKAGE_FINGERPRINT, activated_at=activated_at)


def activate_package(
    conn: sqlite3.Connection,
    package_fingerprint: str,
    *,
    activated_at: str,
) -> ActiveFamily:
    packages = known_packages()
    if package_fingerprint not in packages:
        raise ValueError("OPERATING_INCOME_V2_UNKNOWN_PACKAGE")
    repository = ParallelModelRepository(conn)
    current_manifest = repository.package_manifest()
    if current_manifest["persistence_fingerprint"] != package_fingerprint:
        raise RuntimeError("OPERATING_INCOME_V2_ARCHIVED_MANIFEST_NOT_ACTIVATABLE")
    model_map = packages[package_fingerprint]
    repository.assert_v2_bundle(
        model_map, persistence_fingerprint=package_fingerprint
    )
    manifest = repository.package_manifest(package_fingerprint)
    if manifest["status"] != "COMPLETE":
        raise RuntimeError("OPERATING_INCOME_V2_PACKAGE_INCOMPLETE")
    current = active_family(conn)
    if current is not None and current.persistence_fingerprint == package_fingerprint:
        return assert_v2_active(conn)
    ensure_activation_schema(conn)
    conn.execute(
        f"INSERT OR REPLACE INTO {ACTIVATION_TABLE} VALUES(1,?,?,?,?,?)",
        (
            contract.FAMILY_VERSION,
            contract.FAMILY_FINGERPRINT,
            package_fingerprint,
            json.dumps(model_map, sort_keys=True, separators=(",", ":")),
            activated_at,
        ),
    )
    return assert_v2_active(conn)


def deactivate_v2(conn: sqlite3.Connection) -> None:
    ensure_activation_schema(conn)
    conn.execute(f"DELETE FROM {ACTIVATION_TABLE} WHERE singleton=1")
