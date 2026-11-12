"""Carry accepted ticker state between inactive copies; never repair its lineage."""

from __future__ import annotations

from contextlib import closing
from datetime import date
import math
from pathlib import Path
import sqlite3

from .publication_journal import sha256_file, sqlite_verification
from rawcandle.fundamentals.generations import resolve_active_generation

HOLD = "LOCAL_BASELINE_INTEGRITY_HOLD"
REASON = "ACCEPTED_BASELINE_PROVENANCE_INCOMPLETE"
TABLES = (
    "v4_quarter",
    "v4_quarter_financials",
    "v4_field_provenance",
    "v4_common_earnings_provenance",
    "v4_operating_working_capital_provenance",
    "v4_parent_equity_source",
    "v4_parent_equity_provenance",
)


def readonly(path):
    c = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def verified_generation(paths):
    """One operation-scoped verification, never a cached substitute for recheck."""
    canonical = paths.canonical_db.resolve()
    if canonical.parent.parent.name != "fundamentals_generations":
        return None  # Legacy flat copies cannot attest a degraded baseline.
    binding = resolve_active_generation(canonical.parents[3], require_generation=True)
    roles = binding.role_paths()
    for role, path in roles.items():
        if path.resolve() != paths.as_dict()[role].resolve():
            raise ValueError("CARRY_FORWARD_ACTIVE_ROLE_BINDING_MISMATCH:" + role)
        verification = sqlite_verification(path)
        if (
            verification["sha256"]
            != binding.manifest["role_verification"][role]["sha256"]
        ):
            raise ValueError("CARRY_FORWARD_ACTIVE_ROLE_HASH_MISMATCH:" + role)
    return {
        "generation_id": binding.generation_id,
        "manifest_sha256": sha256_file(binding.manifest_path),
        "role_hashes": {
            r: binding.manifest["role_verification"][r]["sha256"] for r in roles
        },
    }


