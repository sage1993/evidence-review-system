"""CLI stages for the external AI question-planner handoff."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.llm_layer.question_planner import validate_question_planner_output
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.question_planning import (
    prepare_question_planner_handoff,
    question_plan_sha256,
)


def _write_stdout(document: object) -> None:
    sys.stdout.buffer.write(dump_bytes(document))


def _prepare_plan_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-review review-question prepare-plan")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--question", required=True)
    return parser


def _prepare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-review review-question prepare")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--question-plan-output", required=True, type=Path)
    parser.add_argument("--expansion", action="append", default=[])
    parser.add_argument("--calculation-result", action="append", default=[], type=Path)
    parser.add_argument("--rule-result", action="append", default=[], type=Path)
    parser.add_argument("--approved-rule-result-id", action="append", default=[])
    return parser


def _prepare_plan(arguments: Sequence[str]) -> int:
    args = _prepare_plan_parser().parse_args(arguments)
    try:
        handoff = prepare_question_planner_handoff(args.workspace, args.question)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "prepare-plan",
            "status": "WAITING_QUESTION_PLAN",
            "planning_directory": str(handoff.planning_directory),
            "input_bundle": str(handoff.bundle_path),
            "instructions": str(handoff.instructions_path),
            "expected_output": str(handoff.expected_output_path),
        }
    )
    return 0


def _planner_failure(reason_code: str, error: Exception | None = None) -> int:
    if error is not None:
        print(str(error), file=sys.stderr)
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "prepare",
            "status": "PLANNER_FAILED",
            "reason_code": reason_code,
        }
    )
    return 2


def _prepare(arguments: Sequence[str]) -> int:
    args = _prepare_parser().parse_args(arguments)
    try:
        raw_plan = json.loads(args.question_plan_output.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_MISSING", error)
    except (OSError, UnicodeError) as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_UNREADABLE", error)
    except json.JSONDecodeError as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_INVALID_JSON", error)

    try:
        plan = validate_question_planner_output(raw_plan, args.question)
    except ValueError as error:
        return _planner_failure("QUESTION_PLAN_INVALID", error)

    try:
        calculations = [
            json.loads(path.read_text(encoding="utf-8")) for path in args.calculation_result
        ]
        rules = [json.loads(path.read_text(encoding="utf-8")) for path in args.rule_result]
        result = prepare_planned_review_question(
            args.workspace,
            plan,
            args.expansion,
            calculations=calculations,
            rules=rules,
            approved_rule_result_ids=args.approved_rule_result_id,
        )
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
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
            "stage": "prepare",
            "status": result.status,
            "run_id": result.run_id,
            "question_plan_sha256": question_plan_sha256(plan),
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


def dispatch_question_planning(argv: Sequence[str]) -> int | None:
    """Handle the staged planner flow; return None for unrelated review-question stages."""
    if len(argv) < 2 or argv[0] != "review-question":
        return None
    if argv[1] == "prepare-plan":
        return _prepare_plan(argv[2:])
    if argv[1] == "prepare" and "--question-plan-output" in argv[2:]:
        return _prepare(argv[2:])
    return None
