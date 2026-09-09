"""Deterministic question-to-review-run orchestration without model calls."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from evidence_review.abstention.finalizer import verify_finalized_run
from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.contracts.next_action import NextAction, next_action_document
from evidence_review.contracts.review import (
    TERMINAL_FINALIZER_STATUSES,
    FinalizerStatus,
)
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.contracts.workflow import WorkflowState
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.observability.run_metrics import (
    append_stage,
    finish_stage,
    record_external_wait,
    start_stage,
)
from evidence_review.retrieval.bundle import build_evidence_bundle
from evidence_review.review_packet.builder import build_review_view_model
from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_run import (
    FinalizedReviewRun,
    PreparedReviewRun,
    SubmittedTrackA,
    TrackBContractError,
    prepare_review_run,
    submit_track_a,
    submit_track_b,
    validate_track_b_submission,
)
from evidence_review.workflow.artifact_ownership import FINALIZATION_DERIVED
from evidence_review.workflow.events import (
    append_workflow_event,
    load_workflow_events,
    make_workflow_event,
    workflow_events_directory,
)


@dataclass(frozen=True, slots=True)
class PreparedReviewQuestion:
    """The run and safe handoff produced for one fully deterministic question."""

    run_id: str
    status: str
    next_action_path: Path | None
    resumed: bool
    retrieval_guidance_path: Path | None
    run_directory: Path | None = None


class ReviewEvidenceSnapshotError(RuntimeError):
    """Stable fail-closed error when a prepared run no longer matches its workspace."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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
        existing = verified_regular_file_below(
            path.parent,
            (path.name,),
            field=f"run artifact {path.name}",
        )
        if existing.read_bytes() != encoded:
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


def _validated_snapshot_provenance(value: object, snapshot_hash: str) -> dict[str, object] | None:
    if value is None:
        return None
    provenance = dict(_mapping(value, "evidence_bundle.snapshot_provenance"))
    required = {
        "evidence_snapshot_hash",
        "evidence_db_sha256",
        "schema_version",
        "retrieval_record_count",
        "clause_record_count",
    }
    if set(provenance) != required:
        raise ValueError("evidence_bundle.snapshot_provenance has invalid fields")
    if provenance["evidence_snapshot_hash"] != snapshot_hash:
        raise ValueError("evidence snapshot provenance does not match bundle snapshot")
    db_sha = provenance["evidence_db_sha256"]
    if not isinstance(db_sha, str) or len(db_sha) != 64:
        raise ValueError("evidence_snapshot_provenance.evidence_db_sha256 must be SHA-256")
    for field in ("schema_version", "retrieval_record_count", "clause_record_count"):
        if isinstance(provenance[field], bool) or not isinstance(provenance[field], int):
            raise ValueError(f"evidence_snapshot_provenance.{field} must be an integer")
    return provenance


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
    provenance = _validated_snapshot_provenance(
        payload.get("snapshot_provenance"),
        snapshot_hash,
    )

    evidence: list[dict[str, object]] = []
    for index, hit in enumerate(_sequence(payload.get("hits"), "evidence_bundle.hits")):
        hit_payload = _mapping(hit, f"evidence_bundle.hits[{index}]")
        citation = hit_payload.get("citation")
        text = hit_payload.get("text")
        if isinstance(text, str) and not text.strip():
            continue
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
    evidence_dependent_factors = {
        "source completeness",
        "traceability",
        "input completeness",
    }
    inputs: dict[str, object] = {"snapshot_hash": snapshot_hash}
    if provenance is not None:
        inputs["evidence_snapshot_provenance"] = provenance
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": question,
        "inputs": inputs,
        "evidence": evidence,
        "calculations": calculation_documents,
        "rules": rule_documents,
        "approved_rule_result_ids": approved,
        "confidence_input": {
            "factors": {
                name: {
                    "value": (
                        "0.0"
                        if not evidence and name in evidence_dependent_factors
                        else "1.0"
                    ),
                    "source": "retrieval:evidence_availability",
                }
                for name in FACTOR_WEIGHTS
            }
        },
    }


def _evidence_database(workspace: Path) -> Path:
    return verified_regular_file_below(
        workspace,
        ("evidence", "evidence.sqlite"),
        field="evidence database",
    )


