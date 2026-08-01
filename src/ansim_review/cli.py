"""Command-line interface for the deterministic review runtime."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line parser."""
    return argparse.ArgumentParser(
        prog="ansim-review",
        description="Evidence-first regulatory review runtime",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    parser.parse_args(argv)
    return 0
