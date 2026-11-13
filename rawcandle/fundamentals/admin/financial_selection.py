"""Explicit financial-purpose selections in native versioned member rows.

No allocator, external identity reader or production installation entry point.
Decisions are supplied by the operator; runtime authority is the installed row.
"""

from contextlib import closing, nullcontext
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

from rawcandle.fundamentals.phase13b_foundation import (
    CONTRACT_VERSION,
    universe_identity,
)
from . import baseline_carry_forward as carry
from .contracts import fingerprint

CONTRACT = "FUNDAMENTALS_FINANCIAL_REPRESENTATIVE_V1"
STATUS = "OPERATOR_APPROVED_FINANCIAL_REPRESENTATIVE"
PURPOSE = "FINANCIAL_REFRESH_ONLY"
ROOT = Path(__file__).resolve().parents[3]


def code_binding():
    from .publication_journal import sha256_file

    files = [
        Path(__file__),
        Path(__file__).with_name("refresh_universe.py"),
        Path(__file__).with_name("refresh_copy_runtime.py"),
        Path(__file__).with_name("refresh_update.py"),
        ROOT / "rawcandle/fundamentals/phase12d.py",
    ]
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in files}


def read_state(canonical, *, connection=None):
    """Read exact native authority, including a stale physical-count assertion."""
    with (
        nullcontext(connection)
        if connection is not None
        else closing(carry.readonly(canonical))
    ) as db:
        versions = [
            dict(r)
            for r in db.execute(
                "SELECT v.* FROM fundamentals_operational_universe_version v "
                "JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) WHERE a.singleton=1"
            )
        ]
        if (
            len(versions) != 1
            or versions[0]["contract_version"] != CONTRACT_VERSION
            or versions[0]["status"] != "COMPLETE"
        ):
            raise ValueError("FINANCIAL_SELECTION_INSTALLED_AUTHORITY_REQUIRED")
        version = versions[0]
        members = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? ORDER BY company_id",
                (version["universe_version_id"],),
            )
        ]
        aliases = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM fundamentals_operational_universe_member_alias WHERE universe_version_id=? "
                "ORDER BY company_id,security_id,alias_ticker,provider,valid_from",
                (version["universe_version_id"],),
            )
        ]
        state = dict(version=version, members=members, aliases=aliases)
        for key, table, order in (
            ("securities", "security", "security_id"),
            ("physical_aliases", "ticker_alias", "alias_id"),
            ("mappings", "provider_security_identity", "provider,provider_security_id"),
        ):
            state[key] = [
                dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY {order}")
            ]
    identity = universe_identity(members, aliases, as_of_date=version["as_of_date"])
    for key in (
        "universe_version_id",
        "economic_result_fingerprint",
        "member_count",
        "company_count",
        "active_security_count",
        "zero_active_company_count",
        "multi_active_company_count",
    ):
        if identity[key] != version[key]:
            raise ValueError(
                "FINANCIAL_SELECTION_INSTALLED_FINGERPRINT_MISMATCH:" + key
            )
    return state


def physical_binding(company, securities, mappings, aliases):
    owned = [s for s in securities if s["company_id"] == company]
    ids = {s["security_id"] for s in owned}
    return fingerprint(
        dict(
            securities=owned,
            mappings=[m for m in mappings if m["security_id"] in ids],
            aliases=[a for a in aliases if a["security_id"] in ids],
        )
    )


def read_selection(member, securities, mappings, physical_aliases, installed_aliases):
    """Validate purpose-specific authority without granting another security it."""
    if member["source"] != CONTRACT:
        if member["identity_resolution_status"] == STATUS:
            raise ValueError("FINANCIAL_SELECTION_AUTHORITY_MISSING")
        return None
    try:
        decision = json.loads(member["reason"])
        cid, sid = member["company_id"], member["security_id"]
        owned = {s["security_id"]: s for s in securities if s["company_id"] == cid}
        maps = [
            m
            for m in mappings
            if m["security_id"] == sid and m["provider"] == "SHARADAR"
        ]
        if not (
            decision["contract"] == CONTRACT
            and decision["purpose"] == PURPOSE
            and member["identity_resolution_status"] == STATUS
            and decision["company_id"] == cid
            and decision["security_id"] == sid
            and owned[sid]["current_ticker"]
            == decision["ticker"]
            == member["current_ticker"]
            and owned[sid]["active"] == 1
            and len(maps) == 1
            and str(maps[0]["provider_security_id"]) == decision["provider_security_id"]
            and maps[0]["provider_ticker"] == decision["ticker"]
            and decision["companion_security_ids"] == sorted(set(owned) - {sid})
            and decision["physical_fingerprint"]
            == physical_binding(cid, securities, mappings, physical_aliases)
            and all(
                (s, owned[s]["current_ticker"].upper()) in installed_aliases
                for s in owned
            )
            and decision["approval_reference"]
            and len(decision["approval_fingerprint"]) == 64
            and decision["starting_universe_fingerprint"]
            and decision["old_authority"]
            and decision["code_binding"]
        ):
            raise ValueError("invalid selection")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("FINANCIAL_SELECTION_AUTHORITY_INVALID") from exc
    return decision


