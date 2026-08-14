"""Single business-command dispatcher for every Evidence Review CLI entrypoint."""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ansim_review import cli_handlers as handlers
from ansim_review.documentation_integrity.validator import run_documentation_integrity
from ansim_review.network_guard import install_network_guard
from ansim_review.parsing.reproducibility import run_reproducibility_validation
from ansim_review.parsing.warnings import collect_parser_warnings
from ansim_review.review_packet.decision_record import import_human_decision_envelope
from ansim_review.review_packet.server_runtime import ReviewWorkspaceServerError
from ansim_review.review_run import (
    open_review_run,
    review_run_server_status,
    serve_review_run,
    stop_review_run_server,
)
from ansim_review.rule_engine.activation import build_active_manifest
from ansim_review.rule_engine.manifest import load_governed_active_rules
from ansim_review.rule_engine.selection import load_rule_selection_context_bytes


__all__ = ["dispatch"]


def _write_stdout(document: object) -> None:
    handlers._write_stdout(document)


def _documentation_validate(
    repository_root: Path,
    config_path: Path,
    output_path: Path,
) -> int:
    try:
        report = run_documentation_integrity(repository_root, config_path, output_path)
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/documentation-integrity-cli-status",
            "version": 1,
            "status": report["status"],
            "output": str(output_path.resolve()),
            "document_count": len(report["documents"]),
            "error_count": report["summary"]["error_count"],
            "warning_count": report["summary"]["warning_count"],
        }
    )
    return 0 if report["status"] == "PASS" else 2


def _parser_reproducibility_validate(
    source_pdf: Path,
    run_a: Path,
    run_b: Path,
    config_path: Path,
    output_path: Path,
) -> int:
    try:
        report = run_reproducibility_validation(
            source_pdf,
            run_a,
            run_b,
            config_path,
            output_path,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/parser-reproducibility-cli-status",
            "version": 1,
            "status": report["status"],
            "output": str(output_path.resolve()),
            "parser": report["parser"],
            "reproducibility": report["reproducibility"],
        }
    )
    return 0 if report["status"] == "PASS" else 2


def _parser_warning_collect(
    source_manifest: Path,
    parser_artifacts: Path,
    config_path: Path,
    warning_output: Path,
    queue_output: Path,
    previous_queue: Path | None,
) -> int:
    try:
        warning_report, queue = collect_parser_warnings(
            source_manifest,
            parser_artifacts,
            config_path,
            warning_output,
            queue_output,
            previous_queue=previous_queue,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/parser-warning-cli-status",
            "version": 1,
            "status": warning_report["status"],
            "warning_output": str(warning_output.resolve()),
            "queue_output": str(queue_output.resolve()),
            "warning_count": warning_report["summary"]["warning_count"],
            "blocking_count": warning_report["summary"]["blocking_count"],
            "queue_count": queue["summary"]["queue_count"],
        }
    )
    return 0 if warning_report["status"] == "PASS" else 2


def _review_import_decision(workspace: Path, run_id: str, envelope_path: Path) -> int:
    run_directory = workspace / "runs" / run_id
    packet_path = run_directory / "final-review-packet.json"
    try:
        packet_hash = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        output = import_human_decision_envelope(
            run_directory,
            envelope,
            expected_packet_hash=packet_hash,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/human-decision-import-status",
            "version": 1,
            "status": "RECORDED",
            "run_id": run_id,
            "decision_record": str(output),
            "packet_hash": packet_hash,
        }
    )
    return 0


def _review_serve(
    workspace: Path,
    run_id: str,
    reviewer_id: str | None,
    detach: bool,
    idle_timeout_seconds: float | None,
) -> int:
    try:
        if detach:
            handle = serve_review_run(
                workspace,
                run_id,
                reviewer_id=reviewer_id,
                detach=True,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        else:
            handle = open_review_run(
                workspace,
                run_id,
                reviewer_id=reviewer_id,
                idle_timeout_seconds=idle_timeout_seconds,
            )
    except (FileNotFoundError, OSError, ValueError, ReviewWorkspaceServerError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/review-run-cli-status",
            "version": 1,
            "stage": "serve",
            "status": "SERVING",
            "run_id": run_id,
            "url": handle.url,
            "detached": detach,
            "reviewer_id": reviewer_id,
            "idle_timeout_seconds": idle_timeout_seconds,
        }
    )
    return 0


