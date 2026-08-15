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

_COMPATIBILITY_HANDLER_NAMES = frozenset(
    {
        "_result_exit_code",
        "apply_legacy_lineage_migration",
        "finalize_review_run",
        "import_source_batch",
        "open_review_run",
        "prepare_review_run",
        "prepare_source_batch",
        "serve_review_run",
        "submit_question_track_b",
        "wait_for_review_run",
        "close_review_run",
    }
)


def __getattr__(name: str) -> object:
    if name == "build_parser":
        from evidence_review.cli_parser import build_parser

        return build_parser
    if name in _COMPATIBILITY_HANDLER_NAMES:
        from evidence_review import cli_handlers

        return getattr(cli_handlers, name)
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

    if arguments in (["--help"], ["-h"]):
        from evidence_review.cli_parser import build_parser

        build_parser().print_help()
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

    from evidence_review.question_planner_cli import dispatch_question_planning

    planned_result = dispatch_question_planning(arguments)
    if planned_result is not None:
        return planned_result

    import evidence_review.command_dispatch as runtime_dispatch
    from evidence_review import cli_handlers as runtime_handlers
    from evidence_review.command_dispatch import main as runtime_main

    for hook_name in _COMPATIBILITY_HANDLER_NAMES:
        if hook_name in globals():
            setattr(runtime_handlers, hook_name, globals()[hook_name])
    if "serve_review_run" in globals():
        setattr(runtime_dispatch, "serve_review_server", globals()["serve_review_run"])  # noqa: B010

    return runtime_main(arguments)
