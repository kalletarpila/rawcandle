"""Immutable market-source bundle foundation for Fundamentals rebuilds.

Phase 13G.3.25 deliberately does not route runtime callers through this module.
Taxonomy remains an external source-policy binding until its writer lock is proven
to cover every authoritative mutation path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from rawcandle.datacenter_taxonomy_operation_log import TaxonomyOperationLock
from rawcandle.fundamentals.operating_income_v2.taxonomy_source import (
    load_active_dc_memberships,
)


SOURCE_CONTRACT_VERSION = "FUNDAMENTALS_READ_ONLY_SOURCE_V1"
MARKET_BUNDLE_SCHEMA_VERSION = 1
TTM_MODEL_VERSION = "V4_TTM_EBIT_FIRST_V1"


class ReadOnlySourceMode(str, Enum):
    STABLE_SOURCE_BUNDLE = "STABLE_SOURCE_BUNDLE"
    FULL_SQLITE_BACKUP = "FULL_SQLITE_BACKUP"


class TaxonomySourceMode(str, Enum):
    DIRECT_LOCKED_READ = "DIRECT_LOCKED_READ"
    FULL_SQLITE_BACKUP = "FULL_SQLITE_BACKUP"


@dataclass(frozen=True)
class SourceReadDependency:
    reader: str
    tables: tuple[str, ...]
    semantics: str


MARKET_READ_CLOSURE = (
    SourceReadDependency(
        "operating_income_v2.rehearsal._load_split_events",
        ("splits_data",),
        "all split rows consumed by V2 score normalization",
    ),
    SourceReadDependency(
        "operating_income_v2.canonical_valuation_source.load_canonical_source",
        ("ticker_meta", "osakedata"),
        "all classifications and latest valid exact-ticker OHLC on/before every V4 TTM availability date",
    ),
    SourceReadDependency(
        "operating_income_v2.peer_source_context._classification_source",
        ("ticker_meta",),
        "all ticker/market/sector/industry rows, including classification fingerprint input",
    ),
    SourceReadDependency(
        "relative_valuation.source.load_relative_valuation_source",
        ("ticker_meta", "osakedata"),
        "classification closure and exact/fallback last-32 OHLC window on/before calculation date",
    ),
    SourceReadDependency(
        "snapshot.v2_assembler._current_price_valuation",
        ("osakedata",),
        "case-insensitive last-32 OHLC window on/before report date",
    ),
    SourceReadDependency(
        "snapshot.v2_scaffold.read_source_state",
        ("ticker_meta", "osakedata"),
        "classification plus complete price count/max evidence for deterministic rebuild-validation sample",
    ),
)


TAXONOMY_READ_CLOSURE = (
    SourceReadDependency(
        "operating_income_v2.taxonomy_source.load_active_dc_memberships",
        ("ec_taxonomy_version", "ec_ecosystem", "ec_entity", "ec_membership"),
        "active dc_ecosystem version, semantic fingerprint, and canonical ticker mapping",
    ),
    SourceReadDependency(
        "operating_income_v2.peer_source_context._taxonomy_source",
        ("ec_taxonomy_version", "ec_ecosystem", "ec_entity", "ec_membership"),
        "active taxonomy graph, ticker identity mapping, and peer fingerprint",
    ),
    SourceReadDependency(
        "snapshot.v2_scaffold taxonomy readers",
        ("ec_taxonomy_version", "ec_ecosystem", "ec_entity", "ec_membership"),
        "active version source-state evidence and active membership presentation",
    ),
)


class SourceBundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaxonomySourceBinding:
    mode: str
    source_path: str
    domain: str
    version: str
    semantic_fingerprint: str
    membership_rows: int
    lock_path: str | None
    lock_contract_status: str
    runtime_authorized: bool
    packaged: bool = False


@dataclass(frozen=True)
class StableReadOnlySourceBundle:
    market_db: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    extraction_seconds: float

    @property
    def source_contract_version(self) -> str:
        return str(self.manifest["source_contract_version"])

    @property
    def semantic_fingerprint(self) -> str:
        return str(self.manifest["market"]["semantic_fingerprint"])


Hook = Callable[[str, Mapping[str, Any]], None]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _readonly(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise SourceBundleError(f"READ_ONLY_SOURCE_NOT_REGULAR_ABSOLUTE_FILE:{path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table}")'))


def _require_columns(
    connection: sqlite3.Connection, table: str, required: Sequence[str]
) -> tuple[str, ...]:
    columns = _columns(connection, table)
    if not columns:
        raise SourceBundleError(f"READ_ONLY_SOURCE_TABLE_MISSING:{table}")
    missing = sorted(set(required) - set(columns))
    if missing:
        raise SourceBundleError(
            f"READ_ONLY_SOURCE_SCHEMA_UNSUPPORTED:{table}:{','.join(missing)}"
        )
    return columns


def _file_identity(path: Path) -> dict[str, int]:
    value = path.stat()
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
    }


def _source_pragmas(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
        "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
        "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
        "application_id": int(connection.execute("PRAGMA application_id").fetchone()[0]),
    }


def _canonical_requirements(
    canonical_db: Path, as_of_date: str
) -> dict[str, Any]:
    with _readonly(canonical_db) as connection:
        _require_columns(
            connection,
            "security",
            ("security_id", "company_id", "current_ticker", "active"),
        )
        _require_columns(
            connection,
            "v4_ttm_values",
            (
                "ttm_id",
                "company_id",
                "security_id",
                "ttm_source_available_date",
                "model_version",
                "endpoint_fiscal_year",
                "endpoint_fiscal_quarter",
            ),
        )
        valuation = [
            dict(row)
            for row in connection.execute(
                """SELECT t.ttm_id,t.company_id,t.security_id,s.current_ticker AS ticker,
                          t.ttm_source_available_date AS cutoff
                     FROM v4_ttm_values t
                     LEFT JOIN security s ON s.security_id=t.security_id
                                          AND s.company_id=t.company_id
                    WHERE t.model_version=?
                    ORDER BY t.company_id,t.endpoint_fiscal_year,
                      CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2
                           WHEN 'Q3' THEN 3 ELSE 4 END,t.ttm_id""",
                (TTM_MODEL_VERSION,),
            )
        ]
        recent_tickers = sorted(
            {
                str(row["ticker"])
                for row in valuation
                if row["ticker"] is not None
                and row["cutoff"] is not None
                and str(row["cutoff"]) <= as_of_date
            }
        )
        sample = connection.execute(
            """SELECT s.current_ticker
                 FROM security s JOIN v4_ttm_values t USING(company_id)
                WHERE s.active=1 AND t.model_version=?
                  AND t.ttm_source_available_date<=?
                ORDER BY s.company_id,t.endpoint_fiscal_year DESC,
                         t.endpoint_fiscal_quarter DESC LIMIT 1""",
            (TTM_MODEL_VERSION, as_of_date),
        ).fetchone()
    payload = {
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "as_of_date": as_of_date,
        "valuation_requirements": valuation,
        "recent_tickers": recent_tickers,
        "validation_sample_ticker": str(sample[0]) if sample else None,
    }
    return {**payload, "semantic_fingerprint": _fingerprint(payload)}


def _normalized_market_projection(
    market_db: Path, requirements: Mapping[str, Any]
) -> dict[str, Any]:
    with _readonly(market_db) as connection:
        ticker_columns = _require_columns(
            connection, "ticker_meta", ("ticker", "sector", "industry")
        )
        _require_columns(
            connection,
            "osakedata",
            ("id", "osake", "pvm", "open", "high", "low", "close"),
        )
        _require_columns(
            connection,
            "splits_data",
            ("osake", "split_date", "split_ratio", "is_price_data_corrected"),
        )
        market_expr = "market" if "market" in ticker_columns else "'usa' AS market"
        ticker_meta = [
            dict(row)
            for row in connection.execute(
                f"SELECT ticker,{market_expr},sector,industry FROM ticker_meta ORDER BY ticker,market"
            )
        ]
        ticker_keys = [(str(row["ticker"]).upper(), str(row["market"]).lower()) for row in ticker_meta]
        if len(ticker_keys) != len(set(ticker_keys)):
            raise SourceBundleError("READ_ONLY_SOURCE_DUPLICATE_TICKER_META")
        splits = [
            dict(row)
            for row in connection.execute(
                "SELECT osake,split_date,split_ratio,is_price_data_corrected "
                "FROM splits_data ORDER BY osake,split_date"
            )
        ]
        split_keys = [(str(row["osake"]), str(row["split_date"])) for row in splits]
        if len(split_keys) != len(set(split_keys)):
            raise SourceBundleError("READ_ONLY_SOURCE_DUPLICATE_SPLIT")
        selected: dict[int, dict[str, Any]] = {}
        valuation_coverage: list[dict[str, Any]] = []
        ticker_forms: dict[str, list[str]] = {}
        for row in connection.execute(
            "SELECT DISTINCT osake FROM osakedata WHERE osake IS NOT NULL ORDER BY osake"
        ):
            value = str(row[0])
            ticker_forms.setdefault(value.upper(), []).append(value)
        relevant_folded_tickers = {
            str(row["ticker"]).upper()
            for row in requirements["valuation_requirements"]
            if row["ticker"] is not None
        } | {str(ticker).upper() for ticker in requirements["recent_tickers"]}
        if requirements["validation_sample_ticker"]:
            relevant_folded_tickers.add(
                str(requirements["validation_sample_ticker"]).upper()
            )
        for folded in sorted(relevant_folded_tickers):
            forms = ticker_forms.get(folded, ())
            if len(forms) < 2:
                continue
            by_date: dict[str, tuple[Any, ...]] = {}
            for source_ticker in forms:
                for row in connection.execute(
                    "SELECT pvm,open,high,low,close FROM osakedata "
                    "WHERE osake=? AND pvm<=? ORDER BY pvm",
                    (source_ticker, requirements["as_of_date"]),
                ):
                    date_key = str(row["pvm"])
                    values = tuple(row[column] for column in ("open", "high", "low", "close"))
                    prior = by_date.get(date_key)
                    if prior is not None and prior != values:
                        raise SourceBundleError(
                            f"READ_ONLY_SOURCE_CASEFOLD_PRICE_CONFLICT:{folded}:{date_key}"
                        )
                    by_date[date_key] = values

        def retain(rows: Sequence[sqlite3.Row]) -> None:
            for row in rows:
                item = dict(row)
                row_id = int(item["id"])
                prior = selected.get(row_id)
                if prior is not None and prior != item:
                    raise SourceBundleError(f"MARKET_PRICE_ID_NOT_STABLE:{row_id}")
                selected[row_id] = item

        price_columns = "id,osake,pvm,open,high,low,close"
        valuation_cache: dict[tuple[str, str], sqlite3.Row | None] = {}
        for requirement in requirements["valuation_requirements"]:
            ticker = requirement["ticker"]
            cutoff = requirement["cutoff"]
            row: sqlite3.Row | None = None
            if ticker is None:
                status = "NO_TICKER"
            elif cutoff is None:
                status = "NO_CUTOFF"
            else:
                status = "NO_MATCHING_VALID_PRICE"
            if ticker is not None and cutoff is not None:
                key = (str(ticker), str(cutoff))
                if key not in valuation_cache:
                    valuation_cache[key] = connection.execute(
                        f"""SELECT {price_columns} FROM osakedata
                             WHERE osake=? AND pvm<=?
                               AND open>0 AND high>0 AND low>0 AND close>0
                               AND high>=MAX(open,close,low)
                               AND low<=MIN(open,close,high)
                             ORDER BY pvm DESC LIMIT 1""",
                        key,
                    ).fetchone()
                row = valuation_cache[key]
                if row is not None:
                    status = "PRICE_FOUND"
            if row is not None:
                retain((row,))
            valuation_coverage.append(
                {
                    "ttm_id": int(requirement["ttm_id"]),
                    "status": status,
                    "price_id": int(row["id"]) if row else None,
                }
            )
        for ticker in requirements["recent_tickers"]:
            for source_ticker in ticker_forms.get(ticker.upper(), ()):
                retain(
                    list(
                        connection.execute(
                            f"SELECT {price_columns} FROM osakedata WHERE osake=? AND pvm<=? "
                            "ORDER BY pvm DESC LIMIT 32",
                            (source_ticker, requirements["as_of_date"]),
                        )
                    )
                )
        sample = requirements["validation_sample_ticker"]
        if sample:
            for source_ticker in ticker_forms.get(str(sample).upper(), ()):
                retain(
                    list(
                        connection.execute(
                            f"SELECT {price_columns} FROM osakedata WHERE osake=? ORDER BY id",
                            (source_ticker,),
                        )
                    )
                )
        rows = [selected[key] for key in sorted(selected)]
        pragmas = _source_pragmas(connection)
    semantic_payload = {
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "as_of_date": requirements["as_of_date"],
        "canonical_binding": requirements["semantic_fingerprint"],
        "ticker_meta": ticker_meta,
        "splits_data": splits,
        "osakedata": rows,
        "valuation_coverage": valuation_coverage,
    }
    return {
        **semantic_payload,
        "semantic_fingerprint": _fingerprint(semantic_payload),
        "source_pragmas": pragmas,
    }


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = [
        list(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE sql IS NOT NULL ORDER BY type,name,tbl_name"
        )
    ]
    return _fingerprint(rows)


def _write_market_bundle(path: Path, projection: Mapping[str, Any]) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE source_bundle_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                source_contract_version TEXT NOT NULL,
                market_bundle_schema_version INTEGER NOT NULL,
                as_of_date TEXT NOT NULL,
                canonical_binding TEXT NOT NULL,
                semantic_fingerprint TEXT NOT NULL
            );
            CREATE TABLE ticker_meta(
                ticker TEXT NOT NULL,
                market TEXT,
                sector TEXT,
                industry TEXT
            );
            CREATE TABLE osakedata(
                id INTEGER PRIMARY KEY,
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL
            );
            CREATE TABLE splits_data(
                osake TEXT NOT NULL,
                split_date TEXT NOT NULL,
                split_ratio REAL,
                is_price_data_corrected INTEGER
            );
            CREATE INDEX idx_source_bundle_ticker_meta ON ticker_meta(ticker,market);
            CREATE INDEX idx_source_bundle_price_ticker_date ON osakedata(osake,pvm DESC);
            CREATE INDEX idx_source_bundle_split_ticker_date ON splits_data(osake,split_date);
            """
        )
        connection.execute(
            "INSERT INTO source_bundle_meta VALUES (1,?,?,?,?,?)",
            (
                SOURCE_CONTRACT_VERSION,
                MARKET_BUNDLE_SCHEMA_VERSION,
                projection["as_of_date"],
                projection["canonical_binding"],
                projection["semantic_fingerprint"],
            ),
        )
        connection.executemany(
            "INSERT INTO ticker_meta(ticker,market,sector,industry) VALUES (?,?,?,?)",
            [
                (row["ticker"], row["market"], row["sector"], row["industry"])
                for row in projection["ticker_meta"]
            ],
        )
        connection.executemany(
            "INSERT INTO osakedata(id,osake,pvm,open,high,low,close) VALUES (?,?,?,?,?,?,?)",
            [
                (
                    row["id"], row["osake"], row["pvm"], row["open"],
                    row["high"], row["low"], row["close"],
                )
                for row in projection["osakedata"]
            ],
        )
        connection.executemany(
            "INSERT INTO splits_data(osake,split_date,split_ratio,is_price_data_corrected) VALUES (?,?,?,?)",
            [
                (
                    row["osake"], row["split_date"], row["split_ratio"],
                    row["is_price_data_corrected"],
                )
                for row in projection["splits_data"]
            ],
        )
        connection.commit()
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SourceBundleError("MARKET_BUNDLE_QUICK_CHECK_FAILED")
        schema_fingerprint = _schema_fingerprint(connection)
    return {
        "schema_fingerprint": schema_fingerprint,
        "row_counts": {
            "ticker_meta": len(projection["ticker_meta"]),
            "osakedata": len(projection["osakedata"]),
            "splits_data": len(projection["splits_data"]),
        },
    }


