"""Secure run-directory layout and immutable request persistence."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.workflow import WorkflowStateRecord
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.workflow.events import project_workflow_state
from evidence_review.workflow.request import (
    ReviewRequest,
    decode_review_request,
    review_request_bytes,
    review_request_sha256,
)


def _strict_json(raw: bytes, field: str) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=reject_duplicate_keys,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must be valid UTF-8 JSON") from exc


def _write_create_only_or_identical(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = verified_regular_directory(
        path.parent,
        field="review run artifact directory",
    )
    target = parent / path.name
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing = verified_regular_file_below(
            parent,
            (path.name,),
            field=f"review run artifact {path.name}",
        )
        if existing.read_bytes() == payload:
            return
        raise FileExistsError(
            f"existing run artifact differs: {path.name}"
        ) from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True, slots=True)
class ReviewRunLayout:
    """Canonical file locations for one review run."""

    runs_root: Path
    run_id: str
    run_dir: Path
    request_path: Path
    request_hash_path: Path
    events_dir: Path
    machine_dir: Path
    reference_receipt_path: Path
    reference_receipt_sha256_path: Path

    def load_request(self) -> ReviewRequest:
        """Load and byte-revalidate the immutable request."""
        request_path = verified_regular_file_below(
            self.run_dir,
            ("request.json",),
            field="review request",
        )
        raw = request_path.read_bytes()
        request = decode_review_request(_strict_json(raw, "request"))
        if raw != review_request_bytes(request):
            raise ValueError("request bytes are not canonical")
        expected = self.load_request_sha256()
        if review_request_sha256(request) != expected:
            raise ValueError("request SHA-256 does not match request bytes")
        return request

    def load_request_sha256(self) -> str:
        """Load the exact lowercase request digest sidecar."""
        request_hash_path = verified_regular_file_below(
            self.run_dir,
            ("request.sha256",),
            field="review request hash",
        )
        raw = request_hash_path.read_bytes()
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "request SHA-256 sidecar must be ASCII"
            ) from exc
        if not text.endswith("\n") or len(text) != 65:
            raise ValueError("request SHA-256 sidecar is malformed")
        digest = text[:-1]
        if any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("request SHA-256 sidecar is malformed")
        return digest

    def load_state(self) -> WorkflowStateRecord:
        """Rebuild current state from the append-only event journal."""
        return project_workflow_state(self.events_dir)

    def attachment_path(self, stored_path: str) -> Path:
        """Resolve one validated immutable stored path inside this run."""
        return verified_regular_file_below(
            self.run_dir,
            tuple(stored_path.split("/")),
            field="review attachment",
        )

    def verify_request_attachments(self, request: ReviewRequest) -> None:
        """Rehash immutable attachment bytes before downstream action."""
        for attachment in request.attachments:
            path = self.attachment_path(attachment.stored_path)
            payload = path.read_bytes()
            if len(payload) != attachment.byte_size:
                raise ValueError(
                    "SOURCE_HASH_MISMATCH: byte size differs for "
                    f"{attachment.attachment_id}"
                )
            digest = hashlib.sha256(payload).hexdigest()
            if digest != attachment.sha256:
                raise ValueError(
                    "SOURCE_HASH_MISMATCH: source differs for "
                    f"{attachment.attachment_id}"
                )


def review_run_layout(runs_root: Path, run_id: str) -> ReviewRunLayout:
    """Return canonical direct-child paths for one validated run ID."""
    validated_run_id = validate_identifier(run_id, "run_id")
    try:
        root = verified_regular_directory(runs_root, field="runs root")
    except FileNotFoundError:
        runs_root.parent.mkdir(parents=True, exist_ok=True)
        parent = verified_regular_directory(
            runs_root.parent,
            field="runs root parent",
        )
        candidate = parent / runs_root.name
        candidate.mkdir(exist_ok=False)
        root = verified_regular_directory(candidate, field="runs root")
    run_dir = root / validated_run_id
    return ReviewRunLayout(
        runs_root=root,
        run_id=validated_run_id,
        run_dir=run_dir,
        request_path=run_dir / "request.json",
        request_hash_path=run_dir / "request.sha256",
        events_dir=run_dir / "events",
        machine_dir=run_dir / "machine",
        reference_receipt_path=(
            run_dir / "machine" / "reference-ingestion.json"
        ),
        reference_receipt_sha256_path=(
            run_dir / "machine" / "reference-ingestion.sha256"
        ),
    )


def initialize_review_run(
    runs_root: Path,
    run_id: str,
    request: ReviewRequest,
) -> ReviewRunLayout:
    """Persist one immutable request while preserving pre-copied inputs."""
    layout = review_run_layout(runs_root, run_id)
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    verified_regular_directory(layout.run_dir, field="run directory")
    layout.verify_request_attachments(request)
    encoded = review_request_bytes(request)
    digest = review_request_sha256(request)
    _write_create_only_or_identical(layout.request_path, encoded)
    _write_create_only_or_identical(
        layout.request_hash_path,
        f"{digest}\n".encode("ascii"),
    )
    layout.load_request()
    return layout


def open_review_run(runs_root: Path, run_id: str) -> ReviewRunLayout:
    """Open an existing run without trusting mutable projections."""
    layout = review_run_layout(runs_root, run_id)
    verified_regular_directory(layout.run_dir, field="run directory")
    layout.load_request()
    return layout
