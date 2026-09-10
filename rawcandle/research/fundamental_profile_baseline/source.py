from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import AliasInterval, ForwardLabel, PriceBar, construct_forward_label, resolve_ticker, stable_hash, valid_bar


SCORE_FINGERPRINT = "271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360"
LIFECYCLE_FINGERPRINT = "0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175"
VALUATION_FINGERPRINT = "9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb"
DELTA_MODEL_FINGERPRINT = "c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11"
DIAGNOSTIC_MODEL_FINGERPRINT = "0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904"


@dataclass(frozen=True)
class ResearchPaths:
    canonical_db: Path
    analysis_db: Path
    provider_db: Path
    market_db: Path
    taxonomy_db: Path


def readonly(path: Path) -> sqlite3.Connection:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError(f"EXPLICIT_REGULAR_ABSOLUTE_PATH_REQUIRED:{path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _model_package_ids(conn: sqlite3.Connection) -> tuple[int, int]:
    delta = conn.execute(
        "SELECT package_id FROM fundamental_delta_package WHERE model_fingerprint=?",
        (DELTA_MODEL_FINGERPRINT,),
    ).fetchall()
    diagnostic = conn.execute(
        "SELECT package_id FROM diagnostic_flag_package WHERE model_fingerprint=?",
        (DIAGNOSTIC_MODEL_FINGERPRINT,),
    ).fetchall()
    if len(delta) != 1 or len(diagnostic) != 1:
        raise RuntimeError("ACTIVE_RESEARCH_PACKAGE_IDENTITY_MISMATCH")
    return int(delta[0][0]), int(diagnostic[0][0])


def load_endpoint_features(paths: ResearchPaths) -> tuple[list[dict[str, Any]], dict[int, list[AliasInterval]], dict[int, str]]:
    analysis = readonly(paths.analysis_db)
    delta_package, diagnostic_package = _model_package_ids(analysis)
    rows = [dict(row) for row in analysis.execute(
        """
        SELECT score_result_id,company_id,quarter_id,total_score AS fundamental_score,
               readiness_status AS score_status
        FROM score_result WHERE model_fingerprint=? ORDER BY company_id,quarter_id
        """,
        (SCORE_FINGERPRINT,),
    )]
    by_key = {(int(row["company_id"]), int(row["quarter_id"])): row for row in rows}
    by_score = {int(row["score_result_id"]): row for row in rows}

    for component in analysis.execute(
        """
        SELECT r.company_id,r.quarter_id,c.component_name,c.component_score,c.evidence_json
        FROM score_component c JOIN score_result r USING(score_result_id)
        WHERE r.model_fingerprint=? ORDER BY r.company_id,r.quarter_id,c.component_name
        """,
        (SCORE_FINGERPRINT,),
    ):
        row = by_key[(int(component["company_id"]), int(component["quarter_id"]))]
        name = str(component["component_name"]).lower()
        row[f"component_{name}"] = component["component_score"]
        row[f"component_{name}_evidence_json"] = component["evidence_json"]

    for lifecycle in analysis.execute(
        """
        SELECT company_id,quarter_id,fiscal_sequence,raw_state,final_state AS lifecycle,
               lifecycle_status,candidate_state,candidate_count,operating_margin_ttm,
               operating_margin_direction,fcf_margin_ttm,revenue_growth_yoy_ttm
        FROM lifecycle_revised_result WHERE model_fingerprint=?
        ORDER BY company_id,fiscal_sequence
        """,
        (LIFECYCLE_FINGERPRINT,),
    ):
        key = (int(lifecycle["company_id"]), int(lifecycle["quarter_id"]))
        if key in by_key:
            by_key[key].update(dict(lifecycle))

    for valuation in analysis.execute(
        """
        SELECT company_id,quarter_id,total_valuation_score AS valuation_score,
               valuation_status,reason_code AS valuation_reason,
               applicability_classification,operating_income_yield,operating_income_points,
               fcf_yield,fcf_points,earnings_yield,earnings_points,market_cap,sector,industry
        FROM valuation_revised_result WHERE model_fingerprint=?
        """,
        (VALUATION_FINGERPRINT,),
    ):
        key = (int(valuation["company_id"]), int(valuation["quarter_id"]))
        if key in by_key:
            by_key[key].update(dict(valuation))

    statuses = {int(row["status_id"]): str(row["status_text"]) for row in analysis.execute("SELECT * FROM fundamental_delta_status")}
    for delta in analysis.execute(
        """
        SELECT current_score_result_id,qoq_delta,two_quarter_delta,yoy_delta,
               qoq_status_id,two_quarter_status_id,yoy_status_id
        FROM fundamental_delta_result WHERE package_id=?
        """,
        (delta_package,),
    ):
        score_id = int(delta["current_score_result_id"])
        if score_id in by_score:
            values = dict(delta)
            values["qoq_status"] = statuses[int(delta["qoq_status_id"])]
            values["two_quarter_status"] = statuses[int(delta["two_quarter_status_id"])]
            values["yoy_status"] = statuses[int(delta["yoy_status_id"])]
            by_score[score_id].update(values)

    diagnostic_status = {int(row["status_id"]): str(row["status_text"]) for row in analysis.execute("SELECT * FROM diagnostic_flag_status")}
    flag_names = {int(row["flag_id"]): str(row["flag_name"]) for row in analysis.execute("SELECT * FROM diagnostic_flag_type")}
    diagnostics: dict[tuple[int, int], dict[str, Any]] = defaultdict(dict)
    for item in analysis.execute(
        """
        SELECT e.company_id,e.quarter_id,v.flag_id,v.status_id,v.triggered
        FROM diagnostic_flag_endpoint e JOIN diagnostic_flag_evaluation v USING(endpoint_id)
        WHERE e.package_id=? ORDER BY e.company_id,e.quarter_id,v.flag_id
        """,
        (diagnostic_package,),
    ):
        key = (int(item["company_id"]), int(item["quarter_id"]))
        diagnostics[key][flag_names[int(item["flag_id"])]] = diagnostic_status[int(item["status_id"])]
    for key, row in by_key.items():
        decisions = diagnostics.get(key, {})
        row["diagnostic_decisions"] = decisions
        row["diagnostic_flag_count"] = sum(status == "EVALUATED_FLAGGED" for status in decisions.values())
        row["diagnostic_complete"] = len(decisions) == 8
        row["diagnostic_not_ready_count"] = sum(status == "FLAG_NOT_READY" for status in decisions.values())
        row["diagnostic_not_applicable_count"] = sum(status == "FLAG_NOT_APPLICABLE" for status in decisions.values())
    analysis.close()

    canonical = readonly(paths.canonical_db)
    quarters = {int(row["quarter_id"]): dict(row) for row in canonical.execute(
        "SELECT quarter_id,fiscal_year,fiscal_quarter,period_end,source_availability_date FROM v4_quarter"
    )}
    aliases: dict[int, list[AliasInterval]] = defaultdict(list)
    company_status = {int(row["company_id"]): str(row["status"]) for row in canonical.execute("SELECT company_id,status FROM company")}
    for alias in canonical.execute(
        """
        SELECT s.company_id,s.current_ticker,s.active,a.ticker,a.valid_from,a.valid_to
        FROM security s JOIN ticker_alias a USING(security_id)
        ORDER BY s.company_id,a.valid_from,a.ticker
        """
    ):
        aliases[int(alias["company_id"])].append(AliasInterval(
            ticker=str(alias["ticker"]),
            valid_from=alias["valid_from"],
            valid_to=alias["valid_to"],
            security_active=bool(alias["active"]),
            current_ticker=str(alias["current_ticker"]),
        ))
    canonical.close()
    for row in rows:
        row.update(quarters[int(row["quarter_id"])])

    histories: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        histories[int(row["company_id"])].append(row)
    for history in histories.values():
        history.sort(key=lambda item: int(item.get("fiscal_sequence") or -1))
        prior_confirmed = None
        tenure = 0
        for row in history:
            current = row.get("lifecycle") if row.get("lifecycle_status") == "LIFECYCLE_READY" else None
            row["recent_lifecycle_transition"] = bool(current and prior_confirmed and current != prior_confirmed)
            if current is None:
                row["lifecycle_tenure"] = None
            elif current == prior_confirmed:
                tenure += 1
                row["lifecycle_tenure"] = tenure
            else:
                tenure = 1
                row["lifecycle_tenure"] = tenure
            if current:
                prior_confirmed = current
            row["pending_lifecycle_candidate"] = bool(row.get("candidate_state") and int(row.get("candidate_count") or 0) == 1)
    return rows, aliases, company_status


class MarketReader:
    def __init__(self, path: Path):
        self.connection = readonly(path)
        self.cache: dict[str, dict[str, PriceBar]] = {}

    def close(self) -> None:
        self.connection.close()

    def bars(self, ticker: str) -> dict[str, PriceBar]:
        ticker = ticker.upper()
        if ticker not in self.cache:
            values: dict[str, PriceBar] = {}
            for row in self.connection.execute(
                "SELECT pvm,open,high,low,close FROM osakedata INDEXED BY idx_osake_pvm WHERE osake=? AND market='usa' ORDER BY pvm",
                (ticker,),
            ):
                raw = (row["open"], row["high"], row["low"], row["close"])
                if valid_bar(raw):
                    values[str(row["pvm"])] = PriceBar(str(row["pvm"]), *(float(value) for value in raw))
            self.cache[ticker] = values
        return self.cache[ticker]


def load_action_evidence(path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = readonly(path)
    actions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        "SELECT date,action,ticker,name,value,contraticker,contraname FROM sharadar_action_metadata ORDER BY ticker,date,action"
    ):
        actions[str(row["ticker"]).upper()].append(dict(row))
    conn.close()
    return actions


def build_research_rows(
    paths: ResearchPaths,
    *,
    entry_session_number: int = 0,
    include_phase12a_reconciliation: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    endpoints, aliases, company_status = load_endpoint_features(paths)
    actions = load_action_evidence(paths.provider_db)
    market = MarketReader(paths.market_db)
    benchmark = market.bars("SPY")
    sessions = sorted(benchmark)
    output = []
    for endpoint in endpoints:
        ticker, identity_status = resolve_ticker(
            str(endpoint["source_availability_date"]), aliases.get(int(endpoint["company_id"]), [])
        ) if endpoint.get("source_availability_date") else (None, "MISSING_AVAILABILITY_DATE")
        company_bars = market.bars(ticker) if ticker else {}
        row = dict(endpoint)
        row.update({
            "ticker": ticker,
            "identity_status": identity_status,
            "company_status": company_status.get(int(endpoint["company_id"])),
            "action_evidence": actions.get(ticker or "", []),
        })
        for horizon in (21, 42, 63):
            if ticker is None:
                label = ForwardLabel(horizon, "UNRESOLVED_IDENTITY")
            else:
                label = construct_forward_label(
                    signal_date=endpoint.get("source_availability_date"),
                    horizon=horizon,
                    benchmark_sessions=sessions,
                    benchmark_bars=benchmark,
                    company_bars=company_bars,
                    entry_session_number=entry_session_number,
                )
            for field, value in asdict(label).items():
                row[f"h{horizon}_{field}"] = value
            if include_phase12a_reconciliation:
                if ticker is None:
                    phase12a = ForwardLabel(horizon, "UNRESOLVED_IDENTITY")
                else:
                    phase12a = construct_forward_label(
                        signal_date=endpoint.get("source_availability_date"),
                        horizon=horizon,
                        benchmark_sessions=sessions,
                        benchmark_bars=benchmark,
                        company_bars=company_bars,
                        entry_session_number=1,
                    )
                for field, value in asdict(phase12a).items():
                    row[f"phase12a_h{horizon}_{field}"] = value
        row["entry_date"] = row.get("h63_entry_date") or row.get("h21_entry_date")
        output.append(row)
    market.close()
    return output, sessions


def source_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    fields = (
        "company_id", "quarter_id", "source_availability_date", "fundamental_score",
        "valuation_score", "two_quarter_delta", "component_fundamental_trajectory",
        "lifecycle", "diagnostic_flag_count",
    )
    return stable_hash([{field: row.get(field) for field in fields} for row in rows])
