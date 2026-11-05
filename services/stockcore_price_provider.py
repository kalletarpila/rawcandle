"""Temporary, opt-in scheduled price bridge. No acquisition or writes at import.

Source authority stays in StockCore; the RC-facing conversion preserves Yahoo's
existing auto-adjusted contract. Only a proven route absence permits Yahoo routing.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import importlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

import pandas as pd

from services.price_revision_policy import (RevisionDiagnostics, difference,
                                           ordinary_revision, revision_witness)

SOURCE_ROOT = Path('/home/kalle/projects/stockcore')
PRICE_FIELDS = ('Open', 'High', 'Low', 'Close')
COLUMNS = [*PRICE_FIELDS, 'Volume']
COUNTERS = ('usa_stockcore', 'usa_yahoo_fallback', 'omxh_yahoo', 'stockcore_no_new',
            'action_split_holds', 'source_quality_coverage_holds',
            'currency_unit_holds', 'anchor_materiality_holds', 'reader_failures',
            'historical_revision_differences', 'historical_revision_warnings_new',
            'historical_revision_safety_holds')


class SourceHold(Exception):
    def __init__(self, category, reason):
        self.category, self.reason = category, reason
        super().__init__(reason)


@lru_cache(maxsize=4)
def source_contract(root: str):
    """Load only the trusted checkout, without replacing RC's Yahoo installation."""
    path = Path(root)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('UNTRUSTED_STOCKCORE_CHECKOUT')
    if not (path / 'stockcore/prices.py').is_file():
        raise RuntimeError('STOCKCORE_READER_NOT_INSTALLED')
    if str(path) not in sys.path:
        sys.path.append(str(path))
    package = importlib.import_module('stockcore')
    if Path(package.__file__).resolve().parent != path / 'stockcore':
        raise RuntimeError('STOCKCORE_PACKAGE_ORIGIN_MISMATCH')
    from stockcore.config import physical_file
    from stockcore.storage import Store
    from stockcore.identity import resolve, instrument_type
    from stockcore.source_model import binding
    from stockcore.sessions import Calendar
    from stockcore.prices import PriceReader
    from stockcore.source import identity_token
    from stockcore.source_references import calendar_dependency
    from stockcore.actions import operating_security
    from stockcore.contracts import fingerprint, ContractError
    from stockcore.source_receipt_contract import acceptance_receipt
    from stockcore.config import Config
    from stockcore.storage import acceptance_lock
    return SimpleNamespace(**locals())


