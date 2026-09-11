from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d_backend import stage_mock_provider_response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage mocked Phase 13D provider records without network access")
    parser.add_argument("--tickers", required=True)
    parser.add_argument("--response-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage_mock_provider_response(args.tickers, response_json=args.response_json, output=args.output)
        print(json.dumps({"ok": True, "staged": len(result["staged"]), "missing": len(result["missing"]), "output": str(args.output)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
