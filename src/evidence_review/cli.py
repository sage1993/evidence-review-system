"""Canonical CLI imports for the evidence review runtime."""

from ansim_review.cli import build_parser
from ansim_review.entrypoint import main

__all__ = ["build_parser", "main"]
