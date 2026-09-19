"""Staged offline orchestration for immutable evidence review runs."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.scorer import FactorInput, score_confidence
from evidence_review.contracts.codecs import (
    decode_calculation_result,
    decode_citation,
    decode_rule_result,
)
from evidence_review.contracts.common import Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.contracts.next_action import NextAction, next_action_document
from evidence_review.contracts.review import ConfidenceFactorState, ReviewPacket, TrackBAudit
from evidence_review.contracts.run_context import (
    compute_run_id_from_request,
    create_run_directory,
)
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    TrackABundle,
    build_track_a_bundle,
    track_a_bundle_document,
    validate_track_a_output,
)
from evidence_review.llm_layer.track_b import (
    required_facet_completeness_status,
    track_b_semantic_gate_status,
    validate_track_b_output,
)
from evidence_review.llm_layer.validators import validate_track_a_integrity
from evidence_review.observability.run_metrics import append_stage, finish_stage, start_stage
from evidence_review.review_packet.browser_launcher import (
    close_open_review_server,
    open_protected_review_workspace,
    review_server_status,
    serve_review_server,
    stop_review_server,
    wait_for_open_review_server,
)
from evidence_review.review_packet.builder import build_review_view_model
from evidence_review.review_packet.external_launcher import open_external_url
from evidence_review.review_packet.html_renderer import write_review_html
from evidence_review.review_packet.page_image_verifier import verify_review_page_images
from evidence_review.review_packet.server_runtime import DEFAULT_IDLE_TIMEOUT_SECONDS
from evidence_review.workflow.artifact_ownership import TRACK_A_DERIVED

_RUN_ID = re.compile(r"^RUN-[0-9A-F]{20}$")
_REQUEST_FIELDS = {
    "format",
    "version",
    "question",
    "inputs",
    "evidence",
    "calculations",
    "rules",
    "approved_rule_result_ids",
    "confidence_input",
}
_REQUEST_FORMATS = {
    "ansim/review-run-request",
    "evidence-review/review-run-request",
}
_FINALIZER_ARTIFACTS = (
    "track-a-bundle.json",
    "track-a-output.json",
    "track-b-output.json",
    "confidence-input.json",
)
_PREPARE_STATUS_FORMAT = "evidence-review/review-run-prepare-status"
_PREPARE_REQUIRED_OUTPUTS = ("track-a-output.json", "track-b-output.json")
_PREPARE_INSTRUCTION_TEMPLATES = {
    "TRACK_A_INSTRUCTIONS.md": "track-a.md",
    "TRACK_B_INSTRUCTIONS.md": "track-b.md",
}


class TrackBContractError(ValueError):
    """Stable error for Track B ownership and retry contract violations."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class PreparedReviewRun:
    """Paths created by the deterministic preparation stage."""

    run_id: str
    run_directory: Path
    track_a_bundle: Path
    confidence_input: Path


@dataclass(frozen=True, slots=True)
class FinalizedReviewRun:
    """Artifacts created by finalization and optional publication."""

    run_id: str
    run_directory: Path
    packet: ReviewPacket
    packet_path: Path
    review_html: Path
    published_packet: Path | None


@dataclass(frozen=True, slots=True)
class SubmittedTrackA:
    """A validated Track A submission and the only permitted next handoff."""

    run_id: str
    run_directory: Path
    next_action_path: Path


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, str | bytes | bytearray) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{field} must be {qualifier}")
    return value


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(dump_bytes(document))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _prepared_instruction_text(name: str) -> str:
    """Return the exact tracked instruction text for a prepared-run artifact."""
    try:
        template_name = _PREPARE_INSTRUCTION_TEMPLATES[name]
    except KeyError as error:
        raise ValueError(f"unsupported prepared instruction artifact: {name}") from error
    template_root = Path(__file__).with_name("llm_layer") / "templates"
    return (template_root / template_name).read_text(encoding="utf-8")


