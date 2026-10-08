"""Generation-local, explicit opt-in to quarterly ownership reporting.

No configuration means V1. Reading a report never creates schema or writes DBs.
Activation is permitted only on an inactive, unpublished canonical copy.
"""
from datetime import date
from pathlib import Path
import sqlite3

from rawcandle.fundamentals.ownership_basis import (
    OWNERSHIP_CONTRACT, QUARTERLY_OWNERSHIP_CONTRACT, ownership_reviews_v2_hash,
)
from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy

TABLE = 'v4_pb_reporting_contract'
V2_NOT_BEFORE = '2026-10-08'


def activate_quarterly_ownership(canonical_db: Path, *, effective_from: str) -> None:
    """Prepare a candidate; publication remains the existing generation workflow."""
    date.fromisoformat(effective_from)
    if effective_from < V2_NOT_BEFORE:
        raise ValueError('QUARTERLY_OWNERSHIP_ACTIVATION_TOO_EARLY')
    assert_inactive_copy(canonical_db)
    with sqlite3.connect(canonical_db) as conn:
        conn.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            ownership_contract TEXT NOT NULL, effective_from TEXT NOT NULL,
            review_artifact_sha256 TEXT NOT NULL)''')
        desired = (1, QUARTERLY_OWNERSHIP_CONTRACT, effective_from, ownership_reviews_v2_hash())
        existing = conn.execute(f'SELECT * FROM {TABLE}').fetchall()
        if existing and existing != [desired]:
            raise ValueError('QUARTERLY_OWNERSHIP_ACTIVATION_CONFLICT')
        conn.execute(f'INSERT OR IGNORE INTO {TABLE} VALUES(?,?,?,?)', desired)


def repin_quarterly_reviews(canonical_db: Path, *, expected_artifact_sha256: str) -> None:
    """Explicitly bind a candidate to an operator-reviewed registry revision.

    This does not create or approve evidence. The caller must first review and
    commit new observation-bound records; refresh never invokes this helper.
    """
    assert_inactive_copy(canonical_db)
    with sqlite3.connect(canonical_db) as conn:
        rows = conn.execute(f'SELECT singleton,ownership_contract,effective_from,review_artifact_sha256 FROM {TABLE}').fetchall()
        if (len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != QUARTERLY_OWNERSHIP_CONTRACT
            or date.fromisoformat(rows[0][2]) < date.fromisoformat(V2_NOT_BEFORE)
            or rows[0][3] != expected_artifact_sha256):
            raise ValueError('QUARTERLY_OWNERSHIP_REPIN_CONFLICT')
        conn.execute(f'UPDATE {TABLE} SET review_artifact_sha256=? WHERE singleton=1', (ownership_reviews_v2_hash(),))


def reporting_ownership_contract(conn: sqlite3.Connection, *, as_of: str) -> str:
    date.fromisoformat(as_of)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
        return OWNERSHIP_CONTRACT
    rows = conn.execute(f'SELECT singleton,ownership_contract,effective_from,review_artifact_sha256 FROM {TABLE}').fetchall()
    if len(rows) != 1:
        raise ValueError('QUARTERLY_OWNERSHIP_CONFIG_INVALID')
    singleton, contract, activated, artifact_hash = rows[0]
    if singleton != 1 or contract != QUARTERLY_OWNERSHIP_CONTRACT or date.fromisoformat(activated) < date.fromisoformat(V2_NOT_BEFORE):
        raise ValueError('QUARTERLY_OWNERSHIP_CONFIG_INVALID')
    # Historical V1 is independent of subsequent V2 registry revisions.
    if as_of < activated:
        return OWNERSHIP_CONTRACT
    if artifact_hash != ownership_reviews_v2_hash():
        raise ValueError('QUARTERLY_OWNERSHIP_ARTIFACT_MISMATCH')
    return contract
