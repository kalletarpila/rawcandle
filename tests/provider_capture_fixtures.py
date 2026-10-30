"""Full-source fixtures through the real HTTP acquisition boundary, never a bypass."""
import io,json
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from rawcandle.fundamentals.source_capture import SF1_FIELDS


def full_row(row):
    # This is an explicitly declared synthetic provider response. Production
    # never fills absent fields; omitted fixture metrics are provider NULLs.
    return {**dict.fromkeys(SF1_FIELDS),**row}


def acquired(rows, *, full=True, fields=None):
    payload=[full_row(r) if full else dict(r) for r in rows]
    class Response(io.BytesIO):
        status=200
        headers={'Content-Type':'application/json'}
        def getcode(self):return 200
    client=SharadarClient(api_key='fixture-key',opener=lambda request,timeout:Response(json.dumps(payload).encode()))
    return client.fundamentals(fields=fields).records


def trusted_history(rows, **kwargs):
    from rawcandle.fundamentals.admin.refresh_fundamentals import validate_complete_history
    return validate_complete_history(acquired(rows),**kwargs)


import pytest
@pytest.fixture(autouse=True)
def provider_capture_enabled_for_rollout_checks(monkeypatch):
    from rawcandle.fundamentals import source_capture
    monkeypatch.setattr(source_capture,'ACTIVE',True)
