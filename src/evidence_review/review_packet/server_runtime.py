"""Shared validation and defaults for protected review server lifecycle."""
from __future__ import annotations

import argparse
import math

DEFAULT_IDLE_TIMEOUT_SECONDS = 1800


def validate_idle_timeout(value: object) -> float:
    """Return a finite positive idle timeout in seconds."""
    if isinstance(value, bool):
        raise ValueError("idle timeout must be a finite positive number")
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        raise ValueError("idle timeout must be a finite positive number") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("idle timeout must be a finite positive number")
    return seconds


def idle_timeout_argument(value: str) -> float:
    try:
        return validate_idle_timeout(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


__all__ = [
    "DEFAULT_IDLE_TIMEOUT_SECONDS",
    "idle_timeout_argument",
    "validate_idle_timeout",
]
