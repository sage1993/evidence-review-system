"""Command-line interface for the deterministic evidence review runtime."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.cli_parser import build_parser
from ansim_review.contracts.engines import CalculationResult
from ansim_review.contracts.formats import HUMAN_ATTESTATION_STATUS_FORMAT
from ansim_review.contracts.source_batch import SourceBatch, decode_source_batch
from ansim_review.evidence.lineage_migration import apply_legacy_lineage_migration
from ansim_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2
from ansim_review.evidence.store import EvidenceStore
from ansim_review.math_engine.manifest import calculation_result_document
from ansim_review.math_engine.requests import decode_calculation_request
from ansim_review.math_engine.runner import run_calculation_request
from ansim_review.network_guard import install_network_guard
from ansim_review.parsing.legacy_grist_qa import (
    derive_grist_qa_status,
    grist_qa_status_document,
    load_and_validate_grist_qa,
)
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
from ansim_review.review_question import (
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from ansim_review.review_run import (
    finalize_review_run,
    open_review_run,
    prepare_review_run,
    review_run_server_status,
    serve_review_run,
    stop_review_run_server,
)
from ansim_review.rule_engine.activation import (
    activation_report_bytes,
    build_active_manifest,
)
from ansim_review.rule_engine.golden import run_rule_golden
from ansim_review.rule_engine.manifest import load_governed_active_rules
from ansim_review.rule_engine.selection import (
    load_rule_selection_context,
    rule_selection_result_bytes,
)

__all__ = ["build_parser", "main"]


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


def _evidence_migrate_lineage(
    source: Path,
    manifest: Path,
    output: Path,
) -> int:
    try:
        result = apply_legacy_lineage_migration(source, manifest, output)
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
            "format": "evidence-review/legacy-lineage-migration-status",
            "version": 1,
            "status": "MIGRATED",
            "output_database": str(result.output_database),
            "aliases": str(result.aliases_path),
            "report": str(result.report_path),
            "output_sha256": result.output_sha256,
            "logical_lineage_digest": result.logical_lineage_digest,
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
            "sources": [_source_projection(source) for source in report.sources],
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


def _legacy_grist_qa_validate(artifact_path: Path, root: Path) -> int:
    try:
        artifact, artifact_hash = load_and_validate_grist_qa(
            artifact_path,
            root,
        )
    except (
        FileNotFoundError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2

    status = derive_grist_qa_status(artifact)
    _write_stdout(grist_qa_status_document(artifact, artifact_hash))
    return 0 if status == "PASS" else 1


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


def _rules_run_golden(
    repository_root: Path,
    fixture_manifest: Path,
    actual_root: Path,
    report_path: Path,
    source_commit: str,
    command: str,
) -> int:
    try:
        report = run_rule_golden(
            repository_root,
            fixture_manifest,
            actual_root,
            report_path,
            source_commit=source_commit,
            command=command,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/rule-golden-cli-status",
            "version": 1,
            "status": report.status,
            "rule_id": report.rule_id,
            "rule_version": report.rule_version,
            "report": str(report_path),
            "case_count": report.case_count,
            "passed_count": report.passed_count,
            "failed_count": report.failed_count,
        }
    )
    return 0 if report.status == "PASS" else 2


def _approval_files(approvals: Path) -> tuple[Path, ...]:
    if approvals.is_symlink() or not approvals.is_dir():
        raise ValueError("approvals must be a real directory")
    paths = tuple(
        sorted(
            (
                path
                for path in approvals.iterdir()
                if path.suffix == ".json" and path.is_file() and not path.is_symlink()
            ),
            key=lambda path: path.name,
        )
    )
    return paths


def _rules_build_active_manifest(
    repository_root: Path,
    approvals: Path,
    output: Path,
    report_path: Path,
) -> int:
    try:
        result = build_active_manifest(
            repository_root,
            _approval_files(approvals),
            output,
            report_path,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(activation_report_bytes(result))
    return 0 if result.status == "ACTIVATED" else 2


def _rules_select(
    repository_root: Path,
    manifest: Path,
    context_path: Path,
) -> int:
    try:
        context_payload = json.loads(context_path.read_text(encoding="utf-8"))
        context = load_rule_selection_context(context_payload)
        loaded = load_governed_active_rules(repository_root, manifest, context)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(rule_selection_result_bytes(loaded.selection))
    return 2 if loaded.selection.status == "BLOCKED" else 0


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


def _review_question_prepare(
    workspace: Path,
    question: str,
    expansions: Sequence[str],
    calculation_paths: Sequence[Path],
    rule_paths: Sequence[Path],
    approved_rule_result_ids: Sequence[str],
) -> int:
    try:
        calculations = [json.loads(path.read_text(encoding="utf-8")) for path in calculation_paths]
        rules = [json.loads(path.read_text(encoding="utf-8")) for path in rule_paths]
        result = prepare_review_question(
            workspace,
            question,
            expansions,
            calculations=calculations,
            rules=rules,
            approved_rule_result_ids=approved_rule_result_ids,
        )
    except (
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "prepare",
            "status": result.status,
            "run_id": result.run_id,
            "next_action_path": (
                None if result.next_action_path is None else str(result.next_action_path)
            ),
            "resumed": result.resumed,
        }
    )
    return 0


def _review_question_submit_track_a(
    workspace: Path,
    run_id: str,
    output: Path,
) -> int:
    try:
        result = submit_question_track_a(workspace, run_id, output)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "submit-track-a",
            "status": "WAITING_TRACK_B",
            "run_id": result.run_id,
            "next_action_path": str(result.next_action_path),
        }
    )
    return 0


def _review_question_submit_track_b(
    workspace: Path,
    run_id: str,
    output: Path,
    *,
    publish: bool,
) -> int:
    try:
        result = submit_question_track_b(workspace, run_id, output, publish=publish)
    except (
        FileExistsError,
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
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "submit-track-b",
            "status": result.packet.status,
            "run_id": result.run_id,
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
    open_browser: bool,
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
    if open_browser:
        try:
            url = open_review_run(workspace, result.run_id)
        except (OSError, RuntimeError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
        _write_stdout(
            {
                "status": result.packet.status,
                "run_id": result.run_id,
                "url": url,
            }
        )
    else:
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
                    None if result.published_packet is None else str(result.published_packet)
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
    if args.command == "evidence" and args.evidence_stage == "migrate-lineage":
        return _evidence_migrate_lineage(args.source, args.manifest, args.output)
    if args.command == "source-batch" and args.source_stage == "prepare":
        return _source_batch_prepare(args.root, args.manifest)
    if args.command == "source-batch" and args.source_stage == "ingest":
        return _source_batch_ingest(args.root, args.manifest, args.output)
    if args.command == "legacy" and args.legacy_stage == "inspect-visual-manifest":
        return _legacy_visual_inspect(args.manifest, args.root, args.output)
    if args.command == "legacy" and args.legacy_stage == "validate-grist-qa":
        return _legacy_grist_qa_validate(args.artifact, args.root)
    if args.command == "release" and args.release_stage == "validate-attestation":
        return _release_validate_attestation(
            args.attestation,
            args.candidate_hash,
            args.packet_hash,
        )
    if args.command == "rules" and args.rules_stage == "run-golden":
        return _rules_run_golden(
            args.repository_root,
            args.fixture_manifest,
            args.actual_root,
            args.report,
            args.source_commit,
            args.golden_command,
        )
    if args.command == "rules" and args.rules_stage == "build-active-manifest":
        return _rules_build_active_manifest(
            args.repository_root,
            args.approvals,
            args.output,
            args.report,
        )
    if args.command == "rules" and args.rules_stage == "select":
        return _rules_select(args.repository_root, args.manifest, args.context)
    if args.command == "math-run":
        return _math_run(args.request, args.output)
    if args.command == "query":
        return _query_run(args.db, args.request, args.output)
    if args.command == "review-question" and args.review_question_stage == "prepare":
        return _review_question_prepare(
            args.workspace,
            args.question,
            args.expansion,
            args.calculation_result,
            args.rule_result,
            args.approved_rule_result_id,
        )
    if args.command == "review-question" and args.review_question_stage == "submit-track-a":
        return _review_question_submit_track_a(
            args.workspace,
            args.run_id,
            args.track_a_output,
        )
    if args.command == "review-question" and args.review_question_stage == "submit-track-b":
        return _review_question_submit_track_b(
            args.workspace,
            args.run_id,
            args.track_b_output,
            publish=args.publish,
        )
    if args.command == "review-run" and args.review_stage == "prepare":
        return _review_run_prepare(args.workspace, args.request)
    if args.command == "review-run" and args.review_stage == "finalize":
        return _review_run_finalize(
            args.workspace,
            args.run_id,
            args.track_a_output,
            args.track_b_output,
            publish=args.publish,
            open_browser=args.open,
        )
    if args.command == "review-run" and args.review_stage == "serve":
        try:
            url = serve_review_run(
                args.workspace,
                args.run_id,
                reviewer_id=args.reviewer_id,
                idle_timeout_seconds=args.idle_timeout_seconds,
            )
            _write_stdout(
                {
                    "run_id": args.run_id,
                    "url": url,
                    "detached": args.detach,
                    "idle_timeout_seconds": args.idle_timeout_seconds,
                }
            )
            return 0
        except (OSError, RuntimeError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
    if args.command == "review-run" and args.review_stage == "serve-status":
        try:
            _write_stdout(review_run_server_status(args.workspace, args.run_id))
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
    if args.command == "review-run" and args.review_stage == "serve-stop":
        try:
            stop_review_run_server(args.workspace, args.run_id)
            _write_stdout({"run_id": args.run_id, "stopped": True})
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
    raise RuntimeError("unreachable command state")