def _rules_build_active(
    repository_root: Path,
    approvals: Path,
    output: Path,
    report_path: Path,
) -> int:
    try:
        approval_paths = tuple(
            sorted(
                (
                    path
                    for path in approvals.iterdir()
                    if path.suffix == ".json" and path.is_file() and not path.is_symlink()
                ),
                key=lambda path: path.name,
            )
        )
        result = build_active_manifest(
            repository_root,
            approval_paths,
            output,
            report_path,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(handlers.activation_report_bytes(result))
    return 0 if result.status == "ACTIVATED" else 2


def _rules_select(repository_root: Path, manifest: Path, context_path: Path) -> int:
    try:
        context = load_rule_selection_context_bytes(context_path.read_bytes())
        loaded = load_governed_active_rules(repository_root, manifest, context)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(handlers.rule_selection_result_bytes(loaded.selection))
    return 2 if loaded.selection.status == "BLOCKED" else 0


def dispatch(arguments: Sequence[str] | None = None) -> int:
    """Parse and execute one business command behind one network-guard boundary."""
    install_network_guard()
    parser = handlers.build_parser()
    args = parser.parse_args(arguments)

    if args.command == "documentation" and args.documentation_stage == "validate":
        return _documentation_validate(args.repository_root, args.config, args.output)
    if (
        args.command == "parser"
        and args.parser_stage == "reproducibility"
        and args.parser_action == "validate"
    ):
        return _parser_reproducibility_validate(
            args.source,
            args.run_a,
            args.run_b,
            args.config,
            args.output,
        )
    if (
        args.command == "parser"
        and args.parser_stage == "warnings"
        and args.parser_action == "collect"
    ):
        return _parser_warning_collect(
            args.source_manifest,
            args.parser_artifacts,
            args.config,
            args.warning_output,
            args.queue_output,
            args.previous_queue,
        )
    if args.command == "review-run" and args.review_stage == "serve":
        return _review_serve(
            args.workspace,
            args.run_id,
            args.reviewer_id,
            args.detach,
            args.idle_timeout_seconds,
        )
    if args.command == "review-run" and args.review_stage == "import-decision":
        return _review_import_decision(args.workspace, args.run_id, args.envelope)
    if args.command == "rules" and args.rules_stage == "build-active-manifest":
        return _rules_build_active(
            args.repository_root,
            args.approvals,
            args.output,
            args.report,
        )
    if args.command == "rules" and args.rules_stage == "select":
        return _rules_select(args.repository_root, args.manifest, args.context)

    if args.command == "evidence":
        if args.evidence_stage == "migrate":
            return handlers._evidence_migrate(args.source, args.output)
        if args.evidence_stage == "migrate-lineage":
            return handlers._evidence_migrate_lineage(args.source, args.manifest, args.output)
    if args.command == "source-batch":
        if args.source_stage == "prepare":
            return handlers._source_batch_prepare(args.root, args.manifest)
        if args.source_stage == "ingest":
            return handlers._source_batch_ingest(args.root, args.manifest, args.output)
    if args.command == "release" and args.release_stage == "validate-attestation":
        return handlers._release_validate_attestation(
            args.attestation,
            args.candidate_hash,
            args.packet_hash,
        )
    if args.command == "rules" and args.rules_stage == "run-golden":
        return handlers._rules_run_golden(
            args.repository_root,
            args.fixture_manifest,
            args.actual_root,
            args.report,
            args.source_commit,
            args.golden_command,
        )
    if args.command == "math-run":
        return handlers._math_run(args.request, args.output)
    if args.command == "query":
        return handlers._query_run(args.db, args.request, args.output)
    if args.command == "review-question":
        if args.review_question_stage == "prepare":
            return handlers._review_question_prepare(
                args.workspace,
                args.question,
                args.expansion,
                args.calculation_result,
                args.rule_result,
                args.approved_rule_result_id,
            )
        if args.review_question_stage == "submit-track-a":
            return handlers._review_question_submit_track_a(
                args.workspace,
                args.run_id,
                args.track_a_output,
            )
        if args.review_question_stage == "submit-track-b":
            return handlers._review_question_submit_track_b(
                args.workspace,
                args.run_id,
                args.track_b_output,
                publish=args.publish,
                open_browser=args.open,
            )
    if args.command == "review-run":
        if args.review_stage == "prepare":
            return handlers._review_run_prepare(args.workspace, args.request)
        if args.review_stage == "finalize":
            return handlers._review_run_finalize(
                args.workspace,
                args.run_id,
                args.track_a_output,
                args.track_b_output,
                publish=args.publish,
                open_browser=args.open,
            )
        if args.review_stage == "serve-status":
            try:
                result = review_run_server_status(args.workspace, args.run_id)
            except (FileNotFoundError, OSError, ValueError) as error:
                print(str(error), file=sys.stderr)
                return 2
            _write_stdout(result)
            return 0
        if args.review_stage == "serve-stop":
            try:
                result = stop_review_run_server(args.workspace, args.run_id)
            except (FileNotFoundError, OSError, ValueError) as error:
                print(str(error), file=sys.stderr)
                return 2
            _write_stdout(result)
            return 0

    parser.error("unsupported command")
    return 2
