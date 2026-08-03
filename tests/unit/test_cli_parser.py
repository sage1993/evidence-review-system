"""Regression tests for shared CLI parser construction."""

from ansim_review.cli import build_parser as legacy_build_parser
from ansim_review.cli_parser import build_parser
from evidence_review.cli import build_parser as canonical_build_parser


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
