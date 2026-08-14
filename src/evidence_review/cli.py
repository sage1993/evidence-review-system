"""Stdlib-only CLI bootstrap with runtime provenance preflight."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evidence_review.diagnostics import collect_runtime_diagnostics, preflight_runtime

__all__ = ["main", "build_parser"]  # noqa: F822

def __getattr__(name: str) -> object:
    if name == "build_parser":
        from ansim_review.cli_parser import build_parser

        return build_parser
    raise AttributeError(name)


def _doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repository-root", type=Path)
    return parser


def _write_json(document: object) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True))


def _source_version() -> str:
    try:
        return importlib.metadata.version("evidence-review-system")
    except importlib.metadata.PackageNotFoundError:
        return "0+source"


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    if arguments == ["--version"]:
        print(_source_version())
        return 0

    if arguments and arguments[0] == "doctor":
        doctor = _doctor_parser().parse_args(arguments[1:])
        result = collect_runtime_diagnostics(doctor.repository_root)
        _write_json(result.to_document())
        return 0 if result.status in {"OK", "NOT_A_CHECKOUT"} else 2

    result = preflight_runtime()
    if result.status in {"SOURCE_MISMATCH", "DEPENDENCY_MISSING"}:
        _write_json(result.to_document())
        return 2

    from ansim_review.entrypoint import main as runtime_main

    return runtime_main(arguments)
