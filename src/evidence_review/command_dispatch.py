"""Fail-closed canonical CLI dispatch for governance-sensitive commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from evidence_review import cli_handlers as runtime_handlers
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.documentation_integrity.cli import run_documentation_validation
from evidence_review.network_guard import install_network_guard
from evidence_review.review_packet.browser_launcher import (
    open_protected_review_workspace,
    serve_review_server,
)
from evidence_review.review_packet.decision_record import import_human_decision_envelope
from evidence_review.review_packet.external_launcher import open_external_url
from evidence_review.rule_engine.activation import (
    activation_report_bytes,
    build_active_manifest,
)
from evidence_review.rule_engine.manifest import load_governed_active_rules
from evidence_review.rule_engine.selection import (
    load_rule_selection_context_bytes,
    rule_selection_result_bytes,
)


def _approval_entries(directory: Path) -> tuple[Path, ...]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("approvals must be a real directory")
    return tuple(
        sorted(
            (path for path in directory.iterdir() if path.suffix == ".json"),
            key=lambda path: path.name,
        )
    )


def _build_active(args: argparse.Namespace) -> int:
    repository_root = cast(Path, args.repository_root)
    approvals = cast(Path, args.approvals)
    output = cast(Path, args.output)
    report_path = cast(Path, args.report)
    try:
        result = build_active_manifest(
            repository_root,
            _approval_entries(approvals),
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


def _select(args: argparse.Namespace) -> int:
    repository_root = cast(Path, args.repository_root)
    manifest = cast(Path, args.manifest)
    context_path = cast(Path, args.context)
    try:
        context = load_rule_selection_context_bytes(context_path.read_bytes())
        loaded = load_governed_active_rules(repository_root, manifest, context)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(rule_selection_result_bytes(loaded.selection))
    return 2 if loaded.selection.status == "BLOCKED" else 0


def _documentation_validate(args: argparse.Namespace) -> int:
    return run_documentation_validation(
        cast(Path, args.repository_root),
        cast(Path, args.config),
        cast(Path, args.output),
    )


def _parser_dispatch(args: argparse.Namespace) -> int:
    from evidence_review.parser_reproducibility.cli import (
        collect_warnings_command,
        validate_command,
    )

    if args.parser_stage == "reproducibility" and args.parser_action == "validate":
        return validate_command(
            cast(Path, args.source),
            cast(Path, args.run_a),
            cast(Path, args.run_b),
            cast(Path, args.config),
            cast(Path, args.output),
        )
    if args.parser_stage == "warnings" and args.parser_action == "collect":
        return collect_warnings_command(
            cast(Path, args.source_manifest),
            cast(Path, args.parser_artifacts),
            cast(Path, args.config),
            cast(Path, args.warning_output),
            cast(Path, args.queue_output),
            cast(Path | None, args.previous_queue),
        )
    raise RuntimeError("unreachable parser command state")


def _review_serve(args: argparse.Namespace) -> int:
    workspace = cast(Path, args.workspace)
    run_id = cast(str, args.run_id)
    reviewer_id = cast(str | None, args.reviewer_id)
    try:
        if args.detach:
            url = serve_review_server(
                workspace,
                run_id,
                reviewer_id=reviewer_id,
                idle_timeout_seconds=args.idle_timeout_seconds,
            )
            status = "DETACHED"
        else:
            url = open_protected_review_workspace(
                workspace,
                run_id,
                browser=open_external_url,
                reviewer_id=reviewer_id,
            )
            status = "OPENED"
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    payload = {
        "format": "evidence-review/review-run-cli-status",
        "version": 1,
        "stage": "serve",
        "status": status,
        "run_id": run_id,
        "reviewer_id": reviewer_id,
        "url": url,
    }
    if args.detach:
        payload["detached"] = True
        payload["idle_timeout_seconds"] = args.idle_timeout_seconds
    sys.stdout.buffer.write(dump_bytes(payload))
    return 0


def _review_import_decision(args: argparse.Namespace) -> int:
    workspace = cast(Path, args.workspace)
    run_id = validate_identifier(cast(str, args.run_id), "run_id")
    envelope_path = cast(Path, args.envelope)
    run_directory = workspace / "runs" / run_id
    packet_path = run_directory / "final-review-packet.json"
    try:
        packet_bytes = packet_path.read_bytes()
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        packet_hash = hashlib.sha256(packet_bytes).hexdigest()
        output = import_human_decision_envelope(
            run_directory,
            envelope,
            expected_packet_hash=packet_hash,
        )
    except FileExistsError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(
        dump_bytes(
            {
                "format": "evidence-review/review-run-cli-status",
                "version": 1,
                "stage": "import-decision",
                "status": "RECORDED",
                "run_id": run_id,
                "decision_record": str(output),
            }
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch strict commands and delegate the remaining legacy-compatible CLI."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    install_network_guard()

    if len(arguments) >= 2 and arguments[0] == "review-question":
        from evidence_review.question_planner_cli import dispatch_question_planning

        planned_result = dispatch_question_planning(arguments)
        if planned_result is not None:
            return planned_result

    if len(arguments) >= 2 and arguments[:2] == ["documentation", "validate"]:
        args = runtime_handlers.build_parser().parse_args(arguments)
        return _documentation_validate(args)
    if arguments and arguments[0] == "parser":
        args = runtime_handlers.build_parser().parse_args(arguments)
        return _parser_dispatch(args)
    if len(arguments) >= 2 and arguments[0] == "review-run":
        if arguments[1] in {"serve", "import-decision"}:
            args = runtime_handlers.build_parser().parse_args(arguments)
            if args.review_stage == "serve":
                return _review_serve(args)
            if args.review_stage == "import-decision":
                return _review_import_decision(args)
            raise RuntimeError("unreachable review command state")
    if len(arguments) < 2 or arguments[0] != "rules":
        return runtime_handlers.dispatch(arguments)
    if arguments[1] not in {"build-active-manifest", "select"}:
        return runtime_handlers.dispatch(arguments)

    args = runtime_handlers.build_parser().parse_args(arguments)
    if args.rules_stage == "build-active-manifest":
        return _build_active(args)
    if args.rules_stage == "select":
        return _select(args)
    raise RuntimeError("unreachable governance command state")
