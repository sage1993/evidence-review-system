"""Command-line interface for the deterministic evidence review runtime."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.engines import CalculationResult
from ansim_review.contracts.source_batch import decode_source_batch
from ansim_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2
from ansim_review.math_engine.manifest import calculation_result_document
from ansim_review.math_engine.requests import decode_calculation_request
from ansim_review.math_engine.runner import run_calculation_request
from ansim_review.network_guard import install_network_guard
from ansim_review.parsing.source_batch_importer import import_source_batch
from ansim_review.retrieval.bundle import build_evidence_bundle
from ansim_review.review_run import finalize_review_run, prepare_review_run


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line parser."""
    parser = argparse.ArgumentParser(
        prog="evidence-review",
        description="Evidence-first regulatory review for arbitrary documents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    evidence = subparsers.add_parser(
        "evidence",
        help="manage versioned evidence databases",
    )
    evidence_stages = evidence.add_subparsers(
        dest="evidence_stage",
        required=True,
    )
    evidence_migrate = evidence_stages.add_parser(
        "migrate",
        help="copy an evidence schema v1 database to schema v2",
    )
    evidence_migrate.add_argument("--source", required=True, type=Path)
    evidence_migrate.add_argument("--output", required=True, type=Path)

    source_batch = subparsers.add_parser(
        "source-batch",
        help="validate and ingest arbitrary user-provided PDF sources",
    )
    source_stages = source_batch.add_subparsers(dest="source_stage", required=True)
    source_ingest = source_stages.add_parser(
        "ingest",
        help="build a searchable evidence SQLite database from a source batch",
    )
    source_ingest.add_argument("--root", required=True, type=Path)
    source_ingest.add_argument("--manifest", required=True, type=Path)
    source_ingest.add_argument("--output", required=True, type=Path)

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
    review_stages = review_run.add_subparsers(dest="review_stage", required=True)
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


def _evidence_migrate(source: Path, output: Path) -> int:
    try:
        report = migrate_v1_to_v2(source, output)
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        ValueError,
        RuntimeError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/evidence-migration-status",
            "version": 1,
            "status": "MIGRATED",
            "source_db": str(report.source_db),
            "output_db": str(report.output_db),
            "report": str(report.report_path),
            "source_schema_version": report.source_schema_version,
            "output_schema_version": report.output_schema_version,
            "source_sha256": report.source_sha256,
            "output_sha256": report.output_sha256,
            "logical_snapshot_hash": report.logical_snapshot_hash,
            "counts": report.counts,
        }
    )
    return 0


def _source_batch_ingest(root: Path, manifest: Path, output: Path) -> int:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        batch = decode_source_batch(payload)
        report = import_source_batch(root, batch, output)
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
            "format": "evidence-review/source-batch-cli-status",
            "version": 1,
            "status": "INGESTED",
            "output_db": str(report.output_db),
            "snapshot_hash": report.snapshot_hash,
            "counts": report.counts,
            "sources": [
                {
                    "document_id": source.document_id,
                    "revision_id": source.revision_id,
                    "source_sha256": source.source_sha256,
                    "state": source.state,
                }
                for source in report.sources
            ],
        }
    )
    return 0


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
            stream.write(dump_bytes(calculation_result_document(result)))
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
            "format": "evidence-review/review-run-cli-status",
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
            "format": "evidence-review/review-run-cli-status",
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
    if args.command == "evidence" and args.evidence_stage == "migrate":
        return _evidence_migrate(args.source, args.output)
    if args.command == "source-batch" and args.source_stage == "ingest":
        return _source_batch_ingest(args.root, args.manifest, args.output)
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
    raise RuntimeError("unreachable command state")
