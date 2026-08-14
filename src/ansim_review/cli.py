"""Compatibility wrapper for the canonical Evidence Review command dispatcher."""
from __future__ import annotations

from collections.abc import Sequence


def main(arguments: Sequence[str] | None = None) -> int:
    from ansim_review import command_dispatch

    return command_dispatch.dispatch(arguments)


__all__ = ["main"]
