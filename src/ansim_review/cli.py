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
from ansim_review.contracts.formats import HUMAN_ATTESTATION_STATUS_FORMAT
from ansim_review.contracts.source_batch import SourceBatch, decode_source_batch
from ansim_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2
from ansim_review.evidence.store import EvidenceStore
from ansim_review.math_engine.manifest import calculation_result_document
from ansim_review.math_engine.requests import decode_calculation_request
from ansim_review.math_engine.runner import run_calculation_request
from ansim_review.network_guard import install_network_guard
from ansim_review.parsing.legacy_visual_manifest import (
    inspect_legacy_visual_manifest,
)
from ansim_review.parsing.source_batch_importer import (
    PreparedSource,
    import_source_batch,
    prepare_source_batch,
)
from ansim_review.release.attestation import PROCESS_ATTESTATION, validate_attestation
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
    source_prepare = source_stages.add_parser(
        "prepare",
        help="validate a source batch and report parser and routing states",
    )
    source_prepare.add_argument("--root", required=True, type=Path)
    source_prepare.add_argument("--manifest", required=True, type=Path)
    source_ingest = source_stages.add_parser(
        "ingest",
        help="build a searchable evidence SQLite database from a source batch",
    )
    source_ingest.add_argument("--root", required=True, type=Path)
    source_ingest.add_argument("--manifest", required=True, type=Path)
    source_ingest.add_argument("--output", required=True, type=Path)

    legacy = subparsers.add_parser(
        "legacy",
        help="inspect read-only legacy artifacts without canonical promotion",
    )
    legacy_stages = legacy.add_subparsers(dest="legacy_stage", required=True)
    legacy_visuals = legacy_stages.add_parser(
        "inspect-visual-manifest",
        help="inspect a legacy Grist visual CSV as non-canonical data",
    )
    legacy_visuals.add_argument("--manifest", required=True, type=Path)
    legacy_visuals.add_argument("--root", type=Path)
    legacy_visuals.add_argument("--output", required=True, type=Path)

    release = subparsers.add_parser(
        "release",
        help="validate release authorization artifacts",
    )
    release_stages = release.add_subparsers(dest="release_stage", required=True)
    release_attestation = release_stages.add_parser(
        "validate-attestation",
        help="validate a named process attestation against exact artifact hashes",
    )
    release_attestation.add_argument("--attestation", required=True, type=Path)
    release_attestation.add_argument("--candidate-hash", required=True)
    release_attestation.add_argument("--packet-hash", required=True)

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


def _decode_source_batch_file(manifest: Path) -> SourceBatch:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    return decode_source_batch(payload)


def _source_projection(source: PreparedSource) -> dict[str, object]:
    return {
        "role": source.role,
        "document_id": source.document_id,
        "revision_id": source.revision_id,
        "source_sha256": source.source_sha256,
        "parser_kind": source.parser_kind,
        "state": str(source.state),
        "reason_codes": list(source.reason_codes),
        "can_ingest_reference": source.can_ingest_reference,
        "can_evaluate": source.can_evaluate,
    }


def _preparation_status(sources: Sequence[PreparedSource]) -> str:
    states = {str(source.state) for source in sources}
    if "FAILED" in states:
        return "FAILED"
    if "BLOCKED" in states:
        return "BLOCKED"
    if states == {"READY_TO_EVALUATE"}:
        return "READY_TO_EVALUATE"
    return "PENDING"


def _source_batch_prepare(root: Path, manifest: Path) -> int:
    try:
        batch = _decode_source_batch_file(manifest)
        sources = prepare_source_batch(root, batch)
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
            "version": 2,
            "stage": "prepare",
            "status": _preparation_status(sources),
            "sources": [_source_projection(source) for source in sources],
        }
    )
    return 0


def _source_batch_ingest(root: Path, manifest: Path, output: Path) -> int:
    try:
        batch = _decode_source_batch_file(manifest)
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
            "version": 2,
            "stage": "ingest",
            "status": "INGESTED",
            "output_db": str(report.output_db),
            "snapshot_hash": report.snapshot_hash,
            "counts": report.counts,
            "sources": [
                _source_projection(source) for source in report.sources
            ],
        }
    )
    return 0


def _legacy_visual_inspect(
    manifest: Path,
    root: Path | None,
    output: Path,
) -> int:
    if output.exists():
        print(f"output already exists: {output}", file=sys.stderr)
        return 1
    try:
        report = inspect_legacy_visual_manifest(manifest, root=root)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(dump_bytes(report))
    except FileExistsError:
        print(f"output already exists: {output}", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2

    issues = report.get("issues")
    issue_count = len(issues) if isinstance(issues, list) else 0
    _write_stdout(
        {
            "format": "evidence-review/legacy-visual-inspection-status",
            "version": 1,
            "status": report["status"],
            "output": str(output.resolve()),
            "row_count": report["row_count"],
            "issue_count": issue_count,
            "conversion_supported": report["conversion_supported"],
        }
    )
    return 0


def _release_validate_attestation(
    attestation_path: Path,
    candidate_hash: str,
    packet_hash: str,
) -> int:
    try:
        attestation = validate_attestation(
            attestation_path,
            expected_candidate_hash=candidate_hash,
            expected_packet_hash=packet_hash,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": HUMAN_ATTESTATION_STATUS_FORMAT,
            "version": 1,
            "status": "VALID",
            "assurance_level": PROCESS_ATTESTATION,
            "cryptographic_identity_verified": False,
            "reviewer_id": attestation.reviewer_id,
            "reviewed_at": attestation.reviewed_at.isoformat(),
            "release_candidate_hash": attestation.release_candidate_hash,
            "packet_hash": attestation.packet_hash,
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
        with EvidenceStore(db_path) as store:
            bundle = build_evidence_bundle(store.require_connection(), payload)
    except (
        FileNotFoundError,
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
    if args.command == "source-batch" and args.source_stage == "prepare":
        return _source_batch_prepare(args.root, args.manifest)
    if args.command == "source-batch" and args.source_stage == "ingest":
        return _source_batch_ingest(args.root, args.manifest, args.output)
    if args.command == "legacy" and args.legacy_stage == "inspect-visual-manifest":
        return _legacy_visual_inspect(args.manifest, args.root, args.output)
    if args.command == "release" and args.release_stage == "validate-attestation":
        return _release_validate_attestation(
            args.attestation,
            args.candidate_hash,
            args.packet_hash,
        )
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