def _manifest_projection(path: Path) -> dict[str, Any]:
    with _readonly(path) as connection:
        meta = dict(connection.execute("SELECT * FROM source_bundle_meta").fetchone())
        ticker_meta = [
            dict(row)
            for row in connection.execute(
                "SELECT ticker,market,sector,industry FROM ticker_meta ORDER BY ticker,market"
            )
        ]
        splits = [
            dict(row)
            for row in connection.execute(
                "SELECT osake,split_date,split_ratio,is_price_data_corrected "
                "FROM splits_data ORDER BY osake,split_date"
            )
        ]
        prices = [
            dict(row)
            for row in connection.execute(
                "SELECT id,osake,pvm,open,high,low,close FROM osakedata ORDER BY id"
            )
        ]
    return {
        "meta": meta,
        "ticker_meta": ticker_meta,
        "splits_data": splits,
        "osakedata": prices,
    }


def validate_stable_read_only_source_bundle(bundle: StableReadOnlySourceBundle) -> None:
    manifest = bundle.manifest
    if manifest.get("source_contract_version") != SOURCE_CONTRACT_VERSION:
        raise SourceBundleError("SOURCE_BUNDLE_CONTRACT_VERSION_UNSUPPORTED")
    market = manifest["market"]
    projection = _manifest_projection(bundle.market_db)
    meta = projection["meta"]
    if meta["semantic_fingerprint"] != market["semantic_fingerprint"]:
        raise SourceBundleError("SOURCE_BUNDLE_EMBEDDED_FINGERPRINT_MISMATCH")
    counts = {
        "ticker_meta": len(projection["ticker_meta"]),
        "osakedata": len(projection["osakedata"]),
        "splits_data": len(projection["splits_data"]),
    }
    if counts != market["row_counts"]:
        raise SourceBundleError("SOURCE_BUNDLE_ROW_COVERAGE_MISMATCH")
    if _sha256(bundle.market_db) != market["physical_sha256"]:
        raise SourceBundleError("SOURCE_BUNDLE_PHYSICAL_FINGERPRINT_MISMATCH")
    with _readonly(bundle.market_db) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SourceBundleError("SOURCE_BUNDLE_QUICK_CHECK_FAILED")
        if _schema_fingerprint(connection) != market["schema_fingerprint"]:
            raise SourceBundleError("SOURCE_BUNDLE_SCHEMA_FINGERPRINT_MISMATCH")