def snapshot(db, company, *, validate=False):
    with closing(readonly(db)) as c:
        present = {
            r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        quarters = [
            dict(r)
            for r in c.execute(
                "SELECT * FROM v4_quarter WHERE company_id=?", (company,)
            )
        ]
        numeric = {
            r[1]
            for r in c.execute("PRAGMA table_info(v4_quarter_financials)")
            if r[2].upper() in {"INTEGER", "REAL", "NUMERIC"} and r[1] != "quarter_id"
        }
        result = {"v4_quarter": quarters}
        for table in TABLES[1:]:
            if table in present:
                result[table] = [
                    dict(r)
                    for r in c.execute(
                        f"SELECT t.* FROM {table} t JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=?",
                        (company,),
                    )
                ]
    if validate:
        if not quarters or len(result.get("v4_quarter_financials", [])) != len(
            quarters
        ):
            raise ValueError("CARRY_FORWARD_CANONICAL_BASELINE_MISSING")
        keys = {(q["fiscal_year"], q["fiscal_quarter"]) for q in quarters}
        if len(keys) != len(quarters):
            raise ValueError("CARRY_FORWARD_DUPLICATE_FISCAL_IDENTITY")
        for q in quarters:
            if (
                q["company_id"] != company
                or q["identity_status"] != "ACCEPTED"
                or not isinstance(q["fiscal_year"], int)
                or q["fiscal_year"] <= 0
                or q["fiscal_quarter"] not in {"Q1", "Q2", "Q3", "Q4"}
            ):
                raise ValueError("CARRY_FORWARD_CANONICAL_IDENTITY_INVALID")
            for field in (
                "period_end",
                "source_reportperiod",
                "source_availability_date",
                "first_public_result_date",
            ):
                if q.get(field) is not None:
                    date.fromisoformat(q[field])
            if not q.get("period_end") or not q.get("source_availability_date"):
                raise ValueError("CARRY_FORWARD_CANONICAL_DATE_MISSING")
        for row in result["v4_quarter_financials"]:
            if any(
                row[k] is not None
                and (not isinstance(row[k], (int, float)) or not math.isfinite(row[k]))
                for k in numeric
            ):
                raise ValueError("CARRY_FORWARD_CANONICAL_FINANCIAL_INVALID")
    return result


def baseline_issues(paths, company_ids=None):
    """Check only this operation's companies, including otherwise safe changes.

    Missing lineage must not become new-source acceptance just because a later
    incoming response no longer produces a review-shaped comparison.
    """
    result = {}
    with closing(readonly(paths.canonical_db)) as c:
        c.execute(
            "ATTACH DATABASE ? AS accepted_provider",
            (f"file:{paths.provider_db.resolve()}?mode=ro",),
        )
        tables = {
            r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        ids = sorted(set(company_ids)) if company_ids is not None else None
        batches = (
            [None]
            if ids is None
            else [ids[n : n + 400] for n in range(0, len(ids), 400)]
        )
        for batch in batches:
            restriction = (
                ""
                if batch is None
                else f"q.company_id IN ({','.join('?' for _ in batch)}) AND "
            )
            for table in TABLES[2:]:
                if table not in tables:
                    continue
                fields = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
                field = (
                    "provider_observation_id"
                    if "provider_observation_id" in fields
                    else "observation_id"
                )
                for r in c.execute(
                    f"""SELECT DISTINCT q.company_id,t.{field},p.company_id source_company
                    FROM {table} t JOIN v4_quarter q USING(quarter_id)
                    LEFT JOIN accepted_provider.provider_observation p ON p.observation_id=t.{field}
                    LEFT JOIN accepted_provider.sharadar_fundamental_observation s ON s.observation_id=p.observation_id
                    WHERE {restriction}(p.observation_id IS NULL OR s.observation_id IS NULL OR p.company_id<>q.company_id
                        OR s.dimension<>'ARQ' OR s.reportperiod<>q.source_reportperiod
                        OR s.date<>q.source_availability_date)""",
                    batch or (),
                ):
                    result.setdefault(r[0], []).append(
                        {
                            "table": table,
                            "provider_observation_id": r[1],
                            "cross_company": r[2] is not None and r[2] != r[0],
                        }
                    )
    return result


def degraded_tickers(paths):
    """The full rebuild touches all canonical companies, even outside discovery."""
    companies = baseline_issues(paths)
    names = set()
    with closing(readonly(paths.canonical_db)) as c:
        for company in companies:
            rows = c.execute(
                "SELECT current_ticker FROM security WHERE company_id=?", (company,)
            ).fetchall()
            if not rows:
                raise ValueError(
                    "DEGRADED_BASELINE_IDENTITY_UNISOLATABLE:" + str(company)
                )
            names.update(str(r[0]).strip().upper() for r in rows)
    return sorted(names)


def broken_references(provider_db, state):
    evidence = []
    quarters = {q["quarter_id"]: q for q in state["v4_quarter"]}
    with closing(readonly(provider_db)) as c:
        for table, rows in state.items():
            if table in TABLES[:2]:
                continue
            for row in rows:
                oid = row.get("provider_observation_id") or row.get("observation_id")
                source = (
                    c.execute(
                        "SELECT s.ticker,s.dimension,s.date,s.reportperiod FROM provider_observation p "
                        "JOIN sharadar_fundamental_observation s USING(observation_id) WHERE p.observation_id=?",
                        (oid,),
                    ).fetchone()
                    if oid
                    else None
                )
                q = quarters[row["quarter_id"]]
                if (
                    source is None
                    or source["dimension"] != "ARQ"
                    or source["reportperiod"] != q["source_reportperiod"]
                    or source["date"] != q["source_availability_date"]
                ):
                    evidence.append(
                        {
                            "table": table,
                            "canonical_field": row.get("canonical_field"),
                            "quarter_id": row["quarter_id"],
                            "provider_observation_id": oid,
                            "reason": (
                                "MISSING_PROVIDER_OBSERVATION"
                                if source is None
                                else "STALE_PROVIDER_REFERENCE"
                            ),
                            "source_identity": dict(source) if source else None,
                        }
                    )
    return evidence


def capture(canonical_db, held):
    """Snapshot all held quarters before the normal full canonical rebuild."""
    return {
        int(h["identity_binding"]["company_id"]): snapshot(
            canonical_db, int(h["identity_binding"]["company_id"]), validate=True
        )
        for h in held
    }


def restore(canonical_db, states):
    """Restore stored financial/source semantics, remapping only physical IDs.

    Targets are inactive candidate copies. Missing provider observations remain
    missing and their recorded provenance references are copied verbatim.
    """
    if not states:
        return {"companies": 0, "quarters": 0}
    from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy

    assert_inactive_copy(Path(canonical_db))
    with sqlite3.connect(canonical_db) as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("BEGIN IMMEDIATE")
        count = 0

        def insert(table, row):
            columns = list(row)
            return c.execute(
                f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                [row[k] for k in columns],
            )

        for company, state in states.items():
            c.execute("DELETE FROM v4_quarter WHERE company_id=?", (company,))
            mapping = {}
            for row in state["v4_quarter"]:
                mapping[row["quarter_id"]] = insert(
                    "v4_quarter", {k: v for k, v in row.items() if k != "quarter_id"}
                ).lastrowid
                count += 1
            for table in TABLES[1:]:
                for row in state.get(table, []):
                    insert(
                        table,
                        {
                            k: (mapping[v] if k == "quarter_id" else v)
                            for k, v in row.items()
                            if k != "provenance_id"
                        },
                    )
        c.commit()
    return {
        "companies": len(states),
        "quarters": count,
        "policy": "EXACT_ACTIVE_CANONICAL_CARRY_FORWARD_NO_SOURCE_ACCEPTANCE",
    }
