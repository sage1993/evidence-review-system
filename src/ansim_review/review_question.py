"""Deterministic question-to-review-run orchestration without model calls."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.contracts.codecs import decode_review_packet
from ansim_review.contracts.next_action import NextAction, next_action_document
from ansim_review.contracts.review import FinalizerStatus
from ansim_review.contracts.run_context import compute_run_id_from_request
from ansim_review.contracts.workflow import WorkflowState
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.bundle import build_evidence_bundle
from ansim_review.review_run import (
    FinalizedReviewRun,
    PreparedReviewRun,
    SubmittedTrackA,
    prepare_review_run,
    submit_track_a,
    submit_track_b,
    validate_track_b_submission,
)
from ansim_review.workflow.events import (
    append_workflow_event,
    load_workflow_events,
    make_workflow_event,
)


@dataclass(frozen=True, slots=True)
class PreparedReviewQuestion:
    """The run and safe handoff produced for one fully deterministic question."""

    run_id: str
    status: str
    next_action_path: Path | None
    resumed: bool


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _write_or_identical(path: Path, document: object) -> None:
    encoded = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise FileExistsError(f"existing artifact differs: {path.name}") from None


def canonical_query_request(question: str, expansions: Sequence[str]) -> dict[str, object]:
    """Normalize user-provided expansion terms into the existing query contract."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    normalized_expansions: list[dict[str, str]] = []
    for index, term in enumerate(expansions):
        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"expansion[{index}] must be a non-empty string")
        normalized_expansions.append({"text": term, "origin": "user"})
    return {
        "question": question,
        "expansions": normalized_expansions,
        "synonym_manifest": {},
        "filters": {},
        "clause_ids": [],
        "seed_ids": [],
        "graph_depth": 1,
        "limit": 20,
    }


def build_review_run_request(
    bundle: object,
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> dict[str, object]:
    """Convert retrieval output to the canonical review-run input losslessly."""
    payload = _mapping(bundle, "evidence_bundle")
    query = _mapping(payload.get("query"), "evidence_bundle.query")
    question = query.get("primary")
    if not isinstance(question, str) or not question:
        raise ValueError("evidence_bundle.query.primary must be a non-empty string")
    snapshot_hash = payload.get("snapshot_hash")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        raise ValueError("evidence_bundle.snapshot_hash must be a SHA-256")

    evidence: list[dict[str, object]] = []
    for index, hit in enumerate(_sequence(payload.get("hits"), "evidence_bundle.hits")):
        hit_payload = _mapping(hit, f"evidence_bundle.hits[{index}]")
        citation = hit_payload.get("citation")
        text = hit_payload.get("text")
        if not isinstance(citation, Mapping) or not isinstance(text, str) or not text:
            raise ValueError("retrieval hit requires a traceable citation and text")
        evidence.append({"citation": dict(citation), "text": text})
    calculation_documents = [dict(_mapping(item, "calculation_result")) for item in calculations]
    rule_documents = [dict(_mapping(item, "rule_result")) for item in rules]
    approved = list(approved_rule_result_ids)
    if len(approved) != len(set(approved)):
        raise ValueError("approved_rule_result_ids must be unique")
    known_rule_ids = {
        item.get("rule_result_id")
        for item in rule_documents
        if isinstance(item.get("rule_result_id"), str)
    }
    if set(approved) - known_rule_ids:
        raise ValueError("approved_rule_result_ids reference unknown rules")
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": question,
        "inputs": {"snapshot_hash": snapshot_hash},
        "evidence": evidence,
        "calculations": calculation_documents,
        "rules": rule_documents,
        "approved_rule_result_ids": approved,
        "confidence_input": {
            "factors": {
                name: {"value": "1.0", "source": "retrieval:snapshot_hash"}
                for name in FACTOR_WEIGHTS
            }
        },
    }