def _prepare_status_document(run_id: str) -> dict[str, object]:
    """Build the canonical status record produced with every prepared run."""
    return {
        "format": _PREPARE_STATUS_FORMAT,
        "version": 1,
        "run_id": run_id,
        "state": "AWAITING_TRACK_OUTPUTS",
        "required_outputs": list(_PREPARE_REQUIRED_OUTPUTS),
    }


def _write_json_or_identical(path: Path, document: object) -> None:
    encoded = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        existing = verified_regular_file_below(
            path.parent,
            (path.name,),
            field=f"run artifact {path.name}",
        )
        if existing.read_bytes() != encoded:
            raise FileExistsError(f"existing artifact differs: {path.name}") from None


def _publish_validated_track_a(
    source: Path,
    destination: Path,
    document: object,
) -> None:
    """Publish validated Track A without rewriting a same-path source."""
    if source.resolve() == destination.resolve():
        verified_regular_file_below(
            destination.parent,
            (destination.name,),
            field="run-local Track A",
        )
        return
    _write_json_or_identical(destination, document)


def _publish_validated_track_b(
    source: Path,
    destination: Path,
    document: object,
) -> None:
    """Bind a validated Track B without rewriting or replacing user input."""
    if source.resolve() == destination.resolve():
        verified_regular_file_below(
            destination.parent,
            (destination.name,),
            field="run-local Track B",
        )
        return

    encoded = dump_bytes(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        try:
            trusted_destination = verified_regular_file_below(
                destination.parent,
                (destination.name,),
                field="run-local Track B",
            )
            existing = dump_bytes(_json(trusted_destination))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "existing run-local Track B is not a valid canonical JSON document",
            ) from error
        if existing != encoded:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "existing run-local Track B differs from validated submission",
            ) from None


def _citation_document(citation: Citation) -> dict[str, object]:
    return {
        "citation_id": citation.citation_id,
        "document_id": citation.document_id,
        "revision_id": citation.revision_id,
        "page_number": citation.page_number,
        "evidence_id": citation.evidence_id,
        "bbox": [
            citation.bbox.left,
            citation.bbox.bottom,
            citation.bbox.right,
            citation.bbox.top,
        ],
        "source_hash": citation.source_hash,
    }


def _calculation_document(result: CalculationResult) -> dict[str, object]:
    document: dict[str, object] = {
        "calculation_result_id": result.calculation_result_id,
        "status": result.status,
        "formula_id": result.formula_id,
        "formula_version": result.formula_version,
        "inputs": dict(result.inputs),
        "substitution": result.substitution,
        "raw_result": result.raw_result,
        "display_result": result.display_result,
        "comparison": result.comparison,
        "formula_manifest_hash": result.formula_manifest_hash,
        "result_hash": result.result_hash,
        "error_codes": list(result.error_codes),
    }
    if result.input_sources:
        document["input_sources"] = dict(result.input_sources)
    if result.input_units:
        document["input_units"] = dict(result.input_units)
    if result.precision is not None:
        document["precision"] = result.precision
    if result.rounding is not None:
        document["rounding"] = result.rounding
    if result.intermediate_rounding_policy is not None:
        document["intermediate_rounding_policy"] = result.intermediate_rounding_policy
    return document


def _rule_document(result: RuleResult) -> dict[str, object]:
    return {
        "rule_result_id": result.rule_result_id,
        "rule_id": result.rule_id,
        "rule_version": result.rule_version,
        "status": result.status,
        "citations": [_citation_document(item) for item in result.citations],
        "missing_inputs": list(result.missing_inputs),
        "calculation_result_ids": list(result.calculation_result_ids),
        "reason_codes": list(result.reason_codes),
        "result_hash": result.result_hash,
    }


