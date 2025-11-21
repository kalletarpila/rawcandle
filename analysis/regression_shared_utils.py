from __future__ import annotations

from typing import Any, Dict, Iterable


def _legacy_module():
    from regression import run_regression

    return run_regression


def load_blackout_dates(*args, **kwargs):
    return _legacy_module().load_blackout_dates(*args, **kwargs)


def apply_blackout_flags(*args, **kwargs):
    return _legacy_module().apply_blackout_flags(*args, **kwargs)


def preprocess_signals(*args, **kwargs):
    return _legacy_module().preprocess_signals(*args, **kwargs)


__all__ = ["apply_blackout_flags", "load_blackout_dates", "preprocess_signals"]
