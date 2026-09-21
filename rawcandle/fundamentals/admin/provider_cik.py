"""Sharadar provider CIK extraction and canonical normalization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse


CANONICAL_CIK_WIDTH = 10
SHARADAR_SEC_HOST = "www.sec.gov"
SHARADAR_SEC_PATH = "/cgi-bin/browse-edgar"


@dataclass(frozen=True)
class ProviderCikExtraction:
    status: str
    cik_normalized: str | None
    source_value: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_cik(value: Any) -> str | None:
    """Return RawCandle's ten-digit canonical CIK, or None for invalid input."""
    text = str(value or "").strip()
    if not text or not text.isdigit() or len(text) > CANONICAL_CIK_WIDTH:
        return None
    if int(text) <= 0:
        return None
    return text.zfill(CANONICAL_CIK_WIDTH)


def extract_sharadar_cik(secfilings: Any) -> ProviderCikExtraction:
    """Parse the observed Sharadar SEC company-filings URL contract."""
    text = str(secfilings or "").strip()
    if not text:
        return ProviderCikExtraction(
            "UNAVAILABLE", None, None, "PROVIDER_CIK_UNAVAILABLE",
        )
    try:
        parsed = urlparse(text)
    except ValueError:
        return ProviderCikExtraction("INVALID", None, text, "PROVIDER_CIK_INVALID")
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != SHARADAR_SEC_HOST
        or parsed.path != SHARADAR_SEC_PATH
    ):
        return ProviderCikExtraction(
            "UNSUPPORTED", None, text, "PROVIDER_CIK_UNSUPPORTED_FORMAT",
        )
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=False)
    action = query.get("action") or []
    cik_values = query.get("CIK") or query.get("cik") or []
    if action != ["getcompany"] or len(cik_values) != 1:
        return ProviderCikExtraction("INVALID", None, text, "PROVIDER_CIK_INVALID")
    normalized = normalize_cik(cik_values[0])
    if normalized is None:
        return ProviderCikExtraction("INVALID", None, text, "PROVIDER_CIK_INVALID")
    return ProviderCikExtraction("AVAILABLE", normalized, text, "PROVIDER_CIK_AVAILABLE")