def bind_taxonomy_source(
    taxonomy_db: Path,
    canonical_db: Path,
    *,
    mode: TaxonomySourceMode = TaxonomySourceMode.FULL_SQLITE_BACKUP,
    operation_lock: TaxonomyOperationLock | None = None,
) -> TaxonomySourceBinding:
    taxonomy_db = taxonomy_db.absolute()
    canonical_db = canonical_db.absolute()
    lock_path: str | None = None
    if mode is TaxonomySourceMode.DIRECT_LOCKED_READ:
        if operation_lock is None:
            raise SourceBundleError("TAXONOMY_AUTHORITATIVE_LOCK_REQUIRED")
        lock_path = operation_lock.lock_path
        path = Path(lock_path)
        if not path.is_file():
            raise SourceBundleError("TAXONOMY_AUTHORITATIVE_LOCK_NOT_ACTIVE")
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceBundleError("TAXONOMY_AUTHORITATIVE_LOCK_UNREADABLE") from exc
        if stored.get("pid") != operation_lock.pid or stored.get("operation_id") != operation_lock.operation_id:
            raise SourceBundleError("TAXONOMY_AUTHORITATIVE_LOCK_IDENTITY_MISMATCH")
    _, dependency = load_active_dc_memberships(taxonomy_db, canonical_db)
    return TaxonomySourceBinding(
        mode=mode.value,
        source_path=str(taxonomy_db.resolve()),
        domain=str(dependency["domain"]),
        version=str(dependency["version"]),
        semantic_fingerprint=str(dependency["semantic_fingerprint"]),
        membership_rows=int(dependency["membership_rows"]),
        lock_path=lock_path,
        lock_contract_status=(
            "LOCK_HELD_BUT_ALL_WRITER_COVERAGE_UNPROVEN"
            if mode is TaxonomySourceMode.DIRECT_LOCKED_READ
            else "FULL_SQLITE_BACKUP_RUNTIME_AUTHORITY"
        ),
        runtime_authorized=mode is TaxonomySourceMode.FULL_SQLITE_BACKUP,
    )


