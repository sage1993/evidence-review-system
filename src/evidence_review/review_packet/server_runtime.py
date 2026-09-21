"""Shared validation and defaults for protected review server lifecycle."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.filesystem_trust import verified_regular_directory

DEFAULT_IDLE_TIMEOUT_SECONDS = 1800


def review_runtime_directory(workspace_root: Path, run_id: str, *, create: bool = False) -> Path:
    """Resolve mutable operational state separately from immutable RUN artifacts."""
    workspace = verified_regular_directory(workspace_root, field="workspace root")
    validated_id = validate_identifier(run_id, "run_id")
    directory = workspace
    for part in (".review-runtime", validated_id):
        candidate = directory / part
        if create:
            candidate.mkdir(exist_ok=True)
        directory = verified_regular_directory(candidate, field="review runtime directory")
    return directory


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
    "review_runtime_directory",
]
