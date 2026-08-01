"""Command-line interface for the deterministic review runtime."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.engines import CalculationResult
from ansim_review.math_engine.manifest import calculation_result_document
from ansim_review.math_engine.requests import decode_calculation_request
from ansim_review.math_engine.runner import run_calculation_request
from ansim_review.network_guard import install_network_guard
from ansim_review.retrieval.bundle import build_evidence_bundle


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line parser."""
    parser = argparse.ArgumentParser(
        prog="ansim-review",
        description="Evidence-first regulatory review runtime",
    )
    subparsers = parser.add_subparsers(dest="command")
    math_run = subparsers.add_parser(
        "math-run",
        help="run a deterministic calculation request",
    )
    math_run.add_argument("--request", required=True, type=Path)
    math_run.add_argument("--output", required=True, type=Path)
    query = subparsers.add_parser(
        "query",
        help="retrieve a deterministic evidence bundle",
    )
    query.add_argument("--db", required=True, type=Path)
    query.add_argument("--request", required=True, type=Path)
    query.add_argument("--output", required=True, type=Path)
    return parser


def _result_exit_code(result: CalculationResult) -> int:
    if result.status == "ENGINE_ERROR":
        return 3
    if result.status == "SUCCESS":
        return 0
    return 2


def _math_run(request_path: Path, output_path: Path) -> int:
    if output_path.exists():
        print(f"output already exists: {output_path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        request = decode_calculation_request(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    result = run_calculation_request(request)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("xb") as stream:
            stream.write(
                dump_bytes(calculation_result_document(result))
            )
    except FileExistsError:
        print(f"output already exists: {output_path}", file=sys.stderr)
        return 1
    return _result_exit_code(result)


def _query_run(
    db_path: Path,
    request_path: Path,
    output_path: Path,
) -> int:
    if output_path.exists():
        print(f"output already exists: {output_path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            bundle = build_evidence_bundle(connection, payload)
    except (
        OSError,
        json.JSONDecodeError,
        sqlite3.Error,
        ValueError,
        RuntimeError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("xb") as stream:
            stream.write(dump_bytes(bundle))
    except FileExistsError:
        print(f"output already exists: {output_path}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    install_network_guard()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "math-run":
        return _math_run(args.request, args.output)
    if args.command == "query":
        return _query_run(args.db, args.request, args.output)
    return 0