def prepare_reconciliation(
    paths, decisions, *, expected_start, expected_old, approval_reference, applied_at
):
    """Plan a new version; never edit the starting authority or publish finance."""
    from . import review_locality as locality

    state = read_state(paths.canonical_db)
    if fingerprint(state) != expected_start:
        raise ValueError("FINANCIAL_SELECTION_STARTING_UNIVERSE_DRIFT")
    if carry.verified_generation(paths) != expected_old or expected_old is None:
        raise ValueError("FINANCIAL_SELECTION_OLD_GENERATION_DRIFT")
    choices = sorted(deepcopy(decisions), key=lambda d: d["company_id"])
    if (
        not approval_reference
        or not choices
        or len({d["company_id"] for d in choices}) != len(choices)
    ):
        raise ValueError("FINANCIAL_SELECTION_EXPLICIT_DECISIONS_REQUIRED")
    approval = fingerprint(dict(reference=approval_reference, decisions=choices))
    members = deepcopy(state["members"])
    aliases = [
        {k: v for k, v in a.items() if k != "universe_version_id"}
        for a in state["aliases"]
    ]
    evidence = {}
    for choice in choices:
        cid, sid, ticker = choice["company_id"], choice["security_id"], choice["ticker"]
        member = next((m for m in members if m["company_id"] == cid), None)
        owned = [s for s in state["securities"] if s["company_id"] == cid]
        selected = [
            s
            for s in owned
            if s["security_id"] == sid
            and s["current_ticker"] == ticker
            and s["active"] == 1
        ]
        maps = [
            m
            for m in state["mappings"]
            if m["security_id"] == sid and m["provider"] == "SHARADAR"
        ]
        if (
            member is None
            or member["membership_status"] == "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY"
            or len(selected) != 1
            or len(maps) != 1
            or str(maps[0]["provider_security_id"]) != choice["provider_security_id"]
            or maps[0]["provider_ticker"] != ticker
            or choice["companion_security_ids"]
            != sorted(s["security_id"] for s in owned if s["security_id"] != sid)
            or not any(
                a["security_id"] == sid and a["alias_ticker"] == ticker for a in aliases
            )
        ):
            raise ValueError("FINANCIAL_SELECTION_APPROVED_TUPLE_MISMATCH")
        identity = dict(
            company_id=cid,
            security_id=sid,
            provider_security_id=choice["provider_security_id"],
        )
        evidence[ticker] = locality.authority(
            paths.provider_db, paths.canonical_db, ticker, identity
        )
        with closing(carry.readonly(paths.provider_db)) as p, closing(
            carry.readonly(paths.canonical_db)
        ) as c:
            dims = {
                r[0]
                for r in p.execute(
                    "SELECT DISTINCT dimension FROM provider_observation WHERE company_id=? AND security_id=? AND provider_ticker=?",
                    (cid, sid, ticker),
                )
            }
            if not {"ARQ", "MRQ"} <= dims:
                raise ValueError("FINANCIAL_SELECTION_ACCEPTED_HISTORY_REQUIRED")
            refs = c.execute(
                "SELECT fp.provider_observation_id FROM v4_field_provenance fp JOIN v4_quarter q USING(quarter_id) WHERE q.company_id=?",
                (cid,),
            ).fetchall()
            if not refs:
                raise ValueError("FINANCIAL_SELECTION_CANONICAL_SOURCE_REQUIRED")
            for ref in {r[0] for r in refs}:
                owner = p.execute(
                    "SELECT company_id,security_id FROM provider_observation WHERE observation_id=?",
                    (ref,),
                ).fetchone()
                if owner is None or tuple(owner) != (cid, sid):
                    raise ValueError("FINANCIAL_SELECTION_CANONICAL_OWNER_MISMATCH")
        # Newly represented companions get aliases, never incoming authority.
        for a in state["physical_aliases"]:
            if a["security_id"] in {s["security_id"] for s in owned}:
                row = dict(
                    company_id=cid,
                    security_id=a["security_id"],
                    alias_ticker=a["ticker"],
                    provider=a["provider"],
                    valid_from=a["valid_from"],
                    valid_to=a["valid_to"],
                    source=a["source"],
                )
                if not any(
                    all(
                        x[k] == row[k]
                        for k in (
                            "company_id",
                            "security_id",
                            "alias_ticker",
                            "provider",
                            "valid_from",
                        )
                    )
                    for x in aliases
                ):
                    aliases.append(row)
        reason = dict(
            contract=CONTRACT,
            purpose=PURPOSE,
            **choice,
            approval_reference=approval_reference,
            approval_fingerprint=approval,
            physical_fingerprint=physical_binding(
                cid, state["securities"], state["mappings"], state["physical_aliases"]
            ),
            starting_universe_fingerprint=expected_start,
            old_authority=expected_old,
            code_binding=code_binding(),
        )
        member.update(
            security_id=sid,
            current_ticker=ticker,
            membership_status=(
                "ACTIVE_MULTI_SECURITY"
                if sum(s["active"] == 1 for s in owned) > 1
                else "ACTIVE_SINGLE_SECURITY"
            ),
            identity_resolution_status=STATUS,
            active_security_count=sum(s["active"] == 1 for s in owned),
            all_security_count=len(owned),
            source=CONTRACT,
            reason=json.dumps(reason, sort_keys=True, separators=(",", ":")),
            updated_at_utc=applied_at,
        )
    aliases.sort(
        key=lambda a: (
            a["company_id"],
            a["security_id"],
            a["alias_ticker"],
            a["provider"] or "",
            a["valid_from"] or "",
        )
    )
    identity = universe_identity(members, aliases, as_of_date=applied_at[:10])
    plan = dict(
        contract=CONTRACT,
        starting_universe=state["version"],
        starting_fingerprint=expected_start,
        old_authority=expected_old,
        decisions=choices,
        approval_reference=approval_reference,
        approval_fingerprint=approval,
        code_binding=code_binding(),
        applied_at=applied_at,
        identity=identity,
        members=members,
        aliases=aliases,
        financial_evidence=evidence,
    )
    return {**plan, "fingerprint": fingerprint(plan)}


