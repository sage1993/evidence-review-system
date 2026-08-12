"""Dependency-safe construction of the evidence-review CLI parser."""

from __future__ import annotations

import argparse
from pathlib import Path


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
    evidence_lineage = evidence_stages.add_parser(
        "migrate-lineage",
        help="copy equivalent legacy document aliases into one canonical lineage",
    )
    evidence_lineage.add_argument("--source", required=True, type=Path)
    evidence_lineage.add_argument("--manifest", required=True, type=Path)
    evidence_lineage.add_argument("--output", required=True, type=Path)

    source_batch = subparsers.add_parser(
        "source-batch",
        help="validate and ingest arbitrary user-provided PDF sources",
    )
    source_stages = source_batch.add_subparsers(
        dest="source_stage",
        required=True,
    )
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

    parser_command = subparsers.add_parser(
        "parser",
        help="validate parser warnings and reproducibility without rerunning parsing",
    )
    parser_stages = parser_command.add_subparsers(
        dest="parser_stage",
        required=True,
    )
    reproducibility = parser_stages.add_parser(
        "reproducibility",
        help="compare two immutable OpenDataLoader parser runs",
    )
    reproducibility_actions = reproducibility.add_subparsers(
        dest="parser_action",
        required=True,
    )
    reproducibility_validate = reproducibility_actions.add_parser(
        "validate",
        help="write a canonical two-run reproducibility report",
    )
    reproducibility_validate.add_argument("--source", required=True, type=Path)
    reproducibility_validate.add_argument("--run-a", required=True, type=Path)
    reproducibility_validate.add_argument("--run-b", required=True, type=Path)
    reproducibility_validate.add_argument("--config", required=True, type=Path)
    reproducibility_validate.add_argument("--output", required=True, type=Path)

    parser_warnings = parser_stages.add_parser(
        "warnings",
        help="collect parser warnings into review evidence",
    )
    warning_actions = parser_warnings.add_subparsers(
        dest="parser_action",
        required=True,
    )
    warning_collect = warning_actions.add_parser(
        "collect",
        help="write a warning report and stable review queue",
    )
    warning_collect.add_argument(
        "--source-manifest",
        required=True,
        type=Path,
    )
    warning_collect.add_argument(
        "--parser-artifacts",
        required=True,
        type=Path,
    )
    warning_collect.add_argument("--config", required=True, type=Path)
    warning_collect.add_argument("--warning-output", required=True, type=Path)
    warning_collect.add_argument("--queue-output", required=True, type=Path)
    warning_collect.add_argument("--previous-queue", type=Path)

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
    legacy_grist_qa = legacy_stages.add_parser(
        "validate-grist-qa",
        help="validate a manual Grist Desktop QA artifact",
    )
    legacy_grist_qa.add_argument("--artifact", required=True, type=Path)
    legacy_grist_qa.add_argument("--root", required=True, type=Path)

    release = subparsers.add_parser(
        "release",
        help="validate release authorization artifacts",
    )
    release_stages = release.add_subparsers(
        dest="release_stage",
        required=True,
    )
    release_attestation = release_stages.add_parser(
        "validate-attestation",
        help="validate a named process attestation against exact artifact hashes",
    )
    release_attestation.add_argument("--attestation", required=True, type=Path)
    release_attestation.add_argument("--candidate-hash", required=True)
    release_attestation.add_argument("--packet-hash", required=True)

    rules = subparsers.add_parser(
        "rules",
        help="run governed rule golden tests, activation, and scope selection",
    )
    rule_stages = rules.add_subparsers(dest="rules_stage", required=True)
    run_golden = rule_stages.add_parser(
        "run-golden",
        help="evaluate one strict rule golden fixture manifest",
    )
    run_golden.add_argument("--repository-root", required=True, type=Path)
    run_golden.add_argument("--fixture-manifest", required=True, type=Path)
    run_golden.add_argument("--actual-root", required=True, type=Path)
    run_golden.add_argument("--report", required=True, type=Path)
    run_golden.add_argument("--source-commit", required=True)
    run_golden.add_argument("--command", required=True, dest="golden_command")

    build_active = rule_stages.add_parser(
        "build-active-manifest",
        help="derive a scoped active manifest from verified approval artifacts",
    )
    build_active.add_argument("--repository-root", required=True, type=Path)
    build_active.add_argument("--approvals", required=True, type=Path)
    build_active.add_argument("--output", required=True, type=Path)
    build_active.add_argument("--report", required=True, type=Path)

    select_rules = rule_stages.add_parser(
        "select",
        help="verify active authority and select exact-scope rules",
    )
    select_rules.add_argument("--repository-root", required=True, type=Path)
    select_rules.add_argument("--manifest", required=True, type=Path)
    select_rules.add_argument("--context", required=True, type=Path)

    documentation = subparsers.add_parser(
        "documentation",
        help="validate repository documentation integrity",
    )
    documentation_stages = documentation.add_subparsers(
        dest="documentation_stage",
        required=True,
    )
    documentation_validate = documentation_stages.add_parser(
        "validate",
        help="write a canonical documentation integrity report",
    )
    documentation_validate.add_argument(
        "--repository-root",
        required=True,
        type=Path,
    )
    documentation_validate.add_argument("--config", required=True, type=Path)
    documentation_validate.add_argument("--output", required=True, type=Path)

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

    review_question = subparsers.add_parser(
        "review-question",
        help="retrieve evidence and drive one staged formal review run",
    )
    question_stages = review_question.add_subparsers(
        dest="review_question_stage",
        required=True,
    )
    question_prepare = question_stages.add_parser(
        "prepare",
        help="retrieve evidence and emit the Track A handoff",
    )
    question_prepare.add_argument("--workspace", required=True, type=Path)
    question_prepare.add_argument("--question", required=True)
    question_prepare.add_argument("--expansion", action="append", default=[])
    question_prepare.add_argument("--calculation-result", action="append", default=[], type=Path)
    question_prepare.add_argument("--rule-result", action="append", default=[], type=Path)
    question_prepare.add_argument("--approved-rule-result-id", action="append", default=[])
    question_track_a = question_stages.add_parser(
        "submit-track-a",
        help="validate Track A before issuing the Track B handoff",
    )
    question_track_a.add_argument("--workspace", required=True, type=Path)
    question_track_a.add_argument("--run-id", required=True)
    question_track_a.add_argument("--track-a-output", required=True, type=Path)
    question_track_b = question_stages.add_parser(
        "submit-track-b",
        help="validate Track B then finalize the prepared review run",
    )
    question_track_b.add_argument("--workspace", required=True, type=Path)
    question_track_b.add_argument("--run-id", required=True)
    question_track_b.add_argument("--track-b-output", required=True, type=Path)
    question_track_b.add_argument("--publish", action="store_true")

    review_run = subparsers.add_parser(
        "review-run",
        help="prepare or finalize an immutable staged review run",
    )
    review_stages = review_run.add_subparsers(
        dest="review_stage",
        required=True,
    )
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
    review_finalize.add_argument(
        "--open",
        action="store_true",
        help="open the finalized review workspace through its protected loopback route",
    )
    review_serve_status = review_stages.add_parser("serve-status")
    review_serve_status.add_argument("--workspace", required=True, type=Path)
    review_serve_status.add_argument("--run-id", required=True)
    review_serve_stop = review_stages.add_parser("serve-stop")
    review_serve_stop.add_argument("--workspace", required=True, type=Path)
    review_serve_stop.add_argument("--run-id", required=True)
    return parser