def _run_expected_snapshot_provenance(
    run_directory: Path,
) -> tuple[str, dict[str, object]]:
    request_path = verified_regular_file_below(
        run_directory,
        ("review-request.json",),
        field="review request",
    )
    request = _mapping(_json(request_path), "review_request")
    inputs = _mapping(request.get("inputs"), "review_request.inputs")
    expected = inputs.get("snapshot_hash")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ReviewEvidenceSnapshotError(
            "STALE_REVIEW_RUN",
            "prepared review run does not contain a valid evidence snapshot identity",
        )
    provenance = inputs.get("evidence_snapshot_provenance")
    if provenance is None:
        raise ReviewEvidenceSnapshotError(
            "STALE_REVIEW_RUN",
            "prepared review run is missing exact evidence database provenance",
        )
    try:
        bound = _validated_snapshot_provenance(provenance, expected)
    except (TypeError, ValueError) as error:
        raise ReviewEvidenceSnapshotError(
            "STALE_REVIEW_RUN",
            "prepared review run snapshot provenance is invalid",
        ) from error
    if bound is None:
        raise ReviewEvidenceSnapshotError(
            "STALE_REVIEW_RUN",
            "prepared review run is missing exact evidence database provenance",
        )
    return expected, bound


def _run_expected_snapshot_hash(run_directory: Path) -> str:
    """Return the logical snapshot identity retained for compatibility callers."""
    expected, _provenance = _run_expected_snapshot_provenance(run_directory)
    return expected


def _assert_run_evidence_snapshot(run_directory: Path) -> dict[str, object]:
    """Fail closed when a prepared run is resumed against a different evidence snapshot."""
    expected, expected_provenance = _run_expected_snapshot_provenance(run_directory)
    workspace = run_directory.parent.parent
    try:
        active = finalized_evidence_provenance(_evidence_database(workspace))
    except ReviewEvidenceSnapshotError:
        raise
    except Exception as error:
        raise ReviewEvidenceSnapshotError(
            "WORKSPACE_EVIDENCE_MISMATCH",
            f"active workspace evidence identity cannot be verified: {error}",
        ) from error
    actual = active.get("evidence_snapshot_hash")
    if actual != expected:
        raise ReviewEvidenceSnapshotError(
            "EVIDENCE_SNAPSHOT_MISMATCH",
            f"prepared run snapshot {expected} does not match active workspace snapshot {actual}",
        )
    actual_file_hash = active.get("evidence_db_sha256")
    expected_file_hash = expected_provenance["evidence_db_sha256"]
    if actual_file_hash != expected_file_hash:
        raise ReviewEvidenceSnapshotError(
            "EVIDENCE_DATABASE_MISMATCH",
            "prepared review run evidence database bytes do not match the bound artifact",
        )
    return active


