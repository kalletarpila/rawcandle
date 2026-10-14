"""Yahoo-only, incremental insert-only administration using the stock-update transport.

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
MARKET_TIMEZONES = {
    "usa": "America/New_York",
    "omxh": "Europe/Helsinki",
    "omxs": "Europe/Stockholm",
    "xetra": "Europe/Berlin",
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
    invalid_records: int = 0
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


class ExistingIdentityEvidence:
    """Only dated, reviewed identity conflicts; never Fundamentals eligibility."""
    def __init__(self, registry: Path | None = None):
        self.records = json.loads(registry.read_text())["records"] if registry and registry.exists() else []

    def conflict(self, ticker: str, ds: str) -> dict | None:
        for record in self.records:
            effective = record.get("effective_date")
            if record.get("review_status") != "APPROVED" or not effective:
                continue  # Missing dates and pending reviews are not proven conflicts.
            subject = record.get("subject_ticker")
            predecessor = record.get("predecessor_ticker")
            if subject == ticker and ds < effective:
                reason = "TARGET_BEFORE_REVIEWED_SUCCESSOR"
            elif predecessor == ticker and ds >= effective:
                reason = "TARGET_AFTER_REVIEWED_SUCCESSOR"
            else:
                continue
            return {"reason": reason, "subject_ticker": subject,
                    "predecessor_ticker": predecessor, "effective_date": effective,
                    "resolution_class": record.get("resolution_class"),
                    "review_status": "APPROVED", "evidence": record.get("evidence", [])}
        return None


def existing_identity_evidence() -> ExistingIdentityEvidence:
    return ExistingIdentityEvidence(ROOT / "rawcandle/fundamentals/admin/identity_resolutions.json")


def history_rows(stock, ticker: str, market: str, start: str, end: str) -> dict[str, dict]:
    fetched = update.fetch_history_for_date_ranges(
        stock=stock, ticker=ticker,
        date_ranges=[update.StockUpdateDateRange(start, end)])
    try:
        rows = update.convert_histories_to_ohlcv_rows(histories=fetched.histories, ticker=ticker, market=market)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_PROVIDER_OHLCV_CONVERSION") from exc
    # The normal converter skips incomplete OHLC; report a malformed requested
    # one-day bar as invalid rather than pretending Yahoo returned no bar.
    if (date.fromisoformat(end) - date.fromisoformat(start)).days == 1:
        raw_target = any(history is not None and any(
            index.strftime("%Y-%m-%d") == start for index in history.index)
            for history in fetched.histories)
        if raw_target and not any(row.date == start for row in rows):
            raise ValueError("INCOMPLETE_PROVIDER_OHLC")
    if len({r.date for r in rows}) != len(rows):
        raise ValueError("DUPLICATE_PROVIDER_DATES")
    if any(r.ticker != ticker or r.market != market for r in rows):
        raise ValueError("PROVIDER_ROW_IDENTITY_MISMATCH")
    return {r.date: {k: getattr(r, k) for k in BAR_FIELDS} for r in rows}


def provider_identity(stock, ticker: str, market: str, *, allow_missing: bool = False) -> tuple[dict, str | None]:
    metadata = stock.history_metadata or {}
    evidence = {k: metadata.get(k) for k in
                ("symbol", "instrumentType", "exchangeTimezoneName", "firstTradeDate")}
    if evidence["symbol"] and evidence["symbol"] != ticker:
        return evidence, "PROVIDER_SYMBOL_MISMATCH"
    if not evidence["symbol"] and not allow_missing:
        return evidence, "PROVIDER_SYMBOL_UNVERIFIED"
    timezone = evidence["exchangeTimezoneName"]
    if timezone and timezone != MARKET_TIMEZONES[market]:
        return evidence, "PROVIDER_MARKET_MISMATCH"
    if not timezone and not allow_missing:
        return evidence, "PROVIDER_MARKET_UNVERIFIED"
    return evidence, None  # Instrument type and absent start date do not gate insertion.


def no_data_reason(conn, stock, ticker: str, market: str, ds: str,
                   metadata: dict) -> str:
    """Diagnostic evidence only; at most 14 calendar dates, never listing proof."""
    selected = date.fromisoformat(ds)
    start = (selected - timedelta(days=6)).isoformat()
    end = (selected + timedelta(days=8)).isoformat()  # exclusive
    local = [r[0] for r in conn.execute(
        "SELECT pvm FROM osakedata WHERE osake=? AND market=? AND pvm>=? AND pvm<?",
        (ticker, market, start, end))]
    if any(d < ds for d in local) and any(d > ds for d in local):
        return "NO_TRADING_DATA"
    context = history_rows(stock, ticker, market, start, end)
    _, conflict = provider_identity(stock, ticker, market, allow_missing=not context)
    if conflict:
        raise ValueError(conflict)
    if ds in context:
        return "UNKNOWN"  # Inconsistent responses; this diagnostic request never inserts.
    days = local + [d for d, bar in context.items() if start <= d < end and valid_bar(bar)]
    first_trade = metadata.get("firstTradeDate")
    if first_trade is not None:
        first_date = datetime.fromtimestamp(float(first_trade), ZoneInfo(MARKET_TIMEZONES[market])).date()
        if first_date > selected:
            return "PRE_LISTING_POSSIBLE"
    if days and all(d > ds for d in days):
        return "PRE_LISTING_POSSIBLE"
    if days and all(d < ds for d in days):
        return "POST_DELISTING_POSSIBLE"
    if any(d < ds for d in days) and any(d > ds for d in days):
        return "NO_TRADING_DATA"
    return "UNKNOWN"


def insert_validated_rows(db: Path, accepted: list[dict], ds: str, market: str) -> tuple[int, list[dict]]:
    """Insert-only adapter of the normal per-ticker writer, with atomic key recheck.

    The normal writer commits per ticker. Keep that pattern but require the unique
    key and hold BEGIN IMMEDIATE across the check/INSERT to avoid writer races.
    No acquisition or report I/O takes place inside this transaction.
    """
    changed = []
    with closing(sqlite3.connect(db.resolve().as_uri()+"?mode=rw", uri=True, timeout=30)) as c, c:
        c.row_factory = sqlite3.Row
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='osakedata'").fetchone():
            raise sqlite3.DatabaseError("OHLCV_TABLE_TRIGGERS_REQUIRE_REVIEW")
        unique_key = False
        for idx in c.execute("PRAGMA index_list(osakedata)").fetchall():
            if idx["unique"] and not idx["partial"]:
                columns = [r["name"] for r in c.execute('PRAGMA index_info("'+idx["name"].replace('"','""')+'")')]
                unique_key |= columns == ["osake", "pvm"]
        if not unique_key:
            raise sqlite3.DatabaseError("UNIQUE_TICKER_DATE_CONSTRAINT_REQUIRED")
        for record in accepted:
            ticker = record["ticker"]
            if record["date"] != ds or record["market"] != market or not valid_bar(record["bar"]):
                raise ValueError("OUTSIDE_VALIDATED_MARKET_DATE")
            if c.execute("SELECT 1 FROM osakedata WHERE osake=? AND pvm=?", (ticker, ds)).fetchone():
                changed.append({"ticker": ticker, "status": "existing", "reason": "CONCURRENT_INSERT_SKIPPED"})
                continue
            c.execute("INSERT INTO osakedata(osake,pvm,open,high,low,close,volume,market) VALUES(?,?,?,?,?,?,?,?)",
                      (ticker, ds, *(record["bar"][k] for k in BAR_FIELDS), market))
        # SQLite rolls back all INSERTs on any exception, including commit failure.
    return len(accepted)-len(changed), changed


def verify_committed_rows(db: Path, records: list[dict], *, integrity: bool = True) -> None:
    with readonly(db) as c:
        if integrity and [r[0] for r in c.execute("PRAGMA integrity_check")] != ["ok"]:
            raise RuntimeError("POST_WRITE_INTEGRITY_FAILED")
        for r in records:
            if r["status"] != "inserted":
                continue
            actual = c.execute("SELECT open,high,low,close,volume,market FROM osakedata WHERE osake=? AND pvm=?",
                               (r["ticker"], r["date"])).fetchone()
            if not actual or dict(actual) != {**r["bar"], "market": r["market"]}:
                raise RuntimeError("POST_WRITE_VALUE_VERIFICATION_FAILED")


def run_missing_day_recovery(*, db_path: str | Path, market: str, requested_date: str,
                             stock_factory, report_dir: str | Path,
                             identity_evidence=None, progress_callback=None,
                             today: date | None = None) -> MissingDayResult:
    db, report_dir = Path(db_path), Path(report_dir)
    market = (market or "").strip().lower()
    result = MissingDayResult(date=requested_date, market=market,
                              backup={"state": "not_created", "reason": "INSERT_ONLY_TRANSACTIONS"})
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
        if market not in MARKET_TIMEZONES:
            raise ValueError("Markkinaa ei tueta puuttuvan päivän haussa")
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
                emit(update.EVENT_STARTED, "Haetaan puuttuvan päivän tiedot", 0, len(records))
                for index, record in enumerate(records, 1):
                    ticker = record["ticker"]
                    if record["status"] != "pending":
                        continue
                    rows_added = None
                    try:
                        # Recheck immediately before acquisition as well as inside the writer.
                        if conn.execute("SELECT 1 FROM osakedata WHERE osake=? AND pvm=?",
                                        (ticker, requested_date)).fetchone():
                            record.update(status="existing", reason="CONCURRENT_INSERT_SKIPPED")
                            continue
                        conflict = identity_evidence.conflict(ticker, requested_date)
                        if conflict:
                            record.update(status="held", reason=conflict["reason"], identity_evidence=conflict)
                            continue
                        stock = stock_factory(ticker)
                        fetched = history_rows(stock, ticker, market, requested_date,
                                               (selected + timedelta(days=1)).isoformat())
                        bar = fetched.get(requested_date)
                        metadata, reason = provider_identity(stock, ticker, market, allow_missing=bar is None)
                        record["provider_identity"] = metadata
                        if reason:
                            record.update(status="held", reason=reason)
                            continue
                        if bar is None:
                            record.update(status="unavailable", reason=no_data_reason(
                                conn, stock, ticker, market, requested_date, metadata))
                            continue
                        first_trade = metadata.get("firstTradeDate")
                        if first_trade is not None and datetime.fromtimestamp(
                                float(first_trade), ZoneInfo(MARKET_TIMEZONES[market])).date() > selected:
                            record.update(status="held", reason="TARGET_CONFLICTS_WITH_PROVIDER_FIRST_TRADE",
                                          identity_evidence={"firstTradeDate": first_trade})
                            continue
                        if not valid_bar(bar):
                            record.update(status="invalid_data", reason="INVALID_OHLCV")
                            continue
                        record.update(status="validated", reason="VALID_TARGET_YAHOO_OHLCV", bar=bar,
                                      provider="YAHOO", adjustment="Normal history defaults; no rescaling")
                        inserted, changed = insert_validated_rows(db, [record], requested_date, market)
                        result.inserted_rows += inserted  # Already committed; never claim later rollback.
                        record.update(changed[0] if changed else {"status": "inserted"})
                        rows_added = inserted
                        try:
                            verify_committed_rows(db, [record], integrity=False)
                        except Exception:
                            if inserted:
                                record.update(status="committed_unverified", reason="POST_COMMIT_OUTCOME_UNVERIFIED")
                            raise sqlite3.DatabaseError("POST_COMMIT_VALUE_VERIFICATION_FAILED")
                        save()  # Each successful commit is reflected in durable progress.
                    except sqlite3.Error as exc:
                        if record["status"] != "committed_unverified":
                            record.update(status="database_failure", reason=type(exc).__name__)
                    except ValueError as exc:
                        status = "held" if str(exc).startswith("PROVIDER_") else "invalid_data"
                        record.update(status=status, reason=str(exc))
                    except OSError as exc:
                        # Report failure after a successful commit must not relabel the insert.
                        if rows_added is None:
                            record.update(status="provider_failure", reason=type(exc).__name__)
                        else:
                            result.errors.append("Raportin tallennus epäonnistui: " + type(exc).__name__)
                            break
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
            try:
                verify_committed_rows(db, records, integrity=bool(result.inserted_rows))
                result.writes_verified = not any(r["status"] == "committed_unverified" for r in records)
            except Exception as exc:
                result.errors.append("Tallennuksen varmistus epäonnistui: " + type(exc).__name__)
                result.database_failures += 1
            with readonly(db) as conn:
                result.remaining_missing_rows = sum(not conn.execute("SELECT 1 FROM osakedata WHERE osake=? AND pvm=? AND market=?", (r["ticker"],requested_date,market)).fetchone() for r in records)
            result.invalid_records = sum(r["status"] == "invalid_data" for r in records)
            result.unavailable_records = sum(r["status"] == "unavailable" for r in records)
            result.identity_adjustment_holds = sum(r["status"] == "held" for r in records)
            result.provider_failures = sum(r["status"] == "provider_failure" for r in records)
            result.database_failures += sum(r["status"] in ("database_failure", "committed_unverified") for r in records)
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
    except BaseException:
        result.status = "interrupted"
        result.remaining_missing_rows = result.missing_candidates - result.inserted_rows
        try:
            save()  # Completed transactions survive; SQLite rolls back the active write.
        except OSError:
            pass  # Preserve the interruption; restart reconciles directly with database keys.
        raise
    try:
        save()
    except OSError as exc:
        result.errors.append("Raportin tallennus epäonnistui: "+type(exc).__name__)
        result.status = "failed"
    emit(update.EVENT_COMPLETED, result.status)
    return result
