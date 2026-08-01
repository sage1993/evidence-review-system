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
from ansim_review.review_run import finalize_review_run, prepare_review_run


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

    review_run = subparsers.add_parser(
        "review-run",
        help="prepare or finalize an immutable staged review run",
    )
    review_stages = review_run.add_subparsers(dest="review_stage")
    review_prepare = review_stages.add_parser(
        "prepare",
        help="validate deterministic inputs and prepare Track A artifacts",
    )
    review_prepare.add_argument("--workspace", required=True, type=Path)
    review_prepare.add_argument("--request", required=True, type=Path)
    review_finalize = review_stages.add_parser(
        "finalize",
        help="bind external Track outputs and finalize the review packet",
    )
    review_finalize.add_argument("--workspace", required=True, type=Path)
    review_finalize.add_argument("--run-id", required=True)
    review_finalize.add_argument("--track-a-output", required=True, type=Path)
    review_finalize.add_argument("--track-b-output", required=True, type=Path)
    review_finalize.add_argument("--publish", action="store_true")
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


def _write_stdout(document: object) -> None:
    sys.stdout.buffer.write(dump_bytes(document))


def _review_run_prepare(workspace: Path, request: Path) -> int:
    try:
        result = prepare_review_run(workspace, request)
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "ansim/review-run-cli-status",
            "version": 1,
            "stage": "prepare",
            "status": "AWAITING_TRACK_OUTPUTS",
            "run_id": result.run_id,
            "run_directory": str(result.run_directory),
            "track_a_bundle": str(result.track_a_bundle),
            "confidence_input": str(result.confidence_input),
        }
    )
    return 0


def _review_run_finalize(
    workspace: Path,
    run_id: str,
    track_a_output: Path,
    track_b_output: Path,
    *,
    publish: bool,
) -> int:
    try:
        result = finalize_review_run(
            workspace,
            run_id,
            track_a_output,
            track_b_output,
            publish=publish,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "ansim/review-run-cli-status",
            "version": 1,
            "stage": "finalize",
            "status": result.packet.status,
            "run_id": result.run_id,
            "run_directory": str(result.run_directory),
            "packet": str(result.packet_path),
            "review_html": str(result.review_html),
            "published_packet": (
                None
                if result.published_packet is None
                else str(result.published_packet)
            ),
        }
    )
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
    if args.command == "review-run" and args.review_stage == "prepare":
        return _review_run_prepare(args.workspace, args.request)
    if args.command == "review-run" and args.review_stage == "finalize":
        return _review_run_finalize(
            args.workspace,
            args.run_id,
            args.track_a_output,
            args.track_b_output,
            publish=args.publish,
        )
    return 0
