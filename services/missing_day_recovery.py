"""One-day, insert-only administration using the existing stock-update transport.

No downstream analysis, split backfill, new transport, retries or rate limiter.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from rawcandle.io_atomic import write_text_atomic
from services import stock_update_service as update

ROOT = Path(__file__).resolve().parents[1]
# Used only as session evidence; these instruments never expand the stock universe.
CALENDARS = {
    "usa": ("^GSPC", "America/New_York"),
    "omxh": ("^OMXH25", "Europe/Helsinki"),
    "omxs": ("^OMXS30", "Europe/Stockholm"),
    "xetra": ("^GDAXI", "Europe/Berlin"),
}
BAR_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass
class MissingDayResult:
    date: str
    market: str
    status: str = "failed"
    tickers_examined: int = 0
    missing_candidates: int = 0
    skipped_existing: int = 0
    inserted_rows: int = 0
    legitimately_unavailable: int = 0
    unavailable_records: int = 0
    identity_adjustment_holds: int = 0
    provider_failures: int = 0
    database_failures: int = 0
    remaining_missing_rows: int = 0
    existing_rows_modified: int = 0
    existing_rows_deleted: int = 0
    outside_market_date_inserted: int = 0
    writes_verified: bool = False
    report_path: str = ""
    backup: dict = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@contextmanager
def readonly(path: Path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        yield conn


def validate_date(value: str, today: date | None = None) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise ValueError("Päivämäärän muoto on YYYY-MM-DD")
    selected = date.fromisoformat(value)
    today = today or datetime.now(ZoneInfo("Europe/Helsinki")).date()
    if selected >= today:
        raise ValueError("Valitse päättynyt päivä; tänään tai tulevaisuudessa olevaa päivää ei haeta")
    if selected.weekday() >= 5:
        raise ValueError("Valittu päivä ei ole pörssipäivä")
    return selected


@contextmanager
def stock_update_operation_lock(db_path: str | Path):
    """Reuse the scheduler lock without changing scheduler state or configuration."""
    from rawcandle.scheduler.runner import acquire_scheduler_lock, release_scheduler_lock
    db_path = Path(db_path).resolve()
    log_dir = db_path.parent / "logs"
    config_path = ROOT / "scheduler_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        if Path(config["osakedata_db_path"]).resolve() == db_path:
            log_dir = Path(config["log_dir"])
    handle = acquire_scheduler_lock(str(log_dir))
    try:
        yield
    finally:
        release_scheduler_lock(handle)


def valid_bar(bar: dict | None) -> bool:
    if not bar:
        return False
    try:
        o, h, l, c, v = [float(bar[k]) for k in BAR_FIELDS]
        return (all(math.isfinite(x) and x > 0 for x in (o, h, l, c))
                and math.isfinite(v) and v >= 0 and l <= min(o, c) <= max(o, c) <= h)
    except (KeyError, ValueError, TypeError):
        return False


def same_basis(stored: dict, fetched: dict) -> bool:
    # Numerical tolerance only. No empirical scaling or adjustment transformation.
    return valid_bar(stored) and valid_bar(fetched) and all(
        math.isclose(stored[k], fetched[k], rel_tol=1e-6, abs_tol=1e-6)
        for k in BAR_FIELDS[:4]) and stored["volume"] == fetched["volume"]


class ExistingIdentityEvidence:
    """Read existing evidence as guards, never as the recovery ticker universe."""
    def __init__(self, canonical: Path | None = None, registry: Path | None = None):
        self.canonical = canonical
        self.records = json.loads(registry.read_text())["records"] if registry and registry.exists() else []

    def hold_reason(self, ticker: str, ds: str, left: str, right: str) -> str | None:
        for r in self.records:
            subject, predecessor = r.get("subject_ticker"), r.get("predecessor_ticker")
            effective = r.get("effective_date")
            if subject == ticker:
                if r.get("review_status") != "APPROVED" or not effective:
                    return "IDENTITY_REVIEW_UNRESOLVED"
                if ds < effective:
                    return "TARGET_BEFORE_REVIEWED_SUCCESSOR"
                if left < effective:
                    return "PRE_SUCCESSOR_HISTORY"
            if predecessor == ticker and r.get("review_status") == "APPROVED" and effective and right >= effective:
                return "TARGET_AFTER_REVIEWED_SUCCESSOR" if ds >= effective else "SUCCESSOR_BOUNDARY"
        if not self.canonical:
            return None
        with readonly(self.canonical) as c:
            rows = c.execute("""SELECT s.*,co.status company_status FROM security s
                JOIN company co USING(company_id) WHERE s.current_ticker=?""", (ticker,)).fetchall()
            if len(rows) > 1:
                return "AMBIGUOUS_SECURITY_IDENTITY"
            aliases = c.execute("SELECT * FROM ticker_alias WHERE ticker=?", (ticker,)).fetchall()
            if not rows:
                # A former symbol is not guessed into a current security.
                return "FORMER_TICKER_REQUIRES_REVIEW" if aliases else None
            r = rows[0]
            if r["company_status"] == "RETIRED":
                return "RETIRED_IDENTITY_REQUIRES_REVIEW"
            if not r["exchange"]:
                return "MISSING_EXCHANGE_IDENTITY"
            if r["valid_from"] and ds < r["valid_from"]:
                return "TARGET_BEFORE_SECURITY_START"
            if r["valid_to"] and ds > r["valid_to"]:
                return "TARGET_AFTER_SECURITY_END"
            if r["valid_from"] and left < r["valid_from"]:
                return "BEFORE_SECURITY_START"
            if r["valid_to"] and right > r["valid_to"]:
                return "AFTER_SECURITY_END"
            if any(a["security_id"] != r["security_id"] for a in aliases):
                return "CONFLICTING_TICKER_ALIAS"
            old = c.execute("SELECT * FROM ticker_alias WHERE security_id=? AND ticker<>?",
                            (r["security_id"], ticker)).fetchall()
            if any(not a["valid_to"] or left <= a["valid_to"] for a in old):
                return "UNDATED_OR_CROSSING_ALIAS_BOUNDARY"
        return None


def existing_identity_evidence() -> ExistingIdentityEvidence:
    from rawcandle.fundamentals.generations import resolve_active_generation
    # Missing/malformed established evidence is an explicit error, not ignored.
    canonical = resolve_active_generation(ROOT).role_paths()["canonical"]
    return ExistingIdentityEvidence(canonical, ROOT / "rawcandle/fundamentals/admin/identity_resolutions.json")


def history_rows(stock, ticker: str, market: str, start: str, end: str) -> dict[str, dict]:
    fetched = update.fetch_history_for_date_ranges(
        stock=stock, ticker=ticker,
        date_ranges=[update.StockUpdateDateRange(start, end)])
    rows = update.convert_histories_to_ohlcv_rows(histories=fetched.histories, ticker=ticker, market=market)
    if len({r.date for r in rows}) != len(rows):
        raise ValueError("DUPLICATE_PROVIDER_DATES")
    return {r.date: {k: getattr(r, k) for k in BAR_FIELDS} for r in rows}


def session_verified(conn, market: str, ds: str, stock_factory) -> bool:
    anchor, timezone = CALENDARS[market]
    r = conn.execute("SELECT open,high,low,close,volume FROM osakedata WHERE osake=? AND pvm=? AND market=?",
                     (anchor, ds, market)).fetchone()
    if r and valid_bar(dict(r)):
        return True
    # A missing local calendar anchor is verified through the SAME acquisition path.
    # Empty response is unverified (not asserted to be a holiday).
    try:
        stock = stock_factory(anchor)
        rows = history_rows(stock, anchor, market, ds, (date.fromisoformat(ds)+timedelta(days=1)).isoformat())
        metadata = stock.history_metadata
        return (valid_bar(rows.get(ds)) and metadata.get("symbol") == anchor
                and metadata.get("exchangeTimezoneName") == timezone)
    finally:
        update.sleep_after_legacy_stock_ticker(0)


def insert_validated_rows(db: Path, accepted: list[dict], ds: str, market: str) -> tuple[int, list[dict]]:
    """All accepted keys commit together; existing keys and changed anchors are skipped."""
    changed = []
    with closing(sqlite3.connect(db.resolve().as_uri()+"?mode=rw", uri=True, timeout=30)) as c, c:
        c.row_factory = sqlite3.Row
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='osakedata'").fetchone():
            raise RuntimeError("OHLCV_TABLE_TRIGGERS_REQUIRE_REVIEW")
        unique_key = False
        for idx in c.execute("PRAGMA index_list(osakedata)").fetchall():
            if idx["unique"] and not idx["partial"]:
                columns = [r["name"] for r in c.execute('PRAGMA index_info("'+idx["name"].replace('"','""')+'")')]
                unique_key |= columns == ["osake", "pvm"]
        if not unique_key:
            raise RuntimeError("UNIQUE_TICKER_DATE_CONSTRAINT_REQUIRED")
        for record in accepted:
            ticker = record["ticker"]
            if record["date"] != ds or record["market"] != market or not valid_bar(record["bar"]):
                raise ValueError("OUTSIDE_VALIDATED_MARKET_DATE")
            if c.execute("SELECT 1 FROM osakedata WHERE osake=? AND pvm=?", (ticker, ds)).fetchone():
                changed.append({"ticker": ticker, "status": "existing", "reason": "CONCURRENT_INSERT_SKIPPED"})
                continue
            mismatch = False
            for day, expected in record["anchors"].items():
                row = c.execute("SELECT open,high,low,close,volume FROM osakedata WHERE osake=? AND pvm=? AND market=?",
                                (ticker, day, market)).fetchone()
                mismatch |= row is None or dict(row) != expected
            if mismatch:
                changed.append({"ticker": ticker, "status": "held", "reason": "ANCHOR_CHANGED_BEFORE_WRITE"})
                continue
            c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)",
                      (ticker, ds, *(record["bar"][k] for k in BAR_FIELDS), market))
        # SQLite rolls back all INSERTs on any exception, including commit failure.
    return len(accepted)-len(changed), changed


def verified_backup(db: Path, directory: Path, run_id: str) -> dict:
    from rawcandle.fundamentals.phase13b_foundation import online_backup
    from rawcandle.fundamentals.admin.artifacts import sha256_file
    destination = directory / ("osakedata_missing_day_"+run_id+".db")
    if destination.exists():
        raise FileExistsError(destination)
    result = online_backup(db, destination)
    result.update(temporary=True, operation_id=run_id, state="retained")
    if result["quick_check"] != "ok":
        raise RuntimeError("BACKUP_VERIFICATION_FAILED")
    result["sha256"] = sha256_file(destination)
    result["restore"] = "Stop writers; preserve current DB/WAL/SHM; restore this coherent SQLite backup."
    write_text_atomic(destination.with_suffix(".manifest.json"), json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def verify_committed_rows(db: Path, records: list[dict]) -> None:
    with readonly(db) as c:
        if [r[0] for r in c.execute("PRAGMA integrity_check")] != ["ok"]:
            raise RuntimeError("POST_WRITE_INTEGRITY_FAILED")
        for r in records:
            if r["status"] != "inserted":
                continue
            actual = c.execute("SELECT open,high,low,close,volume,market FROM osakedata WHERE osake=? AND pvm=?",
                               (r["ticker"], r["date"])).fetchone()
            if not actual or dict(actual) != {**r["bar"], "market": r["market"]}:
                raise RuntimeError("POST_WRITE_VALUE_VERIFICATION_FAILED")


def delete_verified_temporary_backup(backup: dict) -> None:
    path = Path(backup["destination"])
    if not backup.get("temporary") or path.name != "osakedata_missing_day_"+backup["operation_id"]+".db":
        raise ValueError("UNRELATED_BACKUP_CLEANUP_REFUSED")
    path.unlink()  # Only this operation's DB and manifest, never WAL/SHM or other backups.
    backup["state"] = "deleted"
    path.with_suffix(".manifest.json").unlink(missing_ok=True)


def run_missing_day_recovery(*, db_path: str | Path, market: str, requested_date: str,
                             stock_factory, report_dir: str | Path, backup_dir: str | Path,
                             identity_evidence=None, progress_callback=None,
                             today: date | None = None) -> MissingDayResult:
    db, report_dir = Path(db_path), Path(report_dir)
    market = (market or "").strip().lower()
    result = MissingDayResult(date=requested_date, market=market)
    run_id = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%S%fZ")+"_"+uuid4().hex[:8]
    result.report_path = str((report_dir/("missing_day_"+run_id+".json")).resolve())
    def save():
        write_text_atomic(Path(result.report_path), json.dumps(asdict(result), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    def emit(event_type, message, index=None, total=None):
        if progress_callback:
            try:
                progress_callback(update.StockUpdateProgressEvent(event_type, message=message, index=index, total=total))
            except Exception:
                pass  # Browser callbacks cannot invalidate persisted results.
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        selected = validate_date(requested_date, today)
        if not market:
            raise ValueError("Valitse yksi markkina puuttuvan päivän hakua varten")
        if market not in CALENDARS:
            raise ValueError("Markkinan pörssipäivää ei voida varmistaa")
        if not db.is_file():
            raise FileNotFoundError(db)
        identity_evidence = identity_evidence or existing_identity_evidence()
        with stock_update_operation_lock(db):
            with readonly(db) as conn:
                if not conn.execute("SELECT 1 FROM markets WHERE abbreviation=?", (market,)).fetchone():
                    raise ValueError("Tuntematon markkina")
                # Established universe/market selection, unchanged; no Fundamentals filtering.
                candidates = update.load_stock_update_candidates_for_market(str(db), market)
                result.tickers_examined = len(candidates)
                records = []
                for candidate in candidates:
                    ticker = candidate.ticker
                    existing = conn.execute("SELECT market FROM osakedata WHERE osake=? AND pvm=?", (ticker, requested_date)).fetchone()
                    record = {"ticker": ticker, "date": requested_date, "market": market}
                    if existing:
                        if existing["market"] == market:
                            result.skipped_existing += 1
                            record.update(status="existing", reason="NO_OVERWRITE")
                        else:
                            result.missing_candidates += 1
                            record.update(status="held", reason="EXISTING_KEY_OTHER_MARKET")
                    else:
                        result.missing_candidates += 1
                        record.update(status="pending", reason="NOT_YET_VALIDATED")
                    records.append(record)
                result.records = records
                result.status = "running"
                save()
                if any(r["status"] == "pending" for r in records) and not session_verified(conn, market, requested_date, stock_factory):
                    raise ValueError("Pörssipäivää ei voitu varmistaa; tietoja ei lisätty")
                emit(update.EVENT_STARTED, "Tarkistetaan puuttuvan päivän tiedot", 0, len(records))
                accepted = []
                for index, record in enumerate(records, 1):
                    ticker = record["ticker"]
                    if record["status"] != "pending":
                        continue
                    rows_added = None
                    try:
                        reason = identity_evidence.hold_reason(ticker, requested_date, requested_date, requested_date)
                        if reason:
                            record.update(status="legitimately_unavailable" if reason.startswith("TARGET_") else "held", reason=reason)
                            continue
                        markets = [r[0] for r in conn.execute("SELECT DISTINCT market FROM osakedata WHERE osake=?", (ticker,))]
                        if markets != [market]:
                            record.update(status="held", reason="MIXED_MARKET_HISTORY")
                            continue
                        left = conn.execute("SELECT pvm,open,high,low,close,volume FROM osakedata WHERE osake=? AND market=? AND pvm<? ORDER BY pvm DESC LIMIT 1",
                                            (ticker, market, requested_date)).fetchone()
                        right = conn.execute("SELECT pvm,open,high,low,close,volume FROM osakedata WHERE osake=? AND market=? AND pvm>? ORDER BY pvm LIMIT 1",
                                             (ticker, market, requested_date)).fetchone()
                        if not left or not right:
                            record.update(status="held", reason="NO_TWO_SIDED_BASIS_EVIDENCE")
                            continue
                        if (date.fromisoformat(right["pvm"])-date.fromisoformat(left["pvm"])).days > 14:
                            record.update(status="held", reason="CONTEXT_WINDOW_TOO_WIDE")
                            continue
                        anchors = {r["pvm"]: {k:r[k] for k in BAR_FIELDS} for r in (left, right)}
                        if not all(valid_bar(bar) for bar in anchors.values()):
                            record.update(status="held", reason="INVALID_STORED_ANCHOR")
                            continue
                        record["anchors"] = anchors
                        reason = identity_evidence.hold_reason(ticker, requested_date, left["pvm"], right["pvm"])
                        if reason:
                            record.update(status="held", reason=reason)
                            continue
                        if conn.execute("SELECT 1 FROM splits_data WHERE osake=? AND is_price_data_corrected=0", (ticker,)).fetchone():
                            record.update(status="held", reason="UNCORRECTED_SPLIT_HISTORY")
                            continue
                        stock = stock_factory(ticker)
                        fetched = history_rows(stock, ticker, market, left["pvm"],
                                               (date.fromisoformat(right["pvm"])+timedelta(days=1)).isoformat())
                        bar = fetched.get(requested_date)
                        metadata = stock.history_metadata if fetched else {}
                        record["provider_identity"] = {k:metadata.get(k) for k in ("symbol","instrumentType","exchangeTimezoneName","firstTradeDate")}
                        first_trade = metadata.get("firstTradeDate")
                        if bar is None:
                            record.update(status="unavailable", reason="NO_YAHOO_RECORD_NOT_PROOF_OF_ABSENCE")
                            continue
                        if (metadata.get("symbol") != ticker or metadata.get("instrumentType") != "EQUITY"
                                or metadata.get("exchangeTimezoneName") != CALENDARS[market][1]):
                            record.update(status="held", reason="PROVIDER_IDENTITY_MARKET_MISMATCH")
                            continue
                        if first_trade is None:
                            record.update(status="held", reason="FIRST_TRADE_DATE_UNAVAILABLE")
                            continue
                        first_date = datetime.fromtimestamp(float(first_trade), ZoneInfo(CALENDARS[market][1])).date()
                        if first_date > selected:
                            record.update(status="held", reason="TARGET_CONFLICTS_WITH_PROVIDER_FIRST_TRADE")
                            continue
                        if first_date > date.fromisoformat(left["pvm"]):
                            record.update(status="held", reason="PRE_IPO_ANCHOR_HISTORY")
                            continue
                        if not valid_bar(bar):
                            record.update(status="held", reason="INVALID_OHLCV")
                            continue
                        if not all(day in fetched and same_basis(expected, fetched[day]) for day,expected in anchors.items()):
                            record.update(status="held", reason="ADJUSTMENT_OR_ANCHOR_MISMATCH")
                            continue
                        record.update(status="validated", reason="TWO_SIDED_YAHOO_BASIS_MATCH", bar=bar,
                                      provider="YAHOO", adjustment="Existing history defaults; unchanged; no rescaling")
                        accepted.append(record)
                        rows_added = 1
                    except sqlite3.Error as exc:
                        record.update(status="database_failure", reason=type(exc).__name__)
                    except Exception as exc:
                        record.update(status="provider_failure", reason=type(exc).__name__)
                        if type(exc).__name__ == "YFRateLimitError":
                            result.errors.append("Yahoo-rajoitus: keskeytetty; myöhempiä tickereitä ei haettu")
                            break
                    finally:
                        update.sleep_after_legacy_stock_ticker(rows_added or 0)
                        update.sleep_legacy_stock_batch(index)
                        emit(update.EVENT_TICKER_UPDATED, f"{index}/{len(records)}: {ticker} — {record['status']}", index, len(records))
                        if index % 10 == 0:
                            save()
            # No network inside a write transaction. Backup once, only for accepted rows.
            if accepted:
                emit(update.EVENT_WARNING, "Varmistetaan varmuuskopio ennen lisäystä")
                save()  # Prepared evidence survives an interrupted operation.
                write_returned = False
                try:
                    result.backup = {"destination": str(Path(backup_dir)/("osakedata_missing_day_"+run_id+".db")),
                                     "temporary": True, "operation_id": run_id, "state": "retained"}
                    result.backup = verified_backup(db, Path(backup_dir), run_id)
                    save()
                    inserted, changed = insert_validated_rows(db, accepted, requested_date, market)
                    write_returned = True
                    result.inserted_rows = inserted
                    overrides = {r["ticker"]:r for r in changed}
                    for r in accepted:
                        r.update(overrides.get(r["ticker"], {"status":"inserted"}))
                    verify_committed_rows(db, accepted)
                    result.writes_verified = True
                except Exception as exc:
                    result.errors.append("Tallennus/varmistus epäonnistui: "+type(exc).__name__)
                    if write_returned:
                        result.database_failures += 1
                    for r in accepted:
                        if write_returned and r["status"] == "inserted":
                            r.update(status="committed_unverified", reason="POST_COMMIT_OUTCOME_UNVERIFIED")
                        elif not write_returned and r["status"] == "validated":
                            r.update(status="database_failure", reason="TRANSACTION_NOT_COMMITTED")
                    if not Path(result.backup["destination"]).exists():
                        result.backup["state"] = "not_created"
            with readonly(db) as conn:
                result.remaining_missing_rows = sum(not conn.execute("SELECT 1 FROM osakedata WHERE osake=? AND pvm=? AND market=?", (r["ticker"],requested_date,market)).fetchone() for r in records)
            result.legitimately_unavailable = sum(r["status"] == "legitimately_unavailable" for r in records)
            result.unavailable_records = sum(r["status"] == "unavailable" for r in records)
            result.identity_adjustment_holds = sum(r["status"] == "held" for r in records)
            result.provider_failures = sum(r["status"] == "provider_failure" for r in records)
            result.database_failures += sum(r["status"] == "database_failure" for r in records)
            result.skipped_existing = sum(r["status"] == "existing" for r in records)
            if result.database_failures or (result.errors and not result.inserted_rows):
                result.status = "failed"
            elif result.remaining_missing_rows or result.errors:
                result.status = "partial"
            else:
                result.status = "completed"
    except Exception as exc:
        result.errors.append(type(exc).__name__+": "+str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        result.status = "failed"
        result.remaining_missing_rows = result.missing_candidates - result.inserted_rows
    try:
        save()  # Retained backup location/result durable before any cleanup.
        if result.backup and result.writes_verified and not (result.errors or result.provider_failures or result.database_failures):
            try:
                delete_verified_temporary_backup(result.backup)
            except OSError as exc:
                result.errors.append("Väliaikaisen varmuuskopion siivous: "+type(exc).__name__)
                result.status = "partial"
            save()
    except OSError as exc:
        result.errors.append("Raportin tallennus epäonnistui: "+type(exc).__name__)
        result.status = "failed"
    emit(update.EVENT_COMPLETED, result.status)
    return result