def _evidence_database(workspace: Path) -> Path:
    path = workspace / "evidence" / "evidence.sqlite"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _track_a_action(run_id: str) -> NextAction:
    return NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=run_id,
        workflow_state="WAITING_TRACK_A",
        action="PRODUCE_TRACK_A",
        input_bundle="track-a-bundle.json",
        instructions="TRACK_A_INSTRUCTIONS.md",
        expected_output="track-a-output.json",
        resume_command=(
            "python",
            "-m",
            "evidence_review",
            "review-question",
            "submit-track-a",
            "--run-id",
            run_id,
        ),
        track_a_validated=False,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_event(
    run_directory: Path,
    next_state: WorkflowState,
    payload_sha256: str,
    *,
    finalizer_status: FinalizerStatus | None = None,
) -> None:
    events = load_workflow_events(run_directory / "events")
    if events and events[-1].next_state == next_state:
        return
    sequence = len(events) + 1
    previous = events[-1].next_state if events else None
    append_workflow_event(
        run_directory / "events",
        make_workflow_event(
            run_id=run_directory.name,
            sequence=sequence,
            event_id=f"EVT-{sequence:04d}",
            kind="TRANSITION",
            previous_state=previous,
            next_state=next_state,
            finalizer_status=finalizer_status,
            reason_codes=(),
            resumable=False,
            payload_sha256=payload_sha256,
            recorded_at=_now(),
        ),
    )


def _initialize_events(run_directory: Path) -> None:
    """Write the ordered journal once, after immutable preparation succeeds."""
    request_hash = _sha256(run_directory / "review-request.json")
    bundle_hash = _sha256(run_directory / "track-a-bundle.json")
    stages: tuple[tuple[WorkflowState, str], ...] = (
        ("RECEIVED", request_hash),
        ("CLASSIFYING_INPUTS", request_hash),
        ("READY_TO_EVALUATE", request_hash),
        ("RETRIEVING_EVIDENCE", bundle_hash),
        ("RUNNING_MATH", bundle_hash),
        ("RUNNING_RULES", bundle_hash),
        ("WAITING_TRACK_A", bundle_hash),
    )
    for state, payload_hash in stages:
        _append_event(run_directory, state, payload_hash)


