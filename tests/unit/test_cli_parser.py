"""Regression tests for shared CLI parser construction."""

from evidence_review.cli import build_parser as canonical_build_parser
from evidence_review.cli import build_parser as legacy_build_parser
from evidence_review.cli_parser import build_parser


def test_parser_builder_is_shared_and_existing_commands_remain() -> None:
    assert legacy_build_parser is build_parser
    assert canonical_build_parser is build_parser
    parser = build_parser()
    prepared = parser.parse_args(
        ["source-batch", "prepare", "--root", ".", "--manifest", "m.json"]
    )
    selected = parser.parse_args(
        [
            "rules",
            "select",
            "--repository-root",
            ".",
            "--manifest",
            "a.json",
            "--context",
            "c.json",
        ]
    )
    assert prepared.command == "source-batch"
    assert selected.rules_stage == "select"


def test_parser_reproducibility_command_shape() -> None:
    args = build_parser().parse_args(
        [
            "parser",
            "reproducibility",
            "validate",
            "--source",
            "source.pdf",
            "--run-a",
            "run-a",
            "--run-b",
            "run-b",
            "--config",
            "parser-reproducibility.json",
            "--output",
            "report.json",
        ]
    )

    assert args.command == "parser"
    assert args.parser_stage == "reproducibility"
    assert args.parser_action == "validate"
    assert args.source.name == "source.pdf"


def test_parser_warning_command_uses_source_manifest_authority() -> None:
    args = build_parser().parse_args(
        [
            "parser",
            "warnings",
            "collect",
            "--source-manifest",
            "source-batch.json",
            "--parser-artifacts",
            "parser-output",
            "--config",
            "parser-reproducibility.json",
            "--warning-output",
            "warnings.json",
            "--queue-output",
            "queue.json",
        ]
    )

    assert args.parser_stage == "warnings"
    assert args.source_manifest.name == "source-batch.json"
    assert args.parser_artifacts.name == "parser-output"
    assert not hasattr(args, "source")
    assert not hasattr(args, "run")
