"""Refresh eligibility projected from the installed Phase 13B authority.

This reader grants no membership. Physical identities outside that authority
may identify OLD carry-forward state, never incoming financial authority.
"""

from contextlib import closing, nullcontext

from rawcandle.fundamentals.phase13b_foundation import (
    CONTRACT_VERSION,
    universe_identity,
)
from . import baseline_carry_forward as carry
from . import refresh_fundamentals as rules
from .contracts import fingerprint
from . import financial_selection

POLICY = "FUNDAMENTALS_REFRESH_INSTALLED_UNIVERSE_V1"
HISTORICAL_MODELS = (
    "score_result",
    "lifecycle_revised_result",
    "valuation_revised_result",
    "fundamental_delta_result",
    "diagnostic_flag_endpoint",
)


class RefreshUniverseError(ValueError):
    pass


class InstalledUniverse:
    def __init__(self, paths, *, _connection=None):
        self.paths = paths
        # The owned-copy installer validates before committing its transaction.
        # Ordinary runtime readers always open their own query-only connection.
        with (
            nullcontext(_connection)
            if _connection is not None
            else closing(carry.readonly(paths.canonical_db))
        ) as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_schema WHERE name='fundamentals_operational_universe_active_version'"
            ).fetchone():
                raise RefreshUniverseError("REFRESH_INSTALLED_UNIVERSE_REQUIRED")
            versions = [
                dict(r)
                for r in db.execute(
                    "SELECT v.* FROM fundamentals_operational_universe_active_version a "
                    "JOIN fundamentals_operational_universe_version v USING(universe_version_id) WHERE a.singleton=1"
                )
            ]
            if (
                len(versions) != 1
                or versions[0]["status"] != "COMPLETE"
                or versions[0]["contract_version"] != CONTRACT_VERSION
                or versions[0]["semantic_mode"] != "CURRENT_OPERATIONAL_UNIVERSE"
            ):
                raise RefreshUniverseError("REFRESH_UNIVERSE_AUTHORITY_INCONSISTENT")
            version = versions[0]
            vid = version["universe_version_id"]
            members = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM fundamentals_operational_universe_member WHERE universe_version_id=? ORDER BY company_id",
                    (vid,),
                )
            ]
            aliases = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM fundamentals_operational_universe_member_alias WHERE universe_version_id=? "
                    "ORDER BY company_id,security_id,alias_ticker,provider,valid_from",
                    (vid,),
                )
            ]
            securities = [
                dict(r)
                for r in db.execute("SELECT * FROM security ORDER BY security_id")
            ]
            physical_aliases = [
                dict(r)
                for r in db.execute("SELECT * FROM ticker_alias ORDER BY alias_id")
            ]
            mappings = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM provider_security_identity ORDER BY provider,provider_security_id"
                )
            ]
        identity = universe_identity(members, aliases, as_of_date=version["as_of_date"])
        # Native removal versions hash predecessor-version-bearing alias rows.
        # Do not reinterpret that source fingerprint; pin exact stored content.
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
                raise RefreshUniverseError(
                    "REFRESH_UNIVERSE_AUTHORITY_INCONSISTENT:" + key
                )
        self.members = {m["company_id"]: m for m in members}
        self.securities = {s["security_id"]: s for s in securities}
        self.names = {}
        self.installed_aliases = {
            (a["security_id"], a["alias_ticker"].upper()) for a in aliases
        }
        self.mappings = mappings
        self.financial_selections = {}
        for s in securities:
            self.names.setdefault(s["current_ticker"].upper(), set()).add(
                s["security_id"]
            )
        for a in physical_aliases:
            self.names.setdefault(a["ticker"].upper(), set()).add(a["security_id"])
        for m in members:
            sid = m["security_id"]
            owned = [s for s in securities if s["company_id"] == m["company_id"]]
            active = [s for s in owned if s["active"] == 1]
            if (
                len(active) != m["active_security_count"]
                or len(owned) != m["all_security_count"]
                or (
                    m["membership_status"] == "ACTIVE_SINGLE_SECURITY"
                    and (sid is None or self.securities.get(sid, {}).get("active") != 1)
                )
                or (
                    sid is not None
                    and (
                        sid not in self.securities
                        or self.securities[sid]["company_id"] != m["company_id"]
                        or self.securities[sid]["current_ticker"] != m["current_ticker"]
                    )
                )
            ):
                raise RefreshUniverseError("REFRESH_UNIVERSE_SECURITY_CONTRADICTION")
            try:
                selection = financial_selection.read_selection(
                    m, securities, mappings, physical_aliases, self.installed_aliases
                )
            except ValueError as error:
                raise RefreshUniverseError(str(error)) from error
            if selection is not None:
                self.financial_selections[m["company_id"]] = selection
        for a in aliases:
            if (
                a["company_id"] not in self.members
                or a["security_id"] not in self.securities
                or self.securities[a["security_id"]]["company_id"] != a["company_id"]
            ):
                raise RefreshUniverseError("REFRESH_UNIVERSE_ALIAS_CONTRADICTION")
        self.binding = dict(
            policy=POLICY,
            universe_version_id=vid,
            content_fingerprint=fingerprint(
                dict(
                    version=version,
                    members=members,
                    aliases=aliases,
                    securities=securities,
                    physical_aliases=physical_aliases,
                    provider_security_identity=mappings,
                )
            ),
        )
        if self.financial_selections:
            self.binding.update(
                financial_selection_contract=financial_selection.CONTRACT,
                financial_selection_fingerprint=fingerprint(self.financial_selections),
            )

    @property
    def eligible_companies(self):
        return {
            c
            for c, m in self.members.items()
            if m["membership_status"] == "ACTIVE_SINGLE_SECURITY"
            or c in self.financial_selections
        }

    def resolve(self, ticker):
        ticker = ticker.strip().upper()
        ids = self.names.get(ticker, set())
        admitted = [
            sid for sid in ids if self.securities[sid]["company_id"] in self.members
        ]
        if not admitted:
            return dict(
                status="EXCLUDED", ticker=ticker, reason="OUTSIDE_INSTALLED_UNIVERSE"
            )
        if len(ids) != 1:
            return dict(
                status="AMBIGUOUS",
                ticker=ticker,
                reason="ADMITTED_SECURITY_ALIAS_COLLISION",
            )
        sid = admitted[0]
        s = self.securities[sid]
        m = self.members[s["company_id"]]
        if m["membership_status"] == "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY":
            return dict(
                status="EXCLUDED", ticker=ticker, reason="HISTORICAL_RETENTION_ONLY"
            )
        if s["company_id"] in self.financial_selections and m["security_id"] != sid:
            return dict(
                status="EXCLUDED",
                ticker=ticker,
                reason="FINANCIAL_COMPANION_RETENTION_ONLY",
                company_id=s["company_id"],
                security_id=sid,
                representative_ticker=m["current_ticker"],
            )
        if (
            m["membership_status"] != "ACTIVE_SINGLE_SECURITY"
            and s["company_id"] not in self.financial_selections
        ) or m["security_id"] != sid:
            return dict(
                status="AMBIGUOUS",
                ticker=ticker,
                reason="ADMITTED_SECURITY_SELECTION_REQUIRED",
            )
        if (
            ticker != s["current_ticker"].upper()
            and (sid, ticker) not in self.installed_aliases
        ):
            return dict(
                status="AMBIGUOUS",
                ticker=ticker,
                reason="ALIAS_NOT_BOUND_TO_INSTALLED_VERSION",
            )
        identity = rules.resolve_identity(self.paths, s["current_ticker"])
        if (
            identity["status"] != "KNOWN"
            or identity.get("security_id") != sid
            or identity.get("company_id") != s["company_id"]
            or identity.get("provider_ticker") != s["current_ticker"]
        ):
            return dict(
                status="AMBIGUOUS",
                ticker=ticker,
                reason="NATIVE_ADMITTED_IDENTITY_UNPROVEN",
                identity=identity,
            )
        return dict(
            status="ELIGIBLE",
            ticker=ticker,
            acquisition_ticker=identity["current_ticker"],
            identity=identity,
        )

    def plan(self, **origins):
        selected, excluded, ambiguous, resolutions = set(), [], [], []
        for origin, tickers in origins.items():
            for ticker in sorted(set(tickers)):
                r = dict(self.resolve(ticker), origin=origin)
                resolutions.append(r)
                if r["status"] == "ELIGIBLE":
                    selected.add(r["acquisition_ticker"])
                elif r["status"] == "EXCLUDED":
                    if r.get(
                        "reason"
                    ) == "FINANCIAL_COMPANION_RETENTION_ONLY" and origin in {
                        "financial_reviews",
                        "accounting_queue",
                        "accounting_installed",
                    }:
                        # Reevaluate the company's selected source; the companion's
                        # approval remains bound to its own original identity.
                        representative = self.resolve(r["representative_ticker"])
                        if representative["status"] != "ELIGIBLE":
                            ambiguous.append(representative)
                        else:
                            selected.add(representative["acquisition_ticker"])
                            r["reevaluate_representative"] = representative[
                                "acquisition_ticker"
                            ]
                    excluded.append(r)
                else:
                    ambiguous.append(r)
        return dict(
            universe_binding=self.binding,
            evaluation_tickers=sorted(selected),
            scope_exclusions=excluded,
            scope_ambiguities=ambiguous,
            scope_resolutions=resolutions,
        )

    def require_tickers(self, tickers):
        for ticker in tickers:
            r = self.resolve(ticker)
            if r["status"] != "ELIGIBLE" or r["acquisition_ticker"] != ticker:
                raise RefreshUniverseError(
                    "REFRESH_INCOMING_SCOPE_NOT_AUTHORIZED:" + ticker
                )

    def old_retention(self):
        """Identify OLD state by physical ownership, without admitting it."""
        with closing(carry.readonly(self.paths.canonical_db)) as db:
            domain = [
                dict(r)
                for r in db.execute(
                    "SELECT DISTINCT s.security_id,s.company_id,s.current_ticker FROM security s JOIN v4_quarter q USING(company_id)"
                )
            ]
        retained, blocked = [], []
        for s in domain:
            r = self.resolve(s["current_ticker"])
            if r["status"] == "AMBIGUOUS":
                blocked.append(s["current_ticker"])
            elif r["status"] == "EXCLUDED":
                if r.get("reason") == "FINANCIAL_COMPANION_RETENTION_ONLY":
                    # Preserve its security/provider bytes separately; freezing
                    # this entire company would discard authorized rep updates.
                    continue
                ids = {
                    str(m["provider_security_id"])
                    for m in self.mappings
                    if m["security_id"] == s["security_id"]
                    and m["provider"] == "SHARADAR"
                }
                if len(ids) > 1 or len(self.names.get(s["current_ticker"], ())) != 1:
                    raise RefreshUniverseError(
                        "REFRESH_OLD_RETENTION_IDENTITY_UNPROVEN:" + s["current_ticker"]
                    )
                item = dict(
                    ticker=s["current_ticker"],
                    retention_only=True,
                    identity_binding=dict(
                        company_id=s["company_id"],
                        security_id=s["security_id"],
                        provider_security_id=next(iter(ids), None),
                    ),
                )
                if not ids:
                    from .review_locality import historical_retention_proof

                    try:
                        item["retention_proof"] = historical_retention_proof(
                            self.paths, item["ticker"], item["identity_binding"]
                        )
                    except ValueError as error:
                        raise RefreshUniverseError(
                            "REFRESH_OLD_RETENTION_IDENTITY_UNPROVEN:" + item["ticker"]
                        ) from error
                retained.append(item)
        financial_selection.verify_companion_retention(
            self.paths, self.paths.provider_db, self.paths.canonical_db
        )
        return retained, sorted(blocked)

    def require_buildable_old_history(self, retained):
        return require_buildable_analysis_history(self.paths, retained)


