from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.fundamentals.lifecycle.engine import (
    MODEL_FINGERPRINT,
    MODEL_VERSION,
    TTM_MODEL_VERSION,
    LifecycleObservation,
    RawLifecycleResult,
    StateMachineResult,
    classify_raw_state,
    replay_state_machine,
)


PIT_MODE = "PIT"
REVISED_MODE = "REVISED_HISTORY"
PERSISTENCE_SCHEMA_VERSION = "V4_LIFECYCLE_PIT_1"
REPLAY_MODES = (PIT_MODE, REVISED_MODE)

LIFECYCLE_PIT_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS lifecycle_persistence_schema (
    component TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lifecycle_pit_result (
    result_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    quarter_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_sequence INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    knowledge_date TEXT NOT NULL,
    source_input_fingerprint TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    replay_mode TEXT NOT NULL CHECK (replay_mode IN ('{PIT_MODE}','{REVISED_MODE}')),
    raw_state TEXT NOT NULL,
    final_state TEXT,
    lifecycle_status TEXT NOT NULL,
    startup_profile TEXT,
    final_startup_profile TEXT,
    reason_code TEXT NOT NULL,
    transition_reason TEXT NOT NULL,
    missing_inputs_json TEXT NOT NULL,
    last_confirmed_state TEXT,
    candidate_state TEXT,
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    revenue_growth_yoy_ttm REAL,
    ebit_margin_ttm REAL,
    ebit_margin_direction REAL,
    fcf_margin_ttm REAL,
    evidence_json TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    UNIQUE(company_id, fiscal_sequence, knowledge_date, source_input_fingerprint, model_fingerprint, replay_mode)
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_pit_current
    ON lifecycle_pit_result(company_id, model_fingerprint, replay_mode, knowledge_date DESC, fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_pit_asof
    ON lifecycle_pit_result(company_id, model_fingerprint, replay_mode, knowledge_date, fiscal_sequence);
CREATE INDEX IF NOT EXISTS idx_lifecycle_pit_quarter_audit
    ON lifecycle_pit_result(company_id, fiscal_sequence, model_fingerprint, replay_mode, knowledge_date, result_id);
"""


def _hash_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fiscal_sequence(fiscal_year: int, fiscal_quarter: str) -> int:
    try:
        quarter = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}[fiscal_quarter]
    except KeyError as exc:
        raise ValueError("LIFECYCLE_FISCAL_QUARTER_INVALID") from exc
    return fiscal_year * 4 + quarter


@dataclass(frozen=True)
class LifecycleQuarterVersion:
    company_id: int
    security_id: int | None
    quarter_id: int
    fiscal_year: int
    fiscal_quarter: str
    period_end: str
    knowledge_date: str
    source_version: str
    source_fingerprint: str
    revenue: float | None
    ebit: float | None
    free_cashflow: float | None
    cash: float | None = None
    total_debt: float | None = None
    shares_outstanding: float | None = None
    canonical_precedence: int = 0

    @property
    def fiscal_sequence(self) -> int:
        return fiscal_sequence(self.fiscal_year, self.fiscal_quarter)


@dataclass(frozen=True)
class KnowledgeBatch:
    company_id: int
    knowledge_date: str
    batch_id: str
    quarter_versions: tuple[LifecycleQuarterVersion, ...]


@dataclass(frozen=True)
class LifecyclePersistableResult:
    result_id: str
    batch_id: str
    company_id: int
    security_id: int | None
    quarter_id: int
    fiscal_year: int
    fiscal_quarter: str
    fiscal_sequence: int
    period_end: str
    knowledge_date: str
    source_input_fingerprint: str
    model_version: str
    model_fingerprint: str
    replay_mode: str
    raw_state: str
    final_state: str | None
    lifecycle_status: str
    startup_profile: str | None
    final_startup_profile: str | None
    reason_code: str
    transition_reason: str
    missing_inputs_json: str
    last_confirmed_state: str | None
    candidate_state: str | None
    candidate_count: int
    revenue_growth_yoy_ttm: float | None
    ebit_margin_ttm: float | None
    ebit_margin_direction: float | None
    fcf_margin_ttm: float | None
    evidence_json: str
    generated_at_utc: str


def _validate_version(version: LifecycleQuarterVersion) -> None:
    fiscal_sequence(version.fiscal_year, version.fiscal_quarter)
    for value, code in (
        (version.period_end, "LIFECYCLE_PERIOD_END_INVALID"),
        (version.knowledge_date, "LIFECYCLE_KNOWLEDGE_DATE_INVALID"),
    ):
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(code) from exc
    if not version.source_fingerprint:
        raise ValueError("LIFECYCLE_SOURCE_FINGERPRINT_REQUIRED")
    if not version.source_version:
        raise ValueError("LIFECYCLE_SOURCE_VERSION_REQUIRED")


def build_knowledge_batches(versions: Iterable[LifecycleQuarterVersion]) -> tuple[KnowledgeBatch, ...]:
    grouped: dict[tuple[int, str], list[LifecycleQuarterVersion]] = defaultdict(list)
    for version in versions:
        _validate_version(version)
        grouped[(version.company_id, version.knowledge_date)].append(version)

    batches: list[KnowledgeBatch] = []
    for (company_id, knowledge_date), rows in grouped.items():
        by_sequence: dict[int, list[LifecycleQuarterVersion]] = defaultdict(list)
        for row in rows:
            by_sequence[row.fiscal_sequence].append(row)
        winners: list[LifecycleQuarterVersion] = []
        for sequence, candidates in sorted(by_sequence.items()):
            identities = {
                (row.fiscal_year, row.fiscal_quarter, row.period_end, row.quarter_id)
                for row in candidates
            }
            if len(identities) != 1:
                raise ValueError("LIFECYCLE_CANONICAL_QUARTER_IDENTITY_AMBIGUOUS")
            highest = max(row.canonical_precedence for row in candidates)
            finalists = [row for row in candidates if row.canonical_precedence == highest]
            fingerprints = {row.source_fingerprint for row in finalists}
            if len(fingerprints) != 1:
                raise ValueError("LIFECYCLE_CANONICAL_WINNER_AMBIGUOUS")
            winner = sorted(finalists, key=lambda row: (row.source_fingerprint, row.source_version))[0]
            winners.append(winner)
        batch_payload = {
            "company_id": company_id,
            "knowledge_date": knowledge_date,
            "quarters": [
                {
                    "fiscal_sequence": row.fiscal_sequence,
                    "source_fingerprint": row.source_fingerprint,
                    "canonical_precedence": row.canonical_precedence,
                }
                for row in winners
            ],
        }
        batches.append(
            KnowledgeBatch(
                company_id=company_id,
                knowledge_date=knowledge_date,
                batch_id=_hash_json(batch_payload),
                quarter_versions=tuple(winners),
            )
        )
    return tuple(sorted(batches, key=lambda batch: (batch.company_id, batch.knowledge_date, batch.batch_id)))


def _sum_window(
    known: Mapping[int, LifecycleQuarterVersion],
    sequences: Sequence[int],
    field: str,
) -> float | None:
    rows = [known.get(sequence) for sequence in sequences]
    if any(row is None or getattr(row, field) is None for row in rows):
        return None
    return sum(float(getattr(row, field)) for row in rows if row is not None)


def _observation(
    endpoint: LifecycleQuarterVersion,
    known: Mapping[int, LifecycleQuarterVersion],
    knowledge_date: str,
) -> tuple[LifecycleObservation, str, dict[str, Any]]:
    sequence = endpoint.fiscal_sequence
    current_sequences = tuple(range(sequence - 3, sequence + 1))
    lag_sequences = tuple(range(sequence - 7, sequence - 3))
    current_rows = tuple(known.get(item) for item in current_sequences)
    all_current_present = all(row is not None for row in current_rows)
    current_revenues = tuple(row.revenue if row is not None else None for row in current_rows)
    ttm_revenue = _sum_window(known, current_sequences, "revenue")
    ttm_ebit = _sum_window(known, current_sequences, "ebit")
    ttm_fcf = _sum_window(known, current_sequences, "free_cashflow")
    endpoint_core_instant_ready = all(
        value is not None for value in (endpoint.cash, endpoint.total_debt, endpoint.shares_outstanding)
    )
    core_ready = all_current_present and all(
        value is not None for value in (ttm_revenue, ttm_ebit, ttm_fcf)
    ) and endpoint_core_instant_ready
    lag_chain_valid = all(sequence_item in known for sequence_item in range(sequence - 7, sequence + 1))
    lag_revenue = _sum_window(known, lag_sequences, "revenue") if lag_chain_valid else None
    lag_ebit = _sum_window(known, lag_sequences, "ebit") if lag_chain_valid else None
    evidence_versions = [
        {
            "fiscal_sequence": item,
            "quarter_id": known[item].quarter_id,
            "source_version": known[item].source_version,
            "source_fingerprint": known[item].source_fingerprint,
        }
        for item in range(min(known), sequence + 1)
        if item in known
    ]
    source_input_fingerprint = _hash_json(
        {
            "endpoint_fiscal_sequence": sequence,
            "knowledge_date": knowledge_date,
            "versions_through_endpoint": evidence_versions,
            "ttm_model_version": TTM_MODEL_VERSION,
        }
    )
    observation = LifecycleObservation(
        company_id=endpoint.company_id,
        security_id=endpoint.security_id,
        endpoint_quarter_id=endpoint.quarter_id,
        endpoint_fiscal_year=endpoint.fiscal_year,
        endpoint_fiscal_quarter=endpoint.fiscal_quarter,
        period_end=endpoint.period_end,
        source_available_date=knowledge_date,
        source_data_version=source_input_fingerprint,
        core_ttm_ready=core_ready,
        ttm_revenue=ttm_revenue,
        ttm_ebit=ttm_ebit,
        ttm_free_cashflow=ttm_fcf,
        lag4_ttm_revenue=lag_revenue,
        lag4_ttm_ebit=lag_ebit,
        lag4_chain_valid=lag_chain_valid,
        input_quarter_revenues=current_revenues,
    )
    evidence = {
        "current_ttm_sequences": current_sequences,
        "lag4_ttm_sequences": lag_sequences,
        "core_instant_ready": endpoint_core_instant_ready,
        "input_quarter_revenues": current_revenues,
        "source_versions_through_endpoint": evidence_versions,
    }
    return observation, source_input_fingerprint, evidence


def _persistable(
    machine_result: StateMachineResult,
    batch: KnowledgeBatch,
    source_input_fingerprint: str,
    evidence: Mapping[str, Any],
    replay_mode: str,
    generated_at_utc: str,
) -> LifecyclePersistableResult:
    raw = machine_result.raw_result
    observation = raw.observation
    sequence = fiscal_sequence(observation.endpoint_fiscal_year, observation.endpoint_fiscal_quarter)
    identity = {
        "batch_id": batch.batch_id,
        "company_id": observation.company_id,
        "fiscal_sequence": sequence,
        "knowledge_date": batch.knowledge_date,
        "source_input_fingerprint": source_input_fingerprint,
        "model_fingerprint": MODEL_FINGERPRINT,
        "replay_mode": replay_mode,
        "raw_state": raw.raw_state.value,
        "final_state": machine_result.final_state.value if machine_result.final_state else None,
        "lifecycle_status": machine_result.lifecycle_status.value,
        "candidate_state": machine_result.candidate_state.value if machine_result.candidate_state else None,
        "candidate_count": machine_result.candidate_count,
    }
    metrics = raw.metrics
    return LifecyclePersistableResult(
        result_id=_hash_json(identity),
        batch_id=batch.batch_id,
        company_id=observation.company_id,
        security_id=observation.security_id,
        quarter_id=observation.endpoint_quarter_id,
        fiscal_year=observation.endpoint_fiscal_year,
        fiscal_quarter=observation.endpoint_fiscal_quarter,
        fiscal_sequence=sequence,
        period_end=observation.period_end,
        knowledge_date=batch.knowledge_date,
        source_input_fingerprint=source_input_fingerprint,
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        replay_mode=replay_mode,
        raw_state=raw.raw_state.value,
        final_state=machine_result.final_state.value if machine_result.final_state else None,
        lifecycle_status=machine_result.lifecycle_status.value,
        startup_profile=raw.startup_profile.value if raw.startup_profile else None,
        final_startup_profile=(
            machine_result.final_startup_profile.value if machine_result.final_startup_profile else None
        ),
        reason_code=raw.reason_code.value,
        transition_reason=machine_result.transition_reason.value,
        missing_inputs_json=json.dumps(raw.missing_inputs, separators=(",", ":")),
        last_confirmed_state=(
            machine_result.last_confirmed_state.value if machine_result.last_confirmed_state else None
        ),
        candidate_state=machine_result.candidate_state.value if machine_result.candidate_state else None,
        candidate_count=machine_result.candidate_count,
        revenue_growth_yoy_ttm=metrics.revenue_growth_yoy_ttm,
        ebit_margin_ttm=metrics.ebit_margin_ttm,
        ebit_margin_direction=metrics.ebit_margin_direction,
        fcf_margin_ttm=metrics.fcf_margin_ttm,
        evidence_json=json.dumps(
            {
                **dict(evidence),
                "raw_metrics": asdict(metrics),
                "pre_revenue_evidence": {
                    "quarter_revenues": observation.input_quarter_revenues,
                    "ttm_ebit": observation.ttm_ebit,
                    "ttm_free_cashflow": observation.ttm_free_cashflow,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        generated_at_utc=generated_at_utc,
    )


def _replay_known(
    known: Mapping[int, LifecycleQuarterVersion],
    batch: KnowledgeBatch,
    replay_mode: str,
    generated_at_utc: str,
) -> list[LifecyclePersistableResult]:
    raw_results: list[RawLifecycleResult] = []
    evidence_by_sequence: dict[int, tuple[str, dict[str, Any]]] = {}
    for sequence, endpoint in sorted(known.items()):
        observation, source_fingerprint, evidence = _observation(endpoint, known, batch.knowledge_date)
        raw_results.append(classify_raw_state(observation))
        evidence_by_sequence[sequence] = (source_fingerprint, evidence)
    machine_results = replay_state_machine(raw_results)
    output: list[LifecyclePersistableResult] = []
    for machine_result in machine_results:
        sequence = fiscal_sequence(
            machine_result.raw_result.observation.endpoint_fiscal_year,
            machine_result.raw_result.observation.endpoint_fiscal_quarter,
        )
        source_fingerprint, evidence = evidence_by_sequence[sequence]
        output.append(
            _persistable(
                machine_result,
                batch,
                source_fingerprint,
                evidence,
                replay_mode,
                generated_at_utc,
            )
        )
    return output


def replay_pit_versions(
    versions: Iterable[LifecycleQuarterVersion],
    *,
    generated_at_utc: str,
) -> tuple[LifecyclePersistableResult, ...]:
    batches = build_knowledge_batches(versions)
    by_company: dict[int, list[KnowledgeBatch]] = defaultdict(list)
    for batch in batches:
        by_company[batch.company_id].append(batch)
    output: list[LifecyclePersistableResult] = []
    for company_id in sorted(by_company):
        known: dict[int, LifecycleQuarterVersion] = {}
        for batch in sorted(by_company[company_id], key=lambda item: (item.knowledge_date, item.batch_id)):
            changed: list[int] = []
            for version in batch.quarter_versions:
                previous = known.get(version.fiscal_sequence)
                if previous is not None and (
                    previous.quarter_id != version.quarter_id
                    or previous.period_end != version.period_end
                    or previous.fiscal_year != version.fiscal_year
                    or previous.fiscal_quarter != version.fiscal_quarter
                ):
                    raise ValueError("LIFECYCLE_CANONICAL_QUARTER_IDENTITY_CHANGED")
                if previous is not None and previous.source_fingerprint == version.source_fingerprint:
                    continue
                known[version.fiscal_sequence] = version
                changed.append(version.fiscal_sequence)
            if not changed:
                continue
            earliest = min(changed)
            replayed = _replay_known(known, batch, PIT_MODE, generated_at_utc)
            output.extend(row for row in replayed if row.fiscal_sequence >= earliest)
    return tuple(output)


def replay_revised_history(
    versions: Iterable[LifecycleQuarterVersion],
    *,
    as_of_date: str,
    generated_at_utc: str,
) -> tuple[LifecyclePersistableResult, ...]:
    date.fromisoformat(as_of_date)
    eligible = [version for version in versions if version.knowledge_date <= as_of_date]
    batches = build_knowledge_batches(eligible)
    latest: dict[tuple[int, int], LifecycleQuarterVersion] = {}
    for batch in batches:
        for version in batch.quarter_versions:
            latest[(version.company_id, version.fiscal_sequence)] = version
    by_company: dict[int, dict[int, LifecycleQuarterVersion]] = defaultdict(dict)
    for (company_id, sequence), version in latest.items():
        by_company[company_id][sequence] = version
    output: list[LifecyclePersistableResult] = []
    for company_id, known in sorted(by_company.items()):
        synthetic = KnowledgeBatch(
            company_id=company_id,
            knowledge_date=as_of_date,
            batch_id=_hash_json(
                {
                    "company_id": company_id,
                    "knowledge_date": as_of_date,
                    "mode": REVISED_MODE,
                    "versions": [known[sequence].source_fingerprint for sequence in sorted(known)],
                }
            ),
            quarter_versions=tuple(known[sequence] for sequence in sorted(known)),
        )
        output.extend(_replay_known(known, synthetic, REVISED_MODE, generated_at_utc))
    return tuple(output)


def ensure_lifecycle_pit_schema(conn: sqlite3.Connection, *, applied_at_utc: str) -> None:
    required_columns = set(LifecyclePersistableResult.__dataclass_fields__)
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_pit_result'"
    ).fetchone()
    if table_exists is not None:
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(lifecycle_pit_result)")}
        if not required_columns <= existing_columns:
            raise ValueError("LIFECYCLE_PERSISTENCE_SCHEMA_COLUMNS_MISMATCH")
    conn.executescript(LIFECYCLE_PIT_SCHEMA_SQL)
    actual_columns = {row[1] for row in conn.execute("PRAGMA table_info(lifecycle_pit_result)")}
    if not required_columns <= actual_columns:
        raise ValueError("LIFECYCLE_PERSISTENCE_SCHEMA_COLUMNS_MISMATCH")
    row = conn.execute(
        "SELECT schema_version FROM lifecycle_persistence_schema WHERE component='LIFECYCLE_PIT'"
    ).fetchone()
    if row is not None and row[0] != PERSISTENCE_SCHEMA_VERSION:
        raise ValueError("LIFECYCLE_PERSISTENCE_SCHEMA_VERSION_MISMATCH")
    conn.execute(
        "INSERT OR IGNORE INTO lifecycle_persistence_schema(component,schema_version,applied_at_utc) VALUES (?,?,?)",
        ("LIFECYCLE_PIT", PERSISTENCE_SCHEMA_VERSION, applied_at_utc),
    )


class LifecycleResultRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def append(self, results: Sequence[LifecyclePersistableResult]) -> dict[str, int]:
        columns = tuple(LifecyclePersistableResult.__dataclass_fields__)
        sql = f"INSERT INTO lifecycle_pit_result ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
        inserted = 0
        duplicates = 0
        revised_versions = 0
        self.conn.execute("SAVEPOINT lifecycle_append")
        try:
            for result in results:
                values = tuple(getattr(result, column) for column in columns)
                try:
                    self.conn.execute(sql, values)
                    inserted += 1
                    if self.conn.execute(
                        """SELECT COUNT(*) FROM lifecycle_pit_result
                           WHERE company_id=? AND fiscal_sequence=? AND model_fingerprint=? AND replay_mode=?""",
                        (
                            result.company_id,
                            result.fiscal_sequence,
                            result.model_fingerprint,
                            result.replay_mode,
                        ),
                    ).fetchone()[0] > 1:
                        revised_versions += 1
                except sqlite3.IntegrityError:
                    existing = self.conn.execute(
                        "SELECT * FROM lifecycle_pit_result WHERE result_id=?", (result.result_id,)
                    ).fetchone()
                    if existing is None:
                        raise
                    identity_columns = tuple(column for column in columns if column != "generated_at_utc")
                    if any(existing[column] != getattr(result, column) for column in identity_columns):
                        raise ValueError("LIFECYCLE_RESULT_ID_COLLISION")
                    duplicates += 1
        except Exception:
            self.conn.execute("ROLLBACK TO lifecycle_append")
            self.conn.execute("RELEASE lifecycle_append")
            raise
        self.conn.execute("RELEASE lifecycle_append")
        return {
            "attempted": len(results),
            "inserted": inserted,
            "duplicate_skipped": duplicates,
            "revised_version": revised_versions,
        }

    def current_pit(self, company_id: int, *, model_fingerprint: str) -> dict[str, Any] | None:
        return self._one(
            """SELECT * FROM lifecycle_pit_result
               WHERE company_id=? AND model_fingerprint=? AND replay_mode=?
               ORDER BY knowledge_date DESC, fiscal_sequence DESC, result_id DESC LIMIT 1""",
            (company_id, model_fingerprint, PIT_MODE),
        )

    def as_of_pit(
        self,
        company_id: int,
        as_of_date: str,
        *,
        model_fingerprint: str,
    ) -> dict[str, Any] | None:
        date.fromisoformat(as_of_date)
        return self._one(
            """SELECT * FROM lifecycle_pit_result
               WHERE company_id=? AND model_fingerprint=? AND replay_mode=? AND knowledge_date<=?
               ORDER BY knowledge_date DESC, fiscal_sequence DESC, result_id DESC LIMIT 1""",
            (company_id, model_fingerprint, PIT_MODE, as_of_date),
        )

    def fiscal_quarter_history(
        self,
        company_id: int,
        fiscal_year: int,
        fiscal_quarter: str,
        *,
        model_fingerprint: str,
        replay_mode: str = PIT_MODE,
    ) -> tuple[dict[str, Any], ...]:
        if replay_mode not in REPLAY_MODES:
            raise ValueError("LIFECYCLE_REPLAY_MODE_INVALID")
        rows = self.conn.execute(
            """SELECT * FROM lifecycle_pit_result
               WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?
                 AND model_fingerprint=? AND replay_mode=?
               ORDER BY knowledge_date, result_id""",
            (company_id, fiscal_year, fiscal_quarter, model_fingerprint, replay_mode),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def _one(self, sql: str, parameters: Sequence[Any]) -> dict[str, Any] | None:
        row = self.conn.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None


def load_canonical_quarter_versions(
    source_db: Path,
    *,
    company_ids: Sequence[int] = (),
    tickers: Sequence[str] = (),
    knowledge_date_to: str | None = None,
) -> tuple[LifecycleQuarterVersion, ...]:
    uri = f"file:{source_db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT q.company_id, s.security_id, s.current_ticker, q.quarter_id, q.fiscal_year,
                      q.fiscal_quarter, q.period_end, q.source_availability_date,
                      f.revenue, f.ebit, f.free_cashflow, f.cash, f.total_debt, f.shares_outstanding,
                      q.identity_provider, q.updated_at_utc, f.canonical_source_policy
               FROM v4_quarter q
               JOIN v4_quarter_financials f ON f.quarter_id=q.quarter_id
               LEFT JOIN security s ON s.security_id=(
                   SELECT MIN(s2.security_id) FROM security s2 WHERE s2.company_id=q.company_id
               )
               ORDER BY q.company_id, q.fiscal_year,
                        CASE q.fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,
                        q.quarter_id"""
        ).fetchall()
    finally:
        conn.close()
    company_filter = set(company_ids)
    ticker_filter = {ticker.upper() for ticker in tickers}
    output: list[LifecycleQuarterVersion] = []
    for row in rows:
        if company_filter and int(row["company_id"]) not in company_filter:
            continue
        if ticker_filter and str(row["current_ticker"] or "").upper() not in ticker_filter:
            continue
        available = row["source_availability_date"]
        if not available:
            raise ValueError("LIFECYCLE_SOURCE_AVAILABILITY_AMBIGUOUS")
        if knowledge_date_to and available > knowledge_date_to:
            continue
        payload = {key: row[key] for key in row.keys()}
        source_fingerprint = _hash_json(payload)
        output.append(
            LifecycleQuarterVersion(
                company_id=int(row["company_id"]),
                security_id=int(row["security_id"]) if row["security_id"] is not None else None,
                quarter_id=int(row["quarter_id"]),
                fiscal_year=int(row["fiscal_year"]),
                fiscal_quarter=str(row["fiscal_quarter"]),
                period_end=str(row["period_end"]),
                knowledge_date=str(available),
                source_version=str(row["updated_at_utc"]),
                source_fingerprint=source_fingerprint,
                revenue=row["revenue"],
                ebit=row["ebit"],
                free_cashflow=row["free_cashflow"],
                cash=row["cash"],
                total_debt=row["total_debt"],
                shares_outstanding=row["shares_outstanding"],
            )
        )
    return tuple(output)


def summarize_results(results: Sequence[LifecyclePersistableResult]) -> dict[str, Any]:
    return {
        "computed_results": len(results),
        "status_counts": dict(sorted(Counter(row.lifecycle_status for row in results).items())),
        "class_counts": dict(sorted(Counter(row.final_state or "UNCLASSIFIED" for row in results).items())),
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
    }
