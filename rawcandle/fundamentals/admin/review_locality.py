"""Evidence-bound quarantine, separate from authority to approve incoming data.

Proofs are built from read-only published authorities and validated acquisition
results, and bound to immutable snapshot evidence. No ticker exceptions.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Mapping

from .provider_payload import payload_fingerprint as digest

VERSION = "FUNDAMENTALS_WHOLE_TICKER_QUARANTINE_V4_SNAPSHOT"
RETENTION_VERSION = "REVIEWED_NEW_COMPANY_OLD_RETENTION_V1"
DIMENSIONS = {"ARQ", "MRQ"}
IDENTITY = (
    "ticker",
    "company_id",
    "security_id",
    "provider_security_id",
    "company_key",
    "current_ticker",
    "provider_ticker",
)


def _ro(path):
    c = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def _ordered(rows):
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))


def authority(
    provider_db,
    canonical_db,
    ticker,
    identity,
    *,
    validate=False,
    allow_missing_provider=False,
    retention_proof=None,
):
    """Exact provider + economic canonical identity, independent of physical IDs.

    All financial columns and provenance semantics are included. Only rebuilt
    canonical physical IDs and write timestamps are omitted. Provider headers,
    capture receipts and payloads remain exact. Optional tables stay optional.
    """
    if retention_proof is not None:
        if validate or not allow_missing_provider:
            raise ValueError("RETENTION_PROOF_IS_NOT_INCOMING_AUTHORITY")
        _check_retention_proof(
            provider_db, canonical_db, ticker, identity, retention_proof
        )
    company = identity["company_id"]
    with closing(_ro(provider_db)) as p, closing(_ro(canonical_db)) as c:
        provider = [
            dict(r)
            for r in p.execute(
                "SELECT po.*,s.* FROM provider_observation po JOIN sharadar_fundamental_observation s "
                "USING(observation_id) WHERE s.ticker=? AND s.dimension IN ('ARQ','MRQ')",
                (ticker,),
            )
        ]
        quarters = [
            dict(r)
            for r in c.execute(
                "SELECT q.*,f.* FROM v4_quarter q JOIN v4_quarter_financials f USING(quarter_id) "
                "WHERE q.company_id=?",
                (company,),
            )
        ]
        if (not provider and not allow_missing_provider) or not quarters:
            raise ValueError("QUARANTINE_ACCEPTED_BASELINE_MISSING")
        if any(
            r["company_id"] != company
            or r["security_id"] != identity["security_id"]
            or (
                r["provider_security_id"] is not None
                and str(r["provider_security_id"])
                != str(identity["provider_security_id"])
            )
            or r["provider"] != "SHARADAR"
            or r["native_table"] != "fundamentals"
            for r in provider
        ):
            raise ValueError("QUARANTINE_PROVIDER_IDENTITY_AMBIGUOUS")
        sources = {r["observation_id"]: r for r in provider}
        tables = {
            r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        provenance = []
        for table in (
            "v4_field_provenance",
            "v4_common_earnings_provenance",
            "v4_operating_working_capital_provenance",
            "v4_parent_equity_source",
            "v4_parent_equity_provenance",
        ):
            if table not in tables:
                continue
            for q in quarters:
                for r in c.execute(
                    f"SELECT * FROM {table} WHERE quarter_id=?", (q["quarter_id"],)
                ):
                    row = dict(r)
                    if (
                        validate
                        and (
                            row.get("provider_observation_id")
                            or row.get("observation_id")
                        )
                        not in sources
                    ):
                        raise ValueError("QUARANTINE_ACCEPTED_SOURCE_UNBOUND")
                    provenance.append(
                        {
                            "table": table,
                            "quarter": [company, q["fiscal_year"], q["fiscal_quarter"]],
                            **{
                                k: v
                                for k, v in row.items()
                                if k
                                not in {
                                    "quarter_id",
                                    "provenance_id",
                                    "created_at_utc",
                                    "updated_at_utc",
                                    "accepted_at_utc",
                                }
                            },
                        }
                    )
        if validate:
            from rawcandle.fundamentals.schema.contract import (
                SHARADAR_ARQ_FIELD_MAPPING,
            )

            for q in quarters:
                ids = {
                    r.get("provider_observation_id") or r.get("observation_id")
                    for r in provenance
                    if r["quarter"] == [company, q["fiscal_year"], q["fiscal_quarter"]]
                }
                fields = {
                    r.get("canonical_field")
                    for r in provenance
                    if r["quarter"] == [company, q["fiscal_year"], q["fiscal_quarter"]]
                }
                if q["identity_status"] != "ACCEPTED" or len(ids) != 1:
                    raise ValueError("QUARANTINE_ACCEPTED_SOURCE_AMBIGUOUS")
                if any(
                    q[k] is not None and k not in fields
                    for k in SHARADAR_ARQ_FIELD_MAPPING
                ):
                    raise ValueError("QUARANTINE_ACCEPTED_PROVENANCE_INCOMPLETE")
                s = sources[next(iter(ids))]
                # Reviewed accounting-boundary labels are not inferred here.
                if (
                    s["dimension"] != "ARQ"
                    or s["reportperiod"] != q["source_reportperiod"]
                    or s["date"] != q["source_availability_date"]
                    or s["fiscalperiod"] != q["source_fiscalperiod"]
                    or any(q[k] != s[v] for k, v in SHARADAR_ARQ_FIELD_MAPPING.items())
                ):
                    raise ValueError("QUARANTINE_ACCEPTED_SOURCE_CONTRADICTION")
                from rawcandle.fundamentals.schema.parent_equity import finite

                raw = json.loads(s["payload_json"])
                for field, native in (
                    ("parent_equity", "equity"),
                    ("parent_equity_usd", "equityusd"),
                ):
                    if field in q and q[field] != (
                        finite(raw.get(native))
                        if s.get("sharesbas") is not None
                        else None
                    ):
                        raise ValueError("QUARANTINE_ACCEPTED_EQUITY_CONTRADICTION")
        economic = [
            {
                k: v
                for k, v in q.items()
                if k not in {"quarter_id", "created_at_utc", "updated_at_utc"}
            }
            for q in quarters
        ]
        identity_rows = {}
        for table, where, args in (
            ("company", "company_id=?", (company,)),
            ("security", "company_id=?", (company,)),
            ("provider_security_identity", "security_id=?", (identity["security_id"],)),
        ):
            identity_rows[table] = [
                dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE {where}", args)
            ]
        # Legacy accepted headers can lack provider_security_id. Bind their
        # non-null company/security IDs through the exact canonical provider map;
        # never manufacture or rewrite the old header to fill that absence.
        mapping = [
            r
            for r in identity_rows["provider_security_identity"]
            if r["provider"] == "SHARADAR"
        ]
        if retention_proof is None and (
            len(mapping) != 1
            or str(mapping[0]["provider_security_id"])
            != str(identity["provider_security_id"])
            or str(mapping[0]["provider_ticker"]).upper() != ticker
        ):
            raise ValueError("QUARANTINE_CANONICAL_PROVIDER_MAPPING_AMBIGUOUS")
    return {
        "provider": digest(_ordered(provider)),
        "canonical": digest(
            {
                "quarters": _ordered(economic),
                "provenance": _ordered(provenance),
                "identity": identity_rows,
            }
        ),
        "quarter_count": len(quarters),
        "provider_count": len(provider),
    }


def _reviewed_retention_owner(provider_db, canonical_db, ticker, identity):
    """Read an already admitted new-company identity, never replay its mutation."""
    from . import identity_resolution as identities
    from .publication_journal import sha256_file

    registry = identities.DEFAULT_REGISTRY_PATH
    record = identities.load_review_registry(registry).get(ticker)
    approved = (record or {}).get("approved_resolution") or {}
    if (
        not record
        or record.get("review_status") != "APPROVED"
        or approved.get("subject_ticker") != ticker
        or record.get("approval_fingerprint")
        != identities.approval_fingerprint(approved)
        or approved.get("resolution_class")
        not in {
            "BUSINESS_COMBINATION_NEW_SECURITY",
            "REORGANIZATION_SUCCESSOR",
            "NEW_SECURITY",
        }
        or approved.get("security_continuity") != "NEW_SECURITY"
        or approved.get("company_continuity")
        not in {"NEW_PUBLIC_ISSUER", "SUCCESSOR_COMPANY"}
        or approved.get("canonical_company_id") is not None
        or approved.get("canonical_security_id") is not None
        or approved.get("provider_permaticker") is not None
        or approved.get("provider_continuity") != "PROVIDER_METADATA_ABSENT"
        or not approved.get("cik")
        or not approved.get("effective_date")
    ):
        raise ValueError("OLD_RETENTION_APPROVED_NEW_COMPANY_REQUIRED")
    company, security = identity["company_id"], identity["security_id"]
    if identity.get("provider_security_id") is not None:
        raise ValueError("OLD_RETENTION_NULL_PROVIDER_ID_REQUIRED")
    with closing(_ro(canonical_db)) as c, closing(_ro(provider_db)) as p:
        owner = c.execute(
            "SELECT * FROM company WHERE company_id=?", (company,)
        ).fetchone()
        securities = [
            dict(r)
            for r in c.execute("SELECT * FROM security WHERE company_id=?", (company,))
        ]
        ciks = {
            r[0]
            for r in c.execute(
                "SELECT cik_normalized FROM company_cik WHERE company_id=? AND status='ACTIVE'",
                (company,),
            )
        }
        mapping = c.execute(
            "SELECT 1 FROM provider_security_identity WHERE security_id=? AND provider='SHARADAR'",
            (security,),
        ).fetchone()
        metadata = p.execute(
            "SELECT 1 FROM sharadar_ticker_metadata WHERE table_name='fundamentals' AND UPPER(ticker)=?",
            (ticker,),
        ).fetchone()
        # Missing legacy lineage stays missing; a linked foreign owner is a
        # shared integrity failure, never a historical retention exception.
        for table in (
            "v4_field_provenance",
            "v4_common_earnings_provenance",
            "v4_operating_working_capital_provenance",
            "v4_parent_equity_source",
            "v4_parent_equity_provenance",
        ):
            if not c.execute(
                "SELECT 1 FROM sqlite_schema WHERE name=?", (table,)
            ).fetchone():
                continue
            for r in c.execute(
                f"SELECT t.* FROM {table} t JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=?",
                (company,),
            ):
                row = dict(r)
                oid = row.get("provider_observation_id") or row.get("observation_id")
                source = (
                    p.execute(
                        "SELECT company_id,security_id FROM provider_observation WHERE observation_id=?",
                        (oid,),
                    ).fetchone()
                    if oid
                    else None
                )
                if source is not None and tuple(source) != (company, security):
                    raise ValueError("OLD_RETENTION_CROSS_OWNER_PROVENANCE")
    cik = identities.normalize_cik(approved["cik"])
    if (
        not cik
        or owner is None
        or owner["company_key"] != "SEC_CIK:" + cik
        or ciks != {cik}
        or len(securities) != 1
        or securities[0]["security_id"] != security
        or securities[0]["current_ticker"] != ticker
        or securities[0]["valid_from"] != approved["effective_date"]
        or securities[0]["exchange"] != approved["exchange"]
        or mapping is not None
        or metadata is not None
    ):
        raise ValueError("OLD_RETENTION_REVIEWED_OWNER_MISMATCH")
    return dict(
        company_id=company,
        security_id=security,
        ticker=ticker,
        company_key=owner["company_key"],
        security=securities[0],
        approval_fingerprint=record["approval_fingerprint"],
        registry_sha256=sha256_file(registry),
    )


def _retained_provider_digest(provider_db, ticker, identity):
    from .batch_add_tickers import CONTRACT_VERSION as admission_contract

    with closing(_ro(provider_db)) as p:
        rows = [
            dict(r)
            for r in p.execute(
                "SELECT po.*,s.* FROM provider_observation po JOIN sharadar_fundamental_observation s USING(observation_id) WHERE s.ticker=?",
                (ticker,),
            )
        ]
        if not rows or not DIMENSIONS <= {r["dimension"] for r in rows}:
            raise ValueError("OLD_RETENTION_SOURCE_MISSING")
        for r in rows:
            if (
                r["company_id"] != identity["company_id"]
                or r["security_id"] != identity["security_id"]
                or r["provider_security_id"] is not None
                or r["provider"] != "SHARADAR"
                or r["native_table"] != "fundamentals"
                or r["provider_ticker"] != ticker
                or json.loads(r["payload_json"]).get("permaticker") not in (None, "")
            ):
                raise ValueError("OLD_RETENTION_SOURCE_OWNER_MISMATCH")
        for run_id in {r["run_id"] for r in rows}:
            run = p.execute(
                "SELECT * FROM provider_run WHERE run_id=?", (run_id,)
            ).fetchone()
            if (
                run is None
                or run["provider"] != "SHARADAR"
                or run["status"] != "SUCCESS"
                or run["request_scope"] != "PHASE13G2_GENERIC_BATCH_ADD_TICKERS"
                or run["source_version"] != admission_contract
                or ticker not in json.loads(run["metadata_json"]).get("tickers", [])
            ):
                raise ValueError("OLD_RETENTION_ACCEPTED_ADMISSION_SOURCE_REQUIRED")
    return digest(_ordered(rows))


def historical_retention_proof(paths, ticker, identity):
    """Use existing reviewed admission + immutable OLD for retention only.

    The pre-admission expected state is not replayed as current mutation
    permission. No provider ID is inferred, and incoming identity resolution
    still requires its ordinary native mapping and installed membership.
    """
    from . import baseline_carry_forward as carry

    generation = carry.verified_generation(paths)
    if generation is None:
        raise ValueError("OLD_RETENTION_VERIFIED_GENERATION_REQUIRED")
    proof = dict(
        contract=RETENTION_VERSION,
        generation=generation,
        identity=dict(identity),
        owner=_reviewed_retention_owner(
            paths.provider_db, paths.canonical_db, ticker, identity
        ),
        provider_digest=_retained_provider_digest(paths.provider_db, ticker, identity),
    )
    return {**proof, "fingerprint": digest(proof)}


def _check_retention_proof(provider, canonical, ticker, identity, proof):
    if (
        proof.get("contract") != RETENTION_VERSION
        or proof.get("identity") != identity
        or proof.get("fingerprint")
        != digest({k: v for k, v in proof.items() if k != "fingerprint"})
        or proof.get("owner")
        != _reviewed_retention_owner(provider, canonical, ticker, identity)
        or proof.get("provider_digest")
        != _retained_provider_digest(provider, ticker, identity)
    ):
        raise ValueError("OLD_RETENTION_PROOF_MISMATCH")


def verify_retained(paths, provider, canonical, retained, *, old_authority):
    """Compare OLD to candidate with no incoming admission/approval authority."""
    ordinary = [r for r in retained if not r.get("retention_proof")]
    proof = verify_held(paths, provider, canonical, ordinary)
    reviewed = {}
    for item in retained:
        evidence = item.get("retention_proof")
        if evidence is None:
            continue
        generation = evidence["generation"]
        if (
            item.get("retention_only") is not True
            or generation["generation_id"] != old_authority["generation_id"]
            or generation["manifest_sha256"] != old_authority["manifest_sha256"]
            or generation["role_hashes"]
            != {r: v["sha256"] for r, v in old_authority["roles"].items()}
        ):
            raise ValueError("OLD_RETENTION_GENERATION_BINDING_MISMATCH")
        ticker, identity = item["ticker"], item["identity_binding"]
        old = authority(
            paths.provider_db,
            paths.canonical_db,
            ticker,
            identity,
            allow_missing_provider=True,
            retention_proof=evidence,
        )
        new = authority(
            provider,
            canonical,
            ticker,
            identity,
            allow_missing_provider=True,
            retention_proof=evidence,
        )
        if old != new:
            raise ValueError("OLD_RETENTION_AUTHORITY_CHANGED:" + ticker)
        reviewed[ticker] = old
    return {
        **proof,
        "reviewed_retained_tickers": sorted(reviewed),
        "reviewed_authority_fingerprint": digest(reviewed),
    }


def incoming(change):
    # Bind novel evidence too. Acquisition-time receipts are retained separately;
    # their stable verified scope is in source_completeness for revalidation.
    return {
        k: v
        for k, v in change.items()
        if k
        not in {
            "quarantine_locality",
            "quarantine_failure",
            "baseline_integrity_hold",
            "source_response_receipts",
            "snapshot_reference",
        }
    }


def identity_partition(changes):
    return digest(
        sorted(
            (
                {
                    "ticker": x.get("ticker"),
                    "classification": x.get("classification"),
                    "identity": x.get("identity"),
                }
                for x in changes
            ),
            key=lambda x: str(x["ticker"]),
        )
    )


def isolation_failure(change):
    """Prove an exclusion boundary, without interpreting the unresolved values.

    Novel reasons and incomplete receipts are not shared-risk evidence. Explicit
    shared failures and foreign identities are. Native schema/discovery and
    source-acceptance gates remain independent operation-wide requirements.
    """
    ticker = change.get("ticker")
    identity = change.get("identity") or {}
    if (
        change.get("classification") != "REVIEW_REQUIRED"
        or not isinstance(ticker, str)
        or not ticker
        or ticker != ticker.strip().upper()
        or identity.get("status") != "KNOWN"
        or any(not identity.get(k) for k in IDENTITY if k != "company_key")
        or any(
            identity.get(k) != ticker
            for k in ("ticker", "current_ticker", "provider_ticker")
        )
    ):
        return "WHOLE_TICKER_IDENTITY_UNPROVEN"
    domains = {"company_id", "security_id", "provider_security_id"}

    def inspect(value):
        if isinstance(value, Mapping):
            if value.get("shared_integrity_failure") or value.get("shared_failure"):
                return "SHARED_INTEGRITY_FAILURE"
            if value.get("scope") in {
                "SHARED",
                "CROSS_TICKER",
                "GLOBAL_BLOCKING_REVIEW",
            }:
                return "SHARED_SCOPE_EVIDENCE"
            for k, v in value.items():
                # Capture key-state dictionaries describe field presence, not
                # identity values. Their enum values must not be read as symbols.
                if (
                    k in {"key_states", "required_profile_field_states"}
                    and isinstance(v, Mapping)
                    and all(
                        w in {"VALUE", "ABSENT", "EXPLICIT_NULL"} for w in v.values()
                    )
                ):
                    continue
                if (
                    k in {"ticker", "current_ticker", "provider_ticker"}
                    and v is not None
                    and v != ticker
                ):
                    return "CROSS_TICKER_SOURCE_MAPPING"
                if k in domains and v is not None and str(v) != str(identity[k]):
                    return "CROSS_TICKER_IDENTITY_MAPPING"
                if (
                    k in {"affected_tickers", "source_tickers"}
                    and isinstance(v, (list, tuple))
                    and set(v) != {ticker}
                ):
                    return "CROSS_TICKER_AFFECTED_SET"
                error = inspect(v)
                if error:
                    return error
        elif isinstance(value, (list, tuple)):
            for v in value:
                error = inspect(v)
                if error:
                    return error
        return None

    return inspect(incoming(change))


def supported_evidence(change):
    # Compatibility name: locality has no review-reason or shape allowlist.
    return isolation_failure(change) is None


def valid_proof(change):
    proof = change.get("quarantine_locality") or {}
    return bool(
        supported_evidence(change)
        and proof.get("policy") == VERSION
        and proof.get("incoming_fingerprint") == digest(incoming(change))
        and proof.get("accepted_baseline", {}).get("provider")
        and proof.get("accepted_baseline", {}).get("canonical")
        and proof.get("whole_ticker_excluded") is True
        and proof.get("publication_writes_blocked") is False
        and proof.get("baseline_integrity_hold")
        == change.get("baseline_integrity_hold")
        and proof.get("partition_identity_fingerprint")
        and proof.get("fingerprint")
        == digest({k: v for k, v in proof.items() if k != "fingerprint"})
    )


def bind_locality(
    changes, paths, *, publication_safety=None, pending_baseline_holds=()
):
    """Build positive whole-ticker isolation before partitioning any new shape.

    The same proof is rebuilt in Test and Production; all held authority is then
    compared on the complete candidate before publication. It grants no approval.
    """
    from .refresh_fundamentals import load_current_history, resolve_identity
    from .publication_journal import safety_status, ACTIVE_JOURNAL_PATH

    safety = (
        publication_safety
        if publication_safety is not None
        else safety_status(ACTIVE_JOURNAL_PATH)
    )
    from . import baseline_carry_forward as carry

    try:
        generation = carry.verified_generation(paths)
        generation_error = None
    except (ValueError, RuntimeError, OSError) as error:
        generation = None
        generation_error = str(error)
    if not any(x.get("classification") == "REVIEW_REQUIRED" for x in changes):
        if generation_error or safety.get("production_writes_blocked"):
            raise ValueError(
                "PUBLICATION_SAFETY_UNSAFE:" + str(generation_error or safety)
            )
    issues = carry.baseline_issues(
        paths,
        [
            (x.get("identity") or {})["company_id"]
            for x in changes
            if (x.get("identity") or {}).get("status") == "KNOWN"
        ],
    )
    for x in changes:
        company = (x.get("identity") or {}).get("company_id")
        if any(v["cross_company"] for v in issues.get(company, [])):
            x["classification"] = "REVIEW_REQUIRED"
            x["shared_integrity_failure"] = {
                "reason": "CROSS_COMPANY_ACCEPTED_SOURCE_MAPPING"
            }
        if (
            x.get("ticker") not in pending_baseline_holds and company not in issues
        ) or x.get("classification") == "REVIEW_REQUIRED":
            continue
        try:
            authority(
                paths.provider_db,
                paths.canonical_db,
                x["ticker"],
                x["identity"],
                validate=True,
            )
        except (ValueError, KeyError, sqlite3.Error):
            x["prior_classification"] = x.get("classification")
            x["classification"] = "REVIEW_REQUIRED"
            x["review_reason"] = carry.REASON
    partition = identity_partition(changes)
    owners = {}
    for x in changes:
        for k in ("company_id", "security_id", "provider_security_id"):
            v = (x.get("identity") or {}).get(k)
            if v is not None:
                owners.setdefault((k, str(v)), set()).add(x.get("ticker"))
    collisions = (
        set().union(*(v for v in owners.values() if len(v) > 1)) if owners else set()
    )
    for x in changes:
        if x.get("classification") != "REVIEW_REQUIRED":
            continue
        x.pop("quarantine_locality", None)
        x.pop("quarantine_failure", None)
        x.pop("baseline_integrity_hold", None)
        failure = isolation_failure(x)
        if generation_error:
            failure = "ACTIVE_GENERATION_INVALID:" + generation_error
        elif safety.get("production_writes_blocked"):
            failure = "IMMUTABLE_GENERATION_RECOVERY_UNSAFE"
        elif x.get("ticker") in collisions:
            failure = "SHARED_IDENTITY_COLLISION"
        if failure:
            x["quarantine_failure"] = failure
            continue
        from .refresh_review_queue import classify_review_scope, TICKER_LOCAL_REVIEW

        if (
            x["identity"]["company_id"] not in issues
            and classify_review_scope(x)["scope"] == TICKER_LOCAL_REVIEW
        ):
            # Existing approval contracts keep their exact evidence projection.
            # Candidate carry-forward and the native preservation checks still
            # validate their complete canonical state before any publication.
            continue
        try:
            identity = resolve_identity(paths, x["ticker"])
            if any(
                identity.get(k) != (x.get("identity") or {}).get(k)
                for k in ("status", *IDENTITY)
            ):
                raise ValueError("WHOLE_TICKER_PUBLISHED_IDENTITY_MISMATCH")
            state = carry.snapshot(
                paths.canonical_db, x["identity"]["company_id"], validate=True
            )
            baseline = authority(
                paths.provider_db,
                paths.canonical_db,
                x["ticker"],
                x["identity"],
                allow_missing_provider=True,
            )
            try:
                authority(
                    paths.provider_db,
                    paths.canonical_db,
                    x["ticker"],
                    x["identity"],
                    validate=True,
                )
                degraded = None
            except ValueError as error:
                if generation is None:
                    raise ValueError(
                        "DEGRADED_BASELINE_REQUIRES_VERIFIED_ACTIVE_GENERATION"
                    ) from error
                degraded = {
                    "reason": carry.REASON,
                    "source_validation_error": str(error),
                    "carry_forward_authority": generation,
                    "canonical_fingerprint": baseline["canonical"],
                    "broken_provenance": carry.broken_references(
                        paths.provider_db, state
                    ),
                    "new_incoming_evidence_accepted": False,
                    "guidance": "Current published financial state retained. Historical provider provenance is incomplete. New incoming financial evidence is held until reviewed/repaired.",
                }

        except (ValueError, KeyError, sqlite3.Error) as error:
            x["quarantine_failure"] = "ACCEPTED_BASELINE_UNPROVEN:" + str(error)
            continue
        # Keep existing approval-grade bindings after generic validation.
        # Novel/degraded holds gain exclusion authority, never approval authority.
        from .refresh_review_queue import classify_review_scope, TICKER_LOCAL_REVIEW

        if not degraded and classify_review_scope(x)["scope"] == TICKER_LOCAL_REVIEW:
            continue
        proof = {
            "policy": VERSION,
            "incoming_fingerprint": digest(incoming(x)),
            "accepted_baseline": baseline,
            "partition_identity_fingerprint": partition,
            "whole_ticker_excluded": True,
            "publication_writes_blocked": False,
            **({"baseline_integrity_hold": degraded} if degraded else {}),
        }
        if degraded:
            x["baseline_integrity_hold"] = degraded
        x["quarantine_locality"] = {**proof, "fingerprint": digest(proof)}


def verify_held(before_paths, provider_candidate, canonical_candidate, held):
    """Fail before publication if any held incoming evidence became authority."""
    receipts = {}
    for x in held:
        identity = (
            x.get("identity_binding") or (x.get("change") or {}).get("identity") or {}
        )
        if not all(
            identity.get(k)
            for k in ("company_id", "security_id", "provider_security_id")
        ):
            raise ValueError("QUARANTINE_HELD_IDENTITY_MISSING")
        old = authority(
            before_paths.provider_db,
            before_paths.canonical_db,
            x["ticker"],
            identity,
            allow_missing_provider=True,
        )
        new = authority(
            provider_candidate,
            canonical_candidate,
            x["ticker"],
            identity,
            allow_missing_provider=True,
        )
        if old != new:
            raise ValueError("QUARANTINE_HELD_AUTHORITY_CHANGED:" + x["ticker"])
        receipts[x["ticker"]] = old
    return {
        "policy": VERSION,
        "held_tickers": sorted(receipts),
        "authority_fingerprint": digest(receipts),
        "unchanged": True,
    }


def verify_replacements(provider_result, expected):
    actual = [x["ticker"] for x in provider_result.get("tickers", [])]
    if (
        len(actual) != len(set(actual))
        or sorted(actual) != sorted(expected)
        or provider_result.get("ticker_count") != len(expected)
    ):
        raise ValueError("REFRESH_ACTUAL_SAFE_REPLACEMENT_SET_MISMATCH")


def apply_to_comparison(change, **kwargs):
    """Route unavailable frozen lineage to isolation proof; grant no repair."""
    from .historical_freeze import apply_to_comparison as frozen

    try:
        return frozen(change, **kwargs)
    except ValueError as error:
        if not str(error).startswith(
            ("HISTORICAL_FREEZE_ACCEPTED_SOURCE_", "HISTORICAL_FREEZE_ACCEPTED_EQUITY_")
        ):
            raise
        from .baseline_carry_forward import REASON

        return {
            **change,
            "classification": "REVIEW_REQUIRED",
            "review_reason": REASON,
            "accepted_baseline_error": str(error),
        }
