from __future__ import annotations

from dev_tools.inspect_ecosystem_dashboard import main as inspect_main


def main(argv: list[str] | None = None) -> int:
    return inspect_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
