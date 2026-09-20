"""Command-line interface for the deterministic evidence review runtime."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.cli_parser import build_parser
from evidence_review.contracts.engines import CalculationResult
from evidence_review.contracts.formats import HUMAN_ATTESTATION_STATUS_FORMAT
from evidence_review.contracts.source_batch import SourceBatch, decode_source_batch
from evidence_review.evidence.lineage_migration import apply_legacy_lineage_migration
from evidence_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2
from evidence_review.evidence.store import EvidenceStore
from evidence_review.filesystem_trust import verified_regular_file
from evidence_review.math_engine.manifest import calculation_result_document
from evidence_review.math_engine.requests import decode_calculation_request
from evidence_review.math_engine.runner import run_calculation_request
from evidence_review.parsing.legacy_grist_qa import (
    derive_grist_qa_status,
    grist_qa_status_document,
    load_and_validate_grist_qa,
)
from evidence_review.parsing.legacy_visual_manifest import (
    inspect_legacy_visual_manifest,
)
from evidence_review.parsing.source_batch_importer import (
    PreparedSource,
    import_source_batch,
    prepare_source_batch,
)
from evidence_review.release.attestation import PROCESS_ATTESTATION, validate_attestation
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.review_matter.contracts import ReviewMatter, review_matter_document
from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.review_matter.store import MatterStoreError
from evidence_review.review_question import (
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from evidence_review.review_run import (
    TrackBContractError,
    finalize_review_run,
    open_review_run,
    prepare_review_run,
    review_run_server_status,
    serve_review_run,
    stop_review_run_server,
)
from evidence_review.rule_engine.activation import (
    activation_report_bytes,
    build_active_manifest_from_directory,
)
from evidence_review.rule_engine.golden import run_rule_golden
from evidence_review.rule_engine.manifest import load_governed_active_rules
from evidence_review.rule_engine.selection import (
    load_rule_selection_context,
    rule_selection_result_bytes,
)

__all__ = ["build_parser", "dispatch"]


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


def _rules_build_active_manifest(
    repository_root: Path,
    approvals: Path,
    output: Path,
    report_path: Path,
) -> int:
    try:
        result = build_active_manifest_from_directory(
            repository_root,
            approvals,
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
        trusted_db_path = verified_regular_file(
            db_path,
            field="evidence database",
        )
        with EvidenceStore(trusted_db_path, read_only=True) as store:
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


def _matter_document(
    stage: str, status: str, matter: ReviewMatter
) -> dict[str, object]:
    return {
        "format": "evidence-review/review-matter-cli-status",
        "version": 1,
        "stage": stage,
        "status": status,
        "matter": review_matter_document(matter),
    }


def _review_matter_dispatch(args: argparse.Namespace) -> int:
    """Delegate every Matter mutation to the canonical application service."""
    try:
        service = ReviewMatterService.open(args.workspace)
        stage = args.review_matter_stage
        if stage == "create":
            _write_stdout(
                _matter_document("create", "MATTER_CREATED", service.create(
                    matter_id=args.matter_id, title=args.title
                ))
            )
            return 0
        if stage == "status":
            _write_stdout(
                _matter_document(
                    "status", "MUTABLE_MATTER_WORK", service.status(matter_id=args.matter_id)
                )
            )
            return 0
        if stage == "add-issue":
            _write_stdout(
                _matter_document(
                    "add-issue",
                    "MATTER_UPDATED",
                    service.add_issue(
                        matter_id=args.matter_id,
                        expected_revision=args.expected_revision,
                        issue_id=args.issue_id,
                        question=args.question,
                        work_state=args.work_state,
                        depends_on=args.depends_on,
                    ),
                )
            )
            return 0
        if stage == "bind-evidence":
            _write_stdout(
                _matter_document(
                    "bind-evidence",
                    "MATTER_EVIDENCE_BOUND",
                    service.bind_evidence(
                        matter_id=args.matter_id,
                        expected_revision=args.expected_revision,
                    ),
                )
            )
            return 0
        if stage == "search":
            navigation_result = service.search(
                matter_id=args.matter_id,
                query=args.query,
                limit=args.limit,
            )
            _write_stdout(
                {
                    "format": "evidence-review/review-matter-cli-status",
                    "version": 1,
                    "stage": "search",
                    "status": "NAVIGATION_RESULTS",
                    "query": navigation_result.query,
                    "evidence_snapshot_hash": navigation_result.evidence_snapshot_hash,
                    "evidence_db_sha256": navigation_result.evidence_db_sha256,
                    "hits": [
                        {
                            "evidence_id": hit.evidence_id,
                            "document_id": hit.document_id,
                            "revision_id": hit.revision_id,
                            "page_number": hit.page_number,
                            "bbox": [
                                hit.bbox.left,
                                hit.bbox.bottom,
                                hit.bbox.right,
                                hit.bbox.top,
                            ],
                            "source_hash": hit.source_hash,
                            "title": hit.title,
                            "text": hit.text,
                            "citation_id": hit.citation.citation_id,
                        }
                        for hit in navigation_result.hits
                    ],
                }
            )
            return 0
        if stage == "select-evidence":
            _write_stdout(
                _matter_document(
                    "select-evidence",
                    "MATTER_EVIDENCE_SELECTED",
                    service.select_evidence(
                        matter_id=args.matter_id,
                        expected_revision=args.expected_revision,
                        query=args.query,
                        evidence_id=args.evidence_id,
                        limit=args.limit,
                    ),
                )
            )
            return 0
        if stage == "formalize":
            formalized = service.formalize(
                matter_id=args.matter_id,
                expected_revision=args.expected_revision,
            )
            _write_stdout(
                {
                    "format": "evidence-review/review-matter-cli-status",
                    "version": 1,
                    "stage": "formalize",
                    "status": formalized.prepared.status,
                    "matter_id": formalized.snapshot.matter_id,
                    "matter_revision": formalized.snapshot.matter_revision,
                    "snapshot_id": formalized.snapshot.snapshot_id,
                    "run_id": formalized.prepared.run_id,
                    "run_directory": str(
                            service.workspace / "runs" / formalized.prepared.run_id
                    ),
                    "next_action_path": str(formalized.prepared.next_action_path),
                }
            )
            return 0
        raise RuntimeError("unreachable review-matter command state")
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        MatterStoreError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2


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
            "retrieval_guidance_path": (
                None
                if result.retrieval_guidance_path is None
                else str(result.retrieval_guidance_path)
            ),
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
    open_browser: bool,
) -> int:
    try:
        result = submit_question_track_b(workspace, run_id, output, publish=publish)
    except TrackBContractError as error:
        _write_stdout(
            {
                "format": "evidence-review/review-question-status",
                "version": 1,
                "stage": "submit-track-b",
                "status": "FAILED",
                "reason_code": error.reason_code,
                "run_id": run_id,
            }
        )
        return 2
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

    document: dict[str, object] = {
        "format": "evidence-review/review-question-status",
        "version": 1,
        "stage": "submit-track-b",
        "status": result.packet.status,
        "run_id": result.run_id,
        "packet": str(result.packet_path),
        "review_html": str(result.review_html),
        "published_packet": (
            None if result.published_packet is None else str(result.published_packet)
        ),
    }
    if open_browser:
        try:
            url = open_review_run(workspace, result.run_id)
        except (OSError, RuntimeError, ValueError) as error:
            document["display_status"] = "OPEN_FAILED"
            document["display_error"] = str(error)
        else:
            document["display_status"] = "OPENED"
            document["url"] = url

    _write_stdout(document)
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


def dispatch(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
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
    if args.command == "review-matter":
        return _review_matter_dispatch(args)
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
            open_browser=args.open,
        )
    if args.command == "review-run" and args.review_stage == "prepare":
        return _review_run_prepare(args.workspace, args.request)
    if args.command == "review-run" and args.review_stage == "response":
        from evidence_review.review_packet.formal_response import (
            build_formal_response,
            validate_formal_response,
        )

        try:
            if args.response_input is None:
                response = build_formal_response(args.workspace, args.run_id)
            else:
                source = verified_regular_file(args.response_input, field="response input")
                response = validate_formal_response(
                    json.loads(source.read_text(encoding="utf-8")),
                    args.workspace,
                    args.run_id,
                )
            _write_stdout(response)
            return 0
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
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