def build_stable_read_only_source_bundle(
    *,
    market_db: Path,
    canonical_db: Path,
    bundle_dir: Path,
    as_of_date: str,
    taxonomy_binding: TaxonomySourceBinding | None = None,
    hook: Hook | None = None,
) -> StableReadOnlySourceBundle:
    # ISO validation without importing workflow-level date policy.
    from datetime import date

    date.fromisoformat(as_of_date)
    market_db = market_db.absolute()
    canonical_db = canonical_db.absolute()
    bundle_dir = bundle_dir.absolute()
    if bundle_dir.exists():
        raise FileExistsError(bundle_dir)
    started = time.monotonic()
    staging = bundle_dir.with_name(f".{bundle_dir.name}.partial-{uuid.uuid4().hex}")
    market_path = staging / "market.db"
    manifest_path = staging / "manifest.json"
    before_identity = _file_identity(market_db)
    canonical_identity_before = _file_identity(canonical_db)
    try:
        staging.mkdir(parents=True)
        requirements = _canonical_requirements(canonical_db, as_of_date)
        projection = _normalized_market_projection(market_db, requirements)
        if hook:
            hook("AFTER_SOURCE_EXTRACTION", {"market_db": market_db, "staging": staging})
        after_projection = _normalized_market_projection(market_db, requirements)
        after_identity = _file_identity(market_db)
        requirements_after = _canonical_requirements(canonical_db, as_of_date)
        canonical_identity_after = _file_identity(canonical_db)
        if (
            projection["semantic_fingerprint"] != after_projection["semantic_fingerprint"]
            or before_identity["device"] != after_identity["device"]
            or before_identity["inode"] != after_identity["inode"]
        ):
            raise SourceBundleError("READ_ONLY_SOURCE_DRIFT")
        if (
            requirements["semantic_fingerprint"]
            != requirements_after["semantic_fingerprint"]
            or canonical_identity_before["device"] != canonical_identity_after["device"]
            or canonical_identity_before["inode"] != canonical_identity_after["inode"]
        ):
            raise SourceBundleError("SOURCE_BUNDLE_CANONICAL_BINDING_DRIFT")
        written = _write_market_bundle(market_path, projection)
        if hook:
            hook("AFTER_BUNDLE_WRITE", {"market_db": market_db, "staging": staging})
        physical_sha256 = _sha256(market_path)
        coverage_statuses = (
            "PRICE_FOUND", "NO_MATCHING_VALID_PRICE", "NO_TICKER", "NO_CUTOFF"
        )
        coverage_ids = {
            status: sorted(
                int(row["ttm_id"])
                for row in projection["valuation_coverage"]
                if row["status"] == status
            )
            for status in coverage_statuses
        }
        manifest: dict[str, Any] = {
            "source_contract_version": SOURCE_CONTRACT_VERSION,
            "mode": ReadOnlySourceMode.STABLE_SOURCE_BUNDLE.value,
            "as_of_date": as_of_date,
            "canonical_binding": {
                "path": str(canonical_db.resolve()),
                "semantic_fingerprint": requirements["semantic_fingerprint"],
                "valuation_requirement_count": len(requirements["valuation_requirements"]),
                "recent_ticker_count": len(requirements["recent_tickers"]),
                "validation_sample_ticker": requirements["validation_sample_ticker"],
                "source_identity_before": canonical_identity_before,
                "source_identity_after": canonical_identity_after,
            },
            "market": {
                "path": "market.db",
                "semantic_fingerprint": projection["semantic_fingerprint"],
                "physical_sha256": physical_sha256,
                "schema_fingerprint": written["schema_fingerprint"],
                "row_counts": written["row_counts"],
                "valuation_coverage": {
                    "requirements": len(projection["valuation_coverage"]),
                    "status_counts": {
                        status: len(coverage_ids[status]) for status in coverage_statuses
                    },
                    "status_identity_fingerprints": {
                        status: _fingerprint(coverage_ids[status])
                        for status in coverage_statuses
                    },
                },
                "source_identity_before": before_identity,
                "source_identity_after": after_identity,
                "source_pragmas": projection["source_pragmas"],
            },
            "taxonomy": (
                asdict(taxonomy_binding)
                if taxonomy_binding is not None
                else {
                    "packaged": False,
                    "mode": TaxonomySourceMode.FULL_SQLITE_BACKUP.value,
                    "lock_contract_status": "FULL_SQLITE_BACKUP_RUNTIME_AUTHORITY",
                    "runtime_authorized": True,
                }
            ),
            "read_closure": {
                "market": [asdict(item) for item in MARKET_READ_CLOSURE],
                "taxonomy": [asdict(item) for item in TAXONOMY_READ_CLOSURE],
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        candidate = StableReadOnlySourceBundle(
            market_db=market_path,
            manifest_path=manifest_path,
            manifest=manifest,
            extraction_seconds=time.monotonic() - started,
        )
        validate_stable_read_only_source_bundle(candidate)
        os.chmod(market_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.chmod(manifest_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(staging, bundle_dir)
        if hook:
            hook("AFTER_BUNDLE_PUBLISH", {"market_db": market_db, "bundle_dir": bundle_dir})
        final = StableReadOnlySourceBundle(
            market_db=bundle_dir / "market.db",
            manifest_path=bundle_dir / "manifest.json",
            manifest=manifest,
            extraction_seconds=time.monotonic() - started,
        )
        validate_stable_read_only_source_bundle(final)
        return final
    except Exception:
        for disposable in (staging, bundle_dir):
            if disposable.exists():
                for path in disposable.rglob("*"):
                    if path.is_file():
                        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                shutil.rmtree(disposable)
        raise