@contextmanager
def readonly(path: Path, *, seconds=2.0):
    """Physical RO open; no recovery, initialize, migration or writable fallback."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('UNSAFE_DATABASE_PATH')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError('REGULAR_UNLINKED_DATABASE_REQUIRED')
    before = path.stat()
    c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=.1)
    try:
        after = path.stat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise RuntimeError('DATABASE_CHANGED_DURING_OPEN')
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        c.execute('PRAGMA trusted_schema=OFF')
        deadline = time.monotonic() + seconds
        c.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        c.execute('BEGIN')
        yield c
    finally:
        c.close()


class PinnedStore:
    """Canonical reader facade; the outer context alone owns/ends this snapshot."""
    config = SimpleNamespace(mode='projection')

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def read(self, **_kwargs):
        yield self.connection


def bounded(cursor):
    rows = cursor.fetchmany(10001)
    if len(rows) > 10000:
        raise RuntimeError('SOURCE_SCOPE_TOO_LARGE')
    return rows


def valid_prices(values):
    try:
        o, h, l, c = map(float, values)
        eps = max(o, h, l, c) * 1e-12
        return all(math.isfinite(v) and v > 0 for v in (o, h, l, c)) and l <= min(o, c) + eps and max(o, c) <= h + eps
    except (TypeError, ValueError, OverflowError):
        return False


def valid_volume(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and
            math.isfinite(value) and 0 <= value <= 2**63 - 1 and int(value) == value and
            int(float(value)) == value)  # RC iterrows() coerces numeric rows to float


def prices_match(a, b, tolerance=.001):
    return valid_prices(a) and valid_prices(b) and all(abs(x-y) / y <= tolerance + 1e-12 for x, y in zip(a, b))


def volumes_match(source, rc, *, counted=True):
    if not valid_volume(source) or not valid_volume(rc):
        return False
    if source == rc:
        return True
    if not source or not rc or max(source, rc) <= 100:
        return False
    relative = abs(source - rc) / rc
    return relative <= .01 or (counted and max(source, rc) <= 5000 and source % 100 == 0 and
                              abs(source - rc) <= 50 and relative <= .1)


def rc_state(path, ticker):
    with readonly(path) as c:
        rows = bounded(c.execute('SELECT pvm,open,high,low,close,volume,market FROM osakedata WHERE osake=? ORDER BY pvm DESC LIMIT 3', (ticker,)))
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='splits_data'").fetchone()
        splits = bounded(c.execute('SELECT split_date,split_ratio,is_price_data_corrected FROM splits_data WHERE osake=? ORDER BY split_date', (ticker,))) if exists else []
        return [dict(r) for r in rows], [tuple(r) for r in splits]


class StockCoreTicker:
    def __init__(self, owner, ticker, rows=(), splits=(), zone='America/New_York', hold=None, anchor=None, rc_splits=(), source_pin=None):
        self.owner, self.ticker = owner, ticker
        self.rows, self.events, self.zone = rows, splits, zone
        self.hold, self.anchor, self.rc_splits = hold, anchor, rc_splits
        self.source_pin = source_pin
        self.revision_diagnostics = []

    @contextmanager
    def _stockcore_publication_context(self):
        """Hold the native Source acceptance lock through the RC price commit."""
        lib = source_contract(str(self.owner.source_root))
        config = lib.Config(self.owner.source_path.parent.parent, mode='projection')
        if config.db != self.owner.source_path or not self.source_pin:
            raise RuntimeError('PINNED_SOURCE_PUBLICATION_REQUIRED')
        with lib.acceptance_lock(config):
            self.guard(anchor=True)
            with readonly(self.owner.source_path) as c:
                sid = self.source_pin['security_id']
                head = c.execute('SELECT * FROM source_heads WHERE security_id=?', (sid,)).fetchone()
                dep = json.loads(head['dependency']) if head else None
                if not head or dep != self.source_pin['dependency'] or head['receipt_id'] != self.source_pin['receipt_id']:
                    raise RuntimeError('SOURCE_CHANGED_AFTER_PREFLIGHT')
                cal = lib.Calendar(lib.binding(c, sid, expanded=True)['calendar'])
                if dep['identity_version'] != lib.identity_token(c, sid) or dep['calendar_version'] != lib.calendar_dependency(c, sid, cal):
                    raise RuntimeError('SOURCE_REFERENCE_CHANGED_AFTER_PREFLIGHT')
                self.owner._route_holds(c, [sid])
                actions = [dict(r, payload=json.loads(r['payload'])) for r in bounded(c.execute('SELECT * FROM corporate_actions WHERE security_id=?', (sid,)))]
                if lib.fingerprint(actions) != self.source_pin['actions']:
                    raise RuntimeError('SOURCE_ACTION_CHANGED_AFTER_PREFLIGHT')
            yield

    def _stockcore_price_rows_committed(self, dates):
        for item in self.revision_diagnostics:
            item.update(new_sessions_appended=list(dates), publication_status='COMMITTED' if dates else 'NO_NEW_ROWS')
            self.owner.diagnostics.record(item, update=True)

    def guard(self, *, anchor=False):
        if self.hold:
            raise RuntimeError('STOCKCORE_WITHHELD: ' + self.hold)
        rows, splits = rc_state(self.owner.rc_path, self.ticker)
        if splits != self.rc_splits or (anchor and (not rows or rows[0] != self.anchor)):
            self.owner.record('action_split_holds', self.ticker, 'RC_STATE_CHANGED_AFTER_PREFLIGHT')
            raise RuntimeError('RC_STATE_CHANGED_AFTER_STOCKCORE_PREFLIGHT')

    def history(self, *, start, end):
        if self.hold:
            return self.owner.frame([], self.zone)
        if start <= self.anchor['pvm'] or end > self.owner.until:
            raise RuntimeError('HISTORY_OUTSIDE_PREFLIGHT_SCOPE')
        self.guard(anchor=True)
        return self.owner.frame([r for r in self.rows if start <= r['session'] < end], self.zone)

    @property
    def splits(self):
        self.guard()
        return pd.Series([ratio for _, ratio in self.events],
                         index=pd.DatetimeIndex([day for day, _ in self.events], tz=self.zone), dtype='float64')


class ScheduledPriceFactory:
    def __init__(self, *, rc_path, market, until, yahoo_factory, source_path=None, source_root=SOURCE_ROOT, now=None,
                 diagnostic_dir=None):
        self.rc_path, self.market, self.until = Path(rc_path), market, until
        self.yahoo_factory = yahoo_factory
        self.source_root = Path(source_root)
        self.source_path = Path(source_path) if source_path else self.source_root / 'runtime/osakedata_ng.db'
        self.now = now or datetime.now(timezone.utc)
        self.counts, self.reasons, self.examples, self.selected = Counter(), Counter(), [], {}
        self.diagnostics = RevisionDiagnostics(diagnostic_dir or self.rc_path.parent / 'price_bridge_revisions')
        self.pending_diagnostics = []

    def _flush_diagnostics(self, *, held=None, sessions=()):
        for item in self.pending_diagnostics:
            item.update(classification='SAFETY_HOLD' if held else 'NON_BLOCKING_HISTORICAL_REVISION',
                        new_sessions_eligible=list(sessions), skipped_reason=held)
            self.counts['historical_revision_differences'] += 1
            self.counts['historical_revision_safety_holds'] += bool(held)
            if self.diagnostics.record(item):
                self.counts['historical_revision_warnings_new'] += 1
                if len(self.examples) < 20:
                    self.examples.append(item)
        self.pending_diagnostics = []

    def record(self, category, ticker, reason, **evidence):
        self.counts[category] += 1
        self.reasons[reason] += 1
        if len(self.examples) < 20:
            self.examples.append(dict(ticker=ticker, reason=reason, **evidence))

    @staticmethod
    def frame(rows, zone):
        # Called only after all Source/RC read contexts have closed.
        frame = pd.DataFrame([r['adjusted'] for r in rows], columns=COLUMNS)
        for field in PRICE_FIELDS:
            frame[field] = frame[field].astype('float64')
        frame['Volume'] = frame['Volume'].astype('int64')
        frame.index = pd.DatetimeIndex([r['session'] for r in rows], tz=zone, name='Date')
        return frame

    def summary_lines(self):
        lines = [f'SUMMARY price_bridge.{key}={self.counts[key]}' for key in COUNTERS]
        lines.append('SUMMARY price_bridge.reasons=' + json.dumps(dict(self.reasons), sort_keys=True))
        lines.append('SUMMARY price_bridge.examples=' + json.dumps(self.examples, sort_keys=True))
        return lines

    def __call__(self, ticker):
        if self.market != 'usa':
            self.counts['omxh_yahoo'] += 1
            return self.yahoo_factory(ticker)
        self.pending_diagnostics = []
        try:
            lib = source_contract(str(self.source_root))
            with readonly(self.source_path) as c:
                lib.Store._validate(PinnedStore(c), c, integrity=False)
                identity = c.execute("SELECT value FROM settings WHERE key='identity_fingerprint'").fetchone()
                if not identity or not identity[0]:
                    raise RuntimeError('ACCEPTED_SOURCE_IDENTITY_REQUIRED')
                c.execute('SELECT request FROM operation_schedules LIMIT 0')
                decision = self._snapshot(c, lib, ticker)
        except SourceHold as exc:
            self._flush_diagnostics(held=exc.reason)
            self.record(exc.category, ticker, exc.reason)
            result = StockCoreTicker(self, ticker, hold=exc.reason)
            self.selected[ticker] = result
            return result
        except Exception:
            self.record('reader_failures', ticker, 'SOURCE_READER_OR_CONTRACT_FAILURE')
            raise
        # Yahoo construction and all pandas work occur outside Source reads.
        if isinstance(decision, str):
            self.record('usa_yahoo_fallback', ticker, decision)
            return self.yahoo_factory(ticker)
        self.counts['usa_stockcore'] += 1
        decision.revision_diagnostics = list(self.pending_diagnostics)
        self._flush_diagnostics(sessions=[r['session'] for r in decision.rows])
        self.selected[ticker] = decision
        return decision

    def _snapshot(self, c, lib, ticker):
        if ticker != ticker.strip().upper():
            raise SourceHold('source_quality_coverage_holds', 'UNVERIFIED_TICKER_CONVENTION')
        routes = bounded(c.execute("SELECT * FROM routes WHERE provider='yahoo' AND ticker=?", (ticker,)))
        if not routes:
            return 'MISSING_SOURCE_TICKER'
        # Unqualified competing evidence must never become Yahoo fallback.
        if any(not r['accepted'] or not r['valid_from'] for r in routes):
            raise SourceHold('source_quality_coverage_holds', 'UNQUALIFIED_SOURCE_ROUTE')
        today = self.now.date().isoformat()
        resolved = lib.resolve(c, ticker=ticker, as_of=today)
        if resolved.reason == 'AMBIGUOUS_ROUTE_INTERVAL':
            raise SourceHold('source_quality_coverage_holds', 'AMBIGUOUS_SOURCE_ROUTE')
        self._route_holds(c, [resolved.security_id] if resolved.status == 'ACCEPTED' else {r['security_id'] for r in routes})
        if resolved.status == 'UNKNOWN' and resolved.reason == 'NO_ACCEPTED_DATED_ROUTE':
            # Validate all interval dates before concluding an eligible route is absent.
            for route in routes:
                date.fromisoformat(route['valid_from'])
                if route['valid_to']:
                    date.fromisoformat(route['valid_to'])
                    if route['valid_from'] >= route['valid_to']:
                        raise SourceHold('source_quality_coverage_holds', 'CONTRADICTORY_ROUTE_INTERVAL')
            return 'NO_ELIGIBLE_SOURCE_ROUTE'
        sid = resolved.security_id
        if resolved.status != 'ACCEPTED':
            sid = routes[0]['security_id'] if len(routes) == 1 else None
            security_row = c.execute('SELECT payload FROM securities WHERE security_id=?', (sid,)).fetchone()
            p = json.loads(security_row[0]) if security_row else {}
            if p.get('eligible_from') and (today < p['eligible_from'] or p.get('eligible_to') and today >= p['eligible_to']):
                return 'OUTSIDE_SOURCE_ELIGIBILITY'
            raise SourceHold('source_quality_coverage_holds', 'SOURCE_ELIGIBILITY_UNPROVEN')
        security_row = c.execute('SELECT * FROM securities WHERE security_id=?', (sid,)).fetchone()
        security = json.loads(security_row['payload'])
        if not security_row['active'] or security_row['market'] != 'USA':
            return 'NO_SUPPORTED_ELIGIBLE_SOURCE_INSTRUMENT'
        kind = lib.instrument_type(security, ticker=ticker)
        if kind['status'] != 'QUALIFIED':
            raise SourceHold('currency_unit_holds', 'INSTRUMENT_UNITS_UNQUALIFIED')
        binding = lib.binding(c, sid, expanded=True)
        if not binding:
            raise SourceHold('source_quality_coverage_holds', 'MISSING_CALENDAR_BINDING')
        cal = lib.Calendar(binding['calendar'])
        cal.require_instrument(security, ticker=ticker)
        head = c.execute('SELECT * FROM source_heads WHERE security_id=?', (sid,)).fetchone()
        if not head:
            raise SourceHold('source_quality_coverage_holds', 'SOURCE_NOT_ACCEPTED')
        dependency = json.loads(head['dependency'])
        if (dependency.get('security_id') != sid or dependency.get('source_revision') != str(head['revision']) or
                dependency.get('identity_version') != lib.identity_token(c, sid) or
                dependency.get('calendar_version') != lib.calendar_dependency(c, sid, cal)):
            raise SourceHold('source_quality_coverage_holds', 'STALE_SOURCE_DEPENDENCY')
        setting = c.execute("SELECT value FROM settings WHERE key=?", ('source_quality_hold:' + str(sid),)).fetchone()
        if setting and json.loads(setting[0]).get('active'):
            raise SourceHold('currency_unit_holds', 'SOURCE_UNIT_HOLD')
        schedule = c.execute("SELECT request FROM operation_schedules WHERE schedule_id='yahoo-daily'").fetchone()
        if schedule and str(sid) in json.loads(schedule[0]).get('held', {}):
            raise SourceHold('source_quality_coverage_holds', 'SOURCE_OPERATOR_HOLD')
        actions = [dict(r, payload=json.loads(r['payload'])) for r in bounded(c.execute('SELECT * FROM corporate_actions WHERE security_id=?', (sid,)))]
        source_pin = dict(security_id=sid, dependency=dependency, receipt_id=head['receipt_id'], actions=lib.fingerprint(actions))
        if any(a['status'] == 'HELD' and a['kind'] != 'DIVIDEND' for a in actions):
            raise SourceHold('action_split_holds', 'SOURCE_ACTION_HELD')
        self._currency(c, lib, security, actions, ticker)
        rc_rows, rc_splits = rc_state(self.rc_path, ticker)
        if not rc_rows:
            raise SourceHold('anchor_materiality_holds', 'RC_ANCHOR_MISSING')
        anchor = rc_rows[0]
        if any((r['market'] or '').strip().lower() != 'usa' for r in rc_rows):
            raise SourceHold('currency_unit_holds', 'RC_MARKET_IDENTITY_CONFLICT')
        extent = c.execute('SELECT MIN(session),MAX(session) FROM source_observations WHERE security_id=?', (sid,)).fetchone()
        events = self._splits(actions, rc_splits, extent)
        completed = cal.completed(self.now)
        limit = min(self.until, (date.fromisoformat(completed[-1]) + timedelta(days=1)).isoformat()) if completed else cal.start
        last = min(extent[1], (date.fromisoformat(limit)-timedelta(days=1)).isoformat()) if extent[1] else None
        if last is None:
            raise SourceHold('source_quality_coverage_holds', 'SOURCE_OBSERVATIONS_MISSING')
        no_new = last <= anchor['pvm']
        start = last if no_new else max(cal.start, min(r['pvm'] for r in rc_rows))
        reader = lib.PriceReader(PinnedStore(c)).read(security_id=sid, calendar=cal, now=self.now,
                                                     start=start, end=last, requires_volume=True)
        qualified = {r['session']: r for r in reader['sessions']}
        raw = {r['session']: json.loads(r['payload']) for r in bounded(c.execute('SELECT session,payload FROM source_accepted WHERE security_id=? AND session BETWEEN ? AND ? ORDER BY session', (sid, start, last)))}
        materialized = {}
        for day, item in qualified.items():
            if day < anchor['pvm'] and not no_new:
                continue
            if item['status'] != 'AVAILABLE':
                if item['status'] == 'MISSING' and item.get('coverage_status') in {'NO_PRICE_OBSERVATION', 'ACTION_ONLY'} and day > anchor['pvm']:
                    continue
                raise SourceHold('source_quality_coverage_holds', 'SOURCE_' + item['status'])
            q = item['quality']
            if (not q.get('adjusted_usable') or q.get('price_units') != 'YAHOO_SPLIT_ADJUSTED' or
                    q.get('volume_units') != 'PROVIDER_REPORTED' or q.get('unit_evidence', {}).get('auto_adjust') is not False):
                raise SourceHold('currency_unit_holds', 'UNQUALIFIED_ADJUSTED_PRICE_OR_UNITS')
            materialized[day] = self._convert(raw[day])
        if no_new:
            self.record('stockcore_no_new', ticker, 'NO_NEW_ACCEPTED_SOURCE_SESSION', source_dependency=dependency)
            return StockCoreTicker(self, ticker, anchor=anchor, rc_splits=rc_splits, splits=events, zone=cal.payload['timezone'], source_pin=source_pin)
        if anchor['pvm'] not in materialized:
            raise SourceHold('anchor_materiality_holds', 'SOURCE_ANCHOR_UNAVAILABLE')
        self._factors(materialized, actions)
        raw_anchor = raw[anchor['pvm']]
        diagnostic = difference(ticker=ticker, security_id=sid, anchor=anchor, raw=raw_anchor,
                                adjusted=materialized[anchor['pvm']]['adjusted'], dependency=dependency)
        if diagnostic:
            observation = c.execute('SELECT receipt_id FROM source_observations WHERE security_id=? AND session=?',
                                    (sid, anchor['pvm'])).fetchone()
            witness, reason = revision_witness(c, lib, security_id=sid, session=anchor['pvm'],
                                               calendar=cal, now=self.now, anchor_receipt=observation[0])
            diagnostic.update(source_receipt=observation[0], revision_witness=witness,
                              qualification_reason=reason)
            self.pending_diagnostics.append(diagnostic)
        else:
            witness = None
        context = []
        for peer in rc_rows[1:]:
            if peer['pvm'] in raw and qualified[peer['pvm']]['status'] == 'AVAILABLE':
                q = qualified[peer['pvm']]['quality']
                if q.get('adjusted_usable') and q.get('price_units') == 'YAHOO_SPLIT_ADJUSTED' and q.get('volume_units') == 'PROVIDER_REPORTED':
                    context.append((self._convert(raw[peer['pvm']])['adjusted'],
                                    [peer[k] for k in ('open', 'high', 'low', 'close', 'volume')]))
        self._anchor_revision = (diagnostic, witness, context)
        self._anchor(anchor, materialized[anchor['pvm']], actions, last, kind['value'])
        # Context is diagnostic: hold persistent unexplained scaling, not ordinary old revisions.
        self._scaling(rc_rows, {d: p for d, p in raw.items() if qualified[d]['status'] == 'AVAILABLE'}, actions, last)
        rows = [dict(session=d, **materialized[d]) for d in sorted(materialized) if d > anchor['pvm']]
        if not rows:
            self.record('stockcore_no_new', ticker, 'NO_NEW_PRICE_OBSERVATION')
        if len(self.examples) < 20:
            self.examples.append(dict(ticker=ticker, reason='SOURCE_SNAPSHOT', source_dependency=dependency,
                                      anchor=anchor['pvm'], through=last, observations=len(rows)))
        return StockCoreTicker(self, ticker, rows, events, cal.payload['timezone'], anchor=anchor, rc_splits=rc_splits, source_pin=source_pin)

    @staticmethod
    def _route_holds(c, ids):
        """An explicit quarantine outranks even a closed/inactive-route fallback."""
        row = c.execute("SELECT request FROM operation_schedules WHERE schedule_id='yahoo-daily'").fetchone()
        exclusions = json.loads(row[0]).get('held', {}) if row else {}
        for sid in ids:
            if str(sid) in exclusions:
                raise SourceHold('source_quality_coverage_holds', 'SOURCE_OPERATOR_HOLD')
            row = c.execute('SELECT value FROM settings WHERE key=?', ('source_quality_hold:' + str(sid),)).fetchone()
            if row and json.loads(row[0]).get('active'):
                raise SourceHold('currency_unit_holds', 'SOURCE_UNIT_HOLD')
            if c.execute("SELECT 1 FROM corporate_actions WHERE security_id=? AND status='HELD' AND kind!='DIVIDEND' LIMIT 1", (sid,)).fetchone():
                raise SourceHold('action_split_holds', 'SOURCE_ACTION_HELD')

    def _currency(self, c, lib, security, actions, ticker):
        currency = lib.operating_security(security).get('currency', {})
        values = {currency['value']} if currency.get('value') and currency.get('source') not in (None, '', 'UNKNOWN') else set()
        for action in actions:
            p = action['payload']; ev = p.get('evidence', {}); ref = ev.get('currency_reference', {})
            if (action['status'] != 'RECORDED' or ref.get('basis') != 'SUCCESSFUL_HISTORY_CACHED_PRICE_CURRENCY' or
                    ref.get('field') != 'currency' or ref.get('interface') != 'Ticker.get_history_metadata'):
                continue
            stamp = datetime.fromisoformat(ev['observed_at'])
            if stamp.tzinfo is None or stamp > self.now or ev.get('security_id') != security['security_id']:
                continue
            route = lib.resolve(c, security_id=security['security_id'], as_of=stamp.date().isoformat())
            if route.status == 'ACCEPTED' and route.ticker == ticker and ref.get('value'):
                values.add(ref['value'])
        if values != {'USD'}:
            raise SourceHold('currency_unit_holds', 'QUOTE_CURRENCY_CONFLICT_OR_UNPROVEN')

    @staticmethod
    def _splits(actions, rc_splits, extent):
        old = {d: (ratio, corrected) for d, ratio, corrected in rc_splits}
        if any(corrected != 1 or not math.isfinite(float(ratio)) or float(ratio) <= 0
               for _, ratio, corrected in rc_splits):
            raise SourceHold('action_split_holds', 'RC_UNCORRECTED_SPLIT')
        events = {}
        for action in actions:
            if action['kind'] != 'SPLIT':
                continue
            p = action['payload']; day = date.fromisoformat(p['effective_date']).isoformat(); ratio = float(p['ratio'])
            if action['status'] != 'PROCESSED' or p.get('ratio_orientation') != 'NEW_PER_OLD' or not math.isfinite(ratio) or ratio <= 0 or ratio == 1:
                raise SourceHold('action_split_holds', 'SOURCE_SPLIT_UNQUALIFIED')
            if day in events or old.get(day) != (ratio, 1):
                raise SourceHold('action_split_holds', 'NEW_REVISED_OR_CONFLICTING_SPLIT')
            events[day] = ratio
        if extent[0] and any(extent[0] <= d <= extent[1] and d not in events for d in old):
            raise SourceHold('action_split_holds', 'RC_ONLY_SPLIT_IN_SOURCE_SCOPE')
        return sorted(events.items())

    @staticmethod
    def _convert(raw):
        ordinary = [float(raw[k]) for k in PRICE_FIELDS]
        if not valid_prices(ordinary):
            raise SourceHold('source_quality_coverage_holds', 'INVALID_ACCEPTED_OHLCV')
        factor = float(raw['Adj Close']) / ordinary[3]
        adjusted = [v * factor for v in ordinary[:3]] + [float(raw['Adj Close'])]
        if not valid_prices(ordinary) or not valid_prices(adjusted) or not math.isfinite(factor) or factor <= 0 or not valid_volume(raw['Volume']):
            raise SourceHold('source_quality_coverage_holds', 'INVALID_ACCEPTED_OHLCV')
        return dict(ordinary=ordinary, factor=factor, adjusted=[*adjusted, int(raw['Volume'])])

    @staticmethod
    def _factors(rows, actions):
        """A material new factor step requires independently recorded dividends.

        Reuse the accepted price materiality threshold; do not compare overnight
        price returns or derive adjustment factors from cash amounts.
        """
        previous = None
        for day, row in sorted(rows.items()):
            if previous:
                old_day, old = previous
                change = row['factor'] / old['factor'] - 1
                if abs(change) > .001 + 1e-12:
                    dividends = [a for a in actions if a['kind'] == 'DIVIDEND' and
                                 old_day < a['payload'].get('effective_date', '') <= day]
                    if (change < 0 or not dividends or any(a['status'] != 'RECORDED' or
                            not math.isfinite(float(a['payload'].get('amount', 0))) or
                            float(a['payload'].get('amount', 0)) <= 0 for a in dividends)):
                        raise SourceHold('currency_unit_holds', 'UNEXPLAINED_NEW_ADJUSTMENT_FACTOR_STEP')
            previous = day, row

    def _anchor(self, rc, source, actions, end, kind):
        diagnostic, witness, context = getattr(self, '_anchor_revision', (None, None, ()))
        prices = [rc[k] for k in ('open', 'high', 'low', 'close')]
        if not valid_prices(prices) or not valid_volume(rc['volume']):
            raise SourceHold('anchor_materiality_holds', 'INVALID_RC_ANCHOR')
        ordinary = False
        if diagnostic:
            ordinary, reason = ordinary_revision(diagnostic=diagnostic, witness=witness, context=context,
                                                 prices_match=prices_match, volumes_match=volumes_match)
            diagnostic['qualification_reason'] = reason if witness else diagnostic['qualification_reason']
        if not prices_match(source['adjusted'][:4], prices):
            dividends = [a for a in actions if a['kind'] == 'DIVIDEND' and rc['pvm'] < a['payload'].get('effective_date', '') <= end]
            explained = (dividends and all(a['status'] == 'RECORDED' and float(a['payload'].get('amount', 0)) > 0 for a in dividends)
                         and 0 < source['factor'] < 1 and prices_match(source['ordinary'], prices))
            if not explained and not ordinary:
                raise SourceHold('anchor_materiality_holds', 'UNEXPLAINED_PRICE_OR_FACTOR_BOUNDARY')
            if explained:
                self.record('dividend_vintage_confirmed', '', 'LEGACY_DIVIDEND_VINTAGE_CONFIRMED')
        if not ordinary and not volumes_match(source['adjusted'][4], rc['volume'], counted=kind not in {'CRYPTO', 'INDEX'}):
            raise SourceHold('anchor_materiality_holds', 'MATERIAL_VOLUME_BOUNDARY')

    @staticmethod
    def _scaling(rc_rows, raw, actions, end):
        ratios, volumes = [], []
        for row in rc_rows:
            if row['pvm'] not in raw:
                return
            source = ScheduledPriceFactory._convert(raw[row['pvm']])
            old = [row[k] for k in ('open', 'high', 'low', 'close')]
            if not valid_prices(old):
                return  # old defects are not new observations or substituted anchors
            r = [a/b for a, b in zip(source['adjusted'][:4], old)]
            if max(r)-min(r) <= 1e-8:
                ratios.append(r[3])
            if valid_volume(row['volume']) and row['volume'] > 0:
                volumes.append(source['adjusted'][4] / row['volume'])
        if len(ratios) == 3 and max(ratios)-min(ratios) <= 1e-8 and abs(sum(ratios)/3-1) > 1e-6:
            if not any(a['kind'] == 'DIVIDEND' and a['status'] == 'RECORDED' and min(r['pvm'] for r in rc_rows) <= a['payload'].get('effective_date', '') <= end for a in actions):
                raise SourceHold('currency_unit_holds', 'UNEXPLAINED_PERSISTENT_PRICE_SCALING')
        if len(volumes) == 3 and max(volumes)-min(volumes) <= 1e-4 and abs(sum(volumes)/3-1) > .001:
            raise SourceHold('currency_unit_holds', 'UNEXPLAINED_PERSISTENT_VOLUME_SCALING')


def scheduled_adapters(app, *, market, fetch_until_exclusive):
    """Only the opt-in scheduler CLI supplies this callback. Other builders stay Yahoo."""
    adapters = app._build_stock_update_service_adapters()
    factory = ScheduledPriceFactory(rc_path=app.osakedata_db_path, market=market,
                                    until=fetch_until_exclusive, yahoo_factory=adapters['stock_factory'])
    old_sync, old_backfill = adapters['sync_splits'], adapters['maybe_backfill_splits']

    def sync(ticker, stock):
        if isinstance(stock, StockCoreTicker):
            stock.guard()
            return 0  # matching processed events were verified; no new split write
        return old_sync(ticker, stock)

    def backfill(ticker):
        if ticker in factory.selected:
            factory.selected[ticker].guard()
            return False  # never enter the destructive Yahoo callback for Source
        return old_backfill(ticker)

    return {**adapters, 'stock_factory': factory, 'sync_splits': sync, 'maybe_backfill_splits': backfill}, factory