def _decode_confidence_input(value: object) -> dict[str, object]:
    payload = _mapping(value, "confidence_input")
    if set(payload) != {"factors"}:
        raise ValueError("confidence_input must contain only factors")
    factor_payload = _mapping(payload.get("factors"), "confidence_input.factors")
    factors: dict[str, FactorInput] = {}
    document: dict[str, object] = {}
    for name, item in sorted(factor_payload.items()):
        factor = _mapping(item, f"confidence_input.factors.{name}")
        if set(factor) - {"value", "source", "state"} or set(factor) < {
            "value",
            "source",
        }:
            raise ValueError(
                f"confidence factor {name} must contain value and source"
            )
        value_text = _string(
            factor.get("value"), f"confidence_input.factors.{name}.value"
        )
        source = _string(
            factor.get("source"), f"confidence_input.factors.{name}.source"
        )
        state = factor.get("state", "VERIFIED")
        if state not in {"VERIFIED", "FAILED", "NOT_VERIFIED", "NOT_APPLICABLE"}:
            raise ValueError(f"unsupported confidence factor state: {name}")
        factors[name] = FactorInput(
            value=value_text,
            source=source,
            state=cast(ConfidenceFactorState, state),
        )
        document[name] = {"value": value_text, "source": source, "state": state}
    score_confidence(factors)
    return {"factors": document}


def _decode_request(path: Path) -> tuple[
    str,
    dict[str, object],
    tuple[EvidenceExcerpt, ...],
    tuple[CalculationResult, ...],
    tuple[RuleResult, ...],
    tuple[str, ...],
    dict[str, object],
    dict[str, object],
]:
    payload = _mapping(_json(path), "review_run_request")
    unknown = sorted(set(payload) - _REQUEST_FIELDS)
    missing = sorted(_REQUEST_FIELDS - set(payload))
    if unknown:
        raise ValueError(
            f"review_run_request has unknown fields: {', '.join(unknown)}"
        )
    if missing:
        raise ValueError(
            f"review_run_request is missing fields: {', '.join(missing)}"
        )
    if payload.get("format") not in _REQUEST_FORMATS or payload.get("version") != 1:
        raise ValueError("unsupported review-run request")

    question = _string(payload.get("question"), "question")
    inputs = dict(sorted(_mapping(payload.get("inputs"), "inputs").items()))
    evidence: list[EvidenceExcerpt] = []
    evidence_documents: list[dict[str, object]] = []
    for index, item in enumerate(_sequence(payload.get("evidence"), "evidence")):
        excerpt = _mapping(item, f"evidence[{index}]")
        if set(excerpt) != {"citation", "text"}:
            raise ValueError(
                f"evidence[{index}] must contain citation and text"
            )
        citation = decode_citation(excerpt.get("citation"))
        text = _string(excerpt.get("text"), f"evidence[{index}].text")
        evidence.append(EvidenceExcerpt(citation=citation, text=text))
        evidence_documents.append(
            {"citation": _citation_document(citation), "text": text}
        )

    calculations = tuple(
        decode_calculation_result(item)
        for item in _sequence(payload.get("calculations"), "calculations")
    )
    calculation_ids = [item.calculation_result_id for item in calculations]
    if len(calculation_ids) != len(set(calculation_ids)):
        raise ValueError("calculation_result_ids must be unique")
    for calculation_result in calculations:
        if (
            calculation_result.formula_manifest_hash is None
            or calculation_result.result_hash is None
        ):
            raise ValueError(
                "calculation result is not finalized: "
                f"{calculation_result.calculation_result_id}"
            )

    rules = tuple(
        decode_rule_result(item)
        for item in _sequence(payload.get("rules"), "rules")
    )
    rule_ids = [item.rule_result_id for item in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("rule_result_ids must be unique")
    for rule_result in rules:
        if rule_result.result_hash is None:
            raise ValueError(
                f"rule result is not finalized: {rule_result.rule_result_id}"
            )

    approved = tuple(
        sorted(
            _string(item, f"approved_rule_result_ids[{index}]")
            for index, item in enumerate(
                _sequence(
                    payload.get("approved_rule_result_ids"),
                    "approved_rule_result_ids",
                )
            )
        )
    )
    if len(approved) != len(set(approved)):
        raise ValueError("approved_rule_result_ids must be unique")
    unknown_approved = sorted(set(approved) - set(rule_ids))
    if unknown_approved:
        raise ValueError(
            "approved_rule_result_ids reference unknown rules: "
            + ", ".join(unknown_approved)
        )

    confidence = _decode_confidence_input(payload.get("confidence_input"))
    calculation_documents = [_calculation_document(item) for item in calculations]
    rule_documents = [_rule_document(item) for item in rules]
    normalized_request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": question,
        "inputs": inputs,
        "evidence": evidence_documents,
        "calculations": calculation_documents,
        "rules": rule_documents,
        "approved_rule_result_ids": list(approved),
        "confidence_input": confidence,
    }
    return (
        question,
        inputs,
        tuple(evidence),
        calculations,
        rules,
        approved,
        confidence,
        normalized_request,
    )


