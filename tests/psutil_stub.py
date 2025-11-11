"""
Minimal psutil stub used when the real dependency is not available.

Provides only the Process API surface required by performance-related tests.
"""

from __future__ import annotations

import resource
from dataclasses import dataclass


@dataclass
class _MemoryInfo:
    rss: int


class Process:
    """Lightweight psutil.Process fallback (Linux only)."""

    def __init__(self) -> None:
        self._last_cpu = resource.getrusage(resource.RUSAGE_SELF).ru_utime

    def memory_info(self) -> _MemoryInfo:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = getattr(usage, "ru_maxrss", 0)
        return _MemoryInfo(int(rss_kb * 1024))

    def cpu_percent(self) -> float:
        # Simplified implementation – return 0.0 to keep tests deterministic.
        return 0.0