def _track_a_action(run_id: str) -> NextAction:
    return NextAction(
        format="evidence-review/next-action",
        version=1,
        run_id=run_id,
        workflow_state="WAITING_TRACK_A",
        action="PRODUCE_TRACK_A",
        input_bundle="track-a-bundle.json",
        instructions="TRACK_A_INSTRUCTIONS.md",
        expected_output="track-a-attempt-1.json",
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


def _run_file(run_directory: Path, name: str) -> Path:
    return verified_regular_file_below(
        run_directory,
        (name,),
        field=f"run artifact {name}",
    )


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _track_b_identity(path: Path) -> str:
    """Return Track B identity independent of JSON serialization details."""
    return sha256_json(_json(path))


def _matches_track_b_identity(path: Path, expected: str) -> bool:
    """Match canonical identity, with exact raw bytes for legacy FINALIZING events."""
    return _track_b_identity(path) == expected or _sha256(path) == expected


def _append_event(
    run_directory: Path,
    next_state: WorkflowState,
    payload_sha256: str,
    *,
    finalizer_status: FinalizerStatus | None = None,
) -> None:
    events_directory = workflow_events_directory(run_directory)
    events = load_workflow_events(events_directory)
    if events and events[-1].next_state == next_state:
        return
    sequence = len(events) + 1
    previous = events[-1].next_state if events else None
    append_workflow_event(
        events_directory,
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
    _assert_run_evidence_snapshot(run_directory)
    events_directory = workflow_events_directory(run_directory)
    events = load_workflow_events(events_directory)
    if not events:
        _initialize_events(run_directory)
        events = load_workflow_events(workflow_events_directory(run_directory))
    state = events[-1].next_state
    if state == "WAITING_TRACK_A":
        path = run_directory / "next-action-track-a.json"
    elif state == "WAITING_TRACK_B":
        path = run_directory / "next-action-track-b.json"
    elif state in {"FINALIZING", "READY_FOR_REVIEW"}:
        try:
            finalized = _existing_finalized_run(run_directory)
        except ValueError:
            if state == "FINALIZING":
                return state, run_directory / "next-action-track-b.json"
            raise
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
    path = _run_file(run_directory, path.name)
    return state, path


def _existing_finalized_run(run_directory: Path) -> FinalizedReviewRun | None:
    packet_path: Path | None
    html_path: Path | None
    try:
        packet_path = _run_file(run_directory, "final-review-packet.json")
    except FileNotFoundError:
        packet_path = None
    try:
        html_path = _run_file(run_directory, "review.html")
    except FileNotFoundError:
        html_path = None
    if packet_path is None and html_path is None:
        return None
    if packet_path is None or html_path is None:
        return None
    packet = verify_finalized_run(run_directory)
    workspace = run_directory.parent.parent
    view_model = build_review_view_model(
        packet_path.read_bytes(),
        _evidence_database(workspace),
    )
    expected_html = render_review_html(view_model, workspace / "page-images")
    if html_path.read_text(encoding="utf-8") != expected_html:
        raise ValueError("review HTML does not match the verified final packet")
    return FinalizedReviewRun(
        run_id=run_directory.name,
        run_directory=run_directory,
        packet=packet,
        packet_path=packet_path,
        review_html=html_path,
        published_packet=None,
    )


def _recover_incomplete_finalization(
    run_directory: Path,
    track_b_output: Path,
) -> None:
    """Recover restartable outputs while preserving validated Track B input."""
    try:
        canonical = _run_file(run_directory, "track-b-output.json")
    except FileNotFoundError:
        canonical = None
    if canonical is not None:
        try:
            canonical_document = _json(canonical)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            canonical_document = None

        if canonical_document is not None:
            incoming = dump_bytes(_json(track_b_output))
            if dump_bytes(canonical_document) != incoming:
                raise TrackBContractError(
                    "TRACK_B_INPUT_MISMATCH",
                    "validated run-local Track B differs from retry input",
                )
        elif track_b_output.resolve() == canonical:
            raise ValueError(
                "malformed run-local Track B cannot be recovered as validated input"
            )
        else:
            canonical.unlink()

    for name in sorted(FINALIZATION_DERIVED):
        (run_directory / name).unlink(missing_ok=True)


def _required_finalizing_track_b_hash(run_directory: Path) -> str:
    events = load_workflow_events(workflow_events_directory(run_directory))
    finalizing = [event for event in events if event.next_state == "FINALIZING"]
    if not finalizing:
        raise ValueError("FINALIZING state requires a Track B identity event")
    return finalizing[-1].payload_sha256


def _has_valid_finalizing_canonical_track_b(run_directory: Path) -> bool:
    try:
        canonical = _run_file(run_directory, "track-b-output.json")
    except FileNotFoundError:
        return False
    try:
        return _matches_track_b_identity(
            canonical,
            _required_finalizing_track_b_hash(run_directory),
        )
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def _validate_finalizing_retry_identity(
    run_directory: Path,
    track_b_output: Path,
) -> None:
    expected = _required_finalizing_track_b_hash(run_directory)
    if not _matches_track_b_identity(track_b_output, expected):
        raise TrackBContractError(
            "TRACK_B_RETRY_MISMATCH",
            "retry Track B does not match the artifact that entered FINALIZING",
        )


def _prepare_from_document(workspace: Path, document: dict[str, object]) -> PreparedReviewRun:
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(dump_bytes(document))
    try:
        return prepare_review_run(workspace, temporary)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_review_request_document(
    workspace: Path,
    document: dict[str, object],
    *,
    additional_artifacts: Mapping[str, object] | None = None,
) -> PreparedReviewQuestion:
    """Prepare one already-bound immutable request through the formal core."""
    run_id = compute_run_id_from_request(document)
    try:
        run_directory = verified_regular_directory(
            workspace / "runs" / run_id,
            field="run directory",
        )
        resumed = True
        existing = _run_file(run_directory, "review-request.json")
        if existing.read_bytes() != dump_bytes(document):
            raise ValueError("existing immutable review run differs from request")
    except FileNotFoundError:
        prepared = _prepare_from_document(workspace, document)
        run_directory = prepared.run_directory
        resumed = False

    for name, artifact in (additional_artifacts or {}).items():
        _write_or_identical(run_directory / name, artifact)
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
        retrieval_guidance_path=None,
        run_directory=run_directory,
    )


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
    normalization_timer = start_stage()
    query_request = canonical_query_request(question, expansions)
    normalization_metric = finish_stage("request-normalization", normalization_timer)

    retrieval_timer = start_stage()
    database = _evidence_database(workspace)
    with EvidenceStore(database, read_only=True) as store:
        connection = store.require_connection()
        validate_finalized_evidence(store)
        bundle = dict(build_evidence_bundle(connection, query_request))
    bundle["snapshot_provenance"] = finalized_evidence_provenance(database)
    retrieval_metric = finish_stage("retrieval", retrieval_timer)

    request_timer = start_stage()
    review_request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    request_metric = finish_stage("review-request-build", request_timer)

    run_id = compute_run_id_from_request(review_request)
    try:
        run_directory = verified_regular_directory(
            workspace / "runs" / run_id,
            field="run directory",
        )
    except FileNotFoundError:
        run_directory = workspace / "runs" / run_id
        resumed = False
    else:
        resumed = True
    prepare_timer = start_stage()
    if resumed:
        existing = _run_file(run_directory, "review-request.json")
        if existing.read_bytes() != dump_bytes(review_request):
            raise ValueError("existing immutable review run differs from question request")
        prepare_metric = finish_stage("prepare", prepare_timer, status="SKIPPED")
    else:
        prepared = _prepare_from_document(workspace, review_request)
        run_directory = prepared.run_directory
        prepare_metric = finish_stage("prepare", prepare_timer)
    _write_or_identical(run_directory / "evidence-query.json", bundle)

    guidance_path: Path | None = None
    query_payload = _mapping(bundle["query"], "evidence_bundle.query")
    attempted = query_payload.get("attempted_terms", [])
    if not bundle["hits"] and attempted:
        guidance_path = run_directory / "retrieval-guidance.json"
        _write_or_identical(
            guidance_path,
            {
                "format": "evidence-review/retrieval-guidance",
                "version": 1,
                "query": query_payload["primary"],
                "attempted_terms": attempted,
                "authoritative_hit_count": 0,
            },
        )

    for metric in (
        normalization_metric,
        retrieval_metric,
        request_metric,
        prepare_metric,
    ):
        append_stage(run_directory, metric)

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
        retrieval_guidance_path=guidance_path,
        run_directory=run_directory,
    )