def prepare_review_run(
    workspace_root: Path,
    request_path: Path,
) -> PreparedReviewRun:
    """Validate deterministic artifacts and create an immutable prepared run."""
    (
        question,
        inputs,
        evidence,
        calculations,
        rules,
        approved,
        confidence,
        normalized_request,
    ) = _decode_request(request_path)
    run_id = compute_run_id_from_request(normalized_request)
    bundle = build_track_a_bundle(
        run_id=run_id,
        question=question,
        inputs=inputs,
        evidence=evidence,
        rules=rules,
        calculations=calculations,
        approved_rule_result_ids=approved,
    )
    run_directory = create_run_directory(workspace_root / "runs", run_id)
    try:
        request_output = run_directory / "review-request.json"
        bundle_output = run_directory / "track-a-bundle.json"
        confidence_output = run_directory / "confidence-input.json"
        _write_json(request_output, normalized_request)
        _write_json(bundle_output, track_a_bundle_document(bundle))
        _write_json(confidence_output, confidence)
        _write_text(
            run_directory / "TRACK_A_INSTRUCTIONS.md",
            _prepared_instruction_text("TRACK_A_INSTRUCTIONS.md"),
        )
        _write_text(
            run_directory / "TRACK_B_INSTRUCTIONS.md",
            _prepared_instruction_text("TRACK_B_INSTRUCTIONS.md"),
        )
        _write_json(
            run_directory / "prepare-status.json",
            _prepare_status_document(run_id),
        )
    except Exception:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise
    return PreparedReviewRun(
        run_id=run_id,
        run_directory=run_directory,
        track_a_bundle=bundle_output,
        confidence_input=confidence_output,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_prepared_run(workspace_root: Path, run_id: str) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run_id")
    trusted_workspace = verified_regular_directory(
        workspace_root,
        field="workspace root",
    )
    runs_root = verified_regular_directory(
        trusted_workspace / "runs",
        field="runs root",
    )
    run_directory = verified_regular_directory(
        runs_root / run_id,
        field="run directory",
    )
    for name in ("track-a-bundle.json", "confidence-input.json"):
        verified_regular_file_below(
            run_directory,
            (name,),
            field=f"run artifact {name}",
        )
    return run_directory


def _run_file(run_directory: Path, name: str) -> Path:
    return verified_regular_file_below(
        run_directory,
        (name,),
        field=f"run artifact {name}",
    )


def _track_a_bundle_for_run(run_directory: Path) -> TrackABundle:
    (
        question,
        inputs,
        evidence,
        calculations,
        rules,
        approved,
        _confidence,
        _request,
    ) = _decode_request(_run_file(run_directory, "review-request.json"))
    return build_track_a_bundle(
        run_id=run_directory.name,
        question=question,
        inputs=inputs,
        evidence=evidence,
        rules=rules,
        calculations=calculations,
        approved_rule_result_ids=approved,
    )


def validate_track_a_submission(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
) -> object:
    """Perform Track A's full structural and numeric validation before Track B."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    bundle = _track_a_bundle_for_run(run_directory)
    output = _json(track_a_output)
    validated = validate_track_a_output(output, bundle)
    validate_track_a_integrity(validated, bundle)
    return output


def _track_b_bundle_document(
    run_directory: Path,
    run_id: str,
    track_a_document: object,
) -> dict[str, object]:
    """Project validated Track A claims and their immutable evidence for Track B."""
    track_a = _mapping(track_a_document, "track_a")
    claims = [
        dict(_mapping(item, f"track_a.claims[{index}]"))
        for index, item in enumerate(_sequence(track_a.get("claims", []), "track_a.claims"))
    ]
    cited_ids: set[str] = set()
    for index, claim in enumerate(claims):
        for citation_index, item in enumerate(
            _sequence(claim.get("citation_ids", []), f"track_a.claims[{index}].citation_ids")
        ):
            cited_ids.add(
                _string(item, f"track_a.claims[{index}].citation_ids[{citation_index}]")
            )

    request = _mapping(_json(_run_file(run_directory, "review-request.json")), "review_request")
    question = _string(request.get("question"), "review_request.question")
    request_inputs = _mapping(request.get("inputs", {}), "review_request.inputs")
    facet_values = request_inputs.get("facet_coverage", [])
    facet_coverage = [
        dict(_mapping(item, f"review_request.inputs.facet_coverage[{index}]"))
        for index, item in enumerate(
            _sequence(facet_values, "review_request.inputs.facet_coverage")
        )
    ]
    support_by_id: dict[str, dict[str, object]] = {}
    for index, item in enumerate(_sequence(request.get("evidence", []), "review_request.evidence")):
        evidence = _mapping(item, f"review_request.evidence[{index}]")
        citation = _mapping(
            evidence.get("citation"), f"review_request.evidence[{index}].citation"
        )
        citation_id = _string(
            citation.get("citation_id"),
            f"review_request.evidence[{index}].citation.citation_id",
        )
        if citation_id not in cited_ids:
            continue
        support_by_id[citation_id] = {
            "citation": dict(citation),
            "text": _string(
                evidence.get("text"), f"review_request.evidence[{index}].text"
            ),
        }

    missing = sorted(cited_ids - set(support_by_id))
    if missing:
        raise ValueError(
            "validated Track A references unavailable immutable evidence: "
            + ", ".join(missing)
        )
    return {
        "format": "evidence-review/track-b-bundle",
        "version": 1,
        "run_id": run_id,
        "question": question,
        "claims": claims,
        "evidence_support": [support_by_id[item] for item in sorted(cited_ids)],
        "required_facet_completeness": _required_facet_completeness(facet_coverage),
    }


def _required_facet_completeness(
    facet_coverage: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Summarize required-facet coverage without turning it into a conclusion."""
    if not facet_coverage:
        return {
            "status": "NOT_APPLICABLE",
            "covered_issue_count": 0,
            "total_issue_count": 0,
        }
    complete = sum(
        not _sequence(item.get("missing_facet_ids", []), "missing_facet_ids")
        for item in facet_coverage
    )
    total = len(facet_coverage)
    return {
        "status": "COMPLETE" if complete == total else "INCOMPLETE",
        "covered_issue_count": complete,
        "total_issue_count": total,
    }


def _track_b_validation_document(
    run_directory: Path,
    run_id: str,
    track_b_path: Path,
    audit: TrackBAudit,
) -> dict[str, object]:
    """Record immutable runtime metadata for one validated Track B attempt."""
    bundle_path = _run_file(run_directory, "track-b-bundle.json")
    bundle = _mapping(_json(bundle_path), "track_b_bundle")
    return {
        "format": "evidence-review/track-b-validation",
        "version": 2,
        "run_id": run_id,
        "status": "VALIDATED",
        "input_bundle_sha256": _sha256(bundle_path),
        "track_b_sha256": _sha256(track_b_path),
        "audit_attempt_id": f"TRACK-B-{_sha256(track_b_path)[:20].upper()}",
        "generation_context": {
            "source": "external_submission",
            "validator": "evidence_review.llm_layer.track_b.validate_track_b_output",
            "question": bundle.get("question"),
        },
        "question_responsive": audit.question_responsiveness == "PASS",
        "question_responsiveness": audit.question_responsiveness,
        "semantic_gate_status": track_b_semantic_gate_status(audit),
        "required_facet_completeness": bundle.get(
            "required_facet_completeness",
            {"status": "NOT_APPLICABLE", "covered_issue_count": 0, "total_issue_count": 0},
        ),
    }


def _track_b_action(run_id: str) -> NextAction:
    return NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=run_id,
        workflow_state="WAITING_TRACK_B",
        action="PRODUCE_TRACK_B",
        input_bundle="track-b-bundle.json",
        instructions="TRACK_B_INSTRUCTIONS.md",
        expected_output="track-b-attempt-1.json",
        resume_command=(
            "python",
            "-m",
            "evidence_review",
            "review-question",
            "submit-track-b",
            "--run-id",
            run_id,
        ),
        track_a_validated=True,
    )


