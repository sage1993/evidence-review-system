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

from ansim_review.abstention.finalizer import finalize_run
from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.scorer import FactorInput, score_confidence
from ansim_review.contracts.codecs import (
    decode_calculation_result,
    decode_citation,
    decode_rule_result,
)
from ansim_review.contracts.common import Citation
from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.contracts.next_action import NextAction, next_action_document
from ansim_review.contracts.review import ReviewPacket
from ansim_review.contracts.run_context import (
    compute_run_id_from_request,
    create_run_directory,
)
from ansim_review.llm_layer.track_a import (
    EvidenceExcerpt,
    TrackABundle,
    build_track_a_bundle,
    track_a_bundle_document,
    validate_track_a_output,
)
from ansim_review.llm_layer.track_b import validate_track_b_output
from ansim_review.llm_layer.validators import validate_track_a_integrity
from ansim_review.review_packet.browser_launcher import (
    close_open_review_server,
    open_protected_review_workspace,
    wait_for_open_review_server,
)
from ansim_review.review_packet.builder import build_review_view_model
from ansim_review.review_packet.external_launcher import open_external_url
from ansim_review.review_packet.html_renderer import write_review_html

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


def _write_json_or_identical(path: Path, document: object) -> None:
    encoded = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise FileExistsError(f"existing artifact differs: {path.name}") from None


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
    return {
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
        if set(factor) != {"value", "source"}:
            raise ValueError(
                f"confidence factor {name} must contain value and source"
            )
        value_text = _string(
            factor.get("value"), f"confidence_input.factors.{name}.value"
        )
        source = _string(
            factor.get("source"), f"confidence_input.factors.{name}.source"
        )
        factors[name] = FactorInput(value=value_text, source=source)
        document[name] = {"value": value_text, "source": source}
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
        template_root = Path(__file__).with_name("llm_layer") / "templates"
        _write_text(
            run_directory / "TRACK_A_INSTRUCTIONS.md",
            (template_root / "track-a.md").read_text(encoding="utf-8"),
        )
        _write_text(
            run_directory / "TRACK_B_INSTRUCTIONS.md",
            (template_root / "track-b.md").read_text(encoding="utf-8"),
        )
        _write_json(
            run_directory / "prepare-status.json",
            {
                "format": "evidence-review/review-run-prepare-status",
                "version": 1,
                "run_id": run_id,
                "state": "AWAITING_TRACK_OUTPUTS",
                "required_outputs": [
                    "track-a-output.json",
                    "track-b-output.json",
                ],
            },
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
    run_directory = workspace_root / "runs" / run_id
    if not run_directory.is_dir():
        raise FileNotFoundError(run_directory)
    for name in ("track-a-bundle.json", "confidence-input.json"):
        path = run_directory / name
        if not path.is_file():
            raise FileNotFoundError(path)
    return run_directory


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
    ) = _decode_request(run_directory / "review-request.json")
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


def _track_b_action(run_id: str) -> NextAction:
    return NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=run_id,
        workflow_state="WAITING_TRACK_B",
        action="PRODUCE_TRACK_B",
        input_bundle="track-a-output.json",
        instructions="TRACK_B_INSTRUCTIONS.md",
        expected_output="track-b-output.json",
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


def submit_track_a(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
) -> SubmittedTrackA:
    """Validate Track A now; emit Track B only after all validations pass."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    output = validate_track_a_submission(workspace_root, run_id, track_a_output)
    _write_json_or_identical(run_directory / "track-a-output.json", output)
    action_path = run_directory / "next-action-track-b.json"
    _write_json_or_identical(action_path, next_action_document(_track_b_action(run_id)))
    _write_json_or_identical(
        run_directory / "track-a-validation.json",
        {
            "format": "evidence-review/track-a-validation",
            "version": 1,
            "run_id": run_id,
            "status": "VALIDATED",
            "track_a_sha256": _sha256(run_directory / "track-a-output.json"),
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
) -> FinalizedReviewRun:
    """Reject incomplete Track B output before the existing finalizer can run."""
    validate_track_b_submission(workspace_root, run_id, track_b_output)
    run_directory = _require_prepared_run(workspace_root, run_id)
    track_a_path = run_directory / "track-a-output.json"
    return finalize_review_run(
        workspace_root,
        run_id,
        track_a_path,
        track_b_output,
        publish=publish,
    )


def validate_track_b_submission(
    workspace_root: Path,
    run_id: str,
    track_b_output: Path,
) -> None:
    """Validate Track B against the immutable, validated Track A handoff."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    track_a_path = run_directory / "track-a-output.json"
    if not track_a_path.is_file():
        raise ValueError("Track A must validate before Track B submission")
    bundle = _track_a_bundle_for_run(run_directory)
    validated_a = validate_track_a_output(_json(track_a_path), bundle)
    validate_track_a_integrity(validated_a, bundle)
    validate_track_b_output(_json(track_b_output), validated_a)


def _validate_track_output_run_id(value: object, run_id: str, field: str) -> None:
    payload = _mapping(value, field)
    if payload.get("run_id") != run_id:
        raise ValueError(f"{field} run_id does not match prepared run")


def _evidence_database(workspace_root: Path) -> Path:
    generic = workspace_root / "evidence" / "evidence.sqlite"
    if generic.is_file():
        return generic
    legacy = workspace_root / "evidence" / "ansim-evidence.sqlite"
    if legacy.is_file():
        return legacy
    raise FileNotFoundError(generic)


def finalize_review_run(
    workspace_root: Path,
    run_id: str,
    track_a_output: Path,
    track_b_output: Path,
    *,
    publish: bool = False,
) -> FinalizedReviewRun:
    """Bind external Track outputs, finalize, render, and optionally publish."""
    run_directory = _require_prepared_run(workspace_root, run_id)
    track_a_document = _json(track_a_output)
    track_b_document = _json(track_b_output)
    _validate_track_output_run_id(track_a_document, run_id, "track_a")
    _validate_track_output_run_id(track_b_document, run_id, "track_b")

    imported_a = run_directory / "track-a-output.json"
    imported_b = run_directory / "track-b-output.json"
    prevalidated_track_a = imported_a.exists()
    if prevalidated_track_a and track_a_output.resolve() != imported_a.resolve():
        raise FileExistsError(imported_a)

    generated = (
        run_directory / "track-b-output.json",
        run_directory / "run-manifest.json",
        run_directory / "final-review-packet.json",
        run_directory / "review.html",
    )
    existing = next((path for path in generated if path.exists()), None)
    if existing is not None:
        raise FileExistsError(existing)
    published = workspace_root / "runs" / "final-review-packet.json"
    if publish and published.exists():
        raise FileExistsError(published)

    manifest_path = run_directory / "run-manifest.json"
    packet_path = run_directory / "final-review-packet.json"
    html_path = run_directory / "review.html"
    cleanup = [imported_b, manifest_path, packet_path, html_path]
    if not prevalidated_track_a:
        cleanup.append(imported_a)
    try:
        if not prevalidated_track_a:
            _write_json(imported_a, track_a_document)
        _write_json(imported_b, track_b_document)
        artifacts = {
            name: _sha256(run_directory / name)
            for name in _FINALIZER_ARTIFACTS
        }
        _write_json(
            manifest_path,
            {"run_id": run_id, "artifacts": artifacts},
        )
        packet = finalize_run(run_directory)
        evidence_db = _evidence_database(workspace_root)
        view_model = build_review_view_model(packet_path.read_bytes(), evidence_db)
        write_review_html(
            view_model,
            workspace_root / "page-images",
            html_path,
        )
        published_path: Path | None = None
        if publish:
            with published.open("xb") as stream:
                stream.write(packet_path.read_bytes())
            published_path = published
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
