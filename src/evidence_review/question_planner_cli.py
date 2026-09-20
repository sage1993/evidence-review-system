"""CLI stages for external question-planner and case-visual handoffs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from evidence_review.canonical_json import dump_bytes
from evidence_review.case_visual import prepare_case_visual_sources
from evidence_review.contracts.attachments import (
    ImmutableAttachment,
    decode_immutable_attachment,
    immutable_attachment_document,
)
from evidence_review.contracts.drawing import drawing_candidate_document
from evidence_review.contracts.question_plan import (
    QuestionPlan,
    decode_question_plan,
    question_plan_document,
)
from evidence_review.contracts.visual_review import (
    decode_visual_analysis_output,
    visual_analysis_output_document,
)
from evidence_review.drawing_review.visual_handoff import (
    prepare_visual_analysis_handoff,
)
from evidence_review.drawing_review.visual_submission import (
    validate_visual_analysis_output,
)
from evidence_review.llm_layer.question_planner import validate_question_planner_output
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.question_planning import (
    prepare_question_planner_handoff,
    question_plan_sha256,
)

_VISUAL_RESUME_FORMAT = "evidence-review/visual-analysis-resume"
_VISUAL_RESUME_VERSION = 1


def _write_stdout(document: object) -> None:
    sys.stdout.buffer.write(dump_bytes(document))


def _write_or_identical(path: Path, document: object) -> None:
    encoded = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        if path.read_bytes() != encoded:
            message = f"existing visual resume artifact differs: {path.name}"
            raise FileExistsError(message) from None


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _prepare_plan_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidence-review review-question prepare-plan"
    )
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
    parser.add_argument("--case-drawing", action="append", default=[], type=Path)
    parser.add_argument("--supporting-image", action="append", default=[], type=Path)
    return parser


def _submit_visual_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidence-review review-question submit-visual-analysis"
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--visual-analysis-id", required=True)
    parser.add_argument("--visual-analysis-output", required=True, type=Path)
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


def _visual_resume_document(
    *,
    question_plan: QuestionPlan,
    expansions: Sequence[str],
    calculations: Sequence[object],
    rules: Sequence[object],
    approved_rule_result_ids: Sequence[str],
    attachments: Sequence[ImmutableAttachment],
) -> dict[str, object]:
    return {
        "format": _VISUAL_RESUME_FORMAT,
        "version": _VISUAL_RESUME_VERSION,
        "question": question_plan.original_question,
        "question_plan": question_plan_document(question_plan),
        "expansions": list(expansions),
        "calculations": list(calculations),
        "rules": list(rules),
        "approved_rule_result_ids": list(approved_rule_result_ids),
        "attachments": [
            immutable_attachment_document(item)
            for item in sorted(attachments, key=lambda item: item.attachment_id)
        ],
    }


def _prepare(arguments: Sequence[str]) -> int:
    args = _prepare_parser().parse_args(arguments)
    try:
        raw_plan = _load_json(args.question_plan_output)
    except FileNotFoundError as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_MISSING", error)
    except (OSError, UnicodeError) as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_UNREADABLE", error)
    except json.JSONDecodeError as error:
        return _planner_failure("QUESTION_PLAN_OUTPUT_INVALID_JSON", error)

    try:
        plan = validate_question_planner_output(
            raw_plan,
            args.question,
            allow_legacy=False,
        )
    except ValueError as error:
        return _planner_failure("QUESTION_PLAN_INVALID", error)

    try:
        calculations = [_load_json(path) for path in args.calculation_result]
        rules = [_load_json(path) for path in args.rule_result]
        visual_attachments = prepare_case_visual_sources(
            args.workspace,
            case_drawings=args.case_drawing,
            supporting_images=args.supporting_image,
        )
        if visual_attachments:
            handoff = prepare_visual_analysis_handoff(
                args.workspace,
                plan,
                visual_attachments,
            )
            _write_or_identical(
                handoff.analysis_directory / "review-resume-input.json",
                _visual_resume_document(
                    question_plan=plan,
                    expansions=args.expansion,
                    calculations=calculations,
                    rules=rules,
                    approved_rule_result_ids=args.approved_rule_result_id,
                    attachments=visual_attachments,
                ),
            )
            _write_stdout(
                {
                    "format": "evidence-review/review-question-status",
                    "version": 1,
                    "stage": "visual-analysis",
                    "status": "WAITING_VISUAL_ANALYSIS",
                    "visual_analysis_id": handoff.visual_analysis_id,
                    "input_bundle": str(handoff.bundle_path),
                    "instructions": str(handoff.instructions_path),
                    "expected_output": str(handoff.expected_output_path),
                    "case_visual_attachment_count": len(visual_attachments),
                }
            )
            return 0

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
        FileExistsError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2

    prepare_status = (
        "RETRIEVAL_NO_EVIDENCE"
        if result.retrieval_guidance_path is not None
        else result.status
    )
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "prepare",
            "status": prepare_status,
            "run_id": result.run_id,
            "question_plan_sha256": question_plan_sha256(plan),
            "next_action_path": (
                None
                if result.next_action_path is None
                else str(result.next_action_path)
            ),
            "resumed": result.resumed,
            "retrieval_guidance_path": (
                None
                if result.retrieval_guidance_path is None
                else str(result.retrieval_guidance_path)
            ),
            "case_visual_attachment_count": 0,
        }
    )
    return 0


def _decode_resume(value: object) -> tuple[
    QuestionPlan,
    tuple[str, ...],
    tuple[object, ...],
    tuple[object, ...],
    tuple[str, ...],
    tuple[ImmutableAttachment, ...],
]:
    payload = _mapping(value, "visual_resume")
    required = {
        "format",
        "version",
        "question",
        "question_plan",
        "expansions",
        "calculations",
        "rules",
        "approved_rule_result_ids",
        "attachments",
    }
    if set(payload) != required:
        raise ValueError("visual resume fields are invalid")
    if (
        payload.get("format") != _VISUAL_RESUME_FORMAT
        or payload.get("version") != 1
    ):
        raise ValueError("unsupported visual resume format")
    question = payload.get("question")
    if not isinstance(question, str) or not question:
        raise ValueError("visual resume question is invalid")
    plan = decode_question_plan(payload.get("question_plan"), question)

    def sequence(field: str) -> Sequence[object]:
        item = payload.get(field)
        if isinstance(item, (str, bytes, bytearray)) or not isinstance(
            item, Sequence
        ):
            raise ValueError(f"visual resume {field} must be an array")
        return cast(Sequence[object], item)

    expansions = tuple(str(item) for item in sequence("expansions"))
    if any(not item for item in expansions):
        raise ValueError("visual resume expansions must be non-empty strings")
    approved = tuple(str(item) for item in sequence("approved_rule_result_ids"))
    if any(not item for item in approved):
        raise ValueError("visual resume approved ids must be non-empty strings")
    attachments = tuple(
        decode_immutable_attachment(item) for item in sequence("attachments")
    )
    return (
        plan,
        expansions,
        tuple(sequence("calculations")),
        tuple(sequence("rules")),
        approved,
        attachments,
    )


def _submit_visual(arguments: Sequence[str]) -> int:
    args = _submit_visual_parser().parse_args(arguments)
    directory = args.workspace / "visual-analysis" / args.visual_analysis_id
    resume_path = directory / "review-resume-input.json"
    try:
        (
            plan,
            expansions,
            calculations,
            rules,
            approved,
            attachments,
        ) = _decode_resume(_load_json(resume_path))
        handoff = prepare_visual_analysis_handoff(
            args.workspace,
            plan,
            attachments,
        )
        if handoff.visual_analysis_id != args.visual_analysis_id:
            raise ValueError("visual analysis resume identity mismatch")
        raw_output = _load_json(args.visual_analysis_output)
        decoded_output = decode_visual_analysis_output(raw_output)
        validated = validate_visual_analysis_output(
            raw_output,
            expected_visual_analysis_id=args.visual_analysis_id,
            question_plan=plan,
            attachments=attachments,
            pages=handoff.pages,
        )
        _write_or_identical(
            directory / "visual-analysis-validated.json",
            visual_analysis_output_document(decoded_output),
        )
        _write_or_identical(
            directory / "drawing-candidates.json",
            {
                "format": "evidence-review/visual-candidates",
                "version": 1,
                "visual_analysis_id": args.visual_analysis_id,
                "candidates": [
                    drawing_candidate_document(item)
                    for item in validated.candidates
                ],
                "candidate_lineage": [
                    {
                        "candidate_id": key,
                        "issue_ids": list(validated.candidate_issue_ids[key]),
                    }
                    for key in sorted(validated.candidate_issue_ids)
                ],
            },
        )
        result = prepare_planned_review_question(
            args.workspace,
            plan,
            expansions,
            calculations=calculations,
            rules=rules,
            approved_rule_result_ids=approved,
            case_visual_attachments=attachments,
            drawing_candidates=validated.candidates,
            candidate_issue_ids=validated.candidate_issue_ids,
            visual_page_assets=handoff.pages,
            visual_analysis_completed=True,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        sqlite3.Error,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2

    status = (
        "RETRIEVAL_NO_EVIDENCE"
        if result.retrieval_guidance_path is not None
        else result.status
    )
    _write_stdout(
        {
            "format": "evidence-review/review-question-status",
            "version": 1,
            "stage": "submit-visual-analysis",
            "status": status,
            "visual_analysis_id": args.visual_analysis_id,
            "visual_candidate_count": len(validated.candidates),
            "run_id": result.run_id,
            "next_action_path": (
                None
                if result.next_action_path is None
                else str(result.next_action_path)
            ),
            "resumed": result.resumed,
        }
    )
    return 0


def dispatch_question_planning(argv: Sequence[str]) -> int | None:
    """Handle staged planner/visual flows; return None for unrelated review stages."""
    if len(argv) < 2 or argv[0] != "review-question":
        return None
    if argv[1] == "prepare-plan":
        return _prepare_plan(argv[2:])
    if argv[1] == "prepare":
        prepare_arguments = argv[2:]
        if "--help" in prepare_arguments or "-h" in prepare_arguments:
            return _prepare(prepare_arguments)
        if "--question-plan-output" not in prepare_arguments:
            return _planner_failure("QUESTION_PLAN_OUTPUT_REQUIRED")
        return _prepare(prepare_arguments)
    if argv[1] == "submit-visual-analysis":
        return _submit_visual(argv[2:])
    return None