def _recover_malformed_track_a_submission(run_directory: Path) -> None:
    """Discard malformed runtime-derived Track A sidecars, never canonical input."""
    try:
        canonical = _run_file(run_directory, "track-a-output.json")
    except FileNotFoundError:
        canonical = None
    if canonical is not None:
        try:
            _json(canonical)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(
                "malformed run-local Track A cannot be recovered as validated input"
            ) from error

    for name in sorted(TRACK_A_DERIVED):
        try:
            path = _run_file(run_directory, name)
        except FileNotFoundError:
            continue
        try:
            _json(path)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            for generated_name in TRACK_A_DERIVED:
                (run_directory / generated_name).unlink(missing_ok=True)
            return


def submit_track_a(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
) -> SubmittedTrackA:
    """Validate Track A now; emit Track B only after all validations pass."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    output = validate_track_a_submission(workspace_root, run_id, track_a_output)
    _recover_malformed_track_a_submission(run_directory)
    _publish_validated_track_a(
        track_a_output,
        run_directory / "track-a-output.json",
        output,
    )
    _write_json_or_identical(
        run_directory / "track-b-bundle.json",
        _track_b_bundle_document(run_directory, run_id, output),
    )
    action_path = run_directory / "next-action-track-b.json"
    _write_json_or_identical(action_path, next_action_document(_track_b_action(run_id)))
    _write_json_or_identical(
        run_directory / "track-a-validation.json",
        {
            "format": "evidence-review/track-a-validation",
            "version": 1,
            "run_id": run_id,
            "status": "VALIDATED",
            "track_a_sha256": _sha256(_run_file(run_directory, "track-a-output.json")),
        },
    )
    return SubmittedTrackA(
        run_id=run_id,
        run_directory=run_directory,
        next_action_path=action_path,
    )


def submit_track_b(
    workspace_root: Path,
    run_id: str,
    track_b_output: Path,
    *,
    publish: bool = False,
    prevalidated: bool = False,
) -> FinalizedReviewRun:
    """Bind validated Track B before the finalizer enforces output ownership."""
    if not prevalidated:
        validate_track_b_submission(workspace_root, run_id, track_b_output)
    run_directory = _require_prepared_run(workspace_root, run_id)
    output = _json(track_b_output)
    bound_track_b = run_directory / "track-b-output.json"
    track_a_path = _run_file(run_directory, "track-a-output.json")
    bundle = _track_a_bundle_for_run(run_directory)
    validated_a = validate_track_a_output(_json(track_a_path), bundle)
    validate_track_a_integrity(validated_a, bundle)
    audit = validate_track_b_output(
        output,
        validated_a,
        expected_question=bundle.question,
        expected_facet_completeness=required_facet_completeness_status(
            bundle.inputs.get("facet_coverage")
        ),
    )
    _publish_validated_track_b(track_b_output, bound_track_b, output)
    _write_json_or_identical(
        run_directory / "track-b-validation.json",
        _track_b_validation_document(run_directory, run_id, bound_track_b, audit),
    )
    track_a_path = _run_file(run_directory, "track-a-output.json")
    return finalize_review_run(
        workspace_root,
        run_id,
        track_a_path,
        bound_track_b,
        publish=publish,
        bound_track_b=True,
    )


def validate_track_b_submission(
    workspace_root: Path,
    run_id: str,
    track_b_output: Path,
) -> None:
    """Validate Track B against the immutable, validated Track A handoff."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    try:
        track_a_path = _run_file(run_directory, "track-a-output.json")
    except FileNotFoundError:
        raise ValueError("Track A must validate before Track B submission") from None
    bundle = _track_a_bundle_for_run(run_directory)
    validated_a = validate_track_a_output(_json(track_a_path), bundle)
    validate_track_a_integrity(validated_a, bundle)
    validate_track_b_output(
        _json(track_b_output),
        validated_a,
        expected_question=bundle.question,
        expected_facet_completeness=required_facet_completeness_status(
            bundle.inputs.get("facet_coverage")
        ),
    )