def _analysis_retention_scope(paths, retained):
    """Include historical owners outside the incoming/canonical-quarter plan."""
    with closing(carry.readonly(paths.canonical_db)) as db:
        canonical = {r[0] for r in db.execute("SELECT company_id FROM company")}
        active = {
            r[0]
            for r in db.execute(
                "SELECT DISTINCT company_id FROM security WHERE active=1"
            )
        }
    with closing(carry.readonly(paths.analysis_db)) as db:
        present = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        owners = {
            table: {
                r[0] for r in db.execute(f"SELECT DISTINCT company_id FROM {table}")
            }
            for table in HISTORICAL_MODELS
            if table in present
        }
    historical = (canonical - active) | (set().union(*owners.values()) - canonical)
    return (
        historical
        | {r["identity_binding"]["company_id"] for r in retained}
        | set(financial_selection.selected_securities(paths.canonical_db)),
        historical,
        owners,
    )


def require_buildable_analysis_history(paths, retained):
    """Allow empty actual history; reject known loss by native reconstruction.

    No historical import/recalculation is invented. Check all inactive/missing
    company owners, including those absent from installed membership or FETCH.
    """
    _, historical, owners = _analysis_retention_scope(paths, retained)
    for table, companies in owners.items():
        at_risk = historical & companies
        if at_risk:
            company = min(at_risk)  # Diagnostic order, never a security selection.
            raise RefreshUniverseError(
                f"REFRESH_OLD_ANALYSIS_RETENTION_UNSUPPORTED:{company}:{table}:NATIVE_TTM_REQUIRES_ACTIVE_SECURITY"
            )
    return dict(
        status="NO_AT_RISK_ACCEPTED_HISTORY",
        checked_companies=sorted(historical),
        historical_tables=sorted(owners),
    )


