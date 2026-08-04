"""Secure run-directory layout and immutable request persistence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.workflow import WorkflowStateRecord
from ansim_review.workflow.events import project_workflow_state
from ansim_review.workflow.request import (
    ReviewRequest,
    decode_review_request,
    review_request_bytes,
    review_request_sha256,
)


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def reject_link_ancestors(path: Path) -> None:
    """Reject symlink or Windows reparse-point authority in a run path."""
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if not candidate.exists():
            continue
        if candidate.is_symlink() or _is_reparse_point(candidate):
            raise ValueError(
                "review run path must not contain links or reparse points"
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
    reject_link_ancestors(path.parent)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        reject_link_ancestors(path)
        if path.read_bytes() == payload:
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
        reject_link_ancestors(self.request_path)
        raw = self.request_path.read_bytes()
        request = decode_review_request(_strict_json(raw, "request"))
        if raw != review_request_bytes(request):
            raise ValueError("request bytes are not canonical")
        expected = self.load_request_sha256()
        if review_request_sha256(request) != expected:
            raise ValueError("request SHA-256 does not match request bytes")
        return request

    def load_request_sha256(self) -> str:
        """Load the exact lowercase request digest sidecar."""
        reject_link_ancestors(self.request_hash_path)
        raw = self.request_hash_path.read_bytes()
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
        target = self.run_dir.joinpath(*stored_path.split("/"))
        resolved_run = self.run_dir.resolve()
        if not target.resolve(strict=False).is_relative_to(resolved_run):
            raise ValueError("attachment stored_path escapes the run directory")
        reject_link_ancestors(target)
        return target

    def verify_request_attachments(self, request: ReviewRequest) -> None:
        """Rehash immutable attachment bytes before downstream action."""
        for attachment in request.attachments:
            path = self.attachment_path(attachment.stored_path)
            if not path.is_file():
                raise FileNotFoundError(path)
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
    reject_link_ancestors(runs_root)
    validated_run_id = validate_identifier(run_id, "run_id")
    root = runs_root.resolve()
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
    reject_link_ancestors(layout.runs_root)
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    reject_link_ancestors(layout.run_dir)
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
    reject_link_ancestors(layout.run_dir)
    if not layout.run_dir.is_dir():
        raise FileNotFoundError(layout.run_dir)
    layout.load_request()
    return layout