def _validate_track_output_run_id(value: object, run_id: str, field: str) -> None:
    payload = _mapping(value, field)
    if payload.get("run_id") != run_id:
        raise ValueError(f"{field} run_id does not match prepared run")


def _evidence_database(workspace_root: Path) -> Path:
    generic = ("evidence", "evidence.sqlite")
    try:
        return verified_regular_file_below(
            workspace_root,
            generic,
            field="evidence database",
        )
    except FileNotFoundError as generic_error:
        try:
            return verified_regular_file_below(
                workspace_root,
                ("evidence", "ansim-evidence.sqlite"),
                field="legacy evidence database",
            )
        except FileNotFoundError:
            raise generic_error from None


def _record_stage_failure(run_directory: Path, name: str, timer: object, error: Exception) -> None:
    from evidence_review.observability.run_metrics import StageTimer

    if not isinstance(timer, StageTimer):
        raise TypeError("invalid stage timer")
    append_stage(
        run_directory,
        finish_stage(
            name,
            timer,
            status="FAILED",
            reason_code=type(error).__name__.upper(),
        ),
    )


def finalize_review_run(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
    track_b_output: Path,
    *,
    publish: bool = False,
    bound_track_b: bool = False,
) -> FinalizedReviewRun:
    """Bind external Track outputs, finalize, render, and expose the run-local packet."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    track_a_document = _json(track_a_output)
    track_b_document = _json(track_b_output)
    _validate_track_output_run_id(track_a_document, run_id, "track_a")
    _validate_track_output_run_id(track_b_document, run_id, "track_b")

    try:
        imported_a = _run_file(run_directory, "track-a-output.json")
    except FileNotFoundError:
        imported_a = run_directory / "track-a-output.json"
        prevalidated_track_a = False
    else:
        prevalidated_track_a = True
    if prevalidated_track_a and track_a_output.resolve() != imported_a:
        raise FileExistsError(imported_a)
    try:
        imported_b = _run_file(run_directory, "track-b-output.json")
    except FileNotFoundError:
        imported_b = run_directory / "track-b-output.json"

    generated = (
        (
            run_directory / "run-manifest.json",
            run_directory / "final-review-packet.json",
            run_directory / "review.html",
        )
        if bound_track_b
        else (
            run_directory / "track-b-output.json",
            run_directory / "run-manifest.json",
            run_directory / "final-review-packet.json",
            run_directory / "review.html",
        )
    )
    if bound_track_b:
        try:
            imported_b = _run_file(run_directory, "track-b-output.json")
        except FileNotFoundError as error:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "bound Track B must be the validated run-local artifact",
            ) from error
        if track_b_output.resolve() != imported_b:
            raise TrackBContractError(
                "TRACK_B_INPUT_MISMATCH",
                "bound Track B must be the validated run-local artifact",
            )
    existing = None
    for path in generated:
        try:
            existing = _run_file(run_directory, path.name)
        except FileNotFoundError:
            continue
        break
    if existing is not None:
        raise FileExistsError(existing)
    manifest_path = run_directory / "run-manifest.json"
    packet_path = run_directory / "final-review-packet.json"
    html_path = run_directory / "review.html"
    cleanup = list(generated)
    if not prevalidated_track_a:
        cleanup.append(imported_a)
    try:
        if not prevalidated_track_a:
            _write_json(imported_a, track_a_document)
        if not bound_track_b:
            _write_json(imported_b, track_b_document)
        artifacts = {
            name: _sha256(_run_file(run_directory, name))
            for name in _FINALIZER_ARTIFACTS
        }
        _write_json(
            manifest_path,
            {"run_id": run_id, "artifacts": artifacts},
        )

        finalizer_timer = start_stage()
        try:
            packet = finalize_run(run_directory)
        except Exception as error:
            _record_stage_failure(run_directory, "finalizer", finalizer_timer, error)
            raise
        append_stage(run_directory, finish_stage("finalizer", finalizer_timer))

        evidence_db = _evidence_database(workspace_root)
        view_model_timer = start_stage()
        try:
            view_model = build_review_view_model(packet_path.read_bytes(), evidence_db)
        except Exception as error:
            _record_stage_failure(run_directory, "view-model-build", view_model_timer, error)
            raise
        append_stage(run_directory, finish_stage("view-model-build", view_model_timer))

        page_image_timer = start_stage()
        try:
            verify_review_page_images(view_model, workspace_root / "page-images")
        except Exception as error:
            _record_stage_failure(
                run_directory,
                "page-image-verification",
                page_image_timer,
                error,
            )
            raise
        append_stage(
            run_directory,
            finish_stage("page-image-verification", page_image_timer),
        )

        html_timer = start_stage()
        try:
            write_review_html(
                view_model,
                workspace_root / "page-images",
                html_path,
            )
        except Exception as error:
            _record_stage_failure(run_directory, "html-render-write", html_timer, error)
            raise
        append_stage(run_directory, finish_stage("html-render-write", html_timer))

        published_path = packet_path if publish else None
    except Exception:
        for path in cleanup:
            path.unlink(missing_ok=True)
        raise
    return FinalizedReviewRun(
        run_id=run_id,
        run_directory=run_directory,
        packet=packet,
        packet_path=packet_path,
        review_html=html_path,
        published_packet=published_path,
    )


def open_review_run(
    workspace_root: Path,
    run_id: str,
    *,
    browser: Callable[[str], bool] = open_external_url,
) -> str:
    """Open a finalized review run through its protected loopback route."""
    return open_protected_review_workspace(
        workspace_root,
        run_id,
        browser=browser,
    )


def wait_for_review_run(workspace_root: Path, run_id: str) -> None:
    """Wait for the protected browser session opened for one review run."""
    wait_for_open_review_server(workspace_root, run_id)


def close_review_run(workspace_root: Path, run_id: str) -> None:
    """Close the protected browser session opened for one review run."""
    close_open_review_server(workspace_root, run_id)


def review_run_server_status(workspace_root: Path, run_id: str) -> dict[str, object]:
    return review_server_status(workspace_root, run_id)


def serve_review_run(
    workspace_root: Path,
    run_id: str,
    *,
    reviewer_id: str | None = None,
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> str:
    return serve_review_server(
        workspace_root,
        run_id,
        reviewer_id=reviewer_id,
        idle_timeout_seconds=idle_timeout_seconds,
    )


def stop_review_run_server(workspace_root: Path, run_id: str) -> None:
    stop_review_server(workspace_root, run_id)
