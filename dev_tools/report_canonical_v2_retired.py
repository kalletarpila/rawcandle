from __future__ import annotations

import sys


RETIRED_MESSAGE = (
    "Canonical Report V2 has been retired. "
    "See docs/dc_report_v2_retirement_decision.md."
)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    print(RETIRED_MESSAGE, file=sys.stderr)
    return 2
