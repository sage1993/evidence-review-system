"""Fail-closed canonical CLI dispatch for governance-sensitive commands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from ansim_review import cli as legacy_cli
from ansim_review.documentation_integrity.cli import run_documentation_validation
from ansim_review.network_guard import install_network_guard
from ansim_review.rule_engine.activation import (
    activation_report_bytes,
    build_active_manifest,
)
from ansim_review.rule_engine.manifest import load_governed_active_rules
from ansim_review.rule_engine.selection import (
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
    from ansim_review.parser_reproducibility.cli import (
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
            cast(Path, args.source),
            cast(Path, args.run),
            cast(Path, args.config),
            cast(Path, args.warning_output),
            cast(Path, args.queue_output),
            cast(Path | None, args.previous_queue),
        )
    raise RuntimeError("unreachable parser command state")


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch governance-sensitive commands strictly and delegate the remainder."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) >= 2 and arguments[:2] == ["documentation", "validate"]:
        install_network_guard()
        args = legacy_cli.build_parser().parse_args(arguments)
        return _documentation_validate(args)
    if arguments and arguments[0] == "parser":
        install_network_guard()
        args = legacy_cli.build_parser().parse_args(arguments)
        return _parser_dispatch(args)
    if len(arguments) < 2 or arguments[0] != "rules":
        return legacy_cli.main(arguments)
    if arguments[1] not in {"build-active-manifest", "select"}:
        return legacy_cli.main(arguments)

    install_network_guard()
    args = legacy_cli.build_parser().parse_args(arguments)
    if args.rules_stage == "build-active-manifest":
        return _build_active(args)
    if args.rules_stage == "select":
        return _select(args)
    raise RuntimeError("unreachable governance command state")
