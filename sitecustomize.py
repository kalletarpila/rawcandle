"""Project-level startup hook to ensure flet color compatibility for tests.

This module is automatically imported by site if it's on sys.path. It
attempts to import the installed `flet` package and, if present, ensures
that `flet.Colors` / `flet.colors` expose common color names used across
the codebase and tests (for example `BLUE`, `BLUE_600`, `ORANGE_700`, ...).

This is a minimal, best-effort shim that won't raise if `flet` is missing.
"""

from __future__ import annotations

import sys
import types

_COLORS = {
    "BLUE": "#2196F3",
    "BLUE_600": "#1E88E5",
    "ORANGE_700": "#EF6C00",
    "ORANGE_600": "#FB8C00",
    "ORANGE_400": "#FFB74D",
    "ORANGE_300": "#FFCC80",
    "GREY_600": "#757575",
    "GREY_50": "#FAFAFA",
    "GREEN_700": "#2E7D32",
    "GREEN_600": "#43A047",
    "RED_600": "#E53935",
    "RED_700": "#D32F2F",
    "TRANSPARENT": "transparent",
    "WHITE": "#FFFFFF",
    "BLACK": "#000000",
}


def _ensure(ft_mod: types.ModuleType) -> None:
    # Ensure Colors attribute exists and contains keys
    if not hasattr(ft_mod, "Colors") or ft_mod.Colors is None:

        class _C:  # simple container
            pass

        ft_mod.Colors = _C

    for k, v in _COLORS.items():
        try:
            if not hasattr(ft_mod.Colors, k):
                setattr(ft_mod.Colors, k, v)
        except Exception:
            try:
                ft_mod.Colors.__dict__[k] = v
            except Exception:
                pass

    if not hasattr(ft_mod, "colors"):
        try:
            ft_mod.colors = ft_mod.Colors
        except Exception:
            pass


try:
    import flet as ft  # type: ignore

    _ensure(ft)
except Exception:
    # If flet isn't importable at startup, do nothing. Tests will often
    # patch/mock flet symbols themselves.
    pass