def install_disposable_candidate(paths, plan):
    """Install only in an owned inactive copy, before native generation sealing.

    Production activation needs a separately qualified adapter/authorization.
    The native generation journal remains the sole publication/recovery engine.
    """
    target = Path(paths.canonical_db).absolute()
    if (
        not (
            target.is_relative_to(Path("/tmp")) or target.is_relative_to(ROOT / "temp")
        )
        or target.resolve() != target
        or target.stat().st_nlink != 1
        or "fundamentals_generations" in target.parts
        or any(p.is_symlink() for p in (target, *target.parents))
    ):
        raise ValueError("FINANCIAL_SELECTION_DISPOSABLE_INACTIVE_COPY_REQUIRED")
    if plan.get("contract") != CONTRACT or plan.get("fingerprint") != fingerprint(
        {k: v for k, v in plan.items() if k != "fingerprint"}
    ):
        raise ValueError("FINANCIAL_SELECTION_PLAN_INTEGRITY")
    if (
        plan["code_binding"] != code_binding()
        or fingerprint(read_state(target)) != plan["starting_fingerprint"]
    ):
        raise ValueError("FINANCIAL_SELECTION_PLAN_DRIFT")
    vid = plan["identity"]["universe_version_id"]
    with sqlite3.connect(target) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        if (
            fingerprint(read_state(target, connection=db))
            != plan["starting_fingerprint"]
        ):
            raise ValueError("FINANCIAL_SELECTION_PLAN_DRIFT")
        identity = plan["identity"]
        db.execute(
            "INSERT INTO fundamentals_operational_universe_version VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                vid,
                CONTRACT_VERSION,
                "CURRENT_OPERATIONAL_UNIVERSE",
                plan["applied_at"][:10],
                identity["source_fingerprint"],
                identity["economic_result_fingerprint"],
                identity["physical_content_fingerprint"],
                "COMPLETE",
                identity["member_count"],
                identity["company_count"],
                identity["active_security_count"],
                identity["zero_active_company_count"],
                identity["multi_active_company_count"],
                plan["applied_at"],
                plan["applied_at"],
            ),
        )
        for table, items in (
            ("fundamentals_operational_universe_member", plan["members"]),
            ("fundamentals_operational_universe_member_alias", plan["aliases"]),
        ):
            for item in items:
                row = {**item, "universe_version_id": vid}
                db.execute(
                    f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' for _ in row)})",
                    tuple(row.values()),
                )
        db.execute(
            "UPDATE fundamentals_operational_universe_active_version SET universe_version_id=?,activated_at_utc=? WHERE singleton=1",
            (vid, plan["applied_at"]),
        )
        from .refresh_universe import InstalledUniverse

        candidate = InstalledUniverse(paths, _connection=db)
    return dict(
        universe=candidate.binding,
        candidate_version=vid,
        plan_fingerprint=plan["fingerprint"],
    )