def analysis_history(analysis, canonical, companies):
    """Economic history coverage of the existing native model tables."""
    with closing(carry.readonly(canonical)) as db:
        quarters = {
            r["quarter_id"]: (
                r["company_id"],
                r["fiscal_year"],
                str(r["fiscal_quarter"]).removeprefix("Q"),
            )
            for r in db.execute(
                "SELECT quarter_id,company_id,fiscal_year,fiscal_quarter FROM v4_quarter"
            )
            if r["company_id"] in companies
        }
    result = {}
    with closing(carry.readonly(analysis)) as db:
        present = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        for table in HISTORICAL_MODELS:
            if table not in present:
                continue
            cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            keys = set()
            for company in sorted(companies):
                for r in db.execute(
                    f"SELECT * FROM {table} WHERE company_id=?", (company,)
                ):
                    if {"fiscal_year", "fiscal_quarter"} <= cols:
                        quarter = (
                            r["fiscal_year"],
                            str(r["fiscal_quarter"]).removeprefix("Q"),
                        )
                    else:
                        quarter = quarters.get(r["quarter_id"])
                        if quarter is None or quarter[0] != company:
                            raise RefreshUniverseError(
                                "REFRESH_OLD_ANALYSIS_QUARTER_UNBOUND:" + table
                            )
                        quarter = quarter[1:]
                    keys.add((company, *quarter))
            result[table] = keys
    return result


def verify_analysis_retention(paths, canonical, analysis, retained):
    companies, _, _ = _analysis_retention_scope(paths, retained)
    before = analysis_history(paths.analysis_db, paths.canonical_db, companies)
    after = analysis_history(analysis, canonical, companies)
    for table, keys in before.items():
        if not keys <= after.get(table, set()):
            raise RefreshUniverseError("REFRESH_OLD_ANALYSIS_HISTORY_LOST:" + table)
    return dict(
        companies=sorted(companies),
        historical_rows={t: len(k) for t, k in before.items()},
        preserved=True,
    )


def require_binding(paths, request):
    binding = request.get("refresh_universe")
    if not binding or binding.get("policy") != POLICY:
        raise RefreshUniverseError("UPDATE_UNIVERSE_BINDING_REQUIRED_NEW_UPDATE")
    installed = InstalledUniverse(paths)
    if installed.binding != binding:
        raise RefreshUniverseError("UPDATE_INSTALLED_UNIVERSE_DRIFT")
    return installed
