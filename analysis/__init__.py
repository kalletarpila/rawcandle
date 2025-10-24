"""Analysis package

Provide a small compatibility shim for the `flet` package so that tests
which import analysis.* see the expected `ft.Colors` attributes even if the
installed flet variant exposes a different attribute shape.

This module runs early when `import analysis.*` is performed and augments
the `flet` module with common color constants used in the codebase/tests.
"""

try:
    import flet as ft
except Exception:
    ft = None

if ft is not None:
    """Analysis package

    Provide a small compatibility shim for the `flet` package so that tests
    which import analysis.* see the expected `ft.Colors` attributes even if the
    installed flet variant exposes a different attribute shape.

    This module runs early when `import analysis.*` is performed and augments
    the `flet` module with common color constants used in the codebase/tests.
    """

    try:
        import flet as ft
    except Exception:
        ft = None

    _DEFAULT_COLORS = {
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

    def _ensure_colors_object(ft_module):
        """Ensure ft_module has a Colors attribute with expected color names.

        This function is intentionally idempotent and minimal so importing
        `analysis` cannot fail even if flet is missing or has a different API.
        """
        if not hasattr(ft_module, "Colors") or ft_module.Colors is None:

            class _C:
                pass

            ft_module.Colors = _C

        for name, val in _DEFAULT_COLORS.items():
            # prefer existing value if present
            try:
                if not hasattr(ft_module.Colors, name):
                    setattr(ft_module.Colors, name, val)
            except Exception:
                try:
                    ft_module.Colors.__dict__[name] = val
                except Exception:
                    # best-effort: continue
                    pass

        # Mirror lowercase alias
        if not hasattr(ft_module, "colors"):
            try:
                ft_module.colors = ft_module.Colors
            except Exception:
                pass

    if ft is not None:
        _ensure_colors_object(ft)
