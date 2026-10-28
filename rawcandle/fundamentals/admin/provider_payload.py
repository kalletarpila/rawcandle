"""Source-aware payload completeness, separate from financial semantics.

Repair candidates are explicit, copy-only operations. They do not approve an
ownership interpretation or participate in automatic financial replacement.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from .contracts import canonical_json, fingerprint

CONTRACT = 'SHARADAR_ACQUISITION_PAYLOAD_V1'
REPAIR = 'SOURCE_PAYLOAD_COMPLETENESS_REPAIR'


def payload_fingerprint(value: Any) -> str:
    # Source fields must not inherit the administrative hash's exclusions for
    # keys such as run_id or timestamp_utc.
    return hashlib.sha256(canonical_json(value, exclude_run_local=False).encode()).hexdigest()


def field_state(payload: Mapping[str, Any], key: str) -> str:
    return 'ABSENT' if key not in payload else 'NULL' if payload[key] is None else 'VALUE'


def acquisition_payload(row: Mapping[str, Any]) -> dict[str, Any] | None:
    value = row.get('_acquisition_payload')
    return dict(value) if isinstance(value, Mapping) else None


def completeness(payload: Mapping[str, Any]) -> dict[str, Any]:
    states = {key: field_state(payload, key) for key in sorted(payload)}
    return {'key_states': states, 'key_count': len(states),
            'completeness_fingerprint': payload_fingerprint(states),
            'payload_fingerprint': payload_fingerprint(dict(payload))}


def compare_payload(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any] | None:
    from .refresh_fundamentals import (
        REFRESH_REQUEST_FIELDS, _effective_row, _raw_row, normalize_source_row, source_key,
        source_key_evidence,
    )
    before, after = acquisition_payload(old), acquisition_payload(new)
    if not before or not after:
        return None  # no retained acquisition evidence; do not invent it
    evidence = {'contract': CONTRACT, 'provider': 'SHARADAR', 'source': 'fundamentals',
                'source_key': source_key_evidence(new),
                'old_observation_id': old.get('_provider_observation_id'),
                'old_content_hash': old.get('_provider_content_hash'),
                'provider_identity': old.get('_provider_identity'),
                'old': completeness(before), 'new': completeness(after)}
    try:
        old_normal = normalize_source_row(before)
        new_normal = normalize_source_row(after)
    except (ValueError, TypeError):
        return {**evidence, 'reason': 'INVALID_ACQUISITION_PAYLOAD'}
    if (source_key(old) != source_key(new) or source_key(before) != source_key(old)
        or source_key(after) != source_key(new)
        or any(old_normal[k] != new_normal[k] for k in ('fiscalperiod', 'calendardate'))):
        return {**evidence, 'reason': 'SOURCE_PAYLOAD_IDENTITY_MISMATCH'}
    identity = old.get('_provider_identity') or {}
    for key in ('permaticker', 'provider', 'native_table', 'company_id', 'security_id', 'provider_security_id'):
        expected = identity.get({'permaticker': 'provider_security_id'}.get(key, key))
        if ((key in before and key in after and str(before[key]) != str(after[key]))
            or (key in after and expected is not None and str(after[key]) != str(expected))):
            return {**evidence, 'reason': 'SOURCE_PAYLOAD_IDENTITY_MISMATCH'}
    if (fingerprint(_raw_row(old_normal)) != fingerprint(_raw_row(old))
        or fingerprint(_raw_row(new_normal)) != fingerprint(_raw_row(new))):
        return {**evidence, 'reason': 'ACQUISITION_FINANCIAL_CONTRADICTION'}
    if fingerprint(_effective_row(old_normal)) != fingerprint(_effective_row(new_normal)):
        return {**evidence, 'reason': 'FINANCIAL_OR_SOURCE_METADATA_REVISION'}
    metadata_changed = fingerprint(_raw_row(old_normal)) != fingerprint(_raw_row(new_normal))
    projection = set(REFRESH_REQUEST_FIELDS)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(key for key in set(before) & set(after) - projection
                     if payload_fingerprint(before[key]) != payload_fingerprint(after[key]))
    evidence.update(fields_restored=added, fields_removed=removed, fields_changed=changed,
                    fields_restored_with_null=[key for key in added if after[key] is None],
                    fields_restored_with_value=[key for key in added if after[key] is not None],
                    financial_fields_changed=False,
                    legacy_financial_projection=set(before) == projection)
    if removed:
        return {**evidence, 'reason': 'SOURCE_PAYLOAD_KEY_REGRESSION'}
    if changed:
        return {**evidence, 'reason': 'SOURCE_PAYLOAD_VALUE_REVISION'}
    if added and metadata_changed:
        return {**evidence, 'reason': 'SOURCE_PAYLOAD_VALUE_REVISION'}
    return {**evidence, 'reason': REPAIR if added else 'NO_PAYLOAD_CHANGE'}


def repair_payloads_on_copy(provider_db: Path, candidates: Sequence[Mapping[str, Any]], *,
                            source_histories: Mapping[tuple[str, str], Any],
                            fetched_at_utc: str) -> dict[str, Any]:
    """Repair only explicitly selected exact rows on an inactive SQLite copy.

    Complete source histories must have passed the normal validator. Each item
    binds a stored observation ID/hash, a full source row and the expected pure
    comparison. Old evidence remains in the unchanged source generation; new
    observations use full-payload hashes and record the complete repair binding.
    """
    from rawcandle.fundamentals.schema.parent_equity import assert_inactive_copy
    from .refresh_fundamentals import normalize_source_row, source_key

    assert_inactive_copy(provider_db)
    if not candidates:
        raise ValueError('PAYLOAD_REPAIR_EMPTY_SELECTION')
    fetched = datetime.fromisoformat(fetched_at_utc.replace('Z', '+00:00'))
    if fetched.tzinfo is None:
        raise ValueError('PAYLOAD_REPAIR_FETCH_TIME_REQUIRED')
    evidence = []
    with sqlite3.connect(provider_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE')
        prepared = []
        seen = set()
        for candidate in candidates:
            source_fetch = candidate.get('source_fetch_timestamp', fetched_at_utc)
            if datetime.fromisoformat(source_fetch.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('PAYLOAD_REPAIR_FETCH_TIME_REQUIRED')
            oid = candidate['old_observation_id']
            if oid in seen:
                raise ValueError('PAYLOAD_REPAIR_DUPLICATE_SELECTION')
            seen.add(oid)
            old = conn.execute('SELECT * FROM provider_observation WHERE observation_id=?', (oid,)).fetchone()
            if old is None or old['content_hash'] != candidate['old_content_hash']:
                raise ValueError('PAYLOAD_REPAIR_STALE_OBSERVATION')
            if old['provider'] != 'SHARADAR' or old['native_table'] != 'fundamentals':
                raise ValueError('PAYLOAD_REPAIR_SOURCE_MISMATCH')
            if (not old['company_id'] or not old['security_id'] or not old['provider_security_id']
                or old['provider_status'] != 'SUCCESS'):
                raise ValueError('PAYLOAD_REPAIR_IDENTITY_BINDING_REQUIRED')
            native = conn.execute('SELECT * FROM sharadar_fundamental_observation WHERE observation_id=?', (oid,)).fetchone()
            if native is None:
                raise ValueError('PAYLOAD_REPAIR_NATIVE_ROW_MISSING')
            from . import accounting_boundary_review as boundary
            if (boundary.interpretation(conn, dict(native))['resolution_id']
                or boundary.current_context(provider_db, dict(native))):
                raise ValueError('PAYLOAD_REPAIR_REVIEWED_OR_RETAINED_SOURCE')
            previous = normalize_source_row(dict(native))
            previous.update(_acquisition_payload=json.loads(old['payload_json']),
                            _provider_observation_id=oid, _provider_content_hash=old['content_hash'],
                            _provider_identity={k: old[k] for k in ('provider', 'native_table', 'company_id', 'security_id', 'provider_security_id')})
            trust = source_histories.get(source_key(previous)[:2])
            if trust is None or trust.status != 'COMPLETE':
                raise ValueError('PAYLOAD_REPAIR_COMPLETE_HISTORY_REQUIRED')
            matches = [row for row in trust.rows if source_key(row) == source_key(previous)]
            if len(matches) != 1:
                raise ValueError('PAYLOAD_REPAIR_AMBIGUOUS_OR_MISSING_SOURCE')
            new = matches[0]
            if (new.get('_history_retention_status') or json.loads(old['provenance_json'] or '{}')):
                raise ValueError('PAYLOAD_REPAIR_REVIEWED_OR_RETAINED_SOURCE')
            comparison = compare_payload(previous, new)
            if not comparison or comparison['reason'] != REPAIR:
                raise ValueError('PAYLOAD_REPAIR_NOT_COMPATIBLE')
            if fingerprint(comparison) != candidate['comparison_fingerprint']:
                raise ValueError('PAYLOAD_REPAIR_STALE_PAYLOAD_BINDING')
            key = source_key(previous)
            count = conn.execute('SELECT COUNT(*) FROM sharadar_fundamental_observation WHERE ticker=? AND dimension=? AND date=? AND reportperiod=?', key).fetchone()[0]
            if count != 1:
                raise ValueError('PAYLOAD_REPAIR_AMBIGUOUS_SOURCE_KEY')
            # Do not cascade-delete other retained/linked provider evidence.
            for table, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                if table == 'sharadar_fundamental_observation':
                    continue
                quoted = '"' + table.replace('"', '""') + '"'
                for fk in conn.execute(f'PRAGMA foreign_key_list({quoted})'):
                    if fk['table'] == 'provider_observation':
                        column = '"' + fk['from'].replace('"', '""') + '"'
                        if conn.execute(f'SELECT 1 FROM {quoted} WHERE {column}=? LIMIT 1', (oid,)).fetchone():
                            raise ValueError('PAYLOAD_REPAIR_LINKED_PROVIDER_EVIDENCE')
            payload = acquisition_payload(new)
            content_hash = payload_fingerprint(payload)
            new_id = fingerprint({'provider': old['provider'], 'source': old['native_table'],
                                  'source_key': key, 'payload_hash': content_hash})
            binding = {**comparison, 'source_fetch_timestamp': source_fetch,
                       'new_observation_id': new_id, 'new_content_hash': content_hash}
            prepared.append((dict(old), dict(native), payload, binding))
        # Validation of the entire selection precedes the first write.
        for old, native, payload, binding in prepared:
            record = {**old, 'observation_id': binding['new_observation_id'],
                      'content_hash': binding['new_content_hash'], 'payload_json': json.dumps(payload, sort_keys=True),
                      'fetched_at_utc': binding['source_fetch_timestamp'],
                      'provenance_json': json.dumps({'source_payload_repair': binding}, sort_keys=True)}
            columns = tuple(record)
            native['observation_id'] = record['observation_id']
            conn.execute('DELETE FROM provider_observation WHERE observation_id=?', (old['observation_id'],))
            conn.execute(f"INSERT INTO provider_observation ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(record.values()))
            conn.execute(f"INSERT INTO sharadar_fundamental_observation ({','.join(native)}) VALUES ({','.join('?' for _ in native)})", tuple(native.values()))
            evidence.append(binding)
        check = conn.execute('PRAGMA integrity_check').fetchone()[0]
        if check != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('PAYLOAD_REPAIR_INTEGRITY_FAILED')
    return {'contract': CONTRACT, 'copy_only': True, 'repaired_count': len(evidence),
            'repairs': evidence, 'integrity_check': 'ok'}