def _resume_state(run_directory: Path) -> tuple[str, Path | None]:
    events = load_workflow_events(run_directory / "events")
    if not events:
        _initialize_events(run_directory)
        events = load_workflow_events(run_directory / "events")
    state = events[-1].next_state
    if state == "WAITING_TRACK_A":
        path = run_directory / "next-action-track-a.json"
    elif state == "WAITING_TRACK_B":
        path = run_directory / "next-action-track-b.json"
    elif state in {"FINALIZING", "READY_FOR_REVIEW"}:
        finalized = _existing_finalized_run(run_directory)
        if finalized is not None:
            _append_event(
                run_directory,
                "READY_FOR_REVIEW",
                _sha256(finalized.packet_path),
                finalizer_status=finalized.packet.status,
            )
            return finalized.packet.status, None
        if state == "FINALIZING":
            return state, run_directory / "next-action-track-b.json"
        raise ValueError("READY_FOR_REVIEW requires complete final review artifacts")
    else:
        raise ValueError(f"review question run cannot resume from {state}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return state, path


def _existing_finalized_run(run_directory: Path) -> FinalizedReviewRun | None:
    packet_path = run_directory / "final-review-packet.json"
    html_path = run_directory / "review.html"
    if not packet_path.exists() and not html_path.exists():
        return None
    if not packet_path.is_file() or not html_path.is_file():
        return None
    packet = decode_review_packet(_json(packet_path))
    if packet.run_id != run_directory.name:
        raise ValueError("final review packet run_id does not match run directory")
    return FinalizedReviewRun(
        run_id=run_directory.name,
        run_directory=run_directory,
        packet=packet,
        packet_path=packet_path,
        review_html=html_path,
        published_packet=None,
    )


def _recover_incomplete_finalization(run_directory: Path, track_b_output: Path) -> None:
    """Remove only restartable finalizer outputs from an interrupted FINALIZING run."""
    track_b = run_directory / "track-b-output.json"
    if track_b.exists() and track_b.read_bytes() != track_b_output.read_bytes():
        raise FileExistsError("existing Track B artifact differs from retry input")
    for name in (
        "track-b-output.json",
        "run-manifest.json",
        "final-review-packet.json",
        "review.html",
    ):
        (run_directory / name).unlink(missing_ok=True)


def _prepare_from_document(workspace: Path, document: dict[str, object]) -> PreparedReviewRun:
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(dump_bytes(document))
    try:
        return prepare_review_run(workspace, temporary)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_review_question(
    workspace: Path,
    question: str,
    expansions: Sequence[str] = (),
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> PreparedReviewQuestion:
    """Retrieve evidence and create/resume the immutable Track A handoff."""
    query_request = canonical_query_request(question, expansions)
    with EvidenceStore(_evidence_database(workspace)) as store:
        bundle = build_evidence_bundle(store.require_connection(), query_request)
    review_request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    run_id = compute_run_id_from_request(review_request)
    run_directory = workspace / "runs" / run_id
    resumed = run_directory.exists()
    if resumed:
        existing = run_directory / "review-request.json"
        if not existing.is_file() or existing.read_bytes() != dump_bytes(review_request):
            raise ValueError("existing immutable review run differs from question request")
    else:
        _prepare_from_document(workspace, review_request)
    _write_or_identical(run_directory / "evidence-query.json", bundle)
    if not resumed:
        _write_or_identical(
            run_directory / "next-action-track-a.json",
            next_action_document(_track_a_action(run_id)),
        )
        _initialize_events(run_directory)
    status, next_action_path = _resume_state(run_directory)
    return PreparedReviewQuestion(
        run_id=run_id,
        status=status,
        next_action_path=next_action_path,
        resumed=resumed,
    )


def submit_question_track_a(
    workspace: Path,
    run_id: str,
    track_a_output: Path,
) -> SubmittedTrackA:
    """Advance the journal only after Track A's full validation succeeds."""
    result = submit_track_a(workspace, run_id, track_a_output)
    _append_event(result.run_directory, "WAITING_TRACK_B", _sha256(track_a_output))
    return result


def submit_question_track_b(
    workspace: Path,
    run_id: str,
    track_b_output: Path,
    *,
    publish: bool = False,
) -> FinalizedReviewRun:
    """Finalize idempotently from a Track B handoff or interrupted finalization."""
    run_directory = workspace / "runs" / run_id
    state, _action = _resume_state(run_directory)
    if state == "READY_FOR_HUMAN_REVIEW" or state == "ABSTAIN":
        finalized = _existing_finalized_run(run_directory)
        if finalized is None:
            raise ValueError("final review artifacts are incomplete")
        return finalized
    if state not in {"WAITING_TRACK_B", "FINALIZING"}:
        raise ValueError("review question run is not waiting for Track B")
    if state == "WAITING_TRACK_B":
        validate_track_b_submission(workspace, run_id, track_b_output)
        _append_event(run_directory, "FINALIZING", _sha256(track_b_output))
    else:
        finalized = _existing_finalized_run(run_directory)
        if finalized is not None:
            _append_event(
                run_directory,
                "READY_FOR_REVIEW",
                _sha256(finalized.packet_path),
                finalizer_status=finalized.packet.status,
            )
            return finalized
        _recover_incomplete_finalization(run_directory, track_b_output)
    result = submit_track_b(workspace, run_id, track_b_output, publish=publish)
    _append_event(
        result.run_directory,
        "READY_FOR_REVIEW",
        _sha256(result.packet_path),
        finalizer_status=result.packet.status,
    )
    return result


__all__ = [
    "PreparedReviewQuestion",
    "build_review_run_request",
    "canonical_query_request",
    "prepare_review_question",
    "submit_question_track_a",
    "submit_question_track_b",
]