def submit_question_track_a(
    workspace: Path,
    run_id: str,
    track_a_output: Path,
) -> SubmittedTrackA:
    """Advance the journal only after Track A's full validation succeeds."""
    run_directory = workspace / "runs" / run_id
    _assert_run_evidence_snapshot(run_directory)
    state, _action = _resume_state(run_directory)
    if state != "WAITING_TRACK_A":
        raise ValueError("review question run is not waiting for Track A")
    record_external_wait(
        run_directory,
        "track-a-external-wait",
        after_stage="prepare",
    )
    timer = start_stage()
    try:
        result = submit_track_a(workspace, run_id, track_a_output)
    except Exception as error:
        append_stage(
            run_directory,
            finish_stage(
                "track-a-validation",
                timer,
                status="FAILED",
                reason_code=type(error).__name__.upper(),
            ),
        )
        raise
    append_stage(run_directory, finish_stage("track-a-validation", timer))
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
    if state in TERMINAL_FINALIZER_STATUSES:
        finalized = _existing_finalized_run(run_directory)
        if finalized is None:
            raise ValueError("final review artifacts are incomplete")
        return finalized
    if state not in {"WAITING_TRACK_B", "FINALIZING"}:
        raise ValueError("review question run is not waiting for Track B")

    track_b_input = track_b_output
    if state == "FINALIZING":
        if _has_valid_finalizing_canonical_track_b(run_directory):
            canonical = _run_file(run_directory, "track-b-output.json")
            if track_b_output.resolve() != canonical.resolve():
                raise TrackBContractError(
                    "TRACK_B_REGENERATION_FORBIDDEN",
                    "finalizing recovery must reuse the runtime-owned canonical Track B",
                )
            track_b_input = canonical
        else:
            _validate_finalizing_retry_identity(run_directory, track_b_output)

    record_external_wait(
        run_directory,
        "track-b-external-wait",
        after_stage="track-a-validation",
    )
    validation_timer = start_stage()
    try:
        validate_track_b_submission(workspace, run_id, track_b_input)
    except Exception as error:
        append_stage(
            run_directory,
            finish_stage(
                "track-b-validation",
                validation_timer,
                status="FAILED",
                reason_code=type(error).__name__.upper(),
            ),
        )
        raise
    append_stage(run_directory, finish_stage("track-b-validation", validation_timer))

    if state == "WAITING_TRACK_B":
        _append_event(run_directory, "FINALIZING", _track_b_identity(track_b_output))
    else:
        try:
            finalized = _existing_finalized_run(run_directory)
        except ValueError:
            finalized = None
        if finalized is not None:
            _append_event(
                run_directory,
                "READY_FOR_REVIEW",
                _sha256(finalized.packet_path),
                finalizer_status=finalized.packet.status,
            )
            return finalized
        _recover_incomplete_finalization(run_directory, track_b_input)
    result = submit_track_b(
        workspace,
        run_id,
        track_b_input,
        publish=publish,
        prevalidated=True,
    )
    _append_event(
        result.run_directory,
        "READY_FOR_REVIEW",
        _sha256(result.packet_path),
        finalizer_status=result.packet.status,
    )
    return result


__all__ = [
    "PreparedReviewQuestion",
    "ReviewEvidenceSnapshotError",
    "build_review_run_request",
    "canonical_query_request",
    "prepare_review_question",
    "prepare_review_request_document",
    "submit_question_track_a",
    "submit_question_track_b",
]
