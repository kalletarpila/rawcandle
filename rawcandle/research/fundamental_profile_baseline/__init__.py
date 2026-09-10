"""Phase 12B revised-history fundamental profile baseline."""

from .contract import CONTRACT, CONTRACT_FINGERPRINT, CONTRACT_VERSION
from .runner import RunResult, run
from .source import ResearchPaths

__all__ = [
    "CONTRACT",
    "CONTRACT_FINGERPRINT",
    "CONTRACT_VERSION",
    "ResearchPaths",
    "RunResult",
    "run",
]