def selected_securities(canonical):
    """Exact installed financial source domain; legacy callers remain unchanged."""
    with closing(carry.readonly(canonical)) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_schema WHERE name='fundamentals_operational_universe_active_version'"
        ).fetchone():
            return {}
        members = [
            dict(r)
            for r in db.execute(
                "SELECT m.* FROM fundamentals_operational_universe_member m JOIN fundamentals_operational_universe_active_version a USING(universe_version_id) WHERE m.source=?",
                (CONTRACT,),
            )
        ]
    if not members:
        return {}
    state = read_state(canonical)
    aliases = {(a["security_id"], a["alias_ticker"].upper()) for a in state["aliases"]}
    for m in members:
        read_selection(
            m,
            state["securities"],
            state["mappings"],
            state["physical_aliases"],
            aliases,
        )
    return {m["company_id"]: m["security_id"] for m in members}


def verify_companion_retention(old_paths, provider, canonical):
    """Preserve security-owned OLD without freezing an updated company's facts."""
    selected = selected_securities(old_paths.canonical_db)
    if selected and read_state(old_paths.canonical_db) != read_state(canonical):
        raise ValueError("FINANCIAL_SELECTION_CANDIDATE_UNIVERSE_CHANGED")
    proofs = {}
    with closing(carry.readonly(old_paths.canonical_db)) as old, closing(
        carry.readonly(canonical)
    ) as new:
        for cid, representative in selected.items():
            ids = [
                r[0]
                for r in old.execute(
                    "SELECT security_id FROM security WHERE company_id=? AND security_id<>?",
                    (cid, representative),
                )
            ]
            for sid in ids:
                ticker = old.execute(
                    "SELECT current_ticker FROM security WHERE security_id=?", (sid,)
                ).fetchone()[0]
                for table, condition in (
                    ("security", "security_id=?"),
                    ("ticker_alias", "security_id=?"),
                    ("provider_security_identity", "security_id=?"),
                ):
                    before = [
                        dict(r)
                        for r in old.execute(
                            f"SELECT * FROM {table} WHERE {condition}", (sid,)
                        )
                    ]
                    after = [
                        dict(r)
                        for r in new.execute(
                            f"SELECT * FROM {table} WHERE {condition}", (sid,)
                        )
                    ]
                    if before != after:
                        raise ValueError("FINANCIAL_COMPANION_IDENTITY_CHANGED")
                with closing(carry.readonly(old_paths.provider_db)) as p, closing(
                    carry.readonly(provider)
                ) as q:

                    def observations(db):
                        return [
                            dict(r)
                            for r in db.execute(
                                "SELECT po.*,sf.* FROM provider_observation po LEFT JOIN sharadar_fundamental_observation sf USING(observation_id) "
                                "WHERE po.security_id=? OR (po.company_id=? AND po.provider_ticker=?) ORDER BY po.observation_id",
                                (sid, cid, ticker),
                            )
                        ]

                    prior, following = observations(p), observations(q)
                    if (
                        any(
                            r["company_id"] != cid or r["security_id"] != sid
                            for r in prior
                        )
                        or prior != following
                    ):
                        raise ValueError("FINANCIAL_COMPANION_OLD_PROVIDER_CHANGED")
                    proofs[str(sid)] = dict(
                        rows=len(prior), fingerprint=fingerprint(prior)
                    )
    return dict(companions=proofs, fingerprint=fingerprint(proofs))
