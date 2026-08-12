"""Deterministic question-to-review-run orchestration without model calls."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.contracts.next_action import NextAction, next_action_document
from ansim_review.contracts.run_context import compute_run_id_from_request
from ansim_review.evidence.store import EvidenceStore
from ansim_review.retrieval.bundle import build_evidence_bundle
from ansim_review.review_run import PreparedReviewRun, prepare_review_run


@dataclass(frozen=True, slots=True)
class PreparedReviewQuestion:
    """The run and safe handoff produced for one fully deterministic question."""

    run_id: str
    next_action_path: Path
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
        normalized_expansions.append({"text": term, "origin": "llm"})
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


def build_review_run_request(bundle: object) -> dict[str, object]:
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
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": question,
        "inputs": {"snapshot_hash": snapshot_hash},
        "evidence": evidence,
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": [],
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
) -> PreparedReviewQuestion:
    """Retrieve evidence and create/resume the immutable Track A handoff."""
    query_request = canonical_query_request(question, expansions)
    with EvidenceStore(_evidence_database(workspace)) as store:
        bundle = build_evidence_bundle(store.require_connection(), query_request)
    review_request = build_review_run_request(bundle)
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
    _write_or_identical(
        run_directory / "next-action-track-a.json",
        next_action_document(_track_a_action(run_id)),
    )
    return PreparedReviewQuestion(
        run_id=run_id,
        next_action_path=run_directory / "next-action-track-a.json",
        resumed=resumed,
    )


__all__ = [
    "PreparedReviewQuestion",
    "build_review_run_request",
    "canonical_query_request",
    "prepare_review_question",
]
